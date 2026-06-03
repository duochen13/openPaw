#!/usr/bin/env node

/**
 * Create a new Plaid sandbox connection with test transactions
 * This uses Plaid's test institution that comes pre-populated with data
 */

const { Configuration, PlaidApi, PlaidEnvironments, Products, CountryCode } = require('plaid');
const { DateTime } = require('luxon');

const CLIENT_ID = '6a1e7548b033d9000d7b75fd';
const SECRET = 'c6a87f97d2e2c9042eaafe0cef76a7';

async function createWithTransactions() {
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

    console.log('🏦 Creating Plaid sandbox connection with test transactions...\n');

    // Use First Platypus Bank - it has rich test data
    const sandboxResponse = await client.sandboxPublicTokenCreate({
      institution_id: 'ins_109508', // Chase (reliable test data)
      initial_products: [Products.Transactions],
      options: {
        webhook: null,
        override_username: 'user_good', // This ensures good test data
        override_password: 'pass_good'
      }
    });

    const publicToken = sandboxResponse.data.public_token;
    console.log('✓ Created sandbox item with test data\n');

    // Exchange for access token
    const exchangeResponse = await client.itemPublicTokenExchange({
      public_token: publicToken,
    });

    const accessToken = exchangeResponse.data.access_token;
    const itemId = exchangeResponse.data.item_id;

    console.log('✅ New access token created:\n');
    console.log(accessToken);
    console.log(`\nItem ID: ${itemId}\n`);

    // Fetch transactions to verify
    console.log('📊 Fetching transactions to verify...\n');

    const yesterday = DateTime.now().setZone('America/Los_Angeles').minus({ days: 1 });
    const startDate = yesterday.minus({ days: 30 }).toFormat('yyyy-MM-dd');
    const endDate = DateTime.now().setZone('America/Los_Angeles').toFormat('yyyy-MM-dd');

    const txResponse = await client.transactionsGet({
      access_token: accessToken,
      start_date: startDate,
      end_date: endDate
    });

    const transactions = txResponse.data.transactions;
    const yesterdayDate = yesterday.toFormat('yyyy-MM-dd');
    const yesterdayTx = transactions.filter(t => t.date === yesterdayDate);

    console.log(`Total transactions (last 30 days): ${transactions.length}`);
    console.log(`Yesterday's transactions: ${yesterdayTx.length}\n`);

    if (yesterdayTx.length > 0) {
      console.log(`Yesterday's spending (${yesterdayDate}):`);
      yesterdayTx.forEach(t => {
        console.log(`  • ${t.name}: $${t.amount}`);
      });
      const total = yesterdayTx.reduce((sum, t) => sum + t.amount, 0);
      console.log(`  Total: $${total.toFixed(2)}\n`);
    } else {
      console.log(`⚠️  No transactions for ${yesterdayDate}`);
      console.log('\nShowing most recent transactions instead:');
      transactions.slice(0, 5).forEach(t => {
        console.log(`  • ${t.date}: ${t.name} - $${t.amount}`);
      });
      console.log('\n💡 Sandbox transactions are auto-generated with random dates.');
      console.log('   They may not match yesterday exactly.\n');
    }

    console.log('📋 Next steps:');
    console.log('1. Copy the access token above');
    console.log('2. Update AWS secret: node scripts/update-plaid-token.js');
    console.log('3. Test the Lambda again\n');

  } catch (error) {
    console.error('❌ Error:', error.response?.data || error.message);
  }
}

createWithTransactions();
