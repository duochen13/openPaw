"""Checked-in CPI release prints: actual vs consensus, and move tagging.

The macro calendar (``events/macro.py``) knows *when* releases happen. This
module knows *what they printed*. The distinction matters for attribution:
a CPI date alone explains nothing — the surprise (actual minus consensus)
is what moves prices, so prints are stored as first-class checked-in data
in ``config/cpi_prints.yaml`` (collected by ``scripts/collect_cpi.py``
from BLS sources; see that script for provenance rules).

Schema of ``config/cpi_prints.yaml`` (JSON syntax, valid YAML)::

    {
      "schema_version": 1,
      "series": "CPI",
      "as_of": "2026-10-14",
      "source": "U.S. Bureau of Labor Statistics (BLS)",
      "notes": [...],
      "releases": [
        {
          "release_date": "2026-10-14",        # publication date (ET)
          "reference_period": "2026-09",       # month the data describes
          "release_time_et": "08:30",
          "url": "https://www.bls.gov/...",    # the release itself
          "metrics": {
            "headline_mom": {"actual": ..., "consensus": ..., "prior": ..., "revision": ...},
            "headline_yoy": {...},
            "core_mom": {...},
            "core_yoy": {...}
          }
        }
      ]
    }

Every metric field is a percent value or ``null``. ``consensus`` is null
unless a survey median was genuinely sourced for that release — it is
never estimated. ``prior`` is the previous published release's actual;
``revision`` is null unless BLS restated the print (the NSA series is
never revised; SA values change only at the annual factor recalculation).

Classification (issue #153): a flagged move on a CPI release day is
``macro-driven`` when the release carried a material surprise — the
largest absolute surprise across the four metrics is at least
``SURPRISE_THRESHOLD_PP`` percentage points — and no ticker-specific
dated event (earnings, SEC filing) shares the day; when both are present
it is ``mixed``. With no consensus there is no measurable surprise, so no
tag is applied: the print still attaches as context, the move is just not
attributed to it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

#: The four tracked prints per release. m/m is seasonally adjusted, y/y is
#: not — the pair BLS headlines and surveys quote.
METRIC_KEYS = ("headline_mom", "headline_yoy", "core_mom", "core_yoy")

#: Minimum |actual - consensus|, in percentage points, for a release to
#: count as a surprise. Prints are published to 0.1pp, so 0.1 is the
#: smallest measurable miss; anything below it is rounding, not signal.
SURPRISE_THRESHOLD_PP = 0.1


def _number(value: Any, *, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"CPI print {where} must be a number or null")
    return float(value)


@dataclass(frozen=True)
class CpiMetric:
    """One printed number and its context. All values are percents."""

    actual: float | None
    consensus: float | None
    prior: float | None
    revision: float | None

    @property
    def surprise(self) -> float | None:
        """Actual minus consensus in percentage points (None if either side
        is unknown). Rounded to 2dp: inputs carry 1dp, so the difference is
        exact at that precision and float dust must not leak into bundles."""
        if self.actual is None or self.consensus is None:
            return None
        return round(self.actual - self.consensus, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actual": self.actual,
            "consensus": self.consensus,
            "prior": self.prior,
            "revision": self.revision,
            "surprise": self.surprise,
        }


@dataclass(frozen=True)
class CpiPrint:
    """One CPI release: when it landed, what it described, what it printed."""

    release_date: str
    reference_period: str
    release_time_et: str
    url: str
    metrics: Mapping[str, CpiMetric]

    def surprises(self) -> dict[str, float]:
        """Metric -> surprise (pp) for every metric with a known consensus."""
        return {
            key: surprise
            for key, metric in self.metrics.items()
            if (surprise := metric.surprise) is not None
        }

    def max_abs_surprise(self) -> float | None:
        values = [abs(value) for value in self.surprises().values()]
        return max(values) if values else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "release_date": self.release_date,
            "reference_period": self.reference_period,
            "release_time_et": self.release_time_et,
            "url": self.url,
            "metrics": {key: self.metrics[key].as_dict() for key in METRIC_KEYS},
        }

    def fact_value(self) -> dict[str, Any]:
        """The VerifiedFact payload for this print (key ``macro_print``)."""
        return {
            "release": "CPI",
            "date": self.release_date,
            "reference_period": self.reference_period,
            "release_time_et": self.release_time_et,
            "url": self.url,
            "metrics": {key: self.metrics[key].as_dict() for key in METRIC_KEYS},
            "max_abs_surprise_pp": self.max_abs_surprise(),
        }


class CpiPrints:
    """Validated loader for the checked-in CPI prints file."""

    def __init__(self, path: Path) -> None:
        raw = path.read_text()
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported CPI prints schema")
        if data.get("series") != "CPI":
            raise ValueError("CPI prints file must declare series CPI")
        self.as_of: str = str(data.get("as_of") or "")
        self.source: str = str(data.get("source") or "")
        prints: dict[str, CpiPrint] = {}
        previous_date = ""
        for entry in data.get("releases") or []:
            print_ = self._parse_entry(entry)
            if print_.release_date <= previous_date:
                raise ValueError("CPI prints must be strictly increasing by release_date")
            previous_date = print_.release_date
            prints[print_.release_date] = print_
        if not prints:
            raise ValueError("CPI prints file has no releases")
        self._prints = prints

    @staticmethod
    def _parse_entry(entry: Any) -> CpiPrint:
        if not isinstance(entry, dict):
            raise ValueError("CPI print release must be an object")
        release_date = str(entry["release_date"])
        date.fromisoformat(release_date)
        reference = str(entry["reference_period"])
        if len(reference) != 7 or reference[4] != "-":
            raise ValueError(f"CPI print {release_date}: bad reference_period {reference!r}")
        date.fromisoformat(f"{reference}-01")
        url = str(entry["url"])
        if not url.startswith("https://"):
            raise ValueError(f"CPI print {release_date} requires a source URL")
        raw_metrics = entry["metrics"]
        if set(raw_metrics) != set(METRIC_KEYS):
            raise ValueError(
                f"CPI print {release_date} needs exactly the metrics {sorted(METRIC_KEYS)}"
            )
        metrics: dict[str, CpiMetric] = {}
        for key in METRIC_KEYS:
            raw = raw_metrics[key]
            if not isinstance(raw, dict):
                raise ValueError(f"CPI print {release_date} {key} must be an object")
            metrics[key] = CpiMetric(
                actual=_number(raw.get("actual"), where=f"{release_date} {key}.actual"),
                consensus=_number(raw.get("consensus"), where=f"{release_date} {key}.consensus"),
                prior=_number(raw.get("prior"), where=f"{release_date} {key}.prior"),
                revision=_number(raw.get("revision"), where=f"{release_date} {key}.revision"),
            )
        # The year-over-year prints are the release's headline numbers; a
        # release without them is not a CPI release. m/m may be null (the
        # shutdown-affected November 2025 release published no 1-month
        # change), y/y may not.
        for key in ("headline_yoy", "core_yoy"):
            if metrics[key].actual is None:
                raise ValueError(f"CPI print {release_date} is missing its {key} actual")
        return CpiPrint(
            release_date=release_date,
            reference_period=reference,
            release_time_et=str(entry.get("release_time_et") or "08:30"),
            url=url,
            metrics=metrics,
        )

    def on(self, release_date: str) -> CpiPrint | None:
        return self._prints.get(release_date)

    def between(self, start: str, end: str) -> list[CpiPrint]:
        return [print_ for day, print_ in sorted(self._prints.items()) if start <= day <= end]

    def __len__(self) -> int:
        return len(self._prints)


def classify_print(
    print_: CpiPrint, *, has_ticker_events: bool
) -> dict[str, Any] | None:
    """Tag a move that happened on this print's release day.

    Returns ``None`` when the release carried no material surprise (or no
    sourced consensus to measure one against): the print is context, not
    an attribution. Otherwise returns the classification payload stored in
    the evidence bundle as ``macro_classification``.
    """
    surprises = print_.surprises()
    max_abs = print_.max_abs_surprise()
    if max_abs is None or max_abs < SURPRISE_THRESHOLD_PP:
        return None
    return {
        "classification": "mixed" if has_ticker_events else "macro-driven",
        "release": "CPI",
        "release_date": print_.release_date,
        "reference_period": print_.reference_period,
        "release_time_et": print_.release_time_et,
        "url": print_.url,
        "surprises_pp": surprises,
        "max_abs_surprise_pp": max_abs,
        "prints": {key: print_.metrics[key].as_dict() for key in METRIC_KEYS},
        "ticker_events_same_day": has_ticker_events,
    }
