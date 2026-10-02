"""Ship the baked room's maps as lossless WebP: lightmaps (RGBM PNGs from blender/bake/sunset) and albedo
atlases (PNGs from scripts/v2look/blender_albedo.py), each checked bit-identical to its PNG after decoding.
Writes public/assets/v2/room/{lightmap_<a>.rgbm.webp, albedo_<a>.webp, manifest.json, albedo.json}.

    python scripts/v2look/encode_room_webp.py --albedo <albedo out dir> [--bake blender/bake/sunset]
                                              [--dst public/assets/v2/room]

manifest.json is the bake manifest with `atlases.<a>.web.file` pointing at the WebP (bytes updated, PNG
size kept as `png_bytes`); albedo.json is blender_albedo.py's with `file` pointing at the WebP.

Indirect-only lightmaps (blender/scripts/v2_bake_indirect.py, for live sun + lamp): wherever the bake manifest has
`atlases.<a>.indirect`, lightmap_<a>.indirect.rgbm.png ships as lightmap_<a>.indirect.rgbm.webp the same way, and
`atlases.<a>.indirect = {file, range_sqrt, linear_max, ...}` is written. To add just those (plus `materials` and
`lights`) to an already shipped manifest without touching its `web` entries or re-encoding anything else:

    python scripts/v2look/encode_room_webp.py --indirect-only
"""
import argparse, copy, json, os
import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('--bake', default='blender/bake/sunset')
ap.add_argument('--albedo')
ap.add_argument('--indirect-only', action='store_true')
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


INDIRECT_KEYS = ('method', 'mean_linear', 'max_linear', 'share_of_full', 'sanity_B_plus_indirect_vs_A')


def ship_indirect(pub, man):
    """atlases.<a>.indirect (WebP) and .materials from the bake manifest; lights/materials notes. Returns bytes."""
    total = 0
    for name, at in man['atlases'].items():
        ind = at.get('indirect')
        if not ind:
            continue
        png = ind['web']['file']
        webp = png[:-4] + '.webp'
        b, pb, mode = to_webp(os.path.join(a.bake, png), os.path.join(a.dst, webp))
        w = ind['web']
        pub['atlases'][name]['indirect'] = dict(
            file=webp, range_sqrt=w['range_sqrt'], linear_max=w['linear_max'], bytes=b, png_bytes=pb,
            encoding='RGBM of sqrt(L), 8-bit RGBA lossless WebP (bit-identical to the PNG), linear data',
            decode=w['decode'], mean_rel_err=w['mean_rel_err'], clipped_fraction=w['clipped_fraction'],
            holds='L_full - L_direct(SUN_main + LAMP_disk): sky, emissives, street lights and every bounce',
            **{k: ind[k] for k in INDIRECT_KEYS if k in ind})
        if 'materials' in at:
            pub['atlases'][name]['materials'] = at['materials']
        print(f'indirect {name}: {pb} B png -> {b} B webp ({mode}, bit-identical)')
        total += b
    for k in ('lights', 'materials_note'):
        if k in man:
            pub[k] = man[k]
    if 'indirect_bake' in man:
        ib = man['indirect_bake']
        pub['indirect_bake'] = {k: ib[k] for k in ('pass_b_settings', 'combine', 'darkcheck') if k in ib}
    return total


man = json.load(open(os.path.join(a.bake, 'manifest.json')))
if a.indirect_only:
    dst_man = os.path.join(a.dst, 'manifest.json')
    pub = json.load(open(dst_man))
    before = json.dumps({n: at['web'] for n, at in pub['atlases'].items()}, sort_keys=True)
    t = ship_indirect(pub, man)
    assert json.dumps({n: at['web'] for n, at in pub['atlases'].items()}, sort_keys=True) == before
    json.dump(pub, open(dst_man, 'w'), indent=1)
    print('indirect maps total', t, 'bytes; web entries unchanged')
    raise SystemExit(0)
assert a.albedo, '--albedo is required (or --indirect-only)'
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
total += ship_indirect(pub, man)
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
