# Performance log

Method: `scripts/perf-suite.mjs` — headless Chrome (ANGLE/Metal, M2 Pro), 1440×900 CSS at
DPR 2, render resolution pinned (`pr=1.5`, adaptive off), **no vsync, no frame cap**, so frame
time is the real cost and a faster build shows up as a smaller number. Every comparison is
**interleaved** against the untouched baseline build (`914ffd1`, served from a git worktree)
in the same session, because the machine drifts by ~1 ms across a long run. Numbers are
frame-time p50 / p95 in ms, night (hour 21) unless stated.

Uncapped p95 is bimodal whenever the GPU is saturated (frames queue and periodically stall),
so p95 dropping toward p50 is the sign a scenario has real headroom.

## Baseline (914ffd1)

| scenario | p50 / p95 | uncapped fps | draw calls | tris |
|---|---|---|---|---|
| standing idle | 9.7 / 28.0 | 99 | 246 | 195k |
| seated idle | 10.5 / 28.4 | 92 | 168 | 132k |
| seated look | 10.4 / 27.1 | 94 | 160 | 133–145k |
| hover | 11.2 / 29.0 | 85 | 246 | 196k |

CPU profile: ~60% of main-thread samples inside `uniformMatrix4fv` / `uniform3f` — i.e. the
main thread blocked on GPU back-pressure. Render stage ≈ whole frame; interaction (raycast)
1.2–1.6 ms avg during look/hover, 5 ms max.

Attribution (seated idle, bracketed by default runs 10.5 → 10.5): AO off 6.7, AO half-res 8.1,
MSAA off 9.6, bloom off 10.2, volumetrics off 10.2. **GTAO's per-pixel work was ~3.8 ms — a
third of the frame.** WebGL timer queries are available but report ANGLE/Metal queue time, not
pass time (totals of 180–280 ms for 10 ms frames), so they are only a ranking hint.

## Changes

### Rejected: shared G-buffer for AO (MRT normals from the main pass)
Why: remove GTAO's separate normal+depth scene render (70 draw calls, all triangles again).
Measured: draw calls 167 → 98, triangles halved — and **frame time +2.3 ms worse** (seated idle
10.7 → 13.0). The second half-float MSAA attachment at full resolution plus its resolve costs
more than the old normal pass at CSS resolution. Normals-from-depth was worse still (the
denoiser reconstructs a normal per tap). Reverted. Lesson: this frame is fill/bandwidth-bound,
not draw-call-bound.

### Outline reads AO's depth instead of re-rendering the room
What: `SharedDepthOutlinePass` depth-tests the selection against the depth GTAO already
rendered; skips the glow blur chain while `edgeGlow` is 0.
Measured: hover draw calls 246 → 181, triangles 196k → 134k, CPU −0.2 ms, uncapped 85 → 88 fps.
Pixel-identical outlines on dev board and notebooks; robot identical apart from its animation.

### AO cache: recompute only when the view or on-screen geometry has changed
What: `CachedGTAOPass` reuses last frame's denoised AO while the camera has shifted < 1 CSS px
(rotation + parallax at 0.5 m) and no watched object on screen has moved; blends in place
(multiply) instead of copying the frame first.
Measured (interleaved vs baseline):

| scenario | before | after | fps |
|---|---|---|---|
| standing idle | 9.7 / 28.0 | 7.1 / 13.9 | 99 → 134 |
| seated idle | 10.5 / 28.4 | 6.9 / 13.7 | 92 → 137 |
| seated look | 10.4 / 27.1 | 9.5 / 27.3 | 94 → 100 |
| hover | 11.2 / 29.0 | 7.3 / 14.7 | 85 → 127 |

Idle view refreshes AO on ~11% of frames (camera breathing); turning the head refreshes every frame.

### Dusk shader hitch
What: the dust shader was never warmed on a daytime arrival (hidden while the lamp is off), so
the first dusk compiled it mid-frame: 50–215 ms. Warm-up now forces it visible.
Measured: `scripts/compile-watch.mjs` — zero programs compiled after load from start hours 6,
13 and 21 across a 24 h sweep, all hovers and the shelf (was +1 at hour 16.5).
