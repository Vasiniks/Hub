import * as THREE from 'three';
import type { Materials } from './materials';
import { DESK, DESKTOP } from './layout';
import { at, rbox, rboxGeo, rod, shadowed, rand } from './build';

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

/** §3: a real panel on a real stand, set far enough back to be an anchor rather than a wall. */
function buildMonitor(root: THREE.Group, m: Materials): Pick<DeskRefs, 'screen' | 'screenCenter' | 'screenSize'> {
  const { x, z, rotationY, panelWidth: PW, panelHeight: PH } = DESKTOP.monitor;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;

  // Stand: weighted plate, slim neck, small tilt knuckle.
  at(rbox(0.22, 0.014, 0.15, m.aluminumDark, 0.005), 0, 0.007, 0.03, g);
  at(rbox(0.04, 0.012, 0.13, m.aluminumDark, 0.004), 0, 0.016, 0.03, g);
  const neck = at(rbox(0.052, 0.22, 0.028, m.aluminumDark, 0.008), 0, 0.125, 0.0, g);
  neck.rotation.x = -0.05;
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.019, 0.019, 0.05, 14), m.aluminumDark)), 0, 0.235, 0.004, g).rotation.z =
    Math.PI / 2;

  const panel = at(new THREE.Group(), 0, 0.235 + PH / 2 + 0.012, 0.012, g);
  panel.rotation.x = -0.05;
  // Back shell tapers to a thin rim, so the monitor reads thin in profile.
  at(rbox(PW, PH, 0.02, m.plasticBlack, 0.006), 0, 0, -0.004, panel);
  at(rbox(PW - 0.09, PH - 0.09, 0.024, m.plasticBlack, 0.01), 0, 0.01, -0.016, panel);
  at(rbox(0.09, 0.05, 0.022, m.aluminumDark, 0.004), 0, -PH / 2 + 0.018, -0.02, panel);

  const screen = new THREE.Mesh(new THREE.PlaneGeometry(PW - 0.022, PH - 0.03), new THREE.MeshStandardMaterial({
    color: '#030405',
    roughness: 0.34,
    metalness: 0,
    envMapIntensity: 0.3,
    emissive: '#ffffff',
    emissiveIntensity: 1,
  }));
  at(screen, 0, 0.004, 0.0075, panel);
  // §19: a separate glass sheet so the panel picks up the room rather than only emitting.
  const glass = at(new THREE.Mesh(new THREE.PlaneGeometry(PW - 0.02, PH - 0.028), m.glass), 0, 0.004, 0.0085, panel);
  glass.renderOrder = 3;
  glass.castShadow = glass.receiveShadow = false;
  glass.userData.noMerge = true;
  glass.userData.ignoreRaycast = true;

  g.updateMatrixWorld(true);
  const screenCenter = screen.getWorldPosition(new THREE.Vector3());
  return { screen, screenCenter, screenSize: new THREE.Vector2(PW - 0.022, PH - 0.03) };
}

/**
 * §4/§17: closed, on an inclined riser, sloping up and away from the visitor.
 *
 * The riser is a real extruded side profile with a front lip, and the laptop sits on the deck
 * plane that profile defines — so the arms cannot punch through the body, and the contact is
 * an actual contact rather than two shapes overlapping. The rear edge is a cylinder, which is
 * what a closed laptop's hinge reads as from behind.
 */
