# Handoff: the room, as it stands

> **Read this box first (2026-10-01).** The Blender remodel is now **the website**: `main` ships the baked sunset room
> at https://vasiniks.github.io/Hub/. Everything below the box was written before that and is history where it
> disagrees; the "Web integration — paused" section at the end is superseded by the box.

## State as of 2026-10-01 (web integration finished)

**What ships.** The site is the baked sunset room (`startV2` in `src/main.ts`). The old procedural room was
**removed** on 2026-10-01 at the owner's request: its entry path, scene modules (room, desk, bookshelf, objects, dust,
assets, build, merge, exterior, ltc), book data and shelf UI, its public assets (`processed/`, `textures/`,
`ltc.bin`) and the verify/perf scripts that drove it. The renderer still contains its light passes (AO, volumetric
shafts, rect-area lights, the lamp disk shadow, bloom), all disabled on this path — stripping them out of
`renderer.ts` is a follow-up refactor, not a behaviour change. In the room:

- **Baked shell, desk, furniture, curtains** from `blender/bake/sunset/` with their RGBM lightmaps
  (`public/assets/v2/room/`, now lossless WebP, bit-identical to the PNGs) and real albedo atlases.
- **Grade:** Blender's own view — AgX + look *Medium High Contrast* at +0.45 EV — as a 33³ LUT evaluated from Blender
  5.2's `config.ocio` (`src/scene/v2Look.ts`, `public/assets/v2/grade/`). Against the Cycles references the error went
  24.6 → 7.3 (stand) and 24.5 → 10.1 (seat) on 8-bit steps; the floor (Cycles' own bake preview) is 6.7 / 9.0.
- **The street** outside as two baked panorama cards, 6 triangles + 268 KB WebP, replacing 390 k triangles
  (`src/scene/exteriorBackdrop.ts`, `public/assets/v2/exterior/`). The window glass refracts at IOR 1.5 to match the
  approved stills (which look through a zero-thickness refracting plane, ~1.5× magnified); `exterior.json`
  `glass.ior = 1` gives a plain window, no re-bake.
- **All 20 prop sets** (`public/assets/v2/props/`, exporter `blender/scripts/v2_export_web.py`), 329 k tris. Non-metal
  surfaces are **pre-lit**: a Cycles diffuse bake (direct + indirect + colour) inside the full sunset room, shipped as
  `KHR_materials_unlit` with radiance / `litScale` (glTF extras, capped at 8) — no live light touches them. Metals,
  emissives and glass stay PBR, lit by an environment capture of the baked room plus the sunset sun and lamp disk
  from room.blend (`src/scene/v2PropLight.ts`); the baked room itself is MeshBasic and cannot be lit twice.
- **Geometry is meshopt-compressed** (`scripts/meshopt-glb.mjs`, after `optimize-glb.mjs`; 16-bit positions/UVs kept).
  Room + props GLBs 12.2 MB → 6.9 MB; a parked frame differs by 0.65/255 mean. A visitor downloads ≈ 11 MB in all.
- **Walk / sit / look / examine:** the old room's rig and interaction modules, reused through a prop registry
  (`src/interaction/props.ts`, table in `src/data/v2Props.ts`). Interactive now: FRC robot, Lorenz sculpture, lab
  bench (STM corner), notes (notepad + paper), bookshelf (baked board + exported books). Panel copy comes from
  `src/data/projects.ts` and is **still placeholder** — the owner's to write.
- **Moving parts:** the robot's status lens pulses 0 → 7 on a 4 s sine; the monitor runs the Lorenz attractor
  (`src/scene/v2Animate.ts`). The A1 mini's screen and PC RGB are static emissives.
- **Loader:** the desk monitor's attractor, which the visitor can drop points into (`src/ui/loadingTrace*.ts`,
  worker + OffscreenCanvas; +3.2 kB gzip, no measurable load cost).
- **Credits:** the four CC BY models are credited in a line at the bottom right, read from
  `public/assets/v2/props/CREDITS.json` (`src/ui/credits.ts`).
