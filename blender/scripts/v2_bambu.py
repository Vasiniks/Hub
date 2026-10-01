"""
v2_bambu.py -- Bambu Lab A1 (full-size bed slinger) printing a 3DBenchy, on a small white side table
against the window wall, a little out of the left-wall / window-wall corner.

    blender -b --factory-startup --python blender/scripts/v2_bambu.py -- [--no-render] [--only=34,benchy,table,screen]

Reference (verified): A1 overall 385 x 410 x 430 mm (W x D x H, frame without the spool), build volume
256^3, 3.5" touchscreen. Photos (Wikimedia Commons, "3D (54252952383)", "(54253145195)", JD Mall showroom
R12S 09): two silver anodised Z towers joined by a top beam; silver X extrusion with a steel linear rail,
reaching past the left tower (cutter/wiper block) and ending in a white X-motor box in front of the right
tower; white boxy toolhead with a round front element, black lower hotend area and a white upper neck
taking the PTFE tube and the black umbilical; white rounded base with a dark foot band, dot speaker grille
and a tablet-style screen on a stalk at the front right, tilted up; textured gold PEI plate on a dark
heatbed close above the base; black braided bed cable loop at the rear; spool on a white bracket on top
of the right tower. Assumed: exact proportions, the spool axis running left-right (owner request).

Printer local frame: mm, origin = centre of the footprint at the table top, front faces -Y (toward the
seated viewer). Everything is built in room coordinates.
Output: blender/scene/parts/bambu.blend  (collection NEW_bambu, root NEW_bambu_root) + previews.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector as V, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT = os.path.join(PARTS, 'bambu.blend')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
ONLY = next((a.split('=')[1].split(',') for a in ARGS if a.startswith('--only=')), None)

# ------------------------------------------------------------------ placement (room metres)
# table moved 0.25 m out of the corner toward +X: clear of the book rack (x<=-1.878), the curtain
# (y>=1.149), the desk's left end (x=-1.04) and the floor register (x<=-1.876)
TABLE_X = (-1.800, -1.240)
TABLE_Y = (0.660, 1.130)
TABLE_H = 0.648                      # 72 cm lowered by 10 %
PX, PY, PZ = -1.520, 0.870, TABLE_H  # printer footprint centre
TOOL_X = -8.0                        # nozzle x (printer local mm)
NOZ_Y = -45.0                        # nozzle y: fixed by the X gantry position
BED_TOP = 78.0                       # PEI surface height above the table
BENCHY_H = 24.0                      # half of the 48 mm 3DBenchy

# ------------------------------------------------------------------ scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = bpy.data.collections.new('NEW_bambu')
scene.collection.children.link(coll)
root = bpy.data.objects.new('NEW_bambu_root', None)
root.location = (PX, PY, 0.0)
coll.objects.link(root)
OBJS = []


def P(x, y, z):
    """printer-local mm -> room metres"""
    return V((PX + x / 1000.0, PY + y / 1000.0, PZ + z / 1000.0))


def srgb(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# ------------------------------------------------------------------ materials
MATS = {}


def mat(name, col, rough, metal=0.0, bump=0.0, bscale=900.0, coat=0.0, emit=None, trans=0.0, aniso=0.0):
    m = bpy.data.materials.new('bambu_' + name)
    m.use_nodes = True
    N = m.node_tree.nodes
    L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    c = srgb(col)
    bs.inputs['Base Color'].default_value = (*c, 1)
    bs.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*c, 1)
    if coat:
        bs.inputs['Coat Weight'].default_value = coat
        bs.inputs['Coat Roughness'].default_value = 0.05
    if trans:
        bs.inputs['Transmission Weight'].default_value = trans
        bs.inputs['IOR'].default_value = 1.35
    if aniso:
        bs.inputs['Anisotropic'].default_value = aniso
    if emit:
        bs.inputs['Emission Color'].default_value = (*srgb(emit[0]), 1)
        bs.inputs['Emission Strength'].default_value = emit[1]
    tc = N.new('ShaderNodeTexCoord')
    nz = N.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 60.0
    nz.inputs['Detail'].default_value = 3.0
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = rough * 0.88
    mr.inputs['To Max'].default_value = min(1.0, rough * 1.12)
    L.new(nz.outputs['Fac'], mr.inputs['Value'])
    L.new(mr.outputs['Result'], bs.inputs['Roughness'])
    if bump:
        fn = N.new('ShaderNodeTexNoise')
        fn.inputs['Scale'].default_value = bscale
        fn.inputs['Detail'].default_value = 2.0
        L.new(tc.outputs['Object'], fn.inputs['Vector'])
        bp = N.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = 0.0002
        L.new(fn.outputs['Fac'], bp.inputs['Height'])
        L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    MATS[name] = m
    return m


def banded(name, col, rough, pitch, axis='Z', amp=0.35, sheen=0.0):
    """printed / wound filament: fine sinusoidal ridges every `pitch` metres along an object axis"""
    m = bpy.data.materials.new('bambu_' + name)
    m.use_nodes = True
    N = m.node_tree.nodes
    L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    c = srgb(col)
    bs.inputs['Base Color'].default_value = (*c, 1)
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Subsurface Weight'].default_value = 0.15
    bs.inputs['Subsurface Radius'].default_value = (0.002, 0.002, 0.002)
    if sheen:
        bs.inputs['Coat Weight'].default_value = sheen
    m.diffuse_color = (*c, 1)
    tc = N.new('ShaderNodeTexCoord')
    sp = N.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['Object'], sp.inputs[0])
    mu = N.new('ShaderNodeMath')
    mu.operation = 'MULTIPLY'
    mu.inputs[1].default_value = 2 * math.pi / pitch
    L.new(sp.outputs[axis], mu.inputs[0])
    sn = N.new('ShaderNodeMath')
    sn.operation = 'SINE'
    L.new(mu.outputs[0], sn.inputs[0])
    bp = N.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = amp
    bp.inputs['Distance'].default_value = pitch * 0.25
    L.new(sn.outputs[0], bp.inputs['Height'])
    L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    MATS[name] = m
    return m


def pei_mat():
    m = bpy.data.materials.new('bambu_pei_textured')
    m.use_nodes = True
    N = m.node_tree.nodes
    L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    tc = N.new('ShaderNodeTexCoord')
    fine = N.new('ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 2600
    fine.inputs['Detail'].default_value = 6
    fine.inputs['Roughness'].default_value = 0.7
    L.new(tc.outputs['Object'], fine.inputs['Vector'])
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*srgb((0.50, 0.34, 0.14)), 1)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (*srgb((0.74, 0.56, 0.28)), 1)
    L.new(fine.outputs['Fac'], ramp.inputs['Fac'])
    L.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    bs.inputs['Metallic'].default_value = 0.45
    bs.inputs['Roughness'].default_value = 0.52
    bp = N.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.45
    bp.inputs['Distance'].default_value = 0.00015
    L.new(fine.outputs['Fac'], bp.inputs['Height'])
    L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    m.diffuse_color = (*srgb((0.66, 0.48, 0.22)), 1)
    MATS['pei'] = m
    return m


def screen_mat():
    """3.5" touchscreen showing a dim, text-free print-status layout"""
    m = bpy.data.materials.new('bambu_screen')
    m.use_nodes = True
    N = m.node_tree.nodes
    L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value = (0.005, 0.005, 0.006, 1)
    bs.inputs['Roughness'].default_value = 0.04
    bs.inputs['Coat Weight'].default_value = 1.0
    tc = N.new('ShaderNodeTexCoord')
    sp = N.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['UV'], sp.inputs[0])

    def band(lo_, hi_, comp):
        a = N.new('ShaderNodeMath'); a.operation = 'GREATER_THAN'; a.inputs[1].default_value = lo_
        b = N.new('ShaderNodeMath'); b.operation = 'LESS_THAN'; b.inputs[1].default_value = hi_
        L.new(sp.outputs[comp], a.inputs[0]); L.new(sp.outputs[comp], b.inputs[0])
        mm = N.new('ShaderNodeMath'); mm.operation = 'MULTIPLY'
        L.new(a.outputs[0], mm.inputs[0]); L.new(b.outputs[0], mm.inputs[1])
        return mm.outputs[0]

    def rect(x0, x1, y0, y1):
        mm = N.new('ShaderNodeMath'); mm.operation = 'MULTIPLY'
        L.new(band(x0, x1, 'X'), mm.inputs[0]); L.new(band(y0, y1, 'Y'), mm.inputs[1])
        return mm.outputs[0]

    base = srgb((0.10, 0.11, 0.13))
    col_a = srgb((0.30, 0.78, 0.45))       # green progress bar / accent
    col_b = srgb((0.55, 0.58, 0.62))       # grey tiles
    mixes = [(rect(0.06, 0.62, 0.20, 0.26), col_a), (rect(0.62, 0.94, 0.20, 0.26), srgb((0.22, 0.24, 0.27))),
             (rect(0.06, 0.40, 0.38, 0.86), srgb((0.25, 0.27, 0.30))),
             (rect(0.46, 0.94, 0.72, 0.80), col_b), (rect(0.46, 0.80, 0.56, 0.63), col_b),
             (rect(0.46, 0.70, 0.40, 0.47), col_b)]
    cur = N.new('ShaderNodeRGB'); cur.outputs[0].default_value = (*base, 1)
    out = cur.outputs[0]
    for f, c in mixes:
        mx = N.new('ShaderNodeMix'); mx.data_type = 'RGBA'
        L.new(f, mx.inputs['Factor'])
        L.new(out, mx.inputs[6])
        mx.inputs[7].default_value = (*c, 1)
        out = mx.outputs[2]
    L.new(out, bs.inputs['Emission Color'])
    bs.inputs['Emission Strength'].default_value = 1.6
    m.diffuse_color = (0.05, 0.05, 0.06, 1)
    MATS['screen'] = m
    return m


