"""v2-look: bake each lightmap atlas's ALBEDO (Cycles diffuse colour pass) in the lightmap UV layout.

Why: the atlas GLBs carry no images and the glTF exporter writes baseColorFactor 0.8 for every
material whose base colour is a node graph (walls, floor wood, rug, desk-frame nylon, the bambu
table, the bookrack board), then merges the identical-looking materials. The lightmap L is correct;
the albedo it multiplies is not. This bakes the albedo Cycles actually used, in the same UV layout
(UVMap_lightmap) and with the same margin as the lightmap, so the runtime does `albedo * L` exactly.

The diffuse COLOR pass is the right partner for the lightmap: the lightmap is Cycles' DIFFUSE bake
with colour off, i.e. the diffuse pass divided by this very colour pass, so colour x L is Cycles'
diffuse output (including the Principled BSDF's specular-layer energy loss, and translucency on the
curtains, both of which a plain base colour misses).

Decals (rs_scuff_*: Mix(Transparent, Principled)) also get their coverage baked (EMIT of the mix
factor) into alpha; their RGB is un-premultiplied albedo.

Lighting is untouched: no light bake happens here and nothing is saved to the .blend.

  blender -b <room_bake.blend> --python scripts/v2look/blender_albedo.py -- <out_dir> [--scale 1] [--samples 16]
writes <out_dir>/albedo_<atlas>.png (8-bit sRGB RGB, or RGBA when the atlas has decals) and albedo.json
"""
import bpy, os, sys, json, time, zlib, struct
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = os.path.abspath(argv[0])
SCALE = float(argv[argv.index('--scale') + 1]) if '--scale' in argv else 1.0
SPP = int(argv[argv.index('--samples') + 1]) if '--samples' in argv else 16
os.makedirs(OUT, exist_ok=True)
BAKE_DIR = os.path.dirname(bpy.data.filepath)
man = json.load(open(os.path.join(BAKE_DIR, 'manifest.json')))
LM_UV = man['uv_layer']
MARGIN = man['bake_settings']['margin_px']
NODE = 'V2LOOK_BAKE'
sc = bpy.context.scene

prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.refresh_devices()
for d in prefs.devices:
    d.use = (d.type == 'CUDA')
sc.render.engine = 'CYCLES'
sc.cycles.device = 'GPU'
sc.cycles.samples = SPP
sc.cycles.use_adaptive_sampling = False
sc.cycles.use_denoising = False


def png_write(u8, path):
    """u8 (h, w, c) uint8, top row first; plain zlib PNG, no colour chunks."""
    h, w, c = u8.shape
    raw = np.concatenate([np.zeros((h, 1), np.uint8), u8.reshape(h, w * c)], axis=1)
    a = u8.astype(np.int16)
    up = a.copy(); up[1:] = (a[1:] - a[:-1]) % 256
    raw_up = np.concatenate([np.full((h, 1), 2, np.uint8), up.astype(np.uint8).reshape(h, w * c)], axis=1)
    z = min((zlib.compress(r.tobytes(), 9) for r in (raw, raw_up)), key=len)

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, {3: 2, 4: 6}[c], 0, 0, 0))
                + chunk(b'IDAT', z) + chunk(b'IEND', b''))
    return os.path.getsize(path)


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def target(mats, img):
    for m in mats:
        nt = m.node_tree
        n = nt.nodes.get(NODE) or nt.nodes.new('ShaderNodeTexImage')
        n.name = NODE
        n.image = img
        for x in nt.nodes:
            x.select = False
        n.select = True
        nt.nodes.active = n


