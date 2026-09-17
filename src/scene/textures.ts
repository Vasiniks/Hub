import * as THREE from 'three';

/**
 * Scanned surface textures (ambientCG, CC0 — see assets/MANIFEST.md) for the three surfaces
 * that cover the most screen: floor, walls, chair fabric.
 *
 * Sizes follow how many pixels each can occupy: the floor fills much of the standing view at a
 * grazing angle, so its colour and normal are 1K; plaster roughness is low-frequency, so 512;
 * the fabric weave is tiled small on a chair, so 512 normal and 256 roughness. Seven maps,
 * ~680 KB. They are decoded off the main thread as ImageBitmaps and loaded behind the loading
 * screen, so nothing arrives flat and pops in later.
 */
export interface SurfaceTextures {
  floorColor: THREE.Texture;
  floorNormal: THREE.Texture;
  floorRough: THREE.Texture;
  wallNormal: THREE.Texture;
  wallRough: THREE.Texture;
  fabricNormal: THREE.Texture;
  fabricRough: THREE.Texture;
}

export async function loadSurfaceTextures(): Promise<SurfaceTextures> {
  const loader = new THREE.ImageBitmapLoader();
  loader.setOptions({ imageOrientation: 'none' });
  const base = `${import.meta.env.BASE_URL}assets/textures/`;
  const load = async (file: string, srgb = false, anisotropy = 4) => {
    const bitmap = await loader.loadAsync(base + file);
    const tex = new THREE.Texture(bitmap as unknown as HTMLImageElement);
    // ImageBitmaps ignore flipY; these tile, so orientation does not matter anyway.
    tex.flipY = false;
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.anisotropy = anisotropy;
    if (srgb) tex.colorSpace = THREE.SRGBColorSpace;
    tex.needsUpdate = true;
    return tex;
  };
  const [floorColor, floorNormal, floorRough, wallNormal, wallRough, fabricNormal, fabricRough] = await Promise.all([
    load('floor_color.jpg', true, 8),
    load('floor_normal.jpg', false, 8),
    load('floor_rough.jpg', false, 8),
    load('wall_normal.jpg'),
    load('wall_rough.jpg'),
    load('fabric_normal.jpg'),
    load('fabric_rough.jpg'),
  ]);
  return { floorColor, floorNormal, floorRough, wallNormal, wallRough, fabricNormal, fabricRough };
}

/**
 * Texture coordinates from object-space position, projected along whichever axis the surface
 * faces. Walls are rounded boxes whose UVs run 0–1 per face, and the chair came from Blender
 * with none, so a tiling texture needs coordinates in metres instead. The static merge bakes
 * transforms into these meshes, so object space is room space and the scale is the same
 * everywhere. `tile` is metres per texture repeat, passed as a uniform so materials with
 * different tiles never share a compiled program by accident.
 */
export function projectMaps(mat: THREE.MeshStandardMaterial, tile: number) {
  const own = Object.hasOwn(mat, 'onBeforeCompile') ? mat.onBeforeCompile : null;
  mat.onBeforeCompile = (shader, renderer) => {
    // Resolved at compile time: the class-wide hook (areaLights.ts) is installed after materials exist.
    (own ?? Object.getPrototypeOf(mat).onBeforeCompile).call(mat, shader, renderer);
    shader.uniforms.uTileScale = { value: 1 / tile };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uTileScale;')
      .replace(
        '#include <uv_vertex>',
        `#include <uv_vertex>
  {
    vec3 an = abs(normal);
    vec2 projected = (an.x > an.y && an.x > an.z) ? position.zy : (an.z > an.y ? position.xy : position.xz);
    projected *= uTileScale;
    #ifdef USE_MAP
      vMapUv = projected;
    #endif
    #ifdef USE_NORMALMAP
      vNormalMapUv = projected;
    #endif
    #ifdef USE_ROUGHNESSMAP
      vRoughnessMapUv = projected;
    #endif
  }`,
      );
  };
  // The key must still distinguish whatever the previous hook injected (the walls' set fade):
  // two materials that only share this key would otherwise share one compiled program.
  const previousKey = own?.toString() ?? '';
  mat.customProgramCacheKey = () => `projected-maps|${previousKey}`;
  mat.needsUpdate = true;
}
