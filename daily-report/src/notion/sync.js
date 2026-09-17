const { DateTime } = require('luxon');
const { Client } = require('@notionhq/client');
const { getNotionConfig } = require('./config');
const { logger } = require('../utils/logger');

const TYPE_PRODUCT_HUNT = 'Product Hunt';
const TYPE_HACKER_NEWS = 'Hacker News';
const STATUS_NEW = 'New';

/**
 * Notion Daily Calendar sync.
 *
 * Database design (see README for setup instructions):
 *
 *   "Daily Digest Items" (NOTION_DATABASE_ID)
 *     Name    title   - product name / story title
 *     Type    select  - "Product Hunt" | "Hacker News"
 *     URL     url     - link to the product / story
 *     Date    date    - the digest day (YYYY-MM-DD)
 *     Score   number  - trendingScore (PH) / points (HN)
 *     Status  select  - "New" | "Reviewed" | "Interesting" (user flips this in
 *                       Notion; the sync sets "New" on create and never
 *                       overwrites it afterwards)
 *     Digest  relation -> "Daily Digests" (only populated when
 *                       NOTION_DIGEST_DATABASE_ID is configured)
 *
 *   "Daily Digests" (NOTION_DIGEST_DATABASE_ID, optional)
 *     Name    title   - e.g. "Daily Digest — 2026-09-17"
 *     Date    date    - the digest day; add a Notion calendar view on this
 *
 * Both writes are upserts keyed on (Date, URL) for items and (Date) for the
 * daily page, so re-running the digest for the same day never creates
 * duplicates.
 */

async function findDailyPage(notion, digestDatabaseId, date) {
  const response = await notion.databases.query({
    database_id: digestDatabaseId,
    filter: { property: 'Date', date: { equals: date } },
    page_size: 1
  });
  return response.results[0] || null;
}

async function createDailyPage(notion, digestDatabaseId, date) {
  return notion.pages.create({
    parent: { database_id: digestDatabaseId },
    properties: {
      Name: { title: [{ text: { content: `Daily Digest — ${date}` } }] },
      Date: { date: { start: date } }
    }
  });
}

async function findItemPage(notion, databaseId, date, url) {
  const response = await notion.databases.query({
    database_id: databaseId,
    filter: {
      and: [
        { property: 'Date', date: { equals: date } },
        { property: 'URL', url: { equals: url } }
      ]
    },
    page_size: 1
  });
  return response.results[0] || null;
}

function buildItemProperties({ name, type, url, date, score, digestPageId }) {
  const properties = {
    Name: { title: [{ text: { content: name } }] },
    Type: { select: { name: type } },
    URL: { url },
    Date: { date: { start: date } },
    Score: { number: typeof score === 'number' ? score : null },
    Status: { select: { name: STATUS_NEW } }
  };
  if (digestPageId) {
    properties.Digest = { relation: [{ id: digestPageId }] };
  }
  return properties;
}

function normalizeItems(products, stories) {
  const fromProducts = (products || []).map((product) => ({
    name: product.name,
    type: TYPE_PRODUCT_HUNT,
    url: product.url,
    score: product.trendingScore
  }));
  const fromStories = (stories || []).map((story) => ({
    name: story.title,
    type: TYPE_HACKER_NEWS,
    url: story.url,
    score: story.points
  }));
  return [...fromProducts, ...fromStories].filter((item) => item.name && item.url);
}

/**
 * Sync the day's digest items to Notion.
 *
 * @param {Array} products - Product Hunt products from fetchTopProductHuntProducts
 * @param {Array} stories  - Hacker News stories from fetchTopHackerNewsStories
 * @param {Object} [options]
 * @param {string} [options.date] - digest day as YYYY-MM-DD (defaults to today
 *                                  in TIMEZONE; the override exists for tests)
 * @returns {Promise<Object>} { skipped: true } when Notion is not configured,
 *          otherwise { success, date, itemsCreated, itemsUpdated, itemsFailed, digestPageId }
 */
async function syncDigestToNotion(products, stories, options = {}) {
  const config = await getNotionConfig();
  if (!config) {
    logger.info('Notion sync skipped: NOTION_API_KEY/NOTION_DATABASE_ID not set');
    return { skipped: true };
  }

  const timezone = process.env.TIMEZONE || 'America/Los_Angeles';
  const date = options.date || DateTime.now().setZone(timezone).toISODate();

  const notion = new Client({ auth: config.apiKey });
  const items = normalizeItems(products, stories);

  // Upsert the daily calendar page (one per day), when a digests DB is configured.
  let digestPageId = null;
  if (config.digestDatabaseId) {
    const existingDailyPage = await findDailyPage(notion, config.digestDatabaseId, date);
    if (existingDailyPage) {
      digestPageId = existingDailyPage.id;
      logger.info('Reusing existing Notion daily page', { date, pageId: digestPageId });
    } else {
      const dailyPage = await createDailyPage(notion, config.digestDatabaseId, date);
      digestPageId = dailyPage.id;
      logger.info('Created Notion daily page', { date, pageId: digestPageId });
    }
  }

  let itemsCreated = 0;
  let itemsUpdated = 0;
  let itemsFailed = 0;

  for (const item of items) {
    try {
      const existingItem = await findItemPage(notion, config.databaseId, date, item.url);
      if (existingItem) {
        // Refresh the score, but never touch Status: the user may have
        // manually flipped it to Reviewed / Interesting in Notion.
        await notion.pages.update({
          page_id: existingItem.id,
          properties: {
            Type: { select: { name: item.type } },
            Score: { number: typeof item.score === 'number' ? item.score : null },
            ...(digestPageId ? { Digest: { relation: [{ id: digestPageId }] } } : {})
          }
        });
        itemsUpdated += 1;
      } else {
        await notion.pages.create({
          parent: { database_id: config.databaseId },
          properties: buildItemProperties({ ...item, date, digestPageId })
        });
        itemsCreated += 1;
      }
    } catch (error) {
      // One bad item must not kill the rest of the sync.
      logger.warn('Failed to sync item to Notion', {
        name: item.name,
        url: item.url,
        error: error.message
      });
      itemsFailed += 1;
    }
  }

  const result = { success: true, date, itemsCreated, itemsUpdated, itemsFailed, digestPageId };
  logger.info('Notion sync completed', result);
  return result;
}

module.exports = {
  syncDigestToNotion,
  TYPE_PRODUCT_HUNT,
  TYPE_HACKER_NEWS,
  STATUS_NEW
};
