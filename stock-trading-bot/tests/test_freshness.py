import pytest

from stock_trading_bot.ingest.freshness import StaleDataError, assert_fresh


@pytest.mark.unit
def test_a_current_last_bar_passes():
    assert_fresh([{"session_date": "2026-09-04"}], expected_session="2026-09-04")


@pytest.mark.unit
def test_a_stale_last_bar_raises_rather_than_modelling_on_it():
    with pytest.raises(StaleDataError, match="2026-08-14"):
        assert_fresh([{"session_date": "2026-08-14"}], expected_session="2026-09-04")


@pytest.mark.unit
def test_empty_bars_raise():
    with pytest.raises(StaleDataError, match="no bars"):
        assert_fresh([], expected_session="2026-09-04")


@pytest.mark.unit
def test_a_bar_ahead_of_the_expected_session_raises():
    """A bar from the future means a bad vendor payload, not good news."""
    with pytest.raises(StaleDataError):
        assert_fresh([{"session_date": "2026-09-09"}], expected_session="2026-09-04")


@pytest.mark.unit
@pytest.mark.parametrize("bad", [None, 20260904, ["2026-09-04"], object()])
def test_a_non_text_session_date_is_refused(bad):
    """Bad price data must fail loudly, not compare wrongly."""
    with pytest.raises(StaleDataError, match="non-text session_date"):
        assert_fresh([{"session_date": bad}], expected_session="2026-09-04")


@pytest.mark.unit
def test_a_missing_session_date_key_is_refused():
    with pytest.raises(StaleDataError, match="non-text session_date"):
        assert_fresh([{"close": 1.0}], expected_session="2026-09-04")


@pytest.mark.unit
def test_the_newest_bar_decides_not_the_last_one():
    """Vendors do not always return rows in chronological order."""
    bars = [{"session_date": d} for d in ("2026-09-04", "2026-09-02", "2026-09-03")]
    assert_fresh(bars, expected_session="2026-09-04")
