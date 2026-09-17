// Frozen-grain parked renders of several views under URL variants, diffed against the first
// variant. Usage: VARIANTS='{"ref":"arealights=pixel","new":""}' node scripts/compare-variants.mjs <outDir> [hours=13,21]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
const [out, hoursArg = '13,21'] = process.argv.slice(2);
const variants = JSON.parse(process.env.VARIANTS);
const hours = hoursArg.split(',');
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const views = {
  seated: { p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  deskRight: { p: [0.35, 1.05, -0.25], t: [0.6, 0.76, -0.9], fov: 44 },
  shelf: { p: [-1.0, 1.25, -0.8], t: [-1.72, 1.2, -0.8], fov: 50 },
  standing: { p: [1.06, 1.63, 0.96], t: [-0.3, 1.0, -0.95], fov: 54 },
};
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
for (const [name, q] of Object.entries(variants)) {
  for (const hour of hours) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 750 } });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)));
    await page.goto(`${process.env.BASE ?? 'http://127.0.0.1:5173'}/?debug&pr=1&hour=${hour}&lorenz=0&${q}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
    // HOVER=<project id>: keep that object outlined in every view.
    if (process.env.HOVER) await page.evaluate((id) => window.__room.forceHover(id), process.env.HOVER);
    for (const [vname, v] of Object.entries(views)) {
      await page.evaluate((vv) => window.__room.parkCamera(vv.p, vv.t, vv.fov), v);
      await wait(1300);
      await page.screenshot({ path: `${out}/${name}-${hour}-${vname}.png` });
    }
    if (errors.length) console.log(name, hour, 'errors', errors.slice(0, 2));
    await page.close();
  }
}
await browser.close();
console.log(JSON.stringify({ variants: Object.keys(variants), hours, views: Object.keys(views) }));
