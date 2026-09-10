# stock-trading-bot Features, Targets and Splits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the point-in-time store into a modelling panel — three explicitly-defined targets, three tiers of features, training-only normalization, and a walk-forward splitter that purges on both label overlap and event clusters.

**Architecture:** Every feature builder receives a `PointInTimeView` and nothing else, so it cannot see the future by construction. Targets are computed from the final price vintage, because a realized return is a realized return; **features are computed as-of `t`**. That asymmetry is deliberate and is the single easiest thing to get confused about in this plan, so it is stated in code, in tests, and in the docstring of every module it touches.

**Tech Stack:** Python 3.13, `uv`, `numpy` (added here), stdlib. **No pandas** — the panel is ~7,500 rows, numpy handles it, and pandas 3.0.5 ships no `py.typed` so it would force a mypy stub workaround for no benefit. scikit-learn arrives in Plan 5, where Ridge is first used.

**Spec:** `../specs/2026-09-07-stock-trading-bot-design.md` (§8, §9.1–9.2)

**Branch:** `feat/stock-trading-bot`

---

## Completeness of this plan — read first

**Tasks 1–5, 7 and 8 are executable-complete**: exact files, complete code, exact commands.

**Tasks 6, 9 and 10 are specified but not coded**, deliberately. They consume
`PointInTimeView.documents()` and `.extractions()`, which Plans 2 and 3 introduce and which do
not exist yet. Writing exact code against signatures that have not been built would be
guessing, and every previous plan in this series had its interfaces change under review — the
`PointInTimeView` gateway was rewritten three times. Those three tasks carry full behavioural
specifications, including the tests that must exist; **code them when Plans 2 and 3 have
landed and their real signatures are known.**

Task 11 is verification and needs no code.

If you are executing this plan and reach Task 6, stop and re-derive it against the interfaces
as built rather than as imagined.

## Decomposition note

Spec §8–9 is two plans' worth. This plan stops at a correct panel and correct splits; the
models and the evaluation harness are Plan 5. The split is at a real seam: **this plan can be
verified without any model existing**, because a leaking splitter or a lookahead feature is
detectable on its own, and detecting it before a model is fitted is much easier than after.

| Plan | Scope |
|---|---|
| **4 (this one)** | Session calendar, targets, beta, tiers 1–3 features, `FoldScaler`, walk-forward splitter |
| 5 | Ridge tier ladder, MDE-first reporting, metrics, cluster bootstrap, cost model, sensitivity |
| 6 | The 9-section report with citation audit, `SKILL.md`, the `stock-trading` subagent |

## Prerequisites

Plans 1–3 complete. **Standing constraints, inherited:** canonical timestamps via `to_iso`;
reads only through `store.as_of(t)`; append-only; `ruff` and `mypy --strict` clean; all network
mocked; no credentials anywhere.

Extend `DOWNSTREAM` in `tests/test_import_graph.py` to include `"features"` and `"model"` if
not already covered, and prove the guard bites.

---

## The one asymmetry that matters

**Features are as-of `t`. Targets are as-of now.**

A feature must only use information available when a decision would have been made — that is
the entire point of the store. A *target* is the realized outcome, and a realized return is
not a point-in-time quantity: it is what actually happened, measured after the fact with final
split adjustments.

Confusing the two goes wrong in both directions:

- Computing features from the final vintage leaks the future into the inputs. Invisible in
  results; ruinous.
- Computing targets as-of `t` produces a label based on prices not yet adjusted for a later
  split, which is simply a wrong number.

Every module below states which side it is on. `targets.py` takes a `Store`; every feature
builder takes a `PointInTimeView`. **That type difference is the guardrail** — a feature
builder cannot accidentally reach the final vintage because it was never handed one.

---

## File structure

| File | Responsibility |
|---|---|
| `src/stock_trading_bot/features/adjustment.py` | **Moved** from `ingest/corporate_actions.py` — see Task 5 Step 0 |
| `src/stock_trading_bot/features/calendar.py` | Trading sessions derived from benchmark bars |
| `src/stock_trading_bot/features/targets.py` | Forward returns and the three target definitions |
| `src/stock_trading_bot/features/beta.py` | Trailing beta from data available at `t` |
| `src/stock_trading_bot/features/market.py` | Tier 1: price, volume, volatility features |
| `src/stock_trading_bot/features/social.py` | Tier 2: discussion activity, attention, sentiment |
| `src/stock_trading_bot/features/llm.py` | Tier 3: events, demand stages, expectation changes |
| `src/stock_trading_bot/features/scaler.py` | `FoldScaler` — training-only normalization |
| `src/stock_trading_bot/model/splits.py` | Walk-forward splitter with two-dimensional purging |
| `src/stock_trading_bot/model/panel.py` | Assemble rows into a matrix |
| `src/stock_trading_bot/cli.py` (modify) | `stock-trading build-panel <ticker>` |

---

### Task 1: Session calendar

**Files:**
- Create: `src/stock_trading_bot/features/calendar.py`
- Modify: `pyproject.toml` (add `numpy>=2.0`)
- Test: `tests/test_features_calendar.py`

Spec §5.7. Sessions come from the benchmark's stored bars rather than a holiday-calendar
dependency: **the sessions that exist are the sessions the benchmark traded.** That is
self-maintaining, correct for half-days, and needs no library that must be kept current.

- [ ] **Step 1: Add numpy to `pyproject.toml`**

```toml
dependencies = [
    "requests>=2.32",
    "pyyaml>=6.0",
    "pydantic>=2.9",
    "numpy>=2.0",
]
```

Then `uv pip install -e ".[dev]"`.

- [ ] **Step 2: Write the failing test**

Create `stock-trading-bot/tests/test_features_calendar.py`:

```python
from datetime import UTC, datetime

import pytest

from stock_trading_bot.features.calendar import SessionCalendar
from stock_trading_bot.store import Store

T = datetime(2026, 12, 31, tzinfo=UTC)
# 2026-09-05 and -06 are a weekend; -07 is a holiday we simply never saw a bar for.
SESSIONS = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-08"]


@pytest.fixture
def calendar(tmp_path):
    store = Store.open(tmp_path / "panel.sqlite")
    for session in SESSIONS:
        store.insert_price_bar(
            ticker="QQQ", session_date=session,
            event_time=f"{session}T20:00:00.000000+00:00",
            observed_at=f"{session}T20:05:00.000000+00:00",
            known_at=f"{session}T20:20:00.000000+00:00",
            open=100.0, high=101.0, low=99.0, close=100.0, volume=1.0,
            source="yahoo",
        )
    return SessionCalendar(store.as_of(T), benchmark="QQQ")


@pytest.mark.unit
def test_sessions_come_from_the_benchmarks_bars(calendar):
    assert calendar.sessions() == SESSIONS


@pytest.mark.unit
def test_the_weekend_gap_is_simply_absent(calendar):
    """No holiday calendar needed: the sessions that exist are the ones traded."""
    assert "2026-09-05" not in calendar.sessions()


@pytest.mark.unit
def test_shift_forward_crosses_the_gap(calendar):
    assert calendar.shift("2026-09-04", 1) == "2026-09-08"


@pytest.mark.unit
def test_shift_backward_works(calendar):
    assert calendar.shift("2026-09-08", -1) == "2026-09-04"


@pytest.mark.unit
def test_shift_by_zero_is_identity(calendar):
    assert calendar.shift("2026-09-03", 0) == "2026-09-03"


@pytest.mark.unit
def test_shifting_past_the_end_returns_none(calendar):
    """The final sessions have no 5-day forward return, and pretending they do
    would silently truncate or fabricate labels."""
    assert calendar.shift("2026-09-08", 1) is None


@pytest.mark.unit
def test_shifting_before_the_start_returns_none(calendar):
    assert calendar.shift("2026-09-01", -1) is None


@pytest.mark.unit
def test_an_unknown_session_raises_rather_than_guessing(calendar):
    with pytest.raises(KeyError, match="2026-09-05"):
        calendar.shift("2026-09-05", 1)


@pytest.mark.unit
def test_contains_reports_membership(calendar):
    assert calendar.contains("2026-09-02") is True
    assert calendar.contains("2026-09-05") is False


@pytest.mark.unit
def test_an_empty_benchmark_history_yields_an_empty_calendar(tmp_path):
    store = Store.open(tmp_path / "empty.sqlite")
    assert SessionCalendar(store.as_of(T), benchmark="QQQ").sessions() == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_features_calendar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.features.calendar'`

