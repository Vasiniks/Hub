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

  function measureOverdraw() {
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    const target = new THREE.WebGLRenderTarget(size.x, size.y, { depthBuffer: true });
    const make = (transparent: boolean) =>
      new THREE.MeshBasicMaterial({ color: new THREE.Color(1 / 255, 1 / 255, 1 / 255), transparent, blending: THREE.AdditiveBlending, depthWrite: !transparent, depthTest: true, toneMapped: false, fog: false });
    const counters = { opaque: make(false), transparent: make(true) };
    const swapped: [THREE.Mesh, THREE.Material | THREE.Material[]][] = [];
    const ids = new Map<THREE.Object3D, number>();
    scene.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const m = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
      ids.set(mesh, (m as unknown as { id: number }).id);
      swapped.push([mesh, mesh.material]);
      mesh.material = m.transparent ? counters.transparent : counters.opaque;
    });
    const measure = (only: 'opaque' | 'transparent' | 'all') => {
      counters.opaque.visible = only !== 'transparent';
      counters.transparent.visible = only !== 'opaque';
      // Same order as three's default opaque sort, keyed on the original material.
      renderer.setOpaqueSort((a, b) => a.groupOrder - b.groupOrder || a.renderOrder - b.renderOrder || (ids.get(a.object) ?? 0) - (ids.get(b.object) ?? 0) || a.z - b.z || a.id - b.id);
      const background = scene.background;
      scene.background = null;
      renderer.setRenderTarget(target);
      renderer.setClearColor(0x000000, 1);
      renderer.clear();
      renderer.render(scene, camera);
      scene.background = background;
      const px = new Uint8Array(size.x * size.y * 4);
      renderer.readRenderTargetPixels(target, 0, 0, size.x, size.y, px);
      let sum = 0;
      let covered = 0;
      const hist = [0, 0, 0, 0, 0];
      for (let i = 0; i < px.length; i += 4) {
        sum += px[i];
        if (px[i] > 0) covered++;
        hist[Math.min(4, px[i])]++;
      }
      const n = size.x * size.y;
      return { fragmentsPerPixel: +(sum / n).toFixed(2), coverage: +(covered / n).toFixed(2), share: hist.map((h) => +(h / n).toFixed(3)) };
    };
    const out = { opaque: measure('opaque'), transparent: measure('transparent'), all: measure('all'), opaqueFrontToBack: { fragmentsPerPixel: 0 } };
    renderer.setOpaqueSort((a, b) => a.z - b.z);
    counters.opaque.visible = true;
    counters.transparent.visible = false;
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene, camera);
    {
      const px = new Uint8Array(size.x * size.y * 4);
      renderer.readRenderTargetPixels(target, 0, 0, size.x, size.y, px);
      let sum = 0;
      for (let i = 0; i < px.length; i += 4) sum += px[i];
      out.opaqueFrontToBack.fragmentsPerPixel = +(sum / (size.x * size.y)).toFixed(2);
    }
    renderer.setOpaqueSort(null);
    for (const [mesh, m] of swapped) mesh.material = m;
    renderer.setRenderTarget(null);
    target.dispose();
    counters.opaque.dispose();
    counters.transparent.dispose();
    return out;
  }

  return {
    /**
     * Park the camera, then measure the frame and each pass/feature. `aoLive` forces AO to
     * recompute every frame, which is what turning the head costs.
     */
    async run(pose: { p: number[]; t: number[]; fov: number; quick?: boolean; materials?: boolean; overdraw?: boolean }) {
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
      // Real turning: the camera yaws a fixed step every frame and oscillates, nothing forced, so
      // every reuse path behaves as it does under the mouse. 0.25°/frame ≈ 30°/s at 120 Hz.
      const baseQuat = camera.quaternion.clone();
      const turnAt = (degPerFrame: number) => {
        let angle = 0;
        let dir = 1;
        const q = new THREE.Quaternion();
        return () => {
          angle += dir * degPerFrame;
          if (Math.abs(angle) > 20) dir = -dir;
          q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad(angle));
          camera.quaternion.copy(q).multiply(baseQuat);
          camera.updateMatrixWorld();
          composer.render(0);
        };
      };
      for (let i = 0; i < 30; i++) turnAt(0.25)();
      const turnSlow = await time(turnAt(0.25), 60);
      const turnFast = await time(turnAt(1), 60);
      camera.quaternion.copy(baseQuat);
      camera.updateMatrixWorld();
      results.frame = {
        look: +look.total.toFixed(2),
        lookCpu: +look.cpu.toFixed(2),
        idle: +idle.total.toFixed(2),
        idleCpu: +idle.cpu.toFixed(2),
        turnSlow: +turnSlow.total.toFixed(2),
        turnFast: +turnFast.total.toFixed(2),
      };
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

      // Per-material cost of the scene: every mesh drawing with one material hidden at once. Idle
      // frames (AO cached), so the delta is what that material costs the scene and post passes.
      if (pose.materials) {
        const frustum = new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse));
        const byMaterial = new Map<THREE.Material, THREE.Mesh[]>();
        scene.traverse((o) => {
          const mesh = o as THREE.Mesh;
          if (!mesh.isMesh || !mesh.visible || !mesh.layers.test(camera.layers)) return;
          if (mesh.frustumCulled && !frustum.intersectsObject(mesh)) return;
          for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
            if (!byMaterial.has(m)) byMaterial.set(m, []);
            byMaterial.get(m)!.push(mesh);
          }
        });
        const rows: { label: string; with: number; without: number; cost: number }[] = [];
        for (const [m, meshes] of byMaterial) {
          const label = `${m.name || meshes.map((x) => x.name || x.parent?.name || '?').slice(0, 2).join('+')}${m.transparent ? ' (T)' : ''} ×${meshes.length}`;
          rows.push(await ab(label, idleFrame, () => meshes.forEach((x) => (x.visible = true)), () => meshes.forEach((x) => (x.visible = false)), 3, 10));
        }
        const transparent = [...byMaterial].filter(([m]) => m.transparent).flatMap(([, ms]) => ms);
        rows.push(await ab(`ALL transparent ×${transparent.length}`, idleFrame, () => transparent.forEach((x) => (x.visible = true)), () => transparent.forEach((x) => (x.visible = false)), 4, 10));
        results.materials = rows.sort((a, b) => b.cost - a.cost);
      }

      // Depth complexity: every mesh drawn in its real order with a material that adds 1/255 per
      // shaded fragment. Opaque keeps three's material-id-first sort (the original material's id).
      if (pose.overdraw) results.overdraw = measureOverdraw();

      const output = composer.passes[composer.passes.length - 1];
      const outputTime = await time(() => output.render(renderer, composer.writeBuffer, composer.readBuffer, 0, false), 20);
      results.outputPass = +outputTime.total.toFixed(2);

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
