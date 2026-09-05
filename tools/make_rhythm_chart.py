#!/usr/bin/env python3
"""
Draw the rhythm chart used on the project site — straight from the engine.

Nothing here is illustrative. It plans a real passage with the real planner
and plots the pauses it produced, so the picture cannot drift away from what
the code actually does. Re-run it after touching realism.py.

    python3 tools/make_rhythm_chart.py
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import realism as rz  # noqa: E402

PASSAGE = (
    "Environmental regulation is one of the clearest areas for federal "
    "involvement, because pollution crosses state boundaries and creates "
    "harms that a single state cannot address on its own. Federal "
    "coordination makes sense for interstate transmission and reliability."
)

W, H = 880, 300
PAD_L, PAD_R, PAD_T, PAD_B = 56, 18, 34, 46
PLOT_W = W - PAD_L - PAD_R
PLOT_H = H - PAD_T - PAD_B


def delays_for(profile, seed):
    """Per-keystroke pause lengths, in milliseconds."""
    style = rz.profile(profile)
    style.base_delay, style.variation = 0.08, 0.03
    # Structural pauses would dwarf the keystroke rhythm on this scale, and
    # the rhythm is the thing being shown.
    style.punct_pause = style.para_pause = 0.0
    style.burst_mode = style.idle_pauses = False
    style.think_before_sentence = style.hesitate_chance = 0.0
    out = []
    for ev in rz.plan(PASSAGE, style, random.Random(seed)):
        if isinstance(ev, rz.Pause):
            out.append(ev.seconds * 1000.0)
    return out


# Corrections cost hundreds of milliseconds while ordinary keystrokes cost
# tens, so a linear axis would flatten the rhythm into a line at the bottom.
# A log axis shows both, and the ticks say so plainly.
TICKS = [25, 50, 100, 200, 400, 800]
YMIN, YMAX = 20.0, 900.0


def _y(ms):
    lo, hi = math.log10(YMIN), math.log10(YMAX)
    t = (math.log10(max(YMIN, min(YMAX, ms))) - lo) / (hi - lo)
    return PAD_T + PLOT_H - t * PLOT_H


def path_for(values):
    n = len(values)
    pts = ["%.1f %.1f" % (PAD_L + (i / max(1, n - 1)) * PLOT_W, _y(v))
           for i, v in enumerate(values)]
    return "M " + " L ".join(pts)


def main():
    robotic = delays_for("Robotic", 7)[:260]
    natural = delays_for("Natural", 7)[:260]
    n = min(len(robotic), len(natural))
    robotic, natural = robotic[:n], natural[:n]

    grid = ""
    for ms in TICKS:
        y = _y(ms)
        grid += (
            '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="grid"/>\n'
            '<text x="%d" y="%.1f" class="tick">%d ms</text>\n'
            % (PAD_L, y, W - PAD_R, y, PAD_L - 10, y + 4, ms)
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"
     role="img" aria-labelledby="rhythm-title rhythm-desc">
  <title id="rhythm-title">Keystroke delay over one passage</title>
  <desc id="rhythm-desc">Keystroke delay on a logarithmic scale. The Robotic
  profile holds a flat noisy band around eighty milliseconds. The Natural
  profile drifts around it and spikes into the hundreds where it stops to
  correct a mistake. Both traces are produced by the typing engine
  itself.</desc>
  <style>
    .grid {{ stroke: var(--rule, #E4DFD5); stroke-width: 1; }}
    .tick {{ fill: var(--ink-3, #8A8A97); font: 10px ui-sans-serif, system-ui, sans-serif;
             text-anchor: end; }}
    .lbl  {{ font: 600 11px ui-sans-serif, system-ui, sans-serif; }}
    .trace {{ fill: none; stroke-width: 1.6; stroke-linejoin: round; }}
    .robotic {{ stroke: var(--ink-3, #8A8A97); opacity: .75; }}
    .natural {{ stroke: var(--accent, #2B3A67); }}
  </style>
  {grid}
  <path class="trace robotic" d="{path_for(robotic)}"/>
  <path class="trace natural" d="{path_for(natural)}"/>
  <g transform="translate({PAD_L},{H - 14})">
    <line x1="0" y1="-4" x2="22" y2="-4" class="trace robotic"/>
    <text x="28" y="0" class="lbl" fill="var(--ink-2, #565663)">Robotic — jitter around a fixed delay</text>
    <line x1="270" y1="-4" x2="292" y2="-4" class="trace natural"/>
    <text x="298" y="0" class="lbl" fill="var(--ink-2, #565663)">Natural — effort, drift, and pauses to fix mistakes</text>
  </g>
</svg>
'''
    out = os.path.join(os.path.dirname(__file__), "..", "docs", "rhythm.svg")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)

    span = lambda v: (min(v), max(v), sum(v) / len(v))
    print("wrote", os.path.normpath(out))
    print("robotic  min %.1f  max %.1f  mean %.1f ms" % span(robotic))
    print("natural  min %.1f  max %.1f  mean %.1f ms" % span(natural))


if __name__ == "__main__":
    main()
