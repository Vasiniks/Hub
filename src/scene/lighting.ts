import * as THREE from 'three';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import type { RoomRefs } from './room';
import type { createExterior } from './exterior';

/**
 * The room exists in real time. The window in front of the desk is the main source of
 * daylight: direct sun through the glass plus sky light from the opening. Toward evening the
 * window loses importance and the lamp, monitors, and small LEDs take over. Keyframes describe
 * each hour; the current hour is interpolated continuously between them.
 */
interface LightKey {
  hour: number;
  zenith: string;
  horizon: string;
  ground: string;
  skyBright: number;
  voidColor: string;
  sun: number;
  sunColor: string;
  sunElevation: number;
  /** Radians: negative is left of the window, positive right. */
  sunAzimuth: number;
  window: number;
  windowColor: string;
  haze: number;
  hemi: number;
  hemiSky: string;
  hemiGround: string;
  lamp: number;
  monitor: number;
  led: number;
  glass: number;
  exposure: number;
  env: number;
  bloom: number;
  fog: number;
}

// prettier-ignore
const KEYS: LightKey[] = [
  { hour: 0,    zenith: '#05080d', horizon: '#101723', ground: '#07090c', skyBright: 0.6, voidColor: '#0b0f14', sun: 0,   sunColor: '#8aa0c8', sunElevation: 20, sunAzimuth: 0.9, window: 0.35, windowColor: '#41557a', haze: 0,    hemi: 0.03, hemiSky: '#1f2c42', hemiGround: '#0b0c0e', lamp: 9,   monitor: 5.5, led: 1,   glass: 0.34, exposure: 1.2,  env: 0.5,  bloom: 0.42, fog: 0.1 },
  { hour: 5,    zenith: '#0d1422', horizon: '#2a3346', ground: '#0b0d10', skyBright: 0.8, voidColor: '#121821', sun: 0,   sunColor: '#8aa0c8', sunElevation: 0, sunAzimuth: -1.1,  window: 0.9,  windowColor: '#6b7a96', haze: 0,    hemi: 0.06, hemiSky: '#34435a', hemiGround: '#0e0f11', lamp: 5.5, monitor: 5,   led: 1,   glass: 0.3,  exposure: 1.15, env: 0.55, bloom: 0.4,  fog: 0.09 },
  { hour: 6.5,  zenith: '#5d7596', horizon: '#e6a47a', ground: '#3a3430', skyBright: 1.3, voidColor: '#7b7f85', sun: 4, sunColor: '#ffb27a', sunElevation: 5, sunAzimuth: -1.0,  window: 2.2,    windowColor: '#e8c2a0', haze: 0.5,  hemi: 0.18, hemiSky: '#c9b8a6', hemiGround: '#4a4038', lamp: 1.5, monitor: 3.8, led: 0.8, glass: 0.14, exposure: 1.0,  env: 0.8,  bloom: 0.34, fog: 0.05 },
  { hour: 9,    zenith: '#4777b8', horizon: '#adc6de', ground: '#5a5a55', skyBright: 1.5, voidColor: '#aeb5bb', sun: 8.5, sunColor: '#ffe9cf', sunElevation: 18, sunAzimuth: -0.75, window: 4,    windowColor: '#c3d6ea', haze: 0.06, hemi: 0.2,  hemiSky: '#d6e2ec', hemiGround: '#5f5a54', lamp: 0,   monitor: 2.8, led: 0.5, glass: 0.07, exposure: 0.74, env: 0.85,  bloom: 0.1, fog: 0.032 },
  { hour: 13,   zenith: '#3f73b8', horizon: '#a9c4de', ground: '#6a6a64', skyBright: 1.5, voidColor: '#b7bec4', sun: 9.5, sunColor: '#ffefd6', sunElevation: 30, sunAzimuth: -0.42, window: 4.5,  windowColor: '#bcd3ea', haze: 0.04, hemi: 0.22, hemiSky: '#e3ebf2', hemiGround: '#6c6862', lamp: 0,   monitor: 2.6, led: 0.4, glass: 0.06, exposure: 0.72, env: 0.85,  bloom: 0.08, fog: 0.028 },
  { hour: 16,   zenith: '#4a79b6', horizon: '#bfc9d2', ground: '#6d665c', skyBright: 1.5, voidColor: '#b8b8b4', sun: 8.8, sunColor: '#ffe2bd', sunElevation: 18, sunAzimuth: 0.1, window: 4,    windowColor: '#c9d5e0', haze: 0.07,  hemi: 0.2,  hemiSky: '#dde2e6', hemiGround: '#6d665d', lamp: 0,   monitor: 2.8, led: 0.45, glass: 0.07, exposure: 0.74, env: 0.85, bloom: 0.1, fog: 0.032 },
  { hour: 18.5, zenith: '#58709a', horizon: '#f3a86c', ground: '#4d4038', skyBright: 1.9, voidColor: '#9c8778', sun: 7, sunColor: '#ff9a52', sunElevation: 7, sunAzimuth: 0.62,  window: 3.2,  windowColor: '#f2bf93', haze: 0.4,  hemi: 0.16, hemiSky: '#d9b89c', hemiGround: '#4e4038', lamp: 2,   monitor: 3.4, led: 0.7, glass: 0.1,  exposure: 0.9,  env: 0.85, bloom: 0.26, fog: 0.045 },
  { hour: 20,   zenith: '#1f2a40', horizon: '#7a5a60', ground: '#1a1818', skyBright: 1.1, voidColor: '#36404f', sun: 0.3, sunColor: '#ff6a3a', sunElevation: 0, sunAzimuth: 0.9,  window: 1.4,  windowColor: '#7d86a6', haze: 0.05,  hemi: 0.1,  hemiSky: '#4a5670', hemiGround: '#121214', lamp: 7,   monitor: 4.4, led: 0.9, glass: 0.22, exposure: 1.08, env: 0.6,  bloom: 0.36, fog: 0.08 },
  { hour: 22,   zenith: '#070b12', horizon: '#141c2a', ground: '#08090b', skyBright: 0.7, voidColor: '#101820', sun: 0,   sunColor: '#8aa0c8', sunElevation: 20, sunAzimuth: 0.9, window: 0.45, windowColor: '#4a5c80', haze: 0,    hemi: 0.04, hemiSky: '#26354d', hemiGround: '#0b0c0e', lamp: 8.5, monitor: 5.2, led: 1,   glass: 0.32, exposure: 1.18, env: 0.52, bloom: 0.4,  fog: 0.1 },
  { hour: 24,   zenith: '#05080d', horizon: '#101723', ground: '#07090c', skyBright: 0.6, voidColor: '#0b0f14', sun: 0,   sunColor: '#8aa0c8', sunElevation: 20, sunAzimuth: 0.9, window: 0.35, windowColor: '#41557a', haze: 0,    hemi: 0.03, hemiSky: '#1f2c42', hemiGround: '#0b0c0e', lamp: 9,   monitor: 5.5, led: 1,   glass: 0.34, exposure: 1.2,  env: 0.5,  bloom: 0.42, fog: 0.1 },
];

