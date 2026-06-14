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
