"""
Sunset lightmap bake for the three.js room (re-runnable, headless, CUDA GPU-only).

    blender -b --factory-startup --python blender/scripts/v2_bake_sunset.py -- <stage> [options]

    stage:   all | prepare | bake | export | verify
             prepare  copy room.blend -> blender/bake/sunset/room_bake.blend, bake-only scene edits,
                      second UV layer `UVMap_lightmap` per baked object, packed per atlas; saves the copy
             bake     Cycles DIFFUSE (direct+indirect, colour off) per atlas, OIDN denoise, linear half EXR
                      + sRGB preview PNG; saves the copy
             export   one GLB per atlas (TEXCOORD_1 = UVMap_lightmap, no images) + UV round-trip check
             verify   reference Cycles renders vs albedo x lightmap preview -> compare_<cam>.png
    options: --samples N (default 1024)  --res-scale F (default 1.0, e.g. 0.25 for a smoke test)
             --only atlas[,atlas]  --ref-spp N (128)  --prev-spp N (32)  --pct N (50)

Source: $ROOM_BLEND, else blender/scene/room.blend in this checkout, else the main checkout's (a git worktree
has no room.blend: it is git-ignored). room.blend is only ever READ (shutil.copy). Every save goes to room_bake.blend; the script refuses to
save a file called room.blend. Manifest: blender/bake/sunset/manifest.json (merged per stage).
"""
import bpy, bmesh, sys, os, json, time, math, shutil, struct, hashlib
import numpy as np
from mathutils import Vector, geometry

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.environ.get('ROOM_BLEND') or next(
    (p for p in (os.path.join(REPO, 'blender', 'scene', 'room.blend'),
                 os.path.join(os.path.dirname(REPO), 'Hub', 'blender', 'scene', 'room.blend')) if os.path.exists(p)),
    os.path.join(REPO, 'blender', 'scene', 'room.blend'))
OUT = os.path.join(REPO, 'blender', 'bake', 'sunset')
COPY = os.path.join(OUT, 'room_bake.blend')
TMP = os.path.join(REPO, 'tmp', 'bake_sunset')
MANIFEST = os.path.join(OUT, 'manifest.json')
LM_UV = 'UVMap_lightmap'
BAKE_NODE = 'LM_BAKE'
MARGIN_UV_PX = 6          # gap between islands in the packed lightmap UV: 3 px of own-island gutter per side
# Cycles' bake margin must stay within half the gutter: with several objects baked into one image Blender
# applies each object's margin on its own, over texels other objects already baked. A 16 px margin (8 px in
# the first bake, with 4 px gutters) wrote ~10-texel bands of one object's extension into its neighbours'
# islands: the sky-blue strips on the left wall by the door and at the window corner. The gutters are
# filled by the island-aware dilation below instead. (scripts/v2look/blender_albedo.py reads this too.)
BAKE_MARGIN_PX = MARGIN_UV_PX // 2
DILATE_PX = 32            # post-bake fill of gutters and buried texels from valid texels of the same island
ROBOT_LIGHT_AVG = 3.5     # driver 3.5 + 3.5*sin(frame*2pi/96) -> mean 3.5

# ---------------------------------------------------------------------------------------------
# Bake set. Per atlas: resolution, objects, per-object linear texel weight, and whether islands no
# visitor can see get shrunk ('shrink_hidden'): an island keeps its full density if ANY of its faces
# is seen, unoccluded and from the front, from any viewpoint in VIEW_GRID or a camera in the room
# (ray cast against every baked mesh). Only islands seen from nowhere (outer faces of wall slabs,
# slab ends buried in the next wall, curtain backs, rug underside) get HIDDEN_SHRINK of the density.
# ---------------------------------------------------------------------------------------------
SHELL = ['rs_floor', 'rs_ceiling', 'rs_wall_back', 'rs_wall_left', 'rs_wall_right', 'rs_wall_window',
         'rs_hallway_stub', 'rs_baseboard', 'rs_crown', 'rs_door_casing', 'rs_door_jamb', 'rs_door_slab',
         'rs_window_apron', 'rs_window_casing', 'rs_window_frame', 'rs_window_jamb', 'rs_window_sash',
         'rs_window_stool', 'rs_wall_patches', 'rs_scuff_backwall', 'rs_scuff_baseboard', 'rs_scuff_floor']
ATLASES = {
    'shell': dict(res=2048, objects=SHELL, shrink_hidden=True,
                  weights={'rs_hallway_stub': 0.3}),
    'desk': dict(res=1024, objects=['desk_top_tmp', 'desk_top_tmp_1', 'desk_top_tmp_2', 'desk_top_tmp_3', 'desk_top_tmp_4'],
                 shrink_hidden=False, down_shrink=0.5,
                 weights={'desk_top_tmp': 1.0, 'desk_top_tmp_1': 1.0, 'desk_top_tmp_2': 0.55, 'desk_top_tmp_3': 0.55, 'desk_top_tmp_4': 0.4}),
    'furniture': dict(res=512, shrink_hidden=False, weights={},
                      objects=['bookrack_board', 'bookrack_bracket_L', 'bookrack_bracket_R', 'bookrack_bookend_L', 'bookrack_bookend_R',
                               'bambu_mini_table_top', 'bambu_mini_table_shelf', 'bambu_mini_table_apron_back',
                               'bambu_mini_table_apron_left', 'bambu_mini_table_apron_right', 'bambu_mini_table_drawer_front',
                               'bambu_mini_table_rail_top', 'bambu_mini_table_rail_bot', 'bambu_mini_table_leg_00',
                               'bambu_mini_table_leg_01', 'bambu_mini_table_leg_10', 'bambu_mini_table_leg_11']),
    'soft': dict(res=1024, objects=['curtain_left', 'curtain_right', 'Mesh_4'], shrink_hidden=True,
                 weights={'Mesh_4': 1.0}),
}
HIDDEN_SHRINK = 0.12
PARTLY_SEEN = (0.15, 0.5)  # an island less than 15 % seen (by sampled area; e.g. curtain backs, seen only at
                           # the outer pleat) gets half the linear density
POOR_FILL = 0.45           # islands filling less of their min-area box than this are split per face
# Where a visitor's eye can be (Blender coords, m): a grid over the whole room interior at sitting to
# standing-and-leaning heights, plus every camera inside the room (CAM_stand, CAM_seat, close-ups).
VIEW_GRID = dict(x=(-1.80, 1.65, 0.25), y=(-1.15, 1.05, 0.25), z=(0.8, 1.2, 1.6, 2.0))
# Objects unwrapped with seams (sharp edges + tile cuts) + angle-based unwrap instead of smart project.
# Slabs longer than TILE are bisected so the packer can fill a square atlas. At 2048 a whole wall,
# floor or ceiling face fits as ONE island, so TILE is now larger than the room: every tile cut was
# a seam, and the 1.4 m tiles of the 1024 bake showed as panels of different brightness with dark
# lines between them (each tile was denoised as its own image). Bisect interpolates the existing UV
# layers, so UV0 is unchanged.
SEAM_UNWRAP = {'rs_floor', 'rs_ceiling', 'rs_wall_back', 'rs_wall_left', 'rs_wall_right', 'rs_wall_window',
               'rs_hallway_stub', 'rs_door_slab', 'desk_top_tmp', 'desk_top_tmp_1', 'Mesh_4'}
# Cloth: seams only between the solidify shells (front + rim | back), no tile cuts, so each visible
# curtain face is one island (the 1024 bake split them into ~600 islands per curtain: vertical streaks).
CLOTH_UNWRAP = {'curtain_left', 'curtain_right'}
# The rug's top is a fan of unwelded triangles (custom normals stop the weld), so every wedge became an
# island and a radial seam. It renders MeshBasic on the web (normals unused): weld it.
WELD_DESPITE_NORMALS = {'Mesh_4'}
# trims: rings (casings, jambs) and corner-wrapping strips (baseboard, crown) pack terribly as whole
# islands, so they are cut into short straight pieces
TRIM_UNWRAP = {'rs_baseboard', 'rs_crown', 'rs_door_casing', 'rs_door_jamb', 'rs_window_casing', 'rs_window_jamb',
               'rs_window_apron', 'rs_window_stool', 'rs_window_frame', 'rs_window_sash'}
# Crown and baseboard: one island per wall run (seams where a face's nearest wall changes), never split
# per face: their curved profiles would become 2-texel strips that the denoiser cannot clean (speckle).
RUN_SPLIT = {'rs_crown', 'rs_baseboard'}
TILE = 4.5
TRIM_TILE = 2.1   # crown / baseboard: one piece per wall run (corners are sharp seams anyway)
SHARP_SEAM_DEG = 50
SHARP_SEAM_DEG_OBJ = {"curtain_left": 85, "curtain_right": 85}  # fallback if the solidify shells cannot be told apart
EXCLUDED_NOTES = {
    'NEW_monitor stand/base': 'metallic=1 aluminium (mon_alu_spacegrey/channel_dark): Cycles diffuse pass is 0 and three.js '
                              'lightMap only modulates diffuse, so a lightmap would be black and unused',
    'rs_* outlets/switches/hinges/lever/thermostat/smoke alarm/register/nail holes/ceiling light': 'small detailed props',
    'bookrack books + items (Mesh_160..178)': 'books are dynamic, the rest are small props',
    'bambu_mini_table knob/glides/drawer cavity': 'small or metal',
    'curtain rod/rings/clips/brackets': 'small, black metal',
    'Mesh_11 window glass, NEW_exterior': 'glass / exterior stays on its own materials',
}
CAMS = ['CAM_stand', 'CAM_seat']
# Close-ups rendered by `verify` too (three.js eye, target, vertical fov, size), the web screenshots' poses:
# the ceiling toward the crown and window head, and the left curtain.
CLOSEUPS = {'CU_ceiling': ((0.3, 1.7, 0.5), (-0.6, 2.72, -1.1), 60, (1280, 800)),
            'CU_curtain': ((-0.2, 1.3, -0.3), (-1.0, 1.4, -1.3), 60, (1280, 800))}


