"""COGS vs revenue growth spread metric (follow-up to issue #67).

Network-free: companyfacts fixtures are hand-built. Covers the new
``cogs_revenue_spread`` EDGAR metric (YoY(CostOfRevenue) minus
YoY(revenue), in percentage points): registry shape, the computed spread
on synthetic data, quarter-dropping when either side lacks a year-ago,
and the panel contract (no YoY sparkline, pp formatting).
"""

import pytest

from portfolio_analysis import kpis


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


def _facts(**tags):
    return {"facts": {"us-gaap": {t: {"units": {"USD": u}} for t, u in tags.items()}}}


QUARTERS = [
    ("2025-01-01", "2025-03-31", 2025, "Q1", "10-Q", "2025-04-24"),
    ("2025-04-01", "2025-06-30", 2025, "Q2", "10-Q", "2025-07-24"),
    ("2025-07-01", "2025-09-30", 2025, "Q3", "10-Q", "2025-10-24"),
    ("2025-10-01", "2025-12-31", 2025, "Q4", "10-Q", "2026-01-24"),
    ("2026-01-01", "2026-03-31", 2026, "Q1", "10-Q", "2026-04-23"),
    ("2026-04-01", "2026-06-30", 2026, "Q2", "10-Q", "2026-07-23"),
]

# YoY growth: revenue +20% / +20%, COGS +40% / +50% ->
# spread +20pp in Q1'26, +30pp in Q2'26.
REVENUE_VALS = [1000.0, 1100.0, 1200.0, 1300.0, 1200.0, 1320.0]
COGS_VALS = [300.0, 330.0, 360.0, 390.0, 420.0, 495.0]


def _units(pairs):
    return [_u(s, e, v, fy, fp, form, filed) for (s, e, fy, fp, form, filed), v in pairs]


def _two_tag_facts():
    return _facts(
        CostOfRevenue=_units(zip(QUARTERS, COGS_VALS, strict=True)),
        RevenueFromContractWithCustomerExcludingAssessedTax=_units(
            zip(QUARTERS, REVENUE_VALS, strict=True)
        ),
    )


def test_spread_metric_defined():
    spec = kpis.METRIC_DEFS["cogs_revenue_spread"]
    assert spec["kind"] == "spread"
    assert spec["group"] == "cost"
    assert spec["format"] == "pp"
    assert spec["components"] == ("cogs", "revenue")


def test_spread_computes_known_value():
    series = kpis.build_kpi_series(_two_tag_facts(), ["cogs_revenue_spread"])
    spread = series["cogs_revenue_spread"]
    assert [q for q, _, _ in spread] == ["2026-03-31", "2026-06-30"]
    assert spread[0][2] == pytest.approx(0.20)
    assert spread[1][2] == pytest.approx(0.30)


def test_spread_drops_quarter_missing_year_ago_on_either_side():
    # Revenue lacks Q1'25, so Q1'26 has no revenue year-ago: only Q2'26 survives.
    facts = _facts(
        CostOfRevenue=_units(zip(QUARTERS, COGS_VALS, strict=True)),
        RevenueFromContractWithCustomerExcludingAssessedTax=_units(
            zip(QUARTERS[1:], REVENUE_VALS[1:], strict=True)
        ),
    )
    series = kpis.build_kpi_series(facts, ["cogs_revenue_spread"])
    spread = series["cogs_revenue_spread"]
    assert [q for q, _, _ in spread] == ["2026-06-30"]
    assert spread[0][2] == pytest.approx(0.30)


def test_spread_omitted_when_a_component_has_no_data():
    facts = _facts(CostOfRevenue=_units(zip(QUARTERS, COGS_VALS, strict=True)))
    assert kpis.build_kpi_series(facts, ["cogs_revenue_spread"]) == {}


def test_spread_from_stored_series_shape():
    # render.py derives spreads at render time from stored
    # (quarter, filed, value) rows - same shape, same math.
    num = [
        (q, f, v)
        for (q, f, v) in zip(
            [q[1] for q in QUARTERS],
            ["2025-04-24", "2025-07-24", "2025-10-24", "2026-01-24", "2026-04-23", "2026-07-23"],
            COGS_VALS,
            strict=True,
        )
    ]
    den = [
        (q, f, v)
        for (q, f, v) in zip(
            [q[1] for q in QUARTERS],
            ["2025-04-24", "2025-07-24", "2025-10-24", "2026-01-24", "2026-04-23", "2026-07-23"],
            REVENUE_VALS,
            strict=True,
        )
    ]
    spread = kpis.spread_from_series(num, den)
    assert [q for q, _, _ in spread] == ["2026-03-31", "2026-06-30"]
    assert spread[0][2] == pytest.approx(0.20)
    assert spread[1][2] == pytest.approx(0.30)


def test_spread_panel_has_no_yoy_line_and_pp_format():
    series = kpis.build_kpi_series(_two_tag_facts(), ["cogs_revenue_spread"])
    panels = kpis.kpi_panels(series, ["cogs_revenue_spread"])
    (panel,) = panels["metrics"]
    assert panel["format"] == "pp"
    assert panel["yoy_unit"] == "pp"
    assert panel["yoy"] == [None, None]
    assert panel["current_yoy"] is None
    assert panel["current"] == pytest.approx(0.30)
    assert panel["as_of"] == "2026-06-30"
    assert panel["group"] == "cost"
