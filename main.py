#!/usr/bin/env python3
"""The Whale That Swallowed the Moon — make.fun ai-excited-01 entry.

Pure-stdlib renderer (Python 3, no libraries): a hand-written PNG encoder
plus a scanline rasterizer with 2x supersampling (scene rasterized at
2048x2048, downsampled to 1024x1024). Deterministic: fixed seed, no
timestamps, no dict/set ordering — two runs write byte-identical PNGs.

Scene: a humpback whale breaches out of a midnight sea, head-first toward
the sky, and the full moon is caught in its open jaws — scale, momentum,
and a twist, not a stock explosion.

Writes entry.png to $MAKEFUN_OUTPUT_DIR (default ./out).
"""

import math
import os
import random
import struct
import zlib

W = H = 1024
SS = 2
IW = IH = W * SS
SEED = 20261116
HORIZON = 640  # 1024-space y of the horizon

# ---------------------------------------------------------------- palette
SKY_TOP = (6, 11, 32)
SKY_MID = (13, 30, 61)
SKY_HOR = (18, 63, 92)
SEA_TOP = (14, 51, 73)
SEA_DEEP = (4, 16, 28)
MOON = (247, 240, 218)
MARIA = (206, 194, 164)
GLOW = (255, 238, 194)
WHALE = (10, 22, 38)
MOUTH = (5, 11, 20)
RIM = (168, 220, 255)
RIM_CORE = (232, 246, 255)
FOAM = (207, 234, 255)
WHITE = (235, 245, 255)
MOONLIGHT = (255, 233, 176)
WAVE = (26, 74, 102)
DARK = (2, 4, 10)
LIMB = (180, 168, 130)

MOON_C = (720, 300)
MOON_R = 140

# ------------------------------------------------------- framebuffer planes
Rp = bytearray(IW * IH)
Gp = bytearray(IW * IH)
Bp = bytearray(IW * IH)
PLANES = (Rp, Gp, Bp)

_lut_cache = {}


def _lut(channel_value, alpha):
    """256-entry map old -> round(old*(1-a) + c*a), cached by (c, a)."""
    key = (channel_value, alpha)
    lut = _lut_cache.get(key)
    if lut is None:
        inv = 1.0 - alpha
        lut = bytes(
            min(255, max(0, int(round(i * inv + channel_value * alpha))))
            for i in range(256)
        )
        _lut_cache[key] = lut
    return lut


def hspan(y, x0, x1, color):
    """Solid horizontal span on row y (internal coords, x0 inclusive)."""
    x0 = max(0, x0)
    x1 = min(IW, x1)
    if x1 <= x0 or y < 0 or y >= IH:
        return
    base = y * IW
    n = x1 - x0
    Rp[base + x0:base + x1] = bytes((color[0],)) * n
    Gp[base + x0:base + x1] = bytes((color[1],)) * n
    Bp[base + x0:base + x1] = bytes((color[2],)) * n


def hspan_blend(y, x0, x1, color, alpha):
    """Constant-alpha blend over a horizontal span (C-speed via translate)."""
    if alpha <= 0.0:
        return
    x0 = max(0, x0)
    x1 = min(IW, x1)
    if x1 <= x0 or y < 0 or y >= IH:
        return
    a = round(alpha * 255) / 255.0
    base = y * IW
    for plane, c in zip(PLANES, color):
        lut = _lut(c, a)
        plane[base + x0:base + x1] = plane[base + x0:base + x1].translate(lut)


def blend_px(x, y, color, alpha):
    """Single-pixel alpha blend."""
    if alpha <= 0.0 or x < 0 or x >= IW or y < 0 or y >= IH:
        return
    i = y * IW + x
    inv = 1.0 - alpha
    Rp[i] = min(255, max(0, int(round(Rp[i] * inv + color[0] * alpha))))
    Gp[i] = min(255, max(0, int(round(Gp[i] * inv + color[1] * alpha))))
    Bp[i] = min(255, max(0, int(round(Bp[i] * inv + color[2] * alpha))))


