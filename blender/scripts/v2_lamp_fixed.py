"""
v2_lamp_fixed.py -- clean white desk lamp after the owner's twin-bar design, all straight/true geometry.

    blender -b --factory-startup --python blender/scripts/v2_lamp_fixed.py -- [--no-render]

Owner spec (and what was measured from the original lamp, OLD_replaced / lamp003 + Cylinder in room.blend):
  * round weighted base: same centre/radius/height as the original (lamp003_1).
  * STEM: the lower part is one straight vertical column (Ø26). At about mid-height it splits (a moulded
    junction block) into TWO identical PARALLEL round branches (Ø16), spaced 37 mm apart along the
    plane of movement (the original's twin members were 36.6 mm apart along their lean), which bend
    forward with one smooth arc and then run straight at 12.6 deg -- the original twin bars' lean.
  * a top yoke (same moulded shape as the junction) with pivot caps, then the ORIGINAL SHORT NECK:
    15 mm long (the original neck cylinder measured 14.7 mm), straight and horizontal.
  * HEAD: a true flat circular disc, Ø160 x 16 mm, planar top and bottom, soft edge, level;
    round diffuser + bezel + DISK area light flush and centred underneath.
  * plane of movement = the direction the head reaches out = toward the seated viewer, as the original
    head did (its blade pointed at the seat).
All plastic uses lamp_white_plastic. Writes parts/lamp.blend (NEW_lamp / NEW_lamp_root, ROOM coords,
unit scale everywhere) and parts/lamp_meta.json (neck frame for v2_medals.py).
"""
import bpy
import bmesh
import json
import math
import os
import sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'lamp.blend')
OUT_META = os.path.join(PARTS, 'lamp_meta.json')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
SEAT = Vector((0.0, -0.16, 1.175))
Z = Vector((0, 0, 1))

# ---- original base (lamp003_1, measured)
BASE_C = Vector((-0.7138, 1.0381))
BASE_R = 0.087
BASE_Z0, BASE_Z1 = 0.735, 0.749      # slimmer weighted disc: 14 mm (owner), same diameter

# ---- stem / branches (original twin members: 36.6 mm apart along the lean, lean 12.6 deg)
COL_R = 0.013
COL_BACK = 0.030               # column axis sits this far behind the base centre (head reaches forward)
SPLIT_Z0, SPLIT_Z1 = 0.940, 0.970   # (kept: the branches' bend starts at SPLIT_Z1 + BR_RISE0 as before)
# ---- column + clevis joint (owner: column as wide as the bar pair; bars jointed into its top)
COL_W = 0.037 + 0.016          # along the plane of movement: bar spacing + bar diameter = 53 mm
COL_D = 0.026                  # across
COL_CORNER = 0.005
SLOT_W = 0.016 + 2 * 0.0008    # bar/hub thickness + 0.8 mm clearance each side
AXLE_Z = 0.945                 # pivot axle height
HUB_R = 0.024                  # rotating hub that carries both bar roots (�48, 16 thick)
HUB_T = 0.016
FLOOR_GAP = 0.0015             # hub to slot floor
CHEEK_R = COL_W / 2            # cheek tops are arcs about the axle
AXLE_R = 0.004
KNOB_R = 0.0105
BR_R = 0.008                   # Ø16 branches
BR_SPACING = 0.037             # centre-to-centre, along the plane of movement
BR_LEAN = math.radians(12.6)
BR_RISE0 = 0.010               # straight vertical run above the junction before the bend
BR_BEND_R = 0.080              # bend radius (one smooth arc)
BLOCK_R = 0.013                # junction/yoke end radius (stadium footprint)
YOKE_H = 0.026
# ---- neck + head
NECK_R = 0.008                 # Ø16 round neck (head is 16 mm thick)
NECK_LEN = 0.015               # ORIGINAL short neck length (measured 14.7 mm)
HEAD_R = 0.080
HEAD_T = 0.016
HEAD_EDGE = 0.005
HEAD_BOTTOM = 1.180
# ---- circular light (v2_lamp.py values; diffuser sized to the Ø160 head)
DIFF_R = 0.062
WARM = (1.0, 0.86, 0.68)
DISK_ENERGY = 7.0
DISK_SPREAD = math.radians(75)

F2 = (SEAT.to_2d() - BASE_C).normalized()      # plane of movement: toward the seat
F3 = F2.to_3d()
T3 = Z.cross(F3).normalized()                   # across the plane of movement


