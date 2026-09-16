// Reduced motion: the room must still be fully usable, with the transitions simplified.
import { chromium } from 'playwright-core';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const out = {};
await page.goto('http://127.0.0.1:5173/?debug&hour=21.6', { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 });
await wait(2000);

const t0 = Date.now();
await page.keyboard.press('Space');
await page.waitForFunction(() => window.__room.mode() === 'seated', { timeout: 6000 });
out.sitMs = Date.now() - t0;

await page.evaluate(() => window.__room.openShelf());
await wait(700);
out.shelfEntered = await page.evaluate(() => window.__room.shelf());
// With reduced motion the book should already be fully out, not still springing.
await page.evaluate(() => window.__room.stepBook(1));
await wait(120);
out.afterStepImmediate = await page.evaluate(() => window.__room.shelf());
await page.evaluate(() => window.__room.inspectBook());
await wait(500);
out.panel = await page.evaluate(() => window.__room.panelOpen());
await page.keyboard.press('Escape');
await wait(400);
await page.keyboard.press('Escape');
await wait(900);
out.back = await page.evaluate(() => window.__room.mode());
await page.screenshot({ path: process.argv[2] + '/reduced-motion.png' });
out.errors = errors.slice(0, 5);
console.log(JSON.stringify(out));
await browser.close();
