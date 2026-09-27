"""
Monitor (remodel).

Mount points preserved exactly: PW/PH/BEZEL/DEPTH, FRONT_Y/SCREEN_Y/PANEL_Z,
NECK_TOP/BASE_H, `monitor_screen` quad, `monitor_led` position, sidecar
screenWidth/screenHeight. The runtime swaps the screen quad for its own plane
at `partCenter()` and hangs the area light off it, so none of those move.

What the remodel adds over the first version:
  * front: inner bezel chamfer frame (a real 45-degree inner edge that catches
    light) + power button under the chin next to the LED;
  * back: vent slots across the upper back, VESA 100 boss quartet + screws on a
    mount plaque, rear I/O recess (HDMI/DP/USB-C) with tongues, display cable
    dropping from the I/O to the desk;
  * stand: tapered two-piece neck, tilt barrel with end caps, hinge cover,
    cable-management clip, weighted base with rubber feet;
  * UVMap + reserved Lightmap channel on every mesh (remodel convention).
"""
import bpy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]

PW, PH = 0.62, 0.365          # panel outline (mount point: do not change)
BEZEL = 0.011                 # border around the image (mount point)
DEPTH = 0.021

lib.reset()


def cube(name, size, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    lib.apply_transforms(o)
    return o


def cyl(name, r, depth, loc, rot=(0, 0, 0), verts=18):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth,
                                        location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
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


def tube(name, points, radius, resolution=2):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = resolution
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


# Blender is Z-up, and the glTF exporter converts Blender +Y to glTF -Z. So: up is +Z, and
# the screen faces -Y here to end up facing +Z in the room.
BASE_H = 0.014                # mount point
NECK_TOP = 0.215              # mount point
PANEL_Z = NECK_TOP + PH / 2 - 0.03   # mount point
FRONT_Y = -0.012              # the panel's front face plane (mount point)
SCREEN_Y = FRONT_Y - DEPTH / 2 + 0.0035  # mount point
BACK_Y = FRONT_Y + DEPTH / 2

# --- Stand --------------------------------------------------------------------------------
# Weighted base: wider bevelled slab with a front chamfer that catches the window.
base = cube('mon_base', (0.22, 0.15, BASE_H), (0, 0.03, BASE_H / 2))
lib.bevel(base, width=0.005, segments=3)
lib.apply_modifiers(base)
lib.shade_auto(base, 30)
pad = cube('mon_pad', (0.2, 0.13, 0.003), (0, 0.03, 0.0015))
# Rubber feet under the base (join the housing: same dark plastic).
feet = [cube(f'mon_foot{sx}{sy}', (0.024, 0.024, 0.0025),
             (sx * 0.085, 0.03 + sy * 0.055, -0.001))
        for sx in (-1, 1) for sy in (-1, 1)]
for f in feet:
    lib.bevel(f, width=0.0008, segments=2)
    lib.apply_modifiers(f)
# Tapered two-piece neck: wider lower section flowing into the tilt barrel.
neck_lo = cube('mon_neck_lo', (0.058, 0.03, 0.10), (0, 0.005, BASE_H + 0.05))
neck_hi = cube('mon_neck_hi', (0.046, 0.024, NECK_TOP - BASE_H - 0.06),
               (0, 0.0, (NECK_TOP + BASE_H + 0.04) / 2))
for n in (neck_lo, neck_hi):
    lib.bevel(n, width=0.005, segments=2)
    lib.apply_modifiers(n)
    lib.shade_auto(n, 30)
# Cable-management clip on the back of the neck.
clip = cube('mon_clip', (0.02, 0.008, 0.03), (0, 0.024, 0.10))
lib.bevel(clip, width=0.002, segments=2)
lib.apply_modifiers(clip)
# Tilt barrel + end caps + hinge cover where the neck meets the panel.
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.019, depth=0.05,
                                    location=(0, 0, NECK_TOP), rotation=(0, math.pi / 2, 0))
knuckle = bpy.context.object
knuckle.name = 'mon_knuckle'
lib.shade_auto(knuckle, 30)
caps = [cyl(f'mon_cap{s}', 0.0195, 0.004, (s * 0.026, 0, NECK_TOP),
            rot=(0, math.pi / 2, 0)) for s in (-1, 1)]
