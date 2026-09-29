"""
Room shell for room.blend: floor, walls, ceiling, back wall with a closed interior door, trim and small fixtures.

Headless build (factory startup, writes blender/scene/parts/roomshell.blend):
  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python blender/scripts/v2_roomshell.py

ROOM coordinates (Z-up metres), same space as room.blend. Output: collection NEW_roomshell under empty NEW_roomshell_root (at origin).
Replaces in room.blend: Mesh_3 (floor disc), Mesh_5..Mesh_10 (walls), trim_window_and_skirting (window frame + skirting).
Keeps: Mesh_11 (window glass, y=1.398), Mesh_4 (rug), NEW_curtains, all furniture.

Layout
  interior faces: left x=-2.08, right x=1.91, back y=-1.40, window wall y=1.30, floor z=0, ceiling z=2.72 (~8'11")
  window opening x -1.32..1.02, z 0.70..2.50 (unchanged), black vinyl frame + one operable sash around the kept glass
  interior door (30"x80", 2-panel shaker) in the left wall near the back, hinged on the back side, swings to the back wall
The floor keeps room.blend's oak material (Material_3, appended from room.blend) with the old disc's exact UV scale.
"""
import bpy, bmesh, math, random, os
from mathutils import Vector, Matrix

REPO = r"C:\Users\Vas\Documents\Github\Hub"
ROOM_BLEND = os.path.join(REPO, 'blender', 'scene', 'room.blend')
OUT = os.path.join(REPO, 'blender', 'scene', 'parts', 'roomshell.blend')

# ------------------------------------------------------------------ dimensions
X0, X1, Y0, Y1 = -2.08, 1.91, -1.40, 1.30        # interior wall faces
H = 2.72                                          # ceiling
T_SIDE, T_WIN, T_BACK = 0.08, 0.24, 0.12          # wall thicknesses (side/window match the old walls)
WX0, WX1, WZ0, WZ1 = -1.32, 1.02, 0.70, 2.50      # window rough opening (unchanged)

# door in the left wall (hinges toward the back wall)
JT = 0.019                                        # jamb board thickness
DJ_A, DJ_B = -1.299, -0.531                       # jamb inner faces (y)
D_HEAD = 2.035                                    # head jamb underside
RO_A, RO_B, RO_TOP = DJ_A - JT, DJ_B + JT, D_HEAD + JT   # rough opening in the wall
SLAB_W, SLAB_T = 0.762, 0.035
SLAB_Y0 = DJ_A + 0.002                            # hinge edge
SLAB_Y1 = SLAB_Y0 + SLAB_W                        # latch edge
SLAB_X1 = X0 - 0.002                              # room face of slab
SLAB_X0 = SLAB_X1 - SLAB_T
SLAB_Z0, SLAB_Z1 = 0.013, 2.032

CAS_W, CAS_REV = 0.064, 0.005                     # casing width, reveal

rnd = random.Random(1360)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

col = bpy.data.collections.new('NEW_roomshell')
scene.collection.children.link(col)
root = bpy.data.objects.new('NEW_roomshell_root', None)
root.empty_display_size = 0.3
col.objects.link(root)


# ------------------------------------------------------------------ helpers
def finish(name, bm, mats, smooth_angle=None, recalc=True, parent=root):
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if smooth_angle is not None:
        thr = math.radians(smooth_angle)
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) != 2 or e.calc_face_angle(0.0) > thr:
                e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    o.parent = parent
    return o


def bevel(o, w, seg=2, angle=40):
    b = o.modifiers.new('bevel', 'BEVEL')
    b.width = w
    b.segments = seg
    b.limit_method = 'ANGLE'
    b.angle_limit = math.radians(angle)
    b.harden_normals = False
    return b


