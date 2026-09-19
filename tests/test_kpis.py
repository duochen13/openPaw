"""Unit tests for kpis.py and the kpi_quarter store (issue #29).

All network-free: companyfacts payloads are hand-built fixtures shaped like
the real SEC responses, including the traps the real data sets - YTD cash
flow statements that must be de-accumulated, filers renaming the revenue
tag mid-history, comparative prior-year columns, and restated reprints.
These run under the default ``-m 'not network'`` selection.
"""

import sqlite3
from pathlib import Path
from unittest import mock

import pytest
import yaml

from portfolio_analysis import cli, fundamentals, kpis
from portfolio_analysis.store import Store

REPO_ROOT = Path(kpis.__file__).resolve().parents[2]


def _u(start, end, val, fy, fp, form, filed):
    return {
        "start": start, "end": end, "val": val,
        "accn": "0000000000-00-000000", "fy": fy, "fp": fp,
        "form": form, "filed": filed,
    }


def _u_instant(end, val, fy, fp, form, filed):
    return {
        "end": end, "val": val,
        "accn": "0000000000-00-000000", "fy": fy, "fp": fp,
        "form": form, "filed": filed, "frame": "CY2024Q1",
    }


def _facts(tag, units, taxonomy="us-gaap", unit="USD"):
    return {"facts": {taxonomy: {tag: {"units": {unit: units}}}}}


CAPEX_UNITS = [
    # FY2024: full YTD chain Q1/H1/9M/FY.
    _u("2024-01-01", "2024-03-31", -100.0, 2024, "Q1", "10-Q", "2024-04-25"),
    _u("2024-01-01", "2024-06-30", -250.0, 2024, "Q2", "10-Q", "2024-07-25"),
    _u("2024-01-01", "2024-09-30", -420.0, 2024, "Q3", "10-Q", "2024-10-24"),
    _u("2024-01-01", "2024-12-31", -600.0, 2024, "FY", "10-K", "2025-02-13"),
    # FY2025: Q2's 10-Q is missing - Q3 and the 9M baseline shift.
    _u("2025-01-01", "2025-03-31", -110.0, 2025, "Q1", "10-Q", "2025-04-24"),
    _u("2025-01-01", "2025-09-30", -450.0, 2025, "Q3", "10-Q", "2025-10-23"),
    _u("2025-01-01", "2025-12-31", -640.0, 2025, "FY", "10-K", "2026-02-12"),
    # The Q1'25 10-Q's comparative Q1'24 column: same period, later filing.
    # Grouped by YTD start, it must not disturb FY2024's chain.
    _u("2024-01-01", "2024-03-31", -100.0, 2025, "Q1", "10-Q", "2025-04-24"),
]


