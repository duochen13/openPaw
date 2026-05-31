const axios = require('axios');
const { logger } = require('../utils/logger');

const PH_API_BASE = 'https://api.producthunt.com/v2/api/graphql';
const TIMEOUT_MS = 10000;

const QUERY = `
  query {
    posts(order: VOTES) {
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

async function fetchTopProductHuntProducts(apiKey) {
  try {
    const response = await axios.post(
      PH_API_BASE,
      { query: QUERY },
      {
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        timeout: TIMEOUT_MS
      }
    );

    const posts = response.data?.data?.posts?.edges?.map(edge => edge.node) || response.data?.posts || [];

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

    return topProducts;
  } catch (error) {
    logger.error('Failed to fetch Product Hunt products', { error: error.message });
    throw error;
  }
}

module.exports = { fetchTopProductHuntProducts };
