"""
Hardcover book — one canonical model the shelf resizes per book.

A box with a cover texture reads as a box. What makes a book read as a book, even at shelf
distance, is the construction: the boards overhang the page block (the "squares") at the top,
bottom and fore-edge; the spine is rounded; there is a hinge groove running down each board
beside the spine; the page block is set back and its fore-edge is very slightly concave; and a
headband peeks out at the top and bottom of the spine.

The case is one U-shaped profile — back board, spine arc, front board, grooves included —
extruded to height, so it is a single clean solid with no intersecting parts. The page block
is a second profile. UVs are laid out here, per face corner, into the regions of the shelf's
per-book atlas (cover, spine, page edges, and two swatches added for board edges and the
headband), so every book is still one mesh and one draw call.

Sizes vary per book. The runtime 9-slices this model: vertices within `slice` of a face keep
their distance to it and only the interior stretches, so boards, squares and grooves stay the
same real thickness on a 18 mm paperback-thin book and a 44 mm one. Written to the sidecar.
"""
import bpy
import bmesh
import math
import os
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
    pts = [(t, F), (t, j + GW / 2), (t - GD, j + GW / 4), (t - GD, j - GW / 4), (t, j - GW / 2), (t, S0)]
    for s in range(1, ARC):
        a = math.pi * s / ARC
        pts.append((t * math.cos(a), S0 - BULGE * math.sin(a)))
    pts += [(-t, S0), (-t, j - GW / 2), (-t + GD, j - GW / 4), (-t + GD, j + GW / 4), (-t, j + GW / 2),
            (-t, F), (-t + BT, F), (-t + BT, S0)]
    ib = BULGE - BT
    for s in range(ARC - 1, 0, -1):
        a = math.pi * s / ARC
        pts.append(((t - BT) * math.cos(a), S0 - ib * math.sin(a)))
    pts += [(t - BT, S0), (t - BT, F)]
    return pts


def pages_profile():
    p = t - BT - 0.0005
    pts = []
    for s in range(0, ARC + 1):
        a = math.pi * s / ARC
        pts.append((p * math.cos(a), S0 + 0.0009 - 0.0006 * math.sin(a)))
    for s in range(0, 11):
        x = -p + 2 * p * s / 10
        pts.append((x, F - OV - 0.0012 * (1 - (x / p) ** 2)))
    # The fore-edge's first and last samples duplicate the arc ends' x; nudge to keep it simple.
    return pts


def prism(bm, profile, z0, z1):
    lo = [bm.verts.new((x, y, z0)) for x, y in profile]
    hi = [bm.verts.new((x, y, z1)) for x, y in profile]
    n = len(profile)
    for i in range(n):
        bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    bm.faces.new(list(reversed(lo)))
    bm.faces.new(hi)


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
prism(bm, pages_profile(), OV, H - OV)
page_faces = set(bm.faces) - case_faces
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

# Base on the shelf, centred in thickness and depth.
lib.recentre([obj], 'base')
print(f'  book: {lib.tri_count(obj)} tris')
lib.export(OUT, [obj])
lib.write_meta(OUT, {'thickness': T, 'height': H, 'depth': D + BULGE,
                     'sliceX': SLICE_X, 'sliceY': SLICE_Y})
