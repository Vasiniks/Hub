"""
v2_bookrack.py -- wall book rack on the LEFT wall: two white triangular steel brackets screwed to the
wall, one white-painted shelf board on top, an L-shaped white steel bookend at each end, and the
existing books / small items from room.blend re-stood on the new board.

    blender -b --factory-startup --python blender/scripts/v2_bookrack.py -- [--no-render]

Room coordinates (Z-up, metres). Left wall inner face x = -2.08, rack faces +X.
room.blend is only READ (objects appended from it); it is never saved.
Output: blender/scene/parts/bookrack.blend, collection NEW_bookrack, root empty NEW_bookrack_root.
Previews: bookrack_34.png, bookrack_seat.png (rendered in room context, room not saved), bookrack_close.png.
"""
import bpy
import bmesh
import math
import os
import sys
import random
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ROOM = os.path.join(REPO, 'blender', 'scene', 'room.blend')
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
NAME = 'bookrack'
OUT_BLEND = os.path.join(PARTS, NAME + '.blend')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
random.seed(7)

# ------------------------------------------------------------------ dimensions
WALL_X = -2.08
Y_C = 0.80
PLATE_L, PLATE_D, PLATE_T = 0.770, 0.200, 0.018
PLATE_TOP = 1.100                       # books keep their old standing height
PLATE_BOT = PLATE_TOP - PLATE_T
PLATE_Y0, PLATE_Y1 = Y_C - PLATE_L / 2, Y_C + PLATE_L / 2
PLATE_X0, PLATE_X1 = WALL_X + 0.002, WALL_X + 0.002 + PLATE_D     # 2 mm shadow gap to wall
BR_Y = (Y_C - 0.265, Y_C + 0.265)       # bracket centre lines
BR_ARM = 0.190                          # horizontal reach
BR_H = 0.195                            # wall leg height
FL_W, FL_T = 0.035, 0.003               # flange width (y) / thickness
GUS_T = 0.005                           # gusset plate thickness
BE_T, BE_H, BE_D, BE_FOOT = 0.0018, 0.150, 0.120, 0.105   # bookend sheet / height / depth / foot
BE_INSET = 0.006
BE_X0 = PLATE_X0 + (PLATE_D - BE_D) / 2 + 0.01

MESH_BOOKS = ['Mesh_%d' % i for i in range(165, 177)]
SMALL = ['Mesh_177', 'Mesh_178', 'Mesh_160', 'Mesh_161', 'Mesh_162', 'Mesh_163', 'Mesh_164']


# ------------------------------------------------------------------ helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(obj, coll):
    coll.objects.link(obj)
    return obj


def bm_to_obj(bm, name, mat, coll):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    me.materials.append(mat)
    link(ob, coll)
    return ob


