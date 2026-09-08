# stock-trading-bot — Design Spec

**Date:** 2026-09-07
**Status:** Approved, ready for implementation planning
**Scope:** Thin vertical slice (layers A–D) of an LLM-based equity research and signal-evaluation system.
**Explicitly not authorized:** brokerage integration, live execution, order routing.

---

## 1. Goal

Produce auditable company intelligence for a small watchlist of tickers, and determine whether
LLM-extracted evidence adds measurable predictive value over price/volume baselines.

The second half of that sentence is the hard part and the reason most of this design exists.
A system that generates persuasive financial commentary is easy to build and worthless.
A system that can return "there is no detectable edge here" is the actual deliverable.

Success criteria:

1. Every factual claim in every report traces to a stored record, a verbatim span, and a source URL.
2. The evaluation harness reports minimum detectable effect before it reports any point estimate.
3. Point-in-time integrity is enforced structurally, not by reviewer vigilance.
4. Predicted returns and probabilities render as `unavailable` until a tested model exists.

## 2. Non-goals

- Brokerage integration or live execution of any kind.
- Broad-universe cross-sectional ranking. The universe is deliberately 5–15 names.
- Multi-agent debate, bull/bear persona simulation, or any architecture whose output is a
  narrative rather than a measurement. See §14 for why.
- Advanced time-varying models (Kalman, regime switching). Gated behind evidence, see §9.

## 3. Decisions

Six decisions were settled during brainstorming. Each is recorded with its rationale because
the rationale is what makes them revisable later.

### 3.1 Evaluation strategy: hybrid diagnostic + prospective

Historical social data cannot be made point-in-time by scraping.
Reddit and HN return today's score and today's possibly-edited body for a post from 2024.
Only the timestamp is genuinely point-in-time.
Layered on top, the extraction model's knowledge cutoff precedes much of any backtest window,
so extraction over historical text is contaminated by outcome knowledge.

Therefore:

- Model tier 1 (price/volume) gets a real, clean backtest.
- Model tiers 2 and 3 get a retrospective backtest that is **explicitly labeled a contaminated
  upper bound**, used only to prioritize which features are worth collecting.
- Daily point-in-time snapshotting begins at first run, so a clean prospective evaluation accrues.

### 3.2 Universe: narrow and deep, 5–15 names

Chosen over a mid-size universe with full awareness of the cost.
The consequence is accepted and made visible rather than hidden: at this sample size the
evaluation harness will usually conclude "underpowered to distinguish tier 3 from tier 1."
That is the honest answer, and §9 is designed so it is reported clearly instead of being
papered over with a point estimate.

The primary deliverable at this universe size is auditable intelligence.
The predictive-value question receives a calibrated "not yet answerable" rather than a fabricated verdict.

### 3.3 Observation unit: daily panel with event-cluster weighting

Rows are `(ticker, trading_day)`.
Features are decayed rolling aggregates of prior discussion.

Every row carries a `cluster_id`.
Clusters — not rows — are the unit for sample weighting, bootstrap resampling, and purge boundaries.
This is how "3,000 comments about one event are not 3,000 independent observations" becomes
mechanical rather than aspirational.

Effective n is reported alongside raw n everywhere a sample size appears.

### 3.4 Financial data: free stack, consensus features declared unavailable

- Prices: stooq primary, Yahoo fallback. **Raw OHLCV only**, plus a separate corporate-actions table.
- Fundamentals: SEC EDGAR XBRL `companyfacts`. One row per fact per accession.
- Consensus estimates: **not available**.

No free source provides consensus that is timestamped before disclosure with a matching
accounting definition.
Rather than substitute a proxy, surprise features are defined in the schema and emit `unavailable`.

The code must refuse to substitute quarter-over-quarter acceleration for a consensus surprise.
This is enforced by a test, not a comment.

The provider layer stays swappable so a compliant consensus source can drop in later.
Any candidate vendor must be audited for whether it preserves vintages or silently restates history.

### 3.5 First slice: thin vertical walking skeleton through layers A–D

Real price spine, real social ingestion, real LLM extraction on a small corpus, real feature
aggregation, one real report, and a real evaluation harness — each layer deliberately shallow.

