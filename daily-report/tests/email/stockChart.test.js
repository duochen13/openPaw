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