def log(*a):
    print('[bake]', *a, flush=True)


def args():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = dict(stage=a[0] if a else 'all', samples=1024, res_scale=1.0, only=None, ref_spp=128, prev_spp=32, pct=50)
    i = 1
    while i < len(a):
        k = a[i].lstrip('-').replace('-', '_'); v = a[i + 1]; i += 2
        o[k] = v if k == 'only' else (float(v) if k == 'res_scale' else int(v))
    if o['only']:
        o['only'] = o['only'].split(',')
    return o


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            return json.load(f)
    return {}


def save_manifest(m):
    with open(MANIFEST, 'w') as f:
        json.dump(m, f, indent=2)


def safe_save():
    p = bpy.data.filepath
    assert os.path.basename(p) != 'room.blend' and os.path.abspath(p) == os.path.abspath(COPY), p
    bpy.ops.wm.save_as_mainfile(filepath=COPY, compress=True)
    log('saved', COPY)


def open_copy():
    bpy.ops.wm.open_mainfile(filepath=COPY, load_ui=False)
    assert os.path.abspath(bpy.data.filepath) == os.path.abspath(COPY)


def gpu(sc):
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = (d.type == 'CUDA')
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'GPU'


def atlas_list(opt):
    return [a for a in ATLASES if not opt['only'] or a in opt['only']]


def res_of(name, opt):
    return max(64, int(round(ATLASES[name]['res'] * opt['res_scale'])))


def tri_count(o):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    m = ev.to_mesh(); m.calc_loop_triangles(); n = len(m.loop_triangles); ev.to_mesh_clear()
    return n


def unhide(o):
    o.hide_viewport = False
    o.hide_select = False
    try:
        o.hide_set(False)
    except RuntimeError:
        pass

    def walk(lc):
        for ch in lc.children:
            if o.name in ch.collection.all_objects:
                ch.hide_viewport = False
                walk(ch)
    walk(bpy.context.view_layer.layer_collection)


