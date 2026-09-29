"""
v2_robot.py -- the owner's real FRC robot (team 1360 "Andromeda", Onshape export) reduced to a room prop.

    blender -b --factory-startup --python blender/scripts/v2_robot.py -- [--no-render] [--budget 140000]

Source (owner-supplied CAD, git-ignored): assets/source/robot_andromeda/Andromeda.glb
  353 MB, 6,007 nodes, 901 meshes, 100 flat CAD colours, ~8.1 M unique / ~20.5 M instanced tris.

Pipeline
  1. PREFILTER (pure JSON, before Blender ever sees the file): walk the node tree, compute every mesh
     node's world box from the accessor min/max, drop fasteners/electronics/bearings/internals by name
     and anything < 15 mm, and write a flat GLB (same binary chunk, only kept nodes, world matrices
     baked, Z-up preserved) -> assets/source/robot_andromeda/andromeda_filtered.glb (+ sidecar json).
  2. Import that (~600 parts), weld, planar-dissolve, then collapse-decimate every unique mesh to a
     share of the triangle budget weighted by its size (instances share the reduced mesh).
  3. Re-map the 100 CAD colours onto ~11 procedural materials; join everything per material.
  4. Bumper: the CAD 'BUMPERS' part is kept with a fabric material; "1360" in white Arial Bold is
     added as thin real geometry on two opposite bumper faces.
  5. Place at real scale on the floor where the old robot stood (projects.ts 'frc-robot':
     three [-1.12, 0, 0.34], rotY 0.86 -> Blender (-1.12, -0.34, 0), rotZ 0.86).
Output: blender/scene/parts/robot.blend, collection NEW_robot, root NEW_robot_root (room coords).
"""
import bpy
import bmesh
import json
import math
import os
import re
import struct
import sys
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
SRCDIR = os.path.join(REPO, 'assets', 'source', 'robot_andromeda')
SRC = os.path.join(SRCDIR, 'Andromeda.glb')
FILT = os.path.join(SRCDIR, 'andromeda_filtered.glb')
SIDE = os.path.join(SRCDIR, 'andromeda_filtered.json')
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT = os.path.join(PARTS, 'robot.blend')
ROOM = os.path.join(REPO, 'blender', 'scene', 'room.blend')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
BUDGET = int(ARGS[ARGS.index('--budget') + 1]) if '--budget' in ARGS else 128000
PLACE = Vector((-1.12, -0.34, 0.0))
YAW = 0.86
MIN_SIZE = 0.015

DROP = re.compile(
    r'screw|bolt|\bnut\b|nut_|nylock|rivet|washer|standoff|zip.?tie|spacer|bearing|bushing|capacitor|'
    r'choke|C_0603|R_0603|Rez\d|LM2596|CP_Radial|shcs|bhcs|fhcs|shaft collar|retaining|e-clip|snap ring|'
    r'dowel|\bpin\b|insert|grommet|heat.?set|terminal|header|connector|jst|usb|crystal|inductor|diode|'
    r'resistor|button head|cap screw|thread|shoulder|HSG|OrangePi5\b|Vortex Shaft|hex shaft|tube plug|'
    r'dust cover|pinion|\bshaft\b|FACE\b|sot-|soic|qfn|smd', re.I)


