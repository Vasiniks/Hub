// Startup trace: every frame's duration from page load, plus pixel-ratio changes.
// Usage: node scripts/startup-trace.mjs [hour] [label]
import { chromium } from 'playwright-core';
const hour = process.argv[2] ?? '21';
const label = process.argv[3] ?? 'baseline';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
page.on('pageerror', (e) => console.log('ERROR', e.message));
await page.addInitScript(() => {
  window.__trace = { t0: performance.now(), frames: [], marks: [] };
  const raf = window.requestAnimationFrame.bind(window);
  let prev = performance.now();
  const tick = (t) => { window.__trace.frames.push([+(t - window.__trace.t0).toFixed(1), +(t - prev).toFixed(2)]); prev = t; raf(tick); };
  raf(tick);
});
await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'commit' });
await wait(16000);
const trace = await page.evaluate(() => ({
  frames: window.__trace.frames,
  pr: window.__room ? window.devicePixelRatio : null,
  rendererPr: window.__room ? window.__room.pixelRatio?.() ?? null : null,
}));
const f = trace.frames;
const firstVisible = f.findIndex((x, i) => i > 2 && x[1] < 300);
console.log(`\n== ${label} hour=${hour} ==`);
console.log('total frames in 16s:', f.length);
const gaps = f.filter((x) => x[1] > 60).slice(0, 14);
console.log('gaps >60ms:', JSON.stringify(gaps));
for (const [from, to] of [[0,2],[2,4],[4,6],[6,8],[8,10],[10,12],[12,16]]) {
  const win = f.filter((x) => x[0] >= from * 1000 && x[0] < to * 1000).map((x) => x[1]).sort((a, b) => a - b);
  if (!win.length) { console.log(`${from}-${to}s: (no frames)`); continue; }
  const med = win[win.length >> 1];
  const p95 = win[Math.floor(win.length * 0.95)];
  console.log(`${from}-${to}s: n=${String(win.length).padStart(3)} median=${med.toFixed(1)}ms (${(1000/med).toFixed(0)}fps) p95=${p95.toFixed(1)}ms max=${win[win.length-1].toFixed(1)}ms`);
}
await browser.close();
