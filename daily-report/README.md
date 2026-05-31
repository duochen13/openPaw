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
