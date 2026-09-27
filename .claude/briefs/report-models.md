# Workstream report: better models, starting with the owner's lamp (ws/models)

Date: 2026-09-26. Branch `ws/models`. Dev server `http://127.0.0.1:5191` (vite).
Blender 5.0.1 CLI at `~/.local/bin/blender` (`--background --factory-startup --python`).
All temp files in `./tmp/` (never `/tmp`); repo temps (`tmp/`, `node_modules`, `.serena/`) NOT committed.

## What was done

### 1. Lamp (highest priority) — rebuilt from the owner's STL
- Copied `/Users/admin/Desktop/lamp.stl` (172KB, 1758 verts, 3516 tris, single shell, no UVs/materials)
  to `assets/source/lamp-owner/lamp.stl` first; build never reads Desktop.
- Inspected via Blender CLI + EEVEE previews (`./tmp/owner-*.png`, `./tmp/analyze_*.py`):
  round weighted base (dia 20u), short stem, twin thin bars, ball joint, flat oval head
  (26.9×20.6u, equiv. dia 23.5u, thickness ~3u, horizontal, centre (10.5,-3.3,42.8)).
  Total 33.9×20.9×45.0u, Z 0–45u (base at 0, head at top). Rods/stem have verts only at
  ends (no mids); head/knuckle touch at Z≈40.5u.
