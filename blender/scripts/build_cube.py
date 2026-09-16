"""
GAN-style 3x3 speedcube.

What makes a speedcube read as a speedcube rather than as a Rubik's Cube is that it is
stickerless and heavily rounded. The colour is not a tile laid on a dark body — it *is* the
piece, moulded plastic that carries on over the rounded edge until it meets the next piece's
colour at the arris. A first version built inset tiles instead, and they came out larger than
the bevelled face could hold, so every one of them wrapped over its own edge like a slab.

So: 26 cubie bodies, bevelled, with each face's colour decided by which way it points and
whether the piece it belongs to is on that side of the cube. Interior faces stay dark, which
is what shows in the seams. Each exterior face carries a shallow inset groove — the moulding
line — and the whole assembly is then pushed a little way toward a sphere, which is what
pillowing actually is.

The U layer is caught mid-turn, and a seeded handful of pieces wear a neighbour's colour, so
the cube reads as something someone was using rather than as a boxed product shot.
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.argv()[0]

SIZE = 0.056                  # a 3x3 speedcube is 55-56 mm across
CUBIE = SIZE / 3
GAP = 0.0014                  # the seam between adjacent pieces
BODY = CUBIE - GAP
BEVEL = 0.0017                # the corner radius that is most of the GAN silhouette
GROOVE_W = 0.0008             # the moulding line inset from each face's edge
GROOVE_D = 0.00018
U_TURN = math.radians(31)     # the U layer, caught mid-turn
PILLOW = 0.028

# Blender is Z-up and the exporter maps +Y to glTF -Z, so -Y here faces the viewer.
FACES = [
    ((0, 0, 1), 'white', '#f2f3f0'),
    ((0, 0, -1), 'yellow', '#f6d33c'),
    ((0, -1, 0), 'green', '#25bd5f'),
    ((0, 1, 0), 'blue', '#2a6fd6'),
    ((-1, 0, 0), 'orange', '#ff8a2b'),
    ((1, 0, 0), 'red', '#dd2f39'),
]
SLOT = {d: n + 1 for n, (d, _, _) in enumerate(FACES)}   # slot 0 is the dark interior

lib.reset()
rng = random.Random(7391)
DIRS = [d for d, _, _ in FACES]


def layer(indices):
    """Build one horizontal slice of the cube into its own bmesh, materials already assigned."""
    bm = bmesh.new()
    shown = {}
    for i, j, k in indices:
        # Which of this piece's six faces are on the outside of the whole cube, and in what
        # colour. A piece keeps one colour per exterior direction; the scramble swaps the
        # colour shown, never which faces are coloured.
        vis = {}
        for d in DIRS:
            if Vector(d).dot(Vector((i, j, k))) > 0.5:
                vis[d] = rng.choice(DIRS) if rng.random() < 0.28 else d
        shown[(i, j, k)] = vis
        ret = bmesh.ops.create_cube(bm, size=BODY,
                                    matrix=Matrix.Translation(Vector((i, j, k)) * CUBIE))
        verts = ret['verts']
        edges = [e for e in {e for v in verts for e in v.link_edges}
                 if all(x in verts for x in e.verts)]
        bmesh.ops.bevel(bm, geom=edges, offset=BEVEL, segments=2, affect='EDGES',
                        profile=0.5, clamp_overlap=True)
        # Bevel first. Insetting first leaves a groove ring only GROOVE_W wide beside each
        # original edge, and clamp_overlap then shrinks the bevel to fit it — which is how the
        # first build came out with perfectly sharp corners.
        flat = BODY / 2 - BEVEL
        outer = [f for f in bm.faces
                 if tuple(round(c) for c in f.normal) in vis
                 and tuple(int(round(v / CUBIE)) for v in f.calc_center_median()) == (i, j, k)
                 and abs(abs(f.calc_center_median().dot(Vector(
                     tuple(round(c) for c in f.normal))) - abs(Vector((i, j, k)).dot(Vector(
                         tuple(round(c) for c in f.normal))) * CUBIE)) - BODY / 2) < 1e-5
                 and f.calc_area() > flat * flat * 0.5]
        if outer:
            bmesh.ops.inset_individual(bm, faces=outer, thickness=GROOVE_W, depth=-GROOVE_D,
                                       use_even_offset=True)
    # Colour in one pass at the end, from each face's own position and normal rather than from
    # references: bevel consumes the vertices it rounds, so anything held across it is gone.
    # The bevel strips and corner patches take the dominant axis of their normal, which is what
    # makes the colour run over the rounded edge the way moulded plastic does.
    for f in bm.faces:
        c = f.calc_center_median()
        idx = tuple(int(round(v / CUBIE)) for v in c)
        vis = shown.get(idx)
        if not vis:
            continue
        n = f.normal
        axis = max(range(3), key=lambda a: abs(n[a]))
        if abs(n[axis]) < 1e-4:
            continue
        d = tuple(1 if a == axis and n[axis] > 0 else -1 if a == axis else 0 for a in range(3))
        f.material_index = SLOT[vis[d]] if d in vis else 0
    return bm


low = layer([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0)
             if not (i == 0 and j == 0 and k == 0)])
top = layer([(i, j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)])
bmesh.ops.rotate(top, verts=top.verts, cent=(0, 0, 0),
                 matrix=Matrix.Rotation(U_TURN, 3, 'Z'))

mats = [lib.material('cube_body_mat', lib.hex_rgb('#15161a'), roughness=0.68)]
for _, name, hexc in FACES:
    mats.append(lib.material(f'cube_{name}_mat', lib.hex_rgb(hexc), roughness=0.5,
                             metallic=0.0))


def to_object(bm, name):
    """
    Slots go on the mesh *before* the bmesh is written into it. `lib.set_materials` clears the
    slot list first, and clearing slots resets every polygon's material index to 0 — which
    exported the whole cube in the body colour, twice, before this was found.
    """
    me = bpy.data.meshes.new(name)
    for m in mats:
        me.materials.append(m)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


body = lib.join([to_object(low, 'speedcube'), to_object(top, 'speedcube_top')], 'speedcube')

# Pillow before recentring, so the sphere it pushes toward is the cube's own centre.
lib.pillow([body], SIZE * 0.86, PILLOW)
lib.shade_auto(body, 30)
lib.recentre([body], 'base')

print(f'  {body.name}: {lib.tri_count(body)} tris')
lib.export(OUT, [body])
lib.write_meta(OUT, {'size': SIZE})