# ----------------------------------------------------------------------------------------------- 1
def prefilter():
    if os.path.exists(FILT) and os.path.exists(SIDE) and os.path.getmtime(FILT) > os.path.getmtime(SRC) \
            and os.path.getmtime(FILT) > os.path.getmtime(__file__):
        return json.load(open(SIDE))
    with open(SRC, 'rb') as f:
        f.read(12)
        clen, _ = struct.unpack('<II', f.read(8))
        js = json.loads(f.read(clen))
        blen, _ = struct.unpack('<II', f.read(8))
        binchunk = f.read(blen)
    N, A, Ms = js['nodes'], js['accessors'], js['meshes']

    def local(n):
        if 'matrix' in n:
            return np.array(n['matrix']).reshape(4, 4).T
        T = np.eye(4)
        if 'translation' in n: T[:3, 3] = n['translation']
        if 'rotation' in n:
            x, y, z, w = n['rotation']
            T[:3, :3] = T[:3, :3] @ np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        if 'scale' in n: T[:3, :3] = T[:3, :3] @ np.diag(n['scale'])
        return T
    parent = {c: i for i, n in enumerate(N) for c in n.get('children', [])}
    W = {}

    def world(i):
        if i not in W:
            W[i] = (world(parent[i]) if i in parent else np.eye(4)) @ local(N[i])
        return W[i]

    def chain(i):
        out = []
        while i in parent:
            i = parent[i]; out.append(N[i].get('name', ''))
        return out[::-1]
    kept, dropped, tri_all = [], 0, 0
    for i, n in enumerate(N):
        if 'mesh' not in n: continue
        m = Ms[n['mesh']]
        lo = np.min([A[p['attributes']['POSITION']]['min'] for p in m['primitives']], 0)
        hi = np.max([A[p['attributes']['POSITION']]['max'] for p in m['primitives']], 0)
        tris = sum(A[p['indices']]['count'] // 3 for p in m['primitives'])
        tri_all += tris
        w = world(i)
        c = np.array([[x, y, z, 1] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]) @ w.T
        wlo, whi = c[:, :3].min(0), c[:, :3].max(0)
        name = n.get('name', '')
        # hidden electronics: everything on the stacked Pi/power boards except the boards themselves
        if DROP.search(name) or (whi - wlo).max() < MIN_SIZE:
            dropped += tris
            continue
        kept.append(dict(node=i, name=name, mesh=n['mesh'], tris=tris, chain=chain(i),
                         lo=wlo.tolist(), hi=whi.tolist(), world=w))
    # flat GLB: glTF is Y-up; the Onshape data is Z-up, so pre-rotate so Blender's Y-up->Z-up
    # conversion lands it back exactly: gltf (x, z, -y)
    C = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], float)
    mesh_map = {}
    new_nodes, new_meshes = [], []
    for k, r in enumerate(kept):
        if r['mesh'] not in mesh_map:
            mesh_map[r['mesh']] = len(new_meshes)
            mm = dict(Ms[r['mesh']]); mm['name'] = 'M%04d' % len(new_meshes)
            new_meshes.append(mm)
        new_nodes.append({'name': 'P%04d' % k, 'mesh': mesh_map[r['mesh']],
                          'matrix': (C @ r['world']).T.reshape(-1).tolist()})
    js2 = dict(js)
    js2['nodes'] = new_nodes
    js2['meshes'] = new_meshes
    js2['scenes'] = [{'name': 'Root', 'nodes': list(range(len(new_nodes)))}]
    js2['scene'] = 0
    body = json.dumps(js2, separators=(',', ':')).encode()
    body += b' ' * ((4 - len(body) % 4) % 4)
    with open(FILT, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(body) + 8 + len(binchunk)))
        f.write(struct.pack('<II', len(body), 0x4E4F534A)); f.write(body)
        f.write(struct.pack('<II', len(binchunk), 0x004E4942)); f.write(binchunk)
    side = dict(tri_all=tri_all, tri_dropped=dropped, nodes_total=len(N),
                parts={'P%04d' % k: dict(name=r['name'], sub=(r['chain'][1] if len(r['chain']) > 1 else ''),
                                         tris=r['tris'], lo=r['lo'], hi=r['hi']) for k, r in enumerate(kept)})
    json.dump(side, open(SIDE, 'w'), indent=0)
    return side


side = prefilter()
print('PREFILTER source instanced tris', side['tri_all'], 'dropped', side['tri_dropped'],
      'kept parts', len(side['parts']))

# ----------------------------------------------------------------------------------------------- 2
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=FILT, import_shading='NORMALS', import_scene_as_collection=False)
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in list(bpy.context.scene.objects):
    if o.type != 'MESH':
        bpy.data.objects.remove(o, do_unlink=True)
print('IMPORTED', len(objs), 'objects', len({o.data for o in objs}), 'meshes')


