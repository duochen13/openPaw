"""Alpha and beta surfacing (issue #12).

The regression is r = alpha + beta * r_market + noise. These tests pin the
intercept end to end: the OLS intercept itself, its storage in Move rows,
the migration of pre-alpha databases and artifacts, and its display data in
the rendered chart.
"""

import json
import random
import sqlite3
from datetime import date, timedelta

import pytest

from portfolio_analysis.artifacts import MovesArtifact, read_moves, write_moves
from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import (
    Coverage,
    Move,
    aligned_returns,
    annualize_alpha,
    compute_moves,
    ols_regression,
)
from portfolio_analysis.render import chart_data
from portfolio_analysis.store import Store

PARAMS = MoveParams(beta_window=250, sigma_window=60, z_threshold=2.5)
DRIFT = 0.001


def _drift_series(n=300, drift=DRIFT, spike_at=299, spike=0.20, seed=7):
    """Benchmark noise with the asset tracking 2x the benchmark plus a daily
    drift, then one big idiosyncratic spike to guarantee a flagged day."""
    rng = random.Random(seed)
    bench_ret = [rng.gauss(0.0005, 0.012) for _ in range(n)]
    # Independent asset noise keeps the series off the exact regression line;
    # without it sigma collapses to floating-point dust (see test_cli_detect).
    asset_ret = [2 * b + drift + rng.gauss(0, 0.005) for b in bench_ret]
    asset_ret[spike_at] += spike
    start = date(2024, 1, 2)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(n + 1)]
    bench, asset = {dates[0]: 100.0}, {dates[0]: 100.0}
    for i, (b, a) in enumerate(zip(bench_ret, asset_ret, strict=True), start=1):
        bench[dates[i]] = bench[dates[i - 1]] * (1 + b)
        asset[dates[i]] = asset[dates[i - 1]] * (1 + a)
    return asset, bench, dates


def _artifact(moves, evaluated):
    return MovesArtifact(
        "META",
        "QQQ",
        PARAMS,
        Coverage(None, evaluated, 3, len(moves)),
        moves,
    )


@pytest.mark.unit
def test_alpha_is_the_ols_intercept():
    """On asset = 2*benchmark + 0.001 the intercept must be exactly 0.001."""
    benchmark = [0.01, -0.005, 0.02, -0.015, 0.008]
    asset = [2 * b + DRIFT for b in benchmark]
    beta, alpha = ols_regression(asset, benchmark)
    assert beta == pytest.approx(2.0)
    assert alpha == pytest.approx(DRIFT)


@pytest.mark.unit
def test_annualize_alpha_scales_by_trading_days():
    assert annualize_alpha(DRIFT) == pytest.approx(0.252)


@pytest.mark.unit
@pytest.mark.parametrize(
    "asset, benchmark",
    [
        ([0.01, 0.02], [0.01]),  # mismatched lengths
        ([0.01], [0.01]),  # fewer than two observations
        ([0.01, 0.02], [0.005, 0.005]),  # zero benchmark variance
    ],
)
def test_ols_regression_rejects_degenerate_inputs(asset, benchmark):
    with pytest.raises(ValueError):
        ols_regression(asset, benchmark)


@pytest.mark.unit
def test_compute_moves_stores_daily_alpha_and_a_consistent_decomposition():
    asset, bench, dates = _drift_series()
    moves, _ = compute_moves("META", "QQQ", asset, bench, PARAMS)
    (move,) = [m for m in moves if m.date == dates[-1]]
    # The spike day's own window ends the day before, so the intercept is
    # the raw daily drift, unpolluted by the spike.
    assert move.alpha == pytest.approx(DRIFT, abs=1e-3)
    assert move.beta == pytest.approx(2.0, abs=0.05)
    # The decomposition the chart shows must add up exactly.
    assert move.ret == pytest.approx(move.beta * move.benchmark_return + move.abnormal_return)


