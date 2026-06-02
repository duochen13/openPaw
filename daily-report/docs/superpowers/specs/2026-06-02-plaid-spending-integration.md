# Plaid Spending Integration Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add credit card spending tracking to the daily digest email via Plaid API integration.

**Architecture:** New Plaid fetcher following existing pattern (Product Hunt, Hacker News), integrated into parallel data fetching pipeline. Spending section displays in email after daily joke, before Product Hunt.

**Tech Stack:** Plaid Node.js SDK (v18.x), AWS Secrets Manager for credentials, existing Lambda/SAM infrastructure.

---

## Overview

Integrate Plaid API to fetch yesterday's credit card transactions and display a spending summary in the daily digest email. The summary shows total spending and top 3 largest transactions.

**User Flow:**
1. User manually links credit card via Plaid (one-time setup, gets access token)
2. User stores Plaid credentials in AWS Secrets Manager
3. Daily Lambda execution fetches yesterday's transactions
4. Email displays: Total spending + top 3 transactions with merchant names
5. Gracefully degrades if Plaid fails or no transactions available

---

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────┐
│ Daily Lambda Execution (10am PT)                    │
│                                                       │
│  ┌───────────────────────────────────────────────┐ │
│  │ Secrets Manager (Parallel Fetch)              │ │
│  │ - Gmail credentials                            │ │
│  │ - Product Hunt API key/secret                  │ │
│  │ - Plaid client_id/secret/access_token (NEW)   │ │
│  └───────────────────────────────────────────────┘ │
│                    ↓                                 │
│  ┌───────────────────────────────────────────────┐ │
│  │ Data Fetchers (Promise.allSettled)            │ │
│  │ - fetchTopProductHuntProducts()                │ │
│  │ - fetchTopHackerNewsStories()                  │ │
│  │ - fetchPlaidSpending() (NEW)                   │ │
│  └───────────────────────────────────────────────┘ │
│                    ↓                                 │
│  ┌───────────────────────────────────────────────┐ │
│  │ Email Template Builder                         │ │
│  │ - Daily joke section                           │ │
│  │ - Spending summary (NEW)                       │ │
│  │ - Product Hunt section                         │ │
│  │ - Hacker News section                          │ │
│  └───────────────────────────────────────────────┘ │
│                    ↓                                 │
│  ┌───────────────────────────────────────────────┐ │
│  │ Gmail API - Send Email                         │ │
│  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Design Principles

1. **Fault Tolerance**: Use `Promise.allSettled()` so Plaid failure doesn't crash email delivery
2. **Graceful Degradation**: Show fallback message if Plaid fails or no transactions available
3. **Pattern Consistency**: Follow same code structure as existing fetchers (timeout, error handling, logging)
4. **Separation of Concerns**: Plaid fetcher handles API logic, template builder handles presentation

---

## Components

### 1. Plaid Fetcher (`src/fetchers/plaid.js`)

**Responsibility:** Fetch yesterday's credit card transactions from Plaid API.

**Interface:**
```javascript
async function fetchPlaidSpending(clientId, secret, accessToken, environment)
```

**Inputs:**
- `clientId` (string): Plaid client ID
- `secret` (string): Plaid secret
- `accessToken` (string): User's credit card access token
- `environment` (string): 'sandbox' | 'development' | 'production'

**Output:**
```javascript
{
  total: 87.43,  // Sum of all yesterday's transactions
  transactions: [
    {
      merchant: "Amazon.com",
      amount: 39.93,
      date: "2026-05-31",
      category: "Shopping"
    },
    {
      merchant: "Chipotle",
      amount: 18.50,
      date: "2026-05-31",
      category: "Dining"
    },
    {
      merchant: "Starbucks",
      amount: 14.00,
      date: "2026-05-31",
      category: "Dining"
    }
  ]
}
```

**Error Cases:**
- API failure → Return `{ total: 0, transactions: [] }`
- Timeout (>10s) → Return empty result
- No transactions → Return `{ total: 0, transactions: [] }` (normal for bank delays)

