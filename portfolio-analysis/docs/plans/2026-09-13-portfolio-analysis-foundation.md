# portfolio-analysis Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest six years of adjusted daily prices for a configured ticker list and emit the set of days whose beta-adjusted return exceeded 2.5x its own trailing volatility.

**Architecture:** Two CLI stages over a plain SQLite store.
`ingest-prices` fetches raw OHLC plus Yahoo's adjusted close and upserts one row per `(ticker, date)`.
`detect-moves` reads that table, computes per-day beta against a benchmark from a trailing 250-day OLS regression, derives the abnormal return and its trailing 60-day sigma, and writes the flagged days to both the store and a JSON artifact that Plan 2 consumes.
Pure computation lives in `moves.py` with no I/O, so the statistics are testable without a database or a network.

**Tech Stack:** Python 3.13, `uv`, `requests`, `pyyaml`, stdlib `sqlite3` and `statistics`, `pytest`, `ruff`, `mypy --strict`.

**Spec:** [`docs/specs/2026-09-13-portfolio-analysis-design.md`](../specs/2026-09-13-portfolio-analysis-design.md) — this plan implements §4.1, §5, §11 (price and move tables), and §12 (first two commands).

**Measured verification anchors.** All values below were measured against live Yahoo data on 2026-09-13 and are the assertions Task 11 checks:

| Quantity | Measured value |
|---|---|
| Price series returned for `years=6` | 1506 bars, 2020-09-14 .. 2026-09-11 |
| Evaluable range after 250-day warm-up | 2021-09-13 .. 2026-09-11, 1255 days |
| Flagged days at `z_threshold=2.5` | 30 (2.39% of evaluable days) |
| META 2024-04-25 return | -0.105613 |
| QQQ 2024-04-25 return | -0.004830 |
| META beta at 2024-04-25 | 1.490 |
| META abnormal return at 2024-04-25 | -0.098419 |
| META sigma_60 at 2024-04-25 | 0.026083 |
| META z at 2024-04-25 | -3.77 |
| META z at 2022-02-03 | -16.30 |

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, ruff/mypy/pytest configuration |
| `config/portfolio.yaml` | The universe, benchmark, move parameters, paths. Config, never hardcoded |
| `src/portfolio_analysis/naming.py` | Ticker sanitization for anything reaching a URL or a filesystem path |
| `src/portfolio_analysis/config.py` | Typed loading of `portfolio.yaml`; `PROJECT_ROOT` and `resolve_path` |
| `src/portfolio_analysis/store.py` | SQLite schema, connection lifecycle, price upsert, move upsert, series reads |
| `src/portfolio_analysis/prices.py` | Yahoo chart v8 adapter. HTTP and parsing only, no statistics |
| `src/portfolio_analysis/moves.py` | Pure statistics: return alignment, OLS beta, abnormal return, sigma, z, flagging. No I/O |
| `src/portfolio_analysis/artifacts.py` | Writing and reading the `data/moves/<TICKER>.json` artifact |
| `src/portfolio_analysis/cli.py` | `ingest-prices` and `detect-moves` subcommands |

`prices.py` does no statistics and `moves.py` does no I/O.
That boundary is what lets Task 9 assert the exact measured `z` for 2024-04-25 from a fixture, with no network and no database.

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/portfolio_analysis/__init__.py`
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Test: `tests/test_scaffold.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "portfolio-analysis"
version = "0.1.0"
description = "Retrospective attribution of large single-day equity moves to dated, cited events."
requires-python = ">=3.13"
# Only what code in this repo actually imports today. The Muse Spark client
# arrives in Plan 3; declaring openai now would make the lockfile lie.
dependencies = [
    "requests>=2.32",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "mypy>=1.11", "types-requests", "types-PyYAML"]

[project.scripts]
portfolio-analysis = "portfolio_analysis.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/portfolio_analysis"]

[tool.pytest.ini_options]
testpaths = ["tests"]
# Import the package from src/ directly rather than via the editable-install
# .pth file. uv writes that .pth with the macOS UF_HIDDEN flag set, and
# CPython's site.py skips hidden .pth files, so an editable install can be
# present and silently unimportable.
pythonpath = ["src"]
markers = [
    "unit: fast test with no network access",
    "network: hits a live vendor API; excluded from the default run",
]
addopts = "-q --strict-markers -m 'not network'"

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
files = ["src"]
strict = true
warn_unreachable = true
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.pytest_cache/
data/
out/
```

- [ ] **Step 3: Create the package and test package**

```bash
mkdir -p src/portfolio_analysis tests
cat > src/portfolio_analysis/__init__.py <<'EOF'
"""Retrospective attribution of large single-day equity moves.

This package explains the past. It makes no predictive claim and produces no
trading signal. See docs/specs/2026-09-13-portfolio-analysis-design.md §2.
"""
EOF
touch tests/__init__.py
```

- [ ] **Step 4: Write the failing test**

```python
# tests/test_scaffold.py
import pytest


@pytest.mark.unit
def test_package_imports():
    import portfolio_analysis  # noqa: F401
```

- [ ] **Step 5: Create the venv and run the test to verify it passes**

```bash
uv venv -p 3.13
uv pip install -e ".[dev]"
.venv/bin/pytest tests/test_scaffold.py -v
```

Expected: `1 passed`.
Do not use `pip` — it is broken on this machine's Homebrew Python 3.14 with a `pyexpat` symbol error. Use `uv` only.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/portfolio_analysis/__init__.py tests/__init__.py tests/test_scaffold.py
git commit -m "chore(portfolio-analysis): project scaffold"
```

---

## Task 2: Ticker sanitization

Tickers reach both a URL path segment and a filesystem path (`data/moves/<TICKER>.json`), so they are a path-traversal vector.

**Files:**
- Create: `src/portfolio_analysis/naming.py`
- Test: `tests/test_naming.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_naming.py
import pytest

from portfolio_analysis.naming import safe_ticker_component


@pytest.mark.unit
def test_uppercases_a_valid_ticker():
    assert safe_ticker_component("meta") == "META"


@pytest.mark.unit
def test_allows_dots_and_hyphens_inside():
    assert safe_ticker_component("BRK.B") == "BRK.B"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["../etc", "A..B", "", "NVDA.", ".NVDA", "A" * 13, "a/b"])
def test_rejects_path_unsafe_input(bad):
    with pytest.raises(ValueError):
        safe_ticker_component(bad)


@pytest.mark.unit
def test_rejects_non_string():
    with pytest.raises(TypeError):
        safe_ticker_component(123)


@pytest.mark.unit
def test_validates_before_uppercasing():
    """U+017F uppercases to 'S', so 'snow' and its long-s spelling would
    otherwise collapse to the same cache key and serve one company's data
    for another's. Validating first means upper() only ever runs on ASCII.

    Written as an escape, not as the literal glyph: ruff's RUF001 flags
    ambiguous unicode in string literals, and the ambiguity is the whole
    point of this test. The escape is the same string to Python and names
    the codepoint under test instead of hiding it in a homoglyph."""
    with pytest.raises(ValueError):
        safe_ticker_component("\u017fnow")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_naming.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.naming'`

- [ ] **Step 3: Write the implementation**

```python
# src/portfolio_analysis/naming.py
"""Ticker sanitization.

Tickers reach URL path segments and filesystem paths (data/moves/{ticker}.json),
so an unsanitized symbol is both a path-traversal vector and an aliasing hazard.
Every ticker crossing an I/O boundary passes through here first.

Order matters: validate the raw input, THEN uppercase. Doing it the other way
lets str.upper() launder non-ASCII into ASCII - U+017F LATIN SMALL LETTER LONG S
uppercases to 'S', so 'snow' and its long-s spelling collapse to the same cache
key. Validating first means upper() only ever runs on ASCII, where it is pure
and length-preserving.

Adapted from stock_trading_bot.naming, which established this rule.
"""
from __future__ import annotations

import re

# One to twelve chars. Must start and end alphanumeric: a trailing dot is
# stripped by the Win32 API, which would make 'NVDA.' and 'NVDA' the same file.
# fullmatch (not match with $) because $ also matches before a trailing newline.
_ALLOWED = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,10}[A-Za-z0-9])?")


def safe_ticker_component(raw: str) -> str:
    """Normalize a ticker to uppercase and reject anything path-unsafe.

    Raises rather than sanitizing silently: a ticker we cannot recognize is a
    bug upstream, not something to paper over.
    """
    if not isinstance(raw, str):
        raise TypeError(f"ticker must be a string, got {type(raw).__name__}")
    candidate = raw.strip()
    # The regex alone accepts 'A..B', so this check is load-bearing.
    if ".." in candidate or not _ALLOWED.fullmatch(candidate):
        raise ValueError(f"unsafe ticker component: {raw!r}")
    return candidate.upper()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_naming.py -v`
Expected: `11 passed` (four standalone tests plus the seven `parametrize` cases)

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/naming.py tests/test_naming.py
git commit -m "feat(portfolio-analysis): ticker sanitization at the I/O boundary"
```

---

## Task 3: Configuration

**Files:**
- Create: `config/portfolio.yaml`
- Create: `src/portfolio_analysis/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write `config/portfolio.yaml`**

