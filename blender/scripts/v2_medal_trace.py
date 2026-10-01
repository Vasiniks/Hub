"""
v2_medal_trace.py -- trace the FIRST Robotics Competition 2026 "REBUILT" medal artwork from the owner's reference
photo (blender/scene/parts/medal_ref_silver.jpg; the gold reference is the same design at lower resolution) into
clean vector outlines for real relief geometry.

    python blender/scripts/v2_medal_trace.py            (PIL + numpy only)

Steps: crop each face (front = left medal, back = right medal) and scale to 800 px; local high-pass
(photo minus a 14-16 px blur) so polished raised art (front) / darker lettering (back) separates from the
field; threshold, drop specks and rim-highlight arcs, fill pin-holes; marching squares on the lightly smoothed
mask; Douglas-Peucker simplification; outlines in medal millimetres (Ø70, centre origin, y up, image
orientation -- x to the viewer's right). Output: blender/scene/parts/medal_frc_contours.json.
Artwork source: owner-supplied reference photos (FIRST/HAAS marks belong to their owners).
"""
import os
import sys
# blender/scripts contains an inspect.py (a Blender helper) that would shadow the stdlib module numpy needs
sys.path = [p for p in sys.path if os.path.abspath(p or '.') != os.path.dirname(os.path.abspath(__file__))]
import numpy as np
import json
import math
from PIL import Image, ImageFilter
from collections import deque, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.abspath(os.path.join(HERE, '..', 'scene', 'parts'))
WORK = os.path.join(PARTS, '_trace_work')
os.makedirs(WORK, exist_ok=True)
os.chdir(WORK)

# ----------------------------------------------------------------------
src = Image.open(os.path.join(PARTS, 'medal_ref_silver.jpg')).convert('L')
out = []
for name, (cx, cy, r) in (('front', (239, 473, 139)), ('back', (522, 470, 133))):
    box = (int(cx - r - 4), int(cy - r - 4), int(cx + r + 4), int(cy + r + 4))
    c = src.crop(box).resize((800, 800), Image.LANCZOS)
    c.save(f'{name}_crop.png')
    a = np.asarray(c).astype(float)
    blur = np.asarray(c.filter(ImageFilter.GaussianBlur(18))).astype(float)
    hp = np.clip((a - blur) * 3 + 128, 0, 255).astype(np.uint8)
    Image.fromarray(hp).save(f'{name}_hp.png')
    out += [c.convert('RGB'), Image.fromarray(hp).convert('RGB')]
