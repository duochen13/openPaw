const { getStyles } = require('./styles');

// Tech/startup-themed jokes personalized for a Columbia CS student
const JOKES = [
  "Why do Columbia CS students love Product Hunt? Because launching products is easier than finding laundry machines in the dorms! 🎓",
  "What's the difference between a startup founder and a pizza? A pizza can feed a family of four. But hey, at least you're on Hacker News! 🍕",
  "Why did the developer go broke? Because they used up all their cache! (But seriously, save some for AWS bills) 💸",
  "A SQL query walks into a bar, walks up to two tables and asks... 'Can I JOIN you?' 🍺",
  "How many Product Hunt upvotes does it take to validate a business idea? None. You still need customers. (But 500+ looks nice!) 👍",
  "Why do Java developers wear glasses? Because they can't C#. (Meanwhile, Node.js developers are still looking for their semicolons) 👓",
  "I told my computer I needed a break, and now it won't stop sending me Kit-Kat ads. AWS knows too much! 🍫",
  "Why was the JavaScript developer sad? Because they didn't Node how to Express themselves. (Get it? Like your Lambda function?) 😅",
  "What's a programmer's favorite hangout place? Foo Bar. (Probably discussing their latest side project) 🍻",
  "A product manager walks into a bar. The bartender says, 'I'm sorry, we don't serve your type here.' The PM replies, 'But according to my user research...' 📊",
  "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
  "How do you comfort a JavaScript bug? You console it. (console.log('everything will be okay')) 🤗",
  "What's the object-oriented way to become wealthy? Inheritance. (Or a successful exit on Product Hunt) 💰",
  "Why do Python programmers have low self-esteem? Because they're constantly comparing themselves to others with '==' 🐍",
  "A QA engineer walks into a bar. Orders a beer. Orders 0 beers. Orders 99999999999 beers. Orders a lizard. Orders -1 beers. First real customer walks in and asks where the bathroom is. The bar bursts into flames. 🔥"
];

function getDailyJoke() {
  // Use date as seed for consistent joke per day
  const today = new Date();
  const dayOfYear = Math.floor((today - new Date(today.getFullYear(), 0, 0)) / 1000 / 60 / 60 / 24);
  const jokeIndex = dayOfYear % JOKES.length;
  return JOKES[jokeIndex];
}

function buildSpendingSummarySection(spendingData) {
  const categoryEmojis = {
    'Shopping': '🛍️',
    'Dining': '🍔',
    'Coffee': '☕',
    'Transport': '🚗',
    'Entertainment': '🎬',
    'Other': '💳'
  };

  const transactionLines = spendingData.transactions.map(t => {
    const emoji = categoryEmojis[t.category] || categoryEmojis['Other'];
    return `${emoji} ${t.merchant} - $${t.amount.toFixed(2)}`;
  }).join('<br>');

  return `
    <div class="section" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
      <h2 style="color: white; margin-top: 0;">💰 Yesterday's Spending</h2>
      <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">$${spendingData.total.toFixed(2)}</p>

      <div style="margin-top: 15px;">
        <p style="font-size: 14px; opacity: 0.9; margin-bottom: 8px;">Top Transactions:</p>
        <div style="font-size: 15px; line-height: 1.8;">
          ${transactionLines}
        </div>
      </div>
    </div>
  `;
}

