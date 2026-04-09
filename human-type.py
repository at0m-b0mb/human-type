import platform
import threading
import time
import random
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pyautogui
import pyperclip

# ---------------------------------------------------------------------------
# macOS compatibility — pynput is more reliable than pyautogui on macOS
# because it uses CoreGraphics events that correctly handle shift-modified
# keys (uppercase letters, symbols, etc.).  pyautogui.write() silently drops
# or mis-types many characters on macOS regardless of Accessibility settings.
# ---------------------------------------------------------------------------
_IS_MAC = platform.system() == "Darwin"
# macOS uses Cmd+V; all other platforms use Ctrl+V for paste
_PASTE_HOTKEY = ("command", "v") if _IS_MAC else ("ctrl", "v")
# Per-character interval for pyautogui (non-Mac path only)
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
# Speed presets
# ---------------------------------------------------------------------------
PRESETS = {
    "Slow":    {"base_delay": 0.15, "variation": 0.07, "punct_pause": 0.40, "typo_chance": 0.02, "para_pause": 1.2},
    "Normal":  {"base_delay": 0.08, "variation": 0.03, "punct_pause": 0.25, "typo_chance": 0.04, "para_pause": 0.8},
    "Fast":    {"base_delay": 0.04, "variation": 0.02, "punct_pause": 0.12, "typo_chance": 0.02, "para_pause": 0.4},
    "Blazing": {"base_delay": 0.01, "variation": 0.005, "punct_pause": 0.04, "typo_chance": 0.00, "para_pause": 0.1},
}

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

# Keyboard-adjacency map used for realistic typo generation
NEARBY_KEYS = {
    "a": "sqwz",  "b": "vghn",  "c": "xdfv",  "d": "serfcx", "e": "wsdr",
    "f": "drtgvc","g": "ftyhbv","h": "gyujnb", "i": "ujko",   "j": "huikmn",
    "k": "jiolm", "l": "kop",   "m": "njk",    "n": "bhjm",   "o": "iklp",
    "p": "ol",    "q": "wa",    "r": "edft",   "s": "awedxz", "t": "rfgy",
    "u": "yhji",  "v": "cfgb",  "w": "qase",   "x": "zsdc",   "y": "tghu",
    "z": "asx",
}


class HumanTyperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Human Typer")
        self.geometry("920x720")
        self.minsize(760, 580)

        # Start in dark mode
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._dark = True

        self._stop = False
        self._pause = threading.Event()
        self._pause.set()   # not paused initially

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.01

        self._build_ui()

        # Warn if pynput failed to load on macOS — typing WILL be broken
        if _IS_MAC and _MAC_KBD is None:
            self.after(500, lambda: messagebox.showwarning(
                "macOS Setup Issue",
                "pynput could not be loaded, so typing may not work correctly "
                "on macOS.\n\n"
                f"Error: {_MAC_PYNPUT_ERROR}\n\n"
                "Run:  pip install pynput\n"
                "then restart the app.",
            ))

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(3, weight=1)   # text area expands

        # ── Header ──────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="⌨   Human Typer",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self._theme_btn = ctk.CTkButton(
            hdr, text="☀  Light Mode", width=140,
            fg_color="transparent", border_width=1,
            command=self._toggle_theme,
        )
        self._theme_btn.grid(row=0, column=2, sticky="e")

        ctk.CTkLabel(
            hdr,
            text="Type text naturally into any window — load a file, paste, or type below.",
            text_color="gray60",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # ── Toolbar ─────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(outer, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        bar.grid_columnconfigure(5, weight=1)

        for idx, (icon, label, cmd) in enumerate([
            ("📂", "Load File",        self.load_file),
            ("📋", "Import Clipboard", self.import_clipboard),
            ("🗑", "Clear",            self.clear_text),
        ]):
            ctk.CTkButton(
                bar, text=f"{icon}  {label}", width=148, command=cmd,
            ).grid(row=0, column=idx, padx=(0, 8))

        self._count_var = tk.StringVar(value="0 chars")
        ctk.CTkLabel(
            bar, textvariable=self._count_var, text_color="gray60",
        ).grid(row=0, column=5, sticky="e")

        # ── Settings ────────────────────────────────────────────────────────
        sf = ctk.CTkFrame(outer, corner_radius=10)
        sf.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        sf.grid_columnconfigure((1, 3, 5), weight=1)

        ctk.CTkLabel(
            sf, text="⚙   Typing Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=14, pady=(12, 8))

        # Preset segmented button
        pr = ctk.CTkFrame(sf, fg_color="transparent")
        pr.grid(row=1, column=0, columnspan=6, sticky="w", padx=14, pady=(0, 10))
        ctk.CTkLabel(pr, text="Preset:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 10))
        self._preset_seg = ctk.CTkSegmentedButton(
            pr, values=list(PRESETS.keys()), command=self._apply_preset,
        )
        self._preset_seg.pack(side="left")
        self._preset_seg.set("Normal")

        # Numeric fields arranged 3-per-row
        _fields = [
            ("Start delay (s):",      "start_delay", "5"),
            ("Base delay/char (s):",  "base_delay",  "0.08"),
            ("Variation ± (s):",      "variation",   "0.03"),
            ("Punct pause (s):",      "punct_pause", "0.25"),
            ("Para pause (s):",       "para_pause",  "0.8"),
            ("Typo chance (0–1):",    "typo_chance", "0.04"),
        ]
        self._vars = {}
        for idx, (label, name, default) in enumerate(_fields):
            r = 2 + idx // 3
            cb = (idx % 3) * 2
            ctk.CTkLabel(sf, text=label, font=ctk.CTkFont(size=12)).grid(
                row=r, column=cb, sticky="w", padx=(14, 4), pady=4)
            var = tk.StringVar(value=default)
            self._vars[name] = var
            ctk.CTkEntry(sf, textvariable=var, width=90).grid(
                row=r, column=cb + 1, sticky="w", padx=(0, 18), pady=4)

        # Toggle switches
        sw = ctk.CTkFrame(sf, fg_color="transparent")
        sw.grid(row=4, column=0, columnspan=6, sticky="w", padx=14, pady=(6, 14))
        self._enter_var   = tk.BooleanVar(value=False)
        self._burst_var   = tk.BooleanVar(value=True)
        self._fatigue_var = tk.BooleanVar(value=False)
        for text, var in [
            ("Newlines → Enter",       self._enter_var),
            ("Word-burst variation",   self._burst_var),
            ("Fatigue (slow over time)", self._fatigue_var),
        ]:
            ctk.CTkSwitch(
                sw, text=text, variable=var, onvalue=True, offvalue=False,
            ).pack(side="left", padx=(0, 24))

        # ── Text area ───────────────────────────────────────────────────────
        mono = "Menlo" if _IS_MAC else "Consolas"
        self._tb = ctk.CTkTextbox(
            outer, wrap="word",
            font=ctk.CTkFont(family=mono, size=12),
            corner_radius=8,
        )
        self._tb.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        self._tb._textbox.bind("<KeyRelease>", self._update_count)

        # ── Progress bar ────────────────────────────────────────────────────
        self._prog = ctk.CTkProgressBar(outer, height=10, corner_radius=5)
        self._prog.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self._prog.set(0)

        # ── Action bar ──────────────────────────────────────────────────────
        ab = ctk.CTkFrame(outer, fg_color="transparent")
        ab.grid(row=5, column=0, sticky="ew", pady=(10, 0))

        self._start_btn = ctk.CTkButton(
            ab, text="▶  Start Typing", width=148,
            fg_color="#1f6feb", hover_color="#388bfd",
            command=self.start_typing,
        )
        self._start_btn.pack(side="left")

        self._pause_btn = ctk.CTkButton(
            ab, text="⏸  Pause", width=110,
            fg_color="transparent", border_width=1, state="disabled",
            command=self.toggle_pause,
        )
        self._pause_btn.pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            ab, text="⏹  Stop", width=90,
            fg_color="transparent", border_width=1,
            command=self.stop_typing,
        ).pack(side="left", padx=(8, 0))

        self._wpm_var = tk.StringVar(value="")
        ctk.CTkLabel(
            ab, textvariable=self._wpm_var, text_color="gray60",
        ).pack(side="right")

        # ── Status bar ──────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(
            outer, textvariable=self._status_var,
            anchor="w", text_color="gray60",
            font=ctk.CTkFont(size=11),
        ).grid(row=6, column=0, sticky="ew", pady=(6, 0))

    # -----------------------------------------------------------------------
    # Theme toggle
    # -----------------------------------------------------------------------
    def _toggle_theme(self):
        self._dark = not self._dark
        ctk.set_appearance_mode("dark" if self._dark else "light")
        self._theme_btn.configure(
            text="☀  Light Mode" if self._dark else "🌙  Dark Mode")

    # -----------------------------------------------------------------------
    # Presets
    # -----------------------------------------------------------------------
    def _apply_preset(self, name):
        p = PRESETS[name]
        self._vars["base_delay"].set(str(p["base_delay"]))
        self._vars["variation"].set(str(p["variation"]))
        self._vars["punct_pause"].set(str(p["punct_pause"]))
        self._vars["typo_chance"].set(str(p["typo_chance"]))
        self._vars["para_pause"].set(str(p["para_pause"]))
        self._status_var.set(f"Preset applied: {name}")

    # -----------------------------------------------------------------------
    # Text helpers
    # -----------------------------------------------------------------------
    def load_file(self):
        path = filedialog.askopenfilename(
            title="Select a text file",
            filetypes=[("Text files", "*.txt"), ("Markdown", "*.md"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self._tb.delete("1.0", tk.END)
            self._tb.insert("1.0", text)
            self._update_count()
            self._status_var.set(f"Loaded: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("File Error", f"Could not read file:\n{exc}")

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
            self._status_var.set("Imported from clipboard.")
        except Exception as exc:
            messagebox.showerror("Clipboard Error",
                                 f"Could not read clipboard:\n{exc}")

    def clear_text(self):
        self._tb.delete("1.0", tk.END)
        self._update_count()
        self._status_var.set("Text cleared.")

    def _update_count(self, _event=None):
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        words = len(text.split()) if text.strip() else 0
        self._count_var.set(f"{len(text):,} chars · {words:,} words")

    # -----------------------------------------------------------------------
    # Typing control
    # -----------------------------------------------------------------------
    def stop_typing(self):
        self._stop = True
        self._pause.set()   # unblock if paused so the thread can exit
        self._status_var.set("Stopping…")

    def toggle_pause(self):
        if self._pause.is_set():
            self._pause.clear()
            self._pause_btn.configure(text="▶  Resume")
            self._status_var.set("Paused. Click Resume to continue.")
        else:
            self._pause.set()
            self._pause_btn.configure(text="⏸  Pause")
            self._status_var.set("Resumed.")

    def start_typing(self):
        text = self._tb.get("1.0", tk.END).rstrip("\n")
        if not text.strip():
            messagebox.showwarning("No Text",
                                   "Please load or paste text first.")
            return

        try:
            cfg = {k: float(v.get()) for k, v in self._vars.items()}
        except ValueError:
            messagebox.showerror("Invalid Settings",
                                 "All settings must be numeric.")
            return

        self._stop = False
        self._pause.set()
        self._prog.set(0)
        self._wpm_var.set("")
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal", text="⏸  Pause")

        threading.Thread(
            target=self._run,
            args=(text, cfg,
                  self._enter_var.get(),
                  self._fatigue_var.get(),
                  self._burst_var.get()),
            daemon=True,
        ).start()

    # -----------------------------------------------------------------------
    # Core typing loop (runs in background thread)
    # -----------------------------------------------------------------------
    def _run(self, text, cfg, press_enter, fatigue, word_burst):
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
                    self._done("Stopped.")
                    return
                self._set_status(
                    f"Starting in {remaining}s — switch to target window now…")
                time.sleep(1)
            frac = start_delay - int(start_delay)
            if frac > 0:
                time.sleep(frac)

            total     = len(text)
            typed     = 0
            chars_wpm = 0
            t0        = time.time()
            i         = 0

            while i < len(text):
                if self._stop:
                    self._done("Stopped.")
                    return
                self._pause.wait()   # block here when paused

                ch = text[i]

                # ── Paragraph pause (blank line = \n\n) ──────────────────
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

                # ── Plain newline ────────────────────────────────────────
                if ch == "\n":
                    if press_enter:
                        self._press_key("enter")
                    typed += 1
                    self._tick(typed, total, chars_wpm, t0)
                    time.sleep(max(0, base_delay + random.uniform(-variation, variation)))
                    i += 1
                    continue

                # ── Typo simulation ──────────────────────────────────────
                if (typo_chance > 0
                        and ch.lower() in NEARBY_KEYS
                        and random.random() < typo_chance):
                    wrong = random.choice(NEARBY_KEYS[ch.lower()])
                    self._emit(wrong)
                    time.sleep(base_delay * random.uniform(TYPO_WRONG_KEY_MIN, TYPO_WRONG_KEY_MAX))
                    self._press_key("backspace")
                    time.sleep(base_delay * random.uniform(TYPO_BACKSPACE_MIN, TYPO_BACKSPACE_MAX))

                # ── Emit the real character ──────────────────────────────
                self._emit(ch)
                i         += 1
                typed     += 1
                chars_wpm += 1

                # ── Per-character delay ──────────────────────────────────
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
                self._tick(typed, total, chars_wpm, t0)

            self._done("Done typing ✓")

        except pyautogui.FailSafeException:
            self._done("Fail-safe triggered (mouse moved to corner).")
        except Exception as exc:
            self._done(f"Error: {exc}")

    def _press_key(self, key_name):
        """Press a special key (enter, backspace) cross-platform."""
        if _IS_MAC and _MAC_KBD is not None:
            key_map = {"enter": _Key.enter, "backspace": _Key.backspace}
            k = key_map.get(key_name)
            if k:
                _MAC_KBD.press(k)
                _MAC_KBD.release(k)
                return
        pyautogui.press(key_name)

    def _set_status(self, msg):
        """Thread-safe status bar update."""
        self.after(0, self._status_var.set, msg)

    def _emit(self, ch):
        """Type one character into the active window.

        On macOS we use pynput's CoreGraphics backend which correctly handles
        shift-modified keys (uppercase, symbols, etc.).  pyautogui.write()
        silently drops or garbles many characters on macOS.

        On other platforms we keep pyautogui.write() for broad compatibility.
        Non-ASCII characters fall back to clipboard paste on all platforms.
        """
        if _IS_MAC:
            if _MAC_KBD is not None:
                # pynput handles the full Unicode range including shifted chars
                _MAC_KBD.type(ch)
            else:
                # pynput unavailable — clipboard paste is the most reliable
                # fallback on macOS (works for all characters)
                saved = pyperclip.paste()
                pyperclip.copy(ch)
                pyautogui.hotkey(*_PASTE_HOTKEY)
                time.sleep(0.05)
                pyperclip.copy(saved)
        elif ch.isascii() and ch.isprintable():
            pyautogui.write(ch, interval=_WRITE_INTERVAL)
        else:
            # Non-ASCII fallback on non-Mac: clipboard paste
            saved = pyperclip.paste()
            pyperclip.copy(ch)
            pyautogui.hotkey(*_PASTE_HOTKEY)
            time.sleep(0.05)   # let the paste land before restoring clipboard
            pyperclip.copy(saved)

    def _tick(self, typed, total, chars_wpm, t0):
        pct = typed / total * 100 if total else 0
        elapsed = time.time() - t0
        wpm_str = ""
        if elapsed > 1 and chars_wpm > 0:
            wpm = (chars_wpm / CHARS_PER_WORD) / (elapsed / 60)
            wpm_str = f"{wpm:.0f} WPM"
        # Route all UI updates through the main thread
        self.after(0, self._tick_main, pct, wpm_str,
                   f"Typing… {typed:,} / {total:,} chars ({pct:.0f}%)")

    def _tick_main(self, pct, wpm_str, status):
        # CTkProgressBar expects 0.0–1.0
        self._prog.set(pct / 100)
        self._wpm_var.set(wpm_str)
        self._status_var.set(status)

    def _done(self, msg):
        self.after(0, self._done_main, msg)

    def _done_main(self, msg):
        self._status_var.set(msg)
        if "Done" in msg:
            self._prog.set(1.0)
        self._pause_btn.configure(state="disabled", text="⏸  Pause")
        self._start_btn.configure(state="normal")


if __name__ == "__main__":
    app = HumanTyperApp()
    app.mainloop()