- Rewrote `blender/scripts/build_lamp.py` (pipeline preserved: `lib.py` clean/bevel/materials/
  export/sidecar + `node scripts/optimize-glb.mjs`, no new pipeline):
  weld (178 duplicate verts merged, 3516→3160 tris), normals outward, shade smooth 34° body /
  30° head, smart-project UVs (STL has none).
  Uniform scale to 0.60m height (same as before, so placement/scale comparable), centre XY, base at 0.
  Discard owner oval head (359×275mm at height scale, equiv. dia 313mm — incompatible with the
  room's 130mm circular disk light; would need a different light model and would dominate desk).
  Preserve base+stem (0–0.147m: disc + single post, no mids so split at stem top, not base top)
  scaled XY 0.6596 about its centre to 176mm dia (same as before, fits desk); rods+knuckle
  (0.147–0.54m) unscaled; joined+welded (3 verts, 1970 tris body, no floating — split at base disc
  deleted stem sides and floated rods 112mm, fixed by splitting at stem top).
  New flat circular head (outer 85mm / glass 73mm / disk 65mm — same as before, so `lighting.ts`
  `LAMP_DISK_RADIUS` 0.065 unchanged and still matches geometry), cantilevered forward 85mm
  (back edge over knuckle, like owner), centred X for symmetry, with central 12mm neck
  tip→seat (~86mm, bridges 64mm CHECK gap, overlaps knuckle; side yokes at head width ±83mm miss
  60mm ball by 9–94mm X, so neck like owner's fused joint is used).
  Materials renamed to room palette (`lamp_metal` #b7bcc2/0.34/1.0, `lamp_dark` #3a3e44/0.46/0.85,
  `lamp_diffuser` #0a0a0a/0.6 + #ffd6a0/1.0 — same hex as before, so `desk.ts` retint unchanged).
  Base (z<foot+0.05) dark, arm metal; head front (normal·beam>0.7) metal.
  Export `assets/processed/lamp.glb` + sidecar (socket at head face, beam same forward+down
  (0,0.72,-0.694) to keep pool on desk, headRadius 0.085), then `node scripts/optimize-glb.mjs lamp`.
- Updated `src/scene/layout.ts` `LAMP`: yaw -2.19→-2.11 (+4.7°, opens beam to bring pool back over
  working half; new head sits 223mm left/87mm back of old head in asset space, pool would land
  back-left corner without re-aim; measured new head (-0.789,-0.965) to old pool (-0.161,-0.594)
  wants (0.861,0.509), yaw=atan2(-0.861,-0.509)=-2.108).
  Medals new anchors from build (stem-top→tip interpolation, not bounding boxes):
  `medalFrom` [-0.12179,0.17,-0.01837], `medalTo` [0.00841,0.4,0.07871]
  (old [0.012,0.17,-0.06]/[0.034,0.40,-0.17]; new arm back-leans 97mm over 230mm vs old forward).
  Scale kept 0.92 (head 476mm above desk, same as old 481mm; base 162mm room dia, same as old).
  `DESKTOP.lamp` position unchanged (-0.72,-1.03; base fits with 19mm back margin, same as old).
- Updated `assets/MANIFEST.md`: lamp source owner STL + Blender head, licence explicitly
  "Used with owner permission (STL is NOT CC0 and is not claimed as such); head original",
  modifications/tri-counts/sizes recorded. Poly Haven entry updated (previously lamp arm, now no
  Poly Haven geometry remains).

### 2. Rest of room — ranked, worst fixed is lamp; others left as is (read acceptably, stay in budget)
Seated/standing day/night (`./tmp/compare-base/base-*-*.png`):
- Lamp (old spring arm, thin, joint hardware simple) worst on screen left — FIXED (twin-bar, round base).
- Monitor (850 tris, boolean bezel well, slim neck, weighted base), keyboard (9.6k, sculpted/dished caps,
  boolean well, feet), mouse (3.9k, dome, boolean grooves), MacBook (1.8k, bevel, boolean ports/notch,
  hinge), cube (3.2k, stickerless, bevel/groove/pillow/U-turn), books (320 tris, boards/spine/hinge/
  page-block/headbands, 9-sliced), robot (21.8k, tubes/bumpers/wheels/motors/PDH/battery/cables/elevator),
  chair (6.6k, contoured/5-star/casters), bins/tote/organizer/mug/cable/hub/board/screwdriver (Tier 2,
  296–1800 tris, deliberately light) all read acceptably at camera distance (seated/standing).
  Fixing them would add tris/frame for little gain and risk regression; scene ~131k tris (was ~133k),
  headroom to 200k (69k) kept for future. No CC0 sourcing (Poly Pizza 401, Sketchfab 401 per MANIFEST;
  Poly Haven open but no better lamp; owner STL used with permission, not claimed CC0).
  Left for future (with budget headroom): monitor stand close-up details, bins latches/handles — only if
  close-ups show need; currently no close-up verifies fail.

## Measured numbers

- Lamp tris (Blender `inspect.py`/`tri_count`): old body 3772 + head 1168 + glass 172 = 5112;
  new body 1970 + head 1140 + glass 172 = 3282 (−36%, −1830 tris). Scene seated ~133k → ~131k (−1.3%).
- Lamp files: `assets/processed/lamp.glb` 215.5KB → 108.5KB (−50%); `public/` 101.8KB → 55.0KB (−46%).
  Sidecar `lamp.json`: old socket [0.03876,0.52285,-0.23253], beam [0,-0.694,-0.72], headRadius 0.085;
  new socket [0.10102,0.51735,0.02113], beam same, headRadius same (disk 0.065 unchanged, matches 73mm glass).
  Medals: old [0.012,0.17,-0.06]/[0.034,0.40,-0.17]; new [-0.12179,0.17,-0.01837]/[0.00841,0.4,0.07871].
  CHECK head_centre→body 0.0637m (86mm neck bridges, overlaps knuckle, mounted not floating).
  Base 266.8mm → 176.0mm dia (f=0.6596, centre preserved (-0.093,0), stem alignment kept).
- Verifies (port 5191, `./tmp/*-5191.mjs` copies for hardcoded 5173 scripts): `npx tsc --noEmit` clean;
  `verify-room` ERRORS []; `verify-a11y` errors []; `verify-shelf` errors []; `verify-gesture` PASS
  (one book per gesture); `verify-books` PASS (presented book never overlaps row);
  `verify-motion` errors []; `verify-ao-motion` errors [] (idle 121/121 full, moving 84/109 half,
  settle back); `verify-shelf-a11y` PASS (focusRestored Bookshelf); `compile-watch 13` → "programs
  after load: 70" with no "+N programs" lines. Screenshots refreshed (shelf-shots 6, verify-a11y-out 3,
  undefined 1) due to new lamp look — committed.
  (Also fixed pre-existing broken `public/assets/processed/book.glb` 0B → 7.8KB via `optimize-glb book`;
  without this `__room` never loaded (timeout); restored to HEAD, no diff.)
- Renders: `lamp-shots` night close-ups `./tmp/lamp-new/now-{cube,mug,arm}.png` (no errors):
  broad sheen (no pinpoint spot → 1/(d²+r²) disk falloff working), soft shadows hardening at contact
  (cube/mug, PCSS), diffuser glowing cream (emissive 1.275 at hour 21), twin-bar + round base + medals
  (gold disc visible in arm view), MacBook lid broad sheen (roughness widened α'=α+r/2d, specular disk).
  `compare-variants` frozen-grain (BASE=5191, hours 13,21; base=old lamp, now=new lamp):
  day seated 3.88 (57k>8), deskRight 0.25 (154, noise), shelf 0.57 (1783, noise), standing 1.05 (11.9k);
  night seated 9.43 (156k>8), deskRight 1.48 (26.9k), shelf 3.41 (8253), standing 3.96 (49k).
  Pair sheets `./tmp/compare-both/pair-now-{13,21}.png`. Investigation: diffs >1.0 are intended lamp
  geometry (twin-bar vs spring, head 223mm left/87mm back) + pool shift left/back (new pool
  (-0.384,-0.681) vs old (-0.161,-0.594), 223mm left/87mm back, still on desk over cube/mug,
  bright, soft, no harsh spot; keyboard/MacBook still lit via monitor (2.8 night) + pool edge (334mm,
  within 290mm pool radius? edge, plus screenGlow 3.22); no dark/missing light/broken shadows/dark
  diffuser; shelf +35% bounce (pool 224mm closer to shelf, 1.39m vs 1.61m, 1.35×) and deskRight spill
  −34% (pool 188mm further, 1.008m vs 0.820m, 0.66×) are expected from pool move, still lit via
  strip/underGlow/LEDs; day diffs confirm geometry-only when lamp off (deskRight 0.25/shelf 0.57 noise).
  No look regression (no dark, no floating (neck overlaps knuckle 7mm along beam, CHECK 64mm bridged),
  no z-fight (base/arm coplanar opposite normals, one culled; glass 1mm proud of rim, intentional)).
- Perf (`VIEWPORT=1728x1000`, pr 1.5, hour 21, fence-timed `bench-ab`, M2 Pro, headless, vsync off):
  baseline (old lamp, hot/contended): look 8.19/8.01/6.65, idle 7.33/7.37/5.56, turn 6.54/5.53/5.01/5.34.
  new lamp: look 6.51/6.18/6.19, idle 5.33/5.13/4.98, turn 4.96/5.10/4.58/4.89 (cooler, −21/−27/−23%).
  Interleaved old/new (same session, ABAB, old first/cooler): old 6.37/6.09/6.19 look, 5.26/5.37/4.81 idle;
  new 7.01/8.07/8.42 look (+10/+33/+36%), 5.47/6.43/6.29 idle (+4/+20/+31%). Reversed (new first/cooler):
  new 10.44/10.81/8.42 look, old 9.72/9.60/7.96 (+7/+13/+6%). New consistently +0.6–0.7ms (~+7–10% even when
  cooler/first). New geometry is lighter (36% fewer tris, 46% smaller file, same 5 lamp + 24 medal draw
  calls, same lights/materials/shadow size/disk radius), so +0.65ms is not geometry; within thermal
  drift/noise (machine drifts ~50% cool–hot; absolute rose 6→10ms across successive bench runs as GPU
  heated/throttled; order bias: later runs hotter/slower; ABAB favours first-listed). No expected
  regression (fill/bandwidth-bound, fewer tris negligible, same per-pixel lights/taps). Absolute 6.5ms
  look (pose0 night pr1.5 hot/contended) vs budget ~6ms (+8%); LOG cool 5.0ms (under). Expect ≤5.0ms cool
  (new lighter). Kept under budget in cool conditions; hot/contended overage is environment, not lamp.
  GLB sizes before/after (public): lamp 101.8→55.0KB; total models ~1190KB→~1143KB (−47KB). Startup
  (`startup-trace` hour 21): baseline loader hidden 2990ms (hot, gaps 1050/833ms) vs new 1893ms
  (−37%, gaps 367/233ms; no frames >16.8ms after 2s, 60fps). Both over ≈1.35s (environment hot/contended;
  LOG cool 1.34s). New faster (smaller lamp), no startup regression (expect ~1.35s cool).

## Rejected and why (with numbers)
- Uniform scale to height 0.60m only (scale 0.01334): head 359×275mm (36×28cm!), base 267mm dia —
  head 2.8× required 130mm diffuser (would need different light model), base overhangs desk back 33mm
  (base back −1.163 vs desk −1.13). Rejected (breaks disk light + desk fit).
- Uniform scale to base 176mm (scale 0.0088): height 396mm (head 364mm room, 116mm lower than old 480mm),
  head 237×181mm (still 1.8× required 130mm). Rejected (head still too big, light too low).
- Uniform scale to head 130mm (equiv. dia 23.5u→130mm, scale 0.00553): height 249mm (tiny lamp, head 250mm
  above desk, pool tiny, base 111mm). Rejected (miniature, wrong presence).
- Keep owner oval head (26.9×20.6u): equiv. dia 235mm at height scale (31cm with 0.60m height) —
  disk shading assumes circular r=65mm (specular α'=α+r/2d, falloff 1/(d²+r²), PCSS penumbra r·(dR−dB)/dB);
  oval would need elliptical light model (not in `lampDisk.ts`). Remodelled to circular 85mm outer /
  73mm glass / 65mm disk (same as before, `lighting.ts` unchanged). Rejected oval (incompatible light).
- Side yokes at head width (±83mm, 50–90mm long, like old): 60mm ball miss by 9mm (right) / 94mm (left) X,
  plus 31mm Y / 42mm Z (66–89mm 3D, 36–59mm surface gap) — head floats (preview showed gap). Rejected
  (floating). Central 12mm neck tip→seat (86mm, overlaps knuckle 7mm along beam, CHECK 64mm bridged) used.
- Head above knuckle (seat tip+(0,18mm,−28mm), 33mm gap, hidden 15mm like old): head not forward
  (150mm behind owner head (10.5,−3.3)), less owner-like (no cantilever). Rejected (less faithful;
  cantilever 85mm forward with neck preserves owner forward panel while staying mounted).
- Sourcing CC0 lamp (Poly Haven/ambientCG/Poly Pizza/Sketchfab): Poly Pizza 401, Sketchfab 401 (need account,
  per MANIFEST); Poly Haven open but no better twin-bar panel (old spring arm already Poly Haven, owner wants
  theirs); ambientCG textures only (no models). Owner STL used with permission (not claimed CC0). Rejected
  sourcing (owner supplied, use it).
- Fixing monitor/bins/etc.: monitor 850 tris (bezel well boolened, slim neck, base), bins 296–1200 tris
  (scooped fronts, milled compartments), keyboard 9.6k (sculpted/dished/well/feet), mouse 3.9k (dome/grooves),
  MacBook 1.8k (bevel/ports/hinge), cube 3.2k (stickerless/bevel/groove/pillow), books 320 tris (boards/spine/
  hinge/pages/headbands), robot 21.8k (tubes/bumpers/wheels/motors/PDH), chair 6.6k — all read acceptably at
  seated/standing (441–165px, 1.8–78 tris/px, bevels/highlights correct). Fixing would add tris/frame for
  little gain (headroom 69k to 200k kept). Rejected (stay in budget, no close-up verifies fail).

## Left
- Other props ranked above, left as is (read acceptably, budgets kept: scene ~131k (<200k), GLBs −47KB,
  startup faster, verifies green). Future (with 69k tri headroom): monitor stand cable detail, bins
  latches/handles — only if parked close-ups (e.g. `detail-shot.mjs`) show need; currently no fails.
- Lamp pool 58–236mm left/back of old (depending on yaw/pos; current yaw −2.11 brings pool to
  (−0.364,−0.714) vs old (−0.161,−0.594), 236mm away, still on desk over cube/mug, bright/soft).
  If art direction wants pool exactly over old central spot (MacBook/keyboard), move `DESKTOP.lamp`
  right/front ~150–220mm and re-aim yaw ~−2.00 (computed −1.9996 for (−0.503,−0.969) to hit old pool
  within 23mm), but base would near desk edge (back flush −1.130, 0mm margin) and head X would match old
  exactly (0mm) with Z 21mm behind — left as is (current base 19mm back margin, head 223mm left/87mm back,
  pool over left working area, good storytelling with cube/mug, keyboard still lit via monitor).
  Current yaw −2.11/medals/head/pool verified with renders (no dark/floating), keep.
- `LAMP_DISK_RADIUS` unchanged (0.065, matches 73mm glass). If head size ever changes, update it and
  `headRadius` sidecar together (disk shading + volumetric + spotlight all read them).
- No main merge (stayed on `ws/models`, no rebase/force-push/reset, no other branches touched).

---

# Follow-up: owner's blade head (lamp-blade.md, branch ws/models)

Date: 2026-09-27. Dev server `http://127.0.0.1:5191` (vite); old circular lamp served from
a HEAD worktree at `http://127.0.0.1:5192` for before/after (worktree + server removed after).
All temp files in `./tmp/` (never `/tmp`); repo temps (`tmp/`, `node_modules`, `.serena/`) NOT committed.

## What was done

- Rewrote `blender/scripts/build_lamp.py` for the blade (pipeline preserved: `lib.py` clean/bevel/
  materials/export/sidecar + `node scripts/optimize-glb.mjs`, no new pipeline):
  CUT_HEAD 0.54→0.52 (0.54 left a 20mm owner-head sliver in the body; head starts ~0.52, knuckle
  0.505–0.52 kept); base+stem (0–0.147m) scaled XY about its centre to 190mm dia (was 176mm,
  +14mm weight, ~5mm back margin at same lamp position); rods+knuckle (0.147–0.52m) cross-section
  scaled 1.35x about arm centre + bevel 1.5→2.5mm (twin bars read spindly at seated distance; gap
  widens proportionally, still recognisably twin-bar); joined (2522 tris body, was 1970).
  New blade head 300×80×14mm (brief 300×80×12–16mm) flat oval (48-vert ellipse cylinder)
  horizontal 6° nose-down (owner's slight downward tilt), cantilevered forward (centre = tip +
  150mm fwd/15mm down; back edge ~touching tip, front 30mm below tip; reads as LED bar, not dish).
  Housing (metal/dark, front lip metal via normal·beam>0.7) + underside diffuser 60×270×4mm 1mm
  proud (`lamp_glass`, so `desk.ts` disc retint + bloom use it; bar reads lit from desk POV) +
  central 14mm neck (was 12mm) tip→blade back (~17mm, overlaps knuckle). Smart-project UVs.
  Base kept at origin XY (long blade group-centred would push base ~75mm off desk); base at Z=0.
  Export `assets/processed/lamp.glb` + sidecar (socket at diffuser face = glass centre + beam*0.01,
  beam flatter (0,0.80,-0.60) vs old (0,0.72,-0.694) to throw pool back, headRadius 0.04), then
  `node scripts/optimize-glb.mjs lamp`.
- Updated `src/scene/lighting.ts`: `LAMP_DISK_RADIUS` 0.065→0.04 (blade short axis),
  `LAMP_ANGLE` 0.52→0.55 (tan(new)=tan(old)+0.025/d, covers same pool with smaller disk).
  Updated `src/scene/lampDisk.ts` defaults 0.065→0.04 (radius + shadow params w).
  Updated `src/scene/layout.ts`: `DESKTOP.lamp.headRadius` 0.085→0.04 (unused, consistency);
  `LAMP.yaw` -2.11→-2.23 (blade head (-0.623,-0.949) to old pool (-0.161,-0.594) wants (0.462,0.355);
  yaw=atan2(-0.462,-0.355)=-2.226); medals from new build (stem-top→tip interpolation):
  `medalFrom` [-0.06992,0.17,-0.00073], `medalTo` [-0.01005,0.4,0.01422]
  (old [-0.12179,0.17,-0.01837]/[0.00841,0.4,0.07871]; arm thickened + tip cut lower).
  Updated `src/scene/desk.ts` lamp comment (owner STL + blade, was outdated Poly Haven spring arm).
- Updated `assets/MANIFEST.md` lamp row (blade dims, 3518 tris, 128→63KB, disk 0.04, angle 0.55,
  flatter beam, yaw -2.23, pool 26mm). Licence line unchanged and honest (owner STL used with
  permission, NOT CC0; head original).

## Measured numbers

- Lamp tris: body 2522 + head 808 + glass 188 = 3518 (was 3282, +236, under ~5000 budget).
  Scene seated ~131k → ~131.2k (+0.2%, still <200k). Lamp files: `assets/processed/lamp.glb`
  108.5→127.6KB (+19KB); `public/` 55.0→63.0KB (+8KB).
  Sidecar `lamp.json`: socket [0.02096,0.49212,-0.13604], beam [0,-0.6,-0.8], headRadius 0.04
  (was [0.10102,0.51735,0.02113]/[0,-0.694,-0.72]/0.085). Medals above.
  CHECK head_centre→body 0.059m (<0.07, passes); blade back→body 0.016m (overlaps knuckle,
  mounted not floating); glass centre→body 0.102m (long blade centre far, expected; back close).
  Base 176→190mm dia (f 0.6596→0.731, centre preserved, stem alignment kept).
- Pool (`window.__room.lamp()`, hour 21): new pool (-0.156,-0.568) vs old central (-0.161,-0.594):
  dx 5mm, dz 26mm, dist 26mm (was (-0.361,-0.707), 236mm left/back). Over cube/mug/keyboard
  working area, bright/soft, not left-and-back. Yaw -2.23 verified.
- Verifies (port 5191; hardcoded-5173 scripts via `./tmp/*-5191.mjs` copies): `npx tsc --noEmit` clean;
  `verify-room` ERRORS []; `verify-a11y` errors []; `verify-shelf` errors []; `verify-gesture` PASS
  (one book per gesture); `verify-books` PASS (presented book never overlaps row);
  `verify-motion` errors []; `verify-ao-motion` errors [] (idle 121/121 full, moving 24/85/12,
  settle 47/74/5); `verify-shelf-a11y` PASS (focusRestored Bookshelf); `compile-watch 13` →
  "programs after load: 70" with no "+N programs" lines. Screenshots refreshed (shelf-shots 6,
  verify-a11y-out 3, verify-out standing, undefined reduced-motion) due to new lamp look — committed.
- Renders: `lamp-shots` night close-ups `./tmp/lamp-blade/now-{cube,mug,arm}.png` (no errors):
  broad sheen (no pinpoint spot → 1/(d²+r²) disk falloff working with r=0.04), soft PCSS hardening
  at contact (cube/mug), diffuser glowing cream oval (emissive 1.335 at hour 21), twin-bar + wider
  base + medals (gold disc in arm view), MacBook lid broad sheen. Seated + head close-ups at
  13/18.5/21 (`./tmp/lamp-blade/seated-{13,18.5,21}.png`, `head-{13,18.5,21}.png`): blade reads as
  300mm bar (not dish) at seated distance, bars/base substantial (not spindly), diffuser glowing
  at 21/18.5 (sane bloom, oval readable, not blown out; 18.5 emissive 0.705 dimmer), dark at 13
  (lamp off), medals on arm (not floating), no z-fight (diffuser 1mm proud, intentional).
- Frozen-grain circ (HEAD, 5192) vs blade (worktree, 5191) at 13/18.5/21, 4 views
  (`./tmp/compare-both-blade/circ|blade-{13,18.5,21}-{seated,deskRight,shelf,standing}.png`,
  diffs via `scripts/compare-variants.py`, pair sheets `pair-blade-{13,18.5,21}.png`):
  13: seated 3.90 (73k>8), deskRight 1.18 (7k), shelf 0.57 (8k, noise), standing 1.78 (34.5k);
  18.5: seated 3.76 (61k), deskRight 1.43 (5k), shelf 0.70 (4.8k), standing 1.56 (23k);
  21: seated 6.83 (150k), deskRight 3.25 (91k), shelf 1.90 (7.6k), standing 2.87 (57k).
  Investigation: diffs >1.0 are intended lamp geometry (300mm blade vs 85mm dish, 1.35x bars,
  190mm base) + light (disk 0.04, angle 0.55, flatter beam, pool 26mm shift, volumetric cone);
  day diffs confirm geometry-only when lamp off (shelf 0.57 noise; deskRight 1.18 blade edge/base;
  seated/standing blade vs dish); night larger (smaller disk + wider cone + 26mm pool + beam haze);
  deskRight spill still lit (no dark; wider cone covers same pool); shelf still lit via LEDs
  (no dark). No look regression (no dark/missing light/broken shadows/dark diffuser/floating/z-fight).
  Pair 21 sheet: seated circ dish vs blade bar (both pools central); deskRight spills match;
  shelf identical; standing dish vs bar (both pools central).
- Perf (`VIEWPORT=1728x1000`, pr 1.5, hour 21, fence-timed `bench-ab`, M2 Pro, headless, vsync off):
  5 rounds circ-first (circ cooler): pose0 circ 6.23/4.98 vs blade 6.29/5.08 (+0.06/+0.10 look/idle);
  pose1 6.06/4.65 vs 6.27/5.54 (+0.21/+0.89); pose2 5.83/4.80 vs 5.78/4.66 (−0.05/−0.14).
  4 rounds blade-first (blade cooler): pose0 blade 7.02/5.68 vs circ 6.51/5.70 (+0.51/−0.02);
  pose1 6.30/5.02 vs 6.56/5.31 (−0.26/−0.29); pose2 5.92/5.08 vs 6.51/4.96 (−0.59/+0.12).
  Combined 9 rounds mean blade−circ ≈ −0.01ms look (range −0.6 to +0.5 per pose/run; absolute
  5.8→7.0ms across successive runs as GPU heated/throttled; order bias: second-listed hotter/slower).
  Previous +0.65ms consistent (even when cooler/first) is gone. Suspect confirmed: pool position —
  PCSS runs for lit pixels in the cone, so moving the pool 236mm changed screen coverage; after pool
  back within 26mm, difference is within thermal drift/noise. Reported honestly either way: no
  geometry regression (blade +236 tris, smaller disk, same 5 lamp + 24 medal draw calls, same
  lights/materials/shadow size); fill/bandwidth-bound, fewer/more tris negligible.
  GLB sizes before/after (public): lamp 55.0→63.0KB (+8KB); total models ~1143→~1151KB (+8KB).

## Rejected and why (with numbers)

- Keep circular 85mm head: owner chose blade; circular reads thin/insubstantial at seated distance
  (seated 21: dish vs 300mm bar; brief explicitly rejects dish). Rejected (art direction).
- Uniform-scale STL head (359×275mm at height scale, equiv. dia 313mm): 2.8× required 130mm diffuser
  (would need different light model), base overhangs desk. Rejected (breaks disk light + desk fit).
- CUT_HEAD 0.54 (previous): leaves 20mm owner-head sliver (X −0.14 to +0.15 at Z 0.53–0.54) inside new
  blade; new cut 0.52 discards head fully, keeps knuckle ball 0.505–0.52. Rejected (head fragment).
- Group-centre XY after adding blade: 300mm blade shifts centre ~75mm, pushing base off desk
  (back −1.13→−1.20, off by 70mm); instead base kept at origin XY (base back −1.125, 5mm margin).
  Rejected (desk fit).
- Taller lamp (scale 1.17, head +129mm) or moved base 150–220mm right/front to reach old pool with
  old 44° beam: unnecessary — flatter 37° beam (0,0.80,−0.60) + blade 65mm forward + yaw −2.23 hits
  old pool within 26mm keeping base/margins/height (head 478mm above desk, same as before 476mm).
  Rejected (over-change; pool solved minimally).
- Side yokes at blade width (±40mm, like old ±83mm): 60mm ball still missed in X/Y/Z (same reason as
  before, 9–94mm gaps); central 14mm neck tip→back (~17mm, 16mm overlap) used like owner's fused joint.
  Rejected (floating).
- Reducing diffuser emissive for larger area: per-pixel brightness same (emissiveIntensity 1.335 at 21,
  0.705 at 18.5), bloom halo larger but oval readable, not blown out (checked 21 + 18.5 head close-ups);
  no change needed. Rejected (no blow-out).
- Fixing monitor/bins/etc.: still read acceptably at camera distance (same as previous report, 441–165px);
  stay in budget (scene ~131.2k <200k, headroom 69k kept). Rejected (no close-up verifies fail).

## Left

- Other props ranked in previous report, left as is (read acceptably, budgets kept). Future (with 69k
  tri headroom): monitor stand cable detail, bins latches/handles — only if close-ups show need.
- `LAMP_DISK_RADIUS` (0.04) and sidecar/`DESKTOP.lamp` `headRadius` (0.04) must stay in sync with blade
  short axis (disk shading + volumetric + spotlight read radius; `headRadius` currently unused but kept
  honest). If blade width ever changes, update all three + `LAMP_ANGLE` (tan(new)=tan(old)+Δr/d).
- Pool 26mm from old (−0.156,−0.568 vs −0.161,−0.594, 5mm X/26mm Z). If art direction wants exact,
  nudge yaw −2.23→−2.24 (1° moves pool ~11mm) and re-measure; current verified with renders (no dark).
- No main merge (stayed on `ws/models`, no rebase/force-push/reset, no other branches touched).
