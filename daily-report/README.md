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

Optional variables:
- `NOTION_API_KEY` (or `NOTION_API_KEY_ARN` on Lambda) + `NOTION_DATABASE_ID` - sync digest items to Notion (see below); when unset, Notion sync is skipped

## Notion Daily Calendar (optional)

Each digest run can also sync that day's Product Hunt products and Hacker News
stories into Notion: one row per item, plus (optionally) one calendar page per
day linking to its items. In Notion you can flip an item's `Status` to
`Reviewed` or `Interesting` — the sync never overwrites it.

### 1. Create a Notion integration

1. Go to https://www.notion.so/my-account/integrations → **New integration**
2. Give it a name (e.g. `Daily Digest`), pick your workspace
3. Copy the **Internal Integration Token** → set as `NOTION_API_KEY`

### 2. Create the databases

Create a database named **Daily Digest Items** with these exact properties:

| Property | Type | Notes |
|----------|------|-------|
| Name | Title | Product name / story title |
| Type | Select | Options: `Product Hunt`, `Hacker News` |
| URL | URL | Link to the product / story |
| Date | Date | The digest day |
| Score | Number | Trending score (PH) / points (HN) |
| Status | Select | Options: `New`, `Reviewed`, `Interesting` |
| Digest | Relation | → **Daily Digests** (only needed if you use step 3) |

Optionally, create a second database named **Daily Digests** for the
per-day calendar entries:

| Property | Type | Notes |
|----------|------|-------|
| Name | Title | e.g. `Daily Digest — 2026-09-17` |
| Date | Date | Add a Notion **Calendar view** on this property |

### 3. Share the databases with the integration

For each database: open it → **Share** → invite your integration (search by
the name you gave it in step 1) → **Can edit**. Without this, the API returns
"object not found" errors.

### 4. Configure

Copy each database's ID from its URL
(`notion.so/<workspace>/<DATABASE_ID>?v=...` — the 32-char hex part) into:

```bash
NOTION_DATABASE_ID=abc123...        # Daily Digest Items
NOTION_DIGEST_DATABASE_ID=def456...  # Daily Digests (optional)
```

For the Lambda deployment, store the token in AWS Secrets Manager and set
`NOTION_API_KEY_ARN` instead of `NOTION_API_KEY`.

The sync runs after the email is sent, upserts on `(Date, URL)` so re-runs
never duplicate rows, and is skipped entirely when the vars are unset.

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
│   ├── notion/
│   │   ├── index.js          # Notion module entrypoint
│   │   ├── config.js         # Env/ARN config resolution
│   │   └── sync.js           # Daily calendar upsert logic
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
