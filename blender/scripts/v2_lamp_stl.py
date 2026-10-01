"""
v2_lamp_stl.py -- the desk lamp rebuilt from the owner's STL (C:\\Users\\Vas\\Desktop\\lamp.stl).

    blender -b --factory-startup --python blender/scripts/v2_lamp_stl.py -- [--no-render]

The STL is one clean, manifold, boolean-unioned mesh in CENTIMETRES (33.9 x 20.9 x 45.0: base Ø20, 45 cm
tall, Z up, the arm reaching toward +X). This script:
  * imports it, scales 0.01 (cm -> m), merges near-doubles, recalculates normals, smooth-by-angle;
  * cuts it once, just above the column sleeve's rim, into the static part (base + column sleeve) and the
    arm (twin rods, ball knuckle, neck, head) -- the rods leave the sleeve there, so that is the joint;
  * replaces the owner's slightly elliptical head (17.6 x 20.9 cm) with a true circular disc Ø21.5 cm in the
    same tilted plane, enclosing the STL head; round diffuser + bezel flush underneath + DISK area light,
    energy scaled with diffuser area from v2_lamp.py's 7 W at r 34 mm... (see DISK_* below);
  * places it at the current lamp spot (NEW_lamp_root, measured in room.blend) with the arm reaching toward
    the front-centre of the desk, and tilts the arm ~5 deg further toward it with NEW_lamp_pivot
    (an empty on the joint; its axis-angle rotates the whole arm about the joint axis).
All plastic: lamp_white_plastic. Output: parts/lamp.blend (NEW_lamp / NEW_lamp_root, ROOM coords) and
parts/lamp_meta.json (pivot, neck cylinder, head frame -- used by v2_medals.py).
"""
import bpy
import bmesh
import json
import math
import os
import sys
from mathutils import Vector, Matrix, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
PARTS = os.path.join(REPO, 'blender', 'scene', 'parts')
STL = r'C:\Users\Vas\Desktop\lamp.stl'
OUT_BLEND = os.path.join(PARTS, 'lamp.blend')
OUT_META = os.path.join(PARTS, 'lamp_meta.json')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NO_RENDER = '--no-render' in ARGS
SEAT = Vector((0.0, -0.16, 1.175))
Z = Vector((0, 0, 1))

ROOT = Vector((-0.6638, 0.9181, 0.735))        # NEW_lamp_root in room.blend after the orchestrator's move
AIM = Vector((-0.15, 0.45))                     # front-centre working area of the desk (toward x ~ 0)
TILT_DEG = 5.0                                  # arm/head tilt toward the desk centre
CM = 0.01
CUT_Z_CM = 15.03                                # just above the sleeve rim (15.00 cm)
HEAD_R = 0.1075                                 # Ø21.5 cm circular head
HEAD_EXTRA_T = 0.002                            # new disc is this much thicker than the STL head
DIFF_R = HEAD_R - 0.012
WARM = (1.0, 0.86, 0.68)
DISK_ENERGY = 7.0 * (DIFF_R / 0.034) ** 2 / 4.0   # v2_lamp: 7 W on r 34 mm; scaled by area, then /4 so the
                                                # much larger panel keeps a similar desk illuminance
DISK_SPREAD = math.radians(75)


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


def frame(origin, zaxis, xhint):
    zaxis = zaxis.normalized()
    x = (xhint - zaxis * xhint.dot(zaxis)).normalized()
    y = zaxis.cross(x)
    return Matrix(((x.x, y.x, zaxis.x, origin.x), (x.y, y.y, zaxis.y, origin.y),
                   (x.z, y.z, zaxis.z, origin.z), (0, 0, 0, 1)))


def lathe(prof, fr, seg=96):
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


