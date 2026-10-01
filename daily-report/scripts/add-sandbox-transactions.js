#!/usr/bin/env node

/**
 * Add test transactions to Plaid sandbox account
 */

const { Configuration, PlaidApi, PlaidEnvironments } = require('plaid');
const { DateTime } = require('luxon');

// Sandbox credentials come from the environment — never hardcode secrets here (this repo is public).
// See daily-report/.env.example for the variable names.
const CLIENT_ID = process.env.PLAID_CLIENT_ID;
const SECRET = process.env.PLAID_SECRET;
const ACCESS_TOKEN = process.env.PLAID_ACCESS_TOKEN;

if (!CLIENT_ID || !SECRET || !ACCESS_TOKEN) {
  console.error('Missing Plaid sandbox credentials. Set PLAID_CLIENT_ID, PLAID_SECRET and PLAID_ACCESS_TOKEN env vars (see daily-report/.env.example).');
  process.exit(1);
} // Current deployed token

async function addTestTransactions() {
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

    console.log('🧪 Adding test transactions to sandbox...\n');

    // Get yesterday's date in Pacific Time
    const yesterday = DateTime.now().setZone('America/Los_Angeles').minus({ days: 1 });
    const dateStr = yesterday.toFormat('yyyy-MM-dd');

    // Use Plaid's sandbox endpoint to reset and add test transactions
    const response = await client.sandboxItemResetLogin({
      access_token: ACCESS_TOKEN
    });

    console.log('✓ Sandbox item reset (simulates new login)\n');

    // Now check what transactions we have
    const txResponse = await client.transactionsGet({
      access_token: ACCESS_TOKEN,
      start_date: yesterday.minus({ days: 30 }).toFormat('yyyy-MM-dd'),
      end_date: DateTime.now().setZone('America/Los_Angeles').toFormat('yyyy-MM-dd')
    });

    console.log(`📊 Current transactions: ${txResponse.data.transactions.length}\n`);

    if (txResponse.data.transactions.length > 0) {
      console.log('Sample transactions:');
      txResponse.data.transactions.slice(0, 5).forEach(t => {
        console.log(`  • ${t.date}: ${t.name} - $${t.amount}`);
      });
    } else {
      console.log('⚠️  No transactions yet. Sandbox may take a moment to populate.');
      console.log('\nPlaid Sandbox Note:');
      console.log('  The Chase sandbox institution generates default test transactions,');
      console.log('  but they may not appear immediately. Try these options:\n');
      console.log('  1. Wait 1-2 minutes and check again');
      console.log('  2. Use sandboxItemFireWebhook to trigger transaction updates');
      console.log('  3. Create a new sandbox item with explicit test data\n');
    }

    console.log('\n💡 To get guaranteed test data, use Plaid Link with:');
    console.log('   Username: user_good');
    console.log('   Password: pass_good');
    console.log('   This generates consistent test transactions.\n');

  } catch (error) {
    console.error('❌ Error:', error.response?.data || error.message);
  }
}

addTestTransactions();
