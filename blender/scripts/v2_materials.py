"""
Material realism pass for the room scene (Cycles).

Run inside Blender (room.blend open):  exec(open(r"<repo>/blender/scripts/v2_materials.py").read())
Headless:  blender -b room.blend --python blender/scripts/v2_materials.py            (does not save)
           blender -b room.blend --python blender/scripts/v2_materials.py -- --save  (saves in place)

Idempotent: every material it touches is rebuilt from scratch from a record of its original
inputs (images, tint, uv scale) stored on the material the first time (custom prop `rm_src`),
and every object it reassigns remembers its original slot materials (custom prop `rm_src`).
Running it twice gives the same node trees and the same assignments.

What it does
  * upgrades glTF-export materials (Material_N) in place where every user is ours;
  * where a material is shared with objects other workers are replacing (mouse, macbook,
    cables, medals, curtains, window glass, NEW_* / OLD_* collections), it builds a new `rm_*`
    material and moves only our objects onto it, leaving the original untouched;
  * every recipe is procedural (object-space noise / voronoi / wave, bevel node for rounded
    CAD edges, bump for micro-relief, roughness breakup). Existing scanned images already in
    the file (ambientCG CC0: plaster, oak floor, fabric, wood) are reused, never downloaded.
Lighting, cameras, exposure, world: untouched.
"""
import bpy, json, sys

# ------------------------------------------------------------------ skip rules
SKIP_PREFIX = ('mouse_', 'curtain_', 'keyboard_cable', 'keyboard_boot', 'keyboard_plug',
               'monitor_cable', 'hub_cable', 'cable_coil', 'cable_tie', 'cable_boot',
               'cable_plug', 'medal')
SKIP_NAMES = {'Mesh_11'}                                   # window glass
SKIP_ANCESTORS = {'macbook_body', 'macbook_stand', 'mouse_body',
                  'Node_75', 'Node_83', 'Node_91', 'Node_99'}   # the four medals on the lamp arm
SKIP_MATERIALS = {'Material_23', 'Material_24', 'Material_25', 'Material_26', 'Material_27',
                  'Material_28', 'Material_29', 'window_glass_cycles', 'curtain_linen',
                  'curtain_rod_black', 'mon_dark.001'}


def is_skipped(o):
    if o.name in SKIP_NAMES or o.name.startswith(SKIP_PREFIX):
        return True
    if any(c.name.startswith(('NEW_', 'OLD_')) for c in o.users_collection):
        return True
    p = o.parent
    while p:
        if p.name in SKIP_ANCESTORS:
            return True
        p = p.parent
    return False


