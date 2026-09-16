"""
Desk lamp.

Source: Poly Haven `desk_lamp_arm_01` (CC0). The spring arm is excellent and not something
worth rebuilding by hand — real knuckles, springs, tension rods. Two things about it are
wrong for this room, so Blender fixes them rather than the asset being rejected:

  * the shade is a cone; this room's lamp has a flat circular head
  * it mounts with a desk clamp; this one stands on a weighted base

So: keep the arm, delete the shade and the clamp, model a flat circular head and a base, and
replace every material so the lamp answers the room's lighting rather than carrying its own.
"""
import bpy
import math
import mathutils
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

SRC, OUT = lib.argv()[0], lib.argv()[1]

# Boundaries in the source asset's own space, read off the loose-part report.
SHADE_ABOVE = 0.60
CLAMP_BELOW = 0.055
HEAD_RADIUS = 0.085          # flat circular head, 170mm across
TARGET_HEIGHT = 0.60         # the arm's height once it stands on its own base

lib.reset()
lib.import_any(SRC)
source = lib.meshes()[0]
parts = lib.split_loose(source)

keep, cut, shade = [], [], []
for o in parts:
    lo, hi = lib.world_bounds([o])
    z = (lo.z + hi.z) / 2
    if z > SHADE_ABOVE:
        shade.append(o)
        cut.append(o)
    elif z < CLAMP_BELOW:
        cut.append(o)
    else:
        keep.append(o)

# The replacement head goes exactly where the old shade was, pointing the way the old shade
# pointed. Deriving it from the arm instead kept missing: the arm reaches forward as well as
# up, so neither its highest vertex nor its highest knuckle is its end.
def _weighted_centre(objs):
    total = mathutils.Vector()
    weight = 0.0
    for o in objs:
        plo, phi = lib.world_bounds([o])
        w = max(1, sum(len(p.vertices) - 2 for p in o.data.polygons))
        total += ((plo + phi) / 2) * w
        weight += w
    return total / max(weight, 1e-6)

shade_centre = _weighted_centre(shade)
arm_upper = _weighted_centre([o for o in keep if lib.world_bounds([o])[1].z > SHADE_ABOVE - 0.09])
beam_dir = (shade_centre - arm_upper).normalized()
# The end of the arm is the kept part that sits furthest along the direction the shade used
# to point. The shade itself had a neck, so its centre is ~12cm past the metal it bolted to.
# The far end is the vertex that reaches furthest along the beam. Part *centres* sit behind
# their own extremity, which left the head 7cm short of the arm.
arm_end = max((o.matrix_world @ v.co for o in keep for v in o.data.vertices),
              key=lambda c: c.dot(beam_dir))
print(f'shade centre {tuple(round(c, 3) for c in shade_centre)}  '
      f'arm end {tuple(round(c, 3) for c in arm_end)}  '
      f'span {(shade_centre - arm_end).length:.3f}m')
print(f'arm parts kept {len(keep)}, shade/clamp removed {len(cut)}')
lib.drop(cut)

# Mount the head on the topmost knuckle, not on the highest vertex in the mesh. The highest
# vertex of a spring arm belongs to a spring or a screw that overshoots the structural end,
# which left the head hanging several centimetres off the tip.


arm = lib.join(keep, 'lamp_body')
lib.clean(arm)

# Optimise the arm BEFORE measuring where the head goes. Decimation shortens a thin spring
# arm by a few centimetres, and measuring first left the head floating off the end.
before = lib.tri_count(arm)
lib.decimate(arm, 0.45)
lib.apply_modifiers(arm)
lib.clean(arm)
print(f'arm {before} -> {lib.tri_count(arm)} tris')

mw = arm.matrix_world
verts = [mw @ v.co for v in arm.data.vertices]
tip = arm_end
# The head pivots on its yoke, so it is posed the way a desk lamp is actually aimed — forward
# and about 30 degrees down — rather than continuing the arm's direction, which points up and
# would throw the light at the ceiling.
beam = mathutils.Vector((0.0, 0.72, -0.694)).normalized()
print(f'head at {tuple(round(c, 3) for c in tip)}  beam {tuple(round(c, 3) for c in beam)}')


def cyl(name, radius, depth, loc, rot, verts_n=40):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts_n, radius=radius, depth=depth,
                                        location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    return o


# Orientation that takes +Z onto the beam direction.
quat = beam.to_track_quat('Z', 'Y')
euler = quat.to_euler()
# Seated on the arm end; the yoke reaches back over the metal.
seat = tip + mathutils.Vector((0.0, 0.018, -0.028))

