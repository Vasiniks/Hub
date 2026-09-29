"""
v2 mouse: an off-white Logitech Pebble Mouse 2 (M350s)-proportioned wireless mouse.

Real reference dimensions: 107 x 59 x 26.6 mm. Built at the origin (bottom centre on z=0,
buttons toward +Y), then the root empty is moved to where the old mouse sat in room.blend.

Construction
  * One smooth closed "pebble" solid is generated parametrically: a superellipse footprint,
    a dome whose rays run from the peak (set slightly rearward) out to the rim with a
    vertical tangent, and a short tucked side wall with a filleted underside.
  * The visible parts are cut FROM that one solid with exact booleans, so they share one
    continuous surface but are separate objects with real gaps between them: left button,
    right button, palm cover, base tray. A dark inner core (the same solid offset 0.9 mm
    inward) fills the gaps below the surface so seams read as dark lines, not see-through.
  * The wheel slot, sensor window and power-switch slot are boolean pockets whose walls
    take a dark material; every cut edge gets a small bevel so it catches a highlight.
  * The wheel is a revolved rounded profile with 40 fine ribs around the tread.

Usage:  blender -b --factory-startup --python v2_mouse.py -- [--no-render]
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402

ARGS = lib.argv()
RENDER = '--no-render' not in ARGS
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'mouse.blend')

NAME = 'mouse'
# Old mouse root ("mouse_body" empty) world transform in room.blend.
ROOM_LOC = (0.33, 0.45, 0.735)
ROOM_YAW = -0.14

# ----------------------------------------------------------------------------- dimensions
L, W, H = 0.107, 0.059, 0.0266
FOOT = 0.00045          # PTFE feet thickness; the body's flat bottom sits at z = FOOT
ZR = 0.0085             # rim height: where the dome meets the side wall with a vertical tangent
CY = -0.004             # dome peak sits slightly behind centre
NSE = 2.6              # footprint superellipse exponent
TAPER = 0.035           # nose slightly narrower than the tail
DOME_A, DOME_B = 1.6, 0.62

PART_Z = 0.0047         # parting line between top shell and base tray
PART_G = 0.0004
SEAM_G = 0.00035        # button seams
CORE_INSET = 0.0009

WHEEL_R = 0.0081
WHEEL_W = 0.0056
WHEEL_Y = L / 2 - 0.027
WHEEL_PROUD = 0.0021    # how far the tread stands above the shell
SLOT_HW = 0.0036        # slot half width (x)
SLOT_HL = 0.0040        # slot half length (y) - to the centres of the round ends
POCKET_FLOOR = 0.0038


def seam_y(x):
    """Button/palm seam: bows forward at the centre line."""
    return -0.001 - 5.5 * x * x


# ----------------------------------------------------------------------------- helpers

def link(obj, coll):
    coll.objects.link(obj)
    return obj


def mesh_obj(name, bm, coll):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me), coll)


def outline(t):
    c, s = math.cos(t), math.sin(t)
    x = (W / 2) * math.copysign(abs(c) ** (2 / NSE), c)
    y = (L / 2) * math.copysign(abs(s) ** (2 / NSE), s)
    x *= 1 - TAPER * (y / (L / 2))
    return x, y


def dome(s):
    return ZR + (H - ZR) * max(0.0, 1 - s ** DOME_A) ** DOME_B


def pebble_bm(n_theta, n_top, n_fillet):
    """Closed pebble solid in a bmesh (unscaled footprint; caller normalises)."""
    bm = bmesh.new()
    c = Vector((0.0, CY))
    F = [Vector(outline(2 * math.pi * i / n_theta)) for i in range(n_theta)]
    rings = []
    top_pole = bm.verts.new((c.x, c.y, dome(0.0)))
    for k in range(1, n_top + 1):
        s = 1 - (1 - k / n_top) ** 2
        z = dome(s)
        rings.append([bm.verts.new((*(c + (f - c) * s), z)) for f in F])
    # side wall: short draft, then a quarter-round into the flat underside
    zf = FOOT + 0.0024
    R = 0.0024
    wall = [(0.00012, (ZR + zf) / 2), (0.00025, zf)]
    for j in range(1, n_fillet + 1):
        ph = (math.pi / 2) * j / n_fillet
        wall.append((0.00025 + R * (1 - math.cos(ph)), zf - R * math.sin(ph)))
    for inset, z in wall:
        rings.append([bm.verts.new((*(c + (f - c) * (1 - inset / (f - c).length)), z)) for f in F])
    bot_pole = bm.verts.new((c.x, c.y, FOOT))
    n = n_theta
    for i in range(n):
        bm.faces.new((top_pole, rings[0][i], rings[0][(i + 1) % n]))
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n):
            bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    last = rings[-1]
    for i in range(n):
        bm.faces.new((bot_pole, last[(i + 1) % n], last[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def normalise_xy(bm, sx, sy):
    for v in bm.verts:
        v.co.x *= sx
        v.co.y *= sy


def prism(name, pts, z0, z1, coll, mat=None):
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(bot)
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_obj(name, bm, coll)
    if mat:
        o.data.materials.append(mat)
    return o


def stadium(cx, cy, hw, hl, n=10):
    """Slot outline along Y: straight sides at x = cx +- hw, round ends radius hw."""
    pts = []
    for i in range(n + 1):  # front end
        a = math.pi * i / n
        pts.append((cx + hw * math.cos(a), cy + hl + hw * math.sin(a)))
    for i in range(n + 1):  # rear end
        a = math.pi + math.pi * i / n
        pts.append((cx + hw * math.cos(a), cy - hl + hw * math.sin(a)))
    return pts


def rrect(cx, cy, hw, hl, r, n=5):
    pts = []
    for (qx, qy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ox, oy = cx + qx * (hw - r), cy + qy * (hl - r)
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    return pts


def boolean(obj, cutter, op):
    m = obj.modifiers.new('bool', 'BOOLEAN')
    m.operation = op
    m.object = cutter
    try:
        m.solver = 'EXACT'
    except TypeError:
        pass
    if hasattr(m, 'material_mode'):
        m.material_mode = 'TRANSFER'
    lib.apply_modifiers(obj)


def smooth(obj, angle=50):
    lib.activate(obj)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    except (AttributeError, RuntimeError, TypeError):
        lib.shade_auto(obj, angle)


def bevel(obj, width, segments=2, angle=40):
    m = obj.modifiers.new('bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    m.miter_outer = 'MITER_ARC'
    lib.apply_modifiers(obj)


def bsdf_of(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def make_mat(name, hexcol, rough, spec=0.5, grain=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = bsdf_of(mat)
    b.inputs['Base Color'].default_value = (*lib.hex_rgb(hexcol), 1.0)
    b.inputs['Roughness'].default_value = rough
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = spec
    if coat and 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.05
    if grain > 0:
        # Fine moulded-plastic texture: object-space noise into a very shallow bump, plus a
        # whisper of roughness variation so the matte highlight is not perfectly uniform.
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs['Scale'].default_value = 1400.0
        nz.inputs['Detail'].default_value = 2.0
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = grain
        bump.inputs['Distance'].default_value = 0.00004
        nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = rough - 0.04
        mr.inputs['To Max'].default_value = rough + 0.04
        nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return mat


# ----------------------------------------------------------------------------- build

lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)
tmp = bpy.data.collections.new('tmp_cutters')
scene.collection.children.link(tmp)

M_SHELL = make_mat('mouse_shell_offwhite_matte', '#E3DDD2', 0.46, grain=0.12)
M_BASE = make_mat('mouse_base_offwhite', '#D6D0C5', 0.52, grain=0.10)
M_DARK = make_mat('mouse_interior_dark', '#1A1A1B', 0.75, spec=0.3)
# seam gap walls: the same plastic, but read in shadow - darker than the shell, not black
M_SEAM = make_mat('mouse_seam_wall', '#6B6760', 0.7, spec=0.3)
M_WHEEL = make_mat('mouse_wheel_rubber_grey', '#62605C', 0.72, spec=0.35, grain=0.25)
M_FEET = make_mat('mouse_feet_ptfe', '#CFCCC6', 0.28)
M_SENSOR = make_mat('mouse_sensor_window_gloss', '#101011', 0.55, spec=0.3)
M_LENS = make_mat('mouse_sensor_lens', '#1A1012', 0.15, spec=0.5)
M_SWITCH = make_mat('mouse_switch_grey', '#BDBAB4', 0.5)
M_ON = make_mat('mouse_switch_on_green', '#3BAA4A', 0.45)

# master solid -> normalise footprint to exact L x W
bm = pebble_bm(80, 18, 5)
xs = [v.co.x for v in bm.verts]
ys = [v.co.y for v in bm.verts]
SX, SY = W / (max(xs) - min(xs)), L / (max(ys) - min(ys))
OY = -(max(ys) + min(ys)) / 2
normalise_xy(bm, SX, SY)
for v in bm.verts:
    v.co.y += OY * SY
master = mesh_obj('pebble_master', bm, tmp)

# shell surface height along the centreline, for placing the wheel
bvh = BVHTree.FromObject(master, bpy.context.evaluated_depsgraph_get())
hit = bvh.ray_cast(Vector((0, WHEEL_Y, 0.1)), Vector((0, 0, -1)))
z_surf_wheel = hit[0].z
WHEEL_Z = z_surf_wheel + WHEEL_PROUD - WHEEL_R
print(f'surface at wheel {z_surf_wheel*1000:.2f} mm, wheel centre z {WHEEL_Z*1000:.2f} mm')


def copy_master(name, mat):
    o = master.copy()
    o.data = master.data.copy()
    o.name = name
    o.data.name = name
    coll.objects.link(o)
    o.data.materials.clear()
    o.data.materials.append(mat)
    return o


# region prisms for the top shell
BIG = 0.08
ZT0, ZT1 = PART_Z + PART_G / 2, 0.05
seam_xs = [-0.04 + 0.08 * i / 40 for i in range(41)]
left_pts = ([(x, seam_y(x) + SEAM_G / 2) for x in seam_xs if x <= -SEAM_G / 2] +
            [(-SEAM_G / 2, seam_y(-SEAM_G / 2) + SEAM_G / 2), (-SEAM_G / 2, BIG), (-0.04, BIG)])
right_pts = [(-x, y) for x, y in reversed(left_pts)]
palm_pts = [(x, seam_y(x) - SEAM_G / 2) for x in seam_xs] + [(0.04, -BIG), (-0.04, -BIG)]
palm_pts = list(reversed(palm_pts))

slot_pts = stadium(0.0, WHEEL_Y, SLOT_HW, SLOT_HL)

parts = {}
for pname, pts in (('button_L', left_pts), ('button_R', right_pts), ('palm', palm_pts)):
    o = copy_master(f'NEW_mouse_{pname}', M_SHELL)
    cut = prism(f'cut_{pname}', pts, ZT0, ZT1, tmp, M_SEAM)
    boolean(o, cut, 'INTERSECT')
    if pname.startswith('button'):
        boolean(o, prism('cut_slot', slot_pts, POCKET_FLOOR, ZT1, tmp, M_DARK), 'DIFFERENCE')
    parts[pname] = o

# base tray
base = copy_master('NEW_mouse_base', M_BASE)
boolean(base, prism('cut_base', rrect(0, 0, 0.05, 0.07, 0.01), -0.01, PART_Z - PART_G / 2, tmp, M_SEAM),
        'INTERSECT')
boolean(base, prism('cut_pocket', slot_pts, POCKET_FLOOR, ZT1, tmp, M_DARK), 'DIFFERENCE')
SENSOR_Y = 0.006
boolean(base, prism('cut_sensor', rrect(0, SENSOR_Y, 0.0042, 0.0058, 0.0016), -0.001, FOOT + 0.0007,
                    tmp, M_SENSOR), 'DIFFERENCE')
SWITCH_Y = -0.028
boolean(base, prism('cut_switch', rrect(0, SWITCH_Y, 0.0019, 0.0044, 0.0012), -0.001, FOOT + 0.0009,
                    tmp, M_DARK), 'DIFFERENCE')
parts['base'] = base

for o in parts.values():
    bevel(o, 0.00032, segments=2, angle=38)
    smooth(o, 50)

# dark inner core: coarse copy of the solid, pushed inward along its normals
bm = pebble_bm(48, 10, 3)
normalise_xy(bm, SX, SY)
for v in bm.verts:
    v.co.y += OY * SY
bm.normal_update()
for v in bm.verts:
    v.co -= v.normal * CORE_INSET
core = mesh_obj('NEW_mouse_core', bm, coll)
core.data.materials.append(M_DARK)
boolean(core, prism('cut_core_pocket', slot_pts, POCKET_FLOOR, ZT1, tmp, M_DARK), 'DIFFERENCE')
smooth(core, 40)

# ----------------------------------------------------------------------------- wheel
RIBS = 36
NSEG = RIBS * 4
hw = WHEEL_W / 2
R = WHEEL_R
prof = [(R - 0.0010, -hw), (R - 0.00032, -hw + 0.00012), (R - 0.00008, -hw + 0.0004), (R, -hw + 0.0009),
        (R, hw - 0.0009), (R - 0.00008, hw - 0.0004), (R - 0.00032, hw - 0.00012), (R - 0.0010, hw)]
bm = bmesh.new()
rings = []
for (r, x) in prof:
    ring = []
    tread = r >= R - 0.0001
    for i in range(NSEG):
        a = 2 * math.pi * i / NSEG
        rr = r - (0.00024 if (tread and i % 4 in (2, 3)) else 0.0)
        ring.append(bm.verts.new((x, WHEEL_Y + rr * math.cos(a), WHEEL_Z + rr * math.sin(a))))
    rings.append(ring)
for a_, b_ in zip(rings[:-1], rings[1:]):
    for i in range(NSEG):
        j = (i + 1) % NSEG
        bm.faces.new((a_[i], a_[j], b_[j], b_[i]))
for ring, x in ((rings[0], -hw), (rings[-1], hw)):
    # recessed hub face on each side
    inner = [bm.verts.new((x * 0.8, v.co.y + (WHEEL_Y - v.co.y) * 0.35, v.co.z + (WHEEL_Z - v.co.z) * 0.35))
             for v in ring[::4]]
    ring4 = ring[::4]
    m = len(ring4)
    for i in range(m):
        j = (i + 1) % m
        # connect 4 outer verts to 1 inner span
        seg = ring[4 * i:4 * i + 5] if i < m - 1 else ring[4 * i:] + [ring[0]]
        bm.faces.new(seg + [inner[j], inner[i]])
    bm.faces.new(inner)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
wheel = mesh_obj('NEW_mouse_wheel', bm, coll)
wheel.data.materials.append(M_WHEEL)
smooth(wheel, 28)  # below the rib-wall angle, so every rib keeps a crisp edge

# ----------------------------------------------------------------------------- underside bits
# PTFE feet: two arc strips following the outline, front and rear.
def foot_arc(name, t0, t1, inset, width, n=12):
    c = Vector((0.0, CY * SY + OY * SY))
    outer, inner_ = [], []
    for i in range(n + 1):
        t = math.radians(t0 + (t1 - t0) * i / n)
        f = Vector(outline(t))
        f = Vector((f.x * SX, f.y * SY + OY * SY))
        d = (f - c)
        L_ = d.length
        outer.append(c + d * (1 - inset / L_))
        inner_.append(c + d * (1 - (inset + width) / L_))
    pts = [tuple(p) for p in outer] + [tuple(p) for p in reversed(inner_)]
    o = prism(name, pts, 0.0, FOOT + 0.0002, coll, M_FEET)
    bevel(o, 0.00018, segments=2, angle=30)
    smooth(o, 40)
    return o


foot_f = foot_arc('NEW_mouse_foot_front', 55, 125, 0.0042, 0.0026)
foot_r = foot_arc('NEW_mouse_foot_rear', 235, 305, 0.0042, 0.0026)

# sensor lens sitting in the recessed window
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.0019, depth=0.0005,
                                    location=(0, SENSOR_Y + 0.0012, FOOT + 0.0007 - 0.00025))
lens = bpy.context.object
lens.name = 'NEW_mouse_sensor_lens'
for c_ in list(lens.users_collection):
    c_.objects.unlink(lens)
coll.objects.link(lens)
lens.data.materials.append(M_LENS)
bevel(lens, 0.00012, 1, 30)
smooth(lens, 40)

# power slider in its slot, with a green "on" marker beside it
slider = prism('NEW_mouse_switch', rrect(0, SWITCH_Y + 0.0017, 0.0013, 0.0019, 0.0006),
               FOOT + 0.0001, FOOT + 0.0009, coll, M_SWITCH)
bevel(slider, 0.00015, 2, 30)
smooth(slider, 40)
on_mark = prism('NEW_mouse_switch_on', rrect(0, SWITCH_Y - 0.0021, 0.0012, 0.0012, 0.0005),
                FOOT + 0.00085, FOOT + 0.0009, coll, M_ON)

# ----------------------------------------------------------------------------- tidy
for o in list(tmp.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.data.collections.remove(tmp)

root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.03
coll.objects.link(root)
objs = [o for o in coll.objects if o.type == 'MESH']
for o in objs:
    o.parent = root
    try:
        lib.uv_unwrap(o)
    except Exception as err:  # headless smart-project can fail; UVs are optional here
        print(f'  uv skipped on {o.name}: {err}')

total = 0
for o in sorted(objs, key=lambda o: o.name):
    t = lib.tri_count(o)
    total += t
    lo, hi = lib.world_bounds([o])
    print(f'PART {o.name:28s} {t:6d} tris  x[{lo.x*1000:+.1f},{hi.x*1000:+.1f}] '
          f'y[{lo.y*1000:+.1f},{hi.y*1000:+.1f}] z[{lo.z*1000:+.1f},{hi.z*1000:+.1f}] mm')
lo, hi = lib.world_bounds(objs)
print(f'TOTAL {total} tris; size {(hi.x-lo.x)*1000:.1f} x {(hi.y-lo.y)*1000:.1f} x {(hi.z-lo.z)*1000:.1f} mm')


# ----------------------------------------------------------------------------- previews
def look(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def area(name, loc, target, energy, size, colour=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.size = size
    ld.color = colour
    lo_ = bpy.data.objects.new(name, ld)
    lo_.location = loc
    scene.collection.objects.link(lo_)
    look(lo_, target)
    return lo_


if RENDER:
    rig = []
    world = bpy.data.worlds.new('preview_world')
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.18, 0.18, 0.18, 1)
    bg.inputs[1].default_value = 0.6
    scene.world = world
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = 'preview_ground'
    ground.data.materials.append(make_mat('preview_ground', '#6E6E6E', 0.55))
    rig.append(ground)
    rig.append(area('key', (-0.25, -0.2, 0.35), (0, 0, 0.01), 6.0, 0.3))
    rig.append(area('fill', (0.3, -0.1, 0.15), (0, 0, 0.01), 2.2, 0.3, (0.95, 0.97, 1.0)))
    rig.append(area('rim', (0.05, 0.35, 0.2), (0, 0, 0.01), 5.0, 0.2))
    cam_d = bpy.data.cameras.new('preview_cam')
    cam = bpy.data.objects.new('preview_cam', cam_d)
    scene.collection.objects.link(cam)
    rig.append(cam)
    scene.camera = cam
    cam_d.clip_start = 0.005

    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPTIX'
    except TypeError:
        pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.image_settings.file_format = 'PNG'

    views = {
        'closeup': ((0.075, 0.115, 0.075), (0.0, 0.018, 0.014), 70),
        '34': ((-0.17, -0.2, 0.2), (0.0, 0.002, 0.008), 58),
        'side': ((0.26, 0.0, 0.018), (0.0, 0.0, 0.012), 85),
        'top': ((0.0, 0.0, 0.3), (0.0001, 0.0, 0.0), 48),
    }
    only = [a for a in ARGS if a.startswith('--only=')]
    only = only[0].split('=')[1].split(',') if only else None
    for key, (loc, tgt, lens) in views.items():
        if only and key not in only:
            continue
        cam.location = loc
        look(cam, tgt)
        cam_d.lens = lens
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_{key}.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)

    if not only or 'under' in only:
        # underside: flip the asset over onto its back on the ground
        root.rotation_euler = (0, math.pi, 0)
        root.location = (0, 0, H + 0.0003)
        cam.location = (0.1, 0.12, 0.17)
        look(cam, (0, 0, 0.02))
        cam_d.lens = 62
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_under.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)

    for o in rig:
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
    bpy.data.materials.remove(bpy.data.materials['preview_ground'])
    scene.world = None
    bpy.data.worlds.remove(world)

# ----------------------------------------------------------------------------- place + save
root.location = ROOM_LOC
root.rotation_euler = (0, 0, ROOM_YAW)
bpy.data.orphans_purge(do_recursive=True)
os.makedirs(PARTS, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('SAVED', OUT_BLEND)
