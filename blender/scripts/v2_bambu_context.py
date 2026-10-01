"""
v2_bambu_context.py -- context render + clearance check of parts/bambu.blend inside room.blend
(room.blend is opened read-only, never saved).

    blender -b blender/scene/room.blend --python blender/scripts/v2_bambu_context.py -- [--samples=64] [--only=seat,wide]
Writes parts/bambu_seat.png (seated viewer turned left toward the corner) and parts/bambu_room_wide.png.
"""
import bpy
import os
import sys
from mathutils import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.abspath(os.path.join(HERE, '..', 'scene', 'parts'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SPP = int(next((a.split('=')[1] for a in ARGS if a.startswith('--samples=')), 64))
ONLY = next((a.split('=')[1].split(',') for a in ARGS if a.startswith('--only=')), None)
SEAT = V((0.0, -0.16, 1.175))

scene = bpy.context.scene
old = bpy.data.collections.get('NEW_bambu')
if old is not None:
    for o in [x for x in old.all_objects if x is not None]:
        o.hide_render = True
with bpy.data.libraries.load(os.path.join(PARTS, 'bambu.blend'), link=False) as (src, dst):
    dst.collections = ['NEW_bambu']
new = dst.collections[0]
scene.collection.children.link(new)
bpy.context.view_layer.update()


def wbox(o):
    pts = [o.matrix_world @ V(c) for c in o.bound_box]
    return V([min(p[i] for p in pts) for i in range(3)]), V([max(p[i] for p in pts) for i in range(3)])


def visible(o):
    if o.hide_render:
        return False
    for c in o.users_collection:
        lc = None
        stack = [bpy.context.view_layer.layer_collection]
        while stack:
            l = stack.pop()
            if l.collection == c:
                lc = l
                break
            stack.extend(l.children)
        if c.hide_render or (lc is not None and lc.exclude):
            return False
    return True


mine = [o for o in new.all_objects if o.type == 'MESH']
others = [o for o in scene.objects if o.type in ('MESH', 'CURVE') and o.name not in new.all_objects and visible(o)]
for o in mine:
    lo, hi = wbox(o)
    for p in others:
        if p.name.startswith(('rs_wall', 'rs_floor', 'rs_ceiling', 'rs_crown')):
            continue
        plo, phi = wbox(p)
        if all(lo[i] < phi[i] and hi[i] > plo[i] for i in range(3)):
            print('BBOX_OVERLAP', o.name, 'x', p.name, [c.name for c in p.users_collection])
for nm in ('curtain_left', 'bookrack_board', 'bookrack_bracket_L', 'bookrack_bracket_R', 'rs_register_frame'):
    p = bpy.data.objects.get(nm)
    if p:
        print('REF', nm, [tuple(round(x, 3) for x in v) for v in wbox(p)])
rob = [o for o in scene.objects if any(c.name == 'NEW_robot' for c in o.users_collection) and o.type == 'MESH']
if rob:
    pts = [v for o in rob for v in wbox(o)]
    print('ROBOT', [(round(min(p[i] for p in pts), 3), round(max(p[i] for p in pts), 3)) for i in range(3)])

scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.refresh_devices()
for d in prefs.devices:
    d.use = d.type == 'CUDA'
scene.cycles.device = 'GPU'
scene.cycles.samples = SPP
scene.cycles.use_denoising = True
try:
    scene.cycles.denoiser = 'OPTIX'
except TypeError:
    pass
cam = bpy.data.objects.new('bambu_ctx_cam', bpy.data.cameras.new('bambu_ctx_cam'))
scene.collection.objects.link(cam)
scene.camera = cam


def shot(loc, target, lens, name, res=(1280, 800)):
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(PARTS, name)
    bpy.ops.render.render(write_still=True)
    print('PREVIEW', name)


if not ONLY or 'seat' in ONLY:
    shot(SEAT, V((-1.9, 1.1, 1.0)), 35, 'bambu_seat.png')
if not ONLY or 'wide' in ONLY:
    shot(V((-0.3, -0.9, 1.5)), V((-1.55, 0.9, 0.8)), 24, 'bambu_room_wide.png')