def test_parse_ytd_deaccumulates_quarters():
    rows = fundamentals.parse_quarterly_fact(
        _facts("PaymentsToAcquirePropertyPlantAndEquipment", CAPEX_UNITS),
        [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD")],
        period="ytd",
    )
    got = {q: v for q, _, v in rows}
    # Filed negative (cash outflow); raw parse keeps the filed sign.
    assert got["2024-03-31"] == pytest.approx(-100.0)
    assert got["2024-06-30"] == pytest.approx(-150.0)
    assert got["2024-09-30"] == pytest.approx(-170.0)
    assert got["2024-12-31"] == pytest.approx(-180.0)
    assert got["2025-03-31"] == pytest.approx(-110.0)
    assert got["2025-12-31"] == pytest.approx(-190.0)
    # Q2'25 and Q3'25 are gaps: 9M minus Q1 would be a two-quarter sum.
    assert "2025-06-30" not in got
    assert "2025-09-30" not in got


def test_parse_ytd_filed_date_is_the_revealing_filing():
    rows = fundamentals.parse_quarterly_fact(
        _facts("PaymentsToAcquirePropertyPlantAndEquipment", CAPEX_UNITS),
        [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD")],
        period="ytd",
    )
    by_q = {q: f for q, f, _ in rows}
    # Q2'24 was revealed by the H1 10-Q, not the Q1 filing.
    assert by_q["2024-06-30"] == "2024-07-25"
    # Q4'24 was revealed by the 10-K.
    assert by_q["2024-12-31"] == "2025-02-13"


def test_parse_ytd_comparative_column_keeps_original_filed():
    rows = fundamentals.parse_quarterly_fact(
        _facts("PaymentsToAcquirePropertyPlantAndEquipment", CAPEX_UNITS),
        [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD")],
        period="ytd",
    )
    by_q = {q: f for q, f, _ in rows}
    assert by_q["2024-03-31"] == "2024-04-25"


RPO_UNITS = [
    _u_instant("2024-03-31", 1000.0, 2024, "Q1", "10-Q", "2024-04-25"),
    _u_instant("2024-06-30", 1100.0, 2024, "Q2", "10-Q", "2024-07-25"),
    # The Q2 10-Q reprints Q1 with a restated value: latest value wins,
    # earliest filed date stays (point-in-time).
    _u_instant("2024-03-31", 1050.0, 2024, "Q2", "10-Q", "2024-07-25"),
]


def test_parse_instant_keyed_by_end_date():
    rows = fundamentals.parse_quarterly_fact(
        _facts("RevenueRemainingPerformanceObligation", RPO_UNITS),
        [("us-gaap", "RevenueRemainingPerformanceObligation", "USD")],
        period="instant",
    )
    assert rows == [
        ("2024-03-31", "2024-04-25", pytest.approx(1050.0)),
        ("2024-06-30", "2024-07-25", pytest.approx(1100.0)),
    ]


def test_parse_quarterly_fact_rejects_bad_period():
    with pytest.raises(ValueError):
        fundamentals.parse_quarterly_fact({}, [], period="fortnight")


def test_parse_quarterly_fact_missing_tag_is_empty_not_error():
    # META/GOOGL do not tag GrossProfit: no data, not an exception.
    rows = fundamentals.parse_quarterly_fact(
        {"facts": {"us-gaap": {}}},
        [("us-gaap", "GrossProfit", "USD")],
        period="quarter",
    )
    assert rows == []


# NOW renamed its revenue tag mid-history: quarterly Revenues stops in
# 2018, RevenueFromContractWithCustomerExcludingAssessedTax continues.
# The merge must keep history continuous and prefer the current tag
# where both report the same quarter.
REV_UNITS_OLD = [
    _u("2018-01-01", "2018-03-31", 10.0, 2018, "Q1", "10-Q", "2018-04-25"),
    _u("2018-04-01", "2018-06-30", 11.0, 2018, "Q2", "10-Q", "2018-07-25"),
    _u("2018-07-01", "2018-09-30", 12.0, 2018, "Q3", "10-Q", "2018-10-24"),
    _u("2018-01-01", "2018-12-31", 48.0, 2018, "FY", "10-K", "2019-02-13"),
]
REV_UNITS_NEW = [
    _u("2018-01-01", "2018-03-31", 10.5, 2018, "Q1", "10-Q", "2018-04-26"),
    _u("2018-04-01", "2018-06-30", 11.5, 2018, "Q2", "10-Q", "2018-07-26"),
    _u("2018-07-01", "2018-09-30", 12.5, 2018, "Q3", "10-Q", "2018-10-25"),
    _u("2018-01-01", "2018-12-31", 49.5, 2018, "FY", "10-K", "2019-02-14"),
    _u("2019-01-01", "2019-03-31", 13.0, 2019, "Q1", "10-Q", "2019-04-24"),
    _u("2019-04-01", "2019-06-30", 14.0, 2019, "Q2", "10-Q", "2019-07-24"),
    _u("2019-07-01", "2019-09-30", 15.0, 2019, "Q3", "10-Q", "2019-10-23"),
    _u("2019-01-01", "2019-12-31", 60.0, 2019, "FY", "10-K", "2020-02-12"),
]


def test_parse_quarterly_fact_merges_tags_by_recency():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": REV_UNITS_OLD}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {"USD": REV_UNITS_NEW}},
    }}}
    rows = fundamentals.parse_quarterly_fact(
        facts,
        [("us-gaap", "Revenues", "USD"),
         ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD")],
        period="quarter",
    )
    by_q = {q: v for q, _, v in rows}
    # Overlap quarters come from the current tag (latest coverage wins).
    assert by_q["2018-03-31"] == pytest.approx(10.5)
    assert by_q["2018-12-31"] == pytest.approx(15.0)  # derived Q4, new tag
    # History continues past the old tag's end.
    assert by_q["2019-12-31"] == pytest.approx(18.0)
    assert [q for q, _, _ in rows] == sorted(by_q)


MARGIN_FACTS = {"facts": {"us-gaap": {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        _u("2024-01-01", "2024-03-31", 100.0, 2024, "Q1", "10-Q", "2024-04-25"),
        _u("2024-04-01", "2024-06-30", 100.0, 2024, "Q2", "10-Q", "2024-07-25"),
        _u("2024-07-01", "2024-09-30", 100.0, 2024, "Q3", "10-Q", "2024-10-24"),
        _u("2024-01-01", "2024-12-31", 400.0, 2024, "FY", "10-K", "2025-02-13"),
        _u("2025-01-01", "2025-03-31", 0.0, 2025, "Q1", "10-Q", "2025-04-24"),
    ]}},
    "OperatingIncomeLoss": {"units": {"USD": [
        _u("2024-01-01", "2024-03-31", 20.0, 2024, "Q1", "10-Q", "2024-04-26"),
        _u("2024-04-01", "2024-06-30", 30.0, 2024, "Q2", "10-Q", "2024-07-26"),
        # Q3 operating income missing: no margin that quarter, and no
        # derived Q4 margin (needs all three quarters).
        _u("2025-01-01", "2025-03-31", 5.0, 2025, "Q1", "10-Q", "2025-04-24"),
    ]}},
}}}


