"""v2-look: numbers and side-by-sides for web frames against the Cycles references, same pose.

  python scripts/v2look/compare.py <work_dir> <label> [<label> ...]

<work_dir> holds the Blender outputs of blender_probe.py / blender_lut.py (ref_<cam>.png, prev_<cam>.png,
prev_<cam>.npy, ...) and shots/<label>_<cam>.png (+ .lin.f32) from capture.mjs.

Masks (from the transparent-film preview render, alpha > 0.99):
  baked   pixels where the full Cycles scene shows a baked surface (props, exterior, glass excluded:
          they are holdouts in the preview, so whatever hides a baked surface is not counted).
Metrics, display-referred 8-bit (0..255), over the mask:
  mae[r,g,b], bias[r,g,b] (web - ref), luma mean ref/web, share of pixels within 5 and 10 steps.
  vs 'ref'  : the full Cycles render (what Blender shows; includes specular and everything)
  vs 'prev' : Cycles baked-only preview, base colour x lightmap through the same view transform
Linear (scene-referred, before exposure) over the mask, with --linear captures:
  ratio web/prev of the mean per channel, and median |log2(web/prev)| per channel.
"""
import json, os, sys
import numpy as np
from PIL import Image

work = sys.argv[1]
labels = sys.argv[2:]
CAMS = ['CAM_stand', 'CAM_seat']
LUMA = np.array([0.2126, 0.7152, 0.0722])


def png(p):
    return np.asarray(Image.open(p).convert('RGBA'), dtype=np.float64)


def stats(web, ref, m):
    d = (web - ref)[m]
    ad = np.abs(d)
    lw, lr = web[m] @ LUMA, ref[m] @ LUMA
    dl = np.abs(lw - lr)
    return dict(mae=[round(float(x), 2) for x in ad.mean(0)], mae_mean=round(float(ad.mean()), 2),
                bias=[round(float(x), 2) for x in d.mean(0)],
                luma_ref=round(float(lr.mean()), 1), luma_web=round(float(lw.mean()), 1),
                luma_mae=round(float(dl.mean()), 2),
                within5=round(float((dl < 5).mean()), 3), within10=round(float((dl < 10).mean()), 3))


out = {}
for cam in CAMS:
    ref = png(os.path.join(work, f'ref_{cam}.png'))[..., :3]
    prev_rgba = png(os.path.join(work, f'prev_{cam}.png'))
    m = prev_rgba[..., 3] > 0.99 * 255
    prev = prev_rgba[..., :3]
    lin_prev = np.load(os.path.join(work, f'prev_{cam}.npy'))[..., :3]
    out[cam] = dict(baked_fraction=round(float(m.mean()), 3), cycles_prev_vs_ref=stats(prev, ref, m))
    for lab in labels:
        p = os.path.join(work, 'shots', f'{lab}_{cam}.png')
        if not os.path.exists(p):
            continue
        web = png(p)[..., :3]
        r = dict(vs_ref=stats(web, ref, m), vs_prev=stats(web, prev, m))
        lp = os.path.join(work, 'shots', f'{lab}_{cam}.lin.f32')
        if os.path.exists(lp):
            lw = np.fromfile(lp, dtype=np.float32).reshape(ref.shape[0], ref.shape[1], 3)
            a, b = lw[m], lin_prev[m]
            ok = (a > 1e-4).all(1) & (b > 1e-4).all(1)
            r['linear_vs_prev'] = dict(mean_ratio=[round(float(x), 3) for x in a.mean(0) / b.mean(0)],
                                       median_abs_log2=[round(float(x), 3) for x in np.median(np.abs(np.log2(a[ok] / b[ok])), 0)])
        out[cam][lab] = r
        # side by side: Cycles reference | web, and |difference| x4 on the baked mask
        diff = np.zeros_like(ref)
        diff[m] = np.clip(np.abs(web - ref)[m] * 4, 0, 255)
        sep = np.full((ref.shape[0], 6, 3), 255.0)
        Image.fromarray(np.concatenate([ref, sep, web], 1).astype(np.uint8)).save(os.path.join(work, 'shots', f'sbs_{lab}_{cam}.png'))
        Image.fromarray(diff.astype(np.uint8)).save(os.path.join(work, 'shots', f'diff_{lab}_{cam}.png'))
json.dump(out, open(os.path.join(work, 'shots', 'compare_' + '_'.join(labels) + '.json'), 'w'), indent=1)
print(json.dumps(out, indent=1))
