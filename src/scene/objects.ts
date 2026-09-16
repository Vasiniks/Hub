import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import type { BuilderKey } from '../data/projects';
import type { Materials } from './materials';
import { mergeStatic } from './merge';
import { rand } from './build';

export interface BuiltObject {
  group: THREE.Group;
  /** activity: 0 at rest, rises toward 1 while hovered or examined. */
  tick?: (time: number, activity: number) => void;
}

function mesh(geo: THREE.BufferGeometry, mat: THREE.Material, x = 0, y = 0, z = 0, parent?: THREE.Object3D) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent?.add(m);
  return m;
}

/** Position an already-built object (instanced meshes cannot go through `mesh`). */
function at2<T extends THREE.Object3D>(o: T, x: number, y: number, z: number): T {
  o.position.set(x, y, z);
  return o;
}

const rb = (w: number, h: number, d: number, r = 0.004) =>
  new RoundedBoxGeometry(w, h, d, 2, Math.min(r, w / 2 - 1e-4, h / 2 - 1e-4, d / 2 - 1e-4));

function placard(text: string) {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 96;
  const ctx = c.getContext('2d')!;
  ctx.fillStyle = '#f2f2f0';
  ctx.fillRect(0, 0, 256, 96);
  ctx.fillStyle = '#16181b';
  ctx.font = '600 70px "IBM Plex Sans Condensed", system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 128, 52);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return new THREE.MeshStandardMaterial({ map: t, roughness: 0.7 });
}

/**
 * §5/§31: a competition robot, not a stack of primitives.
 *
 * What makes an FRC robot legible is specific: fabric bumpers with a flat face and a number
 * plate, extruded aluminium rails with lightening holes, swerve modules with treaded wheels
 * and a motor stack on top, and a visible electrical board — battery, PDP, roboRIO, breaker.
 * Those are the details this builds; the rest stays low-poly.
 */
