"""WLS-regression slope over the selected timeframe (issue #50).

``rolling_slope(values, span, half_life=...)`` fits a weighted least-squares
line through the trailing ``span`` alpha points with exponential decay
weights ``w = 0.5 ** ((t - i) / half_life)``. These tests pin down the limit
behaviors, the causality invariant, the span knob (10/20/30), and the legacy
two-point path.

Note on the issue's "tiny half_life ≈ two-point" phrasing: the two are
different estimators and do not agree numerically on noisy data (verified:
hl=2 gives +0.001516 vs two-point +0.002046 on the fixture ramp). What IS
true - and what these tests assert - is that (a) on a clean linear trend all
methods agree exactly, and (b) a small half-life makes the slope insensitive
to old points and hypersensitive to recent ones, i.e. it behaves like a
"recent-days" estimator the way the two-point formula does.
"""

import math

import pytest

from portfolio_analysis.moves import decay_weights, ols_regression
from portfolio_analysis.signals import SLOPE_SPAN, SLOPE_SPANS, rolling_slope


def _noisy_ramp(n: int = 60) -> list[float]:
    """Deterministic alpha-like series: linear drift plus wiggle."""
    return [0.002 * i + 0.01 * math.sin(i * 1.7) for i in range(n)]


def _ols_slope(window: list[float]) -> float:
    beta, _ = ols_regression(window, list(range(len(window))))
    return beta


def test_decay_weights_infinite_half_life_is_uniform():
    weights = decay_weights(20, float("inf"))
    assert weights == pytest.approx([1 / 20] * 20)


def test_wls_slope_infinite_half_life_matches_equal_weight_ols():
    """half_life -> infinity recovers the equal-weight OLS slope (issue #50)."""
    values = _noisy_ramp()
    for span in (10, 20, 30):
        got = rolling_slope(values, span, half_life=float("inf"))
        for i in range(span - 1, len(values)):
            expected = _ols_slope(values[i - span + 1 : i + 1])
            assert got[i] == pytest.approx(expected), f"span={span} i={i}"
        assert all(v is None for v in got[: span - 1])


def test_wls_slope_linear_ramp_all_methods_agree():
    """On a clean linear trend every estimator recovers the true rate."""
    values = [0.01 * i for i in range(60)]
    for span in SLOPE_SPANS:
        two_point = rolling_slope(values, span)[-1]
        wls_inf = rolling_slope(values, span, half_life=float("inf"))[-1]
        wls_small = rolling_slope(values, span, half_life=2.0)[-1]
        assert two_point == pytest.approx(0.01)
        assert wls_inf == pytest.approx(0.01)
        assert wls_small == pytest.approx(0.01)


def test_wls_slope_recency_small_half_life():
    """A small half-life behaves like a recent-days estimator (issue #50).

    Perturbing an old point in the window barely moves the slope; perturbing
    the most recent point moves it far more than under ~equal weighting.
    """
    values = _noisy_ramp()
    span = 20
    base_small = rolling_slope(values, span, half_life=2.0)[-1]
    base_even = rolling_slope(values, span, half_life=1e12)[-1]

    old = values.copy()
    old[-span] += 0.05
    d_old_small = abs(rolling_slope(old, span, half_life=2.0)[-1] - base_small)
    d_old_even = abs(rolling_slope(old, span, half_life=1e12)[-1] - base_even)
    assert d_old_small < d_old_even / 5  # old points nearly ignored

    new = values.copy()
    new[-1] += 0.05
    d_new_small = abs(rolling_slope(new, span, half_life=2.0)[-1] - base_small)
    d_new_even = abs(rolling_slope(new, span, half_life=1e12)[-1] - base_even)
    assert d_new_small > d_new_even  # recent points dominate


def test_wls_slope_causality_span_variants():
    """Perturbing future alphas never changes already-computed slopes."""
    for span in SLOPE_SPANS:
        values = _noisy_ramp()
        before = rolling_slope(values, span, half_life=30.0)
        shocked = values.copy()
        shocked[-1] += 1.0
        shocked[-2] -= 1.0
        after = rolling_slope(shocked, span, half_life=30.0)
        # Only the trailing `span` slopes can see the shocked points.
        assert before[:-span] == after[:-span]


