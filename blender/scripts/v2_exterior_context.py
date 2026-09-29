"""
v2_exterior_context.py -- verify parts/exterior.blend from INSIDE the room (room.blend opened read-only, never saved).
Retires the old exterior placeholders (Mesh_184..Mesh_187) for the render.

    blender -b blender/scene/room.blend --python blender/scripts/v2_exterior_context.py -- [--samples=64] [--only=seat,wide,out]
Writes parts/exterior_room_seat.png, exterior_room_wide.png, exterior_out.png (camera just outside the window).
"""
import bpy
import os
import sys
import time
from mathutils import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.abspath(os.path.join(HERE, '..', 'scene', 'parts'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SPP = int(next((a.split('=')[1] for a in ARGS if a.startswith('--samples=')), 64))
only = next((a.split('=')[1].split(',') for a in ARGS if a.startswith('--only=')), None)
RETIRE = ['Mesh_184', 'Mesh_185', 'Mesh_186', 'Mesh_187']

scene = bpy.context.scene
for n in RETIRE:
    o = bpy.data.objects.get(n)
    if o:
        o.hide_render = True
        o.hide_viewport = True
with bpy.data.libraries.load(os.path.join(PARTS, 'exterior.blend'), link=False) as (src, dst):
    dst.collections = ['NEW_exterior']
scene.collection.children.link(dst.collections[0])

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
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.resolution_percentage = 100


def shot(cam, name):
    scene.camera = cam
    scene.render.filepath = os.path.join(PARTS, name)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print('PREVIEW', name, '%.1fs' % (time.time() - t))


if not only or 'seat' in only:
    shot(bpy.data.objects['CAM_seat'], 'exterior_room_seat.png')
if not only or 'wide' in only:
    shot(bpy.data.objects['CAM_wide'], 'exterior_room_wide.png')
if not only or 'out' in only:
    cam = bpy.data.objects.new('ext_out_cam', bpy.data.cameras.new('ext_out_cam'))
    scene.collection.objects.link(cam)
    cam.location = V((-0.15, 1.75, 1.6))
    cam.data.lens = 20
    cam.rotation_euler = (V((0, 30, -1.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    shot(cam, 'exterior_out.png')
if only and 'down' in only:
    cam = bpy.data.objects.new('ext_down_cam', bpy.data.cameras.new('ext_down_cam'))
    scene.collection.objects.link(cam)
    cam.location = V((-0.15, 1.75, 1.8))
    cam.data.lens = 22
    cam.rotation_euler = (V((0, 14, -3.0)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    shot(cam, 'exterior_down.png')
if only and 'trim' in only:
    cam = bpy.data.objects.new('ext_trim_cam', bpy.data.cameras.new('ext_trim_cam'))
    scene.collection.objects.link(cam)
    cam.location = V((2.8, 5.0, 1.0))
    cam.data.lens = 30
    cam.rotation_euler = (V((-0.2, 1.54, 1.3)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    shot(cam, 'exterior_trim.png')
