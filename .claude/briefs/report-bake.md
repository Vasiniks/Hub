# Report — bake script workstream (ws/bake)

## What was built

- **`blender/scripts/bake_lighting.py`** (new, ~700 lines) — headless, re-runnable:
  `blender --background --factory-startup --python blender/scripts/bake_lighting.py -- <state> <outDir> [--samples N] [--res N] [--only group]`,
  states `day | golden | evening | night | neutral | all`.
  - **Assembly**: imports all 19 group GLBs from `assets/processed/` (authoritative
    builder outputs) and places each at its runtime transform from `layout.ts`
    (`ROOM`/`DESK`/`DESKTOP`/`SHELF`/`LAMP`), `desk.ts`, `room.ts`, `bookshelf.ts`,
    `projects.ts`, using the three→Blender map `(x,y,z)→(x,−z,y)`. Trim is already
    world-space; shelf gets its wall-mount pivot (`SHELF.x/y/z`, rotY π/2); chair
    bakes at the seated pose. Procedural shell (floor disc r=9, window-wall slabs
    with real opening, side walls) rebuilt from `ROOM` dims as bounce/occluders.
    Code-built props (polyhedron, notebooks, devBoard ledger, partsCrate contents)
    and dynamic books are excluded by design (no Blender source / dynamic).
  - **UV**: activates the reserved `Lightmap` channel per mesh, repacks with
    `lightmap_pack`, 6 % margin against bleed.
  - **Bake type: DIFFUSE indirect-only** (direct off, color off, denoised) —
    justified in the script docstring: direct sun/lamp/monitor stay real-time so
    they must not be in the map (no double-up), and COMBINED-without-direct would
    also capture glossy indirect that the runtime PBR already integrates (no
    double-count of specular). DIFFUSE-indirect is exactly Lambertian bounce + AO.
  - **Lights verbatim from `lighting.ts KEYS`** (hours 13 / 18.5 / 20 / 21.5):
    sun intensity/color/elevation/azimuth, window rect (2.34×1.80 m at the real
    opening), hemi via world background mix, lamp spot (angle 0.55, penumbra 0.85,
    disk r 0.04 as `shadow_soft_size`, socket/beam from `lamp.json` + yaw/scale),
    monitor area (0.596×0.341 m), shelf strip. Only renderer-unit translation uses
    per-type gains (sun 1.0 / area 5.0 / spot 8.0, identical for all states, in the
    manifest) — state-to-state ratios are preserved exactly.
  - **Outputs**: `public/assets/lightmaps/<state>/<group>.exr` (float master via
    `save()`) + `.png` (display-referred preview via `save_render()`) +
    `manifest.json` (state, group, res, samples, texel target 512 px/m + measured
    px/m, UV channel, Blender version, sha12 of `blender/source/*.blend`).
    Per-state runs read-merge-write the manifest, so resumes never clobber.
- **`BAKE.md`** (repo root) — operator page: prereqs, per-state + `all` + `--only`
  resume commands, wall-clock/size extrapolations, 5-point verification checklist,
  what to commit (PNGs + manifest; never EXRs ~1.1 GB, never `tmp/`), OOM/blotch
  playbook, Blender 5.0 API notes.
- **Full assembly confirmed practical** — no per-group fallback needed: 19 GLBs
  import in ~1 s; `--only` still assembles the whole room as occluders and bakes
  just the target.

## Smoke test (this machine, Blender 5.0.1, M2 Pro, CPU)

- `neutral … tmp/bake-smoke --samples 32 --res 256 --only mug`: **2.7 s wall**,
  EXR 772 KB + PNG 122 KB, manifest valid. Mug bounds z-base 0.735 = desk top,
  centre (−0.5, 0.5) = DESKTOP.mug ✓. PNG stats: mean 102.7/255, stdev 36 —
  mid-grey indirect with expected 32-spp noise.
- `golden … --only mug`: exercises sun + window + lamp spot + monitor + shelf
  paths (lamp=0 in day, so golden covers all light types). Baked clean, mean 103.3.
- Fixed three Blender 5.0 issues found by the smoke test: `ShaderNodeTexImage`
  node type, `lightmap_pack` kwargs, float-image PNG via `save_render`.
- Manifest merge across separate per-state runs verified (`golden`+`neutral` coexist).
- Extrapolation: ~128× pixels×samples → ~1–3 min per small group per state;
  19 groups × 5 states ≈ 95 bakes ≈ 4–8 h single-process (~2 h split by state);
  EXR masters ≈ 1.1 GB total (256² EXR measured 790 KB = 256²×3×4 + header ✓).

## Rejected / not done

- COMBINED-with-direct-off: rejected (bakes glossy indirect the runtime already does).
- Absolute-unit matching (watts): rejected — three intensities are exposure- and
  shader-coupled; gains are global per light type so ratios (what the bake is for)
  are exact. Runtime integration pass will gain-match.
