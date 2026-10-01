"""v2-look item 1: are the black shapes the bake's contact shadows of props that are not on the web yet?

  python scripts/v2look/missing_props.py <work_dir> <label>

Uses ref_<cam>.png (full Cycles), prev_<cam>.png (baked-only, non-baked objects as HOLDOUT: alpha marks
baked surfaces Cycles actually shows), hidden/prevh_<cam>.png (baked-only, non-baked objects HIDDEN: the
room with nothing in it, through the same view transform) and shots/<label>_<cam>.png (web).
"""
import json, os, sys
import numpy as np
from PIL import Image

work, label = sys.argv[1], sys.argv[2]
LUMA = np.array([0.2126, 0.7152, 0.0722])
png = lambda p: np.asarray(Image.open(p).convert('RGBA'), dtype=np.float64)
out = {}
for cam in ('CAM_stand', 'CAM_seat'):
    ref = png(f'{work}/ref_{cam}.png')[..., :3]
    prev = png(f'{work}/prev_{cam}.png')
    hid = png(f'{work}/hidden/prevh_{cam}.png')
    web = png(f'{work}/shots/{label}_{cam}.png')[..., :3]
    shown = prev[..., 3] > 0.99 * 255          # baked surface visible in the full scene
    bare = hid[..., 3] > 0.99 * 255            # baked surface visible with every prop removed
    missing = bare & (prev[..., 3] < 0.01 * 255)  # visible on the web only because something is missing
    L = lambda im, m: im[m] @ LUMA
    dark = lambda im, m: float((L(im, m) < 25).mean())
    d = np.abs(web - hid[..., :3])[bare]
    out[cam] = dict(
        frame_fraction_missing=round(float(missing.mean()), 3),
        frame_fraction_baked_shown=round(float(shown.mean()), 3),
        luma_at_missing=dict(cycles_full_ref=round(float(L(ref, missing).mean()), 1),
                             cycles_bake_props_hidden=round(float(L(hid[..., :3], missing).mean()), 1),
                             web=round(float(L(web, missing).mean()), 1)),
        share_dark_lt25=dict(web_at_missing=round(dark(web, missing), 3), web_elsewhere_baked=round(dark(web, shown), 3),
                             cycles_bake_props_hidden_at_missing=round(dark(hid[..., :3], missing), 3)),
        web_vs_cycles_props_hidden=dict(mae=[round(float(x), 2) for x in d.mean(0)], mae_mean=round(float(d.mean()), 2),
                                        mae_at_missing=round(float(np.abs(web - hid[..., :3])[missing].mean()), 2)),
    )
    # picture: full Cycles | Cycles baked-only, props hidden | web; missing pixels outlined in red on the last
    edge = missing ^ np.roll(missing, 1, 0) | missing ^ np.roll(missing, 1, 1)
    w2 = web.copy(); w2[edge] = [255, 40, 40]
    sep = np.full((ref.shape[0], 6, 3), 255.0)
    Image.fromarray(np.concatenate([ref, sep, hid[..., :3] * (hid[..., 3:] / 255), sep, w2], 1).astype(np.uint8)).save(f'{work}/shots/missing_{label}_{cam}.png')
print(json.dumps(out, indent=1))
json.dump(out, open(f'{work}/shots/missing_{label}.json', 'w'), indent=1)
