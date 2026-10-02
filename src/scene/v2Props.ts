import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { applyRGBMSpecular } from './bakedRoom';

/**
 * The v2 props, as the props workstream exports them: world-space GLBs in
 * `public/assets/v2/props/` plus a `manifest.json` that lists them.
 *
 * This only loads and indexes. Making a node interactive is `createPropRegistry().register()`
 * (src/interaction/props.ts); which node becomes which object is the table in
 * `src/data/v2Props.ts`. Lighting the props is not done here: they arrive with their own
 * (baked-texture) PBR materials and need the live lights the integration adds.
 *
 * The manifest shape is read loosely, because it is being written in parallel: a bare array, or
 * `{ props | files: [...] }`, or an object keyed by name. Each entry needs a `file` (or `glb`)
 * path relative to the manifest; `name`, `tris`, `emissive`/`emissive_materials` and `anchors`
 * are kept as given. A missing manifest is not an error: the room simply has no props yet.
 */
export interface PropEntry {
  name: string;
  file: string;
  tris?: number;
  emissive?: string[];
  anchors?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface LoadedProp {
  entry: PropEntry;
  /** The GLB's scene, added under `V2Props.group`. */
  root: THREE.Object3D;
}

export interface V2Props {
  group: THREE.Group;
  props: LoadedProp[];
  /** First node with this exact name in any prop GLB (GLTFLoader keeps Blender object names). */
  node(name: string): THREE.Object3D | undefined;
  /** Every node whose name starts with `prefix`, across all prop GLBs. */
  nodes(prefix: string): THREE.Object3D[];
  /** The loaded GLB root for a manifest name or file (`robot` or `robot.glb`). */
  file(nameOrFile: string): THREE.Object3D | undefined;
}

/**
 * Nodes under `root` whose name passes `test`, outermost only: a match inside another match comes
 * with its parent, so grouping the result never tears a hierarchy apart. Shared by the props GLBs
 * and the baked room (whose fixtures, like the bookrack, are interactive too).
 */
export function findNodes(root: THREE.Object3D, test: (name: string) => boolean): THREE.Object3D[] {
  const found: THREE.Object3D[] = [];
  const taken = new Set<THREE.Object3D>();
  root.traverse((o) => {
    if (o === root) return;
    if (o.parent && taken.has(o.parent)) {
      taken.add(o);
      return;
    }
    if (test(o.name)) {
      found.push(o);
      taken.add(o);
    }
  });
  return found;
}

function entriesOf(manifest: unknown): PropEntry[] {
  const list: unknown[] = Array.isArray(manifest)
    ? manifest
    : manifest && typeof manifest === 'object'
      ? Array.isArray((manifest as { assets?: unknown }).assets)
        ? ((manifest as { assets: unknown[] }).assets)
        : Array.isArray((manifest as { props?: unknown }).props)
        ? ((manifest as { props: unknown[] }).props)
        : Array.isArray((manifest as { files?: unknown }).files)
          ? ((manifest as { files: unknown[] }).files)
          : Object.entries(manifest as Record<string, unknown>).map(([name, v]) =>
              v && typeof v === 'object' ? { name, ...(v as object) } : null,
            )
      : [];
  const out: PropEntry[] = [];
  for (const raw of list) {
    if (!raw || typeof raw !== 'object') continue;
    const r = raw as Record<string, unknown>;
    const file = typeof r.file === 'string' ? r.file : typeof r.glb === 'string' ? r.glb : null;
    if (!file || !file.endsWith('.glb')) continue;
    const emissive = (r.emissive ?? r.emissive_materials ?? r.emissive_primitives) as string[] | undefined;
    out.push({
      ...r,
      name: typeof r.name === 'string' ? r.name : file.replace(/^.*\//, '').replace(/\.glb$/, ''),
      file,
      emissive: Array.isArray(emissive) ? emissive : undefined,
    });
  }
  return out;
}

/**
 * Lit materials (`KHR_materials_unlit`, the Cycles diffuse bake of the sunset room) store
 * scene-linear radiance divided by `litScale` so it fits 8 bits; the scale rides in the glTF
 * material extras. Multiply it back into the colour so the texture reads as radiance again —
 * the output pass then applies exposure and Blender's view exactly as it does to the room.
 */
function restoreLitScale(root: THREE.Object3D) {
  const done = new Set<THREE.Material>();
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (done.has(m)) continue;
      done.add(m);
      const k = Number((m.userData as { litScale?: unknown }).litScale);
      if (k > 0 && (m as THREE.MeshBasicMaterial).isMeshBasicMaterial) (m as THREE.MeshBasicMaterial).color.multiplyScalar(k);
    }
  });
}

