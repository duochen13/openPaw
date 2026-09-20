"""Unit tests for manual_kpis.py (issue #36): the kpi_manual.yaml parser,
manual panel builder, and the NOW RPO deceleration flag.

All network-free. The shipped config/kpi_manual.yaml carries only
commented-out examples, so the "empty config" tests below pin the
no-fake-numbers guarantee: nothing renders until Daniel enters real data.
"""

from pathlib import Path
from unittest import mock

import pytest
import yaml

from portfolio_analysis import kpis as kpis_module
from portfolio_analysis import manual_kpis
from portfolio_analysis import render as render_module
from portfolio_analysis.manual_kpis import (
    ManualKpiConfig,
    ManualKpiError,
    ManualPoint,
    load_manual_kpis,
    manual_kpi_panels,
    rpo_deceleration_flag,
)

REPO_ROOT = Path(manual_kpis.__file__).resolve().parents[2]


def _write(path: Path, obj: dict) -> Path:
    path.write_text(yaml.safe_dump(obj))
    return path


def _point(quarter: str, value: float, source: str = "NOW Q2 2026 PR") -> ManualPoint:
    return ManualPoint(
        quarter=quarter, value=value, source=source, date_recorded="2026-09-20"
    )


# --------------------------------------------------------------------------
# Parser: the shipped file


def test_shipped_config_has_no_real_numbers():
    cfg = load_manual_kpis()
    assert cfg.metrics == {}
    assert cfg.rpo_yoy_floor == pytest.approx(0.21)
    assert cfg.rpo_pp_drop == pytest.approx(0.05)


def test_missing_file_is_empty_config(tmp_path):
    cfg = load_manual_kpis(tmp_path / "does-not-exist.yaml")
    assert cfg == ManualKpiConfig()


# --------------------------------------------------------------------------
# Parser: valid input


def test_valid_config_parses_and_sorts(tmp_path):
    p = _write(
        tmp_path / "k.yaml",
        {
            "alerts": {"rpo_deceleration": {"yoy_floor_pct": 20.0, "pp_drop": 4.0}},
            "manual_kpis": {
                "now": {
                    "customers_over_1m_acv": [
                        {
                            "quarter": "2025-06-30",
                            "value": 520,
                            "source": "NOW Q2 2025 PR",
                            "date_recorded": "2026-09-20",
                        },
                        {
                            "quarter": "2025-03-31",
                            "value": 510,
                            "source": "NOW Q1 2025 PR",
                            "date_recorded": "2026-09-20",
                        },
                    ]
                }
            },
        },
    )
    cfg = load_manual_kpis(p)
    assert cfg.rpo_yoy_floor == pytest.approx(0.20)
    assert cfg.rpo_pp_drop == pytest.approx(0.04)
    pts = cfg.metrics["NOW"]["customers_over_1m_acv"]
    assert [pt.quarter for pt in pts] == ["2025-03-31", "2025-06-30"]  # sorted
    assert pts[0].value == 510.0


# --------------------------------------------------------------------------
# Parser: malformed input fails loudly


def _bad_config(tmp_path, mutate):
    obj = {
        "manual_kpis": {
            "NOW": {
                "customers_over_1m_acv": [
                    {
                        "quarter": "2025-06-30",
                        "value": 520,
                        "source": "NOW Q2 2025 PR",
                        "date_recorded": "2026-09-20",
                    }
                ]
            }
        }
    }
    mutate(obj["manual_kpis"]["NOW"]["customers_over_1m_acv"][0])
    return _write(tmp_path / "k.yaml", obj)


def test_bad_quarter_date_raises(tmp_path):
    p = _bad_config(tmp_path, lambda d: d.update(quarter="June 2025"))
    with pytest.raises(ManualKpiError, match="quarter"):
        load_manual_kpis(p)


def test_missing_source_raises(tmp_path):
    p = _bad_config(tmp_path, lambda d: d.pop("source"))
    with pytest.raises(ManualKpiError, match="source"):
        load_manual_kpis(p)


def test_empty_source_raises(tmp_path):
    p = _bad_config(tmp_path, lambda d: d.update(source="   "))
    with pytest.raises(ManualKpiError, match="source"):
        load_manual_kpis(p)


def test_non_numeric_value_raises(tmp_path):
    p = _bad_config(tmp_path, lambda d: d.update(value="lots"))
    with pytest.raises(ManualKpiError, match="value"):
        load_manual_kpis(p)


def test_bool_value_raises(tmp_path):
    p = _bad_config(tmp_path, lambda d: d.update(value=True))
    with pytest.raises(ManualKpiError, match="value"):
        load_manual_kpis(p)


def test_bad_date_recorded_raises(tmp_path):
    p = _bad_config(tmp_path, lambda d: d.update(date_recorded="2025-13-99"))
    with pytest.raises(ManualKpiError, match="date_recorded"):
        load_manual_kpis(p)


def test_duplicate_quarter_raises(tmp_path):
    obj = {
        "manual_kpis": {
            "NOW": {
                "crpo": [
                    {
                        "quarter": "2025-06-30",
                        "value": 1.0,
                        "source": "s",
                        "date_recorded": "2026-09-20",
                    },
                    {
                        "quarter": "2025-06-30",
                        "value": 2.0,
                        "source": "s",
                        "date_recorded": "2026-09-20",
                    },
                ]
            }
        }
    }
    p = _write(tmp_path / "k.yaml", obj)
    with pytest.raises(ManualKpiError, match="duplicate quarter"):
        load_manual_kpis(p)


