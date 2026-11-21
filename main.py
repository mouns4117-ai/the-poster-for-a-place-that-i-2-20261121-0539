# VELMARA — a travel poster for a place that isn't there.
# Pure-stdlib Python: draws the poster pixel by pixel and encodes a PNG
# with zlib + struct. No PIL, no network, no randomness: two runs write
# byte-identical files.
#
# The place: Velmara, an isle where the sea climbs the sky — a great arc
# of water rises out of the ocean and pours upward into the sunset, past
# a lighthouse on a floating rock. The poster is a vintage travel-poster
# composition: big sky, one impossible landmark, the name set large.

import os
import struct
import zlib

W = 1024
H = 1024


# ---------------------------------------------------------------- PNG out
def encode_png(rgb, width, height):
    """Encode a flat RGB bytearray as a PNG (filter 2, Up, per row)."""
    raw = bytearray()
    stride = width * 3
    prev = bytes(stride)
    for y in range(height):
        row = bytes(rgb[y * stride:(y + 1) * stride])
        raw.append(2)
        # PNG filter 2 (Up) subtracts the row above, byte-wise mod 256.
        raw.extend(bytes((a - b) % 256 for a, b in zip(row, prev)))
        prev = row
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.px = bytearray(width * height * 3)

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]

    def blend(self, x, y, color, alpha):
        """Paint color over the pixel with the given opacity (0..1)."""
        if 0 <= x < self.w and 0 <= y < self.h and 0.0 < alpha:
            i = (y * self.w + x) * 3
            a = alpha
            self.px[i] = int(color[0] * a + self.px[i] * (1 - a))
            self.px[i + 1] = int(color[1] * a + self.px[i + 1] * (1 - a))
            self.px[i + 2] = int(color[2] * a + self.px[i + 2] * (1 - a))

    def fill_rect(self, x0, y0, x1, y1, color):
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w, x1)
        y1 = min(self.h, y1)
        for y in range(y0, y1):
            base = (y * self.w + x0) * 3
            for x in range(x0, x1):
                i = base + (x - x0) * 3
                self.px[i] = color[0]
                self.px[i + 1] = color[1]
                self.px[i + 2] = color[2]

    def vgrad(self, y0, y1, top, bottom):
        """Vertical linear gradient between two RGB colors."""
        span = max(1, y1 - y0)
        for y in range(y0, y1):
            t = (y - y0) / span
            color = tuple(int(top[c] + (bottom[c] - top[c]) * t)
                          for c in range(3))
            self.fill_rect(0, y, self.w, y + 1, color)

    def disc(self, cx, cy, r, color):
        r2 = r * r
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            dx = int((r2 - dy * dy) ** 0.5) if r2 - dy * dy > 0 else 0
            self.fill_rect(cx - dx, y, cx + dx + 1, y + 1, color)

    def disc_blend(self, cx, cy, r, color, alpha):
        r2 = r * r
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            rem = r2 - dy * dy
            if rem <= 0:
                continue
            dx = int(rem ** 0.5)
            for x in range(cx - dx, cx + dx + 1):
                self.blend(x, y, color, alpha)

    def ellipse(self, cx, cy, rx, ry, color):
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / ry
            rem = 1.0 - dy * dy
            if rem <= 0:
                continue
            dx = int(rx * rem ** 0.5)
            self.fill_rect(cx - dx, y, cx + dx + 1, y + 1, color)

    def ellipse_blend(self, cx, cy, rx, ry, color, alpha):
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / ry
            rem = 1.0 - dy * dy
            if rem <= 0:
                continue
            dx = int(rx * rem ** 0.5)
            for x in range(cx - dx, cx + dx + 1):
                self.blend(x, y, color, alpha)

    def line(self, x0, y0, x1, y1, color, width=1):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        r = width // 2
        for s in range(steps + 1):
            t = s / steps
            x = int(x0 + (x1 - x0) * t)
            y = int(y0 + (y1 - y0) * t)
            self.disc(x, y, r, color)

    def poly(self, points, color):
        """Scanline-fill a polygon given as [(x, y), ...]."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(points)
            for i in range(n):
                x0, y0 = points[i]
                x1, y1 = points[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                self.fill_rect(int(xs[j]), y, int(xs[j + 1]) + 1, y + 1,
                               color)


def lerp(a, b, t):
    return tuple(int(a[c] + (b[c] - a[c]) * t) for c in range(3))


# ---------------------------------------------------------------- 5x7 type
# Each glyph: 7 rows of 5 bits, '#' = on.
FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'D': ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'J': ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    'K': ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'Q': ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'V': ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    'W': ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    'X': ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    'Y': ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    'Z': ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
}


def text_width(text, scale, spacing=None):
    if spacing is None:
        spacing = max(1, scale // 5)
    return len(text) * (5 * scale + spacing) - spacing


def draw_text(cv, text, cx, y, scale, color, outline=None):
    """Draw text centred on cx at height y, in blocky poster capitals."""
    spacing = max(1, scale // 5)
    w = text_width(text, scale, spacing)
    x = cx - w // 2
    if outline is not None:
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            _draw_text_raw(cv, text, x + dx, y + dy, scale, spacing,
                           outline)
    _draw_text_raw(cv, text, x, y, scale, spacing, color)


def _draw_text_raw(cv, text, x0, y0, scale, spacing, color):
    x = x0
    for ch in text:
        glyph = FONT.get(ch, FONT[' '])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == '1':
                    cv.fill_rect(x + col * scale, y0 + row * scale,
                                 x + (col + 1) * scale,
                                 y0 + (row + 1) * scale, color)
        x += 5 * scale + spacing


# ---------------------------------------------------------------- the scene
CREAM = (250, 243, 224)
DARK = (13, 42, 58)
ARC_BLUE = (64, 158, 196)
ARC_LIGHT = (150, 214, 235)
FOAM = (235, 248, 250)
ROCK = (44, 42, 52)
RED = (200, 68, 44)
SUN = (255, 236, 190)


def _lcg(seed):
    """Tiny deterministic pseudo-random generator (fixed seed)."""
    state = seed

    def next_int(n):
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state % n

    return next_int


def _bezier(p0, p1, p2, t):
    u = 1.0 - t
    x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
    y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
    return x, y


def _beam(cv, lx, ly, length, spread, color, alpha):
    """A horizontal light wedge from (lx, ly), blended over the sky."""
    for dx in range(length):
        half = int(4 + spread * dx)
        for y in range(ly - half, ly + half + 1):
            cv.blend(lx + dx, y, color, alpha)
        for y in range(ly - half, ly + half + 1):
            cv.blend(lx - dx, y, color, alpha)


def draw_poster(cv):
    rnd = _lcg(20261121)
    horizon = 648

    # Sky: deep teal at the top melting into a warm sunset at the horizon.
    cv.vgrad(0, horizon, (16, 56, 78), (250, 184, 116))

    # Sun low over the horizon, with a soft glow.
    cv.disc_blend(712, 585, 150, (255, 200, 120), 0.18)
    cv.disc_blend(712, 585, 100, (255, 214, 140), 0.25)
    cv.disc(712, 585, 64, SUN)

    # Soft clouds.
    cv.ellipse_blend(180, 300, 90, 22, (255, 240, 220), 0.25)
    cv.ellipse_blend(850, 90, 110, 26, (255, 240, 220), 0.25)
    cv.ellipse_blend(420, 140, 70, 18, (255, 240, 220), 0.20)
    cv.ellipse_blend(120, 480, 70, 16, (255, 240, 220), 0.18)

    # Birds.
    for bx, by in ((300, 220), (350, 250), (800, 120), (760, 150)):
        cv.line(bx - 12, by, bx, by - 8, DARK, 3)
        cv.line(bx, by - 8, bx + 12, by, DARK, 3)

    # The rising sea: a great arc of water climbing from the ocean into
    # the sky, drawn as a thick band along a quadratic curve.
    p0, p1, p2 = (150, 660), (260, 110), (880, 210)
    steps = 260
    pts = [_bezier(p0, p1, p2, i / steps) for i in range(steps + 1)]
    for (x, y) in pts:
        cv.disc(int(x), int(y), 26, ARC_BLUE)
    # Pale crest along the upper edge of the arc.
    for (x, y) in pts[::3]:
        cv.disc(int(x) - 12, int(y) - 12, 9, ARC_LIGHT)
    # Foam flecks along the outer edge.
    for (x, y) in pts[::2]:
        if rnd(3) == 0:
            cv.disc(int(x) + 14 + rnd(20) - 10, int(y) + 16 + rnd(16) - 8,
                    3 + rnd(4), FOAM)
    # Where the arc leaves the sea: a burst of spray.
    for _ in range(26):
        sx = 120 + rnd(90)
        sy = 620 + rnd(60)
        cv.disc(sx, sy, 3 + rnd(6), FOAM)
    # Where the arc ends it breaks into droplets that fall back as rain.
    for i in range(40):
        t = 0.86 + i * 0.003
        x, y = _bezier(p0, p1, p2, min(t, 1.0))
        dx = rnd(140) - 20
        dy = rnd(120)
        cv.disc(int(x) + dx, int(y) + dy, 2 + rnd(4), ARC_LIGHT)

    # Floating rock with a lighthouse, mid-frame.
    cv.poly([(520, 432), (700, 432), (672, 492), (640, 548), (610, 566),
             (578, 520), (540, 480)], ROCK)
    # Lighthouse: white tower, red bands, gallery and lamp.
    cv.fill_rect(596, 352, 624, 432, (245, 240, 226))
    cv.fill_rect(596, 372, 624, 388, RED)
    cv.fill_rect(596, 404, 624, 420, RED)
    cv.fill_rect(590, 344, 630, 352, DARK)
    cv.disc(610, 338, 10, (255, 220, 120))
    cv.fill_rect(600, 326, 620, 336, DARK)
    # Light beams sweeping both ways.
    _beam(cv, 610, 338, 250, 0.10, (255, 226, 140), 0.30)
    # A few shrubs on the rock.
    cv.disc(540, 430, 10, (38, 90, 70))
    cv.disc(676, 430, 9, (38, 90, 70))

    # Sea: deep teal darkening toward the bottom.
    cv.vgrad(horizon, H, (18, 74, 99), (8, 38, 58))
    # Sun's path glittering on the water.
    for y in range(horizon + 6, H - 20, 14):
        w = 60 + (y - horizon) // 6
        cv.fill_rect(712 - w // 2, y, 712 + w // 2, y + 3,
                     (255, 200, 130) if rnd(2) else (240, 170, 100))
    # Wave dashes.
    for wy in (690, 730, 780, 840, 900, 960):
        x = (wy * 7) % 70
        while x < W - 50:
            cv.fill_rect(x, wy, x + 42, wy + 3, (120, 190, 215))
            x += 96

    # Sailboats on the sea.
    for (bx, by, s) in ((250, 770, 1.0), (830, 840, 0.8), (430, 910, 1.2)):
        hull = [(bx - 34 * s, by), (bx + 34 * s, by),
                (bx + 22 * s, by + 12 * s), (bx - 22 * s, by + 12 * s)]
        cv.poly([(int(px), int(py)) for px, py in hull], (40, 30, 34))
        cv.poly([(bx, int(by - 46 * s)), (bx, by), (int(bx + 26 * s), by)],
                (245, 240, 226))
        cv.poly([(int(bx - 4 * s), int(by - 38 * s)), (int(bx - 4 * s), by),
                 (int(bx - 26 * s), by)], (235, 120, 90))

    # Frame: a thin cream border, vintage-poster style.
    cv.fill_rect(22, 22, W - 22, 26, CREAM)
    cv.fill_rect(22, H - 26, W - 22, H - 22, CREAM)
    cv.fill_rect(22, 22, 26, H - 22, CREAM)
    cv.fill_rect(W - 26, 22, W - 22, H - 22, CREAM)

    # The name, set large at the top.
    draw_text(cv, "VELMARA", W // 2, 58, 13, CREAM, outline=DARK)
    # A short rule under the name.
    cv.fill_rect(W // 2 - 150, 168, W // 2 + 150, 172, CREAM)
    # The promise, set at the bottom over the dark sea.
    draw_text(cv, "WHERE THE SEA CLIMBS THE SKY", W // 2, 956, 4, CREAM,
              outline=DARK)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    cv = Canvas(W, H)
    draw_poster(cv)
    png = encode_png(cv.px, W, H)
    with open(os.path.join(out_dir, "entry.png"), "wb") as f:
        f.write(png)
    print(f"wrote {os.path.join(out_dir, 'entry.png')} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