export interface LightState {
  hour: number;
  sky: THREE.Color;
  exposure: number;
  env: number;
  bloom: number;
  fog: number;
  monitor: number;
  /** Volumetric scattering colour × strength (zero when the sun is down). */
  scatter: THREE.Color;
}

const smooth = (t: number) => t * t * (3 - 2 * t);
const _a = new THREE.Color();
const _b = new THREE.Color();
const mix = (out: THREE.Color, a: string, b: string, t: number) => out.copy(_a.set(a)).lerp(_b.set(b), t);

export function createLighting(scene: THREE.Scene, room: RoomRefs, exterior: ReturnType<typeof createExterior>) {
  RectAreaLightUniformsLib.init();

  // Direct sun, entering through the window. Its shadow map is also what shapes the light shafts.
  const sun = new THREE.DirectionalLight('#ffffff', 0);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -2.6, right: 2.6, top: 2.6, bottom: -2.6, near: 0.5, far: 18 });
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  sun.shadow.radius = 3;
  sun.shadow.autoUpdate = false;
  sun.target.position.set(-0.05, 0.7, -0.25);
  scene.add(sun, sun.target);

  // Sky light from the whole opening: the soft, directional fill that makes window-facing surfaces glow.
  const sky = new THREE.RectAreaLight('#ffffff', 0, room.windowSize.x, room.windowSize.y);
  sky.position.copy(room.windowCenter).add(new THREE.Vector3(0, 0, 0.02));
  sky.lookAt(room.windowCenter.clone().add(new THREE.Vector3(0, -0.25, 1)));
  scene.add(sky);

  const hemi = new THREE.HemisphereLight('#ffffff', '#000000', 0);
  scene.add(hemi);

  // Always present, sometimes dark: toggling `visible` would recompile every shader at dusk.
  const lamp = new THREE.SpotLight('#ffd2a0', 0, 3.2, 0.75, 0.85, 2);
  lamp.castShadow = true;
  lamp.shadow.mapSize.set(1024, 1024);
  lamp.shadow.bias = -0.0006;
  lamp.shadow.normalBias = 0.01;
  lamp.shadow.radius = 4;
  lamp.shadow.autoUpdate = false;
  room.lampSocket.add(lamp);
  lamp.target = room.lampTarget;

  const mainGlow = new THREE.RectAreaLight('#cfe0f2', 0, 0.64, 0.36);
  room.mainScreen.add(mainGlow);
  mainGlow.position.set(0, 0, 0.004);
  mainGlow.rotation.y = Math.PI;
  const sideGlow = new THREE.RectAreaLight('#d6e2ee', 0, 0.52, 0.295);
  room.sideScreen.add(sideGlow);
  sideGlow.position.set(0, 0, 0.004);
  sideGlow.rotation.y = Math.PI;

  // Lift the glows off the screen meshes (same world transform). A pass that temporarily hides
  // meshes — the hover outline — would otherwise drop them from the light count, and the next
  // shadow redraw would compile a whole new shader variant mid-interaction.
  room.root.updateMatrixWorld(true);
  scene.attach(mainGlow);
  scene.attach(sideGlow);

  const underGlow = new THREE.PointLight('#e8eeff', 0, 0.9, 2);
  underGlow.position.set(0.45, 0.25, -0.55);
  scene.add(underGlow);

  const state: LightState = {
    hour: 0,
    sky: new THREE.Color(),
    exposure: 1,
    env: 1,
    bloom: 0.3,
    fog: 0.05,
    monitor: 3,
    scatter: new THREE.Color(),
  };
  const glassMat = room.windowGlass.material as THREE.MeshStandardMaterial;
  const lampMat = room.lampBulb.material as THREE.MeshStandardMaterial;
  const screenMats = [room.mainScreen.material, room.sideScreen.material] as THREE.MeshStandardMaterial[];
  const ledMats = room.pcLeds.map((l) => l.material as THREE.MeshStandardMaterial);

  const exteriorState = {
    zenith: new THREE.Color(),
    horizon: new THREE.Color(),
    ground: new THREE.Color(),
    sunDirection: new THREE.Vector3(),
    sunColor: new THREE.Color(),
    sunVisible: 0,
  };
  const toSun = new THREE.Vector3();
  const lastSunDir = new THREE.Vector3();
  let sunWasLit = false;
  let lampWasLit = false;

  function sample(hour: number) {
    const h = ((hour % 24) + 24) % 24;
    let i = 0;
    while (i < KEYS.length - 2 && KEYS[i + 1].hour <= h) i++;
    const a = KEYS[i];
    const b = KEYS[i + 1];
    return { a, b, t: smooth((h - a.hour) / (b.hour - a.hour)), h };
  }

  /** Shadow maps only re-render when something that affects them changes. */
  const shadowRequests = { sun: 0, lamp: 0 };
  function markShadowsDirty(which: 'sun' | 'lamp' | 'both' = 'both') {
    if (which !== 'lamp' && sun.intensity > 0) {
      sun.shadow.needsUpdate = true;
      shadowRequests.sun++;
    }
    if (which !== 'sun' && lamp.intensity > 0) {
      lamp.shadow.needsUpdate = true;
      shadowRequests.lamp++;
    }
  }

  function apply(hour: number) {
    const { a, b, t, h } = sample(hour);
    const n = (k: keyof LightKey) => THREE.MathUtils.lerp(a[k] as number, b[k] as number, t);

    state.hour = h;
    mix(state.sky, a.voidColor, b.voidColor, t);
    state.exposure = n('exposure');
    state.env = n('env');
    state.bloom = n('bloom');
    state.fog = n('fog');
    state.monitor = n('monitor');

    // The window faces away from the desk's back; the sun crosses it left to right through the day.
    const az = n('sunAzimuth');
    const el = THREE.MathUtils.degToRad(Math.max(n('sunElevation'), 3));
    toSun.set(Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el));
    sun.position.copy(sun.target.position).addScaledVector(toSun, 8);
    sun.intensity = n('sun');
    mix(sun.color, a.sunColor, b.sunColor, t);

    const sunLit = sun.intensity > 0.01;
    if ((sunLit && !sunWasLit) || (sunLit && lastSunDir.angleTo(toSun) > 0.0015)) {
      sun.shadow.needsUpdate = true;
      lastSunDir.copy(toSun);
    }
    sunWasLit = sunLit;

    sky.intensity = n('window');
    mix(sky.color, a.windowColor, b.windowColor, t);

    hemi.intensity = n('hemi');
    mix(hemi.color, a.hemiSky, b.hemiSky, t);
    mix(hemi.groundColor, a.hemiGround, b.hemiGround, t);

    const lampLevel = n('lamp');
    lamp.intensity = lampLevel;
    const lampLit = lampLevel > 0.01;
    if (lampLit && !lampWasLit) lamp.shadow.needsUpdate = true;
    lampWasLit = lampLit;
    lampMat.emissiveIntensity = 0.05 + lampLevel * 0.28;

    mainGlow.intensity = state.monitor * 1.1;
    sideGlow.intensity = state.monitor * 0.8;
    for (const mat of screenMats) mat.emissiveIntensity = 0.55 + state.monitor * 0.12;

    const led = n('led');
    underGlow.intensity = led * 0.12;
    for (const mat of ledMats) mat.emissiveIntensity = 1 + led * 2;

    // Glass: nearly invisible by day, a dark reflective pane at night.
    glassMat.opacity = n('glass');
    mix(glassMat.color, '#c9d4dc', '#1a2230', THREE.MathUtils.clamp((n('glass') - 0.06) / 0.28, 0, 1));

    const bright = n('skyBright');
    mix(exteriorState.zenith, a.zenith, b.zenith, t).multiplyScalar(bright);
    mix(exteriorState.horizon, a.horizon, b.horizon, t).multiplyScalar(bright);
    mix(exteriorState.ground, a.ground, b.ground, t).multiplyScalar(Math.min(bright, 1.4));
    exteriorState.sunDirection.copy(toSun);
    exteriorState.sunColor.copy(sun.color).multiplyScalar(Math.min(1, sun.intensity / 3));
    exteriorState.sunVisible = THREE.MathUtils.clamp(sun.intensity / 1.5, 0, 1);
    exterior.update(exteriorState);

    state.scatter.copy(sun.color).multiplyScalar(sun.intensity * n('haze') * 0.45);
    return state;
  }

  sun.shadow.needsUpdate = true;
  lamp.shadow.needsUpdate = true;

  return { apply, state, lamp, sun, markShadowsDirty, shadowRequests };
}
