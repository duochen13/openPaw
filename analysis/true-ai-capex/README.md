# Hyperscaler reported vs true AI capex (incl. SPV / off-balance-sheet)

Implements [issue #34](https://github.com/duochen13/openPaw/issues/34).

Hyperscalers increasingly fund AI data centers through SPVs / off-balance-sheet
vehicles, so reported capex understates true AI funding. This dataset tracks the gap.

## Files

- `series.csv` — the dataset. Columns: `year`, `scope`, `series`, `value_usd_b`,
  `anchor_deal`, `source`, `note`.
- `build_chart.py` — regenerates `chart.png` from `series.csv` (nothing else).
- `chart.png` — generated output. Never edit by hand.

## Methodology (read before quoting numbers)

**Two flow series (annual, $B):**

1. `reported_capex` — reported capex from 10-K/earnings. Big-4 = MSFT + AMZN + GOOGL + META
   (calendar year). Oracle is kept separate (FY basis) to avoid mixing fiscal calendars.
2. `offbs_spv_estimate` — **newly announced** off-BS/SPV commitments, booked in the
   announcement year. This is a *funding-side* view of true AI spend: it answers "how much
   additional AI build was funded off-balance-sheet this year", **not** "how much off-BS
   cash was spent this year" (drawdown schedules are not disclosed, so annual spend
   cannot be honestly estimated — we do not invent it).

**Anchor rule:** every `offbs_spv_estimate` row names its anchor deal + source in the CSV.
No anchor deal, no estimate (2023 = $0 by construction).

**Combined ("true funding"):** computed by `build_chart.py` as reported + off-BS.
Commitments ≠ same-year spend — the label on the chart says "true funding", not "true spend",
deliberately.

**Stocks vs flows:** `*_stock` rows (WSJ ~$3T off-BS commitments, GOOGL $811B purchase
commitments, META $347B uncommenced leases) are commitment *stocks*. They are plotted in a
separate panel on a separate axis and are **never** mixed with the annual flow axis.

## Anchor deals

| Year | Deal | Amount | Source |
|------|------|--------|--------|
| 2024 | MSFT Global AI Infrastructure Investment Partnership (GAIIP, BlackRock/GIP/MGX) | up to $100B ($30B equity target) | Microsoft newsroom 2024-09-17 |
| 2025 | FT: $120B+ AI debt moved off-BS (ORCL/META/xAI/CRWV via Pimco/BlackRock/Apollo/Blue Owl) | $120B+ aggregate | Financial Times Dec-2025 |
| 2025 | ↳ META Hyperion via SPV Beignet Investor LLC ($27B debt + $3B Blue Owl equity, Meta 20%) | $30B | techerati / superex Dec-2025 |
| 2025 | ↳ ORCL Vantage $38B debt package (TX+WI sites) | $38B | news.superex.com Dec-2025 |
| 2025 | ↳ xAI $20B SPV (Nvidia-chip-secured debt) | $20B | techerati Dec-2025/Jan-2026 |
| 2026 | META El Paso "Sopaipilla" 1GW via BlackRock 80/20 SPV (~$12.3B bonds at 7.534%) | $12.3B | Bloomberg 2026-07-27 |

The 2025 aggregate ($120B+) is used instead of summing components, to avoid double counting.

## Regenerate

```bash
cd analysis/true-ai-capex
python3 build_chart.py            # writes chart.png
python3 build_chart.py --out /tmp/test.png
```

## Limitations / open questions

- 2026 off-BS tracking is not exhaustive (only the El Paso deal verified so far).
- Big-4 reported figures are the compiled anchors from issue #34 (verified 2026-09-20);
  per-company breakdowns can be added from 10-Ks later.
- If drawdown schedules are ever disclosed, a true annual *spend* series can replace the
  announcement-year commitment series.
