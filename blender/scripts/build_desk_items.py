"""
Small desk items: mug, screwdriver, cable coil, USB hub, loose dev board.

Tier 2 — present to make the desk look used, not to be examined — so each gets the one or two
features that make it read and nothing more. The mug is lathed with real wall thickness and a
rounded lip (the old one was an open cylinder: from above it had no rim at all). The
screwdriver's handle is fluted. The cable is an actual coil with a plug, not a torus. The hub
has port openings and LEDs that the room's lighting drives. The board has mounting holes,
header pins and parts on it.

Exports one GLB per item into the directory given.
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


def mat(name, hexc, rough, metal=0.0):
    return lib.material(name, lib.hex_rgb(hexc), roughness=rough, metallic=metal)


def obj_from(bm, name, material, smooth=35):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    me.materials.append(material)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    lib.shade_auto(o, smooth)
    return o


def lathe(profile, steps=32):
    """Revolve an (r, z) polyline about Z."""
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0, z)) for r, z in profile]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=math.tau, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    return bm


def curve_tube(points, radius, name, material, resolution=2, closed=False, steps=4):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = resolution
    cu.resolution_u = steps
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    sp.use_cyclic_u = closed
    cu.use_fill_caps = True
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    lib.activate(o)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.view_layer.objects.active
    o.name = name
    lib.set_materials(o, [material])
    lib.shade_auto(o, 60)
    return o


def box(size, loc, bevel=0.0, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = size
    lib.apply_transforms(o)
    if bevel:
        lib.bevel(o, width=bevel, segments=2, angle_deg=60)
        lib.apply_modifiers(o)
    return o


def cyl(r, depth, loc, rot=(0, 0, 0), verts=16):
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


def export(objs, name, recentre=True):
    if recentre:
        lib.recentre(objs, 'base')
    lib.export(os.path.join(OUT_DIR, f'{name}.glb'), objs)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


lib.reset()

# --------------------------------------------------------------------------- mug
R, H, WALL, BASE = 0.041, 0.098, 0.0035, 0.007
ceramic = mat('mug_ceramic', '#eeeeec', 0.32)
coffee = mat('mug_coffee', '#1e120b', 0.08)
profile = [
    (0.0, 0.0), (R - 0.004, 0.0), (R - 0.0005, 0.0015), (R, 0.006),             # foot, rounded
    (R + 0.0008, H * 0.5), (R + 0.0012, H - 0.0025),                             # slight belly out
    (R + 0.0002, H - 0.0002), (R - WALL * 0.5, H + 0.0004), (R - WALL, H - 0.0015),  # rounded lip
    (R - WALL - 0.0004, BASE + 0.004), (R - WALL - 0.004, BASE), (0.0, BASE),    # inside wall, floor
]
body = obj_from(lathe(profile, 40), 'mug', ceramic, 40)
handle = curve_tube([(R - 0.002, 0, H * 0.78), (R + 0.03, 0, H * 0.72), (R + 0.03, 0, H * 0.3), (R - 0.002, 0, H * 0.24)],
                    0.0048, 'mug_handle', ceramic, resolution=3, steps=10)
liquid = obj_from(lathe([(0.0, H * 0.78), (R - WALL - 0.0006, H * 0.78)], 40), 'mug_coffee', coffee, 60)
export([body, handle, liquid], 'mug')

# --------------------------------------------------------------------------- screwdriver
handle_mat = mat('driver_handle', '#e2661a', 0.45)
grip_mat = mat('driver_grip', '#1a1b1e', 0.8)
steel = mat('driver_steel', '#b9bec4', 0.25, 1.0)
L = 0.075
prof = [(0.0, 0.0), (0.0075, 0.0005), (0.0095, 0.006), (0.0098, L * 0.6), (0.0088, L * 0.9), (0.006, L), (0.0045, L + 0.004)]
hb = lathe(prof, 36)
# Flutes: push the handle's surface in and out six times around, fading out at both ends.
for v in hb.verts:
    r = math.hypot(v.co.x, v.co.y)
    if r < 1e-6:
        continue
    theta = math.atan2(v.co.y, v.co.x)
    fade = max(0.0, min(1.0, (v.co.z - 0.008) / 0.01, (L * 0.92 - v.co.z) / 0.01))
    k = 1.0 - 0.09 * fade * max(0.0, math.cos(6 * theta)) ** 2
    v.co.x *= k
    v.co.y *= k
handle_obj = obj_from(hb, 'driver_handle', handle_mat, 30)
grip = obj_from(lathe([(0.0101, 0.018), (0.0102, 0.03)], 36), 'driver_grip', grip_mat, 60)
shaft = cyl(0.0022, 0.08, (0, 0, L + 0.004 + 0.04), verts=12)
tip = box((0.0044, 0.0008, 0.008), (0, 0, L + 0.004 + 0.084))
shaft_obj = lib.join([shaft, tip], 'driver_shaft')
lib.set_materials(shaft_obj, [steel])
parts = [handle_obj, grip, shaft_obj]
# Lying on the desk along +X, resting on its handle.
for o in parts:
    o.rotation_euler = (0, math.pi / 2, 0)
    lib.apply_transforms(o)
export(parts, 'screwdriver')

# --------------------------------------------------------------------------- cable coil
cable = mat('cable_jacket', '#16171a', 0.7)
plug_metal = mat('cable_plug', '#a9aeb4', 0.3, 1.0)
pts = []
loops, per = 3, 10
for i in range(loops * per + 1):
    t = i / per
    a = t * math.tau
    r = 0.034 + 0.0035 * math.sin(t * 2.1) + 0.002 * i / (loops * per)
    # Each loop rides a little on the one before where they cross.
    z = 0.0022 + 0.0032 * (0.5 + 0.5 * math.sin(a * 0.5 + t))
    pts.append((r * math.cos(a), r * math.sin(a), z))
tail_start = pts[-1]
pts += [(tail_start[0] + 0.02, tail_start[1] - 0.03, 0.0022), (tail_start[0] + 0.035, tail_start[1] - 0.07, 0.0022)]
coil = curve_tube(pts, 0.0021, 'cable_coil', cable, resolution=1)
end = Vector(pts[-1])
direction = (end - Vector(pts[-2])).normalized()
yaw = math.atan2(direction.y, direction.x)
boot = box((0.016, 0.006, 0.0042), (end.x + direction.x * 0.008, end.y + direction.y * 0.008, 0.0024), bevel=0.0012, rot=(0, 0, yaw))
lib.set_materials(boot, [cable])
plug = box((0.007, 0.0084, 0.0026), (end.x + direction.x * 0.019, end.y + direction.y * 0.019, 0.0024), bevel=0.0009, rot=(0, 0, yaw))
lib.set_materials(plug, [plug_metal])
export([coil, boot, plug], 'cable')

# --------------------------------------------------------------------------- USB hub
alu = mat('hub_body', '#4c5157', 0.38, 1.0)
black = mat('hub_black', '#101114', 0.6)
led_blue = mat('hub_led_blue', '#000000', 0.5)
led_green = mat('hub_led_green', '#000000', 0.5)
W, D, HH = 0.088, 0.042, 0.016
hub = box((W, D, HH), (0, 0, HH / 2), bevel=0.004)
ports = [box((0.0125, 0.012, 0.0052), (x, -D / 2, HH * 0.5)) for x in (-0.03, -0.01, 0.01)]
cut(hub, ports)
hub.name = 'hub_body'
lib.set_materials(hub, [alu])
tongues = [box((0.0112, 0.006, 0.0018), (x, -D / 2 + 0.004, HH * 0.5 - 0.0008)) for x in (-0.03, -0.01, 0.01)]
tongues = lib.join(tongues, 'hub_tongues')
lib.set_materials(tongues, [black])
lb = cyl(0.0016, 0.0008, (0.034, 0.006, HH + 0.0002), verts=12)
lb.name = 'hub_led_blue'
lib.set_materials(lb, [led_blue])
lg = cyl(0.0013, 0.0008, (0.034, -0.006, HH + 0.0002), verts=12)
lg.name = 'hub_led_green'
lib.set_materials(lg, [led_green])
lead = curve_tube([(0, D / 2 - 0.002, HH * 0.5), (0.004, D / 2 + 0.02, 0.004), (0.02, D / 2 + 0.05, 0.0022)], 0.0021, 'hub_cable', black, resolution=1)
export([hub, tongues, lb, lg, lead], 'hub')

# --------------------------------------------------------------------------- dev board
pcb = mat('board_pcb', '#1f5c3a', 0.55)
chip = mat('board_chip', '#141416', 0.45)
metal = mat('board_metal', '#c9ced3', 0.3, 1.0)
W, D, T = 0.07, 0.052, 0.0016
board = box((W, D, T), (0, 0, T / 2), bevel=0.0012)
holes = [cyl(0.0014, 0.01, (sx * (W / 2 - 0.0035), sy * (D / 2 - 0.0035), T / 2), verts=12) for sx in (-1, 1) for sy in (-1, 1)]
cut(board, holes)
board.name = 'board_pcb'
lib.set_materials(board, [pcb])
parts = [box((0.016, 0.016, 0.0022), (-0.008, 0.002, T + 0.0011), bevel=0.0003),
         box((0.006, 0.004, 0.0012), (0.014, -0.012, T + 0.0006)),
         box((0.051, 0.005, 0.0025), (-0.004, D / 2 - 0.0045, T + 0.00125))]
parts = lib.join(parts, 'board_parts')
lib.set_materials(parts, [chip])
pins = [box((0.00064, 0.00064, 0.006), (-0.0265 + i * 0.00254, D / 2 - 0.0045 + (j - 0.5) * 0.00254 * 0.8, T + 0.004)) for i in range(20) for j in (0, 1)]
usb = box((0.0092, 0.0075, 0.0032), (W / 2 - 0.004, 0.006, T + 0.0016), bevel=0.0006)
crystal = box((0.0035, 0.0012, 0.0012), (0.018, 0.012, T + 0.0006), bevel=0.0004)
metal_parts = lib.join(pins + [usb, crystal], 'board_metal')
lib.set_materials(metal_parts, [metal])
export([board, parts, metal_parts], 'board')
