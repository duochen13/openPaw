from datetime import UTC, datetime
from unittest import mock

import pytest

from portfolio_analysis import prices

NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=UTC)

# Two sessions plus one holiday row Yahoo padded with nulls.
PAYLOAD = {
    "chart": {
        "result": [{
            "meta": {"gmtoffset": -14400},
            "timestamp": [1713974400, 1714060800, 1714147200],
            "indicators": {
                "quote": [{
                    "open": [493.29, 441.0, None],
                    "high": [497.0, 447.9, None],
                    "low": [488.0, 439.71, None],
                    "close": [493.5, 441.38, None],
                    "volume": [22000000.0, 100000000.0, None],
                }],
                "adjclose": [{"adjclose": [493.5, 441.38, None]}],
            },
        }]
    }
}


def _patch(payload=PAYLOAD):
    return mock.patch.object(prices, "_http_get_json", return_value=payload)


@pytest.mark.unit
def test_parses_bars_with_the_adjusted_close():
    with _patch():
        bars = prices.fetch_yahoo("META", years=6, now=NOW)
    assert len(bars) == 2
    assert bars[0]["ticker"] == "META"
    assert bars[0]["close"] == 493.5
    assert bars[0]["adj_close"] == 493.5
    assert bars[0]["source"] == "yahoo"


@pytest.mark.unit
def test_a_padded_holiday_row_is_dropped_not_zero_filled():
    """Yahoo pads holidays and halts with nulls. A partial bar is not a bar,
    and a zero-filled one would produce a fabricated -100% return."""
    with _patch():
        bars = prices.fetch_yahoo("META", years=6, now=NOW)
    assert [b["date"] for b in bars] == ["2024-04-24", "2024-04-25"]


@pytest.mark.unit
def test_dates_use_the_exchange_offset_not_utc():
    """Yahoo timestamps are session instants in UTC. The exchange offset must
    be applied before taking the calendar date, or a late-session timestamp
    lands on the following day and every return around it shifts by one."""
    with _patch():
        bars = prices.fetch_yahoo("META", years=6, now=NOW)
    assert bars[1]["date"] == "2024-04-25"


@pytest.mark.unit
def test_requests_epoch_bounds_rather_than_a_range():
    with _patch() as fake:
        prices.fetch_yahoo("META", years=6, now=NOW)
    url = fake.call_args[0][0]
    p1, p2 = prices.epoch_window(6, NOW)
    assert f"period1={p1}" in url
    assert f"period2={p2}" in url
    # The chart API has no `6y` range value; that is why epoch bounds are used.
    assert "range=" not in url


@pytest.mark.unit
def test_the_epoch_window_spans_six_years_including_the_leap_day():
    """6 * 365.25 = 2191.5 days. The half day matters: subtracted from a
    12:00 `now` it lands on 00:00 of the same calendar day, not 12:00."""
    p1, p2 = prices.epoch_window(6, NOW)
    start = datetime.fromtimestamp(p1, UTC)
    assert (start.year, start.month, start.day) == (2020, 9, 13)
    assert start.hour == 0
    assert p2 == int(NOW.timestamp())


@pytest.mark.unit
def test_an_empty_result_raises_rather_than_returning_no_bars():
    """'This ticker has no history' and 'the vendor did not answer' must not
    look the same to the caller."""
    payload = {"chart": {"result": None, "error": "Not Found"}}
    with _patch(payload), pytest.raises(prices.VendorResponseError):
        prices.fetch_yahoo("META", years=6, now=NOW)


@pytest.mark.unit
def test_a_missing_adjclose_block_raises():
    payload = {
        "chart": {"result": [{
            "meta": {"gmtoffset": 0},
            "timestamp": [1713974400],
            "indicators": {"quote": [{
                "open": [1.0], "high": [1.0], "low": [1.0],
                "close": [1.0], "volume": [1.0],
            }]},
        }]}
    }
    with _patch(payload), pytest.raises(prices.VendorResponseError):
        prices.fetch_yahoo("META", years=6, now=NOW)


@pytest.mark.unit
def test_ticker_is_sanitized_before_reaching_the_url():
    with pytest.raises(ValueError):
        prices.fetch_yahoo("../etc", years=6, now=NOW)
