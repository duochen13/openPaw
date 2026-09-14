# portfolio-analysis — design spec

Retrospective attribution of large single-day equity moves to dated, cited events.

**This project explains the past. It makes no predictive claim and produces no trading signal.**
Its sibling `stock-trading-bot` is the mirror image: that repo must never see the future, this one exists to use hindsight.

Date: 2026-09-13.
Status: approved, pending implementation plans.

---

## 1. Purpose

Given a list of tickers, find the days whose price move was too large to be market beta, and for each one assemble the events that were publicly known in a `[-2, +1]` trading-day window.
Then produce a structured, cited explanation and a self-contained HTML chart with the explanations attached to the price line.

The deliverable per flagged day is one record: the move decomposed against a benchmark, a set of code-verified facts, a set of claims reported in sources, a prose reason, and a confidence.

## 2. Non-goals

- **No Robinhood integration.** No brokerage API, no credentials, no position import. The universe is a hand-written list.
- **No portfolio weighting, P&L, or attribution of returns to holdings.**
- **No backtest and no forward-looking signal.** Nothing here is evidence that a future move is predictable.
- **No point-in-time machinery.** Deliberate. See §11.
- **No analyst upgrades/downgrades.** No free source carries dated historical ratings changes. This is the single capability that motivated the original interest in Benzinga, and it is absent.
- **No Reddit in v1.** See §4.3.

## 3. Locked decisions

| Decision | Choice | Why |
|---|---|---|
| Repo boundary | Standalone `portfolio-analysis/`, copying proven code from `stock-trading-bot` | Retrospective code sharing a process with point-in-time code is how a future-leak gets written. That repo's entire value is that leaks are hard to write by accident. |
| Portfolio input | `config/portfolio.yaml`, hand-written | The portfolio-pull step is the least interesting part of the project and the most fragile if automated. |
| v1 universe | META only | One name end-to-end beats five names half-done. The config shape supports more on day one. |
| Move rule | Vol-normalized abnormal return | A 3% day is noise for NVDA and a five-alarm event for NOW. One fixed threshold over-samples volatile names and misses real news on quiet ones. |
| LLM | Meta Muse Spark 1.3, standard tier | Asked for by name; strict JSON Schema and a 1M context window make it a genuine fit. Full 5-year META run costs $1-2. |
| Visualization | Self-contained HTML, one file per ticker | No server, no build, no runtime deps. Matches the sibling repo's zero-dependency instinct. |
| Language / tooling | Python 3.13, `uv`, ruff, mypy strict, pytest | Identical to `stock-trading-bot`. |

## 4. Data sources

All probed on 2026-09-13. Reachability and response shape verified, not assumed.

### 4.1 Verified working

| Source | Endpoint | Cost | Coverage |
|---|---|---|---|
| Prices | Yahoo chart v8, `period1`/`period2` epoch window | free | Daily OHLCV + `adjclose`. Confirmed for META. **Six years are fetched, not five** — see §5. |
| Filings | SEC EDGAR submissions + full-text | free | Full 5y, authoritative, dated. Client exists in sibling repo. |
| Earnings dates | Alpha Vantage `EARNINGS` | free | Full history of `fiscalDateEnding` + `reportedDate`. Confirmed on the demo key. |
| News | Alpha Vantage `NEWS_SENTIMENT` | free, 25 req/day | **2020-01 onward - measured.** Volume is the limit, not depth. See §4.2. |
| Macro calendar | FRED releases | free, needs key | FOMC / CPI / PCE release dates. |
| Forum discussion | HN Algolia search | free | Full history. Already proven working in the sibling repo. |

**Stooq is not usable.** It sits behind a JavaScript proof-of-work anti-bot challenge.
This was established in `stock-trading-bot` and is not re-litigated here; Yahoo is the price path.

### 4.2 The coverage limitation, measured

An earlier draft of this spec said news coverage began around 2022, and that years four and five would be thin to empty.
**That was wrong. It came from documentation and aggregator write-ups rather than from measurement.**

