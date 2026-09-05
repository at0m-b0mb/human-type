"""
Host tests for the realism engine.

No GUI, no keyboard, no network — this runs anywhere Python does:

    python3 tests/test_realism.py

The headline test is `test_reconstruction`: whatever mistakes the engine
invents, replaying the event stream must give back the original text
character for character. Everything else in the app depends on that.
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import realism as R  # noqa: E402


CORPUS = [
    "",
    "a",
    "\n",
    "\n\n\n",
    "The quick brown fox jumps over the lazy dog.",
    "Hello, world! How are you? Fine; thanks: really.",
    "Double letters: still, running, coffee, bookkeeper, aaa.",
    "ALL CAPS SHOUTING AT THE TOP OF ITS LUNGS.",
    "MiXeD cAsE wItH sHiFt SlIpS eVeRyWhErE.",
    "Symbols: !@#$%^&*()_+{}|:\"<>?[]\;',./`~",
    "Digits 0123456789 and maths 3 + 4 = 7.",
    "Unicode: café naïve — em-dash, “smart quotes”, emoji 🙂, ünïcödé.",
    "Tabs\tand\tmore\ttabs.",
    "Trailing spaces   \nand a line that ends abruptly",
    "the and you have that this with from they their because definitely",
    "\n\nLeading blank lines.",
    "Ends with a newline.\n",
    "one\ntwo\nthree\n\nfour\n\n\nfive",
    "a" * 300,
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim "
    "veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip.",
]

# A style that fires every mistake path constantly, to stress the corrector.
CHAOS = R.TypingStyle(
    base_delay=0.01, variation=0.004,
    effort_model=True, rhythm_drift=0.3, warmup=True, fatigue=True,
    word_burst=True, burst_mode=True, idle_pauses=True,
    think_before_sentence=0.5, hesitate_chance=0.5,
    typo_chance=0.35, transpose_chance=0.35, double_letter_chance=0.35,
    common_typo_chance=0.9, cap_slip_chance=0.35, notice_max=8,
)


class Counter:
    """Counts individual assertions so the suite can report its own size."""
    n = 0


def checked(fn):
    def wrapper(self, *a, **kw):
        return fn(self, *a, **kw)
    return wrapper


class ReconstructionTests(unittest.TestCase):
    """The invariant the whole app rests on."""

    def _roundtrip(self, text, style, seeds):
        for seed in range(seeds):
            events = list(R.plan(text, style, random.Random(seed)))
            Counter.n += 1
            self.assertEqual(
                R.replay(events), text,
                "text was not reconstructed exactly "
                "(seed=%d, %r)" % (seed, text[:40]))

    def test_every_profile_reconstructs(self):
        for name in R.PROFILES:
            style = R.profile(name)
            for text in CORPUS:
                self._roundtrip(text, style, 25)

    def test_chaos_style_reconstructs(self):
        for text in CORPUS:
            self._roundtrip(text, CHAOS, 60)

    def test_press_enter_mode_reconstructs(self):
        style = R.profile("Natural")
        style.press_enter = True
        for text in CORPUS:
            self._roundtrip(text, style, 25)

    def test_chaos_with_press_enter(self):
        import dataclasses
        style = dataclasses.replace(CHAOS, press_enter=True)
        for text in CORPUS:
            self._roundtrip(text, style, 40)

    def test_random_texts_reconstruct(self):
        alphabet = "abcdeFGH .,;:!?\n\t'\"-()xyzZ0123é"
        rng = random.Random(1234)
        for _ in range(400):
            text = "".join(rng.choice(alphabet)
                           for _ in range(rng.randint(0, 120)))
            events = list(R.plan(text, CHAOS, rng))
            Counter.n += 1
            self.assertEqual(R.replay(events), text)


class SafetyTests(unittest.TestCase):
    """Properties that stop the engine doing something destructive."""

    def test_backspace_never_underflows(self):
        """A backspace with an empty buffer would eat the user's own text."""
        for text in CORPUS:
            for seed in range(30):
                depth = 0
                for ev in R.plan(text, CHAOS, random.Random(seed)):
                    if isinstance(ev, R.Char):
                        depth += 1
                    elif isinstance(ev, R.Key):
                        if ev.name == "backspace":
                            Counter.n += 1
                            self.assertGreater(
                                depth, 0,
                                "backspace issued with nothing typed yet — "
                                "this would delete text already in the window")
                            depth -= 1
                        elif ev.name == "enter":
                            depth += 1

    def test_mistakes_never_cross_a_line_break(self):
        """Backspacing past a newline in a chat box would send the message."""
        text = "short line\nanother line\n\nthird"
        for seed in range(200):
            run = 0
            for ev in R.plan(text, CHAOS, random.Random(seed)):
                if isinstance(ev, R.Char):
                    run = 0 if ev.ch == "\n" else run + 1
                elif isinstance(ev, R.Key) and ev.name == "backspace":
                    Counter.n += 1
                    self.assertGreater(
                        run, 0, "backspaced onto or past a line break")
                    run -= 1
                elif isinstance(ev, R.Key) and ev.name == "enter":
                    run = 0

    def test_no_negative_pauses(self):
        for name in list(R.PROFILES) + ["chaos"]:
            style = CHAOS if name == "chaos" else R.profile(name)
            for seed in range(10):
                for ev in R.plan(CORPUS[-1], style, random.Random(seed)):
                    if isinstance(ev, R.Pause):
                        Counter.n += 1
                        self.assertGreaterEqual(ev.seconds, 0.0)

    def test_progress_totals_match_text_length(self):
        for text in CORPUS:
            for seed in range(15):
                advance = sum(ev.advance
                              for ev in R.plan(text, CHAOS, random.Random(seed))
                              if isinstance(ev, (R.Char, R.Key)))
                Counter.n += 1
                self.assertEqual(advance, len(text),
                                 "progress bar would not reach 100%%")

    def test_clamped_rejects_nonsense(self):
        s = R.TypingStyle(base_delay=-5, variation=-1, typo_chance=9,
                          notice_max=99, rhythm_drift=17).clamped()
        Counter.n += 5
        self.assertEqual(s.base_delay, 0.0)
        self.assertEqual(s.variation, 0.0)
        self.assertEqual(s.typo_chance, 1.0)
        self.assertEqual(s.notice_max, 8)
        self.assertLessEqual(s.rhythm_drift, 0.40)

    def test_robotic_profile_makes_no_mistakes(self):
        style = R.profile("Robotic")
        for text in CORPUS:
            for seed in range(20):
                events = list(R.plan(text, style, random.Random(seed)))
                Counter.n += 1
                self.assertFalse(
                    any(isinstance(ev, R.Key) and ev.name == "backspace"
                        for ev in events),
                    "Robotic is documented as making no mistakes")


