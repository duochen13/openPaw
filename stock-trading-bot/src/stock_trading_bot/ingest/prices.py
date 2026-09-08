"""Raw OHLCV ingestion (spec §5.4).

Deliberately fetches RAW prices, never a vendor's adjusted series. An adjusted
close is retroactively revised - a split rewrites every prior adjusted value -
so consuming it directly is a leak. Adjustment factors are computed as-of from
the corporate_action table instead. See ingest/corporate_actions.py.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import UTC, datetime

import requests

from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.timestamps import known_at_for, to_iso

_STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
_UA = "stock-trading-bot/0.1 (research)"

# US equity sessions close at 16:00 ET, which is 20:00 UTC during EDT.
# The latency budget, not this value, governs availability.
_SESSION_CLOSE_HOUR_UTC = 20


def _session_close(session_date: str) -> str:
    """Canonical event_time for a session.

    Built through to_iso rather than by string concatenation: a hand-assembled
    timestamp is the same instant as the canonical form but sorts differently,
    which silently breaks the ordering the point-in-time gateway relies on.
    """
    year, month, day = (int(part) for part in session_date.split("-"))
    return to_iso(
        datetime(year, month, day, _SESSION_CLOSE_HOUR_UTC, tzinfo=UTC)
    )


def _http_get(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_stooq(
    ticker: str, observed_at: datetime, latency_budget: Mapping[str, int]
) -> list[dict[str, object]]:
    """Fetch raw daily bars from stooq, shaped for Store.insert_price_bar."""
    symbol = safe_ticker_component(ticker)
    text = _http_get(_STOOQ_URL.format(symbol=symbol.lower()))
    known_at = to_iso(known_at_for(observed_at, "stooq", latency_budget))
    observed_iso = to_iso(observed_at)

    bars: list[dict[str, object]] = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("Date"):
            continue
        session = row["Date"]
        bars.append({
            "ticker": symbol,
            "session_date": session,
            "event_time": _session_close(session),
            "observed_at": observed_iso,
            "known_at": known_at,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
            "source": "stooq",
        })
    return bars
