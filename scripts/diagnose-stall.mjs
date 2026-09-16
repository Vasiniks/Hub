// Pinpoint one-off stalls and periodic spikes: shader programs compiled mid-interaction,
// and the timing pattern of slow frames while the project panel is open.
import { chromium } from 'playwright-core';

const hour = process.argv[2] ?? '13';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--disable-frame-rate-limit'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const room = (fn, arg) => page.evaluate(fn, arg);

await page.goto(`http://127.0.0.1:5173/?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined);
await page.mouse.move(720, 450);
await wait(3000);
const checkpoint = async (label) => {
  const [n, sr] = await room(() => [window.__room.programKeys().length, window.__room.shadowRequests()]);
  console.log(`CHECKPOINT ${label}: programs ${n}, shadow requests ${JSON.stringify(sr)}`);
};
await checkpoint('after load');
await page.mouse.wheel(0, 120);
await wait(4500);
await checkpoint('after sitting');
await page.mouse.move(720, 450);
await wait(1500);
await checkpoint('before sweep');

const diff = (before, after) => {
  const counts = new Map();
  for (const n of before) counts.set(n, (counts.get(n) ?? 0) + 1);
  const added = [];
  for (const n of after) {
    const c = counts.get(n) ?? 0;
    if (c > 0) counts.set(n, c - 1);
    else added.push(n);
  }
  return added;
};

// ---- Look sweep --------------------------------------------------------------
const k0 = await room(() => window.__room.programKeys());
await room(() => window.__room.perf.reset());
const hoveredDuringSweep = new Set();
let firstNewAt = null;
for (let i = 0; i <= 100; i++) {
  const t = i / 100;
  await page.mouse.move(720 + Math.sin(t * Math.PI * 2) * 680, 450 + Math.sin(t * Math.PI * 4) * 180);
  await wait(30);
  if (i % 5 === 0) {
    const [h, n] = await room(() => [window.__room.hovered(), window.__room.programKeys().length]);
    if (h) hoveredDuringSweep.add(h);
    if (firstNewAt === null && n > k0.length) {
      firstNewAt = { step: i, hovered: h, cursor: [Math.round(720 + Math.sin(t * Math.PI * 2) * 680), Math.round(450 + Math.sin(t * Math.PI * 4) * 180)], shadowRequests: await room(() => window.__room.shadowRequests()) };
    }
  }
}
const sweep = await room(() => window.__room.perf.snapshot());
const k1 = await room(() => window.__room.programKeys());
console.log(`LOOK SWEEP: programs ${k0.length} -> ${k1.length}; frame max ${sweep.frameMs.max}ms; hovered during sweep: ${JSON.stringify([...hoveredDuringSweep])}`);
console.log(`  first new program detected at: ${JSON.stringify(firstNewAt)}`);
for (const k of diff(k0, k1)) {
  // Compare against the most similar existing program: which key fields differ?
  const fields = k.split(',');
  let best = null;
  let bestDiff = Infinity;
  for (const e of k0) {
    const ef = e.split(',');
    if (ef.length !== fields.length) continue;
    const d = fields.filter((f, i) => f !== ef[i]).length;
    if (d < bestDiff) { bestDiff = d; best = ef; }
  }
  const changes = best ? fields.map((f, i) => (f !== best[i] ? `#${i}: ${best[i]} -> ${f}` : null)).filter(Boolean) : ['no same-length key'];
  console.log(`   NEW (${fields[0]}) differs from closest existing in ${bestDiff} field(s): ${changes.join(' | ')}`);
}

// ---- Outline alone, before any hover ------------------------------------------------------------
{
  const before = await room(() => window.__room.programKeys().length);
  await room(() => window.__room.perf.reset());
  await room(() => window.__room.outlineOnly('frc-robot'));
  await wait(800);
  const after = await room(() => window.__room.programKeys().length);
  const snap = await room(() => window.__room.perf.snapshot());
  await room(() => window.__room.outlineOnly(null));
  await wait(400);
  console.log(`OUTLINE ONLY (frc-robot): programs ${before} -> ${after}, frame max ${snap.frameMs?.max}`);
}

// ---- Isolate the trigger: single-object hover (Tab) vs focus flight + panel (Enter) ---------------
await page.mouse.move(720, 450);
await wait(1500);
const keys0 = await room(() => window.__room.programKeys());
await room(() => window.__room.perf.reset());
await page.keyboard.press('Tab');
await wait(600);
const keys1 = await room(() => window.__room.programKeys());
const tabSnap = await room(() => window.__room.perf.snapshot());
console.log(`\nTAB (hover ${await room(() => window.__room.hovered())}): programs ${keys0.length} -> ${keys1.length}, frame max ${tabSnap.frameMs?.max}`);
for (const k of diff(keys0, keys1)) console.log(`   NEW ${k.slice(0, 420)}`);
await room(() => window.__room.perf.reset());
await page.keyboard.press('Enter');
await wait(2200);
const keys2 = await room(() => window.__room.programKeys());
const enterSnap = await room(() => window.__room.perf.snapshot());
console.log(`ENTER (${await room(() => window.__room.mode())}): programs ${keys1.length} -> ${keys2.length}, frame max ${enterSnap.frameMs?.max}`);
for (const k of diff(keys1, keys2)) console.log(`   NEW ${k.slice(0, 420)}`);

console.log(`\nerrors: ${JSON.stringify(errors)}`);
await browser.close();
