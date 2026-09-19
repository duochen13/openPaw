"""Quarterly fundamentals from SEC EDGAR companyfacts (issue #28).

Price history is local, but P/E needs earnings. The source is SEC EDGAR's
companyfacts API: free, no API key, no daily quota, and already a trusted
vendor in this project (events/edgar.py). It also beats aggregator APIs on
correctness: every XBRL fact carries its filing date, so TTM EPS is
point-in-time - a quarter enters the series only once actually filed, and
the chart can never peek at earnings before they existed.

Source selection, measured 2026-09-19:
- Yahoo quoteSummary was tried first (same vendor as prices.py, no key).
  It 401s without a cookie/crumb handshake, and Yahoo refuses to issue the
  crumb to datacenter IPs (401/429 on the crumb endpoint). Unusable from
  the machines that run the scheduled jobs.
- Alpha Vantage EARNINGS was considered next, but the free tier is 25
  requests/day shared with the news pipeline, and no key is configured.
- EDGAR companyfacts works from here with a descriptive User-Agent, has
  no quota, and the portfolio config already carries a CIK per ticker.

The same quarterly series backs issue #29 (per-stock business KPIs): that
issue reuses the fetch/store plumbing here and adds its own metric config.

XBRL parsing notes:
- ``EarningsPerShareDiluted`` in ``USD/shares``. A 10-Q files both the
  quarter's EPS (~90-day duration) and year-to-date EPS (~270-day); only
  the ~90-day units are quarterly EPS. Duration, not hope, separates them.
- **Do not key periods by (fy, fp).** Those fields describe the *filing*,
  not the fact: a 10-Q's comparative prior-year column carries the filing's
  fy with the prior year's quarter dates. Periods are keyed by
  (start, end); measured 2026-09-19, keying by (fy, fp) mixed 2022
  quarters into 2023 and produced nonsense like a negative derived Q4.
- Q4 is never filed standalone: it is derived as FY EPS (10-K) minus the
  three 10-Q quarters of that fiscal year. All four components must exist.
- Point-in-time vs restatements: a period keeps its *earliest* filing date
  (when the market first knew it) but the *latest* filed value (restated
  figures, e.g. after stock splits, stay consistent with split-adjusted
  prices). A quarter never waits a year for a comparative reprint.
- Amendments (``/A`` forms) supersede originals only as the latest value.
- Negative or zero TTM EPS makes P/E meaningless (not merely large). Those
  days render as gaps, the same "no made-up numbers" rule the factor
  panels keep.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

#: GetJson seam, matching the events sources: (provider, url, *, daily_limit, max_age) -> payload.
GetJson = Callable[..., dict[str, Any]]

_FORMS_QUARTER = frozenset({"10-Q", "10-Q/A"})
_FORMS_ANNUAL = frozenset({"10-K", "10-K/A"})

#: A fiscal quarter lasts ~90 days; a fiscal year ~365. Units outside these
#: bands are YTD figures or stubs, not the period they claim in `fp`.
_QUARTER_DAYS = (80, 100)
_YEAR_DAYS = (350, 380)

#: Year-to-date spans run from one quarter (Q1) to the full year. Cash-flow
#: facts (capex) are only ever filed YTD, never as standalone quarters.
_YTD_DAYS = (80, 380)

#: A TTM P/E is only defined once four full quarters are known. Fewer than
#: four is not "approximately TTM"; those days stay gaps.
_TTM_QUARTERS = 4


class VendorResponseError(RuntimeError):
    """The vendor answered, but not with the data we asked for."""


def fetch_companyfacts(cik: int, get_json: GetJson) -> dict[str, Any]:
    """Raw companyfacts payload for ``cik`` via the injected HTTP seam."""
    if cik <= 0:
        raise ValueError("EDGAR requires a positive CIK")
    return get_json(
        "edgar",
        _COMPANYFACTS_URL.format(cik=cik),
        daily_limit=None,
        max_age=7 * 86400,
    )


def _duration_days(unit: dict[str, Any]) -> int | None:
    try:
        start = date.fromisoformat(str(unit["start"]))
        end = date.fromisoformat(str(unit["end"]))
    except (KeyError, ValueError):
        return None
    return (end - start).days


def _collect_periods(
    units: list[Any],
    forms: frozenset[str],
    days: tuple[int, int],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Dedupe XBRL units by their own (start, end) period.

    Returns ``(start, end) -> {"end", "filed", "val"}`` where ``filed`` is
    the earliest filing date (point-in-time: when the market first knew)
    and ``val`` is the latest filed value (restatements win).
    """
    periods: dict[tuple[str, str], dict[str, Any]] = {}
    for unit in units:
        if not isinstance(unit, dict):
            continue
        if unit.get("form") not in forms:
            continue
        span = _duration_days(unit)
        val = unit.get("val")
        if span is None or not days[0] <= span <= days[1]:
            continue
        if not isinstance(val, (int, float)) or val != val:
            continue  # NaN guard
        try:
            start, end, filed = (
                str(unit["start"]),
                str(unit["end"]),
                str(unit["filed"]),
            )
            date.fromisoformat(end)
            date.fromisoformat(filed)
        except (KeyError, ValueError):
            continue
        key = (start, end)
        slot = periods.get(key)
        if slot is None:
            periods[key] = {"end": end, "filed": filed, "val": float(val),
                            "latest": filed}
        else:
            slot["filed"] = min(slot["filed"], filed)
            if filed >= slot["latest"]:
                slot["val"] = float(val)
                slot["latest"] = filed
    return periods


