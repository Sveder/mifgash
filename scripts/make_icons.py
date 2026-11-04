"""Draw the Mifgash mark as PNG and ICO files (run once after a colour change).

The mark: two overlapping circles, sea left, sun right, the overlap in coral (T236: the old green blended with the blue).
Same geometry as static/planner/favicon.svg (viewBox 0 0 34 24, r 10, centres x 12 and 22).
Usage: python3 scripts/make_icons.py  (needs Pillow; the app does not)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

SEA, SUN, MEET, BG = "#1D5FD0", "#F5B83D", "#E0474C", "#F2F4F7"
OUT = Path(__file__).resolve().parent.parent / "planner" / "static" / "planner"
SCALE = 8  # draw large, then shrink, for smooth edges


def mark(size, pad=0.0, bg=None):
    s = size * SCALE
    img = Image.new("RGBA", (s, s), bg or (0, 0, 0, 0))
    unit = s * (1 - 2 * pad) / 34  # the mark is 34 x 24 units
    ox, oy = s * pad, (s - 24 * unit) / 2

    def disc():
        m = Image.new("L", (s, s), 0)
        return m, ImageDraw.Draw(m)

    masks = []
    for cx in (12, 22):
        m, d = disc()
        d.ellipse([ox + (cx - 10) * unit, oy + 2 * unit, ox + (cx + 10) * unit, oy + 22 * unit], fill=255)
        masks.append(m)
    img.paste(Image.new("RGBA", (s, s), SEA), mask=masks[0])
    img.paste(Image.new("RGBA", (s, s), SUN), mask=masks[1])
    img.paste(Image.new("RGBA", (s, s), MEET), mask=ImageChops.multiply(masks[0], masks[1]))
    return img.resize((size, size), Image.LANCZOS)


def main():
    mark(32).save(OUT / "favicon-32.png")
    mark(180, pad=0.14, bg=BG).save(OUT / "apple-touch-icon.png")
    mark(64).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
