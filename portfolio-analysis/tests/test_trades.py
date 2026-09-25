"""Robinhood order-history import + trade markers (issue #65).

Covers CSV flavor detection, the tolerant order parser (header aliases,
buy/sell mapping, skipped non-trade rows, date filtering), the trades.yaml
round-trip, per-symbol filtering, and the dashboard payload injection.
"""

from pathlib import Path

import pytest

from portfolio_analysis.positions import (
    Trade,
    detect_robinhood_csv_kind,
    load_trades,
    parse_robinhood_orders_csv,
    trades_for_symbol,
    write_trades,
)

ORDERS_BASIC = """Activity Date,Instrument,Trans Code,Quantity,Price
2026-09-23,GOOGL,Buy,6,349.93
2026-09-22,MU,Sell,1,1040.00
2026-09-22,DAL,sell,1,83.92
"""

ORDERS_ALIASES = """trade date,symbol,side,qty,fill price
09/23/2026,googl,BUY,6,349.93
2026/09/22,TSM,Sold,1,447.97
"""

ORDERS_MESSY = """Activity Date,Instrument,Trans Code,Quantity,Price,Amount
2026-09-23,GOOGL,Buy,6,349.93,2099.58
2026-09-23,GOOGL,Dividend,0,0,10.50
2026-09-22,MU,Fee,0,0,5.00
2026-09-22,DAL,Transfer,0,0,20000.00
2026-09-21,AAPL  260919C00150000,Buy,5,2.50,12.50
2026-09-21,DOGEUSD,Sell,1000,0.20,200.00
2026-09-20,NVDA,Buy,0,224.54,0.00
2026-09-20,TSLA,Buy,6,-340.00,-2040.00
2026-09-19,,Buy,10,100.00,1000.00
2026-09-18,META,Buy,abc,571.30,0.00
2026-09-17,NFLX,Buy,10,74.02,740.20
"""

POSITIONS_CSV = """Symbol,Quantity,Average Cost
NOW,213,135.00
"""

GARBAGE_CSV = """Foo,Bar
1,2
"""


def _write(tmp_path: Path, text: str, name: str = "orders.csv") -> Path:
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


def test_parse_basic_orders(tmp_path: Path) -> None:
    result = parse_robinhood_orders_csv(_write(tmp_path, ORDERS_BASIC))
    assert result.trades == (
        Trade(symbol="DAL", date="2026-09-22", side="sell", qty=1.0, price=83.92),
        Trade(symbol="MU", date="2026-09-22", side="sell", qty=1.0, price=1040.0),
        Trade(symbol="GOOGL", date="2026-09-23", side="buy", qty=6.0, price=349.93),
    )
    assert result.skipped == ()
    assert result.filtered_out == 0


def test_parse_header_aliases_and_date_formats(tmp_path: Path) -> None:
    result = parse_robinhood_orders_csv(_write(tmp_path, ORDERS_ALIASES))
    assert [t.date for t in result.trades] == ["2026-09-22", "2026-09-23"]
    assert {t.side for t in result.trades} == {"buy", "sell"}
    assert all(t.symbol in ("GOOGL", "TSM") for t in result.trades)


def test_parse_skips_non_trade_rows_with_reasons(tmp_path: Path) -> None:
    result = parse_robinhood_orders_csv(_write(tmp_path, ORDERS_MESSY))
    assert [t.symbol for t in result.trades] == ["NFLX", "GOOGL"]
    reasons = {s.symbol: s.reason for s in result.skipped}
    assert "Dividend" in reasons["GOOGL"]
    assert "Fee" in reasons["MU"]
    assert "Transfer" in reasons["DAL"]
    assert "options/crypto" in reasons["AAPL  260919C00150000"]
    assert "options/crypto" in reasons["DOGEUSD"]
    assert "non-positive quantity" in reasons["NVDA"]
    assert "negative price" in reasons["TSLA"]
    assert reasons[""] == "blank symbol"
    assert "not a number" in reasons["META"]


