"""
v2_exterior_web.py -- the street outside at ~5% of the triangles.

Bakes NEW_exterior from room_public.blend (approved dusk setup) into depth-
separated backdrop cards + textures for public/assets/v2/exterior/.

Nothing in this script saves the .blend it opens; all outputs go to tmp/
(intermediates) and public/assets/v2/exterior/ (shippables) via modes.

    blender -b --factory-startup blender/scene/room_public.blend \\
        --python blender/scripts/v2_exterior_web.py -- <mode> [args]

Modes:
    bake_full <exr> <w> <h> <spp>      everything exterior, wide persp cam
    bake_near|bake_mid|bake_far ...    one layer, wide persp cam (near/mid: transparent film)
    bake_ground <exr> <spp>            top-down ortho ground card bake (opaque)
    stats <exr>                        peak/percentile stats of an EXR bake
    rgbm <exr> <out.png> <peak>        linear EXR -> RGBM (sqrt) PNG, reports clipped fraction
    alpha <exr> <out.png>              EXR alpha -> LDR grayscale PNG
    cards                              build card meshes, export assets/processed/exterior_cards.glb
    verify <single|layered> <out.png> <CAM_seat|CAM_stand> <w> <h> <spp>
                                       hide exterior, show cards w/ EXR emission, render

Device note: v2_render.py targets CUDA (RTX 5070 on the owner's machine). This
Mac has no CUDA/NVIDIA, so this script uses METAL GPU and falls back to CPU.
Same engine, same scene, same denoiser family; only the compute device differs.

Coordinate note: Blender Z-up metres. three.js Y-up: three (x, y, z) =
Blender (x, -z, y). The sidecar (written by rgbm/cards modes' printed JSON and
finalised in the report) records both.
"""

import bpy
import math
import os
import sys

# ---------------------------------------------------------------- parameters
# Bake camera: just inside the room behind the seated eye, looking +Y (out).
BAKE_POS = (-0.15, -0.8, 1.55)
BAKE_ROT = (math.pi / 2, 0.0, 0.0)          # looks +Y, horizontal
BAKE_FOV_H = math.radians(110.0)            # wide: covers single-card cyl +-52deg
BAKE_SENSOR = 36.0
BAKE_LENS = (BAKE_SENSOR / 2.0) / math.tan(BAKE_FOV_H / 2.0)   # ~12.6 mm
BAKE_CLIP = (0.5, 3000.0)

# Ortho ground camera: top-down over the visible ground rect.
GND_RECT = (-40.0, 40.0, -2.0, 62.0)        # x0, x1, y0, y1
GND_Z = -2.95
GND_W, GND_H = 2048, 1638                   # ~3.9 cm/px

# Cards: (name, kind, params). Planes face the room (-Y normal).
CARDS = {
    # horizontal ground card: manual UVs from world coords (exact, no projector)
    "GND":    {"kind": "flat", "center": (-0.0, 30.0, GND_Z), "size": (80.0, 64.0)},
    # near: young maples across the street's near side (y~10.8) + neighbours
    "NEAR":   {"kind": "plane_y", "y": 11.0, "x0": -12.0, "x1": 9.0,
               "z0": -3.0, "z1": 7.0},
    # mid: road furniture, poles+wires, house fronts (y=32), maples at y~22
    "MID":    {"kind": "plane_y", "y": 30.0, "x0": -30.0, "x1": 20.0,
               "z0": -3.2, "z1": 12.0},
    # far: backyard trees, LOD rows, terrain tail + baked sky (opaque)
    "FAR":    {"kind": "cyl", "r": 60.0, "a0": -52.0, "a1": 52.0,
               "z0": -3.0, "z1": 48.0, "seg": 64},
    # cheap option: one curved card for the whole exterior incl. sky
    "SINGLE": {"kind": "cyl", "r": 30.0, "a0": -52.0, "a1": 52.0,
               "z0": -3.2, "z1": 28.0, "seg": 64},
}
ROOM_PUBLIC = os.path.abspath("blender/scene/room_public.blend")
TMP = os.path.abspath("tmp")


# ---------------------------------------------------------------- layer sets
def _loc_y(o):
    return o.matrix_world.translation.y


