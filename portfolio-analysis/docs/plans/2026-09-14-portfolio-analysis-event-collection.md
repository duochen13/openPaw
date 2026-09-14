# portfolio-analysis Event Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every flagged move, assemble a dated, cited evidence bundle from EDGAR, earnings dates, news, the macro calendar and HackerNews, within a `[-2, +1]` trading-day window.

**Architecture:** A provider-agnostic `EventSource` protocol with five adapters.
Every adapter writes its raw HTTP response to a content-addressed disk cache *before* parsing, so a parser change never costs a re-fetch and never costs quota.
A persistent rate-limit ledger survives process death, so an interrupted backfill resumes without double-spending the day's budget.
`bundle.py` merges adapter output into one artifact per move, hashed canonically so Plan 3's LLM cache is stable against upstream reordering.

**Tech Stack:** Python 3.13, `uv`, `requests`, `pyyaml`, stdlib `hashlib`/`json`, `pytest`, `ruff`, `mypy --strict`.

**Spec:** [`docs/specs/2026-09-13-portfolio-analysis-design.md`](../specs/2026-09-13-portfolio-analysis-design.md) §4, §6, §7, §11.
**Depends on:** Plan 1 (complete). Consumes `data/moves/<TICKER>.json` via `artifacts.read_moves`.

---

## Measured facts this plan is built on

Probed live on 2026-09-14. These are measurements, not assumptions, and Task 11 asserts them.

| Fact | Measured value |
|---|---|
| EDGAR `filings.recent` for META | **1000 filings, only 2024-06-11 .. 2026-09-11** |
| EDGAR `filings.files[]` archives | `-001.json` 2000 filings 2017-05-02 .. 2024-06-10; `-002.json` 1183 filings 2005-05-06 .. 2017-04-27 |
| META 8-K before the 2024-04-25 move | filed **2024-04-24**, accession `0001326801-24-000044` |
| META 10-Q on the move date | filed 2024-04-25, accession `0001326801-24-000049` |
| META 8-K before the 2022-02-03 move | filed 2022-02-02, accession `0001326801-22-000015` |
| META 10-K on that move date | filed 2022-02-03, accession `0001326801-22-000018` |
| HN Algolia, "Meta earnings", 2024-04-23..26 | `nbHits: 9`, incl. *"Meta stock has lost $137B in market cap on weak Q2 revenue guidance"* |
| META Form 4 / Form 144 volume | 547 and 371 in ~2 years — noise that must be excluded |
| Alpha Vantage free tier | 25 requests/day |
| AV news, earliest META article | **`20200121T221400`** - before the evaluated window begins |
| AV news volume, 2024-04-25 window | **7 articles** |
| AV news volume, 2022-02-03 window | **14 articles** |
| AV reliability | 12 x `502 Bad Gateway` across 3 requests - retry is mandatory |
| yfinance `get_earnings_dates(limit=40)` | 50 quarters, 2014-07 .. 2026-10, **with time of day** |
| Finnhub free tier | 1 year of news - covers 8 of 30 moves, misses all 3 largest. Rejected |

### The EDGAR trap, stated up front

**`filings.recent` does not reach five years back.** For META it starts at 2024-06-11.
An adapter that reads only `recent` reports "no filing" for every move before that date — two thirds of the evaluated window — and reports it *silently*, as an absence rather than an error.

That is precisely the failure this project exists to avoid: a confident-looking empty result.
The adapter therefore **must** merge `filings.recent` with every file listed in `filings.files[]`, and Task 4 has a test that fails if it does not.

### The catalyst lands at t-1, not t

Measured: the earnings 8-K was filed **2024-04-24**, the day before the move.
Companies report after the close, and the price reacts the next session.
This is the empirical justification for a window that reaches two sessions back rather than starting at `t`.

---

## A spec amendment: the macro calendar is a file, not an API

Spec §4.1 lists FRED as the macro source, which needs an API key.
This plan uses a checked-in `config/macro_calendar.yaml` instead, for four reasons:

