"""Report what is actually inside a source asset, before deciding to use it."""
import bpy, sys, os

argv = sys.argv[sys.argv.index('--') + 1:]
path = argv[0]

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(path)[1].lower()
if ext in ('.gltf', '.glb'):
    bpy.ops.import_scene.gltf(filepath=path)
elif ext == '.fbx':
    bpy.ops.import_scene.fbx(filepath=path)
elif ext == '.obj':
    bpy.ops.wm.obj_import(filepath=path)
else:
    raise SystemExit(f'unsupported: {ext}')

total_tris = 0
print('---REPORT---')
for o in bpy.data.objects:
    if o.type != 'MESH':
        print(f'OBJ {o.name} type={o.type}')
        continue
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    total_tris += tris
    dim = o.dimensions
    print(f'MESH {o.name}: verts={len(me.vertices)} tris={tris} '
          f'dims={dim.x:.3f}x{dim.y:.3f}x{dim.z:.3f} mats={[m.name for m in me.materials]}')
print(f'TOTAL_TRIS {total_tris}')
print(f'IMAGES {[(i.name, tuple(i.size)) for i in bpy.data.images if i.name != "Render Result"]}')
