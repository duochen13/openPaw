"""Insight dashboard: hidden AI leverage, in two sections (issues #34 + #35).

One self-contained offline page, following the factor_dashboard.py pattern:

- Section A (#34): annual reported Big-4 AI capex vs reported + SPV /
  off-balance-sheet combined, from ``data/insight/spv_capex.csv``. Every
  estimate row is anchored to a named deal; the SPV layer renders shaded
  between the two lines with anchor labels. A second panel scales both
  series by Big-4 revenue (``data/insight/revenue_big4.csv``, EDGAR
  companyfacts) as capex intensity - the reported-vs-true gap in
  percentage-of-revenue terms. The chart regenerates from
  the CSV on every render - no checked-in images, no hand-drawn numbers.
- Section B (#35): hyperscaler 5Y CDS spreads. Real CDS history is
  paywalled, so the seed data is an annotated event timeline of verified
  credit-stress anchors (``data/insight/cds_spreads.csv``) - every point
  labeled with its proxy type, never presented as a CDS print. The schema
  accepts real weekly 5Y CDS points (``proxy_label`` "cds-print:5y");
  when present they render as a line chart above the timeline.
"""

# The embedded HTML/SVG is intentionally kept in one readable template
# string, like factor_dashboard.py.
# ruff: noqa: E501

from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

#: Repo-root data dir (this project does not support a wheel install;
#: paths resolve against the source checkout).
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "insight"

