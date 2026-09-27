"""
Furniture group remodel (ws/model-furniture).

One script builds all four groups into one scene (collections Chair/Desk/Shelf/Trim),
saves the editable source `blender/source/furniture.blend` (render-ready: one camera per
group, 3-point lights, `//render/` output path), exports `chair/desk/shelf/trim.glb` +
JSON sidecars to `assets/processed/`, then `node scripts/optimize-glb.mjs` quantises them
into `public/assets/processed/` — the existing pipeline, no new one.

Dimensions match `src/scene/layout.ts` exactly (DESK, SHELF, ROOM.window), so no layout
change and all interaction verifies keep passing. All geometry modelled from scratch —
no third-party geometry, no licence rows needed.

Hard-surface standard (see lib.py helpers): bevelled edges everywhere, quads on visible
curved surfaces, metres, Z-up, origin at the natural base/pivot, UVMap + reserved
Lightmap channel, shared palette material names the runtime retints.

Usage: ~/.local/bin/blender --background --factory-startup --python
  blender/scripts/build_furniture.py -- <assets_dir> <blend_path> [chair|desk|shelf|trim|all]
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

ASSETS_DIR = lib.argv()[0] if len(lib.argv()) > 0 else 'assets/processed'
BLEND_OUT = lib.argv()[1] if len(lib.argv()) > 1 else 'blender/source/furniture.blend'
ONLY = lib.argv()[2] if len(lib.argv()) > 2 else 'all'


# --------------------------------------------------------------------------- toolkit

def new_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def finish(coll, parts, bm, name, mat, smooth=35):
    """Close a bmesh into a mesh object inside collection `coll`; return object."""
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    me.materials.append(mat)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    lib.shade_auto(o, smooth)
    parts.append(o)
    return o


def join_bm(target, source):
    me = bpy.data.meshes.new('tmp')
    source.to_mesh(me)
    source.free()
    target.from_mesh(me)
    bpy.data.meshes.remove(me)


def tube(r, p0, p1, verts=16, cap=True):
    bm = bmesh.new()
    d = Vector(p1) - Vector(p0)
    ret = bmesh.ops.create_cone(bm, cap_ends=cap, segments=verts, radius1=r, radius2=r, depth=d.length)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((Vector(p0) + Vector(p1)) / 2) @ rot, verts=ret['verts'])
    return bm


def box_bm(sx, sy, sz, loc=(0, 0, 0), bevel=0.0):
    """A box bmesh with an optional real bevel — the primitive behind every hard part."""
    bm = bmesh.new()
    ret = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(loc)) @ Matrix.Diagonal((sx, sy, sz, 1)),
                        verts=ret['verts'])
    if bevel:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2,
                        affect='EDGES', clamp_overlap=True)
    return bm


def cushion(a, b, r, top, bottom, n=9, place=None):
    """
    A closed cushion: grid top + grid bottom over a rounded-rect outline, joined by a side
    band, rim rounded with a second bevel loop. Same loft as build_chair.py — the seat,
    back, lumbar and arm pads all come from here so the whole chair shares one edge radius
    language.
    """
    bm = bmesh.new()
    ring = lib.ring_indices(n)

    def grid(fn):
        g = {}
        for i in range(n):
            for j in range(n):
                u, v = 2 * i / (n - 1) - 1, 2 * j / (n - 1) - 1
                x, y = lib.rounded(u, v, a, b, r)
                p = Vector((x, y, fn(x, y)))
                g[(i, j)] = bm.verts.new(place(p) if place else p)
        return g

    t = grid(top)
    bo = grid(bottom)
    for i in range(n - 1):
        for j in range(n - 1):
            bm.faces.new((t[(i, j)], t[(i + 1, j)], t[(i + 1, j + 1)], t[(i, j + 1)]))
            bm.faces.new((bo[(i, j)], bo[(i, j + 1)], bo[(i + 1, j + 1)], bo[(i + 1, j)]))
    rt = [t[k] for k in ring]
    rb = [bo[k] for k in ring]
    for k in range(len(ring)):
        bm.faces.new((rb[k], rb[(k + 1) % len(ring)], rt[(k + 1) % len(ring)], rt[k]))
    edges = [e for e in bm.edges if all(v in rt for v in e.verts)]
    bmesh.ops.bevel(bm, geom=edges, offset=0.012, segments=2, affect='EDGES', profile=0.6,
                    clamp_overlap=True)
    return bm


def curve_tube(points, radius, name, material, closed=False, res_u=2, bev_res=1):
    """A piping cord / seam following `points` — seat piping, cable runs."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = bev_res
    cu.resolution_u = res_u
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    sp.use_cyclic_u = closed
    cu.use_fill_caps = True
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    lib.activate(o)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.view_layer.objects.active
    o.name = name
    lib.set_materials(o, [material])
    lib.shade_auto(o, 60)
    bpy.context.scene.collection.objects.unlink(o)
    return o


def prep(obj):
    """Modifiers applied, clean UVs + reserved lightmap channel, transforms applied."""
    lib.apply_modifiers(obj)
    lib.clean(obj)
    lib.uv_unwrap(obj)
    lib.add_lightmap_uv(obj)
    lib.shade_auto(obj, 40)
    return obj


def export_group(name, mesh, meta):
    out = os.path.join(ASSETS_DIR, f'{name}.glb')
    total, size = lib.export(out, [mesh])
    lib.write_meta(out, meta)
    return total, size


# --------------------------------------------------------------------------- CHAIR
# Frame matches build_chair.py: seat front toward +Y, backrest toward -Y, origin on the
# floor under the gas lift (the runtime rolls/turns the chair about it), casters on z=0.

CHAIR_MATS = {
    'chair_fabric': ('#2b2e33', 0.92, 0.0),
    'chair_plastic': ('#141518', 0.5, 0.0),
    'chair_metal': ('#8d9399', 0.35, 1.0),
    'chair_rubber': ('#0d0e10', 0.85, 0.0),
}

