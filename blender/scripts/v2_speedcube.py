"""
v2 speedcube: MoYu WeiLong V11 (WRM V11) 18th Anniversary Edition, 3x3, in a real scrambled state.

Reference (speedcubeshop.com / thecubicle.com product pages and photos, Sept 2026):
  * 55.5 mm, stickerless, UV-coated gloss colour caps, transparent internals.
  * "Round-square centre": centre caps are a squircle; the two corners of each edge piece that
    touch the centre are cut with a large radius, leaving small pockets at the centre's corners.
  * White centre carries the red "18" anniversary emblem (two interlaced square outlines + "18").
  * Bright scheme sampled from the product photos: lime-yellow, pink-red, bright green,
    mid blue, neon orange, soft white.
Owner direction: internals are not visible from the desk, so the piece bodies are grey plastic;
seams are just a very fine gap.

Construction
  * 26 cubies, each its own object: a grey rounded body plus one coloured cap per exterior face.
    A cap is a rounded-square slab (per-corner plan radii) with a rounded top edge, built as
    offset rings so the top can be pillowed. Every cubie is built in its solved position.
  * A WCA-style 20-move scramble (seeded, printed) is applied by rotating the layers: each move
    selects the cubies currently in that layer and left-multiplies their rotation. So the result
    is a genuinely reachable state, with centres (and the emblem) turned by their own face moves.
  * The U layer is left ~3 deg off-grid, as a cube put down after a solve usually is.

Usage:  blender -b --factory-startup --python v2_speedcube.py -- [--no-render] [--only=34,seat]
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402

ARGS = lib.argv()
RENDER = '--no-render' not in ARGS
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'speedcube.blend')
NAME = 'speedcube'

# Old "speedcube" root empty in room.blend (children speedcube_1..7): base centre on the desk.
ROOM_LOC = (-0.33, 0.62, 0.735)
ROOM_YAW = 0.42
VIEWER = Vector((0.0, -0.16, 1.175))

# ----------------------------------------------------------------------------- dimensions
GAP = 0.00015            # seam between neighbouring pieces
PILLOW = 0.00018         # face-centre bulge of the caps
PITCH = (0.0555 + GAP - 2 * PILLOW) / 3   # 55.5 mm across the face centres
HB = PITCH / 2 - GAP / 2  # half size of one piece
CAP = 0.0016             # colour-cap thickness (the colour carries down the piece sides this far)
RT = 0.0009              # rounded top edge of every cap
EDGE_E = 0.00005         # cap footprint inset from the piece outline (keeps walls off the body)
BODY_R = 0.0004          # grey body edge radius
R_S = 0.0013             # ordinary tile corner (plan)
R_E = 0.0046             # edge-piece corners that touch the centre
R_C = 0.0022             # corner-piece corner that touches the centre
R_CEN = 0.0050           # squircle centre cap
CEN_INSET = 0.00025      # centre cap slightly smaller than the tiles
K = 6                    # arc segments per plan corner
TURN_U = math.radians(3.0)

# WCA orientation: U white, F green (-Y here, toward the viewer after the yaw).
FACES = {
    'U': (Vector((0, 0, 1)), 'white'), 'D': (Vector((0, 0, -1)), 'yellow'),
    'F': (Vector((0, -1, 0)), 'green'), 'B': (Vector((0, 1, 0)), 'blue'),
    'R': (Vector((1, 0, 0)), 'red'), 'L': (Vector((-1, 0, 0)), 'orange'),
}
COLOURS = {  # sRGB, sampled from the product photos and nudged off JPEG highlights
    'white': '#E6E7E4', 'yellow': '#E0F800', 'green': '#2ECF4E',
    'blue': '#0B63C2', 'red': '#EE1426', 'orange': '#FF6414',
}
SLOTS = ['body', 'white', 'yellow', 'green', 'blue', 'red', 'orange']


# ----------------------------------------------------------------------------- scramble
def wca_scramble(rng, n=20):
    axis = {'U': 0, 'D': 0, 'F': 1, 'B': 1, 'R': 2, 'L': 2}
    seq = []
    while len(seq) < n:
        f = rng.choice('UDFBRL')
        if seq and seq[-1][0] == f:
            continue
        if len(seq) >= 2 and axis[seq[-1][0]] == axis[f] and seq[-2][0] == f:
            continue
        seq.append(f + rng.choice(['', "'", '2']))
    return seq


def move_matrix(tok):
    n, _ = FACES[tok[0]]
    q = {'': 1, "'": -1, '2': 2}[tok[1:]]
    # clockwise as seen from outside that face = negative rotation about its outward normal
    return Matrix.Rotation(-q * math.pi / 2, 3, n)


def iround(m):
    return Matrix([[round(v) for v in row] for row in m])


def apply_moves(state, seq):
    """state: {solved_idx: 3x3 rotation}. Each move turns the cubies currently in its layer."""
    for tok in seq:
        n, _ = FACES[tok[0]]
        R = move_matrix(tok)
        for idx, M in state.items():
            pos = M @ Vector(idx)
            if round(pos.dot(n)) == 1:
                state[idx] = iround(R @ M)
    return state


def facelets(state):
    """{face letter: 3x3 colour grid} read off the state, for printing and checks."""
    out = {}
    for f, (n, _) in FACES.items():
        tiles = []
        for idx, M in state.items():
            for g, (sn, col) in FACES.items():
                if Vector(idx).dot(sn) > 0.5 and (M @ sn).dot(n) > 0.5:
                    tiles.append((M @ Vector(idx), col))
        out[f] = tiles
    return out


CUBIES = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1) if (i, j, k) != (0, 0, 0)]


def solved_state():
    return {c: Matrix.Identity(3) for c in CUBIES}


# self-tests of the move convention
_s = apply_moves(solved_state(), ['R'])
assert all(col == 'green' for p, col in facelets(_s)['U'] if round(p.x) == 1), 'R must lift F onto U'
_s = apply_moves(solved_state(), ['U'])
assert all(col == 'red' for p, col in facelets(_s)['F'] if round(p.z) == 1), 'U must bring R onto F'
_s = apply_moves(solved_state(), ['R', 'U', "R'", "U'"] * 6)
assert all(M == Matrix.Identity(3) for M in _s.values()), 'sexy move x6 must be identity'

SEED = 55511
SCRAMBLE = wca_scramble(random.Random(SEED))
STATE = apply_moves(solved_state(), SCRAMBLE)
print('SCRAMBLE', ' '.join(SCRAMBLE))
fl = facelets(STATE)
for f, tiles in fl.items():
    counts = {}
    n, _ = FACES[f]
    for _, col in tiles:
        counts[col] = counts.get(col, 0) + 1
    assert len(tiles) == 9
    print(f'FACE {f}: {len(tiles)} tiles, centre stays {FACES[f][1]}:',
          [col for p, col in tiles if p == n][0] == FACES[f][1], counts)
allc = {}
for tiles in fl.values():
    for _, col in tiles:
        allc[col] = allc.get(col, 0) + 1
assert all(v == 9 for v in allc.values()) and len(allc) == 6


# ----------------------------------------------------------------------------- geometry helpers
def rrect(A, B, radii, k=K):
    """Rounded rectangle, CCW from quadrant (+,+); radii per quadrant (++, -+, --, +-)."""
    pts = []
    for q, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        r = max(1e-5, min(radii[q], A - 1e-6, B - 1e-6))
        cx, cy = sx * (A - r), sy * (B - r)
        for i in range(k + 1):
            a = math.radians(90 * q + 90 * i / k)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def face_frame(n):
    """Two in-plane axes (u, v) with u x v = n."""
    n = Vector(n)
    u = Vector((0, 0, 1)).cross(n) if abs(n.z) < 0.5 else Vector((1, 0, 0))
    if u.length < 1e-6:
        u = Vector((1, 0, 0))
    u.normalize()
    v = n.cross(u)
    return u, v


def bulge(p, n):
    """Pillow height on the face with outward normal n, at cube-space point p."""
    u, v = face_frame(n)
    hc = 1.5 * PITCH
    a, b = p.dot(u) / hc, p.dot(v) / hc
    return PILLOW * max(0.0, 1 - a * a) * max(0.0, 1 - b * b)


def add_cap(bm, idx, n, slot):
    """Coloured cap on the exterior face n of piece idx (solved frame)."""
    n = Vector(n)
    u, v = face_frame(n)
    c = Vector(idx) * PITCH
    cu, cv = round(Vector(idx).dot(u)), round(Vector(idx).dot(v))
    radii = []
    for qu, qv in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        gu, gv = cu + qu * 0.5, cv + qv * 0.5
        if cu == 0 and cv == 0:
            radii.append(R_CEN)
        elif abs(gu) <= 0.5 and abs(gv) <= 0.5:
            radii.append(R_E if (cu == 0 or cv == 0) else R_C)
        else:
            radii.append(R_S)
    half = HB - EDGE_E - (CEN_INSET if cu == 0 and cv == 0 else 0.0)
    plane = c + n * HB  # the face plane of this piece (flush with the cube face)

    profile = [(0.0, -CAP - 0.0002), (0.0, -RT)]
    for i in range(1, 5):
        t = math.radians(90 * i / 4)
        profile.append((RT * (1 - math.cos(t)), -RT + RT * math.sin(t)))
    rings2d = [(rrect(half - d, half - d, [r - d for r in radii]), z) for d, z in profile]
    top_pts, _ = rings2d[-1]
    for s in (0.72, 0.45, 0.2):
        rings2d.append(([(x * s, y * s) for x, y in top_pts], 0.0))

    def to3d(x, y, z):
        p = plane + u * x + v * y + n * z
        w = min(1.0, max(0.0, (z + CAP) / CAP))
        return p + n * (bulge(p, n) * w)

    rings = [[bm.verts.new(to3d(x, y, z)) for x, y in pts] for pts, z in rings2d]
    centre = bm.verts.new(to3d(0.0, 0.0, 0.0))
    m = len(rings[0])
    faces = []
    for a_, b_ in zip(rings[:-1], rings[1:]):
        for i in range(m):
            j = (i + 1) % m
            faces.append(bm.faces.new((a_[i], a_[j], b_[j], b_[i])))
    last = rings[-1]
    for i in range(m):
        faces.append(bm.faces.new((last[i], last[(i + 1) % m], centre)))
    # orient outward: the fan faces must point along n
    faces[-1].normal_update()
    if faces[-1].normal.dot(n) < 0:
        for f in faces:
            f.normal_flip()
    for f in faces:
        f.material_index = slot
        f.smooth = True


def add_body(bm, idx):
    lo, hi = [], []
    for a in range(3):
        c = idx[a] * PITCH
        lo.append(c - (HB - CAP if idx[a] == -1 else HB))
        hi.append(c + (HB - CAP if idx[a] == 1 else HB))
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    for vert in tmp.verts:
        vert.co = Vector([lo[a] + (vert.co[a] + 0.5) * (hi[a] - lo[a]) for a in range(3)])
    bmesh.ops.bevel(tmp, geom=list(tmp.edges), offset=BODY_R, segments=2, affect='EDGES',
                    profile=0.5, clamp_overlap=True)
    me = bpy.data.meshes.new('tmp_body')
    tmp.to_mesh(me)
    tmp.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def bsdf_of(mat):
    return next(nd for nd in mat.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED')


def make_mat(name, hexcol, rough, coat=0.0, grain=0.0, var=0.03, scale=2500.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = bsdf_of(mat)
    b.inputs['Base Color'].default_value = (*lib.hex_rgb(hexcol), 1.0)
    b.inputs['Roughness'].default_value = rough
    if coat and 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.06
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 2.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    # broad smudge variation of roughness (handled cube), plus a very fine bump
    sm = nt.nodes.new('ShaderNodeTexNoise')
    sm.inputs['Scale'].default_value = 160.0
    sm.inputs['Detail'].default_value = 3.0
    nt.links.new(tc.outputs['Object'], sm.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = max(0.02, rough - var)
    mr.inputs['To Max'].default_value = rough + var * 2
    nt.links.new(sm.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    if grain > 0:
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = grain
        bump.inputs['Distance'].default_value = 0.00002
        nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return mat


# ----------------------------------------------------------------------------- build
lib.reset()
scene = bpy.context.scene
coll = bpy.data.collections.new(f'NEW_{NAME}')
scene.collection.children.link(coll)

MATS = {'body': make_mat('speedcube_body_grey', '#7C7F83', 0.42, grain=0.15, var=0.04)}
for key in SLOTS[1:]:
    MATS[key] = make_mat(f'speedcube_cap_{key}', COLOURS[key], 0.2, coat=0.35, grain=0.05, var=0.05)
M_PRINT = make_mat('speedcube_emblem_red_print', '#D71A28', 0.3, coat=0.7, var=0.03)

root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.04
coll.objects.link(root)

pieces = {}
for idx in CUBIES:
    bm = bmesh.new()
    add_body(bm, idx)
    for f, (n, col) in FACES.items():
        if Vector(idx).dot(n) > 0.5:
            add_cap(bm, idx, n, SLOTS.index(col))
    tag = ''.join('0' if v == 0 else ('+' if v > 0 else '-') for v in idx)
    me = bpy.data.meshes.new(f'NEW_speedcube_piece_{tag}')
    for key in SLOTS:
        me.materials.append(MATS[key])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(me.name, me)
    coll.objects.link(ob)
    pieces[idx] = ob

# ---- anniversary emblem on the white centre: interlaced square outlines + "18"
def square_ring(bm, half, width, angle, z):
    ro = rrect(half, half, [0.00015] * 4, k=2)
    ri = rrect(half - width, half - width, [0.00005] * 4, k=2)
    rot = Matrix.Rotation(angle, 2)
    vo = [bm.verts.new((*(rot @ Vector(p)), z)) for p in ro]
    vi = [bm.verts.new((*(rot @ Vector(p)), z)) for p in ri]
    m = len(vo)
    for i in range(m):
        j = (i + 1) % m
        bm.faces.new((vo[i], vo[j], vi[j], vi[i]))


ebm = bmesh.new()
Z_E = 0.00003
square_ring(ebm, 0.0043, 0.00034, math.radians(45), Z_E)
square_ring(ebm, 0.0036, 0.00030, math.radians(45), Z_E + 0.000004)
square_ring(ebm, 0.0034, 0.00030, 0.0, Z_E + 0.000008)
tcu = bpy.data.curves.new('emblem_18', 'FONT')
tcu.body = '18'
tcu.size = 0.0042
tcu.align_x = 'CENTER'
tcu.align_y = 'CENTER'
tcu.resolution_u = 4
tob = bpy.data.objects.new('emblem_18', tcu)
scene.collection.objects.link(tob)
bpy.context.view_layer.update()
tme = bpy.data.meshes.new_from_object(tob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
for vert in tme.vertices:
    vert.co.z = Z_E + 0.000012
    vert.co.x *= 0.8   # the printed numerals are narrow
ebm.from_mesh(tme)
bpy.data.objects.remove(tob)
bpy.data.curves.remove(tcu)
bpy.data.meshes.remove(tme)
bmesh.ops.remove_doubles(ebm, verts=ebm.verts, dist=1e-7)
for f in ebm.faces:
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
# sit it on the pillowed white centre cap (face U, centre at z = HB + PITCH)
n_u = Vector((0, 0, 1))
top_z = PITCH + HB
for vert in ebm.verts:
    p = Vector((vert.co.x, vert.co.y, top_z))
    vert.co.z = top_z + bulge(p, n_u) + vert.co.z
emb_me = bpy.data.meshes.new('NEW_speedcube_emblem18')
ebm.to_mesh(emb_me)
ebm.free()
emb_me.materials.append(M_PRINT)
emblem = bpy.data.objects.new('NEW_speedcube_emblem18', emb_me)
coll.objects.link(emblem)

# ---- scramble -> piece transforms (about the cube centre), U layer slightly off-grid
lo_z = None
for idx, ob in pieces.items():
    M = STATE[idx]
    pos = M @ Vector(idx)
    R = M.to_4x4()
    if round(pos.z) == 1:
        R = Matrix.Rotation(TURN_U, 4, 'Z') @ R
    ob['solved_index'] = list(idx)
    ob.matrix_basis = R
emblem.matrix_basis = pieces[(0, 0, 1)].matrix_basis.copy()

# rest the lowest point on z = 0 (root at the base centre)
bpy.context.view_layer.update()
min_z = min((ob.matrix_world @ vv.co).z for ob in pieces.values() for vv in ob.data.vertices)
lift = -min_z
for ob in list(pieces.values()) + [emblem]:
    ob.matrix_basis = Matrix.Translation((0, 0, lift)) @ ob.matrix_basis
    ob.parent = root
    ob.matrix_parent_inverse = Matrix.Identity(4)

for ob in list(pieces.values()) + [emblem]:
    lib.activate(ob)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    except (AttributeError, RuntimeError, TypeError):
        lib.shade_auto(ob, 40)
    try:
        lib.uv_unwrap(ob)
    except Exception as err:
        print(f'  uv skipped on {ob.name}: {err}')

objs = [o for o in coll.objects if o.type == 'MESH']
total = sum(lib.tri_count(o) for o in objs)
bpy.context.view_layer.update()
lo, hi = lib.world_bounds(objs)
print(f'TOTAL {total} tris in {len(objs)} objects; size {(hi.x-lo.x)*1000:.2f} x {(hi.y-lo.y)*1000:.2f} x '
      f'{(hi.z-lo.z)*1000:.2f} mm (U layer turned {math.degrees(TURN_U):.1f} deg); min z {lo.z*1000:.3f} mm')
for f, tiles in fl.items():
    n, _ = FACES[f]
    u, v = face_frame(n)
    grid = sorted(tiles, key=lambda t: (-round(t[0].dot(v)), round(t[0].dot(u))))
    print(f'NET {f}:', ' '.join(col[0].upper() for _, col in grid))


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
root.rotation_euler = (0, 0, ROOM_YAW)
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
    ground.data.materials.append(make_mat('preview_ground', '#8E8E8C', 0.6, var=0.0))
    rig.append(ground)
    rig.append(area('key', (-0.25, -0.25, 0.4), (0, 0, 0.02), 3.2, 0.3))
    rig.append(area('fill', (0.3, -0.15, 0.15), (0, 0, 0.02), 1.1, 0.3, (0.95, 0.97, 1.0)))
    rig.append(area('rim', (0.05, 0.4, 0.25), (0, 0, 0.02), 2.5, 0.2))
    cam_d = bpy.data.cameras.new('preview_cam')
    cam = bpy.data.objects.new('preview_cam', cam_d)
    scene.collection.objects.link(cam)
    rig.append(cam)
    scene.camera = cam
    cam_d.clip_start = 0.005

    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
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

    ctr = Vector((0, 0, 0.028))
    # seated direction: from the cube toward the seated viewer's eye, in room terms
    to_eye = (VIEWER - Vector(ROOM_LOC) - Vector((0, 0, 0.028))).normalized()
    # close 3/4: from the front-right-top corner of the cube (three faces)
    fr = Matrix.Rotation(ROOM_YAW, 3, 'Z') @ Vector((0.55, -1.0, 0.9)).normalized()
    views = {
        '34': (ctr + fr * 0.24, ctr, 60),
        'seat': (ctr + to_eye * 0.35, ctr, 80),
        'top': (ctr + Vector((0.0, -0.02, 0.2)), ctr, 60),
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
    bpy.data.materials.remove(bpy.data.materials['preview_ground'])
    scene.world = None
    bpy.data.worlds.remove(world)

# ----------------------------------------------------------------------------- place + save
root.location = ROOM_LOC
root.rotation_euler = (0, 0, ROOM_YAW)
bpy.data.orphans_purge(do_recursive=True)
os.makedirs(PARTS, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('SAVED', OUT_BLEND)
