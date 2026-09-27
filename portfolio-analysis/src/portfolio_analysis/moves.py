"""Move detection (spec §5). Pure statistics - no I/O, no network, no database.

    r_t      = adj_close_t / adj_close_{t-1} - 1
    beta     = OLS slope of r on r_benchmark over [t-250, t-1]
    alpha    = OLS intercept over the same window (the daily drift the market
               does not explain)
    AR_t     = r_t - beta * r_benchmark_t
    sigma_60 = stdev(AR) over [t-60, t-1]
    z_t      = AR_t / sigma_60

A day is flagged when |z_t| >= 2.5.

Both estimation windows end at t-1. This is a statistical requirement, not a
point-in-time one: including day t in the volatility estimate that day t must
clear makes the threshold move with the thing it is measuring.

The historical abnormal returns used for sigma are computed with the SAME beta
estimated at t, rather than each with its own contemporaneous beta. This is the
constant-beta convention of a standard event study, and it avoids a recursive
estimation whose result would depend on where the series happened to start.

Alpha is the raw OLS intercept - a trailing statistical residual, not a
forecast. Jensen's alpha (net of the risk-free rate) is a deliberate
follow-up: it needs a risk-free series this project does not carry.
"""

from __future__ import annotations

import math
import statistics as st
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, overload

from portfolio_analysis.config import MoveParams
from portfolio_analysis.naming import safe_ticker_component

#: Halts and one-off listing gaps are tolerated; a systematic calendar
#: disagreement is not, because every return spanning a gap is fabricated.
_MAX_DROPPED_DATES = 5


def aligned_returns(
    asset: Mapping[str, float], benchmark: Mapping[str, float]
) -> tuple[list[str], list[float], list[float]]:
    """Simple returns over consecutive dates present in both series.

    Returns (dates, asset_returns, benchmark_returns), all the same length and
    one shorter than the common date set. `dates[i]` is the date the return
    was realized on.
    """
    common = sorted(set(asset) & set(benchmark))
    if len(common) < 2:
        raise ValueError(f"need at least two common dates, got {len(common)}")

    # Count disagreement only INSIDE the overlapping span. Counting the whole
    # symmetric difference makes a short series an error: the benchmark is
    # always fetched at full depth, so a newly listed ticker would score every
    # non-overlapping benchmark date as a "dropped" date and raise - which
    # contradicts compute_moves' contract that a short history is a coverage
    # fact, not a failure. What this guard is actually for is two series that
    # disagree about the calendar where they overlap.
    lo, hi = common[0], common[-1]
    inside = sum(1 for d in asset if lo <= d <= hi)
    inside += sum(1 for d in benchmark if lo <= d <= hi)
    dropped = inside - 2 * len(common)
    if dropped > _MAX_DROPPED_DATES:
        raise ValueError(
            f"{dropped} dates are missing from one series or the other; the two "
            "series disagree about the trading calendar, so every return "
            "spanning a gap would be fabricated"
        )

    dates: list[str] = []
    asset_returns: list[float] = []
    benchmark_returns: list[float] = []
    # pairwise, not zip(common, common[1:]): the two arms are deliberately
    # different lengths, so strict=True rejects it and a bare zip trips B905.
    for series, name in ((asset, "asset"), (benchmark, "benchmark")):
        # Every common date, not just the `previous` of each pair: pairwise
        # never visits the last date, which is the one most likely to carry a
        # bad live partial print.
        for day in common:
            if series[day] <= 0:
                raise ValueError(f"non-positive {name} price {series[day]!r} on {day}")

    for previous, current in pairwise(common):
        dates.append(current)
        asset_returns.append(asset[current] / asset[previous] - 1)
        benchmark_returns.append(benchmark[current] / benchmark[previous] - 1)
    return dates, asset_returns, benchmark_returns


#: Trading sessions per year, for annualizing the daily alpha at presentation
#: time. The stored alpha stays daily; only the display multiplies.
_TRADING_DAYS_PER_YEAR = 252


