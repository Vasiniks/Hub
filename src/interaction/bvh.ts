import * as THREE from 'three';

/**
 * Bounding-volume hierarchies for picking.
 *
 * three.js raycasts triangle by triangle. The room's static geometry is merged into a few large
 * meshes per material, each spanning most of the room, so their bounding spheres nearly always
 * pass and every hover test walked tens of thousands of triangles: 2 ms per ray, and a pick
 * can cast one ray under the pointer plus one per nearby attention dot to check it is not
 * hidden. A BVH per geometry turns each ray into a few dozen box tests.
 *
 * Built in idle time after the room is visible, a geometry at a time, so it never lengthens the
 * loading screen — and the library itself is loaded then too, so it is not in the startup
 * bundle. Until a mesh has its tree, its raycast uses the stock path: hover works from the
 * first frame either way.
 */

type IdleDeadline = { timeRemaining(): number };
const idle: (cb: (d: IdleDeadline) => void) => void =
  'requestIdleCallback' in window
    ? (cb) => (window as unknown as { requestIdleCallback(c: (d: IdleDeadline) => void): void }).requestIdleCallback(cb)
    : (cb) => window.setTimeout(() => cb({ timeRemaining: () => 8 }), 16);

/** Queue BVH construction for every mesh under `root`. Resolves when all trees exist. */
export async function buildPickingTrees(root: THREE.Object3D) {
  const { acceleratedRaycast, computeBoundsTree, disposeBoundsTree } = await import('three-mesh-bvh');
  THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;
  THREE.BufferGeometry.prototype.disposeBoundsTree = disposeBoundsTree;
  THREE.Mesh.prototype.raycast = acceleratedRaycast;

  const queue: THREE.BufferGeometry[] = [];
  const seen = new Set<THREE.BufferGeometry>();
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh || o.userData.ignoreRaycast) return;
    const geo = mesh.geometry;
    if (seen.has(geo) || !geo.attributes.position) return;
    seen.add(geo);
    queue.push(geo);
  });
  // Largest first: those are the ones that make stock raycasting slow.
  queue.sort((a, b) => b.attributes.position.count - a.attributes.position.count);
  const started = performance.now();
  return new Promise<{ geometries: number; ms: number }>((resolve) => {
    const work = (deadline: IdleDeadline) => {
      // Always build at least one per slice, so a busy page still makes progress.
      do {
        const geo = queue.shift();
        if (!geo) break;
        if (!geo.boundsTree) geo.computeBoundsTree();
      } while (queue.length && deadline.timeRemaining() > 4);
      if (queue.length) idle(work);
      else resolve({ geometries: seen.size, ms: Math.round(performance.now() - started) });
    };
    idle(work);
  });
}
