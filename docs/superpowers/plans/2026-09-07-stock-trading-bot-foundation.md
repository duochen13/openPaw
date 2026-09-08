# stock-trading-bot Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the point-in-time data foundation for `stock-trading-bot` — a SQLite store whose gateway makes look-ahead leakage structurally impossible, plus price and SEC filing ingestion behind it.

**Architecture:** A `src/` layout Python package. All facts land in append-only SQLite tables carrying four timestamps. Consumers never touch the connection; they receive a `PointInTimeView` from `store.as_of(t)` that filters every query on `known_at <= t`. Ingestion adapters route all present-day-only vendor fields through one shared withhold rule so swapping providers cannot reintroduce a leak.

**Tech Stack:** Python 3.13, `uv` for dependency management (Homebrew `pip` is broken on this machine), stdlib `sqlite3`, `requests`, `pydantic` v2, `pyyaml`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-07-stock-trading-bot-design.md` (§4, §5, §6.1, §12)

**Branch:** `feat/stock-trading-bot`

---

## File Structure

| File | Responsibility |
|---|---|
| `stock-trading-bot/pyproject.toml` | Package metadata, deps, pytest config |
| `stock-trading-bot/config/run.yaml` | Latency budgets, data paths |
| `stock-trading-bot/config/watchlist.yaml` | Tickers and aliases |
| `src/stock_trading_bot/naming.py` | `safe_ticker_component` — ticker sanitization |
| `src/stock_trading_bot/timestamps.py` | `known_at` computation from latency budget |
| `src/stock_trading_bot/store.py` | Schema, `Store`, `PointInTimeView` — the gateway |
| `src/stock_trading_bot/ingest/live_profile_guard.py` | The one shared withhold rule |
| `src/stock_trading_bot/ingest/prices.py` | stooq + Yahoo raw OHLCV adapters |
| `src/stock_trading_bot/ingest/corporate_actions.py` | Split/dividend rows + as-of adjustment factors |
| `src/stock_trading_bot/ingest/freshness.py` | Stale-bar guard |
| `src/stock_trading_bot/ingest/edgar.py` | SEC XBRL companyfacts, accession-keyed |
| `src/stock_trading_bot/cli.py` | `stock-trading ingest <ticker>` |

Each file has one responsibility. `store.py` is the only module with invariants worth defending, and it gets the heaviest test coverage.

---

### Tasks 1-3: COMPLETE

Landed in `c2341f2`, `106c4b3`, `5258f32`, `d52d4eb`, and the code-review fix commit.
Do not re-run them. Read the committed code rather than the original task text, which
these amendments supersede.

**Divergences from the original tasks, all from the Batch A code review:**

1. `parse_iso` now raises on naive input. `datetime.fromisoformat` accepts an offset-less
   string and `.astimezone()` then assumes system local time, so the stored instant
   depended on which machine read it - and east of UTC that moved `known_at` earlier,
   which is the leak direction.
2. `to_iso` emits **microseconds**, not seconds: `2026-09-07T20:15:00.000000+00:00`.
   Second-truncation was lossy and rounded `known_at` earlier.
   **This changes every timestamp literal in the tasks below.** The canonical form is
   fixed-width UTC with microseconds, and nothing else may be written to a timestamp
   column.
3. `known_at_for` rejects a negative latency budget.
4. `safe_ticker_component` validates before uppercasing. `str.upper()` maps some
   non-ASCII into ASCII, so `snow` and its long-s spelling collapsed to one cache key.
   It also now rejects a leading or trailing `.`/`-` and uses `fullmatch`.
5. Dependencies trimmed to `requests` and `pyyaml`. numpy, pandas, scikit-learn and
   pydantic return with the layers that import them.
6. `ruff` and `mypy --strict` added and passing. Keep them passing.
7. `pythonpath = ["src"]` in the pytest config, so the suite does not depend on the
   editable-install `.pth` file. See the `UF_HIDDEN` note below.

**Never build a timestamp by string concatenation.** A hand-written
`...T20:00:00` followed by `+00:00` is the same instant as the canonical
`...T20:00:00.000000+00:00`, but it sorts *before* it, because `+` (0x2B) precedes
`.` (0x2E). Mixed spellings in one column
silently break the ordering the point-in-time gateway depends on. Always route through
`timestamps.to_iso`.

**Environment note.** `uv` writes
`.venv/lib/python3.13/site-packages/_editable_impl_stock_trading_bot.pth` with the macOS
`UF_HIDDEN` flag, and CPython's `site.py` skips hidden `.pth` files, so the package can be
installed and silently unimportable. `pythonpath = ["src"]` makes the test suite immune.
For the CLI, use `PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli`.

**Verify before starting Task 4:**

```bash
cd /Users/duochen/Desktop/career/openPaw/stock-trading-bot
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
```

Expected: 49 passed, ruff clean, mypy clean.

---

### Tasks 4-5: COMPLETE

Landed in `9301ae6`, `79d432d`, `6ae9326`, `aeba2f1`. Read the committed
`src/stock_trading_bot/store.py` rather than the original task text.

**Two real holes were found by adversarially attacking the gateway, and both are worth
knowing about because the same mistake is easy to repeat in later layers.**

1. `PointInTimeView` originally held a generic query callable, and the `known_at <= t`
   predicate lived only in each accessor's SQL text. So
   `view._query("SELECT * FROM price_bar WHERE ticker = :ticker", ...)` returned
   future-dated rows, and `view._query("DELETE ...")` mutated the append-only store.
   The guarantee was a property of every call site rather than of the view - exactly
   the failure the class exists to prevent.
2. The first fix gave the view its own connection with `PRAGMA query_only = ON`. But a
   pragma is a per-connection *setting*: `view._conn.execute("PRAGMA query_only = OFF")`
   re-enabled writes.

**The design now standing, which later layers must not weaken:**

- The view's connection is opened with a `mode=ro` URI. That is an open *flag*, not a
  setting, so it cannot be revoked. `PRAGMA query_only = ON` is applied as well.
- `_query` re-checks every row in Python before returning it. An accessor whose SQL
  forgets the predicate still cannot emit a future-dated row.
- A returned row with no `known_at` column raises, rather than silently bypassing the
  check. Fail loud on misuse, fail closed on data.
- The accessors keep the predicate in their SQL too, so SQLite can use the `known_at`
  indexes instead of filtering everything in Python.

**When you add an accessor to `PointInTimeView`, you get the guarantee for free.** Do not
add a method that reaches around `_query`.

**Verify before starting Task 6:**

```bash
cd /Users/duochen/Desktop/career/openPaw/stock-trading-bot
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
```

Expected: 69 passed, ruff clean, mypy clean.

---

### Task 6: The live-profile guard

Spec §5.5. Motivated by TradingAgents issue #1300: vendor "overview" endpoints serve only present-day values with no historical vintage.

**Files:**
- Create: `stock-trading-bot/src/stock_trading_bot/ingest/live_profile_guard.py`
- Test: `stock-trading-bot/tests/test_live_profile_guard.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_live_profile_guard.py`:

```python
from datetime import date

