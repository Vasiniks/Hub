"""
v2_medals.py -- medals on real fabric lanyards, draped over the desk lamp's arm by cloth simulation.

    blender -b --factory-startup --python blender/scripts/v2_medals.py -- [--no-render]

What it does, in order:
  1. Opens blender/scene/room.blend READ-ONLY and measures the lamp head: the long flat
     horizontal blade at the top of the lamp (its axis points at the seated viewer).
     Nothing is ever saved back to room.blend.
  2. Builds four lanyard strips (22.5 mm woven ribbon) looped over that bar, spaced along it,
     each following the taut path from its crimp end over the bar and back.
  3. Cloth-simulates each lanyard against a lofted collision proxy of the head (patch lying on
     top of the bar and the crimp ends pinned) and bakes the settled drape into plain meshes.
  4. Builds the metal: crimp ends, jump rings and medals (raised rim, relief face, eye loop).
  5. Rigs one bone chain per medal (tail swing + medal twist) and keys a 4 s seamless sway loop.
  6. Renders previews, saves blender/scene/parts/medals.blend (collection NEW_medals, root empty
     NEW_medals_root), exports medals.glb with the animation, and re-imports it to verify.

All coordinates are ROOM world coordinates (Z-up, metres).
"""
import bpy
import bmesh
import math
import os
import sys
import json
from mathutils import Vector, Matrix, Quaternion
from mathutils.geometry import convex_hull_2d

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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
LOOP_FRAMES = 96          # 4 s
SIM_FRAMES = int(ARGS[ARGS.index('--sim-frames') + 1]) if '--sim-frames' in ARGS else 70
K = 1.2                   # owner: medals 20% bigger (ribbons, clasps, medals)
RIBBON_W = 0.0225 * K     # 27 mm lanyard
ROW_STEP = 0.003          # ribbon rows every 3 mm
Z = Vector((0, 0, 1))
CLOTH = dict(quality=16, time_scale=1.0, mass=0.0015, air=2.0, tension=60.0, shear=25.0, bend=0.25, damp=8.0, bend_damp=0.8,
             pin=3.0, coldist=0.001, colq=10, selfcol=False, selfdist=0.0004, selffric=6.0, friction=8.0)


def hex_rgb(h):
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


# =============================================================================== 1. measure
LAMP_BLEND = os.path.join(PARTS, 'lamp.blend')     # the fixed lamp (v2_lamp_fixed.py)


def measure(refc):
    """Append the fixed lamp (NEW_lamp) into REF_lamp for context and read its world geometry."""
    with bpy.data.libraries.load(LAMP_BLEND, link=False) as (src, dst):
        dst.objects = list(src.objects)
    for o in dst.objects:
        if o is not None:
            refc.objects.link(o)
    bpy.context.view_layer.update()
    out = {'ref': {}}
    for o in refc.objects:
        if o.type == 'MESH':
            mw = o.matrix_world
            out['ref'][o.name] = dict(verts=[tuple(mw @ v.co) for v in o.data.vertices],
                                      faces=[tuple(p.vertices) for p in o.data.polygons])
    bv = [Vector(v) for v in out['ref']['lamp_base']['verts']]
    out['base_top'] = max(v.z for v in bv)
    top = [v for v in bv if v.z > out['base_top'] - 0.004]
    cx = (min(v.x for v in top) + max(v.x for v in top)) / 2
    cy = (min(v.y for v in top) + max(v.y for v in top)) / 2
    out['base_c'] = (cx, cy)
    out['base_r'] = max(math.hypot(v.x - cx, v.y - cy) for v in top)
    return out


# =============================================================================== 2D helpers
def cross2(a, b):
    return a.x * b.y - a.y * b.x


def clean_poly(pts, tol=0.0004):
    out = []
    for p in pts:
        p = Vector(p).to_2d()
        if not out or (p - out[-1]).length > tol:
            out.append(p)
    while len(out) > 2 and (out[0] - out[-1]).length < tol:
        out.pop()
    area = sum(cross2(out[i], out[(i + 1) % len(out)]) for i in range(len(out)))
    if area < 0:
        out.reverse()
    return out


def offset_poly(poly, off, arc_step=math.radians(10)):
    n = len(poly)
    res = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        ei = (p1 - p0).normalized()
        eo = (p2 - p1).normalized()
        a0 = math.atan2(-ei.x, ei.y)
        a1 = math.atan2(-eo.x, eo.y)
        da = (a1 - a0) % (2 * math.pi)
        if da > math.pi:
            da -= 2 * math.pi
        steps = max(1, int(abs(da) / arc_step))
        for s in range(steps + 1):
            a = a0 + da * s / steps
            res.append(p1 + Vector((math.cos(a), math.sin(a))) * off)
    return clean_poly(res, 0.0002)


