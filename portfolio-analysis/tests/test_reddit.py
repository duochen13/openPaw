"""Offline tests for issue #7: ranked Reddit commentary.

Covers ranking (score order, recency tie-break), deduplication, the hard
five-comment cap, deleted/empty filtering, explicit no-results/error states,
resumable collection, structured event context, and safe HTML rendering.
Nothing here touches the network.
"""

import argparse
import json

import pytest
import yaml

from portfolio_analysis import event_dashboard as ed
from portfolio_analysis.config import MoveParams, Portfolio, PortfolioEntry
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.events.reddit import (
    MAX_COMMENTS,
    REDDIT_BASE,
    RedditCollectionResult,
    RedditComment,
    collect_reddit_for_events,
    fetch_event_comments,
    rank_reddit_comments,
)
from portfolio_analysis.http import ProviderError, QuotaExhausted
from portfolio_analysis.store import Store


def _comment(
    cid: str,
    score: int,
    ts: int,
    body: str = "fomc was widely expected",
    subreddit: str = "economics",
    author: str = "someone",
) -> RedditComment:
    return RedditComment(
        comment_id=cid,
        score=score,
        author=author,
        created_utc=ts,
        subreddit=subreddit,
        permalink=f"/r/{subreddit}/comments/xyz/{cid}/",
        body=body,
    )


def _row(
    cid: str,
    body: str,
    score: int = 5,
    ts: int = 1700000000,
    subreddit: str = "economics",
) -> dict:
    return {
        "id": cid,
        "body": body,
        "score": score,
        "author": "trader",
        "created_utc": ts,
        "subreddit": subreddit,
        "permalink": f"/r/{subreddit}/comments/abc/{cid}/",
        "link_id": "t3_abc",
    }


# --- ranking: score order, recency tie-break, dedup, cap, filtering ---


@pytest.mark.unit
def test_rank_orders_by_score_with_recency_tiebreak():
    comments = [_comment("a", 5, 100), _comment("b", 10, 100), _comment("c", 10, 200)]
    ranked = rank_reddit_comments(comments)
    assert [c.comment_id for c in ranked] == ["c", "b", "a"]


@pytest.mark.unit
def test_rank_dedups_by_id_keeping_highest_score():
    comments = [_comment("a", 3, 100), _comment("a", 9, 50), _comment("b", 5, 100)]
    ranked = rank_reddit_comments(comments)
    assert [c.comment_id for c in ranked] == ["a", "b"]
    assert ranked[0].score == 9


@pytest.mark.unit
def test_rank_enforces_hard_five_comment_cap():
    comments = [_comment(f"c{i}", score=i, ts=1000 + i) for i in range(8)]
    ranked = rank_reddit_comments(comments)
    assert len(ranked) == MAX_COMMENTS == 5
    assert [c.score for c in ranked] == [7, 6, 5, 4, 3]


@pytest.mark.unit
@pytest.mark.parametrize("body", ["[deleted]", "[removed]", "", "   "])
def test_rank_drops_deleted_and_empty_bodies(body):
    ranked = rank_reddit_comments(
        [_comment("a", 10, 100, body=body), _comment("b", 1, 100)]
    )
    assert [c.comment_id for c in ranked] == ["b"]


@pytest.mark.unit
def test_excerpt_truncates_at_word_boundary():
    excerpt = _comment("a", 1, 1, body="word " * 100).excerpt(20)
    assert excerpt == "word word word word\u2026"
    assert _comment("a", 1, 1, body="short take").excerpt() == "short take"


@pytest.mark.unit
def test_url_falls_back_when_permalink_is_not_a_path():
    weird = RedditComment(
        comment_id="a",
        score=1,
        author="u",
        created_utc=1,
        subreddit="s",
        permalink="javascript:alert(1)",
        body="fomc",
    )
    assert weird.url == REDDIT_BASE
    good = _comment("b", 1, 1)
    assert good.url == REDDIT_BASE + "/r/economics/comments/xyz/b/"


# --- fetch_event_comments: query shape, keyword filter, explicit states ---


