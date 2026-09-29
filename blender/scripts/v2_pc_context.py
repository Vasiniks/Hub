"""
v2_pc_context.py -- context render of parts/pc.blend inside room.blend (room.blend is opened read-only,
never saved). The storage tote (Node_380 + children) is hidden for the render.

    blender -b blender/scene/room.blend --python blender/scripts/v2_pc_context.py -- [--samples=48]
Writes parts/pc_room_seat.png (seated viewer turned toward the PC) and parts/pc_room_wide.png.
"""
import bpy
import os
import sys
from mathutils import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.abspath(os.path.join(HERE, '..', 'scene', 'parts'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SPP = int(next((a.split('=')[1] for a in ARGS if a.startswith('--samples=')), 48))
SEAT = V((0.0, -0.16, 1.175))

scene = bpy.context.scene
with bpy.data.libraries.load(os.path.join(PARTS, 'pc.blend'), link=False) as (src, dst):
    dst.collections = ['NEW_pc']
scene.collection.children.link(dst.collections[0])
tote = bpy.data.objects['Node_380']
for o in [tote] + list(tote.children_recursive):
    o.hide_render = True
    o.hide_viewport = True
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
cam = bpy.data.objects.new('pc_ctx_cam', bpy.data.cameras.new('pc_ctx_cam'))
scene.collection.objects.link(cam)
scene.camera = cam
bpy.context.view_layer.update()
root = bpy.data.objects['NEW_pc_root']
mid = root.matrix_world @ V((0, 0, 0.24))


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


only = next((a.split('=')[1].split(',') for a in ARGS if a.startswith('--only=')), None)
if not only or 'seat' in only:
    shot(SEAT, mid, 35, 'pc_room_seat.png')
if not only or 'strip' in only:
    shot(V((0.66, 1.115, 0.20)), V((0.30, 1.21, 0.04)), 28, 'pc_room_strip.png')
if not only or 'wide' in only:
    shot(SEAT + V((-0.35, -0.9, 0.25)), mid + V((-0.35, 0.0, 0.1)), 24, 'pc_room_wide.png')
