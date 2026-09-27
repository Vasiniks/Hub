# Workstream report: real materials and textures (ws/textures)

Dev server: `npx vite --port 5192 --strictPort --host 127.0.0.1` (host flag only so
the scripts' hardcoded `127.0.0.1` works; port 5173 was already taken by another workstream).
Baseline for A/B: `tmp/baseline` worktree at HEAD (unmodified code) served on 5181, removed after.

## Inventory (screen area, seated + standing + deskRight views)

1. Desk top (`deskWhite`) — ~35–60% of seated/deskRight pixels. Was flat colour + procedural
   roughness noise. **Done: scanned relief + roughness.**
2. Walls / floor / chair fabric / rug — already scanned in a previous pass. Untouched.
3. Shelf boards + desk rail (`deskEdge`) — same white boards as the desk. **Done: same maps.**
4. Metals (`steel`, `aluminum`, `aluminumDark`: legs, MacBook, lamp, brackets). **Done: scanned roughness.**
5. Plastics (`plasticWhite/Grey/Black`, `keycap*`, `binBlue/binWarm`, `rubber`). **Done: scanned roughness.**
6. Ceramic mug — hero object. No CC0 ceramic scan exists (checked ambientCG + Poly Haven);
   reuses the fine plastic roughness at a glossier scalar. Tone and gloss gap to plastics kept.
7. Paper (bin labels), cardboard (folder, boxes). **Done: paper relief + roughness, kraft colour + roughness + relief.**
8. Left flat deliberately: PCB canvas textures (already patterned), book atlas (per-book canvas),
   graph-paper sheet + notebook covers (builders without surface access, tiny), ribbons, medals,
   LEDs, glass.

## What was added

10 maps, all ambientCG CC0, all verified by preview + full-download inspection before use:

| file | source | size | on |
|---|---|---|---|
| `desk_normal.jpg` 512, `desk_rough.jpg` 256 | PaintedWood009C, relief + roughness only | 30 KB | deskWhite, deskEdge, 1 m tile via `projectMaps` |
| `metal_rough.jpg` 512 | Metal009 brushed steel, roughness only | 33 KB | steel, aluminum, aluminumDark |
| `paper_normal.jpg` + `paper_rough.jpg` 256 | Paper001 | 16 KB | paper |
| `cardboard_color.jpg` + `_rough` + `_normal` 256 | Cardboard002 (clean kraft) | 15 KB | cardboard (+ `#e8f4ff` tint back to established tone) |
| `plastic_rough.jpg` 256 | Plastic013A | 3 KB | light plastics, keycaps, ceramic |
| `plasticdark_rough.jpg` 256 | Plastic010 | 7 KB | dark plastics, bins, rubber |

Totals: 7 → 17 maps, `public/assets/textures` 700 → 824 KB (+124 KB). Est. GPU
+~5.6 MB (≈24 MB total, w×h×4×4/3). All POT, mipmaps on. Roughness scalars re-fit so
scalar × map-mean lands on each material's old flat response (means measured off the
processed files; see comment in `materials.ts`). Dead procedural code removed
(`brushedNoise`, `roughnessNoise`); `tsc` clean. Everything loads through the existing
`loadSurfaceTextures()` gate behind the loading bar — no pop-in path added.

## Measured

- Before/after parked views (`compare-variants`, hours 13 + 21), mean diff / pixels >8:
  13 — seated 1.50/35089, deskRight 1.19/7244, shelf 0.69/8609, standing 1.45/28103;
  21 — 1.46/20118, 1.08/2935, 0.52/5590, 0.79/12058.
  Above the 0.3–0.6 noise floor where the desk dominates (intended), at noise on shelf.
- 40 cm desk macro (new view, `tmp/macro.mjs`): mean 4.72 — faint painted-grain striations
  in raking light, no visible repeat at 1 m tile (checked ~30 cm crop). Mug macro: 3.83 —
  glaze unchanged, desk grain soft around it.
- Startup: direct in-page fetch+ImageBitmap decode of the 10 new maps ≈ 25 ms total.
  Loader-hidden on the dev server is vite-variance dominated (2.4–3.2 s in both builds,
  ±500 ms run-to-run); interleaved before/after `startup-stages` (3 rounds) shows no
  systematic regression (after ≤ before in every round). Within the 15% budget by two
  orders of magnitude on the attributable cost.