@pytest.mark.unit
def test_fetch_builds_subreddit_scoped_body_query_for_event_window():
    seen = []

    def get_json(provider, url, *, daily_limit, max_age=None):
        seen.append((provider, url))
        return {"data": []}

    comments, status = fetch_event_comments(
        get_json, "FOMC", "2024-01-31", daily_limit=400
    )
    assert (comments, status) == ([], "no_results")
    # One `body` keyword request per subreddit: economics + investing.
    assert len(seen) == 2
    for provider, url in seen:
        assert provider == "arctic_shift"
        assert "body=fomc" in url
        assert "subreddit=" in url
        # Event window is event date -1 day through +2 days.
        assert "after=2024-01-30" in url
        assert "before=2024-02-02" in url


@pytest.mark.unit
def test_fetch_ranks_comments_and_filters_server_keyword_misses():
    rows = [
        _row("a", "cpi came in hot, shelter sticky", score=10, ts=1700000001),
        _row("b", "random market chat with no keyword", score=99),
        _row("c", "cpi", score=1, ts=1700000000),
    ]

    def get_json(provider, url, *, daily_limit, max_age=None):
        return {"data": rows}

    comments, status = fetch_event_comments(
        get_json, "CPI", "2024-01-11", daily_limit=400
    )
    assert status == "ok"
    assert [c.comment_id for c in comments] == ["a", "c"]


@pytest.mark.unit
def test_fetch_unknown_event_type_is_no_results_without_requests():
    def get_json(*args, **kwargs):
        raise AssertionError("no requests expected")

    comments, status = fetch_event_comments(
        get_json, "NFP", "2024-01-05", daily_limit=400
    )
    assert (comments, status) == ([], "no_results")


@pytest.mark.unit
def test_fetch_provider_error_becomes_explicit_status():
    def get_json(provider, url, *, daily_limit, max_age=None):
        raise ProviderError("arctic_shift: boom")

    comments, status = fetch_event_comments(
        get_json, "FOMC", "2024-01-31", daily_limit=400
    )
    assert comments == []
    assert status == "error: ProviderError"


# --- collect_reddit_for_events: resumability ---


class _StubCalendar:
    def __init__(self, events):
        self._events = events

    def catalog(self):
        catalog = {}
        for kind, event_date in self._events:
            catalog.setdefault(kind, []).append({"date": event_date})
        return catalog


class _FakeHttp:
    def __init__(self, rows=(), quota_after=None):
        self.calls = 0
        self._rows = list(rows)
        self._quota_after = quota_after

    def get_json(self, provider, url, *, daily_limit, max_age=None):
        if self._quota_after is not None and self.calls >= self._quota_after:
            raise QuotaExhausted("daily budget spent")
        self.calls += 1
        return {"data": self._rows}


@pytest.mark.unit
def test_collect_skips_completed_and_retries_error_and_corrupt(tmp_path):
    reddit_dir = tmp_path / "reddit"
    reddit_dir.mkdir()
    (reddit_dir / "FOMC_2024-01-31.json").write_text(
        json.dumps({"status": "ok", "comments": []})
    )
    (reddit_dir / "CPI_2024-01-11.json").write_text(
        json.dumps({"status": "error: ProviderError", "comments": []})
    )
    (reddit_dir / "PCE_2024-01-26.json").write_text("not json{")
    rows = [_row("a", "fomc preview thread", score=7), _row("b", "cpi thread", score=3)]
    http = _FakeHttp(rows=rows)
    calendar = _StubCalendar(
        [("FOMC", "2024-01-31"), ("CPI", "2024-01-11"), ("PCE", "2024-01-26")]
    )
    result = collect_reddit_for_events(
        calendar, reddit_dir, http, daily_limit=400, report=lambda msg: None
    )
    assert result == RedditCollectionResult(
        completed=3, remaining=0, quota_exhausted=False
    )
    # Only the two unfinished events were fetched (2 subreddits each).
    assert http.calls == 4
    cpi = json.loads((reddit_dir / "CPI_2024-01-11.json").read_text())
    assert cpi["status"] == "ok"
    assert [c["comment_id"] for c in cpi["comments"]] == ["b"]
    pce = json.loads((reddit_dir / "PCE_2024-01-26.json").read_text())
    assert pce["status"] == "no_results"


