/**
 * Preview test email with sample Uber Eats data
 * Generates HTML file you can open in browser
 */

const fs = require('fs');
const path = require('path');
const { buildEmailTemplate } = require('./src/email/template');

async function previewTestEmail() {
  try {
    console.log('🧪 Generating test email preview with Uber Eats data...\n');

    // Sample Uber Eats order from your actual PDF
    const uberEatsOrder = {
      platform: 'UberEats',
      restaurant: 'Tian Shi Fu 田师傅 No.3',
      timestamp: '2026-06-05T21:42:00.000Z',
      total: 30.40,
      items: [
        {
          name: 'Edamame风味毛豆',
          quantity: 1,
          price: 7.75,
          nutrition: {
            totalCalories: 189,
            totalProtein: 16,
            totalCarbs: 16,
            totalFat: 8,
            isEstimate: false
          }
        },
        {
          name: 'Pork Knuckle (Per Piece)烤猪手',
          quantity: 1,
          price: 7.55,
          nutrition: {
            totalCalories: 372,
            totalProtein: 28,
            totalCarbs: 8,
            totalFat: 25,
            isEstimate: false
          }
        },
        {
          name: 'Sausage (Per Skewer)烤香肠',
          quantity: 1,
          price: 2.55,
          nutrition: {
            totalCalories: 220,
            totalProtein: 8,
            totalCarbs: 2,
            totalFat: 19,
            isEstimate: false
          }
        },
        {
          name: 'Lamb Skewer(5 Piece)羊肉串（5串）',
          quantity: 1,
          price: 12.55,
          nutrition: {
            totalCalories: 323,
            totalProtein: 30,
            totalCarbs: 0,
            totalFat: 22,
            isEstimate: true
          }
        }
      ]
    };

    // Calculate summary
    const totalCalories = uberEatsOrder.items.reduce((sum, item) =>
      sum + item.nutrition.totalCalories, 0
    );
    const totalProtein = uberEatsOrder.items.reduce((sum, item) =>
      sum + item.nutrition.totalProtein, 0
    );
    const totalCarbs = uberEatsOrder.items.reduce((sum, item) =>
      sum + item.nutrition.totalCarbs, 0
    );
    const totalFat = uberEatsOrder.items.reduce((sum, item) =>
      sum + item.nutrition.totalFat, 0
    );
    const estimatedItems = uberEatsOrder.items.filter(item =>
      item.nutrition.isEstimate
    ).length;

    console.log(`✅ Order data:`);
    console.log(`   Restaurant: ${uberEatsOrder.restaurant}`);
    console.log(`   Items: ${uberEatsOrder.items.length}`);
    console.log(`   Total: $${uberEatsOrder.total.toFixed(2)}`);
    console.log(`   Calories: ${totalCalories} cal`);
    console.log(`   Protein: ${totalProtein}g`);
    console.log(`   Carbs: ${totalCarbs}g`);
    console.log(`   Fat: ${totalFat}g`);
    console.log('');

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

    // Sample Product Hunt data (top 3)
    const phProducts = [
      {
        name: 'Dreambeans by Google Labs',
        tagline: 'Daily AI stories personalised from your Google apps',
        upvotes: 210,
        comments: 6,
        url: 'https://www.producthunt.com/posts/dreambeans'
      },
      {
        name: 'Wave',
        tagline: 'Turn your voice into text — local or cloud, your choice',
        upvotes: 183,
        comments: 8,
        url: 'https://www.producthunt.com/posts/wave'
      },
      {
        name: 'CabinLink',
        tagline: 'Flight map from cabin Wi-Fi',
        upvotes: 166,
        comments: 16,
        url: 'https://www.producthunt.com/posts/cabinlink'
      }
    ];

    // Sample Hacker News data (top 3)
    const hnStories = [
      {
        title: 'Show HN: I built a tool to visualize your codebase',
        url: 'https://news.ycombinator.com/item?id=12345',
        points: 342,
        comments: 87
      },
      {
        title: 'The architecture of Stripe payment system',
        url: 'https://news.ycombinator.com/item?id=12346',
        points: 298,
        comments: 54
      },
      {
        title: 'Why we switched from AWS to bare metal',
        url: 'https://news.ycombinator.com/item?id=12347',
        points: 256,
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

    const outputPath = path.join(__dirname, 'test-email-preview.html');
    fs.writeFileSync(outputPath, htmlBody);

    console.log('\n✅ Email preview generated!');
    console.log(`📄 Open this file in your browser:`);
    console.log(`   ${outputPath}`);
    console.log('');
    console.log('Or run:');
    console.log(`   open "${outputPath}"`);

  } catch (error) {
    console.error('\n❌ Error generating preview:', error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

previewTestEmail();
