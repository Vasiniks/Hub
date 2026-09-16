import * as THREE from 'three';
import type { Materials } from './materials';
import { mergeStatic } from './merge';
import { ROOM, DESK, CHAIR } from './layout';
import { at, rbox, shadowed } from './build';
import { buildDeskSet, type DeskRefs } from './desk';
import { createBookshelf, type Bookshelf } from './bookshelf';

/** Scene units are metres. The desk faces +z; the visitor sits at +z looking toward -z. */

export interface ChairPose {
  position: THREE.Vector3;
  rotationY: number;
}

export interface RoomRefs extends DeskRefs {
  root: THREE.Group;
  chair: THREE.Group;
  chairStart: ChairPose;
  chairSeated: ChairPose;
  windowGlass: THREE.Mesh;
  windowCenter: THREE.Vector3;
  windowSize: THREE.Vector2;
  shelf: Bookshelf;
}

/**
 * §8: the window sits directly in front of the monitor, in the wall the desk faces.
 * The wall is thick, so the opening has a real reveal that catches raking light, and it runs
 * on well past the set so the exterior is only ever seen through the glass.
 */
function buildShell(root: THREE.Group, m: Materials) {
  const floor = new THREE.Mesh(new THREE.CircleGeometry(ROOM.floorRadius, 56), m.floor);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  root.add(floor);

  const rug = at(new THREE.Mesh(new THREE.CylinderGeometry(0.88, 0.88, 0.006, 40), m.rug), 0.06, 0.003, 0.05, root);
  rug.receiveShadow = true;

  const { wallZ, wallDepth, wallTop, window: win } = ROOM;
  const cz = wallZ - wallDepth / 2;
  const piece = (x0: number, x1: number, y0: number, y1: number) =>
    at(rbox(x1 - x0, y1 - y0, wallDepth, m.wall, 0.004), (x0 + x1) / 2, (y0 + y1) / 2, cz, root);
  piece(-2.4, 4.4, 0, win.y0);
  piece(-2.4, 4.4, win.y1, wallTop);
  piece(-2.4, win.x0, win.y0, win.y1);
  piece(win.x1, 4.4, win.y0, win.y1);

  // Side walls: they bound the space, carry the bookshelf, and bounce light back at the desk.
  // Both dissolve toward the visitor rather than ending, so the set never shows an edge.
  at(rbox(ROOM.leftWallThickness, wallTop, 3.0, m.wall, 0.004), ROOM.leftWallX, wallTop / 2, -0.1, root);
  at(rbox(ROOM.leftWallThickness, wallTop, 3.0, m.wall, 0.004), ROOM.rightWallX, wallTop / 2, -0.1, root);

  // Frame: slim bars at mid-reveal with one mullion and one transom, so the opening reads
  // as a window rather than as a hole, and throws a recognisable shadow across the desk.
  const W = win.x1 - win.x0;
  const H = win.y1 - win.y0;
  const fx = (win.x0 + win.x1) / 2;
  const fy = (win.y0 + win.y1) / 2;
  const fz = wallZ - ROOM.frameInset;
  const t = 0.045;
  const bar = (w: number, h: number, x: number, y: number) => at(rbox(w, h, 0.06, m.windowFrame, 0.004), x, y, fz, root);
  bar(W, t, fx, win.y0 + t / 2);
  bar(W, t, fx, win.y1 - t / 2);
  bar(t, H, win.x0 + t / 2, fy);
  bar(t, H, win.x1 - t / 2, fy);
  bar(t * 0.7, H - t * 2, fx, fy);
  bar(W - t * 2, t * 0.7, fx, win.y1 - 0.46);

  const glass = new THREE.Mesh(new THREE.PlaneGeometry(W - t * 2, H - t * 2), m.windowGlass);
  glass.position.set(fx, fy, fz + 0.012);
  glass.userData.noMerge = true;
  glass.userData.ignoreRaycast = true;
  glass.renderOrder = 2;
  root.add(glass);

  // Sill, and a deep reveal board below it: both catch direct sun and read as bright edges.
  at(rbox(W + 0.16, 0.032, 0.22, m.sill, 0.006), fx, win.y0 - 0.016, wallZ - 0.06, root);
  at(rbox(W + 0.1, 0.05, 0.03, m.sill, 0.004), fx, win.y0 - 0.055, wallZ + 0.03, root);

  return { windowGlass: glass, windowCenter: new THREE.Vector3(fx, fy, wallZ), windowSize: new THREE.Vector2(W, H) };
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

export function buildRoom(m: Materials, reducedMotion: boolean): RoomRefs {
  const root = new THREE.Group();
  root.name = 'room';

  const shell = buildShell(root, m);
  const desk = buildDeskSet(root, m);
  const shelf = createBookshelf(root, m, reducedMotion);

  const chairStart: ChairPose = { position: new THREE.Vector3(...CHAIR.start.position), rotationY: CHAIR.start.rotationY };
  const chairSeated: ChairPose = { position: new THREE.Vector3(...CHAIR.seated.position), rotationY: CHAIR.seated.rotationY };
  const chair = buildChair(m);
  chair.userData.dynamic = true;
  chair.position.copy(chairStart.position);
  chair.rotation.y = chairStart.rotationY;
  root.add(chair);

  void DESK;
  root.userData.meshes = mergeStatic(root);
  return { root, chair, chairStart, chairSeated, shelf, ...shell, ...desk };
}
