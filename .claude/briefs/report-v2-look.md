# Report: v2-look (branch `ws/v2-look`, last commit 438c088)

The subagent returned this report as its final message (subagents cannot write report files); the
coordinator committed it. Evidence (side-by-sides, JSON): `.claude/briefs/v2-look/`.

## Method

- **Error measure:** mean absolute error in 8-bit display steps, only over pixels where Cycles shows a baked surface
  (58.6% of the stand frame, 26.5% of the seat frame).
- **Cameras:** `CAM_stand` and `CAM_seat` (54°) read from `room_bake.blend`.
- **References:** Blender rendered each at 960×540, the full frame plus the bake-only preview, whose alpha gives the
  mask.
- **Web frames:** taken at the identical pose on the real GPU.

## Error against the full Cycles frame (lower is better)

| variant | stand | seat |
|---|---|---|
| shipped before | 24.6 | 24.5 |
| Blender LUT, old albedo | 25.3 | 10.2 |
| real albedo, three AgX + old grade | 10.8 | 24.4 |
| real albedo, three AgX, no old grade | 13.3 | 14.7 |
| **now** | **7.3** | **10.1** |
| now + environment specular | 8.1 | 12.6 |
| floor: Cycles bake-only preview | 6.7 | 9.0 |

**Within 10 luma steps of Cycles:** 0.41 → 0.79 (stand), 0.35 → 0.75 (seat).

**Scene-linear ratio, web ÷ Cycles:** stand went [1.84, 1.57, 1.36] → [0.963, 0.965, 0.968].

## Causes: two runtime bugs; the lightmaps were fine

1. **Albedo.** The atlas GLBs carry no images. The glTF exporter wrote 0.8 grey for every base colour built from a
   node graph, then merged materials that looked identical. The real wall colour is 0.29 blue-grey, so on the web the
   walls were 1.4–1.8× too bright.
   - Fix: `albedo_<atlas>` atlases, Cycles' diffuse colour pass baked in the lightmap UV layout. Colour only; no
     lighting was re-baked.
2. **Grade.** three's `AgXToneMapping` is a polynomial fit of an older AgX with no looks. Blender 5.2's AgX is a
   25-stop 3D LUT, and the "Medium High Contrast" look runs inside it.
   - Fix: a 33³ table evaluated from Blender's own `config.ocio` with PyOpenColorIO. It matches Blender's
     save-as-render to 0.003 of a step on average and 0.008 at most.
   - It is applied in the existing output pass, so there is no extra pass.

## The four brief items

1. **Black shapes on the desk:** the contact shadows of props that had not been exported yet. Confirmed against
   Cycles with the props hidden (MAE 2.3 / 2.4) and left alone.
2. **Window:** the glass was not exported (the exterior workstream's job).
3. **Grade:** fixed as above.
4. **Environment specular:** built but **off by default**. It made the match worse (7.3 → 8.1, 10.1 → 12.6), because
   it reflected the placeholder background with nothing occluding it.

## Cost

- **Whole v2 frame:** 0.65–0.76 ms at 1728×1000 ×1.5 on the RTX 5070. LUT vs AgX and specular on vs off are both
  within noise.
- **Download:** LUT 216 KB, albedo atlases 623 KB as PNG (later WebP).

## Only a re-bake or another workstream can fix

- **Pre-lit props:** must store scene-linear radiance before exposure (followed by web-props).
- **Specular:** not in the bake.
- **Next sunset export:** should write the real albedo into the GLBs and stop the material merge.
- **Remaining gap ≈ the 6.7 / 9.0 floor:** specular, glass and bake noise.
