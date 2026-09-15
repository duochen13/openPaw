import json
from dataclasses import replace

import pytest

from portfolio_analysis import cli, collection
from portfolio_analysis.artifacts import MovesArtifact, write_moves
from portfolio_analysis.config import load_portfolio
from portfolio_analysis.events.base import Document
from portfolio_analysis.http import CachedHttp, QuotaExhausted, RateLimitLedger
from portfolio_analysis.moves import Coverage
from portfolio_analysis.store import Store
from tests.test_bundle import MOVE
from tests.test_cli_detect import _bars


@pytest.fixture
def setup(tmp_path, monkeypatch):
    portfolio = load_portfolio()
    paths = {
        **portfolio.paths,
        "db": str(tmp_path / "prices.sqlite"),
        "moves": str(tmp_path / "moves"),
        "events": str(tmp_path / "events"),
        "cache": str(tmp_path / "cache"),
    }
    portfolio = replace(portfolio, paths=paths)
    monkeypatch.setattr(cli, "load_portfolio", lambda: portfolio)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    store = Store.open(portfolio.path("db"))
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
    write_moves(
        portfolio.path("moves"),
        MovesArtifact(
            "META",
            "QQQ",
            portfolio.move_params,
            Coverage(None, None, 2, 2),
            [replace(MOVE, date="2024-04-24"), MOVE],
        ),
    )
    return portfolio


def test_cli_resume_does_not_recollect_finished_moves(setup, monkeypatch, capsys):
    calls = []

    class Source:
        name = "test"

        def collect(self, ticker, start, end):
            calls.append(end)
            return [], []

    monkeypatch.setattr(collection, "event_sources", lambda *a: [Source()])
    assert cli.main(["collect-events", "META"]) == 0
    assert len(calls) == 2
    assert cli.main(["collect-events", "META"]) == 0
    assert len(calls) == 2
    assert "2 completed, 0 remaining" in capsys.readouterr().out
    payload = json.loads((setup.path("events") / "META/2024-04-25.json").read_text())
    assert payload["coverage"]["source_status"]["earnings"] == "missing_api_key"


def test_cli_quota_exhaustion_keeps_completed_bundle_and_exits_zero(setup, monkeypatch, capsys):
    class Source:
        name = "test"

        def collect(self, ticker, start, end):
            if end == "2024-04-26":
                raise QuotaExhausted("spent")
            return [], []

    monkeypatch.setattr(collection, "event_sources", lambda *a: [Source()])
    assert cli.main(["collect-events", "META"]) == 0
    assert "1 completed, 1 remaining" in capsys.readouterr().out
    assert (setup.path("events") / "META/2024-04-24.json").exists()
    assert not (setup.path("events") / "META/2024-04-25.json").exists()


def test_interrupted_move_reuses_prior_source_response(setup, monkeypatch):
    calls = []
    interrupted = [True]
    http = CachedHttp(
        setup.path("cache"),
        ledger=RateLimitLedger(setup.path("cache") / "quota.json"),
        fetch=lambda url: calls.append(url) or {"ok": True},
        sleep=lambda _: None,
    )

    class Source:
        name = "test"

        def collect(self, ticker, start, end):
            http.get_json("av", "https://x/one", daily_limit=25)
            if interrupted[0]:
                raise KeyboardInterrupt
            http.get_json("av", "https://x/two", daily_limit=25)
            return [], []

    monkeypatch.setattr(collection, "event_sources", lambda *a: [Source()])
    with pytest.raises(KeyboardInterrupt):
        cli.main(["collect-events", "META", "--date", "2024-04-25"])
    interrupted[0] = False
    assert cli.main(["collect-events", "META", "--date", "2024-04-25"]) == 0
    assert calls == ["https://x/one", "https://x/two"]
    assert http.ledger.spent_today("av") == 2


def test_new_key_completes_previously_keyless_bundle(setup, monkeypatch):
    credentials = []

    def sources(http, entry, macro, key):
        credentials.append(bool(key))

        class Source:
            name = "with_key" if key else "without_key"

            def collect(self, *args):
                return [], []

        return [Source()]

    monkeypatch.setattr(collection, "event_sources", sources)
    assert cli.main(["collect-events", "META", "--date", "2024-04-25"]) == 0
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "fake")
    assert cli.main(["collect-events", "META", "--date", "2024-04-25"]) == 0
    assert credentials == [False, True]
    payload = json.loads((setup.path("events") / "META/2024-04-25.json").read_text())
    assert "missing_api_key" not in payload["coverage"]["source_status"].values()


def test_last_session_is_deferred_without_fetch(setup, monkeypatch, capsys):
    write_moves(
        setup.path("moves"),
        MovesArtifact(
            "META",
            "QQQ",
            setup.move_params,
            Coverage(None, None, 1, 1),
            [replace(MOVE, date="2024-04-26")],
        ),
    )
    monkeypatch.setattr(collection, "event_sources", lambda *a: pytest.fail("unfinished window"))
    assert cli.main(["collect-events", "META"]) == 0
    assert "1 awaiting sessions" in capsys.readouterr().out


def test_provider_error_does_not_publish_empty_bundle(setup, monkeypatch, capsys):
    class Source:
        name = "broken"

        def collect(self, *args):
            raise KeyError("SECRET")

    monkeypatch.setattr(collection, "event_sources", lambda *a: [Source()])
    assert cli.main(["collect-events", "META"]) == 1
    assert "SECRET" not in capsys.readouterr().err
    assert not list(setup.path("events").glob("META/*.json"))


def test_unknown_ticker_and_date_fail_clearly(setup):
    assert cli.main(["collect-events", "ZZZZ"]) == 2
    assert cli.main(["collect-events", "META", "--date", "2001-01-01"]) == 1


def test_rebuild_reparses_without_forcing_http_refresh(setup, monkeypatch):
    calls = []

    class Source:
        name = "test"

        def collect(self, *args):
            calls.append(1)
            return [
                Document.make(
                    source="test",
                    native_id="1",
                    published_at="2024-04-25T12:00:00Z",
                    title=str(len(calls)),
                    url="https://example.com",
                )
            ], []

    monkeypatch.setattr(collection, "event_sources", lambda *a: [Source()])
    assert cli.main(["collect-events", "META", "--date", "2024-04-25"]) == 0
    assert cli.main(["collect-events", "META", "--date", "2024-04-25", "--rebuild"]) == 0
    assert len(calls) == 2
