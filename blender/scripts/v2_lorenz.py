"""
v2 lorenz: desk sculpture of the Lorenz attractor, plus the owner's paper (main.pdf) stapled
and lying at the desk's front-left.

Replaces the small wire icosahedron on a stand (room.blend: empty Node_305 at (-0.98, 0.86) with
Mesh_204 = dark round base, Mesh_205 = post, and Node_308 holding the wire frame
Mesh_206..Mesh_247 plus the inner piece Mesh_248).

Placement: the root sits where the orchestrator put the sculpture in room.blend,
(-0.4525, 0.9291, 0.735). The paper stack is a child placed ~0.53 m from it, at the desk's
front-left, left of the notepad / sticky notes.

Construction
  * The Lorenz system (sigma=10, rho=28, beta=8/3) is integrated with RK4, dt=0.005, from
    (1,1,1); the first 3000 steps (15 time units) are discarded as the transient and the next
    6500 points kept. The butterfly (Lorenz x-z plane) is upright, Lorenz y is depth.
  * The trajectory is scaled so its largest extent is 13 cm, then resampled along arc length
    with curvature-adaptive spacing (denser on tight turns) and swept as a Ø1.4 mm, 8-sided
    polished-brass wire with rotation-minimising frames (no twist, no kinks) and rounded ends.
  * It is carried at a low point of the dip between the wings by a Ø3 mm brass rod rising from a
    turned brass collar on a Ø70 mm black-granite disc on a felt pad; a solder bead joins them.
  * Paper: pages 1-4 of the owner's paper (US Letter 215.9 x 279.4 mm, 0.1 mm), pre-rendered at
    200 dpi to blender/scene/parts/paper_page<N>.png (git-ignored) and packed into the .blend.
    Stapled at the top-left corner (steel staple, diagonal); pages 2-4 are fanned a few degrees
    about the staple underneath page 1. Each sheet's height field rests on the sheets below it
    (plus a gap), is flat at the staple and lifts a few mm toward the free corners, with a
    faint cockle.

Usage:  blender -b --factory-startup --python v2_lorenz.py -- [--no-render] [--only=seat,close,34]
"""
import bpy
import bmesh
import math
import os
import sys
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

OLD_SPOT = (-0.98, 0.86)                  # Node_305 (old icosahedron stand) in room.blend
ROOM_LOC = (-0.4525, 0.9291, 0.735)       # sculpture base centre = root (as placed in room.blend)
STACK_W = (-0.878, 0.588)                 # paper stack centre (page 1) in room xy
STACK_YAW = math.radians(13.0)            # page 1 turned a little toward the seated viewer
FAN_DEG = [-8.5, -5.5, -2.5]              # pages 4, 3, 2 rotated about the staple
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
# sight (viewer is at ~-68 deg from the sculpture here); yaw -22 would be square on, -14 turns
# one wing slightly forward.
YAW = math.radians(-14)

BASE_R = 0.035
BASE_H = 0.018
FELT_R = 0.0315
FELT_T = 0.0012
ROD_R = 0.0015
COLLAR_R = 0.0045
COLLAR_H = 0.007
ROD_GAP = 0.042        # rod length visible between collar top and the attractor's low point

LETTER = (0.2159, 0.2794)
PAPER_T = 0.0001
PAPER_GAP = 0.00012
PAPER_Z0 = 0.00004
PNX, PNY = 16, 20
STAPLE_IN = 0.011        # staple point inset from the top-left corner (both directions)
PAGE_DIR = os.path.join(PARTS, 'paper_page{}.png')


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


def mat_steel():
    m = bpy.data.materials.new('lorenz_staple_steel')
    m.use_nodes = True
    nt = m.node_tree
    b = bsdf_of(m)
    b.inputs['Base Color'].default_value = (0.62, 0.63, 0.64, 1)
    b.inputs['Metallic'].default_value = 1.0
    tc = rough_var(nt, b, 0.28, 0.06, 900.0)
    fine_bump(nt, b, tc, 8000.0, 0.1)
    return m


