"""
v2 mouse: Razer Basilisk V3 Pro, White Edition (wireless, so no cable). No logo.

Verified reference (razer.com / B&H / lanoc.org review):
  130 x 75.4 x 42.5 mm, right-handed ergonomic shape with a thumb wing that kicks out low on the
  left; two thumb buttons plus a forward "trigger" paddle on the left; tilting scroll wheel lit by
  a ring on each side; two small buttons behind the wheel; underglow wrapping ~75 % of the base;
  rubber grip sections on both sides (right one dimpled); USB-C at the front centre; underside
  with gliders (one large under the thumb wing), sensor, power switch, profile button and a round
  twist cap for the charging puck.
Assumed (not verified): exact curvature, seam placement, button outlines, grip outlines, glider
  shapes, positions of the underside switch / button, colours of the White Edition parts.

Construction (all in millimetres, scaled to metres at the end)
  * One closed master solid: a rim outline around an off-centre pole, a height field for the top
    (ridge left of centre, right side falling away) rolled over the rim with a vertical tangent,
    then a side wall whose inset varies with height and side (thumb groove + thumb wing on the
    left, shallow groove + small flare on the right, filleted underside).
  * Visible parts are exact-boolean pieces of that one solid, with real gaps: two main buttons,
    body shell, two rubber grips, underglow strip, base plate, two thumb buttons (stood proud),
    two top buttons. A dark core (the solid offset 0.9 mm inward) fills the gaps.
  * Every cut edge gets a small bevel; wheel, paddle and underside parts are separate meshes.

Usage:  blender -b --factory-startup --python v2_mouse.py -- [--no-render] [--only=34,closeup]
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
ROOM_LOC = (0.33, 0.45, 0.735)   # old mouse root ("mouse_body") in room.blend
ROOM_YAW = -0.14

# ----------------------------------------------------------------------------- dimensions (mm)
L, W, H = 130.0, 75.4, 42.5
FOOT = 0.5            # glider thickness; body underside at z = FOOT
CX, CY = -3.0, -12.0  # pole of the radial construction (near the hump)
XS = -2.0             # button split line / wheel centre x
Z_BASE = 2.3          # base plate / underglow split
Z_STRIP = 4.7         # underglow strip top
STRIP_YF = 36.0       # underglow runs from the rear to here on both sides (~75 % of the outline)
G = 0.4               # panel gap
CORE_INSET = 1.3

WHEEL_R = 10.5
WHEEL_Y = 36.0
WHEEL_PROUD = 2.6
SLOT_HW, SLOT_HL = 5.4, 5.6


def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def catmull(pts, x):
    """Catmull-Rom through sorted (x, y) points, clamped at the ends."""
    xs = [p[0] for p in pts]
    if x <= xs[0]:
        return pts[0][1]
    if x >= xs[-1]:
        return pts[-1][1]
    i = max(j for j in range(len(xs) - 1) if xs[j] <= x)
    p0 = pts[max(i - 1, 0)][1]
    p1, p2 = pts[i][1], pts[i + 1][1]
    p3 = pts[min(i + 2, len(pts) - 1)][1]
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                  (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)


# longitudinal crown line (y, z): hump behind centre, long sloping buttons
CROWN = [(-66, 25.0), (-52, 36.0), (-30, 42.3), (-18, 42.6), (0, 40.2), (22, 34.5), (45, 28.0),
         (66, 23.5)]


def ridge_x(y):
    return -5.0 + 0.03 * y


def top_height(x, y):
    """Un-rounded top surface: crown line, ridge left of centre, right side falling away."""
    h = catmull(CROWN, y)
    d = x - ridge_x(y)
    k = 0.0105 if d > 0 else 0.0065
    tilt = 0.13 if d > 0 else 0.0
    return h - k * d * d - tilt * d


def outline(t):
    """Rim outline (top view) before normalisation."""
    c, s = math.cos(t), math.sin(t)
    n = 2.7
    x = 31.0 * math.copysign(abs(c) ** (2 / n), c)
    y = 64.5 * math.copysign(abs(s) ** (2 / n), s)
    if x > 0:   # right side: a waist for the ring finger, and a narrower nose
        x *= 1 - 0.07 * math.exp(-((y + 4) / 24) ** 2) - 0.06 * smoothstep(10, 64, y)
    else:       # left side: straight-ish under the thumb, a little narrower at the nose
        x *= 1 - 0.05 * smoothstep(20, 64, y) + 0.02 * math.exp(-((y + 30) / 20) ** 2)
    return x, y


def rim_height(d):
    """Height where the top rolls into the side wall, by ray direction d (unit, xy)."""
    return 17.0 + 8.0 * max(0.0, -d.x) ** 1.5 + 2.5 * max(0.0, d.x) - 1.5 * max(0.0, d.y) - 4.0 * max(0.0, -d.y) ** 2


def wall_inset(d, y, z, zr=25.0):
    """Side-wall inset (mm, + = inward) as a function of side, position along the body and height."""
    wl = smoothstep(0.35, 0.8, -d.x)
    wr = smoothstep(0.35, 0.8, d.x)
    ins = 0.25 * (1 - z / 30.0)                                    # slight draft everywhere
    m_groove = smoothstep(-56, -34, y) * (1 - smoothstep(26, 52, y))
    m_wing = smoothstep(-62, -24, y) * (1 - smoothstep(-2, 38, y))
    gc = min(16.0, zr - 8.0)   # keep the groove clear of the rim roll-over (no fold)
    ins += wl * (4.2 * math.exp(-((z - gc) / 5.5) ** 2) * m_groove - 11.5 * smoothstep(10.5, 6.0, z) * m_wing)
    m_r = smoothstep(-56, -32, y) * (1 - smoothstep(24, 50, y))
    ins += wr * (2.4 * math.exp(-((z - 11.5) / 5.0) ** 2) - 2.2 * smoothstep(8.0, 3.5, z)) * m_r
    RF = 2.0                                                         # underside fillet
    hb = z - FOOT
    if hb < RF:
        ins += RF - math.sqrt(max(0.0, RF * RF - (RF - hb) ** 2))
    return ins


TOP_A, TOP_B = 5.0, 0.5
WALL_G = [0.9, 0.78, 0.66, 0.55, 0.45, 0.36, 0.28, 0.21, 0.15, 0.1, 0.06, 0.03, 0.01, 0.0]


def master_bm(n_theta, n_top, wall_g, off=0.0):
    """off > 0 builds the same shape shrunk by ~off mm (the dark core), ring for ring."""
    bm = bmesh.new()
    c = Vector((CX, CY))
    F = [Vector(outline(2 * math.pi * i / n_theta)) for i in range(n_theta)]
    D = [(f - c).normalized() for f in F]
    ZR = [rim_height(d) for d in D]
    pole = bm.verts.new((c.x, c.y, top_height(c.x, c.y)))
    rings = []
    for k in range(1, n_top + 1):
        s = 1 - (1 - k / n_top) ** 2
        ring = []
        for f, zr in zip(F, ZR):
            p = c + (f - c) * s * (1 - off / (f - c).length)
            ht = max(top_height(p.x, p.y), zr + 1.0)
            ring.append(bm.verts.new((p.x, p.y, zr + (ht - zr) * max(0.0, 1 - s ** TOP_A) ** TOP_B - off)))
        rings.append(ring)
    for g in wall_g:
        ring = []
        for f, d, zr in zip(F, D, ZR):
            z = FOOT + (zr - FOOT) * g
            ins = wall_inset(d, f.y, z, zr) + off
            z = max(z, FOOT + off)
            p = c + (f - c) * (1 - ins / (f - c).length)
            ring.append(bm.verts.new((p.x, p.y, z)))
        rings.append(ring)
    bot = bm.verts.new((c.x, c.y, FOOT + off))
    n = n_theta
    for i in range(n):
        bm.faces.new((pole, rings[0][i], rings[0][(i + 1) % n]))
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n):
            bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    for i in range(n):
        bm.faces.new((bot, rings[-1][(i + 1) % n], rings[-1][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


# ----------------------------------------------------------------------------- helpers

def mesh_obj(name, bm, coll):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    return o


def prism(name, pts, lo, hi, coll, mat=None, axis='z'):
    """Extrude a 2D outline along an axis. lo/hi: numbers or f(a, b) for sloped caps.
    axis 'z': pts are (x, y); 'x': pts are (y, z); 'y': pts are (x, z)."""
    def P(a, b, c):
        return {'z': (a, b, c), 'x': (c, a, b), 'y': (a, c, b)}[axis]
    f0 = lo if callable(lo) else (lambda a, b: lo)
    f1 = hi if callable(hi) else (lambda a, b: hi)
    bm = bmesh.new()
    bot = [bm.verts.new(P(a, b, f0(a, b))) for a, b in pts]
    top = [bm.verts.new(P(a, b, f1(a, b))) for a, b in pts]
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


def rrect(cx, cy, hw, hl, r, n=5):
    r = min(r, hw, hl)
    pts = []
    for (qx, qy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ox, oy = cx + qx * (hw - r), cy + qy * (hl - r)
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    return pts


def stadium(cx, cy, hw, hl, n=10):
    pts = []
    for i in range(n + 1):
        a = math.pi * i / n
        pts.append((cx + hw * math.cos(a), cy + hl + hw * math.sin(a)))
    for i in range(n + 1):
        a = math.pi + math.pi * i / n
        pts.append((cx + hw * math.cos(a), cy - hl + hw * math.sin(a)))
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


def move(obj, v):
    obj.data.transform(Matrix.Translation(Vector(v)))
    obj.data.update()


# ----------------------------------------------------------------------------- materials

def bsdf_of(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def make_mat(name, hexcol, rough, spec=0.5, grain=0.0, dimple=0.0, transmission=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = bsdf_of(mat)
    b.inputs['Base Color'].default_value = (*lib.hex_rgb(hexcol), 1.0)
    b.inputs['Roughness'].default_value = rough
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = spec
    if transmission and 'Transmission Weight' in b.inputs:
        b.inputs['Transmission Weight'].default_value = transmission
    if coat and 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = coat
    tc = nt.nodes.new('ShaderNodeTexCoord')
    normal_out = None
    rough_src = None
    if grain > 0:
        # fine moulded texture (object space is in metres after the final scale)
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs['Scale'].default_value = 1400.0
        nz.inputs['Detail'].default_value = 2.0
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = grain
        bump.inputs['Distance'].default_value = 0.00004
        nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
        normal_out = bump
        rough_src = nz.outputs['Fac']
    if dimple > 0:
        # rubber grip: a field of small round dimples (Voronoi distance) over the grain
        vo = nt.nodes.new('ShaderNodeTexVoronoi')
        vo.inputs['Scale'].default_value = 1100.0
        if 'Randomness' in vo.inputs:
            vo.inputs['Randomness'].default_value = 0.0
        nt.links.new(tc.outputs['Object'], vo.inputs['Vector'])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['From Min'].default_value = 0.18
        mr.inputs['From Max'].default_value = 0.34
        nt.links.new(vo.outputs['Distance'], mr.inputs['Value'])
        bump2 = nt.nodes.new('ShaderNodeBump')
        bump2.inputs['Strength'].default_value = dimple
        bump2.inputs['Distance'].default_value = 0.0002
        nt.links.new(mr.outputs['Result'], bump2.inputs['Height'])
        if normal_out is not None:
            nt.links.new(normal_out.outputs['Normal'], bump2.inputs['Normal'])
        normal_out = bump2
    if normal_out is not None:
        nt.links.new(normal_out.outputs['Normal'], b.inputs['Normal'])
    if rough_src is not None:
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = rough - 0.04
        mr.inputs['To Max'].default_value = rough + 0.04
        nt.links.new(rough_src, mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return mat


# ----------------------------------------------------------------------------- build

lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)
tmp = bpy.data.collections.new('tmp_cutters')
scene.collection.children.link(tmp)

M_SHELL = make_mat('mouse_shell_white_matte', '#EEEEEC', 0.42, grain=0.12)
M_BTN = make_mat('mouse_button_white_satin', '#F0F0EE', 0.32, grain=0.08)
M_GRIP = make_mat('mouse_grip_rubber_white', '#DCDCD9', 0.78, spec=0.35, grain=0.1, dimple=0.35)
M_BASE = make_mat('mouse_base_white', '#E2E2DF', 0.5, grain=0.1)
M_GLOW = make_mat('mouse_underglow_diffuser', '#F4F4F2', 0.45, transmission=0.35)
M_DARK = make_mat('mouse_interior_dark', '#1A1A1B', 0.75, spec=0.3)
M_SEAM = make_mat('mouse_seam_wall', '#6E6E6B', 0.7, spec=0.3)
M_WHEEL = make_mat('mouse_wheel_rubber', '#A4A4A1', 0.7, spec=0.35, grain=0.2)
M_FEET = make_mat('mouse_gliders', '#CDCDCA', 0.25)
M_SENSOR = make_mat('mouse_sensor_window', '#101011', 0.5, spec=0.3)
M_LENS = make_mat('mouse_sensor_lens', '#1A1012', 0.15, spec=0.5)
M_PORT = make_mat('mouse_usbc_metal', '#9A9A9C', 0.3)
M_PORT.node_tree.nodes  # (metallic set below)
bsdf_of(M_PORT).inputs['Metallic'].default_value = 1.0

S_NTH = 72
bm = master_bm(S_NTH, 14, WALL_G)
xs = [v.co.x for v in bm.verts]
ys = [v.co.y for v in bm.verts]
zs = [v.co.z for v in bm.verts]
SX, SY, SZ = W / (max(xs) - min(xs)), L / (max(ys) - min(ys)), H / max(zs)
OX, OY = -(max(xs) + min(xs)) / 2, -(max(ys) + min(ys)) / 2
print(f'raw {max(xs)-min(xs):.1f} x {max(ys)-min(ys):.1f} x {max(zs):.1f}  -> scale {SX:.3f} {SY:.3f} {SZ:.3f}')


def normalise(bm_):
    for v in bm_.verts:
        v.co.x = (v.co.x + OX) * SX
        v.co.y = (v.co.y + OY) * SY
        v.co.z = FOOT + (v.co.z - FOOT) * (H - FOOT) / (max(zs) - FOOT)


normalise(bm)
master = mesh_obj('master', bm, tmp)
bvh = BVHTree.FromObject(master, bpy.context.evaluated_depsgraph_get())


def surf_z(x, y):
    hit = bvh.ray_cast(Vector((x, y, 200)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] else None


def side_x(y, z, left=True):
    o = Vector((-200 if left else 200, y, z))
    hit = bvh.ray_cast(o, Vector((1 if left else -1, 0, 0)))
    return hit[0].x if hit[0] else None


def piece(name, mat):
    o = master.copy()
    o.data = master.data.copy()
    o.name = o.data.name = name
    coll.objects.link(o)
    o.data.materials.clear()
    o.data.materials.append(mat)
    return o


# --- region cutters -------------------------------------------------------------------------
def seam_y(x):
    """Main-button / palm seam: buttons reach furthest back along the centre."""
    return -9.0 + 0.012 * (x - XS) ** 2


def btn_bottom(x):
    """Underside line of the main buttons across the body: a low lip at the nose, rising over
    the thumb side (above the thumb buttons), staying low over the ring-finger side."""
    d = x - XS
    return 11.0 + (0.0113 if d < 0 else 0.0016) * d * d


def region_button(side, d, mat):
    xs_ = [-45 + 90 * i / 45 for i in range(46)]
    if side == 'L':
        seam = [(x, seam_y(x) + d) for x in xs_ if x <= XS - d]
        pts = seam + [(XS - d, seam_y(XS - d) + d), (XS - d, 90), (-45, 90)]
    else:
        seam = [(x, seam_y(x) + d) for x in xs_ if x >= XS + d]
        pts = [(XS + d, seam_y(XS + d) + d)] + seam + [(45, 90), (XS + d, 90)]
    seam_cut = prism(f'cut_btn{side}', pts, -10, 80, tmp, mat)
    xs2 = [-50 + 100 * i / 60 for i in range(61)]
    prof = [(x, btn_bottom(x) + d) for x in xs2] + [(50, 90), (-50, 90)]
    low = prism(f'cut_btnz{side}', prof, -90, 90, tmp, mat, axis='y')
    boolean(seam_cut, low, 'INTERSECT')
    return seam_cut


def region_slab(z0, z1, yf, mat, name):
    return prism(name, [(-60, -90), (60, -90), (60, yf), (-60, yf)], z0, z1, tmp, mat)


LGRIP = rrect(-9.0, 10.2, 29.0, 3.4, 3.0)          # (y, z) on the left side
RGRIP = rrect(-10.0, 8.6, 30.0, 3.3, 3.0)          # (y, z) on the right side
THUMB = [rrect(-4.0, 17.2, 9.2, 2.6, 2.2), rrect(15.8, 16.4, 9.2, 2.6, 2.2)]   # rear, front (y, z)
TOPBTN = [(XS, 18.5, 2.6, 3.4), (XS, 10.0, 2.6, 3.4)]                          # (x, y, hw, hl)


def grown(pts, d, cx, cy):
    """Cheap offset for convex outlines: scale about the centre by a fixed distance."""
    out = []
    for a, b in pts:
        v = Vector((a - cx, b - cy))
        L_ = v.length or 1.0
        v *= (L_ - d) / L_
        out.append((cx + v.x, cy + v.y))
    return out


def region_x(name, pts, centre, d, x0, x1, mat):
    return prism(name, grown(pts, d, *centre), x0, x1, tmp, mat, axis='x')


# --- main buttons -----------------------------------------------------------------------------
slot = stadium(XS, WHEEL_Y, SLOT_HW, SLOT_HL)
parts = {}
for side in ('L', 'R'):
    o = piece(f'NEW_mouse_button_{side}', M_BTN)
    boolean(o, region_button(side, G / 2, M_SEAM), 'INTERSECT')
    boolean(o, prism('cut_slot', slot, 8.0, 80, tmp, M_DARK), 'DIFFERENCE')
    for (x, y, hw, hl) in TOPBTN:
        zt = surf_z(x, y)
        boolean(o, prism('cut_topbtn', rrect(x, y, hw + G, hl + G, hw + G), zt - 3.5, 80, tmp, M_DARK),
                'DIFFERENCE')
    parts[side] = o

# --- body shell (palm, sides, chin) ------------------------------------------------------------
body = piece('NEW_mouse_body', M_SHELL)
boolean(body, region_slab(Z_BASE + G / 2, 80, 90, M_SEAM, 'cut_body'), 'INTERSECT')
for side in ('L', 'R'):
    boolean(body, region_button(side, -G / 2, M_SEAM), 'DIFFERENCE')
boolean(body, region_slab(Z_BASE - 1, Z_STRIP + G / 2, STRIP_YF + G / 2, M_SEAM, 'cut_strip'), 'DIFFERENCE')
boolean(body, region_x('cut_lgrip', LGRIP, (-9.0, 10.2), -G / 2, -80, -14, M_SEAM), 'DIFFERENCE')
boolean(body, region_x('cut_rgrip', RGRIP, (-10.0, 8.6), -G / 2, 14, 80, M_SEAM), 'DIFFERENCE')
for i, t in enumerate(THUMB):
    cy_, cz_ = sum(p[0] for p in t) / len(t), sum(p[1] for p in t) / len(t)
    boolean(body, region_x(f'cut_thumb{i}', t, (cy_, cz_), -G, -80, -16, M_DARK), 'DIFFERENCE')
boolean(body, prism('cut_slot_b', slot, 8.0, 80, tmp, M_DARK), 'DIFFERENCE')
# USB-C port in the chin
PORT_Z = 6.8
boolean(body, prism('cut_port', rrect(XS, PORT_Z, 4.4, 1.7, 1.6), 50, 80, tmp, M_DARK, axis='y'), 'DIFFERENCE')
# slot for the trigger paddle
PAD_Y, PAD_Z = 29.5, 11.4
boolean(body, prism('cut_pad', rrect(PAD_Y, PAD_Z, 5.4, 2.8, 2.0), -80, -16, tmp, M_DARK, axis='x'),
        'DIFFERENCE')
parts['body'] = body

# --- grips, underglow, base -------------------------------------------------------------------
lg = piece('NEW_mouse_grip_L', M_GRIP)
boolean(lg, region_x('cut_lgrip_i', LGRIP, (-9.0, 10.2), G / 2, -80, -14, M_SEAM), 'INTERSECT')
rg = piece('NEW_mouse_grip_R', M_GRIP)
boolean(rg, region_x('cut_rgrip_i', RGRIP, (-10.0, 8.6), G / 2, 14, 80, M_SEAM), 'INTERSECT')
glow = piece('NEW_mouse_underglow', M_GLOW)
boolean(glow, region_slab(Z_BASE + G / 2, Z_STRIP - G / 2, STRIP_YF - G / 2, M_SEAM, 'cut_glow'),
        'INTERSECT')
base = piece('NEW_mouse_base', M_BASE)
boolean(base, region_slab(-5, Z_BASE - G / 2, 90, M_SEAM, 'cut_base'), 'INTERSECT')
SENSOR = (XS, 4.0)
boolean(base, prism('cut_sensor', rrect(SENSOR[0], SENSOR[1], 4.6, 6.2, 1.8), -1, FOOT + 0.8, tmp, M_SENSOR),
        'DIFFERENCE')
PUCK = (XS - 1.0, -30.0)
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=False, radius=12.6, segments=32)
circ = [(v.co.x + PUCK[0], v.co.y + PUCK[1]) for v in bm.verts]
bm.free()
boolean(base, prism('cut_puck', circ, -1, FOOT + 0.7, tmp, M_SEAM), 'DIFFERENCE')
SWITCH = (14.0, -48.0)
boolean(base, prism('cut_switch', rrect(SWITCH[0], SWITCH[1], 2.0, 5.2, 1.2), -1, FOOT + 1.0, tmp, M_DARK),
        'DIFFERENCE')
PROFILE = (-16.0, -48.0)
boolean(base, prism('cut_profile', rrect(PROFILE[0], PROFILE[1], 2.3, 2.3, 2.3), -1, FOOT + 1.0, tmp, M_DARK),
        'DIFFERENCE')
parts.update(grip_L=lg, grip_R=rg, underglow=glow, base=base)

# --- thumb buttons and top buttons: pieces of the solid, stood proud ---------------------------
for i, t in enumerate(THUMB):
    cy_, cz_ = sum(p[0] for p in t) / len(t), sum(p[1] for p in t) / len(t)
    o = piece(f'NEW_mouse_thumb_{"rear" if i == 0 else "front"}', M_BTN)
    boolean(o, region_x('cut_thumb_i', t, (cy_, cz_), 0.0, -80, -16, M_SEAM), 'INTERSECT')
    move(o, (-0.9, 0, 0))
    parts[o.name] = o
for i, (x, y, hw, hl) in enumerate(TOPBTN):
    zt = surf_z(x, y)
    o = piece(f'NEW_mouse_top_button_{i}', M_BTN)
    boolean(o, prism('cut_topbtn_i', rrect(x, y, hw, hl, hw), zt - 3.0, 80, tmp, M_SEAM), 'INTERSECT')
    move(o, (0, 0, 0.3))
    parts[o.name] = o

for key, o in parts.items():
    fine = 'thumb' in key or 'top_button' in key
    bevel(o, 0.3 if fine or key in ('L', 'R') else 0.35, segments=2 if fine else 1, angle=38)
    smooth(o, 50)

# --- dark core ---------------------------------------------------------------------------------
bm = master_bm(40, 5, WALL_G, off=CORE_INSET)
normalise(bm)
core = mesh_obj('NEW_mouse_core', bm, coll)
core.data.materials.append(M_DARK)
for cutter in (prism('cut_core_slot', slot, 8.0, 80, tmp, M_DARK),
               prism('cut_core_port', rrect(XS, PORT_Z, 4.4, 1.7, 1.6), 50, 80, tmp, M_DARK, axis='y')):
    try:
        boolean(core, cutter, 'DIFFERENCE')
    except Exception as err:
        print('core cut failed', err)
smooth(core, 40)

# ----------------------------------------------------------------------------- scroll wheel
WHEEL_Z = surf_z(XS, WHEEL_Y) + WHEEL_PROUD - WHEEL_R
print(f'wheel centre z {WHEEL_Z:.2f} mm')


def revolve(name, prof, nseg, mat, rib=None, cap=True):
    """Revolve (r, x) profile points about the X axis through the wheel centre."""
    bm_ = bmesh.new()
    rings_ = []
    for (r, x) in prof:
        ring = []
        for i in range(nseg):
            a = 2 * math.pi * i / nseg
            rr = r - (rib(i, r) if rib else 0.0)
            ring.append(bm_.verts.new((XS + x, WHEEL_Y + rr * math.cos(a), WHEEL_Z + rr * math.sin(a))))
        rings_.append(ring)
    for a_, b_ in zip(rings_[:-1], rings_[1:]):
        for i in range(nseg):
            j = (i + 1) % nseg
            bm_.faces.new((a_[i], a_[j], b_[j], b_[i]))
    if cap:
        bm_.faces.new(rings_[0])
        bm_.faces.new(rings_[-1])
    bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces)
    o = mesh_obj(name, bm_, coll)
    o.data.materials.append(mat)
    return o


R = WHEEL_R
TW = 2.6   # half tread width
RIBS = 26
tread = revolve('NEW_mouse_wheel', [(R - 1.4, -TW), (R - 0.3, -TW + 0.15), (R, -TW + 0.8),
                                    (R, TW - 0.8), (R - 0.3, TW - 0.15), (R - 1.4, TW)],
                RIBS * 4, M_WHEEL, rib=lambda i, r: 0.28 if (r >= R - 0.1 and i % 4 in (2, 3)) else 0.0)
smooth(tread, 28)
rings = []
for sgn in (-1, 1):
    x0, x1 = sgn * (TW + 0.05), sgn * (TW + 1.25)
    ring = revolve(f'NEW_mouse_wheel_ring_{"L" if sgn < 0 else "R"}',
                   [(R - 2.4, x0), (R - 0.9, x0), (R - 0.7, (x0 + x1) / 2), (R - 0.9, x1), (R - 2.4, x1)],
                   28, M_GLOW)
    smooth(ring, 40)
    rings.append(ring)

# ----------------------------------------------------------------------------- paddle
# the forward "trigger" on the left side: a short blade that sticks out of its slot
sx_ = side_x(PAD_Y, PAD_Z, left=True)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= 6.0   # outward (x) incl. the part hidden in the slot
    v.co.y *= 9.6
    v.co.z *= 4.4
bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.radians(-8), 4, 'Y'), verts=bm.verts)
bmesh.ops.translate(bm, vec=Vector((sx_ - 0.5, PAD_Y, PAD_Z)), verts=bm.verts)
pad = mesh_obj('NEW_mouse_trigger_paddle', bm, coll)
pad.data.materials.append(M_BTN)
bevel(pad, 1.3, segments=3, angle=30)
smooth(pad, 40)

# ----------------------------------------------------------------------------- underside bits
ex = []
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, radius1=1.9, radius2=1.9, depth=0.4, segments=24)
bmesh.ops.translate(bm, vec=Vector((SENSOR[0], SENSOR[1] + 1.2, FOOT + 0.6)), verts=bm.verts)
lens = mesh_obj('NEW_mouse_sensor_lens', bm, coll)
lens.data.materials.append(M_LENS)
ex.append(lens)

cap = prism('NEW_mouse_puck_cap', [((x - PUCK[0]) * 12.0 / 12.6 + PUCK[0], (y - PUCK[1]) * 12.0 / 12.6 + PUCK[1])
                                   for x, y in circ], FOOT + 0.05, FOOT + 0.7, coll, M_BASE)
bevel(cap, 0.25, 1, 30)
ex.append(cap)
slider = prism('NEW_mouse_switch', rrect(SWITCH[0], SWITCH[1] + 1.6, 1.4, 1.9, 0.6), FOOT + 0.2, FOOT + 1.0,
               coll, M_BTN)
bevel(slider, 0.15, 1, 30)
ex.append(slider)
pbtn = prism('NEW_mouse_profile_button', rrect(PROFILE[0], PROFILE[1], 1.8, 1.8, 1.8, n=3), FOOT + 0.25, FOOT + 1.0,
             coll, M_BTN)
bevel(pbtn, 0.2, 1, 30)
ex.append(pbtn)
# USB-C receptacle: metal shell + tongue, set back in the port
shell_ = prism('NEW_mouse_usbc', rrect(XS, PORT_Z, 4.1, 1.45, 1.4), 58.0, 62.0, coll, M_PORT, axis='y')
ex.append(shell_)
tongue = prism('NEW_mouse_usbc_tongue', rrect(XS, PORT_Z, 3.2, 0.35, 0.3), 58.0, 62.4, coll, M_DARK, axis='y')
ex.append(tongue)


def glider(name, pts):
    o = prism(name, pts, 0.0, FOOT + 0.3, coll, M_FEET)
    bevel(o, 0.22, 1, 30)
    ex.append(o)
    return o


def arc_pts(y0, x_half, depth, width, n=14, sign=1):
    """Crescent following the nose / tail curvature."""
    out, inn = [], []
    for i in range(n + 1):
        u = -1 + 2 * i / n
        x = XS + x_half * u
        y = y0 - sign * depth * u * u
        out.append((x, y))
        inn.append((x * 0.96 + XS * 0.04, y - sign * width))
    return out + list(reversed(inn))


def edge_band(t0, t1, inset, width, n=12):
    """Glider band following the real underside outline (ray-cast on the master solid)."""
    ctr = Vector((XS, -4.0))
    out, inn = [], []
    for i in range(n + 1):
        t = math.radians(t0 + (t1 - t0) * i / n)
        d = Vector((math.cos(t), math.sin(t)))
        hit = bvh.ray_cast(Vector((ctr.x + d.x * 200, ctr.y + d.y * 200, FOOT + 0.05)),
                           Vector((-d.x, -d.y, 0)))
        p = Vector((hit[0].x, hit[0].y))
        dd = (p - ctr).normalized()
        out.append(tuple(p - dd * inset))
        inn.append(tuple(p - dd * (inset + width)))
    return out + list(reversed(inn))


glider('NEW_mouse_glider_front', edge_band(62, 118, 2.8, 3.0))
glider('NEW_mouse_glider_rear', edge_band(242, 298, 2.8, 3.0))
glider('NEW_mouse_glider_wing', edge_band(158, 200, 2.6, 4.2, n=8))
glider('NEW_mouse_glider_right', edge_band(-22, 22, 2.6, 2.6, n=8))
for o in ex:
    smooth(o, 40)

# ----------------------------------------------------------------------------- tidy + scale to metres
for o in list(tmp.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.data.collections.remove(tmp)

root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.03
coll.objects.link(root)
objs = [o for o in coll.objects if o.type == 'MESH']
for o in objs:
    o.data.transform(Matrix.Scale(0.001, 4))
    o.data.update()
    o.parent = root

bpy.context.view_layer.update()
total = 0
for o in sorted(objs, key=lambda o: o.name):
    t = lib.tri_count(o)
    total += t
    lo, hi = lib.world_bounds([o])
    print(f'PART {o.name:30s} {t:6d} tris  x[{lo.x*1000:+.1f},{hi.x*1000:+.1f}] '
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
    ground.data.materials.append(make_mat('preview_ground', '#5E5E5E', 0.55))
    rig.append(ground)
    rig.append(area('key', (-0.3, -0.25, 0.42), (0, 0, 0.015), 7.5, 0.35))
    rig.append(area('fill', (0.35, -0.12, 0.18), (0, 0, 0.015), 2.6, 0.35, (0.95, 0.97, 1.0)))
    rig.append(area('rim', (0.06, 0.42, 0.24), (0, 0, 0.015), 6.0, 0.25))
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
        'closeup': ((0.085, 0.15, 0.095), (0.0, 0.02, 0.022), 62),
        '34': ((-0.2, -0.24, 0.24), (0.0, 0.002, 0.014), 55),
        'left': ((-0.3, 0.02, 0.045), (0.0, 0.0, 0.017), 72),
        'front': ((0.03, 0.3, 0.06), (0.0, 0.0, 0.018), 72),
        'top': ((0.0, 0.0, 0.36), (0.0001, 0.0, 0.0), 48),
    }
    only = [a for a in ARGS if a.startswith('--only=')]
    only = only[0].split('=')[1].split(',') if only else None
    for key, (loc, tgt, lens_) in views.items():
        if only and key not in only:
            continue
        cam.location = loc
        look(cam, tgt)
        cam_d.lens = lens_
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_{key}.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)

    if not only or 'under' in only:
        root.rotation_euler = (0, math.pi, 0)
        root.location = (0, 0, H / 1000 + 0.0003)
        cam.location = (0.12, 0.14, 0.2)
        look(cam, (0, 0, 0.03))
        cam_d.lens = 58
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
