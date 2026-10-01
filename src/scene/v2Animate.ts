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

export function createV2Animations(props: THREE.Object3D, reducedMotion: boolean) {
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
