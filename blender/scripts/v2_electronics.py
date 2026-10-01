"""
v2_electronics.py -- dev boards, aluminium USB hub + braided cable, ceramic mug, spiral notepad + pencil.

    "<blender.exe>" -b --factory-startup --python blender/scripts/v2_electronics.py -- [--no-render] [--only=a,b]

Writes blender/scene/parts/electronics.blend: collection NEW_electronics, root empty NEW_electronics_root
(identity transform). One child empty per item carries its room transform; meshes are modelled in mm
and stored in metres under those empties, so everything sits at its true room position.

Measured in blender/scene/room.blend (Z-up, metres, desk top 0.735):
  old boards  Scene.012 (0.44,0.64) yaw 0.42 | Scene.013 (0.97,0.74) yaw -0.70 | Scene.014 (0.70,1.07) standing,
              PCB 70x52 mm each.  Scene.012 overlapped the old notebook stack and a small alu bead
              (Mesh_146 at 0.43,0.61); Scene.013 overhung the desk's right edge (x 1.013 > 1.000);
              Scene.014 floated, leaning forward with nothing in front and partly inside the bin (Node_141).
  old hub     Scene.015 origin (0.30,0.96) yaw 0.24; body 88 x 42 x 16 mm at local y -46.5..-4.5
  old mug     Scene.008 (-0.50,0.50) yaw 0.5 (left of the keyboard)  -> moves to the RIGHT (owner)
  old notes   Node_352 (0.50,0.50) yaw -0.35 (right front)          -> moves to the LEFT (owner)
  NEW_keyboard x -0.231..0.131, y 0.366..0.504;  NEW_mouse x 0.293..0.367, y 0.393..0.507
  screwdriver Scene.017 x 0.513..0.641 y 0.48..0.636; coil Scene.016 x 0.783..0.941 y 0.562..0.70
  speedcube Node_107 x -0.378..-0.282 y 0.571..0.668; lamp Node_62 x -0.836..-0.591 y >= 0.916
  MacBook right USB-C: laptop-local (0.1563 flank, 0.0536, 0.0058), world tongue (0.1016,0.7611,0.8104),
  laptop tilted 16.9 deg about X (NEW_macbook_laptop).  Bin right wall x 0.675 (z 0.74) .. 0.684 (z 0.77).

New placements
  Uno-style board   (0.440, 0.660) yaw 0.42 rad, resting on its through-hole tails (+1.8 mm) -- nudged
                    +20 mm in y to clear Mesh_146; five Dupont jumpers in the far headers.
  ESP32 DevKit-style (0.955, 0.740) yaw -0.70 rad, standing on its down-facing pin headers (+8.5 mm);
                    nudged 15 mm left so it no longer overhangs the desk edge.
  Pico-style board  leaning against the bin's right wall at y 1.045 (the old third board's spot).
  hub               same footprint as the old one; braided cable to the MacBook's right USB-C port.
  mug               (0.720, 0.460), handle toward the right-front.
  notepad + pencil  (-0.520, 0.520) yaw 12 deg, left of the keyboard (old mug spot).
"""
import bpy
import bmesh
import math
import os
import random
import sys
import numpy as np
from mathutils import Vector as V, Matrix, geometry

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
ROOM = os.path.join(REPO, 'blender', 'scene', 'room.blend')
NAME = 'electronics'
OUT = os.path.join(PARTS, f'{NAME}.blend')
TMP = os.path.join(os.environ.get('TEMP', '/tmp'), 'elec_tex')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
RENDER = '--no-render' not in ARGS
ONLY = None
for a in ARGS:
    if a.startswith('--only='):
        ONLY = a.split('=', 1)[1].split(',')

MM = 0.001
DESK = 0.735
RNG = random.Random(11)
np.random.seed(5)

REPLACES = ['Scene.012', 'board_pcb', 'board_rings', 'board_parts', 'board_cap', 'board_header', 'board_metal',
            'board_usb', 'board_usb_tongue',
            'Scene.013', 'board_pcb.001', 'board_rings.001', 'board_parts.001', 'board_cap.001',
            'board_header.001', 'board_metal.001', 'board_usb.001', 'board_usb_tongue.001',
            'Scene.014', 'board_pcb.002', 'board_rings.002', 'board_parts.002', 'board_cap.002',
            'board_header.002', 'board_metal.002', 'board_usb.002', 'board_usb_tongue.002',
            'Scene.015', 'hub_body', 'hub_tongues', 'hub_led_blue', 'hub_led_green', 'hub_feet', 'hub_cable',
            'Scene.008', 'mug', 'mug_handle', 'mug_coffee',
            'Node_352', 'Mesh_249', 'Mesh_250', 'Mesh_251', 'Mesh_252', 'Mesh_253']


def T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, 'Z')


def Rx(deg):
    return Matrix.Rotation(math.radians(deg), 4, 'X')


def Ry(deg):
    return Matrix.Rotation(math.radians(deg), 4, 'Y')


def lin(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


# ============================================================================ materials
MATS = {}


def _bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def setin(node, name, val):
    if name in node.inputs:
        node.inputs[name].default_value = val


def node(nt, typ, loc=(0, 0), **kw):
    n = nt.nodes.new(typ)
    n.location = loc
    for k, v in kw.items():
        if k in n.inputs:
            n.inputs[k].default_value = v
        else:
            setattr(n, k, v)
    return n


def math_n(nt, op, a=None, b=None, loc=(0, 0)):
    n = nt.nodes.new('ShaderNodeMath')
    n.operation = op
    n.location = loc
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    MATS[name] = m
    return m, m.node_tree, _bsdf(m)


def pbr(name, col, rough, metal=0.0, rvar=0.05, rscale=700.0, bump=0.0, bscale=2500.0, bdist=0.00015,
        coat=0.0, coat_rough=0.08, emit=None, estr=0.0, trans=0.0, sheen=0.0, sss=0.0, ior=None, aniso=0.0):
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'Base Color', (*lin(col), 1))
    setin(b, 'Metallic', metal)
    setin(b, 'Roughness', rough)
    setin(b, 'Coat Weight', coat)
    setin(b, 'Coat Roughness', coat_rough)
    setin(b, 'Transmission Weight', trans)
    setin(b, 'Sheen Weight', sheen)
    setin(b, 'Subsurface Weight', sss)
    setin(b, 'Anisotropic', aniso)
    if ior:
        setin(b, 'IOR', ior)
    if emit:
        setin(b, 'Emission Color', (*lin(emit), 1))
        setin(b, 'Emission Strength', estr)
    tc = node(nt, 'ShaderNodeTexCoord', (-1000, 0))
    if rvar > 0:
        nz = node(nt, 'ShaderNodeTexNoise', (-800, 250), Scale=rscale, Detail=3.0)
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        mr = node(nt, 'ShaderNodeMapRange', (-550, 250))
        mr.inputs['To Min'].default_value = max(rough - rvar, 0.0)
        mr.inputs['To Max'].default_value = min(rough + rvar, 1.0)
        nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    if bump > 0:
        nz2 = node(nt, 'ShaderNodeTexNoise', (-800, -250), Scale=bscale, Detail=6.0)
        nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
        bp = node(nt, 'ShaderNodeBump', (-350, -250), Strength=bump, Distance=bdist)
        nt.links.new(nz2.outputs['Fac'], bp.inputs['Height'])
        nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


def std_mats():
    pbr('fr4_edge', (0.60, 0.57, 0.40), 0.55, sss=0.1, bump=0.3, bscale=4000)
    pbr('plate_gold', (0.95, 0.77, 0.45), 0.2, 1.0)
    pbr('plate_tin', (0.80, 0.80, 0.80), 0.22, 1.0)
    pbr('solder', (0.80, 0.80, 0.80), 0.12, 1.0, rvar=0.06, bump=0.15, bscale=3000)
    pbr('tin_lead', (0.84, 0.84, 0.84), 0.22, 1.0)
    pbr('ic_black', (0.035, 0.035, 0.04), 0.55, rvar=0.08, bump=0.08, bscale=9000, bdist=0.00003)
    pbr('ic_dimple', (0.05, 0.05, 0.055), 0.28)
    pbr('plastic_black', (0.03, 0.03, 0.033), 0.42, rvar=0.06, bump=0.05, bscale=6000, bdist=0.00003)
    pbr('plastic_white', (0.86, 0.85, 0.82), 0.45)
    pbr('cer_tan', (0.52, 0.42, 0.30), 0.5)
    pbr('res_white', (0.82, 0.82, 0.80), 0.55)
    pbr('res_black', (0.03, 0.03, 0.03), 0.45)
    pbr('polyfuse', (0.62, 0.62, 0.22), 0.5)
    pbr('nickel', (0.80, 0.80, 0.79), 0.26, 1.0, rvar=0.07, bump=0.04, bscale=4000, bdist=0.00003)
    pbr('alu_can', (0.87, 0.88, 0.89), 0.3, 1.0, rvar=0.05)
    pbr('gold', (1.0, 0.79, 0.42), 0.18, 1.0)
    pbr('led_body', (0.93, 0.93, 0.91), 0.4)
    pbr('led_red_on', (1.0, 0.15, 0.08), 0.15, trans=0.3, emit=(1.0, 0.08, 0.03), estr=6.0)
    pbr('led_green_on', (0.3, 1.0, 0.3), 0.15, trans=0.3, emit=(0.15, 1.0, 0.2), estr=5.0)
    pbr('led_yellow_off', (0.95, 0.75, 0.2), 0.12, trans=0.4)
    pbr('led_blue_on', (0.4, 0.6, 1.0), 0.15, trans=0.3, emit=(0.25, 0.5, 1.0), estr=8.0)
    pbr('led_white_on', (0.9, 0.95, 1.0), 0.15, trans=0.2, emit=(0.8, 0.9, 1.0), estr=6.0)
    pbr('usb3_blue', (0.04, 0.22, 0.72), 0.4)
    pbr('port_dark', (0.012, 0.012, 0.014), 0.6)
    pbr('wire_red', (0.78, 0.07, 0.05), 0.32, coat=0.2)
    pbr('wire_black', (0.035, 0.035, 0.035), 0.35, coat=0.2)
    pbr('wire_yellow', (0.92, 0.74, 0.08), 0.32, coat=0.2)
    pbr('wire_blue', (0.08, 0.28, 0.80), 0.32, coat=0.2)
    pbr('wire_green', (0.08, 0.55, 0.22), 0.32, coat=0.2)
    pbr('hub_alu', (0.36, 0.37, 0.39), 0.36, 1.0, rvar=0.05, rscale=300, bump=0.12, bscale=12000, bdist=0.00002)
    pbr('alu_diamond', (0.86, 0.87, 0.89), 0.1, 1.0, aniso=0.6)
    pbr('rubber', (0.025, 0.025, 0.025), 0.8, bump=0.2, bscale=5000)
    pbr('tpe_black', (0.04, 0.04, 0.042), 0.55, rvar=0.06)
    pbr('bisque', (0.66, 0.58, 0.48), 0.85, rvar=0.08, bump=0.5, bscale=3000, bdist=0.0002)
    pbr('board_chip', (0.46, 0.41, 0.34), 0.9, bump=0.4, bscale=2500)
    pbr('cover', (0.06, 0.09, 0.14), 0.55, rvar=0.08, bump=0.25, bscale=1500, bdist=0.0001)
    pbr('spiral_wire', (0.78, 0.78, 0.8), 0.25, 1.0)
    pbr('pencil_paint', (0.98, 0.70, 0.06), 0.28, coat=0.5, coat_rough=0.12, rvar=0.04, bump=0.05, bscale=3000)
    pbr('wood', (0.80, 0.62, 0.44), 0.72, bump=0.35, bscale=1800)
    pbr('graphite', (0.12, 0.12, 0.13), 0.35, 0.45)
    pbr('ferrule', (0.86, 0.76, 0.42), 0.3, 1.0, rvar=0.06)
    pbr('eraser', (0.95, 0.56, 0.56), 0.8, bump=0.3, bscale=2500, sss=0.1)
    pbr('chrome', (0.90, 0.90, 0.91), 0.12, 1.0, rvar=0.03)
    pbr('rot_pearl', (0.93, 0.92, 0.89), 0.34, coat=0.35, coat_rough=0.2, rvar=0.05, bump=0.04, bscale=6000,
        bdist=0.00002)
    knurl_mat()


def braid_mat():
    name = 'braid_nylon'
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'Roughness', 0.55)
    setin(b, 'Sheen Weight', 0.4)
    uv = node(nt, 'ShaderNodeTexCoord', (-1600, 0))
    sep = node(nt, 'ShaderNodeSeparateXYZ', (-1400, 0))
    nt.links.new(uv.outputs['UV'], sep.inputs[0])
    U, Vv = sep.outputs[0], sep.outputs[1]
    N, K = 12.0, 17.0
    vn = math_n(nt, 'MULTIPLY', Vv, N)
    uk = math_n(nt, 'MULTIPLY', U, K)
    a = math_n(nt, 'ADD', vn, uk)
    bb = math_n(nt, 'SUBTRACT', vn, uk)
    fa = math_n(nt, 'FRACT', a)
    fb = math_n(nt, 'FRACT', bb)
    par = math_n(nt, 'FLOORED_MODULO', math_n(nt, 'ADD', math_n(nt, 'FLOOR', a), math_n(nt, 'FLOOR', bb)), 2.0)
    sa = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', fa, math.pi))
    sb = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', fb, math.pi))
    # fibres across each strand
    fia = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', fb, math.pi * 10))
    fib = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', fa, math.pi * 10))
    ha = math_n(nt, 'ADD', sa, math_n(nt, 'MULTIPLY', fia, 0.12))
    hb = math_n(nt, 'ADD', sb, math_n(nt, 'MULTIPLY', fib, 0.12))
    mix = node(nt, 'ShaderNodeMix', (-300, -200))
    mix.data_type = 'FLOAT'
    nt.links.new(par, mix.inputs['Factor'])
    nt.links.new(hb, mix.inputs[2])
    nt.links.new(ha, mix.inputs[3])
    h = mix.outputs[0]
    bp = node(nt, 'ShaderNodeBump', (0, -300), Strength=0.9, Distance=0.00025)
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    cm = node(nt, 'ShaderNodeMix', (-100, 200))
    cm.data_type = 'RGBA'
    nt.links.new(par, cm.inputs['Factor'])
    cm.inputs[6].default_value = (*lin((0.07, 0.072, 0.078)), 1)
    cm.inputs[7].default_value = (*lin((0.11, 0.112, 0.12)), 1)
    shade = math_n(nt, 'ADD', math_n(nt, 'MULTIPLY', h, 0.45), 0.55)
    cm2 = node(nt, 'ShaderNodeMix', (100, 200))
    cm2.data_type = 'RGBA'
    cm2.blend_type = 'MULTIPLY'
    cm2.inputs['Factor'].default_value = 1.0
    nt.links.new(cm.outputs[2], cm2.inputs[6])
    nt.links.new(shade, cm2.inputs[7])
    nt.links.new(cm2.outputs[2], b.inputs['Base Color'])
    return name


