# stock-trading-bot Social Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest HackerNews and Reddit discussion into the point-in-time store, attributed to tickers, deduplicated, and with repeated-author and duplicate-event influence capped.

**Architecture:** Documents land in an append-only `social_document` table carrying the same four timestamps as every other fact. Near-duplicate detection, event clustering, and influence capping are **pure functions of the document set visible at `t`**, computed on demand rather than materialized — a cluster is a property of what was visible when you looked, so storing one would be wrong in a walk-forward backtest.

**Tech Stack:** Python 3.13, `uv`, stdlib `sqlite3`, `requests`, `pytest`. No new dependencies: shingling, Jaccard, and TF-IDF cosine are ~60 lines of pure Python and adding scikit-learn here would make the lockfile lie about what the ingestion layer needs.

**Spec:** `docs/superpowers/specs/2026-09-07-stock-trading-bot-design.md` (§6, §7 partial)

**Branch:** `feat/stock-trading-bot` (continues from the foundation)

---

## Revised decomposition

The original spec proposed Plan 2 = "social + extraction". Both halves turned out large enough
to warrant their own cycle, so the remaining work is:

| Plan | Scope |
|---|---|
| **2 (this one)** | Social ingestion, ticker attribution, dedup, clustering, influence caps |
| 3 | LLM extraction: provider interface, long-doc router, schemas, evidence validation, cache |
| 4 | Features, training-only normalization, the ridge tier ladder, walk-forward evaluation |
| 5 | The 9-section report with citation audit, `SKILL.md`, the `stock-trading` subagent |

Each produces working, testable software on its own.

## Prerequisites and standing constraints

The foundation is committed. Read these before starting:

- `src/stock_trading_bot/store.py` — the append-only store and its `PointInTimeView` gateway
- `src/stock_trading_bot/timestamps.py` — `known_at_for`, `to_iso`, `parse_iso`
- `src/stock_trading_bot/naming.py` — `safe_ticker_component`
- `src/stock_trading_bot/config.py` — `load_watchlist`, `load_run_config`, `resolve_path`

**Non-negotiable, inherited from the foundation:**

1. **Canonical timestamps only**: fixed-width UTC with microseconds. SQLite `CHECK` constraints
   reject anything else. Never build one by string concatenation; always use `to_iso`.
2. **Reads go through `store.as_of(t)`.** Adding an accessor to `PointInTimeView` means routing
   it through `_rows`, which validates the returned column tuple against `_COLUMNS`. Reaching
   around `_rows` forfeits the visibility guarantee.
3. **Append-only.** No `UPDATE`, no `DELETE` on fact tables. A new row records new information.
4. Every ticker crossing an I/O boundary goes through `safe_ticker_component`.
5. `ruff` and `mypy --strict` stay clean. All network mocked in tests; the suite runs offline.

**Baseline: 157 tests passing.**

## The corpus situation

`market-research/data/raw/` no longer exists and was never committed, so the 3,104-comment
ServiceNow corpus behind `market-research/reports/servicenow_stock_report_2026-09-07.md` is
gone. Task 11 collects a fresh one.

`market-research/scripts/collect_hn.py` uses the free HN Algolia API and works.
`collect_reddit_new.py` drives the gstack `browse` headless browser and is fragile — Reddit has
already broken it once by gating `old.reddit.com` behind login. **Treat Reddit as optional in
this plan.** HN alone is enough to build and test against, and the source-mix sensitivity
analysis in Plan 4 is what will make a dead source visible rather than silently degrading.

Both collectors emit the same record shape, which the normalizer in Task 2 targets:

```python
# discussion (post)
{"id", "url", "external_url", "title", "source", "subreddit", "author",
 "created_utc", "score", "num_comments", "content", "comments": [...]}
# comment
{"id", "author", "created_utc", "score", "content", "depth"}
```

## File structure

| File | Responsibility |
|---|---|
| `src/stock_trading_bot/store.py` (modify) | Add `social_document` table, `insert_social_document`, `documents()` accessor |
| `src/stock_trading_bot/ingest/social.py` | Collector output → four-timestamp rows |
| `src/stock_trading_bot/validate/tickers.py` | Ticker attribution with `require_cashtag` |
| `src/stock_trading_bot/validate/dedup.py` | Exact hash, canonical URL, near-duplicate |
| `src/stock_trading_bot/validate/cluster.py` | Candidate windowing, TF-IDF cosine, components |
| `src/stock_trading_bot/validate/weights.py` | Author and cluster influence caps |
| `src/stock_trading_bot/cli.py` (modify) | `stock-trading collect <ticker>` |

`validate/` is a new package. It depends on `store` but **not** on `ingest` — the import-graph
test in `tests/test_import_graph.py` must be extended to cover it, since the same reasoning
applies: nothing that processes stored documents should be able to re-fetch live data.

---

### Task 1: `social_document` schema and accessor

**Files:**
- Modify: `src/stock_trading_bot/store.py`
- Test: `tests/test_store_social.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_store_social.py`:

```python
import sqlite3
from datetime import UTC, datetime

import pytest

from stock_trading_bot.store import Store

T = datetime(2026, 9, 9, tzinfo=UTC)


def _doc(store, doc_id="hn:1", ticker="NOW", known_at="2026-09-01T12:00:00.000000+00:00",
         body="ServiceNow raised guidance", author="alice", score=42.0):
    store.insert_social_document(
        doc_id=doc_id, source="hackernews", kind="post", parent_id=None,
        ticker=ticker, author=author,
        url=f"https://news.ycombinator.com/item?id={doc_id}",
        title="ServiceNow Q2", body=body,
        body_sha256=f"sha-of-{body}", score=score, score_contaminated=1,
        event_time="2026-09-01T11:00:00.000000+00:00",
        observed_at="2026-09-01T11:45:00.000000+00:00",
        known_at=known_at,
    )


@pytest.fixture
def store(tmp_path):
    return Store.open(tmp_path / "panel.sqlite")


@pytest.mark.unit
def test_a_stored_document_is_visible_afterwards(store):
    _doc(store)
    assert len(store.as_of(T).documents("NOW")) == 1


@pytest.mark.unit
def test_a_document_known_after_t_is_invisible(store):
    _doc(store, known_at="2026-09-20T12:00:00.000000+00:00")
    assert store.as_of(T).documents("NOW") == []


@pytest.mark.unit
def test_a_null_known_at_document_is_invisible(store):
    _doc(store, known_at=None)
    assert store.as_of(T).documents("NOW") == []


@pytest.mark.unit
def test_the_same_document_can_be_attributed_to_two_tickers(store):
    _doc(store, doc_id="hn:1", ticker="NOW")
    _doc(store, doc_id="hn:1", ticker="CRM")
    assert len(store.as_of(T).documents("NOW")) == 1
    assert len(store.as_of(T).documents("CRM")) == 1


@pytest.mark.unit
def test_reinserting_the_same_observation_collides(store):
    _doc(store)
    with pytest.raises(sqlite3.IntegrityError):
        _doc(store)


@pytest.mark.unit
def test_score_is_flagged_contaminated_by_default(store):
    """Scraped engagement counts are as-of-scrape, not as-of-t. This cannot be
    fixed by scraping; it can only be made impossible to forget."""
    _doc(store)
    assert store.as_of(T).documents("NOW")[0]["score_contaminated"] == 1


@pytest.mark.unit
def test_latest_social_document_finds_the_newest_observation(store):
    """The writer needs this to tell a re-fetch from an edit."""
    assert store.latest_social_document("hn:1", "NOW") is None
    _doc(store, body="first")
    store.insert_social_document(
        doc_id="hn:1", source="hackernews", kind="post", parent_id=None,
        ticker="NOW", author="alice", url="https://x/1", title=None,
        body="edited", body_sha256="sha-of-edited", score=42.0,
        score_contaminated=1,
        event_time="2026-09-01T11:00:00.000000+00:00",
        observed_at="2026-09-05T11:45:00.000000+00:00",
        known_at="2026-09-05T12:00:00.000000+00:00",
    )
    assert store.latest_social_document("hn:1", "NOW")["body"] == "edited"


@pytest.mark.unit
def test_documents_are_ordered_by_event_time(store):
    for i, when in enumerate(("2026-09-03", "2026-09-01", "2026-09-02")):
        store.insert_social_document(
            doc_id=f"hn:{i}", source="hackernews", kind="post", parent_id=None,
            ticker="NOW", author="a", url=f"https://x/{i}", title=None,
            body=f"b{i}", body_sha256=f"s{i}", score=1.0, score_contaminated=1,
            event_time=f"{when}T11:00:00.000000+00:00",
            observed_at=f"{when}T11:45:00.000000+00:00",
            known_at=f"{when}T12:00:00.000000+00:00",
        )
    events = [d["event_time"] for d in store.as_of(T).documents("NOW")]
    assert events == sorted(events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store_social.py -v`
Expected: FAIL with `AttributeError: 'Store' object has no attribute 'insert_social_document'`

- [ ] **Step 3: Add the table to `_SCHEMA` in `store.py`**

