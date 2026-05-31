function createLogger() {
  return {
    info: (message, data = {}) => {
      const logEntry = {
        level: 'INFO',
        message,
        timestamp: new Date().toISOString(),
        ...data
      };
      console.log(JSON.stringify(logEntry));
    },

    error: (message, data = {}) => {
      const logEntry = {
        level: 'ERROR',
        message,
        timestamp: new Date().toISOString(),
        ...data
      };
      console.error(JSON.stringify(logEntry));
    },

    warn: (message, data = {}) => {
      const logEntry = {
        level: 'WARN',
        message,
        timestamp: new Date().toISOString(),
        ...data
      };
      console.log(JSON.stringify(logEntry));
    }
  };
}

const logger = createLogger();

module.exports = { logger };
