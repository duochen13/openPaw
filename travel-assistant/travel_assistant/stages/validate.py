"""Validate stage: analyzer output must satisfy the places schema.

Wraps scripts/validate_places.py (unchanged). Raises ValueError listing every
violation instead of exiting — the orchestrator records the failure in the
run store.
"""
from . import ensure_scripts_on_path

ensure_scripts_on_path()
import validate_places as _vp


def validate_places(obj):
    """Returns (ok: bool, errors: list[str])."""
    return _vp.validate(obj)


def check(obj):
    """Validate or raise ValueError with the violations."""
    ok, errors = validate_places(obj)
    if not ok:
        raise ValueError("analysis INVALID:\n - " + "\n - ".join(errors))
    return True