1. FOMC, CPI and PCE release dates are **published years in advance and never revised retroactively**. There is no freshness argument for an API.
2. It is roughly 160 dates over five years — small enough to read, diff, and audit in review.
3. It removes an API key, a network dependency, and a rate limit from the pipeline.
4. It makes the macro check work offline and in tests without mocking.

The cost is manual data entry, done once, with source URLs recorded in the file.
Update spec §4.1 when this lands.

**Consequence: this plan needs only ONE API key** — Alpha Vantage. EDGAR and HN Algolia are keyless.

---

## File Structure

| Path | Responsibility |
|---|---|
| `config/macro_calendar.yaml` | FOMC / CPI / PCE release dates, with source URLs |
| `src/portfolio_analysis/calendar.py` | Trading-day arithmetic: the `[-2, +1]` window |
| `src/portfolio_analysis/http.py` | Content-addressed response cache + persistent quota ledger |
| `src/portfolio_analysis/events/base.py` | `Document`, `VerifiedFact`, the `EventSource` protocol |
| `src/portfolio_analysis/events/edgar.py` | Filings, merging `recent` with the archives |
| `src/portfolio_analysis/events/earnings.py` | Alpha Vantage `EARNINGS` reported dates |
| `src/portfolio_analysis/events/news.py` | Alpha Vantage `NEWS_SENTIMENT`, windowed |
| `src/portfolio_analysis/events/macro.py` | The checked-in macro calendar |
| `src/portfolio_analysis/events/hn.py` | HackerNews Algolia search |
| `src/portfolio_analysis/bundle.py` | Merge into one bundle, canonical hash, coverage |
| `src/portfolio_analysis/cli.py` | *(modify)* add `collect-events` |

`http.py` owns every network concern — caching, quota, secrets — so no adapter reimplements it.
Each adapter is a pure translation from one provider's JSON into the two evidence types, testable from a recorded fixture with no network.

---

## Task 1: Trading-day window arithmetic

The window is `[-2, +1]` **trading** days, not calendar days.
A Monday move needs the prior Thursday and Friday; calendar arithmetic silently grabs a weekend and misses the two sessions that matter.

**Files:**
- Create: `src/portfolio_analysis/calendar.py`
- Test: `tests/test_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from portfolio_analysis.calendar import TradingCalendar

# Thu Fri Mon Tue Wed Thu Fri Mon - a real run with the weekend gap.
SESSIONS = [
    "2024-04-18", "2024-04-19", "2024-04-22", "2024-04-23",
    "2024-04-24", "2024-04-25", "2024-04-26", "2024-04-29",
]


@pytest.fixture
def cal():
    return TradingCalendar(SESSIONS)


@pytest.mark.unit
def test_window_spans_two_sessions_back_and_one_forward(cal):
    assert cal.window("2024-04-25", before=2, after=1) == ("2024-04-23", "2024-04-26")


@pytest.mark.unit
def test_window_skips_the_weekend_rather_than_counting_calendar_days(cal):
    """2024-04-22 is a Monday. Two sessions back is the prior Thursday, four
    calendar days earlier - a calendar window would land on the Saturday."""
    assert cal.window("2024-04-22", before=2, after=1) == ("2024-04-18", "2024-04-23")


@pytest.mark.unit
def test_window_clamps_at_the_start_of_the_calendar(cal):
    assert cal.window("2024-04-18", before=2, after=1) == ("2024-04-18", "2024-04-19")


@pytest.mark.unit
def test_window_clamps_at_the_end_of_the_calendar(cal):
    assert cal.window("2024-04-29", before=2, after=1) == ("2024-04-25", "2024-04-29")


@pytest.mark.unit
def test_sessions_in_returns_the_inclusive_session_list(cal):
    assert cal.sessions_in("2024-04-23", "2024-04-26") == [
        "2024-04-23", "2024-04-24", "2024-04-25", "2024-04-26"
    ]


@pytest.mark.unit
def test_a_date_that_is_not_a_session_raises(cal):
    """A move date always IS a session. Asking about a non-session means the
    caller mixed up its calendars - worth an error, not a guess."""
    with pytest.raises(KeyError, match="not a trading session"):
        cal.window("2024-04-20", before=2, after=1)


@pytest.mark.unit
def test_an_empty_calendar_raises_at_construction():
    with pytest.raises(ValueError, match="at least one session"):
        TradingCalendar([])


@pytest.mark.unit
def test_the_calendar_sorts_and_deduplicates_its_input():
    cal = TradingCalendar(["2024-04-25", "2024-04-23", "2024-04-25"])
    assert cal.sessions_in("2024-04-23", "2024-04-25") == ["2024-04-23", "2024-04-25"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_calendar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.calendar'`

