import sqlite3
from datetime import UTC, datetime

import pytest

from stock_trading_bot.store import Store

T = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)


def _bar(store, session_date, known_at, close=100.0):
    store.insert_price_bar(
        ticker="NVDA",
        session_date=session_date,
        event_time=f"{session_date}T20:00:00.000000+00:00",
        observed_at=f"{session_date}T20:05:00.000000+00:00",
        known_at=known_at,
        open=99.0, high=101.0, low=98.0, close=close, volume=1000.0,
        source="stooq",
    )


@pytest.fixture
def store(tmp_path):
    return Store.open(tmp_path / "panel.sqlite")


@pytest.mark.unit
def test_view_returns_rows_known_before_t(store):
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_view_refuses_a_row_known_after_t(store):
    """The single most important test in the codebase."""
    _bar(store, "2026-09-08", "2026-09-08T20:20:00.000000+00:00")
    assert store.as_of(T).price_bars("NVDA") == []


@pytest.mark.unit
def test_null_known_at_is_invisible_not_visible(store):
    """Unknown vintage fails closed (spec §5.1)."""
    _bar(store, "2026-09-01", None)
    assert store.as_of(T).price_bars("NVDA") == []


@pytest.mark.unit
def test_boundary_is_inclusive(store):
    _bar(store, "2026-09-07", "2026-09-07T12:00:00.000000+00:00")
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_latest_observation_wins_for_a_restated_session(store):
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00", close=100.0)
    store.insert_price_bar(
        ticker="NVDA", session_date="2026-09-01",
        event_time="2026-09-01T20:00:00.000000+00:00",
        observed_at="2026-09-02T09:00:00.000000+00:00",
        known_at="2026-09-02T09:15:00.000000+00:00",
        open=99.0, high=101.0, low=98.0, close=100.5, volume=1000.0,
        source="stooq",
    )
    bars = store.as_of(T).price_bars("NVDA")
    assert len(bars) == 1
    assert bars[0]["close"] == 100.5


@pytest.mark.unit
def test_restatement_is_invisible_before_it_was_known(store):
    """As-of 2026-09-01T21:00 we must still see the original value."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00", close=100.0)
    store.insert_price_bar(
        ticker="NVDA", session_date="2026-09-01",
        event_time="2026-09-01T20:00:00.000000+00:00",
        observed_at="2026-09-02T09:00:00.000000+00:00",
        known_at="2026-09-02T09:15:00.000000+00:00",
        open=99.0, high=101.0, low=98.0, close=100.5, volume=1000.0,
        source="stooq",
    )
    early = datetime(2026, 9, 1, 21, 0, 0, tzinfo=UTC)
    bars = store.as_of(early).price_bars("NVDA")
    assert len(bars) == 1
    assert bars[0]["close"] == 100.0


@pytest.mark.unit
def test_as_of_rejects_a_naive_datetime(store):
    with pytest.raises(ValueError):
        store.as_of(datetime(2026, 9, 7, 12, 0, 0))


@pytest.mark.unit
def test_a_hand_written_query_missing_the_predicate_still_cannot_leak(store):
    """The guarantee must belong to the view, not to each accessor's SQL."""
    _bar(store, "2026-09-08", "2026-09-08T20:20:00.000000+00:00")
    view = store.as_of(T)
    rows = view._query("SELECT * FROM price_bar WHERE ticker = :ticker", {"ticker": "NVDA"})
    assert rows == []


@pytest.mark.unit
def test_the_view_cannot_mutate_the_store(store):
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    view = store.as_of(T)
    for statement in ("DELETE FROM price_bar", "UPDATE price_bar SET close = 0",
                      "DROP TABLE price_bar"):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            view._query(statement, {})
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_a_query_that_omits_known_at_is_refused(store):
    """Fail loudly on misuse rather than silently returning unfiltered rows."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    with pytest.raises(ValueError, match="known_at"):
        store.as_of(T)._query("SELECT ticker FROM price_bar", {})


@pytest.mark.unit
def test_writes_after_a_view_was_taken_are_visible_to_a_later_view(store):
    """The read-only connection is cached, so it must still see new commits."""
    view_before = store.as_of(T)
    assert view_before.price_bars("NVDA") == []
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_read_only_survives_turning_the_pragma_back_off(store):
    """`mode=ro` is an open flag, not a setting. A caller holding _conn must
    not be able to re-enable writes by toggling PRAGMA query_only."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    view = store.as_of(T)
    view._conn.execute("PRAGMA query_only = OFF")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        view._conn.execute("DELETE FROM price_bar")
    assert len(store.as_of(T).price_bars("NVDA")) == 1
