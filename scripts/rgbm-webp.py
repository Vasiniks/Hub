"""
Hybrid props: turn the indirect lightmaps (RGBM PNGs written by v2_export_web.py --rt) into lossless
WebP next to the GLBs, and prove the round trip is exact.

    python scripts/rgbm-webp.py [set ...]     (default: every set with a sidecar in tmp/props_rt_raw)
    env: RT_SRC (default tmp/props_rt_raw), RT_DST (default public/assets/v2rt/props)

Lossless with exact=True: libwebp would otherwise rewrite RGB under alpha = 0, and RGBM keeps data there.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

SRC = os.environ.get('RT_SRC', 'tmp/props_rt_raw')
DST = os.environ.get('RT_DST', 'public/assets/v2rt/props')
os.makedirs(DST, exist_ok=True)
names = sys.argv[1:] or sorted(f[:-5] for f in os.listdir(SRC) if f.endswith('.json'))
total = 0
for n in names:
    side = json.load(open(os.path.join(SRC, n + '.json')))
    rt = side.get('rt')
    if not rt:
        print(f'{n}: no rt lightmap in the sidecar, skipped')
        continue
    for at in rt.get('atlases', [rt]):          # one lightmap per PBR atlas (the PC has three)
        png = os.path.join(SRC, 'tex', n, at['png'])
        out = os.path.join(DST, at['lightmap'])
        im = Image.open(png).convert('RGBA')
        im.save(out, 'WEBP', lossless=True, exact=True, quality=100, method=6)
        a = np.asarray(im)
        b = np.asarray(Image.open(out).convert('RGBA'))
        same = bool((a == b).all())
        size = os.path.getsize(out)
        total += size
        print(f'{n}: {at["lightmap"]} {im.size[0]}^2 {size / 1024:.0f} KB  round-trip exact: {same}')
        if not same:
            raise SystemExit(f'{n}: lossless WebP round trip changed pixels')
print(f'total {total / 1024:.0f} KB')
