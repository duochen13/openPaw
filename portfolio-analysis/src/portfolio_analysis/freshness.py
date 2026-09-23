"""Freshness-aware build logic (issue #56).

`render` is offline-by-contract and never fetches. The user-facing triggers
`chart` and `dashboard` check staleness first:

- prices: refresh when the latest stored bar is older than the last
  completed trading session (weekends and US market holidays are not
  sessions, and a session counts as completed only after the 16:00 ET
  close);
- fundamentals: refetch only when the stored fetch is older than the
  existing 24h TTL (see cli._fundamentals_fresh / cli._kpi_fresh).

The trading-day calendar below covers US market holidays for 2025-2027.
Extend the set when it goes stale; the unit tests pin the boundary
behavior (weekends, holidays, pre/post-close).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
MARKET_CLOSE = time(16, 0)

#: NYSE holidays, 2025-2027. July 3 2026 / June 18 2027 / July 5 2027 /
#: December 24 2027 are the observed days for holidays falling on weekends.
US_MARKET_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2025
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
        # 2026
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
        # 2027
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 4, 2),
        date(2027, 5, 31),
        date(2027, 6, 18),
        date(2027, 7, 5),
        date(2027, 9, 6),
        date(2027, 11, 25),
        date(2027, 12, 24),
    }
)


def is_trading_day(d: date) -> bool:
    """A weekday that is not a US market holiday."""
    return d.weekday() < 5 and d not in US_MARKET_HOLIDAYS


def last_completed_session(now: datetime) -> date:
    """The most recent trading session whose 16:00 ET close has passed.

    Before the close on a trading day the session is not complete yet, so
    the previous session is returned. Weekends and holidays roll back to
    the last session with a close.
    """
    local = now.astimezone(NY)
    day = local.date()
    if not (is_trading_day(day) and local.time() >= MARKET_CLOSE):
        day -= timedelta(days=1)
    while not is_trading_day(day):
        day -= timedelta(days=1)
    return day


def price_staleness(latest_bar: date | None, now: datetime) -> tuple[bool, int]:
    """Whether prices need a refresh, and how many sessions behind they are.

    Returns (needs_refresh, sessions_behind): True when there are no bars
    at all or the latest bar predates the last completed session.
    sessions_behind is 0 when fresh (or unknown, when there are no bars).
    """
    if latest_bar is None:
        return True, 0
    last = last_completed_session(now)
    if latest_bar >= last:
        return False, 0
    behind = 0
    day = latest_bar
    while day < last:
        day += timedelta(days=1)
        if is_trading_day(day):
            behind += 1
    return True, behind
