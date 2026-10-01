"""
Numeric check of a lit prop texture: the lit image INSIDE the shipped GLB, decoded (sRGB -> linear) and
multiplied by the material's litScale, must match the denoised Cycles bake (EXR) it came from.

    blender -b --factory-startup --python blender/scripts/v2_verify_lit.py -- <name> [name ...]
        [--dir public/assets/v2/props] [--tex tmp/props_raw/tex]

Compares texels the bake covered and that are not clipped (EXR < litScale): prints the mean ratio
decoded/EXR, the median relative error and the share of texels within 5 %.
"""
import bpy
import json
import os
import struct
import sys
import tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default):
    if name in ARGS:
        i = ARGS.index(name)
        v = ARGS[i + 1]
        del ARGS[i:i + 2]
        return v
    return default


DIR = os.path.join(REPO, arg('--dir', os.path.join('public', 'assets', 'v2', 'props')))
TEX = os.path.join(REPO, arg('--tex', os.path.join('tmp', 'props_raw', 'tex')))


def read_glb(path):
    with open(path, 'rb') as f:
        f.read(12)
        clen, _ = struct.unpack('<II', f.read(8))
        js = json.loads(f.read(clen))
        blen, _ = struct.unpack('<II', f.read(8))
        return js, f.read(blen)


def load_pixels(path, data):
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'Non-Color' if data else img.colorspace_settings.name
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    out = a.reshape(img.size[1], img.size[0], 4)
    bpy.data.images.remove(img)
    return out


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


for name in ARGS:
    js, binc = read_glb(os.path.join(DIR, name + '.glb'))
    lit = [m for m in js['materials'] if 'KHR_materials_unlit' in m.get('extensions', {})]
    if not lit:
        print(f'[verify-lit] {name}: no lit material')
        continue
    m = lit[0]
    k = m.get('extras', {}).get('litScale', 1.0)
    tex = js['textures'][m['pbrMetallicRoughness']['baseColorTexture']['index']]
    src = tex.get('source', tex.get('extensions', {}).get('EXT_texture_webp', {}).get('source'))
    im = js['images'][src]
    bv = js['bufferViews'][im['bufferView']]
    blob = binc[bv.get('byteOffset', 0): bv.get('byteOffset', 0) + bv['byteLength']]
    ext = '.webp' if im['mimeType'] == 'image/webp' else '.png' if im['mimeType'] == 'image/png' else '.jpg'
    tmp = os.path.join(tempfile.gettempdir(), f'verify_lit_{name}{ext}')
    open(tmp, 'wb').write(blob)
    enc = load_pixels(tmp, data=True)[..., :3]          # raw sRGB code values
    dec = srgb_to_linear(enc) * k
    exr = load_pixels(os.path.join(TEX, name, f'{name}_lit_dn.exr'), data=True)[..., :3]
    if exr.shape != dec.shape:
        print(f'[verify-lit] {name}: size mismatch {exr.shape} vs {dec.shape}')
        continue
    lum_e = exr.max(axis=2)
    lum_d = dec.max(axis=2)
    sel = (lum_e > 0.02 * k) & (lum_e < 0.98 * k)       # well inside the 8-bit range, not clipped
    rel = np.abs(lum_d[sel] - lum_e[sel]) / lum_e[sel]
    print('[verify-lit] ' + json.dumps(dict(
        name=name, litScale=k, texels=int(sel.sum()),
        mean_ratio=round(float(lum_d[sel].mean() / lum_e[sel].mean()), 4),
        median_rel_err=round(float(np.median(rel)), 4),
        within_5pct=round(float((rel < 0.05).mean()), 4),
        clipped_share=round(float((lum_e >= k).mean()), 5))), flush=True)
