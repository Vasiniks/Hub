"""
Cycles references for the web build's close-up screenshots: render the coordinator's close-up cameras
from the full sunset room.blend, with the same bake-only edits as the prop/lightmap bakes.

    BLENDER_LOCK_OWNER=web-props bash ../blender-locked.sh -b --factory-startup <Hub>/blender/scene/room.blend \
        --python blender/scripts/v2_closeup_cycles.py -- [name ...|all] [--samples 128]
        [--poses C:/Users/Vas/Documents/Github/closeup-poses.json] [--out C:/Users/Vas/Documents/Github/closeup-cycles]

Poses are {name, blender_eye, blender_target, vfov_deg, width, height} (vertical FOV). Output:
<out>/<name>.jpg. Never saves the .blend.
"""
import bpy
import json
import math
import os
import sys
import time
from mathutils import Vector

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default):
    if name in ARGS:
        i = ARGS.index(name)
        v = ARGS[i + 1]
        del ARGS[i:i + 2]
        return v
    return default


SAMPLES = int(arg('--samples', 128))
POSES = arg('--poses', 'C:/Users/Vas/Documents/Github/closeup-poses.json')
OUT = arg('--out', 'C:/Users/Vas/Documents/Github/closeup-cycles')
FIRST = ['lorenz--paper', 'pc--NEW_pc_root', 'speedcube--NEW_speedcube_root', 'mouse_mx--NEW_mouse_mx_root',
         'lamp--NEW_lamp_pivot', 'pc--NEW_plush_teto_root']
os.makedirs(OUT, exist_ok=True)
poses = json.load(open(POSES))['poses']
by = {p['name']: p for p in poses}
want = [n for n in ARGS if not n.startswith('--')]
if not want or want == ['all']:
    want = [n for n in FIRST if n in by] + [p['name'] for p in poses if p['name'] not in FIRST]

sc = bpy.context.scene
# bake-only edits (as v2_bake_sunset.py / v2_export_web.py): no room volume, robot light at its mean
v = bpy.data.objects.get('fx_room_volume')
if v:
    v.hide_render = True
for m in bpy.data.materials:
    nt = m.node_tree
    if nt and nt.animation_data and nt.animation_data.drivers and 'robot' in m.name:
        for fc in list(nt.animation_data.drivers):
            path = fc.data_path
            nt.driver_remove(path)
            nt.path_resolve(path.rsplit('.', 1)[0]).default_value = 3.5
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.refresh_devices()
for d in prefs.devices:
    d.use = (d.type == 'CUDA')
sc.cycles.device = 'GPU'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
except TypeError:
    pass
sc.render.image_settings.file_format = 'JPEG'
sc.render.image_settings.quality = 90
cd = bpy.data.cameras.new('__closeup')
cam = bpy.data.objects.new('__closeup', cd)
sc.collection.objects.link(cam)
sc.camera = cam
cd.sensor_fit = 'VERTICAL'
cd.clip_start = 0.01
print('[closeup] view', sc.view_settings.view_transform, sc.view_settings.look, sc.view_settings.exposure, flush=True)
for n in want:
    p = by[n]
    t0 = time.time()
    sc.render.resolution_x, sc.render.resolution_y = p.get('width', 1280), p.get('height', 800)
    sc.render.resolution_percentage = 100
    cd.angle_y = math.radians(p.get('vfov_deg', 45))
    eye, tgt = Vector(p['blender_eye']), Vector(p['blender_target'])
    cam.location = eye
    cam.rotation_euler = (tgt - eye).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, n + '.jpg')
    bpy.ops.render.render(write_still=True)
    print(f'[closeup] {n} {time.time() - t0:.1f}s -> {sc.render.filepath}', flush=True)