Probed on 2026-09-14 with a real key: the earliest META article Alpha Vantage returns is `20200121T221400`.
Coverage begins in **January 2020**, before the evaluated window starts at 2021-09-13, so all 30 flagged moves sit inside covered territory.

**The real limitation is volume, not depth.**
Measured document counts for a `[-2, +1]` window:

| Window | Articles |
|---|---|
| 2024-04-25, the -10.6% move | 7 |
| 2022-02-03, the -26.4% crash | 14 |

Roughly 7-14 documents per move, not the 30-40 an attribution of this kind would ideally rest on.
The highly relevant items are present - *"Meta earnings: Stock decline could wipe out about $200B"* scores relevance 1.00 on the anchor date - but a seven-document evidence base caps how much confidence any explanation can honestly carry, and the rendered card must show that count rather than bury it.

The free tier is 25 requests per day, which shapes the architecture (§6.1).

The consequence is not hidden. Every move record carries a `coverage` block, and every HTML page prints per-move document counts.
A move showing `documents: 2` is visibly weak rather than silently weak.

Two operational facts, both learned by probing rather than reading:

- Alpha Vantage returns intermittent `502 Bad Gateway` - twelve across three requests. Retry with backoff is required, not optional.
- A 111KB response truncated under `urllib` with `IncompleteRead`. The `requests` library handles it, which is what `http.py` uses.

Optional accelerant: Alpha Vantage's paid tier (~$50/month) raises the limit to 75 requests/minute.
Because every response is cached to disk permanently, buying one month, backfilling, and cancelling is a coherent strategy.

### 4.3 Excluded: Reddit

The sibling repo already built a Reddit collector and abandoned it.
It drove a headless browser, and Reddit broke it once by gating `old.reddit.com` behind a login.
The repo's own conclusion was recorded as "No Reddit."

The ask here is strictly harder: *historical* Reddit going back years.
Pushshift is no longer available to non-moderators, and Reddit's live search will not reach a 2024 date with meaningful recall.
A "Reddit discussions: 214" count for a 2024 move requires a bulk archive (Arctic Shift or academic dumps), which is a separate ingest path for the noisiest signal in the pipeline.

HackerNews via the free Algolia API is used instead: real history, no auth, already proven.
Reddit becomes a v2 `EventSource` adapter. Until then the card shows no Reddit row rather than a misleading one.

### 4.4 Consensus estimates: partially available, and less useful than it sounds

`stock-trading-bot` established that no free source provides consensus estimates timestamped before disclosure with a matching accounting definition.

That finding needs qualifying here.
Alpha Vantage's `EARNINGS` response does carry `estimatedEPS`, `surprise` and `surprisePercentage`, measured on 2026-09-14 across 58 quarters back to 2012.
The sibling project's objection - that the vintage is unverifiable - still holds, but it binds less tightly on a project built to use hindsight.
So EPS surprise is available, with an unknown vintage that must be recorded alongside it.

Two limits remain:

1. It is **EPS, not revenue**. "Revenue beat" still cannot be a verified fact, which is exactly the line the original card crossed.
2. **It routinely fails to explain the move.** On 2024-04-24 META beat EPS by +9.03% and fell 10.6% the next session. On 2022-02-02 it missed by -4.18% and fell 26.4%. A beat and a miss, both followed by large declines.

The second point is the more important one, and it is the strongest available argument for the split in §8: a fact can be perfectly verifiable and still carry no explanatory weight.
Anything that reads a beat as bullish gets 2024-04-25 exactly backwards.

## 5. Move detection

For each ticker and each trading day `t`:

```
r_t      = adj_close_t / adj_close_{t-1} - 1
rb_t     = benchmark return, same day          (benchmark: QQQ)
beta     = OLS slope of r on rb over [t-250, t-1]
AR_t     = r_t - beta * rb_t
sigma_60 = stdev(AR) over [t-60, t-1]
z_t      = AR_t / sigma_60
```

A day is **flagged** when `|z_t| >= 2.5`.

Both the estimation windows end at `t-1`.
This is not a point-in-time requirement — the project has no such requirement — but a statistical one: including day `t` in the volatility estimate that day `t` must clear makes the threshold move with the thing it is measuring.

