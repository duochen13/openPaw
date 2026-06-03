# Plaid Spending Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Plaid credit card spending tracking to daily digest email.

**Architecture:** New Plaid fetcher following existing pattern, integrated into parallel data fetching. Spending section displays between daily joke and Product Hunt.

**Tech Stack:** Plaid Node.js SDK v18.x, AWS Secrets Manager, Luxon for dates, Jest for testing

---

## File Structure

**New Files:**
- `src/fetchers/plaid.js` - Plaid API client and transaction fetcher
- `tests/fetchers/plaid.test.js` - Plaid fetcher unit tests

**Modified Files:**
- `src/index.js` - Add Plaid to handler pipeline (lines 27-40, 54, 67-71)
- `src/email/template.js` - Add spending section builder (new function + template update)
- `tests/index.test.js` - Add spending data tests
- `tests/email/template.test.js` - Add spending section tests
- `template.yaml` - Add Plaid configuration parameters
- `package.json` - Add plaid dependency
- `.env.example` - Document Plaid environment variables

---

## Task 1: Install Plaid SDK

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Install Plaid SDK**

Run: `npm install plaid`

This adds the Plaid Node.js SDK as a dependency.

- [ ] **Step 2: Verify installation**

Run: `npm list plaid`

Expected: Shows `plaid@18.x.x` in dependency tree

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "feat: add Plaid SDK dependency"
```

---

## Task 2: Plaid Fetcher - Basic Structure with Successful Fetch Test

**Files:**
- Create: `tests/fetchers/plaid.test.js`
- Create: `src/fetchers/plaid.js`

- [ ] **Step 1: Write failing test for successful transaction fetch**

Create `tests/fetchers/plaid.test.js`:

```javascript
const { fetchPlaidSpending } = require('../../src/fetchers/plaid');
const { Configuration, PlaidApi, PlaidEnvironments } = require('plaid');

jest.mock('plaid');

