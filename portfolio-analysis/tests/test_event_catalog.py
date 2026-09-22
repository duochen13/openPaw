"""Issue #44 scope item 5: unit tests for write_event_catalog().

The catalog is what seeds chart event annotations on real data. These tests
pin the contract: N symbols in -> N catalog files out, verified dated-fact
sources only (forum/news documents must never seed annotations), and a
failing source degrades to a report line instead of blocking the catalog.
"""

import json
from dataclasses import replace

import pytest

from portfolio_analysis import collection
from portfolio_analysis.config import load_portfolio
from portfolio_analysis.events.base import VerifiedFact
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.http import (
    CachedHttp,
    ProviderError,
    RateLimitLedger,
)
from portfolio_analysis.store import Store
from tests.test_cli_detect import _bars

MACRO_YAML = """\
schema_version: 1
as_of: "2024-01-01"
series:
  FOMC:
    coverage: [["2024-01-01", "2024-12-31"]]
    events:
      - {date: "2024-04-20", release: "FOMC", url: "https://example.com/fomc"}
  CPI:
    coverage: [["2024-01-01", "2024-12-31"]]
    events:
      - {date: "2024-04-10", release: "CPI", url: "https://example.com/cpi"}
  PCE:
    coverage: [["2024-01-01", "2024-12-31"]]
    events: []
"""


class StubEdgar:
    """EdgarSource stand-in: one dated filing fact, no network."""

    name = "edgar"

    def collect(self, ticker, start, end):
        facts = [
            VerifiedFact(
                key="filing",
                value={"form": "10-Q", "filed": "2024-04-25",
                       "url": "https://www.sec.gov/ixviewer/test"},
                source="https://www.sec.gov/cgi-bin/test",
                detail="10-Q filed 2024-04-25",
            )
        ]
        return [], facts


@pytest.fixture
def harness(tmp_path, monkeypatch):
    portfolio = load_portfolio()
    paths = {
        **portfolio.paths,
        "db": str(tmp_path / "prices.sqlite"),
        "events": str(tmp_path / "events"),
        "cache": str(tmp_path / "cache"),
    }
    portfolio = replace(portfolio, paths=paths)
    store = Store.open(portfolio.path("db"))
    bars = {f"2024-04-{d:02d}": 100.0 + d for d in range(1, 30)}
    store.upsert_price_bars(_bars("QQQ", bars))
    store.upsert_price_bars(_bars("META", bars))
    store.upsert_price_bars(_bars("NOW", bars))
    store.close()
    macro_path = tmp_path / "macro_calendar.yaml"
    macro_path.write_text(MACRO_YAML)
    (tmp_path / "fomc_decisions.yaml").write_text("schema_version: 1\n")
    monkeypatch.setattr(
        collection, "EdgarSource", lambda *a, **k: StubEdgar()
    )
    http = CachedHttp(
        portfolio.path("cache"), ledger=RateLimitLedger(portfolio.path("cache") / "quota.json")
    )
    macro = MacroSource(macro_path)
    return portfolio, http, macro


def _run(portfolio, http, macro, symbols, capsys, api_key=""):
    lines: list[str] = []
    collection.write_event_catalog(
        portfolio=portfolio,
        symbols=symbols,
        db=portfolio.path("db"),
        events_dir=portfolio.path("events"),
        http=http,
        macro=macro,
        api_key=api_key,
        report=lines.append,
    )
    return lines


def _catalog(portfolio, symbol):
    return json.loads(
        (portfolio.path("events") / symbol / "event_dates.json").read_text()
    )


def test_one_catalog_per_symbol_with_verified_facts(harness, capsys):
    portfolio, http, macro = harness
    lines = _run(portfolio, http, macro, ["META", "NOW"], capsys)
    for symbol in ("META", "NOW"):
        payload = _catalog(portfolio, symbol)
        assert payload["schema_version"] == 1
        assert payload["ticker"] == symbol
        assert payload["dates"]["2024-04-25"] == [
            {
                "kind": "filing",
                "label": "10-Q filing",
                "date": "2024-04-25",
                "detail": "10-Q filed 2024-04-25",
                "url": "https://www.sec.gov/ixviewer/test",
            }
        ]
        # Macro facts land alongside filings.
        assert payload["dates"]["2024-04-20"][0]["kind"] == "macro"
    assert any("META: " in line and "dated events catalogued" in line for line in lines)


def test_forum_and_news_sources_never_seed_annotations(harness, capsys, monkeypatch):
    """Even if forum/news sources were constructed, catalog rows must only
    ever carry dated-fact kinds (earnings/filing/macro)."""
    portfolio, http, macro = harness

    def boom(*a, **k):
        raise AssertionError("forum/news sources must not be constructed")

    monkeypatch.setattr(collection, "HackerNewsSource", boom)
    monkeypatch.setattr(collection, "NewsSource", boom)
    # RedditSource is not imported by collection; guard the module attr anyway.
    monkeypatch.setattr(collection, "RedditSource", boom, raising=False)
    _run(portfolio, http, macro, ["META"], capsys)
    payload = _catalog(portfolio, "META")
    kinds = {row["kind"] for rows in payload["dates"].values() for row in rows}
    assert kinds <= {"earnings", "filing", "macro"}, kinds
    for rows in payload["dates"].values():
        for row in rows:
            blob = json.dumps(row).lower()
            assert "reddit" not in blob and "hackernews" not in blob


def test_failing_source_degrades_to_report_line(harness, capsys):
    portfolio, http, macro = harness

    class BrokenEdgar:
        name = "edgar"

        def collect(self, ticker, start, end):
            raise ProviderError("boom")

    import portfolio_analysis.collection as coll

    coll_edgar = coll.EdgarSource
    try:
        coll.EdgarSource = lambda *a, **k: BrokenEdgar()
        lines = _run(portfolio, http, macro, ["META"], capsys)
    finally:
        coll.EdgarSource = coll_edgar
    payload = _catalog(portfolio, "META")
    # Macro facts still catalogued; the filing is absent, not fatal.
    assert "2024-04-20" in payload["dates"]
    assert "2024-04-25" not in payload["dates"]
    assert any("skipped" in line and "edgar" in line for line in lines)