def classify():
    """Split NEW_exterior meshes into passes. Returns dict pass -> [names]."""
    col = bpy.data.collections.get("NEW_exterior")
    ground, near, mid, far = [], [], [], []
    # Our own facade + the trim at the glass: the runtime keeps the real
    # wall/trim/casing, which occlude these rays exactly. Baking them would
    # paste backface siding onto the cards' window surround.
    SKIP = {"EXT_window_trim", "EXT_house_facade"}
    for o in col.all_objects:
        if o.type != 'MESH':
            continue
        n = o.name
        if n in SKIP:
            continue
        y = _loc_y(o)
        if n in ("EXT_ground_near", "EXT_road_detail", "EXT_street_asphalt",
                 "EXT_curbs_gutters"):
            ground.append(n)
        elif n == "EXT_terrain":
            ground.append(n)
            far.append(n)  # tail beyond the ortho rect, behind the houses
        elif n.startswith("EXT_house_lod_"):
            (near if y < 10 else mid if y < 45 else far).append(n)
        elif n.startswith("EXT_tree_far_") or n.startswith("EXT_tree_0") \
                or n.startswith("EXT_tree_1"):
            far.append(n)
        elif n.startswith("EXT_spruce_") or n.startswith("EXT_cedar_"):
            (mid if y < 42 else far).append(n)
        elif n.startswith("EXT_shrub_"):
            (near if y < 10 else mid).append(n)
        elif n.startswith("EXT_maple_"):
            (near if y < 14 else mid).append(n)
        elif n.startswith("EXT_house_") or n in (
                "EXT_hydro_poles", "EXT_power_lines", "EXT_car_suv",
                "EXT_car_sedan", "EXT_community_mailbox", "EXT_fire_hydrant",
                "EXT_bins", "EXT_stop_sign", "EXT_fences"):
            mid.append(n)
        elif n in ("EXT_house_facade", "EXT_house_lod_nbrL", "EXT_house_lod_nbrR"):
            near.append(n)
        else:
            mid.append(n)  # default: true depth near the mid card
            print("CLASSIFY-FALLBACK-MID", n)
    return {"ground": ground, "near": near, "mid": mid, "far": far}


PASSES = None  # filled lazily (needs the .blend open)


# ---------------------------------------------------------------- scene setup
def use_metal_or_cpu():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for cdt in ('METAL', 'NONE'):
        try:
            prefs.compute_device_type = cdt
            prefs.refresh_devices()
            break
        except Exception:
            continue
    gpu = [d for d in prefs.devices if d.type != 'CPU']
    for d in prefs.devices:
        d.use = bool(gpu) and d.type != 'CPU'
    bpy.context.scene.cycles.device = 'GPU' if gpu else 'CPU'
    print("DEVICE", [(d.name, d.type, d.use) for d in prefs.devices])


def make_bake_cam():
    sc = bpy.context.scene
    cam = bpy.data.cameras.new("BAKE_win")
    cam.sensor_width = BAKE_SENSOR
    cam.lens = BAKE_LENS
    cam.clip_start, cam.clip_end = BAKE_CLIP
    o = bpy.data.objects.new("BAKE_win", cam)
    sc.collection.objects.link(o)
    o.location = BAKE_POS
    o.rotation_euler = BAKE_ROT
    sc.camera = o
    return o


def make_ground_cam():
    sc = bpy.context.scene
    x0, x1, y0, y1 = GND_RECT
    cam = bpy.data.cameras.new("BAKE_gnd")
    cam.type = 'ORTHO'
    cam.ortho_scale = (x1 - x0)
    cam.clip_start, cam.clip_end = 1.0, 200.0
    o = bpy.data.objects.new("BAKE_gnd", cam)
    sc.collection.objects.link(o)
    o.location = ((x0 + x1) / 2, (y0 + y1) / 2, 50.0)
    o.rotation_euler = (0.0, 0.0, 0.0)  # looks -Z: straight down
    sc.camera = o
    return o


def isolate(pass_names, keep_all_lights=True):
    """Hide every mesh except the named exterior passes. Lights always stay
    (approved dusk setup); window trim at the glass is always hidden."""
    global PASSES
    keep = set()
    for p in pass_names:
        keep.update(PASSES[p])
    n_hide, n_keep = 0, 0
    for o in bpy.data.objects:
        if o.type == 'LIGHT':
            o.hide_render = False
        elif o.type == 'MESH':
            if o.name in keep:
                o.hide_render = False
                n_keep += 1
            else:
                o.hide_render = True
                n_hide += 1
    print(f"ISOLATE {pass_names}: keep {n_keep} meshes, hide {n_hide}")