Leakage prevention lands in the first commit.
Retrofitting point-in-time discipline onto a working pipeline does not succeed, because leaks
are invisible in results.

### 3.6 LLM access: thin provider interface, CLI default

One interface, multiple implementations.

- `ClaudeCliProvider` shells out to the local `claude` CLI with JSON output.
  Uses existing subscription auth, so no API key exists to leak. This is the default.
- `AnthropicApiProvider` uses the SDK with structured outputs, prompt caching, and the
  Message Batches API for bulk backfill.
- `OpenAICompatibleProvider` targets any OpenAI-compatible endpoint by `base_url` + `model`.

The abstraction is not speculative: the brief requires interchangeable providers, and the
long-document router (see §7.4) requires a second backend.

## 4. Architecture

```
stock-trading-bot/
├── SKILL.md                  # /stock-trading procedure
├── README.md                 # setup, data limitations, costs, reproducibility
├── pyproject.toml            # uv-managed
├── config/
│   ├── watchlist.yaml        # tickers, aliases, ambiguity rules
│   └── run.yaml              # horizons, costs, tiers, providers, thresholds
├── src/stock_trading_bot/
│   ├── store.py              # SQLite + PointInTimeView.as_of(t)
│   ├── ingest/               # prices.py, edgar.py, social.py, live_profile_guard.py
│   ├── extract/              # provider.py, router.py, schemas.py, runner.py, cache.py
│   ├── validate/             # evidence.py, dedup.py, cluster.py, ambiguity.py
│   ├── features/             # market.py, social.py, llm.py, scaler.py
│   ├── model/                # tiers.py, targets.py
│   ├── evaluate/             # splits.py, power.py, costs.py, metrics.py
│   └── report/               # render.py, citation_audit.py
├── tests/
├── data/{raw,db,cache}/
└── reports/
```

Dependency direction is one-way: `ingest → store → features → model → evaluate`.
`report` reads from `store` and `features` only.

Nothing downstream of `store` may import an ingest module.
A test walks the import graph and asserts this.
The purpose is to make it impossible for a report to re-fetch live data mid-render and quietly
embed a value from the future.

### 4.1 Environment constraints (verified 2026-09-07)

- Homebrew Python 3.14's `pip` is broken on this machine (`pyexpat` symbol error).
  Use `uv` (present at `~/.local/bin/uv`, verified working against PyPI).
- stooq, the Yahoo chart API, and HN Algolia are all reachable through the sandbox proxy.
- No market-data or LLM API keys are set in the environment.
- The `claude` CLI is installed and authenticated.
- `gh` requires running outside the sandbox; keyring access is blocked inside it, which
  surfaces misleadingly as an invalid token.

## 5. The point-in-time store

This module holds the system's only real invariants and gets the most test coverage.

### 5.1 Four timestamps, never one

| Column | Meaning |
|---|---|
| `event_time` | When the thing happened in the world. |
| `observed_at` | When we fetched it. |
| `known_at` | When it became usable by a model. |
| `valid_from` | Vintage of the value itself, for restated facts. |

`known_at = observed_at + latency_budget`, where the budget is configured per source and covers
collection, parsing, LLM extraction, and validation.
The budget is deliberately pessimistic.
A signal is never available at `event_time`.

**A null `known_at` means invisible, not visible.**
Unknown vintage fails closed.

### 5.2 The gateway

`store.as_of(t)` returns a `PointInTimeView`.

Feature builders receive only that view.
They have no handle on the underlying connection.
Every query the view issues is wrapped with `known_at <= :t`.

One test asserts the view cannot return a future row.
That single test transitively protects every feature builder written afterward.

This is the central architectural bet: leakage becomes an API problem rather than a vigilance problem.

### 5.3 Append-only

No `UPDATE` on fact tables, ever.
A restatement is a new row with a later `known_at` and the same `event_time`.

This makes "do not backfill revisions into past predictions" automatic.

### 5.4 Prices

Adjusted close is retroactively revised — a split rewrites every prior adjusted value.
Consuming a vendor's adjusted series directly is a real and commonly-missed leak.

