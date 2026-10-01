# Shared rules for every workstream (read first)

Project: a first-person cinematic 3D portfolio room (three.js r186 + Vite + TypeScript).
The room IS the navigation: stand → scroll to sit → look with the mouse → click an object →
camera zooms → translucent panel → Esc/click-outside → back. Desktop only. Read `README`-level
context in `perf/LOG.md`, `assets/MANIFEST.md`, `.claude/progress/` and `src/scene/*`.

## Hard rules
1. **Licensing honesty.** Only use assets/shaders whose licence genuinely permits use (CC0, CC-BY
   with attribution recorded, MIT/Apache for code). NEVER claim something is CC0 because it is
   downloadable. If an asset needs an account or purchase, say so and find an alternative. Record
   every asset's source + licence + author in `assets/MANIFEST.md`.
2. **Never claim something you did not verify.** No "imported X" unless the file is in the repo and
   renders. No "faster" unless you measured it with the repo's own scripts.
3. **Measure, don't guess.** Use `scripts/bench-ab.mjs`, `scripts/bench.mjs`, `scripts/perf-suite.mjs`,
   `scripts/compare-variants.mjs` + `.py`, `scripts/real-chrome.mjs`. Bench conditions that matter:
   `VIEWPORT=1728x1000` at pixel ratio 1.5 (the target Mac: M2 Pro, 120 Hz display).
   Interleaved A/B only — this machine drifts.
4. **Do not regress the look.** Compare frozen-grain screenshots before/after
   (`scripts/compare-variants.mjs`); mean diff under ~1.0 is noise, above that investigate.
5. **Revert failures.** If an experiment does not pay off, revert it and write down the measured
   reason in `perf/LOG.md` (perf work) or your workstream report.
6. **Git**: you are in a git worktree on your own branch. Commit in coherent steps. NEVER rebase,
   force-push, reset --hard onto main, or touch other branches. Do not merge to main yourself.
7. **Always leave the build green**: `npx tsc --noEmit -p .` clean, and these all pass with no
   console errors: `node scripts/verify-room.mjs`, `verify-a11y.mjs`, `verify-shelf.mjs`,
   `verify-gesture.mjs`, `verify-books.mjs`, `verify-motion.mjs`, `verify-ao-motion.mjs`,
   `node scripts/compile-watch.mjs 13` (expect "programs after load" and no "+N programs" lines).
8. A dev server may be needed: `npx vite --port <your port> --strictPort` from your worktree.
   Every `scripts/verify-*.mjs` takes `ROOM_URL=http://127.0.0.1:<port>` (default: the dev server)
   and `CHROME_PATH` for the browser, both from `scripts/verify-env.mjs`; with neither set they use
   the dev server and Playwright's own Chromium.
9. Startup must stay fast: loader hidden ≈1.35 s (`node scripts/startup-trace.mjs`). Don't regress
   it by more than ~15%.
10. Write a short report at `.claude/briefs/report-<workstream>.md`: what you did, measured numbers,
    what you rejected and why, what is left. Keep it factual.

## Blender
Blender **5.2.2 LTS** CLI is at `~/.local/bin/blender` (`blender --background --python script.py`).
The repo already has a Blender→GLB pipeline: `blender/scripts/*.py` produce `assets/processed/*.glb`
(+ a JSON sidecar with metadata like the lamp's `socket`/`beam`), then `node scripts/optimize-glb.mjs`
quantises them into `public/assets/processed/`. Follow that pipeline; do not invent a new one.

## The v2 room (this phase)

The room was rebuilt in Blender, re-dressed with the owner over many rounds, lit for sunset and
baked. Read `HANDOFF.md` §2–3 and `blender/scene/WEB_TODO.md` first; they are the owner's decisions,
not suggestions. The job now is getting that room onto the website.

- **Authoritative scene:** `blender/scene/room_public.blend` (66 MB, tracked). `room.blend` is NOT
  on this machine and never will be — it embeds assets this public repo may not redistribute.
  Per-asset sources are `blender/scene/parts/<name>.blend`, built by `blender/scripts/v2_<name>.py`.
  `NEW_*` collections are current; **`OLD_replaced` is retired geometry — never export it.**
- **Already baked, ready to use:** `blender/bake/sunset/` holds four atlas GLBs (shell, desk,
  furniture, soft) carrying the lightmap UV as `TEXCOORD_1`, their RGBM lightmap PNGs, and
  `manifest.json`. Its `README.md` is the spec for the runtime side — follow it literally,
  especially the RGBM decode and "don't double-light".
- **Sunset only** (owner, 2026-09-30). Static surfaces take their light from the bake; small and
  dynamic objects stay live-lit. The time-of-day cycle and the lamp toggle are gone for baked
  surfaces. Never light a baked surface twice.
- **Licensing gate — absolute.** These must never reach `public/`, a GLB, or the bundle:
  `NEW_tele_gb` (Greg Bennett guitar), `NEW_teto*` pear, `NEW_redbull`, `pc_gpukit_*`,
  `*emblem18*` (speedcube logo). They are already stripped from `room_public.blend`; assert they
  are absent rather than assuming it. The CC BY assets that *may* ship — Teto plush (revsworks),
  MX Master 3S (Guibazilla), Bambu A1 mini (neilvfx), motherboard (Daniel Cardona) — **require a
  visible credit on the site**; that line is part of shipping them, not an afterthought.
- **Budget.** `room_public.blend` is ~1.46 M triangles with the exterior. The shipping room today
  is ~150 k at 120 fps on an M2 Pro, and the owner's live complaint is GPU strain, so geometry has
  to come down by roughly 4×, not 10%. Interior target **≤350 k tris**, exterior **≤20 k**.
  Decimate in Blender before export, and never decimate a mesh that carries a lightmap UV — that
  invalidates its atlas. If a baked mesh is over budget, say so and propose a re-bake.
