# Perf workstream report (branch ws/perf)

Production build measured on `npx vite preview --port 5190` (production bundle:
main 866 KB / 232 KB gzip). Target window 1728x1000 CSS at DPR 2, pixel ratio 1.5
(3.9 MP); maximised 2560x1440 CSS (8.3 MP) where noted. Headed = real Chrome
window with vsync (120 Hz ProMotion); uncapped = headless `--disable-gpu-vsync`.

## Step 1 — reproduce the lag

**Steady state holds 120 fps in production.** `BASE=...:5190 real-chrome.mjs`:

| run | seated idle | seated look | hover | popup open | time sweep |
|---|---|---|---|---|---|
| hour 21 | 120.1 fps, 0 missed, frame p50 8.3 / max 9.4, cpu 1.38 | 120.1 fps, 0 missed, max 13.4 | 119.7 fps, max 16.7 | 103.5 fps, 8 missed, **max 470 ms** | 118.6 fps, 1 missed, max 33.8 |
| hour 13 | 119.6 fps, max 16.2 | 116.9 fps, 1 missed, max 45.8 | 117.6 fps, max 41.4 | 64.8 fps, 10 missed, **max 2162 ms** | 117.6 fps, 2 missed, max 32.7 |

No console errors in any run. Calibration keeps pixel ratio 1.5.

Fence-timed GPU (`bench.mjs` copies pointed at 5190), pr 1.5:

| pose | 3.9 MP look / idle | 8.3 MP look / idle |
|---|---|---|
| seatedCentre | 6.06 / 5.64 ms (cpu 0.67) | 10.96 / 11.04 ms |
| seatedRight | 6.08 / 6.00 | 14.29 / 10.76 |
| standing | 6.44 / 6.03 | 11.02 / 11.15 |

Absolute numbers are ~1 ms above `perf/LOG.md`'s 4.1–4.9 / 8.3–9.9 for both
builds — the machine was thermally loaded; only interleaved pairs compare.
Per-material (`bench-materials.mjs`, night): no material over 0.77 ms, cost
spread across the room — same conclusion as the log (~0.5 ms max).

**Stalls, not averages** (all on the prod preview):
- Sitting transition: max 24 ms night / 42 ms day (2–3 frames). Expected:
  shadows redraw every frame while the chair rolls (`main.ts` dirties both
  maps in `sitting` mode), +35 draw calls for the lamp blocker map.
- First focus/hover popup: **intermittent, render-stage, CPU-bound, zero new
  shader programs** (70 before and after). Observed maxima: 126 ms night /
  550 ms day via click; 39–189 ms via Tab+Enter; one 1331 ms outlier in an
  early diagnose run; a rerun of the same day click showed only 42 ms. So the
  hitch is real but not deterministic — a first-open cost in the focus flight
  / panel path, not a compile (program count stable) and not steady-state GPU.
- Time sweep (8 hour steps): max 25–33 ms, 1–2 missed frames over ~6 s at
  120 Hz. Consistent with spread environment captures + shadow redraws landing
  inside adjacent frames.
- Look sweep: max 25.7 ms, programs 70 → 70, no first-new-program (`diagnose`).
- `compile-watch` from hour 13: 70 programs after load, **zero after** across
  the 24 h sweep, hovers and shelf.
- GC (`gc-trace`, 10.5 s look sweep): 11 minor GCs / 53.3 ms total / max
  8.95 ms (~0.5% of wall). Higher total than the log's 11 / 6.8 ms but same
  count; not the lag.
- Startup stages (prod, 3-run avg): ready at 1096 ms (assets 331, room 100,
  capture 249, compile 75, warmup 226, measure 99). One `startup-trace` run
  showed loader hidden at 4129 ms with 0.5–1.7 s gaps — a cold-cache outlier
  against the staged 1.1 s + fade; not pursued further.

**The feel is the camera spring.** `rig.ts updateLook`, critically damped,
stiffness 4.2² / damping 2·4.2 (ω = 4.2 rad/s). Step response
1−(1+ωt)e^(−ωt): **27% at 0.24 s, 62% at 0.5 s, 92% at 1 s**. Measured with a
Playwright edge-step on prod: 25% at 0.23 s, 63% at 0.5 s, ~90% at 1 s,
full settle ~2.3 s. A cursor jump takes about a second to become a view.
That is design (the head gathers speed so a click registers before the view
turns), but it is what "lags" feels like — the GPU frame does not.

## Step 2 — prebake

