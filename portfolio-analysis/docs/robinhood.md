# Robinhood integration (issue #55)

## v1: CSV import (built)

The lowest-risk path: export your positions from Robinhood and import them with
one command. Zero credentials, zero ToS risk, survives Robinhood UI changes.

```bash
# In the Robinhood app: Account → Statements & History → Export (positions CSV)
python run portfolio-analysis import-robinhood-csv ~/Downloads/robinhood-positions.csv
```

What it does:

- Parses ticker, shares, and average cost from the CSV. Header names are
  matched tolerantly (`Symbol`/`Ticker`, `Quantity`/`Shares`/`Qty`,
  `Average cost`/`Avg cost`, case-insensitive).
- Skips non-equity rows (options contracts, crypto pairs) and reports each
  skipped row with a reason instead of failing the whole import.
- Merges duplicate tickers (multiple lots) with a weighted average cost.
- Writes `config/positions.yaml` with a **timestamped snapshot**:

```yaml
snapshot:
  imported_at: '2026-09-23T02:15:00-07:00'
  source: robinhood-csv
positions:
  - symbol: NOW
    shares: 213.0
    avg_cost: 135.0
```

- `--dry-run` parses and prints the table without writing anything.

The factor dashboard (`factors.html`) renders the holdings next to the alpha
signals: shares, avg cost, latest stored close, position value, gain/loss, and
the latest trailing alpha — plus the snapshot timestamp and age. A snapshot
older than 30 days renders with a **STALE** badge so a stale import is visible,
not silent.

`config/positions.yaml` is gitignored: your holdings never enter the repo.

## Order history → trade markers (issue #65)

The same command also imports Robinhood **order history** — it auto-detects
the CSV flavor from the headers (a Trans Code / Side + date column means
orders; an average-cost column means positions), or force one with `--kind`:

```bash
# In the Robinhood app: Account → Statements & History → Export (order history)
python run portfolio-analysis import-robinhood-csv ~/Downloads/robinhood-orders.csv
python run portfolio-analysis import-robinhood-csv ~/Downloads/robinhood-orders.csv \
  --start-date 2026-06-01 --end-date 2026-09-24 --dry-run
```

What it does:

- Parses date, ticker, side (buy/sell), quantity, and fill price. Header
  names are matched tolerantly (`Activity Date`/`Trade Date`,
  `Instrument`/`Symbol`, `Trans Code`/`Side`, `Quantity`/`Qty`,
  `Price`/`Fill Price`, case-insensitive).
- Keeps only buy/sell executions. Dividends, fees, interest, transfers, and
  deposits are skipped with a recorded reason, as are options and crypto rows.
- `--start-date` / `--end-date` (inclusive, `YYYY-MM-DD`) filter the trades;
  the default is all trades in the file.
- Writes `config/trades.yaml` (also gitignored):

```yaml
meta:
  source: robinhood-csv
trades:
  - symbol: GOOGL
    date: '2026-09-23'
    side: buy
    qty: 6.0
    price: 349.93
```

Each per-stock dashboard (`NOW.html`, …) then renders this ticker's trades
as vertical markers — green for buys, red for sells, tooltip with qty @
price — on the price chart **and** on the beta / R² / alpha / alpha-slope
sparklines, so entries can be checked against the alpha signals directly.

## v2: unofficial API sync (NOT built — read this first)

Robinhood has **no official public API**. Community clients (`robin_stocks`
style) exist but sit in a ToS gray area and break whenever Robinhood changes
its internals. If this is ever built, the rules are:

- **Read-only scope**: positions + orders history. No order placement, no
  auto-trading — this integration is portfolio sync, not a trading bot.
- **Credentials live in the Secure Vault**, never in the repo, config files, or
  logs. Login needs MFA/2FA handling; never paste codes or passwords into chat.
- Explicit go-ahead required before building: say so in the issue and get a
  yes. The CSV path stays the default until then.
