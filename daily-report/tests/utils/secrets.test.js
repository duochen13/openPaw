const { mockClient } = require('aws-sdk-client-mock');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { getSecret } = require('../../src/utils/secrets');

const secretsManagerMock = mockClient(SecretsManagerClient);

describe('Secrets Manager', () => {
  beforeEach(() => {
    secretsManagerMock.reset();
  });

  test('getSecret returns secret string', async () => {
    secretsManagerMock.on(GetSecretValueCommand).resolves({
      SecretString: 'my-secret-value'
    });

    const result = await getSecret('arn:aws:secretsmanager:us-east-1:123456789012:secret:test');

    expect(result).toBe('my-secret-value');
  });

  test('getSecret throws error when secret not found', async () => {
    secretsManagerMock.on(GetSecretValueCommand).rejects(new Error('Secret not found'));

    await expect(getSecret('invalid-arn')).rejects.toThrow('Secret not found');
  });

  test('getSecret caches secrets', async () => {
    secretsManagerMock.on(GetSecretValueCommand).resolves({
      SecretString: 'cached-value'
    });

    const result1 = await getSecret('test-arn');
    const result2 = await getSecret('test-arn');

    expect(result1).toBe('cached-value');
    expect(result2).toBe('cached-value');
    expect(secretsManagerMock.calls()).toHaveLength(1);
  });
});
