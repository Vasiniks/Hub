import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { Pass, FullScreenQuad } from 'three/addons/postprocessing/Pass.js';
import { CopyShader } from 'three/addons/shaders/CopyShader.js';
import type { LightState } from './lighting';
import { fadeColor } from './materials';
import { OVERLAY_LAYER } from './layers';
import { VolumetricLightPass } from './volumetric';

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

const GradeShader = {
  uniforms: {
    tDiffuse: { value: null as THREE.Texture | null },
    uTime: { value: 0 },
    uVignette: { value: 0.3 },
    uGrain: { value: 0.03 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
  `,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float uTime, uVignette, uGrain;
    varying vec2 vUv;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      vec2 q = vUv - 0.5;
      float v = smoothstep(0.85, 0.2, length(q * vec2(1.05, 1.25)));
      c.rgb *= mix(1.0 - uVignette, 1.0, v);
      c.rgb += (hash(vUv * vec2(1920.0, 1080.0) + fract(uTime) * 91.0) - 0.5) * uGrain;
      gl_FragColor = c;
    }
  `,
};

export function createRenderer(canvas: HTMLCanvasElement, scene: THREE.Scene, camera: THREE.PerspectiveCamera, sun: THREE.DirectionalLight) {
  const params = new URLSearchParams(location.search);
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
  const target = new THREE.WebGLRenderTarget(w * pixelRatio, h * pixelRatio, { type: THREE.HalfFloatType });
  const composer = new EffectComposer(renderer, target);
  composer.setPixelRatio(pixelRatio);
  composer.addPass(msaaSamples > 0 ? new MultisampleScenePass(scene, camera, msaaSamples) : new RenderPass(scene, camera));

  const gtao = new GTAOPass(scene, camera, w, h);
  // AO is low-frequency: render it at CSS-pixel density, not device density, so retina screens
  // get the same AO detail per point as standard ones without paying 2.25× the fill.
  const aoScale = () => (aoParam === 'full' ? 1 : aoParam === 'half' ? 0.5 : 1 / pixelRatio);
  const baseSetSize = gtao.setSize.bind(gtao);
  gtao.setSize = (width: number, height: number) =>
    baseSetSize(Math.max(1, Math.round(width * aoScale())), Math.max(1, Math.round(height * aoScale())));
  gtao.updateGtaoMaterial({ radius: 0.28, distanceExponent: 1.6, thickness: 1.2, scale: 1.1, samples: 16 });
  gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 5, rings: 2, samples: 16 });
  gtao.blendIntensity = 0.9;
  gtao.enabled = !aoOff;
  composer.addPass(gtao);

  const volumetric = new VolumetricLightPass(camera, sun, () => gtao.depthTexture ?? null);
  volumetric.enabled = volumetricEnabled;
  volumetric.resolutionScale = () => (volScaleParam > 0 ? volScaleParam : 0.4 / pixelRatio);
  composer.addPass(volumetric);

  const outline = new OutlinePass(new THREE.Vector2(w, h), scene, camera);
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

  const bloom = new UnrealBloomPass(new THREE.Vector2(w, h), 0.3, 0.5, 1.15);
  bloom.enabled = params.get('bloom') !== '0';
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  const grade = new ShaderPass(GradeShader);
  composer.addPass(grade);

  // ---- Environment capture: reflections + indirect light from the lit room ----------------
  const cubeTarget = new THREE.WebGLCubeRenderTarget(128, { type: THREE.HalfFloatType });
  const cubeCamera = new THREE.CubeCamera(0.05, 30, cubeTarget);
  cubeCamera.position.set(0.0, 1.15, -0.35);
  scene.add(cubeCamera);
  const pmrem = new THREE.PMREMGenerator(renderer);
  let envTarget: THREE.WebGLRenderTarget | null = null;
  let captureFace = -1;

  function swapEnvironment() {
    const next = pmrem.fromCubemap(cubeTarget.texture);
    envTarget?.dispose();
    envTarget = next;
    scene.environment = next.texture;
  }

  function captureEnvironmentNow() {
    const env = scene.environment;
    scene.environment = null;
    cubeCamera.update(renderer, scene);
    scene.environment = env;
    swapEnvironment();
    captureFace = -1;
  }

  /** Spread a capture over seven frames (one cube face each, then filtering) instead of one hitch. */
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
      renderer.render(scene, cubeCamera.children[captureFace] as THREE.Camera);
      renderer.setRenderTarget(previous);
      scene.environment = env;
      captureFace++;
      return;
    }
    swapEnvironment();
    captureFace = -1;
  }

  function applyLight(state: LightState) {
    renderer.toneMappingExposure = state.exposure;
    scene.environmentIntensity = state.env;
    bloom.strength = state.bloom;
    (scene.background as THREE.Color).copy(state.sky);
    fadeColor.copy(state.sky);
    const fog = scene.fog as THREE.FogExp2;
    fog.color.copy(state.sky);
    fog.density = state.fog;
    volumetric.scatter.copy(state.scatter);
  }

  function resize() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    composer.setSize(width, height);
  }

  // Trade resolution only for sustained slowness after warm-up, judged by the median frame.
  const recent = new Float32Array(120);
  let recentCount = 0;
  let clock = 0;
  function watchPerformance(dt: number) {
    clock += dt;
    if (!adaptive || pixelRatio <= 1 || clock < 6) return;
    recent[recentCount % recent.length] = dt;
    recentCount++;
    if (recentCount % 60 !== 0 || recentCount < recent.length) return;
    const median = Float32Array.from(recent).sort()[recent.length >> 1];
    if (median > 1 / 32) {
      pixelRatio = 1;
      renderer.setPixelRatio(1);
      composer.setPixelRatio(1);
      resize();
    }
  }

  /** Compile every shader and capture the environment before the first visible frame. */
  async function warmUp(samples: THREE.Object3D[] = []) {
    // Capture first: materials compiled before the environment exists get the wrong program
    // variant and recompile (synchronously) the first time each object comes into view.
    captureEnvironmentNow();
    await renderer.compileAsync(scene, camera);
    // Post passes compile lazily on first use. Run the ones that normally sleep (hover outline,
    // daylight shafts) once under the veil, so they never hitch mid-interaction or at dawn.
    const scatter = volumetric.scatter.clone();
    if (scatter.r + scatter.g + scatter.b < 1e-4) volumetric.scatter.setRGB(0.001, 0.001, 0.001);
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
  }

  return {
    renderer,
    outline,
    volumetric,
    warmUp,
    captureEnvironmentNow,
    requestEnvironmentCapture,
    applyLight,
    resize,
    render(dt: number, time: number, animateGrain: boolean) {
      stepCapture();
      grade.uniforms.uTime.value = animateGrain ? time : 0;
      composer.render(dt);
      watchPerformance(dt);
    },
  };
}