import pytest

from stock_trading_bot.ingest.live_profile_guard import (
    LIVE_ONLY_FIELDS,
    withhold_live_profile,
)

PROFILE = {
    "longName": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "marketCap": 3_500_000_000_000,
    "trailingPE": 34.2,
    "fiftyTwoWeekHigh": 260.1,
    "totalRevenue": 391_000_000_000,
}
TODAY = date(2026, 9, 7)


@pytest.mark.unit
def test_a_historical_run_receives_nothing():
    assert withhold_live_profile(PROFILE, date(2024, 5, 10), TODAY) == {}


@pytest.mark.unit
def test_a_current_run_is_unchanged():
    assert withhold_live_profile(PROFILE, TODAY, TODAY) == PROFILE


@pytest.mark.unit
@pytest.mark.parametrize("leaky", [
    "3500000000000", "34.2", "260.1", "391000000000",
    "NVIDIA Corporation", "Technology", "Semiconductors",
])
def test_no_present_day_value_survives_a_historical_run(leaky):
    survived = str(withhold_live_profile(PROFILE, date(2024, 5, 10), TODAY))
    assert leaky not in survived


@pytest.mark.unit
def test_identity_fields_are_withheld_too():
    """Name, sector and industry shift on rename or reclassification, so they
    are not stable identity - they are present-day values without a vintage."""
    assert {"longName", "sector", "industry"} <= LIVE_ONLY_FIELDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_live_profile_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.live_profile_guard'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/live_profile_guard.py`:

```python
"""The one shared withhold rule for present-day-only vendor fields (spec §5.5).

Vendor "company overview" endpoints (yfinance Ticker.info, Alpha Vantage
OVERVIEW) serve only today's values. Market cap, valuation multiples, the
52-week range and TTM income all move with today's quote. Even name, sector and
industry shift when a company renames or is reclassified. None of it carries a
historical vintage, so emitting any of it into a run dated in the past puts
post-decision information into the model's inputs.

This rule lives at the shared layer, and every market-data adapter routes
through it, specifically so that switching providers cannot reintroduce the
leak. Do not reimplement this check inside an adapter.
"""
from __future__ import annotations

from datetime import date
from typing import Mapping

LIVE_ONLY_FIELDS = frozenset({
    "longName", "shortName", "sector", "industry",
    "marketCap", "enterpriseValue",
    "trailingPE", "forwardPE", "priceToBook", "pegRatio",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
    "totalRevenue", "trailingEps", "forwardEps",
    "dividendYield", "beta",
})


def withhold_live_profile(
    fields: Mapping[str, object], curr_date: date, today: date
) -> dict:
    """Strip present-day-only fields from a run dated before today.

    A live run (curr_date == today) is unchanged. A historical run receives
    nothing from a profile payload, because a profile payload has no vintage
    to filter on - the whole object is as-of-now.
    """
    if curr_date >= today:
        return dict(fields)
    return {k: v for k, v in fields.items() if k not in LIVE_ONLY_FIELDS}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_live_profile_guard.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/live_profile_guard.py stock-trading-bot/tests/test_live_profile_guard.py
git commit -m "feat(stock-trading-bot): shared live-profile withhold rule"
```

---

### Task 7: Stale-bar guard

**Files:**
- Create: `stock-trading-bot/src/stock_trading_bot/ingest/freshness.py`
- Test: `stock-trading-bot/tests/test_freshness.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_freshness.py`:

