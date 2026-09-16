import * as THREE from 'three';
import type { Materials } from './materials';
import type { Assets } from './assets';
import { DESK, DESKTOP, LAMP } from './layout';
import { at, rbox, rboxGeo, shadowed, rand } from './build';

/**
 * The desk and everything standing on it.
 *
 * Composition runs left to right (§32): lamp and medals and the speedcube on the left, the
 * monitor / MacBook / keyboard column through the centre, working electronics on the right.
 * Geometry stays low-poly; what carries the quality is bevelled edges, real thickness and a
 * different material response per object.
 */

export interface DeskRefs {
  /** The lit panel of the main monitor — the Lorenz attractor draws here. */
  screen: THREE.Mesh;
  screenCenter: THREE.Vector3;
  screenSize: THREE.Vector2;
  lampHead: THREE.Object3D;
  lampSocket: THREE.Object3D;
  lampTarget: THREE.Object3D;
  lampDisc: THREE.Mesh;
  /** Where the lamp beam lands; the dust volume is centred between head and pool. */
  lampPool: THREE.Vector3;
  leds: THREE.Mesh[];
}

/** Work surface: a thick white slab on a slim steel frame, not a box on four sticks. */
function buildDesk(root: THREE.Group, m: Materials) {
  const { width: W, depth: D, top: Y, thickness: T, centerX: CX, centerZ: CZ, legInset } = DESK;

  // Top: a 4 mm bevel is what catches the window highlight along the front edge.
  at(rbox(W, T, D, m.deskWhite, 0.005), CX, Y - T / 2, CZ, root);
  // Underside rail: gives the slab visible thickness from a seated eyeline.
  at(rbox(W - 0.04, 0.018, D - 0.05, m.deskEdge, 0.003), CX, Y - T - 0.008, CZ, root);

  for (const s of [-1, 1]) {
    const x = CX + s * (W / 2 - legInset);
    const leg = at(new THREE.Group(), x, 0, CZ, root);
    // Inverted-U frame: foot, two uprights, top rail.
    at(rbox(0.055, 0.022, D - 0.1, m.steel, 0.008), 0, 0.011, 0, leg);
    at(rbox(0.05, 0.016, 0.07, m.rubber, 0.004), 0, 0.03, -(D / 2 - 0.09), leg);
    at(rbox(0.05, 0.016, 0.07, m.rubber, 0.004), 0, 0.03, D / 2 - 0.09, leg);
    at(rbox(0.038, Y - T - 0.03, 0.05, m.steel, 0.006), 0, (Y - T) / 2, -0.04, leg);
    at(rbox(0.048, 0.022, D - 0.14, m.steel, 0.006), 0, Y - T - 0.02, 0, leg);
  }
  // Rear cable tray, and the bundle that drops off it.
  at(rbox(W - 0.5, 0.05, 0.026, m.steel, 0.005), CX, Y - 0.12, CZ - D / 2 + 0.05, root);
  const bundle = new THREE.CatmullRomCurve3([
    new THREE.Vector3(CX + 0.2, Y - 0.1, CZ - D / 2 + 0.05),
    new THREE.Vector3(CX + 0.38, Y - 0.26, CZ - D / 2 + 0.02),
    new THREE.Vector3(CX + 0.5, Y - 0.52, CZ - D / 2 + 0.06),
    new THREE.Vector3(CX + 0.62, 0.012, CZ - D / 2 + 0.16),
  ]);
  root.add(shadowed(new THREE.Mesh(new THREE.TubeGeometry(bundle, 28, 0.009, 6), m.rubber)));
}

/**
 * §13: the monitor, set far enough back on the wide desk to be an anchor rather than a wall.
 *
 * Geometry from `assets/processed/monitor.glb` (`blender/scripts/build_monitor.py`). The bezel
 * is the part that needed Blender: the screen sits in a well cut into the housing with a
 * boolean, so there is a real recessed edge that catches light and throws a thin shadow onto
 * the panel, instead of a dark rectangle laid on a slab.
 */
