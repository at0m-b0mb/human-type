# Changelog

## 1.1.0

Three bugs reported from real use, and the feature the first one needed.

### Look-alike characters

A hyphen, an en dash and an em dash were indistinguishable in the editor.
That is not a perception problem: measured in Menlo at the editor's own 13px,
**six of the eight dash characters render as the identical 8x1 pixel stroke**
— hyphen-minus, figure dash, en dash, em dash, horizontal bar and minus sign.
Only U+2010 and U+2011 differ. Changing monospace does not help; Monaco,
Courier New and Andale Mono collapse them the same way, because a monospace
font's job is to give every character the same cell. `tools/make_dash_figure.py`
re-measures it from the font file and redraws `docs/dashes.svg` from the
result.

So the editor stopped relying on the glyph:

- **Marks** (new toolbar toggle) tints the four families that look like
  something they are not — dashes, curly quotes, exotic spaces, and
  zero-width and bidi controls. Four washes, each contrast-tested against the
  editor and against its own ink in both themes. **Nothing in the text is
  changed**, which the suite asserts.
- **A caret readout** under the editor names the exact character beside the
  cursor: `EM DASH (U+2014)`. The one to the left wins; the one to the right
  is named with an arrow, because which side of a dash you click on is a coin
  toss. This is the part that actually tells an en dash from an em dash.
- **The inspector lists** every look-alike in the text, by name, with counts.
- An invisible character has no width to tint, so it borrows the character
  next to it rather than marking nothing.
- Two new transforms: **Dashes to ASCII** and **Punctuation to ASCII**, for
  when flattening is what you wanted. These do change the text, on purpose.

This matters more here than in a normal editor: these are exactly the
characters a document carries in from Word, Pages or a web page, and exactly
the ones a target window may have no key for.

### Fixed

- **Find & Replace appeared to open twice.** A `CTkToplevel` is mapped the
  moment it exists, so the window showed up at the toolkit's placeholder size
  in the corner, then jumped to its real size and position — which reads as
  one window closing and another opening. Dialogs are now built hidden and
  shown once, finished. The dry-run window had the same shape of bug.
- **Dialog sizing went through CustomTkinter's scaled wrappers** while being
  handed real pixels, so at 150% display scaling a dialog came out half again
  too big. It also meant `resizable()` scheduled a Windows titlebar repaint
  that would have restored a still-hidden window to hidden.
- **Recent, Transform and Variable did nothing.** `_popup()` called itself,
  so every one of those three buttons raised `RecursionError` into Tk's
  callback handler, which prints to stderr and swallows it.
- **Escape inside Find & Replace also stopped a typing run**, because the
  dialog binding did not stop the event reaching the application-wide one.
- **Search highlights did not follow a theme change**, keeping the light
  theme's yellow in dark mode.

### Speed and the options

Progress was posted to the interface on **every keystroke** — a hundred
updates a second at the Blazing preset, each rewriting seven variables, a
progress bar and the overlay. It is now capped at twenty a second, which is
more than an eye can use. Measured on this machine, the loop's own overhead
dropped from 1.19 to 1.02 ms per keystroke.

A finished run now reports **planned versus actual** time, so "is the speed
setting doing anything?" has a number instead of an impression. For the
record, measured over 30 seeds on a 792-character passage, the plans are not
subtle: Slow/Natural 42 WPM, Normal/Natural 74, Fast/Natural 132,
Blazing/Robotic 1,033. What the plan cannot control is whether the receiving
application drains keystrokes as fast as they are posted.

### Tests

153 tests, up from 129. New: the look-alike table and both transforms, the
marks never altering the text, zero-width characters still being marked, the
caret readout naming both neighbours, dialogs being hidden until finished and
shown at their final size, Escape not leaking, popup menus posting instead of
recursing, and the four mark washes against WCAG in both themes.

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
- **Appearance** is Light, Dark or Auto, which follows the operating system.
  Light and gold are the defaults.
- The dark theme is genuinely black with neutral greys, rather than the dark
  blue it started as.
