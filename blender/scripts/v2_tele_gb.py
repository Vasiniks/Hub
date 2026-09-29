"""
Prepare the downloaded Greg Bennett Formula FA1 (T-style) model for the room.

Source: Sketchfab "Greg Bennett Formula FA1 Tele" by Arseniy_Go_On (@psevdodav), Sketchfab Free Standard licence
(see assets/MANIFEST.md). Raw download kept in assets/source/tele_greg_bennett/.

    blender -b --factory-startup --python v2_tele_gb.py [-- --render]

Output: blender/scene/parts/tele_gb.blend, collection NEW_tele_gb under NEW_tele_gb_root.
Convention: guitar standing, bottom of the body at z=0, top face toward -Y, centred on x=y=0.
Changes: scaled to 965 mm overall, re-oriented, tuning-peg mesh decimated (370k -> ~20k tris),
body refinished mint (Surf Green) — the source's baked roughness and normal maps are kept.
"""
import bpy, sys, os, math, mathutils

REPO = r"C:\Users\Vas\Documents\Github\Hub"
SRC = os.path.join(REPO, 'assets', 'source', 'tele_greg_bennett', 'source', 'GregBennettFA1bk.glb')
OUT = os.path.join(REPO, 'blender', 'scene', 'parts', 'tele_gb.blend')
LENGTH = 0.965
MINT = (0.36, 0.66, 0.53, 1.0)   # linear; ~#a3d6c2 Surf Green

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']

# bake every import transform into mesh data, then drop the import empties
for o in meshes:
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw
for o in [o for o in bpy.context.scene.objects if o.type != 'MESH']:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# scale to real length (long axis is Z), turn the top face (+X) to -Y, sit on z=0 centred
pts = [v.co for o in meshes for v in o.data.vertices]
zmin, zmax = min(p.z for p in pts), max(p.z for p in pts)
s = LENGTH / (zmax - zmin)
rot = mathutils.Matrix.Rotation(math.radians(-90), 4, 'Z')
M = rot @ mathutils.Matrix.Scale(s, 4)
for o in meshes: o.data.transform(M)
pts = [v.co for o in meshes for v in o.data.vertices]
c = mathutils.Vector(((min(p.x for p in pts) + max(p.x for p in pts)) / 2, (min(p.y for p in pts) + max(p.y for p in pts)) / 2, min(p.z for p in pts)))
for o in meshes: o.data.transform(mathutils.Matrix.Translation(-c))

# optimise: the tuning-peg mesh is ~87% of the triangles
pegs = bpy.data.objects.get('tuning pegs')
if pegs:
    d = pegs.modifiers.new('decimate', 'DECIMATE'); d.ratio = 0.055
    bpy.context.view_layer.objects.active = pegs
    bpy.ops.object.modifier_apply(modifier='decimate')

# refinish the body: its own copy of the atlas material, base colour mint, maps kept
body = bpy.data.objects['Deka_low_Low_material2_0']
src = body.material_slots[0].material
paint = src.copy(); paint.name = 'tele_gb_body_mint'
nt = paint.node_tree
p = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
for l in list(p.inputs['Base Color'].links): nt.links.remove(l)
p.inputs['Base Color'].default_value = MINT
p.inputs['Coat Weight'].default_value = 0.6        # nitro-style clear coat over the paint
p.inputs['Coat Roughness'].default_value = 0.08
body.material_slots[0].material = paint

# collection + root
col = bpy.data.collections.new('NEW_tele_gb'); bpy.context.scene.collection.children.link(col)
root = bpy.data.objects.new('NEW_tele_gb_root', None); col.objects.link(root)
for o in meshes:
    for uc in o.users_collection: uc.objects.unlink(o)
    col.objects.link(o); o.parent = root
    o.name = 'TeleGB_' + o.name.replace('_low_Low_material2_0', '')

tris = sum(sum(len(pg.vertices) - 2 for pg in o.data.polygons) for o in meshes)
pts = [v.co for o in meshes for v in o.data.vertices]
print('TELE_GB tris', tris, 'size', [round(max(q[i] for q in pts) - min(q[i] for q in pts), 3) for i in range(3)])
bpy.ops.wm.save_as_mainfile(filepath=OUT)

if '--render' in sys.argv:
    sc = bpy.context.scene
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.refresh_devices()
    for dv in prefs.devices: dv.use = (dv.type == 'OPTIX')
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'GPU'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 800, 1100
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.6
    for loc, e in (((-1.2, -1.6, 1.4), 300), ((1.4, -0.8, 1.0), 120)):
        ld = bpy.data.lights.new('l', 'AREA'); ld.energy = e; ld.size = 1.0
        lo = bpy.data.objects.new('l', ld); sc.collection.objects.link(lo); lo.location = loc
        lo.rotation_euler = (mathutils.Vector((0, 0, 0.5)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cd = bpy.data.cameras.new('c'); cd.lens = 50
    cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = (0.45, -1.7, 0.75)
    cam.rotation_euler = (mathutils.Vector((0, 0, 0.48)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(REPO, 'blender', 'scene', 'parts', 'tele_gb_front.png')
    bpy.ops.render.render(write_still=True)
