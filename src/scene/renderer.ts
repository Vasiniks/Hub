import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { Pass } from 'three/addons/postprocessing/Pass.js';
import { LAMP_DISK_RADIUS, type LightState } from './lighting';
import { fadeColor } from './materials';
import { OVERLAY_LAYER, REFLECTION_LAYER } from './layers';
import { VolumetricLightPass } from './volumetric';
import { bakeRectAreaVolumes, createReflectionEmitters, environmentIrradiance, installDiffuseOnlyAreaLights, installRectAreaVolumes, installSplitEnvironment } from './areaLights';
import { CachedGTAOPass } from './ao';
import { createDiskLampShadow, installDiskLamp } from './lampDisk';
import { SharedDepthOutlinePass } from './outline';
import { BloomPass } from './bloom';
import { createGpuTimer } from '../debug/gpuTimer';

/**
 * Rendering path: WebGL2 rasterisation with PBR materials, soft PCF shadow maps, area
 * lights, ground-truth AO, volumetric sun scattering through the real shadow map, HDR
 * bloom, and an environment map captured from the lit room (reflections + one bounce of
 * indirect light). No path tracing: it cannot converge while the camera moves. A future
 * progressive mode for a resting camera would slot in here.
 */

/**
 * Multisample only the scene geometry, then resolve once into the single-sampled post chain.
 * With multisampled composer buffers every full-screen pass (AO blend, shafts, bloom, output,
 * grade) paid its own MSAA render and resolve; edge quality comes only from this first render.
 */
class MultisampleScenePass extends Pass {
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.Camera;
  private readonly target: THREE.WebGLRenderTarget;

  constructor(scene: THREE.Scene, camera: THREE.Camera, samples: number) {
    super();
    this.scene = scene;
    this.camera = camera;
    this.target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples });
    this.needsSwap = false;
  }

  /** The resolved scene. Read directly by AO-free consumers and the final composite; never copied. */
  get texture() {
    return this.target.texture;
  }

  render(renderer: THREE.WebGLRenderer) {
    renderer.setRenderTarget(this.target);
    renderer.render(this.scene, this.camera);
  }

  setSize(width: number, height: number) {
    this.target.setSize(width, height);
  }

  dispose() {
    this.target.dispose();
  }
}

/**
 * §13: the final cinematic grade.
 *
 * AgX has already done the tone mapping by this point, so this is the part a colourist would
 * do afterwards: a gentle S-curve for contrast, highlights rolling off toward desaturated
 * white the way film shoulders do, a barely-there cool/warm separation between shadows and
 * highlights, a vignette, and grain. Every term is deliberately small — the goal is a frame
 * that reads as photographed, not one that announces a filter. No orange-and-teal.
 */

const GRADE_UNIFORMS = {
  uTime: { value: 0 },
  uVignette: { value: 0.32 },
  uGrain: { value: 0.022 },
  uContrast: { value: 0.22 },
  uShadowTint: { value: new THREE.Color(0.97, 0.985, 1.05) },
  uHighlightTint: { value: new THREE.Color(1.025, 1.005, 0.978) },
  uHighlightDesat: { value: 0.3 },
  uLift: { value: 0.006 },
};

const GRADE_PARS = /* glsl */ `
  uniform float uTime, uVignette, uGrain, uContrast, uHighlightDesat, uLift;
  uniform vec3 uShadowTint, uHighlightTint;
  float gradeHash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  float gradeLuma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
`;

