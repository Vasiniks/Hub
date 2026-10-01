"""v2-look: Blender's own display transform (AgX + look "AgX - Medium High Contrast", sRGB display) as a
3D LUT for the web grade, validated against Blender itself.

Runs inside Blender (for PyOpenColorIO, OpenImageIO and Blender's bundled config), no .blend needed:
  blender -b --factory-startup --python scripts/v2look/blender_lut.py -- <work_dir> <lut_out.bin>

1. Builds the transform the way Blender's colour management does (LookTransform into the look's
   process space, then DisplayViewTransform with looks bypassed) from
   <blender>/datafiles/colormanagement/config.ocio.
2. Checks it against Blender's own "save as render" of a float test image (view AgX, look MHC,
   exposure 0 and 0.45, dither 0): this is what decides that exposure is a scene-linear multiply
   applied before the look.
3. Samples it on an N^3 grid over a per-channel log2 shaper of linear Rec.709 and measures the
   trilinear-interpolation error on real frame pixels (the reference renders in <work_dir>).
4. Writes the chosen LUT (float16 RGB, red fastest) and the shaper constants, and dumps the
   reference EXRs to .npy for analysis outside Blender.
"""
import bpy, os, sys, json
import numpy as np
import PyOpenColorIO as OCIO
import OpenImageIO as oiio

argv = sys.argv[sys.argv.index('--') + 1:]
WORK = os.path.abspath(argv[0])
LUT_OUT = os.path.abspath(argv[1])
CFG = os.path.join(os.path.dirname(bpy.app.binary_path), f'{bpy.app.version[0]}.{bpy.app.version[1]}',
                   'datafiles', 'colormanagement', 'config.ocio')
LOOK = 'AgX - Medium High Contrast'
EXPOSURE = 0.45
report = dict(config=CFG)

cfg = OCIO.Config.CreateFromFile(CFG)
scene_linear = cfg.getColorSpace(OCIO.ROLE_SCENE_LINEAR).getName()
look = cfg.getLook(LOOK)
report.update(scene_linear=scene_linear, look=LOOK, look_process_space=look.getProcessSpace(),
              look_transform=str(look.getTransform()))


def processor(look_name):
    g = OCIO.GroupTransform()
    src = scene_linear
    if look_name:
        dst = cfg.getLook(look_name).getProcessSpace()  # what OCIO GetLooksResultColorSpace returns for one look
        g.appendTransform(OCIO.LookTransform(src=src, dst=dst, looks=look_name))
        src = dst
    g.appendTransform(OCIO.DisplayViewTransform(src=src, display='sRGB', view='AgX', looksBypass=bool(look_name)))
    return cfg.getProcessor(g).getDefaultCPUProcessor()


P = processor(LOOK)
P0 = processor(None)


def apply(proc, x):
    a = np.ascontiguousarray(x.reshape(-1, 3).astype(np.float32))
    proc.applyRGB(a)
    return a.reshape(x.shape)


def read(path):
    b = oiio.ImageBuf(path)
    return np.array(b.get_pixels(oiio.FLOAT), dtype=np.float32)  # top row first, raw stored values


# ---------------------------------------------------------------- 2. validate against Blender itself
rng = np.random.default_rng(7)
grey = 2.0 ** np.linspace(-12, 8, 1024)
cols = 2.0 ** rng.uniform(-10, 5, (3072, 3))
test = np.concatenate([np.repeat(grey[:, None], 3, 1), cols]).astype(np.float32)   # 4096 = 64x64
W = 64
sc = bpy.context.scene
sc.render.dither_intensity = 0.0
sc.display_settings.display_device = 'sRGB'
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = LOOK
sc.view_settings.gamma = 1.0
ims = sc.render.image_settings
ims.file_format = 'PNG'; ims.color_depth = '16'; ims.color_mode = 'RGB'
img = bpy.data.images.new('v2look_test', W, W, alpha=True, float_buffer=True)
img.colorspace_settings.name = scene_linear
px = np.concatenate([test, np.ones((W * W, 1), np.float32)], 1)
img.pixels.foreach_set(px.ravel())
val = {}
for ev, lk in ((0.0, LOOK), (EXPOSURE, LOOK), (0.0, 'None')):
    sc.view_settings.exposure = ev
    sc.view_settings.look = lk
    p = os.path.join(WORK, f'cm_test_{ev}_{lk[:4]}.png')
    img.save_render(p, scene=sc)
    got = read(p)[::-1].reshape(-1, 3)  # Blender pixel order is bottom-up
    want = apply(P if lk != 'None' else P0, test * 2.0 ** ev)
    want_noexp = apply(P if lk != 'None' else P0, test)
    d = np.abs(got - np.clip(want, 0, 1)) * 255
    val[f'exposure={ev},look={lk}'] = dict(mean_8bit=round(float(d.mean()), 4), max_8bit=round(float(d.max()), 4),
                                           max_8bit_if_exposure_ignored=round(float((np.abs(got - np.clip(want_noexp, 0, 1)) * 255).max()), 2))
report['validation_vs_blender_save_render'] = val
print('[lut] validation', json.dumps(val, indent=1), flush=True)

# ------------------------------------------------- dump reference frames to .npy, check frame pixels
frames = {}
for f in sorted(os.listdir(WORK)):
    if f.endswith('.exr'):
        a = read(os.path.join(WORK, f))
        np.save(os.path.join(WORK, f[:-4] + '.npy'), a)
        frames[f[:-4]] = a