```python
import pytest

from stock_trading_bot.ingest.freshness import StaleDataError, assert_fresh


@pytest.mark.unit
def test_a_current_last_bar_passes():
    assert_fresh([{"session_date": "2026-09-04"}], expected_session="2026-09-04")


@pytest.mark.unit
def test_a_stale_last_bar_raises_rather_than_modelling_on_it():
    with pytest.raises(StaleDataError, match="2026-08-14"):
        assert_fresh([{"session_date": "2026-08-14"}], expected_session="2026-09-04")


@pytest.mark.unit
def test_empty_bars_raise():
    with pytest.raises(StaleDataError, match="no bars"):
        assert_fresh([], expected_session="2026-09-04")


@pytest.mark.unit
def test_a_bar_ahead_of_the_expected_session_raises():
    """A bar from the future means a bad vendor payload, not good news."""
    with pytest.raises(StaleDataError):
        assert_fresh([{"session_date": "2026-09-09"}], expected_session="2026-09-04")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_freshness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.freshness'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/freshness.py`:

```python
"""Stale-bar guard (spec §5.6).

A vendor that silently serves a weeks-old last bar produces a backtest that
looks fine and is wrong. Refuse the data instead.
"""
from __future__ import annotations

from typing import Sequence


class StaleDataError(RuntimeError):
    """Raised when price data does not reach the expected trading session."""


def assert_fresh(bars: Sequence[dict], expected_session: str) -> None:
    """Verify the newest bar is exactly the expected session.

    `expected_session` is a YYYY-MM-DD trading date, derived from the session
    calendar rather than the wall clock, so weekends and holidays are handled
    by the caller.
    """
    if not bars:
        raise StaleDataError(f"no bars returned; expected {expected_session}")
    newest = max(b["session_date"] for b in bars)
    if newest < expected_session:
        raise StaleDataError(
            f"stale data: newest session {newest}, expected {expected_session}"
        )
    if newest > expected_session:
        raise StaleDataError(
            f"vendor returned a future session {newest}, expected {expected_session}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_freshness.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/freshness.py stock-trading-bot/tests/test_freshness.py
git commit -m "feat(stock-trading-bot): stale-bar guard"
```

---

### Task 8: stooq price adapter

**Files:**
- Create: `stock-trading-bot/src/stock_trading_bot/ingest/prices.py`
- Test: `stock-trading-bot/tests/test_prices_stooq.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_prices_stooq.py`:

```python
from datetime import datetime, timezone
from unittest import mock

import pytest

from stock_trading_bot.ingest import prices

CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-09-03,100.0,102.0,99.5,101.0,1000000\n"
    "2026-09-04,101.0,105.0,100.5,104.0,1200000\n"
)
OBSERVED = datetime(2026, 9, 4, 21, 0, 0, tzinfo=timezone.utc)
BUDGET = {"stooq": 900}


def _fetch(text=CSV):
    return mock.patch.object(prices, "_http_get", return_value=text)


@pytest.mark.unit
def test_parses_bars_into_the_four_timestamp_shape():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert len(bars) == 2
    first = bars[0]
    assert first["ticker"] == "NVDA"
    assert first["session_date"] == "2026-09-03"
    assert first["close"] == 101.0
    assert first["source"] == "stooq"


@pytest.mark.unit
def test_known_at_is_observed_at_plus_the_budget():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert bars[0]["known_at"] == "2026-09-04T21:15:00.000000+00:00"


@pytest.mark.unit
def test_event_time_is_the_session_close_not_the_fetch_time():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert bars[0]["event_time"] == "2026-09-03T20:00:00.000000+00:00"


@pytest.mark.unit
def test_ticker_is_sanitized_before_reaching_the_url():
    with pytest.raises(ValueError):
        prices.fetch_stooq("../etc", observed_at=OBSERVED, latency_budget=BUDGET)


@pytest.mark.unit
def test_no_rows_returns_empty_rather_than_raising():
    with _fetch("Date,Open,High,Low,Close,Volume\n"):
        assert prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET) == []


@pytest.mark.unit
def test_adapter_never_returns_a_live_profile_field():
    """Enforces the §5.5 guard at the adapter boundary."""
    from stock_trading_bot.ingest.live_profile_guard import LIVE_ONLY_FIELDS

    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert set(bars[0]) & LIVE_ONLY_FIELDS == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_prices_stooq.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.prices'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/prices.py`:

