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

> **Correction (rendering pass, below):** this "cliff" was a bug, not the GPU. `EffectComposer` was
> constructed with a render target sized in device pixels, took that as its CSS size and applied
> the pixel ratio again, so every post buffer ran at ratio² — "1.25" was really 1.5625 and "1.5"
> was 2.25 — until a window resize happened to correct it. Headless runs never resize. Every
> pinned-ratio number in the tables above is at ratio². Comparisons stand (both sides had the bug).

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

# Rendering pass: precompute what can be known, and stop shading what cannot be seen

Method changes for this pass:
- **Fence timing.** `window.__room.bench(pose)` (`src/debug/bench.ts`, debug-only, lazy) parks the
  camera, pauses the loop and times N composer renders between two `fenceSync` waits: real GPU
  completion, not queue time. Feature costs are A/B toggles alternated inside one page load.
  `scripts/bench.mjs` (per pass/light/feature), `scripts/bench-materials.mjs` (per material),
  `scripts/bench-ab.mjs` (URL variants in interleaved page loads, three seated poses; "look" forces
  AO to recompute every frame, "idle" reuses it).
- **Image checks.** `scripts/compare-variants.mjs` + `.py`: reduced motion, `lorenz=0`, parked
  views (seated, desk right, shelf, standing), mean/>8-level pixel diff against a reference variant
  and side-by-side sheets. Same-build noise floor ≈ 0.3–0.6 mean. `scripts/lamp-shots.mjs`: night
  close-ups of the lamp pool.
- True pixel ratio 1.5 (the fix above), 1440×900 CSS at DPR 2 = 2160×1350 rendered.

## Where the 10.8 ms went (seated, turning, pr 1.5, before this pass)

| cost | ms |
|---|---|
| scene render (MSAA 2×) | 5.1–5.6 |
| · rect-area lights (4) | ~4.0 — specular ~2.1, diffuse ~1.2 (interleaved toggles) |
| · lamp / sun / environment | 0.7 / 0.3–0.6 / 0.3–0.6 |
| GTAO (recomputed every turning frame) | 3.2–3.4 — AO shader 2.5–2.7, normals 0.7, denoise 0.7 |
| bloom / volumetric | 0.5–0.7 / 0.3–0.8 |
| CPU submission | 0.5–0.8 |

GPU-bound: CPU is under a millisecond, draw calls ~160, shadow-map redraws already rare and cheap.
The time was per-pixel integrals re-evaluated every frame for answers that barely change.

## 1. Rect-area light specular → environment probe + near field

What: three evaluates an LTC polygon integral (plus two LUT fetches) for every rect light's
specular on every pixel. Now (`src/scene/areaLights.ts`):
- Diffuse stays per pixel, exact, but skips a light where the bound
  4·|hw|·|hh|·max(radiance)/d² < 0.0005 — the shelf strip and desk spill are invisible almost
  everywhere on screen.
- **Large emitters (the window)** get their specular from the probe: a pane at the light's
  radiance (÷ environment intensity) on a reflection-only layer is drawn over the cube capture,
  unoccluded like the integral. The capture is filtered twice — once without panes for irradiance
  (materials read it through a shared `envMapIrradiance` uniform), once with them for radiance — so
  the window is not counted twice in diffuse. Capture already happens only when the light drifts.
- **Small emitters** keep the LTC specular only within 70 cm, where a room-centred probe is wrong:
  the monitor 30 cm from the laptop lid.

Measured (interleaved, pr 1.5): look 10.5 → 8.2, idle 7.2 → 4.6 ms, day and night alike.
Image vs `?arealights=pixel`: seated 1.05–1.64, desk 1.07–1.10, shelf 0.89–1.82, standing
0.95–1.99 mean — the remainder a faint window sheen on the floor (probe parallax).

Rejected on the way:
- Specular simply dropped: saved the same but the laptop lid went from white to dark navy, day and
  night (mean diff 5–7 seated).
- Window pane in the probe without the split filter: the lid came back, but the room brightened
  (window counted twice in irradiance; standing 5.4 mean diff).
