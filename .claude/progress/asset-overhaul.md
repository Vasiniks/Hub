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
- The pipeline applies transforms into vertices, so every exported mesh sits at its group's
  origin. Use `assets.partCenter()` (bounding-box centre), never `getWorldPosition()`.
- Blender crashed at startup in Metal backend detection inside the sandbox; run it with
  `--factory-startup` and outside the sandbox.
- `mesh.materials.clear()` (inside `lib.set_materials`) resets every polygon's material index
  to 0. For multi-material bmesh builds, append slots to the mesh *before* `bm.to_mesh()`.
- `bmesh.ops.bevel` consumes the vertices it rounds — assign anything per-face afterwards from
  position and normal, not from held references. Bevel before inset, or `clamp_overlap`
  shrinks the bevel to the inset ring's width.
- The preview's key light blows camera-facing faces out to white; judge colour in the scene
  (`__room.parkCamera(p, target, fov)` gives a close-up).
- A multi-material object imports as a Group of primitive meshes, so `assets.part()` (mesh
  lookup) misses it; use `getObjectByName()`.
- Sweeping a section round a rounded path offsets it by its full depth — the outer corner radius
  can never be below the section depth. Use mitre rings for square corners.
- glTF UVs are top-down. A three.js CanvasTexture mapped onto an imported model needs
  `flipY = false`, or every label prints upside down.
- glTF export is Y-up; Blender is Z-up. `lib.to_gltf()` converts, and placement metadata is
  written in glTF space.

## Assets

- [x] **lamp** — Poly Haven CC0 spring arm, shade + clamp replaced, 3.8k tris, 216 KB.
      Integrated, lit, aimed, medals hung. `LAMP` in `layout.ts` holds yaw/scale/medal anchors.
- [x] **mouse** — Blender, from scratch. Dome over a tapered footprint; click split and palm
      seam are boolean grooves. 3.9k tris, 99 KB.
- [x] **keyboard TKL** — Blender, from scratch, layout included. 87 caps lofted at their own
      width (constant corner radius), sheared per row sculpt, dished; plate in a boolean well;
      incline from modelled flip-out feet. 9.6k tris, 289 KB. Replaced ~100k tris of instanced
      rounded boxes — scene tris 252k → 154k.
- [x] **MacBook + stand** — Blender, from scratch. One solid body with a bevel all round,
      boolean port/notch recesses, real rounded hinge; body and riser tilt together so they
      cannot intersect. 1.8k tris, 75 KB.
- [x] **monitor** — Blender, from scratch, built directly in Z-up. Boolean bezel well, slim
      neck, weighted base. 850 tris, 41 KB. Runtime swaps the screen quad for a three.js plane
      (the imported quad showed the attractor mirrored) at `assets.partCenter()`.
- [x] **GAN cube** — Blender, from scratch. Stickerless: colour per face by normal and piece
      position, so it runs over the bevel; inset moulding groove; pillowed; U layer turned;
      seeded part-scramble. One mesh, 7 materials, 3.2k tris, 93 KB.
- [x] **books** — Blender, from scratch: one canonical hardcover (U-profile case with boards,
      rounded spine and hinge grooves; set-back page block with concave fore-edge; headbands),
      320 tris, UVs laid into the per-book atlas regions. Runtime `sliceBook()` 9-slices it to
      each book's thickness/height so boards and squares keep their real size. Still one mesh
      and one draw call per book. Known, pre-existing: books right of the selection sit behind
      the presented book (centre drift), so their bottoms show beneath it.
- [x] **FRC robot** — Blender, from scratch. Hollow 2x1/1x1 tube with holes bored through;
      bumpers swept from the plywood+two-noodle section with mitred corners and the number as a
      decal grid on the fabric curve; treaded swerve wheels, finned motors; pocketed PDH with
      breakers; battery, roboRIO, radio, main breaker, Bezier cable runs; two-stage elevator,
      pocketed carriage with compliant-wheel rollers. 21.8k tris, 970 KB. `robot_carriage` and
      `robot_rsl` exported separately (animated). Layout matches the old in-code robot.
- [x] **Tier 2 (performance/Tier 2 pass)** — Blender, from scratch, deliberately light:
      chair (6.6k tris: contoured seat/back, 5-star base, casters), parts bin (296), tote
      (1.2k, also the parts-crate project object), organiser (1.1k), mug (1.5k, lathed with
      wall thickness), screwdriver (524, fluted), USB cable coil (1.8k), USB hub with LED meshes
      (384), loose dev board (1.2k, retinted per solder mask). Scripts: build_chair.py,
      build_bins.py, build_desk_items.py.
- [ ] materials/textures pass (ambientCG CC0) — floor, walls, chair fabric

## Preserved and must not regress

Camera, interaction, bookshelf one-book-per-gesture, project popup, lighting/time system,
volumetrics, music widget, Lorenz monitor, loading + calibration performance work.
Suites: `verify-room`, `verify-shelf`, `verify-gesture`, `verify-a11y`, `verify-shelf-a11y`,
`verify-motion`, `startup-trace`, `gallery`.
