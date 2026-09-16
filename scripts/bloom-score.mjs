// Scores bloom variants on the two things that pull against each other: colour fidelity of the
// speedcube in a daylight close-up, and faithfulness to the established night look.
// Usage: VARIANTS='{"name":"query"}' node scripts/bloom-score.mjs <outDir>
import { chromium } from 'playwright-core';
const out = process.argv[2];
const variants = JSON.parse(process.env.VARIANTS);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const shots = [
  { key: 'night', hour: 21, p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  { key: 'dusk', hour: 18.5, p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  { key: 'day', hour: 13, p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  { key: 'cube', hour: 13, p: [-0.18, 0.95, -0.42], t: [-0.33, 0.765, -0.62], fov: 28 },
];
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
for (const [name, q] of Object.entries(variants)) {
  for (const s of shots) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 750 } });
    await page.goto(`http://127.0.0.1:5173/?debug&pr=1&hour=${s.hour}&${q}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
    await page.evaluate((v) => window.__room.parkCamera(v.p, v.t, v.fov), s);
    await wait(1600);
    await page.screenshot({ path: `${out}/${s.key}-${name}.png` });
    await page.close();
  }
}
await browser.close();
