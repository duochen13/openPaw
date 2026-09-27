# Hyperscaler 5Y CDS spreads over time

Implements [issue #35](https://github.com/duochen13/openPaw/issues/35).

Credit-insurance prices (5Y CDS) are the market's real-time vote on hyperscaler leverage
as AI capex explodes and SPV debt piles up off-balance-sheet. This dataset tracks them
as a credit-stress signal.

## Files

- `series.csv` — the dataset. Columns: `date`, `company`, `metric`, `value_num`,
  `value_text`, `unit`, `proxy_type`, `source`, `note`.
- `annotations.csv` — AI-debt news events used to annotate widening episodes
  (`date`, `label`, `companies`, `source`).
- `build_chart.py` — regenerates `chart.png` from the two CSVs (nothing else).
- `chart.png` — generated output. Never edit by hand.

## The data problem (and how this dataset handles it)

Continuous CDS history is paywalled (Bloomberg/ICE). What *is* public: CDS prints
quoted in news reporting (usually at stress moments), bond spread medians, rating
actions, and secondary loan quotes. So:

- `proxy_type = cds_print` — an actual 5Y CDS spread quoted in a news article.
  Every one carries its outlet + underlying data vendor (LSEG/Bloomberg/ICE/S&P/FactSet)
  in the `source` column.
- `proxy_type = bond_spread | loan_quote | rating_action` — fallbacks. These are
  **never plotted as CDS prints**: the chart puts them in a separate, clearly labeled
  "Credit PROXIES — not CDS prints" panel.

**Gaps are real gaps.** The top panel connects sparse prints with thin lines for
readability, but the markers are the data — there is no interpolation and no weekly
series. A true 2023→present weekly series requires a Bloomberg/ICE subscription.

## Coverage (verified 2026-09-26)

- **ORCL**: 14 prints, 2024 (~40bps) → Sep-2026 record 227.5bps (Bloomberg via Barron's).
  Widest since the 2008 GFC.
- **CRWV**: 6 prints, Oct-2025 (368bps) → late-Jul-2026 (~1000bps) → Sep-2026 (>800bps).
  (CRWV *is* quoted — the issue's "+CRWV if quoted" is answered yes.)
- **GOOGL**: 38bps (Nov-2025) → 45 (Mar-2026) → 64 (Jul-2026, "biggest in ≥5 years").
- **META**: 95bps (Jul-2026). **AMZN**: 38bps (Nov-2025). **MSFT**: 34bps (Nov-2025).
  **NVDA**: 80bps (Jul-2026, context only — not in issue scope).
- Proxies: LSEG median bond spreads (AMZN/GOOGL/META/ORCL: 2-4yr 30→40, 5-7yr 50→60,
  20yr+ 108.5→118, 2025→Jul-2026, via Reuters); ORCL Project Jupiter $18B loans 89-91c
  (Sep-2026, FT via Reuters); S&P ORCL→BBB- Jul 9 2026; Moody's ORCL negative outlook;
  S&P CRWV B+ affirmed Apr 9 2026.

No public prints were found for MSFT/AMZN/META/GOOGL in 2023-2024 or for 2023 at all —
those cells are empty, not zero.

## Regenerate

```bash
cd analysis/cds-spreads
python3 build_chart.py            # writes chart.png
python3 build_chart.py --out /tmp/test.png
```

## Follow-up (not in this PR)

- The issue's optional item — wiring into the ai-slowdown-news-watch Track B as a
  quantitative trigger (e.g. alert if any hyperscaler 5Y CDS widens >50bps in a month) —
  is **not done here**: no watcher code exists in the repo yet (only a report mentions
  "slowdown"). The `series.csv` schema is append-friendly for whenever the watcher lands.
- Backfilling a denser series needs a Bloomberg/ICE subscription or a vendor feed.
