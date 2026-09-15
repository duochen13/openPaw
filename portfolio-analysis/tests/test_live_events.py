"""Live acceptance anchors; cached responses minimize repeat provider traffic."""

import os

import pytest

from portfolio_analysis.config import PROJECT_ROOT
from portfolio_analysis.events.earnings import EarningsSource
from portfolio_analysis.events.edgar import EdgarSource
from portfolio_analysis.events.hn import HackerNewsSource
from portfolio_analysis.events.news import NewsSource
from portfolio_analysis.http import CachedHttp, QuotaExhausted, RateLimitLedger

pytestmark = pytest.mark.network


@pytest.fixture
def http():
    root = PROJECT_ROOT / "data/cache"
    return CachedHttp(root, ledger=RateLimitLedger(root / "quota.json"))


@pytest.mark.parametrize(
    "start,end,accessions",
    [
        ("2024-04-23", "2024-04-26", {"0001326801-24-000044", "0001326801-24-000049"}),
        ("2022-02-01", "2022-02-04", {"0001326801-22-000015", "0001326801-22-000018"}),
    ],
)
def test_live_edgar_includes_archived_anchor_filings(http, start, end, accessions):
    _, facts = EdgarSource(http.get_json, cik=1326801).collect("META", start, end)
    assert accessions <= {fact.value["accession"] for fact in facts}


def test_live_hn_anchor_has_dated_documents(http):
    docs, _ = HackerNewsSource(http.get_json, query="Meta").collect(
        "META", "2024-04-23", "2024-04-26"
    )
    assert docs
    assert all("2024-04-23" <= doc.eastern_date <= "2024-04-26" for doc in docs)


def test_live_alpha_vantage_anchor(http):
    key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not key:
        pytest.skip("ALPHAVANTAGE_API_KEY is unset")
    try:
        _, facts = EarningsSource(http.get_json, api_key=key).collect(
            "META", "2024-04-23", "2024-04-26"
        )
        docs, _ = NewsSource(http.get_json, api_key=key).collect("META", "2024-04-23", "2024-04-26")
    except QuotaExhausted:
        pytest.skip("Alpha Vantage quota exhausted; rerun after reset")
    assert any(f.value["reportedDate"] == "2024-04-24" for f in facts)
    assert docs
