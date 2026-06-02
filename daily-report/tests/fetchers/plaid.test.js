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
});
