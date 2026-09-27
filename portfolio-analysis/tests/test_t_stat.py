"""t-statistic of the regression intercept (issue #49).

``t = alpha / SE(alpha)`` is the credibility measure that tells "strong
signal" from "loud noise": a flip whose alpha the data cannot distinguish
from noise does not count. These tests pin the statistics (against an
independent formula path, not a re-implementation of the same algebra),
the WLS effective-sample-size degrees of freedom, the rolling t series,
and the flip trigger's credibility gate.
"""

from __future__ import annotations

import math
import random
from math import fsum

import pytest

from portfolio_analysis.moves import decay_weights, ols_regression, wls_regression
from portfolio_analysis.signals import (
    FLIP_MIN_ALPHA_LEVEL,
    FLIP_MIN_T,
    detect_alpha_flips,
    rolling_alpha_daily,
)


def _synthetic_trend(n: int = 120, seed: int = 49) -> tuple[list[float], list[float]]:
    """Benchmark returns and asset returns with a real alpha drift."""
    rng = random.Random(seed)
    xs = [rng.gauss(0, 0.01) for _ in range(n)]
    ys = [0.0008 + 1.2 * x + rng.gauss(0, 0.002) for x in xs]
    return xs, ys


def _synthetic_noise(n: int = 120, seed: int = 7) -> tuple[list[float], list[float]]:
    """Benchmark and asset returns with no relationship at all."""
    rng = random.Random(seed)
    xs = [rng.gauss(0, 0.01) for _ in range(n)]
    ys = [rng.gauss(0, 0.01) for _ in range(n)]
    return xs, ys


# ---------------------------------------------------------------------------
# Core statistics
# ---------------------------------------------------------------------------


def test_clean_trend_gives_large_t() -> None:
    xs, ys = _synthetic_trend()
    _, alpha, t = ols_regression(ys, xs, t_stat=True)
    assert alpha > 0
    assert t > 3.0  # a real drift is distinguishable from noise


def test_pure_noise_gives_near_zero_t() -> None:
    xs, ys = _synthetic_noise()
    _, _, t = ols_regression(ys, xs, t_stat=True)
    assert abs(t) < 1.5  # nothing there: the t says so


def test_wls_uniform_weights_match_ols() -> None:
    xs, ys = _synthetic_trend()
    w = [1.0] * len(xs)
    assert wls_regression(ys, xs, w, t_stat=True) == pytest.approx(
        ols_regression(ys, xs, t_stat=True)
    )


def test_both_flags_return_four_tuple() -> None:
    xs, ys = _synthetic_trend()
    out = ols_regression(ys, xs, r_squared=True, t_stat=True)
    assert len(out) == 4
    beta, alpha, r2, t = out
    _, _, r2_only = ols_regression(ys, xs, r_squared=True)
    _, _, t_only = ols_regression(ys, xs, t_stat=True)
    assert (beta, alpha) == ols_regression(ys, xs)
    assert r2 == r2_only
    assert t == t_only


def test_t_stat_is_scale_invariant() -> None:
    """Annualizing the alpha must not change its t: credibility is about
    the shape of the evidence, not the units."""
    xs, ys = _synthetic_trend()
    _, _, t_daily = ols_regression(ys, xs, t_stat=True)
    scaled = [252 * y for y in ys]
    _, _, t_scaled = ols_regression(scaled, xs, t_stat=True)
    assert t_scaled == pytest.approx(t_daily)


