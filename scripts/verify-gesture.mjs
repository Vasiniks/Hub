// §20: one book per committed gesture, however violent the input.
import { chromium } from 'playwright-core';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto('http://127.0.0.1:5173/?debug&hour=21.6', { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 });
await wait(2200);
await page.keyboard.press('Space');
await page.waitForFunction(() => window.__room.mode() === 'seated', { timeout: 9000 });
await page.evaluate(() => window.__room.openShelf());
await wait(2400);

const idx = () => page.evaluate(() => window.__room.shelf().index);
const results = [];
const start0 = await idx();

// 1. One slow notch.
await page.mouse.wheel(0, 120);
await wait(900);
results.push(['single slow notch', (await idx()) - start0]);

// 2. A violent continuous flick: 40 rapid events, no pause.
let base = await idx();
for (let i = 0; i < 40; i++) await page.mouse.wheel(0, 140);
await wait(1100);
results.push(['violent 40-event flick', (await idx()) - base]);

// 3. An enormous single event.
base = await idx();
await page.mouse.wheel(0, 4000);
await wait(1100);
results.push(['one huge 4000px event', (await idx()) - base]);

// 4. Three deliberate gestures, each separated by a pause. Backwards, so the earlier tests
//    have not already walked the selection into the end of the shelf.
base = await idx();
for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, -130); await wait(420); }
results.push(['three paced gestures', (await idx()) - base]);

// 5. Four deliberate key presses. (Playwright's keyboard.down does not auto-repeat, so a
//    held key would only ever prove that one keydown steps once.)
base = await idx();
for (let i = 0; i < 4; i++) { await page.keyboard.press('ArrowLeft'); await wait(300); }
await wait(500);
results.push(['four ArrowLeft presses', (await idx()) - base]);

for (const [name, moved] of results) console.log(`  ${name.padEnd(26)} -> ${moved >= 0 ? '+' : ''}${moved}`);
const flick = results[1][1], huge = results[2][1], paced = results[3][1];
const keys = results[4][1];
const pass = Math.abs(results[0][1]) === 1 && Math.abs(flick) === 1 && Math.abs(huge) === 1 && Math.abs(paced) === 3 && Math.abs(keys) === 4;
console.log(pass ? 'PASS: one book per gesture' : 'FAIL');
console.log('errors:', JSON.stringify(errors.slice(0, 4)));
await browser.close();
