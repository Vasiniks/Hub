"""Ship the baked room's maps as lossless WebP: lightmaps (RGBM PNGs from blender/bake/sunset) and albedo
atlases (PNGs from scripts/v2look/blender_albedo.py), each checked bit-identical to its PNG after decoding.
Writes public/assets/v2/room/{lightmap_<a>.rgbm.webp, albedo_<a>.webp, manifest.json, albedo.json}.

    python scripts/v2look/encode_room_webp.py --albedo <albedo out dir> [--bake blender/bake/sunset]
                                              [--dst public/assets/v2/room]

manifest.json is the bake manifest with `atlases.<a>.web.file` pointing at the WebP (bytes updated, PNG
size kept as `png_bytes`); albedo.json is blender_albedo.py's with `file` pointing at the WebP.
"""
import argparse, copy, json, os
import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('--bake', default='blender/bake/sunset')
ap.add_argument('--albedo', required=True)
ap.add_argument('--dst', default='public/assets/v2/room')
a = ap.parse_args()
os.makedirs(a.dst, exist_ok=True)


def to_webp(src, dst):
    im = Image.open(src)
    im.load()
    mode = 'RGBA' if im.mode in ('RGBA', 'LA', 'P') and 'A' in im.getbands() else 'RGB'
    im = im.convert(mode)
    im.save(dst, 'WEBP', lossless=True, quality=100, method=6, exact=True)
    back = Image.open(dst)
    back.load()
    ok = np.array_equal(np.asarray(im), np.asarray(back.convert(mode)))
    assert ok, f'{dst}: lossless WebP does not decode bit-identical to {src}'
    return os.path.getsize(dst), os.path.getsize(src), mode


man = json.load(open(os.path.join(a.bake, 'manifest.json')))
pub = copy.deepcopy(man)
total = 0
for name, at in pub['atlases'].items():
    png = at['web']['file'] if at['web']['file'].endswith('.png') else f'lightmap_{name}.rgbm.png'
    webp = png[:-4] + '.webp'
    b, pb, mode = to_webp(os.path.join(a.bake, png), os.path.join(a.dst, webp))
    at['web'].update(file=webp, bytes=b, png_bytes=pb,
                     encoding='RGBM of sqrt(L), 8-bit RGBA lossless WebP (bit-identical to the PNG), linear data')
    print(f'lightmap {name}: {pb} B png -> {b} B webp ({mode}, bit-identical)')
    total += b
json.dump(pub, open(os.path.join(a.dst, 'manifest.json'), 'w'), indent=1)

alb = json.load(open(os.path.join(a.albedo, 'albedo.json')))
for name, at in alb['atlases'].items():
    png = at['file']
    webp = png[:-4] + '.webp'
    b, pb, mode = to_webp(os.path.join(a.albedo, png), os.path.join(a.dst, webp))
    at.update(file=webp, bytes=b, png_bytes=pb)
    print(f'albedo {name}: {pb} B png -> {b} B webp ({mode}, bit-identical)')
    total += b
alb['source'] = 'blender/bake/sunset/room_bake.blend (read only)'
json.dump(alb, open(os.path.join(a.dst, 'albedo.json'), 'w'), indent=1)
print('maps total', total, 'bytes')
