"""AI trade dashboard: the AI slowdown watch's 8-panel chart as a tab
in the portfolio dashboard (issue #163).

One self-contained offline page rendering the watcher's combined-metrics
chart natively (no embedded PNG, no build/view-time fetching):

1. Inflation - CPI vs PPI (y/y %)
2. Rates - the discount rate (2Y / 10Y Treasury)
3. Hyperscaler capex (Big-3) - SEC EDGAR, quarterly
4. Credit stress - HY spreads (left) vs distressed loan volume (right)
5. CoreWeave - equity (left) vs its cost of debt (right)
6. Compute economics - H100 spot rent (left) vs lab revenue scale (right)
7. CDS - 5Y spreads (bp), reported snapshots only
8. Hyperscaler cloud - segment revenue & y/y growth (issue #174)

Data discipline (mirrors the Insight page, PR #38): every series is a
dated snapshot vendored into ``data/ai_trade/`` from the watcher
workspace, with a per-series source note (``series_notes.csv``) and
per-point sources for the sparse series (``snapshots.csv``,
``cds_snapshots.csv``). CDS prints are press-reported levels with the
print date and press source on every row - there is no continuous CDS
history, and no projection is ever drawn on Panel 7. The only forward
segments anywhere are the source chart's own: mechanical trend dashes
(captioned as extrapolations, never forecasts) and Panel 6's stated
expectations, which live in ``snapshots.csv`` as ``kind=expectation``
rows, restricted to Panel 6, and render dashed only.

Panel 8 is the one exception to the vendoring rule: it reads the
Insight page's ``data/insight/cloud_revenue.csv`` (Section D, issue
#174) through that module's own validated loader, so the two
dashboards share one source of truth. The panel appears only when
that CSV sits in the sibling data dir, and - like Panel 7 - it never
draws a projection: reported segment points only.
"""

# The embedded HTML/SVG is intentionally kept in one readable template
# string so the page renders offline with no build step.
# ruff: noqa: E501

from __future__ import annotations

import csv
import html
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from portfolio_analysis.insight_dashboard import InsightDataError, load_cloud_revenue

#: Repo-root data dir (same convention as insight_dashboard.DATA_DIR).
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ai_trade"

#: Panel 8 vendor order + line colors (same as Insight Section D).
CLOUD_VENDORS = (
    ("GOOGL", "#1f6feb"),
    ("AMZN", "#d97706"),
    ("MSFT", "#16a34a"),
)
#: series_notes.csv keys for Panel 8's plotted series, per vendor.
CLOUD_NOTE_KEYS = {
    "GOOGL": "cloud_googl",
    "AMZN": "cloud_amzn",
    "MSFT": "cloud_msft",
}

