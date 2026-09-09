"""Dependency direction is one-way: ingest -> store -> features -> model -> evaluate.

A report or feature builder that can reach an ingest module can re-fetch live
data mid-render and quietly embed a value from the future. This test makes that
structurally impossible rather than a review convention.
"""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "stock_trading_bot"
DOWNSTREAM = ("features", "model", "evaluate", "report")
FORBIDDEN_PREFIX = "stock_trading_bot.ingest"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _downstream_files() -> list[Path]:
    return [p for pkg in DOWNSTREAM for p in (SRC / pkg).rglob("*.py")]


@pytest.mark.unit
def test_the_downstream_packages_exist_so_this_test_can_see_them():
    """A guard that scans nothing passes for the wrong reason."""
    for pkg in DOWNSTREAM:
        assert (SRC / pkg).is_dir(), f"{pkg} missing; this test would be vacuous"
    assert _downstream_files(), "no files to scan"


@pytest.mark.unit
def test_no_downstream_module_imports_ingest():
    offenders = [
        f"{path.relative_to(SRC)} imports {mod}"
        for path in _downstream_files()
        for mod in _imported_modules(path)
        if mod.startswith(FORBIDDEN_PREFIX)
    ]
    assert offenders == [], "dependency direction violated: " + "; ".join(offenders)


@pytest.mark.unit
def test_store_does_not_import_ingest():
    assert not any(
        mod.startswith(FORBIDDEN_PREFIX)
        for mod in _imported_modules(SRC / "store.py")
    )