- Frame time, `bench-ab`, `VIEWPORT=1728x1000`, pr 1.5, both variant orders (order-swap
  proved a ~2 ms second-runner thermal bias — whichever build runs second looks slower):
  day look 9.13 → 9.55 ms, idle 6.95 → 7.48; night look 9.33 → 10.04. Deltas (+0.4–0.7 ms)
  sit inside the ±2 ms drift floor: no measurable regression.
- Green: `tsc`, verify-room/shelf/gesture/books/motion/a11y/shelf-a11y (no console errors),
  verify-ao-motion (idle 100% full-res, sweep 88% half), `compile-watch` 76 programs, zero
  after-load compiles.

## Rejected (with reason)

- `PaintedWood008C` (dark stain) for the desk — `009C` is near-white; colour unused anyway.
- `Cardboard001` / `Cardboard004` — torn scans with exposed fluting; clean `Cardboard002`.
- `plastic_normal.jpg` — dead flat (std 0.1), deleted; roughness only.
- CC0 ceramic scan — none on either repository; mug shares fine plastic grain instead.
- KTX2/Basis — Basis WASM (~100 KB+) outweighs savings on 824 KB and adds transcode time
  behind the loader. WebP (measured −37% bytes) — lossy smoothing on normal maps
  (floor_normal 77 → 17 KB) risks shading artifacts; JPG kept.
- Wiring the graph-paper sheet — its builder takes only `Materials`, no surfaces; tiny screen
  area. Left procedural, noted above.

## Left

- Notebook covers/graph sheet, ribbons, medals, PCBs: still procedural/canvas (all small).
- Cardboard tint `#e8f4ff` is approximate (blue channel clips); folder tone verified close
  in the shelf view but not colorimetrically exact.
- `tmp/` holds before/after pairs, macros, patched script copies (`*-5192.mjs`), and the
  `stages-ab.mjs` interleaver — scratch, not committed. Baseline worktree removed.

---

# Follow-up: visible materials at seated distance (textures-visible.md)

Dev server: `npx vite --port 5192 --strictPort --host 127.0.0.1` (this worktree).
Baseline for A/B: `tmp/baseline` worktree at HEAD served on 5193, removed after.
Before captures in `tmp/visible-before/` (HEAD code), after in `tmp/visible-after4/`,
diffs + pair sheets in `tmp/visible-diff4/`, 40 cm macros in `tmp/visible-after4/macro-*.png`
(all scratch, not committed).

## What was added

3 near-white albedo maps (diffuse = room colour × albedo, so the palette is unchanged,
only 3–5% luminance variation is added). All POT, mipmaps on, `RepeatWrapping`,
sRGB, decoded as ImageBitmaps behind the loading bar:

| file | source | size | variation | on |
|---|---|---|---|---|
| `desk_color.jpg` 512 | PaintedWood009C 1K roughness (tileable) remapped + tileable low-freq sine mottling (20–33 cm, integer harmonics) | 74 KB | std 13.7 (5.4%) | deskWhite, deskEdge, 1 m tile via `projectMaps` |
| `wall_color.jpg` 512 | PaintedPlaster017 colour, mean-removed, 4× contrast | 80 KB | std 8.8 (3.4%) | wall, 1.6 m tile via `projectMaps` |
| `fabric_color.jpg` 512 | Fabric030 colour, mean-removed, compressed to std 14 | 88 KB | std 10.2 (4.0%) | fabric (9 cm tile), rug (22 cm tile) via `projectMaps` |

Plus, no new downloads: bump reuses the already-loaded roughness scans on metals
(0.03), light/dark plastics + keycaps + bins + rubber (0.04) and ceramic (0.035);
book spines get a procedural cloth weave in `bookAtlas` (CPU canvas, no GPU cost).
Desk/wall normalScale 0.35 → 0.5/0.45 so relief survives the grade; grazing-dent
risk checked in the desk macro (no dents, honest strength).

Totals: 17 → 20 maps, `public/assets/textures` 824 → 1029 KB (+205 KB disk).
GPU w×h×4×4/3: ≈22.8 → **27.0 MB**, under the 40 MB budget.
MANIFEST records the three albedo derivations + the bump-reuse decision.

## Measured

