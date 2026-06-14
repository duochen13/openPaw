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
  if (!base) return null;
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
  if (!series || series.length <= step) return series;
  const out = [];
  for (let i = 0; i < series.length; i += step) out.push(series[i]);
  const last = series[series.length - 1];
  if (out[out.length - 1].date !== last.date) out.push(last);
  return out;
}

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
    holdings = await fetchViaYahoo();
    source = 'yahoo';
  }

  if (holdings.length === 0) {
    return { asOf: new Date().toISOString(), holdings: [], source, error: 'No stock data available' };
  }

  holdings.sort((a, b) => b.ytdReturnPct - a.ytdReturnPct);
  return { asOf: new Date().toISOString(), holdings, source };
}

module.exports = { WATCHLIST, buildSeriesAndReturn, downsample, fetchStockData };
