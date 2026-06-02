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

function buildEmailTemplate(phProducts, hnStories, spendingData) {
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