The store keeps raw OHLCV plus a corporate-actions table carrying its own `known_at`,
and computes adjustment factors as-of `t`.

### 5.5 The live-profile guard

Vendor "company overview" endpoints (`yfinance Ticker.info`, Alpha Vantage `OVERVIEW`) serve
only present-day values.
Market cap, valuation multiples, the 52-week range, and TTM income all move with today's quote.
Even name, sector, and industry shift when a company renames or is reclassified.
None of it carries a historical vintage.

`ingest/live_profile_guard.py` holds **one shared withhold rule** that every market-data adapter
must route through.
The rule lives at the shared layer specifically so that switching providers cannot reintroduce the leak.

A test asserts no adapter can bypass it.

### 5.6 Staleness

Reject a last bar older than the expected trading session rather than silently modeling on it.

### 5.7 Execution model

Signal available at `t` → fill at the next achievable price after `t`, resolved against a
market calendar.
Intraday → next bar open.
After close, weekend, or holiday → next session open.

Costs are then applied: spread, slippage, commission, and borrow where relevant.

## 6. Ingestion, dedup, and influence capping

### 6.1 Ingestion

Three collectors behind a `MarketDataProvider` / `SocialProvider` interface pair.
The existing `market-research/scripts/collect_hn.py` and `collect_reddit_new.py` are reused,
wrapped to emit the four-timestamp row shape.

`safe_ticker_component()` sanitizes every ticker before it reaches a filesystem path or cache key.

### 6.2 Deduplication, three escalating passes

1. Exact `sha256` of normalized text. Catches re-scrapes.
2. Canonical URL match. Strips tracking params, resolves redirects, collapses crossposts.
3. MinHash/Jaccard at ≥0.85 over shingles. Catches reposts, quoted-article boilerplate, copypasta.

### 6.3 Event clustering

Candidates are generated cheaply — same ticker, within a 3-day window.
They are scored by TF-IDF cosine similarity.
Connected components form clusters, and every document receives a `cluster_id`.

Clusters drive three things from one concept: sample weighting, bootstrap resampling units,
and purge boundaries.

### 6.4 Influence caps

Two caps, correcting two different pathologies.

- **Author cap.** Within a `(ticker, 30-day)` window, an author's total weight is `min(1, cap/n)`
  per post. Default cap 3. One prolific poster cannot become the signal.
- **Cluster cap.** A cluster's total weight is `sqrt(n_docs)`, not `n_docs`.
  A viral thread counts for more than a quiet one, but sublinearly.

### 6.5 Upvotes are attention, never truth

Enforced structurally.
`score` may only feed features in the `attention_*` namespace.
A test asserts that no `credibility_*` or `confidence_*` feature reads it.

Scraped `score` is as-of-scrape rather than as-of-`t`.
Those columns carry `contaminated=True`, and the evaluation harness prints which tiers consumed
contaminated features in every result header.
This cannot be fixed by scraping. It can only be made impossible to forget.

### 6.6 Ticker ambiguity

Per-ticker config carries aliases and a `require_cashtag` flag.

Tickers that are also common English words — `NOW`, `ON`, `ALL`, `KEY`, `IT`, `GOOD` — match
only on `$TICKER` or a full company-name mention, never the bare token.

Tested against a deliberately adversarial fixture.

## 7. LLM extraction

### 7.1 Schema

Three record types, each requiring a verbatim span.

- `Event` — type, subject entity, `event_time`, direction, span, source URL.
- `DemandEvidence` — buyer, product, stage (`evaluating` / `piloting` / `deployed` / `churning`), span.
- `ExpectationChange` — metric, prior belief, new belief, direction, span.

### 7.2 Evidence attribution

Every extracted field must carry a verbatim span that the validator confirms by substring match
against the source document.

Extractions failing that check are **dropped, not repaired**.

The prompt forbids outside knowledge and instructs the model to return empty rather than infer.
This is the standing mitigation for outcome contamination, and it is a mitigation, not a fix.

### 7.3 Caching

Content-addressed disk cache keyed on `(doc_hash, prompt_version, model_id, schema_version, provider)`.