def _get_units(
    facts: dict[str, Any], taxonomy: str, tag: str, unit: str
) -> list[Any] | None:
    """XBRL unit list for ``(taxonomy, tag, unit)``; None when absent.

    Unlike the EPS path, KPI parsing treats a missing tag as "no data"
    rather than an error: filers simply do not tag every concept (META and
    GOOGL have no GrossProfit; NOW abandoned SubscriptionRevenue in 2014).
    """
    node: Any = facts
    for key in ("facts", taxonomy, tag, "units", unit):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, list) else None


def _derive_q4_rows(
    quarters: dict[tuple[str, str], dict[str, Any]],
    annuals: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Standalone 10-Q quarters plus Q4 derived as FY minus Q1-Q3.

    Each row is ``{"quarter", "filed", "value"}`` oldest first. A fiscal
    year contributes Q4 only when the annual figure and all three quarters
    are present; a restated 10-K never double-counts Q4.
    """
    out: list[dict[str, Any]] = [
        {"quarter": p["end"], "filed": p["filed"], "value": p["val"]}
        for p in quarters.values()
    ]
    for (_start, end), ann in sorted(annuals.items()):
        # The three 10-Q quarters of this fiscal year: latest quarter-ends
        # strictly before the year end, all within the ~year preceding it.
        prior = sorted(
            (q_end, q)
            for (_q_start, q_end), q in quarters.items()
            if q_end < end
        )
        three = [q for _, q in prior[-3:]]
        if len(three) < 3:
            continue
        earliest = min(str(q["end"]) for q in three)
        if (date.fromisoformat(end) - date.fromisoformat(earliest)).days > 370:
            continue
        q4 = float(ann["val"]) - sum(float(q["val"]) for q in three)
        out.append({"quarter": end, "filed": ann["filed"], "value": q4})
    # A restated 10-K must not double-count Q4; one row per quarter end.
    deduped: dict[str, dict[str, Any]] = {}
    for row in out:
        deduped[str(row["quarter"])] = row
    return sorted(deduped.values(), key=lambda r: str(r["quarter"]))


def _parse_ytd_quarters(units: list[Any]) -> list[dict[str, Any]]:
    """De-accumulate YTD facts (cash-flow style) into standalone quarters.

    10-Q/10-K cash flow statements report year-to-date figures, so a
    quarter is YTD(end) minus the previous YTD of the same fiscal year.
    Fiscal years are grouped by the YTD *start* date - never by (fy, fp),
    which describe the filing, not the fact (same trap as issue #28). A
    break in the YTD chain (missing 10-Q) leaves a gap for that quarter:
    the later YTD becomes the new baseline, so a gap never silently
    becomes a two-quarter sum. ``filed`` is the filing that revealed the
    quarter: the later YTD's filing date.
    """
    periods = _collect_periods(units, _FORMS_QUARTER | _FORMS_ANNUAL, _YTD_DAYS)
    by_start: dict[str, list[dict[str, Any]]] = {}
    for (start, _end), p in periods.items():
        by_start.setdefault(start, []).append(p)
    out: list[dict[str, Any]] = []
    for start in sorted(by_start):
        chain = sorted(by_start[start], key=lambda p: str(p["end"]))
        prev_end: str | None = None
        prev_val = 0.0
        start_d = date.fromisoformat(start)
        for p in chain:
            end_d = date.fromisoformat(str(p["end"]))
            if prev_end is None:
                gap = (end_d - start_d).days
            else:
                gap = (end_d - date.fromisoformat(prev_end)).days
            if _QUARTER_DAYS[0] <= gap <= _QUARTER_DAYS[1]:
                out.append(
                    {
                        "quarter": p["end"],
                        "filed": p["filed"],
                        "value": float(p["val"]) - prev_val,
                    }
                )
                prev_end, prev_val = str(p["end"]), float(p["val"])
            else:
                # Chain broken, or the first YTD is not a single quarter:
                # this YTD becomes the new baseline, no quarter derived.
                prev_end, prev_val = str(p["end"]), float(p["val"])
    deduped: dict[str, dict[str, Any]] = {}
    for row in out:
        deduped[str(row["quarter"])] = row
    return sorted(deduped.values(), key=lambda r: str(r["quarter"]))


def _collect_instant(units: list[Any]) -> list[dict[str, Any]]:
    """Point-in-time facts (balance-sheet style): one value per end date.

    These carry no start date, so periods are keyed by ``end`` alone. Same
    dedup semantics as the duration facts: earliest filing date
    (point-in-time) with the latest filed value (restatements win).
    """
    out: dict[str, dict[str, Any]] = {}
    for unit in units:
        if not isinstance(unit, dict):
            continue
        if unit.get("form") not in _FORMS_QUARTER | _FORMS_ANNUAL:
            continue
        val = unit.get("val")
        if not isinstance(val, (int, float)) or val != val:
            continue  # NaN guard
        try:
            end, filed = str(unit["end"]), str(unit["filed"])
            date.fromisoformat(end)
            date.fromisoformat(filed)
        except (KeyError, ValueError):
            continue
        slot = out.get(end)
        if slot is None:
            out[end] = {
                "quarter": end, "filed": filed,
                "value": float(val), "latest": filed,
            }
        else:
            slot["filed"] = min(str(slot["filed"]), filed)
            if filed >= str(slot["latest"]):
                slot["value"] = float(val)
                slot["latest"] = filed
    return sorted(out.values(), key=lambda r: str(r["quarter"]))


def parse_quarterly_fact(
    facts: dict[str, Any],
    candidates: list[tuple[str, str, str]],
    *,
    period: str = "quarter",
) -> list[tuple[str, str, float]]:
    """Quarterly ``(quarter_end, filed, value)`` for an XBRL fact, oldest first.

    ``candidates`` are ``(taxonomy, tag, unit)`` triples, each parsed
    independently and merged per quarter preferring the tag with the most
    recent coverage. Filers rename tags over time - NOW's quarterly
    ``Revenues`` stops in 2018 while
    ``RevenueFromContractWithCustomerExcludingAssessedTax`` continues - so
    merging by recency, not first-non-empty, is what keeps history
    continuous. Tags with no data are skipped, never an error.

    ``period`` selects the filing shape: ``"quarter"`` for standalone
    quarterly durations with derived Q4 (income-statement style),
    ``"ytd"`` for year-to-date facts de-accumulated into quarters
    (cash-flow style), ``"instant"`` for point-in-time facts keyed by end
    date (balance-sheet style).
    """
    if period not in ("quarter", "ytd", "instant"):
        raise ValueError(f"unknown period shape {period!r}")
    parsed: list[list[tuple[str, str, float]]] = []
    for taxonomy, tag, unit in candidates:
        units = _get_units(facts, taxonomy, tag, unit)
        if not units:
            continue
        if period == "quarter":
            quarters = _collect_periods(units, _FORMS_QUARTER, _QUARTER_DAYS)
            annuals = _collect_periods(units, _FORMS_ANNUAL, _YEAR_DAYS)
            rows = _derive_q4_rows(quarters, annuals)
        elif period == "ytd":
            rows = _parse_ytd_quarters(units)
        else:
            rows = _collect_instant(units)
        series = [
            (str(r["quarter"]), str(r["filed"]), float(r["value"]))
            for r in rows
        ]
        if series:
            parsed.append(series)
    if not parsed:
        return []
    ranked = sorted(parsed, key=lambda s: s[-1][0], reverse=True)
    merged: dict[str, tuple[str, float]] = {}
    for series in ranked:
        for q, filed, val in series:
            merged.setdefault(q, (filed, val))
    return [(q, filed, val) for q, (filed, val) in sorted(merged.items())]


def parse_quarterly_eps(facts: dict[str, Any]) -> list[dict[str, object]]:
    """Fiscal quarters with diluted EPS, oldest first.

    Each entry is ``{"quarter": end_date, "filed": filed_date, "eps": float}``.
    Q1-Q3 come from 10-Q filings; Q4 is derived as FY (10-K) minus Q1-Q3 and
    is dated to the fiscal year end. A fiscal year contributes Q4 only when
    the annual figure and all three quarters are present.
    """
    units = _get_units(facts, "us-gaap", "EarningsPerShareDiluted", "USD/shares")
    if units is None:
        raise VendorResponseError(
            "companyfacts has no EarningsPerShareDiluted in USD/shares"
        )
    quarters = _collect_periods(units, _FORMS_QUARTER, _QUARTER_DAYS)
    annuals = _collect_periods(units, _FORMS_ANNUAL, _YEAR_DAYS)
    return [
        {"quarter": r["quarter"], "filed": r["filed"], "eps": r["value"]}
        for r in _derive_q4_rows(quarters, annuals)
    ]


def ttm_eps_on(
    day: str, quarters: list[tuple[str, str, float]]
) -> float | None:
    """TTM EPS knowable on ``day``: the four latest quarters filed by then.

    ``quarters`` is ``(quarter_end, filed, eps)``. Filing date, not quarter
    end, gates eligibility: the chart never sees earnings before they
    existed.
    """
    eligible = sorted(
        (end, eps) for end, filed, eps in quarters if filed <= day
    )
    if len(eligible) < _TTM_QUARTERS:
        return None
    return sum(eps for _, eps in eligible[-_TTM_QUARTERS:])


def pe_series(
    prices: dict[str, float], quarters: list[tuple[str, str, float]]
) -> dict[str, dict[str, float | None]]:
    """Daily rolling TTM P/E: ``date -> {"pe", "ttm_eps"}``.

    ``pe`` is None where TTM EPS is unknown (fewer than four quarters filed)
    or non-positive (a P/E over negative earnings is meaningless, not large).
    """
    out: dict[str, dict[str, float | None]] = {}
    for day in sorted(prices):
        ttm = ttm_eps_on(day, quarters)
        pe = prices[day] / ttm if ttm is not None and ttm > 0 else None
        out[day] = {"pe": pe, "ttm_eps": ttm}
    return out
