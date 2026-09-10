"""The one shared withhold rule for present-day-only vendor fields (spec §5.5).

Vendor "company overview" endpoints (yfinance Ticker.info, Alpha Vantage
OVERVIEW) serve only today's values. Market cap, valuation multiples, the
52-week range and TTM income all move with today's quote. Even name, sector and
industry shift when a company renames or is reclassified. None of it carries a
historical vintage, so emitting any of it into a run dated in the past puts
post-decision information into the model's inputs.

This rule lives at the shared layer, and every market-data adapter routes
through it, specifically so that switching providers cannot reintroduce the
leak. Do not reimplement this check inside an adapter.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date

LIVE_ONLY_FIELDS = frozenset({
    "longName", "shortName", "sector", "industry",
    "marketCap", "enterpriseValue",
    "trailingPE", "forwardPE", "priceToBook", "pegRatio",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
    "totalRevenue", "trailingEps", "forwardEps",
    "dividendYield", "beta",
})


def withhold_live_profile(
    fields: Mapping[str, object], curr_date: date, today: date
) -> dict[str, object]:
    """Strip present-day-only fields from a run dated before today.

    A live run (curr_date == today) is unchanged. A historical run receives
    nothing from a profile payload, because a profile payload has no vintage
    to filter on - the whole object is as-of-now.
    """
    if curr_date >= today:
        return dict(fields)
    return {k: v for k, v in fields.items() if k not in LIVE_ONLY_FIELDS}