def resample_closed(poly, step):
    pts = poly + [poly[0]]
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    total = L[-1]
    n = max(12, int(total / step))
    out, j = [], 0
    for k in range(n):
        s = total * k / n
        while L[j + 1] < s:
            j += 1
        t = (s - L[j]) / (L[j + 1] - L[j]) if L[j + 1] > L[j] else 0.0
        out.append(pts[j].lerp(pts[j + 1], t))
    return out


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


def centroid(poly):
    """Area centroid (a vertex average is biased by densely sampled round ends)."""
    A, cx, cy = 0.0, 0.0, 0.0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        c = cross2(p, q)
        A += c
        cx += (p.x + q.x) * c
        cy += (p.y + q.y) * c
    A *= 0.5
    return Vector((cx / (6 * A), cy / (6 * A)))


# =============================================================================== ribbon path
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
    """ctrl: [(pos Vector3, width Vector3)] -> resampled rows [(pos, width_unit, s)]."""
    P = [c[0] for c in ctrl]
    W = [c[1].normalized() for c in ctrl]
    dense = []
    for pos, i, t in cr_chain(P):
        dense.append((pos, slerp_vec(W[i], W[min(i + 1, len(W) - 1)], t)))
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
                     slerp_vec(dense[j][1], dense[j + 1][1], t), s])
    for k in range(len(rows)):
        a = rows[max(k - 1, 0)][0]
        b = rows[min(k + 1, len(rows) - 1)][0]
        tan = (b - a).normalized()
        w = rows[k][1]
        w = (w - tan * w.dot(tan)).normalized()
        rows[k][1] = w
    return rows, total


# =============================================================================== specs
# d: exit direction in collar frame ('b' = long face toward the seat, 'a' = far round end)
SPECS = [
    # Spread along the lamp's long horizontal head bar (s = along the bar, + toward its free tip /
    # the seat; t = crimp offset across it; drop = crimp top below the bar underside). 37 mm pitch
    # keeps the 29 mm crimps clear while they sway. Nearest the seat hangs shortest, so they cascade.
    dict(name='m1', s=0.140, t=0.021, drop=0.080, R=0.0205 * 1.2, metal='gold', relief='blank',
         cols=[0, .34, .66, 1], bands=['blue', 'blue', 'blue'], twA=8, twB=-5, rot90=True),
    dict(name='m2', s=0.103, t=0.007, drop=0.109, R=0.0195 * 1.2, metal='silver', relief='blank',
         cols=[0, .34, .66, 1], bands=['red', 'red', 'red'], twA=-6, twB=10, rot90=True),
    dict(name='m3', s=0.066, t=-0.007, drop=0.138, R=0.0195 * 1.2, metal='silver', relief='blank',
         cols=[0, .34, .66, 1], bands=['red', 'red', 'red'], twA=11, twB=-7, rot90=True),
    dict(name='m4', s=0.029, t=-0.021, drop=0.167, R=0.0195 * 1.2, metal='silver', relief='blank',
         cols=[0, .34, .66, 1], bands=['red', 'red', 'red'], twA=-8, twB=6, rot90=True),
]
RIBBON_HEX = dict(blue='#1d3a8a', white='#e9e7e0', red='#a81c26', gold='#d9a92e', green='#17613a')


# =============================================================================== mesh builder
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


# =============================================================================== materials
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


# =============================================================================== medal geometry
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