def glaze_mat():
    name = 'mug_glaze'
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'Roughness', 0.06)
    setin(b, 'IOR', 1.52)
    tc = node(nt, 'ShaderNodeTexCoord', (-1600, 0))
    base = lin((0.90, 0.86, 0.78))
    speck = lin((0.30, 0.20, 0.13))
    brk = lin((0.74, 0.60, 0.44))
    # pooling / thickness variation
    nz = node(nt, 'ShaderNodeTexNoise', (-1300, 300), Scale=40.0, Detail=3.0)
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    pool = math_n(nt, 'ADD', math_n(nt, 'MULTIPLY', nz.outputs['Fac'], 0.10), 0.95)
    spk = None
    for sc, thr, kp in ((260.0, 0.07, 0.55), (700.0, 0.09, 0.45)):
        vo = node(nt, 'ShaderNodeTexVoronoi', (-1300, -200), Scale=sc)
        nt.links.new(tc.outputs['Object'], vo.inputs['Vector'])
        near = math_n(nt, 'LESS_THAN', vo.outputs['Distance'], thr)
        sepc = node(nt, 'ShaderNodeSeparateColor', (-1100, -300))
        nt.links.new(vo.outputs['Color'], sepc.inputs[0])
        keep = math_n(nt, 'GREATER_THAN', sepc.outputs[0], kp)
        s = math_n(nt, 'MULTIPLY', near, keep)
        spk = s if spk is None else math_n(nt, 'MAXIMUM', spk, s)
    # glaze breaks toward the clay colour over the rolled lip
    sxyz = node(nt, 'ShaderNodeSeparateXYZ', (-1300, 600))
    nt.links.new(tc.outputs['Object'], sxyz.inputs[0])
    mr = node(nt, 'ShaderNodeMapRange', (-1100, 600))
    mr.inputs['From Min'].default_value = 0.0885
    mr.inputs['From Max'].default_value = 0.0902
    nt.links.new(sxyz.outputs[2], mr.inputs['Value'])
    c1 = node(nt, 'ShaderNodeMix', (-700, 300))
    c1.data_type = 'RGBA'
    nt.links.new(mr.outputs['Result'], c1.inputs['Factor'])
    c1.inputs[6].default_value = (*base, 1)
    c1.inputs[7].default_value = (*brk, 1)
    c1.inputs['Factor'].default_value = 0
    k = math_n(nt, 'MULTIPLY', mr.outputs['Result'], 0.55)
    nt.links.new(k, c1.inputs['Factor'])
    c2 = node(nt, 'ShaderNodeMix', (-500, 300))
    c2.data_type = 'RGBA'
    nt.links.new(math_n(nt, 'MULTIPLY', spk, 0.85), c2.inputs['Factor'])
    nt.links.new(c1.outputs[2], c2.inputs[6])
    c2.inputs[7].default_value = (*speck, 1)
    c3 = node(nt, 'ShaderNodeMix', (-300, 300))
    c3.data_type = 'RGBA'
    c3.blend_type = 'MULTIPLY'
    c3.inputs['Factor'].default_value = 1.0
    nt.links.new(c2.outputs[2], c3.inputs[6])
    nt.links.new(pool, c3.inputs[7])
    nt.links.new(c3.outputs[2], b.inputs['Base Color'])
    # faint glaze orange-peel
    nz2 = node(nt, 'ShaderNodeTexNoise', (-800, -500), Scale=900.0, Detail=2.0)
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    bp = node(nt, 'ShaderNodeBump', (-300, -500), Strength=0.06, Distance=0.0001)
    nt.links.new(nz2.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


def coffee_mat():
    name = 'mug_coffee_liquid'
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'IOR', 1.34)
    tc = node(nt, 'ShaderNodeTexCoord', (-1500, 0))
    sx = node(nt, 'ShaderNodeSeparateXYZ', (-1300, 0))
    nt.links.new(tc.outputs['Object'], sx.inputs[0])
    r = math_n(nt, 'SQRT', math_n(nt, 'ADD', math_n(nt, 'MULTIPLY', sx.outputs[0], sx.outputs[0]),
                                  math_n(nt, 'MULTIPLY', sx.outputs[1], sx.outputs[1])))
    nz = node(nt, 'ShaderNodeTexNoise', (-1300, -300), Scale=350.0, Detail=4.0)
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    rp = math_n(nt, 'ADD', r, math_n(nt, 'MULTIPLY', math_n(nt, 'SUBTRACT', nz.outputs['Fac'], 0.5), 0.0018))
    mr = node(nt, 'ShaderNodeMapRange', (-900, 0))
    mr.inputs['From Min'].default_value = 0.0322
    mr.inputs['From Max'].default_value = 0.0356
    nt.links.new(rp, mr.inputs['Value'])
    f = mr.outputs['Result']
    vo = node(nt, 'ShaderNodeTexVoronoi', (-1300, -600), Scale=2500.0)
    nt.links.new(tc.outputs['Object'], vo.inputs['Vector'])
    cm = node(nt, 'ShaderNodeMix', (-500, 200))
    cm.data_type = 'RGBA'
    nt.links.new(f, cm.inputs['Factor'])
    cm.inputs[6].default_value = (*lin((0.07, 0.035, 0.018)), 1)
    cm.inputs[7].default_value = (*lin((0.46, 0.29, 0.15)), 1)
    nt.links.new(cm.outputs[2], b.inputs['Base Color'])
    rr_ = node(nt, 'ShaderNodeMapRange', (-500, -100))
    rr_.inputs['To Min'].default_value = 0.02
    rr_.inputs['To Max'].default_value = 0.4
    nt.links.new(f, rr_.inputs['Value'])
    nt.links.new(rr_.outputs['Result'], b.inputs['Roughness'])
    h = math_n(nt, 'MULTIPLY', vo.outputs['Distance'], f)
    bp = node(nt, 'ShaderNodeBump', (-200, -400), Strength=0.4, Distance=0.00015)
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


def knurl_mat():
    """chrome with a diamond knurl bump around the pencil axis (object X)."""
    name = 'knurl_chrome'
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'Base Color', (*lin((0.86, 0.86, 0.87)), 1))
    setin(b, 'Metallic', 1.0)
    setin(b, 'Roughness', 0.26)
    tc = node(nt, 'ShaderNodeTexCoord', (-1400, 0))
    sx = node(nt, 'ShaderNodeSeparateXYZ', (-1200, 0))
    nt.links.new(tc.outputs['Object'], sx.inputs[0])
    th = math_n(nt, 'ARCTAN2', sx.outputs[2], sx.outputs[1])
    arc = math_n(nt, 'MULTIPLY', th, 0.0039)
    k = 2 * math.pi / 0.00075
    a = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', math_n(nt, 'ADD', sx.outputs[0], arc), k))
    c = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', math_n(nt, 'SUBTRACT', sx.outputs[0], arc), k))
    h = math_n(nt, 'ABSOLUTE', math_n(nt, 'MULTIPLY', a, c))
    bp = node(nt, 'ShaderNodeBump', (-200, -200), Strength=1.0, Distance=0.00012)
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


def sticky_texture():
    cv = Canvas(76.0, 76.0, 10.0)
    rng = random.Random(9)
    for li, y in enumerate((20.0, 12.0, 4.0, -4.0, -13.0)):
        x = -30.0
        while True:
            wl = rng.uniform(6.0, 15.0)
            if x + wl > 30.0 - (12 if li == 4 else 0):
                break
            scribble(cv, x, y, wl, 2.1, rng, rng.uniform(0.45, 0.65), 0.34)
            x += wl + rng.uniform(2.5, 3.5)
    cv.poly('ink', [(-30.0, 1.5), (-6.0, 1.0)], 0.3, val=0.5)
    H, W = cv.H, cv.W
    ink = np.clip(cv.layer('ink'), 0, 1)
    tooth = np.random.RandomState(4).rand(H, W).astype(np.float32)
    ink = ink * (0.6 + 0.4 * tooth)
    base = np.array((0.99, 0.93, 0.56), np.float32)
    ys = np.linspace(0, 1, H)[:, None, None]
    col = base * (1 + 0.015 * (tooth[..., None] - 0.5)) * (0.97 + 0.03 * ys)
    col = col * (1 - ink[..., None]) + np.array((0.36, 0.36, 0.38), np.float32) * ink[..., None]
    dat = np.stack([0.5 + 0.1 * (tooth - 0.5) - 0.12 * ink, 0.82 - 0.4 * ink, ink * 0.1], -1)
    ic = make_image('elec_sticky_col', col)
    idt = make_image('elec_sticky_dat', dat, noncolor=True)
    return image_mat('sticky_yellow_written', ic, idt, bump_dist=0.0001, sss=0.05, rnoise=0.02)


