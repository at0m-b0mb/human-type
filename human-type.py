import json
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
    "theme": "Midnight",
    "dark_mode": True,
    "recent_files": [],
    "custom_presets": {},
    "custom_snippets": {},
    "draft": "",
    "session_history": [],
    "repeat": {"count": "1", "separator": "\\n\\n"},
    "stats": {
        "lifetime_chars": 0,
        "lifetime_sessions": 0,
        "lifetime_seconds": 0.0,
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
# Themes — each defines accent + a few supporting colors
# ---------------------------------------------------------------------------
THEMES = {
    "Midnight": {
        "accent": "#1f6feb", "accent_hover": "#388bfd",
        "ok": "#3fb950", "warn": "#d29922", "err": "#f85149",
        "muted": "gray60",
    },
    "Dracula": {
        "accent": "#bd93f9", "accent_hover": "#caa9fa",
        "ok": "#50fa7b", "warn": "#f1fa8c", "err": "#ff5555",
        "muted": "#6272a4",
    },
    "Cyberpunk": {
        "accent": "#ff2bd6", "accent_hover": "#ff5be0",
        "ok": "#00ffa3", "warn": "#fff200", "err": "#ff003c",
        "muted": "#9d4edd",
    },
    "Forest": {
        "accent": "#2ea043", "accent_hover": "#3fb950",
        "ok": "#3fb950", "warn": "#d29922", "err": "#da3633",
        "muted": "gray60",
    },
    "Ocean": {
        "accent": "#00b4d8", "accent_hover": "#48cae4",
        "ok": "#90e0ef", "warn": "#ffd166", "err": "#ef476f",
        "muted": "gray60",
    },
    "Sunset": {
        "accent": "#ff7847", "accent_hover": "#ff9466",
        "ok": "#ffd166", "warn": "#ffba49", "err": "#ef476f",
        "muted": "gray60",
    },
}

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
# Typing behaviour constants
# ---------------------------------------------------------------------------
CHARS_PER_WORD = 5
FATIGUE_FACTOR = 0.5
SEMICOLON_PAUSE_FACTOR = 0.7
COMMA_PAUSE_FACTOR = 0.4
TYPO_WRONG_KEY_MIN = 1.2
TYPO_WRONG_KEY_MAX = 2.5
TYPO_BACKSPACE_MIN = 0.8
TYPO_BACKSPACE_MAX = 1.5

# Burst-mode tuning
BURST_WORDS_MIN = 6
BURST_WORDS_MAX = 14
BURST_REST_MIN = 0.4
BURST_REST_MAX = 1.4

# Idle "thinking" pause tuning
IDLE_CHARS_MIN = 150
IDLE_CHARS_MAX = 350
IDLE_PAUSE_MIN = 0.8
IDLE_PAUSE_MAX = 2.6

# Probability that a word in the input gets temporarily mistyped using a
# realistic English misspelling, then corrected.
COMMON_TYPO_CHANCE = 0.03
CAP_SLIP_CHANCE = 0.01   # extra probability of a capitalization slip per char

# Keyboard-adjacency map used for realistic typo generation
NEARBY_KEYS = {
    "a": "sqwz",   "b": "vghn",   "c": "xdfv",   "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko",   "j": "huikmn",
    "k": "jiolm",  "l": "kop",    "m": "njk",    "n": "bhjm",   "o": "iklp",
    "p": "ol",     "q": "wa",     "r": "edft",   "s": "awedxz", "t": "rfgy",
    "u": "yhji",   "v": "cfgb",   "w": "qase",   "x": "zsdc",   "y": "tghu",
    "z": "asx",
}

# Common English mis-spellings that a typist might write then correct
COMMON_TYPOS = {
    "the": "teh", "and": "adn", "you": "yuo", "have": "ahve",
    "that": "taht", "this": "tihs", "with": "wiht", "from": "fomr",
    "they": "tehy", "their": "thier", "there": "tehre", "would": "woudl",
    "could": "coudl", "should": "shoudl", "because": "becuase",
    "receive": "recieve", "definitely": "definately", "separate": "seperate",
    "necessary": "neccessary", "occurred": "occured",
    "tomorrow": "tommorow", "really": "realy", "people": "poeple",
    "about": "abuot", "which": "whcih", "however": "hwoever",
}


# ===========================================================================
# Main app
# ===========================================================================
class HumanTyperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Human Typer")
        self.geometry("1180x780")
        self.minsize(960, 660)

        self.config = load_config()
        ctk.set_appearance_mode("dark" if self.config.get("dark_mode", True) else "light")
        ctk.set_default_color_theme("blue")
        self._theme_name = self.config.get("theme", "Midnight")

        self._stop = False
        self._pause = threading.Event()
        self._pause.set()
        self._typing_active = False

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
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        # Main area
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        self._build_header(main)
        self._build_tabs(main)
        self._build_action_bar(main)
        self._build_status_bar(main)

    # ----- Sidebar ---------------------------------------------------------
    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=240, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        self._sidebar = side

        # Brand
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 6))
        ctk.CTkLabel(
            brand, text="⌨", font=ctk.CTkFont(size=34),
        ).pack(side="left")
        ctk.CTkLabel(
            brand, text=" Human\n Typer",
            font=ctk.CTkFont(size=18, weight="bold"),
            justify="left",
        ).pack(side="left", padx=(2, 0))

        ctk.CTkLabel(
            side, text="Make any machine type\nlike a human.",
            text_color="gray55", justify="left",
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 18))

        # Separator
        ctk.CTkFrame(side, height=1, fg_color=("gray80", "gray25")).grid(
            row=2, column=0, sticky="ew", padx=14, pady=(0, 14))

        # Theme picker
        ctk.CTkLabel(
            side, text="🎨  THEME", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray55",
        ).grid(row=3, column=0, sticky="w", padx=18)
        self._theme_menu = ctk.CTkOptionMenu(
            side, values=list(THEMES.keys()),
            command=self._on_theme_change,
        )
        self._theme_menu.set(self._theme_name)
        self._theme_menu.grid(row=4, column=0, sticky="ew", padx=18, pady=(6, 8))

        self._mode_btn = ctk.CTkButton(
            side, text="☀  Light Mode",
            fg_color="transparent", border_width=1,
            command=self._toggle_dark_mode,
        )
        self._mode_btn.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))

        # Live mini stats
        ctk.CTkFrame(side, height=1, fg_color=("gray80", "gray25")).grid(
            row=6, column=0, sticky="ew", padx=14, pady=(0, 14))

        ctk.CTkLabel(
            side, text="📊  SESSION", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray55",
        ).grid(row=7, column=0, sticky="w", padx=18)

        self._mini_stats = ctk.CTkFrame(side, fg_color="transparent")
        self._mini_stats.grid(row=8, column=0, sticky="ew", padx=18, pady=(6, 0))

        self._mini_wpm_var = tk.StringVar(value="—")
        self._mini_eta_var = tk.StringVar(value="—")
        self._mini_done_var = tk.StringVar(value="0%")

        self._mini_card("WPM", self._mini_wpm_var, 0)
        self._mini_card("Done", self._mini_done_var, 1)
        self._mini_card("ETA", self._mini_eta_var, 2)

        # Tip box at the bottom
        side.grid_rowconfigure(9, weight=1)
        tip = ctk.CTkFrame(side, corner_radius=8)
        tip.grid(row=10, column=0, sticky="ew", padx=14, pady=14)
        ctk.CTkLabel(
            tip, text="💡  Tip",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray55",
        ).pack(anchor="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(
            tip,
            text=("F5 starts typing,\n"
                  "F6 pause / resume,\n"
                  "Esc stops.\n\n"
                  "Move mouse to top-left\ncorner for fail-safe."),
            text_color="gray55", justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(2, 10))

    def _mini_card(self, label, var, col):
        f = ctk.CTkFrame(self._mini_stats, corner_radius=8)
        f.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
        self._mini_stats.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(
            f, text=label, font=ctk.CTkFont(size=10, weight="bold"),
            text_color="gray55",
        ).pack(pady=(8, 0))
        ctk.CTkLabel(
            f, textvariable=var, font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(0, 8))

    # ----- Header ----------------------------------------------------------
    def _build_header(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        # Accent bar
        self._accent_bar = ctk.CTkFrame(hdr, height=3, corner_radius=2)
        self._accent_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        title_row = ctk.CTkFrame(hdr, fg_color="transparent")
        title_row.grid(row=1, column=0, sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_row, text="Human Typer",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_row,
            text="Type text naturally into any window — load a file, paste, or type below.",
            text_color="gray60", font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ----- Tabs ------------------------------------------------------------
    def _build_tabs(self, parent):
        self._tabs = ctk.CTkTabview(parent, corner_radius=10)
        self._tabs.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        self._tabs.add("✏  Editor")
        self._tabs.add("⚙  Tweaks")
        self._tabs.add("✨  Snippets")
        self._tabs.add("📊  Stats")
        self._tabs.add("ℹ  About")

        self._build_editor_tab(self._tabs.tab("✏  Editor"))
        self._build_tweaks_tab(self._tabs.tab("⚙  Tweaks"))
        self._build_snippets_tab(self._tabs.tab("✨  Snippets"))
        self._build_stats_tab(self._tabs.tab("📊  Stats"))
        self._build_about_tab(self._tabs.tab("ℹ  About"))

    # ----- Editor tab ------------------------------------------------------
    def _build_editor_tab(self, tab):
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Toolbar
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 8))

        buttons = [
            ("📂", "Load",       self.load_file),
            ("📋", "Clipboard",  self.import_clipboard),
            ("🔍", "Find",       self.open_find_replace),
            ("✨", "Transform",  self._open_transform_menu),
            ("🔣", "Variable",   self._open_variables_menu),
            ("🧪", "Dry Run",    self._dry_run),
            ("🕘", "Recent",     self._open_recent_menu),
            ("🧹", "Clear",      self.clear_text),
        ]
        for idx, (icon, label, cmd) in enumerate(buttons):
            ctk.CTkButton(
                bar, text=f"{icon}  {label}", width=110, command=cmd,
            ).pack(side="left", padx=(0, 6))

        self._count_var = tk.StringVar(value="0 chars · 0 words")
        ctk.CTkLabel(
            bar, textvariable=self._count_var, text_color="gray60",
        ).pack(side="right", padx=(0, 4))

        # Editor + side stats panel
        mono = "Menlo" if _IS_MAC else "Consolas"
        self._tb = ctk.CTkTextbox(
            tab, wrap="word",
            font=ctk.CTkFont(family=mono, size=13),
            corner_radius=10,
        )
        self._tb.grid(row=1, column=0, sticky="nsew", padx=(4, 8), pady=(0, 4))
        self._tb._textbox.bind("<KeyRelease>", self._update_count)
        self._tb._textbox.bind("<<Modified>>", self._on_modified)

        # Stats side panel
        side = ctk.CTkFrame(tab, corner_radius=10)
        side.grid(row=1, column=1, sticky="nsew", padx=(0, 4), pady=(0, 4))
        side.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            side, text="📐  Text Analysis",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))

        self._stat_rows = {}
        rows = [
            ("Characters", "chars"),
            ("Words",      "words"),
            ("Sentences",  "sentences"),
            ("Paragraphs", "paragraphs"),
            ("Avg word",   "avg_word"),
            ("Reading",    "reading"),
            ("Est. type",  "estimate"),
            ("Flesch ease", "flesch"),
            ("Grade level", "grade"),
        ]
        for r, (label, key) in enumerate(rows, start=1):
            row = ctk.CTkFrame(side, fg_color="transparent")
            row.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=11),
                text_color="gray60",
            ).grid(row=0, column=0, sticky="w")
            var = tk.StringVar(value="—")
            self._stat_rows[key] = var
            ctk.CTkLabel(
                row, textvariable=var,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=1, sticky="e")

        # divider + helper buttons
        ctk.CTkFrame(side, height=1, fg_color=("gray80", "gray25")).grid(
            row=20, column=0, sticky="ew", padx=14, pady=(14, 10))

        ctk.CTkButton(
            side, text="💾  Save as Snippet…",
            fg_color="transparent", border_width=1,
            command=self._save_selection_as_snippet,
        ).grid(row=21, column=0, sticky="ew", padx=14, pady=(0, 8))

        ctk.CTkButton(
            side, text="💾  Export Text…",
            fg_color="transparent", border_width=1,
            command=self._export_text,
        ).grid(row=22, column=0, sticky="ew", padx=14, pady=(0, 14))

    # ----- Tweaks tab ------------------------------------------------------
    def _build_tweaks_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)

        # Presets card
        pcard = ctk.CTkFrame(tab, corner_radius=10)
        pcard.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        pcard.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            pcard, text="⚡  Speed Presets",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 8))

        self._preset_seg = ctk.CTkSegmentedButton(
            pcard, values=list(PRESETS.keys()), command=self._apply_preset,
        )
        self._preset_seg.set("Normal")
        self._preset_seg.grid(row=1, column=0, columnspan=4, sticky="ew",
                              padx=16, pady=(0, 10))

        # Custom-preset row
        crow = ctk.CTkFrame(pcard, fg_color="transparent")
        crow.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 14))
        crow.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            crow, text="Custom:", text_color="gray60",
        ).pack(side="left", padx=(0, 8))
        self._custom_preset_menu = ctk.CTkOptionMenu(
            crow, values=self._custom_preset_values(),
            command=self._apply_custom_preset,
            width=170,
        )
        self._custom_preset_menu.pack(side="left")
        ctk.CTkButton(
            crow, text="💾  Save Current…", width=140,
            command=self._save_custom_preset,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            crow, text="🗑  Delete", width=90,
            fg_color="transparent", border_width=1,
            command=self._delete_custom_preset,
        ).pack(side="left", padx=(8, 0))

        # Timing card
        timing = ctk.CTkFrame(tab, corner_radius=10)
        timing.grid(row=1, column=0, sticky="nsew", padx=(4, 6), pady=4)
        timing.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(
            timing, text="⏱  Timing", font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 8))

        self._vars = {}
        fields = [
            ("Start delay (s)",     "start_delay", "5"),
            ("Base delay/char (s)", "base_delay",  "0.08"),
            ("Variation ± (s)",     "variation",   "0.03"),
            ("Punct pause (s)",     "punct_pause", "0.25"),
            ("Para pause (s)",      "para_pause",  "0.8"),
            ("Typo chance (0–1)",   "typo_chance", "0.04"),
        ]
        for idx, (label, name, default) in enumerate(fields):
            r = 1 + idx // 2
            cb = (idx % 2) * 2
            ctk.CTkLabel(
                timing, text=label, font=ctk.CTkFont(size=12),
            ).grid(row=r, column=cb, sticky="w", padx=(16, 4), pady=6)
            var = tk.StringVar(value=default)
            self._vars[name] = var
            ctk.CTkEntry(timing, textvariable=var, width=110).grid(
                row=r, column=cb + 1, sticky="w", padx=(0, 18), pady=6)

        # Padding row at the bottom of timing card
        ctk.CTkLabel(timing, text="").grid(row=99, column=0, pady=(0, 6))

        # Behaviour card
        behav = ctk.CTkFrame(tab, corner_radius=10)
        behav.grid(row=1, column=1, sticky="nsew", padx=(6, 4), pady=4)
        behav.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            behav, text="🎭  Behaviour", font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self._enter_var    = tk.BooleanVar(value=False)
        self._burst_var    = tk.BooleanVar(value=True)
        self._fatigue_var  = tk.BooleanVar(value=False)
        self._common_typos = tk.BooleanVar(value=False)
        self._cap_slip_var = tk.BooleanVar(value=False)
        self._burst_mode   = tk.BooleanVar(value=False)
        self._idle_var     = tk.BooleanVar(value=False)
        self._vars_expand  = tk.BooleanVar(value=True)
        self._overlay_var  = tk.BooleanVar(value=False)

        switches = [
            ("Newlines → Enter key",        self._enter_var,
             "Press Enter for each newline"),
            ("Word-burst variation",        self._burst_var,
             "Micro-pauses between words"),
            ("Fatigue (slow over time)",    self._fatigue_var,
             "Get gradually slower the longer you type"),
            ("Common English typos",        self._common_typos,
             "Occasionally mistype words like teh→the and correct"),
            ("Capitalization slip-ups",     self._cap_slip_var,
             "Rare wrong-case letter then quick correction"),
            ("Burst mode (chunks + rests)", self._burst_mode,
             "Type a few words quickly, rest, repeat"),
            ("Idle thinking pauses",        self._idle_var,
             "Occasional realistic 1-3 s mid-text pauses"),
            ("Expand {variables}",          self._vars_expand,
             "Substitute {date}, {time}, {clipboard}, {random:N}…"),
            ("Floating overlay window",     self._overlay_var,
             "Always-on-top progress window while typing"),
        ]
        for r, (text, var, desc) in enumerate(switches, start=1):
            row = ctk.CTkFrame(behav, fg_color="transparent")
            row.grid(row=r, column=0, sticky="ew", padx=16, pady=3)
            ctk.CTkSwitch(
                row, text=text, variable=var, onvalue=True, offvalue=False,
            ).pack(anchor="w")
            ctk.CTkLabel(
                row, text=desc, text_color="gray55",
                font=ctk.CTkFont(size=10),
            ).pack(anchor="w", padx=(46, 0))

        # Repeat row inside the timing card
        rrow = ctk.CTkFrame(timing, fg_color="transparent")
        rrow.grid(row=98, column=0, columnspan=4, sticky="ew",
                  padx=14, pady=(6, 0))
        ctk.CTkLabel(
            rrow, text="🔁  Repeat:", font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._repeat_count_var = tk.StringVar(value="1")
        ctk.CTkEntry(rrow, textvariable=self._repeat_count_var, width=60).pack(
            side="left", padx=(8, 6))
        ctk.CTkLabel(rrow, text="times, separator:",
                     text_color="gray60").pack(side="left", padx=(0, 6))
        self._repeat_sep_var = tk.StringVar(value="\\n\\n")
        ctk.CTkEntry(rrow, textvariable=self._repeat_sep_var, width=120).pack(
            side="left")
        ctk.CTkLabel(rrow, text=" (use \\n for newline, \\t for tab)",
                     text_color="gray55",
                     font=ctk.CTkFont(size=10)).pack(side="left")

    # ----- Snippets tab ----------------------------------------------------
    def _build_snippets_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(0, weight=1)

        # Snippet list
        left = ctk.CTkFrame(tab, corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 8), pady=4)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left, text="✨  Snippet Library",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))
        ctk.CTkLabel(
            left, text="Quick text to drop into the editor.",
            text_color="gray55", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        self._snip_list_frame = ctk.CTkScrollableFrame(left, corner_radius=8)
        self._snip_list_frame.grid(row=2, column=0, sticky="nsew",
                                   padx=10, pady=(0, 10))
        self._snip_list_frame.grid_columnconfigure(0, weight=1)
        self._snip_buttons = {}
        self._snip_selected = None

        btnrow = ctk.CTkFrame(left, fg_color="transparent")
        btnrow.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        btnrow.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            btnrow, text="➕  New", command=self._new_snippet,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            btnrow, text="🗑  Delete",
            fg_color="transparent", border_width=1,
            command=self._delete_snippet,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Snippet preview
        right = ctk.CTkFrame(tab, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 4), pady=4)
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._snip_title_var = tk.StringVar(value="No snippet selected")
        ctk.CTkLabel(
            right, textvariable=self._snip_title_var,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))

        ctk.CTkLabel(
            right, text="Preview & edit",
            text_color="gray55", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        mono = "Menlo" if _IS_MAC else "Consolas"
        self._snip_preview = ctk.CTkTextbox(
            right, wrap="word",
            font=ctk.CTkFont(family=mono, size=12),
            corner_radius=8,
        )
        self._snip_preview.grid(row=2, column=0, sticky="nsew",
                                padx=14, pady=(0, 8))

        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        ctk.CTkButton(
            actions, text="📥  Insert into Editor",
            command=self._insert_snippet,
        ).pack(side="left")
        ctk.CTkButton(
            actions, text="💾  Save Changes",
            fg_color="transparent", border_width=1,
            command=self._save_snippet_changes,
        ).pack(side="left", padx=(8, 0))

        self._refresh_snippet_list()

    # ----- Stats tab -------------------------------------------------------
    def _build_stats_tab(self, tab):
        tab.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            tab, text="📊  Statistics",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 12))

        ctk.CTkLabel(
            tab, text="LIFETIME",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray60",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8)

        self._life_chars  = self._stat_card(tab, 2, 0, "Chars typed", "0")
        self._life_sess   = self._stat_card(tab, 2, 1, "Sessions", "0")
        self._life_time   = self._stat_card(tab, 2, 2, "Time spent", "0s")
        self._life_best   = self._stat_card(tab, 3, 0, "Best WPM", "0")
        self._life_avg    = self._stat_card(tab, 3, 1, "Avg WPM", "0")
        self._life_words  = self._stat_card(tab, 3, 2, "Words typed", "0")

        ctk.CTkLabel(
            tab, text="THIS SESSION",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray60",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=(20, 0))

        self._sess_chars = self._stat_card(tab, 5, 0, "Chars typed", "0")
        self._sess_time  = self._stat_card(tab, 5, 1, "Time spent", "0s")
        self._sess_wpm   = self._stat_card(tab, 5, 2, "Last WPM", "0")

        self._session_chars = 0
        self._session_seconds = 0.0
        self._session_last_wpm = 0.0

        ctk.CTkLabel(
            tab, text="RECENT SESSIONS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray60",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=(20, 0))

        self._history_frame = ctk.CTkScrollableFrame(
            tab, corner_radius=10, height=180,
        )
        self._history_frame.grid(row=7, column=0, columnspan=3,
                                 sticky="ew", padx=8, pady=(6, 0))
        self._history_frame.grid_columnconfigure(0, weight=1)

        btnrow = ctk.CTkFrame(tab, fg_color="transparent")
        btnrow.grid(row=8, column=0, columnspan=3, sticky="ew",
                    padx=8, pady=(10, 8))
        ctk.CTkButton(
            btnrow, text="🧹  Reset Lifetime Stats",
            fg_color="transparent", border_width=1,
            command=self._reset_lifetime_stats,
        ).pack(side="left")
        ctk.CTkButton(
            btnrow, text="🗑  Clear History",
            fg_color="transparent", border_width=1,
            command=self._clear_history,
        ).pack(side="left", padx=(8, 0))

        self._refresh_stat_cards()
        self._refresh_history()

    def _stat_card(self, parent, r, c, label, initial):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=r, column=c, sticky="ew", padx=8, pady=6)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text=label, font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray55",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        var = tk.StringVar(value=initial)
        ctk.CTkLabel(
            card, textvariable=var,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))
        return var

    # ----- About tab -------------------------------------------------------
    def _build_about_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(tab, corner_radius=10)
        card.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="⌨   Human Typer",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 0))

        ctk.CTkLabel(
            card,
            text="Make any machine type like a human — adjustable speed, "
                 "realistic typos, natural pauses, fatigue, and snippets.",
            text_color="gray60", justify="left", wraplength=720,
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(2, 12))

        notes = (
            "• F5 starts typing, F6 pauses/resumes, Esc stops.\n"
            "• Move the mouse to the top-left corner to fail-safe-abort at any moment.\n"
            "• Your draft, settings, snippets, history & lifetime stats persist in "
            f"{CONFIG_PATH}.\n"
            "• On macOS, grant Accessibility permission to your terminal/IDE.\n"
        )
        ctk.CTkLabel(
            card, text=notes, justify="left", text_color="gray60",
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 16))

        # Variables documentation
        vcard = ctk.CTkFrame(tab, corner_radius=10)
        vcard.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        vcard.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            vcard, text="🔣  Variables",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            vcard,
            text="Drop these into your text — they're expanded the moment "
                 "typing starts (toggle in Tweaks → Behaviour).",
            text_color="gray60", justify="left", wraplength=720,
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 8))

        for i, (token, desc) in enumerate(VARIABLES, start=2):
            row = ctk.CTkFrame(vcard, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", padx=18, pady=1)
            row.grid_columnconfigure(1, weight=1)
            mono = "Menlo" if _IS_MAC else "Consolas"
            ctk.CTkLabel(
                row, text=token,
                font=ctk.CTkFont(family=mono, size=12, weight="bold"),
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(
                row, text=desc, text_color="gray60",
            ).grid(row=0, column=1, sticky="w", padx=(14, 0))

        ctk.CTkLabel(vcard, text="").grid(row=99, column=0, pady=(0, 8))

    # ----- Action bar + status --------------------------------------------
    def _build_action_bar(self, parent):
        ab = ctk.CTkFrame(parent, fg_color="transparent")
        ab.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ab.grid_columnconfigure(5, weight=1)

        self._prog = ctk.CTkProgressBar(parent, height=8, corner_radius=4)
        self._prog.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._prog.set(0)

        self._start_btn = ctk.CTkButton(
            ab, text="▶  Start Typing  (F5)", width=170,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_typing,
        )
        self._start_btn.grid(row=0, column=0, sticky="w")

        self._schedule_btn = ctk.CTkButton(
            ab, text="🕒  Schedule…", width=120,
            fg_color="transparent", border_width=1,
            command=self._schedule_start,
        )
        self._schedule_btn.grid(row=0, column=1, padx=(8, 0))

        self._pause_btn = ctk.CTkButton(
            ab, text="⏸  Pause  (F6)", width=120,
            fg_color="transparent", border_width=1, state="disabled",
            command=self.toggle_pause,
        )
        self._pause_btn.grid(row=0, column=2, padx=(8, 0))

        ctk.CTkButton(
            ab, text="⏹  Stop  (Esc)", width=110,
            fg_color="transparent", border_width=1,
            command=self.stop_typing,
        ).grid(row=0, column=3, padx=(8, 0))

        self._eta_var = tk.StringVar(value="")
        ctk.CTkLabel(
            ab, textvariable=self._eta_var, text_color="gray60",
        ).grid(row=0, column=4, padx=(16, 0))

        self._wpm_var = tk.StringVar(value="")
        ctk.CTkLabel(
            ab, textvariable=self._wpm_var,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=5, sticky="e")

    def _build_status_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        bar.grid_columnconfigure(1, weight=1)

        self._status_dot = ctk.CTkLabel(bar, text="●", font=ctk.CTkFont(size=14))
        self._status_dot.grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(
            bar, textvariable=self._status_var,
            anchor="w", text_color="gray60",
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._set_status("Ready.", "ok")

    # =======================================================================
    # State persistence / restore
    # =======================================================================
    def _restore_state(self):
        # Restore last-used timing settings
        for k, v in self.config.get("last_settings", {}).items():
            if k in self._vars:
                self._vars[k].set(v)
        # Restore toggles
        toggles = self.config.get("toggles", {})
        self._enter_var.set(toggles.get("newlines_enter", False))
        self._burst_var.set(toggles.get("word_burst", True))
        self._fatigue_var.set(toggles.get("fatigue", False))
        self._common_typos.set(toggles.get("common_typos", False))
        self._cap_slip_var.set(toggles.get("cap_slips", False))
        self._burst_mode.set(toggles.get("burst_mode", False))
        self._idle_var.set(toggles.get("idle_pauses", False))
        self._vars_expand.set(toggles.get("expand_vars", True))
        self._overlay_var.set(toggles.get("show_overlay", False))
        # Restore repeat
        rep = self.config.get("repeat", {})
        self._repeat_count_var.set(rep.get("count", "1"))
        self._repeat_sep_var.set(rep.get("separator", "\\n\\n"))
        # Restore draft
        draft = self.config.get("draft", "")
        if draft:
            self._tb.insert("1.0", draft)
        self._update_count()
        # Apply theme
        self._apply_theme_colors(self._theme_name)
        self._mode_btn.configure(
            text="☀  Light Mode" if self.config.get("dark_mode", True) else "🌙  Dark Mode")

    def _persist_state(self):
        try:
            self.config["last_settings"] = {k: v.get() for k, v in self._vars.items()}
            self.config["toggles"] = {
                "newlines_enter": self._enter_var.get(),
                "word_burst": self._burst_var.get(),
                "fatigue": self._fatigue_var.get(),
                "common_typos": self._common_typos.get(),
                "cap_slips": self._cap_slip_var.get(),
                "burst_mode": self._burst_mode.get(),
                "idle_pauses": self._idle_var.get(),
                "expand_vars": self._vars_expand.get(),
                "show_overlay": self._overlay_var.get(),
            }
            self.config["repeat"] = {
                "count": self._repeat_count_var.get(),
                "separator": self._repeat_sep_var.get(),
            }
            self.config["theme"] = self._theme_name
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
        self._theme_name = name
        self._apply_theme_colors(name)
        self._persist_state()

    def _apply_theme_colors(self, name):
        t = THEMES.get(name, THEMES["Midnight"])
        if hasattr(self, "_accent_bar"):
            self._accent_bar.configure(fg_color=t["accent"])
        if hasattr(self, "_start_btn"):
            self._start_btn.configure(fg_color=t["accent"], hover_color=t["accent_hover"])
        if hasattr(self, "_prog"):
            self._prog.configure(progress_color=t["accent"])

    def _toggle_dark_mode(self):
        dark = ctk.get_appearance_mode().lower() != "dark"
        ctk.set_appearance_mode("dark" if dark else "light")
        self._mode_btn.configure(text="☀  Light Mode" if dark else "🌙  Dark Mode")
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
        dlg = ctk.CTkInputDialog(
            text="Name for this custom preset:", title="Save Preset",
        )
        name = dlg.get_input()
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
            title="Select a text file",
            filetypes=[("Text files", "*.txt"), ("Markdown", "*.md"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        self._load_path(path)

    def _load_path(self, path):
        try:
            text = Path(path).read_text(encoding="utf-8")
            self._tb.delete("1.0", tk.END)
            self._tb.insert("1.0", text)
            self._update_count()
            self._set_status(f"Loaded: {Path(path).name}", "ok")
            self._push_recent(path)
        except Exception as exc:
            messagebox.showerror("File Error", f"Could not read file:\n{exc}")

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
        menu = tk.Menu(self, tearoff=0)
        for path in recents:
            menu.add_command(label=Path(path).name,
                             command=lambda p=path: self._load_path(p))
        menu.add_separator()
        menu.add_command(label="Clear list",
                         command=self._clear_recent)
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

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
        self._count_var.set(f"{chars:,} chars · {words:,} words")

        # Detailed stats
        if "chars" in self._stat_rows:
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
        try:
            base = float(self._vars["base_delay"].get())
            punct = float(self._vars["punct_pause"].get())
            para = float(self._vars["para_pause"].get())
            start = float(self._vars["start_delay"].get())
        except ValueError:
            return 0.0
        total = start
        for ch in text:
            total += base
            if ch in ".!?":
                total += punct
            elif ch in ";:":
                total += punct * SEMICOLON_PAUSE_FACTOR
            elif ch == ",":
                total += punct * COMMA_PAUSE_FACTOR
        total += text.count("\n\n") * para
        return total

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
            return
        w = ctk.CTkToplevel(self)
        w.title("Find & Replace")
        w.geometry("420x180")
        w.transient(self)
        self._find_win = w

        ctk.CTkLabel(w, text="Find:").grid(row=0, column=0, padx=14, pady=(16, 4), sticky="w")
        find_var = tk.StringVar()
        ctk.CTkEntry(w, textvariable=find_var, width=260).grid(
            row=0, column=1, columnspan=2, padx=(0, 14), pady=(16, 4), sticky="ew")

        ctk.CTkLabel(w, text="Replace:").grid(row=1, column=0, padx=14, pady=4, sticky="w")
        repl_var = tk.StringVar()
        ctk.CTkEntry(w, textvariable=repl_var, width=260).grid(
            row=1, column=1, columnspan=2, padx=(0, 14), pady=4, sticky="ew")

        case_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(w, text="Match case", variable=case_var).grid(
            row=2, column=1, sticky="w", pady=(6, 0))

        def do_find_all():
            self._tb._textbox.tag_remove("find", "1.0", tk.END)
            needle = find_var.get()
            if not needle:
                return
            opts = {"nocase": not case_var.get()}
            start = "1.0"
            count = 0
            while True:
                idx = self._tb._textbox.search(needle, start, stopindex=tk.END, **opts)
                if not idx:
                    break
                end = f"{idx}+{len(needle)}c"
                self._tb._textbox.tag_add("find", idx, end)
                start = end
                count += 1
            self._tb._textbox.tag_config("find", background="#ffd166", foreground="black")
            self._set_status(f"Found {count} match(es).", "ok" if count else "warn")

        def do_replace_all():
            text = self._tb.get("1.0", tk.END).rstrip("\n")
            needle = find_var.get()
            if not needle:
                return
            if case_var.get():
                new = text.replace(needle, repl_var.get())
                n = text.count(needle)
            else:
                pattern = re.compile(re.escape(needle), re.IGNORECASE)
                new, n = pattern.subn(repl_var.get(), text)
            self._tb.delete("1.0", tk.END)
            self._tb.insert("1.0", new)
            self._update_count()
            self._set_status(f"Replaced {n} occurrence(s).", "ok")

        ctk.CTkButton(w, text="🔍  Find All", command=do_find_all).grid(
            row=3, column=1, sticky="e", pady=14)
        ctk.CTkButton(w, text="✏  Replace All",
                      fg_color="transparent", border_width=1,
                      command=do_replace_all).grid(
            row=3, column=2, sticky="w", padx=(8, 14), pady=14)

        w.grid_columnconfigure(2, weight=1)

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
            tag = "  ⭐" if name in BUILTIN_SNIPPETS else ""
            btn = ctk.CTkButton(
                self._snip_list_frame,
                text=f"{name}{tag}",
                anchor="w",
                fg_color="transparent",
                hover_color=("gray85", "gray25"),
                command=lambda n=name: self._select_snippet(n),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=2)
            self._snip_buttons[name] = btn

    def _select_snippet(self, name):
        self._snip_selected = name
        self._snip_title_var.set(name)
        self._snip_preview.delete("1.0", tk.END)
        self._snip_preview.insert("1.0", self._all_snippets().get(name, ""))

    def _new_snippet(self):
        dlg = ctk.CTkInputDialog(text="Snippet name:", title="New Snippet")
        name = dlg.get_input()
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
        self._tabs.set("✏  Editor")
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
        dlg = ctk.CTkInputDialog(text="Snippet name:", title="Save as Snippet")
        name = dlg.get_input()
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
            self._pause_btn.configure(text="▶  Resume  (F6)")
            self._set_status("Paused. Click Resume to continue.", "warn")
        else:
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
            cfg = {k: float(v.get()) for k, v in self._vars.items()}
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
            args=(text, cfg,
                  self._enter_var.get(),
                  self._fatigue_var.get(),
                  self._burst_var.get(),
                  self._common_typos.get(),
                  self._cap_slip_var.get(),
                  self._burst_mode.get(),
                  self._idle_var.get()),
            daemon=True,
        ).start()

    # =======================================================================
    # Core typing loop (background thread)
    # =======================================================================
    def _run(self, text, cfg, press_enter, fatigue, word_burst,
             common_typos, cap_slips, burst_mode, idle_pauses):
        try:
            start_delay = cfg["start_delay"]
            base_delay  = cfg["base_delay"]
            variation   = cfg["variation"]
            punct_pause = cfg["punct_pause"]
            para_pause  = cfg["para_pause"]
            typo_chance = cfg["typo_chance"]

            # Countdown
            for remaining in range(int(start_delay), 0, -1):
                if self._stop:
                    self._done("Stopped.", "warn")
                    return
                self._set_status(
                    f"Starting in {remaining}s — switch to target window now…",
                    "warn")
                time.sleep(1)
            frac = start_delay - int(start_delay)
            if frac > 0:
                time.sleep(frac)

            total = len(text)
            typed = 0
            chars_wpm = 0
            t0 = time.time()
            i = 0

            words_since_rest = 0
            next_rest_word_target = random.randint(BURST_WORDS_MIN, BURST_WORDS_MAX)
            chars_since_idle = 0
            next_idle_target = random.randint(IDLE_CHARS_MIN, IDLE_CHARS_MAX)

            while i < len(text):
                if self._stop:
                    self._done("Stopped.", "warn")
                    self._record_session(typed, time.time() - t0, chars_wpm)
                    return
                self._pause.wait()

                ch = text[i]

                # Paragraph (blank line) handling
                if ch == "\n" and i + 1 < len(text) and text[i + 1] == "\n":
                    if press_enter:
                        self._press_key("enter")
                    typed += 1
                    self._tick(typed, total, chars_wpm, t0)
                    time.sleep(para_pause)
                    i += 1
                    if press_enter:
                        self._press_key("enter")
                    typed += 1
                    i += 1
                    continue

                if ch == "\n":
                    if press_enter:
                        self._press_key("enter")
                    typed += 1
                    self._tick(typed, total, chars_wpm, t0)
                    time.sleep(max(0, base_delay + random.uniform(-variation, variation)))
                    i += 1
                    continue

                # ── Common-typo (word-level) ──────────────────────────────
                consumed_word = False
                if common_typos and ch.isalpha() and (i == 0 or not text[i - 1].isalpha()):
                    m = re.match(r"[A-Za-z]+", text[i:])
                    if m:
                        word = m.group(0)
                        lw = word.lower()
                        if lw in COMMON_TYPOS and random.random() < COMMON_TYPO_CHANCE:
                            wrong = COMMON_TYPOS[lw]
                            # match capitalization of the original word
                            if word[0].isupper():
                                wrong = wrong[0].upper() + wrong[1:]
                            for c in wrong:
                                if self._stop:
                                    self._done("Stopped.", "warn")
                                    self._record_session(typed, time.time() - t0, chars_wpm)
                                    return
                                self._pause.wait()
                                self._emit(c)
                                time.sleep(max(0, base_delay + random.uniform(-variation, variation)))
                            # noticed; pause a beat, backspace it all
                            time.sleep(base_delay * 3)
                            for _ in range(len(wrong)):
                                self._press_key("backspace")
                                time.sleep(base_delay * 0.6)
                            # now type the right word naturally
                            for c in word:
                                if self._stop:
                                    self._done("Stopped.", "warn")
                                    self._record_session(typed, time.time() - t0, chars_wpm)
                                    return
                                self._pause.wait()
                                self._emit(c)
                                typed += 1
                                chars_wpm += 1
                                time.sleep(max(0, base_delay + random.uniform(-variation, variation)))
                                self._tick(typed, total, chars_wpm, t0)
                            i += len(word)
                            consumed_word = True
                if consumed_word:
                    continue

                # ── Adjacency typo simulation ─────────────────────────────
                if (typo_chance > 0
                        and ch.lower() in NEARBY_KEYS
                        and random.random() < typo_chance):
                    wrong = random.choice(NEARBY_KEYS[ch.lower()])
                    self._emit(wrong)
                    time.sleep(base_delay * random.uniform(TYPO_WRONG_KEY_MIN, TYPO_WRONG_KEY_MAX))
                    self._press_key("backspace")
                    time.sleep(base_delay * random.uniform(TYPO_BACKSPACE_MIN, TYPO_BACKSPACE_MAX))

                # ── Capitalization slip-ups ───────────────────────────────
                if (cap_slips and ch.isalpha() and ch.isupper()
                        and random.random() < CAP_SLIP_CHANCE):
                    self._emit(ch.lower())
                    time.sleep(base_delay * 1.5)
                    self._press_key("backspace")
                    time.sleep(base_delay * 0.7)

                # ── Emit real character ───────────────────────────────────
                self._emit(ch)
                i += 1
                typed += 1
                chars_wpm += 1

                # ── Per-character delay ───────────────────────────────────
                delay = max(0, base_delay + random.uniform(-variation, variation))
                if ch in ".!?":
                    delay += punct_pause
                elif ch in ";:":
                    delay += punct_pause * SEMICOLON_PAUSE_FACTOR
                elif ch == ",":
                    delay += punct_pause * COMMA_PAUSE_FACTOR
                elif ch == " " and word_burst:
                    delay += random.uniform(0, base_delay * 0.5)
                if fatigue:
                    delay += base_delay * (typed / total) * FATIGUE_FACTOR

                time.sleep(delay)

                # ── Burst-mode rest ───────────────────────────────────────
                if burst_mode and ch == " ":
                    words_since_rest += 1
                    if words_since_rest >= next_rest_word_target:
                        rest = random.uniform(BURST_REST_MIN, BURST_REST_MAX)
                        time.sleep(rest)
                        words_since_rest = 0
                        next_rest_word_target = random.randint(
                            BURST_WORDS_MIN, BURST_WORDS_MAX)

                # ── Idle "thinking" pause ─────────────────────────────────
                if idle_pauses:
                    chars_since_idle += 1
                    if chars_since_idle >= next_idle_target:
                        self._set_status("Pausing to think…", "warn")
                        time.sleep(random.uniform(IDLE_PAUSE_MIN, IDLE_PAUSE_MAX))
                        chars_since_idle = 0
                        next_idle_target = random.randint(
                            IDLE_CHARS_MIN, IDLE_CHARS_MAX)

                self._tick(typed, total, chars_wpm, t0)

            self._record_session(typed, time.time() - t0, chars_wpm)
            self._done("Done typing ✓", "ok")

        except pyautogui.FailSafeException:
            self._done("Fail-safe triggered (mouse moved to corner).", "err")
        except Exception as exc:
            self._done(f"Error: {exc}", "err")

    def _record_session(self, chars, seconds, chars_wpm):
        if seconds <= 0:
            return
        wpm = (chars_wpm / CHARS_PER_WORD) / (seconds / 60) if seconds > 1 else 0
        s = self.config.setdefault("stats", {})
        s["lifetime_chars"] = int(s.get("lifetime_chars", 0)) + chars
        s["lifetime_seconds"] = float(s.get("lifetime_seconds", 0.0)) + seconds
        s["lifetime_sessions"] = int(s.get("lifetime_sessions", 0)) + 1
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
        })
        self.config["session_history"] = hist[:20]

        self._persist_state()
        self.after(0, self._refresh_stat_cards)
        self.after(0, self._refresh_history)

    def _press_key(self, key_name):
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
        t = THEMES.get(self._theme_name, THEMES["Midnight"])
        color = {"ok": t["ok"], "warn": t["warn"], "err": t["err"]}.get(kind, t["ok"])
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

    def _tick(self, typed, total, chars_wpm, t0):
        pct = typed / total * 100 if total else 0
        elapsed = time.time() - t0
        wpm = 0.0
        wpm_str = ""
        eta_str = ""
        if elapsed > 1 and chars_wpm > 0:
            wpm = (chars_wpm / CHARS_PER_WORD) / (elapsed / 60)
            wpm_str = f"{wpm:.0f} WPM"
            if pct > 0:
                remaining = elapsed * (100 - pct) / pct
                eta_str = f"ETA  {self._fmt_secs(remaining)}"
        self.after(0, self._tick_main, pct, wpm_str, eta_str,
                   f"Typing… {typed:,} / {total:,} chars ({pct:.0f}%)")

    def _tick_main(self, pct, wpm_str, eta_str, status):
        self._prog.set(pct / 100)
        self._wpm_var.set(wpm_str)
        self._eta_var.set(eta_str)
        self._mini_wpm_var.set(wpm_str.replace(" WPM", "") if wpm_str else "—")
        self._mini_done_var.set(f"{pct:.0f}%")
        self._mini_eta_var.set(eta_str.replace("ETA  ", "") if eta_str else "—")
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
        menu = tk.Menu(self, tearoff=0)
        for name, fn in TRANSFORMS:
            menu.add_command(label=name,
                             command=lambda f=fn, n=name: self._apply_transform(f, n))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

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
        menu = tk.Menu(self, tearoff=0)
        for token, desc in VARIABLES:
            menu.add_command(label=f"{token}   —   {desc}",
                             command=lambda t=token: self._insert_variable(t))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

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
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        if not text.strip():
            messagebox.showwarning("Empty", "Nothing in the editor to preview.")
            return
        if self._vars_expand.get():
            text = expand_variables(text)
        try:
            cfg = {k: float(v.get()) for k, v in self._vars.items()}
        except ValueError:
            messagebox.showerror("Invalid", "Settings must be numeric.")
            return

        win = ctk.CTkToplevel(self)
        win.title("Dry Run — Preview")
        win.geometry("760x500")
        win.transient(self)

        ctk.CTkLabel(
            win, text="🧪  Dry Run preview",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(14, 0))
        ctk.CTkLabel(
            win, text="Types into this window only — no real keystrokes are sent.",
            text_color="gray60",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        mono = "Menlo" if _IS_MAC else "Consolas"
        tb = ctk.CTkTextbox(win, wrap="word",
                            font=ctk.CTkFont(family=mono, size=13))
        tb.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        prog = ctk.CTkProgressBar(win, height=6)
        prog.set(0)
        prog.pack(fill="x", padx=14, pady=(0, 4))

        status = tk.StringVar(value="Running…")
        ctk.CTkLabel(win, textvariable=status, text_color="gray60").pack(
            anchor="w", padx=14, pady=(0, 10))

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
            base = cfg["base_delay"]
            var = cfg["variation"]
            punct = cfg["punct_pause"]
            para = cfg["para_pause"]
            typo = cfg["typo_chance"]
            total = len(text)
            for i, ch in enumerate(text):
                if stop_flag["stop"]:
                    return
                # adjacency typo
                if typo > 0 and ch.lower() in NEARBY_KEYS and random.random() < typo:
                    wrong = random.choice(NEARBY_KEYS[ch.lower()])
                    self.after(0, append, wrong)
                    time.sleep(base * 1.4)
                    self.after(0, backspace)
                    time.sleep(base * 0.8)
                self.after(0, append, ch)
                delay = max(0, base + random.uniform(-var, var))
                if ch in ".!?":
                    delay += punct
                elif ch in ";:":
                    delay += punct * SEMICOLON_PAUSE_FACTOR
                elif ch == ",":
                    delay += punct * COMMA_PAUSE_FACTOR
                elif ch == "\n":
                    delay += para * 0.2
                time.sleep(delay)
                pct = (i + 1) / total
                self.after(0, prog.set, pct)
            self.after(0, status.set, "Done ✓")

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
        dlg = ctk.CTkInputDialog(
            text="Start typing at (HH:MM, 24-hour) or in (e.g. 30s, 5m):",
            title="Schedule",
        )
        val = (dlg.get_input() or "").strip()
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
        w.geometry("260x130+40+40")
        w.attributes("-topmost", True)
        try:
            w.overrideredirect(False)
        except Exception:
            pass
        w.transient(self)
        self._overlay_win = w

        ctk.CTkLabel(
            w, text="⌨  Typing…",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(10, 0))

        self._overlay_pct = tk.StringVar(value="0%")
        self._overlay_wpm = tk.StringVar(value="—")
        self._overlay_eta = tk.StringVar(value="—")

        row = ctk.CTkFrame(w, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(4, 6))
        ctk.CTkLabel(row, textvariable=self._overlay_pct,
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkLabel(row, textvariable=self._overlay_wpm,
                     text_color="gray60").pack(side="right")

        self._overlay_prog = ctk.CTkProgressBar(w, height=8)
        self._overlay_prog.set(0)
        self._overlay_prog.pack(fill="x", padx=14)

        ctk.CTkLabel(w, textvariable=self._overlay_eta, text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(anchor="e",
                                                    padx=14, pady=(4, 10))

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
                self._history_frame, text="No sessions yet.",
                text_color="gray55",
            ).grid(row=0, column=0, sticky="w", padx=10, pady=8)
            return
        for i, h in enumerate(hist):
            row = ctk.CTkFrame(self._history_frame, corner_radius=6)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row, text=h.get("when", ""),
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=10, pady=6)
            ctk.CTkLabel(
                row,
                text=f"{h.get('chars', 0):,} chars · "
                     f"{h.get('wpm', 0):.0f} WPM · "
                     f"{self._fmt_secs(h.get('seconds', 0))}",
                text_color="gray60",
            ).grid(row=0, column=1, sticky="e", padx=10)

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