def ntris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def info(o):
    return side['parts'].get(o.name.split('.')[0], {})


tri_in = sum(ntris(o.data) for o in objs)

# floor = lowest wheel point; frame centre = centre of the CAD bumper footprint
bump = [o for o in objs if info(o).get('name', '').upper().startswith('BUMPER')]
assert bump, 'no BUMPERS part'
bb = [o.matrix_world @ Vector(c) for o in bump for c in o.bound_box]
bl = Vector([min(v[i] for v in bb) for i in range(3)]); bh = Vector([max(v[i] for v in bb) for i in range(3)])
floor_z = min((o.matrix_world @ v.co).z for o in objs
              if re.search(r'wheel|tread|swerve', info(o).get('name', ''), re.I) for v in o.data.vertices)
CEN = Vector(((bl.x + bh.x) / 2, (bl.y + bh.y) / 2, floor_z))
print('BUMPER box', [round(x, 4) for x in bl], [round(x, 4) for x in bh], 'floor', round(floor_z, 4))

# decimation budget per unique mesh: size-weighted share, clamped, solved by bisection
by_mesh = {}
for o in objs:
    by_mesh.setdefault(o.data, []).append(o)
stats = []
for me, users in by_mesh.items():
    xs = [v.co for v in me.vertices]
    d = Vector([max(v[i] for v in xs) - min(v[i] for v in xs) for i in range(3)])
    area = 2 * (d.x * d.y + d.y * d.z + d.z * d.x)
    stats.append((me, len(users), ntris(me), area, max(d)))
LETTER_TRIS = 6000


def total(B):
    return sum(k * min(t, max(24, B * a ** 0.75)) for me, k, t, a, mx in stats)
lo_b, hi_b = 1.0, 1e9
for _ in range(80):
    mid = math.sqrt(lo_b * hi_b)
    (lo_b, hi_b) = (mid, hi_b) if total(mid) < BUDGET - LETTER_TRIS else (lo_b, mid)
B = lo_b
tmp = bpy.data.objects.new('tmp', None)
for me, k, t, a, mx in stats:
    target = min(t, max(24, B * a ** 0.75))
    o = bpy.data.objects.new('dec', me); bpy.context.scene.collection.objects.link(o)
    w = o.modifiers.new('weld', 'WELD'); w.merge_threshold = 0.00005
    dm = o.modifiers.new('plan', 'DECIMATE'); dm.decimate_type = 'DISSOLVE'
    dm.angle_limit = math.radians(1.0); dm.delimit = {'NORMAL'} if False else set()
    dg = bpy.context.evaluated_depsgraph_get()
    m1 = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    o.modifiers.clear()
    t1 = ntris(m1)
    if t1 > target:
        o.data = m1
        dc = o.modifiers.new('col', 'DECIMATE'); dc.decimate_type = 'COLLAPSE'
        dc.ratio = max(0.002, target / t1); dc.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        m2 = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        o.modifiers.clear()
    else:
        m2 = m1
    bpy.data.objects.remove(o)
    for mat_i, mat in enumerate(me.materials):
        if mat_i < len(m2.materials): m2.materials[mat_i] = mat
    for u in by_mesh[me]:
        u.data = m2
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
tri_dec = sum(ntris(o.data) for o in objs)
print('DECIMATE', tri_in, '->', tri_dec, 'B', round(B, 1))

