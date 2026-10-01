import * as THREE from 'three';
import type { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';
import type { CameraRig, FocusTarget } from '../camera/rig';
import { createInteraction, type InteractTarget } from './interaction';
import { createObjectNav, createPanel, type PanelContent } from '../ui/panel';
import { INTERACTION } from '../scene/layout';

export type { PanelContent };
type Vec3 = [number, number, number];

/**
 * How the camera examines a prop. Every field is optional: the defaults frame the node's bounds
 * from the visitor's side of it, which is right for most desk objects. Wall fixtures and anything
 * that must be seen from a particular side set `yaw` (and usually `distance`).
 */
export interface PropFocus {
  /** World-space point the camera looks at. Default: the centre of the node's bounds. */
  center?: Vec3;
  /** Metres from `center`. Default: the bounds fitted into the focus lens, with room to breathe. */
  distance?: number;
  /** Approach direction about +y, radians (0 = from +z, π/2 = from +x). Default: from the seat. */
  yaw?: number;
  /** Elevation of the approach, radians. Default 0.32. */
  pitch?: number;
  /** Aim right of the object by this fraction of `distance`, so it sits beside the panel. Default 0.3. */
  offset?: number;
}

/** One interactive object. `register(spec)` is the whole integration for a loaded GLB node. */
export interface PropSpec {
  /** Stable id: the debug hooks, the object nav and the analytics all key on it. */
  id: string;
  /** Hover label and keyboard-nav button text. */
  label: string;
  /**
   * The loaded node(s). Several nodes (a baked fixture split across meshes, a prop exported as
   * parts) are grouped in place under one parent, keeping their world transforms.
   */
  node: THREE.Object3D | THREE.Object3D[];
  panel: PanelContent;
  focus?: PropFocus;
  /** Where the attention dot sits. Default: 3.5 cm above the top centre of the bounds. */
  dot?: Vec3;
  /** A few millimetres of lift under attention. Default true; fixtures and baked meshes pass false. */
  lift?: boolean;
  /** Per-frame animation; `activity` rises 0→1 while hovered or examined (the robot's lens, a screen). */
  tick?: (time: number, activity: number) => void;
}

const DEFAULT_PITCH = 0.32;
const DEFAULT_OFFSET = 0.3;

/**
 * The v2 room's interaction layer: hover, attention dots, outline, click to examine, panel,
 * Esc / click-outside back, and keyboard navigation — the default room's own modules
 * (`createInteraction`, `createPanel`, `createObjectNav`, the rig's focus moves), wired once, with
 * objects added by `register()` as they load.
 *
 * Movement stays with the caller: it owns the wheel/keys that sit the visitor down and feeds the
 * rig the pointer. This owns everything that happens because of an object, and asks the caller to
 * call `resumePending()` from `rig.onSeated`, so a click on an object while standing sits down
 * first and then opens it — as in the default room.
 */
export function createPropRegistry(opts: {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  rig: CameraRig;
  outline: OutlinePass;
  canvas: HTMLCanvasElement;
  /** Where the seated visitor's eye is: default focus moves approach from this side. */
  seat: Vec3;
  reducedMotion: boolean;
  hint: { hide(): void };
  /** Called when an object is opened, e.g. to stop a "look around" prompt. */
  onOpen?: (id: string) => void;
}) {
  const { scene, camera, rig, outline, canvas, reducedMotion, hint } = opts;
  const seat = new THREE.Vector3(...opts.seat);
  const specs = new Map<string, PropSpec>();
  const targets = new Map<string, InteractTarget>();

  const interaction = createInteraction({
    scene,
    camera,
    outline,
    targets: [],
    reducedMotion,
    label: document.getElementById('hover-label')!,
    lookExtent: () => rig.lookExtent(),
  });
  const panel = createPanel(() => close());
  const nav = createObjectNav([], {
    onFocus: (id) => interaction.setForcedHover(id),
    onBlur: () => interaction.setForcedHover(null),
    onActivate: (id) => open(id),
  });

  let pendingOpen: string | null = null;
  let panelShown = false;
  let focusedId: string | null = null;

  /** Group several nodes in place under their common parent, without moving anything. */
  function groupOf(id: string, node: PropSpec['node']): THREE.Object3D {
    if (!Array.isArray(node)) return node;
    if (node.length === 1) return node[0];
    if (node.length === 0) throw new Error(`props: "${id}" has no nodes`);
    const parent = node[0].parent ?? scene;
    const group = new THREE.Group();
    group.name = `prop:${id}`;
    parent.add(group);
    group.updateMatrixWorld(true);
    for (const n of node) group.attach(n);
    return group;
  }

  /** Default framing: the bounds fitted into the focus lens, approached from the seat's side. */
  function focusFrom(spec: PropSpec, box: THREE.Box3): FocusTarget {
    const f = spec.focus ?? {};
    const center = f.center ? new THREE.Vector3(...f.center) : box.getCenter(new THREE.Vector3());
    const radius = Math.max(0.04, box.getBoundingSphere(new THREE.Sphere()).radius);
    const halfFov = THREE.MathUtils.degToRad(rig.focusFov / 2);
    const distance = f.distance ?? Math.max(0.3, (radius / Math.sin(halfFov)) * 1.4);
    const yaw = f.yaw ?? Math.atan2(seat.x - center.x, seat.z - center.z);
    return { center, distance, yaw, pitch: f.pitch ?? DEFAULT_PITCH, offset: f.offset ?? DEFAULT_OFFSET };
  }

  /**
   * Make a loaded node interactive. One call: it gets an attention dot, hover outline and label,
   * a focus move, the panel, and a keyboard-nav button. Returns the interaction target.
   */
  function register(spec: PropSpec): InteractTarget {
    if (specs.has(spec.id)) throw new Error(`props: "${spec.id}" is already registered`);
    const group = groupOf(spec.id, spec.node);
    group.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(group);
    if (box.isEmpty()) throw new Error(`props: "${spec.id}" has no geometry`);
    const focus = focusFrom(spec, box);
    const dotPos = spec.dot
      ? new THREE.Vector3(...spec.dot)
      : new THREE.Vector3((box.min.x + box.max.x) / 2, box.max.y + 0.035, (box.min.z + box.max.z) / 2);
    const target: InteractTarget = {
      id: spec.id,
      title: spec.label,
      group,
      anchor: focus.center.clone(),
      dotPos,
      focus: () => ({ ...focus, center: focus.center.clone() }),
      tick: spec.tick,
      lift: spec.lift,
    };
    specs.set(spec.id, spec);
    targets.set(spec.id, target);
    interaction.add(target);
    nav.add({ id: spec.id, label: spec.label });
    return target;
  }

  function open(id: string) {
    const spec = specs.get(id);
    if (!spec) return;
    // From standing, sit first; the open resumes from `resumePending()` once seated.
    if (rig.mode === 'standing') {
      pendingOpen = id;
      if (rig.sitDown()) hint.hide();
      return;
    }
    if (rig.mode === 'sitting') {
      pendingOpen = id;
      return;
    }
    panel.fillContent(spec.panel);
    panelShown = false;
    if (panel.isOpen) panel.close();
    focusedId = id;
    interaction.setFocused(id);
    hint.hide();
    opts.onOpen?.(id);
    rig.focus(interaction.focusTarget(id));
  }

  function close() {
    if (rig.mode !== 'focused' && rig.mode !== 'focusing') return false;
    panel.close();
    panelShown = false;
    focusedId = null;
    interaction.setFocused(null);
    rig.unfocus();
    return true;
  }

  rig.onFocusProgress = (t) => {
    if (!panelShown && t > 0.55) {
      panelShown = true;
      panel.open();
    }
  };

  // ---- Input: everything that happens because of an object -------------------------------
  window.addEventListener('pointermove', (e) => {
    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = -(e.clientY / window.innerHeight) * 2 + 1;
    interaction.setPointer(nx, ny, e.target === canvas);
  });
  document.addEventListener('pointerleave', () => interaction.setPointer(-10, -10, false));
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });

  let downAt: { x: number; y: number } | null = null;
  canvas.addEventListener('pointerdown', (e) => {
    downAt = { x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener('pointerup', (e) => {
    if (!downAt || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > INTERACTION.clickSlopPx) return;
    downAt = null;
    // Click outside the panel while examining: back to the seat.
    if (close()) return;
    const id = interaction.hoveredId;
    if (id && (rig.mode === 'standing' || rig.mode === 'seated')) open(id);
  });

  return {
    register,
    open,
    close,
    /** Call from `rig.onSeated`. True when a click made while standing has now been opened. */
    resumePending() {
      if (!pendingOpen) return false;
      const id = pendingOpen;
      pendingOpen = null;
      open(id);
      return true;
    },
    /** Once per frame, after `rig.update` (the picking reads this frame's camera). */
    update(dt: number, time: number) {
      interaction.setEnabled(rig.interactive);
      interaction.update(dt, time);
    },
    /** Once per frame, before `rig.update`: the head holds still while the cursor rests on an object. */
    holdLook() {
      rig.holdLook(interaction.hoveredId !== null && !interaction.hoverIsCentred && rig.interactive);
    },
    /** Every registered root, for shader warm-up (outline variants) and occlusion bookkeeping. */
    groups: () => [...targets.values()].map((t) => t.group),
    ids: () => [...specs.keys()],
    get hoveredId() {
      return interaction.hoveredId;
    },
    get focusedId() {
      return focusedId;
    },
    get panelOpen() {
      return panel.isOpen;
    },
    interaction,
  };
}

export type PropRegistry = ReturnType<typeof createPropRegistry>;
