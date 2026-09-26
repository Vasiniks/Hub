# Workstream: research reference sites and reusable technique (branch ws/research)

Read `.claude/briefs/_common.md` first. **This workstream writes documentation only** — no changes
under `src/`, `assets/` or `public/`.

The owner: "if it exists, don't reinvent the wheel. Research websites similar to mine, take their
shaders, use their models, mimic their styles."

## What to do
1. Find the best existing work in this exact genre: first-person / room-scale / desk-scene WebGL
   portfolios and cinematic three.js sites. Start from (verify each, add your own finds):
   Bruno Simon's room and portfolio, Henry Heffernan's WebGL desktop, Jesse Zhou's ramen shop,
   Andrew Woan's room scenes, the three.js journey community showcase, Awwwards' three.js winners,
   Vercel/Basement/Lusion studio work.
2. For each: what makes it look good (lighting model, baking strategy, materials, post chain,
   camera language, sound, loading), and how it performs. Concrete technique, not vibes.
3. **Separate what we can legally reuse from what we can only learn from.** Many of these have
   public repos: record the licence for each (MIT/Apache = reusable with attribution; no licence
   file = all rights reserved, learn only, do not copy). Shader snippets, baking workflows and
   camera rigs are usually the reusable parts; art assets usually are not.
4. Pay special attention to **baked lighting workflows** (Bruno Simon and Andrew Woan bake in
   Blender and ship textures — exactly what this room is moving toward) and to **material/texture
   treatment**, since those are our two open problems.
5. Produce `docs/research/reference-sites.md`: one section per site with links, what to steal, the
   licence, and an explicit "how it applies to this room" note. Then a short prioritised list at the
   top: the five things we should adopt next, cheapest first.

Also check the three.js ecosystem for drop-in libraries we are not using but should
(e.g. `three-mesh-bvh` is already in; look at KTX2/Basis tooling, `gltf-transform` options,
lightmap tooling, `postprocessing` (pmndrs) vs our hand-rolled chain) — with licences.

## Definition of done
`docs/research/reference-sites.md` committed on ws/research, factual, every claim linked, licences
recorded, plus `.claude/briefs/report-research.md` with the prioritised recommendations.
