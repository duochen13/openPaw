#!/usr/bin/env python3
"""Collect CPI release prints into ``config/cpi_prints.yaml`` (issue #153).

Data sources (BLS only — no third-party aggregators):

- **As-printed percent changes** come from Table A of each release in the
  BLS news-release archive
  (``https://www.bls.gov/news.release/archives/cpi_<MMDDYYYY>.htm``).
  "As printed" is deliberate: it is the vintage the market actually saw on
  the release morning. Seasonally adjusted m/m values are later revised by
  BLS's annual factor recalculation; this file keeps the original prints.
- **Cross-check**: headline index levels from the BLS public API
  (``CUUR0000SA0`` not seasonally adjusted, ``CUSR0000SA0`` seasonally
  adjusted). Computed headline changes are compared with the Table A
  prints and any gap over 0.15pp is reported. (The API vintage reflects
  the latest seasonal factors, so small m/m gaps after a February
  recalculation are expected; y/y from the NSA index should match.)
- The task brief named ``CUSR0000SA1L1E`` as the core index series, but
  the BLS API answers "Series does not exist" for it (and for
  ``CUUR0000SA1L1E``), so core percent changes are taken from Table A —
  the release archive is an explicitly approved official source.

Consensus (survey expectations) is **never** fetched or inferred by this
script. It comes only from the hand-verified ``CONSENSUS`` table below,
keyed by release date; every other release stores ``null``. Add a row only
with a citable source for that specific release's survey median.

``prior`` is chained from the previous release's printed actual (for the
2025-12-18 release the previous *published* print is September 2025 —
October 2025 was never published). ``revision`` is ``null`` throughout:
the NSA series is never revised, and SA revisions arrive only through the
annual seasonal-factor recalculation, which this file does not restate.

Usage::

    python scripts/collect_cpi.py [--calendar PATH] [--out PATH]
                                  [--start YYYY-MM-DD] [--extracts PATH]

``--extracts`` reads Table A values from a JSON file
``{release_date: {headline_mom, headline_yoy, core_mom, core_yoy}}``
instead of fetching the archive pages — for environments where BLS blocks
the HTTP client. Extracts must be transcribed from the official archive
pages above; the API cross-check still runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from portfolio_analysis.events.macro import MacroSource  # noqa: E402
from portfolio_analysis.events.macro_prints import METRIC_KEYS  # noqa: E402

ARCHIVE_URL = "https://www.bls.gov/news.release/archives/cpi_{stamp}.htm"
API_URL = (
    "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    "{series}?startyear={first}&endyear={last}"
)
HEADLINE_NSA = "CUUR0000SA0"
HEADLINE_SA = "CUSR0000SA0"
RELEASE_TIME_ET = "08:30"
CROSS_CHECK_TOLERANCE_PP = 0.15

#: Survey medians verified by hand for specific releases (issue #153
#: task verification, from the 2026-10-14 release coverage). Metrics not
#: listed for a release stay null. Never add unsourced numbers here.
CONSENSUS: dict[str, dict[str, float]] = {
    "2026-10-14": {"headline_yoy": 3.6, "core_mom": 0.2, "core_yoy": 2.5},
}

_USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; openPaw-collector)"}


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "|", html)
    return re.sub(r"\|+", "|", text)


def _numbers_after(text: str, label: str) -> list[float | None]:
    """Numeric cells following ``label`` in a tag-stripped Table A row."""
    start = text.index(label) + len(label)
    cells: list[float | None] = []
    for cell in text[start:].split("|"):
        cell = cell.strip()
        if not cell:
            continue
        if cell == "-":
            cells.append(None)
            continue
        try:
            cells.append(float(cell))
        except ValueError:
            break
        if len(cells) == 8:  # 7 m/m columns + the 12-month column
            break
    return cells


def parse_table_a(html: str) -> dict[str, float | None]:
    """Extract the release's own-month Table A prints from archive HTML.

    Returns headline/core m/m (seasonally adjusted, last m/m column) and
    y/y (unadjusted 12-month column). A ``-`` cell (not published, e.g.
    the shutdown-affected November 2025 release) parses to ``None``.
    """
    text = _strip_tags(html)
    anchor = text.index("Table A")
    section = text[anchor:]
    headline = _numbers_after(section, "All items")
    core = _numbers_after(section, "All items less food and energy")
    if len(headline) < 8 or len(core) < 8:
        raise ValueError("Table A rows not found or truncated")
    return {
        "headline_mom": headline[6],
        "headline_yoy": headline[7],
        "core_mom": core[6],
        "core_yoy": core[7],
    }


def _round1(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _api_index(series: str, first_year: int, last_year: int) -> dict[tuple[int, int], float]:
    payload = json.loads(_fetch(API_URL.format(series=series, first=first_year, last=last_year)))
    levels: dict[tuple[int, int], float] = {}
    for row in payload["Results"]["series"][0]["data"]:
        try:
            levels[(int(row["year"]), int(row["period"][1:]))] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue  # BLS publishes "-" for the cancelled Oct 2025 month
    return levels


def _pct(levels: dict[tuple[int, int], float], year: int, month: int, months_back: int) -> float | None:
    back_year, back_month = year, month - months_back
    while back_month <= 0:
        back_year, back_month = back_year - 1, back_month + 12
    if months_back == 12:
        back_year, back_month = year - 1, month
    current, prior = levels.get((year, month)), levels.get((back_year, back_month))
    if current is None or prior is None:
        return None
    return _round1((current / prior - 1) * 100)


def reference_period(release: date) -> str:
    """The reference month of a CPI release: the month before it."""
    first = release.replace(day=1)
    previous = first - timedelta(days=1)
    return f"{previous.year:04d}-{previous.month:02d}"


def build_payload(
    releases: list[tuple[str, dict[str, float | None]]],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Assemble the cpi_prints document, chaining priors in release order."""
    entries: list[dict[str, Any]] = []
    previous_actuals: dict[str, float | None] | None = None
    for release_date, actuals in releases:
        day = date.fromisoformat(release_date)
        consensus = CONSENSUS.get(release_date, {})
        metrics: dict[str, Any] = {}
        for key in METRIC_KEYS:
            metrics[key] = {
                "actual": actuals[key],
                "consensus": consensus.get(key),
                "prior": None if previous_actuals is None else previous_actuals[key],
                "revision": None,
            }
        entries.append(
            {
                "release_date": release_date,
                "reference_period": reference_period(day),
                "release_time_et": RELEASE_TIME_ET,
                "url": ARCHIVE_URL.format(stamp=day.strftime("%m%d%Y")),
                "metrics": metrics,
            }
        )
        previous_actuals = actuals
    return {
        "schema_version": 1,
        "series": "CPI",
        "as_of": as_of,
        "source": "U.S. Bureau of Labor Statistics (BLS)",
        "notes": [
            "Actuals are the as-printed Table A percent changes from each BLS release "
            "(m/m seasonally adjusted, y/y unadjusted) - the vintage the market saw on "
            "the release morning. Headline values are cross-checked against index levels "
            "from the BLS public API (CUUR0000SA0 / CUSR0000SA0).",
            "Consensus is stored only where a survey median was verified by hand for "
            "that release (see CONSENSUS in scripts/collect_cpi.py); it is null elsewhere "
            "and is never estimated.",
            "Prior is the previous published release's actual. October 2025 was never "
            "published (federal shutdown), so the 2025-12-18 release chains to September "
            "2025 and its 1-month changes are null - BLS published only a 2-month change "
            "for November 2025.",
            "Revision is null throughout: the not-seasonally-adjusted series is never "
            "revised, and seasonally adjusted values change only via the annual February "
            "seasonal-factor recalculation, which this file does not restate.",
        ],
        "releases": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, default=PROJECT_ROOT / "config" / "macro_calendar.yaml")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "config" / "cpi_prints.yaml")
    parser.add_argument("--start", default="2024-11-01", help="first release date to collect")
    parser.add_argument("--extracts", type=Path, default=None, help="offline Table A extracts JSON")
    args = parser.parse_args(argv)

    calendar = MacroSource(args.calendar)
    release_dates = [
        row["date"] for row in calendar.catalog()["CPI"] if row["date"] >= args.start
    ]
    if not release_dates:
        print("collect_cpi: no CPI releases on or after", args.start, file=sys.stderr)
        return 1

    extracts: dict[str, Any] = {}
    if args.extracts is not None:
        extracts = json.loads(args.extracts.read_text())

    releases: list[tuple[str, dict[str, float | None]]] = []
    for release_date in release_dates:
        if release_date in extracts:
            actuals = {key: extracts[release_date][key] for key in METRIC_KEYS}
            origin = "extracts"
        else:
            stamp = date.fromisoformat(release_date).strftime("%m%d%Y")
            actuals = parse_table_a(_fetch(ARCHIVE_URL.format(stamp=stamp)))
            origin = "archive"
        releases.append((release_date, actuals))
        print(f"collect_cpi: {release_date} ({origin}) {actuals}")

    # Cross-check headline prints against API index levels (warnings only).
    try:
        first_year = int(release_dates[0][:4]) - 2
        last_year = int(release_dates[-1][:4])
        nsa = _api_index(HEADLINE_NSA, first_year, last_year)
        sa = _api_index(HEADLINE_SA, first_year, last_year)
        for release_date, actuals in releases:
            ref = reference_period(date.fromisoformat(release_date))
            year, month = int(ref[:4]), int(ref[5:7])
            for key, computed in (
                ("headline_yoy", _pct(nsa, year, month, 12)),
                ("headline_mom", _pct(sa, year, month, 1)),
            ):
                printed = actuals[key]
                if printed is None or computed is None:
                    continue
                if abs(printed - computed) > CROSS_CHECK_TOLERANCE_PP:
                    print(
                        f"collect_cpi: WARNING {release_date} {key}: printed {printed} "
                        f"vs API-computed {computed} (seasonal-revision vintage gap)"
                    )
    except Exception as exc:  # cross-check is advisory; prints stand on the archive
        print(f"collect_cpi: API cross-check unavailable ({type(exc).__name__}: {exc})")

    payload = build_payload(releases, as_of=release_dates[-1])
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"collect_cpi: wrote {len(releases)} releases to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