# --- Flat circular head ----------------------------------------------------------------
rim = cyl('rim', HEAD_RADIUS, 0.030, seat, euler)
back = cyl('back', HEAD_RADIUS - 0.009, 0.034, seat - beam * 0.004, euler)
glass = cyl('lamp_glass', HEAD_RADIUS - 0.012, 0.004, seat + beam * 0.014, euler, 44)

# A yoke each side, so the head reads as mounted rather than stuck on.
side = beam.cross(mathutils.Vector((0, 0, 1))).normalized()
yokes = []
for s in (-1, 1):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=seat + side * s * (HEAD_RADIUS - 0.002)
                                    - beam * 0.022)
    y = bpy.context.object
    y.scale = (0.006, 0.016, 0.05)
    y.rotation_euler = euler
    y.name = f'yoke{s}'
    yokes.append(y)

head = lib.join([rim, back] + yokes, 'lamp_head')
lib.bevel(head, width=0.0018, segments=2)
lib.apply_modifiers(head)
lib.clean(head)

# --- Weighted base ---------------------------------------------------------------------
foot = min(v.z for v in verts)
base = cyl('base_disc', 0.088, 0.020, (0, 0, foot + 0.010), (0, 0, 0), 48)
collar = cyl('base_collar', 0.032, 0.026, (0, 0, foot + 0.032), (0, 0, 0), 28)
pad = cyl('base_pad', 0.090, 0.004, (0, 0, foot + 0.002), (0, 0, 0), 48)
base = lib.join([base, collar], 'base')
lib.bevel(base, width=0.0025, segments=2)
lib.apply_modifiers(base)

body = lib.join([arm, base, pad], 'lamp_body')
lib.clean(body)

# --- Shading -----------------------------------------------------------------------------
lib.shade_auto(body, 34)
lib.shade_auto(head, 30)
print(f'body {lib.tri_count(body)} tris, head {lib.tri_count(head)} tris')

# --- Materials -------------------------------------------------------------------------
metal = lib.material('lamp_metal', lib.hex_rgb('#b7bcc2'), roughness=0.34, metallic=1.0)
dark = lib.material('lamp_dark', lib.hex_rgb('#3a3e44'), roughness=0.46, metallic=0.85)
diffuser = lib.material('lamp_diffuser', lib.hex_rgb('#0a0a0a'), roughness=0.6,
                        emission=lib.hex_rgb('#ffd6a0'), emission_strength=1.0)
lib.set_materials(body, [metal, dark])
# The base reads darker than the arm, which is how these lamps are actually finished.
lib.assign_slot(body, lambda c, n: c.z < foot + 0.05, 1)
lib.set_materials(head, [dark, metal])
lib.assign_slot(head, lambda c, n: n.dot(beam) > 0.7, 1)
lib.set_materials(glass, [diffuser])

# --- Place for the room ------------------------------------------------------------------
for o in (body, head, glass):
    lib.apply_transforms(o)
group = [body, head, glass]
lo, hi = lib.world_bounds(group)
scale = TARGET_HEIGHT / (hi.z - lo.z)
for o in group:
    o.scale = (scale,) * 3
    lib.apply_transforms(o)
lo, hi = lib.world_bounds(group)
shift = mathutils.Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
for o in group:
    for v in o.data.vertices:
        v.co += shift
    o.data.update()

discs = [v for v in (head.matrix_world @ v.co for v in head.data.vertices)]
centre_of_disc = sum(discs, mathutils.Vector()) / len(discs)
body_verts = [body.matrix_world @ v.co for v in body.data.vertices]
print(f'CHECK disc centre to nearest arm vertex: '
      f'{min((centre_of_disc - b).length for b in body_verts):.4f} m')

for o in group:
    blo, bhi = lib.world_bounds([o])
    print(f'DBG {o.name}: loc={tuple(round(c,3) for c in o.location)} '
          f'scale={tuple(round(c,3) for c in o.scale)} '
          f'bounds z[{blo.z:.3f},{bhi.z:.3f}] y[{blo.y:.3f},{bhi.y:.3f}]')

# Where the light lives, for the runtime: at the face of the head, aimed along the beam.
head_centre = sum((o.matrix_world @ v.co for v in head.data.vertices), mathutils.Vector()) / len(head.data.vertices)
lib.export(OUT, group)
lib.write_meta(OUT, {
    'socket': lib.to_gltf(head_centre + beam * 0.02),
    'beam': lib.to_gltf(beam),
    'headRadius': HEAD_RADIUS,
})
print('HEAD_WORLD', tuple(round(c, 4) for c in (lib.world_bounds([head])[0] + lib.world_bounds([head])[1]) / 2))
print('BEAM', tuple(round(c, 4) for c in beam))
