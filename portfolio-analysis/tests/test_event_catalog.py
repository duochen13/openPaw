"""Dedicated unit tests for write_event_catalog (issue #44).

Contract under test:
- N symbols in -> N ``events_dir/<TICKER>/event_dates.json`` catalogs out.
- Only verified dated-fact sources (EDGAR filings, macro releases,
  earnings when keyed) may seed chart annotations; forum/news chatter
  (HN, Reddit, news documents) never does.
- A failing source degrades to a report line; the catalog still writes
  whatever the other sources found.
"""

import json
from types import SimpleNamespace

import pytest

from portfolio_analysis import collection
from portfolio_analysis.config import load_portfolio
from portfolio_analysis.events.base import VerifiedFact
from portfolio_analysis.http import ProviderError
from portfolio_analysis.render import _event_catalog_info
from portfolio_analysis.store import Store
from tests.test_cli_detect import _bars
from tests.test_render import artifact
from tests.test_render import data as chart_page_data

SYMBOLS = ["META", "NOW"]

FILING = {
    "META": [
        VerifiedFact(
            key="filing",
            value={"form": "8-K", "filed": "2024-04-24", "url": "https://sec.gov/x"},
            source="edgar",
            detail="",
        ),
        # Duplicate of the same fact: catalog must dedupe to one row.
        VerifiedFact(
            key="filing",
            value={"form": "8-K", "filed": "2024-04-24", "url": "https://sec.gov/x"},
            source="edgar",
            detail="",
        ),
        # Outside the price window: must be excluded.
        VerifiedFact(
            key="filing",
            value={"form": "10-Q", "filed": "2024-04-21", "url": "https://sec.gov/y"},
            source="edgar",
            detail="",
        ),
    ],
    "NOW": [
        VerifiedFact(
            key="filing",
            value={"form": "8-K", "filed": "2024-04-25", "url": "https://sec.gov/z"},
            source="edgar",
            detail="",
        ),
    ],
}

MACRO = {
    "META": [
        VerifiedFact(
            key="macro_release",
            value={"release": "CPI", "date": "2024-04-24"},
            source="fred",
            detail="",
        )
    ],
    "NOW": [],
}