def painted_wood(name, direction):
    """white satin paint over wood: faint grain telegraphing through the paint (bump only + tiny tone)"""
    m = bpy.data.materials.new('bambu_' + name)
    m.use_nodes = True
    N = m.node_tree.nodes
    L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    tc = N.new('ShaderNodeTexCoord')
    wv = N.new('ShaderNodeTexWave')
    wv.wave_type = 'BANDS'
    wv.bands_direction = direction
    wv.inputs['Scale'].default_value = 55.0
    wv.inputs['Distortion'].default_value = 6.0
    wv.inputs['Detail'].default_value = 3.0
    wv.inputs['Detail Scale'].default_value = 1.5
    L.new(tc.outputs['Object'], wv.inputs['Vector'])
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*srgb((0.885, 0.88, 0.865)), 1)
    ramp.color_ramp.elements[1].color = (*srgb((0.915, 0.91, 0.895)), 1)
    L.new(wv.outputs['Fac'], ramp.inputs['Fac'])
    L.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    nz = N.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 40
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.30
    mr.inputs['To Max'].default_value = 0.42
    L.new(nz.outputs['Fac'], mr.inputs['Value'])
    L.new(mr.outputs['Result'], bs.inputs['Roughness'])
    fn = N.new('ShaderNodeTexNoise')
    fn.inputs['Scale'].default_value = 900
    L.new(tc.outputs['Object'], fn.inputs['Vector'])
    ad = N.new('ShaderNodeMath')
    ad.operation = 'MULTIPLY_ADD'
    ad.inputs[1].default_value = 0.25
    L.new(fn.outputs['Fac'], ad.inputs[0])
    L.new(wv.outputs['Fac'], ad.inputs[2])
    bp = N.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.06
    bp.inputs['Distance'].default_value = 0.0003
    L.new(ad.outputs[0], bp.inputs['Height'])
    L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    m.diffuse_color = (*srgb((0.90, 0.895, 0.88)), 1)
    MATS[name] = m
    return m