```yaml
# The universe. v1 is META only (spec §3): one name end-to-end beats five
# names half-done. Adding an entry here is the only change needed to widen it.
tickers:
  - symbol: META
    cik: 1326801
    name: Meta Platforms, Inc.
    aliases: ["Meta", "Facebook", "Meta Platforms"]

# Beta is measured against this. QQQ matches the sibling repo's watchlist.
benchmark: QQQ

# Six years, not five. A 250-day beta window consumes the first trading year,
# so five years of fetched prices would yield only four years of evaluable
# days (spec §5).
price_years: 6

moves:
  beta_window: 250
  sigma_window: 60
  z_threshold: 2.5

# Alpha Vantage news coverage begins around here. Moves before this date are
# flagged news_coverage_known_thin in Plan 2 (spec §7).
news_coverage_start: "2022-03-01"

paths:
  db: data/prices.sqlite
  moves: data/moves
  events: data/events
  reasons: data/reasons
  cache: data/cache
  out: out
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_config.py
import pytest

from portfolio_analysis.config import PROJECT_ROOT, load_portfolio, resolve_path


@pytest.mark.unit
def test_loads_the_default_portfolio():
    portfolio = load_portfolio()
    assert portfolio.symbols == ("META",)
    assert portfolio.benchmark == "QQQ"
    assert portfolio.price_years == 6


@pytest.mark.unit
def test_move_params_come_from_config():
    params = load_portfolio().move_params
    assert params.beta_window == 250
    assert params.sigma_window == 60
    assert params.z_threshold == 2.5


@pytest.mark.unit
def test_entry_lookup_is_case_insensitive():
    entry = load_portfolio().entry("meta")
    assert entry.cik == 1326801
    assert entry.name == "Meta Platforms, Inc."


@pytest.mark.unit
def test_entry_lookup_raises_on_unknown_symbol():
    with pytest.raises(KeyError):
        load_portfolio().entry("TSLA")


@pytest.mark.unit
def test_resolve_maps_names_and_aliases_to_symbols():
    portfolio = load_portfolio()
    assert portfolio.resolve("Facebook") == "META"
    assert portfolio.resolve("meta platforms, inc.") == "META"
    assert portfolio.resolve("TSLA") is None


@pytest.mark.unit
def test_paths_resolve_against_the_project_root_not_the_cwd():
    """The CLI must write to the same database regardless of invocation dir."""
    assert resolve_path("data/prices.sqlite") == PROJECT_ROOT / "data" / "prices.sqlite"
    assert (PROJECT_ROOT / "pyproject.toml").exists()


@pytest.mark.unit
def test_sigma_window_must_be_smaller_than_beta_window():
    """compute_moves derives sigma inside the beta window, so a sigma window
    at least as large as the beta window would index before the series start."""
    from portfolio_analysis.config import MoveParams

    with pytest.raises(ValueError):
        MoveParams(beta_window=60, sigma_window=60, z_threshold=2.5)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.config'`

- [ ] **Step 4: Write the implementation**

```python
# src/portfolio_analysis/config.py
"""Configuration loading.

The universe is config, never hardcoded, so it can be widened without touching
code (spec §3).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: The package lives at <root>/src/portfolio_analysis/, so the project root is
#: two levels up. Paths resolve against this rather than the process cwd, so
#: the CLI writes to the same database regardless of which directory it was
#: invoked from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = PROJECT_ROOT / "config"


def resolve_path(relative: str) -> Path:
    """Resolve a configured relative path against the project root."""
    return PROJECT_ROOT / relative


@dataclass(frozen=True)
class MoveParams:
    """Parameters of the move-detection rule (spec §5)."""

    beta_window: int
    sigma_window: int
    z_threshold: float

    def __post_init__(self) -> None:
        if self.sigma_window >= self.beta_window:
            raise ValueError(
                "sigma_window must be smaller than beta_window: sigma is derived "
                f"inside the beta window, got {self.sigma_window} >= {self.beta_window}"
            )
        if self.z_threshold <= 0:
            raise ValueError(f"z_threshold must be positive, got {self.z_threshold}")


@dataclass(frozen=True)
class PortfolioEntry:
    symbol: str
    cik: int
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Portfolio:
    entries: tuple[PortfolioEntry, ...]
    benchmark: str
    price_years: int
    move_params: MoveParams
    news_coverage_start: str
    paths: dict[str, str]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(e.symbol for e in self.entries)

    def entry(self, symbol: str) -> PortfolioEntry:
        for e in self.entries:
            if e.symbol == symbol.upper():
                return e
        raise KeyError(f"{symbol!r} is not in the portfolio")

    def resolve(self, text: str) -> str | None:
        """Resolve a ticker, company name, or alias to a symbol.

        Returns None when unknown. Matching is exact after case folding.
        """
        needle = text.strip().casefold()
        for e in self.entries:
            if any(needle == c.casefold() for c in (e.symbol, e.name, *e.aliases)):
                return e.symbol
        return None

    def path(self, key: str) -> Path:
        return resolve_path(self.paths[key])


def load_portfolio(path: Path | None = None) -> Portfolio:
    raw: dict[str, Any] = yaml.safe_load(
        (path or _CONFIG_DIR / "portfolio.yaml").read_text()
    )
    entries = tuple(
        PortfolioEntry(
            symbol=t["symbol"],
            cik=int(t["cik"]),
            name=t["name"],
            aliases=tuple(t.get("aliases", ())),
        )
        for t in raw["tickers"]
    )
    moves = raw["moves"]
    return Portfolio(
        entries=entries,
        benchmark=raw["benchmark"],
        price_years=int(raw["price_years"]),
        move_params=MoveParams(
            beta_window=int(moves["beta_window"]),
            sigma_window=int(moves["sigma_window"]),
            z_threshold=float(moves["z_threshold"]),
        ),
        news_coverage_start=str(raw["news_coverage_start"]),
        paths=dict(raw["paths"]),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add config/portfolio.yaml src/portfolio_analysis/config.py tests/test_config.py
git commit -m "feat(portfolio-analysis): typed portfolio config with validated move params"
```

---

## Task 4: SQLite store

**Files:**
- Create: `src/portfolio_analysis/store.py`
- Test: `tests/test_store.py`

Two deliberate divergences from `stock_trading_bot.store`, both documented in spec §11:

1. No `known_at` / `observed_at` / `valid_from` columns and no `PointInTimeView`. That machinery prevents a forward-looking model from seeing the future; this project exists to look backward with full hindsight, so carrying it would imply a guarantee this project does not make.
2. Prices are **upserted**, not appended. An adjusted close is legitimately rewritten by a later split or dividend, and a single consistent present-day adjusted series is exactly what a five-year retrospective chart should show. Raw OHLC is stored alongside, so reconstruction stays possible without a re-fetch.

Note also that spec §11 named the return column `return`, which is a reserved word in SQL. It is `ret` here and everywhere downstream.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
import pytest

from portfolio_analysis.store import Store

BAR = {
    "ticker": "META",
    "date": "2024-04-25",
    "open": 493.29,
    "high": 447.9,
    "low": 439.71,
    "close": 441.38,
    "adj_close": 441.38,
    "volume": 100_000_000.0,
    "source": "yahoo",
}


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "t.sqlite")
    yield s
    s.close()


@pytest.mark.unit
def test_insert_then_read_a_bar(store):
    store.upsert_price_bars([BAR])
    series = store.adjusted_series("META")
    assert series == {"2024-04-25": 441.38}


@pytest.mark.unit
def test_reinserting_the_same_date_upserts_rather_than_raising(store):
    """An adjusted close is legitimately rewritten by a later split, so a
    second observation must replace the first, not collide with it."""
    store.upsert_price_bars([BAR])
    store.upsert_price_bars([{**BAR, "adj_close": 220.69}])
    assert store.adjusted_series("META") == {"2024-04-25": 220.69}
    assert store.price_bar_count("META") == 1


@pytest.mark.unit
def test_adjusted_series_is_ordered_by_date(store):
    store.upsert_price_bars([
        {**BAR, "date": "2024-04-26", "adj_close": 443.29},
        {**BAR, "date": "2024-04-24", "adj_close": 493.5},
        BAR,
    ])
    assert list(store.adjusted_series("META")) == [
        "2024-04-24", "2024-04-25", "2024-04-26"
    ]


@pytest.mark.unit
def test_adjusted_series_is_empty_for_an_unknown_ticker(store):
    assert store.adjusted_series("TSLA") == {}


