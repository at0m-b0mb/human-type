"""
Human typing realism engine.

Pure, dependency-free and host-testable: this module never touches the
keyboard, the GUI or the network. It turns a block of text into a stream of
`Event` objects describing *how a person would type it* — including the
mistakes they would make and the pauses they would take — and the GUI layer
executes that stream.

The engine holds one hard invariant, enforced by the test-suite:

    replay(plan(text, style)) == text

Every mistake the engine invents is noticed and corrected before the stream
ends, so the text that lands in the target window is byte-identical to the
text that went in. The realism lives in the *timing and the keystrokes*, not
in the finished document.
"""

import math
import random
import re
from dataclasses import dataclass, field, replace

__all__ = [
    "Char", "Key", "Pause", "Note",
    "TypingStyle", "PROFILES", "profile",
    "plan", "replay", "estimate_seconds",
    "RhythmDrift", "keystroke_effort",
]


# ---------------------------------------------------------------------------
# Events — the language the planner speaks to the executor
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Char:
    """Type one character. `advance` is how much real progress it represents:
    1 for a character that is now correctly in place, 0 for one that is part
    of a mistake and will be erased again."""
    ch: str
    advance: int = 1


@dataclass(frozen=True)
class Key:
    """Press a named key. `name` is 'backspace' or 'enter'."""
    name: str
    advance: int = 0


@dataclass(frozen=True)
class Pause:
    """Wait. `reason` is for the status line / debugging, never for control flow."""
    seconds: float
    reason: str = ""


@dataclass(frozen=True)
class Note:
    """A human-readable status update, e.g. 'pausing to think'."""
    text: str


# ---------------------------------------------------------------------------
# Keyboard geometry — used to model what is physically hard to type
# ---------------------------------------------------------------------------
# Row 0 is the number row, row 2 is the home row. Fingers are numbered
# 1 (index) .. 4 (pinky); 0 is a thumb.
_ROWS = [
    "`1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./",
]

# finger for each column position, per row, left hand then right hand
_FINGER_BY_LETTER = {}
_HAND_BY_LETTER = {}
_ROW_BY_LETTER = {}


def _assign(letters, hand, finger, row):
    for c in letters:
        _FINGER_BY_LETTER[c] = finger
        _HAND_BY_LETTER[c] = hand
        _ROW_BY_LETTER[c] = row


# left hand
_assign("`1qaz", "L", 4, None)
_assign("2wsx", "L", 3, None)
_assign("3edc", "L", 2, None)
_assign("45rtfgvb", "L", 1, None)
# right hand
_assign("67yuhjnm", "R", 1, None)
_assign("8ik,", "R", 2, None)
_assign("9ol.", "R", 3, None)
_assign("0p;/-=[]\\'", "R", 4, None)

for _r, _line in enumerate(_ROWS):
    for _c in _line:
        _ROW_BY_LETTER[_c] = _r

_HOME_ROW = 2

# Characters that need shift on a US layout, mapped to their unshifted key.
_SHIFTED = {
    "~": "`", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
    "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=",
    "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".",
    "?": "/",
}

# Effort model coefficients. These are shaped to match the broad findings of
# keystroke-timing research — same-finger bigrams are the single largest
# penalty, hand alternation is the largest bonus — not measured from any one
# study, so treat them as a plausible feel rather than a citation.
_ROW_PENALTY = {0: 0.34, 1: 0.13, 2: 0.00, 3: 0.16}
_FINGER_PENALTY = {1: 0.00, 2: 0.03, 3: 0.11, 4: 0.20}
_SHIFT_PENALTY = 0.34
_SAME_FINGER_PENALTY = 0.46
_SAME_HAND_PENALTY = 0.07
_ALTERNATE_HAND_BONUS = -0.07
_REPEAT_KEY_BONUS = -0.16
_SPACE_BONUS = -0.26
_EFFORT_MIN = 0.45
_EFFORT_MAX = 2.60


def _key_of(ch):
    """The physical key for `ch`, plus whether shift is held."""
    if ch in _SHIFTED:
        return _SHIFTED[ch], True
    low = ch.lower()
    if low != ch:
        return low, True
    return ch, False