def _span_aa(y, x0f, x1f, color, alpha):
    """Anti-aliased span: solid interior, fractional coverage on edge pixels."""
    if y < 0 or y >= IH or alpha <= 0.0:
        return
    if x1f <= 0.0 or x0f >= IW:
        return
    x0f = max(x0f, 0.0)
    x1f = min(x1f, float(IW))
    if x1f - x0f <= 0.0:
        return
    i0 = math.floor(x0f)
    i1 = math.floor(x1f)
    if i0 == i1:
        blend_px(i0, y, color, (x1f - x0f) * alpha)
        return
    xs = math.ceil(x0f)
    xe = math.floor(x1f)  # solid pixels are [xs, xe)
    if xs < xe:
        if alpha >= 1.0:
            hspan(y, xs, xe, color)
        else:
            hspan_blend(y, xs, xe, color, alpha)
    if i0 < xs and 0 <= i0 < IW:
        blend_px(i0, y, color, (i0 + 1.0 - x0f) * alpha)
    if i1 >= xs and i1 < IW and x1f - i1 > 0.0:
        blend_px(i1, y, color, (x1f - i1) * alpha)


def disc(cx, cy, r, color, alpha=1.0):
    """Filled circle (internal coords)."""
    y0 = max(0, int(math.floor(cy - r)))
    y1 = min(IH - 1, int(math.ceil(cy + r)))
    r2 = r * r
    for y in range(y0, y1 + 1):
        dy = (y + 0.5) - cy
        d = r2 - dy * dy
        if d <= 0.0:
            continue
        dx = math.sqrt(d)
        _span_aa(y, cx - dx, cx + dx, color, alpha)


def ellipse(cx, cy, rx, ry, color, alpha=1.0):
    """Filled axis-aligned ellipse (internal coords)."""
    y0 = max(0, int(math.floor(cy - ry)))
    y1 = min(IH - 1, int(math.ceil(cy + ry)))
    for y in range(y0, y1 + 1):
        t = ((y + 0.5) - cy) / ry
        d = 1.0 - t * t
        if d <= 0.0:
            continue
        dx = rx * math.sqrt(d)
        _span_aa(y, cx - dx, cx + dx, color, alpha)


def annulus(cx, cy, r_out, r_in, color, alpha):
    """Ring between radii r_out (outer) and r_in (inner), internal coords."""
    y0 = max(0, int(math.floor(cy - r_out)))
    y1 = min(IH - 1, int(math.ceil(cy + r_out)))
    ro2 = r_out * r_out
    ri2 = r_in * r_in
    for y in range(y0, y1 + 1):
        dy = (y + 0.5) - cy
        d = ro2 - dy * dy
        if d <= 0.0:
            continue
        dxo = math.sqrt(d)
        di = ri2 - dy * dy
        if di > 0.0:
            dxi = math.sqrt(di)
            _span_aa(y, cx - dxo, cx - dxi, color, alpha)
            _span_aa(y, cx + dxi, cx + dxo, color, alpha)
        else:
            _span_aa(y, cx - dxo, cx + dxo, color, alpha)


def radial_gradient(cx, cy, r_outer, r_inner, color, peak, rings=28, power=1.6):
    """Smooth radial falloff: alpha = peak * (1 - s) ** power, s in [0, 1]
    from r_inner (peak) to r_outer (0). Each pixel blended exactly once."""
    for k in range(rings):
        r_out = r_outer - k * (r_outer - r_inner) / rings
        r_in = r_outer - (k + 1) * (r_outer - r_inner) / rings
        r_mid = (r_out + r_in) / 2.0
        s = (r_mid - r_inner) / (r_outer - r_inner)
        a = peak * (1.0 - s) ** power
        if a > 0.002:
            annulus(cx, cy, r_out, r_in, color, a)


