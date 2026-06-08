/**
 * PDF Receipt Parser
 *
 * Reads manually downloaded Uber Eats PDF receipts from a local folder
 * and extracts itemized order data.
 */

const fs = require('fs').promises;
const path = require('path');
const pdfParse = require('pdf-parse');
const { logger } = require('../utils/logger');

/**
 * Parse all PDF receipts from a folder
 * @param {string} folderPath - Path to folder containing PDF receipts
 * @returns {Array} Array of parsed receipt objects
 */
async function parsePdfReceipts(folderPath) {
  try {
    // Check if folder exists
    try {
      await fs.access(folderPath);
    } catch (error) {
      logger.info('PDF receipts folder not found', { folderPath });
      return [];
    }

    // Read all files in folder
    const files = await fs.readdir(folderPath);
    const pdfFiles = files.filter(f => f.toLowerCase().endsWith('.pdf'));

    if (pdfFiles.length === 0) {
      logger.info('No PDF receipts found', { folderPath });
      return [];
    }

    logger.info('Found PDF receipts', { count: pdfFiles.length, folderPath });

    // Parse each PDF
    const results = [];
    for (const filename of pdfFiles) {
      try {
        const filePath = path.join(folderPath, filename);
        const parsed = await parseSinglePdf(filePath);
        if (parsed) {
          results.push({
            ...parsed,
            filename,
            filePath
          });
        }
      } catch (error) {
        logger.warn('Failed to parse PDF', { filename, error: error.message });
      }
    }

    logger.info('PDF receipts parsed', {
      total: pdfFiles.length,
      successful: results.length
    });

    return results;
  } catch (error) {
    logger.error('PDF parsing failed', { error: error.message });
    return [];
  }
}

/**
 * Parse a single PDF file
 * @param {string} filePath - Path to PDF file
 * @returns {Object|null} Parsed receipt data
 */
async function parseSinglePdf(filePath) {
  try {
    const dataBuffer = await fs.readFile(filePath);
    const data = await pdfParse(dataBuffer);
    const text = data.text;

    // Extract receipt data from text
    const platform = detectPlatformFromPdf(text);
    const restaurant = extractRestaurantFromPdf(text);
    const items = extractItemsFromPdf(text);
    const total = extractTotalFromPdf(text);
    const timestamp = extractTimestampFromPdf(text);

    if (!restaurant || items.length === 0) {
      logger.warn('Incomplete PDF data', { filePath, restaurant, itemCount: items.length });
      return null;
    }

    return {
      platform,
      restaurant,
      items,
      total,
      timestamp,
      source: 'pdf'
    };
  } catch (error) {
    logger.error('Failed to parse single PDF', { filePath, error: error.message });
    return null;
  }
}

/**
 * Detect platform from PDF text
 */
function detectPlatformFromPdf(text) {
  const textLower = text.toLowerCase();

  if (textLower.includes('uber eats') || textLower.includes('ubereats') ||
      (textLower.includes('uber') && textLower.includes("here's your receipt"))) {
    return 'UberEats';
  }
  if (textLower.includes('doordash')) {
    return 'DoorDash';
  }
  if (textLower.includes('grubhub')) {
    return 'Grubhub';
  }

  return 'Unknown';
}

/**
 * Extract restaurant name from PDF text
 */
