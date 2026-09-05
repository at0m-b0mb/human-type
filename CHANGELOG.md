# Changelog

## 1.0.0

The interface was rebuilt from scratch and the typing engine was rewritten as
a testable planner.

### The guarantee

- Every simulated mistake is now provably corrected. A property test replays
  the event stream for every profile, every seed and an adversarial corpus,
  and asserts the result reconstructs the input byte for byte.
- A correction can never backspace across a line break — in a chat box that
  would send a half-written message. Tested separately.

### Typing realism

- **New engine** (`realism.py`): a planner that turns text plus a style into a
  stream of `Char`, `Key`, `Pause` and `Note` events. Pure standard library,
  no GUI and no keyboard, so it is testable and the dry run can replay exactly
  what the keyboard would receive.
- **Correlated rhythm drift** replaces per-key white noise. Speed now wanders
  in runs of seconds and reverts to your set pace.
- **Per-key effort model**: finger, row, hand alternation and shift. Same-finger
  bigrams are the largest penalty; alternating hands the largest saving.
- **Mistakes noticed late** — one to eight characters after the slip, then a
  pause, then the correction. Previously every typo was caught instantly,
  which is the clearest sign a machine is typing.
- **New mistake types**: transposed letters, doubled and dropped letters.
- **Warm-up**, sentence-composition pauses and stalls before long words.
- **Five realism profiles** — Robotic, Steady, Natural, Hurried, Thoughtful —
  separate from the four speed presets.

### Measurement

- Time estimates are now produced by planning the document rather than by a
  formula, which was running up to 45% short with realism enabled. Estimates
  are now within roughly 2%.
- Remaining time counts the pauses still left in the plan instead of
  extrapolating from the opening line.
- Time spent paused no longer counts against your speed.
- **Accuracy** and **keystrokes** are tracked and reported per run and
  lifetime.
- Runs shorter than a second are no longer recorded as 0 WPM.

### Documents

- **Open any document**, not just `.txt` and `.md`: `.docx`, `.odt`, `.rtf`,
  `.html` and — with `pypdf` installed — `.pdf`. Everything but PDF is read
  with the standard library, so importing a Word document adds no dependency.
- Tracked deletions in `.docx` are not imported; deleted text is not part of
  the document.
- Archive members are size-capped before extraction, so a malformed or hostile
  file cannot exhaust memory.

### Interface

- Rebuilt around five pages — Compose, Behaviour, Library, Insights, About —
  with a fixed navigation rail, a persistent action bar and live run figures
  always in view.
- **New design system** (`theme.py`). Light by default with a full dark theme;
  every colour is declared as a light/dark pair, so neither is an afterthought.
- Five restrained accents replace the previous six.
- Serif display type for identity and figures, neutral sans for controls.
- **Newline delivery** is now a choice of Enter, Shift+Enter or skip, rather
  than a switch that silently dropped newlines when off.
- Stop and the fail-safe are now responsive during long pauses; previously a
  three-second thinking pause delayed them by up to three seconds.

### Fixed

- Long settings pages could not be reached below the fold; they scroll now.
- Navigating back to a scrolling page left the previous one on screen.

### Tests

- 70 tests across three suites. The engine suites need no display and no
  dependencies; CI runs them on macOS, Windows and Linux against Python 3.9
  and 3.13.
