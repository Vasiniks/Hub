"""
Task chair.

The old chair was rounded boxes and spheres — at the bottom of the standing view it read as a
black slab with a smaller black slab behind it. What makes an office chair read is its
shape language, all of it curved: a seat cushion that dishes slightly and rolls down over its
front edge (the "waterfall"), a backrest that wraps around the sitter and pushes forward at
the lumbar, a five-star base whose arms taper toward twin-wheel casters, and the gas lift and
tilt mechanism between them.

The cushions are lofted from the same rounded-rect mapping as the keycaps: a top surface, a
bottom surface, and a side band joining their outlines, so the seat is one closed smooth solid
with a real edge radius rather than a bevelled box. The backrest is the same cushion bent
through a lumbar curve and wrapped across its width.

Orientation matches the runtime chair it replaces: seat front toward Blender +Y (the desk),
backrest toward -Y, origin on the floor under the gas lift.
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

MATS = {
    'chair_fabric': ('#2b2e33', 0.92, 0.0),
    'chair_plastic': ('#141518', 0.5, 0.0),
    'chair_metal': ('#8d9399', 0.35, 1.0),
    'chair_rubber': ('#0d0e10', 0.85, 0.0),
}
MAT = {k: lib.material(k, lib.hex_rgb(c), roughness=r, metallic=m) for k, (c, r, m) in MATS.items()}
PARTS = []


def finish(bm, name, mat, smooth=30):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    me.materials.append(MAT[mat])
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    lib.shade_auto(o, smooth)
    PARTS.append(o)
    return o


def cushion(a, b, r, top, bottom, n=9, place=None):
    """
    A closed cushion: a grid top surface and a grid bottom surface over a rounded-rect outline,
    joined by a side band. `top(x, y)` / `bottom(x, y)` give heights; `place(v)` bends the result.
    """
    bm = bmesh.new()
    ring = lib.ring_indices(n)

    def grid(fn):
        g = {}
        for i in range(n):
            for j in range(n):
                u, v = 2 * i / (n - 1) - 1, 2 * j / (n - 1) - 1
                x, y = lib.rounded(u, v, a, b, r)
                p = Vector((x, y, fn(x, y)))
                g[(i, j)] = bm.verts.new(place(p) if place else p)
        return g

    t = grid(top)
    bo = grid(bottom)
    for i in range(n - 1):
        for j in range(n - 1):
            bm.faces.new((t[(i, j)], t[(i + 1, j)], t[(i + 1, j + 1)], t[(i, j + 1)]))
            bm.faces.new((bo[(i, j)], bo[(i, j + 1)], bo[(i + 1, j + 1)], bo[(i + 1, j)]))
    rt = [t[k] for k in ring]
    rb = [bo[k] for k in ring]
    for k in range(len(ring)):
        bm.faces.new((rb[k], rb[(k + 1) % len(ring)], rt[(k + 1) % len(ring)], rt[k]))
    # A second loop just below the top edge rounds the cushion's rim instead of leaving a crease.
    edges = [e for e in bm.edges if all(v in rt for v in e.verts)]
    bmesh.ops.bevel(bm, geom=edges, offset=0.012, segments=3, affect='EDGES', profile=0.6, clamp_overlap=True)
    return bm


def tube(r, p0, p1, verts=16, cap=True):
    bm = bmesh.new()
    d = Vector(p1) - Vector(p0)
    ret = bmesh.ops.create_cone(bm, cap_ends=cap, segments=verts, radius1=r, radius2=r, depth=d.length)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((Vector(p0) + Vector(p1)) / 2) @ rot, verts=ret['verts'])
    return bm


def join_bm(target, source):
    me = bpy.data.meshes.new('tmp')
    source.to_mesh(me)
    source.free()
    target.from_mesh(me)
    bpy.data.meshes.remove(me)


# --------------------------------------------------------------------------- base

base = bmesh.new()
HUB_Z = 0.075
for k in range(5):
    ang = 2 * math.pi * k / 5
    # A tapering arm: profile narrows and thins toward the caster, and drops slightly.
    arm = bmesh.new()
    steps = 6
    rings = []
    for s in range(steps + 1):
        t = s / steps
        x = 0.035 + t * 0.265
        w = 0.024 - t * 0.010
        h = 0.030 - t * 0.012
        zc = HUB_Z - t * 0.012
        rings.append([arm.verts.new((x, sy * w, zc + sz * h / 2)) for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for s in range(steps):
        a_, b_ = rings[s], rings[s + 1]
        for q in range(4):
            arm.faces.new((a_[q], a_[(q + 1) % 4], b_[(q + 1) % 4], b_[q]))
    arm.faces.new(list(reversed(rings[0])))
    arm.faces.new(rings[-1])
    bmesh.ops.bevel(arm, geom=list(arm.edges), offset=0.004, segments=2, affect='EDGES', clamp_overlap=True)
    bmesh.ops.rotate(arm, verts=arm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(ang, 3, 'Z'))
    join_bm(base, arm)
# Hub.
join_bm(base, tube(0.045, (0, 0, HUB_Z - 0.022), (0, 0, HUB_Z + 0.022), verts=24))
finish(base, 'chair_base', 'chair_plastic', 40)

# Twin-wheel casters under each arm tip.
casters = bmesh.new()
for k in range(5):
    ang = 2 * math.pi * k / 5
    c = bmesh.new()
    for side in (-1, 1):
        join_bm(c, tube(0.025, (-0.012, side * 0.012 - 0.006, 0.025), (-0.012, side * 0.012 + 0.006, 0.025), verts=18))
    join_bm(c, tube(0.006, (0.0, 0, 0.03), (0.0, 0, 0.058), verts=8))
    # Swivel each caster about its own stem (they never all point the same way), then carry it
    # out to its arm tip.
    bmesh.ops.rotate(c, verts=c.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(0.9 * math.sin(k * 2.3), 3, 'Z'))
    bmesh.ops.translate(c, verts=c.verts, vec=(0.3, 0, 0))
    bmesh.ops.rotate(c, verts=c.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(ang, 3, 'Z'))
    join_bm(casters, c)
finish(casters, 'chair_casters', 'chair_rubber', 40)

# Gas lift: a chrome piston inside a plastic cover.
lift = tube(0.024, (0, 0, HUB_Z), (0, 0, 0.3), verts=20)
finish(lift, 'chair_lift_cover', 'chair_plastic', 40)
finish(tube(0.014, (0, 0, 0.3), (0, 0, 0.41), verts=16), 'chair_piston', 'chair_metal', 40)

# --------------------------------------------------------------------------- seat

SEAT_Z = 0.44
mech = bmesh.new()
bmesh.ops.create_cube(mech, size=1.0, matrix=Matrix.Translation((0, 0.01, SEAT_Z - 0.035)) @ Matrix.Diagonal((0.2, 0.24, 0.05, 1)))
bmesh.ops.bevel(mech, geom=list(mech.edges), offset=0.008, segments=2, affect='EDGES', clamp_overlap=True)
join_bm(mech, tube(0.016, (0.1, -0.02, SEAT_Z - 0.04), (0.16, -0.02, SEAT_Z - 0.04), verts=14))  # tension knob stem
join_bm(mech, tube(0.004, (-0.1, 0.06, SEAT_Z - 0.03), (-0.22, 0.1, SEAT_Z - 0.05), verts=8))    # height lever
finish(mech, 'chair_mechanism', 'chair_plastic', 40)

# Seat shell: a thin plastic tray the cushion sits in.
shell = cushion(0.245, 0.235, 0.07, lambda x, y: SEAT_Z - 0.004, lambda x, y: SEAT_Z - 0.02, n=7)
finish(shell, 'chair_seat_shell', 'chair_plastic', 40)


def seat_top(x, y):
    # A shallow dish, a raised rear, and the waterfall roll over the front edge (+Y).
    dish = -0.012 * (1 - (x / 0.25) ** 2) * (1 - ((y + 0.02) / 0.24) ** 2)
    rear = 0.008 * max(0.0, -y / 0.24) ** 2
    front = -0.035 * max(0.0, (y - 0.12) / 0.12) ** 2
    return SEAT_Z + 0.07 + dish + rear + front


seat = cushion(0.25, 0.24, 0.075, seat_top, lambda x, y: SEAT_Z - 0.002, n=11)
finish(seat, 'chair_seat', 'chair_fabric', 50)

# --------------------------------------------------------------------------- back

BACK_BASE = SEAT_Z + 0.12
BACK_H = 0.56


def back_place(p):
    """Bend a flat cushion into the backrest: lumbar forward push, recline, and a wrap across x."""
    s = (p.y + BACK_H / 2) / BACK_H          # 0 at the bottom, 1 at the top
    lumbar = 0.028 * math.exp(-((s - 0.28) / 0.18) ** 2)
    wrap = 0.09 * (p.x / 0.23) ** 2
    recline = 0.12 * s
    depth = p.z                              # thickness, positive toward the sitter (+Y)
    return Vector((p.x, -0.26 - recline + depth + lumbar + wrap, BACK_BASE + s * BACK_H))


back = cushion(0.23, BACK_H / 2, 0.09, lambda x, y: 0.045, lambda x, y: 0.0, n=11, place=back_place)
finish(back, 'chair_back', 'chair_fabric', 50)


def back_shell_place(p):
    q = back_place(p)
    return Vector((q.x, q.y - 0.004, q.z))


back_shell = cushion(0.225, BACK_H / 2 - 0.01, 0.09, lambda x, y: 0.0, lambda x, y: -0.012, n=9, place=back_shell_place)
finish(back_shell, 'chair_back_shell', 'chair_plastic', 50)

# Spine: from the mechanism, back under the seat and up into the backrest shell.
spine = bmesh.new()
pts = [(0, -0.05, SEAT_Z - 0.03), (0, -0.22, SEAT_Z - 0.02), (0, -0.275, SEAT_Z + 0.08), (0, -0.298, BACK_BASE + 0.2)]
for p0, p1 in zip(pts, pts[1:]):
    seg = bmesh.new()
    d = Vector(p1) - Vector(p0)
    ret = bmesh.ops.create_cube(seg, size=1.0)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(seg, matrix=Matrix.Translation((Vector(p0) + Vector(p1)) / 2) @ rot @ Matrix.Diagonal((0.05, 0.018, d.length + 0.02, 1)), verts=ret['verts'])
    bmesh.ops.bevel(seg, geom=list(seg.edges), offset=0.005, segments=2, affect='EDGES', clamp_overlap=True)
    join_bm(spine, seg)
finish(spine, 'chair_spine', 'chair_plastic', 40)

# --------------------------------------------------------------------------- arms

arms = bmesh.new()
for side in (-1, 1):
    x = side * 0.27
    post = bmesh.new()
    ret = bmesh.ops.create_cube(post, size=1.0, matrix=Matrix.Translation((x, -0.02, SEAT_Z + 0.08)) @ Matrix.Diagonal((0.03, 0.05, 0.22, 1)))
    bmesh.ops.bevel(post, geom=list(post.edges), offset=0.008, segments=2, affect='EDGES', clamp_overlap=True)
    join_bm(arms, post)
    bracket = bmesh.new()
    bmesh.ops.create_cube(bracket, size=1.0, matrix=Matrix.Translation((x * 0.62, -0.02, SEAT_Z - 0.025)) @ Matrix.Diagonal((abs(x) * 0.76, 0.045, 0.014, 1)))
    bmesh.ops.bevel(bracket, geom=list(bracket.edges), offset=0.005, segments=2, affect='EDGES', clamp_overlap=True)
    join_bm(arms, bracket)
finish(arms, 'chair_arm_posts', 'chair_plastic', 40)
pads = bmesh.new()
for side in (-1, 1):
    pad = cushion(0.036, 0.13, 0.03, lambda x, y: SEAT_Z + 0.215, lambda x, y: SEAT_Z + 0.19, n=5)
    bmesh.ops.translate(pad, verts=pad.verts, vec=(side * 0.27, 0.0, 0))
    join_bm(pads, pad)
finish(pads, 'chair_arm_pads', 'chair_rubber', 40)

# --------------------------------------------------------------------------- export

chair = lib.join(PARTS, 'chair')
# Not recentred: the runtime rolls and turns the chair about its gas lift, which is already the
# origin, and the casters already stand on z = 0. Centring the bounds would shift the pivot.
lib.apply_transforms(chair)
lo, hi = lib.world_bounds([chair])
print(f'  chair: {lib.tri_count(chair)} tris, {len(chair.data.materials)} materials, bounds {tuple(round(v,3) for v in lo)} {tuple(round(v,3) for v in hi)}')
lib.export(OUT, [chair])
