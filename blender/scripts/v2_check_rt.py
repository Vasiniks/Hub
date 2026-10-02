"""
Sanity render for the hybrid (v2rt) props: each GLB with its indirect lightmap applied, no other light.

    blender -b --factory-startup --python blender/scripts/v2_check_rt.py -- [--dir public/assets/v2rt/props]
        [--out tmp/rt_renders] <set> [set ...]

Per set, two views side by side: left = the decoded indirect irradiance L alone (grey material), right =
baseColor x L / 1 (what the diffuse term of a lightMap-only three.js material shows; the runtime adds
the live sun and lamp on top). Graded like the room: AgX Medium High Contrast, +0.45 EV.
"""
import bpy
import json
import math
import os
import sys
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


DIR = os.path.join(REPO, arg('--dir', os.path.join('public', 'assets', 'v2rt', 'props')))
OUT = os.path.join(REPO, arg('--out', os.path.join('tmp', 'rt_renders')))
os.makedirs(OUT, exist_ok=True)
man = json.load(open(os.path.join(DIR, 'manifest.json')))
lm_of = {a['name']: a.get('lightmaps') or [] for a in man['assets']}


def lightmap_nodes(nt, lm_img, rng):
    """L = (rgb * a * rng)^2 from the RGBM texture on UV0 -> returns the colour output socket."""
    N, L = nt.nodes, nt.links
    uv = N.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'
    t = N.new('ShaderNodeTexImage')
    t.image = lm_img
    t.interpolation = 'Linear'
    L.new(uv.outputs['UV'], t.inputs['Vector'])
    mul = N.new('ShaderNodeVectorMath')
    mul.operation = 'SCALE'
    L.new(t.outputs['Color'], mul.inputs[0])
    sc_ = N.new('ShaderNodeMath')
    sc_.operation = 'MULTIPLY'
    L.new(t.outputs['Alpha'], sc_.inputs[0])
    sc_.inputs[1].default_value = rng
    L.new(sc_.outputs[0], mul.inputs['Scale'])
    sq = N.new('ShaderNodeVectorMath')
    sq.operation = 'MULTIPLY'
    L.new(mul.outputs[0], sq.inputs[0])
    L.new(mul.outputs[0], sq.inputs[1])
    return sq.outputs[0]


def render(name, albedo):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    sc.view_settings.exposure = 0.45
    sc.render.resolution_x, sc.render.resolution_y = 720, 600
    sc.render.film_transparent = True
    bpy.ops.import_scene.gltf(filepath=os.path.join(DIR, name + '.glb'))
    lms = lm_of[name]
    imgs = {}
    for lm_ in lms:
        im_ = bpy.data.images.load(os.path.join(DIR, lm_['file']))
        im_.colorspace_settings.name = 'Non-Color'
        im_.alpha_mode = 'CHANNEL_PACKED'
        imgs[lm_['file']] = im_
    for m in bpy.data.materials:
        lm = next((x for x in lms if x.get('materials') and m.name in x['materials']), lms[0])
        img = imgs[lm['file']]
        if not m.node_tree:
            continue
        nt = m.node_tree
        bs = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if bs is None or out is None or bs.inputs['Alpha'].default_value < 0.5 or m.name.startswith('mon_screen'):
            continue          # glass and odd materials keep their own look
        lsock = lightmap_nodes(nt, img, lm['rangeSqrt'])
        em = nt.nodes.new('ShaderNodeEmission')
        if albedo and bs.inputs['Base Color'].links:
            mx = nt.nodes.new('ShaderNodeVectorMath')
            mx.operation = 'MULTIPLY'
            nt.links.new(bs.inputs['Base Color'].links[0].from_socket, mx.inputs[0])
            nt.links.new(lsock, mx.inputs[1])
            nt.links.new(mx.outputs[0], em.inputs['Color'])
        elif albedo:
            mx = nt.nodes.new('ShaderNodeVectorMath')
            mx.operation = 'MULTIPLY'
            mx.inputs[0].default_value = bs.inputs['Base Color'].default_value[:3]
            nt.links.new(lsock, mx.inputs[1])
            nt.links.new(mx.outputs[0], em.inputs['Color'])
        else:
            nt.links.new(lsock, em.inputs['Color'])
        nt.links.new(em.outputs[0], out.inputs['Surface'])
    meshes = [o for o in sc.objects if o.type == 'MESH']
    import numpy as np
    allv = np.array([tuple(o.matrix_world @ v.co) for o in meshes for v in o.data.vertices])
    lo, hi = np.percentile(allv, 3, axis=0), np.percentile(allv, 97, axis=0)
    cen, size = (lo + hi) / 2, float((hi - lo).max())
    cd = bpy.data.cameras.new('cam')
    cd.clip_start = 0.005
    cam = bpy.data.objects.new('cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    d = size * 1.5 + 0.08
    cam.location = Vector(cen) + Vector((d * 0.55, -d, d * 0.5))
    cam.rotation_euler = (Vector(cen) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    path = os.path.join(OUT, f'{name}_{"albedo" if albedo else "L"}.png')
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


for n in [a for a in ARGS if not a.startswith('--')]:
    try:
        a = render(n, False)
        b = render(n, True)
        print(f'[check-rt] {n}: {a} {b}', flush=True)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f'[check-rt] {n}: FAILED {e}', flush=True)
