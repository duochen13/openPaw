"""End-to-end verification against live Yahoo data.

Every expected value here was measured on 2026-09-13 and is recorded in
docs/plans/2026-09-13-portfolio-analysis-foundation.md. Marked `network` and
excluded from the default run: a test that fails when Yahoo is down is not a
test of this code.

Tolerances are loose on counts and ranges because the series grows by one bar
per trading day, and tight on the 2024-04-25 statistics because those are
computed from a fixed historical window that does not move.
"""
import pytest

from portfolio_analysis import prices
from portfolio_analysis.config import load_portfolio
from portfolio_analysis.moves import compute_moves

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def computed():
    portfolio = load_portfolio()
    series = {
        symbol: {
            bar["date"]: bar["adj_close"]
            for bar in prices.fetch_yahoo(symbol, years=portfolio.price_years)
        }
        for symbol in ("META", portfolio.benchmark)
    }
    moves, coverage = compute_moves(
        "META", portfolio.benchmark, series["META"],
        series[portfolio.benchmark], portfolio.move_params,
    )
    return moves, coverage


def test_six_fetched_years_yield_about_five_evaluable_ones(computed):
    _, coverage = computed
    # Measured 2026-09-13: 1506 bars in, 1255 evaluable out.
    assert coverage.evaluated_days == pytest.approx(1255, abs=30)


def test_the_flagged_rate_is_in_the_expected_band(computed):
    """Measured 30 of 1255, or 2.39%. Under a normal distribution |z| >= 2.5
    is 1.24%; return distributions have fatter tails, so 2-3% is expected."""
    _, coverage = computed
    rate = coverage.flagged_days / coverage.evaluated_days
    assert 0.015 <= rate <= 0.035, f"flagged {coverage.flagged_days} ({rate:.2%})"


def _require_evaluable(coverage, date):
    """Skip, rather than fail, once a date slides out of the window.

    The fetch window is `now - 6*365.25 days`, so it moves forward about 252
    trading days a year. A date needs 250 returns before it inside the window
    to be evaluated at all. 2022-02-03 has roughly 99 trading days of margin
    as of 2026-09-14, so it drops out of the evaluable span around February
    2027; 2024-04-25 around 2029. These are `network` tests nothing runs by
    default, so a deterministic expiry would surface later as a mystery
    regression. Skipping with the reason keeps the signal honest.
    """
    if coverage.evaluated is None or date < coverage.evaluated[0]:
        pytest.skip(
            f"{date} is no longer inside the evaluable span "
            f"{coverage.evaluated}; the six-year fetch window has slid past it. "
            "This is expected with time, not a regression."
        )


def test_meta_2024_04_25_is_flagged_with_the_measured_statistics(computed):
    moves, coverage = computed
    _require_evaluable(coverage, "2024-04-25")
    by_date = {m.date: m for m in moves}
    assert "2024-04-25" in by_date, f"flagged dates: {sorted(by_date)}"
    move = by_date["2024-04-25"]
    assert move.ret == pytest.approx(-0.105613, abs=1e-5)
    assert move.benchmark_return == pytest.approx(-0.004830, abs=1e-5)
    assert move.beta == pytest.approx(1.490, abs=0.01)
    assert move.abnormal_return == pytest.approx(-0.098419, abs=1e-4)
    assert move.sigma_60 == pytest.approx(0.026083, abs=1e-4)
    assert move.z == pytest.approx(-3.77, abs=0.02)


def test_beta_correction_is_not_cosmetic(computed):
    """Naive subtraction gives -10.08%; beta-adjusted gives -9.84%. If beta
    were 1.0 these would coincide and the whole rule would be decoration."""
    _require_evaluable(computed[1], "2024-04-25")
    move = {m.date: m for m in computed[0]}["2024-04-25"]
    naive = move.ret - move.benchmark_return
    assert abs(naive - move.abnormal_return) > 0.002


def test_meta_2022_02_03_is_the_largest_flagged_move(computed):
    """The -26.4% earnings crash. Measured z -16.30."""
    moves, coverage = computed
    _require_evaluable(coverage, "2022-02-03")
    largest = min(moves, key=lambda m: m.z)
    assert largest.date == "2022-02-03"
    assert largest.z == pytest.approx(-16.30, abs=0.05)
