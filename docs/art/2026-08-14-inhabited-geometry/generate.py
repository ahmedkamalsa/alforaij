# -*- coding: utf-8 -*-
"""Inhabited Geometry — Plate VII. Renders at 2x then downsamples for hairline AA."""
import math, random
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

S = 2          # supersample factor
W, H = 2400 * S, 3200 * S

# ── palette ──
NAVY_DEEP  = (7, 11, 20, 255)      # field
NAVY_PANEL = (12, 19, 34, 255)     # map panel
GOLD       = (226, 201, 104, 255)  # bright mark
GOLD_DIM   = (138, 122, 74, 255)   # dim mark
GOLD_FAINT = (61, 56, 40, 255)     # apparatus
IVORY      = (232, 224, 200, 255)  # labels
SEAL_RED   = (166, 58, 46, 255)    # signature seal

def A(s, size):
    """shape Arabic (RTL + joining) then return font + display string"""
    f = ImageFont.truetype(r"C:\Windows\Fonts\arabtype.ttf", size)
    return f, get_display(arabic_reshaper.reshape(s))

GEO  = lambda size: ImageFont.truetype(r"C:\Windows\Fonts\georgia.ttf", size)
CON  = lambda size: ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", size)

img = Image.new("RGBA", (W, H), NAVY_DEEP)
d = ImageDraw.Draw(img)

# ── faint astrolabe construction behind everything ──
PLAZA_CX, PLAZA_CY = None, None

# ── geometry of the map ──
CELL, ALLEY, PITCH = 210, 62, 272
COLS, ROWS = 12, 13
map_w_used = COLS * CELL + (COLS - 1) * ALLEY      # 3202
map_h_used = ROWS * CELL + (ROWS - 1) * ALLEY      # 3474
MAP_X0 = 760 + (3280 - map_w_used) // 2
MAP_Y0 = 1350 + (3700 - map_h_used) // 2

def cell_rect(c, r):
    x0 = MAP_X0 + c * PITCH
    y0 = MAP_Y0 + r * PITCH
    return (x0, y0, x0 + CELL, y0 + CELL)

# carve-outs
REMOVED = set()
for r in range(5, 9):                 # plaza 4x4 at cols 4..7, rows 5..8
    for c in range(4, 8):
        REMOVED.add((c, r))
for r in range(ROWS):                 # main alley: full column 2
    REMOVED.add((2, r))
rng = random.Random(20260814)         # deterministic
for _ in range(7):                    # scattered empty lots
    c, r = rng.randrange(COLS), rng.randrange(ROWS)
    if (c, r) not in REMOVED and not (4 <= c <= 7 and 5 <= r <= 8):
        REMOVED.add((c, r))

plaza_cells = [(c, r) for r in range(5, 9) for c in range(4, 8)]
px0, py0, px1, py1 = cell_rect(4, 5)[0], cell_rect(4, 5)[1], cell_rect(7, 8)[2], cell_rect(7, 8)[3]
PLAZA_CX, PLAZA_CY = (px0 + px1) // 2, (py0 + py1) // 2

# astrolabe echoes
for R_ in (760, 1120, 1480):
    d.ellipse([PLAZA_CX - R_, PLAZA_CY - R_, PLAZA_CX + R_, PLAZA_CY + R_],
              outline=(*GOLD_FAINT[:3], 70), width=2)
for ang in (45, 135):
    rad = math.radians(ang)
    d.line([PLAZA_CX - 1500 * math.cos(rad), PLAZA_CY - 1500 * math.sin(rad),
            PLAZA_CX + 1500 * math.cos(rad), PLAZA_CY + 1500 * math.sin(rad)],
           fill=(*GOLD_FAINT[:3], 55), width=2)

# ── the courtyard population ──
PATTERNS = ["v", "h", "d1", "d2", "dots", "court", "tree", "xh", "empty"]

