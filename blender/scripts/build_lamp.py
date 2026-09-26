"""
Desk lamp from the owner's STL.

Source: `assets/source/lamp-owner/lamp.stl` (owner-supplied, used with permission;
NOT CC0 — see assets/MANIFEST.md). A modern twin-bar LED panel lamp: round weighted
base, short stem, two thin parallel rods, ball joint, flat oval head.

What Blender does and why:
  * The STL is raw triangle soup (1758 verts, no shared verts, no UVs, no materials).
    Weld (remove_doubles 0.2mm), recalculate normals outward, shade smooth with sharp
    edges preserved (auto_smooth 34° body / 30° head).
  * Scale uniformly so total height is 0.60m (same as the previous lamp asset, so room
    placement, LAMP.scale and light height stay comparable), centre XY, base at Z=0.
  * Discard the owner's oval head (26.9 x 20.6 units = 359 x 275mm at height scale;
    equivalent dia 235mm). The room's light assumes a ~130mm circular diffuser
    (LAMP_DISK_RADIUS 0.065, disk shading, volumetric beam, spotlight cone). A 235mm
    oval would need a different light model and would dominate the desk. Instead,
    preserve the distinctive base+arm (twin bars, round base, ball joint) and remodel
    the head as a flat circular panel: outer radius 85mm, diffuser radius 73mm
    (glass), disk light radius 65mm — same as before, so lighting.ts is unchanged.
  * Base+stem (0..0.147m: disc + single post) scaled in XY about its own centre to
    176mm dia (same as before, so it fits the desk with the same margins). Rods+
    knuckle (0.147..0.54m) unscaled to preserve lean and joint. Joined and welded
    (3 verts merged at the 0.147m interface, no floating).
  * New head cantilevered forward 85mm (back edge over the knuckle, like the owner
    head which extends forward from the joint), centred in X for symmetry. A central
    neck (12mm radius, tip->seat, ~86mm) bridges the gap — side yokes at head width
    (±83mm) cannot grip the 60mm ball (miss by 9-94mm in X), so a neck like the
    owner's fused joint is used instead. Head reads as mounted, not floating
    (CHECK <0.07m, neck overlaps knuckle).
  * Materials renamed to the room's palette so desk.ts retint works unchanged:
    lamp_metal / lamp_dark / lamp_diffuser (same hex/rough/metal/emission as before).
    Base region (z<foot+0.05) dark, arm metal; head front (normal·beam>0.7) metal.
  * Clean UVs via smart project (STL has none; head cylinders have primitive UVs but
    smart-projected for consistency). No textures (colours only), so UVs are unused
    but present for pipeline consistency.
  * Export lamp_body + lamp_head + lamp_glass to OUT + sidecar with socket (light
    position at head face), beam (aim, same forward+down as before to keep pool on
    desk), headRadius 0.085. Follow with node scripts/optimize-glb.mjs (quantize).

Usage: ~/.local/bin/blender --background --factory-startup --python
  blender/scripts/build_lamp.py -- assets/source/lamp-owner/lamp.stl assets/processed/lamp.glb
"""
import bpy
import bmesh
import math
import mathutils
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

SRC, OUT = lib.argv()[0], lib.argv()[1]

TARGET_HEIGHT = 0.60
HEAD_RADIUS = 0.085
CUT_HEAD = 0.540
CUT_STEM = 0.147
BASE_TARGET_DIA = 0.176


def duplicate(obj, name):
    new = obj.copy()
    new.data = obj.data.copy()
    bpy.context.collection.objects.link(new)
    new.name = name
    return new


def delete_by_z(obj, z_min=None, z_max=None):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    to_del = []
    for v in bm.verts:
        z = v.co.z
        if z_min is not None and z < z_min - 1e-9:
            to_del.append(v)
        elif z_max is not None and z > z_max + 1e-9:
            to_del.append(v)
    if to_del:
        bmesh.ops.delete(bm, geom=to_del, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()
    bpy.context.view_layer.update()


def verts_bounds(obj):
    ws = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = mathutils.Vector((min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws)))
    hi = mathutils.Vector((max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws)))
    return lo, hi


