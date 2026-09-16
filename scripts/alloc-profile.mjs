// Allocation sampling during steady interaction: which functions allocate per frame.
import { chromium } from 'playwright-core';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-precise-memory-info'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`http://127.0.0.1:5173/?debug&pr=1&hour=${process.argv[2] ?? 21}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.mouse.move(720, 450);
await wait(1500);
await page.mouse.wheel(0, 120);
await wait(4500);
const cdp = await page.context().newCDPSession(page);
await cdp.send('HeapProfiler.enable');
await cdp.send('HeapProfiler.collectGarbage');
await cdp.send('HeapProfiler.startSampling', { samplingInterval: 256, includeObjectsCollectedByMajorGC: true, includeObjectsCollectedByMinorGC: true });
const frames0 = await page.evaluate(() => window.__room.frames());
const t0 = Date.now();
// Seated look sweep, then hover the dev board.
for (let i = 0; i < 120; i++) {
  await page.mouse.move(720 + Math.sin(i / 12) * 650, 450 + Math.sin(i / 7) * 150);
  await wait(25);
}
for (let i = 0; i < 60; i++) {
  const s = await page.evaluate(() => window.__room.hitPositionOf('dev-board'));
  if (s) await page.mouse.move(s.x + Math.sin(i) * 5, s.y);
  await wait(25);
}
await wait(1500);
const { profile } = await cdp.send('HeapProfiler.stopSampling');
const seconds = (Date.now() - t0) / 1000;
const frames = (await page.evaluate(() => window.__room.frames())) - frames0;
const self = new Map();
const walk = (node) => {
  const f = node.callFrame;
  const file = (f.url || '').split('/').pop().split('?')[0];
  const key = `${f.functionName || '(anon)'} ${file}:${f.lineNumber + 1}`;
  const bytes = node.selfSize;
  if (bytes) self.set(key, (self.get(key) ?? 0) + bytes);
  node.children.forEach(walk);
};
walk(profile.head);
const total = [...self.values()].reduce((a, b) => a + b, 0);
console.log(`sampled allocations: ${(total / 1024).toFixed(0)} KB over ${seconds.toFixed(1)} s, ${frames} frames → ${(total / frames).toFixed(0)} bytes/frame`);
for (const [k, v] of [...self].sort((a, b) => b[1] - a[1]).slice(0, 18)) console.log(`${(v / 1024).toFixed(1).padStart(8)} KB  ${k}`);
await browser.close();