def paper_edge_mat():
    name = 'paper_edge'
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'Roughness', 0.85)
    setin(b, 'Subsurface Weight', 0.05)
    tc = node(nt, 'ShaderNodeTexCoord', (-1200, 0))
    sx = node(nt, 'ShaderNodeSeparateXYZ', (-1000, 0))
    nt.links.new(tc.outputs['Object'], sx.inputs[0])
    nz = node(nt, 'ShaderNodeTexNoise', (-1000, -300), Scale=300.0, Detail=2.0)
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    zz = math_n(nt, 'ADD', sx.outputs[2], math_n(nt, 'MULTIPLY', nz.outputs['Fac'], 0.00004))
    s = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', zz, 2 * math.pi / 0.0001))
    v = math_n(nt, 'ADD', math_n(nt, 'MULTIPLY', s, 0.035), 0.93)
    comb = node(nt, 'ShaderNodeCombineColor', (-300, 200))
    nt.links.new(v, comb.inputs[0])
    nt.links.new(math_n(nt, 'MULTIPLY', v, 0.985), comb.inputs[1])
    nt.links.new(math_n(nt, 'MULTIPLY', v, 0.95), comb.inputs[2])
    nt.links.new(comb.outputs[0], b.inputs['Base Color'])
    bp = node(nt, 'ShaderNodeBump', (-200, -300), Strength=0.5, Distance=0.00005)
    nt.links.new(s, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


def image_mat(name, img_col, img_dat, coat=0.0, coat_from_metal=False, bump_dist=0.00003, sss=0.0,
              rnoise=0.04):
    m, nt, b = new_mat(name)
    tc = node(nt, 'ShaderNodeTexCoord', (-1400, 0))
    ic = node(nt, 'ShaderNodeTexImage', (-1100, 300))
    ic.image = img_col
    idt = node(nt, 'ShaderNodeTexImage', (-1100, -100))
    idt.image = img_dat
    for n in (ic, idt):
        nt.links.new(tc.outputs['UV'], n.inputs['Vector'])
    nt.links.new(ic.outputs['Color'], b.inputs['Base Color'])
    sep = node(nt, 'ShaderNodeSeparateColor', (-800, -100))
    nt.links.new(idt.outputs['Color'], sep.inputs[0])
    nz = node(nt, 'ShaderNodeTexNoise', (-1100, -500), Scale=2500.0, Detail=3.0)
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    rgh = math_n(nt, 'ADD', sep.outputs[1], math_n(nt, 'MULTIPLY', math_n(nt, 'SUBTRACT', nz.outputs['Fac'], 0.5),
                                                   rnoise * 2))
    nt.links.new(rgh, b.inputs['Roughness'])
    nt.links.new(sep.outputs[2], b.inputs['Metallic'])
    if coat > 0:
        cw = math_n(nt, 'MULTIPLY', math_n(nt, 'SUBTRACT', 1.0, sep.outputs[2]), coat)
        nt.links.new(cw, b.inputs['Coat Weight'])
        setin(b, 'Coat Roughness', 0.1)
    setin(b, 'Subsurface Weight', sss)
    bp = node(nt, 'ShaderNodeBump', (-400, -300), Strength=1.0, Distance=bump_dist)
    nt.links.new(sep.outputs[0], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


def make_image(name, arr, noncolor=False):
    H, W, _ = arr.shape
    img = bpy.data.images.new(name, W, H, alpha=False, is_data=noncolor)
    if noncolor:
        img.colorspace_settings.name = 'Non-Color'
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, name + '.png')
    img.filepath_raw = p
    img.file_format = 'PNG'
    img.save()
    img.pack()
    return img


# ============================================================================ mesh building
class MB:
    def __init__(self, name, scale=MM):
        self.name = name
        self.bm = bmesh.new()
        self.scale = scale
        self.mats = []
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.flist = []

    def mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def verts(self, pts, M=None):
        out = []
        for p in pts:
            p = V(p) if len(p) == 3 else V((p[0], p[1], 0.0))
            if M is not None:
                p = M @ p
            out.append(self.bm.verts.new(p * self.scale))
        return out

    def face(self, vs, mat, smooth=True, uvs=None):
        try:
            f = self.bm.faces.new(vs)
        except ValueError:
            return None
        f.material_index = self.mi(mat)
        f.smooth = smooth
        if uvs:
            for l, uv in zip(f.loops, uvs):
                l[self.uv].uv = uv
        self.flist.append(f)
        return f

    def mark(self):
        return len(self.flist)

    def recalc(self, k):
        fs = [f for f in self.flist[k:] if f.is_valid]
        if fs:
            bmesh.ops.recalc_face_normals(self.bm, faces=fs)

    def tris(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    def finish(self, parent, coll, sharp=38.0, name=None):
        bm = self.bm
        thr = math.radians(sharp)
        for e in bm.edges:
            if len(e.link_faces) == 2:
                if e.calc_face_angle(0.0) > thr:
                    e.smooth = False
        me = bpy.data.meshes.new(name or self.name)
        bm.to_mesh(me)
        bm.free()
        for mname in self.mats:
            me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(name or self.name, me)
        coll.objects.link(ob)
        ob.parent = parent
        return ob


def loft(mb, loops, mat, M=None, closed=True, cap0=False, cap1=False, smooth=True, capmat=None, mats=None,
         us=None, cap0mat=None):
    rings = [mb.verts(L, M) for L in loops]
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        m = mats[i] if mats else mat
        if len(a) == 1 and len(b) == 1:
            continue
        n = max(len(a), len(b))
        for j in range(n if closed else n - 1):
            k = (j + 1) % n
            uvs = None
            if us is not None:
                uvs = [(us[i], j / n), (us[i], (j + 1) / n), (us[i + 1], (j + 1) / n), (us[i + 1], j / n)]
            if len(a) == 1:
                mb.face([a[0], b[k], b[j]], m, smooth)
            elif len(b) == 1:
                mb.face([a[j], a[k], b[0]], m, smooth)
            else:
                mb.face([a[j], a[k], b[k], b[j]], m, smooth, uvs)
    if cap0 and len(rings[0]) > 2:
        mb.face(list(reversed(rings[0])), cap0mat or capmat or mat, smooth=False)
    if cap1 and len(rings[-1]) > 2:
        mb.face(rings[-1], capmat or mat, smooth=False)
    return rings


def rr(w, d, r, seg, z=0.0):
    hw, hd = w / 2, d / 2
    if seg == 0:
        return [(hw, -hd, z), (hw, hd, z), (-hw, hd, z), (-hw, -hd, z)]
    r = max(min(r, hw - 1e-5, hd - 1e-5), 1e-5)
    pts = []
    for cx, cy, a0 in ((hw - r, -hd + r, -90), (hw - r, hd - r, 0), (-hw + r, hd - r, 90), (-hw + r, -hd + r, 180)):
        for s in range(seg + 1):
            a = math.radians(a0 + 90 * s / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    return pts


def slab(mb, mat, M, w, d, h, rc=0.0, seg=0, rt=0.0, tseg=1, rb=0.0, bseg=1, topmat=None, botcap=True, z0=0.0,
         botmat=None):
    k = mb.mark()
    loops = []
    if rb > 0:
        for s in range(bseg + 1):
            ph = math.pi / 2 * s / bseg
            ins = rb - rb * math.sin(ph)
            loops.append(rr(w - 2 * ins, d - 2 * ins, rc - ins, seg, z0 + rb - rb * math.cos(ph)))
    else:
        loops.append(rr(w, d, rc, seg, z0))
    if rt > 0:
        for s in range(tseg + 1):
            ph = math.pi / 2 * s / tseg
            ins = rt - rt * math.cos(ph)
            loops.append(rr(w - 2 * ins, d - 2 * ins, rc - ins, seg, z0 + h - rt + rt * math.sin(ph)))
    else:
        loops.append(rr(w, d, rc, seg, z0 + h))
    rings = loft(mb, loops, mat, M)
    if botcap:
        mb.face(list(reversed(rings[0])), botmat or mat, smooth=False)
    mb.face(rings[-1], topmat or mat, smooth=False)
    return rings


def box(mb, mat, M, cx, cy, cz, w, d, h):
    return slab(mb, mat, M @ T(cx, cy, cz - h / 2), w, d, h)


def revolve(mb, prof, seg, mat, M=None, mats=None, a0=0.0, a1=2 * math.pi, closed=True):
    loops = []
    n = seg if closed else seg + 1
    for r, z in prof:
        if r <= 1e-9:
            loops.append([(0.0, 0.0, z)])
        else:
            loops.append([(r * math.cos(a0 + (a1 - a0) * k / seg), r * math.sin(a0 + (a1 - a0) * k / seg), z)
                          for k in range(n)])
    return loft(mb, loops, mat, M, closed=closed, mats=mats)


def prism(mb, mat, M, loop2d, z0, z1, topmat=None, botmat=None):
    k = mb.mark()
    rings = loft(mb, [[(x, y, z0) for x, y in loop2d], [(x, y, z1) for x, y in loop2d]], mat, M)
    mb.face(list(reversed(rings[0])), botmat or mat, smooth=False)
    mb.face(rings[-1], topmat or mat, smooth=False)
    mb.recalc(k)
    return rings


def stadium(w, h, seg=6):
    """2-D stadium (w along x, h along y) CCW."""
    r = h / 2
    pts = []
    for cx, a0 in ((w / 2 - r, -90), (-w / 2 + r, 90)):
        for s in range(seg + 1):
            a = math.radians(a0 + 180 * s / seg)
            pts.append((cx + r * math.cos(a), r * math.sin(a)))
    return pts


def frames(path, up=None):
    n = len(path)
    Ts = []
    for i in range(n):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        Ts.append((b - a).normalized())
    u = V(up) if up is not None else (V((0, 0, 1)) if abs(Ts[0].z) < 0.9 else V((1, 0, 0)))
    nrm = (u - Ts[0] * u.dot(Ts[0])).normalized()
    Ns, Bs = [], []
    for i in range(n):
        if i > 0:
            ax = Ts[i - 1].cross(Ts[i])
            if ax.length > 1e-9:
                ang = Ts[i - 1].angle(Ts[i])
                nrm = Matrix.Rotation(ang, 3, ax.normalized()) @ nrm
            nrm = (nrm - Ts[i] * nrm.dot(Ts[i])).normalized()
        Ns.append(nrm.copy())
        Bs.append(Ts[i].cross(nrm))
    return Ts, Ns, Bs


def sweep(mb, path, section, mat, M=None, up=None, us=None, cap0=False, cap1=False, mats=None):
    path = [V(p) for p in path]
    Ts, Ns, Bs = frames(path, up)
    loops = []
    for i, p in enumerate(path):
        sec = section(i, len(path)) if callable(section) else section
        loops.append([p + Ns[i] * x + Bs[i] * y for x, y in sec])
    return loft(mb, loops, mat, M, us=us, cap0=cap0, cap1=cap1, mats=mats)


def circle2(r, n):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def spline(pts, step):
    pts = [V(p) for p in pts]
    dense = []
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        for k in range(24):
            t = k / 24
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(pts[-1])
    L = [0.0]
    for a, b in zip(dense[:-1], dense[1:]):
        L.append(L[-1] + (b - a).length)
    n = max(2, int(L[-1] / step) + 1)
    out = []
    j = 0
    for k in range(n + 1):
        s = L[-1] * k / n
        while j < len(L) - 2 and L[j + 1] < s:
            j += 1
        seg = L[j + 1] - L[j] or 1e-9
        t = (s - L[j]) / seg
        out.append(dense[j].lerp(dense[j + 1], min(max(t, 0), 1)))
    return out, L[-1]


# ============================================================================ texture painter
FONT_SRC = {
    '0': "01110 10001 10011 10101 11001 10001 01110", '1': "00100 01100 00100 00100 00100 00100 01110",
    '2': "01110 10001 00001 00010 00100 01000 11111", '3': "11111 00010 00100 00010 00001 10001 01110",
    '4': "00010 00110 01010 10010 11111 00010 00010", '5': "11111 10000 11110 00001 00001 10001 01110",
    '6': "00110 01000 10000 11110 10001 10001 01110", '7': "11111 00001 00010 00100 01000 01000 01000",
    '8': "01110 10001 10001 01110 10001 10001 01110", '9': "01110 10001 10001 01111 00001 00010 01100",
    'A': "01110 10001 10001 11111 10001 10001 10001", 'B': "11110 10001 10001 11110 10001 10001 11110",
    'C': "01110 10001 10000 10000 10000 10001 01110", 'D': "11100 10010 10001 10001 10001 10010 11100",
    'E': "11111 10000 10000 11110 10000 10000 11111", 'F': "11111 10000 10000 11110 10000 10000 10000",
    'G': "01110 10001 10000 10111 10001 10001 01111", 'H': "10001 10001 10001 11111 10001 10001 10001",
    'I': "01110 00100 00100 00100 00100 00100 01110", 'J': "00111 00010 00010 00010 00010 10010 01100",
    'K': "10001 10010 10100 11000 10100 10010 10001", 'L': "10000 10000 10000 10000 10000 10000 11111",
    'M': "10001 11011 10101 10101 10001 10001 10001", 'N': "10001 10001 11001 10101 10011 10001 10001",
    'O': "01110 10001 10001 10001 10001 10001 01110", 'P': "11110 10001 10001 11110 10000 10000 10000",
    'Q': "01110 10001 10001 10001 10101 10010 01101", 'R': "11110 10001 10001 11110 10100 10010 10001",
    'S': "01111 10000 10000 01110 00001 00001 11110", 'T': "11111 00100 00100 00100 00100 00100 00100",
    'U': "10001 10001 10001 10001 10001 10001 01110", 'V': "10001 10001 10001 10001 10001 01010 00100",
    'W': "10001 10001 10001 10101 10101 10101 01010", 'X': "10001 10001 01010 00100 01010 10001 10001",
    'Y': "10001 10001 01010 00100 00100 00100 00100", 'Z': "11111 00001 00010 00100 01000 10000 11111",
    '+': "00000 00100 00100 11111 00100 00100 00000", '-': "00000 00000 00000 11111 00000 00000 00000",
    '.': "00000 00000 00000 00000 00000 01100 01100", '/': "00001 00001 00010 00100 01000 10000 10000",
    '~': "00000 00000 01000 10101 00010 00000 00000", ' ': "00000 00000 00000 00000 00000 00000 00000",
}
FONT = {k: np.array([[c == '1' for c in row] for row in v.split()], bool) for k, v in FONT_SRC.items()}


def lowfreq(H, W, cell, seed):
    rs = np.random.RandomState(seed)
    g = rs.rand(H // cell + 3, W // cell + 3).astype(np.float32)
    ys = np.arange(H) / cell
    xs = np.arange(W) / cell
    y0 = ys.astype(int)
    x0 = xs.astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


class Canvas:
    def __init__(s, w, h, ppmm):
        s.w, s.h, s.p = w, h, ppmm
        s.W = int(round(w * ppmm))
        s.H = int(round(h * ppmm))
        s.L = {}

    def layer(s, name):
        if name not in s.L:
            s.L[name] = np.zeros((s.H, s.W), np.float32)
        return s.L[name]

    def win(s, x0, y0, x1, y1):
        i0 = max(int((x0 + s.w / 2) * s.p) - 1, 0)
        i1 = min(int((x1 + s.w / 2) * s.p) + 2, s.W)
        j0 = max(int((y0 + s.h / 2) * s.p) - 1, 0)
        j1 = min(int((y1 + s.h / 2) * s.p) + 2, s.H)
        if i1 <= i0 or j1 <= j0:
            return None
        xs = (np.arange(i0, i1) + 0.5) / s.p - s.w / 2
        ys = (np.arange(j0, j1) + 0.5) / s.p - s.h / 2
        X, Y = np.meshgrid(xs, ys)
        return (slice(j0, j1), slice(i0, i1)), X, Y

    def sdf(s, name, bb, fn, val=1.0, sub=False):
        w = s.win(*bb)
        if w is None:
            return
        sl, X, Y = w
        a = np.clip(0.5 - fn(X, Y) * s.p, 0, 1) * val
        L = s.layer(name)
        if sub:
            L[sl] *= (1 - a)
        else:
            np.maximum(L[sl], a, out=L[sl])

    def circle(s, name, x, y, r, **k):
        s.sdf(name, (x - r, y - r, x + r, y + r), lambda X, Y: np.hypot(X - x, Y - y) - r, **k)

    def ring(s, name, x, y, r0, r1, **k):
        rm, hw = (r0 + r1) / 2, (r1 - r0) / 2
        s.sdf(name, (x - r1, y - r1, x + r1, y + r1), lambda X, Y: np.abs(np.hypot(X - x, Y - y) - rm) - hw, **k)

    def rect(s, name, x, y, w, h, ang=0.0, r=0.0, lw=None, **k):
        c, sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        R = math.hypot(w, h) / 2 + (lw or 0)

        def fn(X, Y):
            u = (X - x) * c + (Y - y) * sn
            v = -(X - x) * sn + (Y - y) * c
            qx = np.abs(u) - w / 2 + r
            qy = np.abs(v) - h / 2 + r
            d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
            if lw:
                d = np.abs(d) - lw / 2
            return d
        s.sdf(name, (x - R, y - R, x + R, y + R), fn, **k)

    def seg(s, name, x0, y0, x1, y1, wd, **k):
        r = wd / 2

        def fn(X, Y):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-9
            t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0, 1)
            return np.hypot(X - x0 - t * dx, Y - y0 - t * dy) - r
        s.sdf(name, (min(x0, x1) - r, min(y0, y1) - r, max(x0, x1) + r, max(y0, y1) + r), fn, **k)

    def poly(s, name, pts, wd, **k):
        for a, b in zip(pts[:-1], pts[1:]):
            s.seg(name, a[0], a[1], b[0], b[1], wd, **k)

    def text(s, txt, x, y, hmm, ang=0, anchor='c', name='silk', val=1.0):
        cell = hmm / 7.0
        px = max(int(round(cell * s.p)), 1)
        cols = []
        for ch in txt.upper():
            cols.append(FONT.get(ch, FONT[' ']))
            cols.append(np.zeros((7, 1), bool))
        if not cols:
            return
        bmp = np.concatenate(cols[:-1], axis=1)[::-1]
        bmp = np.kron(bmp, np.ones((px, px), bool)).astype(np.float32) * val
        tl = (len(txt) * 6 - 1) * cell
        dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        if anchor == 'l':
            x, y = x + dx * tl / 2, y + dy * tl / 2
        elif anchor == 'r':
            x, y = x - dx * tl / 2, y - dy * tl / 2
        k = int(round(ang / 90)) % 4
        bmp = np.rot90(bmp, -k)
        bh, bw = bmp.shape
        i0 = int(round((x + s.w / 2) * s.p - bw / 2))
        j0 = int(round((y + s.h / 2) * s.p - bh / 2))
        L = s.layer(name)
        a0, b0 = max(j0, 0), max(i0, 0)
        a1, b1 = min(j0 + bh, s.H), min(i0 + bw, s.W)
        if a1 <= a0 or b1 <= b0:
            return
        sub = bmp[a0 - j0:a1 - j0, b0 - i0:b1 - i0]
        np.maximum(L[a0:a1, b0:b1], sub, out=L[a0:a1, b0:b1])


# ============================================================================ PCB
def pcb_mesh(mb, M, outline, holes, t, w, h, mtop, mbot, medge, mplate, plated_flags=None):
    loops = [outline] + holes
    allp = [p for L in loops for p in L]
    tris = geometry.tessellate_polygon([[V((x, y, 0)) for x, y in L] for L in loops])
    top = mb.verts([(x, y, t) for x, y in allp], M)
    bot = mb.verts([(x, y, 0) for x, y in allp], M)
    for tri in tris:
        a, b, c = tri
        pa, pb, pc = allp[a], allp[b], allp[c]
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) < 0:
            a, c = c, a
        uv = [((allp[i][0] + w / 2) / w, (allp[i][1] + h / 2) / h) for i in (a, b, c)]
        mb.face([top[a], top[b], top[c]], mtop, False, uv)
        mb.face([bot[c], bot[b], bot[a]], mbot, False, list(reversed(uv)))
    off = 0
    for li, L in enumerate(loops):
        n = len(L)
        area = sum(L[i][0] * L[(i + 1) % n][1] - L[(i + 1) % n][0] * L[i][1] for i in range(n))
        rev = (area > 0) != (li == 0)
        for i in range(n):
            j = (i + 1) % n
            a, b = off + i, off + j
            if rev:
                a, b = b, a
            if li == 0:
                mat = mplate if (plated_flags and plated_flags[i]) else medge
            else:
                mat = mplate
            mb.face([bot[a], bot[b], top[b], top[a]], mat, smooth=(li > 0 or bool(plated_flags and plated_flags[i])))
        off += n


def hole_loop(x, y, r, n=14):
    return [(x + r * math.cos(-2 * math.pi * k / n), y + r * math.sin(-2 * math.pi * k / n)) for k in range(n)]


def fillet_rect(w, h, r, seg=4):
    return [(p[0], p[1]) for p in rr(w, h, r, seg)]


class Board:
    def __init__(s, key, w, h, t, ppmm, mask_lo, mask_hi, silkc, padc, M, bottom_col=None):
        s.key, s.w, s.h, s.t = key, w, h, t
        s.cv = Canvas(w, h, ppmm)
        s.M = M
        s.parts = MB(key + '_parts')
        s.outline = fillet_rect(w, h, 0.6, 3)
        s.plated = None
        s.holes = []
        s.cols = (mask_lo, mask_hi, silkc, padc)
        s.bottom_col = bottom_col or mask_lo
        s.pins = []     # IC pins for fan-out routing: (x, y, dx, dy)
        s.targets = []  # header pins
        s.cv.rect('pour', 0, 0, w - 1.0, h - 1.0, r=0.6)

    # ---- frames
    def PM(s, x, y, z=None, rot=0.0):
        return s.M @ T(x, y, s.t if z is None else z) @ Rz(rot)

    @staticmethod
    def lp(x, y, rot, u, v):
        c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        return x + u * c - v * sn, y + u * sn + v * c

    # ---- paint helpers
    def pad(s, x, y, rot, u, v, w, h, layer='tin', r=0.0, clear=0.25):
        px, py = s.lp(x, y, rot, u, v)
        s.cv.rect(layer, px, py, w, h, ang=rot, r=r)
        s.cv.rect('clr', px, py, w + 2 * clear, h + 2 * clear, ang=rot, r=r + clear)
        return px, py

    def ring(s, x, y, r0=0.5, r1=0.9, layer='pad'):
        s.cv.circle(layer, x, y, r1)
        s.cv.circle('clr', x, y, r1 + 0.3)

    def silk_box(s, x, y, rot, w, h, lw=0.15):
        s.cv.rect('silk', x, y, w, h, ang=rot, lw=lw)

    def silk_corners(s, x, y, rot, w, h, k=0.8, lw=0.15):
        for sx in (-1, 1):
            for sy in (-1, 1):
                ax, ay = s.lp(x, y, rot, sx * w / 2, sy * h / 2)
                bx, by = s.lp(x, y, rot, sx * (w / 2 - k), sy * h / 2)
                cx, cy = s.lp(x, y, rot, sx * w / 2, sy * (h / 2 - k))
                s.cv.poly('silk', [(bx, by), (ax, ay), (cx, cy)], lw)

    def text(s, txt, x, y, hmm=0.9, ang=0, anchor='c'):
        s.cv.text(txt, x, y, hmm, ang, anchor)

    def trace(s, pts, wd=0.25):
        s.cv.poly('cu', pts, wd)
        s.cv.poly('clr', pts, wd + 0.5)

    def via(s, x, y):
        s.cv.circle('cu', x, y, 0.36)
        s.cv.circle('clr', x, y, 0.62)
        s.cv.circle('dark', x, y, 0.15)

    def route(s, p0, p1, wd=0.25, flip=None):
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        if flip is None:
            flip = RNG.random() < 0.5
        if abs(dx) > abs(dy):
            m = (x1 - math.copysign(abs(dy), dx), y0) if not flip else (x0 + math.copysign(abs(dy), dx), y1)
        else:
            m = (x0, y1 - math.copysign(abs(dx), dy)) if not flip else (x1, y0 + math.copysign(abs(dx), dy))
        s.trace([p0, m, p1], wd)

    def fanout(s, frac=0.5, reach=(2.0, 7.0), to_targets=0.25, wd=0.2):
        for (x, y, dx, dy) in s.pins:
            if RNG.random() > frac:
                continue
            L = RNG.uniform(0.6, 1.4)
            a = (x + dx * L, y + dy * L)
            if s.targets and RNG.random() < to_targets:
                tx, ty = RNG.choice(s.targets)
            else:
                d = RNG.uniform(*reach)
                ang = math.atan2(dy, dx) + RNG.uniform(-0.9, 0.9)
                tx, ty = a[0] + d * math.cos(ang), a[1] + d * math.sin(ang)
                tx = min(max(tx, -s.w / 2 + 1.2), s.w / 2 - 1.2)
                ty = min(max(ty, -s.h / 2 + 1.2), s.h / 2 - 1.2)
                s.via(tx, ty)
            s.trace([(x, y), a], wd)
            s.route(a, (tx, ty), wd)

    # ---- build
    def finalize(s, parent, coll):
        cv = s.cv
        H, W = cv.H, cv.W
        g = lambda n: np.clip(cv.layer(n), 0, 1)
        cu = np.clip(np.maximum(g('pour') * (1 - g('clr')), g('cu')), 0, 1)
        pad, tin, silk, dark = g('pad'), g('tin'), g('silk'), g('dark')
        metal = np.maximum(pad, tin)
        silk = silk * (1 - metal)
        mask_lo, mask_hi, silkc, padc = [np.array(c, np.float32) for c in s.cols]
        col = mask_lo * (1 - cu[..., None]) + mask_hi * cu[..., None]
        nz = lowfreq(H, W, 48, hash(s.key) % 1000)
        col = col * (1 + 0.06 * (nz[..., None] - 0.5))
        col = col * (1 - pad[..., None]) + padc * pad[..., None]
        tincol = np.array((0.80, 0.80, 0.80), np.float32)
        col = col * (1 - tin[..., None]) + tincol * tin[..., None]
        col = col * (1 - silk[..., None]) + np.array(silkc, np.float32) * silk[..., None]
        col = col * (1 - 0.7 * dark[..., None])
        hgt = 0.4 + 0.3 * cu * (1 - metal) + 0.25 * silk + 0.12 * metal - 0.3 * dark
        rgh = 0.34 * (1 - silk) + 0.75 * silk
        rgh = rgh * (1 - metal) + 0.2 * metal
        dat = np.stack([np.clip(hgt, 0, 1), rgh, metal], -1)
        ic = make_image(s.key + '_col', col)
        idt = make_image(s.key + '_dat', dat, noncolor=True)
        mtop = image_mat(s.key + '_mask_top', ic, idt, coat=0.45)
        mbot = pbr(s.key + '_mask_bot', tuple(s.bottom_col), 0.35, coat=0.45, bump=0.1, bscale=3000)
        pcb = MB(s.key + '_pcb')
        platem = 'plate_gold' if padc[0] > padc[2] + 0.2 else 'plate_tin'
        pcb_mesh(pcb, s.M, s.outline, s.holes, s.t, s.w, s.h, mtop, mbot, 'fr4_edge', platem, s.plated)
        o1 = pcb.finish(parent, coll, sharp=30)
        o2 = s.parts.finish(parent, coll, sharp=40)
        return [o1, o2]


# ============================================================================ component library (mm)
PASS = {'0402': (1.0, 0.5, 0.35), '0603': (1.6, 0.8, 0.45), '0805': (2.0, 1.25, 0.55), '1206': (3.2, 1.6, 0.6),
        '1210': (3.2, 2.5, 0.9), '1812': (4.5, 3.2, 1.0)}


def passive(B, x, y, pkg='0603', rot=0, kind='C', label=None):
    L, W, H = PASS[pkg]
    e = L * 0.2
    M = B.PM(x, y, rot=rot)
    mb = B.parts
    body = {'C': 'cer_tan', 'R': 'res_white', 'F': 'polyfuse', 'L': 'ic_black'}[kind]
    slab(mb, body, M @ T(0, 0, 0.02), L - 2 * e + 0.02, W, H)
    if kind == 'R':
        slab(mb, 'res_black', M @ T(0, 0, 0.02 + H), L - 2 * e - 0.1, W * 0.94, 0.03)
    for sgn in (-1, 1):
        slab(mb, 'tin_lead', M @ T(sgn * (L / 2 - e / 2), 0, 0.02), e, W * 1.01, H * 1.01, rt=0.04, tseg=1)
        # solder fillet
        k = mb.mark()
        prof = [(sgn * L / 2, 0.0), (sgn * (L / 2 + 0.28), 0.0), (sgn * L / 2, H * 0.55)]
        if sgn < 0:
            prof.reverse()
        prism(mb, 'solder', M @ Rx(90), prof, -W * 0.45, W * 0.45)
        B.pad(x, y, rot, sgn * (L / 2 - e / 2 + 0.12), 0, e + 0.45, W + 0.2)
    if label:
        lx, ly = B.lp(x, y, rot, 0, W / 2 + 0.75)
        B.text(label, lx, ly, 0.6, rot)


def lead(mb, M, pts, v, w, th, mat):
    """gull-wing lead along polyline pts [(u,z)] at lateral offset v."""
    loops = []
    for i, (u, z) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tu, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tu, tz) or 1
        nu, nz = -tz / ln, tu / ln
        loops.append([(u + nu * sz, v + sv, z + nz * sz) for sv, sz in
                      ((-w / 2, -th / 2), (w / 2, -th / 2), (w / 2, th / 2), (-w / 2, th / 2))])
    k = mb.mark()
    loft(mb, loops, mat, M, cap0=True, cap1=True, smooth=False)
    mb.recalc(k)


def gull_pkg(B, x, y, rot, bl, bw, h, pins, standoff=0.1, lw=0.4, llen=1.0, pin1=True, route=True):
    """pins: list of (u, side, width)."""
    M = B.PM(x, y, rot=rot)
    mb = B.parts
    k = mb.mark()
    slab(mb, 'ic_black', M @ T(0, 0, standoff), bl, bw, h, rc=0.08, seg=1, rt=0.12, tseg=1)
    mb.recalc(k)
    zl = standoff + h * 0.42
    for u, side, w in pins:
        pts = [(bw / 2 - 0.15, zl), (bw / 2 + 0.2, zl), (bw / 2 + 0.45, 0.07), (bw / 2 + llen, 0.07)]
        R = Rz(90 if side > 0 else -90)
        lead(mb, M @ R, pts, -u if side > 0 else u, w, 0.12, 'tin_lead')
        px, py = B.pad(x, y, rot, u, side * (bw / 2 + llen - 0.3), w + 0.15, 1.2)
        if route:
            c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            B.pins.append((px, py, -sn * side, c * side))
    if pin1:
        u0, s0, _ = pins[0]
        disc(mb, 'ic_dimple', M @ T(-bl / 2 + 0.7, -bw / 2 + 0.7, standoff + h + 0.003), min(0.35, bw * 0.12), 10)
    B.silk_corners(x, y, rot, bl + 0.3, bw + 0.3, 0.5)


def disc(mb, mat, M, r, n):
    c = mb.verts([(0, 0, 0)], M)[0]
    ring = mb.verts([(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), 0) for k in range(n)], M)
    for k in range(n):
        mb.face([c, ring[k], ring[(k + 1) % n]], mat, False)


