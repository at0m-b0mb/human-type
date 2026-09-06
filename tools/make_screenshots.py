#!/usr/bin/env python3
"""
Capture the README and site screenshots.

Runs the real app against a fixed demo profile — never your own config, your
own draft or your own statistics — so the images are reproducible and contain
nothing personal.

    python3 tools/make_screenshots.py                 # light theme
    python3 tools/make_screenshots.py --dark          # dark theme
    python3 tools/make_screenshots.py --accent Emerald

macOS needs Screen Recording permission for whatever runs this
(System Settings -> Privacy & Security -> Screen & System Audio Recording).
Without it macOS refuses the capture and this says so rather than writing
blank files.
"""

import argparse
import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "assets", "screenshots")
sys.path.insert(0, ROOT)

WIDTH, HEIGHT = 1320, 880
ORIGIN_X, ORIGIN_Y = 40, 50

DEMO_TEXT = """Dear Mr Whitfield,

Thank you for sending through the revised schedule. I have read it against the
original scope and the two line up on everything except the survey window,
which now closes a fortnight earlier than we had planned for.

That is workable, but it means the access arrangements need confirming this
week rather than next. Could you let me know whether the Tuesday slot is still
available? I would rather move our end than compress the survey itself.

Kind regards,
"""

DEMO_CONFIG = {
    "dark_mode": False,
    "draft": DEMO_TEXT,
    "realism_profile": "Natural",
    "newline_mode": "Press Enter",
    "rhythm_drift": 0.11,
    "notice_max": 3,
    "stats": {
        "lifetime_chars": 148920, "lifetime_sessions": 63,
        "lifetime_seconds": 21640.0, "best_wpm": 96.2,
        "lifetime_keystrokes": 156301, "lifetime_corrections": 3441,
    },
    "session_history": [
        {"when": "2026-04-18 09:24", "chars": 1095, "seconds": 155.1,
         "wpm": 84.3, "accuracy": 97.8, "corrections": 24},
        {"when": "2026-04-17 16:02", "chars": 2806, "seconds": 205.4,
         "wpm": 81.9, "accuracy": 97.2, "corrections": 63},
        {"when": "2026-04-17 11:48", "chars": 640, "seconds": 88.2,
         "wpm": 87.1, "accuracy": 98.6, "corrections": 9},
        {"when": "2026-04-16 14:31", "chars": 1082, "seconds": 149.0,
         "wpm": 86.8, "accuracy": 98.1, "corrections": 20},
    ],
}

SHOTS = [
    ("Compose",   "01-compose.png"),
    ("Behaviour", "02-behaviour.png"),
    ("Library",   "03-library.png"),
    ("Insights",  "04-insights.png"),
    ("About",     "05-about.png"),
]


def check_permission():
    if sys.platform != "darwin":
        return
    if shutil.which("screencapture") is None:
        sys.exit("screencapture not found — is this macOS?")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        probe = fh.name
    os.unlink(probe)
    subprocess.run(["screencapture", "-x", probe],
                   capture_output=True, check=False)
    if not os.path.exists(probe) or os.path.getsize(probe) == 0:
        sys.exit(
            "macOS refused the screen capture.\n\n"
            "Grant Screen Recording to whatever is running this, in\n"
            "System Settings -> Privacy & Security -> Screen & System Audio "
            "Recording,\nthen run this again.")
    os.unlink(probe)


def load_app():
    spec = importlib.util.spec_from_file_location(
        "humantype", os.path.join(ROOT, "human-type.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["humantype"] = module
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dark", action="store_true", help="capture the dark theme")
    ap.add_argument("--accent", default="Gold", help="accent name")
    ap.add_argument("--suffix", default="", help="appended to each filename")
    args = ap.parse_args()

    check_permission()
    os.makedirs(OUT, exist_ok=True)

    module = load_app()
    tmp = tempfile.TemporaryDirectory()
    config = dict(DEMO_CONFIG, dark_mode=args.dark, theme=args.accent)
    path = os.path.join(tmp.name, "demo.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    module.CONFIG_PATH = __import__("pathlib").Path(path)

    app = module.HumanTyperApp()
    app.geometry("%dx%d+%d+%d" % (WIDTH, HEIGHT, ORIGIN_X, ORIGIN_Y))
    app.update()
    app.lift()
    app.focus_force()
    app.update()
    time.sleep(1.0)

    region = "%d,%d,%d,%d" % (ORIGIN_X, ORIGIN_Y, WIDTH, HEIGHT)
    for page, filename in SHOTS:
        app._show_page(page)
        for _ in range(4):
            app.update_idletasks()
            app.update()
            time.sleep(0.15)
        time.sleep(0.4)
        stem, ext = os.path.splitext(filename)
        target = os.path.join(OUT, stem + args.suffix + ext)
        subprocess.run(["screencapture", "-x", "-R", region, target], check=True)
        print("wrote %s  (%.0f KB)"
              % (os.path.relpath(target, ROOT), os.path.getsize(target) / 1024))

    app._on_close()
    tmp.cleanup()


if __name__ == "__main__":
    main()
