# Workstream: prebake the lighting and the particles (branch ws/perf)

Read `.claude/briefs/_common.md` first, then `perf/LOG.md` (the whole "Second rendering pass"
section — it tells you what is already done, what was rejected and why, and what the next lever is).

The owner says "it lags a lot". Two rendering passes already took the seated frame from ~7.4 ms to
~5.0 ms at 1728x1000 / pixel ratio 1.5, and a headed Chrome run holds 120 fps. So **first prove or
disprove the lag before optimising anything**:

## Step 1 — reproduce the lag (do this before touching code)
- Build for production and serve it (`npm run build` then `npx vite preview --port 5190`), and
  measure that, not just the dev server: `BASE=http://127.0.0.1:5190 node scripts/real-chrome.mjs 21 6`.
  Dev-mode and production can differ.
- Measure a maximised window too: `VIEWPORT=2560x1440`.
- Look for *stalls*, not averages: worst frame, missed frames, GC pauses, first-30-seconds hitches,
  environment-capture frames, shadow redraws, texture uploads, the sitting transition.
  `scripts/startup-trace.mjs`, `scripts/gc-trace.mjs`, `scripts/diagnose-stall.mjs` exist.
- Report what you actually find. If the frame is fine and the *feel* is the camera spring
  (rig.ts `updateLook`, stiffness 4.2 ⇒ ~0.24 s to catch up), say so with numbers.

## Step 2 — prebake, in this order (measure each, keep or revert)
1. **Particles.** `src/scene/dust.ts` updates dust on the CPU every frame. Bake the motion into the
   shader (per-particle phase/speed attributes, position from `uTime`) so the CPU does nothing per
   frame and the buffer never re-uploads. Same look — compare screenshots at hour 21.
2. **Static lighting.** `perf/LOG.md` describes the next lever in detail: a **deferred irradiance
   buffer** — evaluate the sun/lamp/rect-light *diffuse* once per AO snapshot, reproject it with the
   existing snapshot machinery (`src/scene/ao.ts` `ViewSnapshot`), and have the forward pass fetch it
   instead of re-evaluating lights per pixel. Estimated −0.7 ms at 3.9 MP, −1.5 ms at 8.3 MP.
   Dynamic/animated geometry must keep the forward path (see the note about a per-geometry attribute
   flag in the log). Specular stays per pixel.
   If that proves too invasive, the fallback is a Blender-baked lightmap for the static room only
   (needs a UV2 unwrap — see the Blender pipeline note in `_common.md`), with the sun and lamp kept
   dynamic. Either way: **the time of day must still animate smoothly** (day → golden → evening →
   night and the transition sweep).
3. Anything else the profile shows, e.g. the environment capture, the lamp blocker map, MSAA.

## Definition of done
Interleaved before/after numbers for seated idle / seated look / standing look / popup / sitting /
time transition at both viewports, frozen-grain image diffs, all verify scripts green, `perf/LOG.md`
updated with kept and rejected experiments, report at `.claude/briefs/report-perf.md`.
