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
Consensus estimates are not available from any free source, so "beat" and "miss" can never be verified facts here — only claims reported in sources.
See spec §16 for the full register.
