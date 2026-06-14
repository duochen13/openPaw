# Stock Watchlist Section — Design

**Date:** 2026-06-14
**Status:** Approved (design phase)

## Goal

Add a "Market Watchlist" section to the daily digest email that monitors a
fixed watchlist of stocks. The section shows a **time-series chart** of YTD
cumulative return for all symbols, plus a **snapshot table** of each symbol's
current price, **year-to-date (YTD) return**, and **P/E ratio**.

## Watchlist (fixed)

Eight symbols, defined as a constant in the fetcher:

| Symbol | Label |
|--------|-------|
| SPY    | S&P 500 |
| AAPL   | Apple |
| MSFT   | Microsoft |
| GOOGL  | Alphabet |
| AMZN   | Amazon |
| NVDA   | NVIDIA |
| META   | Meta |
| TSLA   | Tesla |

`SPY` (the S&P 500 ETF) stands in for the S&P 500 index so it has a tradable
price series and, where available, fundamentals.

## Metrics

Per symbol:

- **YTD daily close series** — the full daily closing-price series from the first
  trading day of the current calendar year to the latest. Used both for the
  current price and to build the cumulative-return chart.
- **YTD return %** — `(latestClose - firstTradingDayOfYearClose) / firstTradingDayOfYearClose * 100`.
- **P/E ratio** — trailing P/E. For `SPY` this is frequently unavailable from the
  data provider; when missing it renders as `—` and does not fail the row.

### Charting constraint (why P/E is not a time series)

The digest is delivered as an HTML email (Gmail) and optionally exported to PDF.
Gmail strips `<script>` and inline `<svg>`, so charts must be **raster images**
referenced by URL. Free market-data tiers provide a historical *price* series
but **only the current trailing P/E** (historical P/E needs historical EPS,
which is not available free). Therefore:

- **Charted over time (x = trading day):** cumulative return % (and, implicitly,
  price, via the underlying series).
- **Snapshot only (current value, shown in the table):** price and P/E ratio.

## Data sources

### Primary: Alpha Vantage (requires free API key)

- **YTD prices:** `TIME_SERIES_DAILY` with `outputsize=full`. Provides the full
  daily series, from which we read the latest close and the first trading day of
  the current calendar year. (One call per symbol.)
- **P/E ratio:** `OVERVIEW` → `PERatio` field. (One call per symbol.)
- ~16 calls per run (8 symbols × 2), under the free tier's 25/day limit.
- Calls are issued **sequentially with a short delay** to respect the 5-requests/
  minute free-tier limit.
- A response containing a rate-limit `Note`/`Information` field is treated as a
  failure and triggers the fallback.

### Fallback: Yahoo Finance (no key)

Used when Alpha Vantage errors or returns a rate-limit notice:

- **YTD prices:** `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=ytd&interval=1d`
  → first and last close. (One call per symbol.)
- **P/E ratio:** `https://query1.finance.yahoo.com/v7/finance/quote?symbols=SPY,AAPL,...`
  → `trailingPE` for all symbols in **one batched call**.

Yahoo endpoints are unofficial and may change without notice; this is acceptable
as a fallback only.

## Fetcher: `src/fetchers/stocks.js`

```
fetchStockData(alphaVantageApiKey) -> {
  asOf: ISO timestamp,
  holdings: [
    {
      symbol, label,
      price,                       // latest close
      ytdReturnPct,                // number
      peRatio | null,
      series: [                    // YTD daily series, ascending by date
        { date: 'YYYY-MM-DD', cumulativeReturnPct: number }
      ],
      source: 'alphavantage' | 'yahoo'
    }
  ],
  source: 'alphavantage' | 'yahoo' | 'mixed',
  error?: string   // present only when the whole fetch failed
}
```

The `series` carries the per-date cumulative return (rebased to 0% at the first
trading day of the year) so the chart layer needs no further computation. To
keep chart URLs small, the series is **downsampled to ~weekly points** (every
5th trading day, always including the last point) before being handed to the
chart builder.

- Each symbol is fetched independently; one bad symbol yields a row dropped (or
  with null metrics) rather than failing the whole section.
- If Alpha Vantage produces zero usable holdings, fall back to Yahoo for the
  whole batch.