Re-runs are free and the extraction set is byte-reproducible.
The provider is part of the key so a routing-threshold change cannot serve a cross-provider hit.

### 7.4 Long-document routing

Tracked in [issue #6](https://github.com/duochen13/openPaw/issues/6).

Documents over a configurable word threshold (default 350) route to a cheaper long-form reader
backend rather than the default provider.
The router sits behind `LLMProvider`, so callers do not know which backend served a request.

The long-doc backend is reached as a generic OpenAI-compatible endpoint configured by
`base_url` + `model` + key env-var name.
No vendor-specific client is needed.

Evidence-attribution validation applies identically to both backends.
On two consecutive schema failures, escalate to the default provider and record the escalation.

## 8. Features, normalization, and the model ladder

### 8.1 Normalization has two distinct failure modes

These are routinely conflated, and fixing only the first still leaks.

1. **Fold leakage** — fitting a scaler on the full sample.
   Fixed by `FoldScaler`, fit strictly on the training fold, persisted with it, applied unchanged
   to validation and test.
2. **Within-series lookahead** — computing a rolling statistic using the whole history.
   Fixed at construction: every rolling statistic uses an expanding or trailing window bounded by `t`.

"Training-only normalization" is usually read as only the first. Both are required.

### 8.2 The ladder

Ridge throughout, on standardized features, so coefficient magnitudes are comparable.

| Tier | Adds |
|---|---|
| 1 | Returns over multiple lookbacks, realized volatility, trailing volume z-score, market/sector beta. |
| 2 | Capped discussion volume, `attention_*` features, lexicon sentiment. |
| 3 | Event counts by type, demand-stage transitions, net expectation-change direction. |
| 4 | Rolling/EWMA ridge, then Kalman or regime models. |

**Tier 4 is gated.** It is not built unless the tier-3-vs-tier-2 paired difference exceeds
the minimum detectable effect on the primary target at the 5-day horizon.
The gate belongs in the plan, not in someone's judgment at the time.

`alpha` is selected by inner walk-forward *inside* the training fold only.

### 8.3 Targets

All three implemented and configurable:

1. Absolute stock return.
2. Stock return minus benchmark return.
3. Beta-adjusted residual return, with beta estimated only from data available at `t`.

Naming is enforced in code: a field named `excess_vs_qqq` can never be labeled `alpha`.
Benchmark-relative upside does not imply a positive absolute return, and the schema will not
let the two be confused.

Horizons: 1, 5, and 21 trading days all computed. 5d is primary.

### 8.4 Interpretation guards

Before any claim that a feature dominates, the report prints that feature's VIF and correlation
neighborhood.
Correlated factors and coefficient uncertainty are considered before asserting narrative dominance.

## 9. Evaluation

### 9.1 Splits

Chronological walk-forward.

The final ~20% of the timeline is an untouched holdout, opened exactly once, at the end.
A hash of the model config is recorded at holdout time so that "we peeked and retuned" is
detectable afterward.

### 9.2 Purging is two-dimensional

A training label is dropped if:

- its forward-return window overlaps the validation period, **or**
- it belongs to an event cluster that straddles the split boundary.

An embargo gap of `horizon + max_latency` is applied on top.

The second condition is why clusters matter.
A single earnings thread spanning the split leaks across it even when no individual label's
forward window does.

### 9.3 Power is reported before results

Every evaluation prints this header, including on runs that find nothing:

```
n_rows=2,847  n_clusters=178  effective_n≈178
MDE (80% power, α=0.05) on Δ Spearman IC: 0.081
contaminated features in tiers: [2, 3]
```

If the observed Δ IC falls below the MDE, the verdict is
**"underpowered — not distinguishable from zero"**, printed *instead of* the point estimate,
not alongside it.

This is the mechanism that stops a 5–15 name universe from producing a confident-looking
false finding.

### 9.4 Metrics

- Continuous targets: RMSE, Spearman rank IC, ICIR.
- Directional targets: Brier score plus a reliability curve. Calibration, not accuracy.
- Uncertainty: cluster block-bootstrap, always on the **paired difference** between tiers.

Comparing whether two separate confidence intervals overlap is not a test of difference.
It both misses real effects and manufactures fake ones. The paired difference is the test.

**Comparison set**, reported in full on every run: tier 2 vs tier 1, tier 3 vs tier 2,
and tier 3 vs tier 1.

The sequential pairs answer "did this layer earn its cost."
The 3-vs-1 pair answers "is the whole LLM apparatus worth anything over price and volume alone."
All three are reported even when all three are underpowered.

### 9.5 Strategy simulation

Net return, maximum drawdown, turnover, and hit rate, after spread, slippage, commission,
and borrow.

Baselines: zero, buy-and-hold the name, buy-and-hold QQQ, and a simple momentum rule.

A profitable period alone does not demonstrate incremental signal value.
Enforced: the paired comparison must clear MDE before any strategy result renders.

### 9.6 Sensitivity, run automatically

- Window lengths.
- Event-definition variants.
- Source mix: HN-only, Reddit-only, both.
- Leave-one-cluster-out, exposing results that rest on a single viral thread.

## 10. Invocation surface

Shipped as `SKILL.md` (the procedure, matching the `market-research` and `travel-research`
convention) wrapped by `.claude/agents/stock-trading.md`, which runs it in its own context window.

The pipeline pulls thousands of comments and runs many extractions.
Subagent isolation keeps that out of the main session; the caller receives the finished report
and a summary.

```
/stock-trading ServiceNow          # company name
/stock-trading NOW                 # ticker
/stock-trading evaluate            # model comparison + power report
```

### 10.1 Resolution ladder

Stopping at first hit:

1. Exact ticker in `watchlist.yaml`.
2. Alias in `watchlist.yaml`.
3. SEC EDGAR `company_tickers.json` name match.
4. Ambiguous or multiple hits → ask the user with the candidate list.

Bare-word tickers resolve to the company when typed as a bare argument.
The argument position disambiguates what a scraped comment cannot.
This is separate from the §6.6 corpus-matching rule, which stays strict.

### 10.2 Run flow

Incremental by default, `--fresh` forces a full refresh.

```
resolve → ingest since last known_at → dedup/cluster/cap
       → LLM extract (cache hits free; only new docs cost)
       → features as-of now → render report
       → reports/{TICKER}_{date}.md + terminal summary
```

### 10.3 Off-watchlist names

They work, but degrade honestly.

Report sections 1–6 and 9 need only prices, filings, and discussion, all fetchable on demand.
Section 7 and any predicted return require the historical panel, so for an unknown ticker they
render `unavailable — not in the modeled universe`.

This preserves the rule that predictions are labeled unavailable until a tested model exists,
and prevents the tool from quietly producing a weaker answer that looks identical to a strong one.

## 11. Report format

**The report is assembled, not narrated.**
This is the primary defense against producing convincing commentary in place of evidence.

Sections 1, 2, 4, 5, 7, and 9 render deterministically from validated records. No LLM writes them.
Only §3 and §8 use generated prose, and both may cite only `record_id`s that already exist in the store.

A final citation-audit pass walks every factual sentence and fails the render if any claim lacks
a record → span → URL chain.

| § | Content | Source | Rule |
|---|---|---|---|
| 1 | New confirmed events, dates, original links | `Event` | ≥2 independent clusters **or** a primary filing |
| 2 | Unverified claims | `Event`, `DemandEvidence` | Single-source; rendered in a visually separate block |
| 3 | Major bullish and bearish theses | LLM | May cite only existing record IDs |
| 4 | Topic attention vs baseline | deterministic | Capped share vs trailing 90d |
| 5 | Procurement/adoption and beneficiary mapping | `DemandEvidence` | Stage transitions |
| 6 | What is unknown or disputed | deterministic | Conflicting directions within one cluster |
| 7 | Did discussion lead or follow price | deterministic | Cross-correlation, labeled non-causal |
| 8 | Next factual milestones | LLM | Dated and checkable only |
| 9 | Coverage limits and extraction confidence | deterministic | Doc counts, drop rate, contamination flags |

All demonstration statistics are labeled synthetic.

## 12. Testing

The five representative tests requested, plus what this environment demands.

**Deduplication** — crosspost, repost, and copypasta fixtures collapse to one cluster.

**Ticker ambiguity** — adversarial fixture covering `"now"`, `"I'll do it now"`, `"$NOW"`,
`"ServiceNow"`, and `"NOW"` in a sentence-initial position.

**Evidence attribution** — a fabricated span is dropped, not repaired.

**Timestamps** — `known_at` ordering; null `known_at` is invisible; latency budget is applied.

**Leakage**, five tests:

1. `PointInTimeView` refuses to return a row with `known_at > t`.
2. Import-graph direction is one-way.
3. Purge and embargo remove overlapping and boundary-straddling labels.
4. The live-profile guard cannot be bypassed by any adapter.
5. Adjustment factors are computed as-of, not from a vendor's adjusted series.

**Additional** — cross-provider cache miss; `safe_ticker_component` path traversal;
stale-bar guard; the consensus-substitution refusal.

Convention: small focused test files, unit markers, all network access mocked.

## 13. Setup, cost, and reproducibility

- Dependencies managed by `uv`. `pip` on Homebrew Python 3.14 is broken on this machine.
- No credentials in source or logs. The default provider uses existing CLI auth, so no key exists.
  API-based providers read keys from the environment only.
- Reproducibility: the extraction cache key pins prompt version, model id, schema version, and provider.
  A run manifest records config hash, data vintages consumed, and cache hit rate.
- Cost: with the CLI default and cache hits, incremental daily runs over 5–15 names are
  inexpensive. The initial diagnostic backfill is the main cost and should be measured on a
  sample corpus before running in full.

## 14. Prior art: TauricResearch/TradingAgents

Reviewed at v0.4.0 (README, file tree, and several tests).

**Adopted:**

- Their leak taxonomy as a QA checklist. They shipped and fixed leaks in social (#1220),
  memory (#1251), FRED (#1275), and fundamentals (#1300). The last one motivated §5.5.
- The shared-withhold-rule pattern: one rule at the shared layer so provider swaps cannot
  reintroduce a leak. Convergent with the §5.2 gateway.
- Fail-closed migration: entries with unknown vintage are excluded from point-in-time queries.
- Ticker path-traversal hardening.
- Stale-OHLCV and cache-freshness guards.
- Treating alternative model backends as OpenAI-compatible endpoints rather than bespoke clients.
- Test organization: many small focused files, all network mocked.

**Deliberately rejected:**

Their multi-agent debate architecture — bull and bear researchers, aggressive/conservative/neutral
risk debators, research manager, portfolio manager.

Adversarial LLM debate is a commentary generator.
It produces a confident bull case and a confident bear case whether or not signal exists,
because that is what it is built to do.
Nothing in that loop can return "there is no edge here."
There is no baseline comparison, no purging, no cluster-aware effective n, and no
minimum-detectable-effect reporting.

Also rejected: LangGraph, as heavy for a linear pipeline; and collapsing sources into a single
sentiment scalar, which destroys per-claim evidence attribution.

## 15. Risks and limitations

1. **Underpowered by construction.** At 5–15 names the most likely honest verdict is
   "not distinguishable from zero." The MDE header makes this legible rather than disappointing,
   but it does not make it go away.
2. **Contamination is unquantified, not eliminated.** The prospective track is the only real fix
   and it takes months to produce a usable sample.
3. **Reddit scraping will break again.** It already did once, when `old.reddit.com` began
   gating behind login. Source-mix sensitivity makes a dead source appear as a visible coverage
   collapse rather than a quiet signal decay.
4. **Extraction quality has no ground truth.** Mitigation: hand-label ~100 spans as a fixture and
   report extraction precision and recall in report §9, so "40 events found" carries a known error rate.
5. **Consensus surprise features are absent.** This weakens the tier-1 baseline relative to what
   a funded desk would use, which biases the comparison in favor of the social and LLM tiers.
   Noted in every evaluation run.

## 16. Future phases, out of scope here

- Layer E: time-varying weights, Kalman filtering, regime models. Gated on §8.2.
- Compliant consensus estimate acquisition.
- Universe expansion, which would make cross-sectional rank correlation meaningful.
- Prospective evaluation readout, once sufficient forward data has accrued.