function buildMacBook(root: THREE.Group, m: Materials) {
  const { x, z, rotationY, tilt } = DESKTOP.macbook;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;

  // Side profile in the ZY plane: foot, back post, deck line, front lip.
  const BACK_Z = -0.112;
  const FRONT_Z = 0.104;
  const BACK_Y = 0.086;
  const FRONT_Y = 0.022;
  const profile = new THREE.Shape();
  // Back post, deck line falling toward the visitor, then a short lip that stops the body
  // sliding forward. The lip is 5mm — enough to catch the front edge, not a pillar.
  profile.moveTo(BACK_Z, 0.004);
  profile.lineTo(BACK_Z, BACK_Y);
  profile.lineTo(FRONT_Z - 0.012, FRONT_Y);
  profile.lineTo(FRONT_Z, FRONT_Y + 0.005);
  profile.lineTo(FRONT_Z + 0.006, FRONT_Y + 0.005);
  profile.lineTo(FRONT_Z + 0.006, 0.004);
  profile.lineTo(FRONT_Z - 0.03, 0.004);
  profile.lineTo(BACK_Z + 0.03, 0.004);
  profile.closePath();
  const armGeo = new THREE.ExtrudeGeometry(profile, { depth: 0.016, bevelEnabled: true, bevelSize: 0.0014, bevelThickness: 0.0014, bevelSegments: 1, curveSegments: 1 });
  // Extrude runs along +z; stand it up so the profile lies in the room's ZY plane. The sign
  // matters: +PI/2 mirrors the profile in z and puts the tall back post at the front.
  armGeo.rotateY(-Math.PI / 2);

  for (const side of [-1, 1]) {
    const arm = at(shadowed(new THREE.Mesh(armGeo, m.aluminum)), side * 0.131 + 0.008, 0, 0, g);
    at(rbox(0.02, 0.005, 0.032, m.rubber, 0.002), side * 0.131, 0.0032, BACK_Z + 0.022, g);
    at(rbox(0.02, 0.005, 0.032, m.rubber, 0.002), side * 0.131, 0.0032, FRONT_Z - 0.026, g);
    void arm;
  }
  // Cross brace between the arms, tucked under the deck so it never meets the body.
  const brace = at(rbox(0.24, 0.01, 0.026, m.aluminumDark, 0.003), 0, 0.058, BACK_Z + 0.03, g);
  brace.rotation.x = tilt;

  // The deck plane the laptop rests on, defined by the profile's top edge.
  const deckMidZ = (BACK_Z + FRONT_Z) / 2;
  const deckMidY = (BACK_Y + FRONT_Y) / 2;
  const deck = at(new THREE.Group(), 0, deckMidY, deckMidZ, g);
  // Positive rotation drops the front and lifts the back: the slope runs away from the visitor.
  deck.rotation.x = Math.atan2(BACK_Y - FRONT_Y, FRONT_Z - BACK_Z);

  // Grip strips where the body actually touches the deck.
  for (const gz of [BACK_Z - deckMidZ + 0.024, FRONT_Z - deckMidZ - 0.028]) {
    at(rbox(0.2, 0.0025, 0.014, m.rubber, 0.001), 0, 0.0012, gz, deck);
  }

  // Body: base and lid as separate slabs, a hair apart, with a cylindrical rear edge.
  const W = 0.304;
  const D = 0.2;
  at(rbox(W, 0.0095, D, m.aluminum, 0.0028), 0, 0.00725, 0.004, deck);
  at(rbox(W - 0.004, 0.0072, D - 0.003, m.aluminum, 0.0024), 0, 0.0156, 0.004, deck);
  const hinge = at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.0084, 0.0084, W - 0.028, 18), m.aluminumDark)), 0, 0.0113, -0.0955, deck);
  hinge.rotation.z = Math.PI / 2;
  // Seam between lid and base, and the notch under the front edge.
  for (const side of [-1, 1]) at(rbox(0.0016, 0.0014, D - 0.02, m.aluminumDark, 0.0004), side * (W / 2 - 0.0012), 0.0119, 0.004, deck);
  at(rbox(0.058, 0.0042, 0.0035, m.aluminumDark, 0.001), 0, 0.0115, D / 2 + 0.0038, deck);
  // Ports on the left flank.
  for (const pz of [-0.03, 0.006, 0.042]) at(rbox(0.0035, 0.0036, 0.0155, m.plasticBlack, 0.001), -W / 2 + 0.0008, 0.0092, pz, deck);

  // Charge cable leaving the left flank and dropping behind the desk.
  deck.updateMatrixWorld(true);
  const port = deck.localToWorld(new THREE.Vector3(-W / 2, 0.0092, 0.006));
  const cable = new THREE.CatmullRomCurve3([
    port,
    port.clone().add(new THREE.Vector3(-0.09, -0.028, -0.05)),
    port.clone().add(new THREE.Vector3(-0.13, -0.05, -0.16)),
    port.clone().add(new THREE.Vector3(-0.1, -0.056, -0.28)),
  ]);
  root.add(shadowed(new THREE.Mesh(new THREE.TubeGeometry(cable, 26, 0.0034, 6), m.plasticWhite)));
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
  const capGeo = rboxGeo(U - GAP, 0.0092, U - GAP, 0.0016, 1);
  const counts = { alpha: 0, mod: 0 };
  const place: { accent: boolean; x: number; z: number; w: number; y: number }[] = [];
  for (let r = 0; r < rows; r++) {
    let cursor = -width / 2;
    // Slight row sculpting: the home row sits lowest.
    const sculpt = [0.0016, 0.0009, 0.0003, 0, 0.0004, 0.0011][r];
    const zRow = -depth / 2 + 0.006 + (r + 0.5) * U;
    for (const w of TKL_ROWS[r]) {
      if (w < 0) {
        cursor += -w * U;
        continue;
      }
      const accent = w !== 1 || r === 0 || (r === 5 && false);
      place.push({ accent, x: cursor + (w * U) / 2, z: zRow, w, y: 0.0255 + sculpt });
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
    dummy.scale.set((p.w * U - GAP) / (U - GAP), 1, 1);
    dummy.updateMatrix();
    if (p.accent) mods.setMatrixAt(mi++, dummy.matrix);
    else alphas.setMatrixAt(ai++, dummy.matrix);
  }
  for (const im of [alphas, mods]) {
    im.castShadow = im.receiveShadow = true;
    caseG.add(im);
  }
  // Indicator LEDs above the nav cluster.
  const led = at(new THREE.Mesh(new THREE.CircleGeometry(0.0015, 8), m.ledGreen), width / 2 - 0.028, 0.0212, -depth / 2 + 0.002, caseG);
  led.rotation.x = -Math.PI / 2;
  return [led];
}

