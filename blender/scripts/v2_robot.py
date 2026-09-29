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
BUDGET = int(ARGS[ARGS.index('--budget') + 1]) if '--budget' in ARGS else 146000
PLACE = Vector((-1.12, -0.34, 0.0))
YAW = 0.86
MIN_SIZE = 0.015
# owner: the hopper (bucket + its extension) walls are polycarbonate; their screws/nuts show through it,
# so those two sub-assemblies keep their hardware (rebuilt below as clean low-poly proxies)
HOPPER_SUBS = ('250 - Bucket', 'Assembly 1 <4>')
def is_hopper(sub):
    return sub in HOPPER_SUBS or re.sub(r'\s*<\d+>$', '', sub) in HOPPER_SUBS


HW = re.compile(r'screw|nut|nut_|nylock|lock nut', re.I)

DROP = re.compile(
    r'screw|bolt|\bnut\b|nut_|nylock|rivet|washer|standoff|zip.?tie|spacer|bearing|bushing|capacitor|'
    r'choke|C_0603|R_0603|Rez\d|LM2596|CP_Radial|shcs|bhcs|fhcs|shaft collar|retaining|e-clip|snap ring|'
    r'dowel|\bpin\b|insert|grommet|heat.?set|terminal|header|connector|jst|usb|crystal|inductor|diode|'
    r'resistor|button head|cap screw|thread|shoulder|HSG|OrangePi5\b|Vortex Shaft|hex shaft|tube plug|'
    r'dust cover|pinion|\bshaft\b|FACE\b|sot-|soic|qfn|smd', re.I)


# ----------------------------------------------------------------------------------------------- 1
def prefilter():
    key = '%s|%s|floor|hw3' % (DROP.pattern, MIN_SIZE)
    if os.path.exists(FILT) and os.path.exists(SIDE) and os.path.getmtime(FILT) > os.path.getmtime(SRC):
        old = json.load(open(SIDE))
        if old.get('key') == key:
            return old
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
        ch = chain(i)
        hw = len(ch) > 1 and is_hopper(ch[1]) and bool(HW.search(name))
        if not hw and (DROP.search(name) or (whi - wlo).max() < MIN_SIZE):
            dropped += tris
            continue
        kept.append(dict(node=i, name=name, mesh=n['mesh'], tris=tris, chain=ch, hw=hw,
                         lo=wlo.tolist(), hi=whi.tolist(), world=w))
    # nothing may hang below the wheel contact plane (a loose top-level copy of 100-004 sits 4 mm under it)
    floor = min(r['lo'][2] for r in kept if re.search(r'swerve|tread|wheel', r['name'], re.I))
    for r in [r for r in kept if r['lo'][2] < floor - 0.002]:
        print('PREFILTER below floor, dropped:', r['name'], r['chain'])
        kept.remove(r); dropped += r['tris']
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
    side = dict(key=key, tri_all=tri_all, tri_dropped=dropped, nodes_total=len(N),
                parts={'P%04d' % k: dict(name=r['name'], sub=(r['chain'][1] if len(r['chain']) > 1 else ''),
                                         tris=r['tris'], lo=r['lo'], hi=r['hi'], hw=r['hw']) for k, r in enumerate(kept)})
    json.dump(side, open(SIDE, 'w'), indent=0)
    return side




side = prefilter()
print('PREFILTER source instanced tris', side['tri_all'], 'dropped', side['tri_dropped'],
      'kept parts', len(side['parts']))


def ntris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def info(o):
    return side['parts'].get(o.name.split('.')[0], {})


