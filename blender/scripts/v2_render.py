"""
Background Cycles still of the room (CUDA GPU-only: measured fastest on the RTX 5070).

    blender -b <file.blend> --python blender/scripts/v2_render.py -- <out.png> <camera> <samples> <percent>
"""
import bpy, sys, time

a = sys.argv[sys.argv.index('--') + 1:]
out, cam, spp, pct = a[0], a[1], int(a[2]), int(a[3])
sc = bpy.context.scene
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.refresh_devices()
for d in prefs.devices:
    d.use = (d.type == 'CUDA')
sc.render.engine = 'CYCLES'
sc.cycles.device = 'GPU'
sc.cycles.samples = spp
sc.cycles.use_denoising = True
sc.cycles.denoiser = 'OPTIX'
sc.render.resolution_percentage = pct
sc.camera = bpy.data.objects[cam]
sc.render.filepath = out
t = time.time()
bpy.ops.render.render(write_still=True)
print('RENDER_SECONDS', round(time.time() - t, 1))
