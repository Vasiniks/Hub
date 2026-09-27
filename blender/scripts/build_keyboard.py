"""
TKL keyboard.

The whole board is built here, layout included, because the thing that makes a keyboard read
as a keyboard is not the case — it is 87 keycaps that are each genuinely the right shape for
the row they sit in. The previous version instanced one rounded box and scaled it in x, which
stretches the corner fillets and the dish and makes a spacebar look like a smeared alpha key.

Each cap is lofted from a rounded-rect outline with a *fixed* corner radius at any width, its
top plane sheared to the row's sculpt angle so the base still sits flat on the plate, and its
top surface dished cylindrically across x. Caps merge into two objects — alphas and modifiers
— so the whole field is two draw calls before the runtime's static merge even sees it.

The case gets the recess the old one only implied: the plate well is a boolean cut, so the
caps sit down inside a wall that catches a shadow along its inner edge.
"""
import bpy
import bmesh
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]

U = 0.01905                   # standard key pitch
GAP = 0.00105                 # air between adjacent caps
CAP_R = 0.0016                # corner radius, constant at every key width
CAP_H = 0.0098
BORDER_X = 0.0085             # case border beside the outermost key
BORDER_F = 0.0080             # in front of the bottom row
BORDER_B = 0.0105             # behind the function row
FN_GAP = 0.5 * U              # the break between the function row and the number row

# Front to back. The runtime used to tilt the whole board; the incline is modelled here now,
# as the flip-out feet that actually produce it.
ROWS = [
    # keys,                                                  sculpt°, lift
    ([1.25, 1.25, 1.25, 6.25, 1.25, 1.25, 1.25, 1.25, -0.25, 1, 1, 1], -7.0, 0.0016),
    ([2.25, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.75, -1.25, 1],             -4.0, 0.0006),
    ([1.75, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.25],                     0.0, 0.0000),
    ([1.5, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1.5, -0.25, 1, 1, 1],    6.0, 0.0016),
    ([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, -0.25, 1, 1, 1],        9.0, 0.0028),
    ([1, -1, 1, 1, 1, 1, -0.5, 1, 1, 1, 1, -0.5, 1, 1, 1, 1, -0.25, 1, 1, 1], 3.0, 0.0008),
]
UNITS = 18.25
KEY_W = UNITS * U
KEY_D = len(ROWS) * U + FN_GAP
CASE_W = KEY_W + BORDER_X * 2
CASE_D = KEY_D + BORDER_F + BORDER_B

WELL = 0.0052                 # how far the well floor sits below the case lip
PLATE_T = 0.0016
CASE_H = 0.0158               # case top surface above the desk, at the front
# The switch plate sits *on* the well floor, not in it. Putting it at the floor plane buried
# it under the boolean's own floor, and the gaps between keys then read case-white instead of
# plate-dark — which is most of what makes a field of keys legible from above.
FLOOR_Z = CASE_H - WELL
PLATE_Z = FLOOR_Z + PLATE_T

lib.reset()


# --------------------------------------------------------------------------- outline

N = 5                         # grid resolution across the dished top; odd, so there is a centre
RING = lib.ring_indices(N)


def ring_uv(scale=1.0):
    return [((2 * i / (N - 1) - 1) * scale, (2 * j / (N - 1) - 1) * scale) for i, j in RING]


def keycap(bm, cx, cy, w, h, angle_deg, dish):
    """
    One sculpted cap, appended into `bm` at (cx, cy).

    Three loops and a grid: base, the bottom of the rim chamfer, and the rim itself, whose
    outer ring *is* the boundary of the dished top grid. The top plane is sheared rather than
    rotated, so the cap still sits flat on the plate the way a real one does.
    """
    a = (w * U - GAP) / 2
    b = (U - GAP) / 2
    taper = 0.0019                       # walls lean in by this much over the cap's height
    rim = 0.0012
    at = max(a - taper, a * 0.55)
    bt = max(b - taper, b * 0.55)
    shear = math.tan(math.radians(angle_deg))
    dish_a = at

    def put(uv, ax, by, z, dished=False):
        x, y = lib.rounded(uv[0], uv[1], ax, by, CAP_R)
        if dished:
            t = min(1.0, abs(x) / dish_a) if dish_a > 1e-6 else 0.0
            z -= dish * (1.0 - t * t)
        return bm.verts.new((cx + x, cy + y, z + shear * y * (z / h)))

    base = [put(uv, a, b, 0.0) for uv in ring_uv()]
    low = [put(uv, at + rim * 0.55, bt + rim * 0.55, h - rim) for uv in ring_uv()]
    # The top grid: its outer ring is the cap's rim, its interior carries the dish.
    grid = {}
    for i in range(N):
        for j in range(N):
            u, v = 2 * i / (N - 1) - 1, 2 * j / (N - 1) - 1
            grid[(i, j)] = put((u, v), at, bt, h, dished=True)
    top = [grid[k] for k in RING]

    def bridge(lower, upper):
        n = len(lower)
        for i in range(n):
            bm.faces.new((lower[i], lower[(i + 1) % n], upper[(i + 1) % n], upper[i]))

    bridge(base, low)
    bridge(low, top)
    for i in range(N - 1):
        for j in range(N - 1):
            bm.faces.new((grid[(i, j)], grid[(i + 1, j)], grid[(i + 1, j + 1)], grid[(i, j + 1)]))


