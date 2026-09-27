"""
Lightmap bake for the portfolio room (ws/bake).

Turnkey script for the bake machine: assembles the whole room from the
existing sources at the room's real world positions, sets up one lighting
state from `src/scene/lighting.ts` keyframes, and bakes indirect bounce +
ambient occlusion per object group into EXR (float) + tone-safe PNG, plus a
manifest.json.

Headless, re-runnable from scratch:
    ~/.local/bin/blender --background --factory-startup \\
        --python blender/scripts/bake_lighting.py -- \\
        <state> <outDir> [--samples N] [--res N] [--only group] [--help]

    state:  day | golden | evening | night | neutral | all
    outDir: e.g. public/assets/lightmaps  (smoke test: tmp/bake-smoke)

Examples:
    # Smoke test only (do NOT run a full bake on this machine):
    ~/.local/bin/blender --background --factory-startup \\
        --python blender/scripts/bake_lighting.py -- neutral tmp/bake-smoke \\
        --samples 32 --res 256 --only mug

    # Bake machine, one state at production quality:
    ~/.local/bin/blender --background --factory-startup \\
        --python blender/scripts/bake_lighting.py -- day public/assets/lightmaps \\
        --samples 256 --res 1024

What it does:
  1. Imports every group GLB from assets/processed/ (the authoritative build
     outputs of blender/scripts/build_*.py) and instances it at the runtime
     transform read from src/scene/layout.ts + src/scene/desk.ts +
     src/scene/room.ts + src/scene/bookshelf.ts + src/data/projects.ts.
     Trim (build_furniture.py) is already in world coords. Everything else is
     placed with the three->Blender map (x, y, z)_three -> (x, -z, y)_blender
     because the glTF exporter maps Blender (x,y,z) to Y-up (x,z,-y).
  2. Rebuilds the procedural room shell (floor disc, wall slabs around the
     window opening, side walls) from ROOM dims in layout.ts, so occlusion and
     bounce match the runtime. Floor/wall materials are plain diffuse; they
     are occluders/bouncers, not bake targets.
  3. Sets up lights for <state> from LIGHT_STATES below, copied VERBATIM from
     the KEYS rows in src/scene/lighting.ts (hours 13, 18.5, 20, 21.5).
     `neutral` is a lights-neutral AO/bounce baseline (uniform white world,
     all lamps off). See UNIT MAPPING below for renderer-unit translation.
  4. For each baked group: activates the reserved `Lightmap` UV channel,
     repacks it with margin (lightmap_pack), creates one float image per
     group, wires an image node into every material, bakes DIFFUSE with
     direct OFF / indirect ON / color OFF (see BAKE TYPE below), denoises,
     saves EXR + PNG, and appends manifest.json.

BAKE TYPE: DIFFUSE indirect-only (not COMBINED with direct off).
  Direct sun/lamp/monitor stay real-time in the runtime, so they must NOT be
  in the lightmap or they would double up. COMBINED-without-direct would also
  capture glossy indirect, which the runtime's PBR already integrates per
  pixel -- baking it would double-count speculars. DIFFUSE indirect-only is
  exactly Lambertian bounce + shadowing (AO emerges naturally from the ray
  trace), which is the term the runtime will multiply in later. Denoised.

UNIT MAPPING (renderer translation, NOT invented light):
  The keyframe numbers (intensities, colors, angles, sizes, positions) are
  verbatim. What cannot transfer 1:1 is absolute units: three.js intensities
  are tuned with exposure 0.47-1.0 and custom shaders (disk lamp falloff,
  LTC rects), while Blender 5 Cycles wants watts/steradians. So each light
  type gets ONE global gain, identical for every state (recorded in the
  manifest): state-to-state RATIOS -- the thing the bake is for -- are
  preserved exactly. Gains were picked so the neutral smoke lands mid-range;
  the runtime integration pass will gain-match anyway (EXR is linear float).

GROUPS: one bake image per GLB group (the builders already join each group
  into 1 mesh with N materials, so the "atlas" is that mesh's Lightmap UV
  repacked into one tile). Code-built props (polyhedron rods, notebooks,
  devBoard ledger, partsCrate contents) have no Blender source and are
  excluded -- they keep real-time lighting. Books are dynamic (slide/turn)
  and excluded; only the shelf carcass bakes.

TEXEL DENSITY: target 512 px/m on the desk area at res 1024 (a 2 m desk
  spans ~1024 px). Fixed --res applies to every group in v1; the manifest
  records each group's world bounds so density can be audited per group
  (px/m ~= res / max(bounds extent)). Margin 0.06 of tile avoids bleed.
"""

