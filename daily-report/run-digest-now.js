/**
 * Run daily digest now (bypass time check)
 * Uses environment variables instead of AWS Secrets Manager
 */

require('dotenv').config();
const { fetchTopProductHuntProducts } = require('./src/fetchers/productHunt');
const { fetchTopHackerNewsStories } = require('./src/fetchers/hackerNews');
const { fetchPlaidSpending } = require('./src/fetchers/plaid');
const { fetchFoodOrdersFromEmail } = require('./src/fetchers/foodOrders');
const { buildEmailTemplate } = require('./src/email/template');
const { sendEmail } = require('./src/gmail/client');
const { logger } = require('./src/utils/logger');

async function runDigestNow() {
  try {
    console.log('🚀 Starting daily digest generation...\n');

    // Fetch data from all sources
    console.log('📊 Fetching data from all sources...');
    const [phProducts, hnStories, spendingData] = await Promise.allSettled([
      fetchTopProductHuntProducts(
        process.env.PRODUCT_HUNT_API_KEY,
        process.env.PRODUCT_HUNT_API_SECRET
      ).catch(err => {
        console.warn('⚠️  Product Hunt fetch failed:', err.message);
        return [];
      }),
      fetchTopHackerNewsStories().catch(err => {
        console.warn('⚠️  Hacker News fetch failed:', err.message);
        return [];
      }),
      fetchPlaidSpending(
        process.env.PLAID_CLIENT_ID,
        process.env.PLAID_SECRET,
        process.env.PLAID_ACCESS_TOKEN,
        process.env.PLAID_ENVIRONMENT || 'sandbox'
      ).catch(err => {
        console.warn('⚠️  Plaid fetch failed:', err.message);
        return { total: 0, transactions: [] };
      })
    ]);

    const products = phProducts.status === 'fulfilled' ? phProducts.value : [];
    const stories = hnStories.status === 'fulfilled' ? hnStories.value : [];
    const spending = spendingData.status === 'fulfilled' ? spendingData.value : { total: 0, transactions: [] };

    console.log(`✅ Product Hunt: ${products.length} products`);
    console.log(`✅ Hacker News: ${stories.length} stories`);
    console.log(`✅ Plaid: ${spending.transactions?.length || 0} transactions, $${spending.total?.toFixed(2) || '0.00'} total\n`);

    // Fetch food orders with Gmail integration
    console.log('🍔 Fetching food orders...');
    const foodOrders = await fetchFoodOrdersFromEmail({
      clientId: process.env.GMAIL_CLIENT_ID,
      clientSecret: process.env.GMAIL_CLIENT_SECRET,
      refreshToken: process.env.GMAIL_REFRESH_TOKEN
    }).catch(err => {
      console.warn('⚠️  Food orders fetch failed:', err.message);
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
    });

    console.log(`✅ Food orders: ${foodOrders.orders.length} orders`);
    console.log(`   📊 ${foodOrders.summary.totalCalories} cal, $${foodOrders.summary.totalSpent.toFixed(2)}`);
    if (foodOrders.summary.pdfOnlyCount > 0) {
      console.log(`   ⚠️  ${foodOrders.summary.pdfOnlyCount} PDF-only receipts need manual PDFs`);
    }
    console.log('');

    // Build email
    console.log('✉️  Building email...');
    const htmlBody = buildEmailTemplate(products, stories, spending, foodOrders);

    // Send email
    console.log('📧 Sending email...');
    const { DateTime } = require('luxon');
    const now = DateTime.now();

    const emailResult = await sendEmail(
      process.env.RECIPIENT_EMAIL,
      `Your Daily Digest - ${now.toLocaleString(DateTime.DATE_FULL)}`,
      htmlBody,
      {
        clientId: process.env.GMAIL_CLIENT_ID,
        clientSecret: process.env.GMAIL_CLIENT_SECRET,
        refreshToken: process.env.GMAIL_REFRESH_TOKEN
      }
    );

    console.log('\n✅ Daily digest sent successfully!');
    console.log(`📬 Message ID: ${emailResult.messageId}`);
  } catch (error) {
    console.error('\n❌ Error generating digest:', error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

// Run it
runDigestNow();