def test_wls_t_stat_matches_independent_weighted_formula() -> None:
    """Pin the WLS t against the weighted-mean-centered formula path -
    a different algebra than the (X'WX)^-1 implementation."""
    xs, ys = _synthetic_trend(n=60, seed=11)
    w = decay_weights(60, 10.0)
    beta, alpha, t = wls_regression(ys, xs, w, t_stat=True)

    w_sum = fsum(w)
    xbar = fsum(wi * x for wi, x in zip(w, xs, strict=True)) / w_sum
    ybar = fsum(wi * y for wi, y in zip(w, ys, strict=True)) / w_sum
    sxx = fsum(wi * (x - xbar) ** 2 for wi, x in zip(w, xs, strict=True))
    beta_e = fsum(wi * (x - xbar) * (y - ybar) for wi, x, y in zip(w, xs, ys, strict=True)) / sxx
    alpha_e = ybar - beta_e * xbar
    sse = fsum(wi * (y - alpha_e - beta_e * x) ** 2 for wi, x, y in zip(w, xs, ys, strict=True))
    n_eff = w_sum**2 / fsum(wi**2 for wi in w)
    assert 2 < n_eff < 60  # decay really does concentrate the information
    sigma2 = sse / (n_eff - 2)
    se = math.sqrt(sigma2 * (1 / w_sum + xbar**2 / sxx))

    assert beta == pytest.approx(beta_e)
    assert alpha == pytest.approx(alpha_e)
    assert t == pytest.approx(alpha_e / se)


def test_t_stat_raises_on_perfect_fit() -> None:
    # y = 0.5 + x exactly: zero residual variance, so no standard error.
    # (All arithmetic here is exact in binary floating point.)
    with pytest.raises(ValueError, match="zero residual variance"):
        ols_regression([0.5, 1.5, 2.5, 3.5], [0.0, 1.0, 2.0, 3.0], t_stat=True)


def test_t_stat_raises_without_effective_degrees_of_freedom() -> None:
    # weights [1, 0, 1]: n_eff = (1+0+1)^2/(1+0+1) = 2, so dof = 0.
    # The nominal n = 3 would claim one degree of freedom the data
    # does not have.
    with pytest.raises(ValueError, match="degrees of freedom"):
        wls_regression(
            [0.010, 0.020, 0.015],
            [0.005, -0.003, 0.008],
            [1.0, 0.0, 1.0],
            t_stat=True,
        )


# ---------------------------------------------------------------------------
# Rolling t series
# ---------------------------------------------------------------------------


def test_rolling_alpha_with_t_fixed_mode() -> None:
    xs, ys = _synthetic_trend(n=90, seed=23)
    alphas, ts = rolling_alpha_daily(ys, xs, 30, with_t=True)
    plain = rolling_alpha_daily(ys, xs, 30)
    assert isinstance(alphas, list) and isinstance(ts, list)
    assert len(alphas) == len(ts) == 90
    assert alphas == plain  # the t leg must not perturb the alpha leg
    assert all(a is None for a in alphas[:29])
    assert all(t is None for t in ts[:29])
    assert all(t is not None for t in ts[29:])
    # spot-check the last window against the single-window fit
    _, _, expected = ols_regression(ys[60:90], xs[60:90], t_stat=True)
    assert ts[89] == pytest.approx(expected)


def test_rolling_alpha_with_t_wls_mode() -> None:
    xs, ys = _synthetic_trend(n=90, seed=23)
    alphas, ts = rolling_alpha_daily(ys, xs, None, half_life=20, with_t=True)
    plain = rolling_alpha_daily(ys, xs, None, half_life=20)
    assert alphas == plain
    assert all(a is None for a in alphas[:19])
    assert all(t is None for t in ts[:19])
    _, _, expected = wls_regression(ys, xs, decay_weights(90, 20), t_stat=True)
    assert ts[89] == pytest.approx(expected)


def test_rolling_alpha_default_still_returns_list() -> None:
    xs, ys = _synthetic_trend(n=60, seed=5)
    out = rolling_alpha_daily(ys, xs, 30)
    assert isinstance(out, list)
    assert len(out) == 60


# ---------------------------------------------------------------------------
# Flip trigger credibility gate
# ---------------------------------------------------------------------------