def select_only(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def light_params(sc):
    out = {}
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and not o.hide_render and o.visible_get():
            l = o.data
            d = dict(type=l.type, energy=l.energy, color=list(l.color), location=list(o.matrix_world.translation),
                     direction=list((o.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()))
            if l.type == 'SUN':
                d['angle_rad'] = l.angle
            if l.type == 'AREA':
                d.update(shape=l.shape, size=l.size, spread=l.spread)
            if l.type in ('POINT', 'SPOT'):
                d['radius'] = l.shadow_soft_size
            if l.type == 'SPOT':
                d.update(spot_size=l.spot_size, spot_blend=l.spot_blend)
            # What a live (runtime) copy of the light needs to match Cycles: shadow softness, shadows on/off,
            # ray visibility, the light's own node tree (it scales the emission when used), and three.js
            # coordinates (a Blender point (x, y, z) is three (x, z, -y)).
            p, v = o.matrix_world.translation, (o.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
            d.update(shadow_soft_size=l.shadow_soft_size, use_shadow=bool(getattr(l, 'use_shadow', True)),
                     visible_diffuse=o.visible_diffuse, visible_glossy=o.visible_glossy,
                     visible_transmission=o.visible_transmission,
                     three_position=[p.x, p.z, -p.y], three_direction=[v.x, v.z, -v.y])
            if l.type == 'SUN':
                d['angle_deg'] = math.degrees(l.angle)
            if l.type == 'AREA':
                d['spread_deg'] = math.degrees(l.spread)
            ll = getattr(o, 'light_linking', None)
            if ll and (ll.receiver_collection or ll.blocker_collection):
                d['light_linking'] = dict(receivers=getattr(ll.receiver_collection, 'name', None),
                                          blockers=getattr(ll.blocker_collection, 'name', None))
            if getattr(l, 'use_nodes', False) and l.node_tree:
                nodes = [n for n in l.node_tree.nodes if n.type not in ('OUTPUT_LIGHT', 'FRAME', 'REROUTE')]
                em = [n for n in nodes if n.type == 'EMISSION']
                d['node_tree'] = dict(node_types=sorted({n.type for n in nodes}),
                                      emission=[dict(strength=n.inputs['Strength'].default_value,
                                                     color=list(n.inputs['Color'].default_value)[:3],
                                                     linked=[s.name for s in n.inputs if s.is_linked]) for n in em])
            out[o.name] = d
    w = sc.world
    sky = {}
    for n in w.node_tree.nodes:
        if n.type == 'TEX_SKY':
            for k in ('sky_type', 'sun_elevation', 'sun_rotation', 'sun_size', 'sun_intensity', 'sun_disc', 'altitude',
                      'air_density', 'aerosol_density', 'ozone_density'):
                if hasattr(n, k):
                    sky[k] = getattr(n, k)
        if n.type == 'BACKGROUND':
            sky['background_strength'] = n.inputs[1].default_value
    vs = sc.view_settings
    return dict(lights=out, sky=sky,
                color_management=dict(view_transform=vs.view_transform, look=vs.look, exposure=vs.exposure, gamma=vs.gamma))


# ---------------------------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------------------------
def bake_scene_edits(sc):
    """Bake-only differences from room.blend: no room volume, robot light at its average."""
    edits = []
    v = bpy.data.objects.get('fx_room_volume')
    if v:
        v.hide_render = True; v.hide_viewport = True
        edits.append('fx_room_volume hidden (volume cannot be represented in a surface lightmap)')
    for m in bpy.data.materials:
        nt = m.node_tree
        if not (nt and nt.animation_data and nt.animation_data.drivers):
            continue
        for fc in list(nt.animation_data.drivers):
            path, expr = fc.data_path, fc.driver.expression
            if 'robot' not in m.name:
                continue
            nt.driver_remove(path)
            sock = nt.path_resolve(path.rsplit('.', 1)[0])
            sock.default_value = ROBOT_LIGHT_AVG
            edits.append(f'{m.name}: driver "{expr}" removed, set to {ROBOT_LIGHT_AVG}')
    return edits


def zero_uv(me, name):
    uv = me.uv_layers.new(name=name)
    n = len(me.loops)
    uv.data.foreach_set('uv', np.zeros(n * 2, dtype=np.float32))
    return uv


def world_face_area(f, mw):
    pts = [mw @ v.co for v in f.verts]
    a = Vector((0, 0, 0))
    for i in range(1, len(pts) - 1):
        a += (pts[i] - pts[0]).cross(pts[i + 1] - pts[0])
    return a.length * 0.5


def uv_face_area(f, uvl):
    uv = [l[uvl].uv for l in f.loops]
    s = 0.0
    for i in range(len(uv)):
        x0, y0 = uv[i]; x1, y1 = uv[(i + 1) % len(uv)]
        s += x0 * y1 - x1 * y0
    return abs(s) * 0.5


def islands(bm, uvl):
    parent = {f.index: f.index for f in bm.faces}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    eps = 1e-12
    for e in bm.edges:
        lf = e.link_loops
        if len(lf) != 2:
            continue
        l1, l2 = lf
        a1, b1 = l1[uvl].uv, l1.link_loop_next[uvl].uv
        if l2.vert == l1.vert:
            a2, b2 = l2[uvl].uv, l2.link_loop_next[uvl].uv
        else:
            a2, b2 = l2.link_loop_next[uvl].uv, l2[uvl].uv
        if (a1 - a2).length_squared < eps and (b1 - b2).length_squared < eps:
            r1, r2 = find(l1.face.index), find(l2.face.index)
            if r1 != r2:
                parent[r1] = r2
    groups = {}
    for f in bm.faces:
        groups.setdefault(find(f.index), []).append(f)
    return list(groups.values())


class Visibility:
    """Can a visitor see this face? Eye points: VIEW_GRID over the room interior plus every camera inside
    the room. A sample point on a face is seen from an eye if the eye is in front of the face and a ray
    from the point to the eye hits none of the baked meshes (BVH of shell, desk, furniture, soft)."""

    def __init__(self, sc, objs, bounds):
        from mathutils.bvhtree import BVHTree
        dg = bpy.context.evaluated_depsgraph_get()
        verts, polys = [], []
        for o in objs:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            base = len(verts)
            mw = o.matrix_world
            verts.extend(mw @ v.co for v in me.vertices)
            polys.extend([base + i for i in p.vertices] for p in me.polygons)
            ev.to_mesh_clear()
        self.tree = BVHTree.FromPolygons(verts, polys, epsilon=0.0)
        (x0, y0, z0), (x1, y1, z1) = bounds
        eyes = []
        for c in bpy.data.objects:
            t = c.matrix_world.translation
            if c.type == 'CAMERA' and x0 < t.x < x1 and y0 < t.y < y1 and z0 < t.z < z1:
                eyes.append(tuple(t))
        g = VIEW_GRID
        for x in np.arange(*g['x']):
            for y in np.arange(*g['y']):
                for z in g['z']:
                    eyes.append((float(x), float(y), float(z)))
        self.eyes = np.array(eyes, dtype=np.float64)
        self.casts = 0
        log('visibility:', len(self.eyes), 'eye points,', len(polys), 'occluder polygons')

    def point_seen(self, p, n):
        d = self.eyes - p
        dist = np.linalg.norm(d, axis=1)
        front = (d @ n) > 0.02 * dist          # in front of the face, not grazing
        if not front.any():
            return False
        idx = np.nonzero(front)[0]
        idx = idx[np.argsort(dist[idx])]
        if len(idx) > 96:                      # nearest 48 + 48 spread over the rest
            idx = np.concatenate([idx[:48], idx[48::max(1, (len(idx) - 48) // 48)][:48]])
        o = Vector(p + n * 2e-3)
        for i in idx:
            dv = Vector(d[i] / dist[i])
            self.casts += 1
            hit = self.tree.ray_cast(o, dv, float(dist[i]) - 2e-3)
            if hit[0] is None:
                return True
        return False

    def face_seen(self, f, mw, nmat):
        n = np.array((nmat @ f.normal).normalized())
        c = np.array(mw @ f.calc_center_median())
        if self.point_seen(c, n):
            return True
        if world_face_area(f, mw) > 0.02:      # big faces: also near each corner
            for v in f.verts:
                q = np.array(mw @ v.co) * 0.85 + c * 0.15
                if self.point_seen(q, n):
                    return True
        return False


def run_seams(o):
    """Seams between faces of a wall-hugging trim that lie nearest to different walls (planes = the trim's
    own world bounding box). Edit mode. Returns the number of seam edges."""
    mw = o.matrix_world
    bb = [mw @ Vector(c) for c in o.bound_box]
    planes = [(0, min(p.x for p in bb)), (0, max(p.x for p in bb)), (1, min(p.y for p in bb)), (1, max(p.y for p in bb))]
    me = o.data
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table(); bm.faces.index_update()
    cls = {}
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        cls[f.index] = min(range(4), key=lambda k: abs(c[planes[k][0]] - planes[k][1]))
    n = 0
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) == 2 and cls[lf[0].index] != cls[lf[1].index]:
            e.seam = True; n += 1
    bmesh.update_edit_mesh(me)
    return n


def split_poor_islands(o, fill_min=POOR_FILL):
    """Rings (window frame, sash, casings, reveals) and strips bent round a corner unwrap as islands that
    fill a small part of their bounding box; so do the U-shaped n-gons the limited dissolve leaves on jambs
    and reveals. Re-unwrap those islands one face per island, their n-gons first triangulated and re-joined
    into quads. Edit mode."""
    me = o.data
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table(); bm.faces.index_update()
    uvl = bm.loops.layers.uv[LM_UV]
    poor = []
    for isl in islands(bm, uvl):
        if len(isl) < 2 and len(isl[0].verts) <= 4:
            continue
        pts = [l[uvl].uv.copy() for f in isl for l in f.loops]
        ua = sum(uv_face_area(f, uvl) for f in isl)
        try:
            hull = geometry.convex_hull_2d(pts)
            ang = geometry.box_fit_2d([pts[i] for i in hull])
        except Exception:
            ang = 0.0
        c, si = math.cos(ang), math.sin(ang)
        P = np.array([tuple(p) for p in pts]) @ np.array([[c, si], [-si, c]])
        box = float(np.prod(P.max(0) - P.min(0)))
        if box > 0 and ua / box < fill_min:
            poor.extend(isl)
    if not poor:
        return 0
    poor_idx = [f.index for f in poor]
    tag = bm.faces.layers.int.get('lm_poor') or bm.faces.layers.int.new('lm_poor')
    bm.faces.ensure_lookup_table()
    poor = [bm.faces[i] for i in poor_idx]
    for f in bm.faces:
        f[tag] = 0
    for f in poor:
        f[tag] = 1
    ngons = [f for f in poor if len(f.verts) > 4]
    if ngons:   # concave n-gons: triangles re-joined into quads where they make a decent one
        tr = bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
        bmesh.ops.join_triangles(bm, faces=tr['faces'], angle_face_threshold=math.radians(1),
                                 angle_shape_threshold=math.radians(60), cmp_materials=True)
    poor = [f for f in bm.faces if f[tag]]
    for f in bm.faces:
        f.select = False
    for f in poor:
        f.select = True
        for e in f.edges:
            e.seam = True
    bm.faces.layers.int.remove(tag)
    bmesh.update_edit_mesh(me)
    bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
    bpy.ops.mesh.select_all(action='SELECT')
    return len(poor)


def normalize_islands(objs, cfg, vis, isl_out):
    """Uniform texel density across all objects of the atlas (world-space area incl. parent transforms),
    times per-object weight; islands no visitor can see (Visibility) shrunk. Appends island records to
    isl_out. Returns ({obj: shrunk islands}, {obj: set of face indices in seen islands})."""
    stats, seen_faces = {}, {}
    for o in objs:
        me = o.data
        bm = bmesh.from_edit_mesh(me)
        bm.faces.ensure_lookup_table(); bm.faces.index_update()
        uvl = bm.loops.layers.uv[LM_UV]
        mw = o.matrix_world
        nmat = mw.to_3x3().inverted().transposed()
        w_obj = cfg['weights'].get(o.name, 1.0)
        nshrunk = 0
        seen_faces[o.name] = set()
        for isl in islands(bm, uvl):
            wa = sum(world_face_area(f, mw) for f in isl)
            ua = sum(uv_face_area(f, uvl) for f in isl)
            if wa < 1e-10 or ua < 1e-14:
                continue
            w = w_obj
            seen = True
            if cfg.get('shrink_hidden'):
                # a big island is tested on at most ~400 of its faces, spread over it
                fs = list(isl)
                if len(fs) > 400:
                    fs = fs[::len(fs) // 400 + 1]
                fa = [world_face_area(f, mw) for f in fs]
                sa = sum(a for f, a in zip(fs, fa) if vis.face_seen(f, mw, nmat))
                frac = sa / max(sum(fa), 1e-12)
                seen = frac > 0
                if not seen:
                    w *= HIDDEN_SHRINK; nshrunk += 1
                elif frac < PARTLY_SEEN[0]:
                    w *= PARTLY_SEEN[1]; nshrunk += 1
            if seen:
                seen_faces[o.name].update(f.index for f in isl)
            down = 0.0
            if cfg.get('down_shrink'):
                for f in isl:
                    n = (nmat @ f.normal).normalized()
                    down += world_face_area(f, mw) * (1 if n.z < -0.7 else -1)
                if down > 0:
                    w *= cfg['down_shrink']; nshrunk += 1
            s = math.sqrt(wa / ua) * w
            loops = [l for f in isl for l in f.loops]
            uv = np.array([tuple(l[uvl].uv) for l in loops], dtype=np.float64) * s
            # rotate to the minimum-area bounding box (ABF/smart islands come out at arbitrary angles)
            try:
                hull = geometry.convex_hull_2d([Vector(p) for p in uv])
                ang = geometry.box_fit_2d([Vector(uv[i]) for i in hull])
            except Exception:
                ang = 0.0
            c, si = math.cos(ang), math.sin(ang)
            uv = uv @ np.array([[c, si], [-si, c]])
            uv -= uv.min(axis=0)
            isl_out.append(dict(obj=o, bm=bm, uvl=uvl, loops=loops, uv=uv, w=float(uv[:, 0].max()), h=float(uv[:, 1].max())))
        stats[o.name] = nshrunk
    return stats, seen_faces


def skyline_pack(rects, s, m):
    """place rects (w,h) scaled by s plus margin m into the unit square; 90 deg rotation allowed.
    returns [(x, y, rotated)] or None."""
    order = sorted(range(len(rects)), key=lambda i: -max(rects[i]) * s)
    sky = [[0.0, 0.0, 1.0]]  # x, y, width
    out = [None] * len(rects)
    for i in order:
        w0, h0 = rects[i][0] * s + m, rects[i][1] * s + m
        best = None
        for rot, (rw, rh) in ((False, (w0, h0)), (True, (h0, w0))):
            if rw > 1 + 1e-9 or rh > 1 + 1e-9:
                continue
            for j in range(len(sky)):
                x = sky[j][0]
                if x + rw > 1 + 1e-9:
                    break
                y = 0.0; wl = rw; k = j
                while wl > 1e-12 and k < len(sky):
                    y = max(y, sky[k][1]); wl -= sky[k][2]; k += 1
                if y + rh > 1 + 1e-9:
                    continue
                waste = 0.0; wl = rw; k = j
                while wl > 1e-12 and k < len(sky):
                    ww = min(wl, sky[k][2]); waste += (y - sky[k][1]) * ww; wl -= ww; k += 1
                sc = (y + rh, waste, x)
                if best is None or sc < best[0]:
                    best = (sc, j, x, y, rw, rh, rot)
        if best is None:
            return None
        _, j, x, y, rw, rh, rot = best
        out[i] = (x, y, rot)
        # update skyline
        new = [x, y + rh, rw]
        nsky = sky[:j]
        k = j; right = x + rw
        while k < len(sky) and sky[k][0] + sky[k][2] <= right + 1e-12:
            k += 1
        nsky.append(new)
        if k < len(sky):
            seg = sky[k]
            if seg[0] < right:
                seg = [right, seg[1], seg[0] + seg[2] - right]
            nsky.append(seg); nsky.extend(sky[k + 1:])
        # merge equal heights
        merged = []
        for seg in nsky:
            if seg[2] <= 1e-12:
                continue
            if merged and abs(merged[-1][1] - seg[1]) < 1e-12:
                merged[-1][2] += seg[2]
            else:
                merged.append(list(seg))
        sky = merged
    return out


def maxrects_pack(rects, s, m, order_key='area'):
    """MaxRects, best-short-side-fit, 90 deg turns; same contract as skyline_pack."""
    n = len(rects)
    if order_key == 'area':
        order = sorted(range(n), key=lambda i: -(rects[i][0] * rects[i][1]))
    else:
        order = sorted(range(n), key=lambda i: -max(rects[i]))
    free = np.array([[0.0, 0.0, 1.0, 1.0]])
    out = [None] * n
    eps = 1e-12
    for i in order:
        w0, h0 = rects[i][0] * s + m, rects[i][1] * s + m
        best = None
        for rot, (rw, rh) in ((False, (w0, h0)), (True, (h0, w0))):
            dw = free[:, 2] - rw; dh = free[:, 3] - rh
            fit = (dw >= -eps) & (dh >= -eps)
            if not fit.any():
                continue
            short = np.where(fit, np.minimum(dw, dh), np.inf)
            long_ = np.where(fit, np.maximum(dw, dh), np.inf)
            k = int(np.lexsort((long_, short))[0])
            sc = (short[k], long_[k])
            if best is None or sc < best[0]:
                best = (sc, k, rot, rw, rh)
        if best is None:
            return None
        _, k, rot, rw, rh = best
        x, y = free[k, 0], free[k, 1]
        out[i] = (float(x), float(y), rot)
        fx, fy, fw, fh = free[:, 0], free[:, 1], free[:, 2], free[:, 3]
        inter = (x < fx + fw - eps) & (x + rw > fx + eps) & (y < fy + fh - eps) & (y + rh > fy + eps)
        keep = free[~inter]
        new = []
        for a, b, c, d in free[inter]:
            if x > a + eps:
                new.append((a, b, x - a, d))
            if x + rw < a + c - eps:
                new.append((x + rw, b, a + c - x - rw, d))
            if y > b + eps:
                new.append((a, b, c, y - b))
            if y + rh < b + d - eps:
                new.append((a, y + rh, c, b + d - y - rh))
        if new:
            N = np.array(new)
            # drop new free rects contained in a kept one or in another new one
            def contained(A, B, strict_self=False):
                ax0, ay0 = A[:, None, 0], A[:, None, 1]
                ax1, ay1 = ax0 + A[:, None, 2], ay0 + A[:, None, 3]
                bx0, by0 = B[None, :, 0], B[None, :, 1]
                bx1, by1 = bx0 + B[None, :, 2], by0 + B[None, :, 3]
                c = (bx0 <= ax0 + eps) & (by0 <= ay0 + eps) & (bx1 >= ax1 - eps) & (by1 >= ay1 - eps)
                if strict_self:
                    np.fill_diagonal(c, False)
                    # identical rects: keep the first one only
                    same = c & c.T
                    c &= ~(same & (np.arange(len(A))[:, None] < np.arange(len(A))[None, :]))
                return c.any(axis=1)
            drop = contained(N, N, strict_self=True)
            if len(keep):
                drop |= contained(N, keep)
            N = N[~drop]
            free = np.concatenate([keep, N]) if len(keep) else N
        else:
            free = keep
    return out


def best_pack(rects, m, n_max_maxrects=1500):
    """binary-search the largest scale for each packer variant; returns (scale, placements, packer name)"""
    variants = [('skyline', lambda r, s: skyline_pack(r, s, m))]
    if len(rects) <= n_max_maxrects:
        variants += [('maxrects-area', lambda r, s: maxrects_pack(r, s, m, 'area')),
                     ('maxrects-side', lambda r, s: maxrects_pack(r, s, m, 'side'))]
    best = (0.0, None, None)
    for name, fn in variants:
        lo, hi = 0.0, 1.0 / max(max(r) for r in rects)
        got = None
        for _ in range(20):
            mid = (lo + hi) / 2
            p = fn(rects, mid)
            if p is None:
                hi = mid
            else:
                lo, got = mid, p
        log('  packer', name, 'scale', round(lo, 5))
        if got is not None and lo > best[0]:
            best = (lo, got, name)
    return best


def pack_atlas(isl, res):
    m = MARGIN_UV_PX / res
    rects = [(d['w'], d['h']) for d in isl]
    s, best, packer = best_pack(rects, m)
    for d, (x, y, rot) in zip(isl, best):
        uv = d['uv'] * s
        if rot:
            uv = np.stack([uv[:, 1], d['w'] * s - uv[:, 0]], axis=1)
        uv += np.array([x + m / 2, y + m / 2])
        uvl = d['uvl']
        for l, p in zip(d['loops'], uv):
            l[uvl].uv = (float(p[0]), float(p[1]))
    for bm_me in {(id(d['bm']), d['obj'].data) for d in isl}:
        bmesh.update_edit_mesh(bm_me[1])
    return s, packer


def optimize_geometry(o):
    """web clean-up BEFORE the lightmap UV exists, so baked mesh == exported mesh: weld (1e-5 m) +
    limited dissolve (0.5 deg) delimited by UV (the existing UV0 is the active layer), seams, sharp,
    material and normal. Objects with custom split normals are left untouched (weld/dissolve would
    change their shading)."""
    me = o.data
    before = tri_count(o)
    note = ''
    if me.has_custom_normals and o.name in WELD_DESPITE_NORMALS:
        select_only([o])
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        note = '; custom normals cleared, sharp edges > 30 deg marked'
    if me.has_custom_normals:
        return dict(tris_before_opt=before, optimized='skipped (custom normals)')
    if len(me.uv_layers):
        me.uv_layers.active = me.uv_layers[0]
    select_only([o])
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.dissolve_limited(angle_limit=math.radians(0.5), use_dissolve_boundaries=False,
                                  delimit={'UV', 'SEAM', 'SHARP', 'MATERIAL', 'NORMAL'})
    if note:
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(30))
        bpy.ops.mesh.mark_sharp()
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.faces_shade_smooth()
    bpy.ops.object.mode_set(mode='OBJECT')
    return dict(tris_before_opt=before, optimized='weld 1e-5 + limited dissolve 0.5 deg (UV/seam/sharp/material/normal)' + note)


def triangulate(o):
    """Triangulate every quad and n-gon once the lightmap UV is packed, so the bake and the GLB are the same
    triangles (a guard: a concave n-gon or a non-planar quad may otherwise be split two ways). The loop
    UVs carry over unchanged; the exporter would triangulate anyway, so the triangle count is the same."""
    me = o.data
    bm = bmesh.new(); bm.from_mesh(me)
    faces = [f for f in bm.faces if len(f.verts) > 3]
    n = len(faces)
    if faces:
        bmesh.ops.triangulate(bm, faces=faces, quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.to_mesh(me); me.update()
    bm.free()
    return n


def tile_cut(o, tile):
    """bisect the edit mesh along world X/Y/Z so no piece is longer than TILE; cut edges become seams."""
    me = o.data
    bm = bmesh.from_edit_mesh(me)
    mw = o.matrix_world
    M = mw.to_3x3()
    inv = mw.inverted()
    ws = [mw @ v.co for v in bm.verts]
    ncut = 0
    for ax in range(3):
        lo = min(p[ax] for p in ws); hi = max(p[ax] for p in ws)
        ext = hi - lo
        if ext <= tile * 1.07:
            continue
        n = math.ceil(ext / tile)
        nw = Vector((0, 0, 0)); nw[ax] = 1.0
        nl = (M.transposed() @ nw).normalized()
        for k in range(1, n):
            cw = Vector((0, 0, 0)); cw[ax] = lo + ext * k / n
            res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                         plane_co=inv @ cw, plane_no=nl, dist=1e-5)
            for e in res['geom_cut']:
                if isinstance(e, bmesh.types.BMEdge):
                    e.seam = True
            ncut += 1
    bmesh.update_edit_mesh(me)
    return ncut


def density_report(objs, res, seen=None):
    out = {}
    cov = 0.0
    for o in objs:
        bm = bmesh.new(); bm.from_mesh(o.data)
        uvl = bm.loops.layers.uv[LM_UV]
        fa = np.array([world_face_area(f, o.matrix_world) for f in bm.faces])
        fu = np.array([uv_face_area(f, uvl) for f in bm.faces])
        bm.free()
        wa, ua = float(fa.sum()), float(fu.sum())
        cov += ua
        d = np.sqrt(fu * res * res / np.maximum(fa, 1e-12))

        def wmedian(sel):
            if not sel.any():
                return 0.0
            dd, aa = d[sel], fa[sel]
            order = np.argsort(dd); cw = np.cumsum(aa[order])
            return float(dd[order][np.searchsorted(cw, cw[-1] * 0.5)])
        # 'median' / 'avg' include the shrunk never-seen faces; 'seen_*' are the faces a visitor can see
        r = dict(world_area_m2=round(wa, 4), uv_area=round(ua, 5),
                 avg_px_per_m=round(math.sqrt(ua * res * res / wa), 1) if wa > 0 else 0,
                 median_px_per_m=round(wmedian(fa > 0), 1), max_px_per_m=round(float(np.percentile(d, 99)), 1))
        if seen is not None:
            sel = np.zeros(len(fa), bool)
            sel[list(seen.get(o.name, ()))] = True
            sel &= fa > 1e-9
            r.update(seen_area_m2=round(float(fa[sel].sum()), 4), seen_median_px_per_m=round(wmedian(sel), 1),
                     seen_p5_px_per_m=round(float(np.percentile(d[sel], 5)), 1) if sel.any() else 0)
        out[o.name] = r
    return out, cov


def prepare_cloth(o):
    """Apply the curtain's solidify with its shells marked (vertex groups lm_shell / lm_rim), and drop its
    subdivision: the lightmap is baked on exactly the mesh that is exported (the 1024 bake lit the
    subdivided surface but shipped the cage). Returns notes for the manifest."""
    notes = []
    for md in list(o.modifiers):
        if md.type == 'SOLIDIFY':
            for g in ('lm_shell', 'lm_rim'):
                if g not in o.vertex_groups:
                    o.vertex_groups.new(name=g)
            md.shell_vertex_group = 'lm_shell'
            md.rim_vertex_group = 'lm_rim'
            select_only([o])
            bpy.ops.object.modifier_apply(modifier=md.name)
            notes.append(f'{o.name}: solidify applied (shells marked)')
        elif md.type == 'SUBSURF':
            o.modifiers.remove(md)
            notes.append(f'{o.name}: subdivision removed, baked and shipped as its {len(o.data.polygons)}-face cage')
    return notes


def cloth_seams(o):
    """Seams between the back shell (all verts in lm_shell) and the rest (front + rim), so the front and
    its rim unwrap as one island and the back as another. Returns the number of seam edges (0 = no shells
    found; the caller falls back to sharp-edge seams)."""
    g = o.vertex_groups.get('lm_shell')
    if g is None:
        return 0
    me = o.data
    bm = bmesh.from_edit_mesh(me)
    dl = bm.verts.layers.deform.active
    if dl is None:
        return 0
    gi = g.index
    bm.faces.ensure_lookup_table(); bm.faces.index_update()
    back = {f.index: all(gi in v[dl] and v[dl][gi] > 0.5 for v in f.verts) for f in bm.faces}
    nb = sum(back.values())
    n = 0
    if 0 < nb < len(bm.faces):
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) == 2 and back[lf[0].index] != back[lf[1].index]:
                e.seam = True; n += 1
    bmesh.update_edit_mesh(me)
    log(o.name, 'cloth shells:', nb, 'back faces of', len(bm.faces), ';', n, 'seam edges')
    return n


def stage_prepare(opt, man):
    os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
    t0 = time.time()
    log('source', SRC)
    shutil.copy2(SRC, COPY)
    src_hash = hashlib.sha1(open(SRC, 'rb').read()).hexdigest()[:12]
    open_copy()
    sc = bpy.context.scene
    edits = bake_scene_edits(sc)
    # room interior bounds (which cameras count as eye points)
    fl, ce = bpy.data.objects['rs_floor'], bpy.data.objects['rs_ceiling']
    pts = [fl.matrix_world @ Vector(c) for c in fl.bound_box] + [ce.matrix_world @ Vector(c) for c in ce.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    tool = sc.tool_settings
    tool.use_uv_select_sync = True
    all_objs = [bpy.data.objects[n] for cfg in ATLASES.values() for n in cfg['objects']]
    for o in all_objs:
        unhide(o)
        assert o.visible_get(), o.name
    # modifiers first: the visibility BVH and the bake must see the final meshes
    for o in all_objs:
        if o.name in CLOTH_UNWRAP:
            edits += prepare_cloth(o)
        else:
            for md in list(o.modifiers):
                if md.type == 'SOLIDIFY':
                    select_only([o])
                    bpy.ops.object.modifier_apply(modifier=md.name)
                    edits.append(f'{o.name}: solidify applied')
                elif md.type == 'SUBSURF':
                    md.uv_smooth = 'NONE'
    log('scene edits', edits)
    vis = Visibility(sc, all_objs, (lo, hi))
    atl_out = {}
    for name, cfg in ATLASES.items():
        res = ATLASES[name]['res']
        objs = [bpy.data.objects[n] for n in cfg['objects']]
        info = {}
        for o in objs:
            info[o.name] = optimize_geometry(o)
        for o in objs:
            me = o.data
            if LM_UV in me.uv_layers:
                me.uv_layers.remove(me.uv_layers[LM_UV])
            first_added = False
            if len(me.uv_layers) == 0:
                # placeholder so the lightmap lands on TEXCOORD_1; all zeros == shading of a mesh without UVs
                zero_uv(me, 'UVMap'); first_added = True
            render_uv = me.uv_layers[0].name
            lm = me.uv_layers.new(name=LM_UV)
            me.uv_layers.active = lm
            for u in me.uv_layers:
                u.active_render = (u.name == render_uv)
            info[o.name].update(uv0=render_uv, uv0_placeholder_zero=first_added)
        t = time.time()
        nsplit = {}
        for o in objs:
            select_only([o])
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.reveal()
            bpy.ops.mesh.select_all(action='SELECT')
            if o.name in CLOTH_UNWRAP:
                bpy.ops.mesh.mark_seam(clear=True)
                nseam = cloth_seams(o)
                if not nseam:
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(SHARP_SEAM_DEG_OBJ.get(o.name, SHARP_SEAM_DEG)))
                    bpy.ops.mesh.mark_seam(clear=False)
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
                info[o.name].update(unwrap='cloth shells+angle_based' if nseam else 'sharp seams+angle_based', seam_edges=nseam)
            elif o.name in SEAM_UNWRAP or o.name in TRIM_UNWRAP:
                ncut = tile_cut(o, TRIM_TILE if o.name in TRIM_UNWRAP else TILE)
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(SHARP_SEAM_DEG_OBJ.get(o.name, SHARP_SEAM_DEG)))
                bpy.ops.mesh.mark_seam(clear=False)
                if o.name in RUN_SPLIT:
                    info[o.name].update(run_seam_edges=run_seams(o))
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
                info[o.name].update(unwrap='seams+angle_based', tile_cuts=ncut)
            else:
                bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, area_weight=0.0,
                                         correct_aspect=True, scale_to_bounds=False)
                info[o.name].update(unwrap='smart_project')
            if (o.name in SEAM_UNWRAP or o.name in TRIM_UNWRAP) and o.name not in RUN_SPLIT:   # not smart-projected parts: splitting
                k = split_poor_islands(o)                          # those per face only fragments them
                if k:
                    nsplit[o.name] = k
                    info[o.name].update(faces_split_from_poor_islands=k)
            bpy.ops.object.mode_set(mode='OBJECT')
        select_only(objs)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        isl = []
        tv = time.time(); c0 = vis.casts
        shr, seen = normalize_islands(objs, cfg, vis, isl)
        log(name, 'visibility', round(time.time() - tv, 1), 's,', vis.casts - c0, 'rays')
        tp = time.time()
        _, packer = pack_atlas(isl, res)
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in objs:   # after the unwrap: the loop UVs carry over to the triangles
            info[o.name]['triangulated_faces'] = triangulate(o)
        bpy.ops.object.mode_set(mode='EDIT')
        log(name, 'poor islands split per face:', nsplit)
        log(name, len(isl), 'islands packed in', round(time.time() - tp, 1), 's by', packer)
        bpy.ops.object.mode_set(mode='OBJECT')
        dens, cov = density_report(objs, res, seen if cfg.get('shrink_hidden') else None)
        for o in objs:
            info[o.name].update(dens[o.name], tris=tri_count(o), islands_shrunk=shr[o.name],
                                weight=cfg['weights'].get(o.name, 1.0))
        atl_out[name] = dict(resolution=res, objects=info, uv_coverage=round(cov, 3),
                             uv_margin_px=MARGIN_UV_PX, islands=len(isl),
                             packer=f'{packer} (best of skyline / MaxRects), islands rotated to min-area box, 90 deg turns',
                             islands_split_per_face=nsplit, uv_seconds=round(time.time() - t, 1))
        log(name, 'coverage', round(cov, 3), {k: (v['median_px_per_m'], v.get('seen_median_px_per_m'), v['max_px_per_m'])
                                               for k, v in dens.items()})
    safe_save()
    man.update(source=dict(file='blender/scene/room.blend', sha1_12=src_hash, copy='blender/bake/sunset/room_bake.blend'),
               bake_only_edits=edits, uv_layer=LM_UV, uv_channel=1, gltf_attribute='TEXCOORD_1',
               visibility=dict(eyes=len(vis.eyes), grid=VIEW_GRID, hidden_shrink=HIDDEN_SHRINK,
                               rule='island keeps full density if any face is seen (front side, unoccluded by baked '
                                    'meshes) from a grid point or camera inside the room'),
               excluded=EXCLUDED_NOTES, atlases=atl_out, prepare_seconds=round(time.time() - t0, 1))
    man.update(light_params(sc))
    save_manifest(man)


# ---------------------------------------------------------------------------------------------
# bake
# ---------------------------------------------------------------------------------------------
def ensure_bake_node(mat):
    nt = mat.node_tree
    n = nt.nodes.get(BAKE_NODE)
    if not n:
        n = nt.nodes.new('ShaderNodeTexImage'); n.name = BAKE_NODE; n.label = BAKE_NODE
        n.location = (-1200, -600)
    return n


def exr_settings(ims, depth='16'):
    ims.file_format = 'OPEN_EXR'
    ims.color_mode = 'RGB'
    ims.color_depth = depth
    ims.exr_codec = 'ZIP'


def denoise(img, res, out_path):
    """OIDN via the compositor (Denoise node, HDR) on a throwaway scene -> linear half EXR."""
    dsc = bpy.data.scenes.new('LM_denoise')
    dsc.render.engine = 'BLENDER_WORKBENCH'
    dsc.render.resolution_x = dsc.render.resolution_y = res
    dsc.render.resolution_percentage = 100
    dsc.view_settings.view_transform = 'Standard'
    dsc.view_settings.look = 'None'
    dsc.view_settings.exposure = 0
    cam = bpy.data.objects.new('LM_denoise_cam', bpy.data.cameras.new('LM_denoise_cam'))
    dsc.collection.objects.link(cam); dsc.camera = cam
    ng = bpy.data.node_groups.new('LM_denoise_tree', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    ni = ng.nodes.new('CompositorNodeImage'); ni.image = img
    nd = ng.nodes.new('CompositorNodeDenoise')
    for s in nd.inputs:
        if s.name == 'HDR':
            s.default_value = True
        elif s.name in ('Prefilter', 'Quality'):
            for v in (('ACCURATE', 'Accurate') if s.name == 'Prefilter' else ('HIGH', 'High')):
                try:
                    s.default_value = v; break
                except Exception:
                    pass
            log('denoise', s.name, getattr(s, 'default_value', None))
    no = ng.nodes.new('NodeGroupOutput')
    ng.links.new(ni.outputs['Image'], nd.inputs['Image'])
    ng.links.new(nd.outputs['Image'], no.inputs[0])
    dsc.compositing_node_group = ng
    dsc.render.use_compositing = True
    exr_settings(dsc.render.image_settings)
    t = time.time()
    bpy.ops.render.render(scene=dsc.name)
    rr = bpy.data.images['Render Result']
    rr.save_render(out_path, scene=dsc)
    log('denoised', out_path, round(time.time() - t, 1), 's')
    bpy.data.scenes.remove(dsc)
    bpy.data.node_groups.remove(ng)
    bpy.data.objects.remove(cam)


def img_array(img):
    a = np.empty(img.size[0] * img.size[1] * img.channels, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], img.channels)


def png_bytes(u8, path):
    """u8: (h, w, c) uint8, TOP row first. Plain zlib PNG writer (no colour management, no alpha
    premultiplication), best of the None/Sub/Up filters, zlib level 9."""
    import zlib
    h, w, c = u8.shape
    a = u8.astype(np.int16)
    sub = a.copy(); sub[:, c:] = (a[:, c:] - a[:, :-c]) % 256
    up = a.copy(); up[1:] = (a[1:] - a[:-1]) % 256
    best = None
    for ftype, data in ((0, a), (1, sub), (2, up)):
        raw = np.concatenate([np.full((h, 1), ftype, np.uint8), data.astype(np.uint8).reshape(h, w * c)], axis=1)
        z = zlib.compress(raw.tobytes(), 9)
        if best is None or len(z) < len(best):
            best = z

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    ct = {1: 0, 3: 2, 4: 6}[c]
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, ct, 0, 0, 0))
                + chunk(b'IDAT', best) + chunk(b'IEND', b''))
    return os.path.getsize(path)