```python
"""Raw OHLCV ingestion (spec §5.4).

Deliberately fetches RAW prices, never a vendor's adjusted series. An adjusted
close is retroactively revised - a split rewrites every prior adjusted value -
so consuming it directly is a leak. Adjustment factors are computed as-of from
the corporate_action table instead. See ingest/corporate_actions.py.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import datetime, timezone

import requests

from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.timestamps import known_at_for, to_iso

_STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
_UA = "stock-trading-bot/0.1 (research)"

# US equity sessions close at 16:00 ET, which is 20:00 UTC during EDT.
# The latency budget, not this value, governs availability.
_SESSION_CLOSE_HOUR_UTC = 20


def _session_close(session_date: str) -> str:
    """Canonical event_time for a session.

    Built through to_iso rather than by string concatenation: a hand-assembled
    timestamp is the same instant as the canonical form but sorts differently,
    which silently breaks the ordering the point-in-time gateway relies on.
    """
    year, month, day = (int(part) for part in session_date.split("-"))
    return to_iso(
        datetime(year, month, day, _SESSION_CLOSE_HOUR_UTC, tzinfo=timezone.utc)
    )


def _http_get(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_stooq(
    ticker: str, observed_at: datetime, latency_budget: Mapping[str, int]
) -> list[dict]:
    """Fetch raw daily bars from stooq, shaped for Store.insert_price_bar."""
    symbol = safe_ticker_component(ticker)
    text = _http_get(_STOOQ_URL.format(symbol=symbol.lower()))
    known_at = to_iso(known_at_for(observed_at, "stooq", latency_budget))
    observed_iso = to_iso(observed_at)

    bars: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("Date"):
            continue
        session = row["Date"]
        bars.append({
            "ticker": symbol,
            "session_date": session,
            "event_time": _session_close(session),
            "observed_at": observed_iso,
            "known_at": known_at,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
            "source": "stooq",
        })
    return bars
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_prices_stooq.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/prices.py stock-trading-bot/tests/test_prices_stooq.py
git commit -m "feat(stock-trading-bot): stooq raw OHLCV adapter"
```

---

### Task 9: Corporate actions and as-of adjustment factors

**Files:**
- Create: `stock-trading-bot/src/stock_trading_bot/ingest/corporate_actions.py`
- Test: `stock-trading-bot/tests/test_corporate_actions.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_corporate_actions.py`:

```python
from datetime import datetime, timezone

import pytest

from stock_trading_bot.ingest.corporate_actions import split_factor_as_of
from stock_trading_bot.store import Store


def _split(store, effective_date, ratio, known_at):
    store.insert_corporate_action(
        ticker="NOW",
        effective_date=effective_date,
        action_type="split",
        ratio=ratio,
        amount=None,
        event_time=f"{effective_date}T13:30:00.000000+00:00",
        observed_at=f"{effective_date}T14:00:00.000000+00:00",
        known_at=known_at,
        source="stooq",
    )


@pytest.fixture
def store(tmp_path):
    return Store.open(tmp_path / "panel.sqlite")


@pytest.mark.unit
def test_no_splits_means_a_factor_of_one(store):
    view = store.as_of(datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert split_factor_as_of(view, "NOW", "2025-06-01") == 1.0


@pytest.mark.unit
def test_a_later_split_divides_earlier_prices(store):
    """A 5-for-1 split on 2025-12-17 makes a 2025-06-01 price 5x too high."""
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    view = store.as_of(datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert split_factor_as_of(view, "NOW", "2025-06-01") == 5.0


@pytest.mark.unit
def test_a_split_does_not_affect_sessions_after_it(store):
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    view = store.as_of(datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert split_factor_as_of(view, "NOW", "2026-01-05") == 1.0


@pytest.mark.unit
def test_the_factor_is_as_of_t_not_as_of_today(store):
    """The critical case: standing at 2025-06-02, the December split has not
    happened and must not be applied. This is what using a vendor's adjusted
    series gets wrong."""
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    view = store.as_of(datetime(2025, 6, 2, tzinfo=timezone.utc))
    assert split_factor_as_of(view, "NOW", "2025-06-01") == 1.0


@pytest.mark.unit
def test_multiple_splits_compound(store):
    _split(store, "2025-12-17", 5.0, "2025-12-17T14:15:00.000000+00:00")
    _split(store, "2026-06-01", 2.0, "2026-06-01T14:15:00.000000+00:00")
    view = store.as_of(datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert split_factor_as_of(view, "NOW", "2025-01-01") == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_corporate_actions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.corporate_actions'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/corporate_actions.py`:

```python
"""As-of corporate action adjustment (spec §5.4).

The point of this module: an adjusted price series is itself retroactively
revised. A 5-for-1 split in December 2025 rewrites every adjusted close before
it. A backtest standing at June 2025 must not see that adjustment, because it
had not happened yet.

So we store raw prices plus dated actions, and reconstruct the factor from
whatever actions were visible at t.
"""
from __future__ import annotations

from math import prod


def split_factor_as_of(view, ticker: str, session_date: str) -> float:
    """Divisor converting a raw price on `session_date` to `view.t` terms.

    Only splits effective AFTER the session and known by `view.t` apply.
    Returns 1.0 when no such split is visible.
    """
    ratios = [
        action["ratio"]
        for action in view.corporate_actions(ticker)
        if action["action_type"] == "split"
        and action["effective_date"] > session_date
        and action["ratio"]
    ]
    return float(prod(ratios)) if ratios else 1.0


def adjusted_close_as_of(view, ticker: str, bar: dict) -> float:
    """Split-adjusted close for a bar, in `view.t` terms."""
    return bar["close"] / split_factor_as_of(view, ticker, bar["session_date"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_corporate_actions.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/corporate_actions.py stock-trading-bot/tests/test_corporate_actions.py
git commit -m "feat(stock-trading-bot): as-of split adjustment from dated actions"
```

---

### Task 10: SEC EDGAR fundamentals

**Files:**
- Create: `stock-trading-bot/src/stock_trading_bot/ingest/edgar.py`
- Test: `stock-trading-bot/tests/test_edgar.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_edgar.py`:

