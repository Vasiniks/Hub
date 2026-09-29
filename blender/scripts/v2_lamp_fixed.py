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
BASE_Z0, BASE_Z1 = 0.735, 0.7669

# ---- stem / branches (original twin members: 36.6 mm apart along the lean, lean 12.6 deg)
COL_R = 0.013
COL_BACK = 0.030               # column axis sits this far behind the base centre (head reaches forward)
SPLIT_Z0, SPLIT_Z1 = 0.940, 0.970   # junction block (the split), about mid-height of the lamp
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
    prof = [(0.0, z0), (R - 0.009, z0), (R - 0.0075, z0 + 0.0008), (R - 0.0070, z0 + 0.0040),
            (R - 0.0030, z0 + 0.0048), (R - 0.0006, z0 + 0.0062), (R, z0 + 0.0085),
            (R, z1 - 0.0045), (R - 0.0012, z1 - 0.0013), (R - 0.0040, z1),
            (0.056, z1), (0.0555, z1 - 0.0004), (0.0525, z1 - 0.0004), (0.052, z1), (0.0, z1)]
    parts['lamp_base'] = (lathe([(r, h - z0) for r, h in prof], Matrix.Translation(Vector((BASE_C.x, BASE_C.y, z0))), 96), WP, 40)

    # ---- lower column: one straight vertical cylinder, boot at the base, into the junction block
    cprof = [(0.0, -0.006), (COL_R + 0.0035, -0.006), (COL_R + 0.0035, 0.0012), (COL_R + 0.0029, 0.0026),
             (COL_R + 0.0014, 0.0036), (COL_R + 0.0002, 0.0042), (COL_R, 0.0050),
             (COL_R, SPLIT_Z0 + 0.006 - z1), (0.0, SPLIT_Z0 + 0.006 - z1)]
    parts['lamp_column'] = (lathe(cprof, Matrix.Translation(Vector((col_xy.x, col_xy.y, z1))), 48), WP, 40)

    # ---- junction (the split): stadium block holding the two branch roots, centred on the column
    half = BR_SPACING / 2
    parts['lamp_split'] = (stadium_block(col_xy, half, BLOCK_R, SPLIT_Z0, SPLIT_Z1, 0.005, F2), WP, 40)

    # ---- two identical parallel branches: vertical run, one smooth forward arc, straight lean
    def branch_path(root_xy, z_top):
        pts = []
        z_start = SPLIT_Z1 - 0.006
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
        o.parent = root
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
    lo.parent = root
    lo.matrix_world = Matrix.Translation(head_c - Z * 0.0034)
    bpy.context.view_layer.update()

    # ---- numeric checks (world space, after parenting)
    def wv(o):
        return [o.matrix_world @ v.co for v in o.data.vertices]
    checks = {}
    checks['world_scales'] = sorted({tuple(round(x, 6) for x in o.matrix_world.to_scale()) for o in coll.objects})
    cv = [v for v in wv(objs['lamp_column']) if abs((v.to_2d() - col_xy).length - COL_R) < 2e-5 and v.z > z1 + 0.0045]
    zs = sorted({round(v.z, 6) for v in cv})
    c_lo = sum((v.to_2d() for v in cv if round(v.z, 6) == zs[0]), Vector((0, 0))) / len([v for v in cv if round(v.z, 6) == zs[0]])
    c_hi = sum((v.to_2d() for v in cv if round(v.z, 6) == zs[-1]), Vector((0, 0))) / len([v for v in cv if round(v.z, 6) == zs[-1]])
    checks['column_tilt_deg'] = round(math.degrees(math.atan2((c_hi - c_lo).length, zs[-1] - zs[0])), 5)
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

    meta = dict(neck_start=list(neck0), neck_end=list(neck1), neck_dir=list(F3), neck_across=list(T3),
                neck_r=NECK_R, head_centre=list(head_c), head_r=HEAD_R, head_t=HEAD_T,
                yoke_centre=[yoke_xy.x, yoke_xy.y, head_mid], block_r=BLOCK_R, branch_r=BR_R,
                diffuser_r=DIFF_R)
    with open(OUT_META, 'w') as f:
        json.dump(meta, f, indent=1)
    print(f'LAYOUT column {tuple(round(x, 4) for x in col_xy)} split z [{SPLIT_Z0},{SPLIT_Z1}] '
          f'yoke {tuple(round(x, 4) for x in yoke_xy)} neck {tuple(round(x, 4) for x in neck0)} -> '
          f'{tuple(round(x, 4) for x in neck1)} head {tuple(round(x, 4) for x in head_c)} travel {travel * 1000:.1f}mm')
    total = sum(tris.values())
    print('TRIS', total, tris)
    return dict(scene=scene, coll=coll, head_c=head_c, col_xy=col_xy, tris=tris, total=total, checks=checks,
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
    # front view: looking back along the plane of movement (from the head side)
    shot(mid + F3 * 1.4, mid, 50, 'lamp_front.png', (1000, 1100), ortho=0.56)
    three_q = (F3 * 0.55 + T3 * 0.85).normalized()
    shot(mid + three_q * 0.95 + Vector((0, 0, 0.25)), mid, 40, 'lamp_34.png', (900, 1100))
    shot(SEAT, mid + Vector((0, 0, 0.06)), 40, 'lamp_seat.png')
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
