# Workstream report: furniture remodel (ws/model-furniture)

Date: 2026-09-27. Branch `ws/model-furniture`. Dev server `http://127.0.0.1:5195` (vite).
Blender 5.0.1 CLI at `~/.local/bin/blender` (`--background --factory-startup --python`).
All temp files in `./tmp/` (never `/tmp`); repo temps (`tmp/`, `node_modules`, `.serena/`) NOT committed.

## Baseline (before)

- Chair: `assets/processed/chair.glb` 195.5 KB (public 118.8 KB), **6620 tris** (Blender `inspect.py`:
  single mesh `chair`, mats `chair_plastic/chair_rubber/chair_metal/chair_fabric`, dims 0.619x0.697x1.120).
- Desk/shelf/shell: procedural (`desk.ts` rbox, `bookshelf.ts` rbox, `room.ts` rbox) — no GLB.
- Screenshots: `tmp/base-furniture/` h13/h21 standing + seated + look-left/right, no errors.
- Frame (`VIEWPORT=1728x1000`, pr 1.5, hour 21, fence-timed `bench-ab`, 2 rounds, hot machine):
  pose0 (seated at desk) look 6.51 / idle 5.79; pose1 look 6.83 / idle 5.69; pose2 look 6.24 / idle 5.14.
  Budget: seated frame < ~6 ms (interleaved A/B, both orders). Baseline is at/over budget hot;
  LOG cool was ~5.0 ms. Headroom comes from the second rendering pass, not from geometry.
- Seated scene: ~131k tris (perf LOG).

## Plan

One script `blender/scripts/build_furniture.py` builds all four groups into one scene with four
collections (Chair/Desk/Shelf/Trim), saves `blender/source/furniture.blend` (render-ready: 4 cameras,
3-point lights, `//render/` output), exports `chair/desk/shelf/trim.glb` + sidecars to
`assets/processed/`, then `node scripts/optimize-glb.mjs`. Dimensions match `layout.ts` exactly —
no layout change, all interaction verifies keep passing. All geometry modelled from scratch
(no third-party geometry; no MANIFEST licence rows needed beyond noting the script).

Per-object budgets: chair ~13k (was 6.6k), desk ~8k (replaces ~6k procedural), shelf ~5k
(replaces ~3k), trim ~7k (new). Net seated ~131k → ~150k, well under the ~300k ceiling.

## 1. Chair — done, committed

Rebuilt in `blender/scripts/build_furniture.py::build_chair` (same frame as `build_chair.py`:
origin on the gas-lift axis, casters on z=0, front +Y, so `room.ts`/sit animation untouched).
Same 4 material names (`chair_fabric/plastic/metal/rubber`) so the retint is unchanged —
zero runtime code change, GLB-only swap.

What changed: 5-star die-cast base with top stiffening ribs + metal trim ring/cap (was plain
tapered arms + hub); casters with real yoke forks, axle + bolt heads, rounded-tread twin
wheels on a trailing stem (was bare tube wheels); telescoping 3-stage gas lift (shroud +
sleeve + chrome piston); tilt housing with side caps, tension knob with stem, height/back-lock
levers with paddles, seat slider rails; seat cushion with side bolsters + piping cord; backrest
with bolstered top, rear shell with carry-handle slot + 5 stiffening ribs, separate lumbar pad
on its own bracket with height knob; height-adjustable armrests (rail + sleeve + slide + button)
with dished pads. Cushion grids n=11, rim bevel 2 seg. Every part UV-unwrapped + `Lightmap`
channel reserved.

Measured: **6620 → 13846 tris** (+7.2k, budget was ~13k); bounds (±0.319, -0.395..0.302, 0..1.12)
vs old (0.619x0.697x1.120) — same footprint, no layout impact. Files: `assets/processed/chair.glb`
195.5 → 727 KB source, `public/` 118.8 → 276.9 KB (+158 KB). Sidecar `chair.json` (seatHeight 0.51).
`blender/source/furniture.blend` + `render/preview_chair_.png` saved from the same script run.

Fixes after looking: first build was 18810 tris with wild bounds (z min −0.30) — cone transforms
used `R @ T` (rotates the placed position about the origin); corrected to `T @ R`, trimmed
piping curve resolution (the 2.5k-tri hog), arm/rib steps and hub segments → 13846. Rear ribs
floated as slats → sunk to beads; lumbar knob stuck out → tucked; yoke plates hid the wheels →
shrunk/raised so twin wheels read.

Verifies (port 5195, hour 21 unless noted): `tsc` clean; `verify-room` ERRORS []; `verify-shelf`
errors []; `verify-gesture` PASS; `verify-books` PASS; `verify-motion` errors [];
`verify-ao-motion` idle 121/121 full, moving 87/109 half, settle back; `verify-a11y` PASS;
`verify-shelf-a11y` focusRestored Bookshelf; `compile-watch 13` → 76 programs after load
(baseline chair re-measured on this machine: also 76 — the old report's 70 is stale, no
regression from this chair). Screenshots: `tmp/chair-new2/` close-ups h13/h21 (front/rear/base,
no errors), `tmp/chair-final/` standing+seated h13/h21. Standing view: seat edge + armrest pad
now catch light instead of a black slab. Seated view unchanged (chair out of frame).

Frame cost: deferred to the final interleaved A/B (chair is frustum-culled seated; standing cost
scales with pixels, geometry +7k is ~5% of the scene).

## 2. Desk
(TODO)

## 3. Shelf
(TODO)

## 4. Room shell trim
(TODO)

## Final numbers
(TODO)
