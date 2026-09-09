"""As-of corporate action adjustment (spec §5.4).

The point of this module: an adjusted price series is itself retroactively
revised. A 5-for-1 split in December 2025 rewrites every adjusted close before
it. A backtest standing at June 2025 must not see that adjustment, because it
had not happened yet.

So we store raw prices plus dated actions, and reconstruct the factor from
whatever actions were visible at t. The visibility filtering is not done here -
it is already done by the view, which cannot return an action that was not
knowable at `t`.

Malformed action rows raise rather than being skipped. A silently ignored split
is a missed adjustment, which means wrong prices with nothing to indicate it.
"""
from __future__ import annotations

from math import prod

from stock_trading_bot.store import PointInTimeView


def split_factor_as_of(
    view: PointInTimeView, ticker: str, session_date: str
) -> float:
    """Divisor converting a raw price on `session_date` into `view.t` terms.

    Only splits effective AFTER the session and knowable by `view.t` apply.
    Returns 1.0 when no such split is visible.
    """
    ratios: list[float] = []
    for action in view.corporate_actions(ticker):
        if action["action_type"] != "split":
            continue

        effective_date = action["effective_date"]
        if not isinstance(effective_date, str):
            raise ValueError(
                f"corporate action for {ticker} has a non-text effective_date: "
                f"{effective_date!r}"
            )
        if effective_date <= session_date:
            continue

        ratio = action["ratio"]
        if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or ratio <= 0:
            raise ValueError(
                f"split for {ticker} effective {effective_date} has an unusable "
                f"ratio: {ratio!r}. Skipping it would silently mis-price every "
                "earlier session."
            )
        ratios.append(float(ratio))

    return prod(ratios) if ratios else 1.0


def adjusted_close_as_of(
    view: PointInTimeView, ticker: str, bar: dict[str, object]
) -> float:
    """Split-adjusted close for a bar, in `view.t` terms."""
    close = bar["close"]
    if not isinstance(close, (int, float)) or isinstance(close, bool):
        raise ValueError(f"bar has a non-numeric close: {close!r}")
    session_date = bar["session_date"]
    if not isinstance(session_date, str):
        raise ValueError(f"bar has a non-text session_date: {session_date!r}")
    return float(close) / split_factor_as_of(view, ticker, session_date)