import argparse
import hashlib
import json
import math
import os
import sys

import bpy
import mathutils

# ---------------------------------------------------------------------------
# Paths (repo root = cwd when invoked as documented)
# ---------------------------------------------------------------------------

ROOT = os.getcwd()
PROCESSED = os.path.join(ROOT, "assets", "processed")
SOURCE_DIR = os.path.join(ROOT, "blender", "source")

# ---------------------------------------------------------------------------
# Lighting states: VERBATIM from src/scene/lighting.ts KEYS rows.
# day=hour 13, golden=hour 18.5, evening=hour 20, night=hour 21.5.
# Do not edit these numbers without editing lighting.ts first.
# ---------------------------------------------------------------------------

LIGHT_STATES = {
    "day": {
        "hour": 13,
        "sun": 13.2, "sunColor": "#ffefd6", "sunElevation": 31, "sunAzimuth": -0.42,
        "window": 2.7, "windowColor": "#bcd3ea",
        "hemi": 0.105, "hemiSky": "#d2e0ee", "hemiGround": "#575249",
        "lamp": 0, "monitor": 2.0, "led": 0.35,
    },
    "golden": {
        "hour": 18.5,
        "sun": 11.0, "sunColor": "#ff9552", "sunElevation": 7, "sunAzimuth": 0.62,
        "window": 2.0, "windowColor": "#f2bf93",
        "hemi": 0.095, "hemiSky": "#c9a88c", "hemiGround": "#3c322c",
        "lamp": 1.5, "monitor": 2.1, "led": 0.6,
    },
    "evening": {
        "hour": 20,
        "sun": 0.25, "sunColor": "#ff6a3a", "sunElevation": 0, "sunAzimuth": 0.9,
        "window": 0.7, "windowColor": "#6b7694",
        "hemi": 0.095, "hemiSky": "#44526f", "hemiGround": "#121214",
        "lamp": 2.5, "monitor": 2.6, "led": 1.05,
    },
    "night": {
        "hour": 21.5,
        "sun": 0, "sunColor": "#8aa0c8", "sunElevation": 20, "sunAzimuth": 0.9,
        "window": 0.4, "windowColor": "#42588a",
        "hemi": 0.08, "hemiSky": "#263654", "hemiGround": "#0b0d10",
        "lamp": 2.9, "monitor": 2.9, "led": 1.3,
    },
    # Lights-neutral AO/bounce baseline for later interpolation experiments.
    "neutral": {
        "hour": -1,
        "sun": 0, "sunColor": "#ffffff", "sunElevation": 45, "sunAzimuth": 0.0,
        "window": 0, "windowColor": "#ffffff",
        "hemi": 0, "hemiSky": "#ffffff", "hemiGround": "#3a3a3a",
        "lamp": 0, "monitor": 0, "led": 0,
    },
}

# Fixed room facts from layout.ts / lighting.ts / desk.ts (read, not invented).
ROOM = {"wallZ": -1.3, "wallDepth": 0.24, "wallTop": 3.4,
        "leftWallX": -1.82, "rightWallX": 1.7,
        "win": (-1.32, 1.02, 0.7, 2.5), "frameInset": 0.11, "floorRadius": 9}
DESK = {"centerX": -0.02, "centerZ": -0.74, "top": 0.735}
DESKTOP = {
    "monitor": {"x": -0.05, "z": -1.0, "rot": 0.0},
    "macbook": {"x": -0.06, "z": -0.695, "rot": 0.02},
    "keyboard": {"x": -0.05, "z": -0.455, "rot": 0.0},
    "mouse": {"x": 0.33, "z": -0.45, "rot": -0.14},
    "lamp": {"x": -0.72, "z": -1.03, "rot": -2.23, "scale": 0.92},
    "cube": {"x": -0.33, "z": -0.62, "rot": 0.42},
    "mug": {"x": -0.5, "z": -0.5, "rot": 0.5},
}
SHELF = {"x": -1.72, "y": 1.1, "z": -0.8}
LAMP_ANGLE = 0.55          # from lighting.ts
LAMP_DISK_RADIUS = 0.04    # headRadius sidecar; lampDisk.ts header says 13 cm
MONITOR_SIZE = (0.596, 0.341)  # monitor.json screenWidth/Height