function buildMonitor(root: THREE.Group, m: Materials, assets: Assets): Pick<DeskRefs, 'screen' | 'screenCenter' | 'screenSize'> {
  const { x, z, rotationY } = DESKTOP.monitor;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;

  const model = assets.instance('monitor');
  g.add(model);
  assets.retint(model, { mon_housing: m.plasticBlack, mon_metal: m.aluminumDark, mon_led: m.ledGreen });

  const meta = assets.meta('monitor');
  const sw = (meta.screenWidth as number) ?? 0.596;
  const sh = (meta.screenHeight as number) ?? 0.341;

  // The imported quad is used only to locate the panel; its own surface parameterisation
  // renders the attractor mirrored. A three.js plane has UVs this code controls, so the
  // screen gets one of those, placed exactly where the asset's quad sits.
  g.updateMatrixWorld(true);
  const seat = assets.partCenter(model, 'monitor_screen');
  assets.part(model, 'monitor_screen')?.removeFromParent();
  const screenMat = new THREE.MeshStandardMaterial({
    color: '#030405',
    roughness: 0.34,
    metalness: 0,
    envMapIntensity: 0.3,
    emissive: '#ffffff',
    emissiveIntensity: 1,
  });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(sw, sh), screenMat);
  screen.castShadow = false;
  screen.receiveShadow = false;
  g.add(screen);
  g.worldToLocal(screen.position.copy(seat));
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(sw + 0.004, sh + 0.004), m.glass);
  glass.position.copy(screen.position);
  glass.position.z += 0.0012;
  glass.renderOrder = 3;
  glass.castShadow = glass.receiveShadow = false;
  glass.userData.noMerge = true;
  glass.userData.ignoreRaycast = true;
  g.add(glass);

  g.updateMatrixWorld(true);
  return { screen, screenCenter: screen.getWorldPosition(new THREE.Vector3()), screenSize: new THREE.Vector2(sw, sh) };
}
/**
 * §10: the MacBook, closed on an inclined riser, sloping up and away from the visitor.
 *
 * Geometry from `assets/processed/macbook.glb` (`blender/scripts/build_macbook.py`). The body
 * is one solid with a bevel all round, the port cutouts and the front notch are boolean
 * recesses rather than dark boxes laid on the surface, and the rear edge is a real rounded
 * hinge. Body and riser are built in the deck's own frame and tilted together, so the arms
 * cannot pass through the body at any angle.
 */
function buildMacBook(root: THREE.Group, m: Materials, assets: Assets) {
  const { x, z, rotationY } = DESKTOP.macbook;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  const model = assets.instance('macbook');
  assets.retint(model, { mb_alu: m.aluminum, mb_dark: m.aluminumDark, mb_rubber: m.rubber });
  g.add(model);

  // Charge cable leaving the left flank and dropping behind the desk.
  g.updateMatrixWorld(true);
  const port = g.localToWorld(new THREE.Vector3(-0.152, 0.075, 0.0));
  const cable = new THREE.CatmullRomCurve3([
    port,
    port.clone().add(new THREE.Vector3(-0.09, -0.028, -0.05)),
    port.clone().add(new THREE.Vector3(-0.13, -0.05, -0.16)),
    port.clone().add(new THREE.Vector3(-0.1, -0.058, -0.28)),
  ]);
  root.add(shadowed(new THREE.Mesh(new THREE.TubeGeometry(cable, 26, 0.0034, 6), m.plasticWhite)));
  return g;
}

// TKL, 87 keys. Each row is a list of key widths in units; a negative entry is a gap.
// prettier-ignore
const TKL_ROWS: number[][] = [
  [1, -1, 1, 1, 1, 1, -0.5, 1, 1, 1, 1, -0.5, 1, 1, 1, 1, -0.25, 1, 1, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, -0.25, 1, 1, 1],
  [1.5, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1.5, -0.25, 1, 1, 1],
  [1.75, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.25],
  [2.25, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.75, -1.25, 1],
  [1.25, 1.25, 1.25, 6.25, 1.25, 1.25, 1.25, 1.25, -0.25, 1, 1, 1],
];

/**
 * A sculpted keycap: tapered toward the top with a shallow dish, not a flat slab. The taper is
 * what catches a highlight on every cap edge and makes a field of 87 keys read as keys.
 */
