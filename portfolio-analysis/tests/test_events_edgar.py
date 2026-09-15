import pytest

from portfolio_analysis.events.edgar import EdgarSource

# `recent` holds only new filings; the anchor 8-K is in the archive, exactly
# as measured against live EDGAR on 2026-09-14.
INDEX = {
    "filings": {
        "recent": {
            "accessionNumber": ["0001628280-26-050596"],
            "filingDate": ["2026-07-29"],
            "form": ["8-K"],
            "primaryDocument": ["a.htm"],
        },
        "files": [{"name": "CIK0001326801-submissions-001.json"}],
    }
}
ARCHIVE = {
    "accessionNumber": [
        "0001326801-24-000049",
        "0000950103-24-005771",
        "0001326801-24-000044",
    ],
    "filingDate": ["2024-04-25", "2024-04-25", "2024-04-24"],
    "form": ["10-Q", "4", "8-K"],
    "primaryDocument": ["q.htm", "f.htm", "k.htm"],
}


def _source(index=INDEX, archive=ARCHIVE):
    def fake(provider, url, *, daily_limit, max_age=None):
        return archive if "submissions-001" in url else index

    return EdgarSource(get_json=fake)


def _collect(start="2024-04-23", end="2024-04-26", **kw):
    return _source(**kw).collect("META", start, end, cik=1326801)


@pytest.mark.unit
def test_archive_files_are_fetched_not_just_recent():
    """filings.recent holds only the last 1000 filings - for META it begins at
    2024-06-11. An adapter reading only `recent` reports 'no filing' for two
    thirds of the window, silently, as an absence rather than an error."""
    _, facts = _collect()
    assert any("0001326801-24-000044" in f.detail for f in facts)


@pytest.mark.unit
def test_only_filings_inside_the_window_are_returned():
    _, facts = _collect()
    assert all("2026-" not in f.detail for f in facts)


@pytest.mark.unit
def test_form_4_insider_noise_is_excluded():
    """META filed 547 Form 4s and 371 Form 144s in two years. None is a
    catalyst, and including them buries the two filings that matter."""
    _, facts = _collect()
    assert not any("0000950103-24-005771" in f.detail for f in facts)


@pytest.mark.unit
def test_both_the_8k_and_the_10q_are_captured():
    _, facts = _collect()
    assert {f.value["form"] for f in facts} == {"8-K", "10-Q"}


@pytest.mark.unit
def test_a_filing_fact_carries_an_accession_and_a_url():
    _, facts = _collect()
    eight_k = next(f for f in facts if f.value["form"] == "8-K")
    assert eight_k.value["accession"] == "0001326801-24-000044"
    assert eight_k.value["url"] == (
        "https://www.sec.gov/Archives/edgar/data/1326801/000132680124000044/k.htm"
    )
    assert eight_k.source == "edgar:CIK0001326801"


@pytest.mark.unit
def test_facts_are_ordered_by_filing_date():
    _, facts = _collect()
    assert [f.value["filed"] for f in facts] == ["2024-04-24", "2024-04-25"]


@pytest.mark.unit
def test_edgar_yields_facts_not_documents():
    """A filing either exists with an accession number or it does not. It is
    never a 'reported claim'."""
    docs, facts = _collect()
    assert docs == []
    assert facts


@pytest.mark.unit
def test_an_index_with_no_archive_files_still_works():
    index = {"filings": {"recent": INDEX["filings"]["recent"], "files": []}}
    _, facts = _collect("2026-07-28", "2026-07-30", index=index)
    assert len(facts) == 1


@pytest.mark.unit
def test_a_window_with_no_filings_returns_empty_rather_than_raising():
    _, facts = _collect("2024-03-01", "2024-03-04")
    assert facts == []


def test_malformed_edgar_page_is_not_no_filings():
    from portfolio_analysis.http import ProviderError

    with pytest.raises(ProviderError):
        _collect(archive={})


def test_duplicate_accession_in_archive_and_recent_is_emitted_once():
    index = {"filings": {"recent": ARCHIVE, "files": INDEX["filings"]["files"]}}
    _, facts = _collect(index=index)
    assert len(facts) == 2
