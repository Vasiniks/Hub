import './styles.css';
import * as THREE from 'three';
import { createRenderer } from './scene/renderer';
import { CameraRig } from './camera/rig';
import { OVERLAY_LAYER } from './interaction/interaction';
import { createHint } from './ui/panel';
import { createLoader } from './ui/loading';
import { createMusicWidget } from './ui/music';
import { showCredits } from './ui/credits';
import { loadBakedRoom } from './scene/bakedRoom';
import { applyV2Look } from './scene/v2Look';
import { V2_TUNING } from './scene/v2Layout';
import { findNodes, loadV2Props } from './scene/v2Props';
import { createV2PropLight } from './scene/v2PropLight';
import { createRtLights, installRtShading, type RtLights } from './scene/rtLights';
import { createV2Animations } from './scene/v2Animate';
import { createPropRegistry } from './interaction/props';
import { v2Props } from './data/v2Props';
import { loadExteriorBackdrop } from './scene/exteriorBackdrop';
import { buildPickingTrees } from './interaction/bvh';

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const params = new URLSearchParams(location.search);
const canvas = document.getElementById('scene') as HTMLCanvasElement;
const hint = createHint();
// Six real stages: the download, the renderer, then the warm-up's own (see startV2).
const loader = createLoader(['room', 'renderer', 'environment', 'shaders', 'passes', 'measure'], 'loading the baked room');

/**
 * Resolve once the GPU has actually finished the work queued so far.
 *
 * `gl.finish()` does not block on this ANGLE/Metal path, and frame-to-frame rAF timing is
 * no better: while the loading screen is up nothing is being presented, so rAF free-runs at
 * the refresh rate while the driver quietly queues a backlog. Both report a frame that fits
 * in one interval when it really takes two. A fence is the one signal that tells the truth.
 */
function gpuFence(gl: WebGL2RenderingContext) {
  const sync = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
  if (!sync) return Promise.resolve();
  gl.flush();
  return new Promise<void>((resolve) => {
    const poll = () => {
      const status = gl.clientWaitSync(sync, 0, 0);
      if (status === gl.ALREADY_SIGNALED || status === gl.CONDITION_SATISFIED || status === gl.WAIT_FAILED) {
        gl.deleteSync(sync);
        resolve();
        return;
      }
      setTimeout(poll, 0);
    };
    poll();
  });
}

/**
 * `?v2`: the baked sunset room — shell, desk, furniture, curtains — lit entirely by their
 * lightmaps, walked with the default room's rig and examined through its interaction modules.
 * A flag, not a replacement: the default path above is untouched, and this path loads none of
 * it (no procedural room, no live lights). No live light exists in this scene, so the bake
 * cannot be double-lit; AO, shafts and bloom stay off for the same reason (all three would add
 * light or darkness the bake already holds).
 *
 * Interactive objects come from `src/data/v2Props.ts` through the prop registry
 * (`src/interaction/props.ts`): baked fixtures now, the props GLBs as they are exported.
 */