# Renderer-unit translation gains (same for every state; recorded in manifest).
SUN_GAIN = 1.0
AREA_GAIN = 5.0
SPOT_GAIN = 8.0
WORLD_GAIN_NEUTRAL = 1.0

TEXEL_TARGET_PX_PER_M = 512  # desk area at res 1024
PACK_MARGIN = 0.06

# group -> (glb, three-space position, rotY radians, scale).
# Positions mirror desk.ts / room.ts / bookshelf.ts / projects.ts exactly.
_Y = DESK["top"]
GROUPS = {
    # World-space already (trim.glb built in world coords): no transform.
    "trim": ("trim.glb", (0, 0, 0), 0.0, 1.0, False),
    "desk": ("desk.glb", (DESK["centerX"], 0, DESK["centerZ"]), 0.0, 1.0, False),
    "chair": ("chair.glb", (0.02, 0, 0.08), 0.0, 1.0, False),  # seated pose
    "shelf": ("shelf.glb", None, None, 1.0, True),  # special: wall mount, see below
    "monitor": ("monitor.glb", (DESKTOP["monitor"]["x"], _Y, DESKTOP["monitor"]["z"]),
                DESKTOP["monitor"]["rot"], 1.0, False),
    "macbook": ("macbook.glb", (DESKTOP["macbook"]["x"], _Y, DESKTOP["macbook"]["z"]),
                DESKTOP["macbook"]["rot"], 1.0, False),
    "keyboard": ("keyboard.glb", (DESKTOP["keyboard"]["x"], _Y, DESKTOP["keyboard"]["z"]),
                 DESKTOP["keyboard"]["rot"], 1.0, False),
    "mouse": ("mouse.glb", (DESKTOP["mouse"]["x"], _Y, DESKTOP["mouse"]["z"]),
              DESKTOP["mouse"]["rot"], 1.0, False),
    "lamp": ("lamp.glb", (DESKTOP["lamp"]["x"], _Y, DESKTOP["lamp"]["z"]),
             DESKTOP["lamp"]["rot"], DESKTOP["lamp"]["scale"], False),
    "cube": ("cube.glb", (DESKTOP["cube"]["x"], _Y, DESKTOP["cube"]["z"]),
             DESKTOP["cube"]["rot"], 1.0, False),
    "mug": ("mug.glb", (DESKTOP["mug"]["x"], _Y, DESKTOP["mug"]["z"]),
            DESKTOP["mug"]["rot"], 1.0, False),
    "organizer": ("organizer.glb", (0.86, _Y, -0.97), -0.16, 1.0, False),
    "bin": ("bin.glb", (0.6, _Y, -1.03), 0.1, 1.0, False),
    "board": ("board.glb", (0.44, _Y, -0.64), 0.42, 1.0, False),
    "hub": ("hub.glb", (0.3, _Y, -0.96), 0.24, 1.0, False),
    "cable": ("cable.glb", (0.86, _Y, -0.62), 0.3, 1.0, False),
    "screwdriver": ("screwdriver.glb", (0.58, _Y, -0.56), 0.9, 1.0, False),
    "tote": ("tote.glb", (0.64, 0, -0.8), -0.12, 1.0, False),
    "robot": ("robot.glb", (-1.12, 0, 0.34), 0.86, 1.0, False),
    "book": None,  # dynamic (slide/turn/leap) -- excluded from bake
}


def three_to_blender(p):
    """three Y-up (x,y,z) -> Blender Z-up (x,-z,y)."""
    return mathutils.Vector((p[0], -p[2], p[1]))


def hex_linear(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                 for c in srgb)


