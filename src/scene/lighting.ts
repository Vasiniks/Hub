import * as THREE from 'three';

/**
 * What the renderer still takes from the old room's lighting rig: the lamp diffuser's radius
 * (lampDisk.ts) and the shape of a light state (`applyLight`). The time-of-day keys and
 * `createLighting` went with the old room; the baked room carries its light in its lightmaps.
 */

/** Radius of the lamp's diffuser: it lights as a disk this size (see lampDisk.ts). */
export const LAMP_DISK_RADIUS = 0.04;
export interface LightState {
  hour: number;
  sky: THREE.Color;
  exposure: number;
  env: number;
  bloom: number;
  fog: number;
  monitor: number;
  lamp: number;
  /** Volumetric scattering colour × strength (zero when the sun is down). */
  scatter: THREE.Color;
  /** The same, for the lamp's beam: strongest at night, off in daylight. */
  lampScatter: THREE.Color;
}