def keystroke_effort(ch, prev=None):
    """Relative cost of typing `ch` after `prev`, as a delay multiplier.

    1.0 is an average keystroke. Home-row letters under strong fingers with
    the other hand just used come out near 0.7; a shifted pinky reach
    repeated on the same finger climbs past 2.0.
    """
    if ch == "\n" or ch == "\t":
        return 1.0
    if ch == " ":
        # Thumbs are always on the bar; spaces are the fastest keystroke there
        # is, and faster still when the previous key was on either index.
        return max(_EFFORT_MIN, 1.0 + _SPACE_BONUS)

    key, shifted = _key_of(ch)
    effort = 1.0

    row = _ROW_BY_LETTER.get(key)
    if row is None:
        # Unknown / non-US-layout character: treat as an awkward reach.
        return 1.35
    effort += _ROW_PENALTY.get(row, 0.15)
    finger = _FINGER_BY_LETTER.get(key, 2)
    effort += _FINGER_PENALTY.get(finger, 0.05)
    if shifted:
        effort += _SHIFT_PENALTY

    if prev and prev not in ("\n", "\t"):
        if prev == " ":
            # Coming off the space bar the hands are already home.
            effort -= 0.04
        else:
            pkey, _pshift = _key_of(prev)
            if pkey == key:
                effort += _REPEAT_KEY_BONUS
            else:
                phand = _HAND_BY_LETTER.get(pkey)
                pfinger = _FINGER_BY_LETTER.get(pkey)
                hand = _HAND_BY_LETTER.get(key)
                if phand is not None and hand is not None:
                    if phand != hand:
                        effort += _ALTERNATE_HAND_BONUS
                    elif pfinger == finger:
                        effort += _SAME_FINGER_PENALTY
                        prow = _ROW_BY_LETTER.get(pkey, _HOME_ROW)
                        effort += 0.06 * abs(prow - row)
                    else:
                        effort += _SAME_HAND_PENALTY

    return min(_EFFORT_MAX, max(_EFFORT_MIN, effort))


# ---------------------------------------------------------------------------
# Rhythm — slow correlated drift, not white noise
# ---------------------------------------------------------------------------
class RhythmDrift:
    """An Ornstein-Uhlenbeck walk in log-space.

    Per-keystroke jitter alone sounds like a machine adding noise, because
    each key is independent of the last. Real typists speed up and slow down
    in runs that last seconds. This produces a multiplier that wanders
    smoothly around 1.0 and is pulled back toward it, so cadence has texture
    without drifting away forever.
    """

    def __init__(self, strength=0.10, pull=0.08, rng=None):
        self.strength = max(0.0, strength)
        self.pull = min(1.0, max(0.001, pull))
        self._rng = rng or random.Random()
        self._x = 0.0

    def step(self):
        if self.strength <= 0:
            return 1.0
        self._x = self._x * (1.0 - self.pull) + self._rng.gauss(0.0, self.strength)
        # Keep the walk sane even on a long document.
        self._x = min(0.55, max(-0.55, self._x))
        return math.exp(self._x)


# ---------------------------------------------------------------------------
# Style — every knob the planner reads
# ---------------------------------------------------------------------------
@dataclass
class TypingStyle:
    # Core speed
    base_delay: float = 0.08
    variation: float = 0.03

    # Structural pauses
    punct_pause: float = 0.25
    para_pause: float = 0.80
    semicolon_factor: float = 0.70
    comma_factor: float = 0.40

    # Realism models
    effort_model: bool = True          # per-key physical cost
    rhythm_drift: float = 0.10         # 0 disables the OU walk
    warmup: bool = True                # first lines typed slightly cold
    warmup_chars: int = 90
    warmup_extra: float = 0.35
    fatigue: bool = False
    fatigue_factor: float = 0.50

    # Word / sentence behaviour
    word_burst: bool = True
    burst_mode: bool = False
    idle_pauses: bool = False
    think_before_sentence: float = 0.0  # chance of a beat before a sentence
    hesitate_chance: float = 0.0        # chance of stalling before a long word

    # Mistakes — every one of these is corrected before the stream ends
    typo_chance: float = 0.04           # adjacent-key slip
    transpose_chance: float = 0.0       # "the" -> "hte"
    double_letter_chance: float = 0.0   # "ll" -> "l", "l" -> "ll"
    common_typo_chance: float = 0.0     # "the" -> "teh"
    cap_slip_chance: float = 0.0        # missed shift
    notice_max: int = 0                 # how many extra chars before noticing

    # Output
    press_enter: bool = False

    def clamped(self):
        """A copy with every field forced into a sane range."""
        s = replace(self)
        s.base_delay = max(0.0, s.base_delay)
        s.variation = max(0.0, s.variation)
        s.punct_pause = max(0.0, s.punct_pause)
        s.para_pause = max(0.0, s.para_pause)
        s.rhythm_drift = min(0.40, max(0.0, s.rhythm_drift))
        s.notice_max = min(8, max(0, int(s.notice_max)))
        for name in ("typo_chance", "transpose_chance", "double_letter_chance",
                     "common_typo_chance", "cap_slip_chance",
                     "think_before_sentence", "hesitate_chance"):
            setattr(s, name, min(1.0, max(0.0, getattr(s, name))))
        return s


