#!/usr/bin/env node

/**
 * Test fetching most recent transactions instead of strictly yesterday
 * This works better for Plaid sandbox
 */

const { Configuration, PlaidApi, PlaidEnvironments } = require('plaid');
const { DateTime } = require('luxon');

const CLIENT_ID = '6a1e7548b033d9000d7b75fd';
const SECRET = 'c6a87f97d2e2c9042eaafe0cef76a7';
const ACCESS_TOKEN = 'access-sandbox-ff2be822-81eb-4621-b5f0-d09f915dffd1';

async function testMostRecent() {
  try {
    const configuration = new Configuration({
      basePath: PlaidEnvironments.sandbox,
      baseOptions: {
        headers: {
          'PLAID-CLIENT-ID': CLIENT_ID,
          'PLAID-SECRET': SECRET,
        },
      },
    });

    const client = new PlaidApi(configuration);

    console.log('📊 Fetching most recent transactions...\n');

    // Get last 30 days
    const endDate = DateTime.now().setZone('America/Los_Angeles').toFormat('yyyy-MM-dd');
    const startDate = DateTime.now().setZone('America/Los_Angeles').minus({ days: 30 }).toFormat('yyyy-MM-dd');

    const response = await client.transactionsGet({
      access_token: ACCESS_TOKEN,
      start_date: startDate,
      end_date: endDate
    });

    const transactions = response.data.transactions;

    if (transactions.length === 0) {
      console.log('❌ No transactions available');
      return;
    }

    // Find the most recent date
    const dates = transactions.map(t => t.date).sort().reverse();
    const mostRecentDate = dates[0];

    // Get transactions from that date
    const recentTx = transactions.filter(t => t.date === mostRecentDate);

    console.log(`✅ Most recent transaction date: ${mostRecentDate}`);
    console.log(`   Transactions on that date: ${recentTx.length}\n`);

    // Sort by amount descending, take top 3
    const sorted = [...recentTx].sort((a, b) => b.amount - a.amount);
    const top3 = sorted.slice(0, 3);

    console.log('💰 Top 3 transactions:');
    top3.forEach((t, i) => {
      console.log(`   ${i + 1}. ${t.name}: $${t.amount.toFixed(2)} (${t.category?.[0] || 'Other'})`);
    });

    const total = top3.reduce((sum, t) => sum + t.amount, 0);
    console.log(`\n   Total: $${total.toFixed(2)}\n`);

    console.log('📧 This would show in email as:');
    console.log(`   "${mostRecentDate}'s Spending: $${total.toFixed(2)}"`);
    console.log('   Or just show without specific date\n');

  } catch (error) {
    console.error('❌ Error:', error.response?.data || error.message);
  }
}

testMostRecent();