for cam in ('CAM_stand', 'CAM_seat'):
    lin = frames[f'prev_{cam}'][..., :3]
    m = frames[f'prev_{cam}'][..., 3] > 0.999
    png = read(os.path.join(WORK, f'prev_{cam}.png'))[..., :3]
    mine = np.clip(apply(P, lin * 2.0 ** EXPOSURE), 0, 1)
    d = np.abs(mine - png)[m] * 255
    report.setdefault('frame_check', {})[f'prev_{cam}'] = dict(mean_8bit=round(float(d.mean()), 3),
                                                              p99_8bit=round(float(np.percentile(d, 99)), 3))
    lin = frames[f'ref_{cam}'][..., :3]
    png = read(os.path.join(WORK, f'ref_{cam}.png'))[..., :3]
    mine = np.clip(apply(P, lin * 2.0 ** EXPOSURE), 0, 1)
    d = np.abs(mine - png) * 255
    report['frame_check'][f'ref_{cam}'] = dict(mean_8bit=round(float(d.mean()), 3), p99_8bit=round(float(np.percentile(d, 99)), 3))
print('[lut] frame check', report['frame_check'], flush=True)

# ---------------------------------------------------------------------- 3. LUT size / shaper choice
samples = np.concatenate([frames[f'{k}_{c}'][..., :3].reshape(-1, 3) for k in ('ref', 'prev') for c in ('CAM_stand', 'CAM_seat')])
samples = samples[np.all(samples > 0, 1)] * 2.0 ** EXPOSURE
samples = samples[rng.choice(len(samples), 400000, replace=False)]
exact = np.clip(apply(P, samples), 0, 1)

# Shaper matrices: identity (log of Rec.709) or Rec.709 -> Linear FilmLight E-Gamut, the space both of
# Blender's own LUTs (luminance compensation and AgX base) are indexed in.
eg = OCIO.ColorSpaceTransform(src=scene_linear, dst='Linear FilmLight E-Gamut')
M_EG = apply(cfg.getProcessor(eg).getDefaultCPUProcessor(), np.eye(3, dtype=np.float32)).T.astype(np.float64)  # column j = image of e_j
MATS = {'rec709': np.eye(3), 'egamut': M_EG}
report['rec709_to_egamut'] = M_EG.tolist()


def make_lut(n, lo, hi, M):
    s = np.linspace(0, 1, n, dtype=np.float64)
    y = 2.0 ** (lo + s * (hi - lo))
    b, g, r = np.meshgrid(y, y, y, indexing='ij')         # red fastest in memory
    grid = np.stack([r, g, b], -1) @ np.linalg.inv(M).T   # shaper-space node -> linear Rec.709
    return np.clip(apply(P, grid.astype(np.float32)), 0, 1)  # (b, g, r, 3)


def trilinear(lut, n, lo, hi, M, x):
    y = x @ M.T
    s = np.clip((np.log2(np.maximum(y, 1e-10)) - lo) / (hi - lo), 0, 1) * (n - 1)
    i0 = np.minimum(np.floor(s).astype(int), n - 2)
    f = s - i0
    out = 0
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = (f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2])
                out = out + w[:, None] * lut[i0[:, 2] + db, i0[:, 1] + dg, i0[:, 0] + dr]
    return out


LO = -12.47393
choices = {}
for mname, M in MATS.items():
    for n in (33, 41, 49):
        for hi in (12.5260688117, 6.5):
            lut = make_lut(n, LO, hi, M).astype(np.float16).astype(np.float32)
            d = np.abs(trilinear(lut, n, LO, hi, M, samples) - exact) * 255
            k = f'{mname}_n{n}_hi{hi:.2f}'
            choices[k] = dict(mean_8bit=round(float(d.mean()), 4), p99_8bit=round(float(np.percentile(d, 99)), 4),
                              max_8bit=round(float(d.max()), 3), bytes=n ** 3 * 3 * 2, n=n, hi=hi, shaper=mname)
            print('[lut]', k, choices[k], flush=True)
report['lut_choices'] = choices

# Smallest LUT whose interpolation error on real frame pixels stays below Blender's own render
# dither (the 'frame check' above: ~0.35 of an 8-bit step mean, ~1.06 p99 against its own PNG)
# in the mean and within 2 steps at p99. Bigger LUTs buy ~0.1 step for 2-3x the download.
ok = [c for c in choices.values() if c['mean_8bit'] <= 0.3 and c['p99_8bit'] <= 2.0]
best = min(ok, key=lambda c: (c['bytes'], c['mean_8bit'])) if ok else min(choices.values(), key=lambda c: c['mean_8bit'])
N, HI, M = best['n'], best['hi'], MATS[best['shaper']]
lut = make_lut(N, LO, HI, M)
os.makedirs(os.path.dirname(LUT_OUT), exist_ok=True)
lut.astype('<f2').tofile(LUT_OUT)
report['chosen'] = dict(file=os.path.basename(LUT_OUT), size=N, log2_min=LO, log2_max=HI, shaper=best['shaper'],
                        shaper_matrix_rows=M.tolist(), error_on_frame_pixels=best,
                        layout='float16 RGB, red fastest, then green, then blue',
                        input='linear Rec.709 AFTER exposure; y = shaper_matrix * x; s = (log2(y) - log2_min) / (log2_max - log2_min), per channel',
                        output='display-encoded sRGB (what Blender writes to an 8-bit PNG), 0..1',
                        source=f'{CFG}: look {LOOK!r} (LookTransform into its process space) + display sRGB / view AgX')
json.dump(report, open(os.path.join(WORK, 'lut_report.json'), 'w'), indent=1)
json.dump(report['chosen'], open(LUT_OUT[:-4] + '.json', 'w'), indent=1)
print('[lut] chosen', report['chosen'], flush=True)