/** §5: white mouse, right of the keyboard. */
function buildMouse(root: THREE.Group, m: Materials) {
  const { x, z, rotationY } = DESKTOP.mouse;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  at(rbox(0.061, 0.018, 0.108, m.plasticWhite, 0.012), 0, 0.009, 0, g);
  // Domed shell: a squashed sphere is the cheapest honest mouse silhouette.
  const shell = at(shadowed(new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), m.plasticWhite)), 0, 0.012, -0.004, g);
  shell.scale.set(0.031, 0.0205, 0.056);
  // Button split and scroll wheel.
  at(rbox(0.0016, 0.004, 0.042, m.keycapAccent, 0.0005), 0, 0.0305, -0.026, g);
  const wheel = at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.0072, 0.0072, 0.0052, 14), m.plasticGrey)), 0, 0.0318, -0.03, g);
  wheel.rotation.z = Math.PI / 2;
  at(rbox(0.0035, 0.006, 0.02, m.keycapAccent, 0.001), -0.031, 0.016, -0.012, g);
  return g;
}

/**
 * §6: a flat circular head on a two-axis arm, with medals hung off the upper joint.
 * The head is also the room's warm light source after dark.
 */
function buildLamp(root: THREE.Group, m: Materials): Omit<DeskRefs, 'screen' | 'screenCenter' | 'screenSize' | 'leds'> {
  const { x, z, headRadius: R } = DESKTOP.lamp;
  const g = at(new THREE.Group(), x, DESK.top, z, root);

  // Weighted base with a rubber foot ring and a small brushed collar.
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.082, 0.09, 0.016, 28), m.aluminumDark)), 0, 0.008, 0, g);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.086, 0.086, 0.003, 28), m.rubber)), 0, 0.0015, 0, g);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.034, 0.022, 20), m.aluminum)), 0, 0.026, 0, g);

  // Two-axis arm: post → shoulder knuckle → lower arm → elbow knuckle → upper arm → head yoke.
  const knuckle = (px: number, py: number, pz: number, r = 0.013) => {
    const k = at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.026, 14), m.aluminum)), px, py, pz, g);
    k.rotation.z = Math.PI / 2;
    at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(r * 0.45, r * 0.45, 0.032, 10), m.steel)), px, py, pz, g).rotation.z =
      Math.PI / 2;
    return k;
  };
  const p0 = new THREE.Vector3(0, 0.035, 0);
  const p1 = new THREE.Vector3(0, 0.2, 0.005);
  const p2 = new THREE.Vector3(0.12, 0.44, 0.1);
  const p3 = new THREE.Vector3(0.3, 0.5, 0.235);
  g.add(rod(p0, p1, 0.011, m.aluminum, 12));
  knuckle(p1.x, p1.y, p1.z);
  // Arm segments are flattened bars, not tubes: they read as a mechanism.
  const seg = (a: THREE.Vector3, b: THREE.Vector3, w: number) => {
    const bar = rod(a, b, 0.0085, m.aluminum, 8);
    bar.scale.x = w;
    g.add(bar);
    return bar;
  };
  seg(p1, p2, 2.1);
  knuckle(p2.x, p2.y, p2.z, 0.0145);
  seg(p2, p3, 1.9);
  // Tension spring alongside the lower arm.
  const spring = rod(new THREE.Vector3(0.018, 0.22, 0.03), new THREE.Vector3(0.108, 0.41, 0.09), 0.004, m.steel, 6);
  g.add(spring);

  const head = at(new THREE.Group(), p3.x, p3.y, p3.z, g);
  // Aim down and forward onto the working half of the desk. The head's +z is the beam axis,
  // which is also what the spot light and the dust volume follow.
  const pool = new THREE.Vector3(-0.02, DESK.top, -0.42);
  head.lookAt(pool);
  // Flat circular body: rim, back plate, diffuser.
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(R, R, 0.026, 32), m.aluminum)), 0, 0, 0, head).rotation.x = Math.PI / 2;
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(R - 0.008, R - 0.008, 0.03, 32), m.aluminumDark)), 0, 0, -0.004, head).rotation.x =
    Math.PI / 2;
  const disc = at(new THREE.Mesh(new THREE.CircleGeometry(R - 0.011, 32), new THREE.MeshStandardMaterial({
    color: '#0a0a0a',
    emissive: '#ffd6a0',
    emissiveIntensity: 0.1,
    roughness: 0.6,
  })), 0, 0, 0.0145, head);
  // Yoke arms holding the head, and a small tilt knob.
  for (const s of [-1, 1]) {
    const yoke = at(rbox(0.008, 0.05, 0.016, m.aluminum, 0.003), s * (R - 0.004), -0.03, -0.01, head);
    yoke.rotation.z = s * 0.35;
  }
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.02, 10), m.steel)), R - 0.006, -0.05, -0.012, head).rotation.z =
    Math.PI / 2;

  const socket = at(new THREE.Object3D(), 0, 0, 0.03, head);
  const target = at(new THREE.Object3D(), 0, 0, 1, head);

  buildMedals(g, m, p2, p3);

  g.updateMatrixWorld(true);
  return { lampHead: head, lampSocket: socket, lampTarget: target, lampDisc: disc, lampPool: pool };
}

