# Follow-up: the first-focus hitch (branch ws/perf)

Your own report found the real lag and left it untaken. Take it now — it is the single most
user-visible stall in the room: **clicking an object to open its panel hitches 40–550 ms, worst
observed 2162 ms (headed, day), 8–10 missed frames, first-open only, CPU-bound in the render
stage, with zero new shader programs.**

## Get a deterministic repro first
- Headed Chrome, production preview on 5190, hour 13 (day was worse than night).
- Fresh page load each attempt; the hitch is first-open only, so one attempt per load — script it
  to loop: load → sit → hover `dev-board` → click → record `window.__room.perf` max frame → reload.
  Run it ~10 times per condition and report the distribution, not one number.
- Bisect *what* is first-time in that path. Candidates, all testable by forcing them during warm-up
  and seeing whether the hitch moves: the outline pass's first real selection (its mask/edge
  chain runs with a new selected set), the panel DOM/CSS first paint and its backdrop-filter,
  the focus flight's first `setFov` + projection change (it invalidates AO's snapshot and forces a
  full-resolution recompute plus a volumetric re-march), the first BVH raycast against a geometry
  whose tree was not built yet, a texture/mipmap upload on first close-up, or a GC spike.
- Use `?gpu` (per-pass GPU timing), `scripts/diagnose-stall.mjs`, `scripts/gc-trace.mjs`, a Chrome
  performance trace, and `renderer.info` before/after. CPU-bound + render-stage + no new programs
  is a strong hint: something is being *built* on the main thread inside the render call.

## Then fix it
Warm it behind the loading bar like the existing warm-up does for shaders and shadow variants
(`renderer.ts warmUp`, `lighting.ts warmShadows`), or move it off the first click. Whatever you
find, the fix must not add more than ~50 ms to startup (currently ready ≈1.1 s + fade).

## Done means
Ten loaded-fresh click attempts per hour (13 and 21) before and after, reported as
min/median/max frame time and missed frames; all verify scripts green; `perf/LOG.md` updated;
report appended to `.claude/briefs/report-perf.md`.