# ----------------------------------------------------------------------------------------------- materials
def hexrgb(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def make_mat(name, col, rough, metal=0.0, bump=0.0, bump_scale=300.0, trans=0.0, fabric=False, coat=0.0, sss=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value = (*col, 1)
    bs.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*col, 1)
    if trans:
        bs.inputs['Transmission Weight'].default_value = trans
        bs.inputs['IOR'].default_value = 1.586
    if coat:
        bs.inputs['Coat Weight'].default_value = coat
    if sss:
        bs.inputs['Subsurface Weight'].default_value = sss
        bs.inputs['Subsurface Radius'].default_value = (0.004, 0.003, 0.001)
    tc = N.new('ShaderNodeTexCoord')
    nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = bump_scale
    nz.inputs['Detail'].default_value = 4.0
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = rough * 0.85; mr.inputs['To Max'].default_value = min(1, rough * 1.15)
    L.new(nz.outputs['Fac'], mr.inputs['Value']); L.new(mr.outputs['Result'], bs.inputs['Roughness'])
    if fabric:
        # woven cordura: two crossed fine wave bands -> weave bump, low tinted sheen
        wv = N.new('ShaderNodeTexWave'); wv.inputs['Scale'].default_value = 700; wv.bands_direction = 'Z'
        wv2 = N.new('ShaderNodeTexWave'); wv2.inputs['Scale'].default_value = 700; wv2.bands_direction = 'X'
        L.new(tc.outputs['Object'], wv.inputs['Vector']); L.new(tc.outputs['Object'], wv2.inputs['Vector'])
        mx = N.new('ShaderNodeMath'); mx.operation = 'MULTIPLY'
        L.new(wv.outputs['Fac'], mx.inputs[0]); L.new(wv2.outputs['Fac'], mx.inputs[1])
        bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.3
        bp.inputs['Distance'].default_value = 0.0003
        L.new(mx.outputs['Value'], bp.inputs['Height']); L.new(bp.outputs['Normal'], bs.inputs['Normal'])
        bs.inputs['Sheen Weight'].default_value = 0.12
        bs.inputs['Sheen Tint'].default_value = (*[min(1, c * 1.6 + 0.05) for c in col], 1)
    elif bump:
        bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = 0.0002
        L.new(nz.outputs['Fac'], bp.inputs['Height']); L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    return m


def make_polycarb():
    # clear 1/8" polycarbonate: faint blue-grey tint, glossy, directional scuffs in the roughness
    m = bpy.data.materials.new('robot_polycarbonate'); m.use_nodes = True
    N = m.node_tree.nodes; L = m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    col = hexrgb('#dde4ea')
    bs.inputs['Base Color'].default_value = (*col, 1); m.diffuse_color = (*col, 0.25)
    bs.inputs['Transmission Weight'].default_value = 0.95
    bs.inputs['IOR'].default_value = 1.58
    tc = N.new('ShaderNodeTexCoord')
    mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1.0, 1.0, 40.0)
    L.new(tc.outputs['Object'], mp.inputs['Vector'])
    sc_ = N.new('ShaderNodeTexNoise'); sc_.inputs['Scale'].default_value = 60; sc_.inputs['Detail'].default_value = 8
    L.new(mp.outputs['Vector'], sc_.inputs['Vector'])
    blot = N.new('ShaderNodeTexNoise'); blot.inputs['Scale'].default_value = 9
    L.new(tc.outputs['Object'], blot.inputs['Vector'])
    mx = N.new('ShaderNodeMath'); mx.operation = 'MULTIPLY'
    L.new(sc_.outputs['Fac'], mx.inputs[0]); L.new(blot.outputs['Fac'], mx.inputs[1])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 0.15; mr.inputs['From Max'].default_value = 0.45
    mr.inputs['To Min'].default_value = 0.05; mr.inputs['To Max'].default_value = 0.12
    L.new(mx.outputs['Value'], mr.inputs['Value']); L.new(mr.outputs['Result'], bs.inputs['Roughness'])
    return m


def classify(rgb, pname, part=None):
    n = pname.lower()
    if n.startswith('bumper'): return 'fabric'
    if 'game piece' in n: return 'ball'
    if part and is_hopper(part.get('sub', '')) and not part.get('hw'):
        d = sorted(h - l for l, h in zip(part['lo'], part['hi']))
        if d[0] <= 0.0065 and d[1] > 0.10:            # thin, large sheet = a hopper wall
            return 'poly'
    if re.search(r'tread|wheel|belt|compliant|roller', n) and not re.search(r'hub|bracket|plate|block', n):
        return 'rubber'
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
    if r > 0.5 and g < 0.7: return 'orange'
    if r > 0.5: return 'yellow'
    return 'grey'


def cad_rgb(m):
    # Onshape names every material by its sRGB colour: "r_g_b_0_0"
    try:
        return [float(x) for x in re.sub(r'\.\d{3}$', '', m.name).split('_')[:3]]
    except ValueError:
        c = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED').inputs['Base Color'].default_value
        return [c[0], c[1], c[2]]


