from datetime import UTC, datetime
from unittest import mock

import pytest

from stock_trading_bot.ingest import edgar
from stock_trading_bot.store import Store

FACTS = {
    "cik": 1373715,
    "entityName": "ServiceNow, Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"fy": 2026, "fp": "Q1", "form": "10-Q", "val": 3700000000,
                         "filed": "2026-04-23", "accn": "0001373715-26-000045"},
                        {"fy": 2026, "fp": "Q2", "form": "10-Q", "val": 3987000000,
                         "filed": "2026-07-23", "accn": "0001373715-26-000072"},
                        {"fy": 2026, "fp": "Q1", "form": "10-Q/A", "val": 3701000000,
                         "filed": "2026-08-01", "accn": "0001373715-26-000090"},
                        {"form": "10-Q", "val": 1, "filed": "2026-04-23",
                         "accn": "x"},  # no fy/fp: skipped
                    ]
                }
            }
        }
    },
}
OBSERVED = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)
BUDGET = {"edgar": 1800}


def _fetch():
    return mock.patch.object(edgar, "_http_get_json", return_value=FACTS)


def _rows():
    with _fetch():
        return edgar.fetch_facts("NOW", cik=1373715, concepts=["Revenues"],
                                 observed_at=OBSERVED, latency_budget=BUDGET)


@pytest.mark.unit
def test_extracts_one_row_per_accession_skipping_entries_without_a_period():
    assert len(_rows()) == 3


@pytest.mark.unit
def test_known_at_derives_from_the_filing_date_not_the_fetch_time():
    """A 10-Q filed in April was knowable in April. Deriving known_at from the
    scrape time instead would discard most of the usable history."""
    q1 = next(r for r in _rows() if r["accession"] == "0001373715-26-000045")
    assert q1["known_at"] == "2026-04-23T00:30:00.000000+00:00"


@pytest.mark.unit
def test_every_timestamp_is_canonical():
    """Mixed spellings in one column sort wrongly against each other."""
    for row in _rows():
        for column in ("event_time", "observed_at", "known_at", "valid_from"):
            assert str(row[column]).endswith("+00:00")
            assert len(str(row[column])) == len("2026-04-23T00:30:00.000000+00:00")


@pytest.mark.unit
def test_a_restatement_is_a_separate_row_with_a_later_known_at():
    q1 = sorted(
        (r for r in _rows() if r["fiscal_period"] == "2026Q1"),
        key=lambda r: str(r["known_at"]),
    )
    assert len(q1) == 2
    assert [r["value"] for r in q1] == [3700000000, 3701000000]


@pytest.mark.unit
def test_the_original_value_stays_visible_before_the_restatement(tmp_path):
    """Standing at 2026-05-01 we must see 3.700B, not the August correction."""
    store = Store.open(tmp_path / "panel.sqlite")
    for row in _rows():
        store.insert_fundamental_fact(**row)

    view = store.as_of(datetime(2026, 5, 1, tzinfo=UTC))
    assert [r["value"] for r in view.fundamental_facts("NOW", concept="Revenues")] == [
        3700000000
    ]


@pytest.mark.unit
def test_the_restatement_becomes_visible_afterwards(tmp_path):
    store = Store.open(tmp_path / "panel.sqlite")
    for row in _rows():
        store.insert_fundamental_fact(**row)

    view = store.as_of(datetime(2026, 9, 1, tzinfo=UTC))
    values = [r["value"] for r in view.fundamental_facts("NOW", concept="Revenues")]
    assert sorted(values) == [3700000000, 3701000000, 3987000000]


@pytest.mark.unit
def test_refetching_the_same_filing_appends_rather_than_colliding(tmp_path):
    """Re-fetching a filing you already have is routine. The primary key
    includes observed_at so a re-observation appends."""
    store = Store.open(tmp_path / "panel.sqlite")
    for row in _rows():
        store.insert_fundamental_fact(**row)
    for row in _rows():
        store.insert_fundamental_fact(**{**row, "observed_at": "2026-09-08T12:00:00.000000+00:00"})

    view = store.as_of(datetime(2026, 9, 30, tzinfo=UTC))
    assert len(view.fundamental_facts("NOW", concept="Revenues")) == 6


@pytest.mark.unit
def test_ticker_is_sanitized_before_any_request():
    with pytest.raises(ValueError):
        edgar.fetch_facts("../x", cik=1, concepts=["Revenues"],
                          observed_at=OBSERVED, latency_budget=BUDGET)
