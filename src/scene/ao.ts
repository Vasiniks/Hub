import * as THREE from 'three';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';

/**
 * Ambient occlusion that is only recomputed when it could have changed.
 *
 * Profiling put GTAO at over a third of the whole frame — sixteen horizon samples and a
 * sixteen-tap denoise on every pixel, every frame. But occlusion depends on nothing except
 * geometry and the camera: not on the time of day, not on exposure, not on the lamp. While the
 * camera has shifted by less than a fraction of a pixel and nothing on screen has moved, last
 * frame's denoised result is still the correct answer, so it is reused and only blended.
 *
 * The idle breathing of the camera moves the view by about a pixel every few frames, so a
 * resting view still refreshes several times a second — the result can never drift visibly —
 * while a turning head recomputes every frame, exactly as before.
 *
 * The blend itself is also cheaper than stock: it is a pure multiply, so it is applied to the
 * image in place instead of copying the whole frame to a second buffer first.
 *
 * While the view is actually moving, occlusion is traced and denoised at half resolution (a
 * quarter of the pixels): depth and normals, trace and denoise together, ~1 ms instead of ~3.3 at
 * 1440×900. Half resolution softens thin geometry (the lamp's arms gain a faint halo),
 * which a turning head cannot see; once the view has been still for a moment the full-resolution
 * result is computed once and faded in over a fifth of a second, so nothing pops.
 */
const _q = new THREE.Quaternion();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();

/** Seconds the view must be still before full resolution returns (hysteresis against flicker). */
const SETTLE_SECONDS = 0.12;
/** Crossfade from the half-resolution result to the full one. */
const FADE_SECONDS = 0.2;
/** Apparent view speed, in CSS pixels per frame, that counts as moving (idle breathing is well below). */
const MOVING_PX_PER_FRAME = 0.6;

const blendFragment = /* glsl */ `
  uniform float intensity;
  uniform float fade;
  uniform sampler2D tDiffuse;
  uniform sampler2D tPrevious;
  varying vec2 vUv;
  void main() {
    vec4 texel = texture2D( tDiffuse, vUv );
    if ( fade < 1.0 ) texel = mix( texture2D( tPrevious, vUv ), texel, fade );
    gl_FragColor = vec4( mix( vec3( 1. ), texel.rgb, intensity ), texel.a );
  }`;

interface TargetSet {
  gtao: THREE.WebGLRenderTarget;
  pd: THREE.WebGLRenderTarget;
  normal: THREE.WebGLRenderTarget;
}

interface Internals {
  normalRenderTarget: THREE.WebGLRenderTarget;
  depthRenderMaterial: THREE.ShaderMaterial;
  gtaoRenderTarget: THREE.WebGLRenderTarget;
  pdRenderTarget: THREE.WebGLRenderTarget;
  gtaoMaterial: THREE.ShaderMaterial;
  pdMaterial: THREE.ShaderMaterial;
  blendMaterial: THREE.ShaderMaterial;
  _renderPass(r: THREE.WebGLRenderer, m: THREE.Material, t: THREE.WebGLRenderTarget | null): void;
}

export class CachedGTAOPass extends GTAOPass {
  /** Set by the owner when something on screen has moved. */
  invalid = true;
  /** True on frames where AO was actually recomputed (the owner re-baselines its motion checks). */
  computedThisFrame = false;
  /** Largest allowed apparent shift, in CSS pixels, before AO is recomputed. */
  pixelTolerance = 1.0;
  /** Depth used to turn camera translation into parallax: roughly the nearest desk objects. */
  parallaxDepth = 0.5;
  caching = true;
  /** Trace at half resolution while the view moves (see above). */
  adaptiveResolution = true;
  /** Debug (`?aomoving`): always take the moving path, to inspect it in still captures. */
  forceMoving = new URLSearchParams(location.search).has('aomoving');
  /** Resolution of the last result, for tests: 1 full, 0.5 half. */
  lastScale = 1;

