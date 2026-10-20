"""F5 Studio icon. macOS 26 masks full-bleed icons itself and adds a light glass rim to every icon,
so the artwork fills the whole 1024 square and uses a light background the rim blends into.
The purple-to-pink gradient lives on the waveform and the "F5-TTS" label instead.

Usage: make_icon.py OUT.png
"""
import math, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 1024
PURPLE, PINK = (104, 64, 255), (236, 72, 153)


def diagonal(c1, c2):
    v = Image.linear_gradient("L").resize((S, S))
    g = Image.blend(v, v.transpose(Image.Transpose.ROTATE_90).transpose(Image.Transpose.FLIP_LEFT_RIGHT), 0.5)
    return Image.composite(Image.new("RGB", (S, S), c2), Image.new("RGB", (S, S), c1), g)


# soft lavender-white background, slightly lighter at the top
bg = Image.linear_gradient("L").resize((S, S))
icon = Image.composite(Image.new("RGB", (S, S), (236, 230, 252)), Image.new("RGB", (S, S), (255, 254, 255)), bg).convert("RGBA")

# artwork mask: waveform bars + "F5", filled with the brand gradient
mask = Image.new("L", (S, S), 0)
d = ImageDraw.Draw(mask)
n, x0, x1, cy = 15, 180, 844, 640
w = (x1 - x0) / n
for i in range(n):
    h = 30 + 150 * abs(math.sin(i * 0.75 + 0.4)) * (0.5 + 0.5 * math.sin(math.pi * i / (n - 1)))
    cx = x0 + w * (i + 0.5)
    d.rounded_rectangle([cx - w * 0.29, cy - h, cx + w * 0.29, cy + h], radius=int(w * 0.29), fill=255)
LABEL, MAX_W = "F5-TTS", 700   # kept inside the area the system's corner mask never clips
size = 240
while True:
    font = ImageFont.load_default(size)
    for f in ["/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"]:
        try:
            font = ImageFont.truetype(f, size)
            break
        except Exception:
            pass
    if d.textbbox((0, 0), LABEL, font=font)[2] <= MAX_W or size <= 120:
        break
    size -= 6
d.text((S / 2, 310), LABEL, font=font, fill=255, anchor="mm")

# a soft coloured glow under the artwork, then the artwork itself
glow = Image.new("RGBA", (S, S), PURPLE + (0,))
glow.putalpha(mask.filter(ImageFilter.GaussianBlur(28)).point(lambda a: a * 0.28))
icon.alpha_composite(glow, (0, 14))
art = diagonal(PURPLE, PINK).convert("RGBA")
art.putalpha(mask)
icon.alpha_composite(art)
icon.convert("RGB").save(sys.argv[1])
