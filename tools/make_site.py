#!/usr/bin/env python3
"""
Build the project site.

docs/index.html is generated, not hand-edited: it is docs/_template.html with
each figure embedded at its own marker. Edit the template for prose, and the
matching tool for the picture.

    python3 tools/make_rhythm_chart.py
    python3 tools/make_dash_figure.py
    python3 tools/make_site.py

Doing it this way rather than editing the HTML in place is deliberate. The
figures and the favicon are all inline SVG, so "replace the first <svg in the
file" silently overwrote the favicon once. A marker cannot be ambiguous.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE = os.path.join(ROOT, "docs", "_template.html")
OUTPUT = os.path.join(ROOT, "docs", "index.html")

# marker -> the SVG that replaces it, and the id of the section it belongs to
FIGURES = {
    "__CHART__":  (os.path.join(ROOT, "docs", "rhythm.svg"), "rhythm-title"),
    "__DASHES__": (os.path.join(ROOT, "docs", "dashes.svg"), None),
}


def main():
    if not os.path.exists(TEMPLATE):
        sys.exit("missing %s" % os.path.relpath(TEMPLATE, ROOT))

    with open(TEMPLATE, encoding="utf-8") as fh:
        page = fh.read()

    for marker, (path, _sentinel) in FIGURES.items():
        if not os.path.exists(path):
            sys.exit("missing %s — run the tool that generates it"
                     % os.path.relpath(path, ROOT))
        if page.count(marker) != 1:
            sys.exit("template must contain exactly one %s (found %d)"
                     % (marker, page.count(marker)))
        with open(path, encoding="utf-8") as fh:
            page = page.replace(marker, fh.read().strip())

    # The favicon is also inline SVG. If a figure ever lands inside it again,
    # fail loudly rather than shipping a broken icon.
    head = page[:page.index("<body>")]
    for _marker, (_path, sentinel) in FIGURES.items():
        if sentinel and sentinel in head:
            sys.exit("a figure ended up in the document head — check the markers")
    expected = 1 + len(FIGURES)
    if page.count("<svg") != expected:
        sys.exit("expected exactly %d inline SVGs (favicon + %d figures), got %d"
                 % (expected, len(FIGURES), page.count("<svg")))

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("wrote %s (%.1f KB)"
          % (os.path.relpath(OUTPUT, ROOT), len(page) / 1024))


if __name__ == "__main__":
    main()