@pytest.mark.unit
def test_a_malformed_date_is_refused_at_the_write_boundary(store):
    """Lexicographic ordering must equal chronological ordering, which holds
    only if every date is fixed-width ISO. Enforced on the COLUMN so a
    fixture or a notebook INSERT cannot break it either."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_price_bars([{**BAR, "date": "2024-4-25"}])


@pytest.mark.unit
def test_upsert_and_read_moves(store):
    move = {
        "ticker": "META",
        "date": "2024-04-25",
        "ret": -0.105613,
        "benchmark": "QQQ",
        "benchmark_return": -0.004830,
        "beta": 1.490,
        "abnormal_return": -0.098419,
        "sigma_60": 0.026083,
        "z": -3.77,
    }
    store.upsert_moves([move])
    rows = store.moves("META")
    assert len(rows) == 1
    assert rows[0]["z"] == pytest.approx(-3.77)
    assert rows[0]["benchmark"] == "QQQ"


@pytest.mark.unit
def test_recomputing_moves_replaces_rather_than_duplicates(store):
    move = {
        "ticker": "META", "date": "2024-04-25", "ret": -0.105613,
        "benchmark": "QQQ", "benchmark_return": -0.004830, "beta": 1.490,
        "abnormal_return": -0.098419, "sigma_60": 0.026083, "z": -3.77,
    }
    store.upsert_moves([move])
    store.upsert_moves([{**move, "z": -3.80}])
    rows = store.moves("META")
    assert len(rows) == 1
    assert rows[0]["z"] == pytest.approx(-3.80)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.store'`

- [ ] **Step 3: Write the implementation**

```python
# src/portfolio_analysis/store.py
"""SQLite store for prices and detected moves (spec §11).

Deliberately NOT a point-in-time store. The sibling project stock-trading-bot
carries event_time/observed_at/known_at/valid_from on every fact to stop a
forward-looking model from seeing the future. This project exists to look
backward with full hindsight, so that machinery would be dead weight that
implies a guarantee this project does not make.

Prices are upserted rather than appended: an adjusted close is legitimately
rewritten by a later split or dividend, and one consistent present-day adjusted
series is exactly what a five-year retrospective chart should show. Raw OHLC is
stored alongside, so reconstruction stays possible without a re-fetch.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

