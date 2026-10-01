# Report: loading (branch `ws/loading`, commit 8c653f9)

The subagent returned this report as its final message (subagents cannot write report files); the
coordinator committed it. Screenshots: `.claude/briefs/loading-shots/01–07`.

## Idea

The loader shows the desk monitor's Lorenz attractor: the same σ/ρ/β, RK4 at h = 0.0032 and about 340 steps a
second, the same blue trace on dark glass.

- **Drop points:** a click drops a point where the visitor pointed; Enter or Space on the focused figure drops one
  from above. Each point is pulled onto the same two wings.
- **Turn:** ←/→ or the pointer turn the figure.
- **Caption:** after the first drop, it changes from the instruction to what the visitor just saw.

It belongs to the room, one drop takes about the length of the wait, and it reports no progress, so the bar stays
honest.

## Files

- `src/ui/lorenzToy.ts` (simulation and drawing, no DOM).
- `src/ui/loadingTrace.worker.ts` (OffscreenCanvas, CPU raster, 24 Hz).
- `src/ui/lorenzToySize.ts`.
- `src/ui/loadingTrace.ts`: button, input, worker, and a page-thread fallback loaded only when OffscreenCanvas is
  missing.
- `src/ui/loading.ts`: stops the trace on hide/fail; optional first label.
- `index.html`, `src/styles.css`.

## Measured

Windows, RTX 5070, headless Chromium on D3D11; interleaved A/B against `9366d4e`.

**Loader hidden:**

| path | pairs | before (median) | after (median) | change |
|---|---|---|---|---|
| old room | 8 | 9091 ms | 9209 ms | +1.3% |
| v2 | 16 | 1194.5 ms | 1202 ms | +0.6% |

Run-to-run noise is ±1–3%, so read this as no measurable regression, not as free.

**Production v2**, throttled to 20 Mbit/s and 40 ms: 4018 → 3960 ms (noise). The figure is live at 267–475 ms against
first paint at 180–330 ms.

**Longest frozen stretch while loading:** 4971 ms baseline, 4492 ms for the main-thread figure, 401–685 ms for the
worker.

**Rejected:**
- Main-thread figure: freezes during shader-compile stalls.
- GPU-raster worker: +2.1% / +2.5% load time.

**Bundle:** +7.6 kB raw, +3.2 kB gzip. No new dependency, remote asset or font.

## Checks

- tsc clean.
- verify-room, -a11y, -motion, -shelf, -gesture and -books pass (old-room scripts, since removed).
- Tab reaches the figure first.
- Focus returns to `<body>` after the reveal, and the worker is terminated.

## Left

`.music { display: flex }` overrides `[hidden]`, so the music toggle can be reached with Tab while loading. This was
there before and was not touched.
