"""Alpha slope signals (issues #19, #39). Pure statistics - no I/O.

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

Every function is causal: the value at index ``i`` uses only entries at
indices <= ``i``. Entries that cannot be computed (warmup, degenerate OLS
windows) are ``None``, never fabricated. The template skips nulls when
drawing; the backtest skips nulls when scoring.

Signal kinds (see issues #19, #39): "turnaround" (alpha < 0, slope > 0).
Issue #39 removed the acceleration series (it duplicated the slope panel),
so the acceleration-confirmed kinds "turnaround-strong" and "early-watch" no
longer exist. These are regime-change signals for later validation against
forward returns - never buy signals.

``smooth_display`` is presentation-only smoothing for the slope sparkline;
it is deliberately not used by ``alpha_signal``.

Impact on issue #32 (alpha-reversal alert): the slope sign-change detection
it needs is unaffected - the slope series is kept. What changed is that the
alert can no longer require acceleration confirmation, and the "early-watch"
(deterioration slowing while still falling) state is gone.
"""

from __future__ import annotations

from collections.abc import Sequence

from portfolio_analysis.moves import annualize_alpha, decay_weights, ols_regression, wls_regression

#: Smoothing span for the slope, in trading sessions (issue #19: 20).
SLOPE_SPAN = 20

#: Display-smoothing span for the alpha-slope sparkline. The raw per-session
#: slope is jagged; the chart draws a short trailing moving average so the
#: trend is readable. Display only: turnaround signals and the TLDR keep
#: using the raw slope from rolling_slope, so signal behavior is unchanged.
SLOPE_DISPLAY_SPAN = 5

#: Rolling OLS windows offered by the chart's window switch.
REGIME_WINDOWS = (60, 125, 250)

#: Half-lives (sessions) offered by the chart's "enable time weight" tab
#: (issue #47). The WLS fit uses a growing window with exponential decay,
#: so the half-life - not a hard window - controls how much history matters.
WLS_HALF_LIVES = (20, 60, 120)

#: Default half-life for the time-weighted tab and the backtest.
DEFAULT_WLS_HALF_LIFE = 60


def rolling_slope(
    values: Sequence[float | None], span: int = SLOPE_SPAN, *, half_life: float | None = None
) -> list[float | None]:
    """Per-session slope of ``values``.

    ``half_life=None`` (default): ``(v[i] - v[i-span]) / span``, the original
    "fixed time weight" behavior. ``None`` until index ``span`` and whenever
    either endpoint is ``None``: the first ``span`` entries are a warmup fact,
    not a zero slope.

    ``half_life`` set ("enable time weight", issue #47): the WLS slope of the
    trailing ``span`` values against time, with :func:`decay_weights`
    weighting recent values more. ``None`` until ``span`` consecutive defined
    values have been seen; a ``None`` anywhere in the trailing span poisons
    the slope instead of being interpolated - the same "never fabricated"
    rule as the fixed mode.
    """
    out: list[float | None] = [None] * len(values)
    if half_life is None:
        for i in range(span, len(values)):
            start, end = values[i - span], values[i]
            if start is not None and end is not None:
                out[i] = (end - start) / span
        return out
    weights = decay_weights(span, half_life)
    times = list(range(span))
    for i in range(span - 1, len(values)):
        window = values[i - span + 1 : i + 1]
        if any(v is None for v in window):
            continue
        ys = [v for v in window if v is not None]
        slope, _ = wls_regression(ys, times, weights)
        out[i] = slope
    return out


def smooth_display(
    values: Sequence[float | None], span: int = SLOPE_DISPLAY_SPAN
) -> list[float | None]:
    """Trailing moving average for display.

    ``None`` until ``span`` consecutive defined points have been seen; a
    ``None`` gap breaks the run instead of being interpolated. Causal: the
    value at index ``i`` uses only entries at indices <= ``i``. Pure
    presentation smoothing - never fed into signal classification.
    """
    out: list[float | None] = [None] * len(values)
    run: list[float] = []
    for i, value in enumerate(values):
        if value is None:
            run = []
            continue
        run.append(value)
        if len(run) > span:
            run.pop(0)
        if len(run) == span:
            out[i] = sum(run) / span
    return out


def rolling_alpha_daily(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    window: int | None,
    *,
    half_life: float | None = None,
) -> list[float | None]:
    """Trailing alpha (annualized) for every return index.

    Exactly one of ``window`` / ``half_life`` must be set:

    - ``window=N, half_life=None`` ("fixed time weight"): ``alpha[i]`` is the
      OLS intercept over returns ``[i-window+1, i]`` - the "as of" date is
      the date return ``i`` was realized on, matching ``_regime_points``.
      Entries before ``window - 1`` and degenerate windows (zero variance)
      are ``None``.
    - ``window=None, half_life=H`` ("enable time weight", issue #47):
      ``alpha[i]`` is the WLS intercept over the *growing* history
      ``[0, i]`` with :func:`decay_weights` decay ``H`` - recent sessions
      dominate, old ones fade without a hard window edge. Entries before
      ``H - 1`` (fewer than one half-life of data) and degenerate fits are
      ``None``.

    Both modes are causal: the value at index ``i`` uses only entries at
    indices <= ``i``. Passing both or neither raises ``ValueError``.
    """
    if (window is None) == (half_life is None):
        raise ValueError("exactly one of window and half_life must be set")
    if len(asset_returns) != len(benchmark_returns):
        raise ValueError(
            f"series must be the same length, got {len(asset_returns)} and {len(benchmark_returns)}"
        )
    out: list[float | None] = [None] * len(asset_returns)
    if half_life is None:
        assert window is not None
        for i in range(window - 1, len(asset_returns)):
            segment = slice(i - window + 1, i + 1)
            try:
                _, alpha = ols_regression(asset_returns[segment], benchmark_returns[segment])
            except ValueError:
                continue
            out[i] = annualize_alpha(alpha)
        return out
    warmup = max(2, int(half_life))
    for i in range(warmup - 1, len(asset_returns)):
        segment = slice(0, i + 1)
        try:
            _, alpha = wls_regression(
                asset_returns[segment],
                benchmark_returns[segment],
                decay_weights(i + 1, half_life),
            )
        except ValueError:
            continue
        out[i] = annualize_alpha(alpha)
    return out


#: The only signal kind emitted by :func:`alpha_signal` (issue #39).
TURNAROUND = "turnaround"


def alpha_signal(alpha: float | None, slope: float | None) -> str | None:
    """Classify one point of the alpha/slope pair.

    Returns ``"turnaround"`` when alpha < 0 and slope > 0 - alpha is negative
    but improving; else ``None``. Any ``None`` input yields ``None``: a
    signal needs both legs. (Issue #39 removed acceleration, so the former
    "turnaround-strong" and "early-watch" kinds are gone; "turnaround" now
    covers every alpha < 0, slope > 0 point.)
    """
    if alpha is None or slope is None:
        return None
    if alpha < 0 and slope > 0:
        return TURNAROUND
    return None