- **A cadence meter** in the sidebar, built from real data: each bar is the
  gap between two keystrokes on a log scale — the engine's own rhythm while
  idle, and the gaps actually being executed during a run.
- A colophon on the About page, because someone chose the typefaces.
- Stop and the fail-safe are now responsive during long pauses; previously a
  three-second thinking pause delayed them by up to three seconds.

### Security

The document reader takes input from other people, so it was attacked
deliberately rather than reviewed by eye. Five of seven attacks were already
refused; two were not.

- **Deeply nested XML crashed the app.** The `.docx` walk was recursive, so a
  file a few thousand elements deep raised `RecursionError`. The walk keeps
  its own stack now and refuses anything past 100 levels, which no real
  document reaches.
- **XML document type declarations are refused outright.** Modern expat caps
  entity amplification, but that cap depends on the expat the interpreter was
  built against rather than the Python version, and this project supports 3.9.
  Real documents carry no DTD, so refusing it removes the question — along
  with the XXE vector.
- Confirmed safe and now covered by tests: external entities cannot read local
  files, zip members outside the document are never read, nothing is extracted
  to disk, and pathological RTF and HTML stay linear.
- **A corrupted config file used to lock you out of the app.**
  `~/.humantyper.json` is the one input that persists between runs, so a
  partial write or a sync conflict can mangle it. Nine different wrong types
  crashed on startup with an `AttributeError`. Stored values are now kept only
  when they match the shape of their default.
- **Opening a file containing `{variables}` now warns.** They expand when
  typing starts, so a document someone else wrote could use `{clipboard}` to
  put your clipboard into the target window. The feature stays; it no longer
  does that silently.
- **Scheduled delays are capped at 24 hours.** Tcl's `after()` takes a 32-bit
  millisecond count, and `999999h` overflowed it.

### Fixed

- **Closing the window mid-run left the typing thread posting updates into a
  destroyed interpreter**, which Tk reported as a stream of "invalid command
  name" errors. Close now signals the worker, drains the queued updates while
  the window is still alive, and only then tears down. Every cross-thread
  update goes through one guarded helper, and a test fails if a new raw
  `after(0, ...)` appears.

- **The typing thread read Tkinter state.** `_run` fetched the newline mode
  from a Tk variable on the worker thread, and `_record_session` reached the
  editor contents through `_persist_state` from the same thread. Tkinter is
  not thread-safe; both are undefined behaviour even when they appear to
  work. The mode is now read on the main thread and passed in, and the config
  write is scheduled back with `after`.
- **Speed presets silently overwrote the realism profile's typo rate.**
  Choosing Natural and then Blazing dropped the mistake rate to zero while
  the Realism segment still said Natural. Speed now sets pace only; mistake
  rates belong to the profiles, which is what the interface already claimed.
- **The Speed segment lied after a restart**, showing Normal whatever the
  saved timing values were. It now reflects the actual numbers, and clears
  itself when a field is hand-edited away from every preset.
- **A hand-tuned typo rate was lost on restart**, because the profile reset it
  and nothing restored it afterwards — unlike rhythm drift and notice delay,
  which were already handled.

- **Find & Replace was unusable.** Its buttons sat below the bottom edge of a
  fixed-height window, so Replace all looked absent, and the dialog had never
  been restyled — it still used the toolkit's default palette, which against
  warm paper reads as a disabled control. Dialogs now size to their content,
  and the whole dialog layer goes through the design system.
- Two regression tests cover the class rather than the instance: one walks
  every widget and fails if anything still carries a CustomTkinter default
  colour, the other fails if any control falls outside the window that owns
  it. Both were verified against the original bug.

- Long settings pages could not be reached below the fold; they scroll now.
- Navigating back to a scrolling page left the previous one on screen.

### Tests

- 129 tests across four suites. The engine, document and palette suites need
  no display and no dependencies; CI runs them on macOS, Windows and Linux
  against Python 3.9 and 3.13.
- The palette suite checks every text pairing against WCAG AA in both themes
  and all six accents, which is what keeps a gold accent readable.