- [ ] **Step 3: Write the implementation**

```python
"""Trading-day arithmetic (spec §6).

The event window is [-2, +1] TRADING days. Calendar arithmetic is wrong here:
two calendar days before a Monday is a Saturday, so a calendar window silently
trades the two sessions that matter for a weekend where nothing happened.

The session list comes from the benchmark's price history, which is present for
every date in the evaluated range by construction.
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable


class TradingCalendar:
    def __init__(self, sessions: Iterable[str]) -> None:
        self._sessions = sorted(set(sessions))
        if not self._sessions:
            raise ValueError("a trading calendar needs at least one session")
        self._index = {d: i for i, d in enumerate(self._sessions)}

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def first(self) -> str:
        return self._sessions[0]

    @property
    def last(self) -> str:
        return self._sessions[-1]

    def window(self, date: str, *, before: int, after: int) -> tuple[str, str]:
        """Inclusive (start, end) spanning `before` sessions back and `after`
        forward. Clamped at the ends of the calendar."""
        if date not in self._index:
            raise KeyError(f"{date!r} is not a trading session in this calendar")
        i = self._index[date]
        lo = max(0, i - before)
        hi = min(len(self._sessions) - 1, i + after)
        return self._sessions[lo], self._sessions[hi]

    def sessions_in(self, start: str, end: str) -> list[str]:
        """Every session in the inclusive range. Endpoints need not be sessions."""
        lo = bisect_left(self._sessions, start)
        hi = bisect_left(self._sessions, end)
        if hi < len(self._sessions) and self._sessions[hi] == end:
            hi += 1
        return self._sessions[lo:hi]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_calendar.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/calendar.py tests/test_calendar.py
git commit -m "feat(portfolio-analysis): trading-day window arithmetic

Calendar arithmetic is wrong here: two calendar days before a Monday is a
Saturday, so a calendar window trades the two sessions that matter for a
weekend where nothing happened."
```

---

## Task 2: HTTP cache and the persistent quota ledger

Every network concern lives here so no adapter reimplements it.
Two properties matter more than the rest:

- **The API key never reaches disk.** Stripped before the cache key is computed and before anything is written, so `data/cache/` can be inspected, diffed, or shared without leaking a credential — and rotating the key does not invalidate the cache and re-spend the whole quota.
- **The quota ledger survives process death.** A crashed backfill that forgets its spend burns the next day's budget re-fetching, and silently covers fewer moves.

