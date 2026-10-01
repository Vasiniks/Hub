"""v2-look probe: read-only facts and reference renders from the baked sunset scene.

Opens room_bake.blend (the bake's own copy; NEVER saved) and writes, under <out>:
  probe.json            cameras (world matrix, lens, sensor, resolution), colour management,
                        and, per baked object, what drives each material's base colour.
  ref_<cam>.exr/.png    full Cycles render (scene-linear EXR + the AgX/look/exposure PNG)
  prev_<cam>.exr/.png   baked surfaces only, as Emission(albedo x lightmap), others holdout,
                        transparent film (alpha = baked-pixel mask) -- the verify stage's preview
  alb_<cam>.exr         baked surfaces only, Emission(albedo), i.e. what albedo Cycles sees per pixel

Usage (through the lock wrapper):
  blender -b <room_bake.blend> --python scripts/v2look/blender_probe.py -- <out_dir> [--no-render] [--ref-spp 128]
"""
import bpy, os, sys, json, time

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(argv[0])
NO_RENDER = '--no-render' in argv
# --hidden: only the baked-only preview with every non-baked object HIDDEN (not holdout), i.e. what the
# web shows today: the baked surfaces with nothing on them -> prevh_<cam>.exr/.png
HIDDEN = '--hidden' in argv
REF_SPP = int(argv[argv.index('--ref-spp') + 1]) if '--ref-spp' in argv else 128
os.makedirs(OUT, exist_ok=True)
SRC = bpy.data.filepath
CAMS = ['CAM_stand', 'CAM_seat']
BAKE_DIR = os.path.dirname(SRC)
man = json.load(open(os.path.join(BAKE_DIR, 'manifest.json')))
LM_UV = man['uv_layer']
sc = bpy.context.scene


def describe(sock, depth=0):
    if not sock.is_linked:
        v = sock.default_value
        try:
            return {'value': [round(x, 4) for x in v]}
        except TypeError:
            return {'value': round(v, 4)}
    n = sock.links[0].from_node
    d = {'node': n.type, 'name': n.name}
    if n.type == 'TEX_IMAGE' and n.image:
        d['image'] = n.image.name
        d['size'] = list(n.image.size)
        d['colorspace'] = n.image.colorspace_settings.name
    if depth < 3:
        ins = {}
        for i in n.inputs:
            if i.is_linked or i.type in ('RGBA',):
                ins[i.name] = describe(i, depth + 1)
        if ins:
            d['inputs'] = ins
    return d


def surface_of(mat):
    if not mat or not mat.use_nodes:
        return None
    out = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
    if not out or not out.inputs['Surface'].is_linked:
        return None
    return out.inputs['Surface'].links[0].from_node


probe = dict(source=SRC, cameras={}, render=dict(x=sc.render.resolution_x, y=sc.render.resolution_y,
             pct=sc.render.resolution_percentage, dither=sc.render.dither_intensity),
             color_management=dict(view=sc.view_settings.view_transform, look=sc.view_settings.look,
                                   exposure=sc.view_settings.exposure, gamma=sc.view_settings.gamma,
                                   display=sc.display_settings.display_device,
                                   sequencer=sc.sequencer_colorspace_settings.name),
             materials={})
for c in CAMS:
    o = bpy.data.objects[c]
    cd = o.data
    probe['cameras'][c] = dict(matrix_world=[list(r) for r in o.matrix_world], lens=cd.lens, sensor_width=cd.sensor_width,
                               sensor_height=cd.sensor_height, sensor_fit=cd.sensor_fit, shift=[cd.shift_x, cd.shift_y],
                               clip=[cd.clip_start, cd.clip_end], type=cd.type, angle=cd.angle)
baked = {}
for a, spec in man['atlases'].items():
    for n in spec['objects']:
        baked[n] = a
        ob = bpy.data.objects.get(n)
        if not ob:
            continue
        for s in ob.material_slots:
            m = s.material
            if not m or m.name in probe['materials']:
                continue
            surf = surface_of(m)
            d = dict(atlas=a, objects=[], surface=surf.type if surf else None)
            if surf is not None:
                key = 'Base Color' if surf.type == 'BSDF_PRINCIPLED' else 'Color'
                if key in surf.inputs:
                    d['base_color'] = describe(surf.inputs[key])
                for k in ('Roughness', 'Metallic', 'Specular IOR Level', 'Coat Weight', 'Sheen Weight'):
                    if k in surf.inputs:
                        sk = surf.inputs[k]
                        d[k] = describe(sk) if sk.is_linked else round(sk.default_value, 3)
            probe['materials'][m.name] = d
        for s in ob.material_slots:
            if s.material:
                probe['materials'][s.material.name]['objects'].append(n)
if not HIDDEN:
    json.dump(probe, open(os.path.join(OUT, 'probe.json'), 'w'), indent=1)
