"""Unit tests for the issue-#33 walk-forward report dimensions in
scripts/backtest_alpha_signals.py: regime labeling, lead-time scoring, and
event aggregation. All synthetic - no network, no database."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_backtest():
    path = Path(__file__).resolve().parent.parent / "scripts" / "backtest_alpha_signals.py"
    spec = importlib.util.spec_from_file_location("backtest_alpha_signals", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_regime_by_date_labels_and_warmup():
    bt = _load_backtest()
    # 300 sessions: first 250 flat, then a +20% ramp -> bull at the end.
    prices = {f"d{i:04d}": 100.0 for i in range(250)}
    for i in range(250, 300):
        prices[f"d{i:04d}"] = 100.0 * (1 + 0.20 * (i - 249) / 50)
    out = bt.regime_by_date(prices)
    # No label before REGIME_WINDOW sessions of history exist.
    assert f"d{bt.REGIME_WINDOW - 1:04d}" not in out
    assert f"d{bt.REGIME_WINDOW:04d}" in out
    # Flat stretch -> sideways; ramped end -> bull.
    assert out[f"d{bt.REGIME_WINDOW:04d}"] == "sideways"
    assert out["d0299"] == "bull"


@pytest.mark.unit
def test_regime_by_date_bear():
    bt = _load_backtest()
    prices = {f"d{i:04d}": 100.0 * (0.999**i) for i in range(400)}
    out = bt.regime_by_date(prices)
    # 0.999**250 ~= 0.78 -> -22% trailing return -> bear.
    assert out["d0399"] == "bear"


@pytest.mark.unit
def test_cumulative_forward_excess_path():
    bt = _load_backtest()
    sret = [0.0, 0.01, 0.01, -0.05]
    bret = [0.0, 0.005, 0.005, 0.005]
    cum = bt.cumulative_forward_excess(sret, bret, 0, 10)
    assert len(cum) == 3  # truncated by series length
    # Gross-return difference, same convention as forward_excess.
    assert cum[0] == pytest.approx(1.01 - 1.005)
    assert cum[1] == pytest.approx(1.01**2 - 1.005**2)


@pytest.mark.unit
def test_score_events_lead_time_and_realization():
    bt = _load_backtest()
    # Stock beats the benchmark by 1pp/session from session 2 on.
    sret = [0.0] + [0.015] * 130
    bret = [0.0] + [0.005] * 130
    dates = [f"d{i:04d}" for i in range(131)]
    inputs = {
        "AAA": {
            "dates": dates,
            "sret": sret,
            "bret": bret,
            "alpha": [0.1] * 131,
            "t_stats": [2.0] * 131,
            "slope": [0.01] * 131,
            "r2": [0.8] * 131,
        }
    }
    recs = bt.score_events(inputs, [("AAA", 0)], {})
    assert len(recs) == 1
    rec = recs[0]
    assert rec["regime"] is None  # no regime map entry -> None, not a crash
    # Cumulative excess crosses +3% at session 3 (1.01**3 - 1 ~= 3.03%).
    assert rec["realized"] is True
    assert rec["lead_time"] == 3
    assert rec["excess_20"] == pytest.approx(1.015**20 - 1.005**20)


@pytest.mark.unit
def test_score_events_unrealized_when_move_never_comes():
    bt = _load_backtest()
    sret = [0.0] + [0.001] * 130  # never reaches +3% within 120 sessions
    bret = [0.0] + [0.001] * 130
    dates = [f"d{i:04d}" for i in range(131)]
    inputs = {
        "AAA": {
            "dates": dates,
            "sret": sret,
            "bret": bret,
            "alpha": [0.1] * 131,
            "t_stats": [2.0] * 131,
            "slope": [0.01] * 131,
            "r2": [0.8] * 131,
        }
    }
    (rec,) = bt.score_events(inputs, [("AAA", 0)], {})
    assert rec["realized"] is False
    assert rec["lead_time"] is None


@pytest.mark.unit
def test_summarize_event_records_aggregates():
    bt = _load_backtest()
    recs = [
        {
            "excess_20": 0.05,
            "excess_60": 0.10,
            "excess_120": 0.10,
            "realized": True,
            "lead_time": 5,
        },
        {
            "excess_20": -0.02,
            "excess_60": -0.05,
            "excess_120": -0.05,
            "realized": True,
            "lead_time": 15,
        },
        {
            "excess_20": None,
            "excess_60": None,
            "excess_120": None,
            "realized": False,
            "lead_time": None,
        },
    ]
    s = bt.summarize_event_records(recs)
    assert s["n"] == 3
    assert s["h60"]["n"] == 2
    assert s["h60"]["hit_rate"] == pytest.approx(0.5)
    assert s["realized_rate"] == pytest.approx(2 / 3)
    assert s["median_lead"] == pytest.approx(10.0)
    assert s["realized_within_20"] == pytest.approx(2 / 3)
    assert s["realized_within_60"] == pytest.approx(2 / 3)
    assert s["h20"]["mean"] == pytest.approx(0.015)