- **Low-end GPUs:** before the reveal, `startV2` times real frames and steps down a ladder — 1.5× → 1.25× → 1×, then
  MSAA off, then 0.85×, 0.7× — until a frame fits 15.5 ms (`stepDownQuality` in `renderer.ts`); a slowdown later
  steps down again. Under software rendering (SwiftShader) it went 339 ms → 76 ms per frame; on the RTX 5070 it stays
  at full quality (~1.2 ms). Not yet tried on a real low-end machine or the M2 Pro.

**Agents and reports.** Claude Code does not let subagents write report files, so a workstream's report is its final
message and the coordinator commits it (`.claude/briefs/_common.md` rule 10). The 2026-10-01 reports are
`.claude/briefs/report-{v2-rig,loading,web-exterior,v2-look,web-props}.md`.

**Verified** in Chromium on this Windows machine (RTX 5070, D3D11): `scripts/verify-v2.mjs` against the production
build (`vite build --base=/Hub/` + `vite preview`) — stand, look limits, sit, seated look, hover, focus, panel, Esc,
click-outside, keyboard nav, click-while-standing — 0 failures, 0 console errors, ~180 fps. `npm run build` is clean.

**Owner decisions taken 2026-10-01** (recorded in `assets/MANIFEST.md`): the licensing gate is **lifted** — the
Greg Bennett guitar, Teto pear, Red Bull can, GPU kit and the speedcube "18" logo all ship. The web code was written
by Claude subagents directly, not through OpenCode, for this pass. `blender-remodel`'s `.blend` files were already in
`main` from the earlier `?v2` merge.

**Open**
- **Renderer clean-up:** the old room's passes still live in `src/scene/renderer.ts` (disabled here); removing them
  would save their render-target memory on weak GPUs.
- **Panel copy** is placeholder everywhere (as it was in v1).
- **Known visual compromises:** robot 63 k tris (thin plates shred below that) and its polycarbonate hopper shows
  some faceting up close; ~6% of the lamp head's lit texels clip (white under AgX anyway); the PC's saturated pinks
  lose ~7% to WebP chroma; environment specular on baked trim is built but off (it made the match worse);
  no chair motion when sitting (the camera moves; the chair is a static prop).

**Rebuild the web assets** (each Blender run through a lock, one at a time — the owner's live window shares the
GPU): props `blender -b blender/scene/room.blend --python blender/scripts/v2_export_web.py -- <set|all>` →
`PROPS_SRC=tmp/props_raw PROPS_DST=public/assets/v2/props node scripts/optimize-glb.mjs` →
`node scripts/props-manifest.mjs` → `node scripts/meshopt-glb.mjs`. Exterior: `blender/scripts/v2_exterior_web.py`
then `scripts/encode-exterior.mjs`. Grade LUT and albedo atlases: `scripts/v2look/`.

---

Written 2026-09-30 on branch **`blender-remodel`** (pushed; `main` is untouched and still ships the old web build).
This is the whole state of the project for whoever picks it up next — human or agent. Read it before touching
anything; it exists so the next pass does not redo work or undo decisions the owner already made.

The project now has two halves:

1. **The website** — a first-person WebGL room (three.js r186 + Vite + TypeScript) in `src/`. Unchanged on this branch.
2. **The Blender remodel** — the whole room moved into Blender, rebuilt and re-dressed with the owner over many feedback
   rounds, lit for **sunset**, and baked. It has **not** been wired into the website yet. That is the next job.

The bake-machine contract `HANDOFF-BAKE-MACHINE.md` and the 2026-09-27 five-state bake are superseded by the sunset
bake below.

---

## 1. Website (unchanged on this branch)

```
npm install
npm run dev        # dev server
npm run build      # production bundle -> dist/
npm run preview    # serve the production bundle locally
npm run typecheck  # tsc, must stay clean
```