print('[probe] wrote probe.json', flush=True)
if NO_RENDER:
    sys.exit(0)

# ------------------------------------------------------------------------------------------ renders
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.refresh_devices()
for d in prefs.devices:
    d.use = (d.type == 'CUDA')
sc.render.engine = 'CYCLES'
sc.cycles.device = 'GPU'
sc.render.resolution_percentage = 50
sc.cycles.use_denoising = True
sc.cycles.denoiser = 'OPTIX'


def render(cam, spp, base, transparent, png=True):
    sc.camera = bpy.data.objects[cam]
    sc.cycles.samples = spp
    sc.render.film_transparent = transparent
    t = time.time()
    bpy.ops.render.render()
    rr = bpy.data.images['Render Result']
    ims = sc.render.image_settings
    ims.file_format = 'OPEN_EXR'; ims.color_depth = '32'; ims.color_mode = 'RGBA'; ims.exr_codec = 'ZIP'
    rr.save_render(os.path.join(OUT, base + '.exr'), scene=sc)
    if png:
        ims.file_format = 'PNG'; ims.color_depth = '8'; ims.color_mode = 'RGBA' if transparent else 'RGB'
        rr.save_render(os.path.join(OUT, base + '.png'), scene=sc)
    print(f'[probe] {base} {time.time() - t:.1f}s', flush=True)


if not HIDDEN:
    for cam in CAMS:
        render(cam, REF_SPP, f'ref_{cam}', False)

# preview materials (same construction as v2_bake_sunset.py's verify stage)
lm = {}
for a in man['atlases']:
    im = bpy.data.images.load(os.path.join(BAKE_DIR, f'lightmap_{a}.exr'), check_existing=False)
    im.colorspace_settings.name = 'Linear Rec.709'
    lm[a] = im


def preview_material(mat, lm_img, key, albedo_only):
    mp = mat.copy(); mp.name = f'PV{int(albedo_only)}_{key}_{mat.name}'
    nt = mp.node_tree
    bn = nt.nodes.get('LM_BAKE')
    if bn:
        nt.nodes.remove(bn)
    uvn = nt.nodes.new('ShaderNodeUVMap'); uvn.uv_map = LM_UV
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = lm_img; tex.interpolation = 'Linear'; tex.extension = 'EXTEND'
    nt.links.new(uvn.outputs['UV'], tex.inputs['Vector'])
    for n in list(nt.nodes):
        if n.type not in ('BSDF_PRINCIPLED', 'BSDF_DIFFUSE', 'BSDF_TRANSLUCENT', 'BSDF_SHEEN'):
            continue
        cin = n.inputs['Base Color'] if n.type == 'BSDF_PRINCIPLED' else n.inputs['Color']
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        a_in = [s for s in mix.inputs if s.name == 'A' and s.type == 'RGBA'][0]
        b_in = [s for s in mix.inputs if s.name == 'B' and s.type == 'RGBA'][0]
        if cin.links:
            nt.links.new(cin.links[0].from_socket, a_in)
        else:
            a_in.default_value = cin.default_value
        if albedo_only:
            b_in.default_value = (1, 1, 1, 1)
        else:
            nt.links.new(tex.outputs['Color'], b_in)
        em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 1.0
        nt.links.new([s for s in mix.outputs if s.type == 'RGBA'][0], em.inputs['Color'])
        for l in list(n.outputs[0].links):
            nt.links.new(em.outputs['Emission'], l.to_socket)
        nt.nodes.remove(n)
    return mp


orig = {}
for n in baked:
    ob = bpy.data.objects.get(n)
    if ob:
        orig[n] = [s.material for s in ob.material_slots]
for o in sc.objects:
    if o.type == 'LIGHT':
        o.hide_render = True
    elif o.type in ('MESH', 'CURVE', 'FONT', 'META', 'CURVES', 'VOLUME', 'POINTCLOUD') and o.name not in baked:
        if HIDDEN:
            o.hide_render = True
        else:
            o.is_holdout = True
for nd in sc.world.node_tree.nodes:
    if nd.type == 'BACKGROUND':
        nd.inputs[1].default_value = 0.0

for albedo_only in ((False,) if HIDDEN else (False, True)):
    cache = {}
    for n, mats in orig.items():
        ob = bpy.data.objects[n]
        for s, m in zip(ob.material_slots, mats):
            if m:
                k = m.name
                if k not in cache:
                    cache[k] = preview_material(m, lm[baked[n]], baked[n], albedo_only)
                s.material = cache[k]
    for cam in CAMS:
        kind = 'prevh' if HIDDEN else ('alb' if albedo_only else 'prev')
        render(cam, 32 if not albedo_only else 8, f'{kind}_{cam}', True, png=not albedo_only)
print('[probe] done; nothing saved to', SRC, flush=True)