# ----------------------------------------------------------------------------------------------- 2 import
bpy.ops.wm.read_factory_settings(use_empty=True)
MATS = {
    'alu':     make_mat('robot_aluminium', hexrgb('#c4c8cc'), 0.32, 1.0, 0.04, 900),
    'darkalu': make_mat('robot_black_anodised', hexrgb('#2a2c30'), 0.38, 1.0, 0.03, 900),
    'black':   make_mat('robot_black_plastic', hexrgb('#1a1b1e'), 0.5, 0.0, 0.05, 400),
    'grey':    make_mat('robot_grey_plastic', hexrgb('#6d7278'), 0.5, 0.0, 0.05, 400),
    'white':   make_mat('robot_white_plastic', hexrgb('#e9eaec'), 0.45, 0.0, 0.04, 400),
    'rubber':  make_mat('robot_rubber', hexrgb('#161616'), 0.85, 0.0, 0.25, 700),
    'poly':    make_polycarb(),
    'ball':    make_mat('robot_foam_ball', hexrgb('#f3c417'), 0.82, 0.0, 0.35, 260, sss=0.08),
    'red':     make_mat('robot_red_anodised', hexrgb('#b3191c'), 0.35, 0.6, 0.03, 900),
    'blue':    make_mat('robot_blue_anodised', hexrgb('#1d5fb5'), 0.35, 0.6, 0.03, 900),
    'orange':  make_mat('robot_orange', hexrgb('#ef7d10'), 0.45, 0.0, 0.04, 400),
    'yellow':  make_mat('robot_yellow', hexrgb('#f2c21b'), 0.45, 0.0, 0.04, 400),
    'green':   make_mat('robot_green_pcb', hexrgb('#2f7d3a'), 0.4, 0.0, 0.03, 400, coat=0.3),
    'purple':  make_mat('robot_purple_anodised', hexrgb('#7a4a9c'), 0.35, 0.6, 0.03, 900),
    'tan':     make_mat('robot_nylon_tan', hexrgb('#d8cdb0'), 0.55, 0.0, 0.05, 400),
    'fabric':  make_mat('robot_bumper_fabric', hexrgb('#8a0c12'), 0.85, 0.0, fabric=True),
    'number':  make_mat('robot_bumper_number', hexrgb('#f2f2ef'), 0.75, 0.0, fabric=True),
}
bpy.ops.import_scene.gltf(filepath=FILT, import_shading='NORMALS', import_scene_as_collection=False)
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in list(bpy.context.scene.objects):
    if o.type != 'MESH':
        bpy.data.objects.remove(o, do_unlink=True)
print('IMPORTED', len(objs), 'objects', len({o.data for o in objs}), 'meshes')
tri_in = sum(ntris(o.data) for o in objs)

# consolidate 100 CAD colours -> ~14 procedural materials (object-level slots for now)
usage, okey = {}, {}
for o in objs:
    pname = info(o).get('name', '')
    keys = []
    for slot in o.material_slots:
        key = classify(cad_rgb(slot.material) if slot.material else [0.6] * 3, pname, info(o))
        slot.link = 'OBJECT'; slot.material = MATS[key]; keys.append(key)
        usage[key] = usage.get(key, 0) + 1
    okey[o.name] = keys[0] if keys else 'alu'
print('MATERIAL use', usage)


