import * as THREE from 'three';
import type { DisplayLUT } from '../scene/renderer';
import type { BakedRoom } from '../scene/bakedRoom';

/**
 * Debug-only hooks for the v2 look work (`?v2&debug`), loaded on demand:
 *
 *   __v2look.setPose(position, quaternion, fovDeg)  exact camera pose (e.g. a Blender camera)
 *   __v2look.readLinear(ss)    scene-linear frame (before exposure/grade), ss×ss supersampled,
 *                              as base64 float32 RGB rows top-first
 *   __v2look.setLUT(on)        Blender display transform vs three AgX + v1 grade
 *   __v2look.setSpecular(on)   environment specular on trim / laminate / window frame
 *   __v2look.bench(frames)     GPU-fenced frame cost, alternating A/B rounds for each switch
 */
interface Context {
  view: {
    renderer: THREE.WebGLRenderer;
    composer: { render: (dt?: number) => void };
    setDisplayLUT: (lut: DisplayLUT | null) => void;
  };
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  lut: DisplayLUT | null;
  baked: BakedRoom;
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

export function installV2LookDebug(ctx: Context) {
  const { view, scene, camera, lut, baked } = ctx;
  const renderer = view.renderer;
  const gl = renderer.getContext() as WebGL2RenderingContext;
  let lutOn = lut !== null;
  let specOn = baked.specularOn();
  const setLUT = (on: boolean) => {
    lutOn = on && lut !== null;
    view.setDisplayLUT(lutOn ? lut : null);
  };
  const setSpecular = (on: boolean) => {
    specOn = on;
    baked.setSpecular(on);
  };

  async function time(frames: number) {
    view.composer.render(0);
    await fence(gl);
    const t0 = performance.now();
    for (let i = 0; i < frames; i++) view.composer.render(0);
    await fence(gl);
    return (performance.now() - t0) / frames;
  }

  Object.assign(window, {
    __v2look: {
      setPose(p: number[], q: number[], fov: number) {
        camera.position.fromArray(p);
        camera.quaternion.fromArray(q);
        camera.fov = fov;
        camera.updateProjectionMatrix();
        camera.updateMatrixWorld(true);
      },
      readLinear(ss = 2) {
        const size = renderer.getDrawingBufferSize(new THREE.Vector2());
        const w = size.x;
        const h = size.y;
        const target = new THREE.WebGLRenderTarget(w * ss, h * ss, { type: THREE.FloatType, depthBuffer: true });
        const previous = renderer.getRenderTarget();
        renderer.setRenderTarget(target);
        renderer.clear();
        renderer.render(scene, camera);
        const raw = new Float32Array(w * ss * h * ss * 4);
        renderer.readRenderTargetPixels(target, 0, 0, w * ss, h * ss, raw);
        renderer.setRenderTarget(previous);
        target.dispose();
        const out = new Float32Array(w * h * 3);
        const k = 1 / (ss * ss);
        for (let y = 0; y < h; y++)
          for (let x = 0; x < w; x++) {
            const o = ((h - 1 - y) * w + x) * 3; // GL rows are bottom-up
            for (let dy = 0; dy < ss; dy++)
              for (let dx = 0; dx < ss; dx++) {
                const i = ((y * ss + dy) * w * ss + x * ss + dx) * 4;
                out[o] += raw[i] * k;
                out[o + 1] += raw[i + 1] * k;
                out[o + 2] += raw[i + 2] * k;
              }
          }
        const bytes = new Uint8Array(out.buffer);
        let s = '';
        for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        return { w, h, data: btoa(s) };
      },
      setLUT,
      setSpecular,
      state: () => ({ lut: lutOn, specular: specOn, specularMeshes: baked.specularMeshes, background: (scene.background as THREE.Color | null)?.getHexString?.() }),
      async bench(frames = 30, rounds = 6) {
        const result: Record<string, { with: number; without: number; cost: number }> = {};
        const switches: [string, (on: boolean) => void, boolean][] = [
          ['blender display LUT (vs three AgX + v1 grade)', setLUT, lutOn],
          ['environment specular', setSpecular, specOn],
        ];
        const size = renderer.getDrawingBufferSize(new THREE.Vector2());
        for (const [name, set, initial] of switches) {
          let a = 0;
          let b = 0;
          for (let r = 0; r < rounds; r++) {
            set(true);
            a += await time(frames);
            set(false);
            b += await time(frames);
          }
          set(initial);
          result[name] = { with: +(a / rounds).toFixed(3), without: +(b / rounds).toFixed(3), cost: +((a - b) / rounds).toFixed(3) };
        }
        await time(frames);
        return { drawingBuffer: [size.x, size.y], frames, rounds, frameMs: +(await time(frames)).toFixed(3), ...result };
      },
    },
  });
}