| area | files |
|---|---|
| Scene assembly | `src/main.ts`, `src/scene/room.ts`, `desk.ts`, `bookshelf.ts`, `objects.ts`, `layout.ts` |
| Render pipeline | `src/scene/renderer.ts`, `ao.ts`, `bloom.ts`, `outline.ts`, `volumetric.ts` |
| Lighting | `src/scene/lighting.ts`, `areaLights.ts`, `lampDisk.ts` |
| Materials / textures | `src/scene/materials.ts`, `textures.ts` |
| Old model pipeline | `blender/scripts/build_*.py` → `assets/processed/*.glb` → `node scripts/optimize-glb.mjs` → `public/assets/processed/` |
| Performance record | `perf/LOG.md` (a depth pre-pass and several AO tricks were measured and rejected — read before optimising) |

---

## 2. The Blender scene

| file | what it is |
|---|---|
| `blender/scene/room.blend` | **The working scene.** Everything, including assets that may not be redistributed. **Git-ignored** (public repo). Keep it backed up locally. |
| `blender/scene/room_public.blend` | Same scene with non-redistributable parts stripped. Regenerate after every change: `blender -b blender/scene/room.blend --python blender/scripts/v2_make_public.py` |
| `blender/scene/parts/<name>.blend` | One file per asset, collection `NEW_<name>` under root empty `NEW_<name>_root`, built by a re-runnable `blender/scripts/v2_<name>.py`. Some are git-ignored (see §5). |
| `blender/scripts/v2_integrate.py` | Brings a part into the open scene: appends `NEW_<name>`, retires (hides) what it replaces into collection `OLD_replaced`. Old objects are never deleted. |
| `blender/scripts/v2_render.py` | Background Cycles still: `blender -b <file> --python blender/scripts/v2_render.py -- out.png <camera> <spp> <pct>` |
| `blender/scene/parts/WORKER_RULES.md` | The brief every worker agent followed (headless builds, quality bar, render settings, never kill Blender by name). |
| `blender/scene/WEB_TODO.md` | **Everything the website must change** to match the Blender scene. Start here for the web pass. |

Units are metres, Z-up. Runtime three.js is Y-up: three `(x, y, z)` = Blender `(x, -z, y)`.
Cameras: `CAM_seat` (0, -0.16, 1.175), `CAM_stand` (1.06, -0.96, 1.63), `CAM_wide`, plus close-up cameras.

**Render settings that matter:** Cycles on **CUDA, GPU only** (measured on the RTX 5070: CUDA 8.5 s vs OptiX 27 s vs
CUDA+CPU 13 s for the same frame). OptiX *denoiser* is fine. The user's Blender preferences are already set to this.

### What is in the room now (all owner-directed)

- **Shell:** 0.55 m wider than the web room; enclosed 2nd-floor Canadian bedroom/study (ceiling 2.72 m, crown
  moulding, baseboards, door, outlets, thermostat, register); single-pane black-framed window; linen curtains.
- **Outside:** a liminal Canadian suburban street (houses, maples, power lines, street light, cars) seen from the
  2nd floor (`NEW_exterior`), lit for dusk with glowing windows and porch lights.
- **Desk (white):** 28" monitor on a hex base; closed 14" MacBook Pro on a riser; AULA F87 Pro V2 keyboard;
  Logitech MX Master 3S (scan, cleaned, Pale Grey); STM lab corner (copper Faraday box, STM stage, Teensy breadboard,
  preamp, Fluke-117-style meter); dev boards + hub; notepad + sticky notes + white rOtring 600; the owner's paper
  (real pages); brass Lorenz attractor; MoYu WeiLong V11 cube (real scramble); Red Bull can; Teto pear; white PC
  (O11-Vision-style, pink/blue RGB, kit GPU tinted light blue, all-white motherboard, Ryujin III-style AIO) with the
  Teto plush on top.
