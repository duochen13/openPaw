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
from datetime import datetime
from pathlib import Path

from stock_trading_bot.timestamps import to_iso

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

    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self._path = path
        self._ro_conn: sqlite3.Connection | None = None

    @classmethod
    def open(cls, path: str | Path) -> Store:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        conn.commit()
        return cls(conn, path)

    def _readonly_conn(self) -> sqlite3.Connection:
        """A second connection that SQLite itself refuses to write through."""
        if self._ro_conn is None:
            ro = sqlite3.connect(self._path)
            ro.row_factory = sqlite3.Row
            ro.execute("PRAGMA query_only = ON")
            self._ro_conn = ro
        return self._ro_conn

    def close(self) -> None:
        if self._ro_conn is not None:
            self._ro_conn.close()
            self._ro_conn = None
        self._conn.close()

    def as_of(self, t: datetime) -> PointInTimeView:
        """The only supported way to read facts.

        Anything reachable through the returned view was knowable at `t`.
        """
        if t.tzinfo is None:
            raise ValueError("as_of requires a timezone-aware datetime")
        return PointInTimeView(self._readonly_conn(), to_iso(t))

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


class PointInTimeView:
    """A read-only window on the store as it was visible at `t`.

    Two independent mechanisms, because the first one alone proved to be a
    convention rather than a guarantee:

      1. The connection is opened with `PRAGMA query_only = ON`, so the view
         cannot mutate the append-only store even through a hand-written query.
      2. Every row is re-checked here before it is returned. An accessor whose
         SQL forgets the predicate still cannot emit a future-dated row, and a
         row whose `known_at` is NULL is dropped.

    An earlier version stored a generic query callable and relied on each
    accessor's SQL to carry the predicate. That made the guarantee a property
    of every call site rather than of the view, which is exactly the failure
    this class exists to prevent.
    """

    __slots__ = ("_conn", "_t")

    def __init__(self, conn: sqlite3.Connection, t: str) -> None:
        self._conn = conn
        self._t = t

    @property
    def t(self) -> str:
        return self._t

    def _query(self, sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        rows = [dict(r) for r in self._conn.execute(sql, {**params, "t": self._t})]
        visible: list[dict[str, object]] = []
        for row in rows:
            if "known_at" not in row:
                raise ValueError(
                    "a point-in-time view may only return rows carrying known_at; "
                    "got columns: " + ", ".join(sorted(row))
                )
            known_at = row["known_at"]
            if isinstance(known_at, str) and known_at <= self._t:
                visible.append(row)
        return visible

    def price_bars(self, ticker: str) -> list[dict[str, object]]:
        """Visible bars, one row per session, latest visible observation wins."""
        return self._query(
            """
            SELECT p.* FROM price_bar p
            JOIN (
                SELECT session_date, MAX(observed_at) AS observed_at
                FROM price_bar
                WHERE ticker = :ticker
                  AND known_at IS NOT NULL AND known_at <= :t
                GROUP BY session_date
            ) latest
              ON p.session_date = latest.session_date
             AND p.observed_at  = latest.observed_at
            WHERE p.ticker = :ticker
              AND p.known_at IS NOT NULL AND p.known_at <= :t
            ORDER BY p.session_date
            """,
            {"ticker": ticker},
        )

    def corporate_actions(self, ticker: str) -> list[dict[str, object]]:
        return self._query(
            """
            SELECT * FROM corporate_action
            WHERE ticker = :ticker
              AND known_at IS NOT NULL AND known_at <= :t
            ORDER BY effective_date
            """,
            {"ticker": ticker},
        )

    def fundamental_facts(
        self, ticker: str, concept: str | None = None
    ) -> list[dict[str, object]]:
        clause = "AND concept = :concept" if concept else ""
        return self._query(
            f"""
            SELECT * FROM fundamental_fact
            WHERE ticker = :ticker {clause}
              AND known_at IS NOT NULL AND known_at <= :t
            ORDER BY fiscal_period, accession
            """,
            {"ticker": ticker, "concept": concept},
        )