# ------------------------------------------------------------------------------ geometry helpers
def frame(origin, zaxis, xhint=None):
    zaxis = zaxis.normalized()
    x = (xhint - zaxis * xhint.dot(zaxis)).normalized() if xhint is not None else zaxis.orthogonal().normalized()
    y = zaxis.cross(x)
    return Matrix(((x.x, y.x, zaxis.x, origin.x), (x.y, y.y, zaxis.y, origin.y),
                   (x.z, y.z, zaxis.z, origin.z), (0, 0, 0, 1)))


def lathe(prof, fr, seg=64):
    bm = bmesh.new()
    rings = []
    for r, h in prof:
        if r < 1e-9:
            rings.append([bm.verts.new(fr @ Vector((0, 0, h)))])
        else:
            rings.append([bm.verts.new(fr @ Vector((r * math.cos(2 * math.pi * j / seg),
                                                     r * math.sin(2 * math.pi * j / seg), h))) for j in range(seg)])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(seg):
            j2 = (j + 1) % seg
            if len(A) == 1:
                bm.faces.new([A[0], B[j], B[j2]])
            elif len(B) == 1:
                bm.faces.new([A[j], A[j2], B[0]])
            else:
                bm.faces.new([A[j], A[j2], B[j2], B[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def tube(path, radius, seg=32, cap=True):
    """Round tube along a planar polyline path (list of Vector); frames by parallel transport."""
    bm = bmesh.new()
    rings = []
    n_prev = None
    for i, p in enumerate(path):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, len(path) - 1)]
        tan = (b - a).normalized()
        if n_prev is None:
            n = T3.copy()
        else:
            n = (n_prev - tan * n_prev.dot(tan)).normalized()
        n_prev = n
        bnorm = tan.cross(n)
        rings.append([bm.verts.new(p + (n * math.cos(2 * math.pi * j / seg) + bnorm * math.sin(2 * math.pi * j / seg)) * radius)
                      for j in range(seg)])
    for r in range(len(rings) - 1):
        for j in range(seg):
            bm.faces.new([rings[r][j], rings[r][(j + 1) % seg], rings[r + 1][(j + 1) % seg], rings[r + 1][j]])
    if cap:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def stadium_block(centre, half_len, r, z0, z1, fillet, axis2, n_arc=16, n_fil=5):
    """Rounded stadium prism (two half-circles of radius r at +-half_len along axis2) with filleted
    top and bottom edges. Built as stacked offset rings."""
    a = axis2.normalized()
    b = Vector((-a.y, a.x))

    def outline(off):
        rr = r - off
        pts = []
        for k in range(n_arc + 1):                     # +a end, from -b to +b
            ang = -math.pi / 2 + math.pi * k / n_arc
            pts.append(centre + a * half_len + (a * math.cos(ang) + b * math.sin(ang)) * rr)
        for k in range(n_arc + 1):                     # -a end, from +b to -b
            ang = math.pi / 2 + math.pi * k / n_arc
            pts.append(centre - a * half_len + (a * math.cos(ang) + b * math.sin(ang)) * rr)
        return pts
    levels = []
    for k in range(n_fil + 1):                         # bottom fillet
        ang = math.pi / 2 * k / n_fil
        levels.append((z0 + fillet - fillet * math.cos(ang), fillet - fillet * math.sin(ang)))
    for k in range(n_fil + 1):                         # top fillet
        ang = math.pi / 2 * k / n_fil
        levels.append((z1 - fillet + fillet * math.sin(ang), fillet - fillet * math.cos(ang)))
    bm = bmesh.new()
    rings = [[bm.verts.new((p.x, p.y, zz)) for p in outline(off)] for zz, off in levels]
    n = len(rings[0])
    for r_ in range(len(rings) - 1):
        for j in range(n):
            bm.faces.new([rings[r_][j], rings[r_][(j + 1) % n], rings[r_ + 1][(j + 1) % n], rings[r_ + 1][j]])
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


# ------------------------------------------------------------------------------ materials
def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def white_plastic():
    m = bpy.data.materials.new('lamp_white_plastic')
    m.use_nodes = True
    nt = m.node_tree
    p = principled(m)
    p.inputs['Base Color'].default_value = (0.83, 0.83, 0.82, 1)
    p.inputs['Roughness'].default_value = 0.33
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 1400
    nz.inputs['Detail'].default_value = 4
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.03
    bump.inputs['Distance'].default_value = 0.0002
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    nz2 = nt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 220
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.30
    mr.inputs['To Max'].default_value = 0.36
    nt.links.new(nz2.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], p.inputs['Roughness'])
    return m


