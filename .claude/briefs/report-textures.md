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
