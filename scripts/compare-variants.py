# Diff table + side-by-side crops for compare-variants.mjs. Usage: python3 scripts/compare-variants.py <outDir> ref other... --hours 13,21
import sys
from PIL import Image, ImageChops
args = sys.argv[1:]
hours = '13,21'
if '--hours' in args:
    i = args.index('--hours'); hours = args[i + 1]; args = args[:i] + args[i + 2:]
out, ref, *others = args
views = ['seated', 'deskRight', 'shelf', 'standing']
print(f"{'variant':14s} {'hour':5s} " + ' '.join(f'{v:>18s}' for v in views))
for o in others:
    for h in hours.split(','):
        cells = []
        for v in views:
            a = Image.open(f'{out}/{ref}-{h}-{v}.png').convert('RGB'); b = Image.open(f'{out}/{o}-{h}-{v}.png').convert('RGB')
            d = [max(p) for p in ImageChops.difference(a, b).crop((0, 0, a.width, a.height - 70)).get_flattened_data()]
            cells.append(f'{sum(d)/len(d):6.2f} >8:{sum(1 for x in d if x > 8):6d}')
        print(f'{o:14s} {h:5s} ' + ' '.join(f'{c:>18s}' for c in cells))
        rows = []
        for v in views:
            a = Image.open(f'{out}/{ref}-{h}-{v}.png').convert('RGB').resize((600, 375)); b = Image.open(f'{out}/{o}-{h}-{v}.png').convert('RGB').resize((600, 375))
            r = Image.new('RGB', (1210, 375), 'white'); r.paste(a, (0, 0)); r.paste(b, (610, 0)); rows.append(r)
        g = Image.new('RGB', (1210, 385 * len(rows)), 'white')
        for i, r in enumerate(rows): g.paste(r, (0, i * 385))
        g.save(f'{out}/pair-{o}-{h}.png')