def smart_uv(obj):
    lib.activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    try:
        bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.02)
    except Exception as e:
        print(f'  ! smart_project failed on {obj.name}: {e}')
    bpy.ops.object.mode_set(mode='OBJECT')


lib.reset()
print(f'IMPORT {SRC}')
bpy.ops.wm.stl_import(filepath=SRC)
full = [o for o in bpy.data.objects if o.type == 'MESH'][0]
print(f'SRC verts={len(full.data.vertices)} tris={lib.tri_count(full)}')
lo, hi = lib.world_bounds([full])
print(f'SRC bounds lo={tuple(round(c, 3) for c in lo)} hi={tuple(round(c, 3) for c in hi)}')
scale = TARGET_HEIGHT / (hi.z - lo.z)
print(f'SCALE {scale:.6f}')
full.scale = (scale,) * 3
lib.apply_transforms(full)
lo, hi = lib.world_bounds([full])
shift = mathutils.Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
for v in full.data.vertices:
    v.co += shift
full.data.update()
lib.clean(full)
print(f'AFTER CLEAN tris={lib.tri_count(full)}')

body = duplicate(full, 'body_tmp')
delete_by_z(body, z_max=CUT_HEAD)
print(f'BODY (no head) tris={lib.tri_count(body)}')

base = duplicate(body, 'base_tmp')
delete_by_z(base, z_max=CUT_STEM)
blo, bhi = verts_bounds(base)
base_dia = max(bhi.x - blo.x, bhi.y - blo.y)
f = BASE_TARGET_DIA / max(base_dia, 1e-9)
bcx, bcy = (blo.x + bhi.x) / 2, (blo.y + bhi.y) / 2
for v in base.data.vertices:
    v.co.x = bcx + (v.co.x - bcx) * f
    v.co.y = bcy + (v.co.y - bcy) * f
base.data.update()
bpy.context.view_layer.update()
print(f'BASE dia {base_dia:.4f} -> {BASE_TARGET_DIA} (f={f:.4f}) tris={lib.tri_count(base)}')

arm = duplicate(body, 'arm_tmp')
delete_by_z(arm, z_min=CUT_STEM)
print(f'ARM tris={lib.tri_count(arm)}')
lib.drop([full, body])

tip = max((arm.matrix_world @ v.co for v in arm.data.vertices), key=lambda c: c.z)
print(f'TIP {tuple(round(c, 4) for c in tip)}')

lamp_body = lib.join([arm, base], 'lamp_body')
lib.clean(lamp_body)
print(f'LAMP_BODY joined tris={lib.tri_count(lamp_body)}')
lib.bevel(lamp_body, width=0.0015, segments=2)
lib.apply_modifiers(lamp_body)
lib.clean(lamp_body)
print(f'LAMP_BODY beveled tris={lib.tri_count(lamp_body)}')
lib.shade_auto(lamp_body, 34)
smart_uv(lamp_body)

beam = mathutils.Vector((0.0, 0.72, -0.694)).normalized()
print(f'BEAM {tuple(round(c, 4) for c in beam)}')
quat = beam.to_track_quat('Z', 'Y')
euler = quat.to_euler()
seat = tip + mathutils.Vector((0.0, 0.085, -0.010))
print(f'SEAT {tuple(round(c, 4) for c in seat)}')


def cyl(name, radius, depth, loc, rot, verts_n=40):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts_n, radius=radius, depth=depth,
                                        location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    return o


rim = cyl('rim', HEAD_RADIUS, 0.030, seat, euler)
back = cyl('back', HEAD_RADIUS - 0.009, 0.034, seat - beam * 0.004, euler)
glass = cyl('lamp_glass', HEAD_RADIUS - 0.012, 0.004, seat + beam * 0.014, euler, 44)
neck_dir = (seat - tip)
neck_len = neck_dir.length
neck_mid = (tip + seat) / 2
neck_quat = neck_dir.normalized().to_track_quat('Z', 'Y')
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.012, depth=neck_len,
                                    location=neck_mid, rotation=neck_quat.to_euler())