# Realism profiles. Speed presets set *how fast*; these set *how human*.
PROFILES = {
    "Robotic": dict(
        effort_model=False, rhythm_drift=0.0, warmup=False, fatigue=False,
        word_burst=False, burst_mode=False, idle_pauses=False,
        typo_chance=0.0, transpose_chance=0.0, double_letter_chance=0.0,
        common_typo_chance=0.0, cap_slip_chance=0.0, notice_max=0,
        think_before_sentence=0.0, hesitate_chance=0.0,
    ),
    "Steady": dict(
        effort_model=True, rhythm_drift=0.05, warmup=False, fatigue=False,
        word_burst=True, burst_mode=False, idle_pauses=False,
        typo_chance=0.004, transpose_chance=0.002, double_letter_chance=0.001,
        common_typo_chance=0.0, cap_slip_chance=0.0, notice_max=1,
        think_before_sentence=0.05, hesitate_chance=0.0,
    ),
    "Natural": dict(
        effort_model=True, rhythm_drift=0.11, warmup=True, fatigue=True,
        word_burst=True, burst_mode=True, idle_pauses=True,
        typo_chance=0.012, transpose_chance=0.006, double_letter_chance=0.004,
        common_typo_chance=0.02, cap_slip_chance=0.006, notice_max=3,
        think_before_sentence=0.22, hesitate_chance=0.05,
    ),
    "Hurried": dict(
        effort_model=True, rhythm_drift=0.16, warmup=False, fatigue=False,
        word_burst=True, burst_mode=True, idle_pauses=False,
        typo_chance=0.028, transpose_chance=0.016, double_letter_chance=0.010,
        common_typo_chance=0.04, cap_slip_chance=0.014, notice_max=5,
        think_before_sentence=0.05, hesitate_chance=0.02,
    ),
    "Thoughtful": dict(
        effort_model=True, rhythm_drift=0.13, warmup=True, fatigue=True,
        word_burst=True, burst_mode=True, idle_pauses=True,
        typo_chance=0.008, transpose_chance=0.004, double_letter_chance=0.003,
        common_typo_chance=0.012, cap_slip_chance=0.004, notice_max=2,
        think_before_sentence=0.45, hesitate_chance=0.14,
    ),
}

PROFILE_BLURBS = {
    "Robotic":    "Metronome. No mistakes, no drift — for when you just want the text in.",
    "Steady":     "A fast touch-typist on a good day. Even rhythm, rare slips.",
    "Natural":    "The default. Drifting cadence, occasional caught typos, thinking beats.",
    "Hurried":    "Typing quickly and slightly ahead of yourself. More slips, noticed late.",
    "Thoughtful": "Composing as you go. Long pauses before sentences, stalls on hard words.",
}


def profile(name, base=None):
    """A `TypingStyle` for the named realism profile."""
    style = replace(base) if base is not None else TypingStyle()
    for k, v in PROFILES.get(name, PROFILES["Natural"]).items():
        setattr(style, k, v)
    return style


# ---------------------------------------------------------------------------
# Mistake vocabulary
# ---------------------------------------------------------------------------
NEARBY_KEYS = {
    "a": "sqwz",   "b": "vghn",   "c": "xdfv",   "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko",   "j": "huikmn",
    "k": "jiolm",  "l": "kop",    "m": "njk",    "n": "bhjm",   "o": "iklp",
    "p": "ol",     "q": "wa",     "r": "edft",   "s": "awedxz", "t": "rfgy",
    "u": "yhji",   "v": "cfgb",   "w": "qase",   "x": "zsdc",   "y": "tghu",
    "z": "asx",
}

COMMON_TYPOS = {
    "the": "teh", "and": "adn", "you": "yuo", "have": "ahve",
    "that": "taht", "this": "tihs", "with": "wiht", "from": "fomr",
    "they": "tehy", "their": "thier", "there": "tehre", "would": "woudl",
    "could": "coudl", "should": "shoudl", "because": "becuase",
    "receive": "recieve", "definitely": "definately", "separate": "seperate",
    "necessary": "neccessary", "occurred": "occured", "tomorrow": "tommorow",
    "really": "realy", "people": "poeple", "about": "abuot", "which": "whcih",
    "however": "hwoever", "believe": "beleive", "argument": "arguement",
    "environment": "enviroment", "government": "goverment",
    "immediately": "immediatly", "particularly": "particulary",
}

