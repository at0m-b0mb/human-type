import collections
import json
import math
import platform
import threading
import time
import random
import re
import datetime as _dt
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pyautogui
import pyperclip

import docimport
import realism as rz
import theme as T

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# macOS compatibility — pynput is more reliable than pyautogui on macOS
# because it uses CoreGraphics events that correctly handle shift-modified
# keys (uppercase letters, symbols, etc.). pyautogui.write() silently drops
# or mis-types many characters on macOS regardless of Accessibility settings.
# ---------------------------------------------------------------------------
_IS_MAC = platform.system() == "Darwin"
_PASTE_HOTKEY = ("command", "v") if _IS_MAC else ("ctrl", "v")
_WRITE_INTERVAL = 0

if _IS_MAC:
    try:
        from pynput.keyboard import Controller as _KbdController, Key as _Key
        _MAC_KBD = _KbdController()
        _MAC_PYNPUT_ERROR = None
    except Exception as _exc:
        _MAC_KBD = None
        _MAC_PYNPUT_ERROR = str(_exc)
else:
    _MAC_KBD = None
    _MAC_PYNPUT_ERROR = None

# ---------------------------------------------------------------------------
# Persistence — settings, recent files, custom presets, snippets, stats
# ---------------------------------------------------------------------------
CONFIG_PATH = Path.home() / ".humantyper.json"

DEFAULT_CONFIG = {
    # Light by default: this is a document tool, and paper reads better for
    # long text than a dark editor does. Dark is one click away in the rail.
    "theme": "Gold",
    "appearance": "Light",
    "dark_mode": False,   # kept so older versions still read this file
    "recent_files": [],
    "custom_presets": {},
    "custom_snippets": {},
    "draft": "",
    "realism_profile": "Natural",
    "newline_mode": "Press Enter",
    "rhythm_drift": 0.11,
    "notice_max": 3,
    "session_history": [],
    "repeat": {"count": "1", "separator": "\\n\\n"},
    "stats": {
        "lifetime_chars": 0,
        "lifetime_sessions": 0,
        "lifetime_seconds": 0.0,
        "lifetime_keystrokes": 0,
        "lifetime_corrections": 0,
        "best_wpm": 0.0,
    },
    "last_settings": {
        "start_delay": "5",
        "base_delay": "0.08",
        "variation": "0.03",
        "punct_pause": "0.25",
        "para_pause": "0.8",
        "typo_chance": "0.04",
    },
    "toggles": {
        "newlines_enter": False,
        "word_burst": True,
        "fatigue": False,
        "common_typos": False,
        "cap_slips": False,
        "burst_mode": False,
        "idle_pauses": False,
        "effort_model": True,
        "warmup": True,
        "sentence_thinking": False,
        "transpose": False,
        "double_letters": False,
        "expand_vars": True,
        "show_overlay": False,
    },
}


def load_config():
    if not CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        # Deep-merge to keep new keys when upgrading
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in data.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Appearance — the palette itself lives in theme.py
# ---------------------------------------------------------------------------
THEMES = T.ACCENTS
DEFAULT_THEME = T.DEFAULT_ACCENT

# Accent names used before the interface was redesigned.
LEGACY_THEMES = {
    "Midnight": "Royal", "Dracula": "Royal", "Cyberpunk": "Burgundy",
    "Forest": "Emerald", "Ocean": "Slate", "Sunset": "Gold",
}


# Light, Dark, or follow whatever the operating system is doing.
APPEARANCE_MODES = {"Light": "light", "Dark": "dark", "Auto": "system"}
DEFAULT_APPEARANCE = "Light"


def resolve_appearance(name, dark_mode_fallback=False):
    """The saved appearance choice, or one derived from the old boolean."""
    if name in APPEARANCE_MODES:
        return name
    return "Dark" if dark_mode_fallback else "Light"


def resolve_theme(name):
    if name in T.ACCENTS:
        return name
    return LEGACY_THEMES.get(name, T.DEFAULT_ACCENT)


# ---------------------------------------------------------------------------
# Speed presets
# ---------------------------------------------------------------------------
PRESETS = {
    "Slow":    {"base_delay": 0.15, "variation": 0.07,  "punct_pause": 0.40, "typo_chance": 0.02, "para_pause": 1.2},
    "Normal":  {"base_delay": 0.08, "variation": 0.03,  "punct_pause": 0.25, "typo_chance": 0.04, "para_pause": 0.8},
    "Fast":    {"base_delay": 0.04, "variation": 0.02,  "punct_pause": 0.12, "typo_chance": 0.02, "para_pause": 0.4},
    "Blazing": {"base_delay": 0.01, "variation": 0.005, "punct_pause": 0.04, "typo_chance": 0.00, "para_pause": 0.1},
}

# ---------------------------------------------------------------------------
# Built-in snippets
# ---------------------------------------------------------------------------
BUILTIN_SNIPPETS = {
    "Hello (formal)":
        "Dear Sir or Madam,\n\nI hope this message finds you well. "
        "I am writing to follow up on our previous conversation.",
    "Hello (casual)":
        "Hey! Just wanted to drop a quick note to see how things are going on your end.",
    "Lorem ipsum (short)":
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incidunt ut labore et dolore magna aliqua.",
    "Lorem ipsum (paragraph)":
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do "
        "eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut "
        "enim ad minim veniam, quis nostrud exercitation ullamco laboris "
        "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
        "reprehenderit in voluptate velit esse cillum dolore eu fugiat "
        "nulla pariatur.",
    "Pangram":
        "The quick brown fox jumps over the lazy dog.",
    "Code (python)":
        "def fibonacci(n):\n"
        "    a, b = 0, 1\n"
        "    for _ in range(n):\n"
        "        a, b = b, a + b\n"
        "    return a\n",
    "Email signoff":
        "Thanks again for your time, and please don't hesitate to reach out "
        "if you need anything further.\n\nBest regards,",
}

# ---------------------------------------------------------------------------
# Variables / macros — expanded just before typing
# ---------------------------------------------------------------------------
VARIABLES = [
    ("{date}",       "Today's date (YYYY-MM-DD)"),
    ("{time}",       "Current time (HH:MM)"),
    ("{datetime}",   "ISO date + time"),
    ("{weekday}",    "Day of week (e.g. Wednesday)"),
    ("{month}",      "Month name (e.g. May)"),
    ("{year}",       "Current year"),
    ("{clipboard}",  "Current clipboard contents"),
    ("{random:6}",   "Random N-digit number (change 6)"),
    ("{tab}",        "Tab character"),
    ("{newline}",    "Newline character"),
]


def expand_variables(text):
    """Replace {date}, {time}, {clipboard}, {random:N}, etc. in `text`."""
    now = _dt.datetime.now()
    repl = {
        "{date}":     now.strftime("%Y-%m-%d"),
        "{time}":     now.strftime("%H:%M"),
        "{datetime}": now.strftime("%Y-%m-%d %H:%M"),
        "{weekday}":  now.strftime("%A"),
        "{month}":    now.strftime("%B"),
        "{year}":     now.strftime("%Y"),
        "{tab}":      "\t",
        "{newline}":  "\n",
    }
    for k, v in repl.items():
        text = text.replace(k, v)

    try:
        clip = pyperclip.paste() or ""
    except Exception:
        clip = ""
    text = text.replace("{clipboard}", clip)

    def _rand(m):
        n = max(1, min(20, int(m.group(1))))
        return str(random.randint(10 ** (n - 1), 10 ** n - 1))
    text = re.sub(r"\{random:(\d+)\}", _rand, text)
    return text


# ---------------------------------------------------------------------------
# Text transforms — pure string operations
# ---------------------------------------------------------------------------
def _smart_quotes(s):
    out = []
    in_dq = False
    in_sq = False
    for c in s:
        if c == '"':
            out.append("”" if in_dq else "“")
            in_dq = not in_dq
        elif c == "'":
            out.append("’" if in_sq else "‘")
            in_sq = not in_sq
        else:
            out.append(c)
    return "".join(out)


def _strip_markdown(s):
    s = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s


def _sentence_case(s):
    def cap(m):
        return m.group(1) + m.group(2).upper()
    return re.sub(r"(^|[.!?]\s+)([a-z])", cap, s.lower())


TRANSFORMS = [
    ("UPPERCASE",        lambda s: s.upper()),
    ("lowercase",        lambda s: s.lower()),
    ("Title Case",       lambda s: s.title()),
    ("Sentence case",    _sentence_case),
    ("Trim each line",   lambda s: "\n".join(line.strip() for line in s.splitlines())),
    ("Collapse spaces",  lambda s: re.sub(r"[ \t]+", " ", s)),
    ("Sort lines A→Z",   lambda s: "\n".join(sorted(s.splitlines()))),
    ("Reverse lines",    lambda s: "\n".join(reversed(s.splitlines()))),
    ("Dedupe lines",     lambda s: "\n".join(dict.fromkeys(s.splitlines()))),
    ("Smart quotes",     _smart_quotes),
    ("Strip markdown",   _strip_markdown),
]


def flesch_reading_ease(text):
    words = re.findall(r"[A-Za-z']+", text)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    if not words:
        return 0, 0
    syllables = sum(_count_syllables(w) for w in words)
    w, s, sy = len(words), sentences, syllables
    ease = 206.835 - 1.015 * (w / s) - 84.6 * (sy / w)
    grade = 0.39 * (w / s) + 11.8 * (sy / w) - 15.59
    return ease, grade


def _count_syllables(word):
    word = word.lower()
    if not word:
        return 0
    vowels = "aeiouy"
    count, prev = 0, False
    for c in word:
        v = c in vowels
        if v and not prev:
            count += 1
        prev = v
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


# ---------------------------------------------------------------------------
# Typing behaviour — the realism engine lives in realism.py so it can be
# tested without a GUI or a keyboard. These are re-exported for convenience.
# ---------------------------------------------------------------------------
CHARS_PER_WORD          = rz.CHARS_PER_WORD
NEARBY_KEYS             = rz.NEARBY_KEYS
COMMON_TYPOS            = rz.COMMON_TYPOS
REALISM_PROFILES        = list(rz.PROFILES.keys())
DEFAULT_REALISM         = "Natural"

# How newlines are delivered to the target window.
NEWLINE_MODES = {
    "Press Enter":   "enter",
    "Shift + Enter": "shift_enter",
    "Skip (join)":   "skip",
}
NEWLINE_HELP = {
    "enter":       "Sends a real Enter — right for documents and editors.",
    "shift_enter": "Soft line break — right for Slack, Discord and chat boxes.",
    "skip":        "Newlines are dropped, so the text arrives as one run of prose.",
}

# Planning a very long document up front costs memory, so above this length
# the app streams the plan and falls back to a sampled time estimate.
MAX_PLANNED_CHARS = 200_000
# Estimating time by planning is exact but not free; long texts are sampled.
ESTIMATE_SAMPLE_CHARS = 3_000


