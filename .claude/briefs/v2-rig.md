# Workstream: make the baked room walkable

Read `.claude/briefs/_common.md` first, then look at `/?v2` as it stands. Branch `ws/v2-rig`,
worktree `~/Documents/GitHub/hub-wt-v2rig`.

**The problem.** `?v2` renders the baked sunset room from one fixed camera. The visitor cannot
move, look, sit or do anything — it is a photograph. The default room's entire first-person
experience (stand → scroll to sit → mouse look, with limits and springs tuned over several passes)
already exists and `?v2` shares none of it.

**Your job.** Give `?v2` that same experience, by **reusing** the existing code — `src/camera/rig.ts`
above all — not by writing a second rig. If something in the rig assumes the old room's geometry,
make that part take the room's dimensions as input rather than forking the file.

## What you need to know

- `startV2` lives at the bottom of `src/main.ts`. It is deliberately separate from `start()` and
  shares only the camera constants. Keep that separation: the default room must stay byte-for-byte
  as it is, and `scripts/verify-room.mjs` must still pass on the default path.
- The baked room is 0.55 m wider than the procedural one (left wall −0.30, right wall +0.25) with a
  2.72 m ceiling. **Do not** edit `ROOM`/`SHELF` in `src/scene/layout.ts` to match — those drive the
  default room and changing them moves its walls. Give the v2 path its own dimensions.
- Camera poses come from the Blender scene: `CAM_seat` (0, −0.16, 1.175) and `CAM_stand`
  (1.06, −0.96, 1.63), Blender metres, Z-up. three.js `(x, y, z)` = Blender `(x, −z, y)`.
- The look spring is `stiffness = 6.0²`, `damping = 2 × 6.0` — a tuned value, not a placeholder.
- There are no interactive props in `?v2` yet (another workstream is exporting them), so picking,
  outlines and panels are **out of scope**. Movement, look limits, the sit transition and the
  standing/seated modes are in scope. Leave a clean seam where the props will plug in, and say in
  your report what that seam expects.

## Done means

- `/?v2` lets a visitor stand, look around with the mouse inside sensible limits, scroll to sit, and
  look around again from the seat — at 120 fps on the target Mac.
- Screenshots of standing, mid-sit and seated in your report.
- The default room is untouched: `verify-room`, `verify-a11y`, `verify-shelf`, `verify-gesture`,
  `verify-books`, `verify-motion` all green, no console errors.
- `npx tsc --noEmit -p .` clean. Report at `.claude/briefs/report-v2-rig.md`.
