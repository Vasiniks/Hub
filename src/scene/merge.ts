import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const KEEP = new Set(['position', 'normal', 'uv']);

interface Bucket {
  material: THREE.Material;
  cast: boolean;
  receive: boolean;
  /** mergeGeometries needs every input to agree on this, so it is part of the bucket key. */
  indexed: boolean;
  parts: THREE.BufferGeometry[];
  meshes: THREE.Mesh[];
}

/**
 * Collapse static meshes that share a material and shadow flags into one draw call each.
 *
 * Bevelled boxes come from RoundedBoxGeometry, which discards its index — so index-ness is
 * part of the bucket key rather than a reason to skip a mesh. Requiring an index here quietly
 * excluded almost every object in the room from merging.
 * Every pass benefits: main render, AO normals, both shadow maps, and environment capture.
 * Subtrees marked `userData.dynamic` keep their own transform and are merged internally.
 * Returns the number of meshes before and after.
 */
export function mergeStatic(root: THREE.Object3D): { before: number; after: number } {
  root.updateMatrixWorld(true);
  const toRoot = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const buckets = new Map<string, Bucket>();
  const dynamicRoots: THREE.Object3D[] = [];
  let before = 0;

  const visit = (o: THREE.Object3D) => {
    if (o !== root && o.userData.dynamic) {
      dynamicRoots.push(o);
      return;
    }
    const mesh = o as THREE.Mesh;
    if (mesh.isMesh) before++;
    const mergeable =
      o !== root &&
      mesh.isMesh &&
      !(mesh as THREE.InstancedMesh).isInstancedMesh &&
      !mesh.userData.noMerge &&
      !Array.isArray(mesh.material) &&
      mesh.geometry.getAttribute('position') !== undefined &&
      mesh.geometry.getAttribute('normal') !== undefined;
    if (mergeable) {
      const material = mesh.material as THREE.Material;
      const indexed = mesh.geometry.index !== null;
      const key = `${material.uuid}|${mesh.castShadow}|${mesh.receiveShadow}|${indexed}`;
      let bucket = buckets.get(key);
      if (!bucket) {
        buckets.set(key, (bucket = { material, cast: mesh.castShadow, receive: mesh.receiveShadow, indexed, parts: [], meshes: [] }));
      }
      const part = mesh.geometry.clone();
      for (const name of Object.keys(part.attributes)) if (!KEEP.has(name)) part.deleteAttribute(name);
      // Models authored without texture coordinates (most Tier 2 props) still merge: a zero UV
      // is exactly what WebGL feeds a shader for a missing attribute, so nothing renders
      // differently — but without this, every bin, board and cable part was its own draw call.
      if (!part.getAttribute('uv')) part.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(part.attributes.position.count * 2), 2));
      part.clearGroups();
      part.applyMatrix4(new THREE.Matrix4().multiplyMatrices(toRoot, mesh.matrixWorld));
      bucket.parts.push(part);
      bucket.meshes.push(mesh);
    }
    for (const child of [...o.children]) visit(child);
  };
  visit(root);

  const removed = new Set<THREE.Mesh>();
  for (const bucket of buckets.values()) {
    if (bucket.meshes.length < 2) {
      bucket.parts.forEach((p) => p.dispose());
      continue;
    }
    const merged = mergeGeometries(bucket.parts, false);
    bucket.parts.forEach((p) => p.dispose());
    if (!merged) continue;
    merged.computeBoundingSphere();
    const combined = new THREE.Mesh(merged, bucket.material);
    combined.castShadow = bucket.cast;
    combined.receiveShadow = bucket.receive;
    root.add(combined);
    bucket.meshes.forEach((m) => removed.add(m));
  }

  // Anything parented under a merged mesh keeps its world transform on the root.
  for (const mesh of removed) {
    for (const child of [...mesh.children]) if (!removed.has(child as THREE.Mesh)) root.attach(child);
  }
  for (const mesh of removed) mesh.removeFromParent();

  let after = 0;
  root.traverse((o) => {
    if ((o as THREE.Mesh).isMesh && !dynamicRoots.some((d) => d === o || isDescendant(o, d))) after++;
  });
  for (const d of dynamicRoots) {
    const r = mergeStatic(d);
    before += r.before;
    after += r.after;
  }
  return { before, after };
}

function isDescendant(o: THREE.Object3D, ancestor: THREE.Object3D) {
  for (let p = o.parent; p; p = p.parent) if (p === ancestor) return true;
  return false;
}
