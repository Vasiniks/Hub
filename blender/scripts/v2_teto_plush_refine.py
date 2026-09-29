"""
Refine the owner-downloaded Teto plush (CC BY 4.0, "Kasane Teto fatass plush" by revsworks) so it reads as a
soft plush instead of faceted low-poly. Loads blender/scene/parts/teto_plush.blend (built by v2_teto.py) and
saves it back in place. Re-runnable: original vertex positions are kept in the 'plush_orig_co' attribute and
every run restarts from them; modifiers / shader nodes are replaced, not stacked.

  blender -b --factory-startup --python v2_teto_plush_refine.py [-- --out other.blend]

What it does (textures / UVs untouched):
  * drops the FBX's flat custom normals + all-sharp edges -> smooth shading
  * closes the tiny 8-vert holes at the hand tips / feet so subdivision rounds them instead of pinching a cone
  * Catmull-Clark per mesh (UV smooth = Keep Corners, limit surface), levels chosen per part
  * volume compensation: control cages are pre-offset so the subdivided limit surface passes through the
    original vertices -> hands, drills and head keep their size/silhouette instead of shrinking
  * flat face decals (eyes, lashes, mouth) are densified (Simple) and shrinkwrapped onto the smoothed head
  * short-pile minky fabric: fibre + brushed-streak bump, clump mottling, colour-tinted sheen rim, rougher;
    seams with stitch dashes on the hair cap and at the sleeve panel joins. Eyes/lashes/mouth/outlines untouched.
"""
import bpy, bmesh, sys, os, mathutils

REPO = r"C:\Users\Vas\Documents\Github\Hub"
PART = os.path.join(REPO, 'blender', 'scene', 'parts', 'teto_plush.blend')
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[argv.index('--out') + 1] if '--out' in argv else PART

bpy.ops.wm.open_mainfile(filepath=PART)
col = bpy.data.collections['NEW_plush_teto']
M = {o.name: o for o in col.objects if o.type == 'MESH'}

# name -> (subsurf level, volume-compensation strength). None = no Catmull-Clark.
SUB = {
    'Circle':        (2, 1.0),   # skin: head, neck, arms + mitten hands, legs
    'Circle.002':    (1, 1.0),   # hair cap (dense already; L1 + smooth normals is enough)
    'Spiral':        (1, 1.0),   # the two drills
    'Circle.003':    (2, 1.0),   # sleeves
    'Circle.004':    (1, 1.0),   # shirt / torso
    'Circle.005':    (2, 1.0),   # boots
    'Circle.006':    (1, 1.0),   # shorts / seat
    'NurbsPath':     (2, 0.7),   # front bangs
    'NurbsPath.001': (2, 0.7),   # side locks
    'NurbsPath.002': (2, 0.7),   # ahoge
    'Plane.002':     (1, 0.8),   # collar + tie
}
# flat decals that sit on a subdivided surface -> (densify level, shrinkwrap target, wrap mode)
DECALS = {
    'Circle.001': (-2, 'Circle', 'OUTSIDE_SURFACE'),  # textured eye discs (negative = Catmull-Clark, UVs smoothed with the rim)
    'Plane':      (1, 'Circle', 'OUTSIDE_SURFACE'),   # lashes / brows
    'Plane.001':  (1, 'Circle', 'OUTSIDE_SURFACE'),   # mouth
    'Plane.003':  (1, 'Circle.004', 'OUTSIDE'),       # chest pocket outlines (only lift what got buried)
    'Circle.007': (1, 'Circle.004', 'OUTSIDE'),       # shirt buttons
    'Circle.008': (1, 'Circle.004', 'OUTSIDE'),       # pocket buttons
    'Plane.004':  (1, 'Circle.003', 'OUTSIDE'),       # sleeve patch outlines
    'Circle.009': (1, 'Circle.003', 'OUTSIDE'),       # sleeve patch dots
}
FILL_HOLES = ('Circle', 'Circle.005')           # hand tips, feet, boot soles


