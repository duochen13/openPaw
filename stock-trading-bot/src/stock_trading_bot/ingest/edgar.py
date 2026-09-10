"""SEC EDGAR XBRL companyfacts ingestion (spec §3.4, §5.3).

EDGAR is the one genuinely point-in-time fundamentals source available for
free: every fact carries the accession and filing date of the document that
disclosed it. So `known_at` derives from the FILING date, not from when we
happened to scrape it - a 10-Q filed in April was knowable in April, and
treating it as knowable only from today's scrape would throw away most of the
usable history.

Restatements append. A 10-Q/A produces a new row with the same fiscal_period,
a different accession, and a later known_at. Nothing is ever overwritten, so a
backtest standing before the amendment still sees the original figure.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.timestamps import to_iso

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# SEC requires a descriptive User-Agent with contact information for automated
# access. Anonymous scraping gets rate-limited or blocked.
_UA = "stock-trading-bot/0.1 (research; contact via repository)"


def _http_get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=60)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _filing_instant(filed: str) -> datetime:
    """The filing date as an aware UTC datetime.

    EDGAR reports a date, not a time. Midnight UTC is earlier than any plausible
    real filing moment, so the latency budget - not this value - is what keeps
    the fact from appearing usable before it was.
    """
    return datetime.fromisoformat(filed).replace(tzinfo=UTC)


def fetch_facts(
    ticker: str,
    cik: int,
    concepts: Sequence[str],
    observed_at: datetime,
    latency_budget: Mapping[str, int],
) -> list[dict[str, object]]:
    """Fetch XBRL facts shaped for Store.insert_fundamental_fact."""
    symbol = safe_ticker_component(ticker)
    payload = _http_get_json(_FACTS_URL.format(cik=cik))
    observed_iso = to_iso(observed_at)
    latency = timedelta(seconds=latency_budget["edgar"])

    rows: list[dict[str, object]] = []
    us_gaap: dict[str, Any] = payload.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        units: dict[str, Any] = us_gaap.get(concept, {}).get("units", {})
        for unit, entries in units.items():
            for entry in entries:
                if not entry.get("fp") or not entry.get("fy"):
                    continue
                filed = _filing_instant(entry["filed"])
                rows.append({
                    "ticker": symbol,
                    "concept": concept,
                    "unit": unit,
                    "fiscal_period": f"{entry['fy']}{entry['fp']}",
                    "value": float(entry["val"]),
                    "accession": entry["accn"],
                    "event_time": to_iso(filed),
                    "observed_at": observed_iso,
                    "known_at": to_iso(filed + latency),
                    # Canonical form, not the bare EDGAR date string: the
                    # column's CHECK constraint requires it, and a mixed
                    # spelling would sort wrongly against the others.
                    "valid_from": to_iso(filed),
                    "source": "edgar",
                })
    return rows
