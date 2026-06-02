const { handler } = require('../src/index');
const { fetchTopProductHuntProducts } = require('../src/fetchers/productHunt');
const { fetchTopHackerNewsStories } = require('../src/fetchers/hackerNews');
const { fetchPlaidSpending } = require('../src/fetchers/plaid');
const { buildEmailTemplate } = require('../src/email/template');
const { sendEmail } = require('../src/gmail/client');
const { getSecret } = require('../src/utils/secrets');
const { DateTime } = require('luxon');

jest.mock('../src/fetchers/productHunt');
jest.mock('../src/fetchers/hackerNews');
jest.mock('../src/fetchers/plaid');
jest.mock('../src/email/template');
jest.mock('../src/gmail/client');
jest.mock('../src/utils/secrets');
jest.mock('luxon', () => {
  const actual = jest.requireActual('luxon');
  return {
    ...actual,
    DateTime: {
      ...actual.DateTime,
      now: jest.fn()
    }
  };
});

describe('Lambda Handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    process.env.GMAIL_CLIENT_ID = 'client-id';
    process.env.GMAIL_CLIENT_SECRET_ARN = 'arn:secret1';
    process.env.GMAIL_REFRESH_TOKEN_ARN = 'arn:secret2';
    process.env.RECIPIENT_EMAIL = 'test@example.com';
    process.env.PRODUCT_HUNT_API_KEY_ARN = 'arn:secret3';
    process.env.PRODUCT_HUNT_API_SECRET_ARN = 'arn:secret4';
    process.env.PLAID_CLIENT_ID_ARN = 'arn:secret5';
    process.env.PLAID_SECRET_ARN = 'arn:secret6';
    process.env.PLAID_ACCESS_TOKEN_ARN = 'arn:secret7';
    process.env.PLAID_ENVIRONMENT = 'sandbox';
    process.env.TIMEZONE = 'America/Los_Angeles';

    DateTime.now.mockReturnValue({
      setZone: jest.fn().mockReturnValue({
        hour: 10,
        minute: 0
      })
    });

    getSecret
      .mockResolvedValueOnce('client-secret')
      .mockResolvedValueOnce('refresh-token')
      .mockResolvedValueOnce('ph-api-key')
      .mockResolvedValueOnce('ph-api-secret')
      .mockResolvedValueOnce('plaid-client-id')
      .mockResolvedValueOnce('plaid-secret')
      .mockResolvedValueOnce('plaid-access-token');
  });

  test('executes successfully when in time window', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];
    const mockHNStories = [{ id: 101, title: 'Story 1' }];
    const mockSpending = { total: 150.75, transactions: [{ id: 't1', amount: 150.75 }] };

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    fetchPlaidSpending.mockResolvedValueOnce(mockSpending);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(fetchTopProductHuntProducts).toHaveBeenCalledWith('ph-api-key', 'ph-api-secret');
    expect(fetchTopHackerNewsStories).toHaveBeenCalled();
    expect(fetchPlaidSpending).toHaveBeenCalledWith('plaid-client-id', 'plaid-secret', 'plaid-access-token', 'sandbox');
    expect(buildEmailTemplate).toHaveBeenCalledWith(mockPHProducts, mockHNStories, mockSpending);
    expect(sendEmail).toHaveBeenCalled();
  });

  test('skips execution when outside time window', async () => {
    DateTime.now.mockReturnValue({
      setZone: jest.fn().mockReturnValue({
        hour: 14,
        minute: 30
      })
    });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(result.body).toContain('Outside execution window');
    expect(fetchTopProductHuntProducts).not.toHaveBeenCalled();
  });

  test('handles Product Hunt API failure gracefully', async () => {
    const mockHNStories = [{ id: 101, title: 'Story 1' }];
    const mockSpending = { total: 150.75, transactions: [{ id: 't1', amount: 150.75 }] };

    fetchTopProductHuntProducts.mockRejectedValueOnce(new Error('PH API failed'));
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    fetchPlaidSpending.mockResolvedValueOnce(mockSpending);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(buildEmailTemplate).toHaveBeenCalledWith([], mockHNStories, mockSpending);
  });

  test('handles Hacker News API failure gracefully', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];
    const mockSpending = { total: 150.75, transactions: [{ id: 't1', amount: 150.75 }] };

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockRejectedValueOnce(new Error('HN API failed'));
    fetchPlaidSpending.mockResolvedValueOnce(mockSpending);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(buildEmailTemplate).toHaveBeenCalledWith(mockPHProducts, [], mockSpending);
  });

  test('throws error when all data sources fail', async () => {
    fetchTopProductHuntProducts.mockRejectedValueOnce(new Error('PH failed'));
    fetchTopHackerNewsStories.mockRejectedValueOnce(new Error('HN failed'));
    fetchPlaidSpending.mockRejectedValueOnce(new Error('Plaid failed'));

    await expect(handler({})).rejects.toThrow('All data sources failed');
  });

  test('throws error when Gmail send fails', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];
    const mockHNStories = [{ id: 101, title: 'Story 1' }];
    const mockSpending = { total: 150.75, transactions: [{ id: 't1', amount: 150.75 }] };

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    fetchPlaidSpending.mockResolvedValueOnce(mockSpending);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockRejectedValueOnce(new Error('Send failed'));

    await expect(handler({})).rejects.toThrow('Send failed');
  });

  test('handles Plaid API failure gracefully', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];
    const mockHNStories = [{ id: 101, title: 'Story 1' }];

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    fetchPlaidSpending.mockRejectedValueOnce(new Error('Plaid API failed'));
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(buildEmailTemplate).toHaveBeenCalledWith(mockPHProducts, mockHNStories, { total: 0, transactions: [] });
  });
});
