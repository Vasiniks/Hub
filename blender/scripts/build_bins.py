"""
Workshop storage: a stacking parts bin, a tote crate, and a compartment organiser.

The runtime versions were five boxes each — floor, four walls — which read as closed lidded
boxes, because nothing showed the one thing that makes a bin a bin: that it is a moulded,
open, thin-walled shell. These are lofted as real shells with wall thickness, draft (the walls
flare outward toward the top, as every injection-moulded bin does so it releases from its
mould), rounded corners and a stacking rim. The parts bin has the scooped front that lets you
reach in while it is stacked; the tote has hand-hold slots and stacking ribs; the organiser's
compartments are milled out of one block so its dividers are the block itself.

Exports three GLBs to the directory given; each carries a `*_plastic` material the runtime
retints per instance, so one bin model serves every colour.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT_DIR = lib.argv()[0]
N = 5
RING = lib.ring_indices(N)


def outline(a, b, r):
    pts = []
    for i, j in RING:
        u, v = 2 * i / (N - 1) - 1, 2 * j / (N - 1) - 1
        pts.append(lib.rounded(u, v, a, b, r))
    return pts


def shell(bm, w, d, h, t, draft, rc, lip=0.0, top_z=None):
    """
    Thin-walled open shell. `top_z(y)` lets the rim dip (the parts bin's scoop). The rim is a
    flat band joining outer and inner walls, with an optional outward stacking lip.
    """
    top_z = top_z or (lambda y: h)
    ob = outline(w / 2, d / 2, rc)
    ot = outline(w / 2 + draft, d / 2 + draft, rc + draft * 0.5)
    ib = outline(w / 2 - t, d / 2 - t, max(rc - t, 0.002))
    it = outline(w / 2 + draft - t, d / 2 + draft - t, max(rc + draft * 0.5 - t, 0.002))
    n = len(RING)

    def ring(pts, zfn):
        return [bm.verts.new((x, y, zfn(y))) for x, y in pts]

    rings = [ring(ob, lambda y: 0.0)]
    if lip > 0:
        rings.append(ring(ot, lambda y: top_z(y) - lip))
        flare = outline(w / 2 + draft + lip, d / 2 + draft + lip, rc + draft * 0.5 + lip)
        rings.append(ring(flare, lambda y: top_z(y) - lip))
        rings.append(ring(flare, top_z))
    else:
        rings.append(ring(ot, top_z))
    inner_top = ring(it, top_z)
    inner_bottom = ring(ib, lambda y: t)
    rings += [inner_top, inner_bottom]
    for a_, b_ in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a_[k], a_[(k + 1) % n], b_[(k + 1) % n], b_[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(inner_bottom)


def to_object(bm, name, mats):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    for m in mats:
        me.materials.append(m)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    lib.shade_auto(o, 35)
    lib.uv_unwrap(o)
    return o


def box(size, loc, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.object
    o.scale = size
    lib.apply_transforms(o)
    if bevel:
        lib.bevel(o, width=bevel, segments=2, angle_deg=60)
        lib.apply_modifiers(o)
    return o


def cyl(r, depth, loc, axis='z', verts=16):
    rot = {'z': (0, 0, 0), 'x': (0, math.pi / 2, 0), 'y': (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    lib.apply_transforms(o)
    return o


def cut(target, cutters):
    for c in cutters:
        m = target.modifiers.new('cut', 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.object = c
        m.solver = 'EXACT'
    lib.apply_modifiers(target)
    lib.drop(cutters)
    return target


def export(objs, name, meta=None):
    for o in objs:
        lib.uv_unwrap(o)
    lib.recentre(objs, 'base')
    path = os.path.join(OUT_DIR, f'{name}.glb')
    lib.export(path, objs)
    if meta:
        lib.write_meta(path, meta)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


lib.reset()
plastic = lib.material('bin_plastic', lib.hex_rgb('#5a7fa6'), roughness=0.62)
label = lib.material('bin_label', lib.hex_rgb('#e9e6de'), roughness=0.8)

# --------------------------------------------------------------------------- parts bin
W, D, H, T = 0.15, 0.10, 0.058, 0.0022
FRONT = -D / 2          # Blender -Y faces the room


def scoop(y):
    # Full height at the back, dropping to 55% at the front along a smooth ramp.
    k = min(1.0, max(0.0, (y - FRONT) / (D * 0.7)))
    k = k * k * (3 - 2 * k)
    return H * (0.55 + 0.45 * k)


bm = bmesh.new()
shell(bm, W, D, H, T, draft=0.003, rc=0.008, lip=0.004, top_z=scoop)
bin_obj = to_object(bm, 'bin', [plastic])
bin_obj.name = 'bin'
# Label plate on the front, where the scoop leaves a flat wall.
plate = box((W * 0.46, 0.0012, H * 0.2), (0, FRONT - 0.0012, H * 0.26), bevel=0.0004)
plate.name = 'bin_label'
lib.set_materials(plate, [label])
# Stacking rails down both flanks + a hanger lip across the back top.
rails = []
for s in (-1, 1):
    rails.append(box((0.0035, D * 0.8, 0.004), (s * (W / 2 + 0.0035), 0.0, H * 0.62), bevel=0.0012))
rails = lib.join(rails, 'bin_rails')
lib.set_materials(rails, [plastic])
hanger = box((W * 0.9, 0.006, 0.005), (0, D / 2 + 0.001, H - 0.004), bevel=0.0012)
hanger.name = 'bin_hanger'
lib.set_materials(hanger, [plastic])
feet = lib.join([box((0.016, 0.012, 0.003), (sx * (W / 2 - 0.014), sy * (D / 2 - 0.012), 0.0015),
                     bevel=0.001)
                 for sx in (-1, 1) for sy in (-1, 1)], 'bin_feet')
lib.set_materials(feet, [plastic])
export([bin_obj, plate, rails, hanger, feet], 'bin', {'width': W, 'depth': D, 'height': H})

# --------------------------------------------------------------------------- tote
W, D, H, T = 0.32, 0.24, 0.17, 0.004
bm = bmesh.new()
shell(bm, W, D, H, T, draft=0.008, rc=0.018, lip=0.009)
tote = to_object(bm, 'tote', [plastic])
tote.name = 'tote'
# Hand-holds through both short ends, and stacking ribs down the long sides.
holds = []
for s in (-1, 1):
    c = box((0.05, 0.075, 0.024), (s * (W / 2 + 0.004), 0, H - 0.035))
    lib.bevel(c, width=0.011, segments=4, angle_deg=80)
    lib.apply_modifiers(c)
    holds.append(c)
cut(tote, holds)
ribs = []
for sy in (-1, 1):
    for x in (-0.09, -0.03, 0.03, 0.09):
        # On the outside of the drafted wall: its outer face sits at D/2 + draft/2 at mid-height.
        r = box((0.007, 0.006, H * 0.78), (x, sy * (D / 2 + 0.008 / 2 + 0.0035), H * 0.42), bevel=0.0015)
        r.rotation_euler = (sy * 0.047, 0, 0)
        lib.apply_transforms(r)
        ribs.append(r)
# Corner posts: stacking strength reads at the corners.
for sx in (-1, 1):
    for sy in (-1, 1):
        r = box((0.012, 0.012, H * 0.9),
                (sx * (W / 2 + 0.008 / 2 - 0.002), sy * (D / 2 + 0.008 / 2 - 0.002), H * 0.45),
                bevel=0.002)
        r.rotation_euler = (sy * 0.047, 0, sx * 0.05)
        lib.apply_transforms(r)
        ribs.append(r)
ribs = lib.join(ribs, 'tote_ribs')
lib.set_materials(ribs, [plastic])
# Internal stacking ledge: the next tote nests onto this, not into the void.
ledge = []
for s in (-1, 1):
    ledge.append(box((W * 0.92, 0.008, 0.006), (0, s * (D / 2 - 0.004), H - 0.035), bevel=0.0015))
    ledge.append(box((0.008, D * 0.9, 0.006), (s * (W / 2 - 0.004), 0, H - 0.035), bevel=0.0015))
ledge = lib.join(ledge, 'tote_ledge')
lib.set_materials(ledge, [plastic])
# Removable divider with a finger notch, reaching near the floor.
div = box((W * 0.9, 0.003, H * 0.55), (0, 0, H * 0.30), bevel=0.0012)
notch = cyl(0.012, 0.01, (0, 0, H * 0.575), verts=16)
cut(div, [notch])
div.name = 'tote_divider'
lib.set_materials(div, [plastic])
feet = lib.join([box((0.02, 0.016, 0.006), (sx * (W / 2 - 0.03), sy * (D / 2 - 0.025), 0.003),
                     bevel=0.002)
                 for sx in (-1, 1) for sy in (-1, 1)], 'tote_feet')
lib.set_materials(feet, [plastic])
export([tote, ribs, ledge, div, feet], 'tote', {'width': W, 'depth': D, 'height': H})

# --------------------------------------------------------------------------- organiser
W, D, H, WALL = 0.19, 0.125, 0.042, 0.0032
block = box((W, D, H), (0, 0, H / 2), bevel=0.003)
cols, rows = 4, 2
cw = (W - WALL * (cols + 1)) / cols
ch = (D - WALL * (rows + 1)) / rows
pockets = []
for i in range(cols):
    for j in range(rows):
        x = -W / 2 + WALL + cw / 2 + i * (cw + WALL)
        y = -D / 2 + WALL + ch / 2 + j * (ch + WALL)
        # Bevelled cutters leave rounded corners and a rounded floor inside every compartment.
        p = box((cw, ch, H * 1.2), (x, y, WALL + H * 0.6))
        lib.bevel(p, width=0.006, segments=3, angle_deg=80)
        lib.apply_modifiers(p)
        pockets.append(p)
tray = cut(block, pockets)
tray.name = 'organizer'
lib.set_materials(tray, [plastic])
pull = box((0.05, 0.01, 0.012), (0, D / 2 - 0.002, H * 0.32))
cut(tray, [pull])
lib.shade_auto(tray, 35)
lib.uv_unwrap(tray)
# Hinge knuckles across the back (lid-ready), a clasp on the front, and rubber
# feet — the furniture that says organiser, not tray.
knuckles = lib.join([cyl(0.004, 0.03, (x, -D / 2 - 0.001, H - 0.004), axis='x', verts=12)
                     for x in (-0.06, 0.0, 0.06)], 'organizer_hinges')
lib.set_materials(knuckles, [plastic])
clasp = box((0.03, 0.006, 0.02), (0, D / 2 + 0.001, H * 0.55), bevel=0.002)
clasp.name = 'organizer_clasp'
lib.set_materials(clasp, [plastic])
ofeat = lib.join([cyl(0.006, 0.002, (sx * (W / 2 - 0.015), sy * (D / 2 - 0.012), 0.001), verts=12)
                  for sx in (-1, 1) for sy in (-1, 1)], 'organizer_feet')
lib.set_materials(ofeat, [plastic])
export([tray, knuckles, clasp, ofeat], 'organizer', {'width': W, 'depth': D, 'height': H})
