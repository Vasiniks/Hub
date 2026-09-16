// Bookshelf browsing: enter, step both ways, inspect, back out. Screenshots each state.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
const outDir = process.argv[2] ?? 'shelf-shots';
const hour = process.argv[3] ?? '21.6';
fs.mkdirSync(outDir, { recursive: true });
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: Number(process.env.DSF ?? 1) });
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const room = (fn, arg) => page.evaluate(fn, arg);
const shot = (n) => page.screenshot({ path: path.join(outDir, `${n}.png`) });
const log = [];

await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 });
await page.mouse.move(720, 450);
await wait(2500);

// Sit down first.
await page.mouse.wheel(0, 120);
await wait(4000);
await page.mouse.move(720, 450);
await wait(1200);

// Look left until the shelf is hovered, the way a visitor would find it.
await page.mouse.move(70, 400, { steps: 20 });
await wait(2600);
log.push(['hover-after-looking-left', await room(() => window.__room.hovered())]);
await shot('1-look-left');

await room(() => window.__room.openShelf());
await wait(2200);
log.push(['entered', JSON.stringify(await room(() => window.__room.shelf()))]);
await shot('2-shelf-entered');

for (const d of [1, 1, 1]) await (room((x) => window.__room.stepBook(x), d), wait(500));
await wait(900);
log.push(['after-right-x3', JSON.stringify(await room(() => window.__room.shelf()))]);
await shot('3-stepped-right');

await room(() => window.__room.stepBook(-1));
await wait(300);
await room(() => window.__room.stepBook(-1));
await wait(1100);
log.push(['after-left-x2', JSON.stringify(await room(() => window.__room.shelf()))]);
await shot('4-stepped-left');

await room(() => window.__room.inspectBook());
await wait(900);
log.push(['panel-open', await room(() => window.__room.panelOpen()), await page.textContent('#panel-title')]);
await shot('5-book-open');

await page.keyboard.press('Escape');
await wait(700);
log.push(['after-esc-1 (panel closed, still browsing)', await room(() => window.__room.panelOpen()), JSON.stringify(await room(() => window.__room.shelf()))]);
await page.keyboard.press('Escape');
await wait(1800);
log.push(['after-esc-2 (back in the room)', await room(() => window.__room.mode()), JSON.stringify(await room(() => window.__room.shelf()))]);
await shot('6-returned');

for (const l of log) console.log(' ', l.join(' | '));
console.log('errors:', JSON.stringify(errors.slice(0, 6)));
await browser.close();