```python
from datetime import datetime, timezone
from unittest import mock

import pytest

from stock_trading_bot.ingest import edgar

FACTS = {
    "cik": 1373715,
    "entityName": "ServiceNow, Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"fy": 2026, "fp": "Q1", "form": "10-Q", "val": 3700000000,
                         "filed": "2026-04-23", "accn": "0001373715-26-000045"},
                        {"fy": 2026, "fp": "Q2", "form": "10-Q", "val": 3987000000,
                         "filed": "2026-07-23", "accn": "0001373715-26-000072"},
                        {"fy": 2026, "fp": "Q1", "form": "10-Q/A", "val": 3701000000,
                         "filed": "2026-08-01", "accn": "0001373715-26-000090"},
                    ]
                }
            }
        }
    },
}
OBSERVED = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
BUDGET = {"edgar": 1800}


def _fetch():
    return mock.patch.object(edgar, "_http_get_json", return_value=FACTS)


@pytest.mark.unit
def test_extracts_one_row_per_accession():
    with _fetch():
        rows = edgar.fetch_facts("NOW", cik=1373715, concepts=["Revenues"],
                                 observed_at=OBSERVED, latency_budget=BUDGET)
    assert len(rows) == 3


@pytest.mark.unit
def test_known_at_derives_from_the_filing_date_not_the_fetch_time():
    """A 10-Q filed in April was knowable in April, not when we scraped it."""
    with _fetch():
        rows = edgar.fetch_facts("NOW", cik=1373715, concepts=["Revenues"],
                                 observed_at=OBSERVED, latency_budget=BUDGET)
    q1 = next(r for r in rows if r["accession"] == "0001373715-26-000045")
    assert q1["known_at"] == "2026-04-23T00:30:00.000000+00:00"


@pytest.mark.unit
def test_a_restatement_is_a_separate_row_with_a_later_known_at():
    with _fetch():
        rows = edgar.fetch_facts("NOW", cik=1373715, concepts=["Revenues"],
                                 observed_at=OBSERVED, latency_budget=BUDGET)
    q1_rows = sorted(
        (r for r in rows if r["fiscal_period"] == "2026Q1"),
        key=lambda r: r["known_at"],
    )
    assert len(q1_rows) == 2
    assert q1_rows[0]["value"] == 3700000000
    assert q1_rows[1]["value"] == 3701000000


@pytest.mark.unit
def test_the_original_value_stays_visible_before_the_restatement(tmp_path):
    """Standing at 2026-05-01 we must see 3.700B, not the August correction."""
    from stock_trading_bot.store import Store

    store = Store.open(tmp_path / "panel.sqlite")
    with _fetch():
        rows = edgar.fetch_facts("NOW", cik=1373715, concepts=["Revenues"],
                                 observed_at=OBSERVED, latency_budget=BUDGET)
    for row in rows:
        store.insert_fundamental_fact(**row)

    view = store.as_of(datetime(2026, 5, 1, tzinfo=timezone.utc))
    visible = view.fundamental_facts("NOW", concept="Revenues")
    assert [r["value"] for r in visible] == [3700000000]


@pytest.mark.unit
def test_ticker_is_sanitized():
    with pytest.raises(ValueError):
        edgar.fetch_facts("../x", cik=1, concepts=["Revenues"],
                          observed_at=OBSERVED, latency_budget=BUDGET)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_edgar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.ingest.edgar'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/ingest/edgar.py`:

```python
"""SEC EDGAR XBRL companyfacts ingestion (spec §3.4, §5.3).

EDGAR is the one genuinely point-in-time fundamentals source available for
free: every fact carries the accession and filing date of the document that
disclosed it. So known_at derives from the FILING date, not from when we
happened to scrape it - a 10-Q filed in April was knowable in April.

Restatements append. A 10-Q/A produces a new row with the same fiscal_period,
a different accession, and a later known_at. Nothing is ever overwritten.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

import requests

from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.timestamps import to_iso

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# SEC requires a descriptive UA with contact info for automated access.
_UA = "stock-trading-bot/0.1 (research; contact via repository)"


def _http_get_json(url: str) -> dict:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=60)
    response.raise_for_status()
    return response.json()


def fetch_facts(
    ticker: str,
    cik: int,
    concepts: Sequence[str],
    observed_at: datetime,
    latency_budget: Mapping[str, int],
) -> list[dict]:
    """Fetch XBRL facts shaped for Store.insert_fundamental_fact."""
    symbol = safe_ticker_component(ticker)
    payload = _http_get_json(_FACTS_URL.format(cik=cik))
    observed_iso = to_iso(observed_at)
    latency = timedelta(seconds=latency_budget["edgar"])

    rows: list[dict] = []
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        for unit, entries in us_gaap.get(concept, {}).get("units", {}).items():
            for entry in entries:
                if not entry.get("fp") or not entry.get("fy"):
                    continue
                filed = datetime.fromisoformat(entry["filed"]).replace(
                    tzinfo=timezone.utc
                )
                rows.append({
                    "ticker": symbol,
                    "concept": concept,
                    "unit": unit,
                    "fiscal_period": f"{entry['fy']}{entry['fp']}",
                    "value": float(entry["val"]),
                    "accession": entry["accn"],
                    "event_time": to_iso(filed),
                    "observed_at": observed_iso,
                    "known_at": to_iso(filed + latency),
                    "valid_from": entry["filed"],
                    "source": "edgar",
                })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_edgar.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/ingest/edgar.py stock-trading-bot/tests/test_edgar.py
git commit -m "feat(stock-trading-bot): EDGAR XBRL ingest, known_at from filing date"
```