def box(bm, x0, x1, y0, y1, z0, z1, mat=0):
    v = [bm.verts.new((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    fs = []
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        f = bm.faces.new([v[i] for i in q])
        f.material_index = mat
        fs.append(f)
    return fs


def sweep(bm, path, W, profile, ref, toward=True, closed=False, mat=0):
    """Sweep a closed 2D profile (a, b) along a polyline lying in the plane with normal W.
    a runs along the in-plane side normal N (mitred at corners), b along W.
    N points toward `ref` if toward else away from it."""
    W = Vector(W).normalized()
    P = [Vector(p) for p in path]
    n = len(P)
    segs = n if closed else n - 1
    segN = []
    for i in range(segs):
        d = (P[(i + 1) % n] - P[i]).normalized()
        segN.append(W.cross(d).normalized())
    mid = (P[0] + P[1]) / 2
    s = 1 if (Vector(ref) - mid).dot(segN[0]) > 0 else -1
    if not toward:
        s = -s
    segN = [N * s for N in segN]
    rings = []
    for i in range(n):
        if closed:
            Na, Nb = segN[(i - 1) % segs], segN[i % segs]
        else:
            Na = segN[i - 1] if i > 0 else segN[0]
            Nb = segN[i] if i < segs else segN[-1]
        m = (Na + Nb).normalized()
        k = 1.0 / m.dot(Na)
        rings.append([bm.verts.new(P[i] + m * (a * k) + W * b) for a, b in profile])
    npf = len(profile)
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for j in range(npf):
            f = bm.faces.new((r0[j], r0[(j + 1) % npf], r1[(j + 1) % npf], r1[j]))
            f.material_index = mat
    if not closed:
        for r in (rings[0], rings[-1]):
            f = bm.faces.new(r)
            f.material_index = mat


def lathe(bm, prof, c, segs=48, mat=0, cap_first=False, cap_last=False, mats=None):
    """Revolve (r, h) profile about the vertical axis through c. mats: optional per-segment material index."""
    c = Vector(c)
    rings = []
    for r, h in prof:
        if r < 1e-7:
            rings.append([bm.verts.new(c + Vector((0, 0, h)))])
        else:
            rings.append([bm.verts.new(c + Vector((r * math.cos(2 * math.pi * k / segs),
                                                     r * math.sin(2 * math.pi * k / segs), h))) for k in range(segs)])
    for i, (a, b) in enumerate(zip(rings, rings[1:])):
        mi = mats[i] if mats else mat
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(segs):
            k1 = (k + 1) % segs
            if len(a) == 1:
                f = bm.faces.new((a[0], b[k], b[k1]))
            elif len(b) == 1:
                f = bm.faces.new((a[k], a[k1], b[0]))
            else:
                f = bm.faces.new((a[k], a[k1], b[k1], b[k]))
            f.material_index = mi
    if cap_first and len(rings[0]) > 1:
        bm.faces.new(rings[0]).material_index = mat
    if cap_last and len(rings[-1]) > 1:
        bm.faces.new(rings[-1]).material_index = mat


def cyl(bm, c, axis, r, length, segs=24, mat=0):
    """Closed cylinder centred at c along unit axis."""
    axis = Vector(axis).normalized()
    t = axis.orthogonal().normalized()
    u = axis.cross(t)
    c = Vector(c)
    ends = []
    for s in (-0.5, 0.5):
        ends.append([bm.verts.new(c + axis * (s * length) + (t * math.cos(2 * math.pi * k / segs) + u * math.sin(2 * math.pi * k / segs)) * r)
                     for k in range(segs)])
    for k in range(segs):
        k1 = (k + 1) % segs
        bm.faces.new((ends[0][k], ends[0][k1], ends[1][k1], ends[1][k])).material_index = mat
    bm.faces.new(ends[0]).material_index = mat
    bm.faces.new(ends[1]).material_index = mat


def wall_frame(center, normal):
    """Matrix mapping local (u=right, v=up, w=out of wall) to world for a vertical wall with inward normal."""
    n = Vector(normal).normalized()
    up = Vector((0, 0, 1))
    r = up.cross(n)
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = r[i], up[i], n[i], center[i]
    return M


# ------------------------------------------------------------------ materials
def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    return m, nt, p, out


def rgba_mix(nt, blend='MIX'):
    mx = nt.nodes.new('ShaderNodeMix')
    mx.data_type = 'RGBA'
    mx.blend_type = blend
    A = next(s for s in mx.inputs if s.name == 'A' and s.type == 'RGBA')
    B = next(s for s in mx.inputs if s.name == 'B' and s.type == 'RGBA')
    O = next(s for s in mx.outputs if s.type == 'RGBA')
    return mx, mx.inputs[0], A, B, O


def paint(name, base, rough, rough_var=0.05, stipple=600.0, stipple_str=0.08, mottle=0.0,
          roller=False, metallic=0.0, coat=0.0, spec=0.5):
    """Painted / finished surface: fine stipple bump, low-frequency roughness drift, optional colour mottling."""
    m, nt, p, out = new_mat(name)
    p.inputs['Metallic'].default_value = metallic
    p.inputs['Specular IOR Level'].default_value = spec
    p.inputs['Coat Weight'].default_value = coat
    tc = nt.nodes.new('ShaderNodeTexCoord')
    vec = tc.outputs['Object']
    if roller:
        # roller passes run vertically: stretch the lap-mark noise along Z
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (1.0, 1.0, 0.18)
        nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
        lap_vec = mp.outputs['Vector']
    else:
        lap_vec = vec
    # roughness drift
    n2 = nt.nodes.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 3.5
    n2.inputs['Detail'].default_value = 4
    nt.links.new(lap_vec, n2.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs[1].default_value = 0.3
    mr.inputs[2].default_value = 0.7
    mr.inputs[3].default_value = rough - rough_var
    mr.inputs[4].default_value = rough + rough_var
    nt.links.new(n2.outputs[0], mr.inputs[0])
    nt.links.new(mr.outputs[0], p.inputs['Roughness'])
    # stipple bump (fine) + faint trowel/lap undulation (coarse)
    n1 = nt.nodes.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = stipple
    n1.inputs['Detail'].default_value = 3
    n1.inputs['Roughness'].default_value = 0.55
    nt.links.new(vec, n1.inputs['Vector'])
    n3 = nt.nodes.new('ShaderNodeTexNoise')
    n3.inputs['Scale'].default_value = stipple / 9
    n3.inputs['Detail'].default_value = 2
    nt.links.new(vec, n3.inputs['Vector'])
    add = nt.nodes.new('ShaderNodeMath')
    add.operation = 'MULTIPLY_ADD'
    add.inputs[1].default_value = 0.35
    nt.links.new(n3.outputs[0], add.inputs[0])
    nt.links.new(n1.outputs[0], add.inputs[2])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = stipple_str
    bump.inputs['Distance'].default_value = 0.0005
    nt.links.new(add.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    if mottle:
        mx, fac, A, B, O = rgba_mix(nt)
        A.default_value = (base[0] * (1 - mottle), base[1] * (1 - mottle), base[2] * (1 - mottle), 1)
        B.default_value = (base[0] * (1 + mottle), base[1] * (1 + mottle), base[2] * (1 + mottle), 1)
        n4 = nt.nodes.new('ShaderNodeTexNoise')
        n4.inputs['Scale'].default_value = 1.6
        n4.inputs['Detail'].default_value = 5
        nt.links.new(lap_vec, n4.inputs['Vector'])
        nt.links.new(n4.outputs[0], fac)
        nt.links.new(O, p.inputs['Base Color'])
    else:
        p.inputs['Base Color'].default_value = (*base, 1)
    return m


def simple(name, base, rough, metallic=0.0, emission=None, estr=0.0, coat=0.0, sss=0.0, transmission=0.0):
    m, nt, p, out = new_mat(name)
    p.inputs['Base Color'].default_value = (*base, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metallic
    p.inputs['Coat Weight'].default_value = coat
    if sss:
        p.inputs['Subsurface Weight'].default_value = sss
        p.inputs['Subsurface Radius'].default_value = (0.004, 0.004, 0.004)
        p.inputs['Subsurface Scale'].default_value = 1.0
    if transmission:
        p.inputs['Transmission Weight'].default_value = transmission
    if emission:
        p.inputs['Emission Color'].default_value = (*emission, 1)
        p.inputs['Emission Strength'].default_value = estr
    # micro roughness variation
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 180
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs[3].default_value = rough * 0.85
    mr.inputs[4].default_value = min(1.0, rough * 1.15)
    nt.links.new(nz.outputs[0], mr.inputs[0])
    nt.links.new(mr.outputs[0], p.inputs['Roughness'])
    return m


def decal(name, color, rough, opacity, stretch=(3.0, 25.0, 1.0), threshold=(0.45, 0.72), metallic=0.0):
    """Alpha decal on a small plane (generated coords): radial falloff x streaky noise."""
    m, nt, p, out = new_mat(name)
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metallic
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Location'].default_value = (-1.0, -1.0, 0.0)
    mp.inputs['Scale'].default_value = (2.0, 2.0, 1.0)
    nt.links.new(tc.outputs['UV'], mp.inputs['Vector'])
    gr = nt.nodes.new('ShaderNodeTexGradient')
    gr.gradient_type = 'SPHERICAL'
    nt.links.new(mp.outputs['Vector'], gr.inputs['Vector'])
    mp2 = nt.nodes.new('ShaderNodeMapping')
    mp2.inputs['Scale'].default_value = stretch
    nt.links.new(tc.outputs['UV'], mp2.inputs['Vector'])
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 3.0
    nz.inputs['Detail'].default_value = 8
    nz.inputs['Roughness'].default_value = 0.65
    nt.links.new(mp2.outputs['Vector'], nz.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs[1].default_value = threshold[0]
    mr.inputs[2].default_value = threshold[1]
    nt.links.new(nz.outputs[0], mr.inputs[0])
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    nt.links.new(gr.outputs[0], mul.inputs[0])
    nt.links.new(mr.outputs[0], mul.inputs[1])
    mul2 = nt.nodes.new('ShaderNodeMath')
    mul2.operation = 'MULTIPLY'
    mul2.inputs[1].default_value = opacity
    nt.links.new(mul.outputs[0], mul2.inputs[0])
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(mul2.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(p.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    return m


# wall paint keeps the hue/value of the old wall material (cool mid-grey) but as eggshell with roller stipple
M_WALL = paint('rs_wall_eggshell', (0.29, 0.297, 0.31), 0.52, rough_var=0.06, stipple=650, stipple_str=0.10,
               mottle=0.018, roller=True)
M_CEIL = paint('rs_ceiling_flat', (0.74, 0.74, 0.73), 0.88, rough_var=0.04, stipple=380, stipple_str=0.14, mottle=0.01)
M_TRIM = paint('rs_trim_semigloss', (0.80, 0.795, 0.77), 0.24, rough_var=0.04, stipple=1400, stipple_str=0.03)
M_FRAME = paint('rs_window_frame_black', (0.018, 0.019, 0.021), 0.42, rough_var=0.06, stipple=2500, stipple_str=0.02)
M_NICKEL = simple('rs_satin_nickel', (0.66, 0.64, 0.60), 0.28, metallic=1.0)
M_PLATE = simple('rs_decora_white', (0.80, 0.795, 0.765), 0.30)
M_SLOT = simple('rs_slot_black', (0.008, 0.008, 0.008), 0.6)
M_CORD = simple('rs_cord_black', (0.012, 0.012, 0.013), 0.45)
M_REG = simple('rs_register_enamel', (0.72, 0.71, 0.68), 0.38)
M_DUCT = simple('rs_duct_galv', (0.16, 0.16, 0.16), 0.5, metallic=0.85)
M_GLASS_DARK = simple('rs_thermo_glass', (0.006, 0.006, 0.007), 0.06, coat=0.6)
M_DIGIT = simple('rs_thermo_digits', (0.9, 0.95, 1.0), 0.4, emission=(0.85, 0.93, 1.0), estr=4.0)
M_LED = simple('rs_smoke_led', (0.05, 0.4, 0.05), 0.3, emission=(0.1, 1.0, 0.15), estr=6.0)
M_SMOKE = simple('rs_smoke_plastic', (0.78, 0.77, 0.73), 0.42)
M_DIFFUSER = simple('rs_ceiling_diffuser', (0.90, 0.90, 0.88), 0.35, sss=0.4,
                    emission=(1.0, 0.86, 0.70), estr=0.0)   # lights off by default; raise Emission Strength to turn on
M_FIXTURE = simple('rs_fixture_white', (0.82, 0.82, 0.81), 0.32)
M_NAILHOLE = simple('rs_nail_hole', (0.03, 0.03, 0.03), 0.8)
M_PATCH = paint('rs_wall_patch', (0.30, 0.306, 0.318), 0.72, rough_var=0.03, stipple=900, stipple_str=0.04)
M_SCUFF_WALL = decal('rs_scuff_rubber', (0.05, 0.05, 0.05), 0.7, 0.55)
M_SCUFF_FLOOR = decal('rs_scuff_floor', (0.36, 0.31, 0.26), 0.8, 0.45, stretch=(2.0, 30.0, 1.0), threshold=(0.5, 0.75))
M_SCUFF_BASE = decal('rs_scuff_baseboard', (0.09, 0.085, 0.08), 0.6, 0.35, stretch=(25.0, 3.0, 1.0))

# floor: the existing oak material from room.blend (packed images)
with bpy.data.libraries.load(ROOM_BLEND, link=False) as (src, dst):
    dst.materials = ['Material_3']
M_FLOOR = dst.materials[0]


# ------------------------------------------------------------------ floor (rectangle, register hole, door threshold)
REG_C = Vector((-1.95, 0.55))                      # floor register centre (long axis along Y)
REG_HX, REG_HY = 0.051, 0.127                      # half size of the 4"x10" duct hole


def build_floor():
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new('UVMap')
    xs = [X0, REG_C.x - REG_HX, REG_C.x + REG_HX, X1]
    ys = [Y0, REG_C.y - REG_HY, REG_C.y + REG_HY, Y1]
    V = [[bm.verts.new((x, y, 0.0)) for y in ys] for x in xs]
    for i in range(3):
        for j in range(3):
            if i == 1 and j == 1:
                continue
            bm.faces.new((V[i][j], V[i + 1][j], V[i + 1][j + 1], V[i][j + 1]))
    # threshold under the door, into the wall thickness
    a = bm.verts.new((X0 - T_SIDE, RO_A, 0.0))
    b = bm.verts.new((X0 - T_SIDE, RO_B, 0.0))
    c = bm.verts.new((X0, RO_B, 0.0))
    d = bm.verts.new((X0, RO_A, 0.0))
    bm.faces.new((a, d, c, b))
    for f in bm.faces:
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
        for l in f.loops:
            # identical mapping to the old 9 m disc: u = 0.5 + x/18, v = 0.5 - y/18
            l[uv].uv = (0.5 + l.vert.co.x / 18.0, 0.5 - l.vert.co.y / 18.0)
    # same object transform as Mesh_3 (rot X -90deg) so the material's object-space noise lines up
    R = Matrix.Rotation(-math.pi / 2, 4, 'X')
    bmesh.ops.transform(bm, matrix=R.inverted(), verts=bm.verts[:])
    o = finish('rs_floor', bm, [M_FLOOR], recalc=False)
    o.rotation_euler = (-math.pi / 2, 0, 0)
    return o


build_floor()


# ------------------------------------------------------------------ walls + ceiling
def build_walls():
    # window wall: four blocks around the opening
    bm = bmesh.new()
    xa, xb = X0 - T_SIDE, X1 + T_SIDE
    ya, yb = Y1, Y1 + T_WIN
    box(bm, xa, xb, ya, yb, 0.0, WZ0)
    box(bm, xa, xb, ya, yb, WZ1, H)
    box(bm, xa, WX0, ya, yb, WZ0, WZ1)
    box(bm, WX1, xb, ya, yb, WZ0, WZ1)
    finish('rs_wall_window', bm, [M_WALL])
    # left wall with the door rough opening
    bm = bmesh.new()
    box(bm, X0 - T_SIDE, X0, Y0, RO_A, 0.0, H)
    box(bm, X0 - T_SIDE, X0, RO_B, Y1, 0.0, H)
    box(bm, X0 - T_SIDE, X0, RO_A, RO_B, RO_TOP, H)
    finish('rs_wall_left', bm, [M_WALL])
    bm = bmesh.new()
    box(bm, X1, X1 + T_SIDE, Y0, Y1, 0.0, H)
    finish('rs_wall_right', bm, [M_WALL])
    bm = bmesh.new()
    box(bm, X0 - T_SIDE, X1 + T_SIDE, Y0 - T_BACK, Y0, 0.0, H)
    finish('rs_wall_back', bm, [M_WALL])
    bm = bmesh.new()
    box(bm, X0 - T_SIDE, X1 + T_SIDE, Y0 - T_BACK, Y1 + T_WIN, H, H + 0.12)
    finish('rs_ceiling', bm, [M_CEIL])
    # dim hallway stub behind the door so the undercut/gaps don't show sky
    bm = bmesh.new()
    fs = box(bm, X0 - T_SIDE - 1.1, X0 - T_SIDE, RO_A - 0.4, RO_B + 0.4, 0.0, H, mat=0)
    fs[4].material_index = 1                      # z-min face = floor
    for f in fs:
        f.normal_flip()                           # box built outward; flip to face inward
    finish('rs_hallway_stub', bm, [M_WALL, M_FLOOR], recalc=False)


build_walls()


# ------------------------------------------------------------------ profiles
def baseboard_profile():
    p = [(0.0, 0.0), (0.0125, 0.0), (0.0125, 0.096)]
    for k in range(1, 5):                          # cove
        t = k / 4 * math.pi / 2
        p.append((0.0125 - 0.004 * math.sin(t), 0.100 - 0.004 * math.cos(t)))
    p.append((0.0085, 0.1075))
    for k in range(1, 7):                          # round-over to the top
        t = k / 6 * math.pi / 2
        p.append((0.002 + 0.0065 * math.cos(t), 0.1075 + 0.0065 * math.sin(t)))
    p.append((0.0, 0.114))
    return p


def casing_profile():
    # a: 0 at the reveal edge -> 0.064 outer, b: thickness off the wall
    p = [(0.0, 0.0), (0.0, 0.0085)]
    for k in range(1, 5):                          # small bead on the inside edge
        t = k / 4 * math.pi
        p.append((0.003 - 0.003 * math.cos(t), 0.0085 + 0.003 * math.sin(t)))
    p += [(0.0075, 0.0112), (0.050, 0.0135)]
    for k in range(1, 7):                          # back band round-over
        t = k / 6 * math.pi
        p.append((0.057 - 0.007 * math.cos(t), 0.0135 + 0.0032 * math.sin(t) + 0.0003 * (k / 6)))
    p += [(0.0640, 0.0125), (0.0640, 0.0)]
    return p


def crown_profile():
    # a: out from the wall, b: down from the ceiling
    p = [(0.0, 0.058), (0.003, 0.058), (0.0032, 0.0535), (0.006, 0.0515)]
    for k in range(1, 9):                          # cove
        t = k / 8 * math.pi / 2
        p.append((0.040 - 0.034 * math.cos(t), 0.0515 - 0.042 * math.sin(t)))
    p += [(0.0405, 0.007), (0.0435, 0.006), (0.0435, 0.0), (0.0, 0.0)]
    return p


# ------------------------------------------------------------------ trim
def build_trim():
    ctr = (-0.08, -0.05, 0.5)
    # baseboard: continuous run from the latch-side door casing round to the hinge-side casing
    lat = DJ_B + CAS_REV + CAS_W                  # latch-side casing outer edge
    hin = DJ_A - CAS_REV - CAS_W                  # hinge casing outer edge
    bm = bmesh.new()
    sweep(bm, [(X0, lat, 0), (X0, Y1, 0), (X1, Y1, 0), (X1, Y0, 0), (X0, Y0, 0), (X0, hin, 0)],
          (0, 0, 1), baseboard_profile(), ref=ctr)
    finish('rs_baseboard', bm, [M_TRIM], smooth_angle=30)

    # crown moulding
    bm = bmesh.new()
    sweep(bm, [(X0, Y0, H), (X1, Y0, H), (X1, Y1, H), (X0, Y1, H)], (0, 0, -1), crown_profile(),
          ref=(-0.08, -0.05, H), closed=True)
    finish('rs_crown', bm, [M_TRIM], smooth_angle=30)

    # door jambs, stops, casing
    bm = bmesh.new()
    box(bm, X0 - T_SIDE, X0, RO_A, DJ_A, 0.0, D_HEAD + JT)
    box(bm, X0 - T_SIDE, X0, DJ_B, RO_B, 0.0, D_HEAD + JT)
    box(bm, X0 - T_SIDE, X0, DJ_A, DJ_B, D_HEAD, D_HEAD + JT)
    sx0, sx1 = SLAB_X0 - 0.012, SLAB_X0 - 0.0005   # stops on the hallway side of the slab
    box(bm, sx0, sx1, DJ_A, DJ_A + 0.032, 0.0, D_HEAD)
    box(bm, sx0, sx1, DJ_B - 0.032, DJ_B, 0.0, D_HEAD)
    box(bm, sx0, sx1, DJ_A, DJ_B, D_HEAD - 0.032, D_HEAD)
    o = finish('rs_door_jamb', bm, [M_TRIM])
    bevel(o, 0.0012)
    bm = bmesh.new()
    ca, cb, ct = DJ_A - CAS_REV, DJ_B + CAS_REV, D_HEAD + CAS_REV
    sweep(bm, [(X0, ca, 0), (X0, ca, ct), (X0, cb, ct), (X0, cb, 0)], (1, 0, 0), casing_profile(),
          ref=(X0, (DJ_A + DJ_B) / 2, 1.0), toward=False)
    finish('rs_door_casing', bm, [M_TRIM], smooth_angle=30)

    # window: jamb extensions (wall face -> frame), casing, stool, apron
    JX = 0.016
    wc = (-0.15, Y1, 1.6)
    bm = bmesh.new()
    sweep(bm, [(WX0, Y1, WZ0), (WX0, Y1, WZ1), (WX1, Y1, WZ1), (WX1, Y1, WZ0)], (0, 1, 0),
          [(0.0005, 0.0), (JX, 0.0), (JX, 0.080), (0.0005, 0.080)], ref=wc)
    o = finish('rs_window_jamb', bm, [M_TRIM])
    ins = JX - CAS_REV                               # casing inner edge sits 5 mm back on the jamb edge
    bm = bmesh.new()
    sweep(bm, [(WX0 + ins, Y1, WZ0), (WX0 + ins, Y1, WZ1 - ins), (WX1 - ins, Y1, WZ1 - ins), (WX1 - ins, Y1, WZ0)],
          (0, -1, 0), casing_profile(), ref=wc, toward=False)
    finish('rs_window_casing', bm, [M_TRIM], smooth_angle=30)
    cx0, cx1 = WX0 + ins - CAS_W, WX1 - ins + CAS_W      # casing outer edges
    bm = bmesh.new()
    box(bm, cx0 - 0.016, cx1 + 0.016, Y1 - 0.028, Y1 + 0.080, WZ0 - 0.019, WZ0)
    o = finish('rs_window_stool', bm, [M_TRIM])
    bevel(o, 0.004, seg=4, angle=60)
    bm = bmesh.new()
    sweep(bm, [(cx0, Y1, WZ0 - 0.019), (cx1, Y1, WZ0 - 0.019)], (0, -1, 0), casing_profile(),
          ref=(0, Y1, 0.0), toward=True)
    finish('rs_window_apron', bm, [M_TRIM], smooth_angle=30)


build_trim()


# ------------------------------------------------------------------ window frame + sash + hardware (kept glass Mesh_11 at y=1.398)
def build_window():
    wc = (-0.15, Y1, 1.6)
    rect = [(WX0, Y1, WZ0), (WX0, Y1, WZ1), (WX1, Y1, WZ1), (WX1, Y1, WZ0)]
    frame = [(0.0005, 0.080), (0.026, 0.080), (0.030, 0.0835), (0.030, 0.146), (0.020, 0.150), (0.0005, 0.150)]
    bm = bmesh.new()
    sweep(bm, rect, (0, 1, 0), frame, ref=wc, closed=True)
    finish('rs_window_frame', bm, [M_FRAME], smooth_angle=30)
    sash = [(0.031, 0.0875), (0.034, 0.0845), (0.064, 0.0845), (0.069, 0.0865), (0.0715, 0.0900),
            (0.0715, 0.0955), (0.0790, 0.0962), (0.0805, 0.0972), (0.0805, 0.0990), (0.074, 0.1045),
            (0.070, 0.1360), (0.066, 0.1395), (0.034, 0.1395), (0.031, 0.1365)]
    bm = bmesh.new()
    sweep(bm, rect, (0, 1, 0), sash, ref=wc, closed=True)
    finish('rs_window_sash', bm, [M_FRAME], smooth_angle=30)

    # hardware: folding crank operator on the sill (left of the lamp), two cam locks on the sash bottom rail
    bm = bmesh.new()
    ox, oy, oz = -0.86, Y1 + 0.062, WZ0            # operator housing sits on the stool, against the frame
    box(bm, ox - 0.045, ox + 0.045, oy - 0.016, oy + 0.016, oz, oz + 0.026)
    o = finish('rs_window_operator', bm, [M_FRAME])
    bevel(o, 0.006, seg=4, angle=60)
    bm = bmesh.new()
    cyl(bm, (ox + 0.012, oy - 0.024, oz + 0.014), (0, 1, 0), 0.0075, 0.018, segs=20)       # spline hub
    # folded crank arm lying along the housing, knob at the end
    box(bm, ox - 0.058, ox + 0.018, oy - 0.040, oy - 0.030, oz + 0.008, oz + 0.020)
    cyl(bm, (ox - 0.052, oy - 0.048, oz + 0.014), (0, 1, 0), 0.0065, 0.022, segs=20)
    o = finish('rs_window_crank', bm, [M_FRAME])
    bevel(o, 0.0025, seg=3, angle=60)
    bm = bmesh.new()
    for lx in (-0.42, 0.55):
        box(bm, lx - 0.028, lx + 0.028, Y1 + 0.071, Y1 + 0.0845, WZ0 + 0.041, WZ0 + 0.063)   # lock body on bottom rail
        box(bm, lx - 0.004, lx + 0.040, Y1 + 0.064, Y1 + 0.072, WZ0 + 0.052, WZ0 + 0.060)    # lever
    o = finish('rs_window_locks', bm, [M_FRAME])
    bevel(o, 0.002, seg=3, angle=60)


build_window()


# ------------------------------------------------------------------ door slab (2-panel shaker), hinges, lever, stop
def build_door():
    bm = bmesh.new()
    us = [0.0, 0.115, SLAB_W - 0.115, SLAB_W]
    zs = [SLAB_Z0, 0.213, 0.85, 1.05, 1.917, SLAB_Z1]
    xf, xb = SLAB_X1, SLAB_X0
    F = [[bm.verts.new((xf, SLAB_Y0 + u, z)) for z in zs] for u in us]
    cells = {}
    for i in range(3):
        for j in range(5):
            cells[(i, j)] = bm.faces.new((F[i][j], F[i][j + 1], F[i + 1][j + 1], F[i + 1][j]))
    B = {(u, z): bm.verts.new((xb, SLAB_Y0 + us[u], zs[z])) for u in (0, 3) for z in (0, 5)}
    bm.faces.new((B[(0, 0)], B[(3, 0)], B[(3, 5)], B[(0, 5)]))
    bm.faces.new([F[i][0] for i in range(4)] + [B[(3, 0)], B[(0, 0)]])
    bm.faces.new([F[i][5] for i in range(4)] + [B[(3, 5)], B[(0, 5)]])
    bm.faces.new([F[0][j] for j in range(6)] + [B[(0, 5)], B[(0, 0)]])
    bm.faces.new([F[3][j] for j in range(6)] + [B[(3, 5)], B[(3, 0)]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for key in ((1, 1), (1, 3)):
        r = bmesh.ops.inset_individual(bm, faces=[cells[key]], thickness=0.003, depth=-0.0055)
        bmesh.ops.inset_individual(bm, faces=[cells[key]], thickness=0.007, depth=-0.0012)
    o = finish('rs_door_slab', bm, [M_TRIM], recalc=False)
    bevel(o, 0.0015, seg=2, angle=35)

    # hinges: knuckles proud of the room face on the back (hinge) side
    bm = bmesh.new()
    kx, ky = X0 - 0.0005, DJ_A + 0.0005
    for hz in (0.28, 1.02, 1.80):
        cyl(bm, (kx, ky, hz), (0, 0, 1), 0.0064, 0.089, segs=20)
        for s in (-1, 1):
            cyl(bm, (kx, ky, hz + s * 0.0475), (0, 0, 1), 0.0052, 0.006, segs=20)
    o = finish('rs_door_hinges', bm, [M_NICKEL])
    bevel(o, 0.0008, seg=2, angle=50)

    # lever set, 60 mm backset, 36" to centre
    lz, ly = 0.914, SLAB_Y1 - 0.0603
    bm = bmesh.new()
    lathe(bm, [(0.0, 0.0), (0.030, 0.0), (0.031, 0.002), (0.030, 0.007), (0.026, 0.0095), (0.012, 0.0105),
               (0.0095, 0.012), (0.0085, 0.045), (0.0, 0.046)], (0, 0, 0), segs=32)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((xf, ly, lz)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'),
                        verts=bm.verts[:])
    # lever arm returning toward the hinge side
    arm = bmesh.new()
    box(arm, xf + 0.030, xf + 0.046, ly - 0.118, ly + 0.006, lz - 0.0085, lz + 0.0085)
    me = bpy.data.meshes.new('tmp_arm')
    arm.to_mesh(me)
    arm.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    o = finish('rs_door_lever', bm, [M_NICKEL], smooth_angle=40)
    bevel(o, 0.0035, seg=3, angle=50)

    # spring door stop on the back wall baseboard where the door lands
    bm = bmesh.new()
    sx, sz = -1.42, 0.075
    cyl(bm, (sx, Y0 + 0.004, sz), (0, 1, 0), 0.009, 0.008, segs=20)
    cyl(bm, (sx, Y0 + 0.045, sz), (0, 1, 0), 0.0022, 0.075, segs=12)
    o = finish('rs_door_stop', bm, [M_NICKEL], smooth_angle=40)
    bm = bmesh.new()
    cyl(bm, (sx, Y0 + 0.088, sz), (0, 1, 0), 0.0065, 0.014, segs=20)
    o2 = finish('rs_door_stop_tip', bm, [M_PLATE], smooth_angle=40)
    bevel(o2, 0.002, seg=3, angle=50)


build_door()


# ------------------------------------------------------------------ Decora devices
def decora(name, center, normal, kind='duplex', plug=False):
    M = wall_frame(center, normal)
    bm = bmesh.new()
    # plate: 2.75" x 4.5" with pillowed edge
    box(bm, -0.0349, 0.0349, -0.0572, 0.0572, 0.0, 0.0048, mat=0)
    # screws (painted to match) with slots
    for sv in (-0.0485, 0.0485):
        cyl(bm, (0, sv, 0.0052), (0, 0, 1), 0.0034, 0.0012, segs=16, mat=0)
    me_plate = bm
    for v in me_plate.verts:
        v.co = M @ v.co
    o = finish(name + '_plate', me_plate, [M_PLATE], smooth_angle=40)
    bevel(o, 0.0018, seg=3, angle=50)
    bm = bmesh.new()
    box(bm, -0.0168, 0.0168, -0.0335, 0.0335, 0.0030, 0.0062, mat=0)          # device face through the opening
    box(bm, -0.0173, 0.0173, -0.0340, 0.0340, 0.0030, 0.0050, mat=1)          # hairline gap around it
    for sv in (-0.0485, 0.0485):
        box(bm, -0.0026, 0.0026, sv - 0.0003, sv + 0.0003, 0.0060, 0.0066, mat=1)  # screw slot
    if kind == 'duplex':
        for vc in (0.019, -0.019):
            box(bm, -0.0072, -0.0052, vc - 0.0005, vc + 0.0075, 0.0060, 0.0064, mat=1)   # neutral (taller)
            box(bm, 0.0052, 0.0072, vc - 0.0002, vc + 0.0068, 0.0060, 0.0064, mat=1)     # hot
            cyl(bm, (0, vc - 0.0085, 0.0062), (0, 0, 1), 0.0023, 0.0004, segs=16, mat=1)  # ground
            box(bm, -0.0023, 0.0023, vc - 0.0085, vc - 0.0062, 0.0060, 0.0064, mat=1)
        # tiny "TR" tamper-resistant embossing stand-in
        box(bm, -0.0016, 0.0016, -0.0006, 0.0006, 0.0060, 0.00635, mat=1)
    elif kind == 'switch':
        # rocker paddle: pressed at the bottom (ON), top edge proud
        rk = bmesh.new()
        box(rk, -0.0158, 0.0158, -0.0322, 0.0322, 0.0, 0.0022)
        for v in rk.verts:
            v.co.z += 0.0062 + (v.co.y + 0.0322) / 0.0644 * 0.0016 - 0.0006
        me = bpy.data.meshes.new('tmp')
        rk.to_mesh(me)
        rk.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    for v in bm.verts:
        v.co = M @ v.co
    o = finish(name + '_device', bm, [M_PLATE, M_SLOT])
    bevel(o, 0.0006, seg=2, angle=50)
    if plug:
        vc = -0.019
        bm = bmesh.new()
        box(bm, -0.0125, 0.0125, vc - 0.021, vc + 0.012, 0.0064, 0.0270)
        for v in bm.verts:
            v.co = M @ v.co
        o = finish(name + '_plug', bm, [M_CORD])
        bevel(o, 0.004, seg=3, angle=50)
        return M
    return M


def build_devices():
    # window wall, right of the window: power bar cord from NEW_cables ends at (1.03, 1.2773, 0.0034)
    M = decora('rs_outlet_window', (1.10, Y1, 0.30), (0, -1, 0), plug=True)
    pts = [M @ Vector((0.0, -0.036, 0.018)), M @ Vector((0.0, -0.050, 0.020)), Vector((1.098, 1.2776, 0.20)),
           Vector((1.090, 1.2775, 0.10)), Vector((1.072, 1.2774, 0.030)), Vector((1.050, 1.2773, 0.006)),
           Vector((1.026, 1.2773, 0.0034))]
    cu = bpy.data.curves.new('rs_plug_cord', 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.0034
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.resolution_u = 8
    tmp = bpy.data.objects.new('tmp_cord', cu)
    scene.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.name = 'rs_plug_cord'
    me.materials.append(M_CORD)
    o = bpy.data.objects.new('rs_plug_cord', me)
    col.objects.link(o)
    o.parent = root
    decora('rs_outlet_left', (X0, 0.95, 0.30), (1, 0, 0))
    decora('rs_outlet_right', (X1, -0.72, 0.30), (-1, 0, 0))
    decora('rs_switch_door', (X0, DJ_B + CAS_REV + CAS_W + 0.075, 1.22), (1, 0, 0), kind='switch')


build_devices()


# ------------------------------------------------------------------ thermostat
def build_thermostat():
    M = wall_frame((X0, 0.10, 1.52), (1, 0, 0))
    bm = bmesh.new()
    box(bm, -0.046, 0.046, -0.058, 0.058, 0.0, 0.021)
    for v in bm.verts:
        v.co = M @ v.co
    o = finish('rs_thermostat_body', bm, [M_PLATE])
    bevel(o, 0.008, seg=5, angle=50)
    bm = bmesh.new()
    box(bm, -0.034, 0.034, -0.010, 0.040, 0.020, 0.0218)
    for v in bm.verts:
        v.co = M @ v.co
    o = finish('rs_thermostat_screen', bm, [M_GLASS_DARK])
    bevel(o, 0.002, seg=2, angle=50)
    # readout "21" in °C with a small set-point line
    cu = bpy.data.curves.new('rs_thermo_txt', 'FONT')
    cu.body = '21°'
    cu.size = 0.026
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    tmp = bpy.data.objects.new('tmp_txt', cu)
    scene.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.transform(M @ Matrix.Translation((0.0, 0.017, 0.0221)))
    me.name = 'rs_thermostat_digits'
    me.materials.append(M_DIGIT)
    o = bpy.data.objects.new('rs_thermostat_digits', me)
    col.objects.link(o)
    o.parent = root
    # two touch buttons below the screen
    bm = bmesh.new()
    for bu in (-0.016, 0.016):
        cyl(bm, (bu, -0.036, 0.0215), (0, 0, 1), 0.0055, 0.0012, segs=20)
    for v in bm.verts:
        v.co = M @ v.co
    finish('rs_thermostat_buttons', bm, [M_SLOT], smooth_angle=40)


build_thermostat()


# ------------------------------------------------------------------ ceiling fixtures
def build_ceiling_fixtures():
    # 13" flush-mount LED (lights off by default)
    c = (-0.085, -0.05, H)
    bm = bmesh.new()
    lathe(bm, [(0.0, -0.001), (0.150, -0.001), (0.166, -0.003), (0.168, -0.008), (0.165, -0.013),
               (0.158, -0.0145)], c, segs=64, cap_first=False, cap_last=True)
    finish('rs_ceiling_light_base', bm, [M_FIXTURE], smooth_angle=40)
    bm = bmesh.new()
    prof = []
    for k in range(0, 13):
        t = k / 12
        r = 0.156 * (1 - t) + 0.0 * t
        rr = r / 0.156
        prof.append((r, -0.0140 - 0.042 * (1 - rr ** 3) ** 0.6))
    lathe(bm, prof, c, segs=64, cap_first=True)
    o = finish('rs_ceiling_light_diffuser', bm, [M_DIFFUSER], smooth_angle=60)
    o['note'] = 'Set material rs_ceiling_diffuser Emission Strength ~6-10 to switch the light on'

    # smoke alarm near the door
    c = (-1.40, -0.72, H)
    bm = bmesh.new()
    prof = [(0.070, 0.0), (0.070, -0.012), (0.067, -0.015), (0.062, -0.017), (0.061, -0.019),
            (0.061, -0.027), (0.058, -0.030), (0.050, -0.034), (0.036, -0.038), (0.018, -0.040), (0.0, -0.0405)]
    mats = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0]
    lathe(bm, prof, c, segs=48, mats=mats)
    o = finish('rs_smoke_alarm', bm, [M_SMOKE, M_SLOT], smooth_angle=35)
    bm = bmesh.new()
    for k in range(24):                                  # ribs across the vent band
        a = 2 * math.pi * k / 24
        p = Vector(c) + Vector((math.cos(a) * 0.0615, math.sin(a) * 0.0615, -0.023))
        b = bmesh.new()
        box(b, -0.0015, 0.0015, -0.003, 0.003, -0.0045, 0.0045)
        me = bpy.data.meshes.new('tmp')
        b.to_mesh(me)
        b.free()
        me.transform(Matrix.Translation(p) @ Matrix.Rotation(a, 4, 'Z'))
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    cyl(bm, (c[0], c[1], H - 0.0415), (0, 0, 1), 0.013, 0.002, segs=32)      # test button
    finish('rs_smoke_alarm_ribs', bm, [M_SMOKE], smooth_angle=40)
    bm = bmesh.new()
    cyl(bm, (c[0] + 0.030, c[1], H - 0.0372), (0, 0, 1), 0.0016, 0.0012, segs=12)
    finish('rs_smoke_alarm_led', bm, [M_LED])


build_ceiling_fixtures()


# ------------------------------------------------------------------ floor register (4"x10", louvered, with damper tab)
def build_register():
    cx, cy = REG_C
    bm = bmesh.new()
    rect = [(cx - REG_HX, cy - REG_HY, 0), (cx - REG_HX, cy + REG_HY, 0), (cx + REG_HX, cy + REG_HY, 0),
            (cx + REG_HX, cy - REG_HY, 0)]
    prof = [(-0.0008, -0.040), (0.0, -0.040), (0.0, 0.0), (0.0215, 0.0), (0.0228, 0.0012), (0.0222, 0.0030),
            (0.0190, 0.0040), (0.0020, 0.0042), (-0.0008, 0.0030)]
    sweep(bm, rect, (0, 0, 1), prof, ref=(cx, cy, 0), toward=False, closed=True)
    finish('rs_register_frame', bm, [M_REG], smooth_angle=35)
    bm = bmesh.new()
    n = 7
    for k in range(n):
        x = cx - REG_HX + (k + 0.5) * (2 * REG_HX) / n
        b = bmesh.new()
        box(b, -0.0068, 0.0068, -REG_HY + 0.001, REG_HY - 0.001, -0.0006, 0.0006)
        me = bpy.data.meshes.new('tmp')
        b.to_mesh(me)
        b.free()
        me.transform(Matrix.Translation((x, cy, -0.006)) @ Matrix.Rotation(math.radians(38), 4, 'Y'))
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    for yy in (cy - 0.07, cy + 0.07):
        cyl(bm, (cx, yy, -0.008), (1, 0, 0), 0.0015, 2 * REG_HX, segs=10)
    box(bm, cx - 0.004, cx + 0.004, cy + REG_HY - 0.020, cy + REG_HY - 0.008, -0.010, 0.0065)   # damper tab
    o = finish('rs_register_louvers', bm, [M_REG])
    bevel(o, 0.0004, seg=1, angle=50)
    # duct boot below the floor (inward-facing, open top)
    bm = bmesh.new()
    fs = box(bm, cx - REG_HX, cx + REG_HX, cy - REG_HY, cy + REG_HY, -0.12, 0.0)
    bm.faces.remove(fs[5])                               # z-max face open
    for f in fs[:5]:
        f.normal_flip()
    finish('rs_register_boot', bm, [M_DUCT], recalc=False)


build_register()


# ------------------------------------------------------------------ imperfections
def small_disc(bm, c, normal, r, segs=12, off=0.0002):
    M = wall_frame(c, normal)
    vs = [bm.verts.new(M @ Vector((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs), off)))
          for k in range(segs)]
    bm.faces.new(vs)


def decal_plane(name, c, normal, w, h, mat, off=0.0003, rot=0.0):
    n = Vector(normal)
    bm = bmesh.new()
    if abs(n.z) > 0.9:                                  # floor decal
        M = Matrix.Translation(Vector(c) + Vector((0, 0, off))) @ Matrix.Rotation(rot, 4, 'Z')
        pts = [(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)]
    else:
        M = wall_frame(c, normal) @ Matrix.Translation((0, 0, off)) @ Matrix.Rotation(rot, 4, 'Z')
        pts = [(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)]
    vs = [bm.verts.new(M @ Vector(p)) for p in pts]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new('UVMap')
    for l, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        l[uv].uv = t
    return finish(name, bm, [mat], recalc=False)


def build_imperfections():
    bm = bmesh.new()
    # two nail holes from a picture that used to hang left of the thermostat, one stray hole on the right wall
    for y, z in ((0.44, 1.905), (0.462, 1.902)):
        small_disc(bm, (X0, y, z), (1, 0, 0), 0.0016)
    small_disc(bm, (X1, -0.30, 1.71), (-1, 0, 0), 0.0015)
    finish('rs_nail_holes', bm, [M_NAILHOLE], recalc=False)
    bm = bmesh.new()
    small_disc(bm, (X0, -0.02, 1.86), (1, 0, 0), 0.016, segs=20, off=0.0001)     # spackled + touched-up patch
    small_disc(bm, (X0, 0.451, 1.904), (1, 0, 0), 0.0045, segs=16, off=0.0001)   # chipped paint halo round the holes
    finish('rs_wall_patches', bm, [M_PATCH], recalc=False)
    # chair armrest scuff on the back wall, caster scuffs where the chair rolls off the rug, shoe scuff on baseboard
    decal_plane('rs_scuff_backwall', (0.42, Y0, 0.63), (0, 1, 0), 0.16, 0.05, M_SCUFF_WALL, rot=math.radians(-4))
    decal_plane('rs_scuff_floor', (0.40, -1.10, 0.0), (0, 0, 1), 0.70, 0.30, M_SCUFF_FLOOR, rot=math.radians(90))
    decal_plane('rs_scuff_baseboard', (X0 + 0.0125, -0.30, 0.05), (1, 0, 0), 0.10, 0.035, M_SCUFF_BASE, off=0.0004)


build_imperfections()


# ------------------------------------------------------------------ report + save
dg = bpy.context.evaluated_depsgraph_get()
tris = 0
for o in col.objects:
    if o.type == 'MESH':
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        o.evaluated_get(dg).to_mesh_clear()
print('ROOMSHELL objects', len(col.objects), 'tris', tris)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('saved', OUT)
