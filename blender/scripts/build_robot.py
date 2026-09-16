"""
FRC competition robot.

The runtime version was assembled from rounded boxes, and every detail that makes a robot read
as a *built* robot was faked on top of them: lightening holes were dark discs stuck to solid
bars, wheel tread was boxes arranged around a cylinder, bumpers were rounded slabs with a
placard. Here each of those is the real construction:

  * frame and elevator rails are 2x1 / 1x1 rectangular *tube* — hollow, with lightening holes
    bored through both walls, so you can see through them to the floor
  * bumpers are one continuous sweep of the actual FRC bumper section — plywood backing, two
    pool noodles, fabric pulled over — around the frame perimeter, with the team number laid
    onto the fabric's curve rather than on a sign
  * swerve modules have treaded wheels with recessed hubs, pocketed fork plates, and finned
    brushless motors on a bolted top plate
  * the electrical board has a standing battery with terminals and a strap, a PDH with breakers
    seated in real pockets, a roboRIO, radio, main breaker and cable runs

Layout matches the previous in-code robot so the camera framing and the project's focus pose
do not move. The elevator carriage and the robot signal light are exported as their own
objects because the runtime animates them.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]
lib.reset()

IN = 0.0254
FH = 0.27                      # frame outer half-size
RAIL_Z0 = 0.035                # rail underside above the floor
RAIL_H = 2 * IN
RAIL_W = IN
WALL = 0.0016

MATS = {
    'robot_alu': ('#b7bcc2', 0.3, 1.0),
    'robot_black': ('#141518', 0.55, 0.0),
    'robot_rubber': ('#0e0f11', 0.9, 0.0),
    'robot_bumper': ('#a3262a', 0.85, 0.0),
    'robot_orange': ('#e2661a', 0.5, 0.0),
    'robot_white': ('#eceef0', 0.5, 0.0),
    'robot_grey': ('#555b62', 0.6, 0.0),
    'robot_copper': ('#b87333', 0.35, 1.0),
    'robot_red': ('#c0282c', 0.5, 0.0),
    'robot_yellow': ('#e0b92a', 0.6, 0.0),
    'robot_number': ('#ffffff', 0.85, 0.0),
    'robot_rsl': ('#ff8a2a', 0.4, 0.0),
    'robot_poly': ('#2b2f35', 0.4, 0.0),
}
MAT = {k: lib.material(k, lib.hex_rgb(c), roughness=r, metallic=mt) for k, (c, r, mt) in MATS.items()}
PARTS = {'body': [], 'carriage': [], 'rsl': []}


def keep(obj, mat, group='body'):
    lib.set_materials(obj, [MAT[mat]])
    PARTS[group].append(obj)
    return obj


def box(size, loc, bevel=0.0, seg=2, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = size
    lib.apply_transforms(o)
    if bevel:
        lib.bevel(o, width=bevel, segments=seg, angle_deg=60)
        lib.apply_modifiers(o)
    return o


def cyl(r, depth, loc, axis='z', verts=24):
    rot = {'z': (0, 0, 0), 'x': (0, math.pi / 2, 0), 'y': (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    lib.apply_transforms(o)
    return o


def cut(target, cutters):
    if not cutters:
        return target
    tool = lib.join(cutters, 'cutter') if len(cutters) > 1 else cutters[0]
    mod = target.modifiers.new('cut', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = tool
    mod.solver = 'EXACT'
    lib.apply_modifiers(target)
    lib.drop([tool])
    return target


# --------------------------------------------------------------------------- tube stock

def tube(length, axis, centre, w=RAIL_W, h=RAIL_H, holes=True, hole_r=0.0085, pitch=2 * IN):
    """
    Rectangular aluminium tube along `axis`. `w` is the thin side, `h` the wide side; holes are
    bored through the wide faces, through both walls, at a regular pitch.
    """
    cx, cy, cz = centre
    if axis == 'x':
        outer, inner = (length, w, h), (length + 0.01, w - 2 * WALL, h - 2 * WALL)
        bore = 'y'
    elif axis == 'y':
        outer, inner = (w, length, h), (w - 2 * WALL, length + 0.01, h - 2 * WALL)
        bore = 'x'
    else:
        outer, inner = (w, h, length), (w - 2 * WALL, h - 2 * WALL, length + 0.01)
        bore = 'x'
    o = box(outer, centre, bevel=0.0012, seg=1)
    cutters = [box(inner, centre)]
    if holes:
        n = int((length - 2 * IN) // pitch)
        for i in range(n):
            t = (i - (n - 1) / 2) * pitch
            loc = {'x': (cx + t, cy, cz), 'y': (cx, cy + t, cz), 'z': (cx, cy, cz + t)}[axis]
            cutters.append(cyl(hole_r, w * 3 + 0.01, loc, axis=bore, verts=10))
    return cut(o, cutters)


# --------------------------------------------------------------------------- frame

rail_z = RAIL_Z0 + RAIL_H / 2
for s in (-1, 1):
    keep(tube(2 * FH, 'x', (0, s * (FH - RAIL_W / 2), rail_z)), 'robot_alu')
    keep(tube(2 * FH - 2 * RAIL_W, 'y', (s * (FH - RAIL_W / 2), 0, rail_z)), 'robot_alu')
# Elevator cross-member.
keep(tube(2 * FH - 2 * RAIL_W, 'x', (0, 0.17, rail_z)), 'robot_alu')
# Corner gussets, bolted over the joints.
for sx in (-1, 1):
    for sy in (-1, 1):
        g = box((0.07, 0.07, 0.0032), (sx * (FH - 0.035), sy * (FH - 0.035), RAIL_Z0 + RAIL_H + 0.0016), bevel=0.001)
        bolts = [cyl(0.0028, 0.02, (sx * (FH - 0.035) + dx, sy * (FH - 0.035) + dy, RAIL_Z0 + RAIL_H), verts=10)
                 for dx, dy in ((-0.02, -0.02), (0.02, -0.02), (-0.02, 0.02), (0.02, 0.02))]
        keep(cut(g, bolts), 'robot_alu')

# Belly pan: polycarbonate under the frame, with pockets where nothing is mounted.
pan = box((2 * FH - 0.004, 2 * FH - 0.004, 0.0032), (0, 0, RAIL_Z0 - 0.0016), bevel=0.001)
pockets = [box((0.07, 0.05, 0.02), (x, y, RAIL_Z0)) for x, y in ((-0.16, 0.0), (0.16, 0.0), (0.0, 0.045))]
for p in pockets:
    lib.bevel(p, width=0.008, segments=3, angle_deg=80)
    lib.apply_modifiers(p)
keep(cut(pan, pockets), 'robot_poly')

# --------------------------------------------------------------------------- bumpers

HB = 0.127
BZ = 0.040
BACK = 0.019
NR = 0.032
NOODLES = (BZ * 0 + 0.034, 0.093)


def bumper_out(h):
    """Outward reach of the fabric at height h: whichever noodle bulges further there."""
    return BACK + NR + max(math.sqrt(max(0.0, NR * NR - (h - c) ** 2)) for c in NOODLES)


PROFILE = [(0.0, 0.0)] + [(bumper_out(h), h) for h in
                          [0.002 + (HB - 0.004) * i / 17 for i in range(18)]] + [(0.0, HB)]


def path(half, rc, arc=8):
    """Closed rounded-rectangle path, counter-clockwise, as (point, outward normal) pairs."""
    out = []
    for q, (cx, cy) in enumerate(((half - rc, -(half - rc)), (half - rc, half - rc),
                                  (-(half - rc), half - rc), (-(half - rc), -(half - rc)))):
        a0 = -math.pi / 2 + q * math.pi / 2
        for i in range(arc + 1):
            a = a0 + (math.pi / 2) * i / arc
            n = Vector((math.cos(a), math.sin(a), 0))
            out.append((Vector((cx, cy, 0)) + n * rc, n))
    return out


bm = bmesh.new()
rings = []
# Mitred corners. Sweeping the section round any corner radius offsets it by its full depth, so
# the outside came out as an 85 mm radius however small the path's own radius was — a pool
# ring, not a bumper. A mitre ring at each corner, pushed out by sqrt(2), is square the way the
# fabric is pulled square round a real bumper's plywood corner.
for cx, cy in ((FH, -FH), (FH, FH), (-FH, FH), (-FH, -FH)):
    corner = Vector((cx, cy, 0))
    n = Vector((math.copysign(1, cx), math.copysign(1, cy), 0))
    rings.append([bm.verts.new(corner + n * d + Vector((0, 0, BZ + h))) for d, h in PROFILE])
for i in range(len(rings)):
    a, b = rings[i], rings[(i + 1) % len(rings)]
    for k in range(len(PROFILE)):
        bm.faces.new((a[k], b[k], b[(k + 1) % len(PROFILE)], a[(k + 1) % len(PROFILE)]))
bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
me = bpy.data.meshes.new('bumper')
bm.to_mesh(me)
bm.free()
bump = bpy.data.objects.new('bumper', me)
bpy.context.collection.objects.link(bump)
lib.shade_auto(bump, 50)
keep(bump, 'robot_bumper')

# Team numbers: a grid laid onto the fabric's own curve, a hair proud of it.
bm = bmesh.new()
uv = bm.loops.layers.uv.new('UVMap')
NX, NH = 14, 12
HALF_W = 0.115
for side in (-1, 1):
    grid = []
    for j in range(NH + 1):
        h = 0.014 + (HB - 0.028) * j / NH
        row = []
        for i in range(NX + 1):
            x = -HALF_W + 2 * HALF_W * i / NX
            y = side * (FH + bumper_out(h) + 0.0007)
            row.append(bm.verts.new((x, y, BZ + h)))
        grid.append(row)
    outward = Vector((0, side, 0))
    for j in range(NH):
        for i in range(NX):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            f.normal_update()
            if f.normal.dot(outward) < 0:
                f.normal_flip()
            for loop in f.loops:
                x, _, z = loop.vert.co
                u = (x + HALF_W) / (2 * HALF_W)
                # Read left to right from whichever side you are looking at it.
                loop[uv].uv = (u if side < 0 else 1 - u, (z - BZ - 0.014) / (HB - 0.028))
me = bpy.data.meshes.new('numbers')
bm.to_mesh(me)
bm.free()
nums = bpy.data.objects.new('numbers', me)
bpy.context.collection.objects.link(nums)
keep(nums, 'robot_number')


# --------------------------------------------------------------------------- swerve modules

def castellated(r_out, r_in, teeth, length, centre, axis, hub=None):
    """
    A ribbed cylinder — tread on a wheel, cooling fins on a motor — built from a toothed profile
    rather than by arranging boxes round a cylinder. `hub` recesses each end cap to a smaller
    disc, which is what makes a wheel read as a wheel from the side.
    """
    bm = bmesh.new()
    prof = []
    n = teeth * 4
    for i in range(n):
        a = 2 * math.pi * i / n
        r = r_out if (i % 4) in (0, 1) else r_in
        prof.append((r * math.cos(a), r * math.sin(a)))

    def to_world(u, v, t):
        local = {'x': Vector((t, u, v)), 'y': Vector((u, t, v)), 'z': Vector((u, v, t))}[axis]
        return Vector(centre) + local

    ends = []
    for t in (-length / 2, length / 2):
        ends.append([bm.verts.new(to_world(u, v, t)) for u, v in prof])
    for i in range(n):
        bm.faces.new((ends[0][i], ends[0][(i + 1) % n], ends[1][(i + 1) % n], ends[1][i]))
    for k, t in enumerate((-length / 2, length / 2)):
        ring = ends[k]
        if hub:
            hr, depth = hub
            inset = t - math.copysign(depth, t)
            inner = [bm.verts.new(to_world(hr * math.cos(2 * math.pi * i / n),
                                           hr * math.sin(2 * math.pi * i / n), t)) for i in range(n)]
            floor = [bm.verts.new(to_world(hr * math.cos(2 * math.pi * i / n),
                                           hr * math.sin(2 * math.pi * i / n), inset)) for i in range(n)]
            for i in range(n):
                bm.faces.new((ring[i], ring[(i + 1) % n], inner[(i + 1) % n], inner[i]))
                bm.faces.new((inner[i], inner[(i + 1) % n], floor[(i + 1) % n], floor[i]))
            bm.faces.new(floor)
        else:
            bm.faces.new(ring)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new('ribbed')
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new('ribbed', me)
    bpy.context.collection.objects.link(o)
    lib.shade_auto(o, 30)
    return o


MOD = 0.19
PLATE_Z = RAIL_Z0 + RAIL_H
WHEEL_R = 2 * IN
for sx in (-1, 1):
    for sy in (-1, 1):
        cx, cy = sx * MOD, sy * MOD
        yaw = (0.21, -0.17, 0.3, -0.08)[(sx + 1) // 2 * 2 + (sy + 1) // 2]
        start = len(PARTS['body'])
        # Wheel: tread castellated across its face, hubs recessed.
        keep(castellated(WHEEL_R, WHEEL_R - 0.0022, 16, 1.5 * IN, (cx, cy, WHEEL_R), 'x',
                         hub=(0.03, 0.005)), 'robot_rubber')
        keep(cyl(0.012, 1.5 * IN + 0.012, (cx, cy, WHEEL_R), axis='x', verts=16), 'robot_alu')
        # Fork plates either side of the wheel, pocketed.
        for side in (-1, 1):
            fp = box((0.005, 0.09, 0.075), (cx + side * 0.028, cy, WHEEL_R + 0.012), bevel=0.0015)
            tri = box((0.02, 0.04, 0.026), (cx + side * 0.028, cy + 0.012, WHEEL_R + 0.03))
            lib.bevel(tri, width=0.006, segments=2, angle_deg=80)
            lib.apply_modifiers(tri)
            keep(cut(fp, [tri]), 'robot_alu')
        # Top plate, bolted to the frame corner, with the steering bearing bore.
        tp = box((0.125, 0.125, 0.00635), (cx, cy, PLATE_Z + 0.0032), bevel=0.002)
        keep(cut(tp, [cyl(0.004, 0.02, (cx + dx, cy + dy, PLATE_Z), verts=10)
                      for dx, dy in ((-0.05, -0.05), (0.05, -0.05), (-0.05, 0.05), (0.05, 0.05))]), 'robot_alu')
        # Drive motor: finned body, orange end cap. Steer motor: smaller, beside it.
        keep(castellated(0.0305, 0.0285, 12, 0.052, (cx + 0.024, cy - 0.004, PLATE_Z + 0.032), 'z'), 'robot_black')
        keep(cyl(0.0295, 0.009, (cx + 0.024, cy - 0.004, PLATE_Z + 0.0625), verts=24), 'robot_orange')
        keep(cyl(0.008, 0.004, (cx + 0.024, cy - 0.004, PLATE_Z + 0.069), verts=12), 'robot_alu')
        keep(castellated(0.018, 0.0168, 8, 0.042, (cx - 0.028, cy + 0.022, PLATE_Z + 0.027), 'z'), 'robot_black')
        keep(cyl(0.0175, 0.006, (cx - 0.028, cy + 0.022, PLATE_Z + 0.051), verts=16), 'robot_grey')
        # Absolute encoder on the steering axis.
        keep(box((0.028, 0.028, 0.012), (cx - 0.03, cy - 0.03, PLATE_Z + 0.012), bevel=0.002), 'robot_black')
        # A swerve drive at rest rarely has its wheels lined up.
        rot = Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Translation((-cx, -cy, 0))
        for o in PARTS['body'][start:]:
            if o.location.length < 1e9:
                o.data.transform(rot)
                o.data.update()

# --------------------------------------------------------------------------- electrical

# Battery, standing on end, with terminals, a strap and its Anderson lead.
# Behind the PDH, not in front of it: standing, it is tall enough to hide the whole board from
# the side the room is seen from.
BX, BY = -0.03, -0.02
bat = box((0.181, 0.077, 0.167), (BX, BY, RAIL_Z0 + 0.0835), bevel=0.004)
keep(bat, 'robot_black')
for dx, mat in ((-0.05, 'robot_red'), (0.05, 'robot_black')):
    keep(box((0.024, 0.02, 0.012), (BX + dx, BY, RAIL_Z0 + 0.173), bevel=0.002), mat)
    keep(cyl(0.005, 0.01, (BX + dx, BY, RAIL_Z0 + 0.182), verts=12), 'robot_copper')
strap = box((0.186, 0.082, 0.02), (BX, BY, RAIL_Z0 + 0.10), bevel=0.002)
keep(cut(strap, [box((0.181, 0.077, 0.03), (BX, BY, RAIL_Z0 + 0.10))]), 'robot_black')
keep(box((0.04, 0.03, 0.022), (BX + 0.02, BY + 0.058, RAIL_Z0 + 0.19), bevel=0.003), 'robot_red')

# Power distribution hub: breakers seated in real pockets.
PX, PY, PT = -0.02, -0.16, 0.034
pdh = box((0.19, 0.115, PT), (PX, PY, RAIL_Z0 + PT / 2), bevel=0.004)
slots = []
for i in range(10):
    for row in (-1, 1):
        sx_ = PX - 0.075 + i * 0.0165
        slots.append(box((0.0105, 0.021, 0.02), (sx_, PY + row * 0.024, RAIL_Z0 + PT)))
keep(cut(pdh, slots), 'robot_white')
for i in range(10):
    for row in (-1, 1):
        if (i * 7 + row) % 3 == 0:
            continue
        keep(box((0.0095, 0.02, 0.012), (PX - 0.075 + i * 0.0165, PY + row * 0.024, RAIL_Z0 + PT - 0.002)),
             'robot_orange')

# roboRIO, with a recessed port bank and a status window.
RX, RY = 0.07, 0.085
rio = box((0.137, 0.089, 0.035), (RX, RY, RAIL_Z0 + 0.0175), bevel=0.004)
cut(rio, [box((0.1, 0.012, 0.016), (RX, RY - 0.0445, RAIL_Z0 + 0.018)),
          box((0.04, 0.02, 0.004), (RX + 0.035, RY + 0.02, RAIL_Z0 + 0.035))])
keep(rio, 'robot_grey')
for dx in (-0.032, 0.0, 0.032):
    keep(box((0.018, 0.006, 0.011), (RX + dx, RY - 0.041, RAIL_Z0 + 0.018), bevel=0.0008), 'robot_black')

# Radio and main breaker.
keep(box((0.1, 0.06, 0.028), (-0.11, 0.085, RAIL_Z0 + 0.014), bevel=0.006), 'robot_black')
keep(box((0.035, 0.035, 0.03), (0.14, -0.045, RAIL_Z0 + 0.015), bevel=0.003), 'robot_black')
keep(cyl(0.011, 0.012, (0.14, -0.045, RAIL_Z0 + 0.034), verts=16), 'robot_red')


def cable(points, radius, mat):
    cu = bpy.data.curves.new('cable', 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    cu.resolution_u = 6
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new('cable', cu)
    bpy.context.collection.objects.link(o)
    lib.activate(o)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.view_layer.objects.active
    lib.shade_auto(o, 60)
    return keep(o, mat)


Z = RAIL_Z0
cable([(BX - 0.05, BY, Z + 0.19), (-0.02, -0.11, Z + 0.1), (0.14, -0.06, Z + 0.04)], 0.0042, 'robot_red')
cable([(0.14, -0.03, Z + 0.03), (0.08, -0.02, Z + 0.05), (PX + 0.09, PY, Z + 0.03)], 0.0042, 'robot_red')
cable([(BX + 0.05, BY, Z + 0.19), (0.02, -0.1, Z + 0.09), (PX + 0.08, PY - 0.03, Z + 0.035)], 0.0042, 'robot_black')
cable([(PX, PY + 0.06, Z + 0.035), (0.0, 0.05, Z + 0.05), (RX - 0.05, RY - 0.04, Z + 0.03)], 0.0022, 'robot_yellow')
cable([(RX + 0.06, RY, Z + 0.03), (0.15, 0.1, Z + 0.07), (MOD - 0.03, MOD - 0.03, PLATE_Z + 0.02)], 0.002, 'robot_yellow')
cable([(-0.06, 0.085, Z + 0.02), (0.0, 0.1, Z + 0.04), (RX - 0.068, RY + 0.02, Z + 0.02)], 0.0024, 'robot_black')

# --------------------------------------------------------------------------- elevator

EZ0 = PLATE_Z
for x in (-0.13, 0.13):
    keep(tube(0.62, 'z', (x, 0.17, EZ0 + 0.31)), 'robot_alu')
    keep(tube(0.56, 'z', (x, 0.135, EZ0 + 0.45), w=IN, h=IN, hole_r=0.005, pitch=IN * 2), 'robot_alu')
    keep(box((0.004, 0.012, 0.58), (x - 0.02, 0.148, EZ0 + 0.35)), 'robot_rubber')
    for z in (EZ0 + 0.06, EZ0 + 0.61):
        keep(cyl(0.017, 0.012, (x - 0.02, 0.148, z), axis='x', verts=20), 'robot_alu')
keep(tube(0.3, 'x', (0, 0.17, EZ0 + 0.62 + RAIL_H / 2), holes=False), 'robot_alu')
for x in (-0.13, 0.13):
    keep(box((0.012, 0.045, 0.075), (x + (0.019 if x < 0 else -0.019), 0.17, EZ0 + 0.04), bevel=0.001), 'robot_alu')

# Carriage: a pocketed plate on the second stage, carrying the roller intake.
CZ = EZ0 + 0.46
CY = 0.105
cp = box((0.26, 0.00635, 0.12), (0, CY, CZ), bevel=0.0015)
windows = []
for x in (-0.07, 0.0, 0.07):
    w = box((0.045, 0.03, 0.06), (x, CY, CZ))
    lib.bevel(w, width=0.01, segments=3, angle_deg=80)
    lib.apply_modifiers(w)
    windows.append(w)
keep(cut(cp, windows), 'robot_alu', 'carriage')
for x in (-0.12, 0.12):
    sp = box((0.00635, 0.09, 0.14), (x, CY - 0.045, CZ), bevel=0.0015)
    keep(cut(sp, [box((0.02, 0.04, 0.06), (x, CY - 0.04, CZ + 0.01))]), 'robot_alu', 'carriage')
for z in (CZ - 0.04, CZ + 0.05):
    keep(cyl(0.006, 0.25, (0, CY - 0.07, z), axis='x', verts=12), 'robot_alu', 'carriage')
    for x in (-0.09, -0.03, 0.03, 0.09):
        keep(castellated(0.024, 0.0205, 6, 0.022, (x, CY - 0.07, z), 'x', hub=(0.009, 0.003)),
             'robot_orange', 'carriage')

# Robot signal light on the elevator top.
keep(box((0.036, 0.036, 0.05), (0.13, 0.17 - 0.03, EZ0 + 0.62 + RAIL_H + 0.027), bevel=0.008, seg=3),
     'robot_rsl', 'rsl')

# --------------------------------------------------------------------------- export

if os.environ.get('ROBOT_STATS'):
    tally = {}
    for name, objs in PARTS.items():
        for o in objs:
            key = (o.name.split('.')[0], o.data.materials[0].name if o.data.materials else '')
            tally[key] = tally.get(key, 0) + lib.tri_count(o)
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1])[:14]:
        print('  STAT', k, v)

groups = []
for name, objs in PARTS.items():
    if objs:
        groups.append(lib.join(objs, f'robot_{name}'))
lib.recentre(groups, 'base')
for o in groups:
    print(f'  {o.name}: {lib.tri_count(o)} tris, {len(o.data.materials)} materials')
lib.export(OUT, groups)
lib.write_meta(OUT, {'numberMaterial': 'robot_number'})
