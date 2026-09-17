const { getSecret } = require('../utils/secrets');

/**
 * Resolve Notion configuration from the environment.
 *
 * Follows the same pattern as the other integrations in this project:
 * AWS Secrets Manager ARNs for Lambda, plain env vars for local dev.
 *
 *   NOTION_API_KEY / NOTION_API_KEY_ARN - Notion internal integration token
 *   NOTION_DAILY_REPORT_PAGE_ID         - the "Daily Report" page id; each
 *                                         run creates (or reuses) a "MM-DD"
 *                                         subpage under it
 *
 * Returns null when Notion is not configured, so the sync is a no-op.
 */
async function getNotionConfig() {
  let apiKey = process.env.NOTION_API_KEY || null;
  if (!apiKey && process.env.NOTION_API_KEY_ARN) {
    apiKey = await getSecret(process.env.NOTION_API_KEY_ARN);
  }

  const dailyReportPageId = process.env.NOTION_DAILY_REPORT_PAGE_ID || null;
  if (!apiKey || !dailyReportPageId) {
    return null;
  }

  return { apiKey, dailyReportPageId };
}

module.exports = { getNotionConfig };
