"""
v2_exterior_web.py -- the street outside the window as two baked panorama cards.

The exterior (`NEW_exterior`, ~390k tris) is seen through one window from two eye
positions ~1.4 m apart. Instead of shipping geometry, each depth layer is rendered
by Cycles, in the approved dusk setup, as an equirectangular panorama from ONE bake
eye (midpoint of the seated and standing eyes). At runtime every layer is a handful
of triangles placed at that layer's real depth; the fragment shader projects the
fragment's world position back to the bake eye and looks the panorama up. A surface
point that really lies on the proxy is therefore exact from any viewpoint; content
off the proxy shows parallax error proportional to its depth spread.

    back   opaque  ground plane z=GROUND_Z up to the house fronts, then a vertical wall
                   y=Y_BACK: road, lawns, the houses across the street, hedges, fences,
                   the parked SUV, back-row trees, terrain, sky.
    front  alpha   vertical plane y=Y_FRONT: hydro poles, wires, street maples, the
                   sedan, hydrant, mailbox, bins, stop sign, the young maples in front.

Two cards, not more: the site must run on low-end GPUs and every card is a full-window
fragment layer (owner, 2026-10-01). The four-layer variant (far/mid/street/near) measured
in the report was only ~1 mean code closer to the reference.

Lighting stays exactly as approved: nothing is deleted. Objects outside a layer are
made camera-invisible (they still cast shadows and bounce light), the ground is a
holdout in the alpha layers (cuts below-grade parts), and the room is camera-invisible.

The glass (Mesh_11) is camera-invisible while baking: the layers hold the street itself.
The approved stills see it through that single-sided IOR 1.5 plane, which magnifies it
~1.5x; the runtime reproduces that refraction in its shader (sidecar `glass`).

Only reads room.blend (never saves it). Intermediates go to tmp/exterior/, shippables
to public/assets/v2/exterior/ (via scripts/encode-exterior.mjs for the WebP step).

    blender -b <room.blend> --python blender/scripts/v2_exterior_web.py -- <mode> [args]
    (on the Windows machine: through C:/Users/Vas/Documents/Github/blender-locked.sh)

Full rebuild: layer far|mid|street|near 256, encode (no .blend needed: -b --factory-startup),
then `node scripts/encode-exterior.mjs`.

Modes:
    ref <CAM> <out.png> <w> <h> <spp> [seed]  full-geometry Cycles still (the reference)
    layer <far|mid|street|near> <spp> [ppd]   bake one panorama layer -> tmp/exterior/<layer>.exr
    encode                                    EXRs -> tmp/exterior/<layer>.png (log-encoded,
                                              see LOG_*), + layers.json (ranges, stats)
    verify <CAM> <out.png> <w> <h> <spp>      exterior camera-invisible, proxies shaded with
                                              the ENCODED PNGs (decoded in nodes), render
    list                                      print the layer classification + coverage
  CAM may be `EYE@<CAM>` (that camera moved to the bake eye: zero parallax, isolates
  resampling error). EXT_NO_GLASS=1 hides the glass in ref/verify (diagnostic).

Coordinates: Blender Z-up metres. glTF/three.js Y-up: three (x, y, z) = Blender (x, z, -y).
"""

import bpy
import json
import math
import os
import sys
import time

# ---------------------------------------------------------------- parameters
SEAT = (0.0, -0.16, 1.175)
STAND = (1.06, -0.96, 1.63)
EYE = tuple((a + b) / 2 for a, b in zip(SEAT, STAND))   # bake eye: midpoint

# Window aperture (glass, Mesh_11): x, z extents at y = GLASS_Y.
GLASS_Y = 1.398
GLASS_X = (-1.275, 0.975)
GLASS_Z = (0.745, 2.455)

GROUND_Z = -3.05
Y_BACK = 26.5         # back wall: the house fronts across the street (25.5-26)
WALL_TOP = 80.0       # back wall top z
Y_FRONT = float(os.environ.get("EXT_Y_FRONT", "20.0"))   # front card plane (swept 14/17/20: 20 best)
PLANE_Z = (-12.0, 40.0)   # vertical planes extend below grade: layers draw painter-style
PLANE_X = (-200.0, 200.0)

PPD = {"back": 16.0, "front": 18.0}   # pixels per degree
MARGIN_DEG = 3.0

