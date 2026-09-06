<div align="center">

# Human Typer

**Types text into any window the way a person would — not the way a machine does.**

Drifting rhythm, per-key effort, and mistakes noticed a beat late instead of instantly.
Every one of them corrected before the run ends.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-95%20passing-2C6A4F)](#tests)
[![Platform](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Windows%20%C2%B7%20Linux-6B6B76)](#requirements)
[![License](https://img.shields.io/badge/license-MIT-9C7B3A)](LICENSE)

</div>

---

Some windows will not take a paste. Kiosk forms, remote consoles, exam
browsers, legacy line-of-business apps, terminals over flaky links, demo
recordings where a wall of text appearing at once looks wrong. Human Typer
types the text in for you instead — at a pace and a cadence that looks like
hands on a keyboard.

## The guarantee

> **The text that lands in the other window is byte-identical to the text you
> gave it.**
>
> The engine invents typos, transpositions and missed shifts. It notices each
> one a few characters later, backspaces, and retypes it correctly — because
> that is what people do. But the realism lives in the *timing and the
> keystrokes*, never in the finished document. A property test replays every
> event stream across every profile and asserts the result reconstructs the
> input exactly; a second test proves a correction can never backspace across
> a line break, which in a chat box would send a half-written message.
>
> This tool makes typing look human. It does not make writing look
> human-written, and it has no mode that does.

## What makes it look human

Most typing simulators pick a delay and add random jitter. That is the one
thing real typing never does — the jitter is independent from key to key,
which reads as a machine adding noise. Four things fix it.

**Rhythm that drifts.** Speed wanders in runs lasting seconds, not
per-keystroke. The engine walks a mean-reverting process in log space, so
cadence has texture and still comes back to your set pace. The test suite
checks the autocorrelation is above 0.5 — that it is a rhythm rather than
noise.

**Keys that cost different amounts.** A pinky reach to `p` is slower than `a`
on the home row. `?` costs a shift. The single largest effect in real
keystroke timing is the same finger twice in a row — `de`, `un`, `ol` — and
the largest saving is alternating hands. The engine models finger, row,
hand-alternation and shift, then multiplies your base delay by the result.

**Mistakes noticed late.** Every other typing simulator catches its typo on
the very next keystroke. Nobody does that. Here a slip is followed by one to
eight more characters before your eyes catch up, then a pause, then the
backspaces. It is the single clearest tell between a person and a script, and
it is a slider.

**Warm-up, fatigue, rests and thinking.** The first lines come out cold. Long
documents slow down. Bursts of a few words are followed by a breath, and a new
sentence sometimes waits while you compose it.

### Realism profiles

Speed presets set *how fast*. Profiles set *how human*.

| Profile | Character | Typo rate | Notice delay |
|---|---|---|---|
| **Robotic** | Metronome. No mistakes, no drift. | 0 | — |
| **Steady** | A fast touch-typist on a good day. | 0.4% | 0–1 chars |
| **Natural** | The default. Drifting cadence, caught typos, thinking beats. | 1.2% | 0–3 chars |
| **Hurried** | Slightly ahead of yourself. More slips, noticed later. | 2.8% | 0–5 chars |
| **Thoughtful** | Composing as you go. Long pauses, stalls on hard words. | 0.8% | 0–2 chars |

Every switch behind them is individually adjustable.

## Honest estimates

The old time estimate multiplied character count by the base delay. That
ignored per-key effort, drift, rests and the seconds spent correcting
mistakes, so it ran badly short as soon as realism was switched on. The
estimate now *plans the document for real* and adds up the pauses:

| Profile | Actual | New estimate | Old formula |
|---|---:|---:|---:|
| Robotic | 83.2 s | 83.4 s (+0.2%) | 83.7 s (+0.6%) |
| Steady | 99.0 s | 96.7 s (−2.3%) | 83.7 s (−15.4%) |
| Natural | 152.5 s | 155.7 s (+2.1%) | 83.7 s (**−45.1%**) |
| Hurried | 149.6 s | 149.9 s (+0.2%) | 83.7 s (**−44.0%**) |
| Thoughtful | 150.8 s | 148.0 s (−1.9%) | 83.7 s (**−44.5%**) |

<sub>Same 1,150-character passage, 0.08 s base delay, 60 seeds per profile. Reproduce it yourself — the engine is importable and needs no GUI.</sub>

While a run is going, the remaining time counts the pauses still left in the
plan rather than extrapolating from how the first line went, so it does not
lurch when the run hits a thinking pause. Time spent paused is excluded from
the speed figure.

## Documents you can open

Open pulls the **text** out of a document so it can be typed somewhere else.
Formatting is not carried across — a keyboard produces characters, so bold,
headings, tables, images and fonts have no keystroke equivalent and are left
behind.

| Format | Notes |
|---|---|
| `.txt` `.md` `.csv` `.json` `.py` … | Read directly, with encoding fallback |
| `.docx` | Word. Paragraph breaks kept; **tracked deletions are not imported** |
| `.odt` | OpenDocument / LibreOffice |
| `.rtf` | Control words and font tables stripped |
| `.html` `.htm` | Tags stripped, block elements become paragraphs |
| `.pdf` | Only if `pypdf` is installed — see [requirements](#requirements) |

`.docx`, `.odt`, `.rtf` and `.html` are read with the standard library alone —
importing a Word document adds no dependency. Archive members are size-capped
before extraction, so a zip bomb cannot exhaust memory.

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python human-type.py
```

1. **Compose** — open a document, pull the clipboard in, or just type.
2. **Behaviour** — pick a speed and a realism profile.
3. **Start typing**, then switch to the target window before the countdown ends.

`F5` starts · `F6` pauses and resumes · `Esc` stops. Moving the mouse to the
top-left corner of the screen aborts immediately, at any moment.

## The interface

| Page | What lives there |
|---|---|
| **Compose** | The editor, document import, find & replace, text transforms, `{variables}`, and a live analysis panel |
| **Behaviour** | Speed presets, realism profile, the individual realism switches, timing fields, and how newlines are delivered |
| **Library** | Snippets — built-in and your own |
| **Insights** | Lifetime and session totals, accuracy, and a log of recent runs |
| **About** | Supported formats, variables, shortcuts and the guarantees |

Light, dark, or **Auto** to follow the operating system. Light is warm paper
and deep brass; dark is genuinely black, with neutral greys so nothing reads
as navy. Six restrained accents, gold by default.

Every colour is declared as a light/dark pair at the point of definition, so
there is no way to add one and forget the dark half — and
`tests/test_theme.py` holds every text pairing to WCAG AA in both themes,
which is what keeps a gold accent readable instead of merely pretty.

### The cadence meter

The bars under **THIS RUN** in the sidebar are the one ornament in the app,
and they are made of real data: each bar is the gap between two keystrokes on
a logarithmic scale. Idle, it shows the engine's own rhythm for a sample
phrase. During a run it shows the gaps actually being executed — and the tall
ones are the moments it notices a typo and stops to fix it.

### Dry run

Dry run executes the exact event stream that would go to your keyboard into a
preview window instead. Same mistakes, same corrections, same pacing — a
rehearsal rather than an approximation of one.

### Newlines

How a newline is delivered matters more than it sounds, because in a chat box
`Enter` sends the message.

| Mode | Sends | Use for |
|---|---|---|
| **Press Enter** | A real Enter | Documents, editors, forms |
| **Shift + Enter** | A soft line break | Slack, Discord, chat boxes |
| **Skip (join)** | Nothing | When the text must arrive as one continuous run |

## Settings reference

| Setting | Default | Meaning |
|---|---|---|
| Start delay | `5 s` | Time to switch to the target window |
| Base delay | `0.08 s` | Average time per character, before effort and drift |
| Variation | `0.03 s` | Random jitter per keystroke |
| Punctuation pause | `0.25 s` | After `. ! ?`; 70% of it after `; :`, 40% after `,` |
| Paragraph pause | `0.80 s` | On a blank line |
| Typo chance | `0.04` | Probability of an adjacent-key slip per character |
| Rhythm drift | `0.11` | Strength of the slow speed-up/slow-down walk |
| Notice delay | `3 chars` | How far past a mistake you get before spotting it |

### Speed presets

| Preset | Base delay | Variation | Punctuation | Typo chance |
|---|---|---|---|---|
| Slow | 0.15 s | ± 0.07 s | 0.40 s | 2% |
| Normal | 0.08 s | ± 0.03 s | 0.25 s | 4% |
| Fast | 0.04 s | ± 0.02 s | 0.12 s | 2% |
| Blazing | 0.01 s | ± 0.005 s | 0.04 s | 0% |

### What the numbers mean

- **Speed** is net WPM: correct characters ÷ 5, over elapsed typing time —
  including whatever the corrections cost, and excluding time spent paused.
- **Accuracy** is correct characters ÷ characters actually struck. A run with
  no simulated mistakes is 100%.
- **Remaining** comes from the pauses still left in the plan, adjusted by how
  far behind the plan the machine is actually running.

## Tests

```bash
make test          # everything
make test-engine   # no display and no dependencies required
```

| Suite | Tests | Covers |
|---|---:|---|
| `tests/test_realism.py` | 30 | 62,119 individual checks — reconstruction, backspace safety, the effort model, rhythm autocorrelation, determinism |
| `tests/test_docimport.py` | 26 | Real `.docx`/`.odt` archives built in memory, RTF, HTML, encodings, zip bombs |
| `tests/test_theme.py` | 11 | Every text pairing against WCAG AA, in both themes and all six accents |
| `tests/test_ui.py` | 28 | Every page and dialog builds, nothing falls back to the toolkit's default palette, nothing is clipped out of its own window, settings round-trip |

`realism.py` and `docimport.py` import nothing outside the standard library,
so the engine suites run anywhere Python does — no GUI, no keyboard, no
network.

## Requirements

Python 3.9 or newer.

| Package | Why |
|---|---|
| [`customtkinter`](https://customtkinter.tomschimansky.com/) | The interface |
| [`pyautogui`](https://pyautogui.readthedocs.io/) | Keystroke injection on Windows and Linux, plus the fail-safe |
| [`pynput`](https://pynput.readthedocs.io/) | Keystroke injection on macOS — `pyautogui` mis-types shifted and Unicode characters there |
| [`pyperclip`](https://pyperclip.readthedocs.io/) | Clipboard import and the Unicode fallback |
| `pypdf` *(optional)* | Only for opening PDFs |

**macOS** — grant Accessibility permission to whatever launches the app
(System Settings → Privacy & Security → Accessibility). Without it no
keystrokes are sent at all.

**Linux** — `pyperclip` may need `xclip` or `xsel` (`sudo apt install xclip`).

## Project layout

```
human-type.py      The application
realism.py         Typing realism engine — pure, no GUI, no keyboard
docimport.py       Document text extraction — standard library only
theme.py           Design system: colours, type, spacing, widget recipes
tests/             Engine, document, palette and interface suites
tools/             Chart, site and screenshot generators
docs/              The project site (generated — edit _template.html)
```

The realism engine is a planner: it turns text plus a style into a stream of
`Char`, `Key`, `Pause` and `Note` events, and the app just executes them. That
separation is what lets the interesting half be tested without a keyboard, and
what lets the dry run be a true rehearsal.

## License

[MIT](LICENSE)