hinge_cover = cube('mon_hinge_cover', (0.07, 0.03, 0.05), (0, 0.012, NECK_TOP - 0.005))
lib.bevel(hinge_cover, width=0.006, segments=2)
lib.apply_modifiers(hinge_cover)

# --- Housing ------------------------------------------------------------------------------
shell = cube('mon_shell', (PW, DEPTH, PH), (0, FRONT_Y, PANEL_Z))
# The screen well: a real recess, so the bezel has an inner edge that catches light.
cut(shell, [cube('well', (PW - BEZEL * 2, 0.008, PH - BEZEL * 2),
                 (0, FRONT_Y - DEPTH / 2 + 0.001, PANEL_Z))])
lib.bevel(shell, width=0.0012, segments=2, angle_deg=40)
lib.apply_modifiers(shell)
lib.shade_auto(shell, 26)

# Inner bezel chamfer: a thin frame standing 0.5 mm proud of the front face with a
# 45-degree inner edge, so the screen sits inside two catching edges, not one.
frame_t, frame_w = 0.0035, 0.0025
fz = FRONT_Y - DEPTH / 2 - 0.0004
sw, sh = PW - BEZEL * 2, PH - BEZEL * 2
frame_parts = [
    cube('bez_top', (sw + frame_w * 2, 0.002, frame_t), (0, fz, PANEL_Z + sh / 2 + frame_w / 2)),
    cube('bez_bot', (sw + frame_w * 2, 0.002, frame_t), (0, fz, PANEL_Z - sh / 2 - frame_w / 2)),
    cube('bez_l', (frame_w, 0.002, sh), (-sw / 2 - frame_w / 2, fz, PANEL_Z)),
    cube('bez_r', (frame_w, 0.002, sh), (sw / 2 + frame_w / 2, fz, PANEL_Z)),
]
for f in frame_parts:
    lib.bevel(f, width=0.0008, segments=2, angle_deg=30)
    lib.apply_modifiers(f)

# Back: a shallower slab with a raised centre, which gives the monitor its side profile.
back = cube('mon_back', (PW - 0.06, 0.02, PH - 0.06), (0, BACK_Y + 0.007, PANEL_Z + 0.006))
# Vent slots across the upper back, cut before the bevel.
vents = [cube(f'vent{i}', (0.15, 0.022, 0.0055), (0, BACK_Y + 0.007, PANEL_Z + 0.055 + i * 0.011))
         for i in range(6)]
# Rear I/O recess, lower-left of the back.
io_cut = cube('io_cut', (0.075, 0.022, 0.02), (0.14, BACK_Y + 0.007, PANEL_Z - 0.10))
cut(back, vents + [io_cut])
lib.bevel(back, width=0.004, segments=2)
lib.apply_modifiers(back)
lib.shade_auto(back, 30)
hump = cube('mon_hump', (0.12, 0.012, 0.09),
            (0, BACK_Y + 0.016, PANEL_Z - PH * 0.22))
lib.bevel(hump, width=0.003, segments=2)
lib.apply_modifiers(hump)

# VESA 100 plaque + four bosses + screw heads, centred on the back.
vesa_y = BACK_Y + 0.017
plaque = cube('vesa_plaque', (0.13, 0.006, 0.13), (0, vesa_y, PANEL_Z - 0.02))
lib.bevel(plaque, width=0.002, segments=2)
lib.apply_modifiers(plaque)
bosses = [cyl(f'vesa_boss{i}', 0.008, 0.008, (sx * 0.05, vesa_y + 0.004, PANEL_Z - 0.02 + sy * 0.05),
               rot=(math.pi / 2, 0, 0), verts=14)
          for sx in (-1, 1) for i, sy in enumerate((-1, 1))]
screws = [cyl(f'vesa_screw{i}', 0.0032, 0.010, (sx * 0.05, vesa_y + 0.004, PANEL_Z - 0.02 + sy * 0.05),
               rot=(math.pi / 2, 0, 0), verts=10)
          for sx in (-1, 1) for i, sy in enumerate((-1, 1))]

