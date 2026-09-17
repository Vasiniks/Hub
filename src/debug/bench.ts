import * as THREE from 'three';
import type { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import type { Pass } from 'three/addons/postprocessing/Pass.js';

/**
 * Debug-only GPU cost bench (`?debug`, loaded on demand).
 *
 * WebGL timer queries on this ANGLE/Metal path report queueing, not pass cost, so everything
 * here is timed against a GPU fence: run the work N times, wait until the GPU has genuinely
 * finished, divide. Feature costs are A/B deltas taken in alternating rounds on the same page, so
 * thermal drift — which moves absolute numbers by 50% over a long session — cancels out.
 */
export interface BenchContext {
  renderer: THREE.WebGLRenderer;
  composer: EffectComposer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  pause: (on: boolean) => void;
}

function fence(gl: WebGL2RenderingContext) {
  const sync = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
  if (!sync) return Promise.resolve();
  gl.flush();
  return new Promise<void>((resolve) => {
    const poll = () => {
      const s = gl.clientWaitSync(sync, 0, 0);
      if (s === gl.ALREADY_SIGNALED || s === gl.CONDITION_SATISFIED || s === gl.WAIT_FAILED) {
        gl.deleteSync(sync);
        resolve();
      } else setTimeout(poll, 0);
    };
    poll();
  });
}

export function createBench(ctx: BenchContext) {
  const { renderer, composer, scene, camera } = ctx;
  const gl = renderer.getContext() as WebGL2RenderingContext;

  async function time(fn: () => void, frames: number) {
    fn();
    await fence(gl);
    const t0 = performance.now();
    for (let i = 0; i < frames; i++) fn();
    const cpu = performance.now() - t0;
    await fence(gl);
    const total = performance.now() - t0;
    return { total: total / frames, cpu: cpu / frames };
  }

  /** Alternating A/B rounds; returns mean ms for each side. */
  async function ab(label: string, fn: () => void, enable: () => void, disable: () => void, rounds = 5, frames = 12) {
    let a = 0;
    let b = 0;
    for (let r = 0; r < rounds; r++) {
      enable();
      a += (await time(fn, frames)).total;
      disable();
      b += (await time(fn, frames)).total;
    }
    enable();
    return { label, with: +(a / rounds).toFixed(2), without: +(b / rounds).toFixed(2), cost: +((a - b) / rounds).toFixed(2) };
  }

  const passNamed = (name: string) => composer.passes.find((p) => p.constructor.name === name) as (Pass & Record<string, unknown>) | undefined;
  const lightNamed = (name: string) => {
    let found: THREE.Object3D | undefined;
    scene.traverse((o) => {
      if (o.name === name && (o as THREE.Light).isLight) found = o;
    });
    return found;
  };

  return {
    /**
     * Park the camera, then measure the frame and each pass/feature. `aoLive` forces AO to
     * recompute every frame, which is what turning the head costs.
     */
    async run(pose: { p: number[]; t: number[]; fov: number; quick?: boolean }) {
      ctx.pause(true);
      const saved = { pos: camera.position.clone(), quat: camera.quaternion.clone(), fov: camera.fov };
      camera.position.fromArray(pose.p);
      camera.lookAt(new THREE.Vector3().fromArray(pose.t));
      camera.fov = pose.fov;
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld();
      const ao = passNamed('CachedGTAOPass') as unknown as { invalid: boolean; caching: boolean } & Record<string, unknown>;
      const frame = () => {
        if (ao) ao.invalid = true;
        composer.render(0);
      };
      const idleFrame = () => composer.render(0);
      const results: Record<string, unknown> = {};

      // Warm every variant once so no compile lands inside a timing.
      for (let i = 0; i < 4; i++) frame();
      await fence(gl);

      const look = await time(frame, 20);
      const idle = await time(idleFrame, 20);
      results.frame = { look: +look.total.toFixed(2), lookCpu: +look.cpu.toFixed(2), idle: +idle.total.toFixed(2), idleCpu: +idle.cpu.toFixed(2) };
      renderer.info.reset();
      frame();
      results.calls = renderer.info.render.calls;
      results.triangles = renderer.info.render.triangles;
      if (pose.quick) {
        camera.position.copy(saved.pos);
        camera.quaternion.copy(saved.quat);
        camera.fov = saved.fov;
        camera.updateProjectionMatrix();
        ctx.pause(false);
        return results;
      }

      const passes: unknown[] = [];
      for (const pass of composer.passes) {
        const name = pass.constructor.name;
        if (!pass.enabled || name === 'GradedOutputPass') continue;
        passes.push(await ab(`pass:${name}`, frame, () => (pass.enabled = true), () => (pass.enabled = false)));
      }
      results.passes = passes;

      // GTAO internals, timed directly.
      if (ao) {
        const g = ao as unknown as {
          _overrideVisibility(): void;
          _restoreVisibility(): void;
          _renderOverride(r: THREE.WebGLRenderer, m: THREE.Material, t: THREE.WebGLRenderTarget, c: number, a: number): void;
          _renderPass(r: THREE.WebGLRenderer, m: THREE.Material, t: THREE.WebGLRenderTarget | null, c?: number, a?: number): void;
          normalMaterial: THREE.Material;
          normalRenderTarget: THREE.WebGLRenderTarget;
          gtaoMaterial: THREE.Material;
          gtaoRenderTarget: THREE.WebGLRenderTarget;
          pdMaterial: THREE.Material;
          pdRenderTarget: THREE.WebGLRenderTarget;
        };
        const normal = await time(() => {
          g._overrideVisibility();
          g._renderOverride(renderer, g.normalMaterial, g.normalRenderTarget, 0x7777ff, 1.0);
          g._restoreVisibility();
        }, 20);
        const aoPass = await time(() => g._renderPass(renderer, g.gtaoMaterial, g.gtaoRenderTarget, 0xffffff, 1.0), 20);
        const denoise = await time(() => g._renderPass(renderer, g.pdMaterial, g.pdRenderTarget, 0xffffff, 1.0), 20);
        results.gtao = {
          normalPass: +normal.total.toFixed(2),
          aoShader: +aoPass.total.toFixed(2),
          denoise: +denoise.total.toFixed(2),
          aoTarget: [g.gtaoRenderTarget.width, g.gtaoRenderTarget.height],
        };
        renderer.setRenderTarget(null);
      }

      // Lighting features inside the scene pass: toggles change shader variants, so each side is
      // warmed inside `ab` by its first untimed render.
      const features: unknown[] = [];
      for (const name of ['sky', 'screenGlow', 'underGlow', 'shelfLight', 'hemi', 'lamp', 'sun']) {
        const light = lightNamed(name);
        if (!light) continue;
        features.push(await ab(`light:${name}`, frame, () => (light.visible = true), () => (light.visible = false), 4, 10));
      }
      const env = scene.environment;
      features.push(await ab('environment map', frame, () => (scene.environment = env), () => (scene.environment = null), 4, 10));
      features.push(
        await ab('shadow sampling', frame, () => (renderer.shadowMap.enabled = true), () => (renderer.shadowMap.enabled = false), 4, 10),
      );
      results.features = features;

      // Shadow-map redraw cost (normally only when something moves or the sun turns).
      const sun = lightNamed('sun') as THREE.DirectionalLight | undefined;
      const lamp = lightNamed('lamp') as THREE.SpotLight | undefined;
      if (sun && lamp) {
        results.shadowRedraw = [
          await ab('sun shadow redraw', frame, () => (sun.shadow.needsUpdate = true), () => (sun.shadow.needsUpdate = false), 4, 1),
          await ab('lamp shadow redraw', frame, () => (lamp.shadow.needsUpdate = true), () => (lamp.shadow.needsUpdate = false), 4, 1),
        ];
      }

      camera.position.copy(saved.pos);
      camera.quaternion.copy(saved.quat);
      camera.fov = saved.fov;
      camera.updateProjectionMatrix();
      ctx.pause(false);
      return results;
    },
  };
}