def hatch(x0, y0, x1, y1, kind, color, w=2):
    n = 7
    if kind == "v":
        for i in range(1, n):
            xx = x0 + (x1 - x0) * i / n
            d.line([xx, y0 + 8, xx, y1 - 8], fill=color, width=w)
    elif kind == "h":
        for i in range(1, n):
            yy = y0 + (y1 - y0) * i / n
            d.line([x0 + 8, yy, x1 - 8, yy], fill=color, width=w)
    elif kind == "d1":
        for i in range(-n, n):
            off = i * (x1 - x0) / n
            d.line([x0 + off, y1, x1 + off, y0], fill=color, width=w)
    elif kind == "d2":
        for i in range(-n, n):
            off = i * (x1 - x0) / n
            d.line([x0 + off, y0, x1 + off, y1], fill=color, width=w)
    elif kind == "xh":
        hatch(x0, y0, x1, y1, "d1", color, w); hatch(x0, y0, x1, y1, "d2", color, w)
    elif kind == "dots":
        for i in range(1, 6):
            for j in range(1, 6):
                xx = x0 + (x1 - x0) * i / 6
                yy = y0 + (y1 - y0) * j / 6
                d.ellipse([xx - 3, yy - 3, xx + 3, yy + 3], fill=color)
    elif kind == "court":
        m = 26
        d.rectangle([x0 + m, y0 + m, x1 - m, y1 - m], outline=color, width=w)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=color)
    elif kind == "tree":
        cx, cy = (x0 + x1) // 2, y1 - 34
        d.line([cx, y1 - 18, cx, cy], fill=color, width=w)
        d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], outline=color, width=w)

# panel behind the map
d.rectangle([MAP_X0 - 90, MAP_Y0 - 90, MAP_X0 + map_w_used + 90, MAP_Y0 + map_h_used + 90],
            fill=NAVY_PANEL, outline=(*GOLD_FAINT[:3], 255), width=2)

for r in range(ROWS):
    for c in range(COLS):
        if (c, r) in REMOVED:
            continue
        x0, y0, x1, y1 = cell_rect(c, r)
        kind = PATTERNS[rng.randrange(len(PATTERNS))]
        # avoid two identical neighbors feeling mechanical — fine, rng already varies
        d.rectangle([x0, y0, x1, y1], outline=GOLD_DIM, width=2)
        hatch(x0, y0, x1, y1, kind, GOLD_FAINT if kind != "court" else GOLD, 2)

# ── the plaza: gathering square + auction hall star ──
d.rectangle([px0, py0, px1, py1], outline=GOLD, width=3)
d.rectangle([px0 + 18, py0 + 18, px1 - 18, py1 - 18], outline=GOLD_DIM, width=2)
for R_ in (90, 150):
    d.ellipse([PLAZA_CX - R_, PLAZA_CY - R_, PLAZA_CX + R_, PLAZA_CY + R_],
              outline=GOLD_DIM, width=2)
# ring of dots — the gathering
for k in range(24):
    ang = math.radians(k * 15)
    rr = 222
    d.ellipse([PLAZA_CX + rr * math.cos(ang) - 4, PLAZA_CY + rr * math.sin(ang) - 4,
               PLAZA_CX + rr * math.cos(ang) + 4, PLAZA_CY + rr * math.sin(ang) + 4], fill=GOLD)
# 8-point star (two rotated squares)
sz = 95
sq = lambda rot: [ (PLAZA_CX + math.cos(math.radians(rot + 45 + k * 90)) * sz * math.sqrt(2),
                    PLAZA_CY + math.sin(math.radians(rot + 45 + k * 90)) * sz * math.sqrt(2)) for k in range(4)]
d.polygon(sq(0), outline=GOLD, width=3)
d.polygon(sq(45), outline=GOLD, width=3)
d.ellipse([PLAZA_CX - 10, PLAZA_CY - 10, PLAZA_CX + 10, PLAZA_CY + 10], fill=GOLD)

# ── specimen index: numbered tags with leader lines ──
rng2 = random.Random(777)
index_cells = []
while len(index_cells) < 12:
    c, r = rng2.randrange(COLS), rng2.randrange(ROWS)
    if (c, r) in REMOVED or (4 <= c <= 7 and 5 <= r <= 8):
        continue
    if all(abs(c - x) + abs(r - y) > 1 for x, y in index_cells):
        index_cells.append((c, r))
for i, (c, r) in enumerate(index_cells, 1):
    x0, y0, x1, y1 = cell_rect(c, r)
    mx, my = (x0 + x1) // 2, (y0 + y1) // 2
    # tag square at the cell corner
    tx = x0 - 26 if c > 6 else x1 + 6
    ty = y0 - 26 if r > 6 else y1 + 6
    d.rectangle([tx, ty, tx + 20, ty + 20], outline=GOLD_DIM, width=2)
    d.line([mx, my, tx + 10, ty + 10], fill=(*GOLD_DIM[:3], 180), width=2)
    # number into the gutter
    gx = 330 if c <= 6 else W - 330
    gy = ty + 10 + (0 if r > 6 else -14)
    f = CON(42)
    label = f"{i:02d}"
    d.text((gx, gy), label, font=f, fill=IVORY, anchor="mm")
    d.line([tx + 10, ty + 10, gx, gy], fill=(*GOLD_FAINT[:3], 200), width=2)

