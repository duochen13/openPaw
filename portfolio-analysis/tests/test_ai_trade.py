"""Unit tests for ai_trade_dashboard.py (issue #163).

The 8-panel AI trade dashboard renders from dated snapshots vendored
into data/ai_trade/ (Panel 8 reads the Insight page's shared cloud
CSV - see the cloud section below). Discipline, mirroring the Insight
page (PR #38):

- CDS rows are dated press-reported prints with a source on every row;
  the file format has no room for an estimate or a projection, and no
  projection is ever computed for Panel 7.
- Stated expectations exist only as kind=expectation snapshot rows on
  Panel 6 (the two lab run-rate series); anywhere else is a data error.
- Every plotted series carries a source note with an as-of date.

All network-free. The seed data is the watcher's 2026-10-16 snapshot.
"""

from pathlib import Path

import pytest

from portfolio_analysis.ai_trade_dashboard import (
    MONTHLY_COLUMNS,
    TradeDataError,
    _capex_proj,
    _trend_proj,
    ai_trade_data,
    load_cds,
    load_cloud_panel,
    load_monthly,
    load_series_notes,
    load_snapshots,
    render_ai_trade_dashboard,
)

DATA_DIR = (Path(__file__).resolve().parents[1] / ".." / "data" / "ai_trade").resolve()

MONTHLY_HEADER = "date," + ",".join(MONTHLY_COLUMNS) + "\n"
SNAP_HEADER = "panel,series,date,value,unit,kind,source,note\n"
CDS_HEADER = "ticker,date,spread_bps,source,note\n"
NOTES_HEADER = "series,panel,source,as_of,note\n"


def _monthly_seed(rows: int = 4) -> str:
    out = [MONTHLY_HEADER]
    for i in range(1, rows + 1):
        vals = ",".join(str(float(i)) for _ in MONTHLY_COLUMNS)
        out.append(f"2022-0{i}-28,{vals}\n" if i < 10 else f"2022-{i}-28,{vals}\n")
    return "".join(out)


def _notes_seed() -> str:
    rows = "".join(f"{c},1,Test source,2026-10-16,\n" for c in MONTHLY_COLUMNS)
    return NOTES_HEADER + rows + "anthropic_arr,6,Test source,2026-10-16,\n"


def _full_dir(tmp_path: Path, **overrides: str) -> Path:
    d = tmp_path / "ai_trade"
    d.mkdir()
    files = {
        "monthly.csv": _monthly_seed(),
        "snapshots.csv": SNAP_HEADER
        + "6,anthropic_arr,2026-09-30,100,$B,reported,Test source,\n"
        + "6,anthropic_arr,2026-12-31,110,$B,expectation,Test source,Stated expectation\n",
        "cds_snapshots.csv": CDS_HEADER + "ORCL,2026-10-15,288,Reuters,Record\n",
        "series_notes.csv": _notes_seed(),
    }
    files.update(overrides)
    for name, text in files.items():
        (d / name).write_text(text)
    return d


# --------------------------------------------------------------------------
# Monthly series: the shipped snapshot


def test_shipped_monthly_loads_full_range():
    rows = load_monthly(DATA_DIR)
    assert len(rows) == 58
    assert rows[0]["date"] == "2022-01-31"
    assert rows[-1]["date"] == "2026-10-31"
    # Oct-2026 inflation was not yet printed at snapshot time.
    assert rows[-1]["cpi_yoy"] is None and rows[-1]["ppi_yoy"] is None
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-09-30"]["cpi_yoy"] == pytest.approx(3.7)
    assert by_date["2025-03-31"]["crwv"] == pytest.approx(37.08)  # first CRWV close
    assert by_date["2022-01-31"]["crwv"] is None  # CRWV listed Mar-2025


