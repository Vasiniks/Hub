// Deterministic frames (parked camera, grain frozen) from two servers, for pixel comparison.
// Usage: node scripts/frame-diff.mjs <outDir> <tag> [base url]
import { chromium } from 'playwright-core';
const [out, tag, base = 'http://127.0.0.1:5173'] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const shots = [
  { key: 'night', hour: 21, p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  { key: 'dusk', hour: 18.5, p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  { key: 'day', hour: 13, p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
];
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
for (const s of shots) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 750 } });
  // Reduced motion freezes grain and idle sway, so two builds render the same frame.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${base}/?debug&pr=1&hour=${s.hour}&lorenz=0`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
  await page.evaluate((v) => window.__room.parkCamera(v.p, v.t, v.fov), s);
  await wait(1800);
  await page.screenshot({ path: `${out}/${s.key}-${tag}.png` });
  await page.close();
}
await browser.close();