# Log encoding of linear radiance into 8 bits per channel:
#   v = (log2(L) - LOG_MIN) / (LOG_MAX - LOG_MIN),  L = 2^(LOG_MIN + v*(LOG_MAX-LOG_MIN))
# with v == 0 meaning L = 0 (black). Alpha is straight coverage.
LOG_MIN, LOG_MAX = -12.0, 6.0

ROOT = os.path.abspath(".")
TMP = os.path.join(ROOT, "tmp", "exterior")
OUT = os.path.join(ROOT, "public", "assets", "v2", "exterior")

GROUND = {"EXT_ground_near", "EXT_street_asphalt", "EXT_curbs_gutters",
          "EXT_road_detail", "EXT_terrain"}
# Our own house: the runtime keeps the real wall/casing/frame. Neither is seen in
# the window's view cone except as the reveal, which the room shell already models.
SKIP = {"EXT_house_facade", "EXT_window_trim"}
FORCE_MID = {"EXT_fences"}
FORCE_STREET = {"EXT_power_lines", "EXT_hydro_poles"}
LAYERS = ("back", "front")   # back to front
MEMBERS = {"back": ("ground", "far", "mid"), "front": ("street", "near")}


# ---------------------------------------------------------------- helpers
def ext_objects():
    """Exterior meshes, resolved by a name snapshot. Iterating `all_objects` while setting
    visibility invalidates its cache mid-loop (items skipped, then None)."""
    names = [o.name for o in bpy.data.collections["NEW_exterior"].all_objects]
    return [o for o in (bpy.data.objects.get(n) for n in names) if o is not None and o.type == 'MESH']


def world_center(o):
    from mathutils import Vector
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [sum(v[i] for v in bb) / 8 for i in range(3)]


def classify():
    out = {"ground": [], "near": [], "street": [], "mid": [], "far": [], "skip": []}
    for o in ext_objects():
        n = o.name
        if n in SKIP:
            out["skip"].append(n)
        elif n in GROUND:
            out["ground"].append(n)
        elif n in FORCE_MID:
            out["mid"].append(n)
        elif n in FORCE_STREET:
            out["street"].append(n)
        else:
            y = world_center(o)[1]
            out["near" if y < 16 else "street" if y < 24.5 else "mid" if y < 46 else "far"].append(n)
    return out


def use_cuda():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = (d.type == 'CUDA')
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'GPU'
    print("DEVICES", [(d.name, d.type, d.use) for d in prefs.devices])


def render(path, w, h, spp, fmt, transparent=False):
    sc = bpy.context.scene
    sc.cycles.samples = spp
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPTIX'
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    s = sc.render.image_settings
    if fmt == 'EXR':
        s.file_format = 'OPEN_EXR'
        s.color_depth = '32'
        s.exr_codec = 'ZIP'
        s.color_mode = 'RGBA'
    else:
        s.file_format = 'PNG'
        s.color_depth = '8'
        s.color_mode = 'RGB'
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("RENDER_SECONDS", round(time.time() - t, 1), w, "x", h, spp, "spp ->", path)


# ---------------------------------------------------------------- proxy geometry
def proxy_hit(layer, o, d):
    """Intersect ray o + t d (t > 0) with the layer's proxy; returns point or None."""
    if layer == "back":
        if d[2] < -1e-6:
            t = (GROUND_Z - o[2]) / d[2]
            p = [o[i] + t * d[i] for i in range(3)]
            if p[1] <= Y_BACK:
                return p
        y = Y_BACK
    else:
        y = Y_FRONT
    if d[1] <= 1e-6:
        return None
    t = (y - o[1]) / d[1]
    return [o[i] + t * d[i] for i in range(3)]


def az_el(p):
    d = [p[i] - EYE[i] for i in range(3)]
    n = math.sqrt(sum(v * v for v in d))
    return math.degrees(math.atan2(d[0], d[1])), math.degrees(math.asin(d[2] / n))