def test_shipped_capex_is_quarterly_and_current():
    rows = load_monthly(DATA_DIR)
    capex = [(r["date"], r["capex_q"]) for r in rows if r["capex_q"] is not None]
    assert len(capex) == 18  # 2022-Q1 .. 2026-Q2
    assert capex[-1] == ("2026-06-30", pytest.approx(110.842))


def test_monthly_missing_column_raises(tmp_path):
    (tmp_path / "monthly.csv").write_text("date,cpi_yoy\n2022-01-31,7.5\n")
    with pytest.raises(TradeDataError, match="missing columns"):
        load_monthly(tmp_path)


def test_monthly_non_increasing_dates_raise(tmp_path):
    (tmp_path / "monthly.csv").write_text(
        _monthly_seed(2) + "2022-01-15," + ",".join("1" for _ in MONTHLY_COLUMNS) + "\n"
    )
    with pytest.raises(TradeDataError, match="strictly increasing"):
        load_monthly(tmp_path)


# --------------------------------------------------------------------------
# Snapshots: per-point sources, expectations fenced to Panel 6


def test_shipped_snapshots_all_sourced():
    points = load_snapshots(DATA_DIR)
    assert points, "seed snapshots must not be empty"
    for p in points:
        assert p.source, f"{p.series} {p.date}: point without a source"
        assert p.unit, f"{p.series} {p.date}: point without a unit"
    by_series = {}
    for p in points:
        by_series.setdefault(p.series, []).append(p)
    assert by_series["anthropic_arr"][-2].date == "2026-09-30"  # last reported
    assert by_series["anthropic_arr"][-2].value == 100.0
    assert by_series["crwv_debt_cost"][0].value == 9.75


def test_shipped_expectations_are_only_panel6_lab_series():
    points = load_snapshots(DATA_DIR)
    expectations = [p for p in points if p.kind == "expectation"]
    assert {(p.series, p.date, p.value) for p in expectations} == {
        ("anthropic_arr", "2026-12-31", 110.0),
        ("openai_runrate", "2026-12-31", 70.0),
    }
    assert all(p.panel == 6 for p in expectations)


def test_expectation_outside_panel6_raises(tmp_path):
    (tmp_path / "snapshots.csv").write_text(
        SNAP_HEADER + "5,crwv_debt_cost,2027-03-31,20,%,expectation,Press,Nope\n"
    )
    with pytest.raises(TradeDataError, match="expectation"):
        load_snapshots(tmp_path)


def test_expectation_for_monthly_series_raises(tmp_path):
    (tmp_path / "snapshots.csv").write_text(
        SNAP_HEADER + "6,cpi_yoy,2026-12-31,4,%,expectation,BLS,Nope\n"
    )
    with pytest.raises(TradeDataError, match="expectation"):
        load_snapshots(tmp_path)


def test_snapshot_without_source_raises(tmp_path):
    (tmp_path / "snapshots.csv").write_text(
        SNAP_HEADER + "6,h100_spot,2026-09-30,2.65,$/GPU-hr,reported,,\n"
    )
    with pytest.raises(TradeDataError, match="source"):
        load_snapshots(tmp_path)


def test_derived_distress_points_are_labeled():
    points = load_snapshots(DATA_DIR)
    derived = {(p.series, p.date) for p in points if p.kind == "derived"}
    # The two Dec-22 / YoY-derived JPMorgan points must never pass as prints.
    assert derived == {
        ("distressed_le80", "2022-12-31"),
        ("distressed_le80", "2025-10-31"),
    }


# --------------------------------------------------------------------------
# CDS: dated press prints only, exactly the documented set


def test_shipped_cds_is_exactly_the_documented_prints():
    prints = load_cds(DATA_DIR)
    got = {(p.ticker, p.date): p.spread_bps for p in prints}
    assert got == {
        ("ORCL", "2026-09-24"): 227.0,
        ("ORCL", "2026-10-08"): 260.0,
        ("ORCL", "2026-10-14"): 262.0,
        ("ORCL", "2026-10-15"): 288.0,
        ("CRWV", "2026-07-31"): 800.0,
        ("CRWV", "2026-10-14"): 1117.0,
        ("META", "2026-09-29"): 100.0,
        ("META", "2026-10-15"): 104.0,
        ("NVDA", "2026-10-10"): 84.0,
        ("NVDA", "2026-10-15"): 90.0,
    }
    for p in prints:
        assert p.source, f"{p.ticker} {p.date}: print without a press source"