/**
 * The indirect lightmap a `?rt` prop set carries (manifest entry, read loosely): RGBM of sqrt(L),
 * lossless WebP, decoded like the room's, on the UV the entry names (default 0: the PBR atlas).
 */
interface PropLightmap {
  file: string;
  rangeSqrt: number;
  channel: number;
  /** The glTF materials this map belongs to (a set with several atlases); none = every material. */
  materials?: string[];
}

function lightmapsOf(entry: PropEntry): PropLightmap[] {
  const list = (entry as unknown as { lightmaps?: unknown[] }).lightmaps;
  if (Array.isArray(list)) {
    return list.flatMap((raw) => {
      const one = lightmapOf({ lightmap: raw } as unknown as PropEntry);
      const materials = (raw as { materials?: unknown }).materials;
      return one ? [{ ...one, materials: Array.isArray(materials) ? (materials as string[]) : undefined }] : [];
    });
  }
  const one = lightmapOf(entry);
  return one ? [one] : [];
}

function lightmapOf(entry: PropEntry): PropLightmap | null {
  const r = entry as unknown as Record<string, unknown>;
  const lm = (r.lightmap ?? r.indirect) as
    | string
    | { file?: string; range_sqrt?: number; rangeSqrt?: number; uv?: number | string }
    | undefined;
  const file = typeof lm === 'string' ? lm : lm?.file;
  const o = typeof lm === 'object' ? lm : undefined;
  const rangeSqrt = Number(o?.rangeSqrt ?? o?.range_sqrt ?? r.range_sqrt ?? r.rangeSqrt ?? r.lightmap_range_sqrt);
  // A UV index, or its glTF attribute name ('TEXCOORD_1' → 1).
  const uv = o?.uv ?? r.lightmap_uv ?? r.uv_channel ?? r.uv ?? 0;
  const channel = typeof uv === 'string' ? Number(uv.replace(/^\D+/, '')) : Number(uv);
  return file && rangeSqrt > 0 ? { file, rangeSqrt, channel: Number.isFinite(channel) ? channel : 0 } : null;
}

async function applyPropLightmap(root: THREE.Object3D, url: string, rangeSqrt: number, channel: number, only?: string[]) {
  const tex = await new THREE.TextureLoader().loadAsync(url);
  tex.flipY = false;
  tex.colorSpace = THREE.NoColorSpace;
  if ('premultiplyAlpha' in tex) (tex as unknown as { premultiplyAlpha: boolean }).premultiplyAlpha = false;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.channel = channel;
  const done = new Set<THREE.Material>();
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      const std = m as THREE.MeshStandardMaterial;
      if (done.has(m) || !std.isMeshStandardMaterial || std.transparent) continue;
      // The monitor's screen has its own 0..1 UV (the attractor), outside every atlas.
      if (m.name.startsWith('mon_screen')) continue;
      if (only && !only.includes(m.name)) continue;
      done.add(m);
      std.lightMap = tex;
      std.lightMapIntensity = Math.PI;
      applyRGBMSpecular(std, rangeSqrt);
    }
  });
}

export async function loadV2Props(base: string, options: { lightmaps?: boolean } = {}): Promise<V2Props> {
  const group = new THREE.Group();
  group.name = 'v2Props';
  const props: LoadedProp[] = [];

  let manifest: unknown = null;
  try {
    const r = await fetch(`${base}manifest.json`);
    // The dev server answers a missing file with index.html; only JSON counts.
    if (r.ok && (r.headers.get('content-type') ?? '').includes('json')) manifest = await r.json();
  } catch {
    manifest = null;
  }

  // Geometry is EXT_meshopt_compression (scripts/meshopt-glb.mjs).
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  const entries = entriesOf(manifest);
  const loaded = await Promise.all(
    entries.map(async (entry) => {
      const gltf = await loader.loadAsync(base + entry.file);
      gltf.scene.name = `prop-file:${entry.name}`;
      restoreLitScale(gltf.scene);
      if (options.lightmaps) {
        await Promise.all(
          lightmapsOf(entry).map((lm) => applyPropLightmap(gltf.scene, base + lm.file, lm.rangeSqrt, lm.channel, lm.materials)),
        );
      }
      return { entry, root: gltf.scene } satisfies LoadedProp;
    }),
  );
  for (const p of loaded) {
    group.add(p.root);
    props.push(p);
  }
  group.updateMatrixWorld(true);

  return {
    group,
    props,
    node: (name) => findNodes(group, (n) => n === name)[0],
    nodes: (prefix) => findNodes(group, (n) => n.startsWith(prefix)),
    file: (key) => props.find((p) => p.entry.name === key || p.entry.file === key)?.root,
  };
}
