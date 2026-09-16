// Finds shader programs compiled after the loading screen: sweeps the clock and the main
// interactions, logging any new program and the frame time it cost.
import { chromium } from 'playwright-core';
const start = Number(process.argv[2] ?? 13);
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (e) => console.log('ERR', e.message));
await page.goto(`${base}/?debug&pr=1&hour=${start}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await wait(1500);
const keys = () => page.evaluate(() => window.__room.programKeys());
let known = new Set(await keys());
console.log('programs after load:', known.size);
async function check(label) {
  const now = await keys();
  const fresh = now.filter((k) => !known.has(k));
  const snap = await page.evaluate(() => window.__room.perf.snapshot());
  if (fresh.length) console.log(`${label}: +${fresh.length} programs (max frame ${snap.frameMs?.max} ms)`, fresh.map((k) => k.slice(0, 60)));
  known = new Set(now);
}
await page.evaluate(() => window.__room.perf.reset());
await page.mouse.move(720, 450);
await page.mouse.wheel(0, 120);
await wait(3800);
await check('sit');
for (let h = 0; h <= 24; h += 0.5) {
  await page.evaluate((hh) => window.__room.setHour(hh), (start + h) % 24);
  await wait(120);
  await check(`hour ${((start + h) % 24).toFixed(1)}`);
}
for (const id of ['dev-board', 'frc-robot', 'notebooks', 'polyhedron', 'parts-crate']) {
  await page.evaluate((pid) => window.__room.forceHover(pid), id);
  await wait(300);
  await check(`hover ${id}`);
}
await page.evaluate(() => window.__room.forceHover(null));
await page.evaluate(() => window.__room.openShelf());
await wait(2500);
await check('shelf');
await browser.close();
