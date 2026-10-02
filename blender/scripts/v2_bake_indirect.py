"""
Indirect-only lightmaps for hybrid rendering: the runtime lights SUN_main and LAMP_disk live (shadows,
PBR), and the bake keeps everything else.

    L_indirect = L_full - L_direct(SUN_main + LAMP_disk)

L_full is pass A, the shipped sunset bake (v2_bake_sunset.py `bake`: Cycles DIFFUSE, direct + indirect,
colour off, 1024 spp, seed 0). L_direct is pass B: the same bake, same file, same samples, but DIRECT only,
with every light except SUN_main and LAMP_disk off, the world at strength 0 and every emission zeroed.
So the indirect map still holds the sky through the window, the screens, PC RGB, LEDs, the lamp's glowing
diffuser, the street lights, and every bounce of the sun and the lamp.

    blender -b --python blender/scripts/v2_bake_indirect.py -- <stage> [options]

    stage:  (several joined with +, e.g. darkcheck+bake+combine)
            check      prepared copy's lightmap UVs vs blender/bake/sunset/<atlas>.glb, pass A's raw bake present,
                       render settings as recorded for pass A
            darkcheck  every light off, world 0, emission zeroed: a small DIRECT+INDIRECT bake must be exactly 0
                       (proves the isolation removes every other source)
            bake       pass B per atlas -> tmp/bake_sunset/raw_direct_<atlas>.exr   (--full also re-bakes pass A raw)
            combine    denoise B like A; indirect = A - B; write lightmap_<atlas>.{direct,indirect}.exr,
                       lightmap_<atlas>.indirect.rgbm.png, preview; sanity check B + indirect vs A
            materials  roughness / metallic / specular / coat / sheen per material (EMIT bakes of the Principled
                       inputs in the lightmap UV, texel means) -> manifest `materials`
            verify     Cycles from CAM_stand and CAM_seat: (a) full, (b) direct sun + lamp only, (c) indirect bake
                       preview -> .claude/briefs/report-room-indirect/
    options: --samples N (1024)  --only atlas[,atlas]  --method raw|sub (raw)  --res-scale F (1.0, darkcheck 0.125)

Reads blender/bake/sunset/room_bake.blend (prepared by v2_bake_sunset.py `prepare`) and NEVER saves it: the
lightmap UVs that the shipped GLBs and albedo atlases use stay as they are. Writes only into blender/bake/sunset/
(lightmap_*.direct/indirect.*, manifest.json) and tmp/.
"""
import bpy, sys, os, json, time, math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_bake_sunset as S  # noqa: E402  (guarded main)

OUT, TMP, LM_UV, BAKE_NODE = S.OUT, S.TMP, S.LM_UV, S.BAKE_NODE
LIVE = ('SUN_main', 'LAMP_disk')
REPORT = os.path.join(S.REPO, '.claude', 'briefs', 'report-room-indirect')
PUB = os.path.join(S.REPO, 'public', 'assets', 'v2', 'room')
# inputs that make a node emit light
EMISSIVE_INPUTS = {'EMISSION': ('Strength',), 'BSDF_PRINCIPLED': ('Emission Strength',),
                   'PRINCIPLED_VOLUME': ('Emission Strength', 'Blackbody Intensity')}
PARAMS = ('Roughness', 'Metallic', 'IOR', 'Specular IOR Level', 'Coat Weight', 'Coat Roughness', 'Sheen Weight')


def log(*a):
    print('[indirect]', *a, flush=True)


def args():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = dict(stage=a[0] if a else 'check', samples=1024, only=None, method='raw', res_scale=None, full=False,
             spp=128, prev_spp=32, pct=50)
    i = 1
    while i < len(a):
        k = a[i].lstrip('-').replace('-', '_')
        if k == 'full':
            o['full'] = True; i += 1; continue
        v = a[i + 1]; i += 2
        o[k] = v if k in ('only', 'method') else (float(v) if k == 'res_scale' else int(v))
    if o['only']:
        o['only'] = o['only'].split(',')
    return o


def atlases(opt):
    return [a for a in S.ATLASES if not opt['only'] or a in opt['only']]


def res_of(name, scale=None):
    return max(64, int(round(S.ATLASES[name]['res'] * (scale or 1.0))))


