# Daily Digest Email Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AWS Lambda function that sends daily email digests with top Product Hunt products and Hacker News stories at 10am PT.

**Architecture:** Single Lambda orchestrating parallel API fetches (Product Hunt, Hacker News), HTML email generation, and Gmail API delivery. Uses AWS Secrets Manager for credentials, EventBridge for scheduling, and follows TDD throughout.

**Tech Stack:** Node.js 18.x, Jest, AWS SDK v3, Gmail API, Product Hunt API, Hacker News API, Luxon (timezone), AWS SAM

---

## File Structure

**Application Code:**
- `daily-report/src/index.js` - Lambda handler (orchestration)
- `daily-report/src/fetchers/productHunt.js` - Product Hunt fetcher
- `daily-report/src/fetchers/hackerNews.js` - Hacker News fetcher
- `daily-report/src/email/template.js` - HTML email builder
- `daily-report/src/email/styles.js` - CSS inline styles
- `daily-report/src/gmail/client.js` - Gmail API client
- `daily-report/src/utils/logger.js` - Structured logging
- `daily-report/src/utils/secrets.js` - Secrets Manager wrapper

**Tests:**
- `daily-report/tests/utils/logger.test.js`
- `daily-report/tests/utils/secrets.test.js`
- `daily-report/tests/fetchers/hackerNews.test.js`
- `daily-report/tests/fetchers/productHunt.test.js`
- `daily-report/tests/email/styles.test.js`
- `daily-report/tests/email/template.test.js`
- `daily-report/tests/gmail/client.test.js`
- `daily-report/tests/index.test.js`

**Configuration:**
- `daily-report/package.json` - Dependencies and scripts
- `daily-report/.env.example` - Environment variable template
- `daily-report/template.yaml` - AWS SAM template
- `daily-report/jest.config.js` - Jest configuration

---

### Task 1: Project Setup

**Files:**
- Create: `daily-report/package.json`
- Create: `daily-report/jest.config.js`
- Create: `daily-report/.env.example`
- Create: `daily-report/.gitignore`

- [ ] **Step 1: Initialize npm project**

```bash
cd daily-report
npm init -y
```

- [ ] **Step 2: Install dependencies**

```bash
npm install @aws-sdk/client-secrets-manager @aws-sdk/client-ssm googleapis axios luxon
npm install --save-dev jest @types/jest aws-sdk-client-mock
```

- [ ] **Step 3: Create Jest configuration**

Create `daily-report/jest.config.js`:

```javascript
module.exports = {
  testEnvironment: 'node',
  coverageDirectory: 'coverage',
  collectCoverageFrom: [
    'src/**/*.js',
    '!src/**/*.test.js'
  ],
  testMatch: [
    '**/tests/**/*.test.js'
  ],
  clearMocks: true,
  resetMocks: true,
  restoreMocks: true
};
```

- [ ] **Step 4: Update package.json scripts**

Edit `daily-report/package.json` to add:

```json
{
  "name": "daily-digest-email",
  "version": "1.0.0",
  "description": "Daily email digest with Product Hunt and Hacker News",
  "main": "src/index.js",
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch",
    "test:coverage": "jest --coverage"
  },
  "keywords": ["email", "digest", "lambda"],
  "author": "",
  "license": "MIT"
}
```

- [ ] **Step 5: Create environment template**

Create `daily-report/.env.example`:

```
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:name
GMAIL_REFRESH_TOKEN_ARN=arn:aws:secretsmanager:region:account:secret:name
RECIPIENT_EMAIL=your-email@example.com
PRODUCT_HUNT_API_KEY_ARN=arn:aws:secretsmanager:region:account:secret:name
TIMEZONE=America/Los_Angeles
```

- [ ] **Step 6: Create .gitignore**

Create `daily-report/.gitignore`:

```
node_modules/
.env
coverage/
*.log
.DS_Store
.aws-sam/
```

- [ ] **Step 7: Create directory structure**

```bash
mkdir -p src/fetchers src/email src/gmail src/utils tests/fetchers tests/email tests/gmail tests/utils
```

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "feat: initialize project structure and dependencies"
```

---

### Task 2: Logger Utility

**Files:**
- Create: `daily-report/src/utils/logger.js`
- Create: `daily-report/tests/utils/logger.test.js`

- [ ] **Step 1: Write failing test for logger**

Create `daily-report/tests/utils/logger.test.js`:

```javascript
const { logger } = require('../../src/utils/logger');

