"""Issue #36: NOW RPO deceleration alert + manual seat-count proxies.

Network-free: the pure flag computation and the config loader are
exercised against hand-built YoY series and fixtures, plus the real
``config/kpi_metrics.yaml`` (threshold sanity) and the real
``config/kpi_manual.yaml`` (proxy registration). A fake store wires the
render path (``render._kpi_data``) without touching EDGAR.
"""

from pathlib import Path

import pytest
import yaml

from portfolio_analysis import rpo_alerts
from portfolio_analysis.rpo_alerts import (
    RpoAlertConfigError,
    RpoDecelerationConfig,
    load_rpo_deceleration_config,
    rpo_deceleration_flag,
)

REPO_ROOT = Path(rpo_alerts.__file__).resolve().parents[2]
REAL_KPI_CONFIG = REPO_ROOT / "config" / "kpi_metrics.yaml"
REAL_MANUAL_CONFIG = REPO_ROOT / "config" / "kpi_manual.yaml"

NOW_CFG = RpoDecelerationConfig(yoy_floor_pct=21.0, qoq_drop_pp=5.0)


def _yoy(*pairs: tuple[str, float | None]) -> list[tuple[str, float | None]]:
    return list(pairs)


def _write(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "kpi_metrics.yaml"
    target.write_text(yaml.safe_dump(payload))
    return target


# --- the real config -------------------------------------------------------


def test_real_config_has_now_thresholds():
    cfg = load_rpo_deceleration_config(REAL_KPI_CONFIG)
    assert cfg["NOW"] == NOW_CFG


def test_real_config_still_loads_metric_registry():
    # The new top-level section must not break #29's KPI config loader.
    from portfolio_analysis import kpis

    assert "rpo" in kpis.load_kpi_config()["NOW"]


# --- config loader ----------------------------------------------------------


def test_missing_section_is_no_alerts_not_error(tmp_path):
    cfg = load_rpo_deceleration_config(_write(tmp_path, {"kpis": {"NOW": ["rpo"]}}))
    assert cfg == {}


def test_tickers_uppercased(tmp_path):
    payload = {"rpo_deceleration": {"now": {"yoy_floor_pct": 21.0, "qoq_drop_pp": 5.0}}}
    assert load_rpo_deceleration_config(_write(tmp_path, payload))["NOW"] == NOW_CFG


def test_malformed_section_rejected(tmp_path):
    bad = {"rpo_deceleration": {"NOW": {"yoy_floor_pct": "lots", "qoq_drop_pp": 5.0}}}
    with pytest.raises(RpoAlertConfigError, match="must be a number"):
        load_rpo_deceleration_config(_write(tmp_path, bad))


def test_missing_threshold_rejected(tmp_path):
    bad = {"rpo_deceleration": {"NOW": {"yoy_floor_pct": 21.0}}}
    with pytest.raises(RpoAlertConfigError, match="qoq_drop_pp"):
        load_rpo_deceleration_config(_write(tmp_path, bad))


# --- the flag ----------------------------------------------------------------


def test_floor_trigger():
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.25), ("2025-12-31", 0.204)), NOW_CFG)
    assert flag.flagged is True
    assert "20.4%" in flag.reason
    assert "21.0%" in flag.reason
    assert flag.latest_quarter == "2025-12-31"
    assert flag.latest_yoy == pytest.approx(0.204)


def test_floor_boundary_is_strictly_below():
    # "falls below 21%" - exactly 21.0% does not flag.
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.25), ("2025-12-31", 0.21)), NOW_CFG)
    assert flag.flagged is False
    assert flag.reason is None


def test_qoq_drop_trigger():
    # 30% -> 24% = 6pp drop, more than the 5pp threshold.
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.30), ("2025-12-31", 0.24)), NOW_CFG)
    assert flag.flagged is True
    assert "6.0pp" in flag.reason
    assert "5.0pp" in flag.reason
    assert flag.prior_yoy == pytest.approx(0.30)


def test_qoq_drop_boundary_is_strictly_more():
    # Exactly a 5pp drop does not flag ("drops >5pp"); stays above the floor.
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.27), ("2025-12-31", 0.22)), NOW_CFG)
    assert flag.flagged is False


def test_no_flag_near_current_level():
    # The ~21.3% level Daniel cited (2026-09-20): no deceleration, no flag.
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.22), ("2025-12-31", 0.213)), NOW_CFG)
    assert flag.flagged is False
    assert flag.latest_yoy == pytest.approx(0.213)


def test_both_triggers_combined():
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.30), ("2025-12-31", 0.19)), NOW_CFG)
    assert flag.flagged is True
    assert "19.0%" in flag.reason
    assert "11.0pp" in flag.reason


def test_rising_yoy_does_not_flag():
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.24), ("2025-12-31", 0.30)), NOW_CFG)
    assert flag.flagged is False


