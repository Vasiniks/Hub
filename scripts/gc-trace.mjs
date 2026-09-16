// Real garbage-collection pauses during interaction, from a Chrome trace.
import { chromium } from 'playwright-core';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`${base}/?debug&pr=1&hour=21`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
await page.mouse.move(720, 450);
await wait(1500);
await page.mouse.wheel(0, 120);
await wait(4500);
await browser.startTracing(page, { categories: ['v8', 'disabled-by-default-v8.gc', 'devtools.timeline'] });
const t0 = Date.now();
for (let i = 0; i < 200; i++) {
  await page.mouse.move(720 + Math.sin(i / 12) * 650, 450 + Math.sin(i / 7) * 150);
  await wait(25);
}
await wait(2000);
const seconds = (Date.now() - t0) / 1000;
const trace = JSON.parse((await browser.stopTracing()).toString());
const events = (trace.traceEvents ?? trace).filter((e) => ['MinorGC', 'MajorGC', 'V8.GCScavenger', 'V8.GCFinalizeMC'].includes(e.name) && e.dur);
const byName = {};
for (const e of events) {
  const b = (byName[e.name] ??= { count: 0, totalMs: 0, maxMs: 0 });
  b.count++;
  b.totalMs += e.dur / 1000;
  b.maxMs = Math.max(b.maxMs, e.dur / 1000);
}
for (const b of Object.values(byName)) {
  b.totalMs = +b.totalMs.toFixed(1);
  b.maxMs = +b.maxMs.toFixed(2);
}
console.log(`GC over ${seconds.toFixed(1)} s of look sweep:`, JSON.stringify(byName));
await browser.close();