@pytest.mark.unit
def test_open_migrates_a_pre_alpha_database(tmp_path):
    """A database written before the alpha column existed opens fine; old
    rows read back with alpha 0.0 until detect-moves overwrites them."""
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE move (
            ticker TEXT NOT NULL, date TEXT NOT NULL, ret REAL NOT NULL,
            benchmark TEXT NOT NULL, benchmark_return REAL NOT NULL,
            beta REAL NOT NULL, abnormal_return REAL NOT NULL,
            sigma_60 REAL NOT NULL, z REAL NOT NULL,
            computed_at TEXT NOT NULL, PRIMARY KEY (ticker, date))"""
    )
    conn.execute(
        "INSERT INTO move VALUES ('META','2024-04-25',-0.10,'QQQ',-0.005,1.4,"
        "-0.093,0.025,-3.72,'2024-04-26T00:00:00')"
    )
    conn.commit()
    conn.close()

    store = Store.open(path)
    try:
        (row,) = store.moves("META")
        assert row["alpha"] == 0.0
        store.upsert_moves(
            [
                {
                    "ticker": "META",
                    "date": "2024-04-25",
                    "ret": -0.10,
                    "benchmark": "QQQ",
                    "benchmark_return": -0.005,
                    "beta": 1.4,
                    "alpha": 0.0003,
                    "abnormal_return": -0.093,
                    "sigma_60": 0.025,
                    "z": -3.72,
                }
            ]
        )
        (row,) = store.moves("META")
        assert row["alpha"] == pytest.approx(0.0003)
    finally:
        store.close()


@pytest.mark.unit
def test_artifacts_round_trip_carries_alpha(tmp_path):
    move = Move(
        ticker="META",
        date="2024-04-25",
        ret=-0.10,
        benchmark="QQQ",
        benchmark_return=-0.005,
        beta=1.4,
        alpha=0.0003,
        abnormal_return=-0.093,
        sigma_60=0.025,
        z=-3.72,
    )
    path = write_moves(
        tmp_path,
        MovesArtifact(
            "META",
            "QQQ",
            PARAMS,
            Coverage(None, ("2024-04-24", "2024-04-26"), 3, 1),
            [move],
        ),
    )
    assert json.loads(path.read_text())["moves"][0]["alpha"] == pytest.approx(0.0003)
    assert read_moves(path).moves[0].alpha == pytest.approx(0.0003)


@pytest.mark.unit
def test_pre_alpha_artifact_fails_with_a_regenerate_hint(tmp_path):
    path = tmp_path / "META.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ticker": "META",
                "benchmark": "QQQ",
                "params": {"beta_window": 250, "sigma_window": 60, "z_threshold": 2.5},
                "coverage": {
                    "price_series": None,
                    "evaluated": ["2024-04-24", "2024-04-26"],
                    "evaluated_days": 3,
                    "flagged_days": 0,
                },
                "moves": [],
            }
        )
    )
    with pytest.raises(ValueError, match="re-run detect-moves"):
        read_moves(path)


@pytest.mark.unit
def test_chart_data_carries_factor_regime_and_decomposition(tmp_path):
    asset, bench, dates = _drift_series()
    moves, _ = compute_moves("META", "QQQ", asset, bench, PARAMS)
    data = chart_data(
        _artifact(moves, (dates[250], dates[-1])),
        asset,
        bench,
        tmp_path,
        name="Meta Platforms",
    )

    factor = data["factor"]
    assert factor["benchmark"] == "QQQ"
    assert factor["window"] == 250
    assert factor["as_of"] == dates[-1]
    # The trailing window includes the spike day, so beta is pulled below 2;
    # pin the plumbing against the regression itself, plus loose sanity.
    _, ar, br = aligned_returns(asset, bench)
    exp_beta, exp_alpha = ols_regression(ar[-250:], br[-250:])
    assert factor["beta"] == pytest.approx(exp_beta)
    assert factor["alpha_annualized"] == pytest.approx(annualize_alpha(exp_alpha))
    assert 1.5 < factor["beta"] < 2.5
    assert factor["alpha_annualized"] > 0
    assert "forecast" in factor["note"]

    regime = data["regime"]
    assert regime["default_window"] == "250"
    assert set(regime["windows"]) == {"60", "125", "250"}
    reg = regime["windows"]["250"]
    # 300 days at a 21-session step: 4 sample points, strictly increasing.
    assert len(reg["dates"]) >= 2
    assert list(reg["dates"]) == sorted(reg["dates"])
    assert reg["dates"][-1] == dates[-1]
    assert reg["beta"][-1] == pytest.approx(factor["beta"])
    assert reg["alpha_annualized"][-1] == pytest.approx(factor["alpha_annualized"])
    # R² rides the identical trailing window: it must match the factor strip
    # value and stay inside its [0, 1] bounds.
    assert reg["r_squared"][-1] == pytest.approx(factor["r_squared"])
    assert all(0.0 <= r <= 1.0 for r in reg["r_squared"])
    assert len(reg["r_squared"]) == len(reg["dates"])
    # Slope rides the same sampled dates; the trailing point has enough
    # history (needs alpha 20 sessions back). Issue #39 removed acceleration.
    assert len(reg["alpha_slope"]) == len(reg["dates"])
    assert len(reg["signals"]) == len(reg["dates"])
    assert "alpha_accel" not in reg
    assert reg["alpha_slope"][-1] is not None
    assert set(reg["signals"]) <= {"turnaround", None}
    # The shorter windows sample the same series earlier and further back.
    assert len(regime["windows"]["60"]["dates"]) > len(reg["dates"])
    assert regime["windows"]["60"]["dates"][-1] == dates[-1]

    row = next(m for m in data["moves"] if m["date"] == dates[-1])
    assert row["alpha"] == pytest.approx(DRIFT, abs=1e-3)
    assert row["alpha_annualized"] == pytest.approx(0.252, abs=0.05)
    assert row["market_component"] + row["idiosyncratic_component"] == pytest.approx(row["return"])


@pytest.mark.unit
def test_chart_data_with_short_series_omits_factor_and_regime(tmp_path):
    """Fewer than one full beta window: no made-up numbers; the template
    hides the strip and the sparkline panel when these are empty."""
    data = chart_data(
        _artifact([], ("2024-04-24", "2024-04-26")),
        {"2024-04-23": 50, "2024-04-24": 100, "2024-04-25": 90, "2024-04-26": 95},
        {"2024-04-23": 90, "2024-04-24": 100, "2024-04-25": 99.5, "2024-04-26": 101},
        tmp_path,
        name="Meta",
    )
    assert data["factor"] is None
    empty = {
        "dates": [],
        "beta": [],
        "r_squared": [],
        "alpha_annualized": [],
        "alpha_slope": [],
        "alpha_slope_display": [],
        "signals": [],
    }
    assert data["regime"]["default_window"] == "250"
    assert data["regime"]["windows"] == {"60": empty, "125": empty, "250": empty}


@pytest.mark.unit
def test_chart_data_rejects_an_inconsistent_decomposition(tmp_path):
    """A hand-built move whose parts do not add up must fail loudly, not
    render a tooltip whose components contradict the return."""
    bad = Move(
        ticker="META",
        date="2024-04-25",
        ret=-0.10,
        benchmark="QQQ",
        benchmark_return=-0.005,
        beta=1.4,
        alpha=0.0003,
        abnormal_return=0.50,
        sigma_60=0.025,
        z=-3.72,
    )
    with pytest.raises(ValueError, match=r"beta\*benchmark_return"):
        chart_data(
            _artifact([bad], ("2024-04-24", "2024-04-26")),
            {"2024-04-23": 50, "2024-04-24": 100, "2024-04-25": 90, "2024-04-26": 95},
            {"2024-04-23": 90, "2024-04-24": 100, "2024-04-25": 99.5, "2024-04-26": 101},
            tmp_path,
            name="Meta",
        )


@pytest.mark.unit
def test_regime_fine_tail_is_bounded_and_daily(tmp_path):
    """Issue #41: each OLS window also ships a bounded daily-resolution tail
    for zoomed-in views, ending on the latest session."""
    from portfolio_analysis.render import _FINE_TAIL_SESSIONS

    asset, bench, dates = _drift_series()
    moves, _ = compute_moves("META", "QQQ", asset, bench, PARAMS)
    data = chart_data(
        _artifact(moves, (dates[250], dates[-1])),
        asset,
        bench,
        tmp_path,
        name="Meta Platforms",
    )
    regime = data["regime"]
    assert regime["fine_tail_sessions"] == _FINE_TAIL_SESSIONS
    assert set(regime["fine"]) == {"60", "125", "250"}
    for window, fine in regime["fine"].items():
        assert fine["dates"][-1] == dates[-1]
        assert list(fine["dates"]) == sorted(fine["dates"])
        assert len(fine["dates"]) <= _FINE_TAIL_SESSIONS + 1
        # Daily resolution: strictly more points than the monthly sampling.
        assert len(fine["dates"]) > len(regime["windows"][window]["dates"])
        assert "alpha_accel" not in fine
        assert set(fine["signals"]) <= {"turnaround", None}


@pytest.mark.unit
def test_tldr_is_under_100_words_and_states_missing_events(tmp_path):
    """Issue #42: generated summary, hard word cap, honest about gaps."""
    asset, bench, dates = _drift_series()
    moves, _ = compute_moves("META", "QQQ", asset, bench, PARAMS)
    data = chart_data(
        _artifact(moves, (dates[250], dates[-1])),
        asset,
        bench,
        tmp_path,
        name="Meta Platforms",
    )
    tldr = data["tldr"]
    assert isinstance(tldr, str) and tldr
    assert len(tldr.split()) < 100
    # No evidence bundles were collected for these moves: the TLDR must say
    # so instead of inventing drivers.
    assert "No dated events were collected" in tldr
    # The forward read is explicitly labeled as interpretation.
    assert "Interpretation:" in tldr