def polygon_fill(pts, color, alpha=1.0):
    """Scanline fill of a simple polygon (internal coords), even-odd rule,
    with fractional edge coverage."""
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    y0 = max(0, int(math.floor(min(ys))))
    y1 = min(IH - 1, int(math.ceil(max(ys))))
    n = len(pts)
    for y in range(y0, y1 + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            x1, y1p = pts[i]
            x2, y2p = pts[(i + 1) % n]
            if y1p == y2p:
                continue
            if (y1p <= yc < y2p) or (y2p <= yc < y1p):
                xs.append(x1 + (yc - y1p) * (x2 - x1) / (y2p - y1p))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            _span_aa(y, xs[k], xs[k + 1], color, alpha)


def spline(pts, closed=False, subdiv=12):
    """Catmull-Rom spline through control points (any coordinate space)."""
    n = len(pts)
    out = []
    count = n if closed else n - 1
    for i in range(count):
        if closed:
            p0 = pts[(i - 1) % n]
            p1 = pts[i % n]
            p2 = pts[(i + 1) % n]
            p3 = pts[(i + 2) % n]
        else:
            p0 = pts[max(i - 1, 0)]
            p1 = pts[i]
            p2 = pts[min(i + 1, n - 1)]
            p3 = pts[min(i + 2, n - 1)]
        for j in range(subdiv):
            t = j / subdiv
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            yy = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, yy))
    return out


def ribbon(pts, w_out, w_in, color, alpha, side=1):
    """Light ribbon along a polyline (internal coords). side flips the
    outward normal; tune per edge after looking at the render."""
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        ln = math.hypot(dx, dy)
        if ln == 0:
            continue
        nx = -dy / ln * side
        ny = dx / ln * side
        quad = [
            (x1 + nx * w_out, y1 + ny * w_out),
            (x2 + nx * w_out, y2 + ny * w_out),
            (x2 - nx * w_in, y2 - ny * w_in),
            (x1 - nx * w_in, y1 - ny * w_in),
        ]
        polygon_fill(quad, color, alpha)


def vgrad(y0, y1, c0, c1):
    """Vertical gradient over internal rows [y0, y1)."""
    y0i = max(0, int(y0))
    y1i = min(IH, int(y1))
    n = max(1, y1i - y0i)
    for y in range(y0i, y1i):
        t = (y - y0i) / n
        c = (round(c0[0] + (c1[0] - c0[0]) * t),
             round(c0[1] + (c1[1] - c0[1]) * t),
             round(c0[2] + (c1[2] - c0[2]) * t))
        hspan(y, 0, IW, c)


def S(pts):
    """Scale 1024-space points to internal resolution."""
    return [(x * SS, y * SS) for x, y in pts]