def deselect_all():
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = None


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def place_group(name, spec):
    """Import a group GLB and move it to its runtime transform. Returns meshes."""
    glb, pos, rot, scale, _special = spec
    if name == "shelf":
        return place_shelf()
    objs = import_glb(os.path.join(PROCESSED, glb))
    meshes = [o for o in objs if o.type == "MESH"]
    bp = three_to_blender(pos)
    for o in meshes:
        # GLB import lands geometry in Blender space already; apply the
        # runtime rigid transform on top at object level.
        o.location += bp
        o.rotation_euler.rotate_axis("Z", rot)
        # rotation about own origin would orbit around world origin; instead
        # rotate the offset too: recompute properly below.
    # Correct approach: rotate each object's location about the group pivot,
    # then rotate the object itself.
    for o in meshes:
        o.location -= bp
    for o in meshes:
        # undo the naive rotate above by resetting, then do pivot rotation
        o.rotation_euler.rotate_axis("Z", -rot)
    for o in meshes:
        rel = o.location  # currently (import_loc) since we subtracted bp... \
        # Simplest correct: objects import at local coords; group pivot is bp.
        # So: world = R * local + bp.
        loc = mathutils.Vector(o.location)
        # o.location currently holds (import_loc - 0)? re-derive: after the
        # two loops o.location == import_loc - bp and rotation == import rot0.
        # Apply pivot rotation:
        rotmat = mathutils.Matrix.Rotation(rot, 4, "Z")
        new_loc = rotmat @ loc + bp
        o.location = new_loc
        o.rotation_euler.rotate_axis("Z", rot)
        if scale != 1.0:
            # scale about the pivot: offset scales, object scales
            o.location = bp + (o.location - bp) * scale
            o.scale *= scale
    bpy.context.view_layer.update()
    for o in meshes:
        o.name = f"{name}_{o.name}"
    return meshes


def place_shelf():
    """Shelf carcass: group at (SHELF.x,SHELF.y,SHELF.z), rotationY=PI/2.

    three rotationY=PI/2 maps local +x along the wall. In Blender that is a
    rotation about Z by +PI/2 applied to the shelf-local frame, where
    shelf-local (x along wall, y up, z into room) was authored as Blender
    (x, -z, y) (see build_furniture.py). The GLB already carries that author
    frame in its vertices; at runtime the group node adds position+rotY.
    Reproduce the node: R_z(PI/2) about pivot bp.
    """
    objs = import_glb(os.path.join(PROCESSED, "shelf.glb"))
    meshes = [o for o in objs if o.type == "MESH"]
    bp = three_to_blender((SHELF["x"], SHELF["y"], SHELF["z"]))
    rotmat = mathutils.Matrix.Rotation(math.pi / 2, 4, "Z")
    for o in meshes:
        o.location = rotmat @ mathutils.Vector(o.location) + bp
        o.rotation_euler.rotate_axis("Z", math.pi / 2)
    bpy.context.view_layer.update()
    for o in meshes:
        o.name = f"shelf_{o.name}"
    return meshes


def build_shell():
    """Procedural occluders: floor disc, window wall slabs, side walls.

    Mirrors room.ts buildShell planes from ROOM dims. Plain diffuse white-grey
    so they bounce like the room's walls; NOT bake targets.
    """
    wall_mat = bpy.data.materials.new("bake_wall")
    wall_mat.use_nodes = True
    bsdf = wall_mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.55, 0.55, 0.56, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9

    def box(name, sx, sy, sz, loc):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
        o = bpy.context.object
        o.name = name
        o.scale = (sx, sy, sz)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        o.data.materials.clear()
        o.data.materials.append(wall_mat)
        return o

    made = []
    x0, x1, y0, y1 = ROOM["win"]
    wz, wd, top = ROOM["wallZ"], ROOM["wallDepth"], ROOM["wallTop"]
    cz = wz - wd / 2  # wall centre, three z
    # Blender loc = (x_three, -z_three, y_three)
    W = 6.8
    made.append(box("shell_below", W, wd, (y0 - 0.02), ((x0 + x1) / 2, -cz, (y0 - 0.02) / 2)))
    made.append(box("shell_above", W, wd, (top - y1), ((x0 + x1) / 2, -cz, (y1 + top) / 2)))
    made.append(box("shell_left", (x0 + 2.4), wd, (y1 - y0), ((-2.4 + x0) / 2, -cz, (y0 + y1) / 2)))
    made.append(box("shell_right", (4.4 - x1), wd, (y1 - y0), ((x1 + 4.4) / 2, -cz, (y0 + y1) / 2)))
    made.append(box("shell_side_L", 0.08, 3.0, top, (ROOM["leftWallX"], 0.1, top / 2)))
    made.append(box("shell_side_R", 0.08, 3.0, top, (ROOM["rightWallX"], 0.1, top / 2)))
    # Floor disc
    bpy.ops.mesh.primitive_cylinder_add(vertices=56, radius=ROOM["floorRadius"],
                                        depth=0.02, location=(0, 0, -0.01))
    floor = bpy.context.object
    floor.name = "shell_floor"
    floor.data.materials.clear()
    floor.data.materials.append(wall_mat)
    made.append(floor)
    return made


