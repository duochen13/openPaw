from dataclasses import FrozenInstanceError

import pytest

from portfolio_analysis.events.base import Document, VerifiedFact


def _doc(**kw):
    base = dict(source="x", native_id="1", published_at="2024-04-25T11:00:00Z", title="t", url="u")
    return Document.make(**{**base, **kw})


@pytest.mark.unit
def test_doc_ids_are_namespaced_by_source():
    """HN and Alpha Vantage both hand out bare ids; without a namespace two
    unrelated documents collide on one key."""
    a = _doc(source="hackernews", native_id="39812345")
    b = _doc(source="alphavantage_news", native_id="39812345")
    assert a.doc_id == "hackernews:39812345"
    assert a.doc_id != b.doc_id


@pytest.mark.unit
def test_a_document_is_frozen():
    # FrozenInstanceError specifically, not a blind Exception: ruff's B017
    # rejects the latter, and rightly - it would also pass if the attribute
    # simply did not exist.
    with pytest.raises(FrozenInstanceError):
        _doc().title = "changed"  # type: ignore[misc]


@pytest.mark.unit
def test_published_at_is_normalized_to_canonical_utc():
    """Alpha Vantage emits 20240425T110000; HN emits epoch seconds. One shape
    downstream, so lexicographic order equals chronological order."""
    assert _doc(published_at="20240425T110000").published_at == "2024-04-25T11:00:00+00:00"


@pytest.mark.unit
def test_an_unparseable_timestamp_raises():
    with pytest.raises(ValueError, match="timestamp"):
        _doc(published_at="whenever")


@pytest.mark.unit
def test_the_trading_date_of_a_document_uses_us_eastern_not_utc():
    """A 02:00 UTC story on the 26th is 22:00 ET on the 25th - still the 25th's
    news cycle. Bucketing on the UTC date files it under the wrong session."""
    assert _doc(published_at="2024-04-26T02:00:00Z").eastern_date == "2024-04-25"


@pytest.mark.unit
def test_documents_sort_stably_by_doc_id():
    docs = [_doc(native_id=str(i)) for i in (3, 1, 2)]
    assert [d.doc_id for d in sorted(docs)] == ["x:1", "x:2", "x:3"]


@pytest.mark.unit
def test_a_verified_fact_carries_its_source_and_detail():
    f = VerifiedFact(
        key="earnings_reported",
        value=True,
        source="alphavantage:EARNINGS",
        detail="reportedDate 2024-04-24",
    )
    assert f.as_dict() == {
        "key": "earnings_reported",
        "value": True,
        "source": "alphavantage:EARNINGS",
        "detail": "reportedDate 2024-04-24",
    }


@pytest.mark.unit
def test_a_verified_fact_without_a_source_raises():
    """An unsourced 'verified' fact is just an assertion - which is the thing
    this type exists to distinguish itself from."""
    with pytest.raises(ValueError, match="source"):
        VerifiedFact(key="earnings_reported", value=True, source="", detail="")


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2024-01-26T04:30:00Z", "2024-01-25"),
        ("2024-07-26T04:30:00Z", "2024-07-26"),
        ("2024-03-10T04:30:00Z", "2024-03-09"),
    ],
)
def test_eastern_date_observes_daylight_saving(timestamp, expected):
    assert _doc(published_at=timestamp).eastern_date == expected


def test_utc_window_bounds_include_entire_end_date_and_dst_transition():
    from portfolio_analysis.events.base import utc_bounds

    lo, hi = utc_bounds("2024-03-09", "2024-03-10")
    assert lo.isoformat() == "2024-03-09T05:00:00+00:00"
    assert hi.isoformat() == "2024-03-11T04:00:00+00:00"