def build_caps():
    """Lay out the field. Returns (alpha_object, modifier_object, stabilised_key_positions)."""
    bms = {'alpha': bmesh.new(), 'mod': bmesh.new()}
    stabs = []
    for r, (keys, angle, lift) in enumerate(ROWS):
        # Row 0 is the bottom row, nearest the user (-Y here, +Z in the room).
        y = -KEY_D / 2 + (r + 0.5) * U + (FN_GAP if r == len(ROWS) - 1 else 0.0)
        cursor = -KEY_W / 2
        for w in keys:
            if w < 0:
                cursor += -w * U
                continue
            cx = cursor + w * U / 2
            # Function row and every non-1u key are the darker set, as on a two-tone board.
            key = 'mod' if (w != 1 or r == len(ROWS) - 1) else 'alpha'
            keycap(bms[key], cx, y, w, CAP_H, angle, 0.0011 if w < 3 else 0.0007)
            if w >= 1.75:
                stabs.append((cx, y, w, angle))
            cursor += w * U
    out = []
    for name in ('alpha', 'mod'):
        me = bpy.data.meshes.new(f'keyboard_{name}')
        bms[name].to_mesh(me)
        bms[name].free()
        obj = bpy.data.objects.new(f'keyboard_{name}', me)
        bpy.context.collection.objects.link(obj)
        obj.location = (0, 0, PLATE_Z)
        lib.apply_transforms(obj)
        lib.shade_auto(obj, 38)
        out.append(obj)
    return out[0], out[1], stabs


# --------------------------------------------------------------------------- case

