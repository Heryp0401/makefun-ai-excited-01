#!/usr/bin/env python3
"""The Whale That Swallowed the Moon.

A humpback whale breaches out of a midnight sea, head to the sky, and
the full moon is caught between its open jaws -- as if the whale is
offering the moon itself to the judge.

Pure standard library Python. Deterministic: fixed seed, no timestamps,
no dict/set iteration order anywhere, so two runs write byte-identical
PNG files. Renders at 2048x2048 with a scanline rasterizer, then
box-downsamples to 1024x1024.

Run:  python3 main.py
Output: $MAKEFUN_OUTPUT_DIR/entry.png (or ./entry.png)
"""

import math
import os
import random
import struct
import zlib

# ---------------------------------------------------------------- config

S = 2                      # supersample factor (render 2048, output 1024)
W = 1024 * S
H = 1024 * S
OUT_W = 1024
OUT_H = 1024
SEED = 20261117

OUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", ".")
OUT_PATH = os.path.join(OUT_DIR, "entry.png")

HORIZON = 648              # y where the sea meets the sky (1024-space)
MOON = (712.0, 318.0)      # moon centre (1024-space)
MOON_R = 185.0

rng = random.Random(SEED)

# ---------------------------------------------------------------- canvas

buf = bytearray(W * H * 3)


def lerp_rgb(a, b, t):
    """Linear blend of two RGB triples; t in [0, 1]."""
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def fill_span(y, x0, x1, rgb):
    """Paint one horizontal run of pixels on scanline y (supersampled)."""
    if y < 0 or y >= H:
        return
    x0 = int(x0)
    x1 = int(x1)
    if x0 < 0:
        x0 = 0
    if x1 > W - 1:
        x1 = W - 1
    if x1 < x0:
        return
    n = x1 - x0 + 1
    base = (y * W + x0) * 3
    buf[base:base + n * 3] = bytes(rgb) * n


def fill_circle(cx, cy, r, rgb):
    """Filled disc, centre and radius in supersampled pixels."""
    r = int(round(r))
    if r <= 0:
        return
    cx = int(round(cx))
    cy = int(round(cy))
    for yy in range(max(0, cy - r), min(H, cy + r + 1)):
        dy = yy - cy
        dx = int(math.sqrt(max(0, r * r - dy * dy)))
        fill_span(yy, cx - dx, cx + dx, rgb)