**Files:**
- Create: `src/portfolio_analysis/http.py`
- Test: `tests/test_http.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from portfolio_analysis.http import (
    CachedHttp,
    QuotaExhausted,
    RateLimitLedger,
    cache_key,
)


@pytest.mark.unit
def test_the_api_key_is_not_part_of_the_cache_key():
    """Otherwise rotating the key silently invalidates the whole cache and
    re-spends the entire quota."""
    a = cache_key("https://x/q?function=NEWS&tickers=META&apikey=SECRET1")
    b = cache_key("https://x/q?function=NEWS&tickers=META&apikey=SECRET2")
    assert a == b


@pytest.mark.unit
def test_different_requests_have_different_cache_keys():
    assert cache_key("https://x/q?t=META") != cache_key("https://x/q?t=NVDA")


@pytest.mark.unit
def test_query_parameter_order_does_not_change_the_cache_key():
    assert cache_key("https://x/q?a=1&b=2") == cache_key("https://x/q?b=2&a=1")


@pytest.mark.unit
def test_a_cached_response_is_served_without_a_second_fetch(tmp_path):
    calls = []

    def fake(url):
        calls.append(url)
        return {"ok": True}

    http = CachedHttp(tmp_path, ledger=RateLimitLedger(tmp_path / "l.json"), fetch=fake)
    url = "https://x/q?function=NEWS&apikey=SECRET"
    assert http.get_json("test", url, daily_limit=25) == {"ok": True}
    assert http.get_json("test", url, daily_limit=25) == {"ok": True}
    assert len(calls) == 1


@pytest.mark.unit
def test_a_cache_hit_does_not_spend_quota(tmp_path):
    ledger = RateLimitLedger(tmp_path / "l.json")
    http = CachedHttp(tmp_path, ledger=ledger, fetch=lambda u: {"ok": True})
    http.get_json("test", "https://x/q?a=1", daily_limit=25)
    http.get_json("test", "https://x/q?a=1", daily_limit=25)
    assert ledger.spent_today("test") == 1


@pytest.mark.unit
def test_no_api_key_is_written_anywhere_under_the_cache_directory(tmp_path):
    http = CachedHttp(tmp_path, ledger=RateLimitLedger(tmp_path / "l.json"),
                      fetch=lambda u: {"ok": True})
    http.get_json("test", "https://x/q?a=1&apikey=SUPERSECRET", daily_limit=25)
    blob = "".join(p.read_text() + str(p) for p in tmp_path.rglob("*") if p.is_file())
    assert "SUPERSECRET" not in blob


@pytest.mark.unit
def test_quota_exhaustion_raises_rather_than_fetching(tmp_path):
    calls = []
    http = CachedHttp(tmp_path, ledger=RateLimitLedger(tmp_path / "l.json"),
                      fetch=lambda u: (calls.append(u), {"ok": True})[1])
    for i in range(3):
        http.get_json("test", f"https://x/q?i={i}", daily_limit=3)
    with pytest.raises(QuotaExhausted, match="test"):
        http.get_json("test", "https://x/q?i=99", daily_limit=3)
    assert len(calls) == 3


@pytest.mark.unit
def test_the_ledger_survives_a_restart(tmp_path):
    """A crashed backfill that forgets its spend burns the next day's budget
    re-fetching, and silently covers fewer moves."""
    path = tmp_path / "l.json"
    RateLimitLedger(path).record("test")
    RateLimitLedger(path).record("test")
    assert RateLimitLedger(path).spent_today("test") == 2


@pytest.mark.unit
def test_the_ledger_is_per_provider(tmp_path):
    ledger = RateLimitLedger(tmp_path / "l.json")
    ledger.record("alphavantage")
    assert ledger.spent_today("alphavantage") == 1
    assert ledger.spent_today("hackernews") == 0


@pytest.mark.unit
def test_a_corrupt_ledger_fails_loudly_rather_than_resetting_the_quota(tmp_path):
    """Treating an unreadable ledger as zero spend is how you get rate-limited
    by the provider instead of by yourself."""
    path = tmp_path / "l.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="ledger"):
        RateLimitLedger(path).spent_today("test")


@pytest.mark.unit
def test_an_alpha_vantage_refusal_is_not_cached_as_data(tmp_path):
    """Alpha Vantage answers an exceeded quota with HTTP 200 and an
    {"Information": ...} body. Cached as data, that poisons the cache with a
    permanent non-answer no re-run will ever retry."""
    http = CachedHttp(tmp_path, ledger=RateLimitLedger(tmp_path / "l.json"),
                      fetch=lambda u: {"Information": "rate limit is 25 per day"})
    with pytest.raises(QuotaExhausted, match="refused"):
        http.get_json("alphavantage", "https://x/q?a=1", daily_limit=25)
    assert not list((tmp_path / "alphavantage").glob("*.json"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_http.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.http'`

- [ ] **Step 3: Write the implementation**

