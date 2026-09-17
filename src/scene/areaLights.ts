import * as THREE from 'three';
import { shareUniform } from './sharedUniforms';

/**
 * Rect-area light specular, moved to where it is cheap.
 *
 * three evaluates every RectAreaLight for every pixel: a polygon integral for diffuse and another
 * (plus two LUT fetches) for specular. The room has four — the window, the monitor's glow, the
 * shelf strip and the spill under the electronics — and the bench measured them at ~4 ms of a
 * ~5.5 ms scene render, the specular half of it ~2 ms.
 *
 * Diffuse stays exact per pixel (the desk's glow toward the window is most of the daylight read),
 * but skips lights too small and far to register. Specular splits by what can stand in for it:
 * - the window is large and far, so its reflection is precomputed into the environment probe;
 * - small emitters keep the integral, but only within reach, where the probe would be wrong.
 * `?arealights=pixel` restores three's stock path for comparison.
 */

/** False under `?arealights=pixel`: three's stock per-pixel path, for A/B comparison. */
export const diffuseOnlyAreaLights = new URLSearchParams(location.search).get('arealights') !== 'pixel';

/** Emitters at least this large (m²) reflect through the environment probe instead of the integral. */
export const PROBE_EMITTER_AREA = 0.5;
/** Within this distance (m) of a smaller emitter, its specular is still integrated per pixel. */
const NEAR_SPECULAR_RANGE = 0.7;

/**
 * Restrict the per-pixel LTC specular integral (two LUT fetches plus a polygon integral) to where a
 * probe cannot stand in for it: pixels close to a small emitter. The window's reflection comes from
 * the environment probe (see `createReflectionEmitters`) — it is large and far, the case a probe
 * handles — while the monitor 30 cm from the laptop lid is exactly the near field a probe centred
 * in the room gets wrong, and those pixels are few.
 */
export function installDiffuseOnlyAreaLights() {
  if (!diffuseOnlyAreaLights) return;
  const chunks = THREE.ShaderChunk as unknown as Record<string, string>;
  const line = 'reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );';
  const src = chunks.lights_physical_pars_fragment;
  if (!src.includes(line)) throw new Error('diffuse-only area lights: RE_Direct_RectArea_Physical changed');
  const start = src.indexOf('vec2 uv = LTC_Uv( normal, viewDir, roughness );');
  const end = src.indexOf(line) + line.length;
  // Skip lights that cannot register here. A rectangle's irradiance is bounded by
  // area × radiance / distance², so beyond the point where that bound falls below ~1/2000 of scene
  // white the integral is invisible — and the room's small emitters (shelf strip, desk spill,
  // monitor glow) are that small almost everywhere on screen.
  const cull = `vec3 toLight = lightPos - position;
		float bound = 4.0 * length( halfWidth ) * length( halfHeight ) * max( max( lightColor.r, lightColor.g ), lightColor.b ) / max( dot( toLight, toLight ), 1e-6 );
		if ( bound < 0.0005 ) return;
`;
  const near = `vec3 nearOffset = lightPos - position;
		if ( 4.0 * length( halfWidth ) * length( halfHeight ) < ${PROBE_EMITTER_AREA.toFixed(3)} && dot( nearOffset, nearOffset ) < ${(NEAR_SPECULAR_RANGE ** 2).toFixed(3)} ) {
		${src.slice(start, end)}
		}
`;
  chunks.lights_physical_pars_fragment = src.slice(0, start) + cull + near + src.slice(end);
}

/**
 * The texture indirect diffuse is read from, when it differs from `scene.environment`.
 *
 * The probe that carries the window's specular (a pane at the light's radiance, see below)
 * must not also light the room a second time: the rect light already integrates that diffuse
 * exactly, with falloff the probe cannot have. So the capture is filtered twice — once without the
 * pane, for irradiance, and once with it, for reflections — and physical materials take their
 * irradiance from the first. Same fetch count as before; one more bound texture.
 */
export const environmentIrradiance: { value: THREE.Texture | null } = { value: null };

export function installSplitEnvironment() {
  if (!diffuseOnlyAreaLights) return;
  const chunks = THREE.ShaderChunk as unknown as Record<string, string>;
  const sampleLine = 'vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );';
  const src = chunks.envmap_physical_pars_fragment;
  if (!src.includes(sampleLine)) throw new Error('split environment: getIBLIrradiance changed');
  chunks.envmap_physical_pars_fragment = src
    .replace('#ifdef USE_ENVMAP', '#ifdef USE_ENVMAP\n\tuniform sampler2D envMapIrradiance;')
    .replace(sampleLine, sampleLine.replace('( envMap,', '( envMapIrradiance,'));
  shareUniform('envMapIrradiance', environmentIrradiance);
}

/**
 * Emitters only the environment capture draws: a pane per large rect light, at its radiance.
 *
 * With the LTC specular gone, this is where the lights' reflections come from. Each pane is drawn
 * over the captured cube without depth testing — the integral never knew about occluders either —
 * and faces the way its light shines, so the shelf strip is not seen from above.
 */
export function createReflectionEmitters(scene: THREE.Scene, layer: number) {
  const pairs: { light: THREE.RectAreaLight; pane: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> }[] = [];
  if (!diffuseOnlyAreaLights) return null;
  scene.traverse((o) => {
    const light = o as THREE.RectAreaLight;
    if (!light.isRectAreaLight || light.width * light.height < PROBE_EMITTER_AREA) return;
    // A light shines along its −z; a plane's front face is +z.
    const geometry = new THREE.PlaneGeometry(light.width, light.height).rotateY(Math.PI);
    const material = new THREE.MeshBasicMaterial({ color: 0x000000, fog: false, toneMapped: false, depthTest: false, depthWrite: false });
    const pane = new THREE.Mesh(geometry, material);
    pane.name = `${light.name}Reflection`;
    pane.matrixAutoUpdate = false;
    pane.layers.set(layer);
    pane.userData.ignoreRaycast = true;
    pairs.push({ light, pane });
  });
  for (const { pane } of pairs) scene.add(pane);
  return {
    /** Follow each light's transform, colour and intensity, in the units the probe is sampled with. */
    sync() {
      const gain = 1 / Math.max(scene.environmentIntensity, 0.05);
      for (const { light, pane } of pairs) {
        light.updateWorldMatrix(true, false);
        pane.matrix.copy(light.matrixWorld);
        pane.matrixWorld.copy(light.matrixWorld);
        pane.material.color.copy(light.color).multiplyScalar(light.intensity * gain);
      }
    },
  };
}
