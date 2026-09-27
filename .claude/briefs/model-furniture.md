# Remodel: furniture (branch ws/model-furniture)

Read `.claude/briefs/_common.md` and `.claude/briefs/_remodel_convention.md` first.

Your group, in priority order (worst-looking first, judged from the seated and standing views):
1. **Chair** — currently the most obviously CG object in the standing view. A real task chair:
   contoured seat and back with proper thickness and edge radii, lumbar detail, armrests if the
   design calls for them, gas cylinder, five-star base with real caster forks and wheels.
2. **Desk** — top with a real edge profile (not a slab), leg frame with joinery that reads,
   cable management if it suits, correct proportions against `src/scene/layout.ts` DESK.
3. **Shelf** — boards with thickness and edge treatment, real brackets/supports, back panel or
   open, whatever suits the room; must keep working with the bookshelf interaction
   (`src/scene/bookshelf.ts` — books slot in, one steps forward on gesture, so keep the slot
   geometry and dimensions compatible or update both together).
4. **Room shell** if it needs it: window frame/reveal, sill, skirting, wall/floor junctions — these
   are large on screen and currently simple boxes.

Constraints specific to this group: the desk and shelf carry gameplay (objects sit on them, books
slot in, the camera sits at the desk). Any dimension change must be reflected in
`src/scene/layout.ts` and everything that reads it, and all interaction verifies must still pass.
Save `blender/source/furniture.blend`.
