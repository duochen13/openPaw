const axios = require('axios');
const { fetchTopProductHuntProducts } = require('../../src/fetchers/productHunt');

jest.mock('axios');

describe('Product Hunt Fetcher', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('fetches and returns top 5 products by trending score', async () => {
    const mockResponse = {
      data: {
        data: {
          posts: {
            edges: [
              { node: { id: 1, name: 'Product 1', tagline: 'Great product', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: { videoUrl: 'https://video.com/1' } } },
              { node: { id: 2, name: 'Product 2', tagline: 'Amazing tool', votesCount: 200, commentsCount: 50, url: 'https://ph.com/2', thumbnail: { videoUrl: null } } },
              { node: { id: 3, name: 'Product 3', tagline: 'Cool app', votesCount: 150, commentsCount: 100, url: 'https://ph.com/3', thumbnail: { videoUrl: 'https://video.com/3' } } },
              { node: { id: 4, name: 'Product 4', tagline: 'Best service', votesCount: 80, commentsCount: 10, url: 'https://ph.com/4', thumbnail: { videoUrl: 'https://video.com/4' } } },
              { node: { id: 5, name: 'Product 5', tagline: 'Super app', votesCount: 120, commentsCount: 30, url: 'https://ph.com/5', thumbnail: { videoUrl: 'https://video.com/5' } } },
              { node: { id: 6, name: 'Product 6', tagline: 'Nice tool', votesCount: 90, commentsCount: 15, url: 'https://ph.com/6', thumbnail: { videoUrl: null } } }
            ]
          }
        }
      }
    };

    axios.post.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result).toHaveLength(5);
    expect(result[0].name).toBe('Product 2');
    expect(result[0].trendingScore).toBe(155);
    expect(result[1].name).toBe('Product 3');
    expect(result[1].trendingScore).toBe(135);
  });

  test('calculates trending score correctly', async () => {
    const mockResponse = {
      data: {
        data: {
          posts: {
            edges: [
              { node: { id: 1, name: 'Product 1', tagline: 'Test', votesCount: 100, commentsCount: 50, url: 'https://ph.com/1', thumbnail: {} } }
            ]
          }
        }
      }
    };

    axios.post.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    const expectedScore = (100 * 0.7) + (50 * 0.3);
    expect(result[0].trendingScore).toBe(expectedScore);
  });

  test('handles API timeout and tries all fallbacks', async () => {
    axios.post.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));
    axios.post.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));
    axios.post.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));

    await expect(fetchTopProductHuntProducts('fake-api-key')).rejects.toThrow();
  });

  test('handles missing video URLs gracefully', async () => {
    const mockResponse = {
      data: {
        data: {
          posts: {
            edges: [
              { node: { id: 1, name: 'Product 1', tagline: 'Test', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: { videoUrl: null } } }
            ]
          }
        }
      }
    };

    axios.post.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result[0].videoUrl).toBeNull();
  });

  test('falls back to yesterday when today has no products', async () => {
    const emptyResponse = { data: { data: { posts: { edges: [] } } } };
    const yesterdayResponse = {
      data: {
        data: {
          posts: {
            edges: [
              { node: { id: 1, name: 'Yesterday Product', tagline: 'From yesterday', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: {} } }
            ]
          }
        }
      }
    };

    axios.post.mockResolvedValueOnce(emptyResponse);
    axios.post.mockResolvedValueOnce(yesterdayResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Yesterday Product');
  });

  test('falls back to last week when today and yesterday have no products', async () => {
    const emptyResponse = { data: { data: { posts: { edges: [] } } } };
    const lastWeekResponse = {
      data: {
        data: {
          posts: {
            edges: [
              { node: { id: 1, name: 'Last Week Product', tagline: 'From last week', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: {} } }
            ]
          }
        }
      }
    };

    axios.post.mockResolvedValueOnce(emptyResponse);
    axios.post.mockResolvedValueOnce(emptyResponse);
    axios.post.mockResolvedValueOnce(lastWeekResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Last Week Product');
  });

  test('throws error when all time periods have no products', async () => {
    const emptyResponse = { data: { data: { posts: { edges: [] } } } };

    axios.post.mockResolvedValueOnce(emptyResponse);
    axios.post.mockResolvedValueOnce(emptyResponse);
    axios.post.mockResolvedValueOnce(emptyResponse);

    await expect(fetchTopProductHuntProducts('fake-api-key')).rejects.toThrow('No Product Hunt products available');
  });
});
