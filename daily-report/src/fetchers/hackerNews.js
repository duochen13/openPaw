const axios = require('axios');
const { logger } = require('../utils/logger');

const HN_API_BASE = 'https://hacker-news.firebaseio.com/v0';
const TIMEOUT_MS = 10000;

async function fetchTopHackerNewsStories() {
  try {
    const topStoriesResponse = await axios.get(`${HN_API_BASE}/topstories.json`, {
      timeout: TIMEOUT_MS
    });

    const topStoryIds = topStoriesResponse.data.slice(0, 10);

    const storyPromises = topStoryIds.map(async (id) => {
      try {
        const response = await axios.get(`${HN_API_BASE}/item/${id}.json`, {
          timeout: TIMEOUT_MS
        });
        return response.data;
      } catch (error) {
        logger.warn(`Failed to fetch HN story ${id}`, { error: error.message });
        return null;
      }
    });

    const stories = await Promise.all(storyPromises);

    const validStories = stories
      .filter(story => story !== null && story.title && story.score !== undefined)
      .map(story => ({
        id: story.id,
        title: story.title,
        url: story.url || `https://news.ycombinator.com/item?id=${story.id}`,
        points: story.score,
        comments: story.descendants || 0
      }))
      .sort((a, b) => b.points - a.points)
      .slice(0, 3);

    return validStories;
  } catch (error) {
    logger.error('Failed to fetch Hacker News stories', { error: error.message });
    throw error;
  }
}

module.exports = { fetchTopHackerNewsStories };