def _gated_flip_series(
    n: int = 40, *, t_value: float, alpha_value: float = 0.10
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    """A clean negative->positive accelerating flip; the caller chooses the
    t-statistic and alpha level so each gate can be tested in isolation."""
    slope: list[float | None] = [None] * n
    alpha: list[float | None] = [None] * n
    for i in range(10):
        slope[i] = -0.01
        alpha[i] = -0.05
    for k in range(n - 10):
        i = 10 + k
        slope[i] = 0.001 * (k + 1) + 0.0002 * k * k  # positive and accelerating
        alpha[i] = alpha_value
    r2 = [0.9 if s is not None else None for s in slope]
    t = [t_value if s is not None else None for s in slope]
    return alpha, slope, r2, t


def test_flip_blocked_below_min_t() -> None:
    alpha, slope, r2, t = _gated_flip_series(t_value=1.0)
    assert detect_alpha_flips(alpha, slope, r2, t) == []


def test_flip_passes_at_min_t_boundary() -> None:
    alpha, slope, r2, t = _gated_flip_series(t_value=FLIP_MIN_T)
    assert len(detect_alpha_flips(alpha, slope, r2, t)) == 1


def test_flip_passes_above_min_t() -> None:
    alpha, slope, r2, t = _gated_flip_series(t_value=2.5)
    assert len(detect_alpha_flips(alpha, slope, r2, t)) == 1


def test_flip_min_t_is_configurable() -> None:
    alpha, slope, r2, t = _gated_flip_series(t_value=2.0)
    assert detect_alpha_flips(alpha, slope, r2, t, min_t=2.5) == []
    assert len(detect_alpha_flips(alpha, slope, r2, t, min_t=1.0)) == 1


def test_flip_t_gate_disabled_when_t_stats_is_none() -> None:
    # Backward compatible: without a t series the trigger behaves as before.
    alpha, slope, r2, _ = _gated_flip_series(t_value=0.01)
    assert len(detect_alpha_flips(alpha, slope, r2)) == 1


def test_flip_undefined_t_blocks() -> None:
    # A None t means the t-stat was undefined (no effective dof) - a gap,
    # not evidence. Conservative: that session cannot fire; the flip waits
    # for a session where the credibility measure exists.
    alpha, slope, r2, t = _gated_flip_series(t_value=2.5)
    gated = detect_alpha_flips(alpha, slope, r2, t)
    assert len(gated) == 1
    fire_at = gated[0].index
    t[fire_at] = None
    delayed = detect_alpha_flips(alpha, slope, r2, t)
    assert len(delayed) == 1
    assert delayed[0].index == fire_at + 1
    # No defined t anywhere in the positive run: no flip at all.
    t_blank: list[float | None] = [None] * len(t)
    assert detect_alpha_flips(alpha, slope, r2, t_blank) == []


def test_flip_min_alpha_guard() -> None:
    # Significant-but-tiny: t clears, alpha level does not.
    alpha, slope, r2, t = _gated_flip_series(t_value=3.0, alpha_value=0.03)
    assert detect_alpha_flips(alpha, slope, r2, t, min_alpha=FLIP_MIN_ALPHA_LEVEL) == []
    # Economically meaningful: both gates clear.
    alpha, slope, r2, t = _gated_flip_series(t_value=3.0, alpha_value=0.10)
    assert len(detect_alpha_flips(alpha, slope, r2, t, min_alpha=FLIP_MIN_ALPHA_LEVEL)) == 1
    # Guard off by default: the tiny flip counts on t alone.
    alpha, slope, r2, t = _gated_flip_series(t_value=3.0, alpha_value=0.03)
    assert len(detect_alpha_flips(alpha, slope, r2, t)) == 1


def test_flip_t_stats_length_mismatch_raises() -> None:
    alpha, slope, r2, t = _gated_flip_series(t_value=2.0)
    with pytest.raises(ValueError, match="t_stats must match"):
        detect_alpha_flips(alpha, slope, r2, t[:-1])
