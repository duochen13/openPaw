/**
 * Food Orders Fetcher
 *
 * Orchestrates receipt parsing and nutrition matching
 * This is the main entry point for the nutrition tracking feature
 */

const { parseDeliveryReceipt } = require('./receiptParser');
const { matchNutrition, calculateDailySummary } = require('./nutrition');
const { logger } = require('../utils/logger');

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
 * Mock function for testing - returns sample food orders
 * TODO: Replace with actual Gmail API integration
 */
async function fetchFoodOrdersFromEmail() {
  // For now, return empty data
  // This will be replaced with Gmail API call to fetch recent delivery receipts
  logger.info('Food orders fetch not yet implemented - returning empty data');

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

module.exports = {
  processFoodOrderEmail,
  processFoodOrders,
  fetchFoodOrdersFromEmail
};
