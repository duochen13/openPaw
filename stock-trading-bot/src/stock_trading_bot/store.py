"""Append-only point-in-time fact store (spec §5).

Design rules enforced here:
  - Four timestamps on every fact: event_time, observed_at, known_at, valid_from.
  - Append-only. No UPDATE, ever. A restatement is a new row with a later
    known_at and the same event_time, which is what makes "do not backfill
    revisions into past predictions" automatic.
  - observed_at is part of every primary key, so a re-observation appends
    instead of colliding.
  - A NULL known_at means invisible. See PointInTimeView below.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from stock_trading_bot.timestamps import to_iso

#: The canonical shape produced by timestamps.to_iso: fixed-width UTC with
#: microseconds. Enforced at the database boundary so that lexicographic
#: comparison always equals chronological comparison - making that a property
#: of the COLUMN, not merely of whoever happened to write the row. Without it,
#: one hand-built string entering by another route (a fixture, a migration, a
#: notebook INSERT) silently breaks ordering with no error anywhere.
#:
#: `typeof(column) = 'text'` is checked alongside the GLOB pattern because a
#: bytes value bound where a TEXT column was expected can otherwise slip
#: through: GLOB coerces its operand for comparison, so a blob can match the
#: pattern and land in the column. Without this, such a row is stored, and on
#: read `PointInTimeView` treats it as an unknown, non-string vintage - which
#: must raise (see the TypeError branch in `PointInTimeView._rows`) rather
#: than silently disappearing, but it is better to refuse it at the write
#: boundary entirely.
_CANONICAL_TS = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
    "[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00"
)


def _ts_check(column: str) -> str:
    """A CHECK clause pinning `column` to the canonical timestamp shape."""
    return (
        f"CHECK ({column} IS NULL OR "
        f"(typeof({column}) = 'text' AND {column} GLOB '{_CANONICAL_TS}'))"
    )


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

-- The primary key includes `unit` (USD vs. thousands-of-USD would otherwise
-- collide) and `observed_at` (without it, re-fetching a filing you already
-- have raises IntegrityError instead of appending a restatement - the same
-- append-only mechanism price_bar and corporate_action already rely on).
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
    -- Task 10's EDGAR adapter currently writes a bare date (entry["filed"])
    -- here, which this CHECK will reject. That adapter's writer must route
    -- the value through timestamps.to_iso before this column will accept it.
    valid_from    TEXT          {_ts_check('valid_from')},
    source        TEXT NOT NULL,
    PRIMARY KEY (ticker, concept, unit, fiscal_period, accession, observed_at)
);

CREATE INDEX IF NOT EXISTS ix_price_known  ON price_bar (ticker, known_at);
CREATE INDEX IF NOT EXISTS ix_action_known ON corporate_action (ticker, known_at);
CREATE INDEX IF NOT EXISTS ix_fact_known   ON fundamental_fact (ticker, known_at);
"""

#: The full column set each table's rows carry, in schema declaration order.
#: `PointInTimeView._rows` validates every returned row against this, and
#: `Store._insert` validates every write against it - both so a typo or a
#: stray alias produces a loud, immediate error instead of silently doing
#: the wrong thing.
_COLUMNS: dict[str, tuple[str, ...]] = {
    "price_bar": (
        "ticker", "session_date", "event_time", "observed_at", "known_at",
        "open", "high", "low", "close", "volume", "source",
    ),
    "corporate_action": (
        "ticker", "effective_date", "action_type", "ratio", "amount",
        "event_time", "observed_at", "known_at", "source",
    ),
    "fundamental_fact": (
        "ticker", "concept", "unit", "fiscal_period", "value", "accession",
        "event_time", "observed_at", "known_at", "valid_from", "source",
    ),
}