# ── margin coordinate ticks ──
f_ticks = CON(30)
for c in range(COLS):
    x = MAP_X0 + c * PITCH + CELL // 2
    d.line([x, MAP_Y0 - 90, x, MAP_Y0 - 70], fill=(*GOLD_FAINT[:3], 255), width=2)
    d.text((x, MAP_Y0 - 100), chr(65 + c), font=f_ticks, fill=(*IVORY[:3], 120), anchor="mm")
for r in range(ROWS):
    y = MAP_Y0 + r * PITCH + CELL // 2
    d.line([MAP_X0 + map_w_used + 70, y, MAP_X0 + map_w_used + 90, y], fill=(*GOLD_FAINT[:3], 255), width=2)
    d.text((MAP_X0 + map_w_used + 100, y), str(r + 1), font=f_ticks, fill=(*IVORY[:3], 120), anchor="lm")

# ── title band ──
def tracked(draw, xy, text, font, fill, tracking=0, anchor_mm=True):
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x0, y0 = xy
    x = x0 - total / 2
    for ch, w in zip(text, widths):
        if anchor_mm:
            draw.text((x + w / 2, y0), ch, font=font, fill=fill, anchor="mm")
        else:
            draw.text((x, y0), ch, font=font, fill=fill, anchor="lm")
        x += w + tracking