def _alpha_t_stat(
    asset: Sequence[float],
    benchmark: Sequence[float],
    weights: Sequence[float] | None,
    beta: float,
    alpha: float,
) -> float:
    """t-statistic of the regression intercept: ``t = alpha / SE(alpha)``
    (issue #49).

    The standard error is WLS-aware: ``Var(beta_hat) = sigma^2 (X'WX)^-1``,
    taking the intercept (``[0, 0]``) element. For the single-factor model
    with design ``X = [1, x]``,

        (X'WX)^-1[0,0] = sum(wx^2) / (sum(w)*sum(wx^2) - sum(wx)^2).

    ``weights=None`` is uniform weight, i.e. OLS - the formula is identical
    and the effective sample size below reduces to ``n``.

    ``sigma^2`` is the weighted residual sum of squares over degrees of
    freedom. The dof uses the *effective* sample size ``n_eff = (sum w)^2 /
    sum(w^2)`` (Kish) rather than the nominal ``n``: under decay weighting
    the nominal count overstates the information - e.g. half-life 20 over a
    long history carries only ~58 effective observations, and a t built on
    dof ~= 1500 would look far more confident than the data warrants. Two
    parameters (alpha, beta) are estimated, hence ``dof = n_eff - 2``.

    Raises ``ValueError`` when the t-stat is undefined: ``dof <= 0`` (fewer
    than two effective observations), a benchmark with no (weighted)
    variance at floating-point precision, or zero residual variance
    (perfect fit).
    """
    n = len(asset)
    w = [1.0] * n if weights is None else list(weights)
    w_sum = math.fsum(w)
    swx = math.fsum(wi * x for wi, x in zip(w, benchmark, strict=True))
    swx2 = math.fsum(wi * x * x for wi, x in zip(w, benchmark, strict=True))
    # = w_sum^2 * Var_w(x); mathematically non-negative. The caller already
    # rejected zero (weighted) benchmark variance, but through a different
    # formula - catastrophic cancellation can still round this to exactly
    # zero (e.g. a near-flat benchmark), and dividing by it would fabricate
    # a t-stat out of float noise.
    det = w_sum * swx2 - swx * swx
    if det <= 0:
        raise ValueError(
            "t-stat undefined: benchmark has no (weighted) variance at floating-point precision"
        )
    resid_ss = math.fsum(
        wi * (y - (alpha + beta * x)) ** 2 for wi, y, x in zip(w, asset, benchmark, strict=True)
    )
    n_eff = w_sum * w_sum / math.fsum(wi * wi for wi in w)
    dof = n_eff - 2
    if dof <= 0:
        raise ValueError(
            f"t-stat undefined: effective sample size {n_eff:.2f} gives "
            f"{dof:.2f} degrees of freedom (need > 0)"
        )
    if resid_ss == 0:
        raise ValueError("t-stat undefined: zero residual variance (perfect fit)")
    sigma2 = resid_ss / dof
    var_alpha = sigma2 * swx2 / det
    return alpha / math.sqrt(var_alpha)


@overload
def ols_regression(asset: Sequence[float], benchmark: Sequence[float]) -> tuple[float, float]: ...


@overload
def ols_regression(
    asset: Sequence[float], benchmark: Sequence[float], *, r_squared: Literal[True]
) -> tuple[float, float, float]: ...


@overload
def ols_regression(
    asset: Sequence[float], benchmark: Sequence[float], *, t_stat: Literal[True]
) -> tuple[float, float, float]: ...


@overload
def ols_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    *,
    r_squared: Literal[True],
    t_stat: Literal[True],
) -> tuple[float, float, float, float]: ...


