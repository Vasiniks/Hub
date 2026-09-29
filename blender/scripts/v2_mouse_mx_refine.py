"""
Refine the MX Master 3S scan part: clean injection-moulded surface + Pale Grey colourway.

    blender -b --factory-startup --python v2_mouse_mx_refine.py -- [--render]

Loads blender/scene/parts/mouse_mx.blend (built by v2_mouse_mx.py), replaces everything under
NEW_mouse_mx_root with a clean rebuild and saves the file in place. Re-runnable: the geometry is
always rebuilt from the owner-downloaded scan GLB (same alignment as v2_mouse_mx.py), never from
the previous result.

Pipeline
  scan (366k tris, photogrammetry) -> voxel remesh 0.35 mm -> Taubin smoothing (no shrink)
  -> flat base -> collapse-decimate -> exact iso-line cuts along the part boundaries
  (top shell / main buttons / mode button / side buttons / silver chassis) -> material per part,
  seam-distance attribute drives 0.3 mm shader grooves -> boolean wheel well + thumb-wheel slot
  -> clean rebuilt steel scroll wheel and twin-drum thumb wheel, feet, bottom plate, USB-C
  -> scaled to Logitech's 124.9 x 84.3 x 51 mm.
Region boundaries were read off orthographic renders of the scan texture (coordinates below are
in mm, in the aligned-scan frame before the final height scale: +Y front, +X right, Z up).

Colours (Pale Grey): Logitech's own "Pale Gray" swatch (236,237,239) for the shell, button and
thumb rest; satin silver chassis/scoop/thumb-wheel panel, machined-steel wheels, dark-grey
"logi" print, black bottom plate and feet -- sampled from Logitech's MX Master 3S (for Mac)
Pale Grey product renders.

Source scan: Sketchfab "Mouse Logitech MX Master 3S white" by Guibazilla, CC BY 4.0.
"""
import bpy, bmesh, sys, os, math, time
import numpy as np
import mathutils
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

REPO = r"C:\Users\Vas\Documents\Github\Hub"
SRC = os.path.join(REPO, 'assets', 'source', 'mouse_mx_master_3s', 'mouse_logitech_mx_master_3s_white.glb')
BLEND = os.path.join(REPO, 'blender', 'scene', 'parts', 'mouse_mx.blend')
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
LENGTH, HEIGHT = 0.1249, 0.051          # Logitech spec (width 84.3 follows from the scan)
VOXEL = 0.00035
SHELL_TRIS = 17000                      # before the boundary cuts / booleans
a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
T0 = time.time()
def log(*m): print('[mx_refine %5.1fs]' % (time.time() - T0), *m, flush=True)
mm = 0.001

# ---------------------------------------------------------------- scan import (as v2_mouse_mx.py)
def import_aligned_scan():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=SRC)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    bm = bmesh.new()
    for o in meshes:
        t = o.data.copy(); t.transform(o.matrix_world); bm.from_mesh(t); bpy.data.meshes.remove(t)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    mats = [m for o in meshes for m in o.data.materials]
    for o in new: bpy.data.objects.remove(o, do_unlink=True)
    me = bpy.data.meshes.new('tmp_scan'); bm.to_mesh(me); bm.free()
    P = co(me)
    c = P.mean(0); w, V = np.linalg.eigh(np.cov((P - c).T)); up, length = V[:, 0], V[:, 2]
    h = (P - c) @ up
    if (h > h.max() - 0.003 * (h.max() - h.min()) * 10).sum() > (h < h.min() + 0.003 * (h.max() - h.min()) * 10).sum():
        up = -up; h = -h
    l = (P - c) @ length
    if h[l > 0].max() > h[l < 0].max(): length = -length
    side = np.cross(length, up)
    me.transform(Matrix((side, length, up)).to_4x4() @ Matrix.Translation(-Vector(c)))
    P = co(me); me.transform(Matrix.Scale(LENGTH / (P[:, 1].max() - P[:, 1].min()), 4))
    P = co(me); lo, hi = P.min(0), P.max(0)
    me.transform(Matrix.Translation(Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))))
    ob = bpy.data.objects.new('tmp_scan', me); bpy.context.scene.collection.objects.link(ob)
    return ob, mats

def co(me):
    P = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', P); return P.reshape(-1, 3)

def edges_np(me):
    E = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get('vertices', E); return E.reshape(-1, 2)

def taubin(P, E, it, lam=0.5, mu=-0.53):
    n = len(P); cnt = np.zeros(n); np.add.at(cnt, E[:, 0], 1); np.add.at(cnt, E[:, 1], 1); cnt = np.maximum(cnt, 1)[:, None]
    for _ in range(it):
        for f in (lam, mu):
            s = np.zeros_like(P); np.add.at(s, E[:, 0], P[E[:, 1]]); np.add.at(s, E[:, 1], P[E[:, 0]])
            P = P + f * (s / cnt - P)
    return P

def smooth_scalar(F, E, it, f=0.5):
    n = len(F); cnt = np.zeros(n); np.add.at(cnt, E[:, 0], 1); np.add.at(cnt, E[:, 1], 1); cnt = np.maximum(cnt, 1)
    for _ in range(it):
        s = np.zeros(n); np.add.at(s, E[:, 0], F[E[:, 1]]); np.add.at(s, E[:, 1], F[E[:, 0]])
        F = F + f * (s / cnt - F)
    return F

# ---------------------------------------------------------------- 2D region helpers (mm)
def sd_poly(Q, poly):
    """signed distance (mm, + inside) of points Q (N,2) to a closed polygon."""
    V = np.array(poly, float); A = V; B = np.roll(V, -1, 0)
    d = np.full(len(Q), 1e9); inside = np.zeros(len(Q), bool)
    for a_, b_ in zip(A, B):
        pa = Q - a_; ba = b_ - a_
        h = np.clip((pa @ ba) / (ba @ ba), 0, 1); d = np.minimum(d, np.linalg.norm(pa - h[:, None] * ba, axis=1))
        cond = ((a_[1] > Q[:, 1]) != (b_[1] > Q[:, 1]))
        xint = (b_[0] - a_[0]) * (Q[:, 1] - a_[1]) / (b_[1] - a_[1] + 1e-12) + a_[0]
        inside ^= cond & (Q[:, 0] < xint)
    return np.where(inside, d, -d)

