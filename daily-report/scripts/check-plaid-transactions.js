#!/usr/bin/env node

/**
 * Check transactions for a Plaid access token
 */

const { Configuration, PlaidApi, PlaidEnvironments } = require('plaid');
const { DateTime } = require('luxon');

const CLIENT_ID = '6a1e7548b033d9000d7b75fd';
const SECRET = 'c6a87f97d2e2c9042eaafe0cef76a7';

const accessToken = process.argv[2] || 'access-sandbox-ff2be822-81eb-4621-b5f0-d09f915dffd1';

async function checkTransactions() {
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

    console.log('📊 Checking Plaid transactions...\n');
    console.log(`Token: ${accessToken.substring(0, 30)}...\n`);

    const yesterday = DateTime.now().setZone('America/Los_Angeles').minus({ days: 1 });
    const startDate = yesterday.minus({ days: 30 }).toFormat('yyyy-MM-dd');
    const endDate = DateTime.now().setZone('America/Los_Angeles').toFormat('yyyy-MM-dd');

    const response = await client.transactionsGet({
      access_token: accessToken,
      start_date: startDate,
      end_date: endDate
    });

    const transactions = response.data.transactions;
    const yesterdayDate = yesterday.toFormat('yyyy-MM-dd');
    const yesterdayTx = transactions.filter(t => t.date === yesterdayDate);

    console.log(`✅ Total transactions (last 30 days): ${transactions.length}`);
    console.log(`   Yesterday's date: ${yesterdayDate}`);
    console.log(`   Yesterday's transactions: ${yesterdayTx.length}\n`);

    if (yesterdayTx.length > 0) {
      console.log(`💰 Yesterday's spending:`);
      const sorted = [...yesterdayTx].sort((a, b) => b.amount - a.amount);
      sorted.forEach(t => {
        console.log(`   • ${t.name}: $${t.amount.toFixed(2)} (${t.category?.[0] || 'Other'})`);
      });
      const total = yesterdayTx.reduce((sum, t) => sum + t.amount, 0);
      console.log(`   \n   Total: $${total.toFixed(2)}\n`);
    } else {
      console.log(`⚠️  No transactions for yesterday (${yesterdayDate})\n`);

      if (transactions.length > 0) {
        console.log('📅 Available transaction dates:');
        const dates = [...new Set(transactions.map(t => t.date))].sort().reverse();
        dates.slice(0, 10).forEach(date => {
          const count = transactions.filter(t => t.date === date).length;
          console.log(`   • ${date}: ${count} transactions`);
        });
        console.log('\n💡 Sandbox transactions may not have yesterday\'s date.');
      } else {
        console.log('❌ No transactions found at all.');
        console.log('\nThis could mean:');
        console.log('  1. Product is still initializing (wait 1-2 minutes)');
        console.log('  2. This is a fresh sandbox item with no data\n');
      }
    }

  } catch (error) {
    if (error.response?.data?.error_code === 'PRODUCT_NOT_READY') {
      console.error('⏳ Transactions product not ready yet.');
      console.error('   Wait 30-60 seconds and try again.\n');
    } else {
      console.error('❌ Error:', error.response?.data || error.message);
    }
  }
}

checkTransactions();
