import * as THREE from 'three';

/**
 * Lookup tables for rect-area lights (the window, the monitor's glow, the desk spill).
 *
 * three ships them as `RectAreaLightTexturesLib`: two 64×64 RGBA tables written out as some
 * 33,000 decimal float literals — 307 KB of source, over a fifth of the whole bundle, parsed and
 * compiled on every visit. The same tables are fetched here as a 64 KB half-float binary
 * (scripts/build-ltc.mjs), behind the loading bar. three already uses exactly this half-float
 * data on devices without float filtering; where it can filter floats, the float textures are
 * expanded from the same data (≤0.1% relative difference, below any visible threshold).
 */
export async function loadLtcTables() {
  const res = await fetch(`${import.meta.env.BASE_URL}assets/ltc.bin`);
  const bytes = await res.arrayBuffer();
  const n = 64 * 64 * 4;
  const half1 = new Uint16Array(bytes, 0, n);
  const half2 = new Uint16Array(bytes, n * 2, n);
  const toFloat = (h: Uint16Array) => Float32Array.from(h, (v) => THREE.DataUtils.fromHalfFloat(v));
  const table = (data: Float32Array | Uint16Array, type: THREE.TextureDataType) => {
    const tex = new THREE.DataTexture(
      data, 64, 64, THREE.RGBAFormat, type, THREE.UVMapping,
      THREE.ClampToEdgeWrapping, THREE.ClampToEdgeWrapping, THREE.LinearFilter, THREE.NearestFilter, 1,
    );
    tex.needsUpdate = true;
    return tex;
  };
  const lib = THREE.UniformsLib as unknown as Record<string, THREE.DataTexture>;
  lib.LTC_HALF_1 = table(half1, THREE.HalfFloatType);
  lib.LTC_HALF_2 = table(half2, THREE.HalfFloatType);
  lib.LTC_FLOAT_1 = table(toFloat(half1), THREE.FloatType);
  lib.LTC_FLOAT_2 = table(toFloat(half2), THREE.FloatType);
}
