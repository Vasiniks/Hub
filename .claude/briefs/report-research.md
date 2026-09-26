# Workstream report: research (ws/research)

Docs-only workstream — no changes under `src/`, `assets/`, `public/`.
Outputs: `docs/research/reference-sites.md` (this workstream's definition of done) + this report.

## What was done

- Read `.claude/briefs/_common.md`, `perf/LOG.md` (fill-bound tile GPU, GTAO cache +
  snapshot reprojection, single composite pass, quantized GLBs 2.35→1.19 MB, textures +683 KB),
  `assets/MANIFEST.md` (Poly Haven + ambientCG CC0 only; mouse/keyboard/MacBook/monitor/cube/books/
  robot/chair modelled from scratch), `.claude/progress/asset-overhaul.md`, `package.json`
  (`three ^0.186.0`, `three-mesh-bvh ^0.9.15`, `gltf-transform ^4.5.0`), `src/scene/*` listing.
- Researched in parallel (4 subagents, all fetches verified, temp clones kept in-worktree
  `research-temp/` then deleted before commit — never `/tmp`):
  Bruno `my-room-in-3d` / `folio-2019` / `folio-2025`, Andrew Woan Sooah + Bokoko recreation,
  Wawa Sensei baking guides, Henry Heffernan desktop, Jesse Zhou ramen, Journey showcase +
  examples, Awwwards studios (Basement `shader-lab`/`scrollytelling`/`website-2k25`/
  `ship-25-explorations`, Lusion Of The Oak, Locomotive Scroll, Immersive Garden collabs),
  plus KTX2/Basis, glTF-Transform options, lightmap tooling, `pmndrs/postprocessing`,
  `maath`/`drei-vanilla`/`idb-keyval`.
- Spot-verified licence files directly: folio-2019 MIT, folio-2025 MIT, Sooah MIT, Henry MIT,
  three.js MIT, postprocessing Zlib, plus repo pages confirming my-room-in-3d (no LICENCE),
  abigail-bloom (MIT), shader-lab (Apache-2.0), locomotive-scroll (MIT).
- Wrote `docs/research/reference-sites.md`: per-site links + what-to-steal + licence +
  how-it-applies, top-5 cheapest-first list, drop-in verdicts, explicit fetch-failure list.

## Prioritised recommendations (cheapest first — same as doc top-5)

1. glTF-Transform `weld` + `reorder` + `textureCompress`→WebP in `optimize-glb.mjs`.
2. Invisible hitboxes (Sooah pattern) over existing BVH for shelf props.
3. Dual-gate loader + Howler ducking + mp3 fallback.
4. Palette/matcap + blob shadows (folio-2019 MIT) for dynamic props.
5. Baked day/night/neutral + RGB mask as target shell design + quality ladder.

## What was rejected and why

- KTX2/Basis runtime: 7 maps ~680 KB JPG via ImageBitmap already off-main-thread;
  bottleneck is shaded pixels + MSAA, not fetch. Adds >200 KB WASM + worker on 1.3 s startup;
  ETC1S wrecks normal/roughness. Revisit only on VRAM/upload trace evidence.
- Draco/Meshopt decoders: ~800 KB / ~313 KB decoders vs 1.19 MB models; fights
  `assets.ts` dequantize + metre-slicing. Revisit only if models grow >3–4×.
- Lightmap/whole-room UV2 bake: already decided twice in `perf/LOG.md` with numbers
  (remaining per-light 0.1–0.3 ms; freezes moving sun/lamp; needs UV2 unwrap; conflicts
  with reprojection cache).
- `pmndrs/postprocessing` migration: room already did what it sells (six passes → one
  composite, −1.3…−2.5 ms). Porting rewrites two passes' measured work to save nothing.
- `maath` / `drei-vanilla` helpers: overlap room-owned systems (`pcss`, `Sparkles`,
  transmission = extra pass vs fill-bound). `idb-keyval` asset cache: optional, measure first.
- Copying art/assets from learn-only sources (my-room-in-3d UNLICENSED, Jesse no repo,
  Lusion/Basement-private closed): technique observations only, per brief §3.

## What is left

- Adopt list items 1–3 are small, unblocked follow-ups (perf/textures workstreams own them).
- Items 4–5 need Blender + shader work (models/textures workstreams).
- Unverified this pass (403/timeout/521/JS-shell): awwwards.com three.js index,
  prior.co.jp, immersive-garden.com, Resn/Active Theory/Snellenberg shells, Rachel Wei room.
  Treat as closed/learn-only until fetched.
- Build stays green by construction (docs-only; no code touched). No `perf/LOG.md` entry:
  no measurements taken in this workstream.