def clear_lights():
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o, do_unlink=True)


def setup_lights(state_name, st):
    """Recreate the state's emitters. Returns a note string for the manifest."""
    clear_lights()
    notes = []
    neutral = state_name == "neutral"

    # World: hemi approximation (Blender has no hemisphere light). For real
    # states the world carries hemiSky/hemiGround mix at hemi strength; for
    # neutral it is uniform white so the bake is pure AO/bounce.
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("BakeWorld")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if neutral:
        bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        bg.inputs["Strength"].default_value = WORLD_GAIN_NEUTRAL
        notes.append("neutral: uniform white world, all lamps off")
        return "; ".join(notes)
    sky = hex_linear(st["hemiSky"])
    gnd = hex_linear(st["hemiGround"])
    mix = tuple((s + g) / 2 for s, g in zip(sky, gnd))
    bg.inputs["Color"].default_value = (*mix, 1.0)
    bg.inputs["Strength"].default_value = max(st["hemi"], 1e-4)
    notes.append(f"worldhemi={st['hemi']} {st['hemiSky']}/{st['hemiGround']}")

    # Sun (directional): elevation/azimuth verbatim from the keyframe.
    if st["sun"] > 0:
        az = st["sunAzimuth"]
        el = math.radians(max(st["sunElevation"], 3))
        # three toSun, then to Blender
        ts = mathutils.Vector((math.sin(az) * math.cos(el), math.sin(el),
                               -math.cos(az) * math.cos(el)))
        bs = mathutils.Vector((ts.x, -ts.z, ts.y))
        data = bpy.data.lights.new("sun", "SUN")
        data.energy = st["sun"] * SUN_GAIN
        data.color = hex_linear(st["sunColor"])
        o = bpy.data.objects.new("sun", data)
        bpy.context.collection.objects.link(o)
        target_b = three_to_blender((-0.05, 0.7, -0.4))
        o.location = target_b + bs * 8
        o.rotation_euler = (target_b - o.location).to_track_quat("-Z", "Y").to_euler()
        # Shadows on: direct is excluded from the bake anyway, but shadow
        # rays shape the indirect.
        notes.append(f"sun={st['sun']} {st['sunColor']} el={st['sunElevation']} az={st['sunAzimuth']}")
    else:
        notes.append("sun off")

    # Window rect: whole opening as one soft source (lighting.ts §8).
    if st["window"] > 0:
        x0, x1, y0, y1 = ROOM["win"]
        W, H = x1 - x0, y1 - y0
        fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
        data = bpy.data.lights.new("window", "AREA")
        data.energy = st["window"] * AREA_GAIN * W * H
        data.color = hex_linear(st["windowColor"])
        data.size = W
        # Blender area is square-ish; encode H via scale_y on the object.
        o = bpy.data.objects.new("window", data)
        bpy.context.collection.objects.link(o)
        o.location = three_to_blender((fx, fy, ROOM["wallZ"] + 0.02))
        o.rotation_euler = (three_to_blender((fx, fy - 0.3, ROOM["wallZ"] + 1))
                            - o.location).to_track_quat("-Z", "Y").to_euler()
        o.scale.y = H / W
        notes.append(f"window={st['window']} {st['windowColor']} {W:.2f}x{H:.2f}m")
    else:
        notes.append("window off")

    # Lamp spot at the blade socket along the sidecar beam.
    if st["lamp"] > 0:
        import json as _json
        with open(os.path.join(PROCESSED, "lamp.json")) as f:
            meta = _json.load(f)
        sock = mathutils.Vector(meta["socket"])  # glTF Y-up metres, asset-local
        beam = mathutils.Vector(meta["beam"]).normalized()
        # asset-local glTF -> Blender: (x,y,z)->(x,-z,y); then group transform
        # (rotY=yaw, scale, translate to desktop pos).
        yaw = DESKTOP["lamp"]["rot"]
        sc = DESKTOP["lamp"]["scale"]
        rm = mathutils.Matrix.Rotation(yaw, 4, "Z")

        def asset_to_world(v_gltf):
            v_b = mathutils.Vector((v_gltf.x, -v_gltf.z, v_gltf.y)) * sc
            v_b = rm @ v_b
            return v_b + three_to_blender(
                (DESKTOP["lamp"]["x"], DESK["top"], DESKTOP["lamp"]["z"]))

        sock_w = asset_to_world(sock)
        # beam direction glTF->Blender (rotation only, no translate)
        beam_b = mathutils.Vector((beam.x, -beam.z, beam.y))
        beam_b = (rm @ beam_b.to_4d()).to_3d().normalized()
        data = bpy.data.lights.new("lamp", "SPOT")
        data.energy = st["lamp"] * SPOT_GAIN
        data.color = tuple(c for c in hex_linear("#ffd2a0"))
        data.spot_size = LAMP_ANGLE * 2
        data.spot_blend = 0.85  # matches three SpotLight penumbra 0.85
        data.shadow_soft_size = LAMP_DISK_RADIUS  # disk penumbra approximation
        o = bpy.data.objects.new("lamp", data)
        bpy.context.collection.objects.link(o)
        o.location = sock_w
        o.rotation_euler = (beam_b).to_track_quat("-Z", "Y").to_euler()
        notes.append(f"lamp={st['lamp']} spot_angle={LAMP_ANGLE} disk_r={LAMP_DISK_RADIUS}")
    else:
        notes.append("lamp off")

    # Monitor glow: area the size of the panel at the runtime screen pose.
    if st["monitor"] > 0:
        data = bpy.data.lights.new("screenGlow", "AREA")
        data.energy = st["monitor"] * 1.15 * AREA_GAIN * MONITOR_SIZE[0] * MONITOR_SIZE[1]
        data.color = tuple(c for c in hex_linear("#cfe0f2"))
        data.size = MONITOR_SIZE[0]
        o = bpy.data.objects.new("screenGlow", data)
        bpy.context.collection.objects.link(o)
        mx = DESKTOP["monitor"]["x"]
        mz = DESKTOP["monitor"]["z"]
        # Panel faces +z (toward visitor) from the desk back.
        o.location = three_to_blender((mx, DESK["top"] + 0.30, mz + 0.02))
        o.rotation_euler = (three_to_blender((mx, DESK["top"] + 0.25, mz + 1))
                            - o.location).to_track_quat("-Z", "Y").to_euler()
        o.scale.y = MONITOR_SIZE[1] / MONITOR_SIZE[0]
        notes.append(f"monitor={st['monitor']}")
    else:
        notes.append("monitor off")

    # Shelf strip: small warm area under the top board.
    if st["led"] > 0:
        data = bpy.data.lights.new("shelfLight", "AREA")
        data.energy = st["led"] * 2.2 * AREA_GAIN * 0.1
        data.color = tuple(c for c in hex_linear("#ffeacc"))
        data.size = 0.3
        o = bpy.data.objects.new("shelfLight", data)
        bpy.context.collection.objects.link(o)
        o.location = three_to_blender((SHELF["x"] + 0.1, SHELF["y"] + 0.3, SHELF["z"]))
        o.rotation_euler = (three_to_blender((SHELF["x"] + 0.1, SHELF["y"] - 0.4, SHELF["z"] + 0.28))
                            - o.location).to_track_quat("-Z", "Y").to_euler()
        notes.append(f"shelf_led={st['led']}")
    else:
        notes.append("shelf off")

    return "; ".join(notes)


