"""
v2 keyboard: AULA F87 Pro V2, "Gradient Grey" colourway (black case, grey-gradient PBT caps).

Verified from AULA's own product pages / photos (aulagear.com F87 PRO V2, aulaph.com):
  * 362 x 138 x 42 mm, TKL 87-key ANSI, gasket mount, hot-swap, tri-mode (USB-C wired)
  * two-piece case; the parting line between top and bottom case runs as an S-curve along
    both sides (low at the front, high at the back) and carries the side light strip
  * mode switch (BT / 2.4G / USB) on the right side; USB-C port centred on the rear face
  * small LED dot-matrix display + two round indicators + a thin light bar in the empty
    nav-cluster area above the arrow keys; a small indicator dot on the left bezel
  * Cherry-profile PBT caps (row sculpt), side-printed legends (omitted here)
  * underside: four rubber pads and two flip-out feet at the back
Measured from product photos (approximate): case rim height ~22 mm front / ~31 mm rear incl.
1.5 mm pads, keycaps stand ~6-7 mm above the rim, parting line ~6.5 mm / ~18.5 mm above the
case bottom, ~7 mm side and ~9.5 mm front/back bezels.
Assumed: switch-housing colour, plate colour, exact Cherry row heights/angles, pad colour,
cable (a straight black braided USB-C cable, as the box ships a straight cable).

Built at the origin (footprint centre on z=0, front toward -Y) and then the root empty is put
where the old keyboard sat in room.blend (the cable is routed in room coordinates, draped on
the desk by ray casts against the desk mesh appended read-only from room.blend).

Usage:  blender -b --factory-startup --python v2_keyboard.py -- [--no-render] [--only=seat,34]
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
OUT_BLEND = os.path.join(PARTS, 'keyboard.blend')
NAME = 'keyboard'

MM = 0.001
# Old keyboard parent empty "Scene.004" sits at (-0.05, 0.455, 0.735), yaw 0; the old case
# footprint was centred at y~0.40 but hung 2 cm over the desk's front edge (y=0.35), so the
# new one is centred slightly further back so all four pads are on the desk.
ROOM_LOC = Vector((-0.05, 0.435, 0.735))
ROOM_YAW = 0.0

# ----------------------------------------------------------------------------- dimensions
W, D = 362 * MM, 138 * MM
R_PLAN = 6.0 * MM
PAD = 1.5 * MM                     # rubber pad height: case bottom sits at z = PAD
H_FRONT, H_BACK = 23.0 * MM, 32.5 * MM
SLOPE = math.atan((H_BACK - H_FRONT) / D)
WELL = 9.6 * MM                    # rim to plate top
FILLET = 3.0 * MM
SEAM_LO, SEAM_HI = PAD + 6.5 * MM, PAD + 18.5 * MM
SEAM_GAP = 0.9 * MM
U = 19.05 * MM
BLOCK_W, BLOCK_D = 18.25 * U, 6.25 * U
WELL_MARGIN = 0.9 * MM
CAP_Z = 7.0 * MM                   # keycap bottom above plate top
CAP_GAP = 0.95 * MM
PORT_Z = PAD + 9.25 * MM
CABLE_R = 1.8 * MM


def z_rim(y):
    return H_FRONT + (y + D / 2) * (H_BACK - H_FRONT) / D


def z_plate(y):
    return z_rim(y) - WELL


def z_seam(y):
    t = (y + D / 2) / D
    a, b = 0.47, 0.68
    if t <= a:
        return SEAM_LO
    if t >= b:
        return SEAM_HI
    s = (t - a) / (b - a)
    s = s * s * s * (s * (s * 6 - 15) + 10)
    return SEAM_LO + (SEAM_HI - SEAM_LO) * s


# plate frame: u along X, v up the slope, w normal to the plate (origin: plate top, block centre)
PF = Matrix.Translation((0, 0, z_plate(0.0))) @ Matrix.Rotation(SLOPE, 4, 'X')

# ----------------------------------------------------------------------------- layout (ANSI TKL)
# (x offset in U from the block's left edge, width in U)
ROWS = [
    [(0, 1)] + [(2 + i, 1) for i in range(4)] + [(6.5 + i, 1) for i in range(4)]
    + [(11 + i, 1) for i in range(4)] + [(15.25 + i, 1) for i in range(3)],
    [(i, 1) for i in range(13)] + [(13, 2)] + [(15.25 + i, 1) for i in range(3)],
    [(0, 1.5)] + [(1.5 + i, 1) for i in range(12)] + [(13.5, 1.5)] + [(15.25 + i, 1) for i in range(3)],
    [(0, 1.75)] + [(1.75 + i, 1) for i in range(11)] + [(12.75, 2.25)],
    [(0, 2.25)] + [(2.25 + i, 1) for i in range(10)] + [(12.25, 2.75)] + [(16.25, 1)],
    [(0, 1.25), (1.25, 1.25), (2.5, 1.25), (3.75, 6.25), (10, 1.25), (11.25, 1.25), (12.5, 1.25),
     (13.75, 1.25)] + [(15.25 + i, 1) for i in range(3)],
]
ROW_V = [2.625 * U, 1.375 * U, 0.375 * U, -0.625 * U, -1.625 * U, -2.625 * U]
ROW_PROFILE = ['R1', 'R1', 'R2', 'R3', 'R4', 'R4']
# Cherry-style sculpt: (edge height of the top at its centre line, tilt deg: + = front lower)
PROFILE = {'R1': (9.4 * MM, 7.0), 'R2': (7.9 * MM, 4.0), 'R3': (7.5 * MM, 0.5), 'R4': (8.3 * MM, -6.5)}
# Gradient Grey: light warm grey at the F-row down to a blue-grey bottom row (sampled from
# AULA's product photo, then tempered for linear lighting)
ROW_COLS = ['#C4C2BF', '#B6B5B7', '#A1A1A5', '#898A90', '#737681', '#696D78']


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


def rr_ring(hx, hy, r, nc=3, nsx=3, nsy=3):
    """Rounded rectangle outline, CCW, with a fixed point layout so rings can be bridged."""
    r = max(min(r, hx * 0.999, hy * 0.999), 1e-6)
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
        ns = nsx if ci in (0, 2) else nsy
        for k in range(1, ns + 1):
            t = k / (ns + 1)
            pts.append((p0[0] + (q[0] - p0[0]) * t, p0[1] + (q[1] - p0[1]) * t))
    return pts


def stadium_ring(hw, hh, n=12):
    """Stadium outline in (a, b): straight along a, round ends of radius hh."""
    pts = []
    for k in range(n + 1):
        t = -math.pi / 2 + math.pi * k / n
        pts.append((hw - hh + hh * math.cos(t), hh * math.sin(t)))
    for k in range(n + 1):
        t = math.pi / 2 + math.pi * k / n
        pts.append((-hw + hh + hh * math.cos(t), hh * math.sin(t)))
    return pts


def bridge(bm, ra, rb, mat=0, flip=False):
    n = len(ra)
    for i in range(n):
        j = (i + 1) % n
        vs = (ra[i], ra[j], rb[j], rb[i])
        if flip:
            vs = vs[::-1]
        f = bm.faces.new(vs)
        f.material_index = mat


def cap_face(bm, ring, mat=0, flip=False):
    f = bm.faces.new(ring[::-1] if flip else ring)
    f.material_index = mat
    return f


def prism(bm, pts, z0, z1, M=Matrix(), mat=0):
    lo = [bm.verts.new(M @ Vector((x, y, z0))) for x, y in pts]
    hi = [bm.verts.new(M @ Vector((x, y, z1))) for x, y in pts]
    bridge(bm, lo, hi, mat)
    cap_face(bm, lo, mat, flip=True)
    cap_face(bm, hi, mat)


def finish_bm(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


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


def bevel(obj, width, segments=2, angle=35):
    m = obj.modifiers.new('bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    m.harden_normals = False
    lib.apply_modifiers(obj)


def smooth(obj, angle=35):
    lib.activate(obj)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    except (AttributeError, RuntimeError, TypeError):
        lib.shade_auto(obj, angle)


def bsdf_of(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def make_mat(name, hexcol, rough, spec=0.5, grain=0.0, coat=0.0, metal=0.0, grain_scale=1400.0):
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
        b.inputs['Coat Roughness'].default_value = 0.04
    if grain > 0:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs['Scale'].default_value = grain_scale
        nz.inputs['Detail'].default_value = 2.0
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = grain
        bump.inputs['Distance'].default_value = 0.00004
        nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = max(0.0, rough - 0.05)
        mr.inputs['To Max'].default_value = min(1.0, rough + 0.05)
        nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return mat


def dot_matrix_mat(name, n=10):
    """Unlit LED matrix: black glass with a grid of slightly lighter round LED dots."""
    mat = make_mat(name, '#08080A', 0.12, coat=0.8)
    nt = mat.node_tree
    b = bsdf_of(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])

    def cell(out):
        m1 = nt.nodes.new('ShaderNodeMath')
        m1.operation = 'MULTIPLY'
        m1.inputs[1].default_value = n
        nt.links.new(out, m1.inputs[0])
        fr = nt.nodes.new('ShaderNodeMath')
        fr.operation = 'FRACT'
        nt.links.new(m1.outputs[0], fr.inputs[0])
        sb = nt.nodes.new('ShaderNodeMath')
        sb.operation = 'SUBTRACT'
        sb.inputs[1].default_value = 0.5
        nt.links.new(fr.outputs[0], sb.inputs[0])
        return sb.outputs[0]
    cx, cy = cell(sep.outputs['X']), cell(sep.outputs['Y'])
    cmb = nt.nodes.new('ShaderNodeCombineXYZ')
    nt.links.new(cx, cmb.inputs['X'])
    nt.links.new(cy, cmb.inputs['Y'])
    ln = nt.nodes.new('ShaderNodeVectorMath')
    ln.operation = 'LENGTH'
    nt.links.new(cmb.outputs[0], ln.inputs[0])
    lt = nt.nodes.new('ShaderNodeMath')
    lt.operation = 'LESS_THAN'
    lt.inputs[1].default_value = 0.3
    nt.links.new(ln.outputs['Value'], lt.inputs[0])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.inputs[6].default_value = (*lib.hex_rgb('#08080A'), 1)
    mix.inputs[7].default_value = (*lib.hex_rgb('#2C2A2A'), 1)
    nt.links.new(lt.outputs[0], mix.inputs['Factor'])
    nt.links.new(mix.outputs[2], b.inputs['Base Color'])
    return mat


def braid_mat(name):
    """Black braided sleeve: two crossing helical ridges from the sweep's UVs (u = metres)."""
    mat = make_mat(name, '#19191B', 0.62, spec=0.4)
    nt = mat.node_tree
    b = bsdf_of(mat)
    uv = nt.nodes.new('ShaderNodeUVMap')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(uv.outputs['UV'], sep.inputs[0])

    def helix(sign):
        a = nt.nodes.new('ShaderNodeMath')
        a.operation = 'MULTIPLY'
        a.inputs[1].default_value = 1.0 / 0.0016          # 1.6 mm pitch along the cable
        nt.links.new(sep.outputs['X'], a.inputs[0])
        bb = nt.nodes.new('ShaderNodeMath')
        bb.operation = 'MULTIPLY'
        bb.inputs[1].default_value = 8.0 * sign            # 8 carriers around
        nt.links.new(sep.outputs['Y'], bb.inputs[0])
        s = nt.nodes.new('ShaderNodeMath')
        s.operation = 'ADD'
        nt.links.new(a.outputs[0], s.inputs[0])
        nt.links.new(bb.outputs[0], s.inputs[1])
        m = nt.nodes.new('ShaderNodeMath')
        m.operation = 'MULTIPLY'
        m.inputs[1].default_value = 2 * math.pi
        nt.links.new(s.outputs[0], m.inputs[0])
        sn = nt.nodes.new('ShaderNodeMath')
        sn.operation = 'SINE'
        nt.links.new(m.outputs[0], sn.inputs[0])
        return sn.outputs[0]
    mx = nt.nodes.new('ShaderNodeMath')
    mx.operation = 'MAXIMUM'
    nt.links.new(helix(1), mx.inputs[0])
    nt.links.new(helix(-1), mx.inputs[1])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.45
    bump.inputs['Distance'].default_value = 0.00015
    nt.links.new(mx.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = -1
    mr.inputs['To Min'].default_value = 0.72
    mr.inputs['To Max'].default_value = 0.5
    nt.links.new(mx.outputs[0], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return mat


# ----------------------------------------------------------------------------- scene
lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)
tmp = bpy.data.collections.new('tmp_cutters')
scene.collection.children.link(tmp)

M_CASE = make_mat('kb_case_black_matte', '#1D1D1F', 0.5, spec=0.45, grain=0.12)
M_CASE_B = make_mat('kb_bottom_black_matte', '#1B1B1D', 0.55, spec=0.45, grain=0.12)
M_DIFF = make_mat('kb_lightstrip_smoke', '#2E2F35', 0.3, spec=0.5)
M_DARK = make_mat('kb_interior_dark', '#0C0C0D', 0.8, spec=0.3)
M_PLATE = make_mat('kb_plate_black', '#141415', 0.55)
M_SWITCH = make_mat('kb_switch_housing_grey', '#3A3A3E', 0.35, spec=0.5)
M_CAPS = [make_mat(f'kb_pbt_row{i}', c, 0.58, spec=0.45, grain=0.35, grain_scale=2600.0)
          for i, c in enumerate(ROW_COLS)]
M_GLASS = make_mat('kb_display_glass_black', '#0A0A0B', 0.08, coat=1.0)
M_MATRIX = dot_matrix_mat('kb_display_matrix')
M_LED = make_mat('kb_indicator_frosted', '#9C9CA2', 0.35)
M_RUBBER = make_mat('kb_feet_rubber', '#2A2A2B', 0.85, spec=0.3)
M_TOGGLE = make_mat('kb_mode_toggle', '#2B2B2E', 0.45)
M_PLUG = make_mat('kb_plug_overmold', '#161618', 0.42, grain=0.15)
M_METAL = make_mat('kb_usbc_shell', '#C4C4C8', 0.28, metal=1.0)
M_BRAID = braid_mat('kb_cable_braid')


def case_solid(bm, inset=0.0, top_drop=0.0, mat=0):
    """Rounded-rect case block: chamfered foot, vertical walls, sloped top with a big fillet."""
    hx, hy = W / 2 - inset, D / 2 - inset
    rp = R_PLAN - inset
    nc, nsx, nsy = 8, 28, 10

    def ring(d, zf):
        pts = rr_ring(hx - d, hy - d, max(rp - d, 0.3 * MM), nc, nsx, nsy)
        return [bm.verts.new((x, y, zf(x, y))) for x, y in pts]
    z0 = PAD + inset
    rings = [ring(1.0 * MM, lambda x, y: z0), ring(0.0, lambda x, y: z0 + 1.0 * MM),
             ring(0.0, lambda x, y: z_rim(y) - top_drop - FILLET)]
    nf = 6
    for j in range(1, nf + 1):
        ph = (math.pi / 2) * j / nf
        d = FILLET * (1 - math.cos(ph))
        rings.append(ring(d, lambda x, y, ph=ph: z_rim(y) - top_drop - FILLET * (1 - math.sin(ph))))
    for a, b in zip(rings, rings[1:]):
        bridge(bm, a, b, mat)
    cap_face(bm, rings[0], mat, flip=True)
    cap_face(bm, rings[-1], mat)
    finish_bm(bm)


def seam_cutter(name, off, mat=None):
    """Everything below the parting surface z_seam(y)+off, extruded along X."""
    bm = bmesh.new()
    ys = [-D / 2 - 0.01 + (D + 0.02) * i / 90 for i in range(91)]
    prof = [(y, z_seam(y) + off) for y in ys] + [(ys[-1], -0.02), (ys[0], -0.02)]
    L = [bm.verts.new((-W / 2 - 0.01, y, z)) for y, z in prof]
    R = [bm.verts.new((W / 2 + 0.01, y, z)) for y, z in prof]
    bridge(bm, L, R)
    cap_face(bm, L)
    cap_face(bm, R, flip=True)
    finish_bm(bm)
    return mesh_obj(name, bm, tmp, [mat] if mat else [])


def pocket_cutter(name, extra=0.0):
    bm = bmesh.new()
    pts = rr_ring(BLOCK_W / 2 + WELL_MARGIN + extra, BLOCK_D / 2 + WELL_MARGIN + extra, 1.2 * MM, 4, 30, 10)
    prism(bm, pts, -1.6 * MM, 30 * MM, PF)
    finish_bm(bm)
    return mesh_obj(name, bm, tmp, [M_DARK])


# ---------------------------------------------------------------- case halves
bm = bmesh.new()
case_solid(bm)
top = mesh_obj('NEW_keyboard_top_case', bm, coll, [M_CASE])
bm = bmesh.new()
case_solid(bm)
bottom = mesh_obj('NEW_keyboard_bottom_case', bm, coll, [M_CASE_B])
bm = bmesh.new()
case_solid(bm, inset=0.7 * MM, top_drop=0.7 * MM)
core = mesh_obj('NEW_keyboard_lightstrip', bm, coll, [M_DIFF])

cut_hi = seam_cutter('cut_seam_hi', SEAM_GAP / 2)
cut_lo = seam_cutter('cut_seam_lo', -SEAM_GAP / 2)
cut_band_hi = seam_cutter('cut_band_hi', 2.0 * MM)
cut_band_lo = seam_cutter('cut_band_lo', -2.0 * MM)
pocket = pocket_cutter('cut_pocket')

boolean(top, cut_hi, 'DIFFERENCE')
boolean(top, pocket, 'DIFFERENCE')
boolean(bottom, cut_lo, 'INTERSECT')
boolean(core, cut_band_hi, 'INTERSECT')
boolean(core, cut_band_lo, 'DIFFERENCE')
boolean(core, pocket, 'DIFFERENCE')

# USB-C port: stadium pocket in the rear face of the bottom case
bm = bmesh.new()

# in this frame: x -> x, y -> z (up), z -> -y (into the case)
prism(bm, stadium_ring(4.5 * MM, 1.7 * MM, 8), -8.0 * MM, 3.0 * MM,
      Matrix.Translation((0, D / 2, PORT_Z)) @ Matrix.Rotation(math.radians(-90), 4, "X"))
finish_bm(bm)
port_cut = mesh_obj('cut_port', bm, tmp, [M_DARK])
boolean(bottom, port_cut, 'DIFFERENCE')

# mode switch slot on the right side (~38% from the front, mid-height of the top case band)
SW_Y = -D / 2 + 0.38 * D
SW_Z = (SEAM_LO + SEAM_GAP / 2 + z_rim(SW_Y) - FILLET) / 2 + 0.3 * MM
bm = bmesh.new()
M_sw = Matrix.Translation((W / 2, SW_Y, SW_Z)) @ Matrix.Rotation(math.radians(90), 4, 'Y')
# frame: local x -> -z(world), local y -> y, local z -> +x (outward)
prism(bm, [(b, a) for a, b in stadium_ring(5.5 * MM, 1.9 * MM, 8)], -2.6 * MM, 3.0 * MM, M_sw)
finish_bm(bm)
sw_cut = mesh_obj('cut_switch', bm, tmp, [M_DARK])
boolean(top, sw_cut, 'DIFFERENCE')

# flip-out feet recesses (back corners, underside)
FOOT_X = W / 2 - 40 * MM
FOOT_Y = D / 2 - 17 * MM
bm = bmesh.new()
for sx in (-1, 1):
    prism(bm, [(x + sx * FOOT_X, y + FOOT_Y) for x, y in rr_ring(15 * MM, 12 * MM, 2 * MM, 3, 2, 2)],
          PAD - 1 * MM, PAD + 1.3 * MM)
finish_bm(bm)
feet_cut = mesh_obj('cut_feet', bm, tmp, [M_DARK])
boolean(bottom, feet_cut, 'DIFFERENCE')

bevel(top, 0.35 * MM, 2, 30)
bevel(bottom, 0.35 * MM, 2, 30)
for o in (top, bottom, core):
    smooth(o, 32)

# ---------------------------------------------------------------- plate
bm = bmesh.new()
prism(bm, rr_ring(BLOCK_W / 2 + WELL_MARGIN - 0.05 * MM, BLOCK_D / 2 + WELL_MARGIN - 0.05 * MM,
                  1.15 * MM, 4, 30, 10), -1.5 * MM, 0.0, PF)
finish_bm(bm)
plate = mesh_obj('NEW_keyboard_plate', bm, coll, [M_PLATE])

# ---------------------------------------------------------------- keycaps + switches
def keycap(bm, M, w, prof, mat):
    h, tilt = PROFILE[prof]
    bw, bd = w * U - CAP_GAP, 18.1 * MM
    tw, td = bw - 5.8 * MM, 13.3 * MM
    ysh = 0.35 * MM
    ht, hd = tw / 2, td / 2
    wide = w > 2.3
    sag = (0.35 if wide else 0.5) * MM
    tt = math.tan(math.radians(tilt))
    nc, nsx, nsy = 3, max(3, round(w * 3.5)), 3

    def ztop(x, y):
        yy = y - ysh
        d = max(0.0, 1 - (yy / hd) ** 2) if wide else max(0.0, 1 - (x / ht) ** 2)
        return h + tt * y - sag * d

    def vring(pts, zf, dy=0.0):
        return [bm.verts.new(M @ Vector((x, y + dy, zf(x, y + dy)))) for x, y in pts]
    r0p = rr_ring(bw / 2, bd / 2, 0.9 * MM, nc, nsx, nsy)
    r1p = rr_ring(ht + 0.45 * MM, hd + 0.45 * MM, 1.95 * MM, nc, nsx, nsy)
    r2p = rr_ring(ht, hd, 1.5 * MM, nc, nsx, nsy)
    r0 = vring(r0p, lambda x, y: 0.0)
    r1 = vring(r1p, lambda x, y: ztop(x, y) - 0.55 * MM, ysh)
    # a ring high on the wall keeps the smooth-shaded edge roll local to the top
    rwp = [(a[0] + (b[0] - a[0]) * 0.9, a[1] + (b[1] + ysh - a[1]) * 0.9) for a, b in zip(r0p, r1p)]
    rw = []
    for (x, y), v1 in zip(rwp, r1):
        z1 = (M.inverted() @ v1.co).z
        rw.append(bm.verts.new(M @ Vector((x, y, z1 * 0.9))))
    r2 = vring(r2p, ztop, ysh)
    Lx, Ly = max(ht - hd, 0.0), max(hd - ht, 0.0)
    inner = []
    for s in (0.86, 0.5):
        pts = []
        for x, y in r2p:
            cx, cy = max(-Lx, min(Lx, x)), max(-Ly, min(Ly, y))
            pts.append((cx + (x - cx) * s, cy + (y - cy) * s))
        inner.append(vring(pts, ztop, ysh))
    centre = {}
    cv = []
    for x, y in r2p:
        cx, cy = max(-Lx, min(Lx, x)), max(-Ly, min(Ly, y))
        key = (round(cx * 1e6), round(cy * 1e6))
        if key not in centre:
            centre[key] = bm.verts.new(M @ Vector((cx, cy + ysh, ztop(cx, cy + ysh))))
        cv.append(centre[key])
    seq = [r0, rw, r1, r2] + inner
    for a, b in zip(seq, seq[1:]):
        bridge(bm, a, b, mat)
    last = inner[-1]
    n = len(last)
    for i in range(n):
        j = (i + 1) % n
        if cv[i] is cv[j]:
            f = bm.faces.new((last[i], last[j], cv[i]))
        else:
            f = bm.faces.new((last[i], last[j], cv[j], cv[i]))
        f.material_index = mat


def switch_housing(bm, M):
    lo = rr_ring(7.5 * MM, 7.5 * MM, 0.8 * MM, 1, 0, 0)
    hi = rr_ring(5.6 * MM, 6.0 * MM, 1.2 * MM, 1, 0, 0)
    a = [bm.verts.new(M @ Vector((x, y, 0.0))) for x, y in lo]
    b = [bm.verts.new(M @ Vector((x, y, 5.2 * MM))) for x, y in hi]
    bridge(bm, a, b)
    cap_face(bm, b)


bm_caps = bmesh.new()
bm_sw = bmesh.new()
n_keys = 0
for ri, row in enumerate(ROWS):
    for x0, w in row:
        u = -BLOCK_W / 2 + (x0 + w / 2) * U
        Mk = PF @ Matrix.Translation((u, ROW_V[ri], 0))
        keycap(bm_caps, Mk @ Matrix.Translation((0, 0, CAP_Z)), w, ROW_PROFILE[ri], ri)
        switch_housing(bm_sw, Mk)
        n_keys += 1
print('keys', n_keys)
assert n_keys == 87
caps = mesh_obj('NEW_keyboard_keycaps', bm_caps, coll, M_CAPS)
switches = mesh_obj('NEW_keyboard_switches', bm_sw, coll, [M_SWITCH])
for p in caps.data.polygons:
    p.use_smooth = True
smooth(switches, 40)

# ---------------------------------------------------------------- display module (nav cluster, row 3)
NAV_L = -BLOCK_W / 2 + 15.25 * U
V3 = ROW_V[3]
pan_w, pan_d = 2.86 * U, 0.86 * U
pan_cu = NAV_L + 1.5 * U
bm = bmesh.new()
prism(bm, rr_ring(pan_w / 2, pan_d / 2, 1.2 * MM, 4, 6, 3), 0.0, 1.6 * MM,
      PF @ Matrix.Translation((pan_cu, V3, 0)))
finish_bm(bm)
panel = mesh_obj('NEW_keyboard_display_panel', bm, coll, [M_GLASS])
bevel(panel, 0.3 * MM, 2, 30)
smooth(panel, 35)

mx_s = 0.74 * U
mx_u = NAV_L + 0.12 * U + 0.07 * U + mx_s / 2
bm = bmesh.new()
prism(bm, rr_ring(mx_s / 2, mx_s / 2, 0.6 * MM, 2, 1, 1), 1.2 * MM, 1.64 * MM,
      PF @ Matrix.Translation((mx_u, V3 - 0.03 * U, 0)))
finish_bm(bm)
matrix = mesh_obj('NEW_keyboard_display_matrix', bm, coll, [M_MATRIX])

bm = bmesh.new()
led_u0 = mx_u + mx_s / 2 + 4.0 * MM
for k in range(2):
    c = PF @ Matrix.Translation((led_u0 + k * 5.2 * MM, V3 - 0.12 * U, 1.6 * MM))
    pts = [(1.8 * MM * math.cos(2 * math.pi * i / 16), 1.8 * MM * math.sin(2 * math.pi * i / 16)) for i in range(16)]
    base = [bm.verts.new(c @ Vector((x, y, -0.3 * MM))) for x, y in pts]
    rim = [bm.verts.new(c @ Vector((x, y, 0.15 * MM))) for x, y in pts]
    mid = [bm.verts.new(c @ Vector((x * 0.6, y * 0.6, 0.45 * MM))) for x, y in pts]
    bridge(bm, base, rim)
    bridge(bm, rim, mid)
    cap_face(bm, mid)
    cap_face(bm, base, flip=True)
# light bar along the top edge of the module
bar_l = 1.55 * U
prism(bm, rr_ring(bar_l / 2, 0.55 * MM, 0.5 * MM, 2, 2, 0), 1.2 * MM, 1.64 * MM,
      PF @ Matrix.Translation((NAV_L + 2.86 * U - 0.1 * U - bar_l / 2 + 0.07 * U, V3 + pan_d / 2 - 1.6 * MM, 0)))
# caps-lock style indicator dot on the left bezel, level with row 3
yl = V3 * math.cos(SLOPE)
c = Matrix.Translation((-W / 2 + 4.6 * MM, yl, z_rim(yl))) @ Matrix.Rotation(SLOPE, 4, 'X')
pts = [(0.9 * MM * math.cos(2 * math.pi * i / 12), 0.9 * MM * math.sin(2 * math.pi * i / 12)) for i in range(12)]
prism(bm, pts, -0.5 * MM, 0.03 * MM, c)
finish_bm(bm)
leds = mesh_obj('NEW_keyboard_indicators', bm, coll, [M_LED])
smooth(leds, 40)

# ---------------------------------------------------------------- mode switch toggle (middle = wired)
bm = bmesh.new()
prism(bm, [(b, a) for a, b in rr_ring(2.0 * MM, 1.2 * MM, 0.6 * MM, 2, 1, 1)], -2.6 * MM, -0.5 * MM, M_sw)
finish_bm(bm)
toggle = mesh_obj('NEW_keyboard_mode_switch', bm, coll, [M_TOGGLE])
bevel(toggle, 0.25 * MM, 2, 30)
smooth(toggle, 35)

# ---------------------------------------------------------------- feet: 4 rubber pads + 2 folded flip-out feet
bm = bmesh.new()
for sx in (-1, 1):
    for sy in (-1, 1):
        cx = sx * (W / 2 - 30 * MM)
        cy = sy * (D / 2 - 7.5 * MM)
        if sy > 0:
            cx = sx * (W / 2 - 14 * MM)
            pts = [(x + cx, y + cy) for x, y in rr_ring(5 * MM, 4 * MM, 1.8 * MM, 3, 1, 1)]
        else:
            pts = [(x + cx, y + cy) for x, y in rr_ring(13 * MM, 3 * MM, 2.0 * MM, 3, 2, 1)]
        prism(bm, pts, 0.02 * MM, PAD)
finish_bm(bm)
pads = mesh_obj('NEW_keyboard_feet_pads', bm, coll, [M_RUBBER])
bevel(pads, 0.35 * MM, 2, 30)
smooth(pads, 35)

bm = bmesh.new()
for sx in (-1, 1):
    prism(bm, [(x + sx * FOOT_X, y + FOOT_Y) for x, y in rr_ring(14.4 * MM, 11.4 * MM, 1.7 * MM, 3, 2, 2)],
          PAD - 0.7 * MM, PAD + 0.2 * MM)
    # the rubber tip on the foot's free edge
    prism(bm, [(x + sx * FOOT_X, y + FOOT_Y - 8.5 * MM) for x, y in rr_ring(12 * MM, 1.8 * MM, 1.0 * MM, 3, 2, 0)],
          PAD - 0.95 * MM, PAD - 0.6 * MM, mat=1)
finish_bm(bm)
flipfeet = mesh_obj('NEW_keyboard_flip_feet', bm, coll, [M_CASE_B, M_RUBBER])
smooth(flipfeet, 35)

# ---------------------------------------------------------------- USB-C plug (plugged in)
PLUG_Y0 = D / 2 + 0.4 * MM
PLUG_Y1 = PLUG_Y0 + 16.5 * MM
RELIEF_L = 8.0 * MM
Mplug = Matrix.Translation((0, 0, PORT_Z)) @ Matrix.Rotation(math.radians(-90), 4, 'X')
# frame: local x -> x, local y -> z(up), local z -> +y (out of the case)
bm = bmesh.new()
stations = [(PLUG_Y0, 0.93), (PLUG_Y0 + 0.9 * MM, 1.0), (PLUG_Y1 - 1.6 * MM, 1.0), (PLUG_Y1, 0.88)]
rings = []
for yy, s in stations:
    pts = stadium_ring(6.0 * MM * s, 3.2 * MM * s, 8)
    rings.append([bm.verts.new(Mplug @ Vector((a, b, yy))) for a, b in pts])
for a, b in zip(rings, rings[1:]):
    bridge(bm, a, b)
cap_face(bm, rings[0], flip=True)
cap_face(bm, rings[-1])
# strain relief: round, tapering from 5.2 mm to the cable
nseg = 16
rel = []
for k in range(5):
    t = k / 4
    rr = (2.6 * (1 - t) + (CABLE_R / MM + 0.15) * t) * MM
    yy = PLUG_Y1 - 0.4 * MM + t * RELIEF_L
    rel.append([bm.verts.new(Mplug @ Vector((rr * math.cos(2 * math.pi * i / nseg),
                                              rr * math.sin(2 * math.pi * i / nseg), yy))) for i in range(nseg)])
for a, b in zip(rel, rel[1:]):
    bridge(bm, a, b)
cap_face(bm, rel[0], flip=True)
cap_face(bm, rel[-1])
# metal shell going into the port
ms = stadium_ring(4.12 * MM, 1.25 * MM, 6)
prism(bm, ms, PLUG_Y0 - 6.8 * MM, PLUG_Y0 + 0.3 * MM, Mplug, mat=1)
finish_bm(bm)
plug = mesh_obj('NEW_keyboard_usb_plug', bm, coll, [M_PLUG, M_METAL])
smooth(plug, 40)


# ---------------------------------------------------------------- room context (read-only append)
CONTEXT_NAMES = ['desk_top_tmp', 'desk_top_tmp_1', 'desk_top_tmp_3', 'desk_top_tmp_4',
                 'NEW_stand_sheet', 'NEW_stand_base_pads', 'NEW_stand_deck_pads',
                 'NEW_mbp_base', 'NEW_mbp_lid', 'NEW_mbp_core', 'NEW_mbp_feet',
                 'monitor_body', 'monitor_stand', 'monitor_cable', 'hub_body', 'hub_cable', 'hub_feet',
                 'NEW_mouse_base', 'NEW_mouse_button_L', 'NEW_mouse_button_R', 'NEW_mouse_palm',
                 'NEW_mouse_wheel', 'NEW_mouse_core', 'Mesh_31', 'speedcube_1']
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
mws = {o: o.matrix_world.copy() for o in ctx_objs}
for o in ctx_objs:
    o.parent = None
    o.matrix_world = mws[o]
for o in chain:
    if o not in mws:
        bpy.data.objects.remove(o, do_unlink=True)
bpy.context.view_layer.update()
lo, hi = lib.world_bounds([bpy.data.objects['desk_top_tmp']])
print(f'context desk top: y[{lo.y:.3f},{hi.y:.3f}] z top {hi.z:.4f}')
DESK_BACK = hi.y


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


desk_bvh = bvh_of([bpy.data.objects[n] for n in ('desk_top_tmp', 'desk_top_tmp_1', 'desk_top_tmp_3',
                                                 'desk_top_tmp_4') if n in bpy.data.objects])


def surface_z(x, y):
    hit = desk_bvh.ray_cast(Vector((x, y, 0.80)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] is not None else None


# ---------------------------------------------------------------- cable path (room coordinates)
def catmull(pts, n_per):
    out = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n_per):
            t = k / n_per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return out


start_local = Vector((0, PLUG_Y1 - 0.4 * MM + RELIEF_L, PORT_Z))
S0 = ROOM_LOC + start_local
X_RUN = 0.158      # right of the MacBook riser (x<=0.085) and left of the USB hub (x>=0.258)
ctrl = [Vector((S0.x, S0.y, 0)), Vector((S0.x, S0.y + 0.012, 0)), Vector((S0.x + 0.004, S0.y + 0.03, 0)),
        Vector((S0.x + 0.03, S0.y + 0.047, 0)), Vector((0.03, S0.y + 0.056, 0)),
        Vector((0.10, S0.y + 0.058, 0)), Vector((0.137, S0.y + 0.07, 0)), Vector((X_RUN - 0.004, S0.y + 0.11, 0)),
        Vector((X_RUN, 0.72, 0)), Vector((X_RUN + 0.004, 0.86, 0)), Vector((X_RUN + 0.002, 1.00, 0)),
        Vector((X_RUN, DESK_BACK - 0.03, 0)), Vector((X_RUN, DESK_BACK, 0))]
xy = catmull(ctrl, 24)
# resample to ~2.5 mm steps
path = [xy[0]]
for p in xy[1:]:
    if (p - path[-1]).length >= 0.0025:
        path.append(p)
if (path[-1] - xy[-1]).length > 1e-6:
    path[-1] = xy[-1]
desk_z = 0.735
s_acc = 0.0
pts3 = []
for i, p in enumerate(path):
    if i:
        s_acc += (p - path[i - 1]).length
    sz = surface_z(p.x, p.y)
    if sz is None:
        sz = desk_z
    t = min(1.0, s_acc / 0.05)
    t = t * t * (3 - 2 * t)
    zd = S0.z + (desk_z + CABLE_R - S0.z) * t
    pts3.append(Vector((p.x, p.y, max(zd, sz + CABLE_R + 0.00005))))
# over the back edge: arc of radius RB about a centre below the edge line, touching the corner
RB = 9 * MM
edge = pts3[-1].copy()
ctr_y, ctr_z = DESK_BACK, desk_z + CABLE_R - RB
for k in range(1, 13):
    th = math.pi / 2 - (math.pi / 2) * k / 12
    pts3.append(Vector((edge.x, ctr_y + RB * math.cos(th), ctr_z + RB * math.sin(th))))
for k in range(1, 9):
    pts3.append(Vector((edge.x, ctr_y + RB, ctr_z - 0.016 * k)))


def sweep(bm, pts, r, nseg=10):
    """Tube along pts with parallel-transport frames; UV u = arc length (m), v = around."""
    uvl = bm.loops.layers.uv.new('UVMap')
    tangents = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tangents.append((b - a).normalized())
    nrm = tangents[0].cross(Vector((0, 0, 1)))
    if nrm.length < 1e-6:
        nrm = Vector((1, 0, 0))
    nrm.normalize()
    rings, svals = [], []
    s = 0.0
    for i, (p, t) in enumerate(zip(pts, tangents)):
        if i:
            s += (p - pts[i - 1]).length
            tp = tangents[i - 1]
            ax = tp.cross(t)
            if ax.length > 1e-9:
                ang = tp.angle(t)
                nrm = Matrix.Rotation(ang, 3, ax.normalized()) @ nrm
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / nseg) * nrm
                                             + math.sin(2 * math.pi * k / nseg) * bi)) for k in range(nseg)])
        svals.append(s)
    for i in range(len(rings) - 1):
        for k in range(nseg):
            k2 = (k + 1) % nseg
            f = bm.faces.new((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]))
            for loop, (si, kk) in zip(f.loops, ((i, k), (i, k + 1), (i + 1, k + 1), (i + 1, k))):
                loop[uvl].uv = (svals[si], kk / nseg)
    cap_face(bm, rings[0], flip=True)
    cap_face(bm, rings[-1])
    return s