async function startV2() {
  /**
   * `?rt`: the hybrid real-time room — live sun and lamp with shadow maps on lit materials, only the
   * bounce light baked (rtLights.ts). An experiment beside the fully baked room, not a replacement yet.
   */
  const rt = params.has('rt');
  if (rt) installRtShading();
  const scene = new THREE.Scene();
  // Behind the exterior cards; only seen if they fail to load.
  scene.background = new THREE.Color('#c4b6a8');
  scene.fog = null;

  const camera = new THREE.PerspectiveCamera(V2_TUNING.fov, window.innerWidth / window.innerHeight, 0.02, 40);
  // Attention dots live on the overlay layer, as in the default room.
  camera.layers.enable(OVERLAY_LAYER);

  const base = `${import.meta.env.BASE_URL}assets/v2/room/`;
  // Props and the street outside load alongside the bake; with no props manifest yet the props resolve empty.
  const [baked, propFiles, exterior] = await Promise.all([
    loadBakedRoom(base, { lighting: rt ? 'rt' : 'baked' }),
    // `?rt` takes the PBR props with bounce-only lightmaps once they are exported, the lit ones until then.
    rt
      ? loadV2Props(`${import.meta.env.BASE_URL}assets/v2rt/props/`, { lightmaps: true }).then((p) =>
          p.props.length ? p : loadV2Props(`${import.meta.env.BASE_URL}assets/v2/props/`),
        )
      : loadV2Props(`${import.meta.env.BASE_URL}assets/v2/props/`),
    // The street outside the window: two baked panorama cards (exteriorBackdrop.ts).
    loadExteriorBackdrop(`${import.meta.env.BASE_URL}assets/v2/exterior/`),
  ]);
  scene.add(baked.group);
  scene.add(exterior.group);
  if (propFiles.props.length) scene.add(propFiles.group);
  // Baked: live sun + lamp for the PBR props only; the baked room ignores live light (v2PropLight.ts).
  // `?rt`: the live lights (rtLights.ts) light everything, so these are not made.
  const propLight = rt ? null : createV2PropLight(scene, baked.atlases.shell, propFiles.group);
  if (rt) {
    propFiles.group.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      // Glass (the PC's side panels, the robot's polycarbonate) lets the sun and the lamp through:
      // in Cycles it is transmissive, here it must simply not cast.
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      mesh.castShadow = !mats.some((m) => m.transparent);
      mesh.receiveShadow = true;
    });
  }
  // The robot's pulsing status light and the attractor on the monitor (v2Animate.ts).
  const animations = createV2Animations(propFiles.group, reducedMotion, new THREE.Vector3(...V2_TUNING.seat.position));
  loader.advance('starting the renderer');

  // Weak GPUs step down resolution, then MSAA, then below 1× (see stepDownQuality in renderer.ts).
  const view = createRenderer(canvas, scene, camera);
  // Sunset grade: Blender's own view (AgX, look Medium High Contrast) at the bake's +0.45 EV.
  await applyV2Look(view, scene, camera, baked);
  let rtLights: RtLights | null = null;
  if (rt) {
    const lights = (await fetch(`${base}manifest.json`).then((r) => r.json())).lights;
    rtLights = createRtLights(scene, view.renderer, lights);
  }

  // The same first-person rig as the default room — same file, same spring, same sit
  // transition — driven by the v2 room's own poses and limits (V2_TUNING). No chair: the
  // v2 room has none (see v2Layout.ts), so the rig moves the camera only.
  const rig = new CameraRig(camera, null, reducedMotion, V2_TUNING);

  createMusicWidget({
    title: 'Fortress of Lies',
    artist: 'Keiichi Okabe · NieR:Automata',
    // Official Spotify embed; swap the id, or hand createMusicWidget a TrackSource, to change it.
    spotifyId: '1WA80p54KvFTWDxOGC2jNI',
  });
  // The CC BY models' attribution, from the props export.
  void showCredits(`${import.meta.env.BASE_URL}assets/v2/props/CREDITS.json`);

  // Everything that happens because of an object (hover, outline, label, click to examine,
  // panel, Esc / click-outside, keyboard nav) is the default room's interaction modules behind
  // one `register()` call per object (src/interaction/props.ts).
  const props = createPropRegistry({
    scene,
    camera,
    rig,
    outline: view.outline,
    canvas,
    seat: V2_TUNING.seat.position,
    reducedMotion,
    hint,
  });
  const skippedProps: string[] = [];
  for (const def of v2Props) {
    const src = def.source;
    const nodes =
      'file' in src
        ? [propFiles.file(src.file)].filter((n): n is THREE.Object3D => !!n)
        : [
            ...findNodes(baked.group, (n) => (src.baked ?? []).some((p) => n.startsWith(p))),
            ...findNodes(propFiles.group, (n) => (src.props ?? []).some((p) => n.startsWith(p))),
          ];
    // Not loaded (yet): props are listed before their GLBs are exported.
    if (!nodes.length) {
      skippedProps.push(def.id);
      continue;
    }
    props.register({ ...def, node: nodes });
  }

  function sitV2() {
    if (rig.sitDown()) hint.hide();
  }

  let lookHintShown = false;
  rig.onSeated = () => {
    // A click on an object while standing sat the visitor down; now open it.
    if (props.resumePending()) return;
    if (!lookHintShown) {
      lookHintShown = true;
      hint.show('Look around', 4200);
    }
  };

  window.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      if (rig.mode === 'standing' && e.deltaY > 2) sitV2();
    },
    { passive: false },
  );

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') return; // Esc belongs to the prop registry (back out of an object).
    const active = document.activeElement;
    const onBody = active === document.body || active === null;
    if (onBody && rig.mode === 'standing' && ['ArrowDown', ' ', 'Enter', 'PageDown'].includes(e.key)) {
      e.preventDefault();
      sitV2();
    }
  });

  window.addEventListener('pointermove', (e) => {
    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = -(e.clientY / window.innerHeight) * 2 + 1;
    rig.setPointer(nx, ny);
  });

  loader.advance('shaders');
  // Interactive objects are passed so the hover outline's shader variants compile now, not on
  // the first hover.
  await view.warmUp(props.groups(), (stage) => loader.advance(stage));
  // warmUp captured the room with the props in it, unlit by their own reflections; record it
  // again without them so the props' image-based light is the baked room alone.
  if (propLight) propLight.captureWithoutProps(view.captureEnvironmentNow);
  else {
    // `?rt`: the room as live-lit, without the props, which must not reflect themselves.
    propFiles.group.visible = false;
    view.captureEnvironmentNow();
    propFiles.group.visible = true;
  }

  window.addEventListener('resize', view.resize);

  let last = performance.now();
  let elapsed = 0;
  let frameCount = 0;
  let firstFrame = true;
  let benchPaused = false;
  let reportedError = false;
  /** Suppressed while calibrating, so the reveal does not fire behind the loading bar. */
  let calibrating = true;
  /** Debug only: park the camera anywhere to inspect a model close up. */
  let parked: { p: number[]; t: number[]; fov: number } | null = null;
  function frame(now: number) {
    // Schedule first: a runtime error in one frame must never freeze the room.
    requestAnimationFrame(frame);
    if (benchPaused) {
      last = now;
      return;
    }
    try {
      step(now);
    } catch (err) {
      if (!reportedError) {
        reportedError = true;
        console.error(err);
      }
    }
  }

  function step(now: number) {
    view.renderer.info.reset();
    const dt = Math.min(0.05, (now - last) / 1000);
    frameCount++;
    last = now;
    elapsed += dt;
    props.holdLook();
    if (parked) {
      camera.position.set(parked.p[0], parked.p[1], parked.p[2]);
      camera.lookAt(parked.t[0], parked.t[1], parked.t[2]);
      camera.fov = parked.fov;
      camera.updateProjectionMatrix();
    } else {
      rig.update(dt);
    }
    props.update(dt, elapsed);
    animations.update(dt, elapsed, camera, props.focusedId ? 1 : 0);
    rtLights?.update();
    view.render(dt);

    if (firstFrame && !calibrating) {
      firstFrame = false;
      requestAnimationFrame(() => document.getElementById('veil')!.classList.add('is-lifted'));
      window.setTimeout(() => {
        if (rig.mode === 'standing') hint.show('Scroll to sit down');
      }, 2200);
    }
  }

  if (params.has('debug')) {
    Object.assign(window, {
      __room: {
        mode: () => rig.mode,
        calibration: () => calibration,
        animations: () => animations.info(),
        pixelRatio: () => view.pixelRatio(),
        frames: () => frameCount,
        camera: () => ({ position: camera.position.toArray(), quaternion: camera.quaternion.toArray() }),
        programs: () => (view.renderer.info.programs ?? []).map((p) => p.name),
        hovered: () => props.hoveredId,
        focused: () => props.focusedId,
        panelOpen: () => props.panelOpen,
        props: () => ({ registered: props.ids(), skipped: skippedProps, files: propFiles.props.map((p) => p.entry.file) }),
        openProp: (id: string) => props.open(id),
        /** Try a registration from the console: any baked or prop node prefix, default framing. */
        registerNodes: (id: string, label: string, prefixes: string[]) =>
          !!props.register({
            id,
            label,
            node: [baked.group, propFiles.group].flatMap((root) => findNodes(root, (n) => prefixes.some((p) => n.startsWith(p)))),
            panel: { kind: 'Debug', title: label, summary: 'Registered from the console.', sections: [] },
          }),
        closeProp: () => props.close(),
        forceHover: (id: string | null) => props.interaction.setForcedHover(id),
        screenPositionOf: (id: string) => props.interaction.screenPositionOf(id),
        hitPositionOf: (id: string) => props.interaction.hitPositionOf(id),
        debugPick: (x: number, y: number) => props.interaction.debugPick(x, y),
        debugState: () => ({ ...props.interaction.debugState(), lookExtent: rig.lookExtent() }),
        pickingTrees: () => pickingTrees,
        lookExtent: () => rig.lookExtent(),
        sitDown: () => rig.sitDown(),
        setPointer: (nx: number, ny: number) => rig.setPointer(nx, ny),
        parkCamera: (p: number[] | null, t?: number[], fov = 54) => {
          if (!p) {
            parked = null;
            camera.fov = V2_TUNING.fov;
            return;
          }
          parked = { p, t: t ?? [0, 0.8, -0.6], fov };
        },
        v2: {
          atlases: () => Object.keys(baked.atlases),
          tris: () => baked.tris,
          setAtlasVisible: (name: string, visible: boolean) => {
            baked.atlases[name].visible = visible;
          },
        },
        bench: async (pose: { p: number[]; t: number[]; fov: number }) => {
          const { createBench } = await import('./debug/bench');
          return createBench({ renderer: view.renderer, composer: view.composer, scene, camera, pause: (on) => (benchPaused = on) }).run(pose);
        },
      },
    });
  }

  /**
   * Choose the render quality before the first visible frame, the way the default room does
   * (see `calibrate` in `start()`): run real frames in a burst, fence once, and step down the
   * ladder — resolution, then MSAA, then below 1× — until the frame fits the budget. A low-end
   * GPU starts on a rung it can hold instead of discovering it from stutter.
   */
  const FRAME_BUDGET_MS = 15.5;
  async function calibrate() {
    const gl = view.renderer.getContext() as WebGL2RenderingContext;
    const burst = async (n: number) => {
      const t0 = performance.now();
      for (let i = 0; i < n; i++) step(performance.now());
      await gpuFence(gl);
      return (performance.now() - t0) / n;
    };
    await burst(4); // discard: driver first-use
    const measure = async () => {
      const first = await burst(6);
      if (Math.abs(first - FRAME_BUDGET_MS) > FRAME_BUDGET_MS * 0.25) return first;
      return (first + (await burst(6))) / 2;
    };
    let cost = await measure();
    const trace = [{ ratio: view.pixelRatio(), msaa: view.msaa(), ms: +cost.toFixed(2) }];
    let steps = 0;
    while (view.adaptive && cost > FRAME_BUDGET_MS && steps < 5 && view.stepDownQuality()) {
      steps++;
      await burst(3);
      cost = await measure();
      trace.push({ ratio: view.pixelRatio(), msaa: view.msaa(), ms: +cost.toFixed(2) });
    }
    return { frameMs: +cost.toFixed(2), chosen: view.pixelRatio(), msaa: view.msaa(), steps, trace };
  }
  const calibration = await calibrate();
  calibrating = false;
  // The calibration frames advanced the clocks; put them back so the visitor starts at zero.
  elapsed = 0;
  frameCount = 0;
  loader.advance('ready');
  await loader.hide();
  // Picking acceleration builds in idle time once the room is on screen (see interaction/bvh.ts).
  const pickingTrees = buildPickingTrees(scene);

  last = performance.now();
  requestAnimationFrame(frame);
}

startV2().catch((err) => {
  console.error(err);
  loader.fail('This room needs WebGL. Try a current desktop browser.');
  document.getElementById('veil')!.classList.add('is-lifted');
});