# ----------------------------------------------------------------------------------------------- 3
def hexrgb(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def make_mat(name, col, rough, metal=0.0, bump=0.0, bump_scale=300.0, trans=0.0, fabric=False, coat=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value = (*col, 1)
    bs.inputs['Metallic'].default_value = metal
    if trans:
        bs.inputs['Transmission Weight'].default_value = trans
        bs.inputs['IOR'].default_value = 1.586
    if coat:
        bs.inputs['Coat Weight'].default_value = coat
    tc = N.new('ShaderNodeTexCoord')
    nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = bump_scale
    nz.inputs['Detail'].default_value = 4.0
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = rough * 0.85; mr.inputs['To Max'].default_value = min(1, rough * 1.15)
    L.new(nz.outputs['Fac'], mr.inputs['Value']); L.new(mr.outputs['Result'], bs.inputs['Roughness'])
    if fabric:
        wv = N.new('ShaderNodeTexWave'); wv.inputs['Scale'].default_value = 900; wv.bands_direction = 'Z'
        wv2 = N.new('ShaderNodeTexWave'); wv2.inputs['Scale'].default_value = 900; wv2.bands_direction = 'X'
        L.new(tc.outputs['Object'], wv.inputs['Vector']); L.new(tc.outputs['Object'], wv2.inputs['Vector'])
        mx = N.new('ShaderNodeMath'); mx.operation = 'MULTIPLY'
        L.new(wv.outputs['Fac'], mx.inputs[0]); L.new(wv2.outputs['Fac'], mx.inputs[1])
        bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.35
        bp.inputs['Distance'].default_value = 0.0004
        L.new(mx.outputs['Value'], bp.inputs['Height']); L.new(bp.outputs['Normal'], bs.inputs['Normal'])
        bs.inputs['Sheen Weight'].default_value = 0.6
    elif bump:
        bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = 0.0002
        L.new(nz.outputs['Fac'], bp.inputs['Height']); L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    return m


MATS = {
    'alu':       make_mat('robot_aluminium', hexrgb('#c4c8cc'), 0.32, 1.0, 0.04, 900),
    'darkalu':   make_mat('robot_black_anodised', hexrgb('#2a2c30'), 0.38, 1.0, 0.03, 900),
    'black':     make_mat('robot_black_plastic', hexrgb('#1a1b1e'), 0.5, 0.0, 0.05, 400),
    'grey':      make_mat('robot_grey_plastic', hexrgb('#6d7278'), 0.5, 0.0, 0.05, 400),
    'white':     make_mat('robot_white_plastic', hexrgb('#e9eaec'), 0.45, 0.0, 0.04, 400),
    'rubber':    make_mat('robot_rubber', hexrgb('#141414'), 0.85, 0.0, 0.25, 700),
    'poly':      make_mat('robot_polycarbonate', hexrgb('#dfe6ec'), 0.08, 0.0, 0.0, 300, trans=0.9),
    'red':       make_mat('robot_red_anodised', hexrgb('#b3191c'), 0.35, 0.6, 0.03, 900),
    'blue':      make_mat('robot_blue_anodised', hexrgb('#1d5fb5'), 0.35, 0.6, 0.03, 900),
    'orange':    make_mat('robot_orange', hexrgb('#ef7d10'), 0.45, 0.0, 0.04, 400),
    'yellow':    make_mat('robot_yellow', hexrgb('#f2c21b'), 0.45, 0.0, 0.04, 400),
    'green':     make_mat('robot_green_pcb', hexrgb('#2f7d3a'), 0.4, 0.0, 0.03, 400, coat=0.3),
    'purple':    make_mat('robot_purple_anodised', hexrgb('#7a4a9c'), 0.35, 0.6, 0.03, 900),
    'tan':       make_mat('robot_nylon_tan', hexrgb('#d8cdb0'), 0.55, 0.0, 0.05, 400),
    'fabric':    make_mat('robot_bumper_fabric', hexrgb('#a3161b'), 0.8, 0.0, fabric=True),
    'number':    make_mat('robot_bumper_number', hexrgb('#f4f4f2'), 0.7, 0.0, fabric=True),
}


def classify(rgb, pname):
    n = pname.lower()
    if n.startswith('bumper'): return 'fabric'
    if re.search(r'tread|wheel|belt|compliant|roller', n) and not re.search(r'hub|bracket|plate', n): return 'rubber'
    r, g, b = rgb
    mxc, mnc = max(rgb), min(rgb)
    sat = (mxc - mnc) / mxc if mxc > 0 else 0
    if sat < 0.12:
        if b > r + 0.08 and mxc > 0.7: return 'poly'
        if mxc > 0.93: return 'white'
        if mxc > 0.55: return 'alu'
        if mxc > 0.33: return 'grey'
        if mxc > 0.17: return 'darkalu'
        return 'black'
    if b > r and b > g:
        if mxc > 0.85 and mnc > 0.55: return 'poly'
        if r > 0.5 and g < r: return 'purple'
        return 'blue'
    if r > 0.6 and b > 0.6 and g < r: return 'purple'
    if g > r and g > b: return 'green'
    if r > 0.6 and g > 0.6 and b > 0.45: return 'tan'
    if r > 0.5 and g < 0.2: return 'red'
    if r > 0.5 and g < 0.45: return 'red' if g < 0.2 else 'orange'
    if r > 0.5 and g < 0.7: return 'orange'
    if r > 0.5 and g >= 0.7: return 'yellow'
    return 'grey'


def mat_rgb(m):
    try:
        bs = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        c = bs.inputs['Base Color'].default_value
        # glTF importer stores linear; the CAD file names carry the sRGB values
    except StopIteration:
        c = m.diffuse_color
    try:
        return [float(x) for x in m.name.split('_')[:3]]
    except ValueError:
        return [c[0], c[1], c[2]]


usage = {}
for o in objs:
    pname = info(o).get('name', '')
    me = o.data
    for i, slot in enumerate(o.material_slots):
        m = slot.material
        key = classify(mat_rgb(m) if m else [0.6, 0.6, 0.6], pname)
        usage[key] = usage.get(key, 0) + 1
        slot.link = 'OBJECT'; slot.material = MATS[key]
print('MATERIAL use', usage)

# join everything per material --------------------------------------------------------------
col = bpy.data.collections.new('NEW_robot'); bpy.context.scene.collection.children.link(col)
root = bpy.data.objects.new('NEW_robot_root', None); col.objects.link(root)
groups = {}
for o in objs:
    o.data = o.data.copy() if o.data.users > 1 else o.data
    # bake object-level material into mesh slots so joining keeps it
    ms = [s.material for s in o.material_slots]
    o.data.materials.clear()
    for m in ms: o.data.materials.append(m)
    for s in o.material_slots: s.link = 'DATA'
    o.data.transform(o.matrix_world); o.matrix_world = Matrix()
    groups.setdefault(ms[0].name if len(set(ms)) == 1 else 'mixed', []).append(o)
bpy.ops.object.select_all(action='DESELECT')
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.join()
big = bpy.context.view_layer.objects.active
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='MATERIAL')
bpy.ops.object.mode_set(mode='OBJECT')
parts = [o for o in bpy.context.scene.objects if o.type == 'MESH']

# recentre: bumper centre at XY origin, wheels on z=0
T = Matrix.Translation(-CEN)
for o in parts:
    me = o.data
    me.transform(T)
    for an in [a.name for a in me.attributes if a.name in ('custom_normal', 'sharp_face', 'sharp_edge')]:
        me.attributes.remove(me.attributes[an])
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(35))
    # drop unused slots
    used = {p.material_index for p in me.polygons}
    mat = me.materials[next(iter(used))] if used else None
    me.materials.clear(); me.materials.append(mat)
    for p in me.polygons: p.material_index = 0
    o.name = 'Robot_' + mat.name.replace('robot_', '')
    o.data.name = o.name
    for uc in list(o.users_collection): uc.objects.unlink(o)
    col.objects.link(o); o.parent = root
