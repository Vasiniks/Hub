import './styles.css';
import * as THREE from 'three';
import { projects } from './data/projects';
import { createMaterials } from './scene/materials';
import { buildRoom } from './scene/room';
import { createScreens } from './scene/screens';
import { createLighting } from './scene/lighting';
import { createExterior } from './scene/exterior';
import { createRenderer } from './scene/renderer';
import { CameraRig } from './camera/rig';
import { createInteraction, OVERLAY_LAYER } from './interaction/interaction';
import { createPanel, createHint, createObjectNav } from './ui/panel';
import { FramePerf } from './debug/perf';

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const params = new URLSearchParams(location.search);
const hourParam = params.get('hour');
const hourOverride = hourParam !== null && !Number.isNaN(Number(hourParam)) ? Number(hourParam) : null;

const canvas = document.getElementById('scene') as HTMLCanvasElement;
const hint = createHint();

function start() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#0f1216');
  scene.fog = new THREE.FogExp2('#0f1216', 0.08);

  const camera = new THREE.PerspectiveCamera(56, window.innerWidth / window.innerHeight, 0.02, 40);
  camera.layers.enable(OVERLAY_LAYER);

  const materials = createMaterials();
  const room = buildRoom(materials);
  scene.add(room.root);

  const screens = createScreens();
  for (const [mesh, tex] of [[room.mainScreen, screens.mainTex], [room.sideScreen, screens.sideTex]] as const) {
    const mat = mesh.material as THREE.MeshStandardMaterial;
    mat.emissiveMap = tex;
    mat.needsUpdate = true;
  }

  const exterior = createExterior(scene, room.windowCenter);
  const lighting = createLighting(scene, room, exterior);
  const view = createRenderer(canvas, scene, camera, lighting.sun);
  const rig = new CameraRig(camera, room, reducedMotion);
  const interaction = createInteraction({
    scene,
    camera,
    outline: view.outline,
    projects,
    materials,
    reducedMotion,
    label: document.getElementById('hover-label')!,
  });

  // ---- Shadow-casting motion ----------------------------------------------
  // Animated parts that cast shadows (the chair is handled by the sitting check in the loop).
  const casters: { node: THREE.Object3D; quat: THREE.Quaternion; pos: THREE.Vector3; reach: number }[] = [];
  scene.updateMatrixWorld(true);
  scene.traverse((o) => {
    if (!o.userData.dynamic || o === room.chair) return;
    let casts = false;
    o.traverse((c) => {
      if ((c as THREE.Mesh).isMesh && c.castShadow) casts = true;
    });
    if (!casts) return;
    // Bounds padded by how far its shadow can plausibly fall.
    const reach = new THREE.Box3().setFromObject(o).getBoundingSphere(new THREE.Sphere()).radius + 0.2;
    casters.push({ node: o, quat: o.getWorldQuaternion(new THREE.Quaternion()), pos: o.getWorldPosition(new THREE.Vector3()), reach });
  });
  const _casterQuat = new THREE.Quaternion();
  const _casterPos = new THREE.Vector3();
  const _viewProjection = new THREE.Matrix4();
  const _frustum = new THREE.Frustum();
  const _reachSphere = new THREE.Sphere();
  /**
   * Largest change since the last shadow redraw among casters whose shadow could be on screen,
   * normalised so that 1 means "visible". Off-screen motion keeps accumulating and is caught up
   * as soon as the object comes back into view.
   */
  function casterMotion() {
    _viewProjection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    _frustum.setFromProjectionMatrix(_viewProjection);
    let motion = 0;
    for (const c of casters) {
      c.node.getWorldPosition(_casterPos);
      if (!_frustum.intersectsSphere(_reachSphere.set(_casterPos, c.reach))) continue;
      c.node.getWorldQuaternion(_casterQuat);
      const angle = 2 * Math.acos(Math.min(1, Math.abs(_casterQuat.dot(c.quat))));
      motion = Math.max(motion, angle / 0.09, _casterPos.distanceTo(c.pos) / 0.004);
    }
    if (motion > 1) {
      for (const c of casters) {
        c.node.getWorldQuaternion(c.quat);
        c.node.getWorldPosition(c.pos);
      }
    }
    return motion;
  }

  // ---- Time of day -------------------------------------------------------
  let liveHour = hourOverride;
  const hourNow = () => {
    if (liveHour !== null) return liveHour;
    const d = new Date();
    return d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600;
  };
  let capturedHour = -99;
  function refreshLight(force = false) {
    const hour = hourNow();
    view.applyLight(lighting.apply(hour));
    // Reflections and indirect light follow the day: re-captured every five minutes of real
    // time, spread over several frames so the update never hitches.
    const drift = Math.abs(hour - capturedHour);
    if (force || Math.min(drift, 24 - drift) >= 1 / 12) {
      view.requestEnvironmentCapture();
      capturedHour = hour;
    }
  }

  // ---- Project view ------------------------------------------------------
  let focusTitle: string | null = null;
  let pendingOpen: string | null = null;
  let panelShown = false;
  let activityPulse = 0;

  const panel = createPanel(() => closeProject());

  function openProject(id: string) {
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
    focusTitle = project.title;
    activityPulse = 1;
    hint.hide();
    rig.focus(interaction.focusTarget(id));
  }

  function closeProject() {
    if (rig.mode !== 'focused' && rig.mode !== 'focusing') return;
    panel.close();
    panelShown = false;
    interaction.setFocused(null);
    focusTitle = null;
    rig.unfocus();
  }

  rig.onFocusProgress = (t) => {
    if (!panelShown && t > 0.55) {
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

  createObjectNav(projects, {
    onFocus: (id) => interaction.setForcedHover(id),
    onBlur: () => interaction.setForcedHover(null),
    onActivate: (id) => openProject(id),
  });

  // ---- Input -------------------------------------------------------------
  window.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      if (rig.mode === 'standing' && e.deltaY > 2) sit();
    },
    { passive: false },
  );

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeProject();
      return;
    }
    const onBody = document.activeElement === document.body || document.activeElement === null;
    if (onBody && rig.mode === 'standing' && ['ArrowDown', ' ', 'Enter', 'PageDown'].includes(e.key)) {
      e.preventDefault();
      sit();
    }
  });

  window.addEventListener('pointermove', (e) => {
    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = -(e.clientY / window.innerHeight) * 2 + 1;
    rig.setPointer(nx, ny);
    interaction.setPointer(nx, ny, e.target === canvas);
  });
  document.addEventListener('pointerleave', () => interaction.setPointer(-10, -10, false));

  let downAt: { x: number; y: number } | null = null;
  canvas.addEventListener('pointerdown', (e) => (downAt = { x: e.clientX, y: e.clientY }));
  canvas.addEventListener('pointerup', (e) => {
    if (!downAt || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 6) return;
    downAt = null;
    if (rig.mode === 'focused' || rig.mode === 'focusing') {
      closeProject();
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

    rig.holdLook(interaction.hoveredId !== null && rig.interactive);
    rig.update(dt);
    perf.lap('camera');
    interaction.setEnabled(rig.interactive);
    interaction.update(dt, elapsed);
    perf.lap('interaction');
    screens.update({ focusTitle, time: elapsed });

    // Small reactions: fans spin up briefly when something is opened.
    activityPulse = Math.max(0, activityPulse - dt * 0.25);
    const fanSpeed = reducedMotion ? 0 : 7 + activityPulse * 22;
    for (const fan of room.fans) fan.rotation.z -= fanSpeed * dt;

    perf.lap('screens+reactions');

    view.render(dt, elapsed, !reducedMotion);
    perf.lap('render');

    // Light advances on a one-second tick. Shadow maps redraw only when something that casts them
    // has visibly moved: every frame while the chair rolls in, otherwise once an animated part has
    // turned or shifted enough to show (often while it's being examined, rarely at rest).
    lightTimer += dt;
    if (lightTimer > 1) {
      lightTimer = 0;
      refreshLight();
    }
    if (rig.mode === 'sitting' || casterMotion() > 1) lighting.markShadowsDirty('both');
    perf.lap('lighting+shadows');
    perf.endFrame(view.renderer.info.render.calls, view.renderer.info.render.triangles, view.renderer.info.programs?.length ?? 0);

    if (firstFrame) {
      firstFrame = false;
      requestAnimationFrame(() => document.getElementById('veil')!.classList.add('is-lifted'));
      window.setTimeout(() => {
        if (rig.mode === 'standing') hint.show('Scroll to sit down');
      }, 2200);
    }
  }
  // Compile shaders and capture the room's light while the veil is still down.
  view.warmUp(scene.children.filter((o) => o.userData.projectId !== undefined)).finally(() => {
    capturedHour = hourNow();
    last = performance.now();
    requestAnimationFrame(frame);
  });

  if (params.has('debug')) {
    Object.assign(window, {
      __room: {
        mode: () => rig.mode,
        hovered: () => interaction.hoveredId,
        panelOpen: () => panel.isOpen,
        screenPositionOf: (id: string) => interaction.screenPositionOf(id),
        hitPositionOf: (id: string) => interaction.hitPositionOf(id),
        debugPick: (x: number, y: number) => interaction.debugPick(x, y),
        debugState: () => interaction.debugState(),
        debugDots: () => interaction.debugDots(),
        frames: () => frameCount,
        programs: () => (view.renderer.info.programs ?? []).map((p) => p.name),
        programKeys: () => (view.renderer.info.programs ?? []).map((p) => `${p.name}::${p.cacheKey}`),
        shadowRequests: () => ({ ...lighting.shadowRequests }),
        // Isolation: outline an object directly, with no hover, look-hold, or object activity.
        outlineOnly: (id: string | null) => {
          const group = id ? scene.children.find((o) => o.userData.projectId === id) : undefined;
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
      },
    });
  }
}

try {
  start();
} catch (err) {
  console.error(err);
  document.getElementById('veil')!.classList.add('is-lifted');
  hint.show('This room needs WebGL to render. Try a current desktop browser.');
}