def write_png(arr_rgb, path, size=None):
    """arr_rgb: bottom-up (Blender order) display-referred 0..1 float -> 8-bit RGB PNG."""
    u8 = np.round(np.clip(arr_rgb[::-1, :, :3], 0, 1) * 255).astype(np.uint8)
    return png_bytes(u8, path)


def rgbm_png(a_lin, path):
    """web lightmap: RGBM, 8-bit RGBA PNG of sqrt(L).  decode: L = (rgb * a * R)^2, R = range of sqrt(L).
    R is per atlas: sqrt of the 99.95th percentile of max(rgb), so rare hot texels clip rather than
    crushing the precision of everything else. Linear data: load with colorSpace NoColorSpace, no
    premultiplied alpha. Rows top-first like the EXR."""
    s = np.sqrt(np.clip(a_lin[..., :3], 0, None))
    mx = s.max(axis=2)
    nz = mx[mx > 1e-6]
    R = float(np.percentile(nz, 99.95)) if nz.size else 1.0
    R = math.ceil(R * 100) / 100
    m = np.clip(np.ceil(mx / R * 255) / 255, 1 / 255, 1)
    rgb = np.clip(s / (m[..., None] * R), 0, 1)
    u8 = np.concatenate([np.round(rgb * 255), np.round(m * 255)[..., None]], axis=2).astype(np.uint8)
    size = png_bytes(u8[::-1], path)
    # decode error check (linear, relative to the atlas mean)
    d = (u8[..., :3] / 255 * (u8[..., 3:] / 255) * R) ** 2
    err = float(np.abs(d - np.clip(a_lin[..., :3], 0, R * R)).mean() / max(a_lin[..., :3].mean(), 1e-9))
    clip = float((mx > R).mean())
    return dict(range_sqrt=R, linear_max=round(R * R, 4), bytes=size, mean_rel_err=round(err, 4),
                clipped_fraction=round(clip, 5))


