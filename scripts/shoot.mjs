// Seated screenshots for A/B comparison. Usage: node scripts/shoot.mjs <outDir> <name> "<query>" [look x,y] [shelf]
import { chromium } from 'playwright-core';
const [outDir, name, query = '', look = '720,450', mode = ''] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (e) => console.log('ERR', e.message));
await page.goto(`http://127.0.0.1:5173/?debug&pr=1&${query}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.mouse.move(720, 450);
await wait(1800);
await page.mouse.wheel(0, 120);
await wait(3600);
const [lx, ly] = look.split(',').map(Number);
await page.mouse.move(lx, ly);
await wait(2600);
if (mode === 'shelf') {
  await page.evaluate(() => window.__room.openShelf());
  await wait(3200);
}
await page.screenshot({ path: `${outDir}/${name}.png` });
await browser.close();
