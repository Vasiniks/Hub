"""
Assemble blender/source/props.blend: every prop GLB laid out on a turntable
grid, render-ready (camera + 3-point lights + world, output //render/).

Usage:
    blender --background --factory-startup --python assemble_props_blend.py \
        -- assets/processed blender/source/props.blend

The build_*.py scripts stay the re-runnable builders; this file only gathers
their outputs into the one editable group source the remodel convention asks
for, so the owner can open it and hit render.
"""
import math
import os
import sys

import bpy
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

SRC_DIR, OUT = lib.argv()

ITEMS = ['mug', 'bin', 'tote', 'organizer', 'book', 'cube',
         'cable', 'screwdriver', 'hub', 'board', 'robot']

lib.reset()

# ------------------------------------------------------------------ import
placed = []
for name in ITEMS:
    path = os.path.join(SRC_DIR, f'{name}.glb')
    objs = lib.import_any(path)
    meshes = [o for o in objs if o.type == 'MESH']
    # One group per prop, named after it, so the outliner stays sane.
    empty = bpy.data.objects.new(f'PROP_{name}', None)
    bpy.context.collection.objects.link(empty)
    for o in meshes:
        o.parent = empty
    placed.append((name, empty, meshes))

# ------------------------------------------------------------- turntable
GAP = 0.06
cursor = 0.0
for name, empty, meshes in placed:
    lo, hi = lib.world_bounds(meshes)
    w = hi.x - lo.x
    # Builders recentre to base already; lay out along X at the mesh level so
    # the .blend opens with applied transforms and sane object locations.
    dx = cursor + w / 2 - (lo.x + hi.x) / 2
    for o in meshes:
        lib.apply_transforms(o)
        for v in o.data.vertices:
            v.co.x += dx
        o.data.update()
    lib.activate(meshes[0])
    for o in meshes[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    bpy.data.objects.remove(empty, do_unlink=True)
    cursor += w + GAP

all_meshes = lib.meshes()
lo, hi = lib.world_bounds(all_meshes)
centre = (lo + hi) / 2
radius = max((hi - lo).length / 2, 1e-3)

# ---------------------------------------------------------------- camera
cam_data = bpy.data.cameras.new('PropsCam')
cam_data.lens = 50
cam = bpy.data.objects.new('PropsCam', cam_data)
bpy.context.collection.objects.link(cam)
direction = mathutils.Vector((1.0, -1.2, 0.5)).normalized()
cam.location = centre + direction * radius * 2.15
cam.rotation_euler = (direction * -1).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

# ---------------------------------------------------------------- lights
sun = bpy.data.lights.new('Sun', 'SUN')
sun.energy = 2.2
sun_obj = bpy.data.objects.new('Sun', sun)
sun_obj.rotation_euler = (math.radians(38), 0, math.radians(-32))
bpy.context.collection.objects.link(sun_obj)

key = bpy.data.lights.new('Key', 'AREA')
key.energy = 900 * radius
key.size = radius * 1.6
key_obj = bpy.data.objects.new('Key', key)
key_obj.location = centre + mathutils.Vector((-1.4, -1.6, 2.2)) * radius
key_obj.rotation_euler = (mathutils.Vector((1.4, 1.6, -2.2))).to_track_quat('-Z', 'Y').to_euler()
bpy.context.collection.objects.link(key_obj)

fill = bpy.data.lights.new('Fill', 'AREA')
fill.energy = 280 * radius
fill.size = radius * 2.0
fill.color = (0.82, 0.88, 1.0)
fill_obj = bpy.data.objects.new('Fill', fill)
fill_obj.location = centre + mathutils.Vector((1.8, 0.6, 1.1)) * radius
fill_obj.rotation_euler = (mathutils.Vector((-1.8, -0.6, -1.1))).to_track_quat('-Z', 'Y').to_euler()
bpy.context.collection.objects.link(fill_obj)

world = bpy.data.worlds.new('PropsWorld')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.028, 0.03, 0.034, 1.0)
world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
bpy.context.scene.world = world

# Studio sweep: a light ground plane so dark props read against something.
# Added after framing, so the turntable extent (not the floor) drives the camera.
bpy.ops.mesh.primitive_plane_add(size=radius * 6, location=(centre.x, centre.y, -0.0005))
ground = bpy.context.object
ground.name = 'StudioGround'
gmat = lib.material('studio_ground', lib.hex_rgb('#8a8d92'), roughness=0.9)
lib.set_materials(ground, [gmat])

# ---------------------------------------------------------------- render
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1600
scene.render.resolution_y = 900
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = '//render/preview_'

os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
all_meshes = lib.meshes()
print(f'SAVED {OUT}  {len(all_meshes)} objects  extent {(hi - lo).x:.2f}x{(hi - lo).y:.2f}x{(hi - lo).z:.2f}m')
