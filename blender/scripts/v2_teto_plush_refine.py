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
  * subtle fabric: fine noise bump + a touch of sheen on the plush materials
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
SKIP_MATS = {'Material.003', 'Material.005', 'Material.017', 'Material.018', 'Material.021'}  # textures / outlines
for mat in {s.material for o in M.values() for s in o.material_slots if s.material}:
    if mat.name in SKIP_MATS or not mat.use_nodes: continue
    nt = mat.node_tree
    for n in [n for n in nt.nodes if n.name.startswith('Plush')]: nt.nodes.remove(n)
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    old = bsdf.inputs['Normal'].links[0].from_socket if bsdf.inputs['Normal'].is_linked else None
    tc = nt.nodes.new('ShaderNodeTexCoord'); tc.name = 'PlushCoord'
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.name = 'PlushNoise'
    nz.inputs['Scale'].default_value = 900.0; nz.inputs['Detail'].default_value = 2.0
    nz.inputs['Roughness'].default_value = 0.6
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump'); bump.name = 'PlushBump'
    bump.inputs['Strength'].default_value = 0.08; bump.inputs['Distance'].default_value = 0.0002
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    if old is not None: nt.links.new(old, bump.inputs['Normal'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Sheen Weight'].default_value = 0.2
    bsdf.inputs['Sheen Roughness'].default_value = 0.5
    bsdf.inputs['Sheen Tint'].default_value = bsdf.inputs['Base Color'].default_value
    for i, n in enumerate((tc, nz, bump)): n.location = (bsdf.location.x - 600 + i * 180, bsdf.location.y - 420)

# ---------------------------------------------------------------- report + save
dg = bpy.context.evaluated_depsgraph_get()
tot = 0
for o in M.values():
    me = o.evaluated_get(dg).to_mesh(); t = sum(len(p.vertices) - 2 for p in me.polygons); tot += t
    o.evaluated_get(dg).to_mesh_clear()
    print('TRIS', o.name, t)
print('TETO_PLUSH_TRIS', tot)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
