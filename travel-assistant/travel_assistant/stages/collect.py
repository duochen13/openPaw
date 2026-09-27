"""Collect stage: destination -> raw discussions file.

Collector protocol: a callable
    collector(destination, queries, n_per_query=6) -> raw_path (str)

See travel_assistant/collectors.py for the Collector interface (issue #76):
RednoteCollector (xiaohongshu, headless browser) and WebSearchCollector
(web-search fallback) both implement it. `collect_rednote` below is the
historical plain-function wrapper and now delegates to RednoteCollector.
"""
import json

from ..collectors import RednoteCollector


def collect_rednote(destination, queries, n_per_query=6):
    """Run the rednote headless-browser collector. Returns the raw JSON path.

    Needs a logged-in xiaohongshu.com session per SKILL.md, otherwise it
    yields 0 posts. The scripts/collect_rednote import inside the class is
    lazy because that module probes the home directory for the browse
    binary at import time.
    """
    return RednoteCollector().collect(destination, queries, n_per_query)


def load_raw(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw_summary(raw):
    ds = raw.get("discussions", [])
    return {"destination": raw.get("destination"),
            "source": raw.get("source"),
            "n_discussions": len(ds)}
