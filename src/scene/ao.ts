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
 */
const _q = new THREE.Quaternion();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();

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

  private readonly lastPos = new THREE.Vector3();
  private readonly lastQuat = new THREE.Quaternion();
  private lastFov = 0;
  private lastAspect = 0;

  constructor(scene: THREE.Scene, camera: THREE.PerspectiveCamera, width: number, height: number) {
    super(scene, camera, width, height);
    // Blended in place (see render), so the composer must not swap buffers after this pass.
    this.needsSwap = false;
  }

  setSize(width: number, height: number) {
    super.setSize(width, height);
    this.invalid = true;
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
    this.computedThisFrame = !this.caching || this.invalid || this.viewShiftPx() > this.pixelTolerance;
    if (this.computedThisFrame) {
      // `Off` makes the stock pass compute G-buffer, AO and denoise, and stop before output.
      this.output = GTAOPass.OUTPUT.Off;
      super.render(renderer, writeBuffer, readBuffer, 0, false);
      this.output = GTAOPass.OUTPUT.Default;
      camera.matrixWorld.decompose(this.lastPos, this.lastQuat, _s);
      this.lastFov = camera.fov;
      this.lastAspect = camera.aspect;
      this.invalid = false;
    }

    const internals = this as unknown as {
      blendMaterial: THREE.ShaderMaterial;
      pdRenderTarget: THREE.WebGLRenderTarget;
      _renderPass(r: THREE.WebGLRenderer, m: THREE.Material, t: THREE.WebGLRenderTarget | null): void;
    };
    internals.blendMaterial.uniforms.intensity.value = this.blendIntensity;
    internals.blendMaterial.uniforms.tDiffuse.value = internals.pdRenderTarget.texture;
    internals._renderPass(renderer, internals.blendMaterial, this.renderToScreen ? null : readBuffer);
  }
}
