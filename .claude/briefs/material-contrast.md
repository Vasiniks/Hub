# Follow-up: give the room real material contrast (branch ws/textures)

The owner reviewed your last pass and chose the direction: **material contrast**, not more
micro-detail. Your scanned relief is honest work but it is invisible on a near-monochrome room —
white desk, white plastics, grey walls, everything the same matte response. The room reads as
untextured because nothing differs in *material*, not because the grain is too fine.

## The change
Keep the layout, the lighting and the composition. Change what the surfaces are made of:

1. **Desk top → warm wood.** This is the hero surface (35–60% of the seated frame). A real wood
   desk: visible grain direction along the desk's long axis, plank/board character if it suits,
   warm mid-tone that still lets the white props read against it. Everything in this room is lit
   by a cool window and a warm lamp — a warm desk is what makes both lights legible.
   Keep the desk's *value* sensible: it must not swallow the white MacBook/keyboard or kill the
   lamp pool. Check at hours 13, 18.5 and 21.
2. **Chair → visible fabric.** Weave that reads at seated distance, with sheen falling off at
   grazing angles. The chair is the most obviously CG object in the standing view.
3. **Metals → brushed and directional.** Desk legs, monitor arm, lamp: anisotropic-looking brushed
   highlights (a directional roughness/normal is enough — do not add a new BRDF) so they catch the
   window as metal, not as grey plastic.
4. **Plastics → split matte and satin.** Right now keycaps, bins, monitor shell and mouse share one
   response. Separate them: keycaps matte with fine moulding grain, bins slightly satin, monitor
   shell darker satin, rubber dead matte.
5. **Walls** stay close to now, but give them enough tooth to catch raking window light.
6. **Shelf boards and books**: wood for the boards, cloth/paper differentiation on spines.

Sources: ambientCG + Poly Haven, CC0 only, verified and recorded in `assets/MANIFEST.md` as before.

## Judgement, not just metrics
You are allowed to change colour here — that is the point. But:
- The room must stay the same *designed* room: cinematic, restrained, cool daylight + warm lamp.
  Not a brown wood-panelled office.
- Look at your own pair sheets at all four hours (13, 18.5, 20, 21.5) in the seated, standing,
  deskRight and shelf views, and judge whether each surface now reads as a material. Say so
  honestly in the report, including anything you think went too far.
- Re-check the daylight speedcube saturation guard (`scripts/bloom-score.mjs`) — a warm desk
  bouncing into the frame can change it.

## Budgets (unchanged)
+0.5 ms max on seated look, interleaved A/B in both orders; texture memory under ~40 MB;
startup within 15%; all verify scripts green; `tsc` clean.

Append to `.claude/briefs/report-textures.md`, commit on ws/textures.
