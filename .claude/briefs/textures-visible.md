# Follow-up: make the materials actually read (branch ws/textures)

Your first pass is honest work — scanned relief + roughness, re-fitted scalars, no perf cost — but
the owner's complaint stands: **at seated distance the room still reads as flat colour.** A
before/after splice of the seated day view is nearly indistinguishable. Roughness-and-normal-only
preserves the old look by construction; that was the wrong target.

## The target now
Every large surface should read as *a material* in a still frame, at seated distance, without the
viewer looking for it — while staying the same cinematic, restrained room. Specifically:

- **Desk top**: a laminate/painted surface with faint colour variation and grain, not one flat white.
  Add an albedo map (very low contrast — think 3–6% luminance variation), keep the existing tone.
- **Walls**: painted plaster with slight mottling and a real roughness break-up, visible in raking
  light from the window.
- **Floor**: wood with actual grain direction and plank variation (if it is wood) — currently flat.
- **Chair fabric / rug**: visible weave at seated distance; this is the surface most obviously "CG"
  right now.
- **Keycaps / plastics**: fine moulded grain; **metals**: brushed anisotropy direction that catches
  the window; **mug**: glaze with a subtle throw-line or micro-variation.
- **Shelf boards / books**: wood grain and cloth/paper spine variation.

Use albedo + roughness + normal where the surface earns it. ambientCG and Poly Haven are CC0 —
verify and record. Tile in metres via `projectMaps` so the scale is physically plausible (a desk
laminate repeat of 1 m is fine; a wood floor plank repeat should match plank size).

## Acceptance (measure, do not eyeball once)
1. A 40 cm macro crop of each treated surface must show the material clearly.
2. The **seated** and **standing** frozen-grain diffs vs the current branch state must be clearly
   above the noise floor on the surfaces you treated (mean well over 1.0 where that surface fills
   the frame) — and you must look at the pair sheets and confirm the change reads as *material*,
   not as noise or as a visible tiling pattern.
3. No tiling repeat visible at seated distance on any surface (check the widest view).
4. Frame cost: interleaved A/B, both orders, at `VIEWPORT=1728x1000` pr 1.5. Budget **+0.5 ms max**
   on seated look. Texture memory: keep the total under ~40 MB GPU; say what it is.
5. Startup within 15% of current.
6. All verify scripts green, `tsc` clean.

## Watch out for
- The grade and AgX tone mapping flatten low-contrast detail — check your maps *in the room*, not
  in isolation, and push contrast until it survives the grade (then stop).
- Normal maps at grazing angles on the desk can look like dents. Keep strength honest.
- Do not lose the established palette: these are surface treatments, not a recolour.

Append to `.claude/briefs/report-textures.md` and commit on ws/textures.
