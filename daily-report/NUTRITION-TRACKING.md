# 🍔 Nutrition Tracking Integration

Automatic calorie tracking from food delivery orders (UberEats, DoorDash, Grubhub) integrated into your daily digest email.

## Overview

The nutrition tracking feature automatically:
1. **Parses email receipts** from food delivery platforms
2. **Matches items to nutrition data** using Nutritionix API (with USDA fallback)
3. **Tracks daily calories, macros, and spending** against your food budget
4. **Displays in daily digest** email with beautiful formatting

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

- **Complete test suite** (18 tests passing ✅)

### 🚧 What's Next

- **Gmail integration** to fetch receipts automatically
  - Currently returns empty data
  - Need to implement `fetchFoodOrdersFromEmail()`

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
│   ├── receiptParser.js     # Parse receipts (UberEats/DoorDash/Grubhub)
│   ├── nutrition.js          # Match to Nutritionix/USDA
│   └── foodOrders.js         # Orchestrator
└── email/
    └── template.js           # Updated with nutrition section

tests/
├── receiptParser.test.js    # 18 tests ✅
└── fixtures/
    └── sampleReceipts.js    # Sample UberEats/DoorDash/Grubhub receipts
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
- [x] Tests
- [ ] Gmail integration (auto-fetch receipts)
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