Append inside the `_SCHEMA` f-string, before the `CREATE INDEX` statements:

```sql
CREATE TABLE IF NOT EXISTS social_document (
    doc_id             TEXT NOT NULL,
    source             TEXT NOT NULL,
    kind               TEXT NOT NULL CHECK (kind IN ('post', 'comment')),
    parent_id          TEXT,
    ticker             TEXT NOT NULL,
    author             TEXT NOT NULL,
    url                TEXT NOT NULL,
    title              TEXT,
    body               TEXT NOT NULL,
    body_sha256        TEXT NOT NULL,
    -- Attention, never truth. See validate/weights.py and the namespace test.
    score              REAL,
    score_contaminated INTEGER NOT NULL DEFAULT 1,
    event_time         TEXT NOT NULL {_ts_check('event_time')},
    observed_at        TEXT NOT NULL {_ts_check('observed_at')},
    known_at           TEXT          {_ts_check('known_at')},
    PRIMARY KEY (doc_id, ticker, observed_at)
);
```

Add the index alongside the others:

```sql
CREATE INDEX IF NOT EXISTS ix_doc_known ON social_document (ticker, known_at);
```

- [ ] **Step 4: Add the column tuple to `_COLUMNS`**

```python
    "social_document": (
        "doc_id", "source", "kind", "parent_id", "ticker", "author", "url",
        "title", "body", "body_sha256", "score", "score_contaminated",
        "event_time", "observed_at", "known_at",
    ),
```

The tuple must match the `CREATE TABLE` column order exactly — `_rows` compares
`tuple(row)` against it, and a mismatch raises rather than silently passing.

- [ ] **Step 5: Add the writer to `Store`, next to the other `insert_*` methods**

```python
    def insert_social_document(self, **row: object) -> None:
        self._insert("social_document", row)

    def latest_social_document(
        self, doc_id: str, ticker: str
    ) -> dict[str, object] | None:
        """The most recently observed copy of a document, ignoring visibility.

        For the WRITER only. `observed_at` is part of the primary key, so a
        re-collection would otherwise append a fresh copy of every document and
        grow the table without bound. Append-only means a new row records new
        information: an edited body appends, an identical re-fetch does not.
        Readers must go through `as_of`.
        """
        row = self._conn.execute(
            "SELECT * FROM social_document WHERE doc_id = ? AND ticker = ? "
            "ORDER BY observed_at DESC LIMIT 1",
            (doc_id, ticker),
        ).fetchone()
        return dict(row) if row is not None else None
```

- [ ] **Step 6: Add the accessor to `PointInTimeView`**

```python
    def documents(self, ticker: str) -> list[dict[str, object]]:
        """Discussion documents attributed to `ticker` and visible at `t`."""
        columns = ", ".join(_COLUMNS["social_document"])
        return self._rows(
            "social_document",
            f"""
            SELECT {columns} FROM social_document
            WHERE ticker = :ticker
              AND known_at IS NOT NULL AND known_at <= :t
            ORDER BY event_time, doc_id
            """,
            {"ticker": ticker},
        )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_store_social.py -v`
Expected: PASS, 8 passed

- [ ] **Step 8: Verify the gates and the full suite**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: 165 passed, ruff clean, mypy clean

- [ ] **Step 9: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/store.py stock-trading-bot/tests/test_store_social.py
git commit -m "feat(stock-trading-bot): social_document table and point-in-time accessor"
```

---

### Task 2: Normalize collector output into store rows

**Files:**
- Create: `src/stock_trading_bot/ingest/social.py`
- Test: `tests/test_ingest_social.py`

The collectors emit ISO-8601 strings of varying shape (HN Algolia returns
`2026-09-01T11:00:00.000Z`; the Reddit scraper returns whatever the page rendered). Every one
must be normalized through `to_iso`, and anything unparseable must be refused rather than
guessed at — a document with a wrong `event_time` is a document that becomes visible at the
wrong moment.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_ingest_social.py`:

```python
from datetime import UTC, datetime

import pytest

from stock_trading_bot.ingest.social import normalize_discussion

BUDGET = {"hackernews": 3600}
OBSERVED = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)

DISCUSSION = {
    "id": "41234567",
    "url": "https://news.ycombinator.com/item?id=41234567",
    "external_url": "https://example.com/article",
    "title": "ServiceNow raises FY guidance",
    "source": "hackernews",
    "subreddit": "hackernews",
    "author": "alice",
    "created_utc": "2026-09-01T11:00:00.000Z",
    "score": 128,
    "num_comments": 2,
    "content": "The 8-K is out.",
    "comments": [
        {"id": "41234568", "author": "bob", "created_utc": "2026-09-01T11:30:00.000Z",
         "score": 12, "content": "Guidance raise is small.", "depth": 0},
        {"id": "41234569", "author": "carol", "created_utc": "2026-09-01T12:00:00.000Z",
         "score": 3, "content": "Seat erosion is the real risk.", "depth": 1},
    ],
}


def _rows(discussion=DISCUSSION):
    return normalize_discussion(
        discussion, ticker="NOW", observed_at=OBSERVED, latency_budget=BUDGET
    )


@pytest.mark.unit
def test_a_post_and_its_comments_each_become_a_row():
    assert len(_rows()) == 3


@pytest.mark.unit
def test_the_post_is_marked_post_and_comments_are_marked_comment():
    kinds = [r["kind"] for r in _rows()]
    assert kinds == ["post", "comment", "comment"]


@pytest.mark.unit
def test_comments_carry_the_post_as_parent():
    comments = [r for r in _rows() if r["kind"] == "comment"]
    assert {c["parent_id"] for c in comments} == {"hackernews:41234567"}


@pytest.mark.unit
def test_doc_ids_are_namespaced_by_source():
    """Reddit and HN both use bare numeric ids; without a namespace they collide."""
    assert _rows()[0]["doc_id"] == "hackernews:41234567"


@pytest.mark.unit
def test_every_timestamp_is_canonical():
    for row in _rows():
        for column in ("event_time", "observed_at", "known_at"):
            assert str(row[column]).endswith("+00:00")
            assert len(str(row[column])) == len("2026-09-01T11:00:00.000000+00:00")


@pytest.mark.unit
def test_known_at_is_event_time_plus_the_source_budget_or_later():
    """A document is usable once collected and processed, never when posted."""
    row = _rows()[0]
    assert str(row["known_at"]) > str(row["event_time"])
    assert row["known_at"] == "2026-09-02T11:00:00.000000+00:00"  # observed + 3600s


@pytest.mark.unit
def test_the_body_hash_is_stable_and_content_addressed():
    first, second = _rows()[0], _rows()[0]
    assert first["body_sha256"] == second["body_sha256"]
    assert len(str(first["body_sha256"])) == 64


@pytest.mark.unit
def test_score_is_carried_but_flagged_contaminated():
    assert _rows()[0]["score"] == 128.0
    assert _rows()[0]["score_contaminated"] == 1


@pytest.mark.unit
def test_an_unparseable_timestamp_is_refused_not_guessed():
    bad = {**DISCUSSION, "created_utc": "last Tuesday"}
    with pytest.raises(ValueError, match="timestamp"):
        normalize_discussion(bad, ticker="NOW", observed_at=OBSERVED,
                             latency_budget=BUDGET)


@pytest.mark.unit
def test_an_empty_body_is_skipped_rather_than_stored():
    quiet = {**DISCUSSION, "content": "", "comments": []}
    assert _rows(quiet) == []


@pytest.mark.unit
def test_the_ticker_is_sanitized():
    with pytest.raises(ValueError):
        normalize_discussion(DISCUSSION, ticker="../x", observed_at=OBSERVED,
                             latency_budget=BUDGET)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingest_social.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.social'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/social.py`:

```python
"""Normalize collector output into point-in-time store rows (spec §6.1).

The HN and Reddit collectors in market-research/scripts/ emit the same record
shape. This module turns one discussion - a post plus its comments - into
`social_document` rows carrying the four timestamps.

Two refusals, both for the same reason: a document with a wrong event_time
becomes visible at the wrong moment, which is a leak that looks like data.

  - An unparseable timestamp raises rather than defaulting to "now".
  - An empty body is skipped; a document with no text cannot support an
    evidence span, so storing it only inflates counts.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.timestamps import known_at_for, to_iso


def _parse_created(raw: object) -> datetime:
    """Parse a collector timestamp, refusing anything ambiguous."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"missing or non-text timestamp: {raw!r}")
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"unparseable timestamp: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no offset, refusing to guess: {raw!r}")
    return parsed


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_discussion(
    discussion: Mapping[str, Any],
    ticker: str,
    observed_at: datetime,
    latency_budget: Mapping[str, int],
) -> list[dict[str, object]]:
    """One discussion becomes one post row plus one row per comment."""
    symbol = safe_ticker_component(ticker)
    source = str(discussion.get("source") or "unknown")
    known_at = to_iso(known_at_for(observed_at, source, latency_budget))
    observed_iso = to_iso(observed_at)

    post_id = f"{source}:{discussion['id']}"
    url = str(discussion.get("url") or "")

    def row(
        doc_id: str, kind: str, parent_id: str | None, author: str,
        body: str, created: object, score: object, title: str | None,
    ) -> dict[str, object]:
        return {
            "doc_id": doc_id,
            "source": source,
            "kind": kind,
            "parent_id": parent_id,
            "ticker": symbol,
            "author": str(author or "unknown"),
            "url": url,
            "title": title,
            "body": body,
            "body_sha256": _sha256(body),
            "score": float(score or 0),
            # Scraped engagement is as-of-scrape, not as-of-t. Unfixable by
            # scraping; flagged so it cannot be silently used as evidence.
            "score_contaminated": 1,
            "event_time": to_iso(_parse_created(created)),
            "observed_at": observed_iso,
            "known_at": known_at,
        }

    rows: list[dict[str, object]] = []

    body = str(discussion.get("content") or "").strip()
    if body:
        rows.append(row(
            post_id, "post", None, discussion.get("author", ""), body,
            discussion.get("created_utc"), discussion.get("score"),
            discussion.get("title"),
        ))

    for comment in discussion.get("comments") or []:
        text = str(comment.get("content") or "").strip()
        if not text:
            continue
        rows.append(row(
            f"{source}:{comment['id']}", "comment", post_id,
            comment.get("author", ""), text, comment.get("created_utc"),
            comment.get("score"), None,
        ))

    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingest_social.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/social.py stock-trading-bot/tests/test_ingest_social.py
git commit -m "feat(stock-trading-bot): normalize collector output into store rows"
```

---

### Task 3: Ticker attribution and ambiguity

**Files:**
- Create: `src/stock_trading_bot/validate/__init__.py`
- Create: `src/stock_trading_bot/validate/tickers.py`
- Test: `tests/test_validate_tickers.py`

Spec §6.6. Symbols that are also ordinary English words — `NOW`, `ON`, `ALL`, `KEY`, `IT`,
`GOOD`, `SNOW` — match only on `$TICKER` or a full company-name mention. This is the corpus
rule and is stricter than CLI argument resolution, where the argument position already
disambiguates.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_validate_tickers.py`:

```python
import pytest

from stock_trading_bot.config import load_watchlist
from stock_trading_bot.validate.tickers import mentions_ticker, tickers_mentioned

WL = load_watchlist()


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "$NOW is up again",
    "ServiceNow raised guidance",
    "servicenow is a monopoly",
    "Service Now finally shipped it",
])
def test_an_ambiguous_ticker_matches_a_cashtag_or_a_company_name(text):
    assert mentions_ticker(text, WL.entry("NOW")) is True


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "I'll do it now",
    "now that I think about it",
    "NOW is the time to buy bonds",      # bare token, even shouted
    "Right NOW the market is closed",
    "snow is falling",                    # unrelated word
])
def test_an_ambiguous_ticker_does_not_match_a_bare_word(text):
    assert mentions_ticker(text, WL.entry("NOW")) is False


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "NVDA beat again",
    "$NVDA to the moon",
    "NVIDIA is the whole market",
    "nvidia earnings tomorrow",
])
def test_an_unambiguous_ticker_matches_a_bare_token(text):
    assert mentions_ticker(text, WL.entry("NVDA")) is True


@pytest.mark.unit
def test_an_unambiguous_ticker_does_not_match_inside_another_word():
    assert mentions_ticker("NVDAX fund", WL.entry("NVDA")) is False
    assert mentions_ticker("MYNVDA", WL.entry("NVDA")) is False


@pytest.mark.unit
def test_snow_requires_a_cashtag_because_it_is_a_common_word():
    assert mentions_ticker("snow is falling in Denver", WL.entry("SNOW")) is False
    assert mentions_ticker("$SNOW earnings", WL.entry("SNOW")) is True
    assert mentions_ticker("Snowflake earnings", WL.entry("SNOW")) is True


@pytest.mark.unit
def test_a_document_can_mention_several_tickers():
    text = "Comparing $NOW and NVDA and Salesforce this quarter"
    assert tickers_mentioned(text, WL) == ("CRM", "NOW", "NVDA")


@pytest.mark.unit
def test_no_mention_returns_empty():
    assert tickers_mentioned("the weather is bad", WL) == ()


@pytest.mark.unit
def test_matching_is_not_confused_by_punctuation():
    assert mentions_ticker("(NVDA)", WL.entry("NVDA")) is True
    assert mentions_ticker("NVDA's margins", WL.entry("NVDA")) is True
    assert mentions_ticker("buy NVDA.", WL.entry("NVDA")) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validate_tickers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.validate'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/validate/__init__.py` (empty), then
`stock-trading-bot/src/stock_trading_bot/validate/tickers.py`:

```python
"""Ticker attribution for discussion text (spec §6.6).

Symbols that are also ordinary English words - NOW, ON, ALL, KEY, IT, GOOD,
SNOW - match only on a cashtag or a full company-name mention. Matching them as
bare tokens would attribute "I'll do it now" to ServiceNow, and at a 5-15 name
universe a handful of such false positives is a material fraction of the corpus.

This is stricter than the CLI's argument resolution, where the argument
position already disambiguates what a scraped sentence cannot.
"""
from __future__ import annotations

import re
from functools import lru_cache

from stock_trading_bot.config import Watchlist, WatchlistEntry


@lru_cache(maxsize=512)
def _word_pattern(word: str) -> re.Pattern[str]:
    """Match `word` as a whole token, case-insensitively."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", re.IGNORECASE)


@lru_cache(maxsize=512)
def _cashtag_pattern(symbol: str) -> re.Pattern[str]:
    return re.compile(rf"\${re.escape(symbol)}(?![A-Za-z0-9])", re.IGNORECASE)


def mentions_ticker(text: str, entry: WatchlistEntry) -> bool:
    """Whether `text` refers to `entry`'s company."""
    if _cashtag_pattern(entry.symbol).search(text):
        return True
    for name in (entry.name, *entry.aliases):
        if _word_pattern(name).search(text):
            return True
    if entry.require_cashtag:
        return False
    return bool(_word_pattern(entry.symbol).search(text))


def tickers_mentioned(text: str, watchlist: Watchlist) -> tuple[str, ...]:
    """Every watchlist symbol `text` refers to, sorted for determinism."""
    return tuple(sorted(
        entry.symbol for entry in watchlist.entries if mentions_ticker(text, entry)
    ))
```

Note `entry.name` is `"ServiceNow, Inc."`, which will not match the bare word
`"ServiceNow"` — that is what the `aliases` list is for, and the shipped watchlist already
carries `"ServiceNow"` as an alias. If a test fails on this, add the alias rather than
loosening the pattern.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validate_tickers.py -v`
Expected: PASS, 18 passed

- [ ] **Step 5: Extend the import-graph guard to cover `validate/`**

In `tests/test_import_graph.py`, change:

```python
DOWNSTREAM = ("features", "model", "evaluate", "report")
```

to:

```python
DOWNSTREAM = ("validate", "features", "model", "evaluate", "report")
```

Then prove the guard still bites, exactly as in the foundation:

```bash
echo "from stock_trading_bot.ingest import social" > src/stock_trading_bot/validate/__init__.py
.venv/bin/pytest tests/test_import_graph.py -q     # expect FAIL
: > src/stock_trading_bot/validate/__init__.py
.venv/bin/pytest tests/test_import_graph.py -q     # expect PASS
```

- [ ] **Step 6: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/validate stock-trading-bot/tests/test_validate_tickers.py stock-trading-bot/tests/test_import_graph.py
git commit -m "feat(stock-trading-bot): ticker attribution with cashtag requirement"
```

---

### Task 4: Ingest-time deduplication

**Files:**
- Create: `src/stock_trading_bot/validate/dedup.py`
- Test: `tests/test_validate_dedup.py`

Spec §6.2, passes 1 and 2. Exact body hash catches re-scrapes; canonical URL catches
crossposts and tracking-parameter variants. Pass 3 (near-duplicate) is Task 5.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_validate_dedup.py`:

```python
import pytest

from stock_trading_bot.validate.dedup import canonical_url, dedupe_exact


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("https://example.com/a?utm_source=x&utm_medium=y", "https://example.com/a"),
    ("https://example.com/a?ref=hn", "https://example.com/a"),
    ("https://example.com/a?id=7&utm_campaign=z", "https://example.com/a?id=7"),
    ("https://example.com/a#section", "https://example.com/a"),
    ("https://EXAMPLE.com/a", "https://example.com/a"),
    ("https://example.com/a/", "https://example.com/a"),
    ("http://example.com/a", "http://example.com/a"),
])
def test_tracking_parameters_and_noise_are_stripped(raw, expected):
    assert canonical_url(raw) == expected


@pytest.mark.unit
def test_a_meaningful_query_parameter_survives():
    """Stripping every parameter would collapse genuinely distinct pages."""
    assert canonical_url("https://news.ycombinator.com/item?id=41234567") == (
        "https://news.ycombinator.com/item?id=41234567"
    )


