/**
 * Receipt Parser for Food Delivery Platforms
 *
 * Parses email receipts from UberEats, DoorDash, and Grubhub
 * Extracts: restaurant, items, prices, timestamp, total
 */

const { logger } = require('../utils/logger');

/**
 * Platform detection patterns
 */
const PLATFORM_PATTERNS = {
  UBER_EATS: {
    name: 'UberEats',
    fromEmail: /@uber\.com/i,
    subject: /uber eats|your uber eats receipt/i,
    bodyMarkers: ['uber eats', 'ubereats.com', 'order from:']
  },
  DOORDASH: {
    name: 'DoorDash',
    fromEmail: /@doordash\.com/i,
    subject: /doordash|your doordash receipt/i,
    bodyMarkers: ['doordash', 'dasher', 'doordash.com']
  },
  GRUBHUB: {
    name: 'Grubhub',
    fromEmail: /@grubhub\.com/i,
    subject: /grubhub|your grubhub order/i,
    bodyMarkers: ['grubhub', 'grubhub.com']
  }
};

/**
 * Detect which delivery platform the receipt is from
 * @param {Object} email - Email object with from, subject, body
 * @returns {string|null} Platform name or null
 */
function detectPlatform(email) {
  const { from = '', subject = '', body = '' } = email;
  const bodyLower = body.toLowerCase();

  for (const [key, pattern] of Object.entries(PLATFORM_PATTERNS)) {
    // Check from email
    if (pattern.fromEmail.test(from)) {
      return pattern.name;
    }

    // Check subject
    if (pattern.subject.test(subject)) {
      return pattern.name;
    }

    // Check body markers
    if (pattern.bodyMarkers.some(marker => bodyLower.includes(marker.toLowerCase()))) {
      return pattern.name;
    }
  }

  return null;
}

/**
 * Extract restaurant name from receipt
 */
function extractRestaurant(body, platform) {
  const lines = body.split('\n').map(l => l.trim()).filter(Boolean);

  // UberEats: "Order from: Restaurant Name"
  if (platform === 'UberEats') {
    const orderFromLine = lines.find(l => l.toLowerCase().startsWith('order from:'));
    if (orderFromLine) {
      return orderFromLine.replace(/^order from:\s*/i, '').trim();
    }
  }

  // DoorDash: Usually restaurant name is early in the email
  if (platform === 'DoorDash') {
    const restaurantLine = lines.find(l =>
      l.length > 5 &&
      l.length < 50 &&
      !l.includes('DoorDash') &&
      !l.includes('Order') &&
      !l.includes('Delivery')
    );
    if (restaurantLine) return restaurantLine;
  }

  // Grubhub: "Your order from Restaurant Name"
  if (platform === 'Grubhub') {
    const orderFromLine = lines.find(l => l.toLowerCase().includes('your order from'));
    if (orderFromLine) {
      return orderFromLine.replace(/^.*your order from\s*/i, '').trim();
    }
  }

  return 'Unknown Restaurant';
}

/**
 * Extract line items from receipt
 * Returns array of { name, quantity, price }
 */
function extractItems(body, platform) {
  const items = [];
  const lines = body.split('\n').map(l => l.trim()).filter(Boolean);

  // Common patterns:
  // "Burrito Bowl (Chicken) x1 - $11.50"
  // "1x Burrito Bowl (Chicken) $11.50"
  // "Burrito Bowl (Chicken) $11.50"

  const itemPatterns = [
    // Pattern 1: "Name x1 - $11.50" or "Name x1 $11.50"
    /^(.+?)\s+x(\d+)\s*[-–]?\s*\$?([\d,]+\.?\d{0,2})$/i,
    // Pattern 2: "1x Name $11.50"
    /^(\d+)x\s+(.+?)\s+\$?([\d,]+\.?\d{0,2})$/i,
    // Pattern 3: "Name $11.50"
    /^(.+?)\s+\$?([\d,]+\.?\d{2})$/i
  ];

  for (const line of lines) {
    // Skip headers, totals, delivery, tip, fee lines
    if (
      /^(items?|order|subtotal|delivery|tip|total|tax|fee|promo)/i.test(line) ||
      /(service fee|delivery fee|tax|tip|subtotal|total)/i.test(line) ||
      line.length < 3
    ) {
      continue;
    }

    for (const pattern of itemPatterns) {
      const match = line.match(pattern);
      if (match) {
        let name, quantity, price;

        if (pattern === itemPatterns[0]) {
          // Pattern 1: Name x1 - $11.50
          [, name, quantity, price] = match;
        } else if (pattern === itemPatterns[1]) {
          // Pattern 2: 1x Name $11.50
          [, quantity, name, price] = match;
        } else {
          // Pattern 3: Name $11.50
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
 * Extract order total from receipt
 */
function extractTotal(body) {
  const lines = body.split('\n').map(l => l.trim());

  // Look for "Total: $XX.XX" or "Order total: $XX.XX"
  const totalLine = lines.find(l =>
    /^(order )?total:?\s*\$?[\d,]+\.?\d{0,2}$/i.test(l)
  );

  if (totalLine) {
    const match = totalLine.match(/\$?([\d,]+\.?\d{0,2})$/);
    if (match) {
      return parseFloat(match[1].replace(/,/g, ''));
    }
  }

  return null;
}

/**
 * Extract timestamp from receipt
 * Returns ISO string or current time if not found
 */
function extractTimestamp(body) {
  // Look for common date/time patterns
  // "Monday, June 6, 2026 7:15 PM"
  // "06/06/2026 7:15 PM"
  // "2026-06-06 19:15"

  const datePatterns = [
    /\w+,\s+\w+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M/i,
    /\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M/i,
    /\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/
  ];

  for (const pattern of datePatterns) {
    const match = body.match(pattern);
    if (match) {
      const date = new Date(match[0]);
      if (!isNaN(date.getTime())) {
        return date.toISOString();
      }
    }
  }

  // Fallback to current time
  return new Date().toISOString();
}

/**
 * Main parser function
 * @param {Object} email - { from, subject, body }
 * @returns {Object|null} Parsed receipt data or null if not a delivery receipt
 */
async function parseDeliveryReceipt(email) {
  try {
    const platform = detectPlatform(email);

    if (!platform) {
      logger.info('Email is not from a recognized delivery platform');
      return null;
    }

    const restaurant = extractRestaurant(email.body, platform);
    const items = extractItems(email.body, platform);
    const total = extractTotal(email.body);
    const timestamp = extractTimestamp(email.body);

    if (items.length === 0) {
      logger.warn('No items extracted from receipt', { platform, restaurant });
      return null;
    }

    const result = {
      platform,
      restaurant,
      items,
      total,
      timestamp,
      raw: {
        from: email.from,
        subject: email.subject
      }
    };

    logger.info('Receipt parsed successfully', {
      platform,
      restaurant,
      itemCount: items.length,
      total
    });

    return result;
  } catch (error) {
    logger.error('Receipt parsing failed', { error: error.message, stack: error.stack });
    return null;
  }
}

module.exports = {
  parseDeliveryReceipt,
  detectPlatform,
  extractRestaurant,
  extractItems,
  extractTotal,
  extractTimestamp
};
