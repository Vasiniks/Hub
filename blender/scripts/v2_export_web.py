"""
v2_export_web.py -- turn the room's props into web-ready GLBs with their lighting baked in.

    BLENDER_LOCK_OWNER=web-props bash ../blender-locked.sh -b --factory-startup
        <Hub>/blender/scene/room.blend --python blender/scripts/v2_export_web.py -- <set>[,<set>...]
        [--outdir tmp/props_raw] [--res-scale 0.5] [--cpu] [--lit-samples 256] [--ao-samples 128]
        [--pbr-only] [--list]          (sets: see SETS; 'desk', 'rest', 'all' expand)

Reads the FULL room.blend (owner, 2026-10-01: licensing gate lifted, ship everything; the CC BY
credits stay mandatory) and never saves it: everything happens in memory, outputs go to --outdir.

Per set (see SETS):
  1. keep the whole room loaded (it is the light and shadow context of the bake) and apply the
     bake-only edits of v2_bake_sunset.py (fx_room_volume hidden, robot lens driver held at 3.5);
  2. take the VISIBLE meshes only (skip hide_render / hidden / OLD_replaced / objects the sunset
     bake already ships in blender/bake/sunset/manifest.json), evaluated with their modifiers;
     the sources are hidden from render so the decimated copies stand in for them;
  3. decimate to the set's triangle budget (weld + planar dissolve + quadric collapse to an
     absolute target), BEFORE the bake; decimated meshes get smooth-by-angle normals;
  4. split every mesh by material class:
       lit  - non-metal surfaces (incl. alpha cut-outs): ONE Cycles DIFFUSE bake with direct +
              indirect + colour in the full sunset room (all lights, sun, lamp disk, emissive
              PC/screens; shadows from the room and the other props), OIDN-denoised. Exported as
              KHR_materials_unlit; baseColor = linear / litScale in sRGB, litScale in the material
              extras (three: material.userData.litScale). No albedo/ORM/normal maps for these.
       pbr  - metals (scalar metallic >= 0.5), emissive parts, keepers, glass: base colour,
              ORM (AO, roughness, metallic) (+ normal, + baked emissive for node-driven emission),
              from emission-override bakes of the ORIGINAL node materials; lit at runtime by an
              environment capture of the baked room;
  5. one atlas UV per class ('atlas', multi-object smart project + weighted pack);
  6. keepers (Robot_rsl_lens, the A1 mini screen) stay their OWN node + material, never merged;
     glass parts get scalar BLEND materials;
  7. keep the hierarchy that matters: one node per top-level group under each set root (e.g.
     NEW_lamp_pivot with the arm, head and the medals; each electronics item; the MacBook lid),
     at its world transform, meshes joined per group in group-local space -> the GLB loaded at
     identity sits exactly where it is in the room (glTF Y-up: three (x,y,z) = Blender (x,z,-y));
  8. export GLB (textures re-encoded to WebP via EXT_texture_webp) + sidecar JSON.
  --pbr-only skips the lit bake (purges the room, everything PBR: the first-pass behaviour).

Then: PROPS_SRC=tmp/props_raw PROPS_DST=public/assets/v2/props node scripts/optimize-glb.mjs <set...>
      node scripts/props-manifest.mjs
"""
import bpy
import bmesh
import fnmatch
import json
import math
import os
import sys
import time
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


TARGETS = ARGS[0].split(',') if ARGS and not ARGS[0].startswith('--') else []
OUTDIR = os.path.join(REPO, arg('--outdir', os.path.join('tmp', 'props_raw')))
RS = arg('--res-scale', 1.0, float)
USE_CPU = '--cpu' in ARGS
AO_SAMPLES = arg("--ao-samples", 128, int)
LIT = '--pbr-only' not in ARGS          # default: lit bake in the full room (owner, 2026-10-01)
LIT_SAMPLES = arg('--lit-samples', 256, int)
LIT_K_MAX = 8.0
IMG_QUALITY = arg('--quality', 82, int)
BAKE_MANIFEST = os.path.join(REPO, 'blender', 'bake', 'sunset', 'manifest.json')

# --------------------------------------------------------------------------------------------- sets
# src: collection names, or 'obj:<glob>' for loose objects in the Scene Collection.
# budget: total triangles after decimation (None = keep).  res: atlas size (<= 2048).
# weights: (glob, w) UV-area multipliers (texel density), first match wins.
# ratio: (glob, r) per-object decimation multipliers relative to the set ratio.
# s2a: globs of objects whose normal map is baked from the full-resolution mesh.
# keepers: material name -> output node name ('' = keep the object's own name).
KEEPERS = {'robot_rsl_amber': 'Robot_rsl_lens', 'bambu_mini_screen_lit': 'bambu_mini_screen'}
CREDITS = {
    'teto_plush': '"Kasane Teto fatass plush" by revsworks, CC BY 4.0 '
                  '(https://sketchfab.com/3d-models/kasane-teto-fatass-plush-bd8157eb42a04161b2628e58dfd2a852)',
    'mx_master_3s': '"Mouse Logitech MX Master 3S white" by Guibazilla, CC BY 4.0 '
                    '(https://sketchfab.com/3d-models/mouse-logitech-mx-master-3s-white-dc82de97cbe64c6a8deae3328208c984)',
    'bambu_a1_mini': '"3D Printer - Bambu Lab A1 Mini" by neilvfx, CC BY 4.0 '
                     '(https://sketchfab.com/3d-models/3d-printer-bambu-lab-a1-mini-407fb64c44be4e1888db246b447f811b)',
    'motherboard': '"MotherBoard + Components" by Daniel Cardona, CC BY 4.0 '
                   '(https://sketchfab.com/3d-models/motherboard-components-3bc94057328243d4b341a55f59160f8a)',
}
SETS = {
    # ---- desk set
    'monitor': dict(src=['NEW_monitor'], budget=None, res=512, lit=1024,
                    weights=[('NEW_monitor_screen', 0.3), ('NEW_monitor_rear*', 0.6)]),
    'keyboard': dict(src=['NEW_keyboard'], budget=20000, res=256, lit=1024,
                     weights=[('NEW_keyboard_keycaps', 2.0), ('NEW_keyboard_bottom*', 0.4),
                              ('NEW_keyboard_cable', 0.03),
                              ('NEW_keyboard_switches', 0.3), ('NEW_keyboard_plate', 0.3)]),
    'macbook': dict(src=['NEW_macbook'], budget=10000, res=1024, lit=512,
                    weights=[('NEW_mbp_vent*', 0.3), ('NEW_mbp_feet', 0.3), ('NEW_stand_base_pads', 0.3)]),
    'mouse_mx': dict(src=['NEW_mouse_mx'], budget=12000, res=256, lit=1024, credits=['mx_master_3s'],
                     weights=[('MouseMX_Shell', 2.0), ('MouseMX_Base*', 0.4)]),
    'lamp': dict(src=['NEW_lamp', 'NEW_medals'], budget=20000, res=1024, lit=1024,
                 weights=[('medal_*_disc', 3.0), ('medal_*_ribbon', 1.5)],
                 ratio=[('medal_*_disc', 0.45), ('lamp_*', 2.0)],
                 s2a=['medal_*_disc']),
    'pc': dict(src=['NEW_pc', 'NEW_plush_teto'], budget=48000, res=1024, lit=1024,
               credits=['motherboard', 'teto_plush'],
               weights=[('Circle*', 2.5), ('Plane*', 2.5), ('NurbsPath*', 2.5), ('Spiral', 2.5),
                        ('pc_case_*', 1.0), ('pc_glass_panels', 0.2), ('pc_rear_*', 0.4),
                        ('pc_fans_*', 0.6), ('pc_mobo_board', 1.2), ('pc_lcd_*', 2.0)],
               ratio=[('Circle*', 3.0), ('Plane*', 3.0), ('NurbsPath*', 3.0), ('Spiral', 3.0),
                      ('pc_rear_*', 0.6), ('pc_fans_*', 0.8), ('pc_cables_sleeved', 0.6),
                      ('pc_lcd_*', 4.0)]),
    'electronics': dict(src=['NEW_electronics'], budget=30000, res=1024, lit=1024,
                        weights=[('elec_notepad', 1.5), ('elec_sticky_notes', 1.5)]),
    'speedcube': dict(src=['NEW_speedcube'], budget=12000, res=256, lit=512,
                      weights=[('NEW_speedcube_emblem18', 2.0), ('NEW_speedcube_core', 0.2)],
                      ratio=[('NEW_speedcube_emblem18', 3.0), ('NEW_speedcube_core', 0.5)]),
    'lorenz': dict(src=['NEW_lorenz'], budget=15000, res=512, lit=1024,
                   weights=[('NEW_lorenz_paper_page1', 5.0), ('NEW_lorenz_paper_page*', 3.0),
                            ('NEW_lorenz_wire', 0.6)],
                   ratio=[('NEW_lorenz_paper*', 3.0), ('NEW_lorenz_base', 2.0)]),
    'cables': dict(src=['NEW_cables'], budget=15000, res=512, lit=512,
                   weights=[('*_cable', 0.08), ('*_cord', 0.08)]),
    'redbull': dict(src=['NEW_redbull'], budget=4000, res=512, lit=512),
    'teto_pear': dict(src=['NEW_teto_pear'], budget=None, res=256, lit=512),
    # ---- the rest
    'robot': dict(src=['NEW_robot'], budget=40000, res=1024, lit=1024,
                  weights=[('Robot_bumper_fabric', 1.5), ('Robot_number_*', 2.0)],
                  ratio=[('Robot_number_*', 3.0), ('Robot_bumper_fabric', 3.0)]),
    'bambu_mini': dict(src=['NEW_bambu_mini'], budget=35000, res=512, lit=1024, credits=['bambu_a1_mini'],
                       weights=[('bambu_mini_base', 1.5), ('bambu_mini_toolhead', 1.5)]),
    'telecaster': dict(src=['NEW_telecaster', 'NEW_tele_gb'], budget=28000, res=512, lit=1024,
                       weights=[('TeleGB_Deka', 2.5), ('TeleGB_fingerboard*', 2.0), ('TeleStand', 0.5),
                                ('TeleGB_Spring*', 0.2), ('TeleGB_Strings', 0.2)],
                       ratio=[('TeleStand', 0.5), ('TeleGB_Deka', 3.0), ('TeleGB_fingerboard', 2.0)]),
    'painting': dict(src=['NEW_painting'], budget=None, res=256, lit=1024,
                     weights=[('painting_canvas', 6.0)]),
    'bookrack': dict(src=['NEW_bookrack'], budget=8000, res=256, lit=1024,
                     weights=[('bookrack_screw*', 0.2)]),
    'chair': dict(src=['obj:chair_base*'], budget=10000, res=512, lit=1024),
    'desk_misc': dict(src=['obj:driver_*', 'obj:tote*', 'obj:Mesh_14[2-6]'], budget=None, res=512, lit=512),
    'fixtures': dict(src=['NEW_roomshell', 'NEW_curtains'], budget=None, res=512, lit=1024),
}
DESK_SET = ['monitor', 'keyboard', 'macbook', 'mouse_mx', 'lamp', 'pc', 'electronics', 'speedcube',
            'lorenz', 'cables', 'redbull', 'teto_pear']
