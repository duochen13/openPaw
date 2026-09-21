"""The two kinds of evidence, kept as different types on purpose (spec §8).

A VerifiedFact is computed from a dated source: an 8-K was filed, earnings were
reported, the date was an FOMC day. A Document is something a source SAID.

The separation is the structural defense against post-hoc narrative fitting. In
Plan 3 the model is handed Documents and may cite them; it is never given the
ability to construct a VerifiedFact, so it cannot promote its own story into a
checkmark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

_TIMESTAMP_FORMATS = ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y-%m-%d")


def _parse_datetime(text: str) -> datetime:
    """First format that parses wins; nothing parsing is an error.

    Split out from parse_timestamp so the return type is a plain datetime.
    Folding this into the caller forces a `datetime | None` annotation that
    mypy --strict cannot narrow back across the try/except boundary, which
    costs three union-attr errors for no benefit.
    """
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable timestamp: {text!r}")


def parse_timestamp(raw: str) -> str:
    """Normalize a vendor timestamp to canonical UTC ISO-8601."""
    parsed = _parse_datetime(raw.strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


@dataclass(frozen=True, order=True)
class Document:
    """Something a source said, with a citable identity."""

    doc_id: str
    source: str = field(compare=False)
    published_at: str = field(compare=False)
    title: str = field(compare=False)
    url: str = field(compare=False)
    summary: str = field(compare=False, default="")
    relevance: float | None = field(compare=False, default=None)

    @classmethod
    def make(
        cls,
        *,
        source: str,
        native_id: str,
        published_at: str,
        title: str,
        url: str,
        summary: str = "",
        relevance: float | None = None,
    ) -> Document:
        return cls(
            doc_id=f"{source}:{native_id}",
            source=source,
            published_at=parse_timestamp(published_at),
            title=title,
            url=url,
            summary=summary,
            relevance=relevance,
        )

    @property
    def eastern_date(self) -> str:
        """The exchange-day this document belongs to."""
        return (datetime.fromisoformat(self.published_at).astimezone(EASTERN)).strftime("%Y-%m-%d")

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "published_at": self.published_at,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "relevance": self.relevance,
        }


@dataclass(frozen=True)
class VerifiedFact:
    """Computed from a dated source. Never written by a model."""

    key: str
    value: Any
    source: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError(
                f"VerifiedFact {self.key!r} has no source; an unsourced "
                "'verified' fact is just an assertion, which is exactly what "
                "this type exists to distinguish itself from"
            )

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source, "detail": self.detail}


class EventSource(Protocol):
    """One provider. Translation only."""

    name: str

    def collect(
        self, ticker: str, start: str, end: str
    ) -> tuple[list[Document], list[VerifiedFact]]: ...


def dated_fact_label(key: str, value: Any) -> tuple[str, str] | None:
    """(label, calendar date) for a verified fact that pins an event to a day.

    Returns None for fact kinds with no event date (not an error: most facts
    are contextual, not dated). Shared by the evidence-bundle renderer and
    the event-date catalog so both label the same fact the same way.
    """
    try:
        if key == "filing":
            return f"{value['form']} filing", str(value["filed"])
        if key == "earnings_reported":
            return "Quarterly earnings reported", str(value["reportedDate"])
        if key == "macro_release":
            return f"{value['release']} release", str(value["date"])
    except (KeyError, TypeError):
        return None
    return None


def utc_bounds(start: str, end: str) -> tuple[datetime, datetime]:
    """Inclusive Eastern dates as [start, next-midnight) UTC instants."""
    lo = datetime.combine(datetime.fromisoformat(start).date(), time(), EASTERN)
    hi = datetime.combine(datetime.fromisoformat(end).date() + timedelta(days=1), time(), EASTERN)
    return lo.astimezone(UTC), hi.astimezone(UTC)
