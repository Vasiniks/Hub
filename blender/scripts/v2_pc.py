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
import ntpath
import random

import numpy as np
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
C = V((0.738, 0.970, 0.735))       # on the desk top, back-right corner (long axis along the back edge)
YAW = math.radians(90.0)            # side glass faces the chair, front (vertical LCD fans) toward +x
MIRROR = False                      # native layout, positive scales only
DZ = 0.041                          # everything is modelled with the inside floor at z=0.034; lift by DZ
LCD_Q, FRAMED = [], []
# owner-supplied downloads (git-ignored under assets/source; textures stay external, never packed)
SRC = os.path.join(REPO, 'assets', 'source')
KIT_DIR = os.path.join(SRC, 'gpu-kit-rtx-5090-arc-b580-gigabyte-aero')        # licence unknown: local-only
MOBO_DIR = os.path.join(SRC, 'motherboard-components')                        # CC BY 4.0, Daniel Cardona
GPU_TINT = (0.74, 0.85, 1.0)
T = Matrix.Translation(C) @ Matrix.Rotation(YAW, 4, 'Z')
TI = T.inverted()
W, D, H = 0.296, 0.465, 0.454         # build coords: H = top of the thin top rail (world height H + DZ)
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
    si(p, 'Base Color', (0.90, 0.95, 0.94, 1))
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
    m = new_mat('pc_filter_mesh', (0.20, 0.20, 0.21), 0.6, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    a = math_node(nt, 'SINE', math_node(nt, 'MULTIPLY', sep.outputs['X'], 2 * math.pi / 0.0009))
    b = math_node(nt, 'SINE', math_node(nt, 'MULTIPLY', sep.outputs['Y'], 2 * math.pi / 0.0009))
    h = math_node(nt, 'MAXIMUM', a, b)
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.3
    bp.inputs['Distance'].default_value = 0.0002
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], p.inputs['Normal'])
    return m


def mb_pcb_mat():
    """White board PCB with faint copper-trace runs (object Y/Z = board plane) and fine bump."""
    m = new_mat('pc_mb_pcb', (0.80, 0.80, 0.79), 0.5, bump=0.02, bscale=500)
    nt = m.node_tree
    p = pr(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])

    def line(coord, pitch, width):
        f = math_node(nt, 'ABSOLUTE', math_node(nt, 'SUBTRACT', math_node(nt, 'FRACT', math_node(nt, 'DIVIDE', coord, pitch)), 0.5))
        return math_node(nt, 'LESS_THAN', f, width)
    ly = line(sep.outputs['Y'], 0.0017, 0.09)
    lz = line(sep.outputs['Z'], 0.0023, 0.08)
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 45
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nz2 = nt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 38
    nz2.inputs['Detail'].default_value = 1.0
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    my = math_node(nt, 'GREATER_THAN', nz.outputs['Fac'], 0.56)
    mz = math_node(nt, 'GREATER_THAN', nz2.outputs['Fac'], 0.58)
    tr = math_node(nt, 'MAXIMUM', math_node(nt, 'MULTIPLY', ly, my), math_node(nt, 'MULTIPLY', lz, mz))
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    nt.links.new(tr, mix.inputs['Factor'])
    sock(mix.inputs, 'A_Color').default_value = (0.80, 0.80, 0.79, 1)
    sock(mix.inputs, 'B_Color').default_value = (0.70, 0.71, 0.71, 1)
    nt.links.new(sock(mix.outputs, 'Result_Color'), p.inputs['Base Color'])
    return m


def dots_mat():
    """Ice-silver shroud flat with a fine staggered dot-perforation pattern (object XY = card underside plane)."""
    m = new_mat('pc_gpu_dots', (0.80, 0.83, 0.88), 0.34, metal=0.25, rvar=0.0)
    nt = m.node_tree
    p = pr(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    P_ = 0.0012
    u = math_node(nt, 'DIVIDE', sep.outputs['X'], P_)
    v = math_node(nt, 'DIVIDE', sep.outputs['Y'], P_ * 0.866)
    odd = math_node(nt, 'ABSOLUTE', math_node(nt, 'MODULO', math_node(nt, 'FLOOR', v), 2.0))
    u2 = math_node(nt, 'ADD', u, math_node(nt, 'MULTIPLY', odd, 0.5))
    fu = math_node(nt, 'SUBTRACT', math_node(nt, 'FRACT', u2), 0.5)
    fv = math_node(nt, 'MULTIPLY', math_node(nt, 'SUBTRACT', math_node(nt, 'FRACT', v), 0.5), 0.866)
    d = math_node(nt, 'SQRT', math_node(nt, 'ADD', math_node(nt, 'MULTIPLY', fu, fu), math_node(nt, 'MULTIPLY', fv, fv)))
    dot = math_node(nt, 'LESS_THAN', d, 0.26)
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    nt.links.new(dot, mix.inputs['Factor'])
    sock(mix.inputs, 'A_Color').default_value = (0.80, 0.83, 0.88, 1)
    sock(mix.inputs, 'B_Color').default_value = (0.30, 0.32, 0.36, 1)
    nt.links.new(sock(mix.outputs, 'Result_Color'), p.inputs['Base Color'])
    b = nt.nodes.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = 0.35
    b.inputs['Distance'].default_value = 0.0002
    nt.links.new(math_node(nt, 'SUBTRACT', 1.0, dot), b.inputs['Height'])
    nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
    return m


def lcd_art_mat():
    """Abstract pink/blue light-streak artwork for the pump LCD (object XY in metres), no text/logos."""
    m = bpy.data.materials.new('pc_lcd_art')
    m.use_nodes = True
    nt = m.node_tree
    p = pr(m)
    si(p, 'Base Color', (0.0, 0.0, 0.0, 1))
    si(p, 'Roughness', 0.05)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (24.0, 24.0, 24.0)
    mp.inputs['Rotation'].default_value = (0.0, 0.0, math.radians(28))
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 1.4
    nz.inputs['Detail'].default_value = 4.0
    nz.inputs['Distortion'].default_value = 1.2
    nt.links.new(mp.outputs['Vector'], nz.inputs['Vector'])
    wv = nt.nodes.new('ShaderNodeTexWave')
    wv.bands_direction = 'DIAGONAL'
    wv.inputs['Scale'].default_value = 0.55
    wv.inputs['Distortion'].default_value = 3.0
    wv.inputs['Detail'].default_value = 3.0
    nt.links.new(mp.outputs['Vector'], wv.inputs['Vector'])
    f = math_node(nt, 'MULTIPLY_ADD', nz.outputs['Fac'], 0.80)
    f.node.inputs[2].default_value = 0.0
    f = math_node(nt, 'ADD', f, math_node(nt, 'MULTIPLY', wv.outputs['Fac'], 0.30))
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.20, (0.004, 0.006, 0.025, 1)
    el[1].position, el[1].color = 0.98, (1.0, 0.92, 0.98, 1)
    for pos, col in ((0.40, (0.05, 0.12, 0.85, 1)), (0.58, (0.55, 0.10, 0.75, 1)), (0.74, (1.0, 0.18, 0.58, 1)),
                     (0.86, (0.25, 0.65, 1.0, 1))):
        e = el.new(pos)
        e.color = col
    nt.links.new(f, ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], p.inputs['Emission Color'])
    si(p, 'Emission Strength', 3.2)
    MAT['pc_lcd_art'] = m
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
    new_mat('pc_gpu_blue', (0.30, 0.48, 0.95), 0.34, metal=0.15, coat=0.3, bump=0.01, bscale=1500)
    new_mat('pc_gpu_blue_dark', (0.10, 0.22, 0.62), 0.35, metal=0.3, coat=0.3)
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
    m = new_mat('pc_glass_edge', (0.42, 0.74, 0.60), 0.04, rvar=0.0)
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
    mb_pcb_mat()
    dots_mat()
    lcd_art_mat()
    new_mat('pc_gpu_ice', (0.80, 0.83, 0.88), 0.32, metal=0.25, coat=0.2, bump=0.008, bscale=1500)
    new_mat('pc_fin_alu', (0.78, 0.80, 0.83), 0.30, metal=1.0, rvar=0.05)
    new_mat('pc_hub_silver', (0.86, 0.87, 0.89), 0.20, metal=1.0, bump=0.015, bscale=4000)
    m = new_mat('pc_gpu_blade_ice', (0.90, 0.92, 0.95), 0.40, rvar=0.0)
    si(pr(m), 'Transmission Weight', 0.35)
    new_mat('pc_smd_tan', (0.50, 0.40, 0.26), 0.45, rvar=0.0)
    new_mat('pc_smd_grey', (0.22, 0.22, 0.23), 0.4, metal=0.3, rvar=0.0)
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