f_title = GEO(150)
tracked(d, (W // 2, 430), "INHABITED GEOMETRY", f_title, GOLD, tracking=58)
f_ar, ar_title = A("هندسة مسكونة", 190)
d.text((W // 2, 640), ar_title, font=f_ar, fill=IVORY, anchor="mm")
f_sub = CON(44)
tracked(d, (W // 2, 800), "PLATE VII  ·  A NEIGHBORHOOD UNDER OBSERVATION", f_sub, GOLD_DIM, tracking=22)
# rule with diamond
rule_y = 900
d.line([W // 2 - 1400, rule_y, W // 2 - 40, rule_y], fill=GOLD_FAINT, width=2)
d.line([W // 2 + 40, rule_y, W // 2 + 1400, rule_y], fill=GOLD_FAINT, width=2)
d.polygon([(W // 2, rule_y - 14), (W // 2 + 14, rule_y), (W // 2, rule_y + 14), (W // 2 - 14, rule_y)],
          outline=GOLD, width=2)

# ── frame ──
FR = 160
d.rectangle([FR, FR, W - FR, H - FR], outline=GOLD_DIM, width=3)
d.rectangle([FR + 40, FR + 40, W - FR - 40, H - FR - 40], outline=(*GOLD_FAINT[:3], 255), width=2)
for cx, cy in ((FR, FR), (W - FR, FR), (FR, H - FR), (W - FR, H - FR)):
    d.polygon([(cx, cy - 24), (cx + 24, cy), (cx, cy + 24), (cx - 24, cy)], outline=GOLD, width=3)
for cx in (W // 2,):
    for cy in (FR, H - FR):
        d.polygon([(cx, cy - 14), (cx + 14, cy), (cx, cy + 14), (cx - 14, cy)], outline=GOLD_DIM, width=2)

# ── bottom apparatus ──
# compass rose (left)
cxc, cyc = 620, 5600
d.ellipse([cxc - 170, cyc - 170, cxc + 170, cyc + 170], outline=GOLD_DIM, width=2)
for k in range(8):
    ang = math.radians(k * 45)
    r0, r1 = 130, 170
    d.line([cxc + r0 * math.cos(ang), cyc + r0 * math.sin(ang),
            cxc + r1 * math.cos(ang), cyc + r1 * math.sin(ang)], fill=GOLD_DIM, width=3)
d.line([cxc, cyc - 130, cxc, cyc - 210], fill=GOLD, width=3)
d.polygon([(cxc - 26, cyc - 210), (cxc + 26, cyc - 210), (cxc, cyc - 260)], fill=GOLD)
d.text((cxc, cyc + 205), "N", font=GEO(80), fill=IVORY, anchor="mm")
d.text((cxc, cyc + 275), "TRUE NORTH OF THE FAREEJ", font=CON(30), fill=GOLD_DIM, anchor="mm")

# scale bar (center)
sx0, sy = W // 2 - 460, 5560
d.line([sx0, sy, sx0 + 920, sy], fill=IVORY, width=3)
for i, v in enumerate((0, 1, 2)):
    xx = sx0 + i * 460
    d.line([xx, sy - 18, xx, sy + 18], fill=IVORY, width=3)
    f_ar2, dv = A(str(v), 92)
    d.text((xx, sy + 60), dv, font=f_ar2, fill=IVORY, anchor="mm")
f_ar3, unit = A("م", 92)
d.text((sx0 + 920 + 46, sy + 60), unit, font=f_ar3, fill=IVORY, anchor="mm")
d.text((W // 2, sy + 150), "SCALE OF THE COURTYARD", font=CON(30), fill=GOLD_DIM, anchor="mm")

# seal (right)
sex, sey = W - 620, 5600
d.ellipse([sex - 150, sey - 150, sex + 150, sey + 150], outline=SEAL_RED, width=4)
for k in range(24):
    ang = math.radians(k * 15)
    r0, r1 = 132, 148
    d.line([sex + r0 * math.cos(ang), sey + r0 * math.sin(ang),
            sex + r1 * math.cos(ang), sey + r1 * math.sin(ang)], fill=SEAL_RED, width=2)
f_ar4, seal_word = A("الفريج", 120)
d.text((sex, sey), seal_word, font=f_ar4, fill=SEAL_RED, anchor="mm")

# specimen key strip (centered, bottom)
key_items = [("dots", "a"), ("v", "b"), ("xh", "c"), ("court", "d"), ("tree", "e"), ("empty", "f")]
key_x0 = W // 2 - (6 * 170) // 2
for i, (kind, lab) in enumerate(key_items):
    kx = key_x0 + i * 170
    ky = 6010
    hx0, hy0, hx1, hy1 = kx - 55, ky - 55, kx + 55, ky + 55
    d.rectangle([hx0, hy0, hx1, hy1], outline=GOLD_DIM, width=2)
    if kind == "empty":
        pass
    else:
        hatch(hx0 + 6, hy0 + 6, hx1 - 6, hy1 - 6, kind, GOLD, 2)
    d.text((kx, ky + 85), lab, font=CON(34), fill=IVORY, anchor="mm")
f_ar5, key_title = A("مفتاح العينات", 78)
d.text((key_x0 - 110, 6010), key_title, font=f_ar5, fill=GOLD_DIM, anchor="rm")

# signature line — فوق الإطار السفلي (6240) بمسافة واضحة
f_sig = CON(34)
_sig_text = "FAREEJ CARTOGRAPHIC SURVEY  ·  MMXXVI"
_sig_w = f_sig.getlength(_sig_text)
d.text((W // 2, 6186), _sig_text, font=f_sig, fill=(*GOLD_DIM[:3], 220), anchor="mm")
# فاصل صغير تحت التوقيع — في المنتصف بين الإطارين الداخلي (6200) والخارجي (6240)
for _off in (-1, 1):
    d.line([W // 2 - _sig_w / 2 + _off, 6220, W // 2 + _sig_w / 2 - _off, 6220], fill=(*GOLD_FAINT[:3], 200), width=2)

# ── vignette: تظليل قطري ناعم نحو الحواف (قناع L سليم: 255 في المنتصف) ──
import numpy as _np
_yy, _xx = _np.mgrid[0:H, 0:W]
_cx, _cy = W / 2, H / 2
_dist = _np.sqrt((_xx - _cx) ** 2 + (_yy - _cy) ** 2) / _np.hypot(_cx, _cy)
_vig = (255 - 66 * _np.clip(_dist, 0, 1) ** 2).astype("uint8")
vig = Image.fromarray(_vig, "L")
img = Image.composite(img, Image.new("RGBA", (W, H), NAVY_DEEP), vig)

# ── downsample ──
out = img.resize((W // S, H // S), Image.LANCZOS)
out.save(r"D:\foraj_social\287\alforaij-research-assistant\docs\art\2026-08-14-inhabited-geometry\inhabited-geometry.png")
print("saved", out.size)