**Algorithm:**
1. Calculate yesterday's date range in Pacific Time:
   - Start: Yesterday at 00:00:00 PT
   - End: Yesterday at 23:59:59 PT
2. Initialize Plaid client with credentials and environment
3. Call `plaidClient.transactionsGet()` with date range
4. Extract transactions from response
5. Filter to only yesterday's date (double-check due to bank timezone variations)
6. Calculate total: sum of all transaction amounts
7. Sort by amount descending
8. Take top 3 transactions
9. Return formatted result

**Implementation Notes:**
- Use `luxon` for date calculations (consistent with existing timezone handling)
- Set 10-second timeout (matches Product Hunt/Hacker News)
- Use structured logging (`logger.info/warn/error`)
- Handle Plaid SDK errors gracefully (don't throw, return empty)

---

### 2. Email Template Updates (`src/email/template.js`)

**New Function:**
```javascript
function buildSpendingSummarySection(spendingData)
```

**Input:**
```javascript
{
  total: 87.43,
  transactions: [...]  // Top 3 transactions
}
```

**Output:** HTML string for spending section

**Template Design:**
```html
<div class="section" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
  <h2 style="color: white; margin-top: 0;">💰 Yesterday's Spending</h2>
  <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">$87.43</p>

  <div style="margin-top: 15px;">
    <p style="font-size: 14px; opacity: 0.9; margin-bottom: 8px;">Top Transactions:</p>
    <div style="font-size: 15px; line-height: 1.8;">
      🛍️ Amazon.com - $39.93<br>
      🍔 Chipotle - $18.50<br>
      ☕ Starbucks - $14.00
    </div>
  </div>
</div>
```

**Visual Design:**
- Green gradient background (money theme): `#10b981` to `#059669`
- White text for contrast
- Bold, large total amount
- Smaller transaction details with emoji icons
- Matches daily joke section styling (gradient card)

**Fallback Template** (when no transactions):
```html
<div class="section">
  <h2>💰 Yesterday's Spending</h2>
  <p style="color: #999; font-style: italic;">
    Spending data unavailable for yesterday
  </p>
</div>
```

**Integration into Main Template:**
```javascript
function buildEmailTemplate(phProducts, hnStories, spendingData) {
  // ... existing date and joke logic ...

  const spendingSection = spendingData.transactions.length > 0
    ? buildSpendingSummarySection(spendingData)
    : '<div class="section"><h2>💰 Yesterday\'s Spending</h2><p style="color: #999; font-style: italic;">Spending data unavailable for yesterday</p></div>';

  return `
    <!DOCTYPE html>
    <html lang="en">
    <head>...</head>
    <body>
      <div class="container">
        <h1>Your Daily Digest</h1>
        <p style="color: #666; font-size: 14px;">${today}</p>

        <!-- Daily Joke -->
        ${jokeSection}

        <!-- Spending Summary (NEW) -->
        ${spendingSection}

        <!-- Product Hunt -->
        ${phSection}

        <!-- Hacker News -->
        ${hnSection}

        <div class="footer">...</div>
      </div>
    </body>
    </html>
  `;
}
```

**Emoji Mapping** (for transaction categories):
- Shopping: 🛍️
- Dining: 🍔
- Coffee: ☕
- Transport: 🚗
- Entertainment: 🎬
- Other: 💳

---

### 3. Handler Integration (`src/index.js`)

**Changes Required:**

**1. Fetch Plaid Secrets:**
```javascript
const [
  clientSecret,
  refreshToken,
  phApiKey,
  phApiSecret,
  plaidClientId,    // NEW
  plaidSecret,      // NEW
  plaidAccessToken  // NEW
] = await Promise.all([
  getSecret(process.env.GMAIL_CLIENT_SECRET_ARN),
  getSecret(process.env.GMAIL_REFRESH_TOKEN_ARN),
  getSecret(process.env.PRODUCT_HUNT_API_KEY_ARN),
  getSecret(process.env.PRODUCT_HUNT_API_SECRET_ARN),
  getSecret(process.env.PLAID_CLIENT_ID_ARN),
  getSecret(process.env.PLAID_SECRET_ARN),
  getSecret(process.env.PLAID_ACCESS_TOKEN_ARN)
]);
```

**2. Fetch Spending Data:**
```javascript
const [phProducts, hnStories, spendingData] = await Promise.allSettled([
  fetchTopProductHuntProducts(phApiKey, phApiSecret),
  fetchTopHackerNewsStories(),
  fetchPlaidSpending(
    plaidClientId,
    plaidSecret,
    plaidAccessToken,
    process.env.PLAID_ENVIRONMENT || 'sandbox'
  )
]);

const products = phProducts.status === 'fulfilled' ? phProducts.value : [];
const stories = hnStories.status === 'fulfilled' ? hnStories.value : [];
const spending = spendingData.status === 'fulfilled'
  ? spendingData.value
  : { total: 0, transactions: [] };
```

**3. Pass to Template:**
```javascript
const htmlBody = buildEmailTemplate(products, stories, spending);
```

**4. Update Logging:**
```javascript
logger.info('Daily digest sent successfully', {
  messageId: emailResult.messageId,
  productCount: products.length,
  storyCount: stories.length,
  spendingTotal: spending.total,
  transactionCount: spending.transactions.length
});
```

**Error Handling:**
- Spending failure does NOT prevent email send (graceful degradation)
- Only fail if ALL three sources (PH, HN, Plaid) fail:
  ```javascript
  if (products.length === 0 && stories.length === 0 && spending.transactions.length === 0) {
    throw new Error('All data sources failed');
  }
  ```

---

## Data Flow

### Sequence Diagram

```
User           Lambda          Secrets Mgr      Plaid API      Gmail API
 |               |                  |               |              |
 |--10am PT----->|                  |               |              |
 |               |                  |               |              |
 |               |--Get Secrets---->|               |              |
 |               |<-Credentials-----|               |              |
 |               |                  |               |              |
 |               |--Get Transactions--------------->|              |
 |               |<-Yesterday's Txns----------------|              |
 |               |                  |               |              |
 |               |--Transform & Sort|               |              |
 |               |                  |               |              |
 |               |--Build Email-----|               |              |
 |               |                  |               |              |
 |               |--Send Email---------------------------->|       |
 |               |<-Message ID------------------------------|       |
 |               |                  |               |              |
 |<--Success-----|                  |               |              |
```

### Transaction Data Transformation

**Plaid API Response:**
```javascript
{
  transactions: [
    {
      transaction_id: "abc123",
      account_id: "xyz789",
      amount: 39.93,
      date: "2026-05-31",
      name: "Amazon.com",
      merchant_name: "Amazon",
      category: ["Shops", "Digital Purchase"],
      payment_channel: "online"
    },
    // ... more transactions
  ]
}
```

**Transformed to Internal Format:**
```javascript
{
  total: 87.43,
  transactions: [
    {
      merchant: "Amazon.com",
      amount: 39.93,
      date: "2026-05-31",
      category: "Shopping"
    }
  ]
}
```

**Category Mapping Logic:**
- Use first category from Plaid's category array
- Map Plaid categories to simplified names:
  - "Food and Drink" → "Dining"
  - "Shops" → "Shopping"
  - "Travel" → "Transport"
  - "Recreation" → "Entertainment"
  - Default → "Other"

---

## Error Handling

### Plaid API Errors

| Error Type | Plaid Code | Handling Strategy |
|------------|-----------|-------------------|
| Invalid access token | `INVALID_ACCESS_TOKEN` | Log error, return empty data, email shows "unavailable" |
| Rate limiting | `RATE_LIMIT_EXCEEDED` | Log warning, return empty data |
| Network timeout | - | Abort after 10s, return empty data |
| Authentication failure | `INVALID_CREDENTIALS` | Log error with "Check Plaid credentials", return empty data |
| Bank maintenance | `INSTITUTION_DOWN` | Log info, return empty data (normal) |

### Data Edge Cases

1. **No transactions for yesterday:**
   - Common due to bank posting delays (1-2 days)
   - Return `{ total: 0, transactions: [] }`
   - Email shows: "Spending data unavailable for yesterday"
   - NOT an error - this is expected behavior

2. **Less than 3 transactions:**
   - Show all available transactions (1-2)
   - Don't pad with empty slots

3. **Zero-amount transactions:**
   - Filter out transactions with `amount === 0`
   - These are pending or refunds

4. **Negative amounts (refunds):**
   - Include in total calculation (reduces total)
   - Display with negative sign: "-$15.00 refund"

### Logging Strategy

**Success:**
```javascript
logger.info('Plaid spending fetched', {
  transactionCount: 5,
  total: 87.43,
  dateRange: { start: '2026-05-31', end: '2026-05-31' }
});
```

**Warning (no transactions):**
```javascript
logger.warn('No Plaid transactions for yesterday', {
  date: '2026-05-31',
  reason: 'Bank posting delay or no spending'
});
```

**Error:**
```javascript
logger.error('Plaid API failed', {
  error: error.message,
  code: error.code,
  dateRange: { start: '2026-05-31', end: '2026-05-31' }
});
```

---

## Configuration and Deployment

### AWS Secrets Manager Setup

**Create three secrets manually:**

1. **Plaid Client ID:**
   ```bash
   aws secretsmanager create-secret \
     --name /openpaw/plaid/client-id \
     --secret-string "YOUR_PLAID_CLIENT_ID" \
     --region us-east-1
   ```

2. **Plaid Secret:**
   ```bash
   aws secretsmanager create-secret \
     --name /openpaw/plaid/secret \
     --secret-string "YOUR_PLAID_SECRET" \
     --region us-east-1
   ```

3. **Plaid Access Token:**
   ```bash
   aws secretsmanager create-secret \
     --name /openpaw/plaid/access-token \
     --secret-string "access-sandbox-xxx-yyy-zzz" \
     --region us-east-1
   ```

### SAM Template Updates (`template.yaml`)

**Add Parameters:**
```yaml
Parameters:
  # ... existing parameters ...

  PlaidClientIdArn:
    Type: String
    Description: ARN of Plaid client ID secret
    Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-XXXXX

  PlaidSecretArn:
    Type: String
    Description: ARN of Plaid secret
    Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-XXXXX

  PlaidAccessTokenArn:
    Type: String
    Description: ARN of Plaid access token secret
    Default: arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-XXXXX

  PlaidEnvironment:
    Type: String
    Description: Plaid environment
    Default: sandbox
    AllowedValues:
      - sandbox
      - development
      - production
```

**Add Environment Variables:**
```yaml
Resources:
  DailyDigestFunction:
    Type: AWS::Serverless::Function
    Properties:
      # ... existing properties ...
      Environment:
        Variables:
          # ... existing variables ...
          PLAID_CLIENT_ID_ARN: !Ref PlaidClientIdArn
          PLAID_SECRET_ARN: !Ref PlaidSecretArn
          PLAID_ACCESS_TOKEN_ARN: !Ref PlaidAccessTokenArn
          PLAID_ENVIRONMENT: !Ref PlaidEnvironment
```

**IAM Permissions:**
- Existing Secrets Manager policy already covers new secrets (no changes needed)

### Dependencies (`package.json`)

**Add Plaid SDK:**
```json
{
  "dependencies": {
    "plaid": "^18.0.0"
  }
}
```

### Deployment Steps

1. **Install Plaid SDK:**
   ```bash
   cd /Users/duochen/Desktop/career/openPaw/daily-report
   npm install plaid
   ```

2. **Create AWS Secrets:**
   - Run the three `aws secretsmanager create-secret` commands above
   - Note the ARNs returned for each secret

3. **Update SAM Config:**
   - Edit `template.yaml` with new parameters
   - Update ARN default values with actual ARNs from step 2

4. **Deploy:**
   ```bash
   sam build
   sam deploy
   ```
   - SAM will prompt for new parameter values
   - Accept defaults (ARNs already in template) or override

5. **Test:**
   ```bash
   aws lambda invoke \
     --function-name openpaw-daily-digest \
     --payload '{}' \
     response.json

   cat response.json
   ```

### Plaid Environment Options

| Environment | Description | Use Case |
|------------|-------------|----------|
| **sandbox** | Fake data, free | Initial testing and development |
| **development** | Real bank data, limited usage | Pre-production testing with real cards |
| **production** | Real bank data, full usage | Live production (requires Plaid approval) |

**Recommendation:** Start with `sandbox`, move to `development` once code is working, then request Plaid production access.

---

## Testing Strategy

### Unit Tests

**1. Plaid Fetcher Tests** (`tests/fetchers/plaid.test.js`):
- ✅ Successful transaction fetch
- ✅ Empty transactions (bank delay)
- ✅ API timeout
- ✅ Authentication failure
- ✅ Network error
- ✅ Correct total calculation
- ✅ Top 3 sorting (descending)
- ✅ Date range calculation (yesterday in PT)

**2. Email Template Tests** (`tests/email/template.test.js`):
- ✅ Spending section present when data available
- ✅ Fallback message when no transactions
- ✅ Correct transaction rendering
- ✅ Total amount formatting
- ✅ Section ordering (joke → spending → PH → HN)

**3. Handler Tests** (`tests/index.test.js`):
- ✅ Spending data passed to template
- ✅ Spending failure doesn't prevent email
- ✅ Logging includes spending metrics

### Integration Testing

**Manual Test Checklist:**
1. Deploy Lambda with sandbox credentials
2. Invoke Lambda manually
3. Verify email received with spending section
4. Check CloudWatch logs for Plaid API call
5. Test with invalid credentials (expect graceful failure)

### Monitoring

**CloudWatch Metrics:**
- Lambda execution time (should remain ~5-8 seconds)
- Plaid API call duration
- Transaction count per day
- Error rates

**Alarms:**
- Alert if Plaid fails >3 consecutive days
- Alert if spending total = $0 for >5 consecutive days (unusual)

---

## Security Considerations

### Credentials Management
- All Plaid credentials stored in AWS Secrets Manager (encrypted at rest)
- Access token is user-specific (links to user's credit card)
- Lambda IAM role has minimal permissions (Secrets Manager read-only)

### Data Privacy
- Transactions fetched daily, never stored permanently
- Only merchant name, amount, date shown in email (no account numbers)
- Email sent only to user's configured recipient address
- No transaction data logged (only counts and totals)

### Access Token Security
- Access token can be revoked by user via Plaid dashboard
- Token rotation not required (Plaid handles expiry)
- If token compromised, user revokes via Plaid, then updates secret

---

## Future Enhancements (Out of Scope)

1. **Budget tracking:** Compare to monthly budget
2. **Category breakdown:** Show spending by category pie chart
3. **Trend analysis:** Week-over-week, month-over-month changes
4. **Multiple cards:** Support multiple linked credit cards
5. **Spending alerts:** Notify if daily spending exceeds threshold
6. **Transaction storage:** Store in DynamoDB for historical analysis
7. **Custom categories:** User-defined category rules

---

## File Manifest

**New Files:**
- `src/fetchers/plaid.js` - Plaid API integration
- `tests/fetchers/plaid.test.js` - Plaid fetcher tests

**Modified Files:**
- `src/index.js` - Add Plaid to parallel fetch pipeline
- `src/email/template.js` - Add spending section builder
- `tests/index.test.js` - Add spending tests
- `tests/email/template.test.js` - Add spending template tests
- `template.yaml` - Add Plaid parameters and env vars
- `package.json` - Add Plaid SDK dependency

**Configuration Files:**
- `.env.example` - Document Plaid environment variables (for local testing)

---

## Success Criteria

1. ✅ Email includes spending section after daily joke
2. ✅ Shows yesterday's total spending and top 3 transactions
3. ✅ Gracefully handles Plaid API failures
4. ✅ Email still sends if Plaid is down
5. ✅ All tests pass (36 existing + 8 new = 44 total)
6. ✅ No increase in Lambda execution time (remains <10s)
7. ✅ No credentials logged or exposed
8. ✅ Production deployment successful with real credit card