function keycapGeometry(side: number, h: number) {
  const geo = rboxGeo(side, h, side, side * 0.1, 3);
  const pos = geo.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i);
    if (y <= 0) continue;
    const k = y / (h / 2);
    const taper = 1 - 0.17 * k;
    const x = pos.getX(i) * taper;
    const z = pos.getZ(i) * taper;
    pos.setX(i, x);
    pos.setZ(i, z);
    if (k > 0.8) {
      // Shallow spherical dish across the top face.
      const r = Math.min(1, Math.hypot(x, z) / (side / 2));
      pos.setY(i, y - h * 0.11 * (1 - r * r));
    }
  }
  pos.needsUpdate = true;
  geo.computeVertexNormals();
  return geo;
}

/** §5: white, and convincingly TKL in silhouette. Legends are deliberately not modelled. */
function buildKeyboard(root: THREE.Group, m: Materials) {
  const { x, z, rotationY } = DESKTOP.keyboard;
  const U = 0.019;
  const GAP = 0.0013;
  const rows = TKL_ROWS.length;
  const width = 18.25 * U;
  const depth = rows * U + 0.012;

  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  // Case: a low white tray with a 5° typing incline and a darker base plate showing at the seam.
  const caseG = at(new THREE.Group(), 0, 0, 0, g);
  caseG.rotation.x = -0.075;
  at(rbox(width + 0.016, 0.019, depth + 0.012, m.plasticWhite, 0.0035), 0, 0.0115, 0, caseG);
  at(rbox(width + 0.012, 0.006, depth + 0.008, m.aluminumDark, 0.002), 0, 0.0035, 0, caseG);
  at(rbox(width - 0.004, 0.003, depth - 0.004, m.keycapAccent, 0.001), 0, 0.0208, 0, caseG);
  for (const s of [-1, 1]) at(rbox(0.02, 0.006, 0.012, m.rubber, 0.002), s * (width / 2 - 0.02), 0.002, depth / 2 - 0.02, caseG);

  // Keycaps: two instanced meshes (alphas, modifiers) — the whole 87-key field is two draw calls.
  const capGeo = keycapGeometry(U - GAP, 0.0098);
  const counts = { alpha: 0, mod: 0 };
  const place: { accent: boolean; x: number; z: number; w: number; y: number; tilt: number; skew: number }[] = [];
  const jitter = rand(5150);
  // Row sculpting: the home row sits lowest and flattest, the outer rows tilt toward the hands.
  const SCULPT = [
    { lift: 0.0018, tilt: 0.1 },
    { lift: 0.001, tilt: 0.065 },
    { lift: 0.0004, tilt: 0.028 },
    { lift: 0, tilt: 0 },
    { lift: 0.0005, tilt: -0.035 },
    { lift: 0.0013, tilt: -0.075 },
  ];
  for (let r = 0; r < rows; r++) {
    let cursor = -width / 2;
    const zRow = -depth / 2 + 0.006 + (r + 0.5) * U;
    for (const w of TKL_ROWS[r]) {
      if (w < 0) {
        cursor += -w * U;
        continue;
      }
      const accent = w !== 1 || r === 0;
      place.push({
        accent,
        x: cursor + (w * U) / 2,
        z: zRow,
        w,
        // A fraction of a millimetre of seat variation: no two caps sit perfectly level.
        y: 0.0255 + SCULPT[r].lift + (jitter() - 0.5) * 0.00028,
        tilt: SCULPT[r].tilt,
        // Wide keys are held by stabilisers, so they cannot sit as crooked as a 1u cap.
        skew: ((jitter() - 0.5) * 0.012) / w,
      });
      accent ? counts.mod++ : counts.alpha++;
      cursor += w * U;
    }
  }
  const alphas = new THREE.InstancedMesh(capGeo, m.keycap, counts.alpha);
  const mods = new THREE.InstancedMesh(capGeo, m.keycapAccent, counts.mod);
  const dummy = new THREE.Object3D();
  let ai = 0;
  let mi = 0;
  for (const p of place) {
    dummy.position.set(p.x, p.y, p.z);
    dummy.rotation.set(p.tilt, p.skew, 0);
    dummy.scale.set((p.w * U - GAP) / (U - GAP), 1, 1);
    dummy.updateMatrix();
    if (p.accent) mods.setMatrixAt(mi++, dummy.matrix);
    else alphas.setMatrixAt(ai++, dummy.matrix);
  }
  for (const im of [alphas, mods]) {
    im.castShadow = im.receiveShadow = true;
    caseG.add(im);
  }

  // Stabiliser bars under the wide keys — the detail that says this is a mechanical board.
  const stabRow = (w: number, r: number, cx: number) => {
    const zRow = -depth / 2 + 0.006 + (r + 0.5) * U;
    for (const side of [-1, 1]) {
      at(rbox(0.0035, 0.0045, 0.009, m.aluminumDark, 0.001), cx + side * (w * U) / 2 * 0.62, 0.0224, zRow, caseG);
    }
  };
  stabRow(2, 1, -width / 2 + 13 * U + U);
  stabRow(1.5, 2, -width / 2 + 13.5 * U - 0.75 * U);
  stabRow(2.25, 3, -width / 2 + 12.75 * U + 1.125 * U);
  stabRow(2.75, 4, -width / 2 + 12.25 * U + 1.375 * U);
  stabRow(6.25, 5, -width / 2 + 3.75 * U + 3.125 * U);

  // Indicator LEDs above the nav cluster.
  const led = at(new THREE.Mesh(new THREE.CircleGeometry(0.0015, 8), m.ledGreen), width / 2 - 0.028, 0.0212, -depth / 2 + 0.002, caseG);
  led.rotation.x = -Math.PI / 2;
  return [led];
}