- **Lamp:** from the owner's `lamp.stl` — straight column, twin forward branches on a working pivot
  (`NEW_lamp_pivot`), short neck, Ø215 mm circular head + disk light. **Medals** (static): the owner's FRC 2026
  REBUILT medals, 1 gold on blue + 3 silver on red, hanging from the neck.
- **Room:** white wall book rack; Monet *Water Lilies* (public domain); Bambu A1 mini on a white side table right of
  the desk (spool on a roller stand → right-side box → PTFE tube → toolhead, screen lit); Greg Bennett T-style guitar
  (mint) on a stand; Team 1360 robot (optimised CAD, clear polycarbonate hopper, yellow balls, "1360" bumpers, CAD
  status light pulsing via a driver).

### Lighting: sunset (owner decision)

Key sun `SUN_main` ≈ #ff9552 at 9° elevation, ~40° right (angled down the street so the houses don't block it), AgX
Medium High Contrast at +0.45 EV, thin room volume `fx_room_volume`, lamp on, fixture lights in `NEW_fx`.

**DECISION (owner, 2026-09-30): the site is sunset-only.** Static room surfaces use the full baked sunset lighting;
small/dynamic objects stay live-lit; the time-of-day cycle and lamp toggle are dropped for baked surfaces. Recorded in
`WEB_TODO.md` — don't double-light baked surfaces.

### The sunset bake (`blender/bake/sunset/`, script `blender/scripts/v2_bake_sunset.py`, ~11 min)

- Irradiance only (direct + bounced, no albedo), 512 spp + OIDN, from a fresh copy (`room_bake.blend`, git-ignored).
- Atlases: shell 1024², desk 1024², furniture 512², soft (curtains + rug) 512².
- Web set: RGBM PNGs, 5.2 MB — decode `L = (rgb·a·range)²`, `range` per atlas in `manifest.json`,
  `lightMapIntensity = π`. Masters: half-float EXR, 8.7 MB. Per-atlas GLBs (3.6 MB) carry the lightmap UV as
  `TEXCOORD_1` (round-trip verified 99.97–100 %).
- Versus Cycles: 85–89 % of baked pixels within 0.05 luma; baked ≈5 % darker.
- Known issues: metallic monitor stand left unbaked (bakes black — keep it live-lit); faint curtain streaks; jamb and
  baseboards a little soft at 113 px/m; exported curtains drop their subdivision.

---

## 3. Next job: put it on the website

In order:

1. **Export the parts for the web.** Most materials are procedural Blender node setups and do not survive glTF:
   bake each part's materials to textures (base colour / roughness / normal, ≤2K) and export GLBs through
   `scripts/optimize-glb.mjs`. Budget triangles per asset (the scene is ~1.2 M visible tris plus the street).
2. **Wire in the lightmaps** from `blender/bake/sunset/` (see its `README.md`).
3. **Code changes** (`WEB_TODO.md`): room dimensions in `src/scene/layout.ts`, loading the new GLBs, interactions,
   sunset lighting values, the pulsing robot status light, the static medals.
4. **Licensing gate** (§5) before anything goes live.

The owner's earlier instruction: non-Blender (website) work goes through **OpenCode** with the contributer models only
(`opencode/muse-spark-1.3-contributer-free`, fallback `meta/muse-spark-1.3-contributer`, never anything else).

---

## 4. Process notes (learned the hard way)

- **Never kill Blender by process name.** A worker's `taskkill /IM blender.exe` once closed the owner's live window.
  Only kill PIDs you launched.
- **The MCP connection to the live Blender** runs code on Blender's main thread: an open dialog, popup or modal in
  the window stalls every call (they time out after 30 min). Long renders through MCP freeze the window — render
  headless with `v2_render.py` instead. To recover, compare the autosave with the last save, then restart Blender.
- **Re-importing a part** (`v2_integrate.py`) brings back objects that were hidden in the part file (e.g. the old mug
  inside `NEW_electronics` — re-hide it) and resets the part root's transform to the part file's.
- **The auto-mode safety classifier** has had repeated outages; when it fails, read-only work still runs; switching to
  manual permission mode gets everything else through.
