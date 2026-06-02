#!/usr/bin/env node

/**
 * Deploy Lambda function code using AWS SDK
 * Workaround for broken SAM CLI
 */

const { LambdaClient, UpdateFunctionCodeCommand, UpdateFunctionConfigurationCommand } = require('@aws-sdk/client-lambda');
const { readFile, rm, mkdir, cp } = require('fs/promises');
const { promisify } = require('util');
const { exec } = require('child_process');
const execAsync = promisify(exec);

const FUNCTION_NAME = 'openpaw-daily-digest';
const REGION = 'us-east-1';
const BUILD_DIR = '.aws-build';

const client = new LambdaClient({ region: REGION });

async function deployLambda() {
  try {
    console.log('📦 Step 1: Creating optimized deployment package...\n');

    // Clean up previous builds
    await rm(BUILD_DIR, { recursive: true, force: true });
    await rm('function.zip', { force: true });

    // Create build directory
    await mkdir(BUILD_DIR, { recursive: true });

    // Copy source files
    console.log('  • Copying source files...');
    await execAsync(`cp -r src ${BUILD_DIR}/`, { maxBuffer: 1024 * 1024 * 10 });
    await execAsync(`cp package.json package-lock.json ${BUILD_DIR}/`, { maxBuffer: 1024 * 1024 * 10 });

    // Install production dependencies only
    console.log('  • Installing production dependencies...');
    await execAsync(`cd ${BUILD_DIR} && npm install --production --no-optional`, { maxBuffer: 1024 * 1024 * 10 });

    // Create zip from build directory
    console.log('  • Creating deployment package...');
    await execAsync(`cd ${BUILD_DIR} && zip -rq ../function.zip .`, { maxBuffer: 1024 * 1024 * 10 });

    console.log('✓ Created function.zip\n');

    console.log('☁️  Step 2: Uploading to Lambda...\n');

    // Read zip file
    const zipBuffer = await readFile('function.zip');
    const sizeMB = (zipBuffer.length / (1024 * 1024)).toFixed(2);
    console.log(`  Package size: ${sizeMB} MB`);

    // Update function code
    const updateCodeCommand = new UpdateFunctionCodeCommand({
      FunctionName: FUNCTION_NAME,
      ZipFile: zipBuffer
    });

    const codeResponse = await client.send(updateCodeCommand);
    console.log('✓ Code uploaded successfully');
    console.log(`  Function ARN: ${codeResponse.FunctionArn}`);
    console.log(`  Last Modified: ${codeResponse.LastModified}\n`);

    console.log('⚙️  Step 3: Updating environment variables...\n');

    // Update environment variables to include Plaid configuration
    const updateConfigCommand = new UpdateFunctionConfigurationCommand({
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

    const configResponse = await client.send(updateConfigCommand);
    console.log('✓ Environment variables updated\n');

    // Clean up
    await rm(BUILD_DIR, { recursive: true, force: true });
    await rm('function.zip', { force: true });

    console.log('✅ Deployment complete!\n');
    console.log('📋 Next steps:');
    console.log('1. Test the function: node scripts/test-lambda.js');
    console.log('2. Check CloudWatch logs for any errors');
    console.log('3. Verify email is sent with spending data\n');

  } catch (error) {
    console.error('❌ Deployment failed:', error.message);

    if (error.name === 'ResourceNotFoundException') {
      console.error('\n⚠️  Lambda function not found!');
      console.error('You need to create the function first using SAM or AWS Console.');
      console.error('See DEPLOY-MANUAL.md for instructions.');
    }

    // Clean up on error
    try {
      await rm(BUILD_DIR, { recursive: true, force: true });
      await rm('function.zip', { force: true });
    } catch (cleanupError) {
      // Ignore cleanup errors
    }

    process.exit(1);
  }
}

deployLambda();
