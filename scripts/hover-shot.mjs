// Screenshot an object while hovered, to compare outline implementations.
// Usage: node scripts/hover-shot.mjs <out.png> <projectId> "<query>"
import { chromium } from 'playwright-core';
const [out, id = 'dev-board', query = ''] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (e) => console.log('ERR', e.message));
page.on('console', (m) => m.type() === 'error' && console.log('CONSOLE', m.text()));
await page.goto(`http://127.0.0.1:5173/?debug&pr=1&arrive=0&${query}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.mouse.move(720, 450);
await wait(1500);
await page.mouse.wheel(0, 120);
await wait(3800);
for (let i = 0; i < 40; i++) {
  const s = await page.evaluate((pid) => window.__room.hitPositionOf(pid), id);
  if (s) await page.mouse.move(s.x, s.y);
  await wait(60);
}
await wait(800);
console.log('hovered', await page.evaluate(() => window.__room.hovered()));
await page.screenshot({ path: out });
await browser.close();
