// GPU cost A/B: each variant measured at the same fixed pixel ratio, uncapped.
// Usage: node scripts/ab.mjs [hour] [ratio]
import { chromium } from 'playwright-core';

const hour = process.argv[2] ?? '13';
const ratio = process.argv[3] ?? '1.5';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const variants = process.env.VARIANTS
  ? JSON.parse(process.env.VARIANTS)
  : [
      ['new defaults', `&pr=${ratio}`],
      ['legacy: msaa4, ao full, vol 0.4', `&pr=${ratio}&msaa=4&ao=full&volscale=0.4`],
      ['msaa=4 only', `&pr=${ratio}&msaa=4`],
      ['ao=full only', `&pr=${ratio}&ao=full`],
      ['ratio-1 (reference)', `&pr=1`],
    ];

const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'],
});
console.log(`hour ${hour}, ratio ${ratio} at 1440x900 (deviceScaleFactor 2)`);
console.log('variant'.padEnd(46) + ' | standing fps  p50   p95 | seated fps  p50   p95');
for (const [name, query] of variants) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}${query}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined);
  await page.mouse.move(720, 450);
  await wait(4500);
  const snap = async () => {
    await page.evaluate(() => window.__room.perf.reset());
    await wait(3000);
    return page.evaluate(() => window.__room.perf.snapshot());
  };
  const s = await snap();
  await page.mouse.wheel(0, 120);
  await wait(4500);
  const d = await snap();
  let popup = null;
  if (process.env.POPUP) {
    // Open the first object through the keyboard list: deterministic, no aiming needed.
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    await wait(2200);
    popup = await snap();
  }
  const f = (v) => `${String(v.fps).padStart(5)} ${String(v.frameMs.p50).padStart(5)} ${String(v.frameMs.p95).padStart(5)}`;
  console.log(`${name.padEnd(46)} | ${f(s)}      | ${f(d)}${popup ? '   | popup ' + f(popup) : ''}   pr=${d.pixelRatio}${errors.length ? ' errors=' + errors[0] : ''}`);
  await ctx.close();
}
await browser.close();
