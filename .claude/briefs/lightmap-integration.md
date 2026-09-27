# Workstream: wire the baked lightmaps into the room (branch ws/lightmaps)

Read `.claude/briefs/_common.md` first. The bake machine has delivered five states
(`neutral, day, golden, evening, night`) at 1024 px / 256 spp into
`public/assets/lightmaps/<state>/<group>.png` plus `manifest.json` (which records gains, texel
density, UV channel, bake type, per-group bounds). Your job is to make the room use them — or to
prove with measurements that it should not, and say so.

## Two blockers to clear first
1. **The runtime GLBs carry no UVs.** `public/assets/processed/desk.glb` has only `POSITION` and
   `NORMAL`. The `Lightmap` UV exists in `blender/source/*.blend` but is not exported. Fix the
   export (`blender/lib.py` + the `build_*.py` scripts) so the lightmap UV ships as `TEXCOORD_1`,
   re-run the builds and `node scripts/optimize-glb.mjs`, and make sure `scripts/optimize-glb.mjs`
   does not strip it.
2. **`mergeStatic` must preserve it.** `src/scene/merge.ts` merges static meshes per material; the
   merged geometry has to keep a consistent `uv1`. Meshes without a lightmap need a valid fallback
   (the existing zero-uv trick, pointing at a white texel).

## Then the runtime
- Sample the lightmap as three's `lightMap` (it reads `uv1`), per object group, with
  `lightMapIntensity` set from the manifest's gains.
- **Do not double-count.** The room already has: an environment probe carrying one bounce, a hemi
  term, and baked rect-area volumes. The bake is indirect-only (DIFFUSE, direct off). Decide what
  the lightmap replaces and turn that off where it now comes from the bake — measure the result
  against the current build; the room must not get brighter or flatter.
- **Time of day must keep animating.** Blend between the two adjacent states by hour
  (day↔golden↔evening↔night, with neutral available), so the sweep stays smooth. Sun and lamp stay
  real-time.
- The chair was baked in its seated position and the real chair rolls in during `sitting`. Decide:
  exclude the chair from lightmapping, or accept it and say why.

## Weight — this is a hard gate
84 MB of PNG (16–18 MB per state) cannot ship. Bring **the whole set under ~12 MB**:
right-size each group by its world bounds (a mug does not need 1024²; the manifest records
`approxPxPerM` — target a consistent density instead of a consistent resolution), convert to WebP,
and load only what a given hour needs, after the loading bar if that keeps startup flat.
Report the final byte total per state and in sum.

## Acceptance
- Frame time: no worse than current at `VIEWPORT=1728x1000` pr 1.5, interleaved both orders.
- Startup: within 15% of current (~1.35 s to loader hidden).
- Visual: frozen-grain pairs at hours 13, 18.5, 20, 21.5 in all four views. The bake should add
  contact darkening and bounce — if it flattens the room or fights the existing lighting, **revert
  and report that with the images and numbers**. A null result here is a perfectly good outcome.
- All verify scripts green, `tsc` clean.

Commit on `ws/lightmaps`; write `.claude/briefs/report-lightmaps.md`.