# hopper hardware -> clean low-poly proxies built in each CAD part's own frame (button-head screws with
# shank, hex nuts), so they read through the clear polycarbonate without costing 16k tris each
def hw_proxy(me, is_screw):
    V = np.array([v.co[:] for v in me.vertices])
    lo, hi = V.min(0), V.max(0); dims = hi - lo; c = (lo + hi) / 2
    ax = int(np.argmax(dims)) if is_screw else int(np.argmin(dims))
    o1, o2 = [i for i in range(3) if i != ax]
    bm = bmesh.new()

    def frame(a, r1, r2):                      # axial a, radial offsets -> local point
        p = c.copy(); p[ax] = a; p[o1] += r1; p[o2] += r2
        return p
    if is_screw:
        a = V[:, ax]; rad = np.hypot(V[:, o1] - c[o1], V[:, o2] - c[o2])
        L = dims[ax]
        end_lo = rad[a < lo[ax] + 0.15 * L].max(); end_hi = rad[a > hi[ax] - 0.15 * L].max()
        head_at_hi = end_hi > end_lo
        rh = max(end_lo, end_hi); rs = max(min(end_lo, end_hi), 0.0008)
        big = a[rad > 1.25 * rs]
        hh = (hi[ax] - big.min()) if head_at_hi else (big.max() - lo[ax])
        hh = min(max(hh, 0.001), 0.6 * L)
        sgn = 1 if head_at_hi else -1
        base = hi[ax] - hh if head_at_hi else lo[ax] + hh
        tip = lo[ax] if head_at_hi else hi[ax]
        n = 10
        rings = [(tip, rs), (base, rs), (base, rh * 0.98), (base + sgn * hh * 0.35, rh),
                 (base + sgn * hh * 0.75, rh * 0.72), (base + sgn * hh, rh * 0.25)]
        vs = [[bm.verts.new(frame(z, r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)))
               for k in range(n)] for z, r in rings]
        for j in range(len(vs) - 1):
            for k in range(n):
                bm.faces.new((vs[j][k], vs[j][(k + 1) % n], vs[j + 1][(k + 1) % n], vs[j + 1][k]))
        bm.faces.new(vs[0][::-1]); bm.faces.new(vs[-1])
    else:
        rr = 0.5 * max(dims[o1], dims[o2]) / math.cos(math.pi / 6) * 0.93
        rr = min(rr, 0.5 * max(dims[o1], dims[o2]))
        vs = [[bm.verts.new(frame(z, rr * math.cos(math.pi / 3 * k), rr * math.sin(math.pi / 3 * k)))
               for k in range(6)] for z in (lo[ax], hi[ax])]
        for k in range(6):
            bm.faces.new((vs[0][k], vs[0][(k + 1) % 6], vs[1][(k + 1) % 6], vs[1][k]))
        bm.faces.new(vs[0][::-1]); bm.faces.new(vs[1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    out = bpy.data.meshes.new(me.name + '_proxy'); bm.to_mesh(out); bm.free()
    for m in me.materials: out.materials.append(m)
    return out


hw_meshes, bad = {}, []
for o in list(objs):
    if info(o).get('hw'):
        if o.data not in hw_meshes:
            hw_meshes[o.data] = hw_proxy(o.data, 'screw' in info(o)['name'].lower())
        px = hw_meshes[o.data]
        pw = np.array([(o.matrix_world @ v.co)[:] for v in px.vertices])
        lo_, hi_ = np.array(info(o)['lo']), np.array(info(o)['hi'])
        if (pw.min(0) < lo_ - 0.002).any() or (pw.max(0) > hi_ + 0.002).any():
            print('   proxy outside CAD box, dropped', info(o)['name'], pw.min(0).round(3), lo_.round(3))
            bad.append(o); continue
        o.data = px
        for s in o.material_slots:
            s.link = 'OBJECT'; s.material = MATS['darkalu']        # black-oxide steel hardware
        okey[o.name] = 'hw'
for o in bad:
    objs.remove(o); bpy.data.objects.remove(o)
HW_DATA = set(hw_meshes.values())
print('HOPPER hardware proxies', sum(1 for o in objs if o.data in HW_DATA), 'objects')
for o in sorted(objs, key=lambda o: min((o.matrix_world @ v.co).z for v in o.data.vertices))[:4]:
    print('   lowest part', o.name, info(o).get('name'), info(o).get('sub'),
          round(min((o.matrix_world @ v.co).z for v in o.data.vertices), 4))

# bumper box + floor (lowest wheel point) in CAD coords
bump = [o for o in objs if info(o).get('name', '').upper().startswith('BUMPER')]
assert bump, 'no BUMPERS part'
bv = np.array([(o.matrix_world @ v.co)[:] for o in bump for v in o.data.vertices])
bl, bh = Vector(bv.min(0)), Vector(bv.max(0))
floor_z = min((o.matrix_world @ v.co).z for o in objs
              if re.search(r'wheel|tread|swerve', info(o).get('name', ''), re.I) for v in o.data.vertices)
CEN = Vector(((bl.x + bh.x) / 2, (bl.y + bh.y) / 2, floor_z))
rel = bv - np.array(CEN)
B_OUT = float(np.abs(rel[:, :2]).max())                                   # outer half size
B_IN = float(np.max(np.abs(rel[:, :2]), 1).min())                          # plywood inner face
B_Z0, B_Z1 = float(rel[:, 2].min()), float(rel[:, 2].max())
print('BUMPER half in/out %.4f %.4f  z %.4f..%.4f  floor %.4f' % (B_IN, B_OUT, B_Z0, B_Z1, floor_z))

# ----------------------------------------------------------------------------------------------- visibility
# Orthographic ray grids from 25 directions around/above the robot. A part's hit count ~ how much of it
# can be seen from outside; parts never hit are internals (inside gearboxes, under covers) and go.
sc = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
hits = {}
C0 = CEN + Vector((0, 0, 0.28))
RAD = 0.95
STEP = 0.011
dirs = [(math.radians(a), math.radians(e)) for e in (6, 35, 65) for a in range(0, 360, 45)] + [(0, math.radians(90))]
for az, el in dirs:
    d = -Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    u = d.cross(Vector((0, 0, 1)))
    u = u.normalized() if u.length > 1e-6 else Vector((1, 0, 0))
    v = u.cross(d).normalized()
    n = int(2 * RAD / STEP)
    for i in range(n):
        for j in range(n):
            org = C0 - d * 2.0 + u * (-RAD + i * STEP) + v * (-RAD + j * STEP)
            for _ in range(4):
                ok, loc, nrm, idx, ob, mw = sc.ray_cast(dg, org, d)
                if not ok: break
                nm = ob.original.name if hasattr(ob, 'original') else ob.name
                if okey.get(nm) == 'poly':
                    hits[nm] = hits.get(nm, 0) + 0.25
                    org = loc + d * 0.0005
                    continue
                hits[nm] = hits.get(nm, 0) + 1
                break
print('VISIBILITY rays done, parts hit', len(hits), 'of', len(objs))

# delete CAD bumper (rebuilt below) and hidden parts
hidden = [o for o in objs if hits.get(o.name, 0) < 2 or o in bump]
tri_hidden = sum(ntris(o.data) for o in hidden if o not in bump)
print('HIDDEN parts removed', len(hidden) - len(bump), 'tris', tri_hidden)
for o in hidden:
    objs.remove(o); bpy.data.objects.remove(o)

# ----------------------------------------------------------------------------------------------- decimate
by_mesh = {}
for o in objs:
    by_mesh.setdefault(o.data, []).append(o)


def reduce(me, mods):
    o = bpy.data.objects.new('dec', me); sc.collection.objects.link(o)
    for kind, kw in mods:
        m = o.modifiers.new(kind, kind)
        for k, val in kw.items(): setattr(m, k, val)
    g = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(o.evaluated_get(g))
    bpy.data.objects.remove(o)
    return out


stats = []
for me, users in by_mesh.items():
    if me in HW_DATA:
        stats.append([me, me, len(users), ntris(me), 1e9]); continue
    m1 = reduce(me, [('WELD', dict(merge_threshold=0.00005)),
                     ('DECIMATE', dict(decimate_type='DISSOLVE', angle_limit=math.radians(1.0)))])
    w = max(hits.get(u.name, 0) for u in users)
    stats.append([me, m1, len(users), ntris(m1), w])
tri_dis = sum(k * t for _, _, k, t, _ in stats)
FIXED_TRIS = 10000                   # rebuilt bumper + two numbers


def total(Bv):
    return sum(k * min(t, max(24, Bv * w ** 0.8)) for _, _, k, t, w in stats)


lo_b, hi_b = 1e-3, 1e7
for _ in range(90):
    mid = math.sqrt(lo_b * hi_b)
    (lo_b, hi_b) = (mid, hi_b) if total(mid) < BUDGET - FIXED_TRIS else (lo_b, mid)
Bv = lo_b
GOAL = BUDGET - FIXED_TRIS
for it in range(4):                  # collapse overshoots on small parts: re-aim until the total fits
    out = []
    for me, m1, k, t1, w in stats:
        target = min(t1, max(24, Bv * w ** 0.8))
        m2 = reduce(m1, [('DECIMATE', dict(decimate_type='COLLAPSE', ratio=max(0.003, target / t1),
                                           use_collapse_triangulate=True))]) if t1 > target else m1
        out.append(m2)
    got = sum(k * ntris(m2) for (me, m1, k, t1, w), m2 in zip(stats, out))
    print('  decimate pass', it, 'B %.3f' % Bv, 'tris', got)
    if got <= GOAL * 1.01 or it == 3:
        break
    for (me, m1, k, t1, w), m2 in zip(stats, out):
        if m2 is not m1: bpy.data.meshes.remove(m2)
    Bv *= (GOAL / got) ** 1.3
for (me, m1, k, t1, w), m2 in zip(stats, out):
    for u in by_mesh[me]:
        u.data = m2
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
tri_dec = sum(ntris(o.data) for o in objs)
print('DECIMATE in %d -> dissolved %d -> %d' % (tri_in - tri_hidden, tri_dis, tri_dec))

# ----------------------------------------------------------------------------------------------- 3 join
col = bpy.data.collections.new('NEW_robot'); sc.collection.children.link(col)
root = bpy.data.objects.new('NEW_robot_root', None); col.objects.link(root)
for o in objs:
    if o.data.users > 1: o.data = o.data.copy()
    ms = [s.material for s in o.material_slots]
    o.data.materials.clear()
    for m in ms: o.data.materials.append(m)
    for s in o.material_slots: s.link = 'DATA'
    o.data.transform(o.matrix_world); o.matrix_world = Matrix()
bpy.ops.object.select_all(action='DESELECT')
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.join()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='MATERIAL')
bpy.ops.object.mode_set(mode='OBJECT')
parts = [o for o in sc.objects if o.type == 'MESH']
T = Matrix.Translation(-CEN)
for o in parts:
    me = o.data
    me.transform(T)
    for an in [a.name for a in me.attributes if a.name in ('custom_normal', 'sharp_face', 'sharp_edge')]:
        me.attributes.remove(me.attributes[an])
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(35))
    used = {p.material_index for p in me.polygons}
    mat = me.materials[next(iter(used))]
    me.materials.clear(); me.materials.append(mat)
    for p in me.polygons: p.material_index = 0
    o.name = 'Robot_' + mat.name.replace('robot_', ''); me.name = o.name
    for uc in list(o.users_collection): uc.objects.unlink(o)
    col.objects.link(o); o.parent = root
