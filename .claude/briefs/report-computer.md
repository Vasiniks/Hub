# Remodel: computer gear (branch ws/model-computer) — report

## What was done

Complete remodel of the desk computer group, all modelled from scratch in
Blender (no third-party geometry — same as before, so `assets/MANIFEST.md`
needs no new entries). Per-object build scripts updated in place; pipeline
unchanged (`assets/processed/*.glb` + JSON sidecar → `optimize-glb.mjs` →
`public/assets/processed/`). Every mesh now carries `UVMap` (Smart Project) +
a reserved empty `Lightmap` channel per the remodel convention (new
`lib.uv_unwrap` / `lib.unwrap_all` helpers in `blender/scripts/lib.py`).

Deliverable: `blender/source/computer.blend` (37 objects in 6 collections,
studio world + 3-point area lights + tracked camera, render path
`//../render/`), assembled by
`blender/scripts/assemble_computer_blend.py` (re-runnable). Proof render:
`blender/render/assemble_0001.png` (all six objects in frame, EEVEE).

1. **Monitor** (`build_monitor.py`): screen plane, `monitor_screen` quad,
   `monitor_led` position and sidecar (`0.596 × 0.341`) byte-identical —
   attractor + area light hookups untouched. Added: inner bezel chamfer frame,
   power button, rear vent slots, VESA-100 plaque + bosses + screws, rear I/O
   recess (HDMI/DP/USB-C + tongues), display cable to the desk, tapered
   two-piece neck, tilt barrel with end caps, hinge cover, cable clip, weighted
   base with rubber feet. 850 → 4166 tris, source 41 → 267 KB, public 21 → 101 KB.
2. **Keyboard** (`build_keyboard.py`): layout, footprint, tilt, `keyboard_led`,
   sidecar identical. Added: USB-C cable + boot + plug out the back port,
   two-piece groove line around the case, F/J homing nubs. 9574 → 10354 tris,
   289 → 489 KB source, 168 → 194 KB public.
3. **MacBook** (`build_macbook.py`): footprint, tilt, materials, object names
   unchanged. Added: lid inset panel (hero specular edge), bottom gasket,
   rubber feet, bottom screws, port tongues (3 left + right HDMI recess),
   hinge end caps. 1752 → 2376 tris, 75 → 131 KB source, 37 → 51 KB public.
4. **Mouse** (`build_mouse.py`): footprint, profiles, wheel position, object
   and material names unchanged. Added: wheel grip ribs, smaller DPI button,
   PTFE skates, sensor window + lens, nose USB-C port + tongue; grid 34×24 →
   40×28. 3894 → 6297 tris, 99 → 254 KB source, 53 → 105 KB public.
5. **Hub / dev board** (`build_desk_items.py` + 1-line `desk.ts` retint for the
   new `board_silk` → `m.paper` mapping): hub gains side USB-C, rear power
   barrel, top vents, rubber feet (384 → 700 tris); board gains silkscreen,
   0402 row, reset button, electrolytics, mounting-hole copper rings
   (1154 → 2250 tris). Mug / screwdriver / cable geometry untouched (UVs only).
6. **PC tower**: deliberately not modelled — no tower exists in the runtime
   (no layout slot, no builder, no interaction target); adding furniture would
   change the §32 composition. Hub + boards cover the "working electronics".

Group total: ~21.3k → ~28.9k tris (+7.5k). Room seated: ~130–136k → ~152–155k
triangles (bench `triangles` counter), under the ~300k budget.

## Measured numbers (VIEWPORT=1728x1000, pr 1.5, interleaved A/B both orders, 5196)

| condition | base look | new look | delta | idle base/new |
|---|---|---|---|---|
| hour 13, 3 poses | 5.87 / 5.74 / 5.75 | 5.92 / 5.90 / 5.88 | +0.05…+0.16 ms | ≈ same |
| hour 21, 2 poses | 6.52 / 6.45 / 5.99 | 6.42 / 6.43 / 5.95 | −0.10…0.00 ms | ≈ same |

Day stays under the 6 ms budget on both builds. Night exceeds 6 ms on
**both** builds (pre-existing night-lighting cost, not a remodel regression;
new is equal or marginally faster). All suites green, no console errors:
`tsc`, `verify-room` (frc/dev-board/notebooks hover+focus), `verify-a11y`,
`verify-shelf`, `verify-shelf-a11y`, `verify-gesture`, `verify-books`,
`verify-motion`, `verify-ao-motion`, `compile-watch` (76 programs after load,
no +N lines). Scripts hardcoding :5173 were run as port-swapped copies in
`./tmp/v5196/` (repo scripts untouched; :5173 belongs to a sibling worktree).

Frozen-grain (`lorenz=0`, reduced motion) new-vs-base mean-abs-diff:
seated 1.97/1.55 (13/21), deskRight 0.47/0.24, standing 0.62/0.71. Seated is
above the 1.0 noise bar — investigated via heatmap: the delta is the remodel
itself (thicker monitor neck + new display cable, keyboard cable/plug, lid
inset shading, hub vents/ports) plus the animated music widget. Nothing looks
worse; close-ups (attractor fills panel correctly, keyboard sculpt + nubs,
hub LEDs + silkscreen) all read better than baseline.

## Rejected and why

- **Key legends as geometry**: cap tops are ~19 mm, legend strokes ~0.5 mm —
  sub-pixel at seated distance; kept F/J homing nubs only (visible in close-up).
- **Mouse decimate 0.60**: tried (+1.5k tris), rear-pole faceting identical
  under preview light; kept 0.45. Pole fan is a non-issue at desk distance.
- **MacBook rubber slot**: feet undersides face the stand (never seen); sides
  already read dark via the side-band predicate. Dropped the third slot on the
  body to keep the original two-slot contract (stand keeps `mb_rubber`).
- **Touching `lib.recentre`**: debug showed ±1.5 mm lateral quirks from stale
  `matrix_world` in old and new builds alike; "fixing" it would shift every
  tuned sidecar in the repo (lamp socket/beam). Left alone, documented here.
- **Board preview all-white**: preview key-light blowout on a 70 mm board
  (known preview gotcha); materials verified in-GLB and in-room (green mask,
  gold traces, white silk all correct).

## Left / notes

- Dev server left running on :5196 (this worktree's port); all temp files
  (previews, bench harness, port-swapped verifies) under `./tmp/`.
- Night frame >6 ms predates this workstream (perf workstream territory).
- Screen assembly sits ~2.2 mm higher than before (monitor rubber feet);
  plane size/hookups identical, attachments follow automatically.
