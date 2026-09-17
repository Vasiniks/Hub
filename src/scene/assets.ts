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
  /** Has a sidecar `.json` (placement metadata). Only these are fetched — no 404 per model. */
  meta?: boolean;
}

/**
 * Undo mesh quantization on arrival.
 *
 * The runtime GLBs are quantized (scripts/optimize-glb.mjs): 16-bit positions, 8-bit normals,
 * with each mesh's dequantization stored as a scale and offset on its node. That halves the
 * download, but the room merges static geometry into shared buffers in room coordinates, slices
 * the book in metres, and animates parts by absolute position — none of which survive integer
 * attributes or extra node transforms. The pipeline applies every real transform in Blender
 * before export, so every node transform under a model's root is quantization and nothing else:
 * baking it into a float copy of each mesh's geometry and resetting the nodes is exactly the
 * unquantized model, at the cost of a few milliseconds behind the loading bar.
 */
function dequantize(root: THREE.Object3D) {
  root.updateMatrixWorld(true);
  const toRoot = new THREE.Matrix4();
  const rootInverse = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const meshes: THREE.Mesh[] = [];
  root.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) meshes.push(o as THREE.Mesh);
  });
  for (const mesh of meshes) {
    const source = mesh.geometry;
    const geo = new THREE.BufferGeometry();
    for (const [name, attr] of Object.entries(source.attributes)) {
      const a = attr as THREE.BufferAttribute;
      const out = new Float32Array(a.count * a.itemSize);
      for (let i = 0; i < a.count; i++) for (let k = 0; k < a.itemSize; k++) out[i * a.itemSize + k] = a.getComponent(i, k);
      geo.setAttribute(name, new THREE.BufferAttribute(out, a.itemSize));
    }
    if (source.index) geo.setIndex(source.index);
    for (const g of source.groups) geo.addGroup(g.start, g.count, g.materialIndex);
    toRoot.multiplyMatrices(rootInverse, mesh.matrixWorld);
    geo.applyMatrix4(toRoot);
    mesh.geometry = geo;
  }
  root.traverse((o) => {
    if (o === root) return;
    o.position.set(0, 0, 0);
    o.quaternion.identity();
    o.scale.set(1, 1, 1);
  });
  root.updateMatrixWorld(true);
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
      const [gltf, meta] = await Promise.all([
        loader.loadAsync(base + spec.file),
        spec.meta ? fetch(base + spec.file.replace(/\.glb$/, '.json')).then((r) => (r.ok ? r.json() : null)) : null,
      ]);
      dequantize(gltf.scene);
      scenes.set(spec.name, gltf.scene);
      if (meta) metas.set(spec.name, meta as AssetMeta);
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
    /**
     * World-space centre of a named part.
     *
     * Not `getWorldPosition`: the Blender pipeline applies transforms into the vertices, so
     * every exported mesh sits at its group's origin and its position tells you nothing about
     * where the geometry actually is.
     */
    partCenter(root: THREE.Object3D, name: string, out = new THREE.Vector3()) {
      const mesh = this.part(root, name);
      if (!mesh) return out;
      return new THREE.Box3().setFromObject(mesh).getCenter(out);
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