MONTHLY_COLUMNS = [
    "cpi_yoy",
    "ppi_yoy",
    "dgs2",
    "dgs10",
    "hy_oas",
    "crwv",
    "nvda",
    "capex_q",
]
_SNAPSHOT_REQUIRED = {"panel", "series", "date", "value", "unit", "kind", "source", "note"}
_CDS_REQUIRED = {"ticker", "date", "spread_bps", "source", "note"}
_NOTES_REQUIRED = {"series", "panel", "source", "as_of", "note"}
_KINDS = {"reported", "derived", "expectation"}
#: Stated expectations exist only on Panel 6 of the source chart, and only
#: for these two series. An expectation row anywhere else is a data error.
EXPECTATION_SERIES = {"anthropic_arr", "openai_runrate"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

X_START = date(2022, 1, 1)
PROJ_END = date(2027, 3, 31)  # source chart's projection horizon
ORCL_WATCH_BP = 250.0

_CDS_COLORS = {"CRWV": "#6c3483", "ORCL": "#c0392b", "META": "#2e86c1", "NVDA": "#7f8c8d"}
_CDS_LABELS = {
    "CRWV": "CRWV 5Y CDS, bp (reported points: \u2265800 Jul-26; 1,117 Oct-14)",
    "ORCL": "ORCL 5Y CDS, bp (227 Sep-24 \u2192 288 Oct-15, record)",
    "META": "META 5Y CDS, bp (~100 Sep-29 \u2192 104 Oct-15)",
    "NVDA": "NVDA 5Y CDS, bp (84 ~Oct-10 \u2192 90 Oct-15)",
}


class TradeDataError(ValueError):
    """A data/ai_trade CSV is malformed."""


@dataclass(frozen=True)
class SnapshotPoint:
    """One sparse reported/derived point, or a Panel 6 stated expectation."""

    panel: int
    series: str
    date: str  # YYYY-MM-DD
    value: float
    unit: str
    kind: str  # reported | derived | expectation
    source: str
    note: str


@dataclass(frozen=True)
class CdsPrint:
    """One dated, press-reported 5Y CDS level. Never a projection."""

    ticker: str
    date: str  # YYYY-MM-DD
    spread_bps: float
    source: str
    note: str


@dataclass(frozen=True)
class SeriesNote:
    series: str
    panel: int
    source: str
    as_of: str  # YYYY-MM-DD
    note: str


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError as exc:
        raise TradeDataError(f"ai-trade data not found: {path}") from exc
    if not rows:
        raise TradeDataError(f"{path}: no data rows")
    missing = required - set(rows[0].keys())
    if missing:
        raise TradeDataError(f"{path}: missing columns {sorted(missing)}")
    return rows


def _parse_date(raw: str, *, where: str) -> str:
    raw = raw.strip()
    if not _DATE_RE.match(raw):
        raise TradeDataError(f"{where}: date {raw!r} must be YYYY-MM-DD")
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise TradeDataError(f"{where}: date {raw!r} is not a real date") from exc
    return raw


def _parse_amount(raw: str, *, where: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise TradeDataError(f"{where}: {raw!r} is not a number") from exc
    if value < 0:
        raise TradeDataError(f"{where}: negative amount {raw!r}")
    return value


def load_monthly(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Monthly panel series: one row per month-end, values or None.

    Columns: cpi_yoy / ppi_yoy (Panels 1), dgs2 / dgs10 (2), capex_q (3,
    quarterly values on quarter-end rows), hy_oas (4), crwv / nvda (5).
    """
    path = (data_dir or DATA_DIR) / "monthly.csv"
    rows = []
    prev = ""
    for i, r in enumerate(_read_csv(path, {"date", *MONTHLY_COLUMNS}), 1):
        where = f"{path}:{i}"
        d = _parse_date(r["date"], where=where)
        if d <= prev:
            raise TradeDataError(f"{where}: dates must be strictly increasing")
        prev = d
        row: dict[str, Any] = {"date": d}
        for col in MONTHLY_COLUMNS:
            raw = r[col].strip()
            row[col] = _parse_amount(raw, where=where) if raw else None
        rows.append(row)
    return rows


def load_snapshots(data_dir: Path | None = None) -> list[SnapshotPoint]:
    """Sparse points for Panels 4R / 5R / 6, each with its own source.

    The expectation rule: ``kind=expectation`` rows are stated
    expectations, not data - they are only allowed on Panel 6 for the
    two lab run-rate series, and they render dashed only.
    """
    path = (data_dir or DATA_DIR) / "snapshots.csv"
    points = []
    for i, r in enumerate(_read_csv(path, _SNAPSHOT_REQUIRED), 1):
        where = f"{path}:{i}"
        try:
            panel = int(r["panel"])
        except ValueError as exc:
            raise TradeDataError(f"{where}: panel {r['panel']!r} is not an integer") from exc
        if not 1 <= panel <= 7:
            raise TradeDataError(f"{where}: panel {panel} out of range 1-7")
        kind = r["kind"].strip().lower()
        if kind not in _KINDS:
            raise TradeDataError(f"{where}: kind {r['kind']!r} not in {sorted(_KINDS)}")
        series = r["series"].strip()
        if kind == "expectation" and (panel != 6 or series not in EXPECTATION_SERIES):
            raise TradeDataError(
                f"{where}: expectation rows are Panel 6 lab run-rates only, not {series!r}"
            )
        if not r["source"].strip():
            raise TradeDataError(f"{where}: every point needs a source")
        if not r["unit"].strip():
            raise TradeDataError(f"{where}: every point needs a unit")
        points.append(
            SnapshotPoint(
                panel=panel,
                series=series,
                date=_parse_date(r["date"], where=where),
                value=_parse_amount(r["value"], where=where),
                unit=r["unit"].strip(),
                kind=kind,
                source=r["source"].strip(),
                note=r["note"].strip(),
            )
        )
    points.sort(key=lambda p: (p.panel, p.series, p.date))
    return points


def load_cds(data_dir: Path | None = None) -> list[CdsPrint]:
    """Panel 7 prints: dated, press-sourced 5Y CDS levels, nothing else.

    There is deliberately no kind/status column here: every row is a
    reported print with a date and a press source. A projection or an
    estimate cannot be represented in this file.
    """
    path = (data_dir or DATA_DIR) / "cds_snapshots.csv"
    prints = []
    for i, r in enumerate(_read_csv(path, _CDS_REQUIRED), 1):
        where = f"{path}:{i}"
        if not r["ticker"].strip():
            raise TradeDataError(f"{where}: ticker is required")
        if not r["source"].strip():
            raise TradeDataError(f"{where}: every CDS print needs a press source")
        spread = _parse_amount(r["spread_bps"], where=where)
        if spread <= 0:
            raise TradeDataError(f"{where}: spread_bps must be positive")
        prints.append(
            CdsPrint(
                ticker=r["ticker"].strip().upper(),
                date=_parse_date(r["date"], where=where),
                spread_bps=spread,
                source=r["source"].strip(),
                note=r["note"].strip(),
            )
        )
    prints.sort(key=lambda p: (p.date, p.ticker))
    return prints


def load_series_notes(data_dir: Path | None = None) -> dict[str, SeriesNote]:
    """Per-series provenance: source + as-of date for every plotted series."""
    path = (data_dir or DATA_DIR) / "series_notes.csv"
    notes: dict[str, SeriesNote] = {}
    for i, r in enumerate(_read_csv(path, _NOTES_REQUIRED), 1):
        where = f"{path}:{i}"
        series = r["series"].strip()
        if not series:
            raise TradeDataError(f"{where}: series is required")
        if series in notes:
            raise TradeDataError(f"{where}: duplicate note for series {series!r}")
        if not r["source"].strip():
            raise TradeDataError(f"{where}: series {series!r} without a source")
        try:
            panel = int(r["panel"])
        except ValueError as exc:
            raise TradeDataError(f"{where}: panel {r['panel']!r} is not an integer") from exc
        notes[series] = SeriesNote(
            series=series,
            panel=panel,
            source=r["source"].strip(),
            as_of=_parse_date(r["as_of"], where=where),
            note=r["note"].strip(),
        )
    return notes


def _quarter_start(quarter: str) -> str:
    """ "2021-Q1" -> "2021-01-01" (Panel 8 points sit at quarter starts). """
    return f"{quarter[:4]}-{(int(quarter[6]) - 1) * 3 + 1:02d}-01"


def _shift_quarter(quarter: str, quarters: int) -> str:
    idx = int(quarter[:4]) * 4 + int(quarter[6]) - 1 + quarters
    return f"{idx // 4:04d}-Q{idx % 4 + 1}"


def load_cloud_panel(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Panel 8 series from the Insight page's cloud_revenue.csv.

    Additive, mirroring the Insight page's own Section D rule: when
    the sibling ``data/insight/cloud_revenue.csv`` is absent the tab
    keeps its original seven panels. A present-but-malformed CSV
    raises (the insight loader's validation, re-raised as
    TradeDataError). YoY is computed here from the chained quarterly
    revenue, exactly as ``insight_dashboard_data`` computes it for
    Section D - never stored.
    """
    insight_dir = (data_dir or DATA_DIR).parent / "insight"
    if not (insight_dir / "cloud_revenue.csv").exists():
        return []
    try:
        rows = load_cloud_revenue(insight_dir)
    except InsightDataError as exc:
        raise TradeDataError(f"cloud panel: {exc}") from exc
    by_vendor: dict[str, dict[str, Any]] = {}
    for r in rows:
        entry = by_vendor.setdefault(
            r.vendor, {"vendor": r.vendor, "segment": r.segment, "by_quarter": {}}
        )
        entry["by_quarter"][r.quarter] = r.revenue
    out = []
    for vendor, _color in CLOUD_VENDORS:
        entry = by_vendor.get(vendor)
        if entry is None:
            continue
        by_quarter = entry["by_quarter"]
        revenue_pts: list[tuple[str, float]] = []
        growth_pts: list[tuple[str, float]] = []
        for quarter in sorted(by_quarter):
            day = _quarter_start(quarter)
            revenue_pts.append((day, by_quarter[quarter]))
            year_ago = by_quarter.get(_shift_quarter(quarter, -4))
            if year_ago:
                growth_pts.append(
                    (day, 100.0 * (by_quarter[quarter] / year_ago - 1))
                )
        out.append(
            {
                "vendor": vendor,
                "segment": entry["segment"],
                "revenue": revenue_pts,
                "growth": growth_pts,
            }
        )
    return out


#: Microsoft chained y/y cells that straddle the FY2025 segment
#: redefinition (new-basis quarters against old-basis year-ago
#: quarters) - asterisked in the Panel 8 table, explained in its note.
CLOUD_TABLE_STAR_MSFT = {"2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2"}


def _date_quarter(day: str) -> str:
    """ "2021-01-01" -> "2021-Q1" (Panel 8 points sit at quarter starts). """
    return f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"


def _cloud_panel(cloud: list[dict[str, Any]]) -> dict[str, Any]:
    """Panel 8 assembled: two quarter-axis line charts in one block -
    quarterly segment revenue, then its y/y growth - plus the full
    quarterly y/y table (the growth series as numbers, not just a line)."""
    colors = dict(CLOUD_VENDORS)
    rev_series, growth_series = [], []
    growth_by_vendor: dict[str, dict[str, float]] = {}
    for s in cloud:
        color = colors[s["vendor"]]
        rev_series.append(
            _series(
                f"{s['segment']} segment revenue, $B (company earnings releases)",
                color,
                "l",
                s["revenue"],
                end_label=f"${s['revenue'][-1][1]:.1f}B",
            )
        )
        growth_series.append(
            _series(
                f"{s['segment']} revenue y/y % (computed from the chained quarterly revenue)",
                color,
                "l",
                s["growth"],
                end_label=f"{s['growth'][-1][1]:+.0f}%",
            )
        )
        growth_by_vendor[s["vendor"]] = {
            _date_quarter(d): v for d, v in s["growth"]
        }
    quarters = sorted(
        {q for by_q in growth_by_vendor.values() for q in by_q},
    )
    table_rows = []
    for q in quarters:
        cells = []
        for s in cloud:
            v = growth_by_vendor[s["vendor"]].get(q)
            cells.append((v, s["vendor"] == "MSFT" and q in CLOUD_TABLE_STAR_MSFT))
        table_rows.append({"quarter": q, "cells": cells})
    return {
        "kind": "cloud",
        "title": "8 \u00b7 Hyperscaler cloud \u2014 segment revenue & y/y growth (reported points only; no projection)",
        "caption": (
            "Points only - reported segment revenue, no projection, no interpolation. "
            "Microsoft is plotted on its Intelligent Cloud segment in both charts: Microsoft "
            "does not disclose Azure revenue in dollars, so Azure is never a plotted series "
            "(Azure and other cloud services grew +43% y/y in Q2 2026, Microsoft FY26 Q4 - a "
            "growth rate, given here as text only). Microsoft quarters are calendar-aligned "
            "(fiscal Q3 = calendar Q1). Microsoft redefined the Intelligent Cloud segment in "
            "FY2025: quarters from Sep 2024 are as reported under the new composition, so the "
            "near-zero chained y/y prints that follow in 2025 H1 are definitional, not a "
            "revenue decline (the affected table cells, 2024-Q3 to 2025-Q2, are asterisked). "
            "Data: data/insight/cloud_revenue.csv, shared with the Insight "
            "page's Section D - one source of truth for both dashboards."
        ),
        "charts": [
            {
                "y_left": "USD B per quarter",
                "aria": "Hyperscaler cloud segment revenue by quarter",
                "caption": "Quarterly cloud segment revenue, USD billions, calendar quarters; points sit at quarter starts.",
                "series": rev_series,
            },
            {
                "y_left": "y/y %",
                "aria": "Hyperscaler cloud segment revenue growth, year over year",
                "caption": "Year-over-year growth computed from the chained quarterly revenue - never stored. Lines start 2021-Q1: the 2020 quarters in the CSV are the y/y base year.",
                "series": growth_series,
            },
        ],
        "table": {
            "columns": [s["segment"] for s in cloud],
            "rows": table_rows,
        },
    }


# ---------------------------------------------------------------------------
# Projections - the source chart's own, replicated exactly. Mechanical
# trend extrapolations of the recent segment; NOT forecasts.


def _trend_proj(
    points: list[tuple[str, float]], k: int, floor: float | None = None
) -> list[tuple[str, float]] | None:
    """Linear fit on the last k points; segment from the last actual point
    to PROJ_END (the source chart's trend_proj, numpy-free)."""
    if len(points) < 3:
        return None
    tail = points[-k:]
    d0 = date.fromisoformat(tail[0][0])
    xs = [(date.fromisoformat(d) - d0).days for d, _ in tail]
    ys = [v for _, v in tail]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    intercept = my - slope * mx
    end_val = intercept + slope * (PROJ_END - d0).days
    if floor is not None:
        end_val = max(end_val, floor)
    return [(points[-1][0], points[-1][1]), (PROJ_END.isoformat(), end_val)]


def _capex_proj(points: list[tuple[str, float]]) -> list[tuple[str, float]] | None:
    """Panel 3 projection: extend the average QoQ step of the last two
    steps to 2026-12-31 and 2027-03-31 (the source chart's rule)."""
    if len(points) < 3:
        return None
    slope = (points[-1][1] - points[-3][1]) / 2.0
    last_d, last_v = points[-1]
    return [
        (last_d, last_v),
        ("2026-12-31", last_v + slope),
        ("2027-03-31", last_v + 2 * slope),
    ]


# ---------------------------------------------------------------------------
# Panel assembly


def _series(
    label: str,
    color: str,
    axis: str,
    points: list[tuple[str, float]],
    *,
    style: str = "line",
    marker: str = "circle",
    proj: list[tuple[str, float]] | None = None,
    end_label: str | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "color": color,
        "axis": axis,
        "points": points,
        "style": style,  # line | dash | markers
        "marker": marker,  # circle | square | triangle | diamond
        "proj": proj,
        "end_label": end_label,
    }


def ai_trade_data(data_dir: Path | None = None) -> dict[str, Any]:
    """Validated snapshot data assembled into the render-ready panels:
    the seven vendored panels, plus Panel 8 when the shared Insight
    cloud CSV sits in the sibling data dir."""
    monthly = load_monthly(data_dir)
    snapshots = load_snapshots(data_dir)
    cds = load_cds(data_dir)
    notes = load_series_notes(data_dir)

    def col(name: str) -> list[tuple[str, float]]:
        return [(r["date"], r[name]) for r in monthly if r[name] is not None]

    def snap(series: str, kinds: set[str]) -> list[tuple[str, float]]:
        return [
            (p.date, p.value) for p in snapshots if p.series == series and p.kind in kinds
        ]

    # Provenance rule: every plotted series carries a source note.
    plotted = set(MONTHLY_COLUMNS) | {p.series for p in snapshots}
    missing = plotted - set(notes)
    if missing:
        raise TradeDataError(f"series_notes.csv: no source note for {sorted(missing)}")

    panels: list[dict[str, Any]] = [
        {
            "title": "1 \u00b7 Inflation \u2014 CPI vs PPI (y/y %)",
            "y_left": "y/y %",
            "y_right": None,
            "caption": "BLS, by reference month. Dashed: mechanical trend of the last 8 prints \u2014 an extrapolation, not a forecast.",
            "series": [
                _series("CPI y/y % (BLS, reference month)", "#c0392b", "l", col("cpi_yoy"),
                        proj=_trend_proj(col("cpi_yoy"), 8)),
                _series("PPI final demand y/y % (BLS)", "#7d3c98", "l", col("ppi_yoy"),
                        proj=_trend_proj(col("ppi_yoy"), 8)),
            ],
        },
        {
            "title": "2 \u00b7 Rates \u2014 the discount rate",
            "y_left": "%",
            "y_right": None,
            "caption": "FRED daily yields, monthly mean. Dashed: mechanical trend of the last 6 months \u2014 an extrapolation, not a forecast.",
            "series": [
                _series("10Y Treasury % (FRED DGS10, monthly avg)", "#1a5276", "l", col("dgs10"),
                        proj=_trend_proj(col("dgs10"), 6)),
                _series("2Y Treasury % (FRED DGS2)", "#2e86c1", "l", col("dgs2"),
                        proj=_trend_proj(col("dgs2"), 6)),
            ],
        },
        {
            "title": "3 \u00b7 Hyperscaler capex (Big-3) \u2014 still accelerating",
            "y_left": "$B per quarter",
            "y_right": None,
            "caption": "SEC EDGAR cash-flow capex, YTD-differenced to quarters. AMZN excluded \u2014 its EDGAR capex tag series ends in 2017. Dashed: the last-two-steps average QoQ step extended \u2014 an extrapolation, not guidance.",
            "series": [
                _series("Big-3 capex per quarter, $B (SEC EDGAR: MSFT+GOOGL+META; AMZN excluded, tag ends 2017)",
                        "#117864", "l", col("capex_q"), proj=_capex_proj(col("capex_q"))),
            ],
        },
        {
            "title": "4 \u00b7 Credit stress \u2014 spreads (left) vs distressed loan volume (right)",
            "y_left": "spread %",
            "y_right": "$B",
            "caption": "Left: US high-yield option-adjusted spread (FRED), dashed trend of the last 6 months. Right: JPMorgan reported snapshots only, dashed because four snapshots are not a continuous series \u2014 no projection is drawn on them.",
            "series": [
                _series("US high-yield spread (option-adjusted spread), % (FRED)", "#b9770e", "l",
                        col("hy_oas"), proj=_trend_proj(col("hy_oas"), 6)),
                _series("Distressed loans \u226480\u00a2, $B (JPMorgan snapshots; Dec-22 derived; no projection \u2014 too few points)",
                        "#c0392b", "r", snap("distressed_le80", {"reported", "derived"}),
                        style="dash", marker="square"),
                _series("Deep distress <60\u00a2, $B (JPMorgan)", "#78281f", "r",
                        snap("distressed_lt60", {"reported", "derived"}),
                        style="dash", marker="triangle"),
            ],
        },
        {
            "title": "5 \u00b7 CoreWeave \u2014 equity (left) vs its cost of debt (right)",
            "y_left": "$",
            "y_right": "debt cost %",
            "y_right_fixed": (0.0, 20.0),
            "caption": "Monthly closes (Yahoo). The red diamonds are dated financing prints \u2014 markers only, no line is drawn between financing events. Dashed: mechanical trends of the last 6 months \u2014 extrapolations, not forecasts.",
            "series": [
                _series("CRWV share price, $ (monthly close)", "#6c3483", "l", col("crwv"),
                        proj=_trend_proj(col("crwv"), 6, floor=1.0)),
                _series("NVDA share price, $ (monthly close, scale ref)", "#aeb6bf", "l", col("nvda"),
                        proj=_trend_proj(col("nvda"), 6, floor=1.0)),
                _series("CRWV marginal debt cost: 9.75% new issue (Apr/Oct-26) \u2192 ~15% 2032 secondary (Oct-26)",
                        "#c0392b", "r", snap("crwv_debt_cost", {"reported"}),
                        style="markers", marker="diamond"),
            ],
        },
        {
            "title": "6 \u00b7 Compute economics \u2014 unit rent (left) vs lab revenue scale (right)",
            "y_left": "$/GPU-hr",
            "y_right": "run-rate $B",
            "caption": "Left: H100 spot rent from reported index points, dashed trend of the last 4 points. Right: reported run-rate points (solid); the dashed segments are stated expectations \u2014 OpenAI \u2265$70B annualized by YE2026 per the company, Anthropic $100\u2013120B investor expectation (midpoint plotted) \u2014 expectations, not data.",
            "series": [
                _series("H100 spot rent, $/GPU-hr (Silicon Data / Ornn OCPI points)", "#117a65", "l",
                        snap("h100_spot", {"reported"}),
                        proj=_trend_proj(snap("h100_spot", {"reported"}), 4, floor=0.5)),
                _series("Anthropic ARR run-rate, $B (reported points)", "#b9770e", "r",
                        snap("anthropic_arr", {"reported"}), marker="square",
                        proj=_expectation_proj(snapshots, "anthropic_arr")),
                _series("Anthropic projection: investor-expected YE2026 $100\u2013120B (midpoint shown)",
                        "#b9770e", "r", [], style="dash", marker="square"),
                _series("OpenAI revenue run-rate, $B (reported points, net basis)", "#2874a6", "r",
                        snap("openai_runrate", {"reported"}), marker="triangle",
                        proj=_expectation_proj(snapshots, "openai_runrate")),
                _series("OpenAI projection: company-expected \u2265$70B annualized by YE2026",
                        "#2874a6", "r", [], style="dash", marker="triangle"),
            ],
        },
    ]

    by_ticker: dict[str, list[CdsPrint]] = {}
    for p in cds:
        by_ticker.setdefault(p.ticker, []).append(p)
    cds_series = []
    for ticker in ("CRWV", "ORCL", "META", "NVDA"):
        pts = by_ticker.get(ticker)
        if not pts:
            continue
        cds_series.append(
            _series(
                _CDS_LABELS[ticker],
                _CDS_COLORS[ticker],
                "l",
                [(p.date, p.spread_bps) for p in pts],
                marker="square" if ticker in ("META", "NVDA") else "circle",
                end_label=f"{pts[-1].spread_bps:,.0f}" if ticker in ("CRWV", "ORCL") else None,
            )
        )
    panels.append(
        {
            "title": "7 \u00b7 CDS \u2014 5-year credit default swap spreads (bp, reported snapshots only; no projection)",
            "y_left": "bp",
            "y_right": None,
            "y_left_fixed": (0.0, 1250.0),
            "hline": {
                "value": ORCL_WATCH_BP,
                "color": "#c0392b",
                "label": "ORCL watch alert line ~250bp",
            },
            "caption": "Dated press-reported prints only (Reuters / S&P Global / LSEG via press and the watch logs). CDS has no free continuous history, so nothing is interpolated into a claim of one \u2014 and no projection is drawn on this panel, ever.",
            "series": cds_series,
        }
    )

    cloud = load_cloud_panel(data_dir)
    if cloud:
        # Same provenance rule as every other plotted series.
        missing_cloud = {CLOUD_NOTE_KEYS[s["vendor"]] for s in cloud} - set(notes)
        if missing_cloud:
            raise TradeDataError(
                f"series_notes.csv: no source note for {sorted(missing_cloud)}"
            )
        panels.append(_cloud_panel(cloud))

    return {
        "panels": panels,
        "cds": [
            {
                "ticker": p.ticker,
                "date": p.date,
                "spread_bps": p.spread_bps,
                "source": p.source,
                "note": p.note,
            }
            for p in cds
        ],
        "notes": [notes[s] for s in sorted(notes, key=lambda s: (notes[s].panel, s))],
        "asof": max(n.as_of for n in notes.values()) if notes else "",
    }


def _expectation_proj(
    snapshots: list[SnapshotPoint], series: str
) -> list[tuple[str, float]] | None:
    """Dashed segment from the last reported point to the stated
    expectation point (Panel 6 only; the loader enforces that)."""
    reported = [(p.date, p.value) for p in snapshots if p.series == series and p.kind == "reported"]
    expected = [(p.date, p.value) for p in snapshots if p.series == series and p.kind == "expectation"]
    if not reported or not expected:
        return None
    return [reported[-1], max(expected)]



# ---------------------------------------------------------------------------
# SVG charts (server-rendered from the snapshot data; line charts only)


def _nice_ticks(vmin: float, vmax: float, target: int = 5) -> tuple[list[float], float, float]:
    span = vmax - vmin
    if span <= 0:
        span = abs(vmax) or 1.0
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10) if m * mag >= raw)
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    ticks = []
    t = lo
    while t <= hi + 1e-9:
        ticks.append(round(t, 6))
        t += step
    return ticks, lo, hi


def _domain(values: list[float], fixed: tuple[float, float] | None) -> tuple[list[float], float, float]:
    if fixed is not None:
        lo, hi = fixed
        step = (hi - lo) / 5
        return [lo + i * step for i in range(6)], lo, hi
    if not values:
        return [0.0, 1.0], 0.0, 1.0
    vmin, vmax = min(values), max(values)
    pad = 0.06 * (vmax - vmin or abs(vmax) or 1.0)
    lo, hi = vmin - pad, vmax + pad
    if vmin >= 0:
        lo = max(0.0, lo)
    return _nice_ticks(lo, hi)


def _marker(x: float, y: float, shape: str, color: str, r: float, title: str) -> str:
    t = f"<title>{html.escape(title)}</title>"
    if shape == "square":
        return f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r:.1f}" height="{2 * r:.1f}" fill="{color}">{t}</rect>'
    if shape == "triangle":
        pts = f"{x:.1f},{y - r - 1:.1f} {x - r - 1:.1f},{y + r:.1f} {x + r + 1:.1f},{y + r:.1f}"
        return f'<polygon points="{pts}" fill="{color}">{t}</polygon>'
    if shape == "diamond":
        pts = f"{x:.1f},{y - r - 2:.1f} {x + r + 2:.1f},{y:.1f} {x:.1f},{y + r + 2:.1f} {x - r - 2:.1f},{y:.1f}"
        return f'<polygon points="{pts}" fill="{color}">{t}</polygon>'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}">{t}</circle>'


