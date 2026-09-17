const { Client } = require('@notionhq/client');
const { syncDigestToNotion, pageTitleFor } = require('../../src/notion/sync');

jest.mock('@notionhq/client', () => ({
  Client: jest.fn()
}));

describe('pageTitleFor', () => {
  test('formats YYYY-MM-DD as MM-DD', () => {
    expect(pageTitleFor('2026-09-17')).toBe('09-17');
    expect(pageTitleFor('2026-01-05')).toBe('01-05');
  });
});

describe('Notion daily report sync', () => {
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

  function childPageBlock(title) {
    return { id: `block-${title}`, type: 'child_page', child_page: { title } };
  }

  // parentChildren: blocks under the Daily Report page; pageChildren: blocks
  // already inside the day's subpage.
  function routeChildren({ parentChildren = [], pageChildren = [] } = {}) {
    notion.blocks.children.list.mockImplementation(async ({ block_id }) => {
      if (block_id === 'daily-report-page-id') {
        return { results: parentChildren, has_more: false, next_cursor: null };
      }
      return { results: pageChildren, has_more: false, next_cursor: null };
    });
    notion.pages.create.mockImplementation(async () => ({
      id: `page-${Math.random().toString(36).slice(2)}`
    }));
  }

  beforeEach(() => {
    jest.clearAllMocks();
    process.env = { ...OLD_ENV };
    process.env.NOTION_API_KEY = 'secret_test_key';
    process.env.NOTION_DAILY_REPORT_PAGE_ID = 'daily-report-page-id';
    delete process.env.NOTION_API_KEY_ARN;

    notion = {
      blocks: { children: { list: jest.fn(), append: jest.fn() } },
      pages: { create: jest.fn() }
    };
    Client.mockImplementation(() => notion);
  });

  afterEach(() => {
    process.env = OLD_ENV;
  });

  test('is a no-op when Notion is not configured', async () => {
    delete process.env.NOTION_API_KEY;
    delete process.env.NOTION_DAILY_REPORT_PAGE_ID;

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result).toEqual({ skipped: true });
    expect(Client).not.toHaveBeenCalled();
    expect(notion.blocks.children.list).not.toHaveBeenCalled();
  });

  test('is a no-op when only the API key is set', async () => {
    delete process.env.NOTION_DAILY_REPORT_PAGE_ID;

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result).toEqual({ skipped: true });
    expect(Client).not.toHaveBeenCalled();
  });

  test('creates a MM-DD subpage and appends grouped item blocks', async () => {
    routeChildren();

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(Client).toHaveBeenCalledWith({ auth: 'secret_test_key' });
    expect(result.success).toBe(true);
    expect(result.pageTitle).toBe('09-17');
    expect(result.pageCreated).toBe(true);
    expect(result.itemsAppended).toBe(3);

    // Subpage created under the Daily Report page, titled by date.
    expect(notion.pages.create).toHaveBeenCalledTimes(1);
    const createArgs = notion.pages.create.mock.calls[0][0];
    expect(createArgs.parent.page_id).toBe('daily-report-page-id');
    expect(createArgs.properties.title[0].text.content).toBe('09-17');

    // One append with a heading + bullets per source.
    expect(notion.blocks.children.append).toHaveBeenCalledTimes(1);
    const appendArgs = notion.blocks.children.append.mock.calls[0][0];
    expect(appendArgs.block_id).toBe(result.pageId);
    const types = appendArgs.children.map((b) => b.type);
    expect(types).toEqual([
      'heading_2',
      'bulleted_list_item',
      'bulleted_list_item',
      'heading_2',
      'bulleted_list_item'
    ]);
    expect(appendArgs.children[0].heading_2.rich_text[0].text.content).toBe('Product Hunt');
    expect(appendArgs.children[3].heading_2.rich_text[0].text.content).toBe('Hacker News');

    const bullet = appendArgs.children[1].bulleted_list_item.rich_text[0].text;
    expect(bullet.content).toBe('Cool App (73)');
    expect(bullet.link.url).toBe('https://www.producthunt.com/posts/cool-app');

    const storyBullet = appendArgs.children[4].bulleted_list_item.rich_text[0].text;
    expect(storyBullet.content).toBe('Some HN story (250)');
    expect(storyBullet.link.url).toBe('https://example.com/hn-story');
  });

  test('reuses the existing subpage and does not duplicate content', async () => {
    routeChildren({
      parentChildren: [childPageBlock('09-16'), childPageBlock('09-17')],
      pageChildren: [{ id: 'existing-block', type: 'heading_2' }]
    });

    const result = await syncDigestToNotion(sampleProducts, sampleStories, { date: '2026-09-17' });

    expect(result.success).toBe(true);
    expect(result.pageId).toBe('block-09-17');
    expect(result.pageCreated).toBe(false);
    expect(notion.pages.create).not.toHaveBeenCalled();
    // Page already has content: leave it alone.
    expect(notion.blocks.children.append).not.toHaveBeenCalled();
    expect(result.itemsAppended).toBe(0);
  });

  test('fills an existing but empty subpage', async () => {
    routeChildren({ parentChildren: [childPageBlock('09-17')], pageChildren: [] });

    const result = await syncDigestToNotion(sampleProducts, [], { date: '2026-09-17' });

    expect(result.pageCreated).toBe(false);
    expect(notion.pages.create).not.toHaveBeenCalled();
    expect(notion.blocks.children.append).toHaveBeenCalledTimes(1);
    expect(result.itemsAppended).toBe(2);
  });

  test('skips items missing a name or url', async () => {
    routeChildren();

    const result = await syncDigestToNotion(
      [{ name: '', url: 'https://www.producthunt.com/posts/nameless', trendingScore: 10 }],
      [{ title: 'No URL story', url: '', points: 5 }],
      { date: '2026-09-17' }
    );

    expect(result.success).toBe(true);
    expect(result.pageCreated).toBe(true);
    expect(notion.blocks.children.append).not.toHaveBeenCalled();
    expect(result.itemsAppended).toBe(0);
  });
});
