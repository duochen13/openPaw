# Stock Watchlist Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Market Watchlist" section to the daily digest email showing a YTD cumulative-return chart plus a snapshot table (price, YTD return %, P/E) for the S&P 500 (SPY) and the Magnificent 7.

**Architecture:** A new fetcher (`src/fetchers/stocks.js`) pulls daily price series + P/E from Alpha Vantage, falling back to Yahoo Finance on error/rate-limit. A pure chart module (`src/email/stockChart.js`) turns the series into a QuickChart.io image URL. `template.js` gains `buildStockSection` and a new `stockData` parameter; `index.js` wires the fetcher into the existing `Promise.allSettled` flow.

**Tech Stack:** Node.js (CommonJS), axios, Jest. Alpha Vantage + Yahoo Finance APIs, QuickChart.io for chart images.

---

## File Structure

- **Create** `src/fetchers/stocks.js` — fetches watchlist data; exports `fetchStockData`, plus internal helpers (`WATCHLIST`, `buildSeriesAndReturn`, `downsample`) for testing.
- **Create** `src/email/stockChart.js` — pure module; exports `buildReturnChartUrl(holdings)`.
- **Modify** `src/email/template.js` — add `buildStockSection`, add `stockData` parameter to `buildEmailTemplate`, render the section between Uber Eats and Product Hunt.
- **Modify** `src/index.js` — read `ALPHA_VANTAGE_API_KEY`, add `fetchStockData` to `Promise.allSettled`, pass result to `buildEmailTemplate`.
- **Modify** `.env.example`, `.env`, `template.yaml` — add `ALPHA_VANTAGE_API_KEY` config.
- **Create** `tests/fetchers/stocks.test.js`, `tests/email/stockChart.test.js`; **modify** `tests/email/template.test.js`.

---

## Task 1: Watchlist constant + pure helpers

**Files:**
- Create: `src/fetchers/stocks.js`
- Test: `tests/fetchers/stocks.test.js`

- [ ] **Step 1: Write the failing test**

```js
// tests/fetchers/stocks.test.js
const {
  WATCHLIST,
  buildSeriesAndReturn,
  downsample
} = require('../../src/fetchers/stocks');

describe('stocks helpers', () => {
  test('WATCHLIST has SPY plus the Magnificent 7', () => {
    const symbols = WATCHLIST.map(w => w.symbol);
    expect(symbols).toEqual(['SPY', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']);
  });

  test('buildSeriesAndReturn computes cumulative return rebased to first close', () => {
    const closes = [
      { date: '2026-01-02', close: 100 },
      { date: '2026-01-03', close: 110 },
      { date: '2026-01-06', close: 90 }
    ];
    const built = buildSeriesAndReturn(closes);
    expect(built.price).toBe(90);
    expect(built.ytdReturnPct).toBeCloseTo(-10, 5);
    expect(built.series[0]).toEqual({ date: '2026-01-02', cumulativeReturnPct: 0 });
    expect(built.series[1].cumulativeReturnPct).toBeCloseTo(10, 5);
  });

  test('buildSeriesAndReturn returns null for empty input', () => {
    expect(buildSeriesAndReturn([])).toBeNull();
  });

  test('downsample keeps every Nth point and always the last', () => {
    const series = Array.from({ length: 12 }, (_, i) => ({ date: `d${i}`, cumulativeReturnPct: i }));
    const out = downsample(series, 5);
    expect(out.map(p => p.date)).toEqual(['d0', 'd5', 'd10', 'd11']);
  });

  test('downsample returns input unchanged when short', () => {
    const series = [{ date: 'd0', cumulativeReturnPct: 0 }];
    expect(downsample(series, 5)).toEqual(series);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest tests/fetchers/stocks.test.js -t "stocks helpers"`
Expected: FAIL — cannot find module `../../src/fetchers/stocks` (or undefined exports).

- [ ] **Step 3: Write minimal implementation**

