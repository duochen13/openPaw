const { buildEmailTemplate } = require('../../src/email/template');

describe('Email Template Builder', () => {
  const mockPHProducts = [
    {
      id: 1,
      name: 'Product 1',
      tagline: 'Great product',
      upvotes: 100,
      comments: 20,
      url: 'https://ph.com/1',
      videoUrl: 'https://video.com/1.mp4'
    },
    {
      id: 2,
      name: 'Product 2',
      tagline: 'Amazing tool',
      upvotes: 200,
      comments: 50,
      url: 'https://ph.com/2',
      videoUrl: null
    }
  ];

  const mockHNStories = [
    {
      id: 101,
      title: 'Story 1',
      url: 'https://example.com/1',
      points: 500,
      comments: 50
    },
    {
      id: 102,
      title: 'Story 2',
      url: 'https://example.com/2',
      points: 300,
      comments: 25
    }
  ];

  test('builds complete HTML email', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<html');
    expect(html).toContain('</html>');
  });

  test('includes Product Hunt section', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('Product Hunt');
    expect(html).toContain('Product 1');
    expect(html).toContain('Great product');
  });

  test('includes Hacker News section', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('Hacker News');
    expect(html).toContain('Story 1');
    expect(html).toContain('500 points');
  });

  test('embeds video when videoUrl is provided', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('<video');
    expect(html).toContain('https://video.com/1.mp4');
  });

  test('shows link only when no video URL', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    expect(html).toContain('Product 2');
    expect(html).not.toContain('https://video.com/2.mp4');
  });

  test('handles empty Product Hunt data', () => {
    const html = buildEmailTemplate([], mockHNStories);

    expect(html).toContain('Product Hunt data unavailable today');
  });

  test('handles empty Hacker News data', () => {
    const html = buildEmailTemplate(mockPHProducts, []);

    expect(html).toContain('Hacker News data unavailable today');
  });

  test('includes current date in header', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories);

    const today = new Date().toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    });

    expect(html).toContain(today);
  });
});
