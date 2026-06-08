const { DateTime } = require('luxon');
const { fetchTopProductHuntProducts } = require('./fetchers/productHunt');
const { fetchTopHackerNewsStories } = require('./fetchers/hackerNews');
const { fetchPlaidSpending } = require('./fetchers/plaid');
const { buildEmailTemplate } = require('./email/template');
const { sendEmail } = require('./gmail/client');
const { getSecret } = require('./utils/secrets');
const { logger } = require('./utils/logger');

async function handler(event) {
  try {
    const timezone = process.env.TIMEZONE || 'America/Los_Angeles';
    const now = DateTime.now().setZone(timezone);

    if (now.hour !== 10 || now.minute > 1) {
      logger.info('Outside execution window, skipping', {
        hour: now.hour,
        minute: now.minute
      });
      return {
        statusCode: 200,
        body: JSON.stringify({ message: 'Outside execution window' })
      };
    }

    logger.info('Starting daily digest execution');

    const [clientSecret, refreshToken, phApiKey, phApiSecret, plaidClientId, plaidSecret, plaidAccessToken] = await Promise.all([
      getSecret(process.env.GMAIL_CLIENT_SECRET_ARN),
      getSecret(process.env.GMAIL_REFRESH_TOKEN_ARN),
      getSecret(process.env.PRODUCT_HUNT_API_KEY_ARN),
      getSecret(process.env.PRODUCT_HUNT_API_SECRET_ARN),
      getSecret(process.env.PLAID_CLIENT_ID_ARN),
      getSecret(process.env.PLAID_SECRET_ARN),
      getSecret(process.env.PLAID_ACCESS_TOKEN_ARN)
    ]);

    const [phProducts, hnStories, spendingData] = await Promise.allSettled([
      fetchTopProductHuntProducts(phApiKey, phApiSecret),
      fetchTopHackerNewsStories(),
      fetchPlaidSpending(plaidClientId, plaidSecret, plaidAccessToken, process.env.PLAID_ENVIRONMENT || 'sandbox')
    ]);

    const products = phProducts.status === 'fulfilled' ? phProducts.value : [];
    const stories = hnStories.status === 'fulfilled' ? hnStories.value : [];
    const spending = spendingData.status === 'fulfilled' ? spendingData.value : { total: 0, transactions: [] };

    if (phProducts.status === 'rejected') {
      logger.warn('Product Hunt fetch failed', { error: phProducts.reason.message });
    }

    if (hnStories.status === 'rejected') {
      logger.warn('Hacker News fetch failed', { error: hnStories.reason.message });
    }

    if (spendingData.status === 'rejected') {
      logger.warn('Plaid fetch failed', { error: spendingData.reason.message });
    }

    if (products.length === 0 && stories.length === 0 && spending.transactions.length === 0) {
      throw new Error('All data sources failed');
    }

    // Fetch food orders from Gmail
    const { fetchFoodOrdersFromEmail } = require('./fetchers/foodOrders');
    const foodOrders = await fetchFoodOrdersFromEmail({
      clientId: process.env.GMAIL_CLIENT_ID,
      clientSecret,
      refreshToken
    });

    const htmlBody = buildEmailTemplate(products, stories, spending, foodOrders);

    const emailResult = await sendEmail(
      process.env.RECIPIENT_EMAIL,
      `Your Daily Digest - ${now.toLocaleString(DateTime.DATE_FULL)}`,
      htmlBody,
      {
        clientId: process.env.GMAIL_CLIENT_ID,
        clientSecret,
        refreshToken
      }
    );

    logger.info('Daily digest sent successfully', {
      messageId: emailResult.messageId,
      productCount: products.length,
      storyCount: stories.length,
      spendingTotal: spending.total,
      transactionCount: spending.transactions.length
    });

    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Success',
        messageId: emailResult.messageId
      })
    };
  } catch (error) {
    logger.error('Handler execution failed', { error: error.message, stack: error.stack });
    throw error;
  }
}

module.exports = { handler };