bm = bmesh.new()
local_pts = [p - ROOM_LOC for p in pts3]
cable_len = sweep(bm, local_pts, CABLE_R, 10)
finish_bm(bm)
cable = mesh_obj('NEW_keyboard_cable', bm, coll, [M_BRAID])
for p in cable.data.polygons:
    p.use_smooth = True
print(f'cable length {cable_len:.3f} m, {len(local_pts)} rings')

# ---------------------------------------------------------------- root + cleanup
for o in list(tmp.objects):
    me = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.meshes.remove(me)
bpy.data.collections.remove(tmp)

root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_size = 0.05
coll.objects.link(root)
parts = [o for o in coll.objects if o is not root]
for o in parts:
    o.parent = root
root.location = ROOM_LOC
root.rotation_euler = (0, 0, ROOM_YAW)
bpy.context.view_layer.update()

total = 0
for o in sorted(parts, key=lambda o: o.name):
    t = lib.tri_count(o)
    total += t
    lo, hi = lib.world_bounds([o])
    print(f'PART {o.name:32s} {t:6d} tris  x[{lo.x:+.4f},{hi.x:+.4f}] y[{lo.y:+.4f},{hi.y:+.4f}] '
          f'z[{lo.z:+.4f},{hi.z:+.4f}]')
lo, hi = lib.world_bounds([o for o in parts if o.name not in ('NEW_keyboard_cable', 'NEW_keyboard_usb_plug')])
print(f'TOTAL {total} tris; keyboard body {(hi.x-lo.x)*1000:.1f} x {(hi.y-lo.y)*1000:.1f} x '
      f'{(hi.z-lo.z)*1000:.1f} mm  (z {lo.z:.4f}..{hi.z:.4f})')