/**
 * §8: the mouse.
 *
 * Geometry from `assets/processed/mouse.glb` (`blender/scripts/build_mouse.py`). The shape is
 * a dome over a tapered footprint — nose low and narrow, palm rest tallest about two thirds
 * back — but what makes it read is the part that needs Blender: the click split and the palm
 * seam are boolean grooves cut into the shell, so they are real recesses that catch a shadow
 * rather than strips laid on top of it.
 */
function buildMouse(root: THREE.Group, m: Materials, assets: Assets) {
  const { x, z, rotationY } = DESKTOP.mouse;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  const model = assets.instance('mouse');
  assets.retint(model, {
    mouse_shell_mat: m.plasticWhite,
    mouse_grey_mat: m.plasticGrey,
    mouse_dark_mat: m.plasticBlack,
  });
  g.add(model);
  return g;
}
/**
 * §12: the lamp.
 *
 * Geometry comes from `assets/processed/lamp.glb`, built by `blender/scripts/build_lamp.py`
 * from a CC0 Poly Haven spring arm whose cone shade and desk clamp are replaced by a flat
 * circular head and a weighted base. A spring arm with real knuckles and tension rods is not
 * worth approximating with cylinders, which is the whole reason the pipeline exists.
 *
 * The medals stay in code: they hang off the arm and are simple enough that this is the right
 * place for them.
 */
function buildLamp(root: THREE.Group, m: Materials, assets: Assets): Omit<DeskRefs, 'screen' | 'screenCenter' | 'screenSize' | 'leds'> {
  const { x, z } = DESKTOP.lamp;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = LAMP.yaw;

  const model = assets.instance('lamp');
  model.scale.setScalar(LAMP.scale);
  g.add(model);

  // Re-author the imported materials against this room's palette, so the lamp answers this
  // room's lighting instead of arriving with its own look.
  const discMat = new THREE.MeshStandardMaterial({
    color: '#0a0a0a',
    emissive: '#ffd6a0',
    emissiveIntensity: 0.1,
    roughness: 0.55,
  });
  assets.retint(model, { lamp_metal: m.aluminum, lamp_dark: m.aluminumDark, lamp_diffuser: discMat });
  const disc = (assets.part(model, 'lamp_glass') ?? assets.part(model, 'lamp_head'))!;

  // Socket and aim come from the build's sidecar, so the light sits at the real head rather
  // than at a position guessed at runtime.
  const meta = assets.meta('lamp');
  const socketLocal = new THREE.Vector3(...(meta.socket ?? [0, 0.5, 0])).multiplyScalar(LAMP.scale);
  const beamLocal = new THREE.Vector3(...(meta.beam ?? [0, -1, 0])).normalize();
  const head = at(new THREE.Object3D(), socketLocal.x, socketLocal.y, socketLocal.z, g);
  const socket = at(new THREE.Object3D(), 0, 0, 0, head);
  const target = at(new THREE.Object3D(), beamLocal.x, beamLocal.y, beamLocal.z, head);

  g.updateMatrixWorld(true);
  const headWorld = head.getWorldPosition(new THREE.Vector3());
  const beamWorld = target.getWorldPosition(new THREE.Vector3()).sub(headWorld).normalize();
  const drop = (DESK.top - headWorld.y) / Math.min(-0.05, beamWorld.y);
  const pool = headWorld.clone().addScaledVector(beamWorld, drop);

  buildMedals(g, m, model);
  return { lampHead: head, lampSocket: socket, lampTarget: target, lampDisc: disc, lampPool: pool };
}

