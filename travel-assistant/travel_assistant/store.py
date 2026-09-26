"""SQLite run store: every research run recorded with params, places, artifacts.

Tables:
  runs   — one row per research() call (params, artifact paths, timing, status).
  places — one row per place in the run's final analysis object.

price_hint and geocode_confidence are reserved for future stages (the v1
analyzer does not emit them); columns exist now so later stages can fill
them without a migration.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  run_uuid         TEXT UNIQUE NOT NULL,
  destination      TEXT NOT NULL,
  slug             TEXT NOT NULL,
  vibe             TEXT,
  date_start       TEXT,
  date_end         TEXT,
  budget_tier      TEXT,
  source_mode      TEXT,
  raw_path         TEXT,
  analysis_path    TEXT,
  kml_path         TEXT,
  map_html_path    TEXT,
  csv_path         TEXT,
  n_places         INTEGER,
  n_geocoded       INTEGER,
  status           TEXT NOT NULL,          -- running | complete | failed
  error            TEXT,
  started_at       TEXT NOT NULL,
  ended_at         TEXT,
  duration_s       REAL
);
CREATE TABLE IF NOT EXISTS places (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id             INTEGER NOT NULL REFERENCES runs(id),
  name               TEXT NOT NULL,
  category           TEXT,
  area               TEXT,
  lat                REAL,
  lng                REAL,
  why_loved          TEXT,
  source_urls        TEXT,                 -- JSON list
  price_hint         TEXT,
  mention_count      INTEGER,
  sentiment          TEXT,
  rating             REAL,
  map_link           TEXT,
  geocode_confidence REAL,
  tags               TEXT                  -- JSON list
);
CREATE INDEX IF NOT EXISTS idx_places_run ON places(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_dest ON runs(destination);
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Thin wrapper around the runs SQLite DB."""

    def __init__(self, path=None):
        self.path = paths.runs_db_path() if path is None else Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- writes ---------------------------------------------------------
    def create_run(self, destination, slug, vibe="all", date_start=None,
                   date_end=None, budget_tier=None, source_mode=None,
                   raw_path=None, analysis_path=None, started_at=None):
        cur = self._conn.execute(
            """INSERT INTO runs (run_uuid, destination, slug, vibe, date_start,
                                 date_end, budget_tier, source_mode, raw_path,
                                 analysis_path, status, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)""",
            (uuid.uuid4().hex, destination, slug, vibe, date_start, date_end,
             budget_tier, source_mode, raw_path, analysis_path,
             started_at or _now_iso()))
        self._conn.commit()
        return cur.lastrowid

    def update_run(self, run_id, **fields):
        allowed = {"source_mode", "raw_path", "analysis_path", "kml_path",
                   "map_html_path", "csv_path", "n_places", "n_geocoded",
                   "status", "error", "ended_at", "duration_s"}
        sets = [f"{k} = ?" for k in fields if k in allowed]
        if not sets:
            return
        vals = [fields[k] for k in fields if k in allowed]
        self._conn.execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", (*vals, run_id))
        self._conn.commit()

    def complete_run(self, run_id, n_places, n_geocoded, kml_path=None,
                     map_html_path=None, csv_path=None, started_at=None):
        ended = _now_iso()
        duration = None
        if started_at:
            try:
                duration = (datetime.fromisoformat(ended)
                            - datetime.fromisoformat(started_at)).total_seconds()
            except ValueError:
                duration = None
        self.update_run(run_id, status="complete", n_places=n_places,
                        n_geocoded=n_geocoded, kml_path=kml_path,
                        map_html_path=map_html_path, csv_path=csv_path,
                        ended_at=ended, duration_s=duration)

    def fail_run(self, run_id, error):
        self.update_run(run_id, status="failed", error=str(error),
                        ended_at=_now_iso())

    def add_places(self, run_id, places):
        rows = [(
            run_id,
            p.get("name"),
            p.get("type"),
            p.get("area"),
            p.get("lat"),
            p.get("lng"),
            p.get("why_loved"),
            json.dumps(p.get("source_urls") or [], ensure_ascii=False),
            p.get("price_hint"),
            p.get("mention_count"),
            p.get("sentiment"),
            p.get("rating"),
            p.get("map_link"),
            p.get("geocode_confidence"),
            json.dumps(p.get("tags") or [], ensure_ascii=False),
        ) for p in places]
        self._conn.executemany(
            """INSERT INTO places (run_id, name, category, area, lat, lng,
                                   why_loved, source_urls, price_hint,
                                   mention_count, sentiment, rating, map_link,
                                   geocode_confidence, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
        self._conn.commit()
        return len(rows)

    # -- reads ----------------------------------------------------------
    def get_run(self, run_id):
        row = self._conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        rec = dict(row)
        rec["places"] = [
            dict(p) for p in self._conn.execute(
                "SELECT * FROM places WHERE run_id = ? ORDER BY id", (run_id,))]
        for p in rec["places"]:
            p["source_urls"] = json.loads(p["source_urls"] or "[]")
            p["tags"] = json.loads(p["tags"] or "[]")
        return rec

    def list_runs(self, limit=20, destination=None):
        q = "SELECT * FROM runs"
        args = []
        if destination:
            q += " WHERE destination = ?"
            args.append(destination)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._conn.execute(q, args)]

    def latest_run(self, destination=None):
        rows = self.list_runs(limit=1, destination=destination)
        return rows[0] if rows else None
