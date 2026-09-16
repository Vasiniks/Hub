import * as THREE from 'three';
import type { Materials } from './materials';
import { SHELF } from './layout';
import { at, rbox, shadowed } from './build';
import { books, type BookDef } from '../data/books';
import { OVERLAY_LAYER } from './layers';
import type { Assets } from './assets';

/**
 * §15: the bookshelf is a real mechanism, not a prop.
 *
 * Browsing keeps the visitor in the room. The selected book physically slides out of the row,
 * lifts, and turns its cover toward the camera; its neighbours ease apart and settle back into
 * the shelf. Motion is a lightly underdamped spring per book, so the row has weight and the
 * selection lands with a settle rather than a snap.
 *
 * Each book is one mesh from `assets/processed/book.glb` (`blender/scripts/build_book.py`): a
 * hardcover with boards that overhang the page block, a rounded spine, hinge grooves, a set-back
 * page block with a concave fore-edge, and headbands. It is resized per book by `sliceBook`, and
 * its UVs already point into the regions of the per-book atlas below — cover, spine, page edges,
 * and swatches for the board edges and headband — so a book still costs one draw call.
 */

const COVER_U = [0.0, 0.6] as const;
const EDGE_U = [0.6, 0.62] as const;
const SPINE_U = [0.62, 0.74] as const;
const BAND_U = [0.745, 0.775] as const;
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

  // Swatches the model's board edges and headbands sample. Wider than the texels they need, so
  // mip levels at shelf distance do not bleed the neighbouring cover gradient into them.
  ctx.fillStyle = def.color;
  ctx.fillRect(EDGE_U[0] * S, 0, (EDGE_U[1] - EDGE_U[0]) * S, S);
  ctx.fillStyle = def.accent;
  ctx.fillRect(BAND_U[0] * S, 0, (BAND_U[1] - BAND_U[0]) * S, S);

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
  // The book model's UVs come from glTF, where v runs top-down; three's canvas default assumes
  // bottom-up, which printed every cover and spine upside down.
  tex.flipY = false;
  return tex;
}

interface BookMeta {
  thickness: number;
  height: number;
  depth: number;
  sliceX: number;
  sliceY: number;
}

/**
 * Resize the canonical book to one book's thickness and height without stretching its
 * construction. A 3D nine-slice: vertices within `sliceX` of either cover and `sliceY` of the
 * top or bottom keep their distance to that face, and only the interior stretches — so the
 * boards, squares, hinge grooves and headbands stay their real size on every book. Scaling the
 * whole mesh would give the thinnest book 7 mm boards' worth of 0.5 mm card.
 */
function sliceBook(source: THREE.BufferGeometry, meta: BookMeta, thickness: number, height: number) {
  const geo = source.clone();
  const pos = geo.getAttribute('position') as THREE.BufferAttribute;
  const hx = meta.thickness / 2;
  const nx = thickness / 2;
  const sx = (nx - meta.sliceX) / (hx - meta.sliceX);
  const sy = (height - 2 * meta.sliceY) / (meta.height - 2 * meta.sliceY);
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const ax = Math.abs(x);
    pos.setX(i, ax > hx - meta.sliceX ? Math.sign(x) * (ax + nx - hx) : x * sx);
    if (y > meta.height - meta.sliceY) pos.setY(i, y + height - meta.height);
    else if (y > meta.sliceY) pos.setY(i, meta.sliceY + (y - meta.sliceY) * sy);
  }
  pos.needsUpdate = true;
  geo.computeVertexNormals();
  geo.computeBoundingBox();
  geo.computeBoundingSphere();
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
  /** Spring state for the sideways shove from the selected book. */
  shove: number;
  shoveVel: number;
  base: THREE.Color;
}

export type Bookshelf = ReturnType<typeof createBookshelf>;