REST_SET = ['robot', 'bambu_mini', 'telecaster', 'painting', 'bookrack', 'chair', 'desk_misc', 'fixtures']
NO_DECIMATE_BELOW = 300   # objects this small are left alone


def log(*a):
    print('[webprops]', *a, flush=True)


def ntris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def match(name, pairs, default=None):
    for g, v in pairs or ():
        if fnmatch.fnmatchcase(name, g):
            return v
    return default


# --------------------------------------------------------------------------------------------- selection
def baked_object_names():
    try:
        m = json.load(open(BAKE_MANIFEST))
    except OSError:
        m = json.load(open(os.path.join(os.path.dirname(REPO), 'Hub', 'blender', 'bake', 'sunset',
                                        'manifest.json')))
    names = set()
    for a in m['atlases'].values():
        names |= set(a['objects'])
    return names


def ancestors(o):
    out = []
    p = o.parent
    while p:
        out.append(p)
        p = p.parent
    return out


def source_objects(cfg):
    """Visible, non-retired, not-already-baked mesh objects of the set."""
    old = bpy.data.collections.get('OLD_replaced')
    old_objs = set(old.all_objects) if old else set()
    baked = baked_object_names()
    cand = []
    for s in cfg['src']:
        if s.startswith('obj:'):
            cand += [o for o in bpy.context.scene.collection.objects if fnmatch.fnmatchcase(o.name, s[4:])]
        else:
            c = bpy.data.collections.get(s)
            if not c:
                raise RuntimeError(f'collection {s} missing')
            cand += list(c.all_objects)
    vl = bpy.context.view_layer
    out, skipped = [], {}
    for o in dict.fromkeys(cand):
        if o.type != 'MESH':
            continue
        why = None
        if o in old_objs:
            why = 'OLD_replaced'
        elif o.hide_render:
            why = 'hide_render'
        elif o.name not in vl.objects or o.hide_get():
            why = 'hidden'
        elif o.name in baked:
            why = 'in sunset bake'
        elif any(a.hide_render for a in ancestors(o)):
            why = 'parent hidden'
        if why:
            skipped.setdefault(why, []).append(o.name)
        else:
            out.append(o)
    return out, skipped


def purge_to(keep_objs):
    keep = set(keep_objs)
    for o in keep_objs:
        keep |= set(ancestors(o))
    for o in list(bpy.data.objects):
        if o not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    log(f'working set: {len(bpy.data.objects)} objects, {len(bpy.data.meshes)} meshes, '
        f'{len(bpy.data.materials)} materials, {len(bpy.data.images)} images')


# --------------------------------------------------------------------------------------------- materials
def output_nodes(nt):
    return [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL']


def surface_node(mat):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    outs = output_nodes(mat.node_tree)
    act = [n for n in outs if n.is_active_output and n.target in ('ALL', 'CYCLES')] or outs
    for o in act:
        if o.inputs['Surface'].links:
            return o.inputs['Surface'].links[0].from_node
    return None


def find_bsdf(node, seen=None):
    """First Principled (else Diffuse/Emission/...) reached from the surface, skipping
    Transparent branches of Mix/Add shaders. Returns (node, has_transparent_mix)."""
    seen = seen or set()
    if node is None or node in seen:
        return None, False
    seen.add(node)
    if node.type in ('BSDF_PRINCIPLED', 'BSDF_DIFFUSE', 'EMISSION', 'BSDF_GLOSSY', 'BSDF_GLASS',
                     'BSDF_TRANSLUCENT', 'BSDF_SHEEN', 'SUBSURFACE_SCATTERING', 'BSDF_REFRACTION'):
        return node, False
    if node.type in ('MIX_SHADER', 'ADD_SHADER'):
        kids = [l.from_node for i in node.inputs if i.type == 'SHADER' for l in i.links]
        transp = any(k.type == 'BSDF_TRANSPARENT' for k in kids)
        # prefer a Principled child, then anything non-transparent
        kids.sort(key=lambda k: (k.type != 'BSDF_PRINCIPLED', k.type == 'BSDF_TRANSPARENT'))
        for k in kids:
            if k.type == 'BSDF_TRANSPARENT':
                continue
            b, t = find_bsdf(k, seen)
            if b:
                return b, transp or t
        return None, transp
    if node.type == 'REROUTE':
        for i in node.inputs:
            for l in i.links:
                return find_bsdf(l.from_node, seen)
    return None, False


def sock(node, *names):
    for n in names:
        s = node.inputs.get(n)
        if s is not None:
            return s
    return None


def scalar(s, default):
    """default_value of an unlinked socket (float, or luminance of a colour)."""
    if s is None:
        return default
    v = s.default_value
    try:
        return float(v)
    except TypeError:
        return float(0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2])


