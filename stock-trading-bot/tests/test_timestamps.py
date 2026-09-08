from datetime import datetime, timezone

import pytest

from stock_trading_bot.timestamps import known_at_for, parse_iso, to_iso


@pytest.mark.unit
def test_known_at_adds_the_source_latency_budget():
    observed = datetime(2026, 9, 7, 20, 0, 0, tzinfo=timezone.utc)
    budget = {"stooq": 900}
    assert known_at_for(observed, "stooq", budget) == datetime(
        2026, 9, 7, 20, 15, 0, tzinfo=timezone.utc
    )


@pytest.mark.unit
def test_unknown_source_is_an_error_not_a_zero_default():
    """A missing budget must not silently mean 'instantly available'."""
    observed = datetime(2026, 9, 7, 20, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(KeyError):
        known_at_for(observed, "mystery_vendor", {"stooq": 900})


@pytest.mark.unit
def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        known_at_for(datetime(2026, 9, 7, 20, 0, 0), "stooq", {"stooq": 900})


@pytest.mark.unit
def test_iso_round_trip_preserves_utc():
    dt = datetime(2026, 9, 7, 20, 15, 0, tzinfo=timezone.utc)
    assert parse_iso(to_iso(dt)) == dt