function frcRobot(m: Materials): BuiltObject {
  const g = new THREE.Group();
  const W = 0.62;
  const L = 0.62;
  const H0 = 0.075;
  const r = rand(8123);

  // ---- Frame: 2x1 extrusion with lightening holes -------------------------
  const holeMat = new THREE.MeshStandardMaterial({ color: '#0c0d0f', roughness: 0.9 });
  const rail = (w: number, d: number, x: number, z: number, along: 'x' | 'z') => {
    mesh(rb(w, 0.05, d, 0.004), m.aluminum, x, H0, z, g);
    // Holes read as dark discs on the web of the rail.
    const n = 7;
    for (let i = 0; i < n; i++) {
      const t = (i + 0.5) / n - 0.5;
      const hx = along === 'x' ? x + t * (w - 0.06) : x;
      const hz = along === 'x' ? z : z + t * (d - 0.06);
      for (const side of [-1, 1]) {
        const hole = mesh(new THREE.CircleGeometry(0.014, 12), holeMat, hx, H0, hz, g);
        if (along === 'x') {
          hole.position.z += side * (d / 2 + 0.0004);
          hole.rotation.y = side > 0 ? 0 : Math.PI;
        } else {
          hole.position.x += side * (w / 2 + 0.0004);
          hole.rotation.y = side * Math.PI / 2;
        }
        hole.castShadow = false;
      }
    }
  };
  rail(W - 0.08, 0.035, 0, -(L / 2 - 0.06), 'x');
  rail(W - 0.08, 0.035, 0, L / 2 - 0.06, 'x');
  rail(0.035, L - 0.08, -(W / 2 - 0.06), 0, 'z');
  rail(0.035, L - 0.08, W / 2 - 0.06, 0, 'z');
  // Belly pan.
  mesh(rb(W - 0.11, 0.005, L - 0.11, 0.002), m.plasticGrey, 0, H0 - 0.022, 0, g);

  // ---- Bumpers: flat fabric faces, not tubes ------------------------------
  const plate = placard('0000');
  const bumper = (w: number, d: number, x: number, z: number, face: 'z' | 'x', sign: number) => {
    // Small radius: a bumper has a flat front with rounded corners. A large radius turns it
    // into a foam noodle, which is what this looked like before.
    mesh(rb(w, 0.125, d, 0.012), m.bumperRed, x, 0.105, z, g);
    // Seam where the fabric wraps the plywood backing.
    mesh(rb(w * 0.995, 0.004, d * 0.995, 0.002), m.rubber, x, 0.105, z, g);
    if (face === 'z') {
      const p = mesh(new THREE.PlaneGeometry(0.21, 0.08), plate, x, 0.108, z + sign * (d / 2 + 0.0012), g);
      p.rotation.y = sign > 0 ? 0 : Math.PI;
      p.castShadow = false;
    }
  };
  bumper(W + 0.1, 0.075, 0, -(L / 2 + 0.012), 'z', -1);
  bumper(W + 0.1, 0.075, 0, L / 2 + 0.012, 'z', 1);
  bumper(0.075, L - 0.04, -(W / 2 + 0.012), 0, 'x', -1);
  bumper(0.075, L - 0.04, W / 2 + 0.012, 0, 'x', 1);

  // ---- Swerve modules: treaded wheel, gear plate, motor stack -------------
  const treadGeo = new THREE.BoxGeometry(0.0085, 0.006, 0.036);
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) {
    const mx = sx * (W / 2 - 0.105);
    const mz = sz * (L / 2 - 0.105);
    const mod = new THREE.Group();
    mod.position.set(mx, 0, mz);
    // Each module is steered a little differently — a swerve drive at rest rarely lines up.
    mod.rotation.y = (r() - 0.5) * 0.7;
    g.add(mod);

    mesh(rb(0.105, 0.035, 0.105, 0.006), m.plasticBlack, 0, H0 + 0.012, 0, mod);
    const wheel = mesh(new THREE.CylinderGeometry(0.051, 0.051, 0.034, 22), m.rubber, 0, 0.051, 0, mod);
    wheel.rotation.z = Math.PI / 2;
    // Tread blocks around the circumference.
    const tread = new THREE.InstancedMesh(treadGeo, m.rubber, 18);
    const d = new THREE.Object3D();
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * Math.PI * 2;
      d.position.set(0, Math.sin(a) * 0.0525, Math.cos(a) * 0.0525);
      d.rotation.set(-a, 0, 0);
      d.updateMatrix();
      tread.setMatrixAt(i, d.matrix);
    }
    tread.castShadow = tread.receiveShadow = true;
    mesh(rb(0.09, 0.05, 0.006, 0.002), m.aluminum, 0, 0.05, 0.026, mod);
    mod.add(at2(tread, 0, 0.051, 0));
    // Drive and steer motors stacked above the module.
    mesh(new THREE.CylinderGeometry(0.026, 0.026, 0.072, 16), m.steel, 0.022, H0 + 0.07, 0, mod);
    mesh(new THREE.CylinderGeometry(0.027, 0.027, 0.012, 16), m.safetyOrange, 0.022, H0 + 0.112, 0, mod);
    mesh(new THREE.CylinderGeometry(0.019, 0.019, 0.05, 14), m.steel, -0.026, H0 + 0.058, 0.01, mod);
  }

  // ---- Electrical board ---------------------------------------------------
  // Battery with a retention strap.
  mesh(rb(0.165, 0.09, 0.09, 0.005), m.plasticBlack, -0.09, H0 + 0.043, 0.115, g);
  mesh(rb(0.172, 0.012, 0.02, 0.003), m.bumperRed, -0.09, H0 + 0.09, 0.115, g);
  for (const bx of [-0.05, 0.005]) mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.014, 10), m.copper, -0.09 + bx, H0 + 0.094, 0.09, g);
  // Power distribution panel: a row of breakers is the recognisable part.
  mesh(rb(0.135, 0.028, 0.115, 0.004), m.plasticWhite, 0.095, H0 + 0.014, 0.075, g);
  for (let i = 0; i < 8; i++) {
    mesh(rb(0.011, 0.012, 0.02, 0.002), m.safetyOrange, 0.047 + (i % 4) * 0.032, H0 + 0.033, 0.045 + Math.floor(i / 4) * 0.045, g);
  }
  // roboRIO with a port face.
  mesh(rb(0.115, 0.032, 0.075, 0.004), m.plasticGrey, 0.075, H0 + 0.016, -0.095, g);
  for (const px of [-0.03, 0, 0.03]) mesh(rb(0.018, 0.012, 0.004, 0.001), m.plasticBlack, 0.075 + px, H0 + 0.018, -0.059, g);
  // Main breaker and a radio.
  mesh(rb(0.03, 0.03, 0.022, 0.003), m.bumperRed, -0.005, H0 + 0.015, -0.09, g);
  mesh(rb(0.055, 0.016, 0.055, 0.003), m.plasticBlack, -0.09, H0 + 0.008, -0.07, g);

  // Loom from battery to PDP, and PDP to roboRIO.
  for (const [pts, colour, rad] of [
    [[[-0.005, 0.1, 0.09], [0.03, 0.14, 0.06], [0.06, 0.1, 0.05]], m.bumperRed, 0.007],
    [[[0.09, 0.1, 0.04], [0.09, 0.12, -0.02], [0.08, 0.09, -0.06]], m.plasticBlack, 0.005],
  ] as const) {
    const curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
    mesh(new THREE.TubeGeometry(curve, 14, rad, 6), colour, 0, 0, 0, g);
  }

  // ---- Elevator with a roller intake -------------------------------------
  const mast = new THREE.Group();
  mast.position.set(0, H0, -0.17);
  g.add(mast);
  for (const x of [-0.13, 0.13]) {
    mesh(rb(0.035, 0.62, 0.035), m.aluminum, x, 0.31, 0, mast);
    mesh(rb(0.028, 0.5, 0.028), m.aluminum, x, 0.42, 0.04, mast);
    // Belt run up the inside of each stage.
    mesh(rb(0.005, 0.56, 0.012, 0.001), m.rubber, x - 0.02, 0.33, 0, mast);
  }
  mesh(rb(0.3, 0.03, 0.035), m.aluminum, 0, 0.62, 0, mast);
  const carriage = new THREE.Group();
  carriage.position.set(0, 0.46, 0.07);
  carriage.userData.dynamic = true;
  mast.add(carriage);
  mesh(rb(0.26, 0.12, 0.012, 0.004), m.plasticGrey, 0, 0, 0, carriage);
  for (const y of [-0.04, 0.05]) {
    const roller = mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.24, 14), m.safetyOrange, 0, y, 0.06, carriage);
    roller.rotation.z = Math.PI / 2;
  }
  for (const x of [-0.12, 0.12]) mesh(rb(0.01, 0.14, 0.09, 0.003), m.plasticGrey, x, 0.005, 0.04, carriage);

  const rslMat = m.ledOrange.clone();
  mesh(rb(0.035, 0.05, 0.035, 0.006), rslMat, 0.13, 0.66, 0.03, mast);

  return {
    group: g,
    tick(time, activity) {
      // Robot signal light: slow blink when idle, faster when examined.
      const rate = 1.0 + activity * 1.5;
      rslMat.emissiveIntensity = Math.sin(time * Math.PI * rate) > 0 ? 3.2 : 0.15;
      carriage.position.y = 0.46 + Math.sin(time * 0.5) * 0.004 * activity;
    },
  };
}

