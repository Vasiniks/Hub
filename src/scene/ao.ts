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
 * Nothing is blended here: the final composite (renderer.ts) multiplies the result into the image,
 * so this pass writes no full-resolution buffer at all.
 *
 * Turning the head does not invalidate it either. Occlusion belongs to surfaces, and from a fixed
 * eye a rotation only changes where on screen each surface lands — so the result is computed for a
 * slightly wider view than the screen (a guard band) and the final composite maps each pixel into
 * it with one 3×3 homography. No history, no blending across frames: a single warp of a buffer
 * computed moments ago for the same eye, so there is nothing to ghost. It is recomputed only when
 * the eye translates, something on screen moves, the view turns past the guard band, or the
 * resolution upgrades. The light shafts share the same snapshot (see volumetric.ts).
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
/** Extra view on each side, as a fraction of the screen's half-extent, computed for reprojection. */
export const GUARD_BAND = 0.14;
export const GUARD_SCALE = 1 + GUARD_BAND;

/** The view a buffer was computed for, and the map from the current screen into it. */
export class ViewSnapshot {
  readonly camera = new THREE.PerspectiveCamera();
  private readonly viewFromWorld = new THREE.Matrix4();
  private readonly _m = new THREE.Matrix4();
  private readonly _a = new THREE.Matrix3();
  private readonly _h = new THREE.Vector3();

  /** Take the current camera's eye and orientation, widened by the guard band. */
  capture(main: THREE.PerspectiveCamera) {
    main.updateMatrixWorld();
    this.camera.position.setFromMatrixPosition(main.matrixWorld);
    this.camera.quaternion.setFromRotationMatrix(this._m.extractRotation(main.matrixWorld));
    this.camera.aspect = main.aspect;
    this.camera.near = main.near;
    this.camera.far = main.far;
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(main.fov) / 2) * GUARD_SCALE));
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld(true);
    this.viewFromWorld.copy(this.camera.matrixWorld).invert();
  }

  /**
   * Homography from the current screen's NDC (x, y, 1) to this snapshot's NDC (after dividing by z).
   * Rotation only: the eye translates by millimetres at most while a snapshot is in use.
   */
  reprojection(main: THREE.PerspectiveCamera, out: THREE.Matrix3) {
    const tanY = Math.tan(THREE.MathUtils.degToRad(main.fov) / 2);
    const tanX = tanY * main.aspect;
    const snapTanY = Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2);
    const snapTanX = snapTanY * this.camera.aspect;
    // Rotation part of snapshot-view-from-current-view.
    this._m.multiplyMatrices(this.viewFromWorld, main.matrixWorld);
    const r = this._a.setFromMatrix4(this._m);
    const e = r.elements; // column-major
    // A = R · diag(tanX, tanY, -1); H = diag(1/snapTanX, 1/snapTanY, -1) · A
    const cx = [tanX, tanY, -1];
    const rs = [1 / snapTanX, 1 / snapTanY, -1];
    const h = out.elements;
    for (let col = 0; col < 3; col++) for (let row = 0; row < 3; row++) h[col * 3 + row] = rs[row] * e[col * 3 + row] * cx[col];
    return out;
  }

  /** True while every corner of the current screen still lands inside this snapshot. */
  covers(main: THREE.PerspectiveCamera, scratch: THREE.Matrix3) {
    const H = this.reprojection(main, scratch);
    for (const x of [-1, 1])
      for (const y of [-1, 1]) {
        const v = this._h.set(x, y, 1).applyMatrix3(H);
        if (v.z <= 0) return false;
        if (Math.abs(v.x / v.z) > 1 || Math.abs(v.y / v.z) > 1) return false;
      }
    return true;
  }
}


interface TargetSet {
  gtao: THREE.WebGLRenderTarget;
  pd: THREE.WebGLRenderTarget;
  normal: THREE.WebGLRenderTarget;
  /** The view the result in these targets was computed for. */
  view: ViewSnapshot;
}

interface Internals {
  normalRenderTarget: THREE.WebGLRenderTarget;
  depthRenderMaterial: THREE.ShaderMaterial;
  gtaoRenderTarget: THREE.WebGLRenderTarget;
  pdRenderTarget: THREE.WebGLRenderTarget;
  gtaoMaterial: THREE.ShaderMaterial;
  pdMaterial: THREE.ShaderMaterial;
}

