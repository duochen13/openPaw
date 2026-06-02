# Deployment Instructions

## Task 14: Create AWS Secrets ✅ (Script Ready)

### Your Plaid Credentials (Sandbox)
- **Client ID**: `6a1e7548b033d9000d7b75fd`
- **Secret**: `c6a87f97d2e2c9042eaafe0cef76a7`
- **Access Token**: `access-sandbox-2ae98c21-ddc5-4d8c-9518-89dea04590b5`

### Option 1: Run the Script (Recommended)
```bash
./scripts/create-aws-secrets.sh
```

This will create all 3 secrets and output their ARNs.

### Option 2: Manual Commands
If the script doesn't work, run these commands individually:

```bash
# Create Client ID secret
aws secretsmanager create-secret \
  --name /openpaw/plaid/client-id \
  --description "Plaid Client ID for daily digest" \
  --secret-string "6a1e7548b033d9000d7b75fd" \
  --region us-east-1

# Create Secret
aws secretsmanager create-secret \
  --name /openpaw/plaid/secret \
  --description "Plaid Secret for daily digest" \
  --secret-string "c6a87f97d2e2c9042eaafe0cef76a7" \
  --region us-east-1

# Create Access Token secret
aws secretsmanager create-secret \
  --name /openpaw/plaid/access-token \
  --description "Plaid Access Token for daily digest" \
  --secret-string "access-sandbox-2ae98c21-ddc5-4d8c-9518-89dea04590b5" \
  --region us-east-1
```

### Get the ARNs
After creating the secrets, get their full ARNs:

```bash
aws secretsmanager describe-secret --secret-id /openpaw/plaid/client-id --region us-east-1 --query 'ARN' --output text
aws secretsmanager describe-secret --secret-id /openpaw/plaid/secret --region us-east-1 --query 'ARN' --output text
aws secretsmanager describe-secret --secret-id /openpaw/plaid/access-token --region us-east-1 --query 'ARN' --output text
```

---

## Task 15: Update SAM Template with Real ARNs

After creating the secrets and getting their ARNs, you need to update `template.yaml`:

1. **Line 43**: Replace the Client ID ARN default
2. **Line 48**: Replace the Secret ARN default
3. **Line 53**: Replace the Access Token ARN default

The ARN format will be:
```
arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/client-id-XXXXXX
arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/secret-XXXXXX
arn:aws:secretsmanager:us-east-1:065424081594:secret:/openpaw/plaid/access-token-XXXXXX
```

Where `XXXXXX` is the 6-character suffix AWS generates (e.g., `hWktkd`).

---

## Task 16: Deploy to AWS

Once the template is updated with real ARNs:

```bash
# Build the Lambda package
sam build

# Deploy (first time - guided)
sam deploy --guided

# Follow prompts:
# - Stack Name: openpaw-daily-digest
# - AWS Region: us-east-1
# - Parameter GmailClientId: [your gmail client id]
# - Parameter RecipientEmail: [your email]
# - Confirm changes before deploy: Y
# - Allow SAM CLI IAM role creation: Y
# - Save arguments to configuration file: Y
```

For subsequent deploys:
```bash
sam build && sam deploy
```

---

## Task 17: Test Deployed Lambda

After deployment, test the Lambda function:

```bash
# Invoke the function
aws lambda invoke \
  --function-name openpaw-daily-digest \
  --region us-east-1 \
  output.json

# Check the output
cat output.json
```

Expected output:
```json
{
  "statusCode": 200,
  "body": "{\"message\":\"Success\",\"messageId\":\"...\"}"
}
```

Then check your email inbox for the daily digest with:
- Today's Tech Joke 😄
- Yesterday's Spending 💰
- Product Hunt products 🚀
- Hacker News stories 📰

---

## Troubleshooting

### If secrets already exist:
```bash
# Delete and recreate
aws secretsmanager delete-secret --secret-id /openpaw/plaid/client-id --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id /openpaw/plaid/secret --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id /openpaw/plaid/access-token --force-delete-without-recovery

# Then run create commands again
```

### If Lambda fails to invoke:
```bash
# Check CloudWatch logs
aws logs tail /aws/lambda/openpaw-daily-digest --follow
```

### If email doesn't send:
- Verify Gmail OAuth tokens are still valid
- Check Lambda execution role has secretsmanager:GetSecretValue permissions
- Verify all 7 secrets exist and are accessible
