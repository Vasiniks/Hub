"""
v2 telecaster: a Surf Green Telecaster-style guitar resting in a tubular tripod floor stand.

Everything is generated procedurally (no downloads). Geometry is authored in millimetres in a
guitar-local frame and scaled to metres on mesh creation.

Guitar-local frame (object space of the `NEW_telecaster_guitar` empty):
    +X  along the guitar, butt end at x=0, nut at x=780, headstock tip at x~965
    +Y  bass side (low E)
    +Z  out of the top; body back at z=0, body top at z=44.5
The guitar empty rotates that frame so the guitar stands up, front facing -Y, leaning back
ALPHA degrees into the stand. Stand geometry is authored directly in world space.

Output: blender/scene/parts/telecaster.blend with collection NEW_telecaster, root empty
NEW_telecaster_root at the floor-level centre of the stand's footprint, plus previews.

Run:
  blender -b --factory-startup --python blender/scripts/v2_telecaster.py -- [--views front,bridge] [--samples 64]
"""
import bpy
import bmesh
import math
import os
import sys
import time
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT_DIR = os.path.join(REPO, 'blender', 'scene', 'parts')
NAME = 'telecaster'
S = 0.001  # mm -> m


def cli():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    opts = {'views': 'front,bridge', 'samples': 64, 'norender': False}
    i = 0
    while i < len(a):
        if a[i] == '--views':
            opts['views'] = a[i + 1]; i += 2
        elif a[i] == '--samples':
            opts['samples'] = int(a[i + 1]); i += 2
        elif a[i] == '--norender':
            opts['norender'] = True; i += 1
        else:
            i += 1
    return opts


OPTS = cli()

# ------------------------------------------------------------------------------ dimensions
ALPHA = math.radians(16.0)      # lean of the guitar in the stand
BODY_T = 44.5                   # body thickness
ZTOP = BODY_T                   # body top
EDGE_R = 3.0                    # body edge radius
NUT_X = 780.0
SCALE = 648.0
ZFB = 53.5                      # fretboard crown height (flat Fender neck angle)
FB_R = 184.0                    # 7.25" fretboard radius
HS_FACE = 52.6                  # flat headstock face, level with the fretboard edges (no back angle)
HS_T = 14.5
PLATE_TOP = ZTOP + 1.2          # bridge base plate top
Z_SAD0 = 58.5                   # string underside at saddle, centre
R_BARREL = 3.9
FRET_H = 1.15
NUT_TOP = ZFB + 1.8             # string underside at nut, centre

N_FRETS = 21
BODY_SHIFT = 8.0                # body outline authored 0..406, shifted so the neck joins at fret 16
BODY_NECK_X = 399.0 - BODY_SHIFT


def fret_x(n):
    return NUT_X - SCALE * (1.0 - 2.0 ** (-n / 12.0))


FB_END = fret_x(N_FRETS) - 6.0

# strings: low E -> high E
GAUGE_IN = [0.046, 0.036, 0.026, 0.017, 0.013, 0.010]
R_STR = [g * 25.4 / 2 for g in GAUGE_IN]
WOUND = [True, True, True, False, False, False]
Y_BRIDGE = [27.0, 16.2, 5.4, -5.4, -16.2, -27.0]
Y_NUT = [17.5, 10.5, 3.5, -3.5, -10.5, -17.5]
SADDLE_X = [128.8, 130.0, 131.2]   # E/A, D/G, B/E barrels (compensated)
SADDLE_Y = [21.6, 0.0, -21.6]
POST_XN = [38, 61, 84, 107, 130, 153]
POST_Y = 14.0
POST_R = 2.9
TREE_X = NUT_X + 96
NECK_PU_X = 300.0
HOLE_X = 108.0

# ------------------------------------------------------------------------------ geometry core


class MB:
    """Minimal mesh builder: verts in mm, faces carry a material name."""

    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def vert(self, p):
        self.v.append(Vector((p[0], p[1], p[2])))
        return len(self.v) - 1

    def face(self, idx, mat):
        if len(set(idx)) < 3:
            return
        self.f.append(list(idx))
        self.m.append(mat)

    def add(self, other, M=None):
        off = len(self.v)
        for p in other.v:
            self.v.append((M @ p) if M is not None else p.copy())
        for f, m in zip(other.f, other.m):
            self.f.append([i + off for i in f])
            self.m.append(m)
        return self


def v2(p):
    return Vector((p[0], p[1]))


def catmull(pts, closed=True, n=8):
    P = [Vector(p) for p in pts]
    m = len(P)
    out = []
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p1, p2 = P[i], P[(i + 1) % m]
        p0 = P[(i - 1) % m] if (closed or i > 0) else 2 * p1 - p2
        p3 = P[(i + 2) % m] if (closed or i + 2 < m) else 2 * p2 - p1
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, 1e-4) ** 0.5
        t2 = t1 + max((p2 - p1).length, 1e-4) ** 0.5
        t3 = t2 + max((p3 - p2).length, 1e-4) ** 0.5
        for k in range(n):
            t = t1 + (t2 - t1) * k / n
            A1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            A2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            A3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            B1 = (t2 - t) / (t2 - t0) * A1 + (t - t0) / (t2 - t0) * A2
            B2 = (t3 - t) / (t3 - t1) * A2 + (t - t1) / (t3 - t1) * A3
            out.append((t2 - t) / (t2 - t1) * B1 + (t - t1) / (t2 - t1) * B2)
    if not closed:
        out.append(P[-1])
    return [tuple(v) for v in out]


def resample(P, step, closed=True):
    P = [Vector(p) for p in P]
    if closed:
        P = P + [P[0]]
    L = [0.0]
    for i in range(1, len(P)):
        L.append(L[-1] + (P[i] - P[i - 1]).length)
    total = L[-1]
    n = max(3, int(round(total / step)))
    out = []
    j = 0
    count = n if closed else n + 1
    for k in range(count):
        s = total * k / n
        while j < len(L) - 2 and L[j + 1] < s:
            j += 1
        seg = L[j + 1] - L[j]
        t = 0 if seg < 1e-9 else (s - L[j]) / seg
        out.append(tuple(P[j].lerp(P[j + 1], t)))
    return out


def area2(P):
    return 0.5 * sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1]
                     for i in range(len(P)))


def ccw(P):
    return list(P) if area2(P) > 0 else list(reversed(P))


def normals2(P):
    n = len(P)
    out = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        e1 = (b[0] - a[0], b[1] - a[1])
        e2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*e1) or 1
        l2 = math.hypot(*e2) or 1
        n1 = (e1[1] / l1, -e1[0] / l1)
        n2 = (e2[1] / l2, -e2[0] / l2)
        nx, ny = n1[0] + n2[0], n1[1] + n2[1]
        L = math.hypot(nx, ny)
        if L < 1e-9:
            nx, ny = n1
        else:
            nx, ny = nx / L, ny / L
        m = 1.0 / max(nx * n1[0] + ny * n1[1], 0.4)
        out.append((nx * m, ny * m))
    return out


def inset(P, d):
    N = normals2(P)
    return [(p[0] - n[0] * d, p[1] - n[1] * d) for p, n in zip(P, N)]


def round_rings(z0, z1, rt, rb, st=3, sb=3):
    R = []
    if rb > 0:
        for k in range(sb + 1):
            f = math.pi / 2 * k / sb
            R.append((rb * (1 - math.sin(f)), z0 + rb * (1 - math.cos(f))))
    else:
        R.append((0.0, z0))
    if rt > 0:
        for k in range(st + 1):
            f = math.pi / 2 * k / st
            R.append((rt * (1 - math.cos(f)), z1 - rt + rt * math.sin(f)))
    else:
        R.append((0.0, z1))
    return R


def slab(P, rings, mat, mat_top=None, mat_bot=None, cap_top=True, cap_bot=True):
    """Extrude a 2D outline through (inset, z) rings: rounded/chamfered edges for free."""
    P = ccw(P)
    mb = MB()
    idx = []
    for d, z in rings:
        Q = inset(P, d) if abs(d) > 1e-9 else P
        idx.append([mb.vert((q[0], q[1], z)) for q in Q])
    n = len(P)
    for j in range(len(rings) - 1):
        mm = mat(j) if callable(mat) else mat
        for i in range(n):
            mb.face([idx[j][i], idx[j][(i + 1) % n], idx[j + 1][(i + 1) % n], idx[j + 1][i]], mm)
    side = mat(0) if callable(mat) else mat
    if cap_bot:
        mb.face(list(reversed(idx[0])), mat_bot or side)
    if cap_top:
        mb.face(idx[-1], mat_top or side)
    return mb


