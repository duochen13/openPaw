"""Manually entered per-stock business KPIs (issue #36).

EDGAR companyfacts (issue #29) cannot see everything: NOW's seat-count
proxies - customers with >$1M ACV, current RPO, renewal / NRR - live in
earnings materials, not XBRL. This module is the validated loader for
``config/kpi_manual.yaml``: hand-entered quarterly datapoints, each
carrying its own source and recording date.

Nothing here touches #29's EDGAR plumbing (``kpis.py`` /
``fundamentals.py``). Manual series are read at render time and merged
into the dashboard's Business metrics section, each panel visibly labeled
"manual source".

Also home to the RPO deceleration alert: a flag computed off the *EDGAR*
NOW RPO YoY series. It fires when RPO YoY growth falls below
``yoy_floor`` or decelerates by more than ``pp_drop`` (percentage points)
versus the prior quarter. Both thresholds live in ``kpi_manual.yaml``
under ``alerts.rpo_deceleration`` so Daniel can tune them.
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

#: Defaults when the config file (or its alerts section) is absent.
DEFAULT_RPO_YOY_FLOOR = 0.21
DEFAULT_RPO_PP_DROP = 0.05

#: Display registry for manual metric keys. ``format`` follows the
#: template's vocabulary ("currency" / "percent") plus "count"; a
#: percent-formatted metric gets its YoY in percentage points, like the
#: EDGAR margin panels. Keys not listed here still render - with a generic
#: label and "count" formatting - so the schema stays open for CRM or new
#: proxies without a code change.
KNOWN_MANUAL_METRICS: dict[str, dict[str, str]] = {
    "customers_over_1m_acv": {
        "label": "Customers >$1M ACV",
        "format": "count",
        "blurb": (
            "Customers with more than $1M in annual contract value - "
            "the closest seat-count proxy NOW discloses. Hand-entered "
            "from earnings materials."
        ),
    },
    "crpo": {
        "label": "Current RPO",
        "format": "currency",
        "blurb": (
            "Current remaining performance obligation - the near-term "
            "slice of backlog. Hand-entered from earnings materials."
        ),
    },
    "renewal_rate": {
        "label": "Renewal rate",
        "format": "percent",
        "blurb": "Customer renewal rate, when disclosed. Hand-entered.",
    },
    "nrr": {
        "label": "Net revenue retention",
        "format": "percent",
        "blurb": "Net revenue retention, when disclosed. Hand-entered.",
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
    rpo_yoy_floor: float = DEFAULT_RPO_YOY_FLOOR  # fraction, e.g. 0.21
    rpo_pp_drop: float = DEFAULT_RPO_PP_DROP  # fraction, e.g. 0.05


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


def _parse_alerts(raw: Any, *, source: Path) -> tuple[float, float]:
    floor, drop = DEFAULT_RPO_YOY_FLOOR, DEFAULT_RPO_PP_DROP
    if raw is None:
        return floor, drop
    if not isinstance(raw, dict):
        raise ManualKpiError(f"{source}: 'alerts' must be a mapping")
    cfg = raw.get("rpo_deceleration")
    if cfg is None:
        return floor, drop
    if not isinstance(cfg, dict):
        raise ManualKpiError(f"{source}: alerts.rpo_deceleration must be a mapping")
    for key, default in (("yoy_floor_pct", floor * 100), ("pp_drop", drop * 100)):
        val = cfg.get(key, default)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ManualKpiError(f"{source}: alerts.rpo_deceleration.{key} must be a number")
        if not math.isfinite(val) or val <= 0:
            raise ManualKpiError(
                f"{source}: alerts.rpo_deceleration.{key} must be a positive number"
            )
        if key == "yoy_floor_pct":
            floor = float(val) / 100
        else:
            drop = float(val) / 100
    return floor, drop


def load_manual_kpis(path: str | Path | None = None) -> ManualKpiConfig:
    """Validated manual KPIs + RPO alert thresholds from ``kpi_manual.yaml``.

    A missing file means "no manual data yet" - not an error - so a fresh
    checkout renders exactly like before. Anything structurally wrong
    raises ManualKpiError with the location.
    """
    source = Path(path) if path else _CONFIG_PATH
    if not source.exists():
        return ManualKpiConfig()
    raw = yaml.safe_load(source.read_text())
    if raw is None:
        return ManualKpiConfig()
    if not isinstance(raw, dict):
        raise ManualKpiError(f"{source}: top level must be a mapping")
    floor, drop = _parse_alerts(raw.get("alerts"), source=source)
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
            if not isinstance(points, list) or not points:
                raise ManualKpiError(f"{where_m}: must be a non-empty list")
            seen: set[str] = set()
            parsed_points = [
                _parse_point(p, where=f"{where_m}[{i}]") for i, p in enumerate(points)
            ]
            for p in parsed_points:
                if p.quarter in seen:
                    raise ManualKpiError(f"{where_m}: duplicate quarter {p.quarter}")
                seen.add(p.quarter)
            parsed[str(key)] = sorted(parsed_points, key=lambda p: p.quarter)
        metrics[str(ticker).upper()] = parsed
    return ManualKpiConfig(metrics=metrics, rpo_yoy_floor=floor, rpo_pp_drop=drop)


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
    """
    panels = []
    for key, points in ticker_metrics.items():
        spec = _display_spec(key)
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
            }
        )
    return panels


def rpo_deceleration_flag(
    rpo_series: list[tuple[str, str, float]],
    *,
    yoy_floor: float = DEFAULT_RPO_YOY_FLOOR,
    pp_drop: float = DEFAULT_RPO_PP_DROP,
) -> dict[str, Any]:
    """Flag for NOW's RPO growth decelerating (issue #36).

    Fires when the latest RPO YoY growth is *below* ``yoy_floor`` or has
    fallen by *more than* ``pp_drop`` (fraction of 1, i.e. percentage
    points / 100) versus the prior quarter's YoY. Boundary values do not
    fire. A missing latest YoY (short history or a gap) is "not enough
    data", never a flag.
    """
    dated = kpis_module.with_yoy(rpo_series)
    current_yoy = dated[-1][2] if dated else None
    prev_yoy: float | None = None
    for _, _, y in reversed(dated[:-1]):
        if y is not None:
            prev_yoy = y
            break
    result: dict[str, Any] = {
        "flagged": False,
        "reason": None,
        "current_yoy": current_yoy,
        "prev_yoy": prev_yoy,
        "yoy_floor": yoy_floor,
        "pp_drop": pp_drop,
    }
    if current_yoy is None:
        result["reason"] = "not enough RPO history for a YoY read"
        return result
    reasons = []
    if current_yoy < yoy_floor:
        reasons.append(
            f"RPO YoY growth {current_yoy * 100:.1f}% is below the "
            f"{yoy_floor * 100:.1f}% floor"
        )
    if prev_yoy is not None and prev_yoy - current_yoy > pp_drop:
        reasons.append(
            f"RPO YoY decelerated {(prev_yoy - current_yoy) * 100:.1f}pp "
            "vs the prior quarter"
        )
    if reasons:
        result["flagged"] = True
        result["reason"] = "; ".join(reasons)
    return result