def ols_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    *,
    r_squared: bool = False,
    t_stat: bool = False,
) -> tuple[float, float] | tuple[float, float, float] | tuple[float, float, float, float]:
    """Slope (beta) and intercept (alpha) of the OLS regression of asset
    returns on benchmark returns.

    Returns ``(beta, alpha)``. The intercept is the expected asset return on a
    day the benchmark does not move - the drift the market does not explain.
    It is a daily rate; annualize with ``_TRADING_DAYS_PER_YEAR`` only when
    presenting it, never when storing it.

    Jensen's alpha (net of the risk-free rate) is a deliberate follow-up: it
    needs a risk-free series this project does not carry.

    Pass ``r_squared=True`` to also return the coefficient of determination
    ``(beta, alpha, r_squared)``, where R² = 1 - SSE/SST over the same window:
    the share of the asset's return variance the benchmark explains. R² is
    *not* beta² - beta measures sensitivity, R² measures fit. For single-factor
    OLS with an intercept, R² equals the squared Pearson correlation. A
    zero-variance asset series has no defined R² (inventing one would launder
    a flat line into a relationship), so it raises the same ValueError as the
    other degenerate inputs. R² is clamped to [0, 1] against floating-point
    drift; the OLS-with-intercept identity SSE ≤ SST holds mathematically.

    Pass ``t_stat=True`` to also return the intercept's t-statistic
    ``t = alpha / SE(alpha)`` (issue #49), the credibility measure that tells
    "strong signal" from "loud noise": |t| > 2 is roughly statistically
    significant. SE(alpha) is WLS-aware (uniform weights here), with degrees
    of freedom from the effective sample size - see :func:`_alpha_t_stat`.
    Combine both flags for ``(beta, alpha, r_squared, t_stat)``. The t-stat
    is scale-invariant, so it is identical for the daily and the annualized
    alpha. A t-stat with no degrees of freedom left, or on a perfect fit,
    raises ValueError instead of inventing a number.
    """
    if len(asset) != len(benchmark):
        raise ValueError(f"series must be the same length, got {len(asset)} and {len(benchmark)}")
    if len(asset) < 2:
        raise ValueError(f"need at least two observations, got {len(asset)}")

    mean_asset = st.fmean(asset)
    mean_benchmark = st.fmean(benchmark)
    covariance = st.fmean(
        (a - mean_asset) * (b - mean_benchmark) for a, b in zip(asset, benchmark, strict=True)
    )
    variance = st.fmean((b - mean_benchmark) ** 2 for b in benchmark)
    if variance == 0:
        raise ValueError("benchmark has zero variance over the window; beta is undefined")
    beta = covariance / variance
    alpha = mean_asset - beta * mean_benchmark

    r2: float | None = None
    if r_squared:
        sse = math.fsum(
            (a - (alpha + beta * b)) ** 2 for a, b in zip(asset, benchmark, strict=True)
        )
        sst = math.fsum((a - mean_asset) ** 2 for a in asset)
        if sst == 0:
            raise ValueError("asset has zero variance over the window; R² is undefined")
        r2 = min(1.0, max(0.0, 1.0 - sse / sst))
    t: float | None = None
    if t_stat:
        t = _alpha_t_stat(asset, benchmark, None, beta, alpha)

    if r_squared and t_stat:
        assert r2 is not None and t is not None
        return beta, alpha, r2, t
    if r_squared:
        assert r2 is not None
        return beta, alpha, r2
    if t_stat:
        assert t is not None
        return beta, alpha, t
    return beta, alpha


def ols_beta(asset: Sequence[float], benchmark: Sequence[float]) -> float:
    """Slope of the OLS regression of asset returns on benchmark returns.

    cov / var, which is the slope of the least-squares line. The intercept is
    alpha; see ols_regression. This wrapper keeps the beta-only call sites
    (and their tests) intact.
    """
    beta, _ = ols_regression(asset, benchmark)
    return beta


def decay_weights(length: int, half_life: float) -> list[float]:
    """Exponential decay weights, normalized to sum to 1 (issue #47).

    ``weights[t] = 0.5 ** ((length - 1 - t) / half_life)``: the most recent
    observation (``t = length - 1``) has weight 1 before normalization, and an
    observation ``half_life`` sessions older has exactly half that weight.
    Recent data dominates; old data fades but is never hard-cut, so there is
    no window edge to fall off.

    Raises on non-positive ``half_life`` or ``length < 1``.
    """
    if length < 1:
        raise ValueError(f"need at least one observation, got {length}")
    if half_life <= 0:
        raise ValueError(f"half_life must be positive, got {half_life}")
    raw = [0.5 ** ((length - 1 - t) / half_life) for t in range(length)]
    total = math.fsum(raw)
    return [w / total for w in raw]


@overload
def wls_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    weights: Sequence[float],
) -> tuple[float, float]: ...


@overload
def wls_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    weights: Sequence[float],
    *,
    r_squared: Literal[True],
) -> tuple[float, float, float]: ...


@overload
def wls_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    weights: Sequence[float],
    *,
    t_stat: Literal[True],
) -> tuple[float, float, float]: ...


@overload
def wls_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    weights: Sequence[float],
    *,
    r_squared: Literal[True],
    t_stat: Literal[True],
) -> tuple[float, float, float, float]: ...


