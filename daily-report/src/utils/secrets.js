const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

const client = new SecretsManagerClient({});
const secretCache = new Map();

async function getSecret(secretArn) {
  if (secretCache.has(secretArn)) {
    return secretCache.get(secretArn);
  }

  const command = new GetSecretValueCommand({
    SecretId: secretArn
  });

  const response = await client.send(command);
  const secretValue = response.SecretString;

  secretCache.set(secretArn, secretValue);
  return secretValue;
}

module.exports = { getSecret };
