# Reference sites & reusable technique

Branch `ws/research`, September 2026. Room context: first-person cinematic 3D portfolio room,
three.js r186 + Vite + TypeScript, Blender → GLB pipeline (`blender/scripts/*.py` →
`assets/processed/*.glb` → `scripts/optimize-glb.mjs` → `public/assets/processed/`),
KHR_mesh_quantization, GTAO cache + snapshot reprojection, rect-area diffuse volumes,
single composite pass. See `perf/LOG.md`, `assets/MANIFEST.md`, `.claude/progress/asset-overhaul.md`.
Documentation only — no `src/` / `assets/` / `public/` changes in this workstream.

Licence rule used throughout: MIT / Apache-2.0 / Zlib = reusable with attribution;
no LICENCE file = all rights reserved, learn-only, do not copy. Every claim below links
to a URL fetched during this workstream.

## Top 5 to adopt next (cheapest first)

1. **glTF-Transform `weld` + `reorder` + `textureCompress` → WebP** — build-time only, zero
   runtime risk. Appends to existing `scripts/optimize-glb.mjs` (`dedup`, `quantize`, `prune`
   already in). See §15.
2. **Invisible raycast hitboxes for pickables** — Sooah pattern on top of existing
   `three-mesh-bvh`: one `Box3`-sized invisible box per hoverable, `Map<hitbox, real>`,
   delayed creation after intro tweens. Cures hover-twitch, keeps baked meshes out of BVH. See §4.
3. **Dual-gate loader + audio discipline** — `Enter!` / `Enter without Sound` gate (Sooah),
   diegetic `%` label (Jesse "Cooking Your Ramen…"), Howler bgm + SFX ducking, `M` mute +
   `visibilitychange` mute, ship `.mp3` alongside `.ogg` (iPhone glitch note). See §4–§6.
4. **Palette-texture + matcap + blob shadows for dynamic props** — folio-2019 MIT kit:
   `MeshBasicMaterial`/matcap shades, projected blob-shadow planes instead of shadowmaps,
   `base + collision + floorShadow` split. Zero extra lights for avatar/pickables. See §2.
5. **Baked day/night/neutral + RGB lightmask as the target shell design** — Bruno/Sooa shader
   (`mix(day,night) + lighten-masked practicals`, `flipY=false`, sRGB, 2–4 WebP/KTX2 sets),
   dynamics split out of the baked GLB, UV-precision guard for quantization. The room's sun/lamp
   stay dynamic via existing probe-split + 96³ volumes; bake is the direction when they go static.
   Gate with folio-2025 quality ladder (shadow size + bloom mips + DOF on/off). See §1, §3–§4.

---

## Licence ledger (all verified by fetch in this workstream)