def test_build_kpi_series_margin_joins_on_quarter():
    series = kpis.build_kpi_series(MARGIN_FACTS, ["operating_margin"])
    rows = series["operating_margin"]
    by_q = {q: v for q, _, v in rows}
    assert by_q["2024-03-31"] == pytest.approx(0.20)
    assert by_q["2024-06-30"] == pytest.approx(0.30)
    # No operating income for Q3/Q4 -> no margin, not a zero.
    assert "2024-09-30" not in by_q
    assert "2024-12-31" not in by_q
    # Zero revenue -> undefined margin, skipped rather than infinite.
    assert "2025-03-31" not in by_q


def test_build_kpi_series_margin_filed_is_max_of_both():
    series = kpis.build_kpi_series(MARGIN_FACTS, ["operating_margin"])
    by_q = {q: f for q, f, _ in series["operating_margin"]}
    # The quarter is known once both filings exist.
    assert by_q["2024-03-31"] == "2024-04-26"


def test_build_kpi_series_omits_metrics_without_data():
    series = kpis.build_kpi_series({"facts": {"us-gaap": {}}}, ["gross_margin"])
    assert series == {}


def test_build_kpi_series_capex_reads_as_positive_spend():
    # Real filers disagree on the sign: the fixture below is negative
    # (cash outflow); META/NOW tag it positive. abs() reads correctly
    # under either convention.
    facts = _facts("PaymentsToAcquirePropertyPlantAndEquipment", CAPEX_UNITS)
    series = kpis.build_kpi_series(facts, ["capex"])
    by_q = {q: v for q, _, v in series["capex"]}
    assert by_q["2024-03-31"] == pytest.approx(100.0)
    assert by_q["2024-06-30"] == pytest.approx(150.0)


def test_build_kpi_series_capex_positive_filed_stays_positive():
    units = [
        _u("2024-01-01", "2024-03-31", 100.0, 2024, "Q1", "10-Q", "2024-04-25"),
        _u("2024-01-01", "2024-06-30", 250.0, 2024, "Q2", "10-Q", "2024-07-25"),
    ]
    facts = _facts("PaymentsToAcquirePropertyPlantAndEquipment", units)
    series = kpis.build_kpi_series(facts, ["capex"])
    assert [v for _, _, v in series["capex"]] == pytest.approx([100.0, 150.0])


def _series(vals, start_year=2024):
    quarters = ["03-31", "06-30", "09-30", "12-31", "03-31", "06-30"]
    years = [start_year, start_year, start_year, start_year,
             start_year + 1, start_year + 1]
    return [
        (f"{y}-{md}", "2024-01-01", v)
        for (y, md), v in zip(zip(years, quarters, strict=True), vals, strict=True)
    ]


def test_with_yoy_fractional_change():
    dated = kpis.with_yoy(_series([100.0, 110, 120, 130, 150, 165]))
    assert [y for _, _, y in dated[:4]] == [None] * 4
    assert dated[4][2] == pytest.approx(0.50)
    assert dated[5][2] == pytest.approx(0.50)


def test_with_yoy_pp_mode():
    dated = kpis.with_yoy(_series([0.20, 0.22, 0.21, 0.23, 0.25, 0.24]), pp=True)
    assert dated[4][2] == pytest.approx(0.05)
    assert dated[5][2] == pytest.approx(0.02)