def sd_rrect(Q, c, size, r, ang=0.0):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    d = Q - np.array(c); q = np.stack([d[:, 0] * ca + d[:, 1] * sa, -d[:, 0] * sa + d[:, 1] * ca], 1)
    q = np.abs(q) - (np.array(size) / 2 - r)
    return -(np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(np.maximum(q[:, 0], q[:, 1]), 0) - r)

# Region outlines, read off the scan texture (mm, aligned-scan frame).
SPLIT = [(6.3, 75), (6.6, 64), (7.4, 55), (8.2, 50.6)]
BTN_L = [(-45, 75)] + SPLIT + [(2.0, 50.6), (2.0, 20.5), (-17.5, 10.2), (-19.5, 9.5), (-19.5, 27), (-45, 34)]
BTN_R = SPLIT[::-1] + [(45, 75), (36.0, 64), (34.5, 58), (33.3, 52.5), (35.1, 10.2), (34.2, 9.6),
                       (16.2, 14.2), (15.4, 15.5), (15.4, 50.6)]
CEN = (9.0, -5.0)                       # body centre for the parting-line curve
MODE = dict(c=(9.8, 12.95), size=(5.6, 9.1), r=1.4)
# left side, (y, z) projection for x < -12 mm: silver scoop between shell edge and thumb-rest lip
SCOOP = [(75, 14), (64, 17.5), (58, 21), (52, 25.2), (46, 29), (40, 32), (32, 36), (24, 39.5), (16, 43), (10, 47),
         (4, 50.2), (-4, 52.6), (-12, 53.9), (-17, 53.4), (-20.5, 51.2), (-21.6, 48), (-20.4, 45.2),
         (-16, 43.4), (-8, 41.4), (0, 39.6), (6, 38.1), (12, 36.3), (18, 33.8), (23.5, 30.6), (25.4, 28),
         (25.6, 20), (24.4, 12), (22, 5), (20, -5), (75, -5)]
def chaikin(poly, it=3):
    P = np.array(poly, float)
    for _ in range(it):
        Q = np.roll(P, -1, 0); P = np.stack([0.75 * P + 0.25 * Q, 0.25 * P + 0.75 * Q], 1).reshape(-1, 2)
    return [tuple(p) for p in P]
SCOOP = chaikin(SCOOP)
SIDE_F = dict(c=(4.0, 35.0), size=(10.2, 3.3), r=1.3, ang=-11)
SIDE_R = dict(c=(-7.3, 37.3), size=(10.2, 3.6), r=1.4, ang=-16)

# ---------------------------------------------------------------- iso-line cutting
def bm_arrays(bm):
    bm.verts.index_update(); bm.verts.ensure_lookup_table(); bm.normal_update()
    P = np.array([v.co for v in bm.verts]) / mm
    N = np.array([v.normal for v in bm.verts])
    E = np.array([(e.verts[0].index, e.verts[1].index) for e in bm.edges], dtype=np.int64)
    return P, N, E

def iso_cut(bm, lay):
    """Cut the triangle mesh exactly along the zero line of vertex layer `lay`."""
    vals = [v[lay] for v in bm.verts]
    span = max(1e-9, max(abs(x) for x in vals))
    for v in bm.verts:                               # snap near-zero verts onto the line
        if abs(v[lay]) < 1e-6 * span: v[lay] = 0.0
    cross = []
    for e in bm.edges:
        a_, b_ = e.verts[0][lay], e.verts[1][lay]
        if a_ * b_ < 0:
            t = a_ / (a_ - b_)
            if t < 0.08: e.verts[0][lay] = 0.0          # avoid slivers: move the line onto the vert
            elif t > 0.92: e.verts[1][lay] = 0.0
            else: cross.append((e, t))
    newv = []
    for e, t in cross:
        v0, v1 = e.verts
        if v0[lay] == 0.0 or v1[lay] == 0.0: continue
        ne, nv = bmesh.utils.edge_split(e, v0, t)
        nv[lay] = 0.0; newv.append(nv)
    for f in list(bm.faces):
        z = [v for v in f.verts if v[lay] == 0.0]
        if len(z) == 2 and bm.edges.get(z) is None:
            if any(v[lay] > 0 for v in f.verts) and any(v[lay] < 0 for v in f.verts):
                try: bmesh.utils.face_split(f, z[0], z[1])
                except Exception: pass
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    return len(newv)

# ---------------------------------------------------------------- materials
def sock(node, name, kind='RGBA', out=False):
    return next(x for x in (node.outputs if out else node.inputs) if x.name == name and x.type == kind)

def srgb(*c): return tuple(((x / 255) / 12.92 if x / 255 <= 0.04045 else ((x / 255 + 0.055) / 1.055) ** 2.4) for x in c)