- [ ] **Step 4: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/features/calendar.py`:

```python
"""Trading sessions, derived from the benchmark's stored bars (spec §5.7).

No holiday-calendar dependency: the sessions that exist are the sessions the
benchmark actually traded. That is self-maintaining, correct for early closes,
and cannot drift out of date.

Built from a PointInTimeView, so the calendar itself is point-in-time: standing
at t you know which sessions have happened, not which ones will.
"""
from __future__ import annotations

from stock_trading_bot.store import PointInTimeView


class SessionCalendar:
    """The ordered trading sessions visible at a point in time."""

    def __init__(self, view: PointInTimeView, benchmark: str) -> None:
        self._sessions = [
            str(bar["session_date"]) for bar in view.price_bars(benchmark)
        ]
        self._index = {session: i for i, session in enumerate(self._sessions)}

    def sessions(self) -> list[str]:
        return list(self._sessions)

    def contains(self, session: str) -> bool:
        return session in self._index

    def shift(self, session: str, offset: int) -> str | None:
        """The session `offset` trading days from `session`.

        Returns None past either end rather than clamping: the last few
        sessions genuinely have no forward return, and clamping would
        fabricate a label out of a shorter holding period.

        An unknown session raises, because silently treating a non-trading day
        as tradeable is how a backtest ends up executing on a Sunday.
        """
        if session not in self._index:
            raise KeyError(f"{session} is not a trading session for this benchmark")
        target = self._index[session] + offset
        if target < 0 or target >= len(self._sessions):
            return None
        return self._sessions[target]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_features_calendar.py -v`
Expected: PASS, 10 passed

- [ ] **Step 6: Commit**

```bash
git add stock-trading-bot/pyproject.toml stock-trading-bot/src/stock_trading_bot/features stock-trading-bot/tests/test_features_calendar.py
git commit -m "feat(stock-trading-bot): session calendar derived from benchmark bars"
```

---

### Task 2: Forward returns and the three targets

**Files:**
- Create: `src/stock_trading_bot/features/targets.py`
- Test: `tests/test_features_targets.py`

Spec §8.3. All three targets, configurable. **The naming rule is enforced in code:** a field
named `excess_vs_benchmark` can never be called `alpha`. Benchmark-relative upside does not
imply a positive absolute return, and simple subtraction of a benchmark is not risk-adjusted
alpha.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_features_targets.py`:

```python
import math

import pytest

from stock_trading_bot.features.targets import (
    TargetKind,
    forward_return,
    target_value,
)

PRICES = {
    "2026-09-01": 100.0, "2026-09-02": 102.0, "2026-09-03": 101.0,
    "2026-09-04": 105.0, "2026-09-08": 110.0,
}
BENCH = {
    "2026-09-01": 200.0, "2026-09-02": 202.0, "2026-09-03": 203.0,
    "2026-09-04": 204.0, "2026-09-08": 206.0,
}
SESSIONS = list(PRICES)


class FakeCalendar:
    def shift(self, session, offset):
        i = SESSIONS.index(session) + offset
        return SESSIONS[i] if 0 <= i < len(SESSIONS) else None

    def contains(self, session):
        return session in SESSIONS


@pytest.mark.unit
def test_a_one_session_forward_return():
    assert forward_return(PRICES, FakeCalendar(), "2026-09-01", horizon=1) == (
        pytest.approx(0.02)
    )


@pytest.mark.unit
def test_a_multi_session_forward_return_spans_the_gap():
    assert forward_return(PRICES, FakeCalendar(), "2026-09-04", horizon=1) == (
        pytest.approx(110.0 / 105.0 - 1)
    )


@pytest.mark.unit
def test_a_return_past_the_end_is_none_not_truncated():
    """The last sessions have no forward return. Truncating the horizon would
    silently mix 5-day and 2-day labels in one column."""
    assert forward_return(PRICES, FakeCalendar(), "2026-09-08", horizon=1) is None


@pytest.mark.unit
def test_a_missing_price_yields_none_rather_than_a_guess():
    sparse = {k: v for k, v in PRICES.items() if k != "2026-09-08"}
    assert forward_return(sparse, FakeCalendar(), "2026-09-04", horizon=1) is None


@pytest.mark.unit
def test_a_zero_base_price_yields_none_rather_than_infinity():
    assert forward_return({"a": 0.0, "b": 5.0}, FakeCalendar(), "a", horizon=1) is None


@pytest.mark.unit
def test_the_absolute_target_is_the_plain_return():
    assert target_value(TargetKind.ABSOLUTE, stock=0.05, benchmark=0.02, beta=1.5) == (
        pytest.approx(0.05)
    )


@pytest.mark.unit
def test_the_excess_target_subtracts_the_benchmark():
    assert target_value(
        TargetKind.EXCESS_VS_BENCHMARK, stock=0.05, benchmark=0.02, beta=1.5
    ) == pytest.approx(0.03)


@pytest.mark.unit
def test_the_residual_target_scales_the_benchmark_by_beta():
    assert target_value(
        TargetKind.BETA_ADJUSTED_RESIDUAL, stock=0.05, benchmark=0.02, beta=1.5
    ) == pytest.approx(0.02)


@pytest.mark.unit
def test_the_residual_target_requires_a_beta():
    with pytest.raises(ValueError, match="beta"):
        target_value(TargetKind.BETA_ADJUSTED_RESIDUAL, stock=0.05, benchmark=0.02,
                     beta=None)


@pytest.mark.unit
def test_a_nan_input_yields_none():
    assert target_value(TargetKind.ABSOLUTE, stock=math.nan, benchmark=0.0,
                        beta=None) is None


@pytest.mark.unit
def test_no_target_is_named_alpha():
    """Benchmark-relative upside is not risk-adjusted alpha, and a field name
    is where that confusion starts."""
    names = {kind.value for kind in TargetKind}
    assert not any("alpha" in name.lower() for name in names)


@pytest.mark.unit
def test_the_excess_target_is_explicitly_not_alpha_in_its_own_docstring():
    from stock_trading_bot.features import targets

    text = targets.__doc__ or ""
    assert "alpha" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_features_targets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.features.targets'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/features/targets.py`:

```python
"""Forward returns and the three target definitions (spec §8.3).

TARGETS ARE COMPUTED FROM THE FINAL PRICE VINTAGE, not as-of t. A realized
return is what actually happened, measured after the fact with final split
adjustments. Features are the opposite - see every module in this package that
takes a PointInTimeView. Getting this backwards leaks the future into inputs in
one direction, and produces simply-wrong labels in the other.

On naming: `excess_vs_benchmark` is stock return minus benchmark return. It is
NOT alpha. Subtracting an index is not risk adjustment, and benchmark-relative
upside does not imply a positive absolute return - a strategy can beat QQQ by
ten points while losing money. The enum values carry that distinction, and a
test asserts none of them contains the word "alpha".
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Protocol


class TargetKind(Enum):
    ABSOLUTE = "absolute_return"
    EXCESS_VS_BENCHMARK = "excess_vs_benchmark"
    BETA_ADJUSTED_RESIDUAL = "beta_adjusted_residual"


class _Calendar(Protocol):
    def shift(self, session: str, offset: int) -> str | None: ...


def forward_return(
    prices: dict[str, float], calendar: _Calendar, session: str, horizon: int
) -> float | None:
    """Return from `session` to `horizon` sessions later, or None.

    None rather than a shortened horizon when the window runs off the end:
    silently truncating would mix 5-day and 2-day outcomes in one label column,
    which quietly changes what the model is being asked to predict.
    """
    end = calendar.shift(session, horizon)
    if end is None:
        return None
    start_price, end_price = prices.get(session), prices.get(end)
    if start_price is None or end_price is None:
        return None
    if start_price <= 0:
        return None
    return end_price / start_price - 1.0


def target_value(
    kind: TargetKind, stock: float, benchmark: float, beta: float | None
) -> float | None:
    """One target value from a stock return and a benchmark return."""
    if math.isnan(stock) or math.isnan(benchmark):
        return None
    if kind is TargetKind.ABSOLUTE:
        return stock
    if kind is TargetKind.EXCESS_VS_BENCHMARK:
        return stock - benchmark
    if beta is None or math.isnan(beta):
        raise ValueError(
            "beta_adjusted_residual requires a beta estimated from data "
            "available at t; refusing to fall back to plain subtraction, which "
            "is a different and weaker target"
        )
    return stock - beta * benchmark
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_features_targets.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/features/targets.py stock-trading-bot/tests/test_features_targets.py
git commit -m "feat(stock-trading-bot): three explicit targets, none of them called alpha"
```

---

### Task 3: Beta from data available at `t`

**Files:**
- Create: `src/stock_trading_bot/features/beta.py`
- Test: `tests/test_features_beta.py`

Spec §8.3. Beta is a *feature-side* quantity — it must be estimated only from bars visible at
`t`, even though it is used to construct a target. Estimating it over the whole sample is a
classic and invisible leak.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_features_beta.py`:

```python
import pytest

from stock_trading_bot.features.beta import trailing_beta


def _series(values):
    return {f"2026-09-{i + 1:02d}": v for i, v in enumerate(values)}


@pytest.mark.unit
def test_a_stock_moving_exactly_with_the_benchmark_has_beta_one():
    prices = _series([100, 102, 104, 106, 108, 110])
    bench = _series([200, 204, 208, 212, 216, 220])
    assert trailing_beta(prices, bench, sessions=list(prices), asof="2026-09-06",
                         window=5) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.unit
def test_a_stock_moving_twice_as_hard_has_beta_two():
    prices = _series([100, 104, 108.16, 112.49, 116.99, 121.67])
    bench = _series([200, 204, 208.08, 212.24, 216.49, 220.82])
    beta = trailing_beta(prices, bench, sessions=list(prices), asof="2026-09-06",
                         window=5)
    assert beta == pytest.approx(2.0, rel=0.02)


@pytest.mark.unit
def test_too_few_observations_returns_none_rather_than_a_noisy_number():
    """A beta from three points is not an estimate; it is a coincidence."""
    prices = _series([100, 101, 102])
    bench = _series([200, 201, 202])
    assert trailing_beta(prices, bench, sessions=list(prices), asof="2026-09-03",
                         window=30, min_observations=20) is None


@pytest.mark.unit
def test_only_sessions_at_or_before_asof_are_used():
    """The whole point. A beta fitted through the future is a leak that is
    invisible in every result it touches."""
    prices = _series([100, 101, 102, 103, 500, 900])
    bench = _series([200, 202, 204, 206, 208, 210])
    sessions = list(prices)
    early = trailing_beta(prices, bench, sessions=sessions, asof="2026-09-04",
                          window=10, min_observations=2)
    late = trailing_beta(prices, bench, sessions=sessions, asof="2026-09-06",
                         window=10, min_observations=2)
    assert early != late
    assert early == pytest.approx(0.5, rel=0.1)


@pytest.mark.unit
def test_the_window_bounds_how_far_back_it_looks():
    prices = _series([100, 200, 100, 101, 102, 103])
    bench = _series([200, 202, 204, 206, 208, 210])
    sessions = list(prices)
    short = trailing_beta(prices, bench, sessions=sessions, asof="2026-09-06",
                          window=3, min_observations=2)
    long = trailing_beta(prices, bench, sessions=sessions, asof="2026-09-06",
                         window=10, min_observations=2)
    assert short != long


@pytest.mark.unit
def test_a_zero_variance_benchmark_returns_none_rather_than_dividing_by_zero():
    prices = _series([100, 101, 102, 103, 104, 105])
    bench = _series([200, 200, 200, 200, 200, 200])
    assert trailing_beta(prices, bench, sessions=list(prices), asof="2026-09-06",
                         window=5, min_observations=2) is None


@pytest.mark.unit
def test_an_unknown_asof_session_returns_none():
    prices = _series([100, 101])
    assert trailing_beta(prices, prices, sessions=list(prices), asof="1999-01-01",
                         window=5, min_observations=2) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_features_beta.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.features.beta'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/features/beta.py`:

```python
"""Trailing beta estimated only from data available at t (spec §8.3).

Beta is used to build the residual target, but it is a FEATURE-side quantity:
it must be estimated from what was knowable at t. Fitting it over the whole
sample is a classic leak, and an especially insidious one because the resulting
target looks entirely reasonable.

Returns None rather than a number whenever the estimate would not be
trustworthy - too few observations, or a benchmark with no variance. A caller
that needs beta must then decide what to do, which is better than silently
receiving a coincidence.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

_DEFAULT_WINDOW = 120
_DEFAULT_MIN_OBSERVATIONS = 40


def _returns(prices: dict[str, float], sessions: Sequence[str]) -> list[float]:
    out: list[float] = []
    for previous, current in zip(sessions, sessions[1:], strict=False):
        before, after = prices.get(previous), prices.get(current)
        if before is None or after is None or before <= 0:
            continue
        out.append(after / before - 1.0)
    return out


def trailing_beta(
    prices: dict[str, float],
    benchmark_prices: dict[str, float],
    sessions: Sequence[str],
    asof: str,
    window: int = _DEFAULT_WINDOW,
    min_observations: int = _DEFAULT_MIN_OBSERVATIONS,
) -> float | None:
    """OLS beta of stock returns on benchmark returns, using sessions <= asof."""
    if asof not in sessions:
        return None
    end = sessions.index(asof)
    start = max(0, end - window)
    span = list(sessions[start:end + 1])

    stock = _returns(prices, span)
    bench = _returns(benchmark_prices, span)
    usable = min(len(stock), len(bench))
    if usable < min_observations:
        return None

    x = np.asarray(bench[:usable], dtype=float)
    y = np.asarray(stock[:usable], dtype=float)
    variance = float(np.var(x))
    if variance <= 0.0:
        return None
    return float(np.cov(y, x, bias=True)[0][1] / variance)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_features_beta.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/features/beta.py stock-trading-bot/tests/test_features_beta.py
git commit -m "feat(stock-trading-bot): trailing beta from data available at t"
```