def coverage_rewire(m):
    """Temporarily make the surface Emission(coverage). Returns an undo closure."""
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
    old = out.inputs['Surface'].links[0].from_socket
    surf = old.node
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 1.0
    made = [em]
    if surf.type == 'MIX_SHADER':
        a, b = surf.inputs[1], surf.inputs[2]
        ta = a.is_linked and a.links[0].from_node.type == 'BSDF_TRANSPARENT'
        tb = b.is_linked and b.links[0].from_node.type == 'BSDF_TRANSPARENT'
        fac = surf.inputs[0]
        if ta or tb:
            if fac.is_linked:
                src = fac.links[0].from_socket
                if tb:  # coverage = 1 - factor
                    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
                    nt.links.new(src, inv.inputs[1]); src = inv.outputs[0]; made.append(inv)
                nt.links.new(src, em.inputs['Color'])
            else:
                v = fac.default_value if ta else 1 - fac.default_value
                em.inputs['Color'].default_value = (v, v, v, 1)
        else:
            em.inputs['Color'].default_value = (1, 1, 1, 1)
    else:
        em.inputs['Color'].default_value = (1, 1, 1, 1)
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])

    def undo():
        nt.links.new(old, out.inputs['Surface'])
        for n in made:
            nt.nodes.remove(n)
    return undo


def unhide(o):
    o.hide_viewport = False
    o.hide_select = False
    try:
        o.hide_set(False)
    except RuntimeError:
        pass

    def walk(lc):
        for ch in lc.children:
            if o.name in ch.collection.all_objects:
                ch.hide_viewport = False
                walk(ch)
    walk(bpy.context.view_layer.layer_collection)


report = dict(source=bpy.data.filepath, scale=SCALE, samples=SPP, margin_px=MARGIN, atlases={})
for name, spec in man['atlases'].items():
    res = int(round(spec['resolution'] * SCALE))
    objs = [bpy.data.objects[n] for n in spec['objects']]
    for o in objs:
        unhide(o)
    mats = sorted({s.material for o in objs for s in o.material_slots if s.material}, key=lambda m: m.name)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    imgs = {}
    for kind in ('color', 'coverage'):
        img = bpy.data.images.new(f'V2LOOK_{name}_{kind}', res, res, alpha=True, float_buffer=True)
        img.colorspace_settings.name = 'Linear Rec.709'
        target(mats, img)
        t = time.time()
        if kind == 'color':
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, margin=MARGIN, margin_type='ADJACENT_FACES',
                                use_clear=True, target='IMAGE_TEXTURES', uv_layer=LM_UV)
        else:
            undos = [coverage_rewire(m) for m in mats]
            bpy.ops.object.bake(type='EMIT', margin=MARGIN, margin_type='ADJACENT_FACES',
                                use_clear=True, target='IMAGE_TEXTURES', uv_layer=LM_UV)
            for u in undos:
                u()
        print(f'[albedo] {name} {kind} {res}px {time.time() - t:.1f}s', flush=True)
        imgs[kind] = pixels(img)[::-1]  # top row first, like the lightmap PNGs (glTF convention)
    col = imgs['color'][..., :3]
    cov = np.clip(imgs['coverage'][..., 0], 0, 1)
    decal = bool((cov < 0.995).any() and any(m.name.startswith('rs_scuff') for m in mats))
    if decal:
        un = np.where(cov[..., None] > 1 / 255, col / np.maximum(cov[..., None], 1 / 255), col)
        u8 = np.concatenate([np.round(srgb_encode(un) * 255), np.round(cov * 255)[..., None]], 2).astype(np.uint8)
    else:
        u8 = np.round(srgb_encode(col) * 255).astype(np.uint8)
    path = os.path.join(OUT, f'albedo_{name}.png')
    size = png_write(u8, path)
    np.save(os.path.join(OUT, f'albedo_{name}_linear.npy'), np.concatenate([col, cov[..., None]], 2).astype(np.float16))
    report['atlases'][name] = dict(file=os.path.basename(path), resolution=res, bytes=size, alpha=decal,
                                   encoding='8-bit sRGB albedo' + (' (un-premultiplied), alpha = decal coverage' if decal else ''),
                                   materials=[m.name for m in mats], mean_linear=[round(float(x), 4) for x in col.reshape(-1, 3).mean(0)])
    print('[albedo]', name, report['atlases'][name], flush=True)
json.dump(report, open(os.path.join(OUT, 'albedo.json'), 'w'), indent=1)
print('[albedo] done; nothing saved to', bpy.data.filepath, flush=True)