def pca(pts):
    import numpy as np
    A = np.array([[p.x, p.y, p.z] for p in pts])
    m = A.mean(0)
    _, s, vt = np.linalg.svd(A - m)
    return Vector(m), [Vector(v) for v in vt], s


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    WP = white_plastic()
    DM = diffuser_mat()
    coll = bpy.data.collections.new('NEW_lamp')
    scene.collection.children.link(coll)

    # ---- import + clean (in STL centimetres first, for measuring)
    bpy.ops.wm.stl_import(filepath=STL)
    src = [o for o in bpy.data.objects if o.type == 'MESH'][0]
    bm = bmesh.new()
    bm.from_mesh(src.data)
    bpy.data.objects.remove(src, do_unlink=True)
    n_before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)          # 0.01 mm
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    V = [v.co.copy() for v in bm.verts]
    lo = Vector([min(v[i] for v in V) for i in range(3)])
    hi = Vector([max(v[i] for v in V) for i in range(3)])
    print(f'STL {n_before} -> {len(bm.verts)} verts, {len(bm.faces)} tris, non-manifold edges {nonman}, '
          f'size cm {tuple(round(x, 2) for x in hi - lo)}')
    base = [v for v in V if v.z < 2.6]
    base_c = Vector(((min(v.x for v in base) + max(v.x for v in base)) / 2,
                     (min(v.y for v in base) + max(v.y for v in base)) / 2, 0))
    base_d = max(max(v.x for v in base) - min(v.x for v in base), max(v.y for v in base) - min(v.y for v in base))
    sleeve = [v for v in V if 3 < v.z < 15.01]
    rim_c = Vector(((min(v.x for v in sleeve) + max(v.x for v in sleeve)) / 2,
                    (min(v.y for v in sleeve) + max(v.y for v in sleeve)) / 2, 15.0))
    # STL head (x > 11 cm is head only): plane, in-plane centre, thickness
    hv = [v for v in V if v.x > 11]
    hc, axes, _ = pca(hv)
    n_h = axes[2] if axes[2].z > 0 else -axes[2]
    u_h = (Vector((1, 0, 0)) - n_h * n_h.x).normalized()
    w_h = n_h.cross(u_h)
    allh = [v for v in V if v.x > 6.9 and (v - hc).dot(n_h) > -3]
    # in-plane extents from all head verts (rear edge is at x ~ 7)
    us = [(v - hc).dot(u_h) for v in allh]
    ws = [(v - hc).dot(w_h) for v in hv]
    hs = [(v - hc).dot(n_h) for v in hv]
    head_c = hc + u_h * ((max(us) + min(us)) / 2) + w_h * ((max(ws) + min(ws)) / 2) + n_h * ((max(hs) + min(hs)) / 2)
    head_t = (max(hs) - min(hs))
    head_len, head_wid = max(us) - min(us), max(ws) - min(ws)
    tilt_head = math.degrees(n_h.angle(Z))
    # neck: the bulb between the ball knuckle (x < 0.5 cm) and the head bracket (x > 3.5 cm), measured by
    # x-slices of the STL: axis along +X at (y -5.35, z 40.8) cm, x 1.05..3.30, section ~4.2 x 3.2 cm
    NECK_X0, NECK_X1, NECK_Y, NECK_Z, NECK_AT, NECK_AZ = 1.05, 3.30, -5.35, 40.80, 2.10, 1.60
    nk = [v for v in V if NECK_X0 <= v.x <= NECK_X1 and v.z > 38.5 and abs(v.y - NECK_Y) < 3]
    nc = Vector((0.0, NECK_Y, NECK_Z))
    n_ax = Vector((1, 0, 0))
    projs = [NECK_X0, NECK_X1]
    n_r = NECK_AT
    print(f'STL base centre {tuple(round(x, 2) for x in base_c)} cm Ø{base_d:.2f}; sleeve rim centre '
          f'{tuple(round(x, 2) for x in rim_c)}; head {head_len:.2f} x {head_wid:.2f} cm, t {head_t:.2f}, '
          f'tilt {tilt_head:.1f} deg; neck r {n_r:.2f} cm len {max(projs) - min(projs):.2f} cm')

    # ---- STL cm -> room: scale, yaw so +X points at the desk aim, base centre on NEW_lamp_root
    R2 = (AIM - ROOT.to_2d()).normalized()
    yaw = math.atan2(R2.y, R2.x)
    to_room = Matrix.Translation(ROOT) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Scale(CM, 4) @ \
        Matrix.Translation(-base_c)
    rot3 = Matrix.Rotation(yaw, 3, 'Z')

    # ---- cut at the joint: static (base + sleeve) and arm (rods, knuckle, neck, head)
    def half(keep_below):
        b = bm.copy()
        geom = b.verts[:] + b.edges[:] + b.faces[:]
        r = bmesh.ops.bisect_plane(b, geom=geom, plane_co=(0, 0, CUT_Z_CM), plane_no=(0, 0, 1),
                                   clear_outer=keep_below, clear_inner=not keep_below)
        edges = [e for e in b.edges if e.is_boundary]
        if edges:
            bmesh.ops.holes_fill(b, edges=edges, sides=0)
            bmesh.ops.triangulate(b, faces=[f for f in b.faces if len(f.verts) > 4])
        bmesh.ops.recalc_face_normals(b, faces=b.faces)
        b.transform(to_room)
        return b
    bm_static = half(True)
    bm_arm = half(False)

    # ---- circular head disc (encloses the STL head), diffuser + bezel flush underneath
    hc_w = to_room @ head_c
    n_w = (rot3 @ n_h).normalized()
    u_w = (rot3 @ u_h).normalized()
    T_new = head_t * CM + HEAD_EXTRA_T
    e = 0.005
    fr = frame(hc_w - n_w * (T_new / 2), n_w, u_w)
    prof = [(0.0, 0.0), (HEAD_R - e, 0.0)]
    prof += [(HEAD_R - e + e * math.sin(a), e - e * math.cos(a)) for a in [math.pi / 2 * k / 6 for k in range(1, 7)]]
    prof += [(HEAD_R, T_new - e)]
    prof += [(HEAD_R - e + e * math.cos(a), T_new - e + e * math.sin(a)) for a in [math.pi / 2 * k / 6 for k in range(1, 6)]]
    prof += [(HEAD_R - e, T_new), (0.0, T_new)]
    bm_head = lathe(prof, fr, 128)
    fr_d = frame(hc_w - n_w * (T_new / 2), -n_w, u_w)       # local +Z points away from the head (down)
    bez = [(DIFF_R - 0.0012, 0.0024), (DIFF_R + 0.0005, 0.0031), (DIFF_R + 0.0030, 0.0035),
           (DIFF_R + 0.0046, 0.0026), (DIFF_R + 0.0052, 0.0008), (DIFF_R + 0.0052, -0.0006),
           (DIFF_R - 0.0012, -0.0006), (DIFF_R - 0.0012, 0.0024)]
    bm_bez = lathe(bez, fr_d, 128)
    disc = [(0.0, 0.0028), (DIFF_R * 0.5, 0.0027), (DIFF_R * 0.85, 0.0025), (DIFF_R - 0.0008, 0.0022),
            (DIFF_R - 0.0008, 0.0002), (0.0, 0.0002)]
    bm_disc = lathe(disc, fr_d, 128)

    # ---- objects: root, static parts, pivot with the arm
    root = bpy.data.objects.new('NEW_lamp_root', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.05
    root.location = ROOT
    coll.objects.link(root)
    bpy.context.view_layer.update()
    pivot_w = to_room @ rim_c
    T_axis = Z.cross(R2.to_3d()).normalized()                 # joint axis: horizontal, across the reach
    pivot = bpy.data.objects.new('NEW_lamp_pivot', None)
    pivot.empty_display_type = 'ARROWS'
    pivot.empty_display_size = 0.04
    coll.objects.link(pivot)
    pivot.parent = root
    pivot.location = pivot_w - ROOT
    pivot.rotation_mode = 'AXIS_ANGLE'
    pivot.rotation_axis_angle = (0.0, T_axis.x, T_axis.y, T_axis.z)
    bpy.context.view_layer.update()
    tris = {}
    objs = {}

    def emit(name, b, mat, parent, smooth=30):
        me = bpy.data.meshes.new(name)
        b.transform(parent.matrix_world.inverted())
        b.to_mesh(me)
        b.free()
        me.materials.append(mat)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(smooth))
        o = bpy.data.objects.new(name, me)
        coll.objects.link(o)
        o.parent = parent
        objs[name] = o
        tris[name] = sum(len(p.vertices) - 2 for p in me.polygons)
        return o
    emit('lamp_body', bm_static, WP, root)
    emit('lamp_arm', bm_arm, WP, pivot)
    emit('lamp_head', bm_head, WP, pivot, 35)
    emit('lamp_diffuser_bezel', bm_bez, WP, pivot, 50)
    emit('lamp_diffuser_disc', bm_disc, DM, pivot, 50)
    ld = bpy.data.lights.new('LAMP_disk', 'AREA')
    ld.shape = 'DISK'
    ld.size = 2 * DIFF_R
    ld.energy = DISK_ENERGY
    ld.color = WARM
    ld.spread = DISK_SPREAD
    lo_ = bpy.data.objects.new('LAMP_disk', ld)
    coll.objects.link(lo_)
    lo_.parent = pivot
    lo_.matrix_parent_inverse = pivot.matrix_world.inverted()
    lo_.matrix_world = Matrix.Translation(hc_w - n_w * (T_new / 2 + 0.0034)) @ \
        (-n_w).to_track_quat('-Z', 'Y').to_matrix().to_4x4()
    bpy.context.view_layer.update()

    # ---- tilt the arm ~5 deg toward the desk centre
    pivot.rotation_axis_angle = (math.radians(TILT_DEG), T_axis.x, T_axis.y, T_axis.z)
    bpy.context.view_layer.update()

    # ---- checks (world space, tilted state)
    def wv(o):
        return [o.matrix_world @ v.co for v in o.data.vertices]
    bvs = [v for v in wv(objs['lamp_body']) if v.z < ROOT.z + 0.026]
    base_diam = max(max(v.x for v in bvs) - min(v.x for v in bvs), max(v.y for v in bvs) - min(v.y for v in bvs))
    h = wv(objs['lamp_head'])
    Mh = objs['lamp_head'].matrix_world
    hc_now = Mh @ (objs['lamp_head'].matrix_world.inverted() @ (pivot.matrix_world @ (pivot.matrix_world.inverted() @ Vector())))
    n_now = (pivot.matrix_world.to_3x3() @ (pivot.matrix_world.to_3x3().inverted() @ n_w)).normalized()
    # head diameter measured in its own plane, along two orthogonal in-plane axes
    cen = sum(h, Vector()) / len(h)
    nn = (pivot.matrix_world.to_3x3() @ Matrix.Rotation(0, 3, 'Z') @ n_w)
    Rt = Quaternion(T_axis, math.radians(TILT_DEG)).to_matrix()
    nn = (Rt @ n_w).normalized()
    ax1 = (Rt @ u_w).normalized()
    ax2 = nn.cross(ax1)
    d1 = max((v - cen).dot(ax1) for v in h) - min((v - cen).dot(ax1) for v in h)
    d2 = max((v - cen).dot(ax2) for v in h) - min((v - cen).dot(ax2) for v in h)
    top_z = max(v.z for o in objs.values() for v in wv(o))
    checks = dict(stl_units='cm', scale=CM, base_diam_mm=round(base_diam * 1000, 1),
                  head_diam_mm=(round(d1 * 1000, 2), round(d2 * 1000, 2)), head_thickness_mm=round(T_new * 1000, 1),
                  head_tilt_from_level_deg=round(math.degrees(nn.angle(Z)), 1), arm_tilt_deg=TILT_DEG,
                  reach_dir=(round(R2.x, 3), round(R2.y, 3)), lamp_height_mm=round((top_z - ROOT.z) * 1000, 1),
                  diffuser_r_mm=round(DIFF_R * 1000, 1), disk_energy_w=round(DISK_ENERGY, 2),
                  scales=sorted({tuple(round(x, 6) for x in o.matrix_world.to_scale()) for o in coll.objects}))
    print('CHECKS', checks)
    # neck cylinder in the room (tilted), for the medals
    Mp = pivot.matrix_world @ Matrix.Translation(Vector()) @ \
        (pivot.matrix_world.inverted() @ Matrix.Identity(4))

    def arm_pt(p_cm):
        """STL point (cm) -> room, including the arm tilt."""
        p_rest = to_room @ p_cm
        return pivot_w + Rt @ (p_rest - pivot_w)
    n0 = arm_pt(nc + n_ax * min(projs))
    n1 = arm_pt(nc + n_ax * max(projs))
    up_w = (Rt @ Z).normalized()
    meta = dict(root=list(ROOT), pivot=list(pivot_w), pivot_axis=list(T_axis), tilt_deg=TILT_DEG,
                neck_start=list(n0), neck_end=list(n1), neck_r=n_r * CM, neck_at=NECK_AT * CM, neck_az=NECK_AZ * CM,
                neck_up=list(up_w),
                head_centre=list(pivot_w + Rt @ (hc_w - pivot_w)), head_normal=list(nn), head_r=HEAD_R,
                head_t=T_new, reach_dir=[R2.x, R2.y, 0.0])
    with open(OUT_META, 'w') as f:
        json.dump(meta, f, indent=1)
    print('NECK room', tuple(round(x, 4) for x in n0), '->', tuple(round(x, 4) for x in n1), 'r', round(n_r * CM * 1000, 1), 'mm')
    total = sum(tris.values())
    print('TRIS', total, tris)
    return dict(scene=scene, coll=coll, pivot=pivot, T_axis=T_axis, R2=R2, head_c=Vector(meta['head_centre']),
                neck=(n0, n1), tris=tris, total=total)


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
    c = ROOT
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
    R3 = b['R2'].to_3d()
    mid = ROOT + R3 * 0.07 + Z * 0.23

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
    T3 = b['T_axis']
    three_q = (R3 * 0.55 - T3 * 0.85).normalized()
    shot(mid + three_q * 1.0 + Vector((0, 0, 0.22)), mid, 40, 'lamp_34.png', (900, 1100))
    side = T3 if T3.dot((SEAT - mid).normalized()) > 0 else -T3
    shot(mid + side * 1.4, mid, 50, 'lamp_side.png', (1000, 1100), ortho=0.62)
    shot(SEAT, mid + Vector((0, 0, 0.02)), 40, 'lamp_seat.png')
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
