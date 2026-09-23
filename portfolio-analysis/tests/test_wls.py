"""Exponentially-weighted (WLS) regression and rolling series (issue #47).

Covers decay_weights, wls_regression, and the half_life paths of
rolling_alpha_daily / rolling_slope. The causality tests are the load-bearing
ones: perturbing observations *after* index i must not change any output at
index <= i.
"""

import math
from itertools import pairwise

import pytest

from portfolio_analysis.moves import decay_weights, ols_regression, wls_regression
from portfolio_analysis.signals import (
    DEFAULT_WLS_HALF_LIFE,
    WLS_HALF_LIVES,
    rolling_alpha_daily,
    rolling_slope,
)


@pytest.mark.unit
def test_wls_half_life_contract():
    """The template's half-life switch and the backtest rely on these values."""
    assert WLS_HALF_LIVES == (20, 60, 120)
    assert DEFAULT_WLS_HALF_LIFE == 60


@pytest.mark.unit
def test_decay_weights_normalized_and_monotonic():
    w = decay_weights(100, 20)
    assert len(w) == 100
    assert math.fsum(w) == pytest.approx(1.0)
    assert all(a < b for a, b in pairwise(w))  # recent weighs more
    assert all(x > 0 for x in w)


@pytest.mark.unit
def test_decay_weights_half_life_property():
    """An observation half_life sessions back weighs exactly half the latest."""
    half_life = 30
    w = decay_weights(200, half_life)
    assert w[-1 - half_life] == pytest.approx(0.5 * w[-1])


@pytest.mark.unit
def test_decay_weights_invalid():
    with pytest.raises(ValueError, match="half_life must be positive"):
        decay_weights(10, 0)
    with pytest.raises(ValueError, match="half_life must be positive"):
        decay_weights(10, -5)
    with pytest.raises(ValueError, match="at least one observation"):
        decay_weights(0, 20)


@pytest.mark.unit
def test_wls_uniform_weights_match_ols():
    """Uniform weights must reproduce ols_regression exactly (issue #47)."""
    asset = [0.001 * ((i * 13) % 7 - 3) for i in range(120)]
    bench = [0.0008 * ((i * 29) % 9 - 4) for i in range(120)]
    n = len(asset)
    uniform = [1.0 / n] * n
    assert wls_regression(asset, bench, uniform) == pytest.approx(
        ols_regression(asset, bench)
    )
    assert wls_regression(asset, bench, uniform, r_squared=True) == pytest.approx(
        ols_regression(asset, bench, r_squared=True)
    )


@pytest.mark.unit
def test_wls_large_half_life_approx_ols():
    """A very long half-life is nearly uniform, so nearly OLS."""
    asset = [0.001 * ((i * 13) % 7 - 3) for i in range(120)]
    bench = [0.0008 * ((i * 29) % 9 - 4) for i in range(120)]
    w = decay_weights(len(asset), 1_000_000)
    beta_w, alpha_w = wls_regression(asset, bench, w)
    beta_o, alpha_o = ols_regression(asset, bench)
    assert beta_w == pytest.approx(beta_o, rel=1e-3)
    assert alpha_w == pytest.approx(alpha_o, rel=1e-3)


@pytest.mark.unit
def test_wls_known_drift():
    """asset = 0.002 + bench: intercept is 0.002 whatever the weights."""
    bench = [0.0005 * ((i * 37) % 11 - 5) for i in range(150)]
    asset = [0.002 + b for b in bench]
    for half_life in (5, 20, 60):
        _, alpha = wls_regression(asset, bench, decay_weights(len(asset), half_life))
        assert alpha == pytest.approx(0.002, abs=1e-12)


@pytest.mark.unit
def test_wls_r_squared_bounded():
    bench = [0.001 * ((i * 37) % 11 - 5) for i in range(150)]
    asset = [0.5 * b + 0.0003 * ((i * 53) % 13 - 6) for i, b in enumerate(bench)]
    _, _, r2 = wls_regression(asset, bench, decay_weights(150, 30), r_squared=True)
    assert 0.0 <= r2 <= 1.0


@pytest.mark.unit
def test_wls_degenerate_inputs_raise():
    flat = [0.0] * 60
    wiggle = [0.001 * (i % 7) for i in range(60)]
    w = decay_weights(60, 20)
    with pytest.raises(ValueError, match=r"zero.*variance"):
        wls_regression(wiggle, flat, w)  # flat benchmark
    with pytest.raises(ValueError, match=r"zero.*variance"):
        wls_regression(flat, wiggle, w, r_squared=True)  # flat asset, R²
    with pytest.raises(ValueError, match="same length"):
        wls_regression(wiggle, wiggle, w[:10])
    with pytest.raises(ValueError, match="non-negative"):
        wls_regression(wiggle, wiggle, [-0.1] * 59 + [1.0])


