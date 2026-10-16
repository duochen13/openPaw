"""Checked-in macro release prints: actual vs consensus, and move tagging.

The macro calendar (``events/macro.py``) knows *when* releases happen. This
module knows *what they printed*. The distinction matters for attribution:
a release date alone explains nothing — the surprise (actual minus
consensus) is what moves prices, so prints are stored as first-class
checked-in data, one file per series, collected from BLS sources (see
``scripts/collect_cpi.py`` / ``scripts/collect_ppi.py`` for provenance):

- ``config/cpi_prints.yaml`` — CPI (issue #153)
- ``config/ppi_prints.yaml`` — PPI (issue #155)

Both files share one schema (JSON syntax, valid YAML)::

    {
      "schema_version": 1,
      "series": "CPI",                          # or "PPI"
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
            ...
          }
        }
      ]
    }

The metric keys are per-series. CPI tracks ``headline_mom``,
``headline_yoy``, ``core_mom``, ``core_yoy`` (all-items and all-items less
food & energy). PPI tracks ``final_demand_mom``, ``final_demand_yoy``,
``core_mom``, ``core_yoy`` (final demand and final demand less foods &
energy). m/m is seasonally adjusted, y/y is not — the pair BLS headlines
and surveys quote.

Every metric field is a percent value or ``null``. ``consensus`` is null
unless a survey median was genuinely sourced for that release — it is
never estimated. ``prior`` is the previous published release's actual;
``revision`` is null unless the source restated the print in a way this
file records (see each file's notes: the CPI NSA series is never revised,
while PPI values are revised for four months — the files keep the
as-printed vintage regardless).

Classification (issues #153/#155): a flagged move on a release day is
``macro-driven`` when the release carried a material surprise — the
largest absolute surprise across the series' metrics is at least
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

#: The four tracked CPI prints per release.
METRIC_KEYS = ("headline_mom", "headline_yoy", "core_mom", "core_yoy")

#: The four tracked PPI prints per release (final demand; core = final
#: demand less foods and energy). Same shape as CPI, different aggregate.
PPI_METRIC_KEYS = ("final_demand_mom", "final_demand_yoy", "core_mom", "core_yoy")

#: Per-series loader contract: the series name the file must declare, the
#: exact metric keys each release carries, and the y/y actuals a release
#: must have to be that release at all (m/m may be null — the
#: shutdown-affected November 2025 CPI release published no 1-month
#: change — y/y may not).
_SERIES_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "CPI": (METRIC_KEYS, ("headline_yoy", "core_yoy")),
    "PPI": (PPI_METRIC_KEYS, ("final_demand_yoy", "core_yoy")),
}

#: Minimum |actual - consensus|, in percentage points, for a release to
#: count as a surprise. Prints are published to 0.1pp, so 0.1 is the
#: smallest measurable miss; anything below it is rounding, not signal.
SURPRISE_THRESHOLD_PP = 0.1


def _number(value: Any, *, series: str, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{series} print {where} must be a number or null")
    return float(value)


@dataclass(frozen=True)
class ReleaseMetric:
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


#: CPI name kept from issue #153; the metric shape is series-independent.
CpiMetric = ReleaseMetric


@dataclass(frozen=True)
class ReleasePrint:
    """One macro release: when it landed, what it described, what it printed."""

    release_date: str
    reference_period: str
    release_time_et: str
    url: str
    metrics: Mapping[str, ReleaseMetric]
    series: str = "CPI"

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
            "metrics": {key: self.metrics[key].as_dict() for key in self.metrics},
        }

    def fact_value(self) -> dict[str, Any]:
        """The VerifiedFact payload for this print (key ``macro_print``)."""
        return {
            "release": self.series,
            "date": self.release_date,
            "reference_period": self.reference_period,
            "release_time_et": self.release_time_et,
            "url": self.url,
            "metrics": {key: self.metrics[key].as_dict() for key in self.metrics},
            "max_abs_surprise_pp": self.max_abs_surprise(),
        }


@dataclass(frozen=True)
class CpiPrint(ReleasePrint):
    """A CPI release print (issue #153)."""

    series: str = "CPI"


@dataclass(frozen=True)
class PpiPrint(ReleasePrint):
    """A PPI release print (issue #155)."""

    series: str = "PPI"


class ReleasePrints:
    """Validated loader for a checked-in prints file of one series."""

    def __init__(self, path: Path, *, series: str) -> None:
        if series not in _SERIES_SPECS:
            raise ValueError(f"unknown macro print series {series!r}")
        self.series = series
        metric_keys, required_actuals = _SERIES_SPECS[series]
        self._metric_keys = metric_keys
        self._required_actuals = required_actuals
        raw = path.read_text()
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError(f"unsupported {series} prints schema")
        if data.get("series") != series:
            raise ValueError(f"{series} prints file must declare series {series}")
        self.as_of: str = str(data.get("as_of") or "")
        self.source: str = str(data.get("source") or "")
        prints: dict[str, ReleasePrint] = {}
        previous_date = ""
        for entry in data.get("releases") or []:
            print_ = self._parse_entry(entry)
            if print_.release_date <= previous_date:
                raise ValueError(f"{series} prints must be strictly increasing by release_date")
            previous_date = print_.release_date
            prints[print_.release_date] = print_
        if not prints:
            raise ValueError(f"{series} prints file has no releases")
        self._prints = prints

    def _parse_entry(self, entry: Any) -> ReleasePrint:
        series = self.series
        if not isinstance(entry, dict):
            raise ValueError(f"{series} print release must be an object")
        release_date = str(entry["release_date"])
        date.fromisoformat(release_date)
        reference = str(entry["reference_period"])
        if len(reference) != 7 or reference[4] != "-":
            raise ValueError(f"{series} print {release_date}: bad reference_period {reference!r}")
        date.fromisoformat(f"{reference}-01")
        url = str(entry["url"])
        if not url.startswith("https://"):
            raise ValueError(f"{series} print {release_date} requires a source URL")
        raw_metrics = entry["metrics"]
        if set(raw_metrics) != set(self._metric_keys):
            raise ValueError(
                f"{series} print {release_date} needs exactly the metrics "
                f"{sorted(self._metric_keys)}"
            )
        metrics: dict[str, ReleaseMetric] = {}
        for key in self._metric_keys:
            raw = raw_metrics[key]
            if not isinstance(raw, dict):
                raise ValueError(f"{series} print {release_date} {key} must be an object")
            fields = {
                field: _number(
                    raw.get(field), series=series, where=f"{release_date} {key}.{field}"
                )
                for field in ("actual", "consensus", "prior", "revision")
            }
            metrics[key] = ReleaseMetric(**fields)
        # The year-over-year prints are the release's headline numbers; a
        # release without them is not a release of this series. m/m may be
        # null (the shutdown-affected November 2025 CPI release published
        # no 1-month change), y/y may not.
        for key in self._required_actuals:
            if metrics[key].actual is None:
                raise ValueError(f"{series} print {release_date} is missing its {key} actual")
        print_type = CpiPrint if series == "CPI" else PpiPrint
        return print_type(
            release_date=release_date,
            reference_period=reference,
            release_time_et=str(entry.get("release_time_et") or "08:30"),
            url=url,
            metrics=metrics,
        )

    def on(self, release_date: str) -> ReleasePrint | None:
        return self._prints.get(release_date)

    def between(self, start: str, end: str) -> list[ReleasePrint]:
        return [print_ for day, print_ in sorted(self._prints.items()) if start <= day <= end]

    def __len__(self) -> int:
        return len(self._prints)


class CpiPrints(ReleasePrints):
    """Validated loader for the checked-in CPI prints file (issue #153)."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, series="CPI")


class PpiPrints(ReleasePrints):
    """Validated loader for the checked-in PPI prints file (issue #155)."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, series="PPI")


def classify_print(
    print_: ReleasePrint, *, has_ticker_events: bool
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
        "release": print_.series,
        "release_date": print_.release_date,
        "reference_period": print_.reference_period,
        "release_time_et": print_.release_time_et,
        "url": print_.url,
        "surprises_pp": surprises,
        "max_abs_surprise_pp": max_abs,
        "prints": {key: print_.metrics[key].as_dict() for key in print_.metrics},
        "ticker_events_same_day": has_ticker_events,
    }
