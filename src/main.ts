import './styles.css';
import * as THREE from 'three';
import { projects } from './data/projects';
import { createMaterials } from './scene/materials';
import { buildRoom } from './scene/room';
import { createLorenzScreen } from './scene/lorenz';
import { createDust } from './scene/dust';
import { createLighting, LAMP_ANGLE, type LightState } from './scene/lighting';
import { createExterior } from './scene/exterior';
import { createRenderer } from './scene/renderer';
import { buildObject } from './scene/objects';
import { CameraRig } from './camera/rig';
import { createInteraction, OVERLAY_LAYER, type InteractTarget } from './interaction/interaction';
import { createPanel, createHint, createObjectNav, createShelfCaption } from './ui/panel';
import { createLoader } from './ui/loading';
import { createMusicWidget } from './ui/music';
import { CAMERA, INTERACTION, SHELF } from './scene/layout';
import { FramePerf } from './debug/perf';

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const params = new URLSearchParams(location.search);
const hourParam = params.get('hour');
const hourOverride = hourParam !== null && !Number.isNaN(Number(hourParam)) ? Number(hourParam) : null;

/**
 * §10/§11: the room opens at night, then settles to the real clock.
 *
 * Night is the arrival state — lamp, monitor and LEDs carrying the frame — and from there the
 * light eases to whatever time it actually is, along the shorter way round the clock. Arriving
 * in the afternoon reads as a slow dawn rather than a preset swap; arriving at night, nothing
 * moves at all. After the settle the room follows the real clock exactly as before.
 */
const NIGHT_HOUR = 21.6;
const ARRIVE_HOLD = 2.4;
const ARRIVE_EASE = 6.5;
const arrivalEnabled = params.get('arrive') !== '0' && hourOverride === null;

const canvas = document.getElementById('scene') as HTMLCanvasElement;
const hint = createHint();
const loader = createLoader(['scene', 'light', 'shaders', 'passes', 'calibrate']);

