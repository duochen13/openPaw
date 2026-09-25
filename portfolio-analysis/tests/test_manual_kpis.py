"""Unit tests for manual_kpis.py (issue #59).

All network-free: the loader is exercised against the real
``config/kpi_manual.yaml`` (real, cited figures) plus hand-built
malformed fixtures. These run under the default ``-m 'not network'``
selection.
"""

from pathlib import Path

import pytest
import yaml

from portfolio_analysis import manual_kpis
from portfolio_analysis.manual_kpis import ManualKpiError, load_manual_kpis

REPO_ROOT = Path(manual_kpis.__file__).resolve().parents[2]
REAL_CONFIG = REPO_ROOT / "config" / "kpi_manual.yaml"


def _write(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "kpi_manual.yaml"
    target.write_text(yaml.safe_dump(payload))
    return target


def _point(quarter: str, value: float) -> dict:
    return {
        "quarter": quarter,
        "value": value,
        "source": "Test earnings release",
        "date_recorded": "2026-09-23",
    }


# --- the real config -----------------------------------------------------


def test_real_config_loads_seeded_series():
    cfg = load_manual_kpis(REAL_CONFIG)
    now = cfg.metrics["NOW"]["subscription_revenue"]
    assert len(now) == 8
    assert now[0].quarter == "2024-09-30"
    assert now[0].value == 2715000000.0
    assert now[-1].quarter == "2026-06-30"
    assert now[-1].value == 3877000000.0
    assert all(p.source for p in now)

    meta = cfg.metrics["META"]["daily_active_people"]
    assert len(meta) == 8
    assert meta[-1].value == 3600000000.0


def test_real_config_search_share_is_empty_not_missing():
    cfg = load_manual_kpis(REAL_CONFIG)
    assert cfg.metrics["GOOGL"]["search_share"] == []


def test_missing_file_is_empty_config_not_error(tmp_path):
    cfg = load_manual_kpis(tmp_path / "does-not-exist.yaml")
    assert cfg.metrics == {}


# --- validation ----------------------------------------------------------


def test_duplicate_quarter_rejected(tmp_path):
    payload = {
        "manual_kpis": {
            "NOW": {"subscription_revenue": [_point("2025-06-30", 1.0), _point("2025-06-30", 2.0)]}
        }
    }
    with pytest.raises(ManualKpiError, match="duplicate quarter"):
        load_manual_kpis(_write(tmp_path, payload))


def test_missing_source_rejected(tmp_path):
    bad = _point("2025-06-30", 1.0)
    del bad["source"]
    payload = {"manual_kpis": {"NOW": {"subscription_revenue": [bad]}}}
    with pytest.raises(ManualKpiError, match="source is required"):
        load_manual_kpis(_write(tmp_path, payload))


def test_bad_quarter_date_rejected(tmp_path):
    bad = _point("2025-13-99", 1.0)
    payload = {"manual_kpis": {"NOW": {"subscription_revenue": [bad]}}}
    with pytest.raises(ManualKpiError, match="not a valid date"):
        load_manual_kpis(_write(tmp_path, payload))


def test_non_numeric_value_rejected(tmp_path):
    bad = _point("2025-06-30", 1.0)
    bad["value"] = "lots"
    payload = {"manual_kpis": {"NOW": {"subscription_revenue": [bad]}}}
    with pytest.raises(ManualKpiError, match="must be a number"):
        load_manual_kpis(_write(tmp_path, payload))


def test_points_sorted_oldest_first(tmp_path):
    payload = {
        "manual_kpis": {
            "NOW": {"subscription_revenue": [_point("2025-06-30", 2.0), _point("2025-03-31", 1.0)]}
        }
    }
    cfg = load_manual_kpis(_write(tmp_path, payload))
    quarters = [p.quarter for p in cfg.metrics["NOW"]["subscription_revenue"]]
    assert quarters == ["2025-03-31", "2025-06-30"]


def test_tickers_uppercased(tmp_path):
    payload = {"manual_kpis": {"now": {"subscription_revenue": [_point("2025-06-30", 1.0)]}}}
    cfg = load_manual_kpis(_write(tmp_path, payload))
    assert "NOW" in cfg.metrics


# --- panels ---------------------------------------------------------------


def test_panels_carry_manual_source_and_citation():
    cfg = load_manual_kpis(REAL_CONFIG)
    panels = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    panel = next(p for p in panels if p["key"] == "subscription_revenue")
    assert panel["key"] == "subscription_revenue"
    assert panel["label"] == "Subscription revenue"
    assert panel["format"] == "currency"
    assert panel["source"] == "manual"
    assert "ServiceNow Q2 2026" in panel["latest_source"]
    assert panel["latest_recorded"] == "2026-09-23"
    assert panel["current"] == 3877000000.0
    assert panel["quarters_reported"] == 8
    assert panel["empty"] is False


def test_panels_yoy_fractional_for_currency():
    cfg = load_manual_kpis(REAL_CONFIG)
    panels = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    panel = next(p for p in panels if p["key"] == "subscription_revenue")
    # Q3 2025 vs Q3 2024: (3299 - 2715) / 2715
    i = panel["quarters"].index("2025-09-30")
    assert panel["yoy"][i] == pytest.approx((3299000000 - 2715000000) / 2715000000)
    assert panel["yoy_unit"] == "pct"


def test_empty_metric_renders_na_panel_not_crash():
    cfg = load_manual_kpis(REAL_CONFIG)
    (panel,) = manual_kpis.manual_kpi_panels(cfg.metrics["GOOGL"])
    assert panel["key"] == "search_share"
    assert panel["label"] == "Search market share"
    assert panel["empty"] is True
    assert panel["current"] is None
    assert panel["quarters"] == []
    assert panel["source"] == "manual"


def test_meta_dap_uses_count_format():
    cfg = load_manual_kpis(REAL_CONFIG)
    (panel,) = manual_kpis.manual_kpi_panels(cfg.metrics["META"])
    assert panel["format"] == "count"
    assert "DAU" not in panel["label"]  # DAP, not legacy Facebook DAU
    assert "DAP" in panel["blurb"]


def test_unknown_key_still_renders_with_generic_label(tmp_path):
    payload = {"manual_kpis": {"NOW": {"mystery_metric": [_point("2025-06-30", 7.0)]}}}
    cfg = load_manual_kpis(_write(tmp_path, payload))
    (panel,) = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    assert panel["label"] == "Mystery Metric"
    assert panel["current"] == 7.0
