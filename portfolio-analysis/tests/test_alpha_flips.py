"""Alpha-flip alert trigger (issue #32).

The trigger fires when the alpha slope crosses from negative to positive,
confirmed by acceleration > 0, persistence (3+ sessions), and a rolling-R²
noise gate. Tests use synthetic alpha series so the trigger - not the
regression stack - is what is under test.
"""

import math
import random

import pytest

from portfolio_analysis.signals import (
    FLIP_LOOKBACK,
    FLIP_MIN_R_SQUARED,
    FLIP_PERSISTENCE,
    detect_alpha_flips,
    rolling_slope,
)


def _v_shape(n: int = 120, trough: int = 49) -> list[float]:
    """Alpha that declines 0.004/session, then recovers 0.008/session.

    With the 20-session two-point slope the sign change lands at
    ``trough + 7`` and the trigger fires at ``trough + 9`` (persistence 3):
    slope[55] = -0.0004 < 0, slope[56] = +0.0002 > 0, so the most recent
    non-positive session is 55 and 58 - 55 = 3 hits the persistence floor.
    """
    alpha = [0.0] * n
    for i in range(n):
        if i <= trough:
            alpha[i] = -0.10 - 0.004 * i
        else:
            alpha[i] = (-0.10 - 0.004 * trough) + 0.008 * (i - trough)
    return alpha


@pytest.mark.unit
def test_flip_constants_documented():
    """The trigger definition lives in named constants, not magic numbers."""
    assert FLIP_LOOKBACK == 20
    assert FLIP_PERSISTENCE == 3
    assert FLIP_MIN_R_SQUARED == 0.5


@pytest.mark.unit
def test_flip_fires_once_on_synthetic_regime_change():
    alpha = _v_shape()
    slope = rolling_slope(alpha, 20)
    r2 = [0.8] * len(alpha)
    flips = detect_alpha_flips(alpha, slope, r2)
    assert len(flips) == 1
    flip = flips[0]
    assert flip.index == 58
    assert flip.alpha == pytest.approx(alpha[58])
    assert flip.slope == pytest.approx(slope[58])
    assert flip.acceleration == pytest.approx(slope[58] - slope[57])
    assert flip.acceleration > 0
    assert flip.r_squared == 0.8


@pytest.mark.unit
def test_flip_quiet_on_noisy_flat_alpha():
    """Low-R² noisy flat alpha must not spam: the noise gate holds."""
    rng = random.Random(7)
    n = 300
    alpha = [0.01 * math.sin(2 * math.pi * i / 47) + 0.004 * (rng.random() - 0.5) for i in range(n)]
    slope = rolling_slope(alpha, 20)
    assert detect_alpha_flips(alpha, slope, [0.15] * n) == []


@pytest.mark.unit
def test_flip_requires_persistence():
    """A two-session positive excursion (whipsaw) never fires."""
    slope = [-0.005] * 40 + [0.002, 0.003] + [-0.004] * 40
    alpha = [-0.2] * len(slope)
    assert detect_alpha_flips(alpha, slope, [0.8] * len(slope)) == []


@pytest.mark.unit
def test_flip_requires_acceleration():
    """Crossing with decelerating slope (accel <= 0 at fire time) never fires."""
    slope = [-0.01] * 40 + [0.006, 0.005, 0.004, 0.004, 0.004] + [-0.01] * 10
    alpha = [-0.2] * len(slope)
    assert detect_alpha_flips(alpha, slope, [0.8] * len(slope)) == []


@pytest.mark.unit
def test_flip_requires_r_squared_gate():
    """A genuine regime change on a low-R² fit stays quiet."""
    alpha = _v_shape()
    slope = rolling_slope(alpha, 20)
    assert detect_alpha_flips(alpha, slope, [0.3] * len(alpha)) == []


@pytest.mark.unit
def test_flip_without_r_squared_skips_gate():
    """r_squared=None disables the noise gate (caller takes responsibility)."""
    alpha = _v_shape()
    slope = rolling_slope(alpha, 20)
    flips = detect_alpha_flips(alpha, slope, None)
    assert len(flips) == 1 and flips[0].index == 58
    assert flips[0].r_squared is None


@pytest.mark.unit
def test_flip_rearms_after_new_crossing():
    """One regime change yields one alert; a second V re-arms and fires again."""
    n = 170
    alpha = [0.0] * n
    for i in range(n):
        if i <= 49:
            alpha[i] = -0.10 - 0.004 * i
        elif i <= 79:
            alpha[i] = -0.296 + 0.008 * (i - 49)
        elif i <= 109:
            alpha[i] = (-0.296 + 0.008 * 30) - 0.004 * (i - 79)
        else:
            alpha[i] = (-0.296 + 0.008 * 30 - 0.004 * 30) + 0.008 * (i - 109)
    slope = rolling_slope(alpha, 20)
    flips = detect_alpha_flips(alpha, slope, [0.8] * n)
    assert [f.index for f in flips] == [58, 118]


@pytest.mark.unit
def test_flip_none_gap_breaks_the_run():
    """A None gap over the inflection means the crossing cannot be confirmed: no fire."""
    alpha: list[float | None] = _v_shape()  # type: ignore[assignment]
    for i in range(50, 60):
        alpha[i] = None
    slope = rolling_slope(alpha, 20)
    assert detect_alpha_flips(alpha, slope, [0.8] * len(alpha)) == []


@pytest.mark.unit
def test_flip_stale_crossing_never_fires():
    """A crossing older than the lookback is history, not an inflection."""
    slope = [-0.01] * 30 + [0.002] * 30  # crossed 30 sessions ago, still rising
    alpha = [-0.2] * len(slope)
    # age = 29 > lookback 20 at every positive session
    assert detect_alpha_flips(alpha, slope, [0.8] * len(slope)) == []


@pytest.mark.unit
def test_flip_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        detect_alpha_flips([0.1] * 10, [0.01] * 9)
    with pytest.raises(ValueError, match="r_squared"):
        detect_alpha_flips([0.1] * 10, [0.01] * 10, [0.5] * 9)


@pytest.mark.unit
def test_flip_is_causal_no_look_ahead():
    """Appending future data must not change flips at earlier indices."""
    alpha = _v_shape()
    slope = rolling_slope(alpha, 20)
    flips_a = detect_alpha_flips(alpha, slope, [0.8] * len(alpha))
    alpha_b = alpha + [10.0] * 50
    slope_b = rolling_slope(alpha_b, 20)
    flips_b = detect_alpha_flips(alpha_b, slope_b, [0.8] * len(alpha_b))
    assert [f.index for f in flips_b if f.index < len(alpha)] == [f.index for f in flips_a]