| Project | Licence file (fetched) | Verdict |
|---|---|---|
| Bruno `my-room-in-3d` | none — repo listing shows `bundler/ src/ static/ package.json readme.md` only, `package.json: "UNLICENSED"` | **Learn-only** — https://github.com/brunosimon/my-room-in-3d |
| Bruno `folio-2019` | https://raw.githubusercontent.com/brunosimon/folio-2019/master/license.md (MIT ©2019) | **MIT — reusable + attribution** |
| Bruno `folio-2025` | https://raw.githubusercontent.com/brunosimon/folio-2025/main/license.md (MIT ©2025) | **MIT — reusable + attribution** |
| Andrew Woan `sooahs-room-folio` | https://raw.githubusercontent.com/andrewwoan/sooahs-room-folio/main/LICENSE.md (MIT ©2025) | **MIT — reusable + attribution** |
| Andrew Woan `abigail-bloom-portolio-bokoko33` | `LICENSE.md` on `master` (MIT ©2023, repo page confirms "MIT license") | **MIT — reusable; original bokoko33 concept learn-only** |
| Wawa Sensei `r3f-baking` / `r3f-baking-advanced` | `https://github.com/wass08/r3f-baking/blob/main/LICENSE` (MIT ©2025) | **MIT — reusable + attribution** |
| Henry Heffernan `portfolio-website` | https://raw.githubusercontent.com/henryjeff/portfolio-website/master/LICENSE.md (MIT ©2024) | **MIT — reusable + attribution** (companion `portfolio-inner-site`: no licence → learn-only) |
| Jesse Zhou ramen shop | no public repo (`github.com/Jesse-zhou`: 0 public repos) | **Learn-only** — https://jesse-zhou.com |
| three.js | https://raw.githubusercontent.com/mrdoob/three.js/dev/LICENSE (MIT ©2010–2026) | **MIT — reusable** |
| Basement `shader-lab` | `LICENSE.md` (Apache-2.0, repo page confirms) | **Apache-2.0 — reusable + attribution** — https://github.com/basementstudio/shader-lab |
| Basement `scrollytelling` | `LICENSE` (MIT + GSAP notice) | **MIT — reusable** — https://github.com/basementstudio/scrollytelling |
| Basement `website-2k25`, `ship-25-explorations` | no LICENCE, `"private": true` | **Learn-only** |
| Lusion studio + Of The Oak | closed-source, no public repo | **Learn-only** — https://lusion.co/projects/of_the_oak |
| Locomotive Scroll | `LICENSE` (MIT, repo page confirms) | **MIT — reusable** — https://github.com/locomotivemtl/locomotive-scroll |
| `pmndrs/postprocessing` | https://raw.githubusercontent.com/pmndrs/postprocessing/main/LICENSE.md (Zlib ©2015) | **Zlib — reusable** |
| glTF-Transform | MIT ©2024 Don McCurdy | **MIT — reusable** — https://github.com/donmccurdy/glTF-Transform |
| `three-mesh-bvh` (already in) | MIT | **MIT — already adopted** — https://www.npmjs.com/package/three-mesh-bvh |
| KTX2 stack: `ktx-parse` (MIT ©2020 Don McCurdy), `basis_universal` + `KTX-Software` (Apache-2.0) | raw LICENCE files | **Reusable, but SKIP runtime (see §14)** |
| Draco (`google/draco` Apache-2.0), `meshoptimizer` (MIT), `maath`/`math` (MIT), `drei-vanilla` (MIT ©2023 Poimandres), `idb-keyval` (Apache-2.0) | npm + raw LICENCE | **Reusable; verdicts in §15–§16** |

## 1. Bruno Simon — my-room-in-3d (genre originator, learn-only)

- Live: https://my-room-in-3d.vercel.app
- Repo: https://github.com/brunosimon/my-room-in-3d (4.5k★, 626 forks)
- Lesson: https://threejs-journey.com/lessons/baking-and-exporting-the-scene
- Licence: **none — all rights reserved, learn-only** (no LICENCE file in listing; `package.json: "UNLICENSED"`).

What makes it look good: zero realtime lights for the shell. Single `ShaderMaterial`
(`src/Experience/Baked.js`) over `roomModel.glb`, three pre-baked JPGs
(`bakedDay.jpg` 1.4 MB, `bakedNeutral.jpg` 1.5 MB, `bakedNight.jpg` 1.2 MB) + `lightMap.jpg`
846 KB + `roomModel.glb` 270 KB. Fragment fuses `mix(mix(day,night,uNightMix),neutral,uNeutralMix)`
then `glsl-blend/lighten` adds three tinted practicals masked by lightmap channels —
TV red `#ff115e ×1.47` (R), desk orange `#ff6700 ×1.9` (G), PC blue `#0082ff ×1.4` (B).
All baked textures `flipY=false`, sRGB. Journey lesson: delete hidden faces, fix normals,
`Apply Scale`, `Make Single User` before unwrap, second UV channel, Cycles bake → JPG.
No shadowmaps (commented out in `Renderer.js`), no post (`usePostprocess=false`,
`EffectComposer + RenderPass` scaffold only). Dynamics split out of baked GLB
(`pcScreenModel, macScreenModel, coffeeSteamModel, elgatoLightModel`); screens as
`VideoTexture → MeshBasicMaterial`; LEDs `MeshBasicMaterial + alphaMap` pulsed;
coffee steam `ShaderMaterial` (`uTime`, `uUvFrequency 4×5`). Camera narrow long-lens
`PerspectiveCamera(20, 0.1–150)` + custom spherical nav (radius 10–50, target clamp-box,
`0.005 × delta` smoothing, drag-orbit / right-drag-pan / wheel-dolly). No audio; group
loader → build. `pixelRatio ≤2`, three 0.130.1.