/**
 * §12: medals hung over the lamp's arm. Lengths, lean and facing all differ, so they read as
 * things that were dropped there rather than an arrangement.
 */
function buildMedals(lamp: THREE.Group, m: Materials, model: THREE.Object3D) {
  const metals = [m.gold, m.silver, m.bronze, m.gold];
  const ribbons = [m.ribbonBlue, m.ribbonRed, m.ribbonGreen, m.ribbonRed];
  const r = rand(4211);
  const from = new THREE.Vector3(...LAMP.medalFrom).multiplyScalar(LAMP.scale);
  const to = new THREE.Vector3(...LAMP.medalTo).multiplyScalar(LAMP.scale);
  void model;
  const specs = [
    { t: 0.0, drop: 0.2, lean: -0.24, turn: 0.35 },
    { t: 0.34, drop: 0.155, lean: -0.1, turn: 1.32 },
    { t: 0.62, drop: 0.235, lean: -0.3, turn: -0.42 },
    { t: 1.0, drop: 0.13, lean: -0.05, turn: 0.78 },
  ];
  specs.forEach((s, i) => {
    const hang = from.clone().lerp(to, s.t);
    const g = at(new THREE.Group(), hang.x, hang.y, hang.z, lamp);
    g.rotation.z = s.lean;
    g.rotation.y = s.turn;

    const bottom = -s.drop;
    for (const side of [-1, 1]) {
      const strap = at(rbox(0.009, s.drop, 0.0016, ribbons[i], 0.0006), side * 0.011, bottom / 2, 0, g);
      strap.rotation.z = side * 0.05 + (r() - 0.5) * 0.04;
    }
    at(rbox(0.026, 0.006, 0.0022, ribbons[i], 0.0008), 0, bottom + 0.004, 0, g);
    const ring = at(shadowed(new THREE.Mesh(new THREE.TorusGeometry(0.006, 0.0016, 6, 12), metals[i])), 0, bottom - 0.002, 0, g);
    ring.rotation.y = Math.PI / 2;
    const disc = at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.023, 0.023, 0.0035, 22), metals[i])), 0, bottom - 0.028, 0, g);
    disc.rotation.x = Math.PI / 2;
    disc.rotation.z = (r() - 0.5) * 0.5;
    at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 0.0042, 22), metals[i])), 0, bottom - 0.028, 0.0004, g).rotation.x =
      Math.PI / 2;
  });
}

/**
 * §14/§18: a 56mm stickerless speedcube, caught mid-solve with one layer turned.
 *
 * What makes a GAN read as a GAN rather than as a Rubik's cube is the stickerless
 * construction — colour moulded into the plastic, so it wraps the rounded chamfer of every
 * tile instead of stopping at a sticker's edge — plus a frosted matte finish, generous corner
 * radii, wide piece gaps showing dark interior plastic, and a recessed cap on each centre.
 * Deliberately no logo: that is trademarked, and the form reads without it.
 */
