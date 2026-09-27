"""Robinhood CSV position import + holdings snapshot (issue #55).

Covers the tolerant CSV parser (header aliases, skipped non-equity rows,
duplicate-lot merging, bad input) and the timestamped snapshot round-trip.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from portfolio_analysis.positions import (
    ImportResult,
    Position,
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
