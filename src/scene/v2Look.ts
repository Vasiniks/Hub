import * as THREE from 'three';
import type { DisplayLUT } from './renderer';
import { V2_EXPOSURE, type BakedRoom } from './bakedRoom';

/**
 * The `?v2` room's image formation, taken from Blender rather than approximated.
 *
 * The bake's reference frames were made with Blender 5.2's view "AgX", look "AgX - Medium High
 * Contrast", exposure +0.45 EV, sRGB display. three's `AgXToneMapping` is a polynomial fit of an
 * older AgX (16.5 stops, Rec.2020 inset, pow 2.2) with no looks; Blender 5.2's AgX is a 25-stop
 * E-Gamut LUT, and its look adds a log-space contrast of 1.2 (pivot -0.2) inside a luminance-
 * compensated Rec.2020 log space that is itself a 3D LUT. Neither has a faithful closed form in a
 * few lines of GLSL, so `scripts/v2look/blender_lut.py` evaluates Blender's own OCIO config
 * (PyOpenColorIO, the same processor Blender builds) on a 33³ grid and checks it against Blender's
 * "save as render" output (mean error 0.003 of an 8-bit step). This module loads that table and
 * hands it to the grade pass (`GradedOutputPass.setDisplayLUT`).
 *
 * URL switches for A/B against the previous look (debug aids, default off):
 *   `lut=0`  three's AgX + the v1 cinematic grade instead of Blender's view
 */

interface LutMeta {
  file: string;
  size: number;
  log2_min: number;
  log2_max: number;
}

/** Load the float16 RGB table (red fastest, then green, then blue) as N blue slices side by side. */
export async function loadDisplayLUT(base: string): Promise<DisplayLUT> {
  const meta = (await fetch(`${base}agx_mhc_srgb.json`).then((r) => {
    if (!r.ok) throw new Error(`v2 look: LUT metadata missing at ${base}`);
    return r.json();
  })) as LutMeta;
  const buffer = await fetch(base + meta.file).then((r) => {
    if (!r.ok) throw new Error(`v2 look: LUT missing at ${base}${meta.file}`);
    return r.arrayBuffer();
  });
  const n = meta.size;
  const src = new Uint16Array(buffer);
  if (src.length !== n * n * n * 3) throw new Error(`v2 look: LUT is ${src.length} halves, expected ${n * n * n * 3}`);
  const data = new Uint16Array(n * n * n * 4);
  const ONE = 0x3c00; // 1.0 as a half float
  for (let b = 0; b < n; b++)
    for (let g = 0; g < n; g++)
      for (let r = 0; r < n; r++) {
        const i = ((b * n + g) * n + r) * 3;
        const o = (g * n * n + b * n + r) * 4;
        data[o] = src[i];
        data[o + 1] = src[i + 1];
        data[o + 2] = src[i + 2];
        data[o + 3] = ONE;
      }
  const texture = new THREE.DataTexture(data, n * n, n, THREE.RGBAFormat, THREE.HalfFloatType);
  texture.colorSpace = THREE.NoColorSpace;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.needsUpdate = true;
  return { texture, size: n, log2Min: meta.log2_min, log2Max: meta.log2_max };
}

interface V2View {
  renderer: THREE.WebGLRenderer;
  composer: { render: (dt?: number) => void };
  setDisplayLUT: (lut: DisplayLUT | null) => void;
}

/**
 * Apply the v2 look to a renderer made by `createRenderer`: Blender's exposure and display
 * transform. Call once, before `warmUp`, so the grade program compiles under the veil.
 */
export async function applyV2Look(view: V2View, scene: THREE.Scene, camera: THREE.PerspectiveCamera, baked: BakedRoom) {
  const params = new URLSearchParams(location.search);
  view.renderer.toneMappingExposure = V2_EXPOSURE;
  const lut = params.get('lut') === '0' ? null : await loadDisplayLUT(`${import.meta.env.BASE_URL}assets/v2/grade/`);
  view.setDisplayLUT(lut);
  if (params.has('debug')) {
    const { installV2LookDebug } = await import('../debug/v2look');
    installV2LookDebug({ view, scene, camera, lut, baked });
  }
}