function buildCube(root: THREE.Group) {
  const { x, z, rotationY, size } = DESKTOP.cube;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  g.rotation.x = 0.015;

  const cubie = size / 3;
  const gap = 0.0012;
  const body = new THREE.MeshStandardMaterial({ color: '#17181b', roughness: 0.62, metalness: 0 });
  // Frosted, slightly desaturated: moulded plastic under a matte finish, not gloss vinyl.
  const frosted = (color: string) => new THREE.MeshStandardMaterial({ color, roughness: 0.58, metalness: 0, envMapIntensity: 0.45 });
  const faces = {
    U: frosted('#f4f5f2'),
    D: frosted('#f8d945'),
    F: frosted('#2bc264'),
    B: frosted('#2f75da'),
    L: frosted('#ff8f33'),
    R: frosted('#e0323c'),
  };
  // Colour runs nearly edge to edge on each piece, the way moulded plastic does — a small
  // tile floating on a dark body reads as a stickered cube, which is the wrong object.
  const tileSide = cubie * 0.935;
  const tileGeo = rboxGeo(tileSide, 0.0019, tileSide, cubie * 0.13, 1);
  const capGeo = new THREE.TorusGeometry(cubie * 0.25, 0.00055, 6, 20);
  const cubieGeo = rboxGeo(cubie - gap, cubie - gap, cubie - gap, cubie * 0.17, 1);

  // The top layer is rotated: the cube is mid-solve, not sitting factory-fresh.
  const top = at(new THREE.Group(), 0, 0, 0, g);
  top.rotation.y = 0.52;

  for (let ix = -1; ix <= 1; ix++) {
    for (let iy = -1; iy <= 1; iy++) {
      for (let iz = -1; iz <= 1; iz++) {
        if (ix === 0 && iy === 0 && iz === 0) continue;
        const parent = iy === 1 ? top : g;
        const c = at(shadowed(new THREE.Mesh(cubieGeo, body)), ix * cubie, size / 2 + iy * cubie, iz * cubie, parent);
        const isCentre = Math.abs(ix) + Math.abs(iy) + Math.abs(iz) === 1;
        const put = (mat: THREE.MeshStandardMaterial, ox: number, oy: number, oz: number, rx: number, rz: number) => {
          const tile = at(new THREE.Mesh(tileGeo, mat), ox, oy, oz, c);
          tile.rotation.set(rx, 0, rz);
          tile.castShadow = false;
          tile.receiveShadow = true;
          // Centres carry the shallow cap ring every GAN centre has. A filled dark disc reads
          // as a hole; a ring groove in the piece's own colour reads as moulding.
          if (isCentre) {
            const cap = at(new THREE.Mesh(capGeo, mat), 0, 0.00075, 0, tile);
            cap.rotation.x = Math.PI / 2;
            cap.castShadow = false;
            cap.receiveShadow = true;
          }
        };
        // Tiles sit a hair proud of the piece so the gap between them reads as a real seam.
        const h = (cubie - gap) / 2 - 0.0002;
        if (iy === 1) put(faces.U, 0, h, 0, 0, 0);
        if (iy === -1) put(faces.D, 0, -h, 0, Math.PI, 0);
        if (iz === 1) put(faces.F, 0, 0, h, Math.PI / 2, 0);
        if (iz === -1) put(faces.B, 0, 0, -h, -Math.PI / 2, 0);
        if (ix === -1) put(faces.L, -h, 0, 0, 0, Math.PI / 2);
        if (ix === 1) put(faces.R, h, 0, 0, 0, -Math.PI / 2);
      }
    }
  }
}

/** A mug, left-front: the one object on the desk with no technical purpose. */
function buildMug(root: THREE.Group, m: Materials) {
  const { x, z, rotationY } = DESKTOP.mug;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  const wall = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.042, 0.038, 0.098, 26, 1, true), m.plasticWhite));
  const wallMat = (wall.material as THREE.MeshStandardMaterial).clone();
  wallMat.side = THREE.DoubleSide;
  wall.material = wallMat;
  at(wall, 0, 0.049, 0, g);
  at(shadowed(new THREE.Mesh(new THREE.CircleGeometry(0.038, 26), m.plasticWhite)), 0, 0.004, 0, g).rotation.x = -Math.PI / 2;
  // Coffee: a dark disc a little below the rim.
  const brew = at(new THREE.Mesh(new THREE.CircleGeometry(0.0395, 26), new THREE.MeshStandardMaterial({ color: '#241509', roughness: 0.22 })), 0, 0.072, 0, g);
  brew.rotation.x = -Math.PI / 2;
  const handle = shadowed(new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.0058, 8, 18, Math.PI * 1.1), m.plasticWhite));
  handle.rotation.z = -Math.PI / 2 - 0.15;
  at(handle, 0.044, 0.05, 0, g);
}

/**
 * §12/§13: the working half of the desk. Boards lying where they were put down, a stack of
 * parts bins, a compartment tray, loose hardware. Art-directed mess: dense enough to say
 * someone works here, sparse enough that silhouettes stay readable.
 */
