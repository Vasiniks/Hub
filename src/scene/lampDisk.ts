import * as THREE from 'three';
import { shareUniform } from './sharedUniforms';

/**
 * The desk lamp as a disk emitter rather than a point.
 *
 * The lamp is a 13 cm diffuser half a metre above the desk. Lit as a point (three's SpotLight),
 * it gave pinpoint highlights, the same penumbra everywhere, and an inverse-square hot spot. Three
 * things change, all analytic, none of them extra lights:
 *
 * - Shadows are percentage-closer soft shadows. A blocker search finds how far above the receiver
 *   the occluder is, and the filter widens with that distance exactly as a disk's penumbra does
 *   (r·(dReceiver − dBlocker)/dBlocker): the mug's shadow is crisp at its base and soft at its rim.
 *   The search needs raw depth, which the lamp's compare-mode shadow map cannot give, so the
 *   casters' depth is also written to a small float map — redrawn only when the shadow map is, which
 *   is only when something that casts has moved.
 * - Specular widens by the disk's angular size (α' = α + r/2d, the half-vector spread of a source
 *   of radius r at distance d), so glossy surfaces show a soft disk instead of a pin.
 * - Irradiance falls off as 1/(d² + r²), a disk's on-axis law, instead of 1/d².
 *
 * Only the fragment work is new, and it runs only where the lamp is lit, inside its cone.
 * `?lamp=point` restores the stock path for comparison.
 */
export const diskLamp = new URLSearchParams(location.search).get('lamp') !== 'point';

const BLOCKER_MAP_SIZE = 512;
const SEARCH_SAMPLES = 12;
const FILTER_SAMPLES = 12;
/** Largest blocker search radius, in shadow-map UV: occluders right at the diffuser cast no shadow worth finding. */
const MAX_SEARCH_UV = 0.05;

const lampDiskRadius = { value: 0.065 };
const lampBlockerMap: { value: THREE.Texture | null } = { value: null };
/** near, far, tan(fov/2) of the shadow camera, and the disk radius. */
const lampShadowParams = { value: new THREE.Vector4(0.1, 3, 0.5, 0.065) };

export function installDiskLamp() {
  if (!diskLamp) return;
  shareUniform('lampDiskRadius', lampDiskRadius);
  shareUniform('lampBlockerMap', lampBlockerMap);
  shareUniform('lampShadowParams', lampShadowParams);
  const chunks = THREE.ShaderChunk as unknown as Record<string, string>;

  chunks.lights_pars_begin = `${chunks.lights_pars_begin}
#if defined( STANDARD ) && NUM_SPOT_LIGHTS > 0
  uniform float lampDiskRadius;
#endif
`;

  chunks.shadowmap_pars_fragment = `${chunks.shadowmap_pars_fragment}
#if defined( USE_SHADOWMAP ) && defined( SHADOWMAP_TYPE_PCF ) && defined( STANDARD ) && NUM_SPOT_LIGHT_SHADOWS > 0
  #define LAMP_DISK_SHADOW
  uniform sampler2D lampBlockerMap;
  uniform vec4 lampShadowParams;

  float lampLinearDepth( const in float z ) {
    float n = lampShadowParams.x;
    float f = lampShadowParams.y;
    return ( 2.0 * n * f ) / ( f + n - ( z * 2.0 - 1.0 ) * ( f - n ) );
  }

  float getLampShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, vec4 shadowCoord ) {
    shadowCoord.xyz /= shadowCoord.w;
    shadowCoord.z += shadowBias;
    if ( shadowCoord.x < 0.0 || shadowCoord.x > 1.0 || shadowCoord.y < 0.0 || shadowCoord.y > 1.0 || shadowCoord.z > 1.0 ) return 1.0;

    // Receiver plane: how depth changes across the map here, so wide kernels do not find the
    // receiver's own surface (tilted toward the lamp) as an occluder.
    vec3 sx = dFdx( shadowCoord.xyz );
    vec3 sy = dFdy( shadowCoord.xyz );
    float det = sx.x * sy.y - sx.y * sy.x;
    vec2 slope = abs( det ) > 1e-12 ? vec2( sy.y * sx.z - sx.y * sy.z, sx.x * sy.z - sy.x * sx.z ) / det : vec2( 0.0 );
    slope = clamp( slope, vec2( -0.05 ), vec2( 0.05 ) );

    float n = lampShadowParams.x;
    float widthPerMetre = 2.0 * lampShadowParams.z;
    float radius = lampShadowParams.w;
    float receiver = lampLinearDepth( shadowCoord.z );
    float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;

    // Blocker search over the region from which any part of the disk can be hidden.
    float searchUv = min( radius * ( receiver - n ) / ( receiver * n * widthPerMetre ), ${MAX_SEARCH_UV.toFixed(3)} );
    float blockerSum = 0.0;
    float blockers = 0.0;
    for ( int i = 0; i < ${SEARCH_SAMPLES}; i ++ ) {
      vec2 offset = vogelDiskSample( i, ${SEARCH_SAMPLES}, phi ) * searchUv;
      float z = 1.0 - texture2D( lampBlockerMap, shadowCoord.xy + offset ).r;
      float d = lampLinearDepth( z );
      float plane = lampLinearDepth( shadowCoord.z + dot( slope, offset ) );
      if ( d < plane - 0.0015 ) {
        blockerSum += d;
        blockers += 1.0;
      }
    }
    // No occluder found: one filtered tap settles it. (Not simply "lit": a sparse search can step
    // over an occluder in near contact, and wrongly lit is far more visible than a hard edge.)
    if ( blockers == 0.0 ) return mix( 1.0, texture( shadowMap, shadowCoord.xyz ), shadowIntensity );

    float blocker = blockerSum / blockers;
    float texel = 1.0 / shadowMapSize.x;
    float penumbraUv = clamp( radius * ( receiver - blocker ) / ( receiver * blocker * widthPerMetre ), texel, searchUv );

    float lit = 0.0;
    for ( int i = 0; i < ${FILTER_SAMPLES}; i ++ ) {
      vec2 offset = vogelDiskSample( i, ${FILTER_SAMPLES}, phi + 1.7 ) * penumbraUv;
      lit += texture( shadowMap, vec3( shadowCoord.xy + offset, shadowCoord.z + dot( slope, offset ) ) );
    }
    return mix( 1.0, lit / ${FILTER_SAMPLES}.0, shadowIntensity );
  }
#endif
`;

  // Spot lights: disk falloff and highlight size, and the soft shadow above.
  const src = chunks.lights_fragment_begin;
  const start = src.indexOf('#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )');
  const end = src.indexOf('#endif', src.indexOf('RE_Direct(', start));
  if (start < 0 || end < 0) throw new Error('disk lamp: lights_fragment_begin changed');
  const stockShadow =
    'directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;';
  const info = 'getSpotLightInfo( spotLight, geometryPosition, directLight );';
  const direct = 'RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );';
  let spot = src.slice(start, end);
  if (!spot.includes(stockShadow) || !spot.includes(info) || !spot.includes(direct)) throw new Error('disk lamp: spot light loop changed');
  spot = spot
    .replace(
      info,
      `${info}
		#ifdef STANDARD
		vec3 toLamp = spotLight.position - geometryPosition;
		float lampDistance2 = dot( toLamp, toLamp );
		directLight.color *= lampDistance2 / ( lampDistance2 + lampDiskRadius * lampDiskRadius );
		#endif`,
    )
    .replace(
      stockShadow,
      `#ifdef LAMP_DISK_SHADOW
		// Only where the lamp can actually be seen to shadow: facing it, and bright enough here. The
		// search and filter are ~24 taps, and the cone covers far more of the screen than the pool does.
		float lampReach = max( max( directLight.color.r, directLight.color.g ), directLight.color.b ) * saturate( dot( geometryNormal, directLight.direction ) );
		directLight.color *= ( directLight.visible && receiveShadow && lampReach > 0.004 ) ? getLampShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, vSpotLightCoord[ i ] ) : 1.0;
		#else
		${stockShadow}
		#endif`,
    )
    .replace(
      direct,
      `#ifdef STANDARD
		float lampRoughness = material.roughness;
		material.roughness = sqrt( min( 1.0, pow2( lampRoughness ) + lampDiskRadius / ( 2.0 * sqrt( lampDistance2 ) ) ) );
		${direct}
		material.roughness = lampRoughness;
		#else
		${direct}
		#endif`,
    );
  chunks.lights_fragment_begin = src.slice(0, start) + spot + src.slice(end);
}