- Wiring lightmaps into `src/`: explicitly out of scope (separate pass). `src/`
  untouched — `tsc --noEmit` clean, no verify scripts affected (no scene change).
- Full bake here: explicitly forbidden by the brief; only 32-spp/256-px smokes ran.
- `tmp/bake-smoke/` outputs are scratch, not committed.

## Bake-fix pass (this machine, Blender 5.0.1, M2 Pro, `ws/bake`)

Fixes `.claude/briefs/bake-fix.md` items 1–5, verified by real smokes into
`tmp/bake-fix-smoke/` (scratch, not committed):

1. **Save path (the crash).** Root cause was a *relative* `filepath_raw`
   (`public/...` + `os.path.join` → mixed `/` + `\` on Windows, resolved
   against the unsaved factory-startup blend instead of cwd), so nothing was
   on disk when `getsize()` ran. Now: `outDir` resolved once to an absolute
   `Path`, state dir `mkdir`'d before the bake, `filepath_raw` absolute,
   `save()` then `save_render()` for the PNG, both stat-checked (missing or
   zero bytes raises). Tried `save(filepath=...)` and `save_render()` for the
   EXR per the brief — both write header-only files on 5.0.1 (296–597 B for
   content `save()` writes as 13–49 KB; `save(filepath=...)` additionally
   leaves the image with "no image data"), so EXR stays on bare `save()`.
2. **Windows paths.** Every output path via `pathlib.Path.resolve()`
   (absolute, separator-consistent); absolute paths passed to both saves.
3. **Exit code.** `main()` wrapped: any exception prints the traceback and
   `sys.exit(1)` (verified: `NotADirectoryError` outDir → traceback,
   Blender exit 1; unknown state → exit 1). Batch loops no longer see 0.
4. **Cycles device.** `--device auto|gpu|cpu` (default `auto`): probes OptiX →
   CUDA → HIP → METAL/ONEAPI via `get_device_types`, activates the GPUs,
   sets `scene.cycles.device`, prints `CYCLES device: GPU via METAL: ...`,
   falls back to CPU with a warning (`--device gpu` with no GPU raises).
   Works under `--factory-startup`; recorded per state as `device` in the
   manifest. This machine: `GPU/METAL` selected.
5. **EXR question.** Decided: PNG previews + `manifest.json` committed, EXR
   masters local. `.gitignore` gains `public/assets/lightmaps/**/*.exr`;
   `BAKE.md` ("What to commit", prereqs, API notes) says it; the manifest
   keeps recording each EXR filename + byte size. Note:
   `HANDOFF-BAKE-MACHINE.md` (on `bake/20260927`, not on this branch — its
   "output" and "Committing" lines still list `*.exr`) needs the same one-line
   update where it lives; `BAKE.md` now points at it.

Verification (wall clock measured, `--device auto` → METAL):

- `neutral tmp/bake-fix-smoke --samples 16 --res 128 --only mug` — 89 s wall
  (first run: kernel compile + 19-group assembly), EXR 199,070 B
  (= 128²×3×4 + header ✓), PNG 34,319 B, PNG mean 98.0 grey, not black.
- Same for `--only cube` — 5 s wall, EXR 199,070 B, PNG 35,566 B, mean 77.5.
- Moderate (save path at size): `golden --samples 64 --res 256 --only mug`
  — 7 s, EXR 790,942 B (= 256² EXR measured in the original smoke ✓), PNG
  153,559 B, warm tint mean R137/G98/B71 vs neutral grey 98/98/98 (state
  variation correct). Same for `cube` — 6 s, EXR 790,942 B, PNG 163,223 B,
  mean R108/G82/B65. None uniformly black (PIL check).
- Known limitation (pre-existing, unchanged): manifest merges per *state*,
  so two `--only` runs into one outDir leave the last group's entry in that
  state's list; both files remain on disk. Cross-state merge verified.

Operator estimate: first group of a fresh process pays minutes of one-time
kernel/assembly cost; steady-state ≈ 5–7 s per small group at 64 spp/256 px
on this M2 Pro GPU. Production 256 spp/1024 px is ~32× pixels×samples over
the moderate smoke — budget ~1–3 min per small group per state as before,
unchanged by this fix (device auto/GPU is faster than the CPU the script
silently used before).

## Left for the bake machine / next pass

1. Run the real bake per `BAKE.md` (5 states × 19 groups, `--samples 256 --res 1024`).
2. Commit `public/assets/lightmaps/*/​*.png` + `manifest.json`; archive EXRs off-git.
3. Runtime integration pass (separate workstream): sample lightmaps by `Lightmap`
   UV, gain-match against live lights, handle chair (baked seated — dynamic
   chair needs follow-up decision) and day/golden/evening/night/neutral blending.