def test_cds_without_source_raises(tmp_path):
    (tmp_path / "cds_snapshots.csv").write_text(
        CDS_HEADER + "ORCL,2026-10-15,288,,Record\n"
    )
    with pytest.raises(TradeDataError, match="press source"):
        load_cds(tmp_path)


def test_cds_bad_date_raises(tmp_path):
    (tmp_path / "cds_snapshots.csv").write_text(
        CDS_HEADER + "ORCL,Oct 2026,288,Reuters,Record\n"
    )
    with pytest.raises(TradeDataError, match="YYYY-MM-DD"):
        load_cds(tmp_path)


def test_cds_nonpositive_spread_raises(tmp_path):
    (tmp_path / "cds_snapshots.csv").write_text(
        CDS_HEADER + "ORCL,2026-10-15,0,Reuters,Zero\n"
    )
    with pytest.raises(TradeDataError, match="positive"):
        load_cds(tmp_path)


# --------------------------------------------------------------------------
# Series notes + assembly


def test_shipped_notes_cover_every_plotted_series():
    notes = load_series_notes(DATA_DIR)
    points = load_snapshots(DATA_DIR)
    for col in MONTHLY_COLUMNS:
        assert col in notes, f"monthly series {col} without a source note"
        assert notes[col].as_of == "2026-10-16"
    for p in points:
        assert p.series in notes, f"snapshot series {p.series} without a source note"


def test_missing_series_note_raises(tmp_path):
    notes = _notes_seed().replace("nvda,1,Test source,2026-10-16,\n", "")
    d = _full_dir(tmp_path, **{"series_notes.csv": notes})
    with pytest.raises(TradeDataError, match="no source note"):
        ai_trade_data(d)


def test_data_shape_eight_panels_no_cds_projection():
    data = ai_trade_data(DATA_DIR)
    assert len(data["panels"]) == 8  # 7 vendored + Panel 8 (shared cloud CSV)
    cds_panel = data["panels"][6]
    assert "no projection" in cds_panel["title"]
    for s in cds_panel["series"]:
        assert s["proj"] is None, "Panel 7 must never carry a projection segment"
    assert cds_panel["hline"]["value"] == 250.0  # ORCL watch line
    assert data["asof"] == "2026-10-16"
    assert len(data["cds"]) == 10
    assert len(data["notes"]) == 17  # 14 vendored + 3 Panel 8 cloud series


def test_panel6_expectation_segments_anchor_on_last_reported():
    data = ai_trade_data(DATA_DIR)
    panel6 = data["panels"][5]
    by_label = {s["label"]: s for s in panel6["series"]}
    arr = by_label["Anthropic ARR run-rate, $B (reported points)"]
    assert arr["proj"] == [("2026-09-30", 100.0), ("2026-12-31", 110.0)]
    oai = by_label["OpenAI revenue run-rate, $B (reported points, net basis)"]
    assert oai["proj"] == [("2026-09-30", 50.0), ("2026-12-31", 70.0)]


# --------------------------------------------------------------------------
# Panel 8: hyperscaler cloud, from the Insight page's shared CSV (#174)


CLOUD_HEADER = "vendor,segment,quarter,revenue_usd_b,source,status\n"


def _cloud_sibling(tmp_path: Path, rows: str) -> Path:
    """The sibling data/insight/ dir Panel 8 reads its CSV from."""
    d = tmp_path / "insight"
    d.mkdir(exist_ok=True)
    (d / "cloud_revenue.csv").write_text(CLOUD_HEADER + rows)
    return d