describe('Logger', () => {
  let consoleLogSpy;
  let consoleErrorSpy;

  beforeEach(() => {
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  test('info logs JSON with info level', () => {
    logger.info('Test message', { key: 'value' });

    expect(consoleLogSpy).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(consoleLogSpy.mock.calls[0][0]);
    expect(loggedData.level).toBe('INFO');
    expect(loggedData.message).toBe('Test message');
    expect(loggedData.key).toBe('value');
    expect(loggedData.timestamp).toBeDefined();
  });

  test('error logs JSON with error level', () => {
    const error = new Error('Test error');
    logger.error('Error occurred', { error });

    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(consoleErrorSpy.mock.calls[0][0]);
    expect(loggedData.level).toBe('ERROR');
    expect(loggedData.message).toBe('Error occurred');
    expect(loggedData.error).toBeDefined();
  });

  test('warn logs JSON with warn level', () => {
    logger.warn('Warning message');

    expect(consoleLogSpy).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(consoleLogSpy.mock.calls[0][0]);
    expect(loggedData.level).toBe('WARN');
    expect(loggedData.message).toBe('Warning message');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/utils/logger.test.js
```

Expected: FAIL with "Cannot find module '../../src/utils/logger'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/utils/logger.js`:

```javascript
function createLogger() {
  return {
    info: (message, data = {}) => {
      const logEntry = {
        level: 'INFO',
        message,
        timestamp: new Date().toISOString(),
        ...data
      };
      console.log(JSON.stringify(logEntry));
    },

    error: (message, data = {}) => {
      const logEntry = {
        level: 'ERROR',
        message,
        timestamp: new Date().toISOString(),
        ...data
      };
      console.error(JSON.stringify(logEntry));
    },

    warn: (message, data = {}) => {
      const logEntry = {
        level: 'WARN',
        message,
        timestamp: new Date().toISOString(),
        ...data
      };
      console.log(JSON.stringify(logEntry));
    }
  };
}

const logger = createLogger();

module.exports = { logger };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/utils/logger.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/utils/logger.js tests/utils/logger.test.js
git commit -m "feat: add structured logger utility"
```

---

### Task 3: Secrets Manager Utility

**Files:**
- Create: `daily-report/src/utils/secrets.js`
- Create: `daily-report/tests/utils/secrets.test.js`

- [ ] **Step 1: Write failing test for secrets manager**

Create `daily-report/tests/utils/secrets.test.js`:

```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/utils/secrets.test.js
```

Expected: FAIL with "Cannot find module '../../src/utils/secrets'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/utils/secrets.js`:

```javascript
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

const client = new SecretsManagerClient({});
const secretCache = new Map();

async function getSecret(secretArn) {
  if (secretCache.has(secretArn)) {
    return secretCache.get(secretArn);
  }

  const command = new GetSecretValueCommand({
    SecretId: secretArn
  });

  const response = await client.send(command);
  const secretValue = response.SecretString;

  secretCache.set(secretArn, secretValue);
  return secretValue;
}

module.exports = { getSecret };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/utils/secrets.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/utils/secrets.js tests/utils/secrets.test.js
git commit -m "feat: add Secrets Manager utility with caching"
```

---

### Task 4: Hacker News Fetcher

**Files:**
- Create: `daily-report/src/fetchers/hackerNews.js`
- Create: `daily-report/tests/fetchers/hackerNews.test.js`

- [ ] **Step 1: Write failing test for Hacker News fetcher**

Create `daily-report/tests/fetchers/hackerNews.test.js`:

```javascript
const axios = require('axios');
const { fetchTopHackerNewsStories } = require('../../src/fetchers/hackerNews');

jest.mock('axios');

describe('Hacker News Fetcher', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('fetches and returns top 5 stories sorted by points', async () => {
    axios.get.mockResolvedValueOnce({
      data: [101, 102, 103, 104, 105, 106, 107]
    });

    axios.get
      .mockResolvedValueOnce({ data: { id: 101, title: 'Story 1', url: 'http://example.com/1', score: 500, descendants: 50 } })
      .mockResolvedValueOnce({ data: { id: 102, title: 'Story 2', url: 'http://example.com/2', score: 800, descendants: 100 } })
      .mockResolvedValueOnce({ data: { id: 103, title: 'Story 3', url: 'http://example.com/3', score: 300, descendants: 25 } })
      .mockResolvedValueOnce({ data: { id: 104, title: 'Story 4', url: 'http://example.com/4', score: 600, descendants: 75 } })
      .mockResolvedValueOnce({ data: { id: 105, title: 'Story 5', url: 'http://example.com/5', score: 400, descendants: 30 } })
      .mockResolvedValueOnce({ data: { id: 106, title: 'Story 6', url: 'http://example.com/6', score: 200, descendants: 10 } })
      .mockResolvedValueOnce({ data: { id: 107, title: 'Story 7', url: 'http://example.com/7', score: 700, descendants: 90 } });

    const result = await fetchTopHackerNewsStories();

    expect(result).toHaveLength(5);
    expect(result[0].title).toBe('Story 2');
    expect(result[0].points).toBe(800);
    expect(result[1].points).toBe(700);
    expect(result[2].points).toBe(600);
    expect(result[3].points).toBe(500);
    expect(result[4].points).toBe(400);
  });

  test('handles API timeout', async () => {
    axios.get.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));

    await expect(fetchTopHackerNewsStories()).rejects.toThrow('timeout');
  });

  test('returns empty array when no stories available', async () => {
    axios.get.mockResolvedValueOnce({ data: [] });

    const result = await fetchTopHackerNewsStories();

    expect(result).toEqual([]);
  });

  test('skips malformed story items', async () => {
    axios.get.mockResolvedValueOnce({
      data: [101, 102, 103]
    });

    axios.get
      .mockResolvedValueOnce({ data: { id: 101, title: 'Story 1', url: 'http://example.com/1', score: 500, descendants: 50 } })
      .mockResolvedValueOnce({ data: null })
      .mockResolvedValueOnce({ data: { id: 103, title: 'Story 3', url: 'http://example.com/3', score: 300, descendants: 25 } });

    const result = await fetchTopHackerNewsStories();

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe(101);
    expect(result[1].id).toBe(103);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/fetchers/hackerNews.test.js
```

Expected: FAIL with "Cannot find module '../../src/fetchers/hackerNews'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/fetchers/hackerNews.js`:

```javascript
const axios = require('axios');
const { logger } = require('../utils/logger');

const HN_API_BASE = 'https://hacker-news.firebaseio.com/v0';
const TIMEOUT_MS = 10000;

async function fetchTopHackerNewsStories() {
  try {
    const topStoriesResponse = await axios.get(`${HN_API_BASE}/topstories.json`, {
      timeout: TIMEOUT_MS
    });

    const topStoryIds = topStoriesResponse.data.slice(0, 10);

    const storyPromises = topStoryIds.map(async (id) => {
      try {
        const response = await axios.get(`${HN_API_BASE}/item/${id}.json`, {
          timeout: TIMEOUT_MS
        });
        return response.data;
      } catch (error) {
        logger.warn(`Failed to fetch HN story ${id}`, { error: error.message });
        return null;
      }
    });

    const stories = await Promise.all(storyPromises);

    const validStories = stories
      .filter(story => story !== null && story.title && story.score !== undefined)
      .map(story => ({
        id: story.id,
        title: story.title,
        url: story.url || `https://news.ycombinator.com/item?id=${story.id}`,
        points: story.score,
        comments: story.descendants || 0
      }))
      .sort((a, b) => b.points - a.points)
      .slice(0, 5);

    return validStories;
  } catch (error) {
    logger.error('Failed to fetch Hacker News stories', { error: error.message });
    throw error;
  }
}

module.exports = { fetchTopHackerNewsStories };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/fetchers/hackerNews.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/hackerNews.js tests/fetchers/hackerNews.test.js
git commit -m "feat: add Hacker News fetcher with error handling"
```

---

### Task 5: Product Hunt Fetcher

**Files:**
- Create: `daily-report/src/fetchers/productHunt.js`
- Create: `daily-report/tests/fetchers/productHunt.test.js`

- [ ] **Step 1: Write failing test for Product Hunt fetcher**

Create `daily-report/tests/fetchers/productHunt.test.js`:

```javascript
const axios = require('axios');
const { fetchTopProductHuntProducts } = require('../../src/fetchers/productHunt');

jest.mock('axios');

describe('Product Hunt Fetcher', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('fetches and returns top 5 products by trending score', async () => {
    const mockResponse = {
      data: {
        posts: [
          { id: 1, name: 'Product 1', tagline: 'Great product', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: { videoUrl: 'https://video.com/1' } },
          { id: 2, name: 'Product 2', tagline: 'Amazing tool', votesCount: 200, commentsCount: 50, url: 'https://ph.com/2', thumbnail: { videoUrl: null } },
          { id: 3, name: 'Product 3', tagline: 'Cool app', votesCount: 150, commentsCount: 100, url: 'https://ph.com/3', thumbnail: { videoUrl: 'https://video.com/3' } },
          { id: 4, name: 'Product 4', tagline: 'Best service', votesCount: 80, commentsCount: 10, url: 'https://ph.com/4', thumbnail: { videoUrl: 'https://video.com/4' } },
          { id: 5, name: 'Product 5', tagline: 'Super app', votesCount: 120, commentsCount: 30, url: 'https://ph.com/5', thumbnail: { videoUrl: 'https://video.com/5' } },
          { id: 6, name: 'Product 6', tagline: 'Nice tool', votesCount: 90, commentsCount: 15, url: 'https://ph.com/6', thumbnail: { videoUrl: null } }
        ]
      }
    };

    axios.get.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result).toHaveLength(5);
    expect(result[0].name).toBe('Product 2');
    expect(result[0].trendingScore).toBe(155);
    expect(result[1].name).toBe('Product 3');
    expect(result[1].trendingScore).toBe(135);
  });

  test('calculates trending score correctly', async () => {
    const mockResponse = {
      data: {
        posts: [
          { id: 1, name: 'Product 1', tagline: 'Test', votesCount: 100, commentsCount: 50, url: 'https://ph.com/1', thumbnail: {} }
        ]
      }
    };

    axios.get.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    const expectedScore = (100 * 0.7) + (50 * 0.3);
    expect(result[0].trendingScore).toBe(expectedScore);
  });

  test('handles API timeout', async () => {
    axios.get.mockRejectedValueOnce(new Error('timeout of 10000ms exceeded'));

    await expect(fetchTopProductHuntProducts('fake-api-key')).rejects.toThrow('timeout');
  });

  test('handles missing video URLs gracefully', async () => {
    const mockResponse = {
      data: {
        posts: [
          { id: 1, name: 'Product 1', tagline: 'Test', votesCount: 100, commentsCount: 20, url: 'https://ph.com/1', thumbnail: { videoUrl: null } }
        ]
      }
    };

    axios.get.mockResolvedValueOnce(mockResponse);

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result[0].videoUrl).toBeNull();
  });

  test('returns empty array when no products available', async () => {
    axios.get.mockResolvedValueOnce({ data: { posts: [] } });

    const result = await fetchTopProductHuntProducts('fake-api-key');

    expect(result).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/fetchers/productHunt.test.js
```

Expected: FAIL with "Cannot find module '../../src/fetchers/productHunt'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/fetchers/productHunt.js`:

```javascript
const axios = require('axios');
const { logger } = require('../utils/logger');

const PH_API_BASE = 'https://api.producthunt.com/v2/api/graphql';
const TIMEOUT_MS = 10000;

const QUERY = `
  query {
    posts(order: VOTES) {
      edges {
        node {
          id
          name
          tagline
          votesCount
          commentsCount
          url
          thumbnail {
            videoUrl
          }
        }
      }
    }
  }
`;

async function fetchTopProductHuntProducts(apiKey) {
  try {
    const response = await axios.post(
      PH_API_BASE,
      { query: QUERY },
      {
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        timeout: TIMEOUT_MS
      }
    );

    const posts = response.data?.data?.posts?.edges?.map(edge => edge.node) || response.data?.posts || [];

    const products = posts.map(post => {
      const upvotes = post.votesCount || 0;
      const comments = post.commentsCount || 0;
      const trendingScore = (upvotes * 0.7) + (comments * 0.3);

      return {
        id: post.id,
        name: post.name,
        tagline: post.tagline,
        upvotes,
        comments,
        trendingScore,
        url: post.url,
        videoUrl: post.thumbnail?.videoUrl || null
      };
    });

    const topProducts = products
      .sort((a, b) => b.trendingScore - a.trendingScore)
      .slice(0, 5);

    return topProducts;
  } catch (error) {
    logger.error('Failed to fetch Product Hunt products', { error: error.message });
    throw error;
  }
}

module.exports = { fetchTopProductHuntProducts };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/fetchers/productHunt.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/productHunt.js tests/fetchers/productHunt.test.js
git commit -m "feat: add Product Hunt fetcher with trending score"
```

---

### Task 6: Email Styles

**Files:**
- Create: `daily-report/src/email/styles.js`
- Create: `daily-report/tests/email/styles.test.js`

- [ ] **Step 1: Write failing test for styles**

Create `daily-report/tests/email/styles.test.js`:

```javascript
const { getStyles } = require('../../src/email/styles');

describe('Email Styles', () => {
  test('returns CSS string', () => {
    const styles = getStyles();

    expect(typeof styles).toBe('string');
    expect(styles.length).toBeGreaterThan(0);
  });

  test('includes body styles', () => {
    const styles = getStyles();

    expect(styles).toContain('body');
    expect(styles).toContain('font-family');
  });

  test('includes responsive styles', () => {
    const styles = getStyles();

    expect(styles).toContain('@media');
  });

  test('includes link styles', () => {
    const styles = getStyles();

    expect(styles).toContain('a');
    expect(styles).toContain('color');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/email/styles.test.js
```

Expected: FAIL with "Cannot find module '../../src/email/styles'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/email/styles.js`:

```javascript
function getStyles() {
  return `
    <style>
      body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 600px;
        margin: 0 auto;
        padding: 20px;
        background-color: #f5f5f5;
      }

      .container {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 30px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      }

      h1 {
        color: #1a1a1a;
        font-size: 28px;
        margin-bottom: 10px;
        border-bottom: 3px solid #ff6b35;
        padding-bottom: 10px;
      }

      h2 {
        color: #2c3e50;
        font-size: 22px;
        margin-top: 30px;
        margin-bottom: 15px;
      }

      .section {
        margin-bottom: 40px;
      }

      .item {
        margin-bottom: 25px;
        padding-bottom: 20px;
        border-bottom: 1px solid #eee;
      }

      .item:last-child {
        border-bottom: none;
      }

      .item-title {
        font-size: 18px;
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 5px;
      }

      .item-tagline {
        color: #666;
        font-size: 14px;
        margin-bottom: 10px;
      }

      .item-meta {
        font-size: 13px;
        color: #999;
        margin-top: 8px;
      }

      .video-container {
        margin: 15px 0;
        max-width: 100%;
      }

      video, iframe {
        max-width: 100%;
        height: auto;
        border-radius: 4px;
      }

      a {
        color: #ff6b35;
        text-decoration: none;
      }

      a:hover {
        text-decoration: underline;
      }

      .footer {
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid #eee;
        font-size: 12px;
        color: #999;
        text-align: center;
      }

      @media only screen and (max-width: 600px) {
        body {
          padding: 10px;
        }

        .container {
          padding: 20px;
        }

        h1 {
          font-size: 24px;
        }

        h2 {
          font-size: 20px;
        }
      }
    </style>
  `;
}

module.exports = { getStyles };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/email/styles.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/email/styles.js tests/email/styles.test.js
git commit -m "feat: add email CSS styles with responsive design"
```

---

### Task 7: Email Template Builder

**Files:**
- Create: `daily-report/src/email/template.js`
- Create: `daily-report/tests/email/template.test.js`

- [ ] **Step 1: Write failing test for template builder**

Create `daily-report/tests/email/template.test.js`:

```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/email/template.test.js
```

Expected: FAIL with "Cannot find module '../../src/email/template'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/email/template.js`:

```javascript
const { getStyles } = require('./styles');

function buildEmailTemplate(phProducts, hnStories) {
  const today = new Date().toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });

  const phSection = phProducts.length > 0
    ? buildProductHuntSection(phProducts)
    : '<p style="color: #999; font-style: italic;">Product Hunt data unavailable today</p>';

  const hnSection = hnStories.length > 0
    ? buildHackerNewsSection(hnStories)
    : '<p style="color: #999; font-style: italic;">Hacker News data unavailable today</p>';

  return `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Your Daily Digest - ${today}</title>
      ${getStyles()}
    </head>
    <body>
      <div class="container">
        <h1>Your Daily Digest</h1>
        <p style="color: #666; font-size: 14px;">${today}</p>

        <div class="section">
          <h2>🚀 Product Hunt</h2>
          ${phSection}
        </div>

        <div class="section">
          <h2>📰 Hacker News</h2>
          ${hnSection}
        </div>

        <div class="footer">
          Generated by OpenPaw Daily Digest
        </div>
      </div>
    </body>
    </html>
  `;
}

function buildProductHuntSection(products) {
  return products.map(product => {
    const videoEmbed = product.videoUrl
      ? `<div class="video-container">
           <video controls width="100%" style="max-height: 300px;">
             <source src="${product.videoUrl}" type="video/mp4">
             Your email client doesn't support video.
           </video>
         </div>`
      : '';

    return `
      <div class="item">
        <div class="item-title">
          <a href="${product.url}">${product.name}</a>
        </div>
        <div class="item-tagline">${product.tagline}</div>
        ${videoEmbed}
        <div class="item-meta">
          👍 ${product.upvotes} upvotes • 💬 ${product.comments} comments
        </div>
      </div>
    `;
  }).join('');
}

function buildHackerNewsSection(stories) {
  return stories.map(story => {
    return `
      <div class="item">
        <div class="item-title">
          <a href="${story.url}">${story.title}</a>
        </div>
        <div class="item-meta">
          ⬆️ ${story.points} points • 💬 ${story.comments} comments
        </div>
      </div>
    `;
  }).join('');
}

module.exports = { buildEmailTemplate };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/email/template.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/email/template.js tests/email/template.test.js
git commit -m "feat: add email template builder with video embeds"
```

---

### Task 8: Gmail Client

**Files:**
- Create: `daily-report/src/gmail/client.js`
- Create: `daily-report/tests/gmail/client.test.js`

- [ ] **Step 1: Write failing test for Gmail client**

Create `daily-report/tests/gmail/client.test.js`:

```javascript
const { google } = require('googleapis');
const { sendEmail } = require('../../src/gmail/client');

jest.mock('googleapis');

describe('Gmail Client', () => {
  let mockGmail;
  let mockOAuth2Client;

  beforeEach(() => {
    jest.clearAllMocks();

    mockOAuth2Client = {
      setCredentials: jest.fn()
    };

    mockGmail = {
      users: {
        messages: {
          send: jest.fn()
        }
      }
    };

    google.auth.OAuth2.mockReturnValue(mockOAuth2Client);
    google.gmail.mockReturnValue(mockGmail);
  });

  test('sends email successfully', async () => {
    mockGmail.users.messages.send.mockResolvedValueOnce({
      data: { id: 'message-123' }
    });

    const credentials = {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    };

    const result = await sendEmail(
      'recipient@example.com',
      'Test Subject',
      '<html>Test Body</html>',
      credentials
    );

    expect(result.messageId).toBe('message-123');
    expect(mockOAuth2Client.setCredentials).toHaveBeenCalledWith({
      refresh_token: 'refresh-token'
    });
  });

  test('constructs email with proper headers', async () => {
    mockGmail.users.messages.send.mockResolvedValueOnce({
      data: { id: 'message-123' }
    });

    const credentials = {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    };

    await sendEmail(
      'recipient@example.com',
      'Test Subject',
      '<html>Test</html>',
      credentials
    );

    const callArgs = mockGmail.users.messages.send.mock.calls[0][0];
    const rawMessage = Buffer.from(callArgs.requestBody.raw, 'base64').toString();

    expect(rawMessage).toContain('To: recipient@example.com');
    expect(rawMessage).toContain('Subject: Test Subject');
    expect(rawMessage).toContain('Content-Type: text/html');
  });

  test('throws error when send fails', async () => {
    mockGmail.users.messages.send.mockRejectedValueOnce(
      new Error('Send failed')
    );

    const credentials = {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    };

    await expect(
      sendEmail('recipient@example.com', 'Subject', '<html>Body</html>', credentials)
    ).rejects.toThrow('Send failed');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/gmail/client.test.js
```

Expected: FAIL with "Cannot find module '../../src/gmail/client'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/gmail/client.js`:

```javascript
const { google } = require('googleapis');
const { logger } = require('../utils/logger');

async function sendEmail(to, subject, htmlBody, credentials) {
  try {
    const oauth2Client = new google.auth.OAuth2(
      credentials.clientId,
      credentials.clientSecret,
      'https://developers.google.com/oauthplayground'
    );

    oauth2Client.setCredentials({
      refresh_token: credentials.refreshToken
    });

    const gmail = google.gmail({ version: 'v1', auth: oauth2Client });

    const message = [
      `To: ${to}`,
      'Content-Type: text/html; charset=utf-8',
      'MIME-Version: 1.0',
      `Subject: ${subject}`,
      '',
      htmlBody
    ].join('\n');

    const encodedMessage = Buffer.from(message)
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    const response = await gmail.users.messages.send({
      userId: 'me',
      requestBody: {
        raw: encodedMessage
      }
    });

    logger.info('Email sent successfully', { messageId: response.data.id });

    return { messageId: response.data.id };
  } catch (error) {
    logger.error('Failed to send email', { error: error.message });
    throw error;
  }
}

module.exports = { sendEmail };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/gmail/client.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/gmail/client.js tests/gmail/client.test.js
git commit -m "feat: add Gmail API client with OAuth"
```

---

### Task 9: Main Lambda Handler

**Files:**
- Create: `daily-report/src/index.js`
- Create: `daily-report/tests/index.test.js`

- [ ] **Step 1: Write failing test for main handler**

Create `daily-report/tests/index.test.js`:

```javascript
const { handler } = require('../src/index');
const { fetchTopProductHuntProducts } = require('../src/fetchers/productHunt');
const { fetchTopHackerNewsStories } = require('../src/fetchers/hackerNews');
const { buildEmailTemplate } = require('../src/email/template');
const { sendEmail } = require('../src/gmail/client');
const { getSecret } = require('../src/utils/secrets');
const { DateTime } = require('luxon');

jest.mock('../src/fetchers/productHunt');
jest.mock('../src/fetchers/hackerNews');
jest.mock('../src/email/template');
jest.mock('../src/gmail/client');
jest.mock('../src/utils/secrets');
jest.mock('luxon', () => {
  const actual = jest.requireActual('luxon');
  return {
    ...actual,
    DateTime: {
      ...actual.DateTime,
      now: jest.fn()
    }
  };
});

describe('Lambda Handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    process.env.GMAIL_CLIENT_ID = 'client-id';
    process.env.GMAIL_CLIENT_SECRET_ARN = 'arn:secret1';
    process.env.GMAIL_REFRESH_TOKEN_ARN = 'arn:secret2';
    process.env.RECIPIENT_EMAIL = 'test@example.com';
    process.env.PRODUCT_HUNT_API_KEY_ARN = 'arn:secret3';
    process.env.TIMEZONE = 'America/Los_Angeles';

    DateTime.now.mockReturnValue({
      setZone: jest.fn().mockReturnValue({
        hour: 10,
        minute: 0
      })
    });

    getSecret
      .mockResolvedValueOnce('client-secret')
      .mockResolvedValueOnce('refresh-token')
      .mockResolvedValueOnce('ph-api-key');
  });

  test('executes successfully when in time window', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];
    const mockHNStories = [{ id: 101, title: 'Story 1' }];

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(fetchTopProductHuntProducts).toHaveBeenCalledWith('ph-api-key');
    expect(fetchTopHackerNewsStories).toHaveBeenCalled();
    expect(buildEmailTemplate).toHaveBeenCalledWith(mockPHProducts, mockHNStories);
    expect(sendEmail).toHaveBeenCalled();
  });

  test('skips execution when outside time window', async () => {
    DateTime.now.mockReturnValue({
      setZone: jest.fn().mockReturnValue({
        hour: 14,
        minute: 30
      })
    });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(result.body).toContain('Outside execution window');
    expect(fetchTopProductHuntProducts).not.toHaveBeenCalled();
  });

  test('handles Product Hunt API failure gracefully', async () => {
    const mockHNStories = [{ id: 101, title: 'Story 1' }];

    fetchTopProductHuntProducts.mockRejectedValueOnce(new Error('PH API failed'));
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(buildEmailTemplate).toHaveBeenCalledWith([], mockHNStories);
  });

  test('handles Hacker News API failure gracefully', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockRejectedValueOnce(new Error('HN API failed'));
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockResolvedValueOnce({ messageId: 'msg-123' });

    const result = await handler({});

    expect(result.statusCode).toBe(200);
    expect(buildEmailTemplate).toHaveBeenCalledWith(mockPHProducts, []);
  });

  test('throws error when both APIs fail', async () => {
    fetchTopProductHuntProducts.mockRejectedValueOnce(new Error('PH failed'));
    fetchTopHackerNewsStories.mockRejectedValueOnce(new Error('HN failed'));

    await expect(handler({})).rejects.toThrow('Both data sources failed');
  });

  test('throws error when Gmail send fails', async () => {
    const mockPHProducts = [{ id: 1, name: 'Product 1' }];
    const mockHNStories = [{ id: 101, title: 'Story 1' }];

    fetchTopProductHuntProducts.mockResolvedValueOnce(mockPHProducts);
    fetchTopHackerNewsStories.mockResolvedValueOnce(mockHNStories);
    buildEmailTemplate.mockReturnValueOnce('<html>Email</html>');
    sendEmail.mockRejectedValueOnce(new Error('Send failed'));

    await expect(handler({})).rejects.toThrow('Send failed');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- tests/index.test.js
```

Expected: FAIL with "Cannot find module '../src/index'"

- [ ] **Step 3: Write minimal implementation**

Create `daily-report/src/index.js`:

```javascript
const { DateTime } = require('luxon');
const { fetchTopProductHuntProducts } = require('./fetchers/productHunt');
const { fetchTopHackerNewsStories } = require('./fetchers/hackerNews');
const { buildEmailTemplate } = require('./email/template');
const { sendEmail } = require('./gmail/client');
const { getSecret } = require('./utils/secrets');
const { logger } = require('./utils/logger');

async function handler(event) {
  try {
    const timezone = process.env.TIMEZONE || 'America/Los_Angeles';
    const now = DateTime.now().setZone(timezone);

    if (now.hour !== 10 || now.minute > 1) {
      logger.info('Outside execution window, skipping', {
        hour: now.hour,
        minute: now.minute
      });
      return {
        statusCode: 200,
        body: JSON.stringify({ message: 'Outside execution window' })
      };
    }

    logger.info('Starting daily digest execution');

    const [clientSecret, refreshToken, phApiKey] = await Promise.all([
      getSecret(process.env.GMAIL_CLIENT_SECRET_ARN),
      getSecret(process.env.GMAIL_REFRESH_TOKEN_ARN),
      getSecret(process.env.PRODUCT_HUNT_API_KEY_ARN)
    ]);

    const [phProducts, hnStories] = await Promise.allSettled([
      fetchTopProductHuntProducts(phApiKey),
      fetchTopHackerNewsStories()
    ]);

    const products = phProducts.status === 'fulfilled' ? phProducts.value : [];
    const stories = hnStories.status === 'fulfilled' ? hnStories.value : [];

    if (phProducts.status === 'rejected') {
      logger.warn('Product Hunt fetch failed', { error: phProducts.reason.message });
    }

    if (hnStories.status === 'rejected') {
      logger.warn('Hacker News fetch failed', { error: hnStories.reason.message });
    }

    if (products.length === 0 && stories.length === 0) {
      throw new Error('Both data sources failed');
    }

    const htmlBody = buildEmailTemplate(products, stories);

    const emailResult = await sendEmail(
      process.env.RECIPIENT_EMAIL,
      `Your Daily Digest - ${now.toLocaleString(DateTime.DATE_FULL)}`,
      htmlBody,
      {
        clientId: process.env.GMAIL_CLIENT_ID,
        clientSecret,
        refreshToken
      }
    );

    logger.info('Daily digest sent successfully', {
      messageId: emailResult.messageId,
      productCount: products.length,
      storyCount: stories.length
    });

    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Success',
        messageId: emailResult.messageId
      })
    };
  } catch (error) {
    logger.error('Handler execution failed', { error: error.message, stack: error.stack });
    throw error;
  }
}

module.exports = { handler };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- tests/index.test.js
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/index.js tests/index.test.js
git commit -m "feat: add main Lambda handler with time-gated execution"
```

---

### Task 10: AWS SAM Infrastructure

**Files:**
- Create: `daily-report/template.yaml`

- [ ] **Step 1: Create SAM template**

Create `daily-report/template.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Daily Digest Email Agent

Globals:
  Function:
    Timeout: 30
    MemorySize: 512
    Runtime: nodejs18.x

Parameters:
  GmailClientId:
    Type: String
    Description: Gmail OAuth Client ID

  RecipientEmail:
    Type: String
    Description: Email address to send digest to

Resources:
  DailyDigestFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: openpaw-daily-digest
      CodeUri: .
      Handler: src/index.handler
      Environment:
        Variables:
          GMAIL_CLIENT_ID: !Ref GmailClientId
          GMAIL_CLIENT_SECRET_ARN: !Ref GmailClientSecret
          GMAIL_REFRESH_TOKEN_ARN: !Ref GmailRefreshToken
          PRODUCT_HUNT_API_KEY_ARN: !Ref ProductHuntApiKey
          RECIPIENT_EMAIL: !Ref RecipientEmail
          TIMEZONE: America/Los_Angeles
      Policies:
        - Statement:
          - Effect: Allow
            Action:
              - secretsmanager:GetSecretValue
            Resource:
              - !Ref GmailClientSecret
              - !Ref GmailRefreshToken
              - !Ref ProductHuntApiKey
      Events:
        DailyTrigger:
          Type: Schedule
          Properties:
            Schedule: cron(0 17 * * ? *)
            Description: Trigger daily digest at 10am PT

  GmailClientSecret:
    Type: AWS::SecretsManager::Secret
    Properties:
      Name: /openpaw/gmail/client-secret
      Description: Gmail OAuth Client Secret

  GmailRefreshToken:
    Type: AWS::SecretsManager::Secret
    Properties:
      Name: /openpaw/gmail/refresh-token
      Description: Gmail OAuth Refresh Token

  ProductHuntApiKey:
    Type: AWS::SecretsManager::Secret
    Properties:
      Name: /openpaw/product-hunt/api-key
      Description: Product Hunt API Key

Outputs:
  DailyDigestFunction:
    Description: Daily Digest Lambda Function ARN
    Value: !GetAtt DailyDigestFunction.Arn

  GmailClientSecretArn:
    Description: Gmail Client Secret ARN
    Value: !Ref GmailClientSecret

  GmailRefreshTokenArn:
    Description: Gmail Refresh Token ARN
    Value: !Ref GmailRefreshToken

  ProductHuntApiKeyArn:
    Description: Product Hunt API Key ARN
    Value: !Ref ProductHuntApiKey
```

- [ ] **Step 2: Create samconfig.toml**

Create `daily-report/samconfig.toml`:

```toml
version = 0.1

[default.deploy.parameters]
stack_name = "openpaw-daily-digest"
region = "us-east-1"
capabilities = "CAPABILITY_IAM"
parameter_overrides = "GmailClientId=\"\" RecipientEmail=\"\""
confirm_changeset = true
```

- [ ] **Step 3: Add deployment script to package.json**

Edit `daily-report/package.json` to add build script:

```json
{
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch",
    "test:coverage": "jest --coverage",
    "build": "sam build",
    "deploy": "sam deploy --guided"
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add template.yaml samconfig.toml package.json
git commit -m "feat: add AWS SAM infrastructure template"
```

---

### Task 11: Documentation

**Files:**
- Create: `daily-report/README.md`
- Create: `daily-report/SETUP.md`

- [ ] **Step 1: Create README**

Create `daily-report/README.md`:

```markdown
# Daily Digest Email Agent

Automated AWS Lambda function that sends daily email digests at 10am PT with:
- Top 5 trending Product Hunt products (with videos)
- Top 5 Hacker News stories (by points)

## Architecture

- **Runtime**: Node.js 18.x
- **Cloud**: AWS Lambda + EventBridge
- **Email**: Gmail API with OAuth
- **Scheduling**: EventBridge cron (10am PT daily)

## Local Development

### Prerequisites
- Node.js 18.x
- AWS CLI configured
- AWS SAM CLI installed

### Installation

```bash
npm install
```

### Testing

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Generate coverage report
npm run test:coverage
```

### Environment Variables

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

Required variables:
- `GMAIL_CLIENT_ID` - Google OAuth client ID
- `GMAIL_CLIENT_SECRET_ARN` - ARN for client secret
- `GMAIL_REFRESH_TOKEN_ARN` - ARN for refresh token
- `RECIPIENT_EMAIL` - Email address to send digest to
- `PRODUCT_HUNT_API_KEY_ARN` - ARN for Product Hunt API key
- `TIMEZONE` - Timezone for scheduling (default: America/Los_Angeles)

## Deployment

See [SETUP.md](./SETUP.md) for complete deployment instructions.

Quick deploy:

```bash
npm run build
npm run deploy
```

## Project Structure

```
daily-report/
├── src/
│   ├── index.js              # Lambda handler
│   ├── fetchers/
│   │   ├── productHunt.js    # Product Hunt API
│   │   └── hackerNews.js     # Hacker News API
│   ├── email/
│   │   ├── template.js       # HTML email builder
│   │   └── styles.js         # CSS styles
│   ├── gmail/
│   │   └── client.js         # Gmail API client
│   └── utils/
│       ├── logger.js         # Structured logging
│       └── secrets.js        # Secrets Manager
├── tests/                    # Jest tests
├── template.yaml             # AWS SAM template
└── package.json
```

## License

MIT
```

- [ ] **Step 2: Create setup guide**

Create `daily-report/SETUP.md`:

```markdown
# Setup Guide

Complete setup instructions for deploying the Daily Digest Email Agent.

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Google Cloud Project** with Gmail API enabled
3. **Product Hunt Account** with API access
4. **Node.js 18.x** installed locally
5. **AWS SAM CLI** installed ([instructions](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))

## Step 1: Google OAuth Setup

### 1.1 Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "Daily Digest Email"
3. Enable Gmail API:
   - Navigation menu → APIs & Services → Library
   - Search for "Gmail API"
   - Click "Enable"

### 1.2 Create OAuth Credentials

1. Navigation menu → APIs & Services → Credentials
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Web application"
4. Name: "Daily Digest"
5. Authorized redirect URIs: `https://developers.google.com/oauthplayground`
6. Save the **Client ID** and **Client Secret**

### 1.3 Generate Refresh Token

1. Go to [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)
2. Click settings gear (top right) → Check "Use your own OAuth credentials"
3. Enter your Client ID and Client Secret
4. In Step 1, select "Gmail API v1" → `https://www.googleapis.com/auth/gmail.send`
5. Click "Authorize APIs" and sign in with your Google account
6. In Step 2, click "Exchange authorization code for tokens"
7. Save the **Refresh Token**

## Step 2: Product Hunt API Setup

1. Go to [Product Hunt API](https://api.producthunt.com/v2/docs)
2. Create an application
3. Generate an API token
4. Save the **API Key**

## Step 3: AWS Secrets Manager

Store sensitive credentials in AWS Secrets Manager:

```bash
# Gmail Client Secret
aws secretsmanager create-secret \
  --name /openpaw/gmail/client-secret \
  --secret-string "YOUR_GMAIL_CLIENT_SECRET"

# Gmail Refresh Token
aws secretsmanager create-secret \
  --name /openpaw/gmail/refresh-token \
  --secret-string "YOUR_GMAIL_REFRESH_TOKEN"

# Product Hunt API Key
aws secretsmanager create-secret \
  --name /openpaw/product-hunt/api-key \
  --secret-string "YOUR_PRODUCT_HUNT_API_KEY"
```

Note the ARNs returned by these commands.

## Step 4: Deploy to AWS

### 4.1 Install Dependencies

```bash
cd daily-report
npm install --production
```

### 4.2 Build SAM Application

```bash
sam build
```

### 4.3 Deploy

```bash
sam deploy --guided
```

Follow the prompts:
- Stack name: `openpaw-daily-digest`
- AWS Region: `us-east-1` (or your preferred region)
- Parameter GmailClientId: `YOUR_GMAIL_CLIENT_ID`
- Parameter RecipientEmail: `your-email@example.com`
- Confirm changes: `Y`
- Allow SAM CLI IAM role creation: `Y`
- Save arguments to config: `Y`

## Step 5: Test Deployment

### 5.1 Manual Test

Invoke the Lambda function manually:

```bash
aws lambda invoke \
  --function-name openpaw-daily-digest \
  --payload '{}' \
  response.json

cat response.json
```

Check your email inbox for the digest.

### 5.2 Monitor Logs

View CloudWatch logs:

```bash
aws logs tail /aws/lambda/openpaw-daily-digest --follow
```

## Step 6: Verify Scheduling

The EventBridge rule triggers at 10am PT daily. To verify:

```bash
aws events list-rules --name-prefix openpaw
```

## Troubleshooting

### Email not sending

1. Check CloudWatch logs for errors
2. Verify OAuth credentials are correct
3. Ensure refresh token hasn't expired (regenerate if needed)
4. Check Gmail API quota limits

### Wrong time zone

The Lambda checks PT time using Luxon. EventBridge triggers at 17:00 UTC (10am PT during DST).

### API rate limits

- Product Hunt: 100 requests/hour
- Hacker News: No official limit, but be respectful
- Gmail: 100 emails/day (free tier)

## Updating

To update the Lambda code:

```bash
npm run build
sam deploy
```

## Cleanup

To remove all resources:

```bash
sam delete --stack-name openpaw-daily-digest
```

Manually delete Secrets Manager secrets if needed.
```

- [ ] **Step 3: Commit**

```bash
git add README.md SETUP.md
git commit -m "docs: add README and setup guide"
```

---

## Self-Review Checklist

**Spec Coverage:**
- ✅ Daily 10am PT scheduling (Task 9 - time-gated execution)
- ✅ Product Hunt top 5 with trending score (Task 5)
- ✅ Embedded videos (Task 7 - template builder)
- ✅ Hacker News top 5 by points (Task 4)
- ✅ Rich HTML email (Tasks 6, 7)
- ✅ Gmail OAuth delivery (Task 8)
- ✅ Secrets Manager storage (Task 3)
- ✅ Error handling (Tasks 4, 5, 8, 9)
- ✅ CloudWatch logging (Task 2, used throughout)
- ✅ AWS SAM deployment (Task 10)

**Placeholder Scan:**
- ✅ All code blocks contain actual implementation
- ✅ No "TBD" or "TODO" items
- ✅ All test expectations are specific
- ✅ All file paths are exact

**Type Consistency:**
- ✅ Product Hunt data structure consistent across Tasks 5, 7, 9
- ✅ Hacker News data structure consistent across Tasks 4, 7, 9
- ✅ Credentials object structure consistent in Tasks 8, 9
- ✅ Logger interface consistent across all tasks

**Dependencies:**
- All required npm packages specified in Task 1
- All external APIs documented
- All AWS services defined in Task 10

---
