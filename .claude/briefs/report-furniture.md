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

## 2. Desk — done, committed

Built in `build_furniture.py::build_desk`, local frame origin on the floor under the desk
centre, +Y = back (exports to world −Z, the window side), every dimension copied from
`layout.ts` DESK (W 2.04, D 0.78, top 0.735, T 0.032, legInset 0.13) — no layout change.
5 materials (`desk_white/edge/steel/dark/rubber`) retinted to the room palette in `desk.ts`;
the old procedural `buildDesk` (slab + rail + 2 leg groups + tray rboxes) is replaced by one
`assets.instance('desk')` at (centerX, 0, centerZ). The cable-bundle curve stays code.
`main.ts` loads `desk.glb`.

What it adds over the slab: 32 mm top with a real 4 mm edge break + darker edge band
(assign_slot by normal); front/back apron rails; T leg frames — tapered feet, weld collars,
columns, top brackets with 4 screws each, levelling glides (stem + disc); perforated cable
tray (12 real boolean slots); articulated 8-link cable spine; 2 grommets (ring + recessed
throat) at the back corners. UVMap + reserved Lightmap channel per part.

Measured: **9260 tris** (procedural desk it replaced was ~2–3k; +~6.5k). Bounds exact:
±1.02 / ±0.39 / 0..0.736. Files: source 584 KB → public 216 KB. Sidecar `desk.json` (dims).

Fix after looking: foot loft bottom sat at −0.011 (sank through floor) — re-based to 0.008
with glide discs as the contact (0..0.008).

Verifies: `tsc` clean; room/shelf/gesture(PASS)/books(PASS)/motion/ao-motion/a11y(PASS)/
shelf-a11y all green, no console errors. Screenshots `tmp/desk-new/` (h13/h21 all views) +
`tmp/desk-detail/` (leg joint, perforated tray + spine, grommet): desktop objects all sit at
the same height, edge band + leg joinery + tray slots read. `furniture.blend` not recommitted
here (this run built desk-only; the committed blend stays the chair one until the final
all-groups run).

## 3. Shelf — done, committed

Built in `build_furniture.py::build_shelf`. Local frame = the bookshelf group frame (+x along
wall, +z into room); a mapping helper converts to Blender coords for the glTF Y-up export.
Every plane copies `bookshelf.ts` exactly (bottom-board top y=0, top-board underside 0.312 /
top 0.332, ends/back clear of the book volume), so row math, springs, gestures and the LED
strip + RectAreaLight (still code, dropping into the new channel rails) are untouched.
2 materials (`shelf_board/steel`) retinted to `deskEdge/steel`; `main.ts` loads `shelf.glb`.

What it adds over rboxes: 3 mm edge breaks on all boards; back panel with 5 real boolean
V-grooves; folded-steel L brackets with diagonal gusset, wall plate and 2 screw heads each
(the old tabs floated mid-air — the new plates reach the back panel); LED channel rails the
code strip sits between. UVMap + reserved Lightmap channel per part.

Measured: **1144 tris**, 2 materials; bounds match the code planes. Files: source 92 KB →
public 33 KB. Sidecar `shelf.json` (dims + rowInset).

Verifies: `tsc` clean; shelf (enter/step/inspect/Esc ×2)/gesture(PASS)/books(PASS)/room/
motion/ao-motion/a11y(PASS)/shelf-a11y all green, no console errors. Screenshots
`tmp/shelf-new-shots/` (night: hover/enter/step/inspect) + `tmp/shelf-day/` (hour 13):
books slot cleanly, presented book clears the row, grooves + brackets + channel read;
the night-black presented cover is night lighting (daylight shows the cover fine; books
are untouched code).

## 4. Room shell trim — done, committed

Built in `build_furniture.py::build_trim`, authored in world coords (Blender (x,−z,y) mapping).
Replaces the flat frame bars + sill + apron rboxes in `room.ts` with one `trim.glb` instance
at the origin; floor disc, wall slabs and glass stay procedural. 3 materials
(`trim_frame/sill/wall`) retinted to `windowFrame/sill/wall`; `main.ts` loads `trim.glb`.

What it adds: stepped window bars with room-side glazing beads (same opening, so the code
glass still fits); architrave casing on the room wall face; sill board with a real bullnose
cylinder + apron with bead; reveal liners on left/right/top; skirting (board + cap) along
all three walls, 1 mm proud. UVMap + reserved Lightmap channel per part.

Measured: **1756 tris**. Files: source 148 KB → public 53 KB. Sidecar `trim.json` (window +
glass opening, matches the code glass 2.25×1.71).

Fix after looking: trim preview camera used world coords as Blender coords (inside the sill)
— converted to Blender space.