def test_with_yoy_missing_year_ago_is_gap():
    # A missing quarter in the middle: the 4th row back is ~2 years ago,
    # outside the YoY window, so no YoY is reported.
    series = [
        ("2023-03-31", "2023-04-01", 100.0),
        ("2023-06-30", "2023-07-01", 110.0),
        # 2023-09-30 missing
        ("2023-12-31", "2024-01-01", 130.0),
        ("2024-03-31", "2024-04-01", 140.0),
        ("2024-06-30", "2024-07-01", 150.0),
        ("2024-09-30", "2024-10-01", 160.0),
        ("2024-12-31", "2025-01-01", 170.0),
    ]
    dated = kpis.with_yoy(series)
    by_q = {q: y for q, _, y in dated}
    # 2024-09-30's 4th-row-back is 2023-06-30 (456 days): too far, gap.
    assert by_q["2024-09-30"] is None
    # 2024-12-31's 4th-row-back is 2023-12-31 (366 days): valid.
    assert by_q["2024-12-31"] == pytest.approx((170 - 130) / 130)


def test_kpi_panels_shape_and_order():
    series = {
        "revenue": _series([100.0, 110, 120, 130, 150, 165]),
        "operating_margin": _series([0.20, 0.22, 0.21, 0.23, 0.25, 0.24]),
    }
    panels = kpis.kpi_panels(series, ["operating_margin", "revenue"])
    assert panels is not None
    assert [m["key"] for m in panels["metrics"]] == ["operating_margin", "revenue"]
    rev = panels["metrics"][1]
    assert rev["label"] == "Revenue"
    assert rev["format"] == "currency"
    assert rev["current"] == pytest.approx(165.0)
    assert rev["current_yoy"] == pytest.approx(0.50)
    assert rev["as_of"] == "2025-06-30"
    assert rev["quarters_reported"] == 6
    assert rev["yoy_unit"] == "pct"
    margin = panels["metrics"][0]
    assert margin["yoy_unit"] == "pp"
    assert margin["current_yoy"] == pytest.approx(0.02)


def test_kpi_panels_none_when_empty():
    assert kpis.kpi_panels({}) is None


def test_load_kpi_config(tmp_path: Path):
    cfg = tmp_path / "kpi.yaml"
    cfg.write_text(yaml.safe_dump({"kpis": {"now": ["revenue", "rpo"]}}))
    assert kpis.load_kpi_config(cfg) == {"NOW": ["revenue", "rpo"]}


def test_load_kpi_config_rejects_unknown_metric(tmp_path: Path):
    cfg = tmp_path / "kpi.yaml"
    cfg.write_text(yaml.safe_dump({"kpis": {"NOW": ["dau"]}}))
    with pytest.raises(kpis.ConfigError):
        kpis.load_kpi_config(cfg)


def test_load_kpi_config_rejects_bad_shape(tmp_path: Path):
    cfg = tmp_path / "kpi.yaml"
    cfg.write_text(yaml.safe_dump({"kpis": {"NOW": []}}))
    with pytest.raises(kpis.ConfigError):
        kpis.load_kpi_config(cfg)
    with pytest.raises(kpis.ConfigError):
        kpis.load_kpi_config(tmp_path / "missing.yaml")


def test_load_kpi_config_repo_config_is_valid():
    # The shipped config must load and only name known metrics.
    config = kpis.load_kpi_config()
    assert set(config) >= {"META", "NOW"}
    assert config["META"] == ["revenue", "operating_margin", "capex"]


def _kpi_rows(ticker, metric, quarters):
    return [
        {"ticker": ticker, "metric": metric, "quarter": q, "filed": f,
         "value": v, "source": "edgar"}
        for q, f, v in quarters
    ]


def test_store_kpi_quarters_roundtrip(tmp_path: Path):
    store = Store.open(tmp_path / "t.db")
    try:
        quarters = [("2024-03-31", "2024-04-25", 100.0),
                    ("2024-06-30", "2024-07-25", 150.0)]
        assert store.upsert_kpi_quarters(_kpi_rows("NOW", "revenue", quarters)) == 2
        assert store.upsert_kpi_quarters(_kpi_rows("NOW", "capex", quarters)) == 2
        got = store.kpi_quarters("now", "revenue")  # case-insensitive ticker
        assert [(q, f) for q, f, _ in got] == [(q, f) for q, f, _ in quarters]
        assert [v for _, _, v in got] == pytest.approx([100.0, 150.0])
        # Metrics are namespaced: capex rows do not leak into revenue.
        assert len(store.kpi_quarters("NOW", "capex")) == 2
        assert store.kpi_quarters("NOW", "rpo") == []
        assert store.kpi_fetched_at("NOW") is not None
        assert store.kpi_fetched_at("META") is None
        # Restatement overwrites rather than duplicating.
        store.upsert_kpi_quarters(
            _kpi_rows("NOW", "revenue", [("2024-06-30", "2024-07-25", 151.0)])
        )
        got = store.kpi_quarters("NOW", "revenue")
        assert len(got) == 2
        assert got[1][2] == pytest.approx(151.0)
    finally:
        store.close()


