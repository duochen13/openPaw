"""Collect stage: destination -> raw discussions file.

Collector protocol: a callable
    collector(destination, queries, n_per_query=6) -> raw_path (str)

`collect_rednote` below wraps scripts/collect_rednote.py (headless browser;
needs a logged-in xiaohongshu.com session per SKILL.md, otherwise it yields
0 posts and the workflow falls back to WebSearch). The import is lazy because
collect_rednote scans the home directory for the browse binary at import time.

Issue #76 (source-pluggable collectors) will add fallback collectors behind
this same protocol; it is defined here so that work slots in without
changing the orchestrator.
"""
import json


def collect_rednote(destination, queries, n_per_query=6):
    """Run the rednote headless-browser collector. Returns the raw JSON path."""
    from . import ensure_scripts_on_path
    ensure_scripts_on_path()
    import collect_rednote as cr  # lazy: module import probes for browse binary
    return cr.collect(destination, list(queries), n_per_query)


def load_raw(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw_summary(raw):
    ds = raw.get("discussions", [])
    return {"destination": raw.get("destination"),
            "source": raw.get("source"),
            "n_discussions": len(ds)}
