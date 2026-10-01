"""
v2_export_web.py -- turn the room's props into web-ready GLBs.

    blender -b blender/scene/room_public.blend --python blender/scripts/v2_export_web.py -- <collection|all>
        [--dry-run] [--no-bake] [--no-decimate] [--res-scale 0.5] [--outdir ./tmp/props_raw]

Per NEW_* prop collection: assert the licensing gate, decimate to the triangle
budget (UV-preserving collapse, BEFORE the bake), bake procedural node materials
to <=2K textures (base colour / roughness+metallic packed / normal / emit), split
keeper emissives (Robot_rsl_lens, the A1 mini screen face) into their own
primitives, export one GLB in world space + a sidecar JSON.

Read blender/scripts/v2_robot.py for the decimate-via-depsgraph pattern and
blender/scripts/v2_bambu_mini.py for how the scan PBR materials are wired
(image-textured materials export natively and are NOT re-baked).

The script never saves the .blend: everything happens in memory.

Tri budgets (interior total <= 350k; silhouette kept, seen from ~40 cm):
  robot 131k->40k, bambu_mini 119k->35k, pc 155k->40k, electronics 106k->30k,
  medals 88k->12k, telecaster 85k->20k, cables 53k->15k, lorenz 40k->15k,
  speedcube 34k->12k, keyboard 32k->20k, bambu 30k->10k, mouse_mx 23k->12k,
  mouse 19k->10k, bookrack 15k->8k, macbook 15k->10k, lamp 10.5k->8k,
  monitor keep, painting keep, plush_teto keep.
"""
import bpy
import bmesh
import json
import math
import os
import sys
import time
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

# ------------------------------------------------------------------------------------------ options
TARGET = ARGS[0] if ARGS and not ARGS[0].startswith('--') else 'all'
DRY_RUN = '--dry-run' in ARGS
NO_BAKE = '--no-bake' in ARGS
NO_DEC = '--no-decimate' in ARGS
RS = float(ARGS[ARGS.index('--res-scale') + 1]) if '--res-scale' in ARGS else 1.0
OUTDIR = os.path.join(REPO, ARGS[ARGS.index('--outdir') + 1]) if '--outdir' in ARGS \
    else os.path.join(REPO, 'tmp', 'props_raw')
TEXDIR = os.path.join(OUTDIR, 'tex')

BUDGETS = {  # None = keep as-is
    # NOTE: NEW_bambu (full-size A1, 30k) and NEW_mouse (scratch Basilisk, 19k) are
    # fully retired in room_public.blend (hide_render + OLD_replaced, replaced by the
    # A1 mini and the MX Master 3S) -- they are NOT exported. NEW_telecaster exports
    # as the current TeleStand only (the 7 scratch-guitar meshes are retired).
    'robot': 40000, 'bambu_mini': 35000, 'pc': 40000, 'electronics': 30000,
    'medals': 12000, 'telecaster': 20000, 'cables': 15000, 'lorenz': 15000,
    'speedcube': 12000, 'keyboard': 20000, 'mouse_mx': 12000,
    'bookrack': 8000, 'macbook': 10000, 'lamp': 8000,
    'monitor': None, 'painting': None, 'plush_teto': None,
}
RETIRED_WHOLE = ('bambu', 'mouse')
CREATED_IMAGES = []  # bake images freed after each collection (memory)
# medals: the discs carry the owner's geometric FRC relief; ribbons/clasps decimate harder
MEDAL_RATIO = (('disc', 0.30), ('ribbon', 0.25), ('clasp', 0.30))
KEEPER_MATS = {'robot_rsl_amber', 'bambu_mini_screen_lit'}  # own primitives, never merged/decimated
NO_DEC_MATS = KEEPER_MATS | {'lamp_diffuser'}  # objects using ONLY these skip decimation

BLOCKED_COLL_PREFIX = ('NEW_tele_gb', 'NEW_teto', 'NEW_redbull')  # NEW_plush_teto is FINE


def log(*a):
    print('[webprops]', *a, flush=True)


