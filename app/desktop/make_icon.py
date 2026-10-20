"""F5 Studio icon, full-bleed: the gradient fills the whole 1024 square with no transparent margin
or shadow, so macOS 26 masks it into its own rounded shape instead of putting it on a white tile.

Usage: make_icon.py OUT.png
"""
import math, sys
from PIL import Image, ImageDraw, ImageFont

S = 1024
c1, c2 = (99, 63, 255), (236, 72, 153)
v = Image.linear_gradient("L").resize((S, S))
grad = Image.blend(v, v.transpose(Image.Transpose.ROTATE_90).transpose(Image.Transpose.FLIP_LEFT_RIGHT), 0.5)
icon = Image.composite(Image.new("RGB", (S, S), c2), Image.new("RGB", (S, S), c1), grad).convert("RGBA")

d = ImageDraw.Draw(icon)
# waveform, kept inside the central ~80% so the system's corner mask never clips it
n, x0, x1, cy = 15, 170, 854, 620
w = (x1 - x0) / n
for i in range(n):
    h = 34 + 160 * abs(math.sin(i * 0.75 + 0.4)) * (0.5 + 0.5 * math.sin(math.pi * i / (n - 1)))
    cx = x0 + w * (i + 0.5)
    d.rounded_rectangle([cx - w * 0.28, cy - h, cx + w * 0.28, cy + h], radius=int(w * 0.28), fill=(255, 255, 255, 240))

font = ImageFont.load_default(260)
for f in ["/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"]:
    try:
        font = ImageFont.truetype(f, 260)
        break
    except Exception:
        pass
d.text((S / 2, 290), "F5", font=font, fill="white", anchor="mm")
icon.save(sys.argv[1])
