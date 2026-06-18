const axios = require('axios');
const {
  WATCHLIST,
  buildSeriesAndReturn,
  downsample,
  fetchStockData
} = require('../../src/fetchers/stocks');

jest.mock('axios');

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

  test('buildSeriesAndReturn returns null when base price is zero', () => {
    expect(buildSeriesAndReturn([{ date: '2026-01-02', close: 0 }, { date: '2026-01-03', close: 5 }])).toBeNull();
  });

  test('buildSeriesAndReturn preserves all series points', () => {
    const built = buildSeriesAndReturn([
      { date: '2026-01-02', close: 100 },
      { date: '2026-01-03', close: 110 },
      { date: '2026-01-06', close: 90 }
    ]);
    expect(built.series).toHaveLength(3);
  });
});

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
    expect(result.holdings[result.holdings.length - 1].symbol).toBe('SPY');
    const spy = result.holdings.find(h => h.symbol === 'SPY');
    expect(spy.ytdReturnPct).toBeCloseTo(10, 5);
    expect(spy.price).toBe(110);
    expect(spy.peRatio).toBeNull();
    expect(spy.series.length).toBeGreaterThan(0);
    const aapl = result.holdings.find(h => h.symbol === 'AAPL');
    expect(aapl.peRatio).toBeCloseTo(30.5, 5);
    expect(aapl.source).toBe('alphavantage');
  });
});

describe('fetchStockData — Yahoo fallback', () => {
  test('falls back to Yahoo when Alpha Vantage is rate-limited', async () => {
    axios.get.mockImplementation((url, config) => {
      if (url === 'https://www.alphavantage.co/query') {
        return Promise.resolve({ data: { Note: 'Thank you for using Alpha Vantage! 25 requests/day reached.' } });
      }
      // Yahoo P/E crumb handshake: cookie seed -> crumb -> quote
      if (url === 'https://fc.yahoo.com') {
        return Promise.resolve({ headers: { 'set-cookie': ['A1=token; Path=/; Domain=.yahoo.com'] }, data: '' });
      }
      if (url === 'https://query1.finance.yahoo.com/v1/test/getcrumb') {
        return Promise.resolve({ data: 'testCrumb123' });
      }
      if (url === 'https://query1.finance.yahoo.com/v7/finance/quote') {
        return Promise.resolve({
          data: { quoteResponse: { result: [{ symbol: 'AAPL', trailingPE: 28.2 }] } }
        });
      }
      return Promise.resolve({
        data: {
          chart: {
            result: [{
              timestamp: [1735819200, 1749700800],
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
    expect(aapl.ytdReturnPct).toBeCloseTo(25, 5);
    const spy = result.holdings.find(h => h.symbol === 'SPY');
    expect(spy.peRatio).toBeNull();
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