# I/O ports sitting in the recess: HDMI + DisplayPort + USB-C shells with tongues.
io_parts, io_dark = [], []
for i, (w, h, dx) in enumerate([(0.0148, 0.005, -0.024), (0.0165, 0.005, 0.0), (0.009, 0.0032, 0.024)]):
    shell_p = cube(f'io_shell{i}', (w, 0.008, h), (0.14 + dx, BACK_Y + 0.004, PANEL_Z - 0.10))
    tongue = cube(f'io_tongue{i}', (w - 0.003, 0.004, h - 0.002),
                  (0.14 + dx, BACK_Y + 0.004, PANEL_Z - 0.10 - 0.0005))
    io_parts.append(shell_p)
    io_dark.append(tongue)

# Display cable: leaves the I/O recess, bows out past the neck, lands on the desk.
cable = tube('monitor_cable',
             [(0.164, BACK_Y + 0.002, PANEL_Z - 0.10),
              (0.185, 0.035, 0.16),
              (0.150, 0.055, 0.045),
              (0.120, 0.060, 0.001)], 0.0028)
lib.shade_auto(cable, 40)

# Power button under the chin, beside the LED position (mount point kept exact).
button = cyl('mon_button', 0.0028, 0.002, (PW * 0.4 - 0.012, SCREEN_Y - 0.001, PANEL_Z - PH / 2 + 0.005),
             rot=(math.pi / 2, 0, 0), verts=14)

# --- Screen (mount point: position, size, name all frozen) ---------------------------------
bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
screen = bpy.context.object
screen.name = 'monitor_screen'
screen.scale = (PW - BEZEL * 2 - 0.002, PH - BEZEL * 2 - 0.002, 1)
lib.apply_transforms(screen)
# Stand it up facing -Y, which is the room's +Z. The opposite sign points the plane into the
# housing, and with front-face culling the screen simply renders black.
screen.rotation_euler = (math.pi / 2, 0, 0)
screen.location = (0, SCREEN_Y, PANEL_Z)
lib.apply_transforms(screen)


# A power LED on the lower bezel (mount point: exact position kept).
bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.0016, depth=0.001,
                                    location=(PW * 0.4, SCREEN_Y - 0.001, PANEL_Z - PH / 2 + 0.005),
                                    rotation=(math.pi / 2, 0, 0))
led = bpy.context.object
led.name = 'monitor_led'

# --- Materials (names are the runtime retint contract) --------------------------------------
housing = lib.material('mon_housing', lib.hex_rgb('#15171a'), roughness=0.52)
metal = lib.material('mon_metal', lib.hex_rgb('#4c5157'), roughness=0.42, metallic=1.0)
dark = lib.material('mon_dark', lib.hex_rgb('#0a0b0d'), roughness=0.7)
panel = lib.material('mon_panel', lib.hex_rgb('#030405'), roughness=0.34,
                     emission=lib.hex_rgb('#ffffff'), emission_strength=1.0)
lit = lib.material('mon_led', lib.hex_rgb('#000000'), emission=lib.hex_rgb('#6dffa8'),
                   emission_strength=2.5)

body = lib.join([shell, back, hump, plaque] + bosses + frame_parts + feet + [button], 'monitor_body')
lib.set_materials(body, [housing])
screws_o = lib.join(screws, 'monitor_screws')
lib.set_materials(screws_o, [metal])
stand = lib.join([neck_lo, neck_hi, clip, knuckle, hinge_cover, base, pad] + caps, 'monitor_stand')
lib.set_materials(stand, [metal])
io = lib.join(io_parts, 'monitor_io')
lib.set_materials(io, [metal])
io_t = lib.join(io_dark, 'monitor_io_tongues')
lib.set_materials(io_t, [dark])
lib.set_materials(cable, [dark])
lib.set_materials(screen, [panel])
lib.set_materials(led, [lit])

group = [body, screws_o, stand, io, io_t, cable, screen, led]
lib.recentre(group, 'base')
lib.unwrap_all(group)

for o in group:
    print(f'  {o.name}: {lib.tri_count(o)} tris')
print(f'monitor body {lib.tri_count(body)} + stand {lib.tri_count(stand)} tris')
lib.export(OUT, group)
lib.write_meta(OUT, {
    'screenWidth': PW - BEZEL * 2 - 0.002,
    'screenHeight': PH - BEZEL * 2 - 0.002,
})
