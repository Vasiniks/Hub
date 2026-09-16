// Solo frame-rate measurement (run with no other browser rendering).
import { chromium } from 'playwright-core';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const hour = process.argv[2] ?? '21';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const fps = (ms) => page.evaluate((dur) => new Promise((res) => {
  let n = 0; const t0 = performance.now();
  const f = () => { n++; if (performance.now() - t0 < dur) requestAnimationFrame(f); else res(+(n / (dur / 1000)).toFixed(1)); };
  requestAnimationFrame(f);
}), ms);
await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined);
await page.mouse.move(720, 450);
await wait(3000);
const standing = await fps(3000);
await page.mouse.wheel(0, 120);
await wait(4500);
const seated = await fps(3000);
await page.focus('#object-nav button');
await page.keyboard.press('Enter');
await wait(2200);
const focusedMode = await page.evaluate(() => window.__room.mode());
const focused = await fps(3000);
console.log(JSON.stringify({ hour, standing, seated, focused, focusedMode, errors }));
await browser.close();
