"""
v2_medals.py -- four medals casually tossed over the desk lamp's short neck, draped by cloth simulation.

    blender -b --factory-startup --python blender/scripts/v2_medals.py -- [--no-render] [--sim-frames N]

1. Reads the lamp as it now stands in blender/scene/room.blend (opened READ-ONLY, never saved): every
   mesh under NEW_lamp_root in world space (the orchestrator moved/scaled it), the tilt pivot and the
   neck (axis, radius, the 15 mm span between the yoke and the head rim).
2. Builds four lanyards (27-30 mm woven ribbon, 1 blue + 3 red) in a clean, non-intersecting start state:
   loops layered over the neck at slightly different lean angles, tails twisting into their own depth
   layers below it.
3. One joint cloth simulation of all four ribbons -- self-collision on, colliding with the real lamp meshes
   and with the medal discs -- while each lanyard's crimp end is carried by a hook to a casual final pose:
   different heights and offsets, one medal flipped to its back (its ribbon takes a half twist), one turned
   sideways, one resting against the lamp's front branch. Gravity and the collisions produce the folds and
   crossings. The settled cloth is baked into plain meshes.
4. Medals (gold on the blue ribbon, silver on the red ones, blank faces), crimps and jump rings at the
   final poses; one armature with a 4 s seamless sway; medals.blend + medals.glb, re-import check.
Output root NEW_medals_root carries parent_to = 'NEW_lamp_pivot' (parent it keeping transform, so the
medals follow the lamp's tilt). ROOM coordinates.
"""
import bpy
import bmesh
import math
import os
import sys
import json
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ROOM = os.path.join(REPO, 'blender', 'scene', 'room.blend')
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
NAME = 'medals'
OUT_BLEND = os.path.join(PARTS, NAME + '.blend')
OUT_GLB = os.path.join(PARTS, NAME + '.glb')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS

SEAT = Vector((0.0, -0.16, 1.175))
FPS = 24
LOOP_FRAMES = 96          # 4 s sway loop
SIM_FRAMES = int(ARGS[ARGS.index('--sim-frames') + 1]) if '--sim-frames' in ARGS else 110
MOVE_FRAMES = 70          # crimps travel to their casual poses over these frames, then everything settles
K = 1.2 * 1.12            # owner: 20% bigger, then another ~12%
RIBBON_W = 0.0225 * K     # 30 mm lanyard
ROW_STEP = 0.003
Z = Vector((0, 0, 1))
CLOTH = dict(quality=25, time_scale=1.0, mass=0.0006, air=3.0, tension=120.0, compression=30.0, shear=40.0, bend=4.0, damp=10.0, bend_damp=2.0,
             pin=6.0, coldist=0.0010, colq=8, selfcol=True, selfdist=0.0006, selffric=5.0, friction=6.0)
RIBBON_HEX = dict(blue='#1d3a8a', white='#e9e7e0', red='#a81c26', gold='#d9a92e', green='#17613a')

# layer 1 = innermost loop ... 4 = outermost (on top). plane/drop: clean start state (drop from the neck
# axis to the crimp top, ~18% longer than before). lean: loop lean about the across axis (deg).
# move: casual final pose of the crimp relative to the start: ds (along the neck, + toward the seat),
# dt (across), dz, rot (deg about vertical). ds='branch' = slide back until the medal rests against the
# lamp's front branch.
AMP_K = 1.0
# layer 1 = innermost loop ... 4 = outermost (on top). plane: start depth of the lanyard below the neck
# (+ toward the seat). drop: final crimp drop below the neck axis (tails of different lengths). lean: loop
# lean about the across axis (deg). move: where the hook carries the crimp during the sim -- ds (along the
# neck; 'branch' = back until the medal rests against the lamp's front branch), dt (across), rot (deg about
# vertical), slack (the crimp rises this much, so the ribbon settles in soft folds instead of a taut strip).
SPECS = [
    dict(name='m1', layer=4, plane=+0.0135, drop=0.111, lean=12, R=0.0205 * K, metal='gold', relief='blank',
         cols=[0, 1/6, 2/6, 3/6, 4/6, 5/6, 1], bands=['blue'] * 6, rot90=False,
         move=dict(ds=0.004, dt=0.004, rot=15, slack=0.003)),
    dict(name='m2', layer=3, plane=+0.0045, drop=0.100, lean=-8, R=0.0195 * K, metal='silver', relief='blank',
         cols=[0, 1/6, 2/6, 3/6, 4/6, 5/6, 1], bands=['red'] * 6, rot90=False,
         move=dict(ds=0.0, dt=-0.020, rot=60, slack=0.002)),
    dict(name='m3', layer=2, plane=-0.0045, drop=0.191, lean=20, R=0.0195 * K, metal='silver', relief='blank',
         cols=[0, 1/6, 2/6, 3/6, 4/6, 5/6, 1], bands=['red'] * 6, rot90=False,
         move=dict(ds=-0.002, dt=0.024, rot=180, slack=0.003)),
    dict(name='m4', layer=1, plane=-0.0135, drop=0.076, lean=-15, R=0.0195 * K, metal='silver', relief='blank',
         cols=[0, 1/6, 2/6, 3/6, 4/6, 5/6, 1], bands=['red'] * 6, rot90=False,
         move=dict(ds=-0.006, dt=-0.004, rot=-10, slack=0.002)),
]


# =============================================================================== helpers
def hex_rgb(h):
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


def cr_chain(P):
    """Centripetal Catmull-Rom through P; returns [(pos, seg_index, t)]."""
    P = [P[0] + (P[0] - P[1])] + list(P) + [P[-1] + (P[-1] - P[-2])]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]

        def tj(ti, a, b):
            return ti + max((b - a).length, 1e-7) ** 0.5
        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        n = max(2, int((p2 - p1).length / 0.0006))
        for s in range(n):
            t = t1 + (t2 - t1) * s / n
            A1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            A2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            A3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            B1 = (t2 - t) / (t2 - t0) * A1 + (t - t0) / (t2 - t0) * A2
            B2 = (t3 - t) / (t3 - t1) * A2 + (t - t1) / (t3 - t1) * A3
            C = (t2 - t) / (t2 - t1) * B1 + (t - t1) / (t2 - t1) * B2
            out.append((C, i - 1, s / n))
    out.append((P[-2], len(P) - 4, 1.0))
    return out


def slerp_vec(a, b, t):
    q = a.rotation_difference(b)
    return Quaternion().slerp(q, t) @ a


def ribbon_rows(ctrl):
    """ctrl: [(pos, width_vec[, width_scale])] -> resampled rows [pos, width_unit, s, width_scale]."""
    P = [c[0] for c in ctrl]
    W = [c[1].normalized() for c in ctrl]
    S = [c[2] if len(c) > 2 else 1.0 for c in ctrl]
    dense = []
    for pos, i, t in cr_chain(P):
        j2 = min(i + 1, len(W) - 1)
        dense.append((pos, slerp_vec(W[i], W[j2], t), S[i] + (S[j2] - S[i]) * t))
    L = [0.0]
    for i in range(1, len(dense)):
        L.append(L[-1] + (dense[i][0] - dense[i - 1][0]).length)
    total = L[-1]
    n = max(4, round(total / ROW_STEP))
    rows, j = [], 0
    for k in range(n + 1):
        s = total * k / n
        while j < len(L) - 2 and L[j + 1] < s:
            j += 1
        t = (s - L[j]) / (L[j + 1] - L[j]) if L[j + 1] > L[j] else 0.0
        rows.append([dense[j][0].lerp(dense[j + 1][0], t),
                     slerp_vec(dense[j][1], dense[j + 1][1], t), s,
                     dense[j][2] + (dense[j + 1][2] - dense[j][2]) * t])
    for k in range(len(rows)):
        a = rows[max(k - 1, 0)][0]
        b = rows[min(k + 1, len(rows) - 1)][0]
        tan = (b - a).normalized()
        w = rows[k][1]
        w = (w - tan * w.dot(tan)).normalized()
        rows[k][1] = w
    return rows, total


