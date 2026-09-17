// Pipeline step: Blender output (assets/processed) → optimised runtime copies (public/assets/processed).
//
// Quantizes vertex attributes with KHR_mesh_quantization — positions to 16-bit, normals to
// 8-bit, texture coordinates to 16-bit — which three's GLTFLoader reads natively, so the room
// ships no decoder. Also merges duplicate accessors/materials and prunes anything unused.
// Usage: node scripts/optimize-glb.mjs [name ...]   (default: every GLB in assets/processed)
import fs from 'node:fs';
import path from 'node:path';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, prune, quantize } from '@gltf-transform/functions';

const src = 'assets/processed';
const dst = 'public/assets/processed';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const names = process.argv.slice(2);
const files = fs.readdirSync(src).filter((f) => f.endsWith('.glb') && (!names.length || names.includes(path.basename(f, '.glb'))));
let before = 0;
let after = 0;
for (const f of files) {
  const doc = await io.read(path.join(src, f));
  await doc.transform(
    dedup(),
    // Positions keep 16 bits across the mesh's own bounds: sub-0.02 mm on a 1 m robot.
    quantize({ quantizePosition: 16, quantizeNormal: 8, quantizeTexcoord: 16, quantizeColor: 8, quantizeGeneric: 12 }),
    prune(),
  );
  const out = path.join(dst, f);
  await io.write(out, doc);
  const a = fs.statSync(path.join(src, f)).size;
  const b = fs.statSync(out).size;
  before += a;
  after += b;
  // Sidecar metadata travels with the model.
  const meta = path.join(src, f.replace('.glb', '.json'));
  if (fs.existsSync(meta)) fs.copyFileSync(meta, path.join(dst, path.basename(meta)));
  console.log(`${f.padEnd(18)} ${(a / 1024).toFixed(0).padStart(5)} KB → ${(b / 1024).toFixed(0).padStart(5)} KB`);
}
console.log(`total ${(before / 1024).toFixed(0)} KB → ${(after / 1024).toFixed(0)} KB`);
