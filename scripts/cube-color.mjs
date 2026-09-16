// Close daylight view of the speedcube under different pipeline variants, with sampled face
// colours (saturation / luminance) so washout is measured rather than eyeballed.
// Usage: node scripts/cube-color.mjs <outDir> [hour]
import { chromium } from 'playwright-core';
const [out, hour = '13'] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const variants = JSON.parse(process.env.VARIANTS ?? '{"default":"","novol":"vol=0","nobloom":"bloom=0","nograde":"grade=0","none":"vol=0&bloom=0&grade=0"}');
// Parked where the examined-object close-up puts the eye, and seated looking down at it.
const views = [
  { name: 'close', p: [-0.18, 0.95, -0.42], t: [-0.33, 0.765, -0.62], fov: 28 },
  { name: 'seated', p: [0.0, 1.175, 0.16], t: [-0.33, 0.77, -0.62], fov: 30 },
];
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
for (const v of views) {
  for (const [label, q] of Object.entries(variants)) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    await page.goto(`http://127.0.0.1:5173/?debug&pr=1&hour=${hour}&${q}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
    await page.evaluate((vv) => window.__room.parkCamera(vv.p, vv.t, vv.fov), v);
    await wait(1800);
    const file = `${out}/cube-${v.name}-${label}.png`;
    await page.screenshot({ path: file });
    await page.close();
  }
}
await browser.close();
