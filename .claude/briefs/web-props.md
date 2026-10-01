# Workstream: export the v2 props for the web

Read `.claude/briefs/_common.md` first, then `HANDOFF.md` §2 and §5. Branch `ws/web-props`,
worktree `~/Documents/GitHub/hub-wt-webprops`.

**Goal.** A re-runnable Blender script that turns the room's props into web-ready GLBs with their
procedural materials baked to textures and their triangle counts inside budget — plus the exported
files. You do **not** wire anything into `src/`; that is a later workstream. Do not touch
`src/scene/`, `public/assets/v2/room/` or `public/assets/v2/exterior/`.

## Why this exists

Almost every material in the Blender scene is a procedural node graph. glTF cannot carry those, so
an unprepared export arrives grey and flat. Each one has to be baked to image textures first.

## Source of truth

`blender/scene/room_public.blend`. `room.blend` is not on this machine and never will be. Props live
in `NEW_*` collections; `OLD_replaced` holds retired geometry and must never be exported. Per-asset
build scripts are `blender/scripts/v2_<name>.py` — read one before touching its asset.

## The work

1. **`blender/scripts/v2_export_web.py`**, driven like the other v2 scripts
   (`blender --background room_public.blend --python … -- <collection|all>`). Per collection:
   bake the node materials to ≤2K textures — base colour, roughness and metallic packed where it
   helps, normal — export a GLB in world space, and write a sidecar JSON with per-object triangles
   before and after, byte sizes, material list, and the names of anything emissive.
2. **Keep emission separate and named.** The runtime has to animate the robot's status lens
   (`Robot_rsl_lens`, emission 0→7 on a 4 s sine — *not* baked) and the A1 mini's screen face. Those
   must arrive as their own primitives with their own material, not merged into a parent.
3. **Budgets.** Interior total ≤350k tris. Current counts and targets:
   robot 131k→≤40k, bambu_mini 119k→≤35k, pc 155k→≤40k, electronics 106k→≤30k, medals 88k→≤12k,
   telecaster 85k→≤20k, cables 53k→≤15k, lorenz 40k→≤15k, speedcube 34k→≤12k, keyboard 32k→≤20k,
   bambu 30k→≤10k, mouse_mx 23k→≤12k, mouse 19k→≤10k, bookrack 15k→≤8k, macbook 15k→≤10k,
   lamp 10.5k→≤8k, monitor 8.6k→keep, painting 74→keep. Decimate in Blender, UV-preserving, before
   the bake, and keep the silhouette: these are seen from 40 cm at a focus pose. Where a budget
   genuinely cannot be met without wrecking the model, report the number and say why instead of
   shipping something visibly broken.
4. **The licensing gate is absolute.** Never export `NEW_tele_gb`, `NEW_teto*` (the pear — the
   *plush* `NEW_plush_teto` is fine), `NEW_redbull`, `pc_gpukit_*`, `*emblem18*`. They are already
   stripped from `room_public.blend`: **assert their absence and abort loudly if any appears**, do
   not assume. Four assets that do ship are CC BY 4.0 and require a visible credit — Teto plush
   (revsworks), MX Master 3S (Guibazilla), Bambu A1 mini (neilvfx), motherboard (Daniel Cardona).
   Add their exact credit strings to `assets/MANIFEST.md` and collect them in one
   `public/assets/v2/props/CREDITS.json` the site can render. You own `assets/MANIFEST.md` this
   phase; nobody else writes to it.
5. Run the exports through `node scripts/optimize-glb.mjs` into `public/assets/v2/props/`, with a
   `manifest.json` listing every file, its tris, its bytes and its credit obligation.

## Done means

- Every shippable prop is a GLB in `public/assets/v2/props/` with baked textures, inside budget or
  with a written reason, and the whole set's byte total is in your report.
- A render of each exported GLB (`blender/scripts/v2_render.py`, or load it back into Blender) in
  your report, so a reader can see the material survived the bake. A grey model means it did not.
- The blocked five are provably absent; show the assertion output.
- Report at `.claude/briefs/report-web-props.md` with the before/after triangle table, byte totals,
  what you could not meet, and what the assembly workstream needs to know about anchors and
  emissive parts.