def _svg_panel(panel: dict[str, Any]) -> str:
    W, H = 1000, 300
    dual = panel.get("y_right") is not None
    pad_l, pad_r, pad_t, pad_b = 58, (58 if dual else 20), 18, 28
    x0 = date(2022, 1, 1).toordinal()
    x1 = PROJ_END.toordinal()

    def x(d: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (date.fromisoformat(d).toordinal() - x0) / (x1 - x0)

    def values(axis: str) -> list[float]:
        out: list[float] = []
        for s in panel["series"]:
            if s["axis"] == axis:
                out += [v for _, v in s["points"]]
                out += [v for _, v in s["proj"] or []]
        return out

    lticks, llo, lhi = _domain(values("l"), panel.get("y_left_fixed"))
    rticks, rlo, rhi = _domain(values("r"), panel.get("y_right_fixed")) if dual else ([], 0.0, 1.0)

    def yl(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - (v - llo) / (lhi - llo))

    def yr(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - (v - rlo) / (rhi - rlo))

    esc = html.escape
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(panel["title"])}">']
    for t in lticks:
        parts.append(
            f'<line x1="{pad_l}" y1="{yl(t):.1f}" x2="{W - pad_r}" y2="{yl(t):.1f}" stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{yl(t) + 4:.1f}" text-anchor="end" font-size="12" fill="#65685f">{t:,.1f}</text>'
        )
    if dual:
        for t in rticks:
            parts.append(
                f'<text x="{W - pad_r + 8}" y="{yr(t) + 4:.1f}" font-size="12" fill="#65685f">{t:,.1f}</text>'
            )
    parts.append(
        f'<text x="{pad_l}" y="11" font-size="11" fill="#65685f">{esc(panel["y_left"] or "")}</text>'
    )
    if dual:
        parts.append(
            f'<text x="{W - pad_r}" y="11" text-anchor="end" font-size="11" fill="#65685f">{esc(panel["y_right"] or "")}</text>'
        )
    for yr_ in range(2022, 2028):
        xd = x(f"{yr_}-01-01")
        if pad_l <= xd <= W - pad_r:
            parts.append(
                f'<line x1="{xd:.1f}" y1="{H - pad_b}" x2="{xd:.1f}" y2="{H - pad_b + 5}" stroke="#c9cabf" stroke-width="1"/>'
                f'<text x="{xd:.1f}" y="{H - pad_b + 20:.1f}" text-anchor="middle" font-size="12" fill="#65685f">{yr_}</text>'
            )
    hline = panel.get("hline")
    if hline:
        yv = yl(hline["value"])
        parts.append(
            f'<line x1="{pad_l}" y1="{yv:.1f}" x2="{W - pad_r}" y2="{yv:.1f}" stroke="{hline["color"]}" stroke-width="1.2" stroke-dasharray="2,3" opacity="0.7"/>'
            f'<text x="{pad_l + 6}" y="{yv - 6:.1f}" font-size="12" fill="{hline["color"]}">{esc(hline["label"])}</text>'
        )
    for s in panel["series"]:
        if not s["points"] and not s["proj"]:
            continue  # legend-only entry (Panel 6 expectation labels)
        yf = yl if s["axis"] == "l" else yr
        color = s["color"]
        if s["proj"]:
            pts = " ".join(f"{x(d):.1f},{yf(v):.1f}" for d, v in s["proj"])
            parts.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="7,5" opacity="0.5"/>'
            )
        if s["points"] and s["style"] != "markers":
            pts = " ".join(f"{x(d):.1f},{yf(v):.1f}" for d, v in s["points"])
            dash = ' stroke-dasharray="7,5"' if s["style"] == "dash" else ""
            parts.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2"{dash}/>'
            )
        if s["points"]:
            r = 2.0 if len(s["points"]) > 24 else 3.4
            for d, v in s["points"]:
                parts.append(_marker(x(d), yf(v), s["marker"], color, r, f"{s['label']} \u00b7 {d}: {v:,.2f}"))
        if s["end_label"] and s["points"]:
            d, v = s["points"][-1]
            parts.append(
                f'<text x="{x(d) + 9:.1f}" y="{yf(v) + 4:.1f}" font-size="13" font-weight="700" fill="{color}">{esc(s["end_label"])}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _legend_html(panel: dict[str, Any]) -> str:
    items = []
    for s in panel["series"]:
        if s["style"] == "markers":
            sw = f'<i class="dm" style="background:{s["color"]}"></i>'
        else:
            dash = "border-top-style:dashed" if s["style"] == "dash" or (s.get("proj") and not s["points"]) else ""
            sw = f'<i class="ln" style="border-color:{s["color"]};{dash}"></i>'
        items.append(f'<span class="lg">{sw}{html.escape(s["label"])}</span>')
    return '<div class="legend">' + "".join(items) + "</div>"


def _svg_quarter_chart(chart: dict[str, Any]) -> str:
    """One Panel 8 chart: quarterly points on a calendar axis spanning
    exactly the plotted data (revenue from 2020, growth from 2021).

    Panels 1-7 share the 2022-to-projection-horizon axis of the source
    chart; Panel 8 has no projection and no shared axis to inherit, so
    its axis is the data's own span - nothing is extrapolated into the
    empty space a shared axis would leave.
    """
    W, H = 1000, 300
    pad_l, pad_r, pad_t, pad_b = 58, 30, 18, 28
    all_points = [p for s in chart["series"] for p in s["points"]]
    xs = [date.fromisoformat(d).toordinal() for d, _ in all_points]
    x0, x1 = min(xs), max(xs)
    span = max(x1 - x0, 1)

    def x(d: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (date.fromisoformat(d).toordinal() - x0) / span

    ticks, lo, hi = _domain([v for _, v in all_points], None)

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    esc = html.escape
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(chart["aria"])}">']
    for t in ticks:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(t):.1f}" x2="{W - pad_r}" y2="{y(t):.1f}" stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{y(t) + 4:.1f}" text-anchor="end" font-size="12" fill="#65685f">{t:,.1f}</text>'
        )
    parts.append(
        f'<text x="{pad_l}" y="11" font-size="11" fill="#65685f">{esc(chart["y_left"] or "")}</text>'
    )
    for yr_ in range(date.fromordinal(x0).year, date.fromordinal(x1).year + 1):
        o = date(yr_, 1, 1).toordinal()
        if x0 <= o <= x1:
            xd = pad_l + (W - pad_l - pad_r) * (o - x0) / span
            parts.append(
                f'<line x1="{xd:.1f}" y1="{H - pad_b}" x2="{xd:.1f}" y2="{H - pad_b + 5}" stroke="#c9cabf" stroke-width="1"/>'
                f'<text x="{xd:.1f}" y="{H - pad_b + 20:.1f}" text-anchor="middle" font-size="12" fill="#65685f">{yr_}</text>'
            )
    end_labels: list[tuple[float, str, str, float]] = []
    for s in chart["series"]:
        if not s["points"]:
            continue
        color = s["color"]
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in s["points"])
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        r = 2.0 if len(s["points"]) > 24 else 3.4
        for d, v in s["points"]:
            parts.append(_marker(x(d), y(v), s["marker"], color, r, f"{s['label']} \u00b7 {d}: {v:,.2f}"))
        if s["end_label"]:
            d, v = s["points"][-1]
            end_labels.append((y(v) - 12, s["end_label"], color, x(d)))
    # End labels share the right edge: push overlapping ones apart.
    end_labels.sort(key=lambda t: t[0])
    for j in range(1, len(end_labels)):
        ly, text, color, lx = end_labels[j]
        if ly < end_labels[j - 1][0] + 16:
            end_labels[j] = (end_labels[j - 1][0] + 16, text, color, lx)
    for ly, text, color, lx in end_labels:
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="end" font-size="13" font-weight="700" fill="{color}">{esc(text)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _cloud_table_html(table: dict[str, Any]) -> str:
    """Panel 8's data table: the growth series as numbers - one row
    per quarter, segment y/y % to one decimal. Asterisked cells are
    the Microsoft prints chained across the FY2025 redefinition."""
    head = "".join(f"<th>{html.escape(c)} y/y %</th>" for c in table["columns"])
    trs = []
    for row in table["rows"]:
        tds = []
        for value, starred in row["cells"]:
            if value is None:
                tds.append("<td>\u2014</td>")
            else:
                tds.append(f"<td>{value:+.1f}{'*' if starred else ''}</td>")
        trs.append(
            f"<tr><td>{html.escape(row['quarter'])}</td>" + "".join(tds) + "</tr>"
        )
    return (
        '<table class="src"><tr><th>Quarter</th>' + head + "</tr>"
        + "".join(trs) + "</table>"
    )


def _cloud_block_html(panel: dict[str, Any]) -> str:
    parts = [
        '<div class="chart-block"><h2>' + html.escape(panel["title"]) + "</h2>"
    ]
    for chart in panel["charts"]:
        parts.append(_legend_html({"series": chart["series"]}))
        parts.append('<div class="chart">' + _svg_quarter_chart(chart) + "</div>")
        parts.append('<p class="cap">' + html.escape(chart["caption"]) + "</p>")
    parts.append(
        '<p class="cap">The growth chart as a table - quarterly y/y % of segment '
        "revenue, one decimal. * Microsoft cells chained across the FY2025 segment "
        "redefinition (see the note below).</p>"
        + _cloud_table_html(panel["table"])
    )
    parts.append('<p class="cap">' + html.escape(panel["caption"]) + "</p></div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Page


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI trade dashboard &middot; the 8-panel watch</title>
<style>
:root{color-scheme:light;--bg:#f5f4ef;--paper:#fffefa;--ink:#21231f;--muted:#65685f;--line:#dedfd6;--accent:#955424}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:1100px;margin:auto;padding:24px 28px 60px}
.top{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:6px}
.brand{font-size:12px;font-weight:750;letter-spacing:.14em;color:var(--muted)}
h1{font:500 32px/1.15 Georgia,serif;margin:18px 0 4px}
p.sub{color:var(--muted);margin:0 0 14px}
.back{display:inline-block;margin:6px 0 18px;color:var(--accent);font-size:13px}
.chart-block{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:16px 16px 8px;margin:14px 0}
.chart-block h2{font-size:16px;margin:0 0 2px}
.chart-block .cap{font-size:12px;color:var(--muted);margin:4px 0 6px}
.chart svg{display:block;width:100%;height:auto}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;margin:2px 0 4px}
.lg{font-size:12px;color:var(--muted)}
.lg i{display:inline-block;width:26px;margin-right:6px;vertical-align:middle}
.lg i.ln{border-top:3px solid}
.lg i.dm{width:9px;height:9px;transform:rotate(45deg);margin:0 8px 0 4px}
.note{font-size:12px;color:var(--muted);margin-top:22px}
table.src{border-collapse:collapse;font-size:12px;color:var(--muted);margin:8px 0}
table.src td,table.src th{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
</style></head><body><main>
<div class="top"><span class="brand">OPENPAW / MARKET NOTES</span></div>
<h1>AI trade dashboard.</h1>
<p class="sub">The AI slowdown watch's eight panels, rendered natively from dated snapshots vendored into <code>data/ai_trade/</code> \u2014 no live fetching. Data as of __ASOF__. Dashed lines are projections, drawn faint on purpose: mechanical trend extrapolations of the recent segment \u2014 NOT forecasts or price targets \u2014 except Panel 6, where the dashed lines are stated expectations. Panel 7 (CDS) has no projection: only dated reported snapshots are plotted. Panel 8 (hyperscaler cloud) is the exception to the vendoring rule: it reads the Insight page's shared <code>data/insight/cloud_revenue.csv</code> and, like Panel 7, draws reported points only.</p>
<a class="back" href="index.html">&larr; Back to the portfolio dashboard</a>
__PANELS__
<div class="chart-block"><h2>Panel 7 data \u2014 every CDS print</h2>
<p class="cap">The complete Panel 7 dataset. Each row is a press-reported 5Y CDS level with its print date and source; the file format has no room for an estimate or a projection.</p>
__CDS_TABLE__</div>
<div class="chart-block"><h2>Series sources</h2>
<p class="cap">Every plotted series, its source, and the snapshot date. Sparse series (Panels 4R, 5R, 6) carry a source on each individual point in <code>data/ai_trade/snapshots.csv</code>.</p>
__NOTES_TABLE__</div>
<p class="note">Method: this tab ports the AI slowdown watch's combined-metrics chart (make_combined_chart.py) to the dashboard's self-contained HTML. Monthly series are the watcher's monthly aggregates (FRED monthly means, Yahoo monthly last closes, BLS as-printed y/y, EDGAR YTD-differenced capex). Refresh: re-run the watcher's chart script, re-extract combined-monthly.csv into data/ai_trade/monthly.csv, update snapshots.csv and cds_snapshots.csv from the watch logs and the script's dated CDS block, and bump the as_of dates in series_notes.csv. Panel 8 refreshes with the Insight page: append quarters to data/insight/cloud_revenue.csv there (2020 is the y/y base year - never trim it) and add its series rows to series_notes.csv here. Overlap note: the Insight page covers reported-vs-true capex and an ORCL credit timeline in depth; this tab is the broader 8-panel watch. Panel 8 is the deliberate exception to the no-duplication rule - it mirrors the Insight page's Section D cloud panel while its final home is being chosen, and both render from the one CSV, so the two copies can never disagree.</p>
</main></body></html>"""


def _cds_table(rows: list[dict[str, Any]]) -> str:
    trs = "".join(
        "<tr><td>{ticker}</td><td>{date}</td><td>{spread:,.0f}</td>"
        "<td>{source}</td><td>{note}</td></tr>".format(
            ticker=html.escape(r["ticker"]),
            date=html.escape(r["date"]),
            spread=r["spread_bps"],
            source=html.escape(r["source"]),
            note=html.escape(r["note"]),
        )
        for r in rows
    )
    return (
        '<table class="src"><tr><th>Ticker</th><th>Print date</th><th>5Y CDS (bp)</th>'
        "<th>Press source</th><th>Note</th></tr>" + trs + "</table>"
    )


def _notes_table(notes: list[SeriesNote]) -> str:
    trs = "".join(
        f"<tr><td>{html.escape(n.series)}</td><td>{n.panel}</td><td>{html.escape(n.source)}</td>"
        f"<td>{html.escape(n.as_of)}</td><td>{html.escape(n.note)}</td></tr>"
        for n in notes
    )
    return (
        '<table class="src"><tr><th>Series</th><th>Panel</th><th>Source</th>'
        "<th>As of</th><th>Note</th></tr>" + trs + "</table>"
    )


def render_ai_trade_dashboard(data: dict[str, Any], out_dir: Path) -> Path:
    """Write the self-contained ``ai-trade.html`` page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "ai-trade.html"
    blocks = []
    for panel in data["panels"]:
        if panel.get("kind") == "cloud":
            blocks.append(_cloud_block_html(panel))
            continue
        blocks.append(
            '<div class="chart-block"><h2>'
            + html.escape(panel["title"])
            + "</h2>"
            + _legend_html(panel)
            + '<div class="chart">'
            + _svg_panel(panel)
            + "</div>"
            + '<p class="cap">'
            + html.escape(panel["caption"])
            + "</p></div>"
        )
    page = (
        _PAGE.replace("__ASOF__", html.escape(str(data["asof"])))
        .replace("__PANELS__", "".join(blocks))
        .replace("__CDS_TABLE__", _cds_table(data["cds"]))
        .replace("__NOTES_TABLE__", _notes_table(data["notes"]))
    )
    target.write_text(page)
    return target