What to steal (technique only): 3-bake + RGB-mask shader logic; `flipY=false` + sRGB baked
contract; split dynamic/emissive meshes out of baked GLB.

How it applies: keep room unlit (`MeshBasicMaterial({map: baked})` or ported `ShaderMaterial`
with `map_day/map_night/lightMap`; r186: `tex.colorSpace = SRGBColorSpace; tex.flipY=false`).
Quantize positions/normals but **keep UVs high-precision** (baked seams bleed otherwise).
GTAO off for baked shell (already has Cycles AO); BVH raycast against invisible hitboxes,
not baked mesh. Ship Blender Cycles 2048 → `gltf-transform etc1s --quality 255` + KTX2, JPG fallback.

## 2. Bruno Simon — folio-2019 (driving folio, MIT reusable)

- Live (old): https://2019.bruno-simon.com — Live (current): https://bruno-simon.com
- Repo: https://github.com/brunosimon/folio-2019
- Licence: **MIT ©2019** — https://github.com/brunosimon/folio-2019/blob/master/license.md

No baked GI, no three lights for world. `World/Materials.js`: `MeshBasicMaterial` pures +
custom matcap system (13 matcaps) + `FloorShadowMaterial` with fake-indirect uniforms
(`uIndirect*`, `uIndirectColor #d04500`). Shadows are projected blob planes
(`World/Shadows.js`: sun vector, per-frame position/rotation/alpha falloff, `maxDistance 3`).
Ship split `base.glb + collision.glb + floorShadow.png + matcap png + floorTexture.webp/png`.
Post is custom `Blur.js, Glows.js`, not Unreal. Camera `PerspectiveCamera(40, 1–80)` Z-up,
GSAP angle presets + zoom 14+15, raycast-plane pan. Sound Howler velocity-rate voices +
looping engine, `M` mute, auto-mute on `visibilitychange`. Custom `Loader` with progress.
three 0.164.1, Vite, cannon 0.6.2.

What to steal (MIT): matcap shade system for stylized props; blob-shadow projector;
`base+collision+floorShadow` split; Howler voice manager.

How it applies: use for non-baked dynamic props (avatar, pickables) — matcap/basic + blob
plane, zero light-count growth alongside baked shell.

## 3. Bruno Simon — folio-2025 (current, MIT reusable)

- Live: https://bruno-simon.com
- Repo: https://github.com/brunosimon/folio-2025
- Licence: **MIT ©2025** — https://github.com/brunosimon/folio-2025/blob/main/license.md
  (music CC0 in `static/sounds/musics`).

Stack (from `package.json`): `three ^0.183.2`, TSL (WebGL+WebGPU), `@dimforge/rapier3d 0.17.3`,
`howler`, `camera-controls ^3.1.2`, Vite 7. Game-loop doc (13 ordered systems). Lighting:
single `DirectionalLight(0xffffff, 5)` spherical orbit + custom TSL bounce/shadow uniforms
(`sources/Game/Ligthing.js`, `Materials.js` — palette-texture lookup, luminance-normalized
emissives, `fog=false`). Post (`Rendering.js`): `WebGPURenderer` + `RenderPipeline/pass`
→ `bloom(output)` (`threshold 1, strength 0.25, mips 5 high / 2 low`) + custom `cheapDOF`;
quality 0 = DOF+bloom, 1 = scene+bloom. Camera `camera-controls` + focus-point tracker +
cinematic module + speed-lines. Sound Howler grouped registry (pool 2, anti-spam, lazy load).
Loader `GLTFLoader + DRACOLoader + KTX2Loader` fan-out + cache. Pipeline: mute palette node,
per-preset export, **no Blender compression — `npm run compress` later** via
`gltf-transform` (`etc1s --quality 255`) + `toktx`, UI → WebP. Quality toggle Low/High,
WebGPU/WebGL switch.