neck = bpy.context.object
neck.name = 'neck'
print(f'NECK len {neck_len:.4f}m')

head = lib.join([rim, back, neck], 'lamp_head')
lib.bevel(head, width=0.0018, segments=2)
lib.apply_modifiers(head)
lib.clean(head)
lib.shade_auto(head, 30)
smart_uv(head)
smart_uv(glass)
print(f'HEAD {lib.tri_count(head)} GLASS {lib.tri_count(glass)} BODY {lib.tri_count(lamp_body)}')

metal = lib.material('lamp_metal', lib.hex_rgb('#b7bcc2'), roughness=0.34, metallic=1.0)
dark = lib.material('lamp_dark', lib.hex_rgb('#3a3e44'), roughness=0.46, metallic=0.85)
diffuser = lib.material('lamp_diffuser', lib.hex_rgb('#0a0a0a'), roughness=0.6,
                        emission=lib.hex_rgb('#ffd6a0'), emission_strength=1.0)
lib.set_materials(lamp_body, [metal, dark])
foot = min((lamp_body.matrix_world @ v.co).z for v in lamp_body.data.vertices)
lib.assign_slot(lamp_body, lambda c, n: c.z < foot + 0.05, 1)
lib.set_materials(head, [dark, metal])
lib.assign_slot(head, lambda c, n: n.dot(beam) > 0.7, 1)
lib.set_materials(glass, [diffuser])

for o in (lamp_body, head, glass):
    lib.apply_transforms(o)
group = [lamp_body, head, glass]
lo, hi = lib.world_bounds(group)
scale2 = TARGET_HEIGHT / (hi.z - lo.z)
print(f'FINAL SCALE {scale2:.5f}')
for o in group:
    o.scale = (scale2,) * 3
    lib.apply_transforms(o)
lo, hi = lib.world_bounds(group)
shift = mathutils.Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
for o in group:
    for v in o.data.vertices:
        v.co += shift
    o.data.update()

head_centre = sum((head.matrix_world @ v.co for v in head.data.vertices),
                  mathutils.Vector()) / len(head.data.vertices)
body_verts = [lamp_body.matrix_world @ v.co for v in lamp_body.data.vertices]
print(f'CHECK disc centre to nearest body vertex: '
      f'{min((head_centre - b).length for b in body_verts):.4f} m')
bot_slab = [v.co for v in lamp_body.data.vertices if abs(v.co.z - 0.147) < 0.006]
if bot_slab:
    bx = sum(v.x for v in bot_slab) / len(bot_slab)
    by = sum(v.y for v in bot_slab) / len(bot_slab)
    for zt, nm in [(0.17, 'medalFrom'), (0.40, 'medalTo')]:
        f2 = (zt - 0.147) / max(tip.z - 0.147, 1e-9)
        ax = bx + (tip.x - bx) * f2
        ay = by + (tip.y - by) * f2
        print(f'{nm} BLENDER ({ax:.5f},{ay:.5f},{zt:.5f}) '
              f'GLTF {lib.to_gltf(mathutils.Vector((ax, ay, zt)))}')

for o in group:
    blo, bhi = lib.world_bounds([o])
    print(f'DBG {o.name}: tris={lib.tri_count(o)} '
          f'z[{blo.z:.3f},{bhi.z:.3f}] y[{blo.y:.3f},{bhi.y:.3f}]')

lib.export(OUT, group)
lib.write_meta(OUT, {
    'socket': lib.to_gltf(head_centre + beam * 0.02),
    'beam': lib.to_gltf(beam),
    'headRadius': HEAD_RADIUS,
})
print('HEAD_WORLD', tuple(round(c, 4) for c in
      (lib.world_bounds([head])[0] + lib.world_bounds([head])[1]) / 2))
print('BEAM', tuple(round(c, 4) for c in beam))
