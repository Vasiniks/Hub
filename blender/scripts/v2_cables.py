"""
v2_cables.py -- every cable on / behind the desk, rebuilt as one asset set in ROOM coordinates.

    "<blender.exe>" -b --factory-startup --python blender/scripts/v2_cables.py

Writes blender/scene/parts/cables.blend: collection NEW_cables, root empty NEW_cables_root
(identity transform, so every mesh sits at its true room position).

Everything is measured against blender/scene/room.blend (Z-up, metres):
  desk top z 0.735, back edge y 1.130, underside 0.703; under-desk tray rear channel
  y 1.067..1.091 (floor 0.614, apron flange 0.6195 at y 1.051..1.067), tray back wall top 0.6625;
  skirting face y 1.285 (z<0.08), wall y 1.300; floor z 0.
  NEW_macbook (collection NEW_macbook): laptop empty rotated 17.0 deg about X; left flank x -0.2063,
    MagSafe 3 recess 12.4 x 3.8 mm, 2.9 mm deep, floor x -0.2034 (pins to -0.2036),
    centre (-0.2034, 0.7869, 0.8182)
  monitor rear I/O bay (x 0.054..0.126, z 0.995..1.015, recess floor y 0.968), DP receptacle
    x 0.0817..0.0982 z 1.0023..1.0072 face y 0.9765; rear panel y 0.9855

Replaces in room.blend: monitor_cable, Mesh_31 (white MacBook tube), cable_coil, cable_tie,
cable_boot, cable_plug, Mesh_17 (rubber tube dropping from the tray).
Not built here: keyboard cable (keyboard asset), USB hub cable (electronics asset).
"""
import bpy
import bmesh
import math
import os
import random
from mathutils import Vector as V, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), 'scene', 'parts')
OUT = os.path.join(OUT_DIR, 'cables.blend')

DESK = 0.735
EDGE_Y = 1.130
TRAY_FLOOR = 0.614
FLANGE = 0.6195
WALL_TOP = 0.6625
MM = 0.001

random.seed(7)

# ----------------------------------------------------------------------------- scene


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ----------------------------------------------------------------------------- materials

MATS = {}


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def _set(b, name, val):
    if name in b.inputs:
        b.inputs[name].default_value = val


