# Asset manifest

Every externally sourced asset used in the runtime, with its licence. Nothing goes in the
scene without an entry here. Assets whose licensing is unclear are not used.

| asset | source | author | licence | url | modifications |
|---|---|---|---|---|---|
| `lamp.glb` | Owner-supplied `assets/source/lamp-owner/lamp.stl` + Blender-modelled head | Owner (STL base+arm); head/assembly by workstream | Used with owner permission (STL is NOT CC0 and is not claimed as such); head geometry original, no third-party | n/a (supplied file, not downloaded) | STL weld (178 duplicate verts merged, 3516→3160 tris), normals outward, shade smooth 34°/30°; oval head (26.9×20.6u, equiv. dia 23.5u = 313mm at height scale, incompatible with 130mm disk light) discarded; base+stem (0–0.147m) scaled XY 0.6596 about its centre to 176mm dia (fits desk, same as before); rods+knuckle (0.147–0.54m) unscaled; joined+welded (3 verts, 1970 tris body); new flat circular head outer 85mm / glass 73mm / disk 65mm (same as before, so lighting.ts unchanged), cantilevered 85mm forward with central 12mm neck (side yokes miss 60mm ball by 9–94mm in X); smart-project UVs (STL has none); 3282 tris total (was 5112), 109KB source → 55KB public (was 215KB → 102KB); PBR palette lamp_metal/lamp_dark/lamp_diffuser (same hex as before) |
| `textures/floor_*.jpg` | ambientCG | ambientCG (Lennart Demes) | CC0 | https://ambientcg.com/view?id=WoodFloor051 | 1K colour + normal (GL), roughness downsized to 512; roughness factor rescaled at runtime |
| `textures/wall_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=PaintedPlaster017 | normal (GL) 1K + roughness 512 only; paint colour stays the room's |
| `textures/fabric_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Fabric030 | normal 512 + roughness 256; used for chair fabric and, at a coarser tile, the rug |

Untouched downloads live in `assets/source/textures/<id>/`.

## Sources checked and not usable

| source | status |
|---|---|
| Poly Pizza | API returns 401 without an account key; no anonymous download |
| Sketchfab | `/v3/models/{uid}/download` returns 401; search works, download needs an account |
| Poly Haven | open API, CC0 — previously used for the lamp arm (`desk_lamp_arm_01`), now replaced by the owner STL; no Poly Haven geometry remains in the runtime |
| ambientCG | open API, CC0 textures — **used** (floor, walls, fabric) |

No CC0 model exists in the reachable open repositories for: computer mouse, TKL keyboard,
monitor, MacBook, speedcube. Those are modelled from scratch in Blender instead
(`blender/scripts/build_*.py`) — `build_mouse.py`, `build_keyboard.py`, `build_macbook.py`,
`build_monitor.py`, `build_cube.py`, `build_book.py`, `build_robot.py`, `build_chair.py`, `build_bins.py`, `build_desk_items.py` — which contain no third-party geometry, which is why the pipeline is built around authoring as well
as importing.

If you download something manually from a site that needs an account, drop the source file in
`assets/source/<name>/` and add a build script — the pipeline takes it from there.
