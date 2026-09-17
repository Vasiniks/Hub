// Writes the rect-area-light LTC lookup tables as a 64 KB half-float binary
// (public/assets/ltc.bin), replacing 307 KB of JavaScript float literals in the bundle.
// Layout: LTC_MAT_1 then LTC_MAT_2, each 64 x 64 x RGBA, Uint16 half floats, little-endian.
import fs from 'node:fs';
import { RectAreaLightTexturesLib } from 'three/examples/jsm/lights/RectAreaLightTexturesLib.js';
RectAreaLightTexturesLib.init();
const a = RectAreaLightTexturesLib.LTC_HALF_1.image.data;
const b = RectAreaLightTexturesLib.LTC_HALF_2.image.data;
const out = Buffer.concat([Buffer.from(a.buffer, a.byteOffset, a.byteLength), Buffer.from(b.buffer, b.byteOffset, b.byteLength)]);
fs.writeFileSync('public/assets/ltc.bin', out);
console.log(`public/assets/ltc.bin ${out.length} bytes`);
