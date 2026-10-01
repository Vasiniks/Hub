// Pipeline step for the `?v2` street backdrop: blender/scripts/v2_exterior_web.py writes the
// log-encoded layer PNGs + tmp/exterior/layers.json; this compresses them for the web and writes
// public/assets/v2/exterior/{far,mid,near}.webp + exterior.json (the runtime sidecar).
//
//   node scripts/encode-exterior.mjs            encode with the chosen settings
//   node scripts/encode-exterior.mjs --measure  compare candidate encodings (bytes + error)
//
// Error is measured where it matters: decoded to linear radiance, through the room's grade
// (exposure 2^0.45 and an AgX-like log curve), as 8-bit display codes, over covered texels.
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const SRC = 'tmp/exterior';
const DST = 'public/assets/v2/exterior';
const LOG = { min: -12, max: 6 }; // must match LOG_MIN/LOG_MAX in v2_exterior_web.py
const EXPOSURE = 2 ** 0.45;

// Chosen per layer after --measure (see .claude/briefs/report-web-exterior.md).
const CHOSEN = {
  // smooth sky/ground: lossy is ~1 display code off, 8x smaller than lossless
  far: { format: 'webp', opts: { quality: 95, alphaQuality: 100, smartSubsample: true, effort: 6 } },
  mid: { format: 'webp', opts: { quality: 95, alphaQuality: 100, smartSubsample: true, effort: 6 } },
  // wires/foliage: near-lossless costs the same bytes as q95 here at half the error
  street: { format: 'webp', opts: { nearLossless: true, quality: 60, effort: 6 } },
  near: { format: 'webp', opts: { nearLossless: true, quality: 60, effort: 6 } },
};

const meta = JSON.parse(fs.readFileSync(path.join(SRC, 'layers.json'), 'utf8'));

// Blender coordinates (Z-up) -> three (Y-up): (x, y, z) -> (x, z, -y)
const toThree = ([x, y, z]) => [x, z, -y];

/** Display code (0..255) of a log-encoded 8-bit value, through exposure + a log2 tone curve. */
function displayCode(v) {
  if (v < 0.5) return 0;
  const L = 2 ** (LOG.min + (v / 255) * (LOG.max - LOG.min)) * EXPOSURE;
  // AgX spans ~16.5 stops (-12.47 .. +4.03 around 0.18); approximate with that log window.
  const t = (Math.log2(Math.max(L, 1e-10) / 0.18) + 12.47) / 16.5;
  return Math.max(0, Math.min(1, t)) * 255;
}

async function raw(input) {
  const { data, info } = await sharp(input).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return { data, info };
}

async function encode(file, format, opts) {
  const img = sharp(file);
  if (format === 'webp') return img.webp(opts).toBuffer();
  if (format === 'avif') return img.avif(opts).toBuffer();
  return img.png({ compressionLevel: 9, effort: 10, palette: false }).toBuffer();
}

async function errorOf(srcRaw, buf) {
  const dec = await raw(buf);
  const a = srcRaw.data;
  const b = dec.data;
  let n = 0;
  let sum = 0;
  let max = 0;
  const hist = new Float64Array(4);
  for (let i = 0; i < a.length; i += 4) {
    if (a[i + 3] < 128) continue;
    for (let c = 0; c < 3; c++) {
      const e = Math.abs(displayCode(a[i + c]) - displayCode(b[i + c]));
      sum += e;
      max = Math.max(max, e);
      hist[e < 1 ? 0 : e < 2 ? 1 : e < 4 ? 2 : 3]++;
      n++;
    }
  }
  return { meanCodes: +(sum / n).toFixed(3), maxCodes: +max.toFixed(1), over4: +(hist[3] / n).toFixed(5) };
}