def rrect(cx, cy, hx, hy, r, nc=6):
    rs = r if isinstance(r, (list, tuple)) else (r, r, r, r)
    pts = []
    for (sx, sy, a0), r in zip(((1, -1, -90), (1, 1, 0), (-1, 1, 90), (-1, -1, 180)), rs):
        r = min(r, hx, hy)
        ox, oy = cx + sx * (hx - r), cy + sy * (hy - r)
        for k in range(nc + 1):
            a = math.radians(a0 + 90 * k / nc)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    # drop duplicates where r == h
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def ellipse(cx, cy, a, b, n=40):
    return [(cx + a * math.cos(2 * math.pi * k / n), cy + b * math.sin(2 * math.pi * k / n)) for k in range(n)]


def lathe(profile, segs, mat, knurl=None, closed=False, caps=True):
    """Revolve (r, z) profile about +Z. `mat` may be callable(j) per band."""
    mb = MB()
    rings = []
    for j, (r, z) in enumerate(profile):
        if r < 1e-6:
            rings.append([mb.vert((0, 0, z))])
        else:
            ring = []
            for i in range(segs):
                a = 2 * math.pi * i / segs
                rr = knurl(r, z, i, j) if knurl else r
                ring.append(mb.vert((rr * math.cos(a), rr * math.sin(a), z)))
            rings.append(ring)
    pairs = list(range(len(rings) - 1))
    if closed:
        pairs.append(len(rings) - 1)
    for j in pairs:
        A, B = rings[j], rings[(j + 1) % len(rings)]
        mm = mat(j) if callable(mat) else mat
        if len(A) == 1 and len(B) == 1:
            continue
        if len(A) == 1:
            for i in range(segs):
                mb.face([A[0], B[(i + 1) % segs], B[i]], mm)
        elif len(B) == 1:
            for i in range(segs):
                mb.face([A[i], A[(i + 1) % segs], B[0]], mm)
        else:
            for i in range(segs):
                mb.face([A[i], A[(i + 1) % segs], B[(i + 1) % segs], B[i]], mm)
    if caps and not closed:
        m0 = mat(0) if callable(mat) else mat
        m1 = mat(len(rings) - 2) if callable(mat) else mat
        if len(rings[0]) > 1:
            mb.face(list(reversed(rings[0])), m0)
        if len(rings[-1]) > 1:
            mb.face(rings[-1], m1)
    return mb


def frame(o, zax, xh=(1, 0, 0)):
    z = Vector(zax).normalized()
    x = Vector(xh)
    x = x - z * x.dot(z)
    if x.length < 1e-6:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, o[0]), (x.y, y.y, z.y, o[1]), (x.z, y.z, z.z, o[2]), (0, 0, 0, 1)))


