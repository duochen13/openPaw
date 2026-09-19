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

_EPS_PATH = ("facts", "us-gaap", "EarningsPerShareDiluted", "units", "USD/shares")

_FORMS_QUARTER = frozenset({"10-Q", "10-Q/A"})
_FORMS_ANNUAL = frozenset({"10-K", "10-K/A"})

#: A fiscal quarter lasts ~90 days; a fiscal year ~365. Units outside these
#: bands are YTD figures or stubs, not the period they claim in `fp`.
_QUARTER_DAYS = (80, 100)
_YEAR_DAYS = (350, 380)

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


def parse_quarterly_eps(facts: dict[str, Any]) -> list[dict[str, object]]:
    """Fiscal quarters with diluted EPS, oldest first.

    Each entry is ``{"quarter": end_date, "filed": filed_date, "eps": float}``.
    Q1-Q3 come from 10-Q filings; Q4 is derived as FY (10-K) minus Q1-Q3 and
    is dated to the fiscal year end. A fiscal year contributes Q4 only when
    the annual figure and all three quarters are present.
    """
    node: Any = facts
    for key in _EPS_PATH:
        if not isinstance(node, dict) or key not in node:
            raise VendorResponseError(
                "companyfacts has no EarningsPerShareDiluted in USD/shares"
            )
        node = node[key]
    if not isinstance(node, list):
        raise VendorResponseError("companyfacts EPS units are not a list")

    quarters = _collect_periods(node, _FORMS_QUARTER, _QUARTER_DAYS)
    annuals = _collect_periods(node, _FORMS_ANNUAL, _YEAR_DAYS)

    out: list[dict[str, object]] = [
        {"quarter": p["end"], "filed": p["filed"], "eps": p["val"]}
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
        out.append({"quarter": end, "filed": ann["filed"], "eps": q4})
    # A restated 10-K must not double-count Q4; one row per quarter end.
    deduped: dict[str, dict[str, object]] = {}
    for row in out:
        deduped[str(row["quarter"])] = row
    return sorted(deduped.values(), key=lambda r: str(r["quarter"]))


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