@pytest.mark.unit
def test_an_empty_url_is_preserved_not_crashed_on():
    assert canonical_url("") == ""


@pytest.mark.unit
def test_identical_bodies_collapse_to_one():
    docs = [
        {"doc_id": "a", "body_sha256": "h1", "url": "https://x/1"},
        {"doc_id": "b", "body_sha256": "h1", "url": "https://x/2"},
        {"doc_id": "c", "body_sha256": "h2", "url": "https://x/3"},
    ]
    assert [d["doc_id"] for d in dedupe_exact(docs)] == ["a", "c"]


@pytest.mark.unit
def test_the_same_article_crossposted_collapses_to_one():
    docs = [
        {"doc_id": "a", "body_sha256": "h1", "url": "https://x/1?utm_source=hn"},
        {"doc_id": "b", "body_sha256": "h2", "url": "https://x/1?utm_source=reddit"},
    ]
    assert [d["doc_id"] for d in dedupe_exact(docs)] == ["a"]


@pytest.mark.unit
def test_the_first_occurrence_wins_so_the_result_is_deterministic():
    docs = [
        {"doc_id": "b", "body_sha256": "h1", "url": "https://x/1"},
        {"doc_id": "a", "body_sha256": "h1", "url": "https://x/1"},
    ]
    assert [d["doc_id"] for d in dedupe_exact(docs)] == ["b"]