def restore_or_store(o):
    me = o.data
    a = me.attributes.get('plush_orig_co')
    n = len(me.vertices)
    if a is None:
        a = me.attributes.new('plush_orig_co', 'FLOAT_VECTOR', 'POINT')
        buf = [0.0] * (3 * n); me.vertices.foreach_get('co', buf); a.data.foreach_set('vector', buf)
    else:
        buf = [0.0] * (3 * n); a.data.foreach_get('vector', buf); me.vertices.foreach_set('co', buf)
    me.update()
    return [mathutils.Vector(buf[i * 3:i * 3 + 3]) for i in range(n)]


def smooth_shading(o):
    me = o.data
    for nm in ('custom_normal', 'sharp_edge', 'sharp_face'):
        if nm in me.attributes: me.attributes.remove(me.attributes[nm])
    me.shade_smooth()


def fill_small_holes(o, max_len=8, max_r=0.004):
    """Close the tiny open rings at the hand/foot tips with a single pole vertex (a CC-friendly round cap)."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    lay = bm.verts.layers.float_vector.get('plush_orig_co')
    bnd = {e for e in bm.edges if e.is_boundary}
    loops, seen = [], set()
    for e in bnd:
        if e in seen: continue
        loop, stack = [], [e]; seen.add(e)
        while stack:
            x = stack.pop(); loop.append(x)
            for v in x.verts:
                for y in v.link_edges:
                    if y in bnd and y not in seen: seen.add(y); stack.append(y)
        loops.append(loop)
    n = 0
    for loop in loops:
        vs = {v for e in loop for v in e.verts}
        c = sum((v.co for v in vs), mathutils.Vector()) / len(vs)
        if len(vs) <= max_len and max((v.co - c).length for v in vs) < max_r:
            bmesh.ops.pointmerge(bm, verts=list(vs), merge_co=c)
            keep = next(v for v in vs if v.is_valid)
            if lay is not None: keep[lay] = c
            n += 1
    bm.to_mesh(o.data); bm.free(); o.data.update()
    return n


def limit_positions(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg); me = oe.to_mesh()
    n = len(o.data.vertices)
    buf = [0.0] * (3 * len(me.vertices)); me.vertices.foreach_get('co', buf)
    oe.to_mesh_clear()
    return [mathutils.Vector(buf[i * 3:i * 3 + 3]) for i in range(n)]   # coarse verts come first


def compensate(o, orig, k, iters=6):
    """Offset the cage so the subdivided limit surface hits the original vertices (keeps volume/silhouette)."""
    me = o.data
    for _ in range(iters):
        lim = limit_positions(o)
        for i, v in enumerate(me.vertices):
            v.co += (orig[i] - lim[i]) * k
        me.update()


# ---------------------------------------------------------------- geometry
for name, o in M.items():
    for m in list(o.modifiers): o.modifiers.remove(m)
    orig = restore_or_store(o)
    smooth_shading(o)
    if name in FILL_HOLES:
        print('HOLES', name, fill_small_holes(o))

for name, (lvl, k) in SUB.items():
    o = M[name]
    orig = [v.co.copy() for v in o.data.vertices]
    m = o.modifiers.new('PlushSubsurf', 'SUBSURF')
    m.subdivision_type = 'CATMULL_CLARK'
    m.levels = m.render_levels = lvl
    m.use_limit_surface = True
    m.uv_smooth = 'PRESERVE_CORNERS'
    m.boundary_smooth = 'ALL'
    m.use_creases = True
    if k > 0: compensate(o, orig, k)

for name, (lvl, tgt, mode) in DECALS.items():
    o = M[name]
    s = o.modifiers.new('PlushDecalDensify', 'SUBSURF')
    s.subdivision_type = 'SIMPLE' if lvl > 0 else 'CATMULL_CLARK'
    s.levels = s.render_levels = abs(lvl)
    s.uv_smooth = 'NONE' if lvl > 0 else 'SMOOTH_ALL'   # eye rim + its UV rim round off together -> no stretch
    w = o.modifiers.new('PlushDecalWrap', 'SHRINKWRAP')
    w.target = M[tgt]; w.wrap_method = 'NEAREST_SURFACEPOINT'; w.wrap_mode = mode
    w.offset = 0.0004

# ---------------------------------------------------------------- fabric
# Short-pile minky / velboa: fine fibre noise + a downward-brushed streak (bump), low-frequency clumping that
# mottles colour and height, colour-tinted sheen for the fuzzy rim, slightly rougher. Seams with stitch dashes
# on the hair cap (centre line) and around the sleeves (at the grey/red panel joins). Printed face untouched.
SKIP_MATS = {'Material.003', 'Material.005', 'Material.017', 'Material.018', 'Material.021'}  # eyes, lashes/mouth, outlines
STITCH = 0.004   # stitch pitch (m)


def sleeve_seams():
    """Grey/red join loops on the right sleeve (object space, mirrored in the shader): [(centre, normal, radius)]."""
    from collections import defaultdict
    me = M['Circle.003'].data
    co = [mathutils.Vector(d.vector) for d in me.attributes['plush_orig_co'].data]
    ef = defaultdict(list)
    for p in me.polygons:
        for k in p.edge_keys: ef[k].append(p.material_index)
    adj = defaultdict(set)
    for (a, b), m in ef.items():
        if len(m) == 2 and m[0] != m[1] and co[a].x > 0: adj[a].add(b); adj[b].add(a)
    seams, seen = [], set()
    for v in adj:
        if v in seen: continue
        st, L = [v], []; seen.add(v)
        while st:
            x = st.pop(); L.append(x)
            for y in adj[x]:
                if y not in seen: seen.add(y); st.append(y)
        c = sum((co[i] for i in L), mathutils.Vector()) / len(L)
        C = mathutils.Matrix(((0, 0, 0), (0, 0, 0), (0, 0, 0)))
        for i in L:
            d = co[i] - c
            for r in range(3):
                for q in range(3): C[r][q] += d[r] * d[q]
        n = mathutils.Vector((1, 0.1, 0.1)); Ci = (C + mathutils.Matrix.Identity(3) * 1e-9).inverted()
        for _ in range(60): n = (Ci @ n).normalized()      # loop-plane normal = sleeve axis at the join
        seams.append((c, n, sum((co[i] - c).length for i in L) / len(L)))
    return seams


class NB:
    """tiny node-builder; every node it makes is named 'Plush*' so reruns can strip them."""
    def __init__(s, nt, kind): s.nt = nt; s.kind = kind; s.x = -1600; s.y = -500
    def node(s, t, name, **kw):
        n = s.nt.nodes.new(t); n.name = n.label = 'Plush' + name
        n.location = (s.x, s.y); s.y -= 170
        if s.y < -2600: s.y = -500; s.x += 200
        for k, v in kw.items(): setattr(n, k, v)
        return n
    def inp(s, n, i, v):
        if isinstance(v, bpy.types.NodeSocket): s.nt.links.new(v, n.inputs[i])
        else: n.inputs[i].default_value = v
    def math(s, op, a, b=0.0):
        n = s.node('ShaderNodeMath', op, operation=op)
        s.inp(n, 0, a); s.inp(n, 1, b)
        return n.outputs[0]
    def vmath(s, op, a, b=(0, 0, 0)):
        n = s.node('ShaderNodeVectorMath', op, operation=op)
        s.inp(n, 0, a); s.inp(n, 1, b)
        return n.outputs['Value' if op in ('DOT_PRODUCT', 'LENGTH') else 'Vector']
    def noise(s, vec, scale, detail=2.0, rough=0.6):
        n = s.node('ShaderNodeTexNoise', 'Noise')
        s.inp(n, 'Vector', vec); n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail; n.inputs['Roughness'].default_value = rough
        return n.outputs['Fac']
    def band(s, t, w):
        """1 at t=0, smoothly 0 for |t| >= w."""
        n = s.node('ShaderNodeMapRange', 'Band', interpolation_type='SMOOTHSTEP')
        s.inp(n, 'Value', s.math('ABSOLUTE', t)); n.inputs['From Min'].default_value = 0.0
        n.inputs['From Max'].default_value = w; n.inputs['To Min'].default_value = 1.0; n.inputs['To Max'].default_value = 0.0
        return n.outputs['Result']
    def dashes(s, arc):
        """stitch dashes along an arc-length coordinate: 1 on the thread, 0 between."""
        sn = s.math('SINE', s.math('MULTIPLY', arc, 2 * 3.14159265 / STITCH))
        return s.math('GREATER_THAN', sn, 0.0)


def seam_height(b, P):
    """Groove (negative) with raised stitch dashes across it -> (height, groove) sockets, or None."""
    grooves, stitches = [], []
    if b.kind == 'hair':                                   # centre seam of the hair cap: plane x = 0
        sep = b.node('ShaderNodeSeparateXYZ', 'Sep'); b.inp(sep, 0, P)
        sy = b.node('ShaderNodeSeparateXYZ', 'SepYZ'); b.inp(sy, 0, b.vmath('SUBTRACT', P, (0.0, 0.016, 0.19)))
        ang = b.math('ARCTAN2', sy.outputs['Z'], sy.outputs['Y'])
        grooves.append(b.band(sep.outputs['X'], 0.0013))
        stitches.append((b.band(sep.outputs['X'], 0.0018), b.dashes(b.math('MULTIPLY', ang, 0.09))))
    elif b.kind == 'sleeve':                               # rings at the grey/red joins, both arms (|x|)
        sep = b.node('ShaderNodeSeparateXYZ', 'Sep'); b.inp(sep, 0, P)
        cm = b.node('ShaderNodeCombineXYZ', 'Mirror')
        b.inp(cm, 0, b.math('ABSOLUTE', sep.outputs['X'])); b.inp(cm, 1, sep.outputs['Y']); b.inp(cm, 2, sep.outputs['Z'])
        for c, n, r in SLEEVE_SEAMS:
            u = n.orthogonal().normalized(); v = n.cross(u)
            d = b.vmath('SUBTRACT', cm.outputs[0], c)
            t = b.vmath('DOT_PRODUCT', d, n)
            ang = b.math('ARCTAN2', b.vmath('DOT_PRODUCT', d, v), b.vmath('DOT_PRODUCT', d, u))
            grooves.append(b.band(t, 0.0013))
            stitches.append((b.band(t, 0.0018), b.dashes(b.math('MULTIPLY', ang, r))))
    else:
        return None
    g = grooves[0]
    for x in grooves[1:]: g = b.math('MAXIMUM', g, x)
    st = None
    for w, dsh in stitches:
        x = b.math('MULTIPLY', w, dsh)
        st = x if st is None else b.math('MAXIMUM', st, x)
    return b.math('SUBTRACT', b.math('MULTIPLY', st, 1.5), g), g     # thread sits proud inside the groove


SLEEVE_SEAMS = sleeve_seams()
KIND = {'Material.006': 'hair', 'Material.008': 'sleeve', 'Material.009': 'sleeve'}

for mat in {s.material for o in M.values() for s in o.material_slots if s.material}:
    if mat.name in SKIP_MATS or not mat.use_nodes: continue
    nt = mat.node_tree
    for n in [n for n in nt.nodes if n.name.startswith('Plush')]: nt.nodes.remove(n)
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    # downloaded values are stashed on the material so every rerun starts from them
    if 'plush_base' not in mat: mat['plush_base'] = list(bsdf.inputs['Base Color'].default_value)
    if 'plush_rough' not in mat: mat['plush_rough'] = bsdf.inputs['Roughness'].default_value
    base = mathutils.Vector(mat['plush_base'][:3])
    bsdf.inputs['Base Color'].default_value = list(base) + [1.0]
    bsdf.inputs['Roughness'].default_value = min(1.0, mat['plush_rough'] + 0.2)
    nmap = next((n for n in nt.nodes if n.type == 'NORMAL_MAP'), None)

    b = NB(nt, KIND.get(mat.name))
    P = b.node('ShaderNodeTexCoord', 'Coord').outputs['Object']
    fibre = b.noise(P, 1400.0, 2.0, 0.6)                                  # individual pile tips
    streak = b.noise(b.vmath('MULTIPLY', P, (1.0, 1.0, 0.12)), 700.0, 3.0, 0.6)   # pile brushed down (Z streaks)
    clump = b.noise(P, 160.0, 3.0, 0.55)                                  # velboa clumping patches
    h = b.math('ADD', b.math('MULTIPLY', fibre, 0.5), b.math('MULTIPLY', streak, 0.35))
    h = b.math('ADD', h, b.math('MULTIPLY', clump, 0.35))
    bump = b.node('ShaderNodeBump', 'Bump')
    bump.inputs['Strength'].default_value = 0.55; bump.inputs['Distance'].default_value = 0.0004
    b.inp(bump, 'Height', h)
    if nmap is not None: nt.links.new(nmap.outputs['Normal'], bump.inputs['Normal'])
    normal_out = bump.outputs['Normal']

    # colour: slight mottling from the clumps (+-6 %), darker in seam grooves
    shade = b.math('ADD', 0.88, b.math('MULTIPLY', clump, 0.24))
    sh = seam_height(b, P)
    if sh is not None:
        seam_h, groove = sh
        sb = b.node('ShaderNodeBump', 'SeamBump')
        sb.inputs['Strength'].default_value = 1.0 if b.kind == 'hair' else 0.45; sb.inputs['Distance'].default_value = 0.0008
        b.inp(sb, 'Height', seam_h); nt.links.new(normal_out, sb.inputs['Normal'])
        normal_out = sb.outputs['Normal']
        shade = b.math('MULTIPLY', shade, b.math('SUBTRACT', 1.0, b.math('MULTIPLY', groove, 0.45)))
    cc = b.node('ShaderNodeCombineColor', 'Shade')
    for i in range(3): b.inp(cc, i, shade)
    col = b.node('ShaderNodeMix', 'Tint', data_type='RGBA', blend_type='MULTIPLY')
    col.inputs['Factor'].default_value = 1.0
    col.inputs[6].default_value = list(base) + [1.0]
    nt.links.new(cc.outputs[0], col.inputs[7])
    nt.links.new(col.outputs[2], bsdf.inputs['Base Color'])
    nt.links.new(normal_out, bsdf.inputs['Normal'])

    # fuzzy rim: sheen tinted toward the fabric colour (lifted a little so dark cloth still gets a soft halo)
    tint = base.lerp(mathutils.Vector((1, 1, 1)), 0.25)
    bsdf.inputs['Sheen Weight'].default_value = 0.65
    bsdf.inputs['Sheen Roughness'].default_value = 0.35
    bsdf.inputs['Sheen Tint'].default_value = list(tint) + [1.0]

# ---------------------------------------------------------------- report + save
dg = bpy.context.evaluated_depsgraph_get()
tot = 0
for o in M.values():
    me = o.evaluated_get(dg).to_mesh(); t = sum(len(p.vertices) - 2 for p in me.polygons); tot += t
    o.evaluated_get(dg).to_mesh_clear()
    print('TRIS', o.name, t)
print('TETO_PLUSH_TRIS', tot)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
