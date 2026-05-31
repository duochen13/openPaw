# Daily Digest Email Agent Design

**Date:** 2026-05-31
**Project:** OpenPaw Daily Digest
**Author:** AI Assistant

## Overview

An automated email agent that sends a daily digest at 10am PT containing:
- Top 5 trending products from Product Hunt (with embedded videos)
- Top 5 stories from Hacker News (by points)

The agent runs as an AWS Lambda function triggered by EventBridge on a daily schedule.

## Requirements

### Functional Requirements
- Send email daily at exactly 10am Pacific Time
- Include top 5 Product Hunt products ranked by combined score (upvotes × 0.7 + comments × 0.3)
- Include embedded videos for Product Hunt products where available
- Include top 5 Hacker News stories ranked by points
- Rich HTML email format with clean, responsive design
- Deliver via Gmail using OAuth authentication

### Non-Functional Requirements
- Execute reliably without manual intervention
- Complete within 30 seconds
- Handle API failures gracefully (partial data delivery)
- Secure credential storage
- Observable via CloudWatch logs

## Architecture

### High-Level Design

**AWS Lambda Function** (Node.js 18.x runtime) orchestrates the entire workflow:
1. Triggered by EventBridge rule at 10am PT daily
2. Fetches data from Product Hunt and Hacker News APIs in parallel
3. Builds rich HTML email template
4. Sends email via Gmail API using OAuth
5. Logs results to CloudWatch

**External Integrations:**
- Product Hunt API (product data and videos)
- Hacker News API (story data)
- Gmail API (email delivery)
- AWS Secrets Manager (OAuth credentials)

**AWS Resources:**
- Lambda function (512MB memory, 30s timeout)
- EventBridge rule (cron: `0 17 * * ? *` UTC = 10am PT)
- IAM role (Secrets Manager read, CloudWatch Logs write)
- Secrets Manager (Gmail OAuth tokens)
- Optional: SNS topic for failure alerts

### Component Structure

```
/src
  /index.js                  # Main handler - orchestrates workflow
  /fetchers
    /productHunt.js          # Fetch & rank Product Hunt products
    /hackerNews.js           # Fetch & rank Hacker News stories
  /email
    /template.js             # Generate HTML email
    /styles.js               # Inline CSS for email clients
  /gmail
    /client.js               # Gmail API OAuth & send logic
  /utils
    /logger.js               # Structured logging
    /secrets.js              # AWS Secrets Manager helper
```

**Main Handler (`index.js`):**
- Entry point for Lambda execution
- Orchestrates: fetch data (parallel) → build email → send email
- Error handling and logging
- Returns success/failure status

**Data Fetchers (`/fetchers/`):**

`productHunt.js`:
- Calls Product Hunt API to fetch today's products
- Calculates trending score: `(upvotes × 0.7) + (comments × 0.3)`
- Sorts by score descending, takes top 5
- Extracts: name, tagline, video URL, upvotes, comments, product URL
- Returns structured array

`hackerNews.js`:
- Calls Hacker News API to fetch top stories
- Fetches story details for each ID
- Sorts by points descending, takes top 5
- Extracts: title, URL, points, comments count
- Returns structured array

**Email Builder (`/email/`):**

`template.js`:
- Accepts Product Hunt and Hacker News data
- Generates rich HTML with:
  - Header: "Your Daily Digest - [Date]"
  - Product Hunt section: each product with embedded video (iframe/video tag), name, tagline, metrics, link
  - Hacker News section: each story with title, points, comments, link
  - Footer: minimal unsubscribe note
- Responsive design for mobile and desktop
- Returns HTML string

`styles.js`:
- Inline CSS for maximum email client compatibility
- Clean, readable typography
- Section spacing and borders
- Link styling

**Gmail Client (`/gmail/`):**

`client.js`:
- Retrieves OAuth credentials from Secrets Manager
- Exchanges refresh token for access token
- Constructs Gmail API request (to, subject, HTML body)
- Sends email via Gmail API
- Handles token refresh and retry logic
- Returns delivery status

## Data Flow

### Step 1: Trigger
EventBridge rule triggers Lambda at 10am PT (17:00 UTC) daily.

### Step 2: Data Collection (Parallel)
Using `Promise.all()` to minimize latency:
- **Product Hunt fetch**: API call → parse response → calculate trending scores → sort → extract top 5 with video URLs
- **Hacker News fetch**: API call → fetch story details → sort by points → extract top 5

### Step 3: Email Generation
Template builder receives both datasets:
- Constructs HTML structure
- Embeds Product Hunt videos using `<video>` or `<iframe>` tags
- Includes all product/story metadata
- Applies inline styles for email client compatibility

### Step 4: Email Delivery
Gmail client:
1. Retrieves OAuth refresh token from AWS Secrets Manager
2. Exchanges refresh token for access token
3. Sends email to configured recipient via Gmail API
4. Returns delivery confirmation

### Step 5: Response
Lambda returns success/failure status to EventBridge.
All execution details logged to CloudWatch.

## Error Handling

### API Failures

**Product Hunt API unavailable:**
- Log error to CloudWatch
- Send email with only Hacker News data
- Include note: "Product Hunt data unavailable today"