def top_layer(name, col, pitch=0.00045):
    """last printed layer seen from above: +-45 deg extrusion lines (object coords)"""
    m = bpy.data.materials.new('bambu_' + name)
    m.use_nodes = True
    N = m.node_tree.nodes
    L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    c = srgb(col)
    bs.inputs['Base Color'].default_value = (*c, 1)
    bs.inputs['Roughness'].default_value = 0.30
    bs.inputs['Subsurface Weight'].default_value = 0.15
    bs.inputs['Subsurface Radius'].default_value = (0.002, 0.002, 0.002)
    tc = N.new('ShaderNodeTexCoord')
    sp = N.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['Object'], sp.inputs[0])
    ad = N.new('ShaderNodeMath')
    ad.operation = 'ADD'
    L.new(sp.outputs['X'], ad.inputs[0])
    L.new(sp.outputs['Y'], ad.inputs[1])
    mu = N.new('ShaderNodeMath')
    mu.operation = 'MULTIPLY'
    mu.inputs[1].default_value = 2 * math.pi / (pitch * 1.4142)
    L.new(ad.outputs[0], mu.inputs[0])
    sn = N.new('ShaderNodeMath')
    sn.operation = 'SINE'
    L.new(mu.outputs[0], sn.inputs[0])
    ab = N.new('ShaderNodeMath')
    ab.operation = 'ABSOLUTE'
    L.new(sn.outputs[0], ab.inputs[0])
    bp = N.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.6
    bp.inputs['Distance'].default_value = 0.00008
    L.new(ab.outputs[0], bp.inputs['Height'])
    L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    m.diffuse_color = (*c, 1)
    MATS[name] = m
    return m


mat('body', (0.90, 0.905, 0.90), 0.40, bump=0.05, bscale=1400)      # white/very light grey PC covers
mat('body_grey', (0.62, 0.63, 0.64), 0.42, bump=0.05, bscale=1400)
mat('body_dark', (0.17, 0.175, 0.18), 0.45, bump=0.06, bscale=1400)  # dark grey trim / foot band
mat('alu', (0.74, 0.75, 0.76), 0.34, metal=1.0, bump=0.05, bscale=3000)       # silver anodised towers
mat('alu_dark', (0.10, 0.105, 0.11), 0.38, metal=0.7, bump=0.05, bscale=3000)  # heatbed
mat('steel', (0.78, 0.78, 0.80), 0.18, metal=1.0, aniso=0.5)
mat('brass', (0.86, 0.66, 0.36), 0.25, metal=1.0)
mat('gold_ring', (0.80, 0.62, 0.34), 0.30, metal=1.0)
mat('rubber', (0.03, 0.03, 0.03), 0.8, bump=0.2, bscale=900)
mat('black', (0.035, 0.035, 0.038), 0.45)
mat('cable', (0.025, 0.025, 0.028), 0.55, bump=0.35, bscale=1800)
mat('ptfe', (0.93, 0.93, 0.92), 0.22, trans=0.35)
mat('spool_white', (0.93, 0.93, 0.92), 0.30, bump=0.03, bscale=1200)
mat('shadow', (0.02, 0.02, 0.02), 0.9)
mat('nickel', (0.80, 0.79, 0.76), 0.28, metal=1.0)
mat('glide', (0.30, 0.30, 0.30), 0.6)
mat('plug', (0.92, 0.92, 0.90), 0.4)
painted_wood('paint_top', 'Y')
painted_wood('paint_leg', 'X')
pei_mat()
screen_mat()
FILAMENT = (0.66, 0.90, 0.78)        # pastel mint PLA
banded('filament_spool', FILAMENT, 0.38, 0.00175, axis='Z', amp=0.5, sheen=0.3)
banded('print', FILAMENT, 0.42, 0.0002, axis='Z', amp=0.3)
top_layer('print_top', FILAMENT)
mat('filament_strand', FILAMENT, 0.35)


# ------------------------------------------------------------------ geometry helpers
def finish(o, m, smooth_angle=35.0):
    o.data.materials.append(MATS[m])
    me = o.data
    if smooth_angle is not None:
        for p in me.polygons:
            p.use_smooth = True
        try:
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        except Exception:
            pass
    coll.objects.link(o)
    OBJS.append(o)
    return o


def from_bm(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def rbox(name, lo, hi, r, m, segs=3, local=True, angle=35.0, rot=None, pivot=None):
    """rounded box between lo/hi (printer-local mm if local else room m); r = edge radius (same units)"""
    lo, hi = V(lo), V(hi)
    s = hi - lo
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = V((v.co.x * s.x, v.co.y * s.y, v.co.z * s.z)) + (lo + hi) / 2
    if r > 0:
        r = min(r, min(s) * 0.49)
        bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=r, segments=segs, profile=0.5,
                        affect='EDGES', clamp_overlap=True)
    if rot is not None:
        pv = V(pivot) if pivot is not None else (lo + hi) / 2
        bmesh.ops.rotate(bm, verts=bm.verts, cent=pv, matrix=rot)
    if local:
        for v in bm.verts:
            v.co = P(*v.co)
    return finish(from_bm(name, bm), m, angle)


def cyl(name, r, a, b, m, verts=32, local=True, r2=None, angle=40.0, cap_bevel=0.0):
    """cylinder / cone from point a to point b"""
    a, b = V(a), V(b)
    if local:
        a, b = P(*a), P(*b)
        r = r / 1000.0
        r2 = r2 / 1000.0 if r2 is not None else None
        cap_bevel /= 1000.0
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r,
                          radius2=r if r2 is None else r2, depth=d.length)
    if cap_bevel > 0:
        caps = [e for e in bm.edges if all(abs(abs(v.co.z) - d.length / 2) < 1e-7 for v in e.verts)]
        bmesh.ops.bevel(bm, geom=caps, offset=cap_bevel, segments=2, profile=0.5, affect='EDGES', clamp_overlap=True)
    q = d.normalized().to_track_quat('Z', 'Y')
    bmesh.ops.rotate(bm, verts=bm.verts, cent=V(), matrix=q.to_matrix())
    bmesh.ops.translate(bm, verts=bm.verts, vec=(a + b) / 2)
    return finish(from_bm(name, bm), m, angle)


