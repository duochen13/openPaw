"""Unit tests for operating EPS (ex-investment gains) and operating P/E (issue #70).

All network-free: companyfacts payloads are hand-built fixtures shaped like
the real SEC response. The headline case is GOOGL Q2'26: GAAP EPS $9.11 on a
~$99B unrealized equity-securities gain, where operating EPS comes out at
~$2.61 using the quarter's effective tax rate as the tax-on-gain proxy.
"""

from pathlib import Path

import pytest

from portfolio_analysis import fundamentals
from portfolio_analysis.store import Store


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
    return {
        "facts": {"us-gaap": {tag: {"units": {unit: units}} for tag, (unit, units) in tags.items()}}
    }


def _tag(unit, units):
    return (unit, units)


def _q(start, end, val, filed, fp="Q1", form="10-Q", fy=2026):
    return _u(start, end, val, fy, fp, form, filed)


# A full fiscal year shaped like GOOGL 2026: Q2 carries a ~$99B
# unrealized gain on equity securities; Q3's gain is exactly zero
# (fallback to GAAP); Q4 is derived FY-minus-Q1-Q3 for every tag.
GOOGL_2026 = _facts(
    EarningsPerShareDiluted=_tag(
        "USD/shares",
        [
            _q("2026-01-01", "2026-03-31", 2.00, "2026-04-24", fp="Q1"),
            _q("2026-04-01", "2026-06-30", 9.11, "2026-07-23", fp="Q2"),
            _q("2026-07-01", "2026-09-30", 3.00, "2026-10-22", fp="Q3"),
            _u("2026-01-01", "2026-12-31", 20.00, 2026, "FY", "10-K", "2027-02-10"),
        ],
    ),
    NetIncomeLoss=_tag(
        "USD",
        [
            _q("2026-01-01", "2026-03-31", 30.0e9, "2026-04-24", fp="Q1"),
            _q("2026-04-01", "2026-06-30", 112.193e9, "2026-07-23", fp="Q2"),
            _q("2026-07-01", "2026-09-30", 40.0e9, "2026-10-22", fp="Q3"),
            _u("2026-01-01", "2026-12-31", 230.0e9, 2026, "FY", "10-K", "2027-02-10"),
        ],
    ),
    EquitySecuritiesFvNiGainLoss=_tag(
        "USD",
        [
            _q("2026-01-01", "2026-03-31", 1.0e9, "2026-04-24", fp="Q1"),
            _q("2026-04-01", "2026-06-30", 99.031e9, "2026-07-23", fp="Q2"),
            _q("2026-07-01", "2026-09-30", 0.0, "2026-10-22", fp="Q3"),
            _u("2026-01-01", "2026-12-31", 110.0e9, 2026, "FY", "10-K", "2027-02-10"),
        ],
    ),
    IncomeTaxExpenseBenefit=_tag(
        "USD",
        [
            _q("2026-01-01", "2026-03-31", 8.0e9, "2026-04-24", fp="Q1"),
            _q("2026-04-01", "2026-06-30", 26.56e9, "2026-07-23", fp="Q2"),
            _q("2026-07-01", "2026-09-30", 10.0e9, "2026-10-22", fp="Q3"),
            _u("2026-01-01", "2026-12-31", 55.0e9, 2026, "FY", "10-K", "2027-02-10"),
        ],
    ),
)


def _op_by_quarter(rows):
    return {r["quarter"]: r["eps"] for r in rows}


def test_known_googl_q2_2026_operating_eps():
    rows = fundamentals.parse_operating_eps(GOOGL_2026)
    got = _op_by_quarter(rows)
    # tau = 26.56 / (112.193 + 26.56) = 19.14%; shares = 112.193e9 / 9.11
    assert got["2026-06-30"] == pytest.approx(2.61, abs=0.05)


def test_zero_gain_falls_back_to_gaap():
    rows = fundamentals.parse_operating_eps(GOOGL_2026)
    got = _op_by_quarter(rows)
    assert got["2026-09-30"] == pytest.approx(3.00)