```js
// src/fetchers/stocks.js
const axios = require('axios');
const { logger } = require('../utils/logger');

const TIMEOUT_MS = 10000;
const AV_BASE = 'https://www.alphavantage.co/query';
const YF_CHART = 'https://query1.finance.yahoo.com/v8/finance/chart';
const YF_QUOTE = 'https://query1.finance.yahoo.com/v7/finance/quote';

const WATCHLIST = [
  { symbol: 'SPY', label: 'S&P 500' },
  { symbol: 'AAPL', label: 'Apple' },
  { symbol: 'MSFT', label: 'Microsoft' },
  { symbol: 'GOOGL', label: 'Alphabet' },
  { symbol: 'AMZN', label: 'Amazon' },
  { symbol: 'NVDA', label: 'NVIDIA' },
  { symbol: 'META', label: 'Meta' },
  { symbol: 'TSLA', label: 'Tesla' }
];

// closes: [{ date, close }] ascending. Returns { price, ytdReturnPct, series } or null.
function buildSeriesAndReturn(closes) {
  if (!closes || closes.length === 0) return null;
  const base = closes[0].close;
  const series = closes.map(c => ({
    date: c.date,
    cumulativeReturnPct: ((c.close - base) / base) * 100
  }));
  return {
    price: closes[closes.length - 1].close,
    ytdReturnPct: series[series.length - 1].cumulativeReturnPct,
    series
  };
}

// Keep every `step`th point, always including the last.
function downsample(series, step = 5) {
  if (series.length <= step) return series;
  const out = [];
  for (let i = 0; i < series.length; i += step) out.push(series[i]);
  const last = series[series.length - 1];
  if (out[out.length - 1].date !== last.date) out.push(last);
  return out;
}

module.exports = { WATCHLIST, buildSeriesAndReturn, downsample };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx jest tests/fetchers/stocks.test.js -t "stocks helpers"`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/stocks.js tests/fetchers/stocks.test.js
git commit -m "feat: add stock watchlist constant and series helpers"
```

---

## Task 2: Alpha Vantage success path (`fetchStockData`)

**Files:**
- Modify: `src/fetchers/stocks.js`
- Test: `tests/fetchers/stocks.test.js`

- [ ] **Step 1: Write the failing test**

Add to `tests/fetchers/stocks.test.js`. Note: tests pass `delayMs: 0` to skip throttling. The mock routes by request URL/params.

```js
const axios = require('axios');
const { fetchStockData } = require('../../src/fetchers/stocks');

jest.mock('axios');

// Helper: an Alpha Vantage TIME_SERIES_DAILY body with two YTD closes.
function avDaily(jan, latest) {
  return {
    data: {
      'Time Series (Daily)': {
        '2026-01-02': { '4. close': String(jan) },
        '2026-06-12': { '4. close': String(latest) },
        '2025-12-31': { '4. close': '1' } // prior year, must be filtered out
      }
    }
  };
}

