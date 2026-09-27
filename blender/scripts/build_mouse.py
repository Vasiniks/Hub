"""
Computer mouse.

No CC0 mouse exists in the open repositories, so this is modelled. The shape is a dome over a
tapered footprint — width and height follow profile curves along the body, so the nose is low
and narrow and the palm rest is tallest about two thirds back.

What Blender adds over building the same idea out of primitives is the part that actually
makes it read: the button split and the cross seam are *cut* into the shell with a boolean,
so they are real recesses that catch a shadow, and subdivision plus a bevel gives the shell
continuous curvature instead of faceted bands.
"""
import bpy
import bmesh
import math
import mathutils
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]

W, L, H = 0.063, 0.117, 0.038
NZ, NX = 40, 28


def half_width(t):
    return (W / 2) * math.pow(math.sin(math.pi * math.pow(t, 1.15)), 0.36)


def height(t):
    return H * math.pow(math.sin(math.pi * math.pow(t, 1.5)), 0.62)


def arch(u):
    return math.pow(max(0.0, 1 - u * u), 0.42)


lib.reset()

# --- Shell -------------------------------------------------------------------------------
bm = bmesh.new()
grid = []
for i in range(NZ + 1):
    t = i / NZ
    hw, h = half_width(t), height(t)
    y = -L / 2 + t * L
    row = [bm.verts.new((hw * (-1 + 2 * j / NX), y, h * arch(-1 + 2 * j / NX))) for j in range(NX + 1)]
    grid.append(row)
bm.verts.ensure_lookup_table()
for i in range(NZ):
    for j in range(NX):
        try:
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
        except ValueError:
            pass  # degenerate at the tapered ends

# Close the underside so the shell is a solid rather than a sheet — a boolean needs a closed
# mesh, and at a grazing angle you would otherwise see straight through the shell.
bm.verts.index_update()
bm.edges.ensure_lookup_table()
boundary = [e for e in bm.edges if e.is_boundary]
if boundary:
    bmesh.ops.holes_fill(bm, edges=boundary, sides=0)

me = bpy.data.meshes.new('mouse_shell')
bm.to_mesh(me)
bm.free()
shell = bpy.data.objects.new('mouse_shell', me)
bpy.context.collection.objects.link(shell)
lib.clean(shell)

# --- Seams cut into the shell ------------------------------------------------------------
def blade(name, size, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    lib.apply_transforms(o)
    return o


# The seams are shallow grooves, not slots. A straight vertical blade cuts clean through the
# nose, where the shell is only a few millimetres tall — hence the sloped, thin cutters that
# follow the dome's rise and take about a millimetre off the top.
def groove(name, t0, t1, width, depth=0.0055, lift=0.0016):
    y0, y1 = -L / 2 + t0 * L, -L / 2 + t1 * L
    z0, z1 = height(t0), height(t1)
    mid_y, mid_z = (y0 + y1) / 2, (z0 + z1) / 2
    length = math.hypot(y1 - y0, z1 - z0)
    o = blade(name, (width, length, depth), (0, mid_y, mid_z + lift + depth / 2 - 0.0012))
    o.rotation_euler = (-math.atan2(z1 - z0, y1 - y0), 0, 0)
    lib.apply_transforms(o)
    return o


cutters = [
    # Split between the two click halves.
    groove('cut_split', 0.06, 0.52, 0.0014),
    # Where the buttons meet the palm rest: a short cross groove at the same depth.
    blade('cut_cross', (W * 0.86, 0.0014, 0.0055),
          (0, -L / 2 + 0.55 * L, height(0.55) + 0.0016 + 0.0055 / 2 - 0.0012)),
]
for c in cutters:
    m = shell.modifiers.new('seam', 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = c
    m.solver = 'EXACT'
lib.apply_modifiers(shell)
lib.drop(cutters)

# Subdivide for continuous curvature, then a small bevel so every cut edge catches light.
sub = shell.modifiers.new('sub', 'SUBSURF')
sub.levels = sub.render_levels = 1
lib.bevel(shell, width=0.0006, segments=2, angle_deg=25)
lib.apply_modifiers(shell)
lib.clean(shell)
# Subdivision buys smooth curvature, then most of it is given back: at desk distance the
# silhouette survives a heavy decimation and the frame budget does not.
lib.decimate(shell, 0.45)
lib.apply_modifiers(shell)
lib.shade_auto(shell, 38)

# --- Wheel, recess and thumb buttons ------------------------------------------------------
# A scroll wheel belongs about a third back, where the shell has real height. At the nose
# the shell is only 15mm tall and the wheel bursts out of it.
wheel_t = 0.30
wheel_y = -L / 2 + wheel_t * L
wheel_z = height(wheel_t)
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.0086, depth=0.0062,
                                    location=(0, wheel_y, wheel_z - 0.0055),
                                    rotation=(0, math.pi / 2, 0))
wheel = bpy.context.object
wheel.name = 'mouse_wheel'
lib.bevel(wheel, width=0.0004, segments=1)
lib.apply_modifiers(wheel)
lib.shade_auto(wheel, 30)

# A short dark slot under the wheel. Kept well inside the dome: a longer box runs out past
# the nose, where the shell is only a few millimetres tall, and pokes through.
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, wheel_y, wheel_z - 0.008))
recess = bpy.context.object
recess.scale = (0.0112, 0.016, 0.009)
recess.name = 'mouse_recess'
lib.apply_transforms(recess)