- Pane only for the window, no near field: lid still dark at night (monitor reflection is near
  field). Near field costs no measurable time (8.36 vs 8.16 ms, noise).
- **Per-vertex diffuse** (form factor in the vertex shader, receivers tessellated): a further
  ~0.8 ms, but near-field banding where a small light sits close to a large face (shelf strip on the
  back wall at night). Per-vertex diffuse with per-pixel specular saved nothing — specular was the
  cost. Removed.

## 2. AO at half resolution while the view moves

What (`src/scene/ao.ts`): while the view sweeps (> 0.6 CSS px/frame) or on-screen geometry keeps
invalidating, depth/normals, trace and denoise all run on half-resolution targets (denoise radius
halved to keep its footprint). Still for 0.12 s → full resolution computed once and crossfaded in
over 0.2 s. Idle breathing stays below the motion threshold, so a resting view is always full
resolution. Outline and light shafts read the half depth while moving: pixel-identical outline.

Measured: AO recompute 3.3 → ~0.8 ms. Seated look 8.1 → 6.0 (half AO) → 5.4 (half G-buffer too).
Image, still vs forced-moving path: 0.3–0.6 mean — thin geometry (lamp arms) gains a faint halo
at half resolution, which is why it never shows at rest. `scripts/verify-ao-motion.mjs`: idle 100%
full, sweep 88% half, back to full after the camera's glide settles (~1.2 s after the mouse stops).

Considered and not done: temporal accumulation (reprojection ghosting on the chair, books and
robot; the half-resolution path already recovers most of the cost); baked AO (desk-scale contact
occlusion between props is exactly what vertex/lightmap AO on this geometry cannot hold, and GTAO's
remaining cost while turning is under a millisecond).

## 3. Window pane: image lighting only

The pane covers a third of the seated view and was shaded with every direct light. The sun and
the window light are behind it, monitor and shelf face away, and the lamp is already in it via the
probe (its diffuser is in the capture). `imageLightingOnly` keeps IBL and ambient, drops the
direct loops. −0.2 to −0.6 ms by pose; image diff 0.22–0.41 mean (noise floor), day/golden/night.

## 4. The lamp as a disk (visual; costs ≤0.4 ms at night)

See `src/scene/lampDisk.ts`. PCSS: blocker search (12 taps) on a float depth map of the casters —
redrawn only when the lamp's shadow map is — with receiver-plane depth bias; penumbra
r·(dR−dB)/dB; 12-tap filter on the hardware compare map; no blocker found → one filtered tap (a
sparse search can step over a contact occluder). Specular roughness widened α' = α + r/2d.
Falloff 1/(d² + r²). Shadow camera near 0.5 → 0.1 m (the medals on the arm were never in the map).
Cube and mug shadows harden at contact and soften with height; the desk's pinpoint hot spot is a
broad sheen; the dark laptop stand now shows the diffuser's reflection (verified to be specular,
not a lost shadow: identical to the point light with widening off). Night seated +0.0–0.4 ms.

## Measured and kept

- MSAA 2× costs 0.8 ms (0× 4.5 / 2× 5.3 / 4× 5.8 look). Kept: edge crawl while turning is the
  most visible regression available, and a post AA softens textures.
- Bloom 0.67 ms: the tight levels carry the look (see the washout fix); dropping the wide levels
  saves nothing (they are tiny mips).
- Volumetric 0.3–0.4 ms at 0.4 resolution. Environment sampling 0.3–0.4 ms.
- Per-material scene cost after the above (`bench-materials`): no material over ~0.5 ms; cost is
  spread across the room's ~40 lit materials.

## Considered, not done (with the numbers that decided it)

- **Lightmaps / baked irradiance.** After §1 each remaining light costs 0.1–0.3 ms. Baking would
  save ~1 ms while freezing a continuously moving sun and lamp, and needs a UV2 unwrap for procedural
  geometry. The probe split in §1 already precomputes the expensive part (specular) per lighting
  state.
