import pytest

from portfolio_analysis.calendar import TradingCalendar

# Thu Fri Mon Tue Wed Thu Fri Mon - a real run with the weekend gap.
SESSIONS = [
    "2024-04-18",
    "2024-04-19",
    "2024-04-22",
    "2024-04-23",
    "2024-04-24",
    "2024-04-25",
    "2024-04-26",
    "2024-04-29",
]


@pytest.fixture
def cal():
    return TradingCalendar(SESSIONS)


@pytest.mark.unit
def test_window_spans_two_sessions_back_and_one_forward(cal):
    assert cal.window("2024-04-25", before=2, after=1) == ("2024-04-23", "2024-04-26")


@pytest.mark.unit
def test_window_skips_the_weekend_rather_than_counting_calendar_days(cal):
    """2024-04-22 is a Monday. Two sessions back is the prior Thursday, four
    calendar days earlier - a calendar window would land on the Saturday."""
    assert cal.window("2024-04-22", before=2, after=1) == ("2024-04-18", "2024-04-23")


@pytest.mark.unit
def test_window_clamps_at_the_start_of_the_calendar(cal):
    assert cal.window("2024-04-18", before=2, after=1) == ("2024-04-18", "2024-04-19")


@pytest.mark.unit
def test_window_clamps_at_the_end_of_the_calendar(cal):
    assert cal.window("2024-04-29", before=2, after=1) == ("2024-04-25", "2024-04-29")


@pytest.mark.unit
def test_sessions_in_returns_the_inclusive_session_list(cal):
    assert cal.sessions_in("2024-04-23", "2024-04-26") == [
        "2024-04-23",
        "2024-04-24",
        "2024-04-25",
        "2024-04-26",
    ]


@pytest.mark.unit
def test_a_date_that_is_not_a_session_raises(cal):
    """A move date always IS a session. Asking about a non-session means the
    caller mixed up its calendars - worth an error, not a guess."""
    with pytest.raises(KeyError, match="not a trading session"):
        cal.window("2024-04-20", before=2, after=1)


@pytest.mark.unit
def test_an_empty_calendar_raises_at_construction():
    with pytest.raises(ValueError, match="at least one session"):
        TradingCalendar([])


@pytest.mark.unit
def test_the_calendar_sorts_and_deduplicates_its_input():
    cal = TradingCalendar(["2024-04-25", "2024-04-23", "2024-04-25"])
    assert cal.sessions_in("2024-04-23", "2024-04-25") == ["2024-04-23", "2024-04-25"]


def test_holiday_boundary_uses_observed_sessions():
    cal = TradingCalendar(["2024-03-27", "2024-03-28", "2024-04-01", "2024-04-02"])
    assert cal.window("2024-04-01", before=2, after=1) == ("2024-03-27", "2024-04-02")


def test_negative_window_rejected(cal):
    with pytest.raises(ValueError):
        cal.window("2024-04-25", before=-1, after=1)
