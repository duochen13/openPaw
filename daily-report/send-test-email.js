/**
 * Send test email with sample Uber Eats data
 */

// Load .env file if it exists
try {
  require('dotenv').config();
} catch (err) {
  console.log('⚠️  dotenv not available, using environment variables');
}

const { buildEmailTemplate } = require('./src/email/template');
const { sendEmail } = require('./src/gmail/client');
const { matchNutrition } = require('./src/fetchers/nutrition');

async function sendTestEmail() {
  try {
    console.log('🧪 Generating test email with Uber Eats data...\n');

    // Sample Uber Eats order from the PDF we parsed
    const uberEatsOrder = {
      platform: 'UberEats',
      restaurant: 'Tian Shi Fu 田师傅 No.3',
      timestamp: '2026-06-05T21:42:00.000Z',
      total: 30.40,
      items: [
        { name: 'Edamame风味毛豆', quantity: 1, price: 7.75 },
        { name: 'Pork Knuckle (Per Piece)烤猪手', quantity: 1, price: 7.55 },
        { name: 'Sausage (Per Skewer)烤香肠', quantity: 1, price: 2.55 },
        { name: 'Lamb Skewer(5 Piece)羊肉串（5串）', quantity: 1, price: 12.55 }
      ]
    };

    console.log('🍜 Enriching items with nutrition data...');
    const enrichedItems = await matchNutrition(
      uberEatsOrder.items,
      uberEatsOrder.restaurant
    );
    uberEatsOrder.items = enrichedItems;

    // Calculate summary
    const totalCalories = enrichedItems.reduce((sum, item) =>
      sum + (item.nutrition?.totalCalories || 0), 0
    );
    const totalProtein = enrichedItems.reduce((sum, item) =>
      sum + (item.nutrition?.totalProtein || 0), 0
    );
    const totalCarbs = enrichedItems.reduce((sum, item) =>
      sum + (item.nutrition?.totalCarbs || 0), 0
    );
    const totalFat = enrichedItems.reduce((sum, item) =>
      sum + (item.nutrition?.totalFat || 0), 0
    );
    const estimatedItems = enrichedItems.filter(item =>
      item.nutrition?.isEstimate
    ).length;

    console.log(`✅ Nutrition data: ${Math.round(totalCalories)} cal, ${Math.round(totalProtein)}g protein\n`);

    const foodOrdersData = {
      orders: [uberEatsOrder],
      summary: {
        totalOrders: 1,
        totalCalories,
        totalProtein,
        totalCarbs,
        totalFat,
        totalSpent: 30.40,
        ordersByPlatform: {
          'UberEats': 1
        },
        estimatedItems,
        pdfOnlyCount: 0
      }
    };

    // Sample Product Hunt data
    const phProducts = [
      {
        name: 'Dreambeans by Google Labs',
        tagline: 'Daily AI stories personalised from your Google apps',
        votesCount: 210,
        commentsCount: 6,
        url: 'https://www.producthunt.com/posts/dreambeans'
      },
      {
        name: 'Wave',
        tagline: 'Turn your voice into text — local or cloud, your choice',
        votesCount: 183,
        commentsCount: 8,
        url: 'https://www.producthunt.com/posts/wave'
      },
      {
        name: 'CabinLink',
        tagline: 'Flight map from cabin Wi-Fi',
        votesCount: 166,
        commentsCount: 16,
        url: 'https://www.producthunt.com/posts/cabinlink'
      }
    ];

    // Sample Hacker News data
    const hnStories = [
      {
        title: 'Show HN: I built a tool to visualize your codebase',
        url: 'https://news.ycombinator.com/item?id=12345',
        score: 342,
        comments: 87
      },
      {
        title: 'The architecture of Stripe payment system',
        url: 'https://news.ycombinator.com/item?id=12346',
        score: 298,
        comments: 54
      },
      {
        title: 'Why we switched from AWS to bare metal',
        url: 'https://news.ycombinator.com/item?id=12347',
        score: 256,
        comments: 123
      }
    ];

    // Sample spending data (empty for test)
    const spendingData = {
      total: 0,
      transactions: []
    };

    console.log('✉️  Building email template...');
    const htmlBody = buildEmailTemplate(
      phProducts,
      hnStories,
      spendingData,
      foodOrdersData
    );

    console.log('📧 Sending test email...');

    // Check for required environment variables
    if (!process.env.RECIPIENT_EMAIL) {
      throw new Error('RECIPIENT_EMAIL not set in environment');
    }
    if (!process.env.GMAIL_CLIENT_ID || !process.env.GMAIL_CLIENT_SECRET || !process.env.GMAIL_REFRESH_TOKEN) {
      throw new Error('Gmail OAuth credentials not set. Need GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN');
    }

    const emailResult = await sendEmail(
      process.env.RECIPIENT_EMAIL,
      'Test: Your Daily Digest with Uber Eats 🍔',
      htmlBody,
      {
        clientId: process.env.GMAIL_CLIENT_ID,
        clientSecret: process.env.GMAIL_CLIENT_SECRET,
        refreshToken: process.env.GMAIL_REFRESH_TOKEN
      }
    );

    console.log('\n✅ Test email sent successfully!');
    console.log(`📬 Message ID: ${emailResult.messageId}`);
    console.log(`📧 Check your inbox at: ${process.env.RECIPIENT_EMAIL}`);
  } catch (error) {
    console.error('\n❌ Error sending test email:', error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

sendTestEmail();