def wls_regression(
    asset: Sequence[float],
    benchmark: Sequence[float],
    weights: Sequence[float],
    *,
    r_squared: bool = False,
    t_stat: bool = False,
) -> tuple[float, float] | tuple[float, float, float] | tuple[float, float, float, float]:
    """Slope (beta) and intercept (alpha) of the *weighted* least-squares
    regression of asset returns on benchmark returns (issue #47).

    Minimizes ``sum(w * residual**2)``. With uniform weights this is exactly
    :func:`ols_regression` (unit-tested); with :func:`decay_weights` the
    recent past dominates the fit.

    Returns ``(beta, alpha)``, or ``(beta, alpha, r_squared)`` with
    ``r_squared=True``, where R² = 1 - SSE_w/SST_w over the weighted sums,
    clamped to [0, 1]. Pass ``t_stat=True`` (issue #49) to also return the
    intercept's t-statistic ``t = alpha / SE(alpha)`` - the credibility
    measure that tells "strong signal" from "loud noise". The standard
    error is WLS-aware, ``Var(beta_hat) = sigma² (X'WX)⁻¹`` on the intercept
    element, with ``sigma²`` from the weighted residual sum of squares and
    degrees of freedom from the *effective* sample size
    ``n_eff = (Σw)²/Σw²`` (nominal ``n`` overstates the information under
    decay weighting); see :func:`_alpha_t_stat`. Combine both flags for
    ``(beta, alpha, r_squared, t_stat)``. The same degenerate-input rules as
    :func:`ols_regression` apply: mismatched lengths, fewer than two
    observations, zero (weighted) benchmark variance, or zero (weighted)
    asset variance for R² all raise ``ValueError`` - a flat line is never
    laundered into a relationship. A t-stat with no effective degrees of
    freedom left, or on a perfect fit, likewise raises.
    """
    if not (len(asset) == len(benchmark) == len(weights)):
        raise ValueError(
            "series and weights must be the same length, got "
            f"{len(asset)}, {len(benchmark)} and {len(weights)}"
        )
    if len(asset) < 2:
        raise ValueError(f"need at least two observations, got {len(asset)}")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")
    w_sum = math.fsum(weights)
    if w_sum <= 0:
        raise ValueError("weights must sum to a positive value")

    def wmean(xs: Sequence[float]) -> float:
        return math.fsum(w * x for w, x in zip(weights, xs, strict=True)) / w_sum

    mean_asset = wmean(asset)
    mean_benchmark = wmean(benchmark)
    covariance = (
        math.fsum(
            w * (a - mean_asset) * (b - mean_benchmark)
            for w, a, b in zip(weights, asset, benchmark, strict=True)
        )
        / w_sum
    )
    variance = (
        math.fsum(w * (b - mean_benchmark) ** 2 for w, b in zip(weights, benchmark, strict=True))
        / w_sum
    )
    if variance == 0:
        raise ValueError("benchmark has zero (weighted) variance; beta is undefined")
    beta = covariance / variance
    alpha = mean_asset - beta * mean_benchmark

    r2: float | None = None
    if r_squared:
        sse = (
            math.fsum(
                w * (a - (alpha + beta * b)) ** 2
                for w, a, b in zip(weights, asset, benchmark, strict=True)
            )
            / w_sum
        )
        sst = (
            math.fsum(w * (a - mean_asset) ** 2 for w, a in zip(weights, asset, strict=True))
            / w_sum
        )
        if sst == 0:
            raise ValueError("asset has zero (weighted) variance; R² is undefined")
        r2 = min(1.0, max(0.0, 1.0 - sse / sst))
    t: float | None = None
    if t_stat:
        t = _alpha_t_stat(asset, benchmark, weights, beta, alpha)

    if r_squared and t_stat:
        assert r2 is not None and t is not None
        return beta, alpha, r2, t
    if r_squared:
        assert r2 is not None
        return beta, alpha, r2
    if t_stat:
        assert t is not None
        return beta, alpha, t
    return beta, alpha


