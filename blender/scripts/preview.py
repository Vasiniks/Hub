"""Render a neutral three-quarter preview of an asset, for judging shape before integrating."""
import bpy, sys, os, math, mathutils

argv = sys.argv[sys.argv.index('--') + 1:]
path, out = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(path)[1].lower()
if ext in ('.gltf', '.glb'):
    bpy.ops.import_scene.gltf(filepath=path)
elif ext == '.fbx':
    bpy.ops.import_scene.fbx(filepath=path)

meshes = [o for o in bpy.data.objects if o.type == 'MESH']
if not meshes:
    raise SystemExit('no meshes')

# Bounds over everything, so the camera frames the whole asset.
lo = mathutils.Vector((1e9,) * 3)
hi = mathutils.Vector((-1e9,) * 3)
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        lo = mathutils.Vector(map(min, lo, w))
        hi = mathutils.Vector(map(max, hi, w))
centre = (lo + hi) / 2
radius = max((hi - lo).length / 2, 1e-3)

cam_data = bpy.data.cameras.new('cam')
cam = bpy.data.objects.new('cam', cam_data)
bpy.context.collection.objects.link(cam)
import os as _os
dv = [float(x) for x in _os.environ.get('PREVIEW_DIR', '1.0,-1.4,0.75').split(',')]
direction = mathutils.Vector(dv).normalized()
cam.location = centre + direction * radius * 3.1
cam.rotation_euler = (direction * -1).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

world = bpy.data.worlds.new('w')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.45, 0.47, 0.5, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 1.4
bpy.context.scene.world = world

key = bpy.data.lights.new('key', 'AREA')
key.energy = 220
key.size = radius * 2.5
ko = bpy.data.objects.new('key', key)
ko.location = centre + mathutils.Vector((-1.2, -1.4, 2.0)) * radius
ko.rotation_euler = (mathutils.Vector((1.2, 1.4, -2.0))).to_track_quat('-Z', 'Y').to_euler()
bpy.context.collection.objects.link(ko)

s = bpy.context.scene
s.render.engine = 'BLENDER_EEVEE'
s.render.resolution_x = 900
s.render.resolution_y = 700
s.render.film_transparent = False
s.render.filepath = out
bpy.ops.render.render(write_still=True)
print('WROTE', out)