function buildFoodOrdersSection(foodOrdersData) {
  const { orders, summary } = foodOrdersData;

  if (!orders || orders.length === 0) {
    return `
      <div class="section" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
        <h2 style="color: white; margin-top: 0;">🍔 Food Orders & Nutrition</h2>
        <p style="color: white; opacity: 0.9; margin-bottom: 15px;">No food delivery orders detected yesterday</p>

        <div style="margin-top: 15px; padding: 12px; background: rgba(255,255,255,0.15); border-radius: 6px; border-left: 4px solid rgba(255,255,255,0.4);">
          <p style="font-size: 14px; margin: 0; line-height: 1.6;">
            📊 <strong>Tracks orders from:</strong> UberEats, DoorDash, Grubhub
            <br><br>
            🥗 <strong>Automatically fetches:</strong> Items, calories, protein, carbs, fat
            <br><br>
            💰 <strong>Daily budget:</strong> $${parseFloat(process.env.DAILY_FOOD_BUDGET || 32).toFixed(2)}
            <br><br>
            📄 <strong>Uber Eats PDFs:</strong> Download receipts to <code style="background: rgba(0,0,0,0.2); padding: 2px 6px; border-radius: 3px;">~/Downloads/uber-receipts/</code> for itemized tracking
          </p>
        </div>
      </div>
    `;
  }

  const platformEmojis = {
    'UberEats': '🚗',
    'DoorDash': '🏃',
    'Grubhub': '🍽️'
  };

  const ordersHTML = orders.map(order => {
    const platformEmoji = platformEmojis[order.platform] || '🍔';
    const orderTime = new Date(order.timestamp).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });

    const itemsHTML = order.items.map(item => {
      const nutrition = item.nutrition;
      const estimateBadge = nutrition.isEstimate
        ? '<span style="font-size: 11px; background: rgba(255,255,255,0.3); padding: 2px 6px; border-radius: 3px; margin-left: 5px;">est.</span>'
        : '';

      return `
        <div style="margin: 8px 0; padding: 8px; background: rgba(255,255,255,0.1); border-radius: 4px;">
          <div style="font-weight: bold;">${item.name} ${item.quantity > 1 ? `x${item.quantity}` : ''}</div>
          <div style="font-size: 13px; margin-top: 4px; opacity: 0.9;">
            ${nutrition.totalCalories} cal | ${nutrition.totalProtein}g protein | ${nutrition.totalCarbs}g carbs | ${nutrition.totalFat}g fat
            ${estimateBadge}
          </div>
        </div>
      `;
    }).join('');

    return `
      <div style="margin: 15px 0; padding: 12px; background: rgba(255,255,255,0.15); border-radius: 6px;">
        <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px;">
          ${platformEmoji} ${orderTime} - ${order.restaurant}
        </div>
        ${itemsHTML}
        <div style="margin-top: 8px; font-size: 14px; opacity: 0.9;">
          Total: $${(order.total || 0).toFixed(2)}
        </div>
      </div>
    `;
  }).join('');

  const dailyBudget = parseFloat(process.env.DAILY_FOOD_BUDGET || 32);
  const budgetRemaining = dailyBudget - summary.totalSpent;
  const budgetStatus = budgetRemaining >= 0
    ? `✅ Within budget ($${budgetRemaining.toFixed(2)} remaining)`
    : `⚠️ Over budget by $${Math.abs(budgetRemaining).toFixed(2)}`;

  const estimateWarning = summary.estimatedItems > 0
    ? `<p style="font-size: 12px; opacity: 0.8; margin-top: 10px;">⚠️ ${summary.estimatedItems} item(s) used estimated nutrition data</p>`
    : '';

  const pdfOnlyWarning = summary.pdfOnlyCount > 0
    ? `<div style="margin-top: 15px; padding: 12px; background: rgba(255,255,255,0.2); border-radius: 6px; border-left: 4px solid rgba(255,255,255,0.5);">
         <p style="font-size: 13px; margin: 0;">
           ⚠️ <strong>${summary.pdfOnlyCount} Uber Eats receipt(s)</strong> only show total amount.
           <br><br>
           <strong>To get itemized data:</strong> Download the PDF receipt from your email and save it to <code style="background: rgba(0,0,0,0.2); padding: 2px 4px; border-radius: 3px;">~/Downloads/uber-receipts/</code>
           <br><br>
           The system will automatically parse it and match items with nutrition data!
         </p>
       </div>`
    : '';

  return `
    <div class="section" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
      <h2 style="color: white; margin-top: 0;">🍔 Food Orders & Nutrition</h2>

      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 20px;">
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Orders</p>
          <p style="font-size: 24px; font-weight: bold; margin: 5px 0 0 0;">${summary.totalOrders}</p>
        </div>
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Total Calories</p>
          <p style="font-size: 24px; font-weight: bold; margin: 5px 0 0 0;">${Math.round(summary.totalCalories)}</p>
        </div>
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Protein</p>
          <p style="font-size: 20px; font-weight: bold; margin: 5px 0 0 0;">${Math.round(summary.totalProtein)}g</p>
        </div>
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Total Spent</p>
          <p style="font-size: 20px; font-weight: bold; margin: 5px 0 0 0;">$${summary.totalSpent.toFixed(2)}</p>
        </div>
      </div>

      <div style="margin-top: 15px; padding: 12px; background: rgba(255,255,255,0.2); border-radius: 6px;">
        <p style="font-size: 14px; opacity: 0.9; margin: 0 0 5px 0;">Budget Status</p>
        <p style="font-size: 16px; font-weight: bold; margin: 0;">${budgetStatus}</p>
      </div>

      <div style="margin-top: 20px;">
        <p style="font-size: 14px; opacity: 0.9; margin-bottom: 10px;">Yesterday's Orders:</p>
        ${ordersHTML}
      </div>

      ${pdfOnlyWarning}
      ${estimateWarning}
    </div>
  `;
}

