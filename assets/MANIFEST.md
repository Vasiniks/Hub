# Asset manifest

Every externally sourced asset used in the runtime, with its licence. Nothing goes in the
scene without an entry here. Assets whose licensing is unclear are not used.

| asset | source | author | licence | url | modifications |
|---|---|---|---|---|---|
| `lamp.glb` | Poly Haven | Yann Kervran, Kuutti Siitonen | CC0 | https://polyhaven.com/a/desk_lamp_arm_01 | Cone shade and desk clamp removed; flat circular head, diffuser and weighted base modelled in Blender; decimated 24k→3.8k tris; PBR textures replaced with the room's material palette |
| `textures/floor_*.jpg` | ambientCG | ambientCG (Lennart Demes) | CC0 | https://ambientcg.com/view?id=WoodFloor051 | 1K colour + normal (GL), roughness downsized to 512; roughness factor rescaled at runtime |
| `textures/wall_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=PaintedPlaster017 | normal (GL) 1K + roughness 512 only; paint colour stays the room's |
| `textures/wall_color.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=PaintedPlaster017 | albedo 512, near-white 3.4% variation: same scan's colour, mean-removed, contrast 4×, 1.6 m tile via `projectMaps`; diffuse = room colour × albedo |
| `textures/fabric_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Fabric030 | normal 512 + roughness 256; used for chair fabric and, at a coarser tile, the rug |
| `textures/fabric_color.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Fabric030 | albedo 512, near-white 4% variation: same scan's colour, mean-removed, compressed to std 14; chair 9 cm tile, rug 22 cm tile via `projectMaps` |
| `textures/desk_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Wood052 | warm pine colour 1K + normal (GL) 512 + roughness 512, 1 m tile via `projectMaps` (80 cm scan, grain along the desk's long axis); desk top, shelf boards, desk rail (replaces PaintedWood009C white laminate) |
| `textures/desk_color.jpg` | ambientCG (derived) + procedural | ambientCG | CC0 (scan portion) | https://ambientcg.com/view?id=PaintedWood009C | SUPERSEDED by Wood052 wood desk (kept for history): albedo 512, near-white 5.4% variation: luminance derived from the same scan's 1K roughness (tileable) + tileable low-freq sine mottling (20–33 cm wavelength, integer harmonics); diffuse = room colour × albedo so tone is unchanged |
| `textures/metal_rough.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Metal009 | brushed-steel roughness 512 only; metalness stays scalar (steel, aluminium, dark aluminium) |
| `textures/paper_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Paper001 | normal + roughness 256 (bin labels) |
| `textures/cardboard_*.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Cardboard002 | colour + normal + roughness 256; colour tinted back to the cardboard's tone at runtime |
| `textures/plastic_rough.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Plastic013A | fine matte-plastic roughness 256 (light plastics, keycaps, ceramic glaze) |
| `textures/plasticdark_rough.jpg` | ambientCG | ambientCG | CC0 | https://ambientcg.com/view?id=Plastic010 | roughness 256 only (dark plastics, bins, rubber) |

Untouched downloads live in `assets/source/textures/<id>/`.

## Sources checked and not usable

| source | status |
|---|---|
| Poly Pizza | API returns 401 without an account key; no anonymous download |
| Sketchfab | `/v3/models/{uid}/download` returns 401; search works, download needs an account |
| Poly Haven | open API, CC0 — **used** |
| ambientCG | open API, CC0 textures — **used** (floor, walls, fabric, desk boards, metal, paper, cardboard, plastics; walls/fabric/desk now include albedo from the same IDs) |

No CC0 model exists in the reachable open repositories for: computer mouse, TKL keyboard,
monitor, MacBook, speedcube. Those are modelled from scratch in Blender instead
(`blender/scripts/build_*.py`) — `build_mouse.py`, `build_keyboard.py`, `build_macbook.py`,
`build_monitor.py`, `build_cube.py`, `build_book.py`, `build_robot.py`, `build_chair.py`, `build_bins.py`, `build_desk_items.py` — which contain no third-party geometry, which is why the pipeline is built around authoring as well
as importing.

If you download something manually from a site that needs an account, drop the source file in
`assets/source/<name>/` and add a build script — the pipeline takes it from there.

## Texture candidates checked and rejected

| candidate | verdict |
|---|---|
| ambientCG `PaintedWood008C` (dark stained wood) | too dark for the white desk; `PaintedWood009C` used instead, relief + roughness only |
| ambientCG `Cardboard001` / `Cardboard004` | torn/worn scans with exposed fluting — wrong for the room's clean boxes; clean `Cardboard002` used |
| ambientCG `Plastic013A` normal map | dead flat (std 0.1) — roughness only; `plastic_normal.jpg` deleted |
| CC0 glazed-ceramic scan | none found on ambientCG or Poly Haven; the mug reuses the fine plastic roughness at a glossier scalar + bump from the same scan for glaze micro-variation |
| KTX2/Basis for compression | rejected: Basis transcoder WASM (~100 KB+) outweighs the saving on 824 KB of textures and adds transcode time behind the loader; WebP rejected for lossy normal-map smoothing — JPG kept, mipmaps on (all POT) |
| new downloads for plastics/metals/mug/books | rejected: small screen area; bump reuses the already-loaded roughness scans (no new downloads, no new memory), book spine weave is procedural canvas in `bookAtlas` — measured no macro change in diffuse light, kept for specular break-up only |
| ambientCG `Wood066` / `Wood027` for the desk | too dark (lum 22% / 15%): would turn 35–60% of the seated frame brown and push the room toward a wood-panelled office; warm mid-tone `Wood052` (lum 55%, 80 cm scan suits the 1 m tile) used instead |
| ambientCG `Wood061` for the desk | whitewashed near-white — same monochrome problem as the old laminate; rejected |
| new downloads for chair fabric / metals / plastics / walls (contrast pass) | rejected: Fabric030 weave enlarged via tile 9→12 cm + normal 0.8→1.0, Metal009 brushing already directional (bump 0.03→0.06), plastics split via scalars only, walls via normal 0.5→0.65 — zero new memory, keeps the total under 40 MB |