def lathe(name, prof, m, segs=64, angle=40.0, closed=False):
    """profile [(r, z)] in metres, spun around local Z; returns object at origin (caller places it)"""
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0.0, z)) for r, z in prof]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    if closed:
        es.append(bm.edges.new((vs[-1], vs[0])))
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=segs,
                   use_merge=True, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(from_bm(name, bm), m, angle)


def torus(name, center, R, r, axis, m, seg=48, rseg=10, local=True):
    bm = bmesh.new()
    rows = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        row = []
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            row.append(bm.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
        rows.append(row)
    for i in range(seg):
        for j in range(rseg):
            bm.faces.new((rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % rseg], rows[i][(j + 1) % rseg]))
    q = V(axis).normalized().to_track_quat('Z', 'Y')
    bmesh.ops.rotate(bm, verts=bm.verts, cent=V(), matrix=q.to_matrix())
    bmesh.ops.translate(bm, verts=bm.verts, vec=V(center))
    if local:
        for v in bm.verts:
            v.co = P(*v.co)
    return finish(from_bm(name, bm), m, 60.0)


def tube(name, pts, radius, m, local=True, res=10, bev=6):
    """smooth tube through points (NURBS-like via bezier AUTO handles)"""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = res
    cu.bevel_depth = radius / 1000.0 if local else radius
    cu.bevel_resolution = bev // 2
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        p = P(*p) if local else V(p)
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    tmp = bpy.data.objects.new(name + '_c', cu)
    scene.collection.objects.link(tmp)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    me.name = name
    o = bpy.data.objects.new(name, me)
    return finish(o, m, 60.0)


# ============================================================================== side table (painted wood)
TX0, TX1 = TABLE_X
TY0, TY1 = TABLE_Y
H = TABLE_H
TOP_T = 0.025
LEG = 0.038
LEG_B = 0.028                     # leg width at the foot (inner faces tapered)
INS = 0.022                       # top overhang past the legs
GL = 0.004                        # glide height
rbox('bambu_table_top', (TX0, TY0, H - TOP_T), (TX1, TY1, H), 0.006, 'paint_top', segs=4, local=False)
LX = ((TX0 + INS, TX0 + INS + LEG), (TX1 - INS - LEG, TX1 - INS))
LY = ((TY0 + INS, TY0 + INS + LEG), (TY1 - INS - LEG, TY1 - INS))
for i, (x0, x1) in enumerate(LX):
    for j, (y0, y1) in enumerate(LY):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            top = v.co.z > 0
            xs = [x0, x1]
            ys = [y0, y1]
            if not top:                         # taper only the two inner faces
                if i == 0: xs[1] = x0 + LEG_B
                else: xs[0] = x1 - LEG_B
                if j == 0: ys[1] = y0 + LEG_B
                else: ys[0] = y1 - LEG_B
            v.co = V((xs[v.co.x > 0], ys[v.co.y > 0], (H - TOP_T) if top else GL))
        bmesh.ops.bevel(bm, geom=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1],
                        offset=0.0025, segments=2, profile=0.5, affect='EDGES')
        bot = [f for f in bm.faces if f.normal.z < -0.9]
        bmesh.ops.inset_region(bm, faces=bot, thickness=0.0015, depth=0.0)
        finish(from_bm('bambu_table_leg_%d%d' % (i, j), bm), 'paint_leg', 40)
        cx = (x0 + LEG_B / 2) if i == 0 else (x1 - LEG_B / 2)
        cy = (y0 + LEG_B / 2) if j == 0 else (y1 - LEG_B / 2)
        cyl('bambu_table_glide_%d%d' % (i, j), 0.0105, (cx, cy, 0.0), (cx, cy, GL), 'glide', verts=24, local=False,
            cap_bevel=0.0012)
# aprons: 18 mm boards, 85 mm deep, set back 4 mm from the leg faces, tenoned into the legs
AT, AH, SB = 0.018, 0.085, 0.004
az0, az1 = H - TOP_T - AH, H - TOP_T
xa0, xa1 = LX[0][1] - 0.010, LX[1][0] + 0.010          # run 10 mm into the legs
ya0, ya1 = LY[0][1] - 0.010, LY[1][0] + 0.010
rbox('bambu_table_apron_back', (xa0, LY[1][1] - SB - AT, az0), (xa1, LY[1][1] - SB, az1), 0.0015, 'paint_top', local=False)
rbox('bambu_table_apron_left', (LX[0][0] + SB, ya0, az0), (LX[0][0] + SB + AT, ya1, az1), 0.0015, 'paint_leg', local=False)
rbox('bambu_table_apron_right', (LX[1][1] - SB - AT, ya0, az0), (LX[1][1] - SB, ya1, az1), 0.0015, 'paint_leg', local=False)
# front: top rail + bottom rail framing a drawer (2 mm reveals, dark cavity behind)
fy0 = LY[0][0] + SB
rbox('bambu_table_rail_top', (xa0, fy0, az1 - 0.016), (xa1, fy0 + AT, az1), 0.0012, 'paint_top', local=False)
rbox('bambu_table_rail_bot', (xa0, fy0, az0), (xa1, fy0 + AT, az0 + 0.012), 0.0012, 'paint_top', local=False)
dx0, dx1 = LX[0][1] + 0.002, LX[1][0] - 0.002
dz0, dz1 = az0 + 0.012 + 0.002, az1 - 0.016 - 0.002
rbox('bambu_table_drawer_cavity', (dx0 - 0.004, fy0 + 0.006, dz0 - 0.004), (dx1 + 0.004, fy0 + 0.060, dz1 + 0.004), 0.0,
     'shadow', local=False)
rbox('bambu_table_drawer_front', (dx0, fy0 - 0.0005, dz0), (dx1, fy0 + AT, dz1), 0.0022, 'paint_top', segs=3, local=False)
knob = lathe('bambu_table_drawer_knob', [(0.0, 0.0), (0.0065, 0.0), (0.0055, 0.004), (0.0042, 0.011), (0.0075, 0.016),
                                          (0.0120, 0.019), (0.0125, 0.0215), (0.0105, 0.0245), (0.0, 0.0255)],
             'nickel', segs=40, angle=50)
