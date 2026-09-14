import random
from datetime import date, timedelta
from statistics import stdev

import pytest

from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import aligned_returns, compute_moves

PARAMS = MoveParams(beta_window=250, sigma_window=60, z_threshold=2.5)


def _series(n=252, spike_at=None, spike=0.20):
    """A synthetic pair whose true beta is 2.0, plus bounded pseudo-random
    idiosyncratic noise so the abnormal return has real, nonzero variance.

    The noise must NOT be a fixed function of the benchmark return. Noise
    collinear with the benchmark loads onto beta instead of the residual: an
    earlier version of this fixture used `+/-0.001` keyed to the same parity
    as `br`, which made the true beta 2.1, drove every abnormal return to
    floating-point dust, and left sigma at ~1e-17 and z at ~1e16. The flagging
    assertions still passed, for entirely the wrong reason.

    Seeded, so the series is identical on every run. The noise is bounded at
    +/-0.002 against a sigma of roughly 0.00115, so no ordinary day can reach
    the 2.5-sigma threshold by chance and `test_a_clean_series_flags_nothing`
    cannot flake.
    """
    rng = random.Random(20240425)
    asset, bench = {}, {}
    asset_px, bench_px = 100.0, 100.0
    start = date(2020, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(n + 1)]
    asset[dates[0]], bench[dates[0]] = asset_px, bench_px
    for i in range(1, n + 1):
        br = 0.01 if i % 2 else -0.01
        noise = (rng.random() - 0.5) * 0.004
        ar = 2 * br + noise
        if spike_at is not None and i == spike_at:
            ar = 2 * br + spike
        bench_px *= 1 + br
        asset_px *= 1 + ar
        bench[dates[i]], asset[dates[i]] = bench_px, asset_px
    return asset, bench, dates


@pytest.mark.unit
def test_the_warm_up_period_is_not_evaluated():
    """With 252 returns and a 250-day beta window, only the final two days
    are evaluable."""
    asset, bench, _ = _series(n=252)
    _, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert coverage.evaluated_days == 2


@pytest.mark.unit
def test_a_clean_series_flags_nothing():
    # n=400, not 252: with a 250-day warm-up, n=252 leaves two evaluable days,
    # and "no false positives" over a sample of two is not a claim.
    asset, bench, _ = _series(n=400)
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert moves == []
    assert coverage.flagged_days == 0


@pytest.mark.unit
def test_an_injected_spike_is_flagged_with_the_right_sign():
    asset, bench, dates = _series(n=252, spike_at=251, spike=0.20)
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert coverage.flagged_days == 1
    move = moves[0]
    assert move.date == dates[251]
    assert move.ticker == "TEST"
    assert move.benchmark == "BENCH"
    assert move.beta == pytest.approx(2.0, abs=0.05)
    assert move.abnormal_return == pytest.approx(0.20, abs=0.01)
    assert move.z > 2.5


@pytest.mark.unit
def test_a_downward_spike_is_flagged_too():
    asset, bench, _ = _series(n=252, spike_at=251, spike=-0.20)
    moves, _ = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert len(moves) == 1
    assert moves[0].z < -2.5


@pytest.mark.unit
def test_abnormal_return_equals_return_minus_beta_times_benchmark():
    asset, bench, _ = _series(n=252, spike_at=251, spike=0.20)
    moves, _ = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    move = moves[0]
    assert move.abnormal_return == pytest.approx(
        move.ret - move.beta * move.benchmark_return
    )


@pytest.mark.unit
def test_z_equals_abnormal_return_over_sigma():
    asset, bench, _ = _series(n=252, spike_at=251, spike=0.20)
    move = compute_moves("TEST", "BENCH", asset, bench, PARAMS)[0][0]
    assert move.z == pytest.approx(move.abnormal_return / move.sigma_60)


@pytest.mark.unit
def test_sigma_uses_exactly_the_60_abnormal_returns_before_the_day():
    """Pins the sigma window offline.

    The beta window's exclusion of day t is pinned by the beta assertion
    above. The sigma window's was not: including day t would take sigma from
    ~0.0011 to ~0.026 and z from ~180 to ~8, which is still over the 2.5
    threshold, so every other test in this file still passes. Until this
    test existed the only thing holding that boundary was a network test
    that the default suite does not run.
    """
    asset, bench, _ = _series(n=252, spike_at=251, spike=0.20)
    moves, _ = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    move = moves[0]

    dates, ar, br = aligned_returns(asset, bench)
    i = dates.index(move.date)
    abnormal = [ar[j] - move.beta * br[j] for j in range(i - 60, i)]
    assert len(abnormal) == 60
    assert move.sigma_60 == pytest.approx(stdev(abnormal), rel=1e-12)


@pytest.mark.unit
def test_a_ticker_shorter_than_the_benchmark_reports_coverage_not_an_error():
    """A newly listed ticker is a coverage fact, not a failure.

    The benchmark is always fetched at full depth, so counting the whole
    symmetric difference made every short ticker raise 'the two series
    disagree about the trading calendar'.
    """
    _, bench, dates = _series(n=400)
    asset_full, _, _ = _series(n=400)
    asset = {d: asset_full[d] for d in dates[-120:]}
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert moves == []
    assert coverage.evaluated_days == 0
    assert coverage.evaluated is None


@pytest.mark.unit
def test_coverage_reports_both_ranges():
    asset, bench, dates = _series(n=252)
    _, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert coverage.price_series == (dates[0], dates[-1])
    # dates[0] is the base for the first return, so returns start at dates[1]
    # and the first evaluable day is 250 returns later.
    assert coverage.evaluated == (dates[251], dates[252])


@pytest.mark.unit
def test_too_short_a_series_yields_no_moves_rather_than_raising():
    """A newly listed ticker has no evaluable days yet. That is a coverage
    fact to report, not an error."""
    asset, bench, _ = _series(n=10)
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert moves == []
    assert coverage.evaluated_days == 0
    assert coverage.evaluated is None
