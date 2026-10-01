"""
Small framed painting on the right wall (room space, Z-up metres). Re-running replaces NEW_painting.
Canvas: Monet, Water Lilies (1906) — public domain, AIC open-access CC0 image (see assets/MANIFEST.md).

Run inside Blender with room.blend open:  exec(open(r"<repo>/blender/scripts/v2_painting.py").read())
"""
import bpy, bmesh, math, os

REPO = r"C:\Users\Vas\Documents\Github\Hub"
IMG = os.path.join(REPO, 'assets', 'textures', 'painting_monet_water_lilies', 'water_lilies_1906.jpg')
WALL_X = 1.91            # inner face of the right wall
CY, CZ = 0.55, 1.58      # painting centre on the wall
CANVAS_H = 0.34          # canvas height; width follows the image aspect
FRAME_W, FRAME_D = 0.028, 0.034   # moulding face width and depth
GAP = 0.006              # float-frame shadow gap around the canvas

col = bpy.data.collections.get('NEW_painting')
if col:
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)
else:
    col = bpy.data.collections.new('NEW_painting')
    bpy.context.scene.collection.children.link(col)

img = bpy.data.images.load(IMG, check_existing=True)
aspect = img.size[0] / img.size[1]
CANVAS_W = CANVAS_H * aspect


def box(name, sx, sy, sz, loc, mat, bevel=0.0015):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    o.location = loc
    me.materials.append(mat)
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = 3; b.limit_method = 'ANGLE'
    for p in me.polygons:
        p.use_smooth = True
    return o


# ---- materials
def canvas_mat():
    m = bpy.data.materials.get('painting_canvas') or bpy.data.materials.new('painting_canvas')
    m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    p = nt.nodes.new('ShaderNodeBsdfPrincipled')
    p.inputs['Roughness'].default_value = 0.62
    p.inputs['Coat Weight'].default_value = 0.15          # thin varnish
    p.inputs['Coat Roughness'].default_value = 0.35
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
    # impasto: image luminance + fine canvas weave into bump
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    wv = nt.nodes.new('ShaderNodeTexWave'); wv.inputs['Scale'].default_value = 900; wv.bands_direction = 'X'
    wv2 = nt.nodes.new('ShaderNodeTexWave'); wv2.inputs['Scale'].default_value = 900; wv2.bands_direction = 'Y'
    mx = nt.nodes.new('ShaderNodeMath'); mx.operation = 'MULTIPLY_ADD'
    mx.inputs[1].default_value = 0.6
    add = nt.nodes.new('ShaderNodeMath'); add.operation = 'ADD'
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.0006
    nt.links.new(tex.outputs['Color'], p.inputs['Base Color'])
    nt.links.new(tex.outputs['Color'], bw.inputs[0])
    nt.links.new(bw.outputs[0], mx.inputs[0])
    nt.links.new(wv.outputs['Fac'], add.inputs[0]); nt.links.new(wv2.outputs['Fac'], add.inputs[1])
    nt.links.new(add.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    nt.links.new(p.outputs[0], out.inputs['Surface'])
    return m


def frame_mat():
    m = bpy.data.materials.get('painting_frame_oak_black') or bpy.data.materials.new('painting_frame_oak_black')
    m.use_nodes = True; nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value = (0.025, 0.022, 0.02, 1)   # black-stained oak
    p.inputs['Roughness'].default_value = 0.5
    wv = nt.nodes.new('ShaderNodeTexWave'); wv.wave_type = 'RINGS'; wv.inputs['Scale'].default_value = 40
    wv.inputs['Distortion'].default_value = 12
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.15
    bump.inputs['Distance'].default_value = 0.0004
    nt.links.new(wv.outputs['Fac'], bump.inputs['Height']); nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def linen_edge_mat():
    m = bpy.data.materials.get('painting_canvas_edge') or bpy.data.materials.new('painting_canvas_edge')
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value = (0.55, 0.5, 0.42, 1); p.inputs['Roughness'].default_value = 0.9
    return m


CAN, FRM, EDGE = canvas_mat(), frame_mat(), linen_edge_mat()

# Local frame: the painting faces -X (into the room). Build axes: depth along X, width along Y, height along Z.
depth_canvas = 0.02
cx = WALL_X - FRAME_D + depth_canvas / 2 + 0.004       # canvas stretcher sits inside the frame, slightly proud of the wall

# stretcher (canvas wrap) — linen sides
box('painting_stretcher', depth_canvas, CANVAS_W, CANVAS_H, (cx, CY, CZ), EDGE, bevel=0.001)

# painted face: a UV-mapped plane on the room side of the stretcher
me = bpy.data.meshes.new('painting_canvas')
bm = bmesh.new()
x = cx - depth_canvas / 2 - 0.0003
vs = [bm.verts.new((x, CY + CANVAS_W / 2, CZ - CANVAS_H / 2)), bm.verts.new((x, CY - CANVAS_W / 2, CZ - CANVAS_H / 2)),
      bm.verts.new((x, CY - CANVAS_W / 2, CZ + CANVAS_H / 2)), bm.verts.new((x, CY + CANVAS_W / 2, CZ + CANVAS_H / 2))]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new('UVMap')
for loop, co in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
    loop[uv].uv = co
bm.to_mesh(me); bm.free()
me.materials.append(CAN)
face = bpy.data.objects.new('painting_canvas', me); col.objects.link(face)

# float frame: four mitred-looking bars around the canvas with a shadow gap
ow, oh = CANVAS_W + 2 * (GAP + FRAME_W), CANVAS_H + 2 * (GAP + FRAME_W)
fx = WALL_X - FRAME_D / 2
box('painting_frame_top', FRAME_D, ow, FRAME_W, (fx, CY, CZ + oh / 2 - FRAME_W / 2), FRM)
box('painting_frame_bottom', FRAME_D, ow, FRAME_W, (fx, CY, CZ - oh / 2 + FRAME_W / 2), FRM)
box('painting_frame_left', FRAME_D, FRAME_W, oh - 2 * FRAME_W, (fx, CY + ow / 2 - FRAME_W / 2, CZ), FRM)
box('painting_frame_right', FRAME_D, FRAME_W, oh - 2 * FRAME_W, (fx, CY - ow / 2 + FRAME_W / 2, CZ), FRM)
# backer tray visible in the shadow gap
box('painting_frame_tray', 0.004, ow - 2 * FRAME_W + 0.002, oh - 2 * FRAME_W + 0.002, (WALL_X - 0.003, CY, CZ), FRM, bevel=0)

print(f'painting {CANVAS_W:.3f} x {CANVAS_H:.3f} m canvas, {ow:.3f} x {oh:.3f} m framed, {len(col.objects)} objects')