function extractRestaurantFromPdf(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  // UberEats PDF format: "Here's your receipt for [Restaurant Name] (Location)."
  // Capture everything up to the opening parenthesis (includes numbers like "No.3")
  const receiptForMatch = text.match(/here'?s your receipt for\s+(.+?)\s*\(/i);
  if (receiptForMatch) {
    return receiptForMatch[1].trim();
  }

  // Alternative: "Order from [Restaurant Name]"
  const orderFromMatch = text.match(/order from\s+(.+?)(?:\n|$)/i);
  if (orderFromMatch) {
    return orderFromMatch[1].trim();
  }

  // Try finding restaurant name (usually within first 10 lines, before address/date)
  for (let i = 0; i < Math.min(10, lines.length); i++) {
    const line = lines[i];
    // Skip common headers and dates
    if (/^(uber|receipt|order|delivered|date|time|\d{1,2}\/\d{1,2}\/|thanks|here)/i.test(line)) {
      continue;
    }
    // Restaurant names are usually 5-80 chars (allowing for longer names with Chinese characters)
    if (line.length >= 5 && line.length <= 80 && !line.includes('@')) {
      return line;
    }
  }

  return 'Unknown Restaurant';
}

/**
 * Extract line items from PDF text
 */
function extractItemsFromPdf(text) {
  const items = [];
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  // UberEats PDF format (newer style):
  // Line 1: "1Edamame风味毛豆" (quantity + name, no space)
  // Line 2: "CA$7.75" (price on next line)

  for (let i = 0; i < lines.length - 1; i++) {
    const line = lines[i];
    const nextLine = lines[i + 1];

    // Skip headers, totals, fees, dates
    if (
      /^(items?|order|subtotal|delivery|tip|total|tax|fee|promo|service|payment|uber|saving|membership|visa|mastercard|amex|eats|pickup|thanks|here)/i.test(line) ||
      /(service fee|delivery fee|tax|tip|subtotal|total|discount|promo|benefit|payment)/i.test(line) ||
      /^\d{1,2}\/\d{1,2}\/\d{2,4}/.test(line) || // Date format
      /^\d{1,2}:\d{2}\s*(AM|PM)/i.test(line) || // Time format
      line.length < 3
    ) {
      continue;
    }

    // Pattern 1: "1ItemName" on one line, "CA$7.75" on next line
    const quantityItemMatch = line.match(/^(\d+)(.+)$/);
    const priceMatch = nextLine.match(/^(?:CA)?\$([0-9,]+\.?[0-9]{0,2})$/);

    if (quantityItemMatch && priceMatch) {
      const [, quantity, name] = quantityItemMatch;
      const price = priceMatch[1];

      items.push({
        name: name.trim(),
        quantity: parseInt(quantity, 10),
        price: parseFloat(price.replace(/,/g, ''))
      });
      i++; // Skip next line since we consumed it
      continue;
    }

    // Pattern 2: Traditional format "1x Name $11.50" on one line
    const traditionalPatterns = [
      /^(\d+)\s*x\s+(.+?)\s+(?:CA)?\$([0-9,]+\.?[0-9]{0,2})$/i,
      /^(.+?)\s+x(\d+)\s+(?:CA)?\$([0-9,]+\.?[0-9]{0,2})$/i,
      /^(.+?)\s+(?:CA)?\$([0-9,]+\.?[0-9]{2})$/i
    ];

    for (const pattern of traditionalPatterns) {
      const match = line.match(pattern);
      if (match) {
        let name, quantity, price;

        if (pattern === traditionalPatterns[0]) {
          [, quantity, name, price] = match;
        } else if (pattern === traditionalPatterns[1]) {
          [, name, quantity, price] = match;
        } else {
          [, name, price] = match;
          quantity = '1';
        }

        items.push({
          name: name.trim(),
          quantity: parseInt(quantity, 10),
          price: parseFloat(price.replace(/,/g, ''))
        });
        break;
      }
    }
  }

  return items;
}

/**
 * Extract total from PDF text
 */
function extractTotalFromPdf(text) {
  const lines = text.split('\n').map(l => l.trim());

  // Look for total line
  const totalLine = lines.find(l =>
    /^(order\s+)?total:?\s*(CA)?\$?[0-9,]+\.?[0-9]{0,2}$/i.test(l)
  );

  if (totalLine) {
    const match = totalLine.match(/(CA)?\$?([0-9,]+\.?[0-9]{0,2})$/i);
    if (match) {
      return parseFloat(match[2].replace(/,/g, ''));
    }
  }

  return null;
}

/**
 * Extract timestamp from PDF text
 */
function extractTimestampFromPdf(text) {
  // Common date/time patterns
  const datePatterns = [
    /\w+,\s+\w+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M/i,
    /\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M/i,
    /\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/
  ];

  for (const pattern of datePatterns) {
    const match = text.match(pattern);
    if (match) {
      const date = new Date(match[0]);
      if (!isNaN(date.getTime())) {
        return date.toISOString();
      }
    }
  }

  // Fallback: use file modification time or current time
  return new Date().toISOString();
}

/**
 * Match PDF receipts to email receipts
 * @param {Array} pdfReceipts - Parsed PDF receipts
 * @param {Array} emailReceipts - Email receipts that are PDF-only
 * @returns {Array} Matched receipts with PDF data merged in
 */
function matchPdfToEmailReceipts(pdfReceipts, emailReceipts) {
  const matched = [];

  for (const emailReceipt of emailReceipts) {
    if (!emailReceipt.isPdfOnly) {
      // Not a PDF-only receipt, no matching needed
      matched.push(emailReceipt);
      continue;
    }

    // Try to find matching PDF by restaurant and total
    const pdfMatch = pdfReceipts.find(pdf => {
      // Match by restaurant name (case-insensitive, fuzzy)
      const restaurantMatch =
        pdf.restaurant.toLowerCase().includes(emailReceipt.restaurant.toLowerCase()) ||
        emailReceipt.restaurant.toLowerCase().includes(pdf.restaurant.toLowerCase());

      // Match by total (within $0.50 tolerance for rounding)
      const totalMatch = emailReceipt.total && pdf.total &&
        Math.abs(emailReceipt.total - pdf.total) < 0.50;

      return restaurantMatch && totalMatch;
    });

    if (pdfMatch) {
      // Merge PDF data into email receipt
      matched.push({
        ...emailReceipt,
        items: pdfMatch.items,
        isPdfOnly: false, // Now we have items!
        requiresPdfParsing: false,
        pdfSource: pdfMatch.filename
      });
      logger.info('Matched PDF to email receipt', {
        restaurant: emailReceipt.restaurant,
        pdfFile: pdfMatch.filename
      });
    } else {
      // No match found, keep original
      matched.push(emailReceipt);
    }
  }

  return matched;
}

module.exports = {
  parsePdfReceipts,
  parseSinglePdf,
  matchPdfToEmailReceipts
};
