"""Rolling R² (issue #18): coefficient of determination of the OLS regression
of asset returns on benchmark returns.

R² = 1 - SSE/SST over the same window as beta/alpha: the share of the
asset's return variance the benchmark explains. It is NOT beta².
"""

import math
import random

import pytest

from portfolio_analysis.moves import correlation, ols_regression

DRIFT = 0.001


@pytest.mark.unit
def test_r_squared_is_one_on_a_perfect_fit():
    benchmark = [0.01, -0.005, 0.02, -0.015, 0.008]
    asset = [2 * b + DRIFT for b in benchmark]
    beta, _, r_squared = ols_regression(asset, benchmark, r_squared=True)
    assert beta == pytest.approx(2.0)
    assert r_squared == pytest.approx(1.0)


@pytest.mark.unit
def test_r_squared_is_near_zero_on_pure_noise():
    rng = random.Random(42)
    benchmark = [rng.gauss(0, 0.01) for _ in range(500)]
    asset = [rng.gauss(0, 0.02) for _ in range(500)]
    _, _, r_squared = ols_regression(asset, benchmark, r_squared=True)
    assert r_squared == pytest.approx(0.0, abs=0.05)


@pytest.mark.unit
def test_r_squared_equals_squared_correlation():
    """For single-factor OLS with an intercept, R² must equal Corr²."""
    rng = random.Random(7)
    benchmark = [rng.gauss(0, 0.012) for _ in range(250)]
    asset = [1.4 * b + rng.gauss(0, 0.008) for b in benchmark]
    _, _, r_squared = ols_regression(asset, benchmark, r_squared=True)
    rho = correlation(asset, benchmark)
    assert r_squared == pytest.approx(rho**2, rel=1e-9)


@pytest.mark.unit
def test_r_squared_is_not_beta_squared():
    """High sensitivity with a noisy fit: beta² and R² tell different stories."""
    rng = random.Random(11)
    benchmark = [rng.gauss(0, 0.01) for _ in range(400)]
    asset = [2.0 * b + rng.gauss(0, 0.03) for b in benchmark]
    beta, _, r_squared = ols_regression(asset, benchmark, r_squared=True)
    assert beta == pytest.approx(2.0, rel=0.1)
    assert r_squared < 0.5  # noisy fit despite beta ≈ 2
    assert r_squared != pytest.approx(beta**2)


@pytest.mark.unit
def test_r_squared_stays_within_unit_interval():
    rng = random.Random(99)
    for seed_scale in (0.001, 0.05):
        benchmark = [rng.gauss(0, 0.01) for _ in range(250)]
        asset = [0.3 * b + rng.gauss(0, seed_scale) for b in benchmark]
        _, _, r_squared = ols_regression(asset, benchmark, r_squared=True)
        assert 0.0 <= r_squared <= 1.0
        assert not math.isnan(r_squared)


@pytest.mark.unit
def test_r_squared_defaults_off_for_backward_compatibility():
    """Existing call sites unpack (beta, alpha) unchanged."""
    benchmark = [0.01, -0.005, 0.02, -0.015, 0.008]
    asset = [2 * b + DRIFT for b in benchmark]
    result = ols_regression(asset, benchmark)
    assert len(result) == 2
    beta, alpha = result
    assert beta == pytest.approx(2.0)
    assert alpha == pytest.approx(DRIFT)


@pytest.mark.unit
@pytest.mark.parametrize(
    "asset, benchmark",
    [
        ([0.01, 0.02], [0.01]),  # mismatched lengths
        ([0.01], [0.01]),  # fewer than two observations
        ([0.01, 0.02], [0.005, 0.005]),  # zero benchmark variance
        ([0.005, 0.005], [0.01, 0.02]),  # zero asset variance: R² undefined
    ],
)
def test_r_squared_rejects_degenerate_inputs(asset, benchmark):
    """Degenerate windows raise instead of fabricating an R²."""
    with pytest.raises(ValueError):
        ols_regression(asset, benchmark, r_squared=True)
