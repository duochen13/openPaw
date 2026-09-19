"""Alpha slope/acceleration metrics and turnaround signals (issue #19)."""

import importlib.util
from pathlib import Path

import pytest

from portfolio_analysis.signals import (
    EARLY_WATCH,
    REGIME_WINDOWS,
    SLOPE_SPAN,
    TURNAROUND,
    TURNAROUND_STRONG,
    alpha_acceleration,
    alpha_signal,
    rolling_alpha_daily,
    rolling_slope,
)


@pytest.mark.unit
def test_slope_span_and_window_contract():
    """The template's window switch and the backtest rely on these values."""
    assert SLOPE_SPAN == 20
    assert REGIME_WINDOWS == (60, 125, 250)


@pytest.mark.unit
def test_rolling_slope_linear_ramp():
    """A ramp of 0.01/session has slope exactly 0.01 wherever defined."""
    values = [0.01 * i for i in range(60)]
    slope = rolling_slope(values, 20)
    assert slope[:20] == [None] * 20
    assert all(s == pytest.approx(0.01) for s in slope[20:] if s is not None)
    assert len([s for s in slope[20:] if s is not None]) == 40


@pytest.mark.unit
def test_rolling_slope_none_propagation():
    """A None endpoint poisons the slope; it is never silently skipped."""
    values = [0.05] * 10 + [None] + [0.05] * 40
    slope = rolling_slope(values, 20)
    assert slope[30] is None  # spans values[10], which is None
    assert slope[31] == pytest.approx(0.0)
    assert slope[9] is None  # warmup


@pytest.mark.unit
def test_alpha_acceleration_quadratic():
    """a[i] = c*i^2 -> slope[i] = c*(2i-20), accel[i] = 40c exactly."""
    c = 0.0002
    values = [c * i * i for i in range(80)]
    accel = alpha_acceleration(rolling_slope(values, 20), 20)
    assert accel[:40] == [None] * 40
    defined = [a for a in accel[40:] if a is not None]
    assert len(defined) == 40
    assert all(a == pytest.approx(40 * c) for a in defined)


@pytest.mark.unit
def test_rolling_alpha_daily_known_drift():
    """asset = 0.001 + bench: daily alpha is exactly 0.001 -> 0.252 annualized."""
    bench = [0.0005 * ((i * 37) % 11 - 5) for i in range(400)]
    asset = [0.001 + b for b in bench]
    alpha = rolling_alpha_daily(asset, bench, 250)
    assert alpha[:249] == [None] * 249
    defined = [a for a in alpha[249:] if a is not None]
    assert len(defined) == len(alpha) - 249
    assert all(a == pytest.approx(0.252, abs=1e-9) for a in defined)


@pytest.mark.unit
def test_rolling_alpha_daily_short_and_degenerate():
    assert rolling_alpha_daily([0.01] * 10, [0.02] * 10, 250) == [None] * 10
    # A flat benchmark has zero variance: every window is undefined, never zero.
    flat = [0.0] * 300
    wiggle = [0.001 * (i % 7) for i in range(300)]
    assert all(a is None for a in rolling_alpha_daily(wiggle, flat, 250))


@pytest.mark.unit
def test_rolling_alpha_daily_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        rolling_alpha_daily([0.01] * 10, [0.02] * 9, 5)


@pytest.mark.unit
@pytest.mark.parametrize(
    "alpha,slope,accel,expected",
    [
        (-0.20, 0.005, 0.001, TURNAROUND_STRONG),
        (-0.20, 0.005, -0.001, TURNAROUND),
        (-0.20, 0.005, 0.0, TURNAROUND),  # accel == 0 is not > 0
        (-0.20, 0.005, None, TURNAROUND),
        (-0.20, -0.005, 0.001, EARLY_WATCH),
        (-0.20, -0.005, None, None),
        (-0.20, -0.005, -0.001, None),  # plain deterioration: no signal
        (0.10, 0.005, 0.001, None),  # positive alpha is not a reversal setup
        (-0.20, 0.0, 0.001, None),  # slope == 0 is not > 0
        (0.0, 0.005, 0.001, None),  # alpha == 0 is not < 0
        (None, 0.005, 0.001, None),
        (-0.20, None, 0.001, None),
    ],
)
def test_alpha_signal_kinds(alpha, slope, accel, expected):
    assert alpha_signal(alpha, slope, accel) == expected


@pytest.mark.unit
def test_signals_are_causal_no_look_ahead():
    """Appending future data must not change slope/accel at earlier indices."""
    values = [0.001 * i + 0.0001 * (i % 5) for i in range(100)]
    slope_a = rolling_slope(values, 20)
    accel_a = alpha_acceleration(slope_a, 20)
    extended = values + [10.0] * 50
    slope_b = rolling_slope(extended, 20)
    accel_b = alpha_acceleration(slope_b, 20)
    assert slope_b[:100] == slope_a
    assert accel_b[:100] == accel_a
    # ... but the future does change the future
    assert slope_b[100] != slope_a[99]


def _load_backtest():
    path = (
        Path(__file__).resolve().parent.parent / "scripts" / "backtest_alpha_signals.py"
    )
    spec = importlib.util.spec_from_file_location("backtest_alpha_signals", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_backtest_cross_up_needs_strict_crossing():
    bt = _load_backtest()
    assert bt.cross_up([None, -0.1, 0.1], 2) is True
    assert bt.cross_up([-0.1, 0.1, 0.2], 2) is False  # already positive
    assert bt.cross_up([-0.1, 0.0, 0.1], 1) is False  # touches zero, no cross
    assert bt.cross_up([None, None, 0.1], 2) is False  # needs both sides


@pytest.mark.unit
def test_backtest_forward_excess_starts_after_t():
    """Forward window is t+1..t+h; a short forward tail yields None, not a number."""
    bt = _load_backtest()
    stock = [0.01] * 200
    bench = [0.005] * 200
    assert bt.forward_excess(stock, bench, 50, 20) == pytest.approx(
        1.01**20 - 1.005**20
    )
    assert bt.forward_excess(stock, bench, 195, 20) is None
    assert bt.forward_excess(stock, bench, 179, 20) == pytest.approx(
        1.01**20 - 1.005**20
    )