/**
 * §6: medals hung over the lamp's upper arm. Each one is a lanyard folded over the arm with
 * the disc swinging at the bottom — lengths, lean and facing all differ, so they read as
 * things that were dropped there rather than an arrangement.
 */
function buildMedals(lamp: THREE.Group, m: Materials, armA: THREE.Vector3, armB: THREE.Vector3) {
  const metals = [m.gold, m.silver, m.bronze, m.gold];
  const ribbons = [m.ribbonBlue, m.ribbonRed, m.ribbonGreen, m.ribbonRed];
  const r = rand(4211);
  // Where along the arm each lanyard sits, how long it hangs, and how it has settled.
  const specs = [
    { t: 0.26, drop: 0.2, lean: -0.24, turn: 0.35, tilt: 0.16 },
    { t: 0.42, drop: 0.155, lean: -0.1, turn: 1.32, tilt: -0.08 },
    { t: 0.55, drop: 0.235, lean: -0.3, turn: -0.42, tilt: 0.24 },
    { t: 0.68, drop: 0.13, lean: -0.05, turn: 0.78, tilt: -0.2 },
  ];
  specs.forEach((s, i) => {
    const hang = armA.clone().lerp(armB, s.t);
    const g = at(new THREE.Group(), hang.x, hang.y, hang.z, lamp);
    g.rotation.z = s.lean;
    g.rotation.y = s.turn;
    g.rotation.x = s.tilt * 0.5;

    // Lanyard: two straps from the arm down to the ring, splayed slightly apart.
    const bottom = -s.drop;
    for (const side of [-1, 1]) {
      const strap = at(rbox(0.009, s.drop, 0.0016, ribbons[i], 0.0006), side * 0.011, bottom / 2, 0, g);
      strap.rotation.z = side * 0.05 + (r() - 0.5) * 0.04;
    }
    at(rbox(0.026, 0.006, 0.0022, ribbons[i], 0.0008), 0, bottom + 0.004, 0, g);
    // Ring and disc.
    const ring = at(shadowed(new THREE.Mesh(new THREE.TorusGeometry(0.006, 0.0016, 6, 12), metals[i])), 0, bottom - 0.002, 0, g);
    ring.rotation.y = Math.PI / 2;
    const disc = at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.023, 0.023, 0.0035, 22), metals[i])), 0, bottom - 0.028, 0, g);
    disc.rotation.x = Math.PI / 2;
    disc.rotation.z = (r() - 0.5) * 0.5;
    // Raised inner face so the disc is not a plain coin.
    at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 0.0042, 22), metals[i])), 0, bottom - 0.028, 0.0004, g).rotation.x =
      Math.PI / 2;
  });
}