def qfp(B, x, y, body, n, pitch, rot=0, h=1.0):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'ic_black', M @ T(0, 0, 0.1), body, body, h, rc=0.15, seg=1, rt=0.12, tseg=1)
    mb.recalc(k)
    c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    for side in range(4):
        R = Rz(90 * side)
        for i in range(n):
            v = (i - (n - 1) / 2) * pitch
            pts = [(body / 2 - 0.15, 0.1 + h * 0.45), (body / 2 + 0.25, 0.1 + h * 0.45), (body / 2 + 0.5, 0.07),
                   (body / 2 + 1.0, 0.07)]
            lead(mb, M @ R, pts, v, 0.22, 0.12, 'tin_lead')
            ru = math.radians(rot + 90 * side)
            cu_, su_ = math.cos(ru), math.sin(ru)
            u = body / 2 + 0.75
            px = x + u * cu_ - v * su_
            py = y + u * su_ + v * cu_
            B.cv.rect('tin', px, py, 1.3, 0.3, ang=rot + 90 * side)
            B.cv.rect('clr', px, py, 1.8, 0.45, ang=rot + 90 * side)
            B.pins.append((px, py, cu_, su_))
    disc(mb, 'ic_dimple', M @ T(-body / 2 + 1.0, body / 2 - 1.0, 1.1 + 0.003), 0.4, 12)
    disc(mb, 'ic_dimple', M @ T(body / 2 - 1.3, -body / 2 + 1.3, 1.1 + 0.002), 0.7, 14)
    s = body / 2 + 0.25
    for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        a = B.lp(x, y, rot, sx * s, sy * (s - 0.6))
        b = B.lp(x, y, rot, sx * s, sy * s)
        cc = B.lp(x, y, rot, sx * (s - 0.6), sy * s)
        B.cv.poly('silk', [a, b, cc], 0.15)
    B.cv.circle('silk', *B.lp(x, y, rot, -s - 0.6, s + 0.6), 0.3)


def qfn(B, x, y, size, n, pitch, rot=0, h=0.85):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'ic_black', M @ T(0, 0, 0.02), size, size, h, rc=0.06, seg=1, rt=0.05, tseg=1)
    mb.recalc(k)
    for side in range(4):
        R = Rz(90 * side)
        ru = math.radians(rot + 90 * side)
        cu_, su_ = math.cos(ru), math.sin(ru)
        for i in range(n):
            v = (i - (n - 1) / 2) * pitch
            slab(mb, 'tin_lead', M @ R @ T(size / 2 - 0.18, v, 0.02), 0.38, pitch * 0.5, 0.2)
            u = size / 2 + 0.1
            px, py = x + u * cu_ - v * su_, y + u * su_ + v * cu_
            B.cv.rect('tin', px, py, 0.75, pitch * 0.55, ang=rot + 90 * side)
            B.cv.rect('clr', px, py, 1.2, pitch * 0.8, ang=rot + 90 * side)
            B.pins.append((px, py, cu_, su_))
    disc(mb, 'ic_dimple', M @ T(-size / 2 + 0.7, size / 2 - 0.7, h + 0.023), min(0.3, size * 0.07), 10)
    s = size / 2 + 0.4
    B.cv.circle('silk', *B.lp(x, y, rot, -s - 0.3, s + 0.3), 0.22)
    B.silk_corners(x, y, rot, size + 0.8, size + 0.8, 0.5)


def sot223(B, x, y, rot=0):
    gull_pkg(B, x, y, rot, 6.5, 3.5, 1.6, [(-2.3, -1, 0.7), (0.0, -1, 0.7), (2.3, -1, 0.7), (0.0, 1, 3.0)],
             llen=1.15, pin1=False)
    B.pad(x, y, rot, 0, 3.2, 3.6, 2.2)


def sot23(B, x, y, rot=0, n=3):
    pins = [(-0.95, -1, 0.4), (0.95, -1, 0.4), (0.0, 1, 0.4)] if n == 3 else \
        [(-0.95, -1, 0.4), (0.0, -1, 0.4), (0.95, -1, 0.4), (0.95, 1, 0.4), (-0.95, 1, 0.4)]
    gull_pkg(B, x, y, rot, 2.9, 1.5, 1.0, pins, llen=0.75, lw=0.4, pin1=False)


def soic8(B, x, y, rot=0):
    pins = [(u, -1, 0.42) for u in (-1.905, -0.635, 0.635, 1.905)] + [(u, 1, 0.42) for u in (1.905, 0.635, -0.635, -1.905)]
    gull_pkg(B, x, y, rot, 4.9, 3.9, 1.45, pins, llen=1.05)


def sod123(B, x, y, rot=0):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'ic_black', M @ T(0, 0, 0.05), 2.7, 1.6, 1.05, rc=0.1, seg=1, rt=0.1, tseg=1)
    slab(mb, 'res_white', M @ T(-0.9, 0, 1.1), 0.35, 1.5, 0.01)
    mb.recalc(k)
    for sgn in (-1, 1):
        slab(mb, 'tin_lead', M @ T(sgn * 1.55, 0, 0.0), 0.6, 0.6, 0.12)
        B.pad(x, y, rot, sgn * 1.65, 0, 1.0, 1.0)
    B.silk_box(x, y, rot, 4.2, 2.0, 0.12)


def crystal_smd(B, x, y, rot=0, l=3.2, w=2.5):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'cer_tan', M @ T(0, 0, 0.02), l, w, 0.35, rc=0.15, seg=1)
    slab(mb, 'nickel', M @ T(0, 0, 0.37), l - 0.3, w - 0.3, 0.42, rc=0.3, seg=2, rt=0.08, tseg=1)
    mb.recalc(k)
    for sx in (-1, 1):
        for sy in (-1, 1):
            B.pad(x, y, rot, sx * (l / 2 - 0.5), sy * (w / 2 - 0.45), 1.2, 1.0)
    B.silk_box(x, y, rot, l + 0.9, w + 0.9, 0.12)


def hc49(B, x, y, rot=0):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'plastic_black', M, 11.2, 4.7, 0.4, rc=2.3, seg=6)
    slab(mb, 'nickel', M @ T(0, 0, 0.4), 11.0, 4.5, 3.3, rc=2.25, seg=8, rt=0.5, tseg=2)
    mb.recalc(k)
    B.cv.rect('silk', x, y, 12.2, 5.4, ang=rot, r=2.7, lw=0.15)
    for sgn in (-1, 1):
        B.ring(*B.lp(x, y, rot, sgn * 2.44, 0), 0.4, 0.8, layer='tin')


def electrolytic(B, x, y, d=6.3, h=5.4, rot=0):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    s = d / 2 + 0.15
    c = 1.0
    base = [(s, -s), (s, s), (-s + c, s), (-s, s - c), (-s, -s + c), (-s + c, -s)]
    prism(mb, 'plastic_black', M, base, 0.0, 1.0)
    r = d / 2
    prof = [(r - 0.05, 0.95), (r, 1.25), (r, 1.85), (r - 0.28, 2.05), (r, 2.3), (r, h - 0.4), (r - 0.08, h - 0.15),
            (r - 0.35, h - 0.02), (r - 0.5, h), (0.0, h)]
    revolve(mb, prof, 32, 'alu_can', M)
    # polarity sector + vent cross
    k = mb.mark()
    revolve(mb, [(r - 0.55, h + 0.004), (0.0, h + 0.004)], 10, 'res_black', M @ Rz(180), a0=math.radians(-55),
            a1=math.radians(55), closed=False)
    slab(mb, 'port_dark', M @ T(0, 0, h - 0.01) @ Rz(45), d * 0.55, 0.14, 0.02)
    slab(mb, 'port_dark', M @ T(0, 0, h - 0.01) @ Rz(-45), d * 0.55, 0.14, 0.02)
    for sgn in (-1, 1):
        slab(mb, 'tin_lead', M @ T(sgn * (s + 0.2), 0, 0), 1.2, 0.7, 0.12)
        B.pad(x, y, rot, sgn * (s + 0.4), 0, 2.0, 1.4)
    pts = [B.lp(x, y, rot, *p) for p in base + [base[0]]]
    B.cv.poly('silk', [(px + 0, py) for px, py in pts], 0.15)
    B.text('+', *B.lp(x, y, rot, s + 1.2, s - 0.4), 0.9)


def led(B, x, y, lens='led_red_on', rot=0, pkg='0603'):
    L, W, H = PASS[pkg]
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'led_body', M @ T(0, 0, 0.02), L - 0.5, W, 0.22)
    slab(mb, lens, M @ T(0, 0, 0.24), L - 0.6, W - 0.05, 0.3, rc=0.1, seg=1, rt=0.12, tseg=2)
    mb.recalc(k)
    for sgn in (-1, 1):
        slab(mb, 'tin_lead', M @ T(sgn * (L / 2 - 0.2), 0, 0.02), 0.4, W, 0.25)
        B.pad(x, y, rot, sgn * (L / 2 - 0.1), 0, 0.8, W + 0.2)


def tact(B, x, y, rot=0, w=4.2, d=3.2, h=1.6, pd=1.4, cap='plastic_black', plate=True, round_cap=True):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    k = mb.mark()
    slab(mb, 'plastic_black', M, w, d, h, rc=0.2, seg=1)
    if plate:
        slab(mb, 'nickel', M @ T(0, 0, h), w + 0.1, d + 0.1, 0.12, rc=0.25, seg=2)
    top = h + (0.12 if plate else 0)
    if round_cap:
        revolve(mb, [(pd / 2 + 0.05, top - 0.02), (pd / 2, top + 0.45), (pd / 2 - 0.15, top + 0.62), (0, top + 0.64)],
                20, cap, M)
    else:
        slab(mb, cap, M @ T(0, 0, top - 0.02), pd, pd * 0.8, 0.6, rc=0.15, seg=1, rt=0.1, tseg=1)
    mb.recalc(k)
    for sx in (-1, 1):
        for sy in (-1, 1):
            slab(mb, 'nickel', M @ T(sx * (w / 2 + 0.25), sy * (d / 2 - 0.5), 0), 0.6, 0.45, 0.12)
            B.pad(x, y, rot, sx * (w / 2 + 0.35), sy * (d / 2 - 0.5), 1.1, 0.8)


