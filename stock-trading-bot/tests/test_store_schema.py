import sqlite3

import pytest

from stock_trading_bot.store import Store


@pytest.mark.unit
def test_open_creates_the_expected_tables(tmp_path):
    store = Store.open(tmp_path / "panel.sqlite")
    names = {
        row[0]
        for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"price_bar", "corporate_action", "fundamental_fact"} <= names


@pytest.mark.unit
def test_open_is_idempotent(tmp_path):
    path = tmp_path / "panel.sqlite"
    Store.open(path).close()
    Store.open(path).close()  # must not raise


@pytest.mark.unit
def test_price_bar_rejects_a_duplicate_observation(tmp_path):
    store = Store.open(tmp_path / "panel.sqlite")
    row = dict(
        ticker="NVDA",
        session_date="2026-09-04",
        event_time="2026-09-04T20:00:00.000000+00:00",
        observed_at="2026-09-04T20:05:00.000000+00:00",
        known_at="2026-09-04T20:20:00.000000+00:00",
        open=100.0, high=105.0, low=99.0, close=104.0, volume=1000.0,
        source="stooq",
    )
    store.insert_price_bar(**row)
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_price_bar(**row)


@pytest.mark.unit
@pytest.mark.parametrize("bad_ts", [
    "2026-09-04T20:20:00+00:00",           # seconds only, no microseconds
    "2026-09-04T13:20:00.000000-07:00",    # correct instant, non-UTC offset
    "2026-09-04T20:20:00.000000Z",         # Z instead of +00:00
    "2026-09-04",                          # date only
])
def test_a_noncanonical_timestamp_is_rejected_by_the_database(tmp_path, bad_ts):
    """Lexicographic ordering must be a property of the column, not of the
    writer. A non-canonical string is the same instant but sorts differently."""
    store = Store.open(tmp_path / "panel.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_price_bar(
            ticker="NVDA", session_date="2026-09-04",
            event_time="2026-09-04T20:00:00.000000+00:00",
            observed_at="2026-09-04T20:05:00.000000+00:00",
            known_at=bad_ts,
            open=100.0, high=105.0, low=99.0, close=104.0, volume=1000.0,
            source="stooq",
        )


@pytest.mark.unit
def test_a_restatement_appends_rather_than_overwriting(tmp_path):
    """Append-only: a corrected value is a new row with a later known_at."""
    store = Store.open(tmp_path / "panel.sqlite")
    common = dict(
        ticker="NVDA", session_date="2026-09-04",
        event_time="2026-09-04T20:00:00.000000+00:00",
        open=100.0, high=105.0, low=99.0, close=104.0, volume=1000.0,
        source="stooq",
    )
    store.insert_price_bar(
        observed_at="2026-09-04T20:05:00.000000+00:00",
        known_at="2026-09-04T20:20:00.000000+00:00", **common
    )
    store.insert_price_bar(
        observed_at="2026-09-05T09:00:00.000000+00:00",
        known_at="2026-09-05T09:15:00.000000+00:00", **{**common, "close": 104.5}
    )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM price_bar WHERE ticker='NVDA'"
    ).fetchone()[0]
    assert count == 2


@pytest.mark.unit
def test_a_fundamental_fact_reobservation_appends_rather_than_colliding(tmp_path):
    """observed_at is part of the primary key so re-fetching a filing you
    already have appends instead of raising IntegrityError - the same
    restatement mechanism price_bar relies on must work here too."""
    store = Store.open(tmp_path / "panel.sqlite")
    common = dict(
        ticker="NOW", concept="Revenues", unit="USD", fiscal_period="2026Q1",
        value=3_700_000_000.0, accession="0001373715-26-000045",
        event_time="2026-04-23T00:00:00.000000+00:00",
        valid_from="2026-04-23T00:00:00.000000+00:00",
        source="edgar",
    )
    store.insert_fundamental_fact(
        observed_at="2026-09-07T12:00:00.000000+00:00",
        known_at="2026-09-07T12:30:00.000000+00:00", **common
    )
    store.insert_fundamental_fact(
        observed_at="2026-09-08T09:00:00.000000+00:00",
        known_at="2026-09-08T09:30:00.000000+00:00", **common
    )
    count = store._conn.execute(
        "SELECT COUNT(*) FROM fundamental_fact WHERE ticker='NOW'"
    ).fetchone()[0]
    assert count == 2