```python
"""Caching and quota for every outbound request (spec §6.1).

Two properties matter more than the rest of this module:

  - The API key never reaches disk. It is stripped before the cache key is
    computed and before anything is written, so data/cache/ can be inspected,
    diffed, or handed to someone else without leaking a credential, and
    rotating the key does not invalidate the cache.

  - The quota ledger survives process death. Alpha Vantage's free tier is 25
    requests per day, and a crashed backfill that forgets its spend burns the
    next day's budget re-fetching - silently covering fewer moves rather than
    failing.

Raw responses are cached BEFORE parsing, so a parser change costs nothing and,
more importantly, costs no quota.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

_UA = "portfolio-analysis/0.1 (research)"

#: Query parameters holding credentials. Stripped before hashing and before any
#: write, so a cache directory never contains a secret.
_SECRET_PARAMS = frozenset({"apikey", "api_key", "token", "key"})


class QuotaExhausted(RuntimeError):
    """The daily budget for a provider is spent, or the provider refused."""


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _SECRET_PARAMS
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def cache_key(url: str) -> str:
    """Stable hash of a request, with credentials and parameter order removed."""
    return hashlib.sha256(_canonical_url(url).encode()).hexdigest()


class RateLimitLedger:
    """Per-provider daily request counts, persisted across processes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, dict[str, int]]:
        if not self.path.exists():
            return {}
        try:
            data: dict[str, dict[str, int]] = json.loads(self.path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"rate-limit ledger at {self.path} is unreadable ({exc}); refusing "
                "to treat that as zero spend, which would get us rate-limited by "
                "the provider instead of by ourselves. Inspect it or delete it."
            ) from exc
        return data

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def spent_today(self, provider: str) -> int:
        return int(self._load().get(provider, {}).get(self._today(), 0))

    def record(self, provider: str) -> None:
        data = self._load()
        day = self._today()
        data.setdefault(provider, {})[day] = int(data.get(provider, {}).get(day, 0)) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _http_get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=60)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


class CachedHttp:
    def __init__(
        self,
        cache_dir: Path,
        *,
        ledger: RateLimitLedger,
        fetch: Callable[[str], dict[str, Any]] = _http_get_json,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ledger = ledger
        self._fetch = fetch

    def get_json(
        self, provider: str, url: str, *, daily_limit: int | None
    ) -> dict[str, Any]:
        path = self.cache_dir / provider / f"{cache_key(url)}.json"
        if path.exists():
            cached: dict[str, Any] = json.loads(path.read_text())
            return cached

        if daily_limit is not None and self.ledger.spent_today(provider) >= daily_limit:
            raise QuotaExhausted(
                f"{provider}: the daily budget of {daily_limit} requests is spent. "
                "Everything already fetched is cached, so resuming tomorrow picks "
                "up where this left off."
            )

        payload = self._fetch(url)
        self.ledger.record(provider)

        # Alpha Vantage answers an exceeded quota with HTTP 200 and an
        # {"Information": ...} body. Cached as data that poisons the cache with
        # a permanent non-answer no re-run will ever retry.
        note = payload.get("Information") or payload.get("Note")
        if note:
            raise QuotaExhausted(f"{provider}: the provider refused with {note!r}")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_http.py -v`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/http.py tests/test_http.py
git commit -m "feat(portfolio-analysis): cached http with a persistent quota ledger

The API key never reaches disk - stripped before the cache key is computed
and before any write, so rotating it does not invalidate the cache and the
cache directory never holds a credential.

The ledger survives process death: a crashed backfill that forgets its
spend burns the next day's budget and silently covers fewer moves.

An {Information: ...} quota refusal arrives as HTTP 200; cached as data it
would poison the cache with a permanent non-answer."
```

---

## Task 3: `Document`, `VerifiedFact`, and the `EventSource` protocol

The line this module draws is the one spec §8 rests on: **verified facts are computed, reported claims are asserted by sources.**
Keeping them as different types means the model in Plan 3 is handed `Document`s and structurally cannot construct a `VerifiedFact` — it cannot promote its own story into a checkmark.

**Files:**
- Create: `src/portfolio_analysis/events/__init__.py`
- Create: `src/portfolio_analysis/events/base.py`
- Test: `tests/test_events_base.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from portfolio_analysis.events.base import Document, VerifiedFact