knob.matrix_world = Matrix.Translation(V(((dx0 + dx1) / 2, fy0 - 0.0005, (dz0 + dz1) / 2))) @ Matrix.Rotation(math.radians(90), 4, 'X')
# lower shelf, notched around the legs
SH_TOP = 0.175
rbox('bambu_table_shelf', (LX[0][0] + SB, LY[0][0] + SB, SH_TOP - 0.016), (LX[1][1] - SB, LY[1][1] - SB, SH_TOP),
     0.0025, 'paint_top', segs=3, local=False)

# ============================================================================== printer base
for sx in (-1, 1):
    for sy in (-1, 1):
        cyl('bambu_foot_%d%d' % (sx, sy), 12, (sx * 135, -150 if sy < 0 else 165, 0), (sx * 135, -150 if sy < 0 else 165, 4),
            'rubber', verts=24)
BY0, BY1 = -170.0, 185.0
rbox('bambu_base_band', (-164, BY0 + 4, 3), (164, BY1 - 4, 12), 8, 'body_dark')
rbox('bambu_base_body', (-168, BY0, 9), (168, BY1, 62), 16, 'body', segs=4)
rbox('bambu_base_ychannel', (-40, BY0 + 10, 59.5), (40, BY1 - 10, 62.6), 4, 'body_dark')
rbox('bambu_y_rail', (-10, BY0 + 14, 62.6), (10, BY1 - 14, 67.0), 1.2, 'alu')
# dot speaker grille on the front face, right of the screen
for c_ in range(5):
    for r_ in range(4):
        x_ = 124 + c_ * 7.5
        z_ = 22 + r_ * 7.0
        cyl('bambu_grille_%d%d' % (c_, r_), 1.25, (x_, BY0 - 0.6, z_), (x_, BY0 + 1.2, z_), 'body_dark', verts=10)
rbox('bambu_base_inlet', (-140, BY1 - 2, 22), (-100, BY1 + 0.5, 46), 2.0, 'body_dark')
rbox('bambu_base_switch', (-92, BY1 - 2, 28), (-80, BY1 + 0.8, 40), 1.5, 'rubber')

# tablet-style 3.5" touchscreen on a stalk at the front right, tilted up toward the user
SCX, SCY, SCZ = 72.0, -199.0, 45.0
tilt = Matrix.Rotation(math.radians(-58), 3, 'X')
rbox('bambu_screen_stalk', (SCX - 14, BY0 - 14, 28), (SCX + 14, BY0 + 6, 48), 5, 'body')
rbox('bambu_screen_shell', (SCX - 45, SCY - 4.5, SCZ - 31), (SCX + 45, SCY + 4.5, SCZ + 31), 5, 'body', segs=3,
     rot=tilt, pivot=(SCX, SCY, SCZ))
rbox('bambu_screen_glass', (SCX - 42.5, SCY - 4.8, SCZ - 28.5), (SCX + 42.5, SCY - 3.5, SCZ + 28.5), 3, 'black', segs=2,
     rot=tilt, pivot=(SCX, SCY, SCZ))
bm = bmesh.new()
sw, sh = 73.0, 48.5
co = [(-sw / 2, -sh / 2), (sw / 2, -sh / 2), (sw / 2, sh / 2), (-sw / 2, sh / 2)]
vs = [bm.verts.new((SCX + x, SCY - 4.95, SCZ + z)) for x, z in co]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new('UVMap')
for loop, (x, z) in zip(f.loops, co):
    loop[uv].uv = (x / sw + 0.5, z / sh + 0.5)
bmesh.ops.rotate(bm, verts=bm.verts, cent=V((SCX, SCY, SCZ)), matrix=tilt)
for v in bm.verts:
    v.co = P(*v.co)
o = from_bm('bambu_screen', bm)
o.data.update()
if o.data.polygons[0].normal.y > 0:
    o.data.flip_normals()
finish(o, 'screen', None)

# ============================================================================== Y bed (sliding), parked under the nozzle
by = NOZ_Y
rbox('bambu_bed_carriage', (-38, by - 60, 66.5), (38, by + 60, 72), 2.5, 'alu_dark')
rbox('bambu_heatbed', (-130, by - 130, 72), (130, by + 130, BED_TOP - 1), 3, 'alu_dark', segs=2)
rbox('bambu_pei_plate', (-128.5, by - 128.5, BED_TOP - 1), (128.5, by + 128.5, BED_TOP), 0.45, 'pei', segs=2, angle=60)
rbox('bambu_pei_tab', (-22, by - 137, BED_TOP - 1), (22, by - 127, BED_TOP - 0.3), 3, 'steel', segs=2, angle=60)
# braided bed cable loop from the heatbed rear down into the base rear
tube('bambu_bed_cable', [(30, by + 128, 71), (34, by + 150, 80), (40, 150, 92), (46, 196, 70), (44, 192, 38),
                         (40, BY1 - 4, 32)], 3.2, 'cable', res=12)

# ============================================================================== Z towers + top beam (silver anodised)
TX_IN, TX_OUT = 140.0, 172.0
TY_0, TY_1 = 8.0, 44.0
for s, nm in ((-1, 'L'), (1, 'R')):
    xa, xb = sorted((s * TX_IN, s * TX_OUT))
    rbox('bambu_tower_' + nm, (xa, TY_0, 2), (xb, TY_1, 400), 3.5, 'alu', segs=3)
    rbox('bambu_tower_foot_' + nm, (xa - 3, TY_0 - 5, 0), (xb + 3, TY_1 + 5, 28), 5, 'body_dark', segs=3)
rbox('bambu_top_beam', (-TX_OUT, TY_0, 398), (TX_OUT, TY_1, 428), 4, 'alu', segs=3)
rbox('bambu_top_clip', (-72, TY_0 - 3, 424), (-50, TY_1 + 3, 437), 4, 'body')

# ============================================================================== X gantry
GZ = 150.0
rbox('bambu_x_beam', (-190, -16, GZ - 20), (150, 6, GZ + 20), 2, 'alu', segs=2)
rbox('bambu_x_rail', (-176, -18.2, GZ + 2), (140, -16, GZ + 14), 0.6, 'steel')
for k in range(16):
    xh = -166 + k * 20
    cyl('bambu_x_rail_hole_%02d' % k, 1.6, (xh, -18.5, GZ + 8), (xh, -17.4, GZ + 8), 'black', verts=10)
