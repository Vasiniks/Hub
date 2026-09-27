# Workstream report: remodel props (ws/model-props)

Date: 2026-09-27. Branch `ws/model-props`. Dev server `http://127.0.0.1:5197` (vite,
`--host 127.0.0.1 --strictPort`; log in `./tmp/vite-5197.log`).
Blender 5.0.1 CLI at `~/.local/bin/blender` (`--background --factory-startup --python`).
All temp files in `./tmp/` (never `/tmp`); repo temps (`tmp/`, `node_modules`, `.serena/`,
`undefined/`, `__pycache__`) NOT committed.

Note on ports: `127.0.0.1:5173` is occupied by another session's server (a React app,
not this repo), so the hardcoded-5173 verify/bench scripts were run as patched copies
under `./tmp/vscripts/` (same files, `5173→5197`). Repo scripts untouched. `verify-room`
used `ROOM_URL`, `verify-ao-motion`/`compare-variants` used `BASE`, `bench-ab` used the
`origin|` variant prefix.

## What was done (one commit per object group)

Pipeline preserved throughout: `blender/scripts/build_*.py` (+ shared `lib.py`) produce
`assets/processed/*.glb` + sidecar JSON, then `node scripts/optimize-glb.mjs <name>`
writes `public/assets/processed/`. No new pipeline. Every touched object ships `UVMap`
+ reserved `Lightmap` channels (new `lib.uv_unwrap`, `redo_base=False` where a good
parameterisation already exists, e.g. book atlas UVs). All material names the runtime
retints kept exactly; no new palette names.

### 1. Desk items — `df85a77` (mug, screwdriver, cable, hub, board)
- **Mug** 1456→3152 tris (39→136 KB source, 24→55 KB public): throwing rings in the
  lathe profile, strap-section handle (flattened, swelled at top attach) with fillet
  pads at both joints, meniscus edge on the coffee, 48-step lathe. Close-up at 40 cm
  in the lamp pool verified (`./tmp/close-di-13-mug.png`).
- **Screwdriver** 524→1448: hanging hole in pommel, 2 soft-grip rings, hex bolster,
  hex shaft, cross-cut Phillips tip. All parts named (`driver_bolster`, …).
- **Cable** 1760→3016: smoother jacket (curve resolution 2, 12 pts/loop), velcro tie,
  3-step strain-relief boot, metal shroud with a real mouth (`cable_plug`).
- **Hub** 384→704: ports as recesses with seated tongues, light-pipe LED bars
  (same `hub_led_blue/green` part names the runtime animates), rubber feet, top
  finger groove. LEDs sit 0.2 mm proud (no coplanar flicker).
- **Board** 1154→1734: gold annular rings on mounting holes, USB-C shell with mouth
  + tongue, header base strip under the pins, electrolytic cap, 2 jellybeans.
  All parts named (`board_header`, `board_usb`, …).

### 2. Bins / tote / organiser — `eca00e1`
- **Bin** 296→1052: deeper rolled lip, side stacking rails, rear hanger lip, feet.
- **Tote** 1236→2680: corner posts, internal stacking ledge, removable divider with
  finger notch, feet. Divider top (138 mm stacked) clears the parts-crate contents.
- **Organiser** 1146→1618: front pull scoop (cut before shade/UV), clasp, 3 rear
  hinge knuckles, feet. (Plus a local `cyl()` helper; `cut()` after pocket booleans.)

### 3. Book — `b2bc4cb`
320→804 tris (16→33 KB source, 8→14 KB public): page block rebuilt as 10 stacked
leaves with alternating ±0.12 mm insets + seeded jitter (real fore-edge page
variation), fore-edge corner chamfers on the case. Atlas regions, T/H/D, slice
margins and sidecar values byte-identical — `bookshelf.ts` untouched,
`verify-books` + `verify-shelf` green, shelf close-up checked.

### 4. Speedcube — `012b85f`
3240→5320 tris (93→224 KB source, 59→91 KB public): seam gap 1.4→1.8 mm, bevel
1.7→1.9 mm at 3 segments, deeper moulding groove, shallow centre-cap ring cut
into each face before pillowing. Same 56 mm size, materials, scramble seed,
sidecar. In-room close-up: stickerless colour-over-bevel, dark seams, U-turn.

