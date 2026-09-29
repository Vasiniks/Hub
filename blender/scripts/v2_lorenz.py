"""
v2 lorenz: desk sculpture of the Lorenz attractor on loose sheets of paper.

Replaces the small wire icosahedron on a stand at the desk's front-left (room.blend: empty
Node_305 at (-0.98, 0.86) with Mesh_204 = dark round base, Mesh_205 = post, and Node_308 holding
the wire frame Mesh_206..Mesh_247 plus the inner piece Mesh_248).

Construction
  * The Lorenz system (sigma=10, rho=28, beta=8/3) is integrated with RK4, dt=0.005, from
    (1,1,1); the first 3000 steps (15 time units) are discarded as the transient and the next
    6500 points kept. The butterfly (Lorenz x-z plane) is upright, Lorenz y is depth.
  * The trajectory is scaled so its largest extent is 13 cm, then resampled along arc length
    with curvature-adaptive spacing (denser on tight turns) and swept as a Ø1.4 mm, 8-sided
    polished-brass wire with rotation-minimising frames (no twist, no kinks) and rounded ends.
  * It is carried at its lowest point (where the trajectory dips toward the origin between the
    wings) by a Ø3 mm brass rod rising from a turned brass collar on a Ø70 mm black-granite disc
    on a felt pad. A small solder bead joins wire and rod.
  * Four loose A5 sheets (0.1 mm thick) lie slightly fanned under the base. Each sheet's height
    field rests on the sheets below it (plus a gap), is pressed flat under the base and lifts a
    few mm toward the free edges and corners, with a faint cockle. Pages are drawn in numpy and
    packed into the .blend: printed text, graph paper with a pencilled x(t) plot, ruled paper
    with ballpoint handwriting, and on top a pencil sketch of the attractor's x-z projection.

Usage:  blender -b --factory-startup --python v2_lorenz.py -- [--no-render] [--only=34,seat]
"""
import bpy
import bmesh
import math
import os
import sys
import tempfile
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402

ARGS = lib.argv()
RENDER = '--no-render' not in ARGS
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'lorenz.blend')
NAME = 'lorenz'

OLD_SPOT = (-0.98, 0.86)          # Node_305 (old icosahedron stand) in room.blend
ROOM_LOC = (-0.93, 0.86, 0.735)   # base centre on the desk top
VIEWER = Vector((0.0, -0.16, 1.175))
DESK_X_MIN = -1.04

# ----------------------------------------------------------------------------- dimensions
SIGMA, RHO, BETA = 10.0, 28.0, 8.0 / 3.0
DT = 0.005
N_TRANS = 3000
N_KEEP = 6500
SPAN = 0.13            # largest extent of the attractor
WIRE_R = 0.0007        # Ø1.4 mm
WIRE_SIDES = 8
N_RINGS = 1850
# The wings lie along Lorenz (1,1,0); yaw ~0 puts that axis across the seated viewer's line of
# sight (viewer is at ~-47 deg from the sculpture), a few degrees more turns one wing forward.
YAW = math.radians(8)

BASE_R = 0.035
BASE_H = 0.018
FELT_R = 0.0315
FELT_T = 0.0012
ROD_R = 0.0015
COLLAR_R = 0.0045
COLLAR_H = 0.007
ROD_GAP = 0.042        # rod length visible between collar top and the attractor's low point

A5 = (0.148, 0.210)
PAPER_T = 0.0001
PAPER_GAP = 0.00012
PAPER_Z0 = 0.00004
PNX, PNY = 14, 20


# ----------------------------------------------------------------------------- Lorenz
def lorenz_f(p):
    x, y, z = p
    return np.array([SIGMA * (y - x), x * (RHO - z) - y, x * y - BETA * z])


def integrate():
    p = np.array([1.0, 1.0, 1.0])
    out = np.empty((N_KEEP, 3))
    for i in range(N_TRANS + N_KEEP):
        k1 = lorenz_f(p)
        k2 = lorenz_f(p + 0.5 * DT * k1)
        k3 = lorenz_f(p + 0.5 * DT * k2)
        k4 = lorenz_f(p + DT * k3)
        p = p + DT / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        if i >= N_TRANS:
            out[i - N_TRANS] = p
    return out


