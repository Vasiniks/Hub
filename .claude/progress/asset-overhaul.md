# Asset overhaul — progress

**Resume rule:** read this file, check `git log`, run the build, continue from the first
unchecked item. Do not redo checked work.

Last verified commit: see `git log` (each checkpoint below is one commit).

## Toolchain

- Blender **5.0.1** at `/Applications/Blender.app/Contents/MacOS/Blender` (not on PATH).
- Headless Python works. Note: Blender 5.0 removed the `SMOOTH_BY_ANGLE` modifier enum —
  use `bpy.ops.object.shade_auto_smooth(angle=…)`. `BLENDER_EEVEE_NEXT` is now `BLENDER_EEVEE`.
- Pipeline lives in `blender/scripts/`:
  - `lib.py` — shared: import, clean, bevel, decimate, materials, export, sidecar metadata
  - `inspect.py` / `parts.py` / `preview.py` — diagnostics
  - `build_*.py` — one per asset
- `assets/source/` untouched downloads · `assets/processed/` exported GLB + sidecar JSON
- Runtime copies live in `public/assets/processed/` (Vite serves `public/` at the root).
- Runtime loader: `src/scene/assets.ts`. Loads everything before the room is built.

## Pipeline gotchas already paid for

- Draco is **off**: these props are a few thousand tris, so the file is already tiny and
  enabling it drags a WASM decoder into the runtime for no real saving.
- `preview.py` renders were repeatedly misleading about part placement. Trust numeric checks
  and the real scene, not the preview thumbnail.
- Placing a part by measuring an extreme vertex or a part centroid is fragile on a scanned
  mesh. For the lamp the reliable answer was: project along a known direction and take the
  extreme vertex.
- `lib.recentre()` takes a **list**. Recentring one object of an assembly and leaving the rest
  is how the lamp head and the mouse wheel both ended up floating beside their bodies.
- A POLY curve converted to mesh has edges but no face, so Solidify thickens nothing — build
  profiles as an n-gon with bmesh instead.
- `cube()` applies transforms, so reading `.location` back afterwards returns zero. Pass
  positions in; do not read them back.
- glTF export is Y-up; Blender is Z-up. `lib.to_gltf()` converts, and placement metadata is
  written in glTF space.

## Assets

- [x] **lamp** — Poly Haven CC0 spring arm, shade + clamp replaced, 3.8k tris, 216 KB.
      Integrated, lit, aimed, medals hung. `LAMP` in `layout.ts` holds yaw/scale/medal anchors.
- [x] **mouse** — Blender, from scratch. Dome over a tapered footprint; click split and palm
      seam are boolean grooves. 3.9k tris, 99 KB.
- [ ] keyboard TKL
- [x] **MacBook + stand** — Blender, from scratch. One solid body with a bevel all round,
      boolean port/notch recesses, real rounded hinge; body and riser tilt together so they
      cannot intersect. 1.8k tris, 75 KB.
- [ ] monitor
- [ ] GAN cube
- [ ] books
- [ ] FRC robot — already rebuilt in code last run and reads well; lowest priority
- [ ] electronics / bins — Tier 2

## Preserved and must not regress

Camera, interaction, bookshelf one-book-per-gesture, project popup, lighting/time system,
volumetrics, music widget, Lorenz monitor, loading + calibration performance work.
Suites: `verify-room`, `verify-shelf`, `verify-gesture`, `verify-a11y`, `verify-shelf-a11y`,
`verify-motion`, `startup-trace`, `gallery`.
