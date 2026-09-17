const { DateTime } = require('luxon');
const { Client } = require('@notionhq/client');
const { getNotionConfig } = require('./config');
const { logger } = require('../utils/logger');

const TYPE_PRODUCT_HUNT = 'Product Hunt';
const TYPE_HACKER_NEWS = 'Hacker News';

/**
 * Notion Daily Report sync.
 *
 * Each run writes the day's digest into a subpage of the "Daily Report" page
 * (NOTION_DAILY_REPORT_PAGE_ID). The subpage is titled "MM-DD" (e.g. "09-17")
 * and holds the Product Hunt / Hacker News items as linked bullets.
 *
 * Re-runs are safe: when the day's subpage already exists and has content, the
 * sync leaves it alone instead of duplicating items or clobbering manual edits.
 */

/**
 * "2026-09-17" -> "09-17"
 */
function pageTitleFor(date) {
  const [, month, day] = date.split('-');
  return `${month}-${day}`;
}

async function findSubpage(notion, parentPageId, title) {
  let cursor;
  do {
    const response = await notion.blocks.children.list({
      block_id: parentPageId,
      start_cursor: cursor,
      page_size: 100
    });
    const match = response.results.find(
      (block) => block.type === 'child_page' && block.child_page && block.child_page.title === title
    );
    if (match) {
      return match;
    }
    cursor = response.has_more ? response.next_cursor : undefined;
  } while (cursor);
  return null;
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

function richText(content, url) {
  const text = { content };
  if (url) {
    text.link = { url };
  }
  return [{ type: 'text', text }];
}

function buildContentBlocks(items) {
  const blocks = [];
  const groups = [
    [TYPE_PRODUCT_HUNT, 'Product Hunt'],
    [TYPE_HACKER_NEWS, 'Hacker News']
  ];
  for (const [type, heading] of groups) {
    const groupItems = items.filter((item) => item.type === type);
    if (groupItems.length === 0) {
      continue;
    }
    blocks.push({
      object: 'block',
      type: 'heading_2',
      heading_2: { rich_text: richText(heading) }
    });
    for (const item of groupItems) {
      const label = typeof item.score === 'number' ? `${item.name} (${item.score})` : item.name;
      blocks.push({
        object: 'block',
        type: 'bulleted_list_item',
        bulleted_list_item: { rich_text: richText(label, item.url) }
      });
    }
  }
  return blocks;
}

/**
 * Sync the day's digest items to a "MM-DD" subpage under the Daily Report page.
 *
 * @param {Array} products - Product Hunt products from fetchTopProductHuntProducts
 * @param {Array} stories  - Hacker News stories from fetchTopHackerNewsStories
 * @param {Object} [options]
 * @param {string} [options.date] - digest day as YYYY-MM-DD (defaults to today
 *                                  in TIMEZONE; the override exists for tests)
 * @returns {Promise<Object>} { skipped: true } when Notion is not configured,
 *          otherwise { success, date, pageTitle, pageId, pageCreated, itemsAppended }
 */
async function syncDigestToNotion(products, stories, options = {}) {
  const config = await getNotionConfig();
  if (!config) {
    logger.info('Notion sync skipped: NOTION_API_KEY/NOTION_DAILY_REPORT_PAGE_ID not set');
    return { skipped: true };
  }

  const timezone = process.env.TIMEZONE || 'America/Los_Angeles';
  const date = options.date || DateTime.now().setZone(timezone).toISODate();
  const title = pageTitleFor(date);

  const notion = new Client({ auth: config.apiKey });
  const items = normalizeItems(products, stories);

  let page = await findSubpage(notion, config.dailyReportPageId, title);
  let pageCreated = false;
  if (!page) {
    page = await notion.pages.create({
      parent: { page_id: config.dailyReportPageId },
      properties: { title: [{ text: { content: title } }] }
    });
    pageCreated = true;
    logger.info('Created Notion daily subpage', { title, pageId: page.id });
  } else {
    logger.info('Reusing existing Notion daily subpage', { title, pageId: page.id });
  }

  // Populate only a fresh/empty page: re-runs must not duplicate items or
  // wipe out anything added manually.
  const existingChildren = await notion.blocks.children.list({ block_id: page.id, page_size: 1 });
  let itemsAppended = 0;
  if (existingChildren.results.length === 0 && items.length > 0) {
    const blocks = buildContentBlocks(items);
    for (let i = 0; i < blocks.length; i += 100) {
      await notion.blocks.children.append({
        block_id: page.id,
        children: blocks.slice(i, i + 100)
      });
    }
    itemsAppended = items.length;
  }

  const result = { success: true, date, pageTitle: title, pageId: page.id, pageCreated, itemsAppended };
  logger.info('Notion sync completed', result);
  return result;
}

module.exports = {
  syncDigestToNotion,
  pageTitleFor,
  TYPE_PRODUCT_HUNT,
  TYPE_HACKER_NEWS
};