def diffuser_mat():
    m = bpy.data.materials.new('lamp_diffuser')
    m.use_nodes = True
    p = principled(m)
    p.inputs['Base Color'].default_value = (0.95, 0.95, 0.93, 1)
    p.inputs['Roughness'].default_value = 0.5
    p.inputs['Emission Color'].default_value = (*WARM, 1)
    p.inputs['Emission Strength'].default_value = 6.0
    return m


# ------------------------------------------------------------------------------ build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    coll = bpy.data.collections.new('NEW_lamp')
    scene.collection.children.link(coll)
    WP = white_plastic()
    DM = diffuser_mat()
    parts = {}

    col_xy = BASE_C - F2 * COL_BACK
    col3 = Vector((col_xy.x, col_xy.y, 0))
    head_mid = HEAD_BOTTOM + HEAD_T / 2

    # ---- base (same footprint): foot ring, rounded top edge, shallow top groove
    R, z0, z1 = BASE_R, BASE_Z0, BASE_Z1
    prof = [(0.0, z0), (R - 0.008, z0), (R - 0.0068, z0 + 0.0008), (R - 0.0062, z0 + 0.0022),
            (R - 0.0030, z0 + 0.0026), (R - 0.0009, z0 + 0.0036), (R - 0.0001, z0 + 0.0055),
            (R, z0 + 0.0070), (R - 0.0004, z1 - 0.0028), (R - 0.0015, z1 - 0.0010), (R - 0.0040, z1),
            (0.066, z1), (0.0655, z1 - 0.0004), (0.0625, z1 - 0.0004), (0.062, z1), (0.0, z1)]
    parts['lamp_base'] = (lathe([(r, h - z0) for r, h in prof], Matrix.Translation(Vector((BASE_C.x, BASE_C.y, z0))), 96), WP, 40)

    # ---- lower column: one straight vertical rounded-rectangle prism as wide as the bar pair
    half = BR_SPACING / 2
    t2 = T3.to_2d()

    def rrect(off, n=6):
        """Plan outline (CCW) of the column section grown by `off`: COL_W along F, COL_D across."""
        a, b = COL_W / 2 + off, COL_D / 2 + off
        r = COL_CORNER + off
        pts = []
        for cf, ct, a0 in ((a - r, -b + r, -math.pi / 2), (a - r, b - r, 0.0), (-a + r, b - r, math.pi / 2),
                           (-a + r, -b + r, math.pi)):
            for k in range(n + 1):
                ang = a0 + math.pi / 2 * k / n
                pts.append(col_xy + F2 * (cf + r * math.cos(ang)) + t2 * (ct + r * math.sin(ang)))
        return pts
    floor_z = AXLE_Z - HUB_R - FLOOR_GAP
    levels = [(z1 - 0.004, 0.0024), (z1 + 0.0004, 0.0024), (z1 + 0.0018, 0.0017), (z1 + 0.0030, 0.0008),
              (z1 + 0.0040, 0.0), (floor_z, 0.0)]
    bm = bmesh.new()
    rings = [[bm.verts.new((q.x, q.y, zz)) for q in rrect(off)] for zz, off in levels]
    n = len(rings[0])
    for r_ in range(len(rings) - 1):
        for j in range(n):
            bm.faces.new([rings[r_][j], rings[r_][(j + 1) % n], rings[r_ + 1][(j + 1) % n], rings[r_ + 1][j]])
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    parts['lamp_column'] = (bm, WP, 40)

    # ---- clevis: the column's top continues as two cheeks either side of a slot, tops arched about the axle
    def cheek(sign):
        """One clevis cheek: the column section clipped to |t| >= slot/2, top arched about the axle."""
        bm = bmesh.new()
        t_in, t_out = SLOT_W / 2, COL_D / 2
        a, b, r = COL_W / 2, COL_D / 2, COL_CORNER

        def f_lim(tt):
            e_ = max(0.0, tt - (b - r))
            return a - r + math.sqrt(max(r * r - e_ * e_, 0.0))

        def arch(f_):
            f_ = max(-CHEEK_R, min(CHEEK_R, f_))
            return AXLE_Z + math.sqrt(max(CHEEK_R ** 2 - f_ ** 2, 0.0))
        m, nt = 40, 5
        grid_b, grid_t = [], []
        for i in range(nt + 1):
            tt = t_in + (t_out - t_in) * i / nt
            fl = f_lim(tt)
            rowb, rowt = [], []
            for k in range(m + 1):
                f_ = -fl + 2 * fl * k / m
                q = col_xy + F2 * f_ + t2 * (sign * tt)
                rowb.append(bm.verts.new((q.x, q.y, floor_z)))
                rowt.append(bm.verts.new((q.x, q.y, arch(f_))))
            grid_b.append(rowb)
            grid_t.append(rowt)
        for i in range(nt):
            for k in range(m):
                bm.faces.new([grid_t[i][k], grid_t[i][k + 1], grid_t[i + 1][k + 1], grid_t[i + 1][k]])
                bm.faces.new([grid_b[i][k + 1], grid_b[i][k], grid_b[i + 1][k], grid_b[i + 1][k + 1]])
        for k in range(m):
            for i_face in (0, nt):
                bm.faces.new([grid_b[i_face][k], grid_b[i_face][k + 1], grid_t[i_face][k + 1], grid_t[i_face][k]])
        for i in range(nt):
            for k_end in (0, m):
                bm.faces.new([grid_b[i][k_end], grid_b[i + 1][k_end], grid_t[i + 1][k_end], grid_t[i][k_end]])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return bm
    cl = bmesh.new()
    for sg in (1, -1):
        cb = cheek(sg)
        me_tmp = bpy.data.meshes.new('tmp')
        cb.to_mesh(me_tmp)
        cb.free()
        cl.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    parts['lamp_clevis'] = (cl, WP, 40)
    # ---- axle through both cheeks with knob caps on the outside (static, belongs to the column)
    axle_c = Vector((col_xy.x, col_xy.y, AXLE_Z))
    ab = lathe([(0.0, -COL_D / 2 - 0.001), (AXLE_R, -COL_D / 2 - 0.001), (AXLE_R, COL_D / 2 + 0.001),
                (0.0, COL_D / 2 + 0.001)], frame(axle_c, T3), 24)
    for sgn in (1, -1):
        fr = frame(axle_c + T3 * (sgn * COL_D / 2), T3 * sgn)
        kprof = [(0.0, 0.0042), (0.0030, 0.0042), (0.0034, 0.0038), (0.0038, 0.0042), (KNOB_R - 0.0015, 0.0042),
                 (KNOB_R - 0.0003, 0.0034), (KNOB_R, 0.0022), (KNOB_R, 0.0), (0.0, 0.0)]
        kb = lathe(kprof, fr, 48)
        me_tmp = bpy.data.meshes.new('tmp')
        kb.to_mesh(me_tmp)
        kb.free()
        ab.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    parts['lamp_axle'] = (ab, WP, 40)
    # ---- hub: round disc on the axle between the cheeks, carries both bar roots (rotates with the arm)
    hprof_h = [(0.0, -HUB_T / 2), (HUB_R - 0.0012, -HUB_T / 2), (HUB_R, -HUB_T / 2 + 0.0012),
               (HUB_R, HUB_T / 2 - 0.0012), (HUB_R - 0.0012, HUB_T / 2), (0.0, HUB_T / 2)]
    parts['lamp_hub'] = (lathe(hprof_h, frame(axle_c, T3), 64), WP, 40)

    # ---- two identical parallel branches: vertical run, one smooth forward arc, straight lean
    def branch_path(root_xy, z_top):
        pts = []
        z_start = AXLE_Z + 0.004                              # rooted inside the hub
        z_bend = SPLIT_Z1 + BR_RISE0
        root = Vector((root_xy.x, root_xy.y, 0))
        for k in range(3):
            pts.append(root + Z * (z_start + (z_bend - z_start) * k / 2))
        c = root + Z * z_bend + F3 * BR_BEND_R               # arc centre, forward of the branch
        n_arc = 16
        for k in range(1, n_arc + 1):
            a = BR_LEAN * k / n_arc
            pts.append(c - F3 * (BR_BEND_R * math.cos(a)) + Z * (BR_BEND_R * math.sin(a)))
        p_end = pts[-1]
        d = (F3 * math.sin(BR_LEAN) + Z * math.cos(BR_LEAN)).normalized()
        L = (z_top - p_end.z) / d.z
        n_run = 6
        for k in range(1, n_run + 1):
            pts.append(p_end + d * (L * k / n_run))
        return pts, p_end, d, L

    yoke_z0 = head_mid - YOKE_H / 2
    yoke_z1 = head_mid + YOKE_H / 2
    rb, rf = col_xy - F2 * half, col_xy + F2 * half
    pb, pe_b, d_b, L_b = branch_path(rb, yoke_z0 + 0.008)
    pf, pe_f, d_f, L_f = branch_path(rf, yoke_z0 + 0.008)
    parts['lamp_branch_rear'] = (tube(pb, BR_R, 32), WP, 40)
    parts['lamp_branch_front'] = (tube(pf, BR_R, 32), WP, 40)
    travel = (pf[-1] - Vector((rf.x, rf.y, pf[-1].z))).to_2d().length   # forward travel of each branch
    yoke_xy = col_xy + F2 * ((pf[-1].to_2d() - rf).dot(F2))
    parts['lamp_yoke'] = (stadium_block(yoke_xy, half, BLOCK_R, yoke_z0, yoke_z1, 0.006, F2), WP, 40)
    # pivot caps on both sides of the yoke's front end (the head pivot)
    piv = Vector((yoke_xy.x, yoke_xy.y, head_mid)) + F3 * half
    for sgn, nm in ((1, 'l'), (-1, 'r')):
        fr = frame(piv + T3 * (sgn * (BLOCK_R - 0.0015)), T3 * sgn)
        prof = [(0.0, 0.0028), (0.0026, 0.0028), (0.0030, 0.0025), (0.0036, 0.0028), (0.0078, 0.0028),
                (0.0088, 0.0021), (0.0094, 0.0010), (0.0094, 0.0), (0.0, 0.0)]
        parts['lamp_pivot_' + nm] = (lathe(prof, fr, 40), WP, 40)
    # ---- short straight neck, then the head
    neck0 = Vector((yoke_xy.x, yoke_xy.y, head_mid)) + F3 * (half + BLOCK_R)
    neck1 = neck0 + F3 * NECK_LEN
    nprof = [(0.0, -0.006), (NECK_R, -0.006), (NECK_R, NECK_LEN + 0.006), (0.0, NECK_LEN + 0.006)]
    parts['lamp_neck'] = (lathe(nprof, frame(neck0, F3), 32), WP, 40)
    H = neck1 + F3 * HEAD_R
    head_c = Vector((H.x, H.y, HEAD_BOTTOM))
    e = HEAD_EDGE
    hprof = [(0.0, 0.0), (HEAD_R - e, 0.0)]
    hprof += [(HEAD_R - e + e * math.sin(a), e - e * math.cos(a)) for a in [math.pi / 2 * k / 6 for k in range(1, 7)]]
    hprof += [(HEAD_R, HEAD_T - e)]
    hprof += [(HEAD_R - e + e * math.cos(a), HEAD_T - e + e * math.sin(a)) for a in [math.pi / 2 * k / 6 for k in range(1, 6)]]
    hprof += [(HEAD_R - e, HEAD_T), (HEAD_R - 0.010, HEAD_T), (HEAD_R - 0.0104, HEAD_T - 0.0003),
              (HEAD_R - 0.0116, HEAD_T - 0.0003), (HEAD_R - 0.012, HEAD_T), (0.0, HEAD_T)]
    parts['lamp_head'] = (lathe(hprof, Matrix.Translation(head_c), 128), WP, 35)
    fr_d = frame(head_c, -Z, xhint=F3)
    bez = [(DIFF_R - 0.0012, 0.0024), (DIFF_R + 0.0005, 0.0031), (DIFF_R + 0.0030, 0.0035),
           (DIFF_R + 0.0046, 0.0026), (DIFF_R + 0.0052, 0.0008), (DIFF_R + 0.0052, -0.0006),
           (DIFF_R - 0.0012, -0.0006), (DIFF_R - 0.0012, 0.0024)]
    parts['lamp_diffuser_bezel'] = (lathe(bez, fr_d, 96), WP, 50)
    disc = [(0.0, 0.0028), (DIFF_R * 0.5, 0.0027), (DIFF_R * 0.85, 0.0025), (DIFF_R - 0.0008, 0.0022),
            (DIFF_R - 0.0008, 0.0002), (0.0, 0.0002)]
    parts['lamp_diffuser_disc'] = (lathe(disc, fr_d, 96), DM, 50)

    # ---- objects (unit scale, root at the base centre)
    root = bpy.data.objects.new('NEW_lamp_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.05
    root.location = Vector((BASE_C.x, BASE_C.y, BASE_Z0))
    coll.objects.link(root)
    inv = Matrix.Translation(-root.location)
    pivot = bpy.data.objects.new('NEW_lamp_pivot', None)
    pivot.empty_display_type = 'ARROWS'
    pivot.empty_display_size = 0.04
    coll.objects.link(pivot)
    bpy.context.view_layer.update()
    pivot.parent = root
    pivot.matrix_parent_inverse = Matrix.Identity(4)
    pivot.location = axle_c - root.location                 # root has no rotation/scale
    pivot.rotation_mode = 'AXIS_ANGLE'
    pivot.rotation_axis_angle = (0.0, T3.x, T3.y, T3.z)   # tilt = change the angle (rad) about the axle
    bpy.context.view_layer.update()
    ARM = {'lamp_hub', 'lamp_branch_rear', 'lamp_branch_front', 'lamp_yoke', 'lamp_pivot_l', 'lamp_pivot_r',
           'lamp_neck', 'lamp_head', 'lamp_diffuser_bezel', 'lamp_diffuser_disc'}
    tris, objs = {}, {}
    for name, (bm, mat, ang) in parts.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
        bm.transform(inv)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(ang))
        o = bpy.data.objects.new(name, me)
        coll.objects.link(o)
        par = pivot if name in ARM else root
        o.parent = par
        o.matrix_parent_inverse = par.matrix_world.inverted() @ root.matrix_world
        objs[name] = o
        tris[name] = sum(len(p.vertices) - 2 for p in me.polygons)
    ld = bpy.data.lights.new('LAMP_disk', 'AREA')
    ld.shape = 'DISK'
    ld.size = 2 * DIFF_R
    ld.energy = DISK_ENERGY
    ld.color = WARM
    ld.spread = DISK_SPREAD
    lo = bpy.data.objects.new('LAMP_disk', ld)
    coll.objects.link(lo)
    lo.parent = pivot
    lo.matrix_world = Matrix.Translation(head_c - Z * 0.0034)
    bpy.context.view_layer.update()

    # ---- numeric checks (world space, after parenting)
    def wv(o):
        return [o.matrix_world @ v.co for v in o.data.vertices]
    checks = {}
    checks['world_scales'] = sorted({tuple(round(x, 6) for x in o.matrix_world.to_scale()) for o in coll.objects})
    cvv = wv(objs['lamp_column'])
    zs = sorted({round(v.z, 6) for v in cvv})
    ring = lambda zz: [v for v in cvv if abs(v.z - zz) < 1e-6]
    c_lo = sum((v.to_2d() for v in ring(zs[4])), Vector((0, 0))) / len(ring(zs[4]))
    c_hi = sum((v.to_2d() for v in ring(zs[-1])), Vector((0, 0))) / len(ring(zs[-1]))
    checks['column_tilt_deg'] = round(math.degrees(math.atan2((c_hi - c_lo).length, zs[-1] - zs[4])), 5)
    w_f = max(v.to_2d().dot(F2) for v in ring(zs[-1])) - min(v.to_2d().dot(F2) for v in ring(zs[-1]))
    w_t = max(v.to_2d().dot(T3.to_2d()) for v in ring(zs[-1])) - min(v.to_2d().dot(T3.to_2d()) for v in ring(zs[-1]))
    checks['column_section_mm'] = (round(w_f * 1000, 2), round(w_t * 1000, 2))
    checks['bar_pair_outer_width_mm'] = round((BR_SPACING + 2 * BR_R) * 1000, 2)
    bv = wv(objs['lamp_base'])
    checks['base_thickness_mm'] = round((max(v.z for v in bv) - min(v.z for v in bv)) * 1000, 2)
    from mathutils.bvhtree import BVHTree

    def tree(names):
        V, Fc = [], []
        dg = bpy.context.evaluated_depsgraph_get()
        for nm_ in names:
            ev = objs[nm_].evaluated_get(dg)
            m_ = ev.to_mesh()
            base_i = len(V)
            V += [ev.matrix_world @ v.co for v in m_.vertices]
            Fc += [tuple(i + base_i for i in p_.vertices) for p_ in m_.polygons]
            ev.to_mesh_clear()
        return V, BVHTree.FromPolygons(V, Fc)
    joint = {}
    for ang_deg in (0.0, -15.0, 15.0):
        pivot.rotation_axis_angle = (math.radians(ang_deg), T3.x, T3.y, T3.z)
        bpy.context.view_layer.update()
        mv, mt = tree(['lamp_hub', 'lamp_branch_rear', 'lamp_branch_front'])
        sv, st_ = tree(['lamp_clevis', 'lamp_column', 'lamp_axle'])
        # the axle passes through the hub by design: measure hub/bars against cheeks + column only
        sv2, st2 = tree(['lamp_clevis', 'lamp_column'])
        d = min(st2.find_nearest(v)[3] for v in mv)
        joint[ang_deg] = round(d * 1000, 3)
    pivot.rotation_axis_angle = (0.0, T3.x, T3.y, T3.z)
    bpy.context.view_layer.update()
    checks['joint_clearance_mm_at_0_-15_+15deg'] = joint
    # branch straight runs: axis direction of each, angle between them, straightness (ring-centre deviation)
    def run_axis(path, n_run=6):
        run = path[-(n_run + 1):]
        d = (run[-1] - run[0]).normalized()
        dev = max(((p - run[0]) - d * (p - run[0]).dot(d)).length for p in run)
        return d, dev
    da, deva = run_axis(pb)
    dfr, devf = run_axis(pf)
    checks['branch_lean_deg'] = (round(math.degrees(da.angle(Z)), 4), round(math.degrees(dfr.angle(Z)), 4))
    checks['branches_parallel_deg'] = round(math.degrees(da.angle(dfr)), 6)
    checks['branch_run_straightness_mm'] = (round(deva * 1000, 5), round(devf * 1000, 5))
    checks['branch_lean_in_plane_of_movement'] = round(abs(da.dot(T3)), 6)   # 0 = no sideways twist
    checks['branch_spacing_mm'] = round((pf[-1] - pb[-1]).length * 1000, 3)
    hv = wv(objs['lamp_head'])
    rr = lambda v: (v.to_2d() - head_c.to_2d()).length
    top = [v.z for v in hv if v.z > head_c.z + HEAD_T / 2 and rr(v) < HEAD_R - 0.013]
    bot = [v.z for v in hv if v.z < head_c.z + HEAD_T / 2 and rr(v) < HEAD_R - HEAD_EDGE + 1e-6]
    checks['head_top_flatness_mm'] = round((max(top) - min(top)) * 1000, 4)
    checks['head_bottom_flatness_mm'] = round((max(bot) - min(bot)) * 1000, 4)
    xs = [v.x for v in hv]
    ys = [v.y for v in hv]
    ext_f = max(v.to_2d().dot(F2) for v in hv) - min(v.to_2d().dot(F2) for v in hv)
    ext_t = max(v.to_2d().dot(T3.to_2d()) for v in hv) - min(v.to_2d().dot(T3.to_2d()) for v in hv)
    checks['head_diam_world_x_y_mm'] = (round((max(xs) - min(xs)) * 1000, 3), round((max(ys) - min(ys)) * 1000, 3))
    checks['head_diam_along_across_mm'] = (round(ext_f * 1000, 3), round(ext_t * 1000, 3))
    rim = [rr(v) for v in hv if abs(v.z - (head_c.z + HEAD_T - e)) < 1e-6]
    checks['head_roundness_mm'] = round((max(rim) - min(rim)) * 1000, 4)
    nv = wv(objs['lamp_neck'])
    checks['neck_visible_len_mm'] = round(NECK_LEN * 1000, 2)
    checks['neck_level_mm'] = round((max(v.z for v in nv) - min(v.z for v in nv) - 2 * NECK_R) * 1000, 4)
    print('CHECKS', checks)

    meta = dict(pivot=list(axle_c), pivot_axis=list(T3), neck_start=list(neck0), neck_end=list(neck1), neck_dir=list(F3), neck_across=list(T3),
                neck_r=NECK_R, head_centre=list(head_c), head_r=HEAD_R, head_t=HEAD_T,
                yoke_centre=[yoke_xy.x, yoke_xy.y, head_mid], block_r=BLOCK_R, branch_r=BR_R,
                diffuser_r=DIFF_R)
    with open(OUT_META, 'w') as f:
        json.dump(meta, f, indent=1)
    print(f'LAYOUT column {tuple(round(x, 4) for x in col_xy)} axle z {AXLE_Z} '
          f'yoke {tuple(round(x, 4) for x in yoke_xy)} neck {tuple(round(x, 4) for x in neck0)} -> '
          f'{tuple(round(x, 4) for x in neck1)} head {tuple(round(x, 4) for x in head_c)} travel {travel * 1000:.1f}mm')
    total = sum(tris.values())
    print('TRIS', total, tris)
    return dict(scene=scene, coll=coll, head_c=head_c, col_xy=col_xy, tris=tris, total=total, checks=checks,
                pivot=pivot, axle=axle_c,
                yoke=Vector((yoke_xy.x, yoke_xy.y, head_mid)))