# ------------------------------------------------------------------------------------------ licensing gate
def licensing_gate():
    bad_c = [c.name for c in bpy.data.collections if c.name.startswith(BLOCKED_COLL_PREFIX)
             and c.name != 'NEW_plush_teto' or c.name == 'NEW_plush_teto' and False]    # (explicit: plush stays; the startswith check above would catch NEW_teto* pear only)
    bad_c = [c.name for c in bpy.data.collections
             if c.name.startswith(BLOCKED_COLL_PREFIX) and c.name != 'NEW_plush_teto']
    bad_o = [o.name for o in bpy.data.objects
             if 'emblem18' in o.name or o.name.startswith('pc_gpukit_')]
    log('LICENCE_GATE blocked collections present:', bad_c if bad_c else 'NONE')
    log('LICENCE_GATE blocked objects present:', bad_o if bad_o else 'NONE')
    if bad_c or bad_o:
        log('LICENCE_GATE FAIL: blocked assets present, aborting')
        sys.exit(1)
    log('LICENCE_GATE PASS')


def ntris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def coll_tris(coll):
    return sum(ntris(o.data) for o in coll.all_objects if o.type == 'MESH' and o.data)


# ------------------------------------------------------------------------------------------ material analysis
TEXLIKE = {'TEX_NOISE', 'TEX_VORONOI', 'TEX_WAVE', 'TEX_MUSGRAVE', 'TEX_GRADIENT',
           'TEX_MAGIC', 'TEX_CHECKER', 'TEX_BRICK', 'TEX_POINTDENSITY',
           'ATTRIBUTE', 'GEOMETRY', 'NEW_GEOMETRY', 'OBJECT_INFO', 'VERTEX_COLOR',
           'LAYER_WEIGHT', 'FRESNEL', 'AMBIENT_OCCLUSION', 'BEVEL',
           'TEX_COORD', 'UVMAP'}
CHAN_INPUTS = {'base': ('Base Color',), 'rough': ('Roughness',), 'metal': ('Metallic',),
               'normal': ('Normal',), 'emit': ('Emission Color', 'Emission Strength')}


def upstream_types(node, seen=None):
    seen = seen or set()
    out = set()
    if node in seen:
        return out
    seen.add(node)
    for inp in getattr(node, 'inputs', []):
        for link in inp.links:
            fn = link.from_node
            out.add(fn.type)
            out |= upstream_types(fn, seen)
    return out


def analyse_material(mat):
    """Which channels need a bake (procedural feed) vs export natively."""
    need = set()
    if not mat.use_nodes or not mat.node_tree:
        return need
    bs = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bs:
        return need
    for ch, inpnames in CHAN_INPUTS.items():
        for inpname in inpnames:
            inp = bs.inputs.get(inpname)
            if inp and inp.links:
                ups = upstream_types(inp.links[0].from_node)
                if ups & TEXLIKE - {'TEX_COORD', 'UVMAP', 'TEX_IMAGE'}:
                    need.add(ch)
                    break
                if 'TEX_IMAGE' in ups:
                    # image feed: check the vector; non-UV vectors need a bake to a fresh UV
                    for n in mat.node_tree.nodes:
                        if n.type == 'TEX_IMAGE':
                            v = n.inputs.get('Vector')
                            if v and v.links:
                                vt = v.links[0].from_node.type
                                if vt not in ('UVMAP', 'TEX_COORD'):
                                    need.add(ch)
                                    break
                            else:
                                # unlinked vector on an object with no UVs -> bake
                                need.add(ch)
                                break
                    break
    return need


def emissive_scalar(mat):
    try:
        bs = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        s = bs.inputs.get('Emission Strength')
        c = bs.inputs.get('Emission Color')
        sv = s.default_value if s and not s.links else 0.0
        cv = tuple(c.default_value[:3]) if c and not c.links else (1.0, 1.0, 1.0)
        return (sv, cv) if sv > 0.01 else None
    except (StopIteration, AttributeError):
        return None


# ------------------------------------------------------------------------------------------ mesh ops
def single_user(objs):
    for o in objs:
        if o.type == 'MESH' and o.data and o.data.users > 1:
            o.data = o.data.copy()


