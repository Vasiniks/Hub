// `?v2` window check for the street backdrop: seated + standing screenshots at the Cycles
// reference framing (1280x720, fov 54) with the sidecar's glass IOR and with IOR 1, console errors, and an A/B of frame cost with the
// backdrop vs an empty sidecar (same page, same build: only the four layers differ).
// Usage: ROOM_URL=http://127.0.0.1:<port> node scripts/shoot-exterior.mjs <outDir> [--bench]
import { chromium } from 'playwright-core';
import { base, chrome } from './verify-env.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { CAMERA } from '../src/scene/layout.ts';

const outDir = process.argv[2] ?? 'tmp/exterior/web';
const bench = process.argv.includes('--bench');
fs.mkdirSync(outDir, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: ['--use-angle=d3d11', '--enable-gpu-rasterization', '--ignore-gpu-blocklist'],
});

async function run(label, { empty = false, ior = null, suffix = '' } = {}) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  if (empty || ior !== null) {
    await page.route('**/assets/v2/exterior/exterior.json', async (route) => {
      const res = await route.fetch();
      const json = await res.json();
      if (empty) json.layers = [];
      if (ior !== null) json.glass.ior = ior;
      await route.fulfill({ response: res, json });
    });
  }
  await page.goto(`${base}/?v2&debug&pr=1`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room?.frames?.() > 30, null, { timeout: 60000 });
  const out = { label, errors };
  for (const [name, pose] of [['seat', CAMERA.seat], ['stand', CAMERA.stand]]) {
    await page.evaluate(([p, t]) => window.__room.parkCamera(p, t, 54), [pose.position, pose.lookAt]);
    await wait(600);
    if (!empty) await page.screenshot({ path: path.join(outDir, `web_${name}${suffix}.png`) });
    if (bench) out[name] = await page.evaluate((pose) => window.__room.bench({ p: pose.position, t: pose.lookAt, fov: 54, quick: true }), pose);
  }
  out.programs = await page.evaluate(() => window.__room.programs().filter((n) => n.includes('exterior')));
  await page.close();
  return out;
}

const results = [];
const reps = bench ? 3 : 1;
for (let i = 0; i < reps; i++) {
  results.push(await run('backdrop'));
  if (!bench) results.push(await run('plain glass (ior 1)', { ior: 1, suffix: '_ior1' }));
  if (bench) results.push(await run('empty', { empty: true }));
}
await browser.close();
console.log(JSON.stringify(results, null, 1));
