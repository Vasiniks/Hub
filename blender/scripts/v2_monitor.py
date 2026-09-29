"""
v2 monitor: a generic 27"-class 16:9 desktop monitor (no brand), rebuilt to replace the old one.

Brief (owner): slightly larger than the old panel, not too tall, squished hexagonal base.
  * head 640 x 371 mm, 12 mm thin slab (7 mm bezels top/sides, 12 mm chin), active area
    626 x 352 mm (16:9, 28.3" diagonal), anti-glare glass recessed 0.4 mm behind the bezel lip,
    parting-line groove round the slab edge, power LED on the chin, joystick under the chin
  * rear housing: a 32 mm deep bulge with a 26 deg chamfer band (vent slots on its top run)
    and a flat back plate carrying the stand's carriage, a rear-facing I/O pocket (2x HDMI,
    DP, USB-C, 2x USB-A, 3.5 mm) right of the stand and a C8 (figure-8) mains inlet pocket left
  * stand: 64 x 34 mm aluminium column with a slide channel up its front (the carriage rides
    in it = height adjustment) and a cable-routing hole, on a flat 9 mm squished-hexagon plate
    (310 x 205 mm, soft corners, 1.2 mm top chamfer, six rubber pads)
  * head tilted 2 deg back about the hinge
Assumed (no specific product copied): all dimensions above, port set, materials.

Built in root-local coordinates (x right, y back = away from the viewer, z up, origin on the
desk under the column's front), then the root empty is put at the old monitor's spot.
Hierarchy: NEW_monitor_root -> NEW_monitor_lift (z = height adjust) -> NEW_monitor_head
(pivot = tilt hinge) -> head parts; stand parts hang off the root.

Usage:  blender -b --factory-startup --python v2_monitor.py -- [--no-render] [--only=seat,rear]
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
ROOM_BLEND = os.path.join(REPO, 'blender', 'scene', 'room.blend')
OUT_BLEND = os.path.join(PARTS, 'monitor.blend')
NAME = 'monitor'
MM = 0.001

# old monitor empty "Scene.002" sat at (-0.05, 1.0, 0.735); its screen face was at y~0.950 and
# its body top at z 1.2872. The new one is 15 mm further back so the base's front edge keeps
# 32 mm clear of the MacBook riser (rear edge y 0.8675) while the column stays well in front
# of the desk's back edge (y 1.130).
ROOM_LOC = Vector((-0.05, 1.015, 0.735))
ROOM_YAW = 0.0

# ----------------------------------------------------------------------------- head
W2 = 0.320                     # half width
ZT = 0.565                     # head top (local) -> world ~1.300
H = 0.371
ZB = ZT - H                    # 0.194
ZC = (ZT + ZB) / 2
H2 = H / 2
FY = -0.050                    # front face of the bezel
SB = -0.038                    # back of the thin slab
RC = 5.0 * MM                  # outer corner radius
LIP = 1.2 * MM                 # plastic lip round the glass (sides/top)
CHIN = 9.0 * MM                # plastic chin under the glass
ACT_W, ACT_H = 0.626, 0.352
ACT_Z0 = ZB + 12.0 * MM        # active area bottom
GLASS_Y = FY + 0.4 * MM
# rear housing
ZH = 0.360
HX0, HZ0 = 0.300, 0.150        # housing half size where it meets the slab
HOUSING_PROFILE = [(-0.0385, 0.0), (-0.0365, 0.0), (-0.0350, 0.0015),
                   (-0.0085, 0.0560), (-0.0070, 0.0605), (-0.0062, 0.0650), (-0.0060, 0.0690)]
PLATE_Y = -0.0060
CH0, CH1 = HOUSING_PROFILE[2], HOUSING_PROFILE[3]      # the planar chamfer band
# tilt hinge
PIVOT = Vector((0.0, 0.004, 0.370))
TILT = math.radians(-2.0)      # negative about X = top goes back
# ----------------------------------------------------------------------------- stand
BASE_T = 9.0 * MM
FOOT = 1.2 * MM
BASE_TOP = FOOT + BASE_T       # 0.0102
HEX_A, HEX_B, HEX_D = 0.155, 0.088, 0.1025       # pointy half width, flat half length, half depth
HEX_YC = -0.0125
HEX_R = [0.022, 0.030, 0.030, 0.022, 0.030, 0.030]
COL_HX, COL_HY, COL_R = 0.032, 0.017, 0.010
COL_YC = 0.031                 # column front face y 0.014
COL_TOP = 0.445
CH_HX = 17.0 * MM              # slide channel half width / depth
CH_D = 2.0 * MM


# ----------------------------------------------------------------------------- helpers
def link(obj, coll):
    coll.objects.link(obj)
    return obj


def mesh_obj(name, bm, coll, mats=()):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    return link(bpy.data.objects.new(name, me), coll)


def rr_ring(hx, hy, r, nc=6, nsx=2, nsy=2):
    """Rounded rectangle outline, CCW, fixed point layout so rings can be bridged."""
    r = max(min(r, hx * 0.999, hy * 0.999), 1e-5)
    cs = [((hx - r, hy - r), 0), ((-hx + r, hy - r), 90), ((-hx + r, -hy + r), 180),
          ((hx - r, -hy + r), 270)]
    pts = []
    for ci, ((cx, cy), a0) in enumerate(cs):
        for k in range(nc + 1):
            a = math.radians(a0 + 90 * k / nc)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        p0 = pts[-1]
        (nx, ny), a1 = cs[(ci + 1) % 4]
        a1 = math.radians(a1)
        q = (nx + r * math.cos(a1), ny + r * math.sin(a1))
        ns = nsy if ci in (0, 2) else nsx
        for k in range(1, ns + 1):
            t = k / (ns + 1)
            pts.append((p0[0] + (q[0] - p0[0]) * t, p0[1] + (q[1] - p0[1]) * t))
    return pts


def rounded_poly(V, R, d, nc=8, ne=3):
    """Convex CCW polygon V with corner radii R, offset inward by d (same layout for any d)."""
    n = len(V)
    lines = []
    for i in range(n):
        p, q = Vector(V[i]), Vector(V[(i + 1) % n])
        e = (q - p).normalized()
        lines.append((p + Vector((-e.y, e.x)) * d, e))

    def isect(l1, l2):
        (p1, e1), (p2, e2) = l1, l2
        den = e1.x * e2.y - e1.y * e2.x
        t = ((p2.x - p1.x) * e2.y - (p2.y - p1.y) * e2.x) / den
        return p1 + e1 * t
    arcs = []
    for i in range(n):
        Wv = isect(lines[i - 1], lines[i])
        r = max(R[i] - d, 1e-5)
        ein, eout = lines[i - 1][1], lines[i][1]
        phi = math.acos(max(-1.0, min(1.0, -ein.dot(eout))))
        t = r / math.tan(phi / 2)
        tin = Wv - ein * t
        tout = Wv + eout * t
        c = tin + Vector((-ein.y, ein.x)) * r
        a0 = math.atan2(tin.y - c.y, tin.x - c.x)
        a1 = math.atan2(tout.y - c.y, tout.x - c.x)
        delta = (a1 - a0) % (2 * math.pi)
        arcs.append([c + r * Vector((math.cos(a0 + delta * k / nc), math.sin(a0 + delta * k / nc)))
                     for k in range(nc + 1)])
    pts = []
    for i in range(n):
        pts += arcs[i]
        a, b = arcs[i][-1], arcs[(i + 1) % n][0]
        for k in range(1, ne + 1):
            pts.append(a + (b - a) * (k / (ne + 1)))
    return [(p.x, p.y) for p in pts]


def stadium(hw, hh, n=8):
    pts = []
    for k in range(n + 1):
        t = -math.pi / 2 + math.pi * k / n
        pts.append((hw - hh + hh * math.cos(t), hh * math.sin(t)))
    for k in range(n + 1):
        t = math.pi / 2 + math.pi * k / n
        pts.append((-hw + hh + hh * math.cos(t), hh * math.sin(t)))
    return pts


def circle(r, n=16):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def figure8(r, c, n=10):
    """IEC C8 inlet outline: two overlapping circles (radius r, centres +-c), CCW."""
    zc = math.sqrt(max(r * r - c * c, 1e-8))
    th = math.atan2(zc, -c)                  # angle of the waist point seen from the right centre
    pts = []
    for k in range(2 * n + 1):
        a = -th + 2 * th * k / (2 * n)
        pts.append((c + r * math.cos(a), r * math.sin(a)))
    for k in range(2 * n + 1):
        a = (math.pi - th) + 2 * th * k / (2 * n)
        pts.append((-c + r * math.cos(a), r * math.sin(a)))
    # drop the duplicated waist points
    out = []
    for p in pts:
        if not out or (abs(p[0] - out[-1][0]) > 1e-7 or abs(p[1] - out[-1][1]) > 1e-7):
            out.append(p)
    if abs(out[0][0] - out[-1][0]) < 1e-7 and abs(out[0][1] - out[-1][1]) < 1e-7:
        out.pop()
    return out


def chamfer_rect(hw, hh, cuts):
    """Rect with chamfered corners; cuts = (tr, tl, bl, br) sizes. Always 8 points, CCW."""
    tr, tl, bl, br = [max(c, 0.03 * MM) for c in cuts]
    return [(hw, hh - tr), (hw - tr, hh), (-hw + tl, hh), (-hw, hh - tl),
            (-hw, -hh + bl), (-hw + bl, -hh), (hw - br, -hh), (hw, -hh + br)]


def ring_xz(bm, pts, y, xc=0.0, zc=0.0):
    return [bm.verts.new((xc + a, y, zc + b)) for a, b in pts]


def ring_xy(bm, pts, z, xc=0.0, yc=0.0):
    return [bm.verts.new((xc + a, yc + b, z)) for a, b in pts]


def bridge(bm, ra, rb, mat=0):
    n = len(ra)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
        f.material_index = mat


def cap(bm, ring, mat=0, flip=False):
    f = bm.faces.new(ring[::-1] if flip else ring)
    f.material_index = mat
    return f


def loft(bm, rings, mat=0, cap_ends=True, cap_mat=None):
    for a, b in zip(rings, rings[1:]):
        bridge(bm, a, b, mat)
    if cap_ends:
        cm = mat if cap_mat is None else cap_mat
        cap(bm, rings[0], cm)
        cap(bm, rings[-1], cm)


def prism_y(bm, pts, y0, y1, xc=0.0, zc=0.0, mat=0, cap_mat=None):
    loft(bm, [ring_xz(bm, pts, y0, xc, zc), ring_xz(bm, pts, y1, xc, zc)], mat, True, cap_mat)


def prism_z(bm, pts, z0, z1, xc=0.0, yc=0.0, mat=0, cap_mat=None):
    loft(bm, [ring_xy(bm, pts, z0, xc, yc), ring_xy(bm, pts, z1, xc, yc)], mat, True, cap_mat)


def closed(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def face_dir(bm, want):
    """Orient an open sheet so its mean normal points along `want`."""
    bm.normal_update()
    s = Vector()
    for f in bm.faces:
        s += f.normal * f.calc_area()
    if s.dot(want) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)


def boolean(obj, cutter, op='DIFFERENCE'):
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


def bevel(obj, width, segments=2, angle=35):
    m = obj.modifiers.new('bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    lib.apply_modifiers(obj)


def smooth(obj, angle=35):
    lib.activate(obj)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    except (AttributeError, RuntimeError, TypeError):
        lib.shade_auto(obj, angle)


def bsdf_of(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def make_mat(name, hexcol, rough, spec=0.5, grain=0.0, metal=0.0, grain_scale=1400.0, rough_var=0.05,
             coat=0.0, emit=None, emit_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = bsdf_of(mat)
    b.inputs['Base Color'].default_value = (*lib.hex_rgb(hexcol), 1.0)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = spec
    if coat and 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.08
    if emit is not None:
        b.inputs['Emission Color'].default_value = (*lib.hex_rgb(emit), 1.0)
        b.inputs['Emission Strength'].default_value = emit_strength
    if grain > 0:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs['Scale'].default_value = grain_scale
        nz.inputs['Detail'].default_value = 3.0
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = grain
        bump.inputs['Distance'].default_value = 0.00004
        nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
        # low-frequency roughness drift (handling marks / coating variation)
        nz2 = nt.nodes.new('ShaderNodeTexNoise')
        nz2.inputs['Scale'].default_value = 18.0
        nz2.inputs['Detail'].default_value = 4.0
        nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = max(0.0, rough - rough_var)
        mr.inputs['To Max'].default_value = min(1.0, rough + rough_var)
        nt.links.new(nz2.outputs['Fac'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return mat


# ----------------------------------------------------------------------------- scene
lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)
tmp = bpy.data.collections.new('tmp_cutters')
scene.collection.children.link(tmp)

M_BEZEL = make_mat('mon_bezel_black_matte', '#18181A', 0.48, spec=0.45, grain=0.10, grain_scale=2600)
M_REAR = make_mat('mon_rear_black_textured', '#1B1B1D', 0.62, spec=0.4, grain=0.35, grain_scale=3800)
M_DARK = make_mat('mon_recess_dark', '#070708', 0.85, spec=0.3)
M_GLASS = make_mat('mon_glass_border_black', '#020203', 0.2, spec=0.5, grain=0.02, grain_scale=9000,
                   rough_var=0.03)
M_SCREEN = make_mat('mon_screen_antiglare', '#07080A', 0.2, spec=0.5, grain=0.02, grain_scale=9000,
                    rough_var=0.035)
M_ALU = make_mat('mon_alu_spacegrey', '#5E6166', 0.33, metal=1.0, grain=0.05, grain_scale=1600,
                 rough_var=0.06)
M_CHAN = make_mat('mon_alu_channel_dark', '#2A2B2E', 0.45, metal=1.0)
M_NICKEL = make_mat('mon_port_nickel', '#C6C6CA', 0.3, metal=1.0)
M_PORTBLK = make_mat('mon_port_black', '#141416', 0.5)
M_TONGUE = make_mat('mon_port_tongue', '#0D0D0F', 0.55)
M_RUBBER = make_mat('mon_feet_rubber', '#1E1E1F', 0.9, spec=0.3)
M_LED = make_mat('mon_power_led', '#E8ECFF', 0.3, emit='#EEF2FF', emit_strength=3.0)

head_parts, lift_parts, stand_parts = [], [], []

# ---------------------------------------------------------------- slab (bezel + thin panel body)
NC, NS = 6, 2
op_hx = W2 - LIP
op_z0, op_z1 = ZB + CHIN, ZT - LIP
op_hz, op_zc = (op_z1 - op_z0) / 2, (op_z1 + op_z0) / 2
op_r = RC - LIP


def outer(d):
    return rr_ring(W2 - d, H2 - d, RC - d, NC, NS, NS)


opening = rr_ring(op_hx, op_hz, op_r, NC, NS, NS)
opening_in = rr_ring(op_hx - 0.3 * MM, op_hz - 0.3 * MM, op_r - 0.3 * MM, NC, NS, NS)
bm = bmesh.new()
rings = [ring_xz(bm, opening_in, FY + 0.9 * MM, 0, op_zc),     # glass seat (hidden behind glass)
         ring_xz(bm, opening, FY + 0.35 * MM, 0, op_zc),
         ring_xz(bm, opening, FY, 0, op_zc),
         ring_xz(bm, outer(0.5 * MM), FY, 0, ZC),
         ring_xz(bm, outer(0.0), FY + 0.5 * MM, 0, ZC),
         # parting line between the front bezel and the rear shell
         ring_xz(bm, outer(0.0), FY + 3.6 * MM, 0, ZC),
         ring_xz(bm, outer(0.45 * MM), FY + 3.85 * MM, 0, ZC),
         ring_xz(bm, outer(0.45 * MM), FY + 4.35 * MM, 0, ZC),
         ring_xz(bm, outer(0.0), FY + 4.6 * MM, 0, ZC),
         ring_xz(bm, outer(0.0), SB - 1.2 * MM, 0, ZC),
         ring_xz(bm, outer(0.8 * MM), SB - 0.3 * MM, 0, ZC),
         ring_xz(bm, outer(1.4 * MM), SB, 0, ZC)]
loft(bm, rings)
closed(bm)
slab = mesh_obj('NEW_monitor_bezel', bm, coll, [M_BEZEL])
head_parts.append(slab)

# ---------------------------------------------------------------- glass border + screen
bm = bmesh.new()
g_out = ring_xz(bm, rr_ring(op_hx - 0.05 * MM, op_hz - 0.05 * MM, op_r - 0.05 * MM, NC, NS, NS), GLASS_Y, 0, op_zc)
g_in = ring_xz(bm, rr_ring(ACT_W / 2, ACT_H / 2, 0.25 * MM, NC, NS, NS), GLASS_Y, 0, ACT_Z0 + ACT_H / 2)
bridge(bm, g_out, g_in)
face_dir(bm, Vector((0, -1, 0)))
glass = mesh_obj('NEW_monitor_glass_border', bm, coll, [M_GLASS])
head_parts.append(glass)

bm = bmesh.new()
uvl = bm.loops.layers.uv.new('UVMap')
NU, NV = 32, 18
grid = [[bm.verts.new((-ACT_W / 2 + ACT_W * i / NU, GLASS_Y - 0.02 * MM, ACT_Z0 + ACT_H * j / NV))
         for j in range(NV + 1)] for i in range(NU + 1)]
for i in range(NU):
    for j in range(NV):
        f = bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
        for loop, (ii, jj) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
            loop[uvl].uv = (ii / NU, jj / NV)
face_dir(bm, Vector((0, -1, 0)))
screen = mesh_obj('NEW_monitor_screen', bm, coll, [M_SCREEN])
head_parts.append(screen)

# ---------------------------------------------------------------- rear housing
HNC, HNX, HNZ = 8, 6, 4


def housing_ring(bm, inset, y):
    return ring_xz(bm, rr_ring(HX0 - inset, HZ0 - inset, 0.034 - inset * 0.2, HNC, HNX, HNZ), y, 0, ZH)


bm = bmesh.new()
loft(bm, [housing_ring(bm, i, y) for y, i in HOUSING_PROFILE])
closed(bm)
housing = mesh_obj('NEW_monitor_rear_housing', bm, coll, [M_REAR])
head_parts.append(housing)

# vent slots along the top run of the chamfer band
v_dir = Vector((0.0, CH1[0] - CH0[0], -(CH1[1] - CH0[1])))
band_len = v_dir.length
v_dir.normalize()
n_dir = Vector((0.0, -v_dir.z, v_dir.y))          # outward (up and back)
mid = Vector((0.0, (CH0[0] + CH1[0]) / 2, ZH + HZ0 - (CH0[1] + CH1[1]) / 2))
u_dir = Vector((1, 0, 0))
bm = bmesh.new()
slot = stadium(0.30 * band_len, 1.3 * MM, 6)      # (along v, along u)
n_slots = 0
x = -0.168
while x <= 0.1681:
    lo = [bm.verts.new(mid + u_dir * (x + b) + v_dir * a + n_dir * (-3.0 * MM)) for a, b in slot]
    hi = [bm.verts.new(mid + u_dir * (x + b) + v_dir * a + n_dir * (6.0 * MM)) for a, b in slot]
    loft(bm, [lo, hi], mat=1)
    n_slots += 1
    x += 7.0 * MM
# I/O pocket (right of the stand) and mains-inlet pocket (left), both rear-facing
IO_XC, IO_HX, IO_ZC, IO_HZ, IO_FLOOR = 0.120, 0.070, 0.305, 0.017, -0.0190
PW_XC, PW_HX, PW_HZ, PW_FLOOR = -0.090, 0.020, 0.013, -0.0160
prism_y(bm, rr_ring(IO_HX, IO_HZ, 3.0 * MM, 4, 2, 1), IO_FLOOR, 0.01, IO_XC, IO_ZC, mat=0, cap_mat=1)
prism_y(bm, rr_ring(PW_HX, PW_HZ, 3.0 * MM, 4, 2, 1), PW_FLOOR, 0.01, PW_XC, IO_ZC, mat=0, cap_mat=1)
closed(bm)
# pocket side walls in housing plastic, pocket floors and vent slots dark
cut = mesh_obj('cut_housing', bm, tmp, [M_REAR, M_DARK])
boolean(housing, cut)
print(f'vent slots {n_slots}')

# ---------------------------------------------------------------- ports (rear-facing, on the pocket floor)
PROUD = 1.2 * MM
WALL = 0.35 * MM


def port(bm_shell, bm_tong, shape, cx, cz, floor, mat_shell_idx, tongues=(), proud=PROUD, wall=WALL):
    """shape(d) -> CCW outline in (x, z) inset by d. Shell ring standing proud of the floor."""
    o0 = ring_xz(bm_shell, shape(0.0), floor - 0.4 * MM, cx, cz)
    o1 = ring_xz(bm_shell, shape(0.0), floor + proud, cx, cz)
    i1 = ring_xz(bm_shell, shape(wall), floor + proud, cx, cz)
    i0 = ring_xz(bm_shell, shape(wall), floor + 0.05 * MM, cx, cz)
    for a, b in ((o0, o1), (o1, i1), (i1, i0)):
        bridge(bm_shell, a, b, mat_shell_idx)
    cap(bm_shell, i0, 2)          # dark cavity floor
    cap(bm_shell, o0, mat_shell_idx)
    for pts, dz, h in tongues:
        prism_y(bm_tong, pts, floor, floor + h, cx, cz + dz)


bm_s = bmesh.new()
bm_t = bmesh.new()
IO = [('hdmi', 15.0), ('hdmi', 15.0), ('dp', 16.6), ('usbc', 8.9), ('usba', 13.2), ('usba', 13.2), ('jack', 6.4)]
GAP = 4.5 * MM
total = sum(w for _, w in IO) * MM + GAP * (len(IO) - 1)
xk = IO_XC - total / 2
port_log = []
for kind, w in IO:
    w *= MM
    cx = xk + w / 2
    if kind == 'hdmi':
        port(bm_s, bm_t, lambda d: chamfer_rect(7.5 * MM - d, 2.8 * MM - d, (0, 0, 1.7 * MM - 0.6 * d, 1.7 * MM - 0.6 * d)),
             cx, IO_ZC, IO_FLOOR, 0, [(rr_ring(5.6 * MM, 0.55 * MM, 0.2 * MM, 2, 0, 0), 0.35 * MM, 0.9 * MM)])
    elif kind == 'dp':
        port(bm_s, bm_t, lambda d: chamfer_rect(8.3 * MM - d, 2.7 * MM - d, (0, 0, 2.0 * MM - 0.6 * d, 0)),
             cx, IO_ZC, IO_FLOOR, 0, [(rr_ring(6.0 * MM, 0.55 * MM, 0.2 * MM, 2, 0, 0), 0.3 * MM, 0.9 * MM)])
    elif kind == 'usbc':
        port(bm_s, bm_t, lambda d: stadium(4.45 * MM - d, 1.65 * MM - d, 8),
             cx, IO_ZC, IO_FLOOR, 0, [(rr_ring(3.3 * MM, 0.35 * MM, 0.15 * MM, 2, 0, 0), 0.0, 0.9 * MM)])
    elif kind == 'usba':
        port(bm_s, bm_t, lambda d: chamfer_rect(6.6 * MM - d, 2.9 * MM - d, (0, 0, 0, 0)),
             cx, IO_ZC, IO_FLOOR, 0, [(rr_ring(5.6 * MM, 0.95 * MM, 0.2 * MM, 2, 0, 0), 0.9 * MM, 0.9 * MM)])
    elif kind == 'jack':
        port(bm_s, bm_t, lambda d: circle(3.2 * MM - 3.2 * d, 16), cx, IO_ZC, IO_FLOOR, 1, [], proud=1.0 * MM)
    port_log.append((kind, cx, w))
    xk += w + GAP
# C8 figure-8 mains inlet (plastic surround + two pins)
port(bm_s, bm_t, lambda d: figure8(3.9 * MM - d, 2.4 * MM, 10), PW_XC, IO_ZC, PW_FLOOR, 1, [],
     proud=2.0 * MM, wall=0.9 * MM)
for sx in (-1, 1):
    prism_y(bm_t, circle(0.6 * MM, 10), PW_FLOOR, PW_FLOOR + 1.3 * MM, PW_XC + sx * 2.4 * MM, IO_ZC)
closed(bm_s)
closed(bm_t)
io = mesh_obj('NEW_monitor_io', bm_s, coll, [M_NICKEL, M_PORTBLK, M_DARK])
io_t = mesh_obj('NEW_monitor_io_tongues', bm_t, coll, [M_TONGUE])
head_parts += [io, io_t]

# ---------------------------------------------------------------- chin LED + joystick
bm = bmesh.new()
prism_y(bm, circle(0.75 * MM, 12), FY - 0.12 * MM, FY + 0.3 * MM, 0.290, ZB + 4.5 * MM)
closed(bm)
led = mesh_obj('NEW_monitor_led', bm, coll, [M_LED])
head_parts.append(led)

bm = bmesh.new()
JX, JY = 0.0, -0.0445
prof = [(3.4, 1.0), (3.4, -2.2), (3.2, -2.9), (2.7, -3.5), (1.8, -3.9), (0.0, -4.05)]
rings_j = []
for rr, dz in prof[:-1]:
    rings_j.append(ring_xy(bm, circle(rr * MM, 16), ZB + dz * MM, JX, JY))
loft(bm, rings_j, cap_ends=False)
tip = bm.verts.new((JX, JY, ZB + prof[-1][1] * MM))
last = rings_j[-1]
for i in range(len(last)):
    bm.faces.new((last[i], last[(i + 1) % len(last)], tip))
cap(bm, rings_j[0])
closed(bm)
joy = mesh_obj('NEW_monitor_joystick', bm, coll, [M_PORTBLK])
head_parts.append(joy)

# ---------------------------------------------------------------- carriage (rides in the column channel)
CF = COL_YC - COL_HY                    # column front face 0.014
bm = bmesh.new()
prism_y(bm, rr_ring(0.028, 0.060, 8.0 * MM, 6, 1, 2), -0.011, 0.005, 0, 0.370)
closed(bm)
car = mesh_obj('NEW_monitor_carriage', bm, coll, [M_BEZEL])
bevel(car, 1.2 * MM, 3, 30)
bm = bmesh.new()
prism_y(bm, rr_ring(CH_HX - 0.6 * MM, 0.056, 3.0 * MM, 4, 1, 2), 0.004, CF + CH_D - 0.5 * MM, 0, 0.370)
closed(bm)
slider = mesh_obj('NEW_monitor_slider', bm, coll, [M_CHAN])
bevel(slider, 0.5 * MM, 2, 30)
lift_parts += [car, slider]

# ---------------------------------------------------------------- column
bm = bmesh.new()


def col_ring(o, z):
    return ring_xy(bm, rr_ring(COL_HX + o, COL_HY + o, COL_R + o, 6, 2, 2), z, 0, COL_YC)


FIL = 3.5 * MM
TOPR = 6.0 * MM
crings = [col_ring(FIL, BASE_TOP - 1.0 * MM)]
for k in range(7):
    ph = (math.pi / 2) * k / 6
    crings.append(col_ring(FIL - FIL * math.sin(ph), BASE_TOP + FIL - FIL * math.cos(ph)))
for k in range(7):
    ph = (math.pi / 2) * k / 6
    crings.append(col_ring(-TOPR * (1 - math.cos(ph)), COL_TOP - TOPR + TOPR * math.sin(ph)))
loft(bm, crings)
closed(bm)
column = mesh_obj('NEW_monitor_column', bm, coll, [M_ALU])
bm = bmesh.new()
# slide channel up the front face (open at the top)
prism_z(bm, rr_ring(CH_HX, 6.0 * MM, 1.0 * MM, 3, 1, 1), 0.105, COL_TOP + 0.01, 0, CF - 6.0 * MM + CH_D,
        mat=0, cap_mat=0)
# cable-routing hole through the column
prism_y(bm, rr_ring(0.018, 0.024, 6.0 * MM, 6, 1, 1), CF - 0.01, CF + 2 * COL_HY + 0.01, 0, 0.062, mat=1, cap_mat=1)
closed(bm)
ccut = mesh_obj('cut_column', bm, tmp, [M_CHAN, M_ALU])
boolean(column, ccut)
stand_parts.append(column)

# ---------------------------------------------------------------- squished hex base
HEX = [(HEX_A, HEX_YC), (HEX_B, HEX_YC + HEX_D), (-HEX_B, HEX_YC + HEX_D), (-HEX_A, HEX_YC),
       (-HEX_B, HEX_YC - HEX_D), (HEX_B, HEX_YC - HEX_D)]


def hex_ring(bm, d, z):
    return ring_xy(bm, rounded_poly(HEX, HEX_R, d, 8, 3), z)


bm = bmesh.new()
loft(bm, [hex_ring(bm, 0.9 * MM, FOOT), hex_ring(bm, 0.25 * MM, FOOT + 0.15 * MM),
          hex_ring(bm, 0.0, FOOT + 0.9 * MM), hex_ring(bm, 0.0, BASE_TOP - 1.25 * MM),
          hex_ring(bm, 0.1 * MM, BASE_TOP - 1.13 * MM), hex_ring(bm, 1.1 * MM, BASE_TOP - 0.1 * MM),
          hex_ring(bm, 1.25 * MM, BASE_TOP)])
closed(bm)
base = mesh_obj('NEW_monitor_base', bm, coll, [M_ALU])
stand_parts.append(base)

bm = bmesh.new()
FEET = [(0.126, HEX_YC, 7.0, 5.0), (-0.126, HEX_YC, 7.0, 5.0),
        (0.070, HEX_YC + 0.080, 9.0, 5.0), (-0.070, HEX_YC + 0.080, 9.0, 5.0),
        (0.070, HEX_YC - 0.080, 9.0, 5.0), (-0.070, HEX_YC - 0.080, 9.0, 5.0)]
for fx, fy, hw, hh in FEET:
    loft(bm, [ring_xy(bm, rr_ring((hw - 0.4) * MM, (hh - 0.4) * MM, 2.6 * MM, 4, 1, 1), 0.05 * MM, fx, fy),
              ring_xy(bm, rr_ring(hw * MM, hh * MM, 3.0 * MM, 4, 1, 1), 0.45 * MM, fx, fy),
              ring_xy(bm, rr_ring(hw * MM, hh * MM, 3.0 * MM, 4, 1, 1), FOOT + 0.3 * MM, fx, fy)])
closed(bm)
feet = mesh_obj('NEW_monitor_feet', bm, coll, [M_RUBBER])
stand_parts.append(feet)

# ---------------------------------------------------------------- shading
for o in (slab, housing, column, base, car, slider):
    smooth(o, 32)
for o in (io, io_t, feet, led, joy):
    smooth(o, 40)
for o in (glass, screen):
    for p in o.data.polygons:
        p.use_smooth = False

# ---------------------------------------------------------------- hierarchy
for o in list(tmp.objects):
    me = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.meshes.remove(me)
bpy.data.collections.remove(tmp)

root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_size = 0.05
coll.objects.link(root)
lift = bpy.data.objects.new(f'NEW_{NAME}_lift', None)
lift.empty_display_size = 0.03
coll.objects.link(lift)
lift.parent = root
head = bpy.data.objects.new(f'NEW_{NAME}_head', None)
head.empty_display_type = 'SINGLE_ARROW'
head.empty_display_size = 0.03
coll.objects.link(head)
head.parent = lift
head.location = PIVOT
head.rotation_euler = (TILT, 0, 0)
for o in stand_parts:
    o.parent = root
for o in lift_parts:
    o.parent = lift
for o in head_parts:
    o.parent = head
    o.matrix_parent_inverse = Matrix.Translation(-PIVOT)
root.location = ROOM_LOC
root.rotation_euler = (0, 0, ROOM_YAW)
bpy.context.view_layer.update()
parts = [o for o in coll.objects if o.type == 'MESH']

# ---------------------------------------------------------------- room context (read-only append)
CONTEXT_NAMES = ['desk_top_tmp', 'desk_top_tmp_1', 'desk_top_tmp_3', 'desk_top_tmp_4',
                 'NEW_stand_sheet', 'NEW_stand_base_pads', 'NEW_stand_deck_pads',
                 'NEW_mbp_base', 'NEW_mbp_lid', 'NEW_mbp_core', 'NEW_mbp_feet', 'NEW_mbp_hinge_barrel',
                 'NEW_keyboard_top_case', 'NEW_keyboard_bottom_case', 'NEW_keyboard_keycaps',
                 'NEW_keyboard_plate', 'NEW_keyboard_lightstrip', 'NEW_keyboard_cable',
                 'NEW_keyboard_usb_plug', 'NEW_keyboard_feet_pads', 'NEW_keyboard_switches',
                 'NEW_keyboard_display_panel', 'NEW_keyboard_indicators',
                 'hub_body', 'hub_cable', 'hub_feet',
                 'NEW_mouse_base', 'NEW_mouse_button_L', 'NEW_mouse_button_R', 'NEW_mouse_palm',
                 'NEW_mouse_wheel', 'NEW_mouse_core', 'trim_window_and_skirting', 'Mesh_11',
                 'lamp_body', 'lamp_head', 'lamp_glass', 'speedcube', 'Mesh_25', 'Mesh_26']
ctx = bpy.data.collections.new('room_context')
scene.collection.children.link(ctx)
with bpy.data.libraries.load(ROOM_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in CONTEXT_NAMES if n in src.objects]
ctx_objs = [o for o in dst.objects if o is not None]
chain = set()
for o in ctx_objs:
    p = o
    while p is not None:
        chain.add(p)
        p = p.parent
for o in chain:
    if not o.users_collection:
        ctx.objects.link(o)
bpy.context.view_layer.update()
for n in ('Mesh_25', 'Mesh_26'):
    o = bpy.data.objects.get(n)
    if o:
        pc, p = [], o.parent
        while p is not None:
            pc.append(p.name)
            p = p.parent
        print(f'OLD {n} parent chain {pc}')
mws = {o: o.matrix_world.copy() for o in ctx_objs}
for o in ctx_objs:
    o.parent = None
    o.matrix_world = mws[o]
for o in chain:
    if o not in mws:
        bpy.data.objects.remove(o, do_unlink=True)
for n in ('Mesh_25', 'Mesh_26'):
    o = bpy.data.objects.get(n)
    if o:
        ctx_objs.remove(o)
        bpy.data.objects.remove(o, do_unlink=True)
bpy.context.view_layer.update()


def bvh_of(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        off = len(verts)
        verts += [o.matrix_world @ v.co for v in me.vertices]
        polys += [[off + i for i in p.vertices] for p in me.polygons]
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


# ---------------------------------------------------------------- report
total = 0
for o in sorted(parts, key=lambda o: o.name):
    t = lib.tri_count(o)
    total += t
    lo, hi = lib.world_bounds([o])
    print(f'PART {o.name:30s} {t:6d} tris  x[{lo.x:+.4f},{hi.x:+.4f}] y[{lo.y:+.4f},{hi.y:+.4f}] '
          f'z[{lo.z:+.4f},{hi.z:+.4f}]')
lo, hi = lib.world_bounds(parts)
print(f'TOTAL {total} tris; bounds x[{lo.x:+.4f},{hi.x:+.4f}] y[{lo.y:+.4f},{hi.y:+.4f}] z[{lo.z:+.4f},{hi.z:+.4f}]')
mw = head.matrix_world @ Matrix.Translation(-PIVOT)
tl = mw @ Vector((-W2, FY, ZT))
bl = mw @ Vector((-W2, FY, ZB))
print(f'HEAD top-front edge z {tl.z:.4f}  bottom-front y {bl.y:.4f} z {bl.z:.4f}')
sc = [mw @ Vector((sx * ACT_W / 2, GLASS_Y, ACT_Z0 + sz * ACT_H)) for sx, sz in ((-1, 0), (1, 0), (1, 1), (-1, 1))]
print('SCREEN corners (BL, BR, TR, TL):', [tuple(round(c, 4) for c in v) for v in sc])
for kind, cx, w in port_log:
    c = mw @ Vector((cx, IO_FLOOR + PROUD, IO_ZC))
    print(f'PORT {kind:5s} centre ({c.x:+.4f}, {c.y:+.4f}, {c.z:+.4f}) width {w * 1000:.1f} mm')
c = mw @ Vector((PW_XC, PW_FLOOR + 2.0 * MM, IO_ZC))
print(f'PORT C8inlet centre ({c.x:+.4f}, {c.y:+.4f}, {c.z:+.4f})')
hole = root.matrix_world @ Vector((0, COL_YC, 0.062))
print(f'CABLE HOLE centre {tuple(round(v, 4) for v in hole)} (36 x 48 mm, through Y)')
spot = root.matrix_world @ Vector((0.0, -0.070, BASE_TOP))
front = root.matrix_world @ Vector((0.0, HEX_YC - HEX_D, BASE_TOP))
colf = root.matrix_world @ Vector((0.0, CF, BASE_TOP))
print(f'FIGURE SPOT {tuple(round(v, 4) for v in spot)}; clear strip y {front.y:.4f}..{colf.y:.4f} on base top z {spot.z:.4f}')

ctx_bvh = {o.name: bvh_of([o]) for o in ctx_objs if o.type == 'MESH'}
for o in parts:
    b = bvh_of([o])
    for n, cb in ctx_bvh.items():
        ov = b.overlap(cb)
        if ov:
            print(f'OVERLAP {o.name} x {n}: {len(ov)} face pairs')
print('overlap check done')


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
    T = Vector((-0.05, 1.0, 0.98))
    rig.append(area('key', (-0.6, 0.35, 1.7), T, 45.0, 0.9))
    rig.append(area('fill', (0.7, 0.3, 1.2), T, 14.0, 0.9, (0.95, 0.97, 1.0)))
    rig.append(area('rim', (0.45, 1.25, 1.55), T, 18.0, 0.5))
    # figure placeholder (8 cm tall, 5 cm wide) for the base close-up only
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.025, depth=0.08,
                                        location=(spot.x, spot.y, spot.z + 0.04))
    proxy = bpy.context.active_object
    proxy.name = 'figure_proxy'
    for c in proxy.users_collection:
        c.objects.unlink(proxy)
    ctx.objects.link(proxy)
    proxy.data.materials.append(make_mat('proxy_red', '#B03020', 0.5))
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

    walls = [bpy.data.objects.get(n) for n in ('trim_window_and_skirting', 'Mesh_11')]
    walls = [w for w in walls if w]
    views = {
        # key: (cam loc, target, lens, hide walls, show proxy)
        'seat': ((0.0, -0.16, 1.175), (-0.05, 0.97, 1.02), 32, False, False),
        'rear': ((0.62, 1.62, 1.24), (-0.03, 1.02, 0.97), 30, True, False),
        'base': ((0.30, 0.60, 0.93), (-0.05, 0.98, 0.78), 38, False, True),
        'io': ((0.28, 1.30, 1.10), (0.07, 1.01, 1.03), 45, True, False),
    }
    only = [a for a in ARGS if a.startswith('--only=')]
    only = only[0].split('=')[1].split(',') if only else None
    for key, (loc, tgt, lens, hide_walls, show_proxy) in views.items():
        if only and key not in only:
            continue
        for w in walls:
            w.hide_render = hide_walls
        proxy.hide_render = not show_proxy
        cam.location = loc
        look(cam, tgt)
        cam_d.lens = lens
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_{key}.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)

    for o in rig:
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
    scene.world = None
    bpy.data.worlds.remove(world)

# ----------------------------------------------------------------------------- save (context removed)
for o in list(ctx.all_objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.data.collections.remove(ctx)
for o in list(bpy.data.objects):
    if not o.users_collection and o.name not in coll.all_objects:
        bpy.data.objects.remove(o, do_unlink=True)
bpy.data.orphans_purge(do_recursive=True)
os.makedirs(PARTS, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('SAVED', OUT_BLEND, sorted(o.name for o in bpy.data.objects))