def decimate_to(me, ratio):
    """Weld + planar dissolve (frees the collapse floor on CAD plates/extrusions),
    then quadric collapse. Mirrors the v2 part scripts' own reduction order."""
    sc = bpy.context.scene
    o = bpy.data.objects.new('__dec', me)
    sc.collection.objects.link(o)
    mw = o.modifiers.new('WELD', 'WELD')
    mw.merge_threshold = 0.00005
    md = o.modifiers.new('DIS', 'DECIMATE')
    md.decimate_type = 'DISSOLVE'
    md.angle_limit = math.radians(1.0)
    try:
        md.delimit = {'MATERIAL', 'SEAM', 'SHARP', 'UV', 'NORMAL'}
    except TypeError:
        pass
    g = bpy.context.evaluated_depsgraph_get()
    mid = bpy.data.meshes.new_from_object(o.evaluated_get(g))
    o.modifiers.clear()
    o.data = mid
    m = o.modifiers.new('DEC', 'DECIMATE')
    m.decimate_type = 'COLLAPSE'
    m.ratio = max(0.01, min(1.0, ratio))
    m.use_collapse_triangulate = True
    g = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(o.evaluated_get(g))
    bpy.data.objects.remove(o)
    if mid.users == 0:
        bpy.data.meshes.remove(mid)
    return out


def ensure_uv(o):
    me = o.data
    if me.uv_layers:
        return me.uv_layers.active.name, False
    sc = bpy.context.scene
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    sc.view_layers[0].objects.active = o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    return me.uv_layers.active.name, True


def separate_by_material(o, mat_name, new_name):
    """Split polygons using mat_name into their own object. Returns new object or None."""
    idx = next((i for i, s in enumerate(o.material_slots)
                if s.material and s.material.name == mat_name), None)
    if idx is None:
        return None
    sc = bpy.context.scene
    pre = set(sc.objects)
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    sc.view_layers[0].objects.active = o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    o.active_material_index = idx
    bpy.ops.object.material_slot_select()
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    newies = [x for x in sc.objects if x not in pre]
    if not newies:
        return None
    no = newies[0]
    no.name = new_name
    no.data.name = new_name
    return no


# ------------------------------------------------------------------------------------------ baking
def setup_cycles():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False


def bake_image(rep, mat, img, btype, margin=4, pass_filter=None):
    nt = mat.node_tree
    tn = nt.nodes.new('ShaderNodeTexImage')
    tn.image = img
    nt.nodes.active = tn
    sc = bpy.context.scene
    bpy.ops.object.select_all(action='DESELECT')
    rep.select_set(True)
    sc.view_layers[0].objects.active = rep
    kw = dict(type=btype, use_selected_to_active=False, margin=margin, use_clear=True,
              target='IMAGE_TEXTURES', save_mode='INTERNAL')
    if btype == 'NORMAL':
        kw['normal_space'] = 'TANGENT'
    if btype == 'DIFFUSE' and pass_filter:
        kw['pass_filter'] = pass_filter
    bpy.ops.object.bake(**kw)
    bpy.ops.object.select_all(action='DESELECT')
    nt.nodes.remove(tn)


def bake_socket_override(rep, mat, socket_name, img):
    """Bake an arbitrary Principled scalar socket (Metallic/Alpha) via an emission override."""
    nt = mat.node_tree
    bs = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    sock = bs.inputs.get(socket_name)
    if not sock or not sock.links and socket_name == 'Metallic':
        return False  # scalar metallic: no bake needed
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    old_link = out.inputs['Surface'].links[0] if out.inputs['Surface'].links else None
    em = nt.nodes.new('ShaderNodeEmission')
    if sock.links:
        nt.links.new(sock.links[0].from_socket, em.inputs['Color'])
    else:
        v = sock.default_value
        em.inputs['Color'].default_value = (v, v, v, 1) if isinstance(v, float) else v
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    try:
        bake_image(rep, mat, img, 'EMIT')
    finally:
        nt.links.new(old_link.from_socket, out.inputs['Surface']) if old_link else None
        nt.nodes.remove(em)
    return True


def new_image(name, w, h, srgb):
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    CREATED_IMAGES.append(img)
    return img


def obj_area(o):
    vs = np.array([v.co[:] for v in o.data.vertices])
    d = vs.max(0) - vs.min(0)
    return float(d[0] * d[1] + d[1] * d[2] + d[2] * d[0])


