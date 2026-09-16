// Quick look: load, screenshot standing + seated, report errors and state.
// Usage: node scripts/peek.mjs <outDir> <hour|live> [extraQuery]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
const [outDir, hour, extra = ''] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: Number(process.env.DSF ?? 1) });
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => ['error', 'warning'].includes(m.type()) && errors.push(`${m.type()}: ${m.text()}`));
const q = hour === 'live' ? '?debug' : `?debug&hour=${hour}`;
await page.goto(`http://127.0.0.1:5173/${q}${extra}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 }).catch(() => {});
await page.mouse.move(720, 450);
await wait(3500);
const tag = String(hour).replace('.', '_');
await page.screenshot({ path: path.join(outDir, `${tag}-standing.png`) });
await page.mouse.wheel(0, 120);
await wait(4200);
await page.mouse.move(720, 450);
await wait(1500);
await page.screenshot({ path: path.join(outDir, `${tag}-seated.png`) });
const state = await page.evaluate(() => (window.__room ? { mode: window.__room.mode(), hour: window.__room.hour(), pr: window.__room.pixelRatio(), cal: window.__room.calibration() } : 'no __room'));
console.log(tag, JSON.stringify(state), 'errors:', JSON.stringify(errors.slice(0, 6)));
await browser.close();
