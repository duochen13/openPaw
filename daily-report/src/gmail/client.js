const { google } = require('googleapis');
const { logger } = require('../utils/logger');

async function sendEmail(to, subject, htmlBody, credentials) {
  try {
    const oauth2Client = new google.auth.OAuth2(
      credentials.clientId,
      credentials.clientSecret,
      'https://developers.google.com/oauthplayground'
    );

    oauth2Client.setCredentials({
      refresh_token: credentials.refreshToken
    });

    const gmail = google.gmail({ version: 'v1', auth: oauth2Client });

    const message = [
      `To: ${to}`,
      'Content-Type: text/html; charset=utf-8',
      'MIME-Version: 1.0',
      `Subject: ${subject}`,
      '',
      htmlBody
    ].join('\n');

    const encodedMessage = Buffer.from(message)
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    const response = await gmail.users.messages.send({
      userId: 'me',
      requestBody: {
        raw: encodedMessage
      }
    });

    logger.info('Email sent successfully', { messageId: response.data.id });

    return { messageId: response.data.id };
  } catch (error) {
    logger.error('Failed to send email', { error: error.message });
    throw error;
  }
}

module.exports = { sendEmail };
