"""Raw OHLCV ingestion (spec §5.4).

Deliberately fetches RAW prices, never a vendor's adjusted series. An adjusted
close is retroactively revised - a split rewrites every prior adjusted value -
so consuming it directly is a leak. Adjustment factors are computed as-of from
the corporate_action table instead. See ingest/corporate_actions.py.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.timestamps import known_at_for, to_iso

_STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
_YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range={range_}&interval=1d"
)
_STOOQ_HEADER = "Date,Open,High,Low,Close,Volume"
_UA = "stock-trading-bot/0.1 (research)"

# US equity sessions close at 16:00 ET, which is 20:00 UTC during EDT.
# The latency budget, not this value, governs availability.
_SESSION_CLOSE_HOUR_UTC = 20

#: The OHLCV fields every adapter must supply.
_PRICE_FIELDS = ("open", "high", "low", "close", "volume")


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


class VendorResponseError(RuntimeError):
    """The vendor answered, but not with the data we asked for."""


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
    # stooq answers an anti-bot challenge with HTTP 200 and an HTML body. Parsed
    # as CSV that yields zero rows, which would look like "this ticker has no
    # history" instead of "the vendor did not answer". Refuse it.
    if not text.lstrip().startswith(_STOOQ_HEADER):
        raise VendorResponseError(
            f"stooq did not return CSV for {symbol}; got {text[:80]!r}"
        )
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


def _http_get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def fetch_yahoo(
    ticker: str,
    observed_at: datetime,
    latency_budget: Mapping[str, int],
    range_: str = "2y",
) -> list[dict[str, object]]:
    """Fetch raw daily bars from Yahoo's chart API.

    Reads `indicators.quote`, which is unadjusted, and deliberately ignores
    `indicators.adjclose`: an adjusted series is retroactively revised, so
    consuming it would bake a future split into past prices.
    """
    symbol = safe_ticker_component(ticker)
    payload = _http_get_json(_YAHOO_URL.format(symbol=symbol, range_=range_))
    results = payload.get("chart", {}).get("result")
    if not results:
        error = payload.get("chart", {}).get("error")
        raise VendorResponseError(f"yahoo returned no result for {symbol}: {error!r}")

    result = results[0]
    timestamps: Sequence[int] = result.get("timestamp") or []
    quote: dict[str, Sequence[float | None]] = result["indicators"]["quote"][0]
    # The exchange's UTC offset, so a timestamp maps to the local trading date
    # rather than to whatever date it happens to be in UTC.
    gmtoffset = int(result.get("meta", {}).get("gmtoffset", 0))

    known_at = to_iso(known_at_for(observed_at, "yahoo", latency_budget))
    observed_iso = to_iso(observed_at)

    bars: list[dict[str, object]] = []
    for index, epoch in enumerate(timestamps):
        values = {field: quote[field][index] for field in _PRICE_FIELDS}
        # Yahoo pads holidays and halts with nulls. A partial bar is not a bar.
        if any(value is None for value in values.values()):
            continue
        session = (
            datetime.fromtimestamp(epoch, UTC) + timedelta(seconds=gmtoffset)
        ).strftime("%Y-%m-%d")
        bars.append({
            "ticker": symbol,
            "session_date": session,
            "event_time": _session_close(session),
            "observed_at": observed_iso,
            "known_at": known_at,
            **{field: float(values[field]) for field in _PRICE_FIELDS},  # type: ignore[arg-type]
            "source": "yahoo",
        })
    return bars


def fetch_bars(
    ticker: str, observed_at: datetime, latency_budget: Mapping[str, int]
) -> list[dict[str, object]]:
    """Raw daily bars, stooq first and Yahoo as fallback (spec §6.1).

    stooq currently sits behind a JavaScript proof-of-work challenge and
    answers it with HTTP 200, so the fallback is the live path today. The
    order is kept because the challenge may lift, and because a working
    second source is what makes a single vendor outage survivable.
    """
    try:
        return fetch_stooq(ticker, observed_at, latency_budget)
    except (VendorResponseError, requests.RequestException):
        return fetch_yahoo(ticker, observed_at, latency_budget)
