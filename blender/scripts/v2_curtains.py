"""
Curtains + rod for the window wall, built straight into the open room scene.

Run inside Blender (room.blend open):  exec(open(r"<repo>/blender/scripts/v2_curtains.py").read())
Re-running replaces the previous build (collection NEW_curtains).

Room space (Blender, Z-up, metres): window opening x -1.32..1.02, z 0.7..2.5, inner wall face y = 1.30.
Two floor-length linen panels, pinch-pleated on rings, one each side of the opening.
"""
import bpy, bmesh, math, random
from mathutils import Vector

WIN_X0, WIN_X1, WALL_Y = -1.32, 1.02, 1.30
ROD_Z, ROD_Y = 2.64, 1.215          # rod centre: above the casing, 8.5 cm off the wall
ROD_X0, ROD_X1 = WIN_X0 - 0.36, WIN_X1 + 0.36
PANEL_W = 0.46                       # gathered width of each panel
OVERLAP = 0.09                       # how far each panel covers the opening edge
HEM_Z = 0.012                        # hem clearance above the floor
TOP_Z = ROD_Z - 0.045                # fabric top, hanging under the rings

rnd = random.Random(7)

# ------------------------------------------------------------------ reset
col = bpy.data.collections.get('NEW_curtains')
if col:
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)
else:
    col = bpy.data.collections.new('NEW_curtains')
    bpy.context.scene.collection.children.link(col)


def link(o):
    col.objects.link(o)
    return o


# ------------------------------------------------------------------ materials
def mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree


def linen():
    m, nt = mat('curtain_linen')
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    p = nt.nodes.new('ShaderNodeBsdfPrincipled')
    p.inputs['Base Color'].default_value = (0.80, 0.765, 0.70, 1)   # warm off-white linen
    p.inputs['Roughness'].default_value = 0.88
    p.inputs['Sheen Weight'].default_value = 0.35
    p.inputs['Sheen Roughness'].default_value = 0.5
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent')
    tr.inputs['Color'].default_value = (0.86, 0.80, 0.70, 1)
    mix = nt.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.32                          # backlit glow from the window
    # slub weave: fine anisotropic noise into bump
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (900, 60, 900)
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 1.0
    nz.inputs['Detail'].default_value = 3
    wv = nt.nodes.new('ShaderNodeTexWave')
    wv.inputs['Scale'].default_value = 5200
    wv.inputs['Distortion'].default_value = 2
    add = nt.nodes.new('ShaderNodeMath'); add.operation = 'ADD'
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.12
    bump.inputs['Distance'].default_value = 0.0004
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], nz.inputs['Vector'])
    nt.links.new(tc.outputs['Object'], wv.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], add.inputs[0])
    nt.links.new(wv.outputs['Fac'], add.inputs[1])
    nt.links.new(add.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    nt.links.new(p.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    return m


def metal():
    m, nt = mat('curtain_rod_black')
    p = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value = (0.018, 0.018, 0.02, 1)
    p.inputs['Metallic'].default_value = 1.0
    p.inputs['Roughness'].default_value = 0.38
    return m


LINEN, METAL = linen(), metal()


# ------------------------------------------------------------------ panel
def panel(name, x_wall, x_inner):
    """Pleated panel between x_wall (outer, toward the side wall) and x_inner (covering the opening)."""
    nu, nv = 150, 110
    folds = 8
    h = TOP_Z - HEM_Z
    phase = [rnd.uniform(-0.35, 0.35) for _ in range(folds + 2)]
    amp_j = [rnd.uniform(0.8, 1.2) for _ in range(folds + 2)]
    bm = bmesh.new()
    grid = []
    for j in range(nv + 1):
        v = j / nv                              # 0 at top, 1 at hem
        z = TOP_Z - v * h
        row = []
        for i in range(nu + 1):
            u = i / nu
            k = u * folds
            fi = int(min(k, folds))
            # pleat depth: pinched tight under each ring, opening out as it falls
            base = 0.020 + 0.030 * (v ** 0.7)
            a = base * (amp_j[fi] * (1 - (k - fi)) + amp_j[fi + 1] * (k - fi))
            s = math.sin(2 * math.pi * k + phase[fi] * v * 3.0)
            pinch = 1.0 - 0.75 * math.exp(-v * 22)          # top 10 cm: tight pinch-pleat
            y = ROD_Y + 0.004 - a * s * pinch - 0.012 * (v ** 2)  # hem kicks out slightly
            # gathered width: fabric fans out a little toward the hem
            spread = 1.0 + 0.05 * v
            xm = (x_wall + x_inner) / 2
            x = xm + (x_wall + (x_inner - x_wall) * u - xm) * spread
            x += 0.004 * math.sin(v * 7 + u * 3)            # gentle irregularity
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for j in range(nv):
        for i in range(nu):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    me.materials.append(LINEN)
    o = link(bpy.data.objects.new(name, me))
    for p in me.polygons:
        p.use_smooth = True
    sol = o.modifiers.new('thickness', 'SOLIDIFY'); sol.thickness = 0.0025; sol.offset = 0
    sub = o.modifiers.new('smooth', 'SUBSURF'); sub.levels = 1; sub.render_levels = 1
    # UVs for the weave (object coords drive it; still give a clean grid unwrap for export)
    return o, folds


def cyl(name, r, length, loc, axis='X', verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=length, location=loc)
    o = bpy.context.active_object
    if axis == 'X':
        o.rotation_euler = (0, math.pi / 2, 0)
    elif axis == 'Y':
        o.rotation_euler = (math.pi / 2, 0, 0)
    for c in o.users_collection:
        c.objects.unlink(o)
    link(o); o.name = name
    o.data.materials.append(METAL)
    bev = o.modifiers.new('bevel', 'BEVEL'); bev.width = min(0.0015, r * 0.3); bev.segments = 2
    bpy.ops.object.shade_smooth()
    return o


def rings(xs):
    for n, x in enumerate(xs):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.019, minor_radius=0.0028, major_segments=28, minor_segments=10,
                                         location=(x, ROD_Y, ROD_Z), rotation=(0, math.pi / 2, 0))
        o = bpy.context.active_object
        for c in o.users_collection:
            c.objects.unlink(o)
        link(o); o.name = f'curtain_ring_{n:02d}'
        o.data.materials.append(METAL)
        bpy.ops.object.shade_smooth()
        # clip + eyelet hook dropping to the fabric
        cyl(f'curtain_clip_{n:02d}', 0.0016, 0.03, (x, ROD_Y, ROD_Z - 0.032), axis='Z', verts=10)


# left panel: outer edge near the left end of the rod, inner edge over the opening
lx_wall, lx_in = WIN_X0 - PANEL_W + OVERLAP, WIN_X0 + OVERLAP
rx_in, rx_wall = WIN_X1 - OVERLAP, WIN_X1 + PANEL_W - OVERLAP
left, folds = panel('curtain_left', lx_wall, lx_in)
right, _ = panel('curtain_right', rx_wall, rx_in)
ring_x = [lx_wall + (lx_in - lx_wall) * (i + 0.5) / folds for i in range(folds)] + \
         [rx_in + (rx_wall - rx_in) * (i + 0.5) / folds for i in range(folds)]
rings(ring_x)

# rod, finials, brackets
cyl('curtain_rod', 0.011, ROD_X1 - ROD_X0, ((ROD_X0 + ROD_X1) / 2, ROD_Y, ROD_Z))
for side, x in (('L', ROD_X0), ('R', ROD_X1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=14, radius=0.02, location=(x + (-0.02 if side == 'L' else 0.02), ROD_Y, ROD_Z))
    f = bpy.context.active_object
    for c in f.users_collection:
        c.objects.unlink(f)
    link(f); f.name = f'curtain_finial_{side}'
    f.scale = (1.25, 1, 1); f.data.materials.append(METAL); bpy.ops.object.shade_smooth()
for side, x in (('L', ROD_X0 + 0.07), ('R', ROD_X1 - 0.07)):
    cyl(f'curtain_bracket_arm_{side}', 0.006, WALL_Y - ROD_Y, (x, (WALL_Y + ROD_Y) / 2, ROD_Z), axis='Y', verts=16)
    cyl(f'curtain_bracket_plate_{side}', 0.022, 0.006, (x, WALL_Y - 0.003, ROD_Z), axis='Y', verts=32)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0135, minor_radius=0.0035, major_segments=24, minor_segments=8,
                                     location=(x, ROD_Y, ROD_Z), rotation=(0, math.pi / 2, 0))
    cup = bpy.context.active_object
    for c in cup.users_collection:
        c.objects.unlink(cup)
    link(cup); cup.name = f'curtain_bracket_cup_{side}'; cup.data.materials.append(METAL); bpy.ops.object.shade_smooth()

print('curtains built:', len(col.objects), 'objects')
