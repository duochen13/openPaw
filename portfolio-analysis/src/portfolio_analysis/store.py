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
    abnormal_return  REAL NOT NULL,
    sigma_60         REAL NOT NULL,
    z                REAL NOT NULL,
    computed_at      TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
"""

_PRICE_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close",
    "adj_close", "volume", "source", "fetched_at",
)
_MOVE_COLUMNS = (
    "ticker", "date", "ret", "benchmark", "benchmark_return",
    "beta", "abnormal_return", "sigma_60", "z", "computed_at",
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
        conn.commit()
        return cls(conn, target)

    def close(self) -> None:
        self._conn.close()

    def _upsert(
        self, table: str, columns: tuple[str, ...], rows: Iterable[Mapping[str, object]]
    ) -> int:
        placeholders = ", ".join(f":{c}" for c in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in ("ticker", "date"))
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT (ticker, date) DO UPDATE SET {updates}"
        )
        stamped = [{**row, "fetched_at": _now(), "computed_at": _now()} for row in rows]
        payload = [{c: row[c] for c in columns} for row in stamped]
        with self._conn:
            self._conn.executemany(sql, payload)
        return len(payload)

    def upsert_price_bars(self, bars: Iterable[Mapping[str, object]]) -> int:
        return self._upsert("price_bar", _PRICE_COLUMNS, bars)

    def upsert_moves(self, moves: Iterable[Mapping[str, object]]) -> int:
        return self._upsert("move", _MOVE_COLUMNS, moves)

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
