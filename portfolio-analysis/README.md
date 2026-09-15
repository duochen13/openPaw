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
PYTHONPATH=src .venv/bin/python -m portfolio_analysis.cli ingest-prices
PYTHONPATH=src .venv/bin/python -m portfolio_analysis.cli detect-moves
```

A `portfolio-analysis` console script is declared, but **prefer the module form above**.
`uv` writes its editable-install file
`.venv/lib/python3.13/site-packages/_editable_impl_portfolio_analysis.pth`
with the macOS `UF_HIDDEN` flag set, and CPython's `site.py` skips hidden `.pth` files.
The install is therefore present and silently unimportable, and the console script fails with `ModuleNotFoundError: No module named 'portfolio_analysis'`.
The same note appears in the sibling project's README for the same reason.
`pythonpath = ["src"]` in `pyproject.toml` is what keeps the test suite independent of this.

## What this foundation does

Six years of adjusted daily prices are fetched for every configured ticker and for the benchmark.
Six, not five: a 250-day beta window consumes the first trading year, so five fetched years would yield only four evaluable ones.

For each evaluable day, beta comes from a trailing 250-day OLS regression of the ticker's returns on the benchmark's, both windows ending the day before.
The abnormal return is the return less beta times the benchmark return, and a day is flagged when that abnormal return exceeds 2.5 times its own trailing 60-day standard deviation.

One fixed threshold would be wrong. A 3% day is noise for NVDA and a five-alarm event for ServiceNow, so a single cutoff over-samples the volatile names and misses real news on the quiet ones. The rule here self-calibrates per ticker and per era.

On META over the five years ending 2026-09-11 this flags 30 of 1255 days, or 2.39%.

## Limitations

Coverage of the *events* behind these moves is uneven, and later plans surface that per move rather than hiding it.
Alpha Vantage provides vendor-stored EPS estimates and surprises, with unknown consensus vintage.
These are dated facts with an explicit caveat, not proof of what caused a move.
Revenue beats and misses remain reported claims.
See spec §16 for the full register.


## Event collection

Plan 2 adds `collect-events`, consuming the move artifacts and benchmark sessions:

```bash
# Load the existing Alpha Vantage key without putting it in a command argument.
set -a
. ~/.config/portfolio-analysis/env
set +a
PYTHONPATH=src .venv/bin/python -m portfolio_analysis.cli collect-events META --date 2024-04-25
PYTHONPATH=src .venv/bin/python -m portfolio_analysis.cli collect-events META
```

The sources are SEC filings (including submission archives), Alpha Vantage
quarterly earnings and news, HackerNews company-name/alias searches, and the
checked-in FOMC/CPI/PCE calendar. `SEC_USER_AGENT` can supply a descriptive SEC
request identity. No LLM is called by this stage.

Each bundle lives at `data/events/<TICKER>/<DATE>.json` and includes source
status, document counts, macro coverage, and a canonical SHA-256. The `verified`
field is a list of sourced facts, preserving multiple filings/releases in one
window. It is separate from `documents`; no generated reasons exist yet.

- Windows include all calendar time between the start and end of the `[-2,+1]`
  trading-session window, interpreted in New York time. Incomplete session
  windows are deferred without fetching news.
- Without `ALPHAVANTAGE_API_KEY`, keyless sources still run and bundles explicitly
  mark earnings/news as missing. Adding the key invalidates those partial bundles.
- Completed bundles are reused. `--rebuild` reparses cached responses; it does not
  force every provider to refetch. Changes to move values, source configuration,
  or macro calendar invalidate the bundle automatically.
- HTTP responses are stored by content hash before source parsing. Mutable EDGAR
  and earnings responses expire after 24 hours; historical news/HN windows are
  cached indefinitely. Persisted request identities and manifests contain no API keys.
- Quota is reserved before every attempt, including retries. A provider quota
  refusal persists until the next UTC date. Quota exhaustion prints completed
  and remaining counts and exits 0; rerun after the provider resets. Failed
  requests are not cached as empty evidence.
- HackerNews can report approximate hit counts. Returned pages are collected,
  but that source is marked `approximate_hit_count`; it never claims exhaustive
  historical coverage. Search includes old company aliases and is not restricted
  to earnings stories.

The macro calendar covers 2021-01-01 through 2026-09-13, with authoritative
source URLs per release. It includes actual shutdown-related rescheduling in
2025 and a PCE data-only update. Extend its verified coverage as time advances;
outside coverage is unknown, not “no macro event.” The calendar is offline at
runtime and needs no FRED key.

`--db`, `--moves-dir`, `--events-dir`, `--cache-dir`, and `--macro-calendar` support
isolated runs. The response cache is local to this machine and uses POSIX locks.

Validation: `.venv/bin/pytest` runs offline; `.venv/bin/pytest -m network -rs`
checks live anchors. Alpha Vantage live checks skip when its key is absent or
its quota is exhausted. See `docs/CODEX-HANDOFF.md` for the latest measured run
and the remaining live verification.

## Generate a stock event chart

From the `openPaw` repository root:

```bash
./portfolio-analysis/run chart META --keyless
```

This produces **`portfolio-analysis/out/META.html`**. Open it in a browser.
It uses stored prices if available, detects unusual moves, collects SEC/HN/macro
context, and renders the chart. `--keyless` deliberately omits Alpha Vantage;
remove it after loading your API key to include earnings and news when quota
is available. No paid model or attribution API is called.

The chart includes:

- Stock versus benchmark, indexed to 100, or adjusted share price in USD.
- Up/down markers, a selectable move list, and period/direction filters.
- Dated events and linked source headlines; post-move events are labeled.
- Explicit missing/partial evidence, keyboard/touch controls, light/dark themes.
- A selected date in the URL fragment, and SVG/data downloads.

To regenerate entirely from saved data:

```bash
./portfolio-analysis/run render META
```

To build one offline dashboard for every configured stock:

```bash
./portfolio-analysis/run render
./portfolio-analysis/run dashboard
```

Open `portfolio-analysis/out/index.html` and use its stock selector to switch
between the individual evidence charts.

To update prices too:

```bash
./portfolio-analysis/run chart META --refresh-prices --keyless
```

Other stocks must first be added to `config/portfolio.yaml` with their symbol,
company name, CIK, and aliases. Replace `META` with that configured symbol.
The chart displays historical context; it does not claim the nearby events
caused the move. Model attribution and reliability controls remain separate,
unimplemented work.
