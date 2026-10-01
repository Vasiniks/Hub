# Workstream: the baked sunset room in the runtime

Read `.claude/briefs/_common.md` first, then `blender/bake/sunset/README.md` end to end. That README
is the spec. Branch `ws/web-shell`, worktree `~/Documents/GitHub/hub-wt-shell`.

**Goal.** The baked sunset room — shell, desk, furniture, curtains — rendering in the three.js
runtime behind `?v2`, lit entirely by its lightmaps, at a frame cost you have measured. Nothing
else: the props, the exterior and the interactions are other people's workstreams. Do not touch
`blender/`, `public/assets/v2/props/` or `public/assets/v2/exterior/`.

## What you are given

`blender/bake/sunset/` — four atlas GLBs (`shell` 5.3k tris, `desk` 9.4k, `furniture` 3.9k,
`soft` 81k), four `lightmap_<atlas>.rgbm.png`, and `manifest.json` with `range_sqrt` per atlas.
The GLBs are world-space, glTF Y-up, `TEXCOORD_0` = original UV, `TEXCOORD_1` = lightmap UV.

## The work

1. **Get the GLBs into `public/assets/v2/room/` with `TEXCOORD_1` intact.** `scripts/optimize-glb.mjs`
   currently drops extra attributes: `prune()` needs `{ keepAttributes: true }`. That exact fix is on
   branch `ws/lightmaps`, commit `e61413e` — read it, port it, and then **prove** TEXCOORD_1 survived
   by reading the written GLB back and printing the attribute list per primitive. If quantisation
   damages the lightmap UV, give that channel more bits or leave it unquantised, and say which.
2. **Load the lightmaps exactly as the README says**: `flipY = false`, `colorSpace = NoColorSpace`,
   `premultiplyAlpha = false`, `LinearFilter`, the RGBM decode patched into the lightmap fetch with
   `range_sqrt` from the manifest, `tex.channel = 1`, `lightMapIntensity = Math.PI`.
3. **Do not double-light.** The bake already holds the sun, the sky, the lamp and every bounce. Baked
   surfaces must not also receive the live sun, lamp, hemisphere or environment *diffuse*. three.js
   cannot exclude a light per mesh, so decide and justify: either the baked meshes get a material
   that ignores lights (lightmap + optional env specular), or those lights leave the v2 scene
   entirely. Specular is not in the bake — semigloss trim, desk laminate and the window frame either
   keep an env-map reflection or go matte. Say which you chose and show it.
4. **Grade.** Blender was AgX, look "Medium High Contrast", exposure +0.45 EV. Use
   `AgXToneMapping` with `toneMappingExposure = 2 ** 0.45` and compare against
   `blender/bake/sunset/compare_CAM_seat.png` and `compare_CAM_stand.png`. Those are Cycles
   references for the same two camera poses — put your screenshot beside each and report what
   differs. Blender metres are Z-up; three.js `(x, y, z)` = Blender `(x, -z, y)`. Cameras:
   `CAM_seat` (0, -0.16, 1.175), `CAM_stand` (1.06, -0.96, 1.63).
5. **Room dimensions.** The new shell is 0.55 m wider (left wall −0.30, right wall +0.25) with a
   2.72 m ceiling. `src/scene/layout.ts` (`ROOM.leftWallX`, `rightWallX`, `SHELF.x`) and anything
   deriving from them — area-light volumes, AO snapshot bounds — must match the baked geometry, or
   the old room's furniture will intersect the new walls.
6. **`?v2` is a flag, not a replacement.** Default stays today's room until the owner signs off.
   Keep both paths working; `?v2` must not slow the default path down.
7. **The curtains are over budget and you must not quietly fix them.** `soft.glb` is 81k tris of
   two curtains, 55% of the baked room. Decimating them destroys the atlas UV they were baked
   against, so do not. Measure what they cost, and if they do not fit the budget, write the number
   down and propose a re-bake from a lighter cage. That is a correct outcome, not a failure.

## Done means

- `?v2` shows the baked sunset room, and a screenshot of each of the two reference poses is in your
  report next to its Cycles comparison.
- Fence-timed cost through `window.__room.bench(pose)`, seated and standing, against the default
  room, interleaved both orders (`scripts/bench-ab.mjs`) — this machine drifts ~50% cool to hot, so
  a single pair proves nothing.
- `npx tsc --noEmit -p .` clean; every `scripts/verify-*.mjs` green with no console errors, run with
  `ROOM_URL` pointed at your own port.
- Report at `.claude/briefs/report-web-shell.md`: what you wired, the measured numbers, what you
  rejected and why, and what the next workstream needs from you.