---

### Task 11: Import-graph direction test

Spec §4: nothing downstream of `store` may import an ingest module. This test enforces it for all future code.

**Files:**
- Test: `stock-trading-bot/tests/test_import_graph.py`

- [ ] **Step 1: Write the test**

Create `stock-trading-bot/tests/test_import_graph.py`:

```python
"""Dependency direction is one-way: ingest -> store -> features -> model -> evaluate.

A report or feature builder that can reach an ingest module can re-fetch live
data mid-render and quietly embed a value from the future. This test makes that
structurally impossible rather than a review convention.
"""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "stock_trading_bot"
DOWNSTREAM = ("features", "model", "evaluate", "report")
FORBIDDEN_PREFIX = "stock_trading_bot.ingest"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _downstream_files() -> list[Path]:
    return [p for pkg in DOWNSTREAM for p in (SRC / pkg).rglob("*.py")]


@pytest.mark.unit
def test_no_downstream_module_imports_ingest():
    offenders = [
        f"{path.relative_to(SRC)} imports {mod}"
        for path in _downstream_files()
        for mod in _imported_modules(path)
        if mod.startswith(FORBIDDEN_PREFIX)
    ]
    assert offenders == [], "dependency direction violated: " + "; ".join(offenders)


@pytest.mark.unit
def test_store_does_not_import_ingest():
    assert not any(
        mod.startswith(FORBIDDEN_PREFIX)
        for mod in _imported_modules(SRC / "store.py")
    )
```

- [ ] **Step 2: Create the downstream package directories so the test has something to scan**

```bash
cd /Users/duochen/Desktop/career/openPaw/stock-trading-bot
for pkg in features model evaluate report; do
  mkdir -p "src/stock_trading_bot/$pkg"
  touch "src/stock_trading_bot/$pkg/__init__.py"
done
```

- [ ] **Step 3: Run the test**

Run: `.venv/bin/pytest tests/test_import_graph.py -v`
Expected: PASS, 2 passed

- [ ] **Step 4: Verify the test actually catches a violation**

Temporarily add a bad import, confirm the test fails, then revert:

```bash
echo "from stock_trading_bot.ingest import prices" > src/stock_trading_bot/features/__init__.py
.venv/bin/pytest tests/test_import_graph.py -v   # expect FAIL
: > src/stock_trading_bot/features/__init__.py
.venv/bin/pytest tests/test_import_graph.py -v   # expect PASS
```

Expected: FAIL then PASS. A guard test that cannot fail is not a guard.

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/features stock-trading-bot/src/stock_trading_bot/model stock-trading-bot/src/stock_trading_bot/evaluate stock-trading-bot/src/stock_trading_bot/report stock-trading-bot/tests/test_import_graph.py
git commit -m "test(stock-trading-bot): enforce one-way dependency direction"
```

---

### Task 12: Config loading and watchlist

**Files:**
- Create: `stock-trading-bot/config/watchlist.yaml`
- Create: `stock-trading-bot/src/stock_trading_bot/config.py`
- Test: `stock-trading-bot/tests/test_config.py`

- [ ] **Step 1: Write `config/watchlist.yaml`**

Starter universe of enterprise software and semis, matching the existing
ServiceNow research in `market-research/reports/`.

```yaml
tickers:
  - symbol: NOW
    cik: 1373715
    name: ServiceNow, Inc.
    aliases: ["ServiceNow", "Service Now"]
    require_cashtag: true      # "now" is a common English word
  - symbol: NVDA
    cik: 1045810
    name: NVIDIA Corporation
    aliases: ["NVIDIA", "Nvidia"]
    require_cashtag: false
  - symbol: CRM
    cik: 1108524
    name: Salesforce, Inc.
    aliases: ["Salesforce"]
    require_cashtag: false
  - symbol: WDAY
    cik: 1327811
    name: Workday, Inc.
    aliases: ["Workday"]
    require_cashtag: false
  - symbol: SNOW
    cik: 1640147
    name: Snowflake Inc.
    aliases: ["Snowflake"]
    require_cashtag: true      # "snow" appears in unrelated contexts

benchmark: QQQ
```

- [ ] **Step 2: Write the failing test**

Create `stock-trading-bot/tests/test_config.py`:

```python
import pytest

from stock_trading_bot.config import load_run_config, load_watchlist


@pytest.mark.unit
def test_watchlist_loads_the_shipped_default():
    wl = load_watchlist()
    assert wl.benchmark == "QQQ"
    assert "NOW" in wl.symbols


@pytest.mark.unit
def test_ambiguous_symbols_require_a_cashtag():
    wl = load_watchlist()
    assert wl.entry("NOW").require_cashtag is True
    assert wl.entry("NVDA").require_cashtag is False


@pytest.mark.unit
def test_lookup_resolves_an_alias_case_insensitively():
    wl = load_watchlist()
    assert wl.resolve("servicenow") == "NOW"
    assert wl.resolve("NOW") == "NOW"
    assert wl.resolve("not a company") is None


