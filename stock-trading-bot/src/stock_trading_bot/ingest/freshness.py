"""Stale-bar guard (spec §5.6).

A vendor that silently serves a weeks-old last bar produces a backtest that
looks fine and is wrong. Refuse the data instead.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence


class StaleDataError(RuntimeError):
    """Raised when price data does not reach the expected trading session."""


def assert_fresh(bars: Sequence[Mapping[str, object]], expected_session: str) -> None:
    """Verify the newest bar is exactly the expected session.

    `expected_session` is a YYYY-MM-DD trading date, derived from the session
    calendar rather than the wall clock, so weekends and holidays are handled
    by the caller.
    """
    if not bars:
        raise StaleDataError(f"no bars returned; expected {expected_session}")

    sessions: list[str] = []
    for bar in bars:
        session = bar.get("session_date")
        # A non-text session cannot be compared against the calendar. Comparing
        # it anyway would either raise deep inside max() or, worse, compare
        # wrongly - and the whole point of this guard is that bad price data
        # fails loudly instead of quietly producing a plausible backtest.
        if not isinstance(session, str):
            raise StaleDataError(
                f"bar has a non-text session_date: {session!r}; "
                f"expected a YYYY-MM-DD string"
            )
        sessions.append(session)

    newest = max(sessions)
    if newest < expected_session:
        raise StaleDataError(
            f"stale data: newest session {newest}, expected {expected_session}"
        )
    if newest > expected_session:
        raise StaleDataError(
            f"vendor returned a future session {newest}, expected {expected_session}"
        )