rbox('bambu_x_belt_slot', (-170, -16.4, GZ - 13), (136, -15.6, GZ - 7), 0.3, 'black')
rbox('bambu_x_block_L', (-TX_OUT - 2, -20, GZ - 28), (-TX_IN + 2, TY_0 + 1, GZ + 26), 4, 'body_grey')
rbox('bambu_x_motor_box', (TX_IN - 2, -30, GZ - 30), (192.5, 12, GZ + 28), 8, 'body', segs=3)
rbox('bambu_x_cutter_block', (-192.5, -24, GZ - 18), (-174, 6, GZ + 16), 4, 'body_dark')
rbox('bambu_x_cutter_lever', (-190, -30, GZ - 4), (-180, -24, GZ + 10), 2, 'black')

# ============================================================================== toolhead
tx = TOOL_X
NZ = BED_TOP + BENCHY_H + 0.3     # nozzle tip, 0.3 mm above the last layer
rbox('bambu_th_carriage', (tx - 24, -22, GZ - 20), (tx + 24, -18, GZ + 20), 2, 'body_grey')
rbox('bambu_th_body', (tx - 24, -72, NZ + 22), (tx + 24, -20, NZ + 78), 7, 'body', segs=4)
rbox('bambu_th_lower', (tx - 17, -62, NZ + 12), (tx + 17, -30, NZ + 24), 3.5, 'black')
rbox('bambu_th_heatsink', (tx - 7, NOZ_Y - 7, NZ + 10), (tx + 7, NOZ_Y + 7, NZ + 13), 1.0, 'steel')
# round front element: dark recess, gold ring, white centre
fcz = NZ + 52
cyl('bambu_th_front_recess', 13, (tx, -73.2, fcz), (tx, -71.5, fcz), 'black', verts=40)
torus('bambu_th_front_ring', (tx, -73.3, fcz), 11.0, 1.3, (0, 1, 0), 'gold_ring', seg=40, rseg=8)
cyl('bambu_th_front_disc', 8.6, (tx, -74.0, fcz), (tx, -72.5, fcz), 'body', verts=36, cap_bevel=0.7)
# upper neck with PTFE coupling + umbilical connector
rbox('bambu_th_neck', (tx - 18, -60, NZ + 76), (tx + 6, -30, NZ + 104), 5, 'body', segs=3)
cyl('bambu_th_ptfe_coupling', 5.0, (tx - 6, -45, NZ + 103), (tx - 6, -45, NZ + 110), 'black', verts=24, cap_bevel=1)
rbox('bambu_th_connector', (tx + 6, -54, NZ + 70), (tx + 20, -36, NZ + 98), 3, 'body', segs=3)
rbox('bambu_th_cutter', (tx + 23.5, -66, NZ + 56), (tx + 29, -52, NZ + 72), 2.2, 'body')
rbox('bambu_th_side_fan', (tx - 27.5, -64, NZ + 28), (tx - 23.5, -30, NZ + 54), 2, 'black')
# hotend: silicone sock, brass nozzle
rbox('bambu_th_sock', (tx - 8, NOZ_Y - 7, NZ + 4.0), (tx + 8, NOZ_Y + 7, NZ + 10.2), 2.5, 'body_grey')
cyl('bambu_th_nozzle_hex', 3.6, (tx, NOZ_Y, NZ + 2.2), (tx, NOZ_Y, NZ + 4.2), 'brass', verts=6, angle=30)
cyl('bambu_th_nozzle_tip', 0.55, (tx, NOZ_Y, NZ), (tx, NOZ_Y, NZ + 2.2), 'brass', r2=2.6, verts=16)

# ============================================================================== spool holder + white spool (axis left-right)
SX, SY, SZC = 150.0, 26.0, 548.0
rbox('bambu_spool_clip', (104, TY_0 - 4, 425), (178, TY_1 + 4, 440), 4, 'body', segs=3)
rbox('bambu_spool_post', (100, SY - 9, 436), (113, SY + 9, SZC + 14), 5, 'body', segs=3)
cyl('bambu_spool_axle', 24.5, (110, SY, SZC), (190, SY, SZC), 'body', verts=40, cap_bevel=1.5)
cyl('bambu_spool_axle_cap', 28, (189, SY, SZC), (193, SY, SZC), 'body', verts=40, cap_bevel=1.2)
cyl('bambu_spool_inlet', 5.5, (136, -2, 434), (136, -8, 441), 'body', verts=20, r2=4.0)
spool_rot = Matrix.Rotation(math.radians(90), 4, 'Y')            # local Z (spool axis) -> room X
spool_loc = P(SX, SY, SZC)
W = 0.066 / 2
fl_t = 0.0028
prof_fl = [(0.0275, -W), (0.0995, -W), (0.1, -W + fl_t * 0.5), (0.0995, -W + fl_t), (0.0275, -W + fl_t)]
spool_parts = []
for side, sgn in (('L', 1), ('R', -1)):
    spool_parts.append(lathe('bambu_spool_flange_' + side, [(r, z * sgn) for r, z in prof_fl], 'spool_white', segs=72,
                             closed=True))
spool_parts.append(lathe('bambu_spool_core', [(0.0275, -W + fl_t), (0.0275, W - fl_t), (0.0385, W - fl_t),
                                              (0.0385, -W + fl_t)], 'spool_white', segs=48, closed=True))
R_FIL = 0.086
fil = [(0.0385, -W + fl_t + 0.0002), (R_FIL - 0.0015, -W + fl_t + 0.0002), (R_FIL, -W + fl_t + 0.0018),
       (R_FIL, W - fl_t - 0.0018), (R_FIL - 0.0015, W - fl_t - 0.0002), (0.0385, W - fl_t - 0.0002)]
spool_parts.append(lathe('bambu_spool_filament', fil, 'filament_spool', segs=96, closed=True))
for o in spool_parts:
    o.matrix_world = Matrix.Translation(spool_loc) @ spool_rot
