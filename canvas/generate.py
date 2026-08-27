#!/usr/bin/env python3
"""
Desert Cartography — A visual study of invisible real estate systems.
Generates a museum-quality PNG composition following the design philosophy.
"""
import math
import random
from PIL import Image, ImageDraw, ImageFont

# ── Canvas Setup ──
W, H = 2400, 3200
img = Image.new("RGB", (W, H), "#F5F0E8")  # aged parchment
draw = ImageDraw.Draw(img)

# ── Palette (Geological) ──
SAND      = "#C8B896"  # sandstone ochre
LIMESTONE = "#E8E0D0"  # limestone white
PETROL    = "#1A1A2E"  # petroleum black
TWILIGHT  = "#2C5F7C"  # Gulf twilight blue
ACCENT    = "#B85C38"  # surveyor's red-orange
WARM_GRAY = "#8A8070"
LIGHT_GRAY = "#D5CFC3"

# ── Fonts ──
def load_font(name, size):
    paths = [
        f"C:/Windows/Fonts/{name}",
        f"C:/Users/hello/AppData/Local/Microsoft/Windows/Fonts/{name}",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

font_label = load_font("tahoma.ttf", 22)
font_title = load_font("tahoma.ttf", 36)
font_specimen = load_font("tahomabd.ttf", 18)
font_accent = load_font("tahoma.ttf", 14)
font_arabic = load_font("tahoma.ttf", 28)
font_arabic_sm = load_font("tahoma.ttf", 16)

random.seed(42)  # reproducible

# ── Helper: draw with transparency via overlay ──
def draw_circle(draw, cx, cy, r, outline=None, fill=None, width=1):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=outline, fill=fill, width=width)

def draw_line(draw, x1, y1, x2, y2, fill, width=1):
    draw.line([(x1,y1),(x2,y2)], fill=fill, width=width)

# ══════════════════════════════════════════════════════════
# LAYER 1: Base grid (faint surveying grid)
# ══════════════════════════════════════════════════════════
grid_spacing = 60
for x in range(0, W, grid_spacing):
    opacity = 0.03 + 0.02 * math.sin(x / 200)
    c = int(200 + 15 * math.sin(x / 300))
    draw_line(draw, x, 0, x, H, fill=f"#{c:02x}{c-10:02x}{c-20:02x}", width=1)
for y in range(0, H, grid_spacing):
    c = int(200 + 15 * math.cos(y / 300))
    draw_line(draw, 0, y, W, y, fill=f"#{c:02x}{c-10:02x}{c-20:02x}", width=1)

# ══════════════════════════════════════════════════════════
# LAYER 2: Concentric zone system (top-right quadrant)
# ══════════════════════════════════════════════════════════
zone_cx, zone_cy = W * 0.72, H * 0.35
for i in range(12, 0, -1):
    r = i * 65
    alpha = max(15, 60 - i * 4)
    color = TWILIGHT if i % 3 == 0 else SAND
    draw_circle(draw, zone_cx, zone_cy, r, outline=color, width=1 if i > 6 else 2)

# Radial lines from zone center
for angle_deg in range(0, 360, 15):
    angle = math.radians(angle_deg)
    r_inner = 80
    r_outer = 12 * 65
    x1 = zone_cx + r_inner * math.cos(angle)
    y1 = zone_cy + r_inner * math.sin(angle)
    x2 = zone_cx + r_outer * math.cos(angle)
    y2 = zone_cy + r_outer * math.sin(angle)
    w = 1 if angle_deg % 45 != 0 else 2
    draw_line(draw, x1, y1, x2, y2, fill=LIGHT_GRAY if w == 1 else SAND, width=w)

# Scatter points within zones (data points)
for _ in range(300):
    angle = random.uniform(0, 2 * math.pi)
    dist = random.gauss(0, 350)
    x = zone_cx + dist * math.cos(angle)
    y = zone_cy + dist * math.sin(angle)
    if 100 < x < W - 100 and 100 < y < H - 100:
        size = random.choice([1, 1, 1, 2, 2, 3])
        color = random.choice([PETROL, TWILIGHT, ACCENT, SAND])
        draw_circle(draw, x, y, size, fill=color)