def new_mat(name, col, rough, metal=0.0, spec=0.5, coat=0.0, grain=0.03, groove=True, logo_img=None,
            rough_var=0.06, knurl=0, knurl_axis='X', sparkle=0.0):
    m = bpy.data.materials.get(name)
    if m: bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N_ = nt.nodes; L_ = nt.links
    bsdf = next(n for n in N_ if n.type == 'BSDF_PRINCIPLED'); bsdf.location = (400, 0)
    bsdf.inputs['Base Color'].default_value = (*col, 1)
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Specular IOR Level'].default_value = spec
    if coat: bsdf.inputs['Coat Weight'].default_value = coat; bsdf.inputs['Coat Roughness'].default_value = 0.25
    tc = N_.new('ShaderNodeTexCoord'); tc.location = (-1400, 0)
    # micro roughness variation
    nz = N_.new('ShaderNodeTexNoise'); nz.location = (-900, 200)
    nz.inputs['Scale'].default_value = 900.0; nz.inputs['Detail'].default_value = 3.0
    L_.new(tc.outputs['Object'], nz.inputs['Vector'])
    rr = N_.new('ShaderNodeMapRange'); rr.location = (-600, 200)
    rr.inputs['To Min'].default_value = rough - rough_var; rr.inputs['To Max'].default_value = rough + rough_var
    L_.new(nz.outputs['Fac'], rr.inputs['Value']); L_.new(rr.outputs['Result'], bsdf.inputs['Roughness'])
    # fine surface grain (moulded matte texture / satin paint)
    gr = N_.new('ShaderNodeTexNoise'); gr.location = (-900, -250)
    gr.inputs['Scale'].default_value = 9000.0 if not sparkle else 20000.0; gr.inputs['Detail'].default_value = 2.0
    L_.new(tc.outputs['Object'], gr.inputs['Vector'])
    height = gr.outputs['Fac']; strength = grain
    colour_out = bsdf.inputs['Base Color']
    col_src = None
    if knurl:
        # straight knurl ridges around the local axis
        axc = N_.new('ShaderNodeAttribute'); axc.attribute_name = 'axc'; axc.attribute_type = 'GEOMETRY'; axc.location = (-1400, -500)
        sep = N_.new('ShaderNodeSeparateXYZ'); sep.location = (-1200, -500); L_.new(axc.outputs['Vector'], sep.inputs[0])
        at = N_.new('ShaderNodeMath'); at.operation = 'ARCTAN2'; at.location = (-1000, -500)
        ax = {'X': ('Z', 'Y'), 'Z': ('Y', 'X')}[knurl_axis]
        L_.new(sep.outputs[ax[0]], at.inputs[0]); L_.new(sep.outputs[ax[1]], at.inputs[1])
        mul = N_.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = knurl; mul.location = (-850, -500)
        L_.new(at.outputs[0], mul.inputs[0])
        sn = N_.new('ShaderNodeMath'); sn.operation = 'SINE'; sn.location = (-700, -500); L_.new(mul.outputs[0], sn.inputs[0])
        ab = N_.new('ShaderNodeMath'); ab.operation = 'ABSOLUTE'; ab.location = (-550, -500); L_.new(sn.outputs[0], ab.inputs[0])
        # only on the rolling surface: attribute 'knurl' (1 on tread, 0 on faces / groove)
        ka = N_.new('ShaderNodeAttribute'); ka.attribute_name = 'knurl'; ka.attribute_type = 'GEOMETRY'; ka.location = (-700, -700)
        km = N_.new('ShaderNodeMath'); km.operation = 'MULTIPLY'; km.location = (-400, -550)
        L_.new(ab.outputs[0], km.inputs[0]); L_.new(ka.outputs['Fac'], km.inputs[1])
        height = km.outputs[0]; strength = 0.9
    bump = N_.new('ShaderNodeBump'); bump.location = (100, -300)
    bump.inputs['Strength'].default_value = strength; bump.inputs['Distance'].default_value = 0.0002 if knurl else 0.00005
    L_.new(height, bump.inputs['Height'])
    normal_out = bump.outputs['Normal']
    if groove:
        # 0.3 mm parting-line grooves from the per-vertex distance to the part boundaries (mm)
        sa = N_.new('ShaderNodeAttribute'); sa.attribute_name = 'seam'; sa.attribute_type = 'GEOMETRY'; sa.location = (-900, -900)
        gm = N_.new('ShaderNodeMapRange'); gm.location = (-650, -900); gm.interpolation_type = 'SMOOTHSTEP'
        gm.inputs['From Min'].default_value = 0.08; gm.inputs['From Max'].default_value = 0.22
        gm.inputs['To Min'].default_value = 1.0; gm.inputs['To Max'].default_value = 0.0
        L_.new(sa.outputs['Fac'], gm.inputs['Value'])
        sh = N_.new('ShaderNodeMapRange'); sh.location = (-650, -1150); sh.interpolation_type = 'SMOOTHSTEP'
        sh.inputs['From Min'].default_value = 0.0; sh.inputs['From Max'].default_value = 0.9
        sh.inputs['To Min'].default_value = 1.0; sh.inputs['To Max'].default_value = 0.0
        L_.new(sa.outputs['Fac'], sh.inputs['Value'])
        b2 = N_.new('ShaderNodeBump'); b2.location = (250, -500); b2.invert = True
        b2.inputs['Strength'].default_value = 1.0; b2.inputs['Distance'].default_value = 0.00025
        L_.new(gm.outputs['Result'], b2.inputs['Height']); L_.new(bump.outputs['Normal'], b2.inputs['Normal'])
        normal_out = b2.outputs['Normal']
        # darken inside the groove (+ slight ambient falloff next to it)
        mx = N_.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.location = (150, 150)
        sock(mx, 'A').default_value = (*col, 1); sock(mx, 'B').default_value = (col[0] * 0.28, col[1] * 0.28, col[2] * 0.29, 1)
        f1 = N_.new('ShaderNodeMath'); f1.operation = 'MULTIPLY_ADD'; f1.location = (-400, -1000)
        f1.inputs[1].default_value = 0.12
        L_.new(sh.outputs['Result'], f1.inputs[0]); L_.new(gm.outputs['Result'], f1.inputs[2])
        cl = N_.new('ShaderNodeClamp'); cl.location = (-250, -1000); L_.new(f1.outputs[0], cl.inputs[0])
        L_.new(cl.outputs[0], sock(mx, 'Factor', 'VALUE'))
        col_src = mx
    if logo_img is not None:
        uv = N_.new('ShaderNodeUVMap'); uv.uv_map = 'LogoUV'; uv.location = (-900, 600)
        ti = N_.new('ShaderNodeTexImage'); ti.image = logo_img; ti.extension = 'CLIP'; ti.location = (-650, 600)
        ti.interpolation = 'Cubic'; ti.image.colorspace_settings.name = 'Non-Color'
        L_.new(uv.outputs['UV'], ti.inputs['Vector'])
        m2 = N_.new('ShaderNodeMix'); m2.data_type = 'RGBA'; m2.location = (300, 300)
        sock(m2, 'B').default_value = (*srgb(112, 114, 117), 1)
        if col_src: L_.new(sock(col_src, 'Result', out=True), sock(m2, 'A'))
        else: sock(m2, 'A').default_value = (*col, 1)
        L_.new(ti.outputs['Color'], sock(m2, 'Factor', 'VALUE'))
        col_src = m2
    if col_src: L_.new(sock(col_src, 'Result', out=True), bsdf.inputs['Base Color'])
    L_.new(normal_out, bsdf.inputs['Normal'])
    return m

