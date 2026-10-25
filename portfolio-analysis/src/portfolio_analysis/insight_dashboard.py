"""Insight dashboard: hidden AI leverage + macro early-warning (#34, #35, #171).

One self-contained offline page:

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
- Section C (#171): macro early-warning figures - the series that crack
  before credit does. The NAR Pending Home Sales Index
  (``data/insight/pending_home_sales.csv``, monthly; NAR benchmark-
  revises it, so each row cites the release table / snapshot its level
  was read from), the 30-year mortgage rate
  (``data/insight/mortgage_rates.csv``: FRED MORTGAGE30US weekly
  observations stored as monthly averages) and CME FedWatch target-rate
  probability snapshots (``data/insight/fedwatch_snapshots.csv``) - one
  line per FOMC meeting, snapshots appended over time and never
  connected across meetings.
- Section D (#174): hyperscaler cloud revenue & growth - quarterly
  segment revenue and YoY growth for Google Cloud, AWS and Microsoft
  Intelligent Cloud (``data/insight/cloud_revenue.csv``, calendar
  quarters). Microsoft does not disclose Azure dollar revenue, so
  Microsoft is plotted on its Intelligent Cloud segment in both
  charts; Azure's reported growth rate appears only as a sourced
  text annotation, never as a plotted series.
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
_HOUSING_REQUIRED = {"month", "level", "source", "release_date"}
_MORTGAGE_REQUIRED = {"month", "avg_rate", "source"}
_FEDWATCH_REQUIRED = {"as_of", "meeting", "p_cut", "p_hold", "p_hike", "source"}
_CLOUD_REQUIRED = {"vendor", "segment", "quarter", "revenue_usd_b", "source", "status"}
_CLOUD_STATUSES = {"verified", "estimated"}
_QUARTER_RE = re.compile(r"^\d{4}-Q[1-4]$")

#: Section D chart order and line colors: (vendor ticker, segment, color).
#: Labels render from each row's own segment field; this table only
#: fixes the vendor order and colors.
_CLOUD_SERIES = (
    ("GOOGL", "Google Cloud", "#1f6feb"),
    ("AMZN", "AWS", "#d97706"),
    ("MSFT", "Microsoft Intelligent Cloud", "#16a34a"),
)
_SPV_STATUSES = {"verified", "estimated", "guidance"}
_REV_STATUSES = {"verified", "ttm-partial", "estimated"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

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


@dataclass(frozen=True)
class HousingRow:
    """One monthly NAR Pending Home Sales Index print (SAAR, 2001 = 100).

    NAR benchmark-revises the index, so ``release_date`` dates the source
    document the level was read from (a release table or a dated
    snapshot), not the first release of that month's data.
    """

    month: str  # YYYY-MM
    level: float
    source: str
    release_date: str  # YYYY-MM-DD, date of the source document/snapshot


@dataclass(frozen=True)
class MortgageRow:
    """One month of the 30-year fixed mortgage rate, percent.

    ``avg_rate`` is the mean of that month's FRED MORTGAGE30US weekly
    observations; the final month may average only the weeks published
    so far. ``source`` says exactly that on every row.
    """

    month: str  # YYYY-MM
    avg_rate: float
    source: str


@dataclass(frozen=True)
class FedWatchRow:
    """One CME FedWatch snapshot: target-rate probabilities for a meeting.

    Snapshots are append-only history - a later snapshot of the same
    meeting never overwrites an earlier one, and the chart connects
    snapshots of one meeting only.
    """

    as_of: str  # YYYY-MM-DD, when the snapshot was taken
    meeting: str  # YYYY-MM-DD, the FOMC meeting date
    p_cut: float  # percent probability of a cut at that meeting
    p_hold: float  # percent probability of no change
    p_hike: float  # percent probability of a hike
    source: str


@dataclass(frozen=True)
class CloudRow:
    """One vendor-quarter of cloud segment revenue (USD billions).

    ``quarter`` is the CALENDAR quarter the segment revenue belongs
    to. Microsoft reports on a fiscal calendar (fiscal Q3 = calendar
    Q1, fiscal Q4 = calendar Q2, fiscal Q1 = calendar Q3, fiscal Q2 =
    calendar Q4); its rows are stored already mapped to calendar
    quarters. YoY growth is computed downstream from the chained
    revenue, never stored.
    """

    vendor: str  # ticker, e.g. "GOOGL"
    segment: str  # reported segment name, e.g. "Google Cloud"
    quarter: str  # calendar quarter, "2021-Q1"
    revenue: float  # segment revenue, USD billions
    source: str
    status: str  # verified | estimated


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


def _check_month(raw: str, *, where: str) -> str:
    month = raw.strip()
    if not _MONTH_RE.match(month):
        raise InsightDataError(f"{where}: month {raw!r} must be YYYY-MM")
    return month


def _check_full_date(raw: str, *, where: str, field: str) -> str:
    value = raw.strip()
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InsightDataError(
            f"{where}: {field} {raw!r} must be YYYY-MM-DD"
        ) from exc
    if len(value) != 10:
        raise InsightDataError(f"{where}: {field} {raw!r} must be YYYY-MM-DD")
    return value


def _month_label(month: str) -> str:
    """ "2026-09" -> "Sep 2026". """
    return f"{_MONTH_ABBR[int(month[5:7]) - 1]} {month[:4]}"


def load_pending_home_sales(data_dir: Path | None = None) -> list[HousingRow]:
    """Validated monthly Pending Home Sales Index rows.

    The source rule: every level carries the document it was read from -
    NAR revises this series, so an unsourced level could silently mix
    vintages. Months must be unique; MoM/YoY are computed downstream
    from the chained levels, never stored.
    """
    path = (data_dir or DATA_DIR) / "pending_home_sales.csv"
    rows = []
    seen: set[str] = set()
    for i, r in enumerate(_read_csv(path, _HOUSING_REQUIRED), 1):
        where = f"{path}:{i}"
        month = _check_month(r["month"], where=where)
        if month in seen:
            raise InsightDataError(f"{where}: duplicate month {month!r}")
        seen.add(month)
        level = _parse_amount(r["level"], where=where)
        if level <= 0:
            raise InsightDataError(f"{where}: level must be positive")
        if not r["source"].strip():
            raise InsightDataError(f"{where}: level without source")
        rows.append(
            HousingRow(
                month=month,
                level=level,
                source=r["source"].strip(),
                release_date=_check_full_date(
                    r["release_date"], where=where, field="release_date"
                ),
            )
        )
    rows.sort(key=lambda r: r.month)
    return rows


def load_mortgage_rates(data_dir: Path | None = None) -> list[MortgageRow]:
    """Validated monthly mortgage-rate rows (monthly averages of weekly).

    The source rule: every row names its series and aggregation
    ("FRED MORTGAGE30US weekly, monthly average") so a stored average is
    never mistaken for a weekly print.
    """
    path = (data_dir or DATA_DIR) / "mortgage_rates.csv"
    rows = []
    seen: set[str] = set()
    for i, r in enumerate(_read_csv(path, _MORTGAGE_REQUIRED), 1):
        where = f"{path}:{i}"
        month = _check_month(r["month"], where=where)
        if month in seen:
            raise InsightDataError(f"{where}: duplicate month {month!r}")
        seen.add(month)
        rate = _parse_amount(r["avg_rate"], where=where)
        if not 0 < rate < 25:
            raise InsightDataError(f"{where}: avg_rate {rate} outside a sane 0-25% band")
        if not r["source"].strip():
            raise InsightDataError(f"{where}: avg_rate without source")
        rows.append(
            MortgageRow(month=month, avg_rate=rate, source=r["source"].strip())
        )
    rows.sort(key=lambda r: r.month)
    return rows


def load_fedwatch_snapshots(data_dir: Path | None = None) -> list[FedWatchRow]:
    """Validated CME FedWatch snapshot rows.

    The probability rule: cut + hold + hike must sum to ~100 (within
    rounding tolerance) - a snapshot that does not is a parsing error,
    not a market view, and never renders.
    """
    path = (data_dir or DATA_DIR) / "fedwatch_snapshots.csv"
    rows = []
    for i, r in enumerate(_read_csv(path, _FEDWATCH_REQUIRED), 1):
        where = f"{path}:{i}"
        for key in ("as_of", "meeting", "source"):
            if not r[key].strip():
                raise InsightDataError(f"{where}: {key} is required")
        probs = {
            key: _parse_amount(r[key], where=where)
            for key in ("p_cut", "p_hold", "p_hike")
        }
        for key, value in probs.items():
            if value > 100:
                raise InsightDataError(f"{where}: {key} probability {value} above 100")
        total = sum(probs.values())
        if abs(total - 100.0) > 1.5:
            raise InsightDataError(
                f"{where}: probabilities sum to {total:.1f}, not ~100"
            )
        rows.append(
            FedWatchRow(
                as_of=_check_full_date(r["as_of"], where=where, field="as_of"),
                meeting=_check_full_date(r["meeting"], where=where, field="meeting"),
                p_cut=probs["p_cut"],
                p_hold=probs["p_hold"],
                p_hike=probs["p_hike"],
                source=r["source"].strip(),
            )
        )
    rows.sort(key=lambda r: (r.meeting, r.as_of))
    return rows


def _check_quarter(raw: str, *, where: str) -> str:
    quarter = raw.strip()
    if not _QUARTER_RE.match(quarter):
        raise InsightDataError(f"{where}: quarter {raw!r} must be YYYY-Qn")
    return quarter


def _shift_quarter(quarter: str, quarters: int) -> str:
    idx = int(quarter[:4]) * 4 + int(quarter[6]) - 1 + quarters
    return f"{idx // 4:04d}-Q{idx % 4 + 1}"


def _quarter_label(quarter: str) -> str:
    """ "2026-Q2" -> "Q2 2026". """
    return f"Q{quarter[6]} {quarter[:4]}"


def load_cloud_revenue(data_dir: Path | None = None) -> list[CloudRow]:
    """Validated quarterly cloud segment revenue rows (Section D).

    The source rule: every quarter carries where its revenue was read
    from - segment definitions differ per vendor (and Microsoft
    redefined Intelligent Cloud in FY2025), so an unsourced number
    could silently mix definitions. Each vendor must report a single
    segment name; (vendor, quarter) pairs must be unique. YoY is
    computed downstream from the chained revenue, never stored.
    """
    path = (data_dir or DATA_DIR) / "cloud_revenue.csv"
    rows = []
    seen: set[tuple[str, str]] = set()
    segments: dict[str, str] = {}
    for i, r in enumerate(_read_csv(path, _CLOUD_REQUIRED), 1):
        where = f"{path}:{i}"
        vendor = r["vendor"].strip().upper()
        if not vendor:
            raise InsightDataError(f"{where}: vendor is required")
        segment = r["segment"].strip()
        if not segment:
            raise InsightDataError(f"{where}: segment is required")
        if segments.setdefault(vendor, segment) != segment:
            raise InsightDataError(
                f"{where}: vendor {vendor} reports two segments "
                f"({segments[vendor]!r} and {segment!r})"
            )
        quarter = _check_quarter(r["quarter"], where=where)
        if (vendor, quarter) in seen:
            raise InsightDataError(f"{where}: duplicate {vendor} {quarter}")
        seen.add((vendor, quarter))
        revenue = _parse_amount(r["revenue_usd_b"], where=where)
        if revenue <= 0:
            raise InsightDataError(f"{where}: revenue must be positive")
        if not r["source"].strip():
            raise InsightDataError(f"{where}: revenue without source")
        status = r["status"].strip().lower()
        if status not in _CLOUD_STATUSES:
            raise InsightDataError(
                f"{where}: status {r['status']!r} not in {sorted(_CLOUD_STATUSES)}"
            )
        rows.append(
            CloudRow(
                vendor=vendor,
                segment=segment,
                quarter=quarter,
                revenue=revenue,
                source=r["source"].strip(),
                status=status,
            )
        )
    rows.sort(key=lambda r: (r.vendor, r.quarter))
    return rows


def _load_optional(name: str, loader: Any, data_dir: Path | None) -> list:
    """Load an additive Section C/D CSV when present.

    Sections C (#171) and D (#174) are additive: a data dir that
    predates them renders the earlier sections unchanged. A
    present-but-malformed file still raises - absence is tolerated,
    bad data is not.
    """
    if not ((data_dir or DATA_DIR) / name).exists():
        return []
    return loader(data_dir)


def insight_dashboard_data(data_dir: Path | None = None) -> dict[str, Any]:
    """Section A rows, revenue-scaled intensity, Section B timeline, real
    CDS prints, the Section C macro figures (housing, mortgage,
    FedWatch) with MoM/YoY computed from the chained housing levels,
    and the Section D cloud series with YoY computed from the chained
    quarterly revenue."""
    spv = load_spv_capex(data_dir)
    rev = {r.year: r for r in load_revenue(data_dir)}
    cds = load_cds_spreads(data_dir)
    housing_rows = _load_optional(
        "pending_home_sales.csv", load_pending_home_sales, data_dir
    )
    mortgage_rows = _load_optional("mortgage_rates.csv", load_mortgage_rates, data_dir)
    fedwatch_rows = _load_optional(
        "fedwatch_snapshots.csv", load_fedwatch_snapshots, data_dir
    )
    cloud_rows = _load_optional("cloud_revenue.csv", load_cloud_revenue, data_dir)
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
    levels = {r.month: r.level for r in housing_rows}

    def _shift_month(month: str, months: int) -> str:
        idx = int(month[:4]) * 12 + int(month[5:7]) - 1 + months
        return f"{idx // 12:04d}-{idx % 12 + 1:02d}"

    housing = []
    for r in housing_rows:
        prev = levels.get(_shift_month(r.month, -1))
        year_ago = levels.get(_shift_month(r.month, -12))
        housing.append(
            {
                "month": r.month,
                "level": r.level,
                "mom_pct": 100.0 * (r.level / prev - 1) if prev else None,
                "yoy_pct": 100.0 * (r.level / year_ago - 1) if year_ago else None,
                "source": r.source,
                "release_date": r.release_date,
            }
        )
    cloud_by_vendor: dict[str, dict[str, Any]] = {}
    for r in cloud_rows:
        entry = cloud_by_vendor.setdefault(
            r.vendor, {"vendor": r.vendor, "segment": r.segment, "by_quarter": {}}
        )
        entry["by_quarter"][r.quarter] = r.revenue
    cloud_order = {vendor: i for i, (vendor, _, _) in enumerate(_CLOUD_SERIES)}
    cloud = []
    for entry in sorted(
        cloud_by_vendor.values(),
        key=lambda e: cloud_order.get(e["vendor"], len(cloud_order)),
    ):
        by_quarter = entry["by_quarter"]
        points = []
        for quarter in sorted(by_quarter):
            year_ago = by_quarter.get(_shift_quarter(quarter, -4))
            points.append(
                {
                    "quarter": quarter,
                    "revenue": by_quarter[quarter],
                    "yoy_pct": (
                        100.0 * (by_quarter[quarter] / year_ago - 1)
                        if year_ago
                        else None
                    ),
                }
            )
        cloud.append(
            {"vendor": entry["vendor"], "segment": entry["segment"], "points": points}
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
        "housing": housing,
        "mortgage": [
            {"month": r.month, "avg_rate": r.avg_rate, "source": r.source}
            for r in mortgage_rows
        ],
        "fedwatch": [
            {
                "as_of": r.as_of,
                "meeting": r.meeting,
                "p_cut": r.p_cut,
                "p_hold": r.p_hold,
                "p_hike": r.p_hike,
                "source": r.source,
            }
            for r in fedwatch_rows
        ],
        "cloud": cloud,
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
    """Line chart of real weekly 5Y CDS prints, one series per ticker.

    The time axis starts at 2021 to align with the capex panels (#169);
    the span before the first collected print is shaded and labeled as a
    no-data region rather than left empty or, worse, backfilled.
    """
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
    # The x-axis is aligned with the capex panels: it starts at 2021 even
    # though print collection began much later (#169). The span before the
    # first collected print is drawn as an explicit no-data region below -
    # never interpolated, never backfilled.
    first_x = lo_x
    first_date = min(d for _, d, _ in all_pts if dnum(d) == first_x)
    lo_x = min(lo_x, date(2021, 1, 1).toordinal())
    span_x = max(hi_x - lo_x, 1)

    def xo(o: float) -> float:
        return pad_l + (W - pad_l - pad_r) * (o - lo_x) / span_x

    def x(d: str) -> float:
        return xo(dnum(d))

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - v / hi_v)

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="5Y CDS spreads">']
    if first_x - lo_x > 45:
        first_dt = date.fromisoformat(
            first_date if len(first_date) > 7 else first_date + "-01"
        )
        parts.append(
            f'<rect x="{xo(lo_x):.1f}" y="{pad_t}" width="{xo(first_x) - xo(lo_x):.1f}" '
            f'height="{H - pad_t - pad_b}" fill="#21231f" opacity="0.05"/>'
            f'<text x="{(xo(lo_x) + xo(first_x)) / 2:.1f}" y="{(pad_t + H - pad_b) / 2:.1f}" '
            f'text-anchor="middle" font-size="13" fill="#65685f">'
            f"No collected prints before {first_dt.strftime('%b %Y')}</text>"
        )
    for yr in range(2021, date.fromordinal(int(hi_x)).year + 1):
        o = date(yr, 1, 1).toordinal()
        if lo_x <= o <= hi_x:
            parts.append(
                f'<line x1="{xo(o):.1f}" y1="{H - pad_b}" x2="{xo(o):.1f}" y2="{H - pad_b + 6}" '
                f'stroke="#65685f" stroke-width="1"/>'
                f'<text x="{xo(o):.1f}" y="{H - pad_b + 22:.1f}" text-anchor="middle" '
                f'font-size="12" fill="#65685f">{yr}</text>'
            )
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
# Section C charts (#171): housing, mortgage rates, FedWatch snapshots


def _year_ticks(rows: list[dict[str, Any]], x: Any, base_y: float) -> list[str]:
    """Year tick labels: the first point's year, then every January."""
    parts = []
    seen_years: set[str] = set()
    for r in rows:
        year = r["month"][:4]
        if r["month"][5:7] == "01" or not seen_years:
            if year not in seen_years:
                seen_years.add(year)
                parts.append(
                    f'<line x1="{x(r["month"]):.1f}" y1="{base_y:.1f}" '
                    f'x2="{x(r["month"]):.1f}" y2="{base_y + 5:.1f}" stroke="#c9cabf"/>'
                    f'<text x="{x(r["month"]):.1f}" y="{base_y + 24:.1f}" '
                    f'text-anchor="middle" font-size="13" fill="#21231f">{year}</text>'
                )
    return parts


def _svg_housing_chart(rows: list[dict[str, Any]]) -> str:
    """NAR Pending Home Sales Index line; latest print + pre-2026 low marked."""
    if not rows:
        return (
            '<p class="cap">Pending home sales data unavailable '
            "(data/insight/pending_home_sales.csv not loaded).</p>"
        )
    W, H = 1000, 420
    pad_l, pad_r, pad_t, pad_b = 70, 30, 42, 54

    def dnum(m: str) -> float:
        return date(int(m[:4]), int(m[5:7]), 1).toordinal()

    lo_x, hi_x = dnum(rows[0]["month"]), dnum(rows[-1]["month"])
    span_x = max(hi_x - lo_x, 1)
    lo_v = min(r["level"] for r in rows)
    hi_v = max(r["level"] for r in rows)
    ymin = math.floor((lo_v - 5) / 10) * 10
    ymax = math.ceil((hi_v + 5) / 10) * 10

    def x(m: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (dnum(m) - lo_x) / span_x

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - (v - ymin) / (ymax - ymin))

    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Pending home sales index">'
    ]
    g = ymin + 10.0
    while g < ymax:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(g):.1f}" x2="{W - pad_r}" y2="{y(g):.1f}" '
            f'stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 10}" y="{y(g) + 5:.1f}" text-anchor="end" '
            f'font-size="13" fill="#65685f">{g:.0f}</text>'
        )
        g += 10.0
    # Pre-2026 series low: dashed warning line.
    pre = [r for r in rows if r["month"] < "2026-01"]
    if pre:
        low_row = min(pre, key=lambda r: r["level"])
        ly = y(low_row["level"])
        parts.append(
            f'<line x1="{pad_l}" y1="{ly:.1f}" x2="{W - pad_r}" y2="{ly:.1f}" '
            f'stroke="#dc2626" stroke-width="1.5" stroke-dasharray="7,5"/>'
            f'<text x="{W - pad_r - 4}" y="{ly - 8:.1f}" text-anchor="end" '
            f'font-size="12.5" fill="#dc2626">pre-2026 low {low_row["level"]:.1f} '
            f'({_month_label(low_row["month"])})</text>'
        )
    pts = " ".join(f"{x(r['month']):.1f},{y(r['level']):.1f}" for r in rows)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#1f6feb" stroke-width="2.5"/>')
    for r in rows:
        parts.append(
            f'<circle cx="{x(r["month"]):.1f}" cy="{y(r["level"]):.1f}" r="2" fill="#1f6feb"/>'
        )
    last = rows[-1]
    parts.append(
        f'<circle cx="{x(last["month"]):.1f}" cy="{y(last["level"]):.1f}" r="5.5" fill="#dc2626">'
        f"<title>{html.escape(_month_label(last['month']))}: {last['level']:.1f}</title></circle>"
        f'<text x="{x(last["month"]):.1f}" y="{y(last["level"]) - 14:.1f}" text-anchor="end" '
        f'font-size="14" font-weight="700" fill="#dc2626">'
        f'{html.escape(_month_label(last["month"]))}: {last["level"]:.1f} - series low</text>'
    )
    parts.extend(_year_ticks(rows, x, H - pad_b))
    parts.append(
        f'<text x="{pad_l}" y="{H - 8}" font-size="12" fill="#65685f">'
        "NAR Pending Home Sales Index, seasonally adjusted (2001 = 100). Levels are the "
        "latest vintage fetched per month - NAR benchmark-revises the series (per-row "
        "sources in the CSV). Coverage starts Dec 2021: Jan-Nov 2021 monthly values were "
        "not available from a fetchable primary table."
        "</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _svg_mortgage_chart(rows: list[dict[str, Any]]) -> str:
    """30-year mortgage rate: monthly averages of the FRED weekly series."""
    if not rows:
        return (
            '<p class="cap">Mortgage rate data unavailable '
            "(data/insight/mortgage_rates.csv not loaded).</p>"
        )
    W, H = 1000, 380
    pad_l, pad_r, pad_t, pad_b = 70, 30, 42, 54

    def dnum(m: str) -> float:
        return date(int(m[:4]), int(m[5:7]), 1).toordinal()

    lo_x, hi_x = dnum(rows[0]["month"]), dnum(rows[-1]["month"])
    span_x = max(hi_x - lo_x, 1)
    lo_v = min(r["avg_rate"] for r in rows)
    hi_v = max(r["avg_rate"] for r in rows)
    ymin = math.floor((lo_v - 0.4) * 2) / 2
    ymax = math.ceil((hi_v + 0.4) * 2) / 2

    def x(m: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (dnum(m) - lo_x) / span_x

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - (v - ymin) / (ymax - ymin))

    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        'aria-label="30-year mortgage rate, monthly average">'
    ]
    g = math.ceil(ymin) + 0.0
    while g < ymax:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(g):.1f}" x2="{W - pad_r}" y2="{y(g):.1f}" '
            f'stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 10}" y="{y(g) + 5:.1f}" text-anchor="end" '
            f'font-size="13" fill="#65685f">{g:.0f}%</text>'
        )
        g += 1.0
    pts = " ".join(f"{x(r['month']):.1f},{y(r['avg_rate']):.1f}" for r in rows)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#d97706" stroke-width="2.5"/>')
    peak = max(rows, key=lambda r: r["avg_rate"])
    parts.append(
        f'<circle cx="{x(peak["month"]):.1f}" cy="{y(peak["avg_rate"]):.1f}" r="4.5" fill="#d97706">'
        f"<title>Peak {_month_label(peak['month'])}: {peak['avg_rate']:.2f}%</title></circle>"
        f'<text x="{x(peak["month"]):.1f}" y="{y(peak["avg_rate"]) - 12:.1f}" text-anchor="middle" '
        f'font-size="13" font-weight="700" fill="#9a3412">peak {peak["avg_rate"]:.2f}% '
        f'({html.escape(_month_label(peak["month"]))})</text>'
    )
    last = rows[-1]
    parts.append(
        f'<circle cx="{x(last["month"]):.1f}" cy="{y(last["avg_rate"]):.1f}" r="4.5" fill="#d97706">'
        f"<title>{_month_label(last['month'])}: {last['avg_rate']:.2f}%</title></circle>"
        f'<text x="{x(last["month"]):.1f}" y="{y(last["avg_rate"]) - 12:.1f}" text-anchor="end" '
        f'font-size="13" font-weight="700" fill="#9a3412">'
        f'{html.escape(_month_label(last["month"]))}: {last["avg_rate"]:.2f}% (partial month)</text>'
    )
    parts.extend(_year_ticks(rows, x, H - pad_b))
    parts.append(
        f'<text x="{pad_l}" y="{H - 8}" font-size="12" fill="#65685f">'
        "30-year fixed mortgage rate (FRED MORTGAGE30US): weekly observations averaged "
        "by calendar month. The final month averages only the weeks published so far."
        "</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _svg_fedwatch_chart(rows: list[dict[str, Any]]) -> str:
    """FedWatch hike probability: one line per FOMC meeting, snapshots only."""
    if not rows:
        return (
            '<p class="cap">FedWatch snapshots unavailable '
            "(data/insight/fedwatch_snapshots.csv not loaded).</p>"
        )
    palette = ["#dc2626", "#1f6feb", "#d97706", "#16a34a", "#7c3aed"]
    W, H = 1000, 380
    pad_l, pad_r, pad_t, pad_b = 70, 150, 42, 54

    def dnum(d: str) -> float:
        return date.fromisoformat(d).toordinal()

    meetings: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        meetings.setdefault(r["meeting"], []).append(r)
    xs = [dnum(r["as_of"]) for r in rows]
    lo_x, hi_x = min(xs) - 2, max(xs) + 2
    span_x = max(hi_x - lo_x, 1)

    def x(d: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (dnum(d) - lo_x) / span_x

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - v / 100.0)

    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        'aria-label="FedWatch hike probabilities by FOMC meeting">'
    ]
    for gval in (25.0, 50.0, 75.0, 100.0):
        parts.append(
            f'<line x1="{pad_l}" y1="{y(gval):.1f}" x2="{W - pad_r}" y2="{y(gval):.1f}" '
            f'stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 10}" y="{y(gval) + 5:.1f}" text-anchor="end" '
            f'font-size="13" fill="#65685f">{gval:.0f}%</text>'
        )
    parts.append(
        f'<text x="{pad_l - 10}" y="{y(0) + 5:.1f}" text-anchor="end" '
        f'font-size="13" fill="#65685f">0%</text>'
    )
    for i, (meeting, snaps) in enumerate(sorted(meetings.items())):
        color = palette[i % len(palette)]
        snaps = sorted(snaps, key=lambda r: r["as_of"])
        if len(snaps) > 1:
            pts = " ".join(
                f"{x(s['as_of']):.1f},{y(s['p_hike']):.1f}" for s in snaps
            )
            parts.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>'
            )
        for s in snaps:
            parts.append(
                f'<circle cx="{x(s["as_of"]):.1f}" cy="{y(s["p_hike"]):.1f}" r="4.5" fill="{color}">'
                f"<title>FOMC {html.escape(meeting)} as of {html.escape(s['as_of'])}: "
                f"cut {s['p_cut']:.1f}% / hold {s['p_hold']:.1f}% / hike {s['p_hike']:.1f}%"
                "</title></circle>"
            )
        last = snaps[-1]
        label = (
            f"FOMC {_MONTH_ABBR[int(meeting[5:7]) - 1]} {int(meeting[8:10])}: "
            f"hike {last['p_hike']:.0f}%"
        )
        parts.append(
            f'<text x="{x(last["as_of"]) + 10:.1f}" y="{y(last["p_hike"]) + 5:.1f}" '
            f'font-size="13" font-weight="700" fill="{color}">{html.escape(label)}</text>'
        )
    for d in sorted({r["as_of"] for r in rows}):
        parts.append(
            f'<text x="{x(d):.1f}" y="{H - pad_b + 24:.1f}" text-anchor="middle" '
            f'font-size="13" fill="#21231f">{_MONTH_ABBR[int(d[5:7]) - 1]} {int(d[8:10])}</text>'
        )
    parts.append(
        f'<text x="{pad_l}" y="{H - 8}" font-size="12" fill="#65685f">'
        "CME FedWatch implied probability of a rate HIKE at each FOMC meeting. Lines "
        "join snapshots of the SAME meeting only - never across meetings. Cut probability "
        "is 0% in every snapshot so far; the notes carry the full cut/hold/hike split."
        "</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _housing_notes(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    last = rows[-1]
    bits = [f"Latest: {_month_label(last['month'])} at {last['level']:.1f}"]
    if last["mom_pct"] is not None:
        bits.append(f"{last['mom_pct']:+.1f}% MoM")
    if last["yoy_pct"] is not None:
        bits.append(f"{last['yoy_pct']:+.1f}% YoY")
    return (
        '<p class="cap">' + html.escape(", ".join(bits)) + " - the lowest print in the "
        "series' history per NAR's release. Contract signings lead closings by one to "
        "two months, which makes this the earliest housing read on the page.</p>"
    )


def _mortgage_notes(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    last = rows[-1]
    peak = max(rows, key=lambda r: r["avg_rate"])
    return (
        f'<p class="cap">Latest monthly average: {_month_label(last["month"])} '
        f'at {last["avg_rate"]:.2f}% (partial month). Cycle peak: '
        f'{_month_label(peak["month"])} at {peak["avg_rate"]:.2f}%. Every 1% on this '
        "rate is roughly a tenth of a buyer's purchasing power - the channel from the "
        "Fed path below to the signings above.</p>"
    )


def _fedwatch_notes(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    meetings: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        meetings.setdefault(r["meeting"], []).append(r)
    bits = []
    for meeting, snaps in sorted(meetings.items()):
        s = sorted(snaps, key=lambda r: r["as_of"])[-1]
        bits.append(
            f"FOMC {_MONTH_ABBR[int(meeting[5:7]) - 1]} {int(meeting[8:10])} "
            f"(as of {_MONTH_ABBR[int(s['as_of'][5:7]) - 1]} {int(s['as_of'][8:10])}): "
            f"cut {s['p_cut']:.1f}% / hold {s['p_hold']:.1f}% / hike {s['p_hike']:.1f}% "
            f"[{s['source']}]"
        )
    return '<p class="cap">' + html.escape(" · ".join(bits)) + "</p>"


# ---------------------------------------------------------------------------
# Section D charts (#174): hyperscaler cloud revenue & growth


def _cloud_color(vendor: str, index: int) -> str:
    palette = ["#1f6feb", "#d97706", "#16a34a", "#dc2626", "#7c3aed", "#0891b2"]
    for known, _, color in _CLOUD_SERIES:
        if vendor == known:
            return color
    return palette[index % len(palette)]


def _svg_cloud_lines(
    series: list[dict[str, Any]],
    *,
    key: str,
    fmt: Any,
    end_fmt: Any,
    grid_step: float,
    caption: str,
    aria: str,
) -> str:
    """Multi-vendor quarterly line chart shared by the Section D panels.

    Points sit at quarter starts on a calendar axis from 2021 (#169).
    A point with no value (YoY for a vendor's first four quarters) is
    simply not drawn - the line starts when the chained data does,
    never at an interpolated value.
    """
    W, H = 1000, 380
    pad_l, pad_r, pad_t, pad_b = 70, 30, 42, 54

    def dnum(quarter: str) -> float:
        return date(int(quarter[:4]), (int(quarter[6]) - 1) * 3 + 1, 1).toordinal()

    plotted = [
        (s, p) for s in series for p in s["points"] if p[key] is not None
    ]
    xs = [dnum(p["quarter"]) for _, p in plotted]
    vs = [p[key] for _, p in plotted]
    lo_x, hi_x = min(xs), max(xs)
    span_x = max(hi_x - lo_x, 1)
    ymin = min(0.0, math.floor(min(vs) / grid_step) * grid_step)
    ymax = math.ceil(max(vs) * 1.12 / grid_step) * grid_step

    def x(quarter: str) -> float:
        return pad_l + (W - pad_l - pad_r) * (dnum(quarter) - lo_x) / span_x

    def y(v: float) -> float:
        return pad_t + (H - pad_t - pad_b) * (1 - (v - ymin) / (ymax - ymin))

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{aria}">']
    g = ymin + grid_step
    while g < ymax:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(g):.1f}" x2="{W - pad_r}" y2="{y(g):.1f}" '
            f'stroke="#e5e4da" stroke-width="1"/>'
            f'<text x="{pad_l - 10}" y="{y(g) + 5:.1f}" text-anchor="end" '
            f'font-size="13" fill="#65685f">{fmt(g)}</text>'
        )
        g += grid_step
    if ymin < 0:
        parts.append(
            f'<line x1="{pad_l}" y1="{y(0):.1f}" x2="{W - pad_r}" y2="{y(0):.1f}" '
            f'stroke="#c9cabf" stroke-width="1.5"/>'
        )
    parts.append(
        f'<text x="{pad_l - 10}" y="{y(ymin) + 5:.1f}" text-anchor="end" '
        f'font-size="13" fill="#65685f">{fmt(ymin)}</text>'
    )
    end_labels: list[tuple[float, float, str, str]] = []
    for i, s in enumerate(series):
        color = _cloud_color(s["vendor"], i)
        pts = [
            p for p in s["points"] if p[key] is not None
        ]
        if not pts:
            continue
        poly = " ".join(f"{x(p['quarter']):.1f},{y(p[key]):.1f}" for p in pts)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        )
        for p in pts:
            parts.append(
                f'<circle cx="{x(p["quarter"]):.1f}" cy="{y(p[key]):.1f}" r="2" fill="{color}">'
                f"<title>{html.escape(s['segment'])} "
                f"{html.escape(_quarter_label(p['quarter']))}: {end_fmt(p[key])}</title></circle>"
            )
        last = pts[-1]
        parts.append(
            f'<circle cx="{x(last["quarter"]):.1f}" cy="{y(last[key]):.1f}" r="4.5" fill="{color}"/>'
        )
        end_labels.append(
            (x(last["quarter"]), y(last[key]) - 12, color, end_fmt(last[key]))
        )
        lx = pad_l + 10 + i * 250
        parts.append(
            f'<line x1="{lx}" y1="14" x2="{lx + 24}" y2="14" stroke="{color}" stroke-width="3"/>'
            f'<text x="{lx + 30}" y="18" font-size="13" fill="#21231f">{html.escape(s["segment"])}</text>'
        )
    # End labels share the right edge: push overlapping ones apart.
    end_labels.sort(key=lambda t: t[1])
    for j in range(1, len(end_labels)):
        lx, ly, color, text = end_labels[j]
        if ly < end_labels[j - 1][1] + 16:
            end_labels[j] = (lx, end_labels[j - 1][1] + 16, color, text)
    for lx, ly, color, text in end_labels:
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="end" '
            f'font-size="13" font-weight="700" fill="{color}">{text}</text>'
        )
    def xo(o: float) -> float:
        return pad_l + (W - pad_l - pad_r) * (o - lo_x) / span_x

    for yr in range(
        date.fromordinal(int(lo_x)).year, date.fromordinal(int(hi_x)).year + 1
    ):
        o = date(yr, 1, 1).toordinal()
        if lo_x <= o <= hi_x:
            parts.append(
                f'<line x1="{xo(o):.1f}" y1="{H - pad_b}" x2="{xo(o):.1f}" '
                f'y2="{H - pad_b + 6}" stroke="#65685f" stroke-width="1"/>'
                f'<text x="{xo(o):.1f}" y="{H - pad_b + 22:.1f}" text-anchor="middle" '
                f'font-size="12" fill="#65685f">{yr}</text>'
            )
    parts.append(
        f'<text x="{pad_l}" y="{H - 8}" font-size="12" fill="#65685f">{caption}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _svg_cloud_revenue_chart(series: list[dict[str, Any]]) -> str:
    """Quarterly cloud segment revenue (USD B), one line per vendor."""
    if not series:
        return (
            '<p class="cap">Cloud revenue data unavailable '
            "(data/insight/cloud_revenue.csv not loaded).</p>"
        )
    return _svg_cloud_lines(
        series,
        key="revenue",
        fmt=lambda v: f"{v:.0f}",
        end_fmt=lambda v: f"${v:.1f}B",
        grid_step=10.0,
        caption=(
            "Quarterly cloud segment revenue, USD billions, calendar quarters. "
            "Microsoft: Intelligent Cloud segment (Azure dollar revenue is not "
            "disclosed - see the note below)."
        ),
        aria="Hyperscaler cloud segment revenue by quarter",
    )


def _svg_cloud_growth_chart(series: list[dict[str, Any]]) -> str:
    """Quarterly YoY growth of cloud segment revenue, one line per vendor."""
    if not series:
        return (
            '<p class="cap">Cloud growth data unavailable '
            "(data/insight/cloud_revenue.csv not loaded).</p>"
        )
    return _svg_cloud_lines(
        series,
        key="yoy_pct",
        fmt=lambda v: f"{v:.0f}%",
        end_fmt=lambda v: f"{v:+.0f}%",
        grid_step=20.0,
        caption=(
            "YoY growth of segment revenue, computed from the chained quarterly "
            "revenue - never stored. Each line starts four quarters in, at its "
            "first YoY."
        ),
        aria="Hyperscaler cloud segment revenue growth, year over year",
    )


def _cloud_notes(series: list[dict[str, Any]]) -> str:
    if not series:
        return ""
    bits = []
    for s in series:
        last = s["points"][-1]
        bit = f"{s['segment']} ${last['revenue']:.1f}B"
        if last["yoy_pct"] is not None:
            bit += f" ({last['yoy_pct']:+.0f}% YoY)"
        bits.append(bit)
    latest = max(s["points"][-1]["quarter"] for s in series)
    return (
        '<p class="cap">'
        + html.escape(f"Latest ({_quarter_label(latest)}): " + " · ".join(bits) + ". ")
        + "Microsoft does not disclose Azure revenue in dollars, so Microsoft is "
        "plotted on its Intelligent Cloud segment in both charts. Azure and other "
        "cloud services grew +43% YoY in Q2 2026 (Microsoft FY26 Q4 earnings "
        "release, 2026-07-29) - a growth rate only, shown here as text and never "
        "plotted against segment revenue. Microsoft quarters are calendar-aligned "
        "(fiscal Q4 = calendar Q2). Microsoft redefined the Intelligent Cloud "
        "segment in FY2025: quarters from Sep 2024 are as reported under the new "
        "composition, so the 2024 level shift - and the near-zero YoY prints that "
        "follow it in the chained math - are definitional, not a revenue decline "
        "(as-reported growth for the Sep 2024 quarter was +20% on the recast "
        "basis).</p>"
    )


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
<p class="sub">Where the reported numbers understate the leverage: AI capex hidden in SPVs, what credit markets charge for it, the cloud revenue funding it, and the macro figures that crack first - housing, mortgage rates, the Fed path. Data as of __ASOF__.</p>
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
<div class="chart-block"><h2>Hyperscaler cloud revenue &amp; growth</h2>
<p class="cap">The franchises funding the capex above: quarterly cloud segment revenue and its year-over-year growth for Google Cloud, AWS and Microsoft Intelligent Cloud, calendar quarters. Points only, from reported segment revenue - no projections, no interpolation.</p>
<div class="chart">__CLOUD_REV_SVG__</div>
<div class="chart">__CLOUD_GROWTH_SVG__</div>
__CLOUD_NOTES__</div>
<div class="chart-block"><h2>Section C — Macro early-warning: housing &amp; the Fed path</h2>
<p class="cap">The figures that turn before credit does: contract signings, the mortgage rate that drives them, and what futures markets charge for the Fed's next moves.</p>
<div class="chart">__HOUSING_SVG__</div>
__HOUSING_NOTES__
<div class="chart">__MORTGAGE_SVG__</div>
__MORTGAGE_NOTES__
<div class="chart">__FEDWATCH_SVG__</div>
__FEDWATCH_NOTES__</div>
<p class="note">Method: SPV estimates are anchored to named deals and spread over build years (see data/insight/spv_capex.csv); reported capex from company filings. Revenue is the calendar-year sum of quarterly us-gaap Revenues for MSFT+AMZN+GOOGL+META from SEC EDGAR companyfacts (see data/insight/revenue_big4.csv). CDS timeline points carry source + proxy labels (see data/insight/cds_spreads.csv) - add real weekly 5Y prints there with proxy_label <code>cds-print:5y</code> to grow the spread chart. Section C: housing levels are the latest NAR vintage fetched per month, each row sourced in data/insight/pending_home_sales.csv; mortgage rates are FRED MORTGAGE30US weekly observations averaged by month (data/insight/mortgage_rates.csv); FedWatch rows are dated snapshots - append new snapshots, never overwrite (data/insight/fedwatch_snapshots.csv). Cloud panel: one row per vendor-quarter in data/insight/cloud_revenue.csv - Google Cloud and AWS from company earnings releases; Microsoft Intelligent Cloud quarterly values differenced from trailing-twelve-month segment history and cross-checked to Microsoft Investor Relations annual segment totals; YoY computed from the chained series, never stored. Azure dollar revenue is not disclosed by Microsoft and is never plotted. Reported history, not a forecast.</p>
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
        .replace("__HOUSING_SVG__", _svg_housing_chart(data.get("housing", [])))
        .replace("__HOUSING_NOTES__", _housing_notes(data.get("housing", [])))
        .replace("__MORTGAGE_SVG__", _svg_mortgage_chart(data.get("mortgage", [])))
        .replace("__MORTGAGE_NOTES__", _mortgage_notes(data.get("mortgage", [])))
        .replace("__FEDWATCH_SVG__", _svg_fedwatch_chart(data.get("fedwatch", [])))
        .replace("__FEDWATCH_NOTES__", _fedwatch_notes(data.get("fedwatch", [])))
        .replace(
            "__CLOUD_REV_SVG__", _svg_cloud_revenue_chart(data.get("cloud", []))
        )
        .replace(
            "__CLOUD_GROWTH_SVG__", _svg_cloud_growth_chart(data.get("cloud", []))
        )
        .replace("__CLOUD_NOTES__", _cloud_notes(data.get("cloud", [])))
    )
    target.write_text(page)
    return target
