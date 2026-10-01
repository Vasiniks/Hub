"""
Verify exported prop GLBs: import each back, studio-light it, render EEVEE, save PNG + stats.

    blender -b --factory-startup --python blender/scripts/v2_check_web.py -- \
        [--dir public/assets/v2/props] [--out tmp/props_renders] <name> [name ...]

Renders two views per GLB (front 3/4 from the room side the seat looks from, and a rear 3/4)
side by side into <out>/<name>.png, and prints GLB JSON stats (meshes/materials/images, alpha
modes, extensions) + pixel stats over the object mask. A failed bake shows up as a flat grey
model: low saturation AND low luminance variance.
"""
import bpy
import json
import os
import struct
import sys
import numpy as np
from mathutils import Vector

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


SRC = os.path.join(REPO, arg('--dir', os.path.join('public', 'assets', 'v2', 'props')))
RDIR = os.path.join(REPO, arg('--out', os.path.join('tmp', 'props_renders')))
os.makedirs(RDIR, exist_ok=True)


def glb_json(path):
    with open(path, 'rb') as f:
        f.read(12)
        clen, _ = struct.unpack('<II', f.read(8))
        return json.loads(f.read(clen))


def glb_info(js):
    d = {k: len(js.get(k, [])) for k in ('meshes', 'nodes', 'materials', 'images', 'textures')}
    d['extensions'] = js.get('extensionsUsed', [])
    d['alpha'] = {m.get('name'): m.get('alphaMode', 'OPAQUE') for m in js.get('materials', [])
                  if m.get('alphaMode', 'OPAQUE') != 'OPAQUE'}
    d['emissive'] = [m.get('name') for m in js.get('materials', []) if 'emissiveFactor' in m
                     or 'emissiveTexture' in m]
    d['node_names'] = [n.get('name') for n in js.get('nodes', [])]
    d['image_types'] = sorted({i.get('mimeType', '?') for i in js.get('images', [])})
    return d


def render_view(sc, cen, size, side):
    dist = size * 1.5 + 0.08
    cam = sc.camera
    cam.location = Vector(cen) + Vector((dist * 0.55 * side, -dist * side, dist * 0.5))
    cam.rotation_euler = (Vector(cen) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for ob in sc.objects:
        if ob.type == 'LIGHT':
            base = Vector(ob['off'])
            ob.location = Vector(cen) + Vector((base.x * side, base.y * side, base.z)) * (size + 0.4)
            ob.rotation_euler = (Vector(cen) - ob.location).to_track_quat('-Z', 'Y').to_euler()
    tmp = os.path.join(RDIR, '_tmp.png')
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(tmp)
    px = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    os.remove(tmp)
    return px


def render_one(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    sc.render.resolution_x, sc.render.resolution_y = 720, 600
    sc.render.film_transparent = True
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.eevee.taa_render_samples = 32
    except AttributeError:
        pass
    path = name if name.endswith('.glb') else os.path.join(SRC, name + '.glb')
    short = os.path.basename(path)[:-4]
    bpy.ops.import_scene.gltf(filepath=path)
    # lit (unlit + baked) materials: apply the runtime's litScale; grade like the room (AgX MHC +0.45 EV)
    for m in bpy.data.materials:
        k = m.get('litScale')
        if k is not None and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type in ('EMISSION', 'BACKGROUND'):
                    n.inputs['Strength'].default_value = float(k)
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    sc.view_settings.exposure = 0.45
    meshes = [o for o in sc.objects if o.type == 'MESH']
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    allv = np.array([tuple(o.matrix_world @ v.co) for o in meshes for v in o.data.vertices])
    lo, hi = np.percentile(allv, 3, axis=0), np.percentile(allv, 97, axis=0)  # cables don't set the frame
    cen = (lo + hi) / 2
    size = float((hi - lo).max())
    cd = bpy.data.cameras.new('cam')
    cd.lens = 50
    cd.clip_start = 0.005
    cam = bpy.data.objects.new('cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    for nm, off, en in (('key', (1.2, -1.0, 1.6), 160), ('fill', (-1.4, -0.6, 0.8), 50),
                        ('rim', (-0.4, 1.4, 1.2), 90)):
        ld = bpy.data.lights.new(nm, 'AREA')
        ld.energy = en * (size + 0.4) ** 2
        ld.size = 0.6
        lo_ = bpy.data.objects.new(nm, ld)
        lo_['off'] = off
        sc.collection.objects.link(lo_)
    w = bpy.data.worlds.new('w')
    sc.world = w
    try:
        w.color = (0.35, 0.35, 0.37)
    except AttributeError:
        pass
    a = render_view(sc, cen, size, 1)
    b = render_view(sc, cen, size, -1)
    both = np.concatenate([a, b], axis=1)
    bg = np.array([0.16, 0.16, 0.17], dtype=np.float32)   # composite over grey: white props stay readable
    al = both[..., 3:4]
    both = np.concatenate([both[..., :3] * al + bg * (1 - al), np.maximum(al, 1.0)], axis=-1)
    mask_alpha = al[..., 0]
    out = os.path.join(RDIR, short + '.png')
    img = bpy.data.images.new('both', both.shape[1], both.shape[0], alpha=True)
    img.pixels.foreach_set(both.ravel())
    img.filepath_raw = out
    img.file_format = 'PNG'
    img.save()
    m = mask_alpha.reshape(-1) > 0.5
    px = both.reshape(-1, 4)[m]
    r, g, bb = px[:, 0], px[:, 1], px[:, 2]
    mx, mn = np.maximum(np.maximum(r, g), bb), np.minimum(np.minimum(r, g), bb)
    sat = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * bb
    js = glb_json(path)
    print(f'[check] {short}: ' + json.dumps(dict(
        info=glb_info(js), tris=tris, bytes=os.path.getsize(path),
        mask_frac=round(float(m.mean()), 3), mean_sat=round(float(sat.mean()), 4),
        std_lum=round(float(lum.std()), 4), mean_lum=round(float(lum.mean()), 4))), flush=True)
    return out


for s in ARGS:
    try:
        render_one(s)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f'[check] {s}: FAILED {e}', flush=True)
