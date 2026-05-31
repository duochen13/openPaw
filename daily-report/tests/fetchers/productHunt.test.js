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
        posts: [
          { id: 1, name: 'Product 1', tagline: 'Great product', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: { videoUrl: 'https://video.com/1' } },
          { id: 2, name: 'Product 2', tagline: 'Amazing tool', votesCount: 200, commentsCount: 50, url: 'https://ph.com/2', thumbnail: { videoUrl: null } },
          { id: 3, name: 'Product 3', tagline: 'Cool app', votesCount: 150, commentsCount: 100, url: 'https://ph.com/3', thumbnail: { videoUrl: 'https://video.com/3' } },
          { id: 4, name: 'Product 4', tagline: 'Best service', votesCount: 80, commentsCount: 10, url: 'https://ph.com/4', thumbnail: { videoUrl: 'https://video.com/4' } },
          { id: 5, name: 'Product 5', tagline: 'Super app', votesCount: 120, commentsCount: 30, url: 'https://ph.com/5', thumbnail: { videoUrl: 'https://video.com/5' } },
          { id: 6, name: 'Product 6', tagline: 'Nice tool', votesCount: 90, commentsCount: 15, url: 'https://ph.com/6', thumbnail: { videoUrl: null } }
        ]
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
        posts: [
          { id: 1, name: 'Product 1', tagline: 'Test', votesCount: 100, commentsCount: 50, url: 'https://ph.com/1', thumbnail: {} }
        ]
      }
    };

    axios.post.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    const expectedScore = (100 * 0.7) + (50 * 0.3);
    expect(result[0].trendingScore).toBe(expectedScore);
  });

  test('handles API timeout', async () => {
    axios.post.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));

    await expect(fetchTopProductHuntProducts('fake-api-key')).rejects.toThrow('timeout');
  });

  test('handles missing video URLs gracefully', async () => {
    const mockResponse = {
      data: {
        posts: [
          { id: 1, name: 'Product 1', tagline: 'Test', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: { videoUrl: null } }
        ]
      }
    };

    axios.post.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result[0].videoUrl).toBeNull();
  });

  test('returns empty array when no products available', async () => {
    axios.post.mockResolvedValueOnce({ data: { posts: [] } });

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result).toEqual([]);
  });
});
