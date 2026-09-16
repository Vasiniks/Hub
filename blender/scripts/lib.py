"""
Shared pipeline helpers.

The point of this file is that asset preparation is repeatable: every build script imports
these, so scale normalisation, cleanup, material authoring, optimisation and export behave
identically for every object and a future asset swap is a small edit rather than a rewrite.

Conventions for everything exported from here:
  * metres, Y-up (glTF), origin at the object's natural resting point (usually its base)
  * -Z is the direction the object faces in the room
  * materials are simple PBR (base colour / roughness / metallic), authored to the room's
    palette, so imported assets do not arrive with their own lighting response
"""
import bpy
import bmesh
import math
import os
import sys
import mathutils


# --------------------------------------------------------------------------- scene


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_any(path):
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext in ('.gltf', '.glb'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f'unsupported source format: {ext}')
    return [o for o in bpy.data.objects if o not in before]


def meshes():
    return [o for o in bpy.data.objects if o.type == 'MESH']


def deselect():
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = None


def activate(obj):
    deselect()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


# --------------------------------------------------------------------------- geometry


def world_bounds(objs):
    lo = mathutils.Vector((1e9,) * 3)
    hi = mathutils.Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            lo = mathutils.Vector(map(min, lo, w))
            hi = mathutils.Vector(map(max, hi, w))
    return lo, hi


def split_loose(obj):
    """Break one mesh into its disconnected shells, so parts can be judged individually."""
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    return meshes()


def drop(objs):
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)


def join(objs, name):
    objs = [o for o in objs if o.type == 'MESH']
    if not objs:
        return None
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    return obj


def apply_transforms(obj):
    activate(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def recentre(obj, mode='base'):
    """Move the mesh so the origin sits where the object naturally rests."""
    apply_transforms(obj)
    lo, hi = world_bounds([obj])
    mid = (lo + hi) / 2
    offset = mathutils.Vector((-mid.x, -mid.y, -lo.z if mode == 'base' else -mid.z))
    me = obj.data
    for v in me.vertices:
        v.co += offset
    me.update()


def scale_to(obj, axis, target):
    """Uniformly scale so one dimension measures `target` metres. Real objects have a size."""
    apply_transforms(obj)
    lo, hi = world_bounds([obj])
    size = {'x': hi.x - lo.x, 'y': hi.y - lo.y, 'z': hi.z - lo.z}[axis]
    if size <= 1e-9:
        return
    obj.scale = (target / size,) * 3
    apply_transforms(obj)


def clean(obj, merge=0.0002):
    """Weld doubles, drop loose geometry, make normals consistent and outward."""
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=merge)
    bpy.ops.mesh.delete_loose()
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')


def shade_auto(obj, angle_deg=32):
    """
    Smooth shading with a sharp-edge angle: the low-poly look depends on this, because it is
    what keeps a bevelled corner crisp while a cylinder stays round.
    """
    activate(obj)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_deg))
    except (AttributeError, RuntimeError):
        bpy.ops.object.shade_smooth()
        if hasattr(obj.data, 'use_auto_smooth'):
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = math.radians(angle_deg)


def bevel(obj, width=0.0012, segments=2, angle_deg=40, clamp=True):
    """A real bevel modifier. This is the single biggest reason Blender geometry reads better
    than primitive composition: every hard edge catches a highlight."""
    m = obj.modifiers.new('bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle_deg)
    m.use_clamp_overlap = clamp
    m.harden_normals = False
    return m


def solidify(obj, thickness, offset=-1.0):
    m = obj.modifiers.new('solidify', 'SOLIDIFY')
    m.thickness = thickness
    m.offset = offset
    return m


def decimate(obj, ratio):
    m = obj.modifiers.new('decimate', 'DECIMATE')
    m.ratio = ratio
    return m


def apply_modifiers(obj):
    activate(obj)
    for m in list(obj.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError as err:
            print(f'  ! could not apply {m.name} on {obj.name}: {err}')


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# --------------------------------------------------------------------------- materials


def material(name, colour, roughness=0.6, metallic=0.0, emission=None, emission_strength=1.0,
             alpha=1.0):
    """
    One simple PBR material. Imported assets get their originals replaced with these so the
    whole room shares a material language instead of each object bringing its own.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if 'Alpha' in bsdf.inputs:
        bsdf.inputs['Alpha'].default_value = alpha
    if emission is not None:
        if 'Emission Color' in bsdf.inputs:
            bsdf.inputs['Emission Color'].default_value = (*emission, 1.0)
        bsdf.inputs['Emission Strength'].default_value = emission_strength
    if alpha < 1.0:
        mat.blend_method = 'BLEND'
    return mat


def set_materials(obj, mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)


def assign_slot(obj, predicate, slot):
    """Assign a material slot to every face matching predicate(face_centre_world, normal)."""
    me = obj.data
    mw = obj.matrix_world
    for poly in me.polygons:
        centre = mw @ poly.center
        normal = (mw.to_3x3() @ poly.normal).normalized()
        if predicate(centre, normal):
            poly.material_index = slot
    me.update()


def hex_rgb(h):
    """sRGB hex to linear, since Blender's base colour input is linear."""
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


# --------------------------------------------------------------------------- export


def export(path, objs=None, draco=False):
    """
    Export to GLB.

    Draco is off by default. These props are a few thousand triangles each, so the file is
    already tiny, and enabling it would drag a WASM decoder into the runtime for no real
    saving. Turn it on per-asset if something large ever justifies it.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deselect()
    for o in (objs if objs is not None else meshes()):
        o.select_set(True)
    total = sum(tri_count(o) for o in (objs if objs is not None else meshes()))
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_draco_mesh_compression_enable=draco,
        export_draco_mesh_compression_level=6,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
        export_extras=False,
    )
    size = os.path.getsize(path)
    print(f'EXPORTED {os.path.basename(path)}  {total} tris  {size / 1024:.0f} KB')
    return total, size


def write_meta(glb_path, data):
    """
    Sidecar JSON beside the GLB, in glTF (Y-up) coordinates.

    Some things the runtime needs are not geometry — where a lamp's light sits, which way its
    beam points. glTF extras do not survive this export path, so they travel alongside instead
    of being re-derived (and re-guessed) at runtime.
    """
    import json
    out = os.path.splitext(glb_path)[0] + '.json'
    with open(out, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'META {os.path.basename(out)} {data}')


def to_gltf(v):
    """Blender Z-up vector to glTF Y-up."""
    return [round(v.x, 5), round(v.z, 5), round(-v.y, 5)]


def argv():
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
