# Handoff: the room, as it stands

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