class Store:
    """Owns the connection. Callers wanting to read facts use `as_of`."""

    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self._path = path
        self._ro_conn: sqlite3.Connection | None = None
        self._closed = False

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
        """A connection SQLite itself refuses to write through.

        `mode=ro` is an open flag, not a setting: unlike `PRAGMA query_only`,
        a caller holding this connection cannot turn it back off. The pragma
        is applied as well, so the refusal survives even if the URI form is
        ever changed. `Path.as_uri()` handles percent-encoding, so paths
        containing brackets or colons are safe.

        The attached-database limit is set to 0 because `mode=ro` is a flag
        on `main` only - it says nothing about a database `ATTACH`ed
        afterward. Without this, `ATTACH DATABASE '<path>' AS w` reopens the
        same file read-write and a subsequent `DELETE FROM w.price_bar`
        empties the store, regardless of `mode=ro` or `PRAGMA query_only` on
        the original connection.
        """
        if self._closed:
            raise ValueError("store is closed")
        if self._ro_conn is None:
            ro = sqlite3.connect(f"{self._path.resolve().as_uri()}?mode=ro", uri=True)
            ro.row_factory = sqlite3.Row
            ro.execute("PRAGMA query_only = ON")
            ro.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            self._ro_conn = ro
        return self._ro_conn

    def close(self) -> None:
        if self._ro_conn is not None:
            self._ro_conn.close()
            self._ro_conn = None
        self._conn.close()
        self._closed = True

    def as_of(self, t: datetime) -> PointInTimeView:
        """The only supported way to read facts.

        Anything reachable through the returned view was knowable at `t`.
        """
        if t.tzinfo is None:
            raise ValueError("as_of requires a timezone-aware datetime")
        return PointInTimeView(self._readonly_conn(), to_iso(t))

    def latest_price_bar(
        self, ticker: str, session_date: str
    ) -> dict[str, object] | None:
        """The most recently observed bar for a session, ignoring visibility.

        For the WRITER only, so ingestion can tell whether newly fetched data
        actually differs from what is already held. Append-only means a new row
        records new information; re-observing identical values is not a
        restatement and should not grow the table. Readers must go through
        `as_of` - this method deliberately ignores `known_at`.
        """
        row = self._conn.execute(
            "SELECT * FROM price_bar WHERE ticker = ? AND session_date = ? "
            "ORDER BY observed_at DESC LIMIT 1",
            (ticker, session_date),
        ).fetchone()
        return dict(row) if row is not None else None

    def insert_price_bar(self, **row: object) -> None:
        self._insert("price_bar", row)

    def insert_corporate_action(self, **row: object) -> None:
        self._insert("corporate_action", row)

    def insert_fundamental_fact(self, **row: object) -> None:
        self._insert("fundamental_fact", row)

    def _insert(self, table: str, row: dict[str, object]) -> None:
        unknown = set(row) - set(_COLUMNS[table])
        if unknown:
            raise ValueError(f"unknown column(s) for {table}: {sorted(unknown)}")
        cols = ", ".join(row)
        marks = ", ".join(f":{c}" for c in row)
        self._conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", row)
        # One commit per insert. A batch entry point is wanted before the
        # ingest layer grows: as written, a reader can observe a partial
        # vintage mid-ingest (some rows of a batch committed, others not).
        self._conn.commit()