@pytest.mark.unit
def test_tldr_word_cap_is_hard():
    """The 100-word cap is enforced by truncation, not trusted to phrasing."""
    from portfolio_analysis.render import _tldr_text

    moves = [
        {"evidence_status": "available", "facts": [{"label": "Quarterly earnings reported"}]}
        for _ in range(50)
    ]
    regime = {"windows": {"250": {"alpha_annualized": [-0.1], "alpha_slope": [0.001]}}}
    text = _tldr_text(
        factor={"beta": 1.5}, regime=regime, moves=moves, benchmark="QQQ"
    )
    assert len(text.split()) < 100


@pytest.mark.unit
def test_tldr_names_collected_drivers_and_labels_interpretation():
    """Drivers come only from collected event windows; the forward read is
    labeled as interpretation."""
    from portfolio_analysis.render import _tldr_text

    moves = [
        {"evidence_status": "available", "facts": [{"label": "Quarterly earnings reported"}]},
        {"evidence_status": "available", "facts": [{"label": "8-K filed"}]},
        {"evidence_status": "missing", "facts": []},
    ]
    regime = {"windows": {"250": {"alpha_annualized": [0.05], "alpha_slope": [-0.001]}}}
    text = _tldr_text(
        factor={"beta": 0.9}, regime=regime, moves=moves, benchmark="QQQ"
    )
    assert "Earnings reports lined up with 1 of 3 unusual moves" in text
    assert "Interpretation:" in text
    assert len(text.split()) < 100
