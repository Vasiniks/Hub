import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import type { BuilderKey } from '../data/projects';
import type { Materials } from './materials';
import { mergeStatic } from './merge';
import type { Assets } from './assets';

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

const rb = (w: number, h: number, d: number, r = 0.004) =>
  new RoundedBoxGeometry(w, h, d, 2, Math.min(r, w / 2 - 1e-4, h / 2 - 1e-4, d / 2 - 1e-4));

/**
 * Team number as it is actually applied: white numerals on the bumper fabric, nothing behind
 * them. Transparent everywhere else, so the decal grid laid onto the fabric's curve in Blender
 * shows only the digits.
 */
function bumperNumber(text: string) {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 256;
  const ctx = c.getContext('2d')!;
  ctx.fillStyle = '#f4f4f2';
  ctx.font = '700 220px "IBM Plex Sans Condensed", system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 256, 138, 480);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  // glTF UVs run top-down.
  t.flipY = false;
  t.anisotropy = 4;
  return new THREE.MeshStandardMaterial({ map: t, roughness: 0.85, transparent: true, alphaTest: 0.35, depthWrite: false });
}

/**
 * §5/§31: a competition robot.
 *
 * Geometry from `assets/processed/robot.glb` (`blender/scripts/build_robot.py`). This used to
 * be rounded boxes with every detail faked on top — dark discs for lightening holes, boxes for
 * tread, a sign for the number. It is now built the way a robot is: hollow 2x1 and 1x1 tube
 * with holes bored through both walls, bumpers swept from the real plywood-and-noodle section
 * with mitred corners and the number laid onto the fabric, treaded swerve wheels with finned
 * motors, a pocketed PDH with seated breakers, and cable runs. The carriage and the signal
 * light are separate objects because they move.
 */
function frcRobot(m: Materials, assets: Assets): BuiltObject {
  const g = new THREE.Group();
  const model = assets.instance('robot');
  const rslMat = m.ledOrange.clone();
  assets.retint(model, {
    robot_alu: m.aluminum,
    robot_black: m.plasticBlack,
    robot_rubber: m.rubber,
    robot_bumper: m.bumperRed,
    robot_orange: m.safetyOrange,
    robot_white: m.plasticWhite,
    robot_grey: m.plasticGrey,
    robot_copper: m.copper,
    robot_red: m.bumperRed,
    robot_number: bumperNumber('0000'),
    robot_rsl: rslMat,
  });
  model.traverse((o) => {
    if (!(o instanceof THREE.Mesh)) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    // The decal sits a hair off the fabric; letting it cast would print the digits' shadow.
    o.castShadow = !mats.every((mat) => mat.transparent);
    o.receiveShadow = true;
  });
  g.add(model);
  // Two materials, so GLTFLoader makes the carriage a group of primitives, not a mesh.
  const carriage = model.getObjectByName('robot_carriage')!;
  carriage.userData.dynamic = true;

  return {
    group: g,
    tick(time, activity) {
      // Robot signal light: slow blink when idle, faster when examined.
      const rate = 1.0 + activity * 1.5;
      rslMat.emissiveIntensity = Math.sin(time * Math.PI * rate) > 0 ? 3.2 : 0.15;
      carriage.position.y = Math.sin(time * 0.5) * 0.004 * activity;
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
  // Spinning an open wire icosahedron changes its shadows but not the occlusion around it: AO
  // ignores its rotation (it still re-shadows as it turns).
  body.userData.aoIgnoresRotation = true;
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

function partsCrate(m: Materials, assets: Assets): BuiltObject {
  const g = new THREE.Group();
  // The workshop tote (build_bins.py) at crate size, in a darker plastic.
  const bin = new THREE.MeshStandardMaterial({ color: '#4a4f55', roughness: 0.7 });
  const tote = assets.instance('tote');
  tote.scale.set(1.44, 1.41, 1.33);
  assets.retint(tote, { bin_plastic: bin });
  tote.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) o.castShadow = o.receiveShadow = true;
  });
  g.add(tote);
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

const builders: Record<BuilderKey, (m: Materials, assets: Assets) => BuiltObject> = {
  frcRobot,
  polyhedron,
  notebooks,
  devBoard,
  partsCrate,
};

export function buildObject(key: BuilderKey, m: Materials, assets: Assets): BuiltObject {
  const built = builders[key](m, assets);
  built.group.userData.meshes = mergeStatic(built.group);
  return built;
}
