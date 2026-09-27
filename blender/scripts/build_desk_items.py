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
    lib.uv_unwrap(o)
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
    lib.uv_unwrap(o)
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
    for o in objs:
        lib.uv_unwrap(o)
    if recentre:
        lib.recentre(objs, 'base')
    lib.export(os.path.join(OUT_DIR, f'{name}.glb'), objs)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


lib.reset()

# --------------------------------------------------------------------------- mug
# Hero close-up object (lamp pool, seen at 40 cm): lathed body with real wall
# thickness and a rounded lip, three faint throwing rings in the outer wall, a
# strap-section handle (flattened front-to-back, wider at the top attach) with
# fillet pads where it meets the body so the join reads thrown, not intersected.
R, H, WALL, BASE = 0.041, 0.098, 0.004, 0.008
ceramic = mat('mug_ceramic', '#eeeeec', 0.32)
coffee = mat('mug_coffee', '#1e120b', 0.08)


def wall_z(frac):
    """Outer-wall radius at a height fraction: belly plus throwing rings."""
    r = R + 0.0008 * (frac * 2 - frac * frac) + 0.0012 * frac
    ring = 0.00035 * (math.sin(frac * 29.0) * 0.5 + math.sin(frac * 47.0 + 1.3) * 0.5)
    return r + ring * math.sin(min(1.0, max(0.0, (frac - 0.08) / 0.84)) * math.pi)


profile = [(0.0, 0.0), (R - 0.004, 0.0), (R - 0.0005, 0.0015), (R, 0.006)]
for i in range(1, 12):
    f = 0.006 / H + (1 - 0.006 / H - 0.004) * i / 12
    profile.append((wall_z(f), f * H))
profile += [
    (R + 0.0002, H - 0.0002), (R - WALL * 0.5, H + 0.0004), (R - WALL, H - 0.0015),
    (R - WALL - 0.0004, BASE + 0.004), (R - WALL - 0.004, BASE), (0.0, BASE),
]
body = obj_from(lathe(profile, 48), 'mug', ceramic, 40)
handle = curve_tube([(R - 0.004, 0, H * 0.80), (R + 0.030, 0, H * 0.74),
                     (R + 0.032, 0, H * 0.32), (R - 0.004, 0, H * 0.26)],
                    0.0052, 'mug_handle', ceramic, resolution=3, steps=12)
# Strap section: flatten front-to-back; swell toward the top attach where a
# pulled handle carries more clay.
hmw = handle.matrix_world
for v in handle.data.vertices:
    w = hmw @ v.co
    f = min(1.0, max(0.0, (w.z - H * 0.26) / (H * 0.54)))
    v.co.y *= 0.78
    k = 1.0 + 0.16 * f
    v.co.x *= k
