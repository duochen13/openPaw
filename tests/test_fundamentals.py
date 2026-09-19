"""Unit tests for fundamentals.py and the eps_quarter store (issue #28).

All network-free: the companyfacts payload is a hand-built fixture shaped
like the real SEC response - including the two traps the real data sets:
a 10-Q's comparative prior-year column (same fp, the *filing's* fy, later
filed date) and a 10-K's comparative annuals. These run under the default
``-m 'not network'`` selection.
"""

import sqlite3
from pathlib import Path

import pytest

from portfolio_analysis import fundamentals
from portfolio_analysis.store import Store


def _u(start, end, val, fy, fp, form, filed):
    return {
        "start": start, "end": end, "val": val,
        "accn": "0000000000-00-000000", "fy": fy, "fp": fp,
        "form": form, "filed": filed,
    }


# Shaped like a real companyfacts response. Traps included:
# - the Q2 year-to-date figure (181 days, fp=Q2): duration filter skips it;
# - the Q1'25 10-Q's comparative Q1'24 column (fy=2025, filed a year later):
#   it is the same period, so it must not move the "known from" date;
# - a 10-Q/A restating Q2'25: latest value wins, earliest filed date stays;
# - the FY'25 10-K's comparative FY'24 annual: same period, no double Q4.
FACTS = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {
    "USD/shares": [
        _u("2024-01-01", "2024-03-31", 1.00, 2024, "Q1", "10-Q", "2024-04-25"),
        _u("2024-04-01", "2024-06-30", 1.10, 2024, "Q2", "10-Q", "2024-07-25"),
        _u("2024-01-01", "2024-06-30", 2.10, 2024, "Q2", "10-Q", "2024-07-25"),
        _u("2024-07-01", "2024-09-30", 1.20, 2024, "Q3", "10-Q", "2024-10-24"),
        _u("2024-01-01", "2024-12-31", 4.60, 2024, "FY", "10-K", "2025-02-13"),
        _u("2025-01-01", "2025-03-31", 1.05, 2025, "Q1", "10-Q", "2025-04-24"),
        _u("2024-01-01", "2024-03-31", 1.00, 2025, "Q1", "10-Q", "2025-04-24"),
        _u("2025-04-01", "2025-06-30", 1.15, 2025, "Q2", "10-Q", "2025-07-24"),
        _u("2025-04-01", "2025-06-30", 1.16, 2025, "Q2", "10-Q/A", "2025-08-01"),
        _u("2025-07-01", "2025-09-30", 1.25, 2025, "Q3", "10-Q", "2025-10-23"),
        _u("2025-01-01", "2025-12-31", 5.00, 2025, "FY", "10-K", "2026-02-12"),
        _u("2024-01-01", "2024-12-31", 4.60, 2025, "FY", "10-K", "2026-02-12"),
    ]
}}}}}

EXPECTED = [
    ("2024-03-31", "2024-04-25", 1.00),  # comparative reprint doesn't move filed
    ("2024-06-30", "2024-07-25", 1.10),
    ("2024-09-30", "2024-10-24", 1.20),
    ("2024-12-31", "2025-02-13", 1.30),  # derived: 4.60 - (1.00+1.10+1.20)
    ("2025-03-31", "2025-04-24", 1.05),
    ("2025-06-30", "2025-07-24", 1.16),  # restated value, original filed date
    ("2025-09-30", "2025-10-23", 1.25),
    ("2025-12-31", "2026-02-12", 1.54),  # derived: 5.00 - (1.05+1.16+1.25)
]


def test_parse_quarterly_eps():
    rows = fundamentals.parse_quarterly_eps(FACTS)
    got = [(r["quarter"], r["filed"], r["eps"]) for r in rows]
    assert [g[:2] for g in got] == [e[:2] for e in EXPECTED]
    assert [g[2] for g in got] == pytest.approx([e[2] for e in EXPECTED])


def test_parse_skips_ytd_decoy():
    # The 181-day "Q2" unit is year-to-date, not the quarter.
    rows = fundamentals.parse_quarterly_eps(FACTS)
    q2 = [r for r in rows if r["quarter"] == "2024-06-30"]
    assert len(q2) == 1 and q2[0]["eps"] == pytest.approx(1.10)


def test_parse_comparative_column_keeps_original_filed_date():
    # The Q1'25 10-Q reprints Q1'24 with a 2025 filed date; the quarter was
    # known in April 2024, and point-in-time math must use that date.
    rows = fundamentals.parse_quarterly_eps(FACTS)
    q1 = [r for r in rows if r["quarter"] == "2024-03-31"]
    assert len(q1) == 1 and q1[0]["filed"] == "2024-04-25"


def test_parse_comparative_annual_no_double_q4():
    rows = fundamentals.parse_quarterly_eps(FACTS)
    q4s = [r for r in rows if r["quarter"] == "2024-12-31"]
    assert len(q4s) == 1 and q4s[0]["eps"] == pytest.approx(1.30)


def test_parse_q4_needs_all_three_quarters():
    facts = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {
        "USD/shares": [
            _u("2024-01-01", "2024-03-31", 1.00, 2024, "Q1", "10-Q", "2024-04-25"),
            _u("2024-01-01", "2024-12-31", 4.60, 2024, "FY", "10-K", "2025-02-13"),
        ]
    }}}}}
    rows = fundamentals.parse_quarterly_eps(facts)
    assert [r["quarter"] for r in rows] == ["2024-03-31"]  # no Q4 derived