def match_loops(a, b):
    """insert midpoints on the longest edges of the shorter loop until both have the same count."""
    a, b = list(a), list(b)
    while len(a) != len(b):
        L = a if len(a) < len(b) else b
        n = len(L)
        i = max(range(n), key=lambda k: math.dist(L[k], L[(k + 1) % n]))
        p, q = L[i], L[(i + 1) % n]
        L.insert(i + 1, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
    return a, b


def tube_shell(mb, M, outer, inner, depth, inner_depth, mat, backmat):
    """Receptacle shell: opening at u=0 facing +u, extends toward -u. loops given in (v,z)."""
    outer, inner = match_loops(outer, inner)
    to3 = lambda L, u: [(u, a, b) for a, b in L]
    loft(mb, [to3(outer, -depth), to3(outer, 0.0), to3(inner, 0.0), to3(inner, -inner_depth)], mat, M)
    mb.face(list(reversed(mb.verts(to3(outer, -depth), M))), mat, False)
    prism(mb, backmat, M @ Ry(90), [(-b, a) for a, b in inner], -inner_depth - 0.01, -inner_depth + 0.02)


def usb_c(mb, M, gold=True):
    outer = stadium(8.94, 3.26, 8)
    inner = stadium(8.34, 2.66, 8)
    tube_shell(mb, M, outer, inner, 7.35, 6.9, 'nickel', 'port_dark')
    k = mb.mark()
    slab(mb, 'plastic_black', M @ T(-3.5, 0, -0.35), 6.2, 6.6, 0.7, rt=0.1, tseg=1, rb=0.1, bseg=1)
    mb.recalc(k)
    for i in range(12):
        v = (i - 5.5) * 0.5
        for zz in (0.35, -0.365):
            slab(mb, 'gold', M @ T(-2.2, v, zz), 2.6, 0.25, 0.015)


def usb_a(mb, M, tongue='usb3_blue'):
    outer = [(p[0], p[1]) for p in rr(12.5, 5.12, 0.35, 2)]
    inner = [(p[0], p[1]) for p in rr(11.9, 4.52, 0.2, 2)]
    tube_shell(mb, M, outer, inner, 13.0, 12.4, 'nickel', 'port_dark')
    k = mb.mark()
    zt = 4.52 / 2 - 0.92
    slab(mb, tongue, M @ T(-6.4, 0, zt - 0.92), 11.6, 11.1, 1.84, rt=0.15, tseg=1)
    mb.recalc(k)
    for i in range(4):
        slab(mb, 'gold', M @ T(-3.5, (i - 1.5) * 2.5, zt - 0.95), 3.5, 1.0, 0.03)
    for i in range(5):
        slab(mb, 'gold', M @ T(-8.0, (i - 2) * 2.0, zt - 0.95), 2.0, 0.7, 0.03)
    # retention springs on the shell
    for sgn in (-1, 1):
        slab(mb, 'nickel', M @ T(-3.0, sgn * 3.2, 4.52 / 2 - 0.05), 2.2, 1.0, 0.08)


def micro_usb(mb, M):
    def trap(w, h, c):
        return [(w / 2, -h / 2 + c), (w / 2, h / 2), (-w / 2, h / 2), (-w / 2, -h / 2 + c), (-w / 2 + c, -h / 2),
                (w / 2 - c, -h / 2)]
    outer = trap(7.5, 2.6, 0.9)
    inner = trap(6.9, 2.0, 0.7)
    tube_shell(mb, M, outer, inner, 5.0, 4.6, 'nickel', 'port_dark')
    slab(mb, 'plastic_black', M @ T(-2.5, 0, 0.35), 4.2, 3.9, 0.35)
    for i in range(5):
        slab(mb, 'gold', M @ T(-1.7, (i - 2) * 0.65, 0.33), 2.0, 0.3, 0.02)


def usb_b(mb, M):
    outer = [(p[0], p[1]) for p in rr(12.0, 10.9, 0.4, 2)]
    ho = 7.78
    wo = 8.45
    c = 1.0
    inner = [(wo / 2, -ho / 2), (wo / 2, ho / 2 - c), (wo / 2 - c, ho / 2), (-wo / 2 + c, ho / 2), (-wo / 2, ho / 2 - c),
             (-wo / 2, -ho / 2)]
    tube_shell(mb, M, outer, inner, 16.0, 11.0, 'nickel', 'port_dark')
    k = mb.mark()
    slab(mb, 'plastic_white', M @ T(-5.5, 0, -1.5), 11.0, 5.4, 3.0, rt=0.2, tseg=1)
    mb.recalc(k)
    for zz in (1.51, -1.52):
        for v in (-1.25, 1.25):
            slab(mb, 'gold', M @ T(-3.0, v, zz), 4.5, 0.9, 0.02)


def barrel_jack(mb, M):
    """opening at u=0 facing +u; body extends to -14; z bottom 0."""
    hw, hh, zc = 4.5, 5.5, 6.5
    ang = sorted(set([round(2 * math.pi * k / 32, 9) for k in range(32)] +
                     [round(math.atan2(dz, sx * hw) % (2 * math.pi), 9) for sx in (-1, 1) for dz in (11.0 - zc, -zc)]))
    # rectangle (v in +-4.5, z in 0..11) sampled along rays from the bore centre
    rect = []
    circ = []
    for a in ang:
        ca, sa = math.cos(a), math.sin(a)
        tv = hw / abs(ca) if abs(ca) > 1e-9 else 1e9
        top = 11.0 - zc if sa > 0 else zc
        tz = top / abs(sa) if abs(sa) > 1e-9 else 1e9
        t = min(tv, tz)
        rect.append((ca * t, zc + sa * t))
        circ.append((3.15 * ca, zc + 3.15 * sa))
    to3 = lambda L, u: [(u, a, b) for a, b in L]
    k = mb.mark()
    loft(mb, [to3(rect, -14.0), to3(rect, 0.0), to3(circ, 0.0), to3(circ, -9.0)], 'plastic_black', M)
    mb.face(list(reversed(mb.verts(to3(rect, -14.0), M))), 'plastic_black', False)
    mb.face(mb.verts(to3(circ, -9.0), M), 'port_dark', False)
    mb.recalc(k)
    k = mb.mark()
    revolve(mb, [(0.0, -9.0), (1.0, -9.0), (1.0, -1.5), (0.8, -1.2), (0.0, -1.2)], 12, 'nickel',
            M @ T(0, 0, zc) @ Ry(90))
    mb.recalc(k)


def header_female(B, x, y, n, rot=0, h=8.5):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    L = n * 2.54
    k = mb.mark()
    rings = loft(mb, [rr(L, 2.54, 0, 0, 0.0), rr(L, 2.54, 0, 0, h)], 'plastic_black', M)
    mb.face(list(reversed(rings[0])), 'plastic_black', False)
    for i in range(n):
        u = (i - (n - 1) / 2) * 2.54
        loops = [rr(2.54, 2.54, 0, 0, h), rr(1.5, 1.5, 0, 0, h - 0.45), rr(1.0, 1.0, 0, 0, h - 0.7),
                 rr(1.0, 1.0, 0, 0, h - 2.6)]
        loft(mb, loops, 'plastic_black', M @ T(u, 0, 0), cap1=True, capmat='gold', mats=['plastic_black',
                                                                                      'port_dark', 'port_dark'])
        k2 = mb.mark()
        pin(mb, M @ T(u, 0, 0), -B.t - 1.8, 0.0, 'tin_lead')
        mb.recalc(k2)
        px, py = B.lp(x, y, rot, u, 0)
        B.ring(px, py, 0.5, 0.85, 'tin')
        B.targets.append((px, py))
        solder_joint(B, px, py, bottom=True)
    B.cv.rect('silk', x, y, L + 0.5, 3.0, ang=rot, lw=0.15)


def pin(mb, M, z0, z1, mat='gold', s=0.64):
    loops = [rr(0.25, 0.25, 0, 0, z0), rr(s, s, 0, 0, z0 + 0.45), rr(s, s, 0, 0, z1 - 0.45), rr(0.25, 0.25, 0, 0, z1)]
    loft(mb, loops, mat, M, cap0=True, cap1=True, smooth=False)


def header_male(B, x, y, n, rows=1, rot=0, down=False, above=6.0, spacer=2.5, below=6.0, joints=True):
    mb = B.parts
    M = B.PM(x, y, rot=rot)
    for r in range(rows):
        v = (r - (rows - 1) / 2) * 2.54
        for i in range(n):
            u = (i - (n - 1) / 2) * 2.54
            if down:
                z0s = -B.t - spacer
                slab(mb, 'plastic_black', M @ T(u, v, z0s), 2.5, 2.5, spacer, rt=0.3, tseg=1, rb=0.3, bseg=1)
                pin(mb, M @ T(u, v, 0), z0s - below, 1.3)
            else:
                slab(mb, 'plastic_black', M @ T(u, v, 0), 2.5, 2.5, spacer, rt=0.3, tseg=1, rb=0.3, bseg=1)
                pin(mb, M @ T(u, v, 0), -B.t - 1.8, spacer + above)
            px, py = B.lp(x, y, rot, u, v)
            B.ring(px, py, 0.5, 0.85, 'tin')
            B.targets.append((px, py))
            if joints:
                solder_joint(B, px, py, bottom=not down)


def solder_joint(B, x, y, bottom=False, r=0.85):
    prof = [(r, 0.0), (r * 0.92, 0.12), (r * 0.66, 0.38), (0.46, 0.72), (0.38, 0.95)]
    if bottom:
        M = B.M @ T(x, y, 0) @ Rx(180)
    else:
        M = B.M @ T(x, y, B.t)
    revolve(B.parts, prof, 8, 'solder', M)


# ============================================================================ boards
def build_uno(coll, parent):
    Mb = Matrix.Identity(4)
    B = Board('elec_uno', 68.58, 53.34, 1.6, 28, (0.0, 0.34, 0.43), (0.05, 0.47, 0.56), (0.93, 0.93, 0.9),
              (0.80, 0.80, 0.80), Mb, bottom_col=(0.0, 0.33, 0.42))
    X0, Y0 = 34.29, 26.67

    def U(X, Y):
        return X0 - X, Y0 - Y

    def R(r):
        return r + 180
    ol = [(0, 0), (66.04, 0), (68.58, 2.54), (68.58, 50.8), (66.04, 53.34), (0, 53.34)]
    B.outline = [U(X, Y) for X, Y in ol]
    for X, Y in ((13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)):
        x, y = U(X, Y)
        B.holes.append(hole_loop(x, y, 1.6, 16))
        B.cv.circle('tin', x, y, 2.6)
        B.cv.circle('clr', x, y, 3.1)
    mb = B.parts
    # connectors
    x, y = U(-6.35, 38.1)
    usb_b(mb, B.PM(x, y, B.t + 10.9 / 2, R(180)))
    x, y = U(-1.8, 7.6)
    barrel_jack(mb, B.PM(x, y, rot=R(180)))
    # headers
    for Xc, Yc, n in ((29.0, 50.8, 10), (54.0, 50.8, 8), (36.83, 2.54, 8), (57.15, 2.54, 6)):
        header_female(B, *U(Xc, Yc), n, rot=R(0))
    header_male(B, *U(64.77, 27.94), 3, rows=2, rot=R(90), joints=False)
    header_male(B, *U(16.5, 46.0), 3, rows=2, rot=R(0), joints=False)
    B.text('ICSP', *U(59.2, 27.94), 0.9, R(90))
    # silicon
    qfp(B, *U(46.0, 23.0), 7.0, 8, 0.8, rot=R(45))
    qfn(B, *U(21.5, 37.5), 5.0, 8, 0.5, rot=R(0))
    hc49(B, *U(33.2, 24.5), rot=R(90))
    crystal_smd(B, *U(14.8, 33.0), rot=R(90), l=3.2, w=1.3)
    sot223(B, *U(7.8, 22.0), rot=R(90))
    sot23(B, *U(40.5, 9.5), rot=R(0), n=5)
    soic8(B, *U(29.5, 41.0), rot=R(90))
    sod123(B, *U(10.5, 15.2), rot=R(0))
    electrolytic(B, *U(16.4, 7.0), rot=R(0))
    electrolytic(B, *U(16.4, 14.2), rot=R(0))
    passive(B, *U(12.8, 27.5), '1812', R(90), 'F')
    tact(B, *U(6.5, 49.3), rot=R(0), w=6.0, d=3.5, h=2.0, pd=2.4, plate=True, round_cap=False)
    B.text('RESET', *U(6.5, 45.3), 0.8, R(0))
    for Yl, t, lens in ((45.3, 'L', 'led_yellow_off'), (41.9, 'TX', 'led_yellow_off'), (39.9, 'RX', 'led_yellow_off')):
        led(B, *U(24.8, Yl), lens, R(0))
        passive(B, *U(20.8, Yl), '0603', R(0), 'R')
        B.text(t, *U(27.6, Yl), 0.8, R(0), anchor='r')
    led(B, *U(60.8, 40.2), 'led_green_on', R(90))
    B.text('ON', *U(60.8, 43.6), 0.9, R(0))
    passive(B, *U(58.0, 40.2), '0603', R(90), 'R')
    # decoupling and support passives
    plist = [(41.5, 28.5, 0, 'C', 'C4'), (51.5, 17.0, 45, 'C', None), (40.3, 17.5, 90, 'C', 'C6'),
             (52.2, 28.8, 45, 'R', 'R2'), (37.5, 19.0, 90, 'C', None), (37.5, 30.0, 90, 'C', None),
             (25.5, 33.5, 0, 'C', 'C7'), (18.0, 41.5, 90, 'R', None), (18.0, 34.0, 90, 'C', None),
             (24.5, 30.5, 0, 'R', 'R1'), (12.0, 36.5, 90, 'C', None), (12.0, 40.0, 90, 'C', None),
             (32.5, 36.0, 0, 'R', None), (32.5, 46.0, 0, 'R', 'RN1'), (35.0, 46.0, 0, 'R', None),
             (37.5, 46.0, 0, 'R', None), (12.5, 20.0, 90, 'C', 'C2'), (4.5, 27.0, 90, 'C', None),
             (22.5, 20.5, 0, 'C', None), (22.5, 23.0, 0, 'C', 'C3'), (44.0, 9.5, 90, 'C', None),
             (37.0, 9.5, 90, 'C', None), (56.5, 30.5, 0, 'R', None), (61.5, 24.0, 90, 'C', None),
             (27.0, 26.0, 90, 'R', None), (47.5, 32.0, 0, 'C', 'C9')]
    for X, Y, r, kd, lb in plist:
        passive(B, *U(X, Y), '0603' if kd == 'C' else '0603', R(r), kd, lb)
    passive(B, *U(30.2, 14.8), '0805', R(0), 'C', 'C1')
    # unpopulated footprint
    for sgn in (-1, 1):
        B.pad(*U(55.5, 12.0), R(0), sgn * 0.85, 0, 0.9, 0.95, layer='pad')
    B.text('R17', *U(55.5, 13.6), 0.6, R(0))
    # silkscreen pin labels
    dig = ['AREF', 'GND', '13', '12', '~11', '~10', '~9', '8']
    dig2 = ['7', '~6', '~5', '4', '~3', '2', 'TX 1', 'RX 0']
    for i, t in enumerate(dig):
        B.text(t, *U(17.53 + 2.54 * (i + 2), 47.9), 0.85, R(90), anchor='l')
    for i, t in enumerate(dig2):
        B.text(t, *U(45.1 + 2.54 * i, 47.9), 0.85, R(90), anchor='l')
    pw = ['', 'IOREF', 'RESET', '3V3', '5V', 'GND', 'GND', 'VIN']
    for i, t in enumerate(pw):
        if t:
            B.text(t, *U(27.94 + 2.54 * i, 5.4), 0.85, R(90), anchor='r')
    for i in range(6):
        B.text(f'A{i}', *U(50.8 + 2.54 * i, 5.4), 0.85, R(90), anchor='r')
    B.text('DIGITAL (PWM~)', *U(40.0, 44.0), 1.1, R(0))
    B.text('POWER', *U(36.8, 11.0), 1.1, R(0))
    B.text('ANALOG IN', *U(57.2, 11.0), 1.1, R(0))
    B.text('DEV BOARD R3', *U(48.0, 36.5), 1.4, R(0))
    B.cv.rect('silk', *U(48.0, 36.5), 18.5, 3.0, ang=R(0), lw=0.15)
    # traces: fan-out + a few power runs
    B.fanout(frac=0.55, to_targets=0.35)
    for a, b in (((8.0, 17.0), (27.94 + 2.54 * 4, 2.54)), ((16.4, 10.6), (8.0, 17.0)), ((12.8, 30.0), (4.5, 30.0)),
                 ((40.5, 12.0), (27.94 + 2.54 * 3, 2.54)), ((60.8, 38.0), (64.77, 30.5))):
        B.route(U(*a), U(*b), 0.6)
    for X, Y in ((30.0, 30.0), (43.5, 15.0), (58.0, 20.0), (26.0, 16.0), (50.0, 43.5), (62.0, 14.0), (10.0, 44.0)):
        B.via(*U(X, Y))
    # bottom-side solder tails the board rests on are part of header_female (bottom joints)
    objs = B.finalize(parent, coll)
    return objs, B


def dupont_wires(B, coll, parent):
    """five jumpers from the far-side (analog/power) headers, arcing away and lying on the desk."""
    mb = MB('elec_uno_jumpers')
    X0, Y0 = 34.29, 26.67
    U = lambda X, Y: (X0 - X, Y0 - Y)
    htop = B.t + 8.5
    zdesk = -1.8
    specs = [((27.94 + 2.54 * 4, 2.54), 'wire_red', (-9.0, 13.0, 44.0, (-30.0, 108.0))),
             ((27.94 + 2.54 * 5, 2.54), 'wire_black', (-15.0, 8.0, 38.0, (-52.0, 96.0))),
             ((50.8, 2.54), 'wire_yellow', (2.0, 16.0, 52.0, (6.0, 122.0))),
             ((50.8 + 2.54, 2.54), 'wire_blue', (9.0, 10.0, 47.0, (34.0, 112.0))),
             ((50.8 + 5.08, 2.54), 'wire_green', (15.0, 6.0, 40.0, (55.0, 92.0)))]
    for (X, Y), wm, (dx, peak, land, (ex, ey)) in specs:
        px, py = U(X, Y)
        k = mb.mark()
        slab(mb, 'plastic_black', T(px, py, htop), 2.5, 2.5, 14.0, rt=0.35, tseg=1, rb=0.2, bseg=1)
        mb.recalc(k)
        slab(mb, 'port_dark', T(px + 1.26, py, htop + 9.0), 0.02, 1.4, 3.0)
        top = htop + 14.0
        revolve(mb, [(1.0, top - 0.5), (0.95, top + 0.6), (0.78, top + 2.2), (0.66, top + 3.2)], 8, wm, T(px, py, 0))
        r = 0.65
        ex_, ey_ = px + ex, py + ey
        lx, ly = px + dx * 1.6, py + land
        pts = [(px, py, top + 3.0), (px + dx * 0.05, py + 0.5, top + 4.0 + peak * 0.4),
               (px + dx * 0.35, py + land * 0.22, top + peak), (px + dx * 0.8, py + land * 0.5, top + peak * 0.55),
               (px + dx * 1.2, py + land * 0.78, zdesk + 7.0), (px + dx * 1.45, py + land - 5, zdesk + 1.6),
               (lx, ly, zdesk + r), (lx + (ex_ - lx) * 0.35 + dx * 0.8, ly + (ey_ - ly) * 0.4, zdesk + r),
               (ex_ - (ex_ - lx) * 0.12, ey_ - 9, zdesk + r), (ex_, ey_ - 3, zdesk + 1.0), (ex_, ey_, zdesk + 1.27)]
        path, _ = spline(pts, 2.0)
        sweep(mb, path, circle2(r, 7), wm, up=(0, 1, 0))
        # loose male end lying on the desk
        d = (path[-1] - path[-4]).normalized()
        ang = math.degrees(math.atan2(d.y, d.x))
        Mend = T(ex_, ey_, zdesk + 1.27) @ Rz(ang) @ Ry(90)
        k = mb.mark()
        slab(mb, 'plastic_black', Mend @ T(0, 0, 0), 2.5, 2.5, 14.0, rt=0.35, tseg=1, rb=0.3, bseg=1)
        mb.recalc(k)
        k = mb.mark()
        pin(mb, Mend, 14.0, 20.0, 'tin_lead')
        mb.recalc(k)
    o = mb.finish(parent, coll, sharp=50)
    return [o]


def build_esp32(coll, parent):
    B = Board('elec_esp32', 55.0, 28.0, 1.6, 32, (0.035, 0.035, 0.04), (0.07, 0.075, 0.08), (0.92, 0.92, 0.9),
              (0.95, 0.77, 0.45), Matrix.Identity(4), bottom_col=(0.035, 0.035, 0.04))
    B.outline = fillet_rect(55.0, 28.0, 1.0, 4)
    mb = B.parts
    left = ['3V3', 'EN', 'VP', 'VN', '34', '35', '32', '33', '25', '26', '27', '14', '12', 'GND', '13', 'D2', 'D3',
            'CMD', '5V']
    right = ['GND', '23', '22', 'TX', 'RX', '21', 'GND', '19', '18', '5', '17', '16', '4', '0', '2', '15', 'D1', 'D0',
             'CLK']
    for sgn, labels in ((-1, left), (1, right)):
        header_male(B, 0.0, sgn * 12.7, 19, rows=1, rot=0, down=True)
        for i, t in enumerate(labels):
            xx = (i - 9) * 2.54 * (-1)
            B.text(t, xx, sgn * 10.95, 0.7, 90, anchor='r' if sgn > 0 else 'l')
    # module
    Mm = T(-18.25, 0, B.t + 0.05)
    Mod = Board('elec_esp32_module', 25.5, 18.0, 0.8, 32, (0.03, 0.03, 0.035), (0.06, 0.06, 0.07),
                (0.9, 0.9, 0.88), (0.95, 0.77, 0.45), Mm)
    ol = []
    hw, hh = 12.75, 9.0
    flags = []
    # castellations along both long sides (14 each, pitch 1.27) in the can region
    xs = [(-5.0 + i * 1.27) for i in range(14)]
    ol.append((-hw, -hh))
    flags.append(False)
    for xx in xs:
        for k in range(5):
            a = math.radians(180 - 180 * k / 4)
            ol.append((xx + 0.45 * math.cos(a), -hh + 0.45 * math.sin(a)))
            flags.append(k < 4)
    ol.append((hw, -hh))
    flags.append(False)
    ol.append((hw, hh))
    flags.append(False)
    for xx in reversed(xs):
        for k in range(5):
            a = math.radians(-180 * k / 4)
            ol.append((xx + 0.45 * math.cos(a), hh + 0.45 * math.sin(a)))
            flags.append(k < 4)
    ol.append((-hw, hh))
    flags.append(False)
    Mod.outline = ol
    Mod.plated = flags
    for xx in xs:
        for sg in (-1, 1):
            Mod.cv.rect('pad', xx, sg * (hh - 0.6), 0.9, 1.4)
            # solder fillets onto the devkit
            revolve(B.parts, [(0.62, 0.0), (0.5, 0.25), (0.3, 0.75), (0.0, 0.85)], 8, 'solder',
                    Mm @ T(xx, sg * hh, -0.05) @ Rz(0), a0=math.radians(0 if sg > 0 else 180),
                    a1=math.radians(180 if sg > 0 else 360), closed=False)
            px, py = xx - 18.25, sg * (hh + 0.3)
            B.cv.rect('tin', px, py, 0.9, 1.4)
    Mod.cv.rect('pour', 0, 0, 1, 1)
    Mod.cv.L['pour'][:] = 0
    Mod.cv.rect('pour', 3.2, 0, 18.0, 17.0, r=0.4)
    # meandering PCB antenna in the keep-out end
    meander = [(-6.4, -7.5), (-11.2, -7.5), (-11.2, -5.0), (-7.2, -5.0), (-7.2, -2.5), (-11.2, -2.5), (-11.2, 0.0),
               (-7.2, 0.0), (-7.2, 2.5), (-11.2, 2.5), (-11.2, 5.0), (-7.2, 5.0), (-7.2, 7.4), (-11.8, 7.4)]
    Mod.cv.poly('cu', meander, 0.45)
    Mod.cv.rect('silk', -9.3, 0, 6.2, 17.2, lw=0.12)
    Mod.text('WIFI', -9.3, -2.0, 0.8, 90)
    k = Mod.parts.mark()
    slab(Mod.parts, 'nickel', Mod.PM(3.3, 0.0), 17.8, 15.6, 2.35, rc=0.5, seg=2, rt=0.3, tseg=2)
    Mod.parts.recalc(k)
    # stamped can: a shallow raised field and two pick-up dimples
    slab(Mod.parts, 'nickel', Mod.PM(3.3, 0.0, Mod.t + 2.35), 14.6, 12.6, 0.06, rc=0.8, seg=2, rt=0.05, tseg=1)
    objs = Mod.finalize(parent, coll)
    # right half: USB-C, USB-UART bridge, regulator, buttons, LED, passives
    usb_c(mb, B.PM(28.5, 0.0, B.t + 3.26 / 2, 0))
    for sgn in (-1, 1):
        slab(mb, 'nickel', B.PM(24.0, sgn * 4.75), 1.8, 0.5, 1.2)
        B.pad(24.0, sgn * 4.9, 0, 0, 0, 2.2, 1.0)
    for i in range(12):
        B.pad(21.3, (i - 5.5) * 0.5, 0, 0, 0, 0.9, 0.28)
    qfn(B, 12.5, 3.2, 5.0, 7, 0.5, rot=0)
    sot223(B, 3.0, -6.2, rot=0)
    tact(B, 22.2, -8.9, rot=0, w=4.2, d=3.2, h=1.5, pd=1.5, cap='plastic_black')
    tact(B, 22.2, 8.9, rot=0, w=4.2, d=3.2, h=1.5, pd=1.5, cap='plastic_black')
    B.text('EN', 17.9, -8.9, 0.8, 90)
    B.text('BOOT', 17.9, 8.9, 0.8, 90)
    led(B, 17.0, -4.6, 'led_red_on', 90)
    B.text('PWR', 15.3, -4.6, 0.6, 90)
    sot23(B, 5.8, 6.0, rot=0)
    sot23(B, 5.8, 9.4, rot=0)
    sod123(B, 13.0, -9.0, rot=0)
    passive(B, 8.6, -3.0, '1206', 90, 'C', 'C10')
    passive(B, -1.6, -2.5, '1206', 90, 'C', 'C11')
    for (px, py, r, kd, lb) in [(17.0, 1.5, 90, 'R', None), (17.0, 5.2, 90, 'C', 'C5'), (9.0, 7.5, 0, 'R', 'R6'),
                               (9.0, 3.2, 90, 'C', None), (12.5, -1.4, 0, 'C', None), (15.4, 3.2, 90, 'R', None),
                               (1.5, 4.2, 0, 'R', 'R3'), (1.5, 8.8, 0, 'R', None), (-2.5, 6.0, 90, 'C', None),
                               (19.8, -4.6, 90, 'R', 'R9'), (24.0, -6.0, 0, 'R', None), (24.0, 6.0, 0, 'R', None),
                               (-3.2, -7.8, 90, 'C', None), (8.0, -8.8, 0, 'R', 'R12'), (-4.0, 1.2, 0, 'C', None)]:
        passive(B, px, py, '0603', r, kd, lb)
    B.text('DEV KIT V1', 3.5, 1.2, 1.1, 0)
    B.fanout(frac=0.6, to_targets=0.3)
    for a, b in (((3.0, -9.5), (-22.86, -12.7)), ((24.0, -2.0), (3.0, -2.5)), ((-3.0, -9.5), (-12.0, -9.6))):
        B.route(a, b, 0.6)
    objs += B.finalize(parent, coll)
    return objs


def build_pico(coll, parent, M):
    B = Board('elec_pico', 51.0, 21.0, 1.0, 36, (0.02, 0.33, 0.14), (0.08, 0.45, 0.20), (0.94, 0.94, 0.92),
              (0.95, 0.77, 0.45), M, bottom_col=(0.02, 0.32, 0.13))
    hw, hh, rc = 25.5, 10.5, 0.8
    xs = [(i - 9.5) * 2.54 for i in range(20)]
    ol, fl = [], []

    def corner(cx, cy, a0):
        for s in range(4):
            a = math.radians(a0 + 90 * s / 3)
            ol.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
            fl.append(False)
    corner(-hw + rc, -hh + rc, 180)
    for xx in xs:
        for k in range(7):
            a = math.radians(180 - 180 * k / 6)
            ol.append((xx + 0.55 * math.cos(a), -hh + 0.55 * math.sin(a)))
            fl.append(k < 6)
    corner(hw - rc, -hh + rc, 270)
    corner(hw - rc, hh - rc, 0)
    for xx in reversed(xs):
        for k in range(7):
            a = math.radians(-180 * k / 6)
            ol.append((xx + 0.55 * math.cos(a), hh + 0.55 * math.sin(a)))
            fl.append(k < 6)
    corner(-hw + rc, hh - rc, 90)
    B.outline, B.plated = ol, fl
    for sg in (-1, 1):
        for xx in xs:
            B.holes.append(hole_loop(xx, sg * 8.89, 0.5, 12))
            B.cv.rect('pad', xx, sg * (hh - 0.95), 1.7, 2.2, r=0.3)
            B.cv.circle('pad', xx, sg * 8.89, 0.85)
            B.cv.rect('pad', xx, sg * 9.4, 1.2, 1.2)
            B.cv.rect('clr', xx, sg * 9.4, 2.2, 3.6, r=0.6)
            B.targets.append((xx, sg * 8.89))
    for sx in (-1, 1):
        for sy in (-1, 1):
            B.holes.append(hole_loop(sx * 23.5, sy * 5.7, 1.05, 16))
            B.cv.circle('pad', sx * 23.5, sy * 5.7, 1.75)
            B.cv.circle('clr', sx * 23.5, sy * 5.7, 2.1)
    for yy in (-2.54, 0.0, 2.54):
        B.holes.append(hole_loop(-24.2, yy, 0.5, 12))
        B.cv.circle('pad', -24.2, yy, 0.85)
    B.text('DEBUG', -21.2, 0.0, 0.7, 90)
    mb = B.parts
    micro_usb(mb, B.PM(26.8, 0.0, B.t + 1.3, 0))
    for sgn in (-1, 1):
        slab(mb, 'nickel', B.PM(23.4, sgn * 3.95), 1.4, 0.5, 1.0)
        B.pad(23.4, sgn * 4.1, 0, 0, 0, 1.8, 1.0)
    for i in range(5):
        B.pad(22.2, (i - 2) * 0.65, 0, 0, 0, 1.2, 0.35)
    qfn(B, -1.5, 0.0, 7.0, 14, 0.4, rot=0)
    soic8(B, 11.2, -2.2, rot=90)
    crystal_smd(B, -8.4, 5.2, rot=0)
    qfn(B, -15.6, -3.6, 2.0, 2, 0.65, rot=0)
    k = mb.mark()
    slab(mb, 'ic_black', B.PM(-15.6, 1.4), 2.5, 2.0, 1.1, rc=0.2, seg=1, rt=0.1, tseg=1)
    mb.recalc(k)
    B.pad(-15.6, 1.4, 0, -1.0, 0, 0.8, 2.0)
    B.pad(-15.6, 1.4, 0, 1.0, 0, 0.8, 2.0)
    tact(B, 17.0, 5.0, rot=0, w=3.5, d=3.0, h=1.4, pd=1.8, cap='plastic_white')
    B.text('BOOTSEL', 17.0, 2.6, 0.6, 0)
    led(B, 19.5, -6.3, 'led_green_on', 0)
    B.text('LED', 19.5, -4.9, 0.6, 0)
    for (px, py, r, kd) in [(-6.5, -4.8, 0, 'C'), (-6.5, 1.8, 90, 'C'), (3.6, 5.4, 0, 'C'), (3.6, -5.4, 0, 'C'),
                            (-1.5, 5.9, 0, 'R'), (5.2, 0.0, 90, 'C'), (-11.5, -3.6, 90, 'C'), (-11.5, 1.4, 90, 'C'),
                            (-19.4, -3.2, 90, 'C'), (-19.4, 1.4, 90, 'R'), (15.0, -2.4, 90, 'R'), (15.0, -5.8, 0, 'C'),
                            (7.5, 5.6, 0, 'R'), (20.2, 1.2, 90, 'R'), (-11.5, 5.6, 0, 'C'), (-3.4, -6.2, 0, 'R')]:
        passive(B, px, py, '0402', r, kd)
    for i, t in ((0, '1'), (19, '20')):
        B.text(t, xs[i] - (0 if i else 0), -6.7, 0.8, 0)
    B.text('39', xs[18], 6.7, 0.8, 0)
    B.text('40', xs[19], 6.7, 0.8, 0)
    B.text('USB', 21.0, 2.3, 0.7, 90)
    B.text('PICO-STYLE', -8.4, -6.9, 0.9, 0)
    B.fanout(frac=0.55, to_targets=0.35, wd=0.18)
    return B.finalize(parent, coll)


# ============================================================================ hub + cable
HUB_M = T(0.30606, 0.93523, DESK) @ Rz(math.degrees(0.24))
LAP_M = Matrix(((1.0, 0.0, 0.0, -0.05), (0.0, 0.9563, -0.2924, 0.7115), (0.0, 0.2924, 0.9563, 0.7891),
                (0, 0, 0, 1)))


def build_hub(coll, parent):
    W_, D_, H_, Z0 = 88.0, 42.0, 14.5, 1.2
    zc = Z0 + H_ / 2
    body = MB('elec_hub_body')
    slab(body, 'hub_alu', Matrix.Identity(4), W_, D_, H_, rc=5.0, seg=6, rt=3.0, tseg=5, rb=1.0, bseg=2, z0=Z0)
    bobj = body.finish(parent, coll, sharp=35)
    cutters = []
    PORTS = [('A', -30.0), ('A', -13.5), ('A', 3.0), ('C', 19.5)]
    for kind, px in PORTS:
        c = MB('cut')
        if kind == 'A':
            w, h, r, sg = 12.9, 5.5, 0.4, 2
        else:
            w, h, r, sg = 9.3, 3.6, 1.8, 5
        loops = []
        mats = []
        for y, grow in ((-23.0, 2.0), (-20.55, 0.0), (-6.0, 0.0)):
            L = rr(w + 2 * grow, h + 2 * grow, r + grow, sg)
            loops.append([(px + a, y, zc + b) for a, b, _ in L])
        k = c.mark()
        loft(c, loops, 'alu_diamond', mats=['alu_diamond', 'port_dark'], cap0=True, cap1=True, capmat='port_dark')
        c.recalc(k)
        cutters.append(c)
    # status LED window in the top
    c = MB('cut')
    k = c.mark()
    revolve(c, [(0.0, 10.0), (0.9, 10.0), (0.9, 15.5), (1.25, 15.9), (1.25, 17.0), (0.0, 17.0)], 16, 'port_dark',
            T(33.0, -15.5, 0))
    c.recalc(k)
    cutters.append(c)
    cobjs = [cm.finish(parent, coll) for cm in cutters]
    for co in cobjs:
        md = bobj.modifiers.new('b', 'BOOLEAN')
        md.operation = 'DIFFERENCE'
        md.object = co
        try:
            md.solver = 'EXACT'
        except TypeError:
            pass
        try:
            md.material_mode = 'TRANSFER'
        except (TypeError, AttributeError):
            pass
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(bobj.evaluated_get(dg))
    old = bobj.data
    bobj.modifiers.clear()
    bobj.data = me
    bpy.data.meshes.remove(old)
    for co in cobjs:
        d = co.data
        bpy.data.objects.remove(co, do_unlink=True)
        bpy.data.meshes.remove(d)
    bm = bmesh.new()
    bm.from_mesh(bobj.data)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35))
    bm.to_mesh(bobj.data)
    bm.free()
    bobj.name = 'elec_hub_body'
    bobj.data.name = 'elec_hub_body'
    # port hardware, LED, feet, strain relief
    hw = MB('elec_hub_parts')
    for kind, px in PORTS:
        M = T(px, -20.75, zc) @ Rz(-90)
        if kind == 'A':
            usb_a(hw, M)
        else:
            usb_c(hw, M)
    k = hw.mark()
    revolve(hw, [(0.0, 10.5), (0.85, 10.5), (0.85, 15.55), (0.6, 15.68), (0.0, 15.7)], 16, 'led_blue_on',
            T(33.0, -15.5, 0))
    hw.recalc(k)
    for sx in (-1, 1):
        for sy in (-1, 1):
            revolve(hw, [(0.0, 0.0), (3.6, 0.0), (4.0, 0.35), (4.0, 1.0), (3.7, 1.25), (0.0, 1.25)], 20, 'rubber',
                    T(sx * 35.0, sy * 13.5, 0))
    k = hw.mark()
    revolve(hw, [(3.4, -1.0), (3.4, 1.0), (3.25, 1.5), (3.0, 1.55), (2.95, 3.5), (2.75, 6.5), (2.5, 9.5),
                 (2.3, 11.8), (2.12, 12.0), (0.0, 12.0)], 24, 'hub_alu', T(0, 21.0, zc) @ Rx(-90),
            mats=['hub_alu', 'hub_alu', 'hub_alu', 'tpe_black', 'tpe_black', 'tpe_black', 'tpe_black', 'tpe_black',
                  'tpe_black'])
    hw.recalc(k)
    o2 = hw.finish(parent, coll, sharp=40)
    exit_world = HUB_M @ (V((0, 32.8, zc)) * MM)
    return [bobj, o2], exit_world


