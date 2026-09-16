import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import type { Materials } from './materials';
import { mergeStatic } from './merge';

/** Scene units are metres. Desk faces +z; the visitor sits at +z looking toward -z. */

export interface ChairPose {
  position: THREE.Vector3;
  rotationY: number;
}

export interface RoomRefs {
  root: THREE.Group;
  chair: THREE.Group;
  chairStart: ChairPose;
  chairSeated: ChairPose;
  mainScreen: THREE.Mesh;
  sideScreen: THREE.Mesh;
  mainScreenCenter: THREE.Vector3;
  lampBulb: THREE.Mesh;
  lampSocket: THREE.Object3D;
  lampTarget: THREE.Object3D;
  fans: THREE.Object3D[];
  pcLeds: THREE.Mesh[];
  windowGlass: THREE.Mesh;
  windowCenter: THREE.Vector3;
  windowSize: THREE.Vector2;
}

function shadowed<T extends THREE.Object3D>(o: T, cast = true, receive = true): T {
  o.traverse((c) => {
    if ((c as THREE.Mesh).isMesh) {
      c.castShadow = cast;
      c.receiveShadow = receive;
    }
  });
  return o;
}

function rbox(w: number, h: number, d: number, mat: THREE.Material, r = 0.006) {
  const radius = Math.min(r, w / 2 - 1e-4, h / 2 - 1e-4, d / 2 - 1e-4);
  return shadowed(new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 2, radius), mat));
}

function at<T extends THREE.Object3D>(o: T, x: number, y: number, z: number, parent?: THREE.Object3D): T {
  o.position.set(x, y, z);
  parent?.add(o);
  return o;
}

function rod(from: THREE.Vector3, to: THREE.Vector3, radius: number, mat: THREE.Material) {
  const len = from.distanceTo(to);
  const mesh = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, len, 10), mat));
  mesh.position.copy(from).lerp(to, 0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), to.clone().sub(from).normalize());
  return mesh;
}

function buildShell(root: THREE.Group, m: Materials) {
  const floor = new THREE.Mesh(new THREE.CircleGeometry(9, 64), m.floor);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  root.add(floor);

  const rug = at(new THREE.Mesh(new THREE.CylinderGeometry(0.82, 0.82, 0.006, 48), m.rug), 0.05, 0.003, -0.02, root);
  rug.receiveShadow = true;

  // Back wall: the desk faces a large window. The wall is thick so the opening has a real
  // reveal that catches light; it runs on into the void so the exterior only reads through glass.
  const wallZ = -1.12;
  const depth = 0.24;
  const cz = wallZ - depth / 2;
  const win = { x0: -1.05, x1: 0.95, y0: 0.92, y1: 2.42 };
  const piece = (x0: number, x1: number, y0: number, y1: number) =>
    at(rbox(x1 - x0, y1 - y0, depth, m.wall, 0.004), (x0 + x1) / 2, (y0 + y1) / 2, cz, root);
  piece(-2.0, 4.2, 0, win.y0);
  piece(-2.0, 4.2, win.y1, 3.4);
  piece(-2.0, win.x0, win.y0, win.y1);
  piece(win.x1, 4.2, win.y0, win.y1);

  // Left wall, now solid: it bounds the space and receives bounce light.
  at(rbox(0.08, 3.4, 2.6, m.wall, 0.004), -1.8, 1.7, -0.02, root);

  // Slim dark frame at mid-reveal, with a mullion and a transom.
  const W = win.x1 - win.x0;
  const H = win.y1 - win.y0;
  const fx = (win.x0 + win.x1) / 2;
  const fy = (win.y0 + win.y1) / 2;
  const fz = wallZ - 0.11;
  const t = 0.045;
  const bar = (w: number, h: number, x: number, y: number) => at(rbox(w, h, 0.06, m.windowFrame, 0.004), x, y, fz, root);
  bar(W, t, fx, win.y0 + t / 2);
  bar(W, t, fx, win.y1 - t / 2);
  bar(t, H, win.x0 + t / 2, fy);
  bar(t, H, win.x1 - t / 2, fy);
  bar(t * 0.7, H - t * 2, fx, fy);
  bar(W - t * 2, t * 0.7, fx, win.y1 - 0.42);

  const glass = new THREE.Mesh(new THREE.PlaneGeometry(W - t * 2, H - t * 2), m.windowGlass);
  glass.position.set(fx, fy, fz + 0.01);
  glass.userData.noMerge = true;
  glass.renderOrder = 2;
  root.add(glass);

  at(rbox(W + 0.14, 0.03, 0.2, m.sill, 0.006), fx, win.y0 - 0.015, wallZ - 0.05, root);

  return { windowGlass: glass, windowCenter: new THREE.Vector3(fx, fy, wallZ), windowSize: new THREE.Vector2(W, H) };
}