def test_two_point_legacy_preserved():
    """half_life=None keeps the original (v[i]-v[i-span])/span formula."""
    values = _noisy_ramp()
    for span in SLOPE_SPANS:
        got = rolling_slope(values, span)
        assert all(v is None for v in got[:span])
        for i in range(span, len(values)):
            assert got[i] == pytest.approx((values[i] - values[i - span]) / span)


def test_wls_slope_none_poisoning_spans():
    """A None anywhere in the trailing span poisons the slope (all spans)."""
    for span in SLOPE_SPANS:
        values = _noisy_ramp(3 * span)
        values[span] = None
        got = rolling_slope(values, span, half_life=30.0)
        # Index 2*span-1 has the None at the head of its trailing span.
        assert got[2 * span - 1] is None
        # ...but later points with a clean trailing span recover.
        assert got[3 * span - 1] is not None


def test_wls_slope_span_warmup():
    """First span-1 entries stay None for every span (issue #50)."""
    values = _noisy_ramp()
    for span in SLOPE_SPANS:
        got = rolling_slope(values, span, half_life=30.0)
        assert all(v is None for v in got[: span - 1])
        assert got[span - 1] is not None


def test_slope_spans_constant():
    assert SLOPE_SPANS == (10, 20, 30)
    assert SLOPE_SPAN in SLOPE_SPANS


def _synthetic_prices(n: int = 500):
    """Deterministic price/benchmark dicts with a wiggly drift (no DB needed)."""
    import datetime

    base = datetime.date(2024, 1, 1)
    dates = [(base + datetime.timedelta(days=i)).isoformat() for i in range(n)]
    prices = {d: 100 * (1.001**i) * (1 + 0.002 * math.sin(i * 1.3)) for i, d in enumerate(dates)}
    bench = {d: 100 * (1.0005**i) for i, d in enumerate(dates)}
    return prices, bench


def test_regime_payloads_keep_two_point_slope():
    """Issue #50: the fixed and WLS payloads keep the legacy two-point slope.

    Only the dedicated ``wls_slope`` payload may use WLS regression. The
    sampled slopes must match the two-point formula recomputed from the daily
    series exactly, and must differ from the WLS-regression slope somewhere
    (so the test can actually tell the estimators apart).
    """
    from portfolio_analysis.moves import aligned_returns
    from portfolio_analysis.render import _regime_points
    from portfolio_analysis.signals import rolling_alpha_daily

    prices, bench = _synthetic_prices()
    rdates, sret, bret = aligned_returns(prices, bench)
    date_to_idx = {d: i for i, d in enumerate(rdates)}

    cases = [
        ("fixed", _regime_points(prices, bench, window=250), rolling_alpha_daily(sret, bret, 250)),
        (
            "wls",
            _regime_points(prices, bench, half_life=60.0),
            rolling_alpha_daily(sret, bret, None, half_life=60.0),
        ),
    ]
    for name, out, alpha_daily in cases:
        assert len(out["dates"]) > 5, f"{name}: fixture too short"
        two_point = rolling_slope(alpha_daily, 20)
        wls_reg = rolling_slope(alpha_daily, 20, half_life=60.0)
        distinguished = False
        for d, s in zip(out["dates"], out["alpha_slope"], strict=True):
            i = date_to_idx[d]
            assert s == pytest.approx(two_point[i]), (
                f"{name} payload slope is not the two-point formula at {d}"
            )
            if s is not None and wls_reg[i] is not None and s != pytest.approx(wls_reg[i]):
                distinguished = True
        assert distinguished, f"{name}: fixture cannot tell the estimators apart"


def test_wls_slope_payload_dates_align_with_wls_payload():
    """Issue #50 acceptance: the slope payload's dates line up exactly with
    the base WLS payload's dates, for both monthly and fine sampling."""
    from portfolio_analysis.render import (
        _FINE_TAIL_SESSIONS,
        _regime_points,
        _wls_slope_payload,
    )

    prices, bench = _synthetic_prices()
    for fine, wls_kwargs in (
        (False, {}),
        (True, {"step": 1, "tail": _FINE_TAIL_SESSIONS}),
    ):
        base = _regime_points(prices, bench, half_life=60.0, **wls_kwargs)
        slope = _wls_slope_payload(prices, bench, fine=fine)
        assert set(slope) >= {"20", "60", "120"}
        for span in ("10", "20", "30"):
            got = slope["60"][span]["dates"]
            assert got == base["dates"], (
                f"fine={fine} span={span}: {len(got)} slope dates vs {len(base['dates'])} wls dates"
            )
