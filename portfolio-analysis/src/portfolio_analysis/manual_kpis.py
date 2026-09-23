"""Manually entered per-stock business KPIs (issues #36, #59).

EDGAR companyfacts (issue #29) cannot see everything: NOW's subscription
revenue (XBRL tag abandoned after 2014), META's daily active people (never
XBRL-tagged), GOOGL's search market share (no XBRL concept at all), and
NOW's seat-count proxies (issue #36) all live in earnings materials, not
filings. This module is the validated loader for
``config/kpi_manual.yaml``: hand-entered quarterly datapoints, each
carrying its own source and recording date.

Nothing here touches #29's EDGAR plumbing (``kpis.py`` /
``fundamentals.py``). Manual series are read at render time and merged
into the dashboard's Business metrics section after the EDGAR panels, each
carrying ``"source": "manual"`` so the template can label them. A metric
with no datapoints yet (e.g. GOOGL search share) renders as an "n/a"
placeholder panel - tracked but empty, never a crash.

Schema and validation follow the pattern established for issue #36
(PR #37): the RPO deceleration alert itself stays in that PR; this module
only loads and panels the manual series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from portfolio_analysis import kpis as kpis_module

#: Same project-root resolution as kpis.py (no wheel install; paths
#: resolve against the source checkout).
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "kpi_manual.yaml"

#: Display registry for manual metric keys. ``format`` follows the
#: template's vocabulary: "currency" (raw USD, $3.0B), "count" (plain
#: numbers, 3.56B people), "percent" (fraction, 0.9 -> 90%). A
#: percent-formatted metric gets its YoY in percentage points, like the
#: EDGAR margin panels. Keys not listed here still render - with a generic
#: label and "count" formatting - so the schema stays open for future
#: per-company metrics without a code change.
KNOWN_MANUAL_METRICS: dict[str, dict[str, str]] = {
    "subscription_revenue": {
        "label": "Subscription revenue",
        "format": "currency",
        "blurb": (
            "Quarterly subscription revenue, hand-entered from ServiceNow "
            "earnings releases (the us-gaap:SubscriptionRevenue XBRL tag "
            "was abandoned after 2014)."
        ),
    },
    "daily_active_people": {
        "label": "Daily active people",
        "format": "count",
        "blurb": (
            "Meta Family daily active people (DAP), hand-entered from Meta "
            "earnings releases. Not the legacy Facebook-only DAU."
        ),
    },
    "search_share": {
        "label": "Search market share",
        "format": "percent",
        "blurb": (
            "Google search market share - no stable provider or definition "
            "chosen yet; values pending."
        ),
    },
}


class ManualKpiError(ValueError):
    """config/kpi_manual.yaml is malformed."""


@dataclass(frozen=True)
class ManualPoint:
    """One hand-entered quarterly datapoint."""

    quarter: str  # quarter-end date, YYYY-MM-DD
    value: float
    source: str  # where the number came from - never empty
    date_recorded: str  # YYYY-MM-DD, when it was entered


@dataclass(frozen=True)
class ManualKpiConfig:
    """Validated contents of kpi_manual.yaml."""

    metrics: dict[str, dict[str, list[ManualPoint]]] = field(default_factory=dict)


def _parse_iso(value: Any, *, what: str, where: str) -> str:
    if not isinstance(value, str):
        raise ManualKpiError(f"{where}: {what} must be a YYYY-MM-DD string")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ManualKpiError(f"{where}: {what} {value!r} is not a valid date") from exc
    return value


def _parse_point(raw: Any, *, where: str) -> ManualPoint:
    if not isinstance(raw, dict):
        raise ManualKpiError(f"{where}: datapoint must be a mapping")
    quarter = _parse_iso(raw.get("quarter"), what="quarter", where=where)
    value = raw.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManualKpiError(f"{where}: value {value!r} must be a number")
    if not math.isfinite(value):
        raise ManualKpiError(f"{where}: value {value!r} must be finite")
    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ManualKpiError(f"{where}: source is required and must be non-empty")
    recorded = _parse_iso(raw.get("date_recorded"), what="date_recorded", where=where)
    return ManualPoint(
        quarter=quarter, value=float(value), source=source.strip(), date_recorded=recorded
    )


def load_manual_kpis(path: str | Path | None = None) -> ManualKpiConfig:
    """Validated manual KPIs from ``kpi_manual.yaml``.

    A missing file means "no manual data yet" - not an error - so a fresh
    checkout renders exactly like before. Anything structurally wrong
    raises ManualKpiError with the location. An empty datapoint list is
    allowed: it marks a tracked-but-unfilled metric (e.g. GOOGL search
    share) that renders as "n/a".
    """
    source = Path(path) if path else _CONFIG_PATH
    if not source.exists():
        return ManualKpiConfig()
    raw = yaml.safe_load(source.read_text())
    if raw is None:
        return ManualKpiConfig()
    if not isinstance(raw, dict):
        raise ManualKpiError(f"{source}: top level must be a mapping")
    metrics: dict[str, dict[str, list[ManualPoint]]] = {}
    block = raw.get("manual_kpis") or {}
    if not isinstance(block, dict):
        raise ManualKpiError(f"{source}: 'manual_kpis' must be a mapping")
    for ticker, per_metric in block.items():
        where_t = f"{source}: {ticker}"
        if not isinstance(per_metric, dict):
            raise ManualKpiError(f"{where_t}: must map metric keys to lists")
        parsed: dict[str, list[ManualPoint]] = {}
        for key, points in per_metric.items():
            where_m = f"{where_t}.{key}"
            if not isinstance(points, list):
                raise ManualKpiError(f"{where_m}: must be a list of datapoints")
            parsed_points = [_parse_point(p, where=f"{where_m}[{i}]") for i, p in enumerate(points)]
            seen: set[str] = set()
            for p in parsed_points:
                if p.quarter in seen:
                    raise ManualKpiError(f"{where_m}: duplicate quarter {p.quarter}")
                seen.add(p.quarter)
            parsed[str(key)] = sorted(parsed_points, key=lambda p: p.quarter)
        metrics[str(ticker).upper()] = parsed
    return ManualKpiConfig(metrics=metrics)


def _display_spec(key: str) -> dict[str, str]:
    if key in KNOWN_MANUAL_METRICS:
        return KNOWN_MANUAL_METRICS[key]
    return {
        "label": key.replace("_", " ").title(),
        "format": "count",
        "blurb": "Hand-entered metric (no display label configured).",
    }


def manual_kpi_panels(
    ticker_metrics: dict[str, list[ManualPoint]],
) -> list[dict[str, Any]]:
    """Render-ready panels for one ticker's manual metrics.

    Panel shape matches ``kpis.kpi_panels`` (quarters / values / YoY line /
    current / blurb) plus ``"source": "manual"`` and the latest point's
    source + recording date for the caption. Percent-formatted metrics get
    YoY in percentage points; counts and currency get fractional growth.
    A metric with no datapoints yields an ``"empty"`` panel so the
    template renders "n/a" instead of dropping the metric silently.
    """
    panels: list[dict[str, Any]] = []
    for key, points in ticker_metrics.items():
        spec = _display_spec(key)
        if not points:
            panels.append(
                {
                    "key": key,
                    "label": spec["label"],
                    "kind": "absolute",
                    "format": spec["format"],
                    "blurb": spec["blurb"],
                    "quarters": [],
                    "values": [],
                    "yoy": [],
                    "yoy_unit": "pp" if spec["format"] == "percent" else "pct",
                    "current": None,
                    "current_yoy": None,
                    "as_of": None,
                    "quarters_reported": 0,
                    "source": "manual",
                    "latest_source": None,
                    "latest_recorded": None,
                    "empty": True,
                }
            )
            continue
        series = [(p.quarter, p.date_recorded, p.value) for p in points]
        pp = spec["format"] == "percent"
        dated = kpis_module.with_yoy(series, pp=pp)
        quarters = [q for q, _, _ in dated]
        values = [v for _, v, _ in dated]
        yoy = [y for _, _, y in dated]
        latest = points[-1]
        panels.append(
            {
                "key": key,
                "label": spec["label"],
                "kind": "absolute",
                "format": spec["format"],
                "blurb": spec["blurb"],
                "quarters": quarters,
                "values": values,
                "yoy": yoy,
                "yoy_unit": "pp" if pp else "pct",
                "current": values[-1],
                "current_yoy": yoy[-1],
                "as_of": quarters[-1],
                "quarters_reported": len(quarters),
                "source": "manual",
                "latest_source": latest.source,
                "latest_recorded": latest.date_recorded,
                "empty": False,
            }
        )
    return panels
