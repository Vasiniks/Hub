import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

/**
 * The baked sunset room (`?v2`), from `blender/bake/sunset/`.
 *
 * Four world-space atlas GLBs (shell, desk, furniture, soft) plus their RGBM lightmap PNGs.
 * `TEXCOORD_1` is the lightmap UV; the decode is `L = (rgb * a * range_sqrt)^2` with the
 * per-atlas `range_sqrt` from `manifest.json`, exactly as `blender/bake/sunset/README.md`
 * specifies. `lightMapIntensity = PI` reproduces Blender (`albedo * L`), because three
 * computes `irradiance * albedo / PI`.
 *
 * Albedo: the GLBs carry no images, and the glTF exporter writes `baseColorFactor` 0.8 for every
 * material whose base colour is a node graph (walls 0.29 blue-grey, floor wood, rug, the desk
 * frame's black nylon, the bambu table, the bookrack board), then merges the look-alikes. So the
 * albedo comes from `albedo_<atlas>.png` instead: Cycles' own diffuse colour pass baked in the
 * lightmap UV layout (`scripts/v2look/blender_albedo.py`), which is exactly the colour the
 * lightmap was divided by. Decals (`rs_scuff_*`) carry their coverage in its alpha.
 *
 * No double-lighting, by construction: every baked mesh becomes a MeshBasicMaterial, which
 * has no direct-light loops, no hemisphere/ambient terms and no diffuse IBL — only its
 * lightmap. The v2 scene carries no live sun, lamp, hemisphere or rect lights.
 * Specular is not in the bake. The semigloss trim, desk laminate and window frame can take it
 * from the renderer's environment capture of the baked room (`SPECULAR`, `?spec=0|1`): a
 * standard material whose diffuse is still exactly `albedo * L` and whose environment
 * *diffuse* is removed.
 */

export const V2_EXPOSURE = 2 ** 0.45;

/**
 * Baked materials that may also take environment specular (glTF material name → roughness).
 * Roughness 0.3 is an assumption, not read from Blender (the materials drive it with noise through
 * Map Range); F0 is three's dielectric 0.04, as Blender's IOR 1.5 / Specular 0.5.
 */
const SPECULAR: Record<string, number> = {
  rs_trim_semigloss: 0.3,
  desk_white_laminate: 0.3,
  desk_white_edge: 0.3,
  rs_window_frame_black: 0.3,
};

/** Decals: alpha-blended over the surface behind, coverage from the albedo atlas's alpha. */
const isDecal = (name: string) => name.startsWith('rs_scuff');

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
  /** Environment specular on the `SPECULAR` materials (they swap back to matte when off). Debug
   * hooks only: the `specular` load option is the switch a quality tier should use. */
  setSpecular: (on: boolean) => void;
  specularOn: () => boolean;
  specularMeshes: number;
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

async function loadAlbedo(url: string): Promise<THREE.Texture> {
  const tex = await new THREE.TextureLoader().loadAsync(url);
  tex.flipY = false; // same row order as the lightmap PNGs
  tex.colorSpace = THREE.SRGBColorSpace;
  // Islands are packed with the lightmap's 8 px margin; mipmaps would bleed across them.
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
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

/**
 * The same lightmap on a MeshStandardMaterial that adds only environment specular: the RGBM
 * decode on the standard lightmap chunk (the README's patch), environment diffuse removed (the
 * bake already holds it), and three's diffuse energy split skipped, because the albedo atlas is
 * Cycles' diffuse colour pass, which has already lost what the Principled specular layer reflects.
 */
function applyRGBMSpecular(mat: THREE.MeshStandardMaterial, rangeSqrt: number) {
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.lmRange = { value: rangeSqrt };
    const chunks = THREE.ShaderChunk as unknown as Record<string, string>;
    const maps = chunks.lights_fragment_maps;
    const physical = chunks.lights_physical_pars_fragment;
    const lm = 'vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;';
    const ibl = 'iblIrradiance += getIBLIrradiance( geometryNormal );';
    const split = 'vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - singleScattering - multiScattering );';
    if (!maps.includes(lm) || !maps.includes(ibl) || !physical.includes(split)) throw new Error('baked room: standard lighting chunks changed');
    shader.fragmentShader =
      'uniform float lmRange;\n' +
      shader.fragmentShader
        .replace(
          '#include <lights_fragment_maps>',
          maps
            .replace(lm, 'vec3 lmS = lightMapTexel.rgb * lightMapTexel.a * lmRange;\nvec3 lightMapIrradiance = lmS * lmS * lightMapIntensity;')
            .replace(ibl, ''),
        )
        .replace('#include <lights_physical_pars_fragment>', physical.replace(split, 'vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution );'));
  };
  mat.customProgramCacheKey = () => `baked-rgbm-spec:${rangeSqrt}`;
}

