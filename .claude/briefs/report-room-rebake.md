# Report: room-rebake (branch `ws/room-rebake`, last commit 5f470c3)

The subagent returned this report as its final message; the coordinator committed it. Screenshots:
`.claude/briefs/report-room-rebake/`.

## What the live defects were
- **Ceiling panels and dark lines:** 1.4 m tile cuts made each tile its own island, denoised separately. Now walls,
  floor and ceiling are one island per face, crown and baseboard one per wall run, and rings/U-shaped n-gons are split
  per face.
- **"Median 8.1 px/m":** the old shrink rule ("face points away from room centre") is replaced by a ray-cast visibility
  test from 518 eye points (a 0.25 m grid at 0.8–2.0 m plus every room camera). Islands seen from nowhere get 0.12×
  density, islands less than 15% seen get 0.5× (curtain backs), and every visible shell face is now 211 px/m.
- **Sky-blue bands ~10 texels wide** by the door and window corner (already live): Blender applies each object's bake
  margin over texels other objects already baked. Fixes:
  - margin is now half the gutter (3 px);
  - gutters, and texels buried in geometry, are refilled from the same UV island before and after OIDN;
  - the albedo bake uses the same margin.
- **Curtain streaks:** about 600 islands per curtain reduced to 2 (front + rim, back).
- **Rug radial seams:** custom normals blocked the weld; the rug is now welded.

## Numbers
**Density (px/m on seen faces):**

| surface | before | after |
|---|---|---|
| shell | 113 | 211 |
| ceiling / frame / sash | 68 | 211 |
| curtain fronts | ~125 | ~250 |
| rug | 118 | 231 |

**Bake:** shell 2048, soft 1024, desk 1024, furniture 512, all at 1024 spp, about 10 min.

**Cycles vs baked preview** (mean absolute luma difference):

| view | before | after |
|---|---|---|
| stand | 0.0254 | 0.018 |
| seat | 0.035 | 0.029 |
| ceiling close-up | – | 0.0098 |
| curtain close-up | – | 0.020 |

**Web vs Cycles** (MAE /255):

| view | before | after |
|---|---|---|
| ceiling | 8.96 | 6.71 |
| curtain | 12.63 | 11.10 |
| stand | 15.5 | 14.4 |
| seat | 20.2 | 19.0 |

**Bytes:** 5.05 → 7.40 MB (shell lightmap 3.38 MB). Lossless WebP, bit-identical to the PNGs. Triangles 99.6k → 95.7k.

## Not fixed
- Curtains ship as the cage mesh (subdivided would be ~280k tris); the bake now matches it.
- The hallway stub stays at low density (seen from nowhere).
- Remaining differences from Cycles are mostly specular and the props.

## Re-run order
1. `v2_bake_sunset.py` (prepare → bake → export → verify).
2. `blender_albedo.py` on `room_bake.blend`.
3. `scripts/v2look/encode_room_webp.py`.
4. `optimize-glb.mjs`.
5. `meshopt-glb.mjs`.

The vite dev server crashes with EBUSY while Blender holds `room_bake.blend`; use `vite preview` during bakes.
