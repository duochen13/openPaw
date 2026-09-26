"""Pipeline stages: collect -> analyze -> validate -> geocode -> map.

Each stage module wraps the existing scripts/ code behind a stable function
interface instead of duplicating it. The scripts remain the source of truth
and keep working standalone.
"""
import sys

STAGE_NAMES = ("collect", "analyze", "validate", "geocode", "map")

_scripts_on_path = False


def ensure_scripts_on_path():
    """Make scripts/*.py importable (they live next to the package, not in it)."""
    global _scripts_on_path
    if not _scripts_on_path:
        from .. import paths
        sys.path.insert(0, str(paths.scripts_dir()))
        _scripts_on_path = True