def test_parse_missing_concept_raises():
    with pytest.raises(fundamentals.VendorResponseError):
        fundamentals.parse_quarterly_eps({"facts": {"us-gaap": {}}})


def test_fetch_companyfacts_rejects_bad_cik():
    with pytest.raises(ValueError):
        fundamentals.fetch_companyfacts(0, lambda *a, **k: {})


def test_fetch_companyfacts_uses_seam():
    seen = {}

    def fake_get_json(provider, url, *, daily_limit, max_age=None):
        seen["provider"] = provider
        seen["url"] = url
        seen["daily_limit"] = daily_limit
        return FACTS

    assert fundamentals.fetch_companyfacts(1373715, fake_get_json) is FACTS
    assert seen["provider"] == "edgar"
    assert "CIK0001373715.json" in seen["url"]
    assert seen["daily_limit"] is None


def test_ttm_eps_gated_by_filed_date():
    q = EXPECTED
    # Q4 2024 is filed 2025-02-13; the day before, only 3 quarters are known.
    assert fundamentals.ttm_eps_on("2025-02-12", q) is None
    assert fundamentals.ttm_eps_on("2025-02-13", q) == pytest.approx(4.60)
    # Rolls forward: Q3'24 + Q4'24 + Q1'25 + Q2'25(restated).
    assert fundamentals.ttm_eps_on("2025-08-01", q) == pytest.approx(4.71)


def test_pe_series():
    series = fundamentals.pe_series({"2025-02-13": 100.0, "2025-02-12": 99.0},
                                    EXPECTED)
    assert series["2025-02-13"]["pe"] == pytest.approx(100.0 / 4.60)
    assert series["2025-02-13"]["ttm_eps"] == pytest.approx(4.60)
    assert series["2025-02-12"]["pe"] is None


def test_pe_series_negative_eps_is_gap_not_number():
    quarters = [
        ("2024-03-31", "2024-04-25", 1.0),
        ("2024-06-30", "2024-07-25", 1.0),
        ("2024-09-30", "2024-10-24", -5.0),
        ("2024-12-31", "2025-02-13", 1.0),
    ]
    series = fundamentals.pe_series({"2025-03-01": 100.0}, quarters)
    assert series["2025-03-01"]["ttm_eps"] == pytest.approx(-2.0)
    assert series["2025-03-01"]["pe"] is None


def _rows(quarters):
    return [
        {"ticker": "NOW", "quarter": q, "filed": f, "eps": e, "source": "edgar"}
        for q, f, e in quarters
    ]


def test_store_eps_quarters_roundtrip(tmp_path: Path):
    store = Store.open(tmp_path / "t.db")
    try:
        assert store.upsert_eps_quarters(_rows(EXPECTED)) == 8
        got = store.eps_quarters("now")  # case-insensitive
        assert [g[:2] for g in got] == [e[:2] for e in EXPECTED]
        assert [g[2] for g in got] == pytest.approx([e[2] for e in EXPECTED])
        assert store.eps_fetched_at("NOW") is not None
        assert store.eps_fetched_at("META") is None
        # Restatement overwrites rather than duplicating.
        store.upsert_eps_quarters(
            [{"ticker": "NOW", "quarter": "2025-09-30", "filed": "2025-10-23",
              "eps": 1.26, "source": "edgar"}]
        )
        got = store.eps_quarters("NOW")
        assert len(got) == 8
        assert got[6] == ("2025-09-30", "2025-10-23", 1.26)
    finally:
        store.close()


def test_store_eps_table_survives_old_database(tmp_path: Path):
    # A database from before the eps_quarter table existed gains it on open.
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE price_bar (ticker TEXT NOT NULL, date TEXT NOT NULL,"
        " open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,"
        " close REAL NOT NULL, adj_close REAL NOT NULL, volume REAL NOT NULL,"
        " source TEXT NOT NULL, fetched_at TEXT NOT NULL,"
        " PRIMARY KEY (ticker, date))"
    )
    conn.execute(
        "CREATE TABLE move (ticker TEXT NOT NULL, date TEXT NOT NULL,"
        " ret REAL NOT NULL, benchmark TEXT NOT NULL,"
        " benchmark_return REAL NOT NULL, beta REAL NOT NULL,"
        " abnormal_return REAL NOT NULL, sigma_60 REAL NOT NULL,"
        " z REAL NOT NULL, computed_at TEXT NOT NULL,"
        " PRIMARY KEY (ticker, date))"
    )
    conn.commit()
    conn.close()
    store = Store.open(db)
    try:
        store.upsert_eps_quarters(_rows(EXPECTED[:1]))
        assert store.eps_quarters("NOW") == EXPECTED[:1]
    finally:
        store.close()


def test_store_eps_filed_column_migrated(tmp_path: Path):
    # Databases created during issue #28 development may lack `filed`.
    db = tmp_path / "mid.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE eps_quarter (ticker TEXT NOT NULL, quarter TEXT NOT NULL,"
        " eps REAL NOT NULL, source TEXT NOT NULL, fetched_at TEXT NOT NULL,"
        " PRIMARY KEY (ticker, quarter))"
    )
    conn.commit()
    conn.close()
    store = Store.open(db)
    try:
        store.upsert_eps_quarters(_rows(EXPECTED[:1]))
        assert store.eps_quarters("NOW") == EXPECTED[:1]
    finally:
        store.close()