def preview_png(exr_path, png_path, size=512):
    im = bpy.data.images.load(exr_path, check_existing=False)
    a = img_array(im)[..., :3]
    bpy.data.images.remove(im)
    h = a.shape[0]
    f = max(1, h // size)
    a = a[:h // f * f, :h // f * f].reshape(h // f, f, h // f, f, 3).mean(axis=(1, 3))
    lum = a @ np.array([0.2126, 0.7152, 0.0722])
    nz = lum[lum > 1e-6]
    p = float(np.percentile(nz, 99)) if nz.size else 1.0
    x = a / max(p, 1e-6)
    x = x / (1 + x) * 2  # soft shoulder so p99 -> 1
    srgb = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(np.clip(x, 0, None), 1 / 2.4) - 0.055)
    write_png(srgb, png_path, size)
    return p


def uv_island_labels(objs, res):
    """(res, res) int32, Blender row order (row 0 = v 0): for every texel whose CENTRE lies inside a
    lightmap-UV triangle of one of objs (evaluated meshes, as Cycles bakes them), the id of its UV island
    (triangles joined through shared UV vertices); -1 elsewhere (gutters)."""
    lab = np.full((res, res), -1, np.int32)
    dg = bpy.context.evaluated_depsgraph_get()
    base = 0
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        lt = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get('loops', lt)
        uv = np.empty(len(me.loops) * 2, np.float32); me.uv_layers[LM_UV].data.foreach_get('uv', uv)
        ev.to_mesh_clear()
        uvt = uv.reshape(-1, 2)[lt.reshape(-1, 3)].astype(np.float64)              # (nt, 3, 2)
        # islands: union triangles that share a UV vertex position
        key = np.round(uvt.reshape(-1, 2) * (1 << 22)).astype(np.int64)
        _, vid = np.unique(key[:, 0] * (1 << 24) + key[:, 1], return_inverse=True)
        vid = vid.reshape(-1, 3)
        parent = list(range(nt))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        first = {}
        for k in range(nt):
            for v in vid[k]:
                v = int(v)
                if v in first:
                    r1, r2 = find(k), find(first[v])
                    if r1 != r2:
                        parent[r1] = r2
                else:
                    first[v] = k
        roots = np.array([find(k) for k in range(nt)])
        _, tri_isl = np.unique(roots, return_inverse=True)
        T = uvt * res - 0.5   # texel centres at integers
        lo = np.clip(np.ceil(T.min(1) - 1e-9).astype(np.int64), 0, res - 1)
        hi = np.clip(np.floor(T.max(1) + 1e-9).astype(np.int64), 0, res - 1)
        for k in range(nt):
            (x0, y0), (x1, y1) = lo[k], hi[k]
            if x1 < x0 or y1 < y0:
                continue
            a, b, c = T[k]
            area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(area) < 1e-12:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            sgn = 1.0 if area > 0 else -1.0
            e = -1e-7
            w0 = sgn * ((b[0] - X) * (c[1] - Y) - (b[1] - Y) * (c[0] - X))
            w1 = sgn * ((c[0] - X) * (a[1] - Y) - (c[1] - Y) * (a[0] - X))
            w2 = sgn * ((a[0] - X) * (b[1] - Y) - (a[1] - Y) * (b[0] - X))
            inside = (w0 >= e) & (w1 >= e) & (w2 >= e)
            sub = lab[y0:y1 + 1, x0:x1 + 1]
            sub[inside] = base + tri_isl[k]
        base += int(tri_isl.max()) + 1 if nt else 0
    return lab


def _shifts(h, w):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                yield ((slice(max(dy, 0), h + min(dy, 0)), slice(max(dx, 0), w + min(dx, 0))),
                       (slice(max(-dy, 0), h + min(-dy, 0)), slice(max(-dx, 0), w + min(-dx, 0))))


def grow_labels(labels, iters):
    """Give gutter texels (-1) the label of the nearest island, ring by ring."""
    lab = labels.copy()
    h, w = lab.shape
    for _ in range(iters):
        empty = lab < 0
        if not empty.any():
            break
        for src, dst in _shifts(h, w):
            ld, ls = lab[dst], lab[src]
            m = (ld < 0) & (ls >= 0) & empty[dst]
            ld[m] = ls[m]
    return lab


def dilate(a, valid, iters, labels=None):
    """Fill texels outside `valid` from valid neighbours, one ring per iteration (mean of the already
    filled 8-neighbours). With `labels` (uv_island_labels), every texel only takes from texels of its own
    island, gutter texels counting as the nearest island's, so values never cross from one island into
    another. Texels still unfilled after `iters` rings keep their input value."""
    out = a.copy()
    filled = valid.copy()
    h, w = valid.shape
    lab = None if labels is None else grow_labels(labels, iters)
    for _ in range(iters):
        if filled.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros((h, w), np.float32)
        for src, dst in _shifts(h, w):
            f = filled[src]
            if lab is not None:
                f = f & (lab[src] == lab[dst])
            acc[dst] += out[src] * f[..., None]
            cnt[dst] += f
        new = (~filled) & (cnt > 0)
        if not new.any():
            break
        out[new] = acc[new] / cnt[new][:, None]
        filled |= new
    return out


def set_pixels(img, a_rgb):
    h, w, _ = a_rgb.shape
    px = np.concatenate([a_rgb.astype(np.float32), np.ones((h, w, 1), np.float32)], axis=2)
    img.pixels.foreach_set(px.ravel())
    img.update()


def save_exr(a_rgb, path, sc, depth='16'):
    """Linear float array (Blender row order) -> OpenEXR via save_render; checked by reading it back."""
    h, w, _ = a_rgb.shape
    img = bpy.data.images.new('LM_save', w, h, alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Linear Rec.709'
    set_pixels(img, a_rgb)
    exr_settings(sc.render.image_settings, depth)
    img.save_render(path, scene=sc)
    bpy.data.images.remove(img)
    chk = bpy.data.images.load(path, check_existing=False)
    b = img_array(chk)[..., :3]
    bpy.data.images.remove(chk)
    err = float(np.abs(b - a_rgb).mean() / max(float(a_rgb.mean()), 1e-9))
    assert err < 2e-3, f'{path}: EXR round trip differs by {err} (colour managed?)'
    return b


def stage_bake(opt, man):
    open_copy()
    sc = bpy.context.scene
    gpu(sc)
    sc.cycles.samples = opt['samples']
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.use_denoising = False
    bk = sc.render.bake
    bk.use_pass_direct = True; bk.use_pass_indirect = True; bk.use_pass_color = False
    bk.margin = BAKE_MARGIN_PX; bk.margin_type = 'ADJACENT_FACES'; bk.use_clear = True; bk.target = 'IMAGE_TEXTURES'
    os.makedirs(TMP, exist_ok=True)
    for name in atlas_list(opt):
        cfg = ATLASES[name]
        res = res_of(name, opt)
        objs = [bpy.data.objects[n] for n in cfg['objects']]
        for o in objs:
            unhide(o)
        iname = 'LM_' + name
        if iname in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[iname])
        img = bpy.data.images.new(iname, res, res, alpha=False, float_buffer=True)
        img.colorspace_settings.name = 'Linear Rec.709'
        img.generated_color = (0, 0, 0, 1)
        mats = {s.material for o in objs for s in o.material_slots if s.material}
        for m in mats:
            n = ensure_bake_node(m)
            n.image = img
            n.interpolation = 'Linear'
            for x in m.node_tree.nodes:
                x.select = False
            n.select = True
            m.node_tree.nodes.active = n
        select_only(objs)
        log('baking', name, res, 'x', res, opt['samples'], 'spp', len(objs), 'objects')
        t = time.time()
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT'}, margin=BAKE_MARGIN_PX,
                            margin_type='ADJACENT_FACES', use_clear=True, target='IMAGE_TEXTURES', uv_layer=LM_UV)
        bake_s = round(time.time() - t, 1)
        log('baked', name, bake_s, 's')
        raw = os.path.join(TMP, f'raw_{name}.exr')
        exr_settings(sc.render.image_settings, '32')
        img.save_render(raw, scene=sc)
        out = os.path.join(OUT, f'lightmap_{name}.exr')
        a_raw = img_array(img)[..., :3].copy()
        # Valid texels: centre inside a UV triangle AND lit. A texel whose surface point is buried in other
        # geometry (a wall face running into the next wall, the ceiling above the crown, the wall behind a
        # baseboard) bakes exactly black; bilinear filtering then pulls a dark line into the visible edge.
        # Buried texels and the gutters are refilled from valid texels of the same island, before the
        # denoise (so OIDN sees no black edges) and again after it (so no denoised cross-talk from a
        # neighbouring island is left in a gutter).
        tm = time.time()
        labels = uv_island_labels(objs, res)
        cov = labels >= 0
        lit = a_raw.max(axis=2) > 1e-6
        valid = cov & lit
        a_pre = dilate(a_raw, valid, DILATE_PX, labels)
        set_pixels(img, a_pre)
        cov_stats = dict(covered_fraction=round(float(cov.mean()), 4),
                         buried_fraction_of_covered=round(float((cov & ~lit).sum() / max(1, cov.sum())), 4),
                         islands=int(labels.max()) + 1, dilate_px=DILATE_PX, mask_seconds=round(time.time() - tm, 1))
        log(name, 'coverage', cov_stats)
        denoise(img, res, out)
        # sanity: denoised file must be linear and match the raw bake's level
        chk = bpy.data.images.load(out, check_existing=False)
        a_dn = img_array(chk)[..., :3]
        bpy.data.images.remove(chk)
        m_raw, m_dn = float(a_pre[valid].mean()), float(a_dn[valid].mean())
        log(name, 'mean raw', m_raw, 'denoised', m_dn, 'max', float(a_dn.max()))
        assert abs(m_dn - m_raw) <= 0.1 * m_raw + 1e-6, 'denoised EXR level differs from raw bake (not linear?)'
        a_dn = save_exr(dilate(a_dn, valid, DILATE_PX, labels), out, sc)
        png = os.path.join(OUT, f'lightmap_{name}_preview.png')
        p99 = preview_png(out, png)
        web = os.path.join(OUT, f'lightmap_{name}.rgbm.png')
        rg = rgbm_png(a_dn, web)
        log(name, 'rgbm', rg)
        # point the bake node at the saved EXR so room_bake.blend references the delivered file
        dn_img = bpy.data.images.load(out, check_existing=True)
        dn_img.colorspace_settings.name = 'Linear Rec.709'
        for m in mats:
            m.node_tree.nodes[BAKE_NODE].image = dn_img
        bpy.data.images.remove(img)
        a = man.setdefault('atlases', {}).setdefault(name, {})
        a.update(image=f'lightmap_{name}.exr', preview=f'lightmap_{name}_preview.png', resolution=res,
                 web=dict(file=f'lightmap_{name}.rgbm.png', encoding='RGBM of sqrt(L), 8-bit RGBA PNG, linear data',
                          decode='L = (rgb * a * range_sqrt)^2', **rg),
                 exr=dict(format='OpenEXR half RGB ZIP, scene-linear Rec.709, Blender/OpenEXR row order (top row first in file)',
                          bytes=os.path.getsize(out)),
                 mean_linear=round(m_dn, 5), max_linear=round(float(a_dn.max()), 3), preview_p99_linear=round(p99, 4),
                 bake_seconds=bake_s, samples=opt['samples'], texels=cov_stats,
                 material_names=sorted(m.name for m in mats))  # `materials` (PBR values): v2_bake_indirect.py
        man['bake_settings'] = dict(engine='CYCLES', device='CUDA GPU only', type='DIFFUSE', passes=['DIRECT', 'INDIRECT'],
                                    color=False, meaning='irradiance-like diffuse lighting L, Blender outgoing diffuse = albedo * L',
                                    samples=opt['samples'], adaptive_sampling=False, margin_px=BAKE_MARGIN_PX,
                                    margin_type='ADJACENT_FACES', denoiser='OIDN (compositor Denoise node, HDR, prefilter Accurate)',
                                    post='gutters and buried (black) texels refilled from valid texels of the same island, '
                                         f'before and after the denoise ({DILATE_PX} px rings)',
                                    max_bounces=sc.cycles.max_bounces, diffuse_bounces=sc.cycles.diffuse_bounces,
                                    glossy_bounces=sc.cycles.glossy_bounces,
                                    sample_clamp_indirect=sc.cycles.sample_clamp_indirect, res_scale=opt['res_scale'])
        save_manifest(man)
    safe_save()