const GRADE_BODY = /* glsl */ `
  #ifdef GRADE
  {
    vec3 c = gl_FragColor.rgb;

    // Gentle S-curve about mid grey. Blended rather than applied outright, so shadow and
    // highlight detail survives instead of being crushed to the ends.
    c = mix(c, c * c * (3.0 - 2.0 * c), uContrast);

    // Shoulder: the brightest values lose saturation on their way to white, which is what
    // stops a sunlit white desk reading as one flat blown patch.
    float l = gradeLuma(c);
    c = mix(c, vec3(l), uHighlightDesat * smoothstep(0.62, 1.0, l));

    // A hair of separation between the cool end and the warm end. Both tints sit within
    // 3% of neutral: enough to feel graded, not enough to read as a colour cast.
    c *= mix(uShadowTint, uHighlightTint, smoothstep(0.08, 0.8, l));

    // Toe lift, so black areas hold a little air rather than clipping to nothing.
    c += uLift * (1.0 - smoothstep(0.0, 0.3, l));

    vec2 q = vUv - 0.5;
    float v = smoothstep(0.86, 0.18, length(q * vec2(1.05, 1.25)));
    c *= mix(1.0 - uVignette, 1.0, v);

    c += (gradeHash(vUv * vec2(1920.0, 1080.0) + fract(uTime) * 91.0) - 0.5) * uGrain;
    gl_FragColor = vec4(c, 1.0);
  }
  #endif
`;

const COMPOSITE_PARS = /* glsl */ `
  uniform sampler2D tAO, tAOPrevious, tScatter, tOutlineMask, tOutlineEdge;
  uniform sampler2D tBloom0, tBloom1, tBloom2, tBloom3, tBloom4;
  uniform float uAO, uAOFade, uScatter, uOutline, uOutlineStrength, uBloom;
  // Screen NDC → the snapshot views AO (and the shafts) and the faded-from AO were computed for.
  uniform mat3 uAOView, uAOPreviousView;
  // For the eye's small translations (breathing): the snapshot's depth, its camera, and the current eye.
  uniform sampler2D tAODepth;
  uniform mat4 uSnapProjectionInverse, uSnapWorld, uSnapViewProjection;
  uniform mat4 uViewProjectionInverse;
  uniform vec3 uSnapEye, uEye;
  vec2 snapshotUv( mat3 view, vec2 uv ) {
    vec3 h = view * vec3( uv * 2.0 - 1.0, 1.0 );
    return h.xy / h.z * 0.5 + 0.5;
  }
  /**
   * Rotation maps exactly; translation is corrected per pixel. The surface is found in the snapshot
   * along the rotated ray, placed at that distance along this eye's ray, and projected back into
   * the snapshot. Exact for millimetres of travel, which is all a snapshot is kept through.
   */
  vec2 snapshotUvWithParallax( vec2 uv ) {
    vec2 rotated = snapshotUv( uAOView, uv );
    float z = texture2D( tAODepth, rotated ).x;
    vec4 snapView = uSnapProjectionInverse * vec4( rotated * 2.0 - 1.0, z * 2.0 - 1.0, 1.0 );
    vec3 surface = ( uSnapWorld * vec4( snapView.xyz / snapView.w, 1.0 ) ).xyz;
    vec4 far = uViewProjectionInverse * vec4( uv * 2.0 - 1.0, 1.0, 1.0 );
    vec3 ray = normalize( far.xyz / far.w - uEye );
    vec4 clip = uSnapViewProjection * vec4( uEye + ray * distance( surface, uSnapEye ), 1.0 );
    return clip.xy / clip.w * 0.5 + 0.5;
  }
  uniform vec3 uBloomWeights[5];
`;

/** Everything the image receives after the scene render, in the order the old pass chain applied it. */
const COMPOSITE_BODY = /* glsl */ `
  if ( uAO > 0.0 ) {
    vec2 aoUv = snapshotUvWithParallax( vUv );
    vec3 ao = texture2D( tAO, aoUv ).rgb;
    if ( uAOFade < 1.0 ) ao = mix( texture2D( tAOPrevious, snapshotUv( uAOPreviousView, vUv ) ).rgb, ao, uAOFade );
    gl_FragColor.rgb *= mix( vec3( 1.0 ), ao, uAO );
  }
  if ( uScatter > 0.0 ) gl_FragColor.rgb += texture2D( tScatter, snapshotUvWithParallax( vUv ) ).rgb;
  if ( uOutline > 0.0 ) {
    vec4 edge = uOutlineStrength * texture2D( tOutlineMask, vUv ).r * texture2D( tOutlineEdge, vUv );
    gl_FragColor.rgb += edge.rgb * edge.a;
  }
  if ( uBloom > 0.0 ) {
    gl_FragColor.rgb += uBloomWeights[ 0 ] * texture2D( tBloom0, vUv ).rgb
      + uBloomWeights[ 1 ] * texture2D( tBloom1, vUv ).rgb
      + uBloomWeights[ 2 ] * texture2D( tBloom2, vUv ).rgb
      + uBloomWeights[ 3 ] * texture2D( tBloom3, vUv ).rgb
      + uBloomWeights[ 4 ] * texture2D( tBloom4, vUv ).rgb;
  }
`;

