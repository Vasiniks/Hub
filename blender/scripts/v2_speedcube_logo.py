"""
Extract the WeiLong V11 18th Anniversary centre-cap emblem as a clean decal texture.

Source: blender/scene/parts/cube_logo_ref.png (owner-supplied retailer photo, straight-on view of
the white face; git-ignored, not an asset). Output: blender/scene/parts/cube_logo_18.png, a
square RGBA decal (flat print red, alpha = the line work) that v2_speedcube.py maps onto the
white centre cap. Also writes cube_logo_18_meta.txt with the emblem size relative to the cap.

The photo's emblem is only ~110 px wide, so the red channel is isolated, upsampled 8x with a
smooth filter, and re-thresholded through a narrow ramp: stair-stepped JPEG/PNG edges become
clean anti-aliased contours while every line keeps the position and width it has in the photo.

Usage (system Python with Pillow + numpy):  python v2_speedcube_logo.py
"""
import os
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(HERE, '..', 'scene', 'parts')
SRC = os.path.join(PARTS, 'cube_logo_ref.png')
OUT = os.path.join(PARTS, 'cube_logo_18.png')
META = os.path.join(PARTS, 'cube_logo_18_meta.txt')

CAP_BOX = (320, 330, 470, 480)  # the white centre cap in the 800x800 photo
UP = 8

im = np.asarray(Image.open(SRC).convert('RGB').crop(CAP_BOX)).astype(np.float32) / 255.0
r, g, b = im[..., 0], im[..., 1], im[..., 2]
red = np.clip((r - np.maximum(g, b)) / 0.6, 0.0, 1.0)      # white cap -> 0, print red -> ~1
red[r < 0.55] = 0.0                                          # dark reddish internals in the pockets
win = np.zeros_like(red)
win[15:136, 15:136] = 1.0                                    # the cap face only, not the pockets
red *= win
ys, xs = np.nonzero(red > 0.35)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
half = max(x1 - x0, y1 - y0) / 2 + 3
box = (int(round(cx - half)), int(round(cy - half)), int(round(cx + half)), int(round(cy + half)))

# print colour: median of the strongly red pixels
strong = red > 0.8
col = np.median(im[strong], axis=0)

# the cap in the photo: find its white extent along the centre row/column for scale
white = (im.min(axis=2) > 0.80)
row = white[int(cy)]
colw = white[:, int(cx)]
cap_w = row.sum()
cap_h = colw.sum()

m = Image.fromarray((red * 255).astype(np.uint8)).crop(box)
size = m.size[0] * UP
m = m.resize((size, size), Image.BICUBIC).filter(ImageFilter.GaussianBlur(UP * 0.45))
a = np.asarray(m).astype(np.float32) / 255.0
a = np.clip((a - 0.50) / 0.12, 0.0, 1.0)                     # narrow ramp = crisp anti-aliased edge
a = a * a * (3 - 2 * a)
rgba = np.zeros((size, size, 4), np.uint8)
rgba[..., 0] = int(col[0] * 255)
rgba[..., 1] = int(col[1] * 255)
rgba[..., 2] = int(col[2] * 255)
rgba[..., 3] = (a * 255).astype(np.uint8)
Image.fromarray(rgba, 'RGBA').save(OUT)

logo_px = box[2] - box[0]
with open(META, 'w') as f:
    f.write(f'logo_px {logo_px}\ncap_px {cap_w} {cap_h}\nlogo_over_cap {logo_px / cap_w:.4f}\n'
            f'colour_srgb #{int(col[0]*255):02X}{int(col[1]*255):02X}{int(col[2]*255):02X}\n')
print('logo box', box, 'logo px', logo_px, 'cap px', cap_w, cap_h, 'colour', col, '->', OUT)