def sweep(path, radius, sides, mat, caps=True, dome=False, radii=None):
    P = [Vector(p) for p in path]
    n = len(P)
    T = []
    for i in range(n):
        if i == 0:
            t = P[1] - P[0]
        elif i == n - 1:
            t = P[-1] - P[-2]
        else:
            t = (P[i + 1] - P[i]).normalized() + (P[i] - P[i - 1]).normalized()
        T.append(t.normalized())
    R = list(radii) if radii else [radius] * n
    if dome:
        pre_p, pre_t, pre_r, post_p, post_t, post_r = [], [], [], [], [], []
        for th in (84, 65, 45, 25):
            a = math.radians(th)
            pre_p.append(P[0] - T[0] * R[0] * math.sin(a)); pre_t.append(T[0]); pre_r.append(R[0] * math.cos(a))
        for th in (25, 45, 65, 84):
            a = math.radians(th)
            post_p.append(P[-1] + T[-1] * R[-1] * math.sin(a)); post_t.append(T[-1]); post_r.append(R[-1] * math.cos(a))
        P = pre_p + P + post_p
        T = pre_t + T + post_t
        R = pre_r + R + post_r
    mb = MB()
    N = T[0].orthogonal().normalized()
    rings = []
    for i in range(len(P)):
        if i > 0:
            q = T[i - 1].rotation_difference(T[i])
            N = q @ N
            N = (N - T[i] * N.dot(T[i])).normalized()
        Bn = T[i].cross(N)
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            ring.append(mb.vert(P[i] + R[i] * (math.cos(a) * N + math.sin(a) * Bn)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(sides):
            mb.face([rings[i][k], rings[i][(k + 1) % sides], rings[i + 1][(k + 1) % sides], rings[i + 1][k]], mat)
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)
    return mb


def loft(rings, mat, caps=True):
    mb = MB()
    idx = [[mb.vert(p) for p in r] for r in rings]
    n = len(rings[0])
    for j in range(len(idx) - 1):
        mm = mat(j) if callable(mat) else mat
        for i in range(n):
            mb.face([idx[j][i], idx[j][(i + 1) % n], idx[j + 1][(i + 1) % n], idx[j + 1][i]], mm)
    if caps:
        m0 = mat(0) if callable(mat) else mat
        mb.face(list(reversed(idx[0])), m0)
        mb.face(idx[-1], mat(len(idx) - 2) if callable(mat) else mat)
    return mb


def smooth01(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def T4(x=0, y=0, z=0):
    return Matrix.Translation((x, y, z))


def RZ(deg):
    return Matrix.Rotation(math.radians(deg), 4, 'Z')


# ------------------------------------------------------------------------------ materials
MAT = {}


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def bsdf_of(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def setin(b, name, val):
    s = b.inputs.get(name)
    if s is not None:
        s.default_value = val


def material(name, color, rough=0.5, metal=0.0, coat=0.0, coat_rough=0.03, coat_tint=None, spec=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = bsdf_of(m)
    setin(b, 'Base Color', (*color, 1.0))
    setin(b, 'Roughness', rough)
    setin(b, 'Metallic', metal)
    if coat > 0:
        setin(b, 'Coat Weight', coat)
        setin(b, 'Coat Roughness', coat_rough)
        setin(b, 'Coat IOR', 1.5)
        if coat_tint:
            setin(b, 'Coat Tint', (*coat_tint, 1.0))
    if spec is not None:
        setin(b, 'Specular IOR Level', spec)
    m.diffuse_color = (*color, 1.0)
    m.roughness = rough
    m.metallic = metal
    MAT[name] = m
    return m


def add_noise_roughness(m, lo, hi, scale, target='Coat Roughness'):
    nt = m.node_tree
    b = bsdf_of(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 4.0
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = lo
    mr.inputs['To Max'].default_value = hi
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs[target])


def add_bump(m, scale, strength, distance=0.0005):
    nt = m.node_tree
    b = bsdf_of(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 6.0
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = distance
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])


def build_materials():
    paint = material('Tele_Paint_SurfGreen_Nitro', srgb('#8FD1B6'), rough=0.32, coat=1.0, coat_rough=0.03)
    add_noise_roughness(paint, 0.02, 0.07, 18.0)

    maple = material('Tele_Maple_Nitro', srgb('#E6C68F'), rough=0.38, coat=1.0, coat_rough=0.05,
                     coat_tint=(1.0, 0.93, 0.80))
    nt = maple.node_tree
    b = bsdf_of(maple)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    wave = nt.nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'Y'
    wave.inputs['Scale'].default_value = 70.0
    wave.inputs['Distortion'].default_value = 1.1
    wave.inputs['Detail'].default_value = 3.0
    wave.inputs['Detail Scale'].default_value = 1.5
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (*srgb('#E6BE80'), 1)
    ramp.color_ramp.elements[1].position = 0.95
    ramp.color_ramp.elements[1].color = (*srgb('#D6A564'), 1)
    nt.links.new(tc.outputs['Object'], wave.inputs['Vector'])
    nt.links.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])

    material('Tele_Pickguard_Parchment', srgb('#ECE3CC'), rough=0.3, spec=0.5)
    material('Tele_Pickguard_BlackPly', srgb('#111111'), rough=0.35)
    material('Tele_Chrome', (0.9, 0.9, 0.9), rough=0.11, metal=1.0)
    material('Tele_Bridge_Plate', (0.78, 0.78, 0.78), rough=0.24, metal=1.0)
    material('Tele_Nickel', (0.83, 0.81, 0.76), rough=0.2, metal=1.0)
    material('Tele_Brass_Saddle', (0.86, 0.62, 0.30), rough=0.24, metal=1.0)
    material('Tele_Steel_Dark', (0.25, 0.25, 0.26), rough=0.35, metal=1.0)
    material('Tele_Fret_NickelSilver', (0.86, 0.85, 0.81), rough=0.15, metal=1.0)
    material('Tele_String_Plain', (0.92, 0.92, 0.92), rough=0.18, metal=1.0)
    material('Tele_String_Wound', (0.80, 0.77, 0.70), rough=0.32, metal=1.0)
    material('Tele_Pickup_Flatwork', srgb('#141414'), rough=0.55)
    material('Tele_Pickup_Copper', (0.75, 0.33, 0.16), rough=0.3, metal=1.0)
    material('Tele_Pole_Alnico', (0.72, 0.72, 0.74), rough=0.28, metal=1.0)
    material('Tele_Nut_Bone', srgb('#EFE7D2'), rough=0.35)
    material('Tele_Inlay_Black', srgb('#0E0D0C'), rough=0.3)
    material('Tele_Plastic_Black', srgb('#0C0C0C'), rough=0.25)
    material('Tele_Hole_Dark', (0.004, 0.004, 0.004), rough=0.9)
    material('Tele_Felt_Black', (0.01, 0.01, 0.01), rough=0.95)
    material('Stand_PowderCoat_Black', srgb('#1B1B1D'), rough=0.42, metal=0.0)
    foam = material('Stand_Foam_Black', srgb('#161616'), rough=0.9)
    add_bump(foam, 900.0, 0.35, 0.0004)
    material('Stand_Rubber_Black', srgb('#101010'), rough=0.7)


# ------------------------------------------------------------------------------ body


def body_outline():
    """Tele slab outline. x from the butt, +y bass side. Authored against a 406 mm body whose
    bass shoulder meets the neck at x=398, then shifted -8 mm so that junction lands on the
    16th fret (x~389) of the 648 mm scale laid out from the nut at x=780."""
    ctrl = [
        # butt -> treble lower bout -> waist
        (0, 0), (2, -42), (9, -82), (24, -116), (47, -143), (80, -158), (120, -162.5),
        (160, -159), (198, -150), (232, -140.5), (262, -139),
        # treble upper-bout shoulder, then the single concave cutaway sweeping into the neck
        (280, -139.5), (292, -137), (300, -131), (306, -121), (311, -107), (317, -91),
        (325, -76), (336, -62), (349, -50.5), (364, -41.5), (378, -35.5), (390, -31.5), (397, -30),
        # neck pocket opening (under the neck heel)
        (399, 0),
        # bass horn / rounded bass upper bout
        (400, 30), (402, 45), (404, 64), (403, 82), (398, 99), (389, 114), (375, 127),
        (356, 136.5), (332, 141.5), (305, 142.5), (278, 140), (252, 137.5), (228, 138.5),
        # bass waist -> lower bout -> butt
        (200, 146), (165, 156), (125, 162.5), (85, 159), (50, 146), (25, 120), (9, 84), (2, 42),
    ]
    ctrl = [(x - BODY_SHIFT, y) for x, y in ctrl]
    pts = catmull(ctrl, closed=True, n=10)
    return ccw(resample(pts, 3.2))


def build_body(BO):
    mb = slab(BO, round_rings(0.0, BODY_T, EDGE_R, EDGE_R, 4, 4), 'Tele_Paint_SurfGreen_Nitro')
    return mb


def guard_outline(BO):
    """Tele guard: bass upper bout + around the neck pocket and neck pickup, a narrow strip along
    the cutaway, a straight lower edge just ahead of the bridge plate with the classic step down
    beside the plate's bass corner. Leaves the treble lower bout bare."""
    BI = inset(BO, 3.5)
    n = len(BI)
    # BO starts at the butt and runs CCW: treble side toward the neck, then bass side back
    treb = [i for i in range(n) if -86 < BI[i][1] < -26 and BI[i][0] > 300]
    bass = [i for i in range(n) if BI[i][1] > 26 and BI[i][0] >= 238]
    tpts = [BI[i] for i in treb]
    bpts = [BI[i] for i in bass]
    lower = [bpts[-1], (225, 119), (214, 101), (204, 83), (196, 68), (193, 58), (195, 51.5),
             (201, 48.5), (207.5, 45), (209, 36), (209, 0), (209, -34), (213, -45), (226, -51),
             (250, -55), (268, -58), (282, -63.5), (293, -71.5), (303, -78.5), tpts[0]]
    lower = catmull(lower, closed=False, n=6)[1:-1]
    P = tpts + bpts + lower
    P = resample(P, 2.0)
    for _ in range(6):   # round off corners (real guards have no sharp inside corners)
        m = len(P)
        P = [((P[i - 1][0] + 2 * P[i][0] + P[(i + 1) % m][0]) / 4,
              (P[i - 1][1] + 2 * P[i][1] + P[(i + 1) % m][1]) / 4) for i in range(m)]
    return ccw(resample(P, 2.5))


def build_guard(G):
    rings = [(0, 0), (0, 0.55), (0.25, 0.8), (0.75, 1.3), (1.7, 2.25), (1.8, 2.3)]
    rings = [(d, ZTOP + 0.02 + z) for d, z in rings]
    mats = ['Tele_Pickguard_Parchment', 'Tele_Pickguard_Parchment', 'Tele_Pickguard_BlackPly',
            'Tele_Pickguard_Parchment', 'Tele_Pickguard_Parchment']
    return slab(G, rings, lambda j: mats[j], mat_top='Tele_Pickguard_Parchment',
                mat_bot='Tele_Pickguard_Parchment')


def screw_head(r=2.9, h=1.4, slot=True, mat='Tele_Chrome'):
    prof = [(0, -0.3), (r, -0.3), (r, 0.0), (r * 0.97, h * 0.35), (r * 0.8, h * 0.7), (r * 0.45, h * 0.95), (0, h)]
    mb = lathe(prof, 20, mat)
    if slot:
        s = slab(rrect(0, 0, r * 0.55, 0.32, 0.1, 2), [(0, h * 0.62), (0, h + 0.06)], 'Tele_Hole_Dark')
        mb.add(s)
    return mb


# ------------------------------------------------------------------------------ neck


def neck_hw(x):
    if x <= NUT_X:
        return 21.0 + 7.0 * min(1.0, (NUT_X - x) / (NUT_X - FB_END))
    yl, yu = hs_plan(x)
    return (yu - yl) / 2


# Headstock plan (x from the nut, +y bass): flat paddle, straight bass edge carrying the six
# in-line tuners, treble edge scooped near the nut then running nearly parallel, rounded tip.
HS_CTRL = [(0, -21), (8, -21.8), (18, -24.5), (30, -29.5), (45, -35), (62, -39), (85, -41.8),
           (110, -43.5), (135, -44.8), (152, -45), (163, -43), (171, -38), (176, -30), (178, -20),
           (177.5, -8), (175.5, 3), (172, 12), (167, 19.5), (160, 24.5), (150, 26.8), (135, 27.2), (100, 27.2),
           (60, 26.2), (30, 24.5), (12, 22.5), (0, 21)]


def _hs_chains():
    pts = catmull(HS_CTRL, closed=False, n=10)
    im = max(range(len(pts)), key=lambda i: pts[i][0])
    lo = sorted(pts[:im + 1], key=lambda p: p[0])
    hi = sorted(pts[im:], key=lambda p: p[0])
    return lo, hi, pts[im][0]


HS_LO, HS_HI, HS_LEN = _hs_chains()
HS_XMAX = NUT_X + HS_LEN


def _interp(chain, xn):
    if xn <= chain[0][0]:
        return chain[0][1]
    for a, b in zip(chain, chain[1:]):
        if xn <= b[0]:
            t = 0 if b[0] - a[0] < 1e-9 else (xn - a[0]) / (b[0] - a[0])
            return a[1] + (b[1] - a[1]) * t
    return chain[-1][1]


def hs_plan(x):
    xn = x - NUT_X
    return _interp(HS_LO, xn), _interp(HS_HI, xn)


def neck_t(x):
    pts = [(300, 24.5), (395, 24.0), (456, 23.0), (NUT_X, 21.0)]
    if x <= pts[0][0]:
        return pts[0][1]
    for (xa, ta), (xb, tb) in zip(pts, pts[1:]):
        if x <= xb:
            return ta + (tb - ta) * (x - xa) / (xb - xa)
    return pts[-1][1]


def crown(x):
    return ZFB, FB_R


def ztop_at(y, Zc=ZFB, R=FB_R):
    return Zc - (R - math.sqrt(R * R - y * y))


def neck_ring(x):
    """One cross-section of the one-piece maple neck + headstock (same 44-point topology from
    the heel to the headstock tip, so the neck flows into the flat headstock with no seam)."""
    if x <= NUT_X:
        yc, hw = 0.0, neck_hw(x)
        Zc, curv = ZFB, 1.0 / FB_R
        zb = ZFB - neck_t(x)
        nexp, rho = 2.35, 1.2
        hb = 1.0 - smooth01((x - (BODY_NECK_X - 7.0)) / 8.0)   # square heel inside the pocket
    else:
        yl, yu = hs_plan(x)
        yc, hw = (yl + yu) / 2, max((yu - yl) / 2, 0.05)
        kt = smooth01((x - NUT_X - 1.0) / 6.0)
        Zc = ZFB + (HS_FACE - ZFB) * kt
        curv = (1.0 / FB_R) * (1 - kt) + (1.0 / 8000.0) * kt
        kb = smooth01((x - NUT_X) / 28.0)
        zb = (ZFB - neck_t(NUT_X)) * (1 - kb) + (HS_FACE - HS_T) * kb
        nexp = 2.35 * (1 - kb) + 12.0 * kb
        rho = 1.2 * (1 - kb) + 1.6 * kb
        hb = 0.0
    rho = min(rho, hw * 0.45)
    R = 1.0 / curv

    def zt(y):
        d = y - yc
        return Zc - (R - math.sqrt(R * R - d * d))
    yt = hw - rho
    ze = zt(yc + yt)
    pts = []
    for k in range(17):
        y = yc + yt - 2 * yt * k / 16
        pts.append((x, y, zt(y)))
    for th in (30, 60, 90):
        a = math.radians(th)
        pts.append((x, yc - (yt + rho * math.sin(a)), ze - rho + rho * math.cos(a)))
    z_side = ze - rho - 0.6
    D = z_side - zb
    if hb > 0:
        nexp = nexp * (1 - hb) + 14.0 * hb
        D = D * (1 - hb) + (z_side - 28.5) * hb
    for k in range(21):
        ph = math.pi * k / 20
        c, s_ = math.cos(ph), math.sin(ph)
        y = yc - hw * math.copysign(abs(c) ** (2 / nexp), c)
        z = z_side - D * abs(s_) ** (2 / nexp)
        pts.append((x, y, z))
    for th in (90, 60, 30):
        a = math.radians(th)
        pts.append((x, yc + yt + rho * math.sin(a), ze - rho + rho * math.cos(a)))
    return pts


def build_neck():
    xs = [318.0, 330, 350, 370, BODY_NECK_X - 10, BODY_NECK_X - 6, BODY_NECK_X - 4, BODY_NECK_X - 2,
          BODY_NECK_X, BODY_NECK_X + 2, BODY_NECK_X + 5, BODY_NECK_X + 12]
    x = 415.0
    while x < 770:
        xs.append(x)
        x += 15.0
    xs += [770, 776, 779, NUT_X, 781.0, 782.5, 784, 786.5, 790, 794, 799, 804, 810, 817, 825]
    x = 833.0
    while x < HS_XMAX - 12:
        xs.append(x)
        x += 9.0
    xs += [HS_XMAX - d for d in (9.0, 6.0, 4.0, 2.5, 1.4, 0.7, 0.3, 0.08)]
    xs = sorted(set(round(v, 3) for v in xs))
    mb = loft([neck_ring(x) for x in xs], 'Tele_Maple_Nitro')

    # nut (bone), bevelled by shrunken end rings
    def nut_ring(x, shrink):
        pts = []
        hw = 20.7 - shrink * 0.3
        for k in range(15):
            y = hw - 2 * hw * k / 14
            pts.append((x, y, NUT_TOP - 0.25 - (FB_R - math.sqrt(FB_R ** 2 - y * y)) - shrink))
        pts.append((x, -hw, ZFB - 2.0))
        pts.append((x, hw, ZFB - 2.0))
        return pts
    mb.add(loft([nut_ring(NUT_X, 0.4), nut_ring(NUT_X + 0.4, 0.0), nut_ring(NUT_X + 2.9, 0.0),
                 nut_ring(NUT_X + 3.3, 0.5)], 'Tele_Nut_Bone'))

    # dot inlays (face dots + side dots on the bass edge)
    def dot(xc, yc, r=3.0):
        zc = ztop_at(yc)
        nrm = Vector((0, yc, zc - (ZFB - FB_R))).normalized()
        d = lathe([(0, -0.6), (r, -0.6), (r, 0.03), (0, 0.03)], 24, 'Tele_Inlay_Black')
        return d, frame((xc, yc, zc), nrm)
    for n in (3, 5, 7, 9, 15, 17, 19, 21, 12):
        xm = 0.5 * (fret_x(n - 1) + fret_x(n))
        ys = (-9.0, 9.0) if n == 12 else (0.0,)
        for yc in ys:
            d, M = dot(xm, yc)
            mb.add(d, M)
        # side dots
        for k, yc in enumerate(ys):
            xs_ = xm + (k * 2 - 1) * 3.0 if n == 12 else xm
            hw = neck_hw(xs_)
            ze = ztop_at(hw - 1.2)
            sd = lathe([(0, -0.5), (1.1, -0.5), (1.1, 0.02), (0, 0.02)], 12, 'Tele_Inlay_Black')
            mb.add(sd, frame((xs_, hw, ze - 2.6), (0, 1, 0)))
    return mb


def build_frets():
    mb = MB()
    sec = []
    for k in range(7):
        th = math.pi * k / 6
        sec.append((1.15 * math.cos(th), FRET_H * math.sin(th)))
    sec += [(-1.15, -0.25), (1.15, -0.25)]
    for n in range(1, N_FRETS + 1):
        xf = fret_x(n)
        e = neck_hw(xf) - 0.5
        ys = [-e, -e + 0.7, -e + 1.6]
        m = 13
        for k in range(1, m):
            ys.append(-e + 1.6 + (2 * e - 3.2) * k / m)
        ys += [e - 1.6, e - 0.7, e]
        rows = []
        for j, y in enumerate(ys):
            hscale = 0.25 if j in (0, len(ys) - 1) else (0.7 if j in (1, len(ys) - 2) else 1.0)
            zt = ztop_at(min(abs(y), neck_hw(xf) - 0.01))
            rows.append([mb.vert((xf + sx * (0.85 + 0.15 * hscale), y, zt + sz * (hscale if sz > 0 else 1)))
                         for sx, sz in sec])
        ns = len(sec)
        for j in range(len(rows) - 1):
            for k in range(ns):
                mb.face([rows[j][k], rows[j][(k + 1) % ns], rows[j + 1][(k + 1) % ns], rows[j + 1][k]],
                        'Tele_Fret_NickelSilver')
        mb.face(list(reversed(rows[0])), 'Tele_Fret_NickelSilver')
        mb.face(rows[-1], 'Tele_Fret_NickelSilver')
    return mb


# ------------------------------------------------------------------------------ hardware


def saddle_z(y):
    return Z_SAD0 - (FB_R - math.sqrt(FB_R ** 2 - y * y))


def saddle_slope(y):
    return -y / math.sqrt(FB_R ** 2 - y * y)


def barrel_center(i):
    yc = SADDLE_Y[i]
    return Vector((SADDLE_X[i], yc, saddle_z(yc) - R_BARREL))


def string_saddle_point(s):
    i = s // 2
    c = barrel_center(i)
    y = Y_BRIDGE[s]
    z = c.z + R_BARREL + saddle_slope(SADDLE_Y[i]) * (y - SADDLE_Y[i])
    return Vector((c.x, y, z)), c.z + saddle_slope(SADDLE_Y[i]) * (y - SADDLE_Y[i])


def helix(p0, p1, r, turns, wire, mat, pts_per_turn=12):
    ax = (p1 - p0)
    L = ax.length
    M = frame(p0, ax)
    path = []
    n = int(turns * pts_per_turn)
    for k in range(n + 1):
        a = 2 * math.pi * k / pts_per_turn
        path.append(M @ Vector((r * math.cos(a), r * math.sin(a), L * k / n)))
    return sweep(path, wire, 6, mat, caps=True)


def build_bridge():
    mb = MB()
    # base plate
    mb.add(slab(rrect(152.5, 0, 52.5, 43, (10, 10, 1.2, 1.2), 6), round_rings(ZTOP, PLATE_TOP, 0.45, 0, 2, 0), 'Tele_Bridge_Plate'))
    # side walls, authored in (x, z) and extruded in y
    prof = [(100, 0), (172, 0), (168, 1.4), (162, 4.8), (156, 8.6), (151, 11.0), (147, 11.8), (142, 12.0), (100, 12.0)]
    for side in (1, -1):
        w = slab(prof, round_rings(0, 1.2, 0.45, 0.45, 2, 2), 'Tele_Bridge_Plate')
        y0 = 43.0 - 1.2 if side > 0 else -43.0
        M = Matrix(((1, 0, 0, 0), (0, 0, 1, y0), (0, 1, 0, ZTOP), (0, 0, 0, 1)))
        mb.add(w, M)
    rear = slab(rrect(0, 6.0, 43.0, 6.0, 0.8, 2), round_rings(0, 1.2, 0.45, 0.45, 2, 2), 'Tele_Bridge_Plate')
    mb.add(rear, Matrix(((0, 0, 1, 100.0), (1, 0, 0, 0), (0, 1, 0, ZTOP), (0, 0, 0, 1))))
    # plate screws
    for (x, y) in ((106.5, 36.5), (106.5, -36.5), (196.5, 33.5), (196.5, -33.5)):
        mb.add(screw_head(2.7, 1.3), T4(x, y, PLATE_TOP))
    # string through-holes
    for y in Y_BRIDGE:
        mb.add(lathe([(0, 0), (1.5, 0), (1.5, 0.04), (0, 0.04)], 12, 'Tele_Hole_Dark'), T4(HOLE_X, y, PLATE_TOP))
    # barrels, height screws, intonation screws + springs
    for i in range(3):
        c = barrel_center(i)
        yc = SADDLE_Y[i]
        beta = math.atan(saddle_slope(yc))
        axis = Vector((0, math.cos(beta), math.sin(beta)))
        hl = 9.9
        prof_b = [(0, -hl), (R_BARREL - 0.6, -hl), (R_BARREL, -hl + 0.6), (R_BARREL, hl - 0.6), (R_BARREL - 0.6, hl), (0, hl)]
        bar = lathe(prof_b, 28, 'Tele_Brass_Saddle')
        mb.add(bar, frame(c, axis, (1, 0, 0)))
        for dy in (-6.2, 6.2):
            p = c + axis * (dy / math.cos(beta))
            hs = lathe([(0, 0), (1.5, 0), (1.5, p.z - PLATE_TOP), (0, p.z - PLATE_TOP)], 12, 'Tele_Steel_Dark')
            mb.add(hs, T4(p.x, p.y, PLATE_TOP))
            # hex socket look on the barrel top
            top = c + axis * (dy / math.cos(beta)) + Vector((0, 0, R_BARREL - 0.35))
            sk = lathe([(0, 0), (1.2, 0), (1.2, 0.45), (0, 0.45)], 6, 'Tele_Hole_Dark')
            mb.add(sk, T4(top.x, top.y, top.z))
        # intonation screw along +x through rear wall into barrel
        p0 = Vector((97.6, c.y, c.z))
        scr = lathe([(0, 0), (1.3, 0), (1.3, c.x + 4.4 - 97.6), (0, c.x + 4.4 - 97.6)], 12, 'Tele_Nickel')
        mb.add(scr, frame(p0, (1, 0, 0), (0, 0, 1)))
        head = lathe([(0, 0), (2.6, 0), (2.6, 0.9), (2.2, 1.6), (1.2, 2.0), (0, 2.1)], 20, 'Tele_Chrome')
        mb.add(head, frame(Vector((100.0, c.y, c.z)), (-1, 0, 0), (0, 0, 1)))
        slot = slab(rrect(0, 0, 1.4, 0.3, 0.1, 2), [(0, 1.3), (0, 2.12)], 'Tele_Hole_Dark')
        mb.add(slot, frame(Vector((100.0, c.y, c.z)), (-1, 0, 0), (0, 0, 1)))
        mb.add(helix(Vector((101.3, c.y, c.z)), Vector((c.x - R_BARREL - 0.4, c.y, c.z)), 1.95, 7.5, 0.32,
                     'Tele_Nickel'))
    # bridge pickup (slanted: treble end toward the saddles)
    Mpu = T4(172.0, 0, PLATE_TOP) @ RZ(-8.0)
    O = rrect(0, 0, 9.4, 35.5, 5.0, 5)
    mb.add(slab(O, round_rings(0, 1.3, 0.3, 0, 1, 0), 'Tele_Pickup_Flatwork'), Mpu)
    mb.add(slab(inset(ccw(O), 1.1), [(0, 1.3), (0, 7.8)], 'Tele_Pickup_Copper'), Mpu)
    mb.add(slab(O, round_rings(7.8, 9.4, 0.45, 0, 2, 0), 'Tele_Pickup_Flatwork'), Mpu)
    for s in range(6):
        yb = Y_BRIDGE[s] + (Y_NUT[s] - Y_BRIDGE[s]) * (172 - 130) / (NUT_X - 130)
        sp = yb / math.cos(math.radians(8))
        pole = lathe([(0, 1.0), (2.4, 1.0), (2.4, 9.5), (2.15, 9.72), (0, 9.78)], 16, 'Tele_Pole_Alnico')
        mb.add(pole, Mpu @ T4(0, sp, 0))
    for sy in (40.3, -40.3):
        mb.add(screw_head(2.3, 1.2), Mpu @ T4(0, sy, 1.2))
        mb.add(lathe([(0, 0), (2.3, 0), (2.3, 1.2), (0, 1.2)], 12, 'Tele_Chrome'), Mpu @ T4(0, sy, 0))
    return mb


def build_neck_pickup():
    mb = MB()
    zb = ZTOP + 2.3
    O = rrect(NECK_PU_X, 0, 9.8, 35.0, 7.0, 6)
    mb.add(slab(O, round_rings(zb - 0.5, zb + 8.1, 3.0, 0, 5, 0), 'Tele_Chrome'))
    for y in (40.6, -40.6):
        mb.add(screw_head(2.5, 1.3), T4(NECK_PU_X, y, zb))
    return mb


def build_controls():
    mb = MB()
    th = 10.0
    C = Vector((160.0, -120.0))
    d = Vector((math.cos(math.radians(th)), math.sin(math.radians(th))))
    Mp = T4(C.x, C.y, 0) @ RZ(th)
    top = ZTOP + 1.6
    mb.add(slab(rrect(0, 0, 76, 12.5, 12.5, 10), round_rings(ZTOP, top, 0.7, 0, 3, 0), 'Tele_Chrome'), Mp)
    for s in (-68.0, 68.0):
        mb.add(screw_head(2.5, 1.2), Mp @ T4(s, 0, top))

    def knurl(r, z, i, j):
        if 1.25 < z < 9.8:
            return r - 0.32 * ((i + j) % 2)
        return r
    prof = [(0, 0.3), (8.8, 0.3), (9.4, 0.7), (9.5, 1.25)]
    z = 1.25
    while z < 9.7:
        z += 0.7
        prof.append((9.5, min(z, 9.8)))
    prof += [(9.4, 10.3), (9.15, 10.9), (8.7, 11.35), (8.0, 11.6), (4.0, 11.85), (0, 11.9)]
    for s in (-54.0, -16.0):
        mb.add(lathe(prof, 96, 'Tele_Chrome', knurl=knurl), Mp @ T4(s, 0, top))
    # 3-way switch: slot, lever, barrel tip
    mb.add(slab(rrect(0, 0, 10.5, 1.7, 1.2, 3), [(0, top), (0, top + 0.05)], 'Tele_Hole_Dark'), Mp @ T4(42.0, 0, 0))
    lev_dir = Vector((math.sin(math.radians(16)), 0, math.cos(math.radians(16))))
    L = 9.0
    lever = slab(rrect(0, 0, 0.7, 2.2, 0.5, 2), [(0, -1.0), (0, L)], 'Tele_Chrome')
    Ml = Mp @ T4(42.0 + 5.0, 0, top) @ frame((0, 0, 0), lev_dir, (0, 1, 0))
    mb.add(lever, Ml)
    tip = [(0, 0), (4.3, 0), (4.8, 0.6), (4.8, 8.6), (4.5, 10.3), (3.4, 11.4), (1.8, 11.9), (0, 12.0)]
    mb.add(lathe(tip, 28, 'Tele_Plastic_Black'), Ml @ T4(0, 0, L - 3.0))
    return mb


def build_neck_plate_and_back():
    mb = MB()
    mb.add(slab(rrect(BODY_NECK_X - 38.0, 0, 32.0, 25.5, 5.0, 5), round_rings(-1.3, 0.02, 0, 0.55, 0, 2), 'Tele_Chrome'))
    for sx in (-23.5, 23.5):
        for sy in (-17.5, 17.5):
            mb.add(screw_head(3.0, 1.4), frame((BODY_NECK_X - 38.0 + sx, sy, -1.3), (0, 0, -1)))
    for y in Y_BRIDGE:
        mb.add(lathe([(0, 0.05), (3.6, 0.05), (3.6, -0.15), (3.3, -0.4), (0, -0.4)], 20, 'Tele_Chrome'), T4(HOLE_X, y, 0))
        mb.add(lathe([(0, 0), (2.0, 0), (2.0, -0.45), (0, -0.45)], 12, 'Tele_Hole_Dark'), T4(HOLE_X, y, 0))
    return mb


def outline_normal(BO, i):
    N = normals2(BO)
    n = Vector((N[i][0], N[i][1], 0)).normalized()
    return n


def build_side_hardware(BO):
    mb = MB()
    # jack cup on the treble side at the lower bout's widest point
    ij = min(range(len(BO)), key=lambda i: BO[i][1])
    pj = Vector((BO[ij][0], BO[ij][1], BODY_T / 2))
    nj = outline_normal(BO, ij)
    Mj = frame(pj, nj, (1, 0, 0))
    cup = [(0, -1.0), (0.38, -0.925), (0.7, -0.715), (0.92, -0.39), (0.985, -0.12), (1.0, 0.0), (1.05, 0.05),
           (1.08, 0.12), (1.06, 0.18), (1.0, 0.2)]
    shell = lathe(cup, 40, 'Tele_Chrome', caps=False)
    mb.add(shell, Mj @ Matrix.Diagonal((17.5, 11.2, 6.0, 1.0)))
    nut = lathe([(0, -6.0), (6.0, -6.0), (6.0, -3.6), (5.4, -3.2), (0, -3.2)], 6, 'Tele_Nickel')
    mb.add(nut, Mj)
    sleeve = lathe([(0, -3.2), (4.3, -3.2), (4.3, -1.7), (3.3, -1.5), (3.3, -1.9), (0, -1.9)], 24, 'Tele_Nickel')
    mb.add(sleeve, Mj)
    mb.add(lathe([(0, -1.88), (3.3, -1.88), (3.3, -1.86), (0, -1.86)], 16, 'Tele_Hole_Dark'), Mj)
    jack = {'center': pj, 'normal': nj, 'scale': (18.2, 11.8, 6.3)}

    def strap(p, n):
        felt = lathe([(0, -0.5), (7.2, -0.5), (7.2, 0.8), (0, 0.8)], 24, 'Tele_Felt_Black')
        btn = lathe([(0, 0.8), (3.3, 0.8), (3.3, 5.5), (5.8, 6.2), (6.4, 7.2), (6.0, 8.2), (4.5, 8.9), (2.0, 9.3), (0, 9.4)],
                    28, 'Tele_Chrome')
        M = frame(p, n, (0, 0, 1))
        mb.add(felt, M)
        mb.add(btn, M)
        mb.add(screw_head(1.9, 0.6, slot=True), M @ T4(0, 0, 9.25))
    ib = min(range(len(BO)), key=lambda i: BO[i][0])
    strap(Vector((BO[ib][0], BO[ib][1], BODY_T / 2)), outline_normal(BO, ib))
    ih = max((i for i in range(len(BO)) if 55 < BO[i][1] < 100), key=lambda i: BO[i][0])
    strap(Vector((BO[ih][0], BO[ih][1], BODY_T / 2)), outline_normal(BO, ih))
    return mb, jack


def build_guard_screws(Gd):
    """Eight screws spaced evenly (by arc length) around the visible part of the guard."""
    mb = MB()
    Gi = inset(Gd, 4.6)
    vis = [p for p in Gi if not (p[0] > 312 and abs(p[1]) < 36)]
    L = [0.0]
    for a_, b_ in zip(vis, vis[1:]):
        L.append(L[-1] + math.hypot(b_[0] - a_[0], b_[1] - a_[1]) if math.hypot(b_[0] - a_[0], b_[1] - a_[1]) < 20 else L[-1] + 30)
    # rotate the run so it starts right after the neck gap
    k = 8
    total = L[-1]
    for j in range(k):
        target = total * (j + 0.5) / k
        i = min(range(len(L)), key=lambda q: abs(L[q] - target))
        p = vis[i]
        mb.add(screw_head(2.8, 1.35), T4(p[0], p[1], ZTOP + 2.3))
    return mb

def build_tuners():
    mb = MB()
    for s in range(6):
        xp = NUT_X + POST_XN[s]
        # front: bushing + post + slot + string wrap
        mb.add(lathe([(POST_R, HS_FACE - 0.2), (4.3, HS_FACE - 0.2), (4.3, HS_FACE + 0.6), (3.9, HS_FACE + 1.2),
                      (POST_R, HS_FACE + 1.2)], 28, 'Tele_Nickel', closed=True), T4(xp, POST_Y, 0))
        ptop = HS_FACE + 10.5
        mb.add(lathe([(0, HS_FACE), (POST_R, HS_FACE), (POST_R, ptop - 0.45), (POST_R - 0.35, ptop), (0, ptop)], 24,
                     'Tele_Nickel'), T4(xp, POST_Y, 0))
        mb.add(slab(rrect(0, 0, 0.45, POST_R + 0.05, 0.1, 2), [(0, ptop - 4.2), (0, ptop + 0.03)], 'Tele_Hole_Dark'),
               T4(xp, POST_Y, 0))
        zw = post_wrap_z(s)
        rs = R_STR[s]
        wraps = 3 if s < 3 else 4
        mb.add(lathe([(POST_R - 0.05, zw - rs * wraps), (POST_R + 2 * rs, zw - rs * wraps + rs * 0.6),
                      (POST_R + 2 * rs, zw + rs * wraps - rs * 0.6), (POST_R - 0.05, zw + rs * wraps)], 24,
                     'Tele_String_Wound' if WOUND[s] else 'Tele_String_Plain', caps=False), T4(xp, POST_Y, 0))
        # back: Kluson-style housing, shaft, button
        zb = HS_FACE - HS_T
        mb.add(slab(rrect(xp, POST_Y + 1.5, 7.0, 7.5, 2.0, 4), round_rings(zb - 8.5, zb + 0.2, 0, 1.6, 0, 3), 'Tele_Nickel'))
        zs = zb - 4.5
        mb.add(lathe([(0, 0), (1.8, 0), (1.8, 9.0), (0, 9.0)], 16, 'Tele_Nickel'),
               frame((xp, POST_Y + 8.5, zs), (0, 1, 0)))
        mb.add(lathe([(0, 0), (3.2, 0), (3.2, 2.0), (2.2, 3.0), (0, 3.0)], 20, 'Tele_Nickel'),
               frame((xp, POST_Y + 8.9 + 7.5, zs), (0, 1, 0)))
        btn = slab(ellipse(0, 0, 8.3, 7.3, 36), round_rings(-2.3, 2.3, 1.7, 1.7, 3, 3), 'Tele_Nickel')
        Mb = Matrix(((0, 0, 1, xp), (1, 0, 0, POST_Y + 8.9 + 7.5 + 2.2 + 8.0), (0, 1, 0, zs), (0, 0, 0, 1)))
        mb.add(btn, Mb)
        # tiny screw between tuners (vintage Kluson mounting screw)
        if s < 5:
            mb.add(screw_head(1.4, 0.7, slot=False, mat='Tele_Nickel'),
                   frame((xp + 11.5, POST_Y + 1.5, zb), (0, 0, -1)))
    # string tree
    mb.add(lathe([(0, HS_FACE), (2.2, HS_FACE), (2.2, 55.65), (0, 55.65)], 16, 'Tele_Nickel'), T4(TREE_X, 3.0, 0))
    mb.add(slab(rrect(TREE_X, 3.0, 2.8, 7.0, 2.2, 4), round_rings(55.65, 56.45, 0.3, 0.2, 1, 1), 'Tele_Nickel'))
    mb.add(screw_head(1.9, 0.9, mat='Tele_Nickel'), T4(TREE_X, 3.0, 56.45))
    return mb


def post_wrap_z(s):
    return HS_FACE + [4.2, 4.6, 5.0, 5.4, 3.2, 3.0][s]


def build_strings():
    mb = MB()
    for s in range(6):
        rs = R_STR[s]
        mat = 'Tele_String_Wound' if WOUND[s] else 'Tele_String_Plain'
        i = s // 2
        c = barrel_center(i)
        contact, zc_line = string_saddle_point(s)
        yb = Y_BRIDGE[s]
        R = R_BARREL + rs
        path = [Vector((HOLE_X, yb, PLATE_TOP - 0.5)), Vector((HOLE_X + 0.2, yb, PLATE_TOP + 0.8))]
        for ang in (160, 135, 112, 90):
            a = math.radians(ang)
            path.append(Vector((c.x + R * math.cos(a), yb, zc_line + R * math.sin(a))))
        zn = NUT_TOP - (FB_R - math.sqrt(FB_R ** 2 - Y_NUT[s] ** 2)) + rs - 0.35
        path.append(Vector((NUT_X, Y_NUT[s], zn)))
        path.append(Vector((NUT_X + 2.0, Y_NUT[s] + (0.0), zn + 0.02)))
        xp = NUT_X + POST_XN[s]
        pend = Vector((xp, POST_Y - POST_R - rs, post_wrap_z(s)))
        pnut = path[-1]
        if s >= 4:  # B and high E go under the tree
            t = (TREE_X - pnut.x) / (pend.x - pnut.x)
            ty = pnut.y + (pend.y - pnut.y) * t
            path.append(Vector((TREE_X, ty, 55.62 - rs)))
        path.append(pend)
        mb.add(sweep(path, rs, 8 if WOUND[s] else 6, mat, caps=True))
    return mb


# ------------------------------------------------------------------------------ stand (world mm)


def guitar_matrix(T):
    B = Matrix(((0, -1, 0, 0), (0, 0, -1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))
    return Matrix.Translation(T) @ Matrix.Rotation(-ALPHA, 4, 'X') @ B


def build_stand(G, T):
    mb = MB()
    D = 32.0                                   # mast axis behind the body back (local -z)
    ca, sa = math.cos(ALPHA), math.sin(ALPHA)

    def mast(xl):
        return G @ Vector((xl, 0, -D))

    def xl_at_z(zw):
        return (zw - T.z + D * sa) / ca

    mast_dir = (G.to_3x3() @ Vector((1, 0, 0))).normalized()
    x_lo = xl_at_z(96.0)
    x_mid = 330.0
    x_top = 648.0
    MT = 'Stand_PowderCoat_Black'
    # masts
    mb.add(sweep([mast(x_lo), mast(x_mid + 6)], 12.5, 24, MT))
    mb.add(sweep([mast(x_mid), mast(x_top)], 10.0, 24, MT))
    # hub
    hub = lathe([(0, -6), (15, -6), (18.5, -3), (19.5, 4), (19.5, 34), (17, 40), (14, 44), (0, 44)], 32, 'Stand_Rubber_Black')
    mb.add(hub, frame(mast(x_lo), mast_dir, (1, 0, 0)))
    H = mast(x_lo + 12)
    # legs
    feet = []
    for ang in (90.0, 215.0, 325.0):
        d = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0))
        p0 = Vector((H.x, H.y, H.z)) + d * 12.0
        F = Vector((H.x, H.y, 0)) + d * 300.0
        F.z = 13.0
        feet.append(F)
        mid = p0.lerp(F, 0.5) + Vector((0, 0, 8))
        mb.add(sweep(catmull([p0, mid, F], closed=False, n=6), 8.0, 20, MT))
        # hinge bracket
        br = slab(rrect(0, 0, 9, 11, 3, 3), round_rings(-7, 7, 1.5, 1.5, 2, 2), 'Stand_Rubber_Black')
        mb.add(br, frame(p0 + d * 6, (-d.y, d.x, 0), (d.x, d.y, 0)))
        foot = lathe([(0, 0), (19, 0), (21, 1.5), (21, 5.5), (18, 9.5), (12.5, 13), (10, 18), (0, 18.5)], 28,
                     'Stand_Rubber_Black')
        mb.add(foot, T4(F.x, F.y, 0))
    # cradle arms
    za = 172.0
    A0 = mast(xl_at_z(za))
    mb.add(lathe([(0, -11), (15, -11), (16, -9), (16, 9), (15, 11), (0, 11)], 28, 'Stand_Rubber_Black'),
           frame(A0, mast_dir, (1, 0, 0)))
    for sx in (1, -1):
        pts = [(A0.x, A0.y, za), (sx * 28, A0.y + 1, za), (sx * 66, A0.y + 1, za), (sx * 92, A0.y - 6, za),
               (sx * 100, A0.y - 22, za), (sx * 100, 4, za), (sx * 100, -44, za), (sx * 100, -54, za + 4),
               (sx * 100, -59, za + 14), (sx * 100, -60, za + 26)]
        path = catmull(pts, closed=False, n=8)
        mb.add(sweep(path, 6.0, 20, MT))
        foam = [p for p in path if p[1] < A0.y - 26 or p[2] > za + 0.1]
        foam = [p for p in foam if p[1] < A0.y - 26]
        mb.add(sweep(foam, 10.0, 24, 'Stand_Foam_Black', dome=True))
    # clamp collar + T-knob at the telescoping joint
    mb.add(lathe([(0, -14), (14.5, -14), (15.5, -12), (15.5, 12), (14.5, 14), (0, 14)], 28, MT),
           frame(mast(x_mid), mast_dir, (1, 0, 0)))
    kp = mast(x_mid) + Vector((15.0, 0, 0))
    mb.add(lathe([(0, 0), (4.0, 0), (4.0, 18.0), (0, 18.0)], 16, 'Tele_Chrome'), frame(kp, (1, 0, 0), (0, 0, 1)))

    def knurl(r, z, i, j):
        return r - (1.2 if (i % 4 < 2 and 0.5 < z < 8.5) else 0)
    kn = lathe([(0, 0), (10.5, 0), (12.0, 1.0), (12.0, 8.0), (10.5, 9.0), (0, 9.0)], 32, 'Stand_Rubber_Black', knurl=knurl)
    mb.add(kn, frame(kp + Vector((16.0, 0, 0)), (1, 0, 0), (0, 0, 1)))
    # neck yoke
    xy = x_top
    hw = neck_hw(xy)
    zback = ZFB - neck_t(xy)
    rf = 8.0
    Ru = hw + rf + 1.0
    zc = zback - 0.5 - rf + Ru
    Mloc = G
    pivot_dir = (G.to_3x3() @ Vector((0, 1, 0))).normalized()
    mb.add(lathe([(0, -15), (9.5, -15), (10.5, -13), (10.5, 13), (9.5, 15), (0, 15)], 24, 'Stand_Rubber_Black'),
           frame(mast(xy), pivot_dir, mast_dir))
    stem = [Mloc @ Vector((xy, 0, -D)), Mloc @ Vector((xy, 0, zc - Ru))]
    mb.add(sweep(stem, 6.0, 20, MT))
    U = [(-hw - rf - 4.5, zc + 32), (-Ru - 0.5, zc + 24), (-Ru, zc + 10)]
    for k in range(1, 12):
        a = math.pi + math.pi * k / 12
        U.append((Ru * math.cos(a), zc + Ru * math.sin(a)))
    U += [(Ru, zc + 10), (Ru + 0.5, zc + 24), (hw + rf + 4.5, zc + 32)]
    Up = [Mloc @ Vector((xy, u[0], u[1])) for u in catmull(U, closed=False, n=5)]
    mb.add(sweep(Up, 4.5, 16, MT))
    mb.add(sweep(Up, rf, 24, 'Stand_Foam_Black', dome=True))
    return mb, feet


