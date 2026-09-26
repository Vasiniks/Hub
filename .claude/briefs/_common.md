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
   Scripts default to `http://127.0.0.1:5173`; most accept `BASE=http://127.0.0.1:<port>`.
9. Startup must stay fast: loader hidden ≈1.35 s (`node scripts/startup-trace.mjs`). Don't regress
   it by more than ~15%.
10. Write a short report at `.claude/briefs/report-<workstream>.md`: what you did, measured numbers,
    what you rejected and why, what is left. Keep it factual.

## Blender
Blender 5.0.1 CLI is at `~/.local/bin/blender` (`blender --background --python script.py`).
The repo already has a Blender→GLB pipeline: `blender/scripts/*.py` produce `assets/processed/*.glb`
(+ a JSON sidecar with metadata like the lamp's `socket`/`beam`), then `node scripts/optimize-glb.mjs`
quantises them into `public/assets/processed/`. Follow that pipeline; do not invent a new one.
