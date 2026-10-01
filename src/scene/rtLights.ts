import * as THREE from 'three';
import { createDiskLampShadow, installDiskLamp } from './lampDisk';

/**
 * The live half of the hybrid real-time room (`?rt`): the sunset sun and the desk lamp's disk light,
 * with shadow maps, on lit standard materials whose lightmaps hold only the bounce light (the full
 * Cycles bake minus these two lights' direct contribution — bakedRoom.ts / v2Props.ts).
 *
 * Both are read from the bake manifest (`lights.SUN_main`, `lights.LAMP_disk`, Blender units), so the
 * live light is the light the bake subtracted. Units: a Blender sun of strength S and a three
 * DirectionalLight of intensity S both give `albedo · S · cos / π`. A Lambertian disk of power P
 * has peak radiant intensity P / π, a SpotLight's intensity; lampDisk.ts gives it the disk's
 * 1/(d² + r²) falloff, its soft PCSS shadows and its widened highlight.
 *
 * Nothing in the room moves, so both shadow maps are drawn once (and again only on `invalidate`).
 */

interface BlenderLight {
  energy: number;
  color: [number, number, number];
  location: [number, number, number];
  direction: [number, number, number];
  angle_rad?: number;
  size?: number;
  spread?: number;
}

const fromBlender = ([x, y, z]: [number, number, number]) => new THREE.Vector3(x, z, -y);

/** Shader patches the disk lamp needs; must run before the first material compiles. */
export function installRtShading() {
  installDiskLamp();
}

export interface RtLights {
  sun: THREE.DirectionalLight;
  lamp: THREE.SpotLight;
  /** Before each frame's render: keeps the lamp's blocker map in step with its shadow map. */
  update(): void;
  /** Redraw both shadow maps (something that casts has moved). */
  invalidate(): void;
}

export function createRtLights(
  scene: THREE.Scene,
  renderer: THREE.WebGLRenderer,
  lights: { SUN_main: BlenderLight; LAMP_disk: BlenderLight },
): RtLights {
  // ---- Sun: sunset key through the window, shadowed by the shell ----------------------------
  const s = lights.SUN_main;
  const sun = new THREE.DirectionalLight(new THREE.Color(...s.color), s.energy);
  sun.name = 'rt:sun';
  const travel = fromBlender(s.direction).normalize();
  const centre = new THREE.Vector3(0, 1.1, -0.2);
  sun.position.copy(centre).addScaledVector(travel, -6);
  sun.target.position.copy(centre);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  const cam = sun.shadow.camera;
  // The room (≈4.3 × 3.1 m, 2.72 m high) seen along the sun: ±3 m holds every surface it reaches.
  cam.left = -3;
  cam.right = 3;
  cam.top = 3;
  cam.bottom = -3;
  cam.near = 1;
  cam.far = 12;
  sun.shadow.bias = -0.0002;
  sun.shadow.normalBias = 0.015;
  // Blender's sun is 1.2° wide: a slightly soft edge (PCF radius in texels, ≈1.5 mm each).
  sun.shadow.radius = Math.max(1, ((s.angle_rad ?? 0.02) / 0.02) * 2);
  sun.shadow.autoUpdate = false;
  sun.shadow.needsUpdate = true;
  scene.add(sun, sun.target);

  // ---- Lamp: the 191 mm diffuser disk under the head ------------------------------------------
  const l = lights.LAMP_disk;
  const spread = l.spread ?? Math.PI * 0.95;
  const lamp = new THREE.SpotLight(new THREE.Color(...l.color), l.energy / Math.PI, 0, Math.min(spread / 2, Math.PI * 0.49), 1, 2);
  lamp.name = 'rt:lamp';
  lamp.position.copy(fromBlender(l.location));
  lamp.target.position.copy(lamp.position).add(fromBlender(l.direction).normalize());
  lamp.castShadow = true;
  lamp.shadow.mapSize.set(2048, 2048);
  lamp.shadow.camera.near = 0.02;
  lamp.shadow.camera.far = 3;
  lamp.shadow.bias = -0.0003;
  lamp.shadow.normalBias = 0.004;
  lamp.shadow.autoUpdate = false;
  lamp.shadow.needsUpdate = true;
  scene.add(lamp, lamp.target);
  const disk = createDiskLampShadow(renderer, scene, lamp, (l.size ?? 0.191) / 2);

  return {
    sun,
    lamp,
    update() {
      disk?.update();
    },
    invalidate() {
      sun.shadow.needsUpdate = true;
      lamp.shadow.needsUpdate = true;
    },
  };
}
