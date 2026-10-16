#!/usr/bin/env python3
"""Collect PPI release prints into ``config/ppi_prints.yaml`` (issue #155).

Sibling of ``scripts/collect_cpi.py`` (issue #153), same discipline:

- **As-printed percent changes** come from each release in the BLS PPI
  news-release archive
  (``https://www.bls.gov/news.release/archives/ppi_<MMDDYYYY>.htm``).
  Final demand m/m (seasonally adjusted) and y/y (unadjusted) are in
  Table A; the core aggregate (final demand less foods and energy) is
  read from its Table 1 row — its 12-month unadjusted change and the last
  of its five seasonally adjusted 1-month changes. "As printed" is
  deliberate: it is the vintage the market actually saw on the release
  morning. PPI indexes are revised for four months after publication, so
  later vintages differ — this file keeps the original prints.
- **Cross-check**: index levels from the BLS public API — ``WPUFD4``
  (final demand, NSA), ``WPSFD4`` (final demand, SA), ``WPUFD49104``
  (final demand less foods & energy, NSA), ``WPSFD49104`` (same, SA).
  All four IDs were verified against the API at implementation time
  (they return data; e.g. WPUFD4 Aug 2026 = 157.604). Computed changes
  are compared with the archive prints and any gap over 0.15pp is
  reported. Because the API serves the *current* vintage, gaps against
  as-printed values are expected wherever BLS has since revised the
  index — the warning flags them, the archive values stand.
- PPI has no entry in ``config/macro_calendar.yaml`` (that calendar's
  series contract is FOMC/CPI/PCE), so release dates come from the
  hand-verified ``RELEASE_DATES`` table below, taken from the BLS release
  schedule pages and confirmed against the archive pages themselves.
  October 2025 is absent: that release was never published (federal
  shutdown), and the September 2025 release was delayed to 2025-11-25.

Consensus (survey expectations) is **never** fetched or inferred by this
script. It comes only from the hand-verified ``CONSENSUS`` table below,
keyed by release date; every other release stores ``null``. No PPI survey
median has been hand-verified yet, so the table is empty and every PPI
print carries ``consensus: null`` — no surprises, no classifications —
until one is sourced. Add a row only with a citable source for that
specific release's survey median.

``prior`` is chained from the previous published release's actual (for
the 2026-01-14 release the previous *published* print is September 2025 —
October 2025 was never published). ``revision`` is ``null`` throughout:
the file keeps as-printed values and does not restate BLS's four-month
revisions.

Usage::

    python scripts/collect_ppi.py [--out PATH] [--start YYYY-MM-DD]
                                  [--extracts PATH]

``--extracts`` reads the four metrics per release from a JSON file
``{release_date: {reference_period, final_demand_mom, final_demand_yoy,
core_mom, core_yoy, notes?}}`` instead of fetching the archive pages —
for environments where BLS blocks the HTTP client. Extracts must be
transcribed from the official archive pages above; the API cross-check
still runs. (The 2024-11 → 2026-08 backfill was produced this way; four
archive pages — the 2026-01-14, 2026-03-18, 2026-04-14 and 2026-06-11
releases — returned HTTP 403 to every fetcher available, so those
extracts were transcribed from the following release's tables, with
core y/y computed from the API index levels; each such release carries
a ``notes`` entry in the output saying exactly that.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from portfolio_analysis.events.macro_prints import PPI_METRIC_KEYS  # noqa: E402

ARCHIVE_URL = "https://www.bls.gov/news.release/archives/ppi_{stamp}.htm"
API_URL = (
    "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    "{series}?startyear={first}&endyear={last}"
)
FINAL_DEMAND_NSA = "WPUFD4"
FINAL_DEMAND_SA = "WPSFD4"
CORE_NSA = "WPUFD49104"
CORE_SA = "WPSFD49104"
RELEASE_TIME_ET = "08:30"
CROSS_CHECK_TOLERANCE_PP = 0.15

#: PPI release dates and their reference periods, hand-verified against
#: the BLS release schedule (bls.gov/schedule) and the archive pages.
#: October 2025 has no row — the release was never published (shutdown).
RELEASE_DATES: list[tuple[str, str]] = [
    ("2024-11-14", "2024-10"),
    ("2024-12-12", "2024-11"),
    ("2025-01-14", "2024-12"),
    ("2025-02-13", "2025-01"),
    ("2025-03-13", "2025-02"),
    ("2025-04-11", "2025-03"),
    ("2025-05-15", "2025-04"),
    ("2025-06-12", "2025-05"),
    ("2025-07-16", "2025-06"),
    ("2025-08-14", "2025-07"),
    ("2025-09-10", "2025-08"),
    ("2025-11-25", "2025-09"),  # shutdown-delayed September release
    ("2026-01-14", "2025-11"),
    ("2026-01-30", "2025-12"),
    ("2026-02-27", "2026-01"),
    ("2026-03-18", "2026-02"),
    ("2026-04-14", "2026-03"),
    ("2026-05-13", "2026-04"),
    ("2026-06-11", "2026-05"),
    ("2026-07-15", "2026-06"),
    ("2026-08-13", "2026-07"),
    ("2026-09-10", "2026-08"),
    ("2026-10-15", "2026-09"),
]

#: Survey medians verified by hand for specific releases. Metrics not
#: listed for a release stay null. Never add unsourced numbers here.
#: (Empty for PPI: no survey median has been hand-verified yet.)
CONSENSUS: dict[str, dict[str, float]] = {}

_USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; openPaw-collector)"}

_MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5,
    "JUNE": 6, "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
    "NOVEMBER": 11, "DECEMBER": 12,
}


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "|", html)
    return re.sub(r"\|+", "|", text)


def _cells(text: str) -> list[str]:
    # Whitespace-only text nodes between tags strip to nothing; drop them
    # so cell positions reflect the table, not the markup's line breaks.
    return [cell for cell in (c.strip() for c in text.split("|")) if cell]


def _table1_row(cells: list[str], label: str, code: str) -> tuple[float, float]:
    """(y/y, m/m) percent changes from a Table 1 percent-change row.

    The row layout is: label | FD | <code> | relative importance |
    12-month unadjusted change | five seasonally adjusted 1-month changes
    (oldest first, so the last is the reference month). The percent table
    precedes the index-levels table in the release, and the first match
    is the percent row; values are sanity-bounded so a levels row can
    never be mistaken for it.
    """
    for i, cell in enumerate(cells):
        if cell != label and not cell.startswith(label + "("):
            continue
        window = cells[i + 1 : i + 10]
        if len(window) < 8 or window[0] != "FD" or window[1] != code:
            continue
        try:
            numbers = [float(value) for value in window[2:9]]
        except ValueError:
            continue
        yoy, mom = numbers[1], numbers[-1]
        if abs(yoy) < 50 and abs(mom) < 10:  # percents, not index levels
            return yoy, mom
    raise ValueError(f"Table 1 row for {label!r} not found")


def parse_reference_period(html: str) -> str:
    """The reference month the release describes, from its own header."""
    match = re.search(r"(\d{4}) M(\d{2}) Results", html)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    text = _strip_tags(html).upper()
    match = re.search(
        r"PRODUCER PRICE INDEXES\s*-\s*([A-Z]+)\s+(\d{4})", text
    )
    if match and match.group(1) in _MONTHS:
        return f"{match.group(2)}-{_MONTHS[match.group(1)]:02d}"
    raise ValueError("release header reference period not found")


def parse_table_1(html: str) -> dict[str, float | None]:
    """Extract the release's final demand / core prints from archive HTML.

    Final demand comes from its Table 1 row (code 4, relative importance
    100.000); core from the "Final demand less foods and energy" row
    (code 49104). For each: y/y is the 12-month unadjusted change, m/m is
    the last (reference-month) seasonally adjusted 1-month change.
    """
    cells = _cells(_strip_tags(html))
    fd_yoy, fd_mom = _table1_row(cells, "Final demand", "4")
    core_yoy, core_mom = _table1_row(
        cells, "Final demand less foods and energy", "49104"
    )
    return {
        "final_demand_mom": fd_mom,
        "final_demand_yoy": fd_yoy,
        "core_mom": core_mom,
        "core_yoy": core_yoy,
    }


def _round1(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _api_index(series: str, first_year: int, last_year: int) -> dict[tuple[int, int], float]:
    url = API_URL.format(series=series, first=first_year, last=last_year)
    payload = json.loads(_fetch(url))
    levels: dict[tuple[int, int], float] = {}
    for row in payload["Results"]["series"][0]["data"]:
        try:
            levels[(int(row["year"]), int(row["period"][1:]))] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue  # BLS publishes "-" for the cancelled Oct 2025 month
    return levels


def _pct(
    levels: dict[tuple[int, int], float], year: int, month: int, months_back: int
) -> float | None:
    back_year, back_month = year, month - months_back
    while back_month <= 0:
        back_year, back_month = back_year - 1, back_month + 12
    if months_back == 12:
        back_year, back_month = year - 1, month
    current, prior = levels.get((year, month)), levels.get((back_year, back_month))
    if current is None or prior is None:
        return None
    return _round1((current / prior - 1) * 100)


def build_payload(
    releases: list[tuple[str, str, dict[str, float | None], list[str]]],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Assemble the ppi_prints document, chaining priors in release order."""
    entries: list[dict[str, Any]] = []
    previous_actuals: dict[str, float | None] | None = None
    for release_date, reference, actuals, notes in releases:
        day = date.fromisoformat(release_date)
        consensus = CONSENSUS.get(release_date, {})
        metrics: dict[str, Any] = {}
        for key in PPI_METRIC_KEYS:
            metrics[key] = {
                "actual": actuals[key],
                "consensus": consensus.get(key),
                "prior": None if previous_actuals is None else previous_actuals[key],
                "revision": None,
            }
        entry: dict[str, Any] = {
            "release_date": release_date,
            "reference_period": reference,
            "release_time_et": RELEASE_TIME_ET,
            "url": ARCHIVE_URL.format(stamp=day.strftime("%m%d%Y")),
            "metrics": metrics,
        }
        if notes:
            entry["notes"] = notes
        entries.append(entry)
        previous_actuals = actuals
    return {
        "schema_version": 1,
        "series": "PPI",
        "as_of": as_of,
        "source": "U.S. Bureau of Labor Statistics (BLS)",
        "notes": [
            "Actuals are the as-printed percent changes from each BLS PPI release "
            "(final demand: m/m seasonally adjusted, y/y unadjusted; core = final "
            "demand less foods and energy) - the vintage the market saw on the "
            "release morning. Values are cross-checked against index levels from "
            "the BLS public API (WPUFD4 / WPSFD4, WPUFD49104 / WPSFD49104). PPI "
            "indexes are revised for four months after publication, so the API's "
            "current vintage legitimately differs from older as-printed values; "
            "the archive prints stand.",
            "Consensus is null for every backfilled release: no PPI survey median "
            "has been hand-verified yet (see CONSENSUS in scripts/collect_ppi.py). "
            "It is never estimated, and null consensus means no surprise and no "
            "macro classification for PPI days until one is sourced.",
            "Prior is the previous published release's actual. October 2025 was "
            "never published (federal shutdown) and the September 2025 release was "
            "delayed to 2025-11-25, so the 2026-01-14 release chains to September "
            "2025. There is no October 2025 row - the gap is explicit, never "
            "interpolated.",
            "Revision is null throughout: the file keeps as-printed values; BLS's "
            "four-month revisions and the annual seasonal-factor recalculation "
            "are not restated.",
            "Four releases carry a per-release note: their archive pages returned "
            "HTTP 403 to the collector's fetcher, so their values were transcribed "
            "from the following release's tables (first revised vintage) with "
            "core y/y computed from the BLS API index levels.",
        ],
        "releases": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "config" / "ppi_prints.yaml")
    parser.add_argument("--start", default="2024-11-01", help="first release date to collect")
    parser.add_argument("--extracts", type=Path, default=None, help="offline Table 1 extracts JSON")
    args = parser.parse_args(argv)

    extracts: dict[str, Any] = {}
    if args.extracts is not None:
        extracts = json.loads(args.extracts.read_text())

    releases: list[tuple[str, str, dict[str, float | None], list[str]]] = []
    for release_date, reference in RELEASE_DATES:
        if release_date < args.start:
            continue
        if args.extracts is not None:
            if release_date not in extracts:
                print(f"collect_ppi: WARNING no extract for {release_date}; skipped")
                continue
            extract = extracts[release_date]
            if extract["reference_period"] != reference:
                print(
                    f"collect_ppi: extract reference_period {extract['reference_period']} "
                    f"for {release_date} disagrees with the schedule ({reference})",
                    file=sys.stderr,
                )
                return 1
            actuals = {key: extract[key] for key in PPI_METRIC_KEYS}
            notes = list(extract.get("notes") or [])
            origin = "extracts"
        else:
            stamp = date.fromisoformat(release_date).strftime("%m%d%Y")
            html = _fetch(ARCHIVE_URL.format(stamp=stamp))
            parsed_reference = parse_reference_period(html)
            if parsed_reference != reference:
                print(
                    f"collect_ppi: {release_date} header reference {parsed_reference} "
                    f"disagrees with the schedule ({reference})",
                    file=sys.stderr,
                )
                return 1
            actuals = parse_table_1(html)
            notes = []
            origin = "archive"
        releases.append((release_date, reference, actuals, notes))
        print(f"collect_ppi: {release_date} ({origin}) {actuals}")

    if not releases:
        print("collect_ppi: no PPI releases collected", file=sys.stderr)
        return 1

    # Cross-check prints against API index levels (warnings only). The API
    # is the current vintage; PPI's four-month revision window means gaps
    # against as-printed values are expected — the archive prints stand.
    try:
        first_year = int(releases[0][1][:4]) - 2
        last_year = int(releases[-1][1][:4])
        series_levels = {
            "final_demand_yoy": (_api_index(FINAL_DEMAND_NSA, first_year, last_year), 12),
            "final_demand_mom": (_api_index(FINAL_DEMAND_SA, first_year, last_year), 1),
            "core_yoy": (_api_index(CORE_NSA, first_year, last_year), 12),
            "core_mom": (_api_index(CORE_SA, first_year, last_year), 1),
        }
        for release_date, reference, actuals, _notes in releases:
            year, month = int(reference[:4]), int(reference[5:7])
            for key, (levels, months_back) in series_levels.items():
                printed = actuals[key]
                computed = _pct(levels, year, month, months_back)
                if printed is None or computed is None:
                    continue
                if abs(printed - computed) > CROSS_CHECK_TOLERANCE_PP:
                    print(
                        f"collect_ppi: WARNING {release_date} {key}: printed {printed} "
                        f"vs API-computed {computed} (post-print revision vintage gap)"
                    )
    except Exception as exc:  # cross-check is advisory; prints stand on the archive
        print(f"collect_ppi: API cross-check unavailable ({type(exc).__name__}: {exc})")

    payload = build_payload(releases, as_of=releases[-1][0])
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"collect_ppi: wrote {len(releases)} releases to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