function buildDesk(root: THREE.Group, m: Materials) {
  at(rbox(1.6, 0.035, 0.72, m.deskTop, 0.008), 0, 0.7225, -0.72, root);
  for (const x of [-0.74, 0.74]) {
    at(rbox(0.06, 0.03, 0.64, m.steel, 0.008), x, 0.015, -0.72, root);
    at(rbox(0.06, 0.675, 0.05, m.steel, 0.006), x, 0.3675, -0.72, root);
    at(rbox(0.05, 0.03, 0.6, m.steel, 0.006), x, 0.69, -0.72, root);
  }
  at(rbox(1.42, 0.05, 0.025, m.steel, 0.006), 0, 0.64, -1.0, root);

  // Desk mat, keyboard, mouse
  at(rbox(0.82, 0.003, 0.34, m.fabric, 0.0015), 0.06, 0.7415, -0.53, root);
  const kb = at(rbox(0.36, 0.016, 0.125, m.plasticGrey, 0.004), -0.06, 0.751, -0.52, root);
  const keyGeo = new RoundedBoxGeometry(0.0165, 0.009, 0.0165, 1, 0.002);
  const keys = new THREE.InstancedMesh(keyGeo, m.plasticBlack, 5 * 15);
  const dummy = new THREE.Object3D();
  let i = 0;
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 15; col++) {
      dummy.position.set(-0.154 + col * 0.022, 0.012, -0.046 + row * 0.023);
      if (row === 4 && col > 4 && col < 10) dummy.scale.set(col === 7 ? 5.8 : 0, 1, 1);
      else dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      keys.setMatrixAt(i++, dummy.matrix);
    }
  }
  keys.castShadow = keys.receiveShadow = true;
  kb.add(keys);
  const mouse = at(rbox(0.062, 0.032, 0.105, m.plasticBlack, 0.014), 0.32, 0.758, -0.5, root);
  mouse.rotation.y = -0.12;

  // Mug
  const mug = at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.037, 0.095, 24, 1, true), m.plasticWhite)), -0.34, 0.788, -0.8, root);
  mug.add(at(shadowed(new THREE.Mesh(new THREE.CircleGeometry(0.037, 24), m.plasticWhite)), 0, -0.047, 0).rotateX(-Math.PI / 2));
  const handle = shadowed(new THREE.Mesh(new THREE.TorusGeometry(0.024, 0.006, 8, 16, Math.PI), m.plasticWhite));
  handle.rotation.z = -Math.PI / 2;
  at(handle, 0.04, 0, 0, mug);
}

function buildMonitors(root: THREE.Group, m: Materials) {
  const screenMat = () =>
    new THREE.MeshStandardMaterial({ color: '#040506', roughness: 0.3, envMapIntensity: 0.35, emissive: '#ffffff', emissiveIntensity: 1 });

  const main = new THREE.Group();
  at(main, -0.04, 0, -0.93, root);
  at(rbox(0.26, 0.012, 0.17, m.aluminum, 0.005), 0, 0.746, 0.02, main);
  at(rbox(0.045, 0.34, 0.025, m.aluminum, 0.006), 0, 0.9, -0.02, main);
  const panel = at(rbox(0.66, 0.39, 0.032, m.plasticBlack, 0.006), 0, 1.075, 0.0, main);
  panel.rotation.x = -0.04;
  const mainScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.64, 0.36), screenMat());
  at(mainScreen, 0, 0.008, 0.0165, panel);

  const side = new THREE.Group();
  at(side, 0.68, 0, -0.8, root);
  side.rotation.y = -0.52;
  at(rbox(0.2, 0.012, 0.14, m.aluminum, 0.005), 0, 0.746, 0.02, side);
  at(rbox(0.04, 0.3, 0.022, m.aluminum, 0.006), 0, 0.88, -0.02, side);
  const sidePanel = at(rbox(0.54, 0.325, 0.03, m.plasticBlack, 0.006), 0, 1.035, 0, side);
  const sideScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.52, 0.295), screenMat());
  at(sideScreen, 0, 0.006, 0.0155, sidePanel);

  // Cable from the main monitor down behind the desk
  const cable = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-0.04, 0.95, -0.98),
    new THREE.Vector3(-0.02, 0.76, -1.04),
    new THREE.Vector3(0.1, 0.72, -1.1),
    new THREE.Vector3(0.28, 0.3, -1.1),
    new THREE.Vector3(0.45, 0.02, -1.02),
  ]);
  root.add(shadowed(new THREE.Mesh(new THREE.TubeGeometry(cable, 40, 0.006, 6), m.rubber)));

  main.updateMatrixWorld(true);
  const mainScreenCenter = new THREE.Vector3();
  mainScreen.getWorldPosition(mainScreenCenter);
  return { mainScreen, sideScreen, mainScreenCenter };
}