SEAT_Z = 0.44
HUB_Z = 0.075


def build_chair():
    coll = new_collection('Chair')
    MAT = {k: lib.material(k, lib.hex_rgb(c), roughness=r, metallic=m)
           for k, (c, r, m) in CHAIR_MATS.items()}
    PARTS = []

    def fin(bm, name, mat, smooth=40):
        return finish(coll, PARTS, bm, name, MAT[mat], smooth)

    # ---- five-star die-cast base: tapered arms with a top stiffening rib ----
    base = bmesh.new()
    for k in range(5):
        ang = 2 * math.pi * k / 5
        arm = bmesh.new()
        steps = 5
        rings = []
        for s in range(steps + 1):
            t = s / steps
            x = 0.030 + t * 0.265
            w = 0.026 - t * 0.012
            h = 0.032 - t * 0.014
            zc = HUB_Z - t * 0.014
            rings.append([arm.verts.new((x, sy * w, zc + sz * h / 2))
                          for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        for s in range(steps):
            a_, b_ = rings[s], rings[s + 1]
            for q in range(4):
                arm.faces.new((a_[q], a_[(q + 1) % 4], b_[(q + 1) % 4], b_[q]))
        arm.faces.new(list(reversed(rings[0])))
        arm.faces.new(rings[-1])
        # Stiffening rib along the arm's spine — the die-cast read.
        rib = bmesh.new()
        rsteps, rw, rh = 4, 0.007, 0.006
        rrings = []
        for s in range(rsteps + 1):
            t = s / rsteps
            x = 0.045 + t * 0.225
            zc = HUB_Z + 0.016 - t * 0.014
            rrings.append([rib.verts.new((x, sy * rw, zc + sz * rh / 2))
                           for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        for s in range(rsteps):
            a_, b_ = rrings[s], rrings[s + 1]
            for q in range(4):
                rib.faces.new((a_[q], a_[(q + 1) % 4], b_[(q + 1) % 4], b_[q]))
        rib.faces.new(list(reversed(rrings[0])))
        rib.faces.new(rrings[-1])
        join_bm(arm, rib)
        bmesh.ops.bevel(arm, geom=list(arm.edges), offset=0.0035, segments=2,
                        affect='EDGES', clamp_overlap=True)
        bmesh.ops.rotate(arm, verts=arm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(ang, 3, 'Z'))
        join_bm(base, arm)
    join_bm(base, tube(0.048, (0, 0, HUB_Z - 0.022), (0, 0, HUB_Z + 0.022), verts=24))
    fin(base, 'chair_base', 'chair_plastic')
    # Hub trim ring + cap.
    fin(tube(0.049, (0, 0, 0.090), (0, 0, 0.098), verts=16), 'chair_hub_ring', 'chair_metal')
    fin(tube(0.020, (0, 0, 0.096), (0, 0, 0.104), verts=12), 'chair_hub_cap', 'chair_plastic')

    # ---- casters with real forks: stem, swivel cup, yoke plates, axle, twin wheels ----
    casters = bmesh.new()
    forks = bmesh.new()
    for k in range(5):
        ang = 2 * math.pi * k / 5
        c = bmesh.new()
        for side in (-1, 1):
            # Wheel: rounded-tread cylinder on a Y axle, trailing behind the stem.
            w = bmesh.new()
            ret = bmesh.ops.create_cone(w, cap_ends=True, segments=14, radius1=0.028,
                                        radius2=0.028, depth=0.014)
            bmesh.ops.transform(w, verts=ret['verts'],
                                matrix=Matrix.Translation((-0.020, side * 0.0135, 0.028)) @
                                Matrix.Rotation(math.pi / 2, 4, 'X'))
            bmesh.ops.bevel(w, geom=list(w.edges), offset=0.004, segments=2,
                            affect='EDGES', clamp_overlap=True)
            join_bm(c, w)
            # Yoke plate over each wheel, rising to the swivel.
            yoke = box_bm(0.046, 0.005, 0.034, loc=(-0.014, side * 0.0235, 0.042), bevel=0.002)
            join_bm(c, yoke)
        join_bm(c, tube(0.005, (-0.020, -0.026, 0.028), (-0.020, 0.026, 0.028), verts=10))  # axle
        for side in (-1, 1):
            join_bm(c, tube(0.008, (-0.020, side * 0.024, 0.028),
                            (-0.020, side * 0.030, 0.028), verts=6))  # bolt heads
        join_bm(c, tube(0.007, (-0.006, 0, 0.030), (-0.006, 0, 0.058), verts=10))  # stem
        join_bm(c, tube(0.014, (-0.006, 0, 0.052), (-0.006, 0, 0.062), verts=14))  # swivel cup
        # Caster trail: wheels sit behind the stem, like the real thing.
        bmesh.ops.rotate(c, verts=c.verts, cent=(0, 0, 0),
                         matrix=Matrix.Rotation(0.9 * math.sin(k * 2.3), 3, 'Z'))
        bmesh.ops.translate(c, verts=c.verts, vec=(0.295, 0, 0))
        bmesh.ops.rotate(c, verts=c.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(ang, 3, 'Z'))
        join_bm(casters, c)
    fin(casters, 'chair_casters', 'chair_rubber')
    fin(forks, 'chair_forks', 'chair_plastic')

    # ---- gas lift: telescoping 3-stage (shroud, sleeve, chrome piston) ----
    fin(tube(0.030, (0, 0, HUB_Z - 0.005), (0, 0, 0.27), verts=20), 'chair_lift_shroud', 'chair_plastic')
    fin(tube(0.020, (0, 0, 0.26), (0, 0, 0.335), verts=16), 'chair_lift_sleeve', 'chair_plastic')
    fin(tube(0.014, (0, 0, 0.30), (0, 0, 0.415), verts=16), 'chair_piston', 'chair_metal')

    # ---- tilt mechanism: housing, side caps, tension knob, levers, slider rails ----
    mech = bmesh.new()
    join_bm(mech, box_bm(0.20, 0.24, 0.055, loc=(0, 0.01, SEAT_Z - 0.038), bevel=0.008))
    for side in (-1, 1):
        cap = bmesh.new()
        ret = bmesh.ops.create_cone(cap, cap_ends=True, segments=14, radius1=0.034,
                                    radius2=0.034, depth=0.012)
        bmesh.ops.transform(cap, verts=ret['verts'],
                            matrix=Matrix.Translation((side * 0.104, 0.01, SEAT_Z - 0.038)) @
                            Matrix.Rotation(math.pi / 2, 4, 'Y'))
        join_bm(mech, cap)
    join_bm(mech, tube(0.016, (0.10, -0.02, SEAT_Z - 0.04), (0.155, -0.02, SEAT_Z - 0.04), verts=14))
    join_bm(mech, tube(0.022, (0.155, -0.02, SEAT_Z - 0.04), (0.180, -0.02, SEAT_Z - 0.04), verts=12))
    join_bm(mech, tube(0.004, (-0.10, 0.06, SEAT_Z - 0.03), (-0.20, 0.10, SEAT_Z - 0.055), verts=8))
    join_bm(mech, box_bm(0.055, 0.022, 0.008, loc=(-0.215, 0.105, SEAT_Z - 0.058), bevel=0.003))
    join_bm(mech, tube(0.004, (0.10, 0.06, SEAT_Z - 0.03), (0.19, 0.09, SEAT_Z - 0.05), verts=8))
    join_bm(mech, box_bm(0.05, 0.02, 0.008, loc=(0.20, 0.095, SEAT_Z - 0.053), bevel=0.003))
    for side in (-1, 1):
        join_bm(mech, box_bm(0.030, 0.20, 0.012, loc=(side * 0.09, 0.0, SEAT_Z - 0.012), bevel=0.003))
    fin(mech, 'chair_mechanism', 'chair_plastic')

    # ---- seat shell tray + cushion with bolsters, dish, waterfall, piping ----
    shell = cushion(0.245, 0.235, 0.07, lambda x, y: SEAT_Z - 0.006,
                    lambda x, y: SEAT_Z - 0.024, n=7)
    fin(shell, 'chair_seat_shell', 'chair_plastic')

    def seat_top(x, y):
        dish = -0.012 * (1 - (x / 0.25) ** 2) * (1 - ((y + 0.02) / 0.24) ** 2)
        rear = 0.008 * max(0.0, -y / 0.24) ** 2
        front = -0.035 * max(0.0, (y - 0.12) / 0.12) ** 2
        bolster = 0.010 * max(0.0, (abs(x) - 0.13) / 0.12) ** 2
        return SEAT_Z + 0.07 + dish + rear + front + bolster

    seat = cushion(0.25, 0.24, 0.075, seat_top, lambda x, y: SEAT_Z - 0.008, n=11)
    fin(seat, 'chair_seat', 'chair_fabric', 50)

    # Piping cord around the seat's mid-side — the upholstery read.
    pipe_pts = []
    for i in range(40):
        u = math.cos(2 * math.pi * i / 40)
        v = math.sin(2 * math.pi * i / 40)
        x, y = lib.rounded(u, v, 0.240, 0.230, 0.068)
        pipe_pts.append((x, y, SEAT_Z + 0.030))
    pipe = curve_tube(pipe_pts, 0.0038, 'chair_seat_piping', MAT['chair_fabric'], closed=True)
    coll.objects.link(pipe)
    PARTS.append(pipe)

    # ---- backrest: wrapped + lumbar, shell with carry handle + rear ribs ----
    BACK_BASE = SEAT_Z + 0.12
    BACK_H = 0.56

    def back_place(p):
        s = (p.y + BACK_H / 2) / BACK_H
        lumbar = 0.028 * math.exp(-((s - 0.28) / 0.18) ** 2)
        wrap = 0.09 * (p.x / 0.23) ** 2
        recline = 0.12 * s
        depth = p.z
        return Vector((p.x, -0.26 - recline + depth + lumbar + wrap, BACK_BASE + s * BACK_H))

    def back_top(x, y):
        return 0.045 + 0.012 * (x / 0.23) ** 2

    back = cushion(0.23, BACK_H / 2, 0.09, back_top, lambda x, y: 0.0, n=11, place=back_place)
    fin(back, 'chair_back', 'chair_fabric', 50)

    def back_shell_place(p):
        q = back_place(p)
        return Vector((q.x, q.y - 0.005, q.z))

    back_shell_bm = cushion(0.225, BACK_H / 2 - 0.01, 0.09, lambda x, y: 0.0,
                            lambda x, y: -0.012, n=9, place=back_shell_place)
    back_shell = finish(coll, PARTS, back_shell_bm, 'chair_back_shell_tmp', MAT['chair_plastic'], 50)
    # Carry-handle slot near the top of the shell.
    slot_at = back_place(Vector((0, 0.82 * BACK_H - BACK_H / 2, 0.0)))
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(slot_at.x, slot_at.y, slot_at.z))
    cutter = bpy.context.object
    cutter.scale = (0.13, 0.030, 0.05)
    lib.apply_transforms(cutter)
    m = back_shell.modifiers.new('handle', 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = cutter
    m.solver = 'EXACT'
    lib.apply_modifiers(back_shell)
    lib.drop([cutter])
    back_shell.name = 'chair_back_shell'
    # Rear stiffening ribs following the recline — sunk halfway so they read as beads.
    ribs = bmesh.new()
    for s in (0.15, 0.30, 0.45, 0.60, 0.72):
        py = s * (BACK_H - 0.02) - (BACK_H - 0.02) / 2
        q = back_place(Vector((0, py, -0.012)))
        join_bm(ribs, box_bm(0.27 * (1 - 0.25 * s), 0.010, 0.006,
                             loc=(q.x, q.y - 0.003, q.z), bevel=0.002))
    fin(ribs, 'chair_back_ribs', 'chair_plastic')

    # Lumbar pad on its own bracket — the adjustment read.
    lumbar_bm = cushion(0.15, 0.085, 0.035, lambda x, y: 0.030, lambda x, y: 0.0, n=7,
                        place=lambda p: back_place(Vector((p.x, 0.30 * BACK_H - BACK_H / 2 + p.y * 0.4,
                                                           0.055 + p.z))))
    fin(lumbar_bm, 'chair_lumbar', 'chair_fabric', 50)
    pad_q = back_place(Vector((0, 0.30 * BACK_H - BACK_H / 2, 0.02)))
    spine_q = Vector((0, -0.295, BACK_BASE + 0.30 * BACK_H - 0.06))
    bracket = bmesh.new()
    d = pad_q - spine_q
    ret = bmesh.ops.create_cube(bracket, size=1.0)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bracket,
                        matrix=Matrix.Translation((spine_q + pad_q) / 2) @ rot @
                        Matrix.Diagonal((0.05, 0.024, d.length + 0.02, 1)), verts=ret['verts'])
    bmesh.ops.bevel(bracket, geom=list(bracket.edges), offset=0.005, segments=2,
                    affect='EDGES', clamp_overlap=True)
    fin(bracket, 'chair_lumbar_bracket', 'chair_plastic')
    # Lumbar height knob tucked against the bracket.
    fin(tube(0.014, (0.024, -0.29, BACK_BASE + 0.10), (0.040, -0.29, BACK_BASE + 0.10), verts=12),
        'chair_lumbar_knob', 'chair_plastic')

    # ---- spine: mechanism, under the seat, up into the shell ----
    spine = bmesh.new()
    pts = [(0, -0.05, SEAT_Z - 0.03), (0, -0.22, SEAT_Z - 0.02), (0, -0.272, SEAT_Z + 0.08),
           (0, -0.29, BACK_BASE + 0.10), (0, -0.293, BACK_BASE + 0.30)]
    for p0, p1 in zip(pts, pts[1:]):
        seg = bmesh.new()
        d = Vector(p1) - Vector(p0)
        ret = bmesh.ops.create_cube(seg, size=1.0)
        rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
        bmesh.ops.transform(seg, matrix=Matrix.Translation((Vector(p0) + Vector(p1)) / 2) @ rot @
                            Matrix.Diagonal((0.045, 0.018, d.length + 0.02, 1)), verts=ret['verts'])
        bmesh.ops.bevel(seg, geom=list(seg.edges), offset=0.005, segments=2,
                        affect='EDGES', clamp_overlap=True)
        join_bm(spine, seg)
    fin(spine, 'chair_spine', 'chair_plastic')

    # ---- armrests: slide rail, sleeve post, inner slide + button, dished pad ----
    arms = bmesh.new()
    for side in (-1, 1):
        x = side * 0.27
        join_bm(arms, box_bm(0.05, 0.17, 0.020, loc=(x * 0.80, -0.02, SEAT_Z - 0.032), bevel=0.005))
        join_bm(arms, box_bm(0.034, 0.056, 0.150, loc=(x, -0.02, SEAT_Z + 0.045), bevel=0.008))
        join_bm(arms, box_bm(0.028, 0.046, 0.130, loc=(x, -0.02, SEAT_Z + 0.115), bevel=0.006))
        join_bm(arms, box_bm(0.072, 0.200, 0.012, loc=(x, 0.005, SEAT_Z + 0.188), bevel=0.004))
    fin(arms, 'chair_arm_posts', 'chair_plastic')
    for side in (-1, 1):
        x = side * 0.27
        btn = bmesh.new()
        ret = bmesh.ops.create_cone(btn, cap_ends=True, segments=14, radius1=0.008,
                                    radius2=0.008, depth=0.006)
        bmesh.ops.transform(btn, verts=ret['verts'],
                            matrix=Matrix.Translation((x + side * 0.020, -0.02, SEAT_Z + 0.10)) @
                            Matrix.Rotation(math.pi / 2, 4, 'Y'))
        fin(btn, f'chair_arm_button_{"L" if side < 0 else "R"}', 'chair_rubber')
    pads = bmesh.new()
    for side in (-1, 1):
        def pad_top(x, y, _s=side):
            return SEAT_Z + 0.222 - 0.008 * (1 - (x / 0.045) ** 2) + 0.006 * max(0.0, y / 0.125) ** 2
        pad = cushion(0.045, 0.125, 0.035, pad_top, lambda x, y: SEAT_Z + 0.196, n=7)
        bmesh.ops.translate(pad, verts=pad.verts, vec=(side * 0.27, 0.005, 0))
        bmesh.ops.rotate(pad, verts=pad.verts, cent=(side * 0.27, 0.005, SEAT_Z + 0.2),
                         matrix=Matrix.Rotation(side * 0.05, 3, 'Z'))
        join_bm(pads, pad)
    fin(pads, 'chair_arm_pads', 'chair_rubber')

    for o in PARTS:
        prep(o)
    chair = lib.join(PARTS, 'chair')
    # Kept like build_chair.py: no recentre — the runtime rolls the chair about the gas lift
    # (already the origin) and the casters already stand on z = 0.
    lib.apply_transforms(chair)
    lo, hi = lib.world_bounds([chair])
    print(f'  chair: {lib.tri_count(chair)} tris, {len(chair.data.materials)} materials, '
          f'bounds {tuple(round(v, 3) for v in lo)} {tuple(round(v, 3) for v in hi)}')
    meta = {'seatHeight': round(SEAT_Z + 0.07, 4), 'origin': 'gas lift axis, casters on z=0',
            'front': '+Y'}
    return coll, [(chair, meta)]


# --------------------------------------------------------------------------- DESK
# Local frame: origin on the floor under the desk centre, X = width, +Y = back
# (Blender +Y exports to world -Z, the window side), top surface at z = DESK.top.
# Runtime instances it at (DESK.centerX, 0, DESK.centerZ) with no rotation, so every
# dimension below is copied from src/scene/layout.ts DESK — no layout change.

DESK_DIMS = {'width': 2.04, 'depth': 0.78, 'top': 0.735, 'thickness': 0.032,
             'legInset': 0.13}

DESK_MATS = {
    'desk_white': ('#e9eaea', 0.6, 0.0),
    'desk_edge': ('#dcdee0', 0.65, 0.0),
    'desk_steel': ('#33373c', 0.4, 0.85),
    'desk_dark': ('#15171a', 0.6, 0.0),
    'desk_rubber': ('#0e0f11', 0.9, 0.0),
}


def build_desk():
    coll = new_collection('Desk')
    W, D, TOP, T, INSET = (DESK_DIMS[k] for k in ('width', 'depth', 'top', 'thickness',
                                                 'legInset'))
    MAT = {k: lib.material(k, lib.hex_rgb(c), roughness=r, metallic=m)
           for k, (c, r, m) in DESK_MATS.items()}
    PARTS = []

    def fin(bm, name, mat, smooth=40):
        return finish(coll, PARTS, bm, name, MAT[mat], smooth)

    # ---- top: 32 mm slab with a 4 mm edge break that catches the window highlight ----
    top_bm = box_bm(W, D, T, loc=(0, 0, TOP - T / 2), bevel=0.004)
    top = finish(coll, PARTS, top_bm, 'desk_top_tmp', MAT['desk_white'])
    lib.set_materials(top, [MAT['desk_white'], MAT['desk_edge']])
    lib.assign_slot(top, lambda c, n: abs(n.z) < 0.5, 1)
    top.name = 'desk_top'

    # ---- apron rails: what gives the slab visible thickness from a seated eyeline ----
    fin(box_bm(W - 0.30, 0.024, 0.085, loc=(0, -(D / 2 - 0.075), TOP - T - 0.045), bevel=0.004),
        'desk_apron_front', 'desk_edge')
    fin(box_bm(W - 0.30, 0.024, 0.085, loc=(0, D / 2 - 0.075, TOP - T - 0.045), bevel=0.004),
        'desk_apron_back', 'desk_edge')

    # ---- T leg frames with joinery that reads: tapered foot, collar, column, bracket ----
    for s in (-1, 1):
        lx = s * (W / 2 - INSET)
        leg = bmesh.new()
        # Foot: long low extrusion with tapered ends + end caps.
        steps, rings = 5, []
        for i in range(steps + 1):
            t = i / steps
            y = -((D - 0.12) / 2) + t * (D - 0.12)
            taper = 1.0 - 0.35 * (abs(t - 0.5) * 2) ** 2
            w, h = 0.070 * taper, 0.030
            rings.append([leg.verts.new((lx + sx * w / 2, y, 0.023 + sz * h / 2))
                          for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        for i in range(steps):
            a_, b_ = rings[i], rings[i + 1]
            for q in range(4):
                leg.faces.new((a_[q], a_[(q + 1) % 4], b_[(q + 1) % 4], b_[q]))
        leg.faces.new(list(reversed(rings[0])))
        leg.faces.new(rings[-1])
        join_bm(leg, box_bm(0.078, 0.058, 0.022, loc=(lx, 0.02, 0.040), bevel=0.005))  # weld collar
        join_bm(leg, box_bm(0.064, 0.046, TOP - T - 0.055, loc=(lx, 0.02, (TOP - T + 0.045) / 2),
                            bevel=0.006))  # column
        join_bm(leg, box_bm(0.16, 0.13, 0.010, loc=(lx, 0.0, TOP - T - 0.006), bevel=0.003))
        for dx, dy in ((-0.06, -0.045), (0.06, -0.045), (-0.06, 0.045), (0.06, 0.045)):
            join_bm(leg, tube(0.0042, (lx + dx, dy, TOP - T - 0.011),
                              (lx + dx, dy, TOP - T - 0.001), verts=10))  # screws
        for gy in (-(D / 2 - 0.10), D / 2 - 0.10):
            join_bm(leg, tube(0.008, (lx, gy, 0.008), (lx, gy, 0.024), verts=10))  # glide stem
            join_bm(leg, tube(0.026, (lx, gy, 0.0), (lx, gy, 0.008), verts=16))  # glide disc
        bmesh.ops.bevel(leg, geom=list(leg.edges), offset=0.003, segments=2,
                        affect='EDGES', clamp_overlap=True)
        fin(leg, f'desk_leg_{"L" if s < 0 else "R"}', 'desk_steel')

    # ---- perforated cable tray under the back + articulated cable spine ----
    tray = bmesh.new()
    join_bm(tray, box_bm(W - 0.50, 0.20, 0.008, loc=(0, D / 2 - 0.14, TOP - 0.125), bevel=0.002))
    join_bm(tray, box_bm(W - 0.50, 0.008, 0.055, loc=(0, D / 2 - 0.245, TOP - 0.10), bevel=0.002))
    join_bm(tray, box_bm(W - 0.50, 0.008, 0.055, loc=(0, D / 2 - 0.035, TOP - 0.10), bevel=0.002))
    tray_obj = finish(coll, PARTS, tray, 'desk_tray_tmp', MAT['desk_steel'])
    cutters = []
    for i in range(12):
        x = -(W - 0.62) / 2 + i * (W - 0.62) / 11
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, D / 2 - 0.14, TOP - 0.125))
        c = bpy.context.object
        c.scale = (0.030, 0.10, 0.012)
        lib.apply_transforms(c)
        cutters.append(c)
    for c in cutters:
        m = tray_obj.modifiers.new('slot', 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.object = c
        m.solver = 'EXACT'
    lib.apply_modifiers(tray_obj)
    lib.drop(cutters)
    tray_obj.name = 'desk_tray'

    spine = bmesh.new()
    for i in range(8):
        t = i / 7
        join_bm(spine, box_bm(0.055 - 0.008 * t, 0.045 - 0.006 * t, 0.045,
                              loc=(0.55, D / 2 - 0.10, TOP - 0.16 - i * 0.062), bevel=0.008))
    fin(spine, 'desk_spine', 'desk_dark')

    # ---- grommets: dark ring + recessed throat at the back corners ----
    for gx in (-0.85, 0.85):
        fin(tube(0.034, (gx, D / 2 - 0.09, TOP - 0.004), (gx, D / 2 - 0.09, TOP + 0.001),
                 verts=24), f'desk_grommet_ring_{"-" if gx < 0 else "+"}', 'desk_dark')
        fin(tube(0.026, (gx, D / 2 - 0.09, TOP - 0.006), (gx, D / 2 - 0.09, TOP - 0.002),
                 verts=20), f'desk_grommet_throat_{"-" if gx < 0 else "+"}', 'desk_rubber')

    for o in PARTS:
        prep(o)
    desk = lib.join(PARTS, 'desk')
    lib.apply_transforms(desk)
    lo, hi = lib.world_bounds([desk])
    print(f'  desk: {lib.tri_count(desk)} tris, {len(desk.data.materials)} materials, '
          f'bounds {tuple(round(v, 3) for v in lo)} {tuple(round(v, 3) for v in hi)}')
    meta = {'width': W, 'depth': D, 'top': TOP, 'thickness': T,
            'origin': 'floor under desk centre, +Y = back (window side)', 'instanceAt': [-0.02, 0, -0.74]}
    return coll, [(desk, meta)]


# --------------------------------------------------------------------------- SHELF
# Local frame = the bookshelf carcass group frame in src/scene/bookshelf.ts: +x along the
# wall, +z into the room, origin at the book-row level. Every plane below copies the code
# it replaces (bottom-board top at y=0, top-board underside at 0.312, back/ends/brackets
# clear of the book volume), so the slot geometry, row math and gesture springs are
# untouched — the books never know the carcass changed.

SHELF_DIMS = {'width': 0.74, 'depth': 0.2}

SHELF_MATS = {
    'shelf_board': ('#dcdee0', 0.65, 0.0),
    'shelf_steel': ('#33373c', 0.4, 0.85),
}


def build_shelf():
    # Shelf-local (x along wall, y up, z into room) -> Blender (x, -z, y), because the
    # glTF export maps Blender (x, y, z) to Y-up (x, z, -y).
    coll = new_collection('Shelf')
    W, D = SHELF_DIMS['width'], SHELF_DIMS['depth']
    MAT = {k: lib.material(k, lib.hex_rgb(c), roughness=r, metallic=m)
           for k, (c, r, m) in SHELF_MATS.items()}
    PARTS = []

    def fin(bm, name, mat, smooth=40):
        return finish(coll, PARTS, bm, name, MAT[mat], smooth)

    def sbox(w, d, h, lx, ly, lz, bevel=0.0):
        return box_bm(w, d, h, loc=(lx, -lz, ly), bevel=bevel)

    def stube(r, p0, p1, verts=12):
        f = lambda p: (p[0], -p[2], p[1])
        return tube(r, f(p0), f(p1), verts=verts)

    # ---- boards with a 3 mm edge break ----
    fin(sbox(W, D, 0.022, 0, -0.011, -D / 2, bevel=0.003), 'shelf_bottom', 'shelf_board')
    fin(sbox(W, D - 0.03, 0.02, 0, 0.322, -D / 2 - 0.012, bevel=0.003),
        'shelf_top', 'shelf_board')
    for s in (-1, 1):
        fin(sbox(0.017, D, 0.38, s * (W / 2 + 0.0085), 0.155, -D / 2, bevel=0.004),
            f'shelf_end_{"L" if s < 0 else "R"}', 'shelf_board')

    # ---- back panel with 5 real vertical grooves ----
    back_bm = sbox(W + 0.034, 0.009, 0.36, 0, 0.15, -D + 0.0045, bevel=0.002)
    back = finish(coll, PARTS, back_bm, 'shelf_back_tmp', MAT['shelf_board'])
    cutters = []
    for i in range(5):
        x = -(W - 0.10) / 2 + i * (W - 0.10) / 4
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, D - 0.0045, 0.15))
        c = bpy.context.object
        c.scale = (0.004, 0.012, 0.34)
        lib.apply_transforms(c)
        cutters.append(c)
    for c in cutters:
        m = back.modifiers.new('groove', 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.object = c
        m.solver = 'EXACT'
    lib.apply_modifiers(back)
    lib.drop(cutters)
    back.name = 'shelf_back'

    # ---- folded-steel L brackets: wall plate + screws, arm, gusset ----
    for s in (-1, 1):
        bx = s * (W / 2 - 0.09)
        br = bmesh.new()
        join_bm(br, sbox(0.012, D - 0.03, 0.012, bx, -0.028, -D / 2, bevel=0.002))  # arm
        join_bm(br, sbox(0.012, 0.030, 0.055, bx, -0.05, -0.03, bevel=0.002))  # drop plate
        join_bm(br, sbox(0.016, 0.009, 0.075, bx, -0.05, -D + 0.009, bevel=0.002))  # wall plate
        gus = sbox(0.010, 0.045, 0.045, bx, -0.038, -0.052, bevel=0.002)
        bmesh.ops.rotate(gus, verts=gus.verts, cent=(bx, 0.052, -0.038),
                         matrix=Matrix.Rotation(-math.pi / 4, 3, 'X'))
        join_bm(br, gus)
        for sy in (-0.072, -0.028):
            join_bm(br, stube(0.004, (bx, sy, -D + 0.0135),
                              (bx, sy, -D + 0.009), verts=10))  # screw heads
        fin(br, f'shelf_bracket_{"L" if s < 0 else "R"}', 'shelf_steel')

    # ---- LED channel rails under the top board (the code strip + light drop in) ----
    for dz in (-0.050, -0.030):
        fin(sbox(W - 0.06, 0.008, 0.006, 0, 0.309, dz, bevel=0.001),
            f'shelf_channel_{"-" if dz < -0.04 else "+"}', 'shelf_steel')

    for o in PARTS:
        prep(o)
    shelf = lib.join(PARTS, 'shelf')
    lib.apply_transforms(shelf)
    lo, hi = lib.world_bounds([shelf])
    print(f'  shelf: {lib.tri_count(shelf)} tris, {len(shelf.data.materials)} materials, '
          f'bounds {tuple(round(v, 3) for v in lo)} {tuple(round(v, 3) for v in hi)}')
    meta = {'width': W, 'depth': D,
            'origin': 'book-row level, +x along wall, +z into room',
            'rowInset': 0.07}
    return coll, [(shelf, meta)]


# --------------------------------------------------------------------------- TRIM
# Room-shell trim in WORLD coords (Blender (x, -z, y) maps to Y-up (x, y, z) on export):
# stepped window frame + glazing beads, architrave casing, bullnose sill + beaded apron,
# reveal liners with a shadow gap, skirting along all three walls. Floor disc, wall slabs
# and glass stay procedural (set-fade shader, tiled PBR, image-lighting glass) — the trim
# only replaces the flat bars. All planes copy src/scene/room.ts buildShell + layout ROOM.

TRIM_MATS = {
    'trim_frame': ('#23262a', 0.5, 0.55),
    'trim_sill': ('#dcdedf', 0.56, 0.0),
    'trim_wall': ('#94969a', 0.9, 0.0),
}

ROOM_DIMS = {'wallZ': -1.3, 'wallDepth': 0.24, 'x0': -1.32, 'x1': 1.02, 'y0': 0.7, 'y1': 2.5,
             'frameInset': 0.11, 'leftFace': -1.78, 'rightFace': 1.66}


def build_trim():
    coll = new_collection('Trim')
    wz, wd = ROOM_DIMS['wallZ'], ROOM_DIMS['wallDepth']
    x0, x1, y0, y1 = (ROOM_DIMS[k] for k in ('x0', 'x1', 'y0', 'y1'))
    fz = wz - ROOM_DIMS['frameInset']
    W, H = x1 - x0, y1 - y0
    fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
    t = 0.045
    MAT = {k: lib.material(k, lib.hex_rgb(c), roughness=r, metallic=m)
           for k, (c, r, m) in TRIM_MATS.items()}
    PARTS = []

    def fin(bm, name, mat, smooth=40):
        return finish(coll, PARTS, bm, name, MAT[mat], smooth)

    # ---- window frame: stepped bars (main + room-side glazing bead) ----
    def bar(w, h, x, y, bead=True):
        fin(box_bm(w, 0.06, h, loc=(x, -fz, y), bevel=0.003), f'trim_frame_{x:.2f}_{y:.2f}',
            'trim_frame')
        if bead:
            fin(box_bm(w - 0.012 if w > h else 0.012, 0.014,
                       (h - 0.012) if w > h else h, loc=(x, -(fz + 0.032), y), bevel=0.002),
                f'trim_bead_{x:.2f}_{y:.2f}', 'trim_frame')
    bar(W, t, fx, y0 + t / 2)
    bar(W, t, fx, y1 - t / 2)
    bar(t, H, x0 + t / 2, fy)
    bar(t, H, x1 - t / 2, fy)
    bar(t * 0.7, H - t * 2, fx, fy)
    bar(W - t * 2, t * 0.7, fx, y1 - 0.46)

    # ---- architrave casing: flat band + stepped inner band, on the room wall face ----
    cw, cz = 0.095, wz + 0.007
    for cx, cy, w, h in ((fx, y1 + cw / 2, W + 2 * cw, cw), (fx, y0 - cw / 2, W + 2 * cw, cw),
                         (x0 - cw / 2, fy, cw, H), (x1 + cw / 2, fy, cw, H)):
        fin(box_bm(w, 0.014, h, loc=(cx, -cz, cy), bevel=0.002),
            f'trim_case_{cx:.2f}_{cy:.2f}', 'trim_wall')

    # ---- sill: board + bullnose + apron with bead ----
    fin(box_bm(W + 0.16, 0.30, 0.038, loc=(fx, -(wz - 0.06), y0 - 0.019), bevel=0.004),
        'trim_sill', 'trim_sill')
    nose = bmesh.new()
    ret = bmesh.ops.create_cone(nose, cap_ends=True, segments=20, radius1=0.019,
                                radius2=0.019, depth=W + 0.16)
    bmesh.ops.transform(nose, verts=ret['verts'],
                        matrix=Matrix.Translation((fx, -(wz - 0.06) + 0.15, y0 - 0.019)) @
                        Matrix.Rotation(math.pi / 2, 4, 'Y'))
    fin(nose, 'trim_nose', 'trim_sill')
    fin(box_bm(W + 0.06, 0.03, 0.045, loc=(fx, -(wz + 0.085), y0 - 0.058), bevel=0.003),
        'trim_apron', 'trim_sill')
    fin(box_bm(W + 0.06, 0.012, 0.012, loc=(fx, -(wz + 0.085) + 0.012, y0 - 0.040), bevel=0.002),
        'trim_apron_bead', 'trim_sill')

    # ---- reveal liners (left/right/top) with a recessed shadow gap at the room edge ----
    for lx, lw in ((x0, 0.012), (x1, 0.012)):
        fin(box_bm(lw, wd, H, loc=(lx, -(wz - wd / 2), fy), bevel=0.002),
            f'trim_reveal_{lx:.2f}', 'trim_wall')
    fin(box_bm(W, wd, 0.012, loc=(fx, -(wz - wd / 2), y1), bevel=0.002), 'trim_reveal_top',
        'trim_wall')

    # ---- skirting: main board + cap, 1 mm proud of each wall face ----
    def skirt(length, x, z, along_x=True):
        w, d = (length, 0.015) if along_x else (0.015, length)
        fin(box_bm(w, d, 0.09, loc=(x, -z, 0.045), bevel=0.002), f'trim_skirt_{x:.2f}_{z:.2f}',
            'trim_wall')
        fin(box_bm(w if along_x else 0.020, d if not along_x else 0.020, 0.014,
                   loc=(x, -z, 0.083), bevel=0.002), f'trim_skirtcap_{x:.2f}_{z:.2f}',
            'trim_wall')
    skirt(3.0, ROOM_DIMS['leftFace'] + 0.0075, -0.1, along_x=False)
    skirt(3.0, ROOM_DIMS['rightFace'] - 0.0075, -0.1, along_x=False)
    skirt(6.8, 1.0, wz + 0.0075, along_x=True)

    for o in PARTS:
        prep(o)
    trim = lib.join(PARTS, 'trim')
    lib.apply_transforms(trim)
    lo, hi = lib.world_bounds([trim])
    print(f'  trim: {lib.tri_count(trim)} tris, {len(trim.data.materials)} materials, '
          f'bounds {tuple(round(v, 3) for v in lo)} {tuple(round(v, 3) for v in hi)}')
    meta = {'window': [x0, x1, y0, y1], 'origin': 'world coords',
            'glassOpening': [round(W - 2 * t, 4), round(H - 2 * t, 4)]}
    return coll, [(trim, meta)]


# --------------------------------------------------------------------------- studio + export

CAMERAS = {
    'chair': {'loc': (1.5, 1.9, 1.05), 'target': (0, 0, 0.55)},
    'desk': {'loc': (1.7, -1.7, 1.45), 'target': (0, 0.05, 0.42)},
    'shelf': {'loc': (0.8, -1.05, 0.55), 'target': (0, 0.10, 0.08)},
    'trim': {'loc': (1.3, -1.4, 1.7), 'target': (-0.15, 1.25, 1.5)},
}


def setup_studio(names):
    try:
        world = bpy.context.scene.world
        if world and world.use_nodes:
            bg = world.node_tree.nodes.get('Background')
            if bg:
                bg.inputs['Color'].default_value = (*lib.hex_rgb('#8a8f96'), 1.0)
                bg.inputs['Strength'].default_value = 0.6
    except Exception as err:
        print(f'  ! world setup skipped: {err}')
    for name in names:
        spec = CAMERAS[name]
        cam = bpy.data.cameras.new(f'{name}_cam')
        cam.lens = 50
        co = bpy.data.objects.new(f'{name}_cam', cam)
        bpy.context.scene.collection.objects.link(co)
        co.location = spec['loc']
        d = Vector(spec['target']) - Vector(spec['loc'])
        co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    try:
        key = bpy.data.lights.new('key', 'AREA')
        key.energy, key.size = 1500, 2.5
        ko = bpy.data.objects.new('key', key)
        ko.location = (3, 2, 4)
        bpy.context.scene.collection.objects.link(ko)
        fill = bpy.data.lights.new('fill', 'AREA')
        fill.energy, fill.size = 500, 2.5
        fo = bpy.data.objects.new('fill', fill)
        fo.location = (-3, 2.5, 2)
        bpy.context.scene.collection.objects.link(fo)
        rim = bpy.data.lights.new('rim', 'SUN')
        rim.energy = 3.0
        ro = bpy.data.objects.new('rim', rim)
        ro.rotation_euler = (math.radians(50), 0, math.radians(-140))
        bpy.context.scene.collection.objects.link(ro)
    except Exception as err:
        print(f'  ! light setup skipped: {err}')
    bpy.context.scene.render.filepath = '//render/preview_'
    bpy.context.scene.render.resolution_x = 800
    bpy.context.scene.render.resolution_y = 500
    bpy.context.scene.render.resolution_percentage = 100
    first = bpy.data.objects.get('chair_cam') or bpy.data.objects.get('desk_cam')
    if first:
        bpy.context.scene.camera = first


def main():
    lib.reset()
    built = {}
    if ONLY in ('chair', 'all'):
        coll, meshes = build_chair()
        built['chair'] = meshes
    if ONLY in ('desk', 'all'):
        coll, meshes = build_desk()
        built['desk'] = meshes
    if ONLY in ('shelf', 'all'):
        coll, meshes = build_shelf()
        built['shelf'] = meshes
    if ONLY in ('trim', 'all'):
        coll, meshes = build_trim()
        built['trim'] = meshes
    setup_studio(list(built))
    os.makedirs(os.path.dirname(BLEND_OUT) or '.', exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
    print(f'SAVED {BLEND_OUT}')
    for name, meshes in built.items():
        for mesh, meta in meshes:
            total, size = export_group(name, mesh, meta)
    for name in built:
        cam = bpy.data.objects.get(f'{name}_cam')
        if cam is None:
            continue
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = os.path.join(os.path.dirname(BLEND_OUT), 'render',
                                                         f'preview_{name}_')
        bpy.ops.render.render(write_still=True)
        print(f'PREVIEW preview_{name}_')
    chair_cam = bpy.data.objects.get('chair_cam')
    if chair_cam:
        bpy.context.scene.camera = chair_cam
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)


main()