function buildUberEatsHighlightsSection(foodOrdersData) {
  const { orders } = foodOrdersData;

  // Filter only UberEats orders
  const uberEatsOrders = orders.filter(order => order.platform === 'UberEats');

  if (uberEatsOrders.length === 0) {
    return ''; // Don't show section if no UberEats orders
  }

  // Calculate UberEats-specific stats
  const totalSpent = uberEatsOrders.reduce((sum, order) => sum + order.total, 0);
  const totalCalories = uberEatsOrders.reduce((sum, order) =>
    sum + order.items.reduce((itemSum, item) =>
      itemSum + (item.nutrition?.totalCalories || 0), 0
    ), 0
  );
  const totalItems = uberEatsOrders.reduce((sum, order) => sum + order.items.length, 0);
  const avgOrderValue = totalSpent / uberEatsOrders.length;

  // Find top restaurant (most expensive order)
  const topOrder = uberEatsOrders.reduce((max, order) =>
    order.total > max.total ? order : max
  , uberEatsOrders[0]);

  return `
    <div class="section" style="background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
      <h2 style="color: white; margin-top: 0;">🚗 Uber Eats Highlights</h2>

      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 20px;">
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Orders</p>
          <p style="font-size: 24px; font-weight: bold; margin: 5px 0 0 0;">${uberEatsOrders.length}</p>
        </div>
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Total Spent</p>
          <p style="font-size: 24px; font-weight: bold; margin: 5px 0 0 0;">$${totalSpent.toFixed(2)}</p>
        </div>
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Total Calories</p>
          <p style="font-size: 24px; font-weight: bold; margin: 5px 0 0 0;">${Math.round(totalCalories)}</p>
        </div>
        <div>
          <p style="font-size: 14px; opacity: 0.9; margin: 0;">Avg per Order</p>
          <p style="font-size: 24px; font-weight: bold; margin: 5px 0 0 0;">$${avgOrderValue.toFixed(2)}</p>
        </div>
      </div>

      <div style="padding: 12px; background: rgba(255,255,255,0.2); border-radius: 6px; border-left: 4px solid rgba(255,255,255,0.5);">
        <p style="font-size: 14px; opacity: 0.9; margin: 0 0 5px 0;">🏆 Biggest Order</p>
        <p style="font-size: 16px; font-weight: bold; margin: 0;">${topOrder.restaurant} - $${topOrder.total.toFixed(2)}</p>
        <p style="font-size: 13px; opacity: 0.9; margin: 5px 0 0 0;">${topOrder.items.length} items • ${topOrder.items.reduce((sum, item) => sum + (item.nutrition?.totalCalories || 0), 0)} cal</p>
      </div>

      <div style="margin-top: 15px;">
        <p style="font-size: 14px; opacity: 0.9; margin-bottom: 10px;">All Restaurants:</p>
        ${uberEatsOrders.map(order => {
          const orderTime = new Date(order.timestamp).toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
          });
          return `
            <div style="padding: 10px; background: rgba(255,255,255,0.15); border-radius: 6px; margin-bottom: 8px;">
              <div style="font-weight: bold; font-size: 15px;">${order.restaurant}</div>
              <div style="font-size: 13px; opacity: 0.9; margin-top: 4px;">
                🕐 ${orderTime} • $${order.total.toFixed(2)} • ${order.items.length} items
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function buildStockSection(stockData) {
  const headerOpen = `
    <div class="section" style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
      <h2 style="color: white; margin-top: 0;">📈 Market Watchlist</h2>`;

  if (!stockData || stockData.error || !stockData.holdings || stockData.holdings.length === 0) {
    return `${headerOpen}
      <p style="color: white; font-style: italic; opacity: 0.9;">Market data unavailable today</p>
    </div>`;
  }

  const { buildPeBarChartUrl } = require('./stockChart');
  const chartUrl = buildPeBarChartUrl(stockData.holdings);
  const chartImg = chartUrl
    ? `<img src="${chartUrl}" alt="P/E ratio by symbol for the watchlist" width="100%" style="border-radius: 6px; background: white; margin-bottom: 15px;">`
    : '';

  const asOf = new Date(stockData.asOf).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric'
  });

  const rows = stockData.holdings.map(h => {
    const positive = h.ytdReturnPct >= 0;
    const arrow = positive ? '▲' : '▼';
    const color = positive ? '#bbf7d0' : '#fecaca';
    const pe = (h.peRatio === null || h.peRatio === undefined) ? '—' : h.peRatio.toFixed(1);
    return `
      <tr>
        <td style="padding: 6px 8px;"><strong>${h.symbol}</strong> <span style="opacity: 0.8; font-size: 13px;">${h.label}</span></td>
        <td style="padding: 6px 8px; text-align: right;">$${h.price.toFixed(2)}</td>
        <td style="padding: 6px 8px; text-align: right; color: ${color}; font-weight: bold;">${arrow} ${h.ytdReturnPct.toFixed(2)}%</td>
        <td style="padding: 6px 8px; text-align: right;">${pe}</td>
      </tr>`;
  }).join('');

  return `${headerOpen}
    ${chartImg}
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
      <thead>
        <tr style="text-align: left; opacity: 0.9; font-size: 12px;">
          <th style="padding: 6px 8px;">Symbol</th>
          <th style="padding: 6px 8px; text-align: right;">Price</th>
          <th style="padding: 6px 8px; text-align: right;">YTD</th>
          <th style="padding: 6px 8px; text-align: right;">P/E</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <p style="font-size: 12px; opacity: 0.8; margin: 12px 0 0 0;">as of ${asOf}</p>
  </div>`;
}