# ------------------------------------------------------------------ node helpers
class T:
    """Thin wrapper around a node tree with a cursor for tidy layout."""

    def __init__(self, m):
        m.use_nodes = True
        self.m = m
        self.nt = m.node_tree
        self.nt.nodes.clear()
        self.x = -200
        self.out = self.node('ShaderNodeOutputMaterial', loc=(400, 0))
        self.p = self.node('ShaderNodeBsdfPrincipled', loc=(100, 0))
        self.link(self.p.outputs['BSDF'], self.out.inputs['Surface'])
        self._co = None
        self.ext = {}                     # image name -> original extension mode

    def node(self, typ, loc=None, **props):
        n = self.nt.nodes.new(typ)
        for k, v in props.items():
            setattr(n, k, v)
        if loc is None:
            self.x -= 40
            loc = (self.x - 200, (len(self.nt.nodes) % 12) * -60)
        n.location = loc
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def val(self, sock, v):
        """Set a socket from a constant or link it from an output socket."""
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, sock)
        else:
            sock.default_value = v

    # coordinates ---------------------------------------------------------
    def co(self, space='Object'):
        if self._co is None:
            self._co = self.node('ShaderNodeTexCoord')
        return self._co.outputs[space]

    def scaled(self, scale, space='Object', rot=(0, 0, 0)):
        mp = self.node('ShaderNodeMapping')
        self.link(self.co(space), mp.inputs['Vector'])
        mp.inputs['Scale'].default_value = scale if hasattr(scale, '__len__') else (scale,) * 3
        mp.inputs['Rotation'].default_value = rot
        return mp.outputs['Vector']

    # textures -------------------------------------------------------------
    def noise(self, vec, scale, detail=2.0, rough=0.5, distortion=0.0, dims='3D', out='Fac'):
        n = self.node('ShaderNodeTexNoise', noise_dimensions=dims)
        self.link(vec, n.inputs['Vector'])
        n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail
        n.inputs['Roughness'].default_value = rough
        n.inputs['Distortion'].default_value = distortion
        return n.outputs[out]

    def voronoi(self, vec, scale, feature='F1', out='Distance', rnd=1.0):
        n = self.node('ShaderNodeTexVoronoi', feature=feature)
        self.link(vec, n.inputs['Vector'])
        n.inputs['Scale'].default_value = scale
        n.inputs['Randomness'].default_value = rnd
        return n.outputs[out]

    def wave(self, vec, scale, direction='X', distortion=0.0, detail=0.0, profile='SIN'):
        n = self.node('ShaderNodeTexWave', wave_type='BANDS', bands_direction=direction,
                      wave_profile=profile)
        self.link(vec, n.inputs['Vector'])
        n.inputs['Scale'].default_value = scale
        n.inputs['Distortion'].default_value = distortion
        n.inputs['Detail'].default_value = detail
        return n.outputs['Fac']

    def image(self, name, vec=None, non_color=False):
        img = bpy.data.images.get(name) if name else None
        if img is None:
            return None
        n = self.node('ShaderNodeTexImage')
        n.image = img
        n.extension = self.ext.get(name, 'REPEAT')
        if vec is not None:
            self.link(vec, n.inputs['Vector'])
        return n

    # math -----------------------------------------------------------------
    def maprange(self, v, a, b, c, d, clamp=True):
        n = self.node('ShaderNodeMapRange', clamp=clamp)
        self.val(n.inputs['Value'], v)
        n.inputs['From Min'].default_value = a
        n.inputs['From Max'].default_value = b
        n.inputs['To Min'].default_value = c
        n.inputs['To Max'].default_value = d
        return n.outputs['Result']

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        self.val(n.inputs[0], a)
        self.val(n.inputs[1], b)
        return n.outputs[0]

    def mixf(self, fac, a, b):
        n = self.node('ShaderNodeMix', data_type='FLOAT')
        self.val(n.inputs['Factor'], fac)
        self.val(_sock(n.inputs, 'A_Float'), a)
        self.val(_sock(n.inputs, 'B_Float'), b)
        return _sock(n.outputs, 'Result_Float')

    def mixc(self, fac, a, b, blend='MIX'):
        n = self.node('ShaderNodeMix', data_type='RGBA', blend_type=blend)
        self.val(n.inputs['Factor'], fac)
        self.val(_sock(n.inputs, 'A_Color'), a)
        self.val(_sock(n.inputs, 'B_Color'), b)
        return _sock(n.outputs, 'Result_Color')

    def hsv(self, col, h=0.5, s=1.0, v=1.0):
        n = self.node('ShaderNodeHueSaturation')
        self.val(n.inputs['Color'], col)
        n.inputs['Hue'].default_value = h
        n.inputs['Saturation'].default_value = s
        n.inputs['Value'].default_value = v
        return n.outputs['Color']

    def bw(self, col):
        n = self.node('ShaderNodeRGBToBW')
        self.link(col, n.inputs['Color'])
        return n.outputs['Val']

    # normals --------------------------------------------------------------
    def bevel(self, radius, samples=6):
        if radius <= 0:
            return None
        n = self.node('ShaderNodeBevel', samples=samples)
        n.inputs['Radius'].default_value = radius
        return n.outputs['Normal']

    def bump(self, height, strength, distance=0.001, normal=None):
        n = self.node('ShaderNodeBump')
        self.val(n.inputs['Height'], height)
        n.inputs['Strength'].default_value = strength
        n.inputs['Distance'].default_value = distance
        if normal is not None:
            self.link(normal, n.inputs['Normal'])
        return n.outputs['Normal']

    def normalmap(self, img_name, strength, vec=None, normal=None):
        tex = self.image(img_name, vec)
        if tex is None:
            return normal
        tex.image.colorspace_settings.name = 'Non-Color'
        n = self.node('ShaderNodeNormalMap')
        n.inputs['Strength'].default_value = strength
        self.link(tex.outputs['Color'], n.inputs['Color'])
        return n.outputs['Normal']

    def edge_mask(self, distance=0.004, lo=0.80, hi=0.97):
        """1 on convex edges, 0 on flats (Cycles AO 'inside')."""
        ao = self.node('ShaderNodeAmbientOcclusion', inside=True, only_local=True, samples=8)
        ao.inputs['Distance'].default_value = distance
        return self.maprange(ao.outputs['AO'], lo, hi, 1.0, 0.0)

    # principled -----------------------------------------------------------
    def set(self, **kw):
        names = {'base': 'Base Color', 'rough': 'Roughness', 'metal': 'Metallic',
                 'normal': 'Normal', 'spec': 'Specular IOR Level', 'ior': 'IOR',
                 'coat': 'Coat Weight', 'coat_rough': 'Coat Roughness', 'coat_normal': 'Coat Normal',
                 'sheen': 'Sheen Weight', 'sheen_rough': 'Sheen Roughness', 'sheen_tint': 'Sheen Tint',
                 'sss': 'Subsurface Weight', 'sss_radius': 'Subsurface Radius',
                 'sss_scale': 'Subsurface Scale', 'aniso': 'Anisotropic', 'aniso_rot': 'Anisotropic Rotation',
                 'alpha': 'Alpha', 'emit': 'Emission Color', 'emit_strength': 'Emission Strength'}
        for k, v in kw.items():
            if v is None:
                continue
            sock = self.p.inputs[names[k]]
            if isinstance(v, tuple) and len(v) == 3 and sock.type == 'RGBA':
                v = (*v, 1.0)
            self.val(sock, v)


def _sock(coll, ident):
    for s in coll:
        if s.identifier == ident:
            return s
    raise KeyError(ident)


def rgb(*c):
    return (c[0], c[1], c[2], 1.0)


# ------------------------------------------------------------------ source records
def src_of(m):
    """Original inputs of a glTF material, captured once and stored on it."""
    if m.get('rm_src'):
        return json.loads(m['rm_src'])
    d = {}
    nt = m.node_tree if m.use_nodes else None
    if nt:
        p = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if p:
            d['base'] = list(p.inputs['Base Color'].default_value)
            d['rough'] = p.inputs['Roughness'].default_value
            d['metal'] = p.inputs['Metallic'].default_value
        for n in nt.nodes:
            if n.type == 'MAPPING':
                d['uvscale'] = list(n.inputs['Scale'].default_value)
            if n.type != 'TEX_IMAGE' or not n.image:
                continue
            d.setdefault('ext', {})[n.image.name] = n.extension
            if n.outputs['Alpha'].links:
                d['alpha'] = True
            for l in n.outputs['Color'].links:
                t = l.to_node
                if t.type == 'NORMAL_MAP':
                    d['normal'] = n.image.name
                    d['normal_strength'] = t.inputs['Strength'].default_value
                elif t.type == 'SEPARATE_COLOR':
                    d['orm'] = n.image.name
                elif t.type == 'MIX':
                    d['albedo'] = n.image.name
                    d['tint'] = list(_sock(t.inputs, 'B_Color').default_value)
                elif t.type == 'BSDF_PRINCIPLED' and l.to_socket.name == 'Base Color':
                    d['albedo'] = n.image.name
                elif t.type == 'BSDF_PRINCIPLED' and l.to_socket.name == 'Emission Color':
                    d['emit_img'] = n.image.name
    m['rm_src'] = json.dumps(d)
    return d