def base_mat(name, colour, rough, metal=0.0, coat=0.0, sheen=0.0, spec=0.5, sss=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = _bsdf(m)
    _set(b, 'Base Color', (*colour, 1.0))
    _set(b, 'Roughness', rough)
    _set(b, 'Metallic', metal)
    _set(b, 'Specular IOR Level', spec)
    if coat:
        _set(b, 'Coat Weight', coat)
        _set(b, 'Coat Roughness', 0.15)
    if sheen:
        _set(b, 'Sheen Weight', sheen)
        _set(b, 'Sheen Roughness', 0.6)
    if sss:
        _set(b, 'Subsurface Weight', sss)
        _set(b, 'Subsurface Radius', (0.002, 0.002, 0.002))
        _set(b, 'Subsurface Scale', 0.002)
    MATS[name] = m
    return m


def add_noise_bump(mat, scale, strength, distance, detail=2.0, coord='Object'):
    """Fine grain so a flat PVC or plastic surface does not read as CG-perfect."""
    nt = mat.node_tree
    b = _bsdf(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = detail
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = distance
    nt.links.new(tc.outputs[coord], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return bump


def braid_mat(name, col_a, col_b, rough, carriers=16, pitch=0.62, sheen=0.3):
    """
    Woven jacket from the tube UVs (u around, v = length in circumferences): two families of
    helical strands, over/under chosen by the parity of the strand indices, so it reads as an
    actual 2-over-2 braid at close range rather than a stripe texture.
    """
    m = base_mat(name, col_a, rough, sheen=sheen)
    nt = m.node_tree
    b = _bsdf(m)
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['UV'], sep.inputs[0])

    def math_node(op, a=None, b_=None, va=0.0, vb=0.0):
        n = nt.nodes.new('ShaderNodeMath')
        n.operation = op
        if a is not None:
            L.new(a, n.inputs[0])
        else:
            n.inputs[0].default_value = va
        if b_ is not None:
            L.new(b_, n.inputs[1])
        else:
            n.inputs[1].default_value = vb
        return n.outputs[0]

    un = math_node('MULTIPLY', sep.outputs['X'], vb=carriers)
    vp = math_node('MULTIPLY', sep.outputs['Y'], vb=carriers * pitch)
    a = math_node('ADD', un, vp)
    c = math_node('SUBTRACT', un, vp)
    fa = math_node('FRACT', a)
    fc = math_node('FRACT', c)
    sa = math_node('SINE', math_node('MULTIPLY', fa, vb=math.pi))
    sc_ = math_node('SINE', math_node('MULTIPLY', fc, vb=math.pi))
    # parity of floor(a)+floor(c) in {0,1}, robust for negatives: fract(x/2)*2
    fl = math_node('ADD', math_node('FLOOR', a), math_node('FLOOR', c))
    par = math_node('MULTIPLY', math_node('FRACT', math_node('MULTIPLY', fl, vb=0.5)), vb=2.0)
    # the strand on top is fully visible, the other only in its gaps
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'FLOAT'
    L.new(par, mix.inputs['Factor'])
    L.new(math_node('MULTIPLY', sc_, vb=0.85), mix.inputs[2])
    L.new(sa, mix.inputs[3])
    # fibre lines along each strand
    fib = math_node('MULTIPLY', math_node('SINE', math_node('MULTIPLY', a, vb=math.pi * 7)), vb=0.08)
    h = math_node('ADD', mix.outputs[0], fib)
    ramp = nt.nodes.new('ShaderNodeMix')
    ramp.data_type = 'RGBA'
    L.new(h, ramp.inputs['Factor'])
    ramp.inputs[6].default_value = (*col_b, 1.0)
    ramp.inputs[7].default_value = (*col_a, 1.0)
    L.new(ramp.outputs[2], b.inputs['Base Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.9
    bump.inputs['Distance'].default_value = 0.00025
    L.new(h, bump.inputs['Height'])
    L.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def make_materials():
    m = base_mat('cbl_pvc_black_matte', (0.016, 0.016, 0.017), 0.62, spec=0.45)
    add_noise_bump(m, 2600, 0.12, 0.0002)
    m = base_mat('cbl_pvc_black_satin', (0.013, 0.013, 0.014), 0.42, spec=0.5)
    add_noise_bump(m, 3000, 0.08, 0.0002)
    m = base_mat('cbl_pvc_grey_hub', (0.055, 0.058, 0.064), 0.5)
    add_noise_bump(m, 2600, 0.1, 0.0002)
    m = base_mat('cbl_pvc_white', (0.80, 0.80, 0.79), 0.38, sss=0.05)
    add_noise_bump(m, 2600, 0.06, 0.0002)
    m = base_mat('cbl_pvc_keyboard_grey', (0.60, 0.62, 0.64), 0.55, sss=0.03)
    add_noise_bump(m, 2600, 0.1, 0.0002)
    braid_mat('cbl_braid_white', (0.82, 0.82, 0.80), (0.46, 0.46, 0.45), 0.55)
    base_mat('conn_metal_nickel', (0.80, 0.80, 0.78), 0.22, metal=1.0)
    base_mat('conn_metal_dark', (0.30, 0.30, 0.30), 0.35, metal=1.0)
    base_mat('conn_insulator_black', (0.012, 0.012, 0.012), 0.5)
    base_mat('conn_insulator_blue', (0.02, 0.08, 0.30), 0.45)
    m = base_mat('conn_overmold_black', (0.018, 0.018, 0.019), 0.45)
    add_noise_bump(m, 1800, 0.08, 0.00015)
    m = base_mat('conn_overmold_grey', (0.60, 0.62, 0.64), 0.45)
    add_noise_bump(m, 1800, 0.06, 0.00015)
    base_mat('conn_overmold_white', (0.84, 0.84, 0.83), 0.3, coat=0.2, sss=0.04)
    m = base_mat('conn_overmold_hubgrey', (0.06, 0.063, 0.07), 0.42)
    add_noise_bump(m, 1800, 0.06, 0.00015)
    m = base_mat('brick_white_pc', (0.86, 0.86, 0.85), 0.30, coat=0.15, sss=0.04)
    add_noise_bump(m, 1400, 0.04, 0.0001)
    base_mat('brick_seam', (0.32, 0.32, 0.32), 0.5)
    m = base_mat('strip_white_abs', (0.78, 0.78, 0.76), 0.42)
    add_noise_bump(m, 1500, 0.1, 0.00015)
    base_mat('strip_recess_grey', (0.46, 0.46, 0.45), 0.55)
    base_mat('strip_rocker_red', (0.55, 0.02, 0.01), 0.25, coat=0.5)
    base_mat('strip_hole_black', (0.004, 0.004, 0.004), 0.9)
    m = base_mat('velcro_black', (0.012, 0.012, 0.013), 0.9, sheen=0.15, spec=0.3)
    add_noise_bump(m, 6000, 0.5, 0.0003, detail=4.0)
    base_mat('ziptie_nylon_black', (0.02, 0.02, 0.02), 0.35)
    base_mat('monitor_inlet_dark', (0.012, 0.012, 0.013), 0.6)
    m = base_mat('magsafe_aluminium', (0.72, 0.73, 0.74), 0.32, metal=1.0)
    add_noise_bump(m, 900, 0.05, 0.0001)
    m = base_mat('magsafe_led_amber', (1.0, 0.45, 0.05), 0.3)
    _set(_bsdf(m), 'Emission Color', (1.0, 0.42, 0.04, 1.0))
    _set(_bsdf(m), 'Emission Strength', 6.0)
    base_mat('magsafe_face_black', (0.02, 0.02, 0.02), 0.4)
    base_mat('magsafe_pad_gold', (0.95, 0.72, 0.38), 0.25, metal=1.0)
    m = base_mat('magsafe_sleeve_silver', (0.62, 0.63, 0.64), 0.42, sss=0.02)
    add_noise_bump(m, 2200, 0.08, 0.00015)
    base_mat('brick_port_dark', (0.008, 0.008, 0.008), 0.6)


# ----------------------------------------------------------------------------- mesh builder


class MB:
    """Collects raw verts/faces (+ per-face material slot and optional per-corner UVs)."""

    def __init__(self, name, mats):
        self.name = name
        self.mats = mats
        self.v = []
        self.f = []
        self.mi = []
        self.uv = []
        self.smooth = []

    def vert(self, p):
        self.v.append((p[0], p[1], p[2]))
        return len(self.v) - 1

    def face(self, idx, mat=0, uvs=None, smooth=True):
        self.f.append(list(idx))
        self.mi.append(mat)
        self.uv.append(uvs)
        self.smooth.append(smooth)

    def build(self, coll, sharp_deg=38):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.v, [], self.f)
        me.validate(clean_customdata=False)
        orient_closed_islands(me)
        for m in self.mats:
            me.materials.append(MATS[m])
        me.polygons.foreach_set('material_index', self.mi[:len(me.polygons)])
        uvl = me.uv_layers.new(name='UVMap')
        k = 0
        for poly, uvs in zip(me.polygons, self.uv):
            for j, li in enumerate(poly.loop_indices):
                uvl.data[li].uv = uvs[j] if uvs else (0.0, 0.0)
        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
        try:
            me.set_sharp_from_angle(angle=math.radians(sharp_deg))
        except Exception:
            pass
        ob = bpy.data.objects.new(self.name, me)
        coll.objects.link(ob)
        return ob


def orient_closed_islands(me):
    """Every closed (manifold) island gets outward normals: flip it if its signed volume is negative.
    Open pieces keep the winding their right-handed loft frames give them."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    seen = set()
    flipped = False
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        island = []
        stack = [f0]
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            island.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        if any(len(e.link_faces) != 2 for f in island for e in f.edges):
            continue
        c = sum((v.co for f in island for v in f.verts), V()) / sum(len(f.verts) for f in island)
        vol = 0.0
        for f in island:
            vs = [v.co - c for v in f.verts]
            for k in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[k].cross(vs[k + 1]))
        if vol < 0:
            bmesh.ops.reverse_faces(bm, faces=island)
            flipped = True
    if flipped:
        bm.to_mesh(me)
    bm.free()


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# ----------------------------------------------------------------------------- profiles


def circ(r, n, start=0.0):
    return [(r * math.cos(start + 2 * math.pi * i / n), r * math.sin(start + 2 * math.pi * i / n))
            for i in range(n)]


def rrect(w, h, r, seg=4):
    """Rounded rectangle, CCW, 4*(seg+1) points; r is clamped just under the half-extents."""
    r = max(1e-5, min(r, w / 2 * 0.999, h / 2 * 0.999))
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def inset_rrect(w, h, r, d, seg=4):
    return rrect(w - 2 * d, h - 2 * d, max(r - d, 1e-4), seg)


def fig8(a, c, n=40):
    """Outline of two overlapping circles (radius a, centres at +-c): the IEC C7 figure-8."""
    pts = []
    for i in range(n):
        phi = 2 * math.pi * i / n
        d = (math.cos(phi), math.sin(phi))
        best = 0
        for cx in (c, -c):
            dc = d[0] * cx
            disc = dc * dc - cx * cx + a * a
            if disc >= 0:
                best = max(best, dc + math.sqrt(disc))
        pts.append((best * d[0], best * d[1]))
    return pts


def scale2(pts, sx, sy=None):
    sy = sx if sy is None else sy
    return [(x * sx, y * sy) for x, y in pts]


def shift2(pts, dx, dy):
    return [(x + dx, y + dy) for x, y in pts]


# ----------------------------------------------------------------------------- frames & lofts


def frame(origin, zdir, xdir):
    z = V(zdir).normalized()
    x = V(xdir)
    x = (x - z * x.dot(z)).normalized()
    y = z.cross(x)
    return (V(origin), x, y, z)


def fpt(fr, px, py, pz):
    o, x, y, z = fr
    return o + x * px + y * py + z * pz


def loft(mb, fr, sections, mat=0, cap0=True, cap1=True, cap_mat=None):
    """Sections [(z, pts2d)], all with the same point count, lofted along the frame's Z."""
    o_, x_, y_, z_ = fr
    if x_.cross(y_).dot(z_) < 0:          # left-handed frame: mirror x so faces still point outward
        fr = (o_, -x_, y_, z_)
    rings = []
    for z, pts in sections:
        rings.append([mb.vert(fpt(fr, px, py, z)) for px, py in pts])
    n = len(sections[0][1])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            mb.face([a[i], a[j], b[j], b[i]], mat)
    cm = mat if cap_mat is None else cap_mat
    if cap0:
        mb.face(list(reversed(rings[0])), cm)
    if cap1:
        mb.face(rings[-1], cm)
    return rings


def box(mb, fr, w, h, z0, z1, r=0.0002, mat=0, seg=2):
    p = rrect(w, h, r, seg)
    return loft(mb, fr, [(z0, p), (z1, p)], mat)


# ----------------------------------------------------------------------------- curves


def catmull(points, per_seg=24, alpha=0.5):
    """Centripetal Catmull-Rom through the control points (no overshoot loops)."""
    P = [V(p) for p in points]
    if len(P) < 2:
        return P
    P = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]

        def tj(ti, a, b):
            return ti + max((b - a).length, 1e-6) ** alpha
        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        for k in range(per_seg):
            t = t1 + (t2 - t1) * k / per_seg
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
    out.append(P[-2])
    return out


def resample(poly, step):
    """Uniform arc-length resample."""
    out = [poly[0]]
    acc = 0.0
    for a, b in zip(poly, poly[1:]):
        seg = (b - a).length
        while acc + seg >= step and seg > 0:
            t = (step - acc) / seg
            a = a.lerp(b, t)
            out.append(a)
            seg = (b - a).length
            acc = 0.0
        acc += seg
    if (out[-1] - poly[-1]).length > step * 0.3:
        out.append(poly[-1])
    else:
        out[-1] = poly[-1]
    return out


def adaptive(poly, max_len, max_deg):
    """Keep a ring only where the curve has turned enough (or gone far enough) since the last."""
    keep = [poly[0]]
    last_t = (poly[1] - poly[0]).normalized()
    dist = 0.0
    for i in range(1, len(poly) - 1):
        dist += (poly[i] - poly[i - 1]).length
        t = (poly[i + 1] - poly[i]).normalized()
        ang = math.degrees(last_t.angle(t, 0.0))
        if ang > max_deg or dist > max_len:
            keep.append(poly[i])
            last_t = t
            dist = 0.0
    keep.append(poly[-1])
    return keep


def rest_on_surfaces(poly, r):
    """Nothing sinks: desk top (inside its footprint), tray floors and room floor."""
    out = []
    for p in poly:
        q = p.copy()
        if -1.03 < q.x < 0.99 and 0.355 < q.y < EDGE_Y - 0.001 and DESK - 0.012 < q.z < DESK + r:
            q.z = DESK + r
        if -0.78 < q.x < 0.74 and 1.068 < q.y < 1.090 and 0.605 < q.z < TRAY_FLOOR + r:
            q.z = TRAY_FLOOR + r
        if q.z < r and not (0.95 < q.x):
            q.z = r
        out.append(q)
    return out


def path(ctrl, r, max_len=0.02, max_deg=5.0, clamp=True):
    dense = resample(catmull(ctrl, 30), 0.0008)
    if clamp:
        dense = rest_on_surfaces(dense, r)
    return adaptive(dense, max_len, max_deg)


def tube(mb, pts, r, sides, mat=0, cap0=True, cap1=True, twist=0.0):
    """Sweep a circle along pts with parallel-transport frames; UV u around, v in circumferences."""
    n = len(pts)
    T = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        T.append((b - a).normalized())
    ref = V((0, 0, 1)) if abs(T[0].z) < 0.9 else V((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    rings = []
    s = 0.0
    circ_len = 2 * math.pi * r
    vcoord = []
    for i in range(n):
        if i > 0:
            axis = T[i - 1].cross(T[i])
            if axis.length > 1e-9:
                ang = T[i - 1].angle(T[i], 0.0)
                N = Matrix.Rotation(ang, 3, axis.normalized()) @ N
            N = (N - T[i] * N.dot(T[i])).normalized()
            s += (pts[i] - pts[i - 1]).length
        B = T[i].cross(N)
        rot = twist * s
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides + rot
            ring.append(mb.vert(pts[i] + (N * math.cos(a) + B * math.sin(a)) * r))
        rings.append(ring)
        vcoord.append(s / circ_len)
    for i in range(n - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            uvs = [(k / sides, vcoord[i]), (k / sides, vcoord[i + 1]),
                   ((k + 1) / sides, vcoord[i + 1]), ((k + 1) / sides, vcoord[i])]
            mb.face([rings[i][k], rings[i + 1][k], rings[i + 1][k2], rings[i][k2]], mat, uvs)
    if cap0:
        mb.face(list(reversed(rings[0])), mat)
    if cap1:
        mb.face(rings[-1], mat)
    return s


# ----------------------------------------------------------------------------- connectors
#
# Every connector is built in a frame whose origin is the port face, Z pointing OUT of the port
# (along the cable), X along the connector's long axis. Negative z is inside the port.
# Each returns the point where the cable leaves the strain relief, and its direction.


def boot(mb, fr, z0, r0, r1, length, cable_r, mat, ribs=0, n=20):
    """Strain relief: taper from r0 to cable, optional moulded ribs, blends into the cable."""
    secs = []
    steps = 10
    for i in range(steps + 1):
        t = i / steps
        # a soft S-taper: fat near the plug, then pinched onto the cable
        rr = r0 + (r1 - r0) * (3 * t * t - 2 * t * t * t)
        secs.append((z0 + length * t, rr))
    if ribs:
        rib_secs = []
        for i, (z, rr) in enumerate(secs):
            rib_secs.append((z, rr))
        out = []
        for i in range(len(rib_secs) - 1):
            za, ra = rib_secs[i]
            zb, rb = rib_secs[i + 1]
            out.append((za, ra))
            if 0 < i < len(rib_secs) - 3:
                zm = (za + zb) / 2
                out.append((zm - 0.00025, (ra + rb) / 2 * 1.0))
                out.append((zm, (ra + rb) / 2 * 0.93))
                out.append((zm + 0.00025, (ra + rb) / 2 * 1.0))
        out.append(rib_secs[-1])
        secs = out
    secs.append((z0 + length + 0.0015, cable_r * 1.0))
    loft(mb, fr, [(z, circ(rr, n)) for z, rr in secs], mat, cap0=True, cap1=False)
    return fpt(fr, 0, 0, z0 + length + 0.0012)


def usb_c(mb, fr, mats, body='black', insert=0.0062, length=0.0165, boot_len=0.011, cable_r=0.002,
          ribs=0, show_mouth=True, body_w=0.0122, body_h=0.0064):
    """USB-C plug: stadium nickel shell with a dark mouth + tongue, rounded overmold, boot."""
    M_SHELL, M_INS, M_BODY = mats
    sw, sh = 0.00835, 0.00256
    outer = rrect(sw, sh, sh / 2, 5)
    inner = rrect(sw - 0.0005, sh - 0.0005, (sh - 0.0005) / 2, 5)
    z_tip = -insert
    if show_mouth:
        secs = [(z_tip + 0.0016, inner), (z_tip, inner), (z_tip, scale2(outer, 0.985)),
                (z_tip + 0.0003, outer), (0.0012, outer)]
        rings = loft(mb, fr, secs, M_SHELL, cap0=True, cap1=True)
        # replace the deep cap with the dark insulator: tongue sits in the mouth
        mb.mi[-2] = M_INS
        tongue = rrect(0.0066, 0.0007, 0.0003, 2)
        loft(mb, fr, [(z_tip + 0.0016, tongue), (z_tip + 0.0006, tongue)], M_INS, cap0=True, cap1=True)
    else:
        loft(mb, fr, [(z_tip, scale2(outer, 0.97)), (z_tip + 0.0004, outer), (0.0012, outer)], M_SHELL)
    # overmold: soft nose, straight body, slight waist toward the boot
    bw, bh = body_w, body_h
    br = min(bh / 2 * 0.95, 0.0028)
    secs = [(0.0004, inset_rrect(bw, bh, br, 0.0009, 5)),
            (0.0009, inset_rrect(bw, bh, br, 0.0003, 5)),
            (0.0018, rrect(bw, bh, br, 5)),
            (length - 0.004, rrect(bw, bh, br, 5)),
            (length - 0.0012, inset_rrect(bw, bh, br, 0.0004, 5)),
            (length, inset_rrect(bw, bh, br, 0.0014, 5))]
    loft(mb, fr, secs, M_BODY)
    r0 = min(bw, bh) / 2 * 0.95
    return boot(mb, fr, length - 0.0015, r0, cable_r * 1.25, boot_len, cable_r, M_BODY, ribs=ribs), fr[3]


def usb_a(mb, fr, mats, length=0.021, boot_len=0.012, cable_r=0.002, ribs=4):
    M_SHELL, M_INS, M_BODY = mats
    sw, sh = 0.0120, 0.0045
    outer = rrect(sw, sh, 0.0004, 2)
    inner = rrect(sw - 0.0005, sh - 0.0005, 0.0002, 2)
    z_tip = -0.0118
    loft(mb, fr, [(z_tip + 0.0085, inner), (z_tip, inner), (z_tip, scale2(outer, 0.99)),
                  (z_tip + 0.0003, outer), (0.001, outer)], M_SHELL, cap0=True, cap1=True)
    mb.mi[-2] = M_INS
    # plastic tongue (the half-height insulator of a USB-A plug)
    tg = shift2(rrect(0.0108, 0.0018, 0.0002, 2), 0, -0.0009)
    loft(mb, fr, [(z_tip + 0.0085, tg), (z_tip + 0.0004, tg)], M_INS)
    # latch windows: two dark slots pressed into the shell's top face
    for sx in (-0.0035, 0.0035):
        win = rrect(0.0022, 0.0022, 0.0002, 1)
        o, x, y, z = fr
        wfr = (fpt(fr, sx, sh / 2 + 0.00003, z_tip + 0.0045), x, -z, y)
        loft(mb, wfr, [(0.0, win), (0.00002, win)], M_INS, cap0=False)
    bw, bh, br = 0.0158, 0.0080, 0.0026
    secs = [(0.0005, inset_rrect(bw, bh, br, 0.0010, 4)), (0.0012, inset_rrect(bw, bh, br, 0.0003, 4)),
            (0.0022, rrect(bw, bh, br, 4)), (length - 0.005, rrect(bw, bh, br, 4)),
            (length - 0.0015, inset_rrect(bw, bh, br, 0.0008, 4)), (length, inset_rrect(bw, bh, br, 0.0022, 4))]
    loft(mb, fr, secs, M_BODY)
    # grip dimples on both faces
    for side in (1, -1):
        for k in range(3):
            o, x, y, z = fr
            gfr = (fpt(fr, 0, side * (bh / 2), 0.009 + k * 0.0024), x, z * side, y * side)
            g = rrect(0.0075, 0.0009, 0.00045, 2)
            loft(mb, gfr, [(-0.0001, g), (0.00018, scale2(g, 0.9, 0.7))], M_BODY, cap0=False)
    return boot(mb, fr, length - 0.0015, 0.0036, cable_r * 1.3, boot_len, cable_r, M_BODY, ribs=ribs), fr[3]


def dp_plug(mb, fr, mats, cable_r=0.003):
    """DisplayPort: asymmetric chamfered shell, chunky overmold with a latch button, ribbed boot."""
    M_SHELL, M_INS, M_BODY = mats
    w, h, ch = 0.0161, 0.0048, 0.0013
    shell = [(w / 2, h / 2), (-w / 2, h / 2), (-w / 2, -h / 2 + ch), (-w / 2 + ch, -h / 2), (w / 2, -h / 2)]
    # resample to more points for smooth shading continuity
    loft(mb, fr, [(-0.0045, shell), (0.001, shell)], M_SHELL)
    bw, bh, br = 0.0195, 0.0086, 0.0016
    length = 0.033
    secs = [(0.0006, inset_rrect(bw, bh, br, 0.0009, 3)), (0.0014, inset_rrect(bw, bh, br, 0.0002, 3)),
            (0.0024, rrect(bw, bh, br, 3)), (0.020, rrect(bw, bh, br, 3)),
            (length - 0.004, rrect(bw * 0.86, bh * 0.94, br, 3)),
            (length - 0.0012, inset_rrect(bw * 0.86, bh * 0.94, br, 0.0006, 3)),
            (length, inset_rrect(bw * 0.86, bh * 0.94, br, 0.002, 3))]
    loft(mb, fr, secs, M_BODY)
    # latch release button on top, with a recess line around it
    o, x, y, z = fr
    bfr = (fpt(fr, 0, bh / 2, 0.0095), x, z, y)  # local z = up out of the top face
    btn = rrect(0.0078, 0.0110, 0.0012, 3)
    loft(mb, bfr, [(-0.0002, btn), (0.0006, btn), (0.0009, inset_rrect(0.0078, 0.0110, 0.0012, 0.0005, 3))],
         M_INS)
    for k in range(4):
        rib = rrect(0.0060, 0.0006, 0.0003, 1)
        rfr = (fpt(fr, 0, bh / 2 + 0.0009, 0.0058 + k * 0.0022), x, z, y)
        loft(mb, rfr, [(-0.0002, rib), (0.00025, rib)], M_INS, cap0=False)
    return boot(mb, fr, length - 0.0015, 0.0044, cable_r * 1.25, 0.016, cable_r, M_BODY, ribs=5), fr[3]


def c7_plug(mb, fr, mats, cable_r=0.0028):
    """IEC C7 figure-8 connector (monitor mains): lobed body with a draft and a ribbed boot."""
    M_BODY, M_HOLE = mats
    body = fig8(0.0050, 0.0033, 44)
    face = fig8(0.0044, 0.0033, 44)
    secs = [(0.0, face), (0.0006, scale2(body, 0.97)), (0.0014, body), (0.016, body),
            (0.022, scale2(body, 0.86, 0.92)), (0.0245, scale2(body, 0.62, 0.8))]
    loft(mb, fr, secs, M_BODY)
    # grip ribs across both flat faces
    o, x, y, z = fr
    for side in (1, -1):
        for k in range(5):
            rfr = (fpt(fr, 0, side * 0.0049, 0.0065 + k * 0.0022), x, z * side, y * side)
            rib = rrect(0.0068, 0.0007, 0.00033, 1)
            loft(mb, rfr, [(-0.0003, rib), (0.00035, rib)], M_BODY, cap0=False)
    return boot(mb, fr, 0.0232, 0.0042, cable_r * 1.3, 0.014, cable_r, M_BODY, ribs=6), fr[3]


def magsafe3(mb, fr, mats, cable_r=0.0020, flank=0.0029):
    """
    MagSafe 3 head, ~18.8 x 13.2 x 4.5 mm overall (third-party measurements; Apple publishes none).
    Frame: origin on the laptop's recess floor, +z out of the port, +x along the port's long axis,
    +y = the laptop's up. `flank` = recess depth (where the head's shoulder meets the laptop side).
      nose   stadium 12.1 x 3.6 mm that seats in the 12.4 x 3.8 mm recess; black magnet face with
             five contact pads in a row
      head   stadium 13.2 x 4.5 mm aluminium shell, crisp 0.3 mm chamfered shoulder, a hairline
             split where the shell meets the dark nose insert, tapering tail
      LED    small round charge light on the top face near the laptop end
      sleeve short colour-matched strain relief into the braided cable
    """
    M_AL, M_FACE, M_LED, M_BOOT, M_PAD = mats
    W, H = 0.0132, 0.0045
    nose = lambda d: inset_rrect(0.0121, 0.0036, 0.0018 * 0.999, d, 8)
    head = lambda d, w=W, h=H: inset_rrect(w, h, h / 2 * 0.999, d, 8)
    z_face = 0.00025                      # just clear of the laptop's pins
    # magnet face + nose sides (dark insert)
    loft(mb, fr, [(z_face, nose(0.0006)), (z_face + 0.0002, nose(0.0001)), (z_face + 0.0005, nose(0.0)),
                  (flank + 0.0002, nose(0.0))], M_FACE, cap0=True, cap1=False)
    # contact pads on the face (hidden once seated, but correct if the plug is ever pulled)
    o, x, y, z = fr
    for k in range(5):
        pfr = (fpt(fr, (k - 2) * 0.0019, 0.0, z_face - 0.00003), x, y, z)
        loft(mb, pfr, [(0.0, circ(0.00045, 12)), (0.00006, circ(0.0004, 12))], M_PAD, cap0=True,
             cap1=False)
    # aluminium shell: chamfered shoulder hard against the flank, straight body, rounded tail
    z0 = flank + 0.00015
    L = 0.0150                            # shell length outside the laptop, taper included
    TAP = 0.0046                          # the rear rounds off into the cable neck
    secs = [(z0, head(0.0011)), (z0 + 0.00025, head(0.0003)), (z0 + 0.0006, head(0.0)),
            (z0 + L - TAP, head(0.0))]
    for k in range(1, 11):
        t = k / 10
        secs.append((z0 + L - TAP + TAP * t,
                     head(0.0, W * (1 - 0.43 * t ** 2.1), H * (1 - 0.10 * t * t))))
    loft(mb, fr, secs, M_AL, cap0=True, cap1=True)
    # hairline split line between shell and nose insert (a dark 0.15 mm band just behind the shoulder)
    loft(mb, fr, [(z0 + 0.0012, head(-0.00002)), (z0 + 0.00135, head(-0.00002))], M_FACE,
         cap0=False, cap1=False)
    # charge LED on the top face, 3.5 mm back from the laptop
    lfr = (fpt(fr, 0.0, H / 2 - 0.00006, z0 + 0.0035), x, -z, y)
    loft(mb, lfr, [(0.0, circ(0.00062, 16)), (0.00010, circ(0.00056, 16)), (0.00012, circ(0.0004, 16))],
         M_LED, cap0=False)
    # colour-matched sleeve: one continuous loft that leaves the tail as a flat oval, morphs to a
    # round section and tapers onto the braid (no separate collar, so no faceted step)
    NS = 36
    zt = z0 + L - 0.0006
    oval = closed_resample(rrect(0.0070, 0.0039, 0.00195 * 0.999, 8), NS)
    ring = lambda r: circ(r, NS)
    SL = 0.0115
    ssecs = []
    for k in range(13):
        t = k / 12
        m = min(1.0, t / 0.45)
        m = m * m * (3 - 2 * m)                          # oval -> round over the first 45 %
        r_ = cable_r * (1.30 - 0.22 * t ** 1.4)          # gentle taper, ends a hair proud of the braid
        c = ring(r_)
        ssecs.append((zt + SL * t, [(a[0] * (1 - m) + b[0] * m, a[1] * (1 - m) + b[1] * m)
                                    for a, b in zip(oval, c)]))
    ssecs.append((zt + SL + 0.0012, ring(cable_r * 0.98)))
    loft(mb, fr, ssecs, M_BOOT, cap0=True, cap1=False)
    return fpt(fr, 0, 0, zt + SL + 0.0008), fr[3]


def schuko_plug(mb, fr, mats, cable_r=0.0035, grip_col=0):
    """Round mains plug (CEE 7/7 style) standing in a strip socket; fluted grip, top cable exit."""
    M_BODY, = mats
    n = 48
    secs = []
    flute = [(1 + 0.022 * math.cos(12 * 2 * math.pi * i / n)) for i in range(n)]

    def ring(r, fl=False):
        return [(r * (flute[i] if fl else 1.0) * math.cos(2 * math.pi * i / n),
                 r * (flute[i] if fl else 1.0) * math.sin(2 * math.pi * i / n)) for i in range(n)]
    secs = [(-0.0135, ring(0.0178)), (0.0005, ring(0.0178)), (0.0015, ring(0.0186)),
            (0.0045, ring(0.0188)), (0.0085, ring(0.0176, True)), (0.020, ring(0.0164, True)),
            (0.028, ring(0.0150, True)), (0.0315, ring(0.0128)), (0.0335, ring(0.0092)),
            (0.0345, ring(0.0060))]
    loft(mb, fr, secs, M_BODY, cap0=True, cap1=True)
    return boot(mb, fr, 0.0335, 0.0062, cable_r * 1.3, 0.015, cable_r, M_BODY, ribs=6, n=24), fr[3]


# ----------------------------------------------------------------------------- straps


def hull2d(points):
    pts = sorted(set((round(p[0], 7), round(p[1], 7)) for p in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def closed_resample(poly2, n):
    P = [V((p[0], p[1], 0)) for p in poly2]
    P.append(P[0])
    L = sum((b - a).length for a, b in zip(P, P[1:]))
    out = []
    step = L / n
    d_target = 0.0
    acc = 0.0
    i = 0
    for k in range(n):
        d_target = k * step
        while i < len(P) - 1 and acc + (P[i + 1] - P[i]).length < d_target:
            acc += (P[i + 1] - P[i]).length
            i += 1
        seg = (P[i + 1] - P[i]).length
        t = (d_target - acc) / seg if seg > 0 else 0
        q = P[i].lerp(P[i + 1], t)
        out.append((q.x, q.y))
    return out


def wrap_strap(mb, centre, axis, xref, circles, width, thick, mat, turns=1.32, n=56, tail_lift=0.004,
               ziptie=False):
    """
    A velcro wrap (or zip tie) around a set of cable cross-sections.
    circles: [(u, v, r)] in the plane normal to `axis` (u along xref).  The strap follows the
    convex hull of the cables (so it hugs them, flattening across gaps like a real strap),
    spirals out by its own thickness for the overlap, and the loose end lifts off as a tab.
    """
    ax = V(axis).normalized()
    ux = (V(xref) - ax * V(xref).dot(ax)).normalized()
    vy = ax.cross(ux)
    pts = []
    for (u, v, r) in circles:
        for k in range(48):
            a = 2 * math.pi * k / 48
            pts.append((u + (r + thick * 0.5 + 0.0003) * math.cos(a), v + (r + thick * 0.5 + 0.0003) * math.sin(a)))
    hull = closed_resample(hull2d(pts), n)
    cu = sum(p[0] for p in hull) / n
    cv = sum(p[1] for p in hull) / n
    # start the wrap up on the +u/+v shoulder, so the overlap and the lifted tail sit on top and on
    # the far side, never between the bundle and whatever it rests on
    k0 = max(range(n), key=lambda i: (hull[i][0] - cu) + (hull[i][1] - cv))
    hull = hull[k0:] + hull[:k0]
    total = int(n * turns)
    path3 = []
    for k in range(total + 1):
        p = hull[k % n]
        f_ = min(1.0, max(0.0, (k - 0.85 * n) / (0.15 * n)))
        grow = thick * 1.05 * f_ * f_ * (3 - 2 * f_)     # first turn hugs, second layer rides on it
        dx, dy = p[0] - cu, p[1] - cv
        L = math.hypot(dx, dy)
        f = (L + grow) / L
        lift = 0.0
        if k > total - 8:
            lift = tail_lift * ((k - (total - 8)) / 8) ** 2
            f = (L + grow + lift) / L
        path3.append((cu + dx * f, cv + dy * f))
    # cross-section: a slightly rounded flat band
    hw, ht = width / 2, thick / 2
    prof = [(hw, ht * 0.6), (hw * 0.93, ht), (-hw * 0.93, ht), (-hw, ht * 0.6),
            (-hw, -ht * 0.6), (-hw * 0.93, -ht), (hw * 0.93, -ht), (hw, -ht * 0.6)]
    rings = []
    m = len(path3)
    for k in range(m):
        a = path3[k - 1] if k > 0 else path3[k]
        b = path3[k + 1] if k < m - 1 else path3[k]
        tu, tv = b[0] - a[0], b[1] - a[1]
        tl = math.hypot(tu, tv)
        tu, tv = tu / tl, tv / tl
        nu, nv = tv, -tu  # outward normal for a CCW hull
        base = V(centre) + ux * path3[k][0] + vy * path3[k][1]
        nrm = ux * nu + vy * nv
        rings.append([mb.vert(base + ax * px + nrm * py) for px, py in prof])
    for k in range(m - 1):
        for i in range(8):
            j = (i + 1) % 8
            mb.face([rings[k][i], rings[k + 1][i], rings[k + 1][j], rings[k][j]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)
    if ziptie:
        # locking head where the band closes
        p = path3[0]
        base = V(centre) + ux * p[0] + vy * p[1]
        a, b = path3[0], path3[1]
        tu, tv = b[0] - a[0], b[1] - a[1]
        tl = math.hypot(tu, tv)
        nu, nv = tv / tl, -tu / tl
        nrm = ux * nu + vy * nv
        tan = (ux * tu + vy * tv).normalized()
        hf = (base + nrm * 0.0018, tan, ax, nrm)  # frame: x=tan, y=axis, z=out
        hf = frame(base + nrm * 0.0008, nrm, tan)
        box(mb, hf, 0.0060, width + 0.0012, 0.0, 0.0038, r=0.0006, mat=mat, seg=2)
        # the cut tail stub sticking out of the head
        tf = frame(base + nrm * 0.0028 + tan * 0.003, tan, ax)
        box(mb, tf, width, thick, 0.0, 0.0045, r=0.0003, mat=mat, seg=1)


# ----------------------------------------------------------------------------- cable bundles


def pack(radii, iters=400):
    """Tight 2D packing of circles about the origin (pull in, push apart)."""
    rnd = random.Random(3)
    P = [V((rnd.uniform(-1, 1) * 0.004, rnd.uniform(-1, 1) * 0.004, 0)) for _ in radii]
    for _ in range(iters):
        for i in range(len(P)):
            P[i] *= 0.97
        for i in range(len(P)):
            for j in range(i + 1, len(P)):
                d = P[j] - P[i]
                L = d.length
                need = radii[i] + radii[j] + 0.0002
                if L < need:
                    if L < 1e-9:
                        d = V((1, 0, 0))
                        L = 1e-9
                    push = d.normalized() * (need - L) * 0.5
                    P[i] -= push
                    P[j] += push
    c = sum(P, V()) / len(P)
    return [(p - c) for p in P]


def bundle_offsets(centre_pts, radii, wraps_s, loose=0.55, twist_per_m=1.1, start_pts=None, blend_len=0.07):
    """
    For each cable, points centre + offset(s): tight at the wraps, loosening between them
    (and turning slowly), which is what a loosely strapped bundle actually does.
    Returns (per-cable point lists, per-sample frames).
    """
    base = pack(radii)
    n = len(centre_pts)
    s = [0.0]
    for a, b in zip(centre_pts, centre_pts[1:]):
        s.append(s[-1] + (b - a).length)
    out = [[] for _ in radii]
    frames = []
    T0 = (centre_pts[1] - centre_pts[0]).normalized()
    ref = V((1, 0, 0)) if abs(T0.x) < 0.9 else V((0, 1, 0))
    N = (ref - T0 * ref.dot(T0)).normalized()
    prevT = T0
    if start_pts is not None:
        # hand the packed slots out in the same side-to-side order the cables arrive in, so the
        # gathering never crosses two cables over each other
        B0 = T0.cross(N)
        c0 = centre_pts[0]
        lane_side = sorted(range(len(radii)), key=lambda c: (start_pts[c] - c0).y)
        slot_side = sorted(range(len(radii)), key=lambda k: (N * base[k].x + B0 * base[k].y).y)
        new_base = [None] * len(radii)
        for c, k in zip(lane_side, slot_side):
            new_base[c] = base[k]
        base = new_base
    for i in range(n):
        T = (centre_pts[min(i + 1, n - 1)] - centre_pts[max(i - 1, 0)]).normalized()
        axis = prevT.cross(T)
        if axis.length > 1e-9:
            N = Matrix.Rotation(prevT.angle(T, 0.0), 3, axis.normalized()) @ N
        N = (N - T * N.dot(T)).normalized()
        prevT = T
        B = T.cross(N)
        frames.append((T, N, B))
        dmin = min(abs(s[i] - w) for w in wraps_s) if wraps_s else 1.0
        spread = 1.0 + loose * min(1.0, dmin / 0.07) ** 1.5
        ang = twist_per_m * s[i]
        ca, sa = math.cos(ang), math.sin(ang)
        # near the start, ease from each cable's own lane (side by side in the tray channel) into the
        # packed bundle, so the cables gather without passing through each other
        w = 1.0
        if start_pts is not None:
            w = min(1.0, s[i] / blend_len)
            w = w * w * (3 - 2 * w)
        for c, off in enumerate(base):
            u = (off.x * ca - off.y * sa) * spread
            v = (off.x * sa + off.y * ca) * spread
            p = centre_pts[i] + N * u + B * v
            if w < 1.0:
                p = (centre_pts[i] + (start_pts[c] - centre_pts[0])).lerp(p, w)
            out[c].append(p)
    return out, frames, s, base


# ----------------------------------------------------------------------------- the build


def world_rot_z(deg):
    return Matrix.Rotation(math.radians(deg), 3, 'Z')


def build():
    reset()
    make_materials()
    scene = bpy.context.scene
    coll = bpy.data.collections.new('NEW_cables')
    scene.collection.children.link(coll)
    root = bpy.data.objects.new('NEW_cables_root', None)
    root.empty_display_size = 0.1
    coll.objects.link(root)
    objs = []

    def done(mb, sharp=38):
        ob = mb.build(coll, sharp)
        ob.parent = root
        objs.append(ob)
        return ob

    UP = V((0, 0, 1))
    TILT = 0.2967                                   # NEW_macbook_laptop rotation about X (17.0 deg)
    mb_long = V((0, math.cos(TILT), math.sin(TILT)))   # MacBook flank long axis (toward the hinge)

    # ======================================================================= 2. monitor
    DP_R = 0.0030
    PW_R = 0.0029
    mb = MB('cables_monitor_dp_plug', ['conn_metal_nickel', 'conn_insulator_black', 'conn_overmold_black'])
    fr = frame(V((0.08995, 0.9765, 1.00475)), (0, 1, 0), (1, 0, 0))
    dp_exit, dp_dir = dp_plug(mb, fr, (0, 1, 2), cable_r=DP_R)
    done(mb)

    mb = MB('cables_monitor_c7_plug', ['conn_overmold_black', 'monitor_inlet_dark'])
    pw_face = V((0.1520, 0.9855, 1.0040))
    fr = frame(pw_face + V((0, 0.0015, 0)), (0, 1, 0), (1, 0, 0))
    pw_exit, pw_dir = c7_plug(mb, fr, (0, 1), cable_r=PW_R)
    # the inlet surround the plug sits in (the monitor model has no mains inlet of its own)
    ifr = frame(pw_face, (0, 1, 0), (1, 0, 0))
    outer = fig8(0.0064, 0.0034, 44)
    loft(mb, ifr, [(-0.0004, outer), (0.0011, outer), (0.0015, scale2(outer, 0.96))], 1)
    done(mb)

    # the two monitor cables fall behind the panel, meet under it and are strapped together
    pair_y = 1.066
    dp_hang = [dp_exit, dp_exit + dp_dir * 0.006, V((0.0900, 1.0440, 1.0010)), V((0.0898, 1.0555, 0.9900)),
               V((0.0893, 1.0625, 0.9700)), V((0.0885, pair_y, 0.9400)), V((0.0880, pair_y, 0.9000))]
    pw_hang = [pw_exit, pw_exit + pw_dir * 0.006, V((0.1515, 1.0470, 1.0000)), V((0.1480, 1.0570, 0.9880)),
               V((0.1380, 1.0630, 0.9680)), V((0.1150, pair_y, 0.9420)), V((0.0995, pair_y, 0.9150)),
               V((0.0945, pair_y, 0.9000))]
    # together down to the desk
    dz = DESK
    dp_down = [V((0.0880, pair_y, 0.8600)), V((0.0878, pair_y + 0.001, 0.8000)), V((0.0872, pair_y + 0.004, 0.7650)),
               V((0.0850, pair_y + 0.014, dz + DP_R + 0.004)), V((0.0800, 1.095, dz + DP_R)),
               V((0.0735, 1.108, dz + DP_R)), V((0.0712, 1.118, dz + DP_R))]
    pw_down = [V((0.0940, pair_y, 0.8600)), V((0.0940, pair_y + 0.001, 0.8000)), V((0.0938, pair_y + 0.004, 0.7650)),
               V((0.0925, pair_y + 0.016, dz + PW_R + 0.004)), V((0.0880, 1.097, dz + PW_R)),
               V((0.0805, 1.109, dz + PW_R)), V((0.0778, 1.118, dz + PW_R))]

    # strap on the hanging pair, where it shows under the monitor from the chair
    mb = MB('cables_velcro_monitor', ['velcro_black'])
    wrap_strap(mb, V((0.0910, pair_y, 0.875)), (0, 0, -1), (1, 0, 0),
               [(-0.0030, 0.0, DP_R), (0.0030, 0.0, PW_R)], 0.012, 0.0011, 0, turns=1.3)
    done(mb)

    # ======================================================================= 4. MacBook charge (braided)
    MC_R = 0.0021
    mb = MB('cables_macbook_magsafe_plug', ['magsafe_aluminium', 'magsafe_face_black', 'magsafe_led_amber',
                                             'magsafe_sleeve_silver', 'magsafe_pad_gold'])
    # NEW_macbook: recess floor (contacts) at x -0.2034, flank x -0.2063 (2.9 mm deep); the plug's
    # +y is the laptop's up (0, -sin, cos) because the laptop is tilted 17 deg on its riser
    mcp = V((-0.2034, 0.78688, 0.81822))
    fr = frame(mcp, (-1, 0, 0), -mb_long)
    mc_exit, mc_dir = magsafe3(mb, fr, (0, 1, 2, 3, 4), cable_r=MC_R, flank=0.0029)
    done(mb)
    mz = DESK + MC_R
    # the braid leaves the sleeve level, then rolls over under its own weight on a ~30 mm bend
    # radius (a braided MagSafe cable is fairly stiff), falls almost vertically past the riser, and
    # lands on the desk on a second ~30 mm bend already turning toward the back edge
    mc_desk = [mc_exit, mc_exit + mc_dir * 0.004, mc_exit + mc_dir * 0.009 + V((0, 0.0002, -0.0005)),
               V((-0.2505, 0.7874, 0.8150)), V((-0.2590, 0.7884, 0.8060)), V((-0.2650, 0.7898, 0.7930)),
               V((-0.2690, 0.7918, 0.7780)), V((-0.2716, 0.7948, 0.7620)), V((-0.2736, 0.7998, 0.7482)),
               V((-0.2750, 0.8080, 0.7396)), V((-0.2755, 0.8200, mz)),
               V((-0.2740, 0.8600, mz)), V((-0.2660, 0.9200, mz)), V((-0.2560, 0.9800, mz)),
               V((-0.2470, 1.0400, mz)), V((-0.2420, 1.1000, mz)), V((-0.2400, 1.1180, mz))]

    # ======================================================================= 5. over the back edge, tray channel
    WALL_IN, WALL_OUT = 1.0910, 1.0990          # tray back wall faces (y), top at WALL_TOP

    def over_edge(x, r, y_in, z_in):
        """Wrap the rounded desk edge, hang, tuck under, drape over the tray's back wall (hugging
        both of its top corners) and drop down its inner face into the channel lane."""
        pts = [V((x, 1.1245, DESK + r)), V((x, EDGE_Y + r * 0.72, DESK + r * 0.72 - 0.0010)),
               V((x, EDGE_Y + r + 0.0003, 0.7200)), V((x, EDGE_Y + r + 0.0002, 0.7040)),
               V((x, 1.1260, 0.6905)), V((x, 1.1140, 0.6810))]
        rr = r + 0.0004
        for deg in (60, 30, 0):                   # over the outer corner
            a_ = math.radians(deg)
            pts.append(V((x, WALL_OUT + rr * math.sin(a_), WALL_TOP + rr * math.cos(a_))))
        for deg in (30, 60, 90):                  # and down round the inner corner
            a_ = math.radians(deg)
            pts.append(V((x, WALL_IN - rr * math.sin(a_), WALL_TOP + rr * math.cos(a_))))
        yv = min(WALL_IN - rr, y_in + 0.0035)
        pts += [V((x, yv, 0.6450)), V((x, (yv + y_in) / 2, z_in + 0.006)), V((x, y_in, z_in + 0.0015)),
                V((x + 0.006, y_in, z_in))]
        return pts

    CH = {'mc': (1.0712, TRAY_FLOOR + MC_R), 'dp': (1.0770, TRAY_FLOOR + DP_R),
          'pw': (1.0842, TRAY_FLOOR + PW_R)}
    X_EXIT = 0.395

    def channel_run(key, x0, x1):
        y, z = CH[key]
        pts = []
        n = max(2, int(abs(x1 - x0) / 0.08))
        for i in range(1, n + 1):
            t = i / n
            pts.append(V((x0 + (x1 - x0) * t, y + 0.0006 * math.sin(t * 9 + len(key)), z)))
        return pts

    dp_path1 = dp_hang + dp_down + over_edge(0.0712, DP_R, *CH['dp']) + channel_run('dp', 0.0712, X_EXIT - 0.03)
    pw_path1 = pw_hang + pw_down + over_edge(0.0778, PW_R, *CH['pw']) + channel_run('pw', 0.0778, X_EXIT - 0.03)
    mc_path1 = mc_desk + over_edge(-0.2398, MC_R, *CH['mc']) + channel_run('mc', -0.2398, X_EXIT - 0.03)

    # ======================================================================= 6. the drop to the floor
    # bundle centreline: out of the channel over the tray's back wall, then hanging behind it
    Xb = X_EXIT
    centre = [V((Xb - 0.012, 1.0760, 0.6250)), V((Xb - 0.002, 1.0800, 0.6450)), V((Xb + 0.003, 1.0835, 0.6640)),
              V((Xb + 0.006, 1.0890, 0.6745)), V((Xb + 0.009, 1.0950, 0.6770)), V((Xb + 0.012, 1.1020, 0.6745)),
              V((Xb + 0.014, 1.1080, 0.6650)), V((Xb + 0.015, 1.1160, 0.6450)), V((Xb + 0.015, 1.1240, 0.6100)),
              V((Xb + 0.014, 1.1270, 0.5500)), V((Xb + 0.013, 1.1275, 0.5000)), V((Xb + 0.010, 1.1285, 0.4000)),
              V((Xb + 0.008, 1.1300, 0.3000)), V((Xb + 0.009, 1.1320, 0.2000)), V((Xb + 0.013, 1.1340, 0.1200)),
              V((Xb + 0.019, 1.1370, 0.0650))]
    cdense = resample(catmull(centre, 30), 0.004)
    radii = [MC_R, DP_R, PW_R]
    names = ['mc', 'dp', 'pw']
    cl = [0.0]
    for a, b in zip(cdense, cdense[1:]):
        cl.append(cl[-1] + (b - a).length)
    # wraps: a zip tie just past the tray wall, velcro every ~15 cm down the drop
    def s_at_z(z):
        for i in range(1, len(cdense)):
            if cdense[i].z <= z and cdense[i].y > 1.12:
                return cl[i], i
        return cl[-1], len(cdense) - 1
    wraps = [s_at_z(0.585), s_at_z(0.430), s_at_z(0.275)]
    crest = max(range(len(cdense)), key=lambda i: cdense[i].z)      # held tight where it rides the wall
    lanes = [V((cdense[0].x, CH[k][0], CH[k][1])) for k in names]
    per, frames_, sl, base_off = bundle_offsets(cdense, radii, [w[0] for w in wraps] + [cl[crest]], loose=0.6,
                                                twist_per_m=1.6, start_pts=lanes, blend_len=0.06)
    # strap geometry at each wrap
    mb = MB('cables_bundle_wraps', ['velcro_black', 'ziptie_nylon_black'])
    for k, (sv, idx) in enumerate(wraps):
        T, N, B = frames_[idx]
        ang = 1.6 * sl[idx]
        ca, sa = math.cos(ang), math.sin(ang)
        circles = []
        for off, rr in zip(base_off, radii):
            u = off.x * ca - off.y * sa
            v = off.x * sa + off.y * ca
            circles.append((u, v, rr))
        if k == 0:
            wrap_strap(mb, cdense[idx], T, N, circles, 0.0036, 0.0012, 1, turns=1.0, ziptie=True)
        else:
            wrap_strap(mb, cdense[idx], T, N, circles, 0.0125, 0.0011, 0, turns=1.34)
    done(mb)

    # channel -> bundle entry: each cable leaves its channel lane toward its bundle track
    def bundle_track(c):
        # keep the part of the track after the cable has left the channel lane
        return [p for i, p in enumerate(per[c]) if i % 3 == 0 and cl[i] > 0.012]

    # ======================================================================= 7. floor: strip, brick
    # power strip lying against the skirting, sockets up; the floor end of every cable is here
    SX0, SX1, SY, SH = 0.160, 0.440, 1.2350, 0.038
    sock_x = [0.2050, 0.2600, 0.3150]
    usb_x = [0.3560, 0.3790]
    mb = MB('cables_power_strip', ['strip_white_abs', 'strip_recess_grey', 'strip_hole_black',
                                   'strip_rocker_red', 'conn_metal_nickel', 'conn_insulator_blue'])
    L_, W_ = SX1 - SX0, 0.055
    sfr = frame(V(((SX0 + SX1) / 2, SY, 0.0)), (0, 0, 1), (1, 0, 0))
    secs = [(0.0, inset_rrect(L_, W_, 0.010, 0.0016, 6)), (0.0012, inset_rrect(L_, W_, 0.010, 0.0003, 6)),
            (0.0028, rrect(L_, W_, 0.010, 6)), (SH - 0.0035, rrect(L_, W_, 0.010, 6)),
            (SH - 0.0012, inset_rrect(L_, W_, 0.010, 0.0010, 6)), (SH, inset_rrect(L_, W_, 0.010, 0.0030, 6))]
    loft(mb, sfr, secs, 0)
    done_strip = done(mb, 40)
    # sockets: round recesses cut into the top, USB-A ports into the front face
    cutters = []
    for x in sock_x:
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=0.0195, depth=0.030,
                                            location=(x, SY, SH - 0.0155 + 0.015))
        cutters.append(bpy.context.active_object)
    for x in usb_x:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, SY - W_ / 2, 0.0190))
        c = bpy.context.active_object
        c.scale = (0.0134, 0.026, 0.0058)
        cutters.append(c)
    for c in cutters:
        mod = done_strip.modifiers.new('cut', 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = c
        mod.solver = 'EXACT'
    bpy.context.view_layer.objects.active = done_strip
    for mod in list(done_strip.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for c in cutters:
        bpy.data.objects.remove(c, do_unlink=True)
    # recess faces get the grey insert material
    me = done_strip.data
    for p in me.polygons:
        c = p.center
        inside_sock = any(math.hypot(c.x - x, c.y - SY) < 0.0197 for x in sock_x) and c.z < SH - 0.0004
        inside_usb = any(abs(c.x - x) < 0.0068 for x in usb_x) and c.y > SY - W_ / 2 + 0.0003 and c.z < 0.0225
        if inside_sock or inside_usb:
            p.material_index = 1
    me.set_sharp_from_angle(angle=math.radians(40))

    mb = MB('cables_power_strip_details', ['strip_hole_black', 'conn_metal_nickel', 'strip_rocker_red',
                                           'strip_white_abs', 'conn_insulator_blue', 'strip_recess_grey'])
    floor_z = SH - 0.0150
    for x in sock_x:
        # pin holes and the two side earth clips of each socket
        for dx in (-0.0095, 0.0095):
            h = circ(0.0024, 16)
            hf = frame(V((x + dx, SY, floor_z)), (0, 0, 1), (1, 0, 0))
            loft(mb, hf, [(0.0, h), (0.0002, h)], 0, cap0=False)
        for sy in (-1, 1):
            cf = frame(V((x, SY + sy * 0.0190, floor_z + 0.0075)), (0, -sy, 0), (1, 0, 0))
            box(mb, cf, 0.0060, 0.0120, 0.0, 0.0008, r=0.0003, mat=1)
    # rocker switch: bezel + tilted red rocker
    swf = frame(V((0.4150, SY, SH - 0.0006)), (0, 0, 1), (1, 0, 0))
    loft(mb, swf, [(0.0, rrect(0.024, 0.017, 0.003, 3)), (0.0016, rrect(0.024, 0.017, 0.003, 3)),
                   (0.0019, rrect(0.022, 0.015, 0.0025, 3))], 3)
    rk = Matrix.Rotation(math.radians(8), 3, 'Y')
    rfr = (V((0.4150, SY, SH + 0.0022)), rk @ V((1, 0, 0)), rk @ V((0, 1, 0)), rk @ V((0, 0, 1)))
    loft(mb, rfr, [(-0.002, rrect(0.0195, 0.0125, 0.002, 3)), (0.0015, rrect(0.0195, 0.0125, 0.002, 3)),
                   (0.0022, rrect(0.0185, 0.0115, 0.0016, 3))], 2)
    # USB-A receptacles: nickel frame + blue tongue
    for x in usb_x:
        ufr = frame(V((x, SY - W_ / 2 + 0.0004, 0.0190)), (0, -1, 0), (1, 0, 0))
        outer = rrect(0.0132, 0.0056, 0.0003, 1)
        inner = rrect(0.0122, 0.0046, 0.0002, 1)
        loft(mb, ufr, [(-0.0100, inner), (0.0, inner), (0.0, outer), (-0.0005, outer)], 1, cap0=True, cap1=False)
        tg = shift2(rrect(0.0108, 0.0018, 0.0002, 1), 0, 0.0010)
        loft(mb, ufr, [(-0.0100, tg), (-0.0015, tg)], 4)
    # cord exit collar at the +x end
    cfr = frame(V((SX1 - 0.002, SY, 0.0190)), (1, 0, 0), (0, 1, 0))
    loft(mb, cfr, [(0.0, circ(0.0065, 20)), (0.0045, circ(0.0065, 20)), (0.0060, circ(0.0058, 20))], 3)
    strip_exit = boot(mb, cfr, 0.0055, 0.0056, 0.0042, 0.016, 0.0034, 3, ribs=5)
    done(mb)

    # Apple-style 96 W USB-C brick (80 x 80 x 29 mm), on the floor beside the strip
    BR_C = V((0.0720, 1.1920, 0.0))
    BR_DEG = -7.0
    br_rot = world_rot_z(BR_DEG)
    bx, by = br_rot @ V((1, 0, 0)), br_rot @ V((0, 1, 0))
    W, H, R, RE = 0.080, 0.029, 0.0120, 0.0034       # plan size, height, plan corner radius, edge radius
    SEAM_Z = H - 0.0078                              # parting line between the top shell and the body
    PORT_Z = 0.0140
    bfr = (BR_C, bx, by, V((0, 0, 1)))
    PSEG = 12
    prof = lambda d: inset_rrect(W, W, R, d, PSEG)
    secs = []
    # bottom: flat inner ring, then a quarter-round edge in 7 steps
    secs.append((0.0, prof(RE + 0.004)))
    for k in range(8):
        a_ = math.radians(90 * k / 7)
        secs.append((RE * (1 - math.cos(a_)), prof(RE * (1 - math.sin(a_)))))
    # side wall with the parting seam: a crisp 0.45 mm groove, 0.3 mm deep, with softened lips
    secs += [(SEAM_Z - 0.00045, prof(0.0)), (SEAM_Z - 0.00022, prof(0.00008)), (SEAM_Z - 0.00016, prof(0.0003)),
             (SEAM_Z + 0.00016, prof(0.0003)), (SEAM_Z + 0.00022, prof(0.00008)), (SEAM_Z + 0.00045, prof(0.0))]
    for k in range(8):
        a_ = math.radians(90 * k / 7)
        secs.append((H - RE + RE * math.sin(a_), prof(RE * (1 - math.cos(a_)))))
    secs.append((H, prof(RE + 0.004)))
    mb = MB('cables_power_brick', ['brick_white_pc', 'brick_seam', 'brick_port_dark'])
    loft(mb, bfr, secs, 0)
    nring = len(secs[0][1])
    seam_first = 1 + 8        # index of the first seam section
    for fi in range(nring * (seam_first + 1), nring * (seam_first + 4)):
        mb.mi[fi] = 1
    brick = done(mb, 50)
    # USB-C receptacle in the +x face: stadium opening 8.6 x 3.0 mm, 7 mm deep, cut with a real
    # stadium cutter so the plug fills it with only a hairline of dark gap around its shell
    port_c = BR_C + bx * (W / 2) + V((0, 0, PORT_Z))
    cmb = MB('tmp_port_cut', ['brick_port_dark'])
    cfr_ = frame(port_c + bx * 0.002, -bx, by)
    loft(cmb, cfr_, [(0.0, rrect(0.0086, 0.0030, 0.0015 * 0.999, 6)), (0.009, rrect(0.0086, 0.0030, 0.0015 * 0.999, 6))], 0)
    cut = cmb.build(bpy.context.scene.collection)
    mod = brick.modifiers.new('port', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cut
    mod.solver = 'EXACT'
    bpy.context.view_layer.objects.active = brick
    bpy.ops.object.modifier_apply(modifier='port')
    bpy.data.objects.remove(cut, do_unlink=True)
    for p in brick.data.polygons:
        rel = p.center - port_c
        if abs(rel.dot(bx)) > 0.00005 and rel.dot(bx) < 0 and abs(rel.dot(by)) < 0.0046 and abs(rel.z) < 0.0017:
            p.material_index = 2
    brick.data.set_sharp_from_angle(angle=math.radians(50))
    wn = brick.modifiers.new('wn', 'WEIGHTED_NORMAL')
    wn.keep_sharp = True

    mb = MB('cables_power_brick_details', ['conn_metal_nickel', 'brick_port_dark', 'brick_seam'])
    # receptacle interior: thin nickel shell lining and a dark back wall (the plug's own solid shell
    # fills the rest, so no tongue is modelled)
    rfr = frame(port_c, bx, by)
    shell_o = rrect(0.0086, 0.0030, 0.0015 * 0.999, 6)
    shell_i = rrect(0.0084, 0.0028, 0.0014 * 0.999, 6)
    loft(mb, rfr, [(-0.0068, shell_i), (-0.00035, shell_i), (-0.00035, shell_o), (-0.0068, shell_o)], 0,
         cap0=False, cap1=False)
    loft(mb, rfr, [(-0.0070, shell_o), (-0.0068, shell_o)], 1)
    done(mb)

    # USB-C plug of the MacBook cable into the brick (overmould colour-matched to the MagSafe sleeve)
    mb = MB('cables_brick_usbc_plug', ['conn_metal_nickel', 'conn_insulator_black', 'magsafe_sleeve_silver'])
    fr = frame(port_c, bx, by)
    brick_plug_exit, brick_plug_dir = usb_c(mb, fr, (0, 1, 2), cable_r=MC_R, show_mouth=False,
                                            length=0.0165, boot_len=0.013, body_w=0.0124, body_h=0.0062)
    done(mb)

    # AC extension-cord head slid onto the -x face: soft-radius block with a hairline where it meets
    # the brick, a moulded grip step, round cord exit
    mb = MB('cables_brick_ac_head', ['brick_white_pc', 'brick_seam'])
    ac_face = BR_C - bx * (W / 2) + V((0, 0, 0.0150))
    afr = frame(ac_face, -bx, by)
    HW, HH, HR = 0.050, 0.0255, 0.0070
    head = lambda d: inset_rrect(HW, HH, HR, d, 8)
    hs = [(-0.0002, head(0.0009)), (0.0002, head(0.0005)), (0.00045, head(0.00055)),     # hairline gap
          (0.0008, head(0.0001)), (0.0012, head(0.0))]
    for k in range(1, 7):                                  # rounded outer edge
        a_ = math.radians(90 * k / 6)
        hs.append((0.0132 + 0.0030 * math.sin(a_), head(0.0030 * (1 - math.cos(a_)))))
    # face the cord leaves from: flat inset rings then a boss
    hs += [(0.0162, head(0.0055)), (0.0162, head(0.0085))]
    loft(mb, afr, hs, 0)
    nh = len(head(0.0))
    for fi in range(nh * 1, nh * 3):
        mb.mi[fi] = 1
    # cord boss + strain relief
    loft(mb, afr, [(0.0160, circ(0.0066, 24)), (0.0172, circ(0.0066, 24)), (0.0178, circ(0.0061, 24))], 0,
         cap0=False, cap1=False)
    ac_exit = boot(mb, afr, 0.0176, 0.0060, 0.0035, 0.015, 0.0028, 0, ribs=0, n=24)
    done(mb)
    AC_R = 0.0028

    # mains plugs standing in the strip: monitor (black) in socket 3, brick (white) in socket 1
    mb = MB('cables_mains_plug_monitor', ['conn_overmold_black'])
    pfr = frame(V((sock_x[2], SY, SH)), (0, 0, 1), (1, 0, 0))
    mp_exit, mp_dir = schuko_plug(mb, pfr, (0,), cable_r=PW_R)
    done(mb)
    mb = MB('cables_mains_plug_brick', ['conn_overmold_white'])
    pfr = frame(V((sock_x[0], SY, SH)), (0, 0, 1), (1, 0, 0))
    bp_exit, bp_dir = schuko_plug(mb, pfr, (0,), cable_r=AC_R)
    done(mb)
    # floor runs from the bundle foot to each destination
    foot = cdense[-1]
    fz = lambda r: r

    def tail_from_bundle(c, pts):
        return pts

    # below the last strap the three split: the MacBook cable stays in front and runs left along the
    # floor to the brick, the DP cable goes right along the skirting, the monitor's mains cord peels
    # off higher up and drapes down into its plug in the strip
    mc_floor = [V((0.4150, 1.1331, 0.0330)), V((0.4070, 1.1334, 0.0090)), V((0.3880, 1.1340, fz(MC_R))),
                V((0.3400, 1.1400, fz(MC_R))), V((0.2800, 1.1500, fz(MC_R))), V((0.2200, 1.1620, fz(MC_R))),
                V((0.1800, 1.1740, fz(MC_R) + 0.0003)),
                V((0.1620, 1.1785, 0.0065)), brick_plug_exit + brick_plug_dir * 0.009 + V((0, 0, -0.0012)),
                brick_plug_exit + brick_plug_dir * 0.004, brick_plug_exit]
    dp_floor = [V((0.4185, 1.1420, 0.0330)), V((0.4260, 1.1430, 0.0100)), V((0.4420, 1.1450, fz(DP_R))),
                V((0.4700, 1.1520, fz(DP_R))), V((0.4900, 1.1680, fz(DP_R))), V((0.5100, 1.2000, fz(DP_R))),
                V((0.5400, 1.2450, fz(DP_R))), V((0.5800, 1.2610, fz(DP_R))),
                V((0.6800, 1.2640, fz(DP_R))), V((0.8000, 1.2650, fz(DP_R))), V((0.9200, 1.2660, fz(DP_R))),
                V((1.0200, 1.2660, fz(DP_R)))]
    pw_floor = [V((0.3920, 1.1350, 0.1760)), V((0.3730, 1.1530, 0.1500)), V((0.3490, 1.1800, 0.1310)),
                V((0.3310, 1.2070, 0.1180)), V((0.3190, 1.2290, 0.1080)),
                mp_exit + mp_dir * 0.010, mp_exit]

    # assemble every cable path: desk/channel part + bundle track + floor tail
    tracks = {n_: per[i] for i, n_ in enumerate(names)}

    def join(first, name, last, zmin=-1.0):
        tr = tracks[name]
        # skip bundle samples too close to the channel end so the handover is smooth; a cable that
        # leaves the bundle early stops following it below zmin
        tr = [p for p in tr[::3]]
        tr = [p for i, p in enumerate(tr) if i >= 2 and not (p.z < zmin and p.y > 1.12)]
        return first + tr + last

    dp_all = join(dp_path1, 'dp', dp_floor)
    pw_all = join(pw_path1, 'pw', pw_floor, zmin=0.20)
    mc_all = join(mc_path1, 'mc', mc_floor)

    # brick AC cord: head (-x face) around the back of the brick to the white mains plug
    ac_ctrl = [ac_exit, ac_exit - bx * 0.006, ac_exit - bx * 0.016 + V((0, 0, -0.008)),
               V((0.0140, 1.2140, AC_R + 0.0005)), V((0.0150, 1.2400, AC_R)), V((0.0400, 1.2580, AC_R)),
               V((0.1000, 1.2620, AC_R)), V((0.1500, 1.2700, AC_R)), V((0.1780, 1.2760, 0.0100)),
               V((0.1960, 1.2700, 0.0520)), V((0.2030, 1.2480, 0.0780)), bp_exit + bp_dir * 0.010, bp_exit]
    # strip's own cord: out of the +x end, along the skirting, away under the curtain
    st_ctrl = [strip_exit, strip_exit + V((0.006, 0, 0)), V((0.4750, 1.2380, 0.0060)),
               V((0.5100, 1.2600, 0.0034)), V((0.5500, 1.2750, 0.0034)), V((0.6800, 1.2760, 0.0034)),
               V((0.8200, 1.2765, 0.0034)), V((0.9400, 1.2770, 0.0034)), V((1.0300, 1.2770, 0.0034))]

    # ======================================================================= 8. coil on the desk
    # A hand-coiled USB cable: three turns spiralling inward on the desk, a climb, then two and a
    # bit turns spiralling back out on top, resting in the grooves of the bottom layer. Adjacent
    # turns stay exactly one diameter apart everywhere (a spiral, not stacked circles), so nothing
    # interpenetrates. The whole ring is a little oval and lumpy (identically for every turn), and
    # sits up on the velcro strap where the strap passes under it.
    COIL_R = 0.0020
    coil_c = V((0.8870, 0.6640, 0.0))
    Rc = 0.0415
    d = 2 * COIL_R + 0.00025
    phi0 = math.radians(-35)
    TH_CLIMB = 6 * math.pi
    TH_END = 10.5 * math.pi
    phi_t = phi0 + math.radians(200)          # where the velcro strap sits
    STRAP_T = 0.0011

    def wob(phi):
        return 1 + 0.07 * math.cos(2 * (phi - 0.6)) + 0.025 * math.sin(3 * phi + 1.0)

    def lift(phi):
        a = math.atan2(math.sin(phi - phi_t), math.cos(phi - phi_t))
        return STRAP_T * math.exp(-(a / 0.20) ** 2)

    def coil_off(th):
        bot = (3 * d - d * th / (2 * math.pi), 0.0)
        top = (0.5 * d + d * (th - TH_CLIMB) / (2 * math.pi), d)
        w = 0.40
        if th <= TH_CLIMB - w:
            return bot
        if th >= TH_CLIMB + w:
            return top
        f = (th - (TH_CLIMB - w)) / (2 * w)
        fr_ = f * f * (3 - 2 * f)
        fh = min(1.0, f * 1.6)
        fh = fh * fh * (3 - 2 * fh)
        b0 = (3 * d - d * (TH_CLIMB - w) / (2 * math.pi), 0.0)
        t1 = (0.5 * d + d * w / (2 * math.pi), d)
        return (b0[0] + (t1[0] - b0[0]) * fr_, d * fh)

    def coil_point(th):
        phi = phi0 + th
        off, h = coil_off(th)
        rr = Rc * wob(phi) + off
        return V((coil_c.x + rr * math.cos(phi), coil_c.y + rr * math.sin(phi), DESK + COIL_R + h + lift(phi)))

    nsteps = int(TH_END / math.radians(2.0))
    coil_pts = [coil_point(TH_END * i / nsteps) for i in range(nsteps + 1)]
    cz = DESK + COIL_R
    p0 = coil_pts[0]
    t0 = (coil_pts[1] - coil_pts[0]).normalized()
    n0 = V((math.cos(phi0), math.sin(phi0), 0))
    pe = coil_pts[-1]
    te = (coil_pts[-1] - coil_pts[-2])
    te.z = 0
    te.normalize()
    ne = V((math.cos(phi0 + TH_END), math.sin(phi0 + TH_END), 0))

    # USB-C end: lies on the desk a few cm back along the start tail, nose pointing away
    uC = (-t0 + n0 * 0.45)
    uC.z = 0
    uC.normalize()
    EC = p0 - t0 * 0.040 + n0 * 0.011
    mb = MB('cables_coil_usbc_plug', ['conn_metal_nickel', 'conn_insulator_black', 'conn_overmold_black'])
    faceC = EC + uC * 0.0305
    frC = frame(V((faceC.x, faceC.y, DESK + 0.0032)), -uC, V((0, 0, 1)).cross(-uC))
    cC_exit, cC_dir = usb_c(mb, frC, (0, 1, 2), cable_r=COIL_R, show_mouth=True, length=0.0170,
                            boot_len=0.012, ribs=4)
    done(mb)
    # USB-A end: continues off the top layer, steps down outside the ring
    uA = (te + ne * 0.55)
    uA.normalize()
    EA = pe + te * 0.040 + ne * 0.022
    mb = MB('cables_coil_usba_plug', ['conn_metal_nickel', 'conn_insulator_blue', 'conn_overmold_black'])
    faceA = EA + uA * 0.0335
    frA = frame(V((faceA.x, faceA.y, DESK + 0.0040)), -uA, V((0, 0, 1)).cross(-uA))
    cA_exit, cA_dir = usb_a(mb, frA, (0, 1, 2), cable_r=COIL_R, ribs=4)
    done(mb)
    tailC = [cC_exit, cC_exit + cC_dir * 0.005, cC_exit + cC_dir * 0.012 + V((0, 0, -0.0011)),
             p0 - t0 * 0.022 + n0 * 0.004, p0 - t0 * 0.010 + n0 * 0.0008]
    tailA = [pe + te * 0.007 + ne * 0.0015, pe + te * 0.016 + ne * 0.006 + V((0, 0, -0.0022)),
             pe + te * 0.026 + ne * 0.013 + V((0, 0, -d)), cA_exit + cA_dir * 0.012 + V((0, 0, -0.0015)),
             cA_exit + cA_dir * 0.005, cA_exit]
    tailA[2].z = max(tailA[2].z, cz)
    tailA[3].z = max(tailA[3].z, cz)

    # the velcro rip-tie around the ring cross-section
    circles = []
    for k in range(6):
        th = ((phi_t - phi0) % (2 * math.pi)) + 2 * math.pi * k
        if th > TH_END:
            break
        off, h = coil_off(th)
        circles.append((off, h + COIL_R, COIL_R))
    ring_r = Rc * wob(phi_t)
    ring_c = V((coil_c.x + ring_r * math.cos(phi_t), coil_c.y + ring_r * math.sin(phi_t), DESK + STRAP_T))
    tang = V((-math.sin(phi_t), math.cos(phi_t), 0))
    radial = V((math.cos(phi_t), math.sin(phi_t), 0))
    mb = MB('cables_coil_velcro', ['velcro_black'])
    wrap_strap(mb, ring_c, -tang, radial, circles, 0.0135, STRAP_T, 0, turns=1.38, tail_lift=0.006)
    done(mb)


    # ======================================================================= 9. sweep all tubes
    tubes = [
        ('cables_monitor_dp_cable', dp_all, DP_R, 16, 'cbl_pvc_black_satin'),
        ('cables_monitor_power_cable', pw_all, PW_R, 16, 'cbl_pvc_black_matte'),
        ('cables_macbook_charge_cable', mc_all, MC_R, 16, 'cbl_braid_white'),
        ('cables_brick_ac_cord', ac_ctrl, AC_R, 14, 'cbl_pvc_white'),
        ('cables_strip_cord', st_ctrl, 0.0034, 14, 'cbl_pvc_black_matte'),
    ]
    for name, ctrl, r, sides, mat in tubes:
        mb = MB(name, [mat])
        pts = path(ctrl, r, max_len=0.03, max_deg=6.0)
        tube(mb, pts, r, sides, 0, cap0=True, cap1=True)
        done(mb, 80)
    # coil: the ring itself is already dense; tails through the same smoother
    mb = MB('cables_coil_cable', ['cbl_pvc_black_matte'])
    coil_all = tailC + coil_pts[1:-1] + tailA
    pts = path(coil_all, COIL_R, max_len=0.02, max_deg=7.5, clamp=False)
    tube(mb, pts, COIL_R, 12, 0)
    done(mb, 80)

    total = sum(tris(o) for o in objs)
    print('\n=== NEW_cables objects ===')
    for o in objs:
        print(f'  {o.name:34s} {tris(o):6d} tris')
    print(f'TOTAL {total} tris in {len(objs)} objects')

    os.makedirs(OUT_DIR, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
    print('SAVED', OUT)


# ----------------------------------------------------------------------------- previews
#
#   "<blender.exe>" -b blender/scene/room.blend --python blender/scripts/v2_cables.py -- preview [view ...]
#
# Opens room.blend read-only (never saved), appends NEW_cables, hides what it replaces and the room's
# own lights, and renders each view with a camera-relative 3-point rig under a neutral grey world.

REPLACES = ['monitor_cable', 'Mesh_31', 'cable_coil', 'cable_tie', 'cable_boot', 'cable_plug', 'Mesh_17']

VIEWS = {
    # name: (camera, target, lens)
    'seat_rear': ((-0.12, 0.60, 0.99), (0.0, 1.12, 0.73), 22),
    'under':     ((0.20, 0.52, 0.30), (0.24, 1.20, 0.22), 18),
    'brick':     ((0.200, 1.075, 0.105), (0.082, 1.188, 0.012), 38),
    'magsafe':   ((-0.262, 0.728, 0.852), (-0.2175, 0.7875, 0.8155), 58),
    'coil':      ((0.800, 0.520, 0.880), (0.875, 0.650, 0.738), 42),
    'monitor':   ((0.34, 1.26, 1.02), (0.10, 1.02, 0.86), 26),
    'seat':      ((0.0, -0.16, 1.175), (0.0, 1.0, 0.85), 30),
    'io':        ((0.175, 1.175, 1.075), (0.105, 0.985, 0.995), 40),
    'magsafe_side': ((-0.36, 0.66, 0.86), (-0.245, 0.80, 0.785), 38),
    'magsafe_top':  ((-0.228, 0.772, 0.868), (-0.2140, 0.7872, 0.8175), 70),
    'drop':      ((0.50, 1.27, 0.66), (0.39, 1.10, 0.58), 30),
}


def preview(names):
    import bpy
    sc = bpy.context.scene
    for n in REPLACES:
        o = bpy.data.objects.get(n)
        if o:
            o.hide_render = True
    for o in bpy.data.objects:
        if o.type == 'LIGHT':
            o.hide_render = True
    with bpy.data.libraries.load(OUT, link=False) as (src, dst):
        dst.collections = ['NEW_cables']
    sc.collection.children.link(dst.collections[0])
    w = bpy.data.worlds.new('grey')
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.5, 0.5, 0.5, 1)
    bg.inputs[1].default_value = 0.6
    sc.world = w
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    sc.cycles.device = 'GPU'
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPTIX'
    except TypeError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1280, 800
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else sc.view_settings.view_transform
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    sc.collection.objects.link(cam)
    cam.data.clip_start = 0.004
    sc.camera = cam
    rig = []
    for nm, energy, size in (('key', 1.0, 0.5), ('fill', 0.35, 0.8), ('rim', 0.8, 0.4)):
        ld = bpy.data.lights.new('prev_' + nm, 'AREA')
        ld.size = size
        lo = bpy.data.objects.new('prev_' + nm, ld)
        sc.collection.objects.link(lo)
        rig.append((lo, energy))
    for name in names:
        loc, tgt, lens = VIEWS[name]
        loc, tgt = V(loc), V(tgt)
        cam.location = loc
        cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
        cam.data.lens = lens
        d = (tgt - loc)
        dist = d.length
        f = d.normalized()
        side = f.cross(V((0, 0, 1))).normalized()
        places = [loc - f * 0.2 * dist + side * 0.7 * dist + V((0, 0, 0.6 * dist)),
                  loc - f * 0.1 * dist - side * 0.8 * dist + V((0, 0, 0.2 * dist)),
                  tgt + f * 0.8 * dist - side * 0.3 * dist + V((0, 0, 0.7 * dist))]
        for (lo, e), pl in zip(rig, places):
            lo.location = pl
            lo.rotation_euler = (tgt - pl).to_track_quat('-Z', 'Y').to_euler()
            lo.data.energy = e * 14.0 * (dist / 0.5) ** 2
            lo.data.size = max(0.08, 0.5 * dist)
        sc.render.filepath = os.path.join(OUT_DIR, f'cables_{name}.png')
        bpy.ops.render.render(write_still=True)
        print('RENDERED', sc.render.filepath)


if __name__ == '__main__':
    import sys
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if argv and argv[0] == 'preview':
        preview(argv[1:] or list(VIEWS))
    else:
        build()