@pytest.mark.unit
def test_collect_quota_exhaustion_keeps_finished_events(tmp_path):
    reddit_dir = tmp_path / "reddit"
    reddit_dir.mkdir()
    http = _FakeHttp(rows=[_row("a", "cpi thread", score=4)], quota_after=2)
    calendar = _StubCalendar([("CPI", "2024-01-11"), ("FOMC", "2024-01-31")])
    result = collect_reddit_for_events(
        calendar, reddit_dir, http, report=lambda msg: None
    )
    assert result.quota_exhausted is True
    assert result.completed == 1
    assert result.remaining == 1
    assert (reddit_dir / "CPI_2024-01-11.json").exists()
    assert not (reddit_dir / "FOMC_2024-01-31.json").exists()


@pytest.mark.unit
def test_collect_rebuild_recollects_completed_events(tmp_path):
    reddit_dir = tmp_path / "reddit"
    reddit_dir.mkdir()
    (reddit_dir / "FOMC_2024-01-31.json").write_text(
        json.dumps({"status": "ok", "comments": []})
    )
    http = _FakeHttp(rows=[_row("a", "fomc thread", score=4)])
    calendar = _StubCalendar([("FOMC", "2024-01-31")])
    result = collect_reddit_for_events(
        calendar, reddit_dir, http, rebuild=True, report=lambda msg: None
    )
    assert http.calls == 2
    assert result.completed == 1
    payload = json.loads((reddit_dir / "FOMC_2024-01-31.json").read_text())
    assert payload["status"] == "ok"
    assert len(payload["comments"]) == 1


# --- event dashboard: structured context + reddit attachment + rendering ---


def _write_calendar(tmp_path):
    calendar = {
        "schema_version": 1,
        "as_of": "2026-09-13",
        "series": {
            "FOMC": {
                "coverage": [["2024-01-01", "2024-12-31"]],
                "events": [
                    {"date": "2024-01-31", "url": "https://www.federalreserve.gov/x"}
                ],
            },
            "CPI": {
                "coverage": [["2024-01-01", "2024-12-31"]],
                "events": [{"date": "2024-01-11", "url": "https://www.bls.gov/x"}],
            },
            "PCE": {
                "coverage": [["2024-01-01", "2024-12-31"]],
                "events": [{"date": "2024-01-26", "url": "https://apps.bea.gov/x"}],
            },
        },
    }
    path = tmp_path / "macro_calendar.yaml"
    path.write_text(yaml.safe_dump(calendar))
    (tmp_path / "fomc_decisions.yaml").write_text(
        yaml.safe_dump(
            {
                "2024-01-31": {
                    "action": "hold",
                    "change_bp": 0,
                    "target_range": "5.25%-5.50%",
                    "source": "https://fred.stlouisfed.org/series/DFEDTARU",
                }
            }
        )
    )
    return path


def _portfolio():
    return Portfolio(
        entries=(PortfolioEntry(symbol="META", cik=320193, name="Meta", aliases=()),),
        benchmark="QQQ",
        price_years=6,
        move_params=MoveParams(beta_window=250, sigma_window=60, z_threshold=2.5),
        news_coverage_start="2022-03-01",
        paths={},
    )


def _bars(symbol, closes):
    return [
        {
            "ticker": symbol,
            "date": day,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "adj_close": close,
            "volume": 1000.0,
            "source": "test",
        }
        for day, close in sorted(closes.items())
    ]


@pytest.fixture
def dashboard_inputs(tmp_path):
    calendar = MacroSource(_write_calendar(tmp_path))
    portfolio = _portfolio()
    store = Store.open(":memory:")
    closes = {
        "2024-01-24": 100.0,
        "2024-01-25": 101.0,
        "2024-01-26": 102.0,
        "2024-01-29": 103.0,
        "2024-01-30": 104.0,
        "2024-01-31": 105.0,
        "2024-02-01": 106.0,
        "2024-02-02": 107.0,
    }
    store.upsert_price_bars(_bars("QQQ", closes))
    store.upsert_price_bars(_bars("META", closes))
    yield portfolio, store, calendar, tmp_path
    store.close()


