"""API-key auth for the travel-assistant service (issue #80).

Key lifecycle:
    python -m travel_assistant.apikeys create --name NAME   # prints key ONCE
    python -m travel_assistant.apikeys list
    python -m travel_assistant.apikeys revoke NAME

Storage: only the SHA-256 hash of a key is persisted (table `api_keys` in
the service DB — see paths.api_db_path()). Verification hashes the
presented bearer token and compares with hmac.compare_digest (constant
time). Raw keys are never logged, never stored, and printed exactly once
at creation.

Dev keys: TA_DEV_API_KEYS="k1,k2" seeds process-local keys (local dev / CI).
They are verified against the env value at request time; a stable
`dev:<n>` row is created on first use so metering has a key_id to bill.
Never use dev keys in production — they live in the process environment.
"""
import argparse
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT UNIQUE NOT NULL,
  key_hash     TEXT NOT NULL,          -- sha256 hex of the raw key; raw never stored
  created_at   TEXT NOT NULL,
  revoked      INTEGER NOT NULL DEFAULT 0,
  last_used_at TEXT
);
"""

KEY_PREFIX = "ta_"


def _hash(raw_key):
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _dev_keys():
    return [k.strip() for k in os.environ.get("TA_DEV_API_KEYS", "").split(",")
            if k.strip()]


class ApiKeyStore:
    """Mint / verify / revoke API keys. Opens a fresh SQLite connection per
    operation (timeout=30) so request threads and job-runner threads never
    share a connection."""

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

    # -- writes ---------------------------------------------------------
    def create_key(self, name):
        """Mint a key. Returns the RAW key exactly once — the caller must
        show it to the user now; it cannot be recovered later."""
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        with self._db() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO api_keys (name, key_hash, created_at) "
                    "VALUES (?, ?, ?)",
                    (name, _hash(raw), _now_iso()))
            except sqlite3.IntegrityError:
                raise ValueError(f"api key name {name!r} already exists")
            return {"id": cur.lastrowid, "name": name, "key": raw,
                    "created_at": _now_iso()}

    def revoke(self, name):
        with self._db() as conn:
            cur = conn.execute("UPDATE api_keys SET revoked = 1 WHERE name = ?",
                               (name,))
            return cur.rowcount > 0

    def touch(self, key_id):
        with self._db() as conn:
            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                         (_now_iso(), key_id))

    # -- reads ----------------------------------------------------------
    def verify(self, raw_key):
        """Return the key row for a valid, non-revoked key, else None.

        Checks stored keys first (constant-time compare per row), then
        TA_DEV_API_KEYS entries. Dev-key hits get a stable `dev:<n>` row on
        first use so metering can bill them.
        """
        if not raw_key:
            return None
        digest = _hash(raw_key)
        with self._db() as conn:
            match = None
            for row in conn.execute("SELECT * FROM api_keys"):
                if hmac.compare_digest(digest, row["key_hash"]):
                    match = dict(row)
            if match and not match["revoked"]:
                conn.execute(
                    "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                    (_now_iso(), match["id"]))
                return match
            for i, dev in enumerate(_dev_keys()):
                if hmac.compare_digest(digest, _hash(dev)):
                    name = f"dev:{i}"
                    row = conn.execute(
                        "SELECT * FROM api_keys WHERE name = ?",
                        (name,)).fetchone()
                    if row is None:
                        cur = conn.execute(
                            "INSERT INTO api_keys (name, key_hash, created_at)"
                            " VALUES (?, ?, ?)", (name, digest, _now_iso()))
                        key_id = cur.lastrowid
                    else:
                        key_id = row["id"]
                        conn.execute(
                            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                            (_now_iso(), key_id))
                    return {"id": key_id, "name": name,
                            "created_at": _now_iso(), "revoked": 0,
                            "last_used_at": _now_iso()}
        return None

    def list_keys(self):
        """Metadata only — never hashes, never raw keys."""
        with self._db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT id, name, created_at, revoked, last_used_at "
                "FROM api_keys ORDER BY id")]


# --------------------------------------------------------------------------
# CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="travel-assistant API key manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="mint a key (raw key printed once)")
    c.add_argument("--name", required=True, help="human label for the key")

    sub.add_parser("list", help="list keys (metadata only)")

    r = sub.add_parser("revoke", help="revoke a key by name")
    r.add_argument("name", help="key name to revoke")

    a = ap.parse_args(argv)
    store = ApiKeyStore()
    if a.cmd == "create":
        try:
            rec = store.create_key(a.name)
        except ValueError as e:
            print(f"error: {e}")
            return 1
        print(f"API key created (name={rec['name']!r}, id={rec['id']}).")
        print("SAVE THIS NOW — it will not be shown again and cannot be "
              "recovered (only the hash is stored):")
        print(rec["key"])
    elif a.cmd == "list":
        for k in store.list_keys():
            print(f"id={k['id']} name={k['name']!r} "
                  f"revoked={bool(k['revoked'])} created={k['created_at']} "
                  f"last_used={k['last_used_at']}")
    elif a.cmd == "revoke":
        print("revoked" if store.revoke(a.name) else f"no key named {a.name!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