bl -= CEN; bh -= CEN

# ----------------------------------------------------------------------------------------------- 4
fab = next(o for o in parts if o.name.startswith('Robot_bumper_fabric'))
fab_me = fab.data
fv = np.array([v.co[:] for v in fab_me.vertices])
print('BUMPER local box', fv.min(0).round(4), fv.max(0).round(4))

FONT = r'C:\Windows\Fonts\arialbd.ttf'
DIGIT_H = 0.100


def number_on_face(axis_sign, axis):
    """'1360' on the bumper face whose outward normal is axis_sign * axis ('x' or 'y')."""
    cu = bpy.data.curves.new('num', 'FONT'); cu.body = '1360'
    try:
        cu.font = bpy.data.fonts.load(FONT, check_existing=True)
    except RuntimeError:
        pass
    cu.align_x = 'CENTER'; cu.align_y = 'CENTER'
    cu.size = DIGIT_H / 0.716; cu.extrude = 0.0006; cu.resolution_u = 4
    cu.space_character = 1.05
    t = bpy.data.objects.new('num', cu); bpy.context.scene.collection.objects.link(t)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(t.evaluated_get(dg))
    bpy.data.objects.remove(t); bpy.data.curves.remove(cu)
    # text lies in XY facing +Z; stand it up facing +Y then rotate to the wanted face
    me.transform(Matrix.Rotation(math.radians(90), 4, 'X'))
    # now reading direction +X, up +Z, facing -Y; turn it to the wanted face
    ang = {('y', -1): 0.0, ('x', 1): math.pi / 2, ('y', 1): math.pi, ('x', -1): -math.pi / 2}[(axis, axis_sign)]
    me.transform(Matrix.Rotation(ang, 4, 'Z'))
    # face position: ray-cast to the fabric surface at mid height along the face centre line
    zc = (bl.z + bh.z) / 2
    d = Vector((axis_sign, 0, 0)) if axis == 'x' else Vector((0, axis_sign, 0))
    start = Vector((0, 0, zc)) + d * 2.0
    hit_depth = None
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromObject(fab, bpy.context.evaluated_depsgraph_get())
    hit = bvh.ray_cast(start, -d)
    assert hit[0] is not None, 'bumper face not hit'
    pos = hit[0]
    # letters: back face flush at the fabric, raised 0.6 mm; project each vertex onto the surface
    me.transform(Matrix.Translation(pos + d * 0.0009))
    o = bpy.data.objects.new('Robot_number_1360_%s%s' % ('+' if axis_sign > 0 else '-', axis), me)
    col.objects.link(o); o.parent = root
    sw = o.modifiers.new('wrap', 'SHRINKWRAP'); sw.target = fab; sw.wrap_method = 'PROJECT'
    sw.use_project_x = axis == 'x'; sw.use_project_y = axis == 'y'
    sw.use_negative_direction = True; sw.use_positive_direction = True; sw.offset = 0.0009
    sw.wrap_mode = 'OUTSIDE_SURFACE'
    me.materials.append(MATS['number'])
    return o


