# Performance log

Method: `scripts/perf-suite.mjs` — headless Chrome (ANGLE/Metal, M2 Pro), 1440×900 CSS at
DPR 2, **no vsync, no frame cap**, so frame time is the real cost and a faster build shows up as
a smaller number.

**Correction:** the suite asked for a pinned `pr=1.5`, but startup calibration ignored pinning and
stepped both builds down to **1.25** — every uncapped table below was measured at 1.25 (the
same ratio calibration chooses for real visitors on this machine). Baseline and working tree had
the identical behaviour, so the before/after comparisons stand. Calibration now respects `?pr=`. Every comparison is
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

## Visual fix: speedcube washout in daylight (not a performance change)

Cause, measured on a parked daylight close-up (`scripts/cube-color.mjs`, mean HLS saturation of
the cube's coloured faces): default 0.13 · volumetrics off 0.13 · grade off 0.10 · **bloom off
0.75**. Not the atmosphere — bloom. Its threshold applied to the pre-exposure HDR image, so by day
(exposure 0.47) the whole sunlit desk crossed it, and near-equal weights on the widest blur levels
spread that over everything nearby.

Fix: threshold divided by exposure (means the same on-screen brightness every hour) and per-level
weights `[1.2, 0.8, 0.25, 0.08, 0.05]` — halos come from tight levels, the veil from wide ones.
Rejected on measurement: energy-above-threshold extraction (fidelity 0.20–0.27 and changed the
night look), lower thresholds (made the monitor-lit MacBook lid bloom).
Scored with `scripts/bloom-score.mjs` + `.py`: cube saturation 0.17 → 0.47 (0.70 with no bloom);
night frame difference 2.16 — the same as grain/dust noise (bloom-off vs old is 2.26).

### Picking: BVH per geometry
What: `three-mesh-bvh` trees for every pickable geometry, built in idle callbacks after the
reveal (library dynamically imported then — a 48 kB lazy chunk; main bundle +22 kB for shared
three.js classes); raycasters use `firstHitOnly`.
Why: stock raycasting walks every triangle of the room's merged meshes, whose bounding spheres
span the room — 1.5–2 ms per ray, and a pick casts one ray plus one per nearby attention dot.
Measured: per ray 1.46 → 0.08 ms with identical nearest hits and distances. Interaction stage:
seated look 1.52 avg / 5.0 max → 0.13 / 1.1 ms; hover 1.20 / 4.1 → 0.06 / 0.4 ms. Tree build
109 geometries in idle time; startup trace shows no frame over 16.8 ms after the reveal.

### Allocation and main-thread hygiene
- Objects that can never be picked (dust, city lights, attention dots) get a no-op raycast. They
  were intersected and filtered afterwards; a Points raycast allocates a vector per point within
  a metre of the ray.
- `screenOf` returns a scratch object (ran several times per target per frame); the hover label
  writes its style only when its rounded position changes.
Measured (`scripts/alloc-profile.mjs`, look + hover): sampled allocation 158 → 134 KB/frame, the
remainder inside three's render path. GC over an 8.7 s look sweep (`scripts/gc-trace.mjs`):
baseline 35 minor GCs / 10.9 ms; now 11 / 6.8 ms, longest 2.1 ms — well under 0.1% of wall time.

### Measured and left alone
- Lorenz screen (30 Hz canvas repaint + upload): ~0.1 ms/frame (`?lorenz=0` A/B, 163 → 166 fps).
- Reflection capture: frames inside a capture cost 10–13.7 ms uncapped vs 6.3 quiet — still
  inside 60 Hz, only when the lit state drifts, ≥1.5 s apart. Zeroing `environmentIntensity`
  instead of nulling the environment (to avoid program switches) measured no difference; reverted.

## Real 60 Hz pacing (`CAPPED=1`, calibration as a visitor gets it — chose 1.25 in both builds)
No missed frames in any scenario at any hour, baseline or now. Main-thread CPU per frame, avg/p95:

| scenario | baseline | now |
|---|---|---|
| seated look | 3.0–3.1 / 6.0–6.5 | 1.4–1.5 / 2.2–2.4 |
| hover | 3.3–3.5 / 5.6–5.9 | 1.4 / 2.1–2.2 |
| standing look | 2.8–3.0 / 4.0–4.6 | 1.7 / 2.3–2.4 |
| popup open | 1.3–1.5 / 1.7–2.8 | 1.0–1.2 / 1.7–2.4 |

Draw calls: seated idle 168 → 96, hover 246 → 109, popup 150 → 77. Triangles in popup 103k → 38k.

## Resolution cliff (open question for the visual pass)
Truly pinned at 1.5, the full pipeline costs 17–20 ms uncapped (37–49 fps under vsync) against
6–10 ms at 1.25: ~2× cost for 1.44× pixels, not explained by MSAA (msaa 0/2/4 all show it).
Calibration correctly lands on 1.25 on this GPU. Making 1.5 affordable would need fewer
full-resolution post passes (e.g. merging tone mapping with the grade, compositing the
volumetrics in place) — measured headroom, not yet spent.

### Two fewer full-resolution post passes
What: tone mapping + colour encoding + grade in one pass (`GradedOutputPass`); volumetric light
added in place with additive blending instead of copying base + scatter to a second buffer.
Why: the frame is fill/bandwidth-bound (see the resolution cliff), so every full-resolution
pass matters more than draw calls.
Image: pixel diff against the previous build with frozen grain/sway (`scripts/frame-diff.mjs`)
— mean 0.29–0.43 / 255, the >4-level pixels being animated dust and volumetric jitter.
Measured (interleaved with HEAD, two rounds each, night): pr 1.25 seated idle 94.2 → 97.3 fps,
standing 94.0 → 96.8; pr 1.5 seated idle 52.4 → 53.8, look 40.0 → 41.3. Consistent ~3%.
(Absolute numbers in this block are ~50% slower than earlier blocks for *both* builds: the
machine was thermally loaded by then. Only interleaved pairs are comparable.)

## Assets and startup

### GLB quantization (pipeline step)
What: `scripts/optimize-glb.mjs` — Blender output (`assets/processed`) → `public/assets/processed`
with KHR_mesh_quantization (16-bit positions, 8-bit normals, 16-bit UVs), dedup, prune. Three's
GLTFLoader reads it natively: no decoder shipped. The loader dequantizes on arrival
(`assets.ts`: float attributes, node transforms baked, nodes reset) because the room merges static
geometry in room space, slices books in metres and animates parts by absolute position.
Measured: all 17 models 2,347 KB → 1,190 KB (robot 970 → 449). Frozen-grain pixel diff vs the
unquantized build: mean 0.28–0.36/255 — the same as animated noise between identical builds.
Only models with a sidecar request one (was a 404 per model).

### Startup
Stage timing (`scripts/startup-stages.mjs`, 5–6 cold loads, DPR 2): assets ~200–360 ms (dev
server), build ~90, env capture + setup ~155, shader compile ~55, pass warm-up ~175, calibration
560 → 491 ms (six frames decide a clear case; a leftover diagnostic burst removed). Then the
designed 420 ms bar fade, unchanged.
Loader hidden (`scripts/startup-trace.mjs`): 2.06–2.10 s → 1.72–1.90 s (4 runs, avg 1.81 s);
no frame over 16.8 ms after the reveal. Zero shader compiles after load (`compile-watch`).

### Bundle: rect-area light tables out of the JavaScript
Attribution (source map): `RectAreaLightTexturesLib` was 241 KB of the minified main bundle — two
64×64 RGBA LTC tables as ~33,000 float literals. Now a 64 KB half-float binary
(`scripts/build-ltc.mjs` → `public/assets/ltc.bin`, 50 KB gzipped) fetched behind the loading bar;
float textures are expanded from it (≤0.1% relative difference; three already uses this exact
half data where float filtering is unavailable). Frozen-grain pixel diff vs previous build: mean
0.21–0.32/255 (noise floor). Main bundle 1,095 → 848 kB, gzip 329 → 224 kB (the pass started at
928 / 279 kB); three-mesh-bvh stays a separate 48 kB lazy chunk.

## Final: 914ffd1 → now (same session, same machine; `now` measured second and hotter)

Uncapped, DPR 2, render resolution 1.25 (what calibration picks for visitors), frame p50 in ms,
averaged over night / day / golden hour. Draw calls and triangles from the final runs.

| scenario | baseline | now | change |
|---|---|---|---|
| standing idle | 13.7 | 9.6 | −30% |
| standing look | 13.7 | 10.6 | −23% |
| sitting transition | 14.5 | 14.0 | −3% |
| seated idle | 15.4 | 9.3 | −40% |
| seated look | 15.1 | 14.4 | −5% |
| hover | 16.4 | 9.9 | −40% |
| object focus transition | 16.6 | 15.4 | −7% |
| popup open | 16.8 | 9.1 | −46% |
| time transition | 16.0 (max 338) | 9.6 (max 45) | −40%, hitch gone |

Real 60 Hz (`CAPPED=1`): no missed frames anywhere, before or after. Main-thread CPU per frame
now 0.9–2.0 ms avg (baseline 1.3–3.5). Draw calls (capped runs): seated idle 168 → 93, hover
246 → 106, popup 150 → 77, standing idle 246 → 137. Triangles drawn in popup 103k → 37k.
Heap 31–50 MB sawtooth in both builds, no growth. Startup: loader hidden 2.06–2.10 → 1.63–1.83 s.
Bundle 928 / 279 kB (gzip) at the start of the pass → 848 / 224 kB. Models 2.35 → 1.19 MB with
all Tier 2 props added; textures +683 KB (new).

Where headroom is still thin: **turning the head** (seated look) recomputes AO every frame, and
the pipeline is fill-bound — pixel ratio 1.5 costs ~2× 1.25 on this GPU. Next levers, measured
but not yet spent: AO at reduced resolution only while the view moves; fewer full-resolution
post passes; temporal accumulation for AO/volumetrics.
