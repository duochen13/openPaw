"""Trading-day arithmetic (spec §6).

The event window is [-2, +1] TRADING days. Calendar arithmetic is wrong here:
two calendar days before a Monday is a Saturday, so a calendar window silently
trades the two sessions that matter for a weekend where nothing happened.

The session list comes from the benchmark's price history, which is present for
every date in the evaluated range by construction.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable
from datetime import date as iso_date


class TradingCalendar:
    def __init__(self, sessions: Iterable[str]) -> None:
        self._sessions = sorted({iso_date.fromisoformat(d).isoformat() for d in sessions})
        if not self._sessions:
            raise ValueError("a trading calendar needs at least one session")
        self._index = {d: i for i, d in enumerate(self._sessions)}

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def first(self) -> str:
        return self._sessions[0]

    @property
    def last(self) -> str:
        return self._sessions[-1]

    def window(self, date: str, *, before: int, after: int) -> tuple[str, str]:
        """Inclusive (start, end) spanning `before` sessions back and `after`
        forward. Clamped at the ends of the calendar."""
        if before < 0 or after < 0:
            raise ValueError("window sizes must be non-negative")
        if date not in self._index:
            raise KeyError(f"{date!r} is not a trading session in this calendar")
        i = self._index[date]
        lo = max(0, i - before)
        hi = min(len(self._sessions) - 1, i + after)
        return self._sessions[lo], self._sessions[hi]

    def sessions_in(self, start: str, end: str) -> list[str]:
        """Every session in the inclusive range. Endpoints need not be sessions."""
        lo = bisect_left(self._sessions, start)
        hi = bisect_left(self._sessions, end)
        if hi < len(self._sessions) and self._sessions[hi] == end:
            hi += 1
        return self._sessions[lo:hi]
