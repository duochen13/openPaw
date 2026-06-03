#!/usr/bin/env node

/**
 * Set Gmail Client ID and Recipient Email in Lambda
 */

const { LambdaClient, UpdateFunctionConfigurationCommand, GetFunctionConfigurationCommand } = require('@aws-sdk/client-lambda');

const FUNCTION_NAME = 'openpaw-daily-digest';
const REGION = 'us-east-1';

const client = new LambdaClient({ region: REGION });

async function setGmailConfig() {
  try {
    console.log('📧 Setting Gmail configuration...\n');

    // Get current config
    const getCommand = new GetFunctionConfigurationCommand({
      FunctionName: FUNCTION_NAME
    });
    const current = await client.send(getCommand);

    // Update with Gmail values
    const updateCommand = new UpdateFunctionConfigurationCommand({
      FunctionName: FUNCTION_NAME,
      Environment: {
        Variables: {
          ...current.Environment.Variables,
          GMAIL_CLIENT_ID: '438256498490-91258hh5vpr9qn0pk9aktlidpoelm3gp.apps.googleusercontent.com',
          RECIPIENT_EMAIL: 'dc3565@columbia.edu'
        }
      }
    });

    const response = await client.send(updateCommand);

    console.log('✅ Gmail configuration updated!\n');
    console.log('📋 Settings:');
    console.log(`   Gmail Client ID: ${response.Environment.Variables.GMAIL_CLIENT_ID.substring(0, 30)}...`);
    console.log(`   Recipient Email: ${response.Environment.Variables.RECIPIENT_EMAIL}\n`);

    console.log('🧪 Ready to test! Run: node scripts/test-lambda.js\n');

  } catch (error) {
    console.error('❌ Update failed:', error.message);

    if (error.message.includes('update is in progress')) {
      console.error('\n⏳ Lambda is still processing. Wait 10-20 seconds and try again.');
    }

    process.exit(1);
  }
}

setGmailConfig();