---

### Task 4: Trailing-window statistics

**Files:**
- Create: `src/stock_trading_bot/features/trailing.py`
- Test: `tests/test_features_trailing.py`

Spec §8.1, failure mode 2. **This is the lookahead people miss.** Fold-scoped normalization
(Task 7) fixes fitting a scaler on the full sample. It does *not* fix a "volume z-score"
computed with the whole history including the future. Both are required; fixing only the first
still leaks.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_features_trailing.py`:

```python
import math

import pytest

from stock_trading_bot.features.trailing import trailing_mean, trailing_zscore

SERIES = [1.0, 2.0, 3.0, 4.0, 100.0, 6.0]


@pytest.mark.unit
def test_the_first_point_has_no_history_so_it_is_none():
    assert trailing_mean(SERIES, window=3)[0] is None


@pytest.mark.unit
def test_a_trailing_mean_uses_only_earlier_points():
    """Index 3's mean is of indices 0-2, and must not include index 3 itself."""
    assert trailing_mean(SERIES, window=3)[3] == pytest.approx(2.0)


@pytest.mark.unit
def test_the_window_bounds_the_lookback():
    assert trailing_mean(SERIES, window=2)[3] == pytest.approx(2.5)


@pytest.mark.unit
def test_a_later_spike_cannot_change_an_earlier_value():
    """The property that makes this leak-free, stated directly."""
    baseline = trailing_mean(SERIES, window=3)
    spiked = trailing_mean([*SERIES[:4], 999999.0, *SERIES[5:]], window=3)
    assert baseline[:5] == spiked[:5]


@pytest.mark.unit
def test_a_zscore_uses_only_trailing_statistics():
    values = [1.0, 1.0, 1.0, 1.0, 5.0]
    z = trailing_zscore(values, window=4)
    assert z[4] is not None and z[4] > 3


@pytest.mark.unit
def test_a_zero_variance_window_yields_none_not_infinity():
    assert trailing_zscore([1.0, 1.0, 1.0, 1.0], window=3)[3] is None


@pytest.mark.unit
def test_insufficient_history_yields_none():
    assert trailing_zscore(SERIES, window=3, min_periods=3)[2] is None


@pytest.mark.unit
def test_nan_inputs_do_not_poison_the_whole_series():
    values = [1.0, math.nan, 3.0, 4.0, 5.0]
    result = trailing_mean(values, window=3, min_periods=1)
    assert result[3] is not None and not math.isnan(result[3])