def ensure_lightmap_uv(obj, margin):
    me = obj.data
    if "Lightmap" not in me.uv_layers:
        me.uv_layers.new(name="Lightmap")
    me.uv_layers.active = me.uv_layers["Lightmap"]
    me.uv_layers.active.active_render = True
    # Repack with margin to avoid bleed (brief requirement).
    bpy.context.view_layer.objects.active = obj
    deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        # Blender 5.0 signature: PREF_CONTEXT, PREF_PACK_IN_ONE,
        # PREF_NEW_UVLAYER, PREF_BOX_DIV, PREF_MARGIN_DIV (margin ~= 1/DIV).
        bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True,
                                 PREF_NEW_UVLAYER=False, PREF_BOX_DIV=12,
                                 PREF_MARGIN_DIV=max(int(1.0 / margin), 2))
    except (RuntimeError, TypeError) as err:
        print(f"  ! lightmap_pack failed on {obj.name}: {err}; keeping existing")
    bpy.ops.object.mode_set(mode="OBJECT")
    deselect_all()


def bake_image_for(obj, img):
    """Wire the bake image into every material via an active image node."""
    for mat in obj.data.materials:
        if mat is None:
            continue
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        # Reuse an existing bake node if present.
        found = None
        for n in nodes:
            if n.type == "TEX_IMAGE" and n.label == "BAKE_TARGET":
                found = n
                break
        if found is None:
            found = nodes.new(type="ShaderNodeTexImage")
            found.label = "BAKE_TARGET"
            found.location = (-600, 300)
        found.image = img
        nodes.active = found