def _doc(**kw):
    base = dict(source="x", native_id="1", published_at="2024-04-25T11:00:00Z",
                title="t", url="u")
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
    with pytest.raises(Exception):
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
    f = VerifiedFact(key="earnings_reported", value=True,
                     source="alphavantage:EARNINGS", detail="reportedDate 2024-04-24")
    assert f.as_dict() == {
        "key": "earnings_reported", "value": True,
        "source": "alphavantage:EARNINGS", "detail": "reportedDate 2024-04-24",
    }


@pytest.mark.unit
def test_a_verified_fact_without_a_source_raises():
    """An unsourced 'verified' fact is just an assertion - which is the thing
    this type exists to distinguish itself from."""
    with pytest.raises(ValueError, match="source"):
        VerifiedFact(key="earnings_reported", value=True, source="", detail="")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_events_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.events'`

- [ ] **Step 3: Create the package**

```bash
mkdir -p src/portfolio_analysis/events
cat > src/portfolio_analysis/events/__init__.py <<'EOF'
"""Event sources.

Each adapter translates one provider's JSON into the two types in base.py and
does nothing else - no caching, no quota, no statistics. Those live in
http.py and moves.py respectively.
"""
EOF
```

- [ ] **Step 4: Write `events/base.py`**

```python
"""The two kinds of evidence, kept as different types on purpose (spec §8).

A VerifiedFact is computed from a dated source: an 8-K was filed, earnings were
reported, the date was an FOMC day. A Document is something a source SAID.

The separation is the structural defense against post-hoc narrative fitting. In
Plan 3 the model is handed Documents and may cite them; it is never given the
ability to construct a VerifiedFact, so it cannot promote its own story into a
checkmark.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

#: US markets run on US/Eastern, which is UTC-5 or UTC-4. Market news belongs
#: to the exchange's day, not UTC's: a 02:00 UTC story is the previous evening
#: in New York. The fixed four-hour approximation is deliberate - it is exact
#: during the DST months that cover most of the year and an hour off at the
#: edges, which cannot move a story across a [-2,+1] SESSION window. A tz
#: database dependency would buy nothing here.
_EASTERN_OFFSET = timedelta(hours=-4)

_TIMESTAMP_FORMATS = ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y-%m-%d")


def parse_timestamp(raw: str) -> str:
    """Normalize a vendor timestamp to canonical UTC ISO-8601."""
    text = raw.strip()
    try:
        parsed: datetime | None = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for fmt in _TIMESTAMP_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"unparseable timestamp: {raw!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


@dataclass(frozen=True, order=True)
class Document:
    """Something a source said, with a citable identity."""

    doc_id: str
    source: str = field(compare=False)
    published_at: str = field(compare=False)
    title: str = field(compare=False)
    url: str = field(compare=False)
    summary: str = field(compare=False, default="")
    relevance: float | None = field(compare=False, default=None)

    @classmethod
    def make(
        cls,
        *,
        source: str,
        native_id: str,
        published_at: str,
        title: str,
        url: str,
        summary: str = "",
        relevance: float | None = None,
    ) -> Document:
        return cls(
            doc_id=f"{source}:{native_id}",
            source=source,
            published_at=parse_timestamp(published_at),
            title=title,
            url=url,
            summary=summary,
            relevance=relevance,
        )

    @property
    def eastern_date(self) -> str:
        """The exchange-day this document belongs to."""
        return (
            datetime.fromisoformat(self.published_at) + _EASTERN_OFFSET
        ).strftime("%Y-%m-%d")

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "published_at": self.published_at,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "relevance": self.relevance,
        }


@dataclass(frozen=True)
class VerifiedFact:
    """Computed from a dated source. Never written by a model."""

    key: str
    value: Any
    source: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError(
                f"VerifiedFact {self.key!r} has no source; an unsourced "
                "'verified' fact is just an assertion, which is exactly what "
                "this type exists to distinguish itself from"
            )

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value,
                "source": self.source, "detail": self.detail}


class EventSource(Protocol):
    """One provider. Translation only."""

    name: str

    def collect(
        self, ticker: str, start: str, end: str
    ) -> tuple[list[Document], list[VerifiedFact]]: ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_events_base.py -v`
Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add src/portfolio_analysis/events tests/test_events_base.py
git commit -m "feat(portfolio-analysis): Document and VerifiedFact as distinct types