def get_mat(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    return m


# ================================================================== recipes
# All recipes take (T, **params). Object coordinates are ~metres in this scene.

def plastic(t, base, rough=0.45, grain=2500.0, grain_str=0.12, var=0.06, bevel=0.0006,
            smudge=0.05, spec=0.5, sss=0.0, coat=0.0):
    """Injection-moulded plastic: fine spark-erosion (VDI) texture, roughness breakup,
    faint fingerprint-scale smudges, rounded edges."""
    v = t.scaled(1.0)
    fine = t.noise(v, grain, detail=3.0, rough=0.6)
    mid = t.noise(v, 40.0, detail=4.0, rough=0.55)
    smear = t.noise(v, 9.0, detail=2.0, rough=0.5, distortion=0.4)
    r = t.maprange(fine, 0.3, 0.7, rough - var * 0.5, rough + var * 0.5)
    r = t.math('ADD', r, t.maprange(smear, 0.45, 0.75, 0.0, -smudge))
    r = t.math('ADD', r, t.maprange(mid, 0.3, 0.7, -var * 0.4, var * 0.4), clamp=True)
    col = t.mixc(t.maprange(mid, 0.35, 0.65, 0.0, 1.0), rgb(*[c * 0.965 for c in base]),
                 rgb(*[min(1, c * 1.03) for c in base]))
    nrm = t.bump(fine, grain_str, 0.0004, t.bevel(bevel))
    t.set(base=col, rough=r, normal=nrm, spec=spec, metal=0.0)
    if sss:
        t.set(sss=sss, sss_radius=(0.5, 0.5, 0.5), sss_scale=0.002)
    if coat:
        t.set(coat=coat, coat_rough=0.2)


def rubber(t, base=(0.012, 0.012, 0.012), rough=0.85, bevel=0.0005):
    v = t.scaled(1.0)
    fine = t.noise(v, 3500.0, detail=2.0, rough=0.5)
    blotch = t.noise(v, 60.0, detail=3.0)
    r = t.maprange(blotch, 0.3, 0.7, rough - 0.12, rough + 0.05)
    t.set(base=rgb(*base), rough=r, spec=0.35, sheen=0.1, sheen_rough=0.6,
          normal=t.bump(fine, 0.25, 0.0004, t.bevel(bevel)))


def powder_coat(t, base, rough=0.5, peel_scale=350.0, peel=0.10, bevel=0.0012, wear=0.0,
                wear_col=(0.25, 0.25, 0.26), metallic_flake=0.0):
    """Powder-coated / painted steel: orange-peel waviness + fine grit, optional edge wear
    through to bare steel on convex edges."""
    v = t.scaled(1.0)
    peel_n = t.noise(v, peel_scale, detail=1.5, rough=0.4)
    grit = t.noise(v, 6000.0, detail=1.0)
    patch = t.noise(v, 6.0, detail=3.0)
    h = t.math('ADD', peel_n, t.math('MULTIPLY', grit, 0.15))
    r = t.maprange(patch, 0.3, 0.7, rough - 0.06, rough + 0.06)
    col = rgb(*base)
    metal = 0.0
    if wear > 0:
        edge = t.edge_mask(0.003)
        chip = t.noise(v, 180.0, detail=4.0, rough=0.7)
        wm = t.math('MULTIPLY', edge, t.maprange(chip, 0.45, 0.6, 0.0, 1.0), clamp=True)
        wm = t.math('MULTIPLY', wm, wear, clamp=True)
        col = t.mixc(wm, col, rgb(*wear_col))
        r = t.mixf(wm, r, 0.35)
        metal = t.mixf(wm, 0.0, 1.0)
    t.set(base=col, rough=r, metal=metal, normal=t.bump(h, peel, 0.0008, t.bevel(bevel)))


def aluminium(t, base=(0.80, 0.81, 0.82), rough=0.36, blast=5000.0, bevel=0.0006, edge_polish=0.0,
              brushed=False):
    """Bead-blasted (or anodised) aluminium: isotropic micro-dimple roughness, faint handling
    marks. edge_polish lowers roughness on convex edges (chamfer highlights)."""
    v = t.scaled(1.0)
    dimple = t.noise(v, blast, detail=2.0, rough=0.6)
    handling = t.noise(v, 12.0, detail=3.0, distortion=0.3)
    r = t.maprange(dimple, 0.3, 0.7, rough - 0.05, rough + 0.05)
    r = t.math('ADD', r, t.maprange(handling, 0.5, 0.75, 0.0, -0.06), clamp=True)
    if brushed:
        lines = t.noise(t.scaled((4000.0, 40.0, 40.0)), 1.0, detail=2.0)
        r = t.math('ADD', r, t.maprange(lines, 0.3, 0.7, -0.05, 0.05), clamp=True)
        t.set(aniso=0.5)
    if edge_polish > 0:
        r = t.mixf(t.math('MULTIPLY', t.edge_mask(0.002), edge_polish, clamp=True), r, 0.12)
    col = t.mixc(t.maprange(handling, 0.3, 0.7, 0, 1), rgb(*[c * 0.97 for c in base]), rgb(*base))
    t.set(base=col, metal=1.0, rough=r, normal=t.bump(dimple, 0.06, 0.0003, t.bevel(bevel)))


def chrome_steel(t, base=(0.78, 0.78, 0.77), rough=0.12):
    v = t.scaled((1.0, 1.0, 1.0))
    lines = t.noise(t.scaled((2500.0, 30.0, 30.0)), 1.0, detail=2.0)
    r = t.maprange(lines, 0.3, 0.7, rough - 0.04, rough + 0.05)
    t.set(base=rgb(*base), metal=1.0, rough=r, normal=t.bevel(0.0003))


def laminate_white(t, base=(0.62, 0.62, 0.60), rough=0.58, bevel=0.0015):
    """Matte white HPL laminate / powder-coat desk: fine stipple emboss, very faint mottling,
    wipe marks that read in the sun sheen, rounded 1.5 mm edge."""
    v = t.scaled(1.0)
    stipple = t.noise(v, 1400.0, detail=2.0, rough=0.55)
    fine = t.noise(v, 7000.0, detail=1.0)
    mottle = t.noise(v, 3.5, detail=3.0)
    wipe = t.noise(t.scaled((5.0, 18.0, 5.0)), 1.0, detail=3.0, distortion=1.2)
    r = t.maprange(stipple, 0.3, 0.7, rough - 0.05, rough + 0.05)
    r = t.math('ADD', r, t.maprange(wipe, 0.52, 0.72, 0.0, -0.10), clamp=True)
    col = t.mixc(t.maprange(mottle, 0.3, 0.7, 0, 1), rgb(*[c * 0.975 for c in base]),
                 rgb(*[c * 1.015 for c in base]))
    h = t.math('ADD', stipple, t.math('MULTIPLY', fine, 0.3))
    t.set(base=col, rough=r, spec=0.5, normal=t.bump(h, 0.06, 0.0003, t.bevel(bevel)))


def ceramic(t, base=(0.78, 0.77, 0.73), rough=0.07):
    """Glazed stoneware: glassy clear glaze over a faintly speckled body, slow waviness."""
    v = t.scaled(1.0)
    wav = t.noise(v, 45.0, detail=2.0)
    speck = t.voronoi(v, 700.0, out='Distance')
    speck_m = t.maprange(speck, 0.0, 0.06, 1.0, 0.0)
    rv = t.noise(v, 20.0, detail=2.0)
    col = t.mixc(t.math('MULTIPLY', speck_m, 0.55), rgb(*base), rgb(0.33, 0.30, 0.26))
    col = t.mixc(t.maprange(rv, 0.3, 0.7, 0, 1), col, t.mixc(0.5, col, rgb(0.72, 0.70, 0.64)))
    t.set(base=col, rough=0.35, spec=0.5, coat=1.0, ior=1.5,
          coat_rough=t.maprange(rv, 0.3, 0.7, rough - 0.03, rough + 0.03),
          coat_normal=t.bump(wav, 0.04, 0.001), normal=t.bump(speck_m, 0.05, 0.0002))


def paper(t, base=None, albedo_img=None, rough=0.88, fibre=0.12):
    v = t.scaled(1.0)
    fib = t.noise(t.scaled((2200.0, 900.0, 2200.0)), 1.0, detail=4.0, rough=0.65)
    tooth = t.noise(v, 5000.0, detail=1.0)
    h = t.math('ADD', fib, t.math('MULTIPLY', tooth, 0.5))
    col = rgb(*base) if base else None
    if albedo_img:
        tex = t.image(albedo_img)
        if tex:
            col = tex.outputs['Color']
    col = t.mixc(t.maprange(fib, 0.3, 0.7, 0, 1), col, t.hsv(col, v=0.95), blend='MIX') if col is not None else None
    t.set(base=col, rough=t.maprange(tooth, 0.2, 0.8, rough - 0.05, rough + 0.05), spec=0.35,
          sheen=0.05, sheen_rough=0.5, normal=t.bump(h, fibre, 0.0003))


def book_cloth(t, base=None, albedo_img=None, rough=0.78, pitch=2400.0, strength=0.22):
    """Bookcloth / buckram: plain weave of fine threads, slightly fuzzy (sheen)."""
    v = t.scaled(1.0)
    wx = t.wave(v, pitch, 'X', distortion=2.0, detail=1.0)
    wz = t.wave(v, pitch, 'Z', distortion=2.0, detail=1.0)
    wy = t.wave(v, pitch, 'Y', distortion=2.0, detail=1.0)
    weave = t.math('MULTIPLY', t.math('ADD', t.math('ADD', wx, wz), wy), 0.33)
    slub = t.noise(v, 300.0, detail=2.0)
    wear = t.noise(v, 30.0, detail=3.0)
    col = rgb(*base) if base else None
    if albedo_img:
        tex = t.image(albedo_img)
        if tex:
            col = tex.outputs['Color']
    col = t.mixc(t.maprange(slub, 0.3, 0.7, 0, 1), t.hsv(col, v=0.93), t.hsv(col, v=1.05))
    t.set(base=col, rough=t.maprange(wear, 0.3, 0.7, rough - 0.08, rough + 0.06), spec=0.35,
          sheen=0.08, sheen_rough=0.45, sheen_tint=col,
          normal=t.bump(t.math('ADD', weave, t.math('MULTIPLY', slub, 0.4)), strength, 0.0003,
                        t.bevel(0.0008)))


def pcb(t, albedo_img, rough=0.28):
    """Solder mask over copper: glossy mask, raised traces (from the board art's luminance),
    ENIG gold pads metallic where the art is yellow/bright."""
    tex = t.image(albedo_img)
    col = tex.outputs['Color'] if tex else rgb(0.02, 0.05, 0.12)
    lum = t.bw(col)
    pad = t.maprange(lum, 0.18, 0.35, 0.0, 1.0)
    v = t.scaled(1.0)
    grit = t.noise(v, 5000.0, detail=1.0)
    t.set(base=t.mixc(pad, t.hsv(col, s=1.1, v=0.9), rgb(0.85, 0.62, 0.30)), metal=t.mixf(pad, 0.0, 1.0),
          rough=t.mixf(pad, t.maprange(grit, 0.3, 0.7, rough - 0.05, rough + 0.05), 0.25),
          coat=t.mixf(pad, 0.6, 0.0), coat_rough=0.18,
          normal=t.bump(t.math('ADD', lum, t.math('MULTIPLY', grit, 0.05)), 0.35, 0.0002, t.bevel(0.0003)))


def plaster_paint(t, s):
    """Painted skim-coat plaster: scanned plaster normal (existing), roller stipple, matte
    eggshell paint with slight sheen variation."""
    v = t.scaled(1.0)
    stip = t.noise(v, 900.0, detail=3.0, rough=0.55)
    patch = t.noise(v, 1.5, detail=3.0)
    tint = s.get('tint') or (0.3, 0.3, 0.32, 1)
    col = rgb(*tint[:3])
    alb = t.image(s.get('albedo'))
    if alb:   # scan blotches halved: skim-coat under paint, not raw stucco
        flat = t.mixc(0.5, alb.outputs['Color'], rgb(0.88, 0.88, 0.88))
        col = t.mixc(1.0, flat, rgb(*tint[:3]), blend='MULTIPLY')
    col = t.mixc(t.maprange(patch, 0.3, 0.7, 0, 1), t.hsv(col, v=0.985), t.hsv(col, v=1.015))
    nrm = t.normalmap(s.get('normal'), 0.16)
    nrm = t.bump(stip, 0.06, 0.0005, nrm)
    t.set(base=col, rough=t.maprange(patch, 0.3, 0.7, 0.80, 0.90), spec=0.45, normal=nrm)


def gloss_paint(t, base, rough=0.3):
    v = t.scaled(1.0)
    peel = t.noise(v, 250.0, detail=1.5)
    patch = t.noise(v, 4.0, detail=2.0)
    t.set(base=rgb(*base), rough=t.maprange(patch, 0.3, 0.7, rough - 0.05, rough + 0.06),
          normal=t.bump(peel, 0.04, 0.0006, t.bevel(0.001)))


def oak_floor(t, s):
    """Engineered oak, matte lacquer: keep the scan, break tiling with large-scale tone
    variation, lacquer coat with uneven sheen and faint scuffs."""
    sc = s.get('uvscale', [12, 12, 1])
    uv = t.node('ShaderNodeUVMap')
    mp = t.node('ShaderNodeMapping')
    t.link(uv.outputs['UV'], mp.inputs['Vector'])
    mp.inputs['Scale'].default_value = sc
    vec = mp.outputs['Vector']
    alb = t.image(s.get('albedo'), vec)
    orm = t.image(s.get('orm'), vec)
    v = t.scaled(1.0)
    big = t.noise(v, 0.35, detail=3.0)
    mid = t.noise(v, 2.5, detail=3.0)
    scuff = t.noise(t.scaled((40.0, 400.0, 40.0)), 1.0, detail=4.0, distortion=1.5)
    col = alb.outputs['Color'] if alb else rgb(0.35, 0.22, 0.12)
    col = t.mixc(t.maprange(big, 0.3, 0.7, 0, 1), t.hsv(col, s=0.92, v=0.9), t.hsv(col, s=1.04, v=1.06))
    r = 0.5
    if orm:
        sep = t.node('ShaderNodeSeparateColor')
        t.link(orm.outputs['Color'], sep.inputs['Color'])
        r = t.maprange(sep.outputs['Green'], 0.0, 1.0, 0.35, 0.65)
    r = t.math('ADD', r, t.maprange(mid, 0.3, 0.7, -0.06, 0.06), clamp=True)
    t.set(base=col, rough=r, spec=0.5, normal=t.normalmap(s.get('normal'), 0.7, vec),
          coat=0.35, coat_rough=t.maprange(scuff, 0.5, 0.75, 0.18, 0.4))


def woven_rug(t, s, pile_scale=900.0):
    """Flat-woven / low-loop rug: scanned fabric (existing), loop-pile relief, fibre sheen."""
    v = t.scaled(1.0)
    loops = t.voronoi(v, pile_scale, out='Distance')
    fuzz = t.noise(v, 4000.0, detail=2.0)
    heather = t.noise(v, 150.0, detail=3.0)
    tint = s.get('tint') or (0.04, 0.04, 0.045, 1)
    col = rgb(*tint[:3])
    alb = t.image(s.get('albedo'))
    if alb:
        col = t.mixc(1.0, alb.outputs['Color'], rgb(*tint[:3]), blend='MULTIPLY')
    col = t.mixc(t.maprange(heather, 0.3, 0.7, 0, 1), t.hsv(col, v=0.85), t.hsv(col, v=1.2))
    nrm = t.normalmap(s.get('normal'), 0.8)
    h = t.math('ADD', t.maprange(loops, 0.0, 0.5, 1.0, 0.0), t.math('MULTIPLY', fuzz, 0.3))
    t.set(base=col, rough=0.95, spec=0.3, sheen=0.35, sheen_rough=0.35, sheen_tint=col,
          normal=t.bump(h, 0.35, 0.001, nrm))


def upholstery(t, s):
    """Chair: woven polyester upholstery (existing fabric scan) + weave relief and sheen."""
    v = t.scaled(1.0)
    wx = t.wave(v, 1300.0, 'X', distortion=1.5, detail=1.0)
    wz = t.wave(v, 1300.0, 'Z', distortion=1.5, detail=1.0)
    heather = t.noise(v, 200.0, detail=3.0)
    tint = s.get('tint') or (0.02, 0.02, 0.025, 1)
    col = rgb(*tint[:3])
    alb = t.image(s.get('albedo'))
    if alb:
        col = t.mixc(1.0, alb.outputs['Color'], rgb(*tint[:3]), blend='MULTIPLY')
    col = t.mixc(t.maprange(heather, 0.3, 0.7, 0, 1), t.hsv(col, v=0.9), t.hsv(col, v=1.15))
    nrm = t.normalmap(s.get('normal'), 0.8)
    t.set(base=col, rough=0.9, spec=0.3, sheen=0.3, sheen_rough=0.3, sheen_tint=col,
          normal=t.bump(t.math('MULTIPLY', wx, wz), 0.25, 0.0005, nrm))


def oiled_oak(t, s):
    """Shelf board: oiled oak veneer. Keeps the existing wood scan, pulls it from orange pine
    toward natural oak, satin oil sheen, rounded edge."""
    alb = t.image(s.get('albedo'))
    orm = t.image(s.get('orm'))
    # scan luminance x natural white-oak tone (the scan itself is orange pine)
    lum = t.bw(alb.outputs['Color']) if alb else 0.34
    col = t.mixc(1.0, t.mixc(1.0, rgb(1, 1, 1), lum, blend='MULTIPLY') if alb else rgb(0.34, 0.34, 0.34),
                 rgb(1.42, 0.90, 0.48), blend='MULTIPLY')
    v = t.scaled(1.0)
    pores = t.noise(t.scaled((60.0, 3000.0, 3000.0)), 1.0, detail=3.0)
    r = 0.55
    if orm:
        sep = t.node('ShaderNodeSeparateColor')
        t.link(orm.outputs['Color'], sep.inputs['Color'])
        r = t.maprange(sep.outputs['Green'], 0.0, 1.0, 0.45, 0.7)
    nrm = t.normalmap(s.get('normal'), 0.5, normal=t.bevel(0.0015))
    t.set(base=col, rough=r, spec=0.5, normal=t.bump(pores, 0.08, 0.0003, nrm))


def cordura(t, base):
    """Robot bumper fabric (Cordura nylon): coarse basket weave, high sheen."""
    v = t.scaled(1.0)
    wx = t.wave(v, 700.0, 'X', distortion=1.0, detail=1.0)
    wy = t.wave(v, 700.0, 'Y', distortion=1.0, detail=1.0)
    wz = t.wave(v, 700.0, 'Z', distortion=1.0, detail=1.0)
    weave = t.math('MULTIPLY', t.math('ADD', t.math('ADD', wx, wy), wz), 0.33)
    dirt = t.noise(v, 8.0, detail=4.0)
    col = t.mixc(t.maprange(dirt, 0.45, 0.75, 0.0, 0.35), rgb(*base), rgb(0.12, 0.05, 0.04))
    t.set(base=col, rough=0.72, spec=0.4, sheen=0.25, sheen_rough=0.35, sheen_tint=col,
          normal=t.bump(weave, 0.35, 0.0005, t.bevel(0.003)))


def keycap(t, base, rough=0.62):
    """Double-shot PBT keycaps: sandy matte texture, slightly rounded top edges."""
    plastic(t, base, rough=rough, grain=4500.0, grain_str=0.2, var=0.05, bevel=0.0005,
            smudge=0.08, spec=0.45, sss=0.08)


def screen_off(t):
    """Anti-glare IPS panel, off: near-black with a hazy matte coating."""
    v = t.scaled(1.0)
    haze = t.noise(v, 8000.0, detail=1.0)
    t.set(base=rgb(0.006, 0.007, 0.008), rough=t.maprange(haze, 0.3, 0.7, 0.26, 0.32), spec=0.5,
          normal=t.bump(haze, 0.02, 0.0002))


def speedcube(t, base, rough=0.32):
    """Stickerless speed-cube tiles: frosted gloss ABS, soft edges."""
    plastic(t, base, rough=rough, grain=6000.0, grain_str=0.06, var=0.05, bevel=0.0008,
            smudge=0.06, spec=0.5)


def copper(t, base=(0.93, 0.60, 0.46), rough=0.3):
    v = t.scaled(1.0)
    tar = t.noise(v, 300.0, detail=3.0)
    t.set(base=t.mixc(t.maprange(tar, 0.4, 0.7, 0, 0.5), rgb(*base), rgb(0.55, 0.30, 0.20)), metal=1.0,
          rough=t.maprange(tar, 0.3, 0.7, rough - 0.08, rough + 0.1), normal=t.bevel(0.0003))


# ================================================================== the mapping
# In-place upgrades: material name -> (recipe, kwargs, identity note)
IN_PLACE = {
    'desk_white_laminate': ('desk', {}, 'desk_top_tmp: matte white HPL laminate (keeps its white)'),
    'desk_white_edge':     ('desk', {'bevel': 0.002}, 'desk_top_tmp_1 edge band: matte white laminate'),
    'Material_0':  (powder_coat, dict(base=(0.018, 0.019, 0.021), rough=0.42, peel=0.08), 'window frame: black powder-coated aluminium'),
    'Material_1':  ('plaster', {}, 'walls Mesh_5..10 + window reveal: painted plaster (keeps room paint colour)'),
    'Material_2':  (gloss_paint, dict(base=(0.60, 0.61, 0.60), rough=0.32), 'skirting / casing: satin-painted MDF'),
    'Material_3':  ('floor', {}, 'floor Mesh_3: engineered oak, matte lacquer'),
    'Material_4':  ('rug', {}, 'rug Mesh_4: woven charcoal rug'),
    'Material_7':  ('oak', {}, 'shelf_bottom: oiled oak board (was shared with the old desk edge)'),
    'Material_8':  (powder_coat, dict(base=(0.022, 0.023, 0.025), rough=0.5, peel=0.10, wear=0.35), 'desk legs/frame, shelf brackets, chair gas lift, sculpture base: dark powder-coat steel'),
    'Material_20': (keycap, dict(base=(0.70, 0.71, 0.72)), 'keyboard_alpha: light PBT keycaps'),
    'Material_21': (keycap, dict(base=(0.44, 0.46, 0.49)), 'keyboard_mod: grey PBT modifier caps'),
    'Material_37': (ceramic, dict(base=(0.76, 0.75, 0.71)), 'mug + handle: glazed stoneware'),
    'Material_39': (plastic, dict(base=(0.30, 0.37, 0.43), rough=0.42, grain=1800.0, grain_str=0.10, sss=0.03), 'blue-grey PP bins/tote/organizer'),
    'Material_41': (plastic, dict(base=(0.44, 0.40, 0.32), rough=0.42, grain=1800.0, grain_str=0.10, sss=0.03), 'beige PP bins/tote/shelf pot'),
    'Material_78': (plastic, dict(base=(0.045, 0.05, 0.058), rough=0.5, grain=1800.0, grain_str=0.12), 'dark PP tote under desk'),
    'Material_42': ('paper_label', {}, 'bin labels: paper'),
    'Material_43': ('pcb', {}, 'board_pcb: solder mask PCB'),
    'Material_44': ('pcb', {}, 'board_pcb.001 / Mesh_254: solder mask PCB'),
    'Material_45': ('pcb', {}, 'board_pcb.002: solder mask PCB'),
    'Material_47': (plastic, dict(base=(0.60, 0.10, 0.012), rough=0.22, grain=5000.0, grain_str=0.04, var=0.04, sss=0.05), 'orange-red: screwdriver handle, pencil, robot plates, sculpture cube (glossy)'),
    'Material_61': ('card', {}, 'Mesh_178 (shelf card) / Mesh_283 (box): printed card'),
    'Material_62': ('chair', {}, 'chair_base_3: chair upholstery'),
    'Material_67': (cordura, dict(base=(0.30, 0.018, 0.02)), 'robot bumpers: red Cordura'),
    'Material_71': (aluminium, dict(base=(0.72, 0.72, 0.73), rough=0.22, brushed=True), 'sculpture rods/nodes: brushed stainless'),
    'Material_72': ('cloth', dict(base=(0.026, 0.030, 0.036)), 'desk notebook (bottom): charcoal bookcloth'),
    'Material_73': ('cloth', dict(base=(0.050, 0.068, 0.092)), 'desk notebook (middle): navy bookcloth'),
    'Material_74': ('cloth', dict(base=(0.013, 0.022, 0.017)), 'desk notebook (top): green bookcloth'),
    'Material_75': ('paper_img', {}, 'Mesh_252: sketch sheet (drawn paper)'),
    'Material_16': (screen_off, {}, 'Mesh_26: monitor panel (off) anti-glare'),
    'Material_40': (copper, {}, 'copper parts (organizer, robot)'),
    'cube_body_mat':   (speedcube, dict(base=(0.012, 0.012, 0.014), rough=0.4), 'speedcube core'),
    'cube_white_mat':  (speedcube, dict(base=(0.80, 0.80, 0.78)), 'speedcube'),
    'cube_yellow_mat': (speedcube, dict(base=(0.85, 0.62, 0.03)), 'speedcube'),
    'cube_green_mat':  (speedcube, dict(base=(0.02, 0.45, 0.10)), 'speedcube'),
    'cube_blue_mat':   (speedcube, dict(base=(0.02, 0.13, 0.60)), 'speedcube'),
    'cube_orange_mat': (speedcube, dict(base=(0.95, 0.24, 0.02)), 'speedcube'),
    'cube_red_mat':    (speedcube, dict(base=(0.62, 0.02, 0.03)), 'speedcube'),
    'robot_yellow':    (powder_coat, dict(base=(0.70, 0.45, 0.02), rough=0.45, wear=0.5, wear_col=(0.55, 0.56, 0.57)), 'robot yellow plate: powder coat, edge wear'),
    'robot_poly':      (plastic, dict(base=(0.024, 0.028, 0.036), rough=0.35, grain=3000.0, grain_str=0.05), 'robot belly pan: polycarbonate'),
}
for i in range(49, 61):   # shelf books: covers keep their art/colour, gain bookcloth or paper-board finish
    IN_PLACE[f'Material_{i}'] = ('cloth_img', {'rough': 0.78 if i % 2 else 0.62}, 'shelf book cover')

# Split materials: new name -> (recipe, kwargs, rule). Rule = (source material, objects to
# exclude) or explicit object list. Only non-skipped objects move.
SPLIT = {
    'rm_steel_chrome':      (chrome_steel, {}, {'objects': ['driver_shaft', 'driver_tip', 'driver_bolster']}, 'screwdriver shaft/tip: chrome-vanadium steel'),
    'rm_rubber_black':      (rubber, {}, {'objects': ['hub_feet', 'driver_grip', 'driver_grip2']}, 'rubber feet / grips'),
    'rm_steel_frame':       (powder_coat, dict(base=(0.022, 0.023, 0.025), rough=0.5, peel=0.10), {'objects': ['desk_top_tmp_3']}, 'desk rear spine: dark powder-coat steel'),
    'rm_plastic_black':     (plastic, dict(base=(0.018, 0.018, 0.02), rough=0.5, grain=3000.0, grain_str=0.14), {'from': 'Material_9'}, 'black matte ABS/PC: monitor housing, chair frame, board parts, hub ports, robot'),
    'rm_plastic_black_nylon': (plastic, dict(base=(0.014, 0.014, 0.015), rough=0.62, grain=1500.0, grain_str=0.18, var=0.08), {'from': 'Material_10'}, 'glass-filled nylon: chair base, desk cable slot, tower, robot'),
    'rm_alu_dark':          (aluminium, dict(base=(0.12, 0.125, 0.135), rough=0.4, edge_polish=0.6), {'from': 'Material_11'}, 'space-grey anodised aluminium: monitor stand, lamp base/head, keyboard base, hub'),
    'rm_alu_bead':          (aluminium, dict(base=(0.80, 0.81, 0.82), rough=0.34, edge_polish=0.5), {'from': 'Material_17'}, 'bead-blast aluminium: lamp arm, robot frame, extrusions, board metal'),
    'rm_plastic_white':     (plastic, dict(base=(0.70, 0.71, 0.72), rough=0.42, grain=3500.0, grain_str=0.1, sss=0.06), {'from': 'Material_18'}, 'white ABS: keyboard case, misc white parts'),
    'rm_plastic_darkgrey':  (plastic, dict(base=(0.055, 0.06, 0.066), rough=0.48, grain=3000.0, grain_str=0.12), {'from': 'Material_19'}, 'dark grey ABS: keyboard plate, board case, robot'),
}


def build(m, recipe, kw):
    s = src_of(m)
    t = T(m)
    t.ext = s.get('ext', {})
    if recipe == 'plaster':
        plaster_paint(t, s)
    elif recipe == 'desk':
        base = tuple(s.get('base', (0.62, 0.62, 0.60, 1))[:3])
        if max(base) < 0.45 or max(base) - min(base) > 0.08:     # never let it drift off white
            base = (0.62, 0.62, 0.60)
        laminate_white(t, base=base, bevel=kw.get('bevel', 0.0015))
    elif recipe == 'floor':
        oak_floor(t, s)
    elif recipe == 'rug':
        woven_rug(t, s)
    elif recipe == 'chair':
        upholstery(t, s)
    elif recipe == 'oak':
        oiled_oak(t, s)
    elif recipe == 'pcb':
        pcb(t, s.get('albedo'))
    elif recipe == 'paper_label':
        paper(t, base=(0.74, 0.72, 0.67), fibre=0.15)
    elif recipe == 'paper_img':
        paper(t, albedo_img=s.get('albedo'), fibre=0.1)
    elif recipe == 'card':
        tint = s.get('tint') or [1, 1, 1, 1]
        paper(t, albedo_img=s.get('albedo'), rough=0.8, fibre=0.18)
    elif recipe == 'cloth':
        book_cloth(t, base=kw['base'])
    elif recipe == 'cloth_img':
        book_cloth(t, albedo_img=s.get('albedo'), rough=kw.get('rough', 0.75))
    else:
        recipe(t, **kw)
    m['rm_recipe'] = recipe if isinstance(recipe, str) else recipe.__name__
    return m


def assign(o, new_mat, only_from=None):
    """Point o's slots at new_mat. only_from: original material name to match per slot."""
    orig = json.loads(o['rm_src']) if o.get('rm_src') else [s.material.name if s.material else None for s in o.material_slots]
    if not o.get('rm_src'):
        o['rm_src'] = json.dumps(orig)
    changed = False
    for i, slot in enumerate(o.material_slots):
        if only_from is not None and (i >= len(orig) or orig[i] != only_from):
            continue
        if slot.material is new_mat:
            continue
        if o.data.users > 1 and slot.link != 'OBJECT':
            slot.link = 'OBJECT'          # never retarget mesh data shared with someone else
        slot.material = new_mat
        changed = True
    return changed


def orig_mats(o):
    if o.get('rm_src'):
        return json.loads(o['rm_src'])
    return [s.material.name if s.material else None for s in o.material_slots]


def run():
    rows = []
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    explicit = set()
    for _, (_, _, rule, _) in SPLIT.items():
        explicit.update(rule.get('objects', []))

    # ---- splits first (they read original materials, which stay intact)
    for name, (recipe, kw, rule, note) in SPLIT.items():
        m = get_mat(name)
        build(m, recipe, kw)
        users = []
        for o in meshes:
            if is_skipped(o):
                continue
            if 'objects' in rule:
                if o.name in rule['objects']:
                    assign(o, m)
                    users.append(o.name)
            else:
                if o.name in explicit:
                    continue
                if rule['from'] in orig_mats(o):
                    assign(o, m, only_from=rule['from'])
                    users.append(o.name)
        rows.append((name, note, users))

    # ---- in-place upgrades
    for name, (recipe, kw, note) in IN_PLACE.items():
        m = bpy.data.materials.get(name)
        if m is None or name in SKIP_MATERIALS:
            continue
        # refuse to touch a material still used by a skipped object
        skipped_users = [o.name for o in meshes if is_skipped(o) and any(s.material is m for s in o.material_slots)]
        if skipped_users:
            print(f'[v2_materials] {name}: shared with skipped {skipped_users[:4]} - left alone')
            continue
        build(m, recipe, kw)
        users = [o.name for o in meshes if any(s.material is m for s in o.material_slots)]
        rows.append((name, note, users))

    print('\n[v2_materials] material -> identity -> objects')
    for name, note, users in rows:
        u = ', '.join(users[:6]) + (f' (+{len(users) - 6})' if len(users) > 6 else '')
        print(f'  {name:24s} {note}\n  {"":24s}   -> {u}')
    return rows


run()

if '--' in sys.argv and '--save' in sys.argv[sys.argv.index('--'):]:
    bpy.ops.wm.save_mainfile()