def test_parse_date_filter(tmp_path: Path) -> None:
    result = parse_robinhood_orders_csv(
        _write(tmp_path, ORDERS_BASIC), start_date="2026-09-23", end_date="2026-09-23"
    )
    assert [t.symbol for t in result.trades] == ["GOOGL"]
    assert result.filtered_out == 2


def test_parse_bad_date_filter(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not YYYY-MM-DD"):
        parse_robinhood_orders_csv(_write(tmp_path, ORDERS_BASIC), start_date="Sept 1")
    with pytest.raises(ValueError, match="after end_date"):
        parse_robinhood_orders_csv(
            _write(tmp_path, ORDERS_BASIC),
            start_date="2026-09-24",
            end_date="2026-09-23",
        )


def test_parse_missing_columns(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required column"):
        parse_robinhood_orders_csv(_write(tmp_path, POSITIONS_CSV))


def test_detect_csv_kind(tmp_path: Path) -> None:
    assert detect_robinhood_csv_kind(_write(tmp_path, ORDERS_BASIC)) == "orders"
    assert detect_robinhood_csv_kind(_write(tmp_path, POSITIONS_CSV, "pos.csv")) == "positions"
    with pytest.raises(ValueError, match="cannot tell positions from order history"):
        detect_robinhood_csv_kind(_write(tmp_path, GARBAGE_CSV, "garbage.csv"))


def test_trades_round_trip(tmp_path: Path) -> None:
    result = parse_robinhood_orders_csv(_write(tmp_path, ORDERS_BASIC))
    target = write_trades(result, tmp_path / "trades.yaml")
    loaded = load_trades(target)
    assert loaded == list(result.trades)


def test_load_trades_missing_file(tmp_path: Path) -> None:
    assert load_trades(tmp_path / "nope.yaml") is None


def test_load_trades_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "trades.yaml"
    bad.write_text("trades:\n  - symbol: GOOGL\n    date: '2026-09-23'\n    side: hold\n")
    with pytest.raises(ValueError, match="invalid side"):
        load_trades(bad)
    bad.write_text(
        "trades:\n  - symbol: GOOGL\n    date: 'not-a-date'\n"
        "    side: buy\n    qty: 1\n    price: 1\n"
    )
    with pytest.raises(ValueError, match="invalid date"):
        load_trades(bad)


def test_trades_for_symbol_filters() -> None:
    trades = [
        Trade(symbol="GOOGL", date="2026-09-23", side="buy", qty=6.0, price=349.93),
        Trade(symbol="MU", date="2026-09-22", side="sell", qty=1.0, price=1040.0),
    ]
    assert trades_for_symbol(trades, "googl") == [trades[0]]
    assert trades_for_symbol(trades, "MU") == [trades[1]]
    assert trades_for_symbol(None, "MU") == []
    assert trades_for_symbol([], "MU") == []


def test_render_html_embeds_trades_payload(tmp_path: Path) -> None:
    """The dashboard template must see the trades key when present and
    render identically when it is absent."""
    from portfolio_analysis.render import render_html

    base = {
        "ticker": "NOW",
        "moves": [],
        "dates": ["2026-09-22", "2026-09-23"],
        "prices": [136.0, 137.8],
        "benchmark_prices": [100.0, 101.0],
        "benchmark": "QQQ",
        "beta_window": 60,
        "sigma_window": 60,
        "threshold": 2.0,
        "generated_at": "2026-09-24T00:00:00Z",
    }
    plain = render_html(dict(base))
    assert '"trades"' not in plain
    with_trades = render_html(
        dict(
            base,
            trades=[
                {"date": "2026-09-23", "side": "buy", "qty": 6.0, "price": 349.93},
                {"date": "2026-09-22", "side": "sell", "qty": 1.0, "price": 1040.0},
            ],
        )
    )
    assert '"trades": [{"date": "2026-09-23", "side": "buy"' in with_trades
