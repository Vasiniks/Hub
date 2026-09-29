"""
v2_medals.py -- four FIRST-style medals (1 gold on royal blue, 3 silver on red) hung on the desk lamp's neck.
STATIC (no animation). Built procedurally so the ribbons read as real woven lanyards: smooth gravity
sweeps, one gentle half twist, no crumples, no interpenetration.

    blender -b --factory-startup --python blender/scripts/v2_medals.py -- [--no-render]

Inputs: parts/lamp.blend + parts/lamp_meta.json (v2_lamp_stl.py) -- the lamp from the owner's STL, arm tilted
5 deg; the neck is the bulb between the ball knuckle and the head bracket (22.5 mm long, ~42 x 32 mm section).
Design, from the reference photos (parts/medal_ref_gold.jpg, parts/medal_ref_silver.jpg):
  * medal Ø70 mm cast disc, antique finish (matte darker field, polished raised rim and relief); obverse:
    raised square frame with a block relief and corner icons, a raised word-mark band and a sub-line band;
    reverse: interlocking-loop logo and four raised text bands; a pierced tab on top;
  * split ring through the tab, a D-ring the lanyard is sewn around; plain solid-colour woven ribbon 25 mm.
Lanyards: all four loops stacked on the neck (gathered to 20 mm to fit it); just below, each side's layered
tails twist 90 deg together (a rigid rotation, so layers never cross) and every lanyard then hangs as a flat V
in its own depth layer, 14 mm apart -- gold/blue on top of the loop stack and in front. Each tail is a flat
ribbon swept along a smooth curve (gentle bow, different lengths, lateral offsets); the gold's left tail
carries a half twist. Medals face the seated viewer.
Output: parts/medals.blend (NEW_medals / NEW_medals_root, ROOM coords; root carries parent_to =
'NEW_lamp_pivot' -- parent it keeping transform) + a static parts/medals.glb.
"""
import bpy
import bmesh
import math
import os
import sys
import json
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree
from mathutils.geometry import convex_hull_2d

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
LAMP_BLEND = os.path.join(PARTS, 'lamp.blend')
NAME = 'medals'
OUT_BLEND = os.path.join(PARTS, NAME + '.blend')
OUT_GLB = os.path.join(PARTS, NAME + '.glb')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
SEAT = Vector((0.0, -0.16, 1.175))
Z = Vector((0, 0, 1))
RIBBON_W = 0.025
RIB_T = 0.0005
ROW_STEP = 0.003
MEDAL_R = 0.035
RIBBON_HEX = dict(blue='#2446a8', red='#cc1f27')

