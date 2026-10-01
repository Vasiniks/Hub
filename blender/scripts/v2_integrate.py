"""
Bring a finished part (blender/scene/parts/<name>.blend, collection NEW_<name>) into the open room scene
and retire what it replaces. Old objects are kept, only hidden, in collection OLD_replaced.

Inside Blender:
    NAME = 'mouse'; REPLACES = ['mouse_body', ...]   # REPLACES: object names (descendants included)
    exec(open(r"<repo>/blender/scripts/v2_integrate.py").read())
"""
import bpy, os

REPO = r"C:\Users\Vas\Documents\Github\Hub"
path = os.path.join(REPO, 'blender', 'scene', 'parts', f'{NAME}.blend')
cname = f'NEW_{NAME}'

old = bpy.data.collections.get(cname)
if old:  # re-integration: drop the previous copy
    for o in list(old.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(old)

with bpy.data.libraries.load(path, link=False) as (src, dst):
    dst.collections = [cname]
col = dst.collections[0]
bpy.context.scene.collection.children.link(col)

retired = bpy.data.collections.get('OLD_replaced')
if not retired:
    retired = bpy.data.collections.new('OLD_replaced')
    bpy.context.scene.collection.children.link(retired)
n = 0
for name in REPLACES:
    o = bpy.data.objects.get(name)
    if not o:
        print('missing', name); continue
    for x in [o] + list(o.children_recursive):
        x.hide_render = True; x.hide_set(True)
        if retired not in x.users_collection:
            retired.objects.link(x)
        n += 1
print(f'{cname}: {len(col.all_objects)} objects in, {n} retired')