function buildEmailTemplate(phProducts, hnStories, spendingData, foodOrdersData = null, stockData = null) {
  const today = new Date().toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });

  const dailyJoke = getDailyJoke();

  const spendingSection = spendingData && spendingData.transactions.length > 0
    ? buildSpendingSummarySection(spendingData)
    : `<div class="section" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
         <h2 style="color: white; margin-top: 0;">💰 Yesterday's Spending</h2>
         <p style="color: white; font-style: italic; opacity: 0.9;">Spending data unavailable for yesterday</p>
       </div>`;

  // Always show food orders section (even if no data)
  const foodOrdersSection = foodOrdersData
    ? buildFoodOrdersSection(foodOrdersData)
    : buildFoodOrdersSection({ orders: [], summary: {
        totalOrders: 0,
        totalCalories: 0,
        totalProtein: 0,
        totalCarbs: 0,
        totalFat: 0,
        totalSpent: 0,
        estimatedItems: 0,
        pdfOnlyCount: 0,
        ordersByPlatform: {}
      }});

  // Uber Eats highlights section (only shows if there are UberEats orders)
  const uberEatsSection = foodOrdersData
    ? buildUberEatsHighlightsSection(foodOrdersData)
    : '';

  const stockSection = buildStockSection(stockData);

  const phSection = phProducts.length > 0
    ? buildProductHuntSection(phProducts)
    : '<p style="color: #999; font-style: italic;">Product Hunt data unavailable today</p>';

  const hnSection = hnStories.length > 0
    ? buildHackerNewsSection(hnStories)
    : '<p style="color: #999; font-style: italic;">Hacker News data unavailable today</p>';

  return `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Your Daily Digest - ${today}</title>
      ${getStyles()}
    </head>
    <body>
      <div class="container">
        <h1>Your Daily Digest</h1>
        <p style="color: #666; font-size: 14px;">${today}</p>

        <div class="section" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
          <h2 style="color: white; margin-top: 0;">😄 Today's Tech Joke</h2>
          <p style="font-size: 16px; line-height: 1.6; margin: 0;">${dailyJoke}</p>
        </div>

        ${spendingSection}

        ${foodOrdersSection}

        ${uberEatsSection}

        ${stockSection}

        <div class="section">
          <h2>🚀 Product Hunt</h2>
          ${phSection}
        </div>

        <div class="section">
          <h2>📰 Hacker News</h2>
          ${hnSection}
        </div>

        <div class="footer">
          Generated by OpenPaw Daily Digest
        </div>
      </div>
    </body>
    </html>
  `;
}

function buildProductHuntSection(products) {
  return products.map(product => {
    const videoEmbed = product.videoUrl
      ? `<div class="video-container">
           <video controls width="100%" style="max-height: 300px;">
             <source src="${product.videoUrl}" type="video/mp4">
             Your email client doesn't support video.
           </video>
         </div>`
      : '';

    return `
      <div class="item">
        <div class="item-title">
          <a href="${product.url}">${product.name}</a>
        </div>
        <div class="item-tagline">${product.tagline}</div>
        ${videoEmbed}
        <div class="item-meta">
          👍 ${product.upvotes} upvotes • 💬 ${product.comments} comments
        </div>
      </div>
    `;
  }).join('');
}

function buildHackerNewsSection(stories) {
  return stories.map(story => {
    return `
      <div class="item">
        <div class="item-title">
          <a href="${story.url}">${story.title}</a>
        </div>
        <div class="item-meta">
          ⬆️ ${story.points} points • 💬 ${story.comments} comments
        </div>
      </div>
    `;
  }).join('');
}

module.exports = { buildEmailTemplate };
