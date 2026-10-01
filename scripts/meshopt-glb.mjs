// Compress the v2 GLBs' geometry with EXT_meshopt_compression, in place.
//
// Runs after `optimize-glb.mjs` (which quantizes). Geometry is ~70% of the props' bytes and
// meshopt roughly halves it; three already ships the decoder (examples/jsm/libs/
// meshopt_decoder.module.js, wired in bakedRoom.ts / v2Props.ts), so the site adds no package.
// Quantization stays at 16 bits for positions and texture coordinates: the baked atlases'
// TEXCOORD_1 addresses a 1024² lightmap and must not lose precision.
// Usage: node scripts/meshopt-glb.mjs [dir ...]   (default: public/assets/v2/props public/assets/v2/room)
import fs from 'node:fs';
import path from 'node:path';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS, EXTMeshoptCompression } from '@gltf-transform/extensions';
import { meshopt } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';

await MeshoptEncoder.ready;
await MeshoptDecoder.ready;
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });

const dirs = process.argv.slice(2).length ? process.argv.slice(2) : ['public/assets/v2/props', 'public/assets/v2/room'];
let before = 0;
let after = 0;
for (const dir of dirs) {
  for (const f of fs.readdirSync(dir).filter((f) => f.endsWith('.glb'))) {
    const file = path.join(dir, f);
    const doc = await io.read(file);
    const size = fs.statSync(file).size;
    // Already compressed: decoding and re-encoding would only cost time.
    if (doc.getRoot().listExtensionsUsed().some((e) => e.extensionName === EXTMeshoptCompression.EXTENSION_NAME)) {
      console.log(`${f.padEnd(20)} already meshopt`);
      before += size;
      after += size;
      continue;
    }
    await doc.transform(meshopt({ encoder: MeshoptEncoder, level: 'medium', quantizePosition: 16, quantizeTexcoord: 16, quantizeNormal: 10 }));
    const out = await io.writeBinary(doc);
    fs.writeFileSync(file, out);
    before += size;
    after += out.byteLength;
    console.log(`${f.padEnd(20)} ${size} -> ${out.byteLength}`);
  }
}
console.log(`total ${before} -> ${after} bytes`);