thumbs = []
for bt in (0.36, 0.47):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-half_width(bt) + 0.0012,
                                                        -L / 2 + bt * L, height(bt) * 0.34))
    b = bpy.context.object
    b.scale = (0.0022, 0.016, 0.0068)
    b.rotation_euler = (0, 0, 0.16)
    b.name = f'thumb{bt}'  # sunk into the flank, not stuck on it
    lib.bevel(b, width=0.0006, segments=2)
    lib.apply_modifiers(b)
    lib.shade_auto(b, 34)
    thumbs.append(b)

# --- Wheel ribs, DPI button, feet, sensor, nose port --------------------------------------
white = lib.material('mouse_shell_mat', lib.hex_rgb('#eceef0'), roughness=0.42)
grey = lib.material('mouse_grey_mat', lib.hex_rgb('#9ba2aa'), roughness=0.62)
dark = lib.material('mouse_dark_mat', lib.hex_rgb('#15171a'), roughness=0.7)
# Grip ribs around the wheel: five thin tori on the wheel's axle (X after the
# Y-90 rotation), so the wheel catches a highlight per rib in close-up.
ribs = []
for i in range(5):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0086, minor_radius=0.00055,
                                     major_segments=16, minor_segments=6,
                                     location=(-0.0024 + i * 0.0012, wheel_y, wheel_z - 0.0055),
                                     rotation=(0, math.pi / 2, 0))
    r = bpy.context.object
    r.name = f'wheel_rib{i}'
    ribs.append(r)
lib.set_materials(wheel, [grey])
for r in ribs:
    lib.set_materials(r, [grey])
wheel = lib.join([wheel] + ribs, 'mouse_wheel')

# DPI button on the top centerline, just behind the cross groove.
dpi = blade('mouse_dpi', (0.006, 0.009, 0.0022),
            (0, -L / 2 + 0.63 * L, height(0.63) - 0.0001))
lib.bevel(dpi, width=0.0006, segments=2)
lib.apply_modifiers(dpi)
lib.shade_auto(dpi, 34)
lib.set_materials(dpi, [grey])

# PTFE feet on the flat underside (the shell's bottom fill sits at z = 0).
skates = [blade(f'skate{i}', (sx, sy, 0.0008), (px, py, 0.0004))
          for i, (sx, sy, px, py) in enumerate([(0.02, 0.012, 0, -L / 2 + 0.18 * L),
                                                (0.016, 0.010, -0.018, -L / 2 + 0.80 * L),
                                                (0.016, 0.010, 0.018, -L / 2 + 0.80 * L)])]
for s in skates:
    lib.set_materials(s, [grey])

# Sensor window + lens, recessed in the underside.
sensor = blade('mouse_sensor', (0.012, 0.012, 0.001), (0, -L / 2 + 0.60 * L, 0.0003))
bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.003, depth=0.0012,
                                    location=(0, -L / 2 + 0.60 * L, 0.0004))
lens = bpy.context.object
lens.name = 'mouse_lens'
lib.set_materials(sensor, [dark])
lib.set_materials(lens, [dark])

# USB-C charging port on the nose front (wireless shell, wired charging).
nose_port = blade('mouse_port', (0.009, 0.004, 0.003), (0, -L / 2 + 0.008, 0.004))
nose_tongue = blade('mouse_port_tongue', (0.006, 0.002, 0.001), (0, -L / 2 + 0.008, 0.004))
lib.set_materials(nose_port, [dark])
lib.set_materials(nose_tongue, [grey])

# --- Materials (created above, assigned here) ------------------------------------------------
lib.set_materials(shell, [white])
lib.set_materials(recess, [dark])
for b in thumbs:
    lib.set_materials(b, [grey])

body = lib.join([shell] + thumbs + [dpi] + skates + [nose_tongue], 'mouse_body')
sensor_o = lib.join([sensor, lens, nose_port], 'mouse_sensor')
lib.set_materials(sensor_o, [dark])
group = [body, wheel, recess, sensor_o]
lib.recentre(group, 'base')
lib.unwrap_all(group)

for o in group:
    blo, bhi = lib.world_bounds([o])
    print(f'DBG {o.name}: x[{blo.x:+.4f},{bhi.x:+.4f}] y[{blo.y:+.4f},{bhi.y:+.4f}] z[{blo.z:+.4f},{bhi.z:+.4f}]')
print(f'mouse body {lib.tri_count(body)} tris')
lib.export(OUT, group)
