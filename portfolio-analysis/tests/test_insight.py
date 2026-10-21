"""Unit tests for insight_dashboard.py (issues #34 + #35).

Section A (#34): the SPV/off-BS capex layer regenerates from
data/insight/spv_capex.csv - every estimate row must be anchored to a
named deal with a source. Section B (#35): the credit-stress timeline
regenerates from data/insight/cds_spreads.csv - proxies are never
presented as CDS prints.

All network-free. The seed CSVs carry only verified anchors (issue #35,
2026-09-20); no continuous CDS series exists because that history is
paywalled.
"""

from pathlib import Path

import pytest

from portfolio_analysis.insight_dashboard import (
    InsightDataError,
    insight_dashboard_data,
    load_cds_spreads,
    load_fedwatch_snapshots,
    load_mortgage_rates,
    load_pending_home_sales,
    load_revenue,
    load_spv_capex,
    render_insight_dashboard,
)

DATA_DIR = Path(__file__).resolve().parents[1] / ".." / "data" / "insight"
DATA_DIR = DATA_DIR.resolve()

SPV_HEADER = "year,reported_big4_usd_b,spv_est_usd_b,anchor_deals,chart_label,source,status\n"
CDS_HEADER = "ticker,date,spread_bps,source,proxy_label,note\n"
REV_HEADER = "year,revenue_big4_usd_b,source,status\n"
REV_SEED = (
    "2023,1244.7,SEC EDGAR companyfacts,verified\n"
    "2024,1414.3,SEC EDGAR companyfacts,verified\n"
    "2025,1626.2,SEC EDGAR companyfacts,verified\n"
    "2026,1781.6,SEC EDGAR companyfacts,ttm-partial\n"
)


def _spv_dir(tmp_path: Path, rows: str) -> Path:
    d = tmp_path / "insight"
    d.mkdir()
    (d / "spv_capex.csv").write_text(SPV_HEADER + rows)
    (d / "revenue_big4.csv").write_text(REV_HEADER + REV_SEED)
    (d / "cds_spreads.csv").write_text(
        CDS_HEADER + 'ORCL,2026-09,,Some press,cds-level:reported,A note\n'
    )
    return d


def _cds_dir(tmp_path: Path, rows: str) -> Path:
    d = tmp_path / "insight"
    d.mkdir()
    (d / "spv_capex.csv").write_text(
        SPV_HEADER + '2023,141,0,,,company 10-Ks,verified\n'
    )
    (d / "revenue_big4.csv").write_text(REV_HEADER + REV_SEED)
    (d / "cds_spreads.csv").write_text(CDS_HEADER + rows)
    return d


# --------------------------------------------------------------------------
# Section A: the shipped SPV data


def test_shipped_spv_csv_loads_with_combined_math():
    rows = load_spv_capex(DATA_DIR)
    assert [r.year for r in rows] == ["2023", "2024", "2025", "2026"]
    assert rows[0].spv == 0  # 2023: no SPV layer
    assert rows[-1].combined == pytest.approx(833.0)  # 733 reported + 100 SPV
    for r in rows[1:]:
        assert r.anchor_deals, f"{r.year}: estimate without anchor deals"
        assert r.source, f"{r.year}: estimate without source"


def test_spv_estimate_without_anchor_raises(tmp_path):
    d = _spv_dir(
        tmp_path,
        '2024,220,25,,MSFT SPV,press,estimated\n',
    )
    with pytest.raises(InsightDataError, match="anchor"):
        load_spv_capex(d)


def test_spv_estimate_without_source_raises(tmp_path):
    d = _spv_dir(
        tmp_path,
        '2024,220,25,Some deal,,,'  # empty source
        '\n',
    )
    # status column empty -> also invalid; anchor present so source is the failure
    with pytest.raises(InsightDataError):
        load_spv_capex(d)


def test_spv_bad_status_raises(tmp_path):
    d = _spv_dir(tmp_path, '2024,220,25,Deal,Lbl,press,rumored\n')
    with pytest.raises(InsightDataError, match="status"):
        load_spv_capex(d)