- If both sources fail entirely, return `{ holdings: [], error }`.
- Follows the existing fetcher conventions: `axios` with `TIMEOUT_MS`, structured
  `logger` warnings/errors, no throwing past the top-level (returns empty +
  `error` so the digest degrades gracefully, consistent with how `index.js`
  treats other sources).

## Config

`ALPHA_VANTAGE_API_KEY` as a plain environment variable, matching the existing
Nutritionix pattern (not an AWS Secrets Manager ARN — the free key is
low-sensitivity).

- Add to `.env.example`.
- Add to `template.yaml` Lambda environment variables (and a CloudFormation
  parameter with a blank default).
- Yahoo fallback needs no key, so the section still works without the key set
  (degrades to Yahoo-only).

## Chart builder: `src/email/stockChart.js`

A small, pure module (no network) that turns the holdings' `series` into a
**QuickChart.io image URL**.

- `buildReturnChartUrl(holdings) -> string` — produces a QuickChart line-chart
  config (Chart.js schema): x-axis = dates (shared across symbols), one dataset
  per symbol of `cumulativeReturnPct`, y-axis labeled "YTD return %". Title
  "YTD Cumulative Return". A distinct color per symbol; legend on.
- The config is JSON, URL-encoded into
  `https://quickchart.io/chart?w=600&h=300&c=<encoded-config>`.
- If the encoded URL would be excessively long, rely on the weekly downsampling
  (above); 8 symbols × ~25 weekly points stays well within URL limits.
- Returns `null` if no holding has a usable series, so the template can omit the
  image gracefully.

Kept separate from `template.js` so the chart config is unit-testable without
HTML noise, and `template.js` stays focused on layout.

## Email rendering: `buildStockSection(stockData)` in `src/email/template.js`

- A gradient card consistent with the other sections' visual style, titled
  **"📈 Market Watchlist"**.
- **Chart first:** `<img src="<buildReturnChartUrl(...)>" width="100%" ...>` with
  descriptive `alt` text. Omitted if the chart URL is `null`.
- **Table below:** one row per holding — symbol + label, current **price**,
  **YTD return** (green ▲ for positive, red ▼ for negative, with the percentage),
  and **P/E** (`—` when null).
- **Rows sorted by YTD return, descending** (best performer on top). The chart
  legend follows the same order.
- A small `as of <date>` line.
- If `stockData` is null/has `error`/has no holdings, render the section with
  "Market data unavailable today" — mirroring the other sections' unavailable
  state.

## Wiring: `src/index.js`

- Read `process.env.ALPHA_VANTAGE_API_KEY`.
- Add `fetchStockData(alphaVantageApiKey)` to the existing `Promise.allSettled`
  block alongside the other fetchers; on rejection, log a warning and use a
  safe empty default (same pattern as Product Hunt / HN / Plaid).
- Pass the stock result into `buildEmailTemplate(...)`.
- Section placement in the email: **after Food Orders / Uber Eats, before
  Product Hunt** — grouping the personal/financial content together.

## Testing

`tests/fetchers/stocks.test.js`:
- Alpha Vantage success → correct YTD %, P/E, and a populated `series`.
- Alpha Vantage rate-limit/error → Yahoo fallback succeeds.
- Both sources fail → returns `{ holdings: [], error }`.
- YTD computation correctness (first-of-year vs latest close).
- Missing P/E (e.g. SPY) → `null`, row still produced.
- Series downsampling keeps the last point.

`tests/email/stockChart.test.js`:
- Builds a valid QuickChart URL with one dataset per holding.
- Returns `null` when no holding has a usable series.

Template test (in existing `tests/email/template.test.js` or new case):
- Section renders with holdings: chart `<img>` present and table rows present.
- Unavailable state renders when no data.

## Non-goals (YAGNI)

- No personal/custom tickers (watchlist is fixed).
- No cost-basis / portfolio P&L.
- No intraday or real-time prices.
- No additional time windows (daily / 1-week / 1-month) — YTD only for now.
- No P/E-over-time chart (free data only provides current trailing P/E).
- No per-symbol price charts — one combined cumulative-return chart only.
