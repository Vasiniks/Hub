# Companion to bloom-score.mjs. Usage: python3 scripts/bloom-score.py <outDir> <reference> <nobloom> names...
import sys, colorsys
from PIL import Image, ImageChops
out, ref, nob, *names = sys.argv[1:]
cube_ref = Image.open(f'{out}/cube-{nob}.png').convert('RGB')
w, h = cube_ref.size
px = cube_ref.load()
mask = [(x, y) for y in range(0, h, 2) for x in range(0, w, 2)
        if (lambda hls: hls[2] > 0.45 and 0.12 < hls[1] < 0.85)(colorsys.rgb_to_hls(*[c / 255 for c in px[x, y]]))]
def sat(img):
    p = img.load(); s = 0
    for x, y in mask: s += colorsys.rgb_to_hls(*[c / 255 for c in p[x, y]])[2]
    return s / len(mask)
def diff(a, b):
    d = ImageChops.difference(a.convert('L'), b.convert('L')).crop((0, 0, a.width, a.height - 70))
    v = list(d.get_flattened_data()); return sum(v) / len(v)
print(f"{'variant':34s} cube-sat  night-diff  dusk-diff  day-diff")
for n in [ref, nob] + names:
    c = sat(Image.open(f'{out}/cube-{n}.png').convert('RGB'))
    nd = diff(Image.open(f'{out}/night-{n}.png'), Image.open(f'{out}/night-{ref}.png'))
    dd = diff(Image.open(f'{out}/dusk-{n}.png'), Image.open(f'{out}/dusk-{ref}.png'))
    da = diff(Image.open(f'{out}/day-{n}.png'), Image.open(f'{out}/day-{ref}.png'))
    print(f'{n:34s} {c:.3f}     {nd:6.2f}      {dd:6.2f}     {da:6.2f}')