def fill_polygon(pts, rgb):
    """Even-odd scanline fill of a polygon given in supersampled coords."""
    if len(pts) < 3:
        return
    ymin = max(0, int(math.floor(min(p[1] for p in pts))))
    ymax = min(H - 1, int(math.ceil(max(p[1] for p in pts))))
    n = len(pts)
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                t = (yc - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            fill_span(y, xs[k], xs[k + 1], rgb)


def fill_ellipse(cx, cy, rx, ry, rgb, rot_deg=0.0, steps=72):
    """Filled ellipse, optionally rotated, via a sampled polygon."""
    rot = math.radians(rot_deg)
    cr = math.cos(rot)
    sr = math.sin(rot)
    pts = []
    for i in range(steps):
        a = 2.0 * math.pi * i / steps
        ex = rx * math.cos(a)
        ey = ry * math.sin(a)
        pts.append((cx + ex * cr - ey * sr, cy + ex * sr + ey * cr))
    fill_polygon(pts, rgb)


def stroke(points, radius, rgb, step=3):
    """Thick polyline: a chain of discs along the given points."""
    for i in range(len(points)):
        fill_circle(points[i][0], points[i][1], radius, rgb)
        if i + 1 < len(points):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dist = math.hypot(x2 - x1, y2 - y1)
            n = max(1, int(dist / step))
            for j in range(1, n):
                t = j / n
                fill_circle(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t,
                            radius, rgb)


def cubic(p0, p1, p2, p3, steps):
    """Sample a cubic Bezier curve; returns a list of (x, y) points."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = (mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0]
             + 3 * mt * t * t * p2[0] + t ** 3 * p3[0])
        y = (mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1]
             + 3 * mt * t * t * p2[1] + t ** 3 * p3[1])
        pts.append((x, y))
    return pts


def catmull(points, steps_per_seg=10):
    """Sample a smooth curve through the given control points."""
    pts = [points[0]]
    ext = [points[0]] + list(points) + [points[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for j in range(1, steps_per_seg + 1):
            t = j / steps_per_seg
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            pts.append((x, y))
    return pts


# All scene geometry is authored in 1024-space, then scaled by S.
def P(x, y):
    return (x * S, y * S)


def R(r):
    return r * S


# ---------------------------------------------------------------- palette

SKY_TOP = (7, 11, 32)
SKY_MID = (14, 27, 58)
SKY_HORIZON = (26, 54, 88)
SEA_TOP = (16, 46, 72)
SEA_DEEP = (3, 9, 21)
MOON_FACE = (240, 232, 198)
MOON_CRATER = (216, 208, 172)
MOON_GLOW = (235, 227, 192)
MOON_RIM = (18, 28, 52)
WHALE = (9, 15, 31)
WHALE_BELLY = (16, 26, 48)
RIM_LIGHT = (168, 208, 238)
SPRAY = (190, 220, 240)
FOAM = (205, 228, 242)
REFLECT = (214, 202, 158)
STAR = (235, 240, 255)

# ---------------------------------------------------------------- sky

# Vertical gradient, painted one scanline at a time (fast span fills).
for sy in range(0, HORIZON * S):
    t = sy / float(HORIZON * S)
    if t < 0.55:
        col = lerp_rgb(SKY_TOP, SKY_MID, t / 0.55)
    else:
        col = lerp_rgb(SKY_MID, SKY_HORIZON, (t - 0.55) / 0.45)
    fill_span(sy, 0, W - 1, col)

# ---------------------------------------------------------------- moon glow

def sky_at(y1024):
    """Sky gradient colour at a 1024-space height (reused by the glow)."""
    t = y1024 / float(HORIZON)
    if t < 0.55:
        return lerp_rgb(SKY_TOP, SKY_MID, t / 0.55)
    return lerp_rgb(SKY_MID, SKY_HORIZON, (t - 0.55) / 0.45)


# Concentric rings, outermost first, fading from warm moonlight into the
# night sky. Each ring is painted row by row, blending toward that row's
# own sky colour, so the glow melts into the sky with no disc edge.
# Rings (not per-pixel blending) keep the render fast, and the 2x
# downsample smooths the steps away.
NRINGS = 80
for ring in range(NRINGS, 0, -1):
    frac_out = ring / float(NRINGS)
    frac_in = (ring - 1) / float(NRINGS)
    r_out = (MOON_R + frac_out * 280.0) * S
    r_in = (MOON_R + frac_in * 280.0) * S
    warmth = (1.0 - (frac_out + frac_in) / 2.0) ** 1.6
    gcy = MOON[1] * S
    gcx = MOON[0] * S
    for yy in range(max(0, int(gcy - r_out)),
                    min(HORIZON * S, int(gcy + r_out) + 1)):
        dy = yy - gcy
        dxo = math.sqrt(max(0.0, r_out * r_out - dy * dy))
        dxi = (math.sqrt(max(0.0, r_in * r_in - dy * dy))
               if abs(dy) < r_in else 0.0)
        col = lerp_rgb(sky_at(yy / S), MOON_GLOW, warmth * 0.9)
        fill_span(yy, gcx - dxo, gcx - dxi, col)
        fill_span(yy, gcx + dxi, gcx + dxo, col)

# Moon disc: dark limb ring first, then the bright face, then craters.
fill_circle(MOON[0] * S, MOON[1] * S, (MOON_R + 4) * S, MOON_RIM)
fill_circle(MOON[0] * S, MOON[1] * S, MOON_R * S, MOON_FACE)
for cx, cy, cr in [(658, 272, 30), (762, 362, 36), (792, 268, 19),
                   (676, 382, 17), (728, 296, 13), (700, 340, 22),
                   (812, 330, 12)]:
    fill_circle(cx * S, cy * S, cr * S, MOON_CRATER)

# ---------------------------------------------------------------- stars

for _ in range(300):
    sx = rng.uniform(0, 1024)
    sy = rng.uniform(0, 610)
    if math.hypot(sx - MOON[0], sy - MOON[1]) < MOON_R + 34:
        continue
    sr = rng.choice([1.0, 1.0, 1.4, 1.8, 2.4])
    bright = rng.uniform(0.45, 1.0)
    col = lerp_rgb(SKY_TOP, STAR, bright)
    fill_circle(sx * S, sy * S, sr * S, col)

# A few four-point sparkles for the brightest stars.
for sx, sy, arm in [(150, 120, 9), (905, 120, 8), (60, 430, 7),
                    (330, 90, 7), (985, 300, 8), (430, 170, 6)]:
    fill_span(int(sy * S), int((sx - arm) * S), int((sx + arm) * S), STAR)
    for yy in range(int((sy - arm) * S), int((sy + arm) * S) + 1):
        fill_span(yy, int(sx * S), int(sx * S), STAR)

# ---------------------------------------------------------------- sea

for sy in range(HORIZON * S, H):
    t = (sy - HORIZON * S) / float(H - HORIZON * S)
    col = lerp_rgb(SEA_TOP, SEA_DEEP, t ** 1.15)
    fill_span(sy, 0, W - 1, col)

# Moonlight column on the water: jittered golden streaks, fading down.
for sy in range(HORIZON + 8, 1000, 7):
    depth = (sy - HORIZON) / 352.0
    width = 150.0 * math.exp(-depth * 1.4) * (0.55 + 0.45 * rng.random())
    cx = MOON[0] + rng.uniform(-26, 26)
    sea_col = lerp_rgb(SEA_TOP, SEA_DEEP, (sy - HORIZON) / 376.0)
    col = lerp_rgb(sea_col, REFLECT, max(0.08, 0.85 - depth * 0.9))
    fill_span(sy * S, (cx - width / 2) * S, (cx + width / 2) * S, col)

# Wave streaks: thin lighter and darker horizontal marks across the sea.
for _ in range(110):
    wy = rng.uniform(HORIZON + 12, 1010)
    wx = rng.uniform(0, 900)
    wl = rng.uniform(18, 170)
    sea_col = lerp_rgb(SEA_TOP, SEA_DEEP, (wy - HORIZON) / 376.0)
    if rng.random() < 0.6:
        col = lerp_rgb(sea_col, (90, 130, 165), rng.uniform(0.15, 0.45))
    else:
        col = lerp_rgb(sea_col, SEA_DEEP, 0.5)
    thick = rng.choice([2, 2, 3, 4])
    for yy in range(int(wy * S), int(wy * S) + thick * S):
        fill_span(yy, wx * S, (wx + wl) * S, col)

# ---------------------------------------------------------------- whale

# Spine of the breaching body: tail low-left, head high-right.
SPINE = cubic((118, 812), (300, 716), (520, 556), (688, 452), 48)

# Half-width profile along the spine (t, half-width in 1024-space).
WIDTH_PROFILE = [(0.00, 22), (0.15, 48), (0.35, 78), (0.55, 92),
                 (0.75, 98), (0.90, 88), (1.00, 70)]


def width_at(t):
    for i in range(len(WIDTH_PROFILE) - 1):
        t0, w0 = WIDTH_PROFILE[i]
        t1, w1 = WIDTH_PROFILE[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return w0 + (w1 - w0) * f
    return WIDTH_PROFILE[-1][1]


upper_edge = []
lower_edge = []
for i, (sx, sy) in enumerate(SPINE):
    t = i / (len(SPINE) - 1)
    if i + 1 < len(SPINE):
        dx = SPINE[i + 1][0] - sx
        dy = SPINE[i + 1][1] - sy
    else:
        dx = sx - SPINE[i - 1][0]
        dy = sy - SPINE[i - 1][1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d          # normal; upper edge is -normal here
    w = width_at(t)
    upper_edge.append((sx - nx * w, sy - ny * w))
    lower_edge.append((sx + nx * w, sy + ny * w))

body_pts = [P(x, y) for x, y in upper_edge]
body_pts += [P(x, y) for x, y in reversed(lower_edge)]
fill_polygon(body_pts, WHALE)

# Tail fluke: two lobes with a notch, at the low-left end of the spine.
fluke = [(122, 800), (78, 748), (38, 722), (58, 772), (80, 812),
         (62, 872), (96, 862), (138, 838), (146, 812)]
fill_polygon([P(x, y) for x, y in fluke], WHALE)

# Dorsal fin: small triangle on the back, a third of the way up the body.
dorsal = [(168, 738), (206, 688), (228, 736)]
fill_polygon([P(x, y) for x, y in dorsal], WHALE)

# Pectoral fin: a long tapered fin curving back from the belly.
fin_curve = catmull([(448, 602), (498, 668), (538, 752), (528, 798),
                     (496, 716), (452, 636), (436, 606)], 8)
fill_polygon([P(x, y) for x, y in fin_curve], WHALE)

# Head: a broad ellipse where spine meets the jaws.
fill_ellipse(692 * S, 448 * S, 96 * S, 80 * S, WHALE, rot_deg=-32)

# Upper jaw: a curved flap arcing over the top of the moon, like a lid
# about to close -- the moon sits in the open mouth.
upper_jaw = catmull([(640, 430), (690, 340), (770, 255), (855, 205),
                     (930, 235), (935, 285), (880, 300), (810, 330),
                     (740, 385), (685, 435)], 8)
fill_polygon([P(x, y) for x, y in upper_jaw], WHALE)

# Lower jaw: a rounded shelf under the moon, holding it up.
lower_jaw = catmull([(640, 462), (710, 478), (810, 492), (890, 470),
                     (912, 505), (870, 552), (770, 565), (685, 530),
                     (645, 490)], 8)
fill_polygon([P(x, y) for x, y in lower_jaw], WHALE)

# Eye: a small pale dot on the head, looking up at the moon.
fill_circle(722 * S, 408 * S, 6 * S, (205, 222, 238))
fill_circle(723 * S, 408 * S, 3 * S, (8, 12, 24))

# Pale rim light along the whale's back and along the upper jaw -- the
# moonlight catching the edge of the breach.
rim_pts = [P(x, y) for x, y in upper_edge]
stroke(rim_pts, 3.2 * S, RIM_LIGHT)
jaw_rim = catmull([(640, 430), (690, 340), (770, 255), (855, 205),
                   (930, 235), (935, 285)], 8)
stroke([P(x, y) for x, y in jaw_rim], 3.0 * S, RIM_LIGHT)
stroke([P(x, y) for x, y in lower_jaw[:6]], 2.4 * S,
       lerp_rgb(RIM_LIGHT, WHALE, 0.45))

# Throat grooves: faint lines fanning from the chin down the belly.
for k in range(3):
    groove = catmull([(640 + k * 26, 470 + k * 8),
                      (560 + k * 22, 540 + k * 10),
                      (470 + k * 18, 610 + k * 8),
                      (390 + k * 14, 668)], 8)
    stroke([P(x, y) for x, y in groove], 1.8 * S,
           lerp_rgb(WHALE, WHALE_BELLY, 0.9))

# Pale speckles on the flank (humpbacks are mottled).
for _ in range(90):
    i = rng.randrange(len(SPINE))
    t = i / (len(SPINE) - 1)
    sx, sy = SPINE[i]
    if i + 1 < len(SPINE):
        dx = SPINE[i + 1][0] - sx
        dy = SPINE[i + 1][1] - sy
    else:
        dx = sx - SPINE[i - 1][0]
        dy = sy - SPINE[i - 1][1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d
    off = rng.uniform(-0.62, 0.62) * width_at(t)
    px = sx + nx * off
    py = sy + ny * off
    fill_circle(px * S, py * S, rng.uniform(1.2, 2.6) * S,
                lerp_rgb(WHALE, (200, 220, 235), rng.uniform(0.25, 0.6)))

# ---------------------------------------------------------------- spray

# Exploding droplets where the tail leaves the water, plus foam rings.
for _ in range(320):
    ang = rng.uniform(0, 2 * math.pi)
    dist = abs(rng.gauss(0, 95))
    cx = 150 + math.cos(ang) * dist * 1.25
    cy = 772 + math.sin(ang) * dist * 0.8 - dist * 0.25
    if cy > HORIZON + 160 or cx < 0 or cx > 420:
        continue
    r = rng.uniform(1.0, 4.2) * (1.0 - dist / 260.0) + 0.8
    col = lerp_rgb(SPRAY, FOAM, rng.random())
    fill_circle(cx * S, cy * S, r * S, col)

# Foam collars where the body pierces the surface: small and muted so
# the tail fluke stays visible above them.
for cx, cy, rx, ry in [(150, 814, 84, 10), (185, 830, 62, 8),
                       (120, 838, 46, 7), (250, 814, 52, 7)]:
    for yy in range(int((cy - ry) * S), int((cy + ry) * S) + 1):
        dy = (yy / S - cy) / ry
        if abs(dy) > 1:
            continue
        dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
        fill_span(yy, (cx - dx) * S, (cx + dx) * S,
                  lerp_rgb(FOAM, SEA_TOP, 0.45))

# A few droplets flung up along the back, catching the moonlight.
for _ in range(60):
    i = rng.randrange(len(upper_edge))
    ux, uy = upper_edge[i]
    fill_circle((ux + rng.uniform(-14, 14)) * S,
                (uy - rng.uniform(4, 42)) * S,
                rng.uniform(1.0, 2.6) * S, SPRAY)

# ---------------------------------------------------------------- downsample

# 2x2 box average, 2048 -> 1024. Pure integer math, fully deterministic.
out = bytearray(OUT_W * OUT_H * 3)
src_row = W * 3
for oy in range(OUT_H):
    y0 = oy * 2
    dst_base = oy * OUT_W * 3
    top = y0 * src_row
    bot = (y0 + 1) * src_row
    for ox in range(OUT_W):
        x0 = ox * 6
        d = dst_base + ox * 3
        out[d] = (buf[top + x0] + buf[top + x0 + 3]
                  + buf[bot + x0] + buf[bot + x0 + 3] + 2) // 4
        out[d + 1] = (buf[top + x0 + 1] + buf[top + x0 + 4]
                      + buf[bot + x0 + 1] + buf[bot + x0 + 4] + 2) // 4
        out[d + 2] = (buf[top + x0 + 2] + buf[top + x0 + 5]
                      + buf[bot + x0 + 2] + buf[bot + x0 + 5] + 2) // 4

# ---------------------------------------------------------------- png encode


def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def encode_png(w, h, rgb):
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)  # filter: None
        raw += rgb[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 6)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


png = encode_png(OUT_W, OUT_H, out)
os.makedirs(OUT_DIR, exist_ok=True)
with open(OUT_PATH, "wb") as f:
    f.write(png)
print("wrote %s (%d bytes, %dx%d)" % (OUT_PATH, len(png), OUT_W, OUT_H))
