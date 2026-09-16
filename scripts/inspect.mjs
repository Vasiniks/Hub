// Close-up of any point in the room, for judging model quality.
// Usage: node scripts/inspect.mjs <out.png> <hour> <px,py,pz> <tx,ty,tz> [fov]
import { chromium } from 'playwright-core';
const [out, hour, posStr, tgtStr, fov = '24'] = process.argv.slice(2);
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
page.on('pageerror', (e) => console.log('ERR', e.message));
await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, { timeout: 30000 });
await wait(2500);
await page.evaluate(([p, t, f]) => window.__room.parkCamera(p, t, f), [posStr.split(',').map(Number), tgtStr.split(',').map(Number), Number(fov)]);
await wait(1800);
await page.screenshot({ path: out });
await browser.close();