What to steal: `export-uncompressed → CI compress to ETC1S/WebP`; palette-texture materials;
quality ladder (shadow 2048/512 + bloom mips + DOF on/off behind one event); ordered loop.

How it applies: adopt compress script as Blender→GLB→quantize→KTX step. r186 carries
`three/webgpu` + `three/tsl` `RenderPipeline/pass/bloom` names forward.

## 4. Andrew Woan — sooahs-room-folio (closest reusable room, MIT)

- Live: http://sooahs-room-folio.com/
- Repo: https://github.com/andrewwoan/sooahs-room-folio
- Tutorial inspo: https://my-room-in-3d.vercel.app/ — Awards: Awwwards + CSSDA (per README)
- Licence: **MIT ©2025** — https://github.com/andrewwoan/sooahs-room-folio/blob/main/LICENSE.md

Baked-only + tiny accents, three 0.172.0, no shadowmaps, no post. Blender trio:
`Before Baking.blend / For Export.blend / For Night Time Baking.blend`. Ship **4 texture
sets × day/night** (`public/textures/room/{day,night}/*_texture_set_{day,night}.webp`,
320–994 KB each) + `Room_Portfolio.glb` (Draco) + skybox webp + `Screen.mp4`. Load
`flipY=false`, sRGB, LinearFilter, Draco `/draco/`. Shader (`shaders/theme/`):
`uDayTexture1-4 + uNightTexture1-4 + uMixRatio + uTextureSet`, `mix(day,night,ratio)`,
GSAP `1.5 s power2.inOut` theme crossfade. 4 sets = Blender 4K bake limit / UV density.
Name-driven `traverse`: `*Water* → basic transparent`, `*Glass* → physical
(transmission 1, ior 3, thickness 0.01, skybox env)`, `*Screen* → VideoTexture basic`,
else First–Fourth ShaderMaterials; smoke perlin planes. Camera `PerspectiveCamera(35,
0.1–200)`, custom OrbitControls clamped to one octant (polar/azimuth 0–π/2, distance 5–45,
damping 0.05). Sound Howler bgm + 24 piano Howls + click, piano ducking, mute toggle.
Loading `LoadingManager → Enter! / Enter without Sound` dual gate → GSAP ~10-timeline reveal.
Picking: invisible box hitboxes (`1.1×1.75×1.1`), `hitboxToObjectMap`, delayed hitboxes
post-intro, hover scale + cursor. README warns `.ogg` glitches iPhone → ship `.mp3`.
Author caveat: one 2114-line `main.js` — "recommend a better structure".

What to steal (MIT): 4-set day/night WebP layout + `uTextureSet` shader; Blender trio;
Draco + skybox-env-only glass; hitbox map; dual-gate loader; mp3-fallback rule.

How it applies: closest structural match to Vite+TS room. Port bake layout + gate, keep
modular files, BVH for hitboxes instead of linear scan, GTAO only on dynamic layer.

## 5. Andrew Woan — abigail-bloom-portolio-bokoko33 (realtime contrast, MIT recreation)

