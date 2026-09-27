"""
Assemble blender/source/computer.blend — the editable deliverable for the
computer-gear remodel (monitor, keyboard, MacBook, mouse, hub, dev board).

Imports the finished GLBs (built by build_monitor/keyboard/macbook/mouse.py and
build_desk_items.py) into named collections, lays them out for presentation,
and leaves the file render-ready: studio world, 3-point area lights, a camera
framing the whole group, render output at //../render/.

Re-runnable from scratch:
    blender --background --factory-startup --python blender/scripts/assemble_computer_blend.py
"""
import bpy
import math
import mathutils
import os

ROOT = os.getcwd()
SRC = os.path.join(ROOT, 'assets', 'processed')
OUT = os.path.join(ROOT, 'blender', 'source', 'computer.blend')

# name, GLB, presentation offset (x, y)
GROUP = [
    ('Monitor', 'monitor.glb', (-0.42, 0.02)),
    ('Keyboard', 'keyboard.glb', (0.10, 0.16)),
    ('MacBook', 'macbook.glb', (0.10, -0.28)),
    ('Mouse', 'mouse.glb', (0.50, 0.08)),
    ('Hub', 'hub.glb', (0.50, -0.10)),
    ('Board', 'board.glb', (0.50, -0.26)),
]

bpy.ops.wm.read_factory_settings(use_empty=True)

for name, glb, (px, py) in GROUP:
    path = os.path.join(SRC, glb)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    for o in new:
        # Move out of the master collection into the group collection.
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        o.location.x += px
        o.location.y += py

# Frame everything.
lo = mathutils.Vector((1e9,) * 3)
hi = mathutils.Vector((-1e9,) * 3)
for o in bpy.data.objects:
    if o.type not in ('MESH', 'CURVE'):
        continue
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        lo = mathutils.Vector(map(min, lo, w))
        hi = mathutils.Vector(map(max, hi, w))
centre = (lo + hi) / 2
radius = max((hi - lo).length / 2, 1e-3)

# Focus empty + camera.
bpy.ops.object.empty_add(location=centre)
focus = bpy.context.object
focus.name = 'ComputerFocus'
cam_data = bpy.data.cameras.new('ComputerCam')
cam = bpy.data.objects.new('ComputerCam', cam_data)
bpy.context.collection.objects.link(cam)
direction = mathutils.Vector((0.85, -1.5, 0.85)).normalized()
cam.location = centre + direction * radius * 3.3
con = cam.constraints.new('TRACK_TO')
con.target = focus
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

# Studio world.
world = bpy.data.worlds.new('Studio')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.62, 0.63, 0.65, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
bpy.context.scene.world = world

# 3-point lighting (area lights, Blender units = watts here at this scale).
def area(name, energy, size, loc):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.size = size
    o = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (mathutils.Vector(loc) - centre).to_track_quat('-Z', 'Y').to_euler()
    return o

area('Key', 260, radius * 2.2, centre + mathutils.Vector((-1.2, -1.4, 2.0)) * radius)
area('Fill', 110, radius * 1.6, centre + mathutils.Vector((1.6, -0.6, 1.1)) * radius)
area('Rim', 170, radius * 1.2, centre + mathutils.Vector((0.4, 1.8, 1.4)) * radius)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1280
scene.render.resolution_y = 800
scene.render.film_transparent = False
scene.render.filepath = '//../render/preview_'

os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print(f'SAVED {OUT}  ({len(bpy.data.objects)} objects)')