# ---------------------------------------------------------------- small mesh builders
def lathe(profile, segs, name, knurl_rng=None):
    """profile: [(axial_mm, radius_mm)] from one axle end to the other, around local X."""
    bm = bmesh.new(); rings = []
    kl = bm.verts.layers.float.new('knurl')
    for (x, r) in profile:
        if r < 1e-6:
            v = bm.verts.new((x * mm, 0, 0)); rings.append([v] * segs)
        else:
            ring = []
            for i in range(segs):
                t = 2 * math.pi * i / segs
                v = bm.verts.new((x * mm, r * mm * math.cos(t), r * mm * math.sin(t))); ring.append(v)
            rings.append(ring)
        for v in set(rings[-1]):
            v[kl] = 1.0 if (knurl_rng and any(lo <= x <= hi for lo, hi in knurl_rng) and r > 0) else 0.0
    for ra, rb in zip(rings[:-1], rings[1:]):
        for i in range(segs):
            j = (i + 1) % segs
            vs = [ra[i], ra[j], rb[j], rb[i]]
            uniq = []
            for v in vs:
                if v not in uniq: uniq.append(v)
            if len(uniq) >= 3: bm.faces.new(uniq)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ax = me.attributes.new('axc', 'FLOAT_VECTOR', 'POINT')
    ax.data.foreach_set('vector', (co(me) / mm).ravel().astype(np.float32))
    for p in me.polygons: p.use_smooth = True
    return me

