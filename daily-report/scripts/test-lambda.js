#!/usr/bin/env node

/**
 * Test deployed Lambda function
 */

const { LambdaClient, InvokeCommand } = require('@aws-sdk/client-lambda');

const FUNCTION_NAME = 'openpaw-daily-digest';
const REGION = 'us-east-1';

const client = new LambdaClient({ region: REGION });

async function testLambda() {
  try {
    console.log(`🧪 Testing Lambda function: ${FUNCTION_NAME}\n`);

    const command = new InvokeCommand({
      FunctionName: FUNCTION_NAME,
      InvocationType: 'RequestResponse',
      Payload: JSON.stringify({})
    });

    console.log('⏳ Invoking function...\n');

    const response = await client.send(command);

    // Parse response
    const payload = JSON.parse(Buffer.from(response.Payload).toString());

    console.log('📊 Response:');
    console.log(`  Status Code: ${response.StatusCode}`);
    console.log(`  Execution Status: ${response.FunctionError ? '❌ ERROR' : '✅ SUCCESS'}`);
    console.log('\n📦 Payload:');
    console.log(JSON.stringify(payload, null, 2));

    if (response.FunctionError) {
      console.error('\n❌ Function returned an error');
      process.exit(1);
    }

    if (payload.statusCode === 200) {
      console.log('\n✅ Lambda executed successfully!');

      const body = JSON.parse(payload.body);
      if (body.messageId) {
        console.log(`📧 Email sent with message ID: ${body.messageId}`);
        console.log('\n📬 Check your inbox for the daily digest email with:');
        console.log('   • Today\'s Tech Joke 😄');
        console.log('   • Yesterday\'s Spending 💰 (from Plaid)');
        console.log('   • Top 5 Product Hunt products 🚀');
        console.log('   • Top 5 Hacker News stories 📰');
      } else if (body.message === 'Outside execution window') {
        console.log('\n⏰ Function skipped execution (outside 10am PT window)');
        console.log('This is expected behavior. The function only sends emails at 10am PT.');
      }
    } else {
      console.log(`\n⚠️  Unexpected status code: ${payload.statusCode}`);
    }

  } catch (error) {
    console.error('❌ Test failed:', error.message);

    if (error.name === 'ResourceNotFoundException') {
      console.error('\n⚠️  Lambda function not found!');
      console.error('Make sure the function is deployed first.');
    }

    process.exit(1);
  }
}

testLambda();
