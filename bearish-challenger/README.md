# Bearish Challenger

Research on Michael Burry, Steve Eisman and Jeremy Grantham: disclosed bearish
positions, AI-bubble risk arguments, X/Reddit discussion and observed
market moves. Start with [the dashboard](index.html) or [the report](reports/latest.md).

## Run from the openPaw root

```sh
./bearish-challenger/run build
open bearish-challenger/index.html
./bearish-challenger/run report
# Preview reviewed alerts (silent when none qualify; does not send notifications):
./bearish-challenger/run alerts
# Discover new public-feed headlines, then refresh the local dashboard:
./bearish-challenger/run collect
./bearish-challenger/run build
# Offline tests:
portfolio-analysis/.venv/bin/python -m unittest discover -s bearish-challenger/tests
# Browser verification (uses local Playwright and Chrome):
node bearish-challenger/tests/check_dashboard.cjs
```

The browser check verifies investor/evidence/ticker filters, the empty-position
state, mobile overflow and JavaScript errors. Set `PLAYWRIGHT_MODULE` and
`CHROME_PATH` to use installations other than this workspace's local defaults.

Standard library only. The launcher reuses the local portfolio-analysis Python
interpreter if present, otherwise Python 3.10+. No additional package install.

## Initial research — September 19, 2026

The source-linked dataset in `data/research.json` is manually reviewed. The dashboard
and report distinguish historical SEC holdings, primary self-disclosures,
unverified reports and closed *specific option contracts*. No position is labeled
current merely because a 2025 filing or social repost contains the ticker.

Eisman explicitly disclosed a FICO short in his September 18 public post preview.
It is a non-AI competition thesis. Burry's 2025 NVDA/PLTR puts are filing-backed;
September reports are less certain and a newer September 11 trading post exists.
Grantham's bubble thesis does not establish a particular personal short.
The complete investor positions and research links are in the report.

## Collection and review

`collect` collects only public RSS/Atom title, date and URL metadata from Burry and
Eisman Substack feeds and month-filtered Reddit searches for all three investors.
It upserts by channel/URL, preserves older leads after failures, sets timeouts,
and records per-source failures in `data/collection-status.json`. A failure is
not treated as an empty successful collection. It does not claim complete history.

The inbox is **unreviewed**. It never changes `research.json` or creates a position.
To publish an update, review the original source, add a source record and the dated
claim to `research.json`, update the research cutoff, then build. Keep old records
and record instrument-specific closures separately. Syndicated stories and
reposts sharing an origin do not independently corroborate one another.

X was checked during initial research, but the Burry profile and linked tracker
post were not directly retrievable. There is no authenticated X API integration.
The tracker is not Burry. X AI trend summaries and lookalike accounts are excluded
as evidence. Use manually verified permalinks for future X entries; retain an
explicit access status when an original cannot be read. Grantham's primary GMO
publications currently require manual review. Paywalled trade details are not
bypassed or reconstructed from headlines.

## Risk and price methodology

Each risk chain contains a sourced fact or attributed statement, conditional
mechanism, affected research tickers and measurable indicators.
Exposure mapping is analyst interpretation, not an additional holdings disclosure.
Company accusations and accounting concerns stay attributed claims until verified.

`build` reads `../portfolio-analysis/data/prices.sqlite` in SQLite **read-only** mode.
Override with `--db PATH`. It never fetches prices, changes the portfolio database
or trades. It calculates stock adjusted-close returns and simple excess versus
QQQ over 1, 5 and 20 benchmark trading sessions around explicitly dated publications.
After-close publications start with the next session and use the publication-day
close as baseline. Unknown publication times produce a labeled date-window proxy.
Weekend dates start on the next available benchmark session. All required asset
sessions must exist; incomplete windows stay unavailable. Coverage dates and
price-provider metadata are displayed. These returns do not isolate causation,
measure a short seller's P&L, or substitute for option valuations.

## Files and delivery

- `data/research.json`: curated evidence, positions, risk chains, discussions.
- `data/market-reactions.json`: generated calculations and coverage.
- `index.html`: self-contained, filterable local dashboard; no external assets.
- `reports/latest.md`: generated source-linked research digest.
- `app.py` / `template.html`: collector, calculations and rendering.
- `tests/`: offline tests of attribution rules, session alignment and feed parsing.

Delivery is local files and chat for now. No email or scheduled background job is
configured. Feed collection discovers leads; it is not an unattended analyst or
a continuously updated position tracker.

## Direction: bearish-confirmation

`track.json` defines the directional track. Holdings: NVDA, MSFT, GOOGL, META, NOW.
Only two sub-signals qualify:

1. New substantive investor commentary about AI bubbles, AI capex or economic collapse.
2. A market move, media/analyst response or positioning development explicitly attributed
   to that commentary, with a stated connection to the watched holdings.

No neutral roundups, bullish rebuttals, recycled quotes, unrelated short positions,
or coincident selloffs presented as causation. Factual verification still applies.
The initial research archive is separate from the fresh alert feed; old sources
are not republished as new signals.

`./bearish-challenger/run alerts` prints short English alerts from **reviewed**
`data/signals.json` records, otherwise zero output. Each alert contains what
happened, a source link and one holdings-impact line. Freshness defaults to 72
hours from the original statement/reaction timestamp, not the repost timestamp;
this is a configurable initial default, not a user-specified schedule.

The gate requires explicit reviewed/substantive/non-recycled flags, verified
original commentary or attributed reaction, relevant topic/holdings, and a source.
It suppresses repeated original event keys and normalized statement text. The
reviewer must map paraphrased reposts to the same event key; the gate does not
perform semantic fact-checking. See tests/test_alerts.py for the record contract.
`data/delivered.json`, when present, contains SHA-256 event/text fingerprints already
delivered. A future transport must persist both fingerprints only after successful
sending. Printing a preview does not mark anything delivered.

**Delivery is not activated.** The matching track's channel and schedule have not
been identified. No scheduler, mail transport, X credentials or background pings
are installed. Public-feed collection discovers leads; their substantive content
still requires review before the alert gate.
