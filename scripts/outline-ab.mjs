// Deterministic outline comparison: parked camera, forced hover, grain off via fixed time.
// Usage: node scripts/outline-ab.mjs <outDir>
import { chromium } from 'playwright-core';
const out = process.argv[2];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const views = [
  { id: 'frc-robot', hour: 21, p: [-0.2, 1.2, 1.1], t: [-1.12, 0.3, 0.34], fov: 40 },
  { id: 'dev-board', hour: 13, p: [0.6, 1.15, -0.15], t: [0.9, 0.76, -0.7], fov: 34 },
  { id: 'notebooks', hour: 18.5, p: [0, 1.2, 0.3], t: [-0.4, 0.75, -0.6], fov: 50 },
];
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
for (const variant of ['stock', 'shared']) {
  for (const v of views) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    page.on('pageerror', (e) => console.log('ERR', e.message));
    page.on('console', (m) => m.type() === 'error' && console.log('CONSOLE', m.text()));
    await page.goto(`http://127.0.0.1:5173/?debug&pr=1&hour=${v.hour}&outline=${variant}&motion=reduce`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
    await page.evaluate((vv) => { window.__room.parkCamera(vv.p, vv.t, vv.fov); window.__room.forceHover(vv.id); }, v);
    await wait(2200);
    await page.screenshot({ path: `${out}/ol-${variant}-${v.id}.png` });
    await page.close();
  }
}
await browser.close();
