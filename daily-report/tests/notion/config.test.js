const { getSecret } = require('../../src/utils/secrets');
const { getNotionConfig } = require('../../src/notion/config');

jest.mock('../../src/utils/secrets');

describe('getNotionConfig', () => {
  const OLD_ENV = process.env;

  beforeEach(() => {
    jest.clearAllMocks();
    process.env = { ...OLD_ENV };
    delete process.env.NOTION_API_KEY;
    delete process.env.NOTION_API_KEY_ARN;
    delete process.env.NOTION_DATABASE_ID;
    delete process.env.NOTION_DIGEST_DATABASE_ID;
  });

  afterEach(() => {
    process.env = OLD_ENV;
  });

  test('returns null when nothing is configured', async () => {
    expect(await getNotionConfig()).toBeNull();
    expect(getSecret).not.toHaveBeenCalled();
  });

  test('returns null when the API key is set but the database id is missing', async () => {
    process.env.NOTION_API_KEY = 'secret_test_key';
    expect(await getNotionConfig()).toBeNull();
  });

  test('returns config from plain env vars, digest db optional', async () => {
    process.env.NOTION_API_KEY = 'secret_test_key';
    process.env.NOTION_DATABASE_ID = 'items-db-id';

    expect(await getNotionConfig()).toEqual({
      apiKey: 'secret_test_key',
      databaseId: 'items-db-id',
      digestDatabaseId: null
    });
    expect(getSecret).not.toHaveBeenCalled();
  });

  test('includes the digest database id when set', async () => {
    process.env.NOTION_API_KEY = 'secret_test_key';
    process.env.NOTION_DATABASE_ID = 'items-db-id';
    process.env.NOTION_DIGEST_DATABASE_ID = 'digests-db-id';

    const config = await getNotionConfig();
    expect(config.digestDatabaseId).toBe('digests-db-id');
  });

  test('falls back to Secrets Manager when only the ARN is set', async () => {
    process.env.NOTION_API_KEY_ARN = 'arn:aws:secretsmanager:us-west-2:123:secret:notion';
    process.env.NOTION_DATABASE_ID = 'items-db-id';
    getSecret.mockResolvedValue('secret_from_arn');

    const config = await getNotionConfig();
    expect(getSecret).toHaveBeenCalledWith('arn:aws:secretsmanager:us-west-2:123:secret:notion');
    expect(config.apiKey).toBe('secret_from_arn');
  });
});