export class CachedGTAOPass extends GTAOPass {
  /** Set by the owner when something on screen has moved. */
  invalid = true;
  /** True on frames where AO was actually recomputed (the owner re-baselines its motion checks). */
  computedThisFrame = false;
  /**
   * Eye travel (m) a snapshot is reprojected through before AO is recomputed. The composite corrects
   * translation per pixel from the snapshot's depth, so the breathing bob (a few millimetres) no
   * longer forces recomputes; the limit only guards disocclusion, which appears over centimetres.
   */
  translationTolerance = 0.012;
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
  /** The camera the room is actually seen through; this pass renders through snapshot cameras. */
  private readonly main: THREE.PerspectiveCamera;
  private current: TargetSet;
  private readonly _corners = new THREE.Matrix3();

  constructor(scene: THREE.Scene, camera: THREE.PerspectiveCamera, width: number, height: number) {
    const fullView = new ViewSnapshot();
    fullView.capture(camera);
    super(scene, fullView.camera, width, height);
    this.main = camera;
    this.needsSwap = false;
    const own = this as unknown as Internals;
    this.full = { gtao: own.gtaoRenderTarget, pd: own.pdRenderTarget, normal: own.normalRenderTarget, view: fullView };
    const halfNormal = new THREE.WebGLRenderTarget(1, 1, {
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      type: THREE.HalfFloatType,
      depthTexture: new THREE.DepthTexture(1, 1, THREE.UnsignedInt248Type, undefined, undefined, undefined, undefined, undefined, undefined, THREE.DepthStencilFormat),
    });
    this.half = { gtao: own.gtaoRenderTarget.clone(), pd: own.pdRenderTarget.clone(), normal: halfNormal, view: new ViewSnapshot() };
    this.current = this.full;
    this.sizeHalf(width, height);
  }

  /** Sizes are for the screen; the targets also hold the guard band. */
  setSize(width: number, height: number) {
    this.use(this.full, 1);
    super.setSize(Math.round(width * GUARD_SCALE), Math.round(height * GUARD_SCALE));
    if (this.half) this.sizeHalf(width, height);
    this.invalid = true;
  }

  private sizeHalf(width: number, height: number) {
    const w = Math.max(1, Math.round(width * GUARD_SCALE) >> 1);
    const h = Math.max(1, Math.round(height * GUARD_SCALE) >> 1);
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
    this.camera = set.view.camera;
    this.current = set;
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
    const camera = this.main;
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

  /**
   * Whether the current result can still be reprojected: the eye has not translated by more than
   * the tolerance in parallax, the lens is unchanged, and the view is still inside the guard band.
   */
  private reusable() {
    const camera = this.main;
    camera.matrixWorld.decompose(_p, _q, _s);
    if (camera.fov !== this.lastFov || camera.aspect !== this.lastAspect) return false;
    if (_p.distanceTo(this.lastPos) > this.translationTolerance) return false;
    return this.current.view.covers(camera, this._corners);
  }

  /** The occlusion to multiply the image by (denoised, at whichever resolution was last computed). */
  get texture() {
    return (this as unknown as Internals).pdRenderTarget.texture;
  }

  /** The snapshot `texture` and the depth were computed for. */
  get view() {
    return this.current.view;
  }

  /** While fading up to full resolution: the half-resolution result being faded from, and progress. */
  get previousTexture() {
    return this.half.pd.texture;
  }

  get previousView() {
    return this.half.view;
  }

  get fadeProgress() {
    return this.fade;
  }

  /**
   * Computes occlusion when it could have changed. It no longer draws anything onto the image:
   * the final composite multiplies it in, so no full-resolution buffer is written here.
   */
  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    const camera = this.main;
    const now = performance.now() / 1000;
    const dt = this.lastTime ? Math.min(0.1, now - this.lastTime) : 0;
    this.lastTime = now;

    // Moving: the view is sweeping, or on-screen geometry has invalidated AO two frames running.
    const moving = this.forceMoving || this.frameShiftPx() > MOVING_PX_PER_FRAME || (this.invalid && this.invalidLastFrame);
    this.invalidLastFrame = this.invalid;
    this.stillSeconds = moving ? 0 : this.stillSeconds + dt;
    const wantScale = this.adaptiveResolution && this.stillSeconds < SETTLE_SECONDS ? 0.5 : 1;

    const stale = !this.caching || this.invalid || !this.reusable();
    // Settled after moving: the half-resolution result is still valid, but upgrade it.
    const upgrade = wantScale === 1 && this.lastScale === 0.5;
    this.computedThisFrame = stale || upgrade;
    if (this.computedThisFrame) {
      if (upgrade) {
        // Fade from what is on screen now to the sharper result.
        this.fade = 0;
      } else if (wantScale === 0.5) this.fade = 1;
      // (A full-resolution refresh mid-fade, from idle breathing, lets the fade run on.)
      const set = wantScale === 1 ? this.full : this.half;
      set.view.capture(camera);
      this.use(set, wantScale);
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

  }
}