function polyhedron(m: Materials): BuiltObject {
  const g = new THREE.Group();
  mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.018, 28), m.steel, 0, 0.009, 0, g);
  mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.05, 8), m.steel, 0, 0.04, 0, g);

  const body = new THREE.Group();
  // Satin rather than mirror: the rods sit near the lamp and should read as metal, not as light.
  const rodMat = new THREE.MeshStandardMaterial({ color: '#9ea4aa', roughness: 0.5, metalness: 0.85 });
  body.position.y = 0.115;
  body.userData.dynamic = true;
  g.add(body);
  const ico = new THREE.IcosahedronGeometry(0.06, 0);
  const pos = ico.getAttribute('position');
  const seen = new Set<string>();
  const key = (v: THREE.Vector3) => `${v.x.toFixed(3)},${v.y.toFixed(3)},${v.z.toFixed(3)}`;
  const up = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < pos.count; i += 3) {
    const tri = [0, 1, 2].map((k) => new THREE.Vector3().fromBufferAttribute(pos, i + k));
    for (let e = 0; e < 3; e++) {
      const a = tri[e];
      const b = tri[(e + 1) % 3];
      const id = [key(a), key(b)].sort().join('|');
      if (seen.has(id)) continue;
      seen.add(id);
      const len = a.distanceTo(b);
      const rodMesh = mesh(new THREE.CylinderGeometry(0.0022, 0.0022, len, 6), rodMat, 0, 0, 0, body);
      rodMesh.position.copy(a).lerp(b, 0.5);
      rodMesh.quaternion.setFromUnitVectors(up, b.clone().sub(a).normalize());
    }
    for (const v of tri) {
      if (seen.has(key(v))) continue;
      seen.add(key(v));
      mesh(new THREE.SphereGeometry(0.0045, 8, 6), rodMat, v.x, v.y, v.z, body);
    }
  }
  const inner = mesh(new THREE.OctahedronGeometry(0.026, 0), m.safetyOrange, 0, 0, 0, body);

  return {
    group: g,
    tick(time, activity) {
      body.rotation.y = time * (0.12 + activity * 0.5);
      body.rotation.x = Math.sin(time * 0.2) * 0.15;
      inner.rotation.y = -time * 0.6;
    },
  };
}

