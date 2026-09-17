import * as THREE from 'three';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';
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

const areaLightMode = new URLSearchParams(location.search).get('arealights');
/** False under `?arealights=pixel`: three's stock per-pixel path, for A/B comparison. */
export const diffuseOnlyAreaLights = areaLightMode !== 'pixel';
/** False under `?arealights=integral`: the diffuse stays a per-pixel polygon integral. */
export const bakedAreaLightDiffuse = diffuseOnlyAreaLights && areaLightMode !== 'integral';

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

/**
 * The rect lights' diffuse, precomputed into a volume per light.
 *
 * Their geometry never changes — the window, the monitor's panel, the shelf strip and the spill
 * under the electronics are all bolted in place — and only their colour and intensity follow the
 * hour. What the per-pixel integral computes is therefore the same every frame: the rectangle's
 * *vector* form factor at that point, a purely geometric quantity, which the shader then projects
 * onto the pixel's normal (`max( ( l² − dot( F, N ) ) / ( l + 1 ), 0 )`, three's horizon-clipped
 * approximation). So the vector field is baked once into a small 3D texture per light, and the
 * per-pixel work becomes one trilinear fetch plus a dot product instead of four edge integrals.
 *
 * Lights stay fully dynamic: colour and intensity are still uniforms, so the time of day and the
 * LEDs' pulse behave exactly as before. Normal maps still catch the light, because the normal is
 * still applied per pixel.
 *
 * Each volume covers the whole room, but its axes are warped as the square of the distance from its
 * own light: the innermost voxels are under a millimetre across, the outermost around eight
 * centimetres. That matches how the field actually behaves — it swings hard within centimetres of
 * the spill under the electronics and is nearly flat across the room — so 96³ texels per light is
 * enough everywhere, and nothing has to be cut off at a box edge.
 *
 * `?arealights=pixel` restores three's per-pixel integral for comparison.
 */
const VOLUME_RESOLUTION = 96;
const volumeTextures: { value: (THREE.Texture | null)[] } = { value: [] };
const volumeCentre: { value: THREE.Vector3[] } = { value: [] };
const volumeInvExtent: { value: THREE.Vector3[] } = { value: [] };

const bakeShader = /* glsl */ `
  precision highp float;
  uniform vec3 uCentre, uExtent, uCorner0, uCorner1, uCorner2, uCorner3, uLightNormal;
  uniform float uSlice, uResolution;
  vec3 edgeFormFactor( const in vec3 v1, const in vec3 v2 ) {
    float x = dot( v1, v2 );
    float y = abs( x );
    float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
    float b = 3.4175940 + ( 4.1616724 + y ) * y;
    float v = a / b;
    float thetaSinTheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
    return cross( v1, v2 ) * thetaSinTheta;
  }
  void main() {
    vec3 uvw = vec3( gl_FragCoord.xy / uResolution, ( uSlice + 0.5 ) / uResolution );
    // Undo the square-root warp: u = 0.5 + 0.5·sign(t)·sqrt(|t|), t = (p − centre) / extent.
    vec3 d = uvw * 2.0 - 1.0;
    vec3 p = uCentre + sign( d ) * d * d * uExtent;
    // Behind the emitter: it cannot light this point at all.
    if ( dot( uLightNormal, p - uCorner0 ) < 0.0 ) {
      gl_FragColor = vec4( 0.0 );
      return;
    }
    vec3 c0 = normalize( uCorner0 - p );
    vec3 c1 = normalize( uCorner1 - p );
    vec3 c2 = normalize( uCorner2 - p );
    vec3 c3 = normalize( uCorner3 - p );
    vec3 f = edgeFormFactor( c0, c1 ) + edgeFormFactor( c1, c2 ) + edgeFormFactor( c2, c3 ) + edgeFormFactor( c3, c0 );
    gl_FragColor = vec4( f, 1.0 );
  }
`;