  private readonly lastPos = new THREE.Vector3();
  private readonly lastQuat = new THREE.Quaternion();
  private lastFov = 0;
  private lastAspect = 0;
  private readonly framePos = new THREE.Vector3();
  private readonly frameQuat = new THREE.Quaternion();
  private frameFov = 0;
  private lastTime = 0;
  private stillSeconds = Infinity;
  private invalidLastFrame = false;
  private fade = 1;
  private readonly full: TargetSet;
  private readonly half: TargetSet;

  constructor(scene: THREE.Scene, camera: THREE.PerspectiveCamera, width: number, height: number) {
    super(scene, camera, width, height);
    // Blended in place (see render), so the composer must not swap buffers after this pass.
    this.needsSwap = false;
    const own = this as unknown as Internals;
    this.full = { gtao: own.gtaoRenderTarget, pd: own.pdRenderTarget, normal: own.normalRenderTarget };
    const halfNormal = new THREE.WebGLRenderTarget(1, 1, {
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      type: THREE.HalfFloatType,
      depthTexture: new THREE.DepthTexture(1, 1, THREE.UnsignedInt248Type, undefined, undefined, undefined, undefined, undefined, undefined, THREE.DepthStencilFormat),
    });
    this.half = { gtao: own.gtaoRenderTarget.clone(), pd: own.pdRenderTarget.clone(), normal: halfNormal };
    this.sizeHalf(width, height);
    own.blendMaterial.uniforms.fade = { value: 1 };
    own.blendMaterial.uniforms.tPrevious = { value: null };
    own.blendMaterial.fragmentShader = blendFragment;
    own.blendMaterial.needsUpdate = true;
  }

  setSize(width: number, height: number) {
    this.use(this.full, 1);
    super.setSize(width, height);
    if (this.half) this.sizeHalf(width, height);
    this.invalid = true;
  }

  private sizeHalf(width: number, height: number) {
    const w = Math.max(1, width >> 1);
    const h = Math.max(1, height >> 1);
    this.half.gtao.setSize(w, h);
    this.half.pd.setSize(w, h);
    this.half.normal.setSize(w, h);
  }


  dispose() {
    this.use(this.full, 1);
    this.half.gtao.dispose();
    this.half.pd.dispose();
    this.half.normal.dispose();
    super.dispose();
  }

  /** Point the stock pass at one set of AO targets, with matching texel sizes. */
  private use(set: TargetSet | undefined, scale: number) {
    if (!set) return;
    const own = this as unknown as Internals;
    // Depth and normals switch too: the outline and light shafts read this depth, and measured no
    // visible difference from half resolution while moving (0.5 ms less per moving frame).
    const normal = set.normal;
    if (own.normalRenderTarget !== normal) {
      own.normalRenderTarget = normal;
      this.depthTexture = normal.depthTexture as THREE.DepthTexture;
      this.normalTexture = normal.texture;
      for (const m of [own.gtaoMaterial, own.pdMaterial]) {
        m.uniforms.tNormal.value = normal.texture;
        m.uniforms.tDepth.value = normal.depthTexture;
      }
      own.depthRenderMaterial.uniforms.tDepth.value = normal.depthTexture;
    }
    own.gtaoRenderTarget = set.gtao;
    own.pdRenderTarget = set.pd;
    own.gtaoMaterial.uniforms.resolution.value.set(set.gtao.width, set.gtao.height);
    own.pdMaterial.uniforms.resolution.value.set(set.pd.width, set.pd.height);
    own.pdMaterial.uniforms.tDiffuse.value = set.gtao.texture;
    // Same footprint on screen at either resolution.
    own.pdMaterial.uniforms.radius.value = this.denoiseRadius * scale;
  }

  /** Denoise radius at full resolution, in texels. */
  denoiseRadius = 5;