def build_cable(coll, parent, start):
    mb = MB('elec_hub_cable_braid', scale=1.0)
    R = 0.0021
    # plug housing in the MacBook's right USB-C (laptop-local metres)
    py, pz = 0.0536, 0.0058
    x0 = 0.1566
    loops = []
    for x, w, h, r in ((x0, 0.0112, 0.0054, 0.0026), (x0 + 0.0006, 0.0118, 0.0060, 0.0029),
                       (x0 + 0.0128, 0.0118, 0.0060, 0.0029), (x0 + 0.0142, 0.0112, 0.0056, 0.0027),
                       (x0 + 0.0150, 0.0100, 0.0050, 0.0024)):
        loops.append([(x, py + a, pz + b) for a, b, _ in rr(w, h, r, 5)])
    k = mb.mark()
    loft(mb, loops, 'hub_alu', LAP_M, cap0=True, cap1=True, capmat='port_dark')
    mb.recalc(k)
    k = mb.mark()
    revolve(mb, [(0.0026, 0.0), (0.0026, 0.0012), (0.0024, 0.003), (0.0022, 0.0055), (0.00212, 0.0062)], 20,
            'tpe_black', LAP_M @ T(x0 + 0.0148, py, pz) @ Ry(90))
    mb.recalc(k)
    end = LAP_M @ V((x0 + 0.0148 + 0.0060, py, pz))
    zc = DESK + R
    ctrl = [start, start + V((-0.2377, 0.9713, 0)) * 0.009 + V((0, 0, -0.0012)),
            V((0.2935, 0.9860, zc + 0.0006)), V((0.2830, 1.0010, zc)), V((0.2650, 1.0065, zc)),
            V((0.2450, 0.9985, zc)), V((0.2275, 0.9745, zc)), V((0.2105, 0.9250, zc)), V((0.1935, 0.8700, zc)),
            V((0.1800, 0.8200, zc)), V((0.1700, 0.7900, zc + 0.0008)), V((0.1605, 0.7740, 0.7490)),
            V((0.1520, 0.7660, 0.7680)), V((0.1450, 0.7625, 0.7870)), end + V((0.0105, 0.0002, -0.0070)),
            end + V((0.0045, 0.0, -0.0010)), end]
    path, L = spline(ctrl, 0.0022)
    us = []
    acc = 0.0
    for i, p in enumerate(path):
        if i:
            acc += (p - path[i - 1]).length
        us.append(acc / (2 * math.pi * R))
    sweep(mb, path, circle2(R, 12), braid_mat(), up=(0, 0, 1), us=us)
    o = mb.finish(parent, coll, sharp=60)
    return [o], L


