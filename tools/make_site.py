#!/usr/bin/env python3
"""
Build the project site.

docs/index.html is generated, not hand-edited: it is docs/_template.html with
the rhythm chart embedded at the __CHART__ marker. Edit the template for
prose, and tools/make_rhythm_chart.py for the picture.

    python3 tools/make_rhythm_chart.py && python3 tools/make_site.py

Doing it this way rather than editing the HTML in place is deliberate. The
chart and the favicon are both inline SVG, so "replace the first <svg in the
file" silently overwrote the favicon once. A marker cannot be ambiguous.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE = os.path.join(ROOT, "docs", "_template.html")
CHART = os.path.join(ROOT, "docs", "rhythm.svg")
OUTPUT = os.path.join(ROOT, "docs", "index.html")

MARKER = "__CHART__"


def main():
    for path in (TEMPLATE, CHART):
        if not os.path.exists(path):
            sys.exit("missing %s" % os.path.relpath(path, ROOT))

    with open(TEMPLATE, encoding="utf-8") as fh:
        template = fh.read()
    with open(CHART, encoding="utf-8") as fh:
        chart = fh.read().strip()

    if template.count(MARKER) != 1:
        sys.exit("template must contain exactly one %s (found %d)"
                 % (MARKER, template.count(MARKER)))

    page = template.replace(MARKER, chart)

    # The favicon is also inline SVG. If the chart ever lands inside it again,
    # fail loudly rather than shipping a broken icon.
    head = page[:page.index("<body>")]
    if "rhythm-title" in head:
        sys.exit("the chart ended up in the document head — check the marker")
    if page.count("<svg") != 2:
        sys.exit("expected exactly two inline SVGs (favicon + chart), got %d"
                 % page.count("<svg"))

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("wrote %s (%.1f KB)"
          % (os.path.relpath(OUTPUT, ROOT), len(page) / 1024))


if __name__ == "__main__":
    main()
