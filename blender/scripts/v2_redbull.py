"""
Owner-downloaded Red Bull can -> part at real size (250 ml slim can, 134.5 mm tall, 53 mm dia), upright, bottom on z=0.

Source: owner download "redbull.zip" (Blender 4.0.2 OBJ + two label/top textures). Licence NOT identified —
Blender-only, git-ignored (assets/source/redbull/, parts/redbull.blend). Red Bull artwork is a trademark.

    blender -b --factory-startup --python v2_redbull.py -- [--render]
Output: blender/scene/parts/redbull.blend, collection NEW_redbull under NEW_redbull_root.
"""
import bpy, sys, os, mathutils

REPO = r"C:\Users\Vas\Documents\Github\Hub"
SRC = os.path.join(REPO, 'assets', 'source', 'redbull')
OUT = os.path.join(REPO, 'blender', 'scene', 'parts', 'redbull.blend')
HEIGHT = 0.1345
a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=os.path.join(SRC, 'source', 'redbull.obj'))
can = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = can; can.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
pts = [v.co for v in can.data.vertices]
lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
ax = max(range(3), key=lambda i: hi[i] - lo[i])            # the long axis is the can's height
if ax != 2:
    can.data.transform(mathutils.Matrix.Rotation(-1.5708 if ax == 1 else 1.5708, 4, 'X' if ax == 1 else 'Y'))
pts = [v.co for v in can.data.vertices]
lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
s = HEIGHT / (hi.z - lo.z)
can.data.transform(mathutils.Matrix.Scale(s, 4) @ mathutils.Matrix.Translation(-mathutils.Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
for p in can.data.polygons: p.use_smooth = True


def img(name):
    i = bpy.data.images.load(os.path.join(SRC, 'textures', name), check_existing=True)
    if max(i.size) > 2048:
        i.scale(2048, 2048)
    i.pack()
    return i


def setup(mat, image=None, metal=1.0, rough=0.28, colour=(0.8, 0.8, 0.82, 1)):
    mat.use_nodes = True
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    for l in list(p.inputs['Base Color'].links): nt.links.remove(l)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    if image:
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = image
        nt.links.new(t.outputs['Color'], p.inputs['Base Color'])
        p.inputs['Coat Weight'].default_value = 0.4       # printed can lacquer
        p.inputs['Coat Roughness'].default_value = 0.12
    else:
        p.inputs['Base Color'].default_value = colour


for slot in can.material_slots:
    m = slot.material
    if not m: continue
    # slots measured by face area/height: Material.002 = printed side wall, Material.004 = lid
    if m.name.startswith('Material.002'):
        setup(m, img('68748120555550-transformed.jpeg'), metal=0.55, rough=0.3)
    elif m.name.startswith(('redbull_tops', 'Material.004')):
        setup(m, img('images-vaknMZAFG-transformed.jpeg'), metal=1.0, rough=0.25)
    else:
        setup(m, None, metal=1.0, rough=0.3)                 # tab / rims: brushed aluminium

col = bpy.data.collections.new('NEW_redbull'); bpy.context.scene.collection.children.link(col)
root = bpy.data.objects.new('NEW_redbull_root', None); col.objects.link(root)
for uc in list(can.users_collection): uc.objects.unlink(can)
col.objects.link(can); can.parent = root; can.name = 'RedBull_can'
tris = sum(len(p.vertices) - 2 for p in can.data.polygons)
pts = [v.co for v in can.data.vertices]
print('REDBULL tris', tris, 'dims mm', [round(1000 * (max(p[i] for p in pts) - min(p[i] for p in pts)), 1) for i in range(3)], [s.material.name for s in can.material_slots])
bpy.ops.wm.save_as_mainfile(filepath=OUT)

if '--render' in a:
    sc = bpy.context.scene
    pr = bpy.context.preferences.addons['cycles'].preferences
    pr.compute_device_type = 'CUDA'; pr.refresh_devices()
    for d in pr.devices: d.use = (d.type == 'CUDA')
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'GPU'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 700, 900
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND').inputs['Strength'].default_value = 1.5
    ld = bpy.data.lights.new('k', 'AREA'); ld.energy = 25; ld.size = 0.3
    lo_ = bpy.data.objects.new('k', ld); sc.collection.objects.link(lo_); lo_.location = (-0.3, -0.4, 0.4)
    lo_.rotation_euler = (mathutils.Vector((0, 0, 0.07)) - lo_.location).to_track_quat('-Z', 'Y').to_euler()
    cd = bpy.data.cameras.new('c'); cd.lens = 60
    cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = (0.12, -0.42, 0.2)
    cam.rotation_euler = (mathutils.Vector((0, 0, 0.065)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(REPO, 'blender', 'scene', 'parts', 'redbull_front.png')
    bpy.ops.render.render(write_still=True)
