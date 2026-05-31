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