class PointInTimeView:
    """A read-only window on the store as it was visible at `t`.

    The goal here is not that a hostile caller cannot leak through this
    class - that is not achievable from inside a single process, and
    pretending otherwise is how the previous two rounds of "fixes" on this
    class happened. The goal is that the ACCIDENTAL path disappears: a
    good-faith developer writing an ordinary-looking accessor months from
    now cannot leak a future-dated row, or mutate the append-only store,
    just by getting the SQL slightly wrong.

    Two narrower, independent guarantees follow from that:

      1. The connection is opened `mode=ro`, an open flag rather than a
         revocable setting, with the attached-database limit set to 0. No
         query issued through it - however written - can mutate the store,
         or reopen the same file read-write via `ATTACH`.
      2. `_rows` re-checks every row's `known_at` in Python and validates
         the row's full column set, in order, against the table's declared
         shape. An accessor whose SQL forgets the `known_at` predicate still
         cannot emit a future-dated row. An accessor whose SQL renames,
         drops, reorders, or `COALESCE`s `known_at` - for example turning a
         NULL vintage into an old date, which is a plausible thing to write
         and would otherwise defeat fail-closed - is refused loudly instead
         of silently trusting a column that no longer means what its name
         says.

    Neither mechanism, nor anything else available inside this process,
    stops a caller who deliberately constructs a projection to defeat the
    check - for instance one that lists every real column in the right
    order and position, but computes the value under the `known_at` alias
    from some other column entirely. That is accepted, consciously: the
    column-shape check can see names and positions, not provenance, and no
    in-process check can see provenance either.

    A new accessor gets this guarantee by routing its query through
    `_rows(table, sql, params)`. Reaching around `_rows` - or around this
    view entirely, e.g. by holding `store._readonly_conn()` - forfeits it.
    """

    __slots__ = ("_rows", "_t")

    _rows: Callable[[str, str, dict[str, object]], list[dict[str, object]]]
    _t: str

    def __init__(self, conn: sqlite3.Connection, t: str) -> None:
        def rows(table: str, sql: str, params: dict[str, object]) -> list[dict[str, object]]:
            expected = _COLUMNS[table]  # KeyError on an unknown table is correct
            out: list[dict[str, object]] = []
            for raw in conn.execute(sql, {**params, "t": t}):
                row = dict(raw)
                if tuple(row) != expected:
                    raise ValueError(
                        f"accessor for {table} returned columns {tuple(row)}, "
                        f"expected {expected}. A projection that renames, drops, "
                        "or reorders known_at cannot be visibility-checked."
                    )
                known_at = row["known_at"]
                if known_at is None:
                    continue  # unknown vintage fails closed; not an error
                if not isinstance(known_at, str):
                    raise TypeError(
                        f"known_at must be TEXT, got {type(known_at).__name__}: "
                        f"{known_at!r}. A non-text vintage means the row was "
                        "written outside to_iso, or the query computed it from "
                        "something other than the known_at column."
                    )
                if known_at <= t:
                    out.append(row)
            return out

        object.__setattr__(self, "_rows", rows)
        object.__setattr__(self, "_t", t)

    @property
    def t(self) -> str:
        return self._t

    def price_bars(self, ticker: str) -> list[dict[str, object]]:
        """Visible bars, one row per session, latest visible observation wins."""
        return self._rows(
            "price_bar",
            """
            SELECT p.ticker, p.session_date, p.event_time, p.observed_at,
                   p.known_at, p.open, p.high, p.low, p.close, p.volume, p.source
            FROM price_bar p
            JOIN (
                SELECT ticker, session_date, MAX(observed_at) AS observed_at
                FROM price_bar
                WHERE ticker = :ticker
                  AND known_at IS NOT NULL AND known_at <= :t
                GROUP BY ticker, session_date
            ) latest
              ON p.ticker       = latest.ticker
             AND p.session_date = latest.session_date
             AND p.observed_at  = latest.observed_at
            WHERE p.ticker = :ticker
              AND p.known_at IS NOT NULL AND p.known_at <= :t
            ORDER BY p.session_date
            """,
            {"ticker": ticker},
        )

    def corporate_actions(self, ticker: str) -> list[dict[str, object]]:
        return self._rows(
            "corporate_action",
            """
            SELECT ticker, effective_date, action_type, ratio, amount,
                   event_time, observed_at, known_at, source
            FROM corporate_action
            WHERE ticker = :ticker
              AND known_at IS NOT NULL AND known_at <= :t
            ORDER BY effective_date
            """,
            {"ticker": ticker},
        )

    def fundamental_facts(
        self, ticker: str, concept: str | None = None
    ) -> list[dict[str, object]]:
        clause = "AND concept = :concept" if concept is not None else ""
        return self._rows(
            "fundamental_fact",
            f"""
            SELECT ticker, concept, unit, fiscal_period, value, accession,
                   event_time, observed_at, known_at, valid_from, source
            FROM fundamental_fact
            WHERE ticker = :ticker {clause}
              AND known_at IS NOT NULL AND known_at <= :t
            ORDER BY fiscal_period, accession
            """,
            {"ticker": ticker, "concept": concept},
        )
