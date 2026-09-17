// Fence-timed GPU cost of the frame, each pass and each lighting feature at seated poses.
// Usage: node scripts/bench.mjs [hour=13] [pr=1.25] [extra query]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
const hour = process.argv[2] ?? '13';
const pr = process.argv[3] ?? '1.5';
const extra = process.argv[4] ? `&${process.argv[4]}` : '';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'],
});
// VIEWPORT=WxH (CSS px). The target Mac's browser window is ~1728×1000 at DPR 2.
const [vw, vh] = (process.env.VIEWPORT ?? '1728x1000').split('x').map(Number);
const page = await browser.newPage({ viewport: { width: vw, height: vh }, deviceScaleFactor: 2 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}&pr=${pr}${extra}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await wait(2500);
const poses = {
  seatedCentre: { p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54 },
  seatedRight: { p: [0, 1.175, 0.16], t: [0.9, 1.0, -0.6], fov: 54 },
  standing: { p: [1.06, 1.63, 0.96], t: [-0.3, 1.0, -0.95], fov: 54 },
};
const out = {};
for (const [name, pose] of Object.entries(poses)) out[name] = await page.evaluate((p) => window.__room.bench({ ...p, overdraw: true }), pose);
fs.mkdirSync('perf', { recursive: true });
fs.writeFileSync(`perf/bench-${hour}-${pr}.json`, JSON.stringify(out, null, 2));
for (const [name, r] of Object.entries(out)) {
  console.log(`\n== ${name} (hour ${hour}, pr ${pr}) frame look ${r.frame.look} ms (cpu ${r.frame.lookCpu}) | idle ${r.frame.idle} ms | calls ${r.calls} tris ${r.triangles}`);
  if (r.gtao) console.log('   gtao parts:', JSON.stringify(r.gtao));
  console.log('   output pass', r.outputPass, 'ms | overdraw', JSON.stringify(r.overdraw));
  for (const x of [...r.passes, ...r.features, ...(r.shadowRedraw ?? [])]) console.log(`   ${x.label.padEnd(26)} cost ${String(x.cost).padStart(6)} ms   (with ${x.with}, without ${x.without})`);
}
if (errors.length) console.log('errors', errors);
await browser.close();