def coverage(layer):
    """Azimuth/elevation range (deg, from EYE) of every proxy point visible through the
    glass from any eye on the seat->stand segment, plus margin."""
    azs, els = [], []
    for k in range(6):
        f = k / 5
        e = [SEAT[i] + f * (STAND[i] - SEAT[i]) for i in range(3)]
        for i in range(13):
            for j in range(13):
                g = (GLASS_X[0] + (GLASS_X[1] - GLASS_X[0]) * i / 12, GLASS_Y,
                     GLASS_Z[0] + (GLASS_Z[1] - GLASS_Z[0]) * j / 12)
                d = [g[q] - e[q] for q in range(3)]
                p = proxy_hit(layer, e, d)
                if p is None:
                    continue
                a, el = az_el(p)
                azs.append(a)
                els.append(el)
    m = MARGIN_DEG
    return (min(azs) - m, max(azs) + m, min(els) - m, max(els) + m)


# ---------------------------------------------------------------- scene prep
def all_room_meshes(ext_names):
    return [o for o in bpy.data.objects
            if o.type in ('MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'VOLUME', 'POINTCLOUD')
            and o.name not in ext_names]


def prep_layer(layer, cls):
    ext_names = set(sum(cls.values(), []))
    for o in all_room_meshes(ext_names):
        o.visible_camera = False
    keep = set(sum((cls[k] for k in MEMBERS[layer]), []))
    for o in ext_objects():
        if o.name in keep:
            o.visible_camera = True
            o.is_holdout = False
        elif layer == "front" and o.name in cls["ground"]:
            o.visible_camera = True
            o.is_holdout = True
        else:
            o.visible_camera = False
    vis = [o.name for o in ext_objects() if o.visible_camera and not o.is_holdout]
    print("PREP", layer, "camera-visible exterior meshes:", len(vis), "holdout:",
          sum(1 for o in ext_objects() if o.is_holdout))
    # the volume (fx_room_volume) would fog the camera rays inside the room
    for o in bpy.data.objects:
        if o.name.startswith("fx_room_volume"):
            o.hide_render = True


def make_pano_cam(rng):
    a0, a1, e0, e1 = rng
    cam = bpy.data.cameras.new("BAKE_pano")
    cam.type = 'PANO'
    cam.panorama_type = 'EQUIRECTANGULAR'
    cam.longitude_min, cam.longitude_max = math.radians(a0), math.radians(a1)
    cam.latitude_min, cam.latitude_max = math.radians(e0), math.radians(e1)
    cam.clip_start, cam.clip_end = 0.05, 5000.0
    o = bpy.data.objects.new("BAKE_pano", cam)
    bpy.context.scene.collection.objects.link(o)
    o.location = EYE
    o.rotation_euler = (math.pi / 2, 0.0, 0.0)   # looks +Y, right = +X, up = +Z
    bpy.context.scene.camera = o
    return o


# ---------------------------------------------------------------- modes
def get_cam(name):
    """A scene camera, or `EYE@<CAM>`: that camera's lens/orientation moved to the bake eye
    (zero parallax by construction: isolates resampling/edge error from parallax error)."""
    if not name.startswith("EYE@"):
        return bpy.data.objects[name]
    src = bpy.data.objects[name[4:]]
    o = bpy.data.objects.new(name, src.data)
    bpy.context.scene.collection.objects.link(o)
    o.location = EYE
    o.rotation_euler = src.rotation_euler
    return o


def cmd_ref(cam, out, w, h, spp, seed=None):
    use_cuda()
    if seed is not None:   # noise floor: the same frame with another sampling seed
        bpy.context.scene.cycles.seed = seed
    if os.environ.get("EXT_NO_GLASS"):   # diagnostic: the window without its glass plane
        bpy.data.objects["Mesh_11"].hide_render = True
        print("NO_GLASS")
    bpy.context.scene.camera = get_cam(cam)
    render(out, w, h, spp, 'PNG')


def cmd_layer(layer, spp, ppd):
    use_cuda()
    cls = classify()
    prep_layer(layer, cls)
    rng = coverage(layer)
    w = int(round((rng[1] - rng[0]) * ppd))
    h = int(round((rng[3] - rng[2]) * ppd))
    make_pano_cam(rng)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, f"{layer}.exr")
    print("LAYER", layer, "range", [round(v, 2) for v in rng], "size", w, h)
    render(out, w, h, spp, 'EXR', transparent=(layer == "front"))
    import hashlib
    src = bpy.data.filepath
    with open(src, "rb") as fh:
        sha = hashlib.sha1(fh.read()).hexdigest()[:12]
    sc = bpy.context.scene
    vs = sc.view_settings
    if layer == "back":
        proxy = {"type": "ground+wall", "ground_z": GROUND_Z, "wall_y": Y_BACK,
                 "x": list(PLANE_X), "top_z": WALL_TOP}
    else:
        proxy = {"type": "plane_y", "y": Y_FRONT, "x": list(PLANE_X), "z": list(PLANE_Z)}
    with open(os.path.join(TMP, f"{layer}.range.json"), "w") as f:
        json.dump({"layer": layer, "lon": [rng[0], rng[1]], "lat": [rng[2], rng[3]],
                   "size": [w, h], "spp": spp, "ppd": ppd, "proxy": proxy,
                   "objects": sorted(sum((cls[k] for k in MEMBERS[layer]), [])),
                   "eye_blender": list(EYE),
                   "poses_blender": {"seat": list(SEAT), "stand": list(STAND)},
                   "source": {"file": "blender/scene/room.blend", "sha1_12": sha},
                   "render": {"engine": "CYCLES", "device": "CUDA", "denoiser": "OPTIX",
                              "samples": spp, "film_transparent": layer == "front",
                              "view_transform": vs.view_transform, "look": vs.look,
                              "exposure_ev": round(vs.exposure, 4),
                              "note": "data is pre-view-transform linear; exposure/look not baked in"}},
                  f, indent=1)


