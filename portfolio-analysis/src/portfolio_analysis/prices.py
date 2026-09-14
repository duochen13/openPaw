"""Adjusted daily price ingestion from Yahoo's chart API (spec §4.1).

Reads BOTH indicators.quote (raw OHLCV) and indicators.adjclose. The sibling
project stock-trading-bot deliberately ignores adjclose and reconstructs split
adjustment from dated corporate actions, because a vendor's adjusted series is
retroactively revised and that corrupts a point-in-time backtest. Here the
present-day adjusted series is the correct input for a retrospective chart, so
it is consumed directly and the raw OHLC is kept alongside (spec §11).

Uses period1/period2 epoch bounds rather than `range`: the API has no `6y`
value, and six years of prices are needed to yield five evaluable ones after
the 250-day beta warm-up (spec §5).

Stooq is not a fallback. It sits behind a JavaScript proof-of-work challenge
that it answers with HTTP 200 and an HTML body, established in the sibling repo.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from portfolio_analysis.naming import safe_ticker_component

_YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?period1={p1}&period2={p2}&interval=1d"
)
_UA = "portfolio-analysis/0.1 (research)"

#: The raw OHLCV fields read from indicators.quote.
_QUOTE_FIELDS = ("open", "high", "low", "close", "volume")

#: 365.25 days per year, so a six-year window spans the leap days it contains.
_DAYS_PER_YEAR = 365.25


class VendorResponseError(RuntimeError):
    """The vendor answered, but not with the data we asked for."""


def _http_get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=60)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def epoch_window(years: int, now: datetime) -> tuple[int, int]:
    """Inclusive epoch-second bounds for a trailing `years` window."""
    start = now - timedelta(days=years * _DAYS_PER_YEAR)
    return int(start.timestamp()), int(now.timestamp())


def fetch_yahoo(
    ticker: str, *, years: int, now: datetime | None = None
) -> list[dict[str, object]]:
    """Daily bars with raw OHLCV and the adjusted close, oldest first."""
    symbol = safe_ticker_component(ticker)
    p1, p2 = epoch_window(years, now or datetime.now(UTC))
    payload = _http_get_json(_YAHOO_URL.format(symbol=symbol, p1=p1, p2=p2))

    results = payload.get("chart", {}).get("result")
    if not results:
        error = payload.get("chart", {}).get("error")
        raise VendorResponseError(f"yahoo returned no result for {symbol}: {error!r}")

    result = results[0]
    timestamps: Sequence[int] = result.get("timestamp") or []
    indicators = result.get("indicators", {})

    quote_block = indicators.get("quote")
    if not quote_block:
        raise VendorResponseError(f"yahoo returned no quote block for {symbol}")
    quote: dict[str, Sequence[float | None]] = quote_block[0]

    adjclose_block = indicators.get("adjclose")
    if not adjclose_block:
        raise VendorResponseError(
            f"yahoo returned no adjclose for {symbol}; this project consumes the "
            "adjusted series directly and cannot substitute the raw close"
        )
    adjusted: Sequence[float | None] = adjclose_block[0]["adjclose"]

    # A truncated vendor array must not escape as a bare IndexError from the
    # indexing below - that is indistinguishable from a bug in this module and
    # defeats the VendorResponseError boundary the rest of the function keeps.
    for name, column in (("adjclose", adjusted), *((f, quote[f]) for f in _QUOTE_FIELDS)):
        if len(column) != len(timestamps):
            raise VendorResponseError(
                f"yahoo returned {len(column)} {name} values for {len(timestamps)} "
                f"timestamps on {symbol}; the response is truncated"
            )

    # The exchange's UTC offset, so a timestamp maps to the local trading date
    # rather than to whatever date it happens to be in UTC.
    # `or 0` as well as a default: Yahoo emits explicit nulls in this payload,
    # and .get(k, 0) only defends against an absent key, not a present null.
    meta = result.get("meta") or {}
    gmtoffset = int(meta.get("gmtoffset") or 0)

    # The last bar is live and partial during market hours: every field is
    # non-None, so the null filter below keeps it, and a 30-minute return gets
    # written as a full day. detect-moves would then evaluate it and can
    # publish a spurious Move. A retrospective tool never needs today's bar -
    # and today's is the only one that can be partial - so it is dropped.
    today_eastern = (
        datetime.now(UTC) + timedelta(seconds=gmtoffset)
    ).strftime("%Y-%m-%d")

    bars: list[dict[str, object]] = []
    for index, epoch in enumerate(timestamps):
        values = {field: quote[field][index] for field in _QUOTE_FIELDS}
        values["adj_close"] = adjusted[index]
        # Yahoo pads holidays and halts with nulls. A partial bar is not a bar,
        # and a zero-filled one would produce a fabricated -100% return.
        if any(value is None for value in values.values()):
            continue
        date = (
            datetime.fromtimestamp(epoch, UTC) + timedelta(seconds=gmtoffset)
        ).strftime("%Y-%m-%d")
        if date >= today_eastern:
            continue
        bars.append({
            "ticker": symbol,
            "date": date,
            **{k: float(v) for k, v in values.items()},  # type: ignore[arg-type]
            "source": "yahoo",
        })
    return bars