- Demo: https://abigail-bloom-portolio-bokoko33.vercel.app/
- Repo: https://github.com/andrewwoan/abigail-bloom-portolio-bokoko33 (repo page: "MIT license")
- Original: https://room.bokoko33.me (©2022 bokoko33, scroll chapters)
- Licence: **recreation MIT ©2023; original concept learn-only** (README: "original creator
  asks to please not use this exact idea").

Fully realtime, no bake, three 0.141.0: `DirectionalLight ×3 + AmbientLight + RectAreaLight`,
2048 PCFSoft shadows, `CineonToneMapping 1.75`; aquarium physical (transmission 1, ior 3);
GSAP ScrollTrigger + ASScroll chapters; ortho hero + perspective mix; GSAP light/dark lerp.

What to steal: scroll-chaptered tour as alternative to free-orbit; ortho-hero framing.

How it applies: template for optional "tour" mode (ScrollTrigger → camera + day/night uniform);
its realtime cost is the baseline baked+GTAO beats — cite, don't copy lighting.

## 6. Wawa Sensei baking guides (theory + MIT code)

- Hub: https://www.wawasensei.dev — Guides: https://www.wawasensei.dev/tuto/how-to-bake-lighting
  and https://www.wawasensei.dev/tuto/baking-guide
- Demos: https://baking.wawasensei.dev — Code: https://github.com/wass08/r3f-baking
  and https://github.com/wass08/r3f-baking-advanced
- Licence: **MIT ©2025** — https://github.com/wass08/r3f-baking/blob/main/LICENSE

Bake = Cycles→texture so three keeps look without realtime cost. Stack: SimpleBake (PBR),
UVPackmaster, Zen UV, `gltf.report` gate; Advanced: PBR sets + high→low (sculpt→normal/AO)
+ AO depth. R3F `meshBasicMaterial map=baked` equivalent.

What to steal: SimpleBake + UVPackmaster flow for multi-set WebP; high→low normal/AO for hero props.

How it applies: Wawa Advanced for props, Bruno/Sooa day/night shader for shell. Port
`map=baked` to Vite+TS `MeshBasicMaterial`.

## 7. Henry Heffernan — 3D desktop portfolio (MIT reusable)

- Live: https://henryheffernan.com (dual `#css + #webgl` layers, 2 hidden looping mp4s)
- Repo: https://github.com/henryjeff/portfolio-website (2.5k★, 348 forks; note username `henryjeff`)
- Licence: **MIT ©2024** — https://github.com/henryjeff/portfolio-website/blob/master/LICENSE.md
  (`package.json: "UNLICENSED"` quirk — LICENCE file governs).

Realtime PBR, no post: `MeshStandardMaterial` + emissive/normal/roughness, shadowmaps,
`ACESFilmicToneMapping`. No bake tokens. glTF + DRACO, `VideoTexture` dual monitors,
minimal KTX2. No composer. Camera `camera-controls ^1.34.2` dolly/zoom-to-cursor + tween/gsap;
signature move "click screen → dolly into monitor" (confirmed by forks
`vedanth-portfolio`, `mohammadali-2000/portfolio-website`). CRT-as-iframe portal: CSS3D
iframe → separate inner site (`portfolio-inner-site`, no licence → learn-only). Sound
three-native `Audio` + unlock; loading `LoadingManager + onProgress`; webpack + Express.
Bundle ~931 KB, three 0.137.5.

What to steal (MIT): CRT-as-iframe portal (defers DOM off WebGL thread);
`camera-controls` dolly-into-screen as GSAP-rig primitive.

How it applies: replicate portal for terminal/monitor; replace `camera-controls` with owned
damped dolly; keep Blender→GLB + DRACO.

## 8. Jesse Zhou — ramen shop (learn-only)

- Live: https://jesse-zhou.com ("Cooking Your Ramen… %", `START`, `canvas.webgl`)
- Repo: none public (`github.com/Jesse-zhou`: 0 public repos; `jezhou` unrelated)
- Licence: **all rights reserved, learn-only** (no public repo → no LICENCE).

Black-box bundle forensics (`bundle.7d6f6f7fdd10db02.js` 993 KB): emissive-forward night-market
look — `UnrealBloomPass`, `bloomStrength/Radius/Threshold`, `ACESFilmic`, `VideoTexture ×43`,
`EffectComposer + RenderPass + UnrealBloomPass + ShaderPass + SMAAPass` (SMAA-in-post ⇒ MSAA
off), heaviest Basis usage (`KTX2 ×98 / basis ×91`), `DRACOLoader`, gsap+tween, Howler (`Howl ×63`,
`visibilitychange`), `%`-loader + START audio-unlock gate. Zero GTAO/SSAO tokens.

What to steal (technique only): diegetic `%`-loader + START unlock; bloom-reserved-for-emissive;
Basis/KTX2 for texture-heavy sets; SMAA-in-post ordering.

How it applies: mirror post ordering (render → emissive bloom → output/SMAA); adopt START-gate;
keep GTAO cache + rect-area probes (strictly more advanced — this bundle has no AO).

## 9. Three.js Journey showcase + examples

- Highlights: https://threejs-journey.com/highlights/1 — Selection: https://threejs-journey.com/selection
  (includes `Soo-ah's Room Folio`)
- Examples: https://threejs.org/examples/ — Lessons: Portal Scene incl. "Baking and exporting"
- Licence: **three.js MIT** — https://github.com/mrdoob/three.js/blob/dev/LICENSE ;
  student works retain own rights (inspiration only).

Portal pattern (lessons 49–52): model → optimize → second UV → Cycles bake →
`MeshBasicMaterial` + additive details. Mirror in r186: `webgl_materials_video` (screens),
`webgl_postprocessing_unreal_bloom`, `webgl_materials_lightmap` (legacy — prefer custom
Bruno/Sooa shader).

## 10. Basement Studio — system (mixed licences)

- Live: https://basement.studio (clients Vercel, Linear, Cursor, xAI; own about block claims
  Awwwards/FWA/Webby honors)