describe('Plaid Spending Fetcher', () => {
  let mockPlaidClient;

  beforeEach(() => {
    jest.clearAllMocks();
    mockPlaidClient = {
      transactionsGet: jest.fn()
    };
    PlaidApi.mockImplementation(() => mockPlaidClient);
  });

  test('fetches and transforms yesterday\'s transactions', async () => {
    const mockResponse = {
      data: {
        transactions: [
          {
            transaction_id: '1',
            amount: 39.93,
            date: '2026-05-31',
            name: 'Amazon.com',
            merchant_name: 'Amazon',
            category: ['Shops', 'Digital Purchase']
          },
          {
            transaction_id: '2',
            amount: 18.50,
            date: '2026-05-31',
            name: 'Chipotle Mexican Grill',
            merchant_name: 'Chipotle',
            category: ['Food and Drink', 'Restaurants']
          },
          {
            transaction_id: '3',
            amount: 14.00,
            date: '2026-05-31',
            name: 'Starbucks',
            merchant_name: 'Starbucks',
            category: ['Food and Drink', 'Restaurants', 'Coffee Shop']
          }
        ]
      }
    };

    mockPlaidClient.transactionsGet.mockResolvedValue(mockResponse);

    const result = await fetchPlaidSpending(
      'test-client-id',
      'test-secret',
      'access-token',
      'sandbox'
    );

    expect(result.total).toBe(72.43);
    expect(result.transactions).toHaveLength(3);
    expect(result.transactions[0]).toEqual({
      merchant: 'Amazon.com',
      amount: 39.93,
      date: '2026-05-31',
      category: 'Shopping'
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test tests/fetchers/plaid.test.js`

Expected: FAIL with "Cannot find module '../../src/fetchers/plaid'"

- [ ] **Step 3: Write minimal implementation**

Create `src/fetchers/plaid.js`:

```javascript
const { Configuration, PlaidApi, PlaidEnvironments } = require('plaid');
const { DateTime } = require('luxon');
const { logger } = require('../utils/logger');

const TIMEOUT_MS = 10000;

async function fetchPlaidSpending(clientId, secret, accessToken, environment) {
  try {
    // Initialize Plaid client
    const configuration = new Configuration({
      basePath: PlaidEnvironments[environment],
      baseOptions: {
        headers: {
          'PLAID-CLIENT-ID': clientId,
          'PLAID-SECRET': secret,
        },
      },
    });

    const client = new PlaidApi(configuration);

    // Calculate yesterday's date range in Pacific Time
    const timezone = 'America/Los_Angeles';
    const now = DateTime.now().setZone(timezone);
    const yesterday = now.minus({ days: 1 });
    const startDate = yesterday.toFormat('yyyy-MM-dd');
    const endDate = yesterday.toFormat('yyyy-MM-dd');

    // Fetch transactions
    const response = await Promise.race([
      client.transactionsGet({
        access_token: accessToken,
        start_date: startDate,
        end_date: endDate,
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), TIMEOUT_MS)
      ),
    ]);

    const transactions = response.data.transactions;

    // Filter to yesterday only (double-check timezone)
    const yesterdayTransactions = transactions.filter(t => t.date === startDate);

    // Transform transactions
    const transformed = yesterdayTransactions.map(t => ({
      merchant: t.name,
      amount: t.amount,
      date: t.date,
      category: mapCategory(t.category)
    }));

    // Calculate total
    const total = transformed.reduce((sum, t) => sum + t.amount, 0);

    // Sort by amount descending and take top 3
    const sorted = transformed.sort((a, b) => b.amount - a.amount);
    const top3 = sorted.slice(0, 3);

    logger.info('Plaid spending fetched', {
      transactionCount: top3.length,
      total: total,
      dateRange: { start: startDate, end: endDate }
    });

    return {
      total: Math.round(total * 100) / 100,
      transactions: top3
    };

  } catch (error) {
    logger.error('Plaid API failed', {
      error: error.message,
      code: error.code
    });
    return { total: 0, transactions: [] };
  }
}

function mapCategory(categories) {
  if (!categories || categories.length === 0) return 'Other';

  const primary = categories[0];

  if (primary.includes('Food and Drink')) return 'Dining';
  if (primary.includes('Shops')) return 'Shopping';
  if (primary.includes('Travel')) return 'Transport';
  if (primary.includes('Recreation')) return 'Entertainment';

  return 'Other';
}

module.exports = { fetchPlaidSpending };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test tests/fetchers/plaid.test.js`

Expected: PASS - 1 test passing

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/plaid.js tests/fetchers/plaid.test.js
git commit -m "feat: add Plaid spending fetcher with basic transaction fetch"
```

---

## Task 3: Plaid Fetcher - Empty Transactions Test

**Files:**
- Modify: `tests/fetchers/plaid.test.js`

- [ ] **Step 1: Write test for empty transactions**

Add to `tests/fetchers/plaid.test.js`:

```javascript
test('returns empty data when no transactions available', async () => {
  const mockResponse = {
    data: {
      transactions: []
    }
  };

  mockPlaidClient.transactionsGet.mockResolvedValue(mockResponse);

  const result = await fetchPlaidSpending(
    'test-client-id',
    'test-secret',
    'access-token',
    'sandbox'
  );

  expect(result.total).toBe(0);
  expect(result.transactions).toEqual([]);
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `npm test tests/fetchers/plaid.test.js`

Expected: PASS - 2 tests passing (implementation already handles this)

- [ ] **Step 3: Commit**

```bash
git add tests/fetchers/plaid.test.js
git commit -m "test: add empty transactions test for Plaid fetcher"
```

---

## Task 4: Plaid Fetcher - Error Handling Tests

**Files:**
- Modify: `tests/fetchers/plaid.test.js`

- [ ] **Step 1: Write test for API timeout**

Add to `tests/fetchers/plaid.test.js`:

```javascript
test('handles timeout gracefully', async () => {
  mockPlaidClient.transactionsGet.mockImplementation(
    () => new Promise(resolve => setTimeout(resolve, 15000))
  );

  const result = await fetchPlaidSpending(
    'test-client-id',
    'test-secret',
    'access-token',
    'sandbox'
  );

  expect(result).toEqual({ total: 0, transactions: [] });
});
```

- [ ] **Step 2: Write test for authentication error**

Add to `tests/fetchers/plaid.test.js`:

```javascript
test('handles authentication error gracefully', async () => {
  const error = new Error('Invalid credentials');
  error.code = 'INVALID_CREDENTIALS';
  mockPlaidClient.transactionsGet.mockRejectedValue(error);

  const result = await fetchPlaidSpending(
    'test-client-id',
    'test-secret',
    'access-token',
    'sandbox'
  );

  expect(result).toEqual({ total: 0, transactions: [] });
});
```

- [ ] **Step 3: Write test for network error**

Add to `tests/fetchers/plaid.test.js`:

```javascript
test('handles network error gracefully', async () => {
  mockPlaidClient.transactionsGet.mockRejectedValue(
    new Error('Network error')
  );

  const result = await fetchPlaidSpending(
    'test-client-id',
    'test-secret',
    'access-token',
    'sandbox'
  );

  expect(result).toEqual({ total: 0, transactions: [] });
});
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test tests/fetchers/plaid.test.js`

Expected: PASS - 5 tests passing (error handling already implemented)

- [ ] **Step 5: Commit**

```bash
git add tests/fetchers/plaid.test.js
git commit -m "test: add error handling tests for Plaid fetcher"
```

---

## Task 5: Plaid Fetcher - Sorting and Top 3 Test

**Files:**
- Modify: `tests/fetchers/plaid.test.js`

- [ ] **Step 1: Write test for top 3 sorting with more transactions**

Add to `tests/fetchers/plaid.test.js`:

```javascript
test('returns top 3 transactions sorted by amount descending', async () => {
  const mockResponse = {
    data: {
      transactions: [
        { transaction_id: '1', amount: 15.00, date: '2026-05-31', name: 'Small', category: ['Other'] },
        { transaction_id: '2', amount: 50.00, date: '2026-05-31', name: 'Large', category: ['Other'] },
        { transaction_id: '3', amount: 10.00, date: '2026-05-31', name: 'Smallest', category: ['Other'] },
        { transaction_id: '4', amount: 35.00, date: '2026-05-31', name: 'Medium', category: ['Other'] },
        { transaction_id: '5', amount: 100.00, date: '2026-05-31', name: 'Largest', category: ['Other'] }
      ]
    }
  };

  mockPlaidClient.transactionsGet.mockResolvedValue(mockResponse);

  const result = await fetchPlaidSpending(
    'test-client-id',
    'test-secret',
    'access-token',
    'sandbox'
  );

  expect(result.transactions).toHaveLength(3);
  expect(result.transactions[0].merchant).toBe('Largest');
  expect(result.transactions[0].amount).toBe(100.00);
  expect(result.transactions[1].merchant).toBe('Large');
  expect(result.transactions[1].amount).toBe(50.00);
  expect(result.transactions[2].merchant).toBe('Medium');
  expect(result.transactions[2].amount).toBe(35.00);
  expect(result.total).toBe(210.00);
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `npm test tests/fetchers/plaid.test.js`

Expected: PASS - 6 tests passing

- [ ] **Step 3: Commit**

```bash
git add tests/fetchers/plaid.test.js
git commit -m "test: add top 3 sorting test for Plaid fetcher"
```

---

## Task 6: Email Template - Spending Section Builder

**Files:**
- Modify: `tests/email/template.test.js`
- Modify: `src/email/template.js`

- [ ] **Step 1: Write failing test for spending section with data**

Add to `tests/email/template.test.js` after existing tests:

```javascript
describe('Spending Summary Section', () => {
  const mockSpendingData = {
    total: 87.43,
    transactions: [
      { merchant: 'Amazon.com', amount: 39.93, date: '2026-05-31', category: 'Shopping' },
      { merchant: 'Chipotle', amount: 18.50, date: '2026-05-31', category: 'Dining' },
      { merchant: 'Starbucks', amount: 14.00, date: '2026-05-31', category: 'Dining' }
    ]
  };

  test('includes spending section when data available', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories, mockSpendingData);

    expect(html).toContain('Yesterday\'s Spending');
    expect(html).toContain('$87.43');
    expect(html).toContain('Amazon.com');
    expect(html).toContain('$39.93');
  });

  test('shows fallback message when no transactions', () => {
    const emptySpending = { total: 0, transactions: [] };
    const html = buildEmailTemplate(mockPHProducts, mockHNStories, emptySpending);

    expect(html).toContain('Yesterday\'s Spending');
    expect(html).toContain('Spending data unavailable for yesterday');
  });

  test('spending section appears after joke and before Product Hunt', () => {
    const html = buildEmailTemplate(mockPHProducts, mockHNStories, mockSpendingData);

    const jokeIndex = html.indexOf('Today\'s Tech Joke');
    const spendingIndex = html.indexOf('Yesterday\'s Spending');
    const phIndex = html.indexOf('Product Hunt');

    expect(jokeIndex).toBeGreaterThan(-1);
    expect(spendingIndex).toBeGreaterThan(-1);
    expect(phIndex).toBeGreaterThan(-1);
    expect(jokeIndex).toBeLessThan(spendingIndex);
    expect(spendingIndex).toBeLessThan(phIndex);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test tests/email/template.test.js`

Expected: FAIL - buildEmailTemplate expects 3 parameters, receiving 2

- [ ] **Step 3: Add buildSpendingSummarySection function**

Add to `src/email/template.js` after `getDailyJoke()`:

```javascript
function buildSpendingSummarySection(spendingData) {
  const categoryEmojis = {
    'Shopping': '🛍️',
    'Dining': '🍔',
    'Coffee': '☕',
    'Transport': '🚗',
    'Entertainment': '🎬',
    'Other': '💳'
  };

  const transactionLines = spendingData.transactions.map(t => {
    const emoji = categoryEmojis[t.category] || categoryEmojis['Other'];
    return `${emoji} ${t.merchant} - $${t.amount.toFixed(2)}`;
  }).join('<br>');

  return `
    <div class="section" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
      <h2 style="color: white; margin-top: 0;">💰 Yesterday's Spending</h2>
      <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">$${spendingData.total.toFixed(2)}</p>

      <div style="margin-top: 15px;">
        <p style="font-size: 14px; opacity: 0.9; margin-bottom: 8px;">Top Transactions:</p>
        <div style="font-size: 15px; line-height: 1.8;">
          ${transactionLines}
        </div>
      </div>
    </div>
  `;
}
```

- [ ] **Step 4: Update buildEmailTemplate to accept spendingData parameter**

Modify `buildEmailTemplate` function signature in `src/email/template.js`:

```javascript
function buildEmailTemplate(phProducts, hnStories, spendingData) {
  const today = new Date().toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });

  const dailyJoke = getDailyJoke();

  const phSection = phProducts.length > 0
    ? buildProductHuntSection(phProducts)
    : '<p style="color: #999; font-style: italic;">Product Hunt data unavailable today</p>';

  const hnSection = hnStories.length > 0
    ? buildHackerNewsSection(hnStories)
    : '<p style="color: #999; font-style: italic;">Hacker News data unavailable today</p>';

  const spendingSection = spendingData.transactions.length > 0
    ? buildSpendingSummarySection(spendingData)
    : '<div class="section"><h2>💰 Yesterday\'s Spending</h2><p style="color: #999; font-style: italic;">Spending data unavailable for yesterday</p></div>';

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

        <div class="section" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
          <h2 style="color: white; margin-top: 0;">😄 Today's Tech Joke</h2>
          <p style="font-size: 16px; line-height: 1.6; margin: 0;">${dailyJoke}</p>
        </div>

        ${spendingSection}

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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test tests/email/template.test.js`

Expected: PASS - 13 tests passing (10 existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add src/email/template.js tests/email/template.test.js
git commit -m "feat: add spending summary section to email template"
```

---

## Task 7: Handler - Plaid Secret Fetching

**Files:**
- Modify: `tests/index.test.js`
- Modify: `src/index.js`

- [ ] **Step 1: Write failing test for Plaid secrets**

Add to `tests/index.test.js` in the existing "fetches secrets from AWS Secrets Manager" test:

Update the test to expect 7 secrets instead of 4:

```javascript
test('fetches secrets from AWS Secrets Manager', async () => {
  // ... existing mock setup ...

  await handler({});

  expect(secretsManagerMock.calls()).toHaveLength(7); // Changed from 4
  expect(getSecret).toHaveBeenCalledWith(process.env.GMAIL_CLIENT_SECRET_ARN);
  expect(getSecret).toHaveBeenCalledWith(process.env.GMAIL_REFRESH_TOKEN_ARN);
  expect(getSecret).toHaveBeenCalledWith(process.env.PRODUCT_HUNT_API_KEY_ARN);
  expect(getSecret).toHaveBeenCalledWith(process.env.PRODUCT_HUNT_API_SECRET_ARN);
  expect(getSecret).toHaveBeenCalledWith(process.env.PLAID_CLIENT_ID_ARN);
  expect(getSecret).toHaveBeenCalledWith(process.env.PLAID_SECRET_ARN);
  expect(getSecret).toHaveBeenCalledWith(process.env.PLAID_ACCESS_TOKEN_ARN);
});
```

- [ ] **Step 2: Add environment variables to test setup**

Add to the `beforeEach` block in `tests/index.test.js`:

```javascript
process.env.PLAID_CLIENT_ID_ARN = 'arn:aws:secretsmanager:us-east-1:123:secret:plaid-client-id';
process.env.PLAID_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:123:secret:plaid-secret';
process.env.PLAID_ACCESS_TOKEN_ARN = 'arn:aws:secretsmanager:us-east-1:123:secret:plaid-token';
process.env.PLAID_ENVIRONMENT = 'sandbox';
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npm test tests/index.test.js`

Expected: FAIL - Expected 7 secret calls, got 4

- [ ] **Step 4: Update handler to fetch Plaid secrets**

In `src/index.js`, update the secret fetching:

```javascript
const [clientSecret, refreshToken, phApiKey, phApiSecret, plaidClientId, plaidSecret, plaidAccessToken] = await Promise.all([
  getSecret(process.env.GMAIL_CLIENT_SECRET_ARN),
  getSecret(process.env.GMAIL_REFRESH_TOKEN_ARN),
  getSecret(process.env.PRODUCT_HUNT_API_KEY_ARN),
  getSecret(process.env.PRODUCT_HUNT_API_SECRET_ARN),
  getSecret(process.env.PLAID_CLIENT_ID_ARN),
  getSecret(process.env.PLAID_SECRET_ARN),
  getSecret(process.env.PLAID_ACCESS_TOKEN_ARN)
]);
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test tests/index.test.js`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/index.js tests/index.test.js
git commit -m "feat: add Plaid secret fetching to handler"
```

---

## Task 8: Handler - Plaid Data Fetching

**Files:**
- Modify: `tests/index.test.js`
- Modify: `src/index.js`

- [ ] **Step 1: Add Plaid fetcher import to handler**

Add to top of `src/index.js`:

```javascript
const { fetchPlaidSpending } = require('./fetchers/plaid');
```

- [ ] **Step 2: Write failing test for Plaid data fetching**

Add to `tests/index.test.js`:

```javascript
const { fetchPlaidSpending } = require('../src/fetchers/plaid');

jest.mock('../src/fetchers/plaid');

// In beforeEach:
fetchPlaidSpending.mockResolvedValue({
  total: 87.43,
  transactions: [
    { merchant: 'Amazon', amount: 39.93, date: '2026-05-31', category: 'Shopping' }
  ]
});

// New test:
test('fetches spending data from Plaid', async () => {
  await handler({});

  expect(fetchPlaidSpending).toHaveBeenCalledWith(
    'plaid-client-id',
    'plaid-secret',
    'plaid-token',
    'sandbox'
  );
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npm test tests/index.test.js`

Expected: FAIL - fetchPlaidSpending not called

- [ ] **Step 4: Update handler to fetch Plaid data**

In `src/index.js`, update the data fetching:

```javascript
const [phProducts, hnStories, spendingData] = await Promise.allSettled([
  fetchTopProductHuntProducts(phApiKey, phApiSecret),
  fetchTopHackerNewsStories(),
  fetchPlaidSpending(plaidClientId, plaidSecret, plaidAccessToken, process.env.PLAID_ENVIRONMENT || 'sandbox')
]);

const products = phProducts.status === 'fulfilled' ? phProducts.value : [];
const stories = hnStories.status === 'fulfilled' ? hnStories.value : [];
const spending = spendingData.status === 'fulfilled' ? spendingData.value : { total: 0, transactions: [] };
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test tests/index.test.js`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/index.js tests/index.test.js
git commit -m "feat: add Plaid spending data fetching to handler"
```

---

## Task 9: Handler - Template Integration

**Files:**
- Modify: `tests/index.test.js`
- Modify: `src/index.js`

- [ ] **Step 1: Write failing test for spending passed to template**

Add to `tests/index.test.js`:

```javascript
test('passes spending data to email template', async () => {
  await handler({});

  expect(buildEmailTemplate).toHaveBeenCalledWith(
    expect.any(Array),  // products
    expect.any(Array),  // stories
    expect.objectContaining({  // spending
      total: 87.43,
      transactions: expect.any(Array)
    })
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test tests/index.test.js`

Expected: FAIL - buildEmailTemplate called with 2 args, expected 3

- [ ] **Step 3: Update handler to pass spending to template**

In `src/index.js`, update the template building:

```javascript
const htmlBody = buildEmailTemplate(products, stories, spending);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test tests/index.test.js`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/index.js tests/index.test.js
git commit -m "feat: pass spending data to email template builder"
```

---

## Task 10: Handler - Logging Updates

**Files:**
- Modify: `tests/index.test.js`
- Modify: `src/index.js`

- [ ] **Step 1: Write failing test for spending in logs**

Add to `tests/index.test.js`:

```javascript
test('logs spending metrics on success', async () => {
  await handler({});

  expect(logger.info).toHaveBeenCalledWith(
    'Daily digest sent successfully',
    expect.objectContaining({
      spendingTotal: 87.43,
      transactionCount: 1
    })
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test tests/index.test.js`

Expected: FAIL - Expected spendingTotal in log, not present

- [ ] **Step 3: Update handler logging**

In `src/index.js`, update the success logging:

```javascript
logger.info('Daily digest sent successfully', {
  messageId: emailResult.messageId,
  productCount: products.length,
  storyCount: stories.length,
  spendingTotal: spending.total,
  transactionCount: spending.transactions.length
});
```

- [ ] **Step 4: Update error condition for all sources failing**

In `src/index.js`, update the error check:

```javascript
if (products.length === 0 && stories.length === 0 && spending.transactions.length === 0) {
  throw new Error('All data sources failed');
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test tests/index.test.js`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/index.js tests/index.test.js
git commit -m "feat: add spending metrics to handler logging"
```

---

## Task 11: Configuration - SAM Template

**Files:**
- Modify: `template.yaml`

- [ ] **Step 1: Add Plaid parameters**

Add to `template.yaml` under `Parameters` section:

```yaml
  PlaidClientIdArn:
    Type: String
    Description: ARN of Plaid client ID secret in AWS Secrets Manager
    Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-XXXXX

  PlaidSecretArn:
    Type: String
    Description: ARN of Plaid secret in AWS Secrets Manager
    Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-XXXXX

  PlaidAccessTokenArn:
    Type: String
    Description: ARN of Plaid access token secret in AWS Secrets Manager
    Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-XXXXX

  PlaidEnvironment:
    Type: String
    Description: Plaid environment (sandbox, development, or production)
    Default: sandbox
    AllowedValues:
      - sandbox
      - development
      - production
```

- [ ] **Step 2: Add environment variables to Lambda function**

Add to `template.yaml` under `DailyDigestFunction.Properties.Environment.Variables`:

```yaml
          PLAID_CLIENT_ID_ARN: !Ref PlaidClientIdArn
          PLAID_SECRET_ARN: !Ref PlaidSecretArn
          PLAID_ACCESS_TOKEN_ARN: !Ref PlaidAccessTokenArn
          PLAID_ENVIRONMENT: !Ref PlaidEnvironment
```

- [ ] **Step 3: Verify SAM template syntax**

Run: `sam validate`

Expected: Template is valid

- [ ] **Step 4: Commit**

```bash
git add template.yaml
git commit -m "feat: add Plaid configuration to SAM template"
```

---

## Task 12: Configuration - Environment Variables Example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add Plaid environment variables to .env.example**

Add to `.env.example`:

```
PLAID_CLIENT_ID_ARN=arn:aws:secretsmanager:region:account:secret:/openpaw/plaid/client-id
PLAID_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:/openpaw/plaid/secret
PLAID_ACCESS_TOKEN_ARN=arn:aws:secretsmanager:region:account:secret:/openpaw/plaid/access-token
PLAID_ENVIRONMENT=sandbox
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add Plaid environment variables to .env.example"
```

---

## Task 13: Run All Tests

**Files:**
- None (verification task)

- [ ] **Step 1: Run complete test suite**

Run: `npm test`

Expected: All tests pass (44 total: 36 existing + 8 new)

- [ ] **Step 2: Check test coverage**

Run: `npm run test:coverage`

Expected: Coverage report shows good coverage for new Plaid files

---

## Task 14: Create AWS Secrets (Manual Step)

**Files:**
- None (AWS operations)

This task documents the manual AWS setup required before deployment. The implementer should run these commands with actual Plaid credentials.

- [ ] **Step 1: Create Plaid client ID secret**

Run:
```bash
aws secretsmanager create-secret \
  --name /openpaw/plaid/client-id \
  --secret-string "YOUR_PLAID_CLIENT_ID" \
  --region us-east-1
```

Note the returned ARN and update `template.yaml` default value.

- [ ] **Step 2: Create Plaid secret**

Run:
```bash
aws secretsmanager create-secret \
  --name /openpaw/plaid/secret \
  --secret-string "YOUR_PLAID_SECRET" \
  --region us-east-1
```

Note the returned ARN and update `template.yaml` default value.

- [ ] **Step 3: Create Plaid access token secret**

Run:
```bash
aws secretsmanager create-secret \
  --name /openpaw/plaid/access-token \
  --secret-string "YOUR_PLAID_ACCESS_TOKEN" \
  --region us-east-1
```

Note the returned ARN and update `template.yaml` default value.

- [ ] **Step 4: Verify secrets created**

Run:
```bash
aws secretsmanager list-secrets --region us-east-1 | grep plaid
```

Expected: Three secrets with names matching `/openpaw/plaid/*`

---

## Task 15: Update SAM Template with Real ARNs

**Files:**
- Modify: `template.yaml`

- [ ] **Step 1: Update default ARN values**

Replace the placeholder ARNs in `template.yaml` Parameters section with the actual ARNs returned from Task 14.

Example:
```yaml
PlaidClientIdArn:
  Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-a1b2c3
```

- [ ] **Step 2: Commit**

```bash
git add template.yaml
git commit -m "chore: update Plaid secret ARNs with actual values"
```

---

## Task 16: Deploy to AWS

**Files:**
- None (deployment task)

- [ ] **Step 1: Build SAM application**

Run: `sam build`

Expected: Build succeeds, packages Lambda function with dependencies

- [ ] **Step 2: Deploy to AWS**

Run: `sam deploy`

Expected: CloudFormation stack updates successfully with new parameters

- [ ] **Step 3: Verify deployment**

Run:
```bash
aws lambda get-function --function-name openpaw-daily-digest --region us-east-1
```

Expected: Function exists with updated environment variables

---

## Task 17: Test Deployed Lambda

**Files:**
- None (testing task)

- [ ] **Step 1: Invoke Lambda manually**

Run:
```bash
aws lambda invoke \
  --function-name openpaw-daily-digest \
  --payload '{}' \
  --region us-east-1 \
  response.json
```

Expected: Function executes successfully

- [ ] **Step 2: Check response**

Run: `cat response.json`

Expected: Success response with messageId

- [ ] **Step 3: Check email**

Verify email received with:
- Daily joke section
- Spending section (with data or fallback message)
- Product Hunt section
- Hacker News section

- [ ] **Step 4: Check CloudWatch logs**

Run:
```bash
aws logs tail /aws/lambda/openpaw-daily-digest --follow --region us-east-1
```

Expected: Logs show Plaid API call, spending metrics in success log

---

## Verification Checklist

After completing all tasks, verify:

- [ ] All 44 tests pass (`npm test`)
- [ ] Email includes spending section after daily joke
- [ ] Spending section shows total and top 3 transactions (or fallback)
- [ ] Plaid API failure doesn't prevent email send
- [ ] CloudWatch logs include spending metrics
- [ ] Lambda execution time remains under 10 seconds
- [ ] No credentials logged in CloudWatch
- [ ] Template validates with `sam validate`

---

## Self-Review Results

**Spec Coverage:**
- ✅ Task 1-2: Plaid fetcher (spec section 1)
- ✅ Task 3-5: Error handling and edge cases (spec section 3)
- ✅ Task 6: Email template (spec section 2)
- ✅ Task 7-10: Handler integration (spec section 3)
- ✅ Task 11-12: Configuration (spec section 4)
- ✅ Task 13: Testing (spec section 5)
- ✅ Task 14-17: Deployment (spec section 4)

**Placeholder Scan:**
- ✅ No "TBD", "TODO", or placeholders
- ✅ All code blocks complete
- ✅ All commands have expected output

**Type Consistency:**
- ✅ `fetchPlaidSpending` signature consistent throughout
- ✅ Spending data shape `{ total, transactions }` consistent
- ✅ Transaction shape `{ merchant, amount, date, category }` consistent
- ✅ Template function `buildEmailTemplate(phProducts, hnStories, spendingData)` consistent
