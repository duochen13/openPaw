from datetime import UTC, datetime

import pytest

from stock_trading_bot.ingest.corporate_actions import (
    adjusted_close_as_of,
    split_factor_as_of,
)
from stock_trading_bot.store import Store

NOW = datetime(2026, 9, 7, tzinfo=UTC)


def _split(store, effective_date, ratio, known_at):
    store.insert_corporate_action(
        ticker="NOW",
        effective_date=effective_date,
        action_type="split",
        ratio=ratio,
        amount=None,
        event_time=f"{effective_date}T13:30:00.000000+00:00",
        observed_at=f"{effective_date}T14:00:00.000000+00:00",
        known_at=known_at,
        source="stooq",
    )


@pytest.fixture
def store(tmp_path):
    return Store.open(tmp_path / "panel.sqlite")


@pytest.mark.unit
def test_no_splits_means_a_factor_of_one(store):
    assert split_factor_as_of(store.as_of(NOW), "NOW", "2025-06-01") == 1.0


@pytest.mark.unit
def test_a_later_split_divides_earlier_prices(store):
    """A 5-for-1 split on 2025-12-17 makes a 2025-06-01 raw price 5x too high."""
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    assert split_factor_as_of(store.as_of(NOW), "NOW", "2025-06-01") == 5.0


@pytest.mark.unit
def test_a_split_does_not_affect_sessions_after_it(store):
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    assert split_factor_as_of(store.as_of(NOW), "NOW", "2026-01-05") == 1.0


@pytest.mark.unit
def test_a_split_does_not_affect_its_own_effective_session(store):
    """Prices on and after the effective date are already post-split."""
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    assert split_factor_as_of(store.as_of(NOW), "NOW", "2025-12-17") == 1.0


@pytest.mark.unit
def test_the_factor_is_as_of_t_not_as_of_today(store):
    """The critical case. Standing at 2025-06-02 the December split has not
    happened and must not be applied. This is exactly what consuming a vendor's
    adjusted close series gets wrong."""
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    early = datetime(2025, 6, 2, tzinfo=UTC)
    assert split_factor_as_of(store.as_of(early), "NOW", "2025-06-01") == 1.0


@pytest.mark.unit
def test_multiple_splits_compound(store):
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    _split(store, "2026-06-01", 2.0, "2026-06-01T14:15:00.000000+00:00")
    assert split_factor_as_of(store.as_of(NOW), "NOW", "2025-01-01") == 10.0


@pytest.mark.unit
def test_only_the_splits_visible_at_t_compound(store):
    """Standing between the two splits, only the first one applies."""
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    _split(store, "2026-06-01", 2.0, "2026-06-01T14:15:00.000000+00:00")
    between = datetime(2026, 2, 1, tzinfo=UTC)
    assert split_factor_as_of(store.as_of(between), "NOW", "2025-01-01") == 5.0


@pytest.mark.unit
def test_a_dividend_is_not_treated_as_a_split(store):
    store.insert_corporate_action(
        ticker="NOW", effective_date="2025-12-17", action_type="dividend",
        ratio=None, amount=0.25,
        event_time="2025-12-17T13:30:00.000000+00:00",
        observed_at="2025-12-17T14:00:00.000000+00:00",
        known_at="2025-12-17T14:15:00.000000+00:00",
        source="stooq",
    )
    assert split_factor_as_of(store.as_of(NOW), "NOW", "2025-06-01") == 1.0


@pytest.mark.unit
@pytest.mark.parametrize("bad_ratio", [0.0, -5.0, None])
def test_an_unusable_split_ratio_raises_rather_than_being_skipped(store, bad_ratio):
    """Skipping it would silently mis-price every earlier session."""
    _split(store, "2025-12-17", bad_ratio, "2025-12-17T14:15:00.000000+00:00")
    with pytest.raises(ValueError, match="unusable"):
        split_factor_as_of(store.as_of(NOW), "NOW", "2025-06-01")


@pytest.mark.unit
def test_adjusted_close_divides_by_the_visible_factor(store):
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    bar = {"session_date": "2025-06-01", "close": 500.0}
    assert adjusted_close_as_of(store.as_of(NOW), "NOW", bar) == 100.0
    early = store.as_of(datetime(2025, 6, 2, tzinfo=UTC))
    assert adjusted_close_as_of(early, "NOW", bar) == 500.0