function buildLamp(root: THREE.Group, m: Materials) {
  const lamp = at(new THREE.Group(), -0.66, 0.74, -0.97, root);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.075, 0.02, 32), m.steel)), 0, 0.01, 0, lamp);
  const j1 = new THREE.Vector3(0, 0.02, 0);
  const j2 = new THREE.Vector3(0.05, 0.4, 0.06);
  const j3 = new THREE.Vector3(0.22, 0.56, 0.22);
  lamp.add(rod(j1, j2, 0.008, m.steel), rod(j2, j3, 0.007, m.steel));
  const head = at(new THREE.Group(), j3.x, j3.y, j3.z, lamp);
  head.lookAt(-0.16, 0.74, -0.62);
  const shade = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.075, 0.12, 28, 1, true), m.steel));
  shade.rotation.x = Math.PI / 2;
  // Own copy: making the shared steel double-sided would double-draw every steel surface.
  const shadeMat = (shade.material as THREE.MeshStandardMaterial).clone();
  shadeMat.side = THREE.DoubleSide;
  shade.material = shadeMat;
  head.add(shade);
  const bulbMat = new THREE.MeshStandardMaterial({ color: '#000000', emissive: '#ffd6a0', emissiveIntensity: 4 });
  const bulb = at(new THREE.Mesh(new THREE.SphereGeometry(0.026, 16, 12), bulbMat), 0, 0, 0.02, head);
  const socket = at(new THREE.Object3D(), 0, 0, 0.05, head);
  const target = at(new THREE.Object3D(), 0, 0, 1, head);
  return { lampBulb: bulb, lampSocket: socket, lampTarget: target };
}

function buildTower(root: THREE.Group, m: Materials) {
  const tower = at(new THREE.Group(), 0.5, 0, -0.86, root);
  tower.rotation.y = -0.08;
  at(rbox(0.22, 0.46, 0.44, m.plasticBlack, 0.01), 0, 0.245, 0, tower);
  for (const [x, z] of [[-0.08, -0.17], [0.08, -0.17], [-0.08, 0.17], [0.08, 0.17]]) {
    at(rbox(0.035, 0.015, 0.035, m.rubber, 0.004), x, 0.0075, z, tower);
  }
  const front = at(rbox(0.2, 0.42, 0.006, m.glass, 0.002), 0, 0.245, 0.222, tower);
  front.castShadow = false;
  const fans: THREE.Object3D[] = [];
  const pcLeds: THREE.Mesh[] = [];
  for (const y of [0.33, 0.16]) {
    const ring = at(shadowed(new THREE.Mesh(new THREE.TorusGeometry(0.068, 0.006, 8, 32), m.plasticGrey)), 0, y, 0.214, tower);
    const blades = new THREE.Group();
    for (let b = 0; b < 7; b++) {
      const blade = new THREE.Mesh(new THREE.BoxGeometry(0.058, 0.018, 0.003), m.plasticGrey);
      blade.position.x = 0.032;
      blade.rotation.x = 0.5;
      const pivot = new THREE.Group();
      pivot.rotation.z = (b / 7) * Math.PI * 2;
      pivot.add(blade);
      blades.add(pivot);
    }
    blades.userData.dynamic = true;
    ring.add(blades);
    fans.push(blades);
  }
  const strip = at(new THREE.Mesh(new THREE.BoxGeometry(0.004, 0.36, 0.004), m.ledWhite.clone()), -0.098, 0.245, 0.221, tower);
  pcLeds.push(strip);
  const power = at(new THREE.Mesh(new THREE.CircleGeometry(0.005, 12), m.ledWhite.clone()), 0.08, 0.44, 0.223, tower);
  pcLeds.push(power);
  return { fans, pcLeds };
}

