const { getStyles } = require('../../src/email/styles');

describe('Email Styles', () => {
  test('returns CSS string', () => {
    const styles = getStyles();

    expect(typeof styles).toBe('string');
    expect(styles.length).toBeGreaterThan(0);
  });

  test('includes body styles', () => {
    const styles = getStyles();

    expect(styles).toContain('body');
    expect(styles).toContain('font-family');
  });

  test('includes responsive styles', () => {
    const styles = getStyles();

    expect(styles).toContain('@media');
  });

  test('includes link styles', () => {
    const styles = getStyles();

    expect(styles).toContain('a');
    expect(styles).toContain('color');
  });
});