function graphPaper() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const ctx = c.getContext('2d')!;
  ctx.fillStyle = '#ecebe6';
  ctx.fillRect(0, 0, 512, 512);
  ctx.strokeStyle = 'rgba(80,120,150,0.25)';
  for (let i = 0; i <= 512; i += 16) {
    ctx.lineWidth = i % 80 === 0 ? 1.6 : 0.8;
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 512); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(512, i); ctx.stroke();
  }
  ctx.strokeStyle = '#2d3137';
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (let x = 20; x < 492; x += 4) {
    const y = 256 - 150 * Math.sin((x - 20) * 0.02) * Math.exp(-(x - 20) * 0.004);
    x === 20 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return new THREE.MeshStandardMaterial({ map: t, roughness: 0.9 });
}

function notebooks(m: Materials): BuiltObject {
  const g = new THREE.Group();
  const covers = ['#2f3439', '#46505a', '#1f2a24'];
  let y = 0;
  covers.forEach((color, i) => {
    const h = 0.012 + i * 0.002;
    const nb = mesh(rb(0.21, h, 0.28, 0.003), new THREE.MeshStandardMaterial({ color, roughness: 0.8 }), 0, y + h / 2, 0, g);
    nb.rotation.y = [0.05, -0.08, 0.12][i];
    y += h;
  });
  const sheet = mesh(new THREE.PlaneGeometry(0.2, 0.26), graphPaper(), 0.02, y + 0.001, 0.01, g);
  sheet.rotation.set(-Math.PI / 2, 0, 0.2);
  const pencil = mesh(new THREE.CylinderGeometry(0.0045, 0.0045, 0.17, 6), m.safetyOrange, 0.07, y + 0.006, 0.02, g);
  pencil.rotation.set(Math.PI / 2, 0, -0.5);
  return { group: g };
}

