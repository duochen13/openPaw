"""Issue #67: COGS / cRPO / non-GAAP margins and KPI group sorting.

Network-free: companyfacts fixtures are hand-built. Covers the new
``cogs`` EDGAR metric (us-gaap:CostOfRevenue), the new manual metric
keys (COGS split, cRPO, non-GAAP margins), and the render-time group
sort (revenue & demand before cost control).
"""

from pathlib import Path

import pytest

from portfolio_analysis import kpis, manual_kpis
from portfolio_analysis.render import order_panels_by_group


def _u(start, end, val, fy, fp, form, filed):
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": "0000000000-00-000000",
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


def _facts(tag, units, taxonomy="us-gaap", unit="USD"):
    return {"facts": {taxonomy: {tag: {"units": {unit: units}}}}}


COGS_UNITS = [
    # Standalone quarterly durations, as filers tag CostOfRevenue
    # (frame CY202xQn in the real feed).
    _u("2025-01-01", "2025-03-31", 940_000_000.0, 2025, "Q1", "10-Q", "2025-04-24"),
    _u("2025-04-01", "2025-06-30", 1_013_000_000.0, 2025, "Q2", "10-Q", "2025-07-24"),
    _u("2025-07-01", "2025-09-30", 1_040_000_000.0, 2025, "Q3", "10-Q", "2025-10-24"),
    _u("2025-01-01", "2025-12-31", 3_993_000_000.0, 2025, "FY", "10-K", "2026-02-13"),
    _u("2026-01-01", "2026-03-31", 940_000_000.0, 2026, "Q1", "10-Q", "2026-04-23"),
    _u("2026-04-01", "2026-06-30", 1_169_000_000.0, 2026, "Q2", "10-Q", "2026-07-23"),
]


def test_cogs_metric_defined_from_cost_of_revenue():
    assert "cogs" in kpis.METRIC_DEFS
    spec = kpis.METRIC_DEFS["cogs"]
    assert spec["group"] == "cost"
    assert ("us-gaap", "CostOfRevenue", "USD") in spec["sources"]


def test_cogs_parses_quarterly_like_revenue():
    facts = _facts("CostOfRevenue", COGS_UNITS)
    series = kpis.build_kpi_series(facts, ["cogs"])
    assert "cogs" in series
    by_q = {q: v for q, _, v in series["cogs"]}
    assert by_q["2026-06-30"] == pytest.approx(1_169_000_000.0)
    assert by_q["2026-03-31"] == pytest.approx(940_000_000.0)
    # Q4'25 derived as FY minus Q1-Q3.
    q4 = 3_993_000_000.0 - 940_000_000.0 - 1_013_000_000.0 - 1_040_000_000.0
    assert by_q["2025-12-31"] == pytest.approx(q4)


def test_cogs_missing_tag_is_omitted_not_empty():
    series = kpis.build_kpi_series({"facts": {}}, ["cogs"])
    assert "cogs" not in series


def test_all_metric_defs_carry_a_known_group():
    for key, spec in kpis.METRIC_DEFS.items():
        assert spec.get("group") in ("revenue", "cost"), key


def test_kpi_panels_carry_group():
    facts = _facts("CostOfRevenue", COGS_UNITS)
    series = kpis.build_kpi_series(facts, ["cogs"])
    panels = kpis.kpi_panels(series, ["cogs"])
    assert panels["metrics"][0]["group"] == "cost"


def test_repo_config_now_lists_cogs():
    cfg = kpis.load_kpi_config()
    assert "cogs" in cfg["NOW"]


def test_manual_issue67_keys_registered():
    expected = {
        "cogs_subscription": ("currency", "cost"),
        "cogs_ps": ("currency", "cost"),
        "crpo": ("currency", "revenue"),
        "nongaap_subscription_gross_margin": ("percent", "cost"),
        "nongaap_gross_margin": ("percent", "cost"),
        "nongaap_operating_margin": ("percent", "cost"),
    }
    for key, (fmt, group) in expected.items():
        spec = manual_kpis.KNOWN_MANUAL_METRICS[key]
        assert spec["format"] == fmt, key
        assert spec["group"] == group, key


def test_manual_panels_pass_group_through(tmp_path: Path):
    cfg_file = tmp_path / "kpi_manual.yaml"
    cfg_file.write_text(
        "manual_kpis:\n"
        "  NOW:\n"
        "    nongaap_gross_margin:\n"
        "      - quarter: '2026-03-31'\n"
        "        value: 0.775\n"
        "        source: 'ServiceNow Q1 2026 earnings release'\n"
        "        date_recorded: '2026-09-25'\n"
        "      - quarter: '2026-06-30'\n"
        "        value: 0.78\n"
        "        source: 'ServiceNow Q2 2026 earnings release'\n"
        "        date_recorded: '2026-09-25'\n"
    )
    cfg = manual_kpis.load_manual_kpis(cfg_file)
    panels = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    assert len(panels) == 1
    p = panels[0]
    assert p["group"] == "cost"
    assert p["format"] == "percent"
    assert p["yoy_unit"] == "pp"
    assert p["current"] == pytest.approx(0.78)


def test_manual_unknown_key_defaults_to_other_group(tmp_path: Path):
    cfg_file = tmp_path / "kpi_manual.yaml"
    cfg_file.write_text(
        "manual_kpis:\n  NOW:\n    mystery_metric:\n"
        "      - quarter: '2026-06-30'\n        value: 1\n"
        "        source: 'x'\n        date_recorded: '2026-09-25'\n"
    )
    cfg = manual_kpis.load_manual_kpis(cfg_file)
    panels = manual_kpis.manual_kpi_panels(cfg.metrics["NOW"])
    assert panels[0]["group"] == "other"


def _panel(key, group):
    return {"key": key, "group": group}


def test_order_panels_by_group_revenue_then_cost():
    panels = [
        _panel("capex", "cost"),
        _panel("crpo", "revenue"),
        _panel("cogs", "cost"),
        _panel("revenue", "revenue"),
    ]
    ordered = order_panels_by_group(panels)
    assert [p["key"] for p in ordered] == ["crpo", "revenue", "capex", "cogs"]


def test_order_panels_by_group_is_stable_and_defaults_other():
    panels = [_panel("b", "cost"), _panel("a", None), _panel("c", "cost")]
    ordered = order_panels_by_group(panels)
    # cost group keeps config order; ungrouped sinks to the end.
    assert [p["key"] for p in ordered] == ["b", "c", "a"]
