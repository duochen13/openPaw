#!/usr/bin/env node

/**
 * Switch Plaid environment in Lambda (sandbox → development → production)
 */

const { LambdaClient, UpdateFunctionConfigurationCommand, GetFunctionConfigurationCommand } = require('@aws-sdk/client-lambda');
const readline = require('readline');

const FUNCTION_NAME = 'openpaw-daily-digest';
const REGION = 'us-east-1';

const client = new LambdaClient({ region: REGION });

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(query) {
  return new Promise(resolve => rl.question(query, resolve));
}

async function switchEnvironment() {
  try {
    console.log('🔄 Switch Plaid Environment\n');

    // Get current config
    const getCommand = new GetFunctionConfigurationCommand({
      FunctionName: FUNCTION_NAME
    });
    const current = await client.send(getCommand);

    const currentEnv = current.Environment.Variables.PLAID_ENVIRONMENT || 'sandbox';
    console.log(`Current environment: ${currentEnv}\n`);

    console.log('Choose new environment:\n');
    console.log('1. sandbox   (Test data, no real bank)');
    console.log('2. development   (Real bank, up to 100 accounts, FREE)');
    console.log('3. production   (Real bank, unlimited, requires approval)\n');

    const choice = await question('Enter choice (1, 2, or 3): ');

    let newEnv;
    switch (choice.trim()) {
      case '1':
        newEnv = 'sandbox';
        break;
      case '2':
        newEnv = 'development';
        break;
      case '3':
        newEnv = 'production';
        break;
      default:
        console.error('❌ Invalid choice');
        rl.close();
        process.exit(1);
    }

    if (newEnv === currentEnv) {
      console.log(`\n✓ Already using ${newEnv}`);
      rl.close();
      return;
    }

    console.log(`\n⏳ Switching from ${currentEnv} to ${newEnv}...`);

    // Update environment variable
    const updateCommand = new UpdateFunctionConfigurationCommand({
      FunctionName: FUNCTION_NAME,
      Environment: {
        Variables: {
          ...current.Environment.Variables,
          PLAID_ENVIRONMENT: newEnv
        }
      }
    });

    await client.send(updateCommand);

    console.log(`✅ Switched to ${newEnv}!\n`);

    console.log('⚠️  Important:\n');
    console.log(`1. Make sure your access token is for ${newEnv}`);
    console.log(`2. If switching to ${newEnv}, you need:`);
    console.log(`   - ${newEnv} secret (update if needed)`);
    console.log(`   - ${newEnv} access token (from real bank link)`);
    console.log('');
    console.log('3. Test the Lambda:');
    console.log('   node scripts/test-lambda.js\n');

    rl.close();

  } catch (error) {
    console.error('❌ Update failed:', error.message);

    if (error.message.includes('update is in progress')) {
      console.error('\n⏳ Lambda is still processing. Wait 10-20 seconds and try again.');
    }

    rl.close();
    process.exit(1);
  }
}

switchEnvironment();