export interface BakedRoomOptions {
  /**
   * Environment specular on the trim, desk laminate and window frame. Off by default: measured
   * against the Cycles frames it currently adds error (it reflects the beige window placeholder
   * and is never occluded by the props that are not on the web yet). A quality tier can turn it
   * on later; `setSpecular` switches it at runtime. `?spec=0|1` overrides either way.
   */
  specular?: boolean;
}

export async function loadBakedRoom(base: string, options: BakedRoomOptions = {}): Promise<BakedRoom> {
  const params = new URLSearchParams(location.search);
  // Debug A/B switches: `albedo=0` restores the exported base colours (the old look); `spec=0|1`.
  const useAlbedo = params.get('albedo') !== '0';
  const specularOn = params.has('spec') ? params.get('spec') === '1' : options.specular === true;
  const manifest = (await fetch(`${base}manifest.json`).then((r) => {
    if (!r.ok) throw new Error(`baked room manifest missing at ${base}manifest.json`);
    return r.json();
  })) as {
    atlases: Record<string, { glb: string; web: { file: string; range_sqrt: number } }>;
  };
  const albedoManifest = useAlbedo
    ? ((await fetch(`${base}albedo.json`).then((r) => {
        if (!r.ok) throw new Error(`baked room albedo missing at ${base}albedo.json`);
        return r.json();
      })) as { atlases: Record<string, { file: string }> })
    : null;
  const specs: AtlasSpec[] = Object.entries(manifest.atlases).map(([name, a]) => ({
    name,
    file: a.glb,
    lightmap: a.web.file,
    rangeSqrt: a.web.range_sqrt,
  }));

  // Geometry is EXT_meshopt_compression (scripts/meshopt-glb.mjs).
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  const group = new THREE.Group();
  group.name = 'bakedRoom';
  const atlases: Record<string, THREE.Group> = {};
  const swaps: { mesh: THREE.Mesh; matte: THREE.Material; glossy: THREE.Material }[] = [];
  let tris = 0;

  await Promise.all(
    specs.map(async (spec) => {
      const albedoFile = albedoManifest?.atlases[spec.name]?.file;
      if (albedoManifest && !albedoFile) throw new Error(`baked room: no albedo for atlas ${spec.name}`);
      const [gltf, lightmap, albedo] = await Promise.all([
        loader.loadAsync(base + spec.file),
        loadTexture(base + spec.lightmap),
        albedoFile ? loadAlbedo(base + albedoFile) : Promise.resolve(null),
      ]);
      const made = new Map<string, { matte: THREE.MeshBasicMaterial; glossy: THREE.MeshStandardMaterial | null }>();
      const atlas = new THREE.Group();
      atlas.name = `baked:${spec.name}`;
      gltf.scene.updateMatrixWorld(true);
      gltf.scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const src = Array.isArray(mesh.material) ? mesh.material[0] : (mesh.material as THREE.Material);
        let mats = made.get(src.name);
        if (!mats) {
          const matte = new THREE.MeshBasicMaterial({ name: `baked:${spec.name}:${src.name || 'mat'}` });
          if (albedo) {
            matte.map = albedo; // colour stays white: the atlas is the whole albedo
            if (isDecal(src.name)) {
              matte.transparent = true;
              matte.depthWrite = false;
            }
          } else {
            // `?albedo=0`: the exported base-colour factor, as before.
            const std = src as THREE.MeshStandardMaterial;
            if (std.color) matte.color.copy(std.color);
            if (std.map) matte.map = std.map;
          }
          matte.lightMap = lightmap;
          matte.lightMapIntensity = Math.PI;
          applyRGBM(matte, spec.rangeSqrt);
          let glossy: THREE.MeshStandardMaterial | null = null;
          const roughness = SPECULAR[src.name];
          if (roughness !== undefined) {
            glossy = new THREE.MeshStandardMaterial({
              name: `${matte.name}:spec`,
              color: matte.color,
              map: matte.map,
              roughness,
              metalness: 0,
              lightMap: lightmap,
              lightMapIntensity: Math.PI,
            });
            applyRGBMSpecular(glossy, spec.rangeSqrt);
          }
          mats = { matte, glossy };
          made.set(src.name, mats);
        }
        mesh.material = mats.glossy && specularOn ? mats.glossy : mats.matte;
        if (mats.glossy) swaps.push({ mesh, matte: mats.matte, glossy: mats.glossy });
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
  let specular = specularOn;
  return {
    group,
    atlases,
    tris,
    specularMeshes: swaps.length,
    specularOn: () => specular,
    setSpecular(on: boolean) {
      specular = on;
      for (const { mesh, matte, glossy } of swaps) mesh.material = on ? glossy : matte;
    },
  };
}