def world_bounds(objs):
    lo = mathutils.Vector((1e9,) * 3)
    hi = mathutils.Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            lo = mathutils.Vector(map(min, lo, w))
            hi = mathutils.Vector(map(max, hi, w))
    return lo, hi


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def bake_state(state_name, out_dir, samples, res, only):
    st = LIGHT_STATES[state_name]
    # Cycles setup
    scene = bpy.context.scene
    try:
        scene.render.engine = "CYCLES"
    except TypeError as err:
        print(f"render engine CYCLES rejected: {err}")
    cyc = scene.cycles
    cyc.samples = samples
    cyc.use_denoising = True
    try:
        cyc.denoiser = "OPENIMAGEDENOISE"
    except (AttributeError, TypeError):
        pass
    cyc.bake_type = "DIFFUSE"
    try:
        cyc.use_pass_direct = False
        cyc.use_pass_indirect = True
        cyc.use_pass_color = False
    except AttributeError:
        pass
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = True
    scene.render.bake.use_pass_color = False
    try:
        scene.render.bake.margin = max(int(res * PACK_MARGIN), 4)
        scene.render.bake.target = "IMAGE_TEXTURES"
    except (AttributeError, TypeError):
        pass

    light_note = setup_lights(state_name, st)
    print(f"LIGHTS [{state_name}]: {light_note}")

    # Source hashes for the manifest.
    blend_hashes = {}
    for f in sorted(os.listdir(SOURCE_DIR)):
        if f.endswith(".blend"):
            blend_hashes[f] = file_hash(os.path.join(SOURCE_DIR, f))

    state_dir = os.path.join(out_dir, state_name)
    os.makedirs(state_dir, exist_ok=True)
    entries = []
    targets = [only] if only else [k for k, v in GROUPS.items() if v is not None]
    for name in targets:
        meshes = [o for o in bpy.data.objects if o.name.startswith(name + "_") and o.type == "MESH"]
        if not meshes:
            print(f"  ! group {name}: no meshes, skipping")
            continue
        for m in meshes:
            ensure_lightmap_uv(m, PACK_MARGIN)
        img_name = f"BAKE_{name}_{state_name}"
        if img_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[img_name])
        img = bpy.data.images.new(img_name, res, res, alpha=False, float_buffer=True)
        try:
            img.colorspace_settings.name = "Linear"
        except (AttributeError, TypeError):
            pass
        for m in meshes:
            bake_image_for(m, img)
        deselect_all()
        for m in meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        print(f"BAKE {name} {state_name} samples={samples} res={res} objs={len(meshes)}")
        try:
            bpy.ops.object.bake(type="DIFFUSE", use_clear=True,
                                margin=int(res * PACK_MARGIN))
        except TypeError:
            # Blender 5 moved margin to scene.render.bake (set above).
            bpy.ops.object.bake(type="DIFFUSE", use_clear=True)
        exr_path = os.path.join(state_dir, f"{name}.exr")
        png_path = os.path.join(state_dir, f"{name}.png")
        img.filepath_raw = exr_path
        img.file_format = "OPEN_EXR"
        img.save()
        # Tone-safe PNG preview: display-referred 8-bit through the view
        # transform. A float buffer cannot save directly to PNG, so go
        # through save_render (EXR above stays the linear master).
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_depth = "8"
        scene.render.image_settings.color_mode = "RGB"
        img.save_render(png_path)
        lo, hi = world_bounds(meshes)
        ext = hi - lo
        tris = sum(sum(len(p.vertices) - 2 for p in m.data.polygons) for m in meshes)
        entries.append({
            "group": name,
            "state": state_name,
            "hour": st["hour"],
            "resolution": res,
            "samples": samples,
            "uvChannel": "Lightmap",
            "texelTargetPxPerM": TEXEL_TARGET_PX_PER_M,
            "approxPxPerM": round(res / max(max(ext.x, ext.y, ext.z), 1e-6), 1),
            "worldBoundsBlender": [[round(v, 4) for v in lo], [round(v, 4) for v in hi]],
            "tris": tris,
            "bakeType": "DIFFUSE indirect-only (direct off, color off), denoised",
            "blenderVersion": bpy.app.version_string,
            "files": {os.path.basename(exr_path): os.path.getsize(exr_path),
                      os.path.basename(png_path): os.path.getsize(png_path)},
        })
        print(f"  SAVED {exr_path} + {png_path}")
    return entries, blend_hashes, light_note