- Repos: https://github.com/basementstudio — `website-2k25` (259★), `shader-lab` (689★),
  `scrollytelling` (1.7k★), `ship-25-explorations` (57★)
- Licences: **`shader-lab` Apache-2.0; `scrollytelling` MIT (+ GSAP notice);
  `website-2k25` + `ship-25-explorations` no LICENCE + `"private": true` → learn-only.**

`website-2k25` (`three ^0.180.0`, R3F 9-rc, drei, rapier, uikit, maath, meshline, r3f-perf):
asset gates `assets:verify/hash/exr-to-ktx2/basis:sync/glb-recode-webp` as `prebuild`.
`shader-lab` (Apache-2.0, `three` peer): portable runtime — `ShaderLabComposition` (direct),
`useShaderLab → CanvasTexture` (WebGL+WebGPU hosts), `postprocessing.render` (same-WebGPU
only); layers ASCII/blob-tracking/CRT/dither/halftone/ink/particle/pixelation/slice/chroma;
custom layer TSL `Fn()` + injected noise/SDF/tonemap utils (`simplexNoise, fbm, acesTonemap,
cinematicTonemap, sdBox2d…`); Source vs Effect mode. `scrollytelling`: GSAP ScrollTrigger
`<Root start end> + <Animation tween> + <Waypoint>` (`scrub:true, linear`), Three Tube example.
`ship-25-explorations`: one canvas `(with-canvas)/layout.tsx`, shared `GLOBAL_GL`, `?debug`
Leva + outlines. No custom audio; Next RSC + Sanity + `isbot`.

What to steal: asset-gate scripts as `prebuild`; `start/end`-positioned scroll timelines;
canvas-texture bridge + TSL injection pattern (Apache-2.0, `three` peer only).

How it applies: lift scrollytelling API shape onto vanilla ScrollTrigger driving camera rig;
copy KTX2/Basis gate into build; use `shader-lab` stack as grade reference (ASCII/dither/
halftone/chroma). Pin r186 separately (their R3F targets 0.180).

## 11. Basement × Vercel — Ship explorations (learn-only)

- Event: https://vercel.com/ship — Case: https://basement.studio/showcase/vercel-ship-a-home-for-innovation
- Explorations: https://ship-25-explorations.vercel.app (19 OGL routes: raymarch, fluid,
  depth floor, pyramid, liquid, morph, ferro, particles, water, svg-displacement…)
- Repo: https://github.com/basementstudio/ship-25-explorations (`"private": true`, no licence)
- Licence: **learn-only.**

Raw OGL shaders per effect (`ogl ^1.0.8`, `three ^0.174.0`, `glslify/glsl-noise/glsl-fxaa`,
`simplex-noise`, `detect-gpu`, `leva`, `stats.js`, gsap). In-shader FXAA/noise, one global
`Camera(GLOBAL_GL, fov 75)`, `detect-gpu` tiering, route-split loading.

What to steal: "one context + many small scenes" R&D method; `detect-gpu` tiering;
in-shader FXAA/noise instead of composer passes.

How it applies: mirror as Vite `/explorations/*` routes on a shared renderer singleton;
promote winners into room.

## 12. Lusion — Of The Oak (learn-only)

