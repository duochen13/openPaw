/**
 * Food Orders Fetcher
 *
 * Orchestrates receipt parsing and nutrition matching
 * This is the main entry point for the nutrition tracking feature
 */

const { parseDeliveryReceipt } = require('./receiptParser');
const { matchNutrition, calculateDailySummary } = require('./nutrition');
const { logger } = require('../utils/logger');
const path = require('path');
const os = require('os');

// Conditionally load PDF parser (requires pdf-parse package)
let parsePdfReceipts, matchPdfToEmailReceipts;
try {
  const pdfParser = require('./pdfParser');
  parsePdfReceipts = pdfParser.parsePdfReceipts;
  matchPdfToEmailReceipts = pdfParser.matchPdfToEmailReceipts;
} catch (error) {
  // pdf-parse not installed - PDF parsing will be skipped
  logger.info('PDF parser unavailable (pdf-parse not installed) - PDF-only receipts will not be parsed');
  parsePdfReceipts = async () => [];
  matchPdfToEmailReceipts = (pdfs, emails) => emails;
}

/**
 * Process a food delivery receipt email
 * @param {Object} email - { from, subject, body }
 * @returns {Object|null} Order with nutrition data or null
 */
async function processFoodOrderEmail(email) {
  try {
    // Parse receipt
    const parsedReceipt = await parseDeliveryReceipt(email);

    if (!parsedReceipt) {
      return null;
    }

    // Enrich with nutrition data
    const itemsWithNutrition = await matchNutrition(
      parsedReceipt.items,
      parsedReceipt.restaurant
    );

    return {
      ...parsedReceipt,
      items: itemsWithNutrition
    };
  } catch (error) {
    logger.error('Food order processing failed', {
      error: error.message,
      stack: error.stack
    });
    return null;
  }
}

/**
 * Process multiple food order emails from inbox
 * @param {Array} emails - Array of email objects
 * @returns {Object} { orders: [], summary: {} }
 */
async function processFoodOrders(emails) {
  try {
    logger.info('Processing food order emails', { count: emails.length });

    const orders = [];

    for (const email of emails) {
      const order = await processFoodOrderEmail(email);
      if (order) {
        orders.push(order);
      }
    }

    const summary = calculateDailySummary(orders);

    logger.info('Food orders processed', {
      totalOrders: orders.length,
      totalCalories: summary.totalCalories,
      totalSpent: summary.totalSpent
    });

    return {
      orders,
      summary
    };
  } catch (error) {
    logger.error('Batch food order processing failed', {
      error: error.message,
      stack: error.stack
    });

    return {
      orders: [],
      summary: {
        totalOrders: 0,
        totalSpent: 0,
        totalCalories: 0,
        totalProtein: 0,
        totalCarbs: 0,
        totalFat: 0,
        ordersByPlatform: {},
        estimatedItems: 0
      }
    };
  }
}

/**
 * Fetch food orders from Gmail and process them
 * @param {Object} gmailCredentials - { clientId, clientSecret, refreshToken }
 * @returns {Object} { orders: [], summary: {} }
 */
async function fetchFoodOrdersFromEmail(gmailCredentials) {
  try {
    if (!gmailCredentials || !gmailCredentials.clientId) {
      logger.info('Gmail credentials not provided - returning empty data');
      return {
        orders: [],
        summary: {
          totalOrders: 0,
          totalSpent: 0,
          totalCalories: 0,
          totalProtein: 0,
          totalCarbs: 0,
          totalFat: 0,
          ordersByPlatform: {},
          estimatedItems: 0,
          pdfOnlyCount: 0
        }
      };
    }

    const { fetchDeliveryReceipts } = require('../gmail/receiptFetcher');

    logger.info('Fetching delivery receipts from Gmail');

    // Fetch receipts from last 24 hours
    const emails = await fetchDeliveryReceipts(gmailCredentials, 50);

    if (emails.length === 0) {
      logger.info('No delivery receipts found');
      return {
        orders: [],
        summary: {
          totalOrders: 0,
          totalSpent: 0,
          totalCalories: 0,
          totalProtein: 0,
          totalCarbs: 0,
          totalFat: 0,
          ordersByPlatform: {},
          estimatedItems: 0,
          pdfOnlyCount: 0
        }
      };
    }

    // Process emails through receipt parser
    const result = await processFoodOrders(emails);

    // Count PDF-only receipts BEFORE matching
    const pdfOnlyCountBefore = result.orders.filter(o => o.isPdfOnly).length;

    // Try to match PDF-only receipts with manually downloaded PDFs
    if (pdfOnlyCountBefore > 0) {
      const pdfFolderPath = process.env.PDF_RECEIPTS_FOLDER ||
        path.join(os.homedir(), 'Downloads', 'uber-receipts');

      logger.info('Attempting to match PDF-only receipts', {
        pdfOnlyCount: pdfOnlyCountBefore,
        pdfFolder: pdfFolderPath
      });

      // Parse PDFs from folder
      const pdfReceipts = await parsePdfReceipts(pdfFolderPath);

      if (pdfReceipts.length > 0) {
        // Match PDFs to email receipts
        result.orders = matchPdfToEmailReceipts(pdfReceipts, result.orders);

        // Re-enrich with nutrition data for newly matched items
        for (let i = 0; i < result.orders.length; i++) {
          const order = result.orders[i];
          if (order.pdfSource && order.items.length > 0) {
            // This order was matched from PDF, enrich with nutrition
            order.items = await matchNutrition(order.items, order.restaurant);
          }
        }

        // Recalculate summary with new data
        result.summary = calculateDailySummary(result.orders);
      }
    }

    // Count remaining PDF-only receipts AFTER matching
    const pdfOnlyCountAfter = result.orders.filter(o => o.isPdfOnly).length;
    result.summary.pdfOnlyCount = pdfOnlyCountAfter;

    if (pdfOnlyCountAfter > 0) {
      logger.warn(`${pdfOnlyCountAfter} PDF-only receipts still need manual PDFs`, {
        totalOrders: result.orders.length,
        pdfOnlyCount: pdfOnlyCountAfter,
        matched: pdfOnlyCountBefore - pdfOnlyCountAfter
      });
    }

    if (pdfOnlyCountBefore > pdfOnlyCountAfter) {
      logger.info('Successfully matched PDFs to email receipts', {
        matchedCount: pdfOnlyCountBefore - pdfOnlyCountAfter
      });
    }

    return result;
  } catch (error) {
    logger.error('Failed to fetch food orders from email', {
      error: error.message,
      stack: error.stack
    });

    return {
      orders: [],
      summary: {
        totalOrders: 0,
        totalSpent: 0,
        totalCalories: 0,
        totalProtein: 0,
        totalCarbs: 0,
        totalFat: 0,
        ordersByPlatform: {},
        estimatedItems: 0,
        pdfOnlyCount: 0
      }
    };
  }
}

module.exports = {
  processFoodOrderEmail,
  processFoodOrders,
  fetchFoodOrdersFromEmail
};
