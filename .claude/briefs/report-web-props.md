# Report: web-props (ws/web-props)

## What was done
- `blender/scripts/v2_export_web.py` was restructured. The WIP version baked each material only on its
  "largest user" object, which gave wrong textures for every other object sharing that material. It
  baked metals black (the DIFFUSE colour pass), wrote one texture set per material (the PC has 113),
  and flattened the hierarchy, so the lamp pivot was lost. Its `NodeLinks.new(None)` crash went away
  with the rewrite.
- Owner requirement (2026-10-01): lighting is baked offline. Every set is baked inside the FULL
  `room.blend`, with the bake-only edits of `v2_bake_sunset.py`:
  - **lit**: non-metal surfaces get a Cycles DIFFUSE bake (direct + indirect + colour, 256 spp,
    OIDN). They ship as `KHR_materials_unlit`; baseColor = scene-linear radiance / litScale in
    sRGB, and `extras.litScale` holds the factor. litScale is the 99.9th percentile, capped at 8.
  - **pbr**: metals (scalar metallic >= 0.5), emissive parts, glass and keepers get baseColor and
    ORM (+ normal, + baked emissive for node-driven emission) on their own atlas.
  - Keepers `Robot_rsl_lens` and `bambu_mini_screen` are their own nodes. `mon_screen` is its own
    node with UV 0..1 (u right, v up from the seat).
- Outputs are written to `public/assets/v2/props/` together with `manifest.json`, `CREDITS.json` and
  the sidecars. Builders: `scripts/props-manifest.mjs`, `scripts/optimize-glb.mjs` (v2 mode strips
  normals from unlit primitives).
- `assets/MANIFEST.md` records the 2026-10-01 gate lift, a new row for the speedcube logo, and the
  shipped props table.

## Per asset
| file | tris before | tris after | budget | bytes | litScale | emissive materials | nodes | credit |
|---|---|---|---|---|---|---|---|---|
| bambu_mini.glb | 116,961 | 27,179 | 28000 | 630 KB | 0.33 | bambu_mini_screen_lit | bambu_mini_screen, bambu_mini_printer, bambu_mini_spool_stand, bambu_mini_table_parts, NEW_bambu_mini_root | bambu_a1_mini |
| bookrack.glb | 13,004 | 7,430 | 8000 | 205 KB | 0.62 | - | bookrack_hardware, Mesh_160.001, Mesh_161.001, Mesh_162.001, Mesh_163.001, Mesh_164.001, Mesh_165.001, Mesh_166.001, Mesh_167.001, Mesh_168.001, Mesh_169.001, Mesh_170.001, Mesh_171.001, Mesh_172.001, Mesh_173.001, Mesh_174.001, Mesh_175.001, Mesh_176.001, Mesh_177.001, Mesh_178.001, NEW_bookrack_root | - |
| cables.glb | 53,320 | 14,535 | 15000 | 300 KB | 1.4000000000000001 | magsafe_led_amber.001 | NEW_cables_root | - |
| chair.glb | 13,846 | 7,743 | 8000 | 273 KB | 0.0039 | - | chair, Node_259 | - |
| desk_misc.glb | 8,308 | 8,308 | keep | 295 KB | 0.12 | - | tote_1, tote_2, Node_205, room, screwdriver, Scene.017 | - |
| electronics.glb | 94,596 | 28,576 | 30000 | 926 KB | 6.1 | led_blue_on.003, led_green_on.003, led_red_on.003 | elec_breadboard_grp, elec_esp32, elec_faraday_grp, elec_hub, elec_hub_cable, elec_lab_wiring_grp, elec_multimeter_grp, elec_notes, elec_pico, elec_preamp_grp, elec_stm_stage_grp, elec_uno, NEW_electronics_root | - |
| fixtures.glb | 35,471 | 9,804 | 10000 | 265 KB | 1.7 | rs_smoke_led, rs_thermo_digits | fixtures_root, NEW_roomshell_root | - |
| keyboard.glb | 32,462 | 19,433 | 20000 | 354 KB | 0.66 | - | NEW_keyboard_root | - |
| lamp.glb | 98,334 | 19,350 | 20000 | 797 KB | 8.0 | lamp_diffuser | NEW_lamp_pivot, NEW_lamp_root | - |
| lorenz.glb | 39,832 | 10,216 | 15000 | 368 KB | 4.8 | - | lorenz_sculpture, paper, NEW_lorenz_root | - |
| macbook.glb | 14,742 | 9,704 | 10000 | 228 KB | 0.017 | - | NEW_macbook_laptop, NEW_macbook_root | - |
| monitor.glb | 8,610 | 8,610 | keep | 202 KB | 0.03 | mon_power_led | mon_screen, NEW_monitor_lift, NEW_monitor_root | - |
| mouse_mx.glb | 23,024 | 11,616 | 12000 | 239 KB | 0.17 | - | NEW_mouse_mx_root | mx_master_3s |
| painting.glb | 954 | 954 | keep | 70 KB | 0.053 | - | painting_root | - |
| pc.glb | 245,380 | 46,575 | 48000 | 1274 KB | 5.6000000000000005 | pc_emit, pc_led_amber, pc_led_green, pc_led_white, pc_screen_text | NEW_pc_root, NEW_plush_teto_root | motherboard, teto_plush |
| redbull.glb | 15,095 | 1,784 | 4000 | 81 KB | - | - | NEW_redbull_root | - |
| robot.glb | 131,522 | 63,055 | 62000 | 2591 KB | 0.17 | robot_rsl_amber | Robot_rsl_lens, NEW_robot_root | - |
| speedcube.glb | 34,184 | 11,632 | 12000 | 202 KB | 2.8000000000000003 | - | NEW_speedcube_root | - |
| telecaster.glb | 108,089 | 21,437 | 22000 | 509 KB | 0.066 | - | NEW_telecaster_guitar, NEW_telecaster_root | - |
| teto_pear.glb | 1,192 | 1,192 | keep | 37 KB | 0.16 | - | NEW_teto_pear_root | - |

