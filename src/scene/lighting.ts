import * as THREE from 'three';
import type { RoomRefs } from './room';
import type { createExterior } from './exterior';

/**
 * The room exists in real time.
 *
 * By day the window in front of the desk is the dominant source: direct sun through the glass,
 * plus a large area light standing in for the whole bright opening. After dark that inverts —
 * the window goes quiet and the lamp, the monitor and the small LEDs carry the room (§11).
 *
 * Each keyframe describes one hour; the current hour is interpolated continuously between
 * them with a smoothstep, so nothing ever cuts from one preset to another.
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
  /** Air density for the lamp's cone specifically. */
  lampHaze: number;
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
  { hour: 0,    zenith: '#04070c', horizon: '#0c121c', ground: '#06080a', skyBright: 0.55, voidColor: '#080b10', sun: 0,    sunColor: '#8aa0c8', sunElevation: 20, sunAzimuth: 0.9,   window: 0.3,  windowColor: '#3a4f7c', lampHaze: 0.108, haze: 0,    hemi: 0.075, hemiSky: '#22304d', hemiGround: '#0b0d10', lamp: 3.0, monitor: 2.9, led: 1.3,  glass: 0.36, exposure: 1.0,  env: 0.86,  bloom: 0.2, fog: 0.085 },
  { hour: 5,    zenith: '#0b1220', horizon: '#232c3e', ground: '#0a0c0f', skyBright: 0.75, voidColor: '#10161f', sun: 0,    sunColor: '#8aa0c8', sunElevation: 0,  sunAzimuth: -1.1,  window: 0.55, windowColor: '#5d6c88', lampHaze: 0.092, haze: 0,    hemi: 0.09,  hemiSky: '#33445e', hemiGround: '#0d0e10', lamp: 2.4, monitor: 2.8, led: 1.2,  glass: 0.3,  exposure: 0.99, env: 0.86, bloom: 0.19, fog: 0.08 },
  { hour: 6.5,  zenith: '#5d7596', horizon: '#e6a47a', ground: '#3a3430', skyBright: 1.3,  voidColor: '#7b7f85', sun: 6.5,  sunColor: '#ffb27a', sunElevation: 5,  sunAzimuth: -1.0,  window: 1.5,  windowColor: '#e8c2a0', lampHaze: 0.056, haze: 0.42,  hemi: 0.10,  hemiSky: '#b8a795', hemiGround: '#3a322c', lamp: 1.0, monitor: 2.2, led: 0.8,  glass: 0.14, exposure: 0.78, env: 0.7,  bloom: 0.16, fog: 0.05 },
  { hour: 9,    zenith: '#376cb4', horizon: '#a1bfda', ground: '#5a5a55', skyBright: 1.12, voidColor: '#a7aeb5', sun: 13.0, sunColor: '#ffe9cf', sunElevation: 18, sunAzimuth: -0.75, window: 2.5,  windowColor: '#c3d6ea', lampHaze: 0.0, haze: 0.09, hemi: 0.10,  hemiSky: '#c6d6e6', hemiGround: '#4e4a45', lamp: 0,   monitor: 2.0, led: 0.4,  glass: 0.07, exposure: 0.5,  env: 0.62, bloom: 0.07, fog: 0.03 },
  { hour: 13,   zenith: '#2f66b4', horizon: '#9dbcda', ground: '#6a6a64', skyBright: 1.12, voidColor: '#b0b7bd', sun: 13.2, sunColor: '#ffefd6', sunElevation: 31, sunAzimuth: -0.42, window: 2.7,  windowColor: '#bcd3ea', lampHaze: 0.0, haze: 0.055, hemi: 0.105, hemiSky: '#d2e0ee', hemiGround: '#575249', lamp: 0,   monitor: 2.0, led: 0.35, glass: 0.06, exposure: 0.47, env: 0.6,  bloom: 0.06, fog: 0.027 },
  { hour: 16,   zenith: '#3b6eb2', horizon: '#b3c0cc', ground: '#6d665c', skyBright: 1.12, voidColor: '#b1b1ae', sun: 13.0, sunColor: '#ffe2bd', sunElevation: 18, sunAzimuth: 0.1,   window: 2.5,  windowColor: '#c9d5e0', lampHaze: 0.0, haze: 0.10, hemi: 0.10,  hemiSky: '#ccd4da', hemiGround: '#5a544c', lamp: 0,   monitor: 2.0, led: 0.4,  glass: 0.07, exposure: 0.5,  env: 0.62, bloom: 0.07, fog: 0.031 },
  { hour: 18.5, zenith: '#58709a', horizon: '#f3a86c', ground: '#4d4038', skyBright: 1.85, voidColor: '#9c8778', sun: 11.0, sunColor: '#ff9552', sunElevation: 7,  sunAzimuth: 0.62,  window: 2.0,  windowColor: '#f2bf93', lampHaze: 0.069, haze: 0.34,  hemi: 0.095, hemiSky: '#c9a88c', hemiGround: '#3c322c', lamp: 1.5, monitor: 2.1, led: 0.6,  glass: 0.1,  exposure: 0.66, env: 0.76, bloom: 0.15, fog: 0.044 },
  { hour: 20,   zenith: '#161f30', horizon: '#5c464f', ground: '#141313', skyBright: 0.95, voidColor: '#252d3a', sun: 0.25, sunColor: '#ff6a3a', sunElevation: 0,  sunAzimuth: 0.9,   window: 0.7,  windowColor: '#6b7694', lampHaze: 0.095, haze: 0.05, hemi: 0.095, hemiSky: '#44526f', hemiGround: '#121214', lamp: 2.5, monitor: 2.6, led: 1.05, glass: 0.22, exposure: 0.97, env: 0.84, bloom: 0.19, fog: 0.07 },
  { hour: 21.5, zenith: '#080d16', horizon: '#161e2c', ground: '#090a0c', skyBright: 0.7,  voidColor: '#0d1119', sun: 0,    sunColor: '#8aa0c8', sunElevation: 20, sunAzimuth: 0.9,   window: 0.4,  windowColor: '#42588a', lampHaze: 0.105, haze: 0,    hemi: 0.08,  hemiSky: '#263654', hemiGround: '#0b0d10', lamp: 2.9, monitor: 2.9, led: 1.3,  glass: 0.32, exposure: 1.0,  env: 0.88, bloom: 0.2, fog: 0.082 },
  { hour: 24,   zenith: '#04070c', horizon: '#0c121c', ground: '#06080a', skyBright: 0.55, voidColor: '#080b10', sun: 0,    sunColor: '#8aa0c8', sunElevation: 20, sunAzimuth: 0.9,   window: 0.3,  windowColor: '#3a4f7c', lampHaze: 0.108, haze: 0,    hemi: 0.075, hemiSky: '#22304d', hemiGround: '#0b0d10', lamp: 3.0, monitor: 2.9, led: 1.3,  glass: 0.36, exposure: 1.0,  env: 0.86,  bloom: 0.2, fog: 0.085 },
];

