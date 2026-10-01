// Browser verification for the baked v2 room (`/?v2`): stand, look, sit, look, and the
// hover → click → focus → panel → back flow through the prop registry, by mouse and by keyboard.
// Usage: node scripts/verify-v2.mjs <outDir> [propId]
import { chromium } from 'playwright-core';
import { base, chrome } from './verify-env.mjs';
import fs from 'node:fs';
import path from 'node:path';

const outDir = process.argv[2] ?? 'verify-v2-out';
const propId = process.argv[3] ?? 'bookshelf';
fs.mkdirSync(outDir, { recursive: true });

const report = { steps: [], errors: [], failures: [] };
const log = (name, data = {}) => { report.steps.push({ name, ...data }); console.log(name, JSON.stringify(data)); };
const expect = (name, ok, data) => { if (!ok) report.failures.push({ name, ...data }); };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let cursor = { x: 720, y: 450 };

const browser = await chromium.launch({
  executablePath: chrome,
  headless: true,
  args: ['--use-angle=metal', '--enable-gpu-rasterization', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', (m) => { if (m.type() === 'error') report.errors.push(m.text()); });
page.on('pageerror', (e) => report.errors.push(`pageerror: ${e.message}`));
const room = (expr, arg) => page.evaluate(expr, arg);
const shot = (name) => page.screenshot({ path: path.join(outDir, `${name}.png`), timeout: 15000 }).catch(() => {});
const mode = () => room(() => window.__room.mode());
const yawPitch = async () => {
  const q = (await room(() => window.__room.camera())).quaternion;
  const [x, y, z, w] = q;
  // YXZ Euler from the quaternion: yaw about y, pitch about x.
  const yaw = Math.atan2(2 * (w * y + x * z), 1 - 2 * (x * x + y * y));
  const pitch = Math.asin(Math.max(-1, Math.min(1, 2 * (w * x - y * z))));
  return { yaw: +yaw.toFixed(3), pitch: +pitch.toFixed(3) };
};
const fps = () => room(() => new Promise((res) => { let n = 0; const t0 = performance.now(); const f = () => { n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else res(n / 2); }; requestAnimationFrame(f); }));

async function load() {
  await page.goto(`${base}/?v2&debug`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined && window.__room.frames() > 5, null, { timeout: 60000 });
  await page.mouse.move(720, 450);
  cursor = { x: 720, y: 450 };
  await wait(2500);
}

async function hover(id) {
  for (let i = 0; i < 80; i++) {
    if ((await room(() => window.__room.hovered())) === id) {
      await wait(600);
      if ((await room(() => window.__room.hovered())) === id) return true;
      continue;
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

// ---- Movement and look ------------------------------------------------------------------------
await load();
const renderer = await room(() => {
  const gl = document.getElementById('scene').getContext('webgl2');
  const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown';
});
log('renderer', { renderer });
log('props', await room(() => window.__room.props()));
const restStand = await yawPitch();
log('01-standing', { mode: await mode(), ...restStand, fps: await fps() });
expect('standing', (await mode()) === 'standing', {});
await shot('01-standing');

await page.mouse.move(20, 450, { steps: 10 });
await wait(2200);
const standLeft = await yawPitch();
log('02-standing-look-left', { ...standLeft, dYaw: +(standLeft.yaw - restStand.yaw).toFixed(3) });
expect('standing look turns left within limit', standLeft.yaw - restStand.yaw > 0.2 && standLeft.yaw - restStand.yaw < 0.4, standLeft);
await shot('02-standing-look-left');
await page.mouse.move(720, 450, { steps: 10 });
await wait(2000);

await page.mouse.wheel(0, 120);
await wait(1300);
log('03-sitting-mid', { mode: await mode() });
expect('sitting', (await mode()) === 'sitting', {});
await shot('03-sitting-mid');
await wait(2600);
const restSeat = await yawPitch();
log('04-seated', { mode: await mode(), ...restSeat, camera: await room(() => window.__room.camera()) });
expect('seated', (await mode()) === 'seated', {});
await shot('04-seated');

for (const [name, x, y] of [['05-seated-look-left', 20, 450], ['06-seated-look-right', 1420, 450], ['07-seated-look-up', 720, 20], ['08-seated-look-down', 720, 880]]) {
  await page.mouse.move(x, y, { steps: 12 });
  await wait(2200);
  const yp = await yawPitch();
  log(name, { ...yp, dYaw: +(yp.yaw - restSeat.yaw).toFixed(3), dPitch: +(yp.pitch - restSeat.pitch).toFixed(3) });
  await shot(name);
}

// ---- Hover → click → focus → panel → Esc ------------------------------------------------------
await page.mouse.move(720, 450, { steps: 10 });
cursor = { x: 720, y: 450 };
await wait(1500);
// The shelf is on the left wall: turn toward it the way a visitor would.
const hovered = await hover(propId);
const label = await room(() => {
  const l = document.getElementById('hover-label');
  return { text: l.textContent, visible: l.classList.contains('is-visible'), transform: l.style.transform };
});
log('09-hover', { id: propId, hovered, label, cursorClass: await room(() => document.body.classList.contains('is-hovering')) });
expect('hover', hovered && label.visible && label.text.length > 0, { label });
await shot('09-hover');
if (hovered) {
  await page.mouse.down();
  await page.mouse.up();
  await wait(1900);
  const focused = { mode: await mode(), focused: await room(() => window.__room.focused()), panelOpen: await room(() => window.__room.panelOpen()), title: await room(() => document.getElementById('panel-title').textContent) };
  log('10-focused', focused);
  expect('focused + panel', focused.mode === 'focused' && focused.panelOpen && focused.focused === propId, focused);
  await shot('10-focused');
  await page.keyboard.press('Escape');
  await wait(1700);
  const back = { mode: await mode(), panelOpen: await room(() => window.__room.panelOpen()) };
  log('11-returned-escape', back);
  expect('escape returns', back.mode === 'seated' && !back.panelOpen, back);
  await shot('11-returned-escape');

  // Again, closing by clicking outside the panel.
  await hover(propId);
  await page.mouse.down();
  await page.mouse.up();
  await wait(1900);
  await page.mouse.move(160, 200, { steps: 4 });
  await page.mouse.down();
  await page.mouse.up();
  await wait(1700);
  const back2 = { mode: await mode(), panelOpen: await room(() => window.__room.panelOpen()) };
  log('12-returned-click-outside', back2);
  expect('click outside returns', back2.mode === 'seated' && !back2.panelOpen, back2);
}

// ---- Keyboard: Tab to the object nav, Enter opens, Esc returns ---------------------------------
await page.mouse.move(720, 450, { steps: 6 });
await wait(800);
await page.keyboard.press('Tab');
await wait(400);
const navFocus = await room(() => ({ text: document.activeElement?.textContent, hovered: window.__room.hovered() }));
await page.keyboard.press('Enter');
await wait(1900);
const kb = { navFocus, mode: await mode(), panelOpen: await room(() => window.__room.panelOpen()) };
log('13-keyboard-open', kb);
expect('keyboard opens', kb.mode === 'focused' && kb.panelOpen, kb);
await shot('13-keyboard-open');
await page.keyboard.press('Escape');
await wait(1700);
log('14-keyboard-escape', { mode: await mode() });

// ---- From standing: a click on an object sits down, then opens it ------------------------------
await load();
const standHover = await hover(propId);
if (standHover) {
  await page.mouse.down();
  await page.mouse.up();
  await wait(5200);
  const st = { mode: await mode(), panelOpen: await room(() => window.__room.panelOpen()) };
  log('15-standing-click', { hovered: standHover, ...st });
  expect('standing click sits then opens', st.mode === 'focused' && st.panelOpen, st);
} else {
  log('15-standing-click', { hovered: false, note: 'not reachable from the standing pose' });
}
log('fps-end', { fps: await fps() });

fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2));
console.log('FAILURES', JSON.stringify(report.failures));
console.log('ERRORS', JSON.stringify(report.errors));
await browser.close();
process.exitCode = report.failures.length || report.errors.length ? 1 : 0;
