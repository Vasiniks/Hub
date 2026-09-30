"""
Save blender/scene/room_public.blend: room.blend minus anything this PUBLIC repo must not redistribute.

    blender -b blender/scene/room.blend --python blender/scripts/v2_make_public.py

Stripped (see assets/MANIFEST.md for why):
  - NEW_tele_gb   Greg Bennett guitar, Sketchfab Free Standard
  - NEW_teto*     Teto pear, Sketchfab Free Standard   (the plush lives in NEW_plush_teto and stays)
  - NEW_redbull   Red Bull can, source unidentified
  - pc_gpukit_*   GPU from the owner's kit, licence unverified
  - *emblem18*    speedcube logo traced from a retailer photo
"""
import bpy, os

STRIP_COLLECTIONS = ('NEW_tele_gb', 'NEW_teto', 'NEW_redbull')
for cname in [c.name for c in bpy.data.collections if c.name.startswith(STRIP_COLLECTIONS)]:
    col = bpy.data.collections[cname]
    for o in list(col.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(col)
for o in [o for o in bpy.data.objects if 'emblem18' in o.name or o.name.startswith('pc_gpukit_')]:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
out = os.path.join(os.path.dirname(bpy.data.filepath), 'room_public.blend')
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True, compress=True)
print('PUBLIC_OK', [c.name for c in bpy.data.collections if c.name.startswith('NEW_')])
