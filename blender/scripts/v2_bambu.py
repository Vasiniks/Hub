"""
v2_bambu.py -- Bambu Lab A1 (full-size bed slinger) on a small white side table in the room's
left-wall / window-wall corner.

    blender -b --factory-startup --python blender/scripts/v2_bambu.py -- [--no-render] [--only=34,front]

Reference (verified): A1 overall 385 x 410 x 430 mm (W x D x H, frame without the spool), build volume
256^3, 3.5" touchscreen, two-tower gantry (dual Z), textured/gold PEI plate, spool holder clipped on top
of the frame, PTFE tube from the holder inlet to the toolhead top.
Assumed (not verifiable from text sources): exact tower / beam / toolhead proportions, colours, the
spool holder on the right of the top beam with the spool axis front-to-back, the screen pod on the
base front-right, the toolhead umbilical as a sleeved loop to the left gantry end.

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
TABLE_X = (-2.050, -1.450)          # left wall inner face x=-2.08
TABLE_Y = (0.660, 1.130)            # curtain back face y>=1.149, floor register ends y=0.700
TABLE_H = 0.720
PX, PY, PZ = -1.6575, 0.870, TABLE_H   # printer footprint centre (left tower face at x=-1.850; bookrack face -1.878)
BED_Y = -40.0                        # bed parked 40 mm forward of centre (travel +-128)
TOOL_X = -25.0                       # nozzle x
PRINT_H = 30.0                       # in-progress print height

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


mat('body', (0.80, 0.80, 0.79), 0.42, bump=0.06, bscale=1400)       # light grey ABS/PC covers
mat('body_dark', (0.17, 0.175, 0.18), 0.45, bump=0.06, bscale=1400)  # dark grey trim / base skirt
mat('front_cover', (0.86, 0.86, 0.85), 0.35, bump=0.04, bscale=1400)
mat('alu', (0.70, 0.71, 0.72), 0.30, metal=1.0, bump=0.05, bscale=3000)
mat('alu_dark', (0.12, 0.125, 0.13), 0.35, metal=0.8, bump=0.05, bscale=3000)
mat('steel', (0.78, 0.78, 0.80), 0.18, metal=1.0, aniso=0.5)
mat('brass', (0.86, 0.66, 0.36), 0.25, metal=1.0)
mat('rubber', (0.03, 0.03, 0.03), 0.8, bump=0.2, bscale=900)
mat('silicone', (0.30, 0.31, 0.32), 0.6)
mat('fan', (0.04, 0.04, 0.045), 0.5)
mat('cable', (0.025, 0.025, 0.028), 0.55, bump=0.35, bscale=1800)
mat('ptfe', (0.93, 0.93, 0.92), 0.22, trans=0.35)
mat('spool_flange', (0.10, 0.10, 0.11), 0.30)
mat('spool_hub', (0.18, 0.18, 0.19), 0.45)
mat('paint_white', (0.90, 0.895, 0.88), 0.38, bump=0.08, bscale=500)
mat('felt', (0.55, 0.55, 0.54), 0.9)
mat('plug', (0.92, 0.92, 0.90), 0.4)
pei_mat()
screen_mat()
FILAMENT = (0.66, 0.90, 0.78)        # pastel mint PLA
banded('filament_spool', FILAMENT, 0.38, 0.00175, axis='Z', amp=0.5, sheen=0.3)
banded('print', FILAMENT, 0.42, 0.0002, axis='Z', amp=0.25)
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


# ============================================================================== side table
TX0, TX1 = TABLE_X
TY0, TY1 = TABLE_Y
TOP_T = 0.022
LEG = 0.036
INS = 0.045                                    # legs inset 45 mm under the top (clears the floor register)
rbox('bambu_table_top', (TX0, TY0, TABLE_H - TOP_T), (TX1, TY1, TABLE_H), 0.004, 'paint_white', segs=3, local=False)
lx = (TX0 + INS, TX1 - INS - LEG)
ly = (TY0 + INS, TY1 - INS - LEG)
for i, x0 in enumerate(lx):
    for j, y0 in enumerate(ly):
        # slightly tapered square leg, felt pad at the foot
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            t = 0.5 - v.co.z                       # 1 at bottom, 0 at top
            w = LEG * (1.0 - 0.22 * t)
            cx, cy = x0 + LEG / 2, y0 + LEG / 2
            v.co = V((cx + v.co.x * w, cy + v.co.y * w, 0.004 + (v.co.z + 0.5) * (TABLE_H - TOP_T - 0.004)))
        bmesh.ops.bevel(bm, geom=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1],
                        offset=0.003, segments=2, profile=0.5, affect='EDGES')
        finish(from_bm('bambu_table_leg_%d%d' % (i, j), bm), 'paint_white', 40)
        cyl('bambu_table_pad_%d%d' % (i, j), LEG * 0.36, (x0 + LEG / 2, y0 + LEG / 2, 0.0),
            (x0 + LEG / 2, y0 + LEG / 2, 0.004), 'felt', verts=20, local=False)
# apron (four rails under the top, between the legs)
AP_H = 0.075
az0, az1 = TABLE_H - TOP_T - AP_H, TABLE_H - TOP_T
ax0, ax1 = lx[0] + LEG * 0.25, lx[1] + LEG * 0.75
ay0, ay1 = ly[0] + LEG * 0.25, ly[1] + LEG * 0.75
rbox('bambu_table_apron_f', (ax0, ay0 - 0.009, az0), (ax1, ay0 + 0.009, az1), 0.002, 'paint_white', local=False)
rbox('bambu_table_apron_b', (ax0, ay1 - 0.009, az0), (ax1, ay1 + 0.009, az1), 0.002, 'paint_white', local=False)
rbox('bambu_table_apron_l', (ax0 - 0.009, ay0, az0), (ax0 + 0.009, ay1, az1), 0.002, 'paint_white', local=False)
rbox('bambu_table_apron_r', (ax1 - 0.009, ay0, az0), (ax1 + 0.009, ay1, az1), 0.002, 'paint_white', local=False)
# lower shelf between the legs
SH_Z = 0.200
rbox('bambu_table_shelf', (lx[0] + 0.006, ly[0] + 0.006, SH_Z - 0.016), (lx[1] + LEG - 0.006, ly[1] + LEG - 0.006, SH_Z),
     0.003, 'paint_white', local=False)

# ============================================================================== printer base
# rubber feet
for sx in (-1, 1):
    for sy in (-1, 1):
        cyl('bambu_foot_%d%d' % (sx, sy), 13, (sx * 150, sy * 170, 0), (sx * 150, sy * 170, 5), 'rubber', verts=24)
# dark skirt + light grey body with a rounded top edge
rbox('bambu_base_skirt', (-181, -196, 4), (181, 196, 16), 10, 'body_dark')
rbox('bambu_base_body', (-185, -200, 13), (185, 200, 70), 14, 'body', segs=4)
# shallow top recess strip where the Y carriage runs (dark) + aluminium Y rail
rbox('bambu_base_ychannel', (-44, -190, 67.5), (44, 190, 70.6), 4, 'body_dark')
rbox('bambu_y_rail', (-11, -185, 70.6), (11, 185, 77.0), 1.2, 'alu')
rbox('bambu_y_rail_slot', (-3, -186, 74.5), (3, 186, 77.2), 0.4, 'body_dark')
# front ventilation slots on the left of the base front
for k in range(6):
    z0 = 28 + k * 5.5
    rbox('bambu_base_vent_%d' % k, (-160, -201.2, z0), (-80, -199.0, z0 + 2.4), 1.0, 'body_dark')
# rear: power inlet + switch block
rbox('bambu_base_inlet', (-140, 199.0, 24), (-100, 201.5, 50), 2.0, 'body_dark')
rbox('bambu_base_switch', (-92, 199.0, 30), (-80, 202.0, 44), 1.5, 'rubber')

# touchscreen pod on the front right (tilted back 18 deg)
tilt = Matrix.Rotation(math.radians(-18), 3, 'X')
rbox('bambu_screen_pod', (82, -212, 16), (182, -196, 72), 8, 'body_dark', rot=tilt, pivot=(132, -204, 16))
bm = bmesh.new()
sw, sh = 74.0, 50.0
co = [(-sw / 2, -sh / 2), (sw / 2, -sh / 2), (sw / 2, sh / 2), (-sw / 2, sh / 2)]
vs = [bm.verts.new((132 + x, -212.35, 44 + z)) for x, z in co]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new('UVMap')
for loop, (x, z) in zip(f.loops, co):
    loop[uv].uv = (x / sw + 0.5, z / sh + 0.5)
bmesh.ops.rotate(bm, verts=bm.verts, cent=V((132, -204, 16)), matrix=tilt)
for v in bm.verts:
    v.co = P(*v.co)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
o = from_bm('bambu_screen', bm)
if o.data.polygons[0].normal.y > 0:
    o.data.flip_normals()
finish(o, 'screen', None)

# ============================================================================== Y bed (sliding)
by = BED_Y
rbox('bambu_bed_carriage', (-38, by - 60, 76), (38, by + 60, 86), 2.5, 'alu_dark')
rbox('bambu_heatbed', (-130, by - 130, 86), (130, by + 130, 91), 3, 'alu_dark', segs=2)
# 4 cable/sensor bumps on the heatbed underside rear + front plate tab
rbox('bambu_bed_cable_box', (-40, by + 118, 78), (40, by + 138, 86), 3, 'body_dark')
rbox('bambu_pei_plate', (-128.5, by - 128.5, 91), (128.5, by + 128.5, 92), 0.45, 'pei', segs=2, angle=60)
rbox('bambu_pei_tab', (-22, by - 138, 91), (22, by - 127, 91.7), 3, 'steel', segs=2, angle=60)

# ============================================================================== Z towers + top beam
TW_X0, TW_X1 = 162.5, 192.5
GY0, GY1 = -20.0, 40.0
for s in (-1, 1):
    xa, xb = sorted((s * TW_X0, s * TW_X1))
    rbox('bambu_tower_%s' % ('L' if s < 0 else 'R'), (xa, GY0, 10), (xb, GY1, 402), 6, 'body', segs=3)
    # tower foot block where it meets the base
    rbox('bambu_tower_foot_%s' % ('L' if s < 0 else 'R'), (xa - 1.5, GY0 - 7, 4), (xb + 1.5, GY1 + 7, 34), 7, 'body', segs=3)
    rbox('bambu_tower_foot_seam_%s' % ('L' if s < 0 else 'R'), (xa - 0.8, GY0 - 6.3, 33.4), (xb + 0.8, GY1 + 6.3, 34.6), 1.0, 'body_dark')
    # inner face: dark Z slot strip
    xi = s * TW_X0
    rbox('bambu_tower_slot_%s' % ('L' if s < 0 else 'R'), (xi - 1.2, GY0 + 12, 60), (xi + 1.2, GY1 - 12, 396), 1.0, 'body_dark')
    # Z smooth rod + lead screw
    cyl('bambu_z_rod_%s' % ('L' if s < 0 else 'R'), 4.0, (s * 150, -2, 70), (s * 150, -2, 400), 'steel', verts=16)
    cyl('bambu_z_screw_%s' % ('L' if s < 0 else 'R'), 4.0, (s * 150, 22, 70), (s * 150, 22, 400), 'steel', verts=16)
    cyl('bambu_z_coupler_%s' % ('L' if s < 0 else 'R'), 7.0, (s * 150, 22, 70), (s * 150, 22, 90), 'alu', verts=20)
rbox('bambu_top_beam', (-192.5, -14, 400), (192.5, 32, 430), 9, 'body', segs=4)
rbox('bambu_top_beam_seam', (-186, -14.8, 413.6), (186, -13.6, 414.6), 0.3, 'body_dark')

# ============================================================================== X gantry
GZ = 180.0
for s in (-1, 1):
    xa, xb = sorted((s * 132, s * 162))
    rbox('bambu_x_endblock_%s' % ('L' if s < 0 else 'R'), (xa, -24, GZ - 32), (xb, 42, GZ + 30), 6, 'body_dark')
rbox('bambu_x_beam', (-134, -1, GZ - 20), (134, 21, GZ + 20), 3, 'alu_dark', segs=2)
rbox('bambu_x_rail', (-128, -3.2, GZ + 2), (128, -1, GZ + 14), 0.6, 'steel')
rbox('bambu_x_belt', (-132, 21, GZ - 12), (132, 23, GZ - 4), 0.4, 'rubber')

# ============================================================================== toolhead
tx = TOOL_X
tyc = -29.0
NOZ = 92.0 + PRINT_H + 0.4
rbox('bambu_th_carriage', (tx - 26, -7, GZ - 22), (tx + 26, -1.5, GZ + 22), 2, 'alu_dark')
rbox('bambu_th_body', (tx - 30, -54, NOZ + 14), (tx + 30, -5, NOZ + 100), 10, 'body', segs=4)
rbox('bambu_th_front', (tx - 28, -58.5, NOZ + 22), (tx + 28, -52, NOZ + 96), 8, 'front_cover', segs=4)
# hotend fan behind a round grille on the front cover
fcz = NOZ + 62
cyl('bambu_th_fan_recess', 21, (tx, -58.9, fcz), (tx, -57.5, fcz), 'fan', verts=40)
for i, R in enumerate((7.5, 12.5, 17.5)):
    torus('bambu_th_grille_%d' % i, (tx, -59.0, fcz), R, 0.9, (0, 1, 0), 'front_cover', seg=40, rseg=6)
torus('bambu_th_grille_rim', (tx, -59.0, fcz), 21.2, 1.3, (0, 1, 0), 'front_cover', seg=48, rseg=8)
for k in range(4):
    a = math.radians(45 + 90 * k)
    rbox('bambu_th_grille_spoke_%d' % k, (tx - 0.8, -59.9, fcz), (tx + 0.8, -58.2, fcz + 20), 0.3, 'front_cover',
         rot=Matrix.Rotation(a, 3, 'Y'), pivot=(tx, -59, fcz))
cyl('bambu_th_grille_hub', 5.5, (tx, -60.0, fcz), (tx, -58.2, fcz), 'front_cover', verts=24, cap_bevel=0.6)
# part-cooling fan housing on the left side + duct under the nozzle
rbox('bambu_th_pcfan', (tx - 41, -52, NOZ + 20), (tx - 29, -10, NOZ + 70), 5, 'body_dark')
rbox('bambu_th_duct', (tx - 30, -52, NOZ + 7), (tx + 22, -10, NOZ + 15), 4, 'body_dark')
# cutter lever on the right side
rbox('bambu_th_cutter', (tx + 29.5, -46, NOZ + 70), (tx + 35, -30, NOZ + 92), 2.5, 'front_cover')
# hotend: silicone sock, heater block edge, brass nozzle
rbox('bambu_th_sock', (tx - 10, tyc - 8, NOZ + 4.2), (tx + 10, tyc + 8, NOZ + 15), 3, 'silicone')
cyl('bambu_th_nozzle_hex', 3.6, (tx, tyc, NOZ + 2.4), (tx, tyc, NOZ + 4.4), 'brass', verts=6, angle=30)
cyl('bambu_th_nozzle_tip', 0.6, (tx, tyc, NOZ), (tx, tyc, NOZ + 2.4), 'brass', r2=2.8, verts=16)
# top: PTFE coupling + umbilical connector
cyl('bambu_th_ptfe_coupling', 5.5, (tx - 6, -30, NOZ + 99), (tx - 6, -30, NOZ + 106), 'body_dark', verts=24, cap_bevel=1)
rbox('bambu_th_connector', (tx + 4, -24, NOZ + 98), (tx + 22, -10, NOZ + 108), 2, 'body_dark')

# ============================================================================== spool holder + spool
SX, SYC, SZC = 95.0, -2.0, 560.0
rbox('bambu_spool_clip', (SX - 20, -20, 426), (SX + 20, 38, 444), 5, 'body_dark')
rbox('bambu_spool_post', (SX - 8, 34, 440), (SX + 8, 46, SZC + 10), 5, 'body_dark')
cyl('bambu_spool_axle', 24.5, (SX, 44, SZC), (SX, -44, SZC), 'body_dark', verts=40, cap_bevel=1.5)
cyl('bambu_spool_axle_cap', 29, (SX, -44, SZC), (SX, -48, SZC), 'body_dark', verts=40, cap_bevel=1.2)
# filament inlet funnel on the clip front
cyl('bambu_spool_inlet', 6, (SX - 25, -26, 436), (SX - 25, -18, 440), 'body_dark', verts=20, r2=4.5)
# spool (built around local Z = spool axis, then turned so the axis runs front-to-back)
spool_rot = Matrix.Rotation(math.radians(90), 4, 'X')
spool_loc = P(SX, SYC, SZC)
W = 0.066 / 2
fl_t = 0.0028
prof_fl = [(0.0275, -W), (0.0995, -W), (0.1, -W + fl_t * 0.5), (0.0995, -W + fl_t), (0.0275, -W + fl_t)]
spool_parts = []
for side, sgn in (('F', -1), ('B', 1)):
    pr = [(r, z * (-sgn) if False else (z if sgn < 0 else -z)) for r, z in prof_fl]
    o = lathe('bambu_spool_flange_' + side, pr, 'spool_flange', segs=72, closed=True)
    spool_parts.append(o)
o = lathe('bambu_spool_core', [(0.0275, -W + fl_t), (0.0275, W - fl_t), (0.0385, W - fl_t), (0.0385, -W + fl_t)],
          'spool_hub', segs=48, closed=True)
spool_parts.append(o)
R_FIL = 0.086
fil = [(0.0385, -W + fl_t + 0.0002), (R_FIL - 0.0015, -W + fl_t + 0.0002), (R_FIL, -W + fl_t + 0.0018),
       (R_FIL, W - fl_t - 0.0018), (R_FIL - 0.0015, W - fl_t - 0.0002), (0.0385, W - fl_t - 0.0002)]
o = lathe('bambu_spool_filament', fil, 'filament_spool', segs=96, closed=True)
spool_parts.append(o)
for o in spool_parts:
    o.matrix_world = Matrix.Translation(spool_loc) @ spool_rot
# loose strand from the bottom-front of the winding into the inlet
tube('bambu_filament_strand', [(SX - 22, SYC - 20, SZC - 85), (SX - 24, -22, 470), (SX - 25, -22, 441)], 0.875,
     'filament_strand', res=8, bev=4)

# ============================================================================== PTFE tube + umbilical
tube('bambu_ptfe_tube', [(SX - 25, -26, 436), (SX - 30, -58, 405), (40, -92, 330), (tx - 4, -58, NOZ + 150),
                         (tx - 6, -32, NOZ + 106)], 2.0, 'ptfe', res=14)
tube('bambu_umbilical', [(tx + 13, -14, NOZ + 108), (tx + 5, 4, NOZ + 140), (-70, 20, NOZ + 150),
                         (-126, 22, GZ + 60), (-140, 18, GZ + 31)], 4.5, 'cable', res=14)

# ============================================================================== in-progress print (pastel vase)
PR_X, PR_Y = tx + 18.0, tyc
prof = []
for i in range(13):
    t = i / 12.0
    z = t * PRINT_H / 1000.0
    r = (21.0 - 3.0 * t + 1.6 * math.sin(math.pi * t)) / 1000.0
    prof.append((r, z))
inner = [(r - 0.0012, z) for r, z in prof[::-1]]
inner[-1] = (inner[-1][0], 0.0010)
pts = [(0.0, 0.0)] + prof + inner + [(0.0, 0.0010)]
o = lathe('bambu_print', pts, 'print', segs=64, angle=50)
o.location = P(PR_X, PR_Y, 92.0)
# brim-less first layer ring slightly wider (elephant foot)
o2 = lathe('bambu_print_first_layer', [(0.0, 0.0), (0.0212, 0.0), (0.0212, 0.0003), (0.0, 0.0003)], 'print', segs=64,
           closed=True)
o2.location = P(PR_X, PR_Y, 92.0)

# ============================================================================== power cable to the left-wall outlet
plug_y = 0.950
rbox('bambu_power_plug', (-2.0795, plug_y - 0.017, 0.262), (-2.052, plug_y + 0.017, 0.298), 0.004, 'plug', local=False)
tube('bambu_power_cable', [
    (-2.052, plug_y, 0.272), (-2.050, plug_y + 0.02, 0.18), (-2.064, plug_y + 0.08, 0.121), (-2.062, plug_y + 0.13, 0.03), (-2.058, plug_y + 0.18, 0.0035),
    (-2.050, 1.200, 0.0035), (-1.86, 1.215, 0.004), (-1.805, 1.19, 0.10), (-1.795, 1.165, 0.45), (-1.790, 1.150, 0.69),
    (-1.786, 1.135, 0.727), (-1.782, 1.100, 0.748), (-1.7775, 1.072, 0.750)], 0.0028, 'cable', local=False, res=10, bev=6)

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
frame = [o for o in pr_objs if not o.name.startswith(('bambu_spool', 'bambu_filament', 'bambu_ptfe', 'bambu_screen'))]
fp = [o.matrix_world @ V(c) for o in frame for c in o.bound_box]
print('FRAME_DIMS_MM', [round((max(p[i] for p in fp) - min(p[i] for p in fp)) * 1000, 1) for i in range(3)])


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
    mid = P(0, 0, 200)

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
        shot(P(520, -760, 420), P(0, -20, 230), 40, 'bambu_34.png', (1100, 1150))
    if not ONLY or 'pod' in ONLY:
        shot(P(60, -420, 170), P(132, -205, 45), 60, 'bambu_pod.png')
    if not ONLY or 'head' in ONLY:
        shot(P(160, -300, 250), P(tx, -40, NOZ + 40), 50, 'bambu_head.png')
    if not ONLY or 'table' in ONLY:
        shot(V((-0.7, -0.4, 1.2)), V((-1.75, 0.9, 0.62)), 30, 'bambu_table.png', (1000, 1150))
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)


if not NO_RENDER:
    previews()
scene.render.filepath = ''
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('SAVED', OUT)