function buildWorkClutter(root: THREE.Group, m: Materials) {
  const Y = DESK.top;
  const leds: THREE.Mesh[] = [];
  const r = rand(90210);

  // Compartment tray, back right.
  const tray = at(new THREE.Group(), 0.86, Y, -0.97, root);
  tray.rotation.y = -0.16;
  const T = 0.0035;
  at(rbox(0.19, T, 0.125, m.binBlue, 0.002), 0, T / 2, 0, tray);
  for (const s of [-1, 1]) {
    at(rbox(0.19, 0.042, T, m.binBlue, 0.002), 0, 0.021, s * 0.0625, tray);
    at(rbox(T, 0.042, 0.125, m.binBlue, 0.002), s * 0.095, 0.021, 0, tray);
  }
  for (const dx of [-0.063, 0, 0.063]) at(rbox(T, 0.034, 0.12, m.binBlue, 0.001), dx, 0.017, 0, tray);
  at(rbox(0.19, T, 0.06, m.binBlue, 0.001), 0, 0.017, -0.032, tray);
  // Loose hardware in two compartments.
  for (let i = 0; i < 14; i++) {
    const cell = Math.floor(r() * 4) - 1.5;
    at(
      shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.0022, 0.0022, 0.009, 6), i % 3 ? m.steel : m.copper)),
      cell * 0.063 + (r() - 0.5) * 0.04,
      0.008,
      (r() - 0.5) * 0.1,
      tray,
    ).rotation.set(Math.PI / 2, r() * 3, r() * 3);
  }

  // Two stacked bins, slightly out of square.
  const binStack = at(new THREE.Group(), 0.6, Y, -1.03, root);
  binStack.rotation.y = 0.1;
  const bin = (parent: THREE.Object3D, w: number, h: number, d: number, y: number, mat: THREE.Material, yaw: number) => {
    const b = at(new THREE.Group(), 0, y, 0, parent);
    b.rotation.y = yaw;
    const t = 0.0035;
    at(rbox(w, t, d, mat, 0.002), 0, t / 2, 0, b);
    for (const s of [-1, 1]) {
      // Walls flare out slightly, the way moulded bins do.
      const side = at(rbox(w, h, t, mat, 0.002), 0, h / 2, s * (d / 2 - t / 2), b);
      side.rotation.x = s * -0.05;
      const end = at(rbox(t, h, d, mat, 0.002), s * (w / 2 - t / 2), h / 2, 0, b);
      end.rotation.z = s * 0.05;
    }
    at(rbox(w + 0.006, 0.004, d + 0.006, mat, 0.002), 0, h, 0, b);
    return b;
  };
  bin(binStack, 0.15, 0.058, 0.1, 0, m.binWarm, 0);
  bin(binStack, 0.14, 0.05, 0.095, 0.062, m.binBlue, 0.14);

  // Boards lying around: one flat, one leaning, one half-off a bin.
  const board = (x: number, y: number, z: number, w: number, d: number, mat: THREE.Material, rot: [number, number, number]) => {
    const b = at(shadowed(new THREE.Mesh(rboxGeo(w, 0.0016, d, 0.001, 1), mat)), x, y, z, root);
    b.rotation.set(...rot);
    // Header pins along one edge, and a couple of chips.
    const pins = new THREE.InstancedMesh(new THREE.BoxGeometry(0.0014, 0.006, 0.0014), m.aluminum, 20);
    const dm = new THREE.Object3D();
    for (let i = 0; i < 20; i++) {
      dm.position.set(-w / 2 + 0.006 + (i % 10) * 0.0026, 0.0035, d / 2 - 0.004 - (i < 10 ? 0 : 0.0026));
      dm.updateMatrix();
      pins.setMatrixAt(i, dm.matrix);
    }
    pins.castShadow = true;
    b.add(pins);
    at(rbox(0.016, 0.0022, 0.016, m.plasticBlack, 0.0006), -w * 0.12, 0.0019, 0, b);
    at(rbox(0.009, 0.0035, 0.007, m.aluminum, 0.0008), w * 0.28, 0.0026, -d * 0.2, b);
    return b;
  };
  board(0.44, Y + 0.001, -0.64, 0.07, 0.052, m.pcbBlue, [0, 0.42, 0]);
  board(0.97, Y + 0.001, -0.74, 0.062, 0.046, m.pcbGreen, [0, -0.7, 0]);
  const leaning = board(0.7, Y + 0.03, -1.07, 0.075, 0.055, m.pcbBlack, [-1.18, 0.2, 0]);
  leaning.position.y = Y + 0.028;

  // A small powered hub with two LEDs — the reason anything on this side glows at night.
  const hub = at(new THREE.Group(), 0.3, Y, -0.96, root);
  hub.rotation.y = 0.24;
  at(rbox(0.088, 0.016, 0.042, m.aluminumDark, 0.004), 0, 0.008, 0, hub);
  for (const px of [-0.028, -0.006, 0.016]) at(rbox(0.014, 0.008, 0.005, m.plasticBlack, 0.001), px, 0.009, 0.0205, hub);
  const l1 = at(new THREE.Mesh(new THREE.CircleGeometry(0.0016, 8), m.ledBlue), 0.036, 0.0165, 0.006, hub);
  l1.rotation.x = -Math.PI / 2;
  const l2 = at(new THREE.Mesh(new THREE.CircleGeometry(0.0013, 8), m.ledGreen), 0.036, 0.0165, -0.006, hub);
  l2.rotation.x = -Math.PI / 2;
  leds.push(l1, l2);

  // Coiled wire and a screwdriver, front right.
  const coil = at(shadowed(new THREE.Mesh(new THREE.TorusGeometry(0.036, 0.0055, 7, 26), m.rubber)), 0.86, Y + 0.006, -0.62, root);
  coil.rotation.set(Math.PI / 2, 0, 0.3);
  const driver = at(new THREE.Group(), 0.58, Y + 0.008, -0.56, root);
  driver.rotation.set(0, 0.9, Math.PI / 2 + 0.03);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.0095, 0.0085, 0.072, 12), m.safetyOrange)), 0, 0, 0, driver);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.0022, 0.0022, 0.075, 8), m.steel)), 0, 0.07, 0, driver);
  // A few loose components scattered with restraint.
  for (let i = 0; i < 5; i++) {
    at(
      rbox(0.006 + r() * 0.004, 0.003, 0.005 + r() * 0.004, i % 2 ? m.plasticBlack : m.aluminum, 0.0008),
      0.42 + r() * 0.5,
      Y + 0.0015,
      -0.52 - r() * 0.12,
      root,
    ).rotation.y = r() * 3;
  }
  return leds;
}

