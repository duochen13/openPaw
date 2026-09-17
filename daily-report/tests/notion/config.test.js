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
    delete process.env.NOTION_DAILY_REPORT_PAGE_ID;
  });

  afterEach(() => {
    process.env = OLD_ENV;
  });

  test('returns null when nothing is configured', async () => {
    expect(await getNotionConfig()).toBeNull();
    expect(getSecret).not.toHaveBeenCalled();
  });

  test('returns null when the API key is set but the page id is missing', async () => {
    process.env.NOTION_API_KEY = 'secret_test_key';
    expect(await getNotionConfig()).toBeNull();
  });

  test('returns config from plain env vars', async () => {
    process.env.NOTION_API_KEY = 'secret_test_key';
    process.env.NOTION_DAILY_REPORT_PAGE_ID = 'daily-report-page-id';

    expect(await getNotionConfig()).toEqual({
      apiKey: 'secret_test_key',
      dailyReportPageId: 'daily-report-page-id'
    });
    expect(getSecret).not.toHaveBeenCalled();
  });

  test('falls back to Secrets Manager when only the ARN is set', async () => {
    process.env.NOTION_API_KEY_ARN = 'arn:aws:secretsmanager:us-west-2:123:secret:notion';
    process.env.NOTION_DAILY_REPORT_PAGE_ID = 'daily-report-page-id';
    getSecret.mockResolvedValue('secret_from_arn');

    const config = await getNotionConfig();
    expect(getSecret).toHaveBeenCalledWith('arn:aws:secretsmanager:us-west-2:123:secret:notion');
    expect(config.apiKey).toBe('secret_from_arn');
    expect(config.dailyReportPageId).toBe('daily-report-page-id');
  });
});
