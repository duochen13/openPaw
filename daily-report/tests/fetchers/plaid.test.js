const { fetchPlaidSpending } = require('../../src/fetchers/plaid');
const plaid = require('plaid');

jest.mock('plaid');

describe('Plaid Spending Fetcher', () => {
  let mockPlaidClient;

  beforeEach(() => {
    jest.clearAllMocks();
    mockPlaidClient = {
      transactionsGet: jest.fn()
    };
    plaid.PlaidApi.mockImplementation(() => mockPlaidClient);
    plaid.Configuration.mockImplementation(() => ({}));
  });

  test('fetches and transforms yesterday\'s transactions', async () => {
    const mockResponse = {
      data: {
        transactions: [
          {
            transaction_id: '1',
            amount: 39.93,
            date: '2026-06-01',
            name: 'Amazon.com',
            merchant_name: 'Amazon',
            category: ['Shops', 'Digital Purchase']
          },
          {
            transaction_id: '2',
            amount: 18.50,
            date: '2026-06-01',
            name: 'Chipotle Mexican Grill',
            merchant_name: 'Chipotle',
            category: ['Food and Drink', 'Restaurants']
          },
          {
            transaction_id: '3',
            amount: 14.00,
            date: '2026-06-01',
            name: 'Starbucks',
            merchant_name: 'Starbucks',
            category: ['Food and Drink', 'Restaurants', 'Coffee Shop']
          }
        ]
      }
    };

    mockPlaidClient.transactionsGet.mockResolvedValue(mockResponse);

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result.total).toBe(72.43);
    expect(result.transactions).toHaveLength(3);
    expect(result.transactions[0]).toEqual({
      merchant: 'Amazon.com',
      amount: 39.93,
      date: '2026-06-01',
      category: 'Shopping'
    });
  });

  test('returns empty data when no transactions available', async () => {
    const mockResponse = {
      data: {
        transactions: []
      }
    };

    mockPlaidClient.transactionsGet.mockResolvedValue(mockResponse);

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result.total).toBe(0);
    expect(result.transactions).toEqual([]);
  });

  test('handles timeout gracefully', async () => {
    mockPlaidClient.transactionsGet.mockImplementation(
      () => new Promise(resolve => setTimeout(resolve, 15000))
    );

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result).toEqual({ total: 0, transactions: [] });
  }, 20000);

  test('handles authentication error gracefully', async () => {
    const error = new Error('Invalid credentials');
    error.code = 'INVALID_CREDENTIALS';
    mockPlaidClient.transactionsGet.mockRejectedValue(error);

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result).toEqual({ total: 0, transactions: [] });
  });

  test('handles network error gracefully', async () => {
    mockPlaidClient.transactionsGet.mockRejectedValue(
      new Error('Network error')
    );

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result).toEqual({ total: 0, transactions: [] });
  });

  test('returns top 3 transactions sorted by amount descending', async () => {
    const mockResponse = {
      data: {
        transactions: [
          { transaction_id: '1', amount: 15.00, date: '2026-06-01', name: 'Small', category: ['Other'] },
          { transaction_id: '2', amount: 50.00, date: '2026-06-01', name: 'Large', category: ['Other'] },
          { transaction_id: '3', amount: 10.00, date: '2026-06-01', name: 'Smallest', category: ['Other'] },
          { transaction_id: '4', amount: 35.00, date: '2026-06-01', name: 'Medium', category: ['Other'] },
          { transaction_id: '5', amount: 100.00, date: '2026-06-01', name: 'Largest', category: ['Other'] }
        ]
      }
    };

    mockPlaidClient.transactionsGet.mockResolvedValue(mockResponse);

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result.transactions).toHaveLength(3);
    expect(result.transactions[0].merchant).toBe('Largest');
    expect(result.transactions[0].amount).toBe(100.00);
    expect(result.transactions[1].merchant).toBe('Large');
    expect(result.transactions[1].amount).toBe(50.00);
    expect(result.transactions[2].merchant).toBe('Medium');
    expect(result.transactions[2].amount).toBe(35.00);
    expect(result.total).toBe(185.00);
  });
});