  /** CSS pixels the view has shifted since the previous frame (for motion, not for cache validity). */
  private frameShiftPx() {
    const camera = this.camera as THREE.PerspectiveCamera;
    camera.matrixWorld.decompose(_p, _q, _s);
    const fovChanged = camera.fov !== this.frameFov;
    const angle = 2 * Math.acos(Math.min(1, Math.abs(_q.dot(this.frameQuat))));
    const parallax = _p.distanceTo(this.framePos) / this.parallaxDepth;
    this.framePos.copy(_p);
    this.frameQuat.copy(_q);
    this.frameFov = camera.fov;
    if (fovChanged) return Infinity;
    return (angle + parallax) * (window.innerHeight / THREE.MathUtils.degToRad(camera.fov));
  }

  private viewShiftPx() {
    const camera = this.camera as THREE.PerspectiveCamera;
    camera.matrixWorld.decompose(_p, _q, _s);
    if (camera.fov !== this.lastFov || camera.aspect !== this.lastAspect) return Infinity;
    const angle = 2 * Math.acos(Math.min(1, Math.abs(_q.dot(this.lastQuat))));
    const parallax = _p.distanceTo(this.lastPos) / this.parallaxDepth;
    const pxPerRadian = window.innerHeight / THREE.MathUtils.degToRad(camera.fov);
    return (angle + parallax) * pxPerRadian;
  }

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    // Debug outputs (AO, denoise, normals) keep the stock path.
    if (this.output !== GTAOPass.OUTPUT.Default) {
      this.needsSwap = true;
      super.render(renderer, writeBuffer, readBuffer, 0, false);
      return;
    }
    this.needsSwap = false;

    const camera = this.camera as THREE.PerspectiveCamera;
    const now = performance.now() / 1000;
    const dt = this.lastTime ? Math.min(0.1, now - this.lastTime) : 0;
    this.lastTime = now;
    const own = this as unknown as Internals;

    // Moving: the view is sweeping, or on-screen geometry has invalidated AO two frames running.
    const moving = this.forceMoving || this.frameShiftPx() > MOVING_PX_PER_FRAME || (this.invalid && this.invalidLastFrame);
    this.invalidLastFrame = this.invalid;
    this.stillSeconds = moving ? 0 : this.stillSeconds + dt;
    const wantScale = this.adaptiveResolution && this.stillSeconds < SETTLE_SECONDS ? 0.5 : 1;

    const stale = !this.caching || this.invalid || this.viewShiftPx() > this.pixelTolerance;
    // Settled after moving: the half-resolution result is still valid, but upgrade it.
    const upgrade = wantScale === 1 && this.lastScale === 0.5;
    this.computedThisFrame = stale || upgrade;
    if (this.computedThisFrame) {
      if (upgrade) {
        // Fade from what is on screen now to the sharper result.
        this.fade = 0;
        own.blendMaterial.uniforms.tPrevious.value = this.half.pd.texture;
      } else if (wantScale === 0.5) this.fade = 1;
      // (A full-resolution refresh mid-fade, from idle breathing, lets the fade run on.)
      this.use(wantScale === 1 ? this.full : this.half, wantScale);
      // `Off` makes the stock pass compute G-buffer, AO and denoise, and stop before output.
      this.output = GTAOPass.OUTPUT.Off;
      super.render(renderer, writeBuffer, readBuffer, 0, false);
      this.output = GTAOPass.OUTPUT.Default;
      this.lastScale = wantScale;
      camera.matrixWorld.decompose(this.lastPos, this.lastQuat, _s);
      this.lastFov = camera.fov;
      this.lastAspect = camera.aspect;
      this.invalid = false;
    }
    if (this.fade < 1 && !upgrade) this.fade = Math.min(1, this.fade + dt / FADE_SECONDS);

    const blend = own.blendMaterial.uniforms;
    blend.intensity.value = this.blendIntensity;
    blend.fade.value = this.fade;
    blend.tDiffuse.value = own.pdRenderTarget.texture;
    own._renderPass(renderer, own.blendMaterial, this.renderToScreen ? null : readBuffer);
  }
}