/** §14: a recognisable speedcube, caught mid-solve with one layer turned. */
function buildCube(root: THREE.Group) {
  const { x, z, rotationY, size } = DESKTOP.cube;
  const g = at(new THREE.Group(), x, DESK.top, z, root);
  g.rotation.y = rotationY;
  g.rotation.x = 0.02;

  const cubie = size / 3;
  const gap = 0.0011;
  const body = new THREE.MeshStandardMaterial({ color: '#0d0e10', roughness: 0.42 });
  // Stickers are rounded plates, slightly inset — that inset is what reads as a speedcube.
  const faces: Record<string, THREE.MeshStandardMaterial> = {
    U: new THREE.MeshStandardMaterial({ color: '#eef0f2', roughness: 0.28 }),
    D: new THREE.MeshStandardMaterial({ color: '#f0d64a', roughness: 0.28 }),
    F: new THREE.MeshStandardMaterial({ color: '#2f7d4c', roughness: 0.28 }),
    B: new THREE.MeshStandardMaterial({ color: '#2a5da8', roughness: 0.28 }),
    L: new THREE.MeshStandardMaterial({ color: '#d9541f', roughness: 0.28 }),
    R: new THREE.MeshStandardMaterial({ color: '#b3282d', roughness: 0.28 }),
  };
  const stickerGeo = rboxGeo(cubie * 0.78, 0.0012, cubie * 0.78, cubie * 0.16, 1);

  // Top layer is rotated ~32°: the cube is mid-solve, not sitting factory-fresh.
  const top = at(new THREE.Group(), 0, 0, 0, g);
  top.rotation.y = 0.56;
  for (let ix = -1; ix <= 1; ix++) {
    for (let iy = -1; iy <= 1; iy++) {
      for (let iz = -1; iz <= 1; iz++) {
        if (ix === 0 && iy === 0 && iz === 0) continue;
        const parent = iy === 1 ? top : g;
        const c = at(
          shadowed(new THREE.Mesh(rboxGeo(cubie - gap, cubie - gap, cubie - gap, cubie * 0.13, 1), body)),
          ix * cubie,
          size / 2 + iy * cubie,
          iz * cubie,
          parent,
        );
        const put = (mat: THREE.MeshStandardMaterial, ox: number, oy: number, oz: number, rx: number, rz: number) => {
          const s = at(new THREE.Mesh(stickerGeo, mat), ox, oy, oz, c);
          s.rotation.set(rx, 0, rz);
          s.castShadow = false;
          s.receiveShadow = true;
        };
        const h = cubie / 2 - 0.0002;
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

export function buildDeskSet(root: THREE.Group, m: Materials): DeskRefs {
  buildDesk(root, m);
  const monitor = buildMonitor(root, m);
  buildMacBook(root, m);
  const kbLeds = buildKeyboard(root, m);
  buildMouse(root, m);
  const lamp = buildLamp(root, m);
  buildCube(root);
  buildMug(root, m);
  const clutterLeds = buildWorkClutter(root, m);
  buildFloorBins(root, m);
  return { ...monitor, ...lamp, leds: [...kbLeds, ...clutterLeds] };
}