def test_shipped_cloud_panel_series_and_anchors():
    data = ai_trade_data(DATA_DIR)
    panel = data["panels"][7]
    assert panel["kind"] == "cloud"
    rev, growth = panel["charts"]
    by_label = {s["label"]: s for s in rev["series"]}
    googl = by_label["Google Cloud segment revenue, $B (company earnings releases)"]
    assert len(googl["points"]) == 26  # 2020-Q1 .. 2026-Q2
    assert googl["points"][0] == ("2020-01-01", pytest.approx(2.777))
    assert googl["points"][-1] == ("2026-04-01", pytest.approx(24.768))
    assert googl["end_label"] == "$24.8B"
    g = {s["label"]: s for s in growth["series"]}
    gg = g["Google Cloud revenue y/y % (computed from the chained quarterly revenue)"]
    assert len(gg["points"]) == 22  # 2021-Q1 .. 2026-Q2 (2020 = base year)
    assert gg["points"][0][0] == "2021-01-01"
    assert gg["points"][0][1] == pytest.approx(45.7, abs=0.15)
    assert gg["points"][-1][1] == pytest.approx(81.8, abs=0.15)
    aws = g["Amazon Web Services revenue y/y % (computed from the chained quarterly revenue)"]
    assert aws["points"][0][1] == pytest.approx(32.1, abs=0.15)
    msft = g["Intelligent Cloud revenue y/y % (computed from the chained quarterly revenue)"]
    assert msft["points"][0][1] == pytest.approx(23.0, abs=0.15)
    assert msft["points"][-1][1] == pytest.approx(31.6, abs=0.1)
    for chart in panel["charts"]:
        for s in chart["series"]:
            assert s["proj"] is None, "Panel 8 must never carry a projection segment"


def test_shipped_cloud_table_rows_and_stars():
    table = ai_trade_data(DATA_DIR)["panels"][7]["table"]
    assert table["columns"] == [
        "Google Cloud",
        "Amazon Web Services",
        "Intelligent Cloud",
    ]
    rows = table["rows"]
    assert len(rows) == 22  # every quarter 2021-Q1 .. 2026-Q2
    assert rows[0]["quarter"] == "2021-Q1" and rows[-1]["quarter"] == "2026-Q2"
    assert [c[0] for c in rows[0]["cells"]] == pytest.approx(
        [45.7, 32.1, 23.0], abs=0.15
    )
    # Exactly the four Microsoft cells chained across the FY2025 segment
    # redefinition are asterisked.
    starred = {
        (r["quarter"], i) for r in rows for i, c in enumerate(r["cells"]) if c[1]
    }
    assert starred == {
        ("2024-Q3", 2),
        ("2024-Q4", 2),
        ("2025-Q1", 2),
        ("2025-Q2", 2),
    }


def test_cloud_panel_absent_without_insight_csv(tmp_path):
    d = _full_dir(tmp_path)  # no sibling data/insight/ -> seven panels
    assert load_cloud_panel(d) == []
    data = ai_trade_data(d)
    assert len(data["panels"]) == 7
    assert all(p.get("kind") != "cloud" for p in data["panels"])


def test_cloud_panel_missing_note_raises(tmp_path):
    _cloud_sibling(
        tmp_path,
        "GOOGL,Google Cloud,2020-Q1,2.777,Release,verified\n"
        "GOOGL,Google Cloud,2021-Q1,4.047,Release,verified\n",
    )
    d = _full_dir(tmp_path)  # notes seed has no cloud_googl row
    with pytest.raises(TradeDataError, match="no source note"):
        ai_trade_data(d)


def test_cloud_panel_with_note_renders_eight(tmp_path):
    _cloud_sibling(
        tmp_path,
        "GOOGL,Google Cloud,2020-Q1,2.777,Release,verified\n"
        "GOOGL,Google Cloud,2021-Q1,4.047,Release,verified\n",
    )
    notes = _notes_seed() + "cloud_googl,8,Test source,2026-10-16,\n"
    d = _full_dir(tmp_path, **{"series_notes.csv": notes})
    data = ai_trade_data(d)
    assert len(data["panels"]) == 8
    assert data["panels"][7]["kind"] == "cloud"