# layer 1 = innermost loop ... 4 = outermost (on top). plane: final depth of the lanyard's flat V relative to
# the neck centre, + toward the seat. drop: D-ring bar below the neck axis. t: lateral offset of the V apex.
# bow: gentle lateral sag of the tails (mm). twist: 'A'/'B' tail with a half twist. lean: loop lean (deg).
SPECS = [
    dict(name='m1', layer=4, plane=+0.021, drop=0.190, t=+0.004, bow=(5, -3), twist='A', lean=6, metal='gold',
         ribbon='blue', off_s=+0.0008),
    dict(name='m2', layer=3, plane=+0.007, drop=0.160, t=-0.016, bow=(-4, 6), twist=None, lean=-4, metal='silver',
         ribbon='red', off_s=-0.0006),
    dict(name='m3', layer=2, plane=-0.007, drop=0.222, t=+0.018, bow=(3, 5), twist=None, lean=8, metal='silver',
         ribbon='red', off_s=+0.0004),
    dict(name='m4', layer=1, plane=-0.021, drop=0.176, t=-0.004, bow=(-6, -2), twist=None, lean=-7, metal='silver',
         ribbon='red', off_s=-0.0002),
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


def link_new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


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


# =============================================================================== 2D helpers
def cross2(a, b):
    return a.x * b.y - a.y * b.x


def clean_poly(pts, tol=0.0003):
    out = []
    for p in pts:
        p = Vector(p).to_2d()
        if not out or (p - out[-1]).length > tol:
            out.append(p)
    while len(out) > 2 and (out[0] - out[-1]).length < tol:
        out.pop()
    if sum(cross2(out[i], out[(i + 1) % len(out)]) for i in range(len(out))) < 0:
        out.reverse()
    return out


def offset_poly(poly, off, arc_step=math.radians(8)):
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
        for k in range(steps + 1):
            a = a0 + da * k / steps
            res.append(p1 + Vector((math.cos(a), math.sin(a))) * off)
    return clean_poly(res, 0.0002)


# =============================================================================== materials (static)
def metal_pair(name, polished, antique, r_pol, r_ant):
    return (metal_mat(f'medals_{name}_polished', polished, r_pol),
            metal_mat(f'medals_{name}_antique', antique, r_ant, grain=0.14, grain_scale=3500))


def build_mats():
    M = {}
    for k, hx in RIBBON_HEX.items():
        M['ribbon_' + k] = fabric_mat('medals_ribbon_' + k, hx)
    M['gold'] = metal_pair('gold', (0.90, 0.64, 0.26), (0.32, 0.22, 0.08), 0.24, 0.62)
    M['silver'] = metal_pair('silver', (0.84, 0.84, 0.82), (0.26, 0.26, 0.26), 0.22, 0.62)
    M['nickel'] = metal_mat('medals_nickel', (0.70, 0.69, 0.66), 0.25)
    return M


# =============================================================================== medal geometry (reference style)
def box_relief(mb, cx, cz, sx, sz, y0, h, mat, bev=0.0003, face=1):
    """Raised block on the front (face=+1) or back (face=-1) field: size sx x sz, height h above y0."""
    fr = Matrix.Translation(Vector((cx, face * (y0 + h / 2 - 0.0001), cz)))
    rounded_box(mb, fr, (sx, h + 0.0002, sz), min(bev, h * 0.45, sx * 0.3, sz * 0.3), mat=mat)


def frame_relief(mb, cx, cz, outer, band, y0, h, mat, face=1):
    """Raised square frame (band wide) as four bars."""
    o2, b = outer / 2, band
    box_relief(mb, cx, cz + o2 - b / 2, outer, b, y0, h, mat, face=face)
    box_relief(mb, cx, cz - o2 + b / 2, outer, b, y0, h, mat, face=face)
    box_relief(mb, cx - o2 + b / 2, cz, b, outer - 2 * b, y0, h, mat, face=face)
    box_relief(mb, cx + o2 - b / 2, cz, b, outer - 2 * b, y0, h, mat, face=face)


def medal_frc(R):
    """Cast medal in the reference style. Local frame: X across, +Y = obverse normal, Z up. mat 0 polished,
    1 antique field. Relief is blank-ish: shapes where the artwork and lettering are, no actual text."""
    mb = MB()
    T_f, T_b = 0.0014, -0.0014
    prof = [(0.0, T_f), (0.5 * R, T_f), (R - 0.0033, T_f), (R - 0.0030, T_f + 0.00045),
            (R - 0.0026, T_f + 0.0006), (R - 0.0009, T_f + 0.0006), (R - 0.0002, T_f + 0.0002),
            (R, T_f - 0.0003), (R, T_b + 0.0003), (R - 0.0002, T_b - 0.0002), (R - 0.0009, T_b - 0.0006),
            (R - 0.0026, T_b - 0.0006), (R - 0.0030, T_b - 0.00045), (R - 0.0033, T_b), (0.5 * R, T_b), (0.0, T_b)]
    field = {0, 1, 13, 14}
    lathe(mb, prof, 48, lambda i: 1 if i in field else 0)
    s = R / 0.035
    # obverse: framed artwork panel, block relief, corner icons, word-mark band, sub-line
    frame_relief(mb, 0.0, 0.0055 * s, 0.034 * s, 0.0022 * s, T_f, 0.0006, 0)
    # (local +X appears on the viewer's LEFT when looking at the obverse, so x positions are mirrored)
    box_relief(mb, 0.001 * s, 0.0065 * s, 0.017 * s, 0.009 * s, T_f, 0.0011, 0, bev=0.0005)        # the block
    box_relief(mb, -0.0045 * s, 0.0085 * s, 0.0075 * s, 0.006 * s, T_f + 0.0011, 0.0005, 0, bev=0.0003)
    box_relief(mb, 0.0105 * s, 0.017 * s, 0.0032 * s, 0.0032 * s, T_f, 0.0004, 0)                 # gear
    box_relief(mb, -0.0105 * s, 0.017 * s, 0.0026 * s, 0.0034 * s, T_f, 0.0004, 0)                # lock
    for k in range(3):                                                                            # bricks
        box_relief(mb, (0.0115 - 0.0028 * k) * s, -0.0045 * s, 0.0024 * s, 0.0014 * s, T_f, 0.0003, 0)
    box_relief(mb, -0.0105 * s, -0.0045 * s, 0.0036 * s, 0.0008 * s, T_f, 0.0003, 0)              # hammer
    box_relief(mb, 0.0, -0.0175 * s, 0.031 * s, 0.0058 * s, T_f, 0.0007, 0, bev=0.0004)            # word mark
    box_relief(mb, 0.0, -0.0238 * s, 0.024 * s, 0.0022 * s, T_f, 0.0004, 0)                       # sub-line
    # reverse: interlocking-loop logo and four text bands
    for dx in (-0.0035, 0.0035):
        torus(mb, Vector((dx * s, T_b - 0.0001, 0.0185 * s)), Vector((0, 1, 0)), 0.0045 * s, 0.0007, seg=18, segm=6,
              mat=0)
    box_relief(mb, 0.0, 0.0085 * s, 0.019 * s, 0.0042 * s, -T_b, 0.0005, 0, face=-1)
    box_relief(mb, 0.0, 0.0015 * s, 0.033 * s, 0.0048 * s, -T_b, 0.0005, 0, face=-1)
    box_relief(mb, 0.0, -0.0055 * s, 0.044 * s, 0.0048 * s, -T_b, 0.0005, 0, face=-1)
    box_relief(mb, 0.0, -0.0150 * s, 0.014 * s, 0.0045 * s, -T_b, 0.0005, 0, face=-1)
    box_relief(mb, 0.0, -0.0245 * s, 0.008 * s, 0.0012 * s, -T_b, 0.0003, 0, face=-1)
    # pierced tab on top (a thick washer on a short neck)
    tab_c = Vector((0, 0, R + 0.0031))
    ring = [(0.0021, -0.0012), (0.0048, -0.0012), (0.0048, 0.0012), (0.0021, 0.0012), (0.0021, -0.0012)]
    sub = MB()
    lathe(sub, ring, 20, lambda i: 0)
    mb.extend(sub, xf=Matrix.Translation(tab_c))
    rounded_box(mb, Matrix.Translation(Vector((0, 0, R - 0.0002))), (0.0056, 0.0024, 0.0034), 0.0005, mat=0)
    return mb, tab_c


def sweep_tube(mb, path, radius, seg=12, closed=True, mat=0):
    """Round wire along a polyline (closed loop by default)."""
    n = len(path)
    rings = []
    for i in range(n):
        a = path[(i - 1) % n] if closed else path[max(i - 1, 0)]
        b = path[(i + 1) % n] if closed else path[min(i + 1, n - 1)]
        tan = (b - a).normalized()
        nrm = tan.orthogonal().normalized() if i == 0 else (rings_n[-1] - tan * rings_n[-1].dot(tan)).normalized()
        if i == 0:
            rings_n = [nrm]
        else:
            rings_n.append(nrm)
        bn = tan.cross(nrm)
        rings.append([mb.vert(path[i] + (nrm * math.cos(2 * math.pi * j / seg) + bn * math.sin(2 * math.pi * j / seg))
                              * radius) for j in range(seg)])
    m = n if closed else n - 1
    for i in range(m):
        A, B = rings[i], rings[(i + 1) % n]
        for j in range(seg):
            mb.face([A[j], A[(j + 1) % seg], B[(j + 1) % seg], B[j]], mat)


def d_ring_path(c_top, w_axis, width, height, n=12):
    """D-ring centreline in the plane of w_axis and Z: straight top bar centred at c_top, round bottom."""
    hw = width / 2
    pts = [c_top + w_axis * (-hw + 2 * hw * k / n) for k in range(n)]
    for k in range(3 * n):
        a = math.pi * k / (3 * n)
        pts.append(c_top + w_axis * (hw * math.cos(a)) - Z * (height * math.sin(a)))
    return pts


# =============================================================================== build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    M = build_mats()
    coll = link_new_collection('NEW_medals')
    refc = link_new_collection('REF_lamp')
    with bpy.data.libraries.load(LAMP_BLEND, link=False) as (src, dst):
        dst.objects = list(src.objects)
    for o in dst.objects:
        if o is not None:
            refc.objects.link(o)
    bpy.context.view_layer.update()
    with open(os.path.join(PARTS, 'lamp_meta.json')) as f:
        LM = json.load(f)
    n0, n1 = Vector(LM['neck_start']), Vector(LM['neck_end'])
    NC = (n0 + n1) / 2
    a3 = (n1 - n0)
    a3.z = 0
    span = a3.length
    a3.normalize()
    t3 = Z.cross(a3).normalized()
    AT, AZ = LM['neck_at'], LM['neck_az']
    s_c = span / 2
    O = Vector((n0.x, n0.y, 0))

    def to_w(s, t, z):
        return O + a3 * s + t3 * t + Z * z
    seat_dir = (SEAT - NC)
    seat_dir.z = 0
    seat_dir.normalize()
    print(f'NECK centre {tuple(round(x, 4) for x in NC)} span {span * 1000:.1f}mm section {2 * AT * 1000:.0f}x{2 * AZ * 1000:.0f}mm; '
          f'reach vs seat {math.degrees(a3.angle(seat_dir)):.1f} deg')

    arm = next(o for o in refc.objects if o.name.startswith('lamp_arm'))
    hull_pts = []
    for v in arm.data.vertices:
        p = arm.matrix_world @ v.co
        q = p - O
        sp, tp = q.dot(a3), q.dot(t3)
        if abs(sp - s_c) < 0.0065 and abs(tp) < 0.04 and abs(p.z - NC.z) < 0.03:
            hull_pts.append(Vector((tp, p.z - NC.z)))
    sec = clean_poly([hull_pts[i] for i in convex_hull_2d(hull_pts)])
    AT = max(abs(p.x) for p in sec)
    print(f'NECK section hull: {len(sec)} pts, half-width {AT * 1000:.1f}mm, z [{min(p.y for p in sec) * 1000:.1f},'
          f'{max(p.y for p in sec) * 1000:.1f}]mm')
    W = RIBBON_W
    L = 0.002
    T_START = AT + 0.0012 + 1.5 * L
    T_END = 0.0145
    Z_T0, Z_T1 = NC.z - 0.010, NC.z - 0.050
    Z_FAN = NC.z - 0.120
    WS_G = 0.012 / W                 # pinched to 12 mm over the neck bulb's narrow waist
    AB = 0.00145

    def sm(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)
    ribbons, parts_of = [], {}
    tris = {}
    lanyards = []
    for spec in SPECS:
        k = spec['layer']
        d_k = (k - 2.5) * L
        off_k = 0.0012 + (k - 1) * L
        offs = spec['off_s']
        s_k = s_c + spec['plane']
        t_k = spec['t']
        z_ap = NC.z - spec['drop']
        lean = math.tan(math.radians(spec['lean']))
        # ---- control points: A wrap bottom -> A tail up -> loop -> B tail down -> B wrap bottom
        def tail(sg):
            pts = []
            ab = -sg * AB                                   # A (sg -1) in front of the bar, B behind
            bow = spec['bow'][0 if sg < 0 else 1] * 0.001
            te = Vector((s_c + d_k, sg * T_END - sg * offs, Z_T1))
            for f in (0.12, 0.3, 0.5, 0.7, 0.88):
                z = Z_T1 + (z_ap - Z_T1) * f
                s_ = s_c + d_k + (s_k - s_c - d_k) * sm((Z_T1 - z) / (Z_T1 - Z_FAN)) + ab * sm((f - 0.55) / 0.45)
                t_ = te.y + (t_k - te.y) * f + bow * math.sin(math.pi * f)
                pts.append(to_w(s_, t_, z))
            pts.append(to_w(s_k + ab, t_k, z_ap))
            return te, pts
        teA, A = tail(-1)
        teB, B = tail(+1)
        ctrl = []
        # A wrap: bottom of the bar -> front quarter
        for i in range(4):
            ph = math.pi / 2 * (1 - i / 3)
            ctrl.append((to_w(s_k + AB * math.cos(ph), t_k, z_ap - AB * math.sin(ph)), t3.copy(), 1.0))
        for p in reversed(A[:-1]):
            ctrl.append((p, t3.copy(), 1.0))
        ctrl.append((to_w(teA.x, teA.y, teA.z), t3.copy(), 1.0))
        # twist zone + gather (A side), placeholders refined analytically below
        def twist_pt(sg, u):
            th = math.pi / 2 * sm(u)
            ax = sg * (T_START + (T_END - T_START) * sm(u))
            return (to_w(s_c + offs * math.cos(th) + d_k * math.sin(th),
                         ax + sg * (-offs * math.sin(th) + d_k * math.cos(th)), Z_T0 + (Z_T1 - Z_T0) * u),
                    math.cos(th) * a3 - math.sin(th) * sg * t3, WS_G + (1 - WS_G) * sm((u - 0.4) / 0.6))
        for u in (0.66, 0.33, 0.0):
            ctrl.append(twist_pt(-1.0, u))
        # loop over the neck: the neck bulb's real cross-section, offset per layer (nested, never crossing)
        ring = offset_poly(sec, off_k)
        up = [p for p in ring if p.y >= -0.004]
        up.sort(key=lambda p: -math.atan2(p.y, p.x) % (2 * math.pi))
        up.sort(key=lambda p: math.atan2(p.y, p.x), reverse=True)
        stepped = [up[0]]
        for p in up[1:]:
            if (p - stepped[-1]).length > 0.0025:
                stepped.append(p)
        if (up[-1] - stepped[-1]).length > 1e-6:
            stepped.append(up[-1])
        for p in stepped:
            ctrl.append((to_w(s_c + offs + lean * p.y, p.x, NC.z + p.y), a3.copy(), WS_G))
        for u in (0.0, 0.33, 0.66):
            ctrl.append(twist_pt(1.0, u))
        ctrl.append((to_w(teB.x, teB.y, teB.z), t3.copy(), 1.0))
        for p in B[:-1]:
            ctrl.append((p, t3.copy(), 1.0))
        for i in range(4):
            ph = math.pi / 2 * i / 3
            ctrl.append((to_w(s_k - AB * math.cos(ph), t_k, z_ap - AB * math.sin(ph)), t3.copy(), 1.0))
        rows, length = ribbon_rows(ctrl)
        # ---- exact geometry: twist zone is a rigid rotation of each side's layered stack; elsewhere the
        # width lies in the lanyard's plane (a3 x tangent) with continuity, plus the optional half twist
        top_i = max(range(len(rows)), key=lambda i: rows[i][0].z)
        for i_r, r_ in enumerate(rows):
            p = r_[0]
            sg = -1.0 if i_r < top_i else 1.0
            if Z_T1 <= p.z <= Z_T0:
                u = (Z_T0 - p.z) / (Z_T0 - Z_T1)
                th = math.pi / 2 * sm(u)
                ax = sg * (T_START + (T_END - T_START) * sm(u))
                s_ = s_c + offs * math.cos(th) + d_k * math.sin(th)
                t_ = ax + sg * (-offs * math.sin(th) + d_k * math.cos(th))
                r_[0] = to_w(s_, t_, p.z)
                r_[1] = math.cos(th) * a3 - math.sin(th) * sg * t3
                r_[3] = WS_G + (1 - WS_G) * sm((u - 0.4) / 0.6)
            elif p.z > Z_T0:
                r_[3] = WS_G
        # orient the lower regions by continuity from the twist zone outward
        def lower_orient(indices):
            prev = None
            for i_r in indices:
                r_ = rows[i_r]
                if r_[0].z >= Z_T1:
                    prev = r_[1]
                    continue
                a_ = rows[max(i_r - 1, 0)][0]
                b_ = rows[min(i_r + 1, len(rows) - 1)][0]
                wn = a3.cross((b_ - a_).normalized())
                if wn.length < 1e-6:
                    wn = t3.copy()
                wn.normalize()
                if prev is not None and wn.dot(prev) < 0:
                    wn = -wn
                r_[1] = wn
                r_[3] = 1.0
                prev = wn
        lower_orient(range(top_i, -1, -1))
        lower_orient(range(top_i, len(rows)))
        # the half twist (gentle, over ~70 mm of one tail, above the fan-out end)
        if spec['twist']:
            z_hi, z_lo = Z_FAN - 0.002, Z_FAN - 0.072
            idx = range(0, top_i) if spec['twist'] == 'A' else range(top_i, len(rows))
            for i_r in idx:
                r_ = rows[i_r]
                if r_[0].z < z_hi:
                    f = sm((z_hi - r_[0].z) / (z_hi - z_lo))
                    a_ = rows[max(i_r - 1, 0)][0]
                    b_ = rows[min(i_r + 1, len(rows) - 1)][0]
                    tan = (b_ - a_).normalized()
                    r_[1] = Quaternion(tan, math.pi * f) @ r_[1]
        lanyards.append(dict(spec=spec, rows=rows, length=length, s_k=s_k, t_k=t_k, z_ap=z_ap))
        print(f'RIBBON {spec["name"]} layer {k} len {length * 100:.1f}cm rows {len(rows)} apex drop {spec["drop"] * 1000:.0f}mm')

    # ---- ribbon meshes
    objs = []
    for ly in lanyards:
        spec = ly['spec']
        cols = [0, 0.25, 0.5, 0.75, 1.0]
        verts, faces, uvs = [], [], []
        nc = len(cols)
        for (pos, w, s, ws) in ly['rows']:
            for u in cols:
                verts.append(pos + w * ((u - 0.5) * W * ws))
        for r in range(len(ly['rows']) - 1):
            sa, sb = ly['rows'][r][2], ly['rows'][r + 1][2]
            for c_ in range(nc - 1):
                a = r * nc + c_
                faces.append((a, a + 1, a + nc + 1, a + nc))
                uvs.append([(cols[c_] * W, sa), (cols[c_ + 1] * W, sa), (cols[c_ + 1] * W, sb), (cols[c_] * W, sb)])
        me = bpy.data.meshes.new(f'medal_{spec["name"]}_ribbon')
        me.from_pydata([tuple(v) for v in verts], [], faces)
        me.update()
        uvl = me.uv_layers.new(name='UVMap')
        for j, p in enumerate(me.polygons):
            for li, lp in enumerate(p.loop_indices):
                uvl.data[lp].uv = uvs[j][li]
        me.materials.append(M['ribbon_' + spec['ribbon']])
        o = bpy.data.objects.new(f'medal_{spec["name"]}_ribbon', me)
        coll.objects.link(o)
        sm_ = o.modifiers.new('solidify', 'SOLIDIFY')
        sm_.thickness = RIB_T
        sm_.offset = 0.0
        sm_.use_rim = True
        sm_.use_quality_normals = True
        dg = bpy.context.evaluated_depsgraph_get()
        nm = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        o.modifiers.remove(sm_)
        old = o.data
        o.data = nm
        bpy.data.meshes.remove(old)
        nm.name = f'medal_{spec["name"]}_ribbon'
        nm.shade_smooth()
        nm.set_sharp_from_angle(angle=math.radians(60))
        objs.append(o)
        tris[o.name] = sum(len(p.vertices) - 2 for p in nm.polygons)

    # ---- D-ring, split ring, medal (faces the seat)
    for ly in lanyards:
        spec = ly['spec']
        nmn = spec['name']
        c_top = to_w(ly['s_k'], ly['t_k'], ly['z_ap'])
        mbr = MB()
        DR_W, DR_H, DR_r = 0.028, 0.011, 0.0011
        sweep_tube(mbr, d_ring_path(c_top, t3, DR_W, DR_H, n=8), DR_r, seg=8)
        # split ring: plane spanned by the seat direction and Z, hanging from the D-ring's bottom wire
        u_face = (SEAT - c_top)
        u_face.z = 0
        u_face.normalize()
        Rr, rr = 0.0045, 0.0006
        d_bottom = c_top - Z * DR_H
        ring_c = d_bottom - Z * (Rr - DR_r - rr)
        torus(mbr, ring_c, Z.cross(u_face).normalized(), Rr, rr, seg=18, segm=6, mat=0)
        clasp = mbr.to_object(f'medal_{nmn}_clasp', [M['nickel']], coll, smooth_angle=45)
        objs.append(clasp)
        tris[clasp.name] = sum(len(p.vertices) - 2 for p in clasp.data.polygons)
        # medal: its tab hole hangs on the split ring's bottom wire
        mesh, tab_c = medal_frc(MEDAL_R)
        hole_r = 0.0021
        ring_bottom_wire = ring_c - Z * Rr
        tab_world = ring_bottom_wire - Z * (hole_r - rr)          # the ring's wire rests on the top of the hole
        Mc = tab_world - tab_c
        x_ax = u_face.cross(Z).normalized()
        xf = Matrix.Translation(Mc) @ Matrix(((x_ax.x, u_face.x, 0, 0), (x_ax.y, u_face.y, 0, 0),
                                              (x_ax.z, u_face.z, 1, 0), (0, 0, 0, 1)))
        mbx = MB()
        mbx.extend(mesh, xf=xf)
        pm, am = M[spec['metal']]
        med = mbx.to_object(f'medal_{nmn}_disc', [pm, am], coll, smooth_angle=35)
        objs.append(med)
        tris[med.name] = sum(len(p.vertices) - 2 for p in med.data.polygons)
        ly['Mc'] = Mc
        print(f'MEDAL {nmn} {spec["metal"]} centre {tuple(round(x, 4) for x in Mc)} bottom z {Mc.z - MEDAL_R:.4f}')

    # ---- root (parent to NEW_lamp_pivot in the room, keeping transform)
    root = bpy.data.objects.new('NEW_medals_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.03
    root.location = n0
    root['parent_to'] = 'NEW_lamp_pivot'
    coll.objects.link(root)
    bpy.context.view_layer.update()
    for o in objs:
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()
        o.matrix_world = mw

    # ---- clearance checks: every pair of different lanyards, and everything vs the lamp
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    def data(o):
        ev = o.evaluated_get(dg)
        m = ev.to_mesh()
        V = [ev.matrix_world @ v.co for v in m.vertices]
        F = [tuple(p.vertices) for p in m.polygons]
        ev.to_mesh_clear()
        return V, BVHTree.FromPolygons(V, F)
    D = {o.name: data(o) for o in objs}
    worst = (1.0, None)
    overl = 0
    names = list(D)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if names[i].split('_')[1] == names[j].split('_')[1]:
                continue
            ov = D[names[i]][1].overlap(D[names[j]][1])
            overl += len(ov)
            d_ = min(D[names[j]][1].find_nearest(v)[3] for v in D[names[i]][0][::2])
            if d_ < worst[0]:
                worst = (d_, (names[i], names[j]))
    lamp_objs = [o for o in refc.objects if o.type == 'MESH']
    LV = {o.name: data(o) for o in lamp_objs}
    lamp_min = {}
    for n in names:
        lamp_min[n] = round(min(min(t.find_nearest(v)[3] for v in D[n][0][::3]) for _, t in LV.values()) * 1000, 1)
    lamp_ov = sum(len(D[n][1].overlap(t)) for n in names for _, t in LV.values())
    print(f'CLEARANCE between lanyards: min {worst[0] * 1000:.2f} mm {worst[1]}, overlapping tri pairs {overl}')
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if names[i].split('_')[1] == names[j].split('_')[1]:
                continue
            ov = D[names[i]][1].overlap(D[names[j]][1])
            if ov:
                Vi = D[names[i]][0]
                me_i = bpy.data.objects[names[i]].evaluated_get(dg).to_mesh()
                zs = sorted({round(sum(Vi[v].z for v in me_i.polygons[a].vertices) / len(me_i.polygons[a].vertices) - NC.z, 3)
                             for a, _ in ov})
                bpy.data.objects[names[i]].evaluated_get(dg).to_mesh_clear()
                print(f'  OVERLAP {names[i]} x {names[j]}: {len(ov)} pairs at dz {zs[0]:.3f}..{zs[-1]:.3f}')
    for n in names:
        for ln, (V_, t_) in LV.items():
            ov = D[n][1].overlap(t_)
            if ov:
                Vi = D[n][0]
                me_i = bpy.data.objects[n].evaluated_get(dg).to_mesh()
                zs = sorted({round(sum(Vi[v].z for v in me_i.polygons[a].vertices) / len(me_i.polygons[a].vertices) - NC.z, 3)
                             for a, _ in ov})
                bpy.data.objects[n].evaluated_get(dg).to_mesh_clear()
                print(f'  LAMPOVERLAP {n} x {ln}: {len(ov)} pairs at dz {zs[0]:.3f}..{zs[-1]:.3f}')
    print(f'CLEARANCE to lamp (mm) {lamp_min}, overlapping tri pairs {lamp_ov}')
    total = sum(tris.values())
    print('TRIS', total, json.dumps(tris))
    return dict(scene=scene, coll=coll, refc=refc, lanyards=lanyards, objs=objs, root=root, NC=NC, a3=a3, t3=t3,
                tris=tris, total=total)


# =============================================================================== previews
def previews(b):
    scene = b['scene']
    setup_render(scene)
    refc = b['refc']
    c = b['NC']
    desk = bpy.data.meshes.new('ref_desk')
    desk.from_pydata([(c.x - 0.8, c.y - 0.8, 0.735), (c.x + 0.8, c.y - 0.8, 0.735),
                      (c.x + 0.8, c.y + 0.8, 0.735), (c.x - 0.8, c.y + 0.8, 0.735)], [], [(0, 1, 2, 3)])
    dm = bpy.data.materials.new('ref_desk')
    dm.use_nodes = True
    principled(dm).inputs['Base Color'].default_value = (0.62, 0.33, 0.22, 1)
    principled(dm).inputs['Roughness'].default_value = 0.55
    desk.materials.append(dm)
    refc.objects.link(bpy.data.objects.new('ref_desk', desk))
    target = sum((ly['Mc'] for ly in b['lanyards']), Vector()) / len(b['lanyards'])
    target.z = (target.z - MEDAL_R + c.z) / 2
    add_light(scene, 'key', target + Vector((0.45, -0.55, 0.45)), target, 22, 0.35)
    add_light(scene, 'fill', target + Vector((-0.6, -0.35, 0.15)), target, 7, 0.6, (0.9, 0.95, 1.0))
    add_light(scene, 'rim', target + Vector((-0.2, 0.6, 0.35)), target, 20, 0.3, (1.0, 0.95, 0.9))
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam

    def shot(loc, tgt, lens, fname):
        cam.location = loc
        cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, fname)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', fname)
    dirv = (target - SEAT).normalized()
    side_dir = Vector((-dirv.y, dirv.x, 0)).normalized()
    shot(SEAT, target, 55, 'medals_seat.png')
    three_q = (-dirv * 0.75 + side_dir * 0.62).normalized()
    shot(target + three_q * 0.5 + Vector((0, 0, 0.06)), target, 50, 'medals_34.png')
    shot(target + side_dir * 0.62 + Vector((0, 0, 0.04)), target, 45, 'medals_side.png')
    gold = next(ly for ly in b['lanyards'] if ly['spec']['metal'] == 'gold')
    mt = gold['Mc'] + Vector((0, 0, 0.012))
    shot(mt - dirv * 0.20 + Vector((0, 0, 0.02)), mt, 60, 'medals_closeup.png')


# =============================================================================== save / export / verify
def finish(b):
    for o in list(b['refc'].objects):
        bpy.data.objects.remove(o, do_unlink=True)
    c = bpy.data.collections.get('REF_lamp')
    if c:
        bpy.data.collections.remove(c)
    for o in list(bpy.context.scene.objects):
        if o.type in ('LIGHT', 'CAMERA') or o.name not in b['coll'].all_objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    print('SAVED', OUT_BLEND)
    for o in bpy.context.scene.objects:
        o.select_set(o.name in b['coll'].all_objects)
    bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format='GLB', use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False, export_skins=False,
                              export_materials='EXPORT', export_cameras=False, export_lights=False)
    print('EXPORTED', OUT_GLB, os.path.getsize(OUT_GLB) // 1024, 'KB')


def verify():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=OUT_GLB)
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == 'MESH']
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    print('VERIFY static glb: meshes', len(meshes), 'tris', tris, 'armatures',
          len([o for o in sc.objects if o.type == 'ARMATURE']), 'actions', len(bpy.data.actions))


if __name__ == '__main__':
    b = build()
    if not NO_RENDER:
        previews(b)
    finish(b)
    verify()
    print('DONE')
