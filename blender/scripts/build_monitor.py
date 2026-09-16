"""
Monitor.

The bezel is the thing that needs Blender: the screen sits in a well cut into the front of the
housing with a boolean, so there is a real recessed edge that catches light and casts a thin
shadow onto the panel — rather than a dark rectangle laid on a slab. The back is a tapered
shell with a raised centre, which is what gives a monitor its profile from the side.

`monitor_screen` is exported as its own object so the runtime can put the Lorenz attractor on
it and hang the screen's area light off it.
"""
import bpy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]

PW, PH = 0.62, 0.365          # panel outline
BEZEL = 0.011                 # border around the image
DEPTH = 0.021

lib.reset()


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


# Blender is Z-up, and the glTF exporter converts Blender +Y to glTF -Z. So: up is +Z, and
# the screen faces -Y here to end up facing +Z in the room. Building this with Y as "up"
# (thinking in glTF terms) laid the whole monitor on its back.
BASE_H = 0.014
NECK_TOP = 0.215
PANEL_Z = NECK_TOP + PH / 2 - 0.03
FRONT_Y = -0.012                      # the panel's front face plane
SCREEN_Y = FRONT_Y - DEPTH / 2 + 0.0035

# --- Stand --------------------------------------------------------------------------------
base = cube('mon_base', (0.22, 0.15, BASE_H), (0, 0.03, BASE_H / 2))
lib.bevel(base, width=0.005, segments=3)
lib.apply_modifiers(base)
lib.shade_auto(base, 30)
pad = cube('mon_pad', (0.2, 0.13, 0.003), (0, 0.03, 0.0015))
neck = cube('mon_neck', (0.05, 0.026, NECK_TOP - BASE_H + 0.02), (0, 0, (NECK_TOP + BASE_H) / 2))
lib.bevel(neck, width=0.005, segments=2)
lib.apply_modifiers(neck)
bpy.ops.mesh.primitive_cylinder_add(vertices=18, radius=0.019, depth=0.05,
                                    location=(0, 0, NECK_TOP), rotation=(0, math.pi / 2, 0))
knuckle = bpy.context.object
knuckle.name = 'mon_knuckle'
lib.shade_auto(knuckle, 30)

# --- Housing ------------------------------------------------------------------------------
shell = cube('mon_shell', (PW, DEPTH, PH), (0, FRONT_Y, PANEL_Z))
# The screen well: a real recess, so the bezel has an inner edge that catches light.
cut(shell, [cube('well', (PW - BEZEL * 2, 0.008, PH - BEZEL * 2),
                 (0, FRONT_Y - DEPTH / 2 + 0.001, PANEL_Z))])
lib.bevel(shell, width=0.0012, segments=2, angle_deg=40)
lib.apply_modifiers(shell)
lib.shade_auto(shell, 26)

# Back: a shallower slab with a raised centre, which gives the monitor its side profile.
back = cube('mon_back', (PW - 0.06, 0.02, PH - 0.06), (0, FRONT_Y + DEPTH / 2 + 0.007, PANEL_Z + 0.006))
lib.bevel(back, width=0.004, segments=2)
lib.apply_modifiers(back)
lib.shade_auto(back, 30)
hump = cube('mon_hump', (0.12, 0.012, 0.09),
            (0, FRONT_Y + DEPTH / 2 + 0.016, PANEL_Z - PH * 0.22))
lib.bevel(hump, width=0.003, segments=2)
lib.apply_modifiers(hump)

# --- Screen -------------------------------------------------------------------------------
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


# A power LED on the lower bezel.
bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.0016, depth=0.001,
                                    location=(PW * 0.4, SCREEN_Y - 0.001, PANEL_Z - PH / 2 + 0.005),
                                    rotation=(math.pi / 2, 0, 0))
led = bpy.context.object
led.name = 'monitor_led'

# --- Materials ----------------------------------------------------------------------------
housing = lib.material('mon_housing', lib.hex_rgb('#15171a'), roughness=0.52)
metal = lib.material('mon_metal', lib.hex_rgb('#4c5157'), roughness=0.42, metallic=1.0)
panel = lib.material('mon_panel', lib.hex_rgb('#030405'), roughness=0.34,
                     emission=lib.hex_rgb('#ffffff'), emission_strength=1.0)
lit = lib.material('mon_led', lib.hex_rgb('#000000'), emission=lib.hex_rgb('#6dffa8'),
                   emission_strength=2.5)

body = lib.join([shell, back, hump], 'monitor_body')
lib.set_materials(body, [housing])
stand = lib.join([neck, knuckle, base, pad], 'monitor_stand')
lib.set_materials(stand, [metal])
lib.set_materials(screen, [panel])
lib.set_materials(led, [lit])

group = [body, stand, screen, led]
lib.recentre(group, 'base')

print(f'monitor body {lib.tri_count(body)} + stand {lib.tri_count(stand)} tris')
lib.export(OUT, group)
lib.write_meta(OUT, {
    'screenWidth': PW - BEZEL * 2 - 0.002,
    'screenHeight': PH - BEZEL * 2 - 0.002,
})
