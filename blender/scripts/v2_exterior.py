"""
v2_exterior.py -- the street outside the study window: a quiet Canadian suburban crescent, fully 3D,
in ROOM coordinates (Z-up, metres, room floor z = 0, outside grade z = -3.0).

    "<blender>" -b --factory-startup --python blender/scripts/v2_exterior.py
Writes blender/scene/parts/exterior.blend with ONE collection NEW_exterior under ONE root empty
NEW_exterior_root (identity transform).  Replaces room.blend's placeholders Mesh_184..Mesh_187.

Layout (looking out of the window along +Y):
  y 1.54          our house's outer wall face (lap siding, window trim, sill, eave)
  y 1.54..8.0     our front lawn / driveway          y 8.0..9.5   sidewalk (1.5 m slabs)
  y 9.5..12.0     boulevard with a young maple         y 12.0..21.0 curbs + 8.7 m crowned asphalt
  y 21.0..24.0    boulevard: hydro poles, street light, hydrant, community mailbox, bins
  y 24.0..25.5    sidewalk                            y 32         house fronts across (15 m lots)
  y 54            rear lot line / fences / backyard trees; further rows of houses fade into haze.
Haze: every exterior material ends in the EXT_haze group -- distance-based in-scatter toward the
same multiple-scattering sky the world uses (so it melts into the horizon); no volume, so the
room's sunlight is untouched.
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector as V, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.abspath(os.path.join(HERE, '..', 'scene', 'parts'))
OUT = os.path.join(PARTS, 'exterior.blend')

G = -3.0                 # outside grade (room floor is z = 0)
FY = 1.54                # outer face of the window wall
WIN = (-1.32, 1.02, 0.70, 2.50)
S0 = 16.5                # main street centreline
FRONT = 32.0             # house front walls across the street
LOT = 15.0
HAZE_L = 260.0           # haze e-folding distance (m)
HAZE_D0 = 10.0           # haze starts this far from the camera

rnd = random.Random(1360)


def ground_z(y):
    """Terrain height: flat through the first block, then a very gentle rise (rooflines layer up)."""
    t = max(0.0, y - 60.0)
    return G + 0.012 * t * t / (t + 40.0)


# =====================================================================================  scene
scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)
for m in list(bpy.data.meshes):
    bpy.data.meshes.remove(m)
COL = bpy.data.collections.new('NEW_exterior')
scene.collection.children.link(COL)
ROOT = bpy.data.objects.new('NEW_exterior_root', None)
ROOT.empty_display_size = 2.0
COL.objects.link(ROOT)

# =====================================================================================  materials
MATS = {}


def nd(nt, t, **kw):
    n = nt.nodes.new(t)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def lk(nt, a, b):
    nt.links.new(a, b)


def sv(n, key, val):
    n.inputs[key].default_value = val


def math_n(nt, op, a=None, b=None, c=None, clamp=False):
    if isinstance(c, bool):
        clamp, c = c, None
    n = nd(nt, 'ShaderNodeMath', operation=op)
    n.use_clamp = clamp
    for i, x in enumerate((a, b, c)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            lk(nt, x, n.inputs[i])
    return n.outputs[0]


def mixc(nt, fac, a, b):
    n = nd(nt, 'ShaderNodeMix', data_type='RGBA')
    n.blend_type = 'MIX'
    for sock, x in ((n.inputs[0], fac), (n.inputs[6], a), (n.inputs[7], b)):
        if isinstance(x, (int, float)):
            sock.default_value = x
        elif isinstance(x, tuple):
            sock.default_value = x if len(x) == 4 else (*x, 1.0)
        else:
            lk(nt, x, sock)
    return n.outputs[2]


def mulc(nt, a, b):
    n = nd(nt, 'ShaderNodeMix', data_type='RGBA')
    n.blend_type = 'MULTIPLY'
    n.inputs[0].default_value = 1.0
    for sock, x in ((n.inputs[6], a), (n.inputs[7], b)):
        if isinstance(x, tuple):
            sock.default_value = x if len(x) == 4 else (*x, 1.0)
        else:
            lk(nt, x, sock)
    return n.outputs[2]


def noise(nt, vec, scale, detail=4.0, rough=0.55, dim='3D'):
    n = nd(nt, 'ShaderNodeTexNoise')
    n.noise_dimensions = dim
    sv(n, 'Scale', scale)
    sv(n, 'Detail', detail)
    sv(n, 'Roughness', rough)
    if vec is not None:
        lk(nt, vec, n.inputs['Vector'])
    return n


def ramp(nt, fac, stops, interp='LINEAR'):
    n = nd(nt, 'ShaderNodeValToRGB')
    n.color_ramp.interpolation = interp
    els = n.color_ramp.elements
    while len(els) > 1:
        els.remove(els[-1])
    els[0].position, els[0].color = stops[0][0], (*stops[0][1], 1.0)
    for p, c in stops[1:]:
        e = els.new(p)
        e.color = (*c, 1.0)
    lk(nt, fac, n.inputs[0])
    return n.outputs[0]


def pos(nt):
    return nd(nt, 'ShaderNodeNewGeometry').outputs['Position']


def objinfo(nt):
    return nd(nt, 'ShaderNodeObjectInfo')


def vscale(nt, vec, s):
    n = nd(nt, 'ShaderNodeVectorMath', operation='MULTIPLY')
    lk(nt, vec, n.inputs[0])
    n.inputs[1].default_value = s if isinstance(s, tuple) else (s, s, s)
    return n.outputs[0]


def xyz(nt, vec):
    n = nd(nt, 'ShaderNodeSeparateXYZ')
    lk(nt, vec, n.inputs[0])
    return n.outputs


def comb(nt, x, y, z):
    n = nd(nt, 'ShaderNodeCombineXYZ')
    for i, s in enumerate((x, y, z)):
        if isinstance(s, (int, float)):
            n.inputs[i].default_value = s
        else:
            lk(nt, s, n.inputs[i])
    return n.outputs[0]


def bump(nt, height, strength, dist=0.01, normal=None):
    n = nd(nt, 'ShaderNodeBump')
    sv(n, 'Strength', strength)
    sv(n, 'Distance', dist)
    lk(nt, height, n.inputs['Height'])
    if normal is not None:
        lk(nt, normal, n.inputs['Normal'])
    return n.outputs[0]


def haze_group():
    g = bpy.data.node_groups.get('EXT_haze')
    if g:
        return g
    g = bpy.data.node_groups.new('EXT_haze', 'ShaderNodeTree')
    g.interface.new_socket('Shader', in_out='INPUT', socket_type='NodeSocketShader')
    g.interface.new_socket('Shader', in_out='OUTPUT', socket_type='NodeSocketShader')
    nt = g
    gi = nd(nt, 'NodeGroupInput')
    go = nd(nt, 'NodeGroupOutput')
    cam = nd(nt, 'ShaderNodeCameraData')
    d = math_n(nt, 'SUBTRACT', cam.outputs['View Distance'], HAZE_D0)
    d = math_n(nt, 'MAXIMUM', d, 0.0)
    d = math_n(nt, 'MULTIPLY', d, -1.0 / HAZE_L)
    tr = math_n(nt, 'EXPONENT', d)
    f1 = math_n(nt, 'SUBTRACT', 1.0, tr)
    fac = math_n(nt, 'MULTIPLY', math_n(nt, 'POWER', f1, 1.7), 0.97)   # clear near, dense only far away
    # in-scatter colour = the world's own sky just above the horizon in the view direction (so the far
    # distance melts into the horizon); at mid distances use the dimmer anti-sun horizon tone instead
    geo = nd(nt, 'ShaderNodeNewGeometry')
    dv = vscale(nt, geo.outputs['Incoming'], -1.0)
    c = xyz(nt, dv)
    zc = math_n(nt, 'MAXIMUM', c[2], 0.035)

    def skylook(yv):
        dirn = nd(nt, 'ShaderNodeVectorMath', operation='NORMALIZE')
        lk(nt, comb(nt, c[0], yv, zc), dirn.inputs[0])
        sky = nd(nt, 'ShaderNodeTexSky')
        for attr, val in (('sky_type', 'MULTIPLE_SCATTERING'), ('sun_disc', False), ('sun_elevation', 0.3735004663467407),
                          ('sun_rotation', 0.0), ('altitude', 100.0), ('air_density', 1.0), ('aerosol_density', 1.0),
                          ('ozone_density', 1.0), ('sun_intensity', 1.0)):
            try:
                setattr(sky, attr, val)
            except (TypeError, AttributeError):
                pass
        lk(nt, dirn.outputs[0], sky.inputs['Vector'])
        return sky.outputs[0]
    s_true = skylook(c[1])
    s_anti = skylook(math_n(nt, 'MULTIPLY', c[1], -1.0))
    col = mixc(nt, math_n(nt, 'POWER', fac, 1.5), s_anti, s_true)
    em = nd(nt, 'ShaderNodeEmission')
    lk(nt, col, em.inputs['Color'])
    sv(em, 'Strength', 0.35)              # = world Background strength in room.blend
    mix = nd(nt, 'ShaderNodeMixShader')
    lk(nt, fac, mix.inputs[0])
    lk(nt, gi.outputs[0], mix.inputs[1])
    lk(nt, em.outputs[0], mix.inputs[2])
    lk(nt, mix.outputs[0], go.inputs[0])
    return g


def new_mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    nt.nodes.clear()
    MATS[name] = m
    return m, nt


def finish(m, nt, shader):
    grp = nd(nt, 'ShaderNodeGroup')
    grp.node_tree = haze_group()
    lk(nt, shader, grp.inputs[0])
    out = nd(nt, 'ShaderNodeOutputMaterial')
    lk(nt, grp.outputs[0], out.inputs['Surface'])
    return m


def principled(nt, col, rough, normal=None, **kw):
    p = nd(nt, 'ShaderNodeBsdfPrincipled')
    if isinstance(col, tuple):
        sv(p, 'Base Color', (*col, 1.0) if len(col) == 3 else col)
    else:
        lk(nt, col, p.inputs['Base Color'])
    if isinstance(rough, (int, float)):
        sv(p, 'Roughness', rough)
    else:
        lk(nt, rough, p.inputs['Roughness'])
    if normal is not None:
        lk(nt, normal, p.inputs['Normal'])
    for k, v in kw.items():
        if isinstance(v, (int, float, tuple)):
            sv(p, k, v)
        else:
            lk(nt, v, p.inputs[k])
    return p


def simple(name, col, rough=0.5, grain=0.0, grain_scale=60.0, bstr=0.0, **kw):
    """Plain material with a little colour mottling and fine bump."""
    m, nt = new_mat(name)
    P = pos(nt)
    c = col
    if grain > 0:
        n = noise(nt, P, grain_scale, 5, 0.6)
        c = mixc(nt, math_n(nt, 'MULTIPLY', n.outputs['Fac'], 1.0), tuple(x * (1 - grain) for x in col),
                 tuple(min(1.0, x * (1 + grain)) for x in col))
    rn = noise(nt, P, grain_scale * 0.7, 3, 0.5)
    r = math_n(nt, 'MULTIPLY_ADD', rn.outputs['Fac'], 0.16, rough - 0.08)
    nrm = bump(nt, noise(nt, P, grain_scale * 4, 3, 0.6).outputs['Fac'], bstr, 0.004) if bstr > 0 else None
    return finish(m, nt, principled(nt, c, r, nrm, **kw).outputs[0])


def mat_siding(name, geo=False):
    """Vinyl lap siding. Colour = object colour (per-house tint). Lap shadow lines in bump unless geo."""
    m, nt = new_mat(name)
    P = pos(nt)
    oi = objinfo(nt)
    base = oi.outputs['Color']
    n = noise(nt, P, 3.0, 3, 0.5)
    tint = mixc(nt, n.outputs['Fac'], (0.93, 0.93, 0.93), (1.05, 1.05, 1.04))
    c = mulc(nt, base, tint)
    # faint grime toward grade
    oz = xyz(nt, nd(nt, 'ShaderNodeTexCoord').outputs['Object'])[2]
    grime = math_n(nt, 'SUBTRACT', 1.0, math_n(nt, 'MULTIPLY', oz, 1.2), clamp=True)
    c = mixc(nt, math_n(nt, 'MULTIPLY', grime, 0.22), c, (0.30, 0.29, 0.26))
    grain = noise(nt, vscale(nt, P, (60.0, 60.0, 4.0)), 1.0, 4, 0.6).outputs['Fac']
    if geo:
        h = grain
        nrm = bump(nt, h, 0.05, 0.002)
    else:
        z = xyz(nt, P)[2]
        lap = math_n(nt, 'FRACT', math_n(nt, 'DIVIDE', z, 0.178))
        h = math_n(nt, 'SUBTRACT', 1.0, lap)
        h = math_n(nt, 'ADD', h, math_n(nt, 'MULTIPLY', grain, 0.05))
        nrm = bump(nt, h, 0.55, 0.012)
    return finish(m, nt, principled(nt, c, 0.42, nrm, **{'Specular IOR Level': 0.4}).outputs[0])


def mat_brick(name):
    """Modular clay brick (190x57 + 10 mm joints) in world-aligned running bond; hue from object random."""
    m, nt = new_mat(name)
    P = pos(nt)
    c = xyz(nt, P)
    u = math_n(nt, 'ADD', c[0], c[1])
    vec = comb(nt, u, c[2], 0.0)
    oi = objinfo(nt)
    b = nd(nt, 'ShaderNodeTexBrick')
    b.offset = 0.5
    b.offset_frequency = 2
    lk(nt, vec, b.inputs['Vector'])
    sv(b, 'Scale', 1.0)
    sv(b, 'Brick Width', 0.200)
    sv(b, 'Row Height', 0.067)
    sv(b, 'Mortar Size', 0.010)
    sv(b, 'Mortar Smooth', 0.15)
    sv(b, 'Bias', 0.0)
    pal = ramp(nt, oi.outputs['Random'], [(0.0, (0.30, 0.10, 0.07)), (0.34, (0.30, 0.10, 0.07)),
                                           (0.35, (0.42, 0.30, 0.20)), (0.67, (0.42, 0.30, 0.20)),
                                           (0.68, (0.22, 0.12, 0.09)), (1.0, (0.22, 0.12, 0.09))], 'CONSTANT')
    # per-brick variation from the brick node's own random colour
    sv(b, 'Color1', (0.80, 0.80, 0.80, 1))
    sv(b, 'Color2', (1.15, 1.1, 1.05, 1))
    sv(b, 'Mortar', (0.0, 0.0, 0.0, 1))
    bc = mulc(nt, pal, b.outputs['Color'])
    sp = noise(nt, P, 90.0, 3, 0.7).outputs['Fac']
    bc = mixc(nt, math_n(nt, 'MULTIPLY', sp, 0.35), bc, (0.12, 0.08, 0.06))
    col = mixc(nt, b.outputs['Fac'], bc, (0.52, 0.50, 0.46))
    h = math_n(nt, 'SUBTRACT', 1.0, b.outputs['Fac'])
    h = math_n(nt, 'ADD', h, math_n(nt, 'MULTIPLY', sp, 0.15))
    nrm = bump(nt, h, 0.5, 0.006)
    return finish(m, nt, principled(nt, col, 0.85, nrm).outputs[0])


def mat_shingle(name):
    """Laminated asphalt shingles, rows on world z (6/12 pitch => 0.0626 z per 143 mm course)."""
    m, nt = new_mat(name)
    P = pos(nt)
    c = xyz(nt, P)
    u = math_n(nt, 'ADD', c[0], c[1])
    s = math_n(nt, 'MULTIPLY', c[2], 2.236)
    vec = comb(nt, u, s, 0.0)
    b = nd(nt, 'ShaderNodeTexBrick')
    b.offset = 0.37
    b.offset_frequency = 1
    lk(nt, vec, b.inputs['Vector'])
    sv(b, 'Scale', 1.0)
    sv(b, 'Brick Width', 0.33)
    sv(b, 'Row Height', 0.143)
    sv(b, 'Mortar Size', 0.006)
    sv(b, 'Mortar Smooth', 0.4)
    sv(b, 'Color1', (0.75, 0.75, 0.75, 1))
    sv(b, 'Color2', (1.25, 1.22, 1.2, 1))
    sv(b, 'Mortar', (0.25, 0.25, 0.25, 1))
    oi = objinfo(nt)
    pal = ramp(nt, oi.outputs['Random'], [(0.0, (0.085, 0.085, 0.09)), (0.4, (0.085, 0.085, 0.09)),
                                           (0.41, (0.13, 0.105, 0.085)), (0.72, (0.13, 0.105, 0.085)),
                                           (0.73, (0.11, 0.115, 0.12)), (1.0, (0.11, 0.115, 0.12))], 'CONSTANT')
    gr = noise(nt, P, 220.0, 2, 0.5).outputs['Fac']
    col = mulc(nt, pal, b.outputs['Color'])
    col = mulc(nt, col, mixc(nt, gr, (0.8, 0.8, 0.8), (1.2, 1.2, 1.2)))
    weather = noise(nt, P, 0.6, 3, 0.5).outputs['Fac']
    col = mixc(nt, math_n(nt, 'MULTIPLY', weather, 0.3), col, (0.16, 0.16, 0.15))
    h = math_n(nt, 'ADD', b.outputs['Fac'], math_n(nt, 'MULTIPLY', gr, 0.3))
    nrm = bump(nt, h, 0.45, 0.01)
    return finish(m, nt, principled(nt, col, 0.9, nrm).outputs[0])


def mat_concrete(name, base=(0.43, 0.42, 0.40), joints=False, broom=True):
    m, nt = new_mat(name)
    P = pos(nt)
    n1 = noise(nt, P, 0.9, 4, 0.6).outputs['Fac']
    n2 = noise(nt, P, 14.0, 5, 0.6).outputs['Fac']
    col = mixc(nt, n1, tuple(x * 0.82 for x in base), tuple(x * 1.1 for x in base))
    col = mixc(nt, math_n(nt, 'MULTIPLY', n2, 0.35), col, tuple(x * 0.7 for x in base))
    stain = noise(nt, P, 2.5, 3, 0.7).outputs['Fac']
    col = mixc(nt, math_n(nt, 'MULTIPLY', math_n(nt, 'SUBTRACT', stain, 0.58, clamp=True), 1.6), col,
               tuple(x * 0.62 for x in base))
    h = noise(nt, P, 180.0, 3, 0.6).outputs['Fac']
    if broom:
        c = xyz(nt, P)
        w = nd(nt, 'ShaderNodeTexWave')
        lk(nt, comb(nt, c[1], c[0], c[2]), w.inputs['Vector'])
        sv(w, 'Scale', 400.0)
        sv(w, 'Distortion', 6.0)
        sv(w, 'Detail', 2.0)
        h = math_n(nt, 'ADD', h, math_n(nt, 'MULTIPLY', w.outputs['Fac'], 0.25))
    nrm = bump(nt, h, 0.25, 0.003)
    r = math_n(nt, 'MULTIPLY_ADD', n2, 0.12, 0.78)
    return finish(m, nt, principled(nt, col, r, nrm).outputs[0])


def mat_asphalt(name, base=0.075, patch=False):
    m, nt = new_mat(name)
    P = pos(nt)
    c = xyz(nt, P)
    n1 = noise(nt, P, 0.35, 4, 0.6).outputs['Fac']
    agg = nd(nt, 'ShaderNodeTexVoronoi')
    lk(nt, P, agg.inputs['Vector'])
    sv(agg, 'Scale', 140.0)
    speck = ramp(nt, agg.outputs['Distance'], [(0.0, (0.26, 0.25, 0.24)), (0.22, (0.07, 0.07, 0.07)),
                                               (1.0, (0.05, 0.05, 0.05))])
    b = base
    col = mixc(nt, n1, (b * 0.85, b * 0.84, b * 0.82), (b * 1.25, b * 1.23, b * 1.2))
    col = mixc(nt, 0.35, col, speck)
    if not patch:
        # wheel paths polished lighter; gutters collect sand/dirt
        dy = math_n(nt, 'ABSOLUTE', math_n(nt, 'SUBTRACT', c[1], S0))
        wp = math_n(nt, 'ABSOLUTE', math_n(nt, 'SUBTRACT', dy, 2.3))
        wpath = math_n(nt, 'SUBTRACT', 1.0, math_n(nt, 'DIVIDE', wp, 0.75), clamp=True)
        col = mixc(nt, math_n(nt, 'MULTIPLY', wpath, 0.35), col, (b * 1.6, b * 1.58, b * 1.55))
        edge = math_n(nt, 'SUBTRACT', math_n(nt, 'DIVIDE', dy, 4.2), 0.86, clamp=True)
        col = mixc(nt, math_n(nt, 'MULTIPLY', edge, 5.0), col, (0.16, 0.145, 0.12))
        oil = noise(nt, comb(nt, math_n(nt, 'MULTIPLY', c[0], 0.3), c[1], 0.0), 1.2, 3, 0.6).outputs['Fac']
        lane = math_n(nt, 'SUBTRACT', 1.0, math_n(nt, 'DIVIDE', math_n(nt, 'ABSOLUTE', math_n(nt, 'SUBTRACT', dy, 2.3)), 0.5), clamp=True)
        oilm = math_n(nt, 'MULTIPLY', math_n(nt, 'SUBTRACT', oil, 0.6, clamp=True), lane)
        col = mixc(nt, math_n(nt, 'MULTIPLY', oilm, 3.0), col, (0.035, 0.035, 0.035))
    else:
        col = mulc(nt, col, (0.8, 0.8, 0.82))
    h = math_n(nt, 'ADD', math_n(nt, 'SUBTRACT', 1.0, agg.outputs['Distance']),
               math_n(nt, 'MULTIPLY', noise(nt, P, 30, 3, 0.5).outputs['Fac'], 0.4))
    nrm = bump(nt, h, 0.35, 0.004)
    r = math_n(nt, 'MULTIPLY_ADD', n1, 0.15, 0.72 if not patch else 0.62)
    return finish(m, nt, principled(nt, col, r, nrm).outputs[0])


def mat_grass(name):
    m, nt = new_mat(name)
    P = pos(nt)
    n1 = noise(nt, P, 0.25, 4, 0.6).outputs['Fac']
    n2 = noise(nt, P, 3.0, 4, 0.6).outputs['Fac']
    n3 = noise(nt, P, 140.0, 2, 0.5).outputs['Fac']
    col = ramp(nt, n1, [(0.3, (0.075, 0.095, 0.030)), (0.55, (0.10, 0.115, 0.040)), (0.72, (0.16, 0.15, 0.065))])
    col = mixc(nt, math_n(nt, 'MULTIPLY', n2, 0.5), col, (0.06, 0.08, 0.028))
    c = xyz(nt, P)
    stripe = math_n(nt, 'GREATER_THAN', math_n(nt, 'FRACT', math_n(nt, 'DIVIDE', c[0], 1.6)), 0.5)
    col = mixc(nt, math_n(nt, 'MULTIPLY', stripe, 0.12), col, (0.14, 0.16, 0.07))
    col = mixc(nt, math_n(nt, 'MULTIPLY', n3, 0.5), col, (0.05, 0.06, 0.02))
    nrm = bump(nt, n3, 0.6, 0.01)
    return finish(m, nt, principled(nt, col, 0.93, nrm, **{'Specular IOR Level': 0.25}).outputs[0])


def mat_glass_house(name):
    """Window glass: see-through (so shadow rays light the blinds) plus a Fresnel sky reflection."""
    m, nt = new_mat(name)
    tr = nd(nt, 'ShaderNodeBsdfTransparent')
    sv(tr, 'Color', (0.55, 0.58, 0.58, 1))
    gl = principled(nt, (0.02, 0.02, 0.02), 0.03, **{'Specular IOR Level': 1.0})
    lw = nd(nt, 'ShaderNodeLayerWeight')
    sv(lw, 'Blend', 0.35)
    f = math_n(nt, 'MULTIPLY_ADD', lw.outputs['Fresnel'], 0.8, 0.18)
    mix = nd(nt, 'ShaderNodeMixShader')
    lk(nt, f, mix.inputs[0])
    lk(nt, tr.outputs[0], mix.inputs[1])
    lk(nt, gl.outputs[0], mix.inputs[2])
    return finish(m, nt, mix.outputs[0])


def mat_blinds(name):
    m, nt = new_mat(name)
    P = pos(nt)
    z = xyz(nt, P)[2]
    sl = math_n(nt, 'FRACT', math_n(nt, 'DIVIDE', z, 0.025))
    h = math_n(nt, 'SINE', math_n(nt, 'MULTIPLY', sl, 3.14159))
    oi = objinfo(nt)
    col = ramp(nt, oi.outputs['Random'], [(0.0, (0.62, 0.60, 0.55)), (0.5, (0.62, 0.60, 0.55)),
                                          (0.51, (0.55, 0.50, 0.42)), (1.0, (0.55, 0.50, 0.42))], 'CONSTANT')
    col = mulc(nt, col, mixc(nt, h, (0.55, 0.55, 0.55), (1.0, 1.0, 1.0)))
    tr = nd(nt, 'ShaderNodeBsdfTranslucent')
    lk(nt, col, tr.inputs['Color'])
    p = principled(nt, col, 0.6)
    mix = nd(nt, 'ShaderNodeMixShader')
    sv(mix, 0, 0.25)
    lk(nt, p.outputs[0], mix.inputs[1])
    lk(nt, tr.outputs[0], mix.inputs[2])
    return finish(m, nt, mix.outputs[0])


def mat_curtain(name):
    m, nt = new_mat(name)
    oi = objinfo(nt)
    col = ramp(nt, oi.outputs['Random'], [(0.0, (0.55, 0.52, 0.46)), (0.33, (0.55, 0.52, 0.46)),
                                          (0.34, (0.30, 0.32, 0.30)), (0.66, (0.30, 0.32, 0.30)),
                                          (0.67, (0.45, 0.36, 0.30)), (1.0, (0.45, 0.36, 0.30))], 'CONSTANT')
    tr = nd(nt, 'ShaderNodeBsdfTranslucent')
    lk(nt, col, tr.inputs['Color'])
    p = principled(nt, col, 0.9)
    mix = nd(nt, 'ShaderNodeMixShader')
    sv(mix, 0, 0.3)
    lk(nt, p.outputs[0], mix.inputs[1])
    lk(nt, tr.outputs[0], mix.inputs[2])
    return finish(m, nt, mix.outputs[0])


def mat_door(name):
    m, nt = new_mat(name)
    oi = objinfo(nt)
    col = ramp(nt, oi.outputs['Random'], [(0.0, (0.22, 0.035, 0.03)), (0.25, (0.22, 0.035, 0.03)),
                                          (0.26, (0.035, 0.05, 0.09)), (0.5, (0.035, 0.05, 0.09)),
                                          (0.51, (0.02, 0.02, 0.02)), (0.75, (0.02, 0.02, 0.02)),
                                          (0.76, (0.60, 0.58, 0.53)), (1.0, (0.60, 0.58, 0.53))], 'CONSTANT')
    return finish(m, nt, principled(nt, col, 0.35, **{'Coat Weight': 0.3}).outputs[0])


def mat_wood(name, base, stripes=0.0, grain_axis='z'):
    m, nt = new_mat(name)
    P = pos(nt)
    c = xyz(nt, P)
    if grain_axis == 'z':
        vec = comb(nt, math_n(nt, 'MULTIPLY', c[0], 30.0), math_n(nt, 'MULTIPLY', c[1], 30.0), math_n(nt, 'MULTIPLY', c[2], 1.5))
    else:
        vec = comb(nt, math_n(nt, 'MULTIPLY', c[0], 1.5), math_n(nt, 'MULTIPLY', c[1], 1.5), math_n(nt, 'MULTIPLY', c[2], 30.0))
    g = noise(nt, vec, 2.0, 6, 0.65).outputs['Fac']
    col = mixc(nt, g, tuple(x * 0.72 for x in base), tuple(x * 1.2 for x in base))
    wt = noise(nt, P, 1.5, 3, 0.5).outputs['Fac']
    col = mixc(nt, math_n(nt, 'MULTIPLY', wt, 0.35), col, (0.28, 0.27, 0.25))
    h = g
    if stripes > 0:
        u = math_n(nt, 'ADD', c[0], c[1])
        s = math_n(nt, 'FRACT', math_n(nt, 'DIVIDE', u, stripes))
        gap = math_n(nt, 'LESS_THAN', s, 0.07)
        col = mixc(nt, math_n(nt, 'MULTIPLY', gap, 0.8), col, (0.03, 0.025, 0.02))
        h = math_n(nt, 'SUBTRACT', h, gap)
    nrm = bump(nt, h, 0.4, 0.006)
    return finish(m, nt, principled(nt, col, 0.85, nrm).outputs[0])


def mat_leaf(name, c0, c1, c2):
    m, nt = new_mat(name)
    geo = nd(nt, 'ShaderNodeNewGeometry')
    oi = objinfo(nt)
    rr = math_n(nt, 'FRACT', math_n(nt, 'ADD', geo.outputs['Random Per Island'], oi.outputs['Random']))
    col = ramp(nt, rr, [(0.0, c0), (0.6, c1), (0.93, c1), (1.0, c2)])
    P = geo.outputs['Position']
    n = noise(nt, P, 0.8, 3, 0.5).outputs['Fac']
    col = mixc(nt, math_n(nt, 'MULTIPLY', n, 0.4), col, tuple(x * 0.65 for x in c0))
    tr = nd(nt, 'ShaderNodeBsdfTranslucent')
    lk(nt, mulc(nt, col, (1.2, 1.35, 0.8)), tr.inputs['Color'])
    p = principled(nt, col, 0.6, bump(nt, noise(nt, P, 60, 3, 0.5).outputs['Fac'], 0.2, 0.002),
                   **{'Specular IOR Level': 0.3})
    mix = nd(nt, 'ShaderNodeMixShader')
    sv(mix, 0, 0.3)
    lk(nt, p.outputs[0], mix.inputs[1])
    lk(nt, tr.outputs[0], mix.inputs[2])
    return finish(m, nt, mix.outputs[0])


def mat_bark(name, base=(0.12, 0.10, 0.085)):
    m, nt = new_mat(name)
    P = pos(nt)
    c = xyz(nt, P)
    vec = comb(nt, math_n(nt, 'MULTIPLY', c[0], 12.0), math_n(nt, 'MULTIPLY', c[1], 12.0), math_n(nt, 'MULTIPLY', c[2], 1.2))
    n = noise(nt, vec, 3.0, 6, 0.7).outputs['Fac']
    col = mixc(nt, n, tuple(x * 0.6 for x in base), tuple(x * 1.5 for x in base))
    nrm = bump(nt, n, 0.8, 0.02)
    return finish(m, nt, principled(nt, col, 0.92, nrm).outputs[0])


def mat_paint(name, col, rough=0.35, coat=0.0, metallic=0.0, objcol=False):
    m, nt = new_mat(name)
    P = pos(nt)
    c = objinfo(nt).outputs['Color'] if objcol else col
    n = noise(nt, P, 8.0, 3, 0.5).outputs['Fac']
    r = math_n(nt, 'MULTIPLY_ADD', n, 0.1, rough - 0.05)
    return finish(m, nt, principled(nt, c, r, Metallic=metallic, **{'Coat Weight': coat, 'Coat Roughness': 0.05}).outputs[0])


def mat_emit_dark(name, col):
    m, nt = new_mat(name)
    return finish(m, nt, principled(nt, col, 0.95).outputs[0])


def mat_sign(name):
    """Octagon face: retro-reflective red; the white legend/border are separate geometry."""
    m, nt = new_mat(name)
    P = pos(nt)
    n = noise(nt, P, 80, 3, 0.5).outputs['Fac']
    col = mixc(nt, n, (0.42, 0.018, 0.02), (0.5, 0.03, 0.03))
    return finish(m, nt, principled(nt, col, 0.35, **{'Specular IOR Level': 0.7}).outputs[0])


print('materials...')
mat_siding('ext_siding')
mat_siding('ext_siding_geo', geo=True)
mat_brick('ext_brick')
mat_shingle('ext_shingle')
simple('ext_trim', (0.66, 0.65, 0.62), 0.38, 0.03, 20.0, 0.1)
simple('ext_soffit', (0.60, 0.59, 0.56), 0.5, 0.03, 20.0, 0.2)
simple('ext_dark', (0.018, 0.018, 0.018), 0.6)
simple('ext_interior', (0.035, 0.03, 0.026), 0.9, 0.3, 1.2)
simple('ext_shutter', (0.03, 0.035, 0.035), 0.5, 0.05, 30.0, 0.2)
simple('ext_metal', (0.42, 0.42, 0.41), 0.35, 0.05, 40.0, 0.1, Metallic=0.8)
simple('ext_galv', (0.50, 0.50, 0.49), 0.45, 0.2, 5.0, 0.1, Metallic=0.9)
simple('ext_insulator', (0.30, 0.31, 0.30), 0.18)
simple('ext_wire', (0.02, 0.02, 0.02), 0.45)
simple('ext_rubber', (0.025, 0.025, 0.025), 0.75, 0.2, 30.0, 0.1)
simple('ext_plastic_black', (0.03, 0.03, 0.03), 0.5)
simple('ext_mulch', (0.10, 0.06, 0.04), 0.95, 0.4, 25.0, 0.6)
simple('ext_stone', (0.36, 0.34, 0.31), 0.7, 0.2, 12.0, 0.3)
simple('ext_bin_blue', (0.02, 0.07, 0.20), 0.45, 0.05, 20.0, 0.05)
simple('ext_bin_green', (0.03, 0.12, 0.04), 0.45, 0.05, 20.0, 0.05)
simple('ext_bin_grey', (0.07, 0.07, 0.075), 0.5, 0.05, 20.0, 0.05)
simple('ext_hydrant', (0.40, 0.03, 0.02), 0.4, 0.1, 10.0, 0.2)
simple('ext_hydrant_cap', (0.62, 0.60, 0.55), 0.4, 0.1, 10.0, 0.2)
simple('ext_sign_white', (0.72, 0.72, 0.70), 0.35)
simple('ext_mailbox', (0.52, 0.52, 0.50), 0.4, 0.04, 20.0, 0.05, Metallic=0.3)
simple('ext_red_band', (0.40, 0.03, 0.03), 0.4)
simple('ext_car_glass', (0.01, 0.012, 0.014), 0.05, **{'Specular IOR Level': 1.0})
simple('ext_chrome', (0.6, 0.6, 0.6), 0.15, Metallic=1.0)
simple('ext_taillight', (0.30, 0.01, 0.01), 0.1, **{'Transmission Weight': 0.3})
simple('ext_headlight', (0.55, 0.55, 0.55), 0.05, Metallic=0.6)
simple('ext_luminaire', (0.72, 0.72, 0.7), 0.15, **{'Transmission Weight': 0.5})
simple('ext_sealant', (0.02, 0.02, 0.019), 0.8, 0.1, 40.0, 0.2, **{'Specular IOR Level': 0.15})
simple('ext_crack', (0.02, 0.02, 0.018), 0.9)
simple('ext_lamp_off', (0.32, 0.30, 0.26), 0.2, **{'Transmission Weight': 0.6})
simple('ext_grate', (0.05, 0.045, 0.04), 0.6, 0.3, 15.0, 0.3, Metallic=0.7)
simple('ext_paint_white', (0.62, 0.62, 0.58), 0.6, 0.3, 3.0, 0.1)
simple('ext_bin_lid', (0.05, 0.05, 0.05), 0.5)
mat_concrete('ext_concrete')
mat_concrete('ext_concrete_old', (0.36, 0.35, 0.33))
mat_concrete('ext_foundation', (0.33, 0.32, 0.30), broom=False)
mat_concrete('ext_pavers', (0.32, 0.29, 0.25), broom=False)
mat_asphalt('ext_asphalt', 0.06)
mat_asphalt('ext_asphalt_patch', 0.055, patch=True)
mat_asphalt('ext_driveway', 0.05, patch=True)
mat_grass('ext_grass')
mat_glass_house('ext_glass')
mat_blinds('ext_blinds')
mat_curtain('ext_curtain')
mat_door('ext_door')
mat_wood('ext_pole', (0.22, 0.19, 0.155))
mat_wood('ext_fence', (0.28, 0.21, 0.15), stripes=0.145)
mat_wood('ext_fence_grey', (0.30, 0.29, 0.27), stripes=0.145)
mat_leaf('ext_leaf_maple', (0.055, 0.085, 0.025), (0.085, 0.12, 0.035), (0.30, 0.20, 0.04))
mat_leaf('ext_leaf_mature', (0.04, 0.06, 0.022), (0.065, 0.085, 0.03), (0.13, 0.12, 0.04))
mat_leaf('ext_leaf_spruce', (0.03, 0.045, 0.035), (0.045, 0.06, 0.05), (0.06, 0.07, 0.06))
mat_leaf('ext_leaf_shrub', (0.035, 0.06, 0.025), (0.06, 0.09, 0.03), (0.09, 0.10, 0.04))
mat_bark('ext_bark')
mat_bark('ext_bark_grey', (0.16, 0.15, 0.14))
mat_paint('ext_carpaint', None, 0.25, coat=1.0, metallic=0.5, objcol=True)
mat_sign('ext_sign_red')


# =====================================================================================  mesh builder
class MB:
    """Accumulates polygons in local coordinates (optionally through a transform stack)."""

    def __init__(self):
        self.v, self.f, self.m, self.s = [], [], [], []
        self.mats = []
        self.T = [Matrix.Identity(4)]

    def mi(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def push(self, M):
        self.T.append(self.T[-1] @ M)

    def pop(self):
        self.T.pop()

    def P(self, p):
        return tuple(self.T[-1] @ V(p))

    def poly(self, pts, mat, smooth=False):
        base = len(self.v)
        self.v.extend(self.P(p) for p in pts)
        self.f.append(list(range(base, base + len(pts))))
        self.m.append(self.mi(mat))
        self.s.append(smooth)

    def raw(self, verts, faces, mat, smooth=False):
        base = len(self.v)
        self.v.extend(self.P(p) for p in verts)
        mi = self.mi(mat)
        for fc in faces:
            self.f.append([base + i for i in fc])
            self.m.append(mi)
            self.s.append(smooth)

    def box(self, mn, mx, mat, skip=()):
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        fs = {'-z': (0, 3, 2, 1), '+z': (4, 5, 6, 7), '-y': (0, 1, 5, 4), '+y': (2, 3, 7, 6), '-x': (3, 0, 4, 7), '+x': (1, 2, 6, 5)}
        self.raw(c, [f for k, f in fs.items() if k not in skip], mat)

    def obox(self, c, ax, ay, az, mat):
        """Oriented box: centre c, half-axis vectors ax, ay, az."""
        c, ax, ay, az = V(c), V(ax), V(ay), V(az)
        pts = [c + sx * ax + sy * ay + sz * az for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
        # order: 0(-,-,-) 1(+,-,-) 2(-,+,-) 3(+,+,-) 4(-,-,+) 5(+,-,+) 6(-,+,+) 7(+,+,+)
        self.raw(pts, [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (3, 2, 6, 7), (2, 0, 4, 6), (1, 3, 7, 5)], mat)

    def beam(self, a, b, w, h, mat, up=(0, 0, 1)):
        a, b = V(a), V(b)
        d = b - a
        L = d.length
        if L < 1e-6:
            return
        dx = d / L
        upv = V(up)
        if abs(dx.dot(upv)) > 0.95:
            upv = V((1, 0, 0))
        side = dx.cross(upv).normalized()
        upn = side.cross(dx).normalized()
        self.obox((a + b) / 2, dx * (L / 2), side * (w / 2), upn * (h / 2), mat)

    def tube(self, pts, radii, n, mat, cap=False, smooth=True):
        """Tube through a polyline with per-point radius (parallel-transported frames)."""
        pts = [V(p) for p in pts]
        rings = []
        prev_n = None
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            if prev_n is None:
                a = V((0, 0, 1)) if abs(t.z) < 0.9 else V((1, 0, 0))
                nrm = t.cross(a).normalized()
            else:
                nrm = (prev_n - t * prev_n.dot(t)).normalized()
            prev_n = nrm
            bn = t.cross(nrm)
            r = radii[i] if isinstance(radii, (list, tuple)) else radii
            rings.append([p + (nrm * math.cos(2 * math.pi * k / n) + bn * math.sin(2 * math.pi * k / n)) * r for k in range(n)])
        verts = [q for ring in rings for q in ring]
        faces = []
        for i in range(len(rings) - 1):
            for k in range(n):
                a, b = i * n + k, i * n + (k + 1) % n
                faces.append((a, b, b + n, a + n))
        if cap:
            faces.append(tuple(range(n - 1, -1, -1)))
            faces.append(tuple(range((len(rings) - 1) * n, len(rings) * n)))
        self.raw(verts, faces, mat, smooth)

    def cyl(self, p0, p1, r0, r1, n, mat, cap=True, smooth=True):
        self.tube([p0, p1], [r0, r1], n, mat, cap, smooth)

    def disc(self, c, nrm, r, n, mat, rot=0.0):
        c, nrm = V(c), V(nrm).normalized()
        a = V((0, 0, 1)) if abs(nrm.z) < 0.9 else V((1, 0, 0))
        u = nrm.cross(a).normalized()
        w = nrm.cross(u)
        pts = [c + (u * math.cos(rot + 2 * math.pi * k / n) + w * math.sin(rot + 2 * math.pi * k / n)) * r for k in range(n)]
        self.poly(pts, mat)

    def build(self, name, loc=(0, 0, 0), rot=0.0, scale=(1, 1, 1), color=None, parent=None, mesh=None):
        if mesh is None:
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(self.v, [], self.f)
            for mn in self.mats:
                mesh.materials.append(MATS[mn])
            mesh.polygons.foreach_set('material_index', self.m)
            mesh.polygons.foreach_set('use_smooth', self.s)
            mesh.validate()
            mesh.update()
        return place(mesh, name, loc, rot, scale, color, parent)


def place(mesh, name, loc=(0, 0, 0), rot=0.0, scale=(1, 1, 1), color=None, parent=None):
    o = bpy.data.objects.new(name, mesh)
    COL.objects.link(o)
    o.parent = parent or ROOT
    o.location = loc
    o.rotation_euler = (0, 0, rot)
    o.scale = scale
    if color is not None:
        o.color = (*color, 1.0)
    return o


def frame(origin, u, v, w):
    """Matrix mapping wall-local (u, v, w) to parent space."""
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = u[i], v[i], w[i], origin[i]
    return M


def wall_frame(side, x0, x1, y0, y1, z0=0.0):
    """Frames for the four walls of a rectangle footprint; u runs left->right seen from outside."""
    if side == 'front':
        return frame((x0, y0, z0), (1, 0, 0), (0, 0, 1), (0, -1, 0)), x1 - x0
    if side == 'back':
        return frame((x1, y1, z0), (-1, 0, 0), (0, 0, 1), (0, 1, 0)), x1 - x0
    if side == 'left':
        return frame((x0, y1, z0), (0, -1, 0), (0, 0, 1), (-1, 0, 0)), y1 - y0
    return frame((x1, y0, z0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), y1 - y0


# =====================================================================================  building parts
def wall(mb, W, H, openings, zones, v0=0.0, band=None):
    """Wall plane w=0 over [0,W]x[v0,H] minus rectangular openings. zones: [(v_top, mat), ...]."""
    us = sorted({0.0, W} | {o[0] for o in openings} | {o[2] for o in openings})
    vs = sorted({v0, H} | {o[1] for o in openings} | {o[3] for o in openings} | {z for z, _ in zones if v0 < z < H})
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            cu, cv = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
            if any(o[0] < cu < o[2] and o[1] < cv < o[3] for o in openings):
                continue
            mat = next(mm for z, mm in zones if cv < z) if any(cv < z for z, _ in zones) else zones[-1][1]
            mw = -0.025 if mat == 'ext_foundation' else 0.0
            mb.poly([(us[i], vs[j], mw), (us[i + 1], vs[j], mw), (us[i + 1], vs[j + 1], mw), (us[i], vs[j + 1], mw)], mat)
    if band is not None:        # frieze / belly band at material transitions
        for z in band:
            mb.box((0.0, z - 0.06, 0.0), (W, z + 0.06, 0.035), 'ext_trim')


def window(mb, u0, v0, u1, v1, brick=False, grille=True, cover=None, shutters=False, deep=0.55, rail=True):
    """Double-hung vinyl window in a wall frame (w outward). Opening u0..u1, v0..v1."""
    R = 0.13 if brick else 0.11
    trim = 'ext_brick' if brick else 'ext_trim'
    # reveal
    mb.poly([(u0, v0, 0), (u0, v1, 0), (u0, v1, -R), (u0, v0, -R)], trim)
    mb.poly([(u1, v0, 0), (u1, v0, -R), (u1, v1, -R), (u1, v1, 0)], trim)
    mb.poly([(u0, v1, 0), (u1, v1, 0), (u1, v1, -R), (u0, v1, -R)], trim)
    mb.poly([(u0, v0, 0), (u0, v0, -R), (u1, v0, -R), (u1, v0, 0)], 'ext_trim')
    # exterior casing / precast sill + soldier header
    if brick:
        mb.box((u0 - 0.06, v0 - 0.09, -0.02), (u1 + 0.06, v0, 0.05), 'ext_stone')
        mb.box((u0 - 0.1, v1, 0.0), (u1 + 0.1, v1 + 0.2, 0.012), 'ext_brick')
    else:
        cw = 0.09
        mb.box((u0 - cw, v0, 0.0), (u0, v1 + cw, 0.03), 'ext_trim')
        mb.box((u1, v0, 0.0), (u1 + cw, v1 + cw, 0.03), 'ext_trim')
        mb.box((u0, v1, 0.0), (u1, v1 + cw, 0.03), 'ext_trim')
        mb.box((u0 - cw - 0.02, v1 + cw, 0.0), (u1 + cw + 0.02, v1 + cw + 0.025, 0.045), 'ext_trim')
        mb.box((u0 - cw - 0.03, v0 - 0.05, -0.01), (u1 + cw + 0.03, v0, 0.05), 'ext_trim')
    if shutters:
        sw = min(0.42, (u1 - u0) * 0.45)
        for a, b in ((u0 - 0.1 - sw, u0 - 0.1), (u1 + 0.1, u1 + 0.1 + sw)):
            mb.box((a, v0, 0.01), (b, v1, 0.04), 'ext_shutter')
    # frame + sashes
    fw, fd = 0.055, -0.06
    mb.box((u0, v0, -R), (u0 + fw, v1, fd), 'ext_trim')
    mb.box((u1 - fw, v0, -R), (u1, v1, fd), 'ext_trim')
    mb.box((u0, v1 - fw, -R), (u1, v1, fd), 'ext_trim')
    mb.box((u0, v0, -R), (u1, v0 + fw, fd), 'ext_trim')
    vm = (v0 + v1) / 2
    if rail:
        mb.box((u0, vm - 0.03, -R + 0.01), (u1, vm + 0.03, fd - 0.005), 'ext_trim')
    gw = -R + 0.035
    mb.poly([(u0, v0, gw), (u1, v0, gw), (u1, v1, gw), (u0, v1, gw)], 'ext_glass')
    if grille and rail:
        for k in (1, 2):
            uu = u0 + (u1 - u0) * k / 3
            mb.box((uu - 0.01, vm + 0.03, gw + 0.002), (uu + 0.01, v1 - fw, gw + 0.014), 'ext_trim')
        vv = (vm + v1) / 2
        mb.box((u0 + fw, vv - 0.01, gw + 0.002), (u1 - fw, vv + 0.01, gw + 0.014), 'ext_trim')
    # what's behind the glass
    bw = gw - 0.04
    kind, amt = cover if cover else ('blinds', 0.5)
    if kind == 'blinds':
        vb = v1 - (v1 - v0) * amt
        mb.poly([(u0, vb, bw), (u1, vb, bw), (u1, v1, bw), (u0, v1, bw)], 'ext_blinds')
        mb.box((u0, vb - 0.02, bw - 0.01), (u1, vb, bw + 0.01), 'ext_blinds')
    elif kind == 'curtain':
        for a, b, fl in ((u0, u0 + (u1 - u0) * amt, 1), (u1 - (u1 - u0) * amt, u1, -1)):
            n = 8
            pts_top = [(a + (b - a) * k / n, v1, bw - 0.03 * (k % 2)) for k in range(n + 1)]
            for k in range(n):
                pa, pb = pts_top[k], pts_top[k + 1]
                mb.poly([(pa[0], v0 + 0.02, pa[2]), (pb[0], v0 + 0.02, pb[2]), (pb[0], v1, pb[2]), (pa[0], v1, pa[2])], 'ext_curtain')
    # dark interior box
    D = gw - deep
    mb.poly([(u0, v0, D), (u1, v0, D), (u1, v1, D), (u0, v1, D)], 'ext_interior')
    mb.poly([(u0, v0, gw), (u0, v0, D), (u0, v1, D), (u0, v1, gw)], 'ext_interior')
    mb.poly([(u1, v0, gw), (u1, v1, gw), (u1, v1, D), (u1, v0, D)], 'ext_interior')
    mb.poly([(u0, v1, gw), (u0, v1, D), (u1, v1, D), (u1, v1, gw)], 'ext_interior')
    mb.poly([(u0, v0, gw), (u1, v0, gw), (u1, v0, D), (u0, v0, D)], 'ext_interior')


def door(mb, u0, v0, u1, v1, sidelight=0.0, brick=False):
    """Insulated steel entry door with raised panels (+ optional sidelight)."""
    R = 0.14
    trim = 'ext_brick' if brick else 'ext_trim'
    ut = u1 + sidelight
    for a in ((u0, v0, u0, v1), (ut, v0, ut, v1)):
        pass
    mb.poly([(u0, v0, 0), (u0, v1, 0), (u0, v1, -R), (u0, v0, -R)], trim)
    mb.poly([(ut, v0, 0), (ut, v0, -R), (ut, v1, -R), (ut, v1, 0)], trim)
    mb.poly([(u0, v1, 0), (ut, v1, 0), (ut, v1, -R), (u0, v1, -R)], trim)
    if not brick:
        cw = 0.1
        mb.box((u0 - cw, v0, 0), (u0, v1 + cw, 0.03), 'ext_trim')
        mb.box((ut, v0, 0), (ut + cw, v1 + cw, 0.03), 'ext_trim')
        mb.box((u0, v1, 0), (ut, v1 + cw, 0.03), 'ext_trim')
    else:
        mb.box((u0 - 0.1, v1, 0.0), (ut + 0.1, v1 + 0.2, 0.012), 'ext_brick')
    fw = 0.05
    mb.box((u0, v0, -R), (u0 + fw, v1, -R + 0.07), 'ext_trim')
    mb.box((ut - fw, v0, -R), (ut, v1, -R + 0.07), 'ext_trim')
    mb.box((u0, v1 - fw, -R), (ut, v1, -R + 0.07), 'ext_trim')
    dw = -R + 0.03
    d0, d1 = u0 + fw, u1 - fw * 0.5
    mb.poly([(d0, v0, dw), (d1, v0, dw), (d1, v1 - fw, dw), (d0, v1 - fw, dw)], 'ext_door')
    pw = (d1 - d0 - 0.24) / 2
    for i in range(2):
        a = d0 + 0.08 + i * (pw + 0.08)
        mb.box((a, v0 + 0.15, dw), (a + pw, v0 + 0.95, dw + 0.012), 'ext_door')
        mb.box((a, v0 + 1.1, dw), (a + pw, v1 - fw - 0.12, dw + 0.012), 'ext_door')
    mb.box((d1 - 0.12, v0 + 0.98, dw), (d1 - 0.07, v0 + 1.06, dw + 0.07), 'ext_metal')
    if sidelight > 0:
        s0 = u1 + fw * 0.5
        mb.box((u1 - fw * 0.5, v0, -R), (u1 + fw * 0.5, v1, -R + 0.07), 'ext_trim')
        mb.poly([(s0, v0 + 0.25, dw), (ut - fw, v0 + 0.25, dw), (ut - fw, v1 - fw, dw), (s0, v1 - fw, dw)], 'ext_glass')
        mb.poly([(s0, v0, dw), (ut - fw, v0, dw), (ut - fw, v0 + 0.25, dw), (s0, v0 + 0.25, dw)], 'ext_door')
        mb.poly([(s0, v0, dw - 0.3), (ut - fw, v0, dw - 0.3), (ut - fw, v1, dw - 0.3), (s0, v1, dw - 0.3)], 'ext_curtain')
    # coach light
    mb.box((u0 - 0.33, v0 + 1.55, 0.02), (u0 - 0.19, v0 + 1.9, 0.14), 'ext_lamp_off')
    mb.box((u0 - 0.35, v0 + 1.88, 0.02), (u0 - 0.17, v0 + 1.93, 0.16), 'ext_shutter')


def garage_door(mb, u0, u1, H=2.13, windows=False):
    """Sectional steel door, 4 sections of raised panels, in a 0.1 m recess with trim."""
    R = 0.1
    mb.poly([(u0, 0, 0), (u0, H, 0), (u0, H, -R), (u0, 0, -R)], 'ext_trim')
    mb.poly([(u1, 0, 0), (u1, 0, -R), (u1, H, -R), (u1, H, 0)], 'ext_trim')
    mb.poly([(u0, H, 0), (u1, H, 0), (u1, H, -R), (u0, H, -R)], 'ext_trim')
    cw = 0.1
    mb.box((u0 - cw, 0, 0), (u0, H + cw, 0.03), 'ext_trim')
    mb.box((u1, 0, 0), (u1 + cw, H + cw, 0.03), 'ext_trim')
    mb.box((u0, H, 0), (u1, H + cw, 0.03), 'ext_trim')
    W = u1 - u0
    npan = max(4, int(round(W / 0.62)))
    sh = H / 4
    for s in range(4):
        z0 = s * sh
        mb.box((u0, z0 + 0.006, -R), (u1, z0 + sh - 0.006, -R + 0.03), 'ext_trim')
        mb.box((u0, z0 + sh - 0.012, -R - 0.005), (u1, z0 + sh + 0.0, -R + 0.022), 'ext_dark')
        pw = (W - 0.12) / npan
        for k in range(npan):
            a = u0 + 0.06 + k * pw + 0.05
            b = a + pw - 0.1
            if windows and s == 3:
                mb.poly([(a, z0 + 0.12, -R + 0.035), (b, z0 + 0.12, -R + 0.035), (b, z0 + sh - 0.12, -R + 0.035),
                         (a, z0 + sh - 0.12, -R + 0.035)], 'ext_car_glass')
            else:
                mb.box((a, z0 + 0.1, -R + 0.03), (b, z0 + sh - 0.1, -R + 0.042), 'ext_trim')


def roof_hip(mb, x0, x1, y0, y1, h, s=0.5, o=0.45, gutters=True, spouts=()):
    X0, X1, Y0, Y1 = x0 - o, x1 + o, y0 - o, y1 + o
    ze = h + 0.2 - o * s
    W, D = X1 - X0, Y1 - Y0
    xc, yc = (X0 + X1) / 2, (Y0 + Y1) / 2
    if W <= D:
        half = W / 2
        rz = ze + half * s
        r0, r1 = (xc, Y0 + half, rz), (xc, Y1 - half, rz)
        mb.poly([(X0, Y0, ze), (X1, Y0, ze), r0], 'ext_shingle')
        mb.poly([(X1, Y1, ze), (X0, Y1, ze), r1], 'ext_shingle')
        mb.poly([(X1, Y0, ze), (X1, Y1, ze), r1, r0], 'ext_shingle')
        mb.poly([(X0, Y1, ze), (X0, Y0, ze), r0, r1], 'ext_shingle')
    else:
        half = D / 2
        rz = ze + half * s
        r0, r1 = (X0 + half, yc, rz), (X1 - half, yc, rz)
        mb.poly([(X0, Y1, ze), (X0, Y0, ze), r0], 'ext_shingle')
        mb.poly([(X1, Y0, ze), (X1, Y1, ze), r1], 'ext_shingle')
        mb.poly([(X0, Y0, ze), (X1, Y0, ze), r1, r0], 'ext_shingle')
        mb.poly([(X1, Y1, ze), (X0, Y1, ze), r0, r1], 'ext_shingle')
    cap(mb, r0, r1)
    for c, r in (((X0, Y0, ze), r0), ((X1, Y0, ze), r1 if W > D else r0), ((X1, Y1, ze), r1), ((X0, Y1, ze), r0 if W > D else r1)):
        cap(mb, c, r)
    eave_ring(mb, [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)], [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], ze, gutters, (0, 1, 2, 3))
    for sp in spouts:
        downspout(mb, sp, x0, x1, y0, y1, o, ze)
    return rz


def cap(mb, a, b, w=0.13, t=0.035):
    a, b = V(a), V(b)
    d = (b - a)
    if d.length < 1e-4:
        return
    d.normalize()
    side = d.cross(V((0, 0, 1)))
    if side.length < 1e-4:
        side = V((1, 0, 0))
    side.normalize()
    up = V((0, 0, t))
    mb.poly([a - side * w, b - side * w, b + up, a + up], 'ext_shingle')
    mb.poly([a + up, b + up, b + side * w, a + side * w], 'ext_shingle')


def eave_ring(mb, outer, inner, ze, gutters, gut_edges, closed=True):
    """Fascia + soffit (+ K-style gutters) along the eave polygon."""
    n = len(outer)
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        a, b = outer[i], outer[(i + 1) % n]
        ia, ib = inner[i], inner[(i + 1) % n]
        mb.poly([(a[0], a[1], ze - 0.2), (b[0], b[1], ze - 0.2), (b[0], b[1], ze), (a[0], a[1], ze)], 'ext_trim')
        mb.poly([(a[0], a[1], ze - 0.2), (ia[0], ia[1], ze - 0.2), (ib[0], ib[1], ze - 0.2), (b[0], b[1], ze - 0.2)], 'ext_soffit')
        if gutters and i in gut_edges:
            A, B = V((a[0], a[1], 0)), V((b[0], b[1], 0))
            d = (B - A).normalized()
            out = d.cross(V((0, 0, 1)))       # outward for a CCW-from-above ring
            A2, B2 = A - d * 0.04, B + d * 0.04
            gw = 0.13
            p = [A2, B2, B2 + out * gw, A2 + out * gw]
            zt, zb = ze - 0.03, ze - 0.15
            mb.poly([(q.x, q.y, zt) for q in p], 'ext_dark')
            mb.poly([(p[3].x, p[3].y, zb), (p[2].x, p[2].y, zb), (p[1].x, p[1].y, zb), (p[0].x, p[0].y, zb)], 'ext_trim')
            mb.poly([(p[3].x, p[3].y, zb), (p[3].x, p[3].y, zt + 0.01), (p[2].x, p[2].y, zt + 0.01), (p[2].x, p[2].y, zb)], 'ext_trim')
            mb.poly([(p[0].x, p[0].y, zb), (p[1].x, p[1].y, zb), (p[1].x, p[1].y, zt), (p[0].x, p[0].y, zt)], 'ext_trim')
            for q0, q1 in ((p[0], p[3]), (p[1], p[2])):
                mb.poly([(q0.x, q0.y, zb), (q1.x, q1.y, zb), (q1.x, q1.y, zt), (q0.x, q0.y, zt)], 'ext_trim')


def downspout(mb, corner, x0, x1, y0, y1, o, ze):
    """corner: (cx, cy) wall corner the downspout runs down; gutter is o+0.065 outside it."""
    cx, cy = corner
    sx = -1 if abs(cx - x0) < 1e-3 else 1
    sy = -1 if abs(cy - y0) < 1e-3 else 1
    gx, gy = cx + sx * 0.25, cy + sy * (o + 0.065)
    wx, wy = gx, cy + sy * 0.05
    zt = ze - 0.15
    mb.beam((gx, gy, zt), (gx, (gy + wy) / 2, zt - 0.25), 0.075, 0.055, 'ext_trim')
    mb.beam((gx, (gy + wy) / 2, zt - 0.25), (wx, wy, zt - 0.5), 0.075, 0.055, 'ext_trim')
    mb.box((wx - 0.0375, wy - 0.03, 0.3), (wx + 0.0375, wy + 0.03, zt - 0.5), 'ext_trim')
    mb.beam((wx, wy, 0.33), (wx, wy + sy * 0.3, 0.12), 0.075, 0.055, 'ext_trim')
    mb.box((wx - 0.15, wy + sy * 0.1 - 0.3 * (sy < 0), -0.02), (wx + 0.15, wy + sy * 0.1 + 0.3 * (sy > 0), 0.05), 'ext_concrete')


def roof_gable(mb, x0, x1, y0, y1, h, s=0.5, o=0.4, orake=0.3, gutters=True, gable_mat='ext_siding', vent=True,
               ends=(True, True)):
    """Ridge along x. Eaves at y0 / y1, gable walls at x0 / x1 (siding triangles)."""
    X0, X1, Y0, Y1 = x0 - orake, x1 + orake, y0 - o, y1 + o
    ze = h + 0.2 - o * s
    yc = (y0 + y1) / 2
    rz = ze + (yc - Y0) * s
    mb.poly([(X0, Y0, ze), (X1, Y0, ze), (X1, yc, rz), (X0, yc, rz)], 'ext_shingle')
    mb.poly([(X1, Y1, ze), (X0, Y1, ze), (X0, yc, rz), (X1, yc, rz)], 'ext_shingle')
    cap(mb, (X0, yc, rz), (X1, yc, rz))
    # gable triangles + rakes
    zw = h
    for x, sgn, on in ((x0, -1, ends[0]), (x1, 1, ends[1])):
        if not on:
            continue
        top = rz - 0.2
        if sgn < 0:
            mb.poly([(x, y1, zw), (x, y0, zw), (x, yc, top)], gable_mat)
        else:
            mb.poly([(x, y0, zw), (x, y1, zw), (x, yc, top)], gable_mat)
        if vent:
            vh = (top - zw) * 0.35
            mb.box((x + sgn * 0.0 - 0.03 * (sgn < 0), yc - 0.25, zw + (top - zw) * 0.3), (x + 0.03 * (sgn > 0), yc + 0.25, zw + (top - zw) * 0.3 + vh), 'ext_trim')
        X = X0 if sgn < 0 else X1
        for (ya, za), (yb, zb) in (((Y0, ze), (yc, rz)), ((yc, rz), (Y1, ze))):
            mb.poly([(X, ya, za - 0.22), (X, yb, zb - 0.22), (X, yb, zb + 0.01), (X, ya, za + 0.01)], 'ext_trim')
            mb.poly([(X, ya, za - 0.22), (x, ya, za - 0.22), (x, yb, zb - 0.22), (X, yb, zb - 0.22)], 'ext_soffit')
    eave_ring(mb, [(X0, Y0), (X1, Y0)], [(x0, y0), (x1, y0)], ze, gutters, (0,), closed=False)
    eave_ring(mb, [(X1, Y1), (X0, Y1)], [(x1, y1), (x0, y1)], ze, gutters, (0,), closed=False)
    return rz


def rot_z90(cx, cy):
    """Rotate +90 deg about (cx, cy): maps x-ridge builders to y-ridge ones."""
    return Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z') @ Matrix.Translation((-cx, -cy, 0))


def block_walls(mb, x0, x1, y0, y1, H, zones, openings, band=None, skip=()):
    """Four walls of a block. openings: dict side -> list of (kind, u0, v0, u1, v1, kwargs)."""
    for side in ('front', 'back', 'left', 'right'):
        if side in skip:
            continue
        M, W = wall_frame(side, x0, x1, y0, y1)
        ops = openings.get(side, [])
        mb.push(M)
        holes = [(a, b, c, d) for k, a, b, c, d, kw in ops if k != 'garage'] + \
                [(a, 0.0, c, d) for k, a, b, c, d, kw in ops if k == 'garage']
        holes2 = []
        for k, a, b, c, d, kw in ops:
            if k == 'door' and kw.get('sidelight'):
                holes2.append((a, b, c + kw['sidelight'], d))
            elif k == 'garage':
                holes2.append((a, 0.0, c, d))
            else:
                holes2.append((a, b, c, d))
        wall(mb, W, H, holes2, zones, 0.0, band)
        for k, a, b, c, d, kw in ops:
            if k == 'win':
                window(mb, a, b, c, d, **kw)
            elif k == 'door':
                door(mb, a, b, c, d, **kw)
            elif k == 'garage':
                garage_door(mb, a, c, d, **kw)
        # corner boards
        if not any(z[1] == 'ext_brick' for z in zones[1:]) or True:
            mb.box((-0.02, 0.35, -0.0), (0.1, H, 0.04), 'ext_trim' if zones[-1][1] != 'ext_brick' else 'ext_brick')
            mb.box((W - 0.1, 0.35, 0.0), (W + 0.02, H, 0.04), 'ext_trim' if zones[-1][1] != 'ext_brick' else 'ext_brick')
        mb.pop()


def steps(mb, x0, x1, y_front, n, rise=0.18, run=0.28, landing=1.3, mat='ext_concrete'):
    """Porch landing against the wall at y_front plus n steps down toward -y."""
    top = n * rise
    mb.box((x0, y_front - landing, -0.3), (x1, y_front, top), mat)
    for i in range(n):
        z = top - (i + 1) * rise
        ya = y_front - landing - (i + 1) * run
        mb.box((x0 + 0.1, ya, -0.3), (x1 - 0.1, ya + run + 0.02, z + rise - rise), mat) if False else \
            mb.box((x0 + 0.1, ya, -0.3), (x1 - 0.1, y_front - landing, z), mat)
    # railing
    for x in (x0 + 0.05, x1 - 0.05):
        yb = y_front - landing - n * run
        mb.beam((x, yb + 0.05, 0.95), (x, y_front - landing, top + 0.9), 0.04, 0.05, 'ext_shutter')
        mb.beam((x, y_front - landing, top + 0.9), (x, y_front - 0.1, top + 0.9), 0.04, 0.05, 'ext_shutter')
        mb.box((x - 0.02, yb + 0.03, 0.0), (x + 0.02, yb + 0.07, 0.97), 'ext_shutter')
        mb.box((x - 0.02, y_front - landing - 0.02, top), (x + 0.02, y_front - landing + 0.02, top + 0.92), 'ext_shutter')
    return top


def shrub_row(mb_list, x0, x1, y, z=0.0):
    pass


# ------------------------------------------------------------------- house types (front at y=0 facing -y)
def house_A():
    """Two-storey hip roof, vinyl siding all round, forward front-gable double garage on the right."""
    mb = MB()
    Hm = 5.95
    zones = [(0.45, 'ext_foundation'), (99, 'ext_siding')]
    x0, x1, y0, y1 = 0.0, 7.4, 0.0, 10.5
    fl1, fl2 = 1.25, 4.0
    ops = {
        'front': [('win', 0.9, fl1, 3.1, fl1 + 1.5, dict(cover=('curtain', 0.3), grille=True)),
                  ('door', 4.9, 0.72, 5.85, 2.8, dict(sidelight=0.36)),
                  ('win', 0.95, fl2, 2.05, fl2 + 1.35, dict(cover=('blinds', 0.45))),
                  ('win', 2.75, fl2, 3.85, fl2 + 1.35, dict(cover=('blinds', 0.8))),
                  ('win', 5.0, fl2 + 0.3, 6.1, fl2 + 1.35, dict(cover=('blinds', 0.3), rail=False))],
        'left': [('win', 3.0, fl1, 4.0, fl1 + 1.2, dict(grille=False, cover=('blinds', 1.0))),
                 ('win', 6.5, fl2, 7.5, fl2 + 1.2, dict(grille=False, cover=('blinds', 0.6)))],
        'right': [('win', 7.2, fl2, 8.2, fl2 + 1.2, dict(grille=False, cover=('curtain', 0.35)))],
        'back': [('win', 1.0, fl1 - 0.4, 3.4, fl1 + 1.6, dict(grille=False, rail=False, cover=('blinds', 0.2))),
                 ('win', 4.5, fl1, 5.6, fl1 + 1.2, dict(grille=False)),
                 ('win', 1.2, fl2, 2.3, fl2 + 1.3, dict(grille=False)),
                 ('win', 4.8, fl2, 5.9, fl2 + 1.3, dict(grille=False, cover=('curtain', 0.4)))],
    }
    block_walls(mb, x0, x1, y0, y1, Hm, zones, ops, band=[3.05])
    roof_hip(mb, x0, x1, y0, y1, Hm, 0.5, 0.45, spouts=[(x0, y0), (x0, y1)])
    # garage: x 7.4..12.9, y -1.6..6.0, front gable
    gx0, gx1, gy0, gy1 = 7.4, 12.9, -1.6, 6.0
    Hg = 2.95
    gops = {'front': [('garage', 0.3, 0.0, 5.2, 2.13, dict(windows=True))],
            'right': [('win', 3.0, 1.2, 4.0, 2.2, dict(grille=False, rail=False, cover=('blinds', 0.2)))]}
    block_walls(mb, gx0, gx1, gy0, gy1, Hg, [(0.2, 'ext_foundation'), (99, 'ext_siding')], gops, skip=('left', 'back'))
    mb.push(rot_z90((gx0 + gx1) / 2, (gy0 + gy1) / 2))
    cx, cy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
    hw, hd = (gx1 - gx0) / 2, (gy1 - gy0) / 2
    roof_gable(mb, cx - hd, cx + hd, cy - hw, cy + hw, Hg, 0.6, 0.35, 0.35, ends=(True, False))
    mb.pop()
    # porch roof + columns over the door (shed roof tied into the wall)
    px0, px1 = 4.4, 7.4
    mb.box((px0, -1.7, -0.3), (px1, 0.0, 0.54), 'ext_concrete')
    for i in range(3):
        mb.box((px0 + 0.8, -1.7 - (i + 1) * 0.28, -0.3), (px1 - 0.6, -1.7 - i * 0.28, 0.54 - (i + 1) * 0.18), 'ext_concrete')
    mb.box((px0 + 0.02, -1.62, 0.54), (px0 + 0.2, -1.44, 2.95), 'ext_trim')
    ze = 3.35
    mb.poly([(px0 - 0.2, -2.0, ze), (px1, -2.0, ze), (px1, 0.0, ze + 0.6), (px0 - 0.2, 0.0, ze + 0.6)], 'ext_shingle')
    mb.box((px0 - 0.2, -2.0, ze - 0.4), (px1, -1.8, ze), 'ext_trim')
    mb.box((px0 - 0.2, -2.0, ze - 0.4), (px0, 0.0, ze + 0.05), 'ext_trim')
    mb.poly([(px0 - 0.2, -1.8, ze - 0.4), (px1, -1.8, ze - 0.4), (px1, 0.0, ze - 0.4), (px0 - 0.2, 0.0, ze - 0.4)], 'ext_soffit')
    # meters on the side wall, AC unit in the side yard
    mb.box((7.3, 7.2, 1.3), (7.5, 7.5, 1.7), 'ext_metal')
    mb.box((7.45, 8.0, 0.0), (8.2, 8.75, 0.75), 'ext_galv')
    mb.box((12.9, 2.0, 1.0), (12.95, 2.3, 1.2), 'ext_metal')
    # garden bed + walkway
    mb.box((0.0, -1.6, -0.02), (4.3, 0.0, 0.07), 'ext_mulch')
    mb.box((px0 + 0.8, -6.0, -0.02), (px1 - 0.6, -2.55, 0.03), 'ext_pavers')
    return mb


def house_B():
    """Side-gable two-storey, brick ground floor + siding above, shutters, porch across the entry,
    double garage (lower side-gable) on the left, flush with the front."""
    mb = MB()
    Hm = 5.9
    x0, x1, y0, y1 = 0.0, 8.8, 0.0, 10.0
    fl1, fl2 = 1.2, 4.0
    zones = [(0.4, 'ext_foundation'), (3.15, 'ext_brick'), (99, 'ext_siding')]
    ops = {
        'front': [('win', 0.8, fl1, 2.0, fl1 + 1.5, dict(brick=True, shutters=True, cover=('blinds', 0.55))),
                  ('win', 2.8, fl1, 4.0, fl1 + 1.5, dict(brick=True, shutters=True, cover=('blinds', 0.55))),
                  ('door', 5.6, 0.62, 6.55, 2.75, dict(sidelight=0.36, brick=True)),
                  ('win', 0.8, fl2, 1.9, fl2 + 1.3, dict(shutters=True, cover=('curtain', 0.25))),
                  ('win', 3.9, fl2, 5.0, fl2 + 1.3, dict(shutters=True, cover=('blinds', 0.9))),
                  ('win', 6.9, fl2, 8.0, fl2 + 1.3, dict(shutters=True, cover=('blinds', 0.4)))],
        'right': [('win', 2.0, fl1, 3.0, fl1 + 1.2, dict(brick=True, grille=False)),
                  ('win', 6.0, fl2, 7.0, fl2 + 1.2, dict(grille=False, cover=('blinds', 0.7)))],
        'back': [('win', 1.0, fl1 - 0.45, 3.4, fl1 + 1.6, dict(brick=True, rail=False, grille=False, cover=('curtain', 0.2))),
                 ('win', 5.2, fl1, 6.4, fl1 + 1.2, dict(brick=True, grille=False)),
                 ('win', 1.2, fl2, 2.3, fl2 + 1.3, dict(grille=False)),
                 ('win', 5.6, fl2, 6.7, fl2 + 1.3, dict(grille=False, cover=('blinds', 0.5)))],
        'left': [('win', 7.0, fl2, 8.0, fl2 + 1.2, dict(grille=False))],
    }
    block_walls(mb, x0, x1, y0, y1, Hm, zones, ops, band=[3.15])
    roof_gable(mb, x0, x1, y0, y1, Hm, 0.5, 0.42, 0.3)
    # garage left: x -5.7..0, y 0..6.6, lower side gable
    gx0, gx1, gy0, gy1 = -5.7, 0.0, 0.0, 6.6
    Hg = 2.9
    gops = {'front': [('garage', 0.35, 0.0, 5.25, 2.13, dict())],
            'left': [('door', 3.6, 0.1, 4.45, 2.1, dict())]}
    block_walls(mb, gx0, gx1, gy0, gy1, Hg, [(0.2, 'ext_foundation'), (99, 'ext_brick')], gops, skip=('right', 'back'))
    roof_gable(mb, gx0, gx1 + 0.05, gy0, gy1, Hg, 0.5, 0.4, 0.3, ends=(True, False), gable_mat='ext_siding')
    # porch: slab, 2 steps, 3 columns, shed roof
    mb.box((4.8, -1.8, -0.3), (8.4, 0.0, 0.4), 'ext_concrete')
    for i in range(2):
        mb.box((5.2, -1.8 - (i + 1) * 0.3, -0.3), (8.0, -1.8 - i * 0.3, 0.4 - (i + 1) * 0.18), 'ext_concrete')
    for x in (4.9, 8.2):
        mb.box((x, -1.7, 0.4), (x + 0.16, -1.54, 3.0), 'ext_trim')
        mb.box((x - 0.03, -1.73, 0.4), (x + 0.19, -1.51, 0.6), 'ext_trim')
    ze = 3.3
    mb.poly([(4.6, -2.05, ze), (8.7, -2.05, ze), (8.7, 0.0, ze + 0.7), (4.6, 0.0, ze + 0.7)], 'ext_shingle')
    mb.box((4.6, -2.05, ze - 0.35), (8.7, -1.85, ze), 'ext_trim')
    mb.poly([(4.6, -1.85, ze - 0.35), (8.7, -1.85, ze - 0.35), (8.7, 0.0, ze - 0.35), (4.6, 0.0, ze - 0.35)], 'ext_soffit')
    for x in (4.6, 8.7):
        mb.poly([(x, -2.05, ze - 0.35), (x, 0.0, ze - 0.35), (x, 0.0, ze + 0.7), (x, -2.05, ze)], 'ext_trim')
    mb.box((0.0, -1.2, -0.02), (4.7, 0.0, 0.07), 'ext_mulch')
    mb.box((5.6, -6.5, -0.02), (7.6, -2.4, 0.03), 'ext_concrete')
    mb.box((x1 - 0.1, 6.0, 0.0), (x1 + 0.65, 6.75, 0.75), 'ext_galv')
    mb.box((x1, 3.2, 1.2), (x1 + 0.2, 3.5, 1.6), 'ext_metal')
    return mb


def house_C():
    """Brick two-storey hip with a projecting front-gable bay; hip-roof garage on the right."""
    mb = MB()
    Hm = 5.9
    x0, x1, y0, y1 = 0.0, 7.2, 0.0, 10.8
    fl1, fl2 = 1.25, 4.0
    zones = [(0.4, 'ext_foundation'), (99, 'ext_brick')]
    ops = {
        'front': [('door', 4.35, 0.62, 5.3, 2.8, dict(brick=True, sidelight=0.0)),
                  ('win', 5.55, fl2, 6.65, fl2 + 1.3, dict(brick=True, cover=('blinds', 0.6)))],
        'left': [('win', 4.0, fl1, 5.0, fl1 + 1.2, dict(brick=True, grille=False))],
        'right': [('win', 8.0, fl2, 9.0, fl2 + 1.2, dict(brick=True, grille=False, cover=('blinds', 1.0)))],
        'back': [('win', 1.0, fl1 - 0.45, 3.4, fl1 + 1.6, dict(brick=True, rail=False, grille=False)),
                 ('win', 4.6, fl1, 5.7, fl1 + 1.2, dict(brick=True, grille=False, cover=('blinds', 0.3))),
                 ('win', 1.3, fl2, 2.4, fl2 + 1.3, dict(brick=True, grille=False)),
                 ('win', 4.6, fl2, 5.7, fl2 + 1.3, dict(brick=True, grille=False, cover=('curtain', 0.3)))]}
    block_walls(mb, x0, x1, y0, y1, Hm, zones, ops)
    roof_hip(mb, x0, x1, y0, y1, Hm, 0.5, 0.45, spouts=[(x0, y1)])
    # projecting bay x 0.3..3.9, y -0.9..0 with bay windows, its own front gable
    bx0, bx1, by0, by1 = 0.3, 3.9, -0.9, 0.0
    bops = {'front': [('win', 0.6, fl1, 3.0, fl1 + 1.55, dict(brick=True, cover=('curtain', 0.28))),
                      ('win', 0.9, fl2, 2.7, fl2 + 1.35, dict(brick=True, cover=('blinds', 0.5)))]}
    block_walls(mb, bx0, bx1, by0, by1, Hm, zones, bops, skip=('back',))
    mb.push(rot_z90((bx0 + bx1) / 2, (by0 + by1) / 2 - 0.9))
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2 - 0.9
    hw, hd = (bx1 - bx0) / 2, 1.8 / 2 + 0.9
    rz = roof_gable(mb, cx - hd, cx + hd, cy - hw, cy + hw, Hm, 0.75, 0.3, 0.3, gable_mat='ext_siding',
                    ends=(True, False), vent=False, gutters=False)
    mb.pop()
    # round-top louvre vent in the gable
    mb.box((1.85, -0.93, Hm + 0.55), (2.35, -0.9, Hm + 1.2), 'ext_trim')
    # garage x 7.2..12.8, y -1.0..6.4 hip roof
    gx0, gx1, gy0, gy1 = 7.2, 12.8, -1.0, 6.4
    Hg = 3.0
    gops = {'front': [('garage', 0.35, 0.0, 5.25, 2.13, dict())]}
    block_walls(mb, gx0, gx1, gy0, gy1, Hg, [(0.2, 'ext_foundation'), (99, 'ext_brick')], gops, skip=('left', 'back'))
    roof_hip(mb, gx0, gx1, gy0, gy1, Hg, 0.45, 0.4, spouts=[(gx1, gy0)])
    # entry: recessed stoop + steps + small portico
    mb.box((4.0, -1.5, -0.3), (5.7, 0.0, 0.54), 'ext_concrete')
    for i in range(3):
        mb.box((4.1, -1.5 - (i + 1) * 0.28, -0.3), (5.6, -1.5 - i * 0.28, 0.54 - (i + 1) * 0.18), 'ext_concrete')
    ze = 3.2
    mb.push(rot_z90(4.85, -0.8))
    roof_gable(mb, 4.85 - 0.8, 4.85 + 0.8, -0.8 - 0.85, -0.8 + 0.85, ze, 0.7, 0.2, 0.25, gable_mat='ext_trim',
               ends=(True, False), vent=False, gutters=False)
    mb.pop()
    for x in (4.05, 5.5):
        mb.box((x, -1.5, 0.54), (x + 0.15, -1.35, 3.2), 'ext_trim')
    mb.box((0.0, -2.0, -0.02), (4.0, -0.9, 0.07), 'ext_mulch')
    mb.box((4.4, -6.5, -0.02), (5.3, -2.35, 0.03), 'ext_pavers')
    mb.box((12.75, 3.0, 1.2), (12.95, 3.3, 1.6), 'ext_metal')
    return mb


def house_lod(seed):
    """Low-detail house for the rows behind (both faces carry windows: fronts and backs are seen)."""
    r = random.Random(seed)
    mb = MB()
    W = r.choice((7.0, 7.6, 8.2, 8.8))
    D = r.choice((9.5, 10.5, 11.0))
    H = r.choice((5.6, 5.9, 5.9, 3.0))          # some bungalows
    brick_front = r.random() < 0.45
    zones = [(0.4, 'ext_foundation'), (3.1 if H > 4 else 99, 'ext_brick' if brick_front else 'ext_siding'), (99, 'ext_siding')]
    for side in ('front', 'back', 'left', 'right'):
        M, Wd = wall_frame(side, 0, W, 0, D)
        mb.push(M)
        holes = []
        if side in ('front', 'back'):
            floors = (1.2, 4.0) if H > 4 else (1.1,)
            for fz in floors:
                n = 3 if W > 7.5 else 2
                for k in range(n):
                    a = 0.9 + k * (Wd - 1.8) / n + 0.2
                    holes.append((a, fz, a + 1.1, fz + 1.3))
        wall(mb, Wd, H, [], zones if side == 'front' else [(0.4, 'ext_foundation'), (99, 'ext_siding')])
        for a, b, c, d in holes:
            mb.box((a - 0.08, b - 0.08, 0.0), (c + 0.08, d + 0.08, 0.025), 'ext_trim')
            mb.poly([(a, b, 0.03), (c, b, 0.03), (c, d, 0.03), (a, d, 0.03)], 'ext_car_glass')
            if r.random() < 0.6:
                f = r.uniform(0.2, 0.8)
                mb.poly([(a, d - (d - b) * f, 0.032), (c, d - (d - b) * f, 0.032), (c, d, 0.032), (a, d, 0.032)], 'ext_blinds')
        if side == 'front':
            mb.box((W - 2.3, 0.6, 0.0), (W - 1.4, 2.7, 0.03), 'ext_door')
        mb.pop()
    if r.random() < 0.5 or H < 4:
        roof_hip(mb, 0, W, 0, D, H, 0.5, 0.4, gutters=True)
    else:
        roof_gable(mb, 0, W, 0, D, H, 0.5, 0.4, 0.3, vent=False)
    # garage wing
    gw = r.choice((3.8, 5.6))
    mb.push(Matrix.Translation((W, -r.choice((0.0, 1.0)), 0)))
    for side in ('front', 'right'):
        M, Wd = wall_frame(side, 0, gw, 0, 6.5)
        mb.push(M)
        wall(mb, Wd, 2.9, [], [(0.2, 'ext_foundation'), (99, 'ext_siding')])
        if side == 'front':
            mb.box((0.3, 0.0, 0.0), (gw - 0.3, 2.13, 0.03), 'ext_trim')
            for s in range(1, 4):
                mb.box((0.3, s * 0.53 - 0.01, 0.03), (gw - 0.3, s * 0.53 + 0.01, 0.035), 'ext_dark')
        mb.pop()
    roof_hip(mb, 0, gw, 0, 6.5, 2.9, 0.45, 0.35, gutters=False)
    mb.pop()
    return mb, W + gw


# =====================================================================================  vegetation
def leaf_shape(k):
    """Unit outline in the leaf plane: k='maple' five-lobed, 'clump' irregular rosette."""
    if k == 'maple':
        rs = [1.0, 0.5, 0.8, 0.3, 0.45, 0.3, 0.8, 0.5]
        return [(r * math.sin(2 * math.pi * i / len(rs)), r * math.cos(2 * math.pi * i / len(rs))) for i, r in enumerate(rs)]
    return None


def tree(seed, H, crown_r, crown_z0, trunk_r, n_leaf, leaf_sz, leaf_mat, bark='ext_bark', depth=3,
         shape='maple', squash=1.0, spread=0.55):
    r = random.Random(seed)
    mb = MB()
    tips = []

    def grow(p, d, L, rad, lvl):
        segs = 3 if lvl < 2 else 2
        pts, rads = [p], [rad]
        q = V(p)
        dd = V(d)
        for i in range(segs):
            dd = (dd + V((r.gauss(0, 0.12), r.gauss(0, 0.12), r.gauss(0, 0.06) + 0.05))).normalized()
            q = q + dd * (L / segs)
            pts.append(q.copy())
            rads.append(rad * (1 - 0.35 * (i + 1) / segs))
        mb.tube(pts, rads, 7 if lvl == 0 else (5 if lvl == 1 else 4), bark, cap=False)
        if lvl >= depth:
            tips.append((q, dd))
            return
        nk = 3 if lvl == 0 else r.choice((2, 3))
        for k in range(nk):
            az = 2 * math.pi * (k + r.random() * 0.6) / nk
            tilt = r.uniform(0.45, 0.85) if lvl > 0 else r.uniform(0.5, 0.8)
            side = V((math.cos(az), math.sin(az), 0))
            nd_ = (dd * math.cos(tilt) + side * math.sin(tilt)).normalized()
            grow(q, nd_, L * r.uniform(0.62, 0.78), rads[-1] * 0.72, lvl + 1)
        if lvl >= 1:
            tips.append((q, dd))

    trunk_len = crown_z0
    grow(V((0, 0, -0.2)), V((0, 0, 1)), trunk_len + 0.2, trunk_r, 0)
    # canopy: leaves clustered around the branch tips inside the crown ellipsoid
    cc = V((0, 0, crown_z0 + (H - crown_z0) * 0.5))
    ez = (H - crown_z0) * 0.5
    outline = leaf_shape(shape)
    for i in range(n_leaf):
        tp, td = tips[r.randrange(len(tips))]
        off = V((r.gauss(0, 1), r.gauss(0, 1), r.gauss(0, 1) * 0.8)) * crown_r * spread * 0.45
        p = tp + off
        rel = p - cc
        e = (rel.x / crown_r) ** 2 + (rel.y / crown_r) ** 2 + (rel.z / ez) ** 2
        if e > 1.0:
            p = cc + rel / math.sqrt(e) * r.uniform(0.9, 1.0)
        if p.z < crown_z0 * 0.85:
            continue
        outn = (p - cc)
        outn.z *= 0.6
        nrm = (outn.normalized() * 0.6 + V((r.gauss(0, 0.6), r.gauss(0, 0.6), r.gauss(0.4, 0.6)))).normalized()
        a = V((0, 0, 1)) if abs(nrm.z) < 0.9 else V((1, 0, 0))
        u = nrm.cross(a).normalized()
        rr = r.random() * 2 * math.pi
        u = (u * math.cos(rr) + nrm.cross(u) * math.sin(rr))
        w = nrm.cross(u)
        s = leaf_sz * r.uniform(0.7, 1.25)
        if outline:
            pts = [p + (u * x + w * y) * s for x, y in outline]
            ctr = p + w * (0.12 * s) + nrm * 0.1 * s
            nv = len(pts)
            mb.raw([ctr] + pts, [(0, 1 + k, 1 + (k + 1) % nv) for k in range(nv)], leaf_mat)
        else:
            nv = 10       # serrated rosette: reads as a cluster of leaves, not one big leaf
            pts = [p + (u * math.cos(2 * math.pi * k / nv) + w * math.sin(2 * math.pi * k / nv)) * s *
                   (r.uniform(0.7, 1.0) if k % 2 == 0 else r.uniform(0.3, 0.5)) for k in range(nv)]
            ctr = p + nrm * 0.25 * s
            mb.raw([ctr] + pts, [(0, 1 + k, 1 + (k + 1) % nv) for k in range(nv)], leaf_mat)
    return mb


def spruce(seed, H, R, mat='ext_leaf_spruce'):
    r = random.Random(seed)
    mb = MB()
    mb.cyl((0, 0, -0.2), (0, 0, H), 0.22, 0.02, 7, 'ext_bark', cap=False)
    z = 0.6
    while z < H - 0.3:
        t = (z - 0.6) / (H - 0.9)
        rad = R * (1 - t) ** 0.95 + 0.25
        for layer in range(2):
            nv = 13
            rot = r.random() * 6.28
            pts = []
            for k in range(nv):
                a = rot + 2 * math.pi * k / nv
                rr = rad * (r.uniform(0.75, 1.05) if k % 2 == 0 else r.uniform(0.45, 0.7))
                pts.append((rr * math.cos(a), rr * math.sin(a), z - 0.35 * rr * (0.8 + 0.4 * r.random())))
            mb.raw([(0, 0, z + 0.15 + layer * 0.1)] + pts, [(0, 1 + k, 1 + (k + 1) % nv) for k in range(nv)], mat)
        z += 0.34 + 0.08 * r.random()
    return mb


def shrub(seed, rx, ry, rz, n=75, sz=0.19, mat='ext_leaf_shrub'):
    r = random.Random(seed)
    mb = MB()
    for i in range(n):
        th, ph = r.uniform(0, 6.283), math.acos(r.uniform(-0.3, 1.0))
        d = V((math.sin(ph) * math.cos(th), math.sin(ph) * math.sin(th), math.cos(ph)))
        p = V((d.x * rx, d.y * ry, d.z * rz + rz * 0.85)) * r.uniform(0.8, 1.02)
        nrm = (d + V((r.gauss(0, .4), r.gauss(0, .4), r.gauss(0, .4)))).normalized()
        a = V((0, 0, 1)) if abs(nrm.z) < 0.9 else V((1, 0, 0))
        u = nrm.cross(a).normalized()
        w = nrm.cross(u)
        nv = 6
        pts = [p + (u * math.cos(2 * math.pi * k / nv) + w * math.sin(2 * math.pi * k / nv)) * sz * r.uniform(0.5, 1.0) for k in range(nv)]
        mb.raw([p + nrm * sz * 0.3] + pts, [(0, 1 + k, 1 + (k + 1) % nv) for k in range(nv)], mat)
    return mb


# =====================================================================================  build: our facade
print('facade...')


def build_facade():
    mb = MB()
    X0, X1 = -7.0, 13.0
    EZ = 3.55                   # soffit underside
    zb = G + 0.35               # siding starts above the parged foundation
    e, t0, t1 = 0.178, 0.012, 0.03
    # openings in facade (x0, z0, x1, z1) -- siding stops at their casing
    holes = [(-1.43, 0.62, 1.13, 2.61),                         # our study window (the room's own opening)
             (-1.3 - 0.09, G + 0.95 - 0.05, 1.0 + 0.09, G + 2.45 + 0.09 + 0.025),   # living room window below
             (-5.6 - 0.09, G + 3.8 - 0.05, -4.4 + 0.09, G + 5.3 + 0.115),
             (9.4 - 0.09, G + 3.8 - 0.05, 10.6 + 0.09, G + 5.3 + 0.115),
             (4.0 - 0.1, G + 0.6, 5.3 + 0.1, G + 2.75 + 0.1),
             (7.5 - 0.1, G - 0.1, 12.4 + 0.1, G + 2.13 + 0.1)]
    nrow = int(math.ceil((EZ - zb) / e))
    for i in range(nrow):
        za, zc = zb + i * e, min(EZ, zb + (i + 1) * e)
        segs = [(X0, X1)]
        for hx0, hz0, hx1, hz1 in holes:
            if zc > hz0 and za < hz1:
                ns = []
                for a, b in segs:
                    if hx1 <= a or hx0 >= b:
                        ns.append((a, b))
                        continue
                    if hx0 > a:
                        ns.append((a, hx0))
                    if hx1 < b:
                        ns.append((hx1, b))
                segs = ns
        for a, b in segs:
            ya, yc = FY + t1, FY + t0
            mb.poly([(b, ya, za), (a, ya, za), (a, yc, zc), (b, yc, zc)], 'ext_siding_geo')
            mb.poly([(a, FY + t0 * 0.5, za), (b, FY + t0 * 0.5, za), (b, ya, za), (a, ya, za)], 'ext_siding_geo')
    # parged foundation strip
    mb.poly([(X1, FY + 0.005, G - 0.1), (X0, FY + 0.005, G - 0.1), (X0, FY + 0.005, zb), (X1, FY + 0.005, zb)], 'ext_foundation')
    # corner boards, frieze under the soffit
    for x in (X0, X1 - 0.1):
        mb.box((x, FY, zb), (x + 0.1, FY + 0.05, EZ), 'ext_trim')
    mb.box((X0, FY, EZ - 0.16), (X1, FY + 0.045, EZ), 'ext_trim')
    # eave: soffit, fascia, short roof strip (only outside the wall plane), gutter + downspout
    o = 0.5
    mb.poly([(X0 - 0.3, FY, EZ), (X1 + 0.3, FY, EZ), (X1 + 0.3, FY + o, EZ), (X0 - 0.3, FY + o, EZ)], 'ext_soffit')
    for k in range(int((X1 - X0 + 0.6) / 0.3)):
        x = X0 - 0.3 + k * 0.3 + 0.15
        mb.box((x - 0.004, FY + 0.05, EZ - 0.004), (x + 0.004, FY + o - 0.03, EZ), 'ext_dark')
    mb.box((X0 - 0.32, FY + o, EZ), (X1 + 0.32, FY + o + 0.025, EZ + 0.2), 'ext_trim')
    rz0 = EZ + 0.2
    mb.poly([(X0 - 0.32, FY + o + 0.04, rz0), (X1 + 0.32, FY + o + 0.04, rz0), (X1 + 0.32, FY, rz0 + (o + 0.04) * 0.5),
             (X0 - 0.32, FY, rz0 + (o + 0.04) * 0.5)], 'ext_shingle')
    gy = FY + o + 0.025
    mb.box((X0 - 0.3, gy, EZ + 0.05), (X1 + 0.3, gy + 0.13, EZ + 0.17), 'ext_trim', skip=('+z',))
    mb.poly([(X0 - 0.3, gy, EZ + 0.165), (X1 + 0.3, gy, EZ + 0.165), (X1 + 0.3, gy + 0.13, EZ + 0.165), (X0 - 0.3, gy + 0.13, EZ + 0.165)], 'ext_dark')
    for x in (X0 + 0.25, X1 - 0.25):
        mb.beam((x, gy + 0.065, EZ + 0.05), (x, FY + 0.28, EZ - 0.3), 0.075, 0.055, 'ext_trim')
        mb.beam((x, FY + 0.28, EZ - 0.3), (x, FY + 0.09, EZ - 0.55), 0.075, 0.055, 'ext_trim')
        mb.box((x - 0.0375, FY + 0.06, G + 0.3), (x + 0.0375, FY + 0.12, EZ - 0.55), 'ext_trim')
        mb.beam((x, FY + 0.09, G + 0.33), (x, FY + 0.4, G + 0.12), 0.075, 0.055, 'ext_trim')
        mb.box((x - 0.15, FY + 0.2, G - 0.02), (x + 0.15, FY + 0.8, G + 0.05), 'ext_concrete')
    # other openings (generic parts in a facade frame: u = x, v = z - G, w = y - FY ... facing +y)
    M = frame((0, FY + 0.02, G), (-1, 0, 0), (0, 0, 1), (0, 1, 0))       # u = -x
    mb.push(M)
    window(mb, -1.0, 0.95, 1.3, 2.45, cover=('curtain', 0.3), deep=0.3)
    window(mb, 4.4, 3.8, 5.6, 5.3, cover=('blinds', 0.5), deep=0.3)
    window(mb, -10.6, 3.8, -9.4, 5.3, cover=('blinds', 0.7), deep=0.3)
    door(mb, -5.3 + 0.36, 0.6, -4.0, 2.75, sidelight=0.0)
    door(mb, -5.3, 0.6, -5.3 + 0.36, 2.75, sidelight=0.0) if False else None
    garage_door(mb, -12.4, -7.5, 2.13, windows=True)
    mb.pop()
    # porch stoop and steps for the front door
    mb.box((3.7, FY, G - 0.2), (5.6, FY + 1.5, G + 0.6), 'ext_concrete')
    for i in range(3):
        mb.box((3.9, FY + 1.5 + i * 0.28, G - 0.2), (5.4, FY + 1.5 + (i + 1) * 0.28, G + 0.6 - (i + 1) * 0.2), 'ext_concrete')
    # ---- the study window's exterior trim and sill (outside the room's own frame, y >= FY)
    x0, x1, z0, z1 = WIN
    cw, T = 0.10, 0.052
    tr = MB()
    tr.box((x0 - cw, FY, z0 - 0.02), (x0, FY + T, z1 + cw), 'ext_trim')
    tr.box((x1, FY, z0 - 0.02), (x1 + cw, FY + T, z1 + cw), 'ext_trim')
    tr.box((x0, FY, z1), (x1, FY + T, z1 + cw), 'ext_trim')
    tr.box((x0 - cw - 0.02, FY, z1 + cw), (x1 + cw + 0.02, FY + T + 0.015, z1 + cw + 0.03), 'ext_trim')      # drip cap
    # sloped sill with drip lip
    sx0, sx1 = x0 - cw - 0.04, x1 + cw + 0.04
    sl = [(FY, z0 + 0.0), (FY + 0.075, z0 - 0.022), (FY + 0.075, z0 - 0.052), (FY + 0.065, z0 - 0.052),
          (FY + 0.065, z0 - 0.044), (FY, z0 - 0.06)]
    n = len(sl)
    verts = [(sx0, y, z) for y, z in sl] + [(sx1, y, z) for y, z in sl]
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    tr.raw(verts, faces, 'ext_trim')
    # J-channel returns where the siding butts the casing
    tr.box((x0 - cw - 0.02, FY, z0 - 0.06), (x0 - cw, FY + 0.038, z1 + cw), 'ext_trim')
    tr.box((x1 + cw, FY, z0 - 0.06), (x1 + cw + 0.02, FY + 0.038, z1 + cw), 'ext_trim')
    o_tr = tr.build('EXT_window_trim')
    bv = o_tr.modifiers.new('bevel', 'BEVEL')
    bv.width = 0.004
    bv.segments = 2
    bv.limit_method = 'ANGLE'
    o_facade = mb.build('EXT_house_facade', color=(0.60, 0.585, 0.54))
    return o_facade


build_facade()

# =====================================================================================  build: street & ground
print('street...')
XS = [-900, -500, -300, -200, -140, -100, -70, -50] + [x * 2.5 for x in range(-18, 19)] + [50, 70, 100, 140, 200, 300, 500, 900]
SIDE_X0, SIDE_X1 = -46.0, -30.0          # side-street corridor (pavement -42.35..-33.65)
SIDE_C = -38.0
CURB_A, CURB_B = 12.15, 20.85            # curb faces
GUT = G - 0.15


def street_z(y):
    """Asphalt surface: crowned 12 cm between the gutter lines."""
    y0, y1 = CURB_A + 0.3, CURB_B - 0.3
    t = (y - S0) / ((y1 - y0) / 2)
    return GUT + 0.02 + 0.12 * max(0.0, 1 - t * t)


def build_street():
    mb = MB()
    ys = [CURB_A + 0.3 + k * (CURB_B - CURB_A - 0.6) / 14 for k in range(15)]
    for i in range(len(XS) - 1):
        xa, xb = XS[i], XS[i + 1]
        for j in range(len(ys) - 1):
            ya, yb = ys[j], ys[j + 1]
            mb.poly([(xa, ya, street_z(ya)), (xb, ya, street_z(ya)), (xb, yb, street_z(yb)), (xa, yb, street_z(yb))], 'ext_asphalt')
    o = mb.build('EXT_street_asphalt')
    return o


def curb_profile(side, dep):
    """Curb + gutter pan cross-section (y, z), from boulevard to asphalt. dep 0..1 = driveway depression."""
    top = G - 0.005 - dep * 0.11
    if side == 'near':
        yb, yf, yg = CURB_A - 0.15, CURB_A, CURB_A + 0.3
        return [(yb, G - 0.3), (yb, top), (yf - 0.02, top), (yf, top - 0.02), (yf + 0.012, GUT + 0.005), (yg, GUT + 0.02), (yg, GUT - 0.3)]
    yb, yf, yg = CURB_B + 0.15, CURB_B, CURB_B - 0.3
    return [(yg, GUT - 0.3), (yg, GUT + 0.02), (yf - 0.012, GUT + 0.005), (yf, top - 0.02), (yf + 0.02, top), (yb, top), (yb, G - 0.3)]


def depression(x, drives):
    d = 0.0
    for a, b in drives:
        if a - 1.0 < x < b + 1.0:
            d = max(d, 1.0 if a <= x <= b else 1.0 - min(abs(x - a), abs(x - b)) / 1.0)
    return d


def build_curbs(drives_near, drives_far):
    mb = MB()
    for side, drives in (('near', drives_near), ('far', drives_far)):
        xs = sorted(set([x for x in XS if -60 <= x <= 60] + [x for a, b in drives for x in (a - 1, a, b, b + 1)] +
                        [x * 1.0 for x in range(-60, 61, 3)]))
        xs = [-900, -300, -100] + [x for x in xs if -60 <= x <= 60] + [100, 300, 900]
        if side == 'far':
            xs = [x for x in xs if not (SIDE_X0 + 3.5 < x < SIDE_X1 - 3.5)]
        prof = [curb_profile(side, depression(x, drives)) for x in xs]
        n = len(prof[0])
        for i in range(len(xs) - 1):
            if side == 'far' and xs[i] <= SIDE_X0 + 3.5 and xs[i + 1] >= SIDE_X1 - 3.5:
                continue
            for k in range(n - 1):
                a0, a1 = prof[i][k], prof[i][k + 1]
                b0, b1 = prof[i + 1][k], prof[i + 1][k + 1]
                mb.poly([(xs[i], a0[0], a0[1]), (xs[i + 1], b0[0], b0[1]), (xs[i + 1], b1[0], b1[1]), (xs[i], a1[0], a1[1])],
                        'ext_concrete_old')
            # expansion/control joints every 3 m
            if -60 < xs[i] < 60 and abs(xs[i] - round(xs[i] / 3) * 3) < 1e-6:
                p = prof[i]
                for k in range(1, n - 2):
                    mb.poly([(xs[i] - 0.004, p[k][0], p[k][1] + 0.001), (xs[i] + 0.004, p[k][0], p[k][1] + 0.001),
                             (xs[i] + 0.004, p[k + 1][0], p[k + 1][1] + 0.001), (xs[i] - 0.004, p[k + 1][0], p[k + 1][1] + 0.001)], 'ext_crack')
    return mb.build('EXT_curbs_gutters')


def sidewalk(mb, y0, y1, x0, x1, slab=1.5, z=G + 0.03, near=(-70, 70), skip=None):
    """Concrete walk: individual 1.5 m slabs with tooled control joints near, one strip far."""
    x = x0
    while x < x1:
        if near[0] <= x < near[1]:
            b = min(x + slab, x1)
            if skip and skip[0] < (x + b) / 2 < skip[1]:
                x = b
                continue
            j = 0.006
            h = z + rnd.uniform(-0.006, 0.006)
            mb.box((x + j, y0, h - 0.12), (b - j, y1, h), 'ext_concrete')
            mb.poly([(x - j, y0 + 0.01, h - 0.012), (x + j, y0 + 0.01, h - 0.012), (x + j, y1 - 0.01, h - 0.012), (x - j, y1 - 0.01, h - 0.012)], 'ext_crack')
            x = b
        else:
            b = near[0] if x < near[0] else x1
            if skip and x < skip[1] and b > skip[0]:
                if x < skip[0]:
                    mb.box((x, y0, z - 0.12), (skip[0], y1, z), 'ext_concrete')
                if b > skip[1]:
                    mb.box((skip[1], y0, z - 0.12), (b, y1, z), 'ext_concrete')
            else:
                mb.box((x, y0, z - 0.12), (b, y1, z), 'ext_concrete')
            x = b


def strip(mb, x0, x1, y0, y1, z, mat, skips=()):
    """Ground strip along x with gaps."""
    cuts = sorted(skips)
    x = x0
    for a, b in cuts + [(x1, x1)]:
        if a > x:
            xs = [xx for xx in XS if x < xx < min(a, x1)]
            pts = [x] + xs + [min(a, x1)]
            for i in range(len(pts) - 1):
                mb.poly([(pts[i], y0, z), (pts[i + 1], y0, z), (pts[i + 1], y1, z), (pts[i], y1, z)], mat)
        x = max(x, b)


# lots across the street and their driveways
ACROSS = [  # (lot_x0, type, mirror, siding colour, garage side x-range in world, seed)
    (-30.0, 'B', False, (0.50, 0.47, 0.40)),
    (-15.0, 'A', False, (0.40, 0.44, 0.45)),
    (0.0, 'C', True, (0.56, 0.54, 0.48)),
    (15.0, 'A', True, (0.40, 0.43, 0.36)),
    (30.0, 'B', True, (0.62, 0.61, 0.58)),
    (45.0, 'C', False, (0.47, 0.44, 0.40)),
    (-61.0, 'A', False, (0.52, 0.50, 0.46)),
    (-76.0, 'C', True, (0.55, 0.52, 0.47)),
]
HOUSE_OFF = {'A': 0.9, 'B': 6.3, 'C': 1.1}          # main-block x0 within the lot
GARAGE_SPAN = {'A': (7.4, 12.9), 'B': (-5.7, 0.0), 'C': (7.2, 12.8)}
GARAGE_FRONT = {'A': -1.6, 'B': 0.0, 'C': -1.0}


def lot_geom(lx, t, mirror):
    """World x-range of the garage (driveway) and house origin/scale for a lot."""
    ox = lx + HOUSE_OFF[t]
    g0, g1 = GARAGE_SPAN[t]
    if mirror:
        ox = lx + LOT - HOUSE_OFF[t]
        return ox, (ox - g1, ox - g0)
    return ox, (ox + g0, ox + g1)


DRIVES_FAR = []
for lx, t, mir, colr in ACROSS:
    ox, (ga, gb) = lot_geom(lx, t, mir)
    DRIVES_FAR.append((ga + 0.2, gb - 0.2))
DRIVES_NEAR = [(7.4, 12.6)]


def build_ground():
    mb = MB()
    # our side
    strip(mb, -900, 900, -30.0, FY, G, 'ext_grass')
    strip(mb, -900, 900, FY, 8.0, G, 'ext_grass', skips=[DRIVES_NEAR[0]])
    sidewalk(mb, 8.0, 9.5, -900, 900)
    strip(mb, -900, 900, 9.5, CURB_A - 0.15, G, 'ext_grass', skips=[(a, b) for a, b in DRIVES_NEAR])
    # across
    far_skips = [(a, b) for a, b in DRIVES_FAR] + [(SIDE_X0 + 3.5, SIDE_X1 - 3.5)]
    strip(mb, -900, 900, CURB_B + 0.15, 24.0, G, 'ext_grass', skips=far_skips)
    sidewalk(mb, 24.0, 25.5, -900, 900, skip=(SIDE_X0 + 3.5, SIDE_X1 - 3.5))
    # driveways (ours + across): apron from the curb, over the walk, up to the garage
    for (a, b) in DRIVES_NEAR:
        mb.box((a, FY - 0.5, G - 0.2), (b, 8.0, G + 0.02), 'ext_driveway')
        mb.poly([(a, 9.5, G + 0.02), (b, 9.5, G + 0.02), (b, CURB_A - 0.15, G - 0.1), (a, CURB_A - 0.15, G - 0.1)], 'ext_driveway')
    for i, (lx, t, mir, colr) in enumerate(ACROSS):
        a, b = DRIVES_FAR[i]
        gf = FRONT + GARAGE_FRONT[t]
        mat = ('ext_driveway', 'ext_pavers', 'ext_driveway', 'ext_concrete', 'ext_driveway', 'ext_pavers', 'ext_driveway', 'ext_driveway')[i]
        mb.poly([(a, CURB_B + 0.15, G - 0.1), (b, CURB_B + 0.15, G - 0.1), (b, 24.0, G + 0.02), (a, 24.0, G + 0.02)], 'ext_driveway')
        mb.box((a, 25.5, G - 0.2), (b, gf, G + 0.025), mat)
    return mb.build('EXT_ground_near')


def build_terrain():
    mb = MB()
    xs = [-900, -500, -300, -200, -140, -100, -70, SIDE_X0, SIDE_X1, -15, 0, 15, 30, 50, 70, 100, 140, 200, 300, 500, 900]
    ys = [25.5, 40, 60, 70, 80, 95, 110, 130, 150, 175, 200, 240, 280, 330, 400, 500, 650, 850, 1100, 1500, 2200]
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            xa, xb, ya, yb = xs[i], xs[i + 1], ys[j], ys[j + 1]
            if xa >= SIDE_X0 + 3.5 - 1e-6 and xb <= SIDE_X1 - 3.5 + 1e-6:
                continue
            mb.poly([(xa, ya, ground_z(ya)), (xb, ya, ground_z(ya)), (xb, yb, ground_z(yb)), (xa, yb, ground_z(yb))], 'ext_grass')
    # side street + its grass shoulders (subdivided in y so it follows the terrain)
    yss = [CURB_B - 0.3, CURB_B + 0.15, 23.5, 25.5] + ys[1:]
    for j in range(len(yss) - 1):
        ya, yb = yss[j], yss[j + 1]
        za = GUT + 0.03 if ya < CURB_B else ground_z(ya) + (0.0 if ya > 23.4 else -0.07)
        zb = GUT + 0.03 if yb < CURB_B else ground_z(yb) + (0.0 if yb > 23.4 else -0.07)
        mb.poly([(SIDE_X0 + 3.65, ya, za), (SIDE_X1 - 3.65, ya, za), (SIDE_X1 - 3.65, yb, zb), (SIDE_X0 + 3.65, yb, zb)], 'ext_asphalt')
        if ya >= 23.4:
            for xa, xb in ((SIDE_X0, SIDE_X0 + 3.5), (SIDE_X1 - 3.5, SIDE_X1)):
                mb.poly([(xa, ya, ground_z(ya) + 0.01), (xb, ya, ground_z(ya) + 0.01), (xb, yb, ground_z(yb) + 0.01), (xa, yb, ground_z(yb) + 0.01)], 'ext_grass')
            for xa in (SIDE_X0 + 3.5, SIDE_X1 - 3.65):
                mb.poly([(xa, ya, ground_z(ya) + 0.02), (xa + 0.15, ya, ground_z(ya) + 0.02), (xa + 0.15, yb, ground_z(yb) + 0.02), (xa, yb, ground_z(yb) + 0.02)], 'ext_concrete_old')
        else:
            for xa, xb in ((SIDE_X0, SIDE_X0 + 3.5), (SIDE_X1 - 3.5, SIDE_X1)):
                mb.poly([(xa, max(ya, CURB_B + 0.15), G), (xb, max(ya, CURB_B + 0.15), G), (xb, yb, G), (xa, yb, G)], 'ext_grass')
    # far parallel streets (every 75 m) and their curbs, following the terrain
    for k in range(1, 7):
        yc = S0 + 75 * k
        for xa, xb in ((-900, SIDE_X0 + 3.5), (SIDE_X1 - 3.5, 900)):
            z = ground_z(yc) + 0.02
            mb.poly([(xa, yc - 4.35, z), (xb, yc - 4.35, z), (xb, yc + 4.35, z), (xa, yc + 4.35, z)], 'ext_asphalt')
            for yy in (yc - 4.5, yc + 4.35):
                mb.poly([(xa, yy, z + 0.1), (xb, yy, z + 0.1), (xb, yy + 0.15, z + 0.1), (xa, yy + 0.15, z + 0.1)], 'ext_concrete_old')
            for yy in (yc - 8.0, yc + 6.5):
                mb.poly([(xa, yy, z + 0.01), (xb, yy, z + 0.01), (xb, yy + 1.5, z + 0.01), (xa, yy + 1.5, z + 0.01)], 'ext_concrete')
    return mb.build('EXT_terrain')


def crack_path(r, p, d, n, step, wob):
    pts = [V(p)]
    dd = V(d).normalized()
    for i in range(n):
        dd = (dd + V((r.gauss(0, wob), r.gauss(0, wob), 0))).normalized()
        pts.append(pts[-1] + dd * step * r.uniform(0.6, 1.3))
    return pts


def ribbon(mb, pts, w, zf, mat):
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = (b - a)
        if d.length < 1e-5:
            continue
        s = V((-d.y, d.x, 0)).normalized() * (w / 2)
        mb.poly([(a - s).to_tuple(), (b - s).to_tuple(), (b + s).to_tuple(), (a + s).to_tuple()], mat)


def build_road_detail():
    """Tar-snake sealed cracks, open hairline cracks, sealed longitudinal seams, patches, manhole, catch basins."""
    r = random.Random(77)
    mb = MB()

    def zs(p, lift):
        return V((p.x, p.y, street_z(p.y) + lift))

    y_lo, y_hi = CURB_A + 0.35, CURB_B - 0.35
    # sealed longitudinal seams (paving joint at centre + near each gutter line)
    for yy, w in ((S0 + 0.05, 0.07), (CURB_A + 0.33, 0.05), (CURB_B - 0.33, 0.05)):
        pts = []
        x = -80.0
        while x <= 80.0:
            pts.append(zs(V((x, yy + r.gauss(0, 0.015), 0)), 0.004))
            x += 2.0
        ribbon(mb, pts, w, 0, 'ext_sealant')
    # transverse sealed cracks (meandering, some branching)
    for i in range(34):
        x = r.uniform(-45, 45)
        y = r.choice((y_lo, y_hi))
        d = V((r.gauss(0, 0.25), 1 if y == y_lo else -1, 0))
        pts = [p for p in crack_path(r, (x, y, 0), d, r.randint(8, 22), 0.35, 0.25) if y_lo <= p.y <= y_hi]
        if len(pts) > 1:
            ribbon(mb, [zs(p, 0.004) for p in pts], r.uniform(0.035, 0.06), 0, 'ext_sealant')
        if r.random() < 0.45 and len(pts) > 4:
            b = crack_path(r, pts[len(pts) // 2], (r.gauss(0, 1), r.gauss(0, 1), 0), r.randint(4, 9), 0.3, 0.35)
            b = [p for p in b if y_lo <= p.y <= y_hi]
            if len(b) > 1:
                ribbon(mb, [zs(p, 0.0035) for p in b], 0.03, 0, 'ext_sealant')
    # hairline (unsealed) cracks
    for i in range(60):
        p0 = V((r.uniform(-40, 40), r.uniform(y_lo, y_hi), 0))
        pts = [p for p in crack_path(r, p0, (r.gauss(0, 1), r.gauss(0, 1), 0), r.randint(4, 14), 0.22, 0.5) if y_lo <= p.y <= y_hi]
        if len(pts) > 1:
            ribbon(mb, [zs(p, 0.002) for p in pts], r.uniform(0.006, 0.012), 0, 'ext_crack')
    # utility-cut patches (darker, slightly proud) with sealed perimeters
    for (x0, y0, w, h) in ((-6.5, 13.2, 2.4, 1.6), (3.2, 17.4, 1.8, 3.0), (-17.0, 18.6, 3.5, 1.7), (11.0, 12.6, 2.0, 1.2),
                           (-2.0, 15.7, 7.5, 1.0)):
        nx, ny = 6, 4
        for i in range(nx):
            for j in range(ny):
                xa, xb = x0 + w * i / nx, x0 + w * (i + 1) / nx
                ya, yb = y0 + h * j / ny, y0 + h * (j + 1) / ny
                mb.poly([zs(V((xa, ya, 0)), 0.006).to_tuple(), zs(V((xb, ya, 0)), 0.006).to_tuple(),
                         zs(V((xb, yb, 0)), 0.006).to_tuple(), zs(V((xa, yb, 0)), 0.006).to_tuple()], 'ext_asphalt_patch')
        edge = [V((x0, y0, 0)), V((x0 + w, y0, 0)), V((x0 + w, y0 + h, 0)), V((x0, y0 + h, 0)), V((x0, y0, 0))]
        pts = []
        for a, b in zip(edge, edge[1:]):
            for k in range(6):
                pts.append(zs(a.lerp(b, k / 6), 0.008))
        pts.append(zs(edge[-1], 0.008))
        ribbon(mb, pts, 0.07, 0, 'ext_sealant')
    # manhole cover (sanitary) in the crown
    c = V((6.8, S0 + 0.9, street_z(S0 + 0.9) + 0.004))
    mb.disc(c + V((0, 0, 0.004)), (0, 0, 1), 0.36, 24, 'ext_grate')
    for k in range(6):
        mb.box((c.x - 0.3 + k * 0.1, c.y - 0.012, c.z + 0.004), (c.x - 0.26 + k * 0.1, c.y + 0.012, c.z + 0.009), 'ext_dark') if False else None
    mb.tube([c + V((0.33 * math.cos(a), 0.33 * math.sin(a), 0.006)) for a in [2 * math.pi * k / 24 for k in range(25)]], 0.012, 4, 'ext_grate')
    for k in range(-3, 4):
        mb.box((c.x + k * 0.085 - 0.01, c.y - 0.28 + abs(k) * 0.02, c.z + 0.004), (c.x + k * 0.085 + 0.01, c.y + 0.28 - abs(k) * 0.02, c.z + 0.012), 'ext_grate')
    patch_ring = [zs(c + V((0.55 * math.cos(a), 0.55 * math.sin(a), 0)), 0.005) for a in [2 * math.pi * k / 20 for k in range(21)]]
    ribbon(mb, patch_ring, 0.12, 0, 'ext_asphalt_patch')
    # catch basins in the gutter: frame, grate bars, dark sump
    for cx, side in ((2.6, 'near'), (-4.2, 'far'), (24.0, 'far')):
        yc = CURB_A + 0.33 if side == 'near' else CURB_B - 0.33
        z = GUT + 0.0
        mb.box((cx - 0.38, yc - 0.33, z - 0.05), (cx + 0.38, yc + 0.33, z + 0.012), 'ext_concrete_old', skip=('+z',))
        mb.poly([(cx - 0.38, yc - 0.33, z + 0.012), (cx + 0.38, yc - 0.33, z + 0.012), (cx + 0.38, yc - 0.28, z + 0.012), (cx - 0.38, yc - 0.28, z + 0.012)], 'ext_concrete_old')
        mb.poly([(cx - 0.38, yc + 0.28, z + 0.012), (cx + 0.38, yc + 0.28, z + 0.012), (cx + 0.38, yc + 0.33, z + 0.012), (cx - 0.38, yc + 0.33, z + 0.012)], 'ext_concrete_old')
        mb.box((cx - 0.3, yc - 0.28, z - 0.6), (cx + 0.3, yc + 0.28, z - 0.59), 'ext_dark')
        for s in (-1, 1):
            mb.poly([(cx - 0.3, yc + s * 0.28, z - 0.6), (cx + 0.3, yc + s * 0.28, z - 0.6), (cx + 0.3, yc + s * 0.28, z), (cx - 0.3, yc + s * 0.28, z)], 'ext_dark')
            mb.poly([(cx + s * 0.3, yc - 0.28, z - 0.6), (cx + s * 0.3, yc + 0.28, z - 0.6), (cx + s * 0.3, yc + 0.28, z), (cx + s * 0.3, yc - 0.28, z)], 'ext_dark')
        mb.box((cx - 0.3, yc - 0.28, z - 0.02), (cx + 0.3, yc - 0.25, z + 0.008), 'ext_grate')
        mb.box((cx - 0.3, yc + 0.25, z - 0.02), (cx + 0.3, yc + 0.28, z + 0.008), 'ext_grate')
        for k in range(9):
            xx = cx - 0.28 + k * 0.07
            mb.box((xx - 0.012, yc - 0.25, z - 0.03), (xx + 0.012, yc + 0.25, z + 0.008), 'ext_grate')
        # sand + leaf litter drift in the gutter around it
        mb.poly([(cx - 1.5, yc - 0.12, z + 0.018), (cx - 0.4, yc - 0.12, z + 0.018), (cx - 0.4, yc + 0.1, z + 0.018), (cx - 1.5, yc + 0.1, z + 0.018)], 'ext_mulch')
    # faded stop bar on the side street
    mb.box((SIDE_X0 + 3.8, 23.1, GUT + 0.1 + 0.04), (SIDE_C - 0.1, 23.5, GUT + 0.1 + 0.046), 'ext_paint_white')
    return mb.build('EXT_road_detail')


build_street()
build_curbs(DRIVES_NEAR, DRIVES_FAR)
build_ground()
build_terrain()
build_road_detail()

# =====================================================================================  houses
print('houses...')
HMESH = {}
for t, fn in (('A', house_A), ('B', house_B), ('C', house_C)):
    mb = fn()
    HMESH[t] = mb.build('EXT_house_' + t + '_src').data
    bpy.data.objects.remove(bpy.data.objects['EXT_house_' + t + '_src'])
    HMESH[t].name = 'EXT_house_' + t

for i, (lx, t, mir, colr) in enumerate(ACROSS):
    ox, _ = lot_geom(lx, t, mir)
    o = place(HMESH[t], 'EXT_house_%s_%02d' % (t, i), (ox, FRONT, G), 0.0, (-1 if mir else 1, 1, 1), colr)

# LOD houses: rows behind, beside us, and far
LODS = []
for s in range(6):
    mbl, wtot = house_lod(900 + s)
    obj = mbl.build('EXT_lod_src')
    LODS.append((obj.data, wtot))
    obj.data.name = 'EXT_house_lod%d' % s
    bpy.data.objects.remove(obj)

SIDING_COLS = [(0.50, 0.48, 0.43), (0.40, 0.43, 0.44), (0.58, 0.56, 0.51), (0.42, 0.44, 0.38), (0.63, 0.62, 0.59),
               (0.46, 0.42, 0.37), (0.36, 0.37, 0.38), (0.55, 0.50, 0.42)]
lr = random.Random(4242)
n_lod = 0


def lod_row(y_front, facing, xlim, skip_x=()):
    """facing -1: front faces -y (toward us). +1: faces +y (we see the back)."""
    global n_lod
    x = -xlim + lr.uniform(0, 5)
    while x < xlim:
        lx = x
        x += LOT
        if lx + LOT > SIDE_X0 and lx < SIDE_X1:
            continue
        if any(a - LOT < lx < b for a, b in skip_x):
            continue
        mesh, wtot = LODS[lr.randrange(len(LODS))]
        off = (LOT - wtot) / 2 + lr.uniform(-0.5, 0.5)
        mir = lr.random() < 0.5
        if facing < 0:
            ox = lx + off + (wtot if mir else 0)
            loc, rot, sc = (ox, y_front, ground_z(y_front + 5)), 0.0, (-1 if mir else 1, 1, 1)
        else:
            ox = lx + LOT - off - (wtot if mir else 0)
            loc, rot, sc = (ox, y_front, ground_z(y_front - 5)), math.pi, (-1 if mir else 1, 1, 1)
        place(mesh, 'EXT_house_lod_%03d' % n_lod, loc, rot, sc, SIDING_COLS[lr.randrange(len(SIDING_COLS))])
        n_lod += 1


# our side of the street: neighbours (front faces +y), beyond our own facade
lod_row(FY - 0.0, +1, 70, skip_x=[(-22.0, 28.0)])
place(LODS[1][0], 'EXT_house_lod_nbrL', (-8.5, FY - 0.3, G), math.pi, (1, 1, 1), SIDING_COLS[2])
place(LODS[3][0], 'EXT_house_lod_nbrR', (13.6 + LODS[3][1] + 0.9, FY - 0.3, G), math.pi, (1, 1, 1), SIDING_COLS[5])
# across row beyond the detailed lots
lod_row(FRONT, -1, 170, skip_x=[(-76.0, 60.0)])
for k in range(0, 3):
    s = S0 + 75 * k
    if k > 0:
        lod_row(s + 15.5, -1, 110 + 70 * k)
    lod_row(s + 75 - 15.5, +1, 110 + 70 * k)

# =====================================================================================  trees / shrubs
print('trees...')
t_young = tree(11, 5.6, 1.9, 2.2, 0.075, 1400, 0.085, 'ext_leaf_maple', 'ext_bark_grey', depth=3, shape='maple', spread=0.75)
m_young = t_young.build('EXT_tree_maple_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_tree_maple_src'])
m_young.name = 'EXT_tree_maple_young'
t_young2 = tree(12, 5.0, 1.6, 2.0, 0.065, 1150, 0.085, 'ext_leaf_maple', 'ext_bark_grey', depth=3, shape='maple', spread=0.75)
m_young2 = t_young2.build('EXT_tree_maple2_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_tree_maple2_src'])
m_young2.name = 'EXT_tree_maple_young2'
t_big = tree(21, 15.0, 5.5, 4.0, 0.32, 1250, 0.55, 'ext_leaf_mature', 'ext_bark', depth=4, shape='clump', spread=0.5)
m_big = t_big.build('EXT_tree_big_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_tree_big_src'])
m_big.name = 'EXT_tree_mature'
t_big2 = tree(22, 12.0, 4.5, 3.2, 0.26, 950, 0.52, 'ext_leaf_mature', 'ext_bark', depth=4, shape='clump', spread=0.5)
m_big2 = t_big2.build('EXT_tree_big2_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_tree_big2_src'])
m_big2.name = 'EXT_tree_mature2'
t_far = tree(31, 13.0, 5.0, 3.5, 0.3, 90, 2.0, 'ext_leaf_mature', 'ext_bark', depth=2, shape='clump', spread=0.7)
m_far = t_far.build('EXT_tree_far_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_tree_far_src'])
m_far.name = 'EXT_tree_far'
m_spruce = spruce(41, 11.0, 2.4).build('EXT_spruce_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_spruce_src'])
m_spruce.name = 'EXT_tree_spruce'
m_shrub = shrub(51, 0.55, 0.55, 0.45).build('EXT_shrub_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_shrub_src'])
m_shrub.name = 'EXT_shrub'
m_cedar = shrub(52, 0.45, 0.45, 1.1, n=95, sz=0.22).build('EXT_cedar_src').data
bpy.data.objects.remove(bpy.data.objects['EXT_cedar_src'])
m_cedar.name = 'EXT_shrub_cedar'

tr_ = random.Random(99)
nt_ = 0


def put(mesh, x, y, z=None, s=1.0, name='tree'):
    global nt_
    nt_ += 1
    return place(mesh, 'EXT_%s_%03d' % (name, nt_), (x, y, ground_z(y) if z is None else z), tr_.uniform(0, 6.283),
                 (s, s, s * tr_.uniform(0.92, 1.08)))


# boulevard maples (young): ours framing the left of the view, across the street
put(m_young, -5.6, 10.75, G, 1.0, 'maple')
put(m_young2, 9.0, 10.8, G, 1.05, 'maple')
put(m_young2, -21.0, 10.8, G, 0.95, 'maple')
put(m_young2, -21.5, 22.5, G, 1.1, 'maple')
put(m_young, -9.8, 22.4, G, 0.9, 'maple')
put(m_young2, 17.5, 22.6, G, 1.0, 'maple')
# backyard canopy trees + spruces behind the houses across
for x, y, m, s in ((-24.0, 49.0, m_big, 1.0), (-7.5, 51.0, m_big2, 1.0), (7.5, 47.5, m_big, 0.85), (21.0, 50.5, m_big2, 1.1),
                   (37.0, 48.0, m_big, 0.95), (-2.0, 60.5, m_big, 1.05), (14.0, 62.0, m_big2, 1.0), (-17.0, 61.0, m_big2, 0.9),
                   (29.0, 61.0, m_big, 1.0), (-53.0, 50.0, m_big, 1.0)):
    put(m, x, y, None, s, 'tree')
for x, y, s in ((-12.5, 45.0, 1.0), (27.0, 44.0, 0.85), (-27.0, 26.8, 0.55), (3.0, 56.0, 1.2)):
    put(m_spruce, x, y, None, s, 'spruce')
# far trees scattered through the rows
for i in range(55):
    y = tr_.uniform(75, 330)
    x = tr_.uniform(-(0.9 * y + 40), 0.9 * y + 40)
    if SIDE_X0 < x < SIDE_X1:
        continue
    put(m_far if tr_.random() < 0.8 else m_spruce, x, y, None, tr_.uniform(0.8, 1.25), 'tree_far')
# shrubs along foundations across + cedar hedges on some lot lines
for i, (lx, t, mir, colr) in enumerate(ACROSS[:6]):
    ox, (ga, gb) = lot_geom(lx, t, mir)
    for k in range(3):
        sx = (ox + (0.8 + k * 1.3) * (-1 if mir else 1)) if t != 'B' else ox + 0.8 + k * 1.4
        put(m_shrub, sx, FRONT - 0.8, G, tr_.uniform(0.8, 1.1), 'shrub')
for x in (-15.0, 30.0):
    for k in range(9):
        put(m_cedar, x, FRONT + 1.0 + k * 0.8, G, tr_.uniform(0.95, 1.1), 'cedar')
for k in range(5):
    put(m_shrub, -4.5 + k * 1.4, FY + 0.6, G, tr_.uniform(0.7, 1.0), 'shrub')

# =====================================================================================  fences
print('fences...')


def fence_run(mb, a, b, H=1.8, mat='ext_fence'):
    a, b = V(a), V(b)
    d = b - a
    L = d.length
    n = max(1, int(math.ceil(L / 2.4)))
    for i in range(n + 1):
        p = a + d * (i / n)
        mb.box((p.x - 0.045, p.y - 0.045, p.z - 0.3), (p.x + 0.045, p.y + 0.045, p.z + H + 0.08), mat)
        mb.box((p.x - 0.06, p.y - 0.06, p.z + H + 0.08), (p.x + 0.06, p.y + 0.06, p.z + H + 0.11), mat)
    dx = d.normalized()
    s = V((-dx.y, dx.x, 0)) * 0.012
    for i in range(n):
        p0, p1 = a + d * (i / n), a + d * ((i + 1) / n)
        q0, q1 = p0 + dx * 0.045, p1 - dx * 0.045
        mb.obox(((q0 + q1) / 2) + V((0, 0, 0.05 + H / 2)), (q1 - q0) / 2, s, V((0, 0, H / 2)), mat)
        mb.obox(((q0 + q1) / 2) + V((0, 0, H + 0.03)) + s * 1.5, (q1 - q0) / 2, s * 1.8, V((0, 0, 0.03)), mat)


fmb = MB()
yb = 54.0
fence_run(fmb, (-30.0, yb, G), (60.0, yb, G))
fence_run(fmb, (-110.0, yb, G), (-47.0, yb, G), mat='ext_fence_grey')
fence_run(fmb, (-29.0, yb, G), (-29.0, 26.0 + 10, G), mat='ext_fence_grey')     # corner lot, along the side street
for lx in (-15.0, 0.0, 15.0, 30.0, 45.0):
    fence_run(fmb, (lx, FRONT + 11.2, G), (lx, yb, G), mat='ext_fence' if lx % 30 else 'ext_fence_grey')
# side-yard gates between the houses (set back from the front walls)
for (a, b) in ((-15.4 + 0.0, -14.1), (-0.6, 0.6), (14.3, 15.7), (29.6, 30.7)):
    fence_run(fmb, (a, FRONT + 3.0, G), (b, FRONT + 3.0, G), 1.7)
fmb.build('EXT_fences')

# =====================================================================================  street furniture
print('furniture...')
PY = 22.35                    # pole line on the far boulevard
POLES = [-67.0, -31.0, 6.2, 42.0, 78.0, 114.0]


def build_pole(mb, x, y, light=False, transformer=False):
    z0 = G
    top = z0 + 11.6
    mb.cyl((x, y, z0 - 0.5), (x, y, top), 0.155, 0.115, 10, 'ext_pole')
    mb.disc((x, y, top + 0.003), (0, 0, 1), 0.117, 10, 'ext_pole')
    # crossarm (perpendicular to the line => along y) with braces and pin insulators
    za = top - 0.35
    mb.box((x - 0.05, y - 1.25, za - 0.05), (x + 0.05, y + 1.25, za + 0.05), 'ext_pole')
    for s in (-1, 1):
        mb.beam((x + 0.12, y, za - 0.6), (x + 0.07, y + s * 0.75, za - 0.05), 0.03, 0.01, 'ext_galv')
    for yy in (-1.1, 0.0, 1.1):
        py = y + yy if yy else y
        px = x if yy else x + 0.0
        zt = za + 0.05 if yy else top
        mb.cyl((px, py, zt), (px, py, zt + 0.08), 0.012, 0.012, 6, 'ext_galv')
        for k in range(3):
            mb.cyl((px, py, zt + 0.06 + k * 0.045), (px, py, zt + 0.09 + k * 0.045), 0.06 - k * 0.01, 0.045 - k * 0.008, 10, 'ext_insulator')
    # neutral, secondary rack with spools, telecom attachment
    for zz in (top - 1.6, top - 3.2):
        mb.box((x - 0.2, y - 0.03, zz - 0.15), (x - 0.15, y + 0.03, zz + 0.15), 'ext_galv')
        mb.cyl((x - 0.24, y, zz - 0.1), (x - 0.24, y, zz + 0.1), 0.04, 0.04, 8, 'ext_insulator')
    mb.box((x - 0.19, y - 0.05, z0 + 5.5), (x - 0.15, y + 0.05, z0 + 5.62), 'ext_galv')
    mb.box((x - 0.21, y - 0.05, z0 + 6.2), (x - 0.155, y + 0.05, z0 + 6.3), 'ext_galv')
    # ground-wire moulding, pole tag, step bolts
    mb.box((x + 0.1, y - 0.015, z0), (x + 0.13, y + 0.015, top - 0.4), 'ext_metal')
    mb.box((x - 0.06, y - 0.16, z0 + 1.6), (x + 0.06, y - 0.15, z0 + 1.75), 'ext_metal')
    for k in range(10):
        zz = z0 + 2.6 + k * 0.45
        s = 1 if k % 2 else -1
        mb.cyl((x, y + s * 0.1, zz), (x, y + s * 0.26, zz), 0.01, 0.01, 5, 'ext_galv', smooth=False)
    if transformer:
        zt = top - 2.3
        mb.cyl((x - 0.45, y, zt - 0.55), (x - 0.45, y, zt + 0.5), 0.3, 0.3, 16, 'ext_galv')
        mb.cyl((x - 0.45, y, zt + 0.5), (x - 0.45, y, zt + 0.56), 0.31, 0.25, 16, 'ext_galv')
        mb.box((x - 0.16, y - 0.2, zt - 0.3), (x - 0.12, y + 0.2, zt + 0.4), 'ext_galv')
        mb.cyl((x - 0.45, y, zt + 0.56), (x - 0.45, y, zt + 0.75), 0.04, 0.03, 8, 'ext_insulator')
        mb.cyl((x - 0.6, y + 0.1, zt + 0.3), (x - 0.6, y + 0.1, zt + 0.55), 0.035, 0.03, 8, 'ext_insulator')
    if light:
        zl = G + 8.4
        arm = [V((x - 0.05, y, zl - 0.5)), V((x - 0.2, y - 0.5, zl + 0.05)), V((x - 0.25, y - 1.5, zl + 0.25)), V((x - 0.25, y - 2.45, zl + 0.3))]
        mb.tube(arm, [0.04, 0.035, 0.032, 0.03], 8, 'ext_metal')
        mb.box((x - 0.12, y - 0.1, zl - 0.7), (x - 0.04, y + 0.1, zl - 0.3), 'ext_metal')
        hy = y - 2.45
        # cobra head: tapered body + flat lens underneath
        c = V((x - 0.25, hy - 0.35, zl + 0.28))
        mb.obox(c, V((0, -0.36, 0.02)), V((0.2, 0, 0)), V((0, 0, 0.08)), 'ext_metal')
        mb.obox(c + V((0, -0.02, 0.07)), V((0, -0.3, 0.02)), V((0.16, 0, 0)), V((0, 0, 0.05)), 'ext_metal')
        mb.obox(c + V((0, -0.02, -0.085)), V((0, -0.28, 0.02)), V((0.15, 0, 0)), V((0, 0, 0.01)), 'ext_luminaire')
        mb.cyl(c + V((0, 0.32, 0.07)), c + V((0, 0.32, 0.12)), 0.035, 0.035, 8, 'ext_plastic_black')


def catenary(a, b, sag, n=24):
    a, b = V(a), V(b)
    return [a.lerp(b, i / n) - V((0, 0, sag * 4 * (i / n) * (1 - i / n))) for i in range(n + 1)]


pmb = MB()
for x in POLES:
    build_pole(pmb, x, PY, light=(x == 6.2), transformer=(x == 42.0))
pmb.build('EXT_hydro_poles')

wmb = MB()
ends = POLES
for i in range(len(ends) - 1):
    xa, xb = ends[i], ends[i + 1]
    top = G + 11.6
    za = top - 0.35
    for yy, zz, sag, r_ in ((-1.1, za + 0.2, 0.55, 0.009), (0.0, top + 0.2, 0.55, 0.009), (1.1, za + 0.2, 0.55, 0.009)):
        wmb.tube(catenary((xa, PY + yy, zz), (xb, PY + yy, zz), sag), r_, 4, 'ext_wire', smooth=True)
    for zz, sag, r_ in ((top - 1.6, 0.8, 0.011), (top - 3.2, 0.95, 0.017), (G + 5.56, 0.75, 0.022), (G + 6.25, 0.7, 0.016)):
        wmb.tube(catenary((xa - 0.24 if zz > G + 7 else xa - 0.2, PY, zz), (xb - 0.24 if zz > G + 7 else xb - 0.2, PY, zz), sag), r_, 5, 'ext_wire')
# service drops: pole -> houses across (mast heads) and one across the street to our eave
for hx, hy, hz in ((-8.0, FRONT + 0.3, G + 5.6), (1.6, FRONT + 0.5, G + 5.6), (21.0, FRONT + 0.3, G + 5.6), (-24.0, FRONT + 0.3, G + 5.4)):
    px = min(POLES, key=lambda p: abs(p - hx))
    wmb.tube(catenary((px - 0.24, PY, G + 11.6 - 3.2), (hx, hy, hz), 0.5, 16), 0.012, 4, 'ext_wire')
wmb.tube(catenary((6.2 - 0.24, PY, G + 11.6 - 3.2), (11.5, FY + 0.3, 3.35), 0.9, 24), 0.012, 4, 'ext_wire')
wmb.tube(catenary((6.2 - 0.2, PY, G + 5.56), (12.2, FY + 0.3, 2.9), 0.8, 24), 0.014, 4, 'ext_wire')
# far streets: plain poles + a couple of wires so the grid keeps going into the haze
for k in range(1, 4):
    yc = S0 + 75 * k + 6.0
    xs = [x for x in range(-200, 220, 38) if not (SIDE_X0 - 2 < x < SIDE_X1 + 2)]
    for x in xs:
        z0 = ground_z(yc)
        wmb.cyl((x, yc, z0), (x, yc, z0 + 11.0), 0.15, 0.11, 6, 'ext_pole')
        wmb.box((x - 0.05, yc - 1.2, z0 + 10.6), (x + 0.05, yc + 1.2, z0 + 10.7), 'ext_pole')
    for a, b in zip(xs, xs[1:]):
        if b - a > 40:
            continue
        z0 = ground_z(yc)
        for yy, zz in ((-1.1, 10.75), (1.1, 10.75), (0.0, 8.4)):
            wmb.tube(catenary((a, yc + yy, z0 + zz), (b, yc + yy, z0 + zz), 0.6, 10), 0.02, 3, 'ext_wire')
wmb.build('EXT_power_lines')


def build_hydrant(x, y):
    mb = MB()
    z = G
    mb.cyl((x, y, z - 0.05), (x, y, z + 0.06), 0.16, 0.16, 16, 'ext_hydrant')
    mb.cyl((x, y, z + 0.06), (x, y, z + 0.1), 0.2, 0.2, 16, 'ext_hydrant')        # breakaway flange
    for k in range(8):
        a = 2 * math.pi * k / 8
        mb.cyl((x + 0.17 * math.cos(a), y + 0.17 * math.sin(a), z + 0.1), (x + 0.17 * math.cos(a), y + 0.17 * math.sin(a), z + 0.125), 0.018, 0.018, 6, 'ext_galv')
    mb.cyl((x, y, z + 0.1), (x, y, z + 0.62), 0.125, 0.118, 18, 'ext_hydrant')
    mb.cyl((x, y, z + 0.62), (x, y, z + 0.66), 0.15, 0.15, 18, 'ext_hydrant')
    mb.tube([V((x, y, z + 0.66)), V((x, y, z + 0.72)), V((x, y, z + 0.77)), V((x, y, z + 0.8))], [0.14, 0.125, 0.09, 0.04], 18, 'ext_hydrant_cap', cap=True)
    mb.cyl((x, y, z + 0.8), (x, y, z + 0.85), 0.028, 0.02, 5, 'ext_hydrant_cap', smooth=False)    # pentagon op-nut
    # pumper nozzle (toward the street) + two hose nozzles, all with caps
    for d, r_, L in (((0, -1, 0), 0.07, 0.13), ((1, 0, 0), 0.045, 0.1), ((-1, 0, 0), 0.045, 0.1)):
        dv = V(d)
        p0 = V((x, y, z + 0.47)) + dv * 0.1
        mb.cyl(p0, p0 + dv * L, r_, r_, 14, 'ext_hydrant')
        mb.cyl(p0 + dv * L, p0 + dv * (L + 0.05), r_ + 0.012, r_ + 0.012, 14, 'ext_hydrant_cap')
        mb.cyl(p0 + dv * (L + 0.05), p0 + dv * (L + 0.07), 0.022, 0.022, 5, 'ext_hydrant_cap', smooth=False)
    # snow-marker flag on a spring rod
    mb.cyl((x + 0.08, y + 0.05, z + 0.63), (x + 0.1, y + 0.08, z + 1.7), 0.006, 0.005, 5, 'ext_galv')
    mb.poly([(x + 0.1, y + 0.08, z + 1.7), (x + 0.1, y + 0.08, z + 1.52), (x + 0.26, y + 0.1, z + 1.61)], 'ext_red_band')
    o = mb.build('EXT_fire_hydrant')
    bv = o.modifiers.new('bevel', 'BEVEL')
    bv.width, bv.segments, bv.limit_method = 0.004, 2, 'ANGLE'
    return o


build_hydrant(-2.6, 22.25)


def build_stop_sign(x, y, face=(1, 0, 0)):
    mb = MB()
    f = V(face).normalized()
    side = V((0, 0, 1)).cross(f).normalized()
    z0 = G
    zc = z0 + 2.25
    mb.cyl((x, y, z0 - 0.4), (x, y, zc + 0.5), 0.03, 0.03, 8, 'ext_galv')
    c = V((x, y, zc)) + f * 0.035

    def octo(r, off, mat):
        pts = [c + f * off + (side * math.cos(math.pi / 8 + k * math.pi / 4) + V((0, 0, 1)) * math.sin(math.pi / 8 + k * math.pi / 4)) * r for k in range(8)]
        mb.poly(pts, mat)
        return pts
    back = [c - f * 0.004 + (side * math.cos(math.pi / 8 + k * math.pi / 4) + V((0, 0, 1)) * math.sin(math.pi / 8 + k * math.pi / 4)) * 0.375 for k in range(8)]
    mb.poly(list(reversed(back)), 'ext_galv')
    octo(0.375, 0.0, 'ext_sign_white')
    octo(0.35, 0.001, 'ext_sign_red')
    # legend "STOP" (block strokes)
    def stroke(u0, v0, u1, v1):
        a = c + f * 0.002 + side * u0 + V((0, 0, v0))
        b = c + f * 0.002 + side * u1 + V((0, 0, v0))
        cc = c + f * 0.002 + side * u1 + V((0, 0, v1))
        d = c + f * 0.002 + side * u0 + V((0, 0, v1))
        mb.poly([a, b, cc, d], 'ext_sign_white')
    lw, hh, t = 0.1, 0.1, 0.022
    xs0 = -0.235
    # S
    for v0 in (-hh, -t / 2, hh - t):
        stroke(xs0, v0, xs0 + lw, v0 + t)
    stroke(xs0, 0, xs0 + t, hh)
    stroke(xs0 + lw - t, -hh, xs0 + lw, 0)
    # T
    x1 = xs0 + lw + 0.025
    stroke(x1, hh - t, x1 + lw, hh)
    stroke(x1 + lw / 2 - t / 2, -hh, x1 + lw / 2 + t / 2, hh)
    # O
    x2 = x1 + lw + 0.025
    stroke(x2, -hh, x2 + lw, -hh + t)
    stroke(x2, hh - t, x2 + lw, hh)
    stroke(x2, -hh, x2 + t, hh)
    stroke(x2 + lw - t, -hh, x2 + lw, hh)
    # P
    x3 = x2 + lw + 0.025
    stroke(x3, -hh, x3 + t, hh)
    stroke(x3, hh - t, x3 + lw, hh)
    stroke(x3, -t / 2, x3 + lw, t / 2)
    stroke(x3 + lw - t, 0, x3 + lw, hh)
    # street-name blades on top
    for k, d in enumerate((f, side)):
        s2 = d.cross(V((0, 0, 1)))
        cz = zc + 0.55 + k * 0.17
        mb.obox(V((x, y, cz)), s2 * 0.45, d * 0.004, V((0, 0, 0.075)), 'ext_bin_blue' if False else 'ext_shutter')
        mb.obox(V((x, y, cz)) + d * 0.0045, s2 * 0.43, d * 0.0005, V((0, 0, 0.06)), 'ext_bin_green')
    return mb.build('EXT_stop_sign')


build_stop_sign(SIDE_X1 - 1.0, 22.6, (1, 0, 0))


def build_mailbox(x, y):
    """Community mailbox (CMB) on a concrete pad: steel cabinet with a sloped top and door grid."""
    mb = MB()
    z = G
    mb.box((x - 0.8, y - 0.55, z - 0.15), (x + 0.8, y + 0.55, z + 0.05), 'ext_concrete')
    W, D, H = 1.25, 0.55, 1.45
    mb.box((x - W / 2 + 0.06, y - D / 2 + 0.06, z + 0.05), (x + W / 2 - 0.06, y + D / 2 - 0.06, z + 0.22), 'ext_mailbox')
    mb.box((x - W / 2, y - D / 2, z + 0.22), (x + W / 2, y + D / 2, z + H), 'ext_mailbox')
    mb.poly([(x - W / 2 - 0.03, y - D / 2 - 0.04, z + H), (x + W / 2 + 0.03, y - D / 2 - 0.04, z + H),
             (x + W / 2 + 0.03, y + D / 2 + 0.04, z + H + 0.08), (x - W / 2 - 0.03, y + D / 2 + 0.04, z + H + 0.08)], 'ext_mailbox')
    mb.box((x - W / 2 - 0.03, y - D / 2 - 0.04, z + H - 0.03), (x + W / 2 + 0.03, y - D / 2 - 0.02, z + H), 'ext_mailbox')
    # door grid on the street side (-y) and a thin red band
    for i in range(4):
        for j in range(5):
            u0 = x - W / 2 + 0.06 + i * (W - 0.12) / 4
            v0 = z + 0.35 + j * (H - 0.5) / 5
            mb.box((u0 + 0.008, y - D / 2 - 0.006, v0 + 0.008), (u0 + (W - 0.12) / 4 - 0.008, y - D / 2, v0 + (H - 0.5) / 5 - 0.008), 'ext_mailbox')
            mb.box((u0 + 0.03, y - D / 2 - 0.012, v0 + 0.06), (u0 + 0.05, y - D / 2 - 0.006, v0 + 0.09), 'ext_dark')
    mb.box((x - W / 2 - 0.002, y - D / 2 - 0.004, z + H - 0.1), (x + W / 2 + 0.002, y + D / 2 + 0.004, z + H - 0.07), 'ext_red_band')
    o = mb.build('EXT_community_mailbox')
    bv = o.modifiers.new('bevel', 'BEVEL')
    bv.width, bv.segments, bv.limit_method = 0.006, 2, 'ANGLE'


build_mailbox(10.4, 22.9)


def cart(mb, x, y, rot, mat, W=0.6, D=0.72, H=1.05):
    c, s = math.cos(rot), math.sin(rot)

    def P(u, v, w):
        return (x + u * c - v * s, y + u * s + v * c, G + w)
    # tapered body
    b0 = [(-W / 2 + 0.04, -D / 2 + 0.05), (W / 2 - 0.04, -D / 2 + 0.05), (W / 2 - 0.04, D / 2 - 0.05), (-W / 2 + 0.04, D / 2 - 0.05)]
    b1 = [(-W / 2, -D / 2), (W / 2, -D / 2), (W / 2, D / 2), (-W / 2, D / 2)]
    verts = [P(u, v, 0.05) for u, v in b0] + [P(u, v, H - 0.05) for u, v in b1]
    mb.raw(verts, [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)], mat)
    lid = [P(u * 1.05, v * 1.05 - 0.02, H - 0.05) for u, v in b1] + [P(u * 1.05, v * 1.05 - 0.02, H) for u, v in b1]
    mb.raw(lid, [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)], mat)
    for u in (-W / 2 + 0.02, W / 2 - 0.02):
        mb.cyl(P(u, D / 2 - 0.02, 0.1), P(u + (0.05 if u > 0 else -0.05), D / 2 - 0.02, 0.1), 0.1, 0.1, 12, 'ext_rubber')
    mb.cyl(P(-W / 2 + 0.05, D / 2 + 0.03, H - 0.12), P(W / 2 - 0.05, D / 2 + 0.03, H - 0.12), 0.018, 0.018, 6, mat)


bmb = MB()
cart(bmb, 0.8, 23.3, 0.1, 'ext_bin_blue')
cart(bmb, 1.55, 23.35, -0.05, 'ext_bin_grey')
cart(bmb, 2.15, 23.4, 0.2, 'ext_bin_green', 0.42, 0.48, 0.78)
cart(bmb, -14.3, 23.2, -0.15, 'ext_bin_blue')
bmb.build('EXT_bins')

# =====================================================================================  cars
print('cars...')


def car(kind='sedan'):
    mb = MB()
    if kind == 'sedan':
        L, Wd, belt, roof, clr, fa, ra, wr = 4.75, 1.82, 0.93, 1.44, 0.2, 1.42, -1.38, 0.33
        cab = (-1.55, 0.78, -0.95, 0.12)       # belt rear, belt front, roof rear, roof front
    else:
        L, Wd, belt, roof, clr, fa, ra, wr = 4.6, 1.88, 1.07, 1.70, 0.27, 1.38, -1.32, 0.36
        cab = (-2.05, 0.95, -1.95, -0.05)
    hl = L / 2
    ar = wr + 0.05
    out = [(-hl + 0.08, clr + 0.08)]
    for cx in (ra, fa):
        out.append((cx - ar, clr + 0.08))
        for k in range(13):
            a = math.pi - math.pi * k / 12
            out.append((cx + ar * math.cos(a), wr + ar * math.sin(a) * 0.92))
        out.append((cx + ar, clr + 0.08))
    out += [(hl - 0.1, clr + 0.08), (hl, clr + 0.25), (hl + 0.02, 0.55 if kind == 'sedan' else 0.62), (hl - 0.08, belt - 0.14),
            (hl - 0.9, belt - 0.02), (cab[1], belt), (cab[0], belt + 0.01), (-hl + 0.12, belt - 0.02 if kind == 'sedan' else belt),
            (-hl, belt - 0.2), (-hl - 0.02, clr + 0.3)]
    n = len(out)
    y0, y1 = -Wd / 2, Wd / 2
    verts = [(x, y0, z) for x, z in out] + [(x, y1, z) for x, z in out]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    faces += [(i, n + i, n + (i + 1) % n, (i + 1) % n) for i in range(n)]
    mb.raw(verts, faces, 'ext_carpaint')
    # greenhouse: loft belt rectangle -> roof rectangle
    bi = 0.06
    rw = Wd / 2 - 0.2
    g = [(cab[0], -Wd / 2 + bi, belt), (cab[1], -Wd / 2 + bi, belt), (cab[1], Wd / 2 - bi, belt), (cab[0], Wd / 2 - bi, belt),
         (cab[2], -rw, roof), (cab[3], -rw, roof), (cab[3], rw, roof), (cab[2], rw, roof)]
    mb.raw(g, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], 'ext_car_glass')
    mb.raw([(p[0], p[1], p[2] + 0.004) for p in g[4:]], [(0, 1, 2, 3)], 'ext_carpaint')
    # pillars
    for s in (-1, 1):
        yb, yr = s * (Wd / 2 - bi + 0.005), s * (rw + 0.005)
        mb.beam((cab[1], yb, belt), (cab[3], yr, roof), 0.08, 0.03, 'ext_carpaint')
        mb.beam((cab[0], yb, belt), (cab[2], yr, roof), 0.16 if kind == 'sedan' else 0.1, 0.03, 'ext_carpaint')
        mx = (cab[0] + cab[1]) / 2 + 0.1
        mb.beam((mx, yb, belt), (mx + (cab[2] + cab[3] - cab[0] - cab[1]) / 2 * 0.45, yr, roof), 0.09, 0.03, 'ext_plastic_black')
        mb.box((cab[1] - 0.12, s * (Wd / 2 + 0.12) - 0.06, belt + 0.02), (cab[1] - 0.0, s * (Wd / 2 + 0.12) + 0.06, belt + 0.13), 'ext_carpaint')
        # door seam lines + handles
        for dx in (mx - 0.02, cab[1] - 0.05, -hl + 1.3 if kind == 'suv' else cab[0] + 0.05):
            mb.box((dx - 0.004, s * (Wd / 2 + 0.001) - 0.002, clr + 0.15), (dx + 0.004, s * (Wd / 2 + 0.001) + 0.002, belt - 0.02), 'ext_dark')
        for hx in (mx - 0.3, cab[1] - 0.3):
            mb.box((hx - 0.08, s * (Wd / 2) - 0.012, belt - 0.12), (hx + 0.08, s * (Wd / 2) + 0.012, belt - 0.09), 'ext_chrome')
    # wheels
    for cx in (ra, fa):
        for s in (-1, 1):
            yo = s * (Wd / 2 - 0.12)
            mb.cyl((cx, yo - 0.11, wr), (cx, yo + 0.11, wr), wr, wr, 20, 'ext_rubber')
            mb.cyl((cx, yo + s * 0.112, wr), (cx, yo + s * 0.116, wr), wr * 0.62, wr * 0.62, 20, 'ext_chrome')
            mb.box((cx - ar, s * (Wd / 2 - 0.02) - 0.2 * (s > 0), wr), (cx + ar, s * (Wd / 2 - 0.02) + 0.2 * (s < 0), wr + ar * 0.9), 'ext_dark') if False else None
        mb.box((cx - ar + 0.02, -Wd / 2 + 0.25, wr - 0.1), (cx + ar - 0.02, Wd / 2 - 0.25, wr + ar - 0.05), 'ext_dark')
    # lamps, grille, plates, bumpers
    for s in (-1, 1):
        mb.box((hl - 0.12, s * (Wd / 2 - 0.12) - 0.2, belt - 0.3), (hl + 0.005, s * (Wd / 2 - 0.12) + 0.2, belt - 0.18), 'ext_headlight')
        mb.box((-hl - 0.025, s * (Wd / 2 - 0.1) - 0.25, belt - 0.26), (-hl + 0.08, s * (Wd / 2 - 0.1) + 0.25, belt - 0.12), 'ext_taillight')
    mb.box((hl - 0.05, -0.45, 0.4), (hl + 0.025, 0.45, belt - 0.33), 'ext_plastic_black')
    mb.box((hl - 0.02, -0.26, 0.3), (hl + 0.03, 0.26, 0.45), 'ext_sign_white')
    mb.box((-hl - 0.04, -0.2, 0.5), (-hl + 0.0, 0.2, 0.66), 'ext_sign_white')
    mb.box((-hl - 0.05, -Wd / 2 + 0.05, clr + 0.1), (-hl + 0.3, Wd / 2 - 0.05, clr + 0.22), 'ext_plastic_black')
    o = mb.build('EXT_car_' + kind + '_src')
    bv = o.modifiers.new('bevel', 'BEVEL')
    bv.width, bv.segments, bv.limit_method = 0.03, 2, 'ANGLE'
    bv.angle_limit = math.radians(40)
    return o


c1 = car('sedan')
c1.name = 'EXT_car_sedan'
c1.location = (-9.0, CURB_B - 1.05, GUT + 0.07)
c1.rotation_euler = (0, 0, math.pi)
c1.color = (0.07, 0.085, 0.11, 1)
c2 = car('suv')
c2.name = 'EXT_car_suv'
_, (ga, gb) = lot_geom(0.0, 'C', True)
c2.location = ((ga + gb) / 2 - 1.2, FRONT - 5.2, G + 0.03)
c2.rotation_euler = (0, 0, math.pi / 2)
c2.color = (0.36, 0.36, 0.35, 1)

# =====================================================================================  finalize
for o in COL.objects:
    if o is not ROOT and o.parent is None:
        o.parent = ROOT
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
tris = 0
per = {}
for o in COL.objects:
    if o.type != 'MESH':
        continue
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ev.to_mesh_clear()
    tris += n
    key = o.data.name
    per[key] = per.get(key, 0) + n
print('OBJECTS', len(COL.objects), 'TRIS', tris)
for k, v in sorted(per.items(), key=lambda kv: -kv[1])[:25]:
    print('  %-28s %8d' % (k, v))
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('SAVED', OUT)