export interface CompositeInputs {
  camera: THREE.PerspectiveCamera;
  scene: () => THREE.Texture;
  ao: CachedGTAOPass;
  volumetric: VolumetricLightPass;
  outline: SharedDepthOutlinePass;
  bloom: BloomPass;
}

/**
 * The whole post chain in one full-screen pass: AO, light shafts, hover outline and bloom are
 * applied to the scene here, then AgX, sRGB encoding and the grade — straight to the canvas.
 *
 * Every earlier stage now writes only its own small buffer (AO at CSS or half resolution, shafts at
 * 0.4, bloom levels from half down, the outline's mask and edges). Before, each one copied or blended
 * the full-resolution image: the MSAA resolve copy, AO multiply, shafts add, outline overlay and bloom
 * add were five full-resolution passes. On a tile-based GPU every one of those stores and reloads the
 * whole frame, which cost more than their arithmetic. Same maths, same order.
 */
class GradedOutputPass extends OutputPass {
  readonly grade = GRADE_UNIFORMS;
  private readonly inputs: CompositeInputs;
  /** 0 normal, 1 occlusion only (`?aoview=ao`). */
  private readonly aoView: boolean;

  constructor(enabled: boolean, inputs: CompositeInputs, aoView: boolean) {
    super();
    this.inputs = inputs;
    this.aoView = aoView;
    Object.assign(this.uniforms, GRADE_UNIFORMS, {
      tAO: { value: null },
      tAOPrevious: { value: null },
      tScatter: { value: null },
      tOutlineMask: { value: null },
      tOutlineEdge: { value: null },
      tBloom0: { value: null },
      tBloom1: { value: null },
      tBloom2: { value: null },
      tBloom3: { value: null },
      tBloom4: { value: null },
      uAO: { value: 0 },
      uAOFade: { value: 1 },
      uScatter: { value: 0 },
      uOutline: { value: 0 },
      uOutlineStrength: { value: 1 },
      uBloom: { value: 0 },
      uBloomWeights: { value: [0, 0, 0, 0, 0].map(() => new THREE.Vector3()) },
      uAOView: { value: new THREE.Matrix3() },
      tAODepth: { value: null },
      uSnapProjectionInverse: { value: new THREE.Matrix4() },
      uSnapWorld: { value: new THREE.Matrix4() },
      uSnapViewProjection: { value: new THREE.Matrix4() },
      uViewProjectionInverse: { value: new THREE.Matrix4() },
      uSnapEye: { value: new THREE.Vector3() },
      uEye: { value: new THREE.Vector3() },
      uAOPreviousView: { value: new THREE.Matrix3() },
    });
    const material = (this as unknown as { material: THREE.RawShaderMaterial }).material;
    const source = material.fragmentShader;
    const end = source.lastIndexOf('}');
    const sample = 'gl_FragColor = texture2D( tDiffuse, vUv );';
    if (!source.includes(sample)) throw new Error('composite: OutputShader changed');
    material.fragmentShader =
      (enabled ? '#define GRADE\n' : '') +
      source
        .slice(0, end)
        .replace('varying vec2 vUv;', `varying vec2 vUv;\n${GRADE_PARS}\n${COMPOSITE_PARS}`)
        .replace(sample, `${sample}\n${aoView ? 'gl_FragColor = vec4( texture2D( tAO, vUv ).rgb, 1.0 );' : COMPOSITE_BODY}`) +
      GRADE_BODY +
      source.slice(end);
    // OutputPass rebuilds its defines when the tone mapping changes; keep the grade switch in the
    // source instead so that rebuild cannot drop it.
    material.needsUpdate = true;
  }

