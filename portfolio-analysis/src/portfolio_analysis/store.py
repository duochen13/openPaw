"""SQLite store for prices and detected moves (spec §11).

Deliberately NOT a point-in-time store. The sibling project stock-trading-bot
carries event_time/observed_at/known_at/valid_from on every fact to stop a
forward-looking model from seeing the future. This project exists to look
backward with full hindsight, so that machinery would be dead weight that
implies a guarantee this project does not make.

Prices are upserted rather than appended: an adjusted close is legitimately
rewritten by a later split or dividend, and one consistent present-day adjusted
series is exactly what a five-year retrospective chart should show. Raw OHLC is
stored alongside, so reconstruction stays possible without a re-fetch.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

#: Fixed-width ISO date. Pinned on the COLUMN, not merely on whoever writes the
#: row, so that lexicographic ordering always equals chronological ordering -
#: a property every window slice in moves.py depends on.
_ISO_DATE = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS price_bar (
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL CHECK (typeof(date) = 'text' AND date GLOB '{_ISO_DATE}'),
    open       REAL NOT NULL,
    high       REAL NOT NULL,
    low        REAL NOT NULL,
    close      REAL NOT NULL,
    adj_close  REAL NOT NULL,
    volume     REAL NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS move (
    ticker           TEXT NOT NULL,
    date             TEXT NOT NULL CHECK (typeof(date) = 'text' AND date GLOB '{_ISO_DATE}'),
    ret              REAL NOT NULL,
    benchmark        TEXT NOT NULL,
    benchmark_return REAL NOT NULL,
    beta             REAL NOT NULL,
    alpha            REAL NOT NULL,
    abnormal_return  REAL NOT NULL,
    sigma_60         REAL NOT NULL,
    z                REAL NOT NULL,
    computed_at      TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS eps_quarter (
    ticker     TEXT NOT NULL,
    quarter    TEXT NOT NULL CHECK (typeof(quarter) = 'text' AND quarter GLOB '{_ISO_DATE}'),
    filed      TEXT NOT NULL CHECK (typeof(filed) = 'text' AND filed GLOB '{_ISO_DATE}'),
    eps        REAL NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (ticker, quarter)
);

CREATE TABLE IF NOT EXISTS operating_eps_quarter (
    ticker     TEXT NOT NULL,
    quarter    TEXT NOT NULL CHECK (typeof(quarter) = 'text' AND quarter GLOB '{_ISO_DATE}'),
    filed      TEXT NOT NULL CHECK (typeof(filed) = 'text' AND filed GLOB '{_ISO_DATE}'),
    eps        REAL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (ticker, quarter)
);

CREATE TABLE IF NOT EXISTS kpi_quarter (
    ticker     TEXT NOT NULL,
    metric     TEXT NOT NULL,
    quarter    TEXT NOT NULL CHECK (typeof(quarter) = 'text' AND quarter GLOB '{_ISO_DATE}'),
    filed      TEXT NOT NULL CHECK (typeof(filed) = 'text' AND filed GLOB '{_ISO_DATE}'),
    value      REAL NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (ticker, metric, quarter)
);
"""

