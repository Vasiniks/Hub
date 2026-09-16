// Scenario profiler. Uncapped frame rate at retina scale so real cost is visible.
// Usage: node scripts/profile.mjs <label> [hour] [outFile]
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const label = process.argv[2] ?? 'run';
const hour = process.argv[3] ?? '13';
const outFile = process.argv[4];
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: [
    '--use-angle=metal',
    '--ignore-gpu-blocklist',
    '--disable-gpu-vsync',
    '--disable-frame-rate-limit',
    ...(process.env.PRECISE_MEM === '0' ? [] : ['--enable-precise-memory-info']),
  ],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const room = (fn, arg) => page.evaluate(fn, arg);

await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined);
await page.mouse.move(720, 450);
await wait(3000);

const results = { label, hour, scenarios: {} };
async function measure(name, action) {
  await room(() => window.__room.perf.reset());
  await action();
  results.scenarios[name] = await room(() => window.__room.perf.snapshot());
}

await measure('standing-idle', () => wait(3000));
await measure('sitting', async () => { await page.mouse.wheel(0, 120); await wait(3200); });
await page.mouse.move(720, 450);
await wait(1500);
await measure('look-sweep', async () => {
  for (let i = 0; i <= 100; i++) {
    const t = i / 100;
    await page.mouse.move(720 + Math.sin(t * Math.PI * 2) * 680, 450 + Math.sin(t * Math.PI * 4) * 180);
    await wait(30);
  }
});
await page.mouse.move(720, 450);
await wait(1500);

let hoverOk = false;
await measure('hover', async () => {
  const start = Date.now();
  while (Date.now() - start < 2500) {
    const s = await room((pid) => window.__room.hitPositionOf(pid), 'dev-board');
    if (s) await page.mouse.move(s.x + Math.sin(Date.now() / 90) * 6, s.y);
    await wait(40);
  }
  hoverOk = (await room(() => window.__room.hovered())) === 'dev-board';
});
results.hoverOk = hoverOk;

if (hoverOk) {
  await page.mouse.down();
  await page.mouse.up();
  await wait(1600);
  await measure('popup-open', () => wait(3000));
  results.popupOpen = await room(() => window.__room.panelOpen());
  await page.keyboard.press('Escape');
  await wait(1500);
}

await measure('time-change', async () => {
  for (let i = 0; i < 12; i++) {
    await room((h) => window.__room.setHour(h), 16 + i * 0.4);
    await wait(250);
  }
});

results.errors = errors;
const json = JSON.stringify(results, null, 2);
if (outFile) fs.writeFileSync(outFile, json);
console.log(json);
await browser.close();