/**
 * Keeps the blocker map in step with the lamp's shadow map. Call before each frame's render:
 * it only draws when the shadow map is about to redraw.
 */
export function createDiskLampShadow(renderer: THREE.WebGLRenderer, scene: THREE.Scene, lamp: THREE.SpotLight, radius: number) {
  if (!diskLamp) return null;
  lampDiskRadius.value = radius;
  lampShadowParams.value.w = radius;
  const target = new THREE.WebGLRenderTarget(BLOCKER_MAP_SIZE, BLOCKER_MAP_SIZE, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    generateMipmaps: false,
    type: THREE.FloatType,
  });
  target.texture.name = 'lampBlockers';
  lampBlockerMap.value = target.texture;
  const depthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.BasicDepthPacking });
  const hidden: THREE.Object3D[] = [];
  const clear = new THREE.Color();

  function draw() {
    const shadow = lamp.shadow;
    lamp.updateWorldMatrix(true, false);
    lamp.target.updateWorldMatrix(true, false);
    shadow.updateMatrices(lamp);
    const cam = shadow.camera as THREE.PerspectiveCamera;
    lampShadowParams.value.set(cam.near, cam.far, Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2), radius);

    // Only what the shadow map holds: shadow casters.
    scene.traverse((o) => {
      const drawable = o as THREE.Mesh;
      if (!o.visible || !(drawable.isMesh || (o as THREE.Points).isPoints || (o as THREE.Line).isLine || (o as THREE.Sprite).isSprite)) return;
      if (drawable.isMesh && o.castShadow) return;
      o.visible = false;
      hidden.push(o);
    });
    const background = scene.background;
    const override = scene.overrideMaterial;
    const previous = renderer.getRenderTarget();
    const alpha = renderer.getClearAlpha();
    renderer.getClearColor(clear);
    const autoUpdate = renderer.shadowMap.autoUpdate;
    scene.background = null;
    scene.overrideMaterial = depthMaterial;
    renderer.shadowMap.autoUpdate = false;
    renderer.setRenderTarget(target);
    // Stored as 1 − depth: clearing to black means "nothing, all the way to the far plane".
    renderer.setClearColor(0x000000, 1);
    renderer.clear();
    renderer.render(scene, cam);
    renderer.setRenderTarget(previous);
    renderer.setClearColor(clear, alpha);
    renderer.shadowMap.autoUpdate = autoUpdate;
    scene.overrideMaterial = override;
    scene.background = background;
    for (const o of hidden) o.visible = true;
    hidden.length = 0;
  }

  return {
    update() {
      if (lamp.castShadow && lamp.intensity > 0 && (lamp.shadow.needsUpdate || lamp.shadow.autoUpdate)) draw();
    },
    draw,
    target,
  };
}
