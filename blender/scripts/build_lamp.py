"""
Desk lamp from the owner's STL, with blade head.

Source: `assets/source/lamp-owner/lamp.stl` (owner-supplied, used with permission;
NOT CC0 — see assets/MANIFEST.md). A modern twin-bar LED lamp: round weighted
base, short stem, two parallel rods, ball joint, flat oval blade head.

What Blender does and why:
  * The STL is raw triangle soup (1758 verts, no shared verts, no UVs, no materials).
    Weld (remove_doubles 0.2mm), recalculate normals outward, shade smooth with sharp
    edges preserved (auto_smooth 34° body / 30° head).
  * Scale uniformly so total height is 0.60m, centre XY, base at Z=0 (same as before,
    so placement/scale comparable).
  * Discard the owner's oval head above Z=0.52m (head starts ~0.52m, knuckle ball
    0.505-0.52m kept; previous CUT_HEAD 0.54 left a 20mm head sliver in the body).
    Preserve base+stem (0..0.147m: disc + single post) scaled XY about its own centre
    to 190mm dia (was 176mm, +14mm for weight; keeps ~5mm back margin at same lamp
    position, more with lamp moved forward). Rods+knuckle (0.147..0.52m) thickened
    by scaling cross-section 1.35x about arm centre (twin bars read spindly at seated
    distance; gap widens proportionally, still recognisably twin-bar) to add substance
    while staying recognisably the owner's design.
  * New blade head 300mm long x 80mm wide x 14mm thick (brief: 300x80x12-16mm),
    flat oval (ellipse cylinder 48 verts) horizontal with 6° nose-down tilt (owner's
    slight downward tilt), cantilevered forward so back edge sits over the knuckle
    (centre = tip + 150mm forward, 15mm down; back edge ~touching tip, front 30mm
    below tip). Reads as modern LED bar, not dish. Housing (metal/dark) + diffuser
    panel on underside (60x270x4mm, 1mm proud, lamp_diffuser so bar reads lit from
    desk POV). Central neck r=14mm (was 12mm) tip->blade back, short (~30mm),
    overlaps knuckle (mounted, not floating).
  * Light: disk at blade centre (socket = blade centre + beam*0.01, just below
    diffuser face), disk radius 0.040m (blade short axis, was 0.065), beam flatter
    (0,0.80,-0.60) vs old (0,0.72,-0.694) to throw pool back to old central spot
    (old pool 0.66m from new head vs 0.49m throw with old beam; flatter 37° vs 44°
    gives 0.63m throw, plus blade 65mm forward + lamp 15mm forward = hits old pool).
    LAMP_ANGLE widened 0.52->0.55 to cover same pool with smaller disk
    (tan(new)=tan(old)+0.025/d).
  * Materials renamed to room palette so desk.ts retint works unchanged:
    lamp_metal / lamp_dark / lamp_diffuser (same hex/rough/metal/emission as before).
  * Clean UVs via smart project (STL has none). No textures (colours only).
  * Export lamp_body + lamp_head + lamp_glass to OUT + sidecar with socket (light
    position at diffuser face), beam (aim), headRadius 0.04. Follow with
    node scripts/optimize-glb.mjs (quantize). Base kept at origin XY (not group
    centred, so long blade does not push base off desk); base at Z=0.

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
CUT_HEAD = 0.520
CUT_STEM = 0.147
BASE_TARGET_DIA = 0.190
ARM_THICKEN = 1.35
BLADE_LONG = 0.300
BLADE_WIDE = 0.080
BLADE_THICK = 0.014
BLADE_TILT_DEG = 6.0
BLADE_FWD = 0.150
BLADE_DOWN = 0.015
NECK_RADIUS = 0.014
HEAD_DISK_RADIUS = 0.040


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
print(f'BODY (no head, cut {CUT_HEAD}) tris={lib.tri_count(body)}')

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
print(f'ARM before thicken tris={lib.tri_count(arm)}')
alo, ahi = verts_bounds(arm)
acx, acy = (alo.x + ahi.x) / 2, (alo.y + ahi.y) / 2
for v in arm.data.vertices:
    v.co.x = acx + (v.co.x - acx) * ARM_THICKEN
    v.co.y = acy + (v.co.y - acy) * ARM_THICKEN
arm.data.update()
bpy.context.view_layer.update()
print(f'ARM thickened x{ARM_THICKEN} about ({acx:.4f},{acy:.4f}) tris={lib.tri_count(arm)}')
lib.drop([full, body])

tip = max((arm.matrix_world @ v.co for v in arm.data.vertices), key=lambda c: c.z)
print(f'TIP {tuple(round(c, 4) for c in tip)}')

lamp_body = lib.join([arm, base], 'lamp_body')
lib.clean(lamp_body)
print(f'LAMP_BODY joined tris={lib.tri_count(lamp_body)}')
lib.bevel(lamp_body, width=0.0025, segments=2)
lib.apply_modifiers(lamp_body)
lib.clean(lamp_body)
print(f'LAMP_BODY beveled tris={lib.tri_count(lamp_body)}')
lib.shade_auto(lamp_body, 34)
smart_uv(lamp_body)

# Flatter beam than before (37 deg down vs 44) to throw pool back to old central spot.
beam = mathutils.Vector((0.0, 0.80, -0.60)).normalized()
print(f'BEAM {tuple(round(c, 4) for c in beam)}')
tilt = math.radians(BLADE_TILT_DEG)
# Blade centre: forward +Y, down -Z from tip; back edge ~touching tip.
blade_centre = tip + mathutils.Vector((0.0, BLADE_FWD, -BLADE_DOWN))
print(f'BLADE_CENTRE {tuple(round(c, 4) for c in blade_centre)}')
rot = ( -tilt, 0.0, 0.0)


def oval(name, sx, sy, thick, loc, rot_euler, verts_n=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts_n, radius=1.0, depth=thick,
                                        location=loc, rotation=rot_euler)
    o = bpy.context.object
    o.name = name
    # Scale XY to ellipse (cylinder axis is Z = thickness).
    for v in o.data.vertices:
        v.co.x *= sx
        v.co.y *= sy
    o.data.update()
    bpy.context.view_layer.update()
    return o


housing = oval('housing', BLADE_WIDE / 2, BLADE_LONG / 2, BLADE_THICK,
               blade_centre, rot)
# Diffuser panel on underside, 1mm proud below housing.
diff_loc = blade_centre + mathutils.Vector((0.0, 0.0, -0.006))
glass = oval('lamp_glass', 0.030, 0.135, 0.004, diff_loc, rot)
# Short neck tip -> blade back (back edge centreline).
blade_back = blade_centre + mathutils.Vector((0.0, -BLADE_LONG / 2 + 0.015, 0.008))
neck_dir = (blade_back - tip)
neck_len = neck_dir.length
neck_mid = (tip + blade_back) / 2
neck_quat = neck_dir.normalized().to_track_quat('Z', 'Y')
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=NECK_RADIUS, depth=neck_len,
                                    location=neck_mid, rotation=neck_quat.to_euler())
neck = bpy.context.object
neck.name = 'neck'
print(f'NECK len {neck_len:.4f}m tip->back')

head = lib.join([housing, neck], 'lamp_head')
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
# Keep base at origin XY (long blade must not push base off desk); base at Z=0.
bl = min((lamp_body.matrix_world @ v.co for v in lamp_body.data.vertices), key=lambda c: c.z)
base_verts = [lamp_body.matrix_world @ v.co for v in lamp_body.data.vertices if v.co.z < foot + 0.06]
bcx2 = sum(v.x for v in base_verts) / len(base_verts)
bcy2 = sum(v.y for v in base_verts) / len(base_verts)
lo, hi = lib.world_bounds(group)
shift = mathutils.Vector((-bcx2, -bcy2, -lo.z))
print(f'BASE_CENTRE ({bcx2:.4f},{bcy2:.4f}) SHIFT {tuple(round(c, 4) for c in shift)}')
for o in group:
    for v in o.data.vertices:
        v.co += shift
    o.data.update()

head_centre = sum((head.matrix_world @ v.co for v in head.data.vertices),
                  mathutils.Vector()) / len(head.data.vertices)
glass_centre = sum((glass.matrix_world @ v.co for v in glass.data.vertices),
                   mathutils.Vector()) / len(glass.data.vertices)
body_verts = [lamp_body.matrix_world @ v.co for v in lamp_body.data.vertices]
print(f'CHECK head centre to nearest body vertex: '
      f'{min((head_centre - b).length for b in body_verts):.4f} m')
print(f'CHECK glass centre to nearest body vertex: '
      f'{min((glass_centre - b).length for b in body_verts):.4f} m')
print(f'CHECK blade back to body: '
      f'{min(((blade_back + shift) - b).length for b in [(lamp_body.matrix_world @ v.co) for v in lamp_body.data.vertices]):.4f} m')
bot_slab = [v.co for v in lamp_body.data.vertices if abs(v.co.z - 0.147) < 0.006]
if bot_slab:
    bx = sum(v.x for v in bot_slab) / len(bot_slab)
    by = sum(v.y for v in bot_slab) / len(bot_slab)
    tip2 = max((lamp_body.matrix_world @ v.co for v in lamp_body.data.vertices), key=lambda c: c.z)
    for zt, nm in [(0.17, 'medalFrom'), (0.40, 'medalTo')]:
        f2 = (zt - 0.147) / max(tip2.z - 0.147, 1e-9)
        ax = bx + (tip2.x - bx) * f2
        ay = by + (tip2.y - by) * f2
        print(f'{nm} BLENDER ({ax:.5f},{ay:.5f},{zt:.5f}) '
              f'GLTF {lib.to_gltf(mathutils.Vector((ax, ay, zt)))}')

for o in group:
    blo, bhi = lib.world_bounds([o])
    print(f'DBG {o.name}: tris={lib.tri_count(o)} '
          f'z[{blo.z:.3f},{bhi.z:.3f}] y[{blo.y:.3f},{bhi.y:.3f}] x[{blo.x:.3f},{bhi.x:.3f}]')

lib.export(OUT, group)
lib.write_meta(OUT, {
    'socket': lib.to_gltf(glass_centre + beam * 0.01),
    'beam': lib.to_gltf(beam),
    'headRadius': HEAD_DISK_RADIUS,
})
print('HEAD_WORLD', tuple(round(c, 4) for c in
      (lib.world_bounds([head])[0] + lib.world_bounds([head])[1]) / 2))
print('BEAM', tuple(round(c, 4) for c in beam))
