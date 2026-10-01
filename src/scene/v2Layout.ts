import type { RigTuning } from '../camera/rig';
import { CAMERA } from './layout';

/**
 * The v2 baked room's own dimensions and camera tuning — deliberately separate from `ROOM`,
 * `SHELF` and `CAMERA` in `layout.ts`, which drive the default room and must not move while it
 * exists. (Kept out of `bakedRoom.ts`, which is about materials and the lightmap.)
 */

/**
 * Inner wall faces, three.js metres (x right, y up, z toward the visitor), measured from the
 * shell atlas (`rs_wall_*`, `rs_ceiling` bounds in `public/assets/v2/room/shell.glb`). The rig
 * does not read these — it needs only its poses and limits — but anything placed in the v2 room
 * (props, the exterior, debug cameras) should take its bounds from here, not from `ROOM`.
 */
export const V2_ROOM = {
  leftWallX: -2.08,
  rightWallX: 1.91,
  windowWallZ: -1.3,
  backWallZ: 1.4,
  ceilingY: 2.72,
} as const;

/**
 * v2 tuning for `CameraRig`. The poses are the Blender scene's `CAM_stand` and `CAM_seat`
 * (three.js `(x, y, z)` = Blender `(x, −z, y)`); their view directions, read from
 * `room_public.blend` — CAM_seat forward (−0.0446, 0.9906, −0.1294), CAM_stand (−0.5602, 0.7867,
 * −0.2595), both 54° vertical — are exactly the default room's tuned lookAts, so those are reused
 * as-is. The look limits, dead zone, spring (in rig.ts) and lenses are the default room's tuned
 * values, with one change: looking down from the seat stops at 0.55 rad instead of 0.72. The
 * baked room has no chair and no legs under the desk to look at, and the extra 10° only showed
 * the floor under the desk.
 *
 * There is no chair in the v2 room at all (none in the bake, none among the props), so `startV2`
 * passes `null` for the rig's chair and the sit transition moves the camera only. When a chair
 * prop lands, pass it as the rig's `SitChair` and it rolls in exactly as in the default room.
 */
export const V2_TUNING: RigTuning = {
  fov: CAMERA.fov,
  focusFov: CAMERA.focusFov,
  // Blender CAM_stand (1.06, −0.96, 1.63) → three (1.06, 1.63, 0.96).
  stand: { position: [1.06, 1.63, 0.96], lookAt: [...CAMERA.stand.lookAt] as [number, number, number] },
  // Blender CAM_seat (0, −0.16, 1.175) → three (0, 1.175, 0.16).
  seat: { position: [0, 1.175, 0.16], lookAt: [...CAMERA.seat.lookAt] as [number, number, number] },
  standYaw: [...CAMERA.standYaw] as [number, number],
  seatYaw: [...CAMERA.seatYaw] as [number, number],
  standPitch: [...CAMERA.standPitch] as [number, number],
  // [down, up] as the rig reads it (a pointer below centre turns the head by the first value).
  seatPitch: [0.55, CAMERA.seatPitch[1]],
  deadZoneX: CAMERA.deadZoneX,
  deadZoneY: CAMERA.deadZoneY,
};