for o in parts:
    if o.name.startswith('Robot_polycarbonate'):
        o.visible_shadow = False          # clear sheet: must not shade the hopper interior like a solid
zmin, zobj = min((min(v.co.z for v in o.data.vertices), o.name) for o in parts)
print('LOWEST after decimation %.4f (%s) -> re-seated on z=0' % (zmin, zobj))
for o in parts: o.data.transform(Matrix.Translation((0, 0, -zmin)))
B_Z0 -= zmin; B_Z1 -= zmin

# ----------------------------------------------------------------------------------------------- 4 bumper
# FRC bumper section: 3/4" plywood backing, two pool noodles, fabric pulled over -> flat back, round-
# shouldered outer face with a faint valley where the noodles meet; swept round the frame perimeter.
BD = B_OUT - B_IN
RO, RI = 0.024, 0.004
ZM = (B_Z0 + B_Z1) / 2


def arc(cx, cz, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * t / n), cz + r * math.sin(a0 + (a1 - a0) * t / n)) for t in range(n + 1)]


prof = []
prof += arc(RI, B_Z0 + RI, RI, math.pi, 1.5 * math.pi, 3)[1:]                    # inner-bottom
prof += arc(BD - RO, B_Z0 + RO, RO, 1.5 * math.pi, 2 * math.pi, 8)               # outer-bottom shoulder
for t in range(1, 14):                                                           # outer face, noodle valley
    z = B_Z0 + RO + (B_Z1 - B_Z0 - 2 * RO) * t / 14
    prof.append((BD - 0.0022 * math.exp(-((z - ZM) / 0.010) ** 2), z))