# ============================================================================ mug
MUG_M = T(0.720, 0.460, DESK) @ Rz(-30)


def build_mug(coll, parent):
    mb = MB('elec_mug_body')
    prof = [(0.0, 2.2), (10, 2.15), (20, 2.0), (28, 1.8), (30.5, 1.5), (31.6, 0.9), (32.3, 0.35), (33.0, 0.05),
            (34.5, 0.0), (36.0, 0.0), (37.0, 0.08), (37.8, 0.35), (38.5, 0.8), (39.2, 1.5), (39.8, 2.3),
            (40.0, 2.6), (40.25, 2.75), (40.35, 3.0), (40.6, 4.5), (40.85, 7.0), (41.0, 10.0), (41.0, 20.0),
            (41.0, 35.0), (41.0, 50.0), (41.0, 65.0), (41.0, 80.0), (41.05, 85.5), (41.15, 87.0)]
    for k in range(9):
        a = math.radians(180 * k / 8)
        prof.append((39.0 + 2.2 * math.cos(a), 88.2 + 2.2 * math.sin(a)))
    prof += [(36.62, 87.0), (36.52, 85.0), (36.5, 75.0), (36.5, 60.0), (36.5, 45.0), (36.5, 30.0), (36.5, 14.0),
             (36.25, 11.6), (35.4, 9.6), (33.8, 8.0), (31.6, 7.2), (25.0, 7.0), (12.0, 6.92), (0.0, 6.9)]
    mats = []
    for i in range(len(prof) - 1):
        (r0, z0), (r1, z1) = prof[i], prof[i + 1]
        foot = i >= 4 and i < 15
        mats.append('bisque' if foot else glaze_mat())
    revolve(mb, prof, 72, glaze_mat(), mats=mats)
    # handle: swept superellipse, flared into the wall at both joins
    ctrl = [(37.5, 75.5), (42.5, 77.2), (51.0, 78.4), (60.0, 75.2), (66.5, 66.0), (68.4, 53.0), (66.8, 40.5),
            (61.5, 30.5), (53.0, 25.0), (44.0, 23.0), (37.5, 22.6)]
    path, L = spline([(x, 0.0, z) for x, z in ctrl], 1.6)
    n = len(path)

    def sec(i, nn):
        t = i / (nn - 1)
        fl = 1 + 0.75 * max(0.0, 1 - t / 0.13) ** 2 + 0.75 * max(0.0, (t - 0.87) / 0.13) ** 2
        a = (4.9 - 0.9 * t) * fl       # thickness (in the path plane)
        b = 6.4 * (1 + 0.5 * (fl - 1))  # width across
        pts = []
        for k in range(24):
            th = 2 * math.pi * k / 24
            c, s = math.cos(th), math.sin(th)
            pts.append((math.copysign(abs(c) ** (2 / 2.7), c) * b, math.copysign(abs(s) ** (2 / 2.7), s) * a))
        return pts
    sweep(mb, path, sec, glaze_mat(), up=(0, 1, 0), cap0=True, cap1=True)
    o1 = mb.finish(parent, coll, sharp=70)
    # coffee: surface 26 mm below the lip with a wetting meniscus at the wall
    cf = MB('elec_mug_coffee')
    rs = [0.0, 6, 12, 18, 24, 29, 32, 34, 35.3, 36.0, 36.4, 36.62]
    prof2 = [(r, 64.0 + 1.25 * math.exp(-(36.62 - r) / 0.55)) for r in rs]
    prof2.append((36.62, 62.0))
    prof2.reverse()
    revolve(cf, prof2, 72, coffee_mat())
    o2 = cf.finish(parent, coll, sharp=80)
    return [o1, o2]


# ============================================================================ notepad + pencil
NOTE_M = T(-0.520, 0.520, DESK) @ Rz(12)


def scribble(cv, x0, y0, length, xh, rng, press=0.8, wd=0.32):
    """cursive-looking pencil word: looping strokes with per-letter width, height, ascenders and descenders."""
    lets = []
    acc = 0.0
    while acc < length:
        w = rng.uniform(1.2, 2.4)
        lets.append((acc, w, rng.choice('nnnnnoaadt'), rng.uniform(0.8, 1.15), rng.uniform(0.18, 0.38)))
        acc += w
    sc = length / acc
    pts = []
    base = rng.uniform(-0.15, 0.15)
    slope = rng.uniform(-0.012, 0.012)
    for (s0, w, kd, hs, loop) in lets:
        s0 *= sc
        w *= sc
        n = max(6, int(w / 0.06))
        for k in range(n):
            ph = k / n
            env = 0.5 * (1 - math.cos(2 * math.pi * ph))
            y = xh * hs * env
            if kd == 'a':
                y *= 1 + 1.4 * math.sin(math.pi * ph) ** 2
            elif kd == 'd':
                y -= 1.7 * xh * math.sin(math.pi * ph) ** 4
            elif kd == 'o':
                y = xh * hs * (0.5 + 0.5 * math.sin(2 * math.pi * ph - math.pi / 2)) * (0.3 + 0.7 * env)
            elif kd == 't':
                y = xh * hs * env * (1 + 0.9 * math.sin(math.pi * ph) ** 6)
            x = s0 + w * ph - w * loop * math.sin(2 * math.pi * ph)
            pts.append((x0 + x + 0.3 * y, y0 + y + base + slope * x))
    pts.append((pts[-1][0] + 0.8, pts[-1][1] + 0.4))
    pr = press
    for a_, b_ in zip(pts[:-1], pts[1:]):
        pr = min(1.0, max(0.45, pr + rng.uniform(-0.04, 0.04)))
        cv.seg('ink', a_[0], a_[1], b_[0], b_[1], wd * (0.8 + 0.3 * pr), val=pr)
    return pts


def page_textures(key, writing):
    W_, H_ = 148.0, 210.0
    cv = Canvas(W_, H_, 9.0)
    rng = random.Random(42)
    top = H_ / 2
    lines = [top - 30.0 - 7.1 * i for i in range(26)]
    for y in lines:
        cv.seg('blue', -W_ / 2, y, W_ / 2, y, 0.18, val=0.9)
    cv.seg('blue', -W_ / 2, top - 21.0, W_ / 2, top - 21.0, 0.3, val=0.9)
    cv.seg('red', -46.0, -H_ / 2, -46.0, top - 13.0, 0.22, val=0.9)
    for i in range(int(W_ / 1.2)):
        x = -W_ / 2 + 0.6 + i * 1.2
        cv.circle('perf', x, top - 13.0, 0.18)
    holes = [-W_ / 2 + 6.2 + i * 6.35 for i in range(int((W_ - 10) / 6.35) + 1)]
    for x in holes:
        cv.rect('hole', x, top - 7.5, 3.0, 3.6, r=1.2)
    if writing:
        # date on the header line
        scribble(cv, 40.0, top - 20.5, 22.0, 1.9, rng)
        # heading, underlined twice
        scribble(cv, -40.0, lines[0] + 0.4, 38.0, 2.6, rng, 0.9, 0.4)
        cv.poly('ink', [(-41.0, lines[0] - 0.9), (0.0, lines[0] - 1.3)], 0.35, val=0.8)
        cv.poly('ink', [(-40.0, lines[0] - 1.9), (-8.0, lines[0] - 2.1)], 0.3, val=0.7)
        # body text
        for li in range(2, 12):
            if li == 6:
                continue
            x = -42.0 if li not in (4, 5) else -34.0
            while True:
                wl = rng.uniform(5.0, 17.0)
                if x + wl > 66.0 - rng.uniform(0, 30) * (li == 11):
                    break
                scribble(cv, x, lines[li] + 0.35, wl, rng.uniform(1.7, 2.0), rng, rng.uniform(0.6, 0.85))
                x += wl + rng.uniform(2.2, 3.4)
        # bullets for lines 4-5
        for li in (4, 5):
            cv.circle('ink', -38.0, lines[li] + 1.2, 0.55, val=0.8)
        # crossed-out word
        cv.poly('ink', [(-10.0, lines[8] + 1.2), (8.0, lines[8] + 1.6)], 0.4, val=0.85)
        cv.poly('ink', [(-10.0, lines[8] + 2.0), (8.0, lines[8] + 0.6)], 0.35, val=0.7)
        # block diagram sketch
        by = lines[15] - 3.0
        for bx, lab in ((-30.0, 5), (5.0, 7), (38.0, 4)):
            rx = [(bx - 13 + rng.uniform(-0.4, 0.4), by - 7 + rng.uniform(-0.4, 0.4)),
                  (bx + 13 + rng.uniform(-0.4, 0.4), by - 7 + rng.uniform(-0.4, 0.4)),
                  (bx + 13 + rng.uniform(-0.4, 0.4), by + 7 + rng.uniform(-0.4, 0.4)),
                  (bx - 13 + rng.uniform(-0.4, 0.4), by + 7 + rng.uniform(-0.4, 0.4))]
            cv.poly('ink', rx + [(rx[0][0] + 0.8, rx[0][1] + 0.3)], 0.35, val=0.8)
            scribble(cv, bx - lab * 1.1, by - 1.0, lab * 2.2, 1.8, rng, 0.8)
        for x0, x1 in ((-16.5, -8.5), (18.5, 24.5)):
            cv.poly('ink', [(x0, by), (x1, by)], 0.35, val=0.8)
            cv.poly('ink', [(x1 - 2.2, by + 1.3), (x1, by), (x1 - 2.2, by - 1.3)], 0.35, val=0.8)
        cv.poly('ink', [(38.0, by - 7.2), (38.0, by - 13.0), (-30.0, by - 13.0), (-30.0, by - 7.5)], 0.3, val=0.6)
        cv.poly('ink', [(-31.6, by - 9.4), (-30.0, by - 7.5), (-28.4, by - 9.4)], 0.3, val=0.6)
        # checklist
        for i, li in enumerate((20, 21, 22)):
            y = lines[li] + 0.6
            cv.rect('ink', -40.0, y + 1.4, 3.0, 3.0, lw=0.3, val=0.8)
            if i < 2:
                cv.poly('ink', [(-41.2, y + 1.6), (-40.1, y + 0.4), (-38.0, y + 3.8)], 0.38, val=0.85)
            scribble(cv, -35.0, y, rng.uniform(22, 40), 1.8, rng, 0.75)
        # circled number in the margin
        for k in range(26):
            a0 = 2 * math.pi * k / 25
            a1 = 2 * math.pi * (k + 1) / 25
            cv.seg('ink', -58.0 + 3.2 * math.cos(a0), lines[2] + 1.5 + 3.0 * math.sin(a0),
                   -58.0 + 3.2 * math.cos(a1), lines[2] + 1.5 + 3.0 * math.sin(a1), 0.3, val=0.7)
        scribble(cv, -59.2, lines[2] + 0.4, 2.2, 1.9, rng, 0.8)
    H, W = cv.H, cv.W
    g = lambda n: np.clip(cv.layer(n), 0, 1)
    tooth = np.random.RandomState(7).rand(H, W).astype(np.float32)
    nz = lowfreq(H, W, 60, 3)
    paper = np.array((0.955, 0.948, 0.918), np.float32)
    col = paper * (1 + 0.02 * (nz[..., None] - 0.5) + 0.012 * (tooth[..., None] - 0.5))
    for lay, c in (('blue', (0.60, 0.72, 0.87)), ('red', (0.90, 0.52, 0.52)), ('perf', (0.80, 0.79, 0.76))):
        a = g(lay)[..., None]
        col = col * (1 - a) + np.array(c, np.float32) * a
    ink = g('ink') * (0.65 + 0.35 * tooth)
    col = col * (1 - ink[..., None]) + np.array((0.30, 0.30, 0.33), np.float32) * ink[..., None]
    hole = g('hole')
    col = col * (1 - hole[..., None]) + np.array((0.16, 0.15, 0.14), np.float32) * hole[..., None]
    hgt = 0.5 + 0.12 * (tooth - 0.5) - 0.15 * ink - 0.3 * hole - 0.1 * g('perf')
    rgh = 0.86 - 0.45 * ink
    dat = np.stack([np.clip(hgt, 0, 1), rgh, ink * 0.12], -1)
    ic = make_image(key + '_col', col)
    idt = make_image(key + '_dat', dat, noncolor=True)
    return image_mat(key, ic, idt, bump_dist=0.00012, sss=0.08, rnoise=0.02), holes


