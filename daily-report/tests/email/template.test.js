const { buildEmailTemplate } = require('../../src/email/template');

describe('Email Template Builder', () => {
  const mockPHProducts = [
    {
      id: 1,
      name: 'Product 1',
      tagline: 'Great product',
      upvotes: 100,
      comments: 20,
      url: 'https://ph.com/1',
      videoUrl: 'https://video.com/1.mp4'
    },
    {
      id: 2,
      name: 'Product 2',
      tagline: 'Amazing tool',
      upvotes: 200,
      comments: 50,
      url: 'https://ph.com/2',
      videoUrl: null
    }
  ];

  const mockHNStories = [
    {
      id: 101,
      title: 'Story 1',
      url: 'https://example.com/1',
      points: 500,
      comments: 50
    },
    {
      id: 102,
      title: 'Story 2',
      url: 'https://example.com/2',
      points: 300,
      comments: 25
    }
  ];

  test('builds complete HTML email', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<html');
    expect(html).toContain('</html>');
  });

  test('includes Product Hunt section', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('Product Hunt');
    expect(html).toContain('Product 1');
    expect(html).toContain('Great product');
  });

  test('includes Hacker News section', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('Hacker News');
    expect(html).toContain('Story 1');
    expect(html).toContain('500 points');
  });

  test('embeds video when videoUrl is provided', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('<video');
    expect(html).toContain('https://video.com/1.mp4');
  });

  test('shows link only when no video URL', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('Product 2');
    expect(html).not.toContain('https://video.com/2.mp4');
  });

  test('handles empty Product Hunt data', () => {
    const html = buildEmailTemplate([], mockHNStories);

    expect(html).toContain('Product Hunt data unavailable today');
  });

  test('handles empty Hacker News data', () => {
    const html = buildEmailTemplate(mockPHProducts, []);

    expect(html).toContain('Hacker News data unavailable today');
  });

  test('includes current date in header', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    const today = new Date().toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    });

    expect(html).toContain(today);
  });

  test('includes daily joke section', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain("Today's Tech Joke");
    expect(html).toContain('😄');
  });

  test('joke section appears before Product Hunt', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    const jokeIndex = html.indexOf("Today's Tech Joke");
    const phIndex = html.indexOf('Product Hunt');

    expect(jokeIndex).toBeGreaterThan(-1);
    expect(phIndex).toBeGreaterThan(-1);
    expect(jokeIndex).toBeLessThan(phIndex);
  });

  describe('Spending Summary Section', () => {
    const mockSpendingData = {
      total: 87.43,
      transactions: [
        { merchant: 'Amazon.com', amount: 39.93, date: '2026-05-31', category: 'Shopping' },
        { merchant: 'Chipotle', amount: 18.50, date: '2026-05-31', category: 'Dining' },
        { merchant: 'Starbucks', amount: 14.00, date: '2026-05-31', category: 'Dining' }
      ]
    };

    test('includes spending section when data available', () => {
      const html = buildEmailTemplate(mockPHProducts, mockHNStories, mockSpendingData);

      expect(html).toContain('Yesterday\'s Spending');
      expect(html).toContain('$87.43');
      expect(html).toContain('Amazon.com');
      expect(html).toContain('$39.93');
    });

    test('shows fallback message when no transactions', () => {
      const emptySpending = { total: 0, transactions: [] };
      const html = buildEmailTemplate(mockPHProducts, mockHNStories, emptySpending);

      expect(html).toContain('Yesterday\'s Spending');
      expect(html).toContain('Spending data unavailable for yesterday');
    });

    test('spending section appears after joke and before Product Hunt', () => {
      const html = buildEmailTemplate(mockPHProducts, mockHNStories, mockSpendingData);

      const jokeIndex = html.indexOf('Today\'s Tech Joke');
      const spendingIndex = html.indexOf('Yesterday\'s Spending');
      const phIndex = html.indexOf('🚀 Product Hunt');

      expect(jokeIndex).toBeGreaterThan(-1);
      expect(spendingIndex).toBeGreaterThan(-1);
      expect(phIndex).toBeGreaterThan(-1);
      expect(jokeIndex).toBeLessThan(spendingIndex);
      expect(spendingIndex).toBeLessThan(phIndex);
    });
  });

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
});