_SPv_REQUIRED = {
    "year",
    "reported_big4_usd_b",
    "spv_est_usd_b",
    "anchor_deals",
    "chart_label",
    "source",
    "status",
}
_CDS_REQUIRED = {"ticker", "date", "spread_bps", "source", "proxy_label", "note"}
_REV_REQUIRED = {"year", "revenue_big4_usd_b", "source", "status"}
_SPV_STATUSES = {"verified", "estimated", "guidance"}
_REV_STATUSES = {"verified", "ttm-partial", "estimated"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")

#: Badge colors per proxy type on the Section B timeline.
_PROXY_COLORS = {
    "cds-level:reported": "#1f6feb",
    "credit-proxy:loan-price": "#dc2626",
    "credit-proxy:rating-action": "#d97706",
    "credit-proxy:balance-sheet": "#7c3aed",
    "cds-print:5y": "#16a34a",
}


class InsightDataError(ValueError):
    """A data/insight CSV is malformed."""


@dataclass(frozen=True)
class SpvRow:
    """One annual row: reported Big-4 capex + the SPV/off-BS estimate."""

    year: str  # e.g. "2023", "2026E"
    reported: float  # reported Big-4 capex, USD billions
    spv: float  # SPV / off-balance-sheet estimate, USD billions
    anchor_deals: str  # named deals anchoring the estimate - never empty when spv > 0
    chart_label: str
    source: str
    status: str  # verified | estimated | guidance

    @property
    def combined(self) -> float:
        """True spend estimate: reported + SPV."""
        return self.reported + self.spv


@dataclass(frozen=True)
class CdsPoint:
    """One credit-stress observation: a real CDS print or a labeled proxy."""

    ticker: str
    date: str  # YYYY-MM or YYYY-MM-DD
    spread_bps: float | None  # None for proxies: never invent a print
    source: str
    proxy_label: str
    note: str


@dataclass(frozen=True)
class RevenueRow:
    """One annual row: Big-4 (MSFT+AMZN+GOOGL+META) revenue, USD billions.

    Calendar-year sums of quarterly ``us-gaap:Revenues`` from SEC EDGAR
    companyfacts. The latest year may be ``ttm-partial``: trailing twelve
    months to the latest reported quarter, paired against full-year
    guidance capex - always labeled as such on the chart.
    """

    year: str
    revenue: float  # Big-4 revenue, USD billions
    source: str
    status: str  # verified | ttm-partial | estimated


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError as exc:
        raise InsightDataError(f"insight data not found: {path}") from exc
    if not rows:
        raise InsightDataError(f"{path}: no data rows")
    missing = required - set(rows[0].keys())
    if missing:
        raise InsightDataError(f"{path}: missing columns {sorted(missing)}")
    return rows


def _parse_amount(raw: str, *, where: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise InsightDataError(f"{where}: {raw!r} is not a number") from exc
    if value < 0:
        raise InsightDataError(f"{where}: negative amount {raw!r}")
    return value


def load_spv_capex(data_dir: Path | None = None) -> list[SpvRow]:
    """Validated annual reported-vs-true capex rows.

    The anchor rule: any row with a positive SPV estimate must name its
    anchor deals and cite a source - an unanchored estimate never renders.
    """
    path = (data_dir or DATA_DIR) / "spv_capex.csv"
    rows = []
    for i, r in enumerate(_read_csv(path, _SPv_REQUIRED), 1):
        where = f"{path}:{i}"
        reported = _parse_amount(r["reported_big4_usd_b"], where=where)
        spv = _parse_amount(r["spv_est_usd_b"], where=where)
        if spv > 0 and not r["anchor_deals"].strip():
            raise InsightDataError(f"{where}: SPV estimate without anchor deals")
        if spv > 0 and not r["source"].strip():
            raise InsightDataError(f"{where}: SPV estimate without source")
        status = r["status"].strip().lower()
        if status not in _SPV_STATUSES:
            raise InsightDataError(
                f"{where}: status {r['status']!r} not in {sorted(_SPV_STATUSES)}"
            )
        rows.append(
            SpvRow(
                year=r["year"].strip(),
                reported=reported,
                spv=spv,
                anchor_deals=r["anchor_deals"].strip(),
                chart_label=r["chart_label"].strip(),
                source=r["source"].strip(),
                status=status,
            )
        )
    return rows


def load_revenue(data_dir: Path | None = None) -> list[RevenueRow]:
    """Validated annual Big-4 revenue rows.

    The honesty rule: revenue must be positive and carry a source; a
    ``ttm-partial`` year is allowed but must say so, so the chart can
    label the capex-vs-revenue mismatch instead of hiding it.
    """
    path = (data_dir or DATA_DIR) / "revenue_big4.csv"
    rows = []
    for i, r in enumerate(_read_csv(path, _REV_REQUIRED), 1):
        where = f"{path}:{i}"
        revenue = _parse_amount(r["revenue_big4_usd_b"], where=where)
        if revenue <= 0:
            raise InsightDataError(f"{where}: revenue must be positive")
        if not r["source"].strip():
            raise InsightDataError(f"{where}: revenue without source")
        status = r["status"].strip().lower()
        if status not in _REV_STATUSES:
            raise InsightDataError(
                f"{where}: status {r['status']!r} not in {sorted(_REV_STATUSES)}"
            )
        rows.append(
            RevenueRow(
                year=r["year"].strip(),
                revenue=revenue,
                source=r["source"].strip(),
                status=status,
            )
        )
    return rows


def load_cds_spreads(data_dir: Path | None = None) -> list[CdsPoint]:
    """Validated credit-stress timeline points.

    The proxy rule: a row carrying ``spread_bps`` must be labeled a real
    CDS print (``proxy_label`` starting with "cds-print"); a proxy row
    must not carry a spread. Proxies are never presented as CDS prints.
    """
    path = (data_dir or DATA_DIR) / "cds_spreads.csv"
    points = []
    for i, r in enumerate(_read_csv(path, _CDS_REQUIRED), 1):
        where = f"{path}:{i}"
        for key in ("ticker", "date", "source", "proxy_label"):
            if not r[key].strip():
                raise InsightDataError(f"{where}: {key} is required")
        if not _DATE_RE.match(r["date"].strip()):
            raise InsightDataError(f"{where}: date {r['date']!r} must be YYYY-MM or YYYY-MM-DD")
        spread: float | None = None
        if r["spread_bps"].strip():
            spread = _parse_amount(r["spread_bps"], where=where)
        label = r["proxy_label"].strip()
        if spread is not None and not label.startswith("cds-print"):
            raise InsightDataError(f"{where}: spread_bps with proxy label {label!r}")
        if label == "cds-print:5y" and spread is None:
            raise InsightDataError(f"{where}: cds-print:5y needs spread_bps")
        points.append(
            CdsPoint(
                ticker=r["ticker"].strip().upper(),
                date=r["date"].strip(),
                spread_bps=spread,
                source=r["source"].strip(),
                proxy_label=label,
                note=r["note"].strip(),
            )
        )
    points.sort(key=lambda p: (p.date, p.ticker))
    return points


def insight_dashboard_data(data_dir: Path | None = None) -> dict[str, Any]:
    """Section A rows, revenue-scaled intensity, Section B timeline, real CDS prints."""
    spv = load_spv_capex(data_dir)
    rev = {r.year: r for r in load_revenue(data_dir)}
    cds = load_cds_spreads(data_dir)
    prints: dict[str, list[tuple[str, float]]] = {}
    for p in cds:
        if p.spread_bps is not None:
            prints.setdefault(p.ticker, []).append((p.date, p.spread_bps))
    data_dates = [r.year for r in spv] + [p.date for p in cds]
    spv_rows = []
    for r in spv:
        rev_row = rev.get(r.year)
        if rev_row is None:
            raise InsightDataError(
                f"revenue_big4.csv: no revenue row for capex year {r.year!r}"
            )
        spv_rows.append(
            {
                "year": r.year,
                "reported": r.reported,
                "spv": r.spv,
                "combined": r.combined,
                "revenue": rev_row.revenue,
                "revenue_status": rev_row.status,
                "intensity_reported": 100.0 * r.reported / rev_row.revenue,
                "intensity_true": 100.0 * r.combined / rev_row.revenue,
                "anchor_deals": r.anchor_deals,
                "chart_label": r.chart_label,
                "source": r.source,
                "status": r.status,
            }
        )
    return {
        "spv": spv_rows,
        "cds": [
            {
                "ticker": p.ticker,
                "date": p.date,
                "spread_bps": p.spread_bps,
                "source": p.source,
                "proxy_label": p.proxy_label,
                "note": p.note,
            }
            for p in cds
        ],
        "cds_prints": prints,
        "asof": max(data_dates) if data_dates else "",
    }


# ---------------------------------------------------------------------------
# SVG charts (server-rendered from the CSV data)


def _svg_spv_chart(rows: list[dict[str, Any]]) -> str:
    """Reported vs reported+SPV: blue line, green dashed combined, shaded gap."""
    W, H = 1000, 560
    pad_l, pad_r, pad_t, pad_b = 70, 30, 50, 60
    ymax: float = float(max(r["combined"] for r in rows)) * 1.15
    n = len(rows)

    def x(i: int) -> float:
        return pad_l + (W - pad_l - pad_r) * i / max(n - 1, 1)

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - v / ymax)

    esc = html.escape
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Reported vs true AI capex">']
    # Gridlines + y labels every 200B.
    step = 200.0
    g = step
    while g < ymax:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(g):.1f}" x2="{W - pad_r}" y2="{y(g):.1f}" '
            f'stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 10}" y="{y(g) + 5:.1f}" text-anchor="end" '
            f'font-size="13" fill="#65685f">${g:.0f}B</text>'
        )
        g += step
    # Shaded SPV gap between the reported and combined lines.
    top = " ".join(f"{x(i):.1f},{y(r['combined']):.1f}" for i, r in enumerate(rows))
    bot = " ".join(f"{x(n - 1 - i):.1f},{y(rows[n - 1 - i]['reported']):.1f}" for i in range(n))
    parts.append(
        f'<polygon points="{top} {bot}" fill="#fdba74" opacity="0.35" '
        'aria-label="SPV / off-balance-sheet layer (estimated)"/>'
    )
    # Reported line (blue) + value labels.
    rep = " ".join(f"{x(i):.1f},{y(r['reported']):.1f}" for i, r in enumerate(rows))
    parts.append(f'<polyline points="{rep}" fill="none" stroke="#1f6feb" stroke-width="3"/>')
    # Combined line (green, dashed).
    cmb = " ".join(f"{x(i):.1f},{y(r['combined']):.1f}" for i, r in enumerate(rows))
    parts.append(
        f'<polyline points="{cmb}" fill="none" stroke="#16a34a" stroke-width="3" '
        'stroke-dasharray="10,6"/>'
    )
    for i, r in enumerate(rows):
        parts.append(f'<circle cx="{x(i):.1f}" cy="{y(r["reported"]):.1f}" r="6" fill="#1f6feb"/>')
        parts.append(
            f'<text x="{x(i):.1f}" y="{y(r["reported"]) + 24:.1f}" text-anchor="middle" '
            f'font-size="14" font-weight="700" fill="#1f6feb">${r["reported"]:.0f}B</text>'
        )
        if r["spv"] > 0:
            parts.append(
                f'<rect x="{x(i) - 5:.1f}" y="{y(r["combined"]) - 5:.1f}" width="10" '
                f'height="10" fill="#16a34a"/>'
            )
            parts.append(
                f'<text x="{x(i):.1f}" y="{y(r["combined"]) - 12:.1f}" text-anchor="middle" '
                f'font-size="13" font-weight="700" fill="#9a3412">+${r["spv"]:.0f}B</text>'
            )
        year_label = r["year"] + ("E" if r["status"] == "guidance" else "")
        parts.append(
            f'<text x="{x(i):.1f}" y="{H - pad_b + 26:.1f}" text-anchor="middle" '
            f'font-size="14" fill="#21231f">{esc(year_label)}</text>'
        )
    # Anchor-deal annotations with leader lines. Labels sit above their
    # point; points near the top of the plot get the label below instead
    # so they never collide with the legend.
    plot_top, plot_h = pad_t, H - pad_t - pad_b
    for i, r in enumerate(rows):
        if not r["chart_label"]:
            continue
        yc = y(r["combined"])
        above = yc > plot_top + 0.25 * plot_h
        tx = x(i) if above else x(i) - 200  # below-labels shift left, off the value labels
        tx = min(max(tx, pad_l + 160), W - pad_r - 160)
        ty = yc - 55 if above else yc + 62
        anchor_y = ty + 14 if above else ty - 14
        parts.append(
            f'<line x1="{tx:.1f}" y1="{anchor_y:.1f}" '
            f'x2="{x(i):.1f}" y2="{yc:.1f}" stroke="#9a3412" stroke-width="1"/>'
            f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="12.5" '
            f'fill="#9a3412">{esc(r["chart_label"])}</text>'
        )
    # Legend.
    lx = pad_l + 10
    parts.append(
        f'<rect x="{lx}" y="8" width="14" height="10" fill="#fdba74" opacity="0.6"/>'
        f'<text x="{lx + 20}" y="17" font-size="13" fill="#65685f">SPV / off-balance-sheet (estimated)</text>'
        f'<line x1="{lx}" y1="32" x2="{lx + 34}" y2="32" stroke="#1f6feb" stroke-width="3"/>'
        f'<text x="{lx + 40}" y="36" font-size="13" fill="#65685f">Reported capex, Big-4 (MSFT+AMZN+GOOGL+META)</text>'
        f'<line x1="{lx + 330}" y1="32" x2="{lx + 364}" y2="32" stroke="#16a34a" stroke-width="3" stroke-dasharray="8,5"/>'
        f'<text x="{lx + 370}" y="36" font-size="13" fill="#65685f">True spend = reported + SPV (estimated)</text>'
    )
    parts.append(
        f'<text x="{pad_l}" y="{H - 12}" font-size="12" fill="#65685f">'
        "Reported: Big-4 filings/earnings calls. SPV layer = estimates anchored to named deals. "
        "Annual FLOW - the WSJ Jun-2026 $3T off-BS figure is a STOCK of commitments, not plotted."
        "</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _svg_intensity_chart(rows: list[dict[str, Any]]) -> str:
    """Grouped bars: reported capex % of revenue vs true (reported+SPV) %."""
    W, H = 1000, 450
    pad_l, pad_r, pad_t, pad_b = 70, 30, 46, 84
    ymax: float = float(max(r["intensity_true"] for r in rows)) * 1.18
    n = len(rows)
    slot = (W - pad_l - pad_r) / n
    bw = min(64.0, slot * 0.28)

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - v / ymax)

    esc = html.escape
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Capex as percent of revenue">']
    g = 10.0
    while g < ymax:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(g):.1f}" x2="{W - pad_r}" y2="{y(g):.1f}" '
            f'stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 10}" y="{y(g) + 5:.1f}" text-anchor="end" '
            f'font-size="13" fill="#65685f">{g:.0f}%</text>'
        )
        g += 10.0
    for i, r in enumerate(rows):
        cx = pad_l + slot * (i + 0.5)
        for j, (key, color) in enumerate(
            (("intensity_reported", "#1f6feb"), ("intensity_true", "#16a34a"))
        ):
            v = r[key]
            bx = cx + (j - 0.5) * bw - bw / 2
            parts.append(
                f'<rect x="{bx:.1f}" y="{y(v):.1f}" width="{bw:.1f}" '
                f'height="{y(0) - y(v):.1f}" fill="{color}" opacity="0.85" rx="3"/>'
            )
            parts.append(
                f'<text x="{bx + bw / 2:.1f}" y="{y(v) - 8:.1f}" text-anchor="middle" '
                f'font-size="13.5" font-weight="700" fill="{color}">{v:.1f}%</text>'
            )
        star = "*" if r["revenue_status"] == "ttm-partial" else ""
        year_label = r["year"] + ("E" if r["status"] == "guidance" else "") + star
        parts.append(
            f'<text x="{cx:.1f}" y="{H - pad_b + 26:.1f}" text-anchor="middle" '
            f'font-size="14" fill="#21231f">{esc(year_label)}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{H - pad_b + 46:.1f}" text-anchor="middle" '
            f'font-size="11.5" fill="#65685f">rev ${r["revenue"]:.0f}B</text>'
        )
    lx = pad_l + 10
    parts.append(
        f'<rect x="{lx}" y="8" width="14" height="10" fill="#1f6feb" opacity="0.85"/>'
        f'<text x="{lx + 20}" y="17" font-size="13" fill="#65685f">Reported capex / revenue</text>'
        f'<rect x="{lx + 220}" y="8" width="14" height="10" fill="#16a34a" opacity="0.85"/>'
        f'<text x="{lx + 240}" y="17" font-size="13" fill="#65685f">True spend (reported + SPV) / revenue</text>'
    )
    parts.append(
        f'<text x="{pad_l}" y="{H - 10}" font-size="12" fill="#65685f">'
        "Revenue: Big-4 calendar-year revenue from SEC EDGAR companyfacts. "
        "*2026 revenue is trailing-12-months to 2026-Q2 (latest reported); "
        "2026 capex is full-year guidance - the pair is a run-rate read, not audited."
        "</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _svg_cds_chart(prints: dict[str, list[tuple[str, float]]]) -> str:
    """Line chart of real weekly 5Y CDS prints, one series per ticker."""
    palette = ["#16a34a", "#1f6feb", "#d97706", "#dc2626", "#7c3aed", "#0891b2"]
    W, H = 1000, 380
    pad_l, pad_r, pad_t, pad_b = 70, 30, 30, 50

    def dnum(d: str) -> float:
        dt = date.fromisoformat(d if len(d) > 7 else d + "-01")
        return dt.toordinal()

    all_pts = [(t, d, v) for t, series in prints.items() for d, v in series]
    xs = [dnum(d) for _, d, _ in all_pts]
    vs = [v for _, _, v in all_pts]
    lo_x, hi_x = min(xs), max(xs)
    hi_v = max(vs) * 1.15
    span_x = max(hi_x - lo_x, 1)

    def x(d: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (dnum(d) - lo_x) / span_x

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - v / hi_v)

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="5Y CDS spreads">']
    for i, (ticker, series) in enumerate(sorted(prints.items())):
        color = palette[i % len(palette)]
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in series)
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        )
        for d, v in series:
            parts.append(
                f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="4" fill="{color}">'
                f"<title>{html.escape(ticker)} {html.escape(d)}: {v:.0f} bps</title></circle>"
            )
        lx = pad_l + 10 + i * 130
        parts.append(
            f'<line x1="{lx}" y1="14" x2="{lx + 24}" y2="14" stroke="{color}" stroke-width="3"/>'
            f'<text x="{lx + 30}" y="18" font-size="13" fill="#21231f">{html.escape(ticker)}</text>'
        )
    parts.append(
        f'<text x="{pad_l}" y="{H - 10}" font-size="12" fill="#65685f">'
        "5Y CDS spreads (bps). Real prints only - proxies live on the timeline below."
        "</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _timeline_html(points: list[dict[str, Any]]) -> str:
    items = []
    for p in points:
        color = _PROXY_COLORS.get(p["proxy_label"], "#65685f")
        badge = (
            f'<span class="proxy-badge" style="border-color:{color};color:{color}">'
            f"{html.escape(p['proxy_label'])}</span>"
        )
        items.append(
            '<div class="tl-item">'
            f'<div class="tl-date">{html.escape(p["date"])}</div>'
            '<div class="tl-dot" style="background:' + color + '"></div>'
            '<div class="tl-body">'
            f"<div><strong>{html.escape(p['ticker'])}</strong> {badge}</div>"
            f"<div>{html.escape(p['note'])}</div>"
            f"<div class=\"tl-src\">Source: {html.escape(p['source'])}</div>"
            "</div></div>"
        )
    return "".join(items)


# ---------------------------------------------------------------------------
# Page


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Insight &middot; hidden AI leverage</title>
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
.chart-block .cap{font-size:12px;color:var(--muted);margin:0 0 6px}
.chart svg{display:block;width:100%;height:auto}
.note{font-size:12px;color:var(--muted);margin-top:22px}
.tl{position:relative;margin:10px 0 6px;padding-left:118px}
.tl:before{content:"";position:absolute;left:104px;top:6px;bottom:6px;width:2px;background:var(--line)}
.tl-item{position:relative;display:flex;gap:12px;padding:10px 0}
.tl-date{position:absolute;left:-118px;width:96px;text-align:right;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.tl-dot{position:absolute;left:-17px;top:14px;width:10px;height:10px;border-radius:50%;flex:none}
.tl-body{font-size:13px}
.tl-src{font-size:12px;color:var(--muted);margin-top:2px}
.proxy-badge{display:inline-block;font-size:11px;font-weight:700;border:1px solid;border-radius:4px;padding:0 6px;margin-left:6px;white-space:nowrap}
table.src{border-collapse:collapse;font-size:12px;color:var(--muted);margin:8px 0}
table.src td,table.src th{border:1px solid var(--line);padding:4px 8px;text-align:left}
</style></head><body><main>
<div class="top"><span class="brand">OPENPAW / MARKET NOTES</span></div>
<h1>Insight.</h1>
<p class="sub">Where the reported numbers understate the leverage: AI capex hidden in SPVs, and what credit markets charge for it. Data as of __ASOF__.</p>
<a class="back" href="index.html">&larr; Back to the portfolio dashboard</a>
<div class="chart-block"><h2>Reported vs true AI capex</h2>
<p class="cap">Annual Big-4 (MSFT + AMZN + GOOGL + META) capex vs reported + SPV/off-balance-sheet. The shaded gap is the hidden leverage - every estimate anchored to a named deal (hover the labels).</p>
<div class="chart">__SPV_SVG__</div>
__SPV_TABLE__</div>
<div class="chart-block"><h2>Capex intensity: share of revenue</h2>
<p class="cap">The same two series as a percentage of Big-4 revenue - this is the leverage ratio that matters. The green-over-blue gap is the reinvestment the income statement never shows.</p>
<div class="chart">__INTENSITY_SVG__</div></div>
<div class="chart-block"><h2>Hyperscaler credit stress</h2>
<p class="cap">5Y CDS history is paywalled, so this is an annotated timeline of verified credit-stress anchors - each point labeled with its proxy type. A proxy is never a CDS print.</p>
__CDS_CHART__
<div class="tl">__TIMELINE__</div></div>
<p class="note">Method: SPV estimates are anchored to named deals and spread over build years (see data/insight/spv_capex.csv); reported capex from company filings. Revenue is the calendar-year sum of quarterly us-gaap Revenues for MSFT+AMZN+GOOGL+META from SEC EDGAR companyfacts (see data/insight/revenue_big4.csv). CDS timeline points carry source + proxy labels (see data/insight/cds_spreads.csv) - add real weekly 5Y prints there with proxy_label <code>cds-print:5y</code> to grow the spread chart. Reported history, not a forecast.</p>
</main></body></html>"""


def _spv_table(rows: list[dict[str, Any]]) -> str:
    trs = "".join(
        "<tr><td>{year}</td><td>${reported:.0f}B</td><td>{spv}</td>"
        "<td>{status}</td><td>{source}</td></tr>".format(
            year=html.escape(r["year"]),
            reported=r["reported"],
            spv=f"+${r['spv']:.0f}B" if r["spv"] > 0 else "\u2014",
            status=html.escape(r["status"]),
            source=html.escape(r["anchor_deals"] or r["source"]),
        )
        for r in rows
    )
    return (
        '<table class="src"><tr><th>Year</th><th>Reported</th><th>SPV est.</th>'
        "<th>Status</th><th>Anchor / source</th></tr>" + trs + "</table>"
    )


def render_insight_dashboard(data: dict[str, Any], out_dir: Path) -> Path:
    """Write the self-contained ``insight.html`` page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "insight.html"
    cds_chart = (
        f'<div class="chart">{_svg_cds_chart(data["cds_prints"])}</div>'
        if data["cds_prints"]
        else ""
    )
    page = (
        _PAGE.replace("__ASOF__", html.escape(str(data["asof"])))
        .replace("__SPV_SVG__", _svg_spv_chart(data["spv"]))
        .replace("__INTENSITY_SVG__", _svg_intensity_chart(data["spv"]))
        .replace("__SPV_TABLE__", _spv_table(data["spv"]))
        .replace("__CDS_CHART__", cds_chart)
        .replace("__TIMELINE__", _timeline_html(data["cds"]))
    )
    target.write_text(page)
    return target
