"""Per-call metering per API key (issue #80).

Table `usage` (service DB — see paths.api_db_path()): one row per /v1 call.

    key_id     INTEGER NULL   -- NULL for rejected-auth calls (no key to bill)
    endpoint   TEXT           -- request path, e.g. /v1/research
    method     TEXT           -- GET / POST
    ts         TEXT           -- UTC ISO timestamp
    cached     INTEGER        -- 1 if the call was served WITHOUT a pipeline run
    cost_tier  TEXT           -- "fresh" | "cached"

Cost-tier rule (documented interpretation): tier is "fresh" iff the call
triggered a NEW pipeline run (a job was enqueued on POST /v1/research).
Everything else — TTL cache hits, idempotent replays, polls, map fetches,
usage reads, and rejected calls (400/401/429/503) — is "cached": it consumed
no pipeline work. No price points are recorded here (business decision,
out of scope per #80); tiers are the strings "fresh"/"cached" only.

GET /v1/usage (a non-spec extra, documented in service.py) exposes the
calling key's own summary.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  key_id     INTEGER,              -- NULL when auth failed (nothing to bill)
  endpoint   TEXT NOT NULL,
  method     TEXT NOT NULL,
  ts         TEXT NOT NULL,
  cached     INTEGER NOT NULL,     -- 0/1: served without running the pipeline
  cost_tier  TEXT NOT NULL         -- "fresh" | "cached"
);
CREATE INDEX IF NOT EXISTS idx_usage_key ON usage(key_id);
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class UsageStore:
    """Append-only usage log. Fresh connection per operation so request
    threads and job-runner threads never share one."""

    def __init__(self, path=None):
        self._path = Path(path) if path else None

    @contextmanager
    def _db(self):
        p = Path(self._path) if self._path else paths.api_db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), timeout=30.0,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, key_id, endpoint, method, cached, cost_tier):
        """Record one /v1 call. cached: bool-ish; cost_tier: fresh|cached."""
        assert cost_tier in ("fresh", "cached"), cost_tier
        with self._db() as conn:
            conn.execute(
                "INSERT INTO usage (key_id, endpoint, method, ts, cached,"
                " cost_tier) VALUES (?, ?, ?, ?, ?, ?)",
                (key_id, endpoint, method, _now_iso(), int(bool(cached)),
                 cost_tier))

    def summary(self, key_id):
        """Per-key totals for GET /v1/usage and for tests."""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT endpoint, method, cached, cost_tier, COUNT(*) AS n "
                "FROM usage WHERE key_id = ? "
                "GROUP BY endpoint, method, cached, cost_tier", (key_id,))
            by_endpoint, by_tier = {}, {"fresh": 0, "cached": 0}
            cached_calls, total = 0, 0
            for r in rows:
                by_endpoint[f"{r['method']} {r['endpoint']}"] = \
                    by_endpoint.get(f"{r['method']} {r['endpoint']}", 0) + r["n"]
                by_tier[r["cost_tier"]] = \
                    by_tier.get(r["cost_tier"], 0) + r["n"]
                cached_calls += r["n"] if r["cached"] else 0
                total += r["n"]
            return {"key_id": key_id, "total_calls": total,
                    "by_endpoint": by_endpoint, "by_cost_tier": by_tier,
                    "cached_calls": cached_calls,
                    "fresh_calls": total - cached_calls}

    def rows(self, key_id, limit=50):
        """Latest raw rows for a key (tests / debugging)."""
        with self._db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM usage WHERE key_id = ? ORDER BY id DESC LIMIT ?",
                (key_id, limit))]
