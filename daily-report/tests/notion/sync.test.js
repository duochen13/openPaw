const { Client } = require('@notionhq/client');
const { syncDigestToNotion } = require('../../src/notion/sync');

jest.mock('@notionhq/client', () => ({
  Client: jest.fn()
}));

describe('Notion daily calendar sync', () => {
  let notion;
  const OLD_ENV = process.env;

  const sampleProducts = [
    {
      id: 'ph-1',
      name: 'Cool App',
      tagline: 'Does cool things',
      upvotes: 100,
      comments: 10,
      trendingScore: 73,
      url: 'https://www.producthunt.com/posts/cool-app',
      videoUrl: null
    },
    {
      id: 'ph-2',
      name: 'Another Tool',
      tagline: 'More things',
      upvotes: 50,
      comments: 5,
      trendingScore: 36.5,
      url: 'https://www.producthunt.com/posts/another-tool',
      videoUrl: null
    }
  ];

  const sampleStories = [
    {
      id: 111,
      title: 'Some HN story',
      url: 'https://example.com/hn-story',
      points: 250,
      comments: 42
    }
  ];

  function routeQueries({ dailyPages = [], existingItemIds = {} } = {}) {
    notion.databases.query.mockImplementation(async ({ database_id, filter }) => {
      if (database_id === 'digests-db-id') {
        return { results: dailyPages };
      }
      const urlCondition = (filter.and || []).find((c) => c.property === 'URL');
      const url = urlCondition && urlCondition.url.equals;
      const pageId = existingItemIds[url];
      return { results: pageId ? [{ id: pageId }] : [] };
    });
    notion.pages.create.mockImplementation(async () => ({ id: `page-${Math.random().toString(36).slice(2)}` }));
  }

  beforeEach(() => {
    jest.clearAllMocks();
    process.env = { ...OLD_ENV };
    process.env.NOTION_API_KEY = 'secret_test_key';
    process.env.NOTION_DATABASE_ID = 'items-db-id';
    process.env.NOTION_DIGEST_DATABASE_ID = 'digests-db-id';
    delete process.env.NOTION_API_KEY_ARN;

    notion = {
      databases: { query: jest.fn() },
      pages: { create: jest.fn(), update: jest.fn() }
    };
    Client.mockImplementation(() => notion);
  });

  afterEach(() => {
    process.env = OLD_ENV;
  });

  test('is a no-op when Notion is not configured', async () => {
    delete process.env.NOTION_API_KEY;
    delete process.env.NOTION_DATABASE_ID;
    delete process.env.NOTION_DIGEST_DATABASE_ID;

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result).toEqual({ skipped: true });
    expect(Client).not.toHaveBeenCalled();
    expect(notion.databases.query).not.toHaveBeenCalled();
  });

  test('is a no-op when only the API key is set', async () => {
    delete process.env.NOTION_DATABASE_ID;

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result).toEqual({ skipped: true });
    expect(Client).not.toHaveBeenCalled();
  });

  test('creates a daily page and item pages with the right properties', async () => {
    routeQueries({ dailyPages: [] });

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(Client).toHaveBeenCalledWith({ auth: 'secret_test_key' });
    expect(result.success).toBe(true);
    expect(result.date).toBe('2026-09-17');
    expect(result.itemsCreated).toBe(3);
    expect(result.itemsUpdated).toBe(0);
    expect(result.digestPageId).toBeTruthy();

    // Daily page created once, keyed on the date.
    const dailyCreates = notion.pages.create.mock.calls.filter(
      ([args]) => args.parent.database_id === 'digests-db-id'
    );
    expect(dailyCreates).toHaveLength(1);
    expect(dailyCreates[0][0].properties.Name.title[0].text.content).toContain('2026-09-17');
    expect(dailyCreates[0][0].properties.Date.date.start).toBe('2026-09-17');

    // Item pages created with the documented schema.
    const itemCreates = notion.pages.create.mock.calls.filter(
      ([args]) => args.parent.database_id === 'items-db-id'
    );
    expect(itemCreates).toHaveLength(3);

    const productPage = itemCreates.find(
      ([args]) => args.properties.URL.url === 'https://www.producthunt.com/posts/cool-app'
    )[0];
    expect(productPage.properties.Name.title[0].text.content).toBe('Cool App');
    expect(productPage.properties.Type.select.name).toBe('Product Hunt');
    expect(productPage.properties.Date.date.start).toBe('2026-09-17');
    expect(productPage.properties.Score.number).toBe(73);
    expect(productPage.properties.Status.select.name).toBe('New');
    expect(productPage.properties.Digest.relation[0].id).toBe(result.digestPageId);

    const storyPage = itemCreates.find(
      ([args]) => args.properties.URL.url === 'https://example.com/hn-story'
    )[0];
    expect(storyPage.properties.Name.title[0].text.content).toBe('Some HN story');
    expect(storyPage.properties.Type.select.name).toBe('Hacker News');
    expect(storyPage.properties.Score.number).toBe(250);
    expect(storyPage.properties.Status.select.name).toBe('New');
  });

  test('reuses the existing daily page instead of creating a duplicate', async () => {
    routeQueries({ dailyPages: [{ id: 'existing-daily-page' }] });

    const result = await syncDigestToNotion(sampleProducts, [], { date: '2026-09-17' });

    expect(result.digestPageId).toBe('existing-daily-page');
    const dailyCreates = notion.pages.create.mock.calls.filter(
      ([args]) => args.parent.database_id === 'digests-db-id'
    );
    expect(dailyCreates).toHaveLength(0);

    const itemCreates = notion.pages.create.mock.calls.filter(
      ([args]) => args.parent.database_id === 'items-db-id'
    );
    expect(itemCreates[0][0].properties.Digest.relation[0].id).toBe('existing-daily-page');
  });

  test('upserts: updates score on existing items without touching Status', async () => {
    routeQueries({
      dailyPages: [{ id: 'daily-page-1' }],
      existingItemIds: { 'https://www.producthunt.com/posts/cool-app': 'item-page-1' }
    });

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result.itemsCreated).toBe(2);
    expect(result.itemsUpdated).toBe(1);

    // The existing item was updated, not re-created.
    expect(notion.pages.update).toHaveBeenCalledTimes(1);
    const updateArgs = notion.pages.update.mock.calls[0][0];
    expect(updateArgs.page_id).toBe('item-page-1');
    expect(updateArgs.properties.Score.number).toBe(73);
    expect(updateArgs.properties.Type.select.name).toBe('Product Hunt');
    // Status must never be overwritten — the user may have flipped it manually.
    expect(updateArgs.properties.Status).toBeUndefined();

    // A fresh item was created for the new URL.
    const createdUrls = notion.pages.create.mock.calls
      .filter(([args]) => args.parent.database_id === 'items-db-id')
      .map(([args]) => args.properties.URL.url);
    expect(createdUrls).toContain('https://www.producthunt.com/posts/another-tool');
    expect(createdUrls).not.toContain('https://www.producthunt.com/posts/cool-app');
  });

  test('works without a digest database: no daily page, no relation', async () => {
    delete process.env.NOTION_DIGEST_DATABASE_ID;
    routeQueries();

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result.success).toBe(true);
    expect(result.digestPageId).toBeNull();
    const dailyQueries = notion.databases.query.mock.calls.filter(
      ([args]) => args.database_id === 'digests-db-id'
    );
    expect(dailyQueries).toHaveLength(0);

    const itemCreates = notion.pages.create.mock.calls.filter(
      ([args]) => args.parent.database_id === 'items-db-id'
    );
    expect(itemCreates).toHaveLength(3);
    expect(itemCreates[0][0].properties.Digest).toBeUndefined();
  });

  test('skips items missing a name or url', async () => {
    routeQueries({ dailyPages: [{ id: 'daily-page-1' }] });

    const result = await syncDigestToNotion(
      [{ name: '', url: 'https://www.producthunt.com/posts/nameless', trendingScore: 10 }],
      [{ title: 'No URL story', url: '', points: 5 }],
      { date: '2026-09-17' }
    );

    expect(result.itemsCreated).toBe(0);
    const itemCreates = notion.pages.create.mock.calls.filter(
      ([args]) => args.parent.database_id === 'items-db-id'
    );
    expect(itemCreates).toHaveLength(0);
  });

  test('continues past per-item failures and reports them', async () => {
    routeQueries({ dailyPages: [{ id: 'daily-page-1' }] });
    notion.pages.create.mockImplementation(async ({ parent }) => {
      if (parent.database_id === 'items-db-id') {
        throw new Error('Notion API exploded');
      }
      return { id: 'daily-page-2' };
    });

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result.success).toBe(true);
    expect(result.itemsCreated).toBe(0);
    expect(result.itemsFailed).toBe(3);
  });
});