/** Bins on the floor to the right: depth below the desk line, and a place for parts to live. */
function buildFloorBins(root: THREE.Group, m: Materials) {
  const g = at(new THREE.Group(), 0.98, 0, -0.62, root);
  g.rotation.y = -0.28;
  const crate = (y: number, w: number, h: number, d: number, mat: THREE.Material, yaw: number) => {
    const b = at(new THREE.Group(), 0, y, 0, g);
    b.rotation.y = yaw;
    const t = 0.008;
    at(rbox(w, t, d, mat, 0.004), 0, t / 2, 0, b);
    for (const s of [-1, 1]) {
      at(rbox(w, h, t, mat, 0.004), 0, h / 2, s * (d / 2 - t / 2), b).rotation.x = s * -0.04;
      at(rbox(t, h, d, mat, 0.004), s * (w / 2 - t / 2), h / 2, 0, b).rotation.z = s * 0.04;
    }
    at(rbox(w + 0.014, 0.01, d + 0.014, mat, 0.004), 0, h, 0, b);
    // Moulded handle recess on the long side.
    at(rbox(w * 0.3, 0.018, 0.006, mat, 0.003), 0, h - 0.03, d / 2 - 0.004, b);
    return b;
  };
  crate(0, 0.32, 0.17, 0.24, m.binBlue, 0);
  crate(0.181, 0.3, 0.14, 0.22, m.binWarm, 0.12);
  return g;
}

export function buildDeskSet(root: THREE.Group, m: Materials, assets: Assets): DeskRefs {
  buildDesk(root, m);
  const monitor = buildMonitor(root, m, assets);
  buildMacBook(root, m, assets);
  const kbLeds = buildKeyboard(root, m);
  buildMouse(root, m, assets);
  const lamp = buildLamp(root, m, assets);
  buildCube(root);
  buildMug(root, m);
  const clutterLeds = buildWorkClutter(root, m);
  buildFloorBins(root, m);
  return { ...monitor, ...lamp, leds: [...kbLeds, ...clutterLeds] };
}
