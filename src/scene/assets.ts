import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

/**
 * Runtime side of the asset pipeline.
 *
 * Models are authored and prepared in Blender (see `blender/scripts`) and land here as GLB.
 * Three.js is the renderer, not the modelling tool — anything with real topology comes from
 * a file, and only genuinely procedural things are still built in code.
 *
 * Everything is loaded up front, behind the loading bar, so no asset can arrive mid-interaction
 * and cause a hitch. Materials are re-authored against the room's own palette on arrival, so
 * an imported object answers this room's lighting rather than carrying its own look.
 */
export interface AssetSpec {
  /** Key used by the scene builders. */
  name: string;
  /** Path under /assets/processed. */
  file: string;
}

export type Assets = Awaited<ReturnType<typeof loadAssets>>;

export interface AssetMeta {
  /** Placement points in glTF space, written by the Blender build. */
  socket?: [number, number, number];
  beam?: [number, number, number];
  [key: string]: unknown;
}

export async function loadAssets(specs: AssetSpec[], onProgress?: (done: number, total: number) => void) {
  const loader = new GLTFLoader();
  const scenes = new Map<string, THREE.Group>();
  const metas = new Map<string, AssetMeta>();
  const base = `${import.meta.env.BASE_URL}assets/processed/`;

  let done = 0;
  await Promise.all(
    specs.map(async (spec) => {
      const gltf = await loader.loadAsync(base + spec.file);
      scenes.set(spec.name, gltf.scene);
      // Sidecar metadata is optional; most assets are pure geometry.
      try {
        const res = await fetch(base + spec.file.replace(/\.glb$/, '.json'));
        if (res.ok) metas.set(spec.name, (await res.json()) as AssetMeta);
      } catch {
        /* no sidecar for this asset */
      }
      done++;
      onProgress?.(done, specs.length);
    }),
  );

  return {
    has(name: string) {
      return scenes.has(name);
    },
    meta(name: string): AssetMeta {
      return metas.get(name) ?? {};
    },
    /**
     * A fresh instance of an asset. Geometry is shared between instances; materials are not,
     * so a caller can retint one copy without touching the rest.
     */
    instance(name: string): THREE.Group {
      const source = scenes.get(name);
      if (!source) throw new Error(`asset not loaded: ${name}`);
      const copy = source.clone(true);
      copy.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.material = Array.isArray(mesh.material)
          ? mesh.material.map((m) => m.clone())
          : (mesh.material as THREE.Material).clone();
      });
      return copy;
    },
    /** Find a named part inside an instance (Blender object names survive the export). */
    part(root: THREE.Object3D, name: string): THREE.Mesh | null {
      let found: THREE.Mesh | null = null;
      root.traverse((o) => {
        if (!found && o.name === name && (o as THREE.Mesh).isMesh) found = o as THREE.Mesh;
      });
      return found;
    },
    /** Replace every material on an instance, keeping the room's material language. */
    retint(root: THREE.Object3D, byName: Record<string, THREE.Material>) {
      root.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const apply = (m: THREE.Material) => byName[m.name] ?? m;
        mesh.material = Array.isArray(mesh.material) ? mesh.material.map(apply) : apply(mesh.material as THREE.Material);
      });
    },
  };
}
