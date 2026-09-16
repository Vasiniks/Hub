// Book row geometry check: while a book is presented, no other book may sit in front of or
// behind its cover. Reports overlaps in shelf-local space, and saves frames for inspection.
// Usage: node scripts/verify-books.mjs [outDir]
import { chromium } from 'playwright-core';
const out = process.argv[2];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto('http://127.0.0.1:5173/?debug&pr=1&hour=12', { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.mouse.move(720, 450);
await wait(1200);
await page.mouse.wheel(0, 120);
await wait(3800);
if (out) await page.screenshot({ path: `${out}/books-room.png` });
await page.evaluate(() => window.__room.openShelf());
await wait(3200);

/** Footprint of each book on the shelf plane (x along the wall, z out into the room). */
const footprints = () => page.evaluate(() => window.__room.bookFootprints());
let failures = 0;
async function check(label) {
  await wait(1700);
  const { selected, books } = await footprints();
  const sel = books[selected];
  const hits = books
    .map((b, i) => ({ i, b }))
    // Seen from the room, the presented cover hides any book whose extent along the row it
    // spans — the cover sits in front, so depth doesn't matter, only the x-overlap does.
    .filter(({ i, b }) => i !== selected && b.x1 > sel.x0 + 0.004 && b.x0 < sel.x1 - 0.004);
  const ok = hits.length === 0;
  if (!ok) failures++;
  console.log(`${label.padEnd(24)} selected=${selected} ${ok ? 'clear' : `OVERLAP with ${hits.map((h) => h.i).join(',')}`}`);
  if (out) await page.screenshot({ path: `${out}/books-${label}.png` });
}
await check('initial');
for (let i = 0; i < 6; i++) await page.evaluate(() => window.__room.stepBook(-1));
await check('first');
for (let i = 0; i < 5; i++) {
  await page.evaluate(() => window.__room.stepBook(1));
  await wait(500);
}
await check('middle');
for (let i = 0; i < 8; i++) {
  await page.evaluate(() => window.__room.stepBook(1));
  await wait(450);
}
await check('last');
await page.keyboard.press('Escape');
await wait(2200);
const after = await footprints();
const displaced = after.books.filter((b) => Math.abs(b.shove) > 0.002).length;
console.log(`returned to room: ${displaced} books still displaced`);
if (displaced) failures++;
if (out) await page.screenshot({ path: `${out}/books-returned.png` });
console.log(failures || errors.length ? `FAIL (${failures} checks, errors ${errors.length})` : 'PASS: presented book never overlaps the row');
await browser.close();
