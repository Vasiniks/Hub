import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { Pass } from 'three/addons/postprocessing/Pass.js';
import { OVERLAY_LAYER } from './layers';
import { SharedDepthOutlinePass } from './outline';
import { createGpuTimer } from '../debug/gpuTimer';

/**
 * Rendering path for the baked room: one multisampled scene render, the hover outline, and one
 * full-screen composite that applies Blender's own view transform (display LUT) straight to the
 * canvas. The bake already holds every bounce, shadow and glow, so there is no AO, no light shafts
 * and no bloom; the only live lighting is for the PBR props (an environment capture of the baked
 * room, plus the sun and lamp in v2PropLight.ts).
 */

/**
 * Multisample only the scene geometry, then resolve once into the single-sampled composite.
 * Edge quality comes only from this first render.
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

  /** The resolved scene, read directly by the final composite; never copied. */
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

  get samples() {
    return this.target.samples;
  }

  /** Change the MSAA sample count; the target is reallocated on its next use. */
  setSamples(samples: number) {
    if (samples === this.target.samples) return;
    this.target.samples = samples;
    this.target.dispose();
  }

  dispose() {
    this.target.dispose();
  }
}

const COMPOSITE_PARS = /* glsl */ `
  uniform sampler2D tOutlineMask, tOutlineEdge;
  uniform float uOutline, uOutlineStrength;
`;

/** The hover outline, added to the scene before exposure and the view transform. */
const COMPOSITE_BODY = /* glsl */ `
  if ( uOutline > 0.0 ) {
    vec4 edge = uOutlineStrength * texture2D( tOutlineMask, vUv ).r * texture2D( tOutlineEdge, vUv );
    gl_FragColor.rgb += edge.rgb * edge.a;
  }
`;

/**
 * A display transform sampled from Blender's own colour management (see `src/scene/v2Look.ts`):
 * scene-linear Rec.709 (after exposure) → display-encoded sRGB, as an N³ table laid out as N
 * blue slices of N×N side by side (width N², height N). When set it replaces three's AgX and the
 * sRGB encode, because Blender's view transform already is the whole image formation.
 */
export interface DisplayLUT {
  texture: THREE.DataTexture;
  size: number;
  log2Min: number;
  log2Max: number;
}

/** Per-channel log2 shaper, then two bilinear fetches (red/green within a slice) mixed across blue. */
const DISPLAY_LUT_PARS = /* glsl */ `
  uniform sampler2D tDisplayLUT;
  uniform vec3 uDisplayLUT; // size, log2 min, log2 max
  vec3 displayLUT( vec3 x ) {
    float n = uDisplayLUT.x;
    vec3 s = clamp( ( log2( max( x, vec3( 1e-10 ) ) ) - uDisplayLUT.y ) / ( uDisplayLUT.z - uDisplayLUT.y ), 0.0, 1.0 ) * ( n - 1.0 );
    float b0 = min( floor( s.b ), n - 2.0 );
    float v = ( s.g + 0.5 ) / n;
    vec3 c0 = texture2D( tDisplayLUT, vec2( ( b0 * n + s.r + 0.5 ) / ( n * n ), v ) ).rgb;
    vec3 c1 = texture2D( tDisplayLUT, vec2( ( ( b0 + 1.0 ) * n + s.r + 0.5 ) / ( n * n ), v ) ).rgb;
    return mix( c0, c1, s.b - b0 );
  }
`;

/**
 * The scene plus the hover outline, then the view transform, in one full-screen pass straight to
 * the canvas. Until a display LUT is set it falls back to three's AgX and sRGB encode.
 */
class CompositeOutputPass extends OutputPass {
  private readonly sceneTexture: () => THREE.Texture;
  private readonly outline: SharedDepthOutlinePass;
  /** The composite as built below; `setDisplayLUT(null)` returns to it byte for byte. */
  private readonly composedFragment: string;
  private readonly input: { texture: THREE.Texture | null } = { texture: null };

  constructor(sceneTexture: () => THREE.Texture, outline: SharedDepthOutlinePass) {
    super();
    this.sceneTexture = sceneTexture;
    this.outline = outline;
    Object.assign(this.uniforms, {
      tOutlineMask: { value: null },
      tOutlineEdge: { value: null },
      uOutline: { value: 0 },
      uOutlineStrength: { value: 1 },
    });
    const material = (this as unknown as { material: THREE.RawShaderMaterial }).material;
    const sample = 'gl_FragColor = texture2D( tDiffuse, vUv );';
    if (!material.fragmentShader.includes(sample)) throw new Error('composite: OutputShader changed');
    material.fragmentShader = material.fragmentShader
      .replace('varying vec2 vUv;', `varying vec2 vUv;\n${COMPOSITE_PARS}`)
      .replace(sample, `${sample}\n${COMPOSITE_BODY}`);
    material.needsUpdate = true;
    this.composedFragment = material.fragmentShader;
  }

