# PDF Receipt Parsing - Quick Start

## Why This is Needed

Uber Eats changed their email format. Their receipts no longer include itemized order data in emails - just a total and a link to download a PDF.

**Before (old format):**
```
Order from: Chipotle
Burrito Bowl x1 - $11.50  ← Items in email
Chips x1 - $3.00          ← Parser can extract this
Total: $14.50
```

**Now (new format):**
```
Your receipt for Walmart
Total CA$56.86
To view your full receipt, download this PDF  ← No items in email!
```

## Solution: Manual PDF Download + Auto-Parsing

### Setup (One-Time)

1. **Create a folder for PDFs:**
```bash
mkdir -p ~/Downloads/uber-receipts
```

2. **Install pdf-parse package:**
```bash
cd /Users/duochen/Desktop/career/openPaw/daily-report
npm install pdf-parse
```

3. **Add to your `.env` file (optional):**
```bash
PDF_RECEIPTS_FOLDER=/Users/duochen/Downloads/uber-receipts
```

If not set, defaults to `~/Downloads/uber-receipts`

### Usage (Every Time You Order)

When you receive an Uber Eats receipt email:

1. **Click the link** in the email: "To view your full receipt go to Uber Eats, or download this PDF"
2. **Login to Uber Eats** if needed
3. **Download the PDF** to `~/Downloads/uber-receipts/`
4. **Done!** Next time your daily digest runs (10am daily), it will:
   - Detect the PDF-only email
   - Find the matching PDF by restaurant + total
   - Parse items from the PDF
   - Calculate calories/macros
   - Show in your email digest

## How It Works

### Matching Algorithm

```javascript
// Email receipt (from Gmail)
{
  restaurant: "Walmart",
  total: 56.86,
  items: [],        // Empty! No itemized data
  isPdfOnly: true   // Flag: needs PDF
}

// PDF receipt (from ~/Downloads/uber-receipts/receipt-123.pdf)
{
  restaurant: "Walmart (9251 Alderbridge Way)",
  total: 56.86,
  items: [
    { name: "Bananas", quantity: 2, price: 3.50 },
    { name: "Milk", quantity: 1, price: 5.99 },
    ...
  ]
}

// System matches by:
// 1. Restaurant name (fuzzy: "Walmart" matches "Walmart (address)")
// 2. Total amount (within $0.50: both are $56.86)
// ✅ Matched! Items merged into email receipt
```

### File Naming

PDFs can have any name - the system matches by content, not filename:
- ✅ `uber-eats-receipt-june-7.pdf`
- ✅ `Walmart_2026-06-07.pdf`
- ✅ `receipt-123.pdf`
- ✅ `download (2).pdf`

All will be parsed and matched automatically.

## What's Supported

### Platforms
- ✅ **Uber Eats** - PDF parsing (manual download required)
- ✅ **DoorDash** - Email parsing (still includes items in emails)
- ✅ **Grubhub** - Email parsing (still includes items in emails)

### PDF Parsing
The PDF parser extracts:
- Restaurant name
- Order timestamp
- Line items (name, quantity, price)
- Total amount

Supported formats:
- `1x Item Name $11.50`
- `Item Name x2 $23.00`
- `Item Name (details) $11.50`
- Canadian dollars: `CA$56.86`

## Troubleshooting

### "No PDFs found"
- Check folder path: `ls ~/Downloads/uber-receipts/`
- Check file extensions: PDFs must end with `.pdf`
- Check environment variable: `echo $PDF_RECEIPTS_FOLDER`

### "PDF parsed but not matched"
- Restaurant name might be too different (e.g., "McDonald's" vs "McD")
- Total amount might differ by >$0.50 (check email vs PDF)
- Check logs: `npm test` to see matching details

### "Items extracted but no nutrition data"
- Nutritionix API key not set (falls back to USDA)
- Item name too generic (e.g., "Meal")
- Solution: System uses default estimates as last resort

## Testing

To test the PDF parser without waiting for the daily digest:

```bash
# Run tests
npm test -- receiptParser.test.js

# Should see: 22 tests passing ✅
```

## Example Output

**In your daily digest email:**

```
🍔 Food Orders & Nutrition

Orders: 2
Total Calories: 1,456

Yesterday's Orders:
🚗 7:15pm - Walmart
  Bananas x2
  850 cal | 15g protein | 120g carbs | 20g fat

  Milk x1
  130 cal | 8g protein | 12g carbs | 5g fat

  Total: $56.86

Budget Status: ✅ Within budget ($8.14 remaining)
```

## Next Steps

See full documentation: [NUTRITION-TRACKING.md](./NUTRITION-TRACKING.md)
