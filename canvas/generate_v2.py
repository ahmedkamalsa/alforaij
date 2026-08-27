#!/usr/bin/env python3
"""
Desert Cartography v2 — Refined second pass.
Philosophy: refine existing elements, don't add new ones.
Make it feel like a master cartographer's life work.
"""
import math
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 2400, 3200
img = Image.new("RGB", (W, H), "#F5F0E8")
draw = ImageDraw.Draw(img)

# Palette
SAND      = "#C8B896"
LIMESTONE = "#E8E0D0"
PETROL    = "#1A1A2E"
TWILIGHT  = "#2C5F7C"
ACCENT    = "#B85C38"
WARM_GRAY = "#8A8070"
LIGHT_GRAY = "#D5CFC3"
FAINT     = "#E0D8C8"

def load_font(name, size):
    for p in [f"C:/Windows/Fonts/{name}", f"C:/Users/hello/AppData/Local/Microsoft/Windows/Fonts/{name}"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

font_label = load_font("tahoma.ttf", 22)
font_title = load_font("tahoma.ttf", 42)
font_specimen = load_font("tahomabd.ttf", 18)
font_accent = load_font("tahoma.ttf", 13)
font_arabic = load_font("tahoma.ttf", 32)
font_arabic_sm = load_font("tahoma.ttf", 16)
font_micro = load_font("tahoma.ttf", 10)

random.seed(42)

def draw_circle(d, cx, cy, r, **kw):
    d.ellipse([cx-r, cy-r, cx+r, cy+r], **kw)

def draw_line(d, x1, y1, x2, y2, **kw):
    d.line([(x1,y1),(x2,y2)], **kw)

# ══════════════════════════════════════════════════════════
# LAYER 1: Parchment texture (subtle noise)
# ══════════════════════════════════════════════════════════
texture = Image.new("RGB", (W, H), "#F5F0E8")
tdraw = ImageDraw.Draw(texture)
for _ in range(80000):
    x = random.randint(0, W-1)
    y = random.randint(0, H-1)
    v = random.randint(230, 245)
    tdraw.point((x, y), fill=f"#{v:02x}{v-3:02x}{v-8:02x}")
texture = texture.filter(ImageFilter.GaussianBlur(0.8))
img = Image.alpha_composite(img.convert("RGBA"), texture.convert("RGBA")).convert("RGB")
draw = ImageDraw.Draw(img)

# ══════════════════════════════════════════════════════════
# LAYER 2: Survey grid (very faint, with organic fade)
# ══════════════════════════════════════════════════════════
grid_spacing = 60
for x in range(0, W, grid_spacing):
    # Fade at edges
    edge_factor = min(x / 200, (W - x) / 200, 1.0)
    v = int(210 + 10 * edge_factor)
    draw_line(draw, x, 0, x, H, fill=f"#{v:02x}{v-8:02x}{v-16:02x}", width=1)
for y in range(0, H, grid_spacing):
    edge_factor = min(y / 200, (H - y) / 200, 1.0)
    v = int(210 + 10 * edge_factor)
    draw_line(draw, 0, y, W, y, fill=f"#{v:02x}{v-8:02x}{v-16:02x}", width=1)

# ══════════════════════════════════════════════════════════
# LAYER 3: Zone system (concentric, with depth)
# ══════════════════════════════════════════════════════════
zone_cx, zone_cy = W * 0.72, H * 0.35
for i in range(14, 0, -1):
    r = i * 58
    # Inner rings darker, outer rings lighter
    if i <= 4:
        color = PETROL
        w = 2
    elif i <= 8:
        color = TWILIGHT
        w = 1
    else:
        color = SAND
        w = 1
    draw_circle(draw, zone_cx, zone_cy, r, outline=color, width=w)

# Radial lines — vary weight by significance
for angle_deg in range(0, 360, 10):
    angle = math.radians(angle_deg)
    r_inner = 60
    r_outer = 14 * 58
    x1 = zone_cx + r_inner * math.cos(angle)
    y1 = zone_cy + r_inner * math.sin(angle)
    x2 = zone_cx + r_outer * math.cos(angle)
    y2 = zone_cy + r_outer * math.sin(angle)
    if angle_deg % 30 == 0:
        draw_line(draw, x1, y1, x2, y2, fill=SAND, width=2)
    elif angle_deg % 15 == 0:
        draw_line(draw, x1, y1, x2, y2, fill=LIGHT_GRAY, width=1)
    else:
        draw_line(draw, x1, y1, x2, y2, fill=FAINT, width=1)

# Data points within zones — clustered by ring
for i in range(14):
    r_center = (i + 0.5) * 58
    n_points = max(3, 25 - i * 2)
    for _ in range(n_points):
        angle = random.uniform(0, 2 * math.pi)
        r = r_center + random.gauss(0, 15)
        x = zone_cx + r * math.cos(angle)
        y = zone_cy + r * math.sin(angle)
        if 80 < x < W - 80 and 80 < y < H - 80:
            size = random.choice([1, 1, 2, 2, 3])
            color = random.choice([PETROL, TWILIGHT, ACCENT, WARM_GRAY])
            draw_circle(draw, x, y, size, fill=color)

# ══════════════════════════════════════════════════════════
# LAYER 4: Dense market cluster (bottom-left)
# ══════════════════════════════════════════════════════════
cluster_cx, cluster_cy = W * 0.28, H * 0.72

# Background field
for i in range(24):
    for j in range(18):
        x = cluster_cx - 480 + i * 42
        y = cluster_cy - 340 + j * 40
        dx = (i - 12) / 12.0
        dy = (j - 9) / 9.0
        dist = math.sqrt(dx*dx + dy*dy)
        if random.random() < max(0.05, 0.85 - dist * 0.7):
            size = random.choice([3, 4, 5, 6, 8, 10])
            color = random.choice([PETROL, TWILIGHT, ACCENT, SAND, WARM_GRAY])
            draw_circle(draw, x, y, size, fill=color)

# Connecting lines (grid in cluster area)
for i in range(24):
    x = cluster_cx - 480 + i * 42
    if random.random() < 0.7:
        draw_line(draw, x, cluster_cy - 340, x, cluster_cy + 340,
                  fill=FAINT, width=1)
for j in range(18):
    y = cluster_cy - 340 + j * 40
    if random.random() < 0.7:
        draw_line(draw, cluster_cx - 480, y, cluster_cx + 480, y,
                  fill=FAINT, width=1)

# ══════════════════════════════════════════════════════════
# LAYER 5: Topographic contours (organic, flowing)
# ══════════════════════════════════════════════════════════
for level in range(10):
    points = []
    r_base = 160 + level * 45
    offset_x = W * 0.48 + math.sin(level * 0.8) * 120
    offset_y = H * 0.55 + math.cos(level * 0.6) * 90
    for angle_deg in range(0, 365, 2):
        angle = math.radians(angle_deg)
        wobble = (math.sin(angle * 5 + level * 0.7) * 25 +
                  math.cos(angle * 3 + level * 0.4) * 18 +
                  math.sin(angle * 7) * 8)
        r = r_base + wobble
        x = offset_x + r * math.cos(angle)
        y = offset_y + r * math.sin(angle)
        points.append((x, y))
    if len(points) > 2:
        if level <= 3:
            color = PETROL
            w = 2 if level <= 1 else 1
        elif level <= 6:
            color = TWILIGHT
            w = 1
        else:
            color = SAND
            w = 1
        draw.line(points, fill=color, width=w, joint="curve")

# ══════════════════════════════════════════════════════════
# LAYER 6: Elevation lines (right side — systematic)
# ══════════════════════════════════════════════════════════
for i in range(30):
    y = H * 0.12 + i * 40
    x_start = W * 0.80
    x_end = W * 0.96
    points = []
    for x in range(int(x_start), int(x_end), 3):
        wave = math.sin((x - x_start) / 25 + i * 0.4) * (6 + i * 0.3)
        points.append((x, y + wave))
    if len(points) > 1:
        draw.line(points, fill=SAND, width=1)

# ══════════════════════════════════════════════════════════
# LAYER 7: Constellation field (top-left)
# ══════════════════════════════════════════════════════════
pts = [(random.uniform(100, W*0.42), random.uniform(100, H*0.32)) for _ in range(60)]
for x, y in pts:
    size = random.choice([1, 1, 2, 2, 3])
    draw_circle(draw, x, y, size, fill=random.choice([PETROL, TWILIGHT]))

for i, (x1, y1) in enumerate(pts):
    for j, (x2, y2) in enumerate(pts):
        if i < j:
            dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            if dist < 100:
                draw_line(draw, x1, y1, x2, y2, fill=LIGHT_GRAY, width=1)

# ══════════════════════════════════════════════════════════
# LAYER 8: Survey marks (crosshairs)
# ══════════════════════════════════════════════════════════
survey = [
    (W*0.15, H*0.12), (W*0.85, H*0.15),
    (W*0.10, H*0.88), (W*0.88, H*0.85),
    (W*0.50, H*0.06), (W*0.50, H*0.94),
    (W*0.08, H*0.50), (W*0.92, H*0.50),
]
for i, (sx, sy) in enumerate(survey):
    s = 16
    draw_line(draw, sx - s, sy, sx + s, sy, fill=ACCENT, width=2)
    draw_line(draw, sx, sy - s, sx, sy + s, fill=ACCENT, width=2)
    draw_circle(draw, sx, sy, s + 5, outline=ACCENT, width=1)
    draw.text((sx + s + 10, sy - 8), f"REF-{i+1:02d}", fill=ACCENT, font=font_accent)

# ══════════════════════════════════════════════════════════
# LAYER 9: Border (double-line survey map frame)
# ══════════════════════════════════════════════════════════
margin = 55
for offset in [0, 6]:
    m = margin + offset
    draw.rectangle([m, m, W-m, H-m], outline=WARM_GRAY, width=1)

# Corner marks — larger, more precise
cs = 35
for cx, cy in [(margin, margin), (W-margin, margin),
               (margin, H-margin), (W-margin, H-margin)]:
    draw_line(draw, cx - cs, cy, cx + cs, cy, fill=PETROL, width=2)
    draw_line(draw, cx, cy - cs, cx, cy + cs, fill=PETROL, width=2)

# ══════════════════════════════════════════════════════════
# LAYER 10: Typography
# ══════════════════════════════════════════════════════════

# Title
title = "DESERT CARTOGRAPHY"
bbox = draw.textbbox((0, 0), title, font=font_title)
tw = bbox[2] - bbox[0]
draw.text(((W - tw) // 2, margin + 20), title, fill=PETROL, font=font_title)

# Thin line under title
draw_line(draw, (W - tw) // 2 - 20, margin + 72,
          (W + tw) // 2 + 20, margin + 72, fill=SAND, width=1)

# Subtitle
subtitle = "A STUDY OF INVISIBLE REAL ESTATE SYSTEMS"
bbox2 = draw.textbbox((0, 0), subtitle, font=font_specimen)
sw = bbox2[2] - bbox2[0]
draw.text(((W - sw) // 2, margin + 82), subtitle, fill=WARM_GRAY, font=font_specimen)

# Arabic accents
draw.text((W * 0.72, H * 0.88), "خريطة الصحراء", fill=PETROL, font=font_arabic)
draw.text((W * 0.62, H * 0.92), "دراسة في الأنظمة العقارية غير المرئية",
          fill=WARM_GRAY, font=font_arabic_sm)

# Specimen labels
labels = [
    (zone_cx + 15*58 + 15, zone_cy - 15, "ZONE \u03b1-7  \u00b7  PRIMARY SURVEY", WARM_GRAY),
    (cluster_cx + 480, cluster_cy - 360, "SECTOR B-12  \u00b7  DENSITY MAP", WARM_GRAY),
    (W * 0.48 - 120, H * 0.55 + 260, "CONTOUR SET \u0394  \u00b7  EQUILIBRIUM", WARM_GRAY),
    (W * 0.82, H * 0.08, "ELEVATION SERIES  \u00b7  LINEAR", WARM_GRAY),
    (W * 0.06, H * 0.06, "CONSTELLATION FIELD  \u00b7  \u03b1", WARM_GRAY),
]
for lx, ly, text, color in labels:
    draw.text((lx, ly), text, fill=color, font=font_accent)

# Measurement scale (bottom)
for i in range(0, W, 200):
    if margin + 40 < i < W - margin - 40:
        draw.text((i, H - margin + 12), f"{i//10}", fill=WARM_GRAY, font=font_micro)
        draw_line(draw, i, H - margin + 5, i, H - margin + 10, fill=WARM_GRAY, width=1)

# Left measurement
for i in range(0, H, 200):
    if margin + 40 < i < H - margin - 40:
        draw.text((margin + 10, i), f"{i//10}", fill=WARM_GRAY, font=font_micro)

# ══════════════════════════════════════════════════════════
# LAYER 11: Accent diagonal
# ══════════════════════════════════════════════════════════
draw_line(draw, W * 0.04, H * 0.15, W * 0.44, H * 0.85,
          fill=ACCENT, width=3)

# Diamond at intersection
ix, iy = W * 0.34, H * 0.50
ds = 8
draw.polygon([(ix, iy-ds), (ix+ds, iy), (ix, iy+ds), (ix-ds, iy)],
             outline=ACCENT, fill=ACCENT)

# ══════════════════════════════════════════════════════════
# Save
# ══════════════════════════════════════════════════════════
output = "canvas/desert_cartography_v2.png"
img.save(output, "PNG", dpi=(300, 300))
print(f"Canvas v2 saved: {output}")
print(f"  Size: {W}x{H} px, 300 DPI")
