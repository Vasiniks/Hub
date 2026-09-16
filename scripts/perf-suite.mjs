// Performance suite: every interaction scenario, at night / day / golden hour, uncapped.
//
// Chrome runs without vsync or a frame-rate limit at retina scale, with the render resolution
// pinned (?pr=1.5, which also disables adaptive resolution), so frame time is the real cost of
// a frame and a faster build shows up as a smaller number instead of being spent on pixels.
// A V8 CPU profile over the whole run gives per-function JS cost.
//
// Usage: node scripts/perf-suite.mjs <label> [hours=21,13,18.5] [extra query, e.g. "ao=off"]
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const label = process.argv[2] ?? 'run';
const hours = (process.argv[3] ?? '21,13,18.5').split(',');
const extra = process.argv[4] ? `&${process.argv[4]}` : '';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// QUICK=1: only the steady-state scenarios, for fast A/B of a single change.
const quick = process.env.QUICK === '1';
fs.mkdirSync('perf', { recursive: true });

const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit', '--enable-precise-memory-info'],
});

const summary = { label, extra, hours: {} };

for (const hour of hours) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  const room = (fn, arg) => page.evaluate(fn, arg);

  const t0 = Date.now();
  await page.goto(`${process.env.BASE ?? 'http://127.0.0.1:5173'}/?debug&hour=${hour}&pr=${process.env.PR ?? 1.5}${extra}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 60000 });
  const ready = Date.now() - t0;

  const cdp = await context.newCDPSession(page);
  await cdp.send('Profiler.enable');
  await cdp.send('Profiler.setSamplingInterval', { interval: 200 });
  await cdp.send('Profiler.start');

  await page.mouse.move(720, 450);
  await wait(2500);
  const out = {};
  async function measure(name, action) {
    await room(() => window.__room.perf.reset());
    await action();
    const s = await room(() => window.__room.perf.snapshot());
    out[name] = {
      fps: s.fps,
      frame: s.frameMs,
      cpu: s.cpuMs,
      stages: Object.fromEntries(Object.entries(s.stages).map(([k, v]) => [k, v && { avg: v.avg, p95: v.p95, max: v.max }])),
      calls: s.drawCalls && s.drawCalls.p50,
      tris: s.triangles,
      heapMB: s.heapMB,
      gpu: s.gpu,
    };
  }
  const sweep = async (ms, ampX = 680, ampY = 180) => {
    const start = Date.now();
    while (Date.now() - start < ms) {
      const t = (Date.now() - start) / ms;
      await page.mouse.move(720 + Math.sin(t * Math.PI * 2) * ampX, 450 + Math.sin(t * Math.PI * 4) * ampY);
      await wait(16);
    }
  };

  await measure('standing-idle', () => wait(3000));
  if (!quick) await measure('standing-look', () => sweep(3000, 500, 150));
  await page.mouse.move(720, 450);
  await wait(800);
  if (quick) {
    await page.mouse.wheel(0, 120);
    await wait(3200);
  } else
    await measure('sitting', async () => {
      await page.mouse.wheel(0, 120);
      await wait(3200);
    });
  await wait(1500);
  await measure('seated-idle', () => wait(3000));
  await measure('seated-look', () => sweep(3500));
  await page.mouse.move(720, 450);
  await wait(1800);
  let hoverOk = false;
  await measure('hover', async () => {
    const start = Date.now();
    while (Date.now() - start < 3000) {
      const s = await room((pid) => window.__room.hitPositionOf(pid), 'dev-board');
      if (s) await page.mouse.move(s.x + Math.sin(Date.now() / 90) * 8, s.y + Math.cos(Date.now() / 110) * 4);
      await wait(16);
    }
    hoverOk = (await room(() => window.__room.hovered())) === 'dev-board';
  });
  if (hoverOk && !quick) {
    await measure('focus-transition', async () => {
      await page.mouse.down();
      await page.mouse.up();
      await wait(1600);
    });
    await measure('popup-open', () => wait(3000));
    await page.keyboard.press('Escape');
    await wait(1600);
  }
  if (!quick) await measure('time-transition', async () => {
    for (let i = 0; i < 16; i++) {
      await room((h) => window.__room.setHour(h), Number(hour) + i * 0.25);
      await wait(190);
    }
  });

  const { profile } = await cdp.send('Profiler.stop');
  // Self time per function, from sample counts.
  const byId = new Map(profile.nodes.map((n) => [n.id, n]));
  const counts = new Map();
  for (const id of profile.samples) counts.set(id, (counts.get(id) ?? 0) + 1);
  const total = profile.samples.length;
  const self = new Map();
  for (const [id, c] of counts) {
    const n = byId.get(id);
    const f = n.callFrame;
    const file = (f.url || '').split('/').pop().split('?')[0];
    const key = `${f.functionName || '(anon)'} ${file}:${f.lineNumber + 1}`;
    self.set(key, (self.get(key) ?? 0) + c);
  }
  const top = [...self].sort((a, b) => b[1] - a[1]).slice(0, 30).map(([k, c]) => [k, +((100 * c) / total).toFixed(2)]);
  const wallMs = (profile.endTime - profile.startTime) / 1000;

  summary.hours[hour] = { ready, scenarios: out, errors, hoverOk, profileTop: top, profileWallMs: Math.round(wallMs) };
  await context.close();
}
await browser.close();

const file = `perf/${label}.json`;
fs.writeFileSync(file, JSON.stringify(summary, null, 2));

// Concise table: fps, frame p50/p95/max, CPU avg/p95, draw calls.
for (const [hour, h] of Object.entries(summary.hours)) {
  console.log(`\n=== ${label} hour=${hour}  errors=${h.errors.length} hover=${h.hoverOk}`);
  console.log('scenario            fps    frame p50/p95/max      cpu avg/p95/max    calls  tris');
  for (const [name, s] of Object.entries(h.scenarios)) {
    const f = s.frame ?? {};
    const c = s.cpu ?? {};
    console.log(
      `${name.padEnd(18)} ${String(s.fps).padStart(5)}  ${`${f.p50}/${f.p95}/${f.max}`.padEnd(20)} ${`${c.avg}/${c.p95}/${c.max}`.padEnd(18)} ${String(s.calls).padStart(5)}  ${s.tris}`,
    );
  }
  for (const [name, s] of Object.entries(h.scenarios)) {
    if (!s.gpu) continue;
    const parts = Object.entries(s.gpu.stages)
      .sort((a, b) => b[1].perFrameAvg - a[1].perFrameAvg)
      .map(([k, v]) => `${k.replace('Pass', '')} ${v.perFrameAvg}${v.calls < 50 ? `(x${v.calls})` : ''}`);
    console.log(`  gpu ${name.padEnd(16)} total ${s.gpu.totalAvg}: ${parts.join(' | ')}`);
  }
  console.log('top JS self time (% of samples):');
  for (const [k, p] of h.profileTop.slice(0, 14)) console.log(`  ${String(p).padStart(6)}  ${k}`);
}
