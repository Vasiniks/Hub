// Interleaved page loads per variant, fence-timed seated look/idle frames at pinned resolution.
// Usage: VARIANTS='{"a":"q1","b":"http://127.0.0.1:5181|q2"}' (origin| prefix: another build) node scripts/bench-ab.mjs [rounds=3] [hour=13] [pr=1.5]
import { chromium } from 'playwright-core';
const rounds = Number(process.argv[2] ?? 3);
const hour = process.argv[3] ?? '13';
const pr = process.argv[4] ?? '1.5';
// VIEWPORT=WxH (CSS px). The target Mac's browser window is ~1728×1000 at DPR 2.
const [vw, vh] = (process.env.VIEWPORT ?? '1728x1000').split('x').map(Number);
const variants = JSON.parse(process.env.VARIANTS);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'] });
const poses = [
  { p: [0, 1.175, 0.16], t: [-0.05, 1.03, -0.95], fov: 54, quick: true },
  { p: [0, 1.175, 0.16], t: [0.9, 1.0, -0.6], fov: 54, quick: true },
  { p: [0, 1.175, 0.16], t: [-1.2, 1.1, -0.7], fov: 54, quick: true },
];
const acc = {};
for (let r = 0; r < rounds; r++) {
  for (const [name, q] of Object.entries(variants)) {
    const page = await browser.newPage({ viewport: { width: vw, height: vh }, deviceScaleFactor: 2 });
    const [origin, query] = q.includes('|') ? q.split('|') : ['http://127.0.0.1:5173', q];
    await page.goto(`${origin}/?debug&hour=${hour}&pr=${pr}&${query}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
    await wait(1500);
    for (const [i, pose] of poses.entries()) {
      const res = await page.evaluate((p) => window.__room.bench(p), pose);
      const key = `${name}|${i}`;
      (acc[key] ??= []).push(res.frame);
    }
    await page.close();
  }
}
await browser.close();
const names = Object.keys(variants);
console.log(`hour ${hour} pr ${pr}, ${rounds} interleaved rounds; look = AO recomputed every frame, idle = cached`);
for (let i = 0; i < poses.length; i++) {
  const cells = names.map((n) => {
    const list = acc[`${n}|${i}`];
    const look = list.reduce((a, f) => a + f.look, 0) / list.length;
    const idle = list.reduce((a, f) => a + f.idle, 0) / list.length;
    return `${n}: look ${look.toFixed(2)} idle ${idle.toFixed(2)}`;
  });
  console.log(`pose ${i}  ` + cells.join('   |   '));
}
