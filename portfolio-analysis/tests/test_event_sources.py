from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from portfolio_analysis.config import PROJECT_ROOT
from portfolio_analysis.events.earnings import EarningsSource
from portfolio_analysis.events.hn import HackerNewsSource
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.events.news import NewsSource
from portfolio_analysis.http import ProviderError

# Small provider-shaped fixtures: deliberate edge cases, not live recordings.
EARNINGS = {
    "quarterlyEarnings": [
        {
            "reportedDate": "2024-04-24",
            "fiscalDateEnding": "2024-03-31",
            "reportTime": "post-market",
            "reportedEPS": "4.71",
            "estimatedEPS": "4.32",
            "surprise": "0.39",
            "surprisePercentage": "9.0278",
        },
        {"reportedDate": "None"},
        {"reportedDate": "2024-07-31", "fiscalDateEnding": "2024-06-30"},
    ]
}
NEWS = {
    "feed": [
        {
            "url": "https://example.com/story",
            "title": "Meta earnings",
            "time_published": "20240426T020000",
            "summary": "Higher spending guidance",
            "ticker_sentiment": [
                {"ticker": "NVDA", "relevance_score": "0.99"},
                {"ticker": "META", "relevance_score": "0.71"},
            ],
        },
    ]
}


def test_earnings_keeps_report_date_and_consensus_caveat():
    docs, facts = EarningsSource(lambda *a, **kw: EARNINGS, api_key="x").collect(
        "META", "2024-04-24", "2024-04-24"
    )
    assert docs == []
    assert len(facts) == 1
    assert facts[0].value["reportedDate"] == "2024-04-24"
    assert facts[0].value["reportTime"] == "post-market"
    assert facts[0].value["estimatedEPS"] == 4.32
    assert "vintage unknown" in facts[0].detail


def test_earnings_missing_numbers_stay_unknown():
    payload = deepcopy(EARNINGS)
    payload["quarterlyEarnings"][0]["estimatedEPS"] = "None"
    _, facts = EarningsSource(lambda *a, **kw: payload, api_key="x").collect(
        "META", "2024-04-23", "2024-04-26"
    )
    assert facts[0].value["estimatedEPS"] is None


def test_news_uses_requested_ticker_and_eastern_day():
    docs, facts = NewsSource(lambda *a, **kw: NEWS, api_key="x").collect(
        "META", "2024-04-25", "2024-04-25"
    )
    assert facts == []
    assert len(docs) == 1
    assert docs[0].relevance == 0.71
    assert docs[0].eastern_date == "2024-04-25"


def test_news_query_and_filter_cover_both_eastern_boundaries():
    urls = []
    payload = deepcopy(NEWS)
    payload["feed"] = []
    for i, stamp in enumerate(
        ["20240123T045959", "20240123T050000", "20240127T045959", "20240127T050000"]
    ):
        payload["feed"].append(
            {**NEWS["feed"][0], "url": f"https://x/{i}", "time_published": stamp}
        )

    def fetch(provider, url, **kw):
        urls.append(url)
        return payload

    docs, _ = NewsSource(fetch, api_key="x").collect("META", "2024-01-23", "2024-01-26")
    query = parse_qs(urlsplit(urls[0]).query)
    assert query["time_from"] == ["20240123T0500"]
    assert query["time_to"] == ["20240127T0500"]
    assert {doc.url for doc in docs} == {"https://x/1", "https://x/2"}


def test_news_deduplicates_repeated_urls():
    payload = {"feed": NEWS["feed"] * 2}
    docs, _ = NewsSource(lambda *a, **kw: payload, api_key="x").collect(
        "META", "2024-04-23", "2024-04-26"
    )
    assert len(docs) == 1


def test_saturated_news_window_is_not_complete():
    with pytest.raises(ProviderError, match="limit"):
        NewsSource(lambda *a, **kw: {"feed": NEWS["feed"] * 1000}, api_key="x").collect(
            "META", "2024-04-23", "2024-04-26"
        )


@pytest.mark.parametrize("source", [EarningsSource, NewsSource])
def test_malformed_response_is_not_empty_success(source):
    with pytest.raises(ProviderError):
        source(lambda *a, **kw: {}, api_key="x").collect("META", "2024-04-23", "2024-04-26")


