"""Source-pluggable collectors (issue #76).

Scraping any single source as a service is an existential risk, so the
collector must never be rednote-shaped: every source implements the
`Collector` interface and the pipeline treats them uniformly.

Collector protocol (same as the historical callable one in stages/collect.py):
    collector(destination, queries, n_per_query=6) -> raw_path (str)

Every collector writes the same raw file shape (whatever
scripts/collect_rednote.py writes), so downstream stages are untouched:

    {"destination", "slug", "source", "timestamp", "discussions": [...]}
    discussions[] = {"title", "url", "likes", "content", "comments"}

A `Collector` instance is itself callable, so it can be used wherever the
old plain-function protocol was accepted (e.g. research(collector=...)).

`Collector.source` ("rednote" / "websearch") is the per-place/run source
label. research() stamps it onto every place that does not already carry
one (see label_places); the run store persists it per place.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json

from . import paths

# Raw file shape every collector must emit (top-level and per-discussion keys).
RAW_TOP_KEYS = ("destination", "slug", "source", "timestamp", "discussions")
DISCUSSION_KEYS = ("title", "url", "likes", "content", "comments")


class Collector(ABC):
    """Abstract source collector.

    Subclasses set the `source` class attribute to their label and implement
    `collect`. Instances are callable with the same signature so they slot
    into the old callable protocol.
    """

    source = ""

    @abstractmethod
    def collect(self, destination, queries, n_per_query=6):
        """Collect raw discussions; return the raw JSON path (str)."""

    def __call__(self, destination, queries, n_per_query=6):
        return self.collect(destination, queries, n_per_query)

    def write_raw(self, destination, discussions):
        """Write discussions in the canonical raw shape. Returns the path."""
        slug = paths.slugify(destination)
        out_dir = paths.raw_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        sid = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"{slug}_{self.source}_{sid}.json"
        data = {
            "destination": destination,
            "slug": slug,
            "source": self.source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "discussions": discussions,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return str(path)


def _dedup_by_url(discussions):
    seen, out = set(), []
    for d in discussions:
        u = d.get("url")
        if u and u not in seen:
            seen.add(u)
            out.append(d)
    return out


class RednoteCollector(Collector):
    """Xiaohongshu collector (wraps scripts/collect_rednote.py).

    Needs the headless `browse` browser plus a logged-in xiaohongshu.com
    session (see SKILL.md); without a session it yields 0 posts, which the
    caller treats as a failed collect. The scripts/ import is lazy because
    that module probes the home directory for the browse binary at import
    time. scripts/collect_rednote.py keeps its own CLI and is unchanged.
    """

    source = "rednote"

    def collect(self, destination, queries, n_per_query=6):
        from .stages import ensure_scripts_on_path
        ensure_scripts_on_path()
        import collect_rednote as cr  # lazy: probes for browse binary
        return cr.collect(destination, list(queries), n_per_query)


class WebSearchCollector(Collector):
    """Web-search fallback collector — proves the abstraction with a second
    source and is the offline-capable option.

    `search` is an injectable backend so tests run with a fake and live use
    can plug in any search API:

        search(query: str, n: int) -> [{"title", "url", "snippet"?}, ...]

    The query passed to the backend is f"{destination} {query}".
    With no backend configured, collect() raises instead of emitting
    garbage — never silently produce empty/made-up results.
    """

    source = "websearch"

    def __init__(self, search=None):
        self.search = search

    def collect(self, destination, queries, n_per_query=6):
        if self.search is None:
            raise RuntimeError(
                "WebSearchCollector has no search backend configured: pass "
                "search=<callable(query, n) -> hits> (e.g. a web-search API "
                "client). Refusing to emit an empty/garbage raw file.")
        discussions = []
        for q in queries:
            hits = self.search(f"{destination} {q}", n_per_query) or []
            for h in hits[:n_per_query]:
                discussions.append({
                    "title": h.get("title", "") or "",
                    "url": h.get("url", "") or "",
                    "likes": 0,
                    "content": h.get("snippet", "") or "",
                    "comments": [],
                })
        discussions = _dedup_by_url(discussions)
        return self.write_raw(destination, discussions)


_COLLECTORS = {
    "rednote": RednoteCollector,
    "websearch": WebSearchCollector,
}


def collector_for(name):
    """Return the Collector class registered under `name`.

    Raises ValueError on unknown names (fail fast, never silently default).
    """
    try:
        return _COLLECTORS[name.lower()]
    except (KeyError, AttributeError):
        raise ValueError(
            f"unknown collector {name!r}; choose from "
            f"{sorted(_COLLECTORS)}")


def label_places(analysis, default_source):
    """Stamp per-place `source` labels the analyzer did not already emit.

    default_source is the label of the collector that produced the raw file
    (e.g. collector.source, or raw["source"]). Places already carrying a
    "source" key are left alone; with no default_source nothing changes.
    """
    if not default_source:
        return
    for p in analysis.get("places", []):
        p.setdefault("source", default_source)