### 5. FRC robot — `fc3c680`
21788→21828 tris (**+40, flat**): elevator chain strands + sprockets per side, tower
RSL (base + amber dome, still the single `robot_rsl` material the tick blinks),
5 hex hub bolts per wheel, lightening/gusset/bore holes 10→8 sides to fund it all.
Same layout/dims, `robot_body/carriage/rsl` objects, `numberMaterial` sidecar kept;
`frc-robot` examine green (carriage `userData.dynamic` + RSL blink intact).

### 6. Medals — `66e7189` (code, `src/scene/desk.ts`)
Woven ribbon canvas texture (selvedge edges, centre stripe, weave ribbing) on
straps + top bar; thin rim torus per disc. Drops/leans/turns unchanged; tsc clean,
no console errors, close-ups checked at hour 13.

### 7. Editable source — `blender/source/props.blend` (+ `assemble_props_blend.py`)
All 11 prop GLBs joined into named objects on a turntable grid (applied
transforms), `PropsCam`, 3-point lights (Sun + Key + Fill) + neutral world,
EEVEE 1600×900, output `//render/preview_`, studio ground plane. Proved with
`blender -b blender/source/props.blend -o ./tmp/props-render- -f 1 -F PNG`
(`./tmp/props-render-0001.png`; board isolated in `./tmp/board-check-0001.png`).

## Measured numbers

| object | tris before → after | source GLB | public GLB |
|---|---|---|---|
| mug | 1456 → 3152 | 39 → 136 KB | 24 → 55 KB |
| screwdriver | 524 → 1448 | 17 → 61 KB | 11 → 28 KB |
| cable | 1760 → 3016 | 67 → 144 KB | 32 → 57 KB |
| hub | 384 → 704 | 25 → 56 KB | 13 → 20 KB |
| board | 1154 → 1734 | 78 → 138 KB | 36 → 52 KB |
| bin | 296 → 1052 | 16 → 87 KB | 9 → 32 KB |
| tote | 1236 → 2680 | 78 → 219 KB | 35 → 79 KB |
| organiser | 1146 → 1618 | 34 → 83 KB | 18 → 34 KB |
| book | 320 → 804 | 16 → 33 KB | 8 → 14 KB |
| cube | 3240 → 5320 | 93 → 224 KB | 59 → 91 KB |
| robot | 21788 → 21828 | 970 → 1156 KB | 449 → 442 KB |
| **props total** | **32304 → 43356** (+11k) | — | **1151 → 1366 KB** (+215 KB) |

Room was ~154k tris seated; props now ~43k — far inside the ~300k allowance.

- **Look**: frozen-grain diffs vs session baseline, all four views, hours 13+21 —
  mean 0.25–0.81 everywhere (convention: <1.0 is noise). No look regression.
- **Perf** (`VIEWPORT=1728x1000`, interleaved A/B vs HEAD worktree on :5198, both
  orders, 3 rounds, hour 13 pr 1.5): look +0.1 ms, idle +0.1 ms averaged
  (pose-0 first run showed +0.86 idle, reversed run +0.13 — drift, not signal).
  Seated idle ≈ 5.0–5.4 ms, look (AO forced) ≈ 6.0–6.2 ms — same as baseline.
- **Startup**: loader hidden 2198–2451 ms (2 samples) vs HEAD 2269 ms — within
  noise, no >15% regression. (One 3554 ms cold sample; machine drifts.)
- **Verifies**: `tsc` clean; verify-room/shelf/a11y/gesture/books/motion/ao-motion
  all green, no console errors; compile-watch 13 → 76 programs, no `+N` lines.

## Rejected / left
- Tote lid: open crate reads correctly in both floor and crate uses; a lid would
  add a part nobody sees open. Left out.
- Cube logo on white centre: unreadable at desk distance; cap ring only. Left out.
- Robot polycarbonate intake shields: no transparent palette material; opaque
  shields would read as armour. Left out.
- Poly Haven HDRI in props.blend: 3-point + world is enough for a source file and
  keeps the build offline-safe. Left out.
- Book leaves beyond 10 /enserifed page texture: 804 tris × 12 books is the right
  weight; texture lines already carry the rest. Left as is.

## Left for later
- Lightmap bake pipeline (channels reserved on every prop, bake itself not done).
- `assets/MANIFEST.md`: no third-party geometry used (all modelled from scratch
  in the build scripts); no new entry needed.
- `./tmp/wt-base` HEAD worktree + `:5198` server still running for any follow-up
  A/B; remove with `git worktree remove ./tmp/wt-base` when done.