# ---------------------------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------------------------
def glb_json(path):
    with open(path, 'rb') as f:
        data = f.read()
    ln = struct.unpack('<I', data[12:16])[0]
    return json.loads(data[20:20 + ln])


def uv_signature(objs, uv_index_or_name, world=True):
    """set of rounded (world position, uv) for every loop."""
    dg = bpy.context.evaluated_depsgraph_get()
    s = set()
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        uvl = me.uv_layers[uv_index_or_name]
        mw = o.matrix_world
        co = np.empty(len(me.vertices) * 3, dtype=np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
        co = co @ np.array(mw.to_3x3()).T + np.array(mw.translation)
        vi = np.empty(len(me.loops), dtype=np.int32); me.loops.foreach_get('vertex_index', vi)
        uv = np.empty(len(me.loops) * 2, dtype=np.float32); uvl.data.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
        p = np.round(co[vi] * 500).astype(np.int64)
        u = np.round(uv * 4096).astype(np.int64)
        for row in np.concatenate([p, u], axis=1):
            s.add(tuple(row))
        ev.to_mesh_clear()
    return s


def stage_export(opt, man):
    open_copy()
    sc = bpy.context.scene
    fmt = [i.identifier for i in bpy.ops.export_scene.gltf.get_rna_type().properties['export_image_format'].enum_items]
    for name in atlas_list(opt):
        cfg = ATLASES[name]
        objs = [bpy.data.objects[n] for n in cfg['objects']]
        for o in objs:
            unhide(o)
        # export the subsurf cage (UVs are linear under subsurf uv_smooth=NONE, so they stay exact)
        subs = [(o, md, md.show_viewport, md.show_render) for o in objs for md in o.modifiers if md.type == 'SUBSURF']
        for o, md, *_ in subs:
            md.show_viewport = False; md.show_render = False
        # never embed the lightmap: drop the bake node for the export (restored after)
        mats = {s.material for o in objs for s in o.material_slots if s.material}
        saved = {}
        for m in mats:
            n = m.node_tree.nodes.get(BAKE_NODE)
            if n:
                saved[m.name] = n.image
                m.node_tree.nodes.remove(n)
        select_only(objs)
        path = os.path.join(OUT, f'{name}.glb')
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_apply=True,
                                  export_texcoords=True, export_normals=True, export_tangents=False,
                                  export_materials='EXPORT', export_image_format='NONE' if 'NONE' in fmt else fmt[0],
                                  export_animations=False, export_skins=False, export_morph=False,
                                  export_cameras=False, export_lights=False, export_yup=True, export_extras=True)
        src_sig = uv_signature(objs, LM_UV)
        tris_exported = sum(tri_count(o) for o in objs)
        for o, md, v, r in subs:
            md.show_viewport = v; md.show_render = r
        for m in mats:
            if m.name in saved:
                n = ensure_bake_node(m); n.image = saved[m.name]
        j = glb_json(path)
        prims = [p for mesh in j['meshes'] for p in mesh['primitives']]
        has_tc1 = all('TEXCOORD_1' in p['attributes'] for p in prims)
        imgs = len(j.get('images', []))
        # round trip: re-import, compare world position + TEXCOORD_1 per loop
        chk = bpy.data.scenes.new('LM_check')
        win_scene = bpy.context.window.scene if bpy.context.window else None
        before = set(bpy.data.objects)
        with bpy.context.temp_override(scene=chk, view_layer=chk.view_layers[0]):
            bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        imp_sig = uv_signature(new, 1)
        match = len(imp_sig & src_sig) / max(1, len(imp_sig))
        for o in [o for o in bpy.data.objects if o not in before]:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.scenes.remove(chk)
        bpy.data.orphans_purge(do_recursive=True)
        log(name, 'glb', os.path.getsize(path), 'bytes; prims', len(prims), 'TEXCOORD_1 on all', has_tc1,
            'images', imgs, 'uv round-trip match', round(match, 4))
        a = man.setdefault('atlases', {}).setdefault(name, {})
        a.update(glb=f'{name}.glb', glb_bytes=os.path.getsize(path), glb_primitives=len(prims),
                 glb_all_have_TEXCOORD_1=has_tc1, glb_images=imgs, glb_uv_roundtrip_match=round(match, 4),
                 glb_tris=tris_exported,
                 glb_note='world-space nodes, glTF Y-up; TEXCOORD_0 = original UV (all-zero placeholder where the '
                          'object had none), TEXCOORD_1 = UVMap_lightmap; curtains baked and exported as the same '
                          'cage mesh (subdivision removed in prepare)')
        save_manifest(man)
    safe_save()


