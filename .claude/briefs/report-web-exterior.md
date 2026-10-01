# Report: web-exterior (branch `ws/web-exterior`, last commit c09b9ff; four-layer version 4f4aeeb)

The subagent returned this report as its final message (subagents cannot write report files); the
coordinator committed it. Comparison images: `.claude/briefs/report-web-exterior/`.

## Numbers

| | full geometry | shipped |
|---|---|---|
| triangles | 390,256 (274 meshes) | **6** |
| draw calls | – | **+2** |
| texture bytes | – | **268,360**: `back.webp` 1303×1039 + `front.webp` 1458×671 |
| extra passes | – | **0** |
| frame cost | – | inside noise (RTX 5070, 1280×720) |

Not measured on a low-end GPU or the M2 Pro.

## How it works

- **The bake:** two Cycles equirectangular panoramas of the approved dusk scene, taken from one bake eye midway
  between the seated and standing eyes.
  - **Back card (opaque):** road, lawns, houses and sky, on a ground plane, then a wall at y = 26.5.
  - **Front card (alpha):** poles, wires, maples and cars, on a plane at y = 20.
- **The shader** projects each fragment back to the bake eye and reads the panorama there.
- **The cards** are unlit, write into the HDR buffer (so the room's grade applies), never write depth, and sit on the
  far plane.
- **Encoding:** the images hold scene-linear radiance in a log2 encoding; exposure is applied at runtime.
- **Sidecar:** `exterior.json` records the bake eye, poses, panorama basis, card placement, encoding, render settings
  and glass.

## Glass (owner kept it)

The approved stills look through `Mesh_11`, a zero-thickness Principled glass plane (transmission 1, IOR 1.5, not
thin-walled). Every ray refracts once and never comes back out, so the street appears about 1.5× magnified.

- The shader reproduces that refraction (`glass.ior = 1.5`).
- `glass.ior = 1` gives a plain window with no re-bake.
- The owner chose to keep it as is (2026-10-01).

## Parallax

Measured as mean |Δ| in 8-bit steps over the glass, 1280×720, against the full-geometry Cycles render with the same
camera and glass:

| | seated | standing |
|---|---|---|
| noise floor | 1.62 | 2.08 |
| at the bake eye | ~4.0 | – |
| 2 cards (shipped) | 9.50 | 13.23 |
| 2 cards, no glass | 8.34 | 9.79 |
| 4 layers | 6.28 | 7.85 |

Houses, road, wires and poles land within a few pixels. Most of the gap is the back-row tree canopies painted on the
26.5 m wall. Four layers measure better, but each costs a full-window fragment pass, so two were kept for low-end
GPUs.

## Files

- `blender/scripts/v2_exterior_web.py`
- `scripts/encode-exterior.mjs`
- `scripts/shoot-exterior.mjs`
- `src/scene/exteriorBackdrop.ts`
- `public/assets/v2/exterior/`
- One row in `assets/MANIFEST.md` (the street is scratch-built, so no third-party asset).

**Rebuild** (Blender through the lock, against `room.blend`):
1. `layer back 256`, then `layer front 256`.
2. `encode`.
3. `node scripts/encode-exterior.mjs`.
