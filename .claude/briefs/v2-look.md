# Workstream: make the baked room look right

Read `.claude/briefs/_common.md` and `blender/bake/sunset/README.md` first, then open `/?v2` and
compare it with `blender/bake/sunset/compare_CAM_seat.png` and `compare_CAM_stand.png` — the Cycles
renders of the same room from the same two cameras. Branch `ws/v2-look`, worktree
`~/Documents/GitHub/hub-wt-v2look`.

**The owner's words: "the baking is terrible."** He is right that it looks wrong. Your job is to
find out *why*, honestly, and fix what can be fixed in the runtime.

## What is visibly wrong, and what is actually causing it

Work out the cause before you change anything. Some of these are runtime bugs and some are not:

1. **Black shapes all over the desk.** These are the baked contact shadows of props — monitor, PC,
   keyboard, mouse, printer — that exist in the Blender scene but have not been exported to the web
   yet. The lightmap is correct; the objects that cast those shadows are missing. That is another
   workstream's job and **you must not paint over it** by lifting the shadows out of the bake.
   Confirm this is the cause (compare against the Cycles render), quantify it, and say so.
2. **The window is a flat beige rectangle.** A placeholder background until the exterior workstream
   lands. Check whether the glass itself is being drawn and whether the curtains read correctly.
3. **Grade.** Blender used AgX, look "Medium High Contrast", exposure +0.45 EV; three.js has AgX
   with no look and `toneMappingExposure = 2 ** 0.45`. The missing "look" is a real difference in
   contrast and shoulder. Measure the gap against the Cycles references — mean and per-channel —
   and close it if a defensible tone curve does (a contrast matching the AgX look, applied in the
   grade that already exists in `GradedOutputPass`). Do not hand-tune until a screenshot "feels
   right" and call that matching.
4. **Everything is matte.** Specular is deliberately not in the bake, and the baked meshes are
   `MeshBasicMaterial`, so the trim, the desk laminate and the window frame have no reflection at
   all. Decide whether a cheap environment specular is worth adding for those materials, measure
   what it costs, and show both.

## Rules

- **Never fake the lighting.** No ambient lift, no "exposure nudge" to hide a missing object, no
  removing the lightmap. If something can only be fixed by a re-bake, write down exactly what the
  re-bake would need to change. That is a legitimate answer.
- The default room is out of scope and must stay untouched.
- Every claim gets a picture: your frame beside the Cycles reference, same pose.

## Done means

- A written cause for each of the four, with evidence.
- The fixes that belong in the runtime, applied and measured (frame cost via `window.__room.bench`).
- A short list of what only a re-bake or another workstream can fix.
- `npx tsc --noEmit -p .` clean. Report at `.claude/briefs/report-v2-look.md`.
