"""
MacBook on an inclined riser.

Modelled rather than sourced — no CC0 laptop of the right kind exists. The parts that need
Blender are the ones the previous procedural version got wrong: the body is a single solid
with a real bevel all round (so the lid edge catches light along its whole length), the port
cutouts and the front lip notch are boolean recesses rather than dark boxes laid on the
surface, and the rear edge is a proper rounded hinge instead of a separate bar.

Everything is built in the deck's frame, then the whole assembly is tilted once — so the body
cannot intersect the arms no matter what the angle is.
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

W, D, T = 0.304, 0.212, 0.0165     # closed body
TILT = math.radians(16.5)          # slopes up and away from the visitor
ARM_X = 0.131

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
        m = target.modifiers.new('cut', 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.object = c
        m.solver = 'EXACT'
    lib.apply_modifiers(target)
    lib.drop(cutters)


# --- Body -------------------------------------------------------------------------------
body = cube('mb_body', (W, D, T), (0, 0, T / 2))
# Port recesses on the left flank, an HDMI recess on the right, and the finger
# notch under the front edge.
cut(body, [
    *[cube(f'port{i}', (0.006, 0.016, 0.0038), (-W / 2, pz, T * 0.52))
      for i, pz in enumerate((-0.03, 0.006, 0.042))],
    cube('port_hdmi', (0.006, 0.018, 0.0042), (W / 2, -0.02, T * 0.52)),
    cube('notch', (0.058, 0.008, 0.0045), (0, D / 2, T * 0.5)),
])
lib.bevel(body, width=0.0016, segments=3, angle_deg=35)
lib.apply_modifiers(body)
lib.shade_auto(body, 28)

# Lid inset: a hair-proud panel on the lid top, so the hero specular surface has
# an edge that catches the window along its whole length.
lid = cube('mb_lid', (W - 0.012, D - 0.012, 0.0008), (0, 0, T + 0.0002))
lib.bevel(lid, width=0.0004, segments=2, angle_deg=35)
lib.apply_modifiers(lid)
lib.shade_auto(lid, 28)

# Bottom gasket + rubber feet + screws: what a closed laptop actually shows
# from a low seated angle.
gasket = cube('mb_gasket', (W - 0.02, D - 0.02, 0.0006), (0, 0, 0.0003))
rb_feet = [cube(f'mb_foot{sx}{sy}', (0.024, 0.008, 0.0015),
                (sx * (W / 2 - 0.03), sy * (D / 2 - 0.02), -0.0005))
           for sx in (-1, 1) for sy in (-1, 1)]
screws = [cube(f'mb_screw{i}', (0.0024, 0.0024, 0.0005),
               (sx * (W / 2 - 0.012), sy * (D / 2 - 0.010), 0.0002))
          for sx in (-1, 1) for sy in (-1, 1)
          for i in (0,)][:8]
# Port tongues inside the recesses, so the ports read as connectors, not holes.
tongues = ([cube(f'mb_tongue{i}', (0.004, 0.012, 0.0015), (-W / 2 + 0.0005, pz, T * 0.52))
            for i, pz in enumerate((-0.03, 0.006, 0.042))] +
           [cube('mb_tongue_hdmi', (0.004, 0.014, 0.0018), (W / 2 - 0.0005, -0.02, T * 0.52))])

# The lid/base seam, cut just deep enough to read as a line at arm's length.
seam = cube('mb_seam', (W + 0.01, D + 0.01, 0.0009), (0, 0, T * 0.52))
cut(body, [seam])
lib.shade_auto(body, 28)

# Rear hinge: a cylinder along the back edge, which is what a closed lid actually shows.
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=T * 0.5, depth=W - 0.03,
                                    location=(0, -D / 2 + T * 0.42, T / 2),
                                    rotation=(0, math.pi / 2, 0))
hinge = bpy.context.object
hinge.name = 'mb_hinge'
lib.shade_auto(hinge, 30)
# Hinge end caps: dark plugs closing the barrel ends.
hinge_caps = []
for s in (-1, 1):
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=T * 0.5 * 0.92, depth=0.003,
                                        location=(s * (W - 0.03) / 2, -D / 2 + T * 0.42, T / 2),
                                        rotation=(0, math.pi / 2, 0))
    c = bpy.context.object
    c.name = f'mb_hingecap{s}'
    lib.shade_auto(c, 30)
    hinge_caps.append(c)

# --- Riser ------------------------------------------------------------------------------
# Side profile: back post, deck line falling toward the visitor, short front lip.
BACK_Y, FRONT_Y = -0.112, 0.104
BACK_Z, FRONT_Z = 0.086, 0.022
profile = [
    (BACK_Y, 0.004), (BACK_Y, BACK_Z), (FRONT_Y - 0.012, FRONT_Y * 0 + FRONT_Z),
    (FRONT_Y, FRONT_Z + 0.005), (FRONT_Y + 0.006, FRONT_Z + 0.005),
    (FRONT_Y + 0.006, 0.004),
]
# Build the profile as an actual n-gon. Converting a POLY curve gives edges with no face,
# so solidify had nothing to thicken and the arms came out empty.
arms = []
for side in (-1, 1):
    bm = bmesh.new()
    # Built straight into the YZ plane, so solidify thickens across the room (X) and no
    # rotation is needed. Building it flat and rotating afterwards laid the arms on their side.
    verts = [bm.verts.new((0.0, y, z)) for y, z in profile]
    bm.faces.new(verts)
    me = bpy.data.meshes.new(f'arm{side}')
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(f'arm{side}', me)
    bpy.context.collection.objects.link(o)
    lib.activate(o)
    lib.solidify(o, 0.016)
    lib.apply_modifiers(o)
    o.location = (side * ARM_X, 0, 0)
    lib.apply_transforms(o)
    lib.bevel(o, width=0.0012, segments=2)
    lib.apply_modifiers(o)
    lib.shade_auto(o, 34)
    arms.append(o)

brace = cube('mb_brace', (0.24, 0.026, 0.01), (0, BACK_Y + 0.03, 0.058), (TILT, 0, 0))
feet = [cube(f'foot{side}{i}', (0.02, 0.03, 0.005), (side * ARM_X, fy, 0.0025))
        for side in (-1, 1) for i, fy in enumerate((BACK_Y + 0.022, FRONT_Y - 0.026))]
def deck_z(y):
    """Height of the deck line at a given depth, from the two profile corners."""
    return BACK_Z + (y - BACK_Y) * (FRONT_Z - BACK_Z) / (FRONT_Y - BACK_Y)


# Grip strips where the body touches the deck, sunk so the body rests on them rather than
# hovering over a visible bar.
grips = [cube(f'grip{i}', (0.2, 0.014, 0.0022), (0, gy, deck_z(gy) - 0.0018), (TILT, 0, 0))
         for i, gy in enumerate((-0.07, 0.06))]

# --- Seat the body on the deck ------------------------------------------------------------
deck_mid_y = (BACK_Y + FRONT_Y) / 2
deck_mid_z = (BACK_Z + FRONT_Z) / 2
laptop = lib.join([body, hinge, lid, gasket] + rb_feet + screws + tongues + hinge_caps, 'macbook_body')
laptop.rotation_euler = (TILT, 0, 0)
laptop.location = (0, deck_mid_y, deck_mid_z - 0.0012)
lib.apply_transforms(laptop)
stand = lib.join(arms + [brace] + feet + grips, 'macbook_stand')
lib.shade_auto(stand, 34)

# --- Materials ---------------------------------------------------------------------------
alu = lib.material('mb_alu', lib.hex_rgb('#b7bcc2'), roughness=0.3, metallic=1.0)
dark = lib.material('mb_dark', lib.hex_rgb('#4c5157'), roughness=0.42, metallic=1.0)
rubber = lib.material('mb_rubber', lib.hex_rgb('#0e0f11'), roughness=0.9)
lib.set_materials(laptop, [alu, dark])
lib.assign_slot(laptop, lambda c, n: abs(n.z) < 0.55 and c.z < deck_mid_z + T * 0.9, 1)
# Underside hardware: bottom faces near the base plane go dark, rubber feet to rubber.
lib.assign_slot(laptop, lambda c, n: n.z < -0.9 and c.z < 0.002, 1)
# Rubber feet keep the housing's dark side-band assignment (vertical faces read
# dark via the predicate above); their undersides face the stand and are never
# seen, so the laptop stays a two-slot object exactly like the original.
laptop.data.update()
lib.set_materials(stand, [alu, rubber])
lib.assign_slot(stand, lambda c, n: c.z < 0.008, 1)

group = [laptop, stand]
lib.recentre(group, 'base')
lib.unwrap_all(group)
print(f'macbook {lib.tri_count(laptop)} + stand {lib.tri_count(stand)} tris')
lib.export(OUT, group)