def cube(name, size, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    lib.apply_transforms(o)
    return o


def cut(target, cutters):
    for c in cutters:
        mod = target.modifiers.new('cut', 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = c
        mod.solver = 'EXACT'
    lib.apply_modifiers(target)
    lib.drop(cutters)


case = cube('kb_case', (CASE_W, CASE_D, CASE_H), (0, 0, CASE_H / 2))
# The plate well: a real recess, so the caps sit inside a wall rather than on a slab.
well = cube('kb_well', (KEY_W + 0.0026, KEY_D + 0.0026, WELL * 2), (0, 0, FLOOR_Z + WELL))
# A chamfer along the front lip, where a case is thinnest and catches the most light.
chamf = cube('kb_chamf', (CASE_W * 1.1, 0.010, 0.010),
             (0, -CASE_D / 2, CASE_H), rot=(math.radians(34), 0, 0))
# USB-C recess, centred at the back.
port = cube('kb_port', (0.0094, 0.008, 0.0034), (0, CASE_D / 2, FLOOR_Z - 0.0035))
# Two-piece read: a thin groove line right around the case sides.
groove = cube('kb_groove', (CASE_W + 0.002, CASE_D + 0.002, 0.0012), (0, 0, 0.0045))
cut(case, [well, chamf, port, groove])
lib.bevel(case, width=0.0011, segments=2, angle_deg=38)
lib.apply_modifiers(case)
lib.shade_auto(case, 34)

plate = cube('kb_plate', (KEY_W + 0.0022, KEY_D + 0.0022, PLATE_T), (0, 0, FLOOR_Z + PLATE_T / 2))
base = cube('kb_base', (CASE_W - 0.0016, CASE_D - 0.0016, 0.0042), (0, 0, -0.0021))
lib.bevel(base, width=0.0012, segments=2)
lib.apply_modifiers(base)

feet = []
for s in (-1, 1):
    feet.append(cube('kb_foot', (0.024, 0.0075, 0.0038),
                     (s * (CASE_W / 2 - 0.022), -CASE_D / 2 + 0.014, -0.0040)))
    # Flip-out feet, deployed: they are what actually produces the typing incline.
    feet.append(cube('kb_riser', (0.030, 0.0085, 0.0118),
                     (s * (CASE_W / 2 - 0.030), CASE_D / 2 - 0.016, -0.0065)))
for f in feet:
    lib.bevel(f, width=0.0009, segments=2)
    lib.apply_modifiers(f)

caps_alpha, caps_mod, stabs = build_caps()

# Homing nubs on F and J (home row = ROWS[2], a 1.75u Caps followed by eleven 1u
# keys; F is the 4th 1u, J the 7th). Tiny bars on the dished top, only visible in
# close-up — which is exactly where a keyboard is examined.
_home_y = -KEY_D / 2 + 2.5 * U
for _n, _k in enumerate((3.5, 6.5)):
    _cx = -KEY_W / 2 + 1.75 * U + _k * U
    _nub = cube(f'kb_nub{_n}', (0.0035, 0.0012, 0.0006),
                (_cx, _home_y, PLATE_Z + CAP_H - 0.0011 + 0.0002))
    lib.bevel(_nub, width=0.0002, segments=1)
    lib.apply_modifiers(_nub)
    caps_alpha = lib.join([caps_alpha, _nub], 'keyboard_alpha')
    caps_alpha.name = 'keyboard_alpha'


def _tube(name, points, radius):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = 1
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.use_fill_caps = True
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    lib.activate(o)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.view_layer.objects.active
    o.name = name
    return o


# USB-C cable: exits the back port through a strain-relief boot, bows right and
# lies down on the desk behind the board, ending in a Type-C plug.
_cable = _tube('keyboard_cable',
               [(0, CASE_D / 2 - 0.006, FLOOR_Z - 0.003),
                (0, CASE_D / 2 + 0.018, 0.006),
                (0.035, CASE_D / 2 + 0.055, 0.0025),
                (0.070, CASE_D / 2 + 0.095, 0.0022)], 0.0018)
lib.shade_auto(_cable, 50)
_boot = cube('keyboard_boot', (0.007, 0.012, 0.005), (0, CASE_D / 2 + 0.002, FLOOR_Z - 0.0025))
lib.bevel(_boot, width=0.0012, segments=2)
lib.apply_modifiers(_boot)
_plug_dir = 0.35
_plug = cube('keyboard_plug', (0.0085, 0.011, 0.0032),
             (0.070 + math.sin(_plug_dir) * 0.006, CASE_D / 2 + 0.095 + math.cos(_plug_dir) * 0.006,
              0.0022), rot=(0, 0, _plug_dir))

# Stabiliser housings, peeking out of the plate beside every wide key.
bars = []
for cx, cy, w, angle in stabs:
    for side in (-1, 1):
        bars.append(cube('kb_stab', (0.0040, 0.0090, 0.0030),
                         (cx + side * (w * U) / 2 * 0.615, cy, PLATE_Z + 0.0012)))

leds = []
for i in range(3):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=0.0013, depth=0.0012,
        location=(KEY_W / 2 - 0.030 + i * 0.012, KEY_D / 2 + 0.0026, PLATE_Z + 0.0006))
    leds.append(bpy.context.object)

# --------------------------------------------------------------------------- materials

white = lib.material('kb_case_mat', lib.hex_rgb('#f2f1ee'), roughness=0.44)
cap_white = lib.material('kb_cap_mat', lib.hex_rgb('#eceae5'), roughness=0.58)
cap_dark = lib.material('kb_mod_mat', lib.hex_rgb('#9aa3ad'), roughness=0.56)
dark = lib.material('kb_dark_mat', lib.hex_rgb('#23262a'), roughness=0.5, metallic=0.4)
plate_mat = lib.material('kb_plate_mat', lib.hex_rgb('#3b4148'), roughness=0.38, metallic=0.8)
led_mat = lib.material('kb_led_mat', lib.hex_rgb('#000000'),
                       emission=lib.hex_rgb('#7dffb4'), emission_strength=2.5)

shell = lib.join([case], 'keyboard_case')
lib.set_materials(shell, [white])
lib.set_materials(plate, [plate_mat])
bottom = lib.join([base] + feet + bars, 'keyboard_base')
lib.set_materials(bottom, [dark])
plate = lib.join([plate], 'keyboard_plate')
lib.set_materials(caps_alpha, [cap_white])
lib.set_materials(caps_mod, [cap_dark])
led = lib.join(leds, 'keyboard_led')
lib.set_materials(led, [led_mat])
lib.set_materials(_cable, [white])
lib.set_materials(_boot, [white])
lib.set_materials(_plug, [dark])

group = [shell, plate, bottom, caps_alpha, caps_mod, led, _cable, _boot, _plug]

# The incline. Built in, rather than left for the runtime to tilt, so the feet and the front
# chamfer are at the angle they are modelled for.
TILT = math.radians(5.5)
for o in group:
    o.rotation_euler = (TILT, 0, 0)
    lib.apply_transforms(o)
lib.recentre(group, 'base')
lib.unwrap_all(group)

for o in group:
    print(f'  {o.name}: {lib.tri_count(o)} tris')
lib.export(OUT, group)
lib.write_meta(OUT, {'width': CASE_W, 'depth': CASE_D})