@pytest.mark.unit
def test_documents_without_a_url_dedupe_on_body_alone():
    """Comments carry their parent's URL or none; they must not all collapse."""
    docs = [
        {"doc_id": "a", "body_sha256": "h1", "url": ""},
        {"doc_id": "b", "body_sha256": "h2", "url": ""},
    ]
    assert len(dedupe_exact(docs)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validate_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.validate.dedup'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/validate/dedup.py`:

```python
"""Deduplication passes 1 and 2 (spec §6.2).

Cheap before expensive: an exact body hash catches re-scrapes, and a canonical
URL catches crossposts and tracking-parameter variants. Near-duplicate
detection is the expensive third pass and lives in cluster.py.

Deduplication matters here for the same reason influence capping does: without
it, one article posted to four subreddits looks like four independent
observations of the same event.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: Query parameters that identify the referrer, not the content.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset({"ref", "source", "fbclid", "gclid", "igshid", "mc_cid"})


def canonical_url(raw: str) -> str:
    """Strip tracking noise so two links to the same page compare equal.

    Deliberately conservative: only known tracking keys are removed. Dropping
    every parameter would collapse genuinely distinct pages, and
    `news.ycombinator.com/item?id=N` is the obvious counterexample.
    """
    if not raw:
        return ""
    parts = urlsplit(raw.strip())
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS
        and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((
        parts.scheme.lower(), parts.netloc.lower(), path, urlencode(kept), ""
    ))


def dedupe_exact(
    documents: Iterable[Mapping[str, object]]
) -> Sequence[Mapping[str, object]]:
    """Drop documents repeating a body hash or a canonical URL already seen.

    First occurrence wins, so the result is deterministic for a given input
    order. Documents with no URL dedupe on body alone - comments share their
    parent's link, and collapsing them all would delete the discussion.
    """
    seen_bodies: set[object] = set()
    seen_urls: set[str] = set()
    kept: list[Mapping[str, object]] = []

    for document in documents:
        body_hash = document["body_sha256"]
        url = canonical_url(str(document.get("url") or ""))
        if body_hash in seen_bodies or (url and url in seen_urls):
            continue
        seen_bodies.add(body_hash)
        if url:
            seen_urls.add(url)
        kept.append(document)

    return kept
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validate_dedup.py -v`
Expected: PASS, 13 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/validate/dedup.py stock-trading-bot/tests/test_validate_dedup.py
git commit -m "feat(stock-trading-bot): exact-hash and canonical-URL deduplication"
```

---

### Task 5: Near-duplicate detection

**Files:**
- Modify: `src/stock_trading_bot/validate/dedup.py`
- Test: `tests/test_validate_neardup.py`

Spec §6.2 pass 3. Catches reposts, quoted-article boilerplate, and copypasta that pass 1 and 2
miss because a single character differs.

Comparison is quadratic, so candidates are generated by a time window first: only documents
within `window_days` of each other are compared. That bound is what keeps a few thousand
documents tractable, and it is the same windowing Task 6 needs for clustering.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_validate_neardup.py`:

```python
import pytest

from stock_trading_bot.validate.dedup import dedupe_near, jaccard, shingles

BASE = "ServiceNow raised full year subscription revenue guidance to fifteen billion"


def _doc(doc_id, body, day=1):
    return {
        "doc_id": doc_id,
        "body": body,
        "body_sha256": f"sha-{doc_id}",
        "url": "",
        "event_time": f"2026-09-{day:02d}T12:00:00.000000+00:00",
    }


@pytest.mark.unit
def test_shingles_of_a_short_text_are_non_empty():
    assert shingles("one two three four five six", k=3)


@pytest.mark.unit
def test_a_text_shorter_than_k_still_yields_one_shingle():
    """Otherwise every short comment has an empty set and matches every other."""
    assert len(shingles("hello there", k=5)) == 1


@pytest.mark.unit
def test_identical_texts_have_jaccard_one():
    assert jaccard(shingles(BASE), shingles(BASE)) == 1.0


@pytest.mark.unit
def test_unrelated_texts_have_low_jaccard():
    other = "The weather in Denver is cold and there is snow on the ground today"
    assert jaccard(shingles(BASE), shingles(other)) < 0.1


@pytest.mark.unit
def test_two_empty_shingle_sets_are_not_similar():
    """0/0 must not be 1.0, or two empty documents would collapse together."""
    assert jaccard(frozenset(), frozenset()) == 0.0


@pytest.mark.unit
def test_a_repost_with_a_trailing_edit_is_caught():
    docs = [_doc("a", BASE), _doc("b", BASE + " (edit: typo)")]
    assert [d["doc_id"] for d in dedupe_near(docs)] == ["a"]


@pytest.mark.unit
def test_a_genuinely_different_comment_survives():
    docs = [_doc("a", BASE), _doc("b", "Seat erosion is the real risk here, not AI")]
    assert [d["doc_id"] for d in dedupe_near(docs)] == ["a", "b"]


@pytest.mark.unit
def test_documents_far_apart_in_time_are_not_compared():
    """The same phrase three weeks later is a new event, not a duplicate."""
    docs = [_doc("a", BASE, day=1), _doc("b", BASE, day=25)]
    assert [d["doc_id"] for d in dedupe_near(docs, window_days=3)] == ["a", "b"]


@pytest.mark.unit
def test_the_earliest_document_survives_a_duplicate_group():
    """Keeping the earliest is the point-in-time-honest choice: the repost adds
    no information that was not already available."""
    docs = [_doc("late", BASE, day=3), _doc("early", BASE, day=1)]
    assert [d["doc_id"] for d in dedupe_near(docs)] == ["early"]


@pytest.mark.unit
def test_a_chain_of_near_duplicates_collapses_to_one():
    docs = [
        _doc("a", BASE),
        _doc("b", BASE + " today"),
        _doc("c", BASE + " today, per the 8-K"),
    ]
    assert len(dedupe_near(docs)) == 1


@pytest.mark.unit
def test_the_threshold_is_honoured():
    docs = [_doc("a", BASE), _doc("b", BASE + " (edit: typo)")]
    assert len(dedupe_near(docs, threshold=0.999)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validate_neardup.py -v`
Expected: FAIL with `ImportError: cannot import name 'shingles'`

- [ ] **Step 3: Append the implementation to `validate/dedup.py`**

```python
_DEFAULT_SHINGLE_K = 5
_DEFAULT_THRESHOLD = 0.85
_DEFAULT_WINDOW_DAYS = 3


def shingles(text: str, k: int = _DEFAULT_SHINGLE_K) -> frozenset[str]:
    """Word k-grams, lowercased.

    A text shorter than k yields a single shingle rather than the empty set,
    because an empty set would compare equal to every other empty set and
    collapse all short comments together.
    """
    words = text.lower().split()
    if len(words) <= k:
        return frozenset({" ".join(words)}) if words else frozenset()
    return frozenset(
        " ".join(words[i:i + k]) for i in range(len(words) - k + 1)
    )


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Set similarity. Two empty sets score 0.0, not 1.0."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _event_day(document: Mapping[str, object]) -> str:
    return str(document["event_time"])[:10]


def _within_window(left: str, right: str, window_days: int) -> bool:
    """Compare two YYYY-MM-DD strings as dates."""
    delta = date.fromisoformat(left) - date.fromisoformat(right)
    return abs(delta.days) <= window_days


def dedupe_near(
    documents: Sequence[Mapping[str, object]],
    threshold: float = _DEFAULT_THRESHOLD,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    shingle_k: int = _DEFAULT_SHINGLE_K,
) -> Sequence[Mapping[str, object]]:
    """Drop near-duplicates, keeping the earliest member of each group.

    Keeping the earliest is the point-in-time-honest choice: a repost carries
    no information that was not already available when the original appeared.

    Comparison is quadratic, so only documents within `window_days` of each
    other are compared. The same phrase three weeks later is a new event, not
    a duplicate.
    """
    ordered = sorted(documents, key=lambda d: (str(d["event_time"]), str(d["doc_id"])))
    fingerprints = [shingles(str(d["body"]), shingle_k) for d in ordered]

    dropped: set[int] = set()
    for i, left in enumerate(ordered):
        if i in dropped:
            continue
        for j in range(i + 1, len(ordered)):
            if j in dropped:
                continue
            if not _within_window(_event_day(ordered[j]), _event_day(left), window_days):
                break  # ordered by time, so nothing later is in range either
            if jaccard(fingerprints[i], fingerprints[j]) >= threshold:
                dropped.add(j)

    return [d for i, d in enumerate(ordered) if i not in dropped]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validate_neardup.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/validate/dedup.py stock-trading-bot/tests/test_validate_neardup.py
git commit -m "feat(stock-trading-bot): near-duplicate detection with time-windowed candidates"
```

---

### Task 6: Event clustering

**Files:**
- Create: `src/stock_trading_bot/validate/cluster.py`
- Test: `tests/test_validate_cluster.py`

Spec §6.3. **This is the task that makes "3,000 comments about one event are not 3,000
independent observations" mechanical rather than aspirational.** Clusters drive three things
downstream: sample weighting, bootstrap resampling units, and purge boundaries.

Clusters are computed from the visible document set and never stored. A cluster is a property
of what was visible when you looked, so materializing one would be wrong the moment a
walk-forward backtest steps to a different `t`.

TF-IDF cosine rather than Jaccard, because IDF downweights the vocabulary every document about
a company shares — the ticker, "earnings", "guidance" — which is exactly what separates one
event from another.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_validate_cluster.py`:

```python
import pytest

from stock_trading_bot.validate.cluster import cluster_documents, effective_sample_size

EARNINGS = [
    "ServiceNow Q2 subscription revenue grew 24 percent beating guidance",
    "Q2 subscription revenue up 24 percent, guidance raised for the year",
    "The Q2 print shows subscription revenue growth of 24 percent",
]
LAYOFFS = [
    "ServiceNow announced a restructuring affecting 400 roles in support",
    "Restructuring hits 400 support roles according to the filing",
]


def _docs(*groups, day=1):
    out, n = [], 0
    for group in groups:
        for body in group:
            out.append({
                "doc_id": f"d{n}", "body": body, "author": f"a{n}",
                "event_time": f"2026-09-{day:02d}T12:00:00.000000+00:00",
            })
            n += 1
    return out


@pytest.mark.unit
def test_documents_about_one_event_share_a_cluster():
    docs = _docs(EARNINGS)
    assignments = cluster_documents(docs)
    assert len(set(assignments.values())) == 1


@pytest.mark.unit
def test_documents_about_different_events_do_not_share_a_cluster():
    docs = _docs(EARNINGS, LAYOFFS)
    assignments = cluster_documents(docs)
    earnings_ids = {d["doc_id"] for d in docs[:3]}
    layoff_ids = {d["doc_id"] for d in docs[3:]}
    assert {assignments[i] for i in earnings_ids} != {assignments[i] for i in layoff_ids}
    assert len(set(assignments.values())) == 2


@pytest.mark.unit
def test_every_document_receives_a_cluster():
    docs = _docs(EARNINGS, LAYOFFS)
    assert set(cluster_documents(docs)) == {d["doc_id"] for d in docs}


@pytest.mark.unit
def test_a_lone_document_forms_its_own_cluster():
    assert len(set(cluster_documents(_docs(["a completely unrelated remark"])).values())) == 1


@pytest.mark.unit
def test_cluster_ids_are_deterministic_across_input_orderings():
    docs = _docs(EARNINGS, LAYOFFS)
    forward = cluster_documents(docs)
    backward = cluster_documents(list(reversed(docs)))
    assert forward == backward


@pytest.mark.unit
def test_documents_outside_the_window_do_not_cluster_together():
    """Identical text a month apart is a recurrence, not one event."""
    early = _docs(EARNINGS, day=1)
    late = _docs(EARNINGS, day=28)
    for i, d in enumerate(late):
        d["doc_id"] = f"late{i}"
    assignments = cluster_documents(early + late, window_days=3)
    assert len(set(assignments.values())) == 2


@pytest.mark.unit
def test_an_empty_corpus_yields_no_clusters():
    assert cluster_documents([]) == {}


@pytest.mark.unit
def test_effective_sample_size_counts_clusters_not_documents():
    """The number this whole module exists to produce."""
    docs = _docs(EARNINGS, LAYOFFS)
    assert len(docs) == 5
    assert effective_sample_size(cluster_documents(docs)) == 2


@pytest.mark.unit
def test_effective_sample_size_of_an_empty_corpus_is_zero():
    assert effective_sample_size({}) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validate_cluster.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.validate.cluster'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/validate/cluster.py`:

```python
"""Event clustering (spec §6.3).

This is where "3,000 comments about one event are not 3,000 independent
observations" stops being a principle and becomes a number. Clusters drive
sample weighting, bootstrap resampling units, and purge boundaries - one
concept, three uses.

Clusters are computed from the visible document set and never stored. A cluster
is a property of what was visible when you looked, so materializing one would be
wrong the moment a walk-forward backtest steps to a different `t`.

TF-IDF cosine rather than Jaccard: IDF downweights the vocabulary every document
about a company shares - the ticker, "earnings", "guidance" - which is exactly
what distinguishes one event from another. Implemented in pure Python because
pulling scikit-learn in for thirty lines would make the lockfile overstate what
the ingestion layer needs.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date

_TOKEN = re.compile(r"[a-z0-9]+")
_DEFAULT_THRESHOLD = 0.35
_DEFAULT_WINDOW_DAYS = 3


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _tf_idf(corpus: Sequence[str]) -> list[dict[str, float]]:
    """L2-normalized TF-IDF vectors, one per document."""
    tokenized = [_tokens(text) for text in corpus]
    document_count = len(tokenized)
    seen_in = Counter(token for tokens in tokenized for token in set(tokens))

    vectors: list[dict[str, float]] = []
    for tokens in tokenized:
        counts = Counter(tokens)
        vector = {
            token: count * math.log((1 + document_count) / (1 + seen_in[token])) + 1.0
            for token, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vectors.append({token: value / norm for token, value in vector.items()})
    return vectors


def _cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


def cluster_documents(
    documents: Sequence[Mapping[str, object]],
    threshold: float = _DEFAULT_THRESHOLD,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> dict[str, str]:
    """Map each doc_id to a cluster id.

    Candidates are generated by a time window, then scored by TF-IDF cosine;
    connected components form the clusters. The cluster id is the smallest
    doc_id in the component, which makes the result independent of input order.
    """
    if not documents:
        return {}

    ordered = sorted(documents, key=lambda d: (str(d["event_time"]), str(d["doc_id"])))
    ids = [str(d["doc_id"]) for d in ordered]
    days = [date.fromisoformat(str(d["event_time"])[:10]) for d in ordered]
    vectors = _tf_idf([str(d["body"]) for d in ordered])

    parent = list(range(len(ordered)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[max(root_i, root_j)] = min(root_i, root_j)

    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            if (days[j] - days[i]).days > window_days:
                break  # time-ordered, so nothing later is in range either
            if _cosine(vectors[i], vectors[j]) >= threshold:
                union(i, j)

    members: dict[int, list[str]] = {}
    for index, doc_id in enumerate(ids):
        members.setdefault(find(index), []).append(doc_id)

    return {
        doc_id: min(group)
        for group in members.values()
        for doc_id in group
    }


def effective_sample_size(assignments: Mapping[str, str]) -> int:
    """Distinct clusters - the honest n for anything downstream.

    Report this alongside the raw document count everywhere a sample size
    appears. The gap between the two is the whole point.
    """
    return len(set(assignments.values()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validate_cluster.py -v`
Expected: PASS, 9 passed

If `test_documents_about_different_events_do_not_share_a_cluster` fails because both groups
merge, the threshold is too low for this corpus. **Do not raise the threshold until the test
passes and then move on** — check first that the two groups genuinely differ in vocabulary. A
threshold tuned to make one test pass is a threshold tuned to nothing; note the value you
chose and why in the commit message, and treat it as a parameter the Plan 4 sensitivity
analysis must vary.

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/validate/cluster.py stock-trading-bot/tests/test_validate_cluster.py
git commit -m "feat(stock-trading-bot): event clustering and effective sample size"
```

---

### Task 7: Author and cluster influence caps

**Files:**
- Create: `src/stock_trading_bot/validate/weights.py`
- Test: `tests/test_validate_weights.py`

Spec §6.4. Two caps correcting two different pathologies: one prolific poster must not become
the signal, and a viral thread must count for more than a quiet one but sublinearly.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_validate_weights.py`:

```python
import math

import pytest

from stock_trading_bot.validate.weights import (
    author_weights,
    cluster_weights,
    document_weights,
)


def _docs(spec, day=1):
    """spec: list of (doc_id, author)."""
    return [
        {"doc_id": i, "author": a,
         "event_time": f"2026-09-{day:02d}T12:00:00.000000+00:00"}
        for i, a in spec
    ]


@pytest.mark.unit
def test_a_single_post_carries_full_weight():
    assert author_weights(_docs([("d1", "alice")]), cap=3) == {"d1": 1.0}


@pytest.mark.unit
def test_an_author_under_the_cap_is_not_penalised():
    weights = author_weights(_docs([("d1", "a"), ("d2", "a"), ("d3", "a")]), cap=3)
    assert set(weights.values()) == {1.0}


@pytest.mark.unit
def test_a_prolific_author_is_capped():
    """Six posts from one author total three units, not six."""
    docs = _docs([(f"d{i}", "loud") for i in range(6)])
    weights = author_weights(docs, cap=3)
    assert sum(weights.values()) == pytest.approx(3.0)
    assert set(weights.values()) == {0.5}


@pytest.mark.unit
def test_authors_are_capped_independently():
    docs = _docs([("d1", "a"), ("d2", "a"), ("d3", "a"), ("d4", "a"), ("d5", "b")])
    weights = author_weights(docs, cap=2)
    assert weights["d5"] == 1.0
    assert sum(weights[f"d{i}"] for i in range(1, 5)) == pytest.approx(2.0)


@pytest.mark.unit
def test_the_cap_window_resets():
    """A steady contributor over months is not the same as a burst."""
    docs = _docs([("d1", "a"), ("d2", "a")], day=1) + _docs([("d3", "a")], day=28)
    weights = author_weights(docs, cap=1, window_days=7)
    assert weights["d3"] == 1.0


@pytest.mark.unit
def test_a_cluster_weight_grows_sublinearly():
    """A viral thread counts more than a quiet one, but not proportionally."""
    assert cluster_weights({"a": "c1"}) == {"c1": 1.0}
    assert cluster_weights({f"d{i}": "c1" for i in range(9)}) == {"c1": 3.0}


@pytest.mark.unit
def test_cluster_weights_are_independent_per_cluster():
    assignments = {"a": "c1", "b": "c1", "c": "c2", "d": "c2", "e": "c2", "f": "c2"}
    weights = cluster_weights(assignments)
    assert weights["c1"] == pytest.approx(math.sqrt(2))
    assert weights["c2"] == 2.0


@pytest.mark.unit
def test_document_weight_combines_both_caps():
    docs = _docs([("d1", "loud"), ("d2", "loud"), ("d3", "quiet")])
    assignments = {"d1": "c1", "d2": "c1", "d3": "c1"}
    weights = document_weights(docs, assignments, cap=1)
    # loud contributes 0.5 each, quiet 1.0; cluster of 3 scales to sqrt(3)/3 per unit
    assert sum(weights.values()) == pytest.approx(math.sqrt(3))
    assert weights["d3"] > weights["d1"]


@pytest.mark.unit
def test_document_weight_of_an_empty_corpus_is_empty():
    assert document_weights([], {}, cap=3) == {}


@pytest.mark.unit
def test_one_author_dominating_one_cluster_cannot_dominate_the_sample():
    """The pathology both caps exist to prevent, in one case."""
    docs = _docs([(f"d{i}", "loud") for i in range(50)] + [("real", "someone")])
    assignments = {d["doc_id"]: "c1" for d in docs}
    weights = document_weights(docs, assignments, cap=3)
    loud = sum(weights[f"d{i}"] for i in range(50))
    assert loud < 5 * weights["real"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validate_weights.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.validate.weights'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/validate/weights.py`:

```python
"""Influence caps (spec §6.4).

Two caps for two different pathologies:

  - Author: within a (ticker, window) period an author's posts total at most
    `cap` units of weight. One prolific poster cannot become the signal.
  - Cluster: a cluster totals sqrt(n) units rather than n. A viral thread
    counts for more than a quiet one, but sublinearly.

Both are pure functions of the visible document set, for the same reason
clustering is: the answer depends on what was visible at `t`.

Note what these caps do NOT use: `score`. Upvotes measure attention or
agreement, not truth, so they may only feed features in the `attention_*`
namespace. See tests/test_attention_namespace.py.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

_DEFAULT_AUTHOR_CAP = 3
_DEFAULT_WINDOW_DAYS = 30


def _window_key(event_time: str, window_days: int) -> int:
    """Which fixed window a document falls into."""
    return date.fromisoformat(event_time[:10]).toordinal() // window_days


def author_weights(
    documents: Sequence[Mapping[str, object]],
    cap: int = _DEFAULT_AUTHOR_CAP,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> dict[str, float]:
    """Per-document weight after capping each author's total per window."""
    buckets: dict[tuple[str, int], list[str]] = defaultdict(list)
    for document in documents:
        key = (
            str(document["author"]),
            _window_key(str(document["event_time"]), window_days),
        )
        buckets[key].append(str(document["doc_id"]))

    weights: dict[str, float] = {}
    for doc_ids in buckets.values():
        share = min(1.0, cap / len(doc_ids))
        for doc_id in doc_ids:
            weights[doc_id] = share
    return weights


def cluster_weights(assignments: Mapping[str, str]) -> dict[str, float]:
    """Total weight per cluster: sqrt(n_docs), not n_docs."""
    sizes: dict[str, int] = defaultdict(int)
    for cluster_id in assignments.values():
        sizes[cluster_id] += 1
    return {cluster_id: math.sqrt(size) for cluster_id, size in sizes.items()}


def document_weights(
    documents: Sequence[Mapping[str, object]],
    assignments: Mapping[str, str],
    cap: int = _DEFAULT_AUTHOR_CAP,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> dict[str, float]:
    """Final per-document weight: author-capped, then rescaled per cluster.

    Within a cluster, author-capped weights are rescaled so the cluster totals
    sqrt(n). Relative standing inside the cluster is preserved, so a capped
    author still counts for less than an occasional one.
    """
    if not documents:
        return {}

    by_author = author_weights(documents, cap=cap, window_days=window_days)

    members: dict[str, list[str]] = defaultdict(list)
    for doc_id, cluster_id in assignments.items():
        members[cluster_id].append(doc_id)

    weights: dict[str, float] = {}
    for cluster_id, doc_ids in members.items():
        raw = {doc_id: by_author.get(doc_id, 0.0) for doc_id in doc_ids}
        total = sum(raw.values())
        target = math.sqrt(len(doc_ids))
        scale = (target / total) if total else 0.0
        for doc_id, value in raw.items():
            weights[doc_id] = value * scale
    return weights
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validate_weights.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/validate/weights.py stock-trading-bot/tests/test_validate_weights.py
git commit -m "feat(stock-trading-bot): author and cluster influence caps"
```

---

### Task 8: The `attention_*` namespace guard

**Files:**
- Test: `tests/test_attention_namespace.py`

Spec §6.5. *Upvotes measure attention or agreement, not factual truth.* This encodes that so
it cannot drift as the codebase grows, in the same way the import-graph test encodes
dependency direction.

- [ ] **Step 1: Write the test**

Create `stock-trading-bot/tests/test_attention_namespace.py`:

```python
"""A score may only feed an attention feature, never a credibility one.

Upvotes measure attention or agreement, not factual truth (spec §6.5). Scraped
scores are also as-of-scrape rather than as-of-t, so they are contaminated as
well as weak. Both facts point the same way: `score` can say how much a claim
was noticed, never whether it is right.

This test scans the source for functions whose names promise truth and checks
none of them reads `score`.
"""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "stock_trading_bot"
TRUTH_PREFIXES = ("credibility_", "confidence_", "veracity_", "reliability_")
SCORE_NAMES = {"score", "num_comments", "upvotes", "points"}


def _functions() -> list[tuple[Path, ast.FunctionDef]]:
    found = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef):
                found.append((path, node))
    return found


def _reads_engagement(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and child.value in SCORE_NAMES:
            return True
        if isinstance(child, ast.Attribute) and child.attr in SCORE_NAMES:
            return True
        if isinstance(child, ast.Name) and child.id in SCORE_NAMES:
            return True
    return False


@pytest.mark.unit
def test_the_scan_finds_functions_so_this_test_is_not_vacuous():
    assert len(_functions()) > 10


@pytest.mark.unit
def test_no_truth_named_function_reads_an_engagement_count():
    offenders = [
        f"{path.relative_to(SRC)}::{node.name}"
        for path, node in _functions()
        if node.name.startswith(TRUTH_PREFIXES) and _reads_engagement(node)
    ]
    assert offenders == [], (
        "engagement counts may only feed attention_* features: " + "; ".join(offenders)
    )


@pytest.mark.unit
def test_the_influence_caps_do_not_use_score():
    """Weighting by upvotes would make popularity the signal."""
    weights = (SRC / "validate" / "weights.py").read_text()
    assert '"score"' not in weights
    assert "['score']" not in weights
```

- [ ] **Step 2: Prove the guard can fail**

```bash
cat >> src/stock_trading_bot/validate/weights.py <<'EOF'


def credibility_from_score(document: dict[str, object]) -> float:
    return float(document["score"] or 0)
EOF
.venv/bin/pytest tests/test_attention_namespace.py -q   # expect 2 FAILED
git checkout -- src/stock_trading_bot/validate/weights.py
.venv/bin/pytest tests/test_attention_namespace.py -q   # expect PASS
```

A guard test that has never failed is not known to be a guard.

- [ ] **Step 3: Commit**

```bash
git add stock-trading-bot/tests/test_attention_namespace.py
git commit -m "test(stock-trading-bot): engagement counts may only feed attention features"
```

---

### Task 9: HackerNews collector

**Files:**
- Create: `src/stock_trading_bot/ingest/hackernews.py`
- Test: `tests/test_ingest_hackernews.py`

**A deliberate deviation from the spec.** §6.1 said "reuse `collect_hn.py`, wrapped". On
inspection, that script writes timestamped files into `market-research/data/raw/` as a side
effect and is driven by CLI arguments — wrapping it would mean shelling out, writing files
into another project's tree, and reading them back, none of which is mockable. The collection
*strategy* is what was worth reusing, and it is small:

> Use 8–12 focused keyword queries, not one long sentence. Algolia ranks by keyword match, so
> "MLOps" and "GPU training" each return sharp results while a 12-word natural-language query
> returns noise. Run several, dedupe by `objectID`.

That strategy is carried over. The transport is forty lines of `requests`. Record the
deviation in the commit message.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_ingest_hackernews.py`:

```python
from unittest import mock

import pytest

from stock_trading_bot.ingest import hackernews

SEARCH = {"hits": [
    {"objectID": "1", "title": "ServiceNow raises guidance", "author": "alice",
     "created_at": "2026-09-01T11:00:00.000Z", "points": 128, "num_comments": 2,
     "url": "https://example.com/a", "story_text": "The 8-K is out."},
    {"objectID": "2", "title": "ServiceNow seat erosion", "author": "bob",
     "created_at": "2026-09-02T11:00:00.000Z", "points": 40, "num_comments": 0,
     "url": "", "story_text": "Fulfiller seats are the risk."},
]}
ITEM = {
    "id": 1, "children": [
        {"type": "comment", "id": 11, "author": "carol",
         "created_at": "2026-09-01T11:30:00.000Z", "points": 5,
         "text": "<p>Guidance raise is <i>small</i>.</p>", "children": []},
    ],
}


def _patched(search=SEARCH):
    def fake(url: str) -> dict:
        return search if "/search" in url else ITEM
    return mock.patch.object(hackernews, "_get_json", side_effect=fake)


@pytest.mark.unit
def test_collects_discussions_in_the_collector_record_shape():
    with _patched():
        found = hackernews.collect(["ServiceNow"], max_stories=5)
    assert {"id", "url", "title", "source", "author", "created_utc",
            "score", "num_comments", "content", "comments"} <= set(found[0])


@pytest.mark.unit
def test_the_source_is_tagged_so_doc_ids_are_namespaced():
    with _patched():
        assert hackernews.collect(["ServiceNow"])[0]["source"] == "hackernews"


@pytest.mark.unit
def test_html_is_stripped_from_comment_text():
    with _patched():
        comment = hackernews.collect(["ServiceNow"])[0]["comments"][0]
    assert comment["content"] == "Guidance raise is small."


@pytest.mark.unit
def test_duplicate_stories_across_queries_are_collected_once():
    with _patched():
        found = hackernews.collect(["ServiceNow", "NOW stock", "Now Assist"])
    assert len({d["id"] for d in found}) == len(found)


@pytest.mark.unit
def test_several_focused_queries_are_issued_rather_than_one_long_one():
    """Algolia ranks by keyword match, so focused queries return sharp results
    where a long natural-language query returns noise."""
    with _patched() as get:
        hackernews.collect(["ServiceNow", "Now Assist", "NOW earnings"])
    searches = [c.args[0] for c in get.call_args_list if "/search" in c.args[0]]
    assert len(searches) == 3


@pytest.mark.unit
def test_a_failing_query_does_not_lose_the_others():
    calls = {"n": 0}

    def flaky(url: str) -> dict:
        if "/search" in url:
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("boom")
            return SEARCH
        return ITEM

    with mock.patch.object(hackernews, "_get_json", side_effect=flaky):
        assert hackernews.collect(["a", "b"]) != []


@pytest.mark.unit
def test_no_hits_yields_no_discussions():
    with _patched(search={"hits": []}):
        assert hackernews.collect(["nothing"]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingest_hackernews.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.hackernews'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/hackernews.py`:

```python
"""HackerNews collection via the free Algolia API (spec §6.1).

Emits the same record shape as market-research/scripts/collect_hn.py, which
ingest/social.py normalizes. The collection strategy is carried over from that
script; the transport is reimplemented so it can be mocked and so collection
does not write files into another project's tree as a side effect.

The strategy that matters: issue several FOCUSED keyword queries rather than one
long natural-language phrase. Algolia ranks by keyword match, so "Now Assist"
and "NOW earnings" each return sharp results while a twelve-word sentence
returns noise. Dedupe by objectID across queries.
"""
from __future__ import annotations

import html
import re
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

import requests

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"
_UA = "stock-trading-bot/0.1 (research)"
_TAG = re.compile(r"<[^>]+>")


def _get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _clean(text: str | None) -> str:
    """Algolia returns comment bodies as HTML fragments."""
    if not text:
        return ""
    return html.unescape(_TAG.sub("", text)).strip()


def _comments(node: dict[str, Any], depth: int = 0, max_depth: int = 3,
              collected: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if collected is None:
        collected = []
    if depth > max_depth:
        return collected
    for child in node.get("children") or []:
        if child.get("type") == "comment" and child.get("text"):
            collected.append({
                "id": str(child.get("id", "")),
                "author": child.get("author") or "",
                "created_utc": child.get("created_at") or "",
                "score": child.get("points") or 0,
                "content": _clean(child.get("text")),
                "depth": depth,
            })
        _comments(child, depth + 1, max_depth, collected)
    return collected


def collect(
    queries: Sequence[str],
    max_stories: int = 15,
    min_points: int = 10,
    max_comments: int = 30,
    pause_seconds: float = 0.25,
) -> list[dict[str, Any]]:
    """Collect discussions for several focused queries, deduped by story id."""
    stories: dict[str, dict[str, Any]] = {}
    for query in queries:
        url = (
            f"{_SEARCH_URL}?query={quote(query)}&tags=story"
            f"&hitsPerPage={max_stories}&numericFilters=points%3E{min_points}"
        )
        try:
            hits = _get_json(url).get("hits") or []
        except Exception:
            # One dead query must not lose the others; a partial corpus is
            # visible in the coverage report, a lost run is not.
            continue
        for hit in hits:
            stories.setdefault(str(hit["objectID"]), hit)
        time.sleep(pause_seconds)

    discussions: list[dict[str, Any]] = []
    for story_id, story in stories.items():
        try:
            item = _get_json(_ITEM_URL.format(item_id=story_id))
        except Exception:
            continue
        discussions.append({
            "id": story_id,
            "url": f"https://news.ycombinator.com/item?id={story_id}",
            "external_url": story.get("url") or "",
            "title": story.get("title") or "",
            "source": "hackernews",
            "author": story.get("author") or "",
            "created_utc": story.get("created_at") or "",
            "score": story.get("points") or 0,
            "num_comments": story.get("num_comments") or 0,
            "content": _clean(story.get("story_text")) or story.get("title") or "",
            "comments": _comments(item)[:max_comments],
        })
        time.sleep(pause_seconds)

    return discussions
```

Note `pause_seconds` defaults to 0.25 for politeness against a free API but is a parameter so
tests run instantly — pass `pause_seconds=0` in the test module if the suite feels slow.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingest_hackernews.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/hackernews.py stock-trading-bot/tests/test_ingest_hackernews.py
git commit -m "feat(stock-trading-bot): HackerNews collector via Algolia

Deviation from spec §6.1, which said to wrap market-research/collect_hn.py.
That script writes timestamped files into another project's tree as a side
effect and is CLI-driven, so wrapping it would mean shelling out and reading
files back - not mockable, and the suite must run offline. The collection
strategy (several focused keyword queries, deduped by objectID) is what was
worth reusing and is carried over; the transport is reimplemented."
```

---

### Task 10: `stock-trading collect` command

**Files:**
- Modify: `src/stock_trading_bot/cli.py`
- Test: `tests/test_cli_collect.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_cli_collect.py`:

```python
from datetime import UTC, datetime
from unittest import mock

import pytest

from stock_trading_bot import cli
from stock_trading_bot.ingest import hackernews
from stock_trading_bot.store import Store

LATER = datetime(2027, 1, 1, tzinfo=UTC)

DISCUSSIONS = [{
    "id": "1", "url": "https://news.ycombinator.com/item?id=1",
    "external_url": "", "title": "ServiceNow raises guidance",
    "source": "hackernews", "author": "alice",
    "created_utc": "2026-09-01T11:00:00.000Z", "score": 128, "num_comments": 1,
    "content": "ServiceNow raised full year guidance in the 8-K today.",
    "comments": [{
        "id": "11", "author": "bob", "created_utc": "2026-09-01T11:30:00.000Z",
        "score": 5, "content": "Seat erosion is the real risk for $NOW.",
        "depth": 0,
    }],
}]


def _run(argv, discussions=DISCUSSIONS):
    with mock.patch.object(hackernews, "collect", return_value=discussions):
        return cli.main(argv)


@pytest.mark.unit
def test_collect_stores_documents_that_read_back(tmp_path, capsys):
    db = tmp_path / "panel.sqlite"
    assert _run(["collect", "ServiceNow", "--db", str(db)]) == 0
    docs = Store.open(db).as_of(LATER).documents("NOW")
    assert len(docs) == 2


@pytest.mark.unit
def test_collect_reports_effective_sample_size_next_to_the_raw_count(tmp_path, capsys):
    """The gap between document count and cluster count is the whole point."""
    _run(["collect", "ServiceNow", "--db", str(tmp_path / "p.sqlite")])
    out = capsys.readouterr().out
    assert "documents" in out and "clusters" in out


@pytest.mark.unit
def test_a_second_collect_does_not_duplicate(tmp_path):
    db = tmp_path / "panel.sqlite"
    _run(["collect", "ServiceNow", "--db", str(db)])
    _run(["collect", "ServiceNow", "--db", str(db)])
    assert len(Store.open(db).as_of(LATER).documents("NOW")) == 2


@pytest.mark.unit
def test_documents_are_attributed_only_to_mentioned_tickers(tmp_path):
    db = tmp_path / "panel.sqlite"
    _run(["collect", "ServiceNow", "--db", str(db)])
    view = Store.open(db).as_of(LATER)
    assert view.documents("NVDA") == []


@pytest.mark.unit
def test_an_off_watchlist_name_is_refused_with_a_clear_message(tmp_path, capsys):
    assert _run(["collect", "Wingdings Corp", "--db", str(tmp_path / "p.sqlite")]) == 1
    assert "not in the watchlist" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_collect.py -v`
Expected: FAIL — `collect` is not a recognized command, so `cli.main` returns 2

- [ ] **Step 3: Add the command to `cli.py`**

Add these imports:

```python
from stock_trading_bot.ingest import hackernews, social
from stock_trading_bot.validate.cluster import cluster_documents, effective_sample_size
from stock_trading_bot.validate.dedup import dedupe_exact, dedupe_near
from stock_trading_bot.validate.tickers import tickers_mentioned
```

Add the handler:

```python
def _collect(args: argparse.Namespace) -> int:
    watchlist = load_watchlist()
    symbol = watchlist.resolve(args.ticker)
    if symbol is None:
        print(f"{args.ticker!r} is not in the watchlist; add it to config/watchlist.yaml")
        return 1

    entry = watchlist.entry(symbol)
    queries = [entry.name, *entry.aliases, f"{symbol} earnings", f"{symbol} stock"]

    cfg = load_run_config()
    store = Store.open(args.db or resolve_path(cfg["paths"]["db"]))
    try:
        discussions = hackernews.collect(queries)
        observed_at = datetime.now(UTC)

        rows: list[dict[str, object]] = []
        for discussion in discussions:
            for row in social.normalize_discussion(
                discussion, ticker=symbol, observed_at=observed_at,
                latency_budget=cfg["latency_budget_seconds"],
            ):
                # Attribute only what actually mentions the company. A thread
                # surfaced by a query is not necessarily a thread about it.
                text = f"{row.get('title') or ''} {row['body']}"
                if symbol in tickers_mentioned(str(text), watchlist):
                    rows.append(row)

        kept = dedupe_near(dedupe_exact(rows))
        written, unchanged = 0, 0
        for row in kept:
            existing = store.latest_social_document(
                str(row["doc_id"]), str(row["ticker"])
            )
            # An edited body appends a new row; an identical re-fetch does not.
            if existing is not None and existing["body_sha256"] == row["body_sha256"]:
                unchanged += 1
                continue
            try:
                store.insert_social_document(**row)
                written += 1
            except sqlite3.IntegrityError:
                unchanged += 1

        assignments = cluster_documents(kept)
        print(
            f"{symbol}: {written} documents written, {unchanged} unchanged "
            f"({len(rows) - len(kept)} duplicates dropped), "
            f"{effective_sample_size(assignments)} clusters"
        )
    finally:
        store.close()
    return 0
```

Register it next to `ingest`:

```python
    collect = sub.add_parser("collect", help="collect and store discussion")
    collect.add_argument("ticker", help="ticker, company name, or watchlist alias")
    collect.add_argument("--db", default=None)
    collect.set_defaults(func=_collect)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_collect.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Verify the whole suite and both gates**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/cli.py stock-trading-bot/tests/test_cli_collect.py
git commit -m "feat(stock-trading-bot): collect command reporting clusters beside documents"
```

---

### Task 11: Live end-to-end

**Files:** none — this is verification.

- [ ] **Step 1: Collect a real corpus**

```bash
cd /Users/duochen/Desktop/career/openPaw/stock-trading-bot
rm -f data/db/live.sqlite
for name in ServiceNow NVIDIA Salesforce; do
  PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli collect "$name" --db "$PWD/data/db/live.sqlite"
done
```

Expected: a nonzero document count for each, with the cluster count **visibly smaller** than
the document count. If clusters equal documents, clustering is not working — investigate
before proceeding rather than accepting the number.

- [ ] **Step 2: Verify point-in-time visibility**

```bash
PYTHONPATH=src .venv/bin/python -c "
from datetime import UTC, datetime, timedelta
from stock_trading_bot.store import Store
from stock_trading_bot.validate.cluster import cluster_documents, effective_sample_size

store = Store.open('data/db/live.sqlite')
now = datetime.now(UTC)
for label, t in [('now + 1d', now + timedelta(days=1)), ('1 year ago', now - timedelta(days=365))]:
    view = store.as_of(t)
    for ticker in ('NOW', 'NVDA', 'CRM'):
        docs = view.documents(ticker)
        n = effective_sample_size(cluster_documents(docs)) if docs else 0
        print(f'{label:12} {ticker:5} docs={len(docs):4} clusters={n:4}')
"
```

Expected: real counts at `now + 1d`; **all zeros at `1 year ago`**, because `known_at` is
today. A nonzero count in the past means the latency budget or `known_at` derivation is wrong,
which is a leak.

- [ ] **Step 3: Sanity-check attribution by eye**

```bash
PYTHONPATH=src .venv/bin/python -c "
from datetime import UTC, datetime, timedelta
from stock_trading_bot.store import Store
view = Store.open('data/db/live.sqlite').as_of(datetime.now(UTC) + timedelta(days=1))
for d in view.documents('NOW')[:5]:
    print(f\"  [{d['kind']:7}] {str(d['body'])[:110]}\")
"
```

Read the output. Every document should plausibly be about ServiceNow. **If any is a false
positive from the bare word "now", the `require_cashtag` rule is not being applied** — fix it
before moving on, because at a 5–15 name universe a handful of false positives is a material
fraction of the corpus.

- [ ] **Step 4: Record what you found**

Note the realized document count, duplicate-drop rate, and cluster count per ticker in the
commit message. These are the first real numbers for the coverage section of the eventual
report, and the documents-to-clusters ratio is the number that will decide whether Plan 4's
evaluation has any power at all.

- [ ] **Step 5: Clean up and commit**

```bash
rm -f data/db/live.sqlite
git commit --allow-empty -m "chore(stock-trading-bot): live social ingestion verified

<record the counts here>"
```

---

## Definition of done

- [ ] `.venv/bin/pytest` passes; `ruff` and `mypy --strict` clean.
- [ ] The import-graph guard covers `validate/` and was shown to fail on a violation.
- [ ] The attention-namespace guard was shown to fail on a violation.
- [ ] A fresh corpus collects, ingests, and reads back point-in-time correctly, with zero
      documents visible a year ago.
- [ ] Cluster count is reported beside document count everywhere a count appears.
- [ ] Ticker attribution was checked by eye against real collected text.
- [ ] No credentials in source or logs. The suite runs offline.

## What this plan deliberately does not do

- **No Reddit.** The collector is browser-dependent and already broke once. HN alone is enough
  to build against, and Plan 4's source-mix sensitivity is what will make a dead source
  visible rather than silently degrading.
- **No LLM extraction.** Plan 3.
- **No features or model.** Plan 4. Nothing here computes a number that predicts anything, and
  nothing here should.
- **No stored clusters.** Clustering is a pure function of the visible set at `t`. Materializing
  it would be wrong the moment a walk-forward backtest steps to a different `t`.
