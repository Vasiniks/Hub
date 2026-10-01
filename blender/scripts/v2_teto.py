"""
Owner-downloaded Teto models -> parts, real scale, centred, bottom on z=0, front toward -Y.

  blender -b --factory-startup --python v2_teto.py -- plush|pear [--render]

plush: Sketchfab "Kasane Teto fatass plush" by revsworks, CC BY 4.0      -> parts/teto_plush.blend (NEW_plush_teto)
pear : Sketchfab "Teto Pear" by Luquez18, Sketchfab Free Standard (NOT CC) -> parts/teto_pear.blend  (NEW_teto_pear)
Raw downloads live in assets/source/ (git-ignored). See assets/MANIFEST.md.
"""
import bpy, sys, os, math, mathutils

REPO = r"C:\Users\Vas\Documents\Github\Hub"
SRC = os.path.join(REPO, 'assets', 'source')
a = sys.argv[sys.argv.index('--') + 1:]
which = a[0]
CFG = {
    'plush': dict(path=os.path.join(SRC, 'kasane-teto-fatass-plush', 'source', 'fatass teto2.fbx'),
                  tex=os.path.join(SRC, 'kasane-teto-fatass-plush', 'textures'), size=0.30, col='NEW_plush_teto'),
    'pear': dict(path=os.path.join(SRC, 'teto-pear', 'source', 'Teto Pear final.blend'),
                 tex=os.path.join(SRC, 'teto-pear', 'textures'), size=0.075, col='NEW_teto_pear'),
}[which]

if CFG['path'].endswith('.fbx'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=CFG['path'])
else:
    bpy.ops.wm.open_mainfile(filepath=CFG['path'])
    for o in [o for o in bpy.context.scene.objects if o.type in ('CAMERA', 'LIGHT')]:
        bpy.data.objects.remove(o, do_unlink=True)

# re-point images at the textures folder shipped in the zip, then pack them into the part
texdir = CFG['tex']
avail = {f.lower(): os.path.join(texdir, f) for f in os.listdir(texdir)}
for img in bpy.data.images:
    base = os.path.basename(img.filepath.replace('\\', '/')).lower()
    if base in avail:
        img.filepath = avail[base]
    elif img.filepath and not os.path.exists(bpy.path.abspath(img.filepath)) and len(avail) == 1:
        img.filepath = next(iter(avail.values()))
    try:
        img.reload(); img.pack()
    except RuntimeError as e:
        print('IMG_MISSING', img.name, img.filepath, e)

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in meshes:
    mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
for o in [o for o in bpy.context.scene.objects if o.type == 'EMPTY']:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

pts = [v.co for o in meshes for v in o.data.vertices]
lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)])
hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
s = CFG['size'] / max(hi - lo)
M = mathutils.Matrix.Scale(s, 4) @ mathutils.Matrix.Translation(-mathutils.Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)))
for o in meshes: o.data.transform(M)

col = bpy.data.collections.new(CFG['col']); bpy.context.scene.collection.children.link(col)
root = bpy.data.objects.new(CFG['col'] + '_root', None); col.objects.link(root)
for o in meshes:
    for uc in list(o.users_collection): uc.objects.unlink(o)
    col.objects.link(o); o.parent = root
pts = [v.co for o in meshes for v in o.data.vertices]
print('TETO', which, 'size', [round(max(p[i] for p in pts) - min(p[i] for p in pts), 3) for i in range(3)])
out = os.path.join(REPO, 'blender', 'scene', 'parts', f'teto_{which}.blend')
bpy.ops.wm.save_as_mainfile(filepath=out)

if '--render' in a:
    sc = bpy.context.scene
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.refresh_devices()
    for dv in prefs.devices: dv.use = (dv.type == 'OPTIX')
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'GPU'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 900, 700
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND'); bg.inputs['Strength'].default_value = 0.8
    h = CFG['size']
    for loc, e in (((-1.5, -2, 2), 40), ((2, -1, 1), 15)):
        ld = bpy.data.lights.new('l', 'AREA'); ld.energy = e * (h / 0.3) ** 2; ld.size = 1.5 * h / 0.3
        lo_ = bpy.data.objects.new('l', ld); sc.collection.objects.link(lo_); lo_.location = mathutils.Vector(loc) * h / 0.3
        lo_.rotation_euler = (mathutils.Vector((0, 0, h / 3)) - lo_.location).to_track_quat('-Z', 'Y').to_euler()
    for tag, d in (('front', (0.4, -1.0, 0.45)), ('side', (1.0, 0.1, 0.35))):
        cd = bpy.data.cameras.new('c'); cd.lens = 60
        cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
        cam.location = mathutils.Vector(d) * h * 3.2
        cam.rotation_euler = (mathutils.Vector((0, 0, h * 0.4)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(REPO, 'blender', 'scene', 'parts', f'teto_{which}_{tag}.png')
        bpy.ops.render.render(write_still=True)
