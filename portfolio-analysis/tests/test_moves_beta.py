import pytest

from portfolio_analysis.moves import ols_beta


@pytest.mark.unit
def test_a_perfect_two_times_series_has_beta_two():
    bench = [0.01, -0.01, 0.02, -0.02, 0.015]
    asset = [2 * b for b in bench]
    assert ols_beta(asset, bench) == pytest.approx(2.0)


@pytest.mark.unit
def test_beta_is_unaffected_by_a_constant_offset():
    """An intercept is alpha, not beta. Adding a constant drift to the asset
    must not change the slope."""
    bench = [0.01, -0.01, 0.02, -0.02, 0.015]
    asset = [2 * b + 0.005 for b in bench]
    assert ols_beta(asset, bench) == pytest.approx(2.0)


@pytest.mark.unit
def test_an_uncorrelated_series_has_beta_near_zero():
    bench = [0.01, -0.01, 0.01, -0.01]
    asset = [0.02, 0.02, -0.02, -0.02]
    assert ols_beta(asset, bench) == pytest.approx(0.0)


@pytest.mark.unit
def test_a_flat_benchmark_raises_rather_than_dividing_by_zero():
    with pytest.raises(ValueError, match="zero variance"):
        ols_beta([0.01, 0.02, 0.03], [0.01, 0.01, 0.01])


@pytest.mark.unit
def test_mismatched_lengths_raise():
    with pytest.raises(ValueError, match="same length"):
        ols_beta([0.01, 0.02], [0.01])


@pytest.mark.unit
def test_fewer_than_two_observations_raise():
    with pytest.raises(ValueError, match="at least two"):
        ols_beta([0.01], [0.01])