- The GitHub repo is **public**; `room_public.blend` is ~55 MB and draws GH001 large-file warnings (owner said that's
  fine for now; move `.blend` files to Git LFS if it nears 100 MB).

---

## 5. Licensing (full detail in `assets/MANIFEST.md`)

| asset | licence | status |
|---|---|---|
| Teto plush (revsworks), MX Master 3S (Guibazilla), A1 mini (neilvfx), motherboard (Daniel Cardona) | CC BY 4.0 | shippable **with a credits line on the site** |
| Monet *Water Lilies* (AIC) | CC0 / public domain | shippable |
| Team 1360 robot, owner's paper, owner's `lamp.stl` | owner's own, owner-approved | shippable |
| Greg Bennett guitar, Teto pear | Sketchfab Free Standard | **local only** — owner decision needed before web use |
| Red Bull can, GPU kit | source unidentified | **local only** — identify or replace before web use |
| Speedcube "18" logo | traced from a retailer photo | **local only** (stripped from the public copy) |
| STM stage | modelled from scratch; repo had no licence | shippable (reference image not redistributed) |

`v2_make_public.py` strips the local-only items from `room_public.blend`; the matching part files are git-ignored.

---

## 6. Ground rules (the owner's, unchanged)

- **Never overstate what was done.** Don't call a model downloaded if it was modelled, a scan accurate if it wasn't
  checked, or a render baked if it wasn't.
- **Licensing is honest or the asset does not ship.** Every external asset gets a row in `assets/MANIFEST.md`.
- No unauthorized copy of the song goes into this repository.
- No destructive git: no history rewriting, no force-pushing, no branch deletion.
- Do not edit the global `~/.claude/CLAUDE.md`. Do not install extra MCP servers, plugins or skills without a
  demonstrated need.
- Do not attempt to bypass authentication or access controls.
- Commits end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## 7. Branches

`main` ships the old web build. **`blender-remodel`** holds all of the above and is not merged.
`bake/20260927` (old five-state bake) and `ws/lightmaps` (old runtime lightmap half) are superseded — don't merge them.


---

# Web integration — paused 2026-10-01 (history; superseded by the box at the top)

Everything below was started after the Blender remodel landed, and is **paused mid-flight** at the
owner's request. Nothing here is merged except where it says so. Five OpenCode agents were stopped;
no process is running.

## What is live right now

**https://vasiniks.github.io/Hub/** — GitHub Pages, deployed from `main` by
`.github/workflows/pages.yml` on every push. Pages serves the repo under `/Hub/`, so the bundle is
built with `--base=/Hub/`; the runtime already resolves assets through `import.meta.env.BASE_URL`,
so nothing in the code knows about the sub-path. Pages was enabled with Actions as the source.

- The default URL is **the old room, complete and interactive** — verified in a real browser against
  the live site: all models, scroll-to-sit, hover, focus, panels, keyboard nav, no console errors.
- **`/?v2` is the baked sunset room, and it is not presentable.** Static camera, no props, flat
  beige through the window. Do not show it to anyone as "the remodel" — that mistake was made once
  already and it reads as the site being broken.

Cold load of the live site is **5.7 s** to interactive (1.7 s locally). GitHub Pages does not allow
custom cache headers, so the fix is smaller files, not headers.

## Branch map

| branch | state |
|---|---|
| `main` | ships. Pages workflow + the baked room behind `?v2` (merged from `ws/web-shell`). |
| `blender-remodel` | the Blender scene, the bake, all briefs. **Not merged into `main`** — it carries ~150 MB of .blend files and that is a deliberate decision not yet taken. |
| `ws/web-shell` | merged into `main`. Done. |
| `ws/web-props` | WIP commit. 710-line exporter written, **zero props exported.** |
| `ws/web-exterior` | WIP commit. Backdrop bake script, not finished. |
| `ws/loading` | WIP commit. Loading-screen work started. |
| `ws/v2-rig` | WIP commit, furthest along: 214 lines across `rig.ts`, `main.ts`, `bakedRoom.ts`. |
| `ws/v2-look` | no commits; it was still diagnosing. |