_PRICE_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close",
    "adj_close", "volume", "source", "fetched_at",
)
_MOVE_COLUMNS = (
    "ticker", "date", "ret", "benchmark", "benchmark_return",
    "beta", "alpha", "abnormal_return", "sigma_60", "z", "computed_at",
)
_EPS_COLUMNS = ("ticker", "quarter", "filed", "eps", "source", "fetched_at")
_OPERATING_EPS_COLUMNS = ("ticker", "quarter", "filed", "eps", "source", "fetched_at")
_KPI_COLUMNS = ("ticker", "metric", "quarter", "filed", "value", "source", "fetched_at")


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a database created by an older schema up to date.

    The `move` table gained the `alpha` column after it first shipped. SQLite
    cannot add a NOT NULL column without a default, so the migration backfills
    0.0 - the next `detect-moves` run overwrites every row with the real
    intercept anyway. A column that exists is left alone; this is idempotent.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(move)")}
    if "alpha" not in columns:
        conn.execute("ALTER TABLE move ADD COLUMN alpha REAL NOT NULL DEFAULT 0.0")
    # The eps_quarter table shipped mid-development of issue #28 without the
    # filed column; databases created in that window gain it here.
    eps_columns = {row[1] for row in conn.execute("PRAGMA table_info(eps_quarter)")}
    if eps_columns and "filed" not in eps_columns:
        conn.execute(
            "ALTER TABLE eps_quarter ADD COLUMN filed TEXT NOT NULL DEFAULT '1970-01-01'"
        )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Store:
    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> Store:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
        return cls(conn, target)

    def close(self) -> None:
        self._conn.close()

    def _upsert(
        self,
        table: str,
        columns: tuple[str, ...],
        rows: Iterable[Mapping[str, object]],
        key_columns: tuple[str, ...] = ("ticker", "date"),
    ) -> int:
        placeholders = ", ".join(f":{c}" for c in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in columns if c not in key_columns
        )
        conflict = ", ".join(key_columns)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        )
        stamped = [{**row, "fetched_at": _now(), "computed_at": _now()} for row in rows]
        payload = [{c: row[c] for c in columns} for row in stamped]
        with self._conn:
            self._conn.executemany(sql, payload)
        return len(payload)

    def upsert_price_bars(self, bars: Iterable[Mapping[str, object]]) -> int:
        return self._upsert("price_bar", _PRICE_COLUMNS, bars)

    def upsert_eps_quarters(
        self, quarters: Iterable[Mapping[str, object]]
    ) -> int:
        """Upsert quarterly EPS actuals (issue #28).

        A restated quarter is legitimately rewritten by a later fetch, the
        same upsert-not-append reasoning as price bars.
        """
        return self._upsert(
            "eps_quarter", _EPS_COLUMNS, quarters, key_columns=("ticker", "quarter")
        )

    def eps_quarters(self, ticker: str) -> list[tuple[str, str, float]]:
        """(quarter_end, filed, eps) ascending for ``ticker``."""
        cursor = self._conn.execute(
            "SELECT quarter, filed, eps FROM eps_quarter WHERE ticker = ? ORDER BY quarter",
            (ticker.upper(),),
        )
        return [
            (row["quarter"], row["filed"], float(row["eps"])) for row in cursor
        ]

    def eps_fetched_at(self, ticker: str) -> str | None:
        """Newest fetch timestamp for ``ticker``'s EPS quarters, if any."""
        cursor = self._conn.execute(
            "SELECT MAX(fetched_at) AS latest FROM eps_quarter WHERE ticker = ?",
            (ticker.upper(),),
        )
        row = cursor.fetchone()
        return str(row["latest"]) if row and row["latest"] else None

    def upsert_operating_eps_quarters(self, quarters: Iterable[Mapping[str, object]]) -> int:
        """Upsert derived operating EPS (ex-investment gains, issue #70).

        ``eps`` may be None: a quarter whose investment gain cannot be
        tax-adjusted is stored as an explicit gap, never silently filled
        with the GAAP value. Keyed by (ticker, quarter) so a refetch is
        idempotent and restatements rewrite cleanly.
        """
        return self._upsert(
            "operating_eps_quarter",
            _OPERATING_EPS_COLUMNS,
            quarters,
            key_columns=("ticker", "quarter"),
        )

    def operating_eps_quarters(self, ticker: str) -> list[tuple[str, str, float | None]]:
        """(quarter_end, filed, operating_eps) ascending for ``ticker``.

        ``operating_eps`` is None for gap quarters.
        """
        cursor = self._conn.execute(
            "SELECT quarter, filed, eps FROM operating_eps_quarter "
            "WHERE ticker = ? ORDER BY quarter",
            (ticker.upper(),),
        )
        return [
            (
                row["quarter"],
                row["filed"],
                float(row["eps"]) if row["eps"] is not None else None,
            )
            for row in cursor
        ]

    def operating_eps_fetched_at(self, ticker: str) -> str | None:
        """Newest fetch timestamp for ``ticker``'s operating EPS, if any."""
        cursor = self._conn.execute(
            "SELECT MAX(fetched_at) AS latest FROM operating_eps_quarter WHERE ticker = ?",
            (ticker.upper(),),
        )
        row = cursor.fetchone()
        return str(row["latest"]) if row and row["latest"] else None

    def upsert_kpi_quarters(
        self, quarters: Iterable[Mapping[str, object]]
    ) -> int:
        """Upsert quarterly business-KPI values (issue #29).

        Keyed by (ticker, metric, quarter): a restated quarter is
        legitimately rewritten by a later fetch, the same upsert-not-append
        reasoning as price bars and EPS quarters.
        """
        return self._upsert(
            "kpi_quarter",
            _KPI_COLUMNS,
            quarters,
            key_columns=("ticker", "metric", "quarter"),
        )

    def kpi_quarters(self, ticker: str, metric: str) -> list[tuple[str, str, float]]:
        """(quarter_end, filed, value) ascending for ``ticker``/``metric``."""
        cursor = self._conn.execute(
            "SELECT quarter, filed, value FROM kpi_quarter "
            "WHERE ticker = ? AND metric = ? ORDER BY quarter",
            (ticker.upper(), metric),
        )
        return [
            (row["quarter"], row["filed"], float(row["value"])) for row in cursor
        ]

    def kpi_fetched_at(self, ticker: str) -> str | None:
        """Newest fetch timestamp for ``ticker``'s KPI quarters, if any."""
        cursor = self._conn.execute(
            "SELECT MAX(fetched_at) AS latest FROM kpi_quarter WHERE ticker = ?",
            (ticker.upper(),),
        )
        row = cursor.fetchone()
        return str(row["latest"]) if row and row["latest"] else None

    def upsert_moves(self, moves: Iterable[Mapping[str, object]]) -> int:
        return self._upsert("move", _MOVE_COLUMNS, moves)

    def replace_moves(self, ticker: str, moves: Iterable[Mapping[str, object]]) -> int:
        """Make the move table match a freshly computed set, exactly.

        write_moves rewrites the JSON artifact wholesale, so a plain upsert
        leaves the database holding days that no longer flag after a price
        restatement or a threshold change - the two outputs silently diverge
        and the JSON is the one that is right.
        """
        with self._conn:
            self._conn.execute("DELETE FROM move WHERE ticker = ?", (ticker.upper(),))
        return self.upsert_moves(moves)

    def adjusted_series(self, ticker: str) -> dict[str, float]:
        """Date -> adjusted close, ordered by date."""
        cursor = self._conn.execute(
            "SELECT date, adj_close FROM price_bar WHERE ticker = ? ORDER BY date",
            (ticker.upper(),),
        )
        return {row["date"]: float(row["adj_close"]) for row in cursor}

    def price_bar_count(self, ticker: str) -> int:
        cursor = self._conn.execute(
            "SELECT COUNT(*) AS n FROM price_bar WHERE ticker = ?", (ticker.upper(),)
        )
        return int(cursor.fetchone()["n"])

    def moves(self, ticker: str) -> list[dict[str, object]]:
        cursor = self._conn.execute(
            "SELECT * FROM move WHERE ticker = ? ORDER BY date", (ticker.upper(),)
        )
        return [dict(row) for row in cursor]