NUM_AXIS = ARGS[ARGS.index('--num-axis') + 1] if '--num-axis' in ARGS else 'x'
nums = [number_on_face(+1, NUM_AXIS), number_on_face(-1, NUM_AXIS)]

# ----------------------------------------------------------------------------------------------- 5
root.matrix_world = Matrix.Translation(PLACE) @ Matrix.Rotation(YAW, 4, 'Z')
for o in col.objects:
    if o.type == 'MESH':
        for p in o.data.polygons: p.use_smooth = True
tri_out = 0
dg = bpy.context.evaluated_depsgraph_get()
for o in col.objects:
    if o.type == 'MESH':
        tri_out += ntris(o.evaluated_get(dg).data)
allv = [o.matrix_world @ v.co for o in col.objects if o.type == 'MESH' for v in o.data.vertices]
wl = Vector([min(v[i] for v in allv) for i in range(3)]); wh = Vector([max(v[i] for v in allv) for i in range(3)])
print('ROBOT tris out', tri_out, 'objects', len([o for o in col.objects if o.type == 'MESH']))
print('ROBOT world box', [round(x, 3) for x in wl], [round(x, 3) for x in wh])
meta = dict(tri_source_instanced=side['tri_all'], tri_after_filter=tri_in, tri_out=tri_out,
            world_lo=list(wl), world_hi=list(wh), place=list(PLACE), yaw=YAW,
            bumper_local=[list(bl), list(bh)])
json.dump(meta, open(os.path.join(PARTS, 'robot_meta.json'), 'w'), indent=1)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('SAVED', OUT)

# ----------------------------------------------------------------------------------------------- previews
OLD_ROBOT_ROOT = 'Node_286'


