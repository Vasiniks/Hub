// v2-look: render `/?v2` from the two Blender cameras of the bake (CAM_stand, CAM_seat) at the
// reference renders' size (960x540, pixel ratio 1), for side-by-side and numeric comparison.
//
//   ROOM_URL=http://127.0.0.1:5192 node scripts/v2look/capture.mjs <out_dir> <label> "<extra query>" [--linear] [--headed]
//
// Writes <out_dir>/<label>_<cam>.png (the canvas as displayed) and, with --linear,
// <out_dir>/<label>_<cam>.lin.f32 (scene-linear RGB float32, rows top-first, 2x2 supersampled).
// Camera poses come from <out_dir>/../probe.json (scripts/v2look/blender_probe.py), converted from
// Blender Z-up to glTF/three Y-up: (x, y, z) -> (x, z, -y).
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';

const [outDir, label, extra = '', ...flags] = process.argv.slice(2);
const linear = flags.includes('--linear');
const headed = flags.includes('--headed');
const base = (process.env.ROOM_URL ?? 'http://127.0.0.1:5192').replace(/\/+$/, '');
const probe = JSON.parse(fs.readFileSync(process.env.PROBE ?? path.join(outDir, '..', 'probe.json'), 'utf8'));
const chromePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
fs.mkdirSync(outDir, { recursive: true });

function quatFromMatrix(m) {
  // m: 3x3 rows
  const [[m11, m12, m13], [m21, m22, m23], [m31, m32, m33]] = m;
  const tr = m11 + m22 + m33;
  let x, y, z, w;
  if (tr > 0) {
    const s = 0.5 / Math.sqrt(tr + 1);
    w = 0.25 / s; x = (m32 - m23) * s; y = (m13 - m31) * s; z = (m21 - m12) * s;
  } else if (m11 > m22 && m11 > m33) {
    const s = 2 * Math.sqrt(1 + m11 - m22 - m33);
    w = (m32 - m23) / s; x = 0.25 * s; y = (m12 + m21) / s; z = (m13 + m31) / s;
  } else if (m22 > m33) {
    const s = 2 * Math.sqrt(1 + m22 - m11 - m33);
    w = (m13 - m31) / s; x = (m12 + m21) / s; y = 0.25 * s; z = (m23 + m32) / s;
  } else {
    const s = 2 * Math.sqrt(1 + m33 - m11 - m22);
    w = (m21 - m12) / s; x = (m13 + m31) / s; y = (m23 + m32) / s; z = 0.25 * s;
  }
  return [x, y, z, w];
}

function pose(cam) {
  const M = cam.matrix_world;
  const C = [[1, 0, 0], [0, 0, 1], [0, -1, 0]];
  const R = C.map((row) => [0, 1, 2].map((j) => row.reduce((acc, c, k) => acc + c * M[k][j], 0)));
  const t = [M[0][3], M[1][3], M[2][3]];
  const p = C.map((row) => row.reduce((acc, c, k) => acc + c * t[k], 0));
  // sensor fit VERTICAL (checked in probe.json): vertical fov from the sensor height
  const fov = (2 * Math.atan(cam.sensor_height / 2 / cam.lens) * 180) / Math.PI;
  return { p, q: quatFromMatrix(R), fov };
}

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: !headed,
  args: ['--ignore-gpu-blocklist', '--enable-gpu', '--use-angle=d3d11', '--force-device-scale-factor=1'],
});
const page = await browser.newPage({ viewport: { width: 960, height: 540 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const url = `${base}/?v2&debug&pr=1&adaptive=0${extra ? '&' + extra : ''}`;
await page.goto(url, { waitUntil: 'load' });
await page.waitForFunction(() => window.__v2look !== undefined && window.__room !== undefined, null, { timeout: 120000 });
await page.waitForTimeout(1500);
const gpu = await page.evaluate(() => {
  const gl = document.querySelector('canvas').getContext('webgl2');
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown';
});
const out = { url, gpu, state: await page.evaluate(() => window.__v2look.state()), shots: {} };
for (const cam of ['CAM_stand', 'CAM_seat']) {
  const { p, q, fov } = pose(probe.cameras[cam]);
  await page.evaluate(([p, q, fov]) => window.__v2look.setPose(p, q, fov), [p, q, fov]);
  await page.waitForTimeout(600);
  const file = path.join(outDir, `${label}_${cam}.png`);
  await page.locator('canvas').first().screenshot({ path: file });
  out.shots[cam] = { file, pose: { p, q, fov } };
  if (linear) {
    const { w, h, data } = await page.evaluate(() => window.__v2look.readLinear(2));
    fs.writeFileSync(path.join(outDir, `${label}_${cam}.lin.f32`), Buffer.from(data, 'base64'));
    out.shots[cam].linear = [w, h];
  }
}
out.errors = errors;
fs.writeFileSync(path.join(outDir, `${label}.json`), JSON.stringify(out, null, 1));
console.log(JSON.stringify({ label, gpu, state: out.state, errors }, null, 1));
await browser.close();
