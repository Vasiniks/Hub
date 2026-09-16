/**
 * Every dimension, position and limit that art direction is likely to move.
 *
 * Scene units are metres. The desk faces +z: the visitor stands and sits at +z
 * looking toward -z, into the desk and the window beyond it.
 *
 * Nothing here should need a rebuild of the scene to change — the builders read
 * these values, so moving an object is a one-line edit in this file.
 */

export const ROOM = {
  /** Inner face of the window wall. */
  wallZ: -1.3,
  wallDepth: 0.24,
  wallTop: 3.4,
  /** Solid side wall that carries the bookshelf. */
  leftWallX: -1.82,
  leftWallThickness: 0.08,
  /** The room needs a right-hand bound too, or a glance that way lands in the void. */
  rightWallX: 1.7,
  /** The opening, in wall-plane coordinates. Its sill sits just under desk height. */
  window: { x0: -1.32, x1: 1.02, y0: 0.7, y1: 2.5 },
  /** Frame depth inside the reveal, measured from the inner wall face. */
  frameInset: 0.11,
  floorRadius: 9,
};

export const DESK = {
  width: 2.04,
  depth: 0.78,
  /** Height of the work surface. */
  top: 0.735,
  thickness: 0.032,
  centerX: -0.02,
  centerZ: -0.74,
  /** How far the leg frames sit in from each end. */
  legInset: 0.13,
};

/** Desk-surface objects, left to right. Positions are world-space. */
export const DESKTOP = {
  monitor: { x: -0.05, z: -1.0, rotationY: 0.0, panelWidth: 0.62, panelHeight: 0.365 },
  macbook: { x: -0.06, z: -0.695, rotationY: 0.02, tilt: 0.2 },
  keyboard: { x: -0.05, z: -0.455, rotationY: 0.0 },
  mouse: { x: 0.33, z: -0.45, rotationY: -0.14 },
  lamp: { x: -0.72, z: -1.03, headRadius: 0.085 },
  cube: { x: -0.33, z: -0.62, rotationY: 0.42, size: 0.056 },
  mug: { x: -0.5, z: -0.5, rotationY: 0.5 },
};

/** Constrained first-person camera. Ranges are radians from the rest direction. */
/** Placement of the imported lamp asset. Its geometry is built in Blender. */
export const LAMP = {
  /**
   * Rotation about Y. The asset's beam leaves along -Z, so this is what turns the arm — and
   * therefore the light — toward the working half of the desk.
   */
  yaw: -2.19,
  scale: 0.92,
  /**
   * Where the medals hang, in the asset's own space: two points along the lower arm. Taken
   * from the build rather than from a bounding box, which put them out in the air.
   */
  medalFrom: [0.012, 0.17, -0.06] as [number, number, number],
  medalTo: [0.034, 0.40, -0.17] as [number, number, number],
};

export const CAMERA = {
  fov: 54,
  /** Narrower while examining an object: a gentle dolly rather than a jump cut. */
  focusFov: 45,
  stand: { position: [1.06, 1.63, 0.96], lookAt: [-0.3, 1.0, -0.95] },
  seat: { position: [0.0, 1.175, 0.16], lookAt: [-0.05, 1.03, -0.95] },
  /** [left, right] and [up, down] limits while standing. */
  standYaw: [0.32, 0.32] as [number, number],
  standPitch: [0.16, 0.12] as [number, number],
  /**
   * Seated. The left limit is set so that a full turn puts the bookshelf near the centre of
   * the frame rather than somewhere past it — the range is a framing decision, not a slack
   * allowance.
   */
  seatYaw: [1.08, 1.0] as [number, number],
  seatPitch: [0.72, 0.42] as [number, number],
  /** Fraction of the screen around the centre that does not turn the head. */
  deadZoneX: 0.3,
  deadZoneY: 0.28,
};

export const CHAIR = {
  start: { position: [0.42, 0, 0.3] as [number, number, number], rotationY: 0.85 },
  seated: { position: [0.02, 0, 0.08] as [number, number, number], rotationY: 0 },
};

export const SHELF = {
  /** Mounted on the left wall, running along it, facing into the room. */
  x: -1.72,
  y: 1.1,
  z: -0.8,
  width: 0.74,
  depth: 0.2,
  /** Gap between book spines in the row. */
  gap: 0.005,
  /**
   * How the selection reads: slide out, lift, turn the cover to camera. The row opens a real
   * gap for it — a turned book's cover swings a full book-depth to the right of its spine, so
   * the books on that side have to move out of the way or the cover ends up in front of them
   * with their bottoms showing underneath. `openLeft` is how much of that gap the left side
   * of the row (and the selection with it) gives; the right side gives the rest.
   */
  select: { out: 0.125, lift: 0.052, turn: 1.4, recede: 0.02, scale: 1.05, tilt: 0.1, openLeft: 0.05, clearance: 0.012 },
  /** Where the row starts, measured in from the shelf's left side panel. Leaves room to open left. */
  rowInset: 0.07,
  /**
   * §20: browsing advances exactly one book per committed gesture, however fast the input.
   * A flick accumulates past `threshold`, commits once, then disarms until the input has been
   * quiet for `restMs` — so a long fast swipe is one book, not five.
   */
  gesture: { threshold: 85, restMs: 90, minStepMs: 240, dragPx: 62 },
  /** Camera framing while browsing. */
  focus: { distance: 0.8, pitch: 0.1, offset: 0.12 },
};

export const INTERACTION = {
  /** Screen-space radius around an attention dot that counts as hovering its object. */
  dotRadiusPx: 30,
  /** Once hovered, an object stays hovered within this wider radius. */
  dotRetainPx: 64,
  /** Beyond dotRadiusPx, how far out the cursor still draws a response from a dot. */
  proximityPx: 130,
  /** Radius used around the centre of the frame while the view is turned to its limit. */
  centreRadiusPx: 260,
  /** Pointer travel that still counts as a click rather than a drag. */
  clickSlopPx: 6,
};

/** Dust motes drifting in the lamp beam. */
export const DUST = {
  count: 190,
  /** Half-extents of the box the motes drift inside, centred under the lamp head. */
  spread: [0.62, 0.52, 0.58] as [number, number, number],
  size: 1.7,
  drift: 0.012,
};