Expected yield: roughly 25-40 flagged days per ticker over five years.
Under a normal distribution `|z| >= 2.5` is 1.24% of days (about 16 of 1260); return distributions have fatter tails, so 2-3% is the realistic range.

`beta`, `sigma_60`, and `z` are all persisted per move so the chart can display the bar each day had to clear.

Days with fewer than 250 prior observations are not evaluated.

**This is why price ingestion fetches six years rather than five.**
A 250-day beta window consumes the first trading year of the series, so `range=5y` would yield only four years of evaluable days.
The Yahoo chart API has no `6y` range value, so ingestion uses explicit `period1`/`period2` epoch bounds set six years back.
The warm-up year is recorded in the coverage block, not silently dropped.

Conveniently, the discarded warm-up year is roughly the same year that has no news coverage (§4.2), so the two limitations overlap rather than compound.

The benchmark is configured in `config/portfolio.yaml`, defaulting to `QQQ` to match the sibling repo's watchlist.

## 6. Event collection

For each flagged move, collect documents and facts in the window `[t-2, t+1]` **trading** days.
Calendar days are wrong here: a Friday move needs the prior Wednesday, not the prior Wednesday-by-calendar that may be a holiday.

### 6.1 Why detection must precede collection

This ordering is load-bearing, not tidiness.

Fetching five years of META news wholesale is thousands of Alpha Vantage requests against a 25/day quota — infeasible.
Fetching only the four-day window around each flagged move is about 30 requests per ticker, which completes in a day and a half on the free tier.

There is no `--jobs` flag.
The bottleneck is a daily quota, and parallelism cannot beat a quota.
Collection is serial behind a rate limiter that persists its own request-count ledger across runs, so an interrupted backfill resumes without burning the day's budget twice.

### 6.2 Source interface

```python
class EventSource(Protocol):
    name: str
    def fetch(self, ticker: str, start: date, end: date) -> list[Document] | list[VerifiedFact]: ...
```

Adapters: `edgar`, `earnings`, `news`, `macro`, `hn`.
Each writes raw responses to a content-addressed disk cache before parsing, so a parser change never costs a re-fetch and never costs quota.

## 7. Evidence bundle

One JSON artifact per flagged move. This is the sole input to the LLM.

```json
{
  "ticker": "META",
  "date": "2024-04-25",
  "bundle_sha256": "<canonical hash, document order normalized>",
  "move": {
    "return": -0.1056,
    "benchmark_return": -0.0055,
    "benchmark": "QQQ",
    "beta": 1.18,
    "abnormal_return": -0.0991,
    "sigma_60": 0.0214,
    "z": -4.63
  },
  "verified": {
    "earnings_reported": {
      "value": true,
      "source": "alphavantage:EARNINGS",
      "detail": "fiscalDateEnding 2024-03-31, reportedDate 2024-04-24"
    },
    "filings": [
      {"form": "8-K", "accession": "0001326801-24-000044", "filed": "2024-04-24", "url": "..."}
    ],
    "macro_release": {"value": false, "source": "fred:releases"},
    "index_move": {"QQQ": -0.0055}
  },
  "documents": [
    {
      "doc_id": "av:3f9c...",
      "source": "alphavantage_news",
      "published_at": "2024-04-25T11:02:00Z",
      "title": "...",
      "url": "...",
      "summary": "...",
      "relevance": 0.82
    }
  ],
  "coverage": {
    "documents": 37,
    "sources": ["alphavantage_news", "edgar", "hackernews"],
    "window": ["2024-04-23", "2024-04-26"],
    "news_coverage_known_thin": false,
    "documents_by_source": {"alphavantage_news": 34, "edgar": 1, "hackernews": 2}
  }
}
```

`bundle_sha256` is computed over a canonical serialization with documents sorted by `doc_id`, so an upstream reordering does not invalidate the LLM cache.