#: Fixed-width ISO date. Pinned on the COLUMN, not merely on whoever writes the
#: row, so that lexicographic ordering always equals chronological ordering -
#: a property every window slice in moves.py depends on.
_ISO_DATE = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS price_bar (
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL CHECK (typeof(date) = 'text' AND date GLOB '{_ISO_DATE}'),
    open       REAL NOT NULL,
    high       REAL NOT NULL,
    low        REAL NOT NULL,
    close      REAL NOT NULL,
    adj_close  REAL NOT NULL,
    volume     REAL NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS move (
    ticker           TEXT NOT NULL,
    date             TEXT NOT NULL CHECK (typeof(date) = 'text' AND date GLOB '{_ISO_DATE}'),
    ret              REAL NOT NULL,
    benchmark        TEXT NOT NULL,
    benchmark_return REAL NOT NULL,
    beta             REAL NOT NULL,
    abnormal_return  REAL NOT NULL,
    sigma_60         REAL NOT NULL,
    z                REAL NOT NULL,
    computed_at      TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
"""

_PRICE_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close",
    "adj_close", "volume", "source", "fetched_at",
)
_MOVE_COLUMNS = (
    "ticker", "date", "ret", "benchmark", "benchmark_return",
    "beta", "abnormal_return", "sigma_60", "z", "computed_at",
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Store:
    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> Store:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        return cls(conn, target)

    def close(self) -> None:
        self._conn.close()

    def _upsert(
        self, table: str, columns: tuple[str, ...], rows: Iterable[Mapping[str, object]]
    ) -> int:
        placeholders = ", ".join(f":{c}" for c in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in ("ticker", "date"))
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT (ticker, date) DO UPDATE SET {updates}"
        )
        stamped = [{**row, "fetched_at": _now(), "computed_at": _now()} for row in rows]
        payload = [{c: row[c] for c in columns} for row in stamped]
        with self._conn:
            self._conn.executemany(sql, payload)
        return len(payload)

    def upsert_price_bars(self, bars: Iterable[Mapping[str, object]]) -> int:
        return self._upsert("price_bar", _PRICE_COLUMNS, bars)

    def upsert_moves(self, moves: Iterable[Mapping[str, object]]) -> int:
        return self._upsert("move", _MOVE_COLUMNS, moves)

    def adjusted_series(self, ticker: str) -> dict[str, float]:
        """Date -> adjusted close, ordered by date."""
        cursor = self._conn.execute(
            "SELECT date, adj_close FROM price_bar WHERE ticker = ? ORDER BY date",
            (ticker.upper(),),
        )
        return {row["date"]: float(row["adj_close"]) for row in cursor}

    def price_bar_count(self, ticker: str) -> int:
        cursor = self._conn.execute(
            "SELECT COUNT(*) AS n FROM price_bar WHERE ticker = ?", (ticker.upper(),)
        )
        return int(cursor.fetchone()["n"])

    def moves(self, ticker: str) -> list[dict[str, object]]:
        cursor = self._conn.execute(
            "SELECT * FROM move WHERE ticker = ? ORDER BY date", (ticker.upper(),)
        )
        return [dict(row) for row in cursor]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/store.py tests/test_store.py
git commit -m "feat(portfolio-analysis): sqlite store for prices and moves

Upsert rather than append: an adjusted close is legitimately rewritten by a
later split, and a retrospective chart wants one consistent present-day
series. No point-in-time columns - this project exists to use hindsight."
```

---

## Task 5: Yahoo price adapter

**Files:**
- Create: `src/portfolio_analysis/prices.py`
- Test: `tests/test_prices.py`

Three findings this adapter is built on, each already established:

- **Stooq is unusable.** It answers a JavaScript proof-of-work challenge with HTTP 200 and an HTML body. `stock-trading-bot` established this; do not add a Stooq path.
- **`adjclose` is read, not ignored.** The sibling repo deliberately ignores it and reconstructs adjustment from dated corporate actions, because a vendor's adjusted series is retroactively revised and that corrupts a point-in-time backtest. Here the present-day adjusted series is the correct input (spec §11).
- **`period1`/`period2` epoch bounds, not `range`.** The chart API has no `6y` range value, and six years is required to yield five evaluable ones (spec §5). Verified against live Yahoo on 2026-09-13: 1506 bars, 2020-09-14 .. 2026-09-11.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prices.py
from datetime import UTC, datetime
from unittest import mock

import pytest

from portfolio_analysis import prices

NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=UTC)

# Two sessions plus one holiday row Yahoo padded with nulls.
PAYLOAD = {
    "chart": {
        "result": [{
            "meta": {"gmtoffset": -14400},
            "timestamp": [1713974400, 1714060800, 1714147200],
            "indicators": {
                "quote": [{
                    "open": [493.29, 441.0, None],
                    "high": [497.0, 447.9, None],
                    "low": [488.0, 439.71, None],
                    "close": [493.5, 441.38, None],
                    "volume": [22000000.0, 100000000.0, None],
                }],
                "adjclose": [{"adjclose": [493.5, 441.38, None]}],
            },
        }]
    }
}


def _patch(payload=PAYLOAD):
    return mock.patch.object(prices, "_http_get_json", return_value=payload)


@pytest.mark.unit
def test_parses_bars_with_the_adjusted_close():
    with _patch():
        bars = prices.fetch_yahoo("META", years=6, now=NOW)
    assert len(bars) == 2
    assert bars[0]["ticker"] == "META"
    assert bars[0]["close"] == 493.5
    assert bars[0]["adj_close"] == 493.5
    assert bars[0]["source"] == "yahoo"


@pytest.mark.unit
def test_a_padded_holiday_row_is_dropped_not_zero_filled():
    """Yahoo pads holidays and halts with nulls. A partial bar is not a bar,
    and a zero-filled one would produce a fabricated -100% return."""
    with _patch():
        bars = prices.fetch_yahoo("META", years=6, now=NOW)
    assert [b["date"] for b in bars] == ["2024-04-24", "2024-04-25"]


@pytest.mark.unit
def test_dates_use_the_exchange_offset_not_utc():
    """Yahoo timestamps are session instants in UTC. The exchange offset must
    be applied before taking the calendar date, or a late-session timestamp
    lands on the following day and every return around it shifts by one."""
    with _patch():
        bars = prices.fetch_yahoo("META", years=6, now=NOW)
    assert bars[1]["date"] == "2024-04-25"


@pytest.mark.unit
def test_requests_epoch_bounds_rather_than_a_range():
    with _patch() as fake:
        prices.fetch_yahoo("META", years=6, now=NOW)
    url = fake.call_args[0][0]
    p1, p2 = prices.epoch_window(6, NOW)
    assert f"period1={p1}" in url
    assert f"period2={p2}" in url
    # The chart API has no `6y` range value; that is why epoch bounds are used.
    assert "range=" not in url


@pytest.mark.unit
def test_the_epoch_window_spans_six_years_including_the_leap_day():
    """6 * 365.25 = 2191.5 days. The half day matters: subtracted from a
    12:00 `now` it lands on 00:00 of the same calendar day, not 12:00."""
    p1, p2 = prices.epoch_window(6, NOW)
    start = datetime.fromtimestamp(p1, UTC)
    assert (start.year, start.month, start.day) == (2020, 9, 13)
    assert start.hour == 0
    assert p2 == int(NOW.timestamp())


@pytest.mark.unit
def test_an_empty_result_raises_rather_than_returning_no_bars():
    """'This ticker has no history' and 'the vendor did not answer' must not
    look the same to the caller."""
    with _patch({"chart": {"result": None, "error": "Not Found"}}):
        with pytest.raises(prices.VendorResponseError):
            prices.fetch_yahoo("META", years=6, now=NOW)


@pytest.mark.unit
def test_a_missing_adjclose_block_raises():
    payload = {
        "chart": {"result": [{
            "meta": {"gmtoffset": 0},
            "timestamp": [1713974400],
            "indicators": {"quote": [{
                "open": [1.0], "high": [1.0], "low": [1.0],
                "close": [1.0], "volume": [1.0],
            }]},
        }]}
    }
    with _patch(payload), pytest.raises(prices.VendorResponseError):
        prices.fetch_yahoo("META", years=6, now=NOW)


@pytest.mark.unit
def test_ticker_is_sanitized_before_reaching_the_url():
    with pytest.raises(ValueError):
        prices.fetch_yahoo("../etc", years=6, now=NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_prices.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.prices'`

- [ ] **Step 3: Write the implementation**

```python
# src/portfolio_analysis/prices.py
"""Adjusted daily price ingestion from Yahoo's chart API (spec §4.1).

Reads BOTH indicators.quote (raw OHLCV) and indicators.adjclose. The sibling
project stock-trading-bot deliberately ignores adjclose and reconstructs split
adjustment from dated corporate actions, because a vendor's adjusted series is
retroactively revised and that corrupts a point-in-time backtest. Here the
present-day adjusted series is the correct input for a retrospective chart, so
it is consumed directly and the raw OHLC is kept alongside (spec §11).

Uses period1/period2 epoch bounds rather than `range`: the API has no `6y`
value, and six years of prices are needed to yield five evaluable ones after
the 250-day beta warm-up (spec §5).

Stooq is not a fallback. It sits behind a JavaScript proof-of-work challenge
that it answers with HTTP 200 and an HTML body, established in the sibling repo.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from portfolio_analysis.naming import safe_ticker_component

_YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?period1={p1}&period2={p2}&interval=1d"
)
_UA = "portfolio-analysis/0.1 (research)"

#: The raw OHLCV fields read from indicators.quote.
_QUOTE_FIELDS = ("open", "high", "low", "close", "volume")

#: 365.25 days per year, so a six-year window spans the leap days it contains.
_DAYS_PER_YEAR = 365.25


class VendorResponseError(RuntimeError):
    """The vendor answered, but not with the data we asked for."""


def _http_get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": _UA}, timeout=60)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def epoch_window(years: int, now: datetime) -> tuple[int, int]:
    """Inclusive epoch-second bounds for a trailing `years` window."""
    start = now - timedelta(days=years * _DAYS_PER_YEAR)
    return int(start.timestamp()), int(now.timestamp())


def fetch_yahoo(
    ticker: str, *, years: int, now: datetime | None = None
) -> list[dict[str, object]]:
    """Daily bars with raw OHLCV and the adjusted close, oldest first."""
    symbol = safe_ticker_component(ticker)
    p1, p2 = epoch_window(years, now or datetime.now(UTC))
    payload = _http_get_json(_YAHOO_URL.format(symbol=symbol, p1=p1, p2=p2))

    results = payload.get("chart", {}).get("result")
    if not results:
        error = payload.get("chart", {}).get("error")
        raise VendorResponseError(f"yahoo returned no result for {symbol}: {error!r}")

    result = results[0]
    timestamps: Sequence[int] = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    quote: dict[str, Sequence[float | None]] = indicators["quote"][0]

    adjclose_block = indicators.get("adjclose")
    if not adjclose_block:
        raise VendorResponseError(
            f"yahoo returned no adjclose for {symbol}; this project consumes the "
            "adjusted series directly and cannot substitute the raw close"
        )
    adjusted: Sequence[float | None] = adjclose_block[0]["adjclose"]

    # The exchange's UTC offset, so a timestamp maps to the local trading date
    # rather than to whatever date it happens to be in UTC.
    gmtoffset = int(result.get("meta", {}).get("gmtoffset", 0))

    bars: list[dict[str, object]] = []
    for index, epoch in enumerate(timestamps):
        values = {field: quote[field][index] for field in _QUOTE_FIELDS}
        values["adj_close"] = adjusted[index]
        # Yahoo pads holidays and halts with nulls. A partial bar is not a bar,
        # and a zero-filled one would produce a fabricated -100% return.
        if any(value is None for value in values.values()):
            continue
        date = (
            datetime.fromtimestamp(epoch, UTC) + timedelta(seconds=gmtoffset)
        ).strftime("%Y-%m-%d")
        bars.append({
            "ticker": symbol,
            "date": date,
            **{k: float(v) for k, v in values.items()},  # type: ignore[arg-type]
            "source": "yahoo",
        })
    return bars
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_prices.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/prices.py tests/test_prices.py
git commit -m "feat(portfolio-analysis): yahoo adjusted-price adapter over six years

period1/period2 epoch bounds because the chart API has no 6y range value,
and six fetched years are needed to yield five evaluable ones after the
250-day beta warm-up."
```

---

## Task 6: `ingest-prices` command

**Files:**
- Create: `src/portfolio_analysis/cli.py`
- Test: `tests/test_cli_ingest.py`

The benchmark is fetched alongside the universe, not separately. Beta cannot be computed without it, so an ingest that skips it produces a store that looks complete and is not.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_ingest.py
from unittest import mock

import pytest

from portfolio_analysis import cli
from portfolio_analysis.store import Store


def _bars(ticker, dates):
    return [{
        "ticker": ticker, "date": d, "open": 1.0, "high": 1.0, "low": 1.0,
        "close": 1.0, "adj_close": 1.0 + i, "volume": 1.0, "source": "yahoo",
    } for i, d in enumerate(dates)]


@pytest.mark.unit
def test_ingest_fetches_the_universe_and_the_benchmark(tmp_path):
    db = tmp_path / "t.sqlite"
    calls = []

    def fake_fetch(ticker, *, years, now=None):
        calls.append((ticker, years))
        return _bars(ticker, ["2024-04-24", "2024-04-25"])

    with mock.patch.object(cli.prices, "fetch_yahoo", side_effect=fake_fetch):
        assert cli.main(["ingest-prices", "--db", str(db)]) == 0

    assert calls == [("META", 6), ("QQQ", 6)]
    store = Store.open(db)
    try:
        assert store.price_bar_count("META") == 2
        assert store.price_bar_count("QQQ") == 2
    finally:
        store.close()


@pytest.mark.unit
def test_ingest_accepts_a_single_ticker_by_alias(tmp_path):
    db = tmp_path / "t.sqlite"
    calls = []

    def fake_fetch(ticker, *, years, now=None):
        calls.append(ticker)
        return _bars(ticker, ["2024-04-25"])

    with mock.patch.object(cli.prices, "fetch_yahoo", side_effect=fake_fetch):
        assert cli.main(["ingest-prices", "Facebook", "--db", str(db)]) == 0

    assert calls == ["META", "QQQ"]


@pytest.mark.unit
def test_ingest_rejects_a_ticker_outside_the_portfolio(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    with mock.patch.object(cli.prices, "fetch_yahoo") as fake:
        assert cli.main(["ingest-prices", "TSLA", "--db", str(db)]) == 2
    fake.assert_not_called()
    assert "not in the portfolio" in capsys.readouterr().err


@pytest.mark.unit
def test_no_subcommand_prints_usage_and_returns_two(capsys):
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.cli'`

- [ ] **Step 3: Write the implementation**

```python
# src/portfolio_analysis/cli.py
"""Command-line entry point.

This tool explains past price moves. It has no brokerage integration, places
no orders, and produces no forward-looking signal (spec §2).
"""
from __future__ import annotations

import argparse
import sys

from portfolio_analysis import prices
from portfolio_analysis.config import Portfolio, load_portfolio
from portfolio_analysis.store import Store


def _selected_symbols(portfolio: Portfolio, requested: str | None) -> list[str] | None:
    """The universe, or the single resolved symbol. None means unresolvable."""
    if requested is None:
        return list(portfolio.symbols)
    symbol = portfolio.resolve(requested)
    return None if symbol is None else [symbol]


def _ingest_prices(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(
            f"{args.ticker!r} is not in the portfolio; add it to config/portfolio.yaml",
            file=sys.stderr,
        )
        return 2

    # The benchmark is fetched alongside the universe, never separately. Beta
    # cannot be computed without it, so an ingest that skips it leaves a store
    # that looks complete and is not.
    targets = [*symbols, portfolio.benchmark]

    store = Store.open(args.db or portfolio.path("db"))
    try:
        for symbol in targets:
            bars = prices.fetch_yahoo(symbol, years=portfolio.price_years)
            written = store.upsert_price_bars(bars)
            first = bars[0]["date"] if bars else "-"
            last = bars[-1]["date"] if bars else "-"
            print(f"{symbol}: {written} bar(s) upserted, {first} .. {last}")
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="portfolio-analysis",
        description="Retrospective attribution of large single-day equity moves.",
    )
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest-prices", help="fetch adjusted daily bars")
    ingest.add_argument(
        "ticker", nargs="?", default=None,
        help="ticker, company name, or alias; omit for the whole portfolio",
    )
    ingest.add_argument("--db", default=None, help="override the configured database")
    ingest.set_defaults(func=_ingest_prices)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_usage()
        return 2
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_ingest.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/cli.py tests/test_cli_ingest.py
git commit -m "feat(portfolio-analysis): ingest-prices command

Fetches the benchmark alongside the universe - beta cannot be computed
without it, so skipping it leaves a store that looks complete and is not."
```

---

## Task 7: Return alignment

**Files:**
- Create: `src/portfolio_analysis/moves.py`
- Test: `tests/test_moves_alignment.py`

Returns are computed over **consecutive dates present in both series**.
A date missing from one series would otherwise produce a two-day return labelled as one day, which is a fabricated move.
Up to five dropped dates are tolerated as halts; more than that means the two series disagree about the trading calendar and the run stops.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_moves_alignment.py
import pytest

from portfolio_analysis.moves import aligned_returns


@pytest.mark.unit
def test_returns_are_computed_between_consecutive_common_dates():
    asset = {"2024-01-02": 100.0, "2024-01-03": 110.0, "2024-01-04": 99.0}
    bench = {"2024-01-02": 50.0, "2024-01-03": 51.0, "2024-01-04": 51.0}
    dates, ar, br = aligned_returns(asset, bench)
    assert dates == ["2024-01-03", "2024-01-04"]
    assert ar == pytest.approx([0.10, -0.10])
    assert br == pytest.approx([0.02, 0.0])


@pytest.mark.unit
def test_dates_absent_from_one_series_are_dropped():
    asset = {"2024-01-02": 100.0, "2024-01-03": 110.0, "2024-01-04": 121.0}
    bench = {"2024-01-02": 50.0, "2024-01-04": 51.0}
    dates, ar, _ = aligned_returns(asset, bench)
    assert dates == ["2024-01-04"]
    # 100 -> 121 across the dropped date, not 110 -> 121.
    assert ar == pytest.approx([0.21])


@pytest.mark.unit
def test_more_than_five_dropped_dates_raises():
    """Beyond a handful of halts, the two series disagree about the trading
    calendar, and every return spanning a gap is fabricated."""
    asset = {f"2024-01-{d:02d}": 100.0 for d in range(1, 21)}
    bench = {f"2024-01-{d:02d}": 50.0 for d in range(1, 21) if d % 3}
    with pytest.raises(ValueError, match="trading calendar"):
        aligned_returns(asset, bench)


@pytest.mark.unit
def test_fewer_than_two_common_dates_raises():
    with pytest.raises(ValueError, match="at least two"):
        aligned_returns({"2024-01-02": 1.0}, {"2024-01-02": 1.0})


@pytest.mark.unit
def test_a_zero_prior_close_raises_rather_than_dividing():
    asset = {"2024-01-02": 0.0, "2024-01-03": 10.0}
    bench = {"2024-01-02": 50.0, "2024-01-03": 51.0}
    with pytest.raises(ValueError, match="non-positive"):
        aligned_returns(asset, bench)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_moves_alignment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.moves'`

- [ ] **Step 3: Write the implementation**

```python
# src/portfolio_analysis/moves.py
"""Move detection (spec §5). Pure statistics - no I/O, no network, no database.

    r_t      = adj_close_t / adj_close_{t-1} - 1
    beta     = OLS slope of r on r_benchmark over [t-250, t-1]
    AR_t     = r_t - beta * r_benchmark_t
    sigma_60 = stdev(AR) over [t-60, t-1]
    z_t      = AR_t / sigma_60

A day is flagged when |z_t| >= 2.5.

Both estimation windows end at t-1. This is a statistical requirement, not a
point-in-time one: including day t in the volatility estimate that day t must
clear makes the threshold move with the thing it is measuring.

The historical abnormal returns used for sigma are computed with the SAME beta
estimated at t, rather than each with its own contemporaneous beta. This is the
constant-beta convention of a standard event study, and it avoids a recursive
estimation whose result would depend on where the series happened to start.
"""
from __future__ import annotations

import statistics as st
from collections.abc import Mapping

#: Halts and one-off listing gaps are tolerated; a systematic calendar
#: disagreement is not, because every return spanning a gap is fabricated.
_MAX_DROPPED_DATES = 5


def aligned_returns(
    asset: Mapping[str, float], benchmark: Mapping[str, float]
) -> tuple[list[str], list[float], list[float]]:
    """Simple returns over consecutive dates present in both series.

    Returns (dates, asset_returns, benchmark_returns), all the same length and
    one shorter than the common date set. `dates[i]` is the date the return
    was realized on.
    """
    common = sorted(set(asset) & set(benchmark))
    dropped = (len(asset) - len(common)) + (len(benchmark) - len(common))
    if dropped > _MAX_DROPPED_DATES:
        raise ValueError(
            f"{dropped} dates are missing from one series or the other; the two "
            "series disagree about the trading calendar, so every return "
            "spanning a gap would be fabricated"
        )
    if len(common) < 2:
        raise ValueError(f"need at least two common dates, got {len(common)}")

    dates: list[str] = []
    asset_returns: list[float] = []
    benchmark_returns: list[float] = []
    for previous, current in zip(common, common[1:], strict=True):
        for series, name in ((asset, "asset"), (benchmark, "benchmark")):
            if series[previous] <= 0:
                raise ValueError(
                    f"non-positive {name} price {series[previous]!r} on {previous}"
                )
        dates.append(current)
        asset_returns.append(asset[current] / asset[previous] - 1)
        benchmark_returns.append(benchmark[current] / benchmark[previous] - 1)
    return dates, asset_returns, benchmark_returns
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_moves_alignment.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/moves.py tests/test_moves_alignment.py
git commit -m "feat(portfolio-analysis): aligned return series

Returns span consecutive dates present in BOTH series; a date missing from
one would otherwise produce a two-day return labelled as one day."
```

---

## Task 8: OLS beta

**Files:**
- Modify: `src/portfolio_analysis/moves.py` (append `ols_beta`)
- Test: `tests/test_moves_beta.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_moves_beta.py
import pytest

from portfolio_analysis.moves import ols_beta


@pytest.mark.unit
def test_a_perfect_two_times_series_has_beta_two():
    bench = [0.01, -0.01, 0.02, -0.02, 0.015]
    asset = [2 * b for b in bench]
    assert ols_beta(asset, bench) == pytest.approx(2.0)


@pytest.mark.unit
def test_beta_is_unaffected_by_a_constant_offset():
    """An intercept is alpha, not beta. Adding a constant drift to the asset
    must not change the slope."""
    bench = [0.01, -0.01, 0.02, -0.02, 0.015]
    asset = [2 * b + 0.005 for b in bench]
    assert ols_beta(asset, bench) == pytest.approx(2.0)


@pytest.mark.unit
def test_an_uncorrelated_series_has_beta_near_zero():
    bench = [0.01, -0.01, 0.01, -0.01]
    asset = [0.02, 0.02, -0.02, -0.02]
    assert ols_beta(asset, bench) == pytest.approx(0.0)


@pytest.mark.unit
def test_a_flat_benchmark_raises_rather_than_dividing_by_zero():
    with pytest.raises(ValueError, match="zero variance"):
        ols_beta([0.01, 0.02, 0.03], [0.01, 0.01, 0.01])


@pytest.mark.unit
def test_mismatched_lengths_raise():
    with pytest.raises(ValueError, match="same length"):
        ols_beta([0.01, 0.02], [0.01])


@pytest.mark.unit
def test_fewer_than_two_observations_raise():
    with pytest.raises(ValueError, match="at least two"):
        ols_beta([0.01], [0.01])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_moves_beta.py -v`
Expected: FAIL with `ImportError: cannot import name 'ols_beta'`

- [ ] **Step 3: Append the implementation to `moves.py`**

Widen the `collections.abc` import at the top of the file — `ols_beta` takes
sequences, not mappings:

```python
from collections.abc import Mapping, Sequence
```

Then append:

```python
def ols_beta(asset: Sequence[float], benchmark: Sequence[float]) -> float:
    """Slope of the OLS regression of asset returns on benchmark returns.

    cov / var, which is the slope of the least-squares line. The intercept is
    alpha and is deliberately not returned: this project measures how much of a
    move the market explains, not whether the name outperforms.
    """
    if len(asset) != len(benchmark):
        raise ValueError(
            f"series must be the same length, got {len(asset)} and {len(benchmark)}"
        )
    if len(asset) < 2:
        raise ValueError(f"need at least two observations, got {len(asset)}")

    mean_asset = st.fmean(asset)
    mean_benchmark = st.fmean(benchmark)
    covariance = st.fmean(
        (a - mean_asset) * (b - mean_benchmark)
        for a, b in zip(asset, benchmark, strict=True)
    )
    variance = st.fmean((b - mean_benchmark) ** 2 for b in benchmark)
    if variance == 0:
        raise ValueError("benchmark has zero variance over the window; beta is undefined")
    return covariance / variance
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_moves_beta.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/portfolio_analysis/moves.py tests/test_moves_beta.py
git commit -m "feat(portfolio-analysis): OLS beta over a trailing window"
```

---

## Task 9: Abnormal return, sigma, z, and flagging

**Files:**
- Modify: `src/portfolio_analysis/moves.py` (append `Move`, `Coverage`, `compute_moves`)
- Test: `tests/test_moves_compute.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_moves_compute.py
from datetime import date, timedelta

import pytest

from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import compute_moves

PARAMS = MoveParams(beta_window=250, sigma_window=60, z_threshold=2.5)


def _series(n=252, spike_at=None, spike=0.20):
    """Build a synthetic pair whose true beta is 2.0 with alternating +/-0.1%
    idiosyncratic noise, so sigma is nonzero and every AR except the spike is
    well inside the threshold."""
    asset, bench = {}, {}
    asset_px, bench_px = 100.0, 100.0
    start = date(2020, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(n + 1)]
    asset[dates[0]], bench[dates[0]] = asset_px, bench_px
    for i in range(1, n + 1):
        br = 0.01 if i % 2 else -0.01
        noise = 0.001 if i % 2 else -0.001
        ar = 2 * br + noise
        if spike_at is not None and i == spike_at:
            ar = 2 * br + spike
        bench_px *= 1 + br
        asset_px *= 1 + ar
        bench[dates[i]], asset[dates[i]] = bench_px, asset_px
    return asset, bench, dates


@pytest.mark.unit
def test_the_warm_up_period_is_not_evaluated():
    """With 252 returns and a 250-day beta window, only the final two days
    are evaluable."""
    asset, bench, _ = _series(n=252)
    _, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert coverage.evaluated_days == 2


@pytest.mark.unit
def test_a_clean_series_flags_nothing():
    asset, bench, _ = _series(n=252)
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert moves == []
    assert coverage.flagged_days == 0


@pytest.mark.unit
def test_an_injected_spike_is_flagged_with_the_right_sign():
    asset, bench, dates = _series(n=252, spike_at=251, spike=0.20)
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert coverage.flagged_days == 1
    move = moves[0]
    assert move.date == dates[251]
    assert move.ticker == "TEST"
    assert move.benchmark == "BENCH"
    assert move.beta == pytest.approx(2.0, abs=0.05)
    assert move.abnormal_return == pytest.approx(0.20, abs=0.01)
    assert move.z > 2.5


@pytest.mark.unit
def test_a_downward_spike_is_flagged_too():
    asset, bench, _ = _series(n=252, spike_at=251, spike=-0.20)
    moves, _ = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert len(moves) == 1
    assert moves[0].z < -2.5


@pytest.mark.unit
def test_abnormal_return_equals_return_minus_beta_times_benchmark():
    asset, bench, _ = _series(n=252, spike_at=251, spike=0.20)
    moves, _ = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    move = moves[0]
    assert move.abnormal_return == pytest.approx(
        move.ret - move.beta * move.benchmark_return
    )


@pytest.mark.unit
def test_z_equals_abnormal_return_over_sigma():
    asset, bench, _ = _series(n=252, spike_at=251, spike=0.20)
    move = compute_moves("TEST", "BENCH", asset, bench, PARAMS)[0][0]
    assert move.z == pytest.approx(move.abnormal_return / move.sigma_60)


@pytest.mark.unit
def test_coverage_reports_both_ranges():
    asset, bench, dates = _series(n=252)
    _, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert coverage.price_series == (dates[0], dates[-1])
    # dates[0] is the base for the first return, so returns start at dates[1]
    # and the first evaluable day is 250 returns later.
    assert coverage.evaluated == (dates[251], dates[252])


@pytest.mark.unit
def test_too_short_a_series_yields_no_moves_rather_than_raising():
    """A newly listed ticker has no evaluable days yet. That is a coverage
    fact to report, not an error."""
    asset, bench, _ = _series(n=10)
    moves, coverage = compute_moves("TEST", "BENCH", asset, bench, PARAMS)
    assert moves == []
    assert coverage.evaluated_days == 0
    assert coverage.evaluated is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_moves_compute.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_moves'`

- [ ] **Step 3: Append the implementation to `moves.py`**

Add these imports to the top of the file, merging with the existing import block:

```python
from dataclasses import dataclass

from portfolio_analysis.config import MoveParams
from portfolio_analysis.naming import safe_ticker_component
```

`config.py` does not import `moves.py`, so this does not create a cycle.

Then append:

```python
@dataclass(frozen=True)
class Move:
    """One flagged day, fully decomposed (spec §7 `move` block)."""

    ticker: str
    date: str
    ret: float
    benchmark: str
    benchmark_return: float
    beta: float
    abnormal_return: float
    sigma_60: float
    z: float

    def as_row(self) -> dict[str, object]:
        """The shape Store.upsert_moves expects."""
        return {
            "ticker": self.ticker,
            "date": self.date,
            "ret": self.ret,
            "benchmark": self.benchmark,
            "benchmark_return": self.benchmark_return,
            "beta": self.beta,
            "abnormal_return": self.abnormal_return,
            "sigma_60": self.sigma_60,
            "z": self.z,
        }


@dataclass(frozen=True)
class Coverage:
    """What was and was not evaluated (spec §5, §7)."""

    price_series: tuple[str, str] | None
    evaluated: tuple[str, str] | None
    evaluated_days: int
    flagged_days: int


def compute_moves(
    ticker: str,
    benchmark_name: str,
    asset: Mapping[str, float],
    benchmark: Mapping[str, float],
    params: MoveParams,
) -> tuple[list[Move], Coverage]:
    """Flagged days and the coverage of the evaluation.

    A series too short to fill the beta window yields no moves and a coverage
    report saying so. A newly listed ticker is a coverage fact, not an error.
    """
    symbol = safe_ticker_component(ticker)
    common = sorted(set(asset) & set(benchmark))
    price_series = (common[0], common[-1]) if common else None

    if len(common) < 2:
        return [], Coverage(price_series, None, 0, 0)

    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)

    first = params.beta_window
    if first >= len(dates):
        return [], Coverage(price_series, None, 0, 0)

    moves: list[Move] = []
    for index in range(first, len(dates)):
        window = slice(index - params.beta_window, index)
        beta = ols_beta(asset_returns[window], benchmark_returns[window])

        # Constant beta across the sigma window, per the module docstring.
        abnormal = [
            asset_returns[j] - beta * benchmark_returns[j]
            for j in range(index - params.sigma_window, index + 1)
        ]
        sigma = st.stdev(abnormal[:-1])
        if sigma == 0:
            raise ValueError(
                f"{symbol}: zero abnormal-return volatility ending {dates[index - 1]}; "
                "z is undefined"
            )
        z = abnormal[-1] / sigma
        if abs(z) >= params.z_threshold:
            moves.append(Move(
                ticker=symbol,
                date=dates[index],
                ret=asset_returns[index],
                benchmark=benchmark_name,
                benchmark_return=benchmark_returns[index],
                beta=beta,
                abnormal_return=abnormal[-1],
                sigma_60=sigma,
                z=z,
            ))

    return moves, Coverage(
        price_series=price_series,
        evaluated=(dates[first], dates[-1]),
        evaluated_days=len(dates) - first,
        flagged_days=len(moves),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_moves_compute.py -v`
Expected: `8 passed`

- [ ] **Step 5: Run the whole suite, the linter, and the type checker**

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```

Expected: all pass with no findings.

- [ ] **Step 6: Commit**

```bash
git add src/portfolio_analysis/moves.py tests/test_moves_compute.py
git commit -m "feat(portfolio-analysis): abnormal return, trailing sigma, z, flagging

Constant beta across the sigma window, per standard event-study convention:
per-day contemporaneous betas would make the result depend on where the
series happened to start."
```

---

## Task 10: `detect-moves` command and the JSON artifact

**Files:**
- Create: `src/portfolio_analysis/artifacts.py`
- Modify: `src/portfolio_analysis/cli.py` (add the `detect-moves` subcommand)
- Test: `tests/test_artifacts.py`
- Test: `tests/test_cli_detect.py`

The artifact is the contract with Plan 2. It carries the parameters and the coverage, not just the moves, so a consumer can tell a quiet five years from a five-year window that was never evaluated.

- [ ] **Step 1: Write the failing test for the artifact**

```python
# tests/test_artifacts.py
import json

import pytest

from portfolio_analysis.artifacts import MovesArtifact, read_moves, write_moves
from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import Coverage, Move

MOVE = Move(
    ticker="META", date="2024-04-25", ret=-0.105613, benchmark="QQQ",
    benchmark_return=-0.004830, beta=1.490, abnormal_return=-0.098419,
    sigma_60=0.026083, z=-3.77,
)
COVERAGE = Coverage(
    price_series=("2020-09-14", "2026-09-11"),
    evaluated=("2021-09-13", "2026-09-11"),
    evaluated_days=1255,
    flagged_days=30,
)
PARAMS = MoveParams(beta_window=250, sigma_window=60, z_threshold=2.5)


@pytest.mark.unit
def test_round_trips_through_disk(tmp_path):
    path = write_moves(tmp_path, MovesArtifact("META", "QQQ", PARAMS, COVERAGE, [MOVE]))
    assert path.name == "META.json"
    loaded = read_moves(path)
    assert loaded.ticker == "META"
    assert loaded.coverage.flagged_days == 30
    assert loaded.moves[0].date == "2024-04-25"
    assert loaded.moves[0].z == pytest.approx(-3.77)


@pytest.mark.unit
def test_the_written_json_records_the_parameters(tmp_path):
    """A move list without its threshold is not reproducible."""
    path = write_moves(tmp_path, MovesArtifact("META", "QQQ", PARAMS, COVERAGE, [MOVE]))
    raw = json.loads(path.read_text())
    assert raw["params"] == {
        "beta_window": 250, "sigma_window": 60, "z_threshold": 2.5
    }
    assert raw["coverage"]["evaluated_days"] == 1255


@pytest.mark.unit
def test_the_filename_is_a_sanitized_ticker(tmp_path):
    with pytest.raises(ValueError):
        write_moves(tmp_path, MovesArtifact("../etc", "QQQ", PARAMS, COVERAGE, []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_artifacts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_analysis.artifacts'`

- [ ] **Step 3: Write `artifacts.py`**

```python
# src/portfolio_analysis/artifacts.py
"""The data/moves/<TICKER>.json artifact (spec §12).

This file is the contract between `detect-moves` and Plan 2's
`collect-events`. It carries the parameters and the coverage alongside the
moves, because a move list without its threshold is not reproducible, and a
consumer otherwise cannot tell a quiet five years from a five-year window that
was never evaluated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import Coverage, Move
from portfolio_analysis.naming import safe_ticker_component

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MovesArtifact:
    ticker: str
    benchmark: str
    params: MoveParams
    coverage: Coverage
    moves: list[Move]


def _coverage_dict(coverage: Coverage) -> dict[str, object]:
    return {
        "price_series": list(coverage.price_series) if coverage.price_series else None,
        "evaluated": list(coverage.evaluated) if coverage.evaluated else None,
        "evaluated_days": coverage.evaluated_days,
        "flagged_days": coverage.flagged_days,
    }


def write_moves(directory: Path, artifact: MovesArtifact) -> Path:
    symbol = safe_ticker_component(artifact.ticker)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ticker": symbol,
        "benchmark": artifact.benchmark,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": {
            "beta_window": artifact.params.beta_window,
            "sigma_window": artifact.params.sigma_window,
            "z_threshold": artifact.params.z_threshold,
        },
        "coverage": _coverage_dict(artifact.coverage),
        "moves": [
            {
                "date": m.date,
                "ret": m.ret,
                "benchmark_return": m.benchmark_return,
                "beta": m.beta,
                "abnormal_return": m.abnormal_return,
                "sigma_60": m.sigma_60,
                "z": m.z,
            }
            for m in artifact.moves
        ],
    }
    path = directory / f"{symbol}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def read_moves(path: Path) -> MovesArtifact:
    raw = json.loads(Path(path).read_text())
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version {raw['schema_version']}, expected {SCHEMA_VERSION}"
        )
    cov = raw["coverage"]
    ticker, benchmark = raw["ticker"], raw["benchmark"]
    return MovesArtifact(
        ticker=ticker,
        benchmark=benchmark,
        params=MoveParams(
            beta_window=int(raw["params"]["beta_window"]),
            sigma_window=int(raw["params"]["sigma_window"]),
            z_threshold=float(raw["params"]["z_threshold"]),
        ),
        coverage=Coverage(
            price_series=tuple(cov["price_series"]) if cov["price_series"] else None,  # type: ignore[arg-type]
            evaluated=tuple(cov["evaluated"]) if cov["evaluated"] else None,  # type: ignore[arg-type]
            evaluated_days=int(cov["evaluated_days"]),
            flagged_days=int(cov["flagged_days"]),
        ),
        moves=[
            Move(
                ticker=ticker,
                date=m["date"],
                ret=float(m["ret"]),
                benchmark=benchmark,
                benchmark_return=float(m["benchmark_return"]),
                beta=float(m["beta"]),
                abnormal_return=float(m["abnormal_return"]),
                sigma_60=float(m["sigma_60"]),
                z=float(m["z"]),
            )
            for m in raw["moves"]
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_artifacts.py -v`
Expected: `3 passed`

- [ ] **Step 5: Write the failing test for the command**

```python
# tests/test_cli_detect.py
from datetime import date, timedelta

import pytest

from portfolio_analysis import cli
from portfolio_analysis.artifacts import read_moves
from portfolio_analysis.store import Store


def _bars(ticker, series):
    return [{
        "ticker": ticker, "date": d, "open": p, "high": p, "low": p,
        "close": p, "adj_close": p, "volume": 1.0, "source": "test",
    } for d, p in series.items()]


def _seed(db, n=252, spike_at=251, spike=0.20):
    asset, bench = {}, {}
    ap, bp = 100.0, 100.0
    # Strictly increasing ISO dates, one per day. Calendar realism does not
    # matter here - aligned_returns only requires that the order is total.
    start = date(2020, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(n + 1)]
    asset[dates[0]], bench[dates[0]] = ap, bp
    for i in range(1, n + 1):
        br = 0.01 if i % 2 else -0.01
        ar = 2 * br + (0.001 if i % 2 else -0.001)
        if i == spike_at:
            ar = 2 * br + spike
        bp *= 1 + br
        ap *= 1 + ar
        bench[dates[i]], asset[dates[i]] = bp, ap
    store = Store.open(db)
    try:
        store.upsert_price_bars(_bars("META", asset))
        store.upsert_price_bars(_bars("QQQ", bench))
    finally:
        store.close()
    return dates


@pytest.mark.unit
def test_detect_writes_the_store_and_the_artifact(tmp_path):
    db = tmp_path / "t.sqlite"
    out = tmp_path / "moves"
    dates = _seed(db)

    assert cli.main([
        "detect-moves", "META", "--db", str(db), "--moves-dir", str(out)
    ]) == 0

    artifact = read_moves(out / "META.json")
    assert artifact.coverage.flagged_days == 1
    assert artifact.moves[0].date == dates[251]
    assert artifact.moves[0].z > 2.5

    store = Store.open(db)
    try:
        rows = store.moves("META")
        assert len(rows) == 1
        assert rows[0]["date"] == dates[251]
        assert rows[0]["benchmark"] == "QQQ"
    finally:
        store.close()


@pytest.mark.unit
def test_rerunning_detect_does_not_duplicate_moves(tmp_path):
    db = tmp_path / "t.sqlite"
    out = tmp_path / "moves"
    _seed(db)
    args = ["detect-moves", "META", "--db", str(db), "--moves-dir", str(out)]
    assert cli.main(args) == 0
    assert cli.main(args) == 0
    store = Store.open(db)
    try:
        assert len(store.moves("META")) == 1
    finally:
        store.close()


@pytest.mark.unit
def test_detect_fails_clearly_when_the_benchmark_was_never_ingested(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    store = Store.open(db)
    try:
        store.upsert_price_bars(_bars("META", {"2024-04-24": 1.0, "2024-04-25": 1.1}))
    finally:
        store.close()

    assert cli.main([
        "detect-moves", "META", "--db", str(db), "--moves-dir", str(tmp_path / "m")
    ]) == 1
    assert "QQQ" in capsys.readouterr().err
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_detect.py -v`
Expected: FAIL with `argument command: invalid choice: 'detect-moves'`

- [ ] **Step 7: Add `detect-moves` to `cli.py`**

Add these imports to the existing import block in `cli.py`:

```python
from pathlib import Path

from portfolio_analysis import moves as moves_module
from portfolio_analysis.artifacts import MovesArtifact, write_moves
```

Add this function above `main`:

```python
def _detect_moves(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(
            f"{args.ticker!r} is not in the portfolio; add it to config/portfolio.yaml",
            file=sys.stderr,
        )
        return 2

    moves_dir = Path(args.moves_dir) if args.moves_dir else portfolio.path("moves")
    store = Store.open(args.db or portfolio.path("db"))
    try:
        benchmark_series = store.adjusted_series(portfolio.benchmark)
        if not benchmark_series:
            print(
                f"no prices for benchmark {portfolio.benchmark}; "
                "run `ingest-prices` first - beta cannot be computed without it",
                file=sys.stderr,
            )
            return 1

        for symbol in symbols:
            asset_series = store.adjusted_series(symbol)
            if not asset_series:
                print(f"no prices for {symbol}; run `ingest-prices` first", file=sys.stderr)
                return 1

            found, coverage = moves_module.compute_moves(
                symbol,
                portfolio.benchmark,
                asset_series,
                benchmark_series,
                portfolio.move_params,
            )
            store.upsert_moves([m.as_row() for m in found])
            path = write_moves(
                moves_dir,
                MovesArtifact(
                    ticker=symbol,
                    benchmark=portfolio.benchmark,
                    params=portfolio.move_params,
                    coverage=coverage,
                    moves=found,
                ),
            )
            evaluated = (
                f"{coverage.evaluated[0]} .. {coverage.evaluated[1]}"
                if coverage.evaluated else "none (series shorter than the beta window)"
            )
            print(
                f"{symbol}: {coverage.flagged_days} flagged of "
                f"{coverage.evaluated_days} evaluated ({evaluated}) -> {path}"
            )
    finally:
        store.close()
    return 0
```

Register it inside `main`, after the `ingest` block:

```python
    detect = sub.add_parser("detect-moves", help="flag days whose abnormal return is large")
    detect.add_argument(
        "ticker", nargs="?", default=None,
        help="ticker, company name, or alias; omit for the whole portfolio",
    )
    detect.add_argument("--db", default=None, help="override the configured database")
    detect.add_argument(
        "--moves-dir", default=None, help="override the configured artifact directory"
    )
    detect.set_defaults(func=_detect_moves)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_detect.py -v`
Expected: `3 passed`

- [ ] **Step 9: Run the whole suite, the linter, and the type checker**

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```

Expected: all pass with no findings.

- [ ] **Step 10: Commit**

```bash
git add src/portfolio_analysis/artifacts.py src/portfolio_analysis/cli.py tests/test_artifacts.py tests/test_cli_detect.py
git commit -m "feat(portfolio-analysis): detect-moves command and moves artifact

The artifact carries params and coverage alongside the moves: a move list
without its threshold is not reproducible, and a consumer otherwise cannot
tell a quiet five years from one that was never evaluated."
```

---

## Task 11: Live end-to-end verification against the measured anchors

**Files:**
- Test: `tests/test_live_meta.py`
- Modify: `README.md` (create)

This is the task that decides whether Plan 1 actually worked.
Every number asserted here was measured against live Yahoo on 2026-09-13.
The test is marked `network` and excluded from the default run, because a test that fails when Yahoo is down is not a test of this code.

- [ ] **Step 1: Write the network test**

```python
# tests/test_live_meta.py
"""End-to-end verification against live Yahoo data.

Every expected value here was measured on 2026-09-13 and is recorded in
docs/plans/2026-09-13-portfolio-analysis-foundation.md. Marked `network` and
excluded from the default run: a test that fails when Yahoo is down is not a
test of this code.

Tolerances are loose on counts and ranges because the series grows by one bar
per trading day, and tight on the 2024-04-25 statistics because those are
computed from a fixed historical window that does not move.
"""
import pytest

from portfolio_analysis import prices
from portfolio_analysis.config import load_portfolio
from portfolio_analysis.moves import compute_moves

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def computed():
    portfolio = load_portfolio()
    series = {
        symbol: {
            bar["date"]: bar["adj_close"]
            for bar in prices.fetch_yahoo(symbol, years=portfolio.price_years)
        }
        for symbol in ("META", portfolio.benchmark)
    }
    moves, coverage = compute_moves(
        "META", portfolio.benchmark, series["META"],
        series[portfolio.benchmark], portfolio.move_params,
    )
    return moves, coverage


def test_six_fetched_years_yield_about_five_evaluable_ones(computed):
    _, coverage = computed
    # Measured 2026-09-13: 1506 bars in, 1255 evaluable out.
    assert coverage.evaluated_days == pytest.approx(1255, abs=30)


def test_the_flagged_rate_is_in_the_expected_band(computed):
    """Measured 30 of 1255, or 2.39%. Under a normal distribution |z| >= 2.5
    is 1.24%; return distributions have fatter tails, so 2-3% is expected."""
    moves, coverage = computed
    rate = coverage.flagged_days / coverage.evaluated_days
    assert 0.015 <= rate <= 0.035, f"flagged {coverage.flagged_days} ({rate:.2%})"


def test_meta_2024_04_25_is_flagged_with_the_measured_statistics(computed):
    moves, _ = computed
    by_date = {m.date: m for m in moves}
    assert "2024-04-25" in by_date, f"flagged dates: {sorted(by_date)}"
    move = by_date["2024-04-25"]
    assert move.ret == pytest.approx(-0.105613, abs=1e-5)
    assert move.benchmark_return == pytest.approx(-0.004830, abs=1e-5)
    assert move.beta == pytest.approx(1.490, abs=0.01)
    assert move.abnormal_return == pytest.approx(-0.098419, abs=1e-4)
    assert move.sigma_60 == pytest.approx(0.026083, abs=1e-4)
    assert move.z == pytest.approx(-3.77, abs=0.02)


def test_beta_correction_is_not_cosmetic(computed):
    """Naive subtraction gives -10.08%; beta-adjusted gives -9.84%. If beta
    were 1.0 these would coincide and the whole rule would be decoration."""
    move = {m.date: m for m in computed[0]}["2024-04-25"]
    naive = move.ret - move.benchmark_return
    assert abs(naive - move.abnormal_return) > 0.002


def test_meta_2022_02_03_is_the_largest_flagged_move(computed):
    """The -26.4% earnings crash. Measured z -16.30."""
    moves, _ = computed
    largest = min(moves, key=lambda m: m.z)
    assert largest.date == "2022-02-03"
    assert largest.z == pytest.approx(-16.30, abs=0.05)
```

- [ ] **Step 2: Run the network test**

```bash
.venv/bin/pytest tests/test_live_meta.py -v -m network
```

Expected: `5 passed`.
If `test_meta_2024_04_25_is_flagged_with_the_measured_statistics` fails on the statistics rather than on membership, the bug is in `moves.py` and not in the data — the historical window it reads does not move.

- [ ] **Step 3: Run the real pipeline end to end**

```bash
.venv/bin/portfolio-analysis ingest-prices
.venv/bin/portfolio-analysis detect-moves
```

Expected output, approximately:

```
META: 1506 bar(s) upserted, 2020-09-14 .. 2026-09-11
QQQ: 1506 bar(s) upserted, 2020-09-14 .. 2026-09-11
META: 30 flagged of 1255 evaluated (2021-09-13 .. 2026-09-11) -> .../data/moves/META.json
```

- [ ] **Step 4: Confirm the artifact contains the anchor date**

```bash
python3 -c "
import json; a=json.load(open('data/moves/META.json'))
m={x['date']: x for x in a['moves']}
print('flagged:', a['coverage']['flagged_days'], 'of', a['coverage']['evaluated_days'])
print('2024-04-25 present:', '2024-04-25' in m)
print({k: round(v,6) for k,v in m['2024-04-25'].items() if k!='date'})
"
```

Expected: `2024-04-25 present: True` with `z` near `-3.77`.

- [ ] **Step 5: Write `README.md`**

````markdown
# portfolio-analysis

Retrospective attribution of large single-day equity moves to dated, cited events.

**This project explains the past. It makes no predictive claim and produces no trading signal.**

Design spec: [`docs/specs/2026-09-13-portfolio-analysis-design.md`](docs/specs/2026-09-13-portfolio-analysis-design.md)

## Setup

Requires [`uv`](https://docs.astral.sh/uv/).
Do not use `pip` — it is broken on this machine's Homebrew Python 3.14 (`pyexpat` symbol error).

```bash
uv venv -p 3.13
uv pip install -e ".[dev]"
.venv/bin/pytest
```

Network-dependent tests are excluded by default. Run them with `.venv/bin/pytest -m network`.

## Usage

```bash
.venv/bin/portfolio-analysis ingest-prices
.venv/bin/portfolio-analysis detect-moves
```

## What this foundation does

Six years of adjusted daily prices are fetched for every configured ticker and for the benchmark.
Six, not five: a 250-day beta window consumes the first trading year, so five fetched years would yield only four evaluable ones.

For each evaluable day, beta comes from a trailing 250-day OLS regression of the ticker's returns on the benchmark's, both windows ending the day before.
The abnormal return is the return less beta times the benchmark return, and a day is flagged when that abnormal return exceeds 2.5 times its own trailing 60-day standard deviation.

One fixed threshold would be wrong. A 3% day is noise for NVDA and a five-alarm event for ServiceNow, so a single cutoff over-samples the volatile names and misses real news on the quiet ones. The rule here self-calibrates per ticker and per era.

On META over the five years ending 2026-09-11 this flags 30 of 1255 days, or 2.39%.

## Limitations

Coverage of the *events* behind these moves is uneven, and later plans surface that per move rather than hiding it.
Consensus estimates are not available from any free source, so "beat" and "miss" can never be verified facts here — only claims reported in sources.
See spec §16 for the full register.
````

- [ ] **Step 6: Commit**

```bash
git add README.md tests/test_live_meta.py
git commit -m "test(portfolio-analysis): live verification against measured anchors

META 2024-04-25: ret -10.5613%, QQQ -0.4830%, beta 1.490, AR -9.8419%,
sigma60 2.6083%, z -3.77. Measured 2026-09-13, 30 of 1255 days flagged."
```

---

## Definition of done

- [ ] `.venv/bin/pytest` passes with no network access
- [ ] `.venv/bin/pytest -m network` passes against live Yahoo
- [ ] `.venv/bin/ruff check .` and `.venv/bin/mypy` report nothing
- [ ] `data/moves/META.json` exists, reports ~30 flagged of ~1255 evaluated, and contains `2024-04-25` with `z` near `-3.77`
- [ ] `README.md` states the no-prediction scope and the coverage limitation

## Handoff to Plan 2

Plan 2 (`collect-events`) consumes `data/moves/<TICKER>.json` through `artifacts.read_moves`.
It needs from this plan: the flagged dates, and the full trading calendar to convert a `[-2, +1]` **trading**-day window into calendar dates.
The calendar is `sorted(Store.adjusted_series(benchmark))` — the benchmark's date set, which is the right source because it is present for every date in the evaluated range by construction.