function buildShelf(root: THREE.Group, m: Materials) {
  // On the left wall now, running along it and facing into the room.
  const shelf = at(new THREE.Group(), -1.66, 1.42, -0.5, root);
  shelf.rotation.y = Math.PI / 2;
  at(rbox(0.92, 0.025, 0.2, m.deskTop, 0.004), 0, 0, 0, shelf);
  const tones = ['#3b4149', '#6d6f73', '#2c3a33', '#8a8d91', '#44403c', '#505760'].map(
    (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.85 }),
  );
  let x = -0.4;
  for (let i = 0; i < 9; i++) {
    const h = 0.17 + ((i * 37) % 7) * 0.012;
    const w = 0.022 + ((i * 13) % 4) * 0.007;
    const book = at(rbox(w, h, 0.15, tones[i % tones.length], 0.002), x + w / 2, 0.0125 + h / 2, 0, shelf);
    if (i === 8) book.rotation.z = -0.28;
    x += w + 0.003;
  }
  at(rbox(0.14, 0.09, 0.12, m.plasticWhite, 0.008), 0.2, 0.0575, 0.0, shelf);
  at(rbox(0.08, 0.14, 0.08, m.plasticBlack, 0.01), 0.36, 0.0825, 0.01, shelf);
}

function buildChair(m: Materials) {
  const chair = new THREE.Group();
  const base = new THREE.Group();
  for (let i = 0; i < 5; i++) {
    const arm = new THREE.Group();
    arm.rotation.y = (i / 5) * Math.PI * 2;
    at(rbox(0.3, 0.028, 0.045, m.plasticBlack, 0.01), 0.15, 0.075, 0, arm);
    at(shadowed(new THREE.Mesh(new THREE.SphereGeometry(0.026, 12, 8), m.rubber)), 0.29, 0.026, 0, arm);
    base.add(arm);
  }
  chair.add(base);
  at(shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.03, 0.34, 16), m.steel)), 0, 0.25, 0, chair);
  at(rbox(0.5, 0.075, 0.48, m.fabric, 0.03), 0, 0.46, 0, chair);
  at(rbox(0.36, 0.025, 0.3, m.plasticBlack, 0.01), 0, 0.41, 0, chair);
  const back = at(new THREE.Group(), 0, 0.5, 0.235, chair);
  back.rotation.x = 0.1;
  at(rbox(0.05, 0.3, 0.025, m.plasticBlack, 0.01), 0, 0.12, 0.02, back);
  at(rbox(0.46, 0.56, 0.065, m.fabric, 0.03), 0, 0.46, 0, back);
  for (const x of [-0.27, 0.27]) {
    at(rbox(0.03, 0.2, 0.04, m.plasticBlack, 0.01), x, 0.55, 0.06, chair);
    at(rbox(0.07, 0.025, 0.25, m.plasticBlack, 0.01), x, 0.66, 0.02, chair);
  }
  return chair;
}

export function buildRoom(m: Materials): RoomRefs {
  const root = new THREE.Group();
  root.name = 'room';

  const shell = buildShell(root, m);
  buildDesk(root, m);
  const monitors = buildMonitors(root, m);
  const lamp = buildLamp(root, m);
  const tower = buildTower(root, m);
  buildShelf(root, m);

  const chairStart: ChairPose = { position: new THREE.Vector3(0.36, 0, 0.26), rotationY: 0.85 };
  const chairSeated: ChairPose = { position: new THREE.Vector3(0.0, 0, 0.06), rotationY: 0 };
  const chair = buildChair(m);
  chair.userData.dynamic = true;
  chair.position.copy(chairStart.position);
  chair.rotation.y = chairStart.rotationY;
  root.add(chair);

  root.userData.meshes = mergeStatic(root);
  return { root, chair, chairStart, chairSeated, ...shell, ...monitors, ...lamp, ...tower };
}
