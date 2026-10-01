"""
Verify an exported prop GLB: import it back, studio-light it, render EEVEE, save PNG + stats.

    blender -b --factory-startup --python blender/scripts/v2_check_web.py -- <short> [short ...]

Reads ./tmp/props_raw/<short>.glb, renders to ./tmp/props_renders/<short>.png,
prints GLB JSON stats (meshes/materials/images) + pixel stats. A missing bake
shows up as a flat mid-grey model (low saturation AND low luminance variance).
"""
import bpy
import json
import math
import os
import struct
import sys
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
RAW = os.path.join(REPO, 'tmp', 'props_raw')
RDIR = os.path.join(REPO, 'tmp', 'props_renders')
os.makedirs(RDIR, exist_ok=True)


def glb_info(path):
    with open(path, 'rb') as f:
        f.read(12)
        clen, _ = struct.unpack('<II', f.read(8))
        js = json.loads(f.read(clen))
    return {k: len(js.get(k, [])) for k in
            ('meshes', 'nodes', 'materials', 'images', 'textures', 'accessors')}


def render_one(short):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 960, 600
    sc.render.film_transparent = True
    sc.display_settings.display_device = 'sRGB'
    try:
        sc.eevee.taa_render_samples = 64
    except AttributeError:
        pass
    path = os.path.join(RAW, short + '.glb')
    bpy.ops.import_scene.gltf(filepath=path, import_shading='NORMALS')
    meshes = [o for o in sc.objects if o.type == 'MESH']
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    allv = np.array([tuple(o.matrix_world @ v.co) for o in meshes for v in o.data.vertices])
    lo, hi = allv.min(0), allv.max(0)
    cen = (lo + hi) / 2
    size = float((hi - lo).max())
    # camera on a 3/4 orbit, fitted
    dist = size * 2.2 + 0.15
    cd = bpy.data.cameras.new('cam')
    cd.lens = 50
    cam = bpy.data.objects.new('cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = Vector(cen) + Vector((dist * 0.8, -dist, dist * 0.55))
    cam.rotation_euler = (Vector(cen) - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    # key + fill + rim
    for nm, off, en in (('key', (1.2, -1.0, 1.6), 900), ('fill', (-1.4, -0.6, 0.8), 250),
                        ('rim', (-0.4, 1.4, 1.2), 400)):
        ld = bpy.data.lights.new(nm, 'AREA')
        ld.energy = en
        ld.size = 0.6
        lo_ = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(lo_)
        lo_.location = Vector(cen) + Vector(off) * (size + 0.5)
        lo_.rotation_euler = (Vector(cen) - Vector(lo_.location)).to_track_quat('-Z', 'Y').to_euler()
    w = bpy.data.worlds.new('w')
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.4
    sc.world = w
    out = os.path.join(RDIR, short + '.png')
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    # pixel stats on the object mask (alpha > 0.5)
    img = bpy.data.images.load(out)
    px = np.array(img.pixels[:]).reshape(-1, 4)
    bpy.data.images.remove(img)
    m = px[:, 3] > 0.5
    frac = float(m.mean())
    r, g, b = px[m][:, 0], px[m][:, 1], px[m][:, 2]
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 1e-4, (mx - mn) / mx, 0)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    info = glb_info(path)
    print(f'[check] {short}: ' + json.dumps(dict(
        info=info, tris=tris, bytes=os.path.getsize(path),
        mask_frac=round(frac, 3), mean_sat=round(float(sat.mean()), 4),
        std_lum=round(float(lum.std()), 4), mean_lum=round(float(lum.mean()), 4))))
    return out


for s in ARGS:
    try:
        render_one(s)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'[check] {s}: FAILED {e}')
