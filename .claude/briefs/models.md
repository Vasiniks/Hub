# Workstream: better models, starting with the owner's lamp (branch ws/models)

Read `.claude/briefs/_common.md` first, then `assets/MANIFEST.md` and `blender/scripts/`.

The owner: "the modeling sucks... use blender more often, but also use online asset repos."

## 1. The lamp (highest priority)
The owner supplied `/Users/admin/Desktop/lamp.stl` (172 KB) and wants the desk lamp to look like it.
Copy it into `assets/source/` first (never read it from the Desktop at build time).
In Blender (CLI, `~/.local/bin/blender --background --python ...`):
- Import, fix scale/orientation (the room is in metres; the current lamp head sits ~0.48 m above the
  desk and aims at the desk — see `blender/scripts/build_lamp.py` and the `socket`/`beam` sidecar).
- STLs are raw triangle soup: weld vertices, recalculate normals, shade smooth with sharp edges
  preserved, decimate only if it is pathologically dense, and give it clean UVs.
- Split materials the room can retint: metal / dark metal / diffuser (see how `build_lamp.py`
  names `lamp_metal`, `lamp_dark`, `lamp_diffuser`, and how `desk.ts` retints them).
- Export through the existing pipeline to `assets/processed/lamp.glb` + sidecar, then
  `node scripts/optimize-glb.mjs`. Keep the sidecar's `socket` (light position) and `beam`
  (aim direction) accurate for the new shape — the lamp's light, its disk-area shading and its
  volumetric beam all read them (`src/scene/lighting.ts`, `src/scene/lampDisk.ts`).
- The lamp must still read as a ~13 cm circular diffuser: `LAMP_DISK_RADIUS` in `lighting.ts` should
  match the new geometry.
- Verify with a render: `node scripts/lamp-shots.mjs <outDir> now:` (night close-ups) and
  `node scripts/compare-variants.mjs`.

## 2. The rest of the room
Rank the current props by how bad they look on screen (seated and standing views are what matter),
then fix the worst few. For each, choose the cheaper of:
- **Model it properly in Blender** (hard-surface workflow, clean topology, real bevels) — the
  monitor, desk, keyboard, mug, bins and shelf are all simple objects that deserve real geometry; or
- **Source it**: Poly Haven (CC0), Poly Pizza (CC0/CC-BY), Sketchfab (check each licence!). Prefer
  CC0. Record source + licence + author in `assets/MANIFEST.md`. If the only good asset needs an
  account or payment, say so and pick another.
Keep the low-poly-but-detailed art direction: this is a stylised, cinematic room, not a CAD dump.

## Budgets
Triangles: the seated view is ~133k today; you may go to ~200k if the models earn it, but measure
the frame cost (`VIEWPORT=1728x1000 node scripts/bench-ab.mjs 3 21 1.5`) and keep the seated frame
under ~6 ms. Each GLB should stay small — check `public/assets/processed/` sizes before/after.
Startup must stay ≈1.35 s.

## Definition of done
New/replaced models in the repo, rendering in the room, screenshots before/after (seated, standing,
close-ups), MANIFEST updated with real licences, tri-counts and frame times measured, verify scripts
green, report at `.claude/briefs/report-models.md`.