The separation is the structural defense against narrative fitting. The
model is handed Documents and may cite them; it is never given the ability
to construct a VerifiedFact, so it cannot promote its story into a checkmark."
```

---

## Task 4: EDGAR adapter — and the `recent`-only trap

Read the "EDGAR trap" section at the top of this plan before starting.

**Files:**
- Create: `src/portfolio_analysis/events/edgar.py`
- Test: `tests/test_events_edgar.py`

- [ ] **Step 1: Write the failing test**

```python
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
        "0001326801-24-000049", "0000950103-24-005771", "0001326801-24-000044",
    ],
    "filingDate": ["2024-04-25", "2024-04-25", "2024-04-24"],
    "form": ["10-Q", "4", "8-K"],
    "primaryDocument": ["q.htm", "f.htm", "k.htm"],
}


def _source(index=INDEX, archive=ARCHIVE):
    def fake(provider, url, *, daily_limit):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_events_edgar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.events.edgar'`

- [ ] **Step 3: Write the implementation**

```python
"""SEC EDGAR filings as verified facts (spec §4.1, §8).

A filing either exists with an accession number or it does not, so EDGAR emits
VerifiedFacts and never Documents.

CRITICAL: `filings.recent` holds only the most recent 1000 filings. Measured on
2026-09-14, META's `recent` begins at 2024-06-11 - two thirds of a five-year
window is absent from it. The older filings live in the archive files listed
under `filings.files[]`, and this adapter merges them. An adapter reading only
`recent` reports "no filing" for most of the window, silently, as an absence
rather than an error.

EDGAR is free and has no daily quota, so it passes daily_limit=None. It does
require a descriptive User-Agent, which http.py sets.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from portfolio_analysis.events.base import Document, VerifiedFact

_INDEX_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://data.sec.gov/submissions/{name}"
_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{document}"

#: Forms that can move a price. Deliberately narrow - see the Form 4 test.
_MATERIAL_FORMS = frozenset({"8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A"})

GetJson = Callable[..., dict[str, Any]]


class EdgarSource:
    name = "edgar"

    def __init__(self, get_json: GetJson) -> None:
        self._get_json = get_json

    def _pages(self, cik: int) -> list[dict[str, Any]]:
        index = self._get_json("edgar", _INDEX_URL.format(cik=cik), daily_limit=None)
        pages = [index["filings"]["recent"]]
        for entry in index["filings"].get("files", []):
            pages.append(self._get_json(
                "edgar", _ARCHIVE_URL.format(name=entry["name"]), daily_limit=None
            ))
        return pages

    def collect(
        self, ticker: str, start: str, end: str, *, cik: int
    ) -> tuple[list[Document], list[VerifiedFact]]:
        facts: list[VerifiedFact] = []
        for page in self._pages(cik):
            forms: list[str] = page.get("form", [])
            documents = page.get("primaryDocument", [""] * len(forms))
            for i, form in enumerate(forms):
                filed = page["filingDate"][i]
                if not (start <= filed <= end) or form not in _MATERIAL_FORMS:
                    continue
                accession = page["accessionNumber"][i]
                facts.append(VerifiedFact(
                    key="filing",
                    value={
                        "form": form,
                        "filed": filed,
                        "accession": accession,
                        "url": _DOC_URL.format(
                            cik=cik,
                            nodash=accession.replace("-", ""),
                            document=documents[i],
                        ),
                    },
                    source=f"edgar:CIK{cik:010d}",
                    detail=f"{form} {accession} filed {filed}",
                ))
        facts.sort(key=lambda f: (f.value["filed"], f.value["accession"]))
        return [], facts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_events_edgar.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/events/edgar.py tests/test_events_edgar.py
git commit -m "feat(portfolio-analysis): EDGAR filings adapter

Merges filings.recent with every archive under filings.files[]. recent holds
only the last 1000 filings - measured 2026-09-14, META's begins at 2024-06-11,
so an adapter reading only recent reports 'no filing' for two thirds of a
five-year window, silently, as an absence rather than an error.

Form 4 and 144 excluded: 918 of them in two years, none a catalyst."
```