# ------------------------------------------------------------------- scene
def render():
    rng = random.Random(SEED)
    hz = HORIZON * SS
    mcx, mcy = MOON_C[0] * SS, MOON_C[1] * SS
    mr = MOON_R * SS

    # 1. sky
    vgrad(0, hz * 0.55, SKY_TOP, SKY_MID)
    vgrad(hz * 0.55, hz, SKY_MID, SKY_HOR)

    # 2. stars (skip the moon disc)
    for _ in range(240):
        x = rng.uniform(0, W)
        y = rng.uniform(0, 615)
        if math.hypot(x - MOON_C[0], y - MOON_C[1]) < MOON_R + 10:
            continue
        r = rng.uniform(1.0, 2.6) * SS
        a = rng.uniform(0.3, 1.0)
        disc(x * SS, y * SS, r, WHITE, a)
    for _ in range(8):  # glint stars: little crosses
        x = rng.uniform(40, W - 40) * SS
        y = rng.uniform(20, 560) * SS
        if math.hypot(x - mcx, y - mcy) < (MOON_R + 40) * SS:
            continue
        ln = rng.uniform(8, 14) * SS
        wd = 2 * SS
        a = rng.uniform(0.5, 0.9)
        hspan_blend(int(y), int(x - ln / 2), int(x + ln / 2), WHITE, a)
        for yy in range(int(y - ln / 2), int(y + ln / 2)):
            hspan_blend(yy, int(x - wd / 2), int(x + wd / 2), WHITE, a)

    # 3. moon glow
    radial_gradient(mcx, mcy, 380 * SS, 150 * SS, GLOW, 0.5, rings=48, power=1.6)

    # 4. mouth interior (dark wedge the moon sits in; moon drawn over it)
    polygon_fill(S([(630, 300), (878, 228), (868, 438), (645, 415)]), MOUTH)

    # 5. moon disc, maria, limb darkening
    disc(mcx, mcy, mr, MOON)
    for (x, y, r) in [(665, 255, 34), (765, 335, 28), (700, 365, 42),
                      (785, 245, 20), (645, 325, 16)]:
        disc(x * SS, y * SS, r * SS, MARIA, 0.28)
    radial_gradient(mcx, mcy, mr, mr * 0.9, LIMB, 0.18, rings=6, power=1.0)

    # 6. sea
    vgrad(hz, IH, SEA_TOP, SEA_DEEP)

    # 7. moonlight column on the water (irregular shimmering dashes)
    yy = 648
    while yy < 1000:
        depth = (yy - 648) / 352.0
        wd = rng.uniform(30, 170) * (1.0 - depth * 0.4)
        cx = 720 + rng.uniform(-25, 25)
        a = 0.5 * (1.0 - depth) + 0.05
        y0 = yy * SS
        tall = rng.choice((SS, SS * 2, SS * 2))
        for row in range(y0, y0 + tall):
            hspan_blend(row, int((cx - wd / 2) * SS), int((cx + wd / 2) * SS),
                        MOONLIGHT, a)
        yy += rng.randint(6, 12)

    # 8. wave bands
    for _ in range(16):
        x = rng.uniform(100, 924)
        y = rng.uniform(660, 1000)
        rx = rng.uniform(60, 220)
        ry = rng.uniform(2, 4.5)
        a = rng.uniform(0.15, 0.4)
        ellipse(x * SS, y * SS, rx * SS, ry * SS, WAVE, a)
    for _ in range(6):  # bright crests near the moonlight column
        x = rng.uniform(620, 820)
        y = rng.uniform(660, 900)
        rx = rng.uniform(40, 120)
        ry = rng.uniform(2, 3.5)
        ellipse(x * SS, y * SS, rx * SS, ry * SS, MOONLIGHT,
                rng.uniform(0.2, 0.35))

    # 9. the whale — one silhouette: thick torpedo body flowing into the
    #    head and the upper jaw; the lower jaw is a separate wedge, so the
    #    moon shows in the open mouth between them.
    body = spline([(110, 790), (200, 720), (290, 650), (375, 585),
                   (455, 520), (525, 465), (585, 415), (630, 375),
                   (645, 330), (670, 255), (710, 200), (760, 168),
                   (815, 165), (860, 195), (885, 230), (810, 240),
                   (730, 245), (665, 270),
                   (650, 320), (650, 420), (600, 560), (520, 640),
                   (430, 715), (330, 775), (225, 820), (130, 835)],
                  closed=True)
    polygon_fill(S(body), WHALE)
    lower_jaw = spline([(640, 420), (720, 415), (800, 425), (875, 440),
                        (800, 480), (720, 490), (660, 470)], closed=True)
    polygon_fill(S(lower_jaw), WHALE)
    fin = spline([(490, 610), (415, 685), (345, 770), (305, 810),
                  (335, 818), (400, 760), (460, 700), (515, 650)],
                 closed=True)
    polygon_fill(S(fin), WHALE)
    flukes = spline([(180, 780), (110, 750), (85, 770), (130, 810),
                     (165, 845), (200, 860), (215, 830), (195, 795)],
                    closed=True)
    polygon_fill(S(flukes), WHALE)

    # 10. moonlit rim light (moon-facing edges). The long ribbon follows the
    #     SPLINED back/jaw curve, not the raw control points, so it stays
    #     smooth; shorter ribbons outline the mouth from inside.
    back_top = spline([(110, 790), (200, 720), (290, 650), (375, 585),
                       (455, 520), (525, 465), (585, 415), (630, 375),
                       (645, 330), (670, 255), (710, 200), (760, 168),
                       (815, 165), (860, 195), (885, 230)], subdiv=12)
    ribbon(S(back_top), 5 * SS, 2 * SS, RIM, 0.65, side=-1)
    ribbon(S(back_top), 2 * SS, 2 * SS, RIM_CORE, 0.8, side=-1)
    ribbon(S([(650, 320), (665, 270), (730, 245), (810, 240), (885, 230)]),
           3 * SS, 1 * SS, RIM, 0.5, side=1)
    ribbon(S([(640, 420), (720, 415), (800, 425), (875, 440)]),
           3 * SS, 1 * SS, RIM, 0.5, side=-1)
    ribbon(S([(490, 610), (415, 685), (345, 770), (305, 810)]),
           3 * SS, 1 * SS, RIM, 0.25, side=-1)

    # 11. eye: pale dot with a bright highlight
    disc(618 * SS, 395 * SS, 5 * SS, (207, 228, 245), 0.9)
    disc(616 * SS, 393 * SS, 2 * SS, WHITE, 0.95)

    # 12. spray from the breach, splash crown, foam at the waterline
    for _ in range(130):
        a = rng.uniform(math.radians(-150), math.radians(-30))
        s = rng.uniform(180, 430)
        t = rng.uniform(0.15, 1.0)
        x = 205 + math.cos(a) * s * t
        y = 715 + math.sin(a) * s * t + 0.5 * 260 * t * t
        r = rng.uniform(1.5, 4.5) * SS
        disc(x * SS, y * SS, r, FOAM, rng.uniform(0.4, 0.95))
    for _ in range(46):
        x = rng.uniform(120, 300)
        y = rng.uniform(690, 735)
        ellipse(x * SS, y * SS, rng.uniform(3, 9) * SS,
                rng.uniform(2, 5) * SS, FOAM, rng.uniform(0.4, 0.85))
    for (x, y, rx, ry, a) in [(180, 705, 90, 10, 0.5), (265, 722, 60, 8, 0.45),
                              (120, 712, 50, 7, 0.4)]:
        ellipse(x * SS, y * SS, rx * SS, ry * SS, FOAM, a)

    # 13. faint vignette
    radial_gradient(512 * SS, 512 * SS, 735 * SS, 565 * SS, DARK, 0.20,
                    rings=20, power=1.3)


# ------------------------------------------------------------ downsample/png
def downsample(plane):
    """2x2 box downsample of one internal plane -> 1024x1024 bytes."""
    out = bytearray(W * H)
    for y in range(H):
        r0 = plane[(2 * y) * IW:(2 * y + 1) * IW]
        r1 = plane[(2 * y + 1) * IW:(2 * y + 2) * IW]
        out[y * W:(y + 1) * W] = bytes(
            (a + b + c + d) // 4
            for a, b, c, d in zip(r0[0::2], r0[1::2], r1[0::2], r1[1::2])
        )
    return bytes(out)


def write_png(path, r, g, b):
    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter: None
        base = y * W
        row = bytearray(W * 3)
        row[0::3] = r[base:base + W]
        row[1::3] = g[base:base + W]
        row[2::3] = b[base:base + W]
        raw += row
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    render()
    r = downsample(Rp)
    g = downsample(Gp)
    b = downsample(Bp)
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    size = write_png(path, r, g, b)
    print(f"wrote {path}: {W}x{H}, {size} bytes")


if __name__ == "__main__":
    main()