/** Shader-side wiring; must run before any material compiles. */
export function installRectAreaVolumes() {
  if (!bakedAreaLightDiffuse) return;
  shareUniform('rectAreaVolumes', volumeTextures as unknown as THREE.IUniform);
  shareUniform('rectAreaVolumeCentre', volumeCentre as unknown as THREE.IUniform);
  shareUniform('rectAreaVolumeInvExtent', volumeInvExtent as unknown as THREE.IUniform);
  const chunks = THREE.ShaderChunk as unknown as Record<string, string>;

  chunks.lights_pars_begin = `${chunks.lights_pars_begin}
#if defined( STANDARD ) && NUM_RECT_AREA_LIGHTS > 0
  #define RECT_AREA_VOLUMES
  uniform sampler3D rectAreaVolumes[ NUM_RECT_AREA_LIGHTS ];
  uniform vec3 rectAreaVolumeCentre[ NUM_RECT_AREA_LIGHTS ];
  uniform vec3 rectAreaVolumeInvExtent[ NUM_RECT_AREA_LIGHTS ];
  /** View space is rigid: the inverse is the transpose of its rotation. */
  vec3 rectAreaWorldPosition( const in vec3 viewPosition ) {
    return transpose( mat3( viewMatrix ) ) * ( viewPosition - viewMatrix[ 3 ].xyz );
  }
#endif
`;

  // The diffuse term moves out of the per-pixel integral; the near-field specular stays in it.
  const physical = chunks.lights_physical_pars_fragment;
  const diffuse = 'reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );';
  if (!physical.includes(diffuse)) throw new Error('rect area volumes: the diffuse term moved');
  chunks.lights_physical_pars_fragment = physical.replace(diffuse, `#ifndef RECT_AREA_VOLUMES\n\t\t${diffuse}\n\t\t#endif`);

  const src = chunks.lights_fragment_begin;
  const call = 'RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );';
  if (!src.includes(call)) throw new Error('rect area volumes: the rect-area loop changed');
  chunks.lights_fragment_begin = src.replace(
    call,
    `${call}
		#ifdef RECT_AREA_VOLUMES
		{
			vec3 volumeOffset = ( rectAreaWorldPosition( geometryPosition ) - rectAreaVolumeCentre[ i ] ) * rectAreaVolumeInvExtent[ i ];
			if ( all( lessThan( abs( volumeOffset ), vec3( 1.0 ) ) ) ) {
				vec3 volumeUvw = 0.5 + 0.5 * sign( volumeOffset ) * sqrt( abs( volumeOffset ) );
				vec3 formFactor = mat3( viewMatrix ) * texture( rectAreaVolumes[ i ], volumeUvw ).xyz;
				float l = length( formFactor );
				float clipped = max( ( l * l - dot( formFactor, geometryNormal ) ) / ( l + 1.0 ), 0.0 );
				reflectedLight.directDiffuse += rectAreaLight.color * material.diffuseContribution * clipped;
			}
		}
		#endif`,
  );
}

/**
 * Bakes one volume per rect light, in the order three's light list will hold them (scene traversal,
 * which is what `WebGLLights` sorts stably). Runs once, on the GPU, behind the loading bar.
 */
