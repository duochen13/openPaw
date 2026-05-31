const { logger } = require('../../src/utils/logger');

describe('Logger', () => {
  let consoleLogSpy;
  let consoleErrorSpy;

  beforeEach(() => {
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  test('info logs JSON with info level', () => {
    logger.info('Test message', { key: 'value' });

    expect(consoleLogSpy).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(consoleLogSpy.mock.calls[0][0]);
    expect(loggedData.level).toBe('INFO');
    expect(loggedData.message).toBe('Test message');
    expect(loggedData.key).toBe('value');
    expect(loggedData.timestamp).toBeDefined();
  });

  test('error logs JSON with error level', () => {
    const error = new Error('Test error');
    logger.error('Error occurred', { error });

    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(consoleErrorSpy.mock.calls[0][0]);
    expect(loggedData.level).toBe('ERROR');
    expect(loggedData.message).toBe('Error occurred');
    expect(loggedData.error).toBeDefined();
  });

  test('warn logs JSON with warn level', () => {
    logger.warn('Warning message');

    expect(consoleLogSpy).toHaveBeenCalledTimes(1);
    const loggedData = JSON.parse(consoleLogSpy.mock.calls[0][0]);
    expect(loggedData.level).toBe('WARN');
    expect(loggedData.message).toBe('Warning message');
  });
});
