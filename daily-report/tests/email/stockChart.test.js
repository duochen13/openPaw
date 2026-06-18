const { buildPeBarChartUrl } = require('../../src/email/stockChart');

describe('buildPeBarChartUrl', () => {
  const holdings = [
    { symbol: 'NVDA', peRatio: 55.2 },
    { symbol: 'AAPL', peRatio: 31.8 },
    { symbol: 'SPY', peRatio: null }
  ];

  test('returns a QuickChart bar-chart URL with one bar per holding that has a P/E', () => {
    const url = buildPeBarChartUrl(holdings);
    expect(url).toContain('https://quickchart.io/chart?');
    const config = JSON.parse(decodeURIComponent(url.split('c=')[1]));
    expect(config.type).toBe('bar');
    // SPY (null P/E) is excluded; NVDA + AAPL remain.
    expect(config.data.labels).toEqual(['NVDA', 'AAPL']);
    expect(config.data.datasets).toHaveLength(1);
    expect(config.data.datasets[0].data).toEqual([55.2, 31.8]);
  });

  test('returns null when no holding has a usable P/E', () => {
    expect(buildPeBarChartUrl([{ symbol: 'SPY', peRatio: null }])).toBeNull();
    expect(buildPeBarChartUrl([{ symbol: 'SPY' }])).toBeNull();
    expect(buildPeBarChartUrl([])).toBeNull();
  });
});