# strand off the bottom-front of the winding into the inlet
a_ = math.radians(35)
tube('bambu_filament_strand', [(SX - 12, SY - 86 * math.sin(a_), SZC - 86 * math.cos(a_)), (138, -8, 470), (136, -6, 440)],
     0.875, 'filament_strand', res=8, bev=4)

# ============================================================================== PTFE tube + cables
tube('bambu_ptfe_tube', [(136, -6, 436), (132, -30, 410), (90, -78, 350), (30, -82, 280), (tx - 6, -58, NZ + 150),
                         (tx - 6, -45, NZ + 110)], 2.0, 'ptfe', res=14)
tube('bambu_umbilical', [(tx + 13, -45, NZ + 97), (tx + 14, -42, NZ + 150), (-30, -18, 345), (-58, 12, 420),
                         (-61, 26, 436)], 3.8, 'cable', res=14)
tube('bambu_x_motor_cable', [(185, -8, GZ - 28), (198, -2, 95), (196, 30, 50), (176, 55, 30), (166, 60, 30)], 3.0,
     'cable', res=12)

# ============================================================================== half-finished 3DBenchy (cut at 24 of 48 mm)
BX, BYC = tx - 3.8, NOZ_Y          # nozzle sits over the cabin's front centre pillar
b_org = P(BX, BYC, BED_TOP)


def benchy_obj(name, bm):
    for v in bm.verts:
        v.co = v.co / 1000.0
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = from_bm(name, bm)
    o.data.materials.append(MATS['print'])
    o.data.materials.append(MATS['print_top'])
    for p in o.data.polygons:
        p.material_index = 1 if p.normal.z > 0.9 else 0
    coll.objects.link(o)
    OBJS.append(o)
    o.location = b_org
    return o


def hull():
    """lofted tug hull: flat-bottomed, flaring sides, sheer rising to a raked, pointed bow, hollow above the deck"""
    bm = bmesh.new()
    stations = [-30, -28.5, -26, -22, -17, -11, -5, 1, 7, 12, 16, 19.5, 22.5, 25, 27, 28.6, 29.6, 30]
    rings = []
    for x in stations:
        if x <= -5:
            w = 13.4 + 2.1 * (1 - ((x + 5) / 25.0) ** 2)
        else:
            w = 15.5 * math.sqrt(max(0.0, 1 - ((x + 5) / 35.0) ** 2))
        w = max(w, 0.15)
        if x == -30:
            w *= 0.97
        zb = 0.0 if x < 8 else 12.5 * ((x - 8) / 22.0) ** 1.6
        h = min(BENCHY_H, 15.5 + 9.0 * ((x + 30) / 60.0) ** 2.4)
        rake = 0.0 if x < 8 else 5.0 * ((x - 8) / 22.0) ** 2          # stem leans forward toward the top
        wi = w - 1.6
        closed = wi < 0.4
        wi = max(wi, 0.0)
        d = min(max(11.0, zb + 1.8), h - 0.8)
        if closed:
            d = h
        zm = zb + 0.45 * (h - zb)
        ring = [(-0.55 * w, zb, 0.0), (-0.97 * w, zm, 0.45), (-w, h, 1.0), (-wi, h, 1.0), (-wi, d, 1.0 if closed else 0.8),
                (wi, d, 1.0 if closed else 0.8), (wi, h, 1.0), (w, h, 1.0), (0.97 * w, zm, 0.45), (0.55 * w, zb, 0.0)]
        rings.append([bm.verts.new((x + rake * t, y, z)) for y, z, t in ring])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    caps = [bm.faces.new(rings[0][::-1]), bm.faces.new(rings[-1])]
    bmesh.ops.triangulate(bm, faces=caps, quad_method='BEAUTY', ngon_method='BEAUTY')
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-4)
    return benchy_obj('bambu_benchy_hull', bm)


def bbox_mesh(bm, x0, x1, y0, y1, z0, z1):
    vs = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in f])


hull()
bm = bmesh.new()
CW, CX0, CX1, CY, DZ, TZ = 2.4, -21.0, 5.0, 11.0, 11.0, BENCHY_H
for s in (-1, 1):                                                      # side walls with door openings
    y0, y1 = sorted((s * CY, s * (CY - CW)))
    bbox_mesh(bm, CX0, -14.0, y0, y1, DZ, TZ)
    bbox_mesh(bm, -6.0, CX1, y0, y1, DZ, TZ)
bbox_mesh(bm, CX1 - CW, CX1, -CY + CW, CY - CW, DZ, 17.0)             # front wall + window pillars
for y0, y1 in ((-CY + CW, -8.5), (-1.5, 1.5), (8.5, CY - CW)):
    bbox_mesh(bm, CX1 - CW, CX1, y0, y1, 17.0, TZ)
bbox_mesh(bm, CX0, CX0 + CW, -CY + CW, CY - CW, DZ, 16.5)             # rear wall + rear window
for y0, y1 in ((-CY + CW, -6.0), (6.0, CY - CW)):
    bbox_mesh(bm, CX0, CX0 + CW, y0, y1, 16.5, TZ)
benchy_obj('bambu_benchy_cabin', bm)
bm = bmesh.new()
for s in (-1, 1):                                                      # stern bollards
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=1.8, radius2=1.8, depth=4.5,
                          matrix=Matrix.Translation((-26.0, s * 7.0, DZ + 2.25)))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=2.4, radius2=2.4, depth=0.8,
                          matrix=Matrix.Translation((-26.0, s * 7.0, DZ + 4.9)))
benchy_obj('bambu_benchy_bollards', bm)
for s_ in (-1, 1):                                                     # hawse holes either side of the bow
    xh = 21.0
    wh = 15.5 * math.sqrt(max(0.0, 1 - ((xh + 5) / 35.0) ** 2))
    o = cyl('bambu_benchy_hawse_%d' % (s_ > 0), 1.6, (BX + xh + 0.9, BYC + s_ * (wh - 1.9), BED_TOP + 19.3),
            (BX + xh + 0.9, BYC + s_ * (wh + 0.3), BED_TOP + 19.3), 'shadow', verts=16)