def main():
    # Blender mangles argparse with its own flags; parse only after '--'.
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description="Bake room lightmaps (see module docstring).")
    ap.add_argument("state", nargs="?", default="neutral",
                    help="day|golden|evening|night|neutral|all")
    ap.add_argument("outDir", nargs="?", default="public/assets/lightmaps")
    ap.add_argument("--samples", type=int, default=256)
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--only", default=None, help="bake a single group, e.g. mug")
    args = ap.parse_args(raw)

    if args.state == "all":
        states = ["day", "golden", "evening", "night", "neutral"]
    else:
        if args.state not in LIGHT_STATES:
            raise SystemExit(f"unknown state '{args.state}': {[k for k in LIGHT_STATES]} + all")
        states = [args.state]

    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Assemble the whole room first (occluders matter even with --only).
    build_shell()
    for name, spec in GROUPS.items():
        if spec is None:
            continue
        if args.only and name != args.only:
            # Still import occluders at low cost? For --only smoke speed we
            # DO import everything: bounce needs the room. No shortcut.
            pass
        try:
            ms = place_group(name, spec)
            print(f"ASSEMBLED {name}: {len(ms)} meshes")
        except FileNotFoundError as err:
            print(f"  ! {name}: missing GLB, skipping ({err})")
        except RuntimeError as err:
            print(f"  ! {name}: import failed, skipping ({err})")

    manifest_path = os.path.join(args.outDir, "manifest.json")
    manifest = None
    if os.path.exists(manifest_path):
        # Merge: per-state runs (or a resumed `all`) must not clobber states
        # baked by an earlier invocation into the same outDir.
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except (ValueError, OSError) as err:
            print(f"  ! existing manifest unreadable, rewriting ({err})")
            manifest = None
    if not isinstance(manifest, dict) or "states" not in manifest:
        manifest = {"states": {}, "gains": {"sun": SUN_GAIN, "area": AREA_GAIN,
                                            "spot": SPOT_GAIN,
                                            "worldNeutral": WORLD_GAIN_NEUTRAL},
                    "texelTargetPxPerM": TEXEL_TARGET_PX_PER_M,
                    "packMargin": PACK_MARGIN,
                    "uvChannel": "Lightmap"}
    # Bake each state with its own lights (world/lights rebuilt per state).
    for s in states:
        entries, hashes, note = bake_state(s, args.outDir, args.samples, args.res, args.only)
        manifest["states"][s] = {"lights": note, "sourceBlendHashes": hashes,
                                 "entries": entries}
        manifest["blenderVersion"] = bpy.app.version_string
        os.makedirs(args.outDir, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"MANIFEST {manifest_path} (state {s} done)")


main()
