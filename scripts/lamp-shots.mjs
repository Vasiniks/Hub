// Night close-ups of the lamp pool (cube, mug, arm) per URL variant, frozen grain.
// Usage: node scripts/lamp-shots.mjs <outDir> name:query [name:query ...]   e.g. point:lamp=point disk:
import { chromium } from 'playwright-core';
const [out, ...variants] = process.argv.slice(2);
const views = {
  cube: { p: [-0.05, 1.0, -0.2], t: [-0.25, 0.74, -0.62], fov: 40 },
  mug: { p: [-0.25, 1.0, -0.1], t: [-0.45, 0.74, -0.55], fov: 45 },
  arm: { p: [0.1, 1.05, -0.3], t: [-0.55, 0.8, -0.85], fov: 50 },
};
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal'] });
for (const v of variants) {
  const [name, q = ''] = v.split(':');
  const p = await b.newPage({ viewport: { width: 1000, height: 700 } });
  await p.emulateMedia({ reducedMotion: 'reduce' });
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && errs.push(m.text().slice(0, 300)));
  await p.goto(`http://127.0.0.1:5173/?debug&pr=1&hour=21&lorenz=0&${q}`);
  await p.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
  for (const [vn, vv] of Object.entries(views)) {
    await p.evaluate((x) => window.__room.parkCamera(x.p, x.t, x.fov), vv);
    await new Promise((r) => setTimeout(r, 1300));
    await p.screenshot({ path: `${out}/${name}-${vn}.png` });
  }
  console.log(name, errs.slice(0, 3));
  await p.close();
}
await b.close();