prof += arc(BD - RO, B_Z1 - RO, RO, 0, 0.5 * math.pi, 8)                          # outer-top shoulder
prof += arc(RI, B_Z1 - RI, RI, 0.5 * math.pi, math.pi, 3)[1:]                      # inner-top
prof += [(0.0, B_Z1 - RI - (B_Z1 - B_Z0 - 2 * RI) * t / 4) for t in range(1, 4)]  # plywood back


def ring(dd):
    a = B_IN + dd
    rc = 0.003 + dd * (0.016 - 0.003) / BD
    pts = []
    for k in range(4):
        ang0 = k * math.pi / 2
        c = Vector((math.cos(ang0 + math.pi / 4), math.sin(ang0 + math.pi / 4))) * math.sqrt(2) * (a - rc)
        for t in range(7):
            ang = ang0 + (math.pi / 2) * t / 6
            pts.append(c + rc * Vector((math.cos(ang), math.sin(ang))))
    return pts


bm = bmesh.new()
grid = [[bm.verts.new((p.x, p.y, z)) for p in ring(dd)] for dd, z in prof]
nj, ni = len(grid), len(grid[0])
for j in range(nj):
    for i in range(ni):
        bm.faces.new((grid[j][i], grid[j][(i + 1) % ni], grid[(j + 1) % nj][(i + 1) % ni], grid[(j + 1) % nj][i]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
fab_me = bpy.data.meshes.new('Robot_bumper_fabric'); bm.to_mesh(fab_me); bm.free()
fab_me.materials.append(MATS['fabric'])
fab = bpy.data.objects.new('Robot_bumper_fabric', fab_me); col.objects.link(fab); fab.parent = root
for p in fab_me.polygons: p.use_smooth = True
fab_me.set_sharp_from_angle(angle=math.radians(60))

FONT = r'C:\Windows\Fonts\arialbd.ttf'
DIGIT_H = 0.095


def number_on_face(axis_sign, axis):
    """'1360' on the bumper face whose outward normal is axis_sign * axis ('x' or 'y')."""
    cu = bpy.data.curves.new('num', 'FONT'); cu.body = '1360'
    if os.path.exists(FONT):
        cu.font = bpy.data.fonts.load(FONT, check_existing=True)
    cu.size = 1.0; cu.resolution_u = 5; cu.space_character = 1.04
    t = bpy.data.objects.new('num', cu); sc.collection.objects.link(t)
    g = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(t.evaluated_get(g))
    bpy.data.objects.remove(t); bpy.data.curves.remove(cu)
    vs = np.array([v.co[:] for v in me.vertices]); lo, hi = vs.min(0), vs.max(0)
    s = DIGIT_H / (hi[1] - lo[1])
    me.transform(Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, 0))))
    bm = bmesh.new(); bm.from_mesh(me)
    for k in range(1, 16):                                   # horizontal cuts so it can follow the curve
        z = -DIGIT_H / 2 + DIGIT_H * k / 16
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, z, 0), plane_no=(0, 1, 0))
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    # XY text facing +Z -> reading +X, up +Z, facing -Y; then turn to the wanted face
    me.transform(Matrix.Rotation(math.radians(90), 4, 'X'))
    ang = {('y', -1): 0.0, ('x', 1): math.pi / 2, ('y', 1): math.pi, ('x', -1): -math.pi / 2}[(axis, axis_sign)]
    me.transform(Matrix.Translation((0, 0, ZM)) @ Matrix.Rotation(ang, 4, 'Z')
                 @ Matrix.Translation((0, -(B_OUT + 0.02), 0)))
    o = bpy.data.objects.new('Robot_number_1360_%s%s' % ('pos' if axis_sign > 0 else 'neg', axis.upper()), me)
    col.objects.link(o); o.parent = root
    sw = o.modifiers.new('wrap', 'SHRINKWRAP'); sw.target = fab; sw.wrap_method = 'PROJECT'
    sw.use_project_x = axis == 'x'; sw.use_project_y = axis == 'y'
    sw.use_negative_direction = True; sw.use_positive_direction = True
    sw.offset = 0.0007
    so = o.modifiers.new('thick', 'SOLIDIFY'); so.thickness = 0.0012; so.offset = 1.0
    so.use_even_offset = True
    me.materials.append(MATS['number'])
    g = bpy.context.evaluated_depsgraph_get()
    m2 = bpy.data.meshes.new_from_object(o.evaluated_get(g)); o.modifiers.clear(); o.data = m2
    bpy.data.meshes.remove(me)
    m2.name = o.name
    for p in m2.polygons: p.use_smooth = True
    m2.set_sharp_from_angle(angle=math.radians(40))
    return o