# ---------------------------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------------------------
def load_png_arr(path):
    im = bpy.data.images.load(path, check_existing=False)
    a = img_array(im).copy()
    bpy.data.images.remove(im)
    return a


def preview_material(mat, lm_img, key):
    """copy of mat where every diffuse-type BSDF becomes Emission(base colour x lightmap)."""
    mp = mat.copy(); mp.name = f'PV_{key}_{mat.name}'
    nt = mp.node_tree
    bn = nt.nodes.get(BAKE_NODE)
    if bn:
        nt.nodes.remove(bn)
    uvn = nt.nodes.new('ShaderNodeUVMap'); uvn.uv_map = LM_UV
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = lm_img; tex.interpolation = 'Linear'; tex.extension = 'EXTEND'
    nt.links.new(uvn.outputs['UV'], tex.inputs['Vector'])
    for n in list(nt.nodes):
        if n.type not in ('BSDF_PRINCIPLED', 'BSDF_DIFFUSE', 'BSDF_TRANSLUCENT', 'BSDF_SHEEN'):
            continue
        cin = n.inputs['Base Color'] if n.type == 'BSDF_PRINCIPLED' else n.inputs['Color']
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        a_in = [s for s in mix.inputs if s.name == 'A' and s.type == 'RGBA'][0]
        b_in = [s for s in mix.inputs if s.name == 'B' and s.type == 'RGBA'][0]
        if cin.links:
            nt.links.new(cin.links[0].from_socket, a_in)
        else:
            a_in.default_value = cin.default_value
        nt.links.new(tex.outputs['Color'], b_in)
        em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 1.0
        nt.links.new([s for s in mix.outputs if s.type == 'RGBA'][0], em.inputs['Color'])
        out_sock = n.outputs[0]
        for l in list(out_sock.links):
            nt.links.new(em.outputs['Emission'], l.to_socket)
        nt.nodes.remove(n)
    return mp


