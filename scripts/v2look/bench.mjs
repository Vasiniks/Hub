// v2-look frame cost: GPU-fenced A/B (alternating rounds) of the Blender display LUT and of the
// environment specular, at the bench conditions of the briefs (1728x1000 CSS, pixel ratio 1.5).
//   ROOM_URL=http://127.0.0.1:5192 node scripts/v2look/bench.mjs [cam=CAM_seat] [extra query]
import fs from 'node:fs';
import { chromium } from 'playwright-core';
const cam = process.argv[2] ?? 'CAM_seat';
const extra = process.argv[3] ? '&' + process.argv[3] : '';
const base = (process.env.ROOM_URL ?? 'http://127.0.0.1:5192').replace(/\/+$/, '');
const shot = JSON.parse(fs.readFileSync('tmp/v2look/shots/new.json', 'utf8')).shots[cam].pose;
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true, args: ['--ignore-gpu-blocklist', '--use-angle=d3d11'] });
const page = await browser.newPage({ viewport: { width: 1728, height: 1000 }, deviceScaleFactor: 1 });
await page.goto(`${base}/?v2&debug&pr=1.5&adaptive=0${extra}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__v2look !== undefined, null, { timeout: 120000 });
await page.waitForTimeout(2000);
await page.evaluate(({ p, q, fov }) => window.__v2look.setPose(p, q, fov), shot);
const runs = [];
for (let i = 0; i < 3; i++) runs.push(await page.evaluate(() => window.__v2look.bench(30, 8)));
console.log(JSON.stringify({ cam, runs }, null, 1));
await browser.close();
