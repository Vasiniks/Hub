// Frame pacing in a real (headed) Chrome window with vsync, as a visitor sees it.
// Usage: node scripts/real-chrome.mjs [hour=21] [seconds=6] [extra query]
import { chromium } from 'playwright-core';
const hour = process.argv[2] ?? '21';
const seconds = Number(process.argv[3] ?? 6);
const extra = process.argv[4] ? `&${process.argv[4]}` : '';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome',
  headless: false,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--window-size=1728,1000', '--window-position=0,0'],
});
const page = await browser.newPage({ viewport: null });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto(`${process.env.BASE ?? 'http://127.0.0.1:5173'}/?debug&hour=${hour}${extra}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await wait(2500);
await page.mouse.move(860, 500);
await page.mouse.wheel(0, 120);
await wait(4000);
async function sample(label, action) {
  await page.evaluate(() => window.__room.perf.reset());
  await action();
  const s = await page.evaluate(() => window.__room.perf.snapshot());
  const frames = await page.evaluate(() => window.__room.frames?.() ?? null);
  console.log(
    `${label.padEnd(14)} fps ${String(s.fps).padStart(5)}  frame p50/p95/max ${s.frameMs.p50}/${s.frameMs.p95}/${s.frameMs.max}  cpu ${s.cpuMs.avg}/${s.cpuMs.p95}  missed ${s.missed}  pr ${s.pixelRatio}  calls ${s.drawCalls?.p50}`,
    frames ?? '',
  );
}
await sample('seated idle', () => wait(seconds * 1000));
await sample('seated look', async () => {
  const start = Date.now();
  while (Date.now() - start < seconds * 1000) {
    const t = (Date.now() - start) / (seconds * 1000);
    await page.mouse.move(860 + Math.sin(t * Math.PI * 4) * 700, 500 + Math.sin(t * Math.PI * 8) * 200);
    await wait(8);
  }
});
await page.mouse.move(860, 500);
await wait(1200);
await sample('hover sweep', async () => {
  const start = Date.now();
  while (Date.now() - start < seconds * 1000) {
    const s = await page.evaluate((id) => window.__room.hitPositionOf(id), 'dev-board');
    if (s) await page.mouse.move(s.x + Math.sin(Date.now() / 90) * 10, s.y + Math.cos(Date.now() / 110) * 6);
    await wait(12);
  }
});
await sample('popup open', async () => {
  const s = await page.evaluate((id) => window.__room.hitPositionOf(id), 'dev-board');
  if (s) {
    await page.mouse.move(s.x, s.y);
    await wait(400);
    await page.mouse.down();
    await page.mouse.up();
  }
  await wait(seconds * 1000);
});
await page.keyboard.press('Escape');
await wait(1800);
await sample('time sweep', async () => {
  for (let i = 0; i < Math.round(seconds * 4); i++) {
    await page.evaluate((h) => window.__room.setHour(h), (Number(hour) + i * 0.25) % 24);
    await wait(250);
  }
});
console.log('errors', errors.slice(0, 3));
await browser.close();