  /**
   * Swap AgX + sRGB encode for a sampled display transform, or back (`null`). Exposure stays
   * `renderer.toneMappingExposure`, applied in scene-linear before the table, as Blender applies
   * its view exposure.
   */
  setDisplayLUT(lut: DisplayLUT | null) {
    const material = (this as unknown as { material: THREE.RawShaderMaterial }).material;
    const u = this.uniforms as Record<string, THREE.IUniform>;
    if (!lut) {
      material.fragmentShader = this.composedFragment;
      material.needsUpdate = true;
      return;
    }
    u.tDisplayLUT = { value: lut.texture };
    u.uDisplayLUT = { value: new THREE.Vector3(lut.size, lut.log2Min, lut.log2Max) };
    const toneMap = '#ifdef LINEAR_TONE_MAPPING';
    const encode = '#ifdef SRGB_TRANSFER';
    const src = this.composedFragment;
    if (!src.includes(toneMap) || !src.includes(encode)) throw new Error('display LUT: OutputShader changed');
    material.fragmentShader = src
      .replace('varying vec2 vUv;', `varying vec2 vUv;\n${DISPLAY_LUT_PARS}`)
      .replace(toneMap, '#if 1\n\t\t\t\tgl_FragColor.rgb = displayLUT( gl_FragColor.rgb * toneMappingExposure );\n\t\t\t#elif defined( LINEAR_TONE_MAPPING )')
      .replace(encode, '#if 0');
    material.needsUpdate = true;
  }

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget) {
    const u = this.uniforms as Record<string, THREE.IUniform>;
    const outline = this.outline;
    u.uOutline.value = outline.enabled && outline.selectedObjects.length > 0 ? 1 : 0;
    // The rim is added before exposure, so dividing it out keeps its on-screen brightness fixed.
    u.uOutlineStrength.value = outline.edgeStrength / Math.max(renderer.toneMappingExposure, 1e-3);
    u.tOutlineMask.value = outline.maskTexture;
    u.tOutlineEdge.value = outline.edgeTexture;
    // OutputPass reads `readBuffer.texture` as its input: hand it the scene instead.
    this.input.texture = this.sceneTexture();
    super.render(renderer, writeBuffer, this.input as unknown as THREE.WebGLRenderTarget, 0, false);
  }
}

