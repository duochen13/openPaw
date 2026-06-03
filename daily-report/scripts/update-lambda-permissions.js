#!/usr/bin/env node

/**
 * Update Lambda IAM role to grant access to Plaid secrets
 */

const { IAMClient, PutRolePolicyCommand, GetRolePolicyCommand } = require('@aws-sdk/client-iam');

const ROLE_NAME = 'openpaw-daily-digest-DailyDigestFunctionRole-0Wp7FIiJfSa2';
const POLICY_NAME = 'SecretsManagerAccess';

const client = new IAMClient({ region: 'us-east-1' });

async function updatePermissions() {
  try {
    console.log('🔐 Updating Lambda IAM permissions for Plaid secrets...\n');

    const policy = {
      Version: '2012-10-17',
      Statement: [
        {
          Effect: 'Allow',
          Action: 'secretsmanager:GetSecretValue',
          Resource: [
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/gmail/client-secret-hWktkd',
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/gmail/refresh-token-e8EDsT',
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/product-hunt/api-key-6cVJKD',
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/product-hunt/api-secret-Q8s1Mx',
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-ChMp7v',
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-mZUbAR',
            'arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-2vtVRz'
          ]
        }
      ]
    };

    const command = new PutRolePolicyCommand({
      RoleName: ROLE_NAME,
      PolicyName: POLICY_NAME,
      PolicyDocument: JSON.stringify(policy)
    });

    await client.send(command);

    console.log('✅ Permissions updated successfully!\n');
    console.log('📋 Granted secretsmanager:GetSecretValue access to:');
    console.log('   • 2 Gmail secrets');
    console.log('   • 2 Product Hunt secrets');
    console.log('   • 3 Plaid secrets (NEW)\n');

    console.log('🧪 Now test the Lambda: node scripts/test-lambda.js\n');

  } catch (error) {
    console.error('❌ Update failed:', error.message);
    process.exit(1);
  }
}

updatePermissions();
