"""
v2_bambu_mini.py -- the owner's downloaded Bambu Lab A1 mini, optimised, on the white side table right of the desk.

    blender -b --factory-startup --python blender/scripts/v2_bambu_mini.py -- [--no-render] [--compare] [--only=34,close,seat]

Source: Sketchfab "3D Printer - Bambu Lab A1 Mini" by neilvfx, CC BY 4.0 (credit required, see assets/MANIFEST.md);
raw download in assets/source/bambu_a1_mini/ (git-ignored): source/a1 3d.fbx (823.4k tris) + 4K PBR textures.

Pipeline
  1. import the FBX, bake every import transform into the meshes, drop the empties;
  2. PBR materials rebuilt per texture set (Body / Head(=Toolhead) / Heatbed / Motor / Z-Axis):
     Col -> Base Color (sRGB), Rough -> Roughness, Normal -> Normal Map, Opacity -> Alpha (Head, Motor),
     Spec -> Metallic through a 0.35..0.75 ramp (the spec maps are black for plastic, white for the steel rails,
     screws and nozzle); all maps downscaled to 2K (spec 1K) into assets/source/bambu_a1_mini/tex2k/ and packed;
  3. scaled to the real A1 mini (see SCALE), front turned to -Y, footprint centred, feet on z=0;
     the Z carriage + toolhead (the FBX 'Motor' + 'Toolhead' groups) lowered so the nozzle sits 0.3 mm over a
     half-printed 3DBenchy (cables to the column top are stretched with a height taper, top ends fixed);
  4. optimisation: (a) faces never hit by ~27M rays cast from the upper hemisphere (table top blocks the underside)
     are deleted, after growing the hit set by two vertex rings; objects left empty are dropped;
     (b) limited dissolve at 0.5 deg, delimit UV/MATERIAL/SEAM/SHARP/NORMAL (UV islands and hard edges survive);
     (c) quadric collapse to a triangle budget: screws ~1.5 %, everything else one common ratio;
     (d) meshes joined per material, custom normals cleared, smooth shading with sharp edges > 35 deg;
  5. white spool (pastel-mint PLA) on an assumed white holder clamped to the top of the Z column, filament strand
     into the PTFE tube, and a half-printed mint 3DBenchy under the nozzle (built like v2_bambu.py);
  6. placed on the white drawer side table copied from blender/scene/parts/bambu.blend, right of the desk.
Output: blender/scene/parts/bambu_mini.blend (collection NEW_bambu_mini, root NEW_bambu_mini_root) + previews.
"""
import bpy
import bmesh
import math
import os
import sys
import time
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
SRC = os.path.join(REPO, 'assets', 'source', 'bambu_a1_mini')
FBX = os.path.join(SRC, 'source', 'a1 3d.fbx')
TEX = os.path.join(SRC, 'textures')
TEX2K = os.path.join(SRC, 'tex2k')
BAMBU_BLEND = os.path.join(PARTS, 'bambu.blend')
OUT = os.path.join(PARTS, 'bambu_mini.blend')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
COMPARE = '--compare' in ARGS
ONLY = next((a.split('=')[1].split(',') for a in ARGS if a.startswith('--only=')), None)

# FBX units -> metres. The model's extents (W 616 x D 556 x H 622 incl. rail cap, filament clip and bed cable)
# least-squares fit Bambu's 347 x 315 x 365 mm at 0.573; 0.575 makes the PEI plate exactly 180 mm wide (the
# 180^3 print area). Result: 354 x 320 x 358 mm frame (see the DIMS print).
SCALE = 0.575
PRINTER_BUDGET = 100000        # printer tris after optimisation (spool, Benchy and table come on top)
BENCHY_H = 24.0                # half of the 48 mm 3DBenchy
FILAMENT = (0.66, 0.90, 0.78)  # pastel mint PLA

# ------------------------------------------------------------------ placement (room metres)
# right of the desk (desk ends at x=1.0): clear of the guitar stand (y<=0.361), the curtain (y>=1.154), the right wall
# (x=1.91) and the desk-edge cables (x<=1.03)
TABLE_SRC_C = V((-1.52, 0.895))              # centre of the table as built in bambu.blend
TABLE_C = V((1.50, 0.845))                   # new centre: x 1.22..1.78, y 0.61..1.08
TABLE_H = 0.648
VIEWER = V((0.0, -0.16, 1.175))