class _StubSource:
    """Duck-typed EventSource returning canned facts per ticker."""

    def __init__(self, facts_by_ticker, name, fail=None):
        self.facts_by_ticker = facts_by_ticker
        self.name = name
        self.fail = fail
        self.calls = []

    def collect(self, ticker, start, end):
        self.calls.append((ticker, start, end))
        if self.fail is not None:
            raise self.fail
        return [], list(self.facts_by_ticker.get(ticker, []))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Seed a benchmark price window and stub the event sources."""
    portfolio = load_portfolio()
    db = tmp_path / "prices.sqlite"
    store = Store.open(db)
    store.upsert_price_bars(
        _bars(
            "QQQ",
            {
                "2024-04-22": 100.0,
                "2024-04-23": 101.0,
                "2024-04-24": 102.0,
                "2024-04-25": 101.0,
                "2024-04-26": 103.0,
            },
        )
    )
    store.close()
    events_dir = tmp_path / "events"

    edgar = _StubSource(FILING, "edgar")
    macro = _StubSource(MACRO, "macro")
    earnings = _StubSource(
        {
            "META": [
                VerifiedFact(
                    key="earnings_reported",
                    value={"reportedDate": "2024-04-24"},
                    source="alphavantage",
                    detail="",
                )
            ]
        },
        "earnings",
    )

    def edgar_factory(get_json, cik=None):
        edgar.cik_seen = cik
        return edgar

    def earnings_factory(get_json, api_key=None):
        earnings.api_key_seen = api_key
        return earnings

    monkeypatch.setattr(collection, "EdgarSource", edgar_factory)
    monkeypatch.setattr(collection, "EarningsSource", earnings_factory)

    def run(*, api_key="", symbols=SYMBOLS):
        reports = []
        http = SimpleNamespace(get_json=lambda *a, **k: {})
        collection.write_event_catalog(
            portfolio=portfolio,
            symbols=symbols,
            db=db,
            events_dir=events_dir,
            http=http,
            macro=macro,
            api_key=api_key,
            report=reports.append,
        )
        return reports

    return {
        "run": run,
        "events_dir": events_dir,
        "edgar": edgar,
        "macro": macro,
        "earnings": earnings,
    }


def _read(setup, ticker):
    path = setup["events_dir"] / ticker / "event_dates.json"
    return json.loads(path.read_text())


def test_n_symbols_write_n_catalog_files(setup):
    setup["run"]()
    for ticker in SYMBOLS:
        payload = _read(setup, ticker)
        assert payload["schema_version"] == 1
        assert payload["ticker"] == ticker
        assert payload["window"] == ["2024-04-22", "2024-04-26"]
        assert payload["sources"] == ["edgar", "macro"]
    meta = _read(setup, "META")["dates"]
    assert set(meta) == {"2024-04-24"}
    # Duplicate filing deduped; both sources land on the same day.
    assert [row["kind"] for row in meta["2024-04-24"]] == ["filing", "macro"]
    assert [row["label"] for row in meta["2024-04-24"]] == ["8-K filing", "CPI release"]
    # Out-of-window filing excluded.
    assert all("10-Q" not in row["label"] for rows in meta.values() for row in rows)
    now = _read(setup, "NOW")["dates"]
    assert set(now) == {"2024-04-25"}


def test_forum_and_news_sources_never_seed_annotations(setup, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("forum/news source must not be constructed")

    monkeypatch.setattr(collection, "HackerNewsSource", explode)
    monkeypatch.setattr(collection, "NewsSource", explode)
    setup["run"]()  # must not raise
    for ticker in SYMBOLS:
        kinds = {row["kind"] for rows in _read(setup, ticker)["dates"].values() for row in rows}
        assert kinds <= {"filing", "earnings", "macro"}


def test_failing_source_degrades_to_report_line(setup):
    setup["edgar"].fail = ProviderError("edgar down")
    reports = setup["run"]()
    assert any("META: event catalog skipped edgar (ProviderError)" in r for r in reports)
    # Macro facts still catalogued; nothing raises.
    assert set(_read(setup, "META")["dates"]) == {"2024-04-24"}
    assert setup["macro"].calls


def test_earnings_included_only_with_api_key(setup):
    # Keyless: earnings source never constructed.
    setup["run"](api_key="")
    assert getattr(setup["earnings"], "api_key_seen", None) is None
    assert _read(setup, "META")["sources"] == ["edgar", "macro"]

    # Keyed: earnings seeds the catalog alongside filings and macro.
    setup["run"](api_key="secret")
    assert setup["earnings"].api_key_seen == "secret"
    payload = _read(setup, "META")
    assert payload["sources"] == ["edgar", "macro", "earnings"]
    labels = [row["label"] for rows in payload["dates"].values() for row in rows]
    assert "Quarterly earnings reported" in labels


def test_event_catalog_info_absent_and_present(setup, tmp_path):
    info = _event_catalog_info(setup["events_dir"], "META")
    assert info == {
        "present": False,
        "generated_at": None,
        "dated_days": 0,
        "sources": [],
        "window": None,
    }
    setup["run"]()
    info = _event_catalog_info(setup["events_dir"], "META")
    assert info["present"] is True
    assert info["dated_days"] == 1
    assert info["sources"] == ["edgar", "macro"]
    assert info["generated_at"]
    assert info["window"] == ["2024-04-22", "2024-04-26"]


def test_event_catalog_info_rejects_wrong_ticker(tmp_path):
    path = tmp_path / "META" / "event_dates.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ticker": "NOW",  # mismatched ticker
                "generated_at": "2026-09-21T00:00:00+00:00",
                "window": ["2024-04-22", "2024-04-26"],
                "sources": ["edgar"],
                "dates": {"2024-04-24": []},
            }
        )
    )
    assert _event_catalog_info(tmp_path, "META")["present"] is False


def test_chart_page_carries_event_catalog_coverage(tmp_path):
    page = chart_page_data(tmp_path, artifact())
    assert page["event_catalog"]["present"] is False