class EffortModelTests(unittest.TestCase):
    """The physical-cost model should agree with how hands actually work."""

    def test_space_is_the_cheapest_key(self):
        space = R.keystroke_effort(" ", "a")
        for ch in "abcdefghijklmnopqrstuvwxyz":
            Counter.n += 1
            self.assertLess(space, R.keystroke_effort(ch, "q"))

    def test_shift_costs_more(self):
        for ch in "abcdefghijklmnopqrstuvwxyz":
            Counter.n += 1
            self.assertGreater(R.keystroke_effort(ch.upper(), " "),
                               R.keystroke_effort(ch, " "))

    def test_same_finger_bigram_is_slower_than_alternating(self):
        # "de" is left-middle twice; "dk" alternates hands.
        Counter.n += 1
        self.assertGreater(R.keystroke_effort("e", "d"),
                           R.keystroke_effort("k", "d"))
        Counter.n += 1
        self.assertGreater(R.keystroke_effort("y", "u"),   # right index twice
                           R.keystroke_effort("y", "d"))   # alternating

    def test_home_row_beats_the_number_row(self):
        for home, far in zip("asdfjkl", "1234789"):
            Counter.n += 1
            self.assertLess(R.keystroke_effort(home, " "),
                            R.keystroke_effort(far, " "))

    def test_pinky_is_slower_than_index(self):
        Counter.n += 1
        self.assertGreater(R.keystroke_effort("q", " "),
                           R.keystroke_effort("f", " "))

    def test_effort_stays_in_range(self):
        chars = ("abcdefghijklmnopqrstuvwxyz"
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                 "0123456789!@#$%^&*()_+ \n\té")
        for a in chars:
            for b in chars:
                Counter.n += 1
                e = R.keystroke_effort(a, b)
                self.assertTrue(0.4 <= e <= 2.7, "%r after %r -> %s" % (a, b, e))

    def test_unknown_characters_do_not_explode(self):
        for ch in "日本語🙂ß€":
            Counter.n += 1
            self.assertTrue(0.4 <= R.keystroke_effort(ch, "a") <= 2.7)