def test_spv_missing_column_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "spv_capex.csv").write_text("year,reported_big4_usd_b\n2023,141\n")
    (d / "cds_spreads.csv").write_text(CDS_HEADER)
    with pytest.raises(InsightDataError, match="missing columns"):
        load_spv_capex(d)


# --------------------------------------------------------------------------
# Section B: the shipped CDS timeline


def test_shipped_cds_csv_is_proxies_only():
    points = load_cds_spreads(DATA_DIR)
    assert len(points) == 4
    # Sorted oldest first.
    assert [p.date for p in points] == ["2025-11", "2026-07", "2026-09", "2026-09"]
    for p in points:
        assert p.ticker == "ORCL"
        assert p.spread_bps is None, "seed data must not invent CDS prints"
        assert p.proxy_label, "every point needs its proxy type"
        assert p.source, "every point needs a source"
    labels = {p.proxy_label for p in points}
    assert "credit-proxy:loan-price" in labels  # Project Jupiter 89-91c
    assert "credit-proxy:rating-action" in labels  # S&P downgrade


def test_proxy_with_spread_raises(tmp_path):
    d = _cds_dir(
        tmp_path,
        'ORCL,2026-09,150,Some press,credit-proxy:loan-price,A proxy with a spread\n',
    )
    with pytest.raises(InsightDataError, match="proxy"):
        load_cds_spreads(d)


def test_cds_print_without_spread_raises(tmp_path):
    d = _cds_dir(
        tmp_path, 'ORCL,2026-09,,Some dealer,cds-print:5y,Missing the print\n'
    )
    with pytest.raises(InsightDataError, match="spread_bps"):
        load_cds_spreads(d)


def test_real_cds_print_loads(tmp_path):
    d = _cds_dir(
        tmp_path, 'ORCL,2026-09-18,150,Dealer poll,cds-print:5y,Weekly poll\n'
    )
    (points,) = load_cds_spreads(d)
    assert points.spread_bps == 150.0


def test_cds_bad_date_raises(tmp_path):
    d = _cds_dir(tmp_path, 'ORCL,Sep 2026,,Some press,cds-level:reported,X\n')
    with pytest.raises(InsightDataError, match="date"):
        load_cds_spreads(d)


# --------------------------------------------------------------------------
# Dashboard data + render smoke tests


def test_dashboard_data_shape():
    data = insight_dashboard_data(DATA_DIR)
    assert len(data["spv"]) == 4
    assert len(data["cds"]) == 4
    assert data["cds_prints"] == {}  # no real prints in the seed
    assert data["asof"] == "2026-09"


def test_render_writes_insight_html(tmp_path):
    data = insight_dashboard_data(DATA_DIR)
    target = render_insight_dashboard(data, tmp_path / "out")
    assert target.name == "insight.html"
    page = target.read_text()
    assert "Reported vs true AI capex" in page
    assert "Hyperscaler credit stress" in page
    assert "$733B" in page  # reported 2026 value label
    assert "+$100B" in page  # SPV gap label
    assert "Project Jupiter" in page
    assert "cds-print:5y" in page  # schema documented for future prints
    assert "<svg" in page
    # No real CDS line chart while the seed has no prints.
    assert "5Y CDS spreads (" not in page


def test_render_with_real_prints_draws_spread_chart(tmp_path):
    d = _cds_dir(
        tmp_path,
        "ORCL,2026-09-11,140,Dealer poll,cds-print:5y,Week 1\n"
        "ORCL,2026-09-18,150,Dealer poll,cds-print:5y,Week 2\n",
    )
    data = insight_dashboard_data(d)
    assert data["cds_prints"] == {"ORCL": [("2026-09-11", 140.0), ("2026-09-18", 150.0)]}
    target = render_insight_dashboard(data, tmp_path / "out")
    page = target.read_text()
    assert "5Y CDS spreads (bps)" in page


# --------------------------------------------------------------------------
# Section A, revenue layer: capex intensity (% of revenue)


