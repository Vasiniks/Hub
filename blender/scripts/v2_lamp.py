"""
Desk lamp: all-white plastic body and a CIRCULAR light (round diffuser + disk area light) under the head.
Run inside Blender with room.blend open:  exec(open(r"<repo>/blender/scripts/v2_lamp.py").read())
Idempotent: rebuilds collection NEW_lamp_light and reuses the lamp_white_plastic / lamp_diffuser materials.
Lamp parts (from the glTF export): lamp003 (stem/arms), lamp003_1 (base), Cylinder / Cylinder_1 (head), lamp_glass (old blade diffuser).
"""
import bpy, bmesh, math, mathutils

O = bpy.data.objects
sc = bpy.context.scene
HEAD_C = mathutils.Vector((-0.6385, 0.9425, 1.1772))   # underside centre of the head (world)
R = 0.034                                              # diffuser radius — fits inside the 80 mm head
WARM = (1.0, 0.86, 0.68)

# white plastic, lamp only (the rm_alu_* materials are shared with other objects)
m = bpy.data.materials.get('lamp_white_plastic') or bpy.data.materials.new('lamp_white_plastic')
m.use_nodes = True
nt = m.node_tree
p = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
p.inputs['Base Color'].default_value = (0.83, 0.83, 0.82, 1)
p.inputs['Roughness'].default_value = 0.33
if not any(n.type == 'BUMP' for n in nt.nodes):
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 1400
    b = nt.nodes.new('ShaderNodeBump'); b.inputs['Strength'].default_value = 0.03; b.inputs['Distance'].default_value = 0.0002
    nt.links.new(nz.outputs['Fac'], b.inputs['Height']); nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
for n in ('lamp003', 'lamp003_1', 'Cylinder', 'Cylinder_1'):
    o = O[n]
    if o.data.users > 1:
        o.data = o.data.copy()
    for s in o.material_slots:
        s.material = m
O['lamp_glass'].hide_render = True
O['lamp_glass'].hide_set(True)

# circular diffuser + disk light
col = bpy.data.collections.get('NEW_lamp_light') or bpy.data.collections.new('NEW_lamp_light')
if col.name not in sc.collection.children:
    sc.collection.children.link(col)
for o in list(col.objects):
    bpy.data.objects.remove(o, do_unlink=True)

em = bpy.data.materials.get('lamp_diffuser') or bpy.data.materials.new('lamp_diffuser')
em.use_nodes = True
ep = next(n for n in em.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
ep.inputs['Base Color'].default_value = (0.95, 0.95, 0.93, 1)
ep.inputs['Roughness'].default_value = 0.5
ep.inputs['Emission Color'].default_value = (*WARM, 1)
ep.inputs['Emission Strength'].default_value = 6.0

me = bpy.data.meshes.new('lamp_diffuser_disc')
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=True, radius=R, segments=48)
for f in bm.faces:
    f.normal_flip()                                   # emit downward
bm.to_mesh(me); bm.free()
me.materials.append(em)
disc = bpy.data.objects.new('lamp_diffuser_disc', me); col.objects.link(disc); disc.location = HEAD_C

ring = bpy.data.meshes.new('lamp_diffuser_ring')
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=False, radius=R + 0.004, segments=48)
bm.to_mesh(ring); bm.free()
ring.materials.append(m)
rg = bpy.data.objects.new('lamp_diffuser_ring', ring); col.objects.link(rg)
rg.location = HEAD_C + mathutils.Vector((0, 0, -0.0005))
sc_mod = rg.modifiers.new('bezel', 'SCREW'); sc_mod.angle = 0; sc_mod.screw_offset = 0.004; sc_mod.steps = 1; sc_mod.render_steps = 1

ld = bpy.data.lights.get('LAMP_disk') or bpy.data.lights.new('LAMP_disk', 'AREA')
ld.shape = 'DISK'; ld.size = 2 * R; ld.energy = 7.0; ld.color = WARM; ld.spread = math.radians(75)
lo = bpy.data.objects.new('LAMP_disk', ld); col.objects.link(lo)
lo.location = HEAD_C + mathutils.Vector((0, 0, -0.0015))   # area lights face -Z by default: straight down
print('lamp: white plastic + circular light')