Worktrees are `~/Documents/GitHub/hub-wt-{shell,webprops,exterior,loading,v2rig,v2look}`. Each has a
git-excluded `opencode.json` granting edit/bash/webfetch, a `node_modules` symlink, and its agent
transcript at `tmp/agent.log`. Briefs are `.claude/briefs/{web-shell,web-props,web-exterior,loading,
v2-rig,v2-look}.md` on `blender-remodel`.

## What each workstream still owes

1. **`ws/web-props` — the long pole.** `blender/scripts/v2_export_web.py` bakes each collection's
   procedural materials to textures and exports a GLB. It got as far as the A1 mini — purged to a
   48-object working set, split the screen out as its own emissive primitive — then failed on its
   own bug: `NodeLinks.new(): ... does not support a 'None' assignment NodeSocket type`, wiring a
   bake graph against a material that lacks the expected socket. **Nothing has been exported yet.**
   Scope idea worth taking: do the desk first (monitor, keyboard, MacBook, mouse, lamp, PC, lab
   corner) and ship that, rather than all 17 collections before anything lands.
2. **`ws/v2-rig`** — stand, mouse look, scroll to sit in `?v2`, reusing `src/camera/rig.ts`. Was
   running its own preview server when stopped. Closest to something showable.
3. **`ws/v2-look`** — why the bake looks wrong. The black shapes on the desk are the baked contact
   shadows of props that have not been exported; the lightmap is correct. **Do not lift the shadows
   out of the bake to hide them.** The real runtime fault is the grade: Blender rendered with AgX
   look "Medium High Contrast", three.js has AgX with no look.
4. **`ws/web-exterior`** — the street as a baked backdrop instead of 373 k triangles.
5. **`ws/loading`** — something to do during the 5.7 s wait, without delaying the reveal by more
   than 5% or taking a second WebGL context.

## Decisions left open

- **"Delete v1, make `/Hub` the remodel."** The owner asked for this; it has not been done. Doing it
  today would replace a working interactive room with a static empty shell on the public URL. The
  plan agreed-but-not-executed: flip the default once `ws/v2-rig` and the first props land, and
  remove the old path in the same change, so the public site is never the worse of the two.
- Whether `blender-remodel` merges into `main` at all, given the .blend payload.
- The four CC BY assets (Teto plush, MX Master 3S, A1 mini, motherboard) need a **visible credit on
  the site** before they ship. Not built yet.

## This machine

- **Blender must be run with `--factory-startup`.** Without it it aborts in Metal backend detection
  before the script runs (`EXC_BAD_ACCESS` → `SIGABRT`); four crash reports in one hour came from
  this. Also: one Blender at a time (`room_public.blend` is 66 MB / 1.5 M tris), and never kill
  Blender by process name — the owner has a window open. These are in `.claude/briefs/_common.md`.
- The machine was at **22 GB of swap and under 100 MB free RAM** when paused, largely from running
  two Blender exports concurrently. That is what made Blender unstable, not the agents.
- Claude's own sandbox blocks local port binding, loopback connections, `gh`'s keyring and TLS, and
  Blender's GPU detection. Server, browser, `gh` and Blender commands all ran outside it.
- Leftover vite servers from several sessions were killed at the pause; `scripts/verify-*.mjs` now
  take `ROOM_URL` and `CHROME_PATH` from `scripts/verify-env.mjs` (the hardcoded Chrome path was
  dead on this machine).

## Known quality notes on the shipping room

Verified by looking, not just by passing tests: the hover highlight is a thick pure-white silhouette
outline that reads as a cutout sticker on small dark objects; the hover label floats detached from
its object; every panel still says "Placeholder project"; and the focused close-up is very dark at
night. The music widget is a Spotify embed — real, licensed playback, no audio bundled in the repo.