# ══════════════════════════════════════════════════════════
# LAYER 3: Dense grid cluster (bottom-left) — "market density"
# ══════════════════════════════════════════════════════════
cluster_cx, cluster_cy = W * 0.28, H * 0.72
for i in range(20):
    for j in range(15):
        x = cluster_cx - 400 + i * 42
        y = cluster_cy - 280 + j * 40
        # Vary density based on distance from center
        dx = i - 10
        dy = j - 7
        dist = math.sqrt(dx*dx + dy*dy)
        if random.random() < max(0.1, 0.9 - dist * 0.06):
            size = random.choice([3, 4, 5, 6, 8])
            color = random.choice([PETROL, TWILIGHT, ACCENT, SAND, WARM_GRAY])
            draw_circle(draw, x, y, size, fill=color)

# Grid lines connecting cluster nodes
for i in range(20):
    x = cluster_cx - 400 + i * 42
    draw_line(draw, x, cluster_cy - 280, x, cluster_cy + 280,
              fill=LIGHT_GRAY, width=1)
for j in range(15):
    y = cluster_cy - 280 + j * 40
    draw_line(draw, cluster_cx - 400, y, cluster_cx + 400, y,
              fill=LIGHT_GRAY, width=1)

# ══════════════════════════════════════════════════════════
# LAYER 4: Topographic contour lines (organic)
# ══════════════════════════════════════════════════════════
for level in range(8):
    points = []
    r_base = 200 + level * 50
    offset_x = W * 0.5 + math.sin(level * 0.7) * 100
    offset_y = H * 0.55 + math.cos(level * 0.5) * 80
    for angle_deg in range(0, 365, 3):
        angle = math.radians(angle_deg)
        wobble = math.sin(angle * 5 + level) * 30 + math.cos(angle * 3) * 20
        r = r_base + wobble
        x = offset_x + r * math.cos(angle)
        y = offset_y + r * math.sin(angle)
        points.append((x, y))
    if len(points) > 2:
        color = SAND if level % 2 == 0 else LIGHT_GRAY
        draw.line(points, fill=color, width=1, joint="curve")

# ══════════════════════════════════════════════════════════
# LAYER 5: Surveying marks (crosshairs + reference points)
# ══════════════════════════════════════════════════════════
survey_points = [
    (W*0.15, H*0.12), (W*0.85, H*0.15),
    (W*0.10, H*0.88), (W*0.88, H*0.85),
    (W*0.50, H*0.08), (W*0.50, H*0.92),
    (W*0.12, H*0.50), (W*0.90, H*0.50),
]
for i, (sx, sy) in enumerate(survey_points):
    # Crosshair
    size = 18
    draw_line(draw, sx - size, sy, sx + size, sy, fill=ACCENT, width=2)
    draw_line(draw, sx, sy - size, sx, sy + size, fill=ACCENT, width=2)
    draw_circle(draw, sx, sy, size + 4, outline=ACCENT, width=1)
    # Reference number
    draw.text((sx + size + 8, sy - 10), f"REF-{i+1:02d}", fill=ACCENT, font=font_accent)

# ══════════════════════════════════════════════════════════
# LAYER 6: Parallel elevation lines (right side)
# ══════════════════════════════════════════════════════════
for i in range(25):
    y = H * 0.15 + i * 45
    x_start = W * 0.78
    x_end = W * 0.95
    # Vary the line with slight waves
    points = []
    for x in range(int(x_start), int(x_end), 4):
        wave = math.sin((x - x_start) / 30 + i * 0.5) * (8 + i * 0.5)
        points.append((x, y + wave))
    if len(points) > 1:
        draw.line(points, fill=SAND, width=1)

# ══════════════════════════════════════════════════════════
# LAYER 7: Scatter field (top-left — data constellation)
# ══════════════════════════════════════════════════════════
for _ in range(150):
    x = random.uniform(80, W * 0.45)
    y = random.uniform(80, H * 0.35)
    size = random.choice([1, 1, 2, 2, 2, 3])
    color = random.choice([PETROL, TWILIGHT, WARM_GRAY])
    draw_circle(draw, x, y, size, fill=color)

# Connect nearby points with faint lines (constellation)
points_list = [(random.uniform(80, W*0.45), random.uniform(80, H*0.35)) for _ in range(40)]
for i, (x1, y1) in enumerate(points_list):
    for j, (x2, y2) in enumerate(points_list):
        if i < j:
            dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            if dist < 120:
                draw_line(draw, x1, y1, x2, y2, fill=LIGHT_GRAY, width=1)