def rrect_prism(name, w, l, r, h, segs=8):
    """rounded rectangle (w along X, l along Y, corner r) extruded h along +Z from z=0 (mm)."""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, l / 2 - r, 0), (-w / 2 + r, l / 2 - r, 90), (-w / 2 + r, -l / 2 + r, 180), (w / 2 - r, -l / 2 + r, 270)):
        for i in range(segs + 1):
            t = math.radians(a0 + 90 * i / segs); pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        # straight side to the next corner, split every ~3 mm (lets the part follow a curved base)
        nx_, ny_ = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[a0]
        L = (w - 2 * r) if a0 in (0, 180) else (l - 2 * r)
        k = int(L // 3)
        ex, ey = pts[-1]
        for j in range(1, k + 1):
            pts.append((ex + nx_ * L * j / (k + 1), ey + ny_ * L * j / (k + 1)))
    bm = bmesh.new()
    bot = [bm.verts.new((x * mm, y * mm, 0)) for x, y in pts]
    top = [bm.verts.new((x * mm, y * mm, h * mm)) for x, y in pts]
    bm.faces.new(top); bm.faces.new(bot[::-1])
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n; bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.triangulate(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return me

def frame(xaxis, zaxis, origin):
    x = Vector(xaxis).normalized(); z = Vector(zaxis); z = (z - z.dot(x) * x).normalized(); y = z.cross(x)
    M = Matrix((x, y, z)).transposed().to_4x4(); M.translation = Vector(origin); return M

# ---------------------------------------------------------------- logo mask (monoline "logi")
def logo_image():
    W = 0.50
    L = dict(lb=0.25, lt=3.85, ou=2.0, cv=1.2, r=0.95, gu=4.85, gd=0.0, ga=0.85, iu=6.95, it=2.2, dv=3.45, dr=0.34)
    U0, U1, V0, V1 = -0.6, 7.8, -1.6, 4.2
    res = 96                                   # px / mm
    nx, ny = int((U1 - U0) * res), int((V1 - V0) * res)
    uu, vv = np.meshgrid(np.linspace(U0, U1, nx), np.linspace(V0, V1, ny))
    P = np.stack([uu, vv], -1).reshape(-1, 2)
    def seg(a_, b_):
        a_ = np.array(a_); b_ = np.array(b_); pa = P - a_; ba = b_ - a_
        h = np.clip((pa @ ba) / (ba @ ba), 0, 1); return np.linalg.norm(pa - h[:, None] * ba, axis=1)
    def ring(c, r): return np.abs(np.linalg.norm(P - np.array(c), axis=1) - r)
    def arc(c, r, a0, a1):
        d = P - np.array(c); ang = np.arctan2(d[:, 1], d[:, 0])
        e0 = np.array(c) + r * np.array([math.cos(a0), math.sin(a0)]); e1 = np.array(c) + r * np.array([math.cos(a1), math.sin(a1)])
        return np.where((ang >= a0) & (ang <= a1), ring(c, r), np.minimum(np.linalg.norm(P - e0, axis=1), np.linalg.norm(P - e1, axis=1)))
    d = seg((0, L['lb']), (0, L['lt']))
    d = np.minimum(d, ring((L['ou'], L['cv']), L['r']))
    d = np.minimum(d, ring((L['gu'], L['cv']), L['r']))
    d = np.minimum(d, seg((L['gu'] + L['r'], L['cv']), (L['gu'] + L['r'], L['gd'])))
    d = np.minimum(d, arc((L['gu'], L['gd']), L['r'], -math.pi * L['ga'], 0))
    d = np.minimum(d, seg((L['iu'], L['lb']), (L['iu'], L['it'])))
    d = d - W / 2
    d = np.minimum(d, np.linalg.norm(P - np.array([L['iu'], L['dv']]), axis=1) - L['dr'])
    m = np.clip(0.5 - d * res / 1.5, 0, 1).reshape(ny, nx)
    img = bpy.data.images.get('MX_logo_mask')
    if img: bpy.data.images.remove(img)
    img = bpy.data.images.new('MX_logo_mask', nx, ny, alpha=False, float_buffer=False)
    px = np.ones((ny, nx, 4), np.float32); px[..., 0] = px[..., 1] = px[..., 2] = m
    img.pixels.foreach_set(px.ravel()); img.pack()
    return img, (U0, U1, V0, V1)

# ======================================================================== build
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
col = bpy.data.collections['NEW_mouse_mx']
root = bpy.data.objects['NEW_mouse_mx_root']
root_mw = root.matrix_world.copy()
for o in list(col.objects):
    if o is not root: bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
    for d in list(coll):
        if d.users == 0: coll.remove(d)

scan, scan_mats = import_aligned_scan()
log('scan', len(scan.data.polygons), 'tris')

# --- 1. voxel remesh + Taubin smoothing -> clean moulded surface
r = scan.modifiers.new('r', 'REMESH'); r.mode = 'VOXEL'; r.voxel_size = VOXEL; r.adaptivity = 0
dense = bpy.data.meshes.new_from_object(scan.evaluated_get(bpy.context.evaluated_depsgraph_get()))
scan.modifiers.remove(r)
E = edges_np(dense); P = taubin(co(dense), E, 45)
# flat base: the scan's underside is lumpy (feet, label plate) -> one plane 0.9 mm up
zf = 0.9 * mm
P[:, 2] = np.maximum(P[:, 2], zf)
dense.vertices.foreach_set('co', P.ravel()); dense.update()
log('remesh', len(dense.vertices), 'verts')
shell = bpy.data.objects.new('MouseMX_Shell', dense); sc.collection.objects.link(shell)
bvh_dense = BVHTree.FromObject(shell, bpy.context.evaluated_depsgraph_get())
# The scoop outline was traced looking along +X; its upper part lies on surface that turns to face
# up-left, so re-express the outline in a frame looking along that surface's normal (better conditioned).
N0 = np.array([-0.8, 0.0, 0.6]); T0v = np.array([0.6, 0.0, 0.8])
def scoop_frame(Q): return np.stack([Q[:, 1], Q @ T0v], 1)
_pts = []
for (yy, zz) in SCOOP:
    hit = bvh_dense.ray_cast(Vector((-0.2, yy * mm, zz * mm)), Vector((1, 0, 0)))[0]
    _pts.append(np.array(hit) / mm if hit is not None else np.array([-30.0, yy, zz]))
SCOOP_T = [tuple(q) for q in scoop_frame(np.array(_pts))]

# --- 2. decimate
tris = sum(len(p.vertices) - 2 for p in dense.polygons)
d = shell.modifiers.new('d', 'DECIMATE'); d.ratio = SHELL_TRIS / tris; d.use_collapse_triangulate = True
me = bpy.data.meshes.new_from_object(shell.evaluated_get(bpy.context.evaluated_depsgraph_get()))
shell.modifiers.remove(d); shell.data = me; bpy.data.meshes.remove(dense)
log('decimated', len(me.polygons), 'tris')

# --- 3. part boundaries as exact iso-line cuts
# Every boundary is a scalar field (mm, + inside) stored as a vertex layer, so edge splits
# interpolate all fields; each field is then cut exactly along its zero line.
bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces)

def f_silver(P, N, E):
    # chassis parting line: where the body turns under (normal pointing down), measured all round,
    # then turned into one smooth height-vs-angle curve so the line reads as a moulded edge
    raw = smooth_scalar(-N[:, 2] - 0.30, E, 40)
    fa, fb = raw[E[:, 0]], raw[E[:, 1]]
    xe = (fa * fb < 0) & (P[E[:, 0], 2] < 24) & (P[E[:, 1], 2] < 24)
    t = fa[xe] / (fa[xe] - fb[xe]); X = P[E[xe, 0]] + t[:, None] * (P[E[xe, 1]] - P[E[xe, 0]])
    X = X[~((X[:, 0] < -12) & (X[:, 1] > 20))]                   # left-front belongs to the scoop
    nb = 72; ang = lambda Q: np.arctan2(Q[:, 1] - CEN[1], Q[:, 0] - CEN[0])
    bins = ((ang(X) + np.pi) / (2 * np.pi) * nb).astype(int) % nb
    H = np.full(nb, np.nan)
    for i in range(nb):
        zz = X[bins == i, 2]
        if len(zz): H[i] = max(5.0, np.percentile(zz, 60))
    ok = ~np.isnan(H); idx = np.arange(nb)
    H = np.interp(idx, idx[ok], H[ok], period=nb)
    k = np.exp(-0.5 * (np.arange(-6, 7) / 2.2) ** 2); k /= k.sum()
    H = np.convolve(np.concatenate([H[-6:], H, H[:6]]), k, 'valid')
    th = (ang(P) + np.pi) / (2 * np.pi) * nb
    Hv = np.interp(th, np.arange(nb) + 0.5, H, period=nb)
    rim = Hv - P[:, 2]
    rim = np.maximum(rim, 2.0 * (zf / mm + 0.25 - P[:, 2]))       # flat base
    scoop = np.minimum(sd_poly(scoop_frame(P), SCOOP_T), -12.0 - P[:, 0])
    side = np.maximum(sd_rrect(P[:, [1, 2]], **SIDE_F), sd_rrect(P[:, [1, 2]], **SIDE_R))
    side = np.minimum(side, -15.0 - P[:, 0])
    scoop = np.clip(scoop, -4, 4); scoop = smooth_scalar(scoop, E, 10, 0.5)   # calm the projected outline
    f = np.maximum(rim, scoop)
    return np.minimum(f, -side)

FIELDS = {
    'silver': f_silver,
    'btnL': lambda P, N, E: sd_poly(P[:, [0, 1]], BTN_L),
    'btnR': lambda P, N, E: sd_poly(P[:, [0, 1]], BTN_R),
    'mode': lambda P, N, E: sd_rrect(P[:, [0, 1]], **MODE),
    'sideF': lambda P, N, E: np.minimum(sd_rrect(P[:, [1, 2]], **SIDE_F), -15.0 - P[:, 0]),
    'sideR': lambda P, N, E: np.minimum(sd_rrect(P[:, [1, 2]], **SIDE_R), -15.0 - P[:, 0]),
}
P_, N_, E_ = bm_arrays(bm)
layers = {}
for name, fn in FIELDS.items():
    lay = bm.verts.layers.float.new('f_' + name); layers[name] = lay
    vals = fn(P_, N_, E_)
    for v in bm.verts: v[lay] = float(vals[v.index])
for name in FIELDS:
    iso_cut(bm, layers[name])
bm.verts.index_update(); bm.faces.index_update(); bm.normal_update()
bm.faces.ensure_lookup_table()
PART = {'shell': 0, 'silver': 1, 'btnL': 2, 'btnR': 3, 'mode': 4, 'sideF': 5, 'sideR': 6, 'base': 7}
def fmean(f, name): return sum(v[layers[name]] for v in f.verts) / len(f.verts)
labels = []
for f in bm.faces:
    lab = 'shell'
    if fmean(f, 'sideF') > 0: lab = 'sideF'
    elif fmean(f, 'sideR') > 0: lab = 'sideR'
    elif fmean(f, 'silver') > 0:
        fz = max(v.co.z for v in f.verts) / mm
        lab = 'base' if (fz < zf / mm + 0.3 and f.normal.z < -0.9) else 'silver'
    elif fmean(f, 'mode') > 0: lab = 'mode'
    elif fmean(f, 'btnL') > 0: lab = 'btnL'
    elif fmean(f, 'btnR') > 0: lab = 'btnR'
    labels.append(PART[lab])
labels = np.array(labels)
# drop tiny islands of a label (< 12 faces) into their surroundings
for _ in range(2):
    for f in bm.faces:
        l0 = labels[f.index]
        nb = [labels[g.index] for e in f.edges for g in e.link_faces if g is not f]
        if nb and sum(1 for x in nb if x == l0) == 0:
            labels[f.index] = max(set(nb), key=nb.count)
log('labels', {k: int((labels == v).sum()) for k, v in PART.items()})

# --- 4. seam distance (mm) per vertex: distance to edges between different parts
def seam_group(l): return 1 if l in (1, 7) else l       # silver chassis and flat base = one part
seam_edges = []
for e in bm.edges:
    if len(e.link_faces) == 2:
        a_, b_ = e.link_faces
        if seam_group(labels[a_.index]) != seam_group(labels[b_.index]): seam_edges.append(e)
kd = mathutils.kdtree.KDTree(len(seam_edges))
for i, e in enumerate(seam_edges): kd.insert((e.verts[0].co + e.verts[1].co) / 2, i)
kd.balance()
seam = np.full(len(bm.verts), 5.0)
for v in bm.verts:
    best = 5.0
    for (_, i, _) in kd.find_range(v.co, 5.0 * mm):
        e = seam_edges[i]
        p, t = mathutils.geometry.intersect_point_line(v.co, e.verts[0].co, e.verts[1].co)
        t = min(1, max(0, t)); q = e.verts[0].co.lerp(e.verts[1].co, t)
        best = min(best, (v.co - q).length / mm)
    seam[v.index] = best
log('seam edges', len(seam_edges))

# side buttons stand 0.35 mm proud of the thumb rest, ramping up just inside their outline
for v in bm.verts:
    fs = max(v[layers['sideF']], v[layers['sideR']])
    if fs > 0: v.co += v.normal * (0.35 * mm * min(1.0, fs / 0.6))
MAT_OF = {0: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 1: 1, 7: 2}           # 0 pale, 1 silver, 2 base
for f in bm.faces: f.material_index = MAT_OF[int(labels[f.index])]
bm.to_mesh(me); bm.free()
a_ = me.attributes.new('seam', 'FLOAT', 'POINT'); a_.data.foreach_set('value', seam.astype(np.float32))
pa = me.attributes.new('part', 'INT', 'FACE'); pa.data.foreach_set('value', labels.astype(np.int32))

# --- 5. materials
PALE = srgb(232, 233, 235)          # Logitech "Pale Gray" swatch 236/237/239, a touch down for albedo
SILVER = srgb(142, 144, 149)
logo_img, logo_rect = logo_image()
m_pale = new_mat('MX_PaleGrey', PALE, 0.52, spec=0.45, grain=0.04, logo_img=logo_img)
m_silver = new_mat('MX_SatinSilver', SILVER, 0.36, metal=0.4, grain=0.02, sparkle=1.0)
m_base = new_mat('MX_BaseSilver', srgb(160, 162, 166), 0.5, metal=0.5, grain=0.02)
m_dark = new_mat('MX_WellDark', srgb(58, 59, 61), 0.6, groove=False)
m_steel = new_mat('MX_Steel', srgb(205, 206, 208), 0.26, metal=1.0, groove=False, knurl=90, grain=0.01)
m_steel_t = new_mat('MX_Steel_Thumb', srgb(200, 201, 203), 0.28, metal=1.0, groove=False, knurl=40, grain=0.01)
m_black = new_mat('MX_BlackPlastic', srgb(24, 24, 25), 0.55, groove=False)
m_feet = new_mat('MX_Feet', srgb(20, 20, 21), 0.32, groove=False, grain=0.0)
for m in (m_pale, m_silver, m_base): me.materials.append(m)
me.materials.append(m_dark)                                        # index 3: boolean walls

# --- 6. rebuilt wheels + booleans (positions from the smoothed scan surface)
def ray(o, dvec):
    loc, n, i, dist = bvh_dense.ray_cast(Vector(o) * mm, Vector(dvec).normalized())
    return (loc, n) if loc else (None, None)

# scroll wheel: 7.2 mm wide steel wheel in a 8.2 x 18.5 mm well between the buttons
WX, WY = 9.4, 36.3
hs = [ray((x, WY + dy, 80), (0, 0, -1))[0].z / mm for x in (3.2, 15.0) for dy in (-6, 0, 6)]
zs = sum(hs) / len(hs)
R_W = 11.5
wheel_c = Vector((WX, WY, zs + 3.8 - R_W)) * mm
prof = [(-3.6, 0), (-3.6, R_W - 1.2), (-3.55, R_W - 0.5), (-3.35, R_W - 0.12), (-3.1, R_W), (-0.55, R_W),
        (-0.4, R_W - 0.3), (0.4, R_W - 0.3), (0.55, R_W), (3.1, R_W), (3.35, R_W - 0.12), (3.55, R_W - 0.5),
        (3.6, R_W - 1.2), (3.6, 0)]
wme = lathe(prof, 72, 'MouseMX_ScrollWheel', knurl_rng=[(-3.1, -0.55), (0.55, 3.1)])
wheel = bpy.data.objects.new('MouseMX_ScrollWheel', wme); wme.materials.append(m_steel)
wheel.matrix_world = Matrix.Translation(wheel_c)
well = rrect_prism('tmp_well', 8.2, 18.6, 1.2, 30.0)
wobj = bpy.data.objects.new('tmp_well', well); wobj.location = (WX * mm, (27.0 + 45.6) / 2 * mm, (zs - 10) * mm)
well.materials.append(m_dark)

# thumb wheel: twin knurled drums on an axle rising ~20 deg to the rear, under the shell edge
pa_, na_ = ray((-80, 8.0, 42.3), (1, 0, 0)); pb_, nb_ = ray((-80, -6.2, 47.0), (1, 0, 0))
pc_, nc_ = ray((-80, 0.9, 44.7), (1, 0, 0))
axis = (pb_ - pa_).normalized()
nrm = (-(nc_)); nrm = (nrm - nrm.dot(axis) * axis).normalized()   # into the body
R_T = 6.0
tw_c = pc_ + nrm * (R_T * mm - 0.3 * mm)
tprof = [(-7.0, 0), (-7.0, R_T - 0.6), (-6.85, R_T - 0.15), (-6.6, R_T), (-0.85, R_T), (-0.7, R_T - 0.2),
         (-0.55, R_T - 0.9), (0.55, R_T - 0.9), (0.7, R_T - 0.2), (0.85, R_T), (6.6, R_T), (6.85, R_T - 0.15),
         (7.0, R_T - 0.6), (7.0, 0)]
tme = lathe(tprof, 48, 'MouseMX_ThumbWheel', knurl_rng=[(-6.6, -0.85), (0.85, 6.6)])
thumb = bpy.data.objects.new('MouseMX_ThumbWheel', tme); tme.materials.append(m_steel_t)
thumb.matrix_world = frame(axis, -nrm, tw_c)
slot = rrect_prism('tmp_slot', 15.4, 11.2, 1.0, 16.0)
sobj = bpy.data.objects.new('tmp_slot', slot); slot.materials.append(m_dark)
# slot frame: X along the axle, Z out of the body, box from 10 mm inside to 6 mm outside
Ms = frame(axis, -nrm, pc_); sobj.matrix_world = Ms @ Matrix.Translation((0, 0, -10 * mm))
# slot box is built along X=w(15.4) Y=l(11.2): X = axle, Y = around-wheel direction
for o in (wheel, wobj, thumb, sobj): sc.collection.objects.link(o)

for cutter in (wobj, sobj):
    at = cutter.data.attributes.new('seam', 'FLOAT', 'POINT'); at.data.foreach_set('value', [5.0] * len(cutter.data.vertices))
    b = shell.modifiers.new('bool', 'BOOLEAN'); b.operation = 'DIFFERENCE'; b.solver = 'EXACT'
    b.object = cutter; b.material_mode = 'TRANSFER'
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.modifier_apply(modifier='bool')
for o in (wobj, sobj): bpy.data.objects.remove(o, do_unlink=True)
me = shell.data
# boolean walls: no groove
sv = me.attributes['seam']
log('after booleans', len(me.polygons), 'tris')

# --- 7. logo UV (planar projection onto the left button)
Cc = Vector((-9.5, 17.5, 45.55)) * mm
Rr = Vector((0.99997, 0.0, -0.0076)); Uu = Vector((-0.00326, 0.9035, -0.42856))
th = math.radians(18)
O3 = Cc + (-2.88 * mm) * Rr + (-1.72 * mm) * Uu
Bd = (math.cos(th) * Rr + math.sin(th) * Uu).normalized(); Ud = (-math.sin(th) * Rr + math.cos(th) * Uu).normalized()
U0, U1, V0, V1 = logo_rect
uvl = me.uv_layers.get('LogoUV') or me.uv_layers.new(name='LogoUV')
lv = [me.vertices[l.vertex_index].co for l in me.loops]
uvs = np.empty(len(me.loops) * 2)
for i, p in enumerate(lv):
    dv = p - O3; uvs[2 * i] = ((dv.dot(Bd) / mm) - U0) / (U1 - U0); uvs[2 * i + 1] = ((dv.dot(Ud) / mm) - V0) / (V1 - V0)
# only the upper left-button faces carry the logo (avoid projecting through to the underside)
uvl.data.foreach_set('uv', uvs)
for p in me.polygons:
    if p.normal.dot(Vector((0.0069, 0.4286, 0.9035))) < 0.5 or p.center.z < 35 * mm:
        for li in p.loop_indices: uvl.data[li].uv = (-1, -1)
for p in me.polygons: p.use_smooth = True
me.set_sharp_from_angle(angle=math.radians(48))

# --- 8. underside: black label plate, two feet; USB-C port at the nose
def place(me_, name, mat, M):
    ob = bpy.data.objects.new(name, me_); me_.materials.append(mat); ob.matrix_world = M
    sc.collection.objects.link(ob); return ob
plate = place(rrect_prism('MouseMX_BasePlate', 25.2, 93.0, 9.0, 0.3), 'MouseMX_BasePlate', m_black,
              Matrix.Translation(Vector((9.1, -1.75, 0.9 - 0.15)) * mm))
footL = place(rrect_prism('MouseMX_FootL', 9.8, 38.5, 4.4, 0.8), 'MouseMX_FootL', m_feet,
              Matrix.Translation(Vector((-28.0, -15.0, 0.9 - 0.45)) * mm))
footR = place(rrect_prism('MouseMX_FootR', 8.2, 40.0, 4.0, 0.8), 'MouseMX_FootR', m_feet,
              Matrix.Translation(Vector((34.6, -14.0, 0.9 - 0.45)) * mm))
def conform(ob, below, above):
    """drape a flat underside part onto the (partly curved) base: bottom face `below` mm under it."""
    for v in ob.data.vertices:
        w_ = ob.matrix_world @ v.co
        hit = bvh_dense.ray_cast(Vector((w_.x, w_.y, -0.01)), Vector((0, 0, 1)))[0]
        zs_ = hit.z if hit is not None else zf
        v.co = ob.matrix_world.inverted() @ Vector((w_.x, w_.y, zs_ + (above if v.co.z > 1e-6 else -below) * mm))
for ob_, b_, a_ in ((plate, 0.5, 0.2), (footL, 0.45, 0.35), (footR, 0.45, 0.35)): conform(ob_, b_, a_)
pu, nu = ray((7.0, 90, 9.5), (0, -1, 0))
usb = place(rrect_prism('MouseMX_USBC', 8.6, 2.7, 1.3, 2.0, segs=6), 'MouseMX_USBC', m_black,
            frame(Vector((1, 0, 0)), Vector(nu), pu) @ Matrix.Translation((0, 0, -1.9 * mm)))
# rrect_prism: w along X, l along Y, extruded +Z; in the port frame Z = outward surface normal

# --- 9. scale to Logitech's 51 mm height (feet bottom on z = 0), parent, tidy
objs = [shell, wheel, thumb, plate, footL, footR, usb]
bpy.data.objects.remove(scan, do_unlink=True)
for m in list(bpy.data.meshes):
    if m.users == 0: bpy.data.meshes.remove(m)
zmin = min((o.matrix_world @ v.co).z for o in (footL, footR) for v in o.data.vertices)
zmax = max((shell.matrix_world @ v.co).z for v in shell.data.vertices)
S = Matrix.Diagonal((1, 1, HEIGHT / (zmax - zmin), 1)) @ Matrix.Translation((0, 0, -zmin))
for o in objs:
    o.data.transform(S @ o.matrix_world); o.matrix_world = Matrix.Identity(4)
for o in objs:
    for uc in list(o.users_collection): uc.objects.unlink(o)
    col.objects.link(o)
    mw = o.matrix_world.copy(); o.parent = root; o.matrix_parent_inverse = root_mw.inverted(); o.matrix_world = root_mw @ mw
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
    for d_ in list(coll):
        if d_.users == 0: coll.remove(d_)

def tri_count(o): return sum(len(p.vertices) - 2 for p in o.data.polygons)
P = np.array([(o.matrix_world @ v.co)[:] for o in objs for v in o.data.vertices])
dims = (P.max(0) - P.min(0)) / mm
log('TRIS', {o.name: tri_count(o) for o in objs}, 'total', sum(tri_count(o) for o in objs))
log('DIMS mm', dims.round(1))
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
log('saved', BLEND)

# ---------------------------------------------------------------- previews
if '--render' in a:
    p = bpy.context.preferences.addons['cycles'].preferences
    p.compute_device_type = 'CUDA'; p.refresh_devices()
    for dv in p.devices: dv.use = (dv.type == 'CUDA')
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'GPU'; sc.cycles.samples = 64
    sc.cycles.use_denoising = True; sc.cycles.denoiser = 'OPTIX'
    sc.render.resolution_x, sc.render.resolution_y = 1280, 800
    sc.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new('mx_prev_world'); sc.world = w; w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.18, 0.18, 0.18, 1); bg.inputs['Strength'].default_value = 0.35
    ground = bpy.data.objects.new('mx_prev_ground', bpy.data.meshes.new('g'))
    gb = bmesh.new(); bmesh.ops.create_grid(gb, x_segments=1, y_segments=1, size=0.6); gb.to_mesh(ground.data); gb.free()
    gm = bpy.data.materials.new('mx_prev_ground'); gm.use_nodes = True
    gbs = next(n for n in gm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    gbs.inputs['Base Color'].default_value = (0.05, 0.05, 0.055, 1); gbs.inputs['Roughness'].default_value = 0.7
    ground.data.materials.append(gm); sc.collection.objects.link(ground)
    ground.matrix_world = root_mw
    ctr = root_mw @ Vector((0, 0, 0.025))
    def light(name, loc, energy, size):
        ld = bpy.data.lights.new(name, 'AREA'); ld.energy = energy; ld.size = size
        lo = bpy.data.objects.new(name, ld); sc.collection.objects.link(lo)
        lo.location = root_mw @ Vector(loc); lo.rotation_euler = (ctr - lo.location).to_track_quat('-Z', 'Y').to_euler()
    light('key', (-0.35, 0.25, 0.45), 9, 0.35); light('fill', (0.4, 0.2, 0.25), 3.5, 0.5); light('rim', (0.05, -0.45, 0.3), 6, 0.3)
    cd = bpy.data.cameras.new('mx_prev_cam'); cam = bpy.data.objects.new('mx_prev_cam', cd); sc.collection.objects.link(cam); sc.camera = cam
    for tag, loc, lens in (('top', (0.0, 0.0, 0.55), 85), ('front34', (0.2, 0.3, 0.2), 70), ('left', (-0.38, 0.0, 0.1), 70)):
        cd.lens = lens
        cam.location = root_mw @ Vector(loc)
        up = 'Y'
        q = (ctr - cam.location).to_track_quat('-Z', up)
        cam.rotation_euler = q.to_euler()
        if tag == 'top':
            cam.rotation_euler = (root_mw.to_3x3() @ Matrix.Identity(3)).to_euler()
        sc.render.filepath = os.path.join(PARTS, f'mouse_mx_{tag}.png')
        bpy.ops.render.render(write_still=True)
        log('rendered', tag)
