// Fence-timed cost of each material in view (all its meshes hidden at once), seated centre pose.
// Usage: node scripts/bench-materials.mjs [hour=13] [pr=1.5] [extra query]
import { chromium } from 'playwright-core';
const hour = process.argv[2] ?? '13';
const pr = process.argv[3] ?? '1.5';
const extra = process.argv[4] ? `&${process.argv[4]}` : '';
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}&pr=${pr}${extra}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await new Promise((r) => setTimeout(r, 2500));
const pose = { p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54, materials: true, quick: false };
const r = await page.evaluate((p) => window.__room.bench(p), pose);
console.log(`hour ${hour} pr ${pr}: idle ${r.frame.idle} ms, look ${r.frame.look} ms, calls ${r.calls}`);
for (const x of r.materials.slice(0, 18)) console.log(`   ${x.label.slice(0, 44).padEnd(44)} ${String(x.cost).padStart(6)} ms`);
await browser.close();