sheet = Image.new('RGB', (1600, 1600))
for i, im in enumerate(out):
    sheet.paste(im, ((i % 2) * 800, (i // 2) * 800))



# ----------------------------------------------------------------------
N = 800

def components(m):
    lab = np.zeros(m.shape, np.int32); cur = 0; sizes = [0]
    H, W = m.shape
    for y in range(H):
        row = m[y]
        for x in np.nonzero(row & (lab[y] == 0))[0]:
            if lab[y, x]: continue
            cur += 1; q = deque([(y, x)]); lab[y, x] = cur; n = 0
            while q:
                a, b = q.popleft(); n += 1
                for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    c, d = a + da, b + db
                    if 0 <= c < H and 0 <= d < W and m[c, d] and not lab[c, d]:
                        lab[c, d] = cur; q.append((c, d))
            sizes.append(n)
    return lab, np.array(sizes)

def clean(m, min_area):
    lab, sizes = components(m)
    keep = sizes >= min_area; keep[0] = False
    return keep[lab]

yy, xx = np.mgrid[0:N, 0:N]
for name, r_px, sign, thr, inner, blur_r in (('front', 139, +1, 16, 0.905, 14), ('back', 133, -1, 14, 0.93, 16)):
    c = Image.open(f'{name}_crop.png')
    a = np.asarray(c).astype(float)
    b = np.asarray(c.filter(ImageFilter.GaussianBlur(blur_r))).astype(float)
    hp = (a - b) * sign
    hp_s = np.asarray(Image.fromarray(np.clip(hp + 128, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.1))).astype(float) - 128
    R = N / 2 * (r_px / (r_px + 4))
    rr = np.hypot(xx - N / 2 + 0.5, yy - N / 2 + 0.5)
    m = (hp_s > thr) & (rr < R * inner)
    m = clean(m, 40)
    # fill tiny holes (specks of field inside shapes)
    holes = clean(~m & (rr < R * inner), 25)
    m = m | ((~holes) & (rr < R * inner))
    np.save(f'{name}_mask.npy', m)
    Image.fromarray((m * 255).astype(np.uint8)).save(f'{name}_mask.png')
    print(name, 'raised fraction', round(m.mean(), 4))
sheet = Image.new('L', (1600, 800))
sheet.paste(Image.open('front_mask.png'), (0, 0)); sheet.paste(Image.open('back_mask.png'), (800, 0))
sheet.save('masks.png')


# ----------------------------------------------------------------------
N = 800

def components(m):
    lab = np.zeros(m.shape, np.int32); cur = 0; pix = [None]
    H, W = m.shape
    for y in range(H):
        for x in np.nonzero(m[y] & (lab[y] == 0))[0]:
            if lab[y, x]: continue
            cur += 1; q = deque([(y, x)]); lab[y, x] = cur; pts = []
            while q:
                a, b = q.popleft(); pts.append((a, b))
                for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    c, d = a + da, b + db
                    if 0 <= c < H and 0 <= d < W and m[c, d] and not lab[c, d]:
                        lab[c, d] = cur; q.append((c, d))
            pix.append(np.array(pts))
    return lab, pix

def dp(pts, tol):
    """Douglas-Peucker on an open polyline (list of np arrays)."""
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]
    ab = b - a; L = np.hypot(*ab)
    P = np.array(pts)
    if L < 1e-9:
        d = np.hypot(*(P - a).T)
    else:
        d = np.abs(np.cross(ab, P - a)) / L
    i = int(np.argmax(d))
    if d[i] > tol:
        return dp(pts[:i + 1], tol)[:-1] + dp(pts[i:], tol)
    return [a, b]

def simplify_closed(loop, tol):
    P = [np.array(p) for p in loop]
    # split at the farthest point from the first to run DP on two halves
    d = [np.hypot(*(p - P[0])) for p in P]
    k = int(np.argmax(d))
    s1 = dp(P[:k + 1], tol); s2 = dp(P[k:] + [P[0]], tol)
    return s1[:-1] + s2[:-1]

def march(f, iso=0.5):
    H, W = f.shape
    segs = defaultdict(list)
    def ept(e):
        kind, i, j = e
        if kind == 'h':   # between (i,j) and (i,j+1)
            v0, v1 = f[i, j], f[i, j + 1]; t = (iso - v0) / (v1 - v0)
            return (j + t, i)
        v0, v1 = f[i, j], f[i + 1, j]; t = (iso - v0) / (v1 - v0)
        return (j, i + t)
    b = f > iso
    for i in range(H - 1):
        for j in range(W - 1):
            tl, tr, br, bl = b[i, j], b[i, j + 1], b[i + 1, j + 1], b[i + 1, j]
            c = tl * 8 + tr * 4 + br * 2 + bl * 1
            if c == 0 or c == 15: continue
            T, R, B, L = ('h', i, j), ('v', i, j + 1), ('h', i + 1, j), ('v', i, j)
            table = {1: [(L, B)], 2: [(B, R)], 3: [(L, R)], 4: [(T, R)], 6: [(T, B)], 7: [(L, T)],
                     8: [(L, T)], 9: [(T, B)], 11: [(T, R)], 12: [(L, R)], 13: [(B, R)], 14: [(L, B)]}
            if c in (5, 10):
                centre = (f[i, j] + f[i, j + 1] + f[i + 1, j + 1] + f[i + 1, j]) / 4 > iso
                if c == 5:
                    pairs = [(L, T), (B, R)] if centre else [(L, B), (T, R)]
                else:
                    pairs = [(T, R), (L, B)] if centre else [(L, T), (B, R)]
            else:
                pairs = table[c]
            for e1, e2 in pairs:
                segs[e1].append(e2); segs[e2].append(e1)
    loops, used = [], set()
    for start in list(segs):
        if start in used: continue
        loop = [start]; used.add(start); prev = None; cur = start
        while True:
            nxt = [e for e in segs[cur] if e != prev and (e not in used or (e == start and len(loop) > 2))]
            if not nxt: break
            n = nxt[0]
            if n == start: break
            loop.append(n); used.add(n); prev, cur = cur, n
        if len(loop) >= 4:
            loops.append([ept(e) for e in loop])
    return loops

out = {}
yy, xx = np.mgrid[0:N, 0:N]
for name, r_px in (('front', 139), ('back', 133)):
    m = np.load(f'{name}_mask.npy')
    R = N / 2 * (r_px / (r_px + 4))
    rr = np.hypot(xx - N / 2 + 0.5, yy - N / 2 + 0.5)
    lab, pix = components(m)
    for k in range(1, len(pix)):
        p = pix[k]
        rad = rr[p[:, 0], p[:, 1]]
        ext = max(p[:, 0].max() - p[:, 0].min(), p[:, 1].max() - p[:, 1].min())
        if rad.max() > 0.84 * R and rad.mean() > 0.78 * R and ext > 0.25 * R:
            m[p[:, 0], p[:, 1]] = False
    np.save(f'{name}_mask2.npy', m)
    f = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))).astype(float) / 255
    f = np.pad(f, 1)
    loops = march(f)
    res = []
    for lp in loops:
        s = simplify_closed(lp, 0.7)
        if len(s) < 3: continue
        pts = [((x - 1 - N / 2 + 0.5) / R * 35.0, -(y - 1 - N / 2 + 0.5) / R * 35.0) for x, y in s]
        area = 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        if abs(area) < 0.01: continue          # < 0.01 mm^2 specks
        res.append(pts)
    out[name] = res
    print(name, 'loops', len(res), 'points', sum(len(r) for r in res))
    Image.fromarray((m * 255).astype(np.uint8)).save(f'{name}_mask2.png')
json.dump(out, open(os.path.join(PARTS, 'medal_frc_contours.json'), 'w'))
print('WROTE', os.path.join(PARTS, 'medal_frc_contours.json'))

