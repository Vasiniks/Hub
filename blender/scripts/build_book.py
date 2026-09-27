"""
Hardcover book — one canonical model the shelf resizes per book.

A box with a cover texture reads as a box. What makes a book read as a book, even at shelf
distance, is the construction: the boards overhang the page block (the "squares") at the top,
bottom and fore-edge; the spine is rounded; there is a hinge groove running down each board
beside the spine; the page block is set back and its fore-edge is very slightly concave; and a
headband peeks out at the top and bottom of the spine.

The case is one U-shaped profile — back board, spine arc, front board, grooves included —
extruded to height, so it is a single clean solid with no intersecting parts. The page block
is built as a stack of thin leaves with alternating micro-insets plus a seeded jitter, so the
fore-edge carries real geometric page variation instead of texture lines alone. UVs are laid
out here, per face corner, into the regions of the shelf's per-book atlas (cover, spine, page
edges, and two swatches added for board edges and the headband), so every book is still one
mesh and one draw call.

Sizes vary per book. The runtime 9-slices this model: vertices within `slice` of a face keep
their distance to it and only the interior stretches, so boards, squares and grooves stay the
same real thickness on a 18 mm paperback-thin book and a 44 mm one. Written to the sidecar.
Keep T/H/D, the slice margins and every atlas region stable: `bookshelf.ts` depends on them.
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]

T, H, D = 0.030, 0.220, 0.145     # canonical thickness, height, depth
BT = 0.0022                       # board thickness
OV = 0.0028                       # squares: how far the boards overhang the pages
JOINT = 0.0078                    # hinge groove distance from the spine
GW, GD = 0.0026, 0.0007           # groove width and depth
BULGE = 0.0036                    # how far the rounded spine stands out
ARC = 14
SLICE_X = 0.0042
SLICE_Y = 0.0070

# Atlas regions, matching src/scene/bookshelf.ts.
COVER_U = (0.0, 0.6)
EDGE_U = 0.61                     # board-edge swatch, painted in the cover colour
SPINE_U = (0.62, 0.74)
BAND_U = 0.76                     # headband swatch, painted in the accent colour
PAGE_U = (0.78, 1.0)

lib.reset()

t = T / 2
S0 = -D / 2                        # Blender -Y becomes glTF +Z: the spine faces the room
F = D / 2


def lerp(r, k):
    return r[0] + (r[1] - r[0]) * max(0.0, min(1.0, k))


def case_profile():
    j = S0 + JOINT
    ch = 0.0009  # fore-edge corner chamfer: boards are cut card, not razor extrusions
    pts = [(t - ch, F), (t, F - ch), (t, j + GW / 2), (t - GD, j + GW / 4), (t - GD, j - GW / 4),
           (t, j - GW / 2), (t, S0)]
    for s in range(1, ARC):
        a = math.pi * s / ARC
        pts.append((t * math.cos(a), S0 - BULGE * math.sin(a)))
    pts += [(-t, S0), (-t, j - GW / 2), (-t + GD, j - GW / 4), (-t + GD, j + GW / 4),
            (-t, j + GW / 2), (-t, F - ch), (-t + ch, F), (-t + BT + ch, F),
            (-t + BT, F - ch), (-t + BT, S0)]
    ib = BULGE - BT
    for s in range(ARC - 1, 0, -1):
        a = math.pi * s / ARC
        pts.append(((t - BT) * math.cos(a), S0 - ib * math.sin(a)))
    pts += [(t - BT, S0), (t - BT, F - ch), (t - BT + ch, F)]
    return pts


LEAVES = 10  # page-block layers: real geometric page variation on the fore-edge


def pages_outline(inset):
    """Plan-view outline of the page block, pushed inward by `inset` metres."""
    p = t - BT - 0.0005 - inset
    pts = []
    for s in range(0, ARC + 1):
        a = math.pi * s / ARC
        pts.append((p * math.cos(a), S0 + 0.0009 - 0.0006 * math.sin(a)))
    for s in range(0, 11):
        x = -p + 2 * p * s / 10
        pts.append((x, F - OV - inset - 0.0012 * (1 - (x / p) ** 2)))
    # The fore-edge's first and last samples duplicate the arc ends' x; nudge to keep it simple.
    return pts


def pages_profile():
    return pages_outline(0.0)


def prism(bm, profile, z0, z1):
    lo = [bm.verts.new((x, y, z0)) for x, y in profile]
    hi = [bm.verts.new((x, y, z1)) for x, y in profile]
    n = len(profile)
    for i in range(n):
        bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    bm.faces.new(list(reversed(lo)))
    bm.faces.new(hi)


def leaves(bm, z0, z1, count):
    """Stacked page leaves: alternating micro-insets + seeded jitter per leaf."""
    rng = random.Random(4177)
    rings = []
    for l in range(count + 1):
        z = z0 + (z1 - z0) * l / count
        inset = 0.00012 * (1 if l % 2 == 0 else -1) + rng.uniform(-0.00005, 0.00005)
        rings.append([bm.verts.new((x, y, z)) for x, y in pages_outline(inset)])
    n = len(rings[0])
    faces = []
    for a_, b_ in zip(rings, rings[1:]):
        for k in range(n):
            faces.append(bm.faces.new((a_[k], a_[(k + 1) % n], b_[(k + 1) % n], b_[k])))
    faces.append(bm.faces.new(list(reversed(rings[0]))))
    faces.append(bm.faces.new(rings[-1]))
    return faces


def band(bm, z):
    """A headband: a small rolled cord at the spine end of the page block."""
    r = 0.0009
    length = 2 * (t - BT - 0.0012)
    ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r, depth=length)
    for v in ret['verts']:
        x, y, zz = v.co
        v.co = Vector((zz, S0 + 0.0013 + y, z + x))


bm = bmesh.new()
prism(bm, case_profile(), 0.0, H)
case_faces = set(bm.faces)
page_faces = set(leaves(bm, OV, H - OV, LEAVES))
before = set(bm.faces)
band(bm, OV + 0.0006)
band(bm, H - OV - 0.0006)
band_faces = set(bm.faces) - before

bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
bm.normal_update()
uv = bm.loops.layers.uv.new('UVMap')


def set_uv(f, fn):
    for loop in f.loops:
        loop[uv].uv = fn(loop.vert.co)


for f in bm.faces:
    n, c = f.normal, f.calc_center_median()
    if f in band_faces:
        set_uv(f, lambda co: (BAND_U, 0.5))
    elif f in case_faces:
        if c.y < S0 + JOINT and abs(n.z) < 0.7:
            # Spine: across the width left to right as seen from the room, up the height.
            set_uv(f, lambda co: (lerp(SPINE_U, (co.x + t) / T), co.z / H))
        elif n.x > 0.7 and c.x > t - GD - 1e-4:
            set_uv(f, lambda co: (lerp(COVER_U, (co.y - S0) / D), co.z / H))
        elif n.x < -0.7 and c.x < -t + GD + 1e-4:
            set_uv(f, lambda co: (lerp(COVER_U, 1 - (co.y - S0) / D), co.z / H))
        else:
            set_uv(f, lambda co: (EDGE_U, 0.5))
    else:
        if abs(n.z) > 0.7:
            set_uv(f, lambda co: (lerp(PAGE_U, (co.y - S0) / D), (co.x + t) / T))
        else:
            set_uv(f, lambda co: (lerp(PAGE_U, co.z / H), (co.x + t) / T))

me = bpy.data.meshes.new('book')
mat = lib.material('book_mat', lib.hex_rgb('#8a8a8a'), roughness=0.78)
me.materials.append(mat)
bm.to_mesh(me)
bm.free()
obj = bpy.data.objects.new('book', me)
bpy.context.collection.objects.link(obj)
lib.shade_auto(obj, 40)
# Atlas UVs above are the shelf's contract — keep them, only reserve Lightmap.
lib.uv_unwrap(obj, redo_base=False)

# Base on the shelf, centred in thickness and depth.
lib.recentre([obj], 'base')
print(f'  book: {lib.tri_count(obj)} tris')
lib.export(OUT, [obj])
lib.write_meta(OUT, {'thickness': T, 'height': H, 'depth': D + BULGE,
                     'sliceX': SLICE_X, 'sliceY': SLICE_Y})