def test_store_kpi_table_survives_old_database(tmp_path: Path):
    # A database from before the kpi_quarter table existed gains it on open.
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE eps_quarter (ticker TEXT NOT NULL, quarter TEXT NOT NULL,"
        " filed TEXT NOT NULL, eps REAL NOT NULL, source TEXT NOT NULL,"
        " fetched_at TEXT NOT NULL, PRIMARY KEY (ticker, quarter))"
    )
    conn.commit()
    conn.close()
    store = Store.open(db)
    try:
        store.upsert_kpi_quarters(
            _kpi_rows("NOW", "revenue", [("2024-03-31", "2024-04-25", 100.0)])
        )
        assert store.kpi_quarters("NOW", "revenue") == [
            ("2024-03-31", "2024-04-25", 100.0)
        ]
    finally:
        store.close()


# One companyfacts payload backs both the EPS parse (issue #28) and the
# KPI parse (issue #29): the CLI must fetch once and write both.
CLI_FACTS = {"facts": {"us-gaap": {
    "EarningsPerShareDiluted": {"units": {"USD/shares": [
        _u("2024-01-01", "2024-03-31", 1.0, 2024, "Q1", "10-Q", "2024-04-25"),
    ]}},
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        _u("2024-01-01", "2024-03-31", 100.0, 2024, "Q1", "10-Q", "2024-04-25"),
    ]}},
    "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
        _u("2024-01-01", "2024-03-31", -10.0, 2024, "Q1", "10-Q", "2024-04-25"),
    ]}},
}}}


def test_fetch_fundamentals_writes_eps_and_kpis_in_one_fetch(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.chdir(REPO_ROOT)
    db = tmp_path / "t.sqlite"
    with mock.patch.object(
        cli.fundamentals, "fetch_companyfacts", return_value=CLI_FACTS
    ) as fake:
        assert cli.main(["fetch-fundamentals", "--db", str(db), "META"]) == 0
    assert fake.call_count == 1  # one fetch backs EPS and all KPIs
    store = Store.open(db)
    try:
        assert len(store.eps_quarters("META")) == 1
        assert len(store.kpi_quarters("META", "revenue")) == 1
        capex = store.kpi_quarters("META", "capex")
        assert [v for _, _, v in capex] == pytest.approx([10.0])  # sign-normalized
        # No OperatingIncomeLoss in the fixture: the margin is omitted,
        # not a zero.
        assert store.kpi_quarters("META", "operating_margin") == []
    finally:
        store.close()
    assert "KPI quarter(s)" in capsys.readouterr().out


def test_fetch_fundamentals_failure_keeps_stored_kpis(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    db = tmp_path / "t.sqlite"
    store = Store.open(db)
    try:
        store.upsert_eps_quarters(
            [{"ticker": "META", "quarter": "2024-03-31", "filed": "2024-04-25",
              "eps": 1.0, "source": "edgar"}]
        )
        store.upsert_kpi_quarters(
            _kpi_rows("META", "revenue", [("2024-03-31", "2024-04-25", 100.0)])
        )
    finally:
        store.close()
    with mock.patch.object(
        cli.fundamentals, "fetch_companyfacts",
        side_effect=fundamentals.VendorResponseError("EDGAR down"),
    ):
        assert cli.main(["fetch-fundamentals", "--db", str(db), "--force", "META"]) == 0
    store = Store.open(db)
    try:
        assert store.kpi_quarters("META", "revenue") == [
            ("2024-03-31", "2024-04-25", 100.0)
        ]
        assert len(store.eps_quarters("META")) == 1
    finally:
        store.close()


def test_fetch_fundamentals_skips_when_eps_and_kpis_fresh(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.chdir(REPO_ROOT)
    db = tmp_path / "t.sqlite"
    with mock.patch.object(
        cli.fundamentals, "fetch_companyfacts", return_value=CLI_FACTS
    ) as fake:
        assert cli.main(["fetch-fundamentals", "--db", str(db), "META"]) == 0
        assert cli.main(["fetch-fundamentals", "--db", str(db), "META"]) == 0
    assert fake.call_count == 1  # the second run skipped: EPS and KPIs fresh
    assert "fresh, skipping" in capsys.readouterr().out