def test_shipped_revenue_csv_loads_edgar_values():
    rows = load_revenue(DATA_DIR)
    assert [(r.year, r.revenue, r.status) for r in rows] == [
        ("2023", 1244.7, "verified"),
        ("2024", 1414.3, "verified"),
        ("2025", 1626.2, "verified"),
        ("2026", 1781.6, "ttm-partial"),
    ]


def test_revenue_nonpositive_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "revenue_big4.csv").write_text(REV_HEADER + "2023,0,EDGAR,verified\n")
    with pytest.raises(InsightDataError, match="must be positive"):
        load_revenue(d)
    (d / "revenue_big4.csv").write_text(REV_HEADER + "2023,-5,EDGAR,verified\n")
    with pytest.raises(InsightDataError, match="negative amount"):
        load_revenue(d)


def test_revenue_bad_status_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "revenue_big4.csv").write_text(REV_HEADER + "2023,1244.7,EDGAR,whatever\n")
    with pytest.raises(InsightDataError, match="not in"):
        load_revenue(d)


def test_revenue_missing_column_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "revenue_big4.csv").write_text("year,revenue_big4_usd_b\n2023,1244.7\n")
    with pytest.raises(InsightDataError, match="missing columns"):
        load_revenue(d)


def test_intensity_math_uses_reported_and_true():
    data = insight_dashboard_data(DATA_DIR)
    by_year = {r["year"]: r for r in data["spv"]}
    r25 = by_year["2025"]
    assert r25["intensity_reported"] == pytest.approx(100 * 375 / 1626.2)
    assert r25["intensity_true"] == pytest.approx(100 * 435 / 1626.2)
    assert r25["intensity_true"] > r25["intensity_reported"]


def test_missing_revenue_year_raises(tmp_path):
    d = _spv_dir(
        tmp_path,
        "2023,141,0,,,company 10-Ks,verified\n"
        "2027,999,0,,,company 10-Ks,verified\n",
    )
    with pytest.raises(InsightDataError, match="no revenue row"):
        insight_dashboard_data(d)


def test_render_includes_intensity_panel(tmp_path):
    data = insight_dashboard_data(DATA_DIR)
    target = render_insight_dashboard(data, tmp_path / "out")
    page = target.read_text()
    assert "Capex intensity: share of revenue" in page
    assert "Capex as percent of revenue" in page  # svg aria-label
    assert "ttm-partial" not in page  # status stays in data, chart shows the "*" label
    assert "2026E*" in page  # guidance capex on TTM revenue, labeled


# --------------------------------------------------------------------------
# Section C (#171): macro early-warning figures


PHS_HEADER = "month,level,source,release_date\n"
MTG_HEADER = "month,avg_rate,source\n"
FW_HEADER = "as_of,meeting,p_cut,p_hold,p_hike,source\n"


def test_shipped_housing_csv_matches_nar_anchors():
    rows = load_pending_home_sales(DATA_DIR)
    # Coverage starts Dec 2021 (Jan-Nov 2021 monthly values not fetchable
    # from a primary table - see the PR), ends at the latest NAR release.
    assert rows[0].month == "2021-12"
    assert rows[-1].month == "2026-09"
    by_month = {r.month: r.level for r in rows}
    # Anchors from NAR's Sep 2026 release (2026-10-20): Sep 2026 = 66.0,
    # -7.3% MoM off Aug 2026 = 71.2, -11.3% YoY off Sep 2025 = 74.4.
    assert by_month["2026-09"] == 66.0
    assert by_month["2026-08"] == 71.2
    assert by_month["2025-09"] == 74.4
    for r in rows:
        assert r.source, f"{r.month}: level without source"
        assert len(r.release_date) == 10, f"{r.month}: release_date must be a full date"