- **Occlusion/visibility culling.** CPU 0.5–0.8 ms, ~160 draw calls, GPU-bound fill: culling
  saves CPU the frame is not waiting on.
- **Dynamic resolution of the main pass.** Already adaptive (steps down on sustained slow frames);
  now rarely engages.

## Before → after (this pass)

Baseline = `bca8de1` (start of the pass) **with only the composer ratio fix applied**, served from a
git worktree, so the comparison isolates rendering work. `scripts/perf-suite.mjs`, uncapped, true
pr 1.5 (2160×1350), runs interleaved base/now/base/now, averaged over day 13:00, golden 18:30,
evening 20:00, night 21:30. Frame p50 / p95 / max ms, (missed-frame count summed over 8 runs),
draw calls. (As shipped before the fix, buffers were 2.25× larger again.)

| scenario | before | after | p50 |
|---|---|---|---|
| standing idle | 8.1 / 15.7 / 27 (22) · 137 | 5.3 / 10.2 / 17 (0) · 137 | −34% |
| standing look | 8.9 / 24.4 / 35 (139) · 240 | 5.5 / 11.0 / 22 (0) · 155 | −38% |
| sitting | 10.4 / 27.6 / 32 (205) · 281 | 5.7 / 11.3 / 23 (0) · 316 | −45% |
| seated idle | 7.7 / 14.3 / 26 (16) · 93 | 5.1 / 9.5 / 15 (0) · 93 | −34% |
| **seated look** | **10.4 / 27.6 / 45 (205) · 156** | **5.6 / 10.9 / 22 (0) · 155** | **−46%** |
| hover | 8.2 / 15.8 / 30 (36) · 106 | 5.6 / 10.9 / 19 (0) · 106 | −32% |
| focus transition | 11.4 / 24.7 / 33 (60) · 133 | 6.3 / 12.0 / 28 (1) · 130 | −45% |
| popup open | 7.7 / 13.3 / 31 (16) · 77 | 5.4 / 9.7 / 19 (0) · 77 | −30% |
| time transition | 8.1 / 21.9 / 51 (110) · 106 | 5.7 / 11.7 / 33 (6) · 107 | −30% |

By hour (p50): seated idle 7.6→4.5 day, 7.8→5.3 golden, 7.8→5.3 evening, 7.7→5.2 night; seated look
10.4→5.5 / 5.7 / 5.7 / 5.7; standing look 9.0→5.5 / 8.8→5.7 / 9.2→5.6 / 8.8→5.5; popup 7.7→5.4 /
7.8→5.4 / 7.7→5.4 / 7.7→5.3. Night idle keeps ~0.7 ms more than day: the disk lamp's shadow work.
Sitting draws +35 calls: the lamp blocker map redraws with the shadow maps while the chair rolls.

Real 60 Hz (`CAPPED=1`, calibration picks 1.5): 60 fps, **zero missed frames in every scenario**
day and night; main-thread CPU 1.0–1.9 ms avg, ≤3.7 ms p95. Heap 34–43 MB both builds, no growth.
Loader hidden at 1.37–1.6 s; startup trace 60 fps with no frame over 16.8 ms after reveal.

Image, before vs after, frozen grain (`scripts/compare-variants`): mean 0.8–2.3 per view and hour;
the visible changes are the lamp (softer, contact-hardening shadows; wider highlight), and a slightly
weaker window sheen on the lamp base by day (161 → 159 mean luminance in that patch).

Tests: verify-room, verify-gesture, verify-motion, verify-a11y (keyboard focus, focus restore,
reduced motion: no idle motion), verify-shelf, verify-shelf-a11y, verify-books, verify-ao-motion
all pass with no console errors; compile-watch from 06:00, 13:00, 21:00: zero shader compiles after
load across the 24 h sweep, hovers and shelf.

**Largest remaining cost:** the main scene pass — lit PBR shading of ~40 materials at 2160×1350 with
MSAA 2× (~3 ms, of which MSAA 0.8), spread evenly with no dominant material; then bloom (0.7) and
AO while turning (~0.8).