@pytest.mark.unit
def test_the_output_length_matches_the_input():
    assert len(trailing_mean(SERIES, window=3)) == len(SERIES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_features_trailing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.features.trailing'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/features/trailing.py`:

```python
"""Strictly-trailing window statistics (spec §8.1).

The lookahead people miss. Fold-scoped normalization fixes fitting a scaler on
the full sample; it does nothing about a rolling statistic computed over the
whole history including the future. Both are required, and fixing only the
first still leaks.

Every window here ends at index i-1, never at i. A value at position i can
therefore never influence its own statistic, and a later spike can never change
an earlier output - which is the property a test asserts directly.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

_DEFAULT_MIN_PERIODS = 2


def _window(values: Sequence[float], i: int, window: int) -> list[float]:
    """Values strictly before i, at most `window` of them, NaNs removed."""
    start = max(0, i - window)
    return [v for v in values[start:i] if not math.isnan(v)]


def trailing_mean(
    values: Sequence[float], window: int, min_periods: int = _DEFAULT_MIN_PERIODS
) -> list[float | None]:
    """Mean of the `window` values before each position."""
    out: list[float | None] = []
    for i in range(len(values)):
        history = _window(values, i, window)
        out.append(sum(history) / len(history) if len(history) >= min_periods else None)
    return out


def trailing_zscore(
    values: Sequence[float], window: int, min_periods: int = _DEFAULT_MIN_PERIODS
) -> list[float | None]:
    """Z-score of each value against the `window` values before it.

    None on a zero-variance window rather than an infinity: a constant history
    tells you nothing about how unusual the next value is.
    """
    out: list[float | None] = []
    for i, value in enumerate(values):
        history = _window(values, i, window)
        if len(history) < min_periods or math.isnan(value):
            out.append(None)
            continue
        mean = sum(history) / len(history)
        variance = sum((h - mean) ** 2 for h in history) / len(history)
        if variance <= 0.0:
            out.append(None)
            continue
        out.append((value - mean) / math.sqrt(variance))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_features_trailing.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/features/trailing.py stock-trading-bot/tests/test_features_trailing.py
git commit -m "feat(stock-trading-bot): strictly-trailing window statistics

Fold-scoped normalization fixes fitting a scaler on the full sample. It does
nothing about a rolling statistic computed over the whole history including the
future. Both are needed; fixing only the first still leaks."
```

---

### Task 5: Tier 1 market features

**Files:**
- Move: `src/stock_trading_bot/ingest/corporate_actions.py` → `src/stock_trading_bot/features/adjustment.py`
- Create: `src/stock_trading_bot/features/market.py`
- Test: `tests/test_features_market.py`

- [ ] **Step 0: Move the adjustment helpers out of `ingest/`**

`ingest/corporate_actions.py` contains only `split_factor_as_of` and `adjusted_close_as_of`.
Both are read-side: they take a `PointInTimeView` and import nothing from `ingest`. They were
put under `ingest/` in the foundation plan by mistake, and `features/market.py` needs them —
which the import-graph guard correctly forbids.

The guard is right; the module is misplaced. Move it rather than weakening the guard:

```bash
cd /Users/duochen/Desktop/career/openPaw/stock-trading-bot
git mv src/stock_trading_bot/ingest/corporate_actions.py src/stock_trading_bot/features/adjustment.py
git mv tests/test_corporate_actions.py tests/test_features_adjustment.py
sed -i '' 's/stock_trading_bot\.ingest\.corporate_actions/stock_trading_bot.features.adjustment/g' \
  tests/test_features_adjustment.py
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
git commit -am "refactor(stock-trading-bot): move as-of adjustment into features/

It is read-side - it takes a PointInTimeView and imports nothing from ingest -
and features/market.py needs it, which the import-graph guard correctly
forbids. The guard was right and the module was misplaced."
```

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_features_market.py`:

```python
from datetime import UTC, datetime

import pytest

from stock_trading_bot.features.calendar import SessionCalendar
from stock_trading_bot.features.market import FEATURE_NAMES, market_features
from stock_trading_bot.store import Store

T = datetime(2026, 12, 31, tzinfo=UTC)


def _bars(store, ticker, closes, volumes=None, known_offset_days=0):
    volumes = volumes or [1000.0] * len(closes)
    for i, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        session = f"2026-09-{i + 1:02d}"
        known_day = i + 1 + known_offset_days
        store.insert_price_bar(
            ticker=ticker, session_date=session,
            event_time=f"{session}T20:00:00.000000+00:00",
            observed_at=f"{session}T20:05:00.000000+00:00",
            known_at=f"2026-09-{known_day:02d}T20:20:00.000000+00:00",
            open=close, high=close, low=close, close=close, volume=volume,
            source="yahoo",
        )


@pytest.fixture
def store(tmp_path):
    store = Store.open(tmp_path / "panel.sqlite")
    _bars(store, "NVDA", [100.0 + i for i in range(28)])
    _bars(store, "QQQ", [200.0 + i for i in range(28)])
    return store


def _features(store, session, view_at=T):
    view = store.as_of(view_at)
    return market_features(view, "NVDA", session,
                           SessionCalendar(view, "QQQ"), benchmark="QQQ")


@pytest.mark.unit
def test_every_declared_feature_is_present(store):
    assert set(_features(store, "2026-09-25")) == set(FEATURE_NAMES)


@pytest.mark.unit
def test_the_key_set_is_identical_with_and_without_history(store):
    """Column shape must not vary by ticker or date, or the matrix is ragged."""
    assert set(_features(store, "2026-09-01")) == set(_features(store, "2026-09-25"))


@pytest.mark.unit
def test_a_one_day_return_is_computed(store):
    assert _features(store, "2026-09-05")["mkt_ret_1d"] == pytest.approx(
        104.0 / 103.0 - 1
    )


@pytest.mark.unit
def test_insufficient_history_yields_none_not_zero(store):
    """Zero is a value. Absence is not, and a model cannot tell them apart."""
    assert _features(store, "2026-09-01")["mkt_ret_21d"] is None


@pytest.mark.unit
def test_a_feature_is_unchanged_when_later_bars_are_added(tmp_path):
    """The property that makes this leak-free. Most important test in the file."""
    store = Store.open(tmp_path / "p.sqlite")
    _bars(store, "NVDA", [100.0 + i for i in range(28)])
    _bars(store, "QQQ", [200.0 + i for i in range(28)])
    before = _features(store, "2026-09-20")

    store.insert_price_bar(
        ticker="NVDA", session_date="2026-09-29",
        event_time="2026-09-29T20:00:00.000000+00:00",
        observed_at="2026-09-29T20:05:00.000000+00:00",
        known_at="2026-09-29T20:20:00.000000+00:00",
        open=9999.0, high=9999.0, low=9999.0, close=9999.0, volume=9e9,
        source="yahoo",
    )
    assert _features(store, "2026-09-20") == before


@pytest.mark.unit
def test_a_bar_not_yet_visible_does_not_contribute(tmp_path):
    """Drive it through the real gateway, not a filtered list."""
    store = Store.open(tmp_path / "p.sqlite")
    _bars(store, "NVDA", [100.0 + i for i in range(28)])
    _bars(store, "QQQ", [200.0 + i for i in range(28)])
    early = datetime(2026, 9, 10, tzinfo=UTC)
    assert _features(store, "2026-09-05", view_at=early)["mkt_ret_1d"] is not None
    assert _features(store, "2026-09-25", view_at=early) == dict.fromkeys(FEATURE_NAMES)


@pytest.mark.unit
def test_prices_are_split_adjusted_as_of_the_view(tmp_path):
    """A split must not appear as a 5:1 crash in the return series."""
    store = Store.open(tmp_path / "p.sqlite")
    _bars(store, "NVDA", [500.0] * 10 + [100.0] * 18)
    _bars(store, "QQQ", [200.0 + i for i in range(28)])
    store.insert_corporate_action(
        ticker="NVDA", effective_date="2026-09-11", action_type="split",
        ratio=5.0, amount=None,
        event_time="2026-09-11T13:30:00.000000+00:00",
        observed_at="2026-09-11T14:00:00.000000+00:00",
        known_at="2026-09-11T14:15:00.000000+00:00", source="yahoo",
    )
    assert _features(store, "2026-09-11")["mkt_ret_1d"] == pytest.approx(0.0)


@pytest.mark.unit
def test_volume_zscore_uses_only_trailing_statistics(tmp_path):
    store = Store.open(tmp_path / "p.sqlite")
    volumes = [1000.0] * 26 + [50000.0, 1000.0]
    _bars(store, "NVDA", [100.0 + i for i in range(28)], volumes=volumes)
    _bars(store, "QQQ", [200.0 + i for i in range(28)])
    spike = _features(store, "2026-09-27")["mkt_volume_z_21d"]
    assert spike is not None and spike > 3


@pytest.mark.unit
def test_the_feature_names_are_sorted_so_column_order_is_deterministic():
    assert list(FEATURE_NAMES) == sorted(FEATURE_NAMES)


@pytest.mark.unit
def test_every_feature_name_is_tier_one_prefixed():
    assert all(name.startswith("mkt_") for name in FEATURE_NAMES)


@pytest.mark.unit
def test_an_unknown_session_raises(store):
    with pytest.raises(KeyError):
        _features(store, "2026-09-06")   # a Sunday: no bar, so not a session
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_features_market.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.features.market'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/features/market.py`:

```python
"""Tier 1 features: price, volume, volatility (spec §8.2).

Takes a PointInTimeView and nothing else. That type is the guardrail: a feature
builder handed only a view cannot reach the final price vintage, so it cannot
see the future even by accident.

Prices are split-adjusted AS OF THE VIEW, never raw and never from a vendor's
adjusted series. Raw prices make a split look like a crash; a vendor's adjusted
series bakes a future split into past values.

Absent history yields None, not 0.0. Zero is a value a model will happily fit;
absence is not, and the two must not be confused.
"""
from __future__ import annotations

from stock_trading_bot.features.adjustment import adjusted_close_as_of
from stock_trading_bot.features.beta import trailing_beta
from stock_trading_bot.features.calendar import SessionCalendar
from stock_trading_bot.features.trailing import trailing_zscore
from stock_trading_bot.store import PointInTimeView

FEATURE_NAMES: tuple[str, ...] = (
    "mkt_beta_120d",
    "mkt_ret_1d",
    "mkt_ret_5d",
    "mkt_ret_21d",
    "mkt_vol_21d",
    "mkt_volume_z_21d",
)

_VOL_WINDOW = 21
_VOLUME_WINDOW = 21
_BETA_WINDOW = 120


def _adjusted_series(
    view: PointInTimeView, ticker: str
) -> tuple[dict[str, float], dict[str, float]]:
    """Adjusted closes and volumes, keyed by session, visible at the view."""
    closes: dict[str, float] = {}
    volumes: dict[str, float] = {}
    for bar in view.price_bars(ticker):
        session = str(bar["session_date"])
        closes[session] = adjusted_close_as_of(view, ticker, bar)
        volumes[session] = float(bar["volume"])  # type: ignore[arg-type]
    return closes, volumes


def _return_over(
    closes: dict[str, float], calendar: SessionCalendar, session: str, lookback: int
) -> float | None:
    start = calendar.shift(session, -lookback)
    if start is None:
        return None
    before, now = closes.get(start), closes.get(session)
    if before is None or now is None or before <= 0:
        return None
    return now / before - 1.0


def market_features(
    view: PointInTimeView,
    ticker: str,
    session: str,
    calendar: SessionCalendar,
    benchmark: str,
) -> dict[str, float | None]:
    """Tier 1 features for one (ticker, session), as knowable at the view."""
    if not calendar.contains(session):
        raise KeyError(f"{session} is not a trading session")

    closes, volumes = _adjusted_series(view, ticker)
    benchmark_closes, _ = _adjusted_series(view, benchmark)
    sessions = [s for s in calendar.sessions() if s <= session]

    features: dict[str, float | None] = dict.fromkeys(FEATURE_NAMES)
    if session not in closes:
        # Nothing visible for this name yet: every feature is absent, but the
        # key set is unchanged so the matrix never becomes ragged.
        return features

    features["mkt_ret_1d"] = _return_over(closes, calendar, session, 1)
    features["mkt_ret_5d"] = _return_over(closes, calendar, session, 5)
    features["mkt_ret_21d"] = _return_over(closes, calendar, session, 21)

    daily = [
        r for r in (
            _return_over(closes, calendar, s, 1) for s in sessions[-_VOL_WINDOW - 1:]
        ) if r is not None
    ]
    if len(daily) >= 2:
        mean = sum(daily) / len(daily)
        features["mkt_vol_21d"] = (
            sum((r - mean) ** 2 for r in daily) / len(daily)
        ) ** 0.5

    volume_series = [volumes[s] for s in sessions if s in volumes]
    if volume_series:
        z = trailing_zscore(volume_series, window=_VOLUME_WINDOW)
        features["mkt_volume_z_21d"] = z[-1]

    features["mkt_beta_120d"] = trailing_beta(
        closes, benchmark_closes, sessions=sessions, asof=session,
        window=_BETA_WINDOW, min_observations=20,
    )
    return features
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_features_market.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/features/market.py stock-trading-bot/tests/test_features_market.py
git commit -m "feat(stock-trading-bot): tier 1 market features, invariant to later bars"
```

---
### Task 6: Tier 2 and tier 3 features

**Files:**
- Create: `src/stock_trading_bot/features/social.py`, `src/stock_trading_bot/features/llm.py`
- Test: `tests/test_features_social.py`, `tests/test_features_llm.py`

**Tier 2** (`social.py`), all prefixed to make the §6.5 rule visible in the column names:
- `attention_doc_count_1d`, `attention_doc_count_5d` — cluster-weighted, not raw counts
- `attention_score_sum_5d` — the only feature allowed to read `score`
- `activity_author_count_5d` — distinct authors, a volume measure that upvotes cannot inflate
- `sentiment_mean_5d` — lexicon-based, no model call

**Tier 3** (`llm.py`), from `view.extractions(ticker)`:
- `evt_count_5d`, `evt_positive_5d`, `evt_negative_5d`
- `demand_advancing_5d`, `demand_churning_5d` — stage transitions, not stage counts
- `expect_up_5d`, `expect_down_5d`

Required behaviours for both, each its own test:
- **A document not yet visible contributes nothing.** Drive this through `store.as_of` with a
  future `known_at`, not by filtering a list — the test must exercise the real gateway.
- Counts are cluster-weighted, so one viral thread does not read as fifty observations.
- No `credibility_*` or `confidence_*` name appears; the Plan 2 namespace guard covers this,
  but assert it here too where the features actually exist.
- An empty corpus yields zeros for counts and `None` for means. A mean of nothing is not zero.
- Feature keys are identical whether or not any document exists, so the column set never
  changes shape between tickers.

---

### Task 7: `FoldScaler` — training-only normalization

**Files:**
- Create: `src/stock_trading_bot/features/scaler.py`
- Test: `tests/test_features_scaler.py`

Spec §8.1, failure mode 1. Fit strictly on the training fold, persist alongside it, apply
unchanged to validation and test.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_features_scaler.py`:

```python
import pytest

from stock_trading_bot.features.scaler import FoldScaler

TRAIN = [
    {"a": 1.0, "b": 10.0},
    {"a": 2.0, "b": 20.0},
    {"a": 3.0, "b": 30.0},
]


@pytest.mark.unit
def test_the_training_fold_is_centred_on_itself():
    scaled = FoldScaler().fit(TRAIN).transform(TRAIN)
    assert sum(row["a"] for row in scaled) == pytest.approx(0.0)


@pytest.mark.unit
def test_test_data_is_scaled_by_training_statistics_not_its_own():
    """The whole point. A test fold centred on itself has leaked."""
    scaler = FoldScaler().fit(TRAIN)
    test = [{"a": 101.0, "b": 1.0}, {"a": 102.0, "b": 2.0}, {"a": 103.0, "b": 3.0}]
    scaled = scaler.transform(test)
    assert sum(row["a"] for row in scaled) != pytest.approx(0.0)
    assert scaled[0]["a"] > 50


@pytest.mark.unit
def test_transform_before_fit_raises():
    with pytest.raises(RuntimeError, match="fit"):
        FoldScaler().transform(TRAIN)


@pytest.mark.unit
def test_a_zero_variance_column_passes_through_unscaled():
    constant = [{"a": 5.0}, {"a": 5.0}, {"a": 5.0}]
    scaler = FoldScaler().fit(constant)
    assert scaler.transform(constant)[0]["a"] == pytest.approx(0.0)


@pytest.mark.unit
def test_a_zero_variance_column_is_recorded_rather_than_hidden():
    """A constant feature is a modelling problem; it should be visible."""
    scaler = FoldScaler().fit([{"a": 5.0}, {"a": 5.0}])
    assert "a" in scaler.degenerate_columns


@pytest.mark.unit
def test_a_column_missing_at_transform_time_raises():
    scaler = FoldScaler().fit(TRAIN)
    with pytest.raises(KeyError, match="b"):
        scaler.transform([{"a": 1.0}])


@pytest.mark.unit
def test_an_unexpected_column_at_transform_time_raises():
    scaler = FoldScaler().fit(TRAIN)
    with pytest.raises(KeyError, match="c"):
        scaler.transform([{"a": 1.0, "b": 2.0, "c": 3.0}])


@pytest.mark.unit
def test_none_values_are_preserved_as_none_not_imputed():
    """Imputing silently invents data; the model should see the gap."""
    scaler = FoldScaler().fit(TRAIN)
    assert scaler.transform([{"a": None, "b": 20.0}])[0]["a"] is None


@pytest.mark.unit
def test_none_values_are_excluded_from_the_fitted_statistics():
    scaler = FoldScaler().fit([{"a": 1.0}, {"a": None}, {"a": 3.0}])
    assert scaler.means["a"] == pytest.approx(2.0)


@pytest.mark.unit
def test_refitting_replaces_rather_than_accumulates():
    scaler = FoldScaler().fit(TRAIN).fit([{"a": 100.0, "b": 1.0}, {"a": 102.0, "b": 3.0}])
    assert scaler.means["a"] == pytest.approx(101.0)


@pytest.mark.unit
def test_the_scaler_round_trips_so_a_fold_can_be_audited_later():
    scaler = FoldScaler().fit(TRAIN)
    restored = FoldScaler.from_dict(scaler.to_dict())
    assert restored.transform(TRAIN) == scaler.transform(TRAIN)


@pytest.mark.unit
def test_fitting_on_an_empty_fold_raises():
    with pytest.raises(ValueError, match="empty"):
        FoldScaler().fit([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_features_scaler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.features.scaler'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/features/scaler.py`:

```python
"""Training-only normalization (spec §8.1).

Fitted strictly on the training fold, persisted with it, applied unchanged to
validation and test. Fitting on the full sample is the textbook leak; it is
also the one people believe they have avoided when they have only avoided it in
one of the two places it occurs. See features/trailing.py for the other.

None is preserved, never imputed. Imputing invents data and hides how much of a
column is actually missing.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

Row = Mapping[str, float | None]


class FoldScaler:
    """Standardizes columns using statistics from one training fold."""

    def __init__(self) -> None:
        self.means: dict[str, float] = {}
        self.stds: dict[str, float] = {}
        self.degenerate_columns: set[str] = set()
        self._fitted = False

    def fit(self, rows: Sequence[Row]) -> FoldScaler:
        if not rows:
            raise ValueError("cannot fit a scaler on an empty training fold")

        self.means, self.stds, self.degenerate_columns = {}, {}, set()
        for column in rows[0]:
            values = [
                float(row[column])  # type: ignore[arg-type]
                for row in rows
                if row.get(column) is not None
                and not math.isnan(float(row[column]))  # type: ignore[arg-type]
            ]
            if not values:
                self.means[column], self.stds[column] = 0.0, 1.0
                self.degenerate_columns.add(column)
                continue
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            self.means[column] = mean
            if variance <= 0.0:
                # Pass through rather than divide by zero, but record it: a
                # constant feature is a modelling problem worth seeing.
                self.stds[column] = 1.0
                self.degenerate_columns.add(column)
            else:
                self.stds[column] = math.sqrt(variance)

        self._fitted = True
        return self

    def transform(self, rows: Sequence[Row]) -> list[dict[str, float | None]]:
        if not self._fitted:
            raise RuntimeError("scaler must be fit on the training fold before transform")

        out: list[dict[str, float | None]] = []
        for row in rows:
            missing = set(self.means) - set(row)
            unexpected = set(row) - set(self.means)
            if missing:
                raise KeyError(f"column(s) missing at transform time: {sorted(missing)}")
            if unexpected:
                raise KeyError(f"unexpected column(s) at transform time: {sorted(unexpected)}")
            out.append({
                column: (
                    None if value is None
                    else (float(value) - self.means[column]) / self.stds[column]
                )
                for column, value in row.items()
            })
        return out

    def to_dict(self) -> dict[str, object]:
        return {
            "means": dict(self.means),
            "stds": dict(self.stds),
            "degenerate_columns": sorted(self.degenerate_columns),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FoldScaler:
        scaler = cls()
        scaler.means = dict(payload["means"])  # type: ignore[arg-type]
        scaler.stds = dict(payload["stds"])  # type: ignore[arg-type]
        scaler.degenerate_columns = set(payload["degenerate_columns"])  # type: ignore[arg-type]
        scaler._fitted = True
        return scaler
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_features_scaler.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/features/scaler.py stock-trading-bot/tests/test_features_scaler.py
git commit -m "feat(stock-trading-bot): fold-scoped normalization, None preserved not imputed"
```

---

### Task 8: Walk-forward splitter with two-dimensional purging

**Files:**
- Create: `src/stock_trading_bot/model/splits.py`
- Test: `tests/test_model_splits.py`

Spec §9.1–9.2. **The highest-risk module in this plan.** A splitter that leaks produces
results that look excellent and mean nothing, and nothing downstream can detect it.

- [ ] **Step 1: Write the failing test**

Create `stock-trading-bot/tests/test_model_splits.py`:

```python
import pytest

from stock_trading_bot.model.splits import WalkForwardSplitter

SESSIONS = [f"2026-{m:02d}-{d:02d}" for m in (1, 2) for d in range(1, 26)]


def _rows(clusters=None):
    clusters = clusters or {}
    return [
        {"session": s, "cluster_id": clusters.get(s, f"c{i}")}
        for i, s in enumerate(SESSIONS)
    ]


@pytest.mark.unit
def test_folds_are_chronological():
    folds = WalkForwardSplitter(n_splits=3, horizon=1, embargo=0).split(_rows())
    for fold in folds:
        assert max(fold.train_index) < min(fold.val_index)


@pytest.mark.unit
def test_validation_folds_do_not_overlap():
    folds = WalkForwardSplitter(n_splits=3, horizon=1, embargo=0).split(_rows())
    seen: set[int] = set()
    for fold in folds:
        assert not (seen & set(fold.val_index))
        seen |= set(fold.val_index)


@pytest.mark.unit
def test_the_holdout_is_never_returned_by_split():
    """The untouched holdout must be unreachable through the ordinary API."""
    rows = _rows()
    splitter = WalkForwardSplitter(n_splits=3, horizon=1, embargo=0,
                                   holdout_fraction=0.2)
    used = {i for fold in splitter.split(rows) for i in (*fold.train_index, *fold.val_index)}
    assert used & set(splitter.holdout_index(rows)) == set()


@pytest.mark.unit
def test_the_holdout_is_the_final_fraction():
    rows = _rows()
    holdout = WalkForwardSplitter(n_splits=3, horizon=1, embargo=0,
                                  holdout_fraction=0.2).holdout_index(rows)
    assert len(holdout) == pytest.approx(len(rows) * 0.2, abs=1)
    assert min(holdout) > len(rows) * 0.75


@pytest.mark.unit
def test_a_label_window_reaching_into_validation_is_purged():
    """Horizon 5: a row 4 sessions before validation must be dropped."""
    folds = WalkForwardSplitter(n_splits=2, horizon=5, embargo=0).split(_rows())
    fold = folds[-1]
    val_start = min(fold.val_index)
    assert all(i + 5 < val_start for i in fold.train_index)
    assert fold.dropped_label_overlap > 0


@pytest.mark.unit
def test_a_row_safely_before_validation_survives():
    folds = WalkForwardSplitter(n_splits=2, horizon=5, embargo=0).split(_rows())
    fold = folds[-1]
    assert (min(fold.val_index) - 6) in fold.train_index


@pytest.mark.unit
def test_a_cluster_straddling_the_boundary_is_purged_even_without_label_overlap():
    """The case label-overlap purging cannot see, and the reason clusters exist.
    A single earnings thread spanning the split leaks across it."""
    rows = _rows()
    val_start = 25   # with n_splits=2 over 40 evaluable sessions
    straddler = 2    # far from the boundary: no label overlap at horizon 1
    rows[straddler]["cluster_id"] = "earnings"
    rows[val_start]["cluster_id"] = "earnings"

    fold = WalkForwardSplitter(n_splits=2, horizon=1, embargo=0).split(rows)[-1]
    assert straddler not in fold.train_index
    assert fold.dropped_cluster > 0


@pytest.mark.unit
def test_a_cluster_confined_to_training_is_not_purged():
    rows = _rows()
    rows[2]["cluster_id"] = "safe"
    rows[3]["cluster_id"] = "safe"
    fold = WalkForwardSplitter(n_splits=2, horizon=1, embargo=0).split(rows)[-1]
    assert 2 in fold.train_index and 3 in fold.train_index


@pytest.mark.unit
def test_the_embargo_removes_additional_sessions():
    plain = WalkForwardSplitter(n_splits=2, horizon=1, embargo=0).split(_rows())[-1]
    embargoed = WalkForwardSplitter(n_splits=2, horizon=1, embargo=5).split(_rows())[-1]
    assert len(embargoed.train_index) < len(plain.train_index)
    assert embargoed.dropped_embargo > 0


@pytest.mark.unit
def test_each_fold_reports_what_it_purged():
    """These numbers go in the evaluation header: a fold that purged 80% of its
    training data is not the fold anyone thinks it is."""
    fold = WalkForwardSplitter(n_splits=2, horizon=5, embargo=2).split(_rows())[-1]
    for attribute in ("dropped_label_overlap", "dropped_cluster", "dropped_embargo",
                      "train_clusters"):
        assert getattr(fold, attribute) >= 0


@pytest.mark.unit
def test_train_clusters_counts_distinct_surviving_clusters():
    rows = _rows(clusters=dict.fromkeys(SESSIONS[:10], "one"))
    fold = WalkForwardSplitter(n_splits=2, horizon=1, embargo=0).split(rows)[-1]
    assert fold.train_clusters < len(fold.train_index)


@pytest.mark.unit
def test_too_many_splits_raises_rather_than_yielding_empty_folds():
    with pytest.raises(ValueError, match="n_splits"):
        WalkForwardSplitter(n_splits=100, horizon=1, embargo=0).split(_rows())


@pytest.mark.unit
def test_an_empty_row_set_raises():
    with pytest.raises(ValueError):
        WalkForwardSplitter(n_splits=2, horizon=1, embargo=0).split([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_model_splits.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_trading_bot.model.splits'`

- [ ] **Step 3: Write the implementation**

Create `stock-trading-bot/src/stock_trading_bot/model/splits.py`:

```python
"""Chronological walk-forward splits with two-dimensional purging (spec §9.1-9.2).

A training row is dropped if EITHER:

  1. its label's forward-return window [t, t + horizon] reaches into the
     validation period, or
  2. it belongs to an event cluster with any member inside the validation
     period.

Condition 2 is why clusters exist and is invisible to condition 1. A single
earnings thread spanning the boundary leaks across it even when no individual
label window does: the same underlying event informs both sides.

An embargo of further sessions is applied on top.

The final `holdout_fraction` of the timeline is NEVER returned by `split`. It is
reachable only through `holdout_index`, so opening it is a deliberate act that
shows up in a diff.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_DEFAULT_HOLDOUT_FRACTION = 0.2


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold, with an account of what purging removed."""

    train_index: tuple[int, ...]
    val_index: tuple[int, ...]
    dropped_label_overlap: int
    dropped_cluster: int
    dropped_embargo: int
    train_clusters: int


class WalkForwardSplitter:
    def __init__(
        self,
        n_splits: int,
        horizon: int,
        embargo: int,
        holdout_fraction: float = _DEFAULT_HOLDOUT_FRACTION,
    ) -> None:
        self.n_splits = n_splits
        self.horizon = horizon
        self.embargo = embargo
        self.holdout_fraction = holdout_fraction

    def _evaluable_count(self, rows: Sequence[Mapping[str, object]]) -> int:
        return int(len(rows) * (1.0 - self.holdout_fraction))

    def holdout_index(self, rows: Sequence[Mapping[str, object]]) -> tuple[int, ...]:
        """The untouched holdout. Opening this is a deliberate act."""
        return tuple(range(self._evaluable_count(rows), len(rows)))

    def split(self, rows: Sequence[Mapping[str, object]]) -> list[Fold]:
        if not rows:
            raise ValueError("cannot split an empty row set")

        evaluable = self._evaluable_count(rows)
        if self.n_splits >= evaluable:
            raise ValueError(
                f"n_splits={self.n_splits} exceeds the {evaluable} evaluable rows"
            )

        block = evaluable // (self.n_splits + 1)
        if block < 1:
            raise ValueError(f"n_splits={self.n_splits} leaves no room for validation")

        folds: list[Fold] = []
        for k in range(1, self.n_splits + 1):
            val_start = k * block
            val_end = evaluable if k == self.n_splits else (k + 1) * block
            val_index = tuple(range(val_start, val_end))
            val_clusters = {rows[i].get("cluster_id") for i in val_index}

            train: list[int] = []
            label_overlap = cluster_drop = embargo_drop = 0
            for i in range(val_start):
                if i + self.horizon >= val_start:
                    label_overlap += 1
                    continue
                if i + self.horizon + self.embargo >= val_start:
                    embargo_drop += 1
                    continue
                if rows[i].get("cluster_id") in val_clusters:
                    cluster_drop += 1
                    continue
                train.append(i)

            folds.append(Fold(
                train_index=tuple(train),
                val_index=val_index,
                dropped_label_overlap=label_overlap,
                dropped_cluster=cluster_drop,
                dropped_embargo=embargo_drop,
                train_clusters=len({rows[i].get("cluster_id") for i in train}),
            ))
        return folds
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_model_splits.py -v`
Expected: PASS, 13 passed

If `test_a_cluster_straddling_the_boundary_is_purged_even_without_label_overlap` fails because
the chosen indices do not land where expected, **fix the indices in the test, not the purging
logic.** The behaviour under test is that a straddling cluster is dropped; the specific index
arithmetic is incidental.

- [ ] **Step 5: Commit**

```bash
git add stock-trading-bot/src/stock_trading_bot/model stock-trading-bot/tests/test_model_splits.py
git commit -m "feat(stock-trading-bot): walk-forward splits purged on label overlap and clusters

Condition 2 is invisible to condition 1: an earnings thread spanning the split
leaks across it even when no individual label window overlaps, because the same
underlying event informs both sides."
```

---
### Task 9: Panel assembly

**Files:**
- Create: `src/stock_trading_bot/model/panel.py`
- Test: `tests/test_model_panel.py`

Assembles `(ticker, session)` rows into a matrix: feature columns, target columns for each
kind and horizon, plus `cluster_id` and `known_at` carried alongside for the splitter.

Required behaviours:
- Column order is deterministic and identical across tickers.
- A row whose target is `None` is retained with a masked label, not silently dropped — the
  count of unlabelable rows belongs in the coverage report.
- Rows are sorted by `(session, ticker)`.
- The matrix reports `n_rows`, `n_clusters`, and `n_labelled` separately. **Never report a
  sample size without its cluster count beside it.**
- Building the panel twice from the same store produces byte-identical output.

---

### Task 10: `stock-trading build-panel <ticker>`

**Files:**
- Modify: `src/stock_trading_bot/cli.py`
- Test: `tests/test_cli_build_panel.py`

Writes the panel to `data/analysis/panel_<ticker>_<date>.json` and prints:

```
NOW: 512 rows, 178 clusters, 486 labelled (5d absolute)
     features: 6 tier-1, 4 tier-2, 7 tier-3
     unlabelable: 26 rows (forward window runs past the last session)
```

Cluster count sits next to row count in the output, because that is the number that decides
whether anything downstream has power.

---

### Task 11: Leakage verification

**Files:** none — this is the verification that matters most in this plan.

- [ ] **Step 1: The future-invariance property, end to end**

Build a panel as-of a date, then add later bars and documents to the store, rebuild as-of the
same date, and diff. **Every feature value must be byte-identical.** Any difference is a leak,
and this single check subsumes most of the unit tests above.

```bash
PYTHONPATH=src .venv/bin/python -c "
# build as-of T, append future data, rebuild as-of T, assert equality
"
```

- [ ] **Step 2: The shuffled-label sanity check**

Fit nothing yet — but confirm that with labels randomly permuted, the panel's
feature-target correlation is indistinguishable from zero. If it is not, the panel is leaking
and Plan 5 would report a spurious edge with total confidence.

- [ ] **Step 3: Inspect one row by hand**

Print a single `(ticker, session)` row with its features and its label, and reason through
each value against the raw store contents. **This is the check that finds the errors the
tests were written to miss**, because the tests encode what was already thought of.

- [ ] **Step 4: Record the shape**

Note rows, clusters, labelled rows, and the ratio between rows and clusters per ticker. That
ratio is the single most important number for Plan 5: it is the effective sample size, and it
determines whether the evaluation can detect anything at all.

---

## Definition of done

- [ ] `pytest`, `ruff`, `mypy --strict` clean; suite runs offline.
- [ ] Import-graph guard covers `features/` and `model/` and was shown to fail on a violation.
- [ ] Rebuilding a panel as-of a past date after appending future data yields identical output.
- [ ] The cluster-purge condition is tested with a case that label-overlap purging misses.
- [ ] The holdout is unreachable through the ordinary splitter API.
- [ ] Every reported sample size has its cluster count beside it.
- [ ] No target is named `alpha`.
- [ ] Rows-to-clusters ratio recorded per ticker.

## Out of scope

- **Any model.** No Ridge, no fitting, no prediction. Plan 5.
- **Any evaluation metric.** Plan 5, where MDE is reported before any point estimate.
- **pandas.** numpy suffices at this size and pandas 3.0.5 ships no `py.typed`, so it would
  force a mypy stub workaround for no benefit.
