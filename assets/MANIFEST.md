# Asset manifest

Every externally sourced asset used in the runtime, with its licence. Nothing goes in the
scene without an entry here. Assets whose licensing is unclear are not used.

| asset | source | author | licence | url | modifications |
|---|---|---|---|---|---|
| `lamp.glb` | Poly Haven | Yann Kervran, Kuutti Siitonen | CC0 | https://polyhaven.com/a/desk_lamp_arm_01 | Cone shade and desk clamp removed; flat circular head, diffuser and weighted base modelled in Blender; decimated 24k→3.8k tris; PBR textures replaced with the room's material palette |

## Sources checked and not usable

| source | status |
|---|---|
| Poly Pizza | API returns 401 without an account key; no anonymous download |
| Sketchfab | `/v3/models/{uid}/download` returns 401; search works, download needs an account |
| Poly Haven | open API, CC0 — **used** |
| ambientCG | open API, CC0 textures — available for a later texture pass |

No CC0 model exists in the reachable open repositories for: computer mouse, TKL keyboard,
monitor, MacBook, speedcube. Those are modelled from scratch in Blender instead
(`blender/scripts/build_*.py`) — `build_mouse.py`, `build_keyboard.py`, `build_macbook.py`,
`build_monitor.py`, `build_cube.py`, `build_book.py`, `build_robot.py`, `build_chair.py`, `build_bins.py`, `build_desk_items.py` — which contain no third-party geometry, which is why the pipeline is built around authoring as well
as importing.

If you download something manually from a site that needs an account, drop the source file in
`assets/source/<name>/` and add a build script — the pipeline takes it from there.
