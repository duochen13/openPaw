"""Append-only point-in-time fact store (spec §5).

Design rules enforced here:
  - Four timestamps on every fact: event_time, observed_at, known_at, valid_from.
  - Append-only. No UPDATE, ever. A restatement is a new row with a later
    known_at and the same event_time, which is what makes "do not backfill
    revisions into past predictions" automatic.
  - observed_at is part of every primary key, so a re-observation appends
    instead of colliding.
  - A NULL known_at means invisible. See PointInTimeView in Task 5.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

#: The canonical shape produced by timestamps.to_iso: fixed-width UTC with
#: microseconds. Enforced at the database boundary so that lexicographic
#: comparison always equals chronological comparison - making that a property
#: of the COLUMN, not merely of whoever happened to write the row. Without it,
#: one hand-built string entering by another route (a fixture, a migration, a
#: notebook INSERT) silently breaks ordering with no error anywhere.
_CANONICAL_TS = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
    "[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00"
)


def _ts_check(column: str) -> str:
    """A CHECK clause pinning `column` to the canonical timestamp shape."""
    return f"CHECK ({column} IS NULL OR {column} GLOB '{_CANONICAL_TS}')"


_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS price_bar (
    ticker       TEXT NOT NULL,
    session_date TEXT NOT NULL,
    event_time   TEXT NOT NULL {_ts_check('event_time')},
    observed_at  TEXT NOT NULL {_ts_check('observed_at')},
    known_at     TEXT          {_ts_check('known_at')},
    open         REAL NOT NULL,
    high         REAL NOT NULL,
    low          REAL NOT NULL,
    close        REAL NOT NULL,
    volume       REAL NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (ticker, session_date, observed_at)
);

CREATE TABLE IF NOT EXISTS corporate_action (
    ticker         TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    action_type    TEXT NOT NULL CHECK (action_type IN ('split', 'dividend')),
    ratio          REAL,
    amount         REAL,
    event_time     TEXT NOT NULL {_ts_check('event_time')},
    observed_at    TEXT NOT NULL {_ts_check('observed_at')},
    known_at       TEXT          {_ts_check('known_at')},
    source         TEXT NOT NULL,
    PRIMARY KEY (ticker, effective_date, action_type, observed_at)
);

CREATE TABLE IF NOT EXISTS fundamental_fact (
    ticker        TEXT NOT NULL,
    concept       TEXT NOT NULL,
    unit          TEXT NOT NULL,
    fiscal_period TEXT NOT NULL,
    value         REAL NOT NULL,
    accession     TEXT NOT NULL,
    event_time    TEXT NOT NULL {_ts_check('event_time')},
    observed_at   TEXT NOT NULL {_ts_check('observed_at')},
    known_at      TEXT          {_ts_check('known_at')},
    valid_from    TEXT,
    source        TEXT NOT NULL,
    PRIMARY KEY (ticker, concept, fiscal_period, accession)
);

CREATE INDEX IF NOT EXISTS ix_price_known  ON price_bar (ticker, known_at);
CREATE INDEX IF NOT EXISTS ix_action_known ON corporate_action (ticker, known_at);
CREATE INDEX IF NOT EXISTS ix_fact_known   ON fundamental_fact (ticker, known_at);
"""


class Store:
    """Owns the connection. Callers wanting to read facts use `as_of`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: str | Path) -> Store:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        conn.commit()
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def insert_price_bar(self, **row: object) -> None:
        self._insert("price_bar", row)

    def insert_corporate_action(self, **row: object) -> None:
        self._insert("corporate_action", row)

    def insert_fundamental_fact(self, **row: object) -> None:
        self._insert("fundamental_fact", row)

    def _insert(self, table: str, row: dict[str, object]) -> None:
        cols = ", ".join(row)
        marks = ", ".join(f":{c}" for c in row)
        self._conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", row)
        self._conn.commit()
