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
