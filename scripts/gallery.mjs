// The frames worth looking at: arrival, the seated desk, an inspection, the shelf, and the day.
import { chromium } from 'playwright-core';
import path from 'node:path';
import fs from 'node:fs';
const out = process.argv[2];
fs.mkdirSync(out, { recursive: true });
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const errors = [];

async function open(hour) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on('pageerror', (e) => errors.push(`${hour}: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && errors.push(`${hour}: ${m.text()}`));
  await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 });
  await page.mouse.move(800, 500);
  await wait(3200);
  return page;
}
const sit = async (page) => { await page.mouse.wheel(0, 120); await wait(4200); await page.mouse.move(800, 500); await wait(1400); };

// 1–2 Night: arrival and the seated desk.
let page = await open(21.6);
await page.screenshot({ path: path.join(out, '1-night-standing.png') });
await sit(page);
await page.screenshot({ path: path.join(out, '2-night-seated.png') });
// 3 Inspecting the robot, via the accessible nav so the framing is deterministic.
await page.evaluate(() => {
  const b = [...document.querySelectorAll('#object-nav button')].find((x) => x.textContent.includes('FRC'));
  b.click();
});
await wait(3000);
await page.screenshot({ path: path.join(out, '3-inspect-robot.png') });
await page.keyboard.press('Escape');
await wait(1800);
// 4 Bookshelf browsing.
await page.evaluate(() => window.__room.openShelf());
await wait(2400);
await page.evaluate(() => { window.__room.stepBook(1); window.__room.stepBook(1); });
await wait(1400);
await page.screenshot({ path: path.join(out, '4-bookshelf.png') });
await page.keyboard.press('Escape');
await wait(1600);
// 8 The music widget, open.
await page.click('#music-toggle');
await wait(1800);
await page.screenshot({ path: path.join(out, '8-music.png') });
await page.close();

// 5 Daylight, 6 golden hour.
page = await open(13);
await sit(page);
await page.screenshot({ path: path.join(out, '5-day-seated.png') });
await page.close();
page = await open(18.5);
await page.screenshot({ path: path.join(out, '6-golden-standing.png') });
await sit(page);
await page.screenshot({ path: path.join(out, '7-golden-seated.png') });
await page.close();
console.log('errors:', JSON.stringify(errors.slice(0, 6)));
await browser.close();
