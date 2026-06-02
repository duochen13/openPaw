#!/usr/bin/env node

/**
 * Update Lambda function environment variables
 * Use this if deployment script fails on config update
 */

const { LambdaClient, UpdateFunctionConfigurationCommand } = require('@aws-sdk/client-lambda');

const FUNCTION_NAME = 'openpaw-daily-digest';
const REGION = 'us-east-1';

const client = new LambdaClient({ region: REGION });

async function updateConfig() {
  try {
    console.log('⚙️  Updating Lambda environment variables...\n');

    const command = new UpdateFunctionConfigurationCommand({
      FunctionName: FUNCTION_NAME,
      Environment: {
        Variables: {
          GMAIL_CLIENT_ID: process.env.GMAIL_CLIENT_ID || '',
          GMAIL_CLIENT_SECRET_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/gmail/client-secret-hWktkd',
          GMAIL_REFRESH_TOKEN_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/gmail/refresh-token-e8EDsT',
          PRODUCT_HUNT_API_KEY_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/product-hunt/api-key-6cVJKD',
          PRODUCT_HUNT_API_SECRET_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/product-hunt/api-secret-Q8s1Mx',
          RECIPIENT_EMAIL: process.env.RECIPIENT_EMAIL || '',
          TIMEZONE: 'America/Los_Angeles',
          PLAID_CLIENT_ID_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-ChMp7v',
          PLAID_SECRET_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-mZUbAR',
          PLAID_ACCESS_TOKEN_ARN: 'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-2vtVRz',
          PLAID_ENVIRONMENT: 'sandbox'
        }
      }
    });

    const response = await client.send(command);
    console.log('✅ Environment variables updated successfully!\n');
    console.log(`Function: ${response.FunctionName}`);
    console.log(`Last Modified: ${response.LastModified}`);
    console.log('\n📋 Next steps:');
    console.log('1. Test the function: node scripts/test-lambda.js');
    console.log('2. Check your email for the daily digest\n');

  } catch (error) {
    console.error('❌ Update failed:', error.message);

    if (error.message.includes('update is in progress')) {
      console.error('\n⏳ Lambda is still processing the previous update.');
      console.error('Wait 10-30 seconds and try again.');
    }

    process.exit(1);
  }
}

updateConfig();