def bake_material(mat, rep, uv_name, coll, texdir):
    """Bake needed channels of mat on rep; return (web_material, [files])."""
    need = analyse_material(mat)
    em = emissive_scalar(mat)
    if em and 'emit' in need:
        pass  # textured emission: bake it too
    if not need:
        return mat, []
    area = obj_area(rep)
    r_base = int((1024 if area > 0.02 else 512) * RS)
    r_rough = int(256 * RS)
    r_metal = int(128 * RS)
    r_norm = int(512 * RS)
    r_emit = int(512 * RS)
    safe = ''.join(c if (c.isalnum() or c in '._-') else '_' for c in mat.name)
    files = {}
    bakes = {}
    if 'base' in need:
        img = new_image(f'{coll}_{safe}_base', r_base, r_base, True)
        bake_image(rep, mat, img, 'DIFFUSE', margin=8, pass_filter={'COLOR'})
        p = os.path.join(texdir, f'{safe}_base.png')
        img.filepath_raw = p
        img.file_format = 'PNG'
        img.save()
        files['base'] = p
        bakes['base'] = img
    if 'rough' in need:
        img = new_image(f'{coll}_{safe}_rough', r_rough, r_rough, False)
        bake_image(rep, mat, img, 'ROUGHNESS')
        bakes['rough'] = img
    if 'metal' in need:
        img = new_image(f'{coll}_{safe}_metal', r_metal, r_metal, False)
        if bake_socket_override(rep, mat, 'Metallic', img):
            bakes['metal'] = img
        else:
            bpy.data.images.remove(img)
            need.discard('metal')
    if 'normal' in need:
        img = new_image(f'{coll}_{safe}_normal', r_norm, r_norm, False)
        bake_image(rep, mat, img, 'NORMAL')
        p = os.path.join(texdir, f'{safe}_normal.png')
        img.filepath_raw = p
        img.file_format = 'PNG'
        img.save()
        files['normal'] = p
        bakes['normal'] = img
    if 'emit' in need:
        img = new_image(f'{coll}_{safe}_emit', r_emit, r_emit, True)
        bake_image(rep, mat, img, 'EMIT', margin=8)
        p = os.path.join(texdir, f'{safe}_emit.png')
        img.filepath_raw = p
        img.file_format = 'PNG'
        img.save()
        files['emit'] = p
        bakes['emit'] = img
    # pack rough+metal -> ORM (R=1, G=rough, B=metal) where both exist
    orm_path = None
    if 'rough' in bakes and 'metal' in bakes:
        n = max(bakes['rough'].size[0], bakes['metal'].size[0])
        rq = np.array(bakes['rough'].pixels[:]) .reshape(-1, 4)[:, 0]
        mt = np.array(bakes['metal'].pixels[:]).reshape(-1, 4)[:, 0]
        img = bpy.data.images.new(f'{coll}_{safe}_orm', n, n, alpha=False)
        img.colorspace_settings.name = 'Non-Color'
        arr = np.ones((n * n, 4), dtype=np.float32)
        arr[:, 1] = rq[:n * n]
        arr[:, 2] = mt[:n * n]
        img.pixels.foreach_set(arr.ravel())
        p = os.path.join(texdir, f'{safe}_orm.png')
        img.filepath_raw = p
        img.file_format = 'PNG'
        img.save()
        orm_path = p
        bpy.data.images.remove(img)  # re-loaded below for the material node
        bpy.data.images.remove(bakes['rough'])
        bpy.data.images.remove(bakes['metal'])
        del bakes['rough']
        del bakes['metal']
    elif 'rough' in bakes:
        p = os.path.join(texdir, f'{safe}_rough.png')
        bakes['rough'].filepath_raw = p
        bakes['rough'].file_format = 'PNG'
        bakes['rough'].save()
        files['rough'] = p
    elif 'metal' in bakes:
        p = os.path.join(texdir, f'{safe}_metal.png')
        bakes['metal'].filepath_raw = p
        bakes['metal'].file_format = 'PNG'
        bakes['metal'].save()
        files['metal'] = p
    if orm_path:
        files['orm'] = orm_path
    # rebuild a clean export material
    wm = bpy.data.materials.new(mat.name + '_web')
    wm.use_nodes = True
    N = wm.node_tree.nodes
    L = wm.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    uvn = N.new('ShaderNodeUVMap')
    uvn.uv_map = uv_name
    # copy scalar fallbacks from the original
    try:
        obs = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        for k in ('Metallic', 'Roughness', 'Specular IOR Level'):
            try:
                if k in obs.inputs and not obs.inputs[k].links:
                    bs.inputs[k].default_value = obs.inputs[k].default_value
            except (KeyError, TypeError):
                pass
        if em:
            bs.inputs['Emission Strength'].default_value = em[0]
            bs.inputs['Emission Color'].default_value = (*em[1], 1)
    except StopIteration:
        pass

    def imgnode(baked_img, srgb):
        t = N.new('ShaderNodeTexImage')
        t.image = baked_img
        t.image.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
        L.new(uvn.outputs['UV'], t.inputs['Vector'])
        return t
    if 'base' in bakes:
        L.new(imgnode(bakes['base'], True).outputs['Color'], bs.inputs['Base Color'])
    if 'orm' in files:
        orm_img = bpy.data.images.load(orm_path)
        CREATED_IMAGES.append(orm_img)
        t = imgnode(orm_img, False)
        sep = N.new('ShaderNodeSeparateColor')
        L.new(t.outputs['Color'], sep.inputs['Color'])
        L.new(sep.outputs['Green'], bs.inputs['Roughness'])
        L.new(sep.outputs['Blue'], bs.inputs['Metallic'])
    else:
        if 'rough' in bakes:
            L.new(imgnode(bakes['rough'], False).outputs['Color'], bs.inputs['Roughness'])
        if 'metal' in bakes:
            L.new(imgnode(bakes['metal'], False).outputs['Color'], bs.inputs['Metallic'])
    if 'normal' in bakes:
        nm = N.new('ShaderNodeNormalMap')
        nm.uv_map = uv_name
        L.new(imgnode(bakes['normal'], False).outputs['Color'], nm.inputs['Color'])
        L.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if 'emit' in bakes:
        L.new(imgnode(bakes['emit'], True).outputs['Color'], bs.inputs['Emission Color'])
    return wm, files