class MB:
    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def vert(self, co):
        self.v.append(Vector(co))
        return len(self.v) - 1

    def face(self, idx, mat=0):
        self.f.append(tuple(idx))
        self.m.append(mat)

    def extend(self, other, mat_map=None, xf=None):
        base = len(self.v)
        for co in other.v:
            self.v.append(xf @ co if xf else co.copy())
        for f, m in zip(other.f, other.m):
            self.f.append(tuple(i + base for i in f))
            self.m.append(mat_map[m] if mat_map else m)

    def to_object(self, name, mats, coll, recalc=True, smooth_angle=35):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(c) for c in self.v], [], self.f)
        me.update()
        for i, p in enumerate(me.polygons):
            p.material_index = self.m[i]
        for m in mats:
            me.materials.append(m)
        if recalc:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
        me.shade_smooth()
        if smooth_angle is not None:
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        o = bpy.data.objects.new(name, me)
        coll.objects.link(o)
        return o


def lathe(mb, prof, seg, mat_fn):
    rings = []
    for (r, y) in prof:
        if r < 1e-7:
            rings.append([mb.vert((0, y, 0))])
        else:
            rings.append([mb.vert((r * math.cos(2 * math.pi * j / seg), y, r * math.sin(2 * math.pi * j / seg)))
                          for j in range(seg)])
    for i in range(len(prof) - 1):
        A, B = rings[i], rings[i + 1]
        m = mat_fn(i)
        for j in range(seg):
            j2 = (j + 1) % seg
            if len(A) == 1:
                mb.face([A[0], B[j2], B[j]], m)
            elif len(B) == 1:
                mb.face([A[j], A[j2], B[0]], m)
            else:
                mb.face([A[j], A[j2], B[j2], B[j]], m)


def ellipsoid(mb, c, ax, ay, az, rotz, seg=8, rings=4, mat=0, xf=None):
    """Ellipsoid in local frame; rotz rotates about local Y (the medal normal)."""
    rot = Matrix.Rotation(rotz, 3, 'Y')
    top = mb.vert(c + rot @ Vector((0, 0, az)))
    ring_ids = []
    for r in range(1, rings):
        th = math.pi * r / rings
        ring = []
        for s in range(seg):
            ph = 2 * math.pi * s / seg
            p = Vector((ax * math.sin(th) * math.cos(ph), ay * math.sin(th) * math.sin(ph), az * math.cos(th)))
            ring.append(mb.vert(c + rot @ p))
        ring_ids.append(ring)
    bot = mb.vert(c + rot @ Vector((0, 0, -az)))
    for s in range(seg):
        mb.face([top, ring_ids[0][s], ring_ids[0][(s + 1) % seg]], mat)
        mb.face([bot, ring_ids[-1][(s + 1) % seg], ring_ids[-1][s]], mat)
    for r in range(len(ring_ids) - 1):
        for s in range(seg):
            a, b = ring_ids[r], ring_ids[r + 1]
            mb.face([a[s], b[s], b[(s + 1) % seg], a[(s + 1) % seg]], mat)


def leaf(mb, c, length, width, thick, ang, mat=0, seg=8, rings=4):
    """A flattened ellipsoid lying on the medal face (local XZ plane, thickness along Y)."""
    rot = Matrix.Rotation(ang, 3, 'Y')
    top = mb.vert(c + rot @ Vector((0, 0, length)))
    ring_ids = []
    for r in range(1, rings):
        th = math.pi * r / rings
        ring = []
        for s in range(seg):
            ph = 2 * math.pi * s / seg
            p = Vector((width * math.sin(th) * math.cos(ph), thick * math.sin(th) * math.sin(ph),
                        length * math.cos(th)))
            ring.append(mb.vert(c + rot @ p))
        ring_ids.append(ring)
    bot = mb.vert(c + rot @ Vector((0, 0, -length)))
    for s in range(seg):
        mb.face([top, ring_ids[0][s], ring_ids[0][(s + 1) % seg]], mat)
        mb.face([bot, ring_ids[-1][(s + 1) % seg], ring_ids[-1][s]], mat)
    for r in range(len(ring_ids) - 1):
        for s in range(seg):
            a, b = ring_ids[r], ring_ids[r + 1]
            mb.face([a[s], b[s], b[(s + 1) % seg], a[(s + 1) % seg]], mat)


def faceted_star(mb, yb, ro, ri, h, points=5, mat=0, rot=0.0):
    n = points * 2
    apex = mb.vert((0, yb + h, 0))
    botc = mb.vert((0, yb - 0.0002, 0))
    ring = []
    for k in range(n):
        a = math.pi / 2 + rot + math.pi * k / points
        r = ro if k % 2 == 0 else ri
        ring.append(mb.vert((r * math.cos(a), yb - 0.00015, r * math.sin(a))))
    for k in range(n):
        mb.face([apex, ring[(k + 1) % n], ring[k]], mat)
        mb.face([botc, ring[k], ring[(k + 1) % n]], mat)


def torus(mb, c, axis, R, r, seg=20, segm=8, mat=0):
    axis = axis.normalized()
    u = axis.orthogonal().normalized()
    v = axis.cross(u).normalized()
    ids = []
    for i in range(seg):
        th = 2 * math.pi * i / seg
        radial = u * math.cos(th) + v * math.sin(th)
        ring = []
        for j in range(segm):
            ph = 2 * math.pi * j / segm
            ring.append(mb.vert(c + radial * (R + r * math.cos(ph)) + axis * (r * math.sin(ph))))
        ids.append(ring)
    for i in range(seg):
        for j in range(segm):
            a, b = ids[i], ids[(i + 1) % seg]
            mb.face([a[j], b[j], b[(j + 1) % segm], a[(j + 1) % segm]], mat)


