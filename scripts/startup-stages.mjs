// Where startup time goes: loading-stage timestamps averaged over several cold loads.
import { chromium } from 'playwright-core';
const runs = Number(process.argv[2] ?? 5);
const base = process.env.BASE ?? 'http://127.0.0.1:5173';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const all = [];
for (let i = 0; i < runs; i++) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.goto(`${base}/?debug&hour=21`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
  const r = await page.evaluate(() => ({
    marks: window.__room.startupMarks(),
    domInteractive: Math.round(performance.getEntriesByType('navigation')[0].domInteractive),
    resources: performance.getEntriesByType('resource').reduce((a, e) => a + (e.transferSize || e.encodedBodySize || 0), 0),
    scriptKB: Math.round(performance.getEntriesByType('resource').filter((e) => e.initiatorType === 'script' || e.name.endsWith('.js') || e.name.endsWith('.ts')).reduce((a, e) => a + (e.encodedBodySize || 0), 0) / 1024),
  }));
  all.push(r);
  await context.close();
}
await browser.close();
const stages = all[0].marks.map((m) => m.stage);
let prev = 'domInteractive';
console.log(`runs ${runs}; domInteractive avg ${Math.round(all.reduce((a, r) => a + r.domInteractive, 0) / runs)} ms`);
for (let k = 0; k < stages.length; k++) {
  const avgAt = all.reduce((a, r) => a + r.marks[k].at, 0) / runs;
  const avgDur = all.reduce((a, r) => a + (r.marks[k].at - (k ? r.marks[k - 1].at : r.domInteractive)), 0) / runs;
  console.log(`${stages[k].padEnd(28)} done at ${Math.round(avgAt).toString().padStart(5)} ms   took ${Math.round(avgDur).toString().padStart(5)} ms`);
}
