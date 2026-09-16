// Browser verification for the room prototype.
// Usage: node scripts/verify-room.mjs <outDir> [hour]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const outDir = process.argv[2] ?? 'verify-out';
const hour = process.argv[3] ?? '21';
const base = process.env.ROOM_URL ?? 'http://127.0.0.1:5173/';
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
fs.mkdirSync(outDir, { recursive: true });

const report = { hour, steps: [], errors: [], warnings: [] };
const log = (name, data = {}) => { report.steps.push({ name, ...data }); console.log(name, JSON.stringify(data)); };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let cursor = { x: 720, y: 450 };

const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: ['--use-angle=metal', '--enable-gpu-rasterization', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', (m) => {
  if (m.type() === 'error') report.errors.push(m.text());
  if (m.type() === 'warning') report.warnings.push(m.text());
});
page.on('pageerror', (e) => report.errors.push(`pageerror: ${e.message}`));

const room = (expr, arg) => page.evaluate(expr, arg);
// Screenshots wait for web fonts; retry rather than fail the whole run on a slow font fetch.
const shot = async (name) => {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await page.screenshot({ path: path.join(outDir, `${name}.png`), timeout: 15000 });
    } catch (e) {
      if (attempt === 2) report.warnings.push(`screenshot ${name} failed: ${e.message.split('\n')[0]}`);
    }
  }
};

await page.goto(`${base}?debug&hour=${hour}`, { waitUntil: 'load' });
await page.waitForFunction(() => window.__room !== undefined, null, { timeout: 15000 });
await page.mouse.move(720, 450);
await wait(3500);

const renderer = await room(() => {
  const gl = document.getElementById('scene').getContext('webgl2');
  const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown';
});
log('renderer', { renderer });
log('standing', { mode: await room(() => window.__room.mode()), camera: await room(() => window.__room.camera()) });
await shot('01-standing');

// Frame rate over two seconds
const fps = await room(() => new Promise((res) => { let n = 0; const t0 = performance.now(); const f = () => { n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else res(n / 2); }; requestAnimationFrame(f); }));
log('fps-standing', { fps });

// Scroll once to sit
await page.mouse.wheel(0, 120);
await wait(1300);
log('sitting-mid', { mode: await room(() => window.__room.mode()), chair: await room(() => window.__room.chair()) });
await shot('02-sitting-mid');
await wait(2600);
log('seated', { mode: await room(() => window.__room.mode()), camera: await room(() => window.__room.camera()), chair: await room(() => window.__room.chair()) });
await shot('03-seated');

// Mouse look
for (const [name, x, y] of [['04-look-left', 40, 470], ['05-look-right', 1400, 470], ['06-look-down', 720, 880]]) {
  await page.mouse.move(x, y, { steps: 12 });
  await wait(1600);
  log(name, { camera: await room(() => window.__room.camera()) });
  await shot(name);
}
await page.mouse.move(720, 450, { steps: 10 });
cursor = { x: 720, y: 450 };
await wait(1500);

// Track the object like a person would: step toward where it currently is on screen until hovered,
// then confirm the hover holds while the cursor rests.
async function hoverProject(id) {
  for (let i = 0; i < 70; i++) {
    if ((await room(() => window.__room.hovered())) === id) {
      await wait(700);
      if ((await room(() => window.__room.hovered())) === id) return true;
      continue; // Lost it: re-aim, as a person would.
    }
    const s = (await room((pid) => window.__room.hitPositionOf(pid), id)) ?? (await room((pid) => window.__room.screenPositionOf(pid), id));
    if (!s) return false;
    const tx = Math.max(10, Math.min(1430, s.x));
    const ty = Math.max(10, Math.min(890, s.y));
    cursor = { x: cursor.x + (tx - cursor.x) * 0.35, y: cursor.y + (ty - cursor.y) * 0.35 };
    await page.mouse.move(cursor.x, cursor.y);
    await wait(90);
  }
  return false;
}

async function examine(id, prefix, closeWith) {
  const hovered = await hoverProject(id);
  log(`${prefix}-hover`, { id, hovered, cursorClass: await room(() => document.body.classList.contains('is-hovering')) });
  await shot(`${prefix}-a-hover`);
  if (!hovered) return;
  await page.mouse.down();
  await page.mouse.up();
  await wait(1900);
  log(`${prefix}-focused`, {
    mode: await room(() => window.__room.mode()),
    panelOpen: await room(() => window.__room.panelOpen()),
    title: await room(() => document.getElementById('panel-title').textContent),
    objectOnScreen: await room((pid) => window.__room.screenPositionOf(pid), id),
  });
  await shot(`${prefix}-b-focused`);
  if (closeWith === 'escape') await page.keyboard.press('Escape');
  else { cursor = { x: 160, y: 200 }; await page.mouse.move(160, 200, { steps: 4 }); await page.mouse.down(); await page.mouse.up(); }
  await wait(1700);
  log(`${prefix}-returned`, { via: closeWith, mode: await room(() => window.__room.mode()), panelOpen: await room(() => window.__room.panelOpen()) });
  await shot(`${prefix}-c-returned`);
}

await examine('frc-robot', '07-frc', 'escape');
await examine('dev-board', '08-devboard', 'click-outside');
await page.mouse.move(720, 450, { steps: 8 });
cursor = { x: 720, y: 450 };
await wait(1200);
await examine('notebooks', '09-notebooks', 'escape');

const fps2 = await room(() => new Promise((res) => { let n = 0; const t0 = performance.now(); const f = () => { n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else res(n / 2); }; requestAnimationFrame(f); }));
log('fps-seated', { fps: fps2 });

fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2));
console.log('ERRORS', JSON.stringify(report.errors));
await browser.close();