# ══════════════════════════════════════════════════════════
# LAYER 8: Decorative border (survey map frame)
# ══════════════════════════════════════════════════════════
margin = 60
# Double-line border
for offset in [0, 8]:
    m = margin + offset
    draw.rectangle([m, m, W-m, H-m], outline=WARM_GRAY, width=1)

# Corner marks
corner_size = 30
for cx, cy in [(margin, margin), (W-margin, margin),
               (margin, H-margin), (W-margin, H-margin)]:
    draw_line(draw, cx - corner_size, cy, cx + corner_size, cy, fill=PETROL, width=2)
    draw_line(draw, cx, cy - corner_size, cx, cy + corner_size, fill=PETROL, width=2)

# ══════════════════════════════════════════════════════════
# LAYER 9: Typography — specimen labels & Arabic accents
# ══════════════════════════════════════════════════════════

# Title — top center
title = "DESERT CARTOGRAPHY"
bbox = draw.textbbox((0, 0), title, font=font_title)
tw = bbox[2] - bbox[0]
draw.text(((W - tw) // 2, margin + 25), title, fill=PETROL, font=font_title)

# Subtitle
subtitle = "A STUDY OF INVISIBLE REAL ESTATE SYSTEMS"
bbox2 = draw.textbbox((0, 0), subtitle, font=font_specimen)
sw = bbox2[2] - bbox2[0]
draw.text(((W - sw) // 2, margin + 70), subtitle, fill=WARM_GRAY, font=font_specimen)

# Arabic accent — bottom right area
arabic_text = "خريطة الصحراء"
draw.text((W * 0.70, H * 0.88), arabic_text, fill=PETROL, font=font_arabic)
arabic_sub = "دراسة في الأنظمة العقارية غير المرئية"
draw.text((W * 0.60, H * 0.92), arabic_sub, fill=WARM_GRAY, font=font_arabic_sm)

# Specimen labels near zones
labels = [
    (zone_cx + 14*65 + 20, zone_cy - 20, "ZONE α-7  ·  PRIMARY SURVEY"),
    (cluster_cx + 420, cluster_cy - 300, "SECTOR B-12  ·  DENSITY MAP"),
    (W * 0.50 - 100, H * 0.55 + 250, "CONTOUR SET Δ  ·  EQUILIBRIUM"),
    (W * 0.80, H * 0.10, "ELEVATION SERIES  ·  LINEAR"),
    (W * 0.08, H * 0.08, "CONSTELLATION FIELD  ·  α"),
]
for lx, ly, text in labels:
    draw.text((lx, ly), text, fill=WARM_GRAY, font=font_accent)

# Measurement annotations along bottom
for i in range(0, W, 200):
    if i > margin + 40 and i < W - margin - 40:
        draw.text((i, H - margin + 15), f"{i//10}", fill=WARM_GRAY, font=font_accent)
        draw_line(draw, i, H - margin + 5, i, H - margin + 12, fill=WARM_GRAY, width=1)

# Left-side measurement
for i in range(0, H, 200):
    if i > margin + 40 and i < H - margin - 40:
        draw.text((margin + 12, i), f"{i//10}", fill=WARM_GRAY, font=font_accent)

# ══════════════════════════════════════════════════════════
# LAYER 10: Final accent — single bold element
# ══════════════════════════════════════════════════════════
# One thick accent line cutting diagonally through composition
draw_line(draw, W * 0.05, H * 0.15, W * 0.45, H * 0.85,
          fill=ACCENT, width=3)

# Small diamond marker at the intersection with zone system
ix = W * 0.35
iy = H * 0.50
ds = 8
draw.polygon([(ix, iy-ds), (ix+ds, iy), (ix, iy+ds), (ix-ds, iy)],
             outline=ACCENT, fill=ACCENT)

# ══════════════════════════════════════════════════════════
# Save
# ══════════════════════════════════════════════════════════
output_path = "canvas/desert_cartography.png"
img.save(output_path, "PNG", dpi=(300, 300))
print(f"✓ Canvas saved: {output_path}")
print(f"  Size: {W}x{H} px, 300 DPI")