def rounded_box(mb, frame, size, bev, mat=0):
    """Beveled box centred at frame.translation, axes frame columns. Built via bmesh bevel."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bev, segments=2, profile=0.5, affect='EDGES',
                    clamp_overlap=True)
    base = len(mb.v)
    idx = {}
    for v in bm.verts:
        idx[v.index] = mb.vert(frame @ v.co)
    for f in bm.faces:
        mb.face([idx[v.index] for v in f.verts], mat)
    bm.free()


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def fabric_mat(name, hx):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = principled(m)
    b.inputs['Base Color'].default_value = (*hex_rgb(hx), 1.0)
    b.inputs['Roughness'].default_value = 0.52
    b.inputs['Metallic'].default_value = 0.0
    b.inputs['Sheen Weight'].default_value = 0.25
    b.inputs['Sheen Roughness'].default_value = 0.3
    # woven polyester: fine warp ridges along the ribbon + weft ticks across + faint twill diagonal
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['UV'], sep.inputs['Vector'])

    def mathn(op, a=None, b=None, va=None, vb=None):
        n = nt.nodes.new('ShaderNodeMath')
        n.operation = op
        if a is not None:
            nt.links.new(a, n.inputs[0])
        elif va is not None:
            n.inputs[0].default_value = va
        if b is not None:
            nt.links.new(b, n.inputs[1])
        elif vb is not None:
            n.inputs[1].default_value = vb
        return n.outputs[0]
    warp = mathn('ABSOLUTE', mathn('SINE', mathn('MULTIPLY', sep.outputs['X'], vb=math.pi / 0.00045)))
    weft = mathn('ABSOLUTE', mathn('SINE', mathn('MULTIPLY', sep.outputs['Y'], vb=math.pi / 0.0007)))
    twill = mathn('SINE', mathn('MULTIPLY', mathn('ADD', sep.outputs['X'], sep.outputs['Y']),
                                vb=2 * math.pi / 0.0016))
    h = mathn('ADD', mathn('MULTIPLY', warp, vb=0.6), mathn('MULTIPLY', weft, vb=0.3))
    h = mathn('ADD', h, mathn('MULTIPLY', twill, vb=0.12))
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.00015
    nt.links.new(h, bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def metal_mat(name, rgb, rough, grain=0.03, grain_scale=1500.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = principled(m)
    b.inputs['Base Color'].default_value = (*rgb, 1.0)
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Roughness'].default_value = rough
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = grain_scale
    nz.inputs['Detail'].default_value = 3.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = grain
    bump.inputs['Distance'].default_value = 0.0001
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def build_materials():
    M = {}
    for k, hx in RIBBON_HEX.items():
        M['ribbon_' + k] = fabric_mat('medals_ribbon_' + k, hx)
    M['gold'] = metal_mat('medals_gold_polished', (1.0, 0.74, 0.33), 0.16)
    M['gold_satin'] = metal_mat('medals_gold_satin', (0.95, 0.70, 0.31), 0.42, grain=0.12, grain_scale=4000)
    M['silver'] = metal_mat('medals_silver_polished', (0.95, 0.94, 0.91), 0.14)
    M['silver_satin'] = metal_mat('medals_silver_satin', (0.88, 0.87, 0.85), 0.40, grain=0.12, grain_scale=4000)
    M['bronze'] = metal_mat('medals_bronze_polished', (0.66, 0.38, 0.19), 0.24)
    M['bronze_satin'] = metal_mat('medals_bronze_satin', (0.55, 0.32, 0.17), 0.48, grain=0.12, grain_scale=4000)
    M['nickel'] = metal_mat('medals_nickel', (0.66, 0.64, 0.60), 0.24)
    return M


def medal_mesh(R, relief):
    """Medal in local frame: face normal +Y (front), up +Z, centre at origin. mat 0 polished, 1 satin."""
    T_f, T_b = 0.0012, -0.0012
    prof = [(0, T_f), (0.45 * (R - 0.0024), T_f), (R - 0.0024, T_f), (R - 0.0021, T_f + 0.00028),
            (R - 0.0018, T_f + 0.00042), (R - 0.0008, T_f + 0.00042), (R - 0.0002, T_f + 0.0001),
            (R, T_f - 0.00035), (R, T_b + 0.00035), (R - 0.0002, T_b - 0.0001), (R - 0.0008, T_b - 0.00032),
            (R - 0.0016, T_b - 0.00032), (R - 0.0019, T_b), (0.45 * (R - 0.002), T_b), (0, T_b)]
    satin_segments = {0, 1, 12, 13}
    mb = MB()
    lathe(mb, prof, 56, lambda i: 1 if i in satin_segments else 0)
    yb = T_f
    if relief == 'star':
        faceted_star(mb, yb, 0.62 * R, 0.25 * R, 0.00048, mat=0)
        n = 30
        for k in range(n):
            a = 2 * math.pi * k / n
            c = Vector((0.81 * R * math.cos(a), yb, 0.81 * R * math.sin(a)))
            ellipsoid(mb, c, 0.00042, 0.00042, 0.00042, 0, seg=6, rings=3, mat=0)
    if relief in ('wreath', 'wreath_boss'):
        for side in (-1, 1):
            n = 9
            for k in range(n):
                t = k / (n - 1)
                a = math.radians(-78 + t * 128)          # from bottom up the side
                rr = 0.70 * R
                px = side * rr * math.cos(a)
                pz = rr * math.sin(a)
                for outer in (0, 1):
                    rr2 = rr + (0.075 * R if outer else -0.075 * R)
                    c = Vector((side * rr2 * math.cos(a), yb + 0.00012, rr2 * math.sin(a)))
                    # leaf axis along the arc tangent (upward), splayed outward / inward
                    ang = -side * a + side * (0.5 if outer else -0.5)
                    leaf(mb, c, 0.115 * R, 0.048 * R, 0.00032, ang, mat=0, seg=8, rings=4)
        if relief == 'wreath':
            faceted_star(mb, yb, 0.34 * R, 0.14 * R, 0.00042, mat=0)
        else:
            boss = [(0, yb + 0.00055), (0.14 * R, yb + 0.0005), (0.26 * R, yb + 0.00032),
                    (0.33 * R, yb + 0.0001), (0.35 * R, yb - 0.0002)]
            sub = MB()
            lathe(sub, boss, 36, lambda i: 0)
            mb.extend(sub)
    if relief == 'sun':
        boss = [(0, yb + 0.0006), (0.12 * R, yb + 0.00055), (0.22 * R, yb + 0.0004),
                (0.28 * R, yb + 0.00015), (0.30 * R, yb - 0.0002)]
        sub = MB()
        lathe(sub, boss, 36, lambda i: 0)
        mb.extend(sub)
        nr = 16
        for k in range(nr):
            a = 2 * math.pi * (k + 0.5) / nr
            dvec = Vector((math.cos(a), 0, math.sin(a)))
            perp = Vector((-math.sin(a), 0, math.cos(a)))
            r0, r1 = 0.33 * R, (0.80 if k % 2 == 0 else 0.66) * R
            hw = 0.055 * R
            A = mb.vert(dvec * r0 + perp * hw + Vector((0, yb - 0.00015, 0)))
            B = mb.vert(dvec * r0 - perp * hw + Vector((0, yb - 0.00015, 0)))
            C = mb.vert(dvec * r1 + Vector((0, yb - 0.00015, 0)))
            Tp = mb.vert(dvec * r0 + Vector((0, yb + 0.00042, 0)))
            mb.face([A, Tp, C], 0)
            mb.face([Tp, B, C], 0)
            mb.face([A, B, Tp], 0)
            mb.face([A, C, B], 0)
        rim2 = [(0.86 * R, yb - 0.0002), (0.875 * R, yb + 0.0002), (0.895 * R, yb + 0.0002),
                (0.91 * R, yb - 0.0002)]
        sub = MB()
        lathe(sub, rim2, 56, lambda i: 0)
        mb.extend(sub)
    return mb


def link_new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def add_collision(o, friction=8.0):
    o.modifiers.new('Collision', 'COLLISION')
    o.collision.thickness_outer = 0.0004
    o.collision.thickness_inner = 0.002
    o.collision.cloth_friction = friction
    o.collision.damping = 0.5


# =============================================================================== 1. measure (room.blend, read-only)
def measure():
    bpy.ops.wm.open_mainfile(filepath=ROOM, load_ui=False)
    root = bpy.data.objects['NEW_lamp_root']
    out = {'ref': {}, 'lights': []}

    def walk(o):
        if o.name.startswith('NEW_medals'):          # the currently integrated medals hang under the pivot
            return
        yield o
        for c in o.children:
            yield from walk(c)
    for o in walk(root):
        if o.type == 'MESH':
            mw = o.matrix_world
            md = dict(col=(0.83, 0.83, 0.82), rough=0.33, metal=0.0, emit=0.0, ecol=(1, 1, 1))
            mat = o.data.materials[0] if o.data.materials else None
            if mat and mat.node_tree:
                b = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if b:
                    md = dict(col=tuple(b.inputs['Base Color'].default_value)[:3],
                              rough=b.inputs['Roughness'].default_value, metal=b.inputs['Metallic'].default_value,
                              emit=b.inputs['Emission Strength'].default_value,
                              ecol=tuple(b.inputs['Emission Color'].default_value)[:3])
            name = o.name.split('.')[0]
            out['ref'][name] = dict(verts=[tuple(mw @ v.co) for v in o.data.vertices],
                                    faces=[tuple(p.vertices) for p in o.data.polygons], mat=md)
        elif o.type == 'LIGHT':
            out['lights'].append(dict(name=o.name, type=o.data.type, energy=o.data.energy, color=tuple(o.data.color),
                                      size=getattr(o.data, 'size', 0.0), shape=getattr(o.data, 'shape', 'DISK'),
                                      spread=getattr(o.data, 'spread', math.pi), matrix=[list(r) for r in o.matrix_world]))
    piv = bpy.data.objects['NEW_lamp_pivot']
    out['pivot'] = list(piv.matrix_world.translation)
    bv = [Vector(v) for v in out['ref']['lamp_base']['verts']]
    out['base_top'] = max(v.z for v in bv)
    cx = (min(v.x for v in bv) + max(v.x for v in bv)) / 2
    cy = (min(v.y for v in bv) + max(v.y for v in bv)) / 2
    out['base_c'] = (cx, cy)
    out['base_r'] = (max(v.x for v in bv) - min(v.x for v in bv)) / 2
    return out


def medal_drop(R):
    """Crimp top -> medal centre, along -Z, for the chain used below (crimp, crimp loop, jump ring, eye)."""
    r_c, m_c = 0.0019 * K, 0.00055 * K
    Rj, mj = 0.0031 * K, 0.0005 * K
    re, me_ = 0.0019 * K, 0.00065 * K
    d = (0.0065 + 0.0014) * K + (r_c - m_c - mj) + Rj + (Rj - mj - me_) + re + (re + R - 0.0007 * K)
    return d


# =============================================================================== main build
def build():
    meas = measure()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start = 0
    scene.frame_end = LOOP_FRAMES
    M = build_materials()
    coll = link_new_collection('NEW_medals')
    work = link_new_collection('WORK_medals')      # proxies, hooks, sim; deleted before save
    refc = link_new_collection('REF_lamp')         # the lamp as in room.blend; deleted before save

    # ------------------------------------------------------------------ the lamp (reference + colliders)
    ref_objs = {}
    for n, d in meas['ref'].items():
        me = bpy.data.meshes.new('ref_' + n)
        me.from_pydata(d['verts'], [], d['faces'])
        me.update()
        mat = bpy.data.materials.new('ref_' + n)
        mat.use_nodes = True
        b = principled(mat)
        b.inputs['Base Color'].default_value = (*d['mat']['col'], 1)
        b.inputs['Roughness'].default_value = d['mat']['rough']
        b.inputs['Metallic'].default_value = d['mat']['metal']
        if d['mat']['emit'] > 0:
            b.inputs['Emission Color'].default_value = (*d['mat']['ecol'], 1)
            b.inputs['Emission Strength'].default_value = d['mat']['emit']
        me.materials.append(mat)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(40))
        o = bpy.data.objects.new('ref_' + n, me)
        refc.objects.link(o)
        ref_objs[n] = o
        add_collision(o, friction=CLOTH['friction'])
        o.collision.thickness_outer = 0.0006
    for L in meas['lights']:
        ld = bpy.data.lights.new('ref_' + L['name'], L['type'])
        ld.energy = L['energy']
        ld.color = L['color']
        if L['type'] == 'AREA':
            ld.shape = L['shape']
            ld.size = L['size']
            ld.spread = L['spread']
        lo = bpy.data.objects.new('ref_' + L['name'], ld)
        refc.objects.link(lo)
        lo.matrix_world = Matrix(L['matrix'])

    # ------------------------------------------------------------------ neck frame (re-measured)
    nv = [Vector(v) for v in meas['ref']['lamp_neck']['verts']]
    c = sum(nv, Vector()) / len(nv)
    import numpy as np
    A = np.array([[v.x, v.y, v.z] for v in nv])
    _, _, vt = np.linalg.svd(A - A.mean(0))
    F = Vector(vt[0]).normalized()
    F.z = 0
    F.normalize()
    if F.to_2d().dot(SEAT.to_2d() - c.to_2d()) < 0:
        F = -F
    T = Z.cross(F).normalized()
    neck_r = max(((v - c) - F * (v - c).dot(F)).length for v in nv)
    yv = [Vector(v) for v in meas['ref']['lamp_yoke']['verts']]
    hv = [Vector(v) for v in meas['ref']['lamp_head']['verts']]
    yoke_front = max((v - c).dot(F) for v in yv if abs(v.z - c.z) < neck_r)
    head_rim = min((v - c).dot(F) for v in hv if abs((v - c).dot(T)) < neck_r and abs(v.z - c.z) < 0.004)
    O = c + F * yoke_front
    neck_c = c.z
    neck_span = head_rim - yoke_front
    s_c = neck_span / 2
    print(f'NECK centre {tuple(round(x, 4) for x in c)} dir {tuple(round(x, 4) for x in F)} r {neck_r * 1000:.1f}mm '
          f'visible span {neck_span * 1000:.1f}mm')
    a3, b3 = F.copy(), T.copy()
    hc = O.to_2d()

    def to_w(s, t, z):
        return Vector((O.x, O.y, 0)) + F * s + T * t + Z * z

    # ------------------------------------------------------------------ clean start state (layered, twisted)
    W = RIBBON_W
    NR = neck_r
    L_LAYER = 0.0032
    T_MID = NR + 0.0014 + 1.5 * L_LAYER
    T_END = 0.017
    Z_T0, Z_T1 = neck_c - 0.010, neck_c - 0.044
    Z_FAN = neck_c - 0.060
    WS_G = 0.014 / W
    AB = 0.0008 * K
    t_hat, s_hat = T, F

    def sm(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)
    rib_data = []
    for spec in SPECS:
        k = spec['layer']
        d_k = (k - 2.5) * L_LAYER
        r_k = T_MID + d_k
        zc = neck_c - spec['drop']
        s_k = s_c + spec['plane']
        t_k = 0.0
        lean = math.tan(math.radians(spec['lean']))
        loop = []
        for i in range(13):
            ph = math.pi * (1 - i / 12)
            loop.append((to_w(s_c + r_k * math.sin(ph) * lean, r_k * math.cos(ph), neck_c + r_k * math.sin(ph)),
                         s_hat.copy(), WS_G))

        def tail(sg):
            off = sg * AB
            pts = [(to_w(s_c, sg * r_k, neck_c), s_hat.copy(), WS_G),
                   (to_w(s_c, sg * r_k, neck_c - 0.006), s_hat.copy(), WS_G)]
            n_tw = 7
            for i in range(n_tw + 1):
                u = i / n_tw
                th = math.pi / 2 * sm(u)
                z = Z_T0 + (Z_T1 - Z_T0) * u
                t_ax = sg * (T_MID + (T_END - T_MID) * sm(u))
                pts.append((to_w(s_c + (d_k + off) * math.sin(th), t_ax + sg * d_k * math.cos(th), z),
                            (-math.sin(th) * sg) * t_hat + math.cos(th) * s_hat,
                            WS_G + (1 - WS_G) * sm((u - 0.45) / 0.55)))
            q_end = Vector((s_k + off, t_k, zc - 0.0026 * K))
            q2 = Vector((q_end.x, q_end.y, q_end.z + 0.011 * K))
            te = Vector((s_c + d_k + off, sg * T_END, Z_T1))
            for zf in (Z_T1 - 0.006, Z_FAN):
                f = sm((Z_T1 - zf) / (Z_T1 - Z_FAN))
                u_line = (Z_T1 - zf) / (Z_T1 - q2.z)
                pts.append((to_w(te.x + (s_k + off - te.x) * f, te.y + (q2.y - te.y) * u_line, zf), -sg * t_hat, 1.0))
            pts.append((to_w(q2.x, q2.y, q2.z), -sg * t_hat, 1.0))
            pts.append((to_w(q_end.x, q_end.y, q_end.z), -sg * t_hat, 1.0))
            return pts
        ctrl = list(reversed(tail(-1))) + loop[1:-1] + tail(+1)
        rows, length = ribbon_rows(ctrl)
        for i_r, r_ in enumerate(rows):
            p = r_[0]
            q = p.to_2d() - hc
            sg = -1.0 if q.dot(T.to_2d()) < 0 else 1.0
            off = sg * AB
            if Z_T1 <= p.z <= Z_T0:
                u = (Z_T0 - p.z) / (Z_T0 - Z_T1)
                th = math.pi / 2 * sm(u)
                t_ax = sg * (T_MID + (T_END - T_MID) * sm(u))
                r_[0] = to_w(s_c + (d_k + off) * math.sin(th), t_ax + sg * d_k * math.cos(th), p.z)
                r_[1] = (-math.sin(th) * sg) * t_hat + math.cos(th) * s_hat
                r_[3] = WS_G + (1 - WS_G) * sm((u - 0.45) / 0.55)
            elif p.z < Z_T1:
                a_ = rows[max(i_r - 1, 0)][0]
                b_ = rows[min(i_r + 1, len(rows) - 1)][0]
                wn = s_hat.cross((b_ - a_).normalized()).normalized()
                if wn.dot(r_[1]) < 0:
                    wn = -wn
                r_[1] = wn
        crimp0 = to_w(s_k, t_k, zc)
        rib_data.append(dict(spec=spec, rows=rows, length=length, crimp0=crimp0,
                             pivot=to_w(s_c, 0.0, neck_c - 0.008), zk=neck_c + NR))

    # ------------------------------------------------------------------ casual final poses of the crimps
    def pose(rd, ds, dt, dz, rot):
        crimp = rd['crimp0'] + F * ds + T * dt + Z * dz            # dz = slack (upward)
        R = Matrix.Rotation(math.radians(rot), 3, 'Z')
        return crimp, R @ T, R @ F

    def medal_pts(crimp, e, d, R):
        """Sample points on the medal disc (both faces + rim) for clearance tests."""
        Mc = crimp - Z * medal_drop(R)
        pts = []
        for ring in (0.25, 0.5, 0.75, 1.0):
            for j in range(24):
                a = 2 * math.pi * j / 24
                for h in (-0.0018 * K / 1.2, 0.0018 * K / 1.2):
                    pts.append(Mc + (e * math.cos(a) + Z * math.sin(a)) * (R * ring) + d * h)
        return pts
    lamp_tree_parts = [n for n in meas['ref'] if n not in ('lamp_neck',)]

    def tree_of(names):
        V, Fc = [], []
        for n in names:
            d = meas['ref'][n]
            b_ = len(V)
            V += [Vector(v) for v in d['verts']]
            Fc += [tuple(i + b_ for i in f) for f in d['faces']]
        return BVHTree.FromPolygons(V, Fc)
    lamp_tree = tree_of(lamp_tree_parts)
    branch_tree = tree_of(['lamp_branch_front'])
    for rd in rib_data:
        mv = dict(rd['spec']['move'])
        for a_ in ARGS:                                   # overrides: move.m2.rot=0
            if a_.startswith('move.' + rd['spec']['name'] + '.'):
                kk_, vv_ = a_.split('.', 2)[2].split('=')
                mv[kk_] = vv_ if vv_ == 'branch' else float(vv_)
        mv['dz'] = mv['slack']
        if mv['ds'] == 'branch':
            ds = 0.0
            for _ in range(120):
                cr, e, d = pose(rd, ds, mv['dt'], mv['dz'], mv['rot'])
                dist = min(branch_tree.find_nearest(p)[3] for p in medal_pts(cr, e, d, rd['spec']['R']))
                if dist < 0.0035:
                    break
                ds -= 0.001
            mv['ds'] = ds
        rd['move'] = mv
    # report medal-medal and medal-lamp clearances of the chosen poses (tuned by hand, not auto-moved)
    mp = []
    for rd in rib_data:
        mv = rd['move']
        cr, e, d = pose(rd, mv['ds'], mv['dt'], mv['dz'], mv['rot'])
        mp.append(medal_pts(cr, e, d, rd['spec']['R']))
    for i in range(len(mp)):
        dl = min(lamp_tree.find_nearest(p)[3] for p in mp[i])
        dm = [round(min((p - q).length for p in mp[i] for q in mp[j]) * 1000, 1) for j in range(len(mp)) if j != i]
        per = {n: round(min(tree_of([n]).find_nearest(p)[3] for p in mp[i]) * 1000, 1) for n in lamp_tree_parts}
        near = sorted(per.items(), key=lambda kv: kv[1])[:2]
        print(f'POSECHECK {rib_data[i]["spec"]["name"]}: to lamp {dl * 1000:.1f}mm {near}, to other medals {dm}')
    for rd in rib_data:
        mv = rd['move']
        rd['crimp'], rd['e'], rd['d'] = pose(rd, mv['ds'], mv['dt'], mv['dz'], mv['rot'])
        print(f'POSE {rd["spec"]["name"]} ds {mv["ds"] * 1000:+.1f} dt {mv["dt"] * 1000:+.1f} slack {mv["dz"] * 1000:+.1f}mm '
              f'rot {mv["rot"]:+.0f}deg crimp {tuple(round(x, 4) for x in rd["crimp"])}')

    # ------------------------------------------------------------------ strips -> one cloth object
    verts, faces, fmats, uvs, pinw, hookgrp = [], [], [], [], [], []
    ranges = []
    for li, rd in enumerate(rib_data):
        spec = rd['spec']
        cols = spec['cols']
        v0, f0 = len(verts), len(faces)
        nr, nc = len(rd['rows']), len(cols)
        for (pos, w, s, ws) in rd['rows']:
            for u in cols:
                verts.append(pos + w * ((u - 0.5) * W * ws))
                ds_ = min(s, rd['length'] - s)
                pinw.append(1.0 if ds_ < 0.0045 else 0.0)
                hookgrp.append(li if ds_ < 0.0045 else -1)
        for r in range(nr - 1):
            for c_ in range(nc - 1):
                a = v0 + r * nc + c_
                faces.append((a, a + 1, a + nc + 1, a + nc))
                fmats.append(c_)
                sa, sb = rd['rows'][r][2], rd['rows'][r + 1][2]
                uvs.append([(cols[c_] * W, sa), (cols[c_ + 1] * W, sa), (cols[c_ + 1] * W, sb), (cols[c_] * W, sb)])
        ranges.append((v0, len(verts), f0, len(faces)))
    # ------------------------------------------------------------------ sequential cloth sim, inner loop first
    # Each lanyard settles with self-collision (its two tails, its own half twist) against the lamp and the
    # lanyards already settled under it (frozen as two-sided colliders), while a hook carries its crimp to the
    # casual pose. One joint self-collision sim of all four was numerically unstable in these tight layers.
    P_ = dict(CLOTH)
    for a in ARGS:
        if a.startswith('cloth.') and '=' in a:
            kk, vv = a[6:].split('=')
            P_[kk] = type(P_[kk])(float(vv)) if not isinstance(P_[kk], bool) else vv in ('1', 'true')
    print('CLOTH', P_)
    draped = [v.copy() for v in verts]
    scene.frame_start = 1
    order = sorted(range(len(rib_data)), key=lambda i: rib_data[i]['spec']['layer'])
    for li in order:
        rd = rib_data[li]
        v0, v1, f0, f1 = ranges[li]
        me = bpy.data.meshes.new(f'sim_{li}')
        me.from_pydata([tuple(verts[i]) for i in range(v0, v1)], [],
                       [tuple(i - v0 for i in faces[j]) for j in range(f0, f1)])
        me.update()
        sim = bpy.data.objects.new(f'sim_{li}', me)
        work.objects.link(sim)
        idx_end = [i - v0 for i in range(v0, v1) if hookgrp[i] == li]
        sim.vertex_groups.new(name='pin').add(idx_end, 1.0, 'REPLACE')
        # rows near the crimp (where both tails meet face to face) do not self-collide
        nc_ = len(rd['spec']['cols'])
        near = [i - v0 for i in range(v0, v1) if min(rd['rows'][(i - v0) // nc_][2],
                                                      rd['length'] - rd['rows'][(i - v0) // nc_][2]) < 0.016]
        sim.vertex_groups.new(name='noself').add(near, 1.0, 'REPLACE')
        hk = bpy.data.objects.new(f'hook_{rd["spec"]["name"]}', None)
        work.objects.link(hk)
        hk.rotation_mode = 'XYZ'
        hk.location = rd['crimp0']
        hk.rotation_euler = (0, 0, 0)
        hk.keyframe_insert('location', frame=1)
        hk.keyframe_insert('rotation_euler', frame=1)
        hk.location = rd['crimp']
        hk.rotation_euler = (0, 0, math.radians(rd['move']['rot']))
        hk.keyframe_insert('location', frame=MOVE_FRAMES)
        hk.keyframe_insert('rotation_euler', frame=MOVE_FRAMES)
        scene.frame_set(1)
        g = sim.vertex_groups.new(name='hook')
        g.add(idx_end, 1.0, 'REPLACE')
        hm = sim.modifiers.new('hook', 'HOOK')
        hm.object = hk
        hm.vertex_group = 'hook'
        hm.falloff_type = 'NONE'
        hm.center = rd['crimp0']
        hm.matrix_inverse = Matrix.Translation(rd['crimp0']).inverted()
        cl = sim.modifiers.new('Cloth', 'CLOTH')
        s = cl.settings
        s.quality = int(P_['quality'])
        s.time_scale = P_.get('time_scale', 1.0)
        s.mass = P_['mass']
        s.air_damping = P_['air']
        s.tension_stiffness = P_['tension']
        s.compression_stiffness = P_['compression']
        s.shear_stiffness = P_['shear']
        s.bending_stiffness = P_['bend']
        s.tension_damping = P_['damp']
        s.compression_damping = P_['damp']
        s.shear_damping = P_['damp']
        s.bending_damping = P_['bend_damp']
        s.vertex_group_mass = 'pin'
        s.pin_stiffness = P_['pin']
        cs = cl.collision_settings
        cs.use_collision = True
        cs.distance_min = P_['coldist']
        cs.collision_quality = int(P_['colq'])
        cs.use_self_collision = P_['selfcol']
        cs.self_distance_min = P_['selfdist']
        cs.self_friction = P_['selffric']
        cs.vertex_group_self_collisions = 'noself'
        cl.point_cache.frame_start = 1
        cl.point_cache.frame_end = SIM_FRAMES
        out = [v.co.copy() for v in me.vertices]
        if SIM_FRAMES > 0:
            for fr in range(1, SIM_FRAMES + 1):
                scene.frame_set(fr)
            dg = bpy.context.evaluated_depsgraph_get()
            ev = sim.evaluated_get(dg)
            em = ev.to_mesh()
            out = [v.co.copy() for v in em.vertices]
            ev.to_mesh_clear()
        for i, co in enumerate(out):
            draped[v0 + i] = co.copy()
        # freeze as a static two-sided collider for the lanyards settling over it
        sim.modifiers.clear()
        for i, co in enumerate(out):
            me.vertices[i].co = co
        me.update()
        add_collision(sim, friction=CLOTH['friction'])
        sim.collision.thickness_outer = 0.0012
        sim.collision.thickness_inner = 0.0012
        if hasattr(sim.collision, 'use_culling'):
            sim.collision.use_culling = False
        sim.hide_render = True
        st_ = max(((draped[a] - draped[b]).length / max(1e-9, (verts[a] - verts[b]).length))
                  for f in faces[f0:f1] for a, b in zip(f, f[1:] + f[:1]))
        print(f'SIMSEQ {rd["spec"]["name"]} stretch {st_:.3f}')
        scene.frame_set(1)
    stretch = max(((draped[a] - draped[b]).length / max(1e-9, (verts[a] - verts[b]).length))
                  for f in faces for a, b in zip(f, f[1:] + f[:1]))
    print(f'SIM frames {SIM_FRAMES}: max edge stretch {stretch:.3f}')
    for li, (v0, v1, f0, f1) in enumerate(ranges):
        st_ = max(((draped[a] - draped[b]).length / max(1e-9, (verts[a] - verts[b]).length))
                  for f in faces[f0:f1] for a, b in zip(f, f[1:] + f[:1]))
        worst = max(((draped[a] - draped[b]).length / max(1e-9, (verts[a] - verts[b]).length), a)
                    for f in faces[f0:f1] for a, b in zip(f, f[1:] + f[:1]))
        print(f'SIM {rib_data[li]["spec"]["name"]} stretch {st_:.3f} at z {draped[worst[1]].z:.4f}')
    scene.frame_start = 0
    scene.frame_set(0)
    # the room/lamp reference frame values used below
    C = O.to_2d()
    ct = neck_c + NR
    base_c = Vector(meas['base_c'])

    # ------------------------------------------------------------------ root, rig
    root_loc = Vector((C.x, C.y, ct))
    root = bpy.data.objects.new('NEW_medals_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.03
    root.location = root_loc
    root['parent_to'] = 'NEW_lamp_pivot'      # parent (keep transform) to the lamp's tilt pivot in the room
    coll.objects.link(root)
    arm_data = bpy.data.armatures.new('NEW_medals_rig')
    rig = bpy.data.objects.new('NEW_medals_rig', arm_data)
    coll.objects.link(rig)
    rig.parent = root
    rig.show_in_front = True
    bpy.context.view_layer.update()

    # hardware / medal placement per ribbon
    hw_info = []
    for rd in rib_data:
        spec = rd['spec']
        d3, e3 = rd['d'], rd['e']
        crimp = rd['crimp']
        cam_dir = (SEAT - crimp)
        cam_dir.z = 0
        cam_dir.normalize()
        # chain axes: crimp loop axis d; jump ring e; (second ring d; eye e) or eye d
        axes = [d3, e3, d3, e3] if spec['rot90'] else [d3, e3, d3]
        L0 = crimp - Z * (0.0065 + 0.0014) * K
        r_c, m_c = 0.0019 * K, 0.00055 * K
        Rj, mj = 0.0031 * K, 0.0005 * K
        re, me_ = 0.0019 * K, 0.00065 * K
        centers = [L0]
        top_wire = L0 - Z * (r_c - m_c - mj)
        J1 = top_wire - Z * Rj
        centers.append(J1)
        prev_R, prev_m = Rj, mj
        if spec['rot90']:
            top_wire = J1 - Z * (Rj - mj - mj)
            J2 = top_wire - Z * Rj
            centers.append(J2)
        last = centers[-1]
        top_wire = last - Z * (Rj - mj - me_)
        Ec = top_wire - Z * re
        Mc = Ec - Z * (re + spec['R'] - 0.0007 * K)
        n_front = d3.copy()          # the flipped medal shows its back
        hw_info.append(dict(L0=L0, centers=centers, axes=axes, Ec=Ec, Mc=Mc, n=n_front))
        rs = meas['base_top']
        low = Mc.z - spec['R']
        rad = (Mc.to_2d() - base_c).length
        print(f'MEDAL {spec["name"]} centre {tuple(round(x, 4) for x in Mc)} bottom z {low:.4f} '
              f'radial-from-base {rad * 1000:.0f}mm (base r {meas["base_r"] * 1000:.0f}mm top {rs:.4f})')

    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones
    inv = root.matrix_world.inverted()
    broot = eb.new('root')
    broot.head = inv @ root_loc
    broot.tail = inv @ (root_loc + Z * 0.03)
    pivots = []
    for rd, hw in zip(rib_data, hw_info):
        nm = rd['spec']['name']
        piv = rd['pivot'].copy()
        pivots.append(piv)
        bt = eb.new('tail_' + nm)
        bt.head = inv @ piv
        bt.tail = inv @ rd['crimp']
        bt.parent = broot
        bm_ = eb.new('medal_' + nm)
        bm_.head = inv @ hw['L0']
        bm_.tail = inv @ hw['Mc']
        bm_.parent = bt
    bpy.ops.object.mode_set(mode='OBJECT')

    # ------------------------------------------------------------------ ribbon objects
    def smooth01(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    tris = {}
    objs = []
    for idx, (rd, (v0, v1, f0, f1)) in enumerate(zip(rib_data, ranges)):
        spec = rd['spec']
        nm = spec['name']
        vs = [draped[i] - root_loc for i in range(v0, v1)]
        fs = [tuple(i - v0 for i in faces[j]) for j in range(f0, f1)]
        me = bpy.data.meshes.new(f'medal_{nm}_ribbon')
        me.from_pydata([tuple(v) for v in vs], [], fs)
        me.update()
        band_names = spec['bands']
        uniq = []
        for bn in band_names:
            if bn not in uniq:
                uniq.append(bn)
        for bn in uniq:
            me.materials.append(M['ribbon_' + bn])
        for j, p in enumerate(me.polygons):
            p.material_index = uniq.index(band_names[fmats[f0 + j]])
        uvl = me.uv_layers.new(name='UVMap')
        for j, p in enumerate(me.polygons):
            for li, loop_i in enumerate(p.loop_indices):
                uvl.data[loop_i].uv = uvs[f0 + j][li]
        o = bpy.data.objects.new(f'medal_{nm}_ribbon', me)
        coll.objects.link(o)
        o.parent = rig
        sm = o.modifiers.new('solidify', 'SOLIDIFY')
        sm.thickness = 0.0007 * K
        sm.offset = 0.0
        sm.use_rim = True
        sm.use_even_offset = False
        sm.use_quality_normals = True
        dg = bpy.context.evaluated_depsgraph_get()
        new_me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        o.modifiers.remove(sm)
        old = o.data
        o.data = new_me
        bpy.data.meshes.remove(old)
        new_me.name = f'medal_{nm}_ribbon'
        new_me.shade_smooth()
        new_me.set_sharp_from_angle(angle=math.radians(60))
        # weights: loops stay on root; tails below the collar swing with their bone
        g_root = o.vertex_groups.new(name='root')
        g_tail = o.vertex_groups.new(name='tail_' + nm)
        zp = pivots[idx].z - root_loc.z
        for v in new_me.vertices:
            w = smooth01((zp - v.co.z) / 0.03)
            if w < 1:
                g_root.add([v.index], 1 - w, 'REPLACE')
            if w > 0:
                g_tail.add([v.index], w, 'REPLACE')
        objs.append(o)
        tris[o.name] = sum(len(p.vertices) - 2 for p in new_me.polygons)

    # ------------------------------------------------------------------ hardware + medal objects
    metal_sets = {'gold': ('gold', 'gold_satin'), 'silver': ('silver', 'silver_satin'),
                  'bronze': ('bronze', 'bronze_satin')}
    for rd, hw in zip(rib_data, hw_info):
        spec = rd['spec']
        nm = spec['name']
        d3, e3 = rd['d'], rd['e']
        mbh = MB()
        fr = Matrix.Translation(rd['crimp'] - Z * 0.00325 * K - root_loc) @ Matrix((
            (e3.x, d3.x, 0, 0), (e3.y, d3.y, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
        rounded_box(mbh, fr, (W + 0.0017 * K, 0.0031 * K, 0.0065 * K), 0.0007 * K, mat=0)
        # a pressed groove line on the crimp: two thin raised ridges
        for zz in (0.0014 * K, -0.0016 * K):
            fr2 = fr @ Matrix.Translation((0, 0, zz))
            rounded_box(mbh, fr2, (W + 0.0019 * K, 0.0033 * K, 0.0005 * K), 0.0002 * K, mat=0)
        torus(mbh, hw['L0'] - root_loc, hw['axes'][0], 0.0019 * K, 0.00055 * K, seg=16, segm=8)
        torus(mbh, hw['centers'][1] - root_loc, hw['axes'][1], 0.0031 * K, 0.0005 * K, seg=22, segm=8)
        if spec['rot90']:
            torus(mbh, hw['centers'][2] - root_loc, hw['axes'][2], 0.0031 * K, 0.0005 * K, seg=22, segm=8)
        crimp_obj = mbh.to_object(f'medal_{nm}_clasp', [M['nickel']], coll, smooth_angle=40)
        crimp_obj.parent = rig
        # medal
        pm, sm_ = metal_sets[spec['metal']]
        mbm = medal_mesh(spec['R'] / K, spec['relief'])
        n = hw['n']
        x = n.cross(Z).normalized()
        xf = Matrix.Translation(hw['Mc'] - root_loc) @ Matrix((
            (x.x, n.x, 0, 0), (x.y, n.y, 0, 0), (x.z, n.z, 1, 0), (0, 0, 0, 1))) @ Matrix.Scale(K, 4)
        mbx = MB()
        mbx.extend(mbm, xf=xf)
        eye_axis = hw['n']
        torus(mbx, hw['Ec'] - root_loc, eye_axis, 0.0019 * K, 0.00065 * K, seg=16, segm=8, mat=0)
        med = mbx.to_object(f'medal_{nm}_disc', [M[pm], M[sm_]], coll, smooth_angle=38)
        med.parent = rig
        for o, bn in ((crimp_obj, 'tail_' + nm), (med, 'medal_' + nm)):
            vg = o.vertex_groups.new(name=bn)
            vg.add(list(range(len(o.data.vertices))), 1.0, 'REPLACE')
        # clasp rings follow the medal bone so the chain swings as one
        ring_vg = crimp_obj.vertex_groups.new(name='medal_' + nm)
        L0l = hw['L0'] - root_loc
        ring_ids = [v.index for v in crimp_obj.data.vertices if v.co.z < L0l.z - 0.0009 * K]
        crimp_obj.vertex_groups['tail_' + nm].remove(ring_ids)
        ring_vg.add(ring_ids, 1.0, 'REPLACE')
        objs += [crimp_obj, med]
        tris[crimp_obj.name] = sum(len(p.vertices) - 2 for p in crimp_obj.data.polygons)
        tris[med.name] = sum(len(p.vertices) - 2 for p in med.data.polygons)

    for o in objs:
        am = o.modifiers.new('Armature', 'ARMATURE')
        am.object = rig
        am.use_vertex_groups = True

    # ------------------------------------------------------------------ sway animation
    rig.animation_data_create()
    # neighbours sway nearly together (a shared draft), so adjacent medals never close on each other
    phases = [0.0, 1.6, 3.1, 4.7]
    # (swing about the across-bar axis, swing about the bar axis, medal twist, medal lag) in degrees
    amp = {'m1': (1.6, 0.5, 1.5, 0.6), 'm2': (1.6, 0.5, 1.5, 0.6), 'm3': (1.6, 0.5, 1.5, 0.6),
           'm4': (1.6, 0.5, 1.5, 0.6)}
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    for f in range(0, LOOP_FRAMES + 1, 2):
        t = 2 * math.pi * f / LOOP_FRAMES
        for i, rd in enumerate(rib_data):
            nm = rd['spec']['name']
            A_side, A_io, A_tw, A_lag = amp[nm]
            A_io, A_tw, A_lag = A_io * AMP_K, A_tw * AMP_K, A_lag * AMP_K
            ph = phases[i]
            # identical for every lanyard: the stacked tails are layered 1-3 mm apart and move together
            side = A_side * (math.sin(t) + 0.22 * math.sin(2 * t + 0.7))
            io = A_io * math.sin(t + 1.1)
            Rw = Quaternion(rd['d'], math.radians(side)) @ Quaternion(rd['e'], math.radians(io))
            pb = rig.pose.bones['tail_' + nm]
            B = pb.bone.matrix_local.to_3x3()
            pb.rotation_quaternion = (B.inverted() @ Rw.to_matrix() @ B).to_quaternion()
            pb.keyframe_insert('rotation_quaternion', frame=f)
            tw = A_tw * (math.sin(t + ph - 0.9) + 0.18 * math.sin(2 * t + ph))
            lag = A_lag * math.sin(t + ph - 1.2)
            Rm = Quaternion(Z, math.radians(tw)) @ Quaternion(rd['d'], math.radians(lag))
            pb = rig.pose.bones['medal_' + nm]
            B = pb.bone.matrix_local.to_3x3()
            pb.rotation_quaternion = (B.inverted() @ Rm.to_matrix() @ B).to_quaternion()
            pb.keyframe_insert('rotation_quaternion', frame=f)
    act = rig.animation_data.action
    act.name = 'medals_sway'
    act.use_frame_range = True
    if hasattr(act, 'use_cyclic'):
        act.use_cyclic = True
    act.frame_range = (0, LOOP_FRAMES)
    scene.frame_set(0)

    # clearance to the lamp arm (lamp003 = arm bars, collar, stem) across the sway loop
    fixed_parts = tuple(n for n in meas['ref'] if n != 'lamp_neck')
    av, af = [], []
    for n in fixed_parts:
        lv = meas['ref'][n]
        base_i = len(av)
        av += [Vector(v) for v in lv['verts']]
        af += [tuple(i + base_i for i in f) for f in lv['faces']]
    tree = BVHTree.FromPolygons(av, af)
    worst = {}
    for f in (0, 24, 48, 72):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for o in objs:
            ev = o.evaluated_get(dg)
            m = ev.to_mesh()
            mw = ev.matrix_world
            dmin = min(tree.find_nearest(mw @ v.co)[3] for v in m.vertices)
            ev.to_mesh_clear()
            worst[o.name] = min(worst.get(o.name, 1.0), dmin)
    # hardware-to-hardware gaps between neighbouring lanyards across the sway
    gap = 1.0
    gap_pair = None
    hw_objs = [o for o in objs if o.name.endswith(('_clasp', '_disc', '_ribbon'))]
    for f in range(0, LOOP_FRAMES, 8):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        trees = {}
        for o in hw_objs:
            ev = o.evaluated_get(dg)
            m = ev.to_mesh()
            trees[o.name] = ([ev.matrix_world @ v.co for v in m.vertices],
                             BVHTree.FromPolygons([ev.matrix_world @ v.co for v in m.vertices],
                                                  [tuple(p.vertices) for p in m.polygons]))
            ev.to_mesh_clear()
        names = list(trees)
        for i in range(len(names)):
            for j in range(len(names)):
                if names[i].split('_')[1] == names[j].split('_')[1]:
                    continue
                gd = min(trees[names[j]][1].find_nearest(v)[3] for v in trees[names[i]][0])
                if gd < gap:
                    gap = gd
                    gap_pair = (names[i], names[j], f)
    print(f'CLEARANCE between different lanyards over the loop: {gap * 1000:.1f} mm {gap_pair}')
    scene.frame_set(0)
    print('CLEARANCE to column/knuckle/head/diffuser/base (mm)', {k: round(v * 1000, 1) for k, v in worst.items()})
    total = sum(tris.values())
    print('TRIS', total, json.dumps(tris))
    return dict(scene=scene, coll=coll, work=work, refc=refc, rib=rib_data, hw=hw_info, root=root, rig=rig,
                objs=objs, tris=tris, total=total, meas=meas, C=C, ct=ct)


# =============================================================================== previews
def setup_render(scene):
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    for dv in prefs.devices:
        dv.use = dv.type == 'OPTIX'
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


def add_light(scene, name, loc, target, power, size, colour=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = power
    ld.size = size
    ld.color = colour
    o = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o


def previews(b):
    scene = b['scene']
    setup_render(scene)
    scene.cycles.samples = 64
    refc = b['refc']
    c = b['C']
    desk = bpy.data.meshes.new('ref_desk')
    desk.from_pydata([(c.x - 0.8, c.y - 0.8, 0.735), (c.x + 0.8, c.y - 0.8, 0.735),
                      (c.x + 0.8, c.y + 0.8, 0.735), (c.x - 0.8, c.y + 0.8, 0.735)], [], [(0, 1, 2, 3)])
    dm = bpy.data.materials.new('ref_desk')
    dm.use_nodes = True
    principled(dm).inputs['Base Color'].default_value = (0.62, 0.33, 0.22, 1)
    principled(dm).inputs['Roughness'].default_value = 0.55
    desk.materials.append(dm)
    refc.objects.link(bpy.data.objects.new('ref_desk', desk))
    target = sum((h['Mc'] for h in b['hw']), Vector()) / len(b['hw'])
    low = min(h['Mc'].z - rd['spec']['R'] for h, rd in zip(b['hw'], b['rib']))
    target.z = (low + b['ct']) / 2
    add_light(scene, 'key', target + Vector((0.45, -0.55, 0.45)), target, 22, 0.35)
    add_light(scene, 'fill', target + Vector((-0.6, -0.35, 0.15)), target, 7, 0.6, (0.9, 0.95, 1.0))
    add_light(scene, 'rim', target + Vector((-0.2, 0.6, 0.35)), target, 20, 0.3, (1.0, 0.95, 0.9))
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam

    def shot(loc, tgt, lens, fname, frame=0):
        scene.frame_set(frame)
        cam.location = loc
        cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, fname)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', fname)
    dirv = (target - SEAT).normalized()
    side_dir = Vector((-dirv.y, dirv.x, 0)).normalized()
    shot(SEAT, target + Vector((0, 0, 0.01)), 75, 'medals_seat.png', 0)
    three_q = (-dirv * 0.75 + side_dir * 0.62).normalized()
    shot(target + three_q * 0.42 + Vector((0, 0, 0.07)), target, 50, 'medals_34.png', 0)
    shot(target + side_dir * 0.62 + Vector((0, 0, 0.05)), target, 45, 'medals_side.png', 0)


# =============================================================================== save / export / verify
def finish(b):
    for o in list(b['work'].objects) + list(b['refc'].objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for cn in ('WORK_medals', 'REF_lamp'):
        c = bpy.data.collections.get(cn)
        if c:
            bpy.data.collections.remove(c)
    for o in list(bpy.context.scene.objects):
        if o.type in ('LIGHT', 'CAMERA'):
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    bpy.context.scene.frame_set(0)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    print('SAVED', OUT_BLEND)
    for o in bpy.context.scene.objects:
        o.select_set(o.name in b['coll'].all_objects)
    kw = dict(filepath=OUT_GLB, export_format='GLB', use_selection=True, export_yup=True,
              export_apply=False, export_animations=True, export_skins=True, export_materials='EXPORT',
              export_cameras=False, export_lights=False, export_force_sampling=True)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError as err:
        print('gltf kw issue', err)
        for k in ('export_force_sampling',):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    print('EXPORTED', OUT_GLB, os.path.getsize(OUT_GLB) // 1024, 'KB')


def verify():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=OUT_GLB)
    scene = bpy.context.scene
    arms = [o for o in scene.objects if o.type == 'ARMATURE']
    meshes = [o for o in scene.objects if o.type == 'MESH']
    acts = [(a.name, tuple(a.frame_range)) for a in bpy.data.actions]
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    print('VERIFY armatures', [(a.name, len(a.data.bones)) for a in arms], 'meshes', len(meshes), 'tris', tris)
    print('VERIFY actions', acts)
    probe = next(o for o in meshes if 'm3_disc' in o.name or o.name.endswith('m3_disc'))

    def centre(f):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = probe.evaluated_get(dg)
        m = ev.to_mesh()
        c = sum((ev.matrix_world @ v.co for v in m.vertices), Vector()) / len(m.vertices)
        ev.to_mesh_clear()
        return c
    fr = [int(x) for x in bpy.data.actions[0].frame_range] if bpy.data.actions else [0, 0]
    c0 = centre(fr[0])
    c1 = centre(fr[0] + (fr[1] - fr[0]) // 3)
    c2 = centre(fr[1])
    print(f'VERIFY probe {probe.name}: moved {(c1 - c0).length * 1000:.2f} mm mid-loop, '
          f'loop closure error {(c2 - c0).length * 1000:.3f} mm')


if __name__ == '__main__':
    b = build()
    if '--sim-only' in ARGS:
        raise SystemExit(0)
    if not NO_RENDER:
        previews(b)
    finish(b)
    verify()
    print('DONE')
