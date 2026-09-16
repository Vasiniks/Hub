import * as THREE from 'three';
import type { Materials } from './materials';
import { SHELF } from './layout';
import { at, rbox, shadowed } from './build';
import { books, type BookDef } from '../data/books';
import { OVERLAY_LAYER } from './layers';

/**
 * §15: the bookshelf is a real mechanism, not a prop.
 *
 * Browsing keeps the visitor in the room. The selected book physically slides out of the row,
 * lifts, and turns its cover toward the camera; its neighbours ease apart and settle back into
 * the shelf. Motion is a lightly underdamped spring per book, so the row has weight and the
 * selection lands with a settle rather than a snap.
 *
 * Each book is a single mesh. Cover, spine and page edges live in one small atlas texture and
 * are addressed by remapping the box's per-face UVs, so a book costs one draw call.
 */

const COVER_U = [0.0, 0.6] as const;
const SPINE_U = [0.62, 0.74] as const;
const PAGE_U = [0.78, 1.0] as const;

function bookAtlas(def: BookDef) {
  const S = 384;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const ctx = c.getContext('2d')!;
  const x0 = COVER_U[0] * S;
  const cw = (COVER_U[1] - COVER_U[0]) * S;

  // Cover: a quiet field, one rule, one mark, and small type. Restrained enough to sit in
  // this room rather than look like a book-cover generator.
  const g = ctx.createLinearGradient(x0, 0, x0 + cw, S);
  g.addColorStop(0, def.color);
  g.addColorStop(1, '#0d0f12');
  ctx.fillStyle = g;
  ctx.fillRect(x0, 0, cw, S);
  ctx.strokeStyle = def.accent;
  ctx.globalAlpha = 0.5;
  ctx.lineWidth = 2;
  ctx.strokeRect(x0 + 14, 14, cw - 28, S - 28);
  ctx.globalAlpha = 1;
  ctx.fillStyle = def.accent;
  ctx.fillRect(x0 + 30, S * 0.6, cw - 60, 3);
  ctx.globalAlpha = 0.85;
  ctx.beginPath();
  ctx.arc(x0 + cw / 2, S * 0.34, cw * 0.16, 0, Math.PI * 2);
  ctx.lineWidth = 3;
  ctx.strokeStyle = def.accent;
  ctx.stroke();
  ctx.globalAlpha = 1;
  ctx.fillStyle = def.accent;
  ctx.font = '600 21px "IBM Plex Sans Condensed", system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(def.title.toUpperCase(), x0 + cw / 2, S * 0.7, cw - 44);
  ctx.globalAlpha = 0.6;
  ctx.font = '400 15px "IBM Plex Sans", system-ui, sans-serif';
  ctx.fillText(def.author, x0 + cw / 2, S * 0.76, cw - 44);
  ctx.globalAlpha = 1;

  // Spine: same field, title running vertically.
  const sx = SPINE_U[0] * S;
  const sw = (SPINE_U[1] - SPINE_U[0]) * S;
  ctx.fillStyle = def.color;
  ctx.fillRect(sx, 0, sw, S);
  ctx.fillStyle = def.accent;
  ctx.globalAlpha = 0.45;
  ctx.fillRect(sx + 4, 16, sw - 8, 2);
  ctx.fillRect(sx + 4, S - 18, sw - 8, 2);
  ctx.globalAlpha = 1;
  ctx.save();
  ctx.translate(sx + sw / 2, S * 0.62);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center';
  ctx.font = '600 15px "IBM Plex Sans Condensed", system-ui, sans-serif';
  ctx.fillText(def.title.toUpperCase(), 0, 5, S * 0.55);
  ctx.restore();

  // Page edges.
  const px = PAGE_U[0] * S;
  const pw = (PAGE_U[1] - PAGE_U[0]) * S;
  ctx.fillStyle = '#ddd8cd';
  ctx.fillRect(px, 0, pw, S);
  ctx.strokeStyle = 'rgba(120,112,98,0.5)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 46; i++) {
    const y = (i / 46) * S;
    ctx.beginPath();
    ctx.moveTo(px, y);
    ctx.lineTo(px + pw, y);
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Point each box face at its region of the atlas: +x cover, +z spine, everything else pages. */
function remapBookUVs(geo: THREE.BoxGeometry) {
  const uv = geo.getAttribute('uv') as THREE.BufferAttribute;
  const region = (face: number): readonly [number, number] => (face === 0 ? COVER_U : face === 4 ? SPINE_U : PAGE_U);
  for (let face = 0; face < 6; face++) {
    const [u0, u1] = region(face);
    for (let v = 0; v < 4; v++) {
      const i = face * 4 + v;
      uv.setX(i, u0 + uv.getX(i) * (u1 - u0));
    }
  }
  uv.needsUpdate = true;
  return geo;
}

function chevronTexture(flip: boolean) {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const ctx = c.getContext('2d')!;
  ctx.translate(32, 32);
  if (flip) ctx.scale(-1, 1);
  ctx.strokeStyle = 'rgba(255,255,255,0.92)';
  ctx.lineWidth = 5;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.beginPath();
  ctx.moveTo(6, -14);
  ctx.lineTo(-8, 0);
  ctx.lineTo(6, 14);
  ctx.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

interface BookNode {
  def: BookDef;
  mesh: THREE.Mesh;
  material: THREE.MeshStandardMaterial;
  /** Rest pose in shelf-local space. */
  homeX: number;
  homeLean: number;
  /** Spring state for the pull-out amount, 0 at rest and 1 fully selected. */
  out: number;
  outVel: number;
  /** Smoothed sideways shove from the selected book. */
  shove: number;
  base: THREE.Color;
}

export type Bookshelf = ReturnType<typeof createBookshelf>;

export function createBookshelf(root: THREE.Group, m: Materials, reducedMotion: boolean) {
  const group = at(new THREE.Group(), SHELF.x, SHELF.y, SHELF.z, root);
  // Local +x runs along the wall, local +z points into the room.
  group.rotation.y = Math.PI / 2;

  const W = SHELF.width;
  const D = SHELF.depth;
  const carcass = at(new THREE.Group(), 0, 0, 0, group);

  // A real wall unit: browsing board, a board above, ends, back, and visible brackets.
  at(rbox(W, 0.022, D, m.deskEdge, 0.003), 0, -0.011, -D / 2, carcass);
  at(rbox(W, 0.02, D - 0.03, m.deskEdge, 0.003), 0, 0.322, -D / 2 - 0.012, carcass);
  for (const s of [-1, 1]) at(rbox(0.017, 0.38, D, m.deskEdge, 0.003), s * (W / 2 + 0.0085), 0.155, -D / 2, carcass);
  at(rbox(W + 0.034, 0.36, 0.009, m.wall, 0.002), 0, 0.15, -D + 0.0045, carcass);
  for (const s of [-1, 1]) {
    const bx = s * (W / 2 - 0.09);
    at(rbox(0.012, 0.055, 0.03, m.steel, 0.002), bx, -0.05, -0.03, carcass);
    at(rbox(0.012, 0.012, D - 0.03, m.steel, 0.002), bx, -0.028, -D / 2, carcass);
  }

  // Under-shelf strip: the reason this corner is legible at night, and a fixture a person
  // with a workbench would actually have.
  const stripMat = new THREE.MeshStandardMaterial({ color: '#000000', emissive: '#ffeacc', emissiveIntensity: 2 });
  const strip = at(new THREE.Mesh(new THREE.BoxGeometry(W - 0.06, 0.004, 0.012), stripMat), 0, 0.306, -0.04, carcass);
  const shelfLight = new THREE.RectAreaLight('#ffeacc', 0, W - 0.06, D * 0.7);
  at(shelfLight, 0, 0.3, -D / 2, carcass);
  // Tilted forward so it also catches the book that has slid out of the row.
  shelfLight.lookAt(group.localToWorld(new THREE.Vector3(0, -0.4, 0.28)));

  // Props on the upper board: this shelf holds things as well as books.
  at(rbox(0.09, 0.052, 0.09, m.binWarm, 0.004), -W / 2 + 0.08, 0.358, -D / 2 - 0.012, carcass).rotation.y = 0.2;
  at(rbox(0.055, 0.075, 0.055, m.plasticBlack, 0.006), -W / 2 + 0.2, 0.37, -D / 2 - 0.02, carcass);
  const trophy = at(new THREE.Group(), W / 2 - 0.1, 0.332, -D / 2 - 0.01, carcass);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.03, 0.012, 16), m.aluminumDark)), 0, 0.006, 0, trophy);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.05, 10), m.gold)), 0, 0.037, 0, trophy);
  at(shadowed(new THREE.Mesh(new THREE.SphereGeometry(0.019, 14, 10), m.gold)), 0, 0.072, 0, trophy);

  // ---- Books -------------------------------------------------------------
  const nodes: BookNode[] = [];
  const bookDepth = 0.145;
  const run = books.reduce((sum, b) => sum + b.thickness, 0) + (books.length - 1) * SHELF.gap;
  let cursor = -W / 2 + 0.022;

  for (const def of books) {
    const geo = remapBookUVs(new THREE.BoxGeometry(def.thickness, def.height, bookDepth));
    const material = new THREE.MeshStandardMaterial({ map: bookAtlas(def), roughness: 0.78, metalness: 0 });
    const mesh = shadowed(new THREE.Mesh(geo, material));
    const holder = at(new THREE.Group(), cursor + def.thickness / 2, 0, 0, group);
    // Marked dynamic so the static merge leaves each book its own transform.
    holder.userData.dynamic = true;
    at(mesh, 0, def.height / 2, -0.006 - bookDepth / 2, holder);
    holder.rotation.z = def.lean ?? 0;
    nodes.push({
      def,
      mesh: holder as unknown as THREE.Mesh,
      material,
      homeX: holder.position.x,
      homeLean: def.lean ?? 0,
      out: 0,
      outVel: 0,
      shove: 0,
      base: material.color.clone(),
    });
    cursor += def.thickness + SHELF.gap;
  }
  // A bookend closing the row, and a leaning folder in the space left over.
  at(rbox(0.01, 0.1, 0.1, m.steel, 0.002), cursor + 0.01, 0.05, -0.06, group);
  const folder = at(rbox(0.13, 0.2, 0.014, m.cardboard, 0.003), cursor + 0.09, 0.098, -0.07, group);
  folder.rotation.set(0, Math.PI / 2, -0.22);

  // ---- Interaction affordances ------------------------------------------
  const anchor = group.localToWorld(new THREE.Vector3(run / 2 - W / 2, 0.11, 0.02));
  // On the book row, not the top board: the seated camera already looks down at the desk,
  // so a dot up at the carcass would sit far above the centre of the frame.
  const dotPos = group.localToWorld(new THREE.Vector3(0, 0.15, 0.01));
  const chevrons = [-1, 1].map((s) => {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: chevronTexture(s > 0), transparent: true, opacity: 0, depthWrite: false, sizeAttenuation: false, toneMapped: false }),
    );
    sprite.scale.setScalar(0.03);
    sprite.position.copy(group.localToWorld(new THREE.Vector3(s * (W / 2 + 0.05), 0.1, 0.04)));
    sprite.layers.set(OVERLAY_LAYER);
    sprite.renderOrder = 10;
    sprite.userData.ignoreRaycast = true;
    root.add(sprite);
    return sprite;
  });

  let active = false;
  let index = Math.floor(books.length / 2);
  let chevronOpacity = 0;
  const raycaster = new THREE.Raycaster();
  const _color = new THREE.Color();

  /** Underdamped enough to settle rather than stop dead — that settle is the whole feel. */
  const STIFFNESS = 150;
  const DAMPING = 2 * Math.sqrt(STIFFNESS) * 0.82;

  return {
    group,
    anchor,
    dotPos,
    chevrons,
    strip,
    /** Driven by the time of day, like every other emissive in the room. */
    setLevel(v: number) {
      shelfLight.intensity = v * 2.2;
      stripMat.emissiveIntensity = 0.35 + v * 0.5;
    },
    get active() {
      return active;
    },
    get index() {
      return index;
    },
    selected(): BookDef {
      return books[index];
    },
    /** Where the camera sits to browse: square on to the shelf, from inside the room. */
    focusTarget() {
      return {
        center: group.localToWorld(new THREE.Vector3(0, 0.12, -0.04)),
        distance: SHELF.focus.distance,
        yaw: Math.PI / 2,
        pitch: SHELF.focus.pitch,
        offset: SHELF.focus.offset,
      };
    },
    enter() {
      active = true;
    },
    exit() {
      active = false;
    },
    step(dir: number) {
      index = THREE.MathUtils.clamp(index + dir, 0, books.length - 1);
      return books[index];
    },
    select(i: number) {
      index = THREE.MathUtils.clamp(i, 0, books.length - 1);
      return books[index];
    },
    /** Outline follows the selection while browsing, the whole unit while merely hovered. */
    outlineTargets(): THREE.Object3D[] {
      return active ? [nodes[index].mesh] : [group];
    },
    /** Which book is under the pointer, or null. Only 12 objects, so this stays cheap. */
    pick(ndc: THREE.Vector2, camera: THREE.Camera): number | null {
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(nodes.map((n) => n.mesh), true);
      if (!hits.length) return null;
      let o: THREE.Object3D | null = hits[0].object;
      while (o && !nodes.some((n) => n.mesh === o)) o = o.parent;
      const found = nodes.findIndex((n) => n.mesh === o);
      return found < 0 ? null : found;
    },
    update(dt: number) {
      const step = Math.min(dt, 1 / 30);
      chevronOpacity = THREE.MathUtils.lerp(chevronOpacity, active ? 0.5 : 0, 1 - Math.exp(-6 * dt));
      for (const c of chevrons) c.material.opacity = chevronOpacity;

      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const isSelected = active && i === index;
        const target = isSelected ? 1 : 0;

        if (reducedMotion) {
          n.out = target;
          n.outVel = 0;
        } else {
          // Spring on the pull-out amount; everything else is derived from it.
          n.outVel += (STIFFNESS * (target - n.out) - DAMPING * n.outVel) * step;
          n.out += n.outVel * step;
        }

        // Neighbours slide aside, further away the closer they are to the selection.
        const delta = i - index;
        const near = active && delta !== 0 ? Math.max(0, 1 - Math.abs(delta) / 3) : 0;
        const wantShove = Math.sign(delta) * near * SHELF.select.spread;
        n.shove = reducedMotion ? wantShove : THREE.MathUtils.lerp(n.shove, wantShove, 1 - Math.exp(-9 * dt));

        const holder = n.mesh;
        holder.position.x = n.homeX + n.shove;
        holder.position.z = n.out * SHELF.select.out - (active && !isSelected ? near * SHELF.select.recede : 0);
        holder.position.y = n.out * SHELF.select.lift;
        holder.rotation.y = -n.out * SHELF.select.turn;
        // The lean straightens as a book comes out of the row.
        holder.rotation.z = n.homeLean * (1 - n.out);

        // Background books recede in tone as well as position, so the selection separates.
        const dim = active ? (isSelected ? 1 : 0.62) : 1;
        n.material.color.lerp(_color.copy(n.base).multiplyScalar(dim), 1 - Math.exp(-6 * dt));
      }
    },
  };
}