function devBoard(m: Materials): BuiltObject {
  const g = new THREE.Group();
  const board = mesh(rb(0.1, 0.004, 0.07, 0.002), m.pcbGreen, 0, 0.012, 0, g);
  for (const [x, z] of [[-0.044, -0.03], [0.044, -0.03], [-0.044, 0.03], [0.044, 0.03]]) {
    mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.01, 8), m.aluminum, x, 0.005, z, g);
  }
  mesh(rb(0.03, 0.004, 0.03, 0.001), m.plasticBlack, -0.012, 0.0045, 0.004, board);
  const sink = new THREE.Group();
  sink.position.set(-0.012, 0.012, 0.004);
  board.add(sink);
  mesh(rb(0.032, 0.003, 0.032, 0.001), m.aluminum, 0, -0.004, 0, sink);
  for (let i = 0; i < 6; i++) mesh(new THREE.BoxGeometry(0.0022, 0.009, 0.03), m.aluminum, -0.013 + i * 0.0052, 0.002, 0, sink);
  mesh(rb(0.014, 0.003, 0.02, 0.001), m.plasticBlack, 0.028, 0.004, -0.018, board);
  mesh(rb(0.012, 0.007, 0.014, 0.002), m.aluminum, 0.047, 0.0055, 0.018, board);
  mesh(rb(0.012, 0.007, 0.014, 0.002), m.aluminum, 0.047, 0.0055, -0.004, board);
  const pins = new THREE.InstancedMesh(new THREE.BoxGeometry(0.0016, 0.007, 0.0016), m.aluminum, 40);
  const d = new THREE.Object3D();
  for (let i = 0; i < 40; i++) {
    d.position.set(-0.038 + (i % 20) * 0.0026, 0.0055, 0.029 + (i >= 20 ? 0.0026 : 0));
    d.updateMatrix();
    pins.setMatrixAt(i, d.matrix);
  }
  board.add(pins);
  const power = m.ledGreen.clone();
  const act = m.ledOrange.clone();
  mesh(new THREE.BoxGeometry(0.003, 0.002, 0.002), power, 0.03, 0.0035, 0.02, board);
  mesh(new THREE.BoxGeometry(0.003, 0.002, 0.002), act, 0.03, 0.0035, 0.025, board);

  // Short ribbon toward the monitor
  const ribbon = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-0.04, 0.02, 0.03),
    new THREE.Vector3(-0.07, 0.03, -0.02),
    new THREE.Vector3(-0.09, 0.004, -0.08),
  ]);
  mesh(new THREE.TubeGeometry(ribbon, 16, 0.003, 5), m.plasticGrey, 0, 0, 0, g);

  let nextBlink = 0;
  let on = false;
  return {
    group: g,
    tick(time, activity) {
      if (time > nextBlink) {
        on = !on;
        const busy = 0.04 + Math.random() * (on ? 0.12 : 0.9 - activity * 0.75);
        nextBlink = time + busy;
      }
      act.emissiveIntensity = on ? 2.8 : 0.05;
    },
  };
}

function partsCrate(m: Materials): BuiltObject {
  const g = new THREE.Group();
  const bin = new THREE.MeshStandardMaterial({ color: '#4a4f55', roughness: 0.7 });
  const W = 0.46, H = 0.24, D = 0.32, T = 0.012;
  mesh(rb(W, T, D, 0.004), bin, 0, T / 2, 0, g);
  for (const s of [-1, 1]) {
    mesh(rb(W, H, T, 0.004), bin, 0, H / 2, s * (D / 2 - T / 2), g);
    mesh(rb(T, H, D, 0.004), bin, s * (W / 2 - T / 2), H / 2, 0, g);
  }
  const bar1 = mesh(rb(0.03, 0.03, 0.42, 0.003), m.aluminum, -0.1, 0.22, 0.0, g);
  bar1.rotation.set(0.6, 0.2, 0.25);
  const bar2 = mesh(rb(0.03, 0.03, 0.36, 0.003), m.aluminum, -0.04, 0.2, 0.03, g);
  bar2.rotation.set(0.9, -0.3, -0.2);
  const wheel = mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.03, 20), m.rubber, 0.12, 0.2, -0.04, g);
  wheel.rotation.set(1.2, 0.2, 0.3);
  const coil = mesh(new THREE.TorusGeometry(0.05, 0.008, 8, 24), m.bumperRed, 0.1, 0.235, 0.07, g);
  coil.rotation.x = Math.PI / 2 - 0.3;
  mesh(rb(0.09, 0.06, 0.07, 0.006), m.cardboard, 0.02, 0.2, -0.08, g);
  mesh(rb(0.06, 0.05, 0.05, 0.004), m.plasticWhite, -0.15, 0.2, -0.1, g).rotation.y = 0.5;
  return { group: g };
}

const builders: Record<BuilderKey, (m: Materials) => BuiltObject> = {
  frcRobot,
  polyhedron,
  notebooks,
  devBoard,
  partsCrate,
};

export function buildObject(key: BuilderKey, m: Materials): BuiltObject {
  const built = builders[key](m);
  built.group.userData.meshes = mergeStatic(built.group);
  return built;
}
