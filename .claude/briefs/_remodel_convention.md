# Remodel convention — read before modelling anything

The owner wants a **complete remodel** of the room's objects, with **editable `.blend` sources**
kept in the repo so they can open and render them (here or on another machine). Their words:
"models matter more than lighting, or maybe lighting can be done some other way." So: geometry
quality first, and build everything so that **lighting can later be baked in Blender** and shipped
as textures.

## Where things live
- `blender/source/<group>.blend` — **the editable source**, saved with
  `bpy.ops.wm.save_as_mainfile()`. One file per object group. This is a deliverable, not a temp file.
- `blender/scripts/build_<name>.py` — the script that builds/updates that object. Keep the existing
  pipeline: the script produces `assets/processed/<name>.glb` + its JSON sidecar, then
  `node scripts/optimize-glb.mjs <name>` writes `public/assets/processed/`.
  Scripts must be re-runnable from scratch (`blender --background --factory-startup --python ...`).
- `blender/lib.py` already has the shared helpers (clean/bevel/materials/export/sidecar). Extend it
  rather than duplicating; put shared materials in one place so every group uses the same palette.

## Modelling standard (this is the point of the exercise)
- **Real hard-surface work**: correct proportions from references, bevelled edges everywhere a real
  object has them (no razor edges), consistent bevel width per object scale, subdivision only where
  it earns it, no n-gons on deforming or visible curved surfaces, no interpenetrating junk.
- **Scale in metres**, +Z up in Blender, origin at the object's natural base/pivot, transforms
  applied, sane object and mesh names.
- **UV unwrapped, non-overlapping, with a second UV channel reserved for a future lightmap bake**
  (`UVMap` for material detail, `Lightmap` for the bake). Texel density consistent within an object.
- **Materials**: use the shared palette names the runtime retints (`src/scene/desk.ts`,
  `assets.retint`). Do not invent new names without wiring them.
- Keep the established art direction: stylised-but-detailed, cinematic, not CAD, not cartoon.

## Budgets
The room was ~131k triangles seated. You may spend up to **~300k total** if the models earn it, but
every object you touch must have its tri count recorded before/after, and the **seated frame must
stay under ~6 ms** at `VIEWPORT=1728x1000` pr 1.5 (interleaved A/B, both orders — this machine
drifts). GLBs stay quantised through `optimize-glb.mjs`; report file sizes.

## References
You may use CC0/permissive reference images and models (Poly Haven, ambientCG, Poly Pizza — verify
each licence, record in `assets/MANIFEST.md`). Never claim CC0 for something that is not.
`docs/research/reference-sites.md` records which reference projects are MIT (reusable with
attribution) and which are learn-only.

## Verify before you commit
`npx tsc --noEmit -p .`, then the verify scripts (`verify-room`, `-a11y`, `-shelf`, `-shelf-a11y`,
`-gesture`, `-books`, `-motion`, `-ao-motion`) and `compile-watch` — all green, no console errors.
Render your object in the room and look at it: seated and standing, hours 13 and 21, plus a close-up.
If it looks worse than what it replaced, say so and keep the old one.

## Rendering
Also leave each `.blend` ready to render standalone: a camera framing the object, a simple 3-point
or HDRI setup (Poly Haven CC0), and `render/` output path — so the owner can open the file and hit
render. Do not spend hours rendering here; one small preview render per object is enough to prove
the file works (`blender -b <file>.blend -o //render/preview_ -f 1 -F PNG`).
