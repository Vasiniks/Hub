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

room.blend is only ever READ (shutil.copy). Every save goes to room_bake.blend; the script refuses to
save a file called room.blend. Manifest: blender/bake/sunset/manifest.json (merged per stage).
"""
import bpy, bmesh, sys, os, json, time, math, shutil, struct, hashlib
import numpy as np
from mathutils import Vector, geometry

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, 'blender', 'scene', 'room.blend')
OUT = os.path.join(REPO, 'blender', 'bake', 'sunset')
COPY = os.path.join(OUT, 'room_bake.blend')
TMP = os.path.join(REPO, 'tmp', 'bake_sunset')
MANIFEST = os.path.join(OUT, 'manifest.json')
LM_UV = 'UVMap_lightmap'
BAKE_NODE = 'LM_BAKE'
MARGIN_UV_PX = 4          # gap between islands in the packed lightmap UV (>= 4 px at the web resolutions)
BAKE_MARGIN_PX = 8
ROBOT_LIGHT_AVG = 3.5     # driver 3.5 + 3.5*sin(frame*2pi/96) -> mean 3.5

# ---------------------------------------------------------------------------------------------
# Bake set. Per atlas: resolution, objects, per-object linear texel weight, and whether faces that
# point away from the room interior get shrunk (outer faces of wall slabs, curtain backs, rug
# underside are never seen from inside, so they get 'OUTWARD_SHRINK' of the linear density).
# ---------------------------------------------------------------------------------------------
SHELL = ['rs_floor', 'rs_ceiling', 'rs_wall_back', 'rs_wall_left', 'rs_wall_right', 'rs_wall_window',
         'rs_hallway_stub', 'rs_baseboard', 'rs_crown', 'rs_door_casing', 'rs_door_jamb', 'rs_door_slab',
         'rs_window_apron', 'rs_window_casing', 'rs_window_frame', 'rs_window_jamb', 'rs_window_sash',
         'rs_window_stool', 'rs_wall_patches', 'rs_scuff_backwall', 'rs_scuff_baseboard', 'rs_scuff_floor']
ATLASES = {
    'shell': dict(res=1024, objects=SHELL, shrink_outward=True,
                  weights={'rs_ceiling': 0.6, 'rs_hallway_stub': 0.3, 'rs_window_frame': 0.6, 'rs_window_sash': 0.6}),
    'desk': dict(res=1024, objects=['desk_top_tmp', 'desk_top_tmp_1', 'desk_top_tmp_2', 'desk_top_tmp_3', 'desk_top_tmp_4'],
                 shrink_outward=False, down_shrink=0.5,
                 weights={'desk_top_tmp': 1.0, 'desk_top_tmp_1': 1.0, 'desk_top_tmp_2': 0.55, 'desk_top_tmp_3': 0.55, 'desk_top_tmp_4': 0.4}),
    'furniture': dict(res=512, shrink_outward=False, weights={},
                      objects=['bookrack_board', 'bookrack_bracket_L', 'bookrack_bracket_R', 'bookrack_bookend_L', 'bookrack_bookend_R',
                               'bambu_mini_table_top', 'bambu_mini_table_shelf', 'bambu_mini_table_apron_back',
                               'bambu_mini_table_apron_left', 'bambu_mini_table_apron_right', 'bambu_mini_table_drawer_front',
                               'bambu_mini_table_rail_top', 'bambu_mini_table_rail_bot', 'bambu_mini_table_leg_00',
                               'bambu_mini_table_leg_01', 'bambu_mini_table_leg_10', 'bambu_mini_table_leg_11']),
    'soft': dict(res=512, objects=['curtain_left', 'curtain_right', 'Mesh_4'], shrink_outward=True,
                 weights={'Mesh_4': 1.0}),
}
OUTWARD_SHRINK = 0.12
# Objects unwrapped with seams (sharp edges + tile cuts) + angle-based unwrap instead of smart project.
# Large planar slabs are bisected into tiles <= ~TILE m so the packer can fill a square atlas
# (one 4 m wall/floor island per face packs at < 40 % coverage); the cuts are seams, hidden by the
# ADJACENT_FACES bake margin. Bisect interpolates the existing UV layers, so UV0 is unchanged.
SEAM_UNWRAP = {'rs_floor', 'rs_ceiling', 'rs_wall_back', 'rs_wall_left', 'rs_wall_right', 'rs_wall_window',
               'rs_hallway_stub', 'rs_door_slab', 'desk_top_tmp', 'desk_top_tmp_1',
               'curtain_left', 'curtain_right', 'Mesh_4'}
# trims: rings (casings, jambs) and corner-wrapping strips (baseboard, crown) pack terribly as whole
# islands, so they are cut into short straight pieces
TRIM_UNWRAP = {'rs_baseboard', 'rs_crown', 'rs_door_casing', 'rs_door_jamb', 'rs_window_casing', 'rs_window_jamb',
               'rs_window_apron', 'rs_window_stool', 'rs_window_frame', 'rs_window_sash'}
TILE = 1.4
TRIM_TILE = 0.6
SHARP_SEAM_DEG = 50
SHARP_SEAM_DEG_OBJ = {"curtain_left": 85, "curtain_right": 85}  # only split front / rim / back of the cloth
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


def log(*a):
    print('[bake]', *a, flush=True)


def args():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = dict(stage=a[0] if a else 'all', samples=512, res_scale=1.0, only=None, ref_spp=128, prev_spp=32, pct=50)
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


def normalize_islands(objs, cfg, center, isl_out):
    """Uniform texel density across all objects of the atlas (world-space area incl. parent transforms),
    times per-object weight, with never-seen faces shrunk. Appends island records to isl_out."""
    stats = {}
    for o in objs:
        me = o.data
        bm = bmesh.from_edit_mesh(me)
        bm.faces.ensure_lookup_table(); bm.faces.index_update()
        uvl = bm.loops.layers.uv[LM_UV]
        mw = o.matrix_world
        nmat = mw.to_3x3().inverted().transposed()
        w_obj = cfg['weights'].get(o.name, 1.0)
        nshrunk = 0
        for isl in islands(bm, uvl):
            wa = sum(world_face_area(f, mw) for f in isl)
            ua = sum(uv_face_area(f, uvl) for f in isl)
            if wa < 1e-10 or ua < 1e-14:
                continue
            w = w_obj
            inward = 0.0; down = 0.0
            for f in isl:
                n = (nmat @ f.normal).normalized()
                c = mw @ f.calc_center_median()
                a = world_face_area(f, mw)
                inward += a * (1 if n.dot(center - c) > 0 else -1)
                down += a * (1 if n.z < -0.7 else -1)
            if cfg.get('shrink_outward') and inward < 0:
                w *= OUTWARD_SHRINK; nshrunk += 1
            if cfg.get('down_shrink') and down > 0:
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
    return stats


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


def pack_atlas(isl, res):
    m = MARGIN_UV_PX / res
    rects = [(d['w'], d['h']) for d in isl]
    lo, hi = 0.0, 1.0 / max(max(r) for r in rects)
    best = None
    for _ in range(22):
        mid = (lo + hi) / 2
        p = skyline_pack(rects, mid, m)
        if p is None:
            hi = mid
        else:
            lo, best = mid, p
    s = lo
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
    return s


def optimize_geometry(o):
    """web clean-up BEFORE the lightmap UV exists, so baked mesh == exported mesh: weld (1e-5 m) +
    limited dissolve (0.5 deg) delimited by UV (the existing UV0 is the active layer), seams, sharp,
    material and normal. Objects with custom split normals are left untouched (weld/dissolve would
    change their shading)."""
    me = o.data
    before = tri_count(o)
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
    bpy.ops.object.mode_set(mode='OBJECT')
    return dict(tris_before_opt=before, optimized='weld 1e-5 + limited dissolve 0.5 deg (UV/seam/sharp/material/normal)')


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


def density_report(objs, res):
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
        order = np.argsort(d); cw = np.cumsum(fa[order])
        med = float(d[order][np.searchsorted(cw, cw[-1] * 0.5)]) if wa > 0 else 0
        # 'max' = density of the largest-weight (seen) faces; 'avg' includes shrunk back/outer faces
        out[o.name] = dict(world_area_m2=round(wa, 4), uv_area=round(ua, 5),
                           avg_px_per_m=round(math.sqrt(ua * res * res / wa), 1) if wa > 0 else 0,
                           median_px_per_m=round(med, 1), max_px_per_m=round(float(np.percentile(d, 99)), 1))
    return out, cov


def stage_prepare(opt, man):
    os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
    t0 = time.time()
    shutil.copy2(SRC, COPY)
    src_hash = hashlib.sha1(open(SRC, 'rb').read()).hexdigest()[:12]
    open_copy()
    sc = bpy.context.scene
    edits = bake_scene_edits(sc)
    log('scene edits', edits)
    # room interior centre (for 'outward' faces)
    fl, ce = bpy.data.objects['rs_floor'], bpy.data.objects['rs_ceiling']
    pts = [fl.matrix_world @ Vector(c) for c in fl.bound_box] + [ce.matrix_world @ Vector(c) for c in ce.bound_box]
    center = sum(pts, Vector()) / len(pts)
    log('room centre', tuple(round(x, 3) for x in center))
    tool = sc.tool_settings
    tool.use_uv_select_sync = True
    atl_out = {}
    for name, cfg in ATLASES.items():
        res = ATLASES[name]['res']
        objs = [bpy.data.objects[n] for n in cfg['objects']]
        for o in objs:
            unhide(o)
            assert o.visible_get(), o.name
        # curtains: apply solidify so front/back get their own lightmap space (it mirrors UVs otherwise);
        # subsurf stays live, set to linear UV interpolation so the cage UVs stay exact at export time
        for o in objs:
            for md in list(o.modifiers):
                if md.type == 'SOLIDIFY':
                    select_only([o])
                    bpy.ops.object.modifier_apply(modifier=md.name)
                    log('applied solidify on', o.name)
                elif md.type == 'SUBSURF':
                    md.uv_smooth = 'NONE'
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
        for o in objs:
            select_only([o])
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.reveal()
            bpy.ops.mesh.select_all(action='SELECT')
            if o.name in SEAM_UNWRAP or o.name in TRIM_UNWRAP:
                ncut = tile_cut(o, TRIM_TILE if o.name in TRIM_UNWRAP else TILE)
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(SHARP_SEAM_DEG_OBJ.get(o.name, SHARP_SEAM_DEG)))
                bpy.ops.mesh.mark_seam(clear=False)
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
                info[o.name].update(unwrap='seams+angle_based', tile_cuts=ncut)
            else:
                bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, area_weight=0.0,
                                         correct_aspect=True, scale_to_bounds=False)
                info[o.name].update(unwrap='smart_project')
            bpy.ops.object.mode_set(mode='OBJECT')
        select_only(objs)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        isl = []
        shr = normalize_islands(objs, cfg, center, isl)
        tp = time.time()
        pack_atlas(isl, res)
        log(name, len(isl), 'islands packed in', round(time.time() - tp, 1), 's')
        bpy.ops.object.mode_set(mode='OBJECT')
        dens, cov = density_report(objs, res)
        for o in objs:
            info[o.name].update(dens[o.name], tris=tri_count(o), islands_shrunk=shr[o.name],
                                weight=cfg['weights'].get(o.name, 1.0))
        atl_out[name] = dict(resolution=res, objects=info, uv_coverage=round(cov, 3),
                             uv_margin_px=MARGIN_UV_PX, islands=len(isl),
                             packer='skyline, islands rotated to min-area box, 90 deg turns', uv_seconds=round(time.time() - t, 1))
        log(name, 'coverage', round(cov, 3), {k: (v['median_px_per_m'], v['max_px_per_m']) for k, v in dens.items()})
    safe_save()
    man.update(source=dict(file='blender/scene/room.blend', sha1_12=src_hash, copy='blender/bake/sunset/room_bake.blend'),
               bake_only_edits=edits, uv_layer=LM_UV, uv_channel=1, gltf_attribute='TEXCOORD_1',
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
        denoise(img, res, out)
        # sanity: denoised file must be linear and match the raw bake's level
        a_raw = img_array(img)[..., :3]
        chk = bpy.data.images.load(out, check_existing=False)
        a_dn = img_array(chk)[..., :3]
        bpy.data.images.remove(chk)
        m_raw, m_dn = float(a_raw.mean()), float(a_dn.mean())
        log(name, 'mean raw', m_raw, 'denoised', m_dn, 'max', float(a_dn.max()))
        assert abs(m_dn - m_raw) <= 0.1 * m_raw + 1e-6, 'denoised EXR level differs from raw bake (not linear?)'
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
                 bake_seconds=bake_s, samples=opt['samples'],
                 materials=sorted(m.name for m in mats))
        man['bake_settings'] = dict(engine='CYCLES', device='CUDA GPU only', type='DIFFUSE', passes=['DIRECT', 'INDIRECT'],
                                    color=False, meaning='irradiance-like diffuse lighting L, Blender outgoing diffuse = albedo * L',
                                    samples=opt['samples'], adaptive_sampling=False, margin_px=BAKE_MARGIN_PX,
                                    margin_type='ADJACENT_FACES', denoiser='OIDN (compositor Denoise node, HDR, prefilter Accurate)',
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
                          'object had none), TEXCOORD_1 = UVMap_lightmap; curtains exported as the subsurf cage')
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


def render_to(sc, cam, spp, pct, path, transparent=False):
    sc.camera = bpy.data.objects[cam]
    sc.cycles.samples = spp
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPTIX'
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
    for cam in CAMS:
        p = os.path.join(TMP, f'ref_{cam}.png')
        times[f'ref_{cam}'] = render_to(sc, cam, opt['ref_spp'], opt['pct'], p)
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
    for cam in CAMS:
        p = os.path.join(TMP, f'prev_{cam}.png')
        times[f'prev_{cam}'] = render_to(sc, cam, opt['prev_spp'], opt['pct'], p, transparent=True)
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
                         pct=opt['pct'],
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


main()
