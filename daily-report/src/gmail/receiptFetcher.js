/**
 * Gmail Receipt Fetcher
 *
 * Fetches food delivery receipts from Gmail using the Gmail API
 * Searches for UberEats, DoorDash, and Grubhub receipts from the last 24 hours
 */

const { google } = require('googleapis');
const { logger } = require('../utils/logger');

/**
 * Get Gmail client (similar to existing Gmail client in the project)
 * @param {Object} credentials - { clientId, clientSecret, refreshToken }
 * @returns {Object} Gmail API client
 */
function getGmailClient(credentials) {
  const oauth2Client = new google.auth.OAuth2(
    credentials.clientId,
    credentials.clientSecret
  );

  oauth2Client.setCredentials({
    refresh_token: credentials.refreshToken
  });

  return google.gmail({ version: 'v1', auth: oauth2Client });
}

/**
 * Extract header value from Gmail message
 * @param {Object} message - Gmail message object
 * @param {string} headerName - Header name (e.g., 'From', 'Subject')
 * @returns {string} Header value or empty string
 */
function getHeader(message, headerName) {
  const headers = message.payload?.headers || [];
  const header = headers.find(h => h.name.toLowerCase() === headerName.toLowerCase());
  return header ? header.value : '';
}

/**
 * Extract email body from Gmail message
 * Handles both plain text and HTML emails
 * @param {Object} message - Gmail message object
 * @returns {string} Email body text
 */
function getBody(message) {
  try {
    const payload = message.payload;

    // Try to get plain text first
    if (payload.body?.data) {
      return Buffer.from(payload.body.data, 'base64').toString('utf-8');
    }

    // Check parts for text/plain or text/html
    if (payload.parts) {
      for (const part of payload.parts) {
        if (part.mimeType === 'text/plain' && part.body?.data) {
          return Buffer.from(part.body.data, 'base64').toString('utf-8');
        }
      }

      // Fallback to HTML
      for (const part of payload.parts) {
        if (part.mimeType === 'text/html' && part.body?.data) {
          const html = Buffer.from(part.body.data, 'base64').toString('utf-8');
          // Strip HTML tags (basic)
          return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
        }
      }
    }

    return '';
  } catch (error) {
    logger.error('Failed to extract email body', { error: error.message });
    return '';
  }
}

/**
 * Fetch delivery receipts from Gmail
 * @param {Object} credentials - { clientId, clientSecret, refreshToken }
 * @param {number} maxResults - Maximum number of emails to fetch (default: 50)
 * @returns {Array} Array of email objects with { from, subject, body }
 */
async function fetchDeliveryReceipts(credentials, maxResults = 50) {
  try {
    const gmail = getGmailClient(credentials);

    // Search for delivery receipts from last 24 hours
    // Searches from: uber.com, doordash.com, or grubhub.com
    // With subject containing: receipt, order, or confirmation
    const query = [
      'from:(uber.com OR doordash.com OR grubhub.com)',
      'subject:(receipt OR order OR confirmation)',
      'newer_than:1d'
    ].join(' ');

    logger.info('Searching Gmail for delivery receipts', { query, maxResults });

    // Search for messages
    const searchResponse = await gmail.users.messages.list({
      userId: 'me',
      q: query,
      maxResults
    });

    const messages = searchResponse.data.messages || [];

    if (messages.length === 0) {
      logger.info('No delivery receipts found in last 24 hours');
      return [];
    }

    logger.info(`Found ${messages.length} potential delivery receipts`);

    // Fetch full message details for each
    const emails = [];

    for (const message of messages) {
      try {
        const fullMessage = await gmail.users.messages.get({
          userId: 'me',
          id: message.id,
          format: 'full'
        });

        const from = getHeader(fullMessage.data, 'From');
        const subject = getHeader(fullMessage.data, 'Subject');
        const body = getBody(fullMessage.data);

        emails.push({ from, subject, body });

        logger.info('Fetched email', {
          from: from.substring(0, 30),
          subject: subject.substring(0, 50)
        });
      } catch (error) {
        logger.error('Failed to fetch message details', {
          messageId: message.id,
          error: error.message
        });
      }
    }

    logger.info(`Successfully fetched ${emails.length} delivery receipts`);

    return emails;
  } catch (error) {
    logger.error('Failed to fetch delivery receipts from Gmail', {
      error: error.message,
      stack: error.stack
    });
    return [];
  }
}

module.exports = {
  fetchDeliveryReceipts,
  getGmailClient,
  getHeader,
  getBody
};
