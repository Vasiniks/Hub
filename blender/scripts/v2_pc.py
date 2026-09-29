"""
v2_pc.py -- all-white dual-chamber showcase PC (panoramic glass, blue GPU, pink/blue RGB) on the floor
at the desk's right, where the storage tote (room.blend Node_380) stood.

    blender -b --factory-startup --python blender/scripts/v2_pc.py -- [--no-render]

Generic O11-Vision / Y60-style build, no brand marks:
  * case 304 x 465 x 465 mm (W x D x H), white aluminium/steel, pillarless tempered-glass front + side
    (4 mm, faint tint; shadow rays pass so light gets in), perforated top over a 360 radiator
  * dual chamber: white motherboard tray with rubber grommets, PSU hidden in the rear chamber
  * white ATX board with white shrouds/heatsinks, 4 white DIMMs with RGB bars, white AIO with a round
    LCD pump head (gauge + "38 C" readout) and white sleeved tubes to a white 360 radiator
  * 7 white 120 mm fans (3 bottom intake, 3 under the radiator, 1 rear) with RGB face rings + inner band
  * blue triple-fan GPU, vertically mounted facing the glass (blue shroud + backplate, RGB edge strip)
  * white sleeved 24-pin / 8-pin EPS / 12V-2x6 cables through the grommets
  * black mains cable from the PSU inlet along the floor behind the desk into the free socket (#2) of
    the power strip (NEW_cables, x 0.26, y 1.235)
RGB: one emission ramp driven by case-local position, so fans read pink at the front-bottom and blue
toward the rear/top with gradients between. Case yawed 12 deg toward the seated viewer.
Writes blender/scene/parts/pc.blend (collection NEW_pc, root NEW_pc_root, ROOM coordinates).
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector as V, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'pc.blend')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
SEAT = V((0.0, -0.16, 1.175))

# ---- placement: case-local u (+x, glass side at -u), v (+y, front glass at -v), z up; origin = floor centre
C = V((1.315, 0.650, 0.0))
YAW = math.radians(12.0)
T = Matrix.Translation(C) @ Matrix.Rotation(YAW, 4, 'Z')
TI = T.inverted()
W, D, H = 0.304, 0.465, 0.465
HW, HD = W / 2, D / 2

PINK = (1.0, 0.114, 0.578)      # #ff5fc8 in linear
BLUE = (0.042, 0.198, 1.0)      # #3a7bff in linear
EMIT = float(next((a.split('=')[1] for a in ARGS if a.startswith('--emit=')), 9.0))
MAT = {}
I4 = Matrix.Identity(4)


# ============================================================================== materials
def pr(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def si(p, name, val):
    try:
        p.inputs[name].default_value = val
    except KeyError:
        pass


def new_mat(name, col, rough, metal=0.0, coat=0.0, bump=0.0, bscale=900.0, rvar=0.03):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = pr(m)
    si(p, 'Base Color', (*col, 1))
    si(p, 'Metallic', metal)
    si(p, 'Roughness', rough)
    if coat:
        si(p, 'Coat Weight', coat)
        si(p, 'Coat Roughness', 0.08)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    if rvar:
        nz2 = nt.nodes.new('ShaderNodeTexNoise')
        nz2.inputs['Scale'].default_value = 160
        nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = max(0.0, rough - rvar)
        mr.inputs['To Max'].default_value = rough + rvar
        nt.links.new(nz2.outputs['Fac'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], p.inputs['Roughness'])
    if bump:
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs['Scale'].default_value = bscale
        nz.inputs['Detail'].default_value = 3
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        b = nt.nodes.new('ShaderNodeBump')
        b.inputs['Strength'].default_value = bump
        b.inputs['Distance'].default_value = 0.0002
        nt.links.new(nz.outputs['Fac'], b.inputs['Height'])
        nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
    MAT[name] = m
    return m


def math_node(nt, op, a, b=None, val=None):
    n = nt.nodes.new('ShaderNodeMath')
    n.operation = op
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def rgb_color(nt):
    """Pink/blue ramp driven by case-local position (object coords: every part sits at the root)."""
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    a = math_node(nt, 'MULTIPLY', sep.outputs['Y'], 2 * math.pi / 0.50)
    b = math_node(nt, 'MULTIPLY', sep.outputs['Z'], 2 * math.pi / 0.62)
    c = math_node(nt, 'ADD', a, b)
    c = math_node(nt, 'ADD', c, 0.35)
    s = math_node(nt, 'SINE', c)
    f = math_node(nt, 'MULTIPLY_ADD', s, 0.5)
    f.node.inputs[2].default_value = 0.5
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.0, (*PINK, 1)
    el[1].position, el[1].color = 1.0, (*BLUE, 1)
    e = el.new(0.32)
    e.color = (*PINK, 1)
    e = el.new(0.68)
    e.color = (*BLUE, 1)
    nt.links.new(f, ramp.inputs['Fac'])
    return ramp.outputs['Color']


def led_mat(name, strength, base=0.9, rough=0.4, trans=0.0):
    m = new_mat(name, (base, base, base), rough, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    nt.links.new(rgb_color(nt), p.inputs['Emission Color'])
    si(p, 'Emission Strength', strength)
    if trans:
        si(p, 'Transmission Weight', trans)
    return m


def glass_mat():
    m = bpy.data.materials.new('pc_glass')
    m.use_nodes = True
    nt = m.node_tree
    p = pr(m)
    si(p, 'Base Color', (0.90, 0.94, 0.95, 1))
    si(p, 'Roughness', 0.01)
    si(p, 'IOR', 1.52)
    si(p, 'Transmission Weight', 1.0)
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    tr.inputs['Color'].default_value = (0.86, 0.89, 0.89, 1)
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Shadow Ray'], mix.inputs[0])
    nt.links.new(p.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    MAT['pc_glass'] = m
    return m


def perforated_mat(name='pc_perforated', ax=('X', 'Y'), P=0.0045):
    """White steel with a staggered hole grid (alpha) in the object-coord plane `ax`."""
    m = new_mat(name, (0.86, 0.86, 0.85), 0.42, bump=0.02, bscale=600)
    nt = m.node_tree
    p = pr(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    u = math_node(nt, 'DIVIDE', sep.outputs[ax[0]], P)
    v = math_node(nt, 'DIVIDE', sep.outputs[ax[1]], P * 0.866)
    row = math_node(nt, 'FLOOR', v)
    odd = math_node(nt, 'MODULO', row, 2.0)
    odd = math_node(nt, 'ABSOLUTE', odd)
    u2 = math_node(nt, 'ADD', u, math_node(nt, 'MULTIPLY', odd, 0.5))
    fu = math_node(nt, 'SUBTRACT', math_node(nt, 'FRACT', u2), 0.5)
    fv = math_node(nt, 'SUBTRACT', math_node(nt, 'FRACT', v), 0.5)
    fv = math_node(nt, 'MULTIPLY', fv, 0.866)
    d = math_node(nt, 'SQRT', math_node(nt, 'ADD', math_node(nt, 'MULTIPLY', fu, fu), math_node(nt, 'MULTIPLY', fv, fv)))
    alpha = math_node(nt, 'GREATER_THAN', d, 0.33)
    nt.links.new(alpha, p.inputs['Alpha'])
    return m


def filter_mat():
    """Fine black nylon dust-filter mesh (woven grid bump) in object XY."""
    m = new_mat('pc_filter_mesh', (0.035, 0.035, 0.038), 0.6, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    a = math_node(nt, 'SINE', math_node(nt, 'MULTIPLY', sep.outputs['X'], 2 * math.pi / 0.0009))
    b = math_node(nt, 'SINE', math_node(nt, 'MULTIPLY', sep.outputs['Y'], 2 * math.pi / 0.0009))
    h = math_node(nt, 'MAXIMUM', a, b)
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.5
    bp.inputs['Distance'].default_value = 0.0002
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], p.inputs['Normal'])
    return m


def rad_core_mat():
    m = new_mat('pc_rad_fins', (0.82, 0.82, 0.81), 0.5, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    s = math_node(nt, 'SINE', math_node(nt, 'MULTIPLY', sep.outputs['Y'], 2 * math.pi / 0.0016))
    b = nt.nodes.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = 0.6
    b.inputs['Distance'].default_value = 0.0004
    nt.links.new(s, b.inputs['Height'])
    nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = -1
    mr.inputs['To Min'].default_value = 0.35
    mr.inputs['To Max'].default_value = 0.82
    nt.links.new(s, mr.inputs['Value'])
    cmb = nt.nodes.new('ShaderNodeCombineXYZ')
    for k in range(3):
        nt.links.new(mr.outputs['Result'], cmb.inputs[k])
    nt.links.new(cmb.outputs[0], p.inputs['Base Color'])
    return m


def sleeve_mat(name, col, rough=0.55):
    """Braided sleeve: UV x = length (m), UV y = around (0..1)."""
    m = new_mat(name, col, rough, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    uvn = nt.nodes.new('ShaderNodeUVMap')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(uvn.outputs['UV'], sep.inputs[0])
    a = math_node(nt, 'MULTIPLY', sep.outputs['X'], 2 * math.pi / 0.0026)
    b = math_node(nt, 'MULTIPLY', sep.outputs['Y'], 2 * math.pi * 7)
    s1 = math_node(nt, 'SINE', math_node(nt, 'ADD', a, b))
    s2 = math_node(nt, 'SINE', math_node(nt, 'SUBTRACT', a, b))
    h = math_node(nt, 'MULTIPLY', s1, s2)
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.45
    bp.inputs['Distance'].default_value = 0.0003
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], p.inputs['Normal'])
    return m


def sock(coll, ident):
    return next(x for x in coll if x.identifier == ident)


def screen_mat():
    """Round pump LCD in its own object XY (metres): dark face, pink->blue gauge arc, thin outer ring."""
    m = bpy.data.materials.new('pc_pump_screen')
    m.use_nodes = True
    nt = m.node_tree
    p = pr(m)
    si(p, 'Base Color', (0.0, 0.0, 0.0, 1))
    si(p, 'Roughness', 0.06)
    si(p, 'Coat Weight', 0.0)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    x, y = sep.outputs['X'], sep.outputs['Y']
    r = math_node(nt, 'SQRT', math_node(nt, 'ADD', math_node(nt, 'MULTIPLY', x, x), math_node(nt, 'MULTIPLY', y, y)))
    ang = math_node(nt, 'ARCTAN2', y, x)
    band = math_node(nt, 'MULTIPLY', math_node(nt, 'GREATER_THAN', r, 0.0215), math_node(nt, 'LESS_THAN', r, 0.0262))
    gap = math_node(nt, 'MULTIPLY', math_node(nt, 'GREATER_THAN', ang, -2.356), math_node(nt, 'LESS_THAN', ang, -0.785))
    arc = math_node(nt, 'MULTIPLY', band, math_node(nt, 'SUBTRACT', 1.0, gap))
    # s: 0 at -45 deg going CCW to 1 at 225 deg (-135)
    s = math_node(nt, 'DIVIDE', math_node(nt, 'FRACT', math_node(nt, 'DIVIDE', math_node(nt, 'ADD', ang, 0.785), 2 * math.pi)), 0.75)
    s = math_node(nt, 'SUBTRACT', 1.0, s)          # fill from the lower-left end clockwise
    lit = math_node(nt, 'LESS_THAN', s, 0.68)
    level = math_node(nt, 'ADD', math_node(nt, 'MULTIPLY', lit, 0.85), 0.15)
    ring = math_node(nt, 'MULTIPLY', math_node(nt, 'GREATER_THAN', r, 0.0288), math_node(nt, 'LESS_THAN', r, 0.0296))
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.0, (*PINK, 1)
    el[1].position, el[1].color = 1.0, (*BLUE, 1)
    nt.links.new(s, ramp.inputs['Fac'])
    g = math_node(nt, 'MULTIPLY', arc, level)
    mix1 = nt.nodes.new('ShaderNodeMix')
    mix1.data_type = 'RGBA'
    mix1.inputs['Factor'].default_value = 1.0
    mix1.blend_type = 'MULTIPLY'
    nt.links.new(ramp.outputs['Color'], sock(mix1.inputs, 'A_Color'))
    cmb = nt.nodes.new('ShaderNodeCombineXYZ')
    for k in range(3):
        nt.links.new(g, cmb.inputs[k])
    nt.links.new(cmb.outputs[0], sock(mix1.inputs, 'B_Color'))
    add = nt.nodes.new('ShaderNodeMix')
    add.data_type = 'RGBA'
    add.blend_type = 'ADD'
    nt.links.new(ring, add.inputs['Factor'])
    nt.links.new(sock(mix1.outputs, 'Result_Color'), sock(add.inputs, 'A_Color'))
    sock(add.inputs, 'B_Color').default_value = (0.10, 0.20, 0.60, 1)
    bg = nt.nodes.new('ShaderNodeMix')
    bg.data_type = 'RGBA'
    bg.blend_type = 'ADD'
    bg.inputs['Factor'].default_value = 1.0
    nt.links.new(sock(add.outputs, 'Result_Color'), sock(bg.inputs, 'A_Color'))
    sock(bg.inputs, 'B_Color').default_value = (0.006, 0.007, 0.022, 1)
    nt.links.new(sock(bg.outputs, 'Result_Color'), p.inputs['Emission Color'])
    si(p, 'Emission Strength', 5.0)
    MAT['pc_pump_screen'] = m
    return m


def make_materials():
    new_mat('pc_white_alu', (0.87, 0.87, 0.86), 0.32, bump=0.015, bscale=1200)
    new_mat('pc_white_steel', (0.85, 0.85, 0.84), 0.45, bump=0.04, bscale=700)
    new_mat('pc_white_plastic', (0.87, 0.87, 0.86), 0.36, bump=0.02, bscale=1400)
    new_mat('pc_white_pcb', (0.80, 0.80, 0.79), 0.5, bump=0.03, bscale=500)
    new_mat('pc_white_rubber', (0.74, 0.74, 0.73), 0.75, bump=0.05, bscale=2000)
    new_mat('pc_dark_plastic', (0.018, 0.018, 0.02), 0.45)
    new_mat('pc_port_dark', (0.006, 0.006, 0.007), 0.7, rvar=0.0)
    new_mat('pc_metal', (0.80, 0.80, 0.80), 0.28, metal=1.0)
    new_mat('pc_heatsink', (0.10, 0.10, 0.11), 0.38, metal=0.85)
    new_mat('pc_psu', (0.05, 0.05, 0.055), 0.45, metal=0.4)
    new_mat('pc_gpu_blue', (0.008, 0.050, 0.32), 0.34, metal=0.3, coat=0.25, bump=0.01, bscale=1500)
    new_mat('pc_gpu_blue_dark', (0.002, 0.010, 0.10), 0.35, metal=0.4, coat=0.3)
    new_mat('pc_gpu_accent', (0.62, 0.68, 0.80), 0.22, metal=1.0)
    new_mat('pc_gpu_pcb', (0.02, 0.03, 0.04), 0.5)
    new_mat('pc_cable_black', (0.018, 0.018, 0.018), 0.45, bump=0.01)
    new_mat('pc_plug_black', (0.02, 0.02, 0.021), 0.38)
    m = new_mat('pc_fan_blade', (0.72, 0.72, 0.74), 0.38, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    si(p, 'Transmission Weight', 0.3)
    nt.links.new(rgb_color(nt), p.inputs['Emission Color'])
    si(p, 'Emission Strength', EMIT * 0.10)
    m = new_mat('pc_gpu_blade', (0.88, 0.89, 0.92), 0.38, rvar=0.0)
    si(pr(m), 'Transmission Weight', 0.2)
    si(pr(m), 'Emission Color', (*BLUE, 1))
    si(pr(m), 'Emission Strength', EMIT * 0.03)
    led_mat('pc_rgb_led', EMIT)
    led_mat('pc_rgb_diffuser', EMIT * 0.75, rough=0.5)
    led_mat('pc_rgb_strip', EMIT * 0.35, rough=0.5)
    m = new_mat('pc_led_white', (0.9, 0.9, 0.9), 0.4, rvar=0.0)
    si(pr(m), 'Emission Color', (0.35, 0.55, 1.0, 1))
    si(pr(m), 'Emission Strength', 14.0)
    m = new_mat('pc_screen_text', (0.9, 0.9, 0.9), 0.3, rvar=0.0)
    si(pr(m), 'Emission Color', (1.0, 1.0, 1.0, 1))
    si(pr(m), 'Emission Strength', 4.0)
    glass_mat()
    m = new_mat('pc_glass_edge', (0.55, 0.80, 0.70), 0.04, rvar=0.0)
    si(pr(m), 'Transmission Weight', 1.0)
    si(pr(m), 'IOR', 1.52)
    perforated_mat()
    perforated_mat('pc_perforated_uz', ('X', 'Z'), 0.0038)
    filter_mat()
    new_mat('pc_riser', (0.80, 0.80, 0.79), 0.30, bump=0.01, bscale=1500)
    new_mat('pc_ssd', (0.03, 0.03, 0.035), 0.35, metal=0.5)
    new_mat('pc_gold', (0.85, 0.62, 0.28), 0.25, metal=1.0)
    new_mat('pc_rubber_dark', (0.03, 0.03, 0.03), 0.8, bump=0.05, bscale=2000)
    new_mat('pc_tie', (0.80, 0.80, 0.78), 0.45)
    for nm, col in (('pc_led_green', (0.1, 1.0, 0.2)), ('pc_led_amber', (1.0, 0.45, 0.05))):
        m = new_mat(nm, (0.2, 0.2, 0.2), 0.3, rvar=0.0)
        si(pr(m), 'Emission Color', (*col, 1))
        si(pr(m), 'Emission Strength', 6.0)
    for nm, col in (('pc_jack_green', (0.05, 0.45, 0.08)), ('pc_jack_pink', (0.8, 0.2, 0.4)),
                    ('pc_jack_blue', (0.05, 0.2, 0.7)), ('pc_jack_orange', (0.8, 0.3, 0.03))):
        new_mat(nm, col, 0.4, rvar=0.0)
    rad_core_mat()
    sleeve_mat('pc_sleeve_white', (0.83, 0.83, 0.82))
    sleeve_mat('pc_tube_white', (0.84, 0.84, 0.83), 0.5)
    screen_mat()


# ============================================================================== geometry
class MB:
    """Mesh builder: a bmesh + material list; each primitive is built in its own bmesh and merged."""

    def __init__(s, name, mats):
        s.name = name
        s.mats = list(mats)
        s.bm = bmesh.new()
        s.uv = s.bm.loops.layers.uv.new('UVMap')

    def i(s, mat):
        if mat not in s.mats:
            s.mats.append(mat)
        return s.mats.index(mat)

    def merge(s, src, mat=None, M=None):
        if M is not None:
            bmesh.ops.transform(src, matrix=M, verts=src.verts)
        bmesh.ops.recalc_face_normals(src, faces=src.faces)
        src_uv = src.loops.layers.uv.active
        vm = {v: s.bm.verts.new(v.co) for v in src.verts}
        mi = s.i(mat) if mat is not None else None
        for f in src.faces:
            try:
                nf = s.bm.faces.new([vm[v] for v in f.verts])
            except ValueError:
                continue
            nf.material_index = mi if mi is not None else f.material_index
            if src_uv is not None:
                for ln, lo in zip(nf.loops, f.loops):
                    ln[s.uv].uv = lo[src_uv].uv
        src.free()

    def build(s, coll, parent, ang=35):
        me = bpy.data.meshes.new(s.name)
        s.bm.to_mesh(me)
        s.bm.free()
        for m in s.mats:
            me.materials.append(MAT[m])
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(ang))
        o = bpy.data.objects.new(s.name, me)
        coll.objects.link(o)
        o.parent = parent
        return o


def box_bm(lo, hi, r=0.0, seg=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    lo, hi = V(lo), V(hi)
    sz, c = hi - lo, (hi + lo) / 2
    for v in bm.verts:
        v.co = V((c.x + v.co.x * sz.x, c.y + v.co.y * sz.y, c.z + v.co.z * sz.z))
    if r > 0:
        r = min(r, min(sz) * 0.49)
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=r, offset_type='OFFSET', segments=seg,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    return bm


def box(mb, lo, hi, mat, r=0.0, seg=2, M=None):
    mb.merge(box_bm(lo, hi, r, seg), mat, M)


def lathe_bm(prof, seg=48, M=None):
    """prof [(r, h)] around local +Z; r=0 ends become poles."""
    bm = bmesh.new()
    rings = []
    for r, h in prof:
        if r < 1e-9:
            rings.append([bm.verts.new((0, 0, h))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * j / seg), r * math.sin(2 * math.pi * j / seg), h))
                          for j in range(seg)])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(seg):
            j2 = (j + 1) % seg
            try:
                if len(A) == 1:
                    bm.faces.new([A[0], B[j], B[j2]])
                elif len(B) == 1:
                    bm.faces.new([A[j], A[j2], B[0]])
                else:
                    bm.faces.new([A[j], A[j2], B[j2], B[j]])
            except ValueError:
                pass
    if M is not None:
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    return bm


def lathe(mb, prof, mat, M, seg=48):
    mb.merge(lathe_bm(prof, seg), mat, M)


def frame(o, z, xhint=None):
    z = V(z).normalized()
    x = V(xhint) if xhint is not None else z.orthogonal()
    x = (x - z * x.dot(z)).normalized()
    y = z.cross(x)
    o = V(o)
    return Matrix(((x.x, y.x, z.x, o.x), (x.y, y.y, z.y, o.y), (x.z, y.z, z.z, o.z), (0, 0, 0, 1)))


def loft_bm(rings, mis, closed_prof=True):
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    n, N = len(vr), len(vr[0])
    for i in range(n if closed_prof else n - 1):
        A, B = vr[i], vr[(i + 1) % n]
        for j in range(N):
            f = bm.faces.new((A[j], A[(j + 1) % N], B[(j + 1) % N], B[j]))
            f.material_index = mis[i] if isinstance(mis, (list, tuple)) else mis
    return bm


def rrect(w, h, r, n=4):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, -h / 2 + r, -math.pi / 2), (w / 2 - r, h / 2 - r, 0.0),
                       (-w / 2 + r, h / 2 - r, math.pi / 2), (-w / 2 + r, -h / 2 + r, math.pi)):
        for k in range(n + 1):
            a = a0 + math.pi / 2 * k / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def cr(ctrl, per=8):
    """Catmull-Rom through the control points."""
    P = [V(p) for p in ctrl]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2 = P[max(i - 1, 0)], P[i], P[i + 1]
        p3 = P[min(i + 2, len(P) - 1)]
        for k in range(per):
            t = k / per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return out


def resample(pts, step):
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    n = max(2, int(L[-1] / step) + 1)
    out, j = [], 0
    for k in range(n):
        s = L[-1] * k / (n - 1)
        while j < len(L) - 2 and L[j + 1] < s:
            j += 1
        t = (s - L[j]) / max(L[j + 1] - L[j], 1e-9)
        out.append(pts[j].lerp(pts[j + 1], t))
    return out


def transport(pts, n0):
    Ts = []
    for i in range(len(pts)):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        Ts.append((b - a).normalized())
    N = V(n0)
    N = (N - Ts[0] * N.dot(Ts[0])).normalized()
    fr = []
    for i, t in enumerate(Ts):
        N = (N - t * N.dot(t)).normalized()
        fr.append((t, N, t.cross(N)))
    return fr


def tube_bm(pts, r, sides=8, n0=None, caps=True):
    fr = transport(pts, n0 if n0 is not None else (pts[1] - pts[0]).orthogonal())
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new('UVMap')
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    rings = []
    for p, (t, N, B) in zip(pts, fr):
        rings.append([bm.verts.new(p + (N * math.cos(2 * math.pi * j / sides) + B * math.sin(2 * math.pi * j / sides)) * r)
                      for j in range(sides)])
    for i in range(len(pts) - 1):
        for j in range(sides):
            j2 = (j + 1) % sides
            f = bm.faces.new((rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]))
            for lp, (a, b) in zip(f.loops, ((L[i], j / sides), (L[i], (j + 1) / sides),
                                            (L[i + 1], (j + 1) / sides), (L[i + 1], j / sides))):
                lp[uv].uv = (a, b)
    if caps:
        for ring, p in ((rings[0], pts[0]), (rings[-1], pts[-1])):
            c = bm.verts.new(p)
            for j in range(sides):
                bm.faces.new((c, ring[j], ring[(j + 1) % sides]))
    return bm


def tube(mb, ctrl, r, mat, sides=8, per=8, step=0.004, n0=None):
    pts = resample(cr(ctrl, per), step)
    mb.merge(tube_bm(pts, r, sides, n0), mat)


def ribbon(mb, ctrl, nw, nt, pw, pt, r, w_axis, mat, sides=7, step=0.003, end_len=0.0):
    """Bundle of nw x nt parallel wires following a centreline (parallel-transported cross-section)."""
    pts = resample(cr(ctrl, 10), step)
    fr = transport(pts, w_axis)
    for a in range(nw):
        for b in range(nt):
            ow = (a - (nw - 1) / 2) * pw
            ot = (b - (nt - 1) / 2) * pt
            wp = [p + N * ow + B * ot for p, (t, N, B) in zip(pts, fr)]
            mb.merge(tube_bm(wp, r, sides, fr[0][1]), mat)
    return pts, fr


def tie(mb, pts, fr, f, w, t, mat='pc_tie'):
    """Cable tie around a ribbon at fraction f of its length (w x t outer size of the bundle)."""
    i = int(f * (len(pts) - 1))
    T_, N, B = fr[i]
    M = Matrix(((N.x, B.x, T_.x, pts[i].x), (N.y, B.y, T_.y, pts[i].y), (N.z, B.z, T_.z, pts[i].z), (0, 0, 0, 1)))
    ri = rrect(w + 0.001, t + 0.001, min(t / 2, 0.003), 3)
    ro = rrect(w + 0.0034, t + 0.0034, min(t / 2, 0.003) + 0.0012, 3)
    R = lambda pts2, z: [M @ V((p[0], p[1], z)) for p in pts2]
    mb.merge(loft_bm([R(ri, -0.0022), R(ro, -0.0022), R(ro, 0.0022), R(ri, 0.0022)], 0), mat)
    box(mb, (w / 2 + 0.0012, -0.0025, -0.0025), (w / 2 + 0.0052, 0.0025, 0.0025), mat, r=0.0006, seg=1, M=M)


def offset2d(pts, d):
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = V(pts[i - 1]), V(pts[i]), V(pts[(i + 1) % n])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = V((e0.y, -e0.x)), V((e1.y, -e1.x))
        m = (n0 + n1).normalized()
        out.append(p1 + m * (d / max(m.dot(n0), 0.3)))
    return out


def prism(mb, pts, M, z0, z1, mat, ch=0.0):
    """Extrude a CCW 2D outline (local XY of M) from z0 to z1, optional chamfer ch on both caps."""
    mb.merge(prism_bm(pts, z0, z1, ch), mat, M)


def prism_bm(pts, z0, z1, ch=0.0):
    pts = [V(p) for p in pts]
    inset = offset2d(pts, -ch) if ch else pts
    if ch:
        secs = [(z0, inset), (z0 + ch, pts), (z1 - ch, pts), (z1, inset)]
    else:
        secs = [(z0, pts), (z1, pts)]
    bm = bmesh.new()
    rings = [[bm.verts.new((p.x, p.y, z)) for p in ring] for z, ring in secs]
    N = len(pts)
    for i in range(len(rings) - 1):
        for j in range(N):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % N], rings[i + 1][(j + 1) % N], rings[i + 1][j]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    return bm


def star(n, r0, r1):
    return [((r0 if k % 2 == 0 else r1) * math.cos(math.pi * k / n), (r0 if k % 2 == 0 else r1) * math.sin(math.pi * k / n))
            for k in range(2 * n)]


def band(mb, ctrl, w, t, w_axis, mat, step=0.003, per=10):
    """Flat ribbon (w wide along the transported w_axis, t thick) swept along a smooth centreline."""
    pts = resample(cr(ctrl, per), step)
    fr = transport(pts, w_axis)
    bm = bmesh.new()
    prof = [(-w / 2, -t / 2), (w / 2, -t / 2), (w / 2, t / 2), (-w / 2, t / 2)]
    rings = [[bm.verts.new(p + N * a + B * b) for a, b in prof] for p, (tt, N, B) in zip(pts, fr)]
    for i in range(len(rings) - 1):
        for j in range(4):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % 4], rings[i + 1][(j + 1) % 4], rings[i + 1][j]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    mb.merge(bm, mat)


def thumbscrew(mb, p, axis, mat='pc_white_alu', r=0.0048, L=0.0055):
    """Knurled thumbscrew head standing on a surface at p, pointing along axis."""
    M = frame(p, axis)
    prism(mb, star(18, r, r - 0.00035), M, 0.0008, L, mat, ch=0.0003)
    lathe(mb, [(0.0, 0.0), (r * 0.8, 0.0), (r * 0.8, 0.0009), (0.0, 0.0009)], mat, M, seg=20)
    lathe(mb, [(0.0, L), (r * 0.55, L), (r * 0.5, L + 0.0004), (0.0, L + 0.0004)], mat, M, seg=20)


def rsq(dx, dy, h, r):
    lo, hi = 0.0, h * 1.6
    for _ in range(40):
        t = (lo + hi) / 2
        qx, qy = abs(dx * t) - (h - r), abs(dy * t) - (h - r)
        dist = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
        if dist < 0:
            lo = t
        else:
            hi = t
    return lo


# ---------------------------------------------------------------------------- fans
def rotor(mb, M, r0, r1, z0, z1, nbl, blade_mat, hub_mat, cap_mat=None, nr=6, ns=6, sweep=18, thick=0.0011):
    """Hub (z0..z1 along local +Z, +Z = visible face) + nbl pitched, swept blades between r0 and r1."""
    zc = (z0 + z1) / 2
    hub = [(0.0, z0), (r0 - 0.0004, z0), (r0, z0 + 0.0006), (r0, z1 - 0.0022), (r0 - 0.0005, z1 - 0.0006),
           (r0 - 0.0018, z1), (r0 * 0.62, z1)]
    lathe(mb, hub, hub_mat, M, seg=40)
    lathe(mb, [(r0 * 0.62, z1), (r0 * 0.6, z1 + 0.0003), (0.0, z1 + 0.0004)], cap_mat or hub_mat, M, seg=40)
    # hub cap trim ring + centre dimple (no logo)
    lathe(mb, [(r0 * 0.66, z1 - 0.0001), (r0 * 0.66, z1 + 0.0005), (r0 * 0.74, z1 + 0.0005), (r0 * 0.74, z1 - 0.0001)],
          'pc_gpu_accent' if cap_mat else 'pc_white_alu', M, seg=40)
    lathe(mb, [(0.0026, z1 + 0.0004), (0.0020, z1 + 0.0001), (0.0, z1 + 0.0001)], hub_mat, M, seg=20)
    depth = (z1 - z0)
    for bi in range(nbl):
        phi = 2 * math.pi * bi / nbl
        grid = []
        for i in range(nr + 1):
            t = i / nr
            r = r0 - 0.0006 + (r1 - r0 + 0.0006) * t
            span = (2 * math.pi / nbl) * 0.92 * (0.72 + 0.36 * t)
            sw = math.radians(sweep) * t * t
            hgt = depth * (0.86 - 0.30 * t)
            row = []
            for j in range(ns + 1):
                s = j / ns
                th = phi + sw + (s - 0.5) * span
                z = zc + (0.5 - s) * hgt + 0.10 * hgt * math.sin(math.pi * s)
                row.append(V((r * math.cos(th), r * math.sin(th), z)))
            grid.append(row)
        bm = bmesh.new()
        A, B = [], []
        for i in range(nr + 1):
            ra, rb = [], []
            for j in range(ns + 1):
                di = grid[min(i + 1, nr)][j] - grid[max(i - 1, 0)][j]
                dj = grid[i][min(j + 1, ns)] - grid[i][max(j - 1, 0)]
                n = di.cross(dj).normalized()
                taper = thick * (0.55 if j in (0, ns) else 1.0) * (0.7 if i == nr else 1.0)
                ra.append(bm.verts.new(grid[i][j] + n * taper / 2))
                rb.append(bm.verts.new(grid[i][j] - n * taper / 2))
            A.append(ra)
            B.append(rb)
        for i in range(nr):
            for j in range(ns):
                bm.faces.new((A[i][j], A[i + 1][j], A[i + 1][j + 1], A[i][j + 1]))
                bm.faces.new((B[i][j], B[i][j + 1], B[i + 1][j + 1], B[i + 1][j]))
        for i in range(nr):
            for j in (0, ns):
                bm.faces.new((A[i][j], B[i][j], B[i + 1][j], A[i + 1][j]))
        for j in range(ns):
            for i in (0, nr):
                bm.faces.new((A[i][j], A[i][j + 1], B[i][j + 1], B[i][j]))
        mb.merge(bm, blade_mat, M)


def case_fan(mbF, mbR, M, size=0.120, depth=0.025):
    """120 mm fan, local +Z = the visible (intake/show) face; struts and motor on the -Z face."""
    h = size / 2
    Ri = 0.0585
    N = 72
    e, ch = 0.0018, 0.0012
    dirs = [(math.cos(2 * math.pi * (k + 0.5) / N), math.sin(2 * math.pi * (k + 0.5) / N)) for k in range(N)]
    tO = [rsq(dx, dy, h, 0.010) for dx, dy in dirs]
    d2 = depth / 2

    def ring(rad_fn, z):
        return [M @ V((dx * rad_fn(k), dy * rad_fn(k), z)) for k, (dx, dy) in enumerate(dirs)]
    I = lambda off: (lambda k: Ri + off)
    O = lambda off: (lambda k: tO[k] - off)
    Wt, LED = mbF.i('pc_white_plastic'), mbF.i('pc_rgb_led')
    prof = [(I(0), -d2 + ch), (I(ch), -d2), (I(0.0056), -d2), (O(e), -d2), (O(0), -d2 + e), (O(0), d2 - e),
            (O(e), d2), (I(0.0056), d2), (I(ch), d2), (I(0), d2 - ch), (I(0), 0.0050), (I(0), -0.0050)]
    mis = [Wt, Wt, Wt, Wt, Wt, Wt, Wt, Wt, Wt, Wt, LED, Wt]
    rings = [ring(f, z) for f, z in prof]
    mbF.merge(loft_bm(rings, mis))
    # frosted diffuser rings standing proud of both faces around the opening
    for sz in (-1, 1):
        lathe(mbF, [(Ri + 0.0009, 0.0), (Ri + 0.0009, 0.0006), (Ri + 0.0020, 0.0011), (Ri + 0.0042, 0.0011),
                    (Ri + 0.0052, 0.0005), (Ri + 0.0052, 0.0)], 'pc_rgb_diffuser',
              M @ frame((0, 0, sz * d2), (0, 0, sz), (1, 0, 0)), seg=64)
    # anti-vibration rubber corner pads (L-shaped wrap over the corner) with the screw hole, both faces
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                Mc = M @ Matrix.Translation((sx * (h - 0.0071), sy * (h - 0.0071), sz * d2))
                box(mbF, (-0.0071, -0.0071, -0.0004 if sz > 0 else -0.0008), (0.0071, 0.0071, 0.0008 if sz > 0 else 0.0004),
                    'pc_white_rubber', r=0.0025, seg=1, M=Mc)
                lathe(mbF, [(0.0, 0.0), (0.0021, 0.0), (0.0021, 0.0002), (0.0, 0.0002)], 'pc_port_dark',
                      Mc @ frame((0, 0, sz * 0.00085), (0, 0, sz)), seg=12)
    # daisy-chain connector nub on the +Y edge
    box(mbF, (-0.011, h - 0.0005, -0.006), (0.011, h + 0.0028, 0.006), 'pc_white_plastic', r=0.0008, seg=1, M=M)
    box(mbF, (-0.008, h + 0.0027, -0.0035), (0.008, h + 0.0031, 0.0035), 'pc_port_dark', M=M)
    # motor stator + 4 struts on the -Z face
    lathe(mbF, [(0.0, -d2), (0.021, -d2), (0.0212, -d2 + 0.0015), (0.020, -d2 + 0.004), (0.0, -d2 + 0.004)],
          'pc_white_plastic', M, seg=40)
    for k in range(4):
        a = math.radians(45 + 90 * k + 8)
        Mr = M @ Matrix.Rotation(a, 4, 'Z')
        box(mbF, (0.019, -0.002, -d2), (Ri + 0.001, 0.002, -d2 + 0.0035), 'pc_white_plastic', r=0.0008, seg=1, M=Mr)
    rotor(mbR, M, 0.0205, 0.0562, -d2 + 0.0045, d2 - 0.0015, 7, 'pc_fan_blade', 'pc_white_plastic', nr=6, ns=7, sweep=26)


# ============================================================================== build
def boolean_apply(o, cutters, mode='DIFFERENCE'):
    for c in cutters:
        m = o.modifiers.new('b', 'BOOLEAN')
        m.operation = mode
        m.object = c
        m.solver = 'EXACT'
        try:
            m.material_mode = 'TRANSFER'
        except (AttributeError, TypeError):
            pass
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = o.data
    o.modifiers.clear()
    o.data = me
    me.name = o.name
    bpy.data.meshes.remove(old)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(30))    # keep cut n-gons flat-shaded
    for c in cutters:
        bpy.data.objects.remove(c, do_unlink=True)


def cutter(coll, bm, mat=None):
    me = bpy.data.meshes.new('cut')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    if mat:
        me.materials.append(MAT[mat])
    o = bpy.data.objects.new('cut', me)
    coll.objects.link(o)
    o.matrix_world = T          # cutters are built in case-local coords like the parts (parented to the root)
    o.display_type = 'WIRE'
    return o


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    make_materials()
    coll = bpy.data.collections.new('NEW_pc')
    scene.collection.children.link(coll)
    root = bpy.data.objects.new('NEW_pc_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.1
    root.matrix_world = T
    coll.objects.link(root)
    objs = []

    def done(mb, ang=35):
        o = mb.build(coll, root, ang)
        objs.append(o)
        return o

    # ------------------------------------------------------------------ chassis
    Z0, Z1 = 0.034, 0.440                  # inside floor / underside of the top frame
    mb = MB('pc_case_base', ['pc_white_alu'])
    box(mb, (-HW, -HD, 0.010), (HW, HD, Z0), 'pc_white_alu', r=0.004, seg=3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            Mft = Matrix.Translation((sx * (HW - 0.035), sy * (HD - 0.045), 0.0))
            # moulded white foot with a dark rubber pad pressed into its sole
            lathe(mb, [(0.0165, 0.0022), (0.0180, 0.0030), (0.0190, 0.0045), (0.0192, 0.0080), (0.0200, 0.0100),
                       (0.0210, 0.0106), (0.0, 0.0106)], 'pc_white_alu', Mft, seg=40)
            lathe(mb, [(0.0, 0.0), (0.0150, 0.0), (0.0162, 0.0006), (0.0167, 0.0022), (0.0165, 0.0030), (0.0, 0.0030)],
                  'pc_rubber_dark', Mft, seg=40)
    # slide-out bottom dust filter: seam + finger notch on the base front, fine mesh under the bottom fans
    box(mb, (-HW + 0.010, -HD - 0.0003, 0.0205), (HW - 0.010, -HD + 0.0006, 0.0212), 'pc_port_dark')
    box(mb, (-0.022, -HD - 0.0004, 0.0135), (0.022, -HD + 0.0015, 0.0205), 'pc_white_rubber', r=0.0015, seg=2)
    box(mb, (-0.103, -HD + 0.014, Z0 - 0.0006), (0.014, HD - 0.014, Z0 + 0.0002), 'pc_filter_mesh')
    for uu in (-0.1035, 0.0135):
        box(mb, (uu - 0.0008, -HD + 0.014, Z0 - 0.0006), (uu + 0.0008, HD - 0.014, Z0 + 0.0008), 'pc_white_plastic')
    # interior floor: raised fan-mount rails either side of the bottom fans
    box(mb, (-0.110, -HD + 0.012, Z0 - 0.001), (-0.104, HD - 0.012, Z0 + 0.003), 'pc_white_steel', r=0.001, seg=1)
    box(mb, (0.015, -HD + 0.012, Z0 - 0.001), (0.021, HD - 0.012, Z0 + 0.003), 'pc_white_steel', r=0.001, seg=1)
    done(mb)

    # top frame with the mesh opening over the radiator
    mb = MB('pc_case_top', ['pc_white_alu'])
    box(mb, (-HW, -HD, Z1), (HW, HD, H), 'pc_white_alu', r=0.004, seg=3)
    top = done(mb)
    ccut = cutter(coll, box_bm((-0.142, -0.222, Z1 - 0.01), (0.045, 0.222, H + 0.01), r=0.004, seg=2), 'pc_white_alu')
    boolean_apply(top, [ccut])
    mb = MB('pc_case_top_mesh', ['pc_perforated'])
    box(mb, (-0.1425, -0.2225, H - 0.0045), (0.0455, 0.2225, H - 0.0030), 'pc_perforated')
    # magnetic filter frame lip around the mesh + fine filter sheet under it
    for a, b_ in (((-0.1425, -0.2225), (0.0455, -0.2185)), ((-0.1425, 0.2185), (0.0455, 0.2225)),
                  ((-0.1425, -0.2185), (-0.1385, 0.2185)), ((0.0415, -0.2185), (0.0455, 0.2185))):
        box(mb, (a[0], a[1], H - 0.0046), (b_[0], b_[1], H - 0.0022), 'pc_white_alu', r=0.0005, seg=1)
    box(mb, (-0.1400, -0.2200, H - 0.0062), (0.0430, 0.2200, H - 0.0056), 'pc_filter_mesh')
    done(mb, 20)
    # top I/O module on the solid right strip: recessed panel cut into the top frame with a power button
    # (LED ring), reset, USB-C, 2x USB-A, combo audio jack and an activity LED
    bx = 0.098
    HP = H - 0.0006                              # floor of the recessed I/O panel
    VB, VR, VC, VA, VJ = -0.2000, -0.1865, -0.1765, (-0.1640, -0.1500), -0.1360
    Tl = lambda v_, z_=0.0: Matrix.Translation((bx, v_, z_))
    cuts = [cutter(coll, prism_bm(rrect(0.0236, 0.1080, 0.0040, 5), HP, H + 0.01), 'pc_white_alu'),
            cutter(coll, lathe_bm([(0.0, HP - 0.0030), (0.0086, HP - 0.0030), (0.0086, H + 0.01), (0.0, H + 0.01)], 48), 'pc_port_dark'),
            cutter(coll, lathe_bm([(0.0, HP - 0.0020), (0.0033, HP - 0.0020), (0.0033, H + 0.01), (0.0, H + 0.01)], 24), 'pc_port_dark'),
            cutter(coll, prism_bm(rrect(0.0090, 0.0032, 0.0015, 5), HP - 0.0070, H + 0.01), 'pc_metal'),
            cutter(coll, lathe_bm([(0.0, HP - 0.0090), (0.0019, HP - 0.0090), (0.0019, H + 0.01), (0.0, H + 0.01)], 20), 'pc_metal')]
    for c, (v_) in zip(cuts, (-0.160, VB, VR, VC, VJ)):
        c.matrix_world = T @ Tl(v_)
    for vy in VA:
        c = cutter(coll, box_bm((-0.0064, -0.0024, HP - 0.0085), (0.0064, 0.0024, H + 0.01)), 'pc_metal')
        c.matrix_world = T @ Tl(vy)
        cuts.append(c)
    boolean_apply(top, cuts)
    mb = MB('pc_case_top_io', ['pc_white_alu'])
    # power button: cap with a light-pipe LED ring in its recess
    lathe(mb, [(0.0074, HP - 0.0030), (0.0082, HP - 0.0030), (0.0082, HP - 0.0003), (0.0074, HP - 0.0003)], 'pc_led_white',
          Tl(VB), seg=48)
    lathe(mb, [(0.0, HP - 0.0030), (0.0069, HP - 0.0030), (0.0069, HP + 0.0004), (0.0066, HP + 0.0010), (0.0056, HP + 0.0013),
               (0.0, HP + 0.0013)], 'pc_white_alu', Tl(VB), seg=48)
    lathe(mb, [(0.0022, HP + 0.00125), (0.0026, HP + 0.00140), (0.0022, HP + 0.00150), (0.0, HP + 0.0015)], 'pc_white_pcb', Tl(VB), seg=24)
    # reset button
    lathe(mb, [(0.0, HP - 0.0020), (0.0028, HP - 0.0020), (0.0028, HP - 0.0003), (0.0024, HP), (0.0, HP)], 'pc_white_alu',
          Tl(VR), seg=24)
    lathe(mb, [(0.0, HP + 0.00005), (0.0010, HP + 0.00005), (0.0010, HP + 0.0002), (0.0, HP + 0.0002)], 'pc_led_white',
          Tl(VR + 0.0000, 0) @ Matrix.Translation((0.0070, 0, 0)), seg=12)
    # USB-C: nickel lining, dark floor, tongue
    Mc = Tl(VC)
    ri, ro = rrect(0.0084, 0.0026, 0.0012, 5), rrect(0.0090, 0.0032, 0.0015, 5)
    R = lambda pts, z: [Mc @ V((p[0], p[1], z)) for p in pts]
    mb.merge(loft_bm([R(ri, HP - 0.0068), R(ri, HP), R(ro, HP), R(ro, HP - 0.0068)], 0), 'pc_metal')
    prism(mb, ro, Mc, HP - 0.0070, HP - 0.0068, 'pc_port_dark')
    box(mb, (-0.0033, -0.0003, HP - 0.0068), (0.0033, 0.0003, HP - 0.0012), 'pc_port_dark', M=Mc)
    # 2x USB-A: metal lining with spring tabs, dark floor, blue tongue on one side
    for vy in VA:
        Ma = Tl(vy)
        ri, ro = rrect(0.0122, 0.0044, 0.0002, 1), rrect(0.0128, 0.0048, 0.0002, 1)
        R = lambda pts, z, M_=Ma: [M_ @ V((p[0], p[1], z)) for p in pts]
        mb.merge(loft_bm([R(ri, HP - 0.0083), R(ri, HP), R(ro, HP), R(ro, HP - 0.0083)], 0), 'pc_metal')
        box(mb, (-0.0064, -0.0024, HP - 0.0085), (0.0064, 0.0024, HP - 0.0083), 'pc_port_dark', M=Ma)
        box(mb, (-0.0055, -0.0021, HP - 0.0083), (0.0055, -0.0003, HP - 0.0012), 'pc_gpu_blue', M=Ma)
        for sx in (-0.0035, 0.0035):
            box(mb, (sx - 0.0008, 0.0019, HP - 0.0030), (sx + 0.0008, 0.0022, HP - 0.0010), 'pc_metal', M=Ma)
    # combo audio jack: nickel ring, dark bore
    Mj = Tl(VJ)
    lathe(mb, [(0.0019, HP - 0.0088), (0.0019, HP), (0.0031, HP + 0.0002), (0.0034, HP), (0.0034, HP - 0.0003)],
          'pc_metal', Mj, seg=24)
    lathe(mb, [(0.0, HP - 0.0089), (0.0019, HP - 0.0089), (0.0019, HP - 0.0087), (0.0, HP - 0.0087)], 'pc_port_dark', Mj, seg=16)
    # activity LED
    lathe(mb, [(0.0, HP), (0.0011, HP), (0.0011, HP + 0.0002), (0.0, HP + 0.0002)], 'pc_led_white', Tl(-0.1240), seg=12)
    # rear thumbscrews of the top frame
    for uu in (-0.100, 0.100):
        thumbscrew(mb, (uu, HD, (Z1 + H) / 2), (0, 1, 0))
    done(mb)

    # glass: side (-u) and front (-v), pillarless front-left corner, 4 mm with arrised edges
    GZ0, GZ1 = Z0 + 0.0008, Z1 - 0.0012
    mb = MB('pc_glass_panels', ['pc_glass'])
    box(mb, (-HW, -HD, GZ0), (-HW + 0.004, HD - 0.012, GZ1), 'pc_glass', r=0.0007, seg=1)
    box(mb, (-HW + 0.0042, -HD, GZ0), (HW, -HD + 0.004, GZ1), 'pc_glass', r=0.0007, seg=1)
    mb.i('pc_glass_edge')
    gl = done(mb, 30)
    for p in gl.data.polygons:          # edge faces of the panes get the green-tinted edge glass
        side = p.center.x < -HW + 0.0045
        if (side and abs(p.normal.x) < 0.9) or (not side and abs(p.normal.y) < 0.9):
            p.material_index = 1
    # addressable RGB strips hidden behind the top rail / along the floor edge (spill light down the glass)
    mb = MB('pc_case_led_strips', ['pc_rgb_strip'])
    box(mb, (-HW + 0.006, -HD + 0.010, Z1 - 0.0045), (-HW + 0.011, HD - 0.016, Z1 - 0.0005), 'pc_rgb_strip', r=0.0008, seg=1)
    box(mb, (-HW + 0.012, -HD + 0.006, Z1 - 0.0045), (0.050, -HD + 0.011, Z1 - 0.0005), 'pc_rgb_strip', r=0.0008, seg=1)
    box(mb, (-HW + 0.006, -HD + 0.010, Z0 + 0.0008), (-HW + 0.011, HD - 0.016, Z0 + 0.0040), 'pc_rgb_strip', r=0.0008, seg=1)
    done(mb)
    # rear-left post + glass clips (the side glass hangs on it), right side panel, rear-chamber front cover
    mb = MB('pc_case_frame', ['pc_white_alu'])
    box(mb, (-HW, HD - 0.0118, Z0), (-HW + 0.012, HD, Z1), 'pc_white_alu', r=0.0025, seg=2)
    for zz in (0.12, 0.36):
        box(mb, (-HW + 0.0041, HD - 0.030, zz - 0.012), (-HW + 0.006, HD - 0.011, zz + 0.012), 'pc_white_rubber', r=0.001, seg=1)
    box(mb, (HW - 0.004, -HD + 0.0042, Z0 + 0.0008), (HW, HD - 0.0008, Z1 - 0.0008), 'pc_white_steel', r=0.0012, seg=1)
    # panel seams: hairline dark gaps where the right panel meets the top frame, base and rear
    box(mb, (HW - 0.0045, -HD + 0.004, Z1 - 0.0008), (HW - 0.0002, HD - 0.0002, Z1), 'pc_port_dark')
    box(mb, (HW - 0.0045, -HD + 0.004, Z0), (HW - 0.0002, HD - 0.0002, Z0 + 0.0008), 'pc_port_dark')
    box(mb, (HW - 0.0045, HD - 0.0008, Z0), (HW - 0.0002, HD - 0.0002, Z1), 'pc_port_dark')
    # rear chamber front: solid PSU-shroud skirt below, perforated cover above (cables hinted behind)
    box(mb, (0.0605, -HD + 0.0045, Z0), (HW - 0.004, -HD + 0.0075, 0.190), 'pc_white_steel', r=0.0008, seg=1)
    box(mb, (0.0605, -HD + 0.0045, 0.190), (0.0645, -HD + 0.0075, Z1), 'pc_white_steel', r=0.0006, seg=1)
    box(mb, (HW - 0.008, -HD + 0.0045, 0.190), (HW - 0.004, -HD + 0.0075, Z1), 'pc_white_steel', r=0.0006, seg=1)
    box(mb, (0.0645, -HD + 0.0050, 0.190), (HW - 0.008, -HD + 0.0065, Z1), 'pc_perforated_uz')
    # PSU shroud top inside the rear chamber (open toward the PSU so the cables drop in)
    box(mb, (0.0605, -HD + 0.0075, 0.1880), (HW - 0.004, 0.030, 0.1905), 'pc_white_steel', r=0.0006, seg=1)
    # rear thumbscrews for the right panel
    for zz in (0.110, 0.370):
        thumbscrew(mb, (HW - 0.010, HD, zz), (0, 1, 0))
    done(mb)

    # rear panel with cut-outs: rear fan, board I/O, GPU bracket, PSU
    mb = MB('pc_case_rear', ['pc_white_steel'])
    box(mb, (-HW + 0.012, HD - 0.003, Z0), (HW - 0.004, HD, Z1), 'pc_white_steel', r=0.0008, seg=1)
    rear = done(mb)
    FAN_R = (-0.048, 0.325)
    cuts = [cutter(coll, lathe_bm([(0.0, -0.01), (0.0575, -0.01), (0.0575, 0.01), (0.0, 0.01)], 64,
                                  frame((FAN_R[0], HD - 0.0015, FAN_R[1]), (0, 1, 0))), 'pc_white_steel'),
            cutter(coll, box_bm((0.019, HD - 0.01, 0.259), (0.050, HD + 0.01, 0.417)), 'pc_white_steel'),
            cutter(coll, box_bm((-0.133, HD - 0.01, 0.097), (-0.065, HD + 0.01, 0.256)), 'pc_white_steel'),
            cutter(coll, box_bm((0.063, HD - 0.01, 0.036), (0.146, HD + 0.01, 0.186)), 'pc_white_steel')]
    boolean_apply(rear, cuts)
    # rear fan guard: thin concentric wire rings + spokes
    mb = MB('pc_rear_guard', ['pc_white_steel'])
    gm = frame((FAN_R[0], HD - 0.0005, FAN_R[1]), (0, 1, 0))
    for rr in (0.018, 0.032, 0.046, 0.057):
        lathe(mb, [(rr - 0.0009, -0.0006), (rr + 0.0009, -0.0006), (rr + 0.0009, 0.0006), (rr - 0.0009, 0.0006)],
              'pc_white_steel', gm, seg=56)
    for k in range(4):
        box(mb, (-0.0008, 0.018, -0.0006), (0.0008, 0.0575, 0.0006), 'pc_white_steel',
            M=gm @ Matrix.Rotation(math.radians(45 + 90 * k), 4, 'Z'))
    done(mb)
    mb = MB('pc_rear_slots', ['pc_white_steel'])
    for k in range(7):
        z0 = 0.104 + k * 0.0203
        box(mb, (-0.060, HD - 0.0004, z0), (0.016, HD + 0.0010, z0 + 0.0180), 'pc_white_steel', r=0.0004, seg=1)
        for j in range(6):
            uu = -0.052 + j * 0.0105
            box(mb, (uu, HD + 0.0006, z0 + 0.0060), (uu + 0.0070, HD + 0.0012, z0 + 0.0120), 'pc_port_dark', r=0.0003, seg=1)
    box(mb, (0.016, HD - 0.0004, 0.100), (0.030, HD + 0.0022, 0.250), 'pc_white_steel', r=0.001, seg=1)
    thumbscrew(mb, (0.023, HD + 0.0022, 0.236), (0, 1, 0), r=0.0042, L=0.005)
    for k in range(4):
        thumbscrew(mb, (-0.128 + (k % 2) * 0.058, HD + 0.0012, 0.104 + (k // 2) * 0.146), (0, 1, 0), mat='pc_metal',
                   r=0.0026, L=0.0022)
    done(mb)

    # motherboard tray with grommet openings
    TU0, TU1 = 0.058, 0.0605
    mb = MB('pc_mb_tray', ['pc_white_steel'])
    box(mb, (TU0, -HD + 0.0075, Z0), (TU1, HD - 0.003, Z1), 'pc_white_steel', r=0.0006, seg=1)
    tray = done(mb)
    holes = [(-0.076, -0.040, 0.285, 0.380), (-0.082, -0.046, 0.200, 0.268), (0.090, 0.152, 0.4295, 0.4385),
             (-0.090, 0.090, 0.068, 0.098)]
    boolean_apply(tray, [cutter(coll, box_bm((TU0 - 0.01, a, c), (TU1 + 0.01, b, d), r=0.003, seg=2), 'pc_white_steel')
                         for a, b, c, d in holes])
    mb = MB('pc_mb_grommets', ['pc_white_rubber'])
    for a, b, c, d in holes[:2] + holes[3:]:
        w, h = b - a, d - c
        inner = rrect(w - 0.001, h - 0.001, 0.0035, 4)
        outer = rrect(w + 0.007, h + 0.007, 0.0065, 4)
        cy, cz = (a + b) / 2, (c + d) / 2
        P = lambda pts, u: [V((u, cy + p[0], cz + p[1])) for p in pts]
        mb.merge(loft_bm([P(inner, TU0 - 0.0012), P(outer, TU0 - 0.0012), P(outer, TU0 + 0.0003),
                          P(inner, TU1 + 0.0010)], 0))
        # split rubber flaps (slit down the middle) seen as a dark line
        box(mb, (TU0 + 0.0004, a + 0.001, cz - 0.0004), (TU1 - 0.0002, b - 0.001, cz + 0.0004), 'pc_port_dark')
    done(mb)

    # ------------------------------------------------------------------ PSU (rear chamber) + inlet
    mb = MB('pc_psu', ['pc_psu'])
    box(mb, (0.064, 0.068, 0.036), (0.146, HD - 0.004, 0.185), 'pc_psu', r=0.003, seg=2)
    box(mb, (0.066, HD - 0.0045, 0.040), (0.144, HD - 0.0005, 0.181), 'pc_heatsink', r=0.001, seg=1)
    for k in range(12):
        zz = 0.100 + k * 0.0065
        box(mb, (0.070, HD - 0.0006, zz), (0.140, HD + 0.0001, zz + 0.0035), 'pc_port_dark')
    box(mb, (0.0895, HD - 0.001, 0.0585), (0.1205, HD + 0.004, 0.0835), 'pc_plug_black', r=0.0015, seg=2)
    box(mb, (0.126, HD - 0.001, 0.062), (0.136, HD + 0.003, 0.080), 'pc_plug_black', r=0.001, seg=1)
    for uu, zz in ((0.069, 0.043), (0.141, 0.043), (0.069, 0.178), (0.141, 0.178)):
        lathe(mb, [(0.0, 0.0), (0.0024, 0.0), (0.0024, 0.0008), (0.0016, 0.0013), (0.0, 0.0013)], 'pc_metal',
              frame((uu, HD, zz), (0, 1, 0)), seg=16)
    for zz, w in ((0.160, 0.024), (0.130, 0.018), (0.100, 0.018), (0.070, 0.018)):
        box(mb, (0.080, 0.0665, zz - 0.006), (0.080 + w, 0.0685, zz + 0.006), 'pc_port_dark', r=0.0005, seg=1)
    done(mb)

    # ------------------------------------------------------------------ motherboard (white)
    BU = 0.052                              # board front surface (components grow toward -u)
    BV0, BV1, BZ0, BZ1 = -0.030, 0.214, 0.123, 0.428
    mb = MB('pc_mb', ['pc_white_pcb'])
    box(mb, (BU, BV0, BZ0), (BU + 0.0016, BV1, BZ1), 'pc_white_pcb', r=0.0006, seg=1)
    # rear I/O shroud with an integrated VRM heatsink, stepped profile + groove
    box(mb, (0.016, 0.168, 0.252), (BU, BV1 - 0.001, 0.420), 'pc_white_alu', r=0.004, seg=3)
    box(mb, (0.0145, 0.176, 0.262), (0.0165, 0.178, 0.412), 'pc_heatsink')
    box(mb, (0.022, 0.150, 0.252), (BU, 0.168, 0.300), 'pc_white_alu', r=0.003, seg=2)
    # top VRM heatsink with fins
    box(mb, (0.030, 0.056, 0.384), (BU, 0.166, 0.411), 'pc_white_alu', r=0.002, seg=2)
    for k in range(6):
        vv = 0.060 + k * 0.0185
        box(mb, (0.021, vv, 0.386), (0.031, vv + 0.013, 0.409), 'pc_white_alu', r=0.0015, seg=2)
    # EPS 8-pin headers
    for v0 in (0.100, 0.124):
        box(mb, (0.038, v0, 0.413), (BU, v0 + 0.020, 0.427), 'pc_white_plastic', r=0.001, seg=1)
    # socket retention plate (peeks out around the pump)
    box(mb, (0.046, 0.070, 0.296), (BU, 0.152, 0.380), 'pc_metal', r=0.002, seg=2)
    # DIMM slots with latches; modules: PCB sandwiched by two stepped heatspreader halves with a
    # chevron accent, frosted RGB diffuser bar with white end caps
    for vc in (0.045, 0.0355, 0.024, 0.0145):
        box(mb, (0.045, vc - 0.0033, 0.276), (BU, vc + 0.0033, 0.420), 'pc_white_plastic', r=0.0006, seg=1)
        for zz in (0.2745, 0.4195):
            box(mb, (0.043, vc - 0.0036, zz - 0.0035), (BU, vc + 0.0036, zz + 0.0035), 'pc_white_plastic', r=0.0008, seg=1)
        box(mb, (0.0095, vc - 0.0006, 0.2775), (0.0460, vc + 0.0006, 0.4185), 'pc_gpu_pcb')
        for sg in (1, -1):
            ol = [(0.0455, 0.0007), (0.0455, 0.0033), (0.0215, 0.0033), (0.0175, 0.0040), (0.0092, 0.0040), (0.0092, 0.0007)]
            pts = [(u_, vc + sg * w_) for u_, w_ in ol]
            prism(mb, pts if sg > 0 else pts[::-1], I4, 0.2805, 0.4155, 'pc_white_alu', ch=0.0004)
            Mfc = frame((0.0, vc + sg * 0.00332, 0.0), (0, sg, 0), (1, 0, 0))
            for z0 in (0.300, 0.318):
                pv = [(0.0400, z0), (0.0440, z0), (0.0290, z0 + 0.030), (0.0250, z0 + 0.030)]
                prism(mb, [(u_, -sg * z_) for u_, z_ in pv], Mfc, 0.0, 0.00025, 'pc_gpu_accent')
            box(mb, (0.0240, vc + sg * 0.0033 - 0.0001, 0.360), (0.0400, vc + sg * 0.0033 + 0.0001, 0.404), 'pc_white_pcb')
        box(mb, (0.0012, vc - 0.0029, 0.2830), (0.0094, vc + 0.0029, 0.4130), 'pc_rgb_diffuser', r=0.0012, seg=2)
        for z0, z1 in ((0.2800, 0.2832), (0.4128, 0.4160)):
            box(mb, (0.0008, vc - 0.0034, z0), (0.0096, vc + 0.0034, z1), 'pc_white_plastic', r=0.0008, seg=1)
    # 24-pin header + plug
    box(mb, (0.040, -0.028, 0.298), (BU, -0.014, 0.356), 'pc_white_plastic', r=0.001, seg=1)
    box(mb, (0.0405, -0.040, 0.2995), (0.0525, -0.027, 0.3545), 'pc_white_plastic', r=0.0012, seg=1)
    box(mb, (0.0415, -0.047, 0.300), (0.0515, -0.044, 0.354), 'pc_white_plastic', r=0.0008, seg=1)      # cable comb
    # PCIe x16 slots with armour, M.2 covers, chipset heatsink, small headers
    for zz in (0.226, 0.152):
        box(mb, (0.043, 0.060, zz), (BU, 0.203, zz + 0.0085), 'pc_white_alu', r=0.001, seg=1)
        box(mb, (0.0425, 0.060, zz + 0.0028), (0.0432, 0.203, zz + 0.0057), 'pc_heatsink')
    box(mb, (0.045, 0.028, 0.243), (BU, 0.168, 0.270), 'pc_white_alu', r=0.002, seg=2)
    box(mb, (0.0445, 0.040, 0.2555), (0.0452, 0.156, 0.2575), 'pc_heatsink')
    box(mb, (0.045, 0.020, 0.168), (BU, 0.140, 0.193), 'pc_white_alu', r=0.002, seg=2)
    box(mb, (0.040, -0.026, 0.132), (BU, 0.044, 0.214), 'pc_white_alu', r=0.004, seg=3)
    for k in range(5):
        zz = 0.140 + k * 0.014
        box(mb, (0.0392, -0.020, zz), (0.0405, 0.038, zz + 0.004), 'pc_white_pcb', r=0.0005, seg=1)
    for k, vv in enumerate((0.00, 0.03, 0.06, 0.09, 0.12, 0.15)):
        box(mb, (0.046, vv, 0.125), (BU, vv + 0.018, 0.131), 'pc_dark_plastic')
    # extra board detail: I/O-shroud slits, second M.2 fins, screws, x1 slot, slot latches, chipset chevron
    for k in range(8):
        zz = 0.300 + k * 0.0135
        box(mb, (0.0152, 0.174, zz), (0.0164, 0.208, zz + 0.0055), 'pc_heatsink', r=0.0004, seg=1)
    for zz in (0.2490, 0.2620):
        box(mb, (0.0445, 0.036, zz), (0.0452, 0.160, zz + 0.0012), 'pc_heatsink')
    for zz in (0.1740, 0.1860):
        box(mb, (0.0445, 0.028, zz), (0.0452, 0.132, zz + 0.0012), 'pc_heatsink')
    for vv, zz in ((0.032, 0.2565), (0.164, 0.2565), (0.024, 0.1805), (0.136, 0.1805), (-0.024, 0.422), (-0.024, 0.270),
                   (-0.024, 0.128), (0.207, 0.128)):
        uu = BU if vv < 0 or zz < 0.13 else 0.045
        lathe(mb, [(0.0, 0.0), (0.0026, 0.0), (0.0026, 0.0006), (0.0018, 0.0012), (0.0, 0.0013)], 'pc_metal',
              frame((uu, vv, zz), (-1, 0, 0)), seg=16)
    box(mb, (0.046, 0.160, 0.2005), (BU, 0.188, 0.2065), 'pc_white_plastic', r=0.0006, seg=1)
    box(mb, (0.0455, 0.162, 0.2025), (0.0462, 0.186, 0.2045), 'pc_port_dark')
    for zz in (0.226, 0.152):
        box(mb, (0.0435, 0.051, zz - 0.0006), (BU, 0.060, zz + 0.0091), 'pc_white_plastic', r=0.0008, seg=1)
    Mch = frame((0.0398, 0.0, 0.0), (-1, 0, 0), (0, 1, 0))
    for dz in (0.0, 0.010):
        pv = [(-0.016, 0.205 - dz), (-0.010, 0.205 - dz), (0.018, 0.176 - dz), (0.012, 0.176 - dz)]
        prism(mb, [(v_, -z_) for v_, z_ in pv], Mch, 0.0, 0.0004, 'pc_gpu_accent')
    # riser plug in the top x16 slot
    box(mb, (0.0310, 0.105, 0.2255), (0.0436, 0.195, 0.2360), 'pc_riser', r=0.0010, seg=1)
    box(mb, (0.0305, 0.108, 0.2295), (0.0312, 0.192, 0.2320), 'pc_port_dark')
    # board I/O in the rear cut-out: Wi-Fi SMA posts, BIOS/CMOS buttons, 8x USB-A, 2x USB-C, RJ45, audio
    box(mb, (0.020, HD - 0.0045, 0.260), (0.049, HD - 0.0005, 0.416), 'pc_white_alu')
    cols = (0.0275, 0.0415)
    for uc in cols:
        Ms = frame((uc, HD - 0.0005, 0.405), (0, 1, 0))
        lathe(mb, [(0.0, 0.0), (0.0040, 0.0), (0.0040, 0.0020), (0.0, 0.0020)], 'pc_gold', Ms, seg=6)
        lathe(mb, [(0.0, 0.0020), (0.0030, 0.0020), (0.0030, 0.0085), (0.0026, 0.0090), (0.0, 0.0090)], 'pc_gold', Ms, seg=20)
        Mbt = frame((uc, HD - 0.0005, 0.393), (0, 1, 0))
        lathe(mb, [(0.0, 0.0), (0.0030, 0.0), (0.0030, 0.0008), (0.0, 0.0008)], 'pc_white_pcb', Mbt, seg=16)
        lathe(mb, [(0.0, 0.0008), (0.0020, 0.0008), (0.0020, 0.0016), (0.0, 0.0016)], 'pc_port_dark', Mbt, seg=16)

    def usb_a(uc, zc):
        box(mb, (uc - 0.0068, HD - 0.0020, zc - 0.0029), (uc + 0.0068, HD + 0.0003, zc + 0.0029), 'pc_metal')
        box(mb, (uc - 0.0062, HD - 0.0019, zc - 0.0023), (uc + 0.0062, HD + 0.0004, zc + 0.0023), 'pc_port_dark')
        box(mb, (uc - 0.0055, HD - 0.0017, zc - 0.0020), (uc + 0.0055, HD - 0.0004, zc - 0.0004), 'pc_gpu_blue')
    for zc in (0.380, 0.371, 0.312, 0.303):
        for uc in cols:
            usb_a(uc, zc)
    for uc in cols:
        Mu = frame((uc, HD - 0.0020, 0.3600), (0, 1, 0), (1, 0, 0))
        prism(mb, rrect(0.0094, 0.0036, 0.0017, 5), Mu, 0.0, 0.0023, 'pc_metal')
        prism(mb, rrect(0.0084, 0.0026, 0.0012, 5), Mu, 0.0, 0.0024, 'pc_port_dark')
    box(mb, (0.0265, HD - 0.0020, 0.3205), (0.0425, HD + 0.0003, 0.3345), 'pc_metal')
    box(mb, (0.0275, HD - 0.0019, 0.3215), (0.0415, HD + 0.0004, 0.3320), 'pc_port_dark')
    box(mb, (0.0275, HD + 0.0002, 0.3322), (0.0300, HD + 0.0005, 0.3340), 'pc_led_green')
    box(mb, (0.0390, HD + 0.0002, 0.3322), (0.0415, HD + 0.0005, 0.3340), 'pc_led_amber')
    for (uc, zc), col in zip(((0.0275, 0.290), (0.0415, 0.290), (0.0275, 0.279), (0.0415, 0.279), (0.0275, 0.268)),
                             ('pc_jack_blue', 'pc_jack_green', 'pc_jack_pink', 'pc_jack_orange', 'pc_metal')):
        Mj = frame((uc, HD - 0.0005, zc), (0, 1, 0))
        lathe(mb, [(0.0018, 0.0), (0.0042, 0.0), (0.0042, 0.0009), (0.0018, 0.0009)], col, Mj, seg=24)
        lathe(mb, [(0.0, -0.002), (0.0018, -0.002), (0.0018, 0.0006), (0.0, 0.0006)], 'pc_port_dark', Mj, seg=16)
    box(mb, (0.0375, HD - 0.0020, 0.2645), (0.0455, HD + 0.0005, 0.2715), 'pc_port_dark', r=0.0008, seg=1)
    done(mb)

    # ------------------------------------------------------------------ AIO pump head
    PV0, PV1, PZ0, PZ1, PU0 = 0.075, 0.147, 0.302, 0.374, 0.008
    pc_ = V((PU0, (PV0 + PV1) / 2, (PZ0 + PZ1) / 2))
    mb = MB('pc_aio_pump', ['pc_white_plastic'])
    box(mb, (PU0, PV0, PZ0), (0.046, PV1, PZ1), 'pc_white_plastic', r=0.010, seg=4)
    Mf = frame(pc_, (-1, 0, 0), (0, -1, 0))      # local +Z out of the pump face (-u)
    lathe(mb, [(0.0290, -0.0002), (0.0290, 0.0003), (0.0322, 0.0006), (0.0334, 0.0003), (0.0334, -0.0003)],
          'pc_white_alu', Mf, seg=72)
    lathe(mb, [(0.0336, -0.0001), (0.0336, 0.0003), (0.0346, 0.0003), (0.0346, -0.0001)], 'pc_rgb_led', Mf, seg=72)
    # retention bracket bars behind the pump with knurled thumbnuts
    for zz in (PZ0 + 0.004, PZ1 - 0.004):
        box(mb, (0.041, 0.062, zz - 0.0035), (0.0475, 0.160, zz + 0.0035), 'pc_white_alu', r=0.0012, seg=2)
        for vv in (0.066, 0.156):
            thumbscrew(mb, (0.041, vv, zz), (-1, 0, 0), mat='pc_white_alu', r=0.0036, L=0.006)
    # swivel fittings on the front (-v) side, turning toward the glass
    for zz in (0.3255, 0.3505):
        lathe(mb, [(0.0, 0.0), (0.0078, 0.0), (0.0078, 0.004), (0.0072, 0.0045), (0.0072, 0.0085), (0.0, 0.0085)],
              'pc_white_alu', frame((0.017, PV0 + 0.0005, zz), (0, -1, 0)), seg=32)
    done(mb)
    # screen as its own object (object coords = screen plane in metres)
    sm = bpy.data.meshes.new('pc_aio_screen')
    bm = lathe_bm([(0.0, 0.0), (0.0290, 0.0)], seg=72)
    bm.to_mesh(sm)
    bm.free()
    sm.materials.append(MAT['pc_pump_screen'])
    so = bpy.data.objects.new('pc_aio_screen', sm)
    coll.objects.link(so)
    so.parent = root
    so.matrix_parent_inverse = Matrix.Identity(4)
    so.matrix_basis = Mf @ Matrix.Translation((0, 0, 0.00005))
    objs.append(so)
    cu = bpy.data.curves.new('pc_screen_text', 'FONT')
    cu.body = '38°C'
    cu.size = 0.0115
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    to = bpy.data.objects.new('tmp_text', cu)
    coll.objects.link(to)
    bpy.context.view_layer.update()
    tm = bpy.data.meshes.new_from_object(to.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(to, do_unlink=True)
    tm.name = 'pc_aio_screen_text'
    tm.materials.clear()
    tm.materials.append(MAT['pc_screen_text'])
    tob = bpy.data.objects.new('pc_aio_screen_text', tm)
    coll.objects.link(tob)
    tob.parent = root
    tob.matrix_basis = Mf @ Matrix.Translation((0.0, 0.0010, 0.00015))
    objs.append(tob)
    cu2 = bpy.data.curves.new('pc_screen_label', 'FONT')
    cu2.body = 'CPU'
    cu2.size = 0.0048
    cu2.align_x = 'CENTER'
    cu2.align_y = 'CENTER'
    to2 = bpy.data.objects.new('tmp_text2', cu2)
    coll.objects.link(to2)
    bpy.context.view_layer.update()
    tm2 = bpy.data.meshes.new_from_object(to2.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(to2, do_unlink=True)
    tm2.name = 'pc_aio_screen_label'
    tm2.materials.clear()
    tm2.materials.append(MAT['pc_screen_text'])
    tob2 = bpy.data.objects.new('pc_aio_screen_label', tm2)
    coll.objects.link(tob2)
    tob2.parent = root
    tob2.matrix_basis = Mf @ Matrix.Translation((0.0, -0.0105, 0.00015))
    objs.append(tob2)

    # ------------------------------------------------------------------ radiator 360 + top fans
    RU0, RU1, RZ0, RZ1 = -0.135, -0.015, 0.410, 0.437
    mb = MB('pc_radiator', ['pc_white_alu'])
    box(mb, (RU0, -0.215, RZ0), (RU1, -0.195, RZ1), 'pc_white_alu', r=0.004, seg=3)
    box(mb, (RU0, 0.165, RZ0), (RU1, 0.182, RZ1), 'pc_white_alu', r=0.004, seg=3)
    box(mb, (RU0 + 0.003, -0.196, RZ0 + 0.001), (RU1 - 0.003, 0.166, RZ1 - 0.001), 'pc_rad_fins')
    for uu in (RU0, RU1 - 0.003):
        box(mb, (uu, -0.196, RZ0), (uu + 0.003, 0.166, RZ1), 'pc_white_alu', r=0.0008, seg=1)
    for k in range(12):
        uu = RU0 + 0.0075 + k * 0.0095
        for z0, z1 in ((RZ0 + 0.0004, RZ0 + 0.0012), (RZ1 - 0.0012, RZ1 - 0.0004)):
            box(mb, (uu - 0.0009, -0.1955, z0), (uu + 0.0009, 0.1655, z1), 'pc_white_alu')
    for vv in (-0.1875, -0.0825, -0.0675, 0.0375, 0.0525, 0.1575):
        for uu, ax in ((RU0, -1), (RU1, 1)):
            lathe(mb, [(0.0, 0.0), (0.0022, 0.0), (0.0022, 0.0006), (0.0014, 0.0010), (0.0, 0.0010)], 'pc_metal',
                  frame((uu, vv, (RZ0 + RZ1) / 2), (ax, 0, 0)), seg=12)
    PORTS = (-0.048, -0.080)
    for uu in PORTS:
        lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.006), (0.0078, 0.0068), (0.0078, 0.012), (0.0, 0.012)],
              'pc_white_alu', frame((uu, -0.205, RZ0 + 0.0005), (0, 0, -1)), seg=32)
    done(mb)
    FZ = RZ0 - 0.0125
    mbF, mbR = MB('pc_fans_frames', ['pc_white_plastic', 'pc_rgb_led']), MB('pc_fans_rotors', ['pc_fan_blade'])
    for vv in (-0.135, -0.015, 0.105):
        case_fan(mbF, mbR, frame((-0.075, vv, FZ), (0, 0, -1), (1, 0, 0)))
    for vv in (-0.135, -0.010, 0.115):
        case_fan(mbF, mbR, frame((-0.045, vv, Z0 + 0.0125 + 0.003), (0, 0, 1), (1, 0, 0)))
    case_fan(mbF, mbR, frame((FAN_R[0], HD - 0.003 - 0.0125, FAN_R[1]), (0, -1, 0), (1, 0, 0)))
    done(mbF)
    done(mbR, 60)

    # AIO tubes (white sleeved, 12.5 mm) from the pump fittings to the radiator ports
    mb = MB('pc_aio_tubes', ['pc_tube_white'])
    tA = [V((0.017, PV0 - 0.008, 0.3255)), V((0.014, 0.062, 0.3255)), V((0.004, 0.058, 0.3255)), V((-0.012, 0.050, 0.327)),
          V((-0.022, 0.0, 0.332)), V((-0.034, -0.110, 0.345)), V((PORTS[0], -0.185, 0.360)), V((PORTS[0], -0.205, 0.380)),
          V((PORTS[0], -0.205, RZ0 - 0.011))]
    tB = [V((0.017, PV0 - 0.008, 0.3505)), V((0.014, 0.062, 0.3505)), V((0.004, 0.058, 0.3505)), V((-0.012, 0.050, 0.352)),
          V((-0.024, 0.0, 0.357)), V((-0.055, -0.110, 0.366)), V((PORTS[1], -0.180, 0.370)), V((PORTS[1], -0.205, 0.386)),
          V((PORTS[1], -0.205, RZ0 - 0.011))]
    for t in (tA, tB):
        tube(mb, t, 0.0063, 'pc_tube_white', sides=16, step=0.004)
        # crimp collars at both ends
        for p, q in ((t[0], t[1]), (t[-1], t[-2])):
            lathe(mb, [(0.0, 0.0), (0.0074, 0.0), (0.0074, 0.011), (0.0068, 0.012), (0.0, 0.012)], 'pc_white_alu',
                  frame(p, q - p), seg=24)
    # tube clip holding the pair together mid-run
    pa, pb = tA[5], tB[5]
    Mcl = frame((pa + pb) / 2, pb - pa, (0, 1, 0))
    L_ = (pb - pa).length
    box(mb, (-0.0035, -0.0045, -L_ / 2), (0.0035, 0.0045, L_ / 2), 'pc_white_plastic', r=0.0015, seg=2, M=Mcl)
    for p in (pa, pb):
        lathe(mb, [(0.0068, -0.0045), (0.0078, -0.0045), (0.0078, 0.0045), (0.0068, 0.0045)], 'pc_white_plastic',
              frame(p, (0, 1, 0)), seg=24)
    done(mb, 50)

    # ------------------------------------------------------------------ GPU (vertical, fans to the glass)
    GU0, GU1 = -0.126, -0.085              # shroud face .. shroud back
    GV0, GV1, GZ0_, GZ1_ = -0.106, 0.203, 0.114, 0.246
    FANS_V = (-0.054, 0.046, 0.146)
    FZC = (GZ0_ + GZ1_) / 2
    mb = MB('pc_gpu_shroud', ['pc_gpu_blue'])
    box(mb, (GU0, GV0, GZ0_), (GU1, GV1 - 0.002, GZ1_), 'pc_gpu_blue', r=0.006, seg=3)
    shroud = done(mb)
    cuts = [cutter(coll, lathe_bm([(0.0, -0.01), (0.0455, -0.01), (0.0455, 0.028), (0.0, 0.028)], 64,
                                  frame((GU0 - 0.004, vv, FZC), (1, 0, 0))), 'pc_heatsink') for vv in FANS_V]
    boolean_apply(shroud, cuts)
    mb = MB('pc_gpu_details', ['pc_gpu_accent'])
    for vv in FANS_V:
        Mfg = frame((GU0, vv, FZC), (-1, 0, 0), (0, -1, 0))
        lathe(mb, [(0.0452, -0.0006), (0.0452, 0.0004), (0.0462, 0.0010), (0.0480, 0.0010), (0.0488, 0.0), (0.0488, -0.0006)],
              'pc_gpu_accent', Mfg, seg=72)
        # heatsink fin stack visible behind the blades (fins normal to v, clipped to the opening)
        for k in range(-15, 16):
            dv = k * 0.0029
            half = math.sqrt(max(0.0452 ** 2 - dv ** 2, 0)) - 0.0008
            if half < 0.004:
                continue
            box(mb, (GU0 + 0.016, vv + dv - 0.0003, FZC - half), (GU0 + 0.0245, vv + dv + 0.0003, FZC + half), 'pc_heatsink')
    # angular dark-blue accent panels between the fans and at the ends, RGB edge strip on top
    for va, vb in ((-0.0995, -0.1040), (0.0955, 0.0965), (0.1955, 0.1965)):
        pass
    for vv in (-0.004, 0.096):
        box(mb, (GU0 - 0.0006, vv - 0.0020, GZ0_ + 0.020), (GU0 + 0.002, vv + 0.0020, GZ1_ - 0.020), 'pc_gpu_blue_dark', r=0.0008, seg=1)
    box(mb, (GU0 - 0.0006, GV0 + 0.004, GZ1_ - 0.012), (GU0 + 0.002, GV0 + 0.030, GZ1_ - 0.008), 'pc_gpu_accent', r=0.0008, seg=1)
    box(mb, (GU0 - 0.0006, GV0 + 0.004, GZ0_ + 0.008), (GU0 + 0.002, GV0 + 0.030, GZ0_ + 0.012), 'pc_gpu_accent', r=0.0008, seg=1)
    box(mb, (GU0 + 0.006, -0.090, GZ1_ - 0.0004), (GU0 + 0.020, 0.170, GZ1_ + 0.0018), 'pc_rgb_diffuser', r=0.0008, seg=1)
    # PCB, backplate, bracket with ports, power connector, vertical-mount shelf
    box(mb, (GU1, GV0 + 0.004, GZ0_ + 0.004), (GU1 + 0.0016, GV1 - 0.003, GZ1_ + 0.004), 'pc_gpu_pcb')
    box(mb, (GU1 + 0.0016, GV0 + 0.002, GZ0_ + 0.002), (GU1 + 0.0046, GV1 - 0.004, GZ1_ + 0.002), 'pc_gpu_blue', r=0.0012, seg=2)
    for k in range(7):
        vv = GV0 + 0.030 + k * 0.022
        box(mb, (GU1 + 0.0044, vv, GZ0_ + 0.030), (GU1 + 0.0050, vv + 0.012, GZ1_ - 0.030), 'pc_gpu_blue_dark', r=0.0002, seg=1)
    box(mb, (-0.132, GV1 - 0.0002, 0.098), (-0.066, GV1 + 0.0012, 0.256), 'pc_metal', r=0.0005, seg=1)
    for k in range(4):
        zz = 0.110 + k * 0.030
        box(mb, (-0.120, GV1 + 0.0010, zz), (-0.104, GV1 + 0.0035, zz + 0.012), 'pc_port_dark', r=0.0005, seg=1)
    box(mb, (-0.0880, -0.0275, GZ1_ + 0.002), (-0.0770, -0.0045, GZ1_ + 0.008), 'pc_dark_plastic', r=0.0008, seg=1)
    box(mb, (-0.0878, -0.0272, GZ1_ + 0.0078), (-0.0772, -0.0048, GZ1_ + 0.0165), 'pc_white_plastic', r=0.0010, seg=1)
    box(mb, (-0.0892, -0.0200, GZ1_ + 0.0050), (-0.0876, -0.0120, GZ1_ + 0.0140), 'pc_white_plastic', r=0.0005, seg=1)
    box(mb, (-0.0877, -0.0262, GZ1_ + 0.0100), (-0.0873, -0.0228, GZ1_ + 0.0150), 'pc_port_dark')
    box(mb, (-0.0880, -0.0272, GZ1_ + 0.0185), (-0.0770, -0.0048, GZ1_ + 0.0215), 'pc_white_plastic', r=0.0006, seg=1)
    # backplate: raised panel, screws
    box(mb, (GU1 + 0.0044, GV0 + 0.012, GZ0_ + 0.014), (GU1 + 0.0056, GV0 + 0.022, GZ1_ - 0.012), 'pc_gpu_blue_dark', r=0.0004, seg=1)
    for vv, zz in ((GV0 + 0.008, GZ0_ + 0.008), (GV0 + 0.008, GZ1_ - 0.006), (0.0, GZ0_ + 0.008), (0.0, GZ1_ - 0.006),
                   (0.125, GZ0_ + 0.008), (0.125, GZ1_ - 0.006), (0.060, FZC), (0.160, FZC)):
        lathe(mb, [(0.0, 0.0), (0.0021, 0.0), (0.0021, 0.0006), (0.0013, 0.0010), (0.0, 0.0010)], 'pc_metal',
              frame((GU1 + 0.0046, vv, zz), (1, 0, 0)), seg=12)
    # vertical-mount shelf with the riser socket under the card's PCIe fingers
    box(mb, (-0.136, 0.100, 0.089), (-0.062, HD - 0.003, 0.097), 'pc_white_steel', r=0.0015, seg=2)
    box(mb, (-0.0930, 0.110, 0.097), (-0.0745, 0.192, 0.1135), 'pc_dark_plastic', r=0.0010, seg=1)
    box(mb, (-0.0940, 0.106, 0.097), (-0.0735, 0.110, 0.1120), 'pc_white_plastic', r=0.0005, seg=1)
    box(mb, (-0.136, HD - 0.009, 0.089), (-0.062, HD - 0.003, 0.140), 'pc_white_steel', r=0.0015, seg=2)
    done(mb)
    mbRs = MB('pc_riser_cable', ['pc_riser'])
    band(mbRs, [V((0.0310, 0.150, 0.2307)), V((0.0240, 0.150, 0.2307)), V((0.0160, 0.150, 0.2220)),
                V((0.0140, 0.150, 0.1900)), V((0.0120, 0.150, 0.1300)), V((0.0000, 0.150, 0.1060)),
                V((-0.0300, 0.150, 0.1025)), V((-0.0600, 0.150, 0.1025)), V((-0.0745, 0.150, 0.1045))],
         0.072, 0.0014, (0, 1, 0), 'pc_riser', step=0.004)
    # shielding stripes on the ribbon
    for zz in (0.200, 0.160):
        box(mbRs, (0.0128, 0.114, zz), (0.0147, 0.186, zz + 0.006), 'pc_white_alu')
    done(mbRs, 40)
    mbG = MB('pc_gpu_fans', ['pc_gpu_blade'])
    for vv in FANS_V:
        Mfg = frame((GU0, vv, FZC), (-1, 0, 0), (0, -1, 0))
        rotor(mbG, Mfg, 0.0165, 0.0435, -0.0185, -0.0035, 11, 'pc_gpu_blade', 'pc_gpu_blue_dark', 'pc_gpu_accent',
              nr=5, ns=5, sweep=24, thick=0.0010)
    done(mbG, 60)

    # ------------------------------------------------------------------ sleeved cables
    mb = MB('pc_cables_sleeved', ['pc_sleeve_white'])
    # 24-pin: 12 rows (z) x 2 columns (u), out of the plug toward -v, bending +u through the grommet
    ribbon(mb, [V((0.0465, -0.040, 0.327)), V((0.0465, -0.047, 0.327)), V((0.0475, -0.054, 0.327)),
                V((0.054, -0.057, 0.327)), V((0.063, -0.058, 0.327)), V((0.075, -0.058, 0.327))],
           12, 2, 0.0043, 0.0040, 0.00185, (0, 0, 1), 'pc_sleeve_white')
    # 12V-2x6 from the GPU top edge up and over into the lower grommet
    ribbon(mb, [V((-0.0825, -0.016, GZ1_ + 0.0160)), V((-0.0825, -0.016, GZ1_ + 0.024)), V((-0.070, -0.030, GZ1_ + 0.032)),
                V((-0.030, -0.052, GZ1_ + 0.024)), V((0.010, -0.062, 0.252)), V((0.045, -0.064, 0.240)),
                V((0.060, -0.064, 0.236)), V((0.080, -0.064, 0.236))],
           6, 2, 0.0036, 0.0036, 0.00165, (0, 1, 0), 'pc_sleeve_white')
    # EPS 8-pin x2 straight up into the top notch
    for v0 in (0.110, 0.134):
        ribbon(mb, [V((0.045, v0, 0.427)), V((0.045, v0, 0.431)), V((0.050, v0, 0.4335)), V((0.058, v0, 0.4340)),
                    V((0.072, v0, 0.4340))], 4, 2, 0.0042, 0.0042, 0.0017, (0, 1, 0), 'pc_sleeve_white')
    # second 24-pin comb just past the bend, EPS combs
    box(mb, (0.0525, -0.0625, 0.3000), (0.0555, -0.0520, 0.3540), 'pc_white_plastic', r=0.0008, seg=1)
    done(mb, 50)

    # ------------------------------------------------------------------ rear chamber (behind the tray)
    mb = MB('pc_rear_chamber', ['pc_cable_black'])
    # 2.5" SSD sleds on the back of the tray
    for z0 in (0.300, 0.212):
        box(mb, (0.0605, -0.200, z0), (0.0625, -0.095, z0 + 0.072), 'pc_white_steel', r=0.0006, seg=1)
        for zz in (z0, z0 + 0.069):
            box(mb, (0.0605, -0.200, zz), (0.0710, -0.095, zz + 0.003), 'pc_white_steel', r=0.0006, seg=1)
        box(mb, (0.0625, -0.198, z0 + 0.0035), (0.0695, -0.099, z0 + 0.0685), 'pc_ssd', r=0.0008, seg=1)
        box(mb, (0.0630, -0.0995, z0 + 0.012), (0.0690, -0.0955, z0 + 0.040), 'pc_port_dark')
        band(mb, [V((0.0660, -0.0955, z0 + 0.026)), V((0.0700, -0.088, z0 + 0.026)), V((0.0850, -0.070, z0 + 0.010)),
                  V((0.1000, -0.040, 0.268)), V((0.1030, -0.005, 0.232))], 0.0085, 0.0012, (0, 0, 1), 'pc_cable_black',
             step=0.006)
    # ARGB/fan hub with its leads
    box(mb, (0.0605, -0.020, 0.340), (0.0710, 0.045, 0.392), 'pc_ssd', r=0.0015, seg=2)
    for k, end in enumerate((V((0.074, 0.120, 0.434)), V((0.074, -0.060, 0.370)), V((0.074, -0.064, 0.250)),
                             V((0.072, 0.080, 0.070)))):
        st = V((0.0712, -0.012 + k * 0.016, 0.340 if k > 1 else 0.392))
        mid = (st + end) / 2 + V((0.012, 0.0, 0.0))
        tube(mb, [st, st + V((0.004, 0, 0)), mid, end], 0.0012, 'pc_cable_black', sides=6, step=0.008)
    # PSU modular cables (black) from the grommets down into the PSU, cable-tied
    pts, fr = ribbon(mb, [V((0.078, -0.058, 0.327)), V((0.090, -0.052, 0.310)), V((0.100, -0.035, 0.272)),
                          V((0.104, 0.000, 0.240)), V((0.104, 0.030, 0.228)), V((0.102, 0.048, 0.205)),
                          V((0.096, 0.058, 0.178)), V((0.092, 0.0645, 0.160))],
                     6, 2, 0.0058, 0.0058, 0.0027, (0, 0, 1), 'pc_cable_black', sides=6, step=0.006)
    tie(mb, pts, fr, 0.35, 0.035, 0.0115)
    tie(mb, pts, fr, 0.62, 0.035, 0.0115)
    pts, fr = ribbon(mb, [V((0.082, -0.064, 0.236)), V((0.095, -0.056, 0.232)), V((0.118, -0.020, 0.226)),
                          V((0.122, 0.030, 0.212)), V((0.112, 0.052, 0.150)), V((0.095, 0.059, 0.133)),
                          V((0.089, 0.0645, 0.130))],
                     3, 2, 0.0058, 0.0058, 0.0027, (0, 1, 0), 'pc_cable_black', sides=6, step=0.006)
    tie(mb, pts, fr, 0.45, 0.0175, 0.0115)
    for k, v0 in enumerate((0.110, 0.134)):
        zt = (0.100, 0.070)[k]
        pts, fr = ribbon(mb, [V((0.074, v0, 0.434)), V((0.082, v0, 0.428)), V((0.090, v0 - 0.012, 0.400)),
                              V((0.110, 0.085, 0.330)), V((0.138, 0.062 - k * 0.008, 0.260)),
                              V((0.138, 0.056 - k * 0.004, 0.190)), V((0.110, 0.060, zt + 0.004)),
                              V((0.090, 0.0645, zt))],
                         2, 2, 0.0058, 0.0058, 0.0027, (0, 1, 0), 'pc_cable_black', sides=6, step=0.006)
        if k == 0:
            tie(mb, pts, fr, 0.55, 0.0175, 0.0115)
    done(mb, 50)

    # ------------------------------------------------------------------ mains cable to the power strip
    mb = MB('pc_power_cable', ['pc_cable_black', 'pc_plug_black'])
    # IEC C13 plug on the PSU inlet (case-local)
    box(mb, (0.0885, HD + 0.0035, 0.0575), (0.1215, HD + 0.030, 0.0845), 'pc_plug_black', r=0.004, seg=3)
    lathe(mb, [(0.0, 0.0), (0.0078, 0.0), (0.0074, 0.008), (0.0055, 0.018), (0.0046, 0.024), (0.0, 0.024)],
          'pc_plug_black', frame((0.105, HD + 0.029, 0.071), (0, 1, 0)), seg=24)
    for k in range(4):
        lathe(mb, [(0.0, 0.0), (0.0079, 0.0), (0.0079, 0.0012), (0.0, 0.0012)], 'pc_plug_black',
              frame((0.105, HD + 0.0325 + k * 0.004, 0.071), (0, 1, 0)), seg=24)
    # Schuko plug standing in socket 2 of the strip (world -> local)
    SOCK = V((0.2600, 1.2350, 0.0))
    Mp = TI @ Matrix.Translation(SOCK)
    lathe(mb, [(0.0, 0.0235), (0.0182, 0.0235), (0.0185, 0.0385), (0.0192, 0.0400), (0.0192, 0.0460), (0.0186, 0.0470),
               (0.0186, 0.0520), (0.0192, 0.0530), (0.0190, 0.0680), (0.0170, 0.0780), (0.0120, 0.0860),
               (0.0070, 0.0900), (0.0052, 0.0905), (0.0046, 0.0990), (0.0, 0.0990)], 'pc_plug_black', Mp, seg=40)
    world_path = [V((0.2600, 1.2350, 0.0980)), V((0.2600, 1.2340, 0.1080)), V((0.2620, 1.2220, 0.1190)),
                  V((0.2660, 1.2010, 0.1060)), V((0.2700, 1.1910, 0.0620)), V((0.2760, 1.1905, 0.0200)),
                  V((0.2920, 1.1940, 0.0035)), V((0.3400, 1.1960, 0.0035)), V((0.5000, 1.1965, 0.0035)),
                  V((0.7000, 1.1960, 0.0035)), V((0.8600, 1.1880, 0.0035)), V((0.9600, 1.1420, 0.0035)),
                  V((1.0900, 1.1000, 0.0035)), V((1.2000, 1.0700, 0.0035)), V((1.2900, 1.0300, 0.0035))]
    local_tail = [V((0.100, HD + 0.100, 0.0035)), V((0.105, HD + 0.093, 0.012)), V((0.105, HD + 0.083, 0.040)),
                  V((0.105, HD + 0.068, 0.066)), V((0.105, HD + 0.054, 0.071))]
    path = [TI @ p for p in world_path] + local_tail
    tube(mb, path, 0.0034, 'pc_cable_black', sides=10, per=10, step=0.006)
    done(mb, 50)

    bpy.context.view_layer.update()
    tris = {}
    for o in objs:
        tris[o.name] = sum(len(p.vertices) - 2 for p in o.data.polygons)
    total = sum(tris.values())
    print('TRIS', total, sorted(tris.items(), key=lambda x: -x[1]))
    # world bbox of the case body (without the mains cable) for clearance reporting
    cw = [T @ V((sx * HW, sy * HD, 0)) for sx in (-1, 1) for sy in (-1, 1)]
    print('FOOTPRINT', [(round(p.x, 3), round(p.y, 3)) for p in cw])
    return dict(scene=scene, coll=coll, root=root, total=total)


# ============================================================================== previews
def previews(b):
    scene = b['scene']
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
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 10
    scene.cycles.transparent_max_bounces = 16
    scene.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new('grey')
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.42, 0.42, 0.42, 1)
    bg.inputs['Strength'].default_value = 0.35
    scene.world = w
    tmp = []
    fl = bpy.data.meshes.new('prev_floor')
    fl.from_pydata([(C.x - 3, C.y - 3, 0), (C.x + 3, C.y - 3, 0), (C.x + 3, C.y + 3, 0), (C.x - 3, C.y + 3, 0)], [], [(0, 1, 2, 3)])
    fm = bpy.data.materials.new('prev_floor')
    fm.use_nodes = True
    pr(fm).inputs['Base Color'].default_value = (0.30, 0.28, 0.26, 1)
    pr(fm).inputs['Roughness'].default_value = 0.6
    fl.materials.append(fm)
    fo = bpy.data.objects.new('prev_floor', fl)
    scene.collection.objects.link(fo)
    tmp.append(fo)
    mid = T @ V((0, 0, 0.24))

    def light(name, off, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        o = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(o)
        o.location = mid + V(off)
        o.rotation_euler = (mid - o.location).to_track_quat('-Z', 'Y').to_euler()
        tmp.append(o)
    light('key', (-1.0, -1.1, 1.3), 60, 1.0)
    light('fill', (0.4, -1.3, 0.5), 25, 1.2)
    light('rim', (0.6, 1.1, 1.2), 60, 0.8)
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam
    tmp.append(cam)

    def shot(loc, target, lens, name, res=(1280, 800)):
        scene.render.resolution_x, scene.render.resolution_y = res
        cam.location = loc
        cam.data.lens = lens
        cam.data.clip_start = 0.01
        cam.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, name)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', name)
    only = [a for a in ARGS if a.startswith('--only=')]
    only = only[0].split('=')[1].split(',') if only else None
    if not only or '34' in only:
        shot(T @ V((-0.62, -0.50, 0.55)), T @ V((0.0, 0.0, 0.225)), 30, 'pc_34.png')
    if not only or 'seat' in only:
        shot(SEAT, mid, 50, 'pc_seat.png')
    if not only or 'side' in only:
        shot(T @ V((-0.95, 0.0, 0.26)), T @ V((0.0, 0.0, 0.24)), 38, 'pc_side.png')
    if not only or 'rear' in only:
        shot(T @ V((0.35, 1.0, 0.6)), T @ V((0.0, 0.3, 0.1)), 30, 'pc_rear.png')
    if not only or 'topio' in only:
        shot(T @ V((0.030, -0.330, H + 0.150)), T @ V((0.098, -0.168, H)), 60, 'pc_topio.png')
    if not only or 'detail' in only:
        shot(T @ V((-0.36, -0.10, 0.40)), T @ V((0.02, 0.06, 0.33)), 40, 'pc_detail.png')
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)


def finish(b):
    for o in list(bpy.context.scene.objects):
        if o.name not in b['coll'].all_objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    print('SAVED', OUT_BLEND)


if __name__ == '__main__':
    b = build()
    if not NO_RENDER:
        previews(b)
    finish(b)
    print('DONE')
