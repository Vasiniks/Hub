# Remodel: props (branch ws/model-props)

Read `.claude/briefs/_common.md` and `.claude/briefs/_remodel_convention.md` first.

Your group, in priority order:
1. **Mug** — hero close-up object: real wall thickness at the rim, a handle with a believable
   section and join, a slight throw on the body. It sits in the lamp pool and is seen at 40 cm.
2. **Bins / totes / organiser** — moulded plastic parts: draft angles, ribs, rolled rims, handles,
   compartment dividers. Currently simple scooped boxes.
3. **Books** — boards, spine curvature, headbands, visible page block with actual variation; they
   must keep working with the shelf interaction (`bookshelf.ts` slices them in metres, so keep the
   dimensions and the per-book atlas mapping compatible or update both together).
4. **Speedcube** — stickerless cube with proper pillowing, rounded cubie edges, visible seams.
5. **FRC robot** — it is the most complex prop and currently the biggest tri budget (~22k). Improve
   what reads at seated distance (frame extrusions, wheels, bumpers) without inflating the count;
   keep its animated carriage working (`userData.dynamic`, `tick`).
6. **Cable coil, screwdriver, medals, small desk items** — only what reads on screen.

Save `blender/source/props.blend`.