export function createBookshelf(root: THREE.Group, m: Materials, reducedMotion: boolean, assets: Assets) {
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
  const bookMeta = assets.meta('book') as unknown as BookMeta;
  const bookSource = (assets.part(assets.instance('book'), 'book') as THREE.Mesh).geometry;
  const bookDepth = bookMeta.depth;
  const run = books.reduce((sum, b) => sum + b.thickness, 0) + (books.length - 1) * SHELF.gap;
  const rowStart = -W / 2 + SHELF.rowInset;
  let cursor = rowStart;

  for (const def of books) {
    const geo = sliceBook(bookSource, bookMeta, def.thickness, def.height);
    const material = new THREE.MeshStandardMaterial({ map: bookAtlas(def), roughness: 0.78, metalness: 0 });
    const mesh = shadowed(new THREE.Mesh(geo, material));
    const holder = at(new THREE.Group(), cursor + def.thickness / 2, 0, 0, group);
    // Marked dynamic so the static merge leaves each book its own transform.
    holder.userData.dynamic = true;
    at(mesh, 0, 0, -0.006 - bookDepth / 2, holder);
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
      shoveVel: 0,
      base: material.color.clone(),
    });
    cursor += def.thickness + SHELF.gap;
  }
  // A bookend closing the row — it moves with the books when the row opens — and a leaning
  // folder out by the side panel, clear of anywhere the row can reach.
  const bookend = at(rbox(0.01, 0.1, 0.1, m.steel, 0.002), cursor + 0.01, 0.05, -0.06, group);
  bookend.userData.dynamic = true;
  const bookendHome = bookend.position.x;
  let bookendShove = 0;
  let bookendVel = 0;
  const folder = at(rbox(0.13, 0.2, 0.014, m.cardboard, 0.003), W / 2 - 0.075, 0.098, -0.07, group);
  folder.rotation.set(0, Math.PI / 2, -0.22);

  /**
   * The gap a presented book needs. Turned about its spine, its body swings across the row by
   * depth × sin(turn), scaled with it, plus a little air so the cover never grazes a spine.
   */
  const presentedSwing = bookDepth * Math.abs(Math.sin(SHELF.select.turn)) * SHELF.select.scale + SHELF.select.clearance;
  const openLeft = Math.min(SHELF.select.openLeft, SHELF.rowInset - 0.01);
  const openRight = presentedSwing - openLeft - SHELF.gap;

  // ---- Interaction affordances ------------------------------------------
  const anchor = group.localToWorld(new THREE.Vector3(rowStart + run / 2, 0.11, 0.02));
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
  /** The row is shoved aside a little faster than the book comes out, so it reads as cause. */
  const SHOVE_STIFFNESS = 210;
  const SHOVE_DAMPING = 2 * Math.sqrt(SHOVE_STIFFNESS) * 0.7;

  /** True until the current selection has substantially arrived; gates the next step. */
  let settled = true;

  /**
   * A step knocks the neighbours rather than merely retargeting them: the books nearest the
   * new selection get an impulse away from it, which is what makes the row feel like objects
   * being pushed apart instead of values being interpolated.
   */
  function kick(from: number, to: number) {
    settled = false;
    for (let i = 0; i < nodes.length; i++) {
      const d = i - to;
      if (d === 0) continue;
      const near = Math.max(0, 1 - Math.abs(d) / 4.5);
      if (near <= 0) continue;
      nodes[i].shoveVel += Math.sign(d) * near * 0.55;
    }
    // The book being put back gets a small nudge home.
    if (from !== to && nodes[from]) nodes[from].outVel -= 0.6;
  }

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
    /** True once the current transition has mostly arrived. */
    get settled() {
      return settled;
    },
    step(dir: number) {
      const from = index;
      index = THREE.MathUtils.clamp(index + dir, 0, books.length - 1);
      if (index !== from) kick(from, index);
      return books[index];
    },
    select(i: number) {
      const from = index;
      index = THREE.MathUtils.clamp(i, 0, books.length - 1);
      if (index !== from) kick(from, index);
      return books[index];
    },
    /** Debug: each book's footprint on the shelf plane, in shelf-local metres. */
    footprints() {
      group.updateMatrixWorld(true);
      const inv = new THREE.Matrix4().copy(group.matrixWorld).invert();
      const box = new THREE.Box3();
      return {
        selected: index,
        books: nodes.map((n) => {
          const mesh = n.mesh.children[0] as THREE.Mesh;
          mesh.geometry.computeBoundingBox();
          box.copy(mesh.geometry.boundingBox!).applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, mesh.matrixWorld));
          return { x0: box.min.x, x1: box.max.x, z0: box.min.z, z1: box.max.z, shove: n.shove };
        }),
      };
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

      let arrived = true;
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const isSelected = active && i === index;
        const target = isSelected ? 1 : 0;

        const delta = i - index;
        const near = active && delta !== 0 ? Math.max(0, 1 - Math.abs(delta) / 4.5) : 0;
        // The row parts around the selection: everything from the selection leftward gives a
        // little, everything to its right gives the rest of the swing.
        const wantShove = !active ? 0 : delta > 0 ? openRight : -openLeft;

        if (reducedMotion) {
          n.out = target;
          n.outVel = 0;
          n.shove = wantShove;
          n.shoveVel = 0;
        } else {
          // Spring on the pull-out amount; everything else is derived from it.
          n.outVel += (STIFFNESS * (target - n.out) - DAMPING * n.outVel) * step;
          n.out += n.outVel * step;
          n.shoveVel += (SHOVE_STIFFNESS * (wantShove - n.shove) - SHOVE_DAMPING * n.shoveVel) * step;
          n.shove += n.shoveVel * step;
        }
        // Loose on purpose: the gate exists to stop steps stacking mid-flight, not to make
        // the visitor wait out the settle. It opens around halfway through the travel.
        if (Math.abs(n.out - target) > 0.45) arrived = false;

        const holder = n.mesh;
        const ease = n.out;
        holder.position.x = n.homeX + n.shove;
        holder.position.z = ease * SHELF.select.out - (active && !isSelected ? near * SHELF.select.recede : 0);
        holder.position.y = ease * SHELF.select.lift;
        holder.rotation.y = -ease * SHELF.select.turn;
        // The lean straightens as a book comes out, and it tips toward the camera as it
        // presents — the small extra rotation is what stops it reading as a sliding panel.
        holder.rotation.z = n.homeLean * (1 - ease) - ease * SHELF.select.tilt;
        holder.scale.setScalar(1 + ease * (SHELF.select.scale - 1));

        // Background books recede in tone as well as position, so the selection separates.
        const dim = active ? (isSelected ? 1 : 0.62) : 1;
        n.material.color.lerp(_color.copy(n.base).multiplyScalar(dim), 1 - Math.exp(-6 * dt));
      }
      // The bookend belongs to the right-hand side of the row, whichever book is out.
      const bookendWant = active ? openRight : 0;
      if (reducedMotion) bookendShove = bookendWant;
      else {
        bookendVel += (SHOVE_STIFFNESS * (bookendWant - bookendShove) - SHOVE_DAMPING * bookendVel) * step;
        bookendShove += bookendVel * step;
      }
      bookend.position.x = bookendHome + bookendShove;
      if (arrived) settled = true;
    },
  };
}
