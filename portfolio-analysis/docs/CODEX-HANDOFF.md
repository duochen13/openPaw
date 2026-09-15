# Codex pickup — 2026-09-13

## Latest chart delivery

The user requested an HTML stock chart, so an evidence renderer was added
without waiting for model attribution. `./portfolio-analysis/run chart META
--keyless` from the repository root is the single command; `run render META`
regenerates from saved artifacts. `--refresh-prices` updates prices explicitly.

`out/META.html` covers all 30 detected moves and all 30 keyless event windows.
Dated records and source headlines are clickable, with partial coverage and
post-move timing visible. Price direction uses the actual return; abnormal
magnitude sets marker size. The chart excludes the beta warm-up year and has
indexed/log and adjusted-price/log modes. No attribution/confidence is invented.

170 offline tests pass; Ruff and mypy pass. Headless Chrome verified desktop
and 390px mobile layouts, marker selection, filters, keyboard navigation, SVG
export, zero external requests, and no JavaScript errors. Screenshots under
`out/` were visually inspected. `scratch/chart_browser_check.cjs` documents the
browser checks and accepts `PLAYWRIGHT_MODULE` pointing to an installed package.

Full Alpha Vantage enrichment and Muse attribution remain pending; the older
partial-backfill notes below describe the state before the chart request.

## Latest implementation status

Plan 2 Tasks 1–10 are implemented; see `PLAN-2-IMPLEMENTATION.md`.
Offline: 161 tests pass; Ruff and strict mypy pass (19 source files).
Live: 8 tests pass, 1 Alpha Vantage test skips without its environment key.
A separate run with the existing key was refused by Alpha Vantage due to daily
quota exhaustion. Its refusal has been recorded for the current UTC day.

The live `data/events/META/2024-04-25.json` currently has 114 HackerNews
documents, the anchor EDGAR filings, and the April 26 PCE event. It explicitly
marks earnings/news as missing and HN hit counts as approximate. It is a
keyless partial bundle, not the full Plan 2 acceptance artifact.

Next: after quota reset, load the external environment and rerun
`collect-events META --date 2024-04-25`, then run the full META backfill.
The newly enabled sources invalidate the partial bundle automatically.
Live earnings/news verification and the full backfill remain unfinished.
Muse billing/readiness still has not been retested; no model calls were made.
Do not write Plan 3 until the full bundles have been examined.

Credential scan: all 22 current cache files were checked against the configured
keys; none contained a key. No credentials were printed or committed.

The sections below preserve the initial study findings for context.


Read this alongside `SESSION-2026-09-14.md`, the design spec, and Plan 2.
This records a repository study and local verification, not completion of Plan 2.

## Verified current state

- Current branch is `main`, at `7bfaf8b`. The foundation was merged; the old
  session's unmerged-branch status is obsolete.
- The implemented CLI has only `ingest-prices` and `detect-moves`.
- Python 3.13, requests, PyYAML, SQLite, and pure-Python statistics form the
  foundation. Configuration and artifact paths resolve against the project root.
- `artifacts.read_moves` is the input boundary for event collection;
  `Store.adjusted_series` supplies benchmark sessions for its trading calendar.
- Existing local artifacts include `data/moves/META.json` and
  `out/META-preview.html`. The preview is a spike, not the final renderer.
- Local checks: 82 tests passed, 5 network tests deselected; `ruff check .`
  passed; `mypy` passed for all 8 source files. Live providers were not retested.
- Pre-existing untracked root `.claude/` and
  `docs/liam-hyland-stock-framework.md` were left untouched.

## Intended product and constraints

Explain historical META moves relative to QQQ, using dated evidence. No trading
signals or brokerage integration. Keep code-verified facts separate from claims
reported by sources. Preserve the requested Muse Spark attribution provider;
switching coding assistants does not change the application's model choice.
Attribution must include citation validation, abstention, placebo, and sign-flip
controls. Output is a self-contained HTML file per ticker.

## Next implementation: Plan 2

Implement the trading calendar, cached HTTP and persistent quota ledger, evidence
types, EDGAR, earnings, news, macro calendar, HackerNews, canonical bundles, and
`collect-events`. Expand the adapter sketches into testable contracts first.
The unavailable superpowers skill references in the historical plan are not
installed skills in this session.

Resolve these findings rather than copying the plan's literal code unchanged:

1. Use `zoneinfo.ZoneInfo("America/New_York")` for timestamp conversion.
   The fixed UTC-4 offset misdates winter stories around midnight. Date-only
   filing and earnings values must retain their source calendar date rather
   than being treated as midnight UTC and shifted to the previous day.
2. Add bounded retries/backoff for transient HTTP failures. The sample HTTP
   implementation performs only one request despite the plan requiring retries.
3. Reserve quota before each outbound attempt, including retries. The sample
   records only after a successful fetch, so timeouts and process death can
   leave actual spend unrecorded. Use atomic persistence and validate ledger
   structure. Keep collection serial as designed.
4. Distinguish provider errors from quota exhaustion and valid empty results.
   Do not permanently cache refusal payloads. Credential stripping from request
   URLs alone does not cover secrets echoed in response bodies or exceptions.
5. Reconcile `EventSource.collect` with EDGAR's required `cik` argument, and
   define consistent coverage/error semantics before bundle assembly.
6. Define refresh/completeness rules. Permanently caching mutable EDGAR indexes
   and earnings histories prevents later runs from seeing new entries. A
   clamped window missing the next session must not become permanently complete.
7. Preserve EDGAR archive merging, requested-ticker news relevance, HN title
   fallback and pagination, and stable bundle hashes across source reordering.
8. Populate the macro calendar from authoritative sources with explicit coverage;
   missing calendar coverage must not be interpreted as no macro event.

## Documentation conflicts to reconcile during Plan 2

- README and spec section 16 still say consensus estimates are unavailable;
  spec section 4.4 and the later session record available EPS estimates with
  unknown vintage. Revenue consensus remains a separate limitation.
- Config and spec section 7 still use `2022-03-01` for news coverage, whereas
  the session records a measured January 2020 start.
- The spec still mentions FRED; the later plan replaces it with checked-in YAML.
- The spec describes append-only price rows, but the implementation deliberately
  upserts adjusted prices. Several illustrative bundle values/counts are old
  mockup data, not verified live output.

## Later work and external dependencies

Plan 3 must wait until Plan 2 produces real bundles; its prompt depends on their
actual contents. The previous session reports Muse billing blocked with HTTP
402 and credentials exposed in an earlier transcript. Billing and rotation
status were not checked in this study. They do not prevent offline Plan 2 work.
Run the existing Muse readiness probe once account setup is resolved.

Plan 4 still needs the production renderer and visual inspection. The preview
provides the indexed, log-scale chart approach but has no real attribution.

## Local checks

Run from `portfolio-analysis/`:

```sh
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
PYTHONPATH=src .venv/bin/python -m portfolio_analysis.cli --help
```

Use the module invocation because the existing editable-install `.pth` issue
is documented in README. No paid calls are needed for these checks.
