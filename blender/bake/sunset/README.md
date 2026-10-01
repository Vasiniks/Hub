# Sunset lightmaps (web)

Baked from `blender/scene/room.blend` (the approved sunset setup). Everything is in
`manifest.json`; this file covers re-running the bake and wiring it into the runtime.

## Re-run

```
blender -b --factory-startup --python blender/scripts/v2_bake_sunset.py -- all
#   stages: prepare | bake | export | verify   options: --samples 1024 --only shell,desk --res-scale 0.25
```

On the Windows machine every run goes through `blender-locked.sh`, and a worktree has no room.blend:
the script reads `$ROOM_BLEND`, else this checkout's, else the main checkout's `Hub/blender/scene/room.blend`.

`prepare` copies room.blend to `room_bake.blend`. The script only reads room.blend and refuses to
save anything called room.blend. In the copy it then does the following:

- applies the bake-only edits: hides `fx_room_volume`, holds the robot lens driver at its 3.5 average,
  applies the curtains' solidify and **removes their subdivision**, so the lightmap is baked on exactly
  the mesh that ships (the first bake lit the subdivided surface and shipped the cage);
- cleans up the geometry (weld + 0.5 deg limited dissolve, limited by UV, seams and sharp edges);
- unwraps `UVMap_lightmap` as the second UV layer and packs one atlas per group. Walls, floor and
  ceiling are one island per face (no tile cuts at 2048: the 1.4 m tiles of the first bake showed as
  panels with dark lines between them); trims are cut once per wall run; each curtain is two islands
  (front + rim, back), split where the solidify shells meet;
- shrinks only islands **no visitor can see**: an island keeps full density if any face is seen,
  from the front and unoccluded by the baked meshes, from a 0.25 m grid over the room at 0.8-2.0 m or
  any camera inside the room. (The first bake used "faces away from the room centre", which also
  caught visible faces.)

`bake` runs a Cycles DIFFUSE bake (direct + indirect, colour off) with a margin of only half the
gutter: with several objects baked into one image, Blender applies each object's margin over texels
other objects already baked (the first bake's 8 px margin over 4 px gutters painted sky-lit bands
into the left wall by the door and at the window corner). Texels whose centre is in no
UV triangle (gutters) or that bake exactly black (buried in other geometry: a wall face running into
the next wall, the ceiling above the crown) are refilled from valid texels of the same island, before
OIDN and again after it, so bilinear filtering never reads a black or foreign texel. Then it writes the
EXR, the RGBM PNG and a preview.
`export` writes the GLBs and checks the UV round trip. `verify` makes `compare_<cam>.png`
for CAM_stand, CAM_seat and two close-ups (`CU_ceiling`, `CU_curtain`, the web screenshots' poses).

Web copies: `python scripts/v2look/encode_room_webp.py --albedo <albedo dir>` (lossless WebP, checked
bit-identical), after `scripts/v2look/blender_albedo.py` on `room_bake.blend`; then
`node scripts/optimize-glb.mjs --src blender/bake/sunset --dst public/assets/v2/room <atlas>` and
`node scripts/meshopt-glb.mjs public/assets/v2/room`.

## Files per atlas (`shell`, `desk`, `furniture`, `soft`)

| file | what |
|---|---|
| `<atlas>.glb` | The baked meshes in world space (glTF Y-up). `TEXCOORD_0` is the original UV, or all zeros where the object had none. `TEXCOORD_1` is the lightmap UV. No images are embedded. |
| `lightmap_<atlas>.exr` | Master copy: linear Rec.709, half-float RGB, ZIP compression. |
| `lightmap_<atlas>.rgbm.png` | Web master: 8-bit RGBA RGBM of sqrt(L) (the site ships it as lossless WebP). **Decode: `L = (rgb * a * range_sqrt)^2`.** `range_sqrt` is listed per atlas under `atlases.<atlas>.web`. |
| `lightmap_<atlas>_preview.png` | A tone-mapped preview only. Do not use it for lighting. |

The atlas groups are fixed by object name, not by material: see `atlases.<atlas>.objects`.
The runtime must keep these groups when it merges meshes. If it merges by material across two
atlases, the lightmap UVs no longer address a single texture.

## Runtime (three.js r186)

- **What the bake holds.** L is the Cycles diffuse light pass: sun, sky, lamp disk, fixture
  points, emissive PC/screens, all bounces. Blender's diffuse output is `albedo * L`. three.js
  computes `irradiance * albedo / PI`, so use **`lightMapIntensity = Math.PI`** to reproduce
  Blender, then match the grade (Blender: AgX, look "Medium High Contrast", exposure +0.45 EV;
  three.js `AgXToneMapping` has no look, `toneMappingExposure = 2 ** 0.45`).
- **UV channel.** Set `material.lightMap = tex` and `tex.channel = 1`, which reads `TEXCOORD_1`.
- **Orientation.**
  - RGBM PNG: load with `TextureLoader` and set `flipY = false`, the glTF convention. The PNG rows
    are top-first, which matches `TEXCOORD_1` directly.
  - EXR: `EXRLoader` flips the data bottom-up. Undo that with `tex.repeat.y = -1; tex.offset.y = 1`,
    or `flipY = true`.
  - Check either way with the preview PNG.
- **RGBM decode.** Set `colorSpace = NoColorSpace` and `premultiplyAlpha = false`, and keep
  `LinearFilter`. Mipmaps on RGBM are approximate. Patch the lightmap fetch:
  ```js
  mat.onBeforeCompile = (s) => {
    s.uniforms.lmRange = { value: RANGE_SQRT };   // from manifest
    s.fragmentShader = 'uniform float lmRange;\n' + s.fragmentShader.replace(
      'vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;',
      'vec3 lmS = lightMapTexel.rgb * lightMapTexel.a * lmRange;\n' +
      'vec3 lightMapIrradiance = lmS * lmS * lightMapIntensity;');
  };
  ```
- **Don't double-light.** The bake already contains the sun, sky, lamp and every bounce. On baked
  surfaces, remove the live sun, lamp, ambient/hemisphere light and environment *diffuse*.
  three.js lights cannot be excluded per mesh, so either give baked meshes a material that ignores
  lights (MeshBasic-style with the lightMap, plus specular from the env map if wanted), or remove
  those lights from the scene altogether. Specular is not in the bake: semigloss trim, desk
  laminate and window frame reflections stay real-time (env map) or are dropped.
- **Not baked.** Monitor stand: metallic, so the diffuse pass is 0. Small props and the exterior
  are not baked either; the full list is in `excluded` in the manifest. These keep real-time light
  tuned to match.
- Lightmaps were deliberately kept out of `main` before. Commit or ship this set only on purpose.