def render(exr_path, w, h, spp, transparent, fmt='EXR'):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = spp
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPTIX'
    except TypeError:
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    if fmt == 'EXR':
        sc.render.image_settings.file_format = 'OPEN_EXR'
        sc.render.image_settings.color_depth = '16'
        sc.render.image_settings.exr_codec = 'ZIP'
        sc.render.image_settings.color_mode = 'RGBA'
    else:
        sc.render.image_settings.file_format = 'PNG'
        sc.render.image_settings.color_depth = '8'
        sc.render.image_settings.color_mode = 'RGB'
    sc.render.filepath = exr_path
    import time
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("RENDER_SECONDS", round(time.time() - t, 1), "->", exr_path)


# ---------------------------------------------------------------- modes
def cmd_bake(which, exr, w, h, spp):
    global PASSES
    bpy.ops.wm.open_mainfile(filepath=ROOM_PUBLIC)
    use_metal_or_cpu()
    PASSES = classify()
    for k, v in PASSES.items():
        print(f"PASSSET {k}: {len(v)} meshes")
    if which == "full":
        make_bake_cam()
        isolate(["ground", "near", "mid", "far"])
        render(exr, w, h, spp, transparent=False)
    elif which in ("near", "mid"):
        make_bake_cam()
        isolate([which])
        render(exr, w, h, spp, transparent=True)
    elif which == "far":
        make_bake_cam()
        isolate(["far"])
        render(exr, w, h, spp, transparent=False)
    elif which == "ground":
        make_ground_cam()
        isolate(["ground"])
        render(exr, GND_W, GND_H, spp, transparent=False)
    else:
        raise SystemExit("unknown bake pass " + which)


def cmd_stats(exr):
    import numpy as np
    img = bpy.data.images.load(exr)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float64).reshape(h, w, 4)
    rgb = px[..., :3]
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    a = px[..., 3]
    print(f"STATS {exr} {w}x{h}")
    print(f"  peak_rgb {rgb.max():.3f} peak_lum {lum.max():.3f}")
    for q in (50, 90, 99, 99.9):
        print(f"  lum_p{q} {np.percentile(lum, q):.4f}")
    print(f"  alpha_cov {(a > 0.01).mean():.4f} alpha_mean {a.mean():.4f}")
    bpy.data.images.remove(img)


def cmd_rgbm(exr, out, peak):
    """Linear EXR -> RGBM PNG of sqrt(L): L = (rgb*a*range)^2, range=sqrt(peak).
    Pixels above peak clip (reported)."""
    import numpy as np
    peak = float(peak)
    rng = math.sqrt(peak)
    img = bpy.data.images.load(exr)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float64).reshape(h, w, 4)
    rgb = np.clip(px[..., :3], 0, None)
    over = (rgb.max(axis=-1) > peak).mean()
    rgb = np.clip(rgb / peak, 0, 1)
    sq = np.sqrt(rgb)
    m = sq.max(axis=-1, keepdims=True)
    m = np.clip(m, 1e-6, 1.0)
    enc = np.concatenate([sq / m, np.broadcast_to(m, m.shape)], axis=-1)
    enc8 = (np.clip(enc, 0, 1) * 255 + 0.5).astype(np.uint8)
    flat = (enc8.astype(np.float32) / 255.0).ravel()
    im2 = bpy.data.images.new("rgbm", w, h, alpha=True, float_buffer=False)
    im2.colorspace_settings.name = 'Non-Color'  # file bytes = our values, no sRGB
    im2.pixels[:] = flat.tolist()
    im2.file_format = 'PNG'
    im2.filepath_raw = out
    im2.save()
    print(f"RGBM {out} {w}x{h} range_sqrt={rng:.4f} clipped_frac={over:.5f}")
    bpy.data.images.remove(img)
    bpy.data.images.remove(im2)


