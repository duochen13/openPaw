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
