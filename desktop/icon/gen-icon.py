#!/usr/bin/env python3
"""Generate the Vepol app icon.

Draws the 1024x1024 master on macOS Big Sur+ geometry (824x824 squircle inside a
1024 canvas, baked drop shadow), downsamples every required size with LANCZOS and
packs them into ``Vepol.icns`` with the system ``iconutil``.

Requires Pillow; the app build itself does not — it consumes the committed
``Vepol.icns``. Regenerate only when the artwork changes:

    python3 desktop/icon/gen-icon.py [--concept monogram|board]
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys

try:
    from PIL import Image, ImageDraw, ImageFilter
except ModuleNotFoundError:  # pragma: no cover - developer tool, not a build step
    sys.exit("Pillow is required to regenerate the icon: python3 -m pip install Pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 1024
SS = 4      # supersample factor for the vector artwork
PAD = 100   # content inset: an 824x824 squircle inside the 1024 canvas

# Icon palette, aligned with the Face UI accent tokens.
INK_ON_PLATE = (255, 255, 255, 242)
ALIVE = (0x5C, 0xE2, 0x99, 255)

ICNS_SIZES = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def _squircle_polygon(cx, cy, a, b, n=5.0, steps=1440):
    """Superellipse outline — the continuous curve Apple's icon grid uses."""
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        pts.append((cx + a * math.copysign(abs(ct) ** (2.0 / n), ct),
                    cy + b * math.copysign(abs(st) ** (2.0 / n), st)))
    return pts


def _squircle_mask():
    m = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    half = (SIZE - 2 * PAD) / 2.0
    ImageDraw.Draw(m).polygon(
        _squircle_polygon(SIZE / 2.0 * SS, SIZE / 2.0 * SS, half * SS, half * SS), fill=255)
    return m.resize((SIZE, SIZE), Image.LANCZOS)


def _vertical_gradient(top, bottom):
    g = Image.new("RGB", (SIZE, SIZE))
    d = ImageDraw.Draw(g)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        d.line([(0, y), (SIZE, y)],
               fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g


def _plate(top, bottom):
    """Gradient squircle with a top-left light and a soft drop shadow."""
    mask = _squircle_mask()
    body = _vertical_gradient(top, bottom)

    glow = Image.new("L", (SIZE, SIZE), 0)
    r = SIZE * 0.42
    ImageDraw.Draw(glow).ellipse(
        [SIZE * 0.34 - r, SIZE * 0.26 - r, SIZE * 0.34 + r, SIZE * 0.26 + r], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.55)).point(lambda v: v // 3)
    body = Image.composite(Image.new("RGB", (SIZE, SIZE), (255, 255, 255)), body, glow)

    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), mask.point(lambda v: int(v * 0.42)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    shadow = shadow.transform(shadow.size, Image.AFFINE, (1, 0, 0, 0, 1, -14))

    plate = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    plate.paste(body, (0, 0), mask)

    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(plate)
    return canvas, mask


def _clip_onto(art, canvas, mask):
    art = art.resize((SIZE, SIZE), Image.LANCZOS)
    art.putalpha(Image.composite(art.getchannel("A"), Image.new("L", (SIZE, SIZE), 0), mask))
    canvas.alpha_composite(art)
    return canvas


def concept_board():
    """Three work stages; the finished column is alive-green."""
    canvas, mask = _plate((0x6D, 0x8B, 0xFF), (0x2B, 0x38, 0xB8))
    art = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)

    col_w, gap, counts = 156, 48, (2, 2, 1)
    x0 = (SIZE - (col_w * 3 + gap * 2)) / 2
    col_top, col_bot = 286, 738
    card_h, card_gap, inset = 112, 30, 22

    for i, count in enumerate(counts):
        cx = x0 + i * (col_w + gap)
        d.rounded_rectangle([cx * SS, col_top * SS, (cx + col_w) * SS, col_bot * SS],
                            radius=34 * SS, fill=(255, 255, 255, 62))
        for k in range(count):
            cy = col_top + 28 + k * (card_h + card_gap)
            d.rounded_rectangle(
                [(cx + inset) * SS, cy * SS, (cx + col_w - inset) * SS, (cy + card_h) * SS],
                radius=26 * SS, fill=ALIVE if i == 2 else INK_ON_PLATE)
    return _clip_onto(art, canvas, mask)


def concept_monogram():
    """V drawn as a tick: the left arm runs slightly longer than the right."""
    canvas, mask = _plate((0x7C, 0x95, 0xFF), (0x23, 0x2F, 0xA8))
    art = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)

    w = 132
    apex = (500, 730)
    left = (290, 286)    # longer arm
    right = (726, 372)   # shorter arm
    white = (255, 255, 255, 255)

    for end in (left, right):
        d.line([(end[0] * SS, end[1] * SS), (apex[0] * SS, apex[1] * SS)],
               fill=white, width=w * SS, joint="curve")
    for x, y in (left, apex, right):
        r = w / 2
        d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=white)

    # Liveness dot fills the space the shorter arm leaves open.
    r, dx, dy = 62, 762, 236
    d.ellipse([(dx - r - 16) * SS, (dy - r - 16) * SS, (dx + r + 16) * SS, (dy + r + 16) * SS],
              fill=(0x23, 0x2F, 0xA8, 255))
    d.ellipse([(dx - r) * SS, (dy - r) * SS, (dx + r) * SS, (dy + r) * SS], fill=ALIVE)
    return _clip_onto(art, canvas, mask)


CONCEPTS = {"board": concept_board, "monogram": concept_monogram}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--concept", choices=sorted(CONCEPTS), default="monogram")
    args = ap.parse_args()

    master = CONCEPTS[args.concept]()
    master_path = os.path.join(HERE, "vepol-icon-1024.png")
    master.save(master_path)

    iconset = os.path.join(HERE, "Vepol.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    for name, px in ICNS_SIZES:
        master.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, name))

    icns = os.path.join(HERE, "Vepol.icns")
    subprocess.run(["/usr/bin/iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    print(f"concept={args.concept}\n{master_path}\n{icns}")


if __name__ == "__main__":
    main()