def build_notes(coll, parent):
    W_, H_ = 148.0, 210.0
    m_top, holes = page_textures('elec_page_written', True)
    m_blank, _ = page_textures('elec_page_blank', False)
    mb = MB('elec_notepad')
    I = Matrix.Identity(4)
    slab(mb, 'cover', I, W_ + 1.5, H_ + 1.0, 0.55, rc=3.0, seg=4, rt=0.2, tseg=1)
    slab(mb, 'board_chip', I @ T(0, -0.3, 0.55), W_, H_ - 0.6, 1.8, rc=2.0, seg=4)
    slab(mb, paper_edge_mat(), I @ T(0, -0.3, 2.35), W_ - 0.4, H_ - 1.2, 6.0, rc=2.0, seg=4,
         topmat=m_blank, botcap=False)
    # patch UVs on the stack's top cap so the ruled texture lines up
    ztop = 8.35
    # curled top sheets (three), each a subdivided grid
    for si, (lift, zoff, mat) in enumerate(((2.2, 0.0, m_blank), (3.3, 0.12, m_blank), (4.6, 0.24, m_top))):
        nx, ny = 24, 34
        grid = []
        for j in range(ny + 1):
            row = []
            for i in range(nx + 1):
                u, v = i / nx, j / ny
                x = -W_ / 2 + 0.2 + (W_ - 0.4) * u
                y = -H_ / 2 + 0.2 + (H_ - 1.4) * v
                d = math.hypot(x - W_ / 2, y + H_ / 2)
                z = ztop + zoff + 0.05
                if d < 55.0:
                    z += lift * (1 - d / 55.0) ** 2.2
                z += 0.16 * math.sin(x * 0.045) * math.sin(y * 0.03 + 1.3) * (1 - v)
                row.append((x, y, z))
            grid.append(row)
        vs = [mb.verts(r) for r in grid]
        for j in range(ny):
            for i in range(nx):
                uvs = [(i / nx, j / ny), ((i + 1) / nx, j / ny), ((i + 1) / nx, (j + 1) / ny), (i / nx, (j + 1) / ny)]
                uvs = [(uu, (vv * (H_ - 1.4) + 0.2) / H_) for uu, vv in uvs]
                mb.face([vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]], mat, True, uvs)
    # UVs for the blank top cap of the stack
    for f in mb.flist:
        if not f.is_valid:
            continue
        f.normal_update()
        if mb.mats[f.material_index] == m_blank and f.normal.z > 0.9 and len(f.verts) > 4:
            for l in f.loops:
                co = l.vert.co / MM
                l[mb.uv].uv = ((co.x + W_ / 2) / W_, (co.y + H_ / 2) / H_)
    # spiral binding along the top edge: one helical coil per punched hole
    cy, czc, R = H_ / 2 - 7.5 + 4.6, 5.3, 5.4
    path = []
    x0 = holes[0] - 6.35 / 2
    x1 = holes[-1] + 6.35 / 2
    turns = len(holes)
    steps = turns * 18
    for k in range(steps + 1):
        t = k / steps
        a = -math.pi / 2 - 2 * math.pi * turns * t - 0.9
        path.append(V((x0 + (x1 - x0) * t, cy + R * math.cos(a), czc + R * math.sin(a))))
    sweep(mb, path, circle2(0.55, 6), 'spiral_wire', up=(1, 0, 0))
    o1 = mb.finish(parent, coll, sharp=40)
    # ---------------------------------------------------------------- sticky notes (76 x 76 mm)
    def sheet_z(x, y):
        v = (y + H_ / 2 - 0.2) / (H_ - 1.4)
        z = ztop + 0.24 + 0.05
        d = math.hypot(x - W_ / 2, y + H_ / 2)
        if d < 55.0:
            z += 4.6 * (1 - d / 55.0) ** 2.2
        return z + 0.16 * math.sin(x * 0.045) * math.sin(y * 0.03 + 1.3) * (1 - v)

    sn = MB('elec_sticky_notes')
    m_sticky = sticky_texture()
    pbr('sticky_pink', (0.98, 0.74, 0.82), 0.8, bump=0.25, bscale=2500, sss=0.05)
    pbr('sticky_mint', (0.74, 0.93, 0.82), 0.8, bump=0.25, bscale=2500, sss=0.05)
    notes_spec = [  # (cx, cy, rot, material, on_page, curl mm, z extra)
        (28.0, -40.0, -7.0, 'sticky_pink', True, 1.6, 0.0),
        (30.0, 36.0, 5.0, m_sticky, True, 2.6, 0.1),
        (-150.0, 40.0, -14.0, 'sticky_mint', False, 3.2, 0.0),
    ]
    for cx, cy, rot, mat, on_page, curl, zx in notes_spec:
        n = 10
        c, s_ = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        top, bot = [], []
        for j in range(n + 1):
            rt, rb = [], []
            for i in range(n + 1):
                a, b = -38 + 76 * i / n, -38 + 76 * j / n
                xp, yp = cx + a * c - b * s_, cy + a * s_ + b * c
                base = sheet_z(xp, yp) + 0.06 if on_page else 0.0
                # glued strip along the top 15 mm; the free edge lifts and one corner curls a little more
                lift = curl * max(0.0, (22.0 - b) / 60.0) ** 2.2 + 0.35 * curl * max(0.0, (a - 20) / 18.0) ** 2 * \
                    max(0.0, (10 - b) / 48.0)
                z = base + 0.09 + lift + zx
                rt.append((xp, yp, z))
                rb.append((xp, yp, z - 0.09))
            top.append(rt)
            bot.append(rb)
        vt = [sn.verts(r) for r in top]
        vb = [sn.verts(r) for r in bot]
        for j in range(n):
            for i in range(n):
                uv = [(i / n, j / n), ((i + 1) / n, j / n), ((i + 1) / n, (j + 1) / n), (i / n, (j + 1) / n)]
                sn.face([vt[j][i], vt[j][i + 1], vt[j + 1][i + 1], vt[j + 1][i]], mat, True, uv)
                sn.face([vb[j][i], vb[j + 1][i], vb[j + 1][i + 1], vb[j][i + 1]], mat, True)
        border = [(0, i) for i in range(n + 1)] + [(j, n) for j in range(1, n + 1)] + \
                 [(n, i) for i in range(n - 1, -1, -1)] + [(j, 0) for j in range(n - 1, 0, -1)]
        for k in range(len(border)):
            (j0, i0), (j1, i1) = border[k], border[(k + 1) % len(border)]
            sn.face([vb[j0][i0], vb[j1][i1], vt[j1][i1], vt[j0][i0]], mat, True)
    o_sn = sn.finish(parent, coll, sharp=60)
    # ---------------------------------------------------------------- rOtring 600 (Pearl White), 0.5 mm
    # Axis +x from the lead tip (x=0) to the push button; hexagonal brass barrel, knurled round grip.
    pm = MB('elec_rotring600')
    RY = Ry(90)
    revolve(pm, [(0.0, -0.75), (0.25, -0.75), (0.25, 0.0)], 8, 'graphite', RY)
    revolve(pm, [(0.2, 0.0), (0.45, 0.0), (0.45, 3.6), (0.55, 3.9), (0.95, 4.0)], 12, 'chrome', RY)
    cone = [(0.95, 4.0), (1.25, 4.6), (2.2, 8.0), (3.1, 11.6), (3.55, 13.6), (3.62, 14.0), (3.45, 14.3), (3.45, 14.7),
            (3.7, 15.0)]
    revolve(pm, cone, 32, 'chrome', RY)
    grip = [(3.7, 15.0), (3.9, 15.4), (3.9, 39.4), (3.75, 39.8), (3.75, 40.4), (3.98, 40.7)]
    revolve(pm, grip, 40, 'chrome', RY, mats=['chrome', 'knurl_chrome', 'chrome', 'chrome', 'chrome'])
    # hexagonal barrel (8 mm across flats, softened corners)
    Rh = 4.0 / math.cos(math.radians(30))
    hexl = []
    for k in range(6):
        a0 = math.radians(60 * k)
        for s in range(-2, 3):
            a = a0 + math.radians(s * 10.0)
            p = V((math.cos(a0), math.sin(a0))) * (Rh - 0.6) + V((math.cos(a), math.sin(a))) * 0.52
            hexl.append((p.x, p.y))
    xs_h = [40.7, 41.3, 70.0, 100.0, 117.6]
    k0 = pm.mark()
    loft(pm, [[(x, py * sc, pz * sc) for py, pz in hexl] for x, sc in
              zip(xs_h, (0.93, 1.0, 1.0, 1.0, 1.0))], 'rot_pearl', None, cap0=True, cap1=True)
    pm.recalc(k0)
    # lead-grade indicator band with its window, then the chrome top cone, clip ring and push button
    revolve(pm, [(3.9, 117.4), (4.3, 117.6), (4.3, 121.6), (3.9, 121.8)], 36, 'chrome', RY)
    k0 = pm.mark()
    slab(pm, 'port_dark', T(119.6, 0.0, 4.22), 2.2, 1.6, 0.12, rc=0.3, seg=2)
    pm.recalc(k0)
    k0 = pm.mark()
    loft(pm, [[(x, py * sc, pz * sc) for py, pz in hexl] for x, sc in ((121.8, 1.0), (126.0, 1.0), (126.6, 0.93))],
         'rot_pearl', None, cap0=True, cap1=True)
    pm.recalc(k0)
    revolve(pm, [(3.6, 126.5), (4.15, 126.7), (4.15, 131.2), (3.3, 132.6), (3.0, 133.0)], 36, 'chrome', RY)
    revolve(pm, [(2.85, 133.0), (2.85, 139.8), (2.6, 140.9), (1.8, 141.6), (0.0, 141.8)], 28, 'chrome', RY)
    # clip: spring-steel strip off the top flat, with a rounded bead at its free end
    clip = [V((129.5, 0.0, 4.2)), V((127.5, 0.0, 5.3)), V((124.0, 0.0, 5.55)), V((105.0, 0.0, 5.25)),
            V((92.0, 0.0, 4.95)), V((89.5, 0.0, 4.55))]
    path, _ = spline(clip, 0.8)
    sweep(pm, path, [(p[0], p[1]) for p in rr(3.2, 0.9, 0.35, 2)], 'chrome', up=(0, 1, 0), cap0=True, cap1=True)
    revolve(pm, [(0.0, -0.9), (0.8, -0.75), (1.1, 0.0), (0.8, 0.75), (0.0, 0.9)], 12, 'chrome',
            T(90.2, 0.0, 4.55))
    o2 = pm.finish(parent, coll, sharp=35)
    return [o1, o2, o_sn]


# ============================================================================ assemble
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    std_mats()
    coll = bpy.data.collections.new(f'NEW_{NAME}')
    scene.collection.children.link(coll)
    root = bpy.data.objects.new(f'NEW_{NAME}_root', None)
    coll.objects.link(root)

    def empty(name, M):
        e = bpy.data.objects.new(name, None)
        coll.objects.link(e)
        e.parent = root
        e.matrix_world = M
        e.empty_display_size = 0.02
        return e
    objs = {}
    # lab-corner layout (2026-09-29): Uno turned so its far headers face the breadboard, ESP32 to the
    # front-right corner, Pico lying flat behind the Uno; jumpers now live in elec_lab_wiring.
    e = empty('elec_uno', T(0.445, 0.690, DESK + 0.0018) @ Rz(-90))
    o, B = build_uno(coll, e)
    objs['uno'] = o
    e = empty('elec_esp32', T(0.935, 0.405, DESK + 0.0085) @ Rz(90))
    objs['esp32'] = build_esp32(coll, e)
    Mp = T(0.440, 0.785, DESK)
    e = empty('elec_pico', Mp)
    objs['pico'] = build_pico(coll, e, Matrix.Identity(4))
    e = empty('elec_hub', HUB_M)
    hub_objs, exit_w = build_hub(coll, e)
    objs['hub'] = hub_objs
    e = empty('elec_hub_cable', Matrix.Identity(4))
    cab, clen = build_cable(coll, e, exit_w)
    objs['cable'] = cab
    e = empty('elec_mug', MUG_M)
    for ob in build_mug(coll, e):   # the owner replaced the mug with a Red Bull can: kept, but hidden
        ob.hide_render = True
        ob.hide_viewport = True
        ob.hide_set(True)
    e = empty('elec_notes', NOTE_M)
    notes = build_notes(coll, e)
    # pencil lies on the pad, resting on its ferrule and graphite tip
    pen = notes[1]
    ptop = 8.35 + 0.24 + 0.05 + 0.1
    pen.matrix_parent_inverse = Matrix.Identity(4)
    # rests on a hex flat (apothem 4.0), clip up, along the page's left side
    pen.matrix_basis = T(-0.052, -0.078, (ptop + 4.0) * MM) @ Rz(79)
    objs['notes'] = notes
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import v2_electronics_lab as lab
    bpy.context.view_layer.update()
    lab_objs = lab.build_lab(sys.modules[__name__], coll, root)
    objs.update(lab_objs)
    lab_tris = sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for lst in lab_objs.values() for ob in lst)
    print('TRIS new lab items', lab_tris)
    # ------------------------------------------------------------------ report
    tot = 0
    for k, lst in objs.items():
        t = 0
        for ob in lst:
            t += sum(len(p.vertices) - 2 for p in ob.data.polygons)
        tot += t
        print(f'TRIS {k:8s} {t:7d}  ' + ', '.join(ob.name for ob in lst))
    print('TRIS total', tot, ' cable length m', round(clen, 3))
    for ob in coll.all_objects:
        if ob.type == 'MESH':
            mw = ob.matrix_world
            cs = [mw @ V(cc) for cc in ob.bound_box]
            print('BB', ob.name, [round(min(p[i] for p in cs), 4) for i in range(3)],
                  [round(max(p[i] for p in cs), 4) for i in range(3)])
    bpy.data.orphans_purge(do_recursive=True)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
    print('SAVED', OUT)
    if RENDER:
        previews(scene, coll)


# ============================================================================ previews
def look(cam, target):
    d = V(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def previews(scene, coll):
    # context from room.blend (appended AFTER saving, never written back anywhere)
    with bpy.data.libraries.load(ROOM, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    ctx = bpy.data.collections.new('CONTEXT_room')
    scene.collection.children.link(ctx)
    retire = set(REPLACES)
    for o in dst.objects:
        if o is None:
            continue
        if o.type in ('LIGHT', 'CAMERA') or o.name in retire or o.hide_render or o.name.startswith(('elec_', 'NEW_electronics')):
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        ctx.objects.link(o)
    bpy.context.view_layer.update()
    for o in list(ctx.objects):
        # hide retired descendants and the room shell (walls/ceiling) so the preview lights reach in
        p = o
        dead = False
        while p is not None:
            if p.name in retire:
                dead = True
            p = p.parent
        if o.type == 'MESH':
            cs = [o.matrix_world @ V(cc) for cc in o.bound_box]
            ext = [max(q[i] for q in cs) - min(q[i] for q in cs) for i in range(3)]
            if max(ext) > 2.6 and not o.name.startswith('desk'):
                dead = True
            if min(q[2] for q in cs) > 2.2:
                dead = True
        for cn in o.users_collection:
            if cn.name == 'OLD_replaced':
                dead = True
        if dead:
            o.hide_render = True
    world = bpy.data.worlds.new('prev_world')
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.18, 0.18, 0.18, 1)
    bg.inputs[1].default_value = 0.35
    scene.world = world
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
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    try:
        scene.view_settings.view_transform = 'AgX'
    except TypeError:
        pass
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.clip_start = 0.003
    lights = []

    def area(name, loc, tgt, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        lo.location = loc
        look(lo, tgt)
        try:
            lo.visible_camera = False
        except AttributeError:
            pass
        lights.append(lo)
    views = {
        'lab': ((0.58, 0.33, 0.95), (0.745, 0.59, 0.78), 30),
        'stage': ((0.665, 0.495, 0.83), (0.745, 0.605, 0.765), 42),
        'box': ((0.60, 0.56, 1.05), (0.73, 0.73, 0.82), 32),
        'bench': ((0.47, 0.50, 0.90), (0.54, 0.70, 0.75), 30),
        'preamp': ((0.78, 0.35, 0.86), (0.835, 0.49, 0.752), 38),
        'dmm': ((0.31, 0.17, 1.00), (0.462, 0.455, 0.765), 40),
        'seat': ((0.0, -0.16, 1.175), (0.12, 0.75, 0.74), 16),
    }
    for key, (loc, tgt, lens) in views.items():
        if ONLY and key not in ONLY:
            continue
        for lo in lights:
            bpy.data.objects.remove(lo, do_unlink=True)
        lights.clear()
        t = V(tgt)
        l = V(loc)
        fwd = (t - l).normalized()
        side = fwd.cross(V((0, 0, 1))).normalized()
        dist = (t - l).length
        area('key', t - side * dist * 0.8 - fwd * dist * 0.5 + V((0, 0, dist * 1.1)), t, 26 * dist ** 2, dist * 0.5)
        area('fill', t + side * dist * 1.0 - fwd * dist * 0.4 + V((0, 0, dist * 0.6)), t, 8 * dist ** 2, dist * 0.6)
        area('rim', t + fwd * dist * 0.35 + V((0, 0, dist * 1.5)), t, 16 * dist ** 2, dist * 0.4)
        if key == 'seat':
            for lo in lights:
                lo.data.energy *= 1.0
        cam.location = loc
        look(cam, tgt)
        cam.data.lens = lens
        scene.render.filepath = os.path.join(PARTS, f'{NAME}_{key}.png')
        bpy.ops.render.render(write_still=True)
        print('WROTE', scene.render.filepath)


if __name__ == '__main__':
    main()
