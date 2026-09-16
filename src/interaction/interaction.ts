import * as THREE from 'three';
import type { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';
import type { ProjectDef } from '../data/projects';
import type { Materials } from '../scene/materials';
import { buildObject, type BuiltObject } from '../scene/objects';
import type { FocusTarget } from '../camera/rig';

import { OVERLAY_LAYER } from '../scene/layers';

export { OVERLAY_LAYER };

interface Interactable {
  project: ProjectDef;
  built: BuiltObject;
  anchor: THREE.Vector3;
  dotPos: THREE.Vector3;
  dot: THREE.Sprite;
  ring: THREE.Sprite;
  activity: number;
  visited: boolean;
}

function dotTexture(hollow: boolean) {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const ctx = c.getContext('2d')!;
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, 'rgba(255,255,255,0.35)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  ctx.beginPath();
  ctx.arc(32, 32, 13, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(12,14,18,0.32)';
  ctx.fill();
  ctx.beginPath();
  ctx.arc(32, 32, 9, 0, Math.PI * 2);
  if (hollow) {
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    ctx.lineWidth = 3;
    ctx.stroke();
  } else {
    ctx.fillStyle = '#ffffff';
    ctx.fill();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function ringTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const ctx = c.getContext('2d')!;
  ctx.beginPath();
  ctx.arc(32, 32, 26, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(12,14,18,0.35)';
  ctx.lineWidth = 5;
  ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,1)';
  ctx.lineWidth = 2.5;
  ctx.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function createInteraction(opts: {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  outline: OutlinePass;
  projects: ProjectDef[];
  materials: Materials;
  reducedMotion: boolean;
  label: HTMLElement;
}) {
  const { scene, camera, outline, projects, materials, reducedMotion, label } = opts;
  const solidTex = dotTexture(false);
  const hollowTex = dotTexture(true);
  const ringTex = ringTexture();

  const items = new Map<string, Interactable>();
  const groups: THREE.Object3D[] = [];

  for (const project of projects) {
    const built = buildObject(project.object.builder, materials);
    const g = built.group;
    g.position.set(...project.object.position);
    g.rotation.y = project.object.rotationY;
    g.scale.setScalar(project.object.scale ?? 1);
    g.userData.projectId = project.id;
    scene.add(g);
    g.updateMatrixWorld(true);
    groups.push(g);

    const anchor = g.localToWorld(new THREE.Vector3(...project.anchor));
    const box = new THREE.Box3().setFromObject(g);
    const dotPos = new THREE.Vector3((box.min.x + box.max.x) / 2, box.max.y + 0.035, (box.min.z + box.max.z) / 2);

    const mat = (map: THREE.Texture, opacity: number) =>
      new THREE.SpriteMaterial({ map, transparent: true, opacity, depthWrite: false, sizeAttenuation: false, toneMapped: false });
    const dot = new THREE.Sprite(mat(solidTex, 0.9));
    dot.scale.setScalar(0.022);
    const ring = new THREE.Sprite(mat(ringTex, 0));
    ring.scale.setScalar(0.022);
    dot.userData.ignoreRaycast = true;
    ring.userData.ignoreRaycast = true;
    for (const s of [dot, ring]) {
      s.userData.projectId = project.id;
      s.position.copy(dotPos);
      s.layers.set(OVERLAY_LAYER);
      s.renderOrder = 10;
      scene.add(s);
    }
    items.set(project.id, { project, built, anchor, dotPos, dot, ring, activity: 0, visited: false });
  }

  /** Screen-space radius around a visible dot that counts as hovering its object. */
  const DOT_RADIUS_PX = 30;
  /** Once hovered, an object stays hovered within this wider radius (hysteresis). */
  const DOT_RETAIN_PX = 64;
  const raycaster = new THREE.Raycaster();
  raycaster.layers.enableAll();
  const occluder = new THREE.Raycaster();
  occluder.layers.enableAll();
  // Sprites can only be raycast with a camera attached; without it Sprite.raycast throws.
  occluder.camera = camera;
  const toDot = new THREE.Vector3();
  const ndc = new THREE.Vector2(-10, -10);
  const probe = new THREE.Vector2();
  let pointerInside = false;
  // Picking is skipped on frames where neither the pointer nor the view has meaningfully moved.
  let pointerDirty = true;
  let lastPicked: string | null = null;
  const lastPickQuat = new THREE.Quaternion();
  let hovered: string | null = null;
  let forced: string | null = null;
  let focused: string | null = null;
  let enabled = true;
  const projected = new THREE.Vector3();

  /** Nearest visible surface under a screen point; the attention dot counts as part of its object. */
  function pickAt(point: THREE.Vector2): string | null {
    raycaster.setFromCamera(point, camera);
    const hit = raycaster
      .intersectObjects(scene.children, true)
      .find((h) => h.object.visible && !h.object.userData.ignoreRaycast && h.object.layers.test(camera.layers));
    let o: THREE.Object3D | null = hit?.object ?? null;
    while (o && o.userData.projectId === undefined) o = o.parent;
    return (o?.userData.projectId as string | undefined) ?? null;
  }

  function dotUnoccluded(id: string, item: Interactable) {
    toDot.copy(item.dotPos).sub(camera.position);
    const dist = toDot.length();
    occluder.set(camera.position, toDot.normalize());
    occluder.far = dist;
    const hit = occluder
      .intersectObjects(scene.children, true)
      .find((h) => h.object.visible && !h.object.userData.ignoreRaycast);
    if (!hit || hit.distance > dist - 0.03) return true;
    let o: THREE.Object3D | null = hit.object;
    while (o && o.userData.projectId === undefined) o = o.parent;
    return o?.userData.projectId === id;
  }

  function pick(): string | null {
    if (!pointerInside) return null;
    const direct = pickAt(ndc);
    if (direct) return direct;
    // Generous target: a visible, unoccluded attention dot near the cursor stands in for its object.
    const px = (ndc.x * 0.5 + 0.5) * window.innerWidth;
    const py = (-ndc.y * 0.5 + 0.5) * window.innerHeight;
    if (hovered && !forced) {
      const current = items.get(hovered)!;
      const s = screenOf(current.dotPos);
      if (s.visible && Math.hypot(s.x - px, s.y - py) < DOT_RETAIN_PX && dotUnoccluded(hovered, current)) return hovered;
    }
    let best: string | null = null;
    let bestDist = DOT_RADIUS_PX;
    for (const [id, item] of items) {
      const s = screenOf(item.dotPos);
      if (!s.visible) continue;
      const d = Math.hypot(s.x - px, s.y - py);
      if (d < bestDist && dotUnoccluded(id, item)) {
        best = id;
        bestDist = d;
      }
    }
    return best;
  }

  function screenOf(p: THREE.Vector3) {
    projected.copy(p).project(camera);
    // Points behind the camera project mirrored; flip so the direction toward them stays true.
    const behind = projected.z > 1;
    const x = behind ? -projected.x : projected.x;
    const y = behind ? -projected.y : projected.y;
    return {
      x: (x * 0.5 + 0.5) * window.innerWidth,
      y: (-y * 0.5 + 0.5) * window.innerHeight,
      visible: !behind && Math.abs(x) < 1.05 && Math.abs(y) < 1.05,
    };
  }

  return {
    get hoveredId() {
      return hovered;
    },
    setPointer(x: number, y: number, inside: boolean) {
      ndc.set(x, y);
      pointerInside = inside;
      pointerDirty = true;
    },
    setEnabled(v: boolean) {
      enabled = v;
    },
    setForcedHover(id: string | null) {
      forced = id;
    },
    setFocused(id: string | null) {
      focused = id;
      if (id) {
        const item = items.get(id)!;
        item.visited = true;
        item.dot.material.map = hollowTex;
        item.dot.material.needsUpdate = true;
      }
    },
    focusTarget(id: string): FocusTarget {
      const item = items.get(id)!;
      const { distance, yaw, pitch } = item.project.focus;
      return { center: item.anchor.clone(), distance, yaw, pitch };
    },
    screenPositionOf(id: string) {
      const item = items.get(id);
      return item ? screenOf(item.anchor) : null;
    },
    /** Raw intersections under a client point, for diagnosing picking in the browser. */
    debugPick(clientX: number, clientY: number) {
      probe.set((clientX / window.innerWidth) * 2 - 1, -(clientY / window.innerHeight) * 2 + 1);
      raycaster.setFromCamera(probe, camera);
      return raycaster
        .intersectObjects(scene.children, true)
        .slice(0, 6)
        .map((h) => {
          let o: THREE.Object3D | null = h.object;
          while (o && o.userData.projectId === undefined) o = o.parent;
          return {
            type: h.object.type,
            name: h.object.name,
            distance: Number(h.distance.toFixed(3)),
            visible: h.object.visible,
            ignore: !!h.object.userData.ignoreRaycast,
            layerOk: h.object.layers.test(camera.layers),
            projectId: (o?.userData.projectId as string | undefined) ?? null,
          };
        });
    },
    debugDots() {
      return [...items].map(([id, item]) => {
        const s = screenOf(item.dotPos);
        let unoccluded: boolean | string;
        try {
          unoccluded = dotUnoccluded(id, item);
        } catch (e) {
          unoccluded = `threw: ${(e as Error).message}`;
        }
        return { id, x: Math.round(s.x), y: Math.round(s.y), visible: s.visible, unoccluded };
      });
    },
    debugState() {
      return { pointerInside, ndc: ndc.toArray(), enabled, hovered, forced, focused };
    },
    /** A screen point that genuinely resolves to this object (used by browser tests). */
    hitPositionOf(id: string) {
      const item = items.get(id);
      if (!item) return null;
      const dot = screenOf(item.dotPos);
      if (dot.visible && dotUnoccluded(id, item)) return dot;
      const candidates: THREE.Vector3[] = [];
      item.built.group.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        m.geometry.computeBoundingSphere();
        candidates.push(m.localToWorld(m.geometry.boundingSphere!.center.clone()));
      });
      for (const p of candidates) {
        const s = screenOf(p);
        if (!s.visible) continue;
        probe.set((s.x / window.innerWidth) * 2 - 1, -(s.y / window.innerHeight) * 2 + 1);
        if (pickAt(probe) === id) return s;
      }
      return null;
    },
    update(dt: number, time: number) {
      let picked: string | null = null;
      if (enabled && !focused) {
        // 1 - |q·q'| ≈ θ²/8: re-pick once the view has turned by roughly 0.02°.
        const turned = 1 - Math.abs(lastPickQuat.dot(camera.quaternion)) > 2e-8;
        if (pointerDirty || turned) {
          lastPicked = pick();
          pointerDirty = false;
          lastPickQuat.copy(camera.quaternion);
        }
        picked = lastPicked;
      } else {
        lastPicked = null;
        pointerDirty = true;
      }
      const next = forced ?? picked;
      if (next !== hovered) {
        hovered = next;
        document.body.classList.toggle('is-hovering', !!picked);
        outline.selectedObjects = hovered ? [items.get(hovered)!.built.group] : [];
        outline.enabled = hovered !== null;
        if (hovered) label.textContent = items.get(hovered)!.project.title;
      }

      for (const [id, item] of items) {
        const wanted = id === hovered || id === focused ? 1 : 0;
        item.activity = THREE.MathUtils.lerp(item.activity, wanted, 1 - Math.exp(-4 * dt));
        item.built.tick?.(time, item.activity);

        // Dots stay quiet: fade entirely while examining something.
        const base = focused ? 0 : item.visited ? 0.55 : 0.9;
        const dm = item.dot.material;
        dm.opacity = THREE.MathUtils.lerp(dm.opacity, id === hovered ? 1 : base, 1 - Math.exp(-6 * dt));
        item.dot.scale.setScalar(0.02 + item.activity * 0.004);

        const rm = item.ring.material;
        if (!reducedMotion && !focused && !item.visited) {
          const phase = ((time + id.length * 0.37) % 3.2) / 3.2;
          const p = Math.min(1, phase / 0.6);
          item.ring.scale.setScalar(0.02 + p * 0.028);
          rm.opacity = (1 - p) * 0.4 * dm.opacity;
        } else {
          rm.opacity = 0;
        }
      }

      if (hovered && !focused) {
        const s = screenOf(items.get(hovered)!.dotPos);
        label.style.transform = `translate(${s.x}px, ${s.y - 16}px) translate(-50%, -100%)`;
        label.classList.toggle('is-visible', s.visible);
      } else {
        label.classList.remove('is-visible');
      }
    },
  };
}