# =============================================================================== scene helpers
def link_new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def prism(name, poly, z0, z1, coll, shift=None):
    """Vertical (or sheared) prism from a 2D polygon."""
    shift = shift or Vector((0, 0))
    bm = bmesh.new()
    b = [bm.verts.new((p.x, p.y, z0)) for p in poly]
    t = [bm.verts.new((p.x + shift.x * (z1 - z0), p.y + shift.y * (z1 - z0), z1)) for p in poly]
    n = len(poly)
    bm.faces.new(list(reversed(b)))
    bm.faces.new(t)
    for i in range(n):
        bm.faces.new([b[i], b[(i + 1) % n], t[(i + 1) % n], t[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    return o


def circle_poly(c, r, n=32):
    return [Vector((c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)))
            for i in range(n)]


def add_collision(o, friction=8.0):
    o.modifiers.new('Collision', 'COLLISION')
    o.collision.thickness_outer = 0.0004
    o.collision.thickness_inner = 0.002
    o.collision.cloth_friction = friction
    o.collision.damping = 0.5


# =============================================================================== main build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start = 0
    scene.frame_end = LOOP_FRAMES
    M = build_materials()

    # ------------------------------------------------------------------ collections
    coll = link_new_collection('NEW_medals')
    work = link_new_collection('WORK_medals')      # proxies + sim; deleted before save
    refc = link_new_collection('REF_lamp')         # fixed lamp for measuring + previews; deleted before save
    meas = measure(refc)

    # ------------------------------------------------------------------ head bar frame
    # The lamp's top horizontal bar is its head: an elongated flat blade. Frame: s along the bar
    # (toward its free tip, which points at the seat), t across it, z up.
    headv = [Vector(v) for n in ('lamp_head', 'lamp_head_trim', 'lamp_diffuser_bezel', 'lamp_diffuser_disc')
             for v in meas['ref'][n]['verts']]
    hv = [Vector(v) for v in meas['ref']['lamp_head']['verts']]
    hc = Vector((sum(v.x for v in hv) / len(hv), sum(v.y for v in hv) / len(hv)))
    sxx = sum((v.x - hc.x) ** 2 for v in hv)
    syy = sum((v.y - hc.y) ** 2 for v in hv)
    sxy = sum((v.x - hc.x) * (v.y - hc.y) for v in hv)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    a2 = Vector((math.cos(ang), math.sin(ang)))
    if a2.dot(SEAT.to_2d() - hc) < 0:
        a2 = -a2
    b2 = Vector((-a2.y, a2.x))
    a3, b3 = a2.to_3d(), b2.to_3d()

    def to_w(s, t, z):
        return Vector((hc.x, hc.y, 0)) + a3 * s + b3 * t + Z * z

    def stc(v):
        q = v.to_2d() - hc
        return q.dot(a2), q.dot(b2), v.z
    HS = [stc(v) for v in headv]
    s_lo, s_hi = min(h[0] for h in HS), max(h[0] for h in HS)

    def section(s, half):
        """Convex cross-section (t, z) of the head near station s; widens until the STL gives one."""
        while True:
            pts = [Vector((h[1], h[2])) for h in HS if abs(h[0] - s) <= half]
            if len(pts) >= 3:
                poly = clean_poly([pts[i] for i in convex_hull_2d(pts)], 0.0003)
                if len(poly) >= 3 and abs(sum(cross2(poly[i], poly[(i + 1) % len(poly)])
                                              for i in range(len(poly)))) > 2e-6:
                    return poly
            half *= 1.5

    def resample_ang(poly, n=32):
        c = centroid(poly)
        out = []
        for k in range(n):
            d = Vector((math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n)))
            t = ray_poly(poly, c, d)
            out.append(c + d * t)
        return out
    ct = max(h[2] for h in HS)
    C = hc
    print(f'HEAD centre {tuple(round(x, 4) for x in hc)} axis {tuple(round(x, 4) for x in a2)} '
          f's[{s_lo:.3f},{s_hi:.3f}] top {ct:.4f}')

    # ------------------------------------------------------------------ collision proxy (lofted head)
    st_list = [s_lo + 0.004 + i * 0.008 for i in range(int((s_hi - s_lo - 0.008) / 0.008) + 1)]
    rings = [resample_ang(section(s, 0.0045)) for s in st_list]
    bm = bmesh.new()
    vr = [[bm.verts.new(to_w(s, p.x, p.y)) for p in ring] for s, ring in zip(st_list, rings)]
    for r in range(len(vr) - 1):
        for k in range(32):
            bm.faces.new([vr[r][k], vr[r][(k + 1) % 32], vr[r + 1][(k + 1) % 32], vr[r + 1][k]])
    bm.faces.new(vr[0])
    bm.faces.new(list(reversed(vr[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    pme = bpy.data.meshes.new('proxy_head')
    bm.to_mesh(pme)
    bm.free()
    proxy = bpy.data.objects.new('proxy_head', pme)
    work.objects.link(proxy)
    add_collision(proxy)
    proxy.hide_render = True
    prox = [proxy]

    # ------------------------------------------------------------------ lanyard paths
    W = RIBBON_W
    rib_data = []
    for spec in SPECS:
        s0 = spec['s']
        sec = section(s0, W / 2 + 0.002)
        zbot = min(p.y for p in sec)
        ztop = max(p.y for p in sec)
        outline = resample_closed(offset_poly(sec, 0.0032), 0.0012)
        zc = zbot - spec['drop']
        Q = Vector((spec['t'], zc - 0.0026 * K))
        angs = [math.atan2(p.y - Q.y, p.x - Q.x) for p in outline]
        i_r = min(range(len(outline)), key=lambda i: angs[i])      # +t side tangent point
        i_l = max(range(len(outline)), key=lambda i: angs[i])      # -t side tangent point
        N = len(outline)
        i_top = max(range(N), key=lambda i: outline[i].y)
        arc, i = [], i_l
        while True:                                                # -t tangent -> over top -> +t tangent
            arc.append(i)
            if i == i_r:
                break
            i = (i - 1) % N
        if i_top not in arc:
            arc, i = [], i_l
            while True:
                arc.append(i)
                if i == i_r:
                    break
                i = (i + 1) % N

        def P3(t, z):
            return to_w(s0, t, z)
        legs = {}
        for side, tw, tan_i in ((-1, spec['twA'], i_l), (1, spec['twB'], i_r)):
            QA = P3(spec['t'] + side * 0.00055 * K, Q.y)
            Q2 = QA + Z * 0.011 * K
            T = P3(outline[tan_i].x, outline[tan_i].y)
            mid = Q2.lerp(T, 0.5)
            wm = Quaternion((T - Q2).normalized(), math.radians(tw)) @ a3
            legs[side] = [(QA, a3), (Q2, a3), (mid, wm)]
        over = [(P3(outline[k].x, outline[k].y), a3) for k in arc[::2]]
        if arc[-1] != arc[::2][-1]:
            over.append((P3(outline[arc[-1]].x, outline[arc[-1]].y), a3))
        ctrl = legs[-1] + over + list(reversed(legs[1]))
        rows, length = ribbon_rows(ctrl)
        crimp = P3(spec['t'], zc)
        rib_data.append(dict(spec=spec, rows=rows, length=length, d=b3.copy(), e=a3.copy(),
                             crimp=crimp, pivot=P3(spec['t'], zbot - 0.004), zbot=zbot, zk=ztop))
        print(f'RIBBON {spec["name"]} s={s0:.3f} t={spec["t"]:.3f} len={length * 100:.1f}cm rows={len(rows)} '
              f'bar z[{zbot:.4f},{ztop:.4f}] crimp z {zc:.4f}')

    # ------------------------------------------------------------------ strips
    verts, faces, fmats, uvs, pinw = [], [], [], [], []
    ranges = []
    for rd in rib_data:
        spec = rd['spec']
        cols = spec['cols']
        v0 = len(verts)
        f0 = len(faces)
        nr, nc = len(rd['rows']), len(cols)
        for (pos, w, s) in rd['rows']:
            for u in cols:
                verts.append(pos + w * ((u - 0.5) * W))
                ds = min(s, rd['length'] - s)
                w_end = 1.0 if ds < 0.0045 else max(0.0, 1.0 - (ds - 0.0045) / 0.008)
                # the patch lying flat on top of the bar is held; edges and tails drape freely
                w_top = 1.0 if pos.z > rd['zk'] - 0.001 else 0.0
                pinw.append(max(w_end, w_top))
        for r in range(nr - 1):
            for c in range(nc - 1):
                a = v0 + r * nc + c
                faces.append((a, a + 1, a + nc + 1, a + nc))
                fmats.append(c)
                sa, sb = rd['rows'][r][2], rd['rows'][r + 1][2]
                uvs.append([(cols[c] * W, sa), (cols[c + 1] * W, sa), (cols[c + 1] * W, sb), (cols[c] * W, sb)])
        ranges.append((v0, len(verts), f0, len(faces)))

    P_ = dict(CLOTH)
    for a in ARGS:
        if a.startswith('cloth.') and '=' in a:
            kk, vv = a[6:].split('=')
            P_[kk] = type(P_[kk])(float(vv)) if not isinstance(P_[kk], bool) else vv in ('1', 'true')
    print('CLOTH', P_)
    for o in prox:
        o.collision.cloth_friction = P_['friction']

    def run_cloth(idx):
        """Each lanyard settles on its own against the head proxy (they are spaced along the bar)."""
        v0, v1, f0, f1 = ranges[idx]
        me = bpy.data.meshes.new(f'sim_{idx}')
        me.from_pydata([tuple(verts[i]) for i in range(v0, v1)], [],
                       [tuple(i - v0 for i in faces[j]) for j in range(f0, f1)])
        me.update()
        sim = bpy.data.objects.new(f'sim_{idx}', me)
        work.objects.link(sim)
        vg = sim.vertex_groups.new(name='pin')
        for i in range(v0, v1):
            if pinw[i] > 0:
                vg.add([i - v0], pinw[i], 'REPLACE')
        cl = sim.modifiers.new('Cloth', 'CLOTH')
        s = cl.settings
        s.quality = int(P_['quality'])
        s.time_scale = P_['time_scale']
        s.mass = P_['mass']
        s.air_damping = P_['air']
        s.tension_stiffness = P_['tension']
        s.compression_stiffness = P_['tension']
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
        cl.point_cache.frame_start = 1
        cl.point_cache.frame_end = SIM_FRAMES
        scene.frame_set(1)
        for f in range(1, SIM_FRAMES + 1):
            scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = sim.evaluated_get(dg)
        em = ev.to_mesh()
        out = [v.co.copy() for v in em.vertices]
        ev.to_mesh_clear()
        bpy.data.objects.remove(sim, do_unlink=True)
        return out

    scene.frame_start = 1
    draped = [v.copy() for v in verts]
    if SIM_FRAMES > 0:
        for idx in range(len(rib_data)):
            out = run_cloth(idx)
            v0, v1, f0, f1 = ranges[idx]
            for i, co in enumerate(out):
                draped[v0 + i] = co
            st = max(((draped[a] - draped[b]).length / max(1e-9, (verts[a] - verts[b]).length))
                     for f in faces[f0:f1] for a, b in zip(f, f[1:] + f[:1]))
            mv = [(draped[i] - verts[i]).length for i in range(v0, v1)]
            print(f'SIM ribbon {rib_data[idx]["spec"]["name"]} stretch {st:.3f} '
                  f'max move {max(mv) * 1000:.1f} mean {sum(mv) / len(mv) * 1000:.1f} mm')
    scene.frame_start = 0
    scene.frame_set(0)
    base_c = Vector(meas['base_c'])

    # ------------------------------------------------------------------ root, rig
    root_loc = Vector((C.x, C.y, ct))
    root = bpy.data.objects.new('NEW_medals_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.03
    root.location = root_loc
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
        n_front = cam_dir.copy()
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
    phases = [0.0, 2.2, 4.1, 1.2]
    # (swing about the across-bar axis, swing about the bar axis, medal twist, medal lag) in degrees
    amp = {'m1': (0.35, 1.6, 5.0, 0.6), 'm2': (0.3, 1.4, 4.5, 0.5), 'm3': (0.4, 1.7, 5.5, 0.6),
           'm4': (0.3, 1.4, 5.0, 0.5)}
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    for f in range(0, LOOP_FRAMES + 1, 2):
        t = 2 * math.pi * f / LOOP_FRAMES
        for i, rd in enumerate(rib_data):
            nm = rd['spec']['name']
            A_side, A_io, A_tw, A_lag = amp[nm]
            ph = phases[i]
            side = A_side * (math.sin(t + ph) + 0.22 * math.sin(2 * t + 1.3 * ph + 0.7))
            io = A_io * math.sin(t + ph + 1.1)
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
    from mathutils.bvhtree import BVHTree
    fixed_parts = ('lamp_arm', 'lamp_column', 'lamp_collar_pivot', 'lamp_head_hinge', 'lamp_base')
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
                gap = min(gap, min(trees[names[j]][1].find_nearest(v)[3] for v in trees[names[i]][0]))
    print(f'CLEARANCE between different lanyards over the loop: {gap * 1000:.1f} mm')
    scene.frame_set(0)
    print('CLEARANCE to arm/column/hinge/base (mm)', {k: round(v * 1000, 1) for k, v in worst.items()})
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
    refc = b['refc']
    desk = bpy.data.meshes.new('ref_desk')
    c = b['C']
    desk.from_pydata([(c.x - 0.6, c.y - 0.6, 0.735), (c.x + 0.6, c.y - 0.6, 0.735),
                      (c.x + 0.6, c.y + 0.6, 0.735), (c.x - 0.6, c.y + 0.6, 0.735)], [], [(0, 1, 2, 3)])
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
    shot(target - dirv * 0.58, target, 50, 'medals_closeup.png', 0)
    shot(target - dirv * 0.58, target, 50, 'medals_closeup_f48.png', 48)
    side_dir = Vector((-dirv.y, dirv.x, 0)).normalized()
    stgt = target.copy()
    shot(stgt + side_dir * 0.62 + Vector((0, 0, 0.06)), stgt, 45, 'medals_side.png', 0)
    shot(SEAT, target, 80, 'medals_seat.png', 0)


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
