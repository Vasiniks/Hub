"""
The exported prop GLBs seen from the coordinator's close-up cameras (to put next to the Cycles references
from v2_closeup_cycles.py). Imports every GLB of --dir at identity (they are world-placed), applies each
lit material's litScale, grades like the room (AgX, Medium High Contrast, +0.45 EV) and renders EEVEE.
Lit (unlit) surfaces show exactly their baked texture; PBR parts only see a dim grey world here.

    blender -b --factory-startup --python blender/scripts/v2_closeup_glb.py -- [name ...|all]
        [--dir public/assets/v2/props] [--poses C:/Users/Vas/Documents/Github/closeup-poses.json]
        [--out tmp/closeup-glb]
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


DIR = os.path.join(REPO, arg('--dir', os.path.join('public', 'assets', 'v2', 'props')))
POSES = arg('--poses', 'C:/Users/Vas/Documents/Github/closeup-poses.json')
OUT = os.path.join(REPO, arg('--out', os.path.join('tmp', 'closeup-glb')))
os.makedirs(OUT, exist_ok=True)
poses = json.load(open(POSES))['poses']
want = [n for n in ARGS if not n.startswith('--')]
if want and want != ['all']:
    poses = [p for p in poses if p['name'] in want]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
for f in sorted(os.listdir(DIR)):
    if f.endswith('.glb'):
        bpy.ops.import_scene.gltf(filepath=os.path.join(DIR, f))
for m in bpy.data.materials:
    k = m.get('litScale')
    if k is not None and m.node_tree:
        for n in m.node_tree.nodes:
            if n.type in ('EMISSION', 'BACKGROUND'):
                n.inputs['Strength'].default_value = float(k)
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
w = bpy.data.worlds.new('w')
sc.world = w
w.color = (0.05, 0.045, 0.04)
sc.render.image_settings.file_format = 'JPEG'
sc.render.image_settings.quality = 90
cd = bpy.data.cameras.new('cam')
cd.sensor_fit = 'VERTICAL'
cd.clip_start = 0.01
cam = bpy.data.objects.new('cam', cd)
sc.collection.objects.link(cam)
sc.camera = cam
for p in poses:
    sc.render.resolution_x, sc.render.resolution_y = p.get('width', 1280), p.get('height', 800)
    cd.angle_y = math.radians(p.get('vfov_deg', 45))
    eye, tgt = Vector(p['blender_eye']), Vector(p['blender_target'])
    cam.location = eye
    cam.rotation_euler = (tgt - eye).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, p['name'] + '.jpg')
    bpy.ops.render.render(write_still=True)
    print('[closeup-glb]', p['name'], flush=True)