def load_page(n):
    path = PAGE_DIR.format(n)
    if not os.path.exists(path):
        raise SystemExit(f'missing {path}: render it from main.pdf at 200 dpi (PyMuPDF)')
    img = bpy.data.images.load(path)
    img.name = f'lorenz_paper_page{n}'
    img.alpha_mode = 'NONE'
    img.pack()
    return img


# ----------------------------------------------------------------------------- paper sheets
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


class Sheet:
    def __init__(self, page, c, th, staple, a_edge, a_corner, seed):
        self.page, self.c, self.th = page, np.array(c), th
        self.staple = np.array(staple)
        self.a_edge, self.a_corner = a_edge, a_corner
        rng = np.random.default_rng(seed)
        self.ck = [(rng.uniform(35, 80), rng.uniform(35, 80), rng.uniform(0, 6.28), rng.uniform(0, 6.28))
                   for _ in range(3)]
        self.hx, self.hy = LETTER[0] / 2, LETTER[1] / 2

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
        """flat and held at the staple, lifting gently toward the free edges and corners"""
        d = np.linalg.norm(p - self.staple, axis=-1)
        w = smoothstep(0.012, 0.08, d)
        q = self.local(p)
        un = np.clip((q[..., 0] + self.hx) / (2 * self.hx), 0, 1)      # 0 at the stapled edge
        vn = np.clip((self.hy - q[..., 1]) / (2 * self.hy), 0, 1)      # 0 at the top edge
        edge = (d / 0.34) ** 2
        corner = (un * vn) ** 3
        ck = sum(0.5 + 0.5 * np.sin(p[..., 0] * a + ph) * np.sin(p[..., 1] * b + ph2)
                 for a, b, ph, ph2 in self.ck) / 3.0
        return w * (self.a_edge * edge + self.a_corner * corner + 0.00018 * ck)


DILATE = [(0.0, 0.0)] + [(0.0100 * math.cos(a), 0.0100 * math.sin(a))
                         for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]


def smax(a, b, k=0.0004):
    return 0.5 * (a + b + np.sqrt((a - b) ** 2 + k * k))


