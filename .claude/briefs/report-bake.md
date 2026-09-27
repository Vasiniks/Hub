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

## Left for the bake machine / next pass

1. Run the real bake per `BAKE.md` (5 states × 19 groups, `--samples 256 --res 1024`).
2. Commit `public/assets/lightmaps/*/​*.png` + `manifest.json`; archive EXRs off-git.
3. Runtime integration pass (separate workstream): sample lightmaps by `Lightmap`
   UV, gain-match against live lights, handle chair (baked seated — dynamic
   chair needs follow-up decision) and day/golden/evening/night/neutral blending.
