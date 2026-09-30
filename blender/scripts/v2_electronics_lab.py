"""
v2_electronics_lab.py -- the STM "lab corner" for NEW_electronics (imported by v2_electronics.py; not run alone).

Adds, in room coordinates on the desk's right half:
  * an STM stage (visual reference: MechRedPanda/red-panda-stm CAD render only -- no CAD data used): black
    anodised base plate, coarse-approach sled driven by a 28BYJ-48-style stepper through a coupler and lead
    screw, two chrome guide rods, knurled fine-adjust thumbscrews, a slotted upright scanner block with a
    piezo tube + tip facing the sample, a small steel sample cup and an SMA bulkhead for the tip lead.
    The triangular frame, rods and suspended disc (vibration isolation) are deliberately omitted.
  * an open copper Faraday box (0.8 mm sheet, soldered corner seams, flange, BNC + SMA bulkheads) with its lid
    leaning against the left side,
  * a Teensy-4.1-style board on a breadboard (jumpers from the Uno), a small transimpedance preamp PCB
    (BNC + SMA + DC jack, shield can, trimpot), RG174 coax preamp -> box and RG316 coax preamp -> stage,
  * a handheld multimeter with plugged probe leads.

Clearances were checked against room.blend: PC x 0.497-0.971 / y >= 0.821, NEW_cables coil cable
x 0.833-0.945 / y 0.561-0.789, screwdriver (tip at 0.641,0.636), Red Bull x 0.693-0.760 / y 0.422-0.490,
small parts Mesh_142/144/145 at x 0.818-0.838 / y 0.566-0.606, mouse x <= 0.381.
"""
import math
import random
import numpy as np

E = None


def bind(mod):
    global E
    E = mod
    g = globals()
    for k in dir(mod):
        if not k.startswith('__') and k not in ('bind', 'build_lab', 'E'):
            g.setdefault(k, getattr(mod, k))


DESK = 0.735
BOX_C = (0.735, 0.665)
STAGE_C = (0.740, 0.530)
BB_C = (0.555, 0.675)
PRE_C = (0.845, 0.400)
DMM_C = (0.590, 0.415)
BOX_W, BOX_H, SHEET = 160.0, 150.0, 0.8


# ----------------------------------------------------------------------------- materials
def lab_mats():
    pbr('anod_black', (0.035, 0.035, 0.04), 0.42, 0.85, rvar=0.06, bump=0.08, bscale=9000, bdist=0.00002)
    pbr('steel', (0.74, 0.74, 0.75), 0.28, 1.0, rvar=0.05)
    pbr('steel_dark', (0.20, 0.20, 0.21), 0.35, 1.0)
    pbr('brass', (0.86, 0.70, 0.38), 0.3, 1.0, rvar=0.05)
    pbr('piezo_white', (0.92, 0.91, 0.87), 0.5)
    pbr('electrode', (0.78, 0.78, 0.8), 0.35, 1.0, bump=0.1, bscale=4000)
    pbr('motor_blue', (0.10, 0.30, 0.78), 0.4)
    pbr('jst_white', (0.93, 0.92, 0.86), 0.45)
    pbr('wire_orange', (0.95, 0.45, 0.08), 0.32, coat=0.2)
    pbr('wire_pink', (0.95, 0.55, 0.65), 0.32, coat=0.2)
    pbr('coax_black', (0.04, 0.04, 0.045), 0.42, rvar=0.05)
    pbr('coax_brown', (0.55, 0.33, 0.17), 0.25, coat=0.3)
    pbr('bb_side', (0.93, 0.92, 0.88), 0.45)
    pbr('dmm_holster', (0.96, 0.64, 0.07), 0.72, bump=0.3, bscale=2000)
    pbr('dmm_red', (0.78, 0.06, 0.05), 0.4)
    pbr('dmm_black', (0.03, 0.03, 0.03), 0.45)
    pbr('trimpot_blue', (0.08, 0.25, 0.75), 0.4)
    pbr('rubber_clear', (0.2, 0.2, 0.2), 0.5)
    copper_mat()