- Frozen-grain diffs vs HEAD (`compare-variants`, parked views, hours 13 + 21),
  mean / pixels >8: 13 — seated **1.02**/11311, deskRight 2.19/39192,
  shelf 4.26/76608, standing 1.96/16281; 21 — seated **1.08**/23206,
  deskRight 2.41/66689, shelf 3.12/34286, standing 1.54/13402.
  Noise floor 0.3–0.6. Seated is just over 1.0 (the desk fills ~40% of a frame
  that also holds the unchanged window/monitor); deskRight/shelf/standing are
  well over. Pair sheets judged honestly: the desk now reads as laminate
  (mottling + grain, no longer flat white), walls as plaster, shelf boards as
  grain, floor as wood (unchanged, already good) — as *material*, not noise,
  and with no tiling repeat in the widest (standing) view. Desk tile 1 m and
  wall tile 1.6 m are stochastic with no distinctive features; the desk albedo
  is derived from a tileable scan plus integer-harmonic mottling so it wraps.
- 40 cm macros (hour 13, `tmp/macros-all.mjs`; night raking-light extras in
  `tmp/macros-night.mjs`): desk PASS (laminate mottling + grain), wall PASS
  (plaster), floor PASS (planks + grain), chair fabric PASS (weave in raking
  light), rug marginal–pass (dark pile, subtle in shadow, clear in the sun
  strip), shelf boards PASS (grain), books pass as material differentiation
  (per-book colours + page edges; within-spine weave is subtle by design).
  Small-surface fine grain is honest about physics: real PBT/moulded grain is
  10–50 µm (<0.2 px at 40 cm in a 1200 px frame), so keycaps/mug/metals read as
  clearly different materials (matte plastic vs glossy ceramic vs reflective
  metal) with bump breaking up specular highlights rather than as resolved
  grain in stills. No dents from the raised normal scales.
- Frame time, `bench-ab`, `VIEWPORT=1728x1000`, pr 1.5, hour 13, 3 rounds,
  both orders (5193 baseline vs 5192 worktree). Order 1 (before first):
  pose 0 look 5.66 → 5.66 (+0.00), pose 1 +0.21, pose 2 +0.03.
  Order 2 (after first): pose 0 5.75 vs 5.83 (−0.08), pose 1 +0.20,
  pose 2 +0.03. Seated look (pose 0) averages −0.04 ms — no regression;
  worst pose +0.20 ms, inside the **+0.5 ms** budget. Idle deltas ≤ +0.10 ms.
- Startup: in-page fetch + ImageBitmap decode of the 3 new maps = **11.8 ms**
  attributable. Interleaved `startup-stages` (alternating 5193/5192, 1 run ×3):
  before 1531 / after 3644 (vite cold outlier), then 1186 / 1125 (−61),
  1094 / 1144 (+50). Excluding the cold outlier: ±61 ms (±5% of ~1.1 s),
  inside the 15% budget (165 ms). No systematic regression; the 11.8 ms
  attributable cost is the real number, the rest is vite dev variance (±500 ms
  run-to-run, as established in the first pass).
- Green: `tsc`, verify-room (ERRORS []), verify-shelf / gesture (PASS) / books
  (PASS) / motion / a11y / shelf-a11y (errors []), verify-ao-motion
  (idle 121/121 full, moving 84/109 half — same profile as before),
  `compile-watch` 76 programs, zero after-load compiles.

## Rejected (with reason)

- Pushing the desk past 6% variation: seated would gain a few tenths, but the
  brief caps the desk at 3–6% and the top already darkens 5% (mean 242); beyond
  that it re-tints rather than textures. Stopped at 5.4%.
- New downloads for plastics/metals/mug/books: small screen area; measured no
  macro change in diffuse light from bump reuse either — kept the reuse (zero
  memory, breaks up specular so highlights don't read CG-flat) rather than
  spending downloads on sub-pixel grain.
- Stronger book spine weave (alpha >0.14): reads as stripes, not cloth. Kept
  subtle; books already differentiate per-book.
- Floor rework: the floor already reads (planks + grain direction + variation
  in every macro and in standing); its normal is flat by nature (smooth wood),
  the colour carries it. Untouched.

## Left

- Small-surface grain stays sub-pixel in stills by physics (see macros); it
  contributes in highlights/raking light and motion, not in thumbnails.
- Rug is dark by palette, so its pile is subtle except in raking light.
- `tmp/visible-before|after*|diff*` + `tmp/macros-*.mjs` + `tmp/dev-519*.log`
  are scratch, not committed. Baseline worktree removed.