# ===========================================================================
# Main app
# ===========================================================================
class HumanTyperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Human Typer")
        self.geometry("1320x880")
        self.minsize(1080, 720)

        self.config = load_config()
        # Light is the default: this is a document tool, and paper reads
        # better for long text than a dark editor does. "Auto" hands the
        # decision to the operating system.
        self._appearance = resolve_appearance(
            self.config.get("appearance"),
            self.config.get("dark_mode", False))
        ctk.set_appearance_mode(APPEARANCE_MODES[self._appearance])
        ctk.set_default_color_theme("blue")
        self._theme_name = resolve_theme(self.config.get("theme", DEFAULT_THEME))
        T.set_accent(self._theme_name)
        self._current_page = "Compose"

        self._stop = False
        self._pause = threading.Event()
        self._pause.set()
        self._typing_active = False
        self._paused_total = 0.0     # seconds spent paused, excluded from WPM
        self._pause_started = None

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.01

        self._build_ui()
        self._restore_state()
        self._bind_hotkeys()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if _IS_MAC and _MAC_KBD is None:
            self.after(500, lambda: messagebox.showwarning(
                "macOS Setup Issue",
                "pynput could not be loaded, so typing may not work correctly "
                "on macOS.\n\n"
                f"Error: {_MAC_PYNPUT_ERROR}\n\n"
                "Run:  pip install pynput\n"
                "then restart the app.",
            ))

    # =======================================================================
    # UI construction
    # =======================================================================
    # =======================================================================
    # Shell
    #
    # A fixed left rail for identity, navigation and live session figures; a
    # content column that changes with the page; a persistent action bar so
    # Start is never more than one glance away, whatever page you are on.
    # =======================================================================
    NAV = [
        ("Compose",   "Compose",
         "Write, open or paste the text you want typed."),
        ("Behaviour", "Behaviour",
         "How fast the keys go down, how human it looks, and how it reaches the window."),
        ("Library",   "Library",
         "Saved passages you reach for often."),
        ("Insights",  "Insights",
         "What you have typed, how quickly, and how cleanly."),
        ("About",     "About",
         "Formats, variables, shortcuts and the guarantees this app makes."),
    ]

    def _build_ui(self):
        self.configure(fg_color=T.CANVAS)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._accented = []      # widgets to re-skin when the accent changes

        self._build_rail()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        self._build_page_header(content)

        self._page_host = ctk.CTkFrame(content, fg_color="transparent")
        self._page_host.grid(row=1, column=0, sticky="nsew",
                             padx=T.SPACE["xl"])
        self._page_host.grid_columnconfigure(0, weight=1)
        self._page_host.grid_rowconfigure(0, weight=1)

        self._pages = {}
        self._build_compose_page()
        self._build_behaviour_page()
        self._build_library_page()
        self._build_insights_page()
        self._build_about_page()

        self._build_action_bar(content)
        self._show_page("Compose")

    def _accent_widget(self, widget, recipe):
        """Re-apply `recipe()` to `widget` whenever the accent changes."""
        self._accented.append((widget, recipe))
        return widget

    # ----- Left rail -------------------------------------------------------
    def _build_rail(self):
        rail = ctk.CTkFrame(self, width=T.RAIL_WIDTH, corner_radius=0,
                            fg_color=T.SURFACE)
        rail.grid(row=0, column=0, sticky="nsw")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(2, weight=1)

        # Hairline between rail and canvas, instead of a heavy border
        ctk.CTkFrame(self, width=T.HAIRLINE, fg_color=T.BORDER,
                     corner_radius=0).grid(row=0, column=0, sticky="nse")

        # Wordmark
        brand = ctk.CTkFrame(rail, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew",
                   padx=T.SPACE["xl"], pady=(T.SPACE["xl"], T.SPACE["lg"]))
        ctk.CTkLabel(brand, text="Human Typer", font=T.font("wordmark"),
                     text_color=T.INK, anchor="w").pack(anchor="w")
        rule = ctk.CTkFrame(brand, height=3, width=34, corner_radius=2,
                            fg_color=T.accent("shine"))
        rule.pack(anchor="w", pady=(7, 7))
        self._accent_widget(rule, lambda: {"fg_color": T.accent("shine")})
        ctk.CTkLabel(brand,
                     text="Typing that behaves\nlike a person typing.",
                     font=T.font("small"), text_color=T.INK_3,
                     justify="left", anchor="w").pack(anchor="w")

        # Navigation
        nav = ctk.CTkFrame(rail, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=T.SPACE["md"])
        nav.grid_columnconfigure(0, weight=1)
        self._nav_buttons = {}
        for i, (key, label, _sub) in enumerate(self.NAV):
            row = ctk.CTkFrame(nav, fg_color="transparent", corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)

            mark = ctk.CTkFrame(row, width=4, height=20, corner_radius=2,
                                fg_color="transparent")
            mark.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=9)

            btn = ctk.CTkButton(
                row, text=label, anchor="w", height=34,
                fg_color="transparent", hover_color=T.SURFACE_ALT,
                text_color=T.INK_2, font=T.font("body"),
                corner_radius=8, border_width=0,
                command=lambda k=key: self._show_page(k),
            )
            btn.grid(row=0, column=1, sticky="ew")
            self._nav_buttons[key] = (row, mark, btn)

        # Live session figures — a quiet ledger, not a dashboard
        ledger = ctk.CTkFrame(rail, fg_color="transparent")
        ledger.grid(row=3, column=0, sticky="ew",
                    padx=T.SPACE["xl"], pady=(0, T.SPACE["lg"]))
        ledger.grid_columnconfigure(1, weight=1)

        ctk.CTkFrame(ledger, height=T.HAIRLINE, fg_color=T.BORDER).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, T.SPACE["md"]))
        ctk.CTkLabel(ledger, text="THIS RUN", font=T.font("eyebrow"),
                     text_color=T.INK_3, anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, T.SPACE["sm"]))

        self._build_cadence(ledger, row=2)

        self._mini_wpm_var = tk.StringVar(value="—")
        self._mini_done_var = tk.StringVar(value="0%")
        self._mini_eta_var = tk.StringVar(value="—")
        self._mini_acc_var = tk.StringVar(value="—")
        for r, (label, var) in enumerate([
            ("Speed", self._mini_wpm_var),
            ("Progress", self._mini_done_var),
            ("Remaining", self._mini_eta_var),
            ("Accuracy", self._mini_acc_var),
        ], start=3):
            ctk.CTkLabel(ledger, text=label, font=T.font("small"),
                         text_color=T.INK_3, anchor="w").grid(
                row=r, column=0, sticky="w", pady=3)
            ctk.CTkLabel(ledger, textvariable=var, font=T.font("metric_sm"),
                         text_color=T.INK, anchor="e").grid(
                row=r, column=1, sticky="e", pady=3)

        # Appearance
        appearance = ctk.CTkFrame(rail, fg_color="transparent")
        appearance.grid(row=4, column=0, sticky="ew",
                        padx=T.SPACE["xl"], pady=(0, T.SPACE["xl"]))
        appearance.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(appearance, height=T.HAIRLINE, fg_color=T.BORDER).grid(
            row=0, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        ctk.CTkLabel(appearance, text="APPEARANCE", font=T.font("eyebrow"),
                     text_color=T.INK_3, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(0, T.SPACE["sm"]))

        self._theme_menu = ctk.CTkOptionMenu(
            appearance, values=list(T.ACCENTS.keys()),
            command=self._on_theme_change, **T.option_menu_kwargs())
        self._theme_menu.set(self._theme_name)
        self._theme_menu.grid(row=2, column=0, sticky="ew")
        self._accent_widget(self._theme_menu, T.option_menu_kwargs)

        self._mode_seg = ctk.CTkSegmentedButton(
            appearance, values=list(APPEARANCE_MODES.keys()),
            command=self._on_mode_change, height=30,
            **T.segmented_kwargs())
        self._mode_seg.set(self._appearance)
        self._mode_seg.grid(row=3, column=0, sticky="ew", pady=(T.SPACE["sm"], 0))
        self._accent_widget(self._mode_seg, T.segmented_kwargs)
        ctk.CTkLabel(appearance, text="Auto follows your system setting.",
                     font=T.font("micro"), text_color=T.INK_3,
                     anchor="w").grid(row=4, column=0, sticky="w", pady=(6, 0))

    # ----- Cadence meter ---------------------------------------------------
    # The one ornament in the app, and it is made of real data: each bar is a
    # gap between two keystrokes, on a log scale so a correction pause and a
    # fast roll are both legible. Idle, it shows the engine's own rhythm for a
    # sample phrase; during a run it shows the gaps actually being executed.
    CADENCE_BARS = 44
    CADENCE_MIN_MS = 18.0
    CADENCE_MAX_MS = 900.0

    def _build_cadence(self, parent, row):
        self._cadence = collections.deque(maxlen=self.CADENCE_BARS)
        self._cadence_last_draw = 0.0
        self._cadence_live = False

        self._cadence_canvas = tk.Canvas(
            parent, height=38, highlightthickness=0, bd=0,
            bg=T.resolve(T.SURFACE))
        self._cadence_canvas.grid(row=row, column=0, columnspan=2, sticky="ew",
                                  pady=(2, T.SPACE["md"]))
        self._cadence_canvas.bind("<Configure>", lambda _e: self._cadence_draw())
        self._cadence_seed()

    def _cadence_seed(self):
        """Fill the meter with the engine's rhythm for a sample phrase."""
        try:
            style = rz.profile("Natural")
            style.base_delay, style.variation = 0.08, 0.03
            style.punct_pause = style.para_pause = 0.0
            gaps = [ev.seconds * 1000.0
                    for ev in rz.plan("the quick brown fox jumps over it",
                                      style, random.Random(4))
                    if isinstance(ev, rz.Pause)]
        except Exception:
            gaps = [80.0] * self.CADENCE_BARS
        self._cadence.clear()
        for gap in gaps[-self.CADENCE_BARS:]:
            self._cadence.append(gap)
        self._cadence_live = False
        self._cadence_draw()

    def _cadence_push(self, seconds):
        """Record one executed gap. Called from the typing thread."""
        self._cadence.append(seconds * 1000.0)
        now = time.time()
        if now - self._cadence_last_draw < 0.07:
            return
        self._cadence_last_draw = now
        self._cadence_live = True
        self.after(0, self._cadence_draw)

    def _cadence_draw(self):
        canvas = getattr(self, "_cadence_canvas", None)
        if canvas is None:
            return
        try:
            canvas.delete("all")
            canvas.configure(bg=T.resolve(T.SURFACE))
            width = canvas.winfo_width() or 184
            height = canvas.winfo_height() or 38
        except tk.TclError:
            return

        values = list(self._cadence)
        if not values:
            return
        count = len(values)
        slot = width / self.CADENCE_BARS
        bar_w = max(2.0, slot - 1.6)

        quiet = T.resolve(T.BORDER_STRONG)
        recent = T.resolve(T.accent("accent"))
        newest = T.resolve(T.accent("shine"))
        lo, hi = math.log10(self.CADENCE_MIN_MS), math.log10(self.CADENCE_MAX_MS)

        for i, ms in enumerate(values):
            clamped = min(self.CADENCE_MAX_MS, max(self.CADENCE_MIN_MS, ms))
            t = (math.log10(clamped) - lo) / (hi - lo)
            bar_h = max(2.0, t * (height - 4))
            x = (self.CADENCE_BARS - count + i) * slot
            y = height - bar_h
            from_end = count - i
            if self._cadence_live and from_end == 1:
                colour = newest
            elif self._cadence_live and from_end <= 6:
                colour = recent
            else:
                colour = quiet
            canvas.create_rectangle(x, y, x + bar_w, height,
                                    fill=colour, outline="")

    # ----- Dialog helpers --------------------------------------------------
    # Secondary windows are the easiest place for a design system to leak. A
    # CustomTkinter widget with no colours falls back to the toolkit default,
    # which against warm paper reads as a disabled control rather than a
    # styled one. Everything below goes through these.
    def _dialog(self, title, size=None):
        win = ctk.CTkToplevel(self)
        win.title(title)
        if size:
            win.geometry(size)
        win.configure(fg_color=T.CANVAS)
        win.transient(self)
        return win

    def _fit_dialog(self, win, min_width=420, resizable=False):
        """Grow the window to whatever its content actually needs.

        Hard-coding a height is how the Find & Replace buttons ended up off
        the bottom edge: the number was measured against one machine's font
        metrics, and every other platform renders taller. Asking Tk for the
        requested size cannot be wrong.
        """
        win.update_idletasks()
        width = max(min_width, win.winfo_reqwidth())
        height = win.winfo_reqheight()
        win.geometry("%dx%d" % (width, height))
        win.minsize(width, height)
        win.resizable(resizable, resizable)
        # Centre on the main window rather than the screen corner.
        try:
            x = self.winfo_rootx() + (self.winfo_width() - width) // 2
            y = self.winfo_rooty() + (self.winfo_height() - height) // 3
            win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        except Exception:
            pass
        return win

    def _dialog_heading(self, parent, title, subtitle=None):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(head, text=title, font=T.font("card_title"),
                     text_color=T.INK, anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(head, text=subtitle, font=T.font("small"),
                         text_color=T.INK_3, anchor="w", justify="left",
                         wraplength=520).pack(anchor="w", pady=(3, 0))
        return head

    def _ask_text(self, title, prompt):
        """A themed one-line prompt. Returns the string, or None if cancelled."""
        dlg = ctk.CTkInputDialog(text=prompt, title=title,
                                 **T.input_dialog_kwargs())
        return dlg.get_input()

    def _menu(self):
        return tk.Menu(self, **T.menu_kwargs())

    def _popup(self, menu):
        self._popup(menu)

    def _show_page(self, key):
        for name, page in self._pages.items():
            if name == key:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        for name, (row, mark, btn) in self._nav_buttons.items():
            active = name == key
            row.configure(fg_color=T.accent("accent_soft") if active
                          else "transparent")
            mark.configure(fg_color=T.accent("shine") if active else "transparent")
            btn.configure(text_color=T.INK if active else T.INK_2,
                          font=T.font("body_bold" if active else "body"),
                          fg_color="transparent")
        for nav_key, title, subtitle in self.NAV:
            if nav_key == key:
                self._page_eyebrow.set(title.upper())
                self._page_title.set(title)
                self._page_sub.set(subtitle)
        self._current_page = key

    # ----- Page header -----------------------------------------------------
    def _build_page_header(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew",
                  padx=T.SPACE["xl"], pady=(T.SPACE["xl"], T.SPACE["lg"]))
        head.grid_columnconfigure(0, weight=1)

        self._page_eyebrow = tk.StringVar(value="COMPOSE")
        self._page_title = tk.StringVar(value="Compose")
        self._page_sub = tk.StringVar(value="")

        eyebrow = ctk.CTkLabel(head, textvariable=self._page_eyebrow,
                               font=T.font("eyebrow"),
                               text_color=T.accent("gold"), anchor="w")
        eyebrow.grid(row=0, column=0, sticky="w")
        self._accent_widget(eyebrow, lambda: {"text_color": T.accent("gold")})

        ctk.CTkLabel(head, textvariable=self._page_title,
                     font=T.font("page_title"), text_color=T.INK,
                     anchor="w").grid(row=1, column=0, sticky="w", pady=(2, 0))
        ctk.CTkLabel(head, textvariable=self._page_sub, font=T.font("subtitle"),
                     text_color=T.INK_3, anchor="w").grid(
            row=2, column=0, sticky="w", pady=(3, 0))

    # ----- Building blocks -------------------------------------------------
    def _page(self, key, scroll=False):
        """A page, plus the frame its content goes in.

        Every page is registered as a plain holder frame even when its content
        scrolls. CTkScrollableFrame does not forward grid_remove() to the
        widget that is actually gridded, so hiding one directly leaves it on
        screen — pages would pile up on top of each other. Showing and hiding
        the holder sidesteps that entirely.
        """
        holder = ctk.CTkFrame(self._page_host, fg_color="transparent")
        holder.grid(row=0, column=0, sticky="nsew")
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        self._pages[key] = holder
        if not scroll:
            return holder
        inner = ctk.CTkScrollableFrame(
            holder, fg_color="transparent",
            scrollbar_button_color=T.BORDER_STRONG,
            scrollbar_button_hover_color=T.INK_3)
        inner.grid(row=0, column=0, sticky="nsew")
        inner.grid_columnconfigure(0, weight=1)
        return inner

    def _card(self, parent, title=None, subtitle=None, **grid):
        """A surface with an optional heading. Returns the body frame."""
        card = ctk.CTkFrame(parent, **T.card_kwargs())
        if grid:
            card.grid(**grid)
        card.grid_columnconfigure(0, weight=1)
        row = 0
        if title:
            ctk.CTkLabel(card, text=title, font=T.font("card_title"),
                         text_color=T.INK, anchor="w").grid(
                row=0, column=0, sticky="ew",
                padx=T.CARD_PAD, pady=(T.SPACE["lg"], 0))
            row = 1
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=T.font("small"),
                         text_color=T.INK_3, anchor="w", justify="left",
                         wraplength=700).grid(
                row=1, column=0, sticky="ew", padx=T.CARD_PAD, pady=(3, 0))
            row = 2
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=row, column=0, sticky="nsew",
                  padx=T.CARD_PAD, pady=(T.SPACE["md"], T.SPACE["lg"]))
        body.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(row, weight=1)
        card.body = body
        return card

    def _field_label(self, parent, text, **grid):
        lbl = ctk.CTkLabel(parent, text=text, font=T.font("small"),
                           text_color=T.INK_2, anchor="w")
        if grid:
            lbl.grid(**grid)
        return lbl

    def _hint(self, parent, text, **grid):
        lbl = ctk.CTkLabel(parent, text=text, font=T.font("micro"),
                           text_color=T.INK_3, anchor="w", justify="left",
                           wraplength=grid.pop("wrap", 320))
        if grid:
            lbl.grid(**grid)
        return lbl

    def _metric(self, parent, label, initial, r, c, big=True):
        tile = ctk.CTkFrame(parent, fg_color=T.SURFACE_ALT,
                            corner_radius=T.RADIUS_CONTROL,
                            border_width=T.HAIRLINE, border_color=T.BORDER)
        tile.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
        tile.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tile, text=label.upper(), font=T.font("eyebrow"),
                     text_color=T.INK_3, anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        var = tk.StringVar(value=initial)
        ctk.CTkLabel(tile, textvariable=var,
                     font=T.font("metric" if big else "metric_sm"),
                     text_color=T.INK, anchor="w").grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        return var

    # =======================================================================
    # Compose
    # =======================================================================
    def _build_compose_page(self):
        page = self._page("Compose")
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, minsize=T.INSPECTOR_WIDTH, weight=0)
        page.grid_rowconfigure(0, weight=1)

        editor_card = ctk.CTkFrame(page, **T.card_kwargs())
        editor_card.grid(row=0, column=0, sticky="nsew", padx=(0, T.SPACE["md"]))
        editor_card.grid_columnconfigure(0, weight=1)
        editor_card.grid_rowconfigure(1, weight=1)

        # Toolbar — words, not icons. Icons need labels anyway at this size.
        bar = ctk.CTkFrame(editor_card, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew",
                 padx=T.SPACE["md"], pady=(T.SPACE["md"], T.SPACE["sm"]))
        for label, cmd, width in [
            ("Open",      self.load_file, 74),
            ("Clipboard", self.import_clipboard, 92),
            ("Recent",    self._open_recent_menu, 78),
            ("Find",      self.open_find_replace, 66),
            ("Transform", self._open_transform_menu, 92),
            ("Variable",  self._open_variables_menu, 84),
            ("Dry run",   self._dry_run, 80),
        ]:
            ctk.CTkButton(bar, text=label, width=width, command=cmd,
                          **T.ghost_button_kwargs()).pack(side="left", padx=(0, 2))
        ctk.CTkButton(bar, text="Clear", width=64, command=self.clear_text,
                      **T.quiet_button_kwargs()).pack(side="left", padx=(2, 0))


        self._tb = ctk.CTkTextbox(
            editor_card, wrap="word", font=T.font("editor"),
            fg_color=T.SURFACE_ALT, text_color=T.INK,
            border_width=T.HAIRLINE, border_color=T.BORDER,
            corner_radius=T.RADIUS_CONTROL,
            scrollbar_button_color=T.BORDER_STRONG,
            scrollbar_button_hover_color=T.INK_3,
        )
        self._tb.grid(row=1, column=0, sticky="nsew",
                      padx=T.SPACE["md"], pady=(0, T.SPACE["md"]))
        self._tb.bind("<<Modified>>", self._on_modified)
        self._tb.bind("<KeyRelease>", self._update_count)

        # Inspector
        insp = ctk.CTkFrame(page, **T.card_kwargs())
        insp.grid(row=0, column=1, sticky="nsew")
        insp.grid_columnconfigure(0, weight=1)
        insp.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(insp, text="Text analysis", font=T.font("card_title"),
                     text_color=T.INK, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=T.SPACE["lg"],
            pady=(T.SPACE["lg"], 0))
        ctk.CTkLabel(insp, text="Updates as you type.", font=T.font("small"),
                     text_color=T.INK_3, anchor="w").grid(
            row=1, column=0, sticky="ew", padx=T.SPACE["lg"], pady=(2, T.SPACE["md"]))

        rows = ctk.CTkFrame(insp, fg_color="transparent")
        rows.grid(row=2, column=0, sticky="new", padx=T.SPACE["lg"])
        rows.grid_columnconfigure(1, weight=1)

        self._stat_rows = {}
        analysis = [
            ("chars",      "Characters"),
            ("words",      "Words"),
            ("sentences",  "Sentences"),
            ("paragraphs", "Paragraphs"),
            ("avg_word",   "Average word"),
            (None,         None),
            ("reading",    "Read aloud"),
            ("estimate",   "Time to type"),
            (None,         None),
            ("flesch",     "Reading ease"),
            ("grade",      "Grade level"),
        ]
        r = 0
        for key, label in analysis:
            if key is None:
                ctk.CTkFrame(rows, height=T.HAIRLINE, fg_color=T.BORDER).grid(
                    row=r, column=0, columnspan=2, sticky="ew", pady=T.SPACE["sm"])
                r += 1
                continue
            ctk.CTkLabel(rows, text=label, font=T.font("small"),
                         text_color=T.INK_2, anchor="w").grid(
                row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value="—")
            self._stat_rows[key] = var
            ctk.CTkLabel(rows, textvariable=var, font=T.font("body_bold"),
                         text_color=T.INK, anchor="e").grid(
                row=r, column=1, sticky="e", pady=4)
            r += 1

        actions = ctk.CTkFrame(insp, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew",
                     padx=T.SPACE["lg"], pady=(T.SPACE["md"], T.SPACE["lg"]))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(actions, text="Save as snippet",
                      command=self._save_selection_as_snippet,
                      **T.secondary_button_kwargs()).grid(
            row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkButton(actions, text="Export text…", command=self._export_text,
                      **T.secondary_button_kwargs()).grid(
            row=1, column=0, sticky="ew")

    # =======================================================================
    # Behaviour
    # =======================================================================
    def _build_behaviour_page(self):
        page = self._page("Behaviour", scroll=True)

        # ---- Speed --------------------------------------------------------
        speed = self._card(page, "Speed",
                           "How fast the keys go down. Everything here is in seconds.",
                           row=0, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        b = speed.body
        self._preset_seg = ctk.CTkSegmentedButton(
            b, values=list(PRESETS.keys()), command=self._apply_preset,
            height=34, **T.segmented_kwargs())
        self._preset_seg.set("Normal")
        self._preset_seg.grid(row=0, column=0, sticky="ew")
        self._accent_widget(self._preset_seg, T.segmented_kwargs)

        crow = ctk.CTkFrame(b, fg_color="transparent")
        crow.grid(row=1, column=0, sticky="ew", pady=(T.SPACE["md"], 0))
        self._field_label(crow, "Saved settings").pack(side="left", padx=(0, 10))
        self._custom_preset_menu = ctk.CTkOptionMenu(
            crow, values=self._custom_preset_values(),
            command=self._apply_custom_preset, width=180,
            **T.option_menu_kwargs())
        self._custom_preset_menu.pack(side="left")
        self._accent_widget(self._custom_preset_menu, T.option_menu_kwargs)
        ctk.CTkButton(crow, text="Save current…", width=124,
                      command=self._save_custom_preset,
                      **T.secondary_button_kwargs()).pack(side="left", padx=(8, 0))
        ctk.CTkButton(crow, text="Delete", width=70,
                      command=self._delete_custom_preset,
                      **T.quiet_button_kwargs()).pack(side="left", padx=(4, 0))

        # ---- Realism ------------------------------------------------------
        realism = self._card(
            page, "Realism",
            "Speed sets the pace; this sets the character of it. Every "
            "mistake below is spotted and corrected before the run ends, so "
            "the text that arrives is exactly the text you gave it.",
            row=1, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        b = realism.body

        self._profile_var = tk.StringVar(value=DEFAULT_REALISM)
        self._profile_seg = ctk.CTkSegmentedButton(
            b, values=REALISM_PROFILES, command=self._apply_realism_profile,
            height=34, **T.segmented_kwargs())
        self._profile_seg.set(DEFAULT_REALISM)
        self._profile_seg.grid(row=0, column=0, sticky="ew")
        self._accent_widget(self._profile_seg, T.segmented_kwargs)

        self._profile_blurb = tk.StringVar(
            value=rz.PROFILE_BLURBS[DEFAULT_REALISM])
        ctk.CTkLabel(b, textvariable=self._profile_blurb, font=T.font("small"),
                     text_color=T.INK_2, anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(T.SPACE["sm"], T.SPACE["lg"]))

        sl = ctk.CTkFrame(b, fg_color="transparent")
        sl.grid(row=2, column=0, sticky="ew", pady=(0, T.SPACE["lg"]))
        sl.grid_columnconfigure(1, weight=1)

        self._drift_var = tk.DoubleVar(value=0.11)
        self._drift_lbl = tk.StringVar(value="0.11")
        self._field_label(sl, "Rhythm drift", row=0, column=0, sticky="w")
        drift = ctk.CTkSlider(
            sl, from_=0.0, to=0.30, number_of_steps=30, variable=self._drift_var,
            command=lambda v: self._drift_lbl.set(f"{float(v):.2f}"),
            **T.slider_kwargs())
        drift.grid(row=0, column=1, sticky="ew", padx=T.SPACE["lg"])
        self._accent_widget(drift, T.slider_kwargs)
        ctk.CTkLabel(sl, textvariable=self._drift_lbl, width=46,
                     font=T.font("body_bold"), text_color=T.INK,
                     anchor="e").grid(row=0, column=2, sticky="e")
        self._hint(sl, "Speeding up and slowing down in runs, rather than "
                       "jittering key to key.", wrap=620,
                   row=1, column=0, columnspan=3, sticky="w", pady=(2, T.SPACE["md"]))

        self._notice_var = tk.IntVar(value=3)
        self._notice_lbl = tk.StringVar(value="3 chars")
        self._field_label(sl, "Notice delay", row=2, column=0, sticky="w")
        notice = ctk.CTkSlider(
            sl, from_=0, to=8, number_of_steps=8, variable=self._notice_var,
            command=lambda v: self._notice_lbl.set(f"{int(float(v))} chars"),
            **T.slider_kwargs())
        notice.grid(row=2, column=1, sticky="ew", padx=T.SPACE["lg"])
        self._accent_widget(notice, T.slider_kwargs)
        ctk.CTkLabel(sl, textvariable=self._notice_lbl, width=60,
                     font=T.font("body_bold"), text_color=T.INK,
                     anchor="e").grid(row=2, column=2, sticky="e")
        self._hint(sl, "How far past a typo you get before spotting it. "
                       "Catching every one instantly is the clearest sign a "
                       "machine is typing.", wrap=620,
                   row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

        self._effort_var    = tk.BooleanVar(value=True)
        self._warmup_var    = tk.BooleanVar(value=True)
        self._fatigue_var   = tk.BooleanVar(value=False)
        self._burst_var     = tk.BooleanVar(value=True)
        self._burst_mode    = tk.BooleanVar(value=False)
        self._idle_var      = tk.BooleanVar(value=False)
        self._common_typos  = tk.BooleanVar(value=False)
        self._cap_slip_var  = tk.BooleanVar(value=False)
        self._transpose_var = tk.BooleanVar(value=False)
        self._double_var    = tk.BooleanVar(value=False)
        self._think_var     = tk.BooleanVar(value=False)

        groups = [
            ("Rhythm", [
                ("Per-key effort", self._effort_var,
                 "Pinky reaches and same-finger runs take longer"),
                ("Warm-up", self._warmup_var,
                 "The first few lines come out a little cold"),
                ("Fatigue", self._fatigue_var,
                 "Gradually slow down through a long document"),
                ("Word-burst variation", self._burst_var,
                 "Micro-pauses at word boundaries"),
            ]),
            ("Pauses", [
                ("Rest between bursts", self._burst_mode,
                 "A few words quickly, then a breath"),
                ("Idle thinking", self._idle_var,
                 "Occasional stops of one to three seconds"),
                ("Sentence thinking", self._think_var,
                 "A beat before a new sentence or a long word"),
            ]),
            ("Mistakes", [
                ("Transposed letters", self._transpose_var,
                 "hte for the — the commonest real slip"),
                ("Double-letter slips", self._double_var,
                 "stil for still, writting for writing"),
                ("Common misspellings", self._common_typos,
                 "teh, recieve, definately"),
                ("Capitalisation slips", self._cap_slip_var,
                 "A missed shift, caught a moment later"),
            ]),
        ]
        cols = ctk.CTkFrame(b, fg_color="transparent")
        cols.grid(row=3, column=0, sticky="ew")
        cols.grid_columnconfigure((0, 1, 2), weight=1, uniform="beh")
        for c, (heading, items) in enumerate(groups):
            col = ctk.CTkFrame(cols, fg_color="transparent")
            col.grid(row=0, column=c, sticky="new",
                     padx=(0 if c == 0 else T.SPACE["lg"], 0))
            ctk.CTkLabel(col, text=heading.upper(), font=T.font("eyebrow"),
                         text_color=T.INK_3, anchor="w").pack(
                anchor="w", pady=(0, T.SPACE["sm"]))
            for label, var, desc in items:
                sw = ctk.CTkSwitch(col, text=label, variable=var, width=40,
                                   onvalue=True, offvalue=False,
                                   **T.switch_kwargs())
                sw.pack(anchor="w", pady=(0, 1))
                self._accent_widget(sw, T.switch_kwargs)
                ctk.CTkLabel(col, text=desc, font=T.font("micro"),
                             text_color=T.INK_3, anchor="w", justify="left",
                             wraplength=230).pack(anchor="w", padx=(48, 0),
                                                  pady=(0, T.SPACE["sm"]))

        # ---- Timing and Output side by side --------------------------------
        pair = ctk.CTkFrame(page, fg_color="transparent")
        pair.grid(row=2, column=0, sticky="ew", pady=(0, T.SPACE["xl"]))
        pair.grid_columnconfigure((0, 1), weight=1, uniform="pair")

        timing = self._card(pair, "Timing",
                            "Fine control over the numbers the presets set.",
                            row=0, column=0, sticky="nsew",
                            padx=(0, T.SPACE["sm"]))
        b = timing.body
        b.grid_columnconfigure(1, weight=1)
        self._vars = {}
        fields = [
            ("Start delay",       "start_delay", "5",    "seconds to switch windows"),
            ("Base delay",        "base_delay",  "0.08", "average per character"),
            ("Variation",         "variation",   "0.03", "± jitter per keystroke"),
            ("Punctuation pause", "punct_pause", "0.25", "after . ! ?"),
            ("Paragraph pause",   "para_pause",  "0.8",  "on a blank line"),
            ("Typo chance",       "typo_chance", "0.04", "0 to 1, adjacent key"),
        ]
        for i, (label, name, default, hint) in enumerate(fields):
            self._field_label(b, label, row=i * 2, column=0, sticky="w", pady=(0, 0))
            var = tk.StringVar(value=default)
            self._vars[name] = var
            ctk.CTkEntry(b, textvariable=var, width=96, justify="right",
                         **T.entry_kwargs()).grid(
                row=i * 2, column=1, sticky="e", pady=3)
            self._hint(b, hint, wrap=260, row=i * 2 + 1, column=0, columnspan=2,
                       sticky="w", pady=(0, T.SPACE["sm"]))
            var.trace_add("write", lambda *_: self._update_count())

        ctk.CTkFrame(b, height=T.HAIRLINE, fg_color=T.BORDER).grid(
            row=90, column=0, columnspan=2, sticky="ew", pady=T.SPACE["sm"])
        rrow = ctk.CTkFrame(b, fg_color="transparent")
        rrow.grid(row=91, column=0, columnspan=2, sticky="ew")
        self._field_label(rrow, "Repeat").pack(side="left", padx=(0, 8))
        self._repeat_count_var = tk.StringVar(value="1")
        ctk.CTkEntry(rrow, textvariable=self._repeat_count_var, width=54,
                     justify="right", **T.entry_kwargs()).pack(side="left")
        ctk.CTkLabel(rrow, text="times, joined by", font=T.font("small"),
                     text_color=T.INK_2).pack(side="left", padx=8)
        self._repeat_sep_var = tk.StringVar(value="\\n\\n")
        ctk.CTkEntry(rrow, textvariable=self._repeat_sep_var, width=76,
                     **T.entry_kwargs()).pack(side="left")
        self._hint(b, "Use \\n for a newline and \\t for a tab.", wrap=300,
                   row=92, column=0, columnspan=2, sticky="w", pady=(6, 0))

        output = self._card(pair, "Output",
                            "What actually reaches the other window.",
                            row=0, column=1, sticky="nsew",
                            padx=(T.SPACE["sm"], 0))
        b = output.body
        self._field_label(b, "Newlines", row=0, column=0, sticky="w")
        self._newline_var = tk.StringVar(value="Press Enter")
        nl = ctk.CTkOptionMenu(b, values=list(NEWLINE_MODES.keys()),
                               variable=self._newline_var, width=170,
                               command=lambda *_: self._update_newline_help(),
                               **T.option_menu_kwargs())
        nl.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._accent_widget(nl, T.option_menu_kwargs)
        self._newline_help = tk.StringVar(value=NEWLINE_HELP["enter"])
        ctk.CTkLabel(b, textvariable=self._newline_help, font=T.font("micro"),
                     text_color=T.INK_3, anchor="w", justify="left",
                     wraplength=300).grid(row=2, column=0, sticky="w",
                                          pady=(6, T.SPACE["lg"]))

        self._vars_expand = tk.BooleanVar(value=True)
        self._overlay_var = tk.BooleanVar(value=False)
        for i, (label, var, desc) in enumerate([
            ("Expand {variables}", self._vars_expand,
             "Substitute {date}, {time}, {clipboard} and {random:N} when typing starts."),
            ("Floating progress window", self._overlay_var,
             "A small always-on-top panel so you can watch progress from the target app."),
        ]):
            sw = ctk.CTkSwitch(b, text=label, variable=var, width=40,
                               onvalue=True, offvalue=False, **T.switch_kwargs())
            sw.grid(row=3 + i * 2, column=0, sticky="w")
            self._accent_widget(sw, T.switch_kwargs)
            self._hint(b, desc, wrap=300, row=4 + i * 2, column=0, sticky="w",
                       pady=(4, T.SPACE["md"]))

    # =======================================================================
    # Library
    # =======================================================================
    def _build_library_page(self):
        page = self._page("Library")
        page.grid_columnconfigure(0, minsize=300, weight=0)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(page, **T.card_kwargs())
        left.grid(row=0, column=0, sticky="nsew", padx=(0, T.SPACE["md"]))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(left, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.SPACE["lg"],
                  pady=(T.SPACE["lg"], T.SPACE["md"]))
        ctk.CTkLabel(head, text="Snippets", font=T.font("card_title"),
                     text_color=T.INK, anchor="w").pack(anchor="w")
        ctk.CTkLabel(head, text="Passages you reach for often.",
                     font=T.font("small"), text_color=T.INK_3,
                     anchor="w").pack(anchor="w", pady=(2, 0))

        self._snip_list_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent",
            scrollbar_button_color=T.BORDER_STRONG,
            scrollbar_button_hover_color=T.INK_3)
        self._snip_list_frame.grid(row=1, column=0, sticky="nsew",
                                   padx=T.SPACE["md"])
        self._snip_list_frame.grid_columnconfigure(0, weight=1)
        self._snip_buttons = {}
        self._snip_selected = None

        btnrow = ctk.CTkFrame(left, fg_color="transparent")
        btnrow.grid(row=2, column=0, sticky="ew", padx=T.SPACE["lg"],
                    pady=T.SPACE["lg"])
        btnrow.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(btnrow, text="New snippet", command=self._new_snippet,
                      **T.secondary_button_kwargs()).grid(
            row=0, column=0, sticky="ew")
        ctk.CTkButton(btnrow, text="Delete", width=76,
                      command=self._delete_snippet,
                      **T.quiet_button_kwargs()).grid(row=0, column=1, padx=(6, 0))

        right = ctk.CTkFrame(page, **T.card_kwargs())
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.SPACE["lg"],
                  pady=(T.SPACE["lg"], T.SPACE["md"]))
        self._snip_title_var = tk.StringVar(value="Nothing selected")
        ctk.CTkLabel(head, textvariable=self._snip_title_var,
                     font=T.font("card_title"), text_color=T.INK,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(head, text="Edit here, then save or insert.",
                     font=T.font("small"), text_color=T.INK_3,
                     anchor="w").pack(anchor="w", pady=(2, 0))

        self._snip_preview = ctk.CTkTextbox(
            right, wrap="word", font=T.font("mono"),
            fg_color=T.SURFACE_ALT, text_color=T.INK,
            border_width=T.HAIRLINE, border_color=T.BORDER,
            corner_radius=T.RADIUS_CONTROL,
            scrollbar_button_color=T.BORDER_STRONG,
            scrollbar_button_hover_color=T.INK_3)
        self._snip_preview.grid(row=1, column=0, sticky="nsew",
                                padx=T.SPACE["lg"])

        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=T.SPACE["lg"],
                     pady=T.SPACE["lg"])
        insert = ctk.CTkButton(actions, text="Insert into editor", width=160,
                               command=self._insert_snippet,
                               **T.primary_button_kwargs())
        insert.pack(side="left")
        self._accent_widget(insert, T.primary_button_kwargs)
        ctk.CTkButton(actions, text="Save changes", width=130,
                      command=self._save_snippet_changes,
                      **T.secondary_button_kwargs()).pack(side="left", padx=(8, 0))

        self._refresh_snippet_list()

    # =======================================================================
    # Insights
    # =======================================================================
    def _build_insights_page(self):
        page = self._page("Insights", scroll=True)

        life = self._card(page, "Lifetime",
                          "Everything this app has typed for you.",
                          row=0, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        g = life.body
        g.grid_columnconfigure((0, 1, 2), weight=1, uniform="life")
        self._life_chars = self._metric(g, "Characters", "0", 0, 0)
        self._life_sess  = self._metric(g, "Sessions", "0", 0, 1)
        self._life_time  = self._metric(g, "Time spent", "0s", 0, 2)
        self._life_best  = self._metric(g, "Best speed", "0", 1, 0)
        self._life_avg   = self._metric(g, "Average speed", "0", 1, 1)
        self._life_words = self._metric(g, "Words", "0", 1, 2)
        self._life_keys  = self._metric(g, "Keystrokes", "0", 2, 0, big=False)
        self._life_fixes = self._metric(g, "Corrections", "0", 2, 1, big=False)
        self._life_acc   = self._metric(g, "Accuracy", "—", 2, 2, big=False)

        sess = self._card(page, "This session",
                          "Since the app was opened.",
                          row=1, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        g = sess.body
        g.grid_columnconfigure((0, 1, 2), weight=1, uniform="sess")
        self._sess_chars = self._metric(g, "Characters", "0", 0, 0, big=False)
        self._sess_time  = self._metric(g, "Time spent", "0s", 0, 1, big=False)
        self._sess_wpm   = self._metric(g, "Last speed", "0", 0, 2, big=False)
        self._session_chars = 0
        self._session_seconds = 0.0
        self._session_last_wpm = 0.0

        hist = self._card(page, "Recent runs", None,
                          row=2, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        self._history_frame = ctk.CTkScrollableFrame(
            hist.body, height=220, fg_color="transparent",
            scrollbar_button_color=T.BORDER_STRONG,
            scrollbar_button_hover_color=T.INK_3)
        self._history_frame.grid(row=0, column=0, sticky="ew")
        self._history_frame.grid_columnconfigure(0, weight=1)

        btnrow = ctk.CTkFrame(hist.body, fg_color="transparent")
        btnrow.grid(row=1, column=0, sticky="ew", pady=(T.SPACE["md"], 0))
        ctk.CTkButton(btnrow, text="Clear history", command=self._clear_history,
                      **T.quiet_button_kwargs()).pack(side="left")
        ctk.CTkButton(btnrow, text="Reset lifetime totals",
                      command=self._reset_lifetime_stats,
                      **T.quiet_button_kwargs()).pack(side="left", padx=(6, 0))

        self._refresh_stat_cards()
        self._refresh_history()

    # =======================================================================
    # About
    # =======================================================================
    def _build_about_page(self):
        page = self._page("About", scroll=True)

        intro = self._card(page, f"Human Typer {__version__}", None,
                           row=0, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        b = intro.body
        ctk.CTkLabel(
            b, font=T.font("body"), text_color=T.INK_2, justify="left",
            wraplength=780, anchor="w",
            text="Types text into any other window at a human pace — drifting "
                 "rhythm, per-key effort, and mistakes noticed a beat late "
                 "rather than instantly.",
        ).grid(row=0, column=0, sticky="w")

        guarantee = ctk.CTkFrame(b, fg_color=T.accent("accent_soft"),
                                 corner_radius=T.RADIUS_CONTROL)
        guarantee.grid(row=1, column=0, sticky="ew", pady=(T.SPACE["md"], 0))
        self._accent_widget(guarantee,
                            lambda: {"fg_color": T.accent("accent_soft")})
        ctk.CTkLabel(
            guarantee, font=T.font("body"), text_color=T.INK, justify="left",
            wraplength=740, anchor="w",
            text="Every simulated mistake is corrected before the run ends. "
                 "The text that lands in the other window is byte-identical "
                 "to the text you gave it — the realism is in the timing and "
                 "the keystrokes, never in the finished document.",
        ).pack(anchor="w", padx=T.SPACE["lg"], pady=T.SPACE["md"])

        for i, line in enumerate([
            "F5 starts typing · F6 pauses and resumes · Esc stops.",
            "Move the mouse to the top-left corner of the screen to abort at "
            "any moment.",
            "On macOS, grant Accessibility permission to whatever launches "
            "this app, or no keystrokes will be sent.",
            f"Draft, settings, snippets and history are kept in {CONFIG_PATH}.",
        ]):
            ctk.CTkLabel(b, text="—   " + line, font=T.font("small"),
                         text_color=T.INK_3, justify="left", wraplength=780,
                         anchor="w").grid(row=2 + i, column=0, sticky="w",
                                          pady=(T.SPACE["sm"] if i == 0 else 2, 0))

        docs = self._card(
            page, "Documents you can open",
            "Only the words come across. Bold, headings, tables, images and "
            "fonts have no keystroke equivalent, so they are left behind.",
            row=1, column=0, sticky="ew", pady=(0, T.SPACE["md"]))
        b = docs.body
        b.grid_columnconfigure(1, weight=1)
        for i, (exts, desc) in enumerate(docimport.describe_support()):
            ctk.CTkLabel(b, text=exts, font=T.font("mono_sm"),
                         text_color=T.INK, anchor="w", width=180).grid(
                row=i, column=0, sticky="w", pady=3)
            ctk.CTkLabel(b, text=desc, font=T.font("small"),
                         text_color=T.INK_2, anchor="w").grid(
                row=i, column=1, sticky="w", pady=3)

        colophon = self._card(
            page, "Colophon", None,
            row=3, column=0, sticky="ew", pady=(0, T.SPACE["xl"]))
        b = colophon.body
        ctk.CTkLabel(
            b, font=T.font("small"), text_color=T.INK_2, justify="left",
            wraplength=780, anchor="w",
            text="Set in %s for titles and figures, %s for controls, and %s "
                 "for your text. Warm paper and deep brass in the light "
                 "theme; true black in the dark one, with neutral greys so "
                 "nothing reads as navy.\n\n"
                 "The bars under THIS RUN are not decoration. Each one is the "
                 "gap between two keystrokes on a logarithmic scale — the "
                 "engine's own rhythm while it is idle, and the gaps actually "
                 "being executed while it types. Watch the tall ones: that is "
                 "the moment it notices a typo and stops to fix it."
                 % (T.SERIF, T.SANS, T.MONO),
        ).grid(row=0, column=0, sticky="w")

        vars_card = self._card(
            page, "Variables",
            "Drop these into your text; they are replaced the moment typing "
            "starts.", row=4, column=0, sticky="ew", pady=(0, T.SPACE["xl"]))
        b = vars_card.body
        b.grid_columnconfigure(1, weight=1)
        for i, (token, desc) in enumerate(VARIABLES):
            ctk.CTkLabel(b, text=token, font=T.font("mono_sm"),
                         text_color=T.INK, anchor="w", width=180).grid(
                row=i, column=0, sticky="w", pady=3)
            ctk.CTkLabel(b, text=desc, font=T.font("small"),
                         text_color=T.INK_2, anchor="w").grid(
                row=i, column=1, sticky="w", pady=3)

    # =======================================================================
    # Action bar
    # =======================================================================
    def _build_action_bar(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color=T.SURFACE, corner_radius=0)
        wrap.grid(row=2, column=0, sticky="ew")
        wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(wrap, height=T.HAIRLINE, fg_color=T.BORDER,
                     corner_radius=0).grid(row=0, column=0, sticky="ew")

        self._prog = ctk.CTkProgressBar(
            wrap, height=3, corner_radius=0, fg_color=T.SURFACE_SUNK,
            progress_color=T.accent("accent"))
        self._prog.set(0)
        self._prog.grid(row=1, column=0, sticky="ew")
        self._accent_widget(self._prog,
                            lambda: {"progress_color": T.accent("accent")})

        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew",
                 padx=T.SPACE["xl"], pady=T.SPACE["md"])
        bar.grid_columnconfigure(4, weight=1)

        self._start_btn = ctk.CTkButton(
            bar, text="Start typing", width=150, command=self.start_typing,
            **{**T.primary_button_kwargs(), "font": T.font("body_bold"),
               "height": T.HEIGHT_BUTTON_LG})
        self._start_btn.grid(row=0, column=0, sticky="w")
        self._accent_widget(
            self._start_btn,
            lambda: {**T.primary_button_kwargs(), "font": T.font("body_bold"),
                     "height": T.HEIGHT_BUTTON_LG})

        self._pause_btn = ctk.CTkButton(
            bar, text="Pause", width=92, state="disabled",
            command=self.toggle_pause,
            **{**T.secondary_button_kwargs(), "height": T.HEIGHT_BUTTON_LG})
        self._pause_btn.grid(row=0, column=1, padx=(T.SPACE["sm"], 0))

        ctk.CTkButton(bar, text="Stop", width=82, command=self.stop_typing,
                      **{**T.secondary_button_kwargs(),
                         "height": T.HEIGHT_BUTTON_LG}).grid(
            row=0, column=2, padx=(6, 0))

        self._schedule_btn = ctk.CTkButton(
            bar, text="Schedule…", width=104, command=self._schedule_start,
            **{**T.secondary_button_kwargs(), "height": T.HEIGHT_BUTTON_LG})
        self._schedule_btn.grid(row=0, column=3, padx=(6, 0))

        readout = ctk.CTkFrame(bar, fg_color="transparent")
        readout.grid(row=0, column=5, sticky="e")
        self._eta_var = tk.StringVar(value="")
        ctk.CTkLabel(readout, textvariable=self._eta_var, font=T.font("small"),
                     text_color=T.INK_3).pack(side="left", padx=(0, T.SPACE["lg"]))
        self._wpm_var = tk.StringVar(value="")
        ctk.CTkLabel(readout, textvariable=self._wpm_var,
                     font=T.font("metric_sm"), text_color=T.INK).pack(side="left")

        status = ctk.CTkFrame(wrap, fg_color="transparent")
        status.grid(row=3, column=0, sticky="ew",
                    padx=T.SPACE["xl"], pady=(0, T.SPACE["md"]))
        status.grid_columnconfigure(1, weight=1)
        self._status_dot = ctk.CTkLabel(status, text="●", font=T.font("micro"),
                                        text_color=T.OK, width=12)
        self._status_dot.grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(status, textvariable=self._status_var, anchor="w",
                     font=T.font("small"), text_color=T.INK_2).grid(
            row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(status, text="F5 start   ·   F6 pause   ·   Esc stop",
                     font=T.font("micro"), text_color=T.INK_3).grid(
            row=0, column=2, sticky="e")

        self._set_status("Ready.", "ok")

    # ----- Realism plumbing ------------------------------------------------
    def _update_newline_help(self):
        self._newline_help.set(
            NEWLINE_HELP.get(self._newline_mode_value(), ""))

    def _newline_mode_value(self):
        return NEWLINE_MODES.get(self._newline_var.get(), "enter")

    def _apply_realism_profile(self, name):
        """Point every realism control at the named profile."""
        self._profile_var.set(name)
        self._profile_blurb.set(rz.PROFILE_BLURBS.get(name, ""))
        s = rz.profile(name)
        self._effort_var.set(s.effort_model)
        self._warmup_var.set(s.warmup)
        self._fatigue_var.set(s.fatigue)
        self._burst_var.set(s.word_burst)
        self._burst_mode.set(s.burst_mode)
        self._idle_var.set(s.idle_pauses)
        self._think_var.set(bool(s.think_before_sentence or s.hesitate_chance))
        self._common_typos.set(bool(s.common_typo_chance))
        self._cap_slip_var.set(bool(s.cap_slip_chance))
        self._transpose_var.set(bool(s.transpose_chance))
        self._double_var.set(bool(s.double_letter_chance))
        self._drift_var.set(s.rhythm_drift)
        self._drift_lbl.set(f"{s.rhythm_drift:.2f}")
        self._notice_var.set(s.notice_max)
        self._notice_lbl.set(f"{s.notice_max} chars")
        if "typo_chance" in self._vars:
            self._vars["typo_chance"].set(f"{s.typo_chance:g}")
        self._update_count()

    def _current_style(self):
        """Build a realism.TypingStyle from everything on screen.

        The profile supplies the magnitude of each behaviour; the switches
        decide whether it happens at all; the timing fields always win.
        Raises ValueError if a timing field is not a number.
        """
        cfg = {k: float(v.get()) for k, v in self._vars.items()}
        s = rz.profile(self._profile_var.get())

        s.base_delay  = cfg["base_delay"]
        s.variation   = cfg["variation"]
        s.punct_pause = cfg["punct_pause"]
        s.para_pause  = cfg["para_pause"]
        s.typo_chance = cfg["typo_chance"]

        s.effort_model = self._effort_var.get()
        s.warmup       = self._warmup_var.get()
        s.fatigue      = self._fatigue_var.get()
        s.word_burst   = self._burst_var.get()
        s.burst_mode   = self._burst_mode.get()
        s.idle_pauses  = self._idle_var.get()
        s.rhythm_drift = float(self._drift_var.get())
        s.notice_max   = int(self._notice_var.get())

        if not self._think_var.get():
            s.think_before_sentence = 0.0
            s.hesitate_chance = 0.0
        if not self._common_typos.get():
            s.common_typo_chance = 0.0
        if not self._cap_slip_var.get():
            s.cap_slip_chance = 0.0
        if not self._transpose_var.get():
            s.transpose_chance = 0.0
        if not self._double_var.get():
            s.double_letter_chance = 0.0

        s.press_enter = self._newline_mode_value() != "skip"
        return s.clamped()

    # =======================================================================
    # State persistence / restore
    # =======================================================================
    def _restore_state(self):
        # Restore last-used timing settings
        for k, v in self.config.get("last_settings", {}).items():
            if k in self._vars:
                self._vars[k].set(v)
        # Restore toggles
        # Start from the saved realism profile, then let any individually
        # saved switch override it.
        prof = self.config.get("realism_profile", DEFAULT_REALISM)
        if prof not in rz.PROFILES:
            prof = DEFAULT_REALISM
        self._profile_seg.set(prof)
        self._apply_realism_profile(prof)

        toggles = self.config.get("toggles", {})
        self._burst_var.set(toggles.get("word_burst", self._burst_var.get()))
        self._fatigue_var.set(toggles.get("fatigue", self._fatigue_var.get()))
        self._common_typos.set(toggles.get("common_typos", self._common_typos.get()))
        self._cap_slip_var.set(toggles.get("cap_slips", self._cap_slip_var.get()))
        self._burst_mode.set(toggles.get("burst_mode", self._burst_mode.get()))
        self._idle_var.set(toggles.get("idle_pauses", self._idle_var.get()))
        self._effort_var.set(toggles.get("effort_model", self._effort_var.get()))
        self._warmup_var.set(toggles.get("warmup", self._warmup_var.get()))
        self._think_var.set(toggles.get("sentence_thinking", self._think_var.get()))
        self._transpose_var.set(toggles.get("transpose", self._transpose_var.get()))
        self._double_var.set(toggles.get("double_letters", self._double_var.get()))
        self._vars_expand.set(toggles.get("expand_vars", True))
        self._overlay_var.set(toggles.get("show_overlay", False))

        self._drift_var.set(self.config.get("rhythm_drift", self._drift_var.get()))
        self._drift_lbl.set(f"{float(self._drift_var.get()):.2f}")
        self._notice_var.set(int(self.config.get("notice_max", self._notice_var.get())))
        self._notice_lbl.set(f"{int(self._notice_var.get())} chars")

        # "newlines_enter" was a boolean before newline modes existed.
        mode = self.config.get("newline_mode")
        if mode not in NEWLINE_MODES:
            mode = "Press Enter" if toggles.get("newlines_enter", False) \
                else "Skip (join)"
        self._newline_var.set(mode)
        self._update_newline_help()
        # Restore repeat
        rep = self.config.get("repeat", {})
        self._repeat_count_var.set(rep.get("count", "1"))
        self._repeat_sep_var.set(rep.get("separator", "\\n\\n"))
        # Restore draft
        draft = self.config.get("draft", "")
        if draft:
            self._tb.insert("1.0", draft)
        self._update_count()
        # Apply appearance
        self._apply_theme_colors(self._theme_name)
        self._mode_seg.set(self._appearance)

    def _persist_state(self):
        try:
            self.config["last_settings"] = {k: v.get() for k, v in self._vars.items()}
            self.config["toggles"] = {
                "newlines_enter": self._newline_mode_value() != "skip",
                "word_burst": self._burst_var.get(),
                "fatigue": self._fatigue_var.get(),
                "common_typos": self._common_typos.get(),
                "cap_slips": self._cap_slip_var.get(),
                "burst_mode": self._burst_mode.get(),
                "idle_pauses": self._idle_var.get(),
                "effort_model": self._effort_var.get(),
                "warmup": self._warmup_var.get(),
                "sentence_thinking": self._think_var.get(),
                "transpose": self._transpose_var.get(),
                "double_letters": self._double_var.get(),
                "expand_vars": self._vars_expand.get(),
                "show_overlay": self._overlay_var.get(),
            }
            self.config["realism_profile"] = self._profile_var.get()
            self.config["newline_mode"] = self._newline_var.get()
            self.config["rhythm_drift"] = float(self._drift_var.get())
            self.config["notice_max"] = int(self._notice_var.get())
            self.config["repeat"] = {
                "count": self._repeat_count_var.get(),
                "separator": self._repeat_sep_var.get(),
            }
            self.config["theme"] = self._theme_name
            self.config["appearance"] = self._appearance
            # Resolved value, so an older build reading this file still opens
            # in something close to what the user last saw.
            self.config["dark_mode"] = ctk.get_appearance_mode().lower() == "dark"
            self.config["draft"] = self._tb.get("1.0", tk.END).rstrip("\n")
            save_config(self.config)
        except Exception:
            pass

    def _on_close(self):
        self._persist_state()
        self.destroy()

    # =======================================================================
    # Hotkeys
    # =======================================================================
    def _bind_hotkeys(self):
        self.bind_all("<F5>", lambda e: self.start_typing())
        self.bind_all("<F6>", lambda e: self.toggle_pause())
        self.bind_all("<Escape>", lambda e: self.stop_typing())

    # =======================================================================
    # Theme
    # =======================================================================
    def _on_theme_change(self, name):
        self._theme_name = resolve_theme(name)
        T.set_accent(self._theme_name)
        self._apply_theme_colors(self._theme_name)
        self._persist_state()

    def _apply_theme_colors(self, name):
        """Re-skin every widget whose colour comes from the accent.

        Each of those widgets registered a recipe when it was built, so this
        never has to know what any individual control is.
        """
        T.set_accent(resolve_theme(name))
        for widget, recipe in getattr(self, "_accented", []):
            try:
                widget.configure(**recipe())
            except Exception:
                pass
        if hasattr(self, "_current_page"):
            self._show_page(self._current_page)
        self._cadence_draw()

    def _on_mode_change(self, choice):
        self._appearance = resolve_appearance(choice)
        ctk.set_appearance_mode(APPEARANCE_MODES[self._appearance])
        # The cadence meter is a Tk canvas, so it holds flat colours and has
        # to be repainted rather than re-themed.
        self.after(60, self._cadence_draw)
        self._persist_state()

    # =======================================================================
    # Presets
    # =======================================================================
    def _apply_preset(self, name):
        p = PRESETS[name]
        self._vars["base_delay"].set(str(p["base_delay"]))
        self._vars["variation"].set(str(p["variation"]))
        self._vars["punct_pause"].set(str(p["punct_pause"]))
        self._vars["typo_chance"].set(str(p["typo_chance"]))
        self._vars["para_pause"].set(str(p["para_pause"]))
        self._set_status(f"Preset applied: {name}", "ok")

    def _custom_preset_values(self):
        items = list(self.config.get("custom_presets", {}).keys())
        return items if items else ["— none —"]

    def _save_custom_preset(self):
        name = self._ask_text("Save preset", "Name for this custom preset:")
        if not name:
            return
        try:
            data = {k: float(v.get()) for k, v in self._vars.items()}
        except ValueError:
            messagebox.showerror("Invalid", "Settings must be numeric.")
            return
        self.config.setdefault("custom_presets", {})[name] = data
        self._custom_preset_menu.configure(values=self._custom_preset_values())
        self._custom_preset_menu.set(name)
        self._persist_state()
        self._set_status(f"Saved custom preset: {name}", "ok")

    def _apply_custom_preset(self, name):
        if name == "— none —":
            return
        data = self.config.get("custom_presets", {}).get(name)
        if not data:
            return
        for k, v in data.items():
            if k in self._vars:
                self._vars[k].set(str(v))
        self._set_status(f"Custom preset applied: {name}", "ok")

    def _delete_custom_preset(self):
        name = self._custom_preset_menu.get()
        if name in ("", "— none —"):
            return
        if not messagebox.askyesno("Delete Preset", f"Delete preset '{name}'?"):
            return
        self.config.get("custom_presets", {}).pop(name, None)
        vals = self._custom_preset_values()
        self._custom_preset_menu.configure(values=vals)
        self._custom_preset_menu.set(vals[0])
        self._persist_state()

    # =======================================================================
    # Text helpers
    # =======================================================================
    def load_file(self):
        path = filedialog.askopenfilename(
            title="Open a document",
            filetypes=docimport.FILE_TYPES,
        )
        if not path:
            return
        self._load_path(path)

    def _load_path(self, path):
        """Load a document into the editor.

        Word, OpenDocument, RTF, HTML and PDF files are read for their text.
        Formatting is not carried across — a keyboard types characters, so
        bold, headings, tables and images have no equivalent to send.
        """
        name = Path(path).name
        try:
            text = docimport.extract(path)
        except (docimport.UnsupportedDocument,
                docimport.DocumentTooLarge) as exc:
            messagebox.showerror("Cannot open %s" % name, str(exc))
            return
        except FileNotFoundError:
            messagebox.showerror("Cannot open %s" % name,
                                 "That file is no longer where it was.")
            return
        except Exception as exc:
            messagebox.showerror("Cannot open %s" % name,
                                 "Could not read the file:\n\n%s" % exc)
            return

        if not text.strip():
            messagebox.showwarning(
                "Nothing to type",
                "%s opened, but there is no text in it to type." % name)
            return

        self._tb.delete("1.0", tk.END)
        self._tb.insert("1.0", text)
        self._update_count()
        self._push_recent(path)

        ext = Path(path).suffix.lower()
        if ext in docimport.RICH_EXTENSIONS:
            self._set_status(
                "Loaded %s — %s chars of text (formatting is not carried over)."
                % (name, format(len(text), ",")), "ok")
        else:
            self._set_status("Loaded %s — %s chars."
                             % (name, format(len(text), ",")), "ok")

    def _push_recent(self, path):
        recents = [p for p in self.config.get("recent_files", []) if p != path]
        recents.insert(0, path)
        self.config["recent_files"] = recents[:8]
        self._persist_state()

    def _open_recent_menu(self):
        recents = self.config.get("recent_files", [])
        if not recents:
            messagebox.showinfo("Recent files", "No recent files yet.")
            return
        menu = self._menu()
        for path in recents:
            menu.add_command(label=Path(path).name,
                             command=lambda p=path: self._load_path(p))
        menu.add_separator()
        menu.add_command(label="Clear list",
                         command=self._clear_recent)
        self._popup(menu)

    def _clear_recent(self):
        self.config["recent_files"] = []
        self._persist_state()

    def import_clipboard(self):
        try:
            text = pyperclip.paste()
            if not text:
                messagebox.showwarning("Clipboard Empty",
                                       "Clipboard does not contain text.")
                return
            self._tb.delete("1.0", tk.END)
            self._tb.insert("1.0", text)
            self._update_count()
            self._set_status("Imported from clipboard.", "ok")
        except Exception as exc:
            messagebox.showerror("Clipboard Error",
                                 f"Could not read clipboard:\n{exc}")

    def clear_text(self):
        if self._tb.get("1.0", tk.END).strip() and \
           not messagebox.askyesno("Clear", "Clear the editor?"):
            return
        self._tb.delete("1.0", tk.END)
        self._update_count()
        self._set_status("Text cleared.", "ok")

    def _export_text(self):
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        if not text:
            messagebox.showwarning("Nothing to export", "Editor is empty.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Markdown", "*.md"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self._set_status(f"Exported to {Path(path).name}", "ok")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _on_modified(self, _event=None):
        try:
            self._tb._textbox.edit_modified(False)
        except Exception:
            pass
        self._update_count()

    def _update_count(self, _event=None):
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        chars = len(text)
        words = len(text.split()) if text.strip() else 0

        # Detailed stats
        if "chars" in getattr(self, "_stat_rows", {}):
            self._stat_rows["chars"].set(f"{chars:,}")
            self._stat_rows["words"].set(f"{words:,}")
            sentences = max(1, len(re.findall(r"[.!?]+", text))) if text.strip() else 0
            paragraphs = len([p for p in text.split("\n\n") if p.strip()])
            avg_word = (sum(len(w) for w in text.split()) / words) if words else 0
            reading_secs = words / (250 / 60) if words else 0   # 250 wpm reading
            est_secs = self._estimate_type_seconds(text)
            self._stat_rows["sentences"].set(f"{sentences:,}")
            self._stat_rows["paragraphs"].set(f"{paragraphs:,}")
            self._stat_rows["avg_word"].set(f"{avg_word:.1f}" if words else "—")
            self._stat_rows["reading"].set(self._fmt_secs(reading_secs) if words else "—")
            self._stat_rows["estimate"].set(self._fmt_secs(est_secs) if chars else "—")
            if words:
                ease, grade = flesch_reading_ease(text)
                self._stat_rows["flesch"].set(f"{ease:.0f}")
                self._stat_rows["grade"].set(f"{max(0, grade):.1f}")
            else:
                self._stat_rows["flesch"].set("—")
                self._stat_rows["grade"].set("—")

    def _estimate_type_seconds(self, text):
        """Seconds this text will take, measured by planning it for real.

        The old estimate multiplied character count by the base delay, which
        ignored per-key effort, rhythm drift, rests and the time spent
        correcting mistakes — so it ran 20-40% short with realism on. This
        plans the text with the current style and adds up the actual pauses.
        Long texts are sampled and scaled rather than planned in full.
        """
        if not text:
            return 0.0
        try:
            start = float(self._vars["start_delay"].get())
        except (ValueError, KeyError):
            start = 0.0
        try:
            style = self._current_style()
        except Exception:
            return 0.0

        sample, scale = text, 1.0
        if len(text) > ESTIMATE_SAMPLE_CHARS:
            # Take the sample from the middle so it misses the warm-up ramp
            # and lands on representative prose.
            mid = len(text) // 2
            half = ESTIMATE_SAMPLE_CHARS // 2
            sample = text[max(0, mid - half):mid + half]
            scale = len(text) / len(sample)

        try:
            secs = rz.estimate_seconds(sample, style, samples=2) * scale
        except Exception:
            return 0.0
        return start + secs

    def _fmt_secs(self, s):
        s = int(s)
        if s < 60:
            return f"{s}s"
        m, sec = divmod(s, 60)
        if m < 60:
            return f"{m}m {sec:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}m"

    # =======================================================================
    # Find & Replace
    # =======================================================================
    def open_find_replace(self):
        if getattr(self, "_find_win", None) and self._find_win.winfo_exists():
            self._find_win.lift()
            self._find_win.focus_force()
            return
        w = self._dialog("Find & Replace")
        self._find_win = w
        w.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(w, **T.card_kwargs())
        card.grid(row=0, column=0, sticky="nsew",
                  padx=T.SPACE["lg"], pady=T.SPACE["lg"])
        card.grid_columnconfigure(1, weight=1)

        self._dialog_heading(card, "Find & replace",
                             "Searches the editor on the Compose page.").grid(
            row=0, column=0, columnspan=2, sticky="ew",
            padx=T.CARD_PAD, pady=(T.SPACE["lg"], T.SPACE["md"]))

        find_var = tk.StringVar()
        repl_var = tk.StringVar()
        case_var = tk.BooleanVar(value=False)

        for row, (label, var) in enumerate(
                (("Find", find_var), ("Replace with", repl_var)), start=1):
            ctk.CTkLabel(card, text=label, font=T.font("small"),
                         text_color=T.INK_2, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(T.CARD_PAD, T.SPACE["md"]),
                pady=5)
            entry = ctk.CTkEntry(card, textvariable=var, **T.entry_kwargs())
            entry.grid(row=row, column=1, sticky="ew",
                       padx=(0, T.CARD_PAD), pady=5)
            if row == 1:
                entry.focus_set()

        ctk.CTkCheckBox(card, text="Match case", variable=case_var,
                        **T.checkbox_kwargs()).grid(
            row=3, column=1, sticky="w", padx=(0, T.CARD_PAD),
            pady=(T.SPACE["sm"], 0))

        result_var = tk.StringVar(value="")
        ctk.CTkLabel(card, textvariable=result_var, font=T.font("small"),
                     text_color=T.INK_3, anchor="w").grid(
            row=4, column=0, columnspan=2, sticky="w",
            padx=T.CARD_PAD, pady=(T.SPACE["md"], 0))

        def do_find_all():
            box = self._tb._textbox
            box.tag_remove("find", "1.0", tk.END)
            needle = find_var.get()
            if not needle:
                result_var.set("Type something to find.")
                return
            opts = {"nocase": not case_var.get()}
            start, count = "1.0", 0
            while True:
                idx = box.search(needle, start, stopindex=tk.END, **opts)
                if not idx:
                    break
                end = "%s+%dc" % (idx, len(needle))
                box.tag_add("find", idx, end)
                start = end
                count += 1
            box.tag_config("find",
                           background=T.resolve(T.FIND_HIGHLIGHT),
                           foreground=T.resolve(T.FIND_HIGHLIGHT_INK))
            result_var.set("%s match%s highlighted."
                           % (format(count, ","), "" if count == 1 else "es")
                           if count else "No matches.")
            self._set_status("Found %s match(es)." % format(count, ","),
                             "ok" if count else "warn")

        def do_replace_all():
            text = self._tb.get("1.0", tk.END).rstrip("\n")
            needle = find_var.get()
            if not needle:
                result_var.set("Type something to find.")
                return
            if case_var.get():
                n = text.count(needle)
                new = text.replace(needle, repl_var.get())
            else:
                new, n = re.compile(re.escape(needle), re.IGNORECASE).subn(
                    repl_var.get(), text)
            if not n:
                result_var.set("Nothing to replace.")
                self._set_status("No matches to replace.", "warn")
                return
            self._tb.delete("1.0", tk.END)
            self._tb.insert("1.0", new)
            self._update_count()
            result_var.set("Replaced %s occurrence%s."
                           % (format(n, ","), "" if n == 1 else "s"))
            self._set_status("Replaced %s occurrence(s)." % format(n, ","), "ok")

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew",
                     padx=T.CARD_PAD, pady=(T.SPACE["lg"], T.SPACE["lg"]))
        buttons.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(buttons, text="Close", width=80, command=w.destroy,
                      **T.ghost_button_kwargs()).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(buttons, text="Find all", width=100,
                      command=do_find_all,
                      **T.secondary_button_kwargs()).grid(row=0, column=1,
                                                          padx=(0, T.SPACE["sm"]))
        replace_btn = ctk.CTkButton(buttons, text="Replace all", width=120,
                                    command=do_replace_all,
                                    **T.primary_button_kwargs())
        replace_btn.grid(row=0, column=2)
        self._accent_widget(replace_btn, T.primary_button_kwargs)

        w.bind("<Return>", lambda _e: do_find_all())
        w.bind("<Escape>", lambda _e: w.destroy())
        self._fit_dialog(w, min_width=480)
        w.lift()
        w.focus_force()

    # =======================================================================
    # Snippets
    # =======================================================================
    def _all_snippets(self):
        merged = dict(BUILTIN_SNIPPETS)
        merged.update(self.config.get("custom_snippets", {}))
        return merged

    def _refresh_snippet_list(self):
        for child in self._snip_list_frame.winfo_children():
            child.destroy()
        self._snip_buttons.clear()
        for i, name in enumerate(self._all_snippets().keys()):
            builtin = name in BUILTIN_SNIPPETS
            btn = ctk.CTkButton(
                self._snip_list_frame,
                text=name + ("   ·  built in" if builtin else ""),
                anchor="w", height=32, corner_radius=T.RADIUS_CONTROL,
                fg_color="transparent", hover_color=T.SURFACE_ALT,
                text_color=T.INK_2 if builtin else T.INK,
                font=T.font("body"), border_width=0,
                command=lambda n=name: self._select_snippet(n),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=1)
            self._snip_buttons[name] = btn

    def _select_snippet(self, name):
        self._snip_selected = name
        self._snip_title_var.set(name)
        self._snip_preview.delete("1.0", tk.END)
        self._snip_preview.insert("1.0", self._all_snippets().get(name, ""))
        for other, btn in self._snip_buttons.items():
            chosen = other == name
            try:
                btn.configure(
                    fg_color=T.accent("accent_soft") if chosen else "transparent",
                    text_color=T.INK if chosen else (
                        T.INK_2 if other in BUILTIN_SNIPPETS else T.INK),
                    font=T.font("body_bold" if chosen else "body"))
            except Exception:
                pass

    def _new_snippet(self):
        name = self._ask_text("New snippet", "Snippet name:")
        if not name:
            return
        if name in BUILTIN_SNIPPETS:
            messagebox.showwarning("Conflict", "Name conflicts with a built-in.")
            return
        self.config.setdefault("custom_snippets", {})[name] = ""
        self._persist_state()
        self._refresh_snippet_list()
        self._select_snippet(name)

    def _delete_snippet(self):
        name = self._snip_selected
        if not name:
            return
        if name in BUILTIN_SNIPPETS:
            messagebox.showwarning("Built-in", "Cannot delete a built-in snippet.")
            return
        if not messagebox.askyesno("Delete", f"Delete snippet '{name}'?"):
            return
        self.config.get("custom_snippets", {}).pop(name, None)
        self._snip_selected = None
        self._snip_title_var.set("No snippet selected")
        self._snip_preview.delete("1.0", tk.END)
        self._persist_state()
        self._refresh_snippet_list()

    def _save_snippet_changes(self):
        name = self._snip_selected
        if not name:
            return
        if name in BUILTIN_SNIPPETS:
            messagebox.showwarning("Built-in",
                                   "Built-in snippets cannot be edited. "
                                   "Save as new (➕  New) instead.")
            return
        self.config.setdefault("custom_snippets", {})[name] = \
            self._snip_preview.get("1.0", tk.END).rstrip("\n")
        self._persist_state()
        self._set_status(f"Saved snippet: {name}", "ok")

    def _insert_snippet(self):
        if not self._snip_selected:
            return
        text = self._snip_preview.get("1.0", tk.END).rstrip("\n")
        try:
            self._tb._textbox.insert(tk.INSERT, text)
        except Exception:
            self._tb.insert(tk.END, text)
        self._update_count()
        self._show_page("Compose")
        self._set_status(f"Inserted snippet: {self._snip_selected}", "ok")

    def _save_selection_as_snippet(self):
        try:
            text = self._tb._textbox.get("sel.first", "sel.last")
        except tk.TclError:
            text = self._tb.get("1.0", tk.END).rstrip("\n")
        if not text.strip():
            messagebox.showwarning("Empty",
                                   "Select text in the editor, or type something first.")
            return
        name = self._ask_text("Save as snippet", "Snippet name:")
        if not name:
            return
        if name in BUILTIN_SNIPPETS:
            messagebox.showwarning("Conflict", "Name conflicts with a built-in.")
            return
        self.config.setdefault("custom_snippets", {})[name] = text
        self._persist_state()
        self._refresh_snippet_list()
        self._set_status(f"Saved snippet: {name}", "ok")

    # =======================================================================
    # Stats cards
    # =======================================================================
    def _refresh_stat_cards(self):
        s = self.config.get("stats", {})
        chars = int(s.get("lifetime_chars", 0))
        secs = float(s.get("lifetime_seconds", 0.0))
        sess = int(s.get("lifetime_sessions", 0))
        self._life_chars.set(f"{chars:,}")
        self._life_sess.set(f"{sess:,}")
        self._life_time.set(self._fmt_secs(secs))
        self._life_best.set(f"{s.get('best_wpm', 0):.0f}")
        avg_wpm = ((chars / CHARS_PER_WORD) / (secs / 60)) if secs > 1 else 0
        self._life_avg.set(f"{avg_wpm:.0f}")
        self._life_words.set(f"{chars // CHARS_PER_WORD:,}")
        keys = int(s.get("lifetime_keystrokes", 0))
        fixes = int(s.get("lifetime_corrections", 0))
        self._life_keys.set(f"{keys:,}")
        self._life_fixes.set(f"{fixes:,}")
        struck = keys - fixes
        self._life_acc.set(
            f"{min(100.0, chars / struck * 100.0):.1f}%" if struck > 0 else "—")

        self._sess_chars.set(f"{self._session_chars:,}")
        self._sess_time.set(self._fmt_secs(self._session_seconds))
        self._sess_wpm.set(f"{self._session_last_wpm:.0f}")

    def _reset_lifetime_stats(self):
        if not messagebox.askyesno(
                "Reset", "Reset all lifetime statistics? This can't be undone."):
            return
        self.config["stats"] = {
            "lifetime_chars": 0,
            "lifetime_sessions": 0,
            "lifetime_seconds": 0.0,
            "best_wpm": 0.0,
        }
        self._persist_state()
        self._refresh_stat_cards()

    # =======================================================================
    # Typing control
    # =======================================================================
    def stop_typing(self):
        if not self._typing_active:
            return
        self._stop = True
        self._pause.set()
        self._set_status("Stopping…", "warn")

    def toggle_pause(self):
        if not self._typing_active:
            return
        if self._pause.is_set():
            self._pause.clear()
            self._pause_started = time.time()
            self._pause_btn.configure(text="▶  Resume  (F6)")
            self._set_status("Paused. Click Resume to continue.", "warn")
        else:
            # Time spent paused is not typing time, so it must not drag the
            # WPM down or inflate the ETA.
            if self._pause_started is not None:
                self._paused_total += time.time() - self._pause_started
                self._pause_started = None
            self._pause.set()
            self._pause_btn.configure(text="⏸  Pause  (F6)")
            self._set_status("Resumed.", "ok")

    def start_typing(self):
        if self._typing_active:
            return
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        if not text.strip():
            messagebox.showwarning("No Text", "Please load or paste text first.")
            return
        try:
            style = self._current_style()
            start_delay = float(self._vars["start_delay"].get())
        except ValueError:
            messagebox.showerror("Invalid Settings", "All settings must be numeric.")
            return

        # Variable expansion
        if self._vars_expand.get():
            text = expand_variables(text)

        # Repeat
        try:
            repeat_n = max(1, int(self._repeat_count_var.get() or "1"))
        except ValueError:
            repeat_n = 1
        if repeat_n > 1:
            sep = (self._repeat_sep_var.get() or "")\
                .replace("\\n", "\n").replace("\\t", "\t")
            text = sep.join([text] * repeat_n)

        # Plan the whole document up front where we can afford to. Knowing
        # every pause in advance is what makes the ETA exact instead of a
        # linear extrapolation from however fast the first line went.
        rng = random.Random()
        try:
            planned = list(rz.plan(text, style, rng)) \
                if len(text) <= MAX_PLANNED_CHARS else None
        except MemoryError:
            planned = None

        self._stop = False
        self._pause.set()
        self._prog.set(0)
        self._wpm_var.set("")
        self._eta_var.set("")
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal", text="⏸  Pause  (F6)")
        self._typing_active = True
        self._persist_state()

        if self._overlay_var.get():
            self._build_overlay()

        threading.Thread(
            target=self._run,
            args=(text, style, start_delay, planned, rng),
            daemon=True,
        ).start()

    # =======================================================================
    # Core typing loop (background thread)
    #
    # All the realism decisions were made by realism.plan(); this loop only
    # executes the resulting event stream and reports progress. Keeping the
    # two apart is what lets the engine be tested without a keyboard.
    # =======================================================================
    def _run(self, text, style, start_delay, planned, rng):
        try:
            # Countdown
            for remaining in range(int(start_delay), 0, -1):
                if self._stop:
                    self._done("Stopped.", "warn")
                    return
                self._set_status(
                    f"Starting in {remaining}s — switch to target window now…",
                    "warn")
                self._sleep(1.0)
            frac = start_delay - int(start_delay)
            if frac > 0:
                self._sleep(frac)
            if self._stop:
                self._done("Stopped.", "warn")
                return

            total = len(text)
            events = planned if planned is not None else rz.plan(text, style, rng)
            planned_total = (
                sum(ev.seconds for ev in planned if isinstance(ev, rz.Pause))
                if planned is not None else None)

            mode = self._newline_mode_value()
            self._paused_total = 0.0
            self._pause_started = None
            typed = 0          # source characters correctly in place
            keystrokes = 0     # every physical key press, corrections included
            corrections = 0    # backspaces
            spent = 0.0        # planned seconds consumed so far
            t0 = time.time()

            for ev in events:
                if self._stop:
                    self._record_session(typed, time.time() - t0,
                                         keystrokes, corrections)
                    self._done("Stopped.", "warn")
                    return
                self._pause.wait()

                if isinstance(ev, rz.Pause):
                    spent += ev.seconds
                    self._cadence_push(ev.seconds)
                    self._sleep(ev.seconds)
                    continue
                if isinstance(ev, rz.Note):
                    self._set_status(ev.text, "warn")
                    continue

                if isinstance(ev, rz.Char):
                    # A bare newline only reaches here in "skip" mode, where
                    # it is deliberately not sent — see NEWLINE_MODES.
                    if ev.ch != "\n":
                        self._emit(ev.ch)
                        keystrokes += 1
                elif isinstance(ev, rz.Key):
                    if ev.name == "enter":
                        if mode != "skip":
                            self._press_key("shift_enter" if mode == "shift_enter"
                                            else "enter")
                            keystrokes += 1
                    else:
                        self._press_key(ev.name)
                        keystrokes += 1
                        if ev.name == "backspace":
                            corrections += 1
                typed += ev.advance
                self._tick(typed, total, keystrokes, corrections, t0,
                           spent, planned_total)

            self._record_session(typed, time.time() - t0, keystrokes, corrections)
            self._done("Done typing ✓", "ok")

        except pyautogui.FailSafeException:
            self._done("Fail-safe triggered (mouse moved to corner).", "err")
        except Exception as exc:
            self._done(f"Error: {exc}", "err")

    def _sleep(self, seconds):
        """Sleep, but stay responsive to Stop.

        Idle pauses run to nearly three seconds; a plain time.sleep() there
        meant Stop and the fail-safe went unnoticed for that whole pause.
        """
        if seconds <= 0:
            return
        end = time.time() + seconds
        while not self._stop:
            left = end - time.time()
            if left <= 0:
                return
            time.sleep(min(0.05, left))

    def _record_session(self, chars, seconds, keystrokes=0, corrections=0):
        if seconds <= 0 or chars <= 0:
            return
        # Net WPM, the same measure typing tests report: correct characters
        # only, divided by elapsed time including whatever the corrections
        # cost. The old code returned 0 for anything under a second, which is
        # why short runs are logged as 0 WPM in the history.
        wpm = (chars / CHARS_PER_WORD) / (seconds / 60)
        struck = max(1, keystrokes - corrections)
        accuracy = min(100.0, chars / struck * 100.0)

        s = self.config.setdefault("stats", {})
        s["lifetime_chars"] = int(s.get("lifetime_chars", 0)) + chars
        s["lifetime_seconds"] = float(s.get("lifetime_seconds", 0.0)) + seconds
        s["lifetime_sessions"] = int(s.get("lifetime_sessions", 0)) + 1
        s["lifetime_keystrokes"] = int(s.get("lifetime_keystrokes", 0)) + keystrokes
        s["lifetime_corrections"] = int(s.get("lifetime_corrections", 0)) + corrections
        if wpm > float(s.get("best_wpm", 0)):
            s["best_wpm"] = wpm
        self._session_chars += chars
        self._session_seconds += seconds
        self._session_last_wpm = wpm

        # Append to recent-session history (keep last 20)
        hist = self.config.setdefault("session_history", [])
        hist.insert(0, {
            "when": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "chars": int(chars),
            "seconds": float(seconds),
            "wpm": float(wpm),
            "accuracy": float(accuracy),
            "corrections": int(corrections),
        })
        self.config["session_history"] = hist[:20]

        self._persist_state()
        self.after(0, self._refresh_stat_cards)
        self.after(0, self._refresh_history)

    def _press_key(self, key_name):
        if key_name == "shift_enter":
            # Soft line break: what chat apps want instead of a send.
            if _IS_MAC and _MAC_KBD is not None:
                with _MAC_KBD.pressed(_Key.shift):
                    _MAC_KBD.press(_Key.enter)
                    _MAC_KBD.release(_Key.enter)
                return
            pyautogui.hotkey("shift", "enter")
            return
        if _IS_MAC and _MAC_KBD is not None:
            key_map = {"enter": _Key.enter, "backspace": _Key.backspace}
            k = key_map.get(key_name)
            if k:
                _MAC_KBD.press(k)
                _MAC_KBD.release(k)
                return
        pyautogui.press(key_name)

    def _set_status(self, msg, kind="ok"):
        self.after(0, self._set_status_main, msg, kind)

    def _set_status_main(self, msg, kind):
        self._status_var.set(msg)
        color = {"ok": T.OK, "warn": T.WARN, "err": T.ERR}.get(kind, T.OK)
        try:
            self._status_dot.configure(text_color=color)
        except Exception:
            pass

    def _emit(self, ch):
        if _IS_MAC:
            if _MAC_KBD is not None:
                _MAC_KBD.type(ch)
            else:
                saved = pyperclip.paste()
                pyperclip.copy(ch)
                pyautogui.hotkey(*_PASTE_HOTKEY)
                time.sleep(0.05)
                pyperclip.copy(saved)
        elif ch.isascii() and ch.isprintable():
            pyautogui.write(ch, interval=_WRITE_INTERVAL)
        else:
            saved = pyperclip.paste()
            pyperclip.copy(ch)
            pyautogui.hotkey(*_PASTE_HOTKEY)
            time.sleep(0.05)
            pyperclip.copy(saved)

    def _tick(self, typed, total, keystrokes, corrections, t0,
              spent, planned_total):
        """Report progress.

        Two things make the numbers honest here. Elapsed time excludes any
        time spent paused, and the ETA counts the pauses still left in the
        plan rather than extrapolating from how the first line went — so it
        does not lurch when the run hits a thinking pause or a burst rest.
        """
        pct = typed / total * 100 if total else 0
        elapsed = max(0.0, time.time() - t0 - self._paused_total)

        wpm_str = eta_str = acc_str = ""
        if elapsed > 0.3 and typed > 0:
            wpm_str = f"{(typed / CHARS_PER_WORD) / (elapsed / 60):.0f} WPM"

        struck = keystrokes - corrections
        if struck > 0:
            acc_str = f"{min(100.0, typed / struck * 100.0):.0f}%"

        if planned_total is not None and spent > 0.25:
            # We know every pause still to come, so the only unknown is how
            # much slower the machine runs than the plan asked for.
            pace = min(3.0, max(0.9, elapsed / spent))
            eta_str = f"ETA  {self._fmt_secs(max(0.0, (planned_total - spent) * pace))}"
        elif pct > 0 and elapsed > 1:
            eta_str = f"ETA  {self._fmt_secs(elapsed * (100 - pct) / pct)}"

        self.after(0, self._tick_main, pct, wpm_str, eta_str, acc_str,
                   f"Typing… {typed:,} / {total:,} chars ({pct:.0f}%)")

    def _tick_main(self, pct, wpm_str, eta_str, acc_str, status):
        self._prog.set(pct / 100)
        self._wpm_var.set(wpm_str)
        self._eta_var.set(eta_str)
        self._mini_wpm_var.set(wpm_str.replace(" WPM", "") if wpm_str else "—")
        self._mini_done_var.set(f"{pct:.0f}%")
        self._mini_eta_var.set(eta_str.replace("ETA  ", "") if eta_str else "—")
        self._mini_acc_var.set(acc_str or "—")
        self._set_status_main(status, "ok")
        if getattr(self, "_overlay_win", None) and self._overlay_win.winfo_exists():
            try:
                self._overlay_prog.set(pct / 100)
                self._overlay_wpm.set(wpm_str or "—")
                self._overlay_eta.set(eta_str.replace("ETA  ", "") if eta_str else "—")
                self._overlay_pct.set(f"{pct:.0f}%")
            except Exception:
                pass

    def _done(self, msg, kind="ok"):
        self.after(0, self._done_main, msg, kind)

    def _done_main(self, msg, kind):
        self._set_status_main(msg, kind)
        if "Done" in msg:
            self._prog.set(1.0)
            self._mini_done_var.set("100%")
            self._mini_eta_var.set("0s")
        self._pause_btn.configure(state="disabled", text="⏸  Pause  (F6)")
        self._start_btn.configure(state="normal")
        self._typing_active = False
        self._destroy_overlay()

    # =======================================================================
    # Text transforms (popup menu in editor toolbar)
    # =======================================================================
    def _open_transform_menu(self):
        menu = self._menu()
        for name, fn in TRANSFORMS:
            menu.add_command(label=name,
                             command=lambda f=fn, n=name: self._apply_transform(f, n))
        self._popup(menu)

    def _apply_transform(self, fn, name):
        try:
            sel = self._tb._textbox.get("sel.first", "sel.last")
            has_sel = True
        except tk.TclError:
            sel = self._tb.get("1.0", tk.END).rstrip("\n")
            has_sel = False
        if not sel.strip():
            return
        new = fn(sel)
        if has_sel:
            self._tb._textbox.delete("sel.first", "sel.last")
            self._tb._textbox.insert("insert", new)
        else:
            self._tb.delete("1.0", tk.END)
            self._tb.insert("1.0", new)
        self._update_count()
        self._set_status(f"Transform: {name}", "ok")

    # =======================================================================
    # Variables menu
    # =======================================================================
    def _open_variables_menu(self):
        menu = self._menu()
        for token, desc in VARIABLES:
            menu.add_command(label=f"{token}   —   {desc}",
                             command=lambda t=token: self._insert_variable(t))
        self._popup(menu)

    def _insert_variable(self, token):
        try:
            self._tb._textbox.insert(tk.INSERT, token)
        except Exception:
            self._tb.insert(tk.END, token)
        self._update_count()
        self._set_status(f"Inserted {token}", "ok")

    # =======================================================================
    # Dry run preview
    # =======================================================================
    def _dry_run(self):
        """Preview the run in a window instead of the keyboard.

        This executes the same event stream `start_typing` would, so the
        preview shows the real mistakes, the real corrections and the real
        pacing — it is a rehearsal, not an approximation of one.
        """
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        if not text.strip():
            messagebox.showwarning("Empty", "Nothing in the editor to preview.")
            return
        if self._vars_expand.get():
            text = expand_variables(text)
        try:
            style = self._current_style()
        except ValueError:
            messagebox.showerror("Invalid", "Settings must be numeric.")
            return

        win = self._dialog("Dry run", "780x560")
        win.minsize(560, 420)
        win.resizable(True, True)

        card = ctk.CTkFrame(win, **T.card_kwargs())
        card.pack(fill="both", expand=True,
                  padx=T.SPACE["lg"], pady=T.SPACE["lg"])

        self._dialog_heading(
            card, "Dry run",
            "The exact run that would go to your keyboard, typed into this "
            "window instead. No real keystrokes are sent.").pack(
            anchor="w", fill="x", padx=T.CARD_PAD,
            pady=(T.SPACE["lg"], T.SPACE["md"]))

        tb = ctk.CTkTextbox(card, wrap="word", font=T.font("editor"),
                            **T.textbox_kwargs())
        tb.pack(fill="both", expand=True, padx=T.CARD_PAD, pady=(0, T.SPACE["md"]))

        prog = ctk.CTkProgressBar(card, height=4, **T.progress_kwargs())
        prog.set(0)
        prog.pack(fill="x", padx=T.CARD_PAD)

        status = tk.StringVar(value="Running…")
        ctk.CTkLabel(card, textvariable=status, font=T.font("small"),
                     text_color=T.INK_2, anchor="w").pack(
            anchor="w", padx=T.CARD_PAD, pady=(T.SPACE["sm"], T.SPACE["lg"]))

        stop_flag = {"stop": False}

        def on_close():
            stop_flag["stop"] = True
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        def append(s):
            tb.insert(tk.END, s)
            tb.see(tk.END)

        def backspace():
            tb.delete("end-2c", "end-1c")

        def worker():
            total = len(text)
            typed = 0
            keys = 0
            fixes = 0
            t0 = time.time()
            for ev in rz.plan(text, style, random.Random()):
                if stop_flag["stop"]:
                    return
                if isinstance(ev, rz.Pause):
                    end = time.time() + ev.seconds
                    while time.time() < end:
                        if stop_flag["stop"]:
                            return
                        time.sleep(min(0.05, max(0.0, end - time.time())))
                    continue
                if isinstance(ev, rz.Note):
                    self.after(0, status.set, ev.text)
                    continue
                if isinstance(ev, rz.Char):
                    self.after(0, append, ev.ch)
                    keys += 1
                elif isinstance(ev, rz.Key):
                    if ev.name == "backspace":
                        self.after(0, backspace)
                        fixes += 1
                    else:
                        self.after(0, append, "\n")
                    keys += 1
                typed += ev.advance
                self.after(0, prog.set, typed / total if total else 1)
            secs = max(0.001, time.time() - t0)
            wpm = (typed / CHARS_PER_WORD) / (secs / 60)
            struck = max(1, keys - fixes)
            self.after(0, status.set,
                       f"Done ✓   {self._fmt_secs(secs)} · {wpm:.0f} WPM · "
                       f"{fixes:,} corrections · "
                       f"{min(100.0, typed / struck * 100.0):.0f}% accuracy")

        threading.Thread(target=worker, daemon=True).start()

    # =======================================================================
    # Schedule typing for later
    # =======================================================================
    def _schedule_start(self):
        if self._typing_active:
            return
        if not self._tb.get("1.0", tk.END).strip():
            messagebox.showwarning("No Text", "Add text to type first.")
            return
        val = (self._ask_text(
            "Schedule",
            "Start typing at (HH:MM, 24-hour) or in (e.g. 30s, 5m):") or "").strip()
        if not val:
            return
        delay_ms = self._parse_schedule(val)
        if delay_ms is None:
            messagebox.showerror("Invalid", "Use HH:MM or e.g. '30s' / '5m'.")
            return
        eta = _dt.datetime.now() + _dt.timedelta(milliseconds=delay_ms)
        self._set_status(
            f"Scheduled — starts at {eta.strftime('%H:%M:%S')}", "warn")
        self._schedule_btn.configure(text="🕒  Scheduled…", state="disabled")
        self.after(delay_ms, self._fire_schedule)

    def _fire_schedule(self):
        self._schedule_btn.configure(text="🕒  Schedule…", state="normal")
        self.start_typing()

    def _parse_schedule(self, s):
        # Duration form
        m = re.fullmatch(r"(\d+)\s*([smh])", s)
        if m:
            n = int(m.group(1))
            mult = {"s": 1000, "m": 60_000, "h": 3_600_000}[m.group(2)]
            return n * mult
        # Time form
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
        if m:
            now = _dt.datetime.now()
            target = now.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                                 second=0, microsecond=0)
            if target <= now:
                target += _dt.timedelta(days=1)
            return int((target - now).total_seconds() * 1000)
        return None

    # =======================================================================
    # Floating overlay
    # =======================================================================
    def _build_overlay(self):
        w = ctk.CTkToplevel(self)
        w.title("Human Typer")
        w.geometry("268x142+40+40")
        w.attributes("-topmost", True)
        w.configure(fg_color=T.SURFACE)
        w.transient(self)
        self._overlay_win = w

        head = ctk.CTkFrame(w, fg_color="transparent")
        head.pack(fill="x", padx=T.SPACE["lg"], pady=(T.SPACE["md"], 0))
        ctk.CTkLabel(head, text="TYPING", font=T.font("eyebrow"),
                     text_color=T.accent("gold")).pack(side="left")
        self._overlay_wpm = tk.StringVar(value="—")
        ctk.CTkLabel(head, textvariable=self._overlay_wpm,
                     font=T.font("small"), text_color=T.INK_3).pack(side="right")

        self._overlay_pct = tk.StringVar(value="0%")
        ctk.CTkLabel(w, textvariable=self._overlay_pct, font=T.font("metric"),
                     text_color=T.INK).pack(anchor="w", padx=T.SPACE["lg"],
                                            pady=(2, T.SPACE["sm"]))

        self._overlay_prog = ctk.CTkProgressBar(
            w, height=4, corner_radius=2, fg_color=T.SURFACE_SUNK,
            progress_color=T.accent("accent"))
        self._overlay_prog.set(0)
        self._overlay_prog.pack(fill="x", padx=T.SPACE["lg"])

        self._overlay_eta = tk.StringVar(value="—")
        ctk.CTkLabel(w, textvariable=self._overlay_eta, font=T.font("small"),
                     text_color=T.INK_3).pack(anchor="e", padx=T.SPACE["lg"],
                                              pady=(T.SPACE["sm"], T.SPACE["md"]))

    def _destroy_overlay(self):
        w = getattr(self, "_overlay_win", None)
        if w is not None:
            try:
                if w.winfo_exists():
                    w.destroy()
            except Exception:
                pass
            self._overlay_win = None

    # =======================================================================
    # Session history
    # =======================================================================
    def _refresh_history(self):
        for child in self._history_frame.winfo_children():
            child.destroy()
        hist = self.config.get("session_history", [])
        if not hist:
            ctk.CTkLabel(
                self._history_frame,
                text="Nothing yet. Your runs will be listed here.",
                font=T.font("small"), text_color=T.INK_3,
            ).grid(row=0, column=0, sticky="w", padx=4, pady=10)
            return
        for i, h in enumerate(hist):
            row = ctk.CTkFrame(self._history_frame, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=0)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=h.get("when", ""), font=T.font("small"),
                         text_color=T.INK_2, anchor="w").grid(
                row=0, column=0, sticky="w", pady=7)

            facts = ["%s chars" % format(int(h.get("chars", 0)), ","),
                     "%.0f WPM" % h.get("wpm", 0)]
            if "accuracy" in h:
                facts.append("%.0f%% accurate" % h["accuracy"])
            facts.append(self._fmt_secs(h.get("seconds", 0)))
            ctk.CTkLabel(row, text="   ·   ".join(facts), font=T.font("small"),
                         text_color=T.INK, anchor="e").grid(
                row=0, column=1, sticky="e", pady=7)

            if i < len(hist) - 1:
                ctk.CTkFrame(row, height=T.HAIRLINE, fg_color=T.BORDER).grid(
                    row=1, column=0, columnspan=2, sticky="ew")

    def _clear_history(self):
        if not messagebox.askyesno(
                "Clear", "Clear recent-session history?"):
            return
        self.config["session_history"] = []
        self._persist_state()
        self._refresh_history()


if __name__ == "__main__":
    app = HumanTyperApp()
    app.mainloop()
