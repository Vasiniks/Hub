import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { Pass, FullScreenQuad } from 'three/addons/postprocessing/Pass.js';
import { CopyShader } from 'three/addons/shaders/CopyShader.js';
import type { LightState } from './lighting';
import { fadeColor } from './materials';
import { OVERLAY_LAYER, REFLECTION_LAYER } from './layers';
import { VolumetricLightPass } from './volumetric';
import { createReflectionEmitters, environmentIrradiance, installDiffuseOnlyAreaLights, installSplitEnvironment } from './areaLights';
import { CachedGTAOPass } from './ao';
import { SharedDepthOutlinePass } from './outline';
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
  private readonly quad: FullScreenQuad;

  constructor(scene: THREE.Scene, camera: THREE.Camera, samples: number) {
    super();
    this.scene = scene;
    this.camera = camera;
    this.target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples });
    const copy = new THREE.ShaderMaterial(CopyShader);
    copy.blending = THREE.NoBlending;
    copy.depthTest = false;
    copy.depthWrite = false;
    this.quad = new FullScreenQuad(copy);
    this.needsSwap = false;
  }

  setSize(width: number, height: number) {
    this.target.setSize(width, height);
  }

  render(renderer: THREE.WebGLRenderer, _writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    renderer.setRenderTarget(this.target);
    renderer.render(this.scene, this.camera);
    (this.quad.material as THREE.ShaderMaterial).uniforms.tDiffuse.value = this.target.texture;
    renderer.setRenderTarget(this.renderToScreen ? null : readBuffer);
    this.quad.render(renderer);
  }

  dispose() {
    this.target.dispose();
    this.quad.dispose();
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

/**
 * Tone mapping, colour encoding and the grade in one full-screen pass.
 *
 * They used to be two: the output pass wrote a full-resolution image purely so the grade could
 * read it back and write another. Same maths, same order — AgX, sRGB encoding, then the grade on
 * display-referred values — one fewer full-resolution pass per frame.
 */
class GradedOutputPass extends OutputPass {
  readonly grade = GRADE_UNIFORMS;

  constructor(enabled: boolean) {
    super();
    Object.assign(this.uniforms, GRADE_UNIFORMS);
    const material = (this as unknown as { material: THREE.RawShaderMaterial }).material;
    const source = material.fragmentShader;
    const end = source.lastIndexOf('}');
    material.fragmentShader =
      (enabled ? '#define GRADE\n' : '') +
      source.slice(0, end).replace('varying vec2 vUv;', `varying vec2 vUv;\n${GRADE_PARS}`) +
      GRADE_BODY +
      source.slice(end);
    // OutputPass rebuilds its defines when the tone mapping changes; keep the grade switch in the
    // source instead so that rebuild cannot drop it.
    material.needsUpdate = true;
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
  const scenePass = msaaSamples > 0 ? new MultisampleScenePass(scene, camera, msaaSamples) : new RenderPass(scene, camera);
  composer.addPass(scenePass);

  const gtao = new CachedGTAOPass(scene, camera, w, h);
  gtao.caching = params.get('aocache') !== '0';
  gtao.adaptiveResolution = params.get('aoadaptive') !== '0';
  // Debug: ?aoview=ao shows the denoised occlusion buffer on its own.
  if (params.get('aoview') === 'ao') gtao.output = GTAOPass.OUTPUT.Denoise;
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

  const volumetric = new VolumetricLightPass(camera, sun, lamp, () => gtao.depthTexture ?? null);
  volumetric.enabled = volumetricEnabled;
  volumetric.resolutionScale = () => (volScaleParam > 0 ? volScaleParam : 0.4 / pixelRatio);
  composer.addPass(volumetric);

  const outline = params.get('outline') === 'stock'
    ? new OutlinePass(new THREE.Vector2(w, h), scene, camera)
    : new SharedDepthOutlinePass(new THREE.Vector2(w, h), scene, camera, () => (gtao.enabled ? gtao.depthTexture : null));
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
  const bloom = new UnrealBloomPass(new THREE.Vector2(w, h), 0.3, 0.5, BLOOM_THRESHOLD);
  bloom.enabled = params.get('bloom') !== '0';
  const tints = (bloom as unknown as { bloomTintColors: THREE.Vector3[] }).bloomTintColors;
  BLOOM_LEVELS.forEach((v, i) => tints[i].setScalar(v));
  composer.addPass(bloom);
  const output = new GradedOutputPass(params.get('grade') !== '0');
  composer.addPass(output);

  // Debug: GPU time per pass (?gpu). Wraps each pass, shadow-map rendering and env capture.
  const gpu = createGpuTimer(renderer.getContext() as WebGL2RenderingContext, params.has('gpu'));
  if (gpu.enabled) {
    for (const pass of composer.passes) gpu.wrap(pass, 'render', pass.constructor.name);
    gpu.wrap(renderer.shadowMap, 'render', 'ShadowMaps');
  }

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
    // Capture first: materials compiled before the environment exists get the wrong program
    // variant and recompile (synchronously) the first time each object comes into view.
    captureEnvironmentNow();
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
      stepCapture();
      output.grade.uTime.value = animateGrain ? time : 0;
      composer.render(dt);
      gpu.endFrame();
      watchPerformance(dt);
    },
  };
}