def cmd_alpha(exr, out):
    import numpy as np
    img = bpy.data.images.load(exr)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float64).reshape(h, w, 4)
    a = np.clip(px[..., 3], 0, 1)
    rgba = np.stack([a, a, a, np.ones_like(a)], axis=-1)
    im2 = bpy.data.images.new("alpha", w, h, alpha=True, float_buffer=False)
    im2.colorspace_settings.name = 'Non-Color'
    im2.pixels[:] = (rgba.ravel()).tolist()
    im2.file_format = 'PNG'
    im2.filepath_raw = out
    im2.save()
    print(f"ALPHA {out} {w}x{h} coverage={(a > 0.5).mean():.4f}")
    bpy.data.images.remove(img)
    bpy.data.images.remove(im2)


def build_cards():
    """Create card meshes with camera-project UVs. Returns {name: object}."""
    sc = bpy.context.scene
    if "BAKE_win" not in bpy.data.objects:
        make_bake_cam()
    cam = bpy.data.objects["BAKE_win"]
    cards = {}
    for name, c in CARDS.items():
        if c["kind"] == "flat":
            cx, cy, cz = c["center"]
            sx, sy = c["size"]
            bpy.ops.mesh.primitive_plane_add(size=2.0, location=(cx, cy, cz))
            o = bpy.context.active_object
            o.name = "CARD_" + name
            o.scale = (sx / 2.0, sy / 2.0, 1.0)
            bpy.ops.object.transform_apply(scale=True)
            # manual UVs from world coords (exact for the ortho bake).
            # NOTE: co is local; world = local + object location.
            import numpy as np
            x0, x1, y0, y1 = GND_RECT
            me = o.data
            uv = me.uv_layers.new(name="UVMap")
            for poly in me.polygons:
                for li in poly.loop_indices:
                    co = me.vertices[me.loops[li].vertex_index].co
                    wx, wy = co.x + cx, co.y + cy
                    uv.data[li].uv = ((wx - x0) / (x1 - x0),
                                      (wy - y0) / (y1 - y0))
        elif c["kind"] == "plane_y":
            cx = (c["x0"] + c["x1"]) / 2
            cz = (c["z0"] + c["z1"]) / 2
            bpy.ops.mesh.primitive_plane_add(
                size=1.0, location=(cx, c["y"], cz),
                rotation=(math.pi / 2, 0.0, 0.0))
            o = bpy.context.active_object
            o.name = "CARD_" + name
            o.scale = (c["x1"] - c["x0"], c["z1"] - c["z0"], 1.0)
            bpy.ops.object.transform_apply(scale=True)
            mod = o.modifiers.new("UVProj", 'UV_PROJECT')
            mod.projectors[0].object = cam
            bpy.ops.object.modifier_apply(modifier=mod.name)
        elif c["kind"] == "cyl":
            cx, cy = BAKE_POS[0], BAKE_POS[1]
            a0, a1 = math.radians(c["a0"]), math.radians(c["a1"])
            n = c["seg"]
            import bmesh
            me = bpy.data.meshes.new("CARD_" + name)
            bm = bmesh.new()
            verts_top, verts_bot = [], []
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                dx, dy = math.sin(a) * c["r"], math.cos(a) * c["r"]
                verts_bot.append(bm.verts.new((cx + dx, cy + dy, c["z0"])))
                verts_top.append(bm.verts.new((cx + dx, cy + dy, c["z1"])))
            for i in range(n):
                b0, b1 = verts_bot[i], verts_bot[i + 1]
                t0, t1 = verts_top[i], verts_top[i + 1]
                try:
                    bm.faces.new((b0, b1, t1, t0))
                except ValueError:
                    pass
            bm.to_mesh(me)
            bm.free()
            o = bpy.data.objects.new("CARD_" + name, me)
            sc.collection.objects.link(o)
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            mod = o.modifiers.new("UVProj", 'UV_PROJECT')
            mod.projectors[0].object = cam
            bpy.ops.object.modifier_apply(modifier=mod.name)
        # placeholder material (assembly replaces with RGBM-decoding unlit)
        m = bpy.data.materials.new("CARDMAT_" + name)
        m.use_nodes = True
        o.data.materials.append(m)
        cards[name] = o
        tris = len(o.data.polygons)
        print(f"CARD {name}: {tris} tris at {tuple(round(v, 2) for v in o.location)}")
    return cards


