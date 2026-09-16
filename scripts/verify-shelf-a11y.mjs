// The bookshelf, driven entirely from the keyboard.
import { chromium } from 'playwright-core';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const out = {};
await page.goto('http://127.0.0.1:5173/?debug&hour=21.6', { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 });
await wait(2500);

// Sit with the keyboard, then tab to the shelf entry in the object nav.
await page.keyboard.press('Space');
await wait(4000);
out.seated = await page.evaluate(() => window.__room.mode());

for (let i = 0; i < 12; i++) {
  await page.keyboard.press('Tab');
  const label = await page.evaluate(() => document.activeElement?.textContent ?? '');
  if (label === 'Bookshelf') { out.tabbedTo = label; break; }
}
await wait(400);
await page.keyboard.press('Enter');
await wait(2400);
out.entered = await page.evaluate(() => window.__room.shelf());
out.focusAfterEnter = await page.evaluate(() => document.activeElement?.id);
out.announced = await page.textContent('#live');

await page.keyboard.press('ArrowRight');
await page.keyboard.press('ArrowRight');
await wait(900);
out.afterArrows = await page.evaluate(() => window.__room.shelf());
out.announcedAfter = await page.textContent('#live');

await page.keyboard.press('Enter');
await wait(900);
out.panel = {
  open: await page.evaluate(() => window.__room.panelOpen()),
  title: await page.textContent('#panel-title'),
  // Class state is not visibility: a stray id rule once hid the panel entirely while
  // every class-based assertion still passed.
  visible: await page.evaluate(() => {
    const el = document.getElementById('panel');
    const r = el.getBoundingClientRect();
    return r.width > 100 && r.height > 100 && getComputedStyle(el).display !== 'none';
  }),
};
out.focusInPanel = await page.evaluate(() => document.activeElement?.id);

await page.keyboard.press('Escape');
await wait(600);
out.afterEsc1 = { panelOpen: await page.evaluate(() => window.__room.panelOpen()), shelf: await page.evaluate(() => window.__room.shelf()) };
await page.keyboard.press('Escape');
await wait(1800);
out.afterEsc2 = { mode: await page.evaluate(() => window.__room.mode()), shelf: await page.evaluate(() => window.__room.shelf()) };
out.focusRestored = await page.evaluate(() => document.activeElement?.textContent ?? document.activeElement?.tagName);
out.errors = errors.slice(0, 5);
console.log(JSON.stringify(out, null, 1));
await browser.close();
