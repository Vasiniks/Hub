# BAKE.md — lightmap bake operator page

The runtime keeps direct sun / lamp / monitor / shelf light real-time. What gets
baked here is the other half of the light: **indirect bounce + ambient occlusion**
per object group, one EXR master + one PNG preview per group per lighting state,
under `public/assets/lightmaps/`. A later pass wires these into the runtime; this
page is only about producing them.

## Prerequisites

- This repo checked out on branch `ws/bake` (or whatever branch the bake lands on),
  at the commit whose `.blend` hashes you want recorded — the script hashes
  `blender/source/*.blend` into `manifest.json` so a stale bake is detectable.
- Blender **5.0.x preferred, 5.2 LTS acceptable**. The script was developed against
  Blender 5.0.1 (`~/.local/bin/blender`, Darwin). What matters is not matching 5.0.1
  exactly but that **every state in a bake set is produced by the same Blender build**
  — Cycles changes between versions shift the look slightly, and a set mixed across
  versions would light one group differently from another. The version is recorded in
  `manifest.json`; run the `neutral` smoke test first and look at it before committing
  to the long states.

## Commands

One state (production quality):

```sh
blender --background --factory-startup \
  --python blender/scripts/bake_lighting.py -- \
  day public/assets/lightmaps --samples 256 --res 1024
```

All five states (the real run — takes hours, parallelize, see below):

```sh
for s in day golden evening night neutral; do
  blender --background --factory-startup \
    --python blender/scripts/bake_lighting.py -- \
    $s public/assets/lightmaps --samples 256 --res 1024
done
```

States: `day` (13:00), `golden` (18:30), `evening` (20:00), `night` (21:30),
`neutral` (lights-neutral AO/bounce baseline for later interpolation tests), or
`all` for every state in one process. Light values come verbatim from the
`KEYS` rows in `src/scene/lighting.ts` — if the keyframes moved since this was
written, update `LIGHT_STATES` in the script first (the script refuses to invent
values; the mapping is documented in its docstring).

Re-bake a single group (resume / fix one blotchy object without redoing all):

```sh
blender --background --factory-startup \
  --python blender/scripts/bake_lighting.py -- \
  day public/assets/lightmaps --samples 256 --res 1024 --only chair
```

Per-state runs merge into the same `manifest.json` (read-merge-write), so a
resume never clobbers finished states. Do **not** run two Blenders into the same
`outDir` at the same time — the manifest merge is not atomic. Parallelize across
machines/dirs, then copy the state folders together (each state is one folder;
`manifest.json` entries are per-state and merge on the next single-group run, or
merge by hand — it is plain JSON).

Smoke test (what was verified on the dev machine — seconds, not hours):

```sh
blender --background --factory-startup \
  --python blender/scripts/bake_lighting.py -- \
  neutral tmp/bake-smoke --samples 32 --res 256 --only mug
```

## Expected wall-clock and output sizes

Measured smoke test (M2 Pro, Blender 5.0.1, CPU): **2.7 s wall** for
`neutral / mug / 32 samples / 256 px`, including startup, importing all 19
groups as occluders, UV repack, bake, EXR+PNG write. The mug bake is 3152 tris.

Extrapolation to production (`--samples 256 --res 1024`): bake cost scales
~linearly with pixels (16×) and samples (8×), so ~128× the smoke bake per group:
roughly **1–3 min per small group per state**, more for the big ones (chair,
desk, robot, keyboard). 19 groups × 5 states ≈ 95 bakes ≈ **4–8 h on one
process**. Split by state across 5 processes/machines to get it under ~2 h.

Output sizes (measured mug at 256 px: EXR 772 KB, PNG 122 KB; EXR scales exactly
with pixels — 256²×3 channels×4 bytes):

| per group per state | EXR master (1024² float) | PNG preview (1024²) |
|---|---|---|
| ~ | ~12 MB | ~0.2–2 MB (denoised lightmaps compress well) |

Full bake ≈ **~1.1 GB of EXR + ~20–100 MB of PNG**. See "What to commit".

## How to verify a bake looks right

