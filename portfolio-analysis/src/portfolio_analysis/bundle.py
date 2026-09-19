"""Canonical evidence artifacts. No model-generated facts or narratives."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from portfolio_analysis.events.base import Document, EventSource, VerifiedFact
from portfolio_analysis.http import atomic_json
from portfolio_analysis.moves import Move
from portfolio_analysis.naming import safe_ticker_component

SCHEMA_VERSION = 1
COLLECTOR_VERSION = 1


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def move_payload(move: Move) -> dict[str, object]:
    # Alpha is part of the payload: a move whose intercept changed is a
    # different move, so existing bundles hash-mismatch and surface as stale
    # rather than silently carrying the old decomposition.
    return {
        "return": move.ret,
        "benchmark": move.benchmark,
        "benchmark_return": move.benchmark_return,
        "beta": move.beta,
        "alpha": move.alpha,
        "abnormal_return": move.abnormal_return,
        "sigma_60": move.sigma_60,
        "z": move.z,
    }


def bundle_hash(bundle: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    payload["documents"] = sorted(payload["documents"], key=lambda doc: doc["doc_id"])
    payload["verified"] = sorted(payload["verified"], key=canonical)
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def build_bundle(
    move: Move,
    *,
    window: tuple[str, str],
    sources: Sequence[EventSource],
    news_coverage_start: str,
    source_status: Mapping[str, str],
    macro_coverage: Mapping[str, bool],
    collection_key: str,
) -> dict[str, Any]:
    documents: dict[str, Document] = {}
    facts: dict[str, VerifiedFact] = {}
    for source in sources:
        docs, verified = source.collect(move.ticker, *window)
        for doc in docs:
            if not window[0] <= doc.eastern_date <= window[1]:
                raise ValueError(f"{source.name}: document outside requested window")
            previous = documents.get(doc.doc_id)
            if previous and previous.as_dict() != doc.as_dict():
                raise ValueError("conflicting documents with the same doc_id")
            documents[doc.doc_id] = doc
        for fact in verified:
            facts[canonical(fact.as_dict())] = fact
    counts = Counter(doc.source for doc in documents.values())
    statuses = dict(source_status)
    statuses.update({source.name: getattr(source, "coverage_status", "ok") for source in sources})
    statuses["macro"] = "ok" if all(macro_coverage.values()) else "partial"
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "collection_key": collection_key,
        "ticker": move.ticker,
        "date": move.date,
        "move": move_payload(move),
        "verified": [fact.as_dict() for _, fact in sorted(facts.items())],
        "documents": [doc.as_dict() for doc in sorted(documents.values())],
        "coverage": {
            "window": list(window),
            "window_complete": True,
            "documents": len(documents),
            "documents_by_source": dict(sorted(counts.items())),
            "sources": sorted(source.name for source in sources),
            "source_status": statuses,
            "macro_calendar": dict(macro_coverage),
            "news_coverage_known_thin": move.date < news_coverage_start
            or counts.get("alphavantage_news", 0) < 5,
            "complete": all(status == "ok" for status in statuses.values()),
        },
    }
    payload["bundle_sha256"] = bundle_hash(payload)
    return payload


def write_bundle(directory: Path, bundle: dict[str, Any]) -> Path:
    ticker = safe_ticker_component(bundle["ticker"])
    day = date.fromisoformat(bundle["date"]).isoformat()
    if bundle_hash(bundle) != bundle["bundle_sha256"]:
        raise ValueError("bundle hash mismatch")
    target = directory / ticker / f"{day}.json"
    atomic_json(target, bundle)
    return target


def reusable(path: Path, collection_key: str) -> bool:
    if not path.exists():
        return False
    try:
        bundle = json.loads(path.read_text())
        return bool(
            bundle["schema_version"] == SCHEMA_VERSION
            and bundle["collection_key"] == collection_key
            and bundle["bundle_sha256"] == bundle_hash(bundle)
        )
    except (ValueError, KeyError, TypeError):
        return False