`news_coverage_known_thin` is `true` when either condition holds: the move date precedes the news source's configured coverage start (`news_coverage_start`, default `2022-03-01`), or fewer than five documents were collected.
It is computed in code, and when `true` the rendered card carries a coverage warning above the reason.

## 8. The verified / reported split

This is the most important constraint in the design.

An LLM handed "META fell 10.56% on 2024-04-25, here are 37 articles" will always produce a fluent, confident reason — including on days when nothing happened.
Post-hoc narrative fitting is the characteristic failure of this entire genre of tool, and it produces something that feels like insight and is not.

The structural defense is that **facts and narrative never share a checkbox**, and the LLM can only write one of them.

**Verified** — computed in Python from a dated source. The LLM never sets these.

- Earnings reported (Alpha Vantage `reportedDate`)
- Filings on or adjacent to the date (EDGAR, with accession number)
- Whether the date was an FOMC / CPI / PCE release day (FRED)
- Benchmark move, beta, abnormal return, z (Yahoo + §5)

**Reported** — a claim asserted in sources, carried with citations and a support count. Written by the LLM, grounded in `documents`.

- "Revenue beat expectations" — 31/37 documents
- "2024 capex guidance raised" — 28/37 documents
- "Guidance seen as not justifying the spend" — 19/37 documents

The original sketch had `✓ Revenue beat` as a checkmark.
It cannot be one, because verifying it requires consensus estimates that no free source provides (§4.4).
It survives as a *reported* claim with a citation, which is what it actually is.

The rendered card shows the two groups in visually distinct blocks.

## 9. Attribution

### 9.1 Provider

Meta Muse Spark, `muse-spark-1.3`, standard tier.

- OpenAI-compatible endpoint: `https://api.meta.ai/v1`
- Context window: 1,048,576 tokens — a 37-document bundle fits with room to spare
- Structured output constrains token generation at decode time via `response_format: {type: "json_schema", json_schema: {...}}`
- `strict: true` is used, which requires: root is a plain object, no `allOf`/`oneOf` anywhere, `additionalProperties: false` on every object, and `required` listing every key in `properties`
- Pricing: $1.25/M input, $4.25/M output, $0.15/M cached input

**Historical note that matters for anyone reading this later:** Meta's Llama API was sunset on 2026-07-06.
Muse Spark is the successor and the current first-party Meta API. Do not write a Llama API adapter.

The `muse-spark-1.3-contributor` tier costs $0.10/$0.20 — 92% less — but Meta trains on submitted prompts, retention is unpublished, and the terms bar FINRA-covered data.
Given that a full META run costs $1-2 on the standard tier, the discount is not worth the ambiguity.
Contributor is reachable only behind an explicit `--contributor` flag.

The client is written against the OpenAI-compatible surface, so an Anthropic or OpenAI adapter is a small addition. No abstraction is built for that now.

### 9.2 Output schema

```json
{
  "no_identifiable_catalyst": false,
  "primary_reason": "Higher-than-expected AI/capex guidance raised near-term free-cash-flow concerns.",
  "secondary_reason": "Revenue guidance was not seen as justifying the increase in investment.",
  "reported_claims": [
    {
      "claim": "2024 capex guidance raised",
      "direction": "negative",
      "supporting_doc_ids": ["av:3f9c...", "av:81aa..."]
    }
  ],
  "confidence": 0.91,
  "confidence_rationale": "Scheduled earnings catalyst, 28 of 37 documents converge on capex guidance."
}
```

`direction` is an enum over `"positive" | "negative" | "neutral"`, describing the claim's sign relative to the share price rather than the business.
Strict mode permits `enum` below the root, though not at it.

Nullable fields are typed `["string", "null"]` rather than omitted, because strict mode requires `required` to list every key.

**Abstention is first-class.** `no_identifiable_catalyst: true` with null reasons is a valid, explicitly valued answer, and the prompt says so.
A system that cannot say "I don't know" cannot be trusted when it says "I know."

Any `supporting_doc_ids` value not present in the bundle's `documents` is a hard validation failure, not a warning.
This makes fabricated citations impossible to persist.

### 9.3 Caching

Cache key is `sha256` over the canonical JSON of:

```
{prompt_version, model_id, schema_version, provider, temperature, bundle_sha256}
```

Stored at `data/llm-cache/<key>.json`.
Re-running `explain` after a prompt edit re-costs only what changed; re-running after no change costs nothing.

## 10. The controls layer

Two cheap diagnostics, run on every batch, printed at the top of every HTML page.
Without these the confidence column is decoration.

**Placebo.** For each flagged move, sample a matched quiet day (`|z| < 0.5`) for the same ticker within ±60 days.
Run the identical collection, prompt, and schema.
Correct behavior is a high rate of `no_identifiable_catalyst: true`.
If the model returns 0.9 confidence on quiet days, the scores carry no information.

**Sign-flip.** Take a real move's real evidence bundle and negate `return`, `abnormal_return`, and `z`, leaving `benchmark_return` and every document untouched.
If the model confidently explains +10% using the same 37 documents it used to explain -10%, that is narrative fit rather than attribution.
Because the mutated numbers change `bundle_sha256`, a sign-flip run cannot collide with its real counterpart in the LLM cache — no special-casing is needed.

Both produce one headline number each:

```
placebo abstention rate:  78%   (31/40 quiet days correctly abstained)
narrative-fit rate:       12%   (5/40 sign-flips confidently explained)
```

Control runs are stored in the same table as real runs with a `kind` discriminator (`real` / `placebo` / `signflip`), never mixed into the rendered attributions.
Cost: roughly doubles LLM calls, to about $3 for a five-year META run.

## 11. Storage

Plain SQLite at `data/prices.sqlite`. Tables:

- `prices(ticker, date, open, high, low, close, adj_close, volume, source, fetched_at)` — PK `(ticker, date)`
- `moves(ticker, date, return, benchmark_return, beta, abnormal_return, sigma_60, z)` — PK `(ticker, date)`
- `documents(doc_id, source, published_at, title, url, summary, relevance, body_sha256, fetched_at)` — PK `doc_id`
- `move_documents(ticker, date, doc_id)` — join table
- `verified_facts(ticker, date, fact_key, value_json, source, detail)`
- `attributions(ticker, date, kind, model_id, prompt_version, schema_version, bundle_sha256, payload_json, created_at)`
- `runs(run_id, started_at, config_sha256, model_id, prompt_version, cache_hits, cache_misses)`

**Two deliberate divergences from `stock-trading-bot`, both justified:**

1. **No `known_at` / `observed_at` / `valid_from` columns and no `PointInTimeView`.**
   That machinery exists to prevent a forward-looking model from seeing the future.
   This project's entire purpose is to look backward with full hindsight, so the machinery would be dead weight that implies a guarantee the project does not make.
   Rows are still append-only and carry `fetched_at`, so a run is reproducible and a restatement is visible.

2. **Yahoo `adj_close` is used directly, rather than storing raw prices and reconstructing split adjustment from dated corporate actions.**
   The sibling repo reconstructs because a vendor's adjusted series is retroactively revised, which corrupts a point-in-time backtest.
   Here a single consistent present-day adjusted series is exactly what a five-year retrospective chart should show.
   Raw OHLC is stored alongside anyway, so reconstruction remains possible without a re-fetch.

## 12. CLI and artifacts

Five commands, five artifacts. Each stage reads the previous artifact and writes its own.

| Command | Reads | Writes |
|---|---|---|
| `ingest-prices` | `config/portfolio.yaml` | `data/prices.sqlite` |
| `detect-moves` | `prices.sqlite` | `data/moves/META.json` |
| `collect-events` | `moves/META.json` | `data/events/META/2024-04-25.json` |
| `explain` | `events/…` | `data/reasons/META/2024-04-25.json` |
| `render` | `reasons/…` + `prices.sqlite` | `out/META.html` |

A failed LLM call never re-fetches prices.
An exhausted news quota never invalidates the moves already detected.
Re-running `explain` with a new prompt costs nothing for unchanged evidence.

This is the decomposition: each stage is independently runnable, testable, resumable, and inspectable as a file on disk.

## 13. Rendering

