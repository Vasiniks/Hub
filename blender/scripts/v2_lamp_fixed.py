"""
v2_lamp_fixed.py -- the desk lamp, structurally fixed, as a standalone part.

    blender -b --factory-startup --python blender/scripts/v2_lamp_fixed.py -- [--no-render]

Starts from the existing lamp meshes in blender/scene/room.blend (opened READ-ONLY, never saved):
  lamp003   -> lamp_arm        (twin arm bars, collar, top bracket; from the owner's STL)
  lamp003_1 -> lamp_base
  Cylinder  -> lamp_head       (the long horizontal head bar)
  Cylinder_1-> lamp_head_trim
and fixes what was broken:
  * the hair-thin stem between base and collar is removed and replaced by a solid column that
    plugs into the base socket (its outline is the socket's own outline) and blends into the
    collar underside, with a flared trim ring where it enters the base;
  * the open socket hole in the base top and the open ends of the head are capped;
  * a pivot pin with caps through the collar (arm pivot) and a hinge barrel joining the arm's top
    bracket to the head (head pivot), so every part connects physically;
  * everything is white plastic (lamp_white_plastic);
  * the CIRCULAR light: round diffuser disc + bezel + DISK area light, fitted flush to the head
    underside (it previously floated ~16 mm below it) and tilted with the head.
Output: blender/scene/parts/lamp.blend, collection NEW_lamp under root NEW_lamp_root, ROOM coordinates.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.geometry import convex_hull_2d

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ROOM = os.path.join(REPO, 'blender', 'scene', 'room.blend')
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'lamp.blend')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
SEAT = Vector((0.0, -0.16, 1.175))
Z = Vector((0, 0, 1))

# circular light (values from v2_lamp.py)
DIFF_R = 0.0305                 # v2_lamp used 0.034; its bezel then overhung the 73.6 mm-wide head
WARM = (1.0, 0.86, 0.68)
DISK_ENERGY = 7.0
DISK_SPREAD = math.radians(75)
DIFF_XY = Vector((-0.6385, 0.9425))


# ------------------------------------------------------------------------------ read room (read-only)
def read_room():
    bpy.ops.wm.open_mainfile(filepath=ROOM, load_ui=False)
    out = {}
    for n in ('lamp003', 'lamp003_1', 'Cylinder', 'Cylinder_1'):
        o = bpy.data.objects[n]
        mw = o.matrix_world
        out[n] = dict(verts=[tuple(mw @ v.co) for v in o.data.vertices],
                      faces=[tuple(p.vertices) for p in o.data.polygons])
    return out


# ------------------------------------------------------------------------------ helpers
def bm_from(d):
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in d['verts']]
    for f in d['faces']:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    return bm


def boundary_loops(bm):
    edges = [e for e in bm.edges if e.is_boundary]
    seen, loops = set(), []
    for e in edges:
        if e in seen:
            continue
        st, comp = [e], []
        seen.add(e)
        while st:
            x = st.pop()
            comp.append(x)
            for v in x.verts:
                for y in v.link_edges:
                    if y.is_boundary and y not in seen:
                        seen.add(y)
                        st.append(y)
        loops.append(comp)
    return loops


def cross2(a, b):
    return a.x * b.y - a.y * b.x


def ray_poly(poly, o, d):
    best = None
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        e = b - a
        den = cross2(d, e)
        if abs(den) < 1e-12:
            continue
        t = cross2(a - o, e) / den
        u = cross2(a - o, d) / den
        if t > 0 and -1e-6 <= u <= 1 + 1e-6:
            best = t if best is None else min(best, t)
    return best


def star_resample(pts2, centre, n=48):
    """Resample a star-shaped outline (points around centre) to n points by angle."""
    ordered = sorted(pts2, key=lambda p: math.atan2(p.y - centre.y, p.x - centre.x))
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        d = Vector((math.cos(a), math.sin(a)))
        t = ray_poly(ordered, centre, d)
        out.append(centre + d * t)
    return out


def convex(pts2):
    idx = convex_hull_2d(pts2)
    return [pts2[i] for i in idx]


def slice_hull(bm_src, z):
    bm = bm_src.copy()
    r = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, z),
                               plane_no=(0, 0, 1))
    pts = [v.co.to_2d() for v in r['geom_cut'] if isinstance(v, bmesh.types.BMVert)]
    bm.free()
    return convex(pts)


def centroid2(poly):
    A = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        c = cross2(p, q)
        A += c
        cx += (p.x + q.x) * c
        cy += (p.y + q.y) * c
    A *= 0.5
    return Vector((cx / (6 * A), cy / (6 * A)))


def smooth01(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def loft(rings, cap_bottom=True, cap_top=True):
    """rings: list of lists of Vector3 (same count). Returns bmesh."""
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(rings[0])
    for r in range(len(vr) - 1):
        for k in range(n):
            bm.faces.new([vr[r][k], vr[r][(k + 1) % n], vr[r + 1][(k + 1) % n], vr[r + 1][k]])
    if cap_bottom:
        bm.faces.new(list(reversed(vr[0])))
    if cap_top:
        bm.faces.new(vr[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def lathe_frame(prof, frame, seg=48, cap=True):
    """prof: (r, h) along local Z; frame: 4x4 world matrix. Returns bmesh."""
    bm = bmesh.new()
    rings = []
    for (r, h) in prof:
        if r < 1e-7:
            rings.append([bm.verts.new(frame @ Vector((0, 0, h)))])
        else:
            rings.append([bm.verts.new(frame @ Vector((r * math.cos(2 * math.pi * j / seg),
                                                        r * math.sin(2 * math.pi * j / seg), h)))
                          for j in range(seg)])
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


def frame_from_axis(origin, axis):
    axis = axis.normalized()
    x = axis.orthogonal().normalized()
    y = axis.cross(x)
    return Matrix(((x.x, y.x, axis.x, origin.x), (x.y, y.y, axis.y, origin.y),
                   (x.z, y.z, axis.z, origin.z), (0, 0, 0, 1)))


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
    # micro roughness variation, 0.30..0.36 around the 0.33 target
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
    src = read_room()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    coll = bpy.data.collections.new('NEW_lamp')
    scene.collection.children.link(coll)
    WP = white_plastic()
    DM = diffuser_mat()

    arm = bm_from(src['lamp003'])
    base = bm_from(src['lamp003_1'])
    head = bm_from(src['Cylinder'])
    trim = bm_from(src['Cylinder_1'])

    base_top = max(v.co.z for v in base.verts)
    base_bot = min(v.co.z for v in base.verts)
    btop = [v.co for v in base.verts if v.co.z > base_top - 0.002]
    base_c = Vector(((min(p.x for p in btop) + max(p.x for p in btop)) / 2,
                     (min(p.y for p in btop) + max(p.y for p in btop)) / 2))

    # ---- base socket: remember its outline, then cap it
    loops = boundary_loops(base)
    sock = max(loops, key=len)
    sock_pts = [v.co.to_2d() for e in sock for v in e.verts]
    sock_c = sum(sock_pts, Vector((0, 0))) / len(sock_pts)
    bmesh.ops.holes_fill(base, edges=[e for e in base.edges if e.is_boundary], sides=0)
    bmesh.ops.triangulate(base, faces=[f for f in base.faces if len(f.verts) > 4])
    print(f'BASE top {base_top:.4f} centre {tuple(round(x, 4) for x in base_c)}; socket centre '
          f'{tuple(round(x, 4) for x in sock_c)}, {len(sock)} edges capped')

    # ---- arms: measure collar, then remove the hair-thin stem below it
    collar_pts = [v.co for v in arm.verts if 0.8 < v.co.z < 1.0]
    collar_top = max(p.z for p in collar_pts)
    collar_bot = min(p.z for p in collar_pts)
    collar_foot = slice_hull(arm, collar_bot + 0.004)

    def outside_collar(f):
        c = f.calc_center_median()
        if c.z < collar_bot - 0.0008:
            return True
        if c.z < collar_bot + 0.0015:
            inside = all(cross2(collar_foot[(i + 1) % len(collar_foot)] - collar_foot[i],
                                c.to_2d() - collar_foot[i]) >= -0.0005 for i in range(len(collar_foot)))
            return not inside
        return False
    stem_faces = [f for f in arm.faces if outside_collar(f)]
    stem_xy = sum((f.calc_center_median().to_2d() for f in stem_faces), Vector((0, 0))) / max(1, len(stem_faces))
    # the stem's attachment tab under the collar (a paper-thin sliver) goes too; the column covers it
    stem_faces += [f for f in arm.faces if f not in stem_faces and f.calc_center_median().z < collar_bot + 0.002
                   and (f.calc_center_median().to_2d() - stem_xy).length < 0.012]
    stem_verts = {v for f in stem_faces for v in f.verts}
    bmesh.ops.delete(arm, geom=stem_faces, context='FACES_ONLY')
    loose = [v for v in stem_verts if v.is_valid and not v.link_faces]
    bmesh.ops.delete(arm, geom=loose, context='VERTS')
    print(f'COLLAR z [{collar_bot:.4f}, {collar_top:.4f}], removed {len(stem_faces)} stem faces')

    collar_low = slice_hull(arm, collar_bot + 0.004)
    collar_mid = slice_hull(arm, (collar_bot + collar_top) / 2)
    cc = centroid2(collar_mid)
    # collar axes: longest hull edge = a (along the arm bundle's wide side)
    best = max(range(len(collar_mid)), key=lambda i: (collar_mid[(i + 1) % len(collar_mid)] - collar_mid[i]).length)
    a_dir = (collar_mid[(best + 1) % len(collar_mid)] - collar_mid[best]).normalized()
    b_dir = Vector((-a_dir.y, a_dir.x))

    # ---- head: cap its open ends
    for bmh in (head, trim):
        bnd = [e for e in bmh.edges if e.is_boundary]
        if bnd:
            bmesh.ops.holes_fill(bmh, edges=bnd, sides=0)
            bmesh.ops.triangulate(bmh, faces=[f for f in bmh.faces if len(f.verts) > 4])

    # head frame: s along the bar (toward its free tip), t across, from PCA of the head
    hv = [v.co for v in head.verts]
    hc = Vector((sum(p.x for p in hv) / len(hv), sum(p.y for p in hv) / len(hv)))
    sxx = sum((p.x - hc.x) ** 2 for p in hv)
    syy = sum((p.y - hc.y) ** 2 for p in hv)
    sxy = sum((p.x - hc.x) * (p.y - hc.y) for p in hv)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ha = Vector((math.cos(ang), math.sin(ang)))
    if ha.dot(SEAT.to_2d() - hc) < 0:
        ha = -ha
    hb = Vector((-ha.y, ha.x))

    def hst(p):
        q = p.to_2d() - hc
        return q.dot(ha), q.dot(hb)

    # ------------------------------------------------------------------ column
    sock_outline = star_resample(sock_pts, sock_c, 48)
    shrink = [sock_c + (p - sock_c) * ((p - sock_c).length - 0.0002) / (p - sock_c).length for p in sock_outline]
    col_low = [sock_c + (p - sock_c) for p in shrink]
    # collar underside outline (inset 0.6 mm), resampled by angle around the socket centre so the
    # loft blends from the round column into the collar without twisting
    cl_in = [cc + (p - cc) * max(0.0, ((p - cc).length - 0.0006)) / (p - cc).length for p in collar_low]
    col_top = star_resample(cl_in, sock_c, 48) if all(ray_poly(cl_in, sock_c, Vector((math.cos(2 * math.pi * k / 48), math.sin(2 * math.pi * k / 48)))) for k in range(48)) else None
    if col_top is None:
        # socket centre not inside the collar footprint: resample around the collar centre instead
        col_top = [p for p in star_resample(cl_in, cc, 48)]
    rings = []

    def ring(pts, z, grow=0.0, c=None):
        c = c or sock_c
        return [Vector((c.x + (p.x - c.x) * (1 + grow / max((p - c).length, 1e-6)),
                        c.y + (p.y - c.y) * (1 + grow / max((p - c).length, 1e-6)), z)) for p in pts]
    z_in = base_top - 0.012
    z_blend0 = collar_bot - 0.034
    z_top = collar_bot + 0.0018
    rings.append(ring(col_low, z_in))
    # flared trim ring where the column enters the base (a moulded boot, with a rounded lip)
    rings.append(ring(col_low, base_top - 0.0005, 0.0026))
    rings.append(ring(col_low, base_top + 0.0020, 0.0026))
    rings.append(ring(col_low, base_top + 0.0034, 0.0019))
    rings.append(ring(col_low, base_top + 0.0042, 0.0008))
    rings.append(ring(col_low, base_top + 0.0046, 0.0))
    rings.append(ring(col_low, base_top + 0.0060, 0.0))
    nb = 7
    for i in range(nb + 1):
        t = i / nb
        z = z_blend0 + (z_top - z_blend0) * t
        w = smooth01(t)
        rings.append([Vector((p.x + (q.x - p.x) * w, p.y + (q.y - p.y) * w, z)) for p, q in zip(col_low, col_top)])
    bm_col = loft(rings)
    print(f'COLUMN socket-outline {len(col_low)} pts, z {z_in:.4f} -> {z_top:.4f}')

    # ------------------------------------------------------------------ collar pivot (arm pivot pin + caps)
    bars_c = centroid2(slice_hull(arm, collar_top + 0.006))
    piv_z = (collar_bot + collar_top) / 2 + 0.004
    # along b, find the collar's outer faces through the bars' centre
    t_plus = ray_poly(collar_mid, bars_c, b_dir) or 0.02
    t_minus = ray_poly(collar_mid, bars_c, -b_dir) or 0.02
    piv_bms = []
    for sgn, tt in ((1, t_plus), (-1, t_minus)):
        o = bars_c + b_dir * (sgn * tt)
        fr = frame_from_axis(Vector((o.x, o.y, piv_z)), (b_dir * sgn).to_3d())
        prof = [(0.0, 0.0022), (0.0040, 0.0022), (0.0058, 0.0019), (0.0068, 0.0012), (0.0072, 0.0004),
                (0.0072, -0.0015), (0.0, -0.0015)]
        piv_bms.append(lathe_frame(prof, fr, seg=40))
        # the pin's recessed centre (a shallow dimple reads as a rivet/pin head)
        piv_bms.append(lathe_frame([(0.0, 0.0024), (0.0022, 0.0024), (0.0026, 0.0021), (0.0, 0.0021)], fr, seg=24))

    # ------------------------------------------------------------------ head hinge barrel
    # the arm's top bracket sits on the +t side of the head's rear end; a barrel along t joins them
    br = [v.co for v in arm.verts if v.co.z > 1.15]
    hr = [v.co for v in head.verts]
    s_rear = min(hst(p)[0] for p in hr)
    br_st = [hst(p) for p in br]
    s_b0 = min(s for s, _ in br_st)
    s_b1 = max(s for s, _ in br_st)
    t_b1 = max(t for _, t in br_st)
    rear_pts = [p for p in hr if hst(p)[0] < s_rear + 0.02]
    z_rear = (min(p.z for p in rear_pts) + max(p.z for p in rear_pts)) / 2
    t_head0 = min(hst(p)[1] for p in rear_pts)
    s_h = s_rear + 0.013
    hinge_c = Vector((hc.x, hc.y, 0)) + ha.to_3d() * s_h + Z * z_rear
    t0, t1 = t_head0 - 0.003, t_b1 + 0.003
    fr = frame_from_axis(hinge_c + hb.to_3d() * t0, hb.to_3d())
    L = t1 - t0
    rb = 0.0118
    prof = [(0.0, 0.0), (rb - 0.0028, 0.0), (rb - 0.0008, 0.0004), (rb, 0.0018), (rb, 0.0205),
            (rb - 0.0006, 0.0211), (rb, 0.0217), (rb, L - 0.0018), (rb - 0.0008, L - 0.0004),
            (rb - 0.0028, L), (0.0, L)]
    bm_hinge = lathe_frame(prof, fr, seg=40)
    print(f'HINGE centre {tuple(round(x, 4) for x in hinge_c)} t [{t0:.4f},{t1:.4f}] r {rb}; bracket s [{s_b0:.3f},{s_b1:.3f}]')

    # ------------------------------------------------------------------ circular light fitted to the head
    tree = BVHTree.FromBMesh(head)
    samples = []
    for dx in (-0.025, 0.0, 0.025):
        for dy in (-0.025, 0.0, 0.025):
            o = Vector((DIFF_XY.x + dx, DIFF_XY.y + dy, 1.0))
            hit = tree.ray_cast(o, Z, 1.0)
            if hit[0] is not None:
                samples.append(hit[0])
    # least-squares plane z = a x + b y + c
    import numpy as np
    A = np.array([[p.x, p.y, 1.0] for p in samples])
    zz = np.array([p.z for p in samples])
    pa, pb, pc = np.linalg.lstsq(A, zz, rcond=None)[0]
    n_up = Vector((-pa, -pb, 1.0)).normalized()
    dc = Vector((DIFF_XY.x, DIFF_XY.y, pa * DIFF_XY.x + pb * DIFF_XY.y + pc))
    n_dn = -n_up
    fr_d = frame_from_axis(dc, n_dn)          # local +Z points down, away from the head
    # bezel: a moulded ring standing 3.5 mm proud of the underside, lip over the diffuser edge
    bez_prof = [(DIFF_R - 0.0012, 0.0024), (DIFF_R + 0.0005, 0.0031), (DIFF_R + 0.0030, 0.0035),
                (DIFF_R + 0.0046, 0.0026), (DIFF_R + 0.0052, 0.0008), (DIFF_R + 0.0052, -0.0006),
                (DIFF_R - 0.0012, -0.0006)]
    bm_bez = lathe_frame(bez_prof + [bez_prof[0]], fr_d, seg=72)
    # diffuser: slightly domed opal disc, emitting down
    disc_prof = [(0.0, 0.0027), (DIFF_R * 0.5, 0.0026), (DIFF_R * 0.85, 0.0024), (DIFF_R - 0.0008, 0.0022),
                 (DIFF_R - 0.0008, 0.0002), (0.0, 0.0002)]
    bm_disc = lathe_frame(disc_prof, fr_d, seg=72)
    head_under = dc
    print(f'DIFFUSER centre on head underside {tuple(round(x, 4) for x in dc)}, tilt '
          f'{math.degrees(n_up.angle(Z)):.1f} deg (was floating at z 1.1772)')

    # ------------------------------------------------------------------ objects
    root = bpy.data.objects.new('NEW_lamp_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.05
    root.location = Vector((base_c.x, base_c.y, base_bot))
    coll.objects.link(root)
    inv = Matrix.Translation(-root.location)
    tris = {}

    def emit(name, bm, mat, smooth=38):
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-6)
        bm.transform(inv)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(smooth))
        o = bpy.data.objects.new(name, me)
        coll.objects.link(o)
        o.parent = root
        tris[name] = sum(len(p.vertices) - 2 for p in me.polygons)
        return o

    emit('lamp_base', base, WP)
    emit('lamp_column', bm_col, WP, 50)
    emit('lamp_arm', arm, WP)
    pv = bmesh.new()
    for b in piv_bms:
        me_tmp = bpy.data.meshes.new('tmp')
        b.to_mesh(me_tmp)
        b.free()
        pv.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    emit('lamp_collar_pivot', pv, WP)
    emit('lamp_head_hinge', bm_hinge, WP)
    emit('lamp_head', head, WP)
    emit('lamp_head_trim', trim, WP)
    emit('lamp_diffuser_bezel', bm_bez, WP, 50)
    emit('lamp_diffuser_disc', bm_disc, DM, 50)

    ld = bpy.data.lights.new('LAMP_disk', 'AREA')
    ld.shape = 'DISK'
    ld.size = 2 * DIFF_R
    ld.energy = DISK_ENERGY
    ld.color = WARM
    ld.spread = DISK_SPREAD
    lo = bpy.data.objects.new('LAMP_disk', ld)
    coll.objects.link(lo)
    lo.parent = root
    lo.matrix_world = Matrix.Translation(dc + n_dn * 0.0032) @ n_dn.to_track_quat('-Z', 'Y').to_matrix().to_4x4()

    total = sum(tris.values())
    print('TRIS', total, tris)
    return dict(scene=scene, coll=coll, root=root, tris=tris, total=total, base_c=base_c, base_top=base_top,
                hinge=hinge_c, diff=dc)


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
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new('grey')
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.42, 0.42, 0.42, 1)
    bg.inputs['Strength'].default_value = 0.6
    scene.world = w
    tmp = []
    c = b['base_c']
    desk = bpy.data.meshes.new('prev_desk')
    desk.from_pydata([(c.x - 0.8, c.y - 0.8, 0.735), (c.x + 0.8, c.y - 0.8, 0.735), (c.x + 0.8, c.y + 0.8, 0.735),
                      (c.x - 0.8, c.y + 0.8, 0.735)], [], [(0, 1, 2, 3)])
    dm = bpy.data.materials.new('prev_desk')
    dm.use_nodes = True
    principled(dm).inputs['Base Color'].default_value = (0.55, 0.42, 0.33, 1)
    desk.materials.append(dm)
    do = bpy.data.objects.new('prev_desk', desk)
    scene.collection.objects.link(do)
    tmp.append(do)
    tgt = Vector((c.x + 0.02, c.y - 0.02, 0.98))

    def light(name, off, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        o = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(o)
        o.location = tgt + Vector(off)
        o.rotation_euler = (tgt - o.location).to_track_quat('-Z', 'Y').to_euler()
        tmp.append(o)
    light('key', (0.8, -0.9, 0.7), 90, 0.6)
    light('fill', (-0.9, -0.5, 0.2), 30, 0.9)
    light('rim', (-0.3, 0.9, 0.6), 70, 0.5)
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam
    tmp.append(cam)

    def shot(loc, target, lens, name):
        cam.location = loc
        cam.data.lens = lens
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, name)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', name)
    scene.render.resolution_x, scene.render.resolution_y = 900, 1100
    shot(tgt + Vector((0.62, -0.66, 0.16)), tgt, 38, 'lamp_34.png')
    shot(Vector((c.x, c.y, 0.80)) + Vector((0.22, -0.26, 0.10)), Vector((c.x + 0.02, c.y + 0.02, 0.81)), 50, 'lamp_column.png')
    shot(b['hinge'] + Vector((0.20, -0.16, 0.06)), b['hinge'] + Vector((0.03, -0.03, -0.01)), 50, 'lamp_hinge.png')
    shot(b['diff'] + Vector((0.16, -0.20, -0.16)), b['diff'], 50, 'lamp_underside.png')
    scene.render.resolution_x, scene.render.resolution_y = 1280, 800
    shot(SEAT, tgt + Vector((0, 0, 0.02)), 42, 'lamp_seat.png')
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
