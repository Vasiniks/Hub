"""
Context check for v2_lorenz: opens room.blend (never saved), hides the old icosahedron stand
(Node_305 hierarchy), appends NEW_lorenz from parts/lorenz.blend, reports BVH overlaps with
nearby room objects and renders the seated view to parts/lorenz_room.png.

Usage:  blender -b blender/scene/room.blend --python v2_lorenz_context.py -- [--no-render]
"""
import bpy
import os
import sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.abspath(os.path.join(HERE, '..', 'scene', 'parts'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

old = bpy.data.objects['Node_305']
stack = [old]
while stack:
    o = stack.pop()
    o.hide_render = True
    o.hide_viewport = True
    stack.extend(o.children)

with bpy.data.libraries.load(os.path.join(PARTS, 'lorenz.blend')) as (src, dst):
    dst.collections = ['NEW_lorenz']
coll = dst.collections[0]
bpy.context.scene.collection.children.link(coll)
dg = bpy.context.evaluated_depsgraph_get()
mine = [o for o in coll.objects if o.type == 'MESH']


def bb(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector([min(c[i] for c in cs) for i in range(3)]), Vector([max(c[i] for c in cs) for i in range(3)]))


lo = Vector((min(bb(o)[0].x for o in mine), min(bb(o)[0].y for o in mine), min(bb(o)[0].z for o in mine)))
hi = Vector((max(bb(o)[1].x for o in mine), max(bb(o)[1].y for o in mine), max(bb(o)[1].z for o in mine)))
print('LORENZ_BBOX', tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))
my_trees = {o.name: BVHTree.FromObject(o, dg) for o in mine}
for o in bpy.data.objects:
    if o.type != 'MESH' or o in mine or o.hide_render or not o.visible_get():
        continue
    a, b = bb(o)
    if a.x > hi.x or b.x < lo.x or a.y > hi.y or b.y < lo.y or a.z > hi.z or b.z < lo.z:
        continue
    t = BVHTree.FromObject(o, dg)
    for n, mt in my_trees.items():
        if mt.overlap(t):
            print('OVERLAP', n, 'x', o.name)
    print('NEAR_CHECKED', o.name)

if '--no-render' not in ARGS:
    scene = bpy.context.scene
    cam_d = bpy.data.cameras.new('ctx_cam')
    cam = bpy.data.objects.new('ctx_cam', cam_d)
    scene.collection.objects.link(cam)
    cam.location = Vector((0.0, -0.16, 1.175))
    tgt = Vector((-0.8, 0.8, 0.8))
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_d.lens = 35
    scene.camera = cam
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'CUDA'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = os.path.join(PARTS, 'lorenz_room.png')
    bpy.ops.render.render(write_still=True)
    print('WROTE', scene.render.filepath)
