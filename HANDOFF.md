# Handoff: the room, as it stands

Written 2026-09-28 at `main` = `921824d`. This is the whole state of the project for whoever picks
it up next — human or agent. Read it before touching anything; it exists so the next pass does not
re-run work that has already been measured and rejected.

The bake-machine contract is a separate, narrower document: `HANDOFF-BAKE-MACHINE.md`. It is
currently dormant (see **Parked** below).

---

## What this is

A first-person WebGL room — you stand, sit at a desk, and open things (dev board, notebooks, robot,
bookshelf). three.js r186 + Vite + TypeScript. No framework, no server: `npm run build` produces a
static `dist/`.

```
npm install
npm run dev        # dev server
npm run build      # production bundle -> dist/  (~4.7 MB, 868 kB JS / 232 kB gzip)
npm run preview    # serve the production bundle locally
npm run typecheck  # tsc, must stay clean
```

Last local deploy of the production bundle served clean on `127.0.0.1:4173`.

---

## Where the work is

| area | files |
|---|---|
| Scene assembly | `src/main.ts`, `src/scene/room.ts`, `desk.ts`, `bookshelf.ts`, `objects.ts`, `layout.ts` |
| Render pipeline | `src/scene/renderer.ts` (single composite pass), `ao.ts`, `bloom.ts`, `outline.ts`, `volumetric.ts` |
| Lighting | `src/scene/lighting.ts`, `areaLights.ts` (baked rect-light volumes), `lampDisk.ts` (PCSS disk lamp) |
| Materials / textures | `src/scene/materials.ts`, `textures.ts` |
| Camera | `src/camera/rig.ts` — look spring is 6.0 rad/s, critically damped; this is a tuned value, not a placeholder |
| Model pipeline | `blender/scripts/build_*.py` + `lib.py` → `assets/processed/*.glb` → `node scripts/optimize-glb.mjs` → `public/assets/processed/` |
| Editable model sources | `blender/source/{furniture,computer,props}.blend` |
| Asset licences | `assets/MANIFEST.md` — **every** external asset has a row, with its licence and every modification |
| Performance record | `perf/LOG.md` — kept and rejected experiments, with numbers |
| Agent briefs + reports | `.claude/briefs/` — one brief and one report per workstream |

---

## What is done

- **Complete remodel.** Furniture, computer gear and props remodelled in Blender with `.blend`
  sources committed. 20 GLBs, ~2.1 MB in `public/assets/processed/`. The lamp is built from the
  owner-supplied `lamp.stl` (used with permission — it is **not** CC0 and must never be described
  as such) with an original blade head.
- **Textures.** ambientCG CC0 scans for floor, wall, fabric; material contrast pass applied.
- **Two rendering passes.** Single composite pass instead of a post chain; AO cached and reprojected
  through a guard-band snapshot; rect-area lighting precomputed into 96³ form-factor volumes; the
  lamp is an analytic disk with PCSS shadows, gated so it costs nothing when unlit. Seated look went
  7.4 → 5.0 ms; 120 fps holds with roughly half the frame budget unused. Full detail in `perf/LOG.md`.

## What is parked

**The lightmap bake.** Five states (neutral, day, golden, evening, night) were baked on a second
machine and are on branch `bake/20260927`, with its log at `docs/bake-log-2026-09-27.md`. Wiring
them into the runtime measured a **null result** (base ±0.2 ms) and the output is not usable as
delivered. Four defects to fix before any re-bake is worth the hours:

1. `bake_lighting.py` repacks UVs for the bake but never saves them back, so the runtime has no
   matching `TEXCOORD_1`.
2. The PNGs are tone-mapped, not linear — they cannot be multiplied into lighting as-is.
3. The bake atlases per group; the runtime merges per material. The two groupings must agree.
4. Lightmaps are gitignored on `main` (`public/assets/lightmaps/`) — deliberate, so a stale bake
   cannot ship by accident. The artifacts live on `bake/20260927`.

Branch `ws/lightmaps` holds the runtime half that was never merged: `scripts/optimize-glb.mjs`
`prune({keepAttributes: true})` and `uv1` preservation in `src/scene/merge.ts`. It costs +653 KB of
model payload and buys nothing until a corrected bake exists. **Do not merge it before then.**

---

## Next job: GPU strain

The owner's instruction, verbatim in spirit: get the models all in place first, then deal with GPU
strain. Frame time is fine on a healthy M2 Pro; what is not fine is how hard the pipeline leans on
the GPU — it is fill-bound, and pixel ratio 1.5 costs roughly twice 1.25 on this hardware.

**Already tried and rejected — do not redo these without new evidence:**

- A depth pre-pass. Cost +1.0–2.2 ms. This GPU is tile-based deferred; hidden-surface removal
  already elides covered fragments, so opaque overdraw is close to free and the extra pass is pure
  loss. Treat this as a standing lesson about the target hardware.
- Warming focus arrival poses behind the loading bar. The warmed state is overwritten before the
  first click; interleaved A/B showed noise, then a regression on the hotter run.
- Fov tolerance in AO snapshot reuse. No benefit — the max is set by contention on recompute
  frames, not by how many there are.
- A shared G-buffer for AO via MRT normals from the main pass.

**Unspent levers, in the order they look worth trying:**

1. Quarter-resolution AO while the view moves (currently half). ~2 ms, needs visual sign-off with
   mid-flight screenshot comparison — `scripts/compare-variants.mjs` does that comparison.
2. Temporal accumulation for AO and volumetrics.
3. Resolution policy itself: the calibration picks 1.25; see the resolution-cliff section of
   `perf/LOG.md` before changing it.

**How to measure, and how not to fool yourself.** Use fence timing, not queue time:
`window.__room.bench(pose)` (`src/debug/bench.ts`, debug-only). `scripts/bench-ab.mjs` runs URL
variants in interleaved page loads and **must** be run in both orders — this machine drifts about
50% from cool to hot, which is larger than most of the effects being chased. A single before/after
pair proves nothing. Any rejected experiment goes in `perf/LOG.md` with its numbers, so the next
pass does not pay for it again.

---

## Ground rules

These are the owner's standing constraints. They are not negotiable and they outlive any individual task.

- **Never overstate what was done.** Do not claim an external asset was imported if it was not, do
  not call something ray tracing when it is not, do not call the music playing when only the UI
  exists, and do not call a model high quality while it is still visibly a primitive.
- **Licensing is honest or the asset does not ship.** Nothing with unclear licensing. Downloadable
  does not mean CC0. If an asset needs an account or a purchase, say so and find an alternative —
  never imply it was downloaded. Every asset gets a row in `assets/MANIFEST.md`.
- No unauthorized copy of the song goes into this repository.
- No destructive git: no history rewriting, no force-pushing, no branch deletion.
- Do not edit the global `~/.claude/CLAUDE.md`. Do not install extra MCP servers, plugins or skills
  without a demonstrated need.
- Do not attempt to bypass authentication or access controls.
- Commits end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Branches

`main` is the only branch that ships. `bake/20260927` holds the bake artifacts and is not merged.
The `ws/*` branches are agent worktrees; all are merged into `main` except `ws/lightmaps`, which is
held back deliberately (above).
