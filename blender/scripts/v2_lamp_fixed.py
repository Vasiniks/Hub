"""
v2_lamp_fixed.py -- clean minimalist white desk lamp (replaces the warped STL lamp).

    blender -b --factory-startup --python blender/scripts/v2_lamp_fixed.py -- [--no-render]

Owner review of the STL lamp: the support was bent/warped and the head warped. This rebuild keeps the
round weighted base on the same footprint and replaces everything above it with true, straight parts:
  * lamp_base        round weighted base (same centre, radius and height as before), rounded edges
  * lamp_column      perfectly vertical round column with a moulded boot where it meets the base
  * lamp_knuckle     horizontal pivot barrel on top of the column (the clean pivot)
  * lamp_neck        short straight horizontal bar from the knuckle to the head's edge
                     (the medals hang on this piece)
  * lamp_head        flat circular disc head, planar top and bottom, soft edge radius, level
  * lamp_diffuser_disc / lamp_diffuser_bezel / LAMP_disk (DISK area light), centred flush underneath
All plastic uses lamp_white_plastic (base colour 0.83, roughness 0.33 + micro variation, fine bump).
Nothing is read from room.blend except the old base centre (hard-coded below from the measured file).
Writes blender/scene/parts/lamp.blend (collection NEW_lamp, root NEW_lamp_root, ROOM coordinates) and
parts/lamp_meta.json (neck span / head frame, used by v2_medals.py to hang the medals).
"""
import bpy
import bmesh
import json
import math
import os
import sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
OUT_BLEND = os.path.join(PARTS, 'lamp.blend')
OUT_META = os.path.join(PARTS, 'lamp_meta.json')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
SEAT = Vector((0.0, -0.16, 1.175))
Z = Vector((0, 0, 1))

# ---- the old base, measured from room.blend (lamp003_1): centre, top radius, bottom and top z
BASE_C = Vector((-0.7138, 1.0381))
BASE_R = 0.087
BASE_Z0, BASE_Z1 = 0.735, 0.7669

# ---- proportions (metres)
COL_R = 0.013             # Ø26 column
KNUCKLE_R = 0.015         # Ø30 pivot barrel
KNUCKLE_L = 0.036
NECK_W, NECK_H = 0.022, 0.012   # neck bar cross-section (across x up)
NECK_SPAN = 0.145         # visible neck length, knuckle surface -> head rim
HEAD_R = 0.080            # Ø160 head
HEAD_T = 0.014            # 14 mm thick
HEAD_EDGE = 0.005         # soft edge radius
HEAD_BOTTOM = 1.180       # underside height (the old head's underside was ~1.18-1.19)
COL_BACK = 0.030          # column sits this far behind the base centre (opposite the head)
# neck direction: 53 deg off the seat line, toward the desk (+x) -> medals spread out as seen from the seat
_u = (SEAT.to_2d() - BASE_C).normalized()
_up = Vector((-_u.y, _u.x)) if Vector((-_u.y, _u.x)).x > 0 else Vector((_u.y, -_u.x))
NECK_DIR = (0.6 * _u + 0.8 * _up).normalized()

# ---- circular light (v2_lamp.py values: warm colour, 7 W, 75 deg spread; diffuser scaled to the new head)
DIFF_R = 0.062
WARM = (1.0, 0.86, 0.68)
DISK_ENERGY = 7.0
DISK_SPREAD = math.radians(75)


# ------------------------------------------------------------------------------ geometry helpers
def frame(origin, zaxis, xhint=None):
    zaxis = zaxis.normalized()
    x = (xhint - zaxis * xhint.dot(zaxis)).normalized() if xhint is not None else zaxis.orthogonal().normalized()
    y = zaxis.cross(x)
    return Matrix(((x.x, y.x, zaxis.x, origin.x), (x.y, y.y, zaxis.y, origin.y),
                   (x.z, y.z, zaxis.z, origin.z), (0, 0, 0, 1)))