# ------------------------------------------------------------------------------ scene assembly


def to_object(mb, name, coll, parent, angle=35.0, all_smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(p.x * S, p.y * S, p.z * S) for p in mb.v], [], mb.f)
    names = []
    for m in mb.m:
        if m not in names:
            names.append(m)
    for n in names:
        me.materials.append(MAT[n])
    me.polygons.foreach_set('material_index', [names.index(m) for m in mb.m])
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    obj.parent = parent
    try:
        me.shade_smooth()
        if not all_smooth:
            me.set_sharp_from_angle(angle=math.radians(angle))
    except AttributeError:
        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    return obj


def boolean_cut(obj, cutter):
    mod = obj.modifiers.new('jack_cut', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    new = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new
    bpy.data.meshes.remove(old)
    new.name = obj.name


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    build_materials()

    coll = bpy.data.collections.new('NEW_' + NAME)
    scene.collection.children.link(coll)
    root = bpy.data.objects.new('NEW_' + NAME + '_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.2
    coll.objects.link(root)

    BO = body_outline()
    GD = guard_outline(BO)

    # place the guitar: back-bottom rim edge rests on the cradle foam
    x_e = min(p[0] for p in BO if 95 < abs(p[1]) < 105)
    T = Vector((0.0, 0.0, 180.5 - x_e * math.cos(ALPHA)))
    G = guitar_matrix(T)
    stand, feet = build_stand(G, T)
    cen = sum((f for f in feet), Vector()) / len(feet)
    shift = Vector((-cen.x, -cen.y, 0))
    T = T + shift
    G = guitar_matrix(T)

    gtr = bpy.data.objects.new('NEW_' + NAME + '_guitar', None)
    gtr.empty_display_type = 'ARROWS'
    gtr.empty_display_size = 0.1
    coll.objects.link(gtr)
    gtr.parent = root
    R = Matrix.Rotation(-ALPHA, 4, 'X') @ Matrix(((0, -1, 0, 0), (0, 0, -1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))
    gtr.matrix_basis = Matrix.Translation(T * S) @ R

    objs = []
    body = to_object(build_body(BO), 'Tele_Body', coll, gtr)
    side_mb, jack = build_side_hardware(BO)
    # jack recess: boolean an ellipsoid out of the body side
    me = bpy.data.meshes.new('jack_cutter')
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    cutter = bpy.data.objects.new('jack_cutter', me)
    coll.objects.link(cutter)
    cutter.parent = gtr
    Mj = frame(jack['center'], jack['normal'], (1, 0, 0))
    sc = jack['scale']
    cutter.matrix_basis = Matrix.Diagonal((S, S, S, 1)) @ Mj @ Matrix.Diagonal((sc[0], sc[1], sc[2], 1))
    bpy.context.view_layer.update()
    boolean_cut(body, cutter)
    bpy.data.objects.remove(cutter, do_unlink=True)
    bm_ = body.data
    bm_.polygons.foreach_set('material_index', [0] * len(bm_.polygons))
    while len(bm_.materials) > 1:
        bm_.materials.pop(index=len(bm_.materials) - 1)
    bpy.data.meshes.remove(me)
    body.data.shade_smooth()
    body.data.set_sharp_from_angle(angle=math.radians(35))
    objs.append(body)

    objs.append(to_object(build_guard(GD), 'Tele_Pickguard', coll, gtr, angle=20))
    objs.append(to_object(build_neck(), 'Tele_Neck', coll, gtr, angle=40))
    objs.append(to_object(build_frets(), 'Tele_Frets', coll, gtr, angle=60))
    hw = MB()
    hw.add(build_bridge())
    hw.add(build_neck_pickup())
    hw.add(build_controls())
    hw.add(side_mb)
    hw.add(build_guard_screws(GD))
    hw.add(build_neck_plate_and_back())
    objs.append(to_object(hw, 'Tele_Hardware', coll, gtr, angle=40))
    objs.append(to_object(build_tuners(), 'Tele_Tuners', coll, gtr, angle=40))
    objs.append(to_object(build_strings(), 'Tele_Strings', coll, gtr, all_smooth=True))
    st = MB().add(stand, Matrix.Translation(shift))
    objs.append(to_object(st, 'TeleStand', coll, root, angle=40))

    total = 0
    for o in objs:
        t = tri_count(o)
        total += t
        print(f'  {o.name:18s} {t:7d} tris')
    print(f'TOTAL {total} tris')

    bpy.context.view_layer.update()
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    print(f'BOUNDS min {tuple(round(v, 4) for v in lo)} max {tuple(round(v, 4) for v in hi)}')
    return root, gtr, objs, G


# ------------------------------------------------------------------------------ preview


def setup_render(samples):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    try:
        prefs.compute_device_type = 'OPTIX'
        prefs.refresh_devices()
        for d in prefs.devices:
            d.use = (d.type == 'OPTIX')
        scene.cycles.device = 'GPU'
    except Exception as err:
        print('GPU setup failed:', err)
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPTIX'
    except TypeError:
        pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    world = bpy.data.worlds.new('preview_world')
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.25, 0.25, 0.25, 1)
    bg.inputs['Strength'].default_value = 0.7
    scene.world = world

    pc = bpy.data.collections.new('preview_only')
    scene.collection.children.link(pc)

    def light(name, loc, target, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        d = Vector(target) - Vector(loc)
        lo.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        pc.objects.link(lo)
    light('key', (-1.7, -1.9, 2.3), (0, 0, 0.6), 170, 1.6)
    light('fill', (2.2, -1.6, 1.1), (0, 0, 0.6), 55, 2.2)
    light('rim', (0.9, 2.2, 2.1), (0, 0, 0.6), 140, 1.2)

    fm = bpy.data.meshes.new('floor')
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=6.0)
    bm.to_mesh(fm)
    bm.free()
    fl = bpy.data.objects.new('floor', fm)
    fmat = bpy.data.materials.new('preview_floor')
    fmat.use_nodes = True
    b = bsdf_of(fmat)
    b.inputs['Base Color'].default_value = (0.32, 0.32, 0.32, 1)
    b.inputs['Roughness'].default_value = 0.8
    fm.materials.append(fmat)
    pc.objects.link(fl)
    cam_d = bpy.data.cameras.new('cam')
    cam = bpy.data.objects.new('cam', cam_d)
    pc.objects.link(cam)
    scene.camera = cam
    return cam


def shoot(cam, loc, target, lens, path):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    bpy.context.scene.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f'RENDER {os.path.basename(path)} {time.time() - t:.1f}s')


def main():
    root, gtr, objs, G = build()
    os.makedirs(OUT_DIR, exist_ok=True)
    blend = os.path.join(OUT_DIR, NAME + '.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print('SAVED', blend)
    if OPTS['norender']:
        return
    cam = setup_render(OPTS['samples'])
    Gm = gtr.matrix_world

    def wl(p):  # guitar-local mm -> world m
        return Gm @ (Vector(p) * S)
    front = (Gm.to_3x3() @ Vector((0, 0, 1))).normalized()
    up = (Gm.to_3x3() @ Vector((1, 0, 0))).normalized()
    side = (Gm.to_3x3() @ Vector((0, -1, 0))).normalized()   # treble side -> world +X
    views = OPTS['views'].split(',')
    for v in views:
        path = os.path.join(OUT_DIR, f'{NAME}_{v}.png')
        if v == 'front':
            shoot(cam, (1.35, -2.55, 1.05), (0.0, 0.03, 0.57), 50, path)
        elif v == 'bridge':
            tgt = wl((160, -8, 50))
            loc = tgt + front * 0.30 + side * 0.13 + up * 0.10
            shoot(cam, loc, tgt, 50, path)
        elif v == 'head':
            tgt = wl((880, 0, 50))
            loc = tgt + front * 0.30 - side * 0.12 + up * 0.02
            shoot(cam, loc, tgt, 50, path)
        elif v == 'back':
            shoot(cam, (-1.2, 2.3, 1.0), (0.0, 0.0, 0.55), 50, path)
        elif v == 'side':
            shoot(cam, (2.6, -0.05, 0.6), (0.0, 0.0, 0.55), 50, path)
        elif v == 'body':
            tgt = wl((250, 0, 45))
            loc = tgt + front * 0.75 + side * 0.05
            shoot(cam, loc, tgt, 50, path)
        elif v == 'horn':
            tgt = wl((370, 20, 48))
            loc = tgt + front * 0.35 + side * 0.05 - up * 0.1
            shoot(cam, loc, tgt, 50, path)
        elif v == 'cradle':
            shoot(cam, (0.55, -0.75, 0.45), (0.0, 0.0, 0.16), 50, path)
        elif v == 'yoke':
            tgt = wl((648, 0, 30))
            shoot(cam, tuple(tgt + Vector((0.3, -0.35, 0.12))), tgt, 50, path)
        elif v == 'heel':
            tgt = wl((400, -10, 35))
            loc = tgt + side * 0.28 + front * 0.12 - up * 0.08
            shoot(cam, loc, tgt, 50, path)
        elif v == 'hsback':
            tgt = wl((820, 0, 35))
            loc = tgt - front * 0.3 + side * 0.12
            shoot(cam, loc, tgt, 50, path)
        elif v == 'wedge':
            tgt = wl((306, -100, 45))
            loc = tgt + front * 0.12 + side * 0.03 + up * 0.02
            shoot(cam, loc, tgt, 50, path)
        elif v == 'jack':
            tgt = wl((125, -160, 22))
            loc = tgt + side * 0.25 + front * 0.12 + up * 0.05
            shoot(cam, loc, tgt, 50, path)


main()
