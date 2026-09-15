// Local browser acceptance check. Set PLAYWRIGHT_MODULE to an installed package.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try {
 const page=await browser.newPage({viewport:{width:1360,height:1060}}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.goto(pathToFileURL(path.resolve('out/META.html')).href);
 await page.waitForSelector('.marker');
 assert.equal(await page.locator('.marker').count(),30);
 assert.match(await page.locator('#selected-date').textContent(),/Apr 25, 2024/);
 await page.screenshot({path:'out/META-desktop.png',fullPage:true});
 await page.locator('.marker[data-date="2022-02-03"]').click();
 assert.match(await page.locator('#selected-date').textContent(),/Feb 3, 2022/);
 assert.match(await page.locator('#facts').textContent(),/8-K/);
 assert.match(page.url(),/date=2022-02-03/);
 await page.locator('.marker[data-date="2024-02-02"]').focus();await page.keyboard.press('Enter');
 assert.equal(await page.evaluate(()=>document.activeElement.dataset.date),'2024-02-02');
 await page.selectOption('#view','price');
 assert.equal(await page.locator('#benchmark-key').isVisible(),false);
 await page.selectOption('#direction','up');
 assert.ok(await page.locator('.marker').count()>0);
 assert.ok((await page.locator('#selected-return').textContent()).startsWith('+'));
 await page.selectOption('#range','1');
 const selected=await page.locator('#selected-date').textContent();
 await page.locator('#next').focus();await page.keyboard.press('Enter');
 assert.notEqual(await page.locator('#selected-date').textContent(),selected);
 await page.selectOption('#direction','all');await page.selectOption('#range','all');await page.selectOption('#view','compare');
 await page.locator('.move-button[data-date="2024-04-25"]').click();
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:'out/META-mobile.png',fullPage:true});
 await page.locator('#theme').click();
 await page.screenshot({path:'out/META-mobile-dark.png',fullPage:true});
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#download-svg').click()]);
 assert.equal(download.suggestedFilename(),'META-price-events.svg');
 assert.deepEqual(errors,[]);
 assert.equal(requests.filter(u=>/^https?:/.test(u)).length,0);
 console.log(JSON.stringify({markers:30,desktop:true,mobile:true,selection:true,filters:true,keyboard:true,svgExport:true,externalRequests:0,consoleErrors:errors}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
