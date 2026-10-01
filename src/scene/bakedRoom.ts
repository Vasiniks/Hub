import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

/**
 * The baked sunset room (`?v2`), from `blender/bake/sunset/`.
 *
 * Four world-space atlas GLBs (shell, desk, furniture, soft) plus their RGBM lightmap PNGs.
 * `TEXCOORD_1` is the lightmap UV; the decode is `L = (rgb * a * range_sqrt)^2` with the
 * per-atlas `range_sqrt` from `manifest.json`, exactly as `blender/bake/sunset/README.md`
 * specifies. `lightMapIntensity = PI` reproduces Blender (`albedo * L`), because three
 * computes `irradiance * albedo / PI`.
 *
 * No double-lighting, by construction: every baked mesh becomes a MeshBasicMaterial, which
 * has no direct-light loops, no hemisphere/ambient terms and no diffuse IBL — only its
 * lightmap. The v2 scene carries no live sun, lamp, hemisphere or rect lights, and no
 * environment map, so there is nothing to exclude per mesh and nothing to reflect.
 * Specular is not in the bake: the choice here is matte everywhere, including the
 * semigloss trim, desk laminate and window frame.
 */

export const V2_EXPOSURE = 2 ** 0.45;

interface AtlasSpec {
  name: string;
  file: string;
  lightmap: string;
  rangeSqrt: number;
}

export interface BakedRoom {
  group: THREE.Group;
  /** Per-atlas groups, for tri counts and the curtain-cost measurement. */
  atlases: Record<string, THREE.Group>;
  tris: number;
}

async function loadTexture(url: string): Promise<THREE.Texture> {
  const tex = await new THREE.TextureLoader().loadAsync(url);
  // glTF convention: PNG rows are top-first, matching TEXCOORD_1 directly.
  tex.flipY = false;
  // Linear RGBM data, not sRGB; never premultiply (that would scale rgb by alpha).
  tex.colorSpace = THREE.NoColorSpace;
  if ('premultiplyAlpha' in tex) (tex as unknown as { premultiplyAlpha: boolean }).premultiplyAlpha = false;
  // The README says LinearFilter; mipmaps on RGBM are approximate, so none.
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  // TEXCOORD_1.
  tex.channel = 1;
  return tex;
}

/**
 * MeshBasicMaterial honours `lightMap` (r186): `indirectDiffuse += texel * intensity / PI`,
 * then modulated by the diffuse colour — so with `lightMapIntensity = PI` the outgoing
 * light is `albedo * L`, exactly the Cycles diffuse pass. The README's patch targets the
 * standard-material chunk; the Basic anchor differs, same decode.
 */
function applyRGBM(mat: THREE.MeshBasicMaterial, rangeSqrt: number) {
  const prev = mat.onBeforeCompile;
  mat.onBeforeCompile = (shader, renderer) => {
    prev.call(mat, shader, renderer);
    shader.uniforms.lmRange = { value: rangeSqrt };
    const anchor = 'reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;';
    if (!shader.fragmentShader.includes(anchor)) throw new Error('baked room: MeshBasicMaterial lightmap chunk changed');
    shader.fragmentShader =
      'uniform float lmRange;\n' +
      shader.fragmentShader.replace(
        anchor,
        'vec3 lmS = lightMapTexel.rgb * lightMapTexel.a * lmRange;\n' +
          'reflectedLight.indirectDiffuse += lmS * lmS * lightMapIntensity * RECIPROCAL_PI;',
      );
  };
  mat.customProgramCacheKey = () => `baked-rgbm:${rangeSqrt}`;
}

export async function loadBakedRoom(base: string): Promise<BakedRoom> {
  const manifest = (await fetch(`${base}manifest.json`).then((r) => {
    if (!r.ok) throw new Error(`baked room manifest missing at ${base}manifest.json`);
    return r.json();
  })) as {
    atlases: Record<string, { glb: string; web: { file: string; range_sqrt: number } }>;
  };
  const specs: AtlasSpec[] = Object.entries(manifest.atlases).map(([name, a]) => ({
    name,
    file: a.glb,
    lightmap: a.web.file,
    rangeSqrt: a.web.range_sqrt,
  }));

  const loader = new GLTFLoader();
  const group = new THREE.Group();
  group.name = 'bakedRoom';
  const atlases: Record<string, THREE.Group> = {};
  let tris = 0;

  await Promise.all(
    specs.map(async (spec) => {
      const [gltf, lightmap] = await Promise.all([
        loader.loadAsync(base + spec.file),
        loadTexture(base + spec.lightmap),
      ]);
      const atlas = new THREE.Group();
      atlas.name = `baked:${spec.name}`;
      gltf.scene.updateMatrixWorld(true);
      gltf.scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const src = Array.isArray(mesh.material) ? mesh.material[0] : (mesh.material as THREE.Material);
        const baked = new THREE.MeshBasicMaterial({ name: `baked:${spec.name}:${src.name || 'mat'}` });
        // The GLBs carry no embedded images: albedo is the exported base-colour factor.
        const std = src as THREE.MeshStandardMaterial;
        if (std.color) baked.color.copy(std.color);
        if (std.map) baked.map = std.map;
        baked.lightMap = lightmap;
        baked.lightMapIntensity = Math.PI;
        // Matte: specular is not in the bake. (MeshBasicMaterial has no envMapIntensity;
        // none is needed — the v2 scene sets no environment, so there is nothing to reflect.)
        applyRGBM(baked, spec.rangeSqrt);
        mesh.material = baked;
        // The bake holds every shadow; nothing here writes or reads live shadow maps.
        mesh.castShadow = false;
        mesh.receiveShadow = false;
        const index = mesh.geometry.getIndex();
        tris += ((index ? index.count : mesh.geometry.getAttribute('position').count) / 3) | 0;
      });
      // The bake is already in world space; bake the node transforms in and reset them so the
      // atlas sits exactly where Cycles put it.
      atlas.add(...[...gltf.scene.children]);
      atlases[spec.name] = atlas;
      group.add(atlas);
    }),
  );
  group.updateMatrixWorld(true);
  return { group, atlases, tris };
}