export function createRenderer(
  canvas: HTMLCanvasElement,
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
) {
  const params = new URLSearchParams(location.search);
  // Profiling switches (A/B): ?msaa=<samples>  ?pr=<ratio> (fixed, no fallback)  ?adaptive=0
  const forcedRatio = Number(params.get('pr'));
  const adaptive = !(forcedRatio > 0) && params.get('adaptive') !== '0';

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
  let pixelRatio = forcedRatio > 0 ? forcedRatio : Math.min(window.devicePixelRatio, 1.5);
  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  // Fallback until the display LUT arrives (v2Look.ts); the LUT replaces it in the composite.
  renderer.toneMapping = THREE.AgXToneMapping;
  // The props' sun shadow (v2PropLight.ts), drawn once.
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  // The main loop resets once per frame, so counts cover every pass.
  renderer.info.autoReset = false;

  const w = window.innerWidth;
  const h = window.innerHeight;
  // At retina density 2× MSAA is hard to tell from 4× and halves the largest buffer.
  const msaaParam = params.get('msaa');
  const msaaSamples = msaaParam !== null ? Number(msaaParam) : pixelRatio > 1.25 ? 2 : 4;
  // No render target passed in: EffectComposer takes a supplied target's size as its CSS size and
  // multiplies by the pixel ratio again.
  const composer = new EffectComposer(renderer);
  const scenePass = new MultisampleScenePass(scene, camera, msaaSamples);
  composer.addPass(scenePass);

  // No AO depth to share here, so the outline renders its own (at half resolution, only while
  // something is hovered).
  const outline = new SharedDepthOutlinePass(new THREE.Vector2(w, h), scene, camera, () => null, () => camera);
  // A soft warm rim rather than a hard white cut-out, which read as a sticker around small dark objects.
  outline.edgeStrength = 1.0;
  outline.edgeGlow = 0;
  outline.edgeThickness = 1;
  outline.visibleEdgeColor.set('#f3e9da');
  outline.hiddenEdgeColor.set('#20242a');
  outline.enabled = false; // switched on only while something is hovered
  composer.addPass(outline);
  // Attention dots are UI: no outline depth.
  const outlineRender = outline.render.bind(outline) as (...args: unknown[]) => void;
  outline.render = ((...args: unknown[]) => {
    camera.layers.disable(OVERLAY_LAYER);
    outlineRender(...args);
    camera.layers.enable(OVERLAY_LAYER);
  }) as unknown as typeof outline.render;

  const output = new CompositeOutputPass(() => scenePass.texture, outline);
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

  // ---- Environment capture: the baked room as image-based light for the PBR props ---------
  const cubeTarget = new THREE.WebGLCubeRenderTarget(128, { type: THREE.HalfFloatType });
  const cubeCamera = new THREE.CubeCamera(0.05, 30, cubeTarget);
  cubeCamera.position.set(0.0, 1.15, -0.35);
  scene.add(cubeCamera);
  const pmrem = new THREE.PMREMGenerator(renderer);
  let envTarget: THREE.WebGLRenderTarget | null = null;

  function captureEnvironmentNow() {
    // The capture must not see a previous capture reflected in the props.
    scene.environment = null;
    gpu.begin('EnvCapture');
    cubeCamera.update(renderer, scene);
    const next = pmrem.fromCubemap(cubeTarget.texture);
    gpu.end();
    envTarget?.dispose();
    envTarget = next;
    scene.environment = next.texture;
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

  /** Candidate render resolutions, highest first: down to 1×, then (MSAA off first) below it. */
  const RATIO_STEPS = [1.5, 1.25, 1];
  const DEEP_STEPS = [0.85, 0.7];

  /**
   * One rung down the quality ladder: 1.5 → 1.25 → 1, then MSAA off, then 0.85 → 0.7, so weak
   * GPUs still get a smooth frame. Returns false at the floor.
   */
  function stepDownQuality() {
    const next = RATIO_STEPS.find((r) => r < pixelRatio - 0.01);
    if (next !== undefined) return setPixelRatio(Math.min(window.devicePixelRatio, next));
    if (scenePass.samples > 0) {
      scenePass.setSamples(0);
      return true;
    }
    const lower = DEEP_STEPS.find((r) => r < pixelRatio - 0.01);
    return lower === undefined ? false : setPixelRatio(lower);
  }

  /**
   * Safety net only. Calibration has already chosen the quality, so this exists for a machine
   * that gets slower later (another tab, thermal throttling) and steps down a rung.
   */
  const recent = new Float32Array(120);
  let recentCount = 0;
  let clock = 0;
  function watchPerformance(dt: number) {
    clock += dt;
    if (!adaptive || clock < 10) return;
    recent[recentCount % recent.length] = dt;
    recentCount++;
    if (recentCount % 60 !== 0 || recentCount < recent.length) return;
    const median = Float32Array.from(recent).sort()[recent.length >> 1];
    // Start a fresh window after a step, so stale slow frames cannot trigger a second one.
    if (median > 1 / 30 && stepDownQuality()) recentCount = 0;
  }

  /**
   * Compile every shader and capture the environment before the first visible frame.
   * `onStage` fires as each phase genuinely completes, so the loading bar reports real work.
   */
  async function warmUp(samples: THREE.Object3D[] = [], onStage: (stage: string) => void = () => {}) {
    scene.updateMatrixWorld(true);
    // Capture first: materials compiled before the environment exists get the wrong program
    // variant and recompile (synchronously) the first time each object comes into view.
    captureEnvironmentNow();
    onStage('compiling shaders');
    await renderer.compileAsync(scene, camera);
    onStage('warming passes');
    // The outline compiles lazily on first use. Run it once under the veil, so the first hover
    // never hitches: every interactive object at once, from a wide vantage that sees them all.
    if (samples.length) {
      outline.selectedObjects = samples;
      outline.enabled = true;
    }
    const pose = { position: camera.position.clone(), quaternion: camera.quaternion.clone(), fov: camera.fov };
    camera.position.set(0.9, 2.9, 2.9);
    camera.lookAt(-0.2, 0.5, -0.4);
    camera.fov = 85;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    composer.render(0);
    // Real hovers outline one object while the others render into the outline's depth pass as
    // "non-selected", which needs its own shader variants. Warm each.
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
    onStage('measuring');
  }

  return {
    renderer,
    /** Debug/bench access to the post chain; not used by the room itself. */
    composer,
    gpu,
    outline,
    warmUp,
    pixelRatio: () => pixelRatio,
    /** False when the resolution is pinned (`?pr=`), so nothing may change it. */
    adaptive,
    stepDownQuality,
    /** Current MSAA sample count of the scene pass. */
    msaa: () => scenePass.samples,
    captureEnvironmentNow,
    /** Blender's display transform in place of AgX (`null` restores AgX). */
    setDisplayLUT: (lut: DisplayLUT | null) => output.setDisplayLUT(lut),
    resize,
    render(dt: number) {
      composer.render(dt);
      gpu.endFrame();
      watchPerformance(dt);
    },
  };
}
