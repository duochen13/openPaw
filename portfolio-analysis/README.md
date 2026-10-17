# portfolio-analysis

Retrospective attribution of large single-day equity moves to dated, cited events.

**This project explains the past. It makes no predictive claim and produces no trading signal.**

Design spec: [`docs/specs/2026-09-13-portfolio-analysis-design.md`](docs/specs/2026-09-13-portfolio-analysis-design.md)

## Setup

Run setup and test commands from the `portfolio-analysis/` directory. Commands
beginning with `./portfolio-analysis/run` below run from the repository root.

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

Tickers without an operating-company EDGAR identity — e.g. leveraged
single-stock ETFs such as METU (2x META) and GGLL (2x GOOGL) — are first-class
universe members with `cik` omitted. They get prices, beta/alpha, move flags
and charts like any stock, but the EDGAR fundamentals fetch and the SEC
filing event source are skipped for them (their charts render those sections
as n/a, the same treatment indices already received).

SPCX (SpaceX, listed June 2026) is the opposite case (issue #152): it has an
EDGAR identity (CIK 1181412), so fundamentals and filing events work as for
any operating company, but its price history is far shorter than the
250-session beta window. Move detection evaluates such a series on all
available history once it clears 40 sessions — beta from every return since
listing, sigma from whatever part of the 60-session window exists — and the
dashboard card carries a `history < 250d` badge until the window fills.
Below 40 sessions a series still reports coverage with zero evaluated days
rather than a fabricated z-score. No history is backfilled or synthesized.

GFS (GlobalFoundries) and IONQ (IonQ) are ordinary CIK-bearing members
(added in #157). One asymmetry: GFS is a foreign private issuer whose EDGAR
companyfacts exist only under the `ifrs-full` taxonomy
(`DilutedEarningsLossPerShare`), while the fundamentals fetch reads
`us-gaap` concepts — so `fetch-fundamentals GFS` reports no
`EarningsPerShareDiluted` in USD/shares and GFS renders its P/E and KPI
sections as n/a until IFRS taxonomy support is added. Prices, move
detection, and SEC filing event collection do not depend on the `us-gaap`
taxonomy and work for GFS normally.

MRNA (Moderna, added in #161) is an ordinary CIK-bearing member
(CIK 1682852) mapped to the XBI biotech industry benchmark. Unlike GFS it
is a US domestic filer reporting in `us-gaap`, so EDGAR fundamentals and
filing event collection work for it as for any other operating company.

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

### CPI release prints (issue #153)

The calendar says *when* a release lands; `config/cpi_prints.yaml` says *what
it printed*. It is a checked-in sibling of the calendar (auto-loaded by
`MacroSource` when present, like `fomc_decisions.yaml`) holding, per CPI
release: `release_date`, `reference_period`, `release_time_et` (08:30), the
BLS release URL, and four metrics — `headline_mom`, `headline_yoy`,
`core_mom`, `core_yoy` — each with `actual`, `consensus`, `prior`, and
`revision` in percent (m/m seasonally adjusted, y/y unadjusted). The backfill
covers the 23 releases from 2024-11-13 through 2026-10-14; October 2025 was
never published (federal shutdown), so the 2025-12-18 release chains its
`prior` to September 2025 and its 1-month changes are null (BLS published
only a 2-month change).

Data discipline: `actual` values are the as-printed Table A percent changes
from each release in the BLS news-release archive, cross-checked against
index levels from the BLS public API (`CUUR0000SA0` / `CUSR0000SA0`).
`consensus` is stored only where a survey median was verified by hand for
that release — currently only 2026-10-14 — and is null elsewhere; it is never
estimated. `revision` is null throughout (the NSA series is never revised;
SA values change only at the annual seasonal-factor recalculation, which this
file does not restate). Regenerate or extend the file with
`scripts/collect_cpi.py` (see its docstring for provenance rules).

Consumers of the prints layer:

- **Verified facts.** `MacroSource.collect` emits a `macro_print` fact per
  CPI release alongside the calendar's `macro_release` date fact, and the
  event-date catalog turns it into a chart annotation such as
  “CPI print: headline 3.7% y/y vs 3.6% consensus” on every ticker's chart.
- **Move classification.** When a flagged move's bundle contains a
  `macro_print` fact dated the move day, `build_bundle` adds a
  `macro_classification`: `macro-driven` when the largest absolute surprise
  (|actual − consensus| across the four metrics) is at least 0.1pp and no
  ticker-specific dated event (earnings, SEC filing) shares the day;
  `mixed` when both are present; absent when the release carried no
  material surprise or no sourced consensus. The tag complements the beta
  decomposition — it never replaces it.
- **Event dashboard.** CPI rows carry the print into the event-impact
  dashboard: the context block quotes actual vs consensus vs prior and the
  per-metric surprise replaces the former “not tracked” placeholder.

### PPI release prints (issue #155)

Issue #155 generalizes the prints layer from CPI-only to series-keyed:
one loader/classifier (`events/macro_prints.py`), one data file per
series. `config/ppi_prints.yaml` is the PPI sibling — same schema with
`series: "PPI"` and the PPI metric keys `final_demand_mom`,
`final_demand_yoy`, `core_mom`, `core_yoy` (final demand; core = final
demand less foods and energy), each `{actual, consensus, prior,
revision}` in percent (m/m seasonally adjusted, y/y unadjusted). The
backfill covers the 22 releases from 2024-11-14 through 2026-09-10.
PPI is not a `macro_calendar.yaml` series (that contract stays
FOMC/CPI/PCE); PPI release dates live in the prints file itself, and
`MacroSource` surfaces them as a `PPI` catalog key, so the event
dashboard lists PPI alongside CPI.

Provenance differs from CPI in three ways worth knowing:

- **Where the numbers sit in the release.** Final demand is Table A's
  headline; core (less foods & energy) is read from its Table 1 row —
  the 12-month unadjusted change plus the last of the five seasonally
  adjusted 1-month changes.
- **Revisions are real.** PPI indexes are revised for four months after
  publication, so the BLS API's current-vintage levels legitimately
  disagree with older as-printed values (the collector's API
  cross-check — `WPUFD4` / `WPSFD4`, `WPUFD49104` / `WPSFD49104` —
  warns past 0.15pp and the archive prints stand). The file keeps the
  as-printed vintage throughout and `revision` stays null.
- **Four pages were unreachable.** The 2026-01-14, 2026-03-18,
  2026-04-14, and 2026-06-11 archive pages returned HTTP 403 to the
  collector's fetcher; those releases were transcribed from the
  following release's tables (first revised vintage) with core y/y
  computed from the API index levels, and each carries a `notes` entry
  in the file saying so. The October 2025 shutdown gap applies to PPI
  too: that release was never published, there is no row for it, the
  September 2025 release was delayed to 2025-11-25, and priors chain
  across the gap.

`consensus` is null for every PPI release: no PPI survey median has
been hand-verified yet, and the discipline from #153 is unchanged —
never estimated. Until one is sourced, PPI prints attach as facts,
chart markers (“PPI print: final demand 5.4% y/y”), and dashboard
context, but they produce no surprises and no `macro_classification`.
Regenerate or extend the file with `scripts/collect_ppi.py`.

**Reading CPI and PPI jointly.** PPI is the upstream half of the
inflation pair — pipeline pressure that typically prints a day after
CPI and leads it. A CPI-day `macro-driven` tag reads differently when
the prior day's PPI also surprised hot (broad pipeline pressure behind
the consumer print) than when PPI was quiet (a consumer-side or
idiosyncratic print). If CPI and PPI ever land on the same day and
both classify, the bundle keeps the larger surprise.

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

## Factor and valuation dashboards

The application source, tests, and configuration live under `portfolio-analysis/`.
From the repository root, use the existing launcher:

```bash
./portfolio-analysis/run detect-moves
./portfolio-analysis/run render
./portfolio-analysis/run dashboard
./portfolio-analysis/run factor-dashboard
open portfolio-analysis/out/index.html
```

After upgrading older move artifacts, `detect-moves` regenerates them from stored
prices in the current schema. Alpha and beta use stored price history. To populate
P/E and supported business KPIs, fetch quarterly fundamentals before rendering:

```bash
./portfolio-analysis/run fetch-fundamentals
./portfolio-analysis/run render
```

Factor trajectories (beta/alpha over time) remain available per stock in the
"Beta, R² & alpha over time" section of each chart page.
