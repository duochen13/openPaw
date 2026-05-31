const axios = require('axios');
const { logger } = require('../utils/logger');

const PH_API_BASE = 'https://api.producthunt.com/v2/api/graphql';
const PH_OAUTH_URL = 'https://api.producthunt.com/v2/oauth/token';
const TIMEOUT_MS = 10000;

let cachedAccessToken = null;
let tokenExpiry = null;

const QUERY_WITH_DATE = `
  query($postedAfter: DateTime!, $postedBefore: DateTime!) {
    posts(order: VOTES, postedAfter: $postedAfter, postedBefore: $postedBefore) {
      edges {
        node {
          id
          name
          tagline
          votesCount
          commentsCount
          url
          thumbnail {
            videoUrl
          }
        }
      }
    }
  }
`;

async function getAccessToken(apiKey, apiSecret) {
  // Return cached token if still valid
  if (cachedAccessToken && tokenExpiry && Date.now() < tokenExpiry) {
    return cachedAccessToken;
  }

  try {
    const response = await axios.post(
      PH_OAUTH_URL,
      {
        client_id: apiKey,
        client_secret: apiSecret,
        grant_type: 'client_credentials'
      },
      {
        headers: {
          'Content-Type': 'application/json'
        },
        timeout: TIMEOUT_MS
      }
    );

    cachedAccessToken = response.data.access_token;
    // Set expiry to 1 hour from now (tokens typically last longer, but being conservative)
    tokenExpiry = Date.now() + (60 * 60 * 1000);

    logger.info('Successfully obtained Product Hunt access token');
    return cachedAccessToken;
  } catch (error) {
    logger.error('Failed to get Product Hunt access token', { error: error.message });
    throw error;
  }
}

function getDateRange(daysAgo) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);

  const startOfDay = new Date(date);
  startOfDay.setHours(0, 0, 0, 0);

  const endOfDay = new Date(date);
  endOfDay.setHours(23, 59, 59, 999);

  return {
    postedAfter: startOfDay.toISOString(),
    postedBefore: endOfDay.toISOString()
  };
}

async function fetchProductsForDate(apiKey, apiSecret, daysAgo, label) {
  try {
    const accessToken = await getAccessToken(apiKey, apiSecret);
    const dateRange = getDateRange(daysAgo);

    const response = await axios.post(
      PH_API_BASE,
      {
        query: QUERY_WITH_DATE,
        variables: dateRange
      },
      {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        },
        timeout: TIMEOUT_MS
      }
    );

    const posts = response.data?.data?.posts?.edges?.map(edge => edge.node) || [];

    if (posts.length === 0) {
      logger.info(`No products found for ${label}`);
      return [];
    }

    const products = posts.map(post => {
      const upvotes = post.votesCount || 0;
      const comments = post.commentsCount || 0;
      const trendingScore = (upvotes * 0.7) + (comments * 0.3);

      return {
        id: post.id,
        name: post.name,
        tagline: post.tagline,
        upvotes,
        comments,
        trendingScore,
        url: post.url,
        videoUrl: post.thumbnail?.videoUrl || null
      };
    });

    const topProducts = products
      .sort((a, b) => b.trendingScore - a.trendingScore)
      .slice(0, 5);

    logger.info(`Fetched ${topProducts.length} products for ${label}`);
    return topProducts;
  } catch (error) {
    logger.error(`Failed to fetch products for ${label}`, { error: error.message });
    throw error;
  }
}

async function fetchTopProductHuntProducts(apiKey, apiSecret) {
  // Try today first
  try {
    const todayProducts = await fetchProductsForDate(apiKey, apiSecret, 0, 'today');
    if (todayProducts.length > 0) {
      return todayProducts;
    }
  } catch (error) {
    logger.warn('Failed to fetch today\'s products, trying yesterday', { error: error.message });
  }

  // Fallback to yesterday
  try {
    const yesterdayProducts = await fetchProductsForDate(apiKey, apiSecret, 1, 'yesterday');
    if (yesterdayProducts.length > 0) {
      return yesterdayProducts;
    }
  } catch (error) {
    logger.warn('Failed to fetch yesterday\'s products, trying last week', { error: error.message });
  }

  // Fallback to last week (7 days ago)
  try {
    const lastWeekProducts = await fetchProductsForDate(apiKey, apiSecret, 7, 'last week');
    if (lastWeekProducts.length > 0) {
      return lastWeekProducts;
    }
  } catch (error) {
    logger.error('Failed to fetch products from all time periods', { error: error.message });
    throw error;
  }

  // If we get here, no products were found in any time period
  logger.error('No products found in today, yesterday, or last week');
  throw new Error('No Product Hunt products available');
}

// For testing: clear cached token
function clearTokenCache() {
  cachedAccessToken = null;
  tokenExpiry = null;
}

module.exports = { fetchTopProductHuntProducts, clearTokenCache };
