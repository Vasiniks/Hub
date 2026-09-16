// Close parked views for judging fine shading detail. Usage: node scripts/detail-shot.mjs <outDir> <tag> "<query>"
import { chromium } from 'playwright-core';
const [out, tag, query = ''] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const views = [
  { name: 'keyboard', hour: 13, p: [0.05, 1.05, -0.2], t: [-0.05, 0.74, -0.46], fov: 30 },
  { name: 'lampbase', hour: 21, p: [-0.45, 0.95, -0.6], t: [-0.7, 0.74, -1.0], fov: 32 },
  { name: 'desk', hour: 18.5, p: [0, 1.175, 0.16], t: [-0.05, 1.0, -0.95], fov: 54 },
];
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
for (const v of views) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  page.on('pageerror', (e) => console.log('ERR', e.message));
  await page.goto(`http://127.0.0.1:5173/?debug&pr=1.5&hour=${v.hour}&${query}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
  await page.evaluate((vv) => window.__room.parkCamera(vv.p, vv.t, vv.fov), v);
  await wait(2000);
  await page.screenshot({ path: `${out}/${v.name}-${tag}.png` });
  await page.close();
}
await browser.close();