/** Lamp cone half-angle. Shared with the dust so the motes light exactly where the beam is. */
export const LAMP_ANGLE = 0.52;
/** See the note where lampScatter is computed. */
const LAMP_SCATTER_GAIN = 12;

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

const smooth = (t: number) => t * t * (3 - 2 * t);
const _a = new THREE.Color();
const _b = new THREE.Color();
const mix = (out: THREE.Color, a: string, b: string, t: number) => out.copy(_a.set(a)).lerp(_b.set(b), t);

export function createLighting(scene: THREE.Scene, room: RoomRefs, exterior: ReturnType<typeof createExterior>) {
  // Rect-area light lookup tables are installed by loadLtcTables() before this runs.

  // Direct sun through the window. Its shadow map also shapes the light shafts.
  const sun = new THREE.DirectionalLight('#ffffff', 0);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -2.8, right: 2.8, top: 2.8, bottom: -2.8, near: 0.5, far: 18 });
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  sun.shadow.radius = 3;
  sun.shadow.autoUpdate = false;
  sun.target.position.set(-0.05, 0.7, -0.4);
  scene.add(sun, sun.target);

  // §8: the whole opening as one soft source. This is what makes the white desk glow toward
  // the window and fall away toward the visitor, which is most of the daylight read.
  const sky = new THREE.RectAreaLight('#ffffff', 0, room.windowSize.x, room.windowSize.y);
  sky.position.copy(room.windowCenter).add(new THREE.Vector3(0, 0, 0.02));
  sky.lookAt(room.windowCenter.clone().add(new THREE.Vector3(0, -0.3, 1)));
  scene.add(sky);

  const hemi = new THREE.HemisphereLight('#ffffff', '#000000', 0);
  scene.add(hemi);

  // Always present, sometimes dark: toggling `visible` would recompile every shader at dusk.
  const lamp = new THREE.SpotLight('#ffd2a0', 0, 3.0, LAMP_ANGLE, 0.85, 2);
  lamp.castShadow = true;
  lamp.shadow.mapSize.set(1024, 1024);
  lamp.shadow.bias = -0.0006;
  lamp.shadow.normalBias = 0.01;
  lamp.shadow.radius = 4;
  lamp.shadow.autoUpdate = false;
  room.lampSocket.add(lamp);
  // THREE.Light's constructor seeds position with the default up vector, which would hang the
  // spot a metre above its socket and throw the beam past the desk entirely.
  lamp.position.set(0, 0, 0);
  lamp.target = room.lampTarget;

  // §3: the monitor lights the room rather than just glowing. An area light the size of the
  // panel puts real screen light on the desk, the MacBook lid and the keyboard.
  const screenGlow = new THREE.RectAreaLight('#cfe0f2', 0, room.screenSize.x, room.screenSize.y);
  room.screen.add(screenGlow);
  screenGlow.position.set(0, 0, 0.004);
  screenGlow.rotation.y = Math.PI;
  // Lift it off the screen mesh, keeping the same world transform: a pass that temporarily
  // hides meshes (the hover outline) would otherwise drop it from the light count, and the
  // next shadow redraw would compile a fresh shader variant mid-interaction.
  room.root.updateMatrixWorld(true);
  scene.attach(screenGlow);

  // Accent tier (§10): the cool spill the powered electronics throw onto the desk around them.
  // A rect light rather than a point — a point source this close to a smooth surface collapses
  // into a pinpoint specular, which is what the stray highlight in the window glass was.
  const underGlow = new THREE.RectAreaLight('#cfe0ff', 0, 0.22, 0.12);
  underGlow.position.set(0.42, 0.79, -0.9);
  underGlow.lookAt(0.42, 0.7, -0.6);
  scene.add(underGlow);

  const state: LightState = {
    hour: 0,
    sky: new THREE.Color(),
    exposure: 1,
    env: 1,
    bloom: 0.3,
    fog: 0.05,
    monitor: 3,
    lamp: 0,
    scatter: new THREE.Color(),
    lampScatter: new THREE.Color(),
  };
  const glassMat = room.windowGlass.material as THREE.MeshStandardMaterial;
  const discMat = room.lampDisc.material as THREE.MeshStandardMaterial;
  const screenMat = room.screen.material as THREE.MeshStandardMaterial;
  const ledMats = room.leds.map((l) => l.material as THREE.MeshStandardMaterial);

  const exteriorState = {
    zenith: new THREE.Color(),
    horizon: new THREE.Color(),
    ground: new THREE.Color(),
    sunDirection: new THREE.Vector3(),
    sunColor: new THREE.Color(),
    sunVisible: 0,
    night: 0,
  };
  const toSun = new THREE.Vector3();
  const lastSunDir = new THREE.Vector3();
  /** Small environmental reaction: opening something brightens the indicator LEDs briefly. */
  let activity = 0;
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

    // The sun crosses the window left to right through the day.
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
    state.lamp = lampLevel;
    const lampLit = lampLevel > 0.01;
    if (lampLit && !lampWasLit) lamp.shadow.needsUpdate = true;
    lampWasLit = lampLit;
    // Just over the bloom threshold when lit, so the shade carries a soft halo rather than
    // reading as a flat cream disc.
    discMat.emissiveIntensity = 0.03 + lampLevel * 0.45;

    screenGlow.intensity = state.monitor * 1.15;
    screenMat.emissiveIntensity = 0.5 + state.monitor * 0.12;

    const led = n('led') * (1 + activity * 0.9);
    room.shelf.setLevel(led);
    underGlow.intensity = led * 0.5;
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
    // Fully lit windows only once the sky itself has gone; they fade out through dusk.
    exteriorState.night = THREE.MathUtils.clamp(1 - n('skyBright') / 0.95, 0, 1);
    exterior.update(exteriorState);

    state.scatter.copy(sun.color).multiplyScalar(sun.intensity * n('haze') * 0.42);
    // §11: the beam is only worth seeing when the room is dark enough for it to register.
    // The gain is explicit: a local source falls off as 1/d², so its per-step contribution
    // along a ray is a small fraction of the sun's, which accumulates unattenuated. This
    // brings the two into the same range so `lampHaze` reads as air density in both.
    state.lampScatter.copy(lamp.color).multiplyScalar(lampLevel * n('lampHaze') * LAMP_SCATTER_GAIN);
    return state;
  }

  sun.shadow.needsUpdate = true;
  lamp.shadow.needsUpdate = true;

  /**
   * Shadow depth shaders compile per material, but only the first time a mesh using that
   * material is actually rendered into a given light's map. Objects that drift into a light's
   * frustum later — the chair rolling under the lamp, a textured surface entering the sun's box
   * at dawn — were paying 400–700 ms for that compile mid-interaction.
   *
   * Called around the warm-up render: light both lights and open their frusta wide enough to
   * take in the whole room, so every depth variant is built while the loading bar is still up.
   * Returns the restore function.
   */
  function warmShadows() {
    const saved = {
      sun: sun.intensity,
      lamp: lamp.intensity,
      angle: lamp.angle,
      distance: lamp.distance,
      box: { left: sun.shadow.camera.left, right: sun.shadow.camera.right, top: sun.shadow.camera.top, bottom: sun.shadow.camera.bottom, far: sun.shadow.camera.far },
    };
    sun.intensity = Math.max(saved.sun, 1);
    lamp.intensity = Math.max(saved.lamp, 1);
    lamp.angle = Math.PI / 2.6;
    lamp.distance = 14;
    Object.assign(sun.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, far: 30 });
    sun.shadow.camera.updateProjectionMatrix();
    sun.shadow.needsUpdate = true;
    lamp.shadow.needsUpdate = true;
    return () => {
      sun.intensity = saved.sun;
      lamp.intensity = saved.lamp;
      lamp.angle = saved.angle;
      lamp.distance = saved.distance;
      Object.assign(sun.shadow.camera, saved.box);
      sun.shadow.camera.updateProjectionMatrix();
      sun.shadow.needsUpdate = true;
      lamp.shadow.needsUpdate = true;
    };
  }

  return {
    apply,
    state,
    lamp,
    sun,
    markShadowsDirty,
    warmShadows,
    shadowRequests,
    setActivity(v: number) {
      activity = v;
    },
  };
}