def bake_mods(ob, sharp_deg=35):
    """apply all modifiers, shade smooth + sharp by angle."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    me.name = ob.name
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(sharp_deg))


def add_bevel(ob, w, seg, limit='ANGLE', angle=30):
    m = ob.modifiers.new('bev', 'BEVEL')
    m.width = w
    m.segments = seg
    m.limit_method = limit
    m.angle_limit = math.radians(angle)
    m.harden_normals = False
    m.miter_outer = 'MITER_ARC'
    return m


def box_bm(bm, x0, x1, y0, y1, z0, z1):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r['verts']:
        v.co = Vector((x0 + (v.co.x + 0.5) * (x1 - x0), y0 + (v.co.y + 0.5) * (y1 - y0), z0 + (v.co.z + 0.5) * (z1 - z0)))
    return r['verts']


# ------------------------------------------------------------------ materials
def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def mat_powder():
    m = bpy.data.materials.new('br_powder_white')
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = principled(m)
    b.inputs['Base Color'].default_value = (0.80, 0.80, 0.785, 1)
    tc = N.new('ShaderNodeTexCoord')
    nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 40; nz.inputs['Detail'].default_value = 3
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = N.new('ShaderNodeMapRange'); mr.inputs['To Min'].default_value = 0.36; mr.inputs['To Max'].default_value = 0.50
    L.new(nz.outputs['Fac'], mr.inputs['Value']); L.new(mr.outputs['Result'], b.inputs['Roughness'])
    peel = N.new('ShaderNodeTexNoise'); peel.inputs['Scale'].default_value = 900; peel.inputs['Detail'].default_value = 2
    L.new(tc.outputs['Object'], peel.inputs['Vector'])
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.06; bump.inputs['Distance'].default_value = 0.0003
    L.new(peel.outputs['Fac'], bump.inputs['Height']); L.new(bump.outputs['Normal'], b.inputs['Normal'])
    b.inputs['Coat Weight'].default_value = 0.15
    b.inputs['Coat Roughness'].default_value = 0.3
    return m


def mat_paint_wood():
    m = bpy.data.materials.new('br_board_white_paint')
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = principled(m)
    tc = N.new('ShaderNodeTexCoord')
    # faint colour mottling
    nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 12; nz.inputs['Detail'].default_value = 4
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    ramp = N.new('ShaderNodeMix'); ramp.data_type = 'RGBA'
    ramp.inputs['A'].default_value = (0.83, 0.825, 0.81, 1)
    ramp.inputs['B'].default_value = (0.87, 0.865, 0.85, 1)
    L.new(nz.outputs['Fac'], ramp.inputs['Factor']); L.new(ramp.outputs['Result'], b.inputs['Base Color'])
    mr = N.new('ShaderNodeMapRange'); mr.inputs['To Min'].default_value = 0.30; mr.inputs['To Max'].default_value = 0.44
    L.new(nz.outputs['Fac'], mr.inputs['Value']); L.new(mr.outputs['Result'], b.inputs['Roughness'])
    # wood grain telegraphing through the paint (grain runs along the board = local Y)
    wave = N.new('ShaderNodeTexWave'); wave.bands_direction = 'X'
    wave.inputs['Scale'].default_value = 28; wave.inputs['Distortion'].default_value = 6
    wave.inputs['Detail'].default_value = 3; wave.inputs['Detail Scale'].default_value = 1.5
    mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1.0, 0.08, 1.0)
    L.new(tc.outputs['Object'], mp.inputs['Vector']); L.new(mp.outputs['Vector'], wave.inputs['Vector'])
    fine = N.new('ShaderNodeTexNoise'); fine.inputs['Scale'].default_value = 700; fine.inputs['Detail'].default_value = 2
    L.new(tc.outputs['Object'], fine.inputs['Vector'])
    add = N.new('ShaderNodeMath'); add.operation = 'MULTIPLY_ADD'
    L.new(wave.outputs['Fac'], add.inputs[0]); add.inputs[1].default_value = 0.6; L.new(fine.outputs['Fac'], add.inputs[2])
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.035; bump.inputs['Distance'].default_value = 0.0004
    L.new(add.outputs['Value'], bump.inputs['Height']); L.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def mat_zinc():
    m = bpy.data.materials.new('br_screw_zinc')
    m.use_nodes = True
    b = principled(m)
    b.inputs['Base Color'].default_value = (0.70, 0.71, 0.72, 1)
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Roughness'].default_value = 0.30
    return m


def mat_recess():
    m = bpy.data.materials.new('br_screw_recess')
    m.use_nodes = True
    b = principled(m)
    b.inputs['Base Color'].default_value = (0.06, 0.06, 0.065, 1)
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Roughness'].default_value = 0.55
    return m


def mat_felt():
    m = bpy.data.materials.new('br_bumper_clear')
    m.use_nodes = True
    b = principled(m)
    b.inputs['Base Color'].default_value = (0.6, 0.6, 0.58, 1)
    b.inputs['Roughness'].default_value = 0.7
    return m


# ------------------------------------------------------------------ geometry
def build_plate(coll, mat):
    bm = bmesh.new()
    box_bm(bm, -PLATE_D / 2, PLATE_D / 2, -PLATE_L / 2, PLATE_L / 2, -PLATE_T / 2, PLATE_T / 2)
    ob = bm_to_obj(bm, 'bookrack_board', mat, coll)
    ob.location = ((PLATE_X0 + PLATE_X1) / 2, Y_C, (PLATE_TOP + PLATE_BOT) / 2)
    add_bevel(ob, 0.003, 4, angle=60)
    bake_mods(ob, 30)
    return ob


def screw_head(bm_head, bm_rec, pos, axis, d=0.0075, h=0.0022, rot=0.0):
    """pan-head Phillips screw lying on a surface. axis = outward normal (unit Vector)."""
    q = Vector((0, 0, 1)).rotation_difference(axis)
    R = q.to_matrix().to_4x4() @ Matrix.Rotation(rot, 4, 'Z')
    M = Matrix.Translation(pos) @ R
    seg = 16
    rings = [(d / 2, 0.0), (d / 2, h * 0.45), (d * 0.44, h * 0.8), (d * 0.3, h * 0.97), (0.0, h)]
    loops = []
    for r, z in rings[:-1]:
        loops.append([bm_head.verts.new(M @ Vector((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z))) for i in range(seg)])
    top = bm_head.verts.new(M @ Vector((0, 0, h)))
    for a, b in zip(loops, loops[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            bm_head.faces.new((a[i], a[j], b[j], b[i]))
    for i in range(seg):
        bm_head.faces.new((loops[-1][i], loops[-1][(i + 1) % seg], top))
    bm_head.faces.new(list(reversed(loops[0])))
    # cross recess (two dark slivers just proud of the dome top)
    for ang in (0.0, math.pi / 2):
        Rr = M @ Matrix.Rotation(ang, 4, 'Z')
        vs = []
        for x, y, z in [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]:
            vs.append(bm_rec.verts.new(Rr @ Vector((x * d * 0.26, y * d * 0.055, h * 0.55 + z * h * 0.47))))
        for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            bm_rec.faces.new([vs[k] for k in f])


def build_bracket(coll, mat, yc, idx, bm_head, bm_rec):
    """T-section right-triangle bracket: wall flange + top flange + triangular gusset (with lightening hole)."""
    bm = bmesh.new()
    x0 = WALL_X
    ztop = PLATE_BOT
    # wall flange (vertical strip flat on the wall)
    box_bm(bm, x0, x0 + FL_T, yc - FL_W / 2, yc + FL_W / 2, ztop - BR_H, ztop)
    # top flange (under the board)
    box_bm(bm, x0 + FL_T - 0.0005, x0 + BR_ARM, yc - FL_W / 2, yc + FL_W / 2, ztop - FL_T, ztop)
    bev_ob_parts = []
    ob = bm_to_obj(bm, 'bookrack_bracket_%s' % idx, mat, coll)
    add_bevel(ob, 0.0009, 2, angle=40)
    bake_mods(ob)
    # gusset: right triangle in XZ with clipped tips and a rounded-triangle lightening hole
    g = bmesh.new()
    xa, za = x0 + FL_T - 0.0005, ztop - FL_T + 0.0005     # right-angle corner
    reach, drop = BR_ARM - FL_T - 0.004, BR_H - FL_T - 0.006
    outer = [(xa, za), (xa + reach, za), (xa + reach, za - 0.012), (xa + 0.012, za - drop), (xa, za - drop)]
    # hole: inner triangle offset inward, corners arced
    k = 0.030
    hole_pts = []
    tri = [(xa + k * 0.75, za - k * 0.75), (xa + reach - k * 2.1, za - k * 0.75), (xa + k * 0.75, za - drop + k * 2.1)]
    cr = 0.010
    for i, (px, pz) in enumerate(tri):
        p = Vector((px, pz)); pa = Vector(tri[i - 1]); pb = Vector(tri[(i + 1) % 3])
        da = (pa - p).normalized(); db = (pb - p).normalized()
        half = da.angle(db) / 2
        dist = cr / math.tan(half)
        c = p + (da + db).normalized() * (cr / math.sin(half))
        s = p + da * dist; e = p + db * dist
        a0 = math.atan2(s.y - c.y, s.x - c.x); a1 = math.atan2(e.y - c.y, e.x - c.x)
        da_ = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for t in range(6):
            a = a0 + da_ * t / 5
            hole_pts.append((c.x + cr * math.cos(a), c.y + cr * math.sin(a)))
    y0, y1 = yc - GUS_T / 2, yc + GUS_T / 2
    # build outer face and hole face on both sides, bridge
    def ring(pts, y):
        return [g.verts.new((px, y, pz)) for px, pz in pts]
    o0, o1 = ring(outer, y0), ring(outer, y1)
    h0, h1 = ring(hole_pts, y0), ring(hole_pts, y1)
    for ring_a, ring_b in ((o0, o1), (h0, h1)):
        n = len(ring_a)
        for i in range(n):
            j = (i + 1) % n
            g.faces.new((ring_a[i], ring_a[j], ring_b[j], ring_b[i]))
    g.normal_update()
    for side, (oo, hh) in enumerate(((o0, h0), (o1, h1))):
        edges = []
        n = len(oo)
        for i in range(n):
            edges.append(g.edges.get((oo[i], oo[(i + 1) % n])))
        m = len(hh)
        for i in range(m):
            edges.append(g.edges.get((hh[i], hh[(i + 1) % m])))
        bmesh.ops.triangle_fill(g, edges=edges, use_beauty=True, use_dissolve=True)
    bmesh.ops.recalc_face_normals(g, faces=g.faces)
    gob = bm_to_obj(g, 'gus_tmp', mat, coll)
    add_bevel(gob, 0.0012, 2, angle=40)
    bake_mods(gob)
    # join gusset into bracket
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); gob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    # screws: two through the wall flange (either side of the gusset), two up into the board
    screw_head(bm_head, bm_rec, Vector((x0 + FL_T, yc - 0.0105, ztop - 0.040)), Vector((1, 0, 0)), rot=random.uniform(0, 1.5))
    screw_head(bm_head, bm_rec, Vector((x0 + FL_T, yc + 0.0105, ztop - BR_H + 0.028)), Vector((1, 0, 0)), rot=random.uniform(0, 1.5))
    screw_head(bm_head, bm_rec, Vector((x0 + 0.075, yc + 0.0105, ztop - FL_T)), Vector((0, 0, -1)), d=0.0065, h=0.0018, rot=random.uniform(0, 1.5))
    screw_head(bm_head, bm_rec, Vector((x0 + 0.165, yc - 0.0105, ztop - FL_T)), Vector((0, 0, -1)), d=0.0065, h=0.0018, rot=random.uniform(0, 1.5))
    return ob


def build_bookend(coll, mat, side):
    """L-shaped sheet-steel bookend. side=-1 left end (foot points +Y), +1 right end (foot points -Y)."""
    s = -side  # direction the foot points
    y_out = (PLATE_Y0 + BE_INSET) if side < 0 else (PLATE_Y1 - BE_INSET)
    t, H, L, D = BE_T, BE_H, BE_FOOT, BE_D
    prof = [(0, 0), (L, 0), (L, t), (t, t), (t, H), (0, H)]   # (u along foot, z)
    bm = bmesh.new()
    x0, x1 = BE_X0, BE_X0 + D
    z0 = PLATE_TOP
    def P(u, z, x):
        return Vector((x, y_out + s * u, z0 + z))
    ra = [bm.verts.new(P(u, z, x0)) for u, z in prof]
    rb = [bm.verts.new(P(u, z, x1)) for u, z in prof]
    n = len(prof)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
    bm.faces.new(ra)
    bm.faces.new(list(reversed(rb)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    def edges_where(pred):
        return [e for e in bm.edges if pred(e)]

    def along(e, axis):
        d = (e.verts[1].co - e.verts[0].co).normalized()
        return abs(d[axis]) > 0.99
    mid = lambda e: (e.verts[0].co + e.verts[1].co) / 2
    # rounded top corners of the upright (edges along Y at z=H)
    top = edges_where(lambda e: along(e, 1) and abs(mid(e).z - (z0 + H)) < 1e-5)
    bmesh.ops.bevel(bm, geom=top, offset=0.022, segments=8, affect='EDGES', profile=0.5, clamp_overlap=True)
    # rounded far corners of the foot (edges along Z at the foot tip)
    tipy = y_out + s * L
    tip = edges_where(lambda e: along(e, 2) and abs(mid(e).y - tipy) < 1e-5)
    bmesh.ops.bevel(bm, geom=tip, offset=0.016, segments=6, affect='EDGES', profile=0.5, clamp_overlap=True)
    # the bend
    outer = edges_where(lambda e: along(e, 0) and abs(mid(e).y - y_out) < 1e-5 and abs(mid(e).z - z0) < 1e-5)
    bmesh.ops.bevel(bm, geom=outer, offset=0.004, segments=5, affect='EDGES', profile=0.5, clamp_overlap=True)
    inner = edges_where(lambda e: along(e, 0) and abs(mid(e).y - (y_out + s * t)) < 1e-5 and abs(mid(e).z - (z0 + t)) < 1e-5)
    bmesh.ops.bevel(bm, geom=inner, offset=0.0022, segments=5, affect='EDGES', profile=0.5, clamp_overlap=True)
    ob = bm_to_obj(bm, 'bookrack_bookend_%s' % ('L' if side < 0 else 'R'), mat, coll)
    add_bevel(ob, 0.0005, 1, angle=50)
    bake_mods(ob, 40)
    return ob, y_out, s


# ------------------------------------------------------------------ appended room items
def append_items(coll):
    names = MESH_BOOKS + SMALL
    with bpy.data.libraries.load(ROOM, link=False) as (src, dst):
        dst.objects = [n for n in names if n in src.objects]
    # world matrices are runtime-only: link the appended parent chain temporarily and evaluate it
    tmp = bpy.data.collections.new('tmp_parents')
    bpy.context.scene.collection.children.link(tmp)
    for o in bpy.data.objects:
        if not o.users_collection and o not in dst.objects:
            tmp.objects.link(o)
    for ob in dst.objects:
        link(ob, coll)
    bpy.context.view_layer.update()
    objs = {ob.name: (ob, ob.matrix_world.copy()) for ob in dst.objects}
    for name, (ob, mw) in objs.items():
        ob.parent = None
        ob.matrix_world = mw
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    bpy.context.view_layer.update()
    return {n: o for n, (o, _) in objs.items()}


def wbbox(obs):
    pts = []
    for o in obs:
        mw = o.matrix_world
        pts += [mw @ v.co for v in o.data.vertices]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def apply_world(obs, M):
    for o in obs:
        o.matrix_world = M @ o.matrix_world
    bpy.context.view_layer.update()


def main():
    reset()
    scene = bpy.context.scene
    coll = bpy.data.collections.new('NEW_' + NAME)
    scene.collection.children.link(coll)
    root = bpy.data.objects.new('NEW_%s_root' % NAME, None)
    root.empty_display_size = 0.1
    root.location = (WALL_X, Y_C, PLATE_TOP)
    link(root, coll)

    powder, paint, zinc, rec = mat_powder(), mat_paint_wood(), mat_zinc(), mat_recess()

    board = build_plate(coll, paint)
    bm_head, bm_rec = bmesh.new(), bmesh.new()
    brackets = [build_bracket(coll, powder, yc, i, bm_head, bm_rec) for i, yc in zip(('L', 'R'), BR_Y)]
    # two small screws per bookend foot (bookends are screwed down so they act as fixed end stops)
    bookends = []
    for side in (-1, 1):
        be, y_out, s = build_bookend(coll, powder, side)
        bookends.append((be, y_out, s))
        for xo in (0.030, 0.090):
            screw_head(bm_head, bm_rec, Vector((BE_X0 + xo, y_out + s * 0.070, PLATE_TOP + BE_T)), Vector((0, 0, 1)),
                       d=0.0065, h=0.0015, rot=random.uniform(0, 1.5))
    heads = bm_to_obj(bm_head, 'bookrack_screws', zinc, coll)
    for p in heads.data.polygons:
        p.use_smooth = True
    recs = bm_to_obj(bm_rec, 'bookrack_screw_recess', rec, coll)

    # ---------------------------------------------------------- books & small items
    items = append_items(coll)
    yL = bookends[0][1] + BE_T            # inner face of left upright
    yR = bookends[1][1] - BE_T            # inner face of right upright
    foot_L = (bookends[0][1], bookends[0][1] + BE_FOOT)
    foot_R = (bookends[1][1] - BE_FOOT, bookends[1][1])
    FRONT = PLATE_X1 - 0.012              # book spines ~12 mm back from the board edge

    def on_foot(y0, y1):
        return (y0 < foot_L[1] and y1 > foot_L[0]) or (y0 < foot_R[1] and y1 > foot_R[0])

    def place_upright(obs, y_left, front=None, zrot=0.0, xcentre=None):
        if zrot:
            mn, mx = wbbox(obs)
            c = (mn + mx) / 2
            apply_world(obs, Matrix.Translation(c) @ Matrix.Rotation(zrot, 4, 'Z') @ Matrix.Translation(-c))
        mn, mx = wbbox(obs)
        dx = 0.0
        if front is not None:
            dx = front - mx.x
        elif xcentre is not None:
            dx = xcentre - (mn.x + mx.x) / 2
        w = mx.y - mn.y
        lift = BE_T if on_foot(y_left, y_left + w) else 0.0
        apply_world(obs, Matrix.Translation((dx, y_left - mn.y, PLATE_TOP + lift - mn.z)))
        return y_left + w, (mx.z - mn.z)

    cur = yL + 0.0008
    last_h = 0
    for i, n in enumerate(MESH_BOOKS[:-1]):
        o = items[n]
        cur, last_h = place_upright([o], cur, front=FRONT + random.uniform(-0.006, 0.003))
        cur += random.choice((0.0004, 0.0008, 0.0015, 0.003))
    # last book leans left against the stack
    lean = items[MESH_BOOKS[-1]]
    mn, mx = wbbox([lean])
    h = mx.z - mn.z; w = mx.y - mn.y
    th = math.radians(11)
    Yn = cur - 0.0005
    yp = Yn + (h * math.sin(th) if last_h >= h * math.cos(th) else last_h * math.tan(th))
    pivot_old = Vector(((mn.x + mx.x) / 2, mn.y, mn.z))
    dx = FRONT - 0.004 - mx.x
    pivot_new = Vector((pivot_old.x + dx, yp, PLATE_TOP))
    apply_world([lean], Matrix.Translation(pivot_new) @ Matrix.Rotation(th, 4, 'X') @ Matrix.Translation(-pivot_old))
    cur = yp + w * math.cos(th)

    # right end: yellow folder standing against the right bookend
    fold = items['Mesh_178']
    mn, mx = wbbox([fold])
    fw = mx.y - mn.y
    place_upright([fold], yR - 0.0008 - fw, front=FRONT - 0.004)
    right_limit = yR - 0.0008 - fw

    # middle: small card, tray, pen cup, desk toy -- spread with even gaps
    groups = [
        (['Mesh_177'], dict(front=FRONT - 0.02)),
        (['Mesh_160'], dict(xcentre=PLATE_X0 + PLATE_D * 0.52, zrot=math.radians(-7))),
        (['Mesh_161'], dict(xcentre=PLATE_X0 + PLATE_D * 0.40, zrot=math.radians(20))),
        (['Mesh_162', 'Mesh_163', 'Mesh_164'], dict(xcentre=PLATE_X0 + PLATE_D * 0.55)),
    ]
    # widths after rotation
    widths = []
    for obs_n, kw in groups:
        obs = [items[n] for n in obs_n]
        if kw.get('zrot'):
            mn, mx = wbbox(obs); c = (mn + mx) / 2
            apply_world(obs, Matrix.Translation(c) @ Matrix.Rotation(kw['zrot'], 4, 'Z') @ Matrix.Translation(-c))
            kw['zrot'] = 0.0
        mn, mx = wbbox(obs)
        widths.append(mx.y - mn.y)
    free = right_limit - cur - sum(widths)
    gap = free / (len(groups) + 1)
    print('bookrack: free space for small items %.4f, gap %.4f' % (free, gap))
    y = cur + gap * 0.6
    for (obs_n, kw), w in zip(groups, widths):
        place_upright([items[n] for n in obs_n], y, **kw)
        y += w + gap * (1.1 if obs_n[0] != 'Mesh_177' else 0.7)

    # ---------------------------------------------------------- parent all to root (keep world)
    bpy.context.view_layer.update()
    for o in list(coll.objects):
        if o is root:
            continue
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()
        o.matrix_world = mw
    bpy.context.view_layer.update()

    tris = 0
    for o in coll.objects:
        if o.type == 'MESH':
            o.data.calc_loop_triangles()
            tris += len(o.data.loop_triangles)
    print('bookrack: TRIS', tris)
    for o in sorted(coll.objects, key=lambda o: o.name):
        if o.type == 'MESH':
            mn, mx = wbbox([o])
            print('  %-28s %s %s' % (o.name, tuple(round(v, 4) for v in mn), tuple(round(v, 4) for v in mx)))
    for img in bpy.data.images:
        print('image', img.name, img.filepath, img.packed_file is not None)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    print('saved', OUT_BLEND)


# ------------------------------------------------------------------ previews
def gpu_setup(scene, spp=64):
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'CUDA'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = spp
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPTIX'
    except TypeError:
        pass
    scene.render.resolution_x, scene.render.resolution_y = 1280, 800
    scene.render.resolution_percentage = 100


def shoot(scene, loc, tgt, lens, path):
    cam = scene.camera
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', path)


def new_cam(scene):
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    cam.data.clip_start = 0.01
    scene.collection.objects.link(cam)
    scene.camera = cam


def render_studio():
    bpy.ops.wm.open_mainfile(filepath=OUT_BLEND)
    scene = bpy.context.scene
    gpu_setup(scene)
    new_cam(scene)
    world = bpy.data.worlds.new('grey'); scene.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.18, 0.18, 0.18, 1); bg.inputs['Strength'].default_value = 0.6
    # wall + floor context planes
    wm = bpy.data.materials.new('ctx_wall'); wm.use_nodes = True
    principled(wm).inputs['Base Color'].default_value = (0.36, 0.42, 0.52, 1)
    principled(wm).inputs['Roughness'].default_value = 0.9
    bm = bmesh.new(); box_bm(bm, WALL_X - 0.05, WALL_X, -0.5, 2.0, 0.3, 2.2)
    wall = bm_to_obj(bm, 'ctx_wall', wm, scene.collection)
    def light(name, loc, tgt, energy, size):
        l = bpy.data.lights.new(name, 'AREA'); l.energy = energy; l.size = size
        o = bpy.data.objects.new(name, l); scene.collection.objects.link(o)
        o.location = loc; o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    c = (-1.98, 0.8, 1.12)
    light('key', (-1.0, -0.3, 1.9), c, 120, 0.8)
    light('fill', (-1.1, 1.9, 1.3), c, 40, 1.2)
    light('rim', (-1.7, 0.8, 2.3), c, 40, 0.5)
    shoot(scene, (-1.40, 0.12, 1.36), (-1.99, 0.80, 1.12), 35, os.path.join(PARTS, NAME + '_close.png'))
    shoot(scene, (-1.62, 0.30, 0.86), (-2.02, 0.56, 1.02), 35, os.path.join(PARTS, NAME + '_under.png'))


def render_room():
    bpy.ops.wm.open_mainfile(filepath=ROOM)          # read-only: never saved
    scene = bpy.context.scene
    gpu_setup(scene)
    old = bpy.data.objects['SHELF_root']
    def hide(o):
        o.hide_render = True; o.hide_viewport = True
        for ch in o.children:
            hide(ch)
    hide(old)
    with bpy.data.libraries.load(OUT_BLEND, link=False) as (src, dst):
        dst.collections = ['NEW_' + NAME]
    scene.collection.children.link(dst.collections[0])
    new_cam(scene)
    shoot(scene, (-1.05, -0.05, 1.50), (-2.00, 0.80, 1.14), 32, os.path.join(PARTS, NAME + '_34.png'))
    shoot(scene, (0.0, -0.16, 1.175), (-2.0, 0.8, 1.2), 35, os.path.join(PARTS, NAME + '_seat.png'))


if __name__ == '__main__':
    if '--render-only' not in ARGS:
        main()
    if not NO_RENDER:
        render_studio()
        render_room()