def test_none_entries_skipped_never_interpolated():
    flag = rpo_deceleration_flag(
        _yoy(("2025-06-30", None), ("2025-09-30", 0.30), ("2025-12-31", 0.24)), NOW_CFG
    )
    assert flag.flagged is True
    assert flag.prior_yoy == pytest.approx(0.30)


def test_latest_none_is_not_flaggable():
    flag = rpo_deceleration_flag(_yoy(("2025-09-30", 0.25), ("2025-12-31", None)), NOW_CFG)
    assert flag.flagged is False
    assert flag.latest_quarter == "2025-09-30"


def test_empty_series_no_crash():
    flag = rpo_deceleration_flag([], NOW_CFG)
    assert flag.flagged is False
    assert flag.latest_yoy is None


def test_single_quarter_evaluates_floor_only():
    below = rpo_deceleration_flag(_yoy(("2025-12-31", 0.19)), NOW_CFG)
    assert below.flagged is True
    assert below.prior_yoy is None
    above = rpo_deceleration_flag(_yoy(("2025-12-31", 0.25)), NOW_CFG)
    assert above.flagged is False


# --- manual seat-count proxies -------------------------------------------------


def test_proxy_metrics_registered_as_tracked_but_empty():
    from portfolio_analysis import manual_kpis

    cfg = manual_kpis.load_manual_kpis(REAL_MANUAL_CONFIG)
    assert cfg.metrics["NOW"]["customers_1m_acv"] == []
    assert cfg.metrics["NOW"]["net_revenue_retention"] == []


def test_proxy_panels_render_na_with_manual_label():
    from portfolio_analysis import manual_kpis

    cfg = manual_kpis.load_manual_kpis(REAL_MANUAL_CONFIG)
    panels = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    acv = next(p for p in panels if p["key"] == "customers_1m_acv")
    assert acv["label"] == "Customers with >$1M ACV"
    assert acv["format"] == "count"
    assert acv["group"] == "revenue"
    assert acv["source"] == "manual"
    assert acv["empty"] is True
    nrr = next(p for p in panels if p["key"] == "net_revenue_retention")
    assert nrr["format"] == "percent"
    assert nrr["empty"] is True


def test_proxy_datapoint_renders_with_source_and_date(tmp_path):
    # The v1 manual-entry path: a hand-entered >$1M-ACV count carries its
    # source and recording date through to the panel.
    from portfolio_analysis import manual_kpis

    payload = {
        "manual_kpis": {
            "NOW": {
                "customers_1m_acv": [
                    {
                        "quarter": "2026-06-30",
                        "value": 1200,
                        "source": "ServiceNow Q2 2026 earnings release, 2026-07-22",
                        "date_recorded": "2026-09-26",
                    }
                ]
            }
        }
    }
    cfg = manual_kpis.load_manual_kpis(_write(tmp_path, payload))
    (panel,) = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    assert panel["current"] == 1200.0
    assert panel["latest_source"] == "ServiceNow Q2 2026 earnings release, 2026-07-22"
    assert panel["latest_recorded"] == "2026-09-26"
    assert panel["empty"] is False


# --- render wiring -------------------------------------------------------------


class _FakeStore:
    def __init__(self, rpo_values: list[float]):
        quarters = [
            "2024-09-30",
            "2024-12-31",
            "2025-03-31",
            "2025-06-30",
            "2025-09-30",
            "2025-12-31",
        ]
        self._rpo = [(q, "2025-01-01", v) for q, v in zip(quarters, rpo_values, strict=True)]

    def kpi_quarters(self, ticker: str, metric: str):
        return list(self._rpo) if metric == "rpo" else []


def _rpo_panel(store: _FakeStore, ticker: str = "NOW") -> dict | None:
    from portfolio_analysis import render

    data = render._kpi_data(store, ticker)
    assert data is not None
    return next((m for m in data["metrics"] if m["key"] == "rpo"), None)


def test_render_attaches_alert_on_deceleration():
    # RPO YoY: 30% -> 24% = 6pp drop vs prior quarter -> flagged.
    panel = _rpo_panel(_FakeStore([100, 100, 100, 100, 130, 124]))
    assert panel is not None
    alert = panel.get("rpo_alert")
    assert alert is not None and alert["flagged"] is True
    assert "6.0pp" in alert["reason"]


def test_render_no_alert_when_growth_holds():
    # RPO YoY: 30% -> 31%: no floor breach, no 5pp drop.
    panel = _rpo_panel(_FakeStore([100, 100, 100, 100, 130, 131]))
    assert panel is not None
    assert panel.get("rpo_alert") is None


def test_render_no_alert_for_unconfigured_ticker():
    panel = _rpo_panel(_FakeStore([100, 100, 100, 100, 130, 124]), ticker="META")
    assert panel is None  # META has no RPO panel in kpi_metrics.yaml