def _write_reddit_file(reddit_dir, kind, event_date, status, comments):
    (reddit_dir / f"{kind}_{event_date}.json").write_text(
        json.dumps(
            {
                "event_type": kind,
                "event_date": event_date,
                "status": status,
                "comments": [c.as_dict() for c in comments],
            }
        )
    )


@pytest.mark.unit
def test_event_context_is_structured_and_source_backed(dashboard_inputs):
    portfolio, store, calendar, _tmp = dashboard_inputs
    data = ed.event_dashboard_data(portfolio, store, calendar)
    by_key = {(e["type"], e["date"]): e for e in data["events"]}
    fomc = by_key[("FOMC", "2024-01-31")]["context"]
    assert fomc["subtype"] == "FOMC"
    assert fomc["decision"]["action"] == "hold"
    assert fomc["decision"]["change_bp"] == 0
    assert fomc["decision"]["target_range"] == "5.25%-5.50%"
    assert fomc["decision"]["source"] == "https://fred.stlouisfed.org/series/DFEDTARU"
    assert fomc["affected_variable"] == "federal funds target range"
    assert fomc["source_timestamp"] == "2026-09-13"
    assert fomc["surprise"] is None
    assert "held" in fomc["summary"]
    cpi = by_key[("CPI", "2024-01-11")]["context"]
    assert cpi["subtype"] == "CPI"
    assert cpi["decision"] is None
    assert "CPI release on 2024-01-11" in cpi["summary"]
    # Existing returns and source URLs are preserved alongside context.
    impact = by_key[("FOMC", "2024-01-31")]["impact"]["QQQ"]
    assert set(impact) == {"before_1d", "after_1d", "after_5d", "after_20d"}
    assert by_key[("FOMC", "2024-01-31")]["url"] == "https://www.federalreserve.gov/x"


@pytest.mark.unit
def test_reddit_attach_enforces_cap_after_dedup_and_keeps_status(dashboard_inputs):
    portfolio, store, calendar, tmp_path = dashboard_inputs
    reddit_dir = tmp_path / "reddit"
    reddit_dir.mkdir()
    comments = [_comment(f"c{i}", score=i, ts=1700000000 + i) for i in range(7)]
    comments.append(_comment("c6", score=99, ts=1))  # duplicate id, higher score wins
    _write_reddit_file(reddit_dir, "FOMC", "2024-01-31", "ok", comments)
    _write_reddit_file(reddit_dir, "CPI", "2024-01-11", "error: ProviderError", [])
    data = ed.event_dashboard_data(portfolio, store, calendar, reddit_dir=reddit_dir)
    by_key = {(e["type"], e["date"]): e for e in data["events"]}
    fomc = by_key[("FOMC", "2024-01-31")]["reddit"]
    assert fomc["status"] == "ok"
    assert len(fomc["comments"]) <= MAX_COMMENTS
    assert fomc["comments"][0]["comment_id"] == "c6"
    assert fomc["comments"][0]["score"] == 99
    assert {c["comment_id"] for c in fomc["comments"]} == {"c6", "c5", "c4", "c3", "c2"}
    cpi = by_key[("CPI", "2024-01-11")]["reddit"]
    assert cpi["status"] == "error: ProviderError"
    assert cpi["comments"] == []
    # Events never collected are explicit, not silently empty.
    assert by_key[("PCE", "2024-01-26")]["reddit"]["status"] == "not_collected"


@pytest.mark.unit
def test_render_labels_reddit_as_commentary_and_escapes_content(dashboard_inputs):
    portfolio, store, calendar, tmp_path = dashboard_inputs
    reddit_dir = tmp_path / "reddit"
    reddit_dir.mkdir()
    nasty = RedditComment(
        comment_id="x1",
        score=12,
        author='evil"><script>',
        created_utc=1700000000,
        subreddit="economics",
        permalink="/r/economics/comments/abc/x1/",
        body="fomc <script>alert('x')</script> & more",
    )
    _write_reddit_file(reddit_dir, "FOMC", "2024-01-31", "ok", [nasty])
    data = ed.event_dashboard_data(portfolio, store, calendar, reddit_dir=reddit_dir)
    target = ed.render_event_dashboard(data, tmp_path / "out")
    page = target.read_text()
    assert "Community commentary (Reddit)" in page
    assert "not verified facts" in page
    # The JSON payload escapes < and &, so hostile markup never reaches the DOM raw.
    assert "<script>alert" not in page
    assert "\\u003cscript>" in page
    assert "/r/economics/comments/abc/x1/" in page