- Studio: https://lusion.co — Project: https://lusion.co/projects/of_the_oak
- Live: https://oftheoak.co.uk/ — About: https://lusion.co/about (58 Awwwards incl. SOTY,
  FWA SOTY+SOTD, CSSDA SOTY per own page) — R&D: https://labs.lusion.co/
- Licence: **closed-source, learn-only.**

Only verified performance claim (project page): "robust Houdini to WebGL pipeline that
compresses complex 3D tree, branch, and node structures into a custom web format, reducing
the download size to just 3.5 MB while leveraging WebGL instancing" (client MLF + Kew).
No disclosed lighting/post/camera stack.

What to steal: offline-pipeline mindset — heavy procedural work in Houdini/Blender, bespoke
compact buffer + instancing, not raw GLBs. 3.5 MB ecosystem budget to beat.

How it applies: pre-bake dressing to KTX2 + DRACO, merge by material, one `InstancedGroup`
per family. Budget shell + dressing ≤4 MB gzipped.

## 13. Locomotive — scroll-as-camera (MIT)

- Agency: https://locomotive.ca/en — Library: https://github.com/locomotivemtl/locomotive-scroll
  (8.9k★, 1.1k forks, 9.4 kB gzip, TS-first, Lenis-based, dual IntersectionObservers,
  touch-gated parallax, native scrollbar + ARIA)
- Licence: **MIT.**

Camera language is DOM: Lenis smooth-scroll + `data-scroll-speed` parallax + in-view split.

What to steal: two-observer split; touch-gate; `data-scroll-speed` authoring primitive.

How it applies: drive dolly camera from Lenis + locomotive exact-pattern (scroll → GSAP →
waypoint lerp, Bruno `magnet 0.25` easing); disable parallax/DOF on touch via quality gate.
Cheapest cinematic camera available.

## 14. Immersive Garden × Bruno collabs (learn-only)

- Index: https://threejs-journey.com (projects list: Chartogne Taillet, Prior Holdings, Orano
  with Immersive Garden; Madbox/Luni/Scout with Hervé)
- Live attempts: https://chartogne-taillet.com (JS-gated shell); https://prior.co.jp/discover/
  (timeout); https://immersive-garden.com (521) — technique from course syllabus, not live sites
- Licence: **closed-source, learn-only.**

Bake-first doctrine (fetched lessons: Baking/exporting, Environment map, Realistic render,
Post-processing, Performance tips, Code structuring): Blender lightmaps/AO/emissive →
unlit-ish materials + envmap; runtime lights near-zero; bake *is* the grade; scroll/chapter
dolly; staged reveal after bake textures resolve.

What to steal: one-directional + baked AO/emissive, not six dynamic lights.

How it applies: Blender bake diffuse/AO/lightmap + small envmap, KTX2 GLB (Bruno compress,
MIT), single-shadow-sun runtime; chapters (desk → shelf → wall) as scroll waypoints.

## 15. Drop-in libraries — verdicts

Room already has `three-mesh-bvh ^0.9.15` (MIT, 48 kB lazy chunk; per-ray 1.46→0.08 ms —
keep) and `@gltf-transform/{core,extensions,functions} ^4.5.0` (MIT).