# intersection check of every new part against the room context
ctx_bvh = {o.name: bvh_of([o]) for o in ctx_objs}
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
    T = Vector((-0.05, 0.47, 0.76))
    rig.append(area('key', (-0.45, 0.05, 1.35), T, 22.0, 0.8))
    rig.append(area('fill', (0.55, 0.1, 1.0), T, 7.0, 0.8, (0.95, 0.97, 1.0)))
    rig.append(area('rim', (0.1, 1.3, 1.25), T, 14.0, 0.6))
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
        'seat': ((0.0, -0.16, 1.175), (-0.04, 0.50, 0.76), 34),
        '34': ((-0.40, 0.14, 0.93), (-0.07, 0.445, 0.757), 42),
        'rear': ((0.27, 0.78, 0.85), (0.02, 0.52, 0.748), 32),
        'side': ((0.42, 0.33, 0.785), (0.12, 0.44, 0.752), 55),
        'nav': ((0.20, 0.30, 0.84), (0.09, 0.43, 0.765), 60),
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
    if o.users_collection == () or not o.users_collection:
        if o.name not in coll.all_objects:
            bpy.data.objects.remove(o, do_unlink=True)
bpy.data.orphans_purge(do_recursive=True)
os.makedirs(PARTS, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('SAVED', OUT_BLEND, [o.name for o in bpy.data.objects])
