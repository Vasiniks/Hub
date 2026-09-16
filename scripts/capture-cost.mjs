// Frame cost of an environment (reflection) capture: per-frame CPU time and draw calls for the
// seven frames a capture spans, against quiet frames either side. Uncapped.
import { chromium } from 'playwright-core';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
const extra = process.argv[2] ? `&${process.argv[2]}` : '';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto(`${base}/?debug&pr=1.5&hour=13${extra}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.evaluate(() => window.__room.parkCamera([0, 1.175, 0.16], [-0.05, 1.03, -0.95], 54));
await wait(2500);
const result = await page.evaluate(async () => {
  const r = window.__room;
  const runs = [];
  for (let k = 0; k < 6; k++) {
    // A forced hour change requests a capture; record frame deltas while it runs.
    const deltas = [];
    let last = performance.now();
    await new Promise((res) => {
      let n = 0;
      const tick = (now) => {
        deltas.push(+(now - last).toFixed(2));
        last = now;
        if (n === 4) r.setHour(13 + (k % 2) * 0.01);
        if (++n < 20) requestAnimationFrame(tick);
        else res();
      };
      requestAnimationFrame(tick);
    });
    runs.push(deltas);
    await new Promise((res) => setTimeout(res, 400));
  }
  return runs;
});
// Frames 5..12 cover the capture (6 faces + PMREM); 13..19 are quiet again.
const avg = (a) => +(a.reduce((x, y) => x + y, 0) / a.length).toFixed(2);
const quiet = result.flatMap((d) => d.slice(14, 20));
const capture = result.flatMap((d) => d.slice(6, 13));
const perSlot = [...Array(8)].map((_, i) => avg(result.map((d) => d[5 + i])));
console.log('quiet frame avg ms:', avg(quiet), '| capture frames avg ms:', avg(capture), '| per frame after request:', perSlot.join(' '));
await browser.close();