def case_fan(mbF, mbR, M, size=0.120, depth=0.025, lcd=None):
    """120 mm fan, local +Z = the visible (intake/show) face; struts and motor on the -Z face."""
    h = size / 2
    Ri = 0.0585
    N = 48
    e, ch = 0.0018, 0.0012
    dirs = [(math.cos(2 * math.pi * (k + 0.5) / N), math.sin(2 * math.pi * (k + 0.5) / N)) for k in range(N)]
    tO = [rsq(dx, dy, h, 0.010) for dx, dy in dirs]
    d2 = depth / 2

    def ring(rad_fn, z):
        return [M @ V((dx * rad_fn(k), dy * rad_fn(k), z)) for k, (dx, dy) in enumerate(dirs)]
    I = lambda off: (lambda k: Ri + off)
    O = lambda off: (lambda k: tO[k] - off)
    Wt, LED = mbF.i('pc_white_plastic'), mbF.i('pc_rgb_led')
    prof = [(I(0), -d2 + ch), (I(ch), -d2), (I(0.0056), -d2), (O(e), -d2), (O(0), -d2 + e),
            (O(0), -0.0022), (O(0.0005), -0.0018), (O(0.0005), -0.0008), (O(0), -0.0004),
            (O(0), d2 - e - 0.0055), (O(0), d2 - e), (O(e), d2), (I(0.0056), d2), (I(ch), d2), (I(0), d2 - ch),
            (I(0), 0.0050), (I(0), -0.0050)]
    # parting groove round the frame's outer wall, light-strip band next to the show face, LED band in the throat
    DK = mbF.i('pc_port_dark')
    mis = [Wt, Wt, Wt, Wt, Wt, Wt, DK, Wt, Wt, LED, Wt, Wt, Wt, Wt, Wt, LED, Wt]
    rings = [ring(f, z) for f, z in prof]
    mbF.merge(loft_bm(rings, mis))
    # diagonal light bars across the four corners of the show face (chamfered "infinity" outline)
    for sx in (-1, 1):
        for sy in (-1, 1):
            th = math.atan2(sx, -sy)
            Mb_ = M @ Matrix.Translation((sx * (h - 0.0068), sy * (h - 0.0068), d2 + 0.0006)) @ Matrix.Rotation(th, 4, 'Z')
            box(mbF, (-0.0085, -0.0009, 0.0), (0.0085, 0.0009, 0.0006), 'pc_rgb_led', M=Mb_)
    if lcd:
        # stationary round LCD hub in front of the rotor: bezel here, the screen object is made later
        lathe(mbF, [(0.0, d2 - 0.0012), (0.0236, d2 - 0.0012), (0.0240, d2 + 0.0004), (0.0234, d2 + 0.0020),
                    (0.0212, d2 + 0.0024), (0.0197, d2 + 0.0020), (0.0197, d2 + 0.0012), (0.0, d2 + 0.0012)],
              'pc_white_alu', M, seg=48)
        lathe(mbF, [(0.0215, d2 + 0.00235), (0.0228, d2 + 0.00235), (0.0228, d2 + 0.0027), (0.0215, d2 + 0.0027)],
              'pc_rgb_led', M, seg=48)
        for k in range(3):
            Ms_ = M @ Matrix.Rotation(math.radians(90 + 120 * k), 4, 'Z')
            box(mbF, (0.0232, -0.0012, d2 - 0.0012), (Ri + 0.001, 0.0012, d2 - 0.0002), 'pc_white_plastic', M=Ms_)
        LCD_Q.append((M @ Matrix.Translation((0, 0, d2 + 0.0017)), lcd))
    # anti-vibration rubber corner pads    # anti-vibration rubber corner pads (L-shaped wrap over the corner) with the screw hole, both faces
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                Mc = M @ Matrix.Translation((sx * (h - 0.0071), sy * (h - 0.0071), sz * d2))
                box(mbF, (-0.0071, -0.0071, -0.0004 if sz > 0 else -0.0008), (0.0071, 0.0071, 0.0008 if sz > 0 else 0.0004),
                    'pc_white_rubber', r=0.0025, seg=1, M=Mc)
                lathe(mbF, [(0.0, 0.0), (0.0021, 0.0), (0.0021, 0.0002), (0.0, 0.0002)], 'pc_port_dark',
                      Mc @ frame((0, 0, sz * 0.0011), (0, 0, sz)), seg=12)
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
    rotor(mbR, M, 0.0205, 0.0562, -d2 + 0.0045, d2 - 0.0015, 7, 'pc_fan_blade', 'pc_white_plastic', nr=5, ns=6, sweep=26)


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


def _import(fn):
    before = set(bpy.data.objects)
    fn()
    return [o for o in bpy.data.objects if o not in before]


def _bake(new, M):
    """Bake each imported mesh's world transform followed by M into its data; drop empties."""
    meshes = []
    for o in new:
        if o.type == 'MESH':
            if o.data.users > 1:
                o.data = o.data.copy()
            W_ = M @ o.matrix_world
            o.parent = None
            o.data.transform(W_)
            if W_.determinant() < 0:
                bm = bmesh.new()
                bm.from_mesh(o.data)
                bmesh.ops.reverse_faces(bm, faces=bm.faces)
                bm.to_mesh(o.data)
                bm.free()
            o.matrix_world = Matrix.Identity(4)
            meshes.append(o)
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    return meshes


def _apply_mods(o):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = o.data
    o.modifiers.clear()
    o.data = me
    bpy.data.meshes.remove(old)


