"""Timestamp handling for the point-in-time store.

Every fact carries four timestamps (spec §5.1). This module owns the one
derived from the others: known_at = observed_at + the source's latency budget.

Two deliberate refusals live here:
  - An unknown source raises rather than defaulting to zero latency, because a
    zero default silently claims a signal was available the instant it existed.
  - A naive datetime raises, because a timezone-less comparison against a UTC
    known_at is a leak waiting to happen.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping


def known_at_for(
    observed_at: datetime, source: str, latency_budget_seconds: Mapping[str, int]
) -> datetime:
    """Return when a fact observed at `observed_at` from `source` becomes usable."""
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    if source not in latency_budget_seconds:
        raise KeyError(
            f"no latency budget configured for source {source!r}; "
            "add one to config/run.yaml rather than assuming zero"
        )
    return observed_at + timedelta(seconds=latency_budget_seconds[source])


def to_iso(dt: datetime) -> str:
    """Serialize to a UTC ISO-8601 string that sorts lexicographically."""
    if dt.tzinfo is None:
        raise ValueError("refusing to serialize a naive datetime")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime:
    """Parse an ISO-8601 string back to an aware UTC datetime."""
    return datetime.fromisoformat(text).astimezone(timezone.utc)