def lathe(prof, fr, seg=64):
    """prof: [(r, h)] along local +Z, first/last may have r=0 (poles). Returns bmesh in world."""
    bm = bmesh.new()
    rings = []
    for r, h in prof:
        if r < 1e-9:
            rings.append([bm.verts.new(fr @ Vector((0, 0, h)))])
        else:
            rings.append([bm.verts.new(fr @ Vector((r * math.cos(2 * math.pi * j / seg),
                                                     r * math.sin(2 * math.pi * j / seg), h))) for j in range(seg)])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(seg):
            j2 = (j + 1) % seg
            if len(A) == 1:
                bm.faces.new([A[0], B[j], B[j2]])
            elif len(B) == 1:
                bm.faces.new([A[j], A[j2], B[0]])
            else:
                bm.faces.new([A[j], A[j2], B[j2], B[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def arc(cx, cy, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def rounded_rect(w, h, r, n=5):
    """Closed outline (CCW) of a w x h rectangle with corner radius r, centred at the origin."""
    pts = []
    for (cx, cy, a0) in ((w / 2 - r, -h / 2 + r, -math.pi / 2), (w / 2 - r, h / 2 - r, 0.0),
                         (-w / 2 + r, h / 2 - r, math.pi / 2), (-w / 2 + r, -h / 2 + r, math.pi)):
        pts += arc(cx, cy, r, a0, a0 + math.pi / 2, n)
    return pts


def sweep_bar(outline, p0, p1, up, end_round=0.0):
    """Straight prism of a 2D outline (x across, y up) from p0 to p1; optional rounded far end."""
    axis = (p1 - p0).normalized()
    across = up.cross(axis).normalized()
    upv = axis.cross(across).normalized()
    bm = bmesh.new()

    def ring(p, scale=1.0):
        return [bm.verts.new(p + across * (x * scale) + upv * (y * scale)) for x, y in outline]
    rings = [ring(p0), ring(p1)]
    n = len(outline)
    for r in range(len(rings) - 1):
        for k in range(n):
            bm.faces.new([rings[r][k], rings[r][(k + 1) % n], rings[r + 1][(k + 1) % n], rings[r + 1][k]])
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


# ------------------------------------------------------------------------------ materials
def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def white_plastic():
    m = bpy.data.materials.new('lamp_white_plastic')
    m.use_nodes = True
    nt = m.node_tree
    p = principled(m)
    p.inputs['Base Color'].default_value = (0.83, 0.83, 0.82, 1)
    p.inputs['Roughness'].default_value = 0.33
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 1400
    nz.inputs['Detail'].default_value = 4
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.03
    bump.inputs['Distance'].default_value = 0.0002
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    nz2 = nt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 220
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.30
    mr.inputs['To Max'].default_value = 0.36
    nt.links.new(nz2.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], p.inputs['Roughness'])
    return m


def diffuser_mat():
    m = bpy.data.materials.new('lamp_diffuser')
    m.use_nodes = True
    p = principled(m)
    p.inputs['Base Color'].default_value = (0.95, 0.95, 0.93, 1)
    p.inputs['Roughness'].default_value = 0.5
    p.inputs['Emission Color'].default_value = (*WARM, 1)
    p.inputs['Emission Strength'].default_value = 6.0
    return m


# ------------------------------------------------------------------------------ build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    coll = bpy.data.collections.new('NEW_lamp')
    scene.collection.children.link(coll)
    WP = white_plastic()
    DM = diffuser_mat()
    d2 = NECK_DIR
    d3 = d2.to_3d()
    b3 = Z.cross(d3).normalized()           # horizontal, across the neck

    head_mid = HEAD_BOTTOM + HEAD_T / 2
    col_xy = BASE_C - d2 * COL_BACK
    K = Vector((col_xy.x, col_xy.y, head_mid))                       # knuckle centre = neck axis height
    neck0 = K + d3 * KNUCKLE_R                                         # visible neck start
    neck1 = neck0 + d3 * NECK_SPAN                                     # head rim
    H = neck1 + d3 * HEAD_R                                            # head centre (at mid thickness)
    head_c = Vector((H.x, H.y, HEAD_BOTTOM))

    parts = {}
    # ---- base: round weighted base, same footprint; foot ring, rounded top edge, shallow top groove
    R = BASE_R
    z0, z1 = BASE_Z0, BASE_Z1
    prof = [(0.0, z0), (R - 0.009, z0), (R - 0.0075, z0 + 0.0008), (R - 0.0070, z0 + 0.0040),
            (R - 0.0030, z0 + 0.0048), (R - 0.0006, z0 + 0.0062), (R, z0 + 0.0085),
            (R, z1 - 0.0045), (R - 0.0012, z1 - 0.0013), (R - 0.0040, z1),
            (0.056, z1), (0.0555, z1 - 0.0004), (0.0525, z1 - 0.0004), (0.052, z1), (0.0, z1)]
    parts['lamp_base'] = (lathe([(r, h - z0) for r, h in prof],
                                Matrix.Translation(Vector((BASE_C.x, BASE_C.y, z0))), seg=96), WP, 40)
    # ---- column: vertical cylinder from inside the base to the knuckle centre, moulded boot at the base
    cprof = [(0.0, -0.006), (COL_R + 0.0035, -0.006), (COL_R + 0.0035, 0.0012), (COL_R + 0.0029, 0.0026),
             (COL_R + 0.0014, 0.0036), (COL_R + 0.0002, 0.0042), (COL_R, 0.0050),
             (COL_R, K.z - z1), (0.0, K.z - z1)]
    parts['lamp_column'] = (lathe(cprof, Matrix.Translation(Vector((col_xy.x, col_xy.y, z1))), seg=48), WP, 40)
    # ---- knuckle: horizontal barrel across the neck, chamfered ends and a pin dimple each side
    L = KNUCKLE_L
    kr = KNUCKLE_R
    kprof = [(0.0, -L / 2), (0.0028, -L / 2), (0.0032, -L / 2 + 0.0004), (0.0036, -L / 2),
             (kr - 0.0014, -L / 2), (kr - 0.0003, -L / 2 + 0.0007), (kr, -L / 2 + 0.0018),
             (kr, -0.0006), (kr - 0.0004, -0.0003), (kr - 0.0004, 0.0003), (kr, 0.0006),
             (kr, L / 2 - 0.0018), (kr - 0.0003, L / 2 - 0.0007), (kr - 0.0014, L / 2),
             (0.0036, L / 2), (0.0032, L / 2 - 0.0004), (0.0028, L / 2), (0.0, L / 2)]
    parts['lamp_knuckle'] = (lathe(kprof, frame(K, b3), seg=48), WP, 40)
    # ---- neck: straight horizontal rounded-rectangle bar, from inside the knuckle into the head rim
    outline = rounded_rect(NECK_W, NECK_H, 0.004, n=5)
    parts['lamp_neck'] = (sweep_bar(outline, K, neck1 + d3 * 0.012, Z), WP, 40)
    # ---- head: flat circular disc with a soft edge radius; planar top and bottom
    e = HEAD_EDGE
    hprof = [(0.0, 0.0), (HEAD_R - e, 0.0)]
    hprof += [(HEAD_R - e + e * math.sin(a), e - e * math.cos(a)) for a in [math.pi / 2 * k / 6 for k in range(1, 7)]]
    hprof += [(HEAD_R, HEAD_T - e)]
    hprof += [(HEAD_R - e + e * math.cos(a), HEAD_T - e + e * math.sin(a)) for a in [math.pi / 2 * k / 6 for k in range(1, 6)]]
    hprof += [(HEAD_R - e, HEAD_T), (HEAD_R - 0.010, HEAD_T), (HEAD_R - 0.0104, HEAD_T - 0.0003),
              (HEAD_R - 0.0116, HEAD_T - 0.0003), (HEAD_R - 0.012, HEAD_T), (0.0, HEAD_T)]
    parts['lamp_head'] = (lathe(hprof, Matrix.Translation(head_c), seg=128), WP, 35)
    # ---- circular light, centred flush under the head
    fr_d = frame(head_c, -Z, xhint=d3)        # local +Z points down
    bez = [(DIFF_R - 0.0012, 0.0024), (DIFF_R + 0.0005, 0.0031), (DIFF_R + 0.0030, 0.0035),
           (DIFF_R + 0.0046, 0.0026), (DIFF_R + 0.0052, 0.0008), (DIFF_R + 0.0052, -0.0006),
           (DIFF_R - 0.0012, -0.0006), (DIFF_R - 0.0012, 0.0024)]
    parts['lamp_diffuser_bezel'] = (lathe(bez, fr_d, seg=96), WP, 50)
    disc = [(0.0, 0.0028), (DIFF_R * 0.5, 0.0027), (DIFF_R * 0.85, 0.0025), (DIFF_R - 0.0008, 0.0022),
            (DIFF_R - 0.0008, 0.0002), (0.0, 0.0002)]
    parts['lamp_diffuser_disc'] = (lathe(disc, fr_d, seg=96), DM, 50)

    # ---- objects under the root
    root = bpy.data.objects.new('NEW_lamp_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.05
    root.location = Vector((BASE_C.x, BASE_C.y, BASE_Z0))
    coll.objects.link(root)
    inv = Matrix.Translation(-root.location)
    tris = {}
    objs = {}
    for name, (bm, mat, ang) in parts.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
        bm.transform(inv)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(ang))
        o = bpy.data.objects.new(name, me)
        coll.objects.link(o)
        o.parent = root
        objs[name] = o
        tris[name] = sum(len(p.vertices) - 2 for p in me.polygons)
    ld = bpy.data.lights.new('LAMP_disk', 'AREA')
    ld.shape = 'DISK'
    ld.size = 2 * DIFF_R
    ld.energy = DISK_ENERGY
    ld.color = WARM
    ld.spread = DISK_SPREAD
    lo = bpy.data.objects.new('LAMP_disk', ld)
    coll.objects.link(lo)
    lo.parent = root
    lo.matrix_world = Matrix.Translation(head_c - Z * 0.0034)          # area lights emit along -Z: down
    bpy.context.view_layer.update()

    # ---- straightness / planarity checks
    def world_verts(o):
        return [o.matrix_world @ v.co for v in o.data.vertices]
    allc = world_verts(objs['lamp_column'])
    cxy0 = col_xy
    # the shaft: every vertex lying on the �26 cylinder (rings at the boot top and at the knuckle)
    cv = [v for v in allc if abs((v.to_2d() - cxy0).length - COL_R) < 2e-5 and v.z > z1 + 0.0045]
    cxy = sum((v.to_2d() for v in cv), Vector((0, 0))) / len(cv)
    col_dev = max(abs((v.to_2d() - cxy).length - COL_R) for v in cv)
    nv = world_verts(objs['lamp_neck'])
    neck_z_spread = max(v.z for v in nv) - min(v.z for v in nv) - NECK_H
    hv = world_verts(objs['lamp_head'])
    # planar faces only (exclude the edge fillet and the deliberate 0.3 mm top groove ring)
    rr = lambda v: (v.to_2d() - head_c.to_2d()).length
    top = [v.z for v in hv if v.z > head_c.z + HEAD_T / 2 and rr(v) < HEAD_R - 0.013]
    bot = [v.z for v in hv if v.z < head_c.z + HEAD_T / 2 and rr(v) < HEAD_R - HEAD_EDGE + 1e-6]
    rad = [(v.to_2d() - head_c.to_2d()).length for v in hv if abs(v.z - (head_c.z + HEAD_T - e)) < 1e-6]
    checks = dict(column_radius_dev_mm=round(col_dev * 1000, 4),
                  column_axis_vs_vertical_deg=0.0,
                  neck_z_extra_mm=round(neck_z_spread * 1000, 4),
                  neck_dir=(round(d3.x, 4), round(d3.y, 4), round(d3.z, 4)),
                  head_top_flatness_mm=round((max(top) - min(top)) * 1000, 4),
                  head_bottom_flatness_mm=round((max(bot) - min(bot)) * 1000, 4),
                  head_roundness_mm=round((max(rad) - min(rad)) * 1000, 4) if rad else None)
    # column axis tilt: centre of the lowest vs highest vertex ring
    zs = sorted({round(v.z, 6) for v in cv})
    c_lo = sum((v.to_2d() for v in cv if round(v.z, 6) == zs[0]), Vector((0, 0))) / len([v for v in cv if round(v.z, 6) == zs[0]])
    c_hi = sum((v.to_2d() for v in cv if round(v.z, 6) == zs[-1]), Vector((0, 0))) / len([v for v in cv if round(v.z, 6) == zs[-1]])
    checks['column_axis_vs_vertical_deg'] = round(math.degrees(math.atan2((c_hi - c_lo).length, zs[-1] - zs[0])), 5)
    print('CHECKS', checks)

    meta = dict(neck_start=list(neck0), neck_end=list(neck1), neck_dir=list(d3), neck_across=list(b3),
                neck_w=NECK_W, neck_h=NECK_H, knuckle=list(K), head_centre=list(head_c), head_r=HEAD_R,
                head_t=HEAD_T, column_xy=list(col_xy), column_r=COL_R, diffuser_r=DIFF_R)
    with open(OUT_META, 'w') as f:
        json.dump(meta, f, indent=1)
    total = sum(tris.values())
    print(f'LAYOUT column {tuple(round(x, 4) for x in col_xy)} knuckle {tuple(round(x, 4) for x in K)} '
          f'neck {tuple(round(x, 4) for x in neck0)} -> {tuple(round(x, 4) for x in neck1)} head {tuple(round(x, 4) for x in head_c)}')
    print('TRIS', total, tris)
    return dict(scene=scene, coll=coll, K=K, head_c=head_c, d3=d3, b3=b3, tris=tris, total=total, checks=checks)


# ------------------------------------------------------------------------------ previews
def previews(b):
    scene = b['scene']
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'CUDA'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPTIX'
    except TypeError:
        pass
    scene.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new('grey')
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.42, 0.42, 0.42, 1)
    bg.inputs['Strength'].default_value = 0.6
    scene.world = w
    tmp = []
    c = BASE_C
    desk = bpy.data.meshes.new('prev_desk')
    desk.from_pydata([(c.x - 0.9, c.y - 0.9, 0.735), (c.x + 0.9, c.y - 0.9, 0.735), (c.x + 0.9, c.y + 0.9, 0.735),
                      (c.x - 0.9, c.y + 0.9, 0.735)], [], [(0, 1, 2, 3)])
    dm = bpy.data.materials.new('prev_desk')
    dm.use_nodes = True
    principled(dm).inputs['Base Color'].default_value = (0.55, 0.42, 0.33, 1)
    desk.materials.append(dm)
    do = bpy.data.objects.new('prev_desk', desk)
    scene.collection.objects.link(do)
    tmp.append(do)
    mid = (Vector((c.x, c.y, 0.735)) + b['head_c']) / 2

    def light(name, off, power, size):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        o = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(o)
        o.location = mid + Vector(off)
        o.rotation_euler = (mid - o.location).to_track_quat('-Z', 'Y').to_euler()
        tmp.append(o)
    light('key', (0.8, -0.9, 0.7), 90, 0.6)
    light('fill', (-0.9, -0.5, 0.2), 30, 0.9)
    light('rim', (-0.3, 0.9, 0.6), 70, 0.5)
    cam = bpy.data.objects.new('prev_cam', bpy.data.cameras.new('prev_cam'))
    scene.collection.objects.link(cam)
    scene.camera = cam
    tmp.append(cam)

    def shot(loc, target, lens, name, res=(1280, 800), ortho=None):
        scene.render.resolution_x, scene.render.resolution_y = res
        cam.data.type = 'ORTHO' if ortho else 'PERSP'
        if ortho:
            cam.data.ortho_scale = ortho
        cam.location = loc
        cam.data.lens = lens
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(PARTS, name)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', name)
    three_q = (b['d3'] * 0.3 - b['b3'] * 0.9).normalized()
    shot(mid + three_q * 0.95 + Vector((0, 0, 0.25)), mid, 40, 'lamp_34.png', (900, 1100))
    side = -b['b3'] if (-b['b3']).dot((SEAT - mid).normalized()) > 0 else b['b3']
    shot(mid + side * 1.2, mid, 50, 'lamp_side.png', (1100, 900), ortho=0.62)
    shot(SEAT, mid + Vector((0, 0, 0.06)), 40, 'lamp_seat.png')
    shot(b['head_c'] + Vector((0.0, 0.0, -0.30)) + b['d3'] * 0.12 - b['b3'] * 0.1, b['head_c'], 45, 'lamp_underside.png', (1000, 800))
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.materials.remove(dm)


def finish(b):
    for o in list(bpy.context.scene.objects):
        if o.name not in b['coll'].all_objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    os.makedirs(PARTS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    print('SAVED', OUT_BLEND)


if __name__ == '__main__':
    b = build()
    if not NO_RENDER:
        previews(b)
    finish(b)
    print('DONE')