def cmd_cards():
    bpy.ops.wm.open_mainfile(filepath=ROOM_PUBLIC)
    cards = build_cards()
    out = os.path.abspath("assets/processed/exterior_cards.glb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in cards.values():
        o.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=out, export_format='GLB', use_selection=True,
        export_materials='EXPORT', export_cameras=False, export_lights=False)
    print("EXPORTED", out, os.path.getsize(out), "bytes")
    total = sum(len(o.data.polygons) for o in cards.values())
    print("CARDS_TRIS", total)


def shade_cards_with(exr_by_card):
    """Emission materials sampling EXRs as linear (verification only)."""
    for name, exr in exr_by_card.items():
        o = bpy.data.objects.get("CARD_" + name)
        img = bpy.data.images.load(os.path.abspath(exr))
        img.colorspace_settings.name = 'Non-Color'
        m = o.data.materials[0]
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        em = nt.nodes.new('ShaderNodeEmission')
        tx = nt.nodes.new('ShaderNodeTexImage')
        tx.image = img
        if name in ("NEAR", "MID"):
            # real transparency: Emission + Transparent mixed by EXR alpha
            transp = nt.nodes.new('ShaderNodeBsdfTransparent')
            mx = nt.nodes.new('ShaderNodeMixShader')
            nt.links.new(tx.outputs['Color'], em.inputs['Color'])
            nt.links.new(transp.outputs['BSDF'], mx.inputs[1])
            nt.links.new(em.outputs['Emission'], mx.inputs[2])
            nt.links.new(tx.outputs['Alpha'], mx.inputs['Fac'])
            nt.links.new(mx.outputs['Shader'], out.inputs['Surface'])
        else:
            nt.links.new(tx.outputs['Color'], em.inputs['Color'])
            nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
        em.inputs['Strength'].default_value = 1.0


def cmd_verify(which, out, cam, w, h, spp):
    global PASSES
    bpy.ops.wm.open_mainfile(filepath=ROOM_PUBLIC)
    use_metal_or_cpu()
    PASSES = classify()
    cards = build_cards()
    sc = bpy.context.scene
    # hide ONLY the baked exterior (keep room, trim, curtains, glass as in refs)
    ext = bpy.data.collections.get("NEW_exterior")
    ext_names = {o.name for o in ext.all_objects}
    if which == "single":
        for o in bpy.data.objects:
            if o.name in ext_names and o.name != "EXT_window_trim":
                o.hide_render = True
        for name in ("GND", "NEAR", "MID", "FAR"):
            bpy.data.objects["CARD_" + name].hide_render = True
        shade_cards_with({"SINGLE": os.path.join(TMP, "bake_full.exr")})
    elif which == "layered":
        for o in bpy.data.objects:
            if o.name in ext_names and o.name != "EXT_window_trim":
                o.hide_render = True
        bpy.data.objects["CARD_SINGLE"].hide_render = True
        shade_cards_with({
            "GND": os.path.join(TMP, "bake_ground.exr"),
            "NEAR": os.path.join(TMP, "bake_near.exr"),
            "MID": os.path.join(TMP, "bake_mid.exr"),
            "FAR": os.path.join(TMP, "bake_far.exr"),
        })
    else:
        raise SystemExit("verify needs single|layered")
    sc.camera = bpy.data.objects[cam]
    sc.render.film_transparent = False
    render(out, w, h, spp, transparent=False, fmt='PNG')


def main():
    a = sys.argv[sys.argv.index('--') + 1:]
    mode = a[0]
    if mode.startswith("bake_"):
        cmd_bake(mode[5:], a[1], int(a[2]), int(a[3]), int(a[4]))
    elif mode == "stats":
        bpy.ops.wm.open_mainfile(filepath=ROOM_PUBLIC)
        cmd_stats(os.path.abspath(a[1]))
    elif mode == "rgbm":
        bpy.ops.wm.open_mainfile(filepath=ROOM_PUBLIC)
        cmd_rgbm(os.path.abspath(a[1]), os.path.abspath(a[2]), a[3])
    elif mode == "alpha":
        bpy.ops.wm.open_mainfile(filepath=ROOM_PUBLIC)
        cmd_alpha(os.path.abspath(a[1]), os.path.abspath(a[2]))
    elif mode == "cards":
        cmd_cards()
    elif mode == "verify":
        cmd_verify(a[1], os.path.abspath(a[2]), a[3],
                   int(a[4]), int(a[5]), int(a[6]))
    else:
        raise SystemExit("unknown mode " + mode)


main()