# ------------------------------------------------------------------------------ previews
def previews(b):
    scene = b['scene']
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'CUDA'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPTIX'
    except TypeError:
        pass
    scene.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new('grey')
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.42, 0.42, 0.42, 1)
    bg.inputs['Strength'].default_value = 0.6
    scene.world = w
    tmp = []
    c = BASE_C
    desk = bpy.data.meshes.new('prev_desk')
    desk.from_pydata([(c.x - 0.9, c.y - 0.9, 0.735), (c.x + 0.9, c.y - 0.9, 0.735), (c.x + 0.9, c.y + 0.9, 0.735),
                      (c.x - 0.9, c.y + 0.9, 0.735)], [], [(0, 1, 2, 3)])
    dm = bpy.data.materials.new('prev_desk')
    dm.use_nodes = True
    principled(dm).inputs['Base Color'].default_value = (0.55, 0.42, 0.33, 1)
    desk.materials.append(dm)
    do = bpy.data.objects.new('prev_desk', desk)
    scene.collection.objects.link(do)
    tmp.append(do)
    mid = Vector((c.x, c.y, 0.97)) + F3 * 0.05

    def light(name, off, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        o = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(o)
        o.location = mid + Vector(off)
        o.rotation_euler = (mid - o.location).to_track_quat('-Z', 'Y').to_euler()
        tmp.append(o)
    light('key', (0.8, -0.9, 0.7), 90, 0.6)
    light('fill', (-0.9, -0.5, 0.2), 30, 0.9)
    light('rim', (-0.3, 0.9, 0.6), 70, 0.5)
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam
    tmp.append(cam)

    def shot(loc, target, lens, name, res=(1280, 800), ortho=None):
        scene.render.resolution_x, scene.render.resolution_y = res
        cam.data.type = 'ORTHO' if ortho else 'PERSP'
        if ortho:
            cam.data.ortho_scale = ortho
        cam.location = loc
        cam.data.lens = lens
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, name)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', name)
    # side view: looking across the plane of movement (along T3)
    shot(mid + T3 * 1.4, mid, 50, 'lamp_side.png', (1000, 1100), ortho=0.56)
    # close-up of the clevis joint (3/4 so the slot, hub, axle and knob read)
    ax = b['axle']
    shot(ax + (T3 * 0.75 + F3 * 0.35).normalized() * 0.23 + Vector((0, 0, 0.07)), ax + Vector((0, 0, 0.004)), 50,
         'lamp_joint.png', (1100, 900))
    shot(SEAT, mid + Vector((0, 0, 0.06)), 40, 'lamp_seat.png')
    # tilt proof: rotate NEW_lamp_pivot -15 deg about the axle, medals attached to it
    med_objs = []
    mb = os.path.join(PARTS, 'medals.blend')
    if os.path.exists(mb):
        with bpy.data.libraries.load(mb, link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None:
                scene.collection.objects.link(o)
                med_objs.append(o)
        bpy.context.view_layer.update()
        mr = bpy.data.objects.get('NEW_medals_root')
        if mr:
            mw = mr.matrix_world.copy()
            mr.parent = b['pivot']
            mr.matrix_world = mw
    pv = b['pivot']
    ang0 = pv.rotation_axis_angle[:]
    pv.rotation_axis_angle = (math.radians(-15), ang0[1], ang0[2], ang0[3])
    bpy.context.view_layer.update()
    shot(mid + T3 * 1.4, mid, 50, 'lamp_tilt_-15.png', (1000, 1100), ortho=0.60)
    pv.rotation_axis_angle = ang0
    for o in med_objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.materials.remove(dm)


def finish(b):
    for o in list(bpy.context.scene.objects):
        if o.name not in b['coll'].all_objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    print('SAVED', OUT_BLEND)


if __name__ == '__main__':
    b = build()
    if not NO_RENDER:
        previews(b)
    finish(b)
    print('DONE')
