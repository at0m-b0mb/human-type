"""
Contrast tests for the design system.

Gold on paper is the classic way an elegant palette becomes an unreadable
one, so the pairings that carry text are checked against WCAG rather than
eyeballed. Both themes, every accent.

Thresholds: 4.5:1 for normal text, 3:1 for large text and for UI marks that
carry meaning without carrying words.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# theme.py builds CTkFonts lazily, so it imports fine without a Tk root as
# long as we only touch colours.
import theme as T  # noqa: E402

AA_TEXT = 4.5
AA_LARGE = 3.0

LIGHT, DARK = 0, 1


def _channel(value):
    v = value / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * _channel(r) + 0.7152 * _channel(g)
            + 0.0722 * _channel(b))


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class ContrastTests(unittest.TestCase):
    def check(self, fg, bg, minimum, what, mode):
        ratio = contrast(fg[mode], bg[mode])
        self.assertGreaterEqual(
            ratio, minimum,
            "%s in %s mode: %s on %s is only %.2f:1, needs %.1f:1"
            % (what, "light" if mode == LIGHT else "dark",
               fg[mode], bg[mode], ratio, minimum))

    def test_body_text_on_every_surface(self):
        for mode in (LIGHT, DARK):
            for bg, bg_name in ((T.SURFACE, "surface"),
                                (T.SURFACE_ALT, "surface-alt"),
                                (T.CANVAS, "canvas")):
                self.check(T.INK, bg, AA_TEXT, "primary text on " + bg_name, mode)
                self.check(T.INK_2, bg, AA_TEXT,
                           "secondary text on " + bg_name, mode)

    def test_hint_text_is_still_readable(self):
        """INK_3 carries captions and hints — small text, so it needs AA."""
        for mode in (LIGHT, DARK):
            for bg, bg_name in ((T.SURFACE, "surface"),
                                (T.SURFACE_ALT, "surface-alt"),
                                (T.CANVAS, "canvas")):
                self.check(T.INK_3, bg, AA_TEXT, "hint text on " + bg_name, mode)

    def test_status_colours(self):
        for mode in (LIGHT, DARK):
            for colour, name in ((T.OK, "ok"), (T.WARN, "warn"), (T.ERR, "err")):
                self.check(colour, T.SURFACE, AA_TEXT, name + " text", mode)

    def test_every_accent_carries_its_button_label(self):
        for name, accent in T.ACCENTS.items():
            for mode in (LIGHT, DARK):
                self.check(accent["accent_ink"], accent["accent"], AA_TEXT,
                           "%s button label" % name, mode)

    def test_every_accent_gold_is_readable_as_text(self):
        """Gold is the eyebrow label above every page title."""
        for name, accent in T.ACCENTS.items():
            for mode in (LIGHT, DARK):
                for bg, bg_name in ((T.CANVAS, "canvas"), (T.SURFACE, "surface")):
                    self.check(accent["gold"], bg, AA_TEXT,
                               "%s gold on %s" % (name, bg_name), mode)

    def test_text_on_the_accent_wash(self):
        """The About page prints body text on accent_soft."""
        for name, accent in T.ACCENTS.items():
            for mode in (LIGHT, DARK):
                self.check(T.INK, accent["accent_soft"], AA_TEXT,
                           "%s text on wash" % name, mode)

    def test_accent_reads_against_its_own_surfaces(self):
        """Sliders, switches and the progress bar are marks, not words."""
        for name, accent in T.ACCENTS.items():
            for mode in (LIGHT, DARK):
                self.check(accent["accent"], T.SURFACE, AA_LARGE,
                           "%s accent mark" % name, mode)

    def test_hairlines_are_visible(self):
        for mode in (LIGHT, DARK):
            ratio = contrast(T.BORDER[mode], T.SURFACE[mode])
            self.assertGreater(ratio, 1.06,
                               "hairline is invisible in %s mode"
                               % ("light" if mode == LIGHT else "dark"))

    def test_shine_is_visible_without_carrying_words(self):
        """The bright gold marks the wordmark rule and the active nav item.

        Neither is the only cue for anything — the active row is tinted and
        bold as well — so this is held to visibility rather than to the 3:1
        that a sole state indicator would need. What it must never do is
        become text; `gold` is the token for that.
        """
        for name, accent in T.ACCENTS.items():
            for mode in (LIGHT, DARK):
                for bg, bg_name in ((T.SURFACE, "surface"),
                                    (accent["accent_soft"], "wash")):
                    ratio = contrast(accent["shine"][mode], bg[mode])
                    self.assertGreater(
                        ratio, 1.7,
                        "%s shine is invisible on %s in %s mode (%.2f:1)"
                        % (name, bg_name, "light" if mode == LIGHT else "dark",
                           ratio))

    def test_shine_is_brighter_than_the_text_gold(self):
        """Otherwise there is no reason for the second token to exist."""
        for name, accent in T.ACCENTS.items():
            self.assertGreater(
                luminance(accent["shine"][LIGHT]),
                luminance(accent["gold"][LIGHT]),
                "%s shine is not brighter than its text gold" % name)

    def test_every_accent_defines_every_token(self):
        expected = {"accent", "accent_hover", "accent_soft", "accent_ink",
                    "gold", "shine"}
        for name, accent in T.ACCENTS.items():
            self.assertEqual(set(accent), expected, "%s is missing tokens" % name)
            for token, pair in accent.items():
                self.assertEqual(len(pair), 2,
                                 "%s.%s has no dark half" % (name, token))
                for half in pair:
                    self.assertRegex(half, r"^#[0-9A-Fa-f]{6}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