@pytest.mark.unit
def test_rolling_alpha_wls_warmup_and_drift():
    """WLS alpha needs one half-life of data; constant drift is recovered."""
    half_life = 20
    bench = [0.0005 * ((i * 37) % 11 - 5) for i in range(300)]
    asset = [0.001 + b for b in bench]
    alpha = rolling_alpha_daily(asset, bench, None, half_life=half_life)
    assert alpha[: half_life - 1] == [None] * (half_life - 1)
    defined = [a for a in alpha[half_life - 1 :] if a is not None]
    assert len(defined) == len(alpha) - (half_life - 1)
    assert all(a == pytest.approx(0.252, abs=1e-9) for a in defined)


@pytest.mark.unit
def test_rolling_alpha_wls_recent_dominates():
    """A late regime change moves WLS alpha far more than early history."""
    bench = [0.0004 * ((i * 41) % 9 - 4) for i in range(400)]
    # drift 0 for 300 sessions, then +0.002/day for the last 100
    asset = [(0.0 if i < 300 else 0.002) + b for i, b in enumerate(bench)]
    alpha = rolling_alpha_daily(asset, bench, None, half_life=20)
    late = alpha[-1]
    assert late is not None
    # With half-life 20 the 100 new-drift sessions dominate: annualized
    # alpha should exceed half the new regime's 0.504 (2x margin for noise).
    assert late > 0.25


@pytest.mark.unit
def test_rolling_alpha_wls_causality():
    """Perturbing returns after index i must not change alpha at <= i."""
    bench = [0.0005 * ((i * 37) % 11 - 5) for i in range(300)]
    asset = [0.001 + b + 0.0002 * ((i * 17) % 5) for i, b in enumerate(bench)]
    before = rolling_alpha_daily(asset, bench, None, half_life=30)
    shocked = asset[:200] + [a + 0.05 for a in asset[200:]]
    after = rolling_alpha_daily(shocked, bench, None, half_life=30)
    assert before[:200] == after[:200]


@pytest.mark.unit
def test_rolling_alpha_wls_degenerate_and_short():
    flat = [0.0] * 200
    wiggle = [0.001 * (i % 7) for i in range(200)]
    assert all(
        a is None for a in rolling_alpha_daily(wiggle, flat, None, half_life=20)
    )
    assert rolling_alpha_daily([0.01] * 10, [0.02] * 10, None, half_life=20) == [None] * 10


@pytest.mark.unit
def test_rolling_alpha_window_half_life_exclusive():
    bench = [0.001 * i for i in range(100)]
    asset = [0.001 * i for i in range(100)]
    with pytest.raises(ValueError, match="exactly one of window and half_life"):
        rolling_alpha_daily(asset, bench, 50, half_life=20)
    with pytest.raises(ValueError, match="exactly one of window and half_life"):
        rolling_alpha_daily(asset, bench, None)


@pytest.mark.unit
def test_rolling_slope_wls_linear_ramp():
    """WLS slope of a 0.01/session ramp is ~0.01 wherever defined."""
    values = [0.01 * i for i in range(80)]
    slope = rolling_slope(values, 20, half_life=60)
    assert slope[:19] == [None] * 19
    defined = [s for s in slope[19:] if s is not None]
    assert len(defined) == len(slope) - 19
    assert all(s == pytest.approx(0.01, rel=1e-6) for s in defined)


@pytest.mark.unit
def test_rolling_slope_wls_none_poisoning():
    """A None inside the trailing span poisons the WLS slope, like fixed mode."""
    values = [0.05] * 10 + [None] + [0.05] * 40
    slope = rolling_slope(values, 20, half_life=30)
    assert slope[29] is None  # span covers values[10], which is None
    assert slope[30] == pytest.approx(0.0)
    assert slope[18] is None  # warmup


@pytest.mark.unit
def test_rolling_slope_wls_causality():
    """Perturbing alphas after index i must not change slopes at <= i."""
    values = [0.001 * i + 0.0001 * ((i * 23) % 7) for i in range(120)]
    before = rolling_slope(values, 20, half_life=40)
    shocked = values[:70] + [v + 0.5 for v in values[70:]]
    after = rolling_slope(shocked, 20, half_life=40)
    assert before[:70] == after[:70]


@pytest.mark.unit
def test_rolling_slope_fixed_mode_unchanged():
    """half_life=None keeps the exact legacy behavior."""
    values = [0.01 * i for i in range(60)]
    slope = rolling_slope(values, 20)
    assert slope[:20] == [None] * 20
    assert all(s == pytest.approx(0.01) for s in slope[20:] if s is not None)
