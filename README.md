<div align="center">

# 🤖⌨️ human-type

**Make any machine type like a human.**

A Python desktop app that types your text into any window at a fully adjustable, human-like speed —  
complete with realistic typos, natural pauses, fatigue, and a polished dark/light GUI.

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#)
[![Dependencies](https://img.shields.io/badge/deps-pyautogui%20%7C%20pynput%20%7C%20pyperclip%20%7C%20customtkinter-blue)](#requirements)

</div>

---

## ✨ Features

### 🎛️ Typing Realism
| Feature | Description |
|---|---|
| **Speed Presets** | One-click **Slow / Normal / Fast / Blazing** profiles to instantly tune all timing settings |
| **Typo Simulation** | Randomly hits a nearby key then backspaces — powered by a full keyboard-adjacency map |
| **Word-Burst Variation** | Micro-pauses between words for a natural typing cadence |
| **Fatigue Simulation** | Gradually slows typing the further through the text you get |
| **Punctuation Pauses** | Separate configurable delays after `.!?`, `;:`, and `,` |
| **Paragraph Pauses** | Extra pause on blank lines to mimic reading between paragraphs |

### 🖥️ UI & Control
| Feature | Description |
|---|---|
| **Dark / Light Mode** | One-click theme toggle — full dark VSCode-style palette included |
| **Pause / Resume** | Suspend mid-text and continue from exactly where you left off |
| **Progress Bar** | Live fill with `X / Y chars (N%)` updated every keystroke |
| **Live WPM Counter** | Real-time words-per-minute displayed in the action bar |
| **Countdown Timer** | Status bar counts down seconds before typing begins so you can switch windows |
| **Char & Word Count** | Live `1,234 chars · 220 words` label updates as you edit |

### 📥 Input Sources
| Feature | Description |
|---|---|
| **Load File** | Open `.txt` or `.md` files directly |
| **Import Clipboard** | Pull clipboard contents into the editor in one click |
| **Manual Input** | Type or paste directly into the built-in editor |
| **Unicode Fallback** | Non-ASCII characters are clipboard-pasted transparently |

---

## 🚀 Quick Start

### 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### 2 — Run

```bash
python human-type.py
```

### 3 — Type away

1. **Load** a `.txt`/`.md` file, **import** from clipboard, or type directly in the editor.
2. Pick a **preset** (or tweak individual settings).
3. Click **▶ Start Typing**, then switch to your target window before the countdown ends.
4. Use **⏸ Pause** / **▶ Resume** any time, or **⏹ Stop** to abort.

---

## ⚙️ Settings Reference

| Setting | Default | Description |
|---|---|---|
| `Start delay` | `5 s` | Seconds to wait before typing begins (use this to switch windows) |
| `Base delay / char` | `0.08 s` | Average time spent on each character |
| `Variation ±` | `0.03 s` | Random jitter added/subtracted from each keystroke delay |
| `Punctuation pause` | `0.25 s` | Extra pause after sentence-ending punctuation (`.!?`) |
| `Paragraph pause` | `0.80 s` | Extra pause on blank lines between paragraphs |
| `Typo chance` | `0.04` | Probability (0–1) that any given character triggers a realistic typo |
| `Newlines → Enter` | off | Press the Enter key for each newline in the text |
| `Word-burst variation` | on | Add micro-pauses at word boundaries |
| `Fatigue` | off | Gradually increase delay as typing progresses |

### Speed Presets at a Glance

| Preset | Delay | Variation | Punct pause | Typo chance |
|---|---|---|---|---|
| 🐢 Slow | 0.15 s | ± 0.07 s | 0.40 s | 2 % |
| 🚶 Normal | 0.08 s | ± 0.03 s | 0.25 s | 4 % |
| 🏃 Fast | 0.04 s | ± 0.02 s | 0.12 s | 2 % |
| ⚡ Blazing | 0.01 s | ± 0.005 s | 0.04 s | 0 % |

---

## 📋 Requirements

- Python 3.8+
- [`pyautogui`](https://pyautogui.readthedocs.io/) — keyboard/mouse automation (Windows/Linux)
- [`pynput`](https://pynput.readthedocs.io/) — keyboard injection on macOS (handles uppercase, symbols, all Unicode)
- [`pyperclip`](https://pyperclip.readthedocs.io/) — clipboard access
- [`customtkinter`](https://customtkinter.tomschimansky.com/) — modern UI toolkit

Install with:
```bash
pip install -r requirements.txt
```

---

## ⚠️ Notes

- **PyAutoGUI fail-safe** is enabled by default — move your mouse to the **top-left corner** at any time to immediately halt typing.
- On **macOS**:
  - Grant **Accessibility** permissions to Terminal / your IDE (System Settings → Privacy & Security → Accessibility). **This is required** — without it, no keystrokes will be sent.
  - The app uses `pynput` (CoreGraphics events) on macOS for reliable typing of all characters including uppercase letters, symbols, and Unicode.
- On **Linux**, `pyperclip` may require `xclip` or `xdotool` (`sudo apt install xclip`).

---

## 📄 License

[MIT](LICENSE) — free to use, modify, and distribute.