# Burst / idle tuning
BURST_WORDS_MIN, BURST_WORDS_MAX = 6, 14
BURST_REST_MIN, BURST_REST_MAX = 0.4, 1.4
IDLE_CHARS_MIN, IDLE_CHARS_MAX = 150, 350
IDLE_PAUSE_MIN, IDLE_PAUSE_MAX = 0.8, 2.6

CHARS_PER_WORD = 5


# ---------------------------------------------------------------------------
# The planner
# ---------------------------------------------------------------------------
def plan(text, style=None, rng=None):
    """Yield the `Event` stream for typing `text` in `style`.

    The stream always reconstructs `text` exactly — see `replay`.
    """
    style = (style or TypingStyle()).clamped()
    rng = rng or random.Random()
    drift = RhythmDrift(style.rhythm_drift, rng=rng)

    total = len(text)
    i = 0
    prev = None
    done = 0                      # source characters correctly in place
    words_since_rest = 0
    next_rest = rng.randint(BURST_WORDS_MIN, BURST_WORDS_MAX)
    chars_since_idle = 0
    next_idle = rng.randint(IDLE_CHARS_MIN, IDLE_CHARS_MAX)

    def delay_for(ch, prev_ch):
        d = style.base_delay
        if style.effort_model:
            d *= keystroke_effort(ch, prev_ch)
        d *= drift.step()
        if style.variation:
            d += rng.uniform(-style.variation, style.variation)
        if style.warmup and style.warmup_chars > 0 and done < style.warmup_chars:
            cold = 1.0 - (done / style.warmup_chars)
            d += style.base_delay * style.warmup_extra * cold
        if style.fatigue and total:
            d += style.base_delay * (done / total) * style.fatigue_factor
        return max(0.0, d)

    def safe_lookahead(start):
        """How many characters past `start` we can keep typing before noticing
        the mistake, without running off the end or across a line break."""
        want = rng.randint(0, style.notice_max) if style.notice_max else 0
        n = 0
        j = start
        while n < want and j < total and text[j] != "\n":
            n += 1
            j += 1
        return n

    def mistake(at, wrong, consumed):
        """Build the full slip → notice → backspace → retype sequence.

        `wrong` is what actually gets struck in place of `text[at:at+consumed]`.
        Returns (events, next_index, last_char_typed).
        """
        out = []
        ahead = safe_lookahead(at + consumed)
        tail = text[at + consumed:at + consumed + ahead]
        p = prev

        for c in wrong:
            out.append(Char(c, 0))
            out.append(Pause(delay_for(c, p)))
            p = c
        for c in tail:
            out.append(Char(c, 0))
            out.append(Pause(delay_for(c, p)))
            p = c

        # The beat where your eyes catch up with your hands. Longer the
        # further past the mistake you got.
        out.append(Pause(style.base_delay * rng.uniform(2.0, 5.0) * (1 + 0.4 * ahead),
                         "spotted a mistake"))

        for _ in range(len(wrong) + len(tail)):
            out.append(Key("backspace"))
            out.append(Pause(style.base_delay * rng.uniform(0.30, 0.75)))

        # Retyping is deliberately a touch slower — you are watching the keys.
        correct = text[at:at + consumed + ahead]
        p = prev
        for c in correct:
            out.append(Char(c, 1))
            out.append(Pause(delay_for(c, p) * rng.uniform(1.0, 1.25)))
            p = c
        return out, at + consumed + ahead, p

    while i < total:
        ch = text[i]

        # ── Line and paragraph breaks ────────────────────────────────────
        if ch == "\n":
            blank_line = i + 1 < total and text[i + 1] == "\n"
            yield (Key("enter", 1) if style.press_enter else Char(ch, 1))
            done += 1
            i += 1
            if blank_line:
                yield Pause(style.para_pause, "between paragraphs")
                yield (Key("enter", 1) if style.press_enter else Char("\n", 1))
                done += 1
                i += 1
            else:
                yield Pause(delay_for("\n", prev))
            prev = "\n"
            continue

        # ── Beat before a new sentence ───────────────────────────────────
        if (style.think_before_sentence
                and i >= 2 and text[i - 1] == " " and text[i - 2] in ".!?"
                and rng.random() < style.think_before_sentence):
            nxt = text.find(".", i)
            span = (nxt - i) if nxt > i else 40
            yield Note("composing the next sentence…")
            yield Pause(style.punct_pause * rng.uniform(1.5, 3.0)
                        + min(1.2, span / 260.0), "thinking")

        # ── Stalling before a long or awkward word ───────────────────────
        if (style.hesitate_chance
                and (i == 0 or text[i - 1] == " ")
                and rng.random() < style.hesitate_chance):
            m = re.match(r"[A-Za-z][A-Za-z'-]*", text[i:])
            if m and len(m.group(0)) >= 8:
                yield Pause(style.base_delay * rng.uniform(6.0, 14.0),
                            "reaching for a word")

        # ── Mistakes. At most one per position, all self-correcting. ─────
        events = None
        word_start = (i == 0 or not text[i - 1].isalpha())

        if (style.common_typo_chance and ch.isalpha() and word_start):
            m = re.match(r"[A-Za-z]+", text[i:])
            if m:
                word = m.group(0)
                wrong = COMMON_TYPOS.get(word.lower())
                if wrong and rng.random() < style.common_typo_chance:
                    if word[0].isupper():
                        wrong = wrong[0].upper() + wrong[1:]
                    events, i, prev = mistake(i, wrong, len(word))

        if (events is None and style.double_letter_chance
                and ch.isalpha() and i + 1 < total and text[i + 1] == ch
                and rng.random() < style.double_letter_chance):
            # Dropped one half of a double letter: "still" typed as "stil".
            events, i, prev = mistake(i, ch, 2)

        if (events is None and style.double_letter_chance
                and ch.isalpha()
                and not (i + 1 < total and text[i + 1] == ch)
                and rng.random() < style.double_letter_chance * 0.6):
            # Bounced the key: "writing" typed as "writting".
            events, i, prev = mistake(i, ch + ch, 1)

        if (events is None and style.transpose_chance
                and ch.isalpha() and i + 1 < total
                and text[i + 1].isalpha() and text[i + 1] != ch
                and rng.random() < style.transpose_chance):
            events, i, prev = mistake(i, text[i + 1] + ch, 2)

        if (events is None and style.cap_slip_chance
                and ch.isalpha() and ch.isupper()
                and rng.random() < style.cap_slip_chance):
            events, i, prev = mistake(i, ch.lower(), 1)

        if (events is None and style.typo_chance
                and ch.lower() in NEARBY_KEYS
                and rng.random() < style.typo_chance):
            wrong = rng.choice(NEARBY_KEYS[ch.lower()])
            if ch.isupper():
                wrong = wrong.upper()
            events, i, prev = mistake(i, wrong, 1)

        if events is not None:
            for ev in events:
                yield ev
                if isinstance(ev, Char):
                    done += ev.advance
            continue

        # ── The ordinary case: strike the right key ──────────────────────
        yield Char(ch, 1)
        done += 1
        i += 1

        delay = delay_for(ch, prev)
        if ch in ".!?":
            delay += style.punct_pause
        elif ch in ";:":
            delay += style.punct_pause * style.semicolon_factor
        elif ch == ",":
            delay += style.punct_pause * style.comma_factor
        elif ch == " " and style.word_burst:
            delay += rng.uniform(0, style.base_delay * 0.5)
        yield Pause(delay)
        prev = ch

        # ── Resting between bursts of words ──────────────────────────────
        if style.burst_mode and ch == " ":
            words_since_rest += 1
            if words_since_rest >= next_rest:
                yield Pause(rng.uniform(BURST_REST_MIN, BURST_REST_MAX), "resting")
                words_since_rest = 0
                next_rest = rng.randint(BURST_WORDS_MIN, BURST_WORDS_MAX)

        # ── Longer idle pauses ───────────────────────────────────────────
        if style.idle_pauses:
            chars_since_idle += 1
            if chars_since_idle >= next_idle:
                yield Note("pausing to think…")
                yield Pause(rng.uniform(IDLE_PAUSE_MIN, IDLE_PAUSE_MAX), "thinking")
                chars_since_idle = 0
                next_idle = rng.randint(IDLE_CHARS_MIN, IDLE_CHARS_MAX)


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------
def replay(events):
    """Apply an event stream to a virtual text buffer and return the result.

    This is what the target window would end up containing. The test-suite
    asserts it equals the input for every style, which is the guarantee that
    the realism never leaks into the finished text.
    """
    buf = []
    for ev in events:
        if isinstance(ev, Char):
            buf.append(ev.ch)
        elif isinstance(ev, Key):
            if ev.name == "backspace":
                if buf:
                    buf.pop()
            elif ev.name == "enter":
                buf.append("\n")
    return "".join(buf)


def estimate_seconds(text, style=None, rng=None, samples=1):
    """Expected wall-clock seconds to type `text`, by planning it."""
    best = 0.0
    for n in range(max(1, samples)):
        r = rng or random.Random(n)
        total = 0.0
        for ev in plan(text, style, r):
            if isinstance(ev, Pause):
                total += ev.seconds
        best += total
    return best / max(1, samples)