t_start = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def tris_of(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def log(*a):
    print('[%5.1fs]' % (time.time() - t_start), *a, flush=True)


# ============================================================================== 1. import + bake
bpy.ops.import_scene.fbx(filepath=FBX)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']


def top_group(o):
    p = o
    while p.parent and p.parent.name != 'Final_Printer_Animation2_1':
        p = p.parent
    return p.name


GROUP = {o.name: top_group(o) for o in meshes}
mws = {o.name: o.matrix_world.copy() for o in meshes}
for o in meshes:
    if o.data.users > 1:
        o.data = o.data.copy()
    o.parent = None
    o.matrix_world = Matrix()
    o.data.transform(mws[o.name])
for o in [o for o in bpy.data.objects if o.type != 'MESH']:
    bpy.data.objects.remove(o, do_unlink=True)
TRIS_SRC = sum(tris_of(o.data) for o in meshes)
log('imported', len(meshes), 'meshes', TRIS_SRC, 'tris')

# ---- lower the Z carriage + toolhead so the nozzle is 0.3 mm above a 24 mm print (FBX units)
bed_top = max(v.co.z for v in bpy.data.objects['PEI_Plate'].data.vertices)
noz_tip = min(v.co.z for v in bpy.data.objects['Nozzle'].data.vertices)
DROP = noz_tip - (bed_top + (BENCHY_H + 0.3) / 1000.0 / SCALE)
for o in meshes:                  # the whole carriage group moves rigidly (both cable loops end on moving parts)
    if GROUP[o.name] in ('Motor', 'Toolhead'):
        o.data.transform(Matrix.Translation((0, 0, -DROP)))
log('carriage lowered by %.1f mm (real)' % (DROP * SCALE * 1000))

# ---- FBX frame -> printer-local metres: front (+X in the FBX, where the screen is) to -Y, footprint centred, z=0 feet
base = bpy.data.objects['Base'].data.vertices
cx = (min(v.co.x for v in base) + max(v.co.x for v in base)) / 2
cy = (min(v.co.y for v in base) + max(v.co.y for v in base)) / 2
zmin = min(v.co.z for o in meshes for v in o.data.vertices)
FRAME = Matrix.Scale(SCALE, 4) @ Matrix.Rotation(math.radians(-90), 4, 'Z') @ Matrix.Translation((-cx, -cy, -zmin))
for o in meshes:
    o.data.transform(FRAME)


def pts_of(name):
    return [v.co.copy() for v in bpy.data.objects[name].data.vertices]


_nz = pts_of('Nozzle')
_zm = min(p.z for p in _nz)
_tip = [p for p in _nz if p.z < _zm + 0.0005]
NOZ = V((sum(p.x for p in _tip) / len(_tip), sum(p.y for p in _tip) / len(_tip), _zm))
BED_TOP = max(p.z for p in pts_of('PEI_Plate'))
_c = pts_of('Würfel_6')                      # Z column top cap
COL_LO = V([min(p[i] for p in _c) for i in range(3)])
COL_HI = V([max(p[i] for p in _c) for i in range(3)])
_pt = pts_of('CableTrans')
PTFE_TOP = max(_pt, key=lambda p: p.z)


def bbox_of(name):
    pp = pts_of(name)
    return V([min(p[i] for p in pp) for i in range(3)]), V([max(p[i] for p in pp) for i in range(3)])


CLIP_LO, CLIP_HI = bbox_of('FilamentClip')      # filament inlet / runout clip on the right of the Z carriage
STOP_LO, STOP_HI = bbox_of('Stopper')
CPL_LO, CPL_HI = bbox_of('CableClip')          # PTFE push-fit coupling on top of the extruder
log('clip', tuple(round(x, 4) for x in CLIP_LO), tuple(round(x, 4) for x in CLIP_HI), 'stopper',
    tuple(round(x, 4) for x in STOP_LO), tuple(round(x, 4) for x in STOP_HI), 'coupling',
    tuple(round(x, 4) for x in CPL_LO), tuple(round(x, 4) for x in CPL_HI))
_ct = bpy.data.objects['CableTrans']
# march along the source tube from its lower end (the carriage-side box) to the toolhead: slab centroids every 3 mm
# (the mesh has long edges between sparse rings, so march on an area-uniform point sample of its surface)
_bmc = bmesh.new()
_bmc.from_mesh(_ct.data)
bmesh.ops.triangulate(_bmc, faces=_bmc.faces)
_tri = np.array([[l.vert.co[:] for l in f.loops] for f in _bmc.faces])
_bmc.free()
_area = 0.5 * np.linalg.norm(np.cross(_tri[:, 1] - _tri[:, 0], _tri[:, 2] - _tri[:, 0]), axis=1)
_rng = np.random.default_rng(7)
_pick = _rng.choice(len(_tri), 60000, p=_area / _area.sum())
_uv = _rng.random((60000, 2))
_fl = _uv.sum(1) > 1
_uv[_fl] = 1 - _uv[_fl]
_t = _tri[_pick]
_vs = _t[:, 0] + (_t[:, 1] - _t[:, 0]) * _uv[:, :1] + (_t[:, 2] - _t[:, 0]) * _uv[:, 1:]
_zl = _vs[:, 2].min()
_end = _vs[_vs[:, 2] < _zl + 0.0012]
_c = _end.mean(0)
PTFE_SRC_R = float(np.linalg.norm(_end - _c, axis=1).max())
_d = np.array([0.0, 0.0, 1.0])
SRC_PATH = [V(_c.tolist())]
for _ in range(600):
    rel = _vs - _c
    along = rel @ _d
    sel = _vs[(np.abs(along - 0.003) < 0.0015) & (np.linalg.norm(rel, axis=1) < 4 * PTFE_SRC_R + 0.003)]
    if len(sel) < 3:
        break
    cn = sel.mean(0)
    _d = (cn - _c) / np.linalg.norm(cn - _c)
    _c = cn
    SRC_PATH.append(V(_c.tolist()))
log('source PTFE: radius %.1f mm, centreline %d pts, %s -> %s' % (PTFE_SRC_R * 1000, len(SRC_PATH),
    tuple(round(x, 4) for x in SRC_PATH[0]), tuple(round(x, 4) for x in SRC_PATH[-1])))
meshes.remove(_ct)
bpy.data.objects.remove(_ct, do_unlink=True)
log('nozzle tip', tuple(round(x, 4) for x in NOZ), 'over bed by %.1f mm' % ((NOZ.z - BED_TOP) * 1000),
    'column top', tuple(round(x, 4) for x in COL_LO), tuple(round(x, 4) for x in COL_HI), 'ptfe top',
    tuple(round(x, 4) for x in PTFE_TOP))


# ============================================================================== 2. materials (PBR, downscaled, packed)
def srgb(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def tex2k(fname, size):
    os.makedirs(TEX2K, exist_ok=True)
    stem, ext = os.path.splitext(fname)
    dst = os.path.join(TEX2K, stem + ('.png' if 'Opacity' in stem else '.jpg'))
    if not os.path.exists(dst):
        im = bpy.data.images.load(os.path.join(TEX, fname))
        im.scale(size, size)
        im.file_format = 'PNG' if dst.endswith('.png') else 'JPEG'
        if dst.endswith('.png'):
            im.save(filepath=dst)
        else:
            im.save(filepath=dst, quality=92)
        bpy.data.images.remove(im)
    im = bpy.data.images.load(dst)
    im.name = 'bambu_mini_' + stem
    return im


TEXSETS = {   # FBX material -> (texture prefix, Col, Normal, Rough, Spec, Opacity)
    'Body': ('Body', 'Body_Col_v2.jpeg', 'Body_Normal.jpeg', 'Body_Rough_v2.jpeg', 'Body_Spec.jpeg', None),
    'Toolhead': ('Head', 'Head_Col_v2.jpeg', 'Head_Normal_v2.jpeg', 'Head_Rough.jpeg', 'Head_Spec.jpeg',
                 'Head_Opacity_v2.png'),
    'Heatbed': ('Heatbed', 'Heatbed_Col.jpeg', 'Heatbed_Normal.jpeg', 'Heatbed_Rough.jpeg', 'Heatbed_Spec.jpeg', None),
    'Motor': ('Motor', 'Motor_Col.jpeg', 'Motor_Normal.jpeg', 'Motor_Rough.jpeg', 'Motor_Spec.jpeg',
              'Motor_Opacity.jpeg'),
    'Z-Axis': ('Z-Axis', 'Z-Axis_Col.jpeg', 'Z-Axis_Normal.jpeg', 'Z-Axis_Rough.jpeg', 'Z-Axis_Spec.jpeg', None),
}
PBR = {}
for key, (pre, col, nrm, rgh, spc, opa) in TEXSETS.items():
    m = bpy.data.materials.new('bambu_mini_' + pre.lower().replace('-', ''))
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')

    def node(fname, colorspace, size=2048, x=-700, y=0):
        n = N.new('ShaderNodeTexImage')
        n.image = tex2k(fname, size)
        n.image.colorspace_settings.name = colorspace
        n.location = (x, y)
        return n
    c = node(col, 'sRGB', y=300)
    L.new(c.outputs['Color'], bs.inputs['Base Color'])
    r = node(rgh, 'Non-Color', y=0)
    L.new(r.outputs['Color'], bs.inputs['Roughness'])
    s = node(spc, 'Non-Color', size=1024, y=-300)
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 0.35
    mr.inputs['From Max'].default_value = 0.75
    L.new(s.outputs['Color'], mr.inputs['Value'])
    L.new(mr.outputs['Result'], bs.inputs['Metallic'])
    n_ = node(nrm, 'Non-Color', y=-600)
    nm = N.new('ShaderNodeNormalMap')
    L.new(n_.outputs['Color'], nm.inputs['Color'])
    L.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if opa:
        o_ = node(opa, 'Non-Color', y=-900)
        L.new(o_.outputs['Color'], bs.inputs['Alpha'])
    m.diffuse_color = (0.8, 0.8, 0.8, 1)
    PBR[key] = m
for im in bpy.data.images:
    if im.source == 'FILE' and im.packed_file is None and im.filepath:
        im.pack()
for o in meshes:
    for slot in o.material_slots:
        if slot.material and slot.material.name in PBR:
            slot.material = PBR[slot.material.name]
        else:
            log('WARN unmapped material', o.name, slot.material and slot.material.name)
for mm in [m for m in bpy.data.materials if m.users == 0]:
    bpy.data.materials.remove(mm)
log('materials', [m.name for m in PBR.values()])


# ============================================================================== render helpers
def setup_render():
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
    if not scene.world:
        w = bpy.data.worlds.new('prev_grey')
        w.use_nodes = True
        bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
        bg.inputs['Color'].default_value = (0.42, 0.42, 0.42, 1)
        bg.inputs['Strength'].default_value = 0.35
        scene.world = w


PREV = []


def prev_obj(o):
    scene.collection.objects.link(o)
    PREV.append(o)
    return o


def lights_and_cam(mid, scale=1.0):
    for name, off, power, size in (('key', (1.1, -1.0, 1.2), 90, 1.0), ('fill', (-0.1, -1.4, 0.3), 30, 1.2),
                                   ('rim', (0.9, 0.9, 1.3), 50, 0.8)):
        ld = bpy.data.lights.new('prev_' + name, 'AREA')
        ld.energy = power * scale * scale
        ld.size = size * scale
        lo = prev_obj(bpy.data.objects.new('prev_' + name, ld))
        lo.location = V(mid) + V(off) * scale
        lo.rotation_euler = (V(mid) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cam = prev_obj(bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam')))
    scene.camera = cam
    return cam


def shot(cam, loc, target, lens, path, res=(1280, 800)):
    scene.render.resolution_x, scene.render.resolution_y = res
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_start = 0.005
    cam.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    log('PREVIEW', os.path.basename(path), '%.1fs' % (time.time() - t))


def clear_prev():
    for o in PREV:
        bpy.data.objects.remove(o, do_unlink=True)
    PREV.clear()


def ground(z=0.0, size=3.0, col=(0.30, 0.27, 0.24)):
    me = bpy.data.meshes.new('prev_ground')
    me.from_pydata([(-size, -size, z), (size, -size, z), (size, size, z), (-size, size, z)], [], [(0, 1, 2, 3)])
    fm = bpy.data.materials.new('prev_ground')
    fm.use_nodes = True
    b_ = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b_.inputs['Base Color'].default_value = (*col, 1)
    b_.inputs['Roughness'].default_value = 0.7
    me.materials.append(fm)
    return prev_obj(bpy.data.objects.new('prev_ground', me))


# compare cameras, printer-local metres (front = -Y)
CMP_SHOTS = [('full', V((0.42, -0.62, 0.42)), V((0.0, 0.0, 0.17)), 42),
             ('head', V((0.16, -0.20, 0.17)), V((0.02, 0.0, 0.095)), 50)]
CMP_DIR = os.path.join(SRC, 'compare')


def render_compare(tag):
    setup_render()
    ground()
    cam = lights_and_cam((0, 0, 0.18), 0.6)
    os.makedirs(CMP_DIR, exist_ok=True)
    for name, loc, tgt, lens in CMP_SHOTS:
        shot(cam, loc, tgt, lens, os.path.join(CMP_DIR, '%s_%s.png' % (tag, name)), (720, 800))
    clear_prev()


if COMPARE and not NO_RENDER:
    render_compare('before')

# ============================================================================== 4a. visibility culling
t0 = time.time()
SEE_THROUGH = {'Glas', 'Lens', 'Lens_2'}
bm_all = bmesh.new()
owner = []
for i, o in enumerate(meshes):
    n0 = len(bm_all.faces)
    nv0 = len(bm_all.verts)
    bm_all.from_mesh(o.data)
    owner.append((n0, len(bm_all.faces)))
    if o.name in SEE_THROUGH:          # glass / lenses / translucent PTFE: moved out of the way, never occlude
        bm_all.verts.ensure_lookup_table()
        for v in bm_all.verts[nv0:]:
            v.co.z += 100.0
# the table top: rays from below the horizon stop here
g = [bm_all.verts.new(p) for p in ((-2, -2, -0.0003), (2, -2, -0.0003), (2, 2, -0.0003), (-2, 2, -0.0003))]
bm_all.faces.new(g)
bm_all.faces.ensure_lookup_table()
nfaces = len(bm_all.faces) - 1
bvh = BVHTree.FromBMesh(bm_all)
bm_all.verts.ensure_lookup_table()
allco = np.array([v.co[:] for v in bm_all.verts][:-4])
allco = allco[allco[:, 2] < 50.0]
lo, hi = allco.min(0), allco.max(0)
C = V(((lo + hi) / 2).tolist())
R = float(np.linalg.norm(hi - lo)) / 2 + 0.005
hit = bytearray(nfaces + 1)
dirs = []
for el in (1, 8, 18, 30, 45, 60, 75, 90):
    n = 1 if el == 90 else (20 if el < 40 else 12)
    for k in range(n):
        az = 2 * math.pi * (k + 0.5 * (el // 8 % 2)) / n
        e = math.radians(el)
        dirs.append(V((math.cos(e) * math.cos(az), math.cos(e) * math.sin(az), math.sin(e))))
STEP = 0.0009
nray = 0
for d in dirs:
    fwd = -d
    u = fwd.orthogonal().normalized()
    w = fwd.cross(u).normalized()
    N = int(2 * R / STEP)
    org0 = C + d * (R + 0.05) - u * R - w * R
    for a in range(N):
        oa = org0 + u * (a * STEP)
        for b in range(N):
            idx = bvh.ray_cast(oa + w * (b * STEP), fwd)[2]
            if idx is not None:
                hit[idx] = 1
    nray += N * N
# grow the visible set by two vertex rings (sampling safety margin); see-through parts count as visible
vis = [bool(hit[i]) for i in range(nfaces)]
for i, o in enumerate(meshes):
    if o.name in SEE_THROUGH:
        for k in range(*owner[i]):
            vis[k] = True
for _ in range(2):
    vv = set()
    for i in range(nfaces):
        if vis[i]:
            vv.update(v.index for v in bm_all.faces[i].verts)
    for i in range(nfaces):
        if not vis[i] and any(v.index in vv for v in bm_all.faces[i].verts):
            vis[i] = True
bm_all.free()
log('visibility: %d rays, %d dirs, %.1fs; visible faces %d / %d' % (nray, len(dirs), time.time() - t0, sum(vis), nfaces))
removed_hidden = 0
CULLED_OBJS = []
for i, o in enumerate(list(meshes)):
    f0, f1 = owner[i]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    dead = [bm.faces[k] for k in range(f1 - f0) if not vis[f0 + k]]
    t_before = tris_of(o.data)
    if dead:
        bmesh.ops.delete(bm, geom=dead, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.to_mesh(o.data)
    bm.free()
    removed_hidden += t_before - tris_of(o.data)
    if len(o.data.polygons) == 0:
        CULLED_OBJS.append(o.name)
        meshes.remove(o)
        bpy.data.objects.remove(o, do_unlink=True)
TRIS_CULLED = sum(tris_of(o.data) for o in meshes)
log('hidden faces removed: %d tris; whole objects dropped: %s' % (removed_hidden, CULLED_OBJS))

# ============================================================================== 4b. limited dissolve (texture-safe)
for o in meshes:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), use_dissolve_boundaries=False, verts=bm.verts,
                             edges=bm.edges, delimit={'UV', 'MATERIAL', 'SEAM', 'SHARP', 'NORMAL'})
    bm.to_mesh(o.data)
    bm.free()
TRIS_DISS = sum(tris_of(o.data) for o in meshes)
log('after limited dissolve', TRIS_DISS)

# ============================================================================== 4c. collapse to budget
dg = bpy.context.evaluated_depsgraph_get()
is_screw = {o.name: ('Screw' in o.name) for o in meshes}
T = {o.name: tris_of(o.data) for o in meshes}
target = {}
screw_budget = 0
for o in meshes:
    if is_screw[o.name]:
        target[o.name] = min(T[o.name], max(120, int(T[o.name] * 0.015)))
        screw_budget += target[o.name]
rest = [o for o in meshes if not is_screw[o.name]]
FLOOR = 250
lo_r, hi_r = 0.0, 1.0
for _ in range(40):
    r = (lo_r + hi_r) / 2
    tot = sum(min(T[o.name], max(FLOOR, int(T[o.name] * r))) for o in rest)
    if tot + screw_budget > PRINTER_BUDGET:
        hi_r = r
    else:
        lo_r = r
RATIO = lo_r
for o in rest:
    target[o.name] = min(T[o.name], max(FLOOR, int(T[o.name] * RATIO)))
for o in meshes:
    if target[o.name] >= T[o.name] * 0.98:
        continue
    mod = o.modifiers.new('dec', 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = target[o.name] / T[o.name]
    mod.use_collapse_triangulate = True
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
for o in meshes:
    if o.modifiers:
        new = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        old = o.data
        o.modifiers.clear()
        o.data = new
        bpy.data.meshes.remove(old)
TRIS_DEC = sum(tris_of(o.data) for o in meshes)
log('collapse ratio %.3f (screws 1.5%%) -> %d tris' % (RATIO, TRIS_DEC))

# ============================================================================== 4d. join per material, normals
coll = bpy.data.collections.new('NEW_bambu_mini')
scene.collection.children.link(coll)
root = bpy.data.objects.new('NEW_bambu_mini_root', None)
coll.objects.link(root)
PART_NAME = {'Body': 'base', 'Toolhead': 'toolhead', 'Heatbed': 'heatbed', 'Motor': 'carriage', 'Z-Axis': 'column'}
PRINTER = []
GROUPS = {key: [o for o in meshes if o.material_slots and o.material_slots[0].material == m] for key, m in PBR.items()}
for key, m in PBR.items():
    grp = GROUPS[key]
    if not grp:
        continue
    bpy.ops.object.select_all(action='DESELECT')
    for o in grp:
        o.select_set(True)
    bpy.context.view_layer.objects.active = grp[0]
    if len(grp) > 1:
        bpy.ops.object.join()
    j = bpy.context.view_layer.objects.active
    j.name = j.data.name = 'bambu_mini_' + PART_NAME[key]
    me = j.data
    if me.has_custom_normals:
        bpy.context.view_layer.objects.active = j
        try:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        except Exception:
            a = me.attributes.get('custom_normal')
            if a:
                me.attributes.remove(a)
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(35))
    for c in list(j.users_collection):
        c.objects.unlink(j)
    coll.objects.link(j)
    PRINTER.append(j)
TRIS_PRINTER = sum(tris_of(o.data) for o in PRINTER)
log('printer objects', [o.name for o in PRINTER], TRIS_PRINTER)

if COMPARE and not NO_RENDER:
    render_compare('after')
    # 2 x 2 sheet: before | after, full view on top, toolhead close-up below
    rows = []
    for name, *_ in CMP_SHOTS:
        pair = []
        for tag in ('before', 'after'):
            im = bpy.data.images.load(os.path.join(CMP_DIR, '%s_%s.png' % (tag, name)))
            a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
            pair.append(a)
            bpy.data.images.remove(im)
        sep = np.ones((pair[0].shape[0], 6, 4), np.float32)
        rows.append(np.concatenate([pair[0], sep, pair[1]], axis=1))
    sheet = np.concatenate(rows[::-1], axis=0)       # pixel rows are bottom-up: full view ends on top
    out = bpy.data.images.new('cmp', sheet.shape[1], sheet.shape[0], alpha=True)
    out.pixels[:] = sheet.ravel()
    out.filepath_raw = os.path.join(PARTS, 'bambu_mini_compare.png')
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    log('PREVIEW bambu_mini_compare.png')

log('STATS tris source %d -> hidden-culled %d -> dissolved %d -> decimated %d' % (TRIS_SRC, TRIS_CULLED, TRIS_DISS,
                                                                                     TRIS_PRINTER))
if '--stop-after-opt' in ARGS:
    raise SystemExit

# ============================================================================== 5. spool, holder, filament, Benchy
MATS = {}


def mat(name, col, rough, metal=0.0, bump=0.0, bscale=900.0):
    m = bpy.data.materials.new('bambu_mini_' + name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    c = srgb(col)
    bs.inputs['Base Color'].default_value = (*c, 1)
    bs.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*c, 1)
    tc = N.new('ShaderNodeTexCoord')
    nz = N.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 60.0
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = rough * 0.88
    mr.inputs['To Max'].default_value = min(1.0, rough * 1.12)
    L.new(nz.outputs['Fac'], mr.inputs['Value'])
    L.new(mr.outputs['Result'], bs.inputs['Roughness'])
    if bump:
        fn = N.new('ShaderNodeTexNoise')
        fn.inputs['Scale'].default_value = bscale
        L.new(tc.outputs['Object'], fn.inputs['Vector'])
        bp = N.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = 0.0002
        L.new(fn.outputs['Fac'], bp.inputs['Height'])
        L.new(bp.outputs['Normal'], bs.inputs['Normal'])
    MATS[name] = m
    return m


def banded(name, col, rough, pitch, axis='Z', amp=0.35, sheen=0.0, diagonal=False):
    """printed / wound filament: fine sinusoidal ridges every `pitch` metres along an object axis
    (diagonal=True: +-45 deg extrusion lines of a top layer seen from above)"""
    m = bpy.data.materials.new('bambu_mini_' + name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
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
    if diagonal:
        ad = N.new('ShaderNodeMath')
        ad.operation = 'ADD'
        L.new(sp.outputs['X'], ad.inputs[0])
        L.new(sp.outputs['Y'], ad.inputs[1])
        L.new(ad.outputs[0], mu.inputs[0])
        mu.inputs[1].default_value = 2 * math.pi / (pitch * 1.4142)
    else:
        L.new(sp.outputs[axis], mu.inputs[0])
        mu.inputs[1].default_value = 2 * math.pi / pitch
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


mat('holder_white', (0.90, 0.905, 0.90), 0.40, bump=0.05, bscale=1400)
mat('spool_white', (0.93, 0.93, 0.92), 0.30, bump=0.03, bscale=1200)
mat('shadow', (0.02, 0.02, 0.02), 0.9)
mat('filament_strand', FILAMENT, 0.35)
banded('filament_spool', FILAMENT, 0.38, 0.00175, axis='Z', amp=0.5, sheen=0.3)
banded('print', FILAMENT, 0.42, 0.0002, axis='Z', amp=0.3)
banded('print_top', FILAMENT, 0.30, 0.00045, amp=0.6, diagonal=True)
EXTRA = []


def finish(o, m, smooth_angle=35.0):
    o.data.materials.append(MATS[m])
    if smooth_angle is not None:
        for p in o.data.polygons:
            p.use_smooth = True
        o.data.set_sharp_from_angle(angle=math.radians(smooth_angle))
    coll.objects.link(o)
    EXTRA.append(o)
    return o


def from_bm(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def rbox(name, lo, hi, r, m, segs=3):
    lo, hi = V(lo), V(hi)
    sz = hi - lo
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = V((v.co.x * sz.x, v.co.y * sz.y, v.co.z * sz.z)) + (lo + hi) / 2
    if r > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=min(r, min(sz) * 0.49), segments=segs,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    return finish(from_bm(name, bm), m)


def cyl(name, r, a, b, m, verts=32, r2=None, cap_bevel=0.0):
    a, b = V(a), V(b)
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r,
                          radius2=r if r2 is None else r2, depth=d.length)
    if cap_bevel > 0:
        caps = [e for e in bm.edges if all(abs(abs(v.co.z) - d.length / 2) < 1e-7 for v in e.verts)]
        bmesh.ops.bevel(bm, geom=caps, offset=cap_bevel, segments=2, profile=0.5, affect='EDGES', clamp_overlap=True)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=V(), matrix=d.normalized().to_track_quat('Z', 'Y').to_matrix())
    bmesh.ops.translate(bm, verts=bm.verts, vec=(a + b) / 2)
    return finish(from_bm(name, bm), m, 40)


def lathe(name, prof, m, segs=64, closed=True):
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0.0, z)) for r, z in prof]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    if closed:
        es.append(bm.edges.new((vs[-1], vs[0])))
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=segs,
                   use_merge=True, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(from_bm(name, bm), m, 40)


def tube(name, pts, radius, m, res=10, bev=6, caps=True, flip=False):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = res
    cu.bevel_depth = radius
    cu.bevel_resolution = bev // 2
    cu.use_fill_caps = caps
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = V(p)
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    tmp = bpy.data.objects.new(name + '_c', cu)
    scene.collection.objects.link(tmp)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    me.name = name
    if flip:
        me.flip_normals()
    return finish(bpy.data.objects.new(name, me), m, 60)


# ---- spool holder (ASSUMED shape: white clamp on the column top, post + axle, spool axis left-right)
cx_, cy_ = (COL_LO.x + COL_HI.x) / 2, (COL_LO.y + COL_HI.y) / 2
ct = COL_HI.z
rbox('bambu_mini_holder_clamp', (COL_LO.x - 0.002, COL_LO.y - 0.002, ct - 0.014),
     (COL_HI.x + 0.002, COL_HI.y + 0.002, ct + 0.010), 0.005, 'holder_white', segs=3)
SPOOL_R = 0.100
SPOOL_W = 0.066
SX = cx_ - 0.018                              # spool centre (x); the post stands at the clamp's right end
SZ = ct + 0.010 + SPOOL_R + 0.012
post_x0 = SX + SPOOL_W / 2 + 0.006
rbox('bambu_mini_holder_post', (post_x0, cy_ - 0.010, ct + 0.004), (post_x0 + 0.014, cy_ + 0.010, SZ + 0.016), 0.005,
     'holder_white', segs=3)
cyl('bambu_mini_holder_axle', 0.0245, (SX - SPOOL_W / 2 - 0.012, cy_, SZ), (post_x0 + 0.002, cy_, SZ), 'holder_white',
    verts=40, cap_bevel=0.0015)
cyl('bambu_mini_holder_axle_cap', 0.028, (SX - SPOOL_W / 2 - 0.016, cy_, SZ), (SX - SPOOL_W / 2 - 0.012, cy_, SZ),
    'holder_white', verts=40, cap_bevel=0.0012)
# spool on a roller stand on the table, right of the printer, axis left-right (the holder arm stays, empty)
BOX_C = V((SRC_PATH[0].x, SRC_PATH[0].y, CLIP_LO.z))             # bottom (filament inlet) of the right-side box
SP_X = CLIP_HI.x + 0.078                     # flanges ~40 mm clear of the box / carriage's whole Z travel
SP_Y = BOX_C.y - 0.123
ROLL_R, ROLL_DY, BASE_T = 0.011, 0.060, 0.010
ROLL_Z = BASE_T + 0.004 + ROLL_R
SP_Z = ROLL_Z + math.sqrt((SPOOL_R + ROLL_R) ** 2 - ROLL_DY ** 2)   # flange rims resting on both rollers
spool_M = Matrix.Translation(V((SP_X, SP_Y, SP_Z))) @ Matrix.Rotation(math.radians(90), 4, 'Y')
STAND_LO = V((SP_X - 0.048, SP_Y - 0.085, 0.0))
STAND_HI = V((SP_X + 0.048, SP_Y + 0.085, BASE_T))
mat('stand_grey', (0.55, 0.56, 0.57), 0.45, bump=0.04, bscale=1400)
mat('roller', (0.12, 0.12, 0.13), 0.35)
rbox('bambu_mini_spoolstand_base', STAND_LO, STAND_HI, 0.004, 'stand_grey', segs=3)
for sy in (-1, 1):
    ry = SP_Y + sy * ROLL_DY
    cyl('bambu_mini_spoolstand_roller_%d' % (sy > 0), ROLL_R, (SP_X - 0.040, ry, ROLL_Z), (SP_X + 0.040, ry, ROLL_Z),
        'roller', verts=32, cap_bevel=0.0012)
    for sx in (-1, 1):
        xx = SP_X + sx * 0.043
        rbox('bambu_mini_spoolstand_cheek_%d%d' % (sy > 0, sx > 0), (xx - 0.003, ry - 0.009, BASE_T - 0.001),
             (xx + 0.003, ry + 0.009, ROLL_Z + 0.006), 0.0015, 'stand_grey', segs=2)
        cyl('bambu_mini_spoolstand_axle_%d%d' % (sy > 0, sx > 0), 0.003, (xx - 0.0035 * sx, ry, ROLL_Z),
            (xx + 0.0045 * sx, ry, ROLL_Z), 'stand_grey', verts=16)
W = SPOOL_W / 2
fl_t = 0.0028
prof_fl = [(0.0275, -W), (SPOOL_R - 0.0005, -W), (SPOOL_R, -W + fl_t * 0.5), (SPOOL_R - 0.0005, -W + fl_t),
           (0.0275, -W + fl_t)]
spool = []
for side, sgn in (('L', 1), ('R', -1)):
    spool.append(lathe('bambu_mini_spool_flange_' + side, [(r, z * sgn) for r, z in prof_fl], 'spool_white', segs=72))
spool.append(lathe('bambu_mini_spool_core', [(0.0275, -W + fl_t), (0.0275, W - fl_t), (0.0385, W - fl_t),
                                            (0.0385, -W + fl_t)], 'spool_white', segs=48))
R_FIL = 0.086
spool.append(lathe('bambu_mini_spool_filament', [(0.0385, -W + fl_t + 0.0002), (R_FIL - 0.0015, -W + fl_t + 0.0002),
                                                (R_FIL, -W + fl_t + 0.0018), (R_FIL, W - fl_t - 0.0018),
                                                (R_FIL - 0.0015, W - fl_t - 0.0002), (0.0385, W - fl_t - 0.0002)],
                   'filament_spool', segs=96))
for o in spool:
    o.data.transform(spool_M)
# ---- filament path: spool (table) -> short free span up into the box on the printer's right (the FBX's
# filament inlet / runout box on the Z carriage) -> PTFE from the box's top fitting along the model's own route
# -> toolhead push-fit coupling. The FBX's PTFE mesh renders almost fully transparent through its opacity map, so
# it is replaced by a real tube swept along its centreline.
mat('black_collet', (0.03, 0.03, 0.035), 0.45)
m_ptfe = mat('ptfe', (0.95, 0.95, 0.94), 0.32)
bsp = next(n for n in m_ptfe.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
bsp.inputs['Transmission Weight'].default_value = 0.72
bsp.inputs['IOR'].default_value = 1.35
m_ptfe.diffuse_color = (0.93, 0.93, 0.92, 0.6)
# inlet collet under the box (the filament enters from below)
cyl('bambu_mini_box_inlet_collet', 0.0034, BOX_C + V((0, 0, -0.004)), BOX_C + V((0, 0, 0.0008)), 'black_collet',
    verts=24, cap_bevel=0.0005)
# free span: leaves the winding tangentially at the back-top and curves up into the inlet
IN_PT = BOX_C + V((0, 0, -0.004))
dvec = V((IN_PT.y - SP_Y, IN_PT.z - SP_Z))
dd = dvec.length
cand = [math.atan2(dvec.y, dvec.x) + sg * math.acos(R_FIL / dd) for sg in (1, -1)]
ang = max(cand, key=lambda a: math.sin(a))                          # the upper tangent (unwinds over the top)
TAN = V((SP_X - 0.012, SP_Y + R_FIL * math.cos(ang), SP_Z + R_FIL * math.sin(ang)))
tdir = V((0, -math.sin(ang), math.cos(ang)))                        # winding tangent direction at that point
if tdir.dot(IN_PT - TAN) < 0:
    tdir = -tdir
span = (IN_PT - TAN).length
_lclear = math.sqrt((SPOOL_R + 0.007) ** 2 - R_FIL ** 2)        # stays in the spool's plane until past the rims
free = [TAN - tdir * 0.0008, TAN + tdir * _lclear * 0.5, TAN + tdir * _lclear, IN_PT + V((0, 0, -0.035)), IN_PT,
        IN_PT + V((0, 0, 0.007))]
tube('bambu_mini_filament_free', free, 0.000875, 'filament_strand', res=12, bev=4)
FREE_PTS = free
# PTFE along the source centreline: seated 2 mm into the box's top fitting and 2 mm into the toolhead coupling
CPL = V(((CPL_LO.x + CPL_HI.x) / 2, (CPL_LO.y + CPL_HI.y) / 2, CPL_HI.z))
src = [q for q in SRC_PATH[::6] if (q - CPL).length > 0.016 and (q - SRC_PATH[0]).length > 0.006]
path = [SRC_PATH[0] + V((0, 0, -0.002)), SRC_PATH[0] + V((0, 0, 0.003))] + src +     [CPL + V((0, 0, 0.008)), CPL + V((0, 0, -0.002))]
log('PTFE ends: box %s, toolhead coupling %s (source tube ended %.1f mm from it)' % (
    tuple(round(x, 4) for x in path[0]), tuple(round(x, 4) for x in path[-1]), (SRC_PATH[-1] - CPL).length * 1000))
tube('bambu_mini_ptfe_tube', path, 0.0020, 'ptfe', res=8, bev=8, caps=False)
tube('bambu_mini_ptfe_tube_bore', path, 0.0010, 'ptfe', res=8, bev=4, caps=False, flip=True)
tube('bambu_mini_filament_in_tube', [BOX_C + V((0, 0, 0.004))] + path[1:-1] + [CPL + V((0, 0, -0.006))], 0.000875,
     'filament_strand', res=8, bev=4, caps=False)


def curve_samples(pts):
    """dense samples of the same AUTO-handle bezier the tube uses"""
    cu = bpy.data.curves.new('tmp_s', 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = 32
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = V(p)
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    tmp = bpy.data.objects.new('tmp_s', cu)
    scene.collection.objects.link(tmp)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    out = [V(v.co) for v in me.vertices]
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return out


PTFE_PTS = curve_samples(path)
FREE_SMP = curve_samples(free)
PTFE_LEN = sum((b - a).length for a, b in zip(PTFE_PTS, PTFE_PTS[1:]))
_bend = []
for a, b, c in zip(PTFE_PTS[2:-2], PTFE_PTS[3:-1], PTFE_PTS[4:]):
    t1, t2 = (b - a), (c - b)
    if t1.length > 1e-6 and t2.length > 1e-6:
        an = t1.angle(t2)
        if an > 1e-4:
            _bend.append(((t1.length + t2.length) / 2) / an)
PTFE_MIN_R = min(_bend)

# ---- half-finished 3DBenchy (cut at 24 of 48 mm), bow to the front, nozzle over the cabin's front pillar
B_M = (Matrix.Translation(V((NOZ.x, NOZ.y, BED_TOP))) @ Matrix.Rotation(math.radians(-90), 4, 'Z') @
       Matrix.Translation(V((-3.8e-3, 0, 0))) @ Matrix.Scale(0.001, 4))


def benchy_obj(name, bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.transform(B_M)
    o = from_bm(name, bm)
    o.data.materials.append(MATS['print'])
    o.data.materials.append(MATS['print_top'])
    for p in o.data.polygons:
        p.material_index = 1 if p.normal.z > 0.9 else 0
    coll.objects.link(o)
    EXTRA.append(o)
    return o


def box(bm, x0, x1, y0, y1, z0, z1):
    vs = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in f])


bm = bmesh.new()
stations = [-30, -28.5, -26, -22, -17, -11, -5, 1, 7, 12, 16, 19.5, 22.5, 25, 27, 28.6, 29.6, 30]
rings = []
for x in stations:
    w = 13.4 + 2.1 * (1 - ((x + 5) / 25.0) ** 2) if x <= -5 else 15.5 * math.sqrt(max(0.0, 1 - ((x + 5) / 35.0) ** 2))
    w = max(w, 0.15) * (0.97 if x == -30 else 1.0)
    zb = 0.0 if x < 8 else 12.5 * ((x - 8) / 22.0) ** 1.6
    h = min(BENCHY_H, 15.5 + 9.0 * ((x + 30) / 60.0) ** 2.4)
    rake = 0.0 if x < 8 else 5.0 * ((x - 8) / 22.0) ** 2
    wi = w - 1.6
    closed = wi < 0.4
    wi = max(wi, 0.0)
    d = h if closed else min(max(11.0, zb + 1.8), h - 0.8)
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
benchy_obj('bambu_mini_benchy_hull', bm)
bm = bmesh.new()
CW, CX0, CX1, CY, DZ, TZ = 2.4, -21.0, 5.0, 11.0, 11.0, BENCHY_H
for s_ in (-1, 1):
    y0, y1 = sorted((s_ * CY, s_ * (CY - CW)))
    box(bm, CX0, -14.0, y0, y1, DZ, TZ)
    box(bm, -6.0, CX1, y0, y1, DZ, TZ)
box(bm, CX1 - CW, CX1, -CY + CW, CY - CW, DZ, 17.0)
for y0, y1 in ((-CY + CW, -8.5), (-1.5, 1.5), (8.5, CY - CW)):
    box(bm, CX1 - CW, CX1, y0, y1, 17.0, TZ)
box(bm, CX0, CX0 + CW, -CY + CW, CY - CW, DZ, 16.5)
for y0, y1 in ((-CY + CW, -6.0), (6.0, CY - CW)):
    box(bm, CX0, CX0 + CW, y0, y1, 16.5, TZ)
benchy_obj('bambu_mini_benchy_cabin', bm)
bm = bmesh.new()
for s_ in (-1, 1):
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=1.8, radius2=1.8, depth=4.5,
                          matrix=Matrix.Translation((-26.0, s_ * 7.0, DZ + 2.25)))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=2.4, radius2=2.4, depth=0.8,
                          matrix=Matrix.Translation((-26.0, s_ * 7.0, DZ + 4.9)))
benchy_obj('bambu_mini_benchy_bollards', bm)
for s_ in (-1, 1):                                     # hawse holes either side of the bow
    xh = 21.0
    wh = 15.5 * math.sqrt(max(0.0, 1 - ((xh + 5) / 35.0) ** 2))
    cyl('bambu_mini_benchy_hawse_%d' % (s_ > 0), 1.6e-3, B_M @ V((xh + 0.9, s_ * (wh - 1.9), 19.3)),
        B_M @ V((xh + 0.9, s_ * (wh + 0.3), 19.3)), 'shadow', verts=16)

# ============================================================================== 6. table + placement in the room
with bpy.data.libraries.load(BAMBU_BLEND, link=False) as (src, dst):
    dst.objects = [nm for nm in src.objects if nm.startswith('bambu_table')]
TABLE = []
dxy = TABLE_C - TABLE_SRC_C
for o in dst.objects:
    mw = o.matrix_basis.copy()
    if o.parent:                                   # appended objects are not evaluated: rebuild the world matrix
        mw = o.parent.matrix_basis @ o.matrix_parent_inverse @ mw
    o.parent = None
    o.name = o.name.replace('bambu_table', 'bambu_mini_table')
    o.data = o.data.copy()
    o.data.name = o.name
    o.data.transform(mw)
    o.matrix_world = Matrix()
    o.data.transform(Matrix.Translation((dxy.x, dxy.y, 0)))
    coll.objects.link(o)
    TABLE.append(o)
for m in {m for o in TABLE for m in o.data.materials if m}:
    if not m.name.startswith('bambu_mini_'):
        m.name = m.name.replace('bambu_', 'bambu_mini_')
tp = [o.matrix_world @ V(c) for o in TABLE for c in o.bound_box]
log('TABLE_BBOX', [(round(min(p[i] for p in tp), 3), round(max(p[i] for p in tp), 3)) for i in range(3)])

PRN = PRINTER + EXTRA
d = VIEWER.xy - TABLE_C
THETA = math.atan2(d.x, -d.y)                         # local -Y (front) -> toward the seated viewer
rotM = Matrix.Rotation(THETA, 4, 'Z')
# centre the rotated printer's footprint (what stands on the table: base, feet, column foot) on the table
foot = [rotM @ V(v.co) for o in PRINTER for v in o.data.vertices if v.co.z < 0.03]
foot += [rotM @ V((x, y, 0)) for x in (STAND_LO.x, STAND_HI.x) for y in (STAND_LO.y, STAND_HI.y)]
fc = V(((min(p.x for p in foot) + max(p.x for p in foot)) / 2, (min(p.y for p in foot) + max(p.y for p in foot)) / 2))
PLACE = Matrix.Translation(V((TABLE_C.x - fc.x, TABLE_C.y - fc.y, TABLE_H))) @ rotM
root.location = (TABLE_C.x, TABLE_C.y, 0.0)
for o in PRN:
    o.matrix_world = PLACE
bpy.context.view_layer.update()
for o in PRN + TABLE:
    mw = o.matrix_world.copy()
    o.parent = root
    o.matrix_world = mw
bpy.context.view_layer.update()


def bb(pp):
    return [(round(min(p[i] for p in pp), 3), round(max(p[i] for p in pp), 3)) for i in range(3)]


fr = [V(v.co) for o in PRINTER for v in o.data.vertices]
DIMS = [round((max(p[i] for p in fr) - min(p[i] for p in fr)) * 1000, 1) for i in range(3)]
allp = [V(v.co) for o in PRN for v in o.data.vertices]
DIMS_SPOOL = [round((max(p[i] for p in allp) - min(p[i] for p in allp)) * 1000, 1) for i in range(3)]
pei = [V(v.co) for v in bpy.data.objects['bambu_mini_heatbed'].data.vertices if v.co.z > BED_TOP - 0.0006]
log('DIMS_MM frame W x D x H', DIMS, '| with spool', DIMS_SPOOL, '| PEI top %.1f x %.1f mm' % (
    (max(p.x for p in pei) - min(p.x for p in pei)) * 1000, (max(p.y for p in pei) - min(p.y for p in pei)) * 1000))
_fp = [PLACE @ V(v.co) for o in PRINTER for v in o.data.vertices if v.co.z < 0.03]
_fp += [PLACE @ V((x, y, 0)) for x in (STAND_LO.x, STAND_HI.x) for y in (STAND_LO.y, STAND_HI.y)]
_tx0, _tx1 = TABLE_C.x - 0.28, TABLE_C.x + 0.28
_ty0, _ty1 = TABLE_C.y - 0.235, TABLE_C.y + 0.235
log('footprint margin to the table-top edges: %.1f mm' % (1000 * min(min(q.x - _tx0, _tx1 - q.x, q.y - _ty0,
                                                                         _ty1 - q.y) for q in _fp)))
log('PRINTER_WORLD_BBOX', bb([PLACE @ p for p in allp]), 'rotation %.1f deg' % math.degrees(THETA))
# PTFE clearance: nearest printer / holder / spool surface from the tube axis (ignoring 10 mm at each fitting)
_bm = bmesh.new()
for o in PRINTER + [o for o in EXTRA if not o.name.startswith(('bambu_mini_ptfe', 'bambu_mini_filament',
                                                                  'bambu_mini_box_inlet'))]:
    _bm.from_mesh(o.data)
_bvh = BVHTree.FromBMesh(_bm)
_bm.free()
_clear = []
_acc = 0.0
for a, b in zip(PTFE_PTS, PTFE_PTS[1:]):
    _acc += (b - a).length
    if 0.010 < _acc < PTFE_LEN - 0.010:
        _clear.append((_bvh.find_nearest(b)[3] - 0.002, tuple(round(x, 4) for x in b)))
_worst = min(_clear)
_facc, _fl = 0.0, sum((b - a).length for a, b in zip(FREE_SMP, FREE_SMP[1:]))
_fclear = []
for a, b in zip(FREE_SMP, FREE_SMP[1:]):
    _facc += (b - a).length
    if 0.012 < _facc < _fl - 0.012:
        _fclear.append((_bvh.find_nearest(b)[3] - 0.000875, tuple(round(x, 4) for x in b)))
log('free filament span %.0f mm, min clearance %.1f mm at %s' % (_fl * 1000, min(_fclear)[0] * 1000,
                                                                  min(_fclear)[1]))
_far = CPL + V((-0.180, 0, 0))
FIT_C = path[0]
PTFE_MIN_R = min(_bend)
log('PTFE length %.0f mm, min bend radius %.0f mm, min clearance to printer surfaces %.1f mm at %s; straight '
    'distance inlet->coupling with the toolhead at the far-left end %.0f mm' % (
        PTFE_LEN * 1000, PTFE_MIN_R * 1000, _worst[0] * 1000, _worst[1], (_far - FIT_C).length * 1000))
TRIS_EXTRA = sum(tris_of(o.data) for o in EXTRA)
TRIS_TABLE = sum(tris_of(o.data) for o in TABLE)
log('TRIS printer %d + spool/holder/Benchy %d + table %d = %d' % (TRIS_PRINTER, TRIS_EXTRA, TRIS_TABLE,
                                                                  TRIS_PRINTER + TRIS_EXTRA + TRIS_TABLE))


# ============================================================================== previews (printer + table only)
def previews():
    setup_render()
    ground(0.0, 4.0)
    for nm, verts in (('prev_wall_r', [(1.91, -1.4, 0), (1.91, 1.3, 0), (1.91, 1.3, 2.7), (1.91, -1.4, 2.7)]),
                      ('prev_wall_w', [(-1, 1.30, 0), (1.91, 1.30, 0), (1.91, 1.30, 2.7), (-1, 1.30, 2.7)])):
        me = bpy.data.meshes.new(nm)
        me.from_pydata(verts, [], [(0, 1, 2, 3)])
        fm = bpy.data.materials.new(nm)
        fm.use_nodes = True
        b_ = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        b_.inputs['Base Color'].default_value = (0.62, 0.62, 0.60, 1)
        me.materials.append(fm)
        prev_obj(bpy.data.objects.new(nm, me))

    def P(x, y, z):                                   # printer-local -> room
        return PLACE @ V((x, y, z))
    cam = lights_and_cam(P(0, 0, 0.2), 0.8)
    if not ONLY or '34' in ONLY:
        shot(cam, P(0.40, -0.80, 0.55), P(0.0, 0.02, 0.27), 35, os.path.join(PARTS, 'bambu_mini_34.png'), (1000, 1150))
    if not ONLY or 'benchy' in ONLY:
        shot(cam, P(NOZ.x + 0.07, NOZ.y - 0.15, BED_TOP + 0.05), P(NOZ.x, NOZ.y, BED_TOP + 0.014), 55,
             os.path.join(PARTS, 'bambu_mini_benchy.png'))
    if not ONLY or 'inlet' in ONLY:
        shot(cam, P(0.33, 0.27, 0.33), P(0.165, 0.03, 0.15), 36, os.path.join(PARTS, 'bambu_mini_inlet.png'))
    if not ONLY or 'toolhead' in ONLY:
        shot(cam, P(0.20, -0.30, 0.36), P(0.075, 0.03, 0.235), 38, os.path.join(PARTS, 'bambu_mini_toolhead.png'))
    if not ONLY or 'table' in ONLY:
        shot(cam, V((0.55, -0.45, 1.20)), V((1.50, 0.85, 0.60)), 30, os.path.join(PARTS, 'bambu_mini_table.png'),
             (1000, 1150))
    clear_prev()


if not NO_RENDER:
    previews()
scene.render.filepath = ''
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
log('SAVED', OUT, '%.1f MB' % (os.path.getsize(OUT) / 1e6))