def closeup_cameras(sc):
    """Blender cameras at the CLOSEUPS poses (three (x, y, z) = Blender (x, -z, y)), no roll."""
    out = {}
    for name, (eye, tgt, fov, size) in CLOSEUPS.items():
        e = Vector((eye[0], -eye[2], eye[1])); t = Vector((tgt[0], -tgt[2], tgt[1]))
        cd = bpy.data.cameras.new(name)
        cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(fov); cd.clip_start = 0.05
        o = bpy.data.objects.new(name, cd)
        sc.collection.objects.link(o)
        o.location = e
        o.rotation_euler = (t - e).to_track_quat('-Z', 'Y').to_euler()
        out[name] = size
    return out


def render_to(sc, cam, spp, pct, path, transparent=False, size=None):
    sc.camera = bpy.data.objects[cam]
    sc.cycles.samples = spp
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPTIX'
    base = sc.get('lm_base_res') or (sc.render.resolution_x, sc.render.resolution_y)
    sc['lm_base_res'] = list(base)
    if size:
        sc.render.resolution_x, sc.render.resolution_y = size
        pct = 100
    else:
        sc.render.resolution_x, sc.render.resolution_y = base
    sc.render.resolution_percentage = pct
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA' if transparent else 'RGB'
    sc.render.image_settings.color_depth = '8'
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    return round(time.time() - t, 1)


def stage_verify(opt, man):
    open_copy()
    sc = bpy.context.scene
    gpu(sc)
    times = {}
    ref = {}
    sizes = closeup_cameras(sc)
    cams = CAMS + list(sizes)
    for cam in cams:
        p = os.path.join(TMP, f'ref_{cam}.png')
        times[f'ref_{cam}'] = render_to(sc, cam, opt['ref_spp'], opt['pct'], p, size=sizes.get(cam))
        ref[cam] = p
        log('reference', cam, times[f'ref_{cam}'], 's')
    # preview: baked objects -> emission(albedo x lightmap); everything else holdout; no lights, black world
    baked = {}
    for name in ATLASES:
        exr = os.path.join(OUT, f'lightmap_{name}.exr')
        if not os.path.exists(exr):
            continue
        im = bpy.data.images.load(exr, check_existing=False); im.colorspace_settings.name = 'Linear Rec.709'
        for n in ATLASES[name]['objects']:
            baked[n] = (name, im)
    cache = {}
    for n, (name, im) in baked.items():
        o = bpy.data.objects[n]
        for s in o.material_slots:
            if s.material:
                k = (name, s.material.name)
                if k not in cache:
                    cache[k] = preview_material(s.material, im, name)
                s.material = cache[k]
    for o in sc.objects:
        if o.type == 'LIGHT':
            o.hide_render = True
        elif o.type in ('MESH', 'CURVE', 'FONT', 'META', 'CURVES', 'VOLUME', 'POINTCLOUD') and o.name not in baked:
            o.is_holdout = True
    for nd in sc.world.node_tree.nodes:
        if nd.type == 'BACKGROUND':
            nd.inputs[1].default_value = 0.0
    results = {}
    for cam in cams:
        p = os.path.join(TMP, f'prev_{cam}.png')
        times[f'prev_{cam}'] = render_to(sc, cam, opt['prev_spp'], opt['pct'], p, transparent=True, size=sizes.get(cam))
        r = load_png_arr(ref[cam])[..., :3]
        v = load_png_arr(p)
        alpha = v[..., 3:4]
        right = v[..., :3] * alpha + r * 0.3 * (1 - alpha)
        sep = np.ones((r.shape[0], 6, 3), dtype=np.float32)
        comp = np.concatenate([r, sep, right], axis=1)
        write_png(comp, os.path.join(OUT, f'compare_{cam}.png'), None)
        m = alpha[..., 0] > 0.99
        lr = r @ np.array([0.2126, 0.7152, 0.0722]); lv = v[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
        d = np.abs(lr - lv)[m]
        results[cam] = dict(baked_pixel_fraction=round(float(m.mean()), 3),
                            mean_abs_diff_display_luma=round(float(d.mean()), 4),
                            median_abs_diff_display_luma=round(float(np.median(d)), 4),
                            within_0p05=round(float((d < 0.05).mean()), 3),
                            mean_luma_ref=round(float(lr[m].mean()), 4), mean_luma_baked=round(float(lv[m].mean()), 4))
        log('compare', cam, results[cam])
    man['verify'] = dict(cameras=results, render_seconds=times, ref_spp=opt['ref_spp'], preview_spp=opt['prev_spp'],
                         pct=opt['pct'], closeups={k: dict(three_eye=v[0], three_target=v[1], vfov=v[2], size=v[3])
                                                    for k, v in CLOSEUPS.items()},
                         method='left: full Cycles render of room_bake.blend (sunset, room volume off, robot light 3.5); '
                                'right: baked objects as Emission(albedo x lightmap) with no lights, others holdout '
                                '(shown at 30% of the reference). Metrics over baked pixels, display-referred (AgX) luma 0..1.')
    save_manifest(man)
    # nothing saved: the preview materials live only in this session


def main():
    opt = args()
    os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
    man = {} if opt['stage'] in ('all', 'prepare') else load_manifest()
    stages = ['prepare', 'bake', 'export', 'verify'] if opt['stage'] == 'all' else [opt['stage']]
    for st in stages:
        log('=== stage', st)
        t = time.time()
        globals()['stage_' + st](opt, man)
        man.setdefault('stage_seconds', {})[st] = round(time.time() - t, 1)
        save_manifest(man)
    log('DONE', stages)


if __name__ == '__main__':   # blender --python runs this as __main__; v2_bake_indirect.py imports it
    main()