@pytest.mark.unit
def test_run_config_exposes_latency_budgets():
    cfg = load_run_config()
    assert cfg["latency_budget_seconds"]["stooq"] == 900


@pytest.mark.unit
def test_config_paths_resolve_against_the_project_root_not_the_cwd(tmp_path, monkeypatch):
    """Otherwise the database lands somewhere different depending on where the
    CLI happened to be invoked from."""
    from stock_trading_bot.config import PROJECT_ROOT, resolve_path

    monkeypatch.chdir(tmp_path)
    resolved = resolve_path(load_run_config()["paths"]["db"])
    assert resolved.is_absolute()
    assert resolved == PROJECT_ROOT / "data/db/panel.sqlite"


@pytest.mark.unit
def test_every_watchlist_symbol_is_path_safe():
    from stock_trading_bot.naming import safe_ticker_component

    for symbol in load_watchlist().symbols:
        assert safe_ticker_component(symbol) == symbol
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.config'`

- [ ] **Step 4: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/config.py`:

```python
"""Configuration loading.

The watchlist is config, never hardcoded, so the universe can be swapped
without touching code (spec §3.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

#: The package lives at <root>/src/stock_trading_bot/, so the project root is
#: two levels up. Config paths resolve against this rather than the process
#: cwd, so `stock-trading ingest` writes to the same database regardless of
#: which directory it was invoked from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = PROJECT_ROOT / "config"


def resolve_path(relative: str) -> Path:
    """Resolve a path from run.yaml against the project root."""
    return PROJECT_ROOT / relative


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    cik: int
    name: str
    aliases: tuple[str, ...]
    require_cashtag: bool


@dataclass(frozen=True)
class Watchlist:
    entries: tuple[WatchlistEntry, ...]
    benchmark: str

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(e.symbol for e in self.entries)

    def entry(self, symbol: str) -> WatchlistEntry:
        for e in self.entries:
            if e.symbol == symbol.upper():
                return e
        raise KeyError(f"{symbol!r} is not in the watchlist")

    def resolve(self, text: str) -> str | None:
        """Resolve a ticker or alias to a symbol. Returns None if unknown."""
        needle = text.strip().casefold()
        for e in self.entries:
            if needle == e.symbol.casefold():
                return e.symbol
            if needle == e.name.casefold():
                return e.symbol
            if any(needle == a.casefold() for a in e.aliases):
                return e.symbol
        return None


def load_run_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or _CONFIG_DIR / "run.yaml").read_text())


def load_watchlist(path: Path | None = None) -> Watchlist:
    raw = yaml.safe_load((path or _CONFIG_DIR / "watchlist.yaml").read_text())
    entries = tuple(
        WatchlistEntry(
            symbol=t["symbol"],
            cik=int(t["cik"]),
            name=t["name"],
            aliases=tuple(t.get("aliases", ())),
            require_cashtag=bool(t.get("require_cashtag", False)),
        )
        for t in raw["tickers"]
    )
    return Watchlist(entries=entries, benchmark=raw["benchmark"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add stock-trading-bot/config/watchlist.yaml stock-trading-bot/src/stock_trading_bot/config.py stock-trading-bot/tests/test_config.py
git commit -m "feat(stock-trading-bot): config loading and starter watchlist"
```

---

### Task 13: CLI ingest command and README

**Files:**
- Create: `stock-trading-bot/src/stock_trading_bot/cli.py`
- Create: `stock-trading-bot/README.md`
- Test: `stock-trading-bot/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_cli.py`:

```python
from datetime import datetime, timezone
from unittest import mock

import pytest

from stock_trading_bot import cli
from stock_trading_bot.ingest import prices

CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-09-04,101.0,105.0,100.5,104.0,1200000\n"
)


@pytest.mark.unit
def test_ingest_writes_bars_that_are_visible_afterwards(tmp_path, capsys):
    db = tmp_path / "panel.sqlite"
    with mock.patch.object(prices, "_http_get", return_value=CSV):
        exit_code = cli.main(["ingest", "NVDA", "--db", str(db)])

    assert exit_code == 0
    assert "1 bar" in capsys.readouterr().out

    from stock_trading_bot.store import Store

    view = Store.open(db).as_of(datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert len(view.price_bars("NVDA")) == 1


@pytest.mark.unit
def test_ingest_rejects_an_unsafe_ticker(tmp_path):
    with pytest.raises(ValueError):
        cli.main(["ingest", "../etc", "--db", str(tmp_path / "p.sqlite")])


@pytest.mark.unit
def test_unknown_command_returns_nonzero(tmp_path, capsys):
    assert cli.main(["nonsense"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.cli'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/cli.py`:

```python
"""Command-line entry point.

Reports and paper evaluation only. This tool has no brokerage integration and
places no orders.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone

from stock_trading_bot.config import load_run_config, resolve_path
from stock_trading_bot.ingest import prices
from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.store import Store


