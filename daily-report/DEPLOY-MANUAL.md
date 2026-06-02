# Manual Deployment Guide (SAM CLI Issue Workaround)

## Issue

Your AWS SAM CLI has a Python 3.14/libexpat compatibility issue that prevents `sam build` and `sam deploy` from running.

## Solution Options

### Option 1: Fix SAM CLI (Recommended)

Try reinstalling AWS SAM CLI with a compatible Python version:

```bash
# Uninstall current SAM CLI
brew uninstall aws-sam-cli

# Install again (will use compatible Python)
brew install aws-sam-cli

# Verify it works
sam --version
```

Then run:
```bash
sam build
sam deploy --guided
```

### Option 2: Deploy Using AWS Console

1. **Package the Lambda code manually:**
```bash
# Create deployment package
cd /Users/duochen/Desktop/career/openPaw/daily-report
zip -r function.zip src/ node_modules/ package.json package-lock.json
```

2. **Go to AWS Lambda Console:**
   - Navigate to: https://console.aws.amazon.com/lambda/home?region=us-east-1
   - Find function: `openpaw-daily-digest`
   - Click "Upload from" → ".zip file"
   - Upload `function.zip`

3. **Update environment variables in Lambda Console:**
   Add these to the function's environment variables:
   ```
   PLAID_CLIENT_ID_ARN=arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-ChMp7v
   PLAID_SECRET_ARN=arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-mZUbAR
   PLAID_ACCESS_TOKEN_ARN=arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-2vtVRz
   PLAID_ENVIRONMENT=sandbox
   ```

4. **Update IAM permissions:**
   - Go to Configuration → Permissions
   - Click on the execution role
   - Add inline policy with these permissions:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "secretsmanager:GetSecretValue",
         "Resource": [
           "arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-ChMp7v",
           "arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-mZUbAR",
           "arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-2vtVRz"
         ]
       }
     ]
   }
   ```

### Option 3: Deploy Using CloudFormation CLI

```bash
# Package the template
aws cloudformation package \
  --template-file template.yaml \
  --s3-bucket YOUR_S3_BUCKET \
  --output-template-file packaged.yaml

# Deploy the stack
aws cloudformation deploy \
  --template-file packaged.yaml \
  --stack-name openpaw-daily-digest \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    GmailClientId=YOUR_GMAIL_CLIENT_ID \
    RecipientEmail=YOUR_EMAIL
```

### Option 4: Manual Lambda Update Script

I can create a Node.js script using AWS SDK to update the Lambda function directly:

```bash
node scripts/deploy-lambda.js
```

---

## After Deployment

Test the Lambda function:

### Using AWS Console:
1. Go to Lambda console
2. Click "Test" tab
3. Create new test event (empty JSON: `{}`)
4. Click "Test"
5. Check CloudWatch logs for output
6. Check your email for the digest

### Using AWS CLI (if working):
```bash
aws lambda invoke \
  --function-name openpaw-daily-digest \
  --region us-east-1 \
  output.json

cat output.json
```

### Check CloudWatch Logs:
```bash
aws logs tail /aws/lambda/openpaw-daily-digest --follow
```

---

## Expected Email Content

Your daily digest email should now include:
1. 😄 Today's Tech Joke
2. 💰 Yesterday's Spending (from Plaid sandbox)
   - Total amount
   - Top 3 transactions with categories
3. 🚀 Top 5 Product Hunt products
4. 📰 Top 5 Hacker News stories

---

## Troubleshooting

### "Permission denied" errors:
- Verify Lambda execution role has `secretsmanager:GetSecretValue` permission for all 3 Plaid secrets

### "All data sources failed" error:
- Check CloudWatch logs to see which data source failed
- Verify all 7 secrets exist and are readable

### No email received:
- Check Gmail OAuth tokens are still valid
- Verify RECIPIENT_EMAIL is set correctly
- Check CloudWatch logs for email sending errors

### Plaid data shows $0 or no transactions:
- This is expected for sandbox until you link a real account
- For testing, sandbox returns empty data by default
- You can use Plaid's test credentials in their Link UI to generate test transactions
