import * as THREE from 'three';
import { createLorenzScreen } from './lorenz';

/**
 * The few things in the baked room that move on their own, found by name in the props export
 * (`public/assets/v2/props/`). Each one switches on only if its node is there, so the room runs
 * the same before and after a prop lands.
 *
 * - `Robot_rsl_lens`: the robot's status light pulses slowly — emission 0 → 7 on a 4 s sine, as
 *   the driver in room.blend does (blender/scene/WEB_TODO.md). Reduced motion holds it at the
 *   average, which is also what the bake assumed.
 * - `mon_screen`: the monitor runs the Lorenz attractor (lorenz.ts), as it did in the default
 *   room — the same figure the loader shows. It repaints only while the screen is on camera.
 */

const RSL_PERIOD = 4;
const RSL_PEAK = 7;

function materialsNamed(root: THREE.Object3D, test: (name: string) => boolean) {
  const found: { mesh: THREE.Mesh; material: THREE.MeshStandardMaterial }[] = [];
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const m of mats) {
      if ((test(m.name) || test(mesh.name)) && (m as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
        found.push({ mesh, material: m as THREE.MeshStandardMaterial });
      }
    }
  });
  return found;
}

/**
 * UVs across a flat screen, u to the right and v up as its viewer sees it. The export prunes
 * texture coordinates from materials that carry no texture, so the screen arrives without any;
 * they are rebuilt from the face itself: its normal (turned toward `viewer`), u = up × normal,
 * v = normal × u, each normalised over the face's extent.
 */
function planarScreenUVs(mesh: THREE.Mesh, viewer: THREE.Vector3) {
  const geo = mesh.geometry;
  if (geo.getAttribute('uv')) return;
  const pos = geo.getAttribute('position');
  const world = (i: number, v: THREE.Vector3) => v.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld);
  const a = world(0, new THREE.Vector3());
  const b = world(1, new THREE.Vector3());
  const c = world(2, new THREE.Vector3());
  const normal = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a)).normalize();
  if (normal.dot(new THREE.Vector3().subVectors(viewer, a)) < 0) normal.negate();
  const u = new THREE.Vector3(0, 1, 0).cross(normal).normalize();
  const v = new THREE.Vector3().crossVectors(normal, u);
  const p = new THREE.Vector3();
  const us = new Float32Array(pos.count);
  const vs = new Float32Array(pos.count);
  for (let i = 0; i < pos.count; i++) {
    world(i, p);
    us[i] = p.dot(u);
    vs[i] = p.dot(v);
  }
  const span = (xs: Float32Array) => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const x of xs) {
      lo = Math.min(lo, x);
      hi = Math.max(hi, x);
    }
    return [lo, hi - lo || 1];
  };
  const [u0, uw] = span(us);
  const [v0, vh] = span(vs);
  const uv = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    uv[i * 2] = (us[i] - u0) / uw;
    uv[i * 2 + 1] = (vs[i] - v0) / vh;
  }
  geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

export function createV2Animations(props: THREE.Object3D, reducedMotion: boolean, viewer: THREE.Vector3) {
  const rsl = materialsNamed(props, (n) => n.startsWith('Robot_rsl_lens')).map(({ material }) => {
    // The export carries the lens colour; a lens exported without one gets the CAD's orange.
    if (material.emissive.getHex() === 0) material.emissive.set('#ff6a1a');
    return material;
  });

  const screens = materialsNamed(props, (n) => n.startsWith('mon_screen'));
  const lorenz = screens.length ? createLorenzScreen() : null;
  const screenSphere = new THREE.Sphere();
  if (lorenz) {
    for (const { mesh, material } of screens) {
      planarScreenUVs(mesh, viewer);
      material.emissive.set('#ffffff');
      material.emissiveMap = lorenz.texture;
      material.emissiveIntensity = 1;
      material.needsUpdate = true;
      mesh.geometry.computeBoundingSphere();
    }
    const { mesh } = screens[0];
    screenSphere.copy(mesh.geometry.boundingSphere!).applyMatrix4(mesh.matrixWorld);
  }

  const frustum = new THREE.Frustum();
  const viewProj = new THREE.Matrix4();

  return {
    /** Debug: what was found. */
    info: () => ({ rsl: rsl.length, screens: screens.map(({ mesh }) => mesh.name), screenSphere: screenSphere.center.toArray().concat(screenSphere.radius) }),
    update(dt: number, time: number, camera: THREE.Camera, activity: number) {
      if (rsl.length) {
        const level = reducedMotion ? RSL_PEAK / 2 : RSL_PEAK * (0.5 - 0.5 * Math.cos((2 * Math.PI * time) / RSL_PERIOD));
        for (const m of rsl) m.emissiveIntensity = level;
      }
      if (lorenz) {
        viewProj.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
        frustum.setFromProjectionMatrix(viewProj);
        lorenz.update(dt, time, frustum.intersectsSphere(screenSphere), activity);
      }
    },
  };
}