NUM_AXIS = ARGS[ARGS.index('--num-axis') + 1] if '--num-axis' in ARGS else 'x'
nums = [number_on_face(+1, NUM_AXIS), number_on_face(-1, NUM_AXIS)]
for o in nums:
    nv = np.array([v.co[:] for v in o.data.vertices])
    print('NUMBER', o.name, 'box', nv.min(0).round(4), nv.max(0).round(4))

# ----------------------------------------------------------------------------------------------- 5 placement
# measured in room.blend: left wall inner face x=-2.08 (skirting in front of it), round rug Mesh_4
# centre (0.06,-0.05) r=0.88 and 6 mm thick, desk leg frame desk_top_tmp_2 x -0.99..0.95 y 0.41..1.10,
# chair_base* x >= -0.014.
WALL_X, RUG_C, RUG_R = -2.08, Vector((0.06, -0.05)), 0.88
DESK = ((-0.99 - 0.01, 0.41 - 0.01), (0.95, 1.10))
local = np.array([v.co[:] for o in col.objects if o.type == 'MESH' for v in o.data.vertices])


def clear(off):
    Rm = np.array(Matrix.Rotation(YAW, 3, 'Z'))
    wv = local @ Rm.T + np.array(PLACE + off)
    if wv[:, 0].min() < WALL_X + 0.02: return False
    low = wv[wv[:, 2] < 0.012]
    if (np.hypot(low[:, 0] - RUG_C.x, low[:, 1] - RUG_C.y) < RUG_R + 0.015).any(): return False
    inside = (wv[:, 0] > DESK[0][0]) & (wv[:, 1] > DESK[0][1]) & (wv[:, 1] < DESK[1][1]) & (wv[:, 2] < 0.74)
    if inside.any(): return False
    if (wv[:, 0] > -0.03).any(): return False
    return True