  private readonly input: { texture: THREE.Texture | null } = { texture: null };

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget) {
    const u = this.uniforms as Record<string, THREE.IUniform>;
    const { ao, volumetric, outline, bloom } = this.inputs;
    u.uAO.value = ao.enabled || this.aoView ? ao.blendIntensity : 0;
    u.tAO.value = ao.texture;
    u.tAOPrevious.value = ao.previousTexture;
    u.uAOFade.value = ao.fadeProgress;
    const main = this.inputs.camera;
    const snap = ao.view.camera;
    ao.view.reprojection(main, u.uAOView.value as THREE.Matrix3);
    u.tAODepth.value = ao.depthTexture;
    (u.uSnapProjectionInverse.value as THREE.Matrix4).copy(snap.projectionMatrixInverse);
    (u.uSnapWorld.value as THREE.Matrix4).copy(snap.matrixWorld);
    (u.uSnapViewProjection.value as THREE.Matrix4).multiplyMatrices(snap.projectionMatrix, snap.matrixWorldInverse);
    (u.uViewProjectionInverse.value as THREE.Matrix4).multiplyMatrices(main.projectionMatrix, main.matrixWorldInverse).invert();
    (u.uSnapEye.value as THREE.Vector3).setFromMatrixPosition(snap.matrixWorld);
    (u.uEye.value as THREE.Vector3).setFromMatrixPosition(main.matrixWorld);
    if (ao.fadeProgress < 1) ao.previousView.reprojection(this.inputs.camera, u.uAOPreviousView.value as THREE.Matrix3);
    u.uScatter.value = volumetric.enabled && volumetric.active ? 1 : 0;
    u.tScatter.value = volumetric.texture;
    u.uOutline.value = outline.enabled && outline.selectedObjects.length > 0 ? 1 : 0;
    u.uOutlineStrength.value = outline.edgeStrength;
    u.tOutlineMask.value = outline.maskTexture;
    u.tOutlineEdge.value = outline.edgeTexture;
    u.uBloom.value = bloom.enabled ? 1 : 0;
    bloom.textures.forEach((t, i) => {
      u[`tBloom${i}`].value = t;
      (u.uBloomWeights.value as THREE.Vector3[])[i].setScalar(bloom.weight(i));
    });
    // OutputPass reads `readBuffer.texture` as its input: hand it the scene instead.
    this.input.texture = this.inputs.scene();
    super.render(renderer, writeBuffer, this.input as unknown as THREE.WebGLRenderTarget, 0, false);
  }
}