class RhythmTests(unittest.TestCase):
    def test_drift_is_bounded_and_centred(self):
        d = R.RhythmDrift(0.12, rng=random.Random(7))
        vals = [d.step() for _ in range(20000)]
        Counter.n += 2
        self.assertTrue(all(0.5 < v < 2.0 for v in vals), "drift ran away")
        mean = sum(vals) / len(vals)
        self.assertTrue(0.9 < mean < 1.15, "drift is biased: %.3f" % mean)

    def test_drift_is_correlated_not_white_noise(self):
        """Consecutive keystrokes should be related — that is the whole point."""
        d = R.RhythmDrift(0.12, rng=random.Random(11))
        vals = [d.step() for _ in range(5000)]
        mean = sum(vals) / len(vals)
        num = sum((vals[i] - mean) * (vals[i + 1] - mean)
                  for i in range(len(vals) - 1))
        den = sum((v - mean) ** 2 for v in vals)
        Counter.n += 1
        self.assertGreater(num / den, 0.5,
                           "rhythm has no autocorrelation — it is just noise")

    def test_zero_strength_disables_drift(self):
        d = R.RhythmDrift(0.0, rng=random.Random(3))
        for _ in range(100):
            Counter.n += 1
            self.assertEqual(d.step(), 1.0)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_gives_the_same_plan(self):
        text = CORPUS[-1]
        for name in R.PROFILES:
            style = R.profile(name)
            a = list(R.plan(text, style, random.Random(99)))
            b = list(R.plan(text, style, random.Random(99)))
            Counter.n += 1
            self.assertEqual(a, b)

    def test_different_seeds_give_different_plans(self):
        text = CORPUS[-1]
        style = R.profile("Natural")
        a = list(R.plan(text, style, random.Random(1)))
        b = list(R.plan(text, style, random.Random(2)))
        Counter.n += 1
        self.assertNotEqual(a, b)


class EstimateTests(unittest.TestCase):
    def test_slower_base_delay_takes_longer(self):
        text = CORPUS[-1]
        fast = R.TypingStyle(base_delay=0.02, variation=0.0, typo_chance=0)
        slow = R.TypingStyle(base_delay=0.20, variation=0.0, typo_chance=0)
        Counter.n += 1
        self.assertGreater(R.estimate_seconds(text, slow, samples=3),
                           R.estimate_seconds(text, fast, samples=3))

    def test_empty_text_takes_no_time(self):
        Counter.n += 1
        self.assertEqual(R.estimate_seconds("", R.profile("Natural")), 0.0)

    def test_mistakes_cost_time(self):
        text = CORPUS[4] * 4
        clean = R.TypingStyle(base_delay=0.05, variation=0.0, typo_chance=0.0,
                              rhythm_drift=0.0)
        messy = R.TypingStyle(base_delay=0.05, variation=0.0, typo_chance=0.25,
                              notice_max=4, rhythm_drift=0.0)
        Counter.n += 1
        self.assertGreater(R.estimate_seconds(text, messy, samples=5),
                           R.estimate_seconds(text, clean, samples=5))


class ProfileTests(unittest.TestCase):
    def test_every_profile_has_a_blurb(self):
        for name in R.PROFILES:
            Counter.n += 1
            self.assertIn(name, R.PROFILE_BLURBS)

    def test_profile_falls_back_to_natural(self):
        Counter.n += 1
        self.assertEqual(R.profile("nonsense").typo_chance,
                         R.profile("Natural").typo_chance)

    def test_profile_keeps_speed_from_base(self):
        base = R.TypingStyle(base_delay=0.42, punct_pause=1.5)
        s = R.profile("Hurried", base)
        Counter.n += 2
        self.assertEqual(s.base_delay, 0.42)
        self.assertEqual(s.punct_pause, 1.5)

    def test_profiles_are_ordered_by_messiness(self):
        order = ["Robotic", "Steady", "Thoughtful", "Hurried"]
        chances = [R.profile(n).typo_chance for n in order]
        for a, b in zip(chances, chances[1:]):
            Counter.n += 1
            self.assertLessEqual(a, b)


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"])
    result = runner.run(suite)
    print("\n%s individual checks across %d tests"
          % (format(Counter.n, ","), result.testsRun))
    sys.exit(0 if result.wasSuccessful() else 1)