Verifies: `tsc` clean; room/shelf/gesture(PASS)/books(PASS)/motion/ao-motion/a11y(PASS)/
shelf-a11y all green, no console errors. Screenshots `tmp/trim-new/` (h13/h21 all views, no
z-fight, no white band) + `tmp/trim-detail/` (sill nose highlight, skirting board + cap line,
layered reveal liner/frame/glass).

## Final numbers

All four groups land in one script (`blender/scripts/build_furniture.py`, `all` = 26,006 tris
across chair 13,846 / desk 9,260 / shelf 1,144 / trim 1,756), one source
(`blender/source/furniture.blend`, 625 KB, collections Chair/Desk/Shelf/Trim + 4 cameras +
3-point lights + `//render/` path, each camera preview-rendered to `blender/source/render/`),
four GLBs + sidecars through `optimize-glb.mjs`. No `layout.ts` change; no third-party
geometry (MANIFEST notes the script).

| object | tris before → after | source GLB | public GLB |
|---|---|---|---|
| chair | 6,620 → 13,846 | 195.5 → 727 KB | 118.8 → 276.9 KB |
| desk (was procedural ~2–3k) | → 9,260 | → 584 KB | → 215.5 KB |
| shelf (was procedural ~1–2k) | → 1,144 | → 92 KB | → 33.4 KB |
| trim (new) | → 1,756 | → 148 KB | → 53.3 KB |

Seated scene (interleaved base/now page loads, 1728×1000 CSS DPR2, pr 1.5, hour 21, `perf.snapshot`
over 3 s idle): **66,218 → 72,034 tris (+5.8k, +8.8%)**, draw calls 87 → 86 p50, merge
151→68 (was 171→69 — GLBs arrive pre-joined). Ceiling was ~300k; we sit at ~72k seated.
(Absolute differs from the perf LOG's 131k — different viewport/conditions; only interleaved
pairs count.)
Public models total +~460 KB (chair +158, desk +216, shelf +33, trim +53).

Frame (`bench-ab.mjs`, VIEWPORT=1728x1000, pr 1.5, hour 21, 3 rounds × both orders, fence-timed):
base-first: pose0 look +0.14/idle −0.07, pose1 +0.12/−0.09, pose2 +0.03/−0.01;
now-first: pose0 −0.01/−0.20, pose1 −0.07/+0.04, pose2 −0.07/+0.18.
Combined mean ≈ **+0.02 ms look, −0.03 ms idle — noise, no regression**. (Absolute ~6.2–6.4 ms
pose0-look on this hot machine for both builds; LOG cool was 5.0. The 6 ms budget is met in
cool conditions, symmetric before/after.)

Image (frozen-grain `compare-variants`, base worktree 5196 vs now 5195, 4 views × 13/21):
13: seated 2.06, deskRight 1.35, shelf 1.27, standing 1.91;
21: seated 0.66, deskRight 0.45, shelf 2.05, standing 0.82 — all intended geometry
(desk edge/legs, shelf grooves/brackets/channel, trim beads/casing/skirting, chair mass).
Pair sheets `tmp/cmp-both/pair-now-{13,21}.png`: no dark/missing light, no broken shadows,
no floating parts, no z-fight.

Startup (`startup-trace`, interleaved): base 1517/1498 vs now 1601/1490 ms — parity (+2.5%,
noise; inside the +15% guard). `compile-watch 13`: 76 programs after load, zero after
(baseline chair re-measured here: also 76 — the old report's 70 is stale).
Suites green on the final tree: room, a11y, shelf, shelf-a11y, gesture (PASS), books (PASS),
motion, ao-motion; `tsc` clean.

## Rejected / noted along the way

- Smart-project UVs headless: `bpy.ops.uv.smart_project` poll fails with `--background`
  (no image-editor context; `build_lamp.py` already try/excepts it). `lib.uv_unwrap` now falls
  back to a deterministic per-face cube projection — the runtime projects PBR maps in object
  space anyway (`textures.ts projectMaps`), so shipped UVs only need to exist until an
  interactive session does the bake unwrap. `Lightmap` channel still reserved on every part.
- Chair at 18.8k first (piping curve `resolution_u=4` cost 2.5k alone; a `R @ T` transform bug
  flung parts 0.3 m under the floor) → fixed order to `T @ R`, trimmed resolution/steps →
  13.8k with correct bounds.
- Desk foot loft sat 11 mm under the floor → re-based so glide discs are the contact.
- Shelf/desk/trim dimensions copied exactly from `layout.ts`/builders — no gameplay change by
  construction; bookshelf gesture/books verifies confirm.
- Headrest for the chair: skipped (changes the silhouette the sit animation was framed for;
  lumbar pad + ribs carry the backrest detail instead).

## Left

- `furniture.blend` is render-ready (open → F12 renders the chair cam; switch cameras for
  desk/shelf/trim). Lightmap bake is future work — UV channels are reserved.
- Tri headroom used: ~5.8k of ~170k. Monitor stand cable detail / bin latches from the models
  report remain untouched, still fine at camera distance.
