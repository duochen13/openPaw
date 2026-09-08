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


def _action(store, effective_date, known_at, ratio=2.0):
    store.insert_corporate_action(
        ticker="NVDA",
        effective_date=effective_date,
        action_type="split",
        ratio=ratio,
        amount=None,
        event_time=f"{effective_date}T13:30:00.000000+00:00",
        observed_at=f"{effective_date}T14:00:00.000000+00:00",
        known_at=known_at,
        source="stooq",
    )


def _fact(store, fiscal_period, accession, known_at, concept="Revenues", value=1.0):
    store.insert_fundamental_fact(
        ticker="NVDA",
        concept=concept,
        unit="USD",
        fiscal_period=fiscal_period,
        value=value,
        accession=accession,
        event_time="2026-09-01T00:00:00.000000+00:00",
        observed_at="2026-09-01T00:05:00.000000+00:00",
        known_at=known_at,
        valid_from="2026-09-01T00:00:00.000000+00:00",
        source="edgar",
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
def test_writes_after_a_view_was_taken_are_visible_to_a_later_view(store):
    """The read-only connection is cached, so it must still see new commits."""
    view_before = store.as_of(T)
    assert view_before.price_bars("NVDA") == []
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_as_of_after_close_raises(store):
    """close() must not leave as_of silently opening a fresh connection on a
    closed store."""
    store.close()
    with pytest.raises(ValueError, match="closed"):
        store.as_of(T)


# --- corporate_actions and fundamental_facts get the same visible / future /
# null-vintage coverage price_bars already had (I3): they were previously
# untested even though fundamental_facts in particular builds its SQL with a
# conditional f-string and carries the most risk.

@pytest.mark.unit
def test_corporate_actions_visible_future_and_null_vintage(store):
    _action(store, "2026-09-01", "2026-09-01T14:15:00.000000+00:00")             # visible
    _action(store, "2026-09-08", "2026-09-08T14:15:00.000000+00:00", ratio=3.0)  # future
    _action(store, "2026-09-02", None, ratio=4.0)                                # null vintage
    actions = store.as_of(T).corporate_actions("NVDA")
    assert len(actions) == 1
    assert actions[0]["effective_date"] == "2026-09-01"


@pytest.mark.unit
def test_fundamental_facts_visible_future_and_null_vintage(store):
    _fact(store, "2026Q1", "acc-1", "2026-09-01T00:10:00.000000+00:00")  # visible
    _fact(store, "2026Q2", "acc-2", "2026-09-08T00:10:00.000000+00:00")  # future
    _fact(store, "2026Q3", "acc-3", None)                                # null vintage
    facts = store.as_of(T).fundamental_facts("NVDA")
    assert len(facts) == 1
    assert facts[0]["fiscal_period"] == "2026Q1"


@pytest.mark.unit
def test_fundamental_facts_concept_filter(store):
    _fact(store, "2026Q1", "acc-rev", "2026-09-01T00:10:00.000000+00:00", concept="Revenues")
    _fact(store, "2026Q1", "acc-eps", "2026-09-01T00:10:00.000000+00:00", concept="EPS")
    facts = store.as_of(T).fundamental_facts("NVDA", concept="Revenues")
    assert [f["concept"] for f in facts] == ["Revenues"]


# --- mutation and pragma-toggle attacks now go through Store, not the view:
# Store is the privileged object that legitimately holds a raw connection;
# PointInTimeView no longer exposes one (C1/C2).

@pytest.mark.unit
def test_read_only_survives_turning_the_pragma_back_off(store):
    """`mode=ro` is an open flag, not a setting. Turning `PRAGMA query_only`
    back off on the connection must not re-enable writes."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    ro = store._readonly_conn()
    ro.execute("PRAGMA query_only = OFF")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("DELETE FROM price_bar")
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_the_view_cannot_mutate_the_store(store):
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    view = store.as_of(T)
    for statement in ("DELETE FROM price_bar", "UPDATE price_bar SET close = 0",
                      "DROP TABLE price_bar"):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            view._rows("price_bar", statement, {})
    assert len(store.as_of(T).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_attach_cannot_reopen_the_store_read_write(store):
    """`ATTACH` re-opens the same file read-write regardless of `mode=ro` on
    `main`; the attached-database limit closes that path."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    ro = store._readonly_conn()
    ro.execute("PRAGMA query_only = OFF")
    with pytest.raises(sqlite3.OperationalError):
        ro.execute(f"ATTACH DATABASE '{store._path}' AS w")
    assert len(store.as_of(T).price_bars("NVDA")) == 1


# --- the column-shape check on _rows (C2): an accessor missing the predicate
# still cannot leak, and the various ways a projection can shadow known_at
# are refused loudly rather than silently trusted.

@pytest.mark.unit
def test_an_accessor_shaped_query_missing_the_predicate_still_filters(store):
    """The predicate lives in `_rows`, not only in an accessor's SQL: a query
    that forgets the WHERE clause is still safe because every row is
    re-checked against known_at before being returned."""
    _bar(store, "2026-09-08", "2026-09-08T20:20:00.000000+00:00")  # future
    view = store.as_of(T)
    rows = view._rows(
        "price_bar",
        "SELECT ticker, session_date, event_time, observed_at, known_at, "
        "open, high, low, close, volume, source FROM price_bar",
        {},
    )
    assert rows == []


@pytest.mark.unit
def test_a_coalesced_known_at_is_refused(store):
    """COALESCE-ing a NULL vintage to an old date is a plausible thing to
    write and would otherwise defeat fail-closed; the column-shape check
    catches it because the projection no longer matches the table's full
    column set."""
    _bar(store, "2026-09-01", None)
    view = store.as_of(T)
    with pytest.raises(ValueError, match="known_at"):
        view._rows(
            "price_bar",
            "SELECT close, COALESCE(known_at, '1970-01-01T00:00:00.000000+00:00') "
            "AS known_at FROM price_bar",
            {},
        )


@pytest.mark.unit
def test_a_query_that_omits_known_at_is_refused(store):
    """Fail loudly on misuse rather than silently returning unfiltered rows."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    view = store.as_of(T)
    with pytest.raises(ValueError, match="known_at"):
        view._rows("price_bar", "SELECT ticker FROM price_bar", {})


@pytest.mark.unit
def test_a_reordered_projection_is_refused(store):
    """Same columns, wrong order: the column check is positional, so a
    projection cannot smuggle a shadowed known_at into a spot the caller
    expects a different column to occupy."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    view = store.as_of(T)
    with pytest.raises(ValueError, match="known_at"):
        view._rows(
            "price_bar",
            "SELECT known_at, ticker, session_date, event_time, observed_at, "
            "open, high, low, close, volume, source FROM price_bar",
            {},
        )


@pytest.mark.unit
def test_a_non_text_known_at_raises_rather_than_vanishing_silently(store):
    """I4: a non-string known_at must raise, not silently drop the row. The
    schema CHECK now refuses to store a blob, so this is exercised by
    mangling the type on the way out instead of storing one."""
    _bar(store, "2026-09-01", "2026-09-01T20:20:00.000000+00:00")
    view = store.as_of(T)
    with pytest.raises(TypeError, match="known_at"):
        view._rows(
            "price_bar",
            "SELECT ticker, session_date, event_time, observed_at, "
            "CAST(known_at AS BLOB) AS known_at, open, high, low, close, "
            "volume, source FROM price_bar",
            {},
        )