One self-contained HTML file per ticker. Inline SVG, inline CSS, vanilla JS, no external requests.

- Five-year adjusted close line
- QQQ overlaid, normalized to the same start, so a market-wide drawdown is visually distinguishable from a company-specific one
- A marker at each flagged move, sized by `|z|`, colored by sign
- Clicking a marker opens the attribution card: move decomposition, verified block, reported block with citation links, prose reason, confidence
- Header panel: coverage per year, placebo abstention rate, narrative-fit rate

Chart construction follows the `dataviz` skill, which is to be loaded before any chart code is written.

## 14. Testing

- Recorded-fixture unit tests for every source parser. No test touches the network.
- Beta / AR / sigma / z computed against a hand-worked fixture with known values.
- A schema-conformance test that walks the JSON Schema and asserts the Muse strict subset: root is an object, no `allOf`/`oneOf`, `additionalProperties: false` everywhere, `required` covers every property. This catches a `400` before it costs an API call.
- Cache-key tests: bumping `prompt_version` changes the key; reordering `documents` does not change `bundle_sha256`.
- Abstention path test: a bundle with zero documents must yield `no_identifiable_catalyst: true`.
- Citation validation test: a fabricated `doc_id` in `supporting_doc_ids` must raise, not warn.
- Window test: the collection window is exactly `[-2, +1]` **trading** days across a holiday boundary.
- Self-containment test: rendered HTML has no external `src` attribute and no `<link rel="stylesheet">`, so it renders identically with networking disabled. Outbound `<a href>` links to source articles and EDGAR filings are expected and explicitly allowed — they are click-throughs, not render dependencies.
- Rate-limiter test: the persisted request ledger survives a simulated interrupt and does not double-spend the daily quota.

## 15. Costs

| Item | Cost |
|---|---|
| Prices, EDGAR, earnings dates, FRED, HN | $0 |
| Alpha Vantage news, free tier | $0, ~1.5 days of drip per ticker |
| Alpha Vantage news, optional accelerant | ~$50 for one month, then cancel |
| Muse Spark, ~40 moves, 5y META | ~$1-2 |
| Muse Spark, with controls | ~$3 |

Every network response is cached content-addressed on disk, so re-runs are free.

## 16. Known limitations

These belong in the README, in the sibling repo's register.

1. **News volume is thin - 7 to 14 documents per move**, measured. Depth is not the problem: coverage reaches back to January 2020, before the evaluated window begins. But a seven-document evidence base limits how much confidence any explanation can carry. Surfaced per-move, never hidden.
2. **Consensus estimates are unavailable**, so "beat" and "miss" are reported claims rather than verified facts.
3. **No analyst ratings changes.** No free source carries dated history.
4. **No Reddit.** Historical recall is not achievable without a bulk archive.
5. **Attribution is not causal identification.** A dated event in the window that the market discussed is not proof it caused the move. The controls layer measures how badly the model over-claims; it does not make the claims causal.
6. **Alpha Vantage relevance and sentiment scores are vendor-computed and opaque.** They are used for ordering documents, never as evidence.
7. **Single-name v1.** Nothing here is a cross-sectional finding.

## 17. Decomposition into implementation plans

| Plan | Scope | Done when |
|---|---|---|
| 1. Foundation | Scaffold, config, store, Yahoo price ingest, move detection, `ingest-prices` + `detect-moves` | `data/moves/META.json` lists flagged days with beta/sigma/z, and 2024-04-25 is among them |
| 2. Event collection | `EventSource` protocol, five adapters, persistent rate limiter, bundle assembly, `collect-events` | The 2024-04-25 bundle contains the earnings fact, the 8-K accession, and N news documents |
| 3. Attribution + controls | Muse Spark client, strict schema, citation validation, disk cache, placebo + sign-flip, `explain` | A reason record for 2024-04-25 with valid citations, plus both control rates printed |
| 4. Render | Self-contained HTML, chart, cards, coverage header, `render` | `out/META.html` opens from the filesystem with markers and clickable cards |

Each plan gets its own document under `docs/plans/`.