def test_shipped_housing_mom_yoy_reproduce_release():
    data = insight_dashboard_data(DATA_DIR)
    last = data["housing"][-1]
    assert last["month"] == "2026-09"
    assert last["mom_pct"] == pytest.approx(-7.3, abs=0.05)
    assert last["yoy_pct"] == pytest.approx(-11.3, abs=0.05)
    assert data["housing"][0]["mom_pct"] is None  # no Nov 2021 level chained


def test_housing_missing_source_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "pending_home_sales.csv").write_text(
        PHS_HEADER + "2026-09,66.0,,2026-10-20\n"
    )
    with pytest.raises(InsightDataError, match="source"):
        load_pending_home_sales(d)


def test_housing_bad_month_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "pending_home_sales.csv").write_text(
        PHS_HEADER + "2026-13,66.0,NAR release,2026-10-20\n"
    )
    with pytest.raises(InsightDataError, match="month"):
        load_pending_home_sales(d)


def test_shipped_mortgage_csv_is_fred_monthly_averages():
    rows = load_mortgage_rates(DATA_DIR)
    assert rows[0].month == "2021-01"
    assert rows[-1].month == "2026-10"
    for r in rows:
        assert r.source == "FRED MORTGAGE30US weekly, monthly average"
    # Oct 2026 averages the three published weekly prints 7.28/7.40/7.40.
    assert rows[-1].avg_rate == pytest.approx(7.36)


def test_mortgage_missing_source_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "mortgage_rates.csv").write_text(MTG_HEADER + "2026-10,7.36,\n")
    with pytest.raises(InsightDataError, match="source"):
        load_mortgage_rates(d)


def test_shipped_fedwatch_seed_rows():
    rows = load_fedwatch_snapshots(DATA_DIR)
    assert len(rows) == 5
    assert {r.meeting for r in rows} == {"2026-10-28", "2026-12-09"}
    for r in rows:
        assert r.p_cut + r.p_hold + r.p_hike == pytest.approx(100.0)
        assert r.source
    oct28 = [r for r in rows if r.meeting == "2026-10-28"]
    assert [r.p_hike for r in oct28] == [17.7, 18.0, 49.3, 16.1]


def test_fedwatch_bad_probability_sum_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "fedwatch_snapshots.csv").write_text(
        FW_HEADER + "2026-10-20,2026-10-28,0,60.0,20.0,CME FedWatch\n"
    )
    with pytest.raises(InsightDataError, match="sum"):
        load_fedwatch_snapshots(d)


def test_fedwatch_missing_source_raises(tmp_path):
    d = tmp_path / "insight"
    d.mkdir()
    (d / "fedwatch_snapshots.csv").write_text(
        FW_HEADER + "2026-10-20,2026-10-28,0,84.0,16.0,\n"
    )
    with pytest.raises(InsightDataError, match="required"):
        load_fedwatch_snapshots(d)


def test_render_includes_section_c(tmp_path):
    data = insight_dashboard_data(DATA_DIR)
    target = render_insight_dashboard(data, tmp_path / "out")
    page = target.read_text()
    assert "Section C" in page
    assert "Macro early-warning" in page
    assert "Pending home sales index" in page  # housing svg aria-label
    assert ">2021</text>" in page  # housing chart's first tick is 2021
    assert "Sep 2026: 66.0" in page  # latest print annotated
    assert "pre-2026 low" in page
    assert "30-year mortgage rate, monthly average" in page
    assert "FedWatch hike probabilities by FOMC meeting" in page
    assert "FOMC Oct 28: hike 16%" in page
    assert "FOMC Dec 9: hike 92%" in page


def test_dashboard_data_without_section_c_files_still_renders(tmp_path):
    # Section C is additive: a data dir without the new CSVs renders A/B.
    d = _cds_dir(tmp_path, 'ORCL,2026-09,,Some press,cds-level:reported,A note\n')
    data = insight_dashboard_data(d)
    assert data["housing"] == []
    assert data["mortgage"] == []
    assert data["fedwatch"] == []
    target = render_insight_dashboard(data, tmp_path / "out")
    page = target.read_text()
    assert "Section C" in page  # block renders with unavailable notes
    assert "data unavailable" in page