def resample_adaptive(P, n_rings):
    """Arc-length resampling with spacing ~ radius of curvature, clamped, n_rings samples."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.gradient(P, s, axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    dt_ = np.gradient(t, s, axis=0)
    k = np.linalg.norm(dt_, axis=1)
    k = np.convolve(k, np.ones(9) / 9, mode='same')
    # density: 1/ds with ds = clamp(a / k, lo, hi); find a so the total count is n_rings
    lo, hi = 0.0009, 0.0075

    def count(a):
        ds = np.clip(a / np.maximum(k, 1e-6), lo, hi)
        dens = 1.0 / ds
        c = np.concatenate([[0.0], np.cumsum(0.5 * (dens[1:] + dens[:-1]) * seg)])
        return c

    a0, a1 = 1e-4, 10.0
    for _ in range(60):
        am = math.sqrt(a0 * a1)
        if count(am)[-1] > n_rings:
            a0 = am
        else:
            a1 = am
    c = count(a1)
    targets = np.linspace(0, c[-1], n_rings)
    ss = np.interp(targets, c, s)
    Q = np.stack([np.interp(ss, s, P[:, i]) for i in range(3)], axis=1)
    return Q, s[-1]


def rmf_frames(Q):
    """Rotation-minimising frames (double reflection, Wang et al. 2008)."""
    n = len(Q)
    T = np.gradient(Q, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    R = np.empty_like(Q)
    a = np.cross(T[0], [0, 0, 1.0])
    if np.linalg.norm(a) < 1e-3:
        a = np.cross(T[0], [1.0, 0, 0])
    R[0] = a / np.linalg.norm(a)
    for i in range(n - 1):
        v1 = Q[i + 1] - Q[i]
        c1 = v1 @ v1
        rL = R[i] - (2 / c1) * (v1 @ R[i]) * v1
        tL = T[i] - (2 / c1) * (v1 @ T[i]) * v1
        v2 = T[i + 1] - tL
        c2 = v2 @ v2
        r = rL - (2 / c2) * (v2 @ rL) * v2 if c2 > 1e-14 else rL
        r -= (r @ T[i + 1]) * T[i + 1]
        R[i + 1] = r / np.linalg.norm(r)
    B = np.cross(T, R)
    return T, R, B


def tube_mesh(name, Q, radius, sides):
    T, R, B = rmf_frames(Q)
    ang = np.linspace(0, 2 * math.pi, sides, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    verts = (Q[:, None, :] + radius * (ca[None, :, None] * R[:, None, :] + sa[None, :, None] * B[:, None, :]))
    verts = verts.reshape(-1, 3).tolist()
    faces = []
    n = len(Q)
    for i in range(n - 1):
        a, b = i * sides, (i + 1) * sides
        for j in range(sides):
            j1 = (j + 1) % sides
            faces.append((a + j, a + j1, b + j1, b + j))
    # rounded end caps: two shrinking rings plus a pole
    for end, sign in ((0, -1.0), (n - 1, 1.0)):
        base = end * sides
        prev = list(range(base, base + sides))
        for step, (dz, rr) in enumerate(((0.55, 0.83), (0.9, 0.44))):
            idx0 = len(verts)
            for j in range(sides):
                p = Q[end] + sign * T[end] * radius * dz + radius * rr * (ca[j] * R[end] + sa[j] * B[end])
                verts.append(p.tolist())
            ring = list(range(idx0, idx0 + sides))
            for j in range(sides):
                j1 = (j + 1) % sides
                f = (prev[j], prev[j1], ring[j1], ring[j])
                faces.append(f if sign > 0 else f[::-1])
            prev = ring
        pole = len(verts)
        verts.append((Q[end] + sign * T[end] * radius).tolist())
        for j in range(sides):
            j1 = (j + 1) % sides
            f = (prev[j], prev[j1], pole)
            faces.append(f if sign > 0 else f[::-1])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.shade_smooth()
    me.validate()
    return me


# ----------------------------------------------------------------------------- lathe
def lathe(bm, prof, n, sharp_deg=40, cz=0.0):
    rings = []
    for r, z in prof:
        if r < 1e-9:
            rings.append([bm.verts.new((0, 0, z + cz))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / n),
                                        r * math.sin(2 * math.pi * k / n), z + cz)) for k in range(n)])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(n):
            k1 = (k + 1) % n
            if len(a) == 1:
                bm.faces.new((a[0], b[k1], b[k]))
            elif len(b) == 1:
                bm.faces.new((a[k], a[k1], b[0]))
            else:
                bm.faces.new((a[k], a[k1], b[k1], b[k]))
    return rings


def arc(cx, cz, r, a0, a1, steps):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / steps), cz + r * math.sin(a0 + (a1 - a0) * i / steps))
            for i in range(steps + 1)]


def finish_bm(bm, name, sharp_deg=40):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bm.normal_update()
    for f in bm.faces:
        f.smooth = True
    thr = math.radians(sharp_deg)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > thr:
            e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


# ----------------------------------------------------------------------------- materials
def bsdf_of(mat):
    return next(nd for nd in mat.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED')


def rough_var(nt, b, rough, var, scale):
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sm = nt.nodes.new('ShaderNodeTexNoise')
    sm.inputs['Scale'].default_value = scale
    sm.inputs['Detail'].default_value = 3.0
    nt.links.new(tc.outputs['Object'], sm.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = max(0.02, rough - var)
    mr.inputs['To Max'].default_value = rough + var
    nt.links.new(sm.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    return tc


def fine_bump(nt, b, tc, scale, strength, dist=0.00002, detail=2.0):
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = detail
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = dist
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return bump


def mat_brass():
    m = bpy.data.materials.new('lorenz_brass_polished')
    m.use_nodes = True
    nt = m.node_tree
    b = bsdf_of(m)
    b.inputs['Base Color'].default_value = (0.86, 0.68, 0.36, 1)
    b.inputs['Metallic'].default_value = 1.0
    tc = rough_var(nt, b, 0.16, 0.05, 90.0)
    fine_bump(nt, b, tc, 6000.0, 0.08)
    return m


def mat_granite():
    m = bpy.data.materials.new('lorenz_black_granite')
    m.use_nodes = True
    nt = m.node_tree
    b = bsdf_of(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = 900.0
    nt.links.new(tc.outputs['Object'], vor.inputs['Vector'])
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 650.0
    nz.inputs['Detail'].default_value = 4.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    # sparse light feldspar/quartz flecks in a near-black matrix
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.62
    ramp.color_ramp.elements[0].color = (0.018, 0.018, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.20, 0.20, 0.21, 1)
    nt.links.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.inputs['A'].default_value = (0.03, 0.03, 0.032, 1)
    nt.links.new(vor.outputs['Distance'], mix.inputs['Factor'])
    nt.links.new(ramp.outputs['Color'], mix.inputs['B'])
    nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.14
    mr.inputs['To Max'].default_value = 0.26
    nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    if 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = 0.25
        b.inputs['Coat Roughness'].default_value = 0.08
    fine_bump(nt, b, tc, 3000.0, 0.04)
    return m


def mat_felt():
    m = bpy.data.materials.new('lorenz_felt')
    m.use_nodes = True
    nt = m.node_tree
    b = bsdf_of(m)
    b.inputs['Base Color'].default_value = (0.025, 0.03, 0.028, 1)
    tc = rough_var(nt, b, 0.95, 0.04, 200.0)
    if 'Sheen Weight' in b.inputs:
        b.inputs['Sheen Weight'].default_value = 0.6
    fine_bump(nt, b, tc, 4000.0, 0.3, detail=6.0)
    return m


def mat_paper(name, img):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = bsdf_of(m)
    tint = (0.84, 0.835, 0.81, 1)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    # paper fibre: fine bump + slight tone mottling
    fib = nt.nodes.new('ShaderNodeTexNoise')
    fib.inputs['Scale'].default_value = 2500.0
    fib.inputs['Detail'].default_value = 8.0
    nt.links.new(tc.outputs['Object'], fib.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.06
    bump.inputs['Distance'].default_value = 0.00002
    nt.links.new(fib.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    mott = nt.nodes.new('ShaderNodeMapRange')
    mott.inputs['To Min'].default_value = 0.97
    mott.inputs['To Max'].default_value = 1.02
    nt.links.new(fib.outputs['Fac'], mott.inputs['Value'])
    tint_mul = nt.nodes.new('ShaderNodeMix')
    tint_mul.data_type = 'RGBA'
    tint_mul.blend_type = 'MULTIPLY'
    tint_mul.inputs['Factor'].default_value = 1.0
    tint_mul.inputs['A'].default_value = tint
    rough_mix = None
    if img is not None:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        tex.interpolation = 'Cubic'
        nt.links.new(tc.outputs['UV'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Color'], tint_mul.inputs['B'])
        # graphite / ink is a little glossier than the paper: roughness follows luminance
        bw = nt.nodes.new('ShaderNodeRGBToBW')
        nt.links.new(tex.outputs['Color'], bw.inputs['Color'])
        rough_mix = nt.nodes.new('ShaderNodeMapRange')
        rough_mix.inputs['From Min'].default_value = 0.35
        rough_mix.inputs['From Max'].default_value = 1.0
        rough_mix.inputs['To Min'].default_value = 0.36
        rough_mix.inputs['To Max'].default_value = 0.62
        nt.links.new(bw.outputs['Val'], rough_mix.inputs['Value'])
        nt.links.new(rough_mix.outputs['Result'], b.inputs['Roughness'])
    else:
        tint_mul.inputs['B'].default_value = (1, 1, 1, 1)
        b.inputs['Roughness'].default_value = 0.62
    fin = nt.nodes.new('ShaderNodeMix')
    fin.data_type = 'RGBA'
    fin.blend_type = 'MULTIPLY'
    fin.inputs['Factor'].default_value = 1.0
    nt.links.new(tint_mul.outputs['Result'], fin.inputs['A'])
    nt.links.new(mott.outputs['Result'], fin.inputs['B'])
    nt.links.new(fin.outputs['Result'], b.inputs['Base Color'])
    if 'Subsurface Weight' in b.inputs:
        b.inputs['Subsurface Weight'].default_value = 0.05
        b.inputs['Subsurface Radius'].default_value = (0.0005, 0.0005, 0.0005)
    return m


# ----------------------------------------------------------------------------- page drawing
PW, PH = 1024, 1448
PXM = PW / A5[0]


def mm(v):
    return v * PXM / 1000.0


def gblur(a, s):
    if s <= 0:
        return a
    r = max(1, int(math.ceil(3 * s)))
    x = np.arange(-r, r + 1)
    w = np.exp(-x * x / (2 * s * s))
    w /= w.sum()
    p = np.pad(a, ((r, r), (0, 0)), mode='edge')
    a = sum(w[i] * p[i:i + a.shape[0]] for i in range(2 * r + 1))
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    a = sum(w[i] * p[:, i:i + a.shape[1]] for i in range(2 * r + 1))
    return a


def splat(acc, x, y, w):
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    for dx, dy, ww in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                       (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        m = (xi >= 0) & (xi < PW) & (yi >= 0) & (yi < PH)
        np.add.at(acc, (yi[m], xi[m]), (w * ww)[m])


class Layer:
    def __init__(self, sigma, colour, opacity=1.0, grain=0.0, graphite=False):
        self.acc = np.zeros((PH, PW))
        self.sigma, self.colour, self.opacity = sigma, np.array(colour), opacity
        self.grain, self.graphite = grain, graphite

    def stroke(self, pts, pressure=1.0):
        pts = np.asarray(pts, float)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        if s[-1] < 1e-6:
            return
        n = max(2, int(s[-1] / 0.45))
        ss = np.linspace(0, s[-1], n)
        x = np.interp(ss, s, pts[:, 0])
        y = np.interp(ss, s, pts[:, 1])
        if np.ndim(pressure):
            w = np.interp(ss, s, pressure)
        else:
            w = np.full(n, float(pressure))
        splat(self.acc, x, y, w * (s[-1] / n))

    def density(self, grain_field):
        a = gblur(self.acc, self.sigma) * math.sqrt(2 * math.pi) * self.sigma
        d = 1.0 - np.exp(-2.4 * a)
        if self.grain:
            d *= np.clip(1.0 - self.grain + self.grain * grain_field, 0, 1)
        return np.clip(d * self.opacity, 0, 1)


class Page:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.rgb = np.ones((PH, PW, 3))
        self.gloss = np.zeros((PH, PW))
        g = gblur(self.rng.random((PH, PW)), 0.8)
        self.grain = np.clip((g - g.mean()) / (g.std() + 1e-9) * 0.35 + 0.6, 0, 1)

    def apply(self, d, colour, graphite=False):
        self.rgb *= 1.0 - d[..., None] * (1.0 - np.asarray(colour)[None, None, :])
        if graphite:
            self.gloss = np.maximum(self.gloss, d)

    def layer(self, L):
        self.apply(L.density(self.grain), L.colour, L.graphite)

    def image(self, name):
        rgba = np.concatenate([self.rgb, np.ones((PH, PW, 1))], axis=2).astype(np.float32)
        img = bpy.data.images.new(name, PW, PH, alpha=False)
        img.pixels.foreach_set(rgba.ravel())
        path = os.path.join(tempfile.gettempdir(), f'{name}.png')
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)
        img = bpy.data.images.load(path)
        img.name = name
        img.alpha_mode = 'NONE'
        img.pack()
        return img


def wobble(rng, n, amp, smooth=40):
    w = rng.normal(0, 1, n + 2 * smooth)
    k = np.exp(-np.linspace(-2.5, 2.5, 2 * smooth + 1) ** 2)
    w = np.convolve(w, k / k.sum(), mode='same')[smooth:smooth + n]
    return w / (np.abs(w).max() + 1e-9) * amp


def hand_line(rng, p0, p1, amp=0.8):
    n = max(8, int(np.linalg.norm(np.subtract(p1, p0)) / 3))
    t = np.linspace(0, 1, n)[:, None]
    pts = np.asarray(p0) * (1 - t) + np.asarray(p1) * t
    d = np.subtract(p1, p0)
    nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
    return pts + nrm[None, :] * wobble(rng, n, amp, smooth=max(3, n // 6))[:, None]


def cursive_word(rng, x0, y0, nl, xh, slant=0.28):
    adv = xh * rng.uniform(0.78, 0.98)
    amps = rng.choice([1.0, 1.0, 1.0, 0.8, 2.3, -1.5], size=nl)
    amps[0] = rng.choice([1.0, 2.3])
    ts = np.linspace(0, nl, nl * 22)
    j = np.clip(np.floor(ts).astype(int), 0, nl - 1)
    f = ts - j
    y = xh * amps[j] * (1 - np.cos(2 * np.pi * f)) / 2
    x = adv * ts + 0.3 * adv * np.sin(2 * np.pi * f)
    y = y + wobble(rng, len(ts), xh * 0.08, smooth=12)
    x = x + slant * y
    pts = np.stack([x0 + x, y0 + y], axis=1)
    return pts, x0 + adv * nl


def handwriting(L, rng, x0, y0, width, xh, pressure=0.85, words=None):
    x = x0
    base = y0
    count = 0
    while x < x0 + width - 3 * xh:
        if words is not None and count >= words:
            break
        nl = int(rng.integers(2, 8))
        nl = min(nl, max(2, int((x0 + width - x) / xh) - 1))
        pts, xe = cursive_word(rng, x, base, nl, xh)
        pr = pressure * (0.85 + 0.3 * rng.random()) * (0.8 + 0.2 * np.sin(np.linspace(0, 3, len(pts))))
        L.stroke(pts, pr)
        if rng.random() < 0.25:  # a t-cross / i-dot
            cx = x + (xe - x) * rng.uniform(0.2, 0.8)
            L.stroke(hand_line(rng, (cx - xh * 0.5, base + xh * 1.6), (cx + xh * 0.6, base + xh * 1.7), 0.3), pressure)
        x = xe + xh * rng.uniform(1.0, 1.7)
        base = y0 + rng.normal(0, xh * 0.06)
        count += 1
    return x


def equation(L, rng, x0, y0, xh, pressure=0.9):
    """word = word(word) style line with an '=' sign."""
    pts, xe = cursive_word(rng, x0, y0, 2, xh)
    L.stroke(pts, pressure)
    x = xe + xh * 0.9
    L.stroke(hand_line(rng, (x, y0 + xh * 0.35), (x + xh * 1.1, y0 + xh * 0.38), 0.2), pressure)
    L.stroke(hand_line(rng, (x, y0 + xh * 0.8), (x + xh * 1.1, y0 + xh * 0.82), 0.2), pressure)
    x += xh * 2.0
    return handwriting(L, rng, x, y0, xh * 14, xh, pressure, words=2)


def page_printed(seed):
    pg = Page(seed)
    rng = pg.rng
    d = np.zeros((PH, PW))
    left, right = mm(16), PW - mm(16)
    y = PH - mm(20)

    def glyph_run(x, y, n, xh, dens):
        for _ in range(n):
            w = mm(rng.uniform(0.7, 1.0))
            h = xh * (1.45 if rng.random() < 0.3 else 1.0)
            y0 = y - (xh * 0.45 if rng.random() < 0.08 else 0.0)
            d[int(y0):int(y + h), int(x):int(x + w)] = dens
            x += w + mm(0.25)
        return x

    # title + author line
    x = left + mm(8)
    for _ in range(5):
        x = glyph_run(x, y, int(rng.integers(3, 9)), mm(2.4), 0.95) + mm(2.2)
    y -= mm(7)
    x = left + mm(24)
    for _ in range(3):
        x = glyph_run(x, y, int(rng.integers(4, 8)), mm(1.4), 0.75) + mm(1.6)
    y -= mm(9)
    fig_top, fig_bot = PH * 0.46, PH * 0.26
    para_left = 0
    while y > mm(18):
        if fig_bot < y < fig_top:
            y = fig_bot - mm(4)
            continue
        indent = mm(4) if para_left == 0 else 0
        last = para_left == 7
        x = left + indent
        xmax = right - (rng.uniform(0.3, 0.7) * (right - left) if last else 0)
        while x < xmax - mm(6):
            n = int(rng.integers(2, 10))
            n = min(n, int((xmax - x) / mm(1.1)))
            if n < 1:
                break
            x = glyph_run(x, y, n, mm(1.5), 0.8) + mm(1.5)
        y -= mm(4.4)
        para_left = 0 if last else para_left + 1
        if last:
            y -= mm(2.0)
    d = gblur(d, 0.6)
    pg.apply(d, (0.12, 0.12, 0.13))
    # printed figure: axes + a thin x(t) trace
    L = Layer(0.55, (0.15, 0.15, 0.2))
    fx0, fx1 = left + mm(10), right - mm(10)
    L.stroke([(fx0, fig_bot + mm(4)), (fx1, fig_bot + mm(4))])
    L.stroke([(fx0, fig_bot + mm(4)), (fx0, fig_top - mm(4))])
    xs = LORENZ[:1600, 0]
    u = np.linspace(fx0 + mm(1), fx1, len(xs))
    v = (fig_bot + fig_top) / 2 + xs / 20.0 * (fig_top - fig_bot) * 0.36
    L.stroke(np.stack([u, v], axis=1), 0.9)
    pg.layer(L)
    return pg


def page_graph(seed):
    pg = Page(seed)
    rng = pg.rng
    d = np.zeros((PH, PW))
    step = mm(5)
    for i in range(1, int(PW / step) + 1):
        d[:, int(i * step)] = 0.35 if i % 2 == 0 else 0.2
    for i in range(1, int(PH / step) + 1):
        d[int(i * step), :] = np.maximum(d[int(i * step), :], 0.35 if i % 2 == 0 else 0.2)
    d = gblur(d, 0.5)
    pg.apply(np.clip(d * 1.6, 0, 1), (0.55, 0.78, 0.82))
    # pencilled time series x(t) and z(t)
    P = Layer(1.2, (0.28, 0.28, 0.3), 0.8, grain=0.6, graphite=True)
    for row, comp, sc, off in ((0.34, 0, 20.0, 0.0), (0.7, 2, 25.0, 25.0)):
        vals = LORENZ[200:1400, comp]
        u = np.linspace(mm(14), PW - mm(10), len(vals))
        v = PH * row + (vals - off) / sc * mm(26)
        pts = np.stack([u, v], axis=1)
        pts[:, 1] += wobble(rng, len(pts), 0.8, smooth=30)
        P.stroke(pts, 0.8 + 0.2 * np.sin(np.linspace(0, 9, len(pts))))
        P.stroke(hand_line(rng, (mm(12), PH * row), (PW - mm(8), PH * row)), 0.7)
        P.stroke(hand_line(rng, (mm(14), PH * row - mm(30)), (mm(14), PH * row + mm(30))), 0.7)
        handwriting(P, rng, mm(18), PH * row + mm(31), mm(40), mm(2.2), 0.8, words=2)
    handwriting(P, rng, mm(16), PH - mm(16), mm(100), mm(2.6), 0.9, words=4)
    pg.layer(P)
    return pg


def page_ruled(seed):
    pg = Page(seed)
    rng = pg.rng
    d = np.zeros((PH, PW))
    pitch = mm(7.1)
    y = PH - mm(24)
    rows = []
    while y > mm(10):
        d[int(y), :] = 0.5
        rows.append(y)
        y -= pitch
    pg.apply(gblur(d, 0.6) * 1.4, (0.55, 0.7, 0.9))
    dm = np.zeros((PH, PW))
    dm[:, int(mm(24)):int(mm(24)) + 2] = 0.55
    pg.apply(gblur(dm, 0.5), (0.9, 0.35, 0.35))
    ink = Layer(0.95, (0.12, 0.2, 0.5), 0.9)
    handwriting(ink, rng, mm(30), rows[0] + mm(1.2), mm(80), mm(2.7), 0.95, words=3)
    for i, yy in enumerate(rows[1:15]):
        if i in (4, 10):
            continue
        x0 = mm(26) + (mm(4) if i in (5, 11) else 0)
        if i % 5 == 2:
            equation(ink, rng, x0 + mm(8), yy + mm(1.0), mm(2.2))
        else:
            handwriting(ink, rng, x0, yy + mm(1.0), PW - x0 - mm(8) - rng.uniform(0, mm(30)), mm(2.2))
    pg.layer(ink)
    return pg


def page_sketch(seed):
    pg = Page(seed)
    rng = pg.rng
    P = Layer(1.25, (0.26, 0.26, 0.28), 0.85, grain=0.7, graphite=True)
    # axes
    ox, oy = PW * 0.5, mm(14)
    P.stroke(hand_line(rng, (mm(12), oy), (PW - mm(12), oy + 3)), 0.9)
    P.stroke(hand_line(rng, (ox, oy - mm(4)), (ox + 2, mm(94))), 0.9)
    for tip, d1, d2 in (((PW - mm(12), oy + 3), (-mm(3), mm(1.3)), (-mm(3), -mm(1.3))),
                        ((ox + 2, mm(94)), (-mm(1.3), -mm(3)), (mm(1.3), -mm(3)))):
        P.stroke([np.add(tip, d1), tip, np.add(tip, d2)], 0.9)
    # the attractor, x-z projection, a few loops traced by hand
    # a window of the trajectory that visits both wings about equally
    st = min(range(0, 3900, 50), key=lambda k: abs(np.sign(LORENZ[k:k + 2600, 0]).mean()))
    sub = LORENZ[st:st + 2600]
    u = ox + sub[:, 0] / 20.0 * mm(54)
    v = oy + (sub[:, 2] - 2.0) / 46.0 * mm(76)
    pts = np.stack([u, v], axis=1)
    pts += np.stack([wobble(rng, len(pts), 1.2, 25), wobble(rng, len(pts), 1.2, 25)], axis=1)
    pr = 0.55 + 0.25 * (np.sin(np.linspace(0, 40, len(pts))) * 0.5 + 0.5)
    P.stroke(pts, pr)
    # fixed points C+ / C- circled
    for sx in (1, -1):
        cx = ox + sx * 8.485 / 20.0 * mm(54)
        cy = oy + (27.0 - 2.0) / 46.0 * mm(76)
        a = np.linspace(0, 2 * np.pi * 1.1, 60)
        circ = np.stack([cx + mm(2.2) * np.cos(a), cy + mm(2.0) * np.sin(a)], axis=1)
        P.stroke(circ + rng.normal(0, 0.4, circ.shape), 0.8)
        P.stroke([(cx - 1.5, cy), (cx + 1.5, cy + 0.5)], 1.2)
    # axis labels and notes
    handwriting(P, rng, PW - mm(16), oy + mm(3), mm(8), mm(2.4), 0.9, words=1)
    handwriting(P, rng, ox + mm(3), mm(90), mm(8), mm(2.4), 0.9, words=1)
    handwriting(P, rng, mm(10), mm(4), mm(90), mm(2.3), 0.85, words=4)
    yy = PH - mm(16)
    for i in range(3):
        equation(P, rng, mm(12), yy, mm(2.6), 0.9)
        yy -= mm(8)
    handwriting(P, rng, PW * 0.62, PH - mm(16), mm(45), mm(2.4), 0.85, words=2)
    P.stroke(hand_line(rng, (PW * 0.62, PH - mm(17.5)), (PW * 0.62 + mm(34), PH - mm(17.2)), 0.6), 0.8)
    pg.layer(P)
    return pg


# ----------------------------------------------------------------------------- paper sheets
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


class Sheet:
    def __init__(self, kind, c, rot_deg, a_edge, a_corner, seed):
        self.kind, self.c = kind, np.array(c)
        self.th = math.radians(rot_deg)
        self.a_edge, self.a_corner = a_edge, a_corner
        rng = np.random.default_rng(seed)
        self.ck = [(rng.uniform(40, 90), rng.uniform(40, 90), rng.uniform(0, 6.28), rng.uniform(0, 6.28))
                   for _ in range(3)]
        self.hx, self.hy = A5[0] / 2, A5[1] / 2

    def local(self, p):
        d = p - self.c
        c, s = math.cos(-self.th), math.sin(-self.th)
        return np.stack([c * d[..., 0] - s * d[..., 1], s * d[..., 0] + c * d[..., 1]], axis=-1)

    def world(self, q):
        c, s = math.cos(self.th), math.sin(self.th)
        return np.stack([c * q[..., 0] - s * q[..., 1], s * q[..., 0] + c * q[..., 1]], axis=-1) + self.c

    def inside(self, p):
        q = self.local(p)
        dx = np.maximum(np.abs(q[..., 0]) - self.hx, 0)
        dy = np.maximum(np.abs(q[..., 1]) - self.hy, 0)
        return 1.0 - smoothstep(0.0, 0.03, np.sqrt(dx * dx + dy * dy))

    def lift(self, p):
        r = np.linalg.norm(p, axis=-1)          # base centre is the local origin
        w = smoothstep(BASE_R + 0.004, BASE_R + 0.045, r)
        q = self.local(p)
        un, vn = np.abs(q[..., 0]) / self.hx, np.abs(q[..., 1]) / self.hy
        edge = np.clip((r - BASE_R - 0.004) / 0.12, 0, None) ** 2
        corner = (un * vn) ** 2.5
        ck = sum(0.5 + 0.5 * np.sin(p[..., 0] * a + ph) * np.sin(p[..., 1] * b + ph2)
                 for a, b, ph, ph2 in self.ck) / 3.0
        return w * (self.a_edge * edge + self.a_corner * corner + 0.00018 * ck)


DILATE = [(0.0, 0.0)] + [(0.0075 * math.cos(a), 0.0075 * math.sin(a))
                         for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]


def smax(a, b, k=0.0004):
    return 0.5 * (a + b + np.sqrt((a - b) ** 2 + k * k))


def stack_height(sheets, i, p):
    """Underside height of sheet i at xy p (base-centre-relative): the sheet's own curled shape,
    but never below the top of any sheet under it (smooth max, so it drapes instead of creasing)."""
    sup = np.full(p.shape[:-1], PAPER_Z0)
    # support is dilated over the mesh cell (~half diagonal) so that the piecewise-linear
    # upper sheet never cuts through a corner or edge of a lower sheet between its vertices
    for j in range(i):
        for ox, oy in DILATE:
            pp = p + np.array([ox, oy])
            hj = stack_height(sheets, j, pp) + PAPER_T + PAPER_GAP
            sup = np.maximum(sup, sheets[j].inside(pp) * hj)
    return smax(sup, PAPER_Z0 + sheets[i].lift(p))


def sheet_mesh(sheets, i, name):
    sh = sheets[i]
    us = np.linspace(-sh.hx, sh.hx, PNX + 1)
    vs = np.linspace(-sh.hy, sh.hy, PNY + 1)
    U, V = np.meshgrid(us, vs, indexing='xy')         # (PNY+1, PNX+1)
    q = np.stack([U, V], axis=-1)
    p = sh.world(q)
    h = stack_height(sheets, i, p)
    nv = (PNX + 1) * (PNY + 1)
    top = np.concatenate([p.reshape(-1, 2), (h + PAPER_T).reshape(-1, 1)], axis=1)
    bot = np.concatenate([p.reshape(-1, 2), h.reshape(-1, 1)], axis=1)
    verts = np.concatenate([top, bot]).tolist()

    def vid(r, c, b=0):
        return b * nv + r * (PNX + 1) + c

    faces, mats, uvs = [], [], []
    for r in range(PNY):
        for c in range(PNX):
            faces.append((vid(r, c), vid(r, c + 1), vid(r + 1, c + 1), vid(r + 1, c)))
            mats.append(0)
            uvs.append([(c / PNX, r / PNY), ((c + 1) / PNX, r / PNY),
                        ((c + 1) / PNX, (r + 1) / PNY), (c / PNX, (r + 1) / PNY)])
            faces.append((vid(r, c, 1), vid(r + 1, c, 1), vid(r + 1, c + 1, 1), vid(r, c + 1, 1)))
            mats.append(1)
            uvs.append([(c / PNX, r / PNY), (c / PNX, (r + 1) / PNY),
                        ((c + 1) / PNX, (r + 1) / PNY), ((c + 1) / PNX, r / PNY)])
    # rim (outline walked counter-clockwise seen from above)
    ring = [(0, c) for c in range(PNX)] + [(r, PNX) for r in range(PNY)] + \
           [(PNY, c) for c in range(PNX, 0, -1)] + [(r, 0) for r in range(PNY, 0, -1)]
    for k in range(len(ring)):
        a, b = ring[k], ring[(k + 1) % len(ring)]
        faces.append((vid(*a, 1), vid(*b, 1), vid(*b), vid(*a)))
        mats.append(1)
        uvs.append([(0.0, 0.0)] * 4)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    for poly, m, uv in zip(me.polygons, mats, uvs):
        poly.material_index = m
        for li, co in zip(poly.loop_indices, uv):
            uvl.data[li].uv = co
    me.shade_smooth()
    me.validate()
    return me, top, bot


# ----------------------------------------------------------------------------- build
lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)
root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.05
coll.objects.link(root)


def add_obj(name, me, mats):
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.parent = root
    return ob


LORENZ = integrate()
M_BRASS, M_GRANITE, M_FELT = mat_brass(), mat_granite(), mat_felt()

# ---- paper stack (bottom -> top); base centre = local origin
SHEETS = [
    Sheet('printed', (0.013, -0.004), 8.5, 0.0020, 0.0016, 11),
    Sheet('graph', (-0.009, -0.012), -5.5, 0.0015, 0.0022, 12),
    Sheet('ruled', (0.010, -0.019), 3.5, 0.0024, 0.0014, 13),
    Sheet('sketch', (0.001, -0.030), -2.0, 0.0019, 0.0024, 14),
]
PAGES = {'printed': page_printed, 'graph': page_graph, 'ruled': page_ruled, 'sketch': page_sketch}
M_PLAIN = mat_paper('lorenz_paper_plain', None)
paper_objs, paper_tops = [], []
for i, sh in enumerate(SHEETS):
    img = PAGES[sh.kind](100 + i).image(f'lorenz_page_{sh.kind}')
    me, top, bot = sheet_mesh(SHEETS, i, f'NEW_lorenz_paper_{i}_{sh.kind}')
    ob = add_obj(me.name, me, [mat_paper(f'lorenz_paper_{sh.kind}', img), M_PLAIN])
    paper_objs.append(ob)
    paper_tops.append(top)

# base rests on the highest paper top under its footprint (lift is zero there)
ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
samp = np.concatenate([np.stack([rr * np.cos(ang), rr * np.sin(ang)], axis=1)
                       for rr in (0.0, 0.01, 0.02, 0.028, FELT_R)])
z_under = max(float(np.max(SHEETS[i].inside(samp) * (stack_height(SHEETS, i, samp) + PAPER_T)))
              for i in range(len(SHEETS)))
Z_FELT = z_under + 0.00005
Z_BASE = Z_FELT + FELT_T
Z_BASE_TOP = Z_BASE + BASE_H

# ---- felt pad
bm = bmesh.new()
lathe(bm, [(0, 0), (FELT_R - 0.0004, 0), (FELT_R, 0.0004), (FELT_R, FELT_T), (0, FELT_T)], 48, cz=Z_FELT)
felt = add_obj('NEW_lorenz_felt_pad', finish_bm(bm, 'NEW_lorenz_felt_pad'), [M_FELT])

# ---- turned granite base
R = BASE_R
prof = [(0, 0)]
prof += arc(R - 0.0015, 0.0015, 0.0015, -math.pi / 2, 0, 4)
prof += arc(R - 0.004, BASE_H - 0.004, 0.004, 0, math.pi / 2, 7)
prof += [(0.0266, BASE_H), (0.0263, BASE_H - 0.0005), (0.0253, BASE_H - 0.0005), (0.0250, BASE_H),
         (0.012, BASE_H), (0, BASE_H)]
bm = bmesh.new()
lathe(bm, prof, 72, cz=Z_BASE)
base = add_obj('NEW_lorenz_base', finish_bm(bm, 'NEW_lorenz_base', 40), [M_GRANITE])

# ---- attractor geometry
L = LORENZ.copy()
# carry it at a low point of the dip between the wings, close to the z axis (balance)
ia = int(np.argmin(L[:, 2] + 0.35 * np.linalg.norm(L[:, :2], axis=1)))
cy, sy = math.cos(YAW), math.sin(YAW)
Pl = L - L[ia]
Pr = np.stack([cy * Pl[:, 0] - sy * Pl[:, 1], sy * Pl[:, 0] + cy * Pl[:, 1], Pl[:, 2]], axis=1)
ext = Pr.max(axis=0) - Pr.min(axis=0)
S = SPAN / ext.max()
Z_ATTACH = Z_BASE_TOP + COLLAR_H + ROD_GAP
Pw = Pr * S + np.array([0, 0, Z_ATTACH])
Q, total_len = resample_adaptive(Pw, N_RINGS)
wire = add_obj('NEW_lorenz_wire', tube_mesh('NEW_lorenz_wire', Q, WIRE_R, WIRE_SIDES), [M_BRASS])
print(f'LORENZ extents {ext.round(2)} scale {S:.5f} attach L={L[ia].round(2)} len={total_len:.2f} m '
      f'rings={len(Q)} bbox_min={Q.min(axis=0).round(3)} bbox_max={Q.max(axis=0).round(3)}')

# ---- brass collar + rod (one turned part), rounded top at the attach point
prof = [(0, 0)]
prof += arc(COLLAR_R - 0.0006, 0.0006, 0.0006, -math.pi / 2, 0, 3)
prof += arc(COLLAR_R - 0.0012, COLLAR_H - 0.0012, 0.0012, 0, math.pi / 2, 4)
prof += [(ROD_R + 0.0004, COLLAR_H), (ROD_R, COLLAR_H + 0.0004)]
rod_top = Z_ATTACH - Z_BASE_TOP
prof += arc(0, rod_top - ROD_R * 0.2, ROD_R, 0, math.pi / 2, 4)
bm = bmesh.new()
lathe(bm, prof, 20, cz=Z_BASE_TOP - 0.0003)
stand = add_obj('NEW_lorenz_stand', finish_bm(bm, 'NEW_lorenz_stand', 50), [M_BRASS])

# ---- solder bead joining wire and rod, stretched along the wire
Ta = Q[min(len(Q) - 1, int(np.argmin(np.linalg.norm(Q - Pw[ia], axis=1))) + 1)] - \
     Q[max(0, int(np.argmin(np.linalg.norm(Q - Pw[ia], axis=1))) - 1)]
Ta = Vector(Ta).normalized()
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1.0)
rot = Ta.to_track_quat('X', 'Z').to_matrix().to_4x4()
bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(Pw[ia]) - Vector((0, 0, 0.0004))) @ rot @
                    Matrix.Diagonal((0.0024, 0.0017, 0.0019, 1.0)), verts=bm.verts)
bead = add_obj('NEW_lorenz_solder', finish_bm(bm, 'NEW_lorenz_solder', 90), [M_BRASS])

# ---- checks
tris = 0
for ob in coll.objects:
    if ob.type == 'MESH':
        tris += sum(len(p.vertices) - 2 for p in ob.data.polygons)
print('TRIS', tris)
room_xy = np.array(ROOM_LOC[:2])
lamp_c, lamp_r = np.array([-0.7135, 1.0385]), 0.1225
for i, t in enumerate(paper_tops):
    w = t[:, :2] + room_xy
    print(f'SHEET {i} {SHEETS[i].kind}: x[{w[:, 0].min():.3f},{w[:, 0].max():.3f}] '
          f'y[{w[:, 1].min():.3f},{w[:, 1].max():.3f}] z_top_max={t[:, 2].max() * 1000:.2f}mm '
          f'lamp_clear={np.linalg.norm(w - lamp_c, axis=1).min() - lamp_r:.3f} '
          f'from_old={np.linalg.norm(w - np.array(OLD_SPOT), axis=1).max():.3f}')
from mathutils.bvhtree import BVHTree
dg = bpy.context.evaluated_depsgraph_get()
trees = [BVHTree.FromObject(o, dg) for o in paper_objs]
g = np.linspace(-0.12, 0.12, 121)
bad = 0
for gx in g:
    for gy in g - 0.03:
        prev_top = None
        for i, tr in enumerate(trees):
            hit_t = tr.ray_cast(Vector((gx, gy, 0.05)), Vector((0, 0, -1)))
            hit_b = tr.ray_cast(Vector((gx, gy, -0.01)), Vector((0, 0, 1)))
            if hit_t[0] is None:
                continue
            if hit_b[0] is None or hit_b[0].z < 0:
                bad += 1
                print('  desk/bottom', i, round(gx, 4), round(gy, 4))
            elif prev_top is not None and hit_b[0].z < prev_top - 1e-7:
                bad += 1
                if bad < 12:
                    print('  overlap', i, round(gx, 4), round(gy, 4), f'{(prev_top - hit_b[0].z) * 1e6:.0f}um')
            prev_top = max(prev_top or 0, hit_t[0].z)
print('PAPER_ORDER_VIOLATIONS', bad)
rod_hits = np.sum((np.linalg.norm(Q[:, :2] - Pw[ia, :2], axis=1) < ROD_R + WIRE_R + 0.0003) &
                  (Q[:, 2] < Z_ATTACH - 0.003))
print('WIRE_THROUGH_ROD', int(rod_hits), 'attach_z', round(Z_ATTACH, 4), 'wire_zmin', round(Q[:, 2].min(), 4))
wq = Q[:, :2] + room_xy
print(f'WIRE x[{wq[:, 0].min():.3f},{wq[:, 0].max():.3f}] y[{wq[:, 1].min():.3f},{wq[:, 1].max():.3f}] '
      f'z[{Q[:, 2].min():.3f},{Q[:, 2].max():.3f}]  Z_FELT={Z_FELT * 1000:.2f}mm')


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


root.location = (0, 0, 0)
if RENDER:
    rig = []
    world = bpy.data.worlds.new('preview_world')
    world.use_nodes = True
    bg = next(nd for nd in world.node_tree.nodes if nd.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.18, 0.18, 0.18, 1)
    bg.inputs[1].default_value = 0.35
    scene.world = world
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = 'preview_ground'
    gm = bpy.data.materials.new('preview_ground')
    gm.use_nodes = True
    bsdf_of(gm).inputs['Base Color'].default_value = (0.25, 0.25, 0.245, 1)
    bsdf_of(gm).inputs['Roughness'].default_value = 0.6
    ground.data.materials.append(gm)
    rig.append(ground)
    rig.append(area('key', (-0.35, -0.3, 0.55), (0, 0, 0.06), 9.0, 0.35))
    rig.append(area('fill', (0.45, -0.25, 0.25), (0, 0, 0.06), 2.5, 0.4, (0.95, 0.97, 1.0)))
    rig.append(area('rim', (0.1, 0.5, 0.35), (0, 0, 0.08), 6.0, 0.25))
    cam_d = bpy.data.cameras.new('preview_cam')
    cam = bpy.data.objects.new('preview_cam', cam_d)
    scene.collection.objects.link(cam)
    rig.append(cam)
    scene.camera = cam
    cam_d.clip_start = 0.005

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
    scene.render.image_settings.file_format = 'PNG'

    ctr = Vector((0.0, -0.02, 0.075))
    to_eye = (VIEWER - Vector(ROOM_LOC) - Vector((0, 0, 0.075))).normalized()
    fr = Vector((0.75, -1.0, 0.75)).normalized()
    views = {
        '34': (ctr + fr * 0.5, ctr, 50),
        'seat': (ctr + to_eye * 0.55, ctr + Vector((0, 0, -0.01)), 50),
        'top': (Vector((0.0, -0.045, 0.62)), Vector((0.0, -0.04, 0.0)), 50),
        'detail': (Vector((0.07, -0.13, 0.07)), Vector((0.0, -0.01, 0.035)), 60),
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
    bpy.data.materials.remove(gm)
    scene.world = None
    bpy.data.worlds.remove(world)

# ----------------------------------------------------------------------------- place + save
root.location = ROOM_LOC
bpy.data.orphans_purge(do_recursive=True)
os.makedirs(PARTS, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('SAVED', OUT_BLEND)
