# Website follow-ups from the Blender remodel

Changes made in `blender/scene/room.blend` that the three.js runtime does not have yet. None of this is
wired into `src/` — it is a to-do list for the web pass (non-Blender work → OpenCode).

## Lighting (owner: "update lighting in the website too")
- **Lamp light is a circle.** Blender now has a round diffuser (Ø ~68 mm) and a disk area light under the lamp head
  (`blender/scripts/v2_lamp.py`). The web lamp (`src/scene/lampDisk.ts`, PCSS disk) must match: circular emitter at the
  new head position, circular pool on the desk, warm white (~#ffdbad).
- **Lamp body is all white plastic** (was aluminium) — update the lamp retint in `src/scene/desk.ts`.
- **Afternoon (15:00) is the main time.** Blender reference: sun el ≈21.4°, az ≈-0.035 rad, colour ≈#ffe6c4
  (interpolated from the 13h/16h keys in `src/scene/lighting.ts`). Re-check exposure/sun balance against Cycles renders.
- **Single-pane window + curtains** change how the sun enters: no mullion/transom shadow any more, and the curtains
  (linen, translucent) should glow and cast soft shadows at the window edges.
- **Room is 0.55 m wider** (left wall -0.30 m, right wall +0.25 m): `ROOM.leftWallX`/`rightWallX` and `SHELF.x` in
  `src/scene/layout.ts`; area-light volumes and AO snapshot bounds may need re-baking/recomputing.

## Assets to export and wire in
- New parts in `blender/scene/parts/*.blend` (mouse, macbook + riser, keyboard, medals, telecaster stand, tele_gb,
  curtains, painting, and in-progress: cables, electronics/mug/notes, speedcube, monitor) need GLB export through the
  existing pipeline (`scripts/optimize-glb.mjs`) and hookups in `src/scene/*`. Procedural Blender materials will need
  baking to textures (or re-authoring in `materials.ts`) — they don't export to glTF as-is.
- **Medal sway**: `medals.glb` carries a 4 s looping armature action `medals_sway`; the runtime must play it
  (AnimationMixer), at least while the lamp/desk is in focus.

## Licensing decisions blocking the web build
- `tele_gb` (Greg Bennett FA1 T-style, Sketchfab **Free Standard**, not CC): shipping it as a served GLB is a grey area.
  Owner decision needed (see `assets/MANIFEST.md`).
- Teto plush / Teto pear (owner downloads): licence to be confirmed before they ship.
