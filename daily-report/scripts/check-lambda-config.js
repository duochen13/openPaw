#!/usr/bin/env node

/**
 * Check Lambda function configuration
 */

const { LambdaClient, GetFunctionConfigurationCommand } = require('@aws-sdk/client-lambda');

const FUNCTION_NAME = 'openpaw-daily-digest';
const REGION = 'us-east-1';

const client = new LambdaClient({ region: REGION });

async function checkConfig() {
  try {
    const command = new GetFunctionConfigurationCommand({
      FunctionName: FUNCTION_NAME
    });

    const response = await client.send(command);

    console.log('📋 Lambda Configuration:\n');
    console.log('Function:', response.FunctionName);
    console.log('Runtime:', response.Runtime);
    console.log('Handler:', response.Handler);
    console.log('\n🔧 Environment Variables:');

    const vars = response.Environment.Variables;
    const keys = Object.keys(vars).sort();

    keys.forEach(key => {
      const value = vars[key];
      if (key.includes('ARN')) {
        console.log(`  ${key}: ${value}`);
      } else if (key === 'GMAIL_CLIENT_ID') {
        console.log(`  ${key}: ${value.substring(0, 20)}... (${value.length} chars)`);
      } else if (key === 'RECIPIENT_EMAIL') {
        console.log(`  ${key}: ${value}`);
      } else {
        console.log(`  ${key}: ${value}`);
      }
    });

    if (!vars.GMAIL_CLIENT_ID || vars.GMAIL_CLIENT_ID === '') {
      console.log('\n⚠️  WARNING: GMAIL_CLIENT_ID is empty!');
      console.log('You need to set it for Gmail to work.');
    }

    if (!vars.RECIPIENT_EMAIL || vars.RECIPIENT_EMAIL === '') {
      console.log('\n⚠️  WARNING: RECIPIENT_EMAIL is empty!');
      console.log('You need to set it to receive emails.');
    }

  } catch (error) {
    console.error('❌ Failed:', error.message);
    process.exit(1);
  }
}

checkConfig();