async function start() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#0f1216');
  scene.fog = new THREE.FogExp2('#0f1216', 0.08);

  const camera = new THREE.PerspectiveCamera(CAMERA.fov, window.innerWidth / window.innerHeight, 0.02, 40);
  camera.layers.enable(OVERLAY_LAYER);

  const materials = createMaterials();
  const room = buildRoom(materials, reducedMotion);
  scene.add(room.root);

  // The monitor runs the attractor; the screen material samples the canvas as its emissive map.
  const lorenz = createLorenzScreen();
  const screenMat = room.screen.material as THREE.MeshStandardMaterial;
  screenMat.emissiveMap = lorenz.texture;
  screenMat.needsUpdate = true;

  const dust = createDust(scene);
  dust.place(room.lampHead, room.lampPool);

  const exterior = createExterior(scene, room.windowCenter);
  const lighting = createLighting(scene, room, exterior);
  const view = createRenderer(canvas, scene, camera, lighting.sun, lighting.lamp);
  const rig = new CameraRig(camera, room, reducedMotion);

  // ---- Interaction targets: project objects, plus the bookshelf ----------
  const projectObjects = projects.map((project) => {
    const built = buildObject(project.object.builder, materials);
    const g = built.group;
    g.position.set(...project.object.position);
    g.rotation.y = project.object.rotationY;
    g.scale.setScalar(project.object.scale ?? 1);
    scene.add(g);
    g.updateMatrixWorld(true);
    const anchor = g.localToWorld(new THREE.Vector3(...project.anchor));
    const box = new THREE.Box3().setFromObject(g);
    const dotPos = new THREE.Vector3((box.min.x + box.max.x) / 2, box.max.y + 0.035, (box.min.z + box.max.z) / 2);
    const target: InteractTarget = {
      id: project.id,
      title: project.title,
      group: g,
      anchor,
      dotPos,
      tick: built.tick,
      focus: () => ({ center: anchor.clone(), ...project.focus }),
    };
    return target;
  });

  const shelfTarget: InteractTarget = {
    id: 'bookshelf',
    title: 'Bookshelf',
    group: room.shelf.group,
    anchor: room.shelf.anchor,
    dotPos: room.shelf.dotPos,
    focus: () => room.shelf.focusTarget(),
    outline: () => room.shelf.outlineTargets(),
  };

  const targets = [...projectObjects, shelfTarget];
  const interaction = createInteraction({
    scene,
    camera,
    outline: view.outline,
    targets,
    reducedMotion,
    label: document.getElementById('hover-label')!,
    lookExtent: () => rig.lookExtent(),
  });

  loader.advance('capturing light');

  // ---- Shadow-casting motion --------------------------------------------
  const casters: { node: THREE.Object3D; quat: THREE.Quaternion; pos: THREE.Vector3; reach: number }[] = [];
  scene.updateMatrixWorld(true);
  scene.traverse((o) => {
    if (!o.userData.dynamic || o === room.chair) return;
    let casts = false;
    o.traverse((c) => {
      if ((c as THREE.Mesh).isMesh && c.castShadow) casts = true;
    });
    if (!casts) return;
    const reach = new THREE.Box3().setFromObject(o).getBoundingSphere(new THREE.Sphere()).radius + 0.2;
    casters.push({ node: o, quat: o.getWorldQuaternion(new THREE.Quaternion()), pos: o.getWorldPosition(new THREE.Vector3()), reach });
  });
  const _casterQuat = new THREE.Quaternion();
  const _casterPos = new THREE.Vector3();
  const _viewProjection = new THREE.Matrix4();
  const _frustum = new THREE.Frustum();
  const _reachSphere = new THREE.Sphere();
  const screenSphere = new THREE.Sphere(room.screenCenter.clone(), 0.42);

  /** Refreshed once per frame and reused by shadow gating and by screen visibility. */
  function updateFrustum() {
    _viewProjection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    _frustum.setFromProjectionMatrix(_viewProjection);
  }

  // The lamp is fixed, so its beam is measured once. A caster outside this cone cannot cast
  // into the lamp's shadow map, however much it moves.
  const lampOrigin = room.lampSocket.getWorldPosition(new THREE.Vector3());
  const lampAxis = room.lampTarget.getWorldPosition(new THREE.Vector3()).sub(lampOrigin).normalize();
  const LAMP_REACH = 3.0;
  const _toCaster = new THREE.Vector3();

  function inLampBeam(pos: THREE.Vector3, radius: number) {
    _toCaster.copy(pos).sub(lampOrigin);
    const dist = _toCaster.length();
    if (dist > LAMP_REACH + radius) return false;
    if (dist < radius) return true;
    // Widen the cone by the angle the object's own radius subtends at this distance.
    const slack = Math.atan2(radius, dist);
    return Math.acos(THREE.MathUtils.clamp(_toCaster.dot(lampAxis) / dist, -1, 1)) < LAMP_ANGLE + slack;
  }

  /**
   * Largest change since the last shadow redraw, reported per light.
   *
   * A redraw is only worth paying for if the thing that moved can actually appear in that
   * light's map: within the camera's view for the sun, inside the beam for the lamp. Without
   * the second test a slowly turning ornament across the room forced a full spot-shadow
   * redraw roughly twice a second, which was the entire p95 frame-time tail.
   */
  const motion = { sun: 0, lamp: 0 };
  function casterMotion() {
    motion.sun = 0;
    motion.lamp = 0;
    for (const c of casters) {
      c.node.getWorldPosition(_casterPos);
      const onScreen = _frustum.intersectsSphere(_reachSphere.set(_casterPos, c.reach));
      const inBeam = inLampBeam(_casterPos, c.reach);
      if (!onScreen && !inBeam) continue;
      c.node.getWorldQuaternion(_casterQuat);
      const angle = 2 * Math.acos(Math.min(1, Math.abs(_casterQuat.dot(c.quat))));
      const moved = Math.max(angle / 0.09, _casterPos.distanceTo(c.pos) / 0.004);
      if (onScreen) motion.sun = Math.max(motion.sun, moved);
      if (inBeam && onScreen) motion.lamp = Math.max(motion.lamp, moved);
    }
    if (motion.sun > 1 || motion.lamp > 1) {
      for (const c of casters) {
        c.node.getWorldQuaternion(c.quat);
        c.node.getWorldPosition(c.pos);
      }
    }
    return motion;
  }

  // ---- Time of day -------------------------------------------------------
  let liveHour = hourOverride;
  let arrival = 0;
  const realHour = () => {
    const d = new Date();
    return d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600;
  };
  function hourNow() {
    if (liveHour !== null) return liveHour;
    const real = realHour();
    if (!arrivalEnabled) return real;
    const t = THREE.MathUtils.clamp((arrival - ARRIVE_HOLD) / ARRIVE_EASE, 0, 1);
    if (t >= 1) return real;
    const e = t * t * (3 - 2 * t);
    // Travel the shorter way round the clock, so 21:36 → 09:00 goes forward through the night.
    let delta = real - NIGHT_HOUR;
    while (delta > 12) delta -= 24;
    while (delta < -12) delta += 24;
    return NIGHT_HOUR + delta * e;
  }
  const arriving = () => arrivalEnabled && liveHour === null && arrival < ARRIVE_HOLD + ARRIVE_EASE;

  /**
   * §28: reflections and indirect light follow the light, not a timer.
   *
   * A capture is requested when the lit state has actually drifted — exposure, ambient level,
   * sky tone, lamp and monitor output — with a floor on how often that can happen. A still
   * room at a fixed hour never re-captures; the dawn sweep re-captures a handful of times.
   */
  function lightSignature(s: LightState) {
    return s.exposure * 3 + s.env * 4 + s.bloom * 2 + s.monitor * 0.3 + s.lamp * 0.25 + (s.sky.r + s.sky.g + s.sky.b) * 2.5;
  }
  let capturedSignature = Number.NEGATIVE_INFINITY;
  let sinceCapture = 99;
  function refreshLight(force = false) {
    const state = lighting.apply(hourNow());
    view.applyLight(state);
    const signature = lightSignature(state);
    if (force || (Math.abs(signature - capturedSignature) > 0.1 && sinceCapture > 1.5)) {
      view.requestEnvironmentCapture();
      capturedSignature = signature;
      sinceCapture = 0;
    }
  }

  // ---- Project view ------------------------------------------------------
  let focusActivity = 0;
  let pendingOpen: string | null = null;
  let panelShown = false;
  let activityPulse = 0;
  let shelfMode = false;

  const panel = createPanel(() => closeCurrent());
  const caption = createShelfCaption();
  const live = document.getElementById('live')!;
  // Where keyboard focus lives while browsing, so the shelf is operable without a mouse and
  // announces itself rather than leaving focus stranded on the nav button that opened it.
  const shelfFocus = document.getElementById('shelf-mode') as HTMLElement;
  let shelfReturnFocus: HTMLElement | null = null;
  const music = createMusicWidget({ title: 'Fortress of Lies', artist: 'Keiichi Okabe · NieR:Automata' });

  function openProject(id: string) {
    if (id === 'bookshelf') return openShelf();
    const project = projects.find((p) => p.id === id);
    if (!project) return;
    if (rig.mode === 'standing') {
      pendingOpen = id;
      sit();
      return;
    }
    if (rig.mode === 'sitting') {
      pendingOpen = id;
      return;
    }
    panel.fill(project);
    panelShown = false;
    if (panel.isOpen) panel.close();
    interaction.setFocused(id);
    activityPulse = 1;
    hint.hide();
    rig.focus(interaction.focusTarget(id));
  }

  // ---- Bookshelf browsing (§15) -----------------------------------------
  function openShelf() {
    if (rig.mode === 'standing') {
      pendingOpen = 'bookshelf';
      sit();
      return;
    }
    if (rig.mode === 'sitting') {
      pendingOpen = 'bookshelf';
      return;
    }
    if (shelfMode) return;
    shelfMode = true;
    shelfReturnFocus = document.activeElement instanceof HTMLElement && document.activeElement.closest('#object-nav')
      ? document.activeElement
      : null;
    shelfFocus.focus({ preventScroll: true });
    room.shelf.enter();
    interaction.setFocused('bookshelf');
    interaction.holdOutline('bookshelf');
    hint.hide();
    rig.focus(room.shelf.focusTarget());
    announceBook();
  }

  function announceBook() {
    const book = room.shelf.selected();
    caption.show(book.title, book.author);
    interaction.holdOutline('bookshelf');
    live.textContent = `${book.title}, ${book.author}. Book ${room.shelf.index + 1} of 12.`;
  }

  function stepBook(dir: number) {
    if (!shelfMode) return;
    if (panel.isOpen) panel.close();
    panelShown = false;
    room.shelf.step(dir);
    lastStepAt = performance.now();
    announceBook();
  }

  /**
   * §19/§20: browsing is gesture-based, not event-based.
   *
   * A wheel or trackpad swipe emits a burst of events; treating each one as a navigation
   * meant a flick threw the selection five books across the shelf. Instead, deltas accumulate
   * until they cross a threshold, that commits exactly one step, and the gesture then disarms
   * until the input has been quiet long enough to count as a new intent. The result: a slow
   * nudge moves one book, and so does a violent swipe.
   */
  let wheelAccum = 0;
  let lastWheelAt = 0;
  let lastStepAt = 0;
  let gestureArmed = true;

  function shelfWheel(e: WheelEvent) {
    // Normalise across deltaMode so a line-mode mouse and a pixel-mode trackpad agree.
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 100 : 1;
    const raw = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    const delta = raw * unit;
    const now = performance.now();
    if (now - lastWheelAt > SHELF.gesture.restMs) {
      wheelAccum = 0;
      gestureArmed = true;
    }
    lastWheelAt = now;
    if (!gestureArmed) return;
    // Direction is consistent: a push away from you, or to the right, advances the row.
    wheelAccum += delta;
    if (Math.abs(wheelAccum) < SHELF.gesture.threshold) return;
    if (now - lastStepAt < SHELF.gesture.minStepMs || !room.shelf.settled) return;
    stepBook(Math.sign(wheelAccum));
    wheelAccum = 0;
    gestureArmed = false;
  }

  /** Keyboard uses the same pacing, so held arrows advance one book at a time. */
  function shelfKey(dir: number) {
    if (performance.now() - lastStepAt < SHELF.gesture.minStepMs || !room.shelf.settled) return;
    stepBook(dir);
  }

  function inspectBook() {
    if (!shelfMode) return;
    const book = room.shelf.selected();
    panel.fillBook(book);
    panel.open();
    panelShown = true;
  }

  function closeCurrent() {
    if (shelfMode) {
      // Esc backs out one layer at a time: book information first, then the shelf itself.
      if (panel.isOpen) {
        panel.close();
        panelShown = false;
        return;
      }
      shelfMode = false;
      room.shelf.exit();
      caption.hide();
      interaction.setFocused(null);
      shelfReturnFocus?.focus({ preventScroll: true });
      shelfReturnFocus = null;
      if (document.activeElement === shelfFocus) shelfFocus.blur();
      rig.unfocus();
      return;
    }
    if (rig.mode !== 'focused' && rig.mode !== 'focusing') return;
    panel.close();
    panelShown = false;
    interaction.setFocused(null);
    rig.unfocus();
  }

  rig.onFocusProgress = (t) => {
    // The shelf opens no panel on arrival: the books are the interface until one is chosen.
    if (!shelfMode && !panelShown && t > 0.55) {
      panelShown = true;
      panel.open();
    }
  };

  let lookHintShown = false;
  rig.onSeated = () => {
    if (pendingOpen) {
      const id = pendingOpen;
      pendingOpen = null;
      openProject(id);
      return;
    }
    if (!lookHintShown) {
      lookHintShown = true;
      hint.show('Look around', 4200);
    }
  };

  function sit() {
    if (rig.sitDown()) hint.hide();
  }

  createObjectNav(
    targets.map((t) => ({ id: t.id, label: t.id === 'bookshelf' ? 'Bookshelf' : labelFor(t.id) })),
    {
      onFocus: (id) => interaction.setForcedHover(id),
      onBlur: () => interaction.setForcedHover(null),
      onActivate: (id) => openProject(id),
    },
  );

  function labelFor(id: string) {
    const p = projects.find((x) => x.id === id)!;
    return p.placeholder ? `${p.title} (${p.kindLabel.toLowerCase()})` : p.title;
  }

  // ---- Input -------------------------------------------------------------
  window.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      if (rig.mode === 'standing' && e.deltaY > 2) sit();
      // While browsing, the wheel walks the row — the same gesture that got you into the chair.
      else if (shelfMode) shelfWheel(e);
    },
    { passive: false },
  );

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeCurrent();
      return;
    }
    const active = document.activeElement;
    const onBody = active === document.body || active === null;
    if (shelfMode) {
      // Enter/Space belong to the shelf unless focus has moved into the open book panel.
      const shelfKeys = onBody || active === shelfFocus;
      if (['ArrowLeft', 'a', 'A'].includes(e.key)) {
        e.preventDefault();
        shelfKey(-1);
      } else if (['ArrowRight', 'd', 'D'].includes(e.key)) {
        e.preventDefault();
        shelfKey(1);
      } else if (shelfKeys && [' ', 'Enter'].includes(e.key)) {
        e.preventDefault();
        inspectBook();
      }
      return;
    }
    if (onBody && rig.mode === 'standing' && ['ArrowDown', ' ', 'Enter', 'PageDown'].includes(e.key)) {
      e.preventDefault();
      sit();
    }
  });

  const pointer = new THREE.Vector2(-10, -10);
  window.addEventListener('pointermove', (e) => {
    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = -(e.clientY / window.innerHeight) * 2 + 1;
    pointer.set(nx, ny);
    rig.setPointer(nx, ny);
    interaction.setPointer(nx, ny, e.target === canvas);
  });
  document.addEventListener('pointerleave', () => interaction.setPointer(-10, -10, false));

  let downAt: { x: number; y: number } | null = null;
  let dragConsumed = false;
  canvas.addEventListener('pointerdown', (e) => {
    downAt = { x: e.clientX, y: e.clientY };
    dragConsumed = false;
  });
  // Dragging sideways across the shelf steps the row — once per drag, like every other gesture.
  canvas.addEventListener('pointermove', (e) => {
    if (!shelfMode || !downAt || dragConsumed) return;
    const dx = e.clientX - downAt.x;
    if (Math.abs(dx) < SHELF.gesture.dragPx) return;
    if (!room.shelf.settled) return;
    stepBook(Math.sign(dx));
    dragConsumed = true;
  });
  canvas.addEventListener('pointerup', (e) => {
    if (!downAt || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > INTERACTION.clickSlopPx) return;
    downAt = null;

    if (shelfMode) {
      const hitBook = room.shelf.pick(pointer, camera);
      if (hitBook === null) {
        closeCurrent();
      } else if (hitBook === room.shelf.index) {
        inspectBook();
      } else {
        room.shelf.select(hitBook);
        if (panel.isOpen) panel.close();
        panelShown = false;
        announceBook();
      }
      return;
    }
    if (rig.mode === 'focused' || rig.mode === 'focusing') {
      closeCurrent();
      return;
    }
    const id = interaction.hoveredId;
    if (rig.mode === 'standing') {
      if (id) pendingOpen = id;
      sit();
    } else if (rig.mode === 'seated' && id) {
      openProject(id);
    }
  });

  window.addEventListener('resize', view.resize);

  // ---- Loop --------------------------------------------------------------
  view.applyLight(lighting.apply(hourNow()));
  let last = performance.now();
  let lightTimer = 0;
  let elapsed = 0;
  let firstFrame = true;
  let frameCount = 0;
  const perf = new FramePerf(params.has('debug'));

  /** Debug only: park the camera anywhere to inspect a model close up. */
  let parked: { p: number[]; t: number[]; fov: number } | null = null;

  /** Suppressed while calibrating, so the reveal does not fire behind the loading bar. */
  let calibrating = true;

  let reportedError = false;
  function frame(now: number) {
    // Schedule first: a runtime error in one frame must never freeze the room.
    requestAnimationFrame(frame);
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
    perf.beginFrame(now);
    view.renderer.info.reset();
    const dt = Math.min(0.05, (now - last) / 1000);
    frameCount++;
    last = now;
    elapsed += dt;
    arrival += dt;
    sinceCapture += dt;

    rig.holdLook(interaction.hoveredId !== null && !interaction.hoverIsCentred && rig.interactive);
    if (parked) {
      camera.position.set(parked.p[0], parked.p[1], parked.p[2]);
      camera.lookAt(parked.t[0], parked.t[1], parked.t[2]);
      camera.fov = parked.fov;
      camera.updateProjectionMatrix();
    } else {
      rig.update(dt);
    }
    updateFrustum();
    perf.lap('camera');

    interaction.setEnabled(rig.interactive && !shelfMode);
    interaction.update(dt, elapsed);
    room.shelf.update(dt);
    if (shelfMode) interaction.holdOutline('bookshelf');
    perf.lap('interaction');

    // §26/§27: the attractor only integrates and repaints while the monitor is on camera.
    focusActivity = THREE.MathUtils.lerp(focusActivity, panelShown ? 1 : 0, 1 - Math.exp(-2 * dt));
    lorenz.update(dt, elapsed, _frustum.intersectsSphere(screenSphere), focusActivity);
    dust.update(elapsed, lighting.state.lamp, Math.cos(LAMP_ANGLE));
    activityPulse = Math.max(0, activityPulse - dt * 0.28);
    lighting.setActivity(activityPulse);
    music.update();
    perf.lap('screens+reactions');

    view.render(dt, elapsed, !reducedMotion);
    perf.lap('render');

    // Light advances on a one-second tick, six times faster while the room is settling from
    // night to the real hour. Shadow maps redraw only when something that casts them has
    // visibly moved: every frame while the chair rolls in, otherwise once an animated part
    // has turned or shifted enough to show.
    lightTimer += dt;
    if (lightTimer > (arriving() ? 1 / 6 : 1)) {
      lightTimer = 0;
      refreshLight();
    }
    const moved = casterMotion();
    if (rig.mode === 'sitting') lighting.markShadowsDirty('both');
    else {
      if (moved.sun > 1) lighting.markShadowsDirty('sun');
      if (moved.lamp > 1) lighting.markShadowsDirty('lamp');
    }
    perf.lap('lighting+shadows');
    perf.endFrame(view.renderer.info.render.calls, view.renderer.info.render.triangles, view.renderer.info.programs?.length ?? 0);

    if (firstFrame && !calibrating) {
      firstFrame = false;
      requestAnimationFrame(() => document.getElementById('veil')!.classList.add('is-lifted'));
      window.setTimeout(() => {
        if (rig.mode === 'standing') hint.show('Scroll to sit down');
      }, 2200);
      window.setTimeout(() => music.reveal(), 1400);
    }
  }

  // ---- Startup (§23/§24) -------------------------------------------------
  // Everything expensive happens here, behind the loading bar, and each stage reports when it
  // is genuinely finished. Nothing is deferred into the first seconds of interaction.
  const outlineSamples = targets.map((t) => t.group);
  const restoreShadows = lighting.warmShadows();
  await view.warmUp(outlineSamples, (stage) => loader.advance(stage));
  restoreShadows();
  /**
   * §23/§43: choose the render resolution before the first visible frame, by running the
   * actual frame.
   *
   * Earlier versions measured `composer.render()` on its own and consistently came in a whole
   * vsync interval under what the loop really cost — the render is only part of a frame. This
   * drives `step()` itself, so what is measured is exactly what will run. Under vsync a frame
   * that overruns does not come back slow, it comes back doubled, so the mean is the signal:
   * it is just the true frame rate.
   */
  /**
   * Budget for one frame, in the units the burst below reports. Frames in a burst pipeline on
   * the GPU, so that number is lower than the latency of a single isolated frame — 15.5 is
   * calibrated against this measurement, not against 1000/60. Re-tune it if the method changes.
   */
  const FRAME_BUDGET_MS = 15.5;

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
   * §23/§43: choose the render resolution before the first visible frame, by running the
   * actual frame — `step()` itself, not the composer on its own, which costs a whole vsync
   * interval less than a real frame.
   *
   * Frames are rendered as a burst and fenced once at the end, so the poll granularity is
   * divided across the whole burst instead of being paid per frame.
   */
  async function calibrate() {
    const from = view.pixelRatio();
    const gl = view.renderer.getContext() as WebGL2RenderingContext;
    const burst = async (n: number) => {
      const t0 = performance.now();
      for (let i = 0; i < n; i++) step(performance.now());
      await gpuFence(gl);
      return (performance.now() - t0) / n;
    };
    await burst(4); // discard: driver first-use
    let cost = await burst(12);
    let steps = 0;
    while (cost > FRAME_BUDGET_MS && steps < 2 && view.stepDownResolution()) {
      steps++;
      await burst(3);
      cost = await burst(12);
    }
    return { frameMs: +cost.toFixed(2), from, chosen: view.pixelRatio(), steps };
  }
  const calibration = await calibrate();
  calibrating = false;
  // The calibration frames advanced the clocks; put them back so the visitor starts at zero.
  elapsed = 0;
  arrival = 0;
  lightTimer = 0;
  frameCount = 0;
  perf.reset();
  loader.advance('ready');
  capturedSignature = lightSignature(lighting.state);
  sinceCapture = 0;
  await loader.hide();

  last = performance.now();
  requestAnimationFrame(frame);

  if (params.has('debug')) {
    Object.assign(window, {
      __room: {
        mode: () => rig.mode,
        hovered: () => interaction.hoveredId,
        panelOpen: () => panel.isOpen,
        shelf: () => ({ active: shelfMode, index: room.shelf.index, title: room.shelf.selected().title }),
        stepBook,
        inspectBook,
        openShelf,
        screenPositionOf: (id: string) => interaction.screenPositionOf(id),
        hitPositionOf: (id: string) => interaction.hitPositionOf(id),
        debugPick: (x: number, y: number) => interaction.debugPick(x, y),
        debugState: () => ({ ...interaction.debugState(), lookExtent: rig.lookExtent() }),
        debugDots: () => interaction.debugDots(),
        frames: () => frameCount,
        hour: () => lighting.state.hour,
        calibration: () => calibration,
        pixelRatio: () => view.pixelRatio(),
        programs: () => (view.renderer.info.programs ?? []).map((p) => p.name),
        programKeys: () => (view.renderer.info.programs ?? []).map((p) => `${p.name}::${p.cacheKey}`),
        shadowRequests: () => ({ ...lighting.shadowRequests }),
        outlineOnly: (id: string | null) => {
          const group = id ? targets.find((t) => t.id === id)?.group : undefined;
          view.outline.selectedObjects = group ? [group] : [];
          view.outline.enabled = !!group;
        },
        perf: { reset: () => perf.reset(), snapshot: () => perf.snapshot(view.renderer.getPixelRatio()) },
        setHour: (h: number) => {
          liveHour = h;
          refreshLight(true);
        },
        camera: () => ({ position: camera.position.toArray(), quaternion: camera.quaternion.toArray() }),
        chair: () => ({ position: room.chair.position.toArray(), rotationY: room.chair.rotation.y }),
        projects: projects.map((p) => p.id),
        meshes: () => room.root.userData.meshes,
        lamp: () => ({
          headWorld: room.lampHead.getWorldPosition(new THREE.Vector3()).toArray(),
          headParent: room.lampHead.parent?.name || room.lampHead.parent?.type,
          headLocal: room.lampHead.position.toArray(),
          parentWorld: room.lampHead.parent?.getWorldPosition(new THREE.Vector3()).toArray(),
          socketWorld: room.lampSocket.getWorldPosition(new THREE.Vector3()).toArray(),
          targetWorld: room.lampTarget.getWorldPosition(new THREE.Vector3()).toArray(),
          pool: room.lampPool.toArray(),
          discWorld: room.lampDisc.getWorldPosition(new THREE.Vector3()).toArray(),
        }),
        /** Diagnostics: list top-level scene children, and hide one by index. */
        parkCamera: (p: number[] | null, t?: number[], fov = 24) => {
          parked = p ? { p, t: t ?? [0, 0.8, -0.6], fov } : null;
          if (!parked) camera.fov = CAMERA.fov;
        },
        volumetric: () => ({
          sunScatter: view.volumetric.scatter.toArray(),
          lampScatter: view.volumetric.lampScatter.toArray(),
          sunMap: !!lighting.sun.shadow.map,
          sunDepthTex: !!lighting.sun.shadow.map?.depthTexture,
          lampMap: !!lighting.lamp.shadow.map,
          lampDepthTex: !!lighting.lamp.shadow.map?.depthTexture,
          lampAngle: lighting.lamp.angle,
          lampIntensity: lighting.lamp.intensity,
          enabled: view.volumetric.enabled,
        }),
        books: () => {
          const out: Record<string, unknown>[] = [];
          room.shelf.group.children.forEach((o) => {
            if (!o.userData.dynamic) return;
            out.push({
              x: +o.position.x.toFixed(4),
              y: +o.position.y.toFixed(4),
              z: +o.position.z.toFixed(4),
              rz: +o.rotation.z.toFixed(3),
              ry: +o.rotation.y.toFixed(3),
              s: +o.scale.x.toFixed(3),
              vis: o.visible,
            });
          });
          return out;
        },
        topLevel: () => scene.children.map((o, i) => `${i}:${o.type}:${o.name || o.userData.projectId || ''}`),
        hideTop: (i: number) => {
          scene.children.forEach((o, k) => { if (k === i) o.visible = false; });
        },
        showAll: () => scene.children.forEach((o) => (o.visible = true)),
        /** Diagnostics: keep one light (or none) and mute the rest. */
        soloLight: (keep: number) => {
          const all: THREE.Light[] = [];
          scene.traverse((o) => { if ((o as THREE.Light).isLight) all.push(o as THREE.Light); });
          all.forEach((l, i) => { l.userData.saved ??= l.intensity; l.intensity = i === keep ? l.userData.saved : 0; });
          return all.map((l, i) => `${i}:${l.type}`);
        },
        lights: () => {
          const out: Record<string, unknown>[] = [];
          scene.traverse((o) => {
            const l = o as THREE.Light;
            if (!l.isLight) return;
            const entry: Record<string, unknown> = {
              type: l.type,
              intensity: Number(l.intensity.toFixed(3)),
              world: l.getWorldPosition(new THREE.Vector3()).toArray().map((v) => Number(v.toFixed(3))),
            };
            const spot = l as THREE.SpotLight;
            if (spot.isSpotLight) {
              entry.targetWorld = spot.target.getWorldPosition(new THREE.Vector3()).toArray().map((v) => Number(v.toFixed(3)));
              entry.angle = Number(spot.angle.toFixed(3));
              entry.distance = spot.distance;
            }
            out.push(entry);
          });
          return out;
        },
      },
    });
  }
}

start().catch((err) => {
  console.error(err);
  loader.fail('This room needs WebGL. Try a current desktop browser.');
  document.getElementById('veil')!.classList.add('is-lifted');
});
