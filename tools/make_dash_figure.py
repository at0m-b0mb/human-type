#!/usr/bin/env python3
"""
Draw the figure that explains the look-alike marks.

The claim the figure makes is a measurement, so the figure is built from the
measurement rather than drawn by hand. For each dash it rasterises the real
font at the real editor size, finds the bounding box of the ink, and emits
that box as an SVG rectangle at 1 pixel = 1 unit. If the strokes come out
identical in the picture it is because they are identical on screen.

    python3 tools/make_dash_figure.py            # writes docs/dashes.svg

Needs Pillow and a monospace font file. Everything else in tools/ is
standard library; this one is not, which is why the SVG is committed.
"""

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT = os.path.join(ROOT, "docs", "dashes.svg")

# (label, character) — every dash a reader might meet, in codepoint order.
# U+2010 and U+2011 are in here precisely because they are the two that do
# NOT collapse: a figure that only showed the collisions would be picking its
# evidence.
ROWS = [
    ("HYPHEN-MINUS",        "\u002d"),
    ("HYPHEN",              "\u2010"),
    ("NON-BREAKING HYPHEN", "\u2011"),
    ("FIGURE DASH",         "\u2012"),
    ("EN DASH",             "\u2013"),
    ("EM DASH",             "\u2014"),
    ("HORIZONTAL BAR",      "\u2015"),
    ("MINUS SIGN",          "\u2212"),
]

FONTS = [
    "/System/Library/Fonts/Menlo.ttc",
    "C:\\Windows\\Fonts\\consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]

SIZE = 13          # the editor's own size
ZOOM = 8           # one font pixel becomes this many SVG units
INK = "#15151C"
PAPER = "#FAF8F3"
RULE = "#E4DFD5"
LABEL = "#6A6A77"
WASH = "#F5C98A"


def measure(font_path, size):
    """char -> (ink width, ink height, advance), rasterised at `size`."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(font_path, size)
    out = {}
    for _label, ch in ROWS:
        img = Image.new("L", (size * 4, size * 4), 255)
        ImageDraw.Draw(img).text((size, size), ch, font=font, fill=0)
        box = img.point(lambda p: 255 if p < 200 else 0).getbbox()
        if box is None:
            out[ch] = (0, 0, font.getlength(ch))
        else:
            out[ch] = (box[2] - box[0], box[3] - box[1], font.getlength(ch))
    return out


def find_font(explicit=None):
    """The first candidate that exists *and* Pillow can actually open.

    Existing is not enough: macOS ships Monaco as a .dfont, which Pillow
    refuses, and a font that cannot be rasterised cannot be measured.
    """
    from PIL import ImageFont
    for path in ([explicit] if explicit else []) + FONTS:
        if not path or not os.path.exists(path):
            continue
        try:
            ImageFont.truetype(path, SIZE)
            return path
        except OSError:
            continue
    sys.exit("no usable monospace font found — pass one with --font")


def svg(measurements, font_name):
    row_h = 34
    code_x = 200          # wide enough for NON-BREAKING HYPHEN
    left = 288
    cell = 13 * ZOOM
    width = left + cell + 128
    height = 54 + row_h * len(ROWS) + 16
    groups = {}
    for label, ch in ROWS:
        w, h, _adv = measurements[ch]
        groups.setdefault((w, h), []).append(label)
    same = len(max(groups.values(), key=len))
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="%d" height="%d" role="img" '
        'aria-label="%d dash characters rendered at %dpx; %d of them are the '
        'same stroke, pixel for pixel">'
        % (width, height, width, height, len(ROWS), SIZE, same),
        '<style>'
        '.l{font:600 11px ui-sans-serif,system-ui,sans-serif;'
        'fill:%s;letter-spacing:.06em}'
        '.n{font:11px ui-monospace,monospace;fill:%s}'
        '.h{font:600 10px ui-sans-serif,system-ui,sans-serif;'
        'fill:%s;letter-spacing:.1em}'
        '</style>' % (LABEL, LABEL, LABEL),
        '<rect width="%d" height="%d" fill="%s"/>' % (width, height, PAPER),
        '<text class="h" x="16" y="22">CHARACTER</text>',
        '<text class="h" x="%d" y="22">INK, %d\u00d7 ACTUAL</text>' % (left, ZOOM),
        '<text class="h" x="%d" y="22">MEASURED</text>' % (left + cell + 16),
        '<line x1="16" y1="32" x2="%d" y2="32" stroke="%s"/>' % (width - 16, RULE),
    ]
    for i, (label, ch) in enumerate(ROWS):
        y = 54 + i * row_h
        w, h, adv = measurements[ch]
        parts.append('<text class="l" x="16" y="%d">%s</text>' % (y + 4, label))
        parts.append('<text class="n" x="%d" y="%d">U+%04X</text>'
                     % (code_x, y + 4, ord(ch)))
        # the cell the monospace font forces every one of them into
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" '
                     'stroke="%s" stroke-dasharray="2 3"/>'
                     % (left, y - 16, int(adv * ZOOM), 24, RULE))
        # the ink, at the size it actually occupies
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s"/>'
                     % (left + (int(adv * ZOOM) - w * ZOOM) // 2,
                        y - 4 - max(2, h * ZOOM) // 2,
                        w * ZOOM, max(2, h * ZOOM), INK))
        parts.append('<text class="n" x="%d" y="%d">%d \u00d7 %d px</text>'
                     % (left + cell + 16, y + 4, w, h))
        if i:
            parts.append('<line x1="16" y1="%d" x2="%d" y2="%d" stroke="%s" '
                         'stroke-opacity=".6"/>' % (y - 25, width - 16, y - 25, RULE))
    parts.append('<rect x="16" y="%d" width="%d" height="1" fill="%s"/>'
                 % (height - 26, width - 32, RULE))
    parts.append('<text class="n" x="16" y="%d">%s at %dpx, the editor\u2019s own '
                 'size \u2014 %d of these %d are the same pixels.</text>'
                 % (height - 10, font_name, SIZE, same, len(ROWS)))
    parts.append('</svg>')
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", help="path to a monospace font file")
    ap.add_argument("--out", default=OUTPUT)
    args = ap.parse_args()

    path = find_font(args.font)
    name = os.path.splitext(os.path.basename(path))[0]
    measurements = measure(path, SIZE)

    print("%s at %dpx:" % (name, SIZE))
    groups = {}
    for label, ch in ROWS:
        w, h, adv = measurements[ch]
        print("  %-21s U+%04X  ink %dx%d  advance %.0f"
              % (label, ord(ch), w, h, adv))
        groups.setdefault((w, h), []).append(label)
    biggest = max(groups.items(), key=lambda kv: len(kv[1]))
    (w, h), members = biggest
    print("\n  -> %d of %d render as the same %dx%d stroke: %s"
          % (len(members), len(ROWS), w, h, ", ".join(members)))
    for key, members in sorted(groups.items()):
        if key != biggest[0]:
            print("     %dx%d: %s" % (key[0], key[1], ", ".join(members)))

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg(measurements, name))
    print("wrote %s" % os.path.relpath(args.out, ROOT))


if __name__ == "__main__":
    main()
