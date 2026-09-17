const { getSecret } = require('../utils/secrets');

/**
 * Resolve Notion configuration from the environment.
 *
 * Follows the same pattern as the other integrations in this project:
 * AWS Secrets Manager ARNs for Lambda, plain env vars for local dev.
 *
 *   NOTION_API_KEY / NOTION_API_KEY_ARN - Notion internal integration token
 *   NOTION_DATABASE_ID                  - "Daily Digest Items" database id (required)
 *   NOTION_DIGEST_DATABASE_ID           - "Daily Digests" database id (optional,
 *                                         enables one calendar page per day)
 *
 * Returns null when Notion is not configured, so the sync is a no-op.
 */
async function getNotionConfig() {
  let apiKey = process.env.NOTION_API_KEY || null;
  if (!apiKey && process.env.NOTION_API_KEY_ARN) {
    apiKey = await getSecret(process.env.NOTION_API_KEY_ARN);
  }

  const databaseId = process.env.NOTION_DATABASE_ID || null;
  if (!apiKey || !databaseId) {
    return null;
  }

  return {
    apiKey,
    databaseId,
    digestDatabaseId: process.env.NOTION_DIGEST_DATABASE_ID || null
  };
}

module.exports = { getNotionConfig };