def load_px(path):
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4), w, h   # rows bottom-first


def cmd_encode():
    """EXR (premultiplied linear) -> straight-alpha log-encoded 8-bit PNG (rows bottom-
    first as Blender stores them; the saved PNG is top-first like any image)."""
    import numpy as np
    meta = {}
    for layer in LAYERS:
        exr = os.path.join(TMP, f"{layer}.exr")
        if not os.path.exists(exr):
            continue
        px, w, h = load_px(exr)
        with open(os.path.join(TMP, f"{layer}.range.json")) as f:
            r = json.load(f)
        if layer == "front":
            # crop the alpha layers to their content (+4 px), keeping the angular mapping
            on = px[..., 3] > 2e-3
            rows, cols = np.nonzero(on.any(axis=1))[0], np.nonzero(on.any(axis=0))[0]
            r0, r1 = max(0, rows[0] - 4), min(h, rows[-1] + 5)
            c0, c1 = max(0, cols[0] - 4), min(w, cols[-1] + 5)
            lo0, lo1 = r["lon"]
            la0, la1 = r["lat"]
            r["lon"] = [lo0 + (lo1 - lo0) * c0 / w, lo0 + (lo1 - lo0) * c1 / w]
            r["lat"] = [la0 + (la1 - la0) * r0 / h, la0 + (la1 - la0) * r1 / h]
            px = np.ascontiguousarray(px[r0:r1, c0:c1])
            r["crop_from"] = [w, h]
            h, w = px.shape[:2]
            r["size"] = [w, h]
        a = np.clip(px[..., 3], 0.0, 1.0)
        rgb = np.clip(px[..., :3], 0.0, None)
        if layer == "back":
            a = np.ones_like(a)
        else:
            # un-premultiply; hide fringe where coverage is negligible
            rgb = np.where(a[..., None] > 1e-3, rgb / np.maximum(a[..., None], 1e-3), 0.0)
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        cov = a > 0.5
        st = {"peak": float(rgb.max()),
              "p50": float(np.percentile(lum[cov], 50)) if cov.any() else 0.0,
              "p01": float(np.percentile(lum[cov], 1)) if cov.any() else 0.0,
              "p999": float(np.percentile(lum[cov], 99.9)) if cov.any() else 0.0,
              "coverage": float(cov.mean())}
        lo = 2.0 ** LOG_MIN
        st["below_min_frac"] = float(((rgb < lo) & (rgb > 0)).mean())
        st["above_max_frac"] = float((rgb > 2.0 ** LOG_MAX).mean())
        v = (np.log2(np.maximum(rgb, lo)) - LOG_MIN) / (LOG_MAX - LOG_MIN)
        v = np.where(rgb <= 0, 0.0, np.clip(v, 1.0 / 255.0, 1.0))
        if layer == "front":
            # Bleed colour into the transparent texels (log domain), so bilinear filtering at
            # a coverage edge mixes in the neighbour's colour rather than black.
            filled = a > 0.02
            for _ in range(8):
                vv = np.pad(v * filled[..., None], ((1, 1), (1, 1), (0, 0)))
                ww = np.pad(filled.astype(np.float32), 1)
                s = sum(vv[1 + dy:vv.shape[0] - 1 + dy, 1 + dx:vv.shape[1] - 1 + dx]
                        for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                c = sum(ww[1 + dy:ww.shape[0] - 1 + dy, 1 + dx:ww.shape[1] - 1 + dx]
                        for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                new = (~filled) & (c > 0)
                v[new] = s[new] / c[new][:, None]
                filled |= new
            v[~filled] = 0.0
        # 1-LSB random dither before quantising (breaks sky banding)
        rs = np.random.RandomState(7)
        v = v + (rs.random_sample(v.shape[:2])[..., None] - 0.5) / 255.0
        enc = np.concatenate([np.clip(v, 0, 1), a[..., None]], axis=-1).astype(np.float32)
        im = bpy.data.images.new(f"enc_{layer}", w, h, alpha=True, float_buffer=False)
        im.colorspace_settings.name = 'Non-Color'
        im.alpha_mode = 'STRAIGHT'
        im.pixels.foreach_set(enc.ravel())
        out = os.path.join(TMP, f"{layer}.png")
        im.filepath_raw = out
        im.file_format = 'PNG'
        im.save()
        bpy.data.images.remove(im)
        r["stats"] = st
        meta[layer] = r
        print("ENCODED", layer, w, h, st)
    with open(os.path.join(TMP, "layers.json"), "w") as f:
        json.dump(meta, f, indent=1)


# ---------------------------------------------------------------- verification
def proxy_mesh(layer):
    import bmesh
    me = bpy.data.meshes.new("PROXY_" + layer)
    bm = bmesh.new()
    x0, x1 = PLANE_X
    if layer == "back":
        quads = [((x0, GLASS_Y, GROUND_Z), (x1, GLASS_Y, GROUND_Z), (x1, Y_BACK, GROUND_Z), (x0, Y_BACK, GROUND_Z)),
                 ((x0, Y_BACK, GROUND_Z), (x1, Y_BACK, GROUND_Z), (x1, Y_BACK, WALL_TOP), (x0, Y_BACK, WALL_TOP))]
    else:
        y = Y_FRONT
        quads = [((x0, y, PLANE_Z[0]), (x1, y, PLANE_Z[0]), (x1, y, PLANE_Z[1]), (x0, y, PLANE_Z[1]))]
    for q in quads:
        bm.faces.new([bm.verts.new(v) for v in q])
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("PROXY_" + layer, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def proxy_material(layer, rng):
    """Emission = decode(png sampled at the equirect coords of (P - EYE)); mirrors the
    runtime shader exactly, including the 8-bit log decode."""
    m = bpy.data.materials.new("PROXYMAT_" + layer)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new
    geo = N('ShaderNodeNewGeometry')
    sub = N('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
    sub.inputs[1].default_value = EYE
    L(geo.outputs['Position'], sub.inputs[0])
    nrm = N('ShaderNodeVectorMath'); nrm.operation = 'NORMALIZE'
    L(sub.outputs[0], nrm.inputs[0])
    sep = N('ShaderNodeSeparateXYZ')
    L(nrm.outputs[0], sep.inputs[0])
    az = N('ShaderNodeMath'); az.operation = 'ARCTAN2'
    L(sep.outputs['X'], az.inputs[0]); L(sep.outputs['Y'], az.inputs[1])
    el = N('ShaderNodeMath'); el.operation = 'ARCSINE'
    L(sep.outputs['Z'], el.inputs[0])
    a0, a1, e0, e1 = [math.radians(v) for v in rng]

    def affine(src, lo, hi):
        s = N('ShaderNodeMath'); s.operation = 'MULTIPLY_ADD'
        L(src.outputs[0], s.inputs[0])
        s.inputs[1].default_value = 1.0 / (hi - lo)
        s.inputs[2].default_value = -lo / (hi - lo)
        return s
    u, v = affine(az, a0, a1), affine(el, e0, e1)
    comb = N('ShaderNodeCombineXYZ')
    L(u.outputs[0], comb.inputs['X']); L(v.outputs[0], comb.inputs['Y'])
    tex = N('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(os.path.join(TMP, f"{layer}.png"))
    tex.image.colorspace_settings.name = 'Non-Color'
    tex.image.alpha_mode = 'CHANNEL_PACKED'
    tex.interpolation = 'Linear'
    tex.extension = 'CLIP'
    L(comb.outputs[0], tex.inputs['Vector'])
    # decode: L = v > 0 ? 2^(LOG_MIN + v*(LOG_MAX-LOG_MIN)) : 0   (per channel)
    sepc = N('ShaderNodeSeparateColor')
    L(tex.outputs['Color'], sepc.inputs[0])
    comb2 = N('ShaderNodeCombineColor')
    for ch in ('Red', 'Green', 'Blue'):
        ma = N('ShaderNodeMath'); ma.operation = 'MULTIPLY_ADD'
        L(sepc.outputs[ch], ma.inputs[0])
        ma.inputs[1].default_value = LOG_MAX - LOG_MIN
        ma.inputs[2].default_value = LOG_MIN
        pw = N('ShaderNodeMath'); pw.operation = 'POWER'
        pw.inputs[0].default_value = 2.0
        L(ma.outputs[0], pw.inputs[1])
        gt = N('ShaderNodeMath'); gt.operation = 'GREATER_THAN'
        L(sepc.outputs[ch], gt.inputs[0]); gt.inputs[1].default_value = 0.5 / 255.0
        mu = N('ShaderNodeMath'); mu.operation = 'MULTIPLY'
        L(pw.outputs[0], mu.inputs[0]); L(gt.outputs[0], mu.inputs[1])
        L(mu.outputs[0], comb2.inputs[ch])
    em = N('ShaderNodeEmission')
    L(comb2.outputs[0], em.inputs['Color'])
    em.inputs['Strength'].default_value = 1.0
    out = N('ShaderNodeOutputMaterial')
    if layer == "back":
        L(em.outputs[0], out.inputs['Surface'])
    else:
        tr = N('ShaderNodeBsdfTransparent')
        mix = N('ShaderNodeMixShader')
        L(tex.outputs['Alpha'], mix.inputs['Fac'])
        L(tr.outputs[0], mix.inputs[1]); L(em.outputs[0], mix.inputs[2])
        L(mix.outputs[0], out.inputs['Surface'])
    return m


def cmd_verify(cam, out, w, h, spp):
    use_cuda()
    if os.environ.get("EXT_NO_GLASS"):
        bpy.data.objects["Mesh_11"].hide_render = True
        print("NO_GLASS")
    meta = json.load(open(os.path.join(TMP, "layers.json")))
    for o in ext_objects():
        o.visible_camera = False
        o.visible_transmission = False
    for layer in LAYERS:
        if layer not in meta:
            continue
        r = meta[layer]
        o = proxy_mesh(layer)
        o.data.materials.append(proxy_material(layer, (r["lon"][0], r["lon"][1], r["lat"][0], r["lat"][1])))
        # seen by camera rays and through the glass only; lights nothing, shadows nothing
        o.visible_diffuse = False
        o.visible_glossy = False
        o.visible_shadow = False
        o.visible_volume_scatter = False
    bpy.context.scene.camera = get_cam(cam)
    render(out, w, h, spp, 'PNG')


def main():
    a = sys.argv[sys.argv.index('--') + 1:]
    mode = a[0]
    if mode == "ref":
        cmd_ref(a[1], os.path.abspath(a[2]), int(a[3]), int(a[4]), int(a[5]),
                int(a[6]) if len(a) > 6 else None)
    elif mode == "layer":
        cmd_layer(a[1], int(a[2]), float(a[3]) if len(a) > 3 else PPD[a[1]])
    elif mode == "encode":
        cmd_encode()
    elif mode == "verify":
        cmd_verify(a[1], os.path.abspath(a[2]), int(a[3]), int(a[4]), int(a[5]))
    elif mode == "list":
        cls = classify()
        for k, v in cls.items():
            print("CLASS", k, len(v), sorted(v))
        for layer in LAYERS:
            print("COVER", layer, [round(x, 1) for x in coverage(layer)])
    else:
        raise SystemExit("unknown mode " + mode)


main()