def test_hn_paginates_and_falls_back_to_story_title():
    pages = []

    def fetch(provider, url, **kw):
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        pages.append(page)
        return {
            "nbPages": 2,
            "hits": [
                {
                    "objectID": str(page),
                    "title": None,
                    "story_title": "Meta earnings",
                    "created_at": "2024-04-25T12:00:00Z",
                    "url": None,
                },
            ],
        }

    docs, facts = HackerNewsSource(fetch, query="Meta").collect("META", "2024-04-23", "2024-04-26")
    assert pages == [0, 1]
    assert len(docs) == 2
    assert all(doc.title == "Meta earnings" for doc in docs)
    assert docs[0].url == "https://news.ycombinator.com/item?id=0"
    assert facts == []


def test_hn_reports_incomplete_pagination():
    with pytest.raises(ProviderError, match="pagination"):
        HackerNewsSource(lambda *a, **kw: {"nbPages": 2, "hits": []}, query="Meta").collect(
            "META", "2024-04-23", "2024-04-26"
        )


def test_macro_anchor_and_unknown_coverage_are_distinct():
    macro = MacroSource(PROJECT_ROOT / "config/macro_calendar.yaml")
    docs, facts = macro.collect("META", "2024-04-23", "2024-04-26")
    assert docs == []
    assert [(fact.value["release"], fact.value["date"]) for fact in facts] == [
        ("PCE", "2024-04-26")
    ]
    assert all(macro.coverage("2024-04-23", "2024-04-26").values())
    assert not any(macro.coverage("2030-01-01", "2030-01-04").values())


def test_macro_calendar_contains_actual_shutdown_rescheduled_dates():
    macro = MacroSource(PROJECT_ROOT / "config/macro_calendar.yaml")
    _, facts = macro.collect("META", "2025-10-01", "2025-12-31")
    dates = {(f.value["release"], f.value["date"]) for f in facts}
    assert ("CPI", "2025-10-24") in dates
    assert ("PCE", "2025-12-05") in dates
    assert ("PCE", "2025-10-31") not in dates
    assert ("PCE", "2025-12-23") in dates


def test_macro_entries_have_valid_dates_and_no_duplicates():
    data = yaml.safe_load((PROJECT_ROOT / "config/macro_calendar.yaml").read_text())
    for series in data["series"].values():
        dates = [e["date"] for e in series["events"]]
        assert dates == sorted(set(dates))
        assert all(e["url"].startswith("https://") for e in series["events"])


def test_hn_approximate_hit_count_retains_documents_with_coverage_marker():
    source = HackerNewsSource(
        lambda *a, **kw: {
            "nbPages": 1,
            "exhaustiveNbHits": False,
            "hits": [
                {"objectID": "1", "created_at": "2024-04-25T12:00:00Z", "title": "Meta"},
            ],
        },
        query="Meta",
    )
    docs, _ = source.collect("META", "2024-04-23", "2024-04-26")
    assert len(docs) == 1
    assert source.coverage_status == "approximate_hit_count"


def test_hn_searches_old_company_alias_and_deduplicates():
    queries = []

    def fetch(provider, url, **kw):
        queries.append(parse_qs(urlsplit(url).query)["query"][0])
        return {
            "nbPages": 1,
            "hits": [
                {"objectID": "1", "created_at": "2024-04-25T12:00:00Z", "title": "Meta"},
            ],
        }

    docs, _ = HackerNewsSource(fetch, query="Meta", aliases=("Facebook", "Meta")).collect(
        "META", "2024-04-23", "2024-04-26"
    )
    assert queries == ["Meta", "Facebook"]
    assert len(docs) == 1


def test_conflicting_news_duplicate_is_not_order_dependent():
    payload = deepcopy(NEWS)
    payload["feed"].append({**payload["feed"][0], "summary": "conflicting version"})
    with pytest.raises(ProviderError, match="conflicting"):
        NewsSource(lambda *a, **kw: payload, api_key="x").collect(
            "META", "2024-04-23", "2024-04-26"
        )