def objs_of(name):
    objs = [bpy.data.objects[n] for n in S.ATLASES[name]['objects']]
    for o in objs:
        S.unhide(o)
    return objs


def load_arr(path):
    im = bpy.data.images.load(path, check_existing=False)
    im.colorspace_settings.name = 'Linear Rec.709'
    a = S.img_array(im)[..., :3].copy()
    bpy.data.images.remove(im)
    return a


def denoise_arr(a, res, out_path):
    img = bpy.data.images.new('LM_dn_in', res, res, alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Linear Rec.709'
    S.set_pixels(img, a)
    S.denoise(img, res, out_path)
    bpy.data.images.remove(img)
    return load_arr(out_path)


# ---------------------------------------------------------------------------------------------
# isolation: only the live lights
# ---------------------------------------------------------------------------------------------
def isolate(sc, keep):
    """Every light not in `keep` off, world black, every emission zeroed (materials and node groups).
    Session only: the file is never saved."""
    off = []
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and o.name not in keep and not o.hide_render:
            o.hide_render = True
            off.append(o.name)
    missing = [k for k in keep if k not in bpy.data.objects or bpy.data.objects[k].hide_render]
    assert not missing, f'live lights missing or not rendering: {missing}'
    wnt = sc.world.node_tree
    for n in wnt.nodes:
        if n.type == 'BACKGROUND':
            for l in list(n.inputs['Strength'].links):
                wnt.links.remove(l)
            n.inputs['Strength'].default_value = 0.0
        if n.type == 'OUTPUT_WORLD':
            for s in n.inputs:
                for l in list(s.links):
                    wnt.links.remove(l)
    zeroed = []
    trees = [(m.name, m.node_tree) for m in bpy.data.materials if m.node_tree] + \
            [('group:' + g.name, g) for g in bpy.data.node_groups if g.bl_idname == 'ShaderNodeTree']
    for owner, nt in trees:
        for n in nt.nodes:
            for name in EMISSIVE_INPUTS.get(n.type, ()):
                s = n.inputs.get(name)
                if s is None:
                    continue
                was = s.is_linked or (s.default_value != 0.0)
                for l in list(s.links):
                    nt.links.remove(l)
                s.default_value = 0.0
                if was:
                    zeroed.append(f'{owner}/{n.name}.{name}')
        ad = getattr(nt, 'animation_data', None)
        if ad and ad.drivers:   # a driver would put the emission back on frame change
            for fc in list(ad.drivers):
                if any(k in fc.data_path for k in ('Strength', 'Blackbody')) or 'inputs[' in fc.data_path:
                    nt.driver_remove(fc.data_path)
                    zeroed.append(f'{owner} driver {fc.data_path} removed')
    log('isolated: lights off', off, '| emission zeroed', len(zeroed))
    return dict(lights_off=off, emission_zeroed=zeroed, world='strength 0, output unlinked')


# ---------------------------------------------------------------------------------------------
# baking
# ---------------------------------------------------------------------------------------------
def bake_raw(sc, name, res, passes, path, samples):
    objs = objs_of(name)
    iname = 'LMI_' + name
    if iname in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[iname])
    img = bpy.data.images.new(iname, res, res, alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Linear Rec.709'
    img.generated_color = (0, 0, 0, 1)
    mats = {s.material for o in objs for s in o.material_slots if s.material}
    for m in mats:
        n = S.ensure_bake_node(m)
        n.image = img
        n.interpolation = 'Linear'
        for x in m.node_tree.nodes:
            x.select = False
        n.select = True
        m.node_tree.nodes.active = n
    S.select_only(objs)
    sc.cycles.samples = samples
    t = time.time()
    bpy.ops.object.bake(type='DIFFUSE', pass_filter=set(passes), margin=S.BAKE_MARGIN_PX,
                        margin_type='ADJACENT_FACES', use_clear=True, target='IMAGE_TEXTURES', uv_layer=LM_UV)
    dt = round(time.time() - t, 1)
    a = S.img_array(img)[..., :3].copy()
    if path:
        S.exr_settings(sc.render.image_settings, '32')
        img.save_render(path, scene=sc)
    bpy.data.images.remove(img)
    log('baked', name, sorted(passes), res, 'px', samples, 'spp', dt, 's', 'mean', float(a.mean()), 'max', float(a.max()))
    return a, dt


def bake_setup(sc):
    S.gpu(sc)
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.use_denoising = False
    bk = sc.render.bake
    bk.use_pass_color = False
    bk.margin = S.BAKE_MARGIN_PX; bk.margin_type = 'ADJACENT_FACES'; bk.use_clear = True; bk.target = 'IMAGE_TEXTURES'
    bs = S.load_manifest().get('bake_settings', {})
    now = dict(max_bounces=sc.cycles.max_bounces, diffuse_bounces=sc.cycles.diffuse_bounces,
               glossy_bounces=sc.cycles.glossy_bounces, sample_clamp_indirect=sc.cycles.sample_clamp_indirect)
    for k, v in now.items():
        assert abs(bs.get(k, v) - v) < 1e-6, f'{k}: file {v} != pass A {bs.get(k)}'
    return dict(now, seed=sc.cycles.seed, sample_clamp_direct=sc.cycles.sample_clamp_direct)


def stage_check(opt, man):
    S.open_copy()
    sc = bpy.context.scene
    settings = bake_setup(sc)
    res = {}
    for name in atlases(opt):
        objs = objs_of(name)
        src = S.uv_signature(objs, LM_UV)
        glb = os.path.join(OUT, f'{name}.glb')
        chk = bpy.data.scenes.new('LM_check')
        before = set(bpy.data.objects)
        with bpy.context.temp_override(scene=chk, view_layer=chk.view_layers[0]):
            bpy.ops.import_scene.gltf(filepath=glb)
        new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        imp = S.uv_signature(new, 1)
        for o in [o for o in bpy.data.objects if o not in before]:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.scenes.remove(chk)
        match = len(imp & src) / max(1, len(imp))
        raw = os.path.join(TMP, f'raw_{name}.exr')
        assert os.path.exists(raw), f'pass A raw bake missing: {raw} (re-run `bake --full`)'
        a_raw = load_arr(raw)
        a_dn = load_arr(os.path.join(OUT, f'lightmap_{name}.exr'))
        lit = a_raw.max(axis=2) > 1e-6
        level = float(a_dn[lit].mean() / a_raw[lit].mean())
        res[name] = dict(uv_match_vs_glb=round(match, 4), loops_glb=len(imp), loops_blend=len(src),
                         raw_A=os.path.relpath(raw, S.REPO).replace('\\', '/'), raw_A_res=a_raw.shape[0],
                         denoised_over_raw_level=round(level, 4))
        log('check', name, res[name])
        assert match > 0.99, f'{name}: lightmap UVs of room_bake.blend do not match {glb}'
        assert a_raw.shape[0] == S.ATLASES[name]['res'] and abs(level - 1) < 0.05
    man.update(S.light_params(sc))   # lights with the runtime fields (shadow softness, three.js coordinates)
    man.setdefault('indirect_bake', {})['check'] = dict(atlases=res, render_settings=settings,
                                                        source=os.path.relpath(S.COPY, S.REPO).replace('\\', '/'))
    S.save_manifest(man)


def stage_darkcheck(opt, man):
    S.open_copy()
    sc = bpy.context.scene
    bake_setup(sc)
    iso = isolate(sc, keep=())
    out = {}
    for name in atlases(opt):
        r = res_of(name, opt['res_scale'] or 0.125)
        a, _ = bake_raw(sc, name, r, {'DIRECT', 'INDIRECT'}, None, 16)
        out[name] = dict(res=r, spp=16, max=float(a.max()), nonzero_texels=int((a.max(axis=2) > 0).sum()))
        log('darkcheck', name, out[name])
    ok = all(v['max'] == 0.0 for v in out.values())
    man.setdefault('indirect_bake', {})['darkcheck'] = dict(
        ok=ok, atlases=out, isolation=dict(lights_off=iso['lights_off'], emission_zeroed=len(iso['emission_zeroed']),
                                           world=iso['world']),
        meaning='all lights off, world 0, emission zeroed: DIRECT+INDIRECT bake must be exactly 0, '
                'so pass B (same isolation with SUN_main and LAMP_disk on) holds those two lights only')
    S.save_manifest(man)
    assert ok, 'light leaks with everything off: ' + json.dumps(out)


def stage_bake(opt, man):
    S.open_copy()
    sc = bpy.context.scene
    bake_setup(sc)
    os.makedirs(TMP, exist_ok=True)
    rec = man.setdefault('indirect_bake', {}).setdefault('pass_b', {})
    if opt['full']:   # pass A again, raw (normally the shipped bake's raw EXR is reused)
        for name in atlases(opt):
            _, dt = bake_raw(sc, name, res_of(name), {'DIRECT', 'INDIRECT'}, os.path.join(TMP, f'raw_{name}.exr'),
                             opt['samples'])
            man['indirect_bake'].setdefault('pass_a_rebake', {})[name] = dict(seconds=dt, samples=opt['samples'])
    iso = isolate(sc, keep=LIVE)
    for name in atlases(opt):
        _, dt = bake_raw(sc, name, res_of(name), {'DIRECT'}, os.path.join(TMP, f'raw_direct_{name}.exr'),
                         opt['samples'])
        rec[name] = dict(seconds=dt, samples=opt['samples'], res=res_of(name))
    man['indirect_bake']['pass_b_settings'] = dict(
        type='DIFFUSE', passes=['DIRECT'], color=False, samples=opt['samples'], seed=sc.cycles.seed,
        adaptive_sampling=False, lights_on=list(LIVE), lights_off=iso['lights_off'],
        emission_zeroed=len(iso['emission_zeroed']), world='strength 0', margin_px=S.BAKE_MARGIN_PX)
    S.save_manifest(man)


def err_stats(e, ref, valid):
    """e, ref: (h, w, 3) linear; stats over valid texels (all channels)."""
    ev, rv = np.abs(e[valid]), ref[valid]
    m = float(rv.mean())
    rel = ev / np.maximum(rv, 0.05 * m)
    return dict(mean_abs=round(float(ev.mean()), 6), mean_abs_rel_to_mean=round(float(ev.mean()) / m, 5),
                p99_abs=round(float(np.percentile(ev, 99)), 5), p99_rel=round(float(np.percentile(rel, 99)), 4),
                bias_rel=round(float(e[valid].mean()) / m, 5))


def stage_combine(opt, man):
    S.open_copy()
    sc = bpy.context.scene
    ib = man.setdefault('indirect_bake', {})
    for name in atlases(opt):
        t0 = time.time()
        res = res_of(name)
        objs = objs_of(name)
        labels = S.uv_island_labels(objs, res)
        cov = labels >= 0
        a_raw = load_arr(os.path.join(TMP, f'raw_{name}.exr'))
        a_dn = load_arr(os.path.join(OUT, f'lightmap_{name}.exr'))
        b_raw = load_arr(os.path.join(TMP, f'raw_direct_{name}.exr'))
        valid = cov & (a_raw.max(axis=2) > 1e-6)    # pass A's mask: buried texels are refilled
        # pass B, denoised exactly like pass A
        b_out = os.path.join(OUT, f'lightmap_{name}.direct.exr')
        b_dn = denoise_arr(S.dilate(b_raw, valid, S.DILATE_PX, labels), res, b_out)
        b_dn = S.save_exr(S.dilate(np.clip(b_dn, 0, None), valid, S.DILATE_PX, labels), b_out, sc)
        # 'sub': difference of the two denoised bakes
        d = a_dn - b_dn
        neg_sub = float((d[valid] < 0).mean())
        i_sub = S.dilate(np.clip(d, 0, None), valid, S.DILATE_PX, labels)
        # 'raw': difference of the raw bakes, one denoise (the indirect field is smooth: no sun edges to blur)
        d_raw = a_raw - b_raw
        neg_raw = float((d_raw[valid] < 0).mean())
        neg_raw_amt = float(np.clip(-d_raw[valid], 0, None).mean() / max(float(a_raw[valid].mean()), 1e-9))
        tmp_i = os.path.join(TMP, f'indirect_raw_dn_{name}.exr')
        i_raw = denoise_arr(S.dilate(np.clip(d_raw, 0, None), valid, S.DILATE_PX, labels), res, tmp_i)
        i_raw = S.dilate(np.clip(i_raw, 0, None), valid, S.DILATE_PX, labels)
        S.save_exr(i_sub, os.path.join(TMP, f'indirect_sub_{name}.exr'), sc)
        cand = dict(raw=i_raw, sub=i_sub)
        sanity = {k: err_stats(b_dn + v - a_dn, a_dn, valid) for k, v in cand.items()}
        # the two estimates are independent where it matters (one denoise of the difference vs the difference
        # of two denoises): how far apart are they, relative to the indirect itself
        cross = err_stats(i_raw - i_sub, i_sub, valid)
        cand_rgbm = {k: S.rgbm_png(v, os.path.join(TMP, f'indirect_{k}_{name}.rgbm.png'))['range_sqrt']
                     for k, v in cand.items()}
        noise = err_stats(a_raw - a_dn, a_dn, valid)                    # what the denoiser removed from pass A
        noise_b = err_stats(b_raw - b_dn, a_dn, valid)
        ind = cand[opt['method']]
        out = os.path.join(OUT, f'lightmap_{name}.indirect.exr')
        ind = S.save_exr(ind, out, sc)
        p99 = S.preview_png(out, os.path.join(OUT, f'lightmap_{name}.indirect_preview.png'))
        S.preview_png(b_out, os.path.join(OUT, f'lightmap_{name}.direct_preview.png'))
        rg = S.rgbm_png(ind, os.path.join(OUT, f'lightmap_{name}.indirect.rgbm.png'))
        mA, mB, mI = float(a_dn[valid].mean()), float(b_dn[valid].mean()), float(ind[valid].mean())
        at = man['atlases'][name]
        at['indirect'] = dict(
            image=f'lightmap_{name}.indirect.exr', preview=f'lightmap_{name}.indirect_preview.png',
            direct_image=f'lightmap_{name}.direct.exr', direct_preview=f'lightmap_{name}.direct_preview.png',
            web=dict(file=f'lightmap_{name}.indirect.rgbm.png', encoding='RGBM of sqrt(L), 8-bit RGBA PNG, linear data',
                     decode='L = (rgb * a * range_sqrt)^2', **rg),
            method=opt['method'], mean_linear=round(mI, 5), max_linear=round(float(ind.max()), 3),
            preview_p99_linear=round(p99, 4),
            share_of_full=dict(direct_sun_lamp=round(mB / mA, 4), indirect=round(mI / mA, 4)),
            sanity_B_plus_indirect_vs_A=sanity[opt['method']], sanity_other_method={
                k: v for k, v in sanity.items() if k != opt['method']},
            raw_vs_sub_rel_to_indirect=cross, tmp_rgbm_range_sqrt=cand_rgbm,
            noise_floor_A_raw_vs_denoised=noise, noise_B_raw_vs_denoised=noise_b,
            negative_fraction=dict(raw_difference=round(neg_raw, 4), raw_negative_mass_rel=round(neg_raw_amt, 5),
                                   denoised_difference=round(neg_sub, 4)),
            seconds=round(time.time() - t0, 1))
        log('combine', name, json.dumps(at['indirect']))
        S.save_manifest(man)
    ib['combine'] = dict(method=opt['method'], methods=dict(
        raw='indirect = OIDN(clamp0(A_raw - B_raw)), gutters/buried refilled per island before and after',
        sub='indirect = clamp0(OIDN(A_raw) - OIDN(B_raw)), refilled per island'),
        sanity_meaning='e = B_denoised + indirect - A_denoised (the shipped full master) over valid texels; '
                       'mean_abs_rel_to_mean = mean|e| / mean(A); p99_rel = 99th pct of |e| / max(A, 5% of mean A)')
    S.save_manifest(man)


# ---------------------------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------------------------
def uv_material_labels(objs, res):
    """(res, res) int32 in Blender row order: index into the returned material-name list for every texel
    whose centre lies in a lightmap-UV triangle, -1 elsewhere."""
    lab = np.full((res, res), -1, np.int32)
    names = []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        lt = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get('loops', lt)
        mi = np.empty(nt, np.int32); me.loop_triangles.foreach_get('material_index', mi)
        uv = np.empty(len(me.loops) * 2, np.float32); me.uv_layers[LM_UV].data.foreach_get('uv', uv)
        ev.to_mesh_clear()
        slot = []
        for s in o.material_slots:
            n = s.material.name if s.material else ''
            if n not in names:
                names.append(n)
            slot.append(names.index(n))
        T = uv.reshape(-1, 2)[lt.reshape(-1, 3)].astype(np.float64) * res - 0.5
        lo = np.clip(np.ceil(T.min(1) - 1e-9).astype(np.int64), 0, res - 1)
        hi = np.clip(np.floor(T.max(1) + 1e-9).astype(np.int64), 0, res - 1)
        for k in range(nt):
            (x0, y0), (x1, y1) = lo[k], hi[k]
            if x1 < x0 or y1 < y0 or not slot:
                continue
            a, b, c = T[k]
            area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(area) < 1e-12:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            sg = 1.0 if area > 0 else -1.0
            w0 = sg * ((b[0] - X) * (c[1] - Y) - (b[1] - Y) * (c[0] - X))
            w1 = sg * ((c[0] - X) * (a[1] - Y) - (c[1] - Y) * (a[0] - X))
            w2 = sg * ((a[0] - X) * (b[1] - Y) - (a[1] - Y) * (b[0] - X))
            inside = (w0 >= -1e-7) & (w1 >= -1e-7) & (w2 >= -1e-7)
            lab[y0:y1 + 1, x0:x1 + 1][inside] = slot[min(int(mi[k]), len(slot) - 1)]
    return lab, names


def principled(m):
    out = m.node_tree.get_output_node('CYCLES')
    ps = [n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
    return out, (ps[0] if ps else None), len(ps)


def stage_materials(opt, man):
    S.open_copy()
    sc = bpy.context.scene
    S.gpu(sc)
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.use_denoising = False
    sc.render.bake.use_clear = True
    blender_mats = {}
    for name in atlases(opt):
        objs = objs_of(name)
        res = max(256, S.ATLASES[name]['res'] // 2)
        labels, names = uv_material_labels(objs, res)
        mats = [bpy.data.materials[n] for n in names if n]
        info = {m.name: principled(m) for m in mats}
        surf = {m.name: (info[m.name][0].inputs['Surface'].links[0].from_socket
                         if info[m.name][0].inputs['Surface'].links else None) for m in mats}
        vals = {m.name: {} for m in mats}
        for prm in PARAMS:
            linked = [m for m in mats if info[m.name][1] and info[m.name][1].inputs[prm].is_linked]
            for m in mats:
                p = info[m.name][1]
                if p is not None and not p.inputs[prm].is_linked:
                    vals[m.name][prm] = dict(value=round(float(p.inputs[prm].default_value), 4), source='scalar')
            if not linked:
                continue
            img = bpy.data.images.new('LM_param', res, res, alpha=False, float_buffer=True)
            img.colorspace_settings.name = 'Linear Rec.709'
            added = []
            for m in mats:
                nt = m.node_tree
                out, p, _ = info[m.name]
                em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 1.0
                if p is not None and p.inputs[prm].is_linked:
                    nt.links.new(p.inputs[prm].links[0].from_socket, em.inputs['Color'])
                else:
                    v = float(p.inputs[prm].default_value) if p is not None else 0.0
                    em.inputs['Color'].default_value = (v, v, v, 1)
                nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
                n = S.ensure_bake_node(m); n.image = img
                for x in nt.nodes:
                    x.select = False
                n.select = True; nt.nodes.active = n
                added.append((m, em))
            S.select_only(objs)
            sc.cycles.samples = 16
            bpy.ops.object.bake(type='EMIT', margin=0, use_clear=True, target='IMAGE_TEXTURES', uv_layer=LM_UV)
            a = S.img_array(img)[..., 0].copy()
            bpy.data.images.remove(img)
            for m, em in added:
                nt = m.node_tree
                nt.nodes.remove(em)
                if surf[m.name] is not None:
                    nt.links.new(surf[m.name], info[m.name][0].inputs['Surface'])
            for m in linked:
                px = a[labels == names.index(m.name)]
                if px.size:
                    vals[m.name][prm] = dict(value=round(float(px.mean()), 4), source='texture-driven, mean over texels',
                                             p5=round(float(np.percentile(px, 5)), 4),
                                             p95=round(float(np.percentile(px, 95)), 4), texels=int(px.size))
            log('param', name, prm, {m.name: vals[m.name].get(prm, {}).get('value') for m in linked})
        for m in mats:
            p = info[m.name][1]
            texels = int((labels == names.index(m.name)).sum())
            d = dict(atlas=name, texels=texels, principled_nodes=info[m.name][2], params=vals[m.name])
            if p is not None:
                d['specular_tint'] = [round(x, 4) for x in p.inputs['Specular Tint'].default_value[:3]]
                d['specular_tint_linked'] = p.inputs['Specular Tint'].is_linked
            blender_mats[m.name] = d
    man['materials_blender'] = blender_mats
    # per shipped GLB material: optimize-glb merges look-alike materials (no textures in the GLB), so map
    # each public material to the Blender materials of its primitives (paired by node name)
    shipped = {}
    for name in atlases(opt):
        src = S.glb_json(os.path.join(OUT, f'{name}.glb'))
        pub = S.glb_json(os.path.join(PUB, f'{name}.glb'))

        def by_node(j):
            r = {}
            for nd in j['nodes']:
                if 'mesh' in nd:
                    r[nd['name']] = [j['materials'][p['material']]['name'] if 'material' in p else None
                                     for p in j['meshes'][nd['mesh']]['primitives']]
            return r
        sn, pn = by_node(src), by_node(pub)
        cover = {}
        for node, pm in pn.items():
            sm = sn.get(node)
            assert sm is not None and len(sm) == len(pm), f'{name}: node {node} differs between bake and public GLB'
            for p, s in zip(pm, sm):
                cover.setdefault(p, set()).add(s)
        out = {}
        for gm, bms in sorted(cover.items()):
            bms = sorted(bms)
            agg = {}
            for prm in PARAMS:
                w = [(blender_mats[b]['params'][prm]['value'], max(1, blender_mats[b]['texels'])) for b in bms
                     if prm in blender_mats.get(b, {}).get('params', {})]
                if w:
                    agg[prm] = round(sum(v * n for v, n in w) / sum(n for _, n in w), 4)
            srcs = {blender_mats[b]['params'].get('Roughness', {}).get('source') for b in bms if b in blender_mats}
            lvl = agg.get('Specular IOR Level', 0.5); ior = agg.get('IOR', 1.5)
            f0 = ((ior - 1) / (ior + 1)) ** 2
            out[gm] = dict(
                blender_materials=bms,
                roughness=agg.get('Roughness'), metallic=agg.get('Metallic'), ior=ior, specular_ior_level=lvl,
                coat_weight=agg.get('Coat Weight'), coat_roughness=agg.get('Coat Roughness'),
                sheen_weight=agg.get('Sheen Weight'),
                roughness_source=' / '.join(sorted(s for s in srcs if s)),
                three=dict(roughness=agg.get('Roughness'), metalness=agg.get('Metallic'), ior=ior,
                           specularIntensity=round(2 * lvl, 4), clearcoat=agg.get('Coat Weight'),
                           clearcoatRoughness=agg.get('Coat Roughness'), sheen=agg.get('Sheen Weight'),
                           f0=round(min(1.0, f0 * 2 * lvl), 4)))
        shipped[name] = out
        man['atlases'][name]['materials'] = out
    man['materials_note'] = (
        'atlases.<a>.materials: per material of the shipped GLB (public/assets/v2/room/<a>.glb), the Principled '
        'inputs as Blender has them. Texture/procedural-driven inputs are EMIT-baked in the lightmap UV and '
        'averaged over the material\'s texels (p5/p95 in materials_blender); several Blender materials merged into '
        'one GLB material are texel-weighted. three: MeshPhysicalMaterial equivalents (specularIntensity = 2 x '
        'Specular IOR Level, so 0.5 -> 1.0, F0 = ((ior-1)/(ior+1))^2 x 2 x level).')
    S.save_manifest(man)
    log('materials', json.dumps(shipped))


# ---------------------------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------------------------
def stage_verify(opt, man):
    S.open_copy()
    sc = bpy.context.scene
    S.gpu(sc)
    os.makedirs(REPORT, exist_ok=True)
    cams = ['CAM_stand', 'CAM_seat']
    times = {}
    shots = {}
    for cam in cams:      # (a) full
        p = os.path.join(REPORT, f'{cam}_a_full.png')
        times[f'a_{cam}'] = S.render_to(sc, cam, opt['spp'], opt['pct'], p)
        shots.setdefault(cam, {})['a'] = p
    iso = isolate(sc, keep=LIVE)
    bounces = dict(max=sc.cycles.max_bounces)
    sc.cycles.max_bounces = 0          # camera ray -> surface -> SUN_main / LAMP_disk, nothing else
    for cam in cams:      # (b) direct sun + lamp
        p = os.path.join(REPORT, f'{cam}_b_direct_sun_lamp.png')
        times[f'b_{cam}'] = S.render_to(sc, cam, opt['spp'], opt['pct'], p)
        shots[cam]['b'] = p
    sc.cycles.max_bounces = bounces['max']
    # (c) indirect bake preview: baked objects as Emission(albedo x indirect), others holdout, no lights
    baked = {}
    for name in S.ATLASES:
        im = bpy.data.images.load(os.path.join(OUT, f'lightmap_{name}.indirect.exr'), check_existing=False)
        im.colorspace_settings.name = 'Linear Rec.709'
        for n in S.ATLASES[name]['objects']:
            baked[n] = (name, im)
    cache = {}
    for n, (name, im) in baked.items():
        o = bpy.data.objects[n]
        for s in o.material_slots:
            if s.material:
                k = (name, s.material.name)
                if k not in cache:
                    cache[k] = S.preview_material(s.material, im, 'ind_' + name)
                s.material = cache[k]
    for o in sc.objects:
        if o.type == 'LIGHT':
            o.hide_render = True
        elif o.type in ('MESH', 'CURVE', 'FONT', 'META', 'CURVES', 'VOLUME', 'POINTCLOUD') and o.name not in baked:
            o.is_holdout = True
    lum = np.array([0.2126, 0.7152, 0.0722])
    stats = {}
    for cam in cams:
        p = os.path.join(TMP, f'ind_prev_{cam}.png')
        times[f'c_{cam}'] = S.render_to(sc, cam, opt['prev_spp'], opt['pct'], p, transparent=True)
        v = S.load_png_arr(p)
        r = S.load_png_arr(shots[cam]['a'])[..., :3]
        al = v[..., 3:4]
        grey = (r @ lum)[..., None] * 0.3
        comp = v[..., :3] * al + grey * (1 - al)
        cp = os.path.join(REPORT, f'{cam}_c_indirect_bake.png')
        S.write_png(comp, cp)
        shots[cam]['c'] = cp
        b = S.load_png_arr(shots[cam]['b'])[..., :3]
        m = al[..., 0] > 0.99
        stats[cam] = dict(baked_pixel_fraction=round(float(m.mean()), 3),
                          mean_display_luma=dict(full=round(float((r @ lum)[m].mean()), 4),
                                                 direct_sun_lamp=round(float((b @ lum)[m].mean()), 4),
                                                 indirect_bake=round(float((v[..., :3] @ lum)[m].mean()), 4)))
        # montage a | b | c at half size
        h, w = r.shape[:2]
        sep = np.ones((h // 2, 4, 3), np.float32)
        half = lambda x: x[:h // 2 * 2, :w // 2 * 2].reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3))
        S.write_png(np.concatenate([half(r), sep, half(b), sep, half(comp)], axis=1),
                    os.path.join(REPORT, f'{cam}_montage_a_b_c.png'))
        log('verify', cam, stats[cam])
    man.setdefault('indirect_bake', {})['verify'] = dict(
        cameras=stats, render_seconds=times, spp=opt['spp'], preview_spp=opt['prev_spp'], pct=opt['pct'],
        files=sorted(os.path.relpath(p, S.REPO).replace('\\', '/') for c in shots.values() for p in c.values()),
        method='(a) full Cycles render of room_bake.blend; (b) Cycles with only SUN_main + LAMP_disk, world 0, '
               'emission zeroed, max bounces 0 (direct diffuse + specular: what the live lights add); (c) baked '
               'objects as Emission(albedo x indirect lightmap), no lights, other objects holdout (shown as 30% grey '
               'of (a)). All through the scene view: AgX, Medium High Contrast, +0.45 EV.',
        isolation_lights_off=iso['lights_off'])
    S.save_manifest(man)


def main():
    opt = args()
    os.makedirs(TMP, exist_ok=True)
    for st in opt['stage'].split('+'):     # e.g. darkcheck+bake: several stages under one Blender lock
        man = S.load_manifest()
        log('=== stage', st)
        t = time.time()
        globals()['stage_' + st](opt, man)
        man.setdefault('indirect_bake', {}).setdefault('stage_seconds', {})[st] = round(time.time() - t, 1)
        S.save_manifest(man)
        log('DONE', st, round(time.time() - t, 1), 's')


main()