def test_cloud_panel_malformed_csv_raises(tmp_path):
    _cloud_sibling(
        tmp_path,
        "GOOGL,Google Cloud,2021-Q1,4.047,Release,verified\n"
        "GOOGL,Google Cloud,2021-Q1,4.047,Release,verified\n",
    )
    d = _full_dir(tmp_path)
    with pytest.raises(TradeDataError, match="cloud panel"):
        ai_trade_data(d)


# --------------------------------------------------------------------------
# Projection math (the source chart's rules, replicated)


def test_trend_proj_extends_a_straight_line():
    pts = [("2026-01-31", 1.0), ("2026-02-28", 2.0), ("2026-03-31", 3.0), ("2026-04-30", 4.0)]
    seg = _trend_proj(pts, 4)
    assert seg is not None and seg[0] == pts[-1]
    assert seg[1][0] == "2027-03-31"
    assert seg[1][1] > 4.0  # rising line keeps rising


def test_trend_proj_floor_and_short_series():
    pts = [("2026-01-31", 10.0), ("2026-02-28", 5.0), ("2026-03-31", 2.0)]
    seg = _trend_proj(pts, 3, floor=1.0)
    assert seg is not None and seg[1][1] == 1.0  # decline floored, as for CRWV
    assert _trend_proj(pts[:2], 3) is None  # too few points: no projection


def test_capex_proj_uses_average_qoq_step():
    data = ai_trade_data(DATA_DIR)
    capex = data["panels"][2]["series"][0]
    assert capex["proj"] == [
        ("2026-06-30", pytest.approx(110.842)),
        ("2026-12-31", pytest.approx(126.708)),
        ("2027-03-31", pytest.approx(142.574)),
    ]
    assert _capex_proj([("2026-01-01", 1.0)]) is None


# --------------------------------------------------------------------------
# Render smoke tests


def test_render_writes_ai_trade_html(tmp_path):
    data = ai_trade_data(DATA_DIR)
    target = render_ai_trade_dashboard(data, tmp_path / "out")
    assert target.name == "ai-trade.html"
    page = target.read_text()
    for n, name in [
        (1, "Inflation"),
        (2, "Rates"),
        (3, "Hyperscaler capex"),
        (4, "Credit stress"),
        (5, "CoreWeave"),
        (6, "Compute economics"),
        (7, "CDS"),
        (8, "Hyperscaler cloud"),
    ]:
        assert f"{n} \u00b7 {name}" in page, f"panel {n} missing"
    assert page.count("<svg") >= 9  # 7 panels + Panel 8's two charts
    # Panel 8: end labels, the full y/y table, and the Azure footnote.
    assert "$42.2B" in page  # AWS latest revenue, end label
    assert "+82%" in page  # Google Cloud latest y/y, end label
    assert "The growth chart as a table" in page
    assert "+45.7" in page  # Google Cloud 2021-Q1 y/y, first table row
    assert "2021-Q1" in page and "2026-Q2" in page  # table row range
    assert "<td>+0.1*</td>" in page  # MSFT 2025-Q1, asterisked (redefinition)
    assert "does not disclose Azure revenue in dollars" in page
    assert "the 8-panel watch" in page
    assert "ORCL watch alert line ~250bp" in page
    assert "1,117" in page  # CRWV end label on Panel 7
    assert "Back to the portfolio dashboard" in page
    assert "Data as of 2026-10-16" in page
    # The CDS data table carries the prints with their press sources.
    assert "288" in page and "Reuters" in page
    # Panel 6 expectations are captioned as expectations, never as data.
    assert "investor-expected YE2026 $100\u2013120B" in page
