# Workstream: the street outside, at 5% of the triangles

Read `.claude/briefs/_common.md` first. Branch `ws/web-exterior`, worktree
`~/Documents/GitHub/hub-wt-exterior`.

**Goal.** The liminal Canadian suburban street in `NEW_exterior` is 373k triangles — a quarter of
the whole scene — and a visitor sees it through one window, from two camera positions 1.5 m apart.
Get it to **≤20k triangles** without losing the dusk mood the owner approved. Own only
`public/assets/v2/exterior/` and `blender/scripts/v2_exterior_web.py`.

## What matters about the viewing conditions

The window is single-pane, roughly 1.1 × 1.3 m, in the left wall of a second-floor room. The seated
eye is at Blender `(0, -0.16, 1.175)` and the standing eye at `(1.06, -0.96, 1.63)`. Parallax across
that baseline is small for anything past the near maple, which is what makes this tractable.

## Approach

Try the cheap one first and measure it before reaching for anything cleverer.

1. **Baked backdrop.** Render the exterior from the window's viewpoint in Cycles at the approved
   dusk setup, onto a curved card (or a few depth-separated layers: near tree, mid houses, far sky)
   sitting outside the glass. Keep the glowing house windows, the porch lights and the street light.
   Report the triangle count, the texture bytes and what the parallax error looks like when the
   camera moves from seated to standing — a screenshot from each pose, not an assurance.
2. **If and only if the card fails** on parallax, fall back to heavy decimation plus a baked albedo
   atlas, and report both options' numbers side by side.

Do not invent a new pipeline: follow `blender/scripts/v2_render.py` for rendering and the existing
`optimize-glb.mjs` step for any geometry you ship.

## Done means

- `public/assets/v2/exterior/` holds what the runtime needs — images, any GLB, and a sidecar JSON
  recording the camera basis, the card's world placement and the exposure the images were rendered
  at, so the runtime can match the room's grade (AgX, +0.45 EV).
- A seated and a standing screenshot in your report, next to the full-geometry Cycles render, so the
  loss is visible rather than asserted.
- Triangle count, texture bytes, and the measured cost if you can get it on screen; if you cannot
  wire it in yourself, state the numbers the assembly workstream should expect.
- Report at `.claude/briefs/report-web-exterior.md`.
