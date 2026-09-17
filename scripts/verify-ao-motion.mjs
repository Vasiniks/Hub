// Motion-adaptive AO: half resolution while the view sweeps, full once still, no error.
// Usage: node scripts/verify-ao-motion.mjs [hour=13]
import { chromium } from 'playwright-core';
const hour = process.argv[2] ?? '13';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(`${process.env.BASE ?? 'http://127.0.0.1:5173'}/?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.mouse.move(720, 450);
await page.mouse.wheel(0, 120);
await wait(4500);
// Sample the scale on every animation frame for a window.
const sample = (ms) =>
  page.evaluate(
    (ms) =>
      new Promise((resolve) => {
        const out = { full: 0, half: 0, computed: 0, frames: 0 };
        const end = performance.now() + ms;
        const tick = () => {
          out.frames++;
          if (window.__room.aoComputed()) out.computed++;
          window.__room.aoScale() === 1 ? out.full++ : out.half++;
          if (performance.now() < end) requestAnimationFrame(tick);
          else resolve(out);
        };
        requestAnimationFrame(tick);
      }),
    ms,
  );
const idle = await sample(2000);
const sweepDone = (async () => {
  const start = Date.now();
  while (Date.now() - start < 2000) {
    const t = (Date.now() - start) / 2000;
    await page.mouse.move(720 + Math.sin(t * Math.PI * 2) * 500, 450 + Math.sin(t * Math.PI * 4) * 120);
    await wait(16);
  }
})();
const moving = await sample(1800);
await sweepDone;
const settle = await sample(2000);
const settled = await page.evaluate(() => window.__room.aoScale());
console.log(JSON.stringify({ idle, moving, settle, settledScale: settled, errors }));
const ok = idle.half / idle.frames < 0.1 && moving.half / moving.frames > 0.7 && settled === 1 && errors.length === 0;
console.log(ok ? 'PASS' : 'FAIL');
await browser.close();
process.exit(ok ? 0 : 1);