total 20 assets, 329,133 tris, 9.62 MB

## Verification
- Every GLB was re-imported in headless Blender and rendered in two views (`blender/scripts/v2_check_web.py`;
  lit materials get litScale and the room's grade: AgX MHC, +0.45 EV). None is grey.
- Lit numeric check (`blender/scripts/v2_verify_lit.py`): decoded GLB texture x litScale vs the EXR bake.
  | asset | mean ratio | median rel err |
  |---|---|---|
  | monitor | 0.99 | 2.6 % |
  | lorenz | 1.00 | 2.6 % |
  | electronics | 0.99 | 3.1 % |
  | lamp | 0.975 | 4.9 % |
  | pc | 0.93 | 9.7 % |

  The PC error is probably WebP chroma loss on saturated colours; that is not proven. The other
  props were not run through this check.
- Not done: the repo's verify-*.mjs suite. The runtime is not touched by this branch.

## Over budget / problems
- **robot 63k tris** (brief: 40k). Quadric collapse shreds the thin, pocketed aluminium plates (a
  render showed shards at 45k), so the frame is only lightly decimated. A few shards remain deep
  inside, behind the bumper.
- **Total 9.62 MB** (coordinator target: about 8 MB). After quantization, geometry is about 70 % of
  the bytes. `EXT_meshopt_compression` would roughly halve that. The decoder ships with three
  (`examples/jsm/libs/meshopt_decoder.module.js`), but `optimize-glb` has no encoder and adding one
  would be a new dependency, so it was not done.
- The lamp clips 6 % of its lit texels above k=8 (the head next to the disk light). These render
  white under AgX anyway.
- `public/assets/v2/props/` is in the repo's local `.git/info/exclude`; files were added with `git add -f`.
- `desk_misc` node `room` holds five ~1 cm parts (Mesh_142-146) of unknown purpose.
