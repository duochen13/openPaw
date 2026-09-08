from datetime import UTC, datetime
from unittest import mock

import pytest

from stock_trading_bot.ingest import prices

CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-09-03,100.0,102.0,99.5,101.0,1000000\n"
    "2026-09-04,101.0,105.0,100.5,104.0,1200000\n"
)
OBSERVED = datetime(2026, 9, 4, 21, 0, 0, tzinfo=UTC)
BUDGET = {"stooq": 900}


def _fetch(text=CSV):
    return mock.patch.object(prices, "_http_get", return_value=text)


@pytest.mark.unit
def test_parses_bars_into_the_four_timestamp_shape():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert len(bars) == 2
    first = bars[0]
    assert first["ticker"] == "NVDA"
    assert first["session_date"] == "2026-09-03"
    assert first["close"] == 101.0
    assert first["source"] == "stooq"


@pytest.mark.unit
def test_known_at_is_observed_at_plus_the_budget():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert bars[0]["known_at"] == "2026-09-04T21:15:00.000000+00:00"


@pytest.mark.unit
def test_event_time_is_the_session_close_not_the_fetch_time():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert bars[0]["event_time"] == "2026-09-03T20:00:00.000000+00:00"


@pytest.mark.unit
def test_ticker_is_sanitized_before_reaching_the_url():
    with pytest.raises(ValueError):
        prices.fetch_stooq("../etc", observed_at=OBSERVED, latency_budget=BUDGET)


@pytest.mark.unit
def test_no_rows_returns_empty_rather_than_raising():
    with _fetch("Date,Open,High,Low,Close,Volume\n"):
        assert prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET) == []


@pytest.mark.unit
def test_adapter_never_returns_a_live_profile_field():
    """Enforces the §5.5 guard at the adapter boundary."""
    from stock_trading_bot.ingest.live_profile_guard import LIVE_ONLY_FIELDS

    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert set(bars[0]) & LIVE_ONLY_FIELDS == set()
