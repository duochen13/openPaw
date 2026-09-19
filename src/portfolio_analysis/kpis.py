"""Per-stock business KPIs from SEC EDGAR companyfacts (issue #29).

Price factors (beta/alpha/P/E) describe *how* a stock moves; these quarterly
operating metrics explain *why* the business is worth owning. The fetch and
XBRL-parsing plumbing is shared with issue #28 (fundamentals.py); this
module adds the metric registry, the ticker->metrics config, and the
quarterly-series builders (absolute, margin, YoY).

Metric keys are the config vocabulary (config/kpi_metrics.yaml maps ticker
-> keys). The XBRL details behind each key live here in METRIC_DEFS, next
to the unit tests, because a wrong tag silently produces wrong numbers -
that knowledge does not belong in a YAML file.

Data reality, measured 2026-09-19 against EDGAR companyfacts:
- Revenue merges two tags by recency: filers rename the revenue concept
  over time (NOW's quarterly ``Revenues`` stops in 2018 while
  ``RevenueFromContractWithCustomerExcludingAssessedTax`` continues).
- Capex is cash-flow style: only YTD figures are filed, so quarters are
  de-accumulated (see fundamentals._parse_ytd_quarters). The filer sign
  convention is unreliable - META and NOW tag capex positive (the
  statement presents it as an outflow, so other filers may tag it
  negative) - so values are normalized with abs() to read as positive
  spend under either convention.
- RPO (remaining performance obligation) is balance-sheet style: a
  point-in-time fact keyed by quarter end.
- Not available in companyfacts, hence not definable here: segment
  revenue (no dimensional breakdowns), DAU/MAU (not XBRL-tagged), TSLA
  deliveries (not in XBRL), NOW subscription revenue (tag abandoned
  after 2014), META/GOOGL gross profit (not tagged).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from portfolio_analysis import fundamentals

#: Same project-root resolution as config.py (this project does not
#: support a wheel install; paths resolve against the source checkout).
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "kpi_metrics.yaml"

#: (taxonomy, tag, unit) candidates for total revenue, most-preferred last
#: in the recency merge - parse_quarterly_fact prefers the tag with the
#: latest coverage per quarter.
_REVENUE_SOURCES = [
    ("us-gaap", "Revenues", "USD"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
    ("us-gaap", "SalesRevenueNet", "USD"),
]

#: Metric registry: key -> definition. ``kind`` is "absolute" (currency
#: bars, e.g. revenue) or "margin" (percent bars derived as
#: numerator/denominator, e.g. operating margin). ``yoy`` selects the
#: growth line: percent change for absolute metrics, percentage-point
#: change for margins.
METRIC_DEFS: dict[str, dict[str, Any]] = {
    "revenue": {
        "label": "Revenue",
        "kind": "absolute",
        "format": "currency",
        "period": "quarter",
        "sources": _REVENUE_SOURCES,
        "yoy": True,
        "blurb": "Quarterly revenue as XBRL-tagged in 10-Q/10-K filings.",
    },
    "gross_margin": {
        "label": "Gross margin",
        "kind": "margin",
        "format": "percent",
        "period": "quarter",
        "numerator": [("us-gaap", "GrossProfit", "USD")],
        "denominator": _REVENUE_SOURCES,
        "yoy": True,
        "blurb": "Gross profit / revenue. Not tagged by every filer.",
    },
    "operating_margin": {
        "label": "Operating margin",
        "kind": "margin",
        "format": "percent",
        "period": "quarter",
        "numerator": [("us-gaap", "OperatingIncomeLoss", "USD")],
        "denominator": _REVENUE_SOURCES,
        "yoy": True,
        "blurb": "Operating income / revenue.",
    },
    "capex": {
        "label": "Capex",
        "kind": "absolute",
        "format": "currency",
        "period": "ytd",
        "sources": [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD")],
        "magnitude": True,
        "yoy": True,
        "blurb": "Quarterly capex de-accumulated from YTD cash-flow statements.",
    },
    "rpo": {
        "label": "Remaining performance obligation",
        "kind": "absolute",
        "format": "currency",
        "period": "instant",
        "sources": [("us-gaap", "RevenueRemainingPerformanceObligation", "USD")],
        "yoy": True,
        "blurb": "Contracted revenue not yet recognized; backlog proxy.",
    },
}

#: Year-ago comparison must be ~4 quarters back, not merely 4 rows back:
#: with a missing quarter in the middle, the 4th row back is two years ago.
_YOY_DAYS = (340, 390)


class ConfigError(ValueError):
    """kpi_metrics.yaml is malformed or names an unknown metric."""


def load_kpi_config(path: str | Path | None = None) -> dict[str, list[str]]:
    """Ticker -> ordered metric keys from ``kpi_metrics.yaml``.

    Unknown metric keys fail loudly: a typo in config must not silently
    drop a panel. Tickers are uppercased; the order of metrics is the
    display order.
    """
    source = Path(path) if path else _CONFIG_PATH
    try:
        raw = yaml.safe_load(source.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(f"KPI config not found: {source}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("kpis"), dict):
        raise ConfigError(f"{source} must define a top-level 'kpis' mapping")
    out: dict[str, list[str]] = {}
    for ticker, keys in raw["kpis"].items():
        if not isinstance(keys, list) or not keys:
            raise ConfigError(f"{source}: {ticker!r} must list at least one metric")
        for key in keys:
            if key not in METRIC_DEFS:
                raise ConfigError(
                    f"{source}: unknown metric {key!r} for {ticker!r}; "
                    f"known: {sorted(METRIC_DEFS)}"
                )
        out[str(ticker).upper()] = [str(k) for k in keys]
    return out


def _as_magnitude(
    series: list[tuple[str, str, float]], magnitude: bool
) -> list[tuple[str, str, float]]:
    if not magnitude:
        return series
    return [(q, f, abs(v)) for q, f, v in series]


def build_kpi_series(
    facts: dict[str, Any], metric_keys: list[str]
) -> dict[str, list[tuple[str, str, float]]]:
    """``metric key -> [(quarter_end, filed, value)]`` for the requested keys.

    Metrics with no EDGAR data are omitted from the result (not empty
    series): the renderer hides metrics it cannot back with real numbers,
    the same "no made-up numbers" rule the factor panels keep.
    """
    out: dict[str, list[tuple[str, str, float]]] = {}
    revenue_cache: list[tuple[str, str, float]] | None = None
    for key in metric_keys:
        spec = METRIC_DEFS[key]
        if spec["kind"] == "margin":
            num = fundamentals.parse_quarterly_fact(
                facts, spec["numerator"], period=spec["period"]
            )
            if revenue_cache is None:
                revenue_cache = fundamentals.parse_quarterly_fact(
                    facts, spec["denominator"], period=spec["period"]
                )
            den = {q: (f, v) for q, f, v in revenue_cache}
            joined = []
            for q, f, v in num:
                if q in den and den[q][1]:
                    # The quarter is known once both filings exist.
                    filed = max(f, den[q][0])
                    joined.append((q, filed, v / den[q][1]))
            if joined:
                out[key] = joined
        else:
            series = fundamentals.parse_quarterly_fact(
                facts, spec["sources"], period=spec["period"]
            )
            series = _as_magnitude(series, spec.get("magnitude", False))
            if series:
                out[key] = series
    return out


def with_yoy(
    series: list[tuple[str, str, float]], *, pp: bool = False
) -> list[tuple[str, float, float | None]]:
    """``[(quarter, value, yoy)]`` oldest first; ``yoy`` is None without a year-ago.

    ``pp=True`` reports the year-ago change in percentage points (for
    margins); otherwise it is a fractional change. A missing year-ago
    quarter - or one outside the ~4-quarter window - is a gap, never an
    interpolated guess.
    """
    ends = [date.fromisoformat(q) for q, _, _ in series]
    out: list[tuple[str, float, float | None]] = []
    for i, (q, _filed, v) in enumerate(series):
        yoy: float | None = None
        if i >= 4:
            gap = (ends[i] - ends[i - 4]).days
            if _YOY_DAYS[0] <= gap <= _YOY_DAYS[1]:
                base = series[i - 4][2]
                if pp:
                    yoy = v - base  # pp change is defined even from a zero base
                elif base:
                    yoy = (v - base) / abs(base)
        out.append((q, v, yoy))
    return out


def kpi_panels(
    series_by_metric: dict[str, list[tuple[str, str, float]]],
    metric_order: list[str] | None = None,
) -> dict[str, Any] | None:
    """Render-ready KPI panels, or None when nothing has data.

    Each panel carries quarterly bars (``quarters``/``values``) plus the
    YoY growth line (``yoy``; percentage points for margins), the latest
    quarter's value and YoY, and the quarter count. The template renders
    panels in ``metric_order`` (the config order) and skips the section
    entirely when this returns None.
    """
    order = metric_order or list(series_by_metric)
    panels = []
    for key in order:
        series = series_by_metric.get(key)
        if not series:
            continue
        spec = METRIC_DEFS[key]
        pp = spec["kind"] == "margin"
        dated = with_yoy(series, pp=pp)
        quarters = [q for q, _, _ in dated]
        values = [v for _, v, _ in dated]
        yoy = [y for _, _, y in dated]
        panels.append(
            {
                "key": key,
                "label": spec["label"],
                "kind": spec["kind"],
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
            }
        )
    if not panels:
        return None
    return {"metrics": panels}