# ------------------------------------------------------------------------------------------ per-collection export
def purge_except(short):
    """Drop everything outside the target collection from memory (never saved).
    room_public.blend holds ~1.4 M tris incl. the exterior; bakes SIGBUS under
    system memory pressure unless the working set is cut to the target."""
    keep = 'NEW_' + short if not short.startswith('NEW_') else short
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        if o.users_collection and keep not in [c.name for c in o.users_collection]:
            bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name != keep and c.name != 'Scene Collection':
            try:
                bpy.data.collections.remove(c)
            except RuntimeError:
                pass
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    sc.view_layers[0].update()
    log(f'{keep}: working set after purge: {len(bpy.data.objects)} objects, '
        f'{len(bpy.data.meshes)} meshes, {len(bpy.data.images)} images, '
        f'{len(bpy.data.materials)} materials')


def export_collection(short):
    cname = short if short.startswith('NEW_') else 'NEW_' + short
    coll = bpy.data.collections.get(cname)
    if not coll:
        log(f'COLLECTION {cname}: MISSING, skipped')
        return None
    t0 = time.time()
    purge_except(short)
    coll = bpy.data.collections.get(cname)
    objs = [o for o in coll.all_objects if o.type == 'MESH']
    # never export retired geometry: hide_render (+ OLD_replaced link) is how
    # v2_integrate.py retires what a part replaces (e.g. the old mug, the
    # scratch guitar, the whole retired full-size A1 and scratch mouse)
    retired = sorted(o.name for o in objs if o.hide_render)
    if retired:
        log(f'{cname}: skipping {len(retired)} retired (hide_render): {retired}')
    objs = [o for o in objs if not o.hide_render]
    before = {o.name: ntris(o.data) for o in objs}
    log(f'{cname}: {len(objs)} mesh objects, {sum(before.values())} tris')
    if DRY_RUN:
        return dict(collection=cname, dry_run=True, tris_before=sum(before.values()))
    single_user(objs)
    if any(o.data.shape_keys for o in objs):
        log(f'{cname}: WARNING shape keys present, decimate may misbehave')

    # keeper emissives -> own primitives
    keepers = set()
    for o in list(objs):
        for km in KEEPER_MATS:
            if any(s.material and s.material.name == km for s in o.material_slots):
                if len(o.material_slots) == 1:
                    keepers.add(o.name)
                else:
                    nn = 'bambu_mini_screen' if km == 'bambu_mini_screen_lit' else o.name + '_keeper'
                    no = separate_by_material(o, km, nn)
                    if no is not None:
                        objs.append(no)
                        before[no.name] = ntris(no.data)
                        before[o.name] = ntris(o.data)
                        keepers.add(no.name)
                        log(f'{cname}: split keeper {no.name} from {o.name}')
    if 'Robot_rsl_lens' not in keepers and any(o.name == 'Robot_rsl_lens' for o in objs):
        keepers.add('Robot_rsl_lens')

    # decimate (before bake)
    budget = BUDGETS.get(short)
    cur = sum(before.values())
    # 0.97 margin: collapse+triangulate overshoots the exact ratio by a few percent
    ratio = 1.0 if budget is None else min(1.0, budget / max(1, cur) * 0.97)
    after = {}
    if not NO_DEC:
        for o in objs:
            if o.name in keepers or all(
                    s.material and s.material.name in NO_DEC_MATS for s in o.material_slots):
                after[o.name] = ntris(o.data)
                continue
            r = ratio
            if short == 'medals':
                r = next((v for k, v in MEDAL_RATIO if k in o.name), ratio)
            if r >= 1.0:
                after[o.name] = ntris(o.data)
                continue
            old = o.data
            o.data = decimate_to(old, r)
            if old.users == 0:
                bpy.data.meshes.remove(old)
            after[o.name] = ntris(o.data)
    # corrective passes: collapse+triangulate overshoots/undershoots, so iterate to the cap
    if not NO_DEC and budget is not None:
        for _pass in range(4):
            got = sum(after[o.name] for o in objs if o.name not in keepers)
            cap = sum(after[o.name] for o in objs if o.name in keepers)
            if got + cap <= budget or got <= 0:
                break
            r2 = max(0.05, (budget - cap) / got * 0.95)
            for o in objs:
                if o.name in keepers:
                    continue
                old = o.data
                o.data = decimate_to(old, r2)
                if old.users == 0:
                    bpy.data.meshes.remove(old)
                after[o.name] = ntris(o.data)
            log(f'{cname}: corrective decimate x{r2:.3f} -> {sum(after.values())} tris')
    else:
        after = dict(before)
    log(f'{cname}: decimate ratio {ratio:.3f} -> {sum(after.values())} tris (target {budget})')

    # UVs
    uv_of = {}
    fresh_uv = set()
    for o in objs:
        un, fresh = ensure_uv(o)
        uv_of[o.name] = un
        if fresh:
            fresh_uv.add(o.name)

    # materials: bake procedurals on the largest user, rebuild, assign to all users
    setup_cycles()
    texdir = os.path.join(TEXDIR, short)
    os.makedirs(texdir, exist_ok=True)
    users = {}
    for o in objs:
        for s in o.material_slots:
            if s.material:
                users.setdefault(s.material, []).append(o)
    webmat = {}
    baked_files = {}
    mat_native = []
    skip_mats = set(x for x in os.environ.get('SKIP_MATS', '').split(',') if x)
    for mat, us in sorted(users.items(), key=lambda kv: kv[0].name):
        # image-vector fix: object got fresh UVs but material reads Generated -> must bake base
        rep = max(us, key=lambda o: ntris(o.data))
        need = analyse_material(mat)
        un = uv_of[rep.name]
        if mat.name in skip_mats:
            log(f'{cname}: SKIP_MATS skipping bake of {mat.name}')
            need = set()
        if not NO_BAKE and (need or (rep.name in fresh_uv and any(
                n.type == 'TEX_IMAGE' for n in mat.node_tree.nodes) if mat.use_nodes else False)):
            log(f'{cname}: baking {mat.name} ({sorted(need)}) on {rep.name} ...')
            wm, files = bake_material(mat, rep, un, short, texdir)
            webmat[mat.name] = wm
            baked_files[mat.name] = files
            log(f'{cname}: baked {mat.name} ({sorted(need)}) on {rep.name}')
        else:
            webmat[mat.name] = mat
            if not need:
                mat_native.append(mat.name)
    for o in objs:
        for s in o.material_slots:
            if s.material and s.material.name in webmat and webmat[s.material.name] != s.material:
                s.material = webmat[s.material.name]

    # freeze world transforms -> world-space meshes, identity nodes
    for o in objs:
        o.data.transform(o.matrix_world)
        o.parent = None
        o.matrix_world = Matrix()
    bpy.context.view_layer.update()

    # export
    os.makedirs(OUTDIR, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    glb = os.path.join(OUTDIR, f'{short}.glb')
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True,
                              export_apply=False, export_yup=True, export_materials='EXPORT',
                              export_cameras=False, export_lights=False, export_animations=False,
                              export_draco_mesh_compression_enable=False)
    bpy.ops.object.select_all(action='DESELECT')

    # sidecar
    anchors = {}
    for o in objs:
        ws = [Vector(v) for v in (Vector(c) for c in
                                  [(o.matrix_world @ v.co) for v in o.data.vertices])]
        lo = Vector((min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws)))
        hi = Vector((max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws)))
        ce = (lo + hi) / 2
        anchors[o.name] = dict(blender_center=[round(x, 4) for x in ce],
                               three_center=[round(x, 4) for x in (ce.x, -ce.z, ce.y)],
                               blender_lo=[round(x, 4) for x in lo],
                               blender_hi=[round(x, 4) for x in hi])
    emissives = sorted({s.material.name for o in objs for s in o.material_slots
                        if s.material and emissive_scalar(s.material)})
    side = dict(collection=cname, budget=budget,
                retired_skipped=retired,
                tris_before=before, tris_after=after,
                tris_total_before=sum(before.values()), tris_total_after=sum(after.values()),
                decimate_ratio=round(ratio, 4),
                within_budget=(budget is None or sum(after.values()) <= budget),
                glb=os.path.basename(glb), glb_bytes=os.path.getsize(glb),
                baked_materials={k: {'channels': sorted(analyse_material(
                    next(m for m in bpy.data.materials if m.name == k))), 'files': v}
                    for k, v in baked_files.items()},
                native_materials=sorted(set(mat_native)),
                final_materials=sorted({s.material.name for o in objs for s in o.material_slots
                                        if s.material}),
                emissive_materials=emissives, keeper_objects=sorted(keepers),
                fresh_uv_objects=sorted(fresh_uv),
                anchors=anchors, seconds=round(time.time() - t0, 1))
    with open(os.path.join(OUTDIR, f'{short}.json'), 'w') as f:
        json.dump(side, f, indent=1)
    # free bake images: they are saved to disk and embedded in the GLB already
    for img in CREATED_IMAGES:
        try:
            if img.name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[img.name])
        except (ReferenceError, RuntimeError):
            pass
    del CREATED_IMAGES[:]
    import gc
    gc.collect()
    log(f"{cname}: WROTE {glb} {os.path.getsize(glb) // 1024} KB "
        f"tris {side['tris_total_before']}->{side['tris_total_after']} "
        f"(budget {budget}, {'OK' if side['within_budget'] else 'OVER'}) "
        f"in {side['seconds']} s")
    return side


def main():
    licensing_gate()
    if TARGET in RETIRED_WHOLE:
        log(f'TARGET {TARGET}: collection NEW_{TARGET} is fully retired in room_public.blend '
            f'(hide_render + OLD_replaced); nothing to export.')
        return
    shorts = [c.name[4:] for c in bpy.data.collections if c.name.startswith('NEW_')
              and c.name[4:] in BUDGETS] if TARGET == 'all' else [TARGET]
    log('TARGETS:', shorts)
    results = {}
    for short in shorts:
        try:
            r = export_collection(short)
            if r:
                results[short] = {k: r[k] for k in (
                    'tris_total_before', 'tris_total_after', 'budget', 'within_budget',
                    'glb_bytes', 'seconds') if k in r}
        except Exception as e:
            import traceback
            traceback.print_exc()
            log(f'{short}: FAILED {e}')
    print('[webprops] RESULTS ' + json.dumps(results))


main()