def optimise(o, angle=1.5, ratio=None):
    """Safe limited dissolve (UV/material/sharp delimited), optional collapse decimate."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(angle), use_dissolve_boundaries=False,
                             verts=list(bm.verts), edges=list(bm.edges), delimit={'UV', 'MATERIAL', 'SHARP'})
    bm.to_mesh(o.data)
    bm.free()
    if ratio:
        md = o.modifiers.new('dec', 'DECIMATE')
        md.ratio = ratio
        md.use_collapse_triangulate = False
        _apply_mods(o)


def _join(meshes, name):
    act = meshes[0]
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=act, selected_editable_objects=meshes, selected_objects=meshes):
            bpy.ops.object.join()
    act.name = name
    act.data.name = name
    return act


def _adopt(o, coll, root, objs):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    coll.objects.link(o)
    o.parent = root
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.matrix_basis = Matrix.Identity(4)
    objs.append(o)


def _principled(m):
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m and m.use_nodes else None


def _whiten(m, col=(0.86, 0.86, 0.85), rough=0.35, metal=0.0):
    """White/alu override that keeps normal (and roughness) maps but drops branded base-colour images."""
    p = _principled(m)
    if p is None:
        return
    for l in list(p.inputs['Base Color'].links):
        m.node_tree.links.remove(l)
    p.inputs['Base Color'].default_value = (*col, 1)
    si(p, 'Metallic', metal)
    if not p.inputs['Roughness'].links:
        si(p, 'Roughness', rough)
    for nm in ('Emission Strength',):
        si(p, nm, 0.0)


def _tint(m, tint=GPU_TINT):
    """Multiply the base colour (texture or value) by a light-blue tint, keeping texture detail."""
    p = _principled(m)
    if p is None:
        return
    nt = m.node_tree
    inp = p.inputs['Base Color']
    if inp.links:
        src = inp.links[0].from_socket
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        nt.links.new(src, sock(mix.inputs, 'A_Color'))
        sock(mix.inputs, 'B_Color').default_value = (*tint, 1)
        nt.links.new(sock(mix.outputs, 'Result_Color'), inp)
    else:
        c = inp.default_value
        inp.default_value = (c[0] * tint[0], c[1] * tint[1], c[2] * tint[2], 1)


def _external(img, name, clean=None):
    """Write a (packed/embedded) image to the git-ignored kit texture folder and reload it from there."""
    out = os.path.join(KIT_DIR, 'textures', 'pc_%s.png' % name)
    W_, H_ = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H_, W_, 4)
    if clean:
        clean(px)
    tmp = bpy.data.images.new('pc_tmp_px', W_, H_, alpha=True)
    tmp.pixels[:] = px.ravel()
    tmp.filepath_raw = out
    tmp.file_format = 'PNG'
    tmp.save()
    bpy.data.images.remove(tmp)
    new = bpy.data.images.load(out, check_existing=False)
    new.name = 'pc_%s' % name
    new.colorspace_settings.name = img.colorspace_settings.name
    new.alpha_mode = img.alpha_mode
    new.filepath = out                                         # made relative to parts/ on save
    img.user_remap(new)
    return new


def _fill_hubs(px):
    """Face photo (1024x512): repaint the three hub caps as plain brushed-silver discs (no text)."""
    H_, W_ = px.shape[:2]
    yy, xx = np.mgrid[0:H_, 0:W_]
    for cx, cy, r in ((208, 212, 55), (533, 206, 57), (839, 212, 56)):
        ry = H_ - 1 - cy
        d = np.sqrt((xx - cx) ** 2 + (yy - ry) ** 2)
        msk = d < r
        t = np.clip(d / r, 0, 1)
        base = 0.80 - 0.16 * t + 0.018 * np.sin(d * 1.3)
        for ch, k in ((0, 0.98), (1, 0.99), (2, 1.02)):
            px[..., ch] = np.where(msk, np.clip(base * k, 0, 1), px[..., ch])
        px[..., 3] = np.where(msk, 1.0, px[..., 3])


def _fill_edge(px):
    """Top-edge photo (1024x128): tile a clean stretch of the strip over the printed words/logos."""
    H_, W_ = px.shape[:2]
    src_x0, src_x1 = 490, 640

    def fill(x0, x1, y0, y1):
        r0, r1 = H_ - y1, H_ - y0
        patch = px[r0:r1, src_x0:src_x1].copy()
        w = src_x1 - src_x0
        for x in range(x0, x1, w):
            n = min(w, x1 - x)
            px[r0:r1, x:x + n] = patch[:, :n]
    for zone in ((55, 172, 76, 101), (196, 322, 68, 108), (334, 476, 76, 101), (664, 1006, 70, 110), (410, 610, 106, 127)):
        fill(*zone)


def import_mobo(coll, root, objs):
    """'MotherBoard + Components' by Daniel Cardona (Sketchfab, CC BY 4.0) -> white ATX board on the standoffs."""
    path = os.path.join(MOBO_DIR, 'source', 'maya2sketchfab.fbx')
    new = _import(lambda: bpy.ops.import_scene.fbx(filepath=path))
    S_, XF, Y0, ZT = 3.3116, 0.0415, 0.0794, 0.0447      # 92.1 x 73.2 model units -> 305 x 244 mm ATX
    M = Matrix(((0, S_, 0, 0.052 - Y0 * S_), (-S_, 0, 0, -0.030 + XF * S_), (0, 0, S_, 0.428 - ZT * S_), (0, 0, 0, 1)))
    meshes = _bake(new, M)
    # hidden under the pump block: socket, latch, retention frame, CPU
    hidden = {'CPULatch', 'CPULatchMountM', 'CPUBracketM', 'CPU_BaseM', 'CPULidM'}
    keep = []
    for o in meshes:
        mn = o.data.materials[0].name if o.data.materials and o.data.materials[0] else ''
        pts = [v.co for v in o.data.vertices]
        if not pts:
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        lo = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        under_pump = lo.x > 0.040 and lo.y > 0.036 and hi.y < 0.133 and lo.z > 0.291 and hi.z < 0.390
        if mn in hidden or under_pump:
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        if mn in ('CapacitorsM', 'Capacitor1M', 'CylinderPinM', 'Audio1m', 'Audio2m', 'Audio3m', 'Audio4m', 'Audio5m') \
                and len(o.data.polygons) > 40:
            md = o.modifiers.new('dec', 'DECIMATE')
            md.ratio = 0.3
            _apply_mods(o)
        keep.append(o)
    # textures: re-point to the (git-ignored) download folder, relative to parts/
    tex = {ntpath.splitext(f)[0].lower(): os.path.join(MOBO_DIR, 'textures', f)
           for f in os.listdir(os.path.join(MOBO_DIR, 'textures'))}
    for im in bpy.data.images:
        stem = ntpath.splitext(ntpath.basename(im.filepath))[0].lower()
        if stem in tex:
            im.filepath = tex[stem]
            im.reload()
    # all-white look: PCB, heatsinks, shrouds, slots, RAM; RGB bars take the build's pink/blue ramp
    mats = {m for o in keep for m in o.data.materials if m}
    for m in mats:
        n = m.name.split('.')[0]
        if n == 'BaseBoardM':
            continue
        if n in ('I_O_Cover', 'BoardPlate1m', 'BoardPlate2m', 'BoardChipsetM', 'BoardM2CoverM', 'BoardM2Cover1M'):
            _whiten(m, (0.87, 0.87, 0.86), 0.30, 0.35)
        elif n in ('BasePLasticM', 'WhiteBasePlasticM', 'Ram2M', 'Ram3M', 'Ram4M', 'lambert1', 'BatteryM'):
            _whiten(m, (0.86, 0.86, 0.85), 0.38, 0.0)
        elif n == 'M2_StickerM':
            _whiten(m, (0.20, 0.20, 0.21), 0.5, 0.0)
    for o in keep:
        for i, m in enumerate(o.data.materials):
            if not m:
                continue
            n = m.name.split('.')[0]
            if n == 'BaseBoardM':
                o.data.materials[i] = MAT['pc_mb_pcb']
            elif n == 'RGBM':
                o.data.materials[i] = MAT['pc_rgb_diffuser']
    board = _join(keep, 'pc_mobo_board')
    optimise(board, 1.0)
    board.data.shade_smooth()
    board.data.set_sharp_from_angle(angle=math.radians(35))
    _adopt(board, coll, root, objs)
    return board


def import_gpukit(coll, root, objs):
    """White GIGABYTE AERO-style card from the owner's GPU kit (licence unknown, local-only): other cards
    discarded, logos removed, tinted light blue, scaled to RTX 5070 AERO OC length (324 mm), in the top x16 slot."""
    path = os.path.join(KIT_DIR, 'source', 'gpukit.glb')
    new = _import(lambda: bpy.ops.import_scene.gltf(filepath=path))
    white = None
    for o in new:
        if o.parent is None and any(c.type == 'MESH' and c.data.materials and c.data.materials[0]
                                    and 'pearl_white' in c.data.materials[0].name for c in o.children_recursive):
            white = o
    ks = set([white] + list(white.children_recursive))
    for o in new:
        if o not in ks:
            bpy.data.objects.remove(o, do_unlink=True)
    new = [o for o in new if o in ks]
    s_ = 0.324 / 10.44                                        # bracket face -> far end = 10.44 kit units
    M = Matrix(((0, 0, -s_, 0.034 - 2.23 * s_), (0, -s_, 0, 0.2285 - 14.56 * s_), (-s_, 0, 0, 0.2465 - 0.70 * s_),
                (0, 0, 0, 1)))
    meshes = _bake(new, M)
    keep = []
    for o in meshes:
        mn = o.data.materials[0].name if o.data.materials and o.data.materials[0] else ''
        if mn.startswith('Material.015') or mn.startswith('Procedural_pearl'):   # hub logo glow + raised hub lettering
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        keep.append(o)
    mats = {m.name: m for o in keep for m in o.data.materials if m}
    metal = next((m for n_, m in mats.items() if n_.startswith('Metal')), None)
    for n_, m in mats.items():
        for node in m.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image and (node.image.packed_file or not node.image.filepath):
                if n_.startswith('Material.009'):
                    _external(node.image, 'gpu_face_clean', _fill_hubs)
                elif n_.startswith('Material.011'):
                    _external(node.image, 'gpu_edge_clean', _fill_edge)
                elif not n_.startswith('Material.012'):
                    _external(node.image, 'gpu_%s' % node.image.name.replace('.', '_'))
    for o in keep:
        for i, m in enumerate(o.data.materials):
            if m and m.name.startswith('Material.012') and metal:     # branded backplate photo -> plain metal
                o.data.materials[i] = metal
    for n_, m in mats.items():
        if any(n_.startswith(k) for k in ('Material.009', 'Material.011', 'Procedural_pearl', 'Procedural_Silver',
                                          'material_0', 'Metal')):
            _tint(m)
    for i, o in enumerate(keep):
        mn = o.data.materials[0].name if o.data.materials and o.data.materials[0] else 'part'
        heavy = len(o.data.polygons) > 8000
        optimise(o, 1.0, 0.30 if heavy else None)
        o.name = 'pc_gpukit_%02d_%s' % (i, mn.split('.')[0].lower()[:20])
        o.data.name = o.name
        _adopt(o, coll, root, objs)
    for im in list(bpy.data.images):                         # nothing embedded may survive into pc.blend
        if im.packed_file and im.users == 0:
            bpy.data.images.remove(im)
    return keep


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
    Z0, Z1 = 0.034, 0.440                  # inside floor / underside of the thin top rail (build coords)
    ZB, ZF = -0.023, -0.041                # underside of the thick base rail / bottom of the feet
    mb = MB('pc_case_base_rail', ['pc_white_alu'])
    box(mb, (-HW, -HD, ZB), (HW, HD, Z0), 'pc_white_alu', r=0.004, seg=3)
    base = done(mb)
    mb = MB('pc_case_base', ['pc_white_alu'])
    # seams, screw heads and the light strip along the base rail's top outer edge
    box(mb, (-HW - 0.0003, -HD + 0.012, -0.0150), (-HW + 0.0010, HD - 0.012, -0.0140), 'pc_port_dark')
    box(mb, (-HW + 0.012, -HD - 0.0003, -0.0150), (HW - 0.012, -HD + 0.0010, -0.0140), 'pc_port_dark')
    for vv in (-0.180, -0.090, 0.0, 0.090, 0.180):
        lathe(mb, [(0.0, 0.0), (0.0022, 0.0), (0.0022, 0.0005), (0.0014, 0.0009), (0.0, 0.0009)], 'pc_metal',
              frame((-HW, vv, 0.021), (-1, 0, 0)), seg=12)
    for uu in (-0.110, -0.050):
        lathe(mb, [(0.0, 0.0), (0.0022, 0.0), (0.0022, 0.0005), (0.0014, 0.0009), (0.0, 0.0009)], 'pc_metal',
              frame((uu, -HD, 0.021), (0, -1, 0)), seg=12)
    box(mb, (-HW - 0.0006, -HD + 0.012, Z0 - 0.0034), (-HW + 0.0004, HD - 0.012, Z0 - 0.0016), 'pc_rgb_strip')
    box(mb, (-HW + 0.012, -HD - 0.0006, Z0 - 0.0034), (HW - 0.012, -HD + 0.0004, Z0 - 0.0016), 'pc_rgb_strip')
    # four tapered feet with dark rubber soles
    for su in (-1, 1):
        ua, ub = (-HW + 0.010, -HW + 0.058) if su < 0 else (HW - 0.058, HW - 0.010)
        for sv in (-1, 1):
            prof_ = [(-HD + 0.004, ZB + 0.0005), (-HD + 0.080, ZB + 0.0005), (-HD + 0.066, ZF), (-HD + 0.014, ZF)]
            if sv > 0:
                prof_ = [(-v_, z_) for v_, z_ in prof_[::-1]]
            prism(mb, prof_, frame((ua, 0, 0), (1, 0, 0), (0, 1, 0)), 0.0, ub - ua, 'pc_white_alu', ch=0.0015)
            va, vb = sorted((sv * (HD - 0.018), sv * (HD - 0.062)))
            box(mb, (ua + 0.004, va, ZF - 0.0015), (ub - 0.004, vb, ZF + 0.0004), 'pc_rubber_dark', r=0.0008, seg=1)
    # fine filter mesh + fan rails on the chamber floor under the bottom fans
    box(mb, (-0.103, -0.176, Z0 - 0.0006), (0.014, 0.194, Z0 + 0.0005), 'pc_filter_mesh')
    for uu in (-0.1035, 0.0135):
        box(mb, (uu - 0.0008, -0.176, Z0 - 0.0006), (uu + 0.0008, 0.194, Z0 + 0.0008), 'pc_white_plastic')
    done(mb)

    # top frame with the mesh opening over the radiator
    mb = MB('pc_case_top', ['pc_white_alu'])
    box(mb, (-HW, -HD, Z1), (HW, HD, H), 'pc_white_alu', r=0.003, seg=3)
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
    # front I/O at the bottom corner: a recessed panel in the base rail's front face with power button
    # (LED ring), reset, USB-C, 2x USB-A, combo audio jack and an activity LED (local x along the rail,
    # y up, z out of the face)
    Mio = frame((0.078, -HD, (ZB + Z0) / 2), (0, -1, 0), (1, 0, 0))
    HP = -0.0006
    L_ = lambda a: Mio @ Matrix.Translation((a, 0, 0))
    AP, AR, AC, AA, AJ, AL = 0.049, 0.036, 0.026, (0.0145, 0.0015), -0.012, -0.024
    cuts = [cutter(coll, prism_bm(rrect(0.0960, 0.0240, 0.0040, 5), HP, 0.01), 'pc_white_alu'),
            cutter(coll, lathe_bm([(0.0, HP - 0.0030), (0.0086, HP - 0.0030), (0.0086, 0.01), (0.0, 0.01)], 48), 'pc_port_dark'),
            cutter(coll, lathe_bm([(0.0, HP - 0.0020), (0.0033, HP - 0.0020), (0.0033, 0.01), (0.0, 0.01)], 24), 'pc_port_dark'),
            cutter(coll, prism_bm(rrect(0.0032, 0.0090, 0.0015, 5), HP - 0.0070, 0.01), 'pc_metal'),
            cutter(coll, lathe_bm([(0.0, HP - 0.0090), (0.0019, HP - 0.0090), (0.0019, 0.01), (0.0, 0.01)], 20), 'pc_metal')]
    for c, a in zip(cuts, (0.012, AP, AR, AC, AJ)):
        c.matrix_world = T @ L_(a)
    for a in AA:
        c = cutter(coll, box_bm((-0.0024, -0.0064, HP - 0.0085), (0.0024, 0.0064, 0.01)), 'pc_metal')
        c.matrix_world = T @ L_(a)
        cuts.append(c)
    boolean_apply(base, cuts)
    mb = MB('pc_case_io', ['pc_white_alu'])
    lathe(mb, [(0.0074, HP - 0.0030), (0.0082, HP - 0.0030), (0.0082, HP - 0.0003), (0.0074, HP - 0.0003)], 'pc_led_white',
          L_(AP), seg=48)
    lathe(mb, [(0.0, HP - 0.0030), (0.0069, HP - 0.0030), (0.0069, HP + 0.0004), (0.0066, HP + 0.0010), (0.0056, HP + 0.0013),
               (0.0, HP + 0.0013)], 'pc_white_alu', L_(AP), seg=48)
    lathe(mb, [(0.0022, HP + 0.00125), (0.0026, HP + 0.00140), (0.0022, HP + 0.00150), (0.0, HP + 0.0015)], 'pc_white_pcb',
          L_(AP), seg=24)
    lathe(mb, [(0.0, HP - 0.0020), (0.0028, HP - 0.0020), (0.0028, HP - 0.0003), (0.0024, HP), (0.0, HP)], 'pc_white_alu',
          L_(AR), seg=24)
    Mc = L_(AC)
    ri, ro = rrect(0.0026, 0.0084, 0.0012, 5), rrect(0.0032, 0.0090, 0.0015, 5)
    R = lambda pts, z: [Mc @ V((p[0], p[1], z)) for p in pts]
    mb.merge(loft_bm([R(ri, HP - 0.0068), R(ri, HP), R(ro, HP), R(ro, HP - 0.0068)], 0), 'pc_metal')
    prism(mb, ro, Mc, HP - 0.0070, HP - 0.0068, 'pc_port_dark')
    box(mb, (-0.0003, -0.0033, HP - 0.0068), (0.0003, 0.0033, HP - 0.0012), 'pc_port_dark', M=Mc)
    for a in AA:
        Ma = L_(a)
        ri, ro = rrect(0.0044, 0.0122, 0.0002, 1), rrect(0.0048, 0.0128, 0.0002, 1)
        R = lambda pts, z, M_=Ma: [M_ @ V((p[0], p[1], z)) for p in pts]
        mb.merge(loft_bm([R(ri, HP - 0.0083), R(ri, HP), R(ro, HP), R(ro, HP - 0.0083)], 0), 'pc_metal')
        box(mb, (-0.0024, -0.0064, HP - 0.0085), (0.0024, 0.0064, HP - 0.0083), 'pc_port_dark', M=Ma)
        box(mb, (-0.0021, -0.0055, HP - 0.0083), (-0.0003, 0.0055, HP - 0.0012), 'pc_gpu_blue', M=Ma)
        for sx in (-0.0035, 0.0035):
            box(mb, (0.0019, sx - 0.0008, HP - 0.0030), (0.0022, sx + 0.0008, HP - 0.0010), 'pc_metal', M=Ma)
    Mj = L_(AJ)
    lathe(mb, [(0.0019, HP - 0.0088), (0.0019, HP), (0.0031, HP + 0.0002), (0.0034, HP), (0.0034, HP - 0.0003)],
          'pc_metal', Mj, seg=24)
    lathe(mb, [(0.0, HP - 0.0089), (0.0019, HP - 0.0089), (0.0019, HP - 0.0087), (0.0, HP - 0.0087)], 'pc_port_dark', Mj, seg=16)
    lathe(mb, [(0.0, HP), (0.0011, HP), (0.0011, HP + 0.0002), (0.0, HP + 0.0002)], 'pc_led_white', L_(AL), seg=12)
    for uu in (-0.100, 0.100):
        thumbscrew(mb, (uu, HD, (Z1 + H) / 2), (0, 1, 0), r=0.0042, L=0.005)
    done(mb)

    # glass: side (-u) and front (-v), pillarless front-left corner, 4 mm with arrised edges
    GZ0, GZ1 = Z0 + 0.0008, Z1 - 0.0012
    mb = MB('pc_glass_panels', ['pc_glass'])
    box(mb, (-HW, -HD + 0.0125, GZ0), (-HW + 0.004, HD - 0.0124, GZ1), 'pc_glass', r=0.0007, seg=1)
    box(mb, (-HW + 0.0125, -HD, GZ0), (HW, -HD + 0.004, GZ1), 'pc_glass', r=0.0007, seg=1)
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
    # light strips along the top rail's lower outer edges
    box(mb, (-HW - 0.0006, -HD + 0.012, Z1 + 0.0014), (-HW + 0.0004, HD - 0.012, Z1 + 0.0032), 'pc_rgb_strip')
    box(mb, (-HW + 0.012, -HD - 0.0006, Z1 + 0.0014), (HW - 0.012, -HD + 0.0004, Z1 + 0.0032), 'pc_rgb_strip')
    done(mb)
    # rear-left post + glass clips (the side glass hangs on it), right side panel, rear-chamber front cover
    mb = MB('pc_case_frame', ['pc_white_alu'])
    box(mb, (-HW, HD - 0.0118, Z0), (-HW + 0.012, HD, Z1), 'pc_white_alu', r=0.0025, seg=2)
    # slim white corner pillar where the front and side glass meet
    box(mb, (-HW, -HD, Z0), (-HW + 0.0120, -HD + 0.0120, Z1), 'pc_white_alu', r=0.0025, seg=2)
    for zz in (Z0 + 0.012, Z1 - 0.012):
        lathe(mb, [(0.0, 0.0), (0.0020, 0.0), (0.0020, 0.0005), (0.0012, 0.0008), (0.0, 0.0008)], 'pc_metal',
              frame((-HW + 0.006, -HD, zz), (0, -1, 0)), seg=12)
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
            cutter(coll, box_bm((-0.075, HD - 0.01, 0.087), (0.040, HD + 0.01, 0.257)), 'pc_white_steel'),
            cutter(coll, box_bm((0.062, HD - 0.01, 0.036), (0.142, HD + 0.01, 0.186)), 'pc_white_steel')]
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
    # 4 vented slot covers below the graphics card's 3-slot bracket
    for k in range(5):
        z0 = 0.0890 + k * 0.0203
        box(mb, (-0.073, HD - 0.0020, z0), (0.038, HD - 0.0004, z0 + 0.0185), 'pc_white_steel', r=0.0004, seg=1)
        for j in range(8):
            uu = -0.066 + j * 0.0125
            box(mb, (uu, HD - 0.0006, z0 + 0.0060), (uu + 0.0078, HD, z0 + 0.0125), 'pc_port_dark', r=0.0003, seg=1)
    box(mb, (0.040, HD - 0.0004, 0.085), (0.052, HD + 0.0022, 0.257), 'pc_white_steel', r=0.001, seg=1)
    for k in range(7):
        thumbscrew(mb, (0.046, HD + 0.0022, 0.0982 + k * 0.0203), (0, 1, 0), mat='pc_metal', r=0.0024, L=0.0022)
    done(mb)

    # motherboard tray with grommet openings
    TU0, TU1 = 0.058, 0.0605
    mb = MB('pc_mb_tray', ['pc_white_steel'])
    box(mb, (TU0, -HD + 0.0075, Z0), (TU1, HD - 0.003, Z1), 'pc_white_steel', r=0.0006, seg=1)
    tray = done(mb)
    holes = [(-0.076, -0.040, 0.285, 0.380), (-0.082, -0.046, 0.200, 0.268), (0.128, 0.170, 0.4295, 0.4385),
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
    box(mb, (0.063, 0.068, 0.036), (0.141, HD - 0.004, 0.185), 'pc_psu', r=0.003, seg=2)
    box(mb, (0.065, HD - 0.0045, 0.040), (0.139, HD - 0.0005, 0.181), 'pc_heatsink', r=0.001, seg=1)
    for k in range(12):
        zz = 0.100 + k * 0.0065
        box(mb, (0.068, HD - 0.0006, zz), (0.136, HD + 0.0001, zz + 0.0035), 'pc_port_dark')
    box(mb, (0.0895, HD - 0.001, 0.0585), (0.1205, HD + 0.004, 0.0835), 'pc_plug_black', r=0.0015, seg=2)
    box(mb, (0.126, HD - 0.001, 0.062), (0.136, HD + 0.003, 0.080), 'pc_plug_black', r=0.001, seg=1)
    for uu, zz in ((0.068, 0.043), (0.136, 0.043), (0.068, 0.178), (0.136, 0.178)):
        lathe(mb, [(0.0, 0.0), (0.0024, 0.0), (0.0024, 0.0008), (0.0016, 0.0013), (0.0, 0.0013)], 'pc_metal',
              frame((uu, HD, zz), (0, 1, 0)), seg=16)
    for zz, w in ((0.160, 0.024), (0.130, 0.018), (0.100, 0.018), (0.070, 0.018)):
        box(mb, (0.080, 0.0665, zz - 0.006), (0.080 + w, 0.0685, zz + 0.006), 'pc_port_dark', r=0.0005, seg=1)
    done(mb)

    # ------------------------------------------------------------------ motherboard (imported, all white)
    BU = 0.052
    import_mobo(coll, root, objs)
    mb = MB('pc_power_plugs', ['pc_white_plastic'])
    # 24-pin plug + comb on the board's 24-pin header, 8-pin EPS header + plug at the top edge
    box(mb, (0.0405, -0.040, 0.2995), (0.0525, -0.029, 0.3545), 'pc_white_plastic', r=0.0012, seg=1)
    box(mb, (0.0415, -0.047, 0.300), (0.0515, -0.044, 0.354), 'pc_white_plastic', r=0.0008, seg=1)
    box(mb, (0.0380, 0.1395, 0.4175), (BU, 0.1575, 0.4280), 'pc_dark_plastic', r=0.0008, seg=1)
    box(mb, (0.0400, 0.1400, 0.4225), (0.0500, 0.1570, 0.4290), 'pc_white_plastic', r=0.0008, seg=1)
    done(mb)
    mb = MB('pc_rear_io', ['pc_white_alu'])
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
        box(mb, (uc - 0.0062, HD - 0.0019, zc - 0.0023), (uc + 0.0062, HD + 0.0007, zc + 0.0023), 'pc_port_dark')
        box(mb, (uc - 0.0055, HD - 0.0017, zc - 0.0020), (uc + 0.0055, HD - 0.0004, zc - 0.0004), 'pc_gpu_blue')
    for zc in (0.380, 0.371, 0.312, 0.303):
        for uc in cols:
            usb_a(uc, zc)
    for uc in cols:
        Mu = frame((uc, HD - 0.0020, 0.3600), (0, 1, 0), (1, 0, 0))
        prism(mb, rrect(0.0094, 0.0036, 0.0017, 5), Mu, 0.0, 0.0023, 'pc_metal')
        prism(mb, rrect(0.0084, 0.0026, 0.0012, 5), Mu, 0.0, 0.0027, 'pc_port_dark')
    box(mb, (0.0265, HD - 0.0020, 0.3205), (0.0425, HD + 0.0003, 0.3345), 'pc_metal')
    box(mb, (0.0275, HD - 0.0019, 0.3215), (0.0415, HD + 0.0007, 0.3320), 'pc_port_dark')
    box(mb, (0.0275, HD + 0.0002, 0.3322), (0.0300, HD + 0.0005, 0.3340), 'pc_led_green')
    box(mb, (0.0390, HD + 0.0002, 0.3322), (0.0415, HD + 0.0005, 0.3340), 'pc_led_amber')
    for (uc, zc), col in zip(((0.0275, 0.290), (0.0415, 0.290), (0.0275, 0.279), (0.0415, 0.279), (0.0275, 0.268)),
                             ('pc_jack_blue', 'pc_jack_green', 'pc_jack_pink', 'pc_jack_orange', 'pc_metal')):
        Mj = frame((uc, HD - 0.0005, zc), (0, 1, 0))
        lathe(mb, [(0.0018, 0.0), (0.0042, 0.0), (0.0042, 0.0009), (0.0018, 0.0009)], col, Mj, seg=24)
        lathe(mb, [(0.0, -0.002), (0.0018, -0.002), (0.0018, 0.0006), (0.0, 0.0006)], 'pc_port_dark', Mj, seg=16)
    box(mb, (0.0375, HD - 0.0020, 0.2645), (0.0455, HD + 0.0005, 0.2715), 'pc_port_dark', r=0.0008, seg=1)
    done(mb)

    # ------------------------------------------------------------------ AIO: ROG Ryujin III 360 ARGB (white) pump block
    # 89 x 91 mm footprint centred on the socket, 101 mm tall with the tilted 3.5" LCD facing the glass,
    # on an LGA mounting bracket with four thumb nuts; tubes leave the -v side through black swivel fittings.
    CV_, CZ_ = 0.0845, 0.3405
    PV0, PV1, PZ0, PZ1 = CV_ - 0.0445, CV_ + 0.0445, CZ_ - 0.0455, CZ_ + 0.0455
    FB, FT = -0.049, -0.017                      # front face at the bottom / top edge (screen tilts back 18 deg)
    mb = MB('pc_cooler_pump', ['pc_white_plastic'])
    Mside = frame((0.0, PV0 + 0.0005, 0.0), (0, 1, 0), (1, 0, 0))            # local x = u, y = -z, extrude +v
    prof = [(0.0430, PZ0 + 0.004), (0.0430, PZ1 - 0.004), (0.0395, PZ1), (FT + 0.004, PZ1), (FT, PZ1 - 0.005),
            (FB, PZ0 + 0.006), (FB + 0.004, PZ0), (0.0395, PZ0)]
    prism(mb, [(u_, -z_) for u_, z_ in prof], Mside, 0.0, PV1 - PV0 - 0.001, 'pc_white_plastic', ch=0.003)
    # silver chassis rails along both side edges of the front, visor across the top
    for vv in (PV0 - 0.0006, PV1 - 0.0034):
        Mrail = frame((0.0, vv, 0.0), (0, 1, 0), (1, 0, 0))
        rail = [(FT + 0.004, PZ1 + 0.0008), (FT - 0.002, PZ1 + 0.0008), (FB - 0.003, PZ0 + 0.004), (FB + 0.012, PZ0 - 0.0008),
                (FB + 0.012, PZ0 + 0.004), (FT + 0.004, PZ1 - 0.004)]
        prism(mb, [(u_, -z_) for u_, z_ in rail], Mrail, 0.0, 0.004, 'pc_metal', ch=0.0006)
    box(mb, (FT - 0.002, PV0 - 0.0006, PZ1 - 0.0015), (0.0300, PV1 + 0.0006, PZ1 + 0.0035), 'pc_metal', r=0.0015, seg=2)
    box(mb, (0.000, PV0 + 0.010, PZ1 + 0.0035), (0.026, PV1 - 0.010, PZ1 + 0.0050), 'pc_white_alu', r=0.0006, seg=1)
    # tilted LCD bezel on the front face
    tvec = V((FT - FB, 0.0, (PZ1 - 0.005) - (PZ0 + 0.006))).normalized()
    nrm = V((-tvec.z, 0.0, tvec.x))                           # outward (toward the glass, slightly up)
    fc = V(((FB + FT) / 2, CV_, (PZ0 + PZ1) / 2 + 0.0005))
    Mface = Matrix(((0.0, tvec.x, nrm.x, fc.x), (1.0, 0.0, 0.0, fc.y), (0.0, tvec.z, nrm.z, fc.z), (0, 0, 0, 1)))
    if Mface.to_3x3().determinant() < 0:
        Mface = Mface @ Matrix.Scale(-1, 4, (1, 0, 0))
    ro, ri = rrect(0.0800, 0.0640, 0.0045, 5), rrect(0.0720, 0.0545, 0.0020, 5)
    R = lambda pts, z: [Mface @ V((p[0], p[1], z)) for p in pts]
    mb.merge(loft_bm([R(ri, -0.0010), R(ri, 0.0024), R(ro, 0.0024), R(ro, -0.0010)], 0), 'pc_metal')
    # LGA mounting bracket (behind the block) with four knurled thumb nuts on standoffs
    box(mb, (0.0430, CV_ - 0.050, CZ_ - 0.054), (0.0470, CV_ + 0.050, CZ_ + 0.054), 'pc_metal', r=0.004, seg=2)
    for dv in (-0.045, 0.045):
        for dz in (-0.049, 0.049):
            lathe(mb, [(0.0, 0.0), (0.0024, 0.0), (0.0024, 0.009), (0.0, 0.009)], 'pc_metal',
                  frame((BU, CV_ + dv, CZ_ + dz), (-1, 0, 0)), seg=12)
            thumbscrew(mb, (0.0430, CV_ + dv, CZ_ + dz), (-1, 0, 0), mat='pc_dark_plastic', r=0.0048, L=0.0065)
    # black swivel fittings on the top face; tubes run along the board's top edge to the radiator's rear tank
    FITS = ((0.012, 0.060), (0.012, 0.080))
    for uu, vv in FITS:
        Mf_ = frame((uu, vv, PZ1 + 0.0030), (0, 0, 1))
        lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.004), (0.0078, 0.0048), (0.0078, 0.0115), (0.0072, 0.012),
                   (0.0, 0.012)], 'pc_dark_plastic', Mf_, seg=24)
        prism(mb, star(12, 0.0090, 0.0084), Mf_, 0.0015, 0.0045, 'pc_dark_plastic')
    done(mb)
    # the LCD (own object: artwork shader in its local XY), 0.8 mm in front of the face, inside the bezel
    lm = bpy.data.meshes.new('pc_cooler_lcd')
    bm = bmesh.new()
    vs = [bm.verts.new((x_, y_, 0.0)) for x_, y_ in rrect(0.0726, 0.0550, 0.0020, 4)]
    bm.faces.new(vs)
    bm.to_mesh(lm)
    bm.free()
    lm.materials.append(MAT['pc_lcd_art'])
    lo_ = bpy.data.objects.new('pc_cooler_lcd', lm)
    coll.objects.link(lo_)
    lo_.parent = root
    lo_.matrix_basis = Mface @ Matrix.Translation((0, 0, 0.0008))
    objs.append(lo_)
    FRAMED.append(lo_)

    # ------------------------------------------------------------------ radiator 360 + top fans
    RU0, RU1, RZ0, RZ1 = -0.141, -0.021, 0.4095, 0.4395
    mb = MB('pc_radiator', ['pc_white_alu'])
    box(mb, (RU0, -0.175, RZ0), (RU1, -0.155, RZ1), 'pc_white_alu', r=0.004, seg=3)
    box(mb, (RU0, 0.2045, RZ0), (RU1, 0.2245, RZ1), 'pc_white_alu', r=0.004, seg=3)
    box(mb, (RU0 + 0.003, -0.156, RZ0 + 0.001), (RU1 - 0.003, 0.2055, RZ1 - 0.001), 'pc_rad_fins')
    for uu in (RU0, RU1 - 0.003):
        box(mb, (uu, -0.156, RZ0), (uu + 0.003, 0.2055, RZ1), 'pc_white_alu', r=0.0008, seg=1)
    for k in range(12):
        uu = RU0 + 0.0075 + k * 0.0095
        for z0, z1 in ((RZ0 + 0.0004, RZ0 + 0.0012), (RZ1 - 0.0012, RZ1 - 0.0004)):
            box(mb, (uu - 0.0009, -0.1555, z0), (uu + 0.0009, 0.2055, z1), 'pc_white_alu')
    for vv in (-0.1475, -0.0425, -0.0275, 0.0775, 0.0925, 0.1975):
        for uu, ax in ((RU0, -1), (RU1, 1)):
            lathe(mb, [(0.0, 0.0), (0.0022, 0.0), (0.0022, 0.0006), (0.0014, 0.0010), (0.0, 0.0010)], 'pc_metal',
                  frame((uu, vv, (RZ0 + RZ1) / 2), (ax, 0, 0)), seg=12)
    PORTS = (RU1, RU1)                            # port fittings on the rear tank's board-side face, stacked
    for zz in (0.4170, 0.4320):
        lathe(mb, [(0.0, 0.0), (0.0068, 0.0), (0.0068, 0.005), (0.0062, 0.0058), (0.0062, 0.012), (0.0, 0.012)],
              'pc_white_alu', frame((RU1 - 0.0005, 0.2145, zz), (1, 0, 0)), seg=32)
    done(mb)
    FZ = RZ0 - 0.015
    mbF, mbR = MB('pc_fans_frames', ['pc_white_plastic', 'pc_rgb_led']), MB('pc_fans_rotors', ['pc_fan_blade'])
    for vv in (-0.095, 0.025, 0.145):                       # Ryujin III ARGB fans (120 x 120 x 30) under the radiator
        case_fan(mbF, mbR, frame(((RU0 + RU1) / 2, vv, FZ), (0, 0, -1), (1, 0, 0)), depth=0.030)
        box(mbF, (RU0 - 0.0014, vv - 0.036, FZ - 0.0110), (RU0 + 0.0004, vv + 0.036, FZ - 0.0040), 'pc_rgb_strip', r=0.0005, seg=1)
    for vv in (-0.112, 0.008, 0.128):
        case_fan(mbF, mbR, frame((-0.045, vv, Z0 + 0.0125 + 0.003), (0, 0, 1), (1, 0, 0)))
    # vertical wall of 3 LCD-hub fans behind the front glass, on a slim bracket
    for zc, lcd in ((0.097, ('9%', 'LOAD')), (0.237, ('28\u00b0C', 'GPU')), (0.377, ('45\u00b0C', 'CPU'))):
        case_fan(mbF, mbR, frame((-0.045, -0.195, zc), (0, -1, 0), (1, 0, 0)), lcd=lcd)
    for uu in (-0.1085, 0.0185):
        box(mbF, (uu - 0.0025, -0.1855, Z0), (uu + 0.0025, -0.1780, Z1), 'pc_white_plastic', r=0.0008, seg=1)
    case_fan(mbF, mbR, frame((FAN_R[0], HD - 0.003 - 0.0125, FAN_R[1]), (0, -1, 0), (1, 0, 0)), lcd=('62%', 'FAN'))
    done(mbF)
    done(mbR, 60)

    # AIO tubes (white sleeved, 12.5 mm) from the pump fittings to the radiator ports
    mb = MB('pc_aio_tubes', ['pc_tube_white'])
    (ua_, va_), (ub_, vb_) = FITS
    PZT = PZ1 + 0.0030 + 0.012                    # top of the swivel fittings
    tA = [V((ua_, va_, PZT)), V((ua_, va_ + 0.001, PZT + 0.005)), V((0.004, va_ + 0.014, 0.4170)), V((-0.003, 0.110, 0.4170)),
          V((-0.003, 0.160, 0.4170)), V((0.004, 0.200, 0.4170)), V((0.004, 0.2145, 0.4170)), V((RU1 + 0.012, 0.2145, 0.4170))]
    tB = [V((ub_, vb_, PZT)), V((ub_, vb_ + 0.001, PZT + 0.006)), V((0.004, vb_ + 0.016, 0.4320)), V((-0.003, 0.110, 0.4320)),
          V((-0.003, 0.160, 0.4320)), V((0.004, 0.200, 0.4320)), V((0.004, 0.2145, 0.4320)), V((RU1 + 0.012, 0.2145, 0.4320))]
    for t in (tA, tB):
        tube(mb, t, 0.0063, 'pc_tube_white', sides=16, step=0.004)
        # crimp collars at both ends
        for p, q in ((t[0], t[1]), (t[-1], t[-2])):
            lathe(mb, [(0.0, 0.0), (0.0074, 0.0), (0.0074, 0.011), (0.0068, 0.012), (0.0, 0.012)], 'pc_white_alu',
                  frame(p, q - p), seg=24)
    # tube clip holding the pair together mid-run
    pa, pb = tA[3], tB[3]
    Mcl = frame((pa + pb) / 2, pb - pa, (0, 1, 0))
    L_ = (pb - pa).length
    box(mb, (-0.0035, -0.0045, -L_ / 2), (0.0035, 0.0045, L_ / 2), 'pc_white_plastic', r=0.0015, seg=2, M=Mcl)
    for p in (pa, pb):
        lathe(mb, [(0.0068, -0.0045), (0.0078, -0.0045), (0.0078, 0.0045), (0.0068, 0.0045)], 'pc_white_plastic',
              frame(p, (0, 1, 0)), seg=24)
    done(mb, 50)

    # ------------------------------------------------------------------ GPU (owner's kit card, top x16 slot)
    import_gpukit(coll, root, objs)
    GPV = 0.037                                  # 12V-2x6 socket on the card's top (glass-side) edge
    mb = MB('pc_gpu_power_plug', ['pc_white_plastic'])
    box(mb, (-0.0930, GPV - 0.0118, 0.2325), (-0.0815, GPV + 0.0118, 0.2465), 'pc_white_plastic', r=0.0010, seg=1)
    box(mb, (-0.0915, GPV - 0.0040, 0.2463), (-0.0845, GPV + 0.0040, 0.2481), 'pc_white_plastic', r=0.0005, seg=1)
    box(mb, (-0.0927, GPV - 0.0110, 0.2440), (-0.0870, GPV + 0.0110, 0.2466), 'pc_port_dark')
    done(mb)

    # ------------------------------------------------------------------ sleeved cables
    mb = MB('pc_cables_sleeved', ['pc_sleeve_white'])
    # 24-pin: 12 rows (z) x 2 columns (u), out of the plug toward -v, bending +u through the grommet
    ribbon(mb, [V((0.0465, -0.040, 0.327)), V((0.0465, -0.047, 0.327)), V((0.0475, -0.054, 0.327)),
                V((0.054, -0.057, 0.327)), V((0.063, -0.058, 0.327)), V((0.075, -0.058, 0.327))],
           12, 2, 0.0043, 0.0040, 0.00185, (0, 0, 1), 'pc_sleeve_white')
    # 12V-2x6 from the GPU top edge up and over into the lower grommet
    pts, fr = ribbon(mb, [V((-0.0930, GPV, 0.2395)), V((-0.0990, GPV, 0.2395)), V((-0.1180, GPV - 0.018, 0.2360)),
                          V((-0.1240, -0.040, 0.2320)), V((-0.1200, -0.100, 0.2300)), V((-0.095, -0.124, 0.230)),
                          V((-0.050, -0.132, 0.232)), V((0.008, -0.118, 0.234)), V((0.044, -0.078, 0.236)),
                          V((0.060, -0.064, 0.236)), V((0.080, -0.064, 0.236))],
                     6, 2, 0.0036, 0.0036, 0.00165, (0, 1, 0), 'pc_sleeve_white', sides=6, step=0.005)
    for f_ in (0.16, 0.34, 0.52, 0.72):
        tie(mb, pts, fr, f_, 0.0216, 0.0072, 'pc_white_plastic')
    # EPS 8-pin x2 straight up into the top notch
    for v0 in (0.1485,):
        ribbon(mb, [V((0.045, v0, 0.4290)), V((0.045, v0, 0.4315)), V((0.050, v0, 0.4335)), V((0.058, v0, 0.4340)),
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
                     6, 2, 0.0058, 0.0058, 0.0027, (0, 0, 1), 'pc_cable_black', sides=4, step=0.010)
    tie(mb, pts, fr, 0.35, 0.035, 0.0115)
    tie(mb, pts, fr, 0.62, 0.035, 0.0115)
    pts, fr = ribbon(mb, [V((0.082, -0.064, 0.236)), V((0.095, -0.056, 0.232)), V((0.118, -0.020, 0.226)),
                          V((0.122, 0.030, 0.212)), V((0.112, 0.052, 0.150)), V((0.095, 0.059, 0.133)),
                          V((0.089, 0.0645, 0.130))],
                     3, 2, 0.0058, 0.0058, 0.0027, (0, 1, 0), 'pc_cable_black', sides=4, step=0.010)
    tie(mb, pts, fr, 0.45, 0.0175, 0.0115)
    for k, v0 in enumerate((0.1485,)):
        zt = (0.100, 0.070)[k]
        pts, fr = ribbon(mb, [V((0.074, v0, 0.434)), V((0.082, v0, 0.428)), V((0.090, v0 - 0.012, 0.400)),
                              V((0.110, 0.085, 0.330)), V((0.130, 0.062 - k * 0.008, 0.260)),
                              V((0.130, 0.056 - k * 0.004, 0.190)), V((0.110, 0.060, zt + 0.004)),
                              V((0.090, 0.0645, zt))],
                         2, 2, 0.0058, 0.0058, 0.0027, (0, 1, 0), 'pc_cable_black', sides=4, step=0.010)
        tie(mb, pts, fr, 0.55 if k == 0 else 0.40, 0.0175, 0.0115)
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
    SX_ = Matrix.Scale(-1, 4, (1, 0, 0)) if MIRROR else I4
    TIB = SX_ @ Matrix.Translation((0, 0, -DZ)) @ TI          # world -> build coords (undoes lift + mirror)
    SOCK = V((0.2600, 1.2350, 0.0))
    Mp = TIB @ Matrix.Translation(SOCK)
    lathe(mb, [(0.0, 0.0235), (0.0182, 0.0235), (0.0185, 0.0385), (0.0192, 0.0400), (0.0192, 0.0460), (0.0186, 0.0470),
               (0.0186, 0.0520), (0.0192, 0.0530), (0.0190, 0.0680), (0.0170, 0.0780), (0.0120, 0.0860),
               (0.0070, 0.0900), (0.0052, 0.0905), (0.0046, 0.0990), (0.0, 0.0990)], 'pc_plug_black', Mp, seg=40)
    world_path = [V((0.2600, 1.2350, 0.0980)), V((0.2600, 1.2340, 0.1080)), V((0.2620, 1.2220, 0.1190)),
                  V((0.2660, 1.2010, 0.1060)), V((0.2700, 1.1910, 0.0620)), V((0.2760, 1.1905, 0.0200)),
                  V((0.2920, 1.1940, 0.0035)), V((0.3400, 1.1960, 0.0035)), V((0.4000, 1.1920, 0.0035)),
                  V((0.4420, 1.1640, 0.0035)), V((0.4570, 1.1500, 0.0280)), V((0.4600, 1.1470, 0.3000)),
                  V((0.4580, 1.1460, 0.6400)), V((0.4520, 1.1430, 0.7250)), V((0.4450, 1.1330, 0.7480)),
                  V((0.4390, 1.1100, 0.7800)), V((0.4370, 1.0900, 0.8230))]
    local_tail = [V((0.105, HD + 0.062, 0.070)), V((0.105, HD + 0.054, 0.071))]
    path = [TIB @ p for p in world_path] + local_tail
    tube(mb, path, 0.0034, 'pc_cable_black', sides=10, per=10, step=0.006)
    done(mb, 50)

    # LCD fan-hub screens (object coords scaled so the pump-screen shader fits the 39 mm disc) + readouts
    for k, (Ml, (big, small)) in enumerate(LCD_Q):
        sc = 0.0195 / 0.029
        me = bpy.data.meshes.new('pc_lcd_%d' % k)
        bm = lathe_bm([(0.0, 0.0), (0.0290, 0.0)], seg=64)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MAT['pc_pump_screen'])
        o = bpy.data.objects.new('pc_lcd_%d' % k, me)
        coll.objects.link(o)
        o.parent = root
        o.matrix_basis = Ml @ Matrix.Scale(sc, 4)
        objs.append(o)
        FRAMED.append(o)
        for j, (txt, size, dy) in enumerate(((big, 0.0074, 0.0008), (small, 0.0032, -0.0072))):
            cu_ = bpy.data.curves.new('pc_lcd_txt', 'FONT')
            cu_.body = txt
            cu_.size = size
            cu_.align_x = 'CENTER'
            cu_.align_y = 'CENTER'
            t_ = bpy.data.objects.new('tmp_t', cu_)
            coll.objects.link(t_)
            bpy.context.view_layer.update()
            tmm = bpy.data.meshes.new_from_object(t_.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            bpy.data.objects.remove(t_, do_unlink=True)
            bpy.data.curves.remove(cu_)
            tmm.name = 'pc_lcd_%d_text%d' % (k, j)
            tmm.materials.clear()
            tmm.materials.append(MAT['pc_screen_text'])
            to_ = bpy.data.objects.new(tmm.name, tmm)
            coll.objects.link(to_)
            to_.parent = root
            to_.matrix_basis = Ml @ Matrix.Translation((0.0, dy, 0.0004))
            objs.append(to_)
            FRAMED.append(to_)
    # lift everything onto the thick base (build floor -> world) and mirror to the reverse layout;
    # framed objects keep proper rotations (their own local X is flipped back so text reads correctly)
    SX = Matrix.Scale(-1, 4, (1, 0, 0)) if MIRROR else I4
    LIFT = Matrix.Translation((0, 0, DZ))
    for o in objs:
        if o in FRAMED:
            o.matrix_basis = LIFT @ SX @ o.matrix_basis @ SX
            continue
        o.data.transform(LIFT @ SX)
        if MIRROR:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
            bm.to_mesh(o.data)
            bm.free()
        o.data.update()
    bpy.context.view_layer.update()
    tris = {}
    for o in objs:
        tris[o.name] = sum(len(p.vertices) - 2 for p in o.data.polygons)
    total = sum(tris.values())
    print('TRIS', total, sorted(tris.items(), key=lambda x: -x[1]))
    # world bbox of the case body (without the mains cable) for clearance reporting
    cw = [T @ V((sx * HW, sy * HD, 0)) for sx in (-1, 1) for sy in (-1, 1)]
    print('WORLD_BBOX', [tuple(round(x, 3) for x in (min(p[i] for o in objs if o.type == 'MESH' and not o.name.startswith('pc_power')
                                                            for p in [o.matrix_world @ V(c) for c in o.bound_box]),
                                                        max(p[i] for o in objs if o.type == 'MESH' and not o.name.startswith('pc_power')
                                                            for p in [o.matrix_world @ V(c) for c in o.bound_box])))
                         for i in range(3)])
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
    fl.from_pydata([(C.x - 3, C.y - 3, C.z), (C.x + 3, C.y - 3, C.z), (C.x + 3, C.y + 3, C.z), (C.x - 3, C.y + 3, C.z)], [], [(0, 1, 2, 3)])
    fm = bpy.data.materials.new('prev_floor')
    fm.use_nodes = True
    pr(fm).inputs['Base Color'].default_value = (0.30, 0.28, 0.26, 1)
    pr(fm).inputs['Roughness'].default_value = 0.6
    fl.materials.append(fm)
    fo = bpy.data.objects.new('prev_floor', fl)
    scene.collection.objects.link(fo)
    tmp.append(fo)
    mid = T @ V((0, 0, 0.25))

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
    if not only or '34' in only:        # reference-like 3/4 on the glass corner (side face dominant)
        d_ = V((math.sin(math.radians(35)), -math.cos(math.radians(35)), 0.0))
        shot(mid + d_ * 1.15 + V((0, 0, 0.10)), mid + V((0, 0, -0.01)), 45, 'pc_34.png', (1000, 1150))
    if not only or 'seat' in only:
        shot(SEAT, mid, 40, 'pc_seat.png')
    if not only or 'lcd_pump' in only:   # pump-head LCD through the side glass
        shot(V((0.612, 0.815, 1.145)), V((0.627, 0.978, 1.114)), 70, 'pc_lcd_pump.png')
    if not only or 'lcd_fan' in only:    # middle vertical-fan hub LCD through the front glass
        shot(V((1.080, 0.885, 1.045)), V((0.933, 0.925, 1.013)), 70, 'pc_lcd_fan.png')
    if not only or 'gpuref' in only:     # GPU alone, reference-photo angle (fan side, bracket end, PCIe edge)
        keep = {o for o in scene.objects if o.name.startswith('pc_gpu')}
        hid = [o for o in scene.objects if o.type == 'MESH' and o not in keep and o not in tmp]
        for o in hid:
            o.hide_render = True
        shot(V((0.300, 1.075, 0.815)), V((0.620, 0.950, 0.960)), 44, 'pc_gpu_ref.png', (1100, 1100))
        for o in hid:
            o.hide_render = False
    if not only or 'board' in only:      # board + pump LCD through the side glass
        shot(V((0.575, 0.615, 1.160)), V((0.650, 0.960, 1.095)), 36, 'pc_board.png')
    if not only or 'gpu' in only:        # GPU from slightly below through the side glass
        shot(V((0.560, 0.660, 0.895)), V((0.690, 0.930, 0.972)), 42, 'pc_gpu.png')
    if not only or 'mobo' in only:       # motherboard through the side glass
        shot(V((0.600, 0.700, 1.110)), V((0.655, 1.020, 1.060)), 40, 'pc_mobo.png')
    if not only or 'io' in only:
        shot(V((1.180, 0.960, 0.860)), V((0.9705, 1.045, 0.780)), 50, 'pc_io.png')
    if not only or 'rear' in only:
        shot(mid + V((-0.85, 0.30, 0.30)), mid + V((-0.20, 0.0, -0.08)), 32, 'pc_rear.png')
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)


def finish(b):
    for o in list(bpy.context.scene.objects):
        if o.name not in b['coll'].all_objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    bpy.ops.file.make_paths_relative()                         # external textures -> //../../../assets/source/...
    packed = [i.name for i in bpy.data.images if i.packed_file]
    print('PACKED_IMAGES', packed, 'EXTERNAL', sorted(i.filepath for i in bpy.data.images if not i.packed_file)[:40])
    bpy.ops.wm.save_mainfile(compress=True)
    print('SAVED', OUT_BLEND)


if __name__ == '__main__':
    b = build()
    if not NO_RENDER:
        previews(b)
    finish(b)
    print('DONE')
