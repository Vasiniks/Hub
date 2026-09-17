// Reprojected AO/shafts vs recomputed-every-frame, while the view turns in small steps.
// Usage: node scripts/ao-reproject-check.mjs <outDir> [hour=21]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
const [out, hour = '21'] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const variants = { reproj: 'aomoving', every: 'aomoving&aocache=0' };
for (const [name, q] of Object.entries(variants)) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 750 } });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:5173/?debug&pr=1&hour=${hour}&lorenz=0&${q}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
  const eye = [0, 1.175, 0.16];
  for (let i = 0; i <= 6; i++) {
    const yaw = -0.35 + i * 0.012; // ~0.7° per step
    const t = [eye[0] - Math.sin(yaw), 1.0, eye[2] - Math.cos(yaw)];
    await page.evaluate(({ p, t }) => window.__room.parkCamera(p, t, 54), { p: eye, t });
    await new Promise((r) => setTimeout(r, i === 0 ? 1500 : 250));
    const computed = await page.evaluate(() => window.__room.aoComputed());
    await page.screenshot({ path: `${out}/${name}-${i}.png` });
    if (name === 'reproj') console.log('step', i, 'aoComputedLastFrame', computed);
  }
  console.log(name, 'errors', errors);
  await page.close();
}
await browser.close();
