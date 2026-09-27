import * as THREE from 'three';
import type { Materials } from './materials';
import { mergeStatic } from './merge';
import { ROOM, DESK, CHAIR } from './layout';
import { at, rbox } from './build';
import { buildDeskSet, type DeskRefs } from './desk';
import type { Assets } from './assets';
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
 *
 * Frame, casing, sill, apron, reveal liners and skirting come from
 * `assets/processed/trim.glb` (`blender/scripts/build_furniture.py`) — stepped bars with
 * glazing beads, architrave casing, bullnose sill — in ROOM dimensions exactly. Floor, wall
 * slabs and glass stay procedural (set-fade, tiled PBR, image-lighting glass).
 */
function buildShell(root: THREE.Group, m: Materials, assets: Assets) {
  const trim = assets.instance('trim');
  assets.retint(trim, { trim_frame: m.windowFrame, trim_sill: m.sill, trim_wall: m.wall });
  trim.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) o.castShadow = o.receiveShadow = true;
  });
  root.add(trim);

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
  // Stops short of the opening: the sill caps this wall, and the two interpenetrate rather
  // than meeting face to face. Coplanar faces here were z-fighting into a blown white band
  // across the whole window.
  piece(-2.4, 4.4, 0, win.y0 - 0.02);
  piece(-2.4, 4.4, win.y1, wallTop);
  piece(-2.4, win.x0, win.y0, win.y1);
  piece(win.x1, 4.4, win.y0, win.y1);

  // Side walls: they bound the space, carry the bookshelf, and bounce light back at the desk.
  // Both dissolve toward the visitor rather than ending, so the set never shows an edge.
  at(rbox(ROOM.leftWallThickness, wallTop, 3.0, m.wall, 0.004), ROOM.leftWallX, wallTop / 2, -0.1, root);
  at(rbox(ROOM.leftWallThickness, wallTop, 3.0, m.wall, 0.004), ROOM.rightWallX, wallTop / 2, -0.1, root);

  // Frame: stepped bars with glazing beads, one mullion and one transom (in trim.glb),
  // so the opening reads as a window rather than as a hole, and throws a recognisable
  // shadow across the desk.
  const W = win.x1 - win.x0;
  const H = win.y1 - win.y0;
  const fx = (win.x0 + win.x1) / 2;
  const fy = (win.y0 + win.y1) / 2;
  const fz = wallZ - ROOM.frameInset;
  const t = 0.045;

  const glass = new THREE.Mesh(new THREE.PlaneGeometry(W - t * 2, H - t * 2), m.windowGlass);
  glass.position.set(fx, fy, fz + 0.012);
  glass.userData.noMerge = true;
  glass.userData.ignoreRaycast = true;
  glass.renderOrder = 2;
  root.add(glass);

  // Sill board + bullnose + beaded apron live in trim.glb (same planes as the old rboxes).

  return { windowGlass: glass, windowCenter: new THREE.Vector3(fx, fy, wallZ), windowSize: new THREE.Vector2(W, H) };
}

/**
 * The task chair. Geometry from `assets/processed/chair.glb` (`blender/scripts/build_chair.py`):
 * a contoured seat with a waterfall front, a lumbar-curved backrest that wraps round the
 * sitter, a tapered five-star base on twin-wheel casters. The origin is the gas lift, which is
 * what the sit-down animation rolls and turns it about.
 */
function buildChair(m: Materials, assets: Assets) {
  const chair = new THREE.Group();
  const model = assets.instance('chair');
  assets.retint(model, {
    chair_fabric: m.fabric,
    chair_plastic: m.plasticBlack,
    chair_metal: m.steel,
    chair_rubber: m.rubber,
  });
  model.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) o.castShadow = o.receiveShadow = true;
  });
  chair.add(model);
  return chair;
}

export function buildRoom(m: Materials, reducedMotion: boolean, assets: Assets): RoomRefs {
  const root = new THREE.Group();
  root.name = 'room';

  const shell = buildShell(root, m, assets);
  const desk = buildDeskSet(root, m, assets);
  const shelf = createBookshelf(root, m, reducedMotion, assets);

  const chairStart: ChairPose = { position: new THREE.Vector3(...CHAIR.start.position), rotationY: CHAIR.start.rotationY };
  const chairSeated: ChairPose = { position: new THREE.Vector3(...CHAIR.seated.position), rotationY: CHAIR.seated.rotationY };
  const chair = buildChair(m, assets);
  chair.userData.dynamic = true;
  chair.position.copy(chairStart.position);
  chair.rotation.y = chairStart.rotationY;
  root.add(chair);

  void DESK;
  root.userData.meshes = mergeStatic(root);
  return { root, chair, chairStart, chairSeated, shelf, ...shell, ...desk };
}
