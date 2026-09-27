"""TTL result cache for the research API (issue #80).

Cache key: sha256 of canonical JSON over
    (destination, vibe, collector, region, queries-hash,
     skip_geocode, from_analysis).
The issue names the first five; skip_geocode and from_analysis are added
because they change the result bytes — a geocoded run and a skipped-geocode
run must not share an entry. Documented here as a deliberate extension.

TTL table — KNOWN SPEC AMBIGUITY, documented interpretation (#80 defines no
TTL values and no per-category mapping):

    CATEGORY_TTLS maps analyzer place categories ("type" values, see
    scripts/validate_places.py TYPES) to seconds:
      perishable (menus/hours churn fast): restaurant, food, cafe,
          nightlife, bar            -> SHORT_TTL_S (6h)
      stable (a bridge is a bridge): sight, museum, landmark, nature,
          park                       -> LONG_TTL_S  (7d)
      everything else (shop, other, unknown) -> DEFAULT_TTL_S (24h)

    DESTINATION_TTL_OVERRIDES: per-destination pins (empty by default; a
    city whose dining scene churns fast could pin a shorter TTL for every
    category).

A run's TTL is the SHORTEST category TTL among its places
("shortest-category wins"): freshness is bounded by the most perishable
category, so a mixed run expires on the restaurant schedule — stale menus
are never served under a sights TTL. A run with no places gets
DEFAULT_TTL_S.

Table `cache` (service DB): cache_key PK, payload (the done-result JSON),
cached_at, ttl_s, job_id (the original job, for map-bundle fallback),
run_id. Expired entries are treated as misses and lazily deleted.

No price points are recorded (business decision, out of scope per #80):
cache hits are metered at cost tier "cached" vs "fresh" for pipeline runs.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  cache_key  TEXT PRIMARY KEY,
  payload    TEXT NOT NULL,        -- done-result JSON (cached:false at write)
  cached_at  TEXT NOT NULL,        -- UTC ISO
  ttl_s      REAL NOT NULL,
  job_id     TEXT NOT NULL,        -- original job (map-bundle fallback)
  run_id     INTEGER
);
"""

SHORT_TTL_S = 6 * 3600          # perishable: restaurants, cafes, nightlife
LONG_TTL_S = 7 * 24 * 3600      # stable: sights, museums, landmarks
DEFAULT_TTL_S = 24 * 3600       # everything else

CATEGORY_TTLS = {
    "restaurant": SHORT_TTL_S,
    "food": SHORT_TTL_S,
    "cafe": SHORT_TTL_S,
    "nightlife": SHORT_TTL_S,
    "bar": SHORT_TTL_S,
    "sight": LONG_TTL_S,
    "museum": LONG_TTL_S,
    "landmark": LONG_TTL_S,
    "nature": LONG_TTL_S,
    "park": LONG_TTL_S,
    "shop": DEFAULT_TTL_S,
    "other": DEFAULT_TTL_S,
}

# Per-destination TTL pins, e.g. {"tokyo": 6 * 3600}. Empty by default.
DESTINATION_TTL_OVERRIDES = {}


def _now():
    return datetime.now(timezone.utc)


def ttl_for_places(places, destination=None):
    """Seconds this run's result stays fresh: the shortest category TTL
    among its places (documented "shortest-category wins" rule)."""
    dest = (destination or "").strip().lower()
    if dest and dest in DESTINATION_TTL_OVERRIDES:
        return DESTINATION_TTL_OVERRIDES[dest]
    ttls = [CATEGORY_TTLS.get((p.get("category") or "").strip().lower(),
                              DEFAULT_TTL_S)
            for p in (places or [])]
    return min(ttls) if ttls else DEFAULT_TTL_S


def cache_key_for(params):
    """Deterministic cache key for a POST /v1/research param set."""
    queries = params.get("queries") or []
    queries_hash = hashlib.sha256(
        json.dumps(sorted(queries), ensure_ascii=False,
                   sort_keys=True).encode("utf-8")).hexdigest()[:16]
    canon = {
        "destination": (params.get("destination") or "").strip().lower(),
        "vibe": params.get("vibe") or "all",
        "collector": params.get("collector"),
        "region": (params.get("region") or "").strip().lower(),
        "queries": queries_hash,
        "skip_geocode": bool(params.get("skip_geocode")),
        "from_analysis": params.get("from_analysis"),
    }
    return hashlib.sha256(
        json.dumps(canon, sort_keys=True).encode("utf-8")).hexdigest()


class CacheStore:
    """Result cache. Fresh connection per operation (see apikeys.py)."""

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

    def get(self, cache_key):
        """Return the entry dict (with ttl_remaining_s) or None on miss /
        expiry. Expired entries are deleted lazily."""
        with self._db() as conn:
            row = conn.execute("SELECT * FROM cache WHERE cache_key = ?",
                               (cache_key,)).fetchone()
            if row is None:
                return None
            entry = dict(row)
            age = (_now() - datetime.fromisoformat(entry["cached_at"])
                   ).total_seconds()
            remaining = entry["ttl_s"] - age
            if remaining <= 0:
                conn.execute("DELETE FROM cache WHERE cache_key = ?",
                             (cache_key,))
                return None
            entry["payload"] = json.loads(entry["payload"])
            entry["ttl_remaining_s"] = int(remaining)
            return entry

    def put(self, cache_key, payload, ttl_s, job_id, run_id=None):
        with self._db() as conn:
            conn.execute(
                "INSERT INTO cache (cache_key, payload, cached_at, ttl_s,"
                " job_id, run_id) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(cache_key) DO UPDATE SET"
                " payload=excluded.payload, cached_at=excluded.cached_at,"
                " ttl_s=excluded.ttl_s, job_id=excluded.job_id,"
                " run_id=excluded.run_id",
                (cache_key, json.dumps(payload, ensure_ascii=False),
                 _now().isoformat(), ttl_s, job_id, run_id))

    def find_job(self, job_id):
        """Entry whose stored payload came from this job (map-bundle
        fallback for cache hits after a process restart)."""
        with self._db() as conn:
            row = conn.execute("SELECT * FROM cache WHERE job_id = ?",
                               (job_id,)).fetchone()
            return dict(row) if row else None

    def invalidate(self, cache_key):
        with self._db() as conn:
            conn.execute("DELETE FROM cache WHERE cache_key = ?",
                         (cache_key,))