def stack_height(sheets, i, p):
    """Underside height of sheet i at root-local xy p: the sheet's own curled shape,
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

# ---- stapled paper stack (bottom -> top) in root-local xy
def rot2(v, a):
    return np.array([math.cos(a) * v[0] - math.sin(a) * v[1], math.sin(a) * v[0] + math.cos(a) * v[1]])


c1 = np.array(STACK_W) - np.array(ROOM_LOC[:2])
sp_local = np.array([-LETTER[0] / 2 + STAPLE_IN, LETTER[1] / 2 - STAPLE_IN])
STAPLE = c1 + rot2(sp_local, STACK_YAW)
SHEETS = []
for k, (page, fan) in enumerate(zip((4, 3, 2), FAN_DEG)):
    th = STACK_YAW + math.radians(fan)
    SHEETS.append(Sheet(page, STAPLE - rot2(sp_local, th), th, STAPLE, 0.0017 - 0.0002 * k, 0.0016, 20 + page))
SHEETS.append(Sheet(1, c1, STACK_YAW, STAPLE, 0.0012, 0.0019, 21))
M_PLAIN = mat_paper('lorenz_paper_back', None)
paper_objs, paper_tops = [], []
for i, sh in enumerate(SHEETS):
    img = load_page(sh.page)
    me, top, bot = sheet_mesh(SHEETS, i, f'NEW_lorenz_paper_page{sh.page}')
    ob = add_obj(me.name, me, [mat_paper(f'lorenz_paper_page{sh.page}', img), M_PLAIN])
    paper_objs.append(ob)
    paper_tops.append(top)

# ---- staple: 12.7 mm crown on page 1, diagonal across the corner, legs through the stack
z_top = float(stack_height(SHEETS, len(SHEETS) - 1, STAPLE[None, :])[0]) + PAPER_T
SR = 0.00025
crown = rot2(np.array([1.0, 1.0]) / math.sqrt(2), STACK_YAW)
zc, zb, rc = z_top + SR + 0.00002, PAPER_Z0 + SR + 0.0001, 0.0006
half = 0.00635
pts = [(-half, zb), (-half, zc - rc)]
pts += [(-half + rc - rc * math.cos(a), zc - rc + rc * math.sin(a)) for a in np.linspace(0.3, math.pi / 2, 4)]
pts += [(half - rc + rc * math.cos(a), zc - rc + rc * math.sin(a)) for a in np.linspace(math.pi / 2, 0.3, 4)]
pts += [(half, zc - rc), (half, zb)]
sp3 = np.array([[STAPLE[0] + crown[0] * u, STAPLE[1] + crown[1] * u, z] for u, z in pts])
seg = np.linalg.norm(np.diff(sp3, axis=0), axis=1)
ss = np.concatenate([[0], np.cumsum(seg)])
tt = np.linspace(0, ss[-1], 40)
sp3 = np.stack([np.interp(tt, ss, sp3[:, i]) for i in range(3)], axis=1)
staple = add_obj('NEW_lorenz_staple', tube_mesh('NEW_lorenz_staple', sp3, SR, 8), [mat_steel()])

# the sculpture stands straight on the desk
Z_FELT = 0.00005
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
for i, t in enumerate(paper_tops):
    w = t[:, :2] + room_xy
    print(f'SHEET page{SHEETS[i].page}: x[{w[:, 0].min():.3f},{w[:, 0].max():.3f}] '
          f'y[{w[:, 1].min():.3f},{w[:, 1].max():.3f}] z_top_max={t[:, 2].max() * 1000:.2f}mm')
from mathutils.bvhtree import BVHTree
dg = bpy.context.evaluated_depsgraph_get()
trees = [BVHTree.FromObject(o, dg) for o in paper_objs]
bad = 0
for gx in np.linspace(c1[0] - 0.2, c1[0] + 0.2, 161):
    for gy in np.linspace(c1[1] - 0.2, c1[1] + 0.2, 161):
        prev_top = None
        for i, tr in enumerate(trees):
            hit_t = tr.ray_cast(Vector((gx, gy, 0.05)), Vector((0, 0, -1)))
            hit_b = tr.ray_cast(Vector((gx, gy, -0.01)), Vector((0, 0, 1)))
            if hit_t[0] is None:
                continue
            if hit_b[0] is None or hit_b[0].z < 0:
                bad += 1
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
print(f'WIRE x[{wq[:, 0].min():.3f},{wq[:, 0].max():.3f}] y[{wq[:, 1].min():.3f},{wq[:, 1].max():.3f}]')


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
    lights = [(area('key', (0, 0, 1), (0, 0, 0), 9.0, 0.35), Vector((-0.35, -0.3, 0.55))),
              (area('fill', (0, 0, 1), (0, 0, 0), 2.5, 0.4, (0.95, 0.97, 1.0)), Vector((0.45, -0.25, 0.25))),
              (area('rim', (0, 0, 1), (0, 0, 0), 6.0, 0.25), Vector((0.1, 0.5, 0.35)))]
    rig += [lo_ for lo_, _ in lights]
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
    fr = Vector((0.75, -1.0, 0.75)).normalized()
    pc = Vector((c1[0], c1[1], 0.001))
    to_eye_p = (VIEWER - Vector((STACK_W[0], STACK_W[1], ROOM_LOC[2]))).normalized()
    title = pc + Vector((*rot2(np.array([-0.01, 0.075]), STACK_YAW), 0.0))
    views = {   # key: (camera, target, lens, light centre)
        'seat': (pc + to_eye_p * 0.62, pc, 75, pc),
        'close': (title + (to_eye_p + Vector((0, 0, 0.35))).normalized() * 0.28, title, 60, pc),
        '34': (ctr + fr * 0.5, ctr, 50, Vector((0, 0, 0.06))),
    }
    only = [a for a in ARGS if a.startswith('--only=')]
    only = only[0].split('=')[1].split(',') if only else None
    for key, (loc, tgt, lens, lc) in views.items():
        if only and key not in only:
            continue
        for lo_, off in lights:
            lo_.location = lc + off
            look(lo_, lc)
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