describe('fetchStockData — Alpha Vantage', () => {
  test('returns holdings with YTD return, P/E, and series, sorted by return desc', async () => {
    axios.get.mockImplementation((url, config) => {
      const fn = config.params.function;
      if (fn === 'TIME_SERIES_DAILY') {
        // SPY +10%, others +20% so SPY sorts last
        const latest = config.params.symbol === 'SPY' ? 110 : 120;
        return Promise.resolve(avDaily(100, latest));
      }
      if (fn === 'OVERVIEW') {
        const pe = config.params.symbol === 'SPY' ? 'None' : '30.5';
        return Promise.resolve({ data: { PERatio: pe } });
      }
      return Promise.reject(new Error('unexpected call'));
    });

    const result = await fetchStockData('FAKEKEY', { delayMs: 0 });

    expect(result.source).toBe('alphavantage');
    expect(result.error).toBeUndefined();
    expect(result.holdings).toHaveLength(8);
    // Sorted by ytdReturnPct desc → SPY (10%) last
    expect(result.holdings[result.holdings.length - 1].symbol).toBe('SPY');
    const spy = result.holdings.find(h => h.symbol === 'SPY');
    expect(spy.ytdReturnPct).toBeCloseTo(10, 5);
    expect(spy.price).toBe(110);
    expect(spy.peRatio).toBeNull(); // 'None' → null
    expect(spy.series.length).toBeGreaterThan(0);
    const aapl = result.holdings.find(h => h.symbol === 'AAPL');
    expect(aapl.peRatio).toBeCloseTo(30.5, 5);
    expect(aapl.source).toBe('alphavantage');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest tests/fetchers/stocks.test.js -t "Alpha Vantage"`
Expected: FAIL — `fetchStockData is not a function`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/fetchers/stocks.js` (above `module.exports`), then update the exports line:

```js
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function isRateLimited(data) {
  return !!(data && (data.Note || data.Information));
}

async function fetchAlphaVantageDaily(symbol, apiKey, year) {
  const res = await axios.get(AV_BASE, {
    params: { function: 'TIME_SERIES_DAILY', symbol, outputsize: 'full', apikey: apiKey },
    timeout: TIMEOUT_MS
  });
  const data = res.data || {};
  if (isRateLimited(data)) throw new Error(`Alpha Vantage limit: ${data.Note || data.Information}`);
  const ts = data['Time Series (Daily)'];
  if (!ts) throw new Error(`Alpha Vantage: no series for ${symbol}`);
  return Object.entries(ts)
    .filter(([date]) => date >= `${year}-01-01`)
    .map(([date, v]) => ({ date, close: parseFloat(v['4. close']) }))
    .filter(c => Number.isFinite(c.close))
    .sort((a, b) => a.date.localeCompare(b.date));
}

async function fetchAlphaVantagePE(symbol, apiKey) {
  const res = await axios.get(AV_BASE, {
    params: { function: 'OVERVIEW', symbol, apikey: apiKey },
    timeout: TIMEOUT_MS
  });
  const data = res.data || {};
  if (isRateLimited(data)) throw new Error(`Alpha Vantage limit (OVERVIEW): ${data.Note || data.Information}`);
  const pe = parseFloat(data.PERatio);
  return Number.isFinite(pe) ? pe : null;
}

async function fetchViaAlphaVantage(apiKey, year, delayMs) {
  const holdings = [];
  for (const { symbol, label } of WATCHLIST) {
    const closes = await fetchAlphaVantageDaily(symbol, apiKey, year);
    const built = buildSeriesAndReturn(closes);
    if (!built) continue;
    const peRatio = await fetchAlphaVantagePE(symbol, apiKey).catch(() => null);
    holdings.push({
      symbol, label,
      price: built.price,
      ytdReturnPct: built.ytdReturnPct,
      peRatio,
      series: downsample(built.series),
      source: 'alphavantage'
    });
    if (delayMs) await sleep(delayMs);
  }
  return holdings;
}

async function fetchStockData(alphaVantageApiKey, options = {}) {
  const { delayMs = 1500 } = options;
  const year = new Date().getFullYear();
  let holdings = [];
  let source = 'alphavantage';

  if (alphaVantageApiKey) {
    try {
      holdings = await fetchViaAlphaVantage(alphaVantageApiKey, year, delayMs);
    } catch (error) {
      logger.warn('Alpha Vantage failed, falling back to Yahoo', { error: error.message });
      holdings = [];
    }
  }

  if (holdings.length === 0) {
    return { asOf: new Date().toISOString(), holdings: [], source, error: 'No stock data available' };
  }

  holdings.sort((a, b) => b.ytdReturnPct - a.ytdReturnPct);
  return { asOf: new Date().toISOString(), holdings, source };
}
```

Update the exports line to:

```js
module.exports = { WATCHLIST, buildSeriesAndReturn, downsample, fetchStockData };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx jest tests/fetchers/stocks.test.js -t "Alpha Vantage"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/stocks.js tests/fetchers/stocks.test.js
git commit -m "feat: fetch stock watchlist data via Alpha Vantage"
```

---

## Task 3: Yahoo Finance fallback path

**Files:**
- Modify: `src/fetchers/stocks.js`
- Test: `tests/fetchers/stocks.test.js`

- [ ] **Step 1: Write the failing test**

Add to `tests/fetchers/stocks.test.js`:

```js
describe('fetchStockData — Yahoo fallback', () => {
  test('falls back to Yahoo when Alpha Vantage is rate-limited', async () => {
    axios.get.mockImplementation((url, config) => {
      // Alpha Vantage → rate-limit note (triggers fallback)
      if (url === 'https://www.alphavantage.co/query') {
        return Promise.resolve({ data: { Note: 'Thank you for using Alpha Vantage! 25 requests/day reached.' } });
      }
      // Yahoo batched quote (P/E)
      if (url === 'https://query1.finance.yahoo.com/v7/finance/quote') {
        return Promise.resolve({
          data: { quoteResponse: { result: [{ symbol: 'AAPL', trailingPE: 28.2 }] } }
        });
      }
      // Yahoo chart (per symbol). URL ends with /{symbol}
      return Promise.resolve({
        data: {
          chart: {
            result: [{
              timestamp: [1735819200, 1749700800], // 2025-... & 2026-... epoch seconds
              indicators: { quote: [{ close: [100, 125] }] }
            }]
          }
        }
      });
    });

    const result = await fetchStockData('FAKEKEY', { delayMs: 0 });

    expect(result.source).toBe('yahoo');
    expect(result.error).toBeUndefined();
    expect(result.holdings).toHaveLength(8);
    const aapl = result.holdings.find(h => h.symbol === 'AAPL');
    expect(aapl.peRatio).toBeCloseTo(28.2, 5);
    expect(aapl.source).toBe('yahoo');
    expect(aapl.ytdReturnPct).toBeCloseTo(25, 5); // 100 → 125
    const spy = result.holdings.find(h => h.symbol === 'SPY');
    expect(spy.peRatio).toBeNull(); // not present in quote result
  });

  test('works with no Alpha Vantage key (Yahoo only)', async () => {
    axios.get.mockImplementation((url) => {
      if (url === 'https://query1.finance.yahoo.com/v7/finance/quote') {
        return Promise.resolve({ data: { quoteResponse: { result: [] } } });
      }
      return Promise.resolve({
        data: { chart: { result: [{ timestamp: [1, 2], indicators: { quote: [{ close: [50, 55] }] } }] } }
      });
    });

    const result = await fetchStockData('', { delayMs: 0 });
    expect(result.source).toBe('yahoo');
    expect(result.holdings).toHaveLength(8);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest tests/fetchers/stocks.test.js -t "Yahoo fallback"`
Expected: FAIL — result.source is `alphavantage` with empty holdings / `error` set (no Yahoo path yet).

- [ ] **Step 3: Write minimal implementation**

Add the Yahoo helpers to `src/fetchers/stocks.js` (above `fetchStockData`):

```js
async function fetchYahooDaily(symbol) {
  const res = await axios.get(`${YF_CHART}/${symbol}`, {
    params: { range: 'ytd', interval: '1d' },
    timeout: TIMEOUT_MS
  });
  const result = res.data?.chart?.result?.[0];
  if (!result) throw new Error(`Yahoo: no chart result for ${symbol}`);
  const timestamps = result.timestamp || [];
  const closesRaw = result.indicators?.quote?.[0]?.close || [];
  return timestamps
    .map((t, i) => ({
      date: new Date(t * 1000).toISOString().slice(0, 10),
      close: closesRaw[i]
    }))
    .filter(c => Number.isFinite(c.close))
    .sort((a, b) => a.date.localeCompare(b.date));
}

async function fetchYahooPEs(symbols) {
  try {
    const res = await axios.get(YF_QUOTE, {
      params: { symbols: symbols.join(',') },
      timeout: TIMEOUT_MS
    });
    const quotes = res.data?.quoteResponse?.result || [];
    const map = {};
    quotes.forEach(q => {
      map[q.symbol] = Number.isFinite(q.trailingPE) ? q.trailingPE : null;
    });
    return map;
  } catch (error) {
    logger.warn('Yahoo P/E batch fetch failed', { error: error.message });
    return {};
  }
}

async function fetchViaYahoo() {
  const peMap = await fetchYahooPEs(WATCHLIST.map(w => w.symbol));
  const holdings = [];
  for (const { symbol, label } of WATCHLIST) {
    try {
      const closes = await fetchYahooDaily(symbol);
      const built = buildSeriesAndReturn(closes);
      if (!built) continue;
      holdings.push({
        symbol, label,
        price: built.price,
        ytdReturnPct: built.ytdReturnPct,
        peRatio: peMap[symbol] ?? null,
        series: downsample(built.series),
        source: 'yahoo'
      });
    } catch (error) {
      logger.warn(`Yahoo fetch failed for ${symbol}`, { error: error.message });
    }
  }
  return holdings;
}
```

Then update `fetchStockData` — replace the early-return block that currently fires when Alpha Vantage yields no holdings with a Yahoo fallback:

```js
  if (holdings.length === 0) {
    try {
      holdings = await fetchViaYahoo();
      source = 'yahoo';
    } catch (error) {
      logger.error('Yahoo fallback failed', { error: error.message });
      return { asOf: new Date().toISOString(), holdings: [], source: 'yahoo', error: error.message };
    }
  }

  if (holdings.length === 0) {
    return { asOf: new Date().toISOString(), holdings: [], source, error: 'No stock data available' };
  }

  holdings.sort((a, b) => b.ytdReturnPct - a.ytdReturnPct);
  return { asOf: new Date().toISOString(), holdings, source };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx jest tests/fetchers/stocks.test.js -t "Yahoo fallback"`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/stocks.js tests/fetchers/stocks.test.js
git commit -m "feat: add Yahoo Finance fallback for stock data"
```

---

## Task 4: Both-sources-fail handling

**Files:**
- Modify: `src/fetchers/stocks.js` (verify only — no code change expected)
- Test: `tests/fetchers/stocks.test.js`

- [ ] **Step 1: Write the failing test**

Add to `tests/fetchers/stocks.test.js`:

```js
describe('fetchStockData — total failure', () => {
  test('returns empty holdings with error when both sources fail', async () => {
    axios.get.mockImplementation((url) => {
      if (url === 'https://www.alphavantage.co/query') {
        return Promise.resolve({ data: { Note: 'limit' } }); // AV rate-limited
      }
      return Promise.reject(new Error('network down')); // Yahoo chart + quote fail
    });

    const result = await fetchStockData('FAKEKEY', { delayMs: 0 });

    expect(result.holdings).toEqual([]);
    expect(result.error).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it passes (already implemented)**

Run: `npx jest tests/fetchers/stocks.test.js -t "total failure"`
Expected: PASS. (Yahoo chart calls reject → `fetchViaYahoo` returns `[]`; `fetchYahooPEs` swallows its own error; final guard returns `{ holdings: [], error: 'No stock data available' }`.)

If it FAILS, fix `fetchStockData` so the final `holdings.length === 0` guard returns the error object rather than throwing.

- [ ] **Step 3: Run the whole fetcher suite**

Run: `npx jest tests/fetchers/stocks.test.js`
Expected: PASS (all describe blocks).

- [ ] **Step 4: Commit**

```bash
git add tests/fetchers/stocks.test.js
git commit -m "test: cover total-failure path for stock fetcher"
```

---

## Task 5: QuickChart URL builder

**Files:**
- Create: `src/email/stockChart.js`
- Test: `tests/email/stockChart.test.js`

- [ ] **Step 1: Write the failing test**

```js
// tests/email/stockChart.test.js
const { buildReturnChartUrl } = require('../../src/email/stockChart');

describe('buildReturnChartUrl', () => {
  const holdings = [
    { symbol: 'AAPL', series: [
      { date: '2026-01-02', cumulativeReturnPct: 0 },
      { date: '2026-06-12', cumulativeReturnPct: 25 }
    ]},
    { symbol: 'SPY', series: [
      { date: '2026-01-02', cumulativeReturnPct: 0 },
      { date: '2026-06-12', cumulativeReturnPct: 10 }
    ]}
  ];

  test('returns a QuickChart URL with one dataset per holding', () => {
    const url = buildReturnChartUrl(holdings);
    expect(url).toContain('https://quickchart.io/chart?');
    const config = JSON.parse(decodeURIComponent(url.split('c=')[1]));
    expect(config.type).toBe('line');
    expect(config.data.datasets).toHaveLength(2);
    expect(config.data.datasets.map(d => d.label)).toEqual(['AAPL', 'SPY']);
  });

  test('returns null when no holding has a usable series', () => {
    expect(buildReturnChartUrl([{ symbol: 'AAPL', series: [] }])).toBeNull();
    expect(buildReturnChartUrl([])).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest tests/email/stockChart.test.js`
Expected: FAIL — cannot find module `../../src/email/stockChart`.

- [ ] **Step 3: Write minimal implementation**

```js
// src/email/stockChart.js
const QUICKCHART_BASE = 'https://quickchart.io/chart';
const COLORS = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d'];

// holdings: [{ symbol, series: [{ date, cumulativeReturnPct }] }]
// Returns a QuickChart.io image URL, or null if nothing chartable.
function buildReturnChartUrl(holdings) {
  const usable = (holdings || []).filter(h => Array.isArray(h.series) && h.series.length > 0);
  if (usable.length === 0) return null;

  // Use the longest series' dates as the shared x-axis labels.
  const longest = usable.reduce((best, h) => (h.series.length > best.series.length ? h : best), usable[0]);
  const labels = longest.series.map(p => p.date);

  const datasets = usable.map((h, i) => ({
    label: h.symbol,
    data: h.series.map(p => Number(p.cumulativeReturnPct.toFixed(2))),
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length],
    fill: false,
    pointRadius: 0,
    borderWidth: 2
  }));

  const config = {
    type: 'line',
    data: { labels, datasets },
    options: {
      title: { display: true, text: 'YTD Cumulative Return' },
      legend: { position: 'bottom' },
      scales: {
        yAxes: [{ scaleLabel: { display: true, labelString: 'YTD return %' } }],
        xAxes: [{ ticks: { maxTicksLimit: 8 } }]
      }
    }
  };

  return `${QUICKCHART_BASE}?w=600&h=300&c=${encodeURIComponent(JSON.stringify(config))}`;
}

module.exports = { buildReturnChartUrl };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx jest tests/email/stockChart.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/email/stockChart.js tests/email/stockChart.test.js
git commit -m "feat: build QuickChart URL for YTD return chart"
```

---

## Task 6: `buildStockSection` + wire into `buildEmailTemplate`

**Files:**
- Modify: `src/email/template.js`
- Test: `tests/email/template.test.js`

- [ ] **Step 1: Write the failing test**

Add to `tests/email/template.test.js` (inside the existing `describe`):

```js
  const mockStockData = {
    asOf: '2026-06-12T17:00:00.000Z',
    source: 'alphavantage',
    holdings: [
      { symbol: 'NVDA', label: 'NVIDIA', price: 130.5, ytdReturnPct: 42.1, peRatio: 55.2,
        series: [{ date: '2026-01-02', cumulativeReturnPct: 0 }, { date: '2026-06-12', cumulativeReturnPct: 42.1 }] },
      { symbol: 'SPY', label: 'S&P 500', price: 610.2, ytdReturnPct: -3.4, peRatio: null,
        series: [{ date: '2026-01-02', cumulativeReturnPct: 0 }, { date: '2026-06-12', cumulativeReturnPct: -3.4 }] }
    ]
  };

  test('includes Market Watchlist section with chart and rows', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories, null, null, mockStockData);
    expect(html).toContain('Market Watchlist');
    expect(html).toContain('quickchart.io/chart');
    expect(html).toContain('NVDA');
    expect(html).toContain('42.10%');
    expect(html).toContain('S&P 500');
    expect(html).toContain('—'); // SPY null P/E
  });

  test('stock section appears between Uber Eats and Product Hunt', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories, null, null, mockStockData);
    const stockIndex = html.indexOf('Market Watchlist');
    const phIndex = html.indexOf('🚀 Product Hunt');
    expect(stockIndex).toBeGreaterThan(-1);
    expect(stockIndex).toBeLessThan(phIndex);
  });

  test('shows unavailable state when stock data missing', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories, null, null, null);
    expect(html).toContain('Market data unavailable today');
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx jest tests/email/template.test.js -t "Market Watchlist"`
Expected: FAIL — section not present (string not found).

- [ ] **Step 3: Write minimal implementation**

Add `buildStockSection` to `src/email/template.js` (e.g. after `buildUberEatsHighlightsSection`):

```js
function buildStockSection(stockData) {
  const headerOpen = `
    <div class="section" style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
      <h2 style="color: white; margin-top: 0;">📈 Market Watchlist</h2>`;

  if (!stockData || stockData.error || !stockData.holdings || stockData.holdings.length === 0) {
    return `${headerOpen}
      <p style="color: white; font-style: italic; opacity: 0.9;">Market data unavailable today</p>
    </div>`;
  }

  const { buildReturnChartUrl } = require('./stockChart');
  const chartUrl = buildReturnChartUrl(stockData.holdings);
  const chartImg = chartUrl
    ? `<img src="${chartUrl}" alt="YTD cumulative return chart for the watchlist" width="100%" style="border-radius: 6px; background: white; margin-bottom: 15px;">`
    : '';

  const asOf = new Date(stockData.asOf).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric'
  });

  const rows = stockData.holdings.map(h => {
    const positive = h.ytdReturnPct >= 0;
    const arrow = positive ? '▲' : '▼';
    const color = positive ? '#bbf7d0' : '#fecaca';
    const pe = (h.peRatio === null || h.peRatio === undefined) ? '—' : h.peRatio.toFixed(1);
    return `
      <tr>
        <td style="padding: 6px 8px;"><strong>${h.symbol}</strong> <span style="opacity: 0.8; font-size: 13px;">${h.label}</span></td>
        <td style="padding: 6px 8px; text-align: right;">$${h.price.toFixed(2)}</td>
        <td style="padding: 6px 8px; text-align: right; color: ${color}; font-weight: bold;">${arrow} ${h.ytdReturnPct.toFixed(2)}%</td>
        <td style="padding: 6px 8px; text-align: right;">${pe}</td>
      </tr>`;
  }).join('');

  return `${headerOpen}
    ${chartImg}
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
      <thead>
        <tr style="text-align: left; opacity: 0.9; font-size: 12px;">
          <th style="padding: 6px 8px;">Symbol</th>
          <th style="padding: 6px 8px; text-align: right;">Price</th>
          <th style="padding: 6px 8px; text-align: right;">YTD</th>
          <th style="padding: 6px 8px; text-align: right;">P/E</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <p style="font-size: 12px; opacity: 0.8; margin: 12px 0 0 0;">as of ${asOf}</p>
  </div>`;
}
```

Change the `buildEmailTemplate` signature to accept `stockData`:

```js
function buildEmailTemplate(phProducts, hnStories, spendingData, foodOrdersData = null, stockData = null) {
```

Add this line near the other section-building lines (after `uberEatsSection` is computed):

```js
  const stockSection = buildStockSection(stockData);
```

Insert `${stockSection}` into the returned HTML, immediately after `${uberEatsSection}` and before the Product Hunt `<div class="section">`:

```js
        ${uberEatsSection}

        ${stockSection}

        <div class="section">
          <h2>🚀 Product Hunt</h2>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx jest tests/email/template.test.js`
Expected: PASS (existing tests unaffected — the new 5th param defaults to `null`; new tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/email/template.js tests/email/template.test.js
git commit -m "feat: render Market Watchlist section in digest email"
```

---

## Task 7: Wire fetcher into `index.js`

**Files:**
- Modify: `src/index.js`

- [ ] **Step 1: Add the require**

Near the other fetcher requires at the top of `src/index.js`, add:

```js
const { fetchStockData } = require('./fetchers/stocks');
```

- [ ] **Step 2: Add to the parallel fetch and read the key**

Replace the existing `Promise.allSettled` destructuring block:

```js
    const [phProducts, hnStories, spendingData] = await Promise.allSettled([
      fetchTopProductHuntProducts(phApiKey, phApiSecret),
      fetchTopHackerNewsStories(),
      fetchPlaidSpending(plaidClientId, plaidSecret, plaidAccessToken, process.env.PLAID_ENVIRONMENT || 'sandbox')
    ]);
```

with:

```js
    const [phProducts, hnStories, spendingData, stockResult] = await Promise.allSettled([
      fetchTopProductHuntProducts(phApiKey, phApiSecret),
      fetchTopHackerNewsStories(),
      fetchPlaidSpending(plaidClientId, plaidSecret, plaidAccessToken, process.env.PLAID_ENVIRONMENT || 'sandbox'),
      fetchStockData(process.env.ALPHA_VANTAGE_API_KEY)
    ]);
```

- [ ] **Step 3: Resolve the value and log failures**

After the existing `const spending = ...` line, add:

```js
    const stocks = stockResult.status === 'fulfilled' ? stockResult.value : { holdings: [] };

    if (stockResult.status === 'rejected') {
      logger.warn('Stock fetch failed', { error: stockResult.reason.message });
    }
```

- [ ] **Step 4: Pass into the template**

Replace:

```js
    const htmlBody = buildEmailTemplate(products, stories, spending, foodOrders);
```

with:

```js
    const htmlBody = buildEmailTemplate(products, stories, spending, foodOrders, stocks);
```

- [ ] **Step 5: Verify the full test suite still passes**

Run: `npx jest`
Expected: PASS (all suites). `index.js` has no dedicated unit test that calls the handler end-to-end with stocks; this step verifies nothing else broke.

- [ ] **Step 6: Commit**

```bash
git add src/index.js
git commit -m "feat: wire stock watchlist fetcher into daily digest handler"
```

---

## Task 8: Configuration

**Files:**
- Modify: `.env.example`, `.env`, `template.yaml`

- [ ] **Step 1: Add to `.env.example`**

Append under a new heading (after the Nutrition section):

```
# Stock Watchlist (Alpha Vantage — free key at https://www.alphavantage.co/support/#api-key)
# Optional: if unset, the section falls back to Yahoo Finance (no key needed).
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
```

- [ ] **Step 2: Add to local `.env`**

Append the same `ALPHA_VANTAGE_API_KEY=...` line with the real key (or leave the placeholder to exercise the Yahoo fallback locally). `.env` is gitignored — do not commit it.

- [ ] **Step 3: Add to `template.yaml`**

Add a CloudFormation parameter (after the existing `PlaidEnvironment` parameter, before `Resources:`):

```yaml
  AlphaVantageApiKey:
    Type: String
    Default: ''
    Description: Alpha Vantage API key for the stock watchlist (optional; falls back to Yahoo Finance)
    NoEcho: true
```

Add the env var under `DailyDigestFunction` → `Properties` → `Environment` → `Variables` (after `PLAID_ENVIRONMENT`):

```yaml
          ALPHA_VANTAGE_API_KEY: !Ref AlphaVantageApiKey
```

- [ ] **Step 4: Verify the SAM template parses**

Run: `npx sam validate --lint` (or `sam validate` if the SAM CLI is installed)
Expected: `template.yaml is a valid SAM Template`. If the SAM CLI is unavailable, visually confirm the YAML indentation matches the surrounding parameters/variables.

- [ ] **Step 5: Commit**

```bash
git add .env.example template.yaml
git commit -m "chore: add ALPHA_VANTAGE_API_KEY config for stock watchlist"
```

---

## Task 9: Local preview verification

**Files:** none (manual verification)

- [ ] **Step 1: Inspect how the preview script builds the email**

Run: `grep -n "buildEmailTemplate" preview-test-email.js send-test-email.js run-digest-now.js`
Expected: shows each call site. If any call `buildEmailTemplate` with positional args, the new 5th `stockData` arg is optional (defaults to `null`) so they keep working — but to preview the stock section, pass a mock or a real `await fetchStockData(process.env.ALPHA_VANTAGE_API_KEY)` result as the 5th argument in `preview-test-email.js`.

- [ ] **Step 2: Regenerate the preview and confirm the section renders**

Run: `node preview-test-email.js`
Expected: opens/writes `test-email-preview.html`. Confirm it contains a "📈 Market Watchlist" card with a `quickchart.io` image and a sorted table. (Use the unavailable-state path if no key/network: the card should read "Market data unavailable today".)

- [ ] **Step 3: Commit any preview-script change**

```bash
git add preview-test-email.js
git commit -m "chore: preview stock watchlist section in test email"
```

(Skip this commit if no preview-script change was needed.)

---

## Self-Review

**Spec coverage:**
- Fixed watchlist (SPY + Mag 7) → Task 1 ✓
- YTD return % + P/E → Tasks 1–3 ✓
- Daily series for charting → Tasks 1–3 (`series`), Task 5 (chart) ✓
- Alpha Vantage primary, Yahoo fallback → Tasks 2–3 ✓
- Rate-limit detection triggers fallback → Task 3 ✓
- Both-fail graceful degrade → Task 4 ✓
- QuickChart combined return chart → Task 5 ✓
- Section: chart + table sorted by YTD desc, unavailable state → Task 6 ✓
- Placement after Uber Eats, before Product Hunt → Task 6 ✓
- `ALPHA_VANTAGE_API_KEY` env config (.env.example, template.yaml) → Task 8 ✓
- Wiring into handler → Task 7 ✓
- Tests for fetcher, chart, template → Tasks 1–6 ✓

**Type consistency:** Holding shape `{ symbol, label, price, ytdReturnPct, peRatio, series, source }` is identical across `fetchViaAlphaVantage`, `fetchViaYahoo`, `buildReturnChartUrl` (reads `symbol`, `series[].cumulativeReturnPct`), and `buildStockSection` (reads all fields). `fetchStockData(apiKey, { delayMs })` signature consistent between Tasks 2–4 and the Task 7 call site (handler omits options → default 1500ms throttle). `buildReturnChartUrl(holdings)` and `buildEmailTemplate(..., stockData)` consistent.

**Placeholder scan:** No TBD/TODO; every code step includes full code.

**Note on `source: 'mixed'`:** the spec listed `'mixed'` as a possible value; this plan keeps it simple — `source` reflects whichever provider produced the holdings (`'alphavantage'` or `'yahoo'`). All-or-nothing per provider, so `'mixed'` is not produced. This is an intentional simplification, not a gap.
