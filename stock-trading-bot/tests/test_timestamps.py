from datetime import UTC, datetime, timedelta, timezone

import pytest

from stock_trading_bot.timestamps import known_at_for, parse_iso, to_iso

UTC = UTC


@pytest.mark.unit
def test_known_at_adds_the_source_latency_budget():
    observed = datetime(2026, 9, 7, 20, 0, 0, tzinfo=UTC)
    assert known_at_for(observed, "stooq", {"stooq": 900}) == datetime(
        2026, 9, 7, 20, 15, 0, tzinfo=UTC
    )


@pytest.mark.unit
def test_unknown_source_is_an_error_not_a_zero_default():
    """A missing budget must not silently mean 'instantly available'."""
    observed = datetime(2026, 9, 7, 20, 0, 0, tzinfo=UTC)
    with pytest.raises(KeyError):
        known_at_for(observed, "mystery_vendor", {"stooq": 900})


@pytest.mark.unit
def test_negative_budget_is_rejected():
    """A sign typo in config would make known_at precede observed_at."""
    observed = datetime(2026, 9, 7, 20, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="negative latency budget"):
        known_at_for(observed, "stooq", {"stooq": -900})


@pytest.mark.unit
def test_zero_budget_is_allowed():
    """Zero is suspicious but legitimate; only a negative value is incoherent."""
    observed = datetime(2026, 9, 7, 20, 0, 0, tzinfo=UTC)
    assert known_at_for(observed, "x", {"x": 0}) == observed


@pytest.mark.unit
def test_naive_observed_at_is_rejected():
    with pytest.raises(ValueError):
        known_at_for(datetime(2026, 9, 7, 20, 0, 0), "stooq", {"stooq": 900})


@pytest.mark.unit
def test_to_iso_rejects_a_naive_datetime():
    with pytest.raises(ValueError):
        to_iso(datetime(2026, 9, 7, 20, 0, 0))


@pytest.mark.unit
def test_parse_iso_rejects_a_naive_string():
    """fromisoformat accepts it and astimezone would assume system local time,
    making the stored instant depend on which machine read it."""
    with pytest.raises(ValueError, match="naive timestamp"):
        parse_iso("2026-09-07T20:15:00")


@pytest.mark.unit
def test_parse_iso_rejects_a_date_only_string():
    with pytest.raises(ValueError, match="naive timestamp"):
        parse_iso("2026-09-07")


@pytest.mark.unit
def test_parse_iso_accepts_a_non_utc_offset_and_normalizes_it():
    assert parse_iso("2026-09-07T13:15:00-07:00") == datetime(
        2026, 9, 7, 20, 15, 0, tzinfo=UTC
    )


@pytest.mark.unit
@pytest.mark.parametrize("dt", [
    datetime(2026, 9, 7, 20, 15, 0, tzinfo=UTC),
    datetime(2026, 9, 7, 20, 15, 0, 999999, tzinfo=UTC),
    datetime(2026, 9, 7, 13, 15, 0, 1, tzinfo=timezone(timedelta(hours=-7))),
    datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=9))),
])
def test_iso_round_trip_is_lossless(dt):
    """Truncating to seconds would round known_at earlier - the leak direction."""
    assert parse_iso(to_iso(dt)) == dt


@pytest.mark.unit
def test_to_iso_output_is_fixed_width():
    """Fixed width is what makes lexicographic order safe without reasoning
    about how '+' and '.' compare."""
    widths = {
        len(to_iso(datetime(2026, 9, 7, 20, 15, 0, us, tzinfo=UTC)))
        for us in (0, 1, 999999)
    }
    assert len(widths) == 1


@pytest.mark.unit
def test_iso_strings_sort_in_chronological_order():
    """The store compares known_at as text, so string order must equal instant
    order. This is the property the whole point-in-time gateway rests on."""
    offsets = (-720, -420, 0, 330, 540)
    moments = [
        datetime(year, month, 7, hour, 15, 0, micro,
                 tzinfo=timezone(timedelta(minutes=off)))
        for year in (2025, 2026)
        for month in (1, 9, 12)
        for hour in (0, 13, 23)
        for micro in (0, 1, 999999)
        for off in offsets
    ]
    assert [to_iso(d) for d in sorted(moments)] == sorted(to_iso(d) for d in moments)