def _ingest(args: argparse.Namespace) -> int:
    symbol = safe_ticker_component(args.ticker)
    cfg = load_run_config()
    store = Store.open(args.db or resolve_path(cfg["paths"]["db"]))
    bars = prices.fetch_stooq(
        symbol,
        observed_at=datetime.now(timezone.utc),
        latency_budget=cfg["latency_budget_seconds"],
    )
    written = 0
    for bar in bars:
        try:
            store.insert_price_bar(**bar)
            written += 1
        except sqlite3.IntegrityError:
            # Same observation already stored. Append-only means a re-run is a
            # no-op, not a duplicate.
            continue
    print(f"{symbol}: {written} bar(s) written, {len(bars) - written} already present")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stock-trading")
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest", help="fetch and store raw daily bars")
    ingest.add_argument("ticker")
    ingest.add_argument("--db", default=None)
    ingest.set_defaults(func=_ingest)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_usage()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Write the README**

Create `stock-trading-bot/README.md`:

````markdown
# stock-trading-bot

Point-in-time equity research and signal evaluation.

**Reports and paper evaluation only. No brokerage integration, no live execution.**

Design spec: `../docs/superpowers/specs/2026-09-07-stock-trading-bot-design.md`

## Setup

Requires `uv`. Do not use `pip` — it is broken on this machine's Homebrew Python 3.14.

```bash
uv venv -p 3.13
uv pip install -e ".[dev]"
.venv/bin/pytest
```

## Usage

```bash
PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli ingest NVDA
```

The `stock-trading` console script also exists, but on this machine `uv` writes the
editable-install `.pth` file with the macOS `UF_HIDDEN` flag, which CPython's `site.py`
skips — so the package can be installed and silently unimportable. Running the module
with `PYTHONPATH=src` sidesteps that entirely. The test suite is already immune via
`pythonpath = ["src"]` in `pyproject.toml`.

## What this foundation guarantees

Every fact carries four timestamps: `event_time`, `observed_at`, `known_at`, `valid_from`.
Reads go through `Store.as_of(t)`, which returns a view that cannot surface a row with
`known_at > t`.
A null `known_at` is invisible, not visible — unknown vintage fails closed.

Tables are append-only.
A restatement is a new row with a later `known_at`, never an overwrite, so revisions
cannot be backfilled into past predictions.

Prices are stored raw. Split adjustment is reconstructed as-of from dated corporate
actions, because a vendor's adjusted series is itself retroactively revised.

## Data limitations

Consensus estimates are **not available**. No free source provides consensus that is
timestamped before disclosure with a matching accounting definition.
Surprise features emit `unavailable` rather than a proxy.
Quarter-over-quarter acceleration is never substituted for a consensus surprise.

Scraped social engagement counts are as-of-scrape, not as-of-`t`. This is a known
contamination that scraping cannot fix; affected columns are flagged and surfaced in
every evaluation header.

## Costs

Price and EDGAR ingestion are free. LLM extraction cost arrives in the next phase and
is cached content-addressed, so re-runs are free.

## Reproducibility

Run manifests record the config hash, data vintages consumed, and cache hit rate.
````

- [ ] **Step 6: Run the full suite**

Run: `cd /Users/duochen/Desktop/career/openPaw/stock-trading-bot && .venv/bin/pytest -v`
Expected: PASS, 110 passed (69 from Tasks 1-5 + 10 live-profile + 4 freshness + 6 stooq
+ 5 corporate actions + 5 edgar + 2 import graph + 6 config + 3 cli).
Also run `.venv/bin/ruff check .` and `.venv/bin/mypy`; both must be clean.

- [ ] **Step 7: Verify the CLI works end to end against the live network**

The generated `.venv/bin/stock-trading` console script imports the package through the
editable-install `.pth`, which is subject to the `UF_HIDDEN` problem described in Task 1.
Invoke the module directly instead:

```bash
PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli ingest NVDA
```

Expected: `NVDA: N bar(s) written, 0 already present` with N > 1000.
Run it a second time; expected: `0 bar(s) written, N already present`.

- [ ] **Step 8: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/cli.py stock-trading-bot/README.md stock-trading-bot/tests/test_cli.py
git commit -m "feat(stock-trading-bot): CLI ingest command and README"
```

---

## Definition of done

- [ ] `.venv/bin/pytest` passes with 110 tests.
- [ ] `.venv/bin/ruff check .` and `.venv/bin/mypy` are both clean.
- [ ] `stock-trading ingest NVDA` writes bars, and a second run writes zero.
- [ ] The import-graph test has been shown to fail on a deliberate violation.
- [ ] No `pip` was used anywhere.
- [ ] No credentials appear in source or logs.

## Deferred to Plan 2 (social + extraction)

Social collectors, deduplication, event clustering, author and cluster influence caps,
ticker-ambiguity corpus matching, the LLM provider interface and long-document router,
evidence-span validation, and the extraction cache.

## Deferred to Plan 3 (model, evaluation, report)

Fold-scoped normalization, the ridge tier ladder, target definitions, walk-forward
splits with two-dimensional purging, MDE-first reporting, the consensus-substitution
refusal test, the deterministic 9-section report with citation audit, `SKILL.md`, and
the `stock-trading` subagent.

Also deferred: the spec §5.7 execution model — resolving a signal at `t` to the next
achievable fill against a session calendar, then applying spread, slippage, commission,
and borrow. It belongs with the strategy simulation, not with ingestion.

The session calendar itself is derived from the benchmark ticker's stored bars rather
than a holiday-calendar dependency: the sessions that exist are the sessions QQQ traded.