def classify(mat, set_name):
    """-> dict(kind=opaque|cutout|emit|glass|keeper, ...)."""
    info = dict(kind='opaque', emit_strength=0.0)
    if mat is None:
        return info
    if mat.name in KEEPERS:
        info['kind'] = 'keeper'
    b, transp = find_bsdf(surface_node(mat))
    info['bsdf'] = b.type if b else None
    if b is None:
        log(f'  ! material {mat.name}: no BSDF found, baked as grey opaque')
        return info
    if b.type == 'BSDF_PRINCIPLED':
        es, ec = sock(b, 'Emission Strength'), sock(b, 'Emission Color')
        st = 1.0 if es.links else scalar(es, 0.0)
        lum = 1.0 if ec.links else scalar(ec, 0.0)
        if st > 1e-3 and lum > 1e-3:
            info['emit_strength'] = st if not es.links else 1.0
            if info['kind'] == 'opaque':
                info['kind'] = 'emit'
        mt = sock(b, 'Metallic')
        info['metal'] = mt is not None and not mt.links and float(mt.default_value) >= 0.5
        tw = sock(b, 'Transmission Weight', 'Transmission')
        al = sock(b, 'Alpha')
        trans = 0.0 if tw is None or tw.links else scalar(tw, 0.0)
        if info['kind'] == 'opaque':
            if transp or trans >= 0.5 or (al is not None and not al.links and scalar(al, 1.0) < 0.9):
                info['kind'] = 'glass'
                a = 1.0 if al is None or al.links else scalar(al, 1.0)
                info['alpha'] = round(max(0.08, min(a, 1.0 - 0.8 * max(trans, 1.0 if transp else 0.0))), 3)
            elif al is not None and al.links:
                info['kind'] = 'cutout'
    elif b.type == 'EMISSION':
        info['emit_strength'] = scalar(sock(b, 'Strength'), 1.0)
        if info['kind'] == 'opaque':
            info['kind'] = 'emit'
    elif b.type in ('BSDF_GLASS', 'BSDF_REFRACTION') or transp:
        if info['kind'] == 'opaque':
            info['kind'] = 'glass'
            info['alpha'] = 0.2
    return info


def channel_source(mat, ch, smax):
    """(socket_or_None, default_value, strength) feeding an Emission override for channel ch."""
    b, _ = find_bsdf(surface_node(mat))
    grey = (0.5, 0.5, 0.5, 1.0)
    if ch == 'mask':
        return None, (1.0, 1.0, 1.0, 1.0), 1.0
    if b is None:
        return None, {'base': grey, 'rough': 0.5, 'metal': 0.0, 'alpha': 1.0, 'emit': (0, 0, 0, 1)}[ch], 1.0
    t = b.type
    if ch == 'base':
        s = sock(b, 'Base Color', 'Color')
        if s is None:
            return None, grey, 1.0
        return (s.links[0].from_socket if s.links else None), tuple(s.default_value), 1.0
    if ch in ('rough', 'metal', 'alpha'):
        nm = {'rough': 'Roughness', 'metal': 'Metallic', 'alpha': 'Alpha'}[ch]
        dflt = {'rough': 1.0 if t == 'BSDF_DIFFUSE' else 0.5, 'metal': 0.0, 'alpha': 1.0}[ch]
        s = sock(b, nm)
        if s is None:
            return None, dflt, 1.0
        if s.links:
            return s.links[0].from_socket, None, 1.0
        return None, float(s.default_value), 1.0
    if ch == 'emit':
        if t == 'EMISSION':
            c, s = sock(b, 'Color'), sock(b, 'Strength')
        elif t == 'BSDF_PRINCIPLED':
            c, s = sock(b, 'Emission Color'), sock(b, 'Emission Strength')
        else:
            return None, (0, 0, 0, 1), 1.0
        st = 1.0 if s.links else float(s.default_value)
        if st <= 1e-3:
            return None, (0, 0, 0, 1), 1.0
        return (c.links[0].from_socket if c.links else None), tuple(c.default_value), st / smax
    raise ValueError(ch)


class Override:
    """Temporarily route one channel of every material into an Emission shader."""

    def __init__(self, mats, ch, smax=1.0, kinds=None):
        self.saved = []
        for m in mats:
            nt = m.node_tree
            if nt is None:
                continue
            em = nt.nodes.new('ShaderNodeEmission')
            em.label = '__bake_override'
            src, val, strength = channel_source(m, ch, smax)
            if ch == 'emit' and kinds is not None and (kinds[m.name]['kind'] not in ('emit', 'keeper')
                                                       or not kinds[m.name].get('emit_textured')):
                src, val, strength = None, (0, 0, 0, 1), 1.0
            col = em.inputs['Color']
            if src is not None:
                nt.links.new(src, col)
            elif isinstance(val, tuple):
                col.default_value = val[:3] + (1.0,) if len(val) >= 3 else (val[0],) * 3 + (1.0,)
            else:
                col.default_value = (val, val, val, 1.0)
            em.inputs['Strength'].default_value = strength
            for out in output_nodes(nt):
                si = out.inputs['Surface']
                old = si.links[0].from_socket if si.links else None
                di = out.inputs.get('Displacement')
                oldd = di.links[0].from_socket if di is not None and di.links else None
                if oldd is not None:
                    nt.links.remove(di.links[0])
                nt.links.new(em.outputs['Emission'], si)
                self.saved.append((nt, out, old, oldd))
            self.saved.append((nt, em, None, None))

    def restore(self):
        for nt, node, old, oldd in reversed(self.saved):
            if node.type == 'EMISSION':
                nt.nodes.remove(node)
            else:
                si = node.inputs['Surface']
                for l in list(si.links):
                    nt.links.remove(l)
                if old is not None:
                    nt.links.new(old, si)
                if oldd is not None:
                    nt.links.new(oldd, node.inputs['Displacement'])


# --------------------------------------------------------------------------------------------- mesh ops
def evaluated_copy(o, name):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    me.name = name
    no = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(no)
    no.matrix_world = o.matrix_world.copy()
    return no


def decimate_to(me, ratio):
    """Weld + planar dissolve (frees the collapse floor on CAD plates/extrusions), then
    quadric collapse. Mirrors the v2 part scripts' own reduction order."""
    sc = bpy.context.scene
    target = max(4, ratio * ntris(me))
    o = bpy.data.objects.new('__dec', me)
    sc.collection.objects.link(o)
    mw = o.modifiers.new('WELD', 'WELD')
    mw.merge_threshold = 0.00005
    md = o.modifiers.new('DIS', 'DECIMATE')
    md.decimate_type = 'DISSOLVE'
    md.angle_limit = math.radians(1.0)
    try:
        md.delimit = {'MATERIAL', 'SEAM', 'SHARP', 'UV'}
    except TypeError:
        pass
    g = bpy.context.evaluated_depsgraph_get()
    mid = bpy.data.meshes.new_from_object(o.evaluated_get(g))
    o.modifiers.clear()
    o.data = mid
    m = o.modifiers.new('DEC', 'DECIMATE')
    m.decimate_type = 'COLLAPSE'
    # the ratio applies to the dissolved mesh: aim at the absolute target, not the source ratio
    m.ratio = max(0.01, min(1.0, target / max(1, ntris(mid))))
    m.use_collapse_triangulate = True
    g = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(o.evaluated_get(g))
    bpy.data.objects.remove(o)
    if mid.users == 0:
        bpy.data.meshes.remove(mid)
    return out


def smooth_by_angle(me, deg=35.0):
    try:
        me.shade_smooth()
        me.set_sharpness_by_angle(angle=math.radians(deg), keep_sharp_edges=True)
    except (AttributeError, TypeError):
        for p in me.polygons:
            p.use_smooth = True


def alive(o):
    try:
        return o.name in bpy.data.objects
    except ReferenceError:
        return False


