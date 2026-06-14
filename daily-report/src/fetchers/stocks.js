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
