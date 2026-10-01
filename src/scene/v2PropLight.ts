import * as THREE from 'three';

/**
 * Live light for the v2 props — and only for them.
 *
 * The baked room is MeshBasicMaterial (bakedRoom.ts): no direct-light loops, no IBL, so the
 * lights below cannot reach it and nothing is lit twice. The props are PBR and get three things:
 *
 * - the room itself as image-based light: the renderer's environment capture (renderer.ts
 *   `captureEnvironmentNow`) records the baked room's radiance, which holds the sun, sky, lamp
 *   and every bounce — so a prop's ambient and reflections come from the same bake as the walls;
 * - the sunset sun (`SUN_main` in room.blend), shadowed by the shell so it only lands where the
 *   window lets it in;
 * - the desk lamp's disk light (`LAMP_disk`), as a spot whose falloff approximates the disk's
 *   Lambertian lobe.
 *
 * Values are read from room.blend (Blender Z-up; a Blender point (x, y, z) is three (x, z, -y)).
 * Units: a Blender sun of strength S and a three DirectionalLight of
 * intensity S both give `albedo * S * cos / PI` — 1:1. A Lambertian disk of power P has peak
 * radiant intensity P / PI, which is what a three SpotLight's intensity is (decay 2).
 */

const fromBlender = (x: number, y: number, z: number) => new THREE.Vector3(x, z, -y);

/** SUN_main: strength 4, colour (1, 0.301, 0.084), travelling (-0.635, -0.757, -0.156). */
const SUN = { strength: 4, color: new THREE.Color(1, 0.301, 0.084), travel: fromBlender(-0.635, -0.757, -0.156) };
/** LAMP_disk: 17.95 W disk, Ø0.191 m, colour (1, 0.86, 0.68), at (-0.532, 0.800, 1.130), aimed (-0.173, 0.206, -0.963). */
const LAMP = {
  power: 17.949,
  color: new THREE.Color(1, 0.86, 0.68),
  position: fromBlender(-0.532, 0.8, 1.13),
  aim: fromBlender(-0.173, 0.206, -0.963),
};

export interface V2PropLight {
  sun: THREE.DirectionalLight;
  lamp: THREE.SpotLight;
  /** Re-record the room as image-based light with the props hidden (they must not light themselves). */
  captureWithoutProps(capture: () => void): void;
}

export function createV2PropLight(scene: THREE.Scene, shell: THREE.Object3D | undefined, propsRoot: THREE.Object3D): V2PropLight {
  const sun = new THREE.DirectionalLight(SUN.color, SUN.strength);
  sun.name = 'v2:sun';
  // The light sits outside the window, looking back along its travel at the room's centre.
  const centre = new THREE.Vector3(0, 1.1, -0.2);
  sun.position.copy(centre).addScaledVector(SUN.travel.clone().normalize(), -6);
  sun.target.position.copy(centre);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const cam = sun.shadow.camera;
  cam.left = -3;
  cam.right = 3;
  cam.top = 3;
  cam.bottom = -3;
  cam.near = 2;
  cam.far = 12;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  scene.add(sun, sun.target);

  const lamp = new THREE.SpotLight(LAMP.color, LAMP.power / Math.PI, 0, Math.PI * 0.48, 1, 2);
  lamp.name = 'v2:lamp';
  lamp.position.copy(LAMP.position);
  lamp.target.position.copy(LAMP.position).add(LAMP.aim.clone().normalize());
  scene.add(lamp, lamp.target);

  // Shadow casters: the shell walls hold the sun to the window opening; the props shadow each
  // other. Baked surfaces never receive — their shadows are already in the lightmap.
  shell?.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) o.castShadow = true;
  });
  propsRoot.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    m.castShadow = true;
    m.receiveShadow = true;
  });
  // Everything that casts is static: draw the shadow map once, not every frame.
  sun.shadow.autoUpdate = false;
  sun.shadow.needsUpdate = true;

  return {
    sun,
    lamp,
    captureWithoutProps(capture) {
      const was = propsRoot.visible;
      propsRoot.visible = false;
      capture();
      propsRoot.visible = was;
    },
  };
}
