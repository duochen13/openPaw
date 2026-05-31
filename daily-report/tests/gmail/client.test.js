const { google } = require('googleapis');
const { sendEmail } = require('../../src/gmail/client');

jest.mock('googleapis');

describe('Gmail Client', () => {
  let mockGmail;
  let mockOAuth2Client;

  beforeEach(() => {
    jest.clearAllMocks();

    mockOAuth2Client = {
      setCredentials: jest.fn()
    };

    mockGmail = {
      users: {
        messages: {
          send: jest.fn()
        }
      }
    };

    google.auth.OAuth2.mockReturnValue(mockOAuth2Client);
    google.gmail.mockReturnValue(mockGmail);
  });

  test('sends email successfully', async () => {
    mockGmail.users.messages.send.mockResolvedValueOnce({
      data: { id: 'message-123' }
    });

    const credentials = {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    };

    const result = await sendEmail(
      'recipient@example.com',
      'Test Subject',
      '<html>Test Body</html>',
      credentials
    );

    expect(result.messageId).toBe('message-123');
    expect(mockOAuth2Client.setCredentials).toHaveBeenCalledWith({
      refresh_token: 'refresh-token'
    });
  });

  test('constructs email with proper headers', async () => {
    mockGmail.users.messages.send.mockResolvedValueOnce({
      data: { id: 'message-123' }
    });

    const credentials = {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    };

    await sendEmail(
      'recipient@example.com',
      'Test Subject',
      '<html>Test</html>',
      credentials
    );

    const callArgs = mockGmail.users.messages.send.mock.calls[0][0];
    const rawMessage = Buffer.from(callArgs.requestBody.raw, 'base64').toString();

    expect(rawMessage).toContain('To: recipient@example.com');
    expect(rawMessage).toContain('Subject: Test Subject');
    expect(rawMessage).toContain('Content-Type: text/html');
  });

  test('throws error when send fails', async () => {
    mockGmail.users.messages.send.mockRejectedValueOnce(
      new Error('Send failed')
    );

    const credentials = {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    };

    await expect(
      sendEmail('recipient@example.com', 'Subject', '<html>Body</html>', credentials)
    ).rejects.toThrow('Send failed');
  });
});
