"""Timestamp handling for the point-in-time store.

Every fact carries four timestamps (spec §5.1). This module owns the one
derived from the others: known_at = observed_at + the source's latency budget.

Three deliberate refusals live here. Each one closes a failure that would be
silent, and a silent failure in this module produces a backtest that looks
excellent and is worthless:

  - An unknown source raises rather than defaulting to zero latency, because a
    zero default claims a signal was usable the instant it existed.
  - A negative budget raises, because a sign typo in config/run.yaml would
    otherwise make known_at precede observed_at - an unbounded time machine.
  - A naive datetime raises on BOTH serialization and parsing. `.astimezone()`
    on a naive value does not raise; it silently assumes system local time. That
    makes the result machine-dependent, and east of UTC it moves known_at
    earlier, admitting facts before they existed.

Canonical string form is fixed-width UTC with microseconds, so that
lexicographic comparison equals chronological comparison. The store compares
known_at as text, so that property is load-bearing. Anything written to a
timestamp column must come from `to_iso` - never from string concatenation,
which would produce a same-instant value that sorts differently.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

#: Canonical form: 'YYYY-MM-DDTHH:MM:SS.ffffff+00:00'. Fixed width, always UTC.
ISO_FORMAT_DESCRIPTION = "UTC ISO-8601 with microseconds, e.g. 2026-09-07T20:15:00.000000+00:00"


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
    budget = latency_budget_seconds[source]
    if budget < 0:
        raise ValueError(
            f"negative latency budget for {source!r}: {budget}. "
            "A fact cannot become usable before it was observed."
        )
    return observed_at + timedelta(seconds=budget)


def to_iso(dt: datetime) -> str:
    """Serialize to the canonical UTC string, which sorts lexicographically.

    Microsecond precision is fixed-width and lossless. Truncating to seconds
    would round known_at *earlier*, which is the leak direction.
    """
    if dt.tzinfo is None:
        raise ValueError("refusing to serialize a naive datetime")
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def parse_iso(text: str) -> datetime:
    """Parse a canonical string back to an aware UTC datetime.

    Refuses naive input. `datetime.fromisoformat` happily accepts an
    offset-less string, and `.astimezone()` would then assume system local
    time, so accepting one would make stored instants depend on the machine
    that read them.
    """
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError(
            f"refusing to parse a naive timestamp: {text!r}. "
            f"Expected {ISO_FORMAT_DESCRIPTION}."
        )
    return dt.astimezone(UTC)
