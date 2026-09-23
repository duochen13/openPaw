"""Robinhood CSV position import + holdings snapshot (issue #55).

Covers the tolerant CSV parser (header aliases, skipped non-equity rows,
duplicate-lot merging, bad input), the timestamped snapshot round-trip, and
the factor-dashboard holdings table rendering with staleness.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from portfolio_analysis.factor_dashboard import (
    factor_dashboard_data,
    render_factor_dashboard,
)
from portfolio_analysis.positions import (
    ImportResult,
    Position,
    Snapshot,
    load_snapshot,
    parse_robinhood_csv,
    write_snapshot,
)

CSV_BASIC = """Symbol,Quantity,Average Cost
NOW,213,135.00
META,20,550.00
"""

CSV_ALIASES = """ticker,qty,avg cost
now,100,$200.50
tsla,15,"1,234.56"
"""

CSV_MESSY = """Symbol,Quantity,Average Cost,Market Value
AAPL,10,150.00,1800.00
AAPL  260919C00150000,5,2.50,1250.00
DOGEUSD,1000,0.20,300.00
,5,10.00,50.00
MSFT,abc,300.00,0.00
GOOGL,10,,0.00
TSLA,0,287.00,0.00
NVDA,10,-5.00,0.00

NFLX,23,74.00,1700.00
"""


def _write(tmp_path: Path, text: str, name: str = "positions.csv") -> Path:
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


def test_parse_basic(tmp_path: Path) -> None:
    result = parse_robinhood_csv(_write(tmp_path, CSV_BASIC))
    assert result.positions == (
        Position(symbol="META", shares=20.0, avg_cost=550.0),
        Position(symbol="NOW", shares=213.0, avg_cost=135.0),
    )
    assert result.skipped == ()


def test_parse_header_aliases_and_money_formats(tmp_path: Path) -> None:
    result = parse_robinhood_csv(_write(tmp_path, CSV_ALIASES))
    assert result.positions == (
        Position(symbol="NOW", shares=100.0, avg_cost=200.50),
        Position(symbol="TSLA", shares=15.0, avg_cost=1234.56),
    )


def test_parse_skips_non_equity_and_bad_rows(tmp_path: Path) -> None:
    result = parse_robinhood_csv(_write(tmp_path, CSV_MESSY))
    symbols = [p.symbol for p in result.positions]
    assert symbols == ["AAPL", "NFLX"]
    reasons = {(s.symbol, s.reason) for s in result.skipped}
    assert any("AAPL  260919C00150000" in sym for sym, _ in reasons)
    assert any("DOGEUSD" in sym for sym, _ in reasons)
    assert any("blank symbol" in reason for _, reason in reasons)
    assert any("MSFT" in sym for sym, _ in reasons)  # non-numeric shares
    assert any("GOOGL" in sym for sym, _ in reasons)  # blank avg cost
    assert any("zero shares" in reason for _, reason in reasons)  # TSLA
    assert any("negative avg cost" in reason for _, reason in reasons)  # NVDA


def test_parse_merges_duplicate_lots_with_weighted_cost(tmp_path: Path) -> None:
    csv_text = "Symbol,Quantity,Average Cost\nNOW,100,120.00\nNOW,100,140.00\n"
    result = parse_robinhood_csv(_write(tmp_path, csv_text))
    assert result.positions == (Position(symbol="NOW", shares=200.0, avg_cost=130.0),)


def test_parse_missing_columns_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required column"):
        parse_robinhood_csv(_write(tmp_path, "Symbol,Quantity\nNOW,213\n"))


def test_parse_empty_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty CSV"):
        parse_robinhood_csv(_write(tmp_path, ""))


def test_snapshot_round_trip_is_timestamped(tmp_path: Path) -> None:
    result = ImportResult(
        positions=(Position(symbol="NOW", shares=213.0, avg_cost=135.0),),
        skipped=(),
    )
    target = write_snapshot(result, tmp_path / "positions.yaml")
    snapshot = load_snapshot(target)
    assert snapshot is not None
    assert snapshot.source == "robinhood-csv"
    assert snapshot.positions == result.positions
    # Timestamped within the last minute: a stale import is visible, not silent.
    assert datetime.now(UTC) - snapshot.imported_at.astimezone(UTC) < timedelta(minutes=1)
    assert snapshot.age_days() == 0
    assert not snapshot.stale


def test_load_missing_snapshot_returns_none(tmp_path: Path) -> None:
    assert load_snapshot(tmp_path / "nope.yaml") is None


def test_load_malformed_snapshot_raises(tmp_path: Path) -> None:
    target = tmp_path / "positions.yaml"
    target.write_text("snapshot: {}\npositions: [{symbol: NOW}]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="imported_at"):
        load_snapshot(target)


def test_load_rejects_bad_numbers(tmp_path: Path) -> None:
    target = tmp_path / "positions.yaml"
    target.write_text(
        "snapshot:\n  imported_at: '2026-09-23T00:00:00+00:00'\n  source: x\n"
        "positions:\n  - symbol: NOW\n    shares: 'a lot'\n    avg_cost: 135.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid shares"):
        load_snapshot(target)


def test_stale_snapshot_flagged(tmp_path: Path) -> None:
    old = datetime.now(UTC) - timedelta(days=45)
    target = write_snapshot(
        (Position(symbol="NOW", shares=1.0, avg_cost=1.0),),
        tmp_path / "positions.yaml",
        imported_at=old,
    )
    snapshot = load_snapshot(target)
    assert snapshot is not None
    assert snapshot.age_days() >= 45
    assert snapshot.stale


def _snapshot() -> Snapshot:
    return Snapshot(
        imported_at=datetime.now(UTC),
        source="robinhood-csv",
        positions=(
            Position(symbol="AAA", shares=10.0, avg_cost=100.0),
            Position(symbol="ZZZ", shares=5.0, avg_cost=50.0),  # not configured
        ),
    )


def test_factor_data_holdings_valued_at_latest_close(tmp_path: Path) -> None:
    from tests.test_factor_dashboard import _bars, _gen_bench, _portfolio, _seed

    portfolio = _portfolio()
    store = _seed(tmp_path)
    try:
        # ZZZ has prices but is outside the configured universe.
        _, zzz, _ = _gen_bench(999, 320)
        store.upsert_price_bars(_bars("ZZZ", zzz))
        data = factor_dashboard_data(portfolio, store, snapshot=_snapshot())
    finally:
        store.close()
    holdings = data["holdings"]
    assert isinstance(holdings, dict)
    rows = {r["symbol"]: r for r in holdings["rows"]}
    assert set(rows) == {"AAA", "ZZZ"}
    aaa = rows["AAA"]
    assert aaa["shares"] == 10.0
    assert aaa["price"] is not None  # valued at the latest stored close
    assert aaa["value"] == pytest.approx(10.0 * aaa["price"], abs=0.05)
    assert aaa["gain"] == pytest.approx(aaa["value"] - 1000.0, abs=0.05)
    assert aaa["name"] == "AAA Inc."  # configured name wins
    assert rows["ZZZ"]["name"] == "ZZZ"  # falls back to the symbol
    assert holdings["age_days"] == 0
    assert holdings["stale"] is False


def test_factor_data_without_snapshot_has_no_holdings(tmp_path: Path) -> None:
    from tests.test_factor_dashboard import _portfolio, _seed

    store = _seed(tmp_path)
    try:
        data = factor_dashboard_data(_portfolio(), store)
    finally:
        store.close()
    assert data["holdings"] is None


def test_render_holdings_table_and_stale_badge(tmp_path: Path) -> None:
    holdings = {
        "as_of": "2026-09-23T02:15-07:00",
        "age_days": 45,
        "stale": True,
        "source": "robinhood-csv",
        "rows": [
            {
                "symbol": "AAA",
                "name": "AAA Inc.",
                "shares": 10.0,
                "avg_cost": 100.0,
                "price": 120.0,
                "value": 1200.0,
                "gain": 200.0,
                "gain_pct": 20.0,
                "alpha": 0.05,
            }
        ],
    }
    target = render_factor_dashboard(
        {
            "dates": [],
            "stocks": {},
            "window": 250,
            "benchmark": "QQQ",
            "asof": "",
            "holdings": holdings,
        },
        tmp_path,
    )
    page = target.read_text(encoding="utf-8")
    assert "Holdings" in page
    assert "STALE" in page
    assert "2026-09-23T02:15-07:00" in page  # snapshot timestamp visible
    assert "45 day(s) old" in page
    assert "$1,200.00" in page
    assert "+5.0%" in page  # alpha next to the holding


def test_render_without_snapshot_has_no_holdings(tmp_path: Path) -> None:
    target = render_factor_dashboard(
        {
            "dates": [],
            "stocks": {},
            "window": 250,
            "benchmark": "QQQ",
            "asof": "",
            "holdings": None,
        },
        tmp_path,
    )
    assert "Holdings" not in target.read_text(encoding="utf-8")
