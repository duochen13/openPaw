# Plaid Production Setup Guide

## Current Status
- **Environment**: Sandbox
- **Client ID**: 6a1e7548b033d9000d7b75fd
- **Secret**: c6a87f97d2e2c9042eaafe0cef76a7 (sandbox)

## Steps to Enable Production

### 1. Request Production Access from Plaid

1. Go to: https://dashboard.plaid.com/team/keys
2. Log in to your Plaid account
3. Navigate to **Team Settings → Keys**
4. You should see:
   - **Sandbox** keys (what you have now)
   - **Development** keys (for testing with real banks, limited to 100 Items)
   - **Production** keys (requires approval)

### 2. Choose Environment

**Option A: Development Environment (Recommended First)**
- Use your real bank account
- Limited to 100 connected accounts
- No approval needed
- Perfect for personal use
- Free

**Option B: Production Environment**
- Unlimited accounts
- Requires Plaid approval
- May require business verification
- For commercial use

### 3. Get Your Production/Development Credentials

From the Plaid Dashboard:
```
Development Environment:
  Client ID: [same as sandbox]
  Secret: [different - starts with "development-"]

Production Environment:
  Client ID: [same as sandbox]
  Secret: [different - starts with "production-"]
```

### 4. Link Your Real Bank Account

You'll need to use Plaid Link to connect your actual credit card/bank:

**Option A: Use Plaid's Link Demo** (Easiest)
1. Go to: https://plaid.com/docs/link/
2. Use the Plaid Link web demo
3. Select your bank
4. Log in with real credentials
5. Get the `public_token`
6. Exchange for `access_token` using the script

**Option B: Build Plaid Link UI** (More work)
- Create a simple HTML page with Plaid Link
- User authenticates with their bank
- Get access token

### 5. Update Environment Variables

Once you have production/development credentials:

```bash
# Update AWS Secrets with production values
node scripts/create-production-secrets.js

# Update Lambda environment variable
PLAID_ENVIRONMENT=development  # or "production"
```

### 6. Important Notes

⚠️ **Security**:
- Production tokens access REAL financial data
- Never commit production credentials to git
- Store only in AWS Secrets Manager

⚠️ **Plaid Pricing**:
- Development: Free (limited to 100 Items)
- Production: May incur costs depending on usage
- Check: https://plaid.com/pricing/

⚠️ **Data Privacy**:
- You're accessing real transaction data
- Ensure compliance with financial data regulations
- Use proper security measures

## Quick Start: Development Environment

If you want to test with real data now:

1. Get your Development secret from Plaid Dashboard
2. Run this script to link your bank:
   ```bash
   PLAID_SECRET="development-xxxxx" node scripts/link-real-bank.js
   ```
3. Update AWS secrets with the new access token
4. Change PLAID_ENVIRONMENT to "development"
5. Test!

## Testing Connection

After setup:
```bash
# Check transactions from your real account
node scripts/check-plaid-transactions.js your-real-access-token

# Should show your actual spending!
```
