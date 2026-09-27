"""Path resolution for the travel_assistant package.

Mirrors the scripts' convention: all data paths resolve relative to the
travel-assistant/ project directory (the package's parent), never the caller's
working directory. Two env overrides exist:

- TA_DATA_ROOT: redirect the whole data tree (tests point this at a tmp dir).
- TA_RUNS_DB:   override the SQLite run-store path directly.
"""
import os
import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent  # travel-assistant/


def slugify(text):
    """Same slug rule the scripts use: lowercase, non-alnum -> underscore."""
    s = re.sub(r"[^a-z0-9]+", "_", (text or "trip").strip().lower()).strip("_")
    return s or "trip"


def data_root():
    return Path(os.environ.get("TA_DATA_ROOT", PROJECT_DIR / "data"))


def raw_dir():
    return data_root() / "raw"


def analysis_dir():
    return data_root() / "analysis"


def maps_dir():
    return data_root() / "maps"


def runs_dir():
    return data_root() / "runs"


def runs_db_path():
    return Path(os.environ.get("TA_RUNS_DB", runs_dir() / "runs.db"))


def api_db_path():
    """Service-layer SQLite DB: API keys, usage metering, result cache.

    Kept separate from the runs DB on purpose: the runs store is the
    pipeline's durable record (issue #75); this DB is the API service's
    operational state (issue #80). Override with TA_API_DB.
    """
    return Path(os.environ.get("TA_API_DB", data_root() / "service" / "api.db"))


def scripts_dir():
    return PROJECT_DIR / "scripts"
