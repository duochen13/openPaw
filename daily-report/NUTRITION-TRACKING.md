# 🍔 Nutrition Tracking Integration

Automatic calorie tracking from food delivery orders (UberEats, DoorDash, Grubhub) integrated into your daily digest email.

## Overview

The nutrition tracking feature automatically:
1. **Fetches receipts from Gmail** - Automatically reads delivery emails from last 24 hours
2. **Parses email receipts** from food delivery platforms (UberEats, DoorDash, Grubhub)
3. **Matches items to nutrition data** using Nutritionix API (with USDA fallback)
4. **Parses PDF receipts** - For Uber Eats receipts without itemized data, download PDFs manually and they'll be auto-parsed
5. **Tracks daily calories, macros, and spending** against your food budget
6. **Displays in daily digest** email with beautiful formatting

---

## Quick Start

```bash
# Run tests
npm test -- receiptParser.test.js

# Expected output: 18 tests passing ✅
```

---

## Features

### ✅ What's Implemented

- **Multi-platform receipt parsing**
  - UberEats, DoorDash, Grubhub
  - Automatic platform detection
  - Extract: restaurant, items, prices, timestamp

- **Nutrition data integration**
  - Nutritionix API (800K+ restaurant items)
  - USDA FoodData Central (free fallback)
  - Default estimates for unknown items

- **Daily digest section**
  - Total orders, calories, protein, carbs, fat
  - Budget tracking ($32/day default)
  - Order-by-order breakdown
  - Estimate indicators

- **Gmail integration** ✅
  - Automatically fetches delivery receipts from last 24 hours
  - OAuth2 authentication

- **PDF receipt parsing** ✅
  - For Uber Eats receipts without itemized data
  - Manual download → automatic parsing

- **Complete test suite** (72 tests passing ✅)

---

## PDF Receipt Workflow (for Uber Eats)

**Why needed?** Uber Eats changed their email format - they no longer include itemized data in emails, only a total amount and a link to view the PDF.

### Setup

1. Create a folder for PDF receipts:
```bash
mkdir -p ~/Downloads/uber-receipts
```

2. Add to your `.env` file:
```bash
PDF_RECEIPTS_FOLDER=/Users/your-username/Downloads/uber-receipts
```

### Usage

When you receive an Uber Eats receipt email:

1. **Open the email** - Click "view full receipt" or "download PDF" link
2. **Download the PDF** - Save it to `~/Downloads/uber-receipts/`
3. **That's it!** - Next time the digest runs, it will:
   - Detect the PDF-only email receipt
   - Find the matching PDF by restaurant name and total
   - Parse the PDF to extract items
   - Match items to nutrition database
   - Show full calorie breakdown in your email

### How Matching Works

The system matches PDFs to email receipts by:
- Restaurant name (fuzzy matching)
- Total amount (within $0.50 tolerance)

Example:
```
Email: "Walmart - Total CA$56.86"
PDF: "Walmart (9251 Alderbridge Way) - $56.86 with 5 items"
✅ Matched! Items extracted from PDF
```

---

## Setup (Optional Nutritionix API)

**For best accuracy** (800K+ restaurant items):

1. Get API credentials at https://www.nutritionix.com/business/api

2. Add to AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name daily-digest/nutritionix-app-id \
  --secret-string "YOUR_APP_ID"

aws secretsmanager create-secret \
  --name daily-digest/nutritionix-api-key \
  --secret-string "YOUR_API_KEY"
```

3. Add to `template.yaml`:
```yaml
Environment:
  Variables:
    NUTRITIONIX_APP_ID_ARN: !Sub "arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:daily-digest/nutritionix-app-id"
    NUTRITIONIX_API_KEY_ARN: !Sub "arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:daily-digest/nutritionix-api-key"
    DAILY_FOOD_BUDGET: "32"
```

**Without Nutritionix:** System auto-falls back to USDA (free, less accurate for restaurants)

---

## File Structure

```
src/
├── fetchers/
│   ├── receiptParser.js     # Parse email receipts (UberEats/DoorDash/Grubhub)
│   ├── pdfParser.js         # Parse PDF receipts (NEW!)
│   ├── nutrition.js         # Match to Nutritionix/USDA
│   └── foodOrders.js        # Orchestrator (with PDF matching)
├── gmail/
│   └── receiptFetcher.js    # Fetch receipts from Gmail API
└── email/
    └── template.js          # Updated with nutrition section

tests/
├── receiptParser.test.js    # 22 tests ✅
├── fetchers/
│   └── plaid.test.js        # 6 tests ✅
├── index.test.js            # 7 tests ✅
└── fixtures/
    └── sampleReceipts.js    # Sample receipts (including PDF-only format)
```

---

## Testing

```javascript
const { parseDeliveryReceipt } = require('./src/fetchers/receiptParser');

const testReceipt = {
  from: 'uber.us@uber.com',
  subject: 'Your Uber Eats receipt',
  body: `
Order from: Chipotle Mexican Grill
Burrito Bowl (Chicken) x1 - $11.50
Order total: $11.50
  `
};

(async () => {
  const parsed = await parseDeliveryReceipt(testReceipt);
  console.log(parsed);
  // {
  //   platform: 'UberEats',
  //   restaurant: 'Chipotle Mexican Grill',
  //   items: [{ name: 'Burrito Bowl (Chicken)', quantity: 1, price: 11.50 }],
  //   total: 11.50,
  //   timestamp: '2026-06-07T...'
  // }
})();
```

---

## Roadmap

- [x] Receipt parser (UberEats/DoorDash/Grubhub)
- [x] Nutrition API integration
- [x] Email template
- [x] Budget tracking
- [x] Gmail integration (auto-fetch receipts)
- [x] PDF-only receipt detection
- [x] PDF receipt parsing (manual download)
- [ ] Test with real Uber Eats PDFs
- [ ] Weekly summaries
- [ ] Custom budgets per day

---

## Market Research Validation

Built based on research showing:
- ✅ 80% of calorie trackers fail due to manual entry
- ✅ ZERO competitors auto-import delivery orders
- ✅ 67% of consumers care about nutrition when ordering
- ✅ 24% of Bay Area orders after 6pm (office workers)

See parent directory: `/reports/calorie_tracking_delivery_report_*.md`

---

## License

MIT
