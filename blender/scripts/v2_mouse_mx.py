"""
Owner-downloaded mouse scan -> part at real size, buttons toward +Y, bottom on z=0, centred.

Source: Sketchfab "Mouse Logitech MX Master 3S white" by Guibazilla, CC BY 4.0 (see assets/MANIFEST.md).
Raw GLB kept in assets/source/mouse_mx_master_3s/ (git-ignored).

    blender -b --factory-startup --python v2_mouse_mx.py -- [--yaw DEG] [--render]

Output: blender/scene/parts/mouse_mx.blend, collection NEW_mouse_mx under NEW_mouse_mx_root.
Real MX Master 3S: 124.9 (L) x 84.3 (W) x 51 (H) mm.
"""
import bpy, sys, os, math, mathutils

REPO = r"C:\Users\Vas\Documents\Github\Hub"
SRC = os.path.join(REPO, 'assets', 'source', 'mouse_mx_master_3s', 'mouse_logitech_mx_master_3s_white.glb')
OUT = os.path.join(REPO, 'blender', 'scene', 'parts', 'mouse_mx.blend')
LENGTH = 0.1249
MAX_TRIS = 60000
a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
yaw = float(a[a.index('--yaw') + 1]) if '--yaw' in a else 0.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in meshes:
    mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
for o in [o for o in bpy.context.scene.objects if o.type != 'MESH']:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

def bounds():
    pts = [v.co for o in meshes for v in o.data.vertices]
    return (mathutils.Vector([min(p[i] for p in pts) for i in range(3)]),
            mathutils.Vector([max(p[i] for p in pts) for i in range(3)]))

lo, hi = bounds()
print('RAW dims', [round(x, 4) for x in (hi - lo)])

# The scan sits tilted (~38 deg). Align it to its principal axes: least variance = height (Z),
# most = length (Y). Then fix the signs: the flat base is down, the taller palm hump is the rear,
# so the buttons point +Y. X follows from a proper (non-mirroring) rotation.
import numpy as np
P = np.array([tuple(v.co) for o in meshes for v in o.data.vertices])
c = P.mean(0)
w, V = np.linalg.eigh(np.cov((P - c).T))
up, length = V[:, 0], V[:, 2]
h = (P - c) @ up
if (h > h.max() - 0.003 * (h.max() - h.min()) * 10).sum() > (h < h.min() + 0.003 * (h.max() - h.min()) * 10).sum():
    up = -up; h = -h                                        # more points hug the max -> that side is the flat base
l = (P - c) @ length
if h[l > 0].max() > h[l < 0].max():
    length = -length                                       # +length half is taller -> it's the rear; flip so +Y is the front
side = np.cross(length, up)
B = mathutils.Matrix((side, length, up))                   # rows: new X, Y, Z expressed in old coords
M = B.to_4x4() @ mathutils.Matrix.Translation(-mathutils.Vector(c))
for o in meshes: o.data.transform(M)
lo, hi = bounds()
s = LENGTH / (hi.y - lo.y)
M = mathutils.Matrix.Rotation(math.radians(yaw), 4, 'Z') @ mathutils.Matrix.Scale(s, 4)
for o in meshes: o.data.transform(M)
lo, hi = bounds()
for o in meshes: o.data.transform(mathutils.Matrix.Translation(-mathutils.Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))

tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
if tris > MAX_TRIS:
    for o in meshes:
        d = o.modifiers.new('decimate', 'DECIMATE'); d.ratio = MAX_TRIS / tris
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier='decimate')
tris2 = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
for o in meshes:
    for p in o.data.polygons: p.use_smooth = True

col = bpy.data.collections.new('NEW_mouse_mx'); bpy.context.scene.collection.children.link(col)
root = bpy.data.objects.new('NEW_mouse_mx_root', None); col.objects.link(root)
for o in meshes:
    for uc in list(o.users_collection): uc.objects.unlink(o)
    col.objects.link(o); o.parent = root; o.name = 'MouseMX_' + o.name
for img in bpy.data.images:
    if img.packed_file is None and img.source == 'FILE':
        try: img.pack()
        except RuntimeError: pass
lo, hi = bounds()
print('MOUSE_MX tris', tris, '->', tris2, 'dims mm', [round(1000 * x, 1) for x in (hi - lo)])
bpy.ops.wm.save_as_mainfile(filepath=OUT)

if '--render' in a:
    sc = bpy.context.scene
    p = bpy.context.preferences.addons['cycles'].preferences
    p.compute_device_type = 'CUDA'; p.refresh_devices()
    for d in p.devices: d.use = (d.type == 'CUDA')
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'GPU'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 900, 700
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND').inputs['Strength'].default_value = 3.0
    for tag, loc in (('top', (0, 0, 0.5)), ('front34', (0.2, 0.3, 0.2)), ('left', (-0.35, 0.0, 0.08))):
        cd = bpy.data.cameras.new('c'); cd.lens = 70
        cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
        cam.location = loc
        cam.rotation_euler = (mathutils.Vector((0, 0, 0.02)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(REPO, 'blender', 'scene', 'parts', f'mouse_mx_{tag}.png')
        bpy.ops.render.render(write_still=True)
