# stock-trading-bot

Point-in-time equity research and signal evaluation.

**Reports and paper evaluation only. No brokerage integration, no live execution.**

Design spec: [`../docs/superpowers/specs/2026-09-07-stock-trading-bot-design.md`](../docs/superpowers/specs/2026-09-07-stock-trading-bot-design.md)

## Setup

Requires [`uv`](https://docs.astral.sh/uv/).
Do not use `pip` — it is broken on this machine's Homebrew Python 3.14 (`pyexpat` symbol error).

```bash
uv venv -p 3.13
uv pip install -e ".[dev]"
.venv/bin/pytest
```

## Usage

```bash
PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli ingest NVDA
PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli ingest ServiceNow
```

A ticker, company name, or watchlist alias all resolve.
A `stock-trading` console script also exists, but prefer the module form — see the environment note below.

## What this foundation guarantees

Every fact carries four timestamps: `event_time`, `observed_at`, `known_at`, and `valid_from`.
Reads go through `Store.as_of(t)`, which returns a `PointInTimeView`.

That view cannot surface a row with `known_at > t`, and a null `known_at` is invisible rather than visible — unknown vintage fails closed.
Its connection is opened `mode=ro`, an open flag rather than a revocable setting, with attached databases limited to zero.
Every returned row is re-checked in Python, and a result set whose columns do not match the table's declared columns is refused, so an aliased or `COALESCE`'d `known_at` cannot be mistaken for the real vintage.

**The containment goal is explicitly not "a leak is impossible."**
That is unachievable inside a single process, and claiming it invites false confidence.
A caller who deliberately constructs a projection to defeat the check can still do so.
The goal is that the *accidental* path disappears: a good-faith developer cannot leak by writing ordinary-looking code.

Tables are append-only.
A restatement is a new row with a later `known_at`, never an overwrite, so revisions cannot be backfilled into past predictions.
Re-fetching data that has not changed does not append — a new row is supposed to mean new information.

Prices are stored raw.
Split adjustment is reconstructed as-of from dated corporate actions, because a vendor's adjusted close series is itself retroactively revised.
Timestamps are canonical fixed-width UTC with microseconds, enforced by SQLite `CHECK` constraints, so lexicographic ordering always equals chronological ordering.

## Data limitations

**Consensus estimates are not available.**
No free source provides consensus that is timestamped before disclosure with a matching accounting definition.
Surprise features emit `unavailable` rather than a proxy, and quarter-over-quarter acceleration is never substituted for a consensus surprise.

**Scraped social engagement counts are as-of-scrape, not as-of-`t`.**
This is a contamination that scraping cannot fix.
Affected columns are flagged and surfaced in every evaluation header.

**The universe is deliberately narrow** (5–15 names).
At that sample size the evaluation harness will usually report *"underpowered to distinguish tier 3 from tier 1"* rather than a verdict.
That is the honest answer, not a failure of the system.

## Costs

Price and EDGAR ingestion are free.
LLM extraction arrives in the next phase and is cached content-addressed, so re-runs cost nothing.

## Reproducibility

Run manifests record the config hash, data vintages consumed, and cache hit rate.
The extraction cache key pins prompt version, model id, schema version, and provider.

## Environment note

`uv` writes the editable-install file
`.venv/lib/python3.13/site-packages/_editable_impl_stock_trading_bot.pth`
with the macOS `UF_HIDDEN` flag set, and CPython's `site.py` skips hidden `.pth` files.
The package is therefore installed and silently unimportable, which presents as `ModuleNotFoundError` immediately after a successful install.

`chflags nohidden` clears it, but `uv` re-applies the flag whenever it rewrites the file, so that is a ritual rather than a fix.
The test suite is immune via `pythonpath = ["src"]` in `pyproject.toml`.
For the CLI, run the module with `PYTHONPATH=src` as shown above.

## Development

```bash
.venv/bin/pytest          # 148 tests
.venv/bin/ruff check .
.venv/bin/mypy            # strict
```

All three must be clean. Network access is mocked in every test; the suite runs offline.