export function bakeRectAreaVolumes(renderer: THREE.WebGLRenderer, scene: THREE.Scene, roomBox: THREE.Box3) {
  if (!bakedAreaLightDiffuse) return [];
  const lights: THREE.RectAreaLight[] = [];
  scene.traverseVisible((o) => {
    if ((o as THREE.RectAreaLight).isRectAreaLight) lights.push(o as THREE.RectAreaLight);
  });

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uCentre: { value: new THREE.Vector3() },
      uExtent: { value: new THREE.Vector3() },
      uCorner0: { value: new THREE.Vector3() },
      uCorner1: { value: new THREE.Vector3() },
      uCorner2: { value: new THREE.Vector3() },
      uCorner3: { value: new THREE.Vector3() },
      uLightNormal: { value: new THREE.Vector3() },
      uSlice: { value: 0 },
      uResolution: { value: VOLUME_RESOLUTION },
    },
    vertexShader: 'void main() { gl_Position = vec4( position.xy, 0.0, 1.0 ); }',
    fragmentShader: bakeShader,
    depthTest: false,
    depthWrite: false,
  });
  const quad = new FullScreenQuad(material);
  const halfWidth = new THREE.Vector3();
  const halfHeight = new THREE.Vector3();
  const rotation = new THREE.Matrix4();
  const centre = new THREE.Vector3();
  const extent = new THREE.Vector3();
  const previousTarget = renderer.getRenderTarget();
  const built: { light: THREE.RectAreaLight; centre: THREE.Vector3; extent: THREE.Vector3 }[] = [];

  volumeTextures.value = [];
  volumeCentre.value = [];
  volumeInvExtent.value = [];

  for (const light of lights) {
    light.updateWorldMatrix(true, false);
    rotation.extractRotation(light.matrixWorld);
    halfWidth.set(light.width * 0.5, 0, 0).applyMatrix4(rotation);
    halfHeight.set(0, light.height * 0.5, 0).applyMatrix4(rotation);
    centre.setFromMatrixPosition(light.matrixWorld);

    // Every volume spans the whole room, measured from its own light.
    // Padded, so surfaces exactly on the room's bounds (the floor) are strictly inside.
    extent
      .set(
        Math.max(centre.x - roomBox.min.x, roomBox.max.x - centre.x),
        Math.max(centre.y - roomBox.min.y, roomBox.max.y - centre.y),
        Math.max(centre.z - roomBox.min.z, roomBox.max.z - centre.z),
      )
      .multiplyScalar(1.08);

    const target = new THREE.WebGL3DRenderTarget(VOLUME_RESOLUTION, VOLUME_RESOLUTION, VOLUME_RESOLUTION, {
      type: THREE.HalfFloatType,
      format: THREE.RGBAFormat,
      depthBuffer: false,
    });
    target.texture.name = `${light.name}Volume`;
    target.texture.minFilter = THREE.LinearFilter;
    target.texture.magFilter = THREE.LinearFilter;
    target.texture.wrapS = target.texture.wrapT = target.texture.wrapR = THREE.ClampToEdgeWrapping;

    const u = material.uniforms;
    (u.uCentre.value as THREE.Vector3).copy(centre);
    (u.uExtent.value as THREE.Vector3).copy(extent);
    // Counter-clockwise, as three builds them; the light shines along −z of its own frame.
    (u.uCorner0.value as THREE.Vector3).copy(centre).add(halfWidth).sub(halfHeight);
    (u.uCorner1.value as THREE.Vector3).copy(centre).sub(halfWidth).sub(halfHeight);
    (u.uCorner2.value as THREE.Vector3).copy(centre).sub(halfWidth).add(halfHeight);
    (u.uCorner3.value as THREE.Vector3).copy(centre).add(halfWidth).add(halfHeight);
    (u.uLightNormal.value as THREE.Vector3).crossVectors(
      (u.uCorner1.value as THREE.Vector3).clone().sub(u.uCorner0.value as THREE.Vector3),
      (u.uCorner3.value as THREE.Vector3).clone().sub(u.uCorner0.value as THREE.Vector3),
    );

    for (let slice = 0; slice < VOLUME_RESOLUTION; slice++) {
      u.uSlice.value = slice;
      renderer.setRenderTarget(target, slice);
      quad.render(renderer);
    }

    volumeTextures.value.push(target.texture);
    volumeCentre.value.push(centre.clone());
    volumeInvExtent.value.push(new THREE.Vector3(1 / extent.x, 1 / extent.y, 1 / extent.z));
    built.push({ light, centre: centre.clone(), extent: extent.clone() });
  }

  renderer.setRenderTarget(previousTarget);
  quad.dispose();
  material.dispose();
  return built.map((b) => ({ light: b.light.name, centre: b.centre.toArray(), extent: b.extent.toArray() }));
}