best = None
for r in range(0, 60):
    for a in range(0, 360, 15):
        off = Vector((r * 0.01 * math.cos(math.radians(a)), r * 0.01 * math.sin(math.radians(a)), 0))
        if clear(off):
            best = off; break
    if best is not None: break
assert best is not None, 'no clear spot'
root.matrix_world = Matrix.Translation(PLACE + best) @ Matrix.Rotation(YAW, 4, 'Z')
bpy.context.view_layer.update()
print('PLACEMENT offset from project spot', [round(x, 3) for x in best])

tri_out = sum(ntris(o.data) for o in col.objects if o.type == 'MESH')
allv = [o.matrix_world @ v.co for o in col.objects if o.type == 'MESH' for v in o.data.vertices]
wl = Vector([min(v[i] for v in allv) for i in range(3)]); wh = Vector([max(v[i] for v in allv) for i in range(3)])
print('ROBOT tris out', tri_out, 'objects', len([o for o in col.objects if o.type == 'MESH']))
for o in col.objects:
    if o.type == 'MESH': print('   ', o.name, ntris(o.data))
print('ROBOT world box', [round(x, 3) for x in wl], [round(x, 3) for x in wh])
meta = dict(tri_source_instanced=side['tri_all'], tri_prefilter_dropped=side['tri_dropped'],
            tri_imported=tri_in, tri_hidden_removed=tri_hidden, tri_out=tri_out,
            root_location=list(root.matrix_world.translation), yaw=YAW,
            world_lo=list(wl), world_hi=list(wh),
            bumper=dict(half_in=B_IN, half_out=B_OUT, z0=B_Z0, z1=B_Z1))
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
    gpu(sc)
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1); bg.inputs['Strength'].default_value = 0.35
    fl = bpy.data.meshes.new('floor'); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=4); bm.to_mesh(fl); bm.free()
    flo = bpy.data.objects.new('preview_floor', fl); sc.collection.objects.link(flo)
    flo.location = root.matrix_world.translation
    fm = bpy.data.materials.new('floor'); fm.use_nodes = True
    fb = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    fb.inputs['Base Color'].default_value = (0.3, 0.3, 0.31, 1); fb.inputs['Roughness'].default_value = 0.6
    fl.materials.append(fm)
    c = root.matrix_world.translation.copy()
    R = root.matrix_world.to_3x3()
    for nm, off, en, sz in (('key', (1.6, -1.8, 2.2), 380, 1.2), ('fill', (-2.0, -0.8, 1.2), 110, 2.0),
                            ('rim', (-0.6, 2.2, 1.8), 220, 1.0)):
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = sz
        lo_ = bpy.data.objects.new(nm, ld); sc.collection.objects.link(lo_)
        lo_.location = c + R @ Vector(off)
        lo_.rotation_euler = (c + Vector((0, 0, 0.25)) - lo_.location).to_track_quat('-Z', 'Y').to_euler()
    shot(sc, c + R @ Vector((1.35, -1.25, 0.95)), c + Vector((0, 0, 0.24)), 38, '34')
    nrm = R @ (Vector((1, 0, 0)) if NUM_AXIS == 'x' else Vector((0, 1, 0)))
    side_ = R @ (Vector((0, 1, 0)) if NUM_AXIS == 'x' else Vector((1, 0, 0)))
    face = c + nrm * B_OUT + Vector((0, 0, ZM))
    shot(sc, face + nrm * 0.5 - side_ * 0.18 + Vector((0, 0, 0.1)), face, 45, 'bumper')
    face2 = c - nrm * B_OUT + Vector((0, 0, ZM))
    shot(sc, face2 - nrm * 1.1 + side_ * 0.5 + Vector((0, 0, 0.45)), face2 + Vector((0, 0, 0.08)), 35, 'bumper_other')

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
