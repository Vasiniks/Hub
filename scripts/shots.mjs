// Composition screenshots across times of day: standing, seated, and a glance each way.
// Usage: node scripts/shots.mjs <outDir> <hour> [hour...]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const [outDir, ...hours] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });

for (const hour of hours) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: Number(process.env.DSF ?? 1) });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => ['error', 'warning'].includes(m.type()) && errors.push(`${m.type()}: ${m.text()}`));
  await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}${process.env.Q ?? ''}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined);
  await page.mouse.move(720, 450);
  await wait(4000);
  const tag = (process.env.TAG ?? '') + String(hour).replace('.', '_');
  await page.screenshot({ path: path.join(outDir, `h${tag}-1-standing.png`) });
  await page.mouse.wheel(0, 120);
  await wait(4200);
  await page.mouse.move(720, 450);
  await wait(1200);
  await page.screenshot({ path: path.join(outDir, `h${tag}-2-seated.png`) });
  await page.mouse.move(60, 380, { steps: 10 });
  await wait(2200);
  await page.screenshot({ path: path.join(outDir, `h${tag}-3-look-left.png`) });
  await page.mouse.move(1380, 380, { steps: 16 });
  await wait(2600);
  await page.screenshot({ path: path.join(outDir, `h${tag}-4-look-right.png`) });
  console.log(`hour ${hour}: mode=${await page.evaluate(() => window.__room.mode())} errors=${JSON.stringify(errors.slice(0, 5))}`);
  await page.close();
}
await browser.close();
