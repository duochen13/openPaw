const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/duochen/.claude/skills/gstack/node_modules/playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(__dirname, '../index.html')).href);
    assert.equal(await page.locator('#people .card').count(), 3);
    await page.selectOption('#status', 'self_disclosed');
    assert.equal(await page.locator('#position-rows tr').count(), 1);
    assert.match(await page.locator('#position-rows').innerText(), /FICO/);
    await page.selectOption('#investor', 'grantham');
    assert.equal(await page.locator('#empty').isVisible(), true);
    await page.click('#reset');
    await page.fill('#ticker', 'NVDA');
    assert.ok(await page.locator('#position-rows tr').count() > 0);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    console.log('Dashboard checks passed: filters, empty state, mobile layout, and JavaScript.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