def test_bad_alert_threshold_raises(tmp_path):
    p = _write(
        tmp_path / "k.yaml",
        {"alerts": {"rpo_deceleration": {"yoy_floor_pct": "high"}}},
    )
    with pytest.raises(ManualKpiError, match="yoy_floor_pct"):
        load_manual_kpis(p)


# --------------------------------------------------------------------------
# Panels


def _quarters(values):
    ends = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    return [_point(q, v) for q, v in zip(ends, values, strict=True)]


def test_manual_panels_carry_manual_source():
    panels = manual_kpi_panels({"customers_over_1m_acv": _quarters([400, 420, 440, 460, 500])})
    assert len(panels) == 1
    p = panels[0]
    assert p["source"] == "manual"
    assert p["label"] == "Customers >$1M ACV"
    assert p["latest_source"] == "NOW Q2 2026 PR"
    assert p["latest_recorded"] == "2026-09-20"
    assert p["current"] == 500.0
    assert p["yoy_unit"] == "pct"
    # YoY vs the year-ago quarter: 500/400 - 1 = 25%.
    assert p["current_yoy"] == pytest.approx(0.25)


def test_percent_metric_yoy_in_percentage_points():
    panels = manual_kpi_panels({"renewal_rate": _quarters([97.0, 97.5, 98.0, 98.0, 99.0])})
    p = panels[0]
    assert p["yoy_unit"] == "pp"
    assert p["current_yoy"] == pytest.approx(2.0)  # 99 - 97


def test_unknown_metric_key_still_renders_generically():
    panels = manual_kpi_panels({"my_custom_thing": _quarters([1, 2, 3, 4, 5])})
    assert panels[0]["label"] == "My Custom Thing"
    assert panels[0]["source"] == "manual"


# --------------------------------------------------------------------------
# RPO deceleration flag


def _rpo(*values: float) -> list[tuple[str, str, float]]:
    ends = [
        "2024-03-31",
        "2024-06-30",
        "2024-09-30",
        "2024-12-31",
        "2025-03-31",
        "2025-06-30",
    ]
    return [(q, "2025-07-01", v) for q, v in zip(ends, values, strict=True)]


def test_flag_fires_below_floor():
    # YoY: 20% then 19% - below the 21% floor, no sharp drop.
    flag = rpo_deceleration_flag(_rpo(20, 21, 22, 23, 24.0, 24.99))
    assert flag["flagged"] is True
    assert "below" in flag["reason"]
    assert "decelerated" not in flag["reason"]


def test_flag_fires_on_pp_drop():
    # YoY: 35% then 25% - above the floor, but a 10pp deceleration.
    flag = rpo_deceleration_flag(_rpo(20, 21, 22, 23, 27.0, 26.25))
    assert flag["flagged"] is True
    assert "decelerated" in flag["reason"]
    assert "below" not in flag["reason"]


def test_flag_fires_on_both():
    flag = rpo_deceleration_flag(_rpo(20, 21, 22, 23, 26.0, 24.99))
    assert flag["flagged"] is True
    assert "below" in flag["reason"] and "decelerated" in flag["reason"]


def test_boundary_values_do_not_fire():
    # Exactly at the floor, and exactly a 5pp drop: strict inequalities.
    series = _rpo(20, 21, 22, 23, 26.0, 25.2)
    dated = kpis_module.with_yoy(series)
    current, prev = dated[-1][2], dated[-2][2]
    assert current is not None and prev is not None
    flag = rpo_deceleration_flag(
        series, yoy_floor=current, pp_drop=prev - current
    )
    assert flag["flagged"] is False


def test_healthy_growth_does_not_fire():
    flag = rpo_deceleration_flag(_rpo(20, 21, 22, 23, 25.0, 26.25))
    assert flag["flagged"] is False
    assert flag["reason"] is None


def test_short_history_is_not_a_flag():
    flag = rpo_deceleration_flag(_rpo(20, 21, 22, 23, 24, 25)[:4])
    assert flag["flagged"] is False
    assert "history" in flag["reason"]


# --------------------------------------------------------------------------
# Render integration: EDGAR + manual merge, alert attached


def test_kpi_data_merges_manual_panels_and_rpo_alert():
    store = mock.Mock()
    rpo = _rpo(20, 21, 22, 23, 24.0, 24.99)  # below-floor growth
    store.kpi_quarters.side_effect = lambda _sym, key: rpo if key == "rpo" else []
    cfg = ManualKpiConfig(
        metrics={"NOW": {"customers_over_1m_acv": _quarters([400, 420, 440, 460, 500])}},
    )
    with mock.patch.object(manual_kpis, "load_manual_kpis", return_value=cfg):
        out = render_module._kpi_data(store, "NOW")
    assert out is not None
    assert any(m.get("source") == "manual" for m in out["metrics"])
    assert any(m.get("source") != "manual" for m in out["metrics"])  # EDGAR rpo panel
    alert = out["rpo_alert"]
    assert alert["flagged"] is True


def test_kpi_data_degrades_when_manual_yaml_broken():
    store = mock.Mock()
    store.kpi_quarters.side_effect = lambda _sym, key: []
    with mock.patch.object(
        manual_kpis, "load_manual_kpis", side_effect=ManualKpiError("boom")
    ):
        assert render_module._kpi_data(store, "NOW") is None
