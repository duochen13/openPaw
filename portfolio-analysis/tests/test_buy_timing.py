"""Tests for positions.buy_timing — the dashboard "Buy timing" section."""

from portfolio_analysis.positions import Trade, buy_timing


def _trade(date, price, qty=10.0, side="buy", symbol="NOW"):
    return Trade(symbol=symbol, date=date, side=side, qty=qty, price=price)


def _prices(start_day, closes):
    # ISO date strings sort chronologically; day numbers stay two-digit here.
    days = [f"2026-08-{d:02d}" for d in range(start_day, start_day + len(closes))]
    return dict(zip(days, closes, strict=True))


def test_score_positions_buy_in_forward_range():
    # Buy at 100; forward closes range 90..110 -> score = (100-90)/20 = 0.5.
    prices = _prices(1, [100.0] + [90.0, 110.0] * 20)
    (row,) = buy_timing([_trade("2026-08-01", 100.0)], prices)
    assert row.score == 0.5
    assert row.verdict == "mid-range"
    assert row.fwd_low == 90.0 and row.fwd_high == 110.0
    assert row.cost == 1000.0


def test_buy_below_forward_range_scores_negative():
    # Buy at 80 while every forward close is >= 90 -> negative score, near low.
    prices = _prices(1, [80.0] + [90.0, 95.0] * 20)
    (row,) = buy_timing([_trade("2026-08-01", 80.0)], prices)
    assert row.score == (80.0 - 90.0) / (95.0 - 90.0)
    assert row.score < 0
    assert row.verdict == "near low"


def test_buy_above_forward_range_scores_over_one():
    prices = _prices(1, [120.0] + [90.0, 100.0] * 20)
    (row,) = buy_timing([_trade("2026-08-01", 120.0)], prices)
    assert row.score == (120.0 - 90.0) / (100.0 - 90.0)
    assert row.score > 1
    assert row.verdict == "near high"


def test_too_recent_has_no_score():
    prices = _prices(1, [100.0, 101.0, 102.0])  # only 2 forward sessions
    (row,) = buy_timing([_trade("2026-08-01", 100.0)], prices)
    assert row.score is None
    assert row.fwd_low is None and row.fwd_high is None
    assert row.verdict == "too recent"
    assert row.fwd_days == 2


def test_sells_are_excluded():
    prices = _prices(1, [100.0] + [110.0] * 20)
    rows = buy_timing(
        [_trade("2026-08-01", 100.0, side="sell"), _trade("2026-08-01", 100.0)],
        prices,
    )
    assert len(rows) == 1 and rows[0].price == 100.0


def test_empty_trades_and_empty_prices():
    assert buy_timing([], _prices(1, [100.0] * 10)) == []
    (row,) = buy_timing([_trade("2026-08-01", 100.0)], {})
    assert row.score is None and row.ret_since is None


def test_buy_on_non_trading_day_uses_next_bar():
    # No bar for 08-02; the forward window starts after the next bar >= buy date.
    prices = {"2026-08-01": 100.0, "2026-08-03": 101.0, **_prices(4, [102.0] * 30)}
    (row,) = buy_timing([_trade("2026-08-02", 100.5)], prices)
    assert row.fwd_days == 30
    assert row.score is not None


def test_ret_since_uses_latest_close():
    prices = _prices(1, [100.0] + [110.0] * 20 + [150.0])
    (row,) = buy_timing([_trade("2026-08-01", 100.0)], prices)
    assert row.ret_since == 150.0 / 100.0 - 1


def test_flat_forward_range_scores_zero():
    prices = _prices(1, [100.0] + [105.0] * 30)
    (row,) = buy_timing([_trade("2026-08-01", 100.0)], prices)
    assert row.score == 0.0
    assert row.verdict == "near low"
