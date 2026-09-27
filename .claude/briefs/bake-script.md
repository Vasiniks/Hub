# Workstream: author the lightmap bake (branch ws/bake)

Read `.claude/briefs/_common.md` and `.claude/briefs/_remodel_convention.md` first.

The owner will run the actual bake **on a different machine**, which will do nothing but bake and
push. Your job is to make that turnkey: write the bake script and the data it needs, smoke-test it
here at low quality, and **do not run the full bake**.

## Deliverables
1. **`blender/scripts/bake_lighting.py`** — headless, re-runnable:
   `~/.local/bin/blender --background --factory-startup --python blender/scripts/bake_lighting.py -- <state> <outDir> [--samples N] [--res N] [--only object]`
   - Assembles the *whole room* from the existing sources (`blender/source/*.blend` plus whatever
     `blender/scripts/build_*.py` generate) into one scene at the room's real world positions —
     read `src/scene/layout.ts` and the builders so the bake matches what the runtime shows. If a
     full assembly is impractical, say so in the report and bake per group with correct transforms.
   - Uses the **`Lightmap` UV channel** the remodel reserved, packs an atlas per object group with
     consistent texel density (state it, e.g. 512 px/m for the desk area), margin to avoid bleed.
   - Bakes **indirect/bounce + ambient occlusion** (Cycles, `COMBINED` with direct off, or
     `DIFFUSE` indirect-only — choose and justify), denoised, into EXR (float) and a tone-safe PNG.
   - Lighting per state must match `src/scene/lighting.ts` keyframes exactly: sun elevation,
     azimuth, colour and intensity, the window rect light, hemi, the lamp (disk, 13 cm), the
     monitor glow and the shelf strip. Encode those states in the script from the keyframes —
     do not invent values.
   - States to support: `day` (13:00), `golden` (18:30), `evening` (20:00), `night` (21:30), and
     `neutral` (a lights-neutral AO/bounce pass, useful if we later interpolate).
   - Writes `public/assets/lightmaps/<state>/<group>.exr|png` plus
     `public/assets/lightmaps/manifest.json` recording state, group, resolution, samples, texel
     density, UV channel, Blender version, and a hash of the source `.blend` files.
2. **`BAKE.md` at the repo root** — the operator's page for the bake machine: prerequisites, exact
   commands per state, expected wall-clock and output sizes, how to verify a bake looks right, what
   to commit, and what to do if Blender OOMs or a bake looks blotchy (increase margin/samples).
3. **`.claude/briefs/report-bake.md`** — what you built, what you smoke-tested, the numbers.

## Smoke test only
Run one state (`neutral`) on **one small group** at low samples (e.g. 32) and a small resolution
(e.g. 256) to prove the path end to end, look at the output, and report timings extrapolated to the
real settings. Do not burn hours baking here.

## Do not
- Do not wire the lightmaps into the runtime (`src/`). That is a separate pass after the bake lands.
- Do not change any model, material or scene code.