def test_q4_derived_for_all_inputs():
    rows = fundamentals.parse_operating_eps(GOOGL_2026)
    got = _op_by_quarter(rows)
    # Q4: eps 5.89, ni 47.807e9, gain 9.969e9, tax 10.44e9
    assert got["2026-12-31"] == pytest.approx(4.88, abs=0.05)


def test_filed_is_latest_across_components():
    rows = fundamentals.parse_operating_eps(GOOGL_2026)
    by_q = {r["quarter"]: r for r in rows}
    assert by_q["2026-06-30"]["filed"] == "2026-07-23"


def test_no_gain_tag_falls_back_to_gaap():
    facts = _facts(
        EarningsPerShareDiluted=_tag(
            "USD/shares",
            [
                _q("2026-01-01", "2026-03-31", 1.50, "2026-04-24", fp="Q1"),
                _q("2026-04-01", "2026-06-30", 1.60, "2026-07-23", fp="Q2"),
            ],
        ),
    )
    rows = fundamentals.parse_operating_eps(facts)
    assert _op_by_quarter(rows) == {
        "2026-03-31": pytest.approx(1.50),
        "2026-06-30": pytest.approx(1.60),
    }


def test_missing_tax_with_nonzero_gain_is_gap_not_fallback():
    facts = _facts(
        EarningsPerShareDiluted=_tag(
            "USD/shares",
            [
                _q("2026-01-01", "2026-03-31", 2.00, "2026-04-24", fp="Q1"),
            ],
        ),
        NetIncomeLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 30.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
        EquitySecuritiesFvNiGainLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 5.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
    )
    rows = fundamentals.parse_operating_eps(facts)
    assert _op_by_quarter(rows)["2026-03-31"] is None


def test_nonpositive_pretax_is_gap():
    facts = _facts(
        EarningsPerShareDiluted=_tag(
            "USD/shares",
            [
                _q("2026-01-01", "2026-03-31", 0.50, "2026-04-24", fp="Q1"),
            ],
        ),
        NetIncomeLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", -5.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
        EquitySecuritiesFvNiGainLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 3.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
        IncomeTaxExpenseBenefit=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 2.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
    )
    rows = fundamentals.parse_operating_eps(facts)
    assert _op_by_quarter(rows)["2026-03-31"] is None


def test_negative_gain_added_back_symmetrically():
    facts = _facts(
        EarningsPerShareDiluted=_tag(
            "USD/shares",
            [
                _q("2026-01-01", "2026-03-31", 2.00, "2026-04-24", fp="Q1"),
            ],
        ),
        NetIncomeLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 20.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
        EquitySecuritiesFvNiGainLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", -4.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
        IncomeTaxExpenseBenefit=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 5.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
    )
    rows = fundamentals.parse_operating_eps(facts)
    # tau = 5/25 = 0.2; shares = 10e9; 2.00 + 4e9*0.8/10e9 = 2.32
    assert _op_by_quarter(rows)["2026-03-31"] == pytest.approx(2.32)


def test_amendment_dedup_latest_filed_wins():
    facts = _facts(
        EarningsPerShareDiluted=_tag(
            "USD/shares",
            [
                _q("2026-01-01", "2026-03-31", 2.00, "2026-04-24", fp="Q1"),
            ],
        ),
        NetIncomeLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 30.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
        EquitySecuritiesFvNiGainLoss=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 1.0e9, "2026-04-24", fp="Q1"),
                _u("2026-01-01", "2026-03-31", 9.0e9, 2026, "Q1", "10-Q/A", "2026-05-01"),
            ],
        ),
        IncomeTaxExpenseBenefit=_tag(
            "USD",
            [
                _q("2026-01-01", "2026-03-31", 8.0e9, "2026-04-24", fp="Q1"),
            ],
        ),
    )
    rows = fundamentals.parse_operating_eps(facts)
    by_q = {r["quarter"]: r for r in rows}
    # Restated gain 9e9 wins: tau = 8/38; shares = 15e9;
    # 2.00 - 9e9*(1-8/38)/15e9 = 2.00 - 0.4737 = 1.5263.
    # filed keeps the original date (established dedup semantics:
    # restated value, original filed date).
    assert by_q["2026-03-31"]["eps"] == pytest.approx(1.5263, abs=1e-3)
    assert by_q["2026-03-31"]["filed"] == "2026-04-24"