def select_only(objs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def atlas_unwrap(objs, weights, res):
    for o in objs:
        me = o.data
        uv = me.uv_layers.new(name='atlas')
        me.uv_layers.active = uv
    select_only(objs)
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_all(action='SELECT')
    t = time.time()
    bpy.ops.uv.smart_project(angle_limit=math.radians(72), island_margin=0.0, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    log(f'  smart_project {time.time() - t:.1f}s')
    # texel-density weights: scale each object's islands, then repack everything together
    for o in objs:
        w = match(o.name.replace('__lo', ''), weights, 1.0)
        if w != 1.0:
            uv = o.data.uv_layers['atlas'].data
            a = np.empty(len(uv) * 2, dtype=np.float32)
            uv.foreach_get('uv', a)
            a *= math.sqrt(w)
            uv.foreach_set('uv', a)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    margin_px = max(2, round(3 * res / 2048))
    packed = 'pack_islands'
    t = time.time()
    try:
        bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='AXIS_ALIGNED',
                                scale=True, margin_method='FRACTION', margin=margin_px / res,
                                shape_method='AABB')
        log(f'  pack_islands {time.time() - t:.1f}s')
    except (RuntimeError, TypeError) as e:
        log('  ! pack_islands failed:', e, '-- falling back to a plain re-project')
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin_px / res,
                                 area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
        packed = 'smart_project (unweighted)'
    bpy.ops.object.mode_set(mode='OBJECT')
    cov = None
    return packed, cov


def separate_material(o, mat, new_name):
    """Split the faces using mat (a material or a set of them) into their own object (bmesh, no
    operators); returns it (the object itself, renamed, if every face matched) or None."""
    ms = mat if isinstance(mat, (set, frozenset, list, tuple)) else {mat}
    idx = {i for i, s in enumerate(o.material_slots) if s.material in ms}
    if not idx:
        return None
    me = o.data
    sel = [p.material_index in idx for p in me.polygons]
    if not any(sel):
        return None
    if all(sel):
        o.name = new_name
        o.data.name = new_name
        return o
    nme = me.copy()
    for mesh, drop in ((me, True), (nme, False)):
        bm = bmesh.new()
        bm.from_mesh(mesh)
        kill = [f for f in bm.faces if (f.material_index in idx) == drop]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(mesh)
        bm.free()
    n = bpy.data.objects.new(new_name, nme)
    for c in o.users_collection:
        c.objects.link(n)
    n.matrix_world = o.matrix_world.copy()
    n.name = new_name
    nme.name = new_name
    return n


# --------------------------------------------------------------------------------------------- baking
def setup_cycles(samples):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    if not USE_CPU:
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'CUDA'
            prefs.refresh_devices()
            n = 0
            for d in prefs.devices:
                d.use = (d.type == 'CUDA')
                n += d.use
            if n:
                sc.cycles.device = 'GPU'
        except Exception as e:  # noqa: BLE001
            log('  ! CUDA unavailable, baking on CPU:', e)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.margin_type = 'EXTEND'
    if sc.world is None:
        sc.world = bpy.data.worlds.new('__bake_world')


def new_image(name, res, alpha=False, data=True):
    img = bpy.data.images.new(name, res, res, alpha=alpha, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
    return img


def bake(objs, btype, img, mats, margin=8, **kw):
    for m in mats:
        nt = m.node_tree
        tn = nt.nodes.get('__bake_target')
        tn.image = img
        nt.nodes.active = tn
    select_only(objs)
    bpy.ops.object.bake(type=btype, uv_layer='atlas', margin=margin, use_clear=kw.pop('use_clear', True),
                        target='IMAGE_TEXTURES', **kw)


def pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(-1, 4)


def masked_blur(v, mask, res, passes=2):
    """3x3 box blur that only averages covered texels (denoises the AO bake, keeps islands apart)."""
    a = v.reshape(res, res).astype(np.float32)
    m = mask.reshape(res, res).astype(np.float32)
    for _ in range(passes):
        num = np.zeros_like(a)
        den = np.zeros_like(a)
        am = a * m
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                num += np.roll(np.roll(am, dy, 0), dx, 1)
                den += np.roll(np.roll(m, dy, 0), dx, 1)
        a = np.where(m > 0, num / np.maximum(den, 1e-6), a)
    return a.reshape(-1)


def save_png(img, path):
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return path


# --------------------------------------------------------------------------------------------- per set
def gltf_settings_group():
    ng = bpy.data.node_groups.get('glTF Material Output')
    if ng is None:
        ng = bpy.data.node_groups.new('glTF Material Output', 'ShaderNodeTree')
        ng.interface.new_socket('Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket('Thickness', in_out='INPUT', socket_type='NodeSocketFloat')
    return ng


def build_material(name, tex, kind, emit_strength=1.0, scalar_info=None):
    """Atlas material for the exporter: base/ORM/normal(/emissive), or a scalar glass one."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bs = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
    if kind == 'glass':
        si = scalar_info
        bs.inputs['Base Color'].default_value = si['base']
        bs.inputs['Roughness'].default_value = si['rough']
        bs.inputs['Metallic'].default_value = 0.0
        bs.inputs['Alpha'].default_value = si['alpha']
        m.surface_render_method = 'BLENDED'
        return m
    if kind == 'keeper_scalar':
        si = scalar_info
        bs.inputs['Base Color'].default_value = si['base']
        bs.inputs['Roughness'].default_value = si['rough']
        bs.inputs['Emission Color'].default_value = si['emit_color']
        bs.inputs['Emission Strength'].default_value = si['emit_strength']
        return m
    uvn = N.new('ShaderNodeUVMap')
    uvn.uv_map = 'UVMap'

    def tnode(path, data):
        img = bpy.data.images.load(path, check_existing=True)
        img.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
        t = N.new('ShaderNodeTexImage')
        t.image = img
        L.new(uvn.outputs['UV'], t.inputs['Vector'])
        return t
    tb = tnode(tex['base'], False)
    L.new(tb.outputs['Color'], bs.inputs['Base Color'])
    if kind == 'cutout':
        rd = N.new('ShaderNodeMath')
        rd.operation = 'ROUND'
        L.new(tb.outputs['Alpha'], rd.inputs[0])
        L.new(rd.outputs[0], bs.inputs['Alpha'])
        m.surface_render_method = 'DITHERED'
    to = tnode(tex['orm'], True)
    sep = N.new('ShaderNodeSeparateColor')
    L.new(to.outputs['Color'], sep.inputs['Color'])
    L.new(sep.outputs['Green'], bs.inputs['Roughness'])
    L.new(sep.outputs['Blue'], bs.inputs['Metallic'])
    if tex.get('ao'):
        g = N.new('ShaderNodeGroup')
        g.node_tree = gltf_settings_group()
        L.new(sep.outputs['Red'], g.inputs['Occlusion'])
    if tex.get('normal'):
        tn = tnode(tex['normal'], True)
        nm = N.new('ShaderNodeNormalMap')
        nm.uv_map = 'UVMap'
        L.new(tn.outputs['Color'], nm.inputs['Color'])
        L.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if kind in ('emit', 'keeper') and tex.get('emit'):
        te = tnode(tex['emit'], False)
        L.new(te.outputs['Color'], bs.inputs['Emission Color'])
        bs.inputs['Emission Strength'].default_value = emit_strength
    if kind == 'emit_scalar':
        bs.inputs['Emission Color'].default_value = scalar_info['emit_color']
        bs.inputs['Emission Strength'].default_value = scalar_info['emit_strength']
    return m


ROBOT_LIGHT_AVG = 3.5     # v2_bake_sunset.py: driver 3.5 + 3.5*sin(...) -> held at its mean


def bake_scene_edits():
    """The same bake-only differences from room.blend as v2_bake_sunset.py."""
    edits = []
    v = bpy.data.objects.get('fx_room_volume')
    if v:
        v.hide_render = True
        v.hide_viewport = True
        edits.append('fx_room_volume hidden')
    for m in bpy.data.materials:
        nt = m.node_tree
        if not (nt and nt.animation_data and nt.animation_data.drivers) or 'robot' not in m.name:
            continue
        for fc in list(nt.animation_data.drivers):
            path = fc.data_path
            nt.driver_remove(path)
            nt.path_resolve(path.rsplit('.', 1)[0]).default_value = ROBOT_LIGHT_AVG
            edits.append(f'{m.name}: driver removed, held at {ROBOT_LIGHT_AVG}')
    return edits


def denoise_pixels(img, res, exr_path):
    """OIDN through the compositor (Denoise node, HDR), as v2_bake_sunset.py does -> linear RGB array."""
    dsc = bpy.data.scenes.new('__denoise')
    dsc.render.engine = 'BLENDER_WORKBENCH'
    dsc.render.resolution_x = dsc.render.resolution_y = res
    dsc.render.resolution_percentage = 100
    dsc.view_settings.view_transform = 'Standard'
    dsc.view_settings.look = 'None'
    dsc.view_settings.exposure = 0
    cam = bpy.data.objects.new('__denoise_cam', bpy.data.cameras.new('__denoise_cam'))
    dsc.collection.objects.link(cam)
    dsc.camera = cam
    ng = bpy.data.node_groups.new('__denoise_tree', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    ni = ng.nodes.new('CompositorNodeImage')
    ni.image = img
    nd = ng.nodes.new('CompositorNodeDenoise')
    for s_ in nd.inputs:
        if s_.name == 'HDR':
            s_.default_value = True
        elif s_.name in ('Prefilter', 'Quality'):
            for v in (('ACCURATE', 'Accurate') if s_.name == 'Prefilter' else ('HIGH', 'High')):
                try:
                    s_.default_value = v
                    break
                except Exception:  # noqa: BLE001
                    pass
    no = ng.nodes.new('NodeGroupOutput')
    ng.links.new(ni.outputs['Image'], nd.inputs['Image'])
    ng.links.new(nd.outputs['Image'], no.inputs[0])
    dsc.compositing_node_group = ng
    dsc.render.use_compositing = True
    ims = dsc.render.image_settings
    ims.file_format = 'OPEN_EXR'
    ims.color_depth = '32'
    ims.exr_codec = 'ZIP'
    bpy.ops.render.render(scene=dsc.name)
    bpy.data.images['Render Result'].save_render(exr_path, scene=dsc)
    bpy.data.scenes.remove(dsc)
    bpy.data.node_groups.remove(ng)
    bpy.data.objects.remove(cam)
    chk = bpy.data.images.load(exr_path, check_existing=False)
    a = pixels(chk)[:, :3].copy()
    bpy.data.images.remove(chk)
    raw = pixels(img)[:, :3]
    if abs(float(a.mean()) - float(raw.mean())) > 0.15 * float(raw.mean()) + 1e-6:
        log(f'  ! denoised level {a.mean():.4f} differs from raw {raw.mean():.4f}; using raw')
        return raw.copy()
    return a


def build_lit_material(name, path, cutout, scale):
    """KHR_materials_unlit for the exporter: Output <- [Mix(alpha, Transparent, .)] <-
    Mix(Is Camera Ray, Transparent, Emission(lit texture)). litScale goes to material extras."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    for n in list(N):
        if n.type != 'OUTPUT_MATERIAL':
            N.remove(n)
    out = next(n for n in N if n.type == 'OUTPUT_MATERIAL')
    uvn = N.new('ShaderNodeUVMap')
    uvn.uv_map = 'UVMap'
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = 'sRGB'
    t = N.new('ShaderNodeTexImage')
    t.image = img
    L.new(uvn.outputs['UV'], t.inputs['Vector'])
    em = N.new('ShaderNodeEmission')
    L.new(t.outputs['Color'], em.inputs['Color'])
    lp = N.new('ShaderNodeLightPath')
    tr = N.new('ShaderNodeBsdfTransparent')
    mx = N.new('ShaderNodeMixShader')
    L.new(lp.outputs['Is Camera Ray'], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    top = mx
    if cutout:
        rd = N.new('ShaderNodeMath')
        rd.operation = 'ROUND'
        L.new(t.outputs['Alpha'], rd.inputs[0])
        tr2 = N.new('ShaderNodeBsdfTransparent')
        ma = N.new('ShaderNodeMixShader')
        L.new(rd.outputs[0], ma.inputs[0])
        L.new(tr2.outputs[0], ma.inputs[1])
        L.new(mx.outputs[0], ma.inputs[2])
        top = ma
        m.surface_render_method = 'DITHERED'
    L.new(top.outputs[0], out.inputs['Surface'])
    m['litScale'] = float(scale)
    return m


def group_of(o, roots):
    """Top-level group node under a set root: the ancestor directly below the topmost ancestor
    (if it is an empty), else the topmost ancestor itself; None for parentless objects."""
    chain = ancestors(o)
    if not chain:
        return None
    top = chain[-1]
    if len(chain) >= 2 and chain[-2].type == 'EMPTY':
        return chain[-2]
    return top


def export_set(name):
    cfg = SETS[name]
    t0 = time.time()
    res = max(256, min(2048, int(cfg['res'] * RS)))
    srcs, skipped = source_objects(cfg)
    log(f'== {name}: {len(srcs)} visible meshes; skipped: ' +
        json.dumps({k: (len(v), v[:8]) for k, v in skipped.items()}))
    if not srcs:
        log(f'{name}: nothing to export')
        return None
    if LIT:
        log(f'{name}: full room kept for the lit bake; bake-only edits: {bake_scene_edits()}')
    else:
        purge_to(srcs)
    # ---------------------------------------------------------------- groups (anchor nodes)
    groups = {}
    for o in srcs:
        g = group_of(o, None)
        groups.setdefault(g.name if g else '__world', []).append(o.name)
    group_mw = {gn: (bpy.data.objects[gn].matrix_world.copy() if gn != '__world' else Matrix())
                for gn in groups}
    group_parent = {}
    for gn in groups:
        if gn == '__world':
            continue
        ch = ancestors(bpy.data.objects[gn])
        group_parent[gn] = ch[-1].name if ch else None
    # ---------------------------------------------------------------- evaluated copies
    lo, hi, before = {}, {}, {}
    s2a = cfg.get('s2a', [])
    for o in srcs:
        c = evaluated_copy(o, o.name + '__lo')
        if not c.data.polygons:
            bpy.data.objects.remove(c)
            skipped.setdefault('no faces', []).append(o.name)
            continue
        before[o.name] = ntris(c.data)
        lo[o.name] = c
        if match(o.name, [(g, True) for g in s2a], False):
            hi[o.name] = evaluated_copy(o, o.name + '__hi')
            hi[o.name].hide_render = True
    # the sources sit exactly under their copies: keep them out of every ray (AO would hit them)
    for o in srcs:
        o.hide_render = True
    for gn in list(groups):
        groups[gn] = [n for n in groups[gn] if n in lo]
        if not groups[gn]:
            del groups[gn]
    tot_before = sum(before.values())
    mats = sorted({s.material for c in lo.values() for s in c.material_slots if s.material},
                  key=lambda m: m.name)
    kinds = {m.name: classify(m, name) for m in mats}
    # objects with no material slots get a neutral one
    neutral = None
    for c in lo.values():
        if not any(s.material for s in c.material_slots):
            if neutral is None:
                neutral = bpy.data.materials.new('__neutral')
                neutral.use_nodes = True
                mats.append(neutral)
                kinds[neutral.name] = classify(neutral, name)
            if c.material_slots:
                c.material_slots[0].material = neutral
            else:
                c.data.materials.append(neutral)
    log(f'{name}: materials ' + json.dumps({k: v['kind'] for k, v in kinds.items()
                                            if v['kind'] != 'opaque'}) + f' (+{sum(v["kind"] == "opaque" for v in kinds.values())} opaque)')
    # ---------------------------------------------------------------- decimate
    budget = cfg.get('budget')

    def protected(c):
        return all(s.material is None or kinds[s.material.name]['kind'] in ('keeper', 'glass')
                   for s in c.material_slots) or ntris(c.data) < NO_DECIMATE_BELOW
    after = dict(before)
    if budget is not None and tot_before > budget:
        fixed = sum(before[k] for k, c in lo.items() if protected(c))
        for it in range(5):
            cur = {k: ntris(c.data) for k, c in lo.items()}
            if sum(cur.values()) <= budget:
                break
            var = {k: v for k, v in cur.items() if not protected(lo[k])}
            want = budget - (sum(cur.values()) - sum(var.values()))
            # weighted shares: r_i = base * w_i, sum(var_i * r_i) = want
            ws = {k: match(k, cfg.get('ratio'), 1.0) for k in var}
            denom = sum(var[k] * ws[k] for k in var)
            base = max(0.02, want * (0.97 if it == 0 else 0.93) / max(1, denom))
            for k in var:
                r = min(1.0, base * ws[k])
                if r >= 0.995:
                    continue
                c = lo[k]
                old = c.data
                c.data = decimate_to(old, r)
                smooth_by_angle(c.data)
                if old.users == 0:
                    bpy.data.meshes.remove(old)
            log(f'{name}: decimate pass {it}: base ratio {base:.3f} -> '
                f'{sum(ntris(c.data) for c in lo.values())} tris (budget {budget}, fixed {fixed})')
        after = {k: ntris(c.data) for k, c in lo.items()}
    tot_after = sum(after.values())
    # ---------------------------------------------------------------- lit / pbr split
    # LIT: non-metal surfaces -> one Cycles DIFFUSE (direct+indirect+colour) bake in the full room,
    #      exported KHR_materials_unlit.  PBR: metal (metallic >= 0.5), emissive, keepers, glass.
    if LIT:
        for v in kinds.values():
            if v['kind'] in ('opaque', 'cutout') and v.get('metal'):
                v['kind'] = 'metal'
    else:
        for v in kinds.values():
            if v['kind'] == 'metal':
                v['kind'] = 'opaque'
    PBR_KINDS = ('metal', 'emit', 'keeper', 'glass') if LIT else ('opaque', 'cutout', 'metal', 'emit',
                                                                   'keeper', 'glass')
    lo_parts = {}
    lit_objs, pbr_objs = [], []
    for k, c in lo.items():
        pm = {s.material for s in c.material_slots if s.material and kinds[s.material.name]['kind'] in PBR_KINDS}
        parts_ = []
        if pm:
            piece = separate_material(c, pm, c.name + 'P')
            if piece is not None:
                parts_.append(piece)
                pbr_objs.append(piece)
        if alive(c) and c not in parts_ and c.data.polygons:
            parts_.append(c)
            lit_objs.append(c)
        lo_parts[k] = parts_
    log(f'{name}: {len(lit_objs)} lit parts ({sum(ntris(o.data) for o in lit_objs)} tris), '
        f'{len(pbr_objs)} pbr parts ({sum(ntris(o.data) for o in pbr_objs)} tris)')
    # ---------------------------------------------------------------- atlas UVs (one per mode)
    res_lit = max(256, min(2048, int(cfg.get('lit', 1024) * RS)))
    tu = time.time()
    packer = {}
    if lit_objs:
        packer['lit'] = atlas_unwrap(lit_objs, cfg.get('weights'), res_lit)[0]
    if pbr_objs:
        packer['pbr'] = atlas_unwrap(pbr_objs, cfg.get('weights'), res)[0]
    coverage = None
    log(f'{name}: atlas UVs {packer} in {time.time() - tu:.1f}s')
    objs = lit_objs + pbr_objs
    for c in objs:   # the material's own UV stays the render UV during the bake
        uvs = c.data.uv_layers
        orig = [u for u in uvs if u.name != 'atlas']
        for u in uvs:
            u.active_render = (u == orig[0]) if orig else (u.name == 'atlas')
        uvs.active = uvs['atlas']
    # ---------------------------------------------------------------- bake
    setup_cycles(4)
    for m in mats:
        tn = m.node_tree.nodes.new('ShaderNodeTexImage')
        tn.name = '__bake_target'
    texdir = os.path.join(OUTDIR, 'tex', name)
    os.makedirs(texdir, exist_ok=True)
    for m in mats:   # scalar emission rides on factors (tiny LEDs are sub-pixel in an atlas)
        kinds[m.name]['emit_textured'] = channel_source(m, 'emit', 1.0)[0] is not None
    emitters = [v['emit_strength'] for v in kinds.values() if v['kind'] in ('emit', 'keeper')
                and v['emit_strength'] > 0 and v['emit_textured']]
    smax = max(emitters) if emitters else 1.0
    timings = {}
    tex, tex_lit, stats = {}, {}, {}
    sc = bpy.context.scene

    def emit_bake(objs_, ch, r, data, margin=8):
        img = new_image(f'{name}_{ch}_{r}', r, alpha=False, data=data)
        ov = Override(mats, ch, smax, kinds)
        try:
            bake(objs_, 'EMIT', img, mats, margin=margin)
        finally:
            ov.restore()
        return img
    if pbr_objs:
        has_cut = 'cutout' in PBR_KINDS and any(v['kind'] == 'cutout' for v in kinds.values())
        imgs = {'mask': emit_bake(pbr_objs, 'mask', res, True, margin=0)}
        for ch, data in (('base', False), ('rough', True), ('metal', True)) + \
                ((('alpha', True),) if has_cut else ()) + ((('emit', False),) if emitters else ()):
            tb = time.time()
            imgs[ch] = emit_bake(pbr_objs, ch, res, data)
            timings[ch] = round(time.time() - tb, 1)
        tb = time.time()
        sc.cycles.samples = AO_SAMPLES
        old_dist = sc.world.light_settings.distance
        sc.world.light_settings.distance = 0.08
        imgs['ao'] = new_image(f'{name}_ao', res, data=True)
        bake(pbr_objs, 'AO', imgs['ao'], mats)
        sc.world.light_settings.distance = old_dist
        timings['ao'] = round(time.time() - tb, 1)
        tb = time.time()
        sc.cycles.samples = 4
        nrm = new_image(f'{name}_normal', res, data=True)
        bake(pbr_objs, 'NORMAL', nrm, mats, normal_space='TANGENT')
        s2a_done = []
        if hi:   # the full-resolution relief for the s2a objects (e.g. medal faces)
            npx = pixels(nrm)
            for k, h in hi.items():
                tgt = [p for p in lo_parts.get(k, []) if p in pbr_objs]
                if not tgt:
                    continue
                tmp = new_image(f'{name}_s2a_{k}', res, alpha=True, data=True)
                tmp.pixels.foreach_set(np.zeros(res * res * 4, dtype=np.float32))
                for m in mats:
                    m.node_tree.nodes['__bake_target'].image = tmp
                h.hide_render = False
                select_only([h, tgt[0]], active=tgt[0])
                dims = max(tgt[0].dimensions)
                bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', use_selected_to_active=True,
                                    cage_extrusion=max(0.0005, dims * 0.01),
                                    max_ray_distance=max(0.002, dims * 0.03),
                                    uv_layer='atlas', margin=0, use_clear=False, target='IMAGE_TEXTURES')
                tp = pixels(tmp)
                mask = tp[:, 3] > 0.5
                npx[mask] = tp[mask]
                s2a_done.append((k, int(mask.sum())))
                h.hide_render = True
                bpy.data.images.remove(tmp)
            nrm.pixels.foreach_set(npx.ravel())
        imgs['normal'] = nrm
        timings['normal'] = round(time.time() - tb, 1)
        P = {k: pixels(v) for k, v in imgs.items()}
        covered = P['mask'][:, 0] > 0.5
        base = new_image(f'{name}_basecolor', res, alpha=has_cut, data=False)
        bp = P['base'].copy()
        bp[:, 3] = P['alpha'][:, 0] if has_cut else 1.0
        base.pixels.foreach_set(bp.ravel())
        tex['base'] = save_png(base, os.path.join(texdir, f'{name}_basecolor.png'))
        orm_res = max(256, res // 2)
        orm = new_image(f'{name}_orm', res, data=True)
        op = np.ones((res * res, 4), dtype=np.float32)
        op[:, 0] = masked_blur(P['ao'][:, 0], covered, res, passes=2)
        op[:, 1] = P['rough'][:, 0]
        op[:, 2] = P['metal'][:, 0]
        orm.pixels.foreach_set(op.ravel())
        if orm_res != res:
            orm.scale(orm_res, orm_res)
        tex['orm'] = save_png(orm, os.path.join(texdir, f'{name}_orm.png'))
        tex['ao'] = True
        n = P['normal']
        dev = np.abs(n[:, :3] - np.array([0.5, 0.5, 1.0]))[covered].max(axis=1) if covered.any() else np.zeros(1)
        bumpy = float((dev > 0.03).mean())
        if bumpy > 0.002:
            tex['normal'] = save_png(nrm, os.path.join(texdir, f'{name}_normal.png'))
        if emitters:
            em = imgs['emit']
            er = max(256, res // 2)
            em.scale(er, er)
            tex['emit'] = save_png(em, os.path.join(texdir, f'{name}_emissive.png'))
        stats['pbr'] = dict(normal_bumpy_fraction=round(bumpy, 4), s2a=s2a_done,
                            base_mean=[round(float(x), 3) for x in P['base'][covered][:, :3].mean(0)] if covered.any() else None,
                            ao_mean=round(float(P['ao'][covered][:, 0].mean()), 3) if covered.any() else None,
                            coverage_px=round(float(covered.mean()), 3))
    if lit_objs:
        lit_cut = any(kinds[s.material.name]['kind'] == 'cutout' for c in lit_objs for s in c.material_slots
                      if s.material)
        mk = emit_bake(lit_objs, 'mask', res_lit, True, margin=0)
        covered_l = pixels(mk)[:, 0] > 0.5
        alpha_l = emit_bake(lit_objs, 'alpha', res_lit, True) if lit_cut else None
        tb = time.time()
        sc.cycles.samples = LIT_SAMPLES
        sc.cycles.use_adaptive_sampling = False
        li = bpy.data.images.new(f'{name}_lit_raw', res_lit, res_lit, alpha=False, float_buffer=True)
        li.colorspace_settings.name = 'Linear Rec.709'
        bake(lit_objs, 'DIFFUSE', li, mats, pass_filter={'DIRECT', 'INDIRECT', 'COLOR'})
        timings['lit'] = round(time.time() - tb, 1)
        tb = time.time()
        raw = pixels(li)[:, :3]
        lin = denoise_pixels(li, res_lit, os.path.join(texdir, f'{name}_lit_dn.exr'))
        timings['lit_denoise'] = round(time.time() - tb, 1)
        lin = np.maximum(lin, 0.0)
        cov_vals = lin[covered_l].max(axis=1) if covered_l.any() else np.ones(1)
        # store lin / K: K is the 99.8th percentile (rounded up to 2 significant digits), so dark
        # props keep 8-bit precision and bright ones are not clipped; the runtime multiplies by K
        # Capped at LIT_K_MAX: AgX (Blender and three) saturates at 0.18 * 2^4.03 = 2.9 scene-linear,
        # 2.15 after the +0.45 EV exposure, so radiance above 8 renders white anyway; the cap keeps
        # 8-bit precision for the rest (the lamp head next to its disk light reaches 160+).
        K = float(min(max(np.percentile(cov_vals, 99.9), 1e-3), LIT_K_MAX))
        e = math.floor(math.log10(K)) - 1
        K = round(math.ceil(K / 10 ** e) * 10 ** e, 6)
        enc = np.clip(lin / K, 0, 1)
        enc = np.where(enc <= 0.0031308, enc * 12.92, 1.055 * np.power(enc, 1 / 2.4) - 0.055)
        out = np.ones((res_lit * res_lit, 4), dtype=np.float32)
        out[:, :3] = enc
        if alpha_l is not None:
            out[:, 3] = pixels(alpha_l)[:, 0]
        lit_img = bpy.data.images.new(f'{name}_lit', res_lit, res_lit, alpha=alpha_l is not None)
        lit_img.colorspace_settings.name = 'sRGB'
        lit_img.pixels.foreach_set(out.ravel())
        tex_lit['lit'] = save_png(lit_img, os.path.join(texdir, f'{name}_lit.png'))
        tex_lit['scale'] = K
        stats['lit'] = dict(lit_scale=K, raw_mean=round(float(raw[covered_l].mean()), 4) if covered_l.any() else None,
                            denoised_mean=round(float(lin[covered_l].mean()), 4) if covered_l.any() else None,
                            p50=round(float(np.percentile(cov_vals, 50)), 4),
                            clipped_fraction=round(float((cov_vals > K).mean()), 5),
                            coverage_px=round(float(covered_l.mean()), 3), samples=LIT_SAMPLES)
    log(f'{name}: bake seconds {timings} on {sc.cycles.device}; textures pbr {sorted(k for k in tex if tex[k] is not True)} '
        f'lit {sorted(tex_lit)}; ' + json.dumps(stats))
    # ---------------------------------------------------------------- build export materials
    def scalar_info(m):
        b, _ = find_bsdf(surface_node(m))
        d = dict(base=(0.8, 0.8, 0.8, 1.0), rough=0.1, alpha=kinds[m.name].get('alpha', 0.3),
                 emit_color=(0, 0, 0, 1), emit_strength=0.0)
        if b is not None:
            s_ = sock(b, 'Base Color', 'Color')
            if s_ is not None and not s_.links:
                d['base'] = tuple(s_.default_value)
            r = sock(b, 'Roughness')
            if r is not None and not r.links:
                d['rough'] = float(r.default_value)
            ec = sock(b, 'Emission Color', 'Color' if b.type == 'EMISSION' else '__none')
            es = sock(b, 'Emission Strength', 'Strength' if b.type == 'EMISSION' else '__none')
            if ec is not None and not ec.links:
                d['emit_color'] = tuple(ec.default_value)
            if es is not None and not es.links:
                d['emit_strength'] = float(es.default_value)
        return d
    fam = {}
    mode_of = {}

    def family(kind):
        if kind not in fam:
            if LIT and kind in ('opaque', 'cutout'):
                nm = f'{name}_lit' + ('_cutout' if kind == 'cutout' else '')
                fam[kind] = build_lit_material(nm, tex_lit['lit'], kind == 'cutout', tex_lit['scale'])
                mode_of[nm] = 'lit'
            else:
                nm = f'{name}_' + {'opaque': 'pbr', 'metal': 'pbr', 'cutout': 'pbr_cutout', 'emit': 'emit'}[kind]
                fam[kind] = build_material(nm, tex, 'opaque' if kind == 'metal' else kind, emit_strength=smax)
                mode_of[nm] = 'pbr' if kind != 'emit' else 'pbr_emissive'
        return fam[kind]
    web = {}
    keeper_info = {}
    for m in mats:
        k = kinds[m.name]['kind']
        if k == 'glass':
            web[m.name] = build_material(f'{m.name}_web', tex, 'glass', scalar_info=scalar_info(m))
            mode_of[web[m.name].name] = 'glass'
        elif k == 'keeper':
            si = scalar_info(m)
            textured_emit = 'emit' in tex and channel_source(m, 'emit', 1.0)[0] is not None
            orig_name = m.name
            m.name = orig_name + '__src'
            kinds[m.name] = kinds[orig_name]
            if textured_emit:
                wmk = build_material(orig_name, tex, 'keeper', emit_strength=si['emit_strength']
                                     if si['emit_strength'] > 0 else smax)
            else:
                wmk = build_material(orig_name, tex, 'keeper_scalar', scalar_info=si)
            web[m.name] = web[orig_name] = wmk
            mode_of[wmk.name] = 'pbr_emissive_keeper'
            keeper_info[orig_name] = dict(textured_emission=bool(textured_emit),
                                          emission_strength=round(si['emit_strength'] or smax, 3),
                                          emission_color=[round(x, 3) for x in si['emit_color'][:3]])
        elif k == 'emit' and not kinds[m.name]['emit_textured']:
            si = scalar_info(m)
            orig_name = m.name
            m.name = orig_name + '__src'
            kinds[m.name] = kinds[orig_name]
            web[m.name] = web[orig_name] = build_material(orig_name, tex, 'emit_scalar', scalar_info=si)
            mode_of[orig_name] = 'pbr_emissive'
        else:
            web[m.name] = family(k)
    # remove the original UV layers, rename the atlas
    for c in objs:
        for u in [u for u in c.data.uv_layers if u.name != 'atlas']:
            c.data.uv_layers.remove(u)
        c.data.uv_layers['atlas'].name = 'UVMap'
        for s_ in c.material_slots:
            if s_.material:
                s_.material = web[s_.material.name]
    tex_all = dict(tex)
    if tex_lit:
        tex_all['lit'] = tex_lit['lit']
    # free the source objects' names for the output nodes
    for o in list(bpy.data.objects):
        if not o.name.endswith(('__lo', '__hi')):
            o.name = o.name + '__src'
    out_objs, nodes, emissive_nodes = [], {}, []
    for gn, members in groups.items():
        node = bpy.data.objects.new(gn if gn != '__world' else f'{name}_root', None)
        bpy.context.scene.collection.objects.link(node)
        node.empty_display_size = 0.05
        node.matrix_world = group_mw[gn]
        nodes[gn] = node
        out_objs.append(node)
    for gn, pn in group_parent.items():
        if pn and pn != gn and pn not in nodes:
            # the set root holds no meshes itself (e.g. electronics: all items are groups): add it
            rn = bpy.data.objects.new(pn, None)
            bpy.context.scene.collection.objects.link(rn)
            rn.matrix_world = bpy.data.objects[pn + '__src'].matrix_world.copy()
            nodes[pn] = rn
            out_objs.append(rn)
    bpy.context.view_layer.update()
    for gn, pn in group_parent.items():
        if pn and pn != gn:
            mw = nodes[gn].matrix_world.copy()
            nodes[gn].parent = nodes[pn]
            nodes[gn].matrix_world = mw
    bpy.context.view_layer.update()
    for gn, members in groups.items():
        node = nodes[gn]
        inv = node.matrix_world.inverted()
        parts = [p for n in members for p in lo_parts.get(n, []) if alive(p)]
        for c in parts:
            c.data.transform(inv @ c.matrix_world)
            c.matrix_world = Matrix()
        # keepers first, as their own objects
        for c in list(parts):
            for km, kname in KEEPERS.items():
                wm = web.get(km)
                if wm is None or not any(s.material == wm for s in c.material_slots):
                    continue
                sep = separate_material(c, wm, kname)
                if sep is not None and sep is not c:
                    parts.append(sep)
                emissive_nodes.append(dict(node=sep.name, material=wm.name, keeper=True,
                                           **keeper_info.get(km, {})))
        knames = {e['node'] for e in emissive_nodes}
        glass = {}
        for c in list(parts):
            if c.name in knames:
                continue
            for s in list(c.material_slots):
                if s.material and s.material.name.endswith('_web'):
                    gname = f'{gn if gn != "__world" else name}__glass_{s.material.name[:-4]}'
                    sep = separate_material(c, s.material, gname + '__part')
                    if sep is not None:
                        glass.setdefault(gname, []).append(sep)
        for gname, pieces in list(glass.items()):
            select_only(pieces, active=pieces[0])
            if len(pieces) > 1:
                bpy.ops.object.join()
            j = bpy.context.view_layer.objects.active
            j.name = gname
            j.data.name = gname
            glass[gname] = j
        parts = [p for p in parts if alive(p)
                 and not p.name.endswith('__part') and p.name not in glass] + list(glass.values())
        keep_names = knames | set(glass)
        body = [c for c in parts if c.name not in keep_names and c.data.polygons]
        if body:
            select_only(body, active=body[0])
            if len(body) > 1:
                bpy.ops.object.join()
            j = bpy.context.view_layer.objects.active
            j.name = f'{gn if gn != "__world" else name}__mesh'
            j.data.name = j.name
            parts = [p for p in parts if alive(p) and p.name in keep_names] + [j]
        for c in parts:
            if alive(c) and c.data.polygons:
                c.parent = node
                c.matrix_parent_inverse = Matrix()
                c.matrix_basis = Matrix()
                out_objs.append(c)
    # ---------------------------------------------------------------- export
    os.makedirs(OUTDIR, exist_ok=True)
    glb = os.path.join(OUTDIR, f'{name}.glb')
    select_only(out_objs)
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True,
                              export_apply=False, export_yup=True, export_materials='EXPORT',
                              export_image_format='WEBP', export_image_quality=IMG_QUALITY,
                              export_texcoords=True, export_normals=True,
                              export_tangents=False,  # three derives tangents; saves ~4 B/vertex
                              export_cameras=False, export_lights=False, export_animations=False,
                              export_extras=True, export_draco_mesh_compression_enable=False)
    # ---------------------------------------------------------------- sidecar
    final_tris = sum(ntris(o.data) for o in out_objs if o.type == 'MESH')
    anchors = {}
    for o in out_objs:
        if o.type != 'EMPTY':
            continue
        t = o.matrix_world.translation
        anchors[o.name] = dict(blender_world=[round(x, 4) for x in t],
                               three_world=[round(t.x, 4), round(t.z, 4), round(-t.y, 4)],
                               parent=o.parent.name if o.parent else None,
                               is_pivot=o.name.endswith('_pivot'))
    meshes = {}
    for o in out_objs:
        if o.type != 'MESH':
            continue
        ws = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo_ = Vector([min(v[i] for v in ws) for i in range(3)])
        hi_ = Vector([max(v[i] for v in ws) for i in range(3)])
        meshes[o.name] = dict(parent=o.parent.name if o.parent else None, tris=ntris(o.data),
                              materials=[s.material.name for s in o.material_slots if s.material],
                              blender_bbox=[[round(x, 4) for x in lo_], [round(x, 4) for x in hi_]])
    emissive_mats = sorted({m.name for o in out_objs if o.type == 'MESH' for s in o.material_slots
                            for m in [s.material] if m and m.node_tree and any(
                                n.type == 'BSDF_PRINCIPLED' and (n.inputs['Emission Color'].links or
                                n.inputs['Emission Strength'].default_value > 0 and
                                max(n.inputs['Emission Color'].default_value[:3]) > 0)
                                for n in m.node_tree.nodes)})
    side = dict(set=name, sources=cfg['src'], source_blend='blender/scene/room.blend',
                budget=budget, within_budget=(budget is None or final_tris <= budget * 1.02),
                tris_before=tot_before, tris_after=final_tris,
                objects=[dict(name=o, tris_before=before[o], tris_after=after[o]) for o in before],
                skipped=skipped, atlas=dict(pbr_res=res if pbr_objs else None,
                                            lit_res=res_lit if lit_objs else None, packer=packer),
                textures={k: os.path.basename(v) for k, v in tex_all.items() if isinstance(v, str)},
                lit_scale=tex_lit.get('scale'),
                material_modes={m: mode_of.get(m, 'pbr') for m in sorted({s_.material.name for o in out_objs
                                if o.type == 'MESH' for s_ in o.material_slots if s_.material})},
                material_kinds={k: v['kind'] for k, v in kinds.items()},
                emissive_materials=emissive_mats, emissive_strength_max=round(smax, 3),
                emissive_nodes=emissive_nodes, anchors=anchors, meshes=meshes,
                credits=[dict(key=c, text=CREDITS[c]) for c in cfg.get('credits', [])],
                bake_stats=stats, bake_seconds=timings, glb=os.path.basename(glb),
                glb_bytes=os.path.getsize(glb), seconds=round(time.time() - t0, 1))
    with open(os.path.join(OUTDIR, f'{name}.json'), 'w') as f:
        json.dump(side, f, indent=1)
    log(f'{name}: WROTE {glb} {os.path.getsize(glb) // 1024} KB, tris {tot_before} -> {final_tris} '
        f'(budget {budget}) in {side["seconds"]} s')
    return side


def main():
    room = bpy.data.filepath
    if '--list' in ARGS:
        for k, v in SETS.items():
            srcs, sk = source_objects(v)
            log(k, len(srcs), sum(ntris(o.data) for o in srcs), {a: len(b) for a, b in sk.items()})
        return
    targets = []
    for t in TARGETS:
        targets += DESK_SET if t == 'desk' else REST_SET if t == 'rest' else list(SETS) if t == 'all' else [t]
    results = {}
    for i, t in enumerate(targets):
        if i:
            bpy.ops.wm.open_mainfile(filepath=room, load_ui=False)
        try:
            r = export_set(t)
            if r:
                results[t] = {k: r[k] for k in ('tris_before', 'tris_after', 'budget', 'glb_bytes', 'seconds')}
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            log(f'{t}: FAILED {e}')
            results[t] = dict(failed=str(e))
    print('[webprops] RESULTS ' + json.dumps(results), flush=True)


main()