export function createRenderer(
  canvas: HTMLCanvasElement,
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  sun: THREE.DirectionalLight,
  lamp: THREE.SpotLight,
) {
  const params = new URLSearchParams(location.search);
  // Must precede every material compile (see areaLights.ts).
  installDiffuseOnlyAreaLights();
  installSplitEnvironment();
  installRectAreaVolumes();
  installDiskLamp();
  // Profiling switches (A/B): ?ao=half|off  ?vol=0  ?msaa=0  ?bloom=0  ?pr=<ratio> (fixed, no fallback)
  const aoParam = params.get('ao');
  const volScaleParam = Number(params.get('volscale'));
  const aoOff = params.get('ao') === 'off';
  const forcedRatio = Number(params.get('pr'));
  const adaptive = !(forcedRatio > 0) && params.get('adaptive') !== '0';
  const volumetricEnabled = params.get('vol') !== '0';

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
  let pixelRatio = forcedRatio > 0 ? forcedRatio : Math.min(window.devicePixelRatio, 1.5);
  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  // The main loop resets once per frame, so counts cover every pass.
  renderer.info.autoReset = false;

  const w = window.innerWidth;
  const h = window.innerHeight;
  // At retina density 2× MSAA is hard to tell from 4× and halves the largest buffers.
  const msaaParam = params.get('msaa');
  const msaaSamples = msaaParam !== null ? Number(msaaParam) : pixelRatio > 1.25 ? 2 : 4;
  // No render target passed in: EffectComposer takes a supplied target's size as its CSS size and
  // multiplies by the pixel ratio again, so every buffer ran at ratio² (2250×1406 at "1.25") until
  // the first window resize happened to correct it. Its own targets are half-float already.
  const composer = new EffectComposer(renderer);
  const scenePass = new MultisampleScenePass(scene, camera, msaaSamples);
  composer.addPass(scenePass);

  const gtao = new CachedGTAOPass(scene, camera, w, h);
  gtao.caching = params.get('aocache') !== '0';
  gtao.adaptiveResolution = params.get('aoadaptive') !== '0';
  // AO is low-frequency: render it at CSS-pixel density, not device density, so retina screens
  // get the same AO detail per point as standard ones without paying 2.25× the fill.
  const aoCss = Number(params.get('aoscale'));
  const aoScale = () => (aoParam === 'full' ? 1 : aoParam === 'half' ? 0.5 : (aoCss > 0 ? aoCss : 1) / pixelRatio);
  const baseSetSize = gtao.setSize.bind(gtao);
  gtao.setSize = (width: number, height: number) =>
    baseSetSize(Math.max(1, Math.round(width * aoScale())), Math.max(1, Math.round(height * aoScale())));
  gtao.updateGtaoMaterial({ radius: 0.28, distanceExponent: 1.6, thickness: 1.2, scale: 1.1, samples: 16 });
  gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 5, rings: 2, samples: 16 });
  gtao.blendIntensity = 0.9;
  gtao.enabled = !aoOff;
  composer.addPass(gtao);

  // The shafts are marched for AO's snapshot view, from its depth, and reprojected with it.
  const volumetric = new VolumetricLightPass(
    () => gtao.view.camera,
    () => gtao.computedThisFrame,
    sun,
    lamp,
    () => gtao.depthTexture ?? null,
  );
  volumetric.enabled = volumetricEnabled;
  volumetric.resolutionScale = () => (volScaleParam > 0 ? volScaleParam : 0.4 / pixelRatio);
  composer.addPass(volumetric);

  const outline = new SharedDepthOutlinePass(
    new THREE.Vector2(w, h),
    scene,
    camera,
    () => (gtao.enabled ? gtao.depthTexture : null),
    () => gtao.view.camera,
  );
  outline.edgeStrength = 2.4;
  outline.edgeGlow = 0;
  outline.edgeThickness = 1;
  outline.visibleEdgeColor.set('#e9edf1');
  outline.hiddenEdgeColor.set('#20242a');
  outline.enabled = false; // switched on only while something is hovered
  composer.addPass(outline);

  // Attention dots are UI: no AO, no outline depth.
  for (const pass of [gtao, outline]) {
    const original = pass.render.bind(pass) as (...args: unknown[]) => void;
    pass.render = ((...args: unknown[]) => {
      camera.layers.disable(OVERLAY_LAYER);
      original(...args);
      camera.layers.enable(OVERLAY_LAYER);
    }) as unknown as typeof pass.render;
  }

  /**
   * Bloom threshold in display terms. The bloom pass sees the scene-referred HDR image before
   * exposure, so a fixed threshold meant "bright" changed with the hour: at night (exposure 1.0)
   * only the lamp, LEDs and screen crossed it, but by day (exposure 0.47) the whole sunlit desk
   * did. Dividing by exposure keeps it meaning the same brightness on screen at every hour.
   */
  const BLOOM_THRESHOLD = 1.45;
  /**
   * Weight of each blur level, tightest first. Stock weights are near-equal, and the widest
   * levels spread a large bright area over everything around it: by day that laid a milky veil
   * across the desk and took the speedcube's faces from strong colour to pastel at close range.
   * The halo around a light comes from the tight levels, the veil from the wide ones, so the
   * tight ones carry slightly more and the wide ones almost nothing. Measured with
   * scripts/bloom-score: cube face saturation in a daylight close-up 0.17 → 0.47 (0.70 with no
   * bloom at all), with the night frame unchanged to within grain.
   */
  const BLOOM_LEVELS = [1.2, 0.8, 0.25, 0.08, 0.05];
  const bloom = new BloomPass(() => scenePass.texture);
  bloom.strength = 0.3;
  bloom.threshold = BLOOM_THRESHOLD;
  bloom.enabled = params.get('bloom') !== '0';
  BLOOM_LEVELS.forEach((v, i) => (bloom.levels[i] = v));
  composer.addPass(bloom);
  // Debug: ?aoview=ao shows the occlusion on its own.
  const output = new GradedOutputPass(
    params.get('grade') !== '0',
    { camera, scene: () => scenePass.texture, ao: gtao, volumetric, outline, bloom },
    params.get('aoview') === 'ao',
  );
  composer.addPass(output);
  // Every pass writes its own buffers and the composite writes the canvas, so the composer's two
  // full-resolution swap buffers are never used: keep them at a pixel instead of ~60 MB of float.
  const shrinkSwapBuffers = () => {
    composer.renderTarget1.setSize(1, 1);
    composer.renderTarget2.setSize(1, 1);
  };
  const composerSetSize = composer.setSize.bind(composer);
  composer.setSize = (width: number, height: number) => {
    composerSetSize(width, height);
    shrinkSwapBuffers();
  };
  const composerSetPixelRatio = composer.setPixelRatio.bind(composer);
  composer.setPixelRatio = (ratio: number) => {
    composerSetPixelRatio(ratio);
    shrinkSwapBuffers();
  };
  shrinkSwapBuffers();

  // Debug: GPU time per pass (?gpu). Wraps each pass, shadow-map rendering and env capture.
  const gpu = createGpuTimer(renderer.getContext() as WebGL2RenderingContext, params.has('gpu'));
  if (gpu.enabled) {
    for (const pass of composer.passes) gpu.wrap(pass, 'render', pass.constructor.name);
    gpu.wrap(renderer.shadowMap, 'render', 'ShadowMaps');
  }

  const lampShadow = createDiskLampShadow(renderer, scene, lamp, LAMP_DISK_RADIUS);
  /** Where the room's lighting lives: the walls, plus the space the visitor can stand in. */
  const ROOM_BOX = new THREE.Box3(new THREE.Vector3(-1.95, 0, -1.45), new THREE.Vector3(1.85, 3, 1.6));
  let rectAreaVolumes: unknown[] = [];

  // ---- Environment capture: reflections + indirect light from the lit room ----------------
  const cubeTarget = new THREE.WebGLCubeRenderTarget(128, { type: THREE.HalfFloatType });
  const cubeCamera = new THREE.CubeCamera(0.05, 30, cubeTarget);
  cubeCamera.position.set(0.0, 1.15, -0.35);
  scene.add(cubeCamera);
  const pmrem = new THREE.PMREMGenerator(renderer);
  let envTarget: THREE.WebGLRenderTarget | null = null;
  let irradianceTarget: THREE.WebGLRenderTarget | null = null;
  let captureFace = -1;
  const reflectionEmitters = createReflectionEmitters(scene, REFLECTION_LAYER);
  const splitEnvironment = reflectionEmitters !== null;

  /** Filter the room as captured: irradiance when the environment is split, both otherwise. */
  function filterRoom() {
    const next = pmrem.fromCubemap(cubeTarget.texture);
    if (!splitEnvironment) return swapEnvironment(next);
    irradianceTarget?.dispose();
    irradianceTarget = next;
    environmentIrradiance.value = next.texture;
  }

  /** Draw the reflection-only emitters over the captured faces, then filter again for specular. */
  function filterReflections() {
    const background = scene.background;
    const autoClear = renderer.autoClear;
    const previous = renderer.getRenderTarget();
    scene.background = null;
    renderer.autoClear = false;
    reflectionEmitters?.sync();
    for (let face = 0; face < 6; face++) {
      const cam = cubeCamera.children[face] as THREE.Camera;
      cam.layers.set(REFLECTION_LAYER);
      renderer.setRenderTarget(cubeTarget, face);
      renderer.render(scene, cam);
      cam.layers.set(0);
    }
    renderer.setRenderTarget(previous);
    renderer.autoClear = autoClear;
    scene.background = background;
    swapEnvironment(pmrem.fromCubemap(cubeTarget.texture));
  }

  function swapEnvironment(next: THREE.WebGLRenderTarget) {
    envTarget?.dispose();
    envTarget = next;
    scene.environment = next.texture;
    if (!splitEnvironment) environmentIrradiance.value = next.texture;
  }

  function captureEnvironmentNow() {
    const env = scene.environment;
    scene.environment = null;
    cubeCamera.update(renderer, scene);
    scene.environment = env;
    filterRoom();
    if (splitEnvironment) filterReflections();
    captureFace = -1;
  }

  /** Spread a capture over frames (one cube face each, then filtering) instead of one hitch. */
  function requestEnvironmentCapture() {
    if (captureFace < 0) captureFace = 0;
  }

  function stepCapture() {
    if (captureFace < 0) return;
    if (captureFace < 6) {
      const env = scene.environment;
      const previous = renderer.getRenderTarget();
      scene.environment = null;
      renderer.setRenderTarget(cubeTarget, captureFace);
      gpu.begin('EnvCaptureFace');
      renderer.render(scene, cubeCamera.children[captureFace] as THREE.Camera);
      gpu.end();
      renderer.setRenderTarget(previous);
      scene.environment = env;
      captureFace++;
      return;
    }
    gpu.begin('EnvPMREM');
    if (captureFace === 6) filterRoom();
    else filterReflections();
    gpu.end();
    captureFace = splitEnvironment && captureFace === 6 ? 7 : -1;
  }

  function applyLight(state: LightState) {
    renderer.toneMappingExposure = state.exposure;
    scene.environmentIntensity = state.env;
    bloom.strength = state.bloom;
    bloom.threshold = BLOOM_THRESHOLD / state.exposure;
    (scene.background as THREE.Color).copy(state.sky);
    fadeColor.copy(state.sky);
    const fog = scene.fog as THREE.FogExp2;
    fog.color.copy(state.sky);
    fog.density = state.fog;
    volumetric.scatter.copy(state.scatter);
    volumetric.lampScatter.copy(state.lampScatter);
  }

  function resize() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    composer.setSize(width, height);
  }

  function setPixelRatio(next: number) {
    if (Math.abs(next - pixelRatio) < 0.01) return false;
    pixelRatio = next;
    renderer.setPixelRatio(next);
    composer.setPixelRatio(next);
    resize();
    return true;
  }

  /** Candidate render resolutions, highest first. */
  const RATIO_STEPS = [1.5, 1.25, 1];

  /**
   * Safety net only. Calibration has already chosen the resolution, so this exists for a
   * machine that gets slower later (another tab, thermal throttling) and steps down once.
   */
  const recent = new Float32Array(120);
  let recentCount = 0;
  let clock = 0;
  function watchPerformance(dt: number) {
    clock += dt;
    if (!adaptive || pixelRatio <= 1 || clock < 10) return;
    recent[recentCount % recent.length] = dt;
    recentCount++;
    if (recentCount % 60 !== 0 || recentCount < recent.length) return;
    const median = Float32Array.from(recent).sort()[recent.length >> 1];
    if (median > 1 / 30) setPixelRatio(Math.max(1, pixelRatio - 0.25));
  }

  /**
   * Compile every shader and capture the environment before the first visible frame.
   * `onStage` fires as each phase genuinely completes, so the loading bar reports real work.
   */
  async function warmUp(samples: THREE.Object3D[] = [], onStage: (stage: string) => void = () => {}) {
    // The rect lights' diffuse volumes, before anything renders with them (see areaLights.ts).
    scene.updateMatrixWorld(true);
    rectAreaVolumes = bakeRectAreaVolumes(renderer, scene, ROOM_BOX);
    // Capture first: materials compiled before the environment exists get the wrong program
    // variant and recompile (synchronously) the first time each object comes into view.
    captureEnvironmentNow();
    lampShadow?.draw();
    onStage('compiling shaders');
    await renderer.compileAsync(scene, camera);
    onStage('warming passes');
    // Post passes compile lazily on first use. Run the ones that normally sleep (hover outline,
    // daylight shafts) once under the veil, so they never hitch mid-interaction or at dawn.
    const scatter = volumetric.scatter.clone();
    const lampScatter = volumetric.lampScatter.clone();
    if (scatter.r + scatter.g + scatter.b < 1e-4) volumetric.scatter.setRGB(0.001, 0.001, 0.001);
    if (lampScatter.r + lampScatter.g + lampScatter.b < 1e-4) volumetric.lampScatter.setRGB(0.001, 0.001, 0.001);
    // Select every interactive object at once so each shader variant (instanced parts included) compiles.
    if (samples.length) {
      outline.selectedObjects = samples;
      outline.enabled = true;
    }
    // Override-material passes (outline mask, AO normals) compile a variant per object only when that
    // object is in view. Warm them from a wide vantage that sees every object, then restore the camera.
    const pose = { position: camera.position.clone(), quaternion: camera.quaternion.clone(), fov: camera.fov };
    camera.position.set(0.9, 2.9, 2.9);
    camera.lookAt(-0.2, 0.5, -0.4);
    camera.fov = 85;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    composer.render(0);
    // Real hovers outline one object while the others render into the outline's depth pass as
    // "non-selected", which needs its own shader variants (instanced parts included). Warm each.
    for (const sample of samples) {
      outline.selectedObjects = [sample];
      composer.render(0);
    }
    camera.position.copy(pose.position);
    camera.quaternion.copy(pose.quaternion);
    camera.fov = pose.fov;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    outline.enabled = false;
    outline.selectedObjects = [];
    volumetric.scatter.copy(scatter);
    volumetric.lampScatter.copy(lampScatter);
    onStage('measuring');
  }

  return {
    renderer,
    /** Debug/bench access to the post chain; not used by the room itself. */
    composer,
    scenePass,
    gpu,
    /** Debug: the boxes the rect-area light volumes were baked over. */
    rectAreaVolumes: () => rectAreaVolumes,
    /** Ambient occlusion cache: flag `invalid` when something on screen moves. */
    ao: gtao,
    outline,
    volumetric,
    warmUp,
    pixelRatio: () => pixelRatio,
    /** False when the resolution is pinned (`?pr=`), so nothing may change it. */
    adaptive,
    /** Step down to the next lower render resolution. Returns false at the floor. */
    stepDownResolution() {
      const next = RATIO_STEPS.find((r) => r < pixelRatio - 0.01);
      if (next === undefined) return false;
      return setPixelRatio(Math.min(window.devicePixelRatio, next));
    },
    /** True while a spread environment capture still has faces left to render. */
    capturing: () => captureFace >= 0,
    captureEnvironmentNow,
    requestEnvironmentCapture,
    applyLight,
    resize,
    render(dt: number, time: number, animateGrain: boolean) {
      // A redrawn shadow map changes the shafts; they are otherwise reused (see volumetric.ts).
      if (sun.shadow.needsUpdate || lamp.shadow.needsUpdate) volumetric.invalid = true;
      lampShadow?.update();
      stepCapture();
      output.grade.uTime.value = animateGrain ? time : 0;
      composer.render(dt);
      gpu.endFrame();
      watchPerformance(dt);
    },
  };
}
