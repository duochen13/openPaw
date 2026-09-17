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
- `NOTION_API_KEY` (or `NOTION_API_KEY_ARN` on Lambda) + `NOTION_DAILY_REPORT_PAGE_ID` - sync digest items to a Notion subpage (see below); when unset, Notion sync is skipped

## Notion Daily Report (optional)

Each digest run can also write that day's Product Hunt products and Hacker News
stories into Notion: a subpage titled `MM-DD` (e.g. `09-17`) under your
**Daily Report** page, with the items as linked bullets grouped by source.
Re-runs never duplicate content — a subpage that already has content is left
alone.

### 1. Create a Notion integration

1. Go to https://www.notion.so/my-account/integrations → **New integration**
2. Give it a name (e.g. `Daily Digest`), pick your workspace
3. Copy the **Internal Integration Token** → set as `NOTION_API_KEY`

### 2. Share the Daily Report page with the integration

Open your **Daily Report** page → **Share** → invite your integration (search by
the name you gave it in step 1) → **Can edit**. Without this, the API returns
"object not found" errors.

### 3. Configure

Copy the page's ID from its URL
(`notion.so/Daily-Report-<PAGE_ID>` — the 32-char hex part) into:

```bash
NOTION_DAILY_REPORT_PAGE_ID=abc123...   # Daily Report page
```

For the Lambda deployment, store the token in AWS Secrets Manager and set
`NOTION_API_KEY_ARN` instead of `NOTION_API_KEY`.

The sync runs after the email is sent, creates (or reuses) the day's `MM-DD`
subpage, fills it only when it's empty, and is skipped entirely when the vars
are unset.

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