if (process.argv.includes('--measure')) {
  const cands = [
    ['png', {}],
    ['webp', { lossless: true, effort: 6 }],
    ['webp', { nearLossless: true, quality: 60, effort: 6 }],
    ['webp', { quality: 95, alphaQuality: 100, smartSubsample: true, effort: 6 }],
    ['webp', { quality: 92, alphaQuality: 100, smartSubsample: true, effort: 6 }],
    ['webp', { quality: 85, alphaQuality: 100, smartSubsample: true, effort: 6 }],
    ['avif', { quality: 70, chromaSubsampling: '4:4:4', effort: 6 }],
  ];
  for (const layer of Object.keys(meta)) {
    const file = path.join(SRC, `${layer}.png`);
    const src = await raw(file);
    for (const [fmt, opts] of cands) {
      const buf = await encode(file, fmt, opts);
      const err = await errorOf(src, buf);
      console.log(layer, fmt, JSON.stringify(opts), buf.length, JSON.stringify(err));
    }
  }
  process.exit(0);
}

fs.mkdirSync(DST, { recursive: true });
const layers = [];
let bytes = 0;
for (const name of ['far', 'mid', 'street', 'near']) {
  const m = meta[name];
  if (!m) continue;
  const c = CHOSEN[name];
  const file = path.join(SRC, `${name}.png`);
  const buf = await encode(file, c.format, c.opts);
  const out = `${name}.${c.format}`;
  fs.writeFileSync(path.join(DST, out), buf);
  const err = await errorOf(await raw(file), buf);
  bytes += buf.length;
  const p = m.proxy;
  const proxy =
    p.type === 'disc+cylinder'
      ? { type: p.type, center: [p.center[0], -p.center[1]], groundY: p.ground_z, radius: p.radius, top: p.top_z }
      : { type: 'planeZ', z: -p.y, x: p.x, y: p.z };
  layers.push({
    name,
    file: out,
    bytes: buf.length,
    size: m.size,
    lon: m.lon,
    lat: m.lat,
    opaque: name === 'far',
    proxy,
    proxy_blender: p,
    spp: m.spp,
    ppd: m.ppd,
    stats_linear: m.stats,
    encode: { ...c, display_error_vs_png: err },
  });
  console.log(name, out, buf.length, 'bytes', JSON.stringify(err));
}
const eyeB = meta.far.eye_blender;
const sidecar = {
  about:
    'Street backdrop for ?v2: Cycles panoramas of NEW_exterior (room.blend, approved dusk setup) from one bake eye; see src/scene/exteriorBackdrop.ts and blender/scripts/v2_exterior_web.py.',
  source: meta.far.source,
  coordinates: 'three.js Y-up metres; three (x, y, z) = Blender (x, z, -y). *_blender fields are Blender Z-up.',
  eye: toThree(eyeB),
  eye_blender: eyeB,
  poses_blender: meta.far.poses_blender,
  camera_basis:
    'Equirectangular from `eye`: azimuth = atan2(x, -z) in three (Blender atan2(x, y)), + to the right of the -Z (Blender +Y) view; elevation = asin(y). u = (az - lon0)/(lon1 - lon0), v = (el - lat0)/(lat1 - lat0), v = 0 is the bottom image row. lon/lat in degrees.',
  encoding: {
    type: 'log2',
    min: LOG.min,
    max: LOG.max,
    decode: 'L = t > 0.5/255 ? 2^(min + t*(max-min)) : 0 per channel; alpha straight (far: opaque)',
  },
  radiance:
    'Scene-linear Rec.709 radiance, as Cycles wrote it before the view transform. The approved grade is applied at runtime: AgX (Blender look Medium High Contrast), exposure +0.45 EV (toneMappingExposure 2^0.45). Unlit/emissive: never lit again.',
  render: meta.far.render,
  glass: {
    plane_z: -1.398,
    ior: 1.5,
    about:
      'The approved stills see the street through Mesh_11, a single-sided IOR 1.5 Principled glass plane (not thin-walled) at Blender y = 1.398: every view ray refracts once and never exits, magnifying the street ~1.5x. The runtime reproduces it by refracting the view ray at this plane (three z = -1.398) and applying Fresnel transmittance; ior 1 = a plain opening. The layers themselves are baked without the glass.',
  },
  tris: null,
  bytes,
  layers,
};
// tris as built by exteriorBackdrop.ts: disc 64 + wall 128, two planes x 2
sidecar.tris = 64 * 3 + layers.filter((l) => l.proxy.type === 'planeZ').length * 2;
fs.writeFileSync(path.join(DST, 'exterior.json'), JSON.stringify(sidecar, null, 1));
console.log('total', bytes, 'bytes; tris', sidecar.tris);