def correlation(asset: Sequence[float], benchmark: Sequence[float]) -> float:
    """Pearson correlation of two same-length return series.

    Raises when either series is degenerate: a zero-variance series has no
    defined correlation, and inventing one would launder a flat line into a
    relationship.
    """
    if len(asset) != len(benchmark):
        raise ValueError(f"series must be the same length, got {len(asset)} and {len(benchmark)}")
    if len(asset) < 2:
        raise ValueError(f"need at least two observations, got {len(asset)}")
    mean_asset = st.fmean(asset)
    mean_benchmark = st.fmean(benchmark)
    covariance = st.fmean(
        (a - mean_asset) * (b - mean_benchmark) for a, b in zip(asset, benchmark, strict=True)
    )
    var_asset = st.fmean((a - mean_asset) ** 2 for a in asset)
    var_benchmark = st.fmean((b - mean_benchmark) ** 2 for b in benchmark)
    if var_asset == 0 or var_benchmark == 0:
        raise ValueError("one series has zero variance over the window; correlation is undefined")
    return covariance / math.sqrt(var_asset * var_benchmark)


def annualize_alpha(alpha_daily: float) -> float:
    """Present the daily OLS intercept as an annualized rate.

    The stored alpha stays daily; only the display multiplies. Kept here so
    the 252 lives next to the regression that produced the intercept.
    """
    return alpha_daily * _TRADING_DAYS_PER_YEAR


@dataclass(frozen=True)
class Move:
    """One flagged day, fully decomposed (spec §7 `move` block).

    ``alpha`` is the OLS intercept from the same trailing window that produced
    ``beta`` - the daily drift the benchmark does not explain. Stored daily;
    annualize (x252) only at presentation time.
    """

    ticker: str
    date: str
    ret: float
    benchmark: str
    benchmark_return: float
    beta: float
    alpha: float
    abnormal_return: float
    sigma_60: float
    z: float

    def as_row(self) -> dict[str, object]:
        """The shape Store.upsert_moves expects."""
        return {
            "ticker": self.ticker,
            "date": self.date,
            "ret": self.ret,
            "benchmark": self.benchmark,
            "benchmark_return": self.benchmark_return,
            "beta": self.beta,
            "alpha": self.alpha,
            "abnormal_return": self.abnormal_return,
            "sigma_60": self.sigma_60,
            "z": self.z,
        }


@dataclass(frozen=True)
class Coverage:
    """What was and was not evaluated (spec §5, §7)."""

    price_series: tuple[str, str] | None
    evaluated: tuple[str, str] | None
    evaluated_days: int
    flagged_days: int


def compute_moves(
    ticker: str,
    benchmark_name: str,
    asset: Mapping[str, float],
    benchmark: Mapping[str, float],
    params: MoveParams,
) -> tuple[list[Move], Coverage]:
    """Flagged days and the coverage of the evaluation.

    A series too short to fill the beta window yields no moves and a coverage
    report saying so. A newly listed ticker is a coverage fact, not an error.
    """
    symbol = safe_ticker_component(ticker)
    common = sorted(set(asset) & set(benchmark))
    price_series = (common[0], common[-1]) if common else None

    if len(common) < 2:
        return [], Coverage(price_series, None, 0, 0)

    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)

    first = params.beta_window
    if first >= len(dates):
        return [], Coverage(price_series, None, 0, 0)

    moves: list[Move] = []
    for index in range(first, len(dates)):
        window = slice(index - params.beta_window, index)
        beta, alpha = ols_regression(asset_returns[window], benchmark_returns[window])

        # Constant beta across the sigma window, per the module docstring.
        abnormal = [
            asset_returns[j] - beta * benchmark_returns[j]
            for j in range(index - params.sigma_window, index + 1)
        ]
        sigma = st.stdev(abnormal[:-1])
        if sigma == 0:
            raise ValueError(
                f"{symbol}: zero abnormal-return volatility ending {dates[index - 1]}; "
                "z is undefined"
            )
        z = abnormal[-1] / sigma
        if abs(z) >= params.z_threshold:
            moves.append(
                Move(
                    ticker=symbol,
                    date=dates[index],
                    ret=asset_returns[index],
                    benchmark=benchmark_name,
                    benchmark_return=benchmark_returns[index],
                    beta=beta,
                    alpha=alpha,
                    abnormal_return=abnormal[-1],
                    sigma_60=sigma,
                    z=z,
                )
            )

    return moves, Coverage(
        price_series=price_series,
        evaluated=(dates[first], dates[-1]),
        evaluated_days=len(dates) - first,
        flagged_days=len(moves),
    )