def copper_mat():
    name = 'copper_sheet'
    if name in MATS:
        return name
    m, nt, b = new_mat(name)
    setin(b, 'Metallic', 1.0)
    tc = node(nt, 'ShaderNodeTexCoord', (-1800, 0))
    fresh, tarn, dark = lin((0.97, 0.62, 0.48)), lin((0.70, 0.40, 0.27)), lin((0.50, 0.30, 0.25))
    nz = node(nt, 'ShaderNodeTexNoise', (-1500, 300), Scale=14.0, Detail=5.0, Roughness=0.6)
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = node(nt, 'ShaderNodeMapRange', (-1300, 300))
    mr.inputs['From Min'].default_value = 0.38
    mr.inputs['From Max'].default_value = 0.72
    nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
    c1 = node(nt, 'ShaderNodeMix', (-1000, 300))
    c1.data_type = 'RGBA'
    nt.links.new(mr.outputs['Result'], c1.inputs['Factor'])
    c1.inputs[6].default_value = (*fresh, 1)
    c1.inputs[7].default_value = (*tarn, 1)
    nz2 = node(nt, 'ShaderNodeTexNoise', (-1500, 0), Scale=70.0, Detail=3.0)
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    spot = math_n(nt, 'MULTIPLY', math_n(nt, 'GREATER_THAN', nz2.outputs['Fac'], 0.66), 0.28)
    c2 = node(nt, 'ShaderNodeMix', (-800, 300))
    c2.data_type = 'RGBA'
    nt.links.new(spot, c2.inputs['Factor'])
    nt.links.new(c1.outputs[2], c2.inputs[6])
    c2.inputs[7].default_value = (*dark, 1)
    # fingerprints: sparse voronoi cells, ridged, raise roughness and dull the colour a little
    vo = node(nt, 'ShaderNodeTexVoronoi', (-1500, -300), Scale=55.0)
    nt.links.new(tc.outputs['Object'], vo.inputs['Vector'])
    sc = node(nt, 'ShaderNodeSeparateColor', (-1300, -400))
    nt.links.new(vo.outputs['Color'], sc.inputs[0])
    keep = math_n(nt, 'GREATER_THAN', sc.outputs[0], 0.86)
    inside = math_n(nt, 'LESS_THAN', vo.outputs['Distance'], 0.30)
    fp = math_n(nt, 'MULTIPLY', keep, inside)
    ridge = math_n(nt, 'ABSOLUTE', math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', vo.outputs['Distance'], 260.0)))
    fpr = math_n(nt, 'MULTIPLY', fp, math_n(nt, 'ADD', math_n(nt, 'MULTIPLY', ridge, 0.6), 0.4))
    c3 = node(nt, 'ShaderNodeMix', (-600, 300))
    c3.data_type = 'RGBA'
    c3.blend_type = 'MULTIPLY'
    nt.links.new(math_n(nt, 'MULTIPLY', fpr, 0.12), c3.inputs['Factor'])
    nt.links.new(c2.outputs[2], c3.inputs[6])
    c3.inputs[7].default_value = (0.8, 0.75, 0.72, 1)
    nt.links.new(c3.outputs[2], b.inputs['Base Color'])
    nz3 = node(nt, 'ShaderNodeTexNoise', (-1100, -700), Scale=400.0, Detail=2.0)
    nt.links.new(tc.outputs['Object'], nz3.inputs['Vector'])
    rough = math_n(nt, 'ADD', math_n(nt, 'ADD', 0.3, math_n(nt, 'MULTIPLY', nz3.outputs['Fac'], 0.12)),
                   math_n(nt, 'ADD', math_n(nt, 'MULTIPLY', fpr, 0.2), math_n(nt, 'MULTIPLY', spot, 0.15)))
    nt.links.new(rough, b.inputs['Roughness'])
    bp = node(nt, 'ShaderNodeBump', (-300, -500), Strength=0.25, Distance=0.00003)
    nt.links.new(math_n(nt, 'ADD', nz3.outputs['Fac'], math_n(nt, 'MULTIPLY', fpr, 0.5)), bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return name


# ----------------------------------------------------------------------------- small hardware
def knurl_loop(r, n=40, depth=0.25):
    return [((r - depth * (k % 2)) * math.cos(2 * math.pi * k / n), (r - depth * (k % 2)) * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def thumbscrew(mb, M, head_r=3.6, head_l=9.0, shank_r=1.5, shank_l=12.0):
    """knurled thumbscrew along +z: head from z=0..head_l, shank below (negative z) with a cone point."""
    k = mb.mark()
    kl = knurl_loop(head_r, 36, 0.28)
    loops = [[(x * 0.9, y * 0.9, 0.0) for x, y in kl], [(x, y, 0.5) for x, y in kl], [(x, y, head_l - 0.5) for x, y in kl],
             [(x * 0.9, y * 0.9, head_l) for x, y in kl]]
    loft(mb, loops, 'steel', M, cap0=True, cap1=True)
    mb.recalc(k)
    revolve(mb, [(shank_r * 1.3, 0.0), (shank_r, -1.0), (shank_r, -shank_l + 1.2), (0.3, -shank_l), (0.0, -shank_l - 0.1)],
            16, 'steel', M)


def shcs(mb, M, d=3.0):
    """socket head cap screw head sitting on z=0."""
    hr = d * 0.85
    revolve(mb, [(0.0, 0.0), (hr, 0.0), (hr, d * 0.95), (hr - 0.25, d), (d * 0.45, d), (d * 0.45, d * 0.55),
                 (0.0, d * 0.55)], 20, 'steel_dark', M)


def pan_screw(mb, M, d=3.0, mat='steel'):
    revolve(mb, [(0.0, 0.0), (d * 0.95, 0.0), (d * 0.95, d * 0.35), (d * 0.8, d * 0.6), (0.0, d * 0.68)], 16, mat, M)
    slab(mb, 'steel_dark', M @ T(0, 0, d * 0.55), d * 1.2, 0.35, 0.16)
    slab(mb, 'steel_dark', M @ T(0, 0, d * 0.55) @ Rz(90), d * 1.2, 0.35, 0.16)


def bnc_plug(mb, M, cable_r=1.4):
    """BNC plug mated on a jack, axis +z from the jack face (z=0); returns cable exit (local) at +z."""
    kl = knurl_loop(7.0, 40, 0.3)
    k = mb.mark()
    loft(mb, [[(x * 0.93, y * 0.93, 0.0) for x, y in kl], [(x, y, 0.8) for x, y in kl], [(x, y, 11.0) for x, y in kl],
              [(x * 0.9, y * 0.9, 11.6) for x, y in kl]], 'nickel', M, cap0=True, cap1=True)
    mb.recalc(k)
    revolve(mb, [(4.6, 11.4), (4.6, 17.0), (4.2, 17.6), (4.2, 19.0)], 20, 'nickel', M)
    revolve(mb, [(4.4, 19.0), (4.1, 24.0), (3.0, 31.0), (cable_r * 1.25, 38.0), (cable_r * 1.05, 38.5)], 20,
            'tpe_black', M)
    return 38.5


def bnc_jack_panel(mb, M):
    """bulkhead BNC jack: flange + nut on the panel (z=0 outer face), barrel to +z."""
    k = mb.mark()
    prism(mb, 'nickel', M, [(7.0 * math.cos(math.radians(60 * i + 30)), 7.0 * math.sin(math.radians(60 * i + 30)))
                            for i in range(6)], 0.0, 2.6)
    mb.recalc(k)
    revolve(mb, [(5.2, 2.6), (4.8, 3.0), (4.8, 5.0)], 20, 'nickel', M)


def sma_plug(mb, M, cable_r=1.25):
    k = mb.mark()
    prism(mb, 'gold', M, [(4.6 * math.cos(math.radians(60 * i + 30)), 4.6 * math.sin(math.radians(60 * i + 30)))
                          for i in range(6)], 0.0, 5.0)
    mb.recalc(k)
    revolve(mb, [(2.6, 5.0), (2.6, 9.0), (2.0, 9.5), (1.9, 14.0), (cable_r * 1.25, 15.5), (cable_r * 1.05, 16.0)], 16,
            'gold', M)
    return 16.0


def sma_jack(mb, M):
    k = mb.mark()
    prism(mb, 'gold', M, [(4.0 * math.cos(math.radians(60 * i + 30)), 4.0 * math.sin(math.radians(60 * i + 30)))
                          for i in range(6)], 0.0, 2.0)
    mb.recalc(k)
    revolve(mb, [(3.1, 2.0), (3.1, 4.0)], 16, 'gold', M)


def cable(mb, pts, r, mat, sides=10, step=0.002):
    path, L = spline(pts, step)
    sweep(mb, path, circle2(r, sides), mat, up=(0, 0, 1))
    return L


def wm(M_world, p_mm):
    """world point (metres) of a local mm point under a world matrix M_world (metres)."""
    return M_world @ (V(p_mm) * MM)


def wd(M_world, d):
    return (M_world.to_3x3() @ V(d)).normalized()


# ----------------------------------------------------------------------------- STM stage
def build_stage(coll, parent):
    mb = MB('elec_stm_stage')
    I = Matrix.Identity(4)
    # base plate with counterbored cap screws
    slab(mb, 'anod_black', I, 95.0, 66.0, 7.0, rc=4.0, seg=3, rt=0.6, tseg=1, rb=0.4, bseg=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            disc(mb, 'port_dark', T(sx * 40.0, sy * 27.0, 7.004), 3.1, 16)
            shcs(mb, T(sx * 40.0, sy * 27.0, 7.0 - 3.0 + 0.2), 3.0)
    # coarse-approach sled (rides on the plate) with the sample post
    slab(mb, 'anod_black', T(-14.0, 0.0, 7.0), 40.0, 34.0, 11.0, rc=1.2, seg=2, rt=0.4, tseg=1)
    slab(mb, 'anod_black', T(-3.0, 0.0, 18.0), 8.0, 16.0, 20.0, rc=1.0, seg=2, rt=0.4, tseg=1)
    revolve(mb, [(0.0, 0.0), (6.0, 0.0), (6.0, 1.6), (5.7, 1.9), (0.0, 1.9)], 28, 'steel',
            T(1.0, 0.0, 30.0) @ Ry(90))
    disc(mb, 'gold', T(2.95, 0.0, 30.0) @ Ry(90), 4.5, 24)
    # motor bracket + 28BYJ-48-style stepper (axis along +x), coupler, lead screw
    slab(mb, 'anod_black', T(-36.0, 0.0, 18.0), 4.0, 34.0, 32.0, rc=0.8, seg=1, rt=0.4, tseg=1)
    Mm = T(-38.0, 0.0, 34.0) @ Ry(-90)
    revolve(mb, [(0.0, 0.0), (14.0, 0.0), (14.0, 0.6), (13.6, 1.0), (13.6, 17.4), (14.0, 17.8), (14.0, 19.0),
                 (12.8, 19.3), (0.0, 19.3)], 36, 'nickel', Mm)
    prism(mb, 'nickel', Mm @ Rz(90), [(p[0], p[1]) for p in rr(49.0, 7.0, 3.5, 4)], 0.0, 0.8)
    for sy in (-1, 1):
        revolve(mb, [(0.0, 0.8), (2.6, 0.8), (2.6, 2.2), (0.0, 2.6)], 12, 'steel_dark', Mm @ T(0, sy * 17.5, 0) @ Rx(0))
    slab(mb, 'motor_blue', Mm @ T(0.0, 0.0, 2.0) @ T(15.5, 0, 0), 5.0, 16.0, 14.0, rc=0.6, seg=1, rt=0.4, tseg=1)
    revolve(mb, [(2.5, -4.0), (2.5, 0.2), (0.0, 0.2)], 12, 'steel', T(-34.0, 0.0, 34.0 - 8.0) @ Ry(90))
    revolve(mb, [(5.0, 0.0), (5.0, 16.0), (0.0, 16.0), (0.0, 0.0)], 20, 'alu_can', T(-34.0, 0.0, 26.0) @ Ry(90))
    for sgn in (-1, 1):
        revolve(mb, [(0.9, 2.0), (0.9, 3.4)], 8, 'steel_dark', T(-34.0 + 2.6, 0.0, 26.0 + sgn * 5.0) @ Ry(0))
    revolve(mb, [(1.5, 0.0), (1.5, 21.0), (0.0, 21.0)], 12, 'steel', T(-18.0, 0.0, 26.0) @ Ry(90))
    # guide rods (chrome) from bracket to upright
    for zz, yy in ((44.0, 10.0), (44.0, -10.0)):
        revolve(mb, [(0.0, 0.0), (2.0, 0.0), (2.0, 55.0), (0.0, 55.0)], 14, 'chrome', T(-36.0, yy, zz) @ Ry(90))
    # upright scanner block: inner plate + outer slotted plate
    slab(mb, 'anod_black', T(22.0, 0.0, 7.0), 8.0, 46.0, 50.0, rc=0.8, seg=1, rt=0.5, tseg=1)
    slab(mb, 'anod_black', T(32.0, 0.0, 7.0), 5.0, 50.0, 54.0, rc=0.8, seg=1, rt=0.5, tseg=1)
    for i in range(5):
        yy = (i - 2) * 9.8
        slab(mb, 'anod_black', T(37.5, yy, 7.0), 6.0, 8.4, 54.0, rc=0.5, seg=1, rt=0.5, tseg=1)
    slab(mb, 'port_dark', T(36.0, 0.0, 7.5), 2.0, 48.0, 52.0)
    # piezo tube + tip holder + tip (pointing -x at the sample)
    Mp = T(18.0, 0.0, 30.0) @ Ry(-90)
    revolve(mb, [(3.2, 0.0), (3.2, 8.0)], 24, 'piezo_white', Mp)
    for q in range(4):
        revolve(mb, [(3.23, 1.0), (3.23, 7.2)], 5, 'electrode', Mp, a0=math.radians(90 * q + 8),
                a1=math.radians(90 * q + 82), closed=False)
    revolve(mb, [(3.3, 8.0), (3.3, 9.0), (1.2, 9.4), (0.8, 10.2), (0.0, 10.2)], 20, 'steel', Mp)
    revolve(mb, [(0.13, 10.2), (0.13, 12.5), (0.01, 13.2)], 8, 'steel', Mp)
    # fine-adjust thumbscrews in an angled block on the sled
    slab(mb, 'anod_black', T(-16.0, -12.0, 18.0), 14.0, 10.0, 12.0, rc=0.6, seg=1, rt=0.4, tseg=1)
    slab(mb, 'anod_black', T(-16.0, 12.0, 18.0), 14.0, 10.0, 12.0, rc=0.6, seg=1, rt=0.4, tseg=1)
    for yy in (-12.0, 12.0):
        thumbscrew(mb, T(-16.0 - 7.0, yy, 30.0 + 7.0) @ Ry(-40), 3.6, 9.0, 1.5, 10.0)
    thumbscrew(mb, T(22.0, -23.0, 44.0) @ Rx(90), 3.4, 8.0, 1.5, 7.0)
    # sample cup (steel), SMA bulkhead bracket
    revolve(mb, [(0.0, 7.0), (7.0, 7.0), (7.0, 18.0), (6.6, 18.3), (6.2, 18.0), (6.2, 7.8), (0.0, 7.8)], 28, 'steel',
            T(10.0, -25.0, 0.0))
    slab(mb, 'anod_black', T(25.0, -30.0, 7.0), 12.0, 3.0, 16.0, rc=0.3, seg=1)
    sma_jack(mb, T(25.0, -31.5, 16.0) @ Rx(90))
    o = mb.finish(parent, coll, sharp=38)
    # motor wires to a white JST plug resting on the base plate
    w = MB('elec_stm_stage_wires')
    cols = ['wire_blue', 'wire_pink', 'wire_yellow', 'wire_orange', 'wire_red']
    for i, cm in enumerate(cols):
        dy = (i - 2) * 1.1
        pts = [(-54.0, dy, 41.0), (-57.0, dy, 44.0), (-62.0, dy * 1.5, 40.0), (-60.0, dy * 2.0 - 8.0, 22.0),
               (-50.0, dy * 1.2 - 20.0, 9.0), (-40.0, dy - 26.0, 7.6), (-33.0, dy - 26.0, 7.6)]
        path, _ = spline(pts, 1.2)
        sweep(w, path, circle2(0.5, 6), cm, up=(0, 0, 1))
    slab(w, 'jst_white', T(-29.0, -26.0, 7.0), 8.0, 7.0, 4.5, rc=0.3, seg=1, rt=0.3, tseg=1)
    o2 = w.finish(parent, coll, sharp=50)
    return [o, o2]


# ----------------------------------------------------------------------------- Faraday box + lid
def build_box(coll, parent):
    mb = MB('elec_faraday_box')
    W, H, t = BOX_W, BOX_H, SHEET
    z0 = 1.5
    k = mb.mark()
    loops = [rr(W, W, 1.2, 2, z0), rr(W, W, 1.2, 2, z0 + H), rr(W + 12.0, W + 12.0, 1.5, 2, z0 + H),
             rr(W + 12.0, W + 12.0, 1.5, 2, z0 + H + t), rr(W - 2 * t, W - 2 * t, 0.4, 2, z0 + H + t),
             rr(W - 2 * t, W - 2 * t, 0.4, 2, z0 + t)]
    loft(mb, loops, 'copper_sheet', None, cap0=True, cap1=True)
    mb.recalc(k)
    # soldered seams: lumpy tin beads down the four outer corners and round the inside floor
    rng = random.Random(3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts = [V((sx * (W / 2 + 0.1), sy * (W / 2 + 0.1), z0 + 2 + (H - 4) * i / 30)) for i in range(31)]
            sweep(mb, pts, lambda i, n: circle2(0.75 + 0.25 * math.sin(i * 1.7 + sx) + 0.1 * rng.random(), 8),
                  'solder', up=(1, 0, 0), cap0=True, cap1=True)
    for side in range(4):
        R = Rz(90 * side)
        pts = [R @ V(((-W / 2 + t + 2) + (W - 2 * t - 4) * i / 24, -(W / 2 - t - 0.3), z0 + t + 0.3)) for i in range(25)]
        sweep(mb, pts, lambda i, n: circle2(0.8 + 0.2 * math.sin(i * 2.3 + side), 6), 'solder', up=(0, 0, 1),
              cap0=True, cap1=True)
    # tapped holes in the flange
    for side in range(4):
        for s in (-1, 1):
            p = Rz(90 * side) @ V((s * 45.0, W / 2 + 3.0, z0 + H + t + 0.005))
            disc(mb, 'port_dark', T(*p), 1.25, 12)
    # rubber feet
    for sx in (-1, 1):
        for sy in (-1, 1):
            revolve(mb, [(0.0, 0.0), (5.0, 0.0), (5.0, 1.0), (4.4, 1.5), (0.0, 1.5)], 16, 'rubber',
                    T(sx * 65.0, sy * 65.0, 0.0))
    # bulkheads on the front face (y = -W/2): BNC (to the preamp) and a capped SMA
    Mb = T(65.0, -W / 2, 46.5) @ Rx(90)
    bnc_jack_panel(mb, Mb)
    revolve(mb, [(0.0, 0.0), (8.0, 0.0), (8.0, 0.8), (0.0, 0.8)], 6, 'nickel', T(65.0, -W / 2 + t, 46.5) @ Rx(-90))
    sma_jack(mb, T(40.0, -W / 2, 45.0) @ Rx(90))
    revolve(mb, [(3.3, 4.0), (3.3, 7.0), (2.9, 7.5), (0.0, 7.5)], 12, 'gold', T(40.0, -W / 2, 45.0) @ Rx(90))
    ob = mb.finish(parent, coll, sharp=40)
    # lid: tray (top plate + 15 mm skirt), captive pan-head screws, leaning on the box's left side
    lid = MB('elec_faraday_lid')
    Lw = W + 12.0 + 2 * t + 1.0
    k = lid.mark()
    loops = [rr(Lw - 2 * t, Lw - 2 * t, 1.2, 2, 0.0), rr(Lw - 2 * t, Lw - 2 * t, 1.2, 2, -15.0), rr(Lw, Lw, 2.0, 2, -15.0),
             rr(Lw, Lw, 2.0, 2, t)]
    loft(lid, loops, 'copper_sheet', None, cap0=True, cap1=True)
    lid.recalc(k)
    for side in range(4):
        for s in (-1, 1):
            p = Rz(90 * side) @ V((s * 45.0, Lw / 2 - 9.0, t))
            pan_screw(lid, T(*p), 3.0)
    revolve(lid, [(0.0, t), (9.0, t), (9.0, t + 1.0), (7.5, t + 2.0), (6.0, t + 12.0), (6.8, t + 14.0), (0.0, t + 15.0)],
            24, 'brass')
    a = math.radians(8.0)
    sa, ca = math.sin(a), math.cos(a)
    # plate normal points -x (away from the box's left face); the skirt tips rest on the flange edge
    xl = BOX_C[0] - W / 2 * MM
    Oz = (Lw / 2 * ca + 15.0 * sa)
    zf = z0 + H + t
    xf = (zf - Oz + 15.0 * sa) / ca
    Ox = -6.0 - sa * xf - 15.0 * ca
    O = V((xl + Ox * MM, BOX_C[1], DESK + Oz * MM))
    Ml = Matrix(((sa, 0.0, -ca, O.x), (0.0, 1.0, 0.0, O.y), (ca, 0.0, sa, O.z), (0, 0, 0, 1)))
    # lean it on the BACK face instead (clear of the screwdriver on the left): rotate about the box centre
    cx, cy = BOX_C
    Ml = T(cx, cy, 0.0) @ Rz(-90) @ T(-cx, -cy, 0.0) @ Ml
    ol = lid.finish(None, coll, sharp=40)
    ol.parent = parent
    ol.matrix_world = Ml
    return [ob, ol]


# ----------------------------------------------------------------------------- breadboard + Teensy
def breadboard_texture():
    cv = Canvas(82.5, 54.5, 12.0)
    for c in range(30):
        x = (c - 14.5) * 2.54
        for k in range(1, 6):
            for sg in (-1, 1):
                cv.rect('hole', x, sg * k * 2.54, 1.05, 1.05, r=0.1)
        if c % 5 == 0 or c == 29:
            cv.text(str(c + 1), x, 15.9, 1.1, 0, name='print')
            cv.text(str(c + 1), x, -15.9, 1.1, 0, name='print')
    for k, ch in zip(range(1, 6), 'FGHIJ'):
        cv.text(ch, -39.2, k * 2.54, 1.2, 0, name='print')
    for k, ch in zip(range(1, 6), 'EDCBA'):
        cv.text(ch, -39.2, -k * 2.54, 1.2, 0, name='print')
    for sg in (-1, 1):
        for g in range(5):
            for h in range(5):
                x = -30.5 + g * 15.24 + h * 2.54
                for y in (19.05, 21.59):
                    cv.rect('hole', x, sg * y, 1.05, 1.05, r=0.1)
        cv.seg('red', -38.0, sg * 24.2, 38.0, sg * 24.2, 0.5)
        cv.seg('blue', -38.0, sg * 16.45, 38.0, sg * 16.45, 0.5)
    H, W = cv.H, cv.W
    g = lambda n: np.clip(cv.layer(n), 0, 1)[..., None]
    col = np.ones((H, W, 3), np.float32) * np.array((0.94, 0.93, 0.89), np.float32)
    col = col * (1 - g('red')) + np.array((0.85, 0.15, 0.12), np.float32) * g('red')
    col = col * (1 - g('blue')) + np.array((0.12, 0.3, 0.8), np.float32) * g('blue')
    col = col * (1 - g('print')) + np.array((0.35, 0.35, 0.36), np.float32) * g('print')
    col = col * (1 - g('hole')) + np.array((0.05, 0.05, 0.05), np.float32) * g('hole')
    hole = g('hole')[..., 0]
    dat = np.stack([0.6 - 0.6 * hole, 0.45 + 0.3 * hole, np.zeros_like(hole)], -1)
    ic = make_image('elec_breadboard_col', col)
    idt = make_image('elec_breadboard_dat', dat, noncolor=True)
    return image_mat('breadboard_top', ic, idt, bump_dist=0.0006, rnoise=0.03)


def build_breadboard(coll, parent):
    mb = MB('elec_breadboard')
    mt = breadboard_texture()
    W, D, H = 82.5, 54.5, 8.5
    # two halves either side of the centre channel; top UV-mapped to the printed texture
    for y0, y1 in ((-D / 2, -1.5), (1.5, D / 2)):
        rings = slab(mb, 'bb_side', T(0.0, (y0 + y1) / 2, 0.0), W, y1 - y0, H, rc=0.6, seg=1, topmat=mt)
        top = mb.flist[-1]
        for l in top.loops:
            co = l.vert.co / MM
            l[mb.uv].uv = ((co.x + W / 2) / W, (co.y + D / 2) / D)
    slab(mb, 'bb_side', T(0.0, 0.0, 0.0), W - 1.0, 3.2, H - 3.0)
    slab(mb, 'rubber_clear', T(0.0, 0.0, -0.01), W - 2.0, D - 2.0, 0.02)
    o = mb.finish(parent, coll, sharp=40)
    # Teensy-4.1-style board straddling the channel on down-facing headers
    B = Board('elec_teensy', 61.0, 17.8, 1.6, 30, (0.02, 0.30, 0.12), (0.07, 0.42, 0.18), (0.94, 0.94, 0.92),
              (0.95, 0.77, 0.45), T(0.0, 0.0, H + 2.5), bottom_col=(0.02, 0.3, 0.12))
    B.outline = fillet_rect(61.0, 17.8, 0.8, 3)
    labels_a = ['GND', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '3.3V', '24', '25', '26', '27',
                '28', '29', '30', '31', '32']
    labels_b = ['VIN', 'GND', '3.3V', '23', '22', '21', '20', '19', '18', '17', '16', '15', '14', '13', 'GND', '41',
                '40', '39', '38', '37', '36', '35', '34', '33']
    for sg, labs in ((-1, labels_a), (1, labels_b)):
        header_male(B, 0.0, sg * 7.62, 24, rows=1, rot=0, down=True, spacer=2.5, below=6.0)
        for i, t in enumerate(labs):
            x = (i - 11.5) * 2.54 * (1 if sg < 0 else -1)
            B.text(t, x, sg * 5.3, 0.55, 90, anchor='l' if sg > 0 else 'r')
    mbp = B.parts
    k = mbp.mark()
    slab(mbp, 'ic_black', B.PM(3.0, 0.0, B.t + 0.25), 10.0, 10.0, 1.15, rc=0.3, seg=1, rt=0.1, tseg=1)
    mbp.recalc(k)
    B.cv.rect('silk', 3.0, 0.0, 11.0, 11.0, lw=0.12)
    micro_usb(mbp, B.PM(31.7, 0.0, B.t + 1.3, 0))
    B.pad(28.4, 0.0, 0, 0, 0, 5.5, 3.0)
    k = mbp.mark()
    slab(mbp, 'nickel', B.PM(-24.0, 0.0), 14.2, 13.0, 1.8, rc=0.4, seg=1)
    slab(mbp, 'port_dark', B.PM(-30.95, 0.0, B.t + 0.4), 0.3, 11.0, 1.0)
    mbp.recalc(k)
    qfn(B, 14.0, 3.6, 4.0, 6, 0.5, rot=0)
    qfn(B, -11.0, -3.8, 3.0, 5, 0.5, rot=0)
    soic8(B, 16.5, -3.4, rot=0)
    crystal_smd(B, 10.0, -5.6, rot=0, l=3.2, w=2.5)
    crystal_smd(B, -7.0, 4.8, rot=90, l=2.0, w=1.2)
    tact(B, -14.5, 3.8, rot=0, w=3.0, d=2.6, h=1.0, pd=1.3, cap='plastic_white', plate=False)
    led(B, 22.8, 3.8, 'led_yellow_off', 0)
    for (px, py, r, kd) in [(-4.0, -5.2, 0, 'C'), (-4.0, 5.2, 0, 'C'), (9.4, 5.5, 0, 'R'), (20.5, 5.6, 90, 'C'),
                            (22.8, -5.4, 0, 'C'), (-8.2, -4.9, 90, 'R'), (-16.8, -4.6, 0, 'C'), (7.4, -1.2, 90, 'C'),
                            (-2.0, 0.0, 90, 'C'), (19.6, 0.4, 90, 'R'), (12.0, -1.0, 0, 'C'), (-18.0, 0.8, 90, 'R')]:
        passive(B, px, py, '0402', r, kd)
    for i in range(6):
        B.pad(-17.0 + i * 1.27, -6.6, 0, 0, 0, 0.8, 1.1, layer='pad')
    B.fanout(frac=0.5, to_targets=0.3, wd=0.15)
    objs = [o] + B.finalize(parent, coll)
    return objs


# ----------------------------------------------------------------------------- preamp PCB
def build_preamp(coll, parent):
    B = Board('elec_preamp', 50.0, 40.0, 1.6, 30, (0.26, 0.07, 0.34), (0.36, 0.13, 0.45), (0.95, 0.95, 0.93),
              (0.95, 0.77, 0.45), T(0.0, 0.0, 6.0), bottom_col=(0.26, 0.07, 0.34))
    B.outline = fillet_rect(50.0, 40.0, 2.0, 4)
    mb = B.parts
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 21.5, sy * 16.5
            B.holes.append(hole_loop(x, y, 1.6, 16))
            B.cv.circle('pad', x, y, 2.9)
            B.cv.circle('clr', x, y, 3.3)
            k = mb.mark()
            prism(mb, 'brass', T(x, y, 0.0), [(3.2 * math.cos(math.radians(60 * i)), 3.2 * math.sin(math.radians(60 * i)))
                                               for i in range(6)], 0.0, 6.0)
            mb.recalc(k)
            pan_screw(mb, B.PM(x, y), 3.0)
    # shield can over the transimpedance front end
    k = mb.mark()
    slab(mb, 'nickel', B.PM(-5.0, -4.0), 16.0, 13.0, 4.0, rc=0.5, seg=1, rt=0.3, tseg=1)
    mb.recalc(k)
    for i in range(4):
        disc(mb, 'port_dark', B.PM(-11.0 + i * 4.0, -4.0, B.t + 4.005), 0.7, 10)
    B.silk_box(-5.0, -4.0, 0, 17.0, 14.0)
    soic8(B, 10.0, -6.0, rot=90)
    soic8(B, 10.0, 8.0, rot=90)
    electrolytic(B, -14.0, 11.0, d=5.0, h=5.4)
    electrolytic(B, -4.0, 12.0, d=5.0, h=5.4)
    # 3296W trimpot
    k = mb.mark()
    slab(mb, 'trimpot_blue', B.PM(3.0, 14.0), 9.5, 4.8, 10.0, rc=0.3, seg=1, rt=0.4, tseg=1)
    mb.recalc(k)
    revolve(mb, [(0.0, 0.0), (1.1, 0.0), (1.1, 1.2), (0.0, 1.2)], 12, 'brass', B.PM(6.4, 14.0, B.t + 7.5) @ Ry(90))
    slab(mb, 'steel_dark', B.PM(7.65, 14.0, B.t + 7.5 - 0.15), 0.1, 1.8, 0.3)
    for (px, py, r, kd, lb) in [(-16.0, -2.0, 90, 'R', 'R1'), (-16.0, -8.0, 90, 'C', 'C1'), (3.0, -1.0, 0, 'R', 'RF'),
                               (3.0, 3.0, 0, 'C', 'CF'), (16.0, 2.0, 90, 'C', None), (16.0, -12.5, 0, 'R', None),
                               (-3.0, 5.5, 0, 'C', None), (20.0, 8.0, 90, 'C', None), (-18.0, 3.0, 0, 'R', 'R4')]:
        passive(B, px, py, '0805', r, kd, lb)
    led(B, 17.0, 14.5, 'led_green_on', 0)
    B.text('PWR', 17.0, 12.6, 0.8, 0)
    B.text('TIA PREAMP V2', -4.0, -14.8, 1.3, 0)
    B.text('BIAS', 3.0, 9.0, 0.8, 0)
    # BNC right-angle jack on the +y edge (to the box), SMA edge jack on the -x edge (to the stage), DC jack
    k = mb.mark()
    slab(mb, 'plastic_black', B.PM(-15.0, 13.5), 14.0, 13.0, 12.5, rc=0.6, seg=1, rt=0.5, tseg=1)
    mb.recalc(k)
    bnc_jack_panel(mb, B.PM(-15.0, 20.0, B.t + 7.0) @ Rx(-90))
    for sgn in (-1, 1):
        B.pad(-15.0, 13.5, 0, sgn * 5.0, 0.0, 2.6, 2.6)
    k = mb.mark()
    slab(mb, 'gold', B.PM(-24.0, -8.0), 5.0, 6.4, 6.4, rc=0.2, seg=1)
    mb.recalc(k)
    sma_jack(mb, B.PM(-26.5, -8.0, B.t + 3.2) @ Ry(-90))
    barrel_jack(mb, B.PM(25.0 + 1.5, -8.0, rot=0))
    B.fanout(frac=0.5, to_targets=0.2)
    for a, b in (((-15.0, 13.0), (-5.0, 3.0)), ((-24.0, -8.0), (-12.0, -6.0)), ((20.0, -8.0), (10.0, -9.0))):
        B.route(a, b, 0.5)
    objs = B.finalize(parent, coll)
    # world attachment points for the coax runs
    Mw = parent.matrix_world
    bnc_front = wm(Mw, (-15.0, 22.6, 6.0 + B.t + 7.0))
    sma_front = wm(Mw, (-30.5, -8.0, 6.0 + B.t + 3.2))
    return objs, bnc_front, sma_front


# ----------------------------------------------------------------------------- multimeter
def dmm_textures():
    cv = Canvas(64.0, 30.0, 16.0)
    seg = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc', '5': 'afgcd', '6': 'afgedc', '7': 'abc',
           '8': 'abcdefg', '9': 'abcdfg'}

    def digit(ch, x, y, h=16.0):
        w = h * 0.5
        on = seg[ch]
        pos = {'a': (x, y + h / 2, w, 1.6), 'g': (x, y, w, 1.6), 'd': (x, y - h / 2, w, 1.6),
               'f': (x - w / 2, y + h / 4, 1.6, h / 2), 'b': (x + w / 2, y + h / 4, 1.6, h / 2),
               'e': (x - w / 2, y - h / 4, 1.6, h / 2), 'c': (x + w / 2, y - h / 4, 1.6, h / 2)}
        for sname, (px, py, sw, sh) in pos.items():
            cv.rect('seg' if sname in on else 'ghost', px + 0.12 * (py - y), py, sw * 0.86, sh * 0.86, r=0.4)
    for i, ch in enumerate('0873'):
        digit(ch, -18.0 + i * 11.5, -1.0)
    cv.rect('seg', -18.0 + 0.5 * 11.5 + 0.6, -9.2, 1.4, 1.4, r=0.3)
    cv.text('MV', 26.5, -8.5, 3.0)
    cv.text('AUTO', -22.0, 10.5, 2.4)
    H, W = cv.H, cv.W
    s = np.clip(cv.layer('seg'), 0, 1)[..., None]
    gh = np.clip(cv.layer('ghost'), 0, 1)[..., None] * 0.08
    tx = np.clip(cv.layer('silk'), 0, 1)[..., None]
    base = np.array((0.52, 0.58, 0.50), np.float32)
    col = np.ones((H, W, 3), np.float32) * base
    col = col * (1 - gh) + np.array((0.12, 0.13, 0.12), np.float32) * gh
    col = col * (1 - np.maximum(s, tx)) + np.array((0.08, 0.09, 0.08), np.float32) * np.maximum(s, tx)
    dat = np.stack([np.full((H, W), 0.5, np.float32), np.full((H, W), 0.08, np.float32), np.zeros((H, W), np.float32)], -1)
    ic = make_image('elec_dmm_lcd_col', col)
    idt = make_image('elec_dmm_lcd_dat', dat, noncolor=True)
    m_lcd = image_mat('dmm_lcd', ic, idt, bump_dist=0.00001, rnoise=0.0)
    # face: dial ring markings and jack labels on dark grey
    cv = Canvas(134.0, 70.0, 10.0)
    cx = -8.0
    for kk in range(12):
        a = math.radians(90 + 30 * kk)
        cv.seg('silk', cx + 24 * math.cos(a), 24 * math.sin(a), cx + 27.5 * math.cos(a), 27.5 * math.sin(a), 0.6)
    for kk, lab in enumerate(['OFF', 'V', 'MV', 'O', 'A', 'MA', 'HZ', 'C', 'NCV', 'UA', '%', 'V']):
        a = math.radians(90 + 30 * kk)
        cv.text(lab, cx + 31 * math.cos(a), 31 * math.sin(a), 2.6)
    for i, lab in enumerate(['10A', 'MA', 'COM', 'V']):
        cv.text(lab, -58.0, 22.0 - i * 14.0 - 6.0, 2.2)
    cv.rect('ylw', 40.0, -22.0, 40.0, 10.0, r=1.5, lw=0.5)
    H, W = cv.H, cv.W
    tx = np.clip(cv.layer('silk'), 0, 1)[..., None]
    yl = np.clip(cv.layer('ylw'), 0, 1)[..., None]
    col = np.ones((H, W, 3), np.float32) * np.array((0.19, 0.20, 0.22), np.float32)
    col = col * (1 - tx) + np.array((0.92, 0.92, 0.9), np.float32) * tx
    col = col * (1 - yl) + np.array((0.95, 0.72, 0.1), np.float32) * yl
    dat = np.stack([np.full((H, W), 0.5, np.float32) + 0.05 * tx[..., 0], 0.55 - 0.1 * tx[..., 0],
                    np.zeros((H, W), np.float32)], -1)
    ic = make_image('elec_dmm_face_col', col)
    idt = make_image('elec_dmm_face_dat', dat, noncolor=True)
    return m_lcd, image_mat('dmm_face', ic, idt, bump_dist=0.00002)


def build_dmm(coll, parent):
    m_lcd, m_face = dmm_textures()
    mb = MB('elec_multimeter')
    L, W, H = 150.0, 78.0, 34.0
    k = mb.mark()
    slab(mb, 'dmm_holster', Matrix.Identity(4), L, W, H, rc=9.0, seg=4, rt=5.0, tseg=3, rb=3.0, bseg=2)
    mb.recalc(k)
    rings = slab(mb, 'dmm_black', T(0.0, 0.0, H - 3.5), 134.0, 70.0, 3.8, rc=5.0, seg=3, topmat=m_face)
    for l in mb.flist[-1].loops:
        co = l.vert.co / MM
        l[mb.uv].uv = ((co.x + 67.0) / 134.0, (co.y + 35.0) / 70.0)
    rings = slab(mb, 'dmm_black', T(42.0, 0.0, H + 0.2), 66.0, 34.0, 0.25, rc=1.5, seg=2, topmat=m_lcd)
    for l in mb.flist[-1].loops:
        co = l.vert.co / MM
        l[mb.uv].uv = ((co.x - 42.0 + 32.0) / 64.0, (co.y + 15.0) / 30.0)
    # rotary dial with grip ridges and pointer
    dx = -8.0
    kl = knurl_loop(19.0, 48, 0.8)
    k = mb.mark()
    loft(mb, [[(dx + x, y, H + 0.2) for x, y in kl], [(dx + x, y, H + 7.0) for x, y in kl]], 'dmm_black', None,
         cap0=True, cap1=True)
    mb.recalc(k)
    slab(mb, 'dmm_black', T(dx, 0.0, H + 7.0), 34.0, 7.0, 3.0, rc=2.5, seg=3, rt=1.0, tseg=2)
    slab(mb, 'plastic_white', T(dx, 14.0, H + 10.0) @ Rz(90), 6.0, 1.2, 0.05)
    # buttons
    for i in range(4):
        slab(mb, 'dmm_black', T(28.0 + i * 11.0 - 16.0, -26.0, H + 0.2), 8.0, 5.0, 1.2, rc=1.0, seg=2, rt=0.5, tseg=1)
    # jacks: 10A, mA, COM, VΩ along the -x end
    jys = [22.0 - i * 14.0 - 6.0 + 2.5 for i in range(4)]
    for jy, rim in zip(jys, ('dmm_black', 'dmm_black', 'dmm_black', 'dmm_red')):
        revolve(mb, [(0.0, H - 1.2), (2.2, H - 1.2), (2.2, H + 0.2), (4.2, H + 0.2), (4.6, H + 0.9), (4.0, H + 1.2),
                     (2.2, H + 1.2)], 20, rim, T(-52.0, jy, 0.0))
    o = mb.finish(parent, coll, sharp=40)
    Mw = parent.matrix_world
    return [o], wm(Mw, (-52.0, jys[2], H)), wm(Mw, (-52.0, jys[3], H))


def probe(mb, Mw_probe, colour):
    """probe along +x from the rear (x=0) to the tip, lying on the desk (local z=0), in mm."""
    I = Matrix.Identity(4)
    prof = [(0.0, 0.0), (3.2, 0.0), (4.4, 6.0), (4.6, 55.0), (6.5, 58.0), (6.5, 61.0), (3.6, 63.0), (3.2, 80.0),
            (0.9, 81.5), (0.9, 96.0), (0.0, 98.5)]
    mats = [colour] * 8 + ['steel', 'steel']
    revolve(mb, prof, 20, colour, Mw_probe @ Ry(90), mats=mats)
    return Mw_probe


# ----------------------------------------------------------------------------- jumpers + coax (world frame)
def build_wiring(coll, parent, uno_M, bb_M, pre_pts, box_M, stage_M, dmm_pts):
    mb = MB('elec_lab_wiring', scale=1.0)
    hdr = 8.5
    # Uno far header (analog A0-A2 + 5V + GND) -> breadboard columns 1-3 on the +/- strips beside the Teensy
    X0, Y0 = 34.29, 26.67
    U = lambda X, Y: (X0 - X, Y0 - Y)
    jobs = [((27.94 + 2.54 * 4, 2.54), 'wire_red', (2, -5)), ((27.94 + 2.54 * 5, 2.54), 'wire_black', (1, -5)),
            ((50.8, 2.54), 'wire_yellow', (3, -4)), ((53.34, 2.54), 'wire_blue', (2, 4)),
            ((55.88, 2.54), 'wire_green', (3, 5))]
    for (X, Y), col, (c, row) in jobs:
        lx, ly = U(X, Y)
        src_top = wm(uno_M, (lx, ly, 1.6 + hdr + 14.0))
        # housing on the Uno header (drawn in world via the Uno frame)
        Mh = uno_M @ T(lx * MM, ly * MM, (1.6 + hdr) * MM)
        slab(mb, 'plastic_black', Mh, 0.0025, 0.0025, 0.014, rt=0.00035, tseg=1)
        bx = (c - 15.5) * 2.54
        by = row * 2.54
        dst = wm(bb_M, (bx, by, 8.5))
        Md = bb_M @ T(bx * MM, by * MM, 8.5 * MM)
        slab(mb, 'plastic_black', Md, 0.0025, 0.0025, 0.014, rt=0.00035, tseg=1)
        a = src_top + V((0, 0, 0.003))
        b = dst + V((0, 0, 0.017))
        mid = (a + b) / 2
        h = 0.013 + 0.0018 * abs(row)
        pts = [a, a + V((0, 0, 0.008)), mid.lerp(a, 0.45) + V((0, 0, h)), mid + V((0, 0, h * 1.1)),
               mid.lerp(b, 0.45) + V((0, 0, h)), b + V((0, 0, 0.008)), b]
        revolve(mb, [(0.0010, 0.0), (0.00095, 0.0011), (0.00078, 0.0027), (0.00066, 0.0032)], 8, col, T(*a) @ T(0, 0, -0.003))
        revolve(mb, [(0.0010, 0.0), (0.00095, 0.0011), (0.00078, 0.0027), (0.00066, 0.0032)], 8, col, T(*b) @ T(0, 0, -0.003))
        cable(mb, pts, 0.00065, col, sides=7, step=0.002)
    # coax 1: RG174, preamp BNC (+y) -> box front BNC (-y)
    bnc_pre, sma_pre = pre_pts
    e1 = bnc_plug(mb, T(*bnc_pre) @ Rx(-90) @ Matrix.Scale(MM, 4))
    p_pre = bnc_pre + V((0, e1 * MM, 0))
    box_bnc = wm(box_M, (65.0, -BOX_W / 2 - 2.6, 46.5))
    e2 = bnc_plug(mb, T(*box_bnc) @ Rx(90) @ Matrix.Scale(MM, 4))
    p_box = box_bnc - V((0, e2 * MM, 0))
    zc = DESK + 0.0014
    pts = [p_box, V((p_box.x, 0.530, p_box.z - 0.009)), V((p_box.x + 0.002, 0.515, zc + 0.008)),
           V((0.806, 0.500, zc)), V((0.815, 0.486, zc)), V((0.826, 0.476, zc + 0.002)),
           p_pre + V((0.0, 0.012, 0.004)), p_pre]
    L1 = cable(mb, pts, 0.0014, 'coax_black', sides=10)
    # coax 2: RG316, preamp SMA (-x) -> stage SMA (-y)
    e3 = sma_plug(mb, T(*sma_pre) @ Ry(-90) @ Matrix.Scale(MM, 4))
    p3 = sma_pre - V((e3 * MM, 0, 0))
    st_sma = wm(stage_M, (25.0, -35.5, 16.0))
    dirn = wd(stage_M, (0, -1, 0))
    Ms = T(*st_sma) @ (dirn.to_track_quat('Z', 'X').to_matrix().to_4x4()) @ Matrix.Scale(MM, 4)
    e4 = sma_plug(mb, Ms)
    p4 = st_sma + dirn * e4 * MM
    zc2 = DESK + 0.00125
    pts = [p4, p4 + dirn * 0.008 + V((0, 0, -0.006)), V((0.767, 0.455, zc2)), V((0.776, 0.425, zc2)),
           V((0.787, 0.400, zc2 + 0.001)), p3 - V((0.008, 0, 0.002)), p3]
    L2 = cable(mb, pts, 0.00125, 'coax_brown', sides=10)
    # multimeter leads: banana plugs in COM / VΩ, leads to probes lying left of the meter
    com, vo = dmm_pts
    for (jack, colour, tip_xy, rot) in ((com, 'dmm_black', (0.418, 0.372), 205.0), (vo, 'dmm_red', (0.428, 0.412), 198.0)):
        Mj = T(*jack)
        revolve(mb, [(0.0, 0.0), (0.0021, 0.0), (0.0021, 0.004), (0.0042, 0.0045), (0.0042, 0.018), (0.0036, 0.024),
                     (0.0024, 0.034), (0.0019, 0.036)], 18, colour, Mj)
        top = jack + V((0, 0, 0.036))
        r = math.radians(rot)
        d = V((math.cos(r), math.sin(r), 0))
        rear = V((tip_xy[0], tip_xy[1], DESK)) - d * 0.0985
        Mp = T(rear.x, rear.y, DESK + 0.0065) @ Rz(rot) @ Matrix.Scale(MM, 4)
        probe(mb, Mp, colour)
        pts = [top, top + V((0, 0, 0.02)), top + V((-0.03, 0.008, 0.022)), V((top.x - 0.05, top.y - 0.002, DESK + 0.01)),
               rear - d * 0.03 + V((0, 0, 0.0015)), rear - d * 0.004 + V((0, 0, 0.0055)), rear + V((0, 0, 0.0065))]
        cable(mb, pts, 0.0017, colour, sides=10)
    o = mb.finish(parent, coll, sharp=55)
    return [o], (L1, L2)


# ----------------------------------------------------------------------------- entry point
def build_lab(mod, coll, root):
    bind(mod)
    lab_mats()

    def empty(name, M):
        e = bpy.data.objects.new(name, None)
        coll.objects.link(e)
        e.parent = root
        e.matrix_world = M
        e.empty_display_size = 0.02
        return e
    import bpy as _bpy
    globals()['bpy'] = _bpy
    out = {}
    stage_M = T(STAGE_C[0], STAGE_C[1], DESK)
    e = empty('elec_stm_stage_grp', stage_M)
    out['stm_stage'] = build_stage(coll, e)
    box_M = T(BOX_C[0], BOX_C[1], DESK)
    e = empty('elec_faraday_grp', box_M)
    out['faraday_box'] = build_box(coll, e)
    bb_M = T(BB_C[0], BB_C[1], DESK)
    e = empty('elec_breadboard_grp', bb_M)
    out['breadboard_teensy'] = build_breadboard(coll, e)
    pre_M = T(PRE_C[0], PRE_C[1], DESK) @ Rz(0)
    e = empty('elec_preamp_grp', pre_M)
    bpy.context.view_layer.update()
    objs, bnc_p, sma_p = build_preamp(coll, e)
    out['preamp'] = objs
    dmm_M = T(DMM_C[0], DMM_C[1], DESK)
    e = empty('elec_multimeter_grp', dmm_M)
    bpy.context.view_layer.update()
    objs, com, vo = build_dmm(coll, e)
    out['multimeter'] = objs
    e = empty('elec_lab_wiring_grp', Matrix.Identity(4))
    uno_M = bpy.data.objects['elec_uno'].matrix_world.copy()
    w, lens = build_wiring(coll, e, uno_M, bb_M, (bnc_p, sma_p), box_M, stage_M, (com, vo))
    out['lab_wiring'] = w
    return out
