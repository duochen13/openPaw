"""Alpha slope and acceleration signals (issue #19). Pure statistics - no I/O.

The absolute level of rolling alpha can be a lagging signal: a stock may sit
at alpha = -30%, improve to -20%, then -10%, and only cross zero after much of
the recovery has happened. These helpers detect when alpha *starts improving*
while it is still negative.

Conventions (stated once, so the units are never ambiguous):

- ``alpha`` is the trailing OLS intercept, *annualized* (x252), exactly as the
  regime series stores it: a change of 0.01 is one percentage point of
  annualized alpha.
- ``slope`` = (alpha(t) - alpha(t-SPAN)) / SPAN: the change in *annualized*
  alpha per trading session. A slope of +0.005 means the annualized alpha is
  improving by half a point per session. Displayed as %/session.
- ``acceleration`` = slope(t) - slope(t-SPAN): the change in the slope over
  SPAN sessions. Algebraically (a(t) - 2*a(t-SPAN) + a(t-2*SPAN)) / SPAN.
  Displayed as % (of slope change per SPAN sessions).

Every function is causal: the value at index ``i`` uses only entries at
indices <= ``i``. Entries that cannot be computed (warmup, degenerate OLS
windows) are ``None``, never fabricated. The template skips nulls when
drawing; the backtest skips nulls when scoring.

Signal kinds (see issue #19): "turnaround" (alpha < 0, slope > 0),
"turnaround-strong" (additionally acceleration > 0), "early-watch"
(alpha < 0, slope < 0, acceleration > 0). These are regime-change signals for
later validation against forward returns - never buy signals.
"""

from __future__ import annotations

from collections.abc import Sequence

from portfolio_analysis.moves import annualize_alpha, ols_regression

#: Smoothing span for the slope, in trading sessions (issue #19: 20).
SLOPE_SPAN = 20

#: Rolling OLS windows offered by the chart's window switch.
REGIME_WINDOWS = (60, 125, 250)


def rolling_slope(
    values: Sequence[float | None], span: int = SLOPE_SPAN
) -> list[float | None]:
    """Per-session slope ``(v[i] - v[i-span]) / span``.

    ``None`` until index ``span`` and whenever either endpoint is ``None``:
    the first ``span`` entries are a warmup fact, not a zero slope.
    """
    out: list[float | None] = [None] * len(values)
    for i in range(span, len(values)):
        start, end = values[i - span], values[i]
        if start is not None and end is not None:
            out[i] = (end - start) / span
    return out


def alpha_acceleration(
    slopes: Sequence[float | None], span: int = SLOPE_SPAN
) -> list[float | None]:
    """Change in the slope over ``span`` sessions: ``slope[i] - slope[i-span]``.

    Positive means the alpha trend itself is improving, even if alpha is still
    falling. This is a pure difference, not a per-session rate: algebraically
    ``(a[i] - 2*a[i-span] + a[i-2*span]) / span``. ``None`` propagates: no
    slope, no acceleration.
    """
    out: list[float | None] = [None] * len(slopes)
    for i in range(span, len(slopes)):
        start, end = slopes[i - span], slopes[i]
        if start is not None and end is not None:
            out[i] = end - start
    return out


def rolling_alpha_daily(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    window: int,
) -> list[float | None]:
    """Trailing OLS alpha (annualized) for every return index.

    ``alpha[i]`` is the intercept of the regression over returns
    ``[i-window+1, i]`` - the "as of" date is the date return ``i`` was
    realized on, matching ``_regime_points``. Entries before ``window - 1``
    and degenerate windows (zero variance) are ``None``.
    """
    if len(asset_returns) != len(benchmark_returns):
        raise ValueError(
            f"series must be the same length, got {len(asset_returns)} and {len(benchmark_returns)}"
        )
    out: list[float | None] = [None] * len(asset_returns)
    for i in range(window - 1, len(asset_returns)):
        segment = slice(i - window + 1, i + 1)
        try:
            _, alpha = ols_regression(asset_returns[segment], benchmark_returns[segment])
        except ValueError:
            continue
        out[i] = annualize_alpha(alpha)
    return out


#: Signal kinds emitted by :func:`alpha_signal`.
TURNAROUND = "turnaround"
TURNAROUND_STRONG = "turnaround-strong"
EARLY_WATCH = "early-watch"


def alpha_signal(
    alpha: float | None, slope: float | None, accel: float | None
) -> str | None:
    """Classify one point of the alpha/slope/acceleration triple.

    Returns ``"turnaround-strong"`` when alpha < 0, slope > 0 and
    acceleration > 0; ``"turnaround"`` when alpha < 0 and slope > 0;
    ``"early-watch"`` when alpha < 0, slope < 0 but acceleration > 0
    (deterioration slowing); else ``None``. Any ``None`` input yields
    ``None`` - a signal needs all three legs.
    """
    if alpha is None or slope is None:
        return None
    if alpha < 0 and slope > 0:
        if accel is not None and accel > 0:
            return TURNAROUND_STRONG
        return TURNAROUND
    if alpha < 0 and slope < 0 and accel is not None and accel > 0:
        return EARLY_WATCH
    return None