**Hacker News API unavailable:**
- Log error to CloudWatch
- Send email with only Product Hunt data
- Include note: "Hacker News data unavailable today"

**Both APIs unavailable:**
- Log error to CloudWatch
- Send fallback email: "Unable to fetch digest data today"
- Throw exception to trigger Lambda retry

### Gmail API Failures

**OAuth token refresh fails:**
- Log error with full details
- Throw exception (Lambda will retry)
- After retries exhausted → alert via SNS (optional)

**Send fails (rate limit, quota exceeded):**
- Log error
- Throw exception (Lambda retries up to 2 times with exponential backoff)
- After retries exhausted → alert via SNS (optional)

### Data Quality Issues

**Fewer than 5 products/stories available:**
- Send whatever data is available
- No error message needed

**Video URLs missing or broken:**
- Show product without video embed
- Include text link to product page only

**Malformed API responses:**
- Log parsing error
- Skip malformed items
- Continue with valid items

### Timeout Protection

- Lambda timeout: 30 seconds
- Individual API call timeout: 10 seconds each
- If approaching Lambda timeout, log partial results and exit gracefully
- CloudWatch alarm on timeout events

## Configuration

### Environment Variables

```
GMAIL_CLIENT_ID             # Google OAuth client ID
GMAIL_CLIENT_SECRET_ARN     # ARN for Secrets Manager secret
GMAIL_REFRESH_TOKEN_ARN     # ARN for Secrets Manager secret
RECIPIENT_EMAIL             # Target email address
PRODUCT_HUNT_API_KEY_ARN    # ARN for Secrets Manager secret (Product Hunt requires API authentication)
TIMEZONE                    # "America/Los_Angeles"
```

### Secrets Manager Entries

```
/openpaw/gmail/client-secret
/openpaw/gmail/refresh-token
/openpaw/product-hunt/api-key
```

### EventBridge Schedule

Cron expression: `0 17 * * ? *` (approximately 10am PT)

**DST Handling:**
Pacific Time observes DST, so the UTC offset changes:
- PST (winter): UTC-8 → 10am = 18:00 UTC
- PDT (summer): UTC-7 → 10am = 17:00 UTC

The Lambda will use the `luxon` library to calculate the current PT time and only execute the email send if it's between 9:59am and 10:01am PT. This ensures correct timing regardless of DST without needing to update EventBridge rules twice yearly.

EventBridge will trigger at 17:00 UTC year-round, and the Lambda will gate execution based on actual PT time.

## Deployment

### Prerequisites
1. Google Cloud project with Gmail API enabled
2. OAuth 2.0 credentials (client ID, client secret, refresh token)
3. AWS account with appropriate permissions
4. Node.js 18.x installed locally for development

### Infrastructure as Code
Use AWS SAM or Terraform to define:
- Lambda function with code package
- EventBridge rule with cron schedule
- IAM role with policies for Secrets Manager and CloudWatch
- Secrets Manager entries for credentials
- (Optional) SNS topic for failure alerts

### Deployment Steps

1. **Google OAuth Setup:**
   - Create Google Cloud project
   - Enable Gmail API
   - Create OAuth 2.0 credentials
   - Generate refresh token using OAuth playground or local flow
   - Store credentials in AWS Secrets Manager

2. **Package Lambda:**
   ```bash
   npm install --production
   zip -r function.zip .
   ```

3. **Deploy Infrastructure:**
   ```bash
   # Using SAM
   sam build
   sam deploy --guided

   # Or using Terraform
   terraform init
   terraform apply
   ```

4. **Test Execution:**
   ```bash
   aws lambda invoke \
     --function-name openpaw-daily-digest \
     --payload '{}' \
     response.json
   ```

5. **Verify Email Delivery:**
   Check inbox for test email, verify formatting and content.

6. **Monitor:**
   Set up CloudWatch dashboard for Lambda invocations, errors, duration.

## Testing Strategy

### Unit Tests
- Product Hunt fetcher: mock API responses, verify scoring logic
- Hacker News fetcher: mock API responses, verify sorting
- Email template: verify HTML structure, video embeds, data rendering
- Gmail client: mock OAuth flow, verify API calls

### Integration Tests
- End-to-end Lambda execution with real APIs (staging)
- OAuth token refresh flow
- Error scenarios (API failures, timeouts)

### Manual Testing
- Trigger Lambda manually via AWS Console
- Verify email delivery and formatting in Gmail client
- Test on mobile and desktop email clients
- Verify video embeds work correctly

## Future Enhancements (Out of Scope)

- User preferences for digest content (e.g., filter by category)
- Multiple recipients with individual preferences
- Web dashboard to view past digests
- Alternative delivery methods (Slack, SMS)
- Customizable scheduling (multiple times per day)
- Analytics on email open rates and link clicks

## Success Criteria

- Email delivered daily at 10am PT ±2 minutes
- Zero manual intervention required for 30 consecutive days
- 95% uptime (allowing for occasional API failures)
- Email formatting renders correctly in Gmail, Apple Mail, Outlook
- Videos play or link correctly in all supported email clients
- CloudWatch logs show clear success/failure status for each execution

## Open Questions

None - all requirements clarified during design phase.