def gpu(sc, spp=64):
    p = bpy.context.preferences.addons['cycles'].preferences
    p.compute_device_type = 'CUDA'; p.refresh_devices()
    for d in p.devices: d.use = (d.type == 'CUDA')
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'GPU'; sc.cycles.samples = spp
    sc.cycles.use_denoising = True
    try: sc.cycles.denoiser = 'OPTIX'
    except TypeError: pass
    sc.render.resolution_x, sc.render.resolution_y = 1280, 800


def shot(sc, loc, target, lens, name):
    cd = bpy.data.cameras.new('cam'); cd.lens = lens; cd.clip_start = 0.02
    cam = bpy.data.objects.new('cam_' + name, cd); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(PARTS, 'robot_%s.png' % name)
    bpy.ops.render.render(write_still=True)


if not NO_RENDER and '--room-only' not in ARGS:
    sc = bpy.context.scene
    gpu(sc)
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1); bg.inputs['Strength'].default_value = 0.6
    fl = bpy.data.meshes.new('floor'); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=4); bm.to_mesh(fl)
    flo = bpy.data.objects.new('preview_floor', fl); sc.collection.objects.link(flo)
    flo.location = PLACE
    fm = bpy.data.materials.new('floor'); fm.use_nodes = True
    fb = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    fb.inputs['Base Color'].default_value = (0.35, 0.35, 0.36, 1); fb.inputs['Roughness'].default_value = 0.6
    fl.materials.append(fm)
    c = root.matrix_world.translation
    for nm, off, en, sz in (('key', (1.6, -1.8, 2.2), 900, 1.2), ('fill', (-2.0, -0.8, 1.2), 250, 2.0),
                            ('rim', (-0.6, 2.2, 1.8), 500, 1.0)):
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = sz
        lo_ = bpy.data.objects.new(nm, ld); sc.collection.objects.link(lo_)
        lo_.location = c + Vector(off)
        lo_.rotation_euler = (c + Vector((0, 0, 0.25)) - lo_.location).to_track_quat('-Z', 'Y').to_euler()
    R = root.matrix_world.to_3x3()
    mid = c + Vector((0, 0, 0.26))
    shot(sc, c + R @ Vector((1.25, -1.35, 0.95)), mid, 40, '34')
    ax = +1 if NUM_AXIS == 'x' else 0
    nrm = R @ (Vector((1, 0, 0)) if NUM_AXIS == 'x' else Vector((0, 1, 0)))
    face = c + nrm * 0.43 + Vector((0, 0, 0.095))
    side_ = R @ (Vector((0, 1, 0)) if NUM_AXIS == 'x' else Vector((1, 0, 0)))
    shot(sc, face + nrm * 0.55 + side_ * 0.25 + Vector((0, 0, 0.12)), face, 50, 'bumper')
    nrm2 = -nrm
    face2 = c + nrm2 * 0.43 + Vector((0, 0, 0.095))
    shot(sc, face2 + nrm2 * 0.9 - side_ * 0.3 + Vector((0, 0, 0.3)), face2 + Vector((0, 0, 0.08)), 40, 'bumper_other')

if not NO_RENDER:
    bpy.ops.wm.open_mainfile(filepath=ROOM)          # read-only: never saved
    sc = bpy.context.scene
    old = bpy.data.objects.get(OLD_ROBOT_ROOT)
    retire = []
    if old:
        stack = [old]
        while stack:
            o = stack.pop(); retire.append(o.name); stack.extend(o.children)
            o.hide_render = True; o.hide_viewport = True
    print('RETIRE', sorted(retire))
    with bpy.data.libraries.load(OUT, link=False) as (src, dst):
        dst.collections = ['NEW_robot']
    sc.collection.children.link(dst.collections[0])
    gpu(sc)
    shot(sc, (1.06, -0.96, 1.63), (-0.3, 0.95, 1.0), 24, 'room')
    shot(sc, (0.35, -1.25, 1.35), (-1.12, -0.34, 0.25), 32, 'room_near')
