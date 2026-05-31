const axios = require('axios');
const { fetchTopHackerNewsStories } = require('../../src/fetchers/hackerNews');

jest.mock('axios');

describe('Hacker News Fetcher', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('fetches and returns top 5 stories sorted by points', async () => {
    axios.get.mockResolvedValueOnce({
      data: [101, 102, 103, 104, 105, 106, 107]
    });

    axios.get
      .mockResolvedValueOnce({ data: { id: 101, title: 'Story 1', url: 'http://example.com/1', score: 500, descendants: 50 } })
      .mockResolvedValueOnce({ data: { id: 102, title: 'Story 2', url: 'http://example.com/2', score: 800, descendants: 100 } })
      .mockResolvedValueOnce({ data: { id: 103, title: 'Story 3', url: 'http://example.com/3', score: 300, descendants: 25 } })
      .mockResolvedValueOnce({ data: { id: 104, title: 'Story 4', url: 'http://example.com/4', score: 600, descendants: 75 } })
      .mockResolvedValueOnce({ data: { id: 105, title: 'Story 5', url: 'http://example.com/5', score: 400, descendants: 30 } })
      .mockResolvedValueOnce({ data: { id: 106, title: 'Story 6', url: 'http://example.com/6', score: 200, descendants: 10 } })
      .mockResolvedValueOnce({ data: { id: 107, title: 'Story 7', url: 'http://example.com/7', score: 700, descendants: 90 } });

    const result = await fetchTopHackerNewsStories();

    expect(result).toHaveLength(5);
    expect(result[0].title).toBe('Story 2');
    expect(result[0].points).toBe(800);
    expect(result[1].points).toBe(700);
    expect(result[2].points).toBe(600);
    expect(result[3].points).toBe(500);
    expect(result[4].points).toBe(400);
  });

  test('handles API timeout', async () => {
    axios.get.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));

    await expect(fetchTopHackerNewsStories()).rejects.toThrow('timeout');
  });

  test('returns empty array when no stories available', async () => {
    axios.get.mockResolvedValueOnce({ data: [] });

    const result = await fetchTopHackerNewsStories();

    expect(result).toEqual([]);
  });

  test('skips malformed story items', async () => {
    axios.get.mockResolvedValueOnce({
      data: [101, 102, 103]
    });

    axios.get
      .mockResolvedValueOnce({ data: { id: 101, title: 'Story 1', url: 'http://example.com/1', score: 500, descendants: 50 } })
      .mockResolvedValueOnce({ data: null })
      .mockResolvedValueOnce({ data: { id: 103, title: 'Story 3', url: 'http://example.com/3', score: 300, descendants: 25 } });

    const result = await fetchTopHackerNewsStories();

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe(101);
    expect(result[1].id).toBe(103);
  });
});
