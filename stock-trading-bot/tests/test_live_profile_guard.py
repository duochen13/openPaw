from datetime import date

import pytest

from stock_trading_bot.ingest.live_profile_guard import (
    LIVE_ONLY_FIELDS,
    withhold_live_profile,
)

PROFILE = {
    "longName": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "marketCap": 3_500_000_000_000,
    "trailingPE": 34.2,
    "fiftyTwoWeekHigh": 260.1,
    "totalRevenue": 391_000_000_000,
}
TODAY = date(2026, 9, 7)


@pytest.mark.unit
def test_a_historical_run_receives_nothing():
    assert withhold_live_profile(PROFILE, date(2024, 5, 10), TODAY) == {}


@pytest.mark.unit
def test_a_current_run_is_unchanged():
    assert withhold_live_profile(PROFILE, TODAY, TODAY) == PROFILE


@pytest.mark.unit
@pytest.mark.parametrize("leaky", [
    "3500000000000", "34.2", "260.1", "391000000000",
    "NVIDIA Corporation", "Technology", "Semiconductors",
])
def test_no_present_day_value_survives_a_historical_run(leaky):
    survived = str(withhold_live_profile(PROFILE, date(2024, 5, 10), TODAY))
    assert leaky not in survived


@pytest.mark.unit
def test_identity_fields_are_withheld_too():
    """Name, sector and industry shift on rename or reclassification, so they
    are not stable identity - they are present-day values without a vintage."""
    assert {"longName", "sector", "industry"} <= LIVE_ONLY_FIELDS