1. **Particles: already baked — no change.** `src/scene/dust.ts` is exactly
   what the brief asks for: `position` + `seed` (phase/speed/twinkle) buffers
   are written once at creation and never flagged for upload; all motion
   (wander from `uTime`, cone test, twinkle, near fade, point size) lives in
   the vertex shader. Per-frame CPU is `update()`: visible toggle + three
   uniform writes (`uTime`, `uIntensity`, `uCos`), zero when the lamp is dark
   (`visible = false` at intensity ≤ 0.04, i.e. all of daylight). 190 additive
   points; night-vs-day bench idle differs by noise (5.88 vs 5.95 ms).
   Hour-21 frozen screenshots are stable across runs (0.11–0.25 mean, inside
   the 0.11–0.35 same-build noise floor measured below).
2. **Deferred irradiance buffer: rejected as too invasive, with numbers.**
   - The rect lights' diffuse — the static part this would bake — is already
     baked into 96³ volumes per light (`areaLights.ts`); image vs per-pixel
     integral is 0.22–0.56 mean (noise).
   - What remains per light is 0.2–0.6 ms diffuse each (log §3 + bench
     features: lamp ~0.6–1.5 total incl. specular/shadow, sun ~0.6–0.9,
     env ~1.0). Total addressable ≈ 0.7–1.5 ms on a frame that is
     **display-limited** (120 fps, renderer uses ~4.5–6 ms of the 8.3 ms
     budget).
   - Cost of the scheme: evaluate sun/lamp/rect diffuse per AO snapshot,
     reproject in the forward pass, keep a forward path + per-geometry flag
     for everything dynamic (robot carriage + RSL, rolling chair, stepping /
     presenting books, spinning polyhedron, dust, 30 Hz Lorenz screen,
     attention dots, hover outline), keep specular + shadow terms per pixel —
     shader surgery across ~40 materials. And the hard requirement stands:
     **time of day must animate smoothly** (day → golden → evening → night +
     transition sweep); sun and lamp move continuously, so they stay dynamic
     and only hemi/env would freeze — the smallest slice.
   - Fallback (Blender lightmap for the static room, sun+lamp dynamic) falls
     to the same objection the log already recorded: needs a UV2 unwrap for
     partly procedural geometry about to be replaced, for the same ~1 ms.
   - Revisit only if the scene gets materially more expensive.
3. **Environment capture / lamp blocker / MSAA: measured, kept as-is.**
   - MSAA 2×: a 3-round interleaved A/B on prod was drift-dominated
     (pose0 −1.4 ms, pose2 −0.5 ms, pose1 inverted). Cannot overturn the
     log's kept measurement (0.8 ms for edge crawl while turning — exactly
     what this room does most). Kept.
   - Lamp blocker map (512 px, 12+12 taps): already gated on shadow redraw;
     sitting dirties every frame by design because the chair moves. Sitting
     p50 stays ~5–6 ms with max 42 ms. Not worth gating further.
   - Environment capture is already spread (one face/frame + PMREM after);
     captures land inside the time-sweep's 1–2 missed frames at 120 Hz and
     inside budget at 60 Hz. Accepted; shrinking the 128 px cube is a
     follow-up, not taken blind.

## Definition of done

- Interleaved numbers: tables above (prod preview 5190, headed real-Chrome +
  fence bench at both viewports). No code changed, so there is no before/after
  delta to claim — the numbers *are* the after, matching the log's
  display-limited verdict.
- Frozen-grain diffs: same-build repeat on prod (`compare-variants`, hours
  13+21, 4 views): **0.11–0.35 mean** — noise floor, no visual change (no code
  change to diff).
- Verifies (all against prod 5190 via port-patched copies in `./tmp/`, plus
  `tsc` clean and `compile-watch` zero-after-load): room, a11y, shelf,
  shelf-a11y, gesture (PASS one-book-per-gesture), books (PASS never-overlap),
  motion/reduced-motion, ao-motion (idle 100% full / sweep 88% half) — **all
  green, no console errors**.
- `perf/LOG.md`: appended § "Perf workstream (ws/perf)" with kept/rejected.
- Report: this file.

## Left for follow-up (not taken)

- Intermittent first-focus hitch (40–550 ms, worst 2162 ms headed day) in the
  focus-flight/panel path. Isolated to render stage, CPU-bound, no new
  programs, first-open only, day worse than night. Needs a deterministic repro
  (Chrome trace with `?gpu`) before any fix — not a blind change.
- Camera-spring feel (~1 s settle). Retune needs design approval; numbers above
  are the case for/against.
- Env-cube 128 → 64 px if 120 Hz time-scrub misses matter. Measure first.
- `startup-trace` cold outlier (4.1 s vs staged 1.1 s). Re-run cold/warm pair
  if startup regresses.