def test_ttm_eps_none_quarter_poisons_ttm():
    quarters = [
        ("2025-09-30", "2025-10-22", 3.00),
        ("2025-12-31", "2026-02-10", 4.00),
        ("2026-03-31", "2026-04-24", 2.00),
        ("2026-06-30", "2026-07-23", None),
    ]
    assert fundamentals.ttm_eps_on("2026-07-23", quarters) is None
    # The gap poisons the TTM for as long as the indeterminate quarter is
    # inside the four-quarter window...
    quarters.append(("2026-09-30", "2026-10-22", 3.50))
    assert fundamentals.ttm_eps_on("2026-10-22", quarters) is None
    # ...and the TTM resolves once four clean quarters roll it out.
    quarters.extend(
        [
            ("2026-12-31", "2027-02-10", 4.00),
            ("2027-03-31", "2027-04-24", 5.00),
            ("2027-06-30", "2027-07-23", 6.00),
        ]
    )
    assert fundamentals.ttm_eps_on("2027-07-23", quarters) == pytest.approx(18.50)


def test_operating_pe_has_no_cliff_where_gaap_does():
    # The user's core comparison: on 2026-07-23 GAAP TTM EPS jumps on the
    # $99B gain and GAAP P/E cliff-dives, while operating P/E barely moves.
    gaap = [
        ("2025-06-30", "2025-07-24", 2.31),
        ("2025-09-30", "2025-10-22", 2.87),
        ("2025-12-31", "2026-02-10", 2.82),
        ("2026-03-31", "2026-04-24", 5.11),
        ("2026-06-30", "2026-07-23", 9.11),
    ]
    operating = [
        ("2025-06-30", "2025-07-24", 2.31),
        ("2025-09-30", "2025-10-22", 2.87),
        ("2025-12-31", "2026-02-10", 2.82),
        ("2026-03-31", "2026-04-24", 2.90),
        ("2026-06-30", "2026-07-23", 2.61),
    ]
    prices = {"2026-07-22": 342.09, "2026-07-23": 317.69}
    gaap_pe = fundamentals.pe_series(prices, gaap)
    op_pe = fundamentals.pe_series(prices, operating, eps_source="operating")
    assert op_pe["2026-07-23"]["eps_source"] == "operating"
    gaap_before = gaap_pe["2026-07-22"]["pe"]
    gaap_after = gaap_pe["2026-07-23"]["pe"]
    op_before = op_pe["2026-07-22"]["pe"]
    op_after = op_pe["2026-07-23"]["pe"]
    # GAAP P/E cliff-dives by more than a third on the $99B gain...
    assert gaap_after < gaap_before * 0.67
    # ...while operating P/E barely moves (only the ~7% price dip).
    assert op_after > op_before * 0.85


def test_store_operating_eps_roundtrip_with_gap(tmp_path: Path):
    store = Store.open(tmp_path / "t.db")
    n = store.upsert_operating_eps_quarters(
        [
            {
                "ticker": "GOOGL",
                "quarter": "2026-03-31",
                "filed": "2026-04-24",
                "eps": 1.95,
                "source": "derived:ex-investment-gains",
            },
            {
                "ticker": "GOOGL",
                "quarter": "2026-06-30",
                "filed": "2026-07-23",
                "eps": None,
                "source": "derived:ex-investment-gains",
            },
        ]
    )
    assert n == 2
    assert store.operating_eps_quarters("GOOGL") == [
        ("2026-03-31", "2026-04-24", 1.95),
        ("2026-06-30", "2026-07-23", None),
    ]
    # Idempotent refetch: same rows, rewritten.
    n2 = store.upsert_operating_eps_quarters(
        [
            {
                "ticker": "GOOGL",
                "quarter": "2026-06-30",
                "filed": "2026-07-23",
                "eps": 2.61,
                "source": "derived:ex-investment-gains",
            },
        ]
    )
    assert n2 == 1
    assert store.operating_eps_quarters("googl")[-1] == ("2026-06-30", "2026-07-23", 2.61)
    store.close()
