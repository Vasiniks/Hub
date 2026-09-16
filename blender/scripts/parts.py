"""Split an imported mesh into loose parts and report each one's size and place."""
import bpy, sys, os, mathutils

argv = sys.argv[sys.argv.index('--') + 1:]
path = argv[0]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)

obj = next(o for o in bpy.data.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='LOOSE')
bpy.ops.object.mode_set(mode='OBJECT')

parts = [o for o in bpy.data.objects if o.type == 'MESH']
print('---PARTS---', len(parts))
rows = []
for o in parts:
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    lo = mathutils.Vector((1e9,) * 3); hi = mathutils.Vector((-1e9,) * 3)
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        lo = mathutils.Vector(map(min, lo, w)); hi = mathutils.Vector(map(max, hi, w))
    rows.append((tris, o.name, lo, hi, [m.name for m in me.materials]))
rows.sort(reverse=True)
for tris, name, lo, hi, mats in rows[:24]:
    print(f'{tris:7d} tris  z[{lo.z:+.3f},{hi.z:+.3f}] y[{lo.y:+.3f},{hi.y:+.3f}] x[{lo.x:+.3f},{hi.x:+.3f}]  {name}  {mats}')
print('TOTAL', sum(r[0] for r in rows))