handle.data.update()
lib.uv_unwrap(handle, redo_base=False)
# Fillet pads: squashed spheres sunk halfway into the wall at both attaches.
pads = []
for z, s in ((H * 0.80, 1.15), (H * 0.26, 1.0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.0072 * s,
                                         location=(R - 0.003, 0, z))
    p = bpy.context.object
    p.scale = (1.25, 0.85, 1.1)
    lib.apply_transforms(p)
    pads.append(p)
handle = lib.join([handle] + pads, 'mug_handle')
lib.set_materials(handle, [ceramic])
lib.uv_unwrap(handle, redo_base=False)
liquid = obj_from(lathe([(0.0, H * 0.78), (R - WALL - 0.0006, H * 0.78),
                         (R - WALL - 0.0002, H * 0.782)], 48), 'mug_coffee', coffee, 60)
export([body, handle, liquid], 'mug')

# --------------------------------------------------------------------------- screwdriver
# Fluted soft-grip handle with a hanging hole, steel bolster, hex shaft and a
# Phillips tip — the silhouette details that read at desk distance.
handle_mat = mat('driver_handle', '#e2661a', 0.45)
grip_mat = mat('driver_grip', '#1a1b1e', 0.8)
steel = mat('driver_steel', '#b9bec4', 0.25, 1.0)
L = 0.078
prof = [(0.0, 0.0), (0.0045, 0.0), (0.0082, 0.0012), (0.0098, 0.006),
        (0.0102, 0.014), (0.0104, 0.024), (0.0102, 0.036), (0.0096, L * 0.62),
        (0.0086, L * 0.86), (0.0062, L), (0.0048, L + 0.004), (0.0, L + 0.004)]
hb = lathe(prof, 40)
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
# Soft-grip rings fore and aft of the flute field.
grip = obj_from(lathe([(0.0104, 0.010), (0.0109, 0.013), (0.0109, 0.017), (0.0103, 0.020)], 40),
                'driver_grip', grip_mat, 60)
grip2 = obj_from(lathe([(0.0094, L * 0.66), (0.0099, L * 0.70), (0.0099, L * 0.74),
                        (0.0093, L * 0.78)], 40), 'driver_grip2', grip_mat, 60)
lib.set_materials(grip2, [grip_mat])
# Hanging hole through the pommel.
hole = cyl(0.0028, 0.02, (0, 0, 0.004), verts=12)
hole.rotation_euler = (math.pi / 2, 0, 0)
lib.apply_transforms(hole)
cut(handle_obj, [hole])
# Hex bolster + hex shaft + Phillips tip.
bolster = cyl(0.0062, 0.012, (0, 0, L + 0.004 + 0.006), verts=6)
bolster.name = 'driver_bolster'
lib.set_materials(bolster, [steel])
shaft = cyl(0.0028, 0.085, (0, 0, L + 0.004 + 0.012 + 0.0425), verts=6)
shaft_obj = lib.join([shaft], 'driver_shaft')
tip_cone = cyl(0.0028, 0.010, (0, 0, L + 0.004 + 0.012 + 0.085 + 0.005), verts=6)
tip_a = box((0.0056, 0.0012, 0.010), (0, 0, L + 0.004 + 0.012 + 0.085 + 0.005))
tip_b = box((0.0012, 0.0056, 0.010), (0, 0, L + 0.004 + 0.012 + 0.085 + 0.005))
tip = lib.join([tip_cone], 'driver_tip')
cut(tip, [tip_a, tip_b])
lib.set_materials(tip, [steel])
lib.set_materials(shaft_obj, [steel])
parts = [handle_obj, grip, grip2, bolster, shaft_obj, tip]
# Lying on the desk along +X, resting on its handle.
for o in parts:
    o.rotation_euler = (0, math.pi / 2, 0)
    lib.apply_transforms(o)
export(parts, 'screwdriver')

# --------------------------------------------------------------------------- cable coil
# An actual coil with a velcro tie, a stepped strain-relief boot and a metal
# shroud with a dark mouth — not a torus. Smoother jacket (resolution 2).
cable = mat('cable_jacket', '#16171a', 0.7)
plug_metal = mat('cable_plug', '#a9aeb4', 0.3, 1.0)
pts = []
loops, per = 3, 12
for i in range(loops * per + 1):
    t = i / per
    a = t * math.tau
    r = 0.034 + 0.0035 * math.sin(t * 2.1) + 0.002 * i / (loops * per)
    # Each loop rides a little on the one before where they cross.
    z = 0.0024 + 0.0032 * (0.5 + 0.5 * math.sin(a * 0.5 + t))
    pts.append((r * math.cos(a), r * math.sin(a), z))
tail_start = pts[-1]
pts += [(tail_start[0] + 0.02, tail_start[1] - 0.03, 0.0024), (tail_start[0] + 0.035, tail_start[1] - 0.07, 0.0024)]
coil = curve_tube(pts, 0.0021, 'cable_coil', cable, resolution=2)
# Velcro tie cinching the loops where they stack.
tie = box((0.014, 0.010, 0.006), (pts[6][0], pts[6][1], 0.006), bevel=0.0015)
tie.name = 'cable_tie'
lib.set_materials(tie, [cable])
end = Vector(pts[-1])
direction = (end - Vector(pts[-2])).normalized()
yaw = math.atan2(direction.y, direction.x)
boot_steps = []
for i, w in enumerate((0.0072, 0.0062, 0.0052)):
    boot_steps.append(box((0.006, w, 0.0036 - i * 0.0004),
                          (end.x + direction.x * (0.004 + i * 0.0055),
                           end.y + direction.y * (0.004 + i * 0.0055), 0.0024),
                          bevel=0.0008, rot=(0, 0, yaw)))
boot = lib.join(boot_steps, 'cable_boot')
lib.set_materials(boot, [cable])
shroud = box((0.0075, 0.0084, 0.0028), (end.x + direction.x * 0.023, end.y + direction.y * 0.023, 0.0024),
             bevel=0.0009, rot=(0, 0, yaw))
mouth = box((0.005, 0.0062, 0.0032), (end.x + direction.x * 0.0265, end.y + direction.y * 0.0265, 0.0024),
            rot=(0, 0, yaw))
cut(shroud, [mouth])
shroud.name = 'cable_plug'
lib.set_materials(shroud, [plug_metal])
export([coil, tie, boot, shroud], 'cable')

# --------------------------------------------------------------------------- USB hub
# Low aluminium slab: ports as real recesses with seated tongues (not stickers),
# light-pipe diffuser bars, rubber feet, and a top finger groove.
alu = mat('hub_body', '#4c5157', 0.38, 1.0)
black = mat('hub_black', '#101114', 0.6)
led_blue = mat('hub_led_blue', '#000000', 0.5)
led_green = mat('hub_led_green', '#000000', 0.5)
W, D, HH = 0.088, 0.042, 0.016
hub = box((W, D, HH), (0, 0, HH / 2), bevel=0.004)
groove = box((W * 0.7, 0.008, 0.002), (0, 0.008, HH))
ports = [box((0.0125, 0.014, 0.0052), (x, -D / 2 + 0.001, HH * 0.5)) for x in (-0.03, -0.01, 0.01)]
cut(hub, ports + [groove])
hub.name = 'hub_body'
lib.set_materials(hub, [alu])
tongues = [box((0.0112, 0.008, 0.0018), (x, -D / 2 + 0.004, HH * 0.5 - 0.0008)) for x in (-0.03, -0.01, 0.01)]
tongues = lib.join(tongues, 'hub_tongues')
lib.set_materials(tongues, [black])
lb = box((0.010, 0.0022, 0.0012), (0.028, 0.006, HH - 0.0004), bevel=0.0005)
lb.name = 'hub_led_blue'
lib.set_materials(lb, [led_blue])
lg = box((0.010, 0.0022, 0.0012), (0.028, -0.006, HH - 0.0004), bevel=0.0005)
lg.name = 'hub_led_green'
lib.set_materials(lg, [led_green])
feet = lib.join([cyl(0.004, 0.0012, (sx * (W / 2 - 0.008), sy * (D / 2 - 0.008), 0.0006), verts=12)
                 for sx in (-1, 1) for sy in (-1, 1)], 'hub_feet')
lib.set_materials(feet, [black])
lead = curve_tube([(0, D / 2 - 0.002, HH * 0.5), (0.004, D / 2 + 0.02, 0.004), (0.02, D / 2 + 0.05, 0.0022)], 0.0021, 'hub_cable', black, resolution=1)
export([hub, tongues, lb, lg, feet, lead], 'hub')

# --------------------------------------------------------------------------- dev board
# Mounting holes with gold annular rings, a real USB-C shell with a dark mouth,
# a header base strip under the pins, and a few jellybean parts.
pcb = mat('board_pcb', '#1f5c3a', 0.55)
chip = mat('board_chip', '#141416', 0.45)
metal = mat('board_metal', '#c9ced3', 0.3, 1.0)
W, D, T = 0.07, 0.052, 0.0016
board = box((W, D, T), (0, 0, T / 2), bevel=0.0012)
holes = [cyl(0.0014, 0.01, (sx * (W / 2 - 0.0035), sy * (D / 2 - 0.0035), T / 2), verts=12) for sx in (-1, 1) for sy in (-1, 1)]
cut(board, holes)
board.name = 'board_pcb'
lib.set_materials(board, [pcb])
rings = lib.join([cyl(0.0028, T + 0.0002, (sx * (W / 2 - 0.0035), sy * (D / 2 - 0.0035), T / 2), verts=16)
                  for sx in (-1, 1) for sy in (-1, 1)], 'board_rings')
hole_inner = [cyl(0.0014, T + 0.0006, (sx * (W / 2 - 0.0035), sy * (D / 2 - 0.0035), T / 2), verts=12)
              for sx in (-1, 1) for sy in (-1, 1)]
cut(rings, hole_inner)
lib.set_materials(rings, [metal])
parts = [box((0.016, 0.016, 0.0022), (-0.008, 0.002, T + 0.0011), bevel=0.0003),
         box((0.006, 0.004, 0.0012), (0.014, -0.012, T + 0.0006)),
         box((0.0032, 0.0016, 0.001), (0.008, 0.014, T + 0.0005)),
         box((0.0032, 0.0016, 0.001), (0.013, 0.014, T + 0.0005))]
parts = lib.join(parts, 'board_parts')
lib.set_materials(parts, [chip])
cap = cyl(0.0025, 0.005, (-0.022, -0.014, T + 0.0025), verts=16)
cap.name = 'board_cap'
lib.set_materials(cap, [chip])
header_base = box((0.051, 0.005, 0.0025), (-0.004, D / 2 - 0.0045, T + 0.00125))
header_base.name = 'board_header'
lib.set_materials(header_base, [chip])
pins = [box((0.00064, 0.00064, 0.006), (-0.0265 + i * 0.00254, D / 2 - 0.0045 + (j - 0.5) * 0.00254 * 0.8, T + 0.004)) for i in range(20) for j in (0, 1)]
usb_shell = box((0.0092, 0.0075, 0.0032), (W / 2 - 0.004, 0.006, T + 0.0016), bevel=0.0006)
usb_mouth = box((0.0074, 0.0078, 0.002), (W / 2 - 0.0036, 0.006, T + 0.0016))
cut(usb_shell, [usb_mouth])
usb_shell.name = 'board_usb'
lib.set_materials(usb_shell, [metal])
usb_tongue = box((0.006, 0.005, 0.0008), (W / 2 - 0.004, 0.006, T + 0.0012))
usb_tongue.name = 'board_usb_tongue'
lib.set_materials(usb_tongue, [chip])
crystal = box((0.0035, 0.0012, 0.0012), (0.018, 0.012, T + 0.0006), bevel=0.0004)
metal_parts = lib.join(pins + [crystal], 'board_metal')
lib.set_materials(metal_parts, [metal])
export([board, rings, parts, cap, header_base, usb_shell, usb_tongue, metal_parts], 'board')
