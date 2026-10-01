"""
v2 macbook: a closed 14-inch MacBook Pro (2021+ design) on a bent-aluminium laptop riser.

MacBook: 312.6 x 221.2 x 15.5 mm chassis (feet add 0.8 mm below). Built in its own frame
(front edge toward -Y, feet on z=0), as two shells with a real parting gap:
  * base (bottom case) and lid are each one closed solid swept from a rounded-rectangle plan
    (uniform 11 mm corner radius) through a vertical edge profile with real fillets,
  * a black core fills the space behind the parting gap so the seam reads as the dark bezel
    line, exactly like a closed MacBook seen from the side,
  * ports (MagSafe 3, 2x Thunderbolt, headphone | HDMI, Thunderbolt, SDXC), the front thumb
    scoop, the rear hinge/vent recess and the underside screw pockets are exact boolean
    cut-ins whose walls take a dark material; every cut edge gets a small bevel.

Stand: a Twelve South ParcSlope-style riser - one 4 mm aluminium sheet bent into a flat base,
a large rounded back and a 17 deg deck that runs DOWN toward the viewer (-Y) and ends in a
small upturned lip. Silicone strips on the deck sit exactly under the MacBook's feet; the
MacBook's front face rests 0.5 mm off the lip.

Usage:  blender -b --factory-startup --python v2_macbook.py -- [--no-render] [--only=a,b]
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402

ARGS = lib.argv()
RENDER = '--no-render' not in ARGS
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
ROOM_BLEND = os.path.join(REPO, 'blender', 'scene', 'room.blend')
OUT_BLEND = os.path.join(PARTS, 'macbook.blend')
NAME = 'macbook'

# Old macbook_body / macbook_stand sat at x=-0.06 (footprint x -0.215..0.096, y 0.581..0.809).
# Monitor and keyboard are both centred on x=-0.05; keyboard (plug) ends at y=0.580 and the
# monitor stand base starts at y=0.925. The stand's front lip goes at y=0.600.
ROOM_X = -0.05
ROOM_FRONT_Y = 0.600
DESK_Z = 0.735

# ----------------------------------------------------------------------------- MacBook dims
W, D, H = 0.3126, 0.2212, 0.0155
A, B = W / 2, D / 2
RC = 0.011              # plan corner radius
FH = 0.0008             # feet height; chassis bottom at z = FH
Z0 = FH
ZP = Z0 + 0.0100        # top of base (bottom case)
GAP = 0.0005            # parting gap
ZL = ZP + GAP           # bottom of lid
ZT = Z0 + H             # top of lid
FOOT_R = 0.006
FOOT_X, FOOT_Y = A - 0.028, B - 0.024
PORT_Z = Z0 + 0.0050

# ----------------------------------------------------------------------------- stand dims
TILT = math.radians(17.0)
T = 0.004               # sheet thickness
SW = 0.270              # stand width
SFOOT = 0.0015          # rubber strips under the base plate
R_BACK = 0.040          # centreline radius of the big rear bend
LD = 0.215              # straight deck length
RL = 0.004              # centreline radius of the lip bend (inner radius 2 mm)
LLIP = 0.0055           # straight lip length
PAD_H = 0.0015          # silicone strips on the deck
PAD_W = 0.016
LAP_GAP = 0.0005        # laptop front face to lip


# ----------------------------------------------------------------------------- helpers
def mesh_obj(name, bm, coll, mats=()):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    for m in mats:
        o.data.materials.append(m)
    return o


def rr_ring(inset, z, nc=12, a=A, b=B, rc=RC):
    r = rc - inset
    cx, cy = a - rc, b - rc
    pts = []
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        for i in range(nc + 1):
            t = math.radians(a0 + 90 * i / nc)
            pts.append((sx * cx + r * math.cos(t), sy * cy + r * math.sin(t), z))
    return pts


def shell(name, profile, coll, mats, nc=12):
    """Closed solid from a list of (inset, z) rings, bottom to top, with flat caps."""
    bm = bmesh.new()
    rings = [[bm.verts.new(p) for p in rr_ring(i, z, nc)] for i, z in profile]
    n = len(rings[0])
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for k in range(n):
            bm.faces.new((r0[k], r0[(k + 1) % n], r1[(k + 1) % n], r1[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_obj(name, bm, coll, mats)


def fillet(r, z_from, up, n, inset_side):
    """Quarter-round from a cap (inset r) to the vertical wall (inset 0)."""
    out = []
    for j in range(n + 1):
        ph = (math.pi / 2) * j / n
        if up:   # bottom edge: starts on the bottom cap, ends on the wall above
            out.append((r * (1 - math.sin(ph)), z_from + r * (1 - math.cos(ph))))
        else:    # top edge: starts on the wall, ends on the top cap
            out.append((r * (1 - math.cos(ph)), z_from - r + r * math.sin(ph)))
    return out


def extrude(name, pts2d, axis, a0, a1, coll, mats=()):
    """Prism: 2D outline in the plane normal to `axis`, extruded from a0 to a1 along it."""
    def P(u, v, w):
        if axis == 'x':
            return (w, u, v)
        if axis == 'y':
            return (u, w, v)
        return (u, v, w)
    bm = bmesh.new()
    s0 = [bm.verts.new(P(u, v, a0)) for u, v in pts2d]
    s1 = [bm.verts.new(P(u, v, a1)) for u, v in pts2d]
    n = len(pts2d)
    bm.faces.new(s0)
    bm.faces.new(s1)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((s0[i], s0[j], s1[j], s1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_obj(name, bm, coll, mats)


def stadium(cu, cv, L, Hh, n=8):
    """Stadium along u: total length L, height Hh (round ends radius Hh/2)."""
    r = Hh / 2
    hl = max(L / 2 - r, 0.0)
    pts = []
    for i in range(n + 1):
        t = -math.pi / 2 + math.pi * i / n
        pts.append((cu + hl + r * math.cos(t), cv + r * math.sin(t)))
    for i in range(n + 1):
        t = math.pi / 2 + math.pi * i / n
        pts.append((cu - hl + r * math.cos(t), cv + r * math.sin(t)))
    return pts


def circle(cu, cv, r, n=20):
    return [(cu + r * math.cos(2 * math.pi * i / n), cv + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rect(cu, cv, hu, hv):
    return [(cu - hu, cv - hv), (cu + hu, cv - hv), (cu + hu, cv + hv), (cu - hu, cv + hv)]


def join(objs, name):
    lib.activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    return o


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


def smooth(obj):
    lib.activate(obj)
    bpy.ops.object.shade_smooth()


def bevel(obj, width, segments=2, angle=40, harden=True):
    smooth(obj)
    m = obj.modifiers.new('bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    m.harden_normals = harden
    try:
        m.miter_outer = 'MITER_ARC'
    except TypeError:
        pass
    lib.apply_modifiers(obj)


def smooth_by_angle(obj, angle):
    lib.activate(obj)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    except (AttributeError, RuntimeError, TypeError):
        lib.shade_auto(obj, angle)


def bsdf_of(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def make_mat(name, hexcol, rough, metallic=0.0, spec=0.5, blast=0.0, blast_scale=5000.0, rvar=0.03,
             aniso=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = bsdf_of(mat)
    b.inputs['Base Color'].default_value = (*lib.hex_rgb(hexcol), 1.0)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metallic
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = spec
    if blast > 0:
        # Bead-blast: a very fine object-space noise into a shallow bump, plus a larger, soft
        # roughness drift so the satin highlight is not perfectly uniform across a big face.
        tc = nt.nodes.new('ShaderNodeTexCoord')
        fine = nt.nodes.new('ShaderNodeTexNoise')
        fine.inputs['Scale'].default_value = blast_scale
        fine.inputs['Detail'].default_value = 1.0
        nt.links.new(tc.outputs['Object'], fine.inputs['Vector'])
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = blast
        bump.inputs['Distance'].default_value = 0.00002
        nt.links.new(fine.outputs['Fac'], bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
        broad = nt.nodes.new('ShaderNodeTexNoise')
        broad.inputs['Scale'].default_value = 40.0
        broad.inputs['Detail'].default_value = 3.0
        nt.links.new(tc.outputs['Object'], broad.inputs['Vector'])
        mix = nt.nodes.new('ShaderNodeMath')
        mix.operation = 'MULTIPLY_ADD'
        mix.inputs[1].default_value = 0.5
        nt.links.new(broad.outputs['Fac'], mix.inputs[0])
        nt.links.new(fine.outputs['Fac'], mix.inputs[2])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['From Min'].default_value = 0.35
        mr.inputs['From Max'].default_value = 1.15
        mr.inputs['To Min'].default_value = rough - rvar
        mr.inputs['To Max'].default_value = rough + rvar
        nt.links.new(mix.outputs[0], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return mat


# ----------------------------------------------------------------------------- scene
lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)
tmp = bpy.data.collections.new('tmp_cutters')
scene.collection.children.link(tmp)

M_ALU = make_mat('mbp_alu_silver_blasted', '#D3D5D8', 0.35, metallic=1.0, blast=0.18, rvar=0.02)
M_GAP = make_mat('mbp_bezel_black', '#0B0B0C', 0.45, spec=0.4)
M_PORT = make_mat('mbp_port_interior', '#101011', 0.7, spec=0.3)
M_TONGUE = make_mat('mbp_port_tongue', '#1D1D1F', 0.5)
M_HINGE = make_mat('mbp_hinge_cover_dark', '#3A3B3E', 0.42, metallic=1.0, blast=0.1)
M_FEET = make_mat('mbp_feet_rubber', '#1B1B1C', 0.85, spec=0.3)
M_SCREW = make_mat('mbp_screw_steel', '#A6A8AB', 0.3, metallic=1.0)
M_PIN = make_mat('mbp_magsafe_pins', '#D8B46E', 0.25, metallic=1.0)
M_STAND = make_mat('stand_alu_spacegrey_anod', '#76797E', 0.38, metallic=1.0, blast=0.22, rvar=0.04,
                   blast_scale=3500.0)
M_PAD = make_mat('stand_silicone_pad', '#2A2B2C', 0.88, spec=0.35)

# ============================================================================= MACBOOK
lap_parts = []

# ---- base (bottom case)
RB, RT_B = 0.0022, 0.0005
base_prof = ([(RB + 0.0012, Z0)] + fillet(RB, Z0, True, 6, 0) + [(0.0, Z0 + RB + 0.0004)] +
             [(0.0, ZP - RT_B - 0.0003)] + fillet(RT_B, ZP, False, 3, 0) + [(RT_B + 0.0008, ZP)])
base = shell('NEW_mbp_base', base_prof, coll, [M_ALU])

# ---- lid
RL_B, RT_L = 0.0005, 0.0011
lid_prof = ([(RL_B + 0.0008, ZL)] + fillet(RL_B, ZL, True, 3, 0) + [(0.0, ZL + RL_B + 0.0003)] +
            [(0.0, ZT - RT_L - 0.0003)] + fillet(RT_L, ZT, False, 5, 0) + [(RT_L + 0.0010, ZT)])
lid = shell('NEW_mbp_lid', lid_prof, coll, [M_ALU])

# ---- cutters for the base
cut = []
LX = -A        # left flank
RX = A         # right flank


def side_cut(nm, pts, side, depth):
    x_out = side * (A + 0.002)
    x_in = side * (A - depth)
    return extrude(nm, pts, 'x', min(x_out, x_in), max(x_out, x_in), tmp, [M_PORT])


# y positions measured from the rear edge (+Y); the display hinge is at the back.
Y_MAG, Y_TB1, Y_TB2, Y_HP = B - 0.030, B - 0.053, B - 0.070, B - 0.098
Y_HDMI, Y_TB3, Y_SD = B - 0.033, B - 0.057, B - 0.094

USB_L, USB_H = 0.0086, 0.0030
HDMI = [(-0.0075, 0.0026), (0.0075, 0.0026), (0.0075, -0.0006), (0.0055, -0.0026),
        (-0.0055, -0.0026), (-0.0075, -0.0006)]
cut += [
    side_cut('c_mag', stadium(Y_MAG, PORT_Z, 0.0124, 0.0038, 8), -1, 0.0030),
    side_cut('c_tb1', stadium(Y_TB1, PORT_Z, USB_L, USB_H, 8), -1, 0.0075),
    side_cut('c_tb2', stadium(Y_TB2, PORT_Z, USB_L, USB_H, 8), -1, 0.0075),
    side_cut('c_hp', circle(Y_HP, PORT_Z, 0.0022, 20), -1, 0.0090),
    side_cut('c_hdmi', [(Y_HDMI + u, PORT_Z + v) for u, v in HDMI], 1, 0.0085),
    side_cut('c_tb3', stadium(Y_TB3, PORT_Z, USB_L, USB_H, 8), 1, 0.0075),
    side_cut('c_sd', stadium(Y_SD, PORT_Z, 0.0250, 0.0024, 6), 1, 0.0090),
]

# front thumb scoop: a shallow ellipsoid bite out of the base's top front edge
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=1.0)
for v in bm.verts:
    v.co = Vector((v.co.x * 0.029, v.co.y * 0.0048 - B, v.co.z * 0.0036 + ZP + 0.0004))
cut.append(mesh_obj('c_scoop', bm, tmp, [M_ALU]))

# rear hinge / vent recess: a long stadium (in XZ) pocket into the back face
REC_Z0, REC_Z1 = Z0 + 0.0020, ZP - 0.0008
REC_HALF = 0.1185
REC_DEPTH = 0.0065
cut.append(extrude('c_hinge', stadium(0.0, (REC_Z0 + REC_Z1) / 2, 2 * REC_HALF, REC_Z1 - REC_Z0, 10), 'y',
                   B - REC_DEPTH, B + 0.003, tmp, [M_PORT]))

# underside screw pockets (6x P5 pentalobe)
SCREWS = [(sx * (A - 0.0105), sy * (B - 0.0105)) for sx in (-1, 1) for sy in (-1, 1)]
SCREWS += [(0.0, -(B - 0.0085)), (0.0, B - 0.0110)]
for i, (sx, sy) in enumerate(SCREWS):
    cut.append(extrude(f'c_screw{i}', circle(sx, sy, 0.00135, 16), 'z', Z0 - 0.001, Z0 + 0.00032, tmp, [M_PORT]))

cutter = join(cut, 'base_cutters')
boolean(base, cutter)
bevel(base, 0.00028, segments=2, angle=50)
lap_parts.append(base)

bevel(lid, 0.0001, segments=1, angle=60)   # no cuts; keeps normals hardened on the caps
lap_parts.append(lid)

# ---- black core behind the parting gap
core = shell('NEW_mbp_core', [(0.0007, ZP - 0.0016), (0.0007, ZL + 0.0016)], coll, [M_GAP], nc=6)
lap_parts.append(core)

# ---- port inserts
ins = []
for y in (Y_TB1, Y_TB2):
    ins.append(extrude('tongue', rect(y, PORT_Z, 0.0033, 0.00035), 'x', -A + 0.0018, -A + 0.0076, coll))
ins.append(extrude('tongue', rect(Y_TB3, PORT_Z, 0.0033, 0.00035), 'x', A - 0.0076, A - 0.0018, coll))
ins.append(extrude('tongue', rect(Y_HDMI, PORT_Z + 0.0006, 0.0056, 0.00065), 'x', A - 0.0086, A - 0.0022, coll))
ins.append(extrude('tongue', circle(Y_HP, PORT_Z, 0.0012, 12), 'x', -A + 0.0060, -A + 0.0092, coll))
ins.append(extrude('tongue', rect(Y_SD, PORT_Z, 0.0118, 0.0004), 'x', A - 0.0092, A - 0.0060, coll))
tongues = join(ins, 'NEW_mbp_port_inserts')
tongues.data.materials.append(M_TONGUE)
lap_parts.append(tongues)

pins = []
for k in range(5):
    pins.append(extrude('pin', rect(Y_MAG - 0.0036 + k * 0.0018, PORT_Z, 0.00045, 0.00085), 'x',
                        -A + 0.0027, -A + 0.0031, coll))
pins = join(pins, 'NEW_mbp_magsafe_pins')
pins.data.materials.append(M_PIN)
lap_parts.append(pins)

# ---- hinge barrel + exhaust fins inside the rear recess
HB_R = 0.0024
HB_Z = REC_Z1 - HB_R - 0.0003
HB_Y = B - 0.0012 - HB_R
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=28, radius1=HB_R, radius2=HB_R,
                      depth=2 * (REC_HALF - 0.0045),
                      matrix=Matrix.Translation((0, HB_Y, HB_Z)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
barrel = mesh_obj('NEW_mbp_hinge_barrel', bm, coll, [M_HINGE])
bevel(barrel, 0.0004, segments=2, angle=50)
lap_parts.append(barrel)

bm = bmesh.new()
fin_top = HB_Z - HB_R + 0.0004
n_fins = 0
x = -REC_HALF + 0.004
while x < REC_HALF - 0.004:
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((x, B - REC_DEPTH + 0.0022, (REC_Z0 + fin_top) / 2)) @
                          Matrix.Diagonal((0.00045, 0.0040, fin_top - REC_Z0 + 0.0002, 1)))
    x += 0.0019
    n_fins += 1
fins = mesh_obj('NEW_mbp_vent_fins', bm, coll, [M_HINGE])
lap_parts.append(fins)

# ---- feet
bm = bmesh.new()
for sx in (-1, 1):
    for sy in (-1, 1):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=28, radius1=FOOT_R, radius2=FOOT_R, depth=Z0 + 0.0002,
                              matrix=Matrix.Translation((sx * FOOT_X, sy * FOOT_Y, (Z0 + 0.0002) / 2)))
feet = mesh_obj('NEW_mbp_feet', bm, coll, [M_FEET])
bevel(feet, 0.00045, segments=3, angle=50)
lap_parts.append(feet)

# ---- screws: slightly recessed heads with a dark pentalobe socket
bm = bmesh.new()
for sx, sy in SCREWS:
    bmesh.ops.create_cone(bm, cap_ends=True, segments=18, radius1=0.00112, radius2=0.00112, depth=0.00026,
                          matrix=Matrix.Translation((sx, sy, Z0 + 0.00006 + 0.00013)))
heads = mesh_obj('NEW_mbp_screws', bm, coll, [M_SCREW, M_PORT])
bevel(heads, 0.00012, segments=1, angle=50)
lap_parts.append(heads)
star = []
for sx, sy in SCREWS:
    pts = []
    for k in range(10):
        r = 0.00052 if k % 2 == 0 else 0.00030
        t = math.pi * k / 5
        pts.append((sx + r * math.cos(t), sy + r * math.sin(t)))
    star.append(extrude('star', pts, 'z', Z0 + 0.00004, Z0 + 0.00007, coll))
star = join(star, 'NEW_mbp_screw_sockets')
star.data.materials.append(M_PORT)
lap_parts.append(star)

for o in lap_parts:
    if o not in (base, lid, barrel, feet, heads):
        smooth_by_angle(o, 30)

# ============================================================================= STAND
# Centreline of the bent sheet in (y, z), with exact tangents; travel direction:
# base front edge -> rear -> up and over -> down the deck -> lip.
c17, s17 = math.cos(TILT), math.sin(TILT)
U = Vector((c17, s17))            # up the deck, toward the rear
N = Vector((-s17, c17))           # deck normal (up)
zb = SFOOT + T / 2
cl = []                           # list of (point, tangent)
YA = 0.0                          # start of the rear bend (shifted later)
# rear bend
arc_end = math.radians(180 + 17)
NA = 44
for i in range(NA + 1):
    th = arc_end * i / NA
    p = Vector((YA + R_BACK * math.sin(th), zb + R_BACK - R_BACK * math.cos(th)))
    cl.append((p, Vector((math.cos(th), math.sin(th)))))
E = cl[-1][0]
Dend = E - U * LD
cl.append((Dend, -U))
# lip bend (clockwise 90 deg), centre on the deck-normal side
C = Dend + N * RL
a0 = math.atan2(-N.y, -N.x)
for i in range(1, 9):
    a = a0 - (math.pi / 2) * i / 8
    p = C + RL * Vector((math.cos(a), math.sin(a)))
    tan = Vector((math.cos(a - math.pi / 2), math.sin(a - math.pi / 2)))
    cl.append((p, tan))
L0 = cl[-1][0]
cl.append((L0 + N * LLIP, N.copy()))
# base plate: from 14 mm behind the lip back to the bend
base_front_y = L0.x - 0.5 * T + 0.014
cl.insert(0, (Vector((base_front_y, zb)), Vector((1.0, 0.0))))

outer, inner = [], []
for p, t in cl:
    t = t.normalized()
    cw = Vector((t.y, -t.x))
    outer.append(p + cw * (T / 2))
    inner.append(p - cw * (T / 2))
profile = outer + list(reversed(inner))

stand_frame_min_y = min(p.x for p in profile)
stand_frame_max_y = max(p.x for p in profile)
SHIFT = -(stand_frame_min_y + stand_frame_max_y) / 2     # centre the footprint on y=0


def sy(y):
    return y + SHIFT


sheet = extrude('NEW_stand_sheet', [(sy(p.x), p.y) for p in profile], 'x', -SW / 2, SW / 2, coll, [M_STAND])
bevel(sheet, 0.0013, segments=4, angle=40)

# deck frame: Q is on the deck's top surface where the lip bend starts
Q = Dend + N * (T / 2)
R_IN = RL - T / 2
S0 = -R_IN + LAP_GAP + B          # laptop centre along the deck


def deck_to_stand(x, s, h):
    p = Q + U * s + N * h
    return (x, sy(p.x), p.y)


# silicone strips on the deck, centred under the MacBook's feet
pads = []
for s_c in (S0 - FOOT_Y, S0 + FOOT_Y):
    bm = bmesh.new()
    pts = stadium(0.0, s_c, SW - 0.012, PAD_W, 8)
    bot = [bm.verts.new(deck_to_stand(u, v, -0.0003)) for u, v in pts]
    top = [bm.verts.new(deck_to_stand(u, v, PAD_H)) for u, v in pts]
    bm.faces.new(bot)
    bm.faces.new(top)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    pads.append(mesh_obj('pad', bm, coll))
pads = join(pads, 'NEW_stand_deck_pads')
pads.data.materials.append(M_PAD)
bevel(pads, 0.0006, segments=2, angle=40)

# rubber strips under the base plate
feet_s = []
for yc in (base_front_y + 0.012, YA - 0.004):
    feet_s.append(extrude('sfoot', stadium(0.0, sy(yc), SW - 0.020, 0.010, 8), 'z', 0.0, SFOOT + 0.0003, coll))
sfeet = join(feet_s, 'NEW_stand_base_pads')
sfeet.data.materials.append(M_PAD)
bevel(sfeet, 0.0005, segments=2, angle=40)

# ============================================================================= assemble
for o in list(tmp.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.data.collections.remove(tmp)

root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.05
coll.objects.link(root)
lap = bpy.data.objects.new('NEW_macbook_laptop', None)
lap.empty_display_type = 'PLAIN_AXES'
lap.empty_display_size = 0.03
coll.objects.link(lap)
lap.parent = root
lap.location = deck_to_stand(0.0, S0, PAD_H)
lap.rotation_euler = (TILT, 0.0, 0.0)
for o in lap_parts:
    o.parent = lap
for o in (sheet, pads, sfeet):
    o.parent = root

objs = [o for o in coll.objects if o.type == 'MESH']
for o in objs:
    try:
        lib.uv_unwrap(o)
    except Exception as err:  # headless smart-project can fail; UVs are optional here
        print(f'  uv skipped on {o.name}: {err}')

bpy.context.view_layer.update()
tot_l = tot_s = 0
for o in sorted(objs, key=lambda o: o.name):
    t = lib.tri_count(o)
    if o.parent == lap:
        tot_l += t
    else:
        tot_s += t
    lo, hi = lib.world_bounds([o])
    print(f'PART {o.name:28s} {t:6d} tris  x[{lo.x*1000:+.1f},{hi.x*1000:+.1f}] '
          f'y[{lo.y*1000:+.1f},{hi.y*1000:+.1f}] z[{lo.z*1000:+.1f},{hi.z*1000:+.1f}] mm')
print(f'TOTAL macbook {tot_l} tris, stand {tot_s} tris')
lo, hi = lib.world_bounds([o for o in objs if o.parent == lap])
print(f'MACBOOK bounds size (tilted) {(hi-lo)*1000}')
print(f'LAPTOP pose: loc {tuple(round(v, 4) for v in lap.location)}  tilt {math.degrees(TILT):.1f} deg')
lo, hi = lib.world_bounds([sheet])
print(f'STAND size {(hi.x-lo.x)*1000:.1f} x {(hi.y-lo.y)*1000:.1f} x {(hi.z-lo.z)*1000:.1f} mm')

# ---- place in the room: stand front (lip) at ROOM_FRONT_Y
root.location = (ROOM_X, ROOM_FRONT_Y - lo.y, DESK_Z)
bpy.context.view_layer.update()
lo, hi = lib.world_bounds(objs)
print(f'ROOM bounds x[{lo.x:.4f},{hi.x:.4f}] y[{lo.y:.4f},{hi.y:.4f}] z[{lo.z:.4f},{hi.z:.4f}]')
print(f'ROOT location {tuple(round(v, 4) for v in root.location)}')

bpy.data.orphans_purge(do_recursive=True)
os.makedirs(PARTS, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('SAVED', OUT_BLEND)


# ============================================================================= previews
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
    only = [a for a in ARGS if a.startswith('--only=')]
    only = only[0].split('=')[1].split(',') if only else None

    # context from room.blend (read-only append; this file is not saved again)
    ctx = bpy.data.collections.new('CONTEXT_room')
    scene.collection.children.link(ctx)
    want = ['room', 'Scene.001', 'Node_23', 'Node_43', 'Mesh_31']
    with bpy.data.libraries.load(ROOM_BLEND, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    keep = set()
    for n in want:
        o = bpy.data.objects.get(n)
        if o:
            keep.add(o)
            if n != 'room':
                keep.update(o.children_recursive)
    for o in keep:
        if o.name not in ctx.objects:
            ctx.objects.link(o)
    bpy.context.view_layer.update()

    # intersection check against the monitor and keyboard bounds
    def bounds_of(root_name):
        o = bpy.data.objects[root_name]
        return lib.world_bounds([c for c in o.children_recursive if c.type == 'MESH'])
    mlo, mhi = lib.world_bounds(objs)
    for nm in ('Node_23', 'Node_43'):
        blo, bhi = bounds_of(nm)
        ov = all(mlo[i] < bhi[i] and blo[i] < mhi[i] for i in range(3))
        print(f'CLEAR vs {nm}: bbox overlap={ov}  gap_y={blo.y - mhi.y if blo.y > mlo.y else mlo.y - bhi.y:.4f}')

    world = bpy.data.worlds.new('preview_world')
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.18, 0.18, 0.18, 1)
    bg.inputs[1].default_value = 0.6
    scene.world = world

    TGT = Vector((ROOM_X, root.location.y, DESK_Z + 0.05))
    area('key', TGT + Vector((-0.5, -0.6, 0.7)), TGT, 60.0, 0.5)
    area('fill', TGT + Vector((0.7, -0.4, 0.3)), TGT, 18.0, 0.6, (0.95, 0.97, 1.0))
    area('rim', TGT + Vector((0.3, 0.6, 0.5)), TGT, 30.0, 0.4)

    bpy.ops.mesh.primitive_plane_add(size=3.0, location=(ROOM_X, root.location.y, DESK_Z))
    ground = bpy.context.object
    ground.name = 'preview_ground'
    for c_ in list(ground.users_collection):
        c_.objects.unlink(ground)
    scene.collection.objects.link(ground)
    ground.data.materials.append(make_mat('preview_ground', '#6E6E6E', 0.55))

    cam_d = bpy.data.cameras.new('preview_cam')
    cam = bpy.data.objects.new('preview_cam', cam_d)
    scene.collection.objects.link(cam)
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

    X, Y = ROOM_X, root.location.y
    Zd = DESK_Z
    views = {
        # the seated viewer's eye, aimed at the laptop (tele) and the real seat camera (wide)
        'seat': ((0.0, -0.16, 1.175), (X, Y, Zd + 0.06), 45, True),
        'seatwide': ((0.0, -0.16, 1.175), (0.0, 0.85, 0.87), 23.55, True),
        '34': ((X - 0.36, Y - 0.40, Zd + 0.24), (X - 0.02, Y, Zd + 0.045), 50, False),
        'side': ((X + 0.55, Y - 0.02, Zd + 0.07), (X, Y, Zd + 0.045), 55, False),
        'rear': ((X + 0.30, Y + 0.42, Zd + 0.17), (X + 0.02, Y + 0.05, Zd + 0.07), 55, False),
        'ports': ((X - 0.26, Y - 0.06, Zd + 0.10), (X - 0.156, Y + 0.02, Zd + 0.065), 70, False),
        'portsR': ((X + 0.26, Y - 0.06, Zd + 0.10), (X + 0.156, Y + 0.02, Zd + 0.065), 70, False),
        'front': ((X + 0.05, Y - 0.28, Zd + 0.10), (X, Y - 0.08, Zd + 0.035), 60, False),
    }
    for key, (loc, tgt, lens, with_ctx) in views.items():
        if only and key not in only:
            continue
        ctx.hide_render = not with_ctx
        ground.hide_render = with_ctx
        cam.location = loc
        look(cam, tgt)
        cam_d.lens = lens
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_{key}.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)

    if not only or 'under' in only:
        # underside: lift the laptop off the stand and flip it onto its back above the stand
        ctx.hide_render = True
        ground.hide_render = True
        sheet.hide_render = pads.hide_render = sfeet.hide_render = True
        lap.location = (0.0, 0.0, 0.2)
        lap.rotation_euler = (0.0, math.pi, 0.0)
        bpy.context.view_layer.update()
        c = lap.matrix_world.translation
        cam.location = c + Vector((-0.2, -0.27, 0.24))
        look(cam, c + Vector((0, 0, 0.01)))
        cam_d.lens = 40
        area('under_key', c + Vector((-0.25, -0.1, 0.4)), c, 10.0, 0.5)
        scene.view_settings.exposure = -1.5
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_under.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)