1. `manifest.json` exists in `outDir`, lists all 5 states, every entry has
   `resolution: 1024`, `samples: 256`, `uvChannel: "Lightmap"`, and the
   `sourceBlendHashes` match the current `blender/source/*.blend` (first 12 hex
   of SHA-256 — recompute with `shasum -a 256 blender/source/*.blend`).
2. Open a few PNGs (`<state>/desk.png`, `<state>/mug.png`, `<state>/chair.png`):
   smooth grey gradients, darker in crevices and under overhangs, no pure-black
   tiles (a fully black tile = missed UV channel or unwired image node), no
   rainbow speckle (fireflies — raise samples), no hard-edged blocks (too-small
   margin or overlapping islands — the script repacks `Lightmap` with 6 % margin;
   if bleed persists, raise `--res` for that group with `--only`).
3. `neutral` should read as soft AO only: mid-grey everywhere, darkening inside
   the mug, under the desk, behind the monitor. `day` should be brighter on top
   faces (window bounce from above-front) than `night`.
4. Spot-check placement: entry `worldBoundsBlender` z-min should sit on the desk
   (0.735) for desktop props, on 0 for floor pieces. (Blender coords are
   `(x, -z, y)` of room coords — see the script docstring.)
5. Optional: open any `blender/source/*.blend`, attach the EXR as an emission
   map on the group's material with the `Lightmap` UV, render once — it should
   look like soft bounce only, no sun shadows (direct is excluded by construction:
   DIFFUSE indirect-only, direct off, color off).

## What to commit

- ✅ `public/assets/lightmaps/<state>/*.png` + `public/assets/lightmaps/manifest.json`
- ❌ Do **not** commit the `*.exr` masters (~1.1 GB). Archive them with the build
  (release artifact / shared drive) so the PNGs can be regenerated, but keep them
  out of git.
- ❌ `tmp/` is scratch (smoke tests). Never commit it.

## If something goes wrong

- **Blender OOMs** (large groups at 1024): bake the big group alone with
  `--only <group> --res 512`, then re-bake just that group at 1024 on a bigger
  machine; or lower `--samples` to 128 and rely on the denoiser (the script
  enables OpenImageDenoise). Never lower `--res` globally to fit one group.
- **Blotchy / splotchy gradients**: indirect noise — raise `--samples` (256 →
  512) for that state with `--only`. Check the PNG at full size, not the
  thumbnail; lightmaps are viewed blurred under the runtime.
- **Light leak / bright seams at island edges**: margin too small for that
  group's texel density — re-bake with higher `--res` (margin scales with res).
- **Black group**: the group's meshes lack a `Lightmap` UV or the bake image
  node did not attach — file an issue with the group name and the console log;
  the builders guarantee `UVMap` + `Lightmap` on every mesh (remodel convention),
  so this means a builder regressed.
- **"Unknown state" / wrong light**: the script's `LIGHT_STATES` must match
  `src/scene/lighting.ts KEYS`. Diff them before the run.
- **Blender 5.x API drift** (e.g. `lightmap_pack` kwargs, `save_render`): the
  script pins the 5.0.1 signatures it was tested against in comments; update the
  call, re-run the smoke test above (seconds), and note the Blender version in
  the commit message — `manifest.json` records `blenderVersion` per entry.

## API notes (for the next person touching the script)

- Node creation is `nodes.new(type="ShaderNodeTexImage")` — `"TexImage"` is rejected.
- `bpy.ops.uv.lightmap_pack` in 5.0 takes only `PREF_CONTEXT / PREF_PACK_IN_ONE /
  PREF_NEW_UVLAYER / PREF_BOX_DIV / PREF_MARGIN_DIV` (no image-size args).
- Bake passes live on `scene.render.bake` (`use_pass_direct=False,
  use_pass_indirect=True, use_pass_color=False`); `scene.cycles` only carries
  `bake_type`. Margin lives on `scene.render.bake.margin`.
- A float-buffer image cannot `save()` to PNG — the script writes EXR with
  `save()` and the PNG preview with `save_render()` (display-referred). Keep it
  that way: EXR is the master, PNG is the preview.