@pytest.mark.unit
def test_render_represents_missing_reddit_explicitly(dashboard_inputs):
    portfolio, store, calendar, tmp_path = dashboard_inputs
    data = ed.event_dashboard_data(portfolio, store, calendar, reddit_dir=None)
    target = ed.render_event_dashboard(data, tmp_path / "out")
    page = target.read_text()
    assert "No Reddit data collected for this event yet" in page
    assert "collect-reddit" in page


@pytest.mark.unit
def test_render_payload_caps_comments_before_rendering(dashboard_inputs):
    portfolio, store, calendar, tmp_path = dashboard_inputs
    reddit_dir = tmp_path / "reddit"
    reddit_dir.mkdir()
    comments = [_comment(f"c{i}", score=i, ts=1700000000 + i) for i in range(9)]
    _write_reddit_file(reddit_dir, "FOMC", "2024-01-31", "ok", comments)
    data = ed.event_dashboard_data(portfolio, store, calendar, reddit_dir=reddit_dir)
    target = ed.render_event_dashboard(data, tmp_path / "out")
    # The payload is what the browser renders from: at most five comments.
    assert target.read_text().count('"comment_id"') == MAX_COMMENTS


# --- CLI wiring ---


class _FakePortfolio:
    def __init__(self, base, paths):
        self._base = base
        self.paths = paths

    def path(self, key):
        return self._base / self.paths[key]


def _patch_collect_reddit(monkeypatch, tmp_path, calls):
    from portfolio_analysis import cli

    portfolio = _FakePortfolio(tmp_path, {"cache": "c", "reddit": "r"})
    monkeypatch.setattr(cli, "load_portfolio", lambda: portfolio)
    monkeypatch.setattr(cli, "CachedHttp", lambda cache, ledger=None: "http")
    monkeypatch.setattr(cli, "RateLimitLedger", lambda path: "ledger")
    monkeypatch.setattr(cli, "MacroSource", lambda path: "macro")

    def fake_collect(calendar, reddit_dir, http, *, daily_limit, rebuild, report=print):
        calls["collect"] = (calendar, reddit_dir, http, daily_limit, rebuild)
        return RedditCollectionResult(completed=2, remaining=0)

    monkeypatch.setattr(cli, "collect_reddit_for_events", fake_collect)
    return cli


def _cli_args(**overrides):
    base = {
        "cache_dir": None,
        "reddit_dir": None,
        "macro_calendar": "cal.yaml",
        "daily_limit": 400,
        "rebuild": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.mark.unit
def test_cli_collect_reddit_uses_configured_paths(monkeypatch, tmp_path, capsys):
    calls = {}
    cli = _patch_collect_reddit(monkeypatch, tmp_path, calls)
    assert cli._collect_reddit(_cli_args()) == 0
    assert calls["collect"] == ("macro", tmp_path / "r", "http", 400, False)
    assert "2 completed, 0 remaining" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_collect_reddit_flag_overrides_and_rebuild(monkeypatch, tmp_path):
    calls = {}
    cli = _patch_collect_reddit(monkeypatch, tmp_path, calls)
    args = _cli_args(reddit_dir=str(tmp_path / "custom"), daily_limit=10, rebuild=True)
    assert cli._collect_reddit(args) == 0
    assert calls["collect"][1] == tmp_path / "custom"
    assert calls["collect"][3:] == (10, True)


@pytest.mark.unit
def test_cli_registers_collect_reddit_and_reddit_dir_flag(capsys):
    from portfolio_analysis import cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["collect-reddit", "--help"])
    assert exc.value.code == 0
    assert "collect-reddit" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["event-dashboard", "--help"])
    assert "--reddit-dir" in capsys.readouterr().out