---

## Tasks 5-9: the remaining adapters and the bundle

These follow the pattern Task 4 establishes — a recorded fixture, a pure translation, no network in tests — and each needs the same level of detail written out before implementation. Their contracts and the specific trap in each:

**Task 5 — `events/earnings.py`.** Alpha Vantage `EARNINGS`, reading `quarterlyEarnings[].reportedDate`. One request per ticker, cached permanently. Emits one `earnings_reported` VerifiedFact when a reported date falls inside the window. *Trap:* Alpha Vantage emits the string `"None"` for a missing `reportedDate`; treat it as absent rather than letting it reach a date parser.

**Task 6 — `events/news.py`.** Alpha Vantage `NEWS_SENTIMENT` with `time_from`/`time_to`, `limit=1000`. One request per move — this is the only source that spends meaningful quota. Emits Documents. *Trap:* `ticker_sentiment` is a list covering every ticker mentioned; the relevance score must be read for the *requested* ticker, not `[0]`, or a story about NVDA that mentions META inherits NVDA's relevance.

**Task 7 — `events/macro.py`.** Reads `config/macro_calendar.yaml`, no network. Emits a `macro_release` VerifiedFact naming the release when the move date is an FOMC/CPI/PCE day. Includes populating the YAML from the Fed, BLS and BEA published calendars, with source URLs recorded in the file.

**Task 8 — `events/hn.py`.** Algolia `search_by_date` with `numericFilters` on `created_at_i`. Keyless, no quota. Emits Documents. *Trap:* comments have no `title`, only `story_title`; fall back or they arrive blank.

**Task 9 — `bundle.py`.** Merges adapters into the spec §7 artifact and computes `bundle_sha256` over a canonical serialization with documents sorted by `doc_id`. *This hash is load-bearing:* Plan 3's LLM cache key includes it, so reordering upstream must not change it, and a test must assert that.

## Task 10: `collect-events` command

The third subcommand. The behaviour that matters: on `QuotaExhausted` it reports how many moves completed and how many remain, and exits **0**. A backfill that finished 25 of 30 moves has not failed, and a non-zero exit would make a scheduled re-run look broken.

## Task 11: Live verification

Marked `network`, excluded from the default run. Asserts the measured anchors: the 2024-04-25 bundle contains 8-K `0001326801-24-000044` filed 2024-04-24, 10-Q `0001326801-24-000049`, an `earnings_reported` fact, and at least one HackerNews document. EDGAR and HN assertions run without a key; news assertions skip when `ALPHAVANTAGE_API_KEY` is unset.

---

## Definition of done

- [ ] `.venv/bin/pytest` passes with no network access
- [ ] `.venv/bin/pytest -m network` passes (news assertions skip without a key)
- [ ] `ruff check .` and `mypy` clean
- [ ] `data/events/META/2024-04-25.json` contains the 8-K accession, the 10-Q, the earnings fact, and N news documents
- [ ] **No API key appears anywhere under `data/cache/`** — assert by grep, not by inspection
- [ ] Interrupting a backfill and re-running resumes without re-spending quota

## Handoff to Plan 3

Plan 3 consumes `data/events/<TICKER>/<DATE>.json` and requires `bundle_sha256` to be stable across re-runs, which Task 9 guarantees.

**Do not write Plan 3 until Plan 2 has run.** The prompt design depends on what the bundles actually contain — how many documents a typical move carries, how much of the text is usable, and how often the news layer comes back thin. Writing it beforehand means guessing at its own input, and the guess would be load-bearing for the controls in spec §10.
