const { Configuration, PlaidApi, PlaidEnvironments } = require('plaid');
const { DateTime } = require('luxon');
const { logger } = require('../utils/logger');

const TIMEOUT_MS = 10000;

async function fetchPlaidSpending(clientId, secret, accessToken, environment) {
  try {
    // Initialize Plaid client
    const configuration = new Configuration({
      basePath: PlaidEnvironments[environment],
      baseOptions: {
        headers: {
          'PLAID-CLIENT-ID': clientId,
          'PLAID-SECRET': secret,
        },
      },
    });

    const client = new PlaidApi(configuration);

    // Calculate yesterday's date range in Pacific Time
    const timezone = 'America/Los_Angeles';
    const now = DateTime.now().setZone(timezone);
    const yesterday = now.minus({ days: 1 });
    const startDate = yesterday.toFormat('yyyy-MM-dd');
    const endDate = yesterday.toFormat('yyyy-MM-dd');

    // Fetch transactions
    const response = await Promise.race([
      client.transactionsGet({
        access_token: accessToken,
        start_date: startDate,
        end_date: endDate,
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), TIMEOUT_MS)
      ),
    ]);

    const transactions = response.data.transactions;

    // Filter to yesterday only (double-check timezone)
    const yesterdayTransactions = transactions.filter(t => t.date === startDate);

    // Transform transactions
    const transformed = yesterdayTransactions.map(t => ({
      merchant: t.name,
      amount: t.amount,
      date: t.date,
      category: mapCategory(t.category)
    }));

    // Calculate total
    const total = transformed.reduce((sum, t) => sum + t.amount, 0);

    // Sort by amount descending and take top 3
    const sorted = transformed.sort((a, b) => b.amount - a.amount);
    const top3 = sorted.slice(0, 3);

    logger.info('Plaid spending fetched', {
      transactionCount: top3.length,
      total: total,
      dateRange: { start: startDate, end: endDate }
    });

    return {
      total: Math.round(total * 100) / 100,
      transactions: top3
    };

  } catch (error) {
    logger.error('Plaid API failed', {
      error: error.message,
      code: error.code
    });
    return { total: 0, transactions: [] };
  }
}

function mapCategory(categories) {
  if (!categories || categories.length === 0) return 'Other';

  const primary = categories[0];

  if (primary.includes('Food and Drink')) return 'Dining';
  if (primary.includes('Shops')) return 'Shopping';
  if (primary.includes('Travel')) return 'Transport';
  if (primary.includes('Recreation')) return 'Entertainment';

  return 'Other';
}

module.exports = { fetchPlaidSpending };
