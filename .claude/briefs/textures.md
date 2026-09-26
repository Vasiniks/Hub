# Workstream: real materials and textures (branch ws/textures)

Read `.claude/briefs/_common.md` first, then `src/scene/materials.ts`, `src/scene/textures.ts`
(projected UV pipeline), `assets/MANIFEST.md` and `scripts/` for the texture tooling.

The owner: "it looks good, but the textures aren't there at all." Most surfaces are flat
`MeshStandardMaterial` colours. Give the room real material identity without wrecking performance.

## What to do
1. Inventory every material in `materials.ts` and rank by screen area in the seated and standing
   views. The ones that matter most: desk top, floor, walls, chair fabric, rug, shelf wood, metal
   parts, ceramic mug, paper, cardboard, plastics.
2. Source **CC0** PBR sets: ambientCG and Poly Haven are the right places (both CC0 — verify, record
   author + URL + licence in `assets/MANIFEST.md`). Prefer 1K, downscale to what the surface needs.
3. Wire them through the existing projected-UV path (`projectMaps`) so procedural geometry without
   UVs still tiles correctly in metres. Use albedo + roughness + normal; skip metalness maps where a
   scalar does the job; use ORM-style packing where it saves a texture unit.
4. Compress: KTX2/Basis if the toolchain allows, otherwise WebP, and generate mipmaps. Watch
   `renderer.info.memory` and the loading time — textures are the classic way to ruin startup.
   They must load behind the existing loading bar, not pop in afterwards.
5. Keep the cinematic grade intact: these textures should read as *subtle surface* (grain, weave,
   brushed metal, wood grain), not as loud tiling patterns. Check tiling scale in metres at close
   range (the seated view sees the desk from 40 cm).

## Definition of done
Before/after screenshots at hours 13 and 21 (seated, deskRight, shelf, standing), texture memory and
startup numbers, frame time A/B at `VIEWPORT=1728x1000`, MANIFEST updated with real licences,
verify scripts green, report at `.claude/briefs/report-textures.md`.