# ============================================================================== power cable to the left-wall outlet
plug_y = 0.950
rbox('bambu_power_plug', (-2.0795, plug_y - 0.017, 0.262), (-2.052, plug_y + 0.017, 0.298), 0.004, 'plug', local=False)
tube('bambu_power_cable', [
    (-2.052, plug_y, 0.272), (-2.050, plug_y + 0.02, 0.18), (-2.064, plug_y + 0.08, 0.121), (-2.062, plug_y + 0.13, 0.03),
    (-2.056, 1.110, 0.0035), (-1.95, 1.122, 0.0035), (-1.84, 1.112, 0.004), (-1.815, 1.100, 0.08),
    (-1.8125, 1.094, 0.45), (-1.8115, 1.091, 0.625), (-1.797, 1.090, 0.6508), (-1.72, 1.092, 0.6508),
    (-1.655, 1.080, 0.6515), (-1.641, 1.061, 0.672), (-1.640, 1.055, 0.682)], 0.0028, 'cable', local=False, res=10, bev=6)
pc = bpy.data.objects['bambu_power_cable']
for v in pc.data.vertices:                 # on (not in) the floor / table, off the baseboard face (toe x=-2.0675)
    v.co.z = max(v.co.z, 0.0002)
    if v.co.z < 0.115:
        v.co.x = max(v.co.x, -2.0668)
    if -1.80 < v.co.x < -1.66 and v.co.z < 0.66:
        v.co.z = max(v.co.z, H + 0.0002)
pc.data.update()

# ============================================================================== parent + stats
bpy.context.view_layer.update()
for o in OBJS:
    mw = o.matrix_world.copy()
    o.parent = root
    o.matrix_world = mw
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in OBJS)
print('TRIS', tris, 'OBJECTS', len(OBJS))
allp = [o.matrix_world @ V(c) for o in OBJS for c in o.bound_box]
print('WORLD_BBOX', [(round(min(p[i] for p in allp), 3), round(max(p[i] for p in allp), 3)) for i in range(3)])
pr_objs = [o for o in OBJS if not o.name.startswith(('bambu_table', 'bambu_power'))]
pp = [o.matrix_world @ V(c) for o in pr_objs for c in o.bound_box]
print('PRINTER_BBOX', [(round(min(p[i] for p in pp), 4), round(max(p[i] for p in pp), 4)) for i in range(3)])
frame = [o for o in pr_objs if not o.name.startswith(('bambu_spool', 'bambu_filament', 'bambu_ptfe', 'bambu_umbilical',
                                                      'bambu_x_motor_cable', 'bambu_bed_cable'))]
fp = [o.matrix_world @ V(c) for o in frame for c in o.bound_box]
print('FRAME_DIMS_MM', [round((max(p[i] for p in fp) - min(p[i] for p in fp)) * 1000, 1) for i in range(3)])
tb = [o.matrix_world @ V(c) for o in OBJS if o.name.startswith('bambu_table') for c in o.bound_box]
print('TABLE_BBOX', [(round(min(p[i] for p in tb), 3), round(max(p[i] for p in tb), 3)) for i in range(3)])


# ============================================================================== previews
def previews():
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
    bg.inputs['Strength'].default_value = 0.35
    scene.world = w
    tmp = []
    # floor + the two corner walls for grounding
    for nm, verts in (('prev_floor', [(-3, -2, 0), (1, -2, 0), (1, 1.3, 0), (-3, 1.3, 0)]),
                      ('prev_wall_l', [(-2.08, -2, 0), (-2.08, 1.3, 0), (-2.08, 1.3, 2.7), (-2.08, -2, 2.7)]),
                      ('prev_wall_w', [(-2.08, 1.30, 0), (1, 1.30, 0), (1, 1.30, 2.7), (-2.08, 1.30, 2.7)])):
        me = bpy.data.meshes.new(nm)
        me.from_pydata(verts, [], [(0, 1, 2, 3)])
        fm = bpy.data.materials.new(nm)
        fm.use_nodes = True
        b_ = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        b_.inputs['Base Color'].default_value = (0.30, 0.27, 0.24, 1) if nm == 'prev_floor' else (0.62, 0.62, 0.60, 1)
        b_.inputs['Roughness'].default_value = 0.7
        me.materials.append(fm)
        fo = bpy.data.objects.new(nm, me)
        scene.collection.objects.link(fo)
        tmp.append(fo)
    mid = P(0, 0, 180)

    def light(name, off, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        lo.location = mid + V(off)
        lo.rotation_euler = (mid - lo.location).to_track_quat('-Z', 'Y').to_euler()
        tmp.append(lo)
    light('key', (1.1, -1.0, 1.2), 90, 1.0)
    light('fill', (-0.1, -1.4, 0.3), 30, 1.2)
    light('rim', (0.9, 0.2, 1.3), 50, 0.8)
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam
    tmp.append(cam)

    def shot(loc, target, lens, name, res=(1280, 800)):
        scene.render.resolution_x, scene.render.resolution_y = res
        cam.location = loc
        cam.data.lens = lens
        cam.data.clip_start = 0.01
        cam.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, name)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', name)
    if not ONLY or '34' in ONLY:
        shot(P(560, -900, 480), P(10, -10, 300), 40, 'bambu_34.png', (1100, 1250))
    if not ONLY or 'benchy' in ONLY:
        shot(P(tx - 70, NOZ_Y - 150, BED_TOP + 48), P(tx - 2, NOZ_Y, BED_TOP + 14), 55, 'bambu_benchy.png')
    if not ONLY or 'screen' in ONLY:
        shot(P(60, -430, 190), P(SCX, SCY, SCZ), 60, 'bambu_screen_close.png')
    if not ONLY or 'table' in ONLY:
        shot(V((-0.75, -0.35, 1.05)), V((-1.52, 0.9, 0.55)), 30, 'bambu_table.png', (1000, 1150))
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)


if not NO_RENDER:
    previews()
scene.render.filepath = ''
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('SAVED', OUT)