- **KTX2/Basis runtime — SKIP.** `three` 0.186.1 (https://www.npmjs.com/package/three, MIT),
  `ktx-parse` 2.0.0 (https://www.npmjs.com/package/ktx-parse, MIT ©2020 Don McCurdy),
  `basis_universal` + `KTX-Software` (Apache-2.0). `KTX2Loader` ships in-tree (worker pool,
  ETC1S/UASTC → ASTC/BC7/S3TC/ETC2/PVRT transcode). 7 maps are ~680 KB JPG via `ImageBitmap`
  behind loader; per-material ≤0.5 ms; bottleneck is shaded pixels + MSAA resolve, not fetch.
  Costs real: >200 KB WASM + worker lifecycle on 1.3 s startup, ETC1S wrecks normal/roughness
  (UASTC needed), `flipY`/tiling re-validation. Revisit only on VRAM/upload trace evidence.
  Note: glTF-Transform v4 has no `toktx` function — KTX via CLI `etc1s/uastc/ktxdecompress`
  (https://gltf-transform.dev/cli.html); `textureCompress` is WebP/AVIF/JPEG/PNG only.
- **glTF-Transform `weld` + `reorder` — ADOPT.** MIT (https://github.com/donmccurdy/glTF-Transform).
  Zero runtime bytes, better vertex cache. Append after `quantize` in `optimize-glb.mjs`,
  re-run frozen-grain gate (`perf/LOG.md` §Assets: 0.28–0.36 mean = noise floor).
- **`textureCompress` / CLI `webp` + `resize` — ADOPT.** MIT. Biggest remaining asset lever
  (textures +683 KB last pass vs models 1.19 MB); no decoder. Exclude/QA `normalTexture`
  slots; re-score daylight cube saturation (`bloom-score` + `cube-color`).
- **`draco` / `meshopt` decoders — SKIP.** `draco3dgltf` 1.5.7 Apache-2.0 (~800 KB unpacked),
  `meshoptimizer` 1.3.0 MIT. Best file-size reduction but new WASM on startup, fights
  `assets.ts` dequantize-on-arrival + metre-slicing. Revisit only if models grow >3–4×.
  (`simplify/join/flatten/unwrap/palette` also SKIP: fill-bound frame gains nothing from verts;
  custom `merge.ts` already 168→93 calls.)
- **Lightmap / baked GI — SKIP (already decided twice with numbers).** `Material.lightMap` +
  `ProgressiveLightMap` exist in r186 (MIT) but need UV2 this room lacks (`textures.ts`
  projects in metres because UVs absent/0–1-per-face). Remaining per-light 0.1–0.3 ms after
  96³ rect-volume bake; baking freezes moving sun/lamp; progressive accumulation conflicts
  with rotation-reprojection cache. Revisit only if sun/lamp go static *and* UV2 exists.
- **`pmndrs/postprocessing` migration — SKIP, borrow ideas.** `postprocessing` 6.39.5
  (https://www.npmjs.com/package/postprocessing, Zlib, 0 deps, peer `three >=0.168 <0.187`
  ⊃ r186 — verified via raw `package.json`). Room already collapsed six full-res passes into
  one `GradedOutputPass` (−1.3…−2.5 ms), MSAA once, swap buffers →1px (~60 MB back). Porting
  `CachedGTAOPass`/volumetric/outline/exposure-bloom/AgX ordering as custom `Effect`s rewrites
  two passes' measured work to save nothing.

## 16. Other drop-ins

- `meshoptimizer` decoder 1.3.0 (MIT, https://www.npmjs.com/package/meshoptimizer) — SKIP
  unless `meshopt` compression adopted; then lazy-import like BVH chunk.
- `maath` 0.10.8 (MIT, https://www.npmjs.com/package/maath ; successor `pmndrs/math` MIT
  ©2026) — SKIP (room owns rig/calibration/dust math; cherry-pick single helper only if it
  deletes identical hand code).
- `@pmndrs/vanilla` 1.25.0 (`drei-vanilla`, MIT ©2023, https://github.com/pmndrs/drei-vanilla)
  — SKIP (`pcss` vs custom disk-lamp PCSS, `AccumulativeShadows` static-only vs moving sun,
  `MeshTransmissionMaterial` extra pass vs fill-bound).
- `idb-keyval` 6.3.0 (Apache-2.0, https://www.npmjs.com/package/idb-keyval, ~295–573 B brotli)
  — OPTIONAL, measure first: version-keyed IDB for GLBs + `ltc.bin` only (~1.9 MB assets,
  repeat-visit ~200–360 ms fetch); must not regress first-visit startup.

## Fetch failures (explicitly not claimed)

- `https://www.awwwards.com/websites/three-js/` → 403; `https://prior.co.jp/discover/` → timeout;
  `https://immersive-garden.com` → 521; `https://github.com/Naxela/TheLightmapper` → 404
  (no verifiable three.js-web baker — do not adopt). Rachel Wei room (cited inspo) JS-gated,
  no claims made. Resn/Active Theory/Dennis Snellenberg shells unverified this pass.
