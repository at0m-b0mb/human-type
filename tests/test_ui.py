"""
Interface smoke tests.

These build the real window, so they need a display and are skipped without
one (CI runs the engine tests instead). They are deliberately shallow and
broad: every page constructs, every accent applies, every control the typing
engine reads still exists under the name the engine expects. That last one is
the point — the view was rebuilt from scratch, and a renamed variable would
otherwise only show up when someone pressed Start.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_app_module():
    spec = importlib.util.spec_from_file_location(
        "humantype", str(ROOT / "human-type.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["humantype"] = module
    spec.loader.exec_module(module)
    return module


try:
    import tkinter
    _root = tkinter.Tk()
    _root.destroy()
    HAVE_DISPLAY = True
except Exception:
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, "no display available")
class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load_app_module()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.m.CONFIG_PATH = Path(cls.tmp.name) / "config.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.app = self.m.HumanTyperApp()
        self.app.update_idletasks()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    # -- structure ------------------------------------------------------
    def test_every_navigation_entry_has_a_page(self):
        for key, _title, _sub in self.app.NAV:
            self.assertIn(key, self.app._pages, "%s has no page" % key)

    def test_pages_can_all_be_shown(self):
        for key, title, _sub in self.app.NAV:
            self.app._show_page(key)
            self.app.update_idletasks()
            self.assertEqual(self.app._current_page, key)
            self.assertEqual(self.app._page_title.get(), title)

    def test_only_one_page_is_visible_at_a_time(self):
        for key, _t, _s in self.app.NAV:
            self.app._show_page(key)
            self.app.update_idletasks()
            visible = [name for name, page in self.app._pages.items()
                       if page.winfo_manager()]
            self.assertEqual(visible, [key], "expected only %s visible" % key)

    # -- the contract between view and engine ---------------------------
    def test_controls_the_typing_engine_reads_all_exist(self):
        """The view was rebuilt; the engine still reads these by name."""
        for name in ["_tb", "_vars", "_profile_var", "_drift_var",
                     "_notice_var", "_effort_var", "_warmup_var",
                     "_fatigue_var", "_burst_var", "_burst_mode", "_idle_var",
                     "_think_var", "_common_typos", "_cap_slip_var",
                     "_transpose_var", "_double_var", "_newline_var",
                     "_vars_expand", "_overlay_var", "_repeat_count_var",
                     "_repeat_sep_var", "_prog", "_start_btn", "_pause_btn",
                     "_status_var", "_status_dot", "_wpm_var", "_eta_var",
                     "_mini_wpm_var", "_mini_eta_var", "_mini_done_var",
                     "_mini_acc_var", "_stat_rows", "_history_frame",
                     "_snip_list_frame", "_snip_preview", "_snip_title_var"]:
            self.assertTrue(hasattr(self.app, name),
                            "the engine reads self.%s and it is gone" % name)

    def test_timing_fields_are_all_present(self):
        for key in ("start_delay", "base_delay", "variation", "punct_pause",
                    "para_pause", "typo_chance"):
            self.assertIn(key, self.app._vars)

    def test_analysis_rows_match_what_update_count_writes(self):
        for key in ("chars", "words", "sentences", "paragraphs", "avg_word",
                    "reading", "estimate", "flesch", "grade"):
            self.assertIn(key, self.app._stat_rows)

    def test_building_a_style_works_for_every_profile(self):
        for name in self.m.REALISM_PROFILES:
            self.app._apply_realism_profile(name)
            style = self.app._current_style()
            self.assertEqual(style.rhythm_drift,
                             float(self.app._drift_var.get()))
            self.assertEqual(style.notice_max, int(self.app._notice_var.get()))

    def test_newline_modes_map_to_engine_values(self):
        for label, value in self.m.NEWLINE_MODES.items():
            self.app._newline_var.set(label)
            self.assertEqual(self.app._newline_mode_value(), value)
            self.app._update_newline_help()
            self.assertTrue(self.app._newline_help.get())

    def test_analysis_updates_when_text_changes(self):
        self.app._tb.delete("1.0", "end")
        self.app._tb.insert("1.0", "One sentence here. And a second one!")
        self.app._update_count()
        self.assertEqual(self.app._stat_rows["words"].get(), "7")
        self.assertEqual(self.app._stat_rows["sentences"].get(), "2")
        self.assertNotEqual(self.app._stat_rows["estimate"].get(), "—")

    # -- speed and realism must not fight over the same field -----------
    def test_speed_presets_only_set_pace(self):
        """Two controls writing one field means the last click silently wins.

        Picking Natural then Blazing used to drop the typo rate to zero while
        the Realism segment still said Natural, so the label lied about the
        behaviour. Speed owns pace; realism owns mistakes.
        """
        for preset in self.m.PRESETS.values():
            for field in preset:
                self.assertIn(field, self.m.PRESET_FIELDS,
                              "%s is a realism concern, not a speed one" % field)
            self.assertNotIn("typo_chance", preset)

    def test_a_speed_preset_does_not_disturb_the_profile(self):
        for profile in self.m.REALISM_PROFILES:
            self.app._apply_realism_profile(profile)
            expected = self.app._current_style().typo_chance
            for preset in self.m.PRESETS:
                self.app._apply_preset(preset)
                self.assertEqual(
                    self.app._current_style().typo_chance, expected,
                    "%s changed the typo rate set by the %s profile"
                    % (preset, profile))

    def test_speed_presets_still_change_the_pace(self):
        self.app._tb.delete("1.0", "end")
        self.app._tb.insert("1.0", "The quick brown fox jumps over the dog. " * 4)
        self.app._apply_realism_profile("Robotic")
        import realism as rz
        seen = {}
        for preset in ("Slow", "Normal", "Fast", "Blazing"):
            self.app._apply_preset(preset)
            seen[preset] = rz.estimate_seconds(
                self.app._tb.get("1.0", "end"), self.app._current_style(),
                samples=2)
        self.assertGreater(seen["Slow"], seen["Normal"])
        self.assertGreater(seen["Normal"], seen["Fast"])
        self.assertGreater(seen["Fast"], seen["Blazing"])

    def test_speed_segment_tells_the_truth(self):
        for preset in self.m.PRESETS:
            self.app._apply_preset(preset)
            self.assertEqual(self.app._matching_preset(), preset)
            self.assertEqual(self.app._preset_seg.get(), preset)
        # A hand-edited value belongs to no preset, and the segment should
        # stop claiming one.
        self.app._vars["base_delay"].set("0.0777")
        self.app.update_idletasks()
        self.assertIsNone(self.app._matching_preset())
        self.assertEqual(self.app._preset_seg.get(), "")

    def test_saved_speed_shows_on_the_segment_after_a_restart(self):
        self.app._apply_preset("Blazing")
        self.app._persist_state()
        revived = self.m.HumanTyperApp()
        try:
            revived.update_idletasks()
            self.assertEqual(revived._vars["base_delay"].get(), "0.01")
            self.assertEqual(revived._preset_seg.get(), "Blazing")
        finally:
            revived.destroy()

    def test_a_hand_tuned_typo_rate_survives_a_restart(self):
        """The profile resets it, so something has to restore it afterwards."""
        self.app._apply_realism_profile("Natural")
        self.app._vars["typo_chance"].set("0.077")
        self.app._persist_state()
        revived = self.m.HumanTyperApp()
        try:
            revived.update_idletasks()
            self.assertEqual(revived._vars["typo_chance"].get(), "0.077")
        finally:
            revived.destroy()

    # -- appearance -----------------------------------------------------
    def test_every_accent_applies_without_error(self):
        import theme
        for name in theme.ACCENTS:
            self.app._on_theme_change(name)
            self.app.update_idletasks()
            self.assertEqual(self.app._theme_name, name)

    def test_legacy_accent_names_still_resolve(self):
        import theme
        for old in ("Midnight", "Dracula", "Cyberpunk", "Forest", "Ocean",
                    "Sunset", "something removed"):
            self.assertIn(self.m.resolve_theme(old), theme.ACCENTS)

    def test_every_appearance_mode_applies(self):
        import customtkinter as ctk
        for mode in self.m.APPEARANCE_MODES:
            self.app._on_mode_change(mode)
            self.app.update_idletasks()
            self.assertEqual(self.app._appearance, mode)
        # Auto resolves to whatever the system is doing, so the app must
        # remember the choice rather than the resolved value.
        self.app._on_mode_change("Auto")
        self.assertEqual(self.app._appearance, "Auto")
        self.assertIn(ctk.get_appearance_mode().lower(), ("light", "dark"))

    def test_appearance_choice_survives_a_restart(self):
        self.app._on_mode_change("Auto")
        self.app._persist_state()
        revived = self.m.HumanTyperApp()
        try:
            self.assertEqual(revived._appearance, "Auto")
            self.assertEqual(revived._mode_seg.get(), "Auto")
        finally:
            revived.destroy()

    def test_old_configs_without_an_appearance_key_still_open(self):
        self.assertEqual(self.m.resolve_appearance(None, True), "Dark")
        self.assertEqual(self.m.resolve_appearance(None, False), "Light")
        self.assertEqual(self.m.resolve_appearance("nonsense", True), "Dark")
        self.assertEqual(self.m.resolve_appearance("Auto", True), "Auto")

    def test_accent_registry_is_populated(self):
        """If nothing registered, switching accent would silently do nothing."""
        self.assertGreater(len(self.app._accented), 5)

    # -- persistence ----------------------------------------------------
    def test_settings_round_trip_through_the_config_file(self):
        self.app._apply_realism_profile("Hurried")
        self.app._newline_var.set("Shift + Enter")
        self.app._vars["base_delay"].set("0.055")
        self.app._on_theme_change("Emerald")
        self.app._persist_state()

        saved = json.loads(self.m.CONFIG_PATH.read_text())
        self.assertEqual(saved["realism_profile"], "Hurried")
        self.assertEqual(saved["newline_mode"], "Shift + Enter")
        self.assertEqual(saved["theme"], "Emerald")
        self.assertEqual(saved["last_settings"]["base_delay"], "0.055")

        revived = self.m.HumanTyperApp()
        try:
            revived.update_idletasks()
            self.assertEqual(revived._profile_var.get(), "Hurried")
            self.assertEqual(revived._newline_var.get(), "Shift + Enter")
            self.assertEqual(revived._vars["base_delay"].get(), "0.055")
            self.assertEqual(revived._theme_name, "Emerald")
        finally:
            revived.destroy()


@unittest.skipUnless(HAVE_DISPLAY, "no display available")
class StylingTests(unittest.TestCase):
    """Nothing may fall back to the CustomTkinter default palette.

    A widget built with no colours inherits the toolkit's stock blue, which
    against warm paper reads as a broken or disabled control rather than a
    styled one. That is exactly how the Replace all button shipped looking
    dead. These walk the real widget tree instead of trusting review.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _load_app_module()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.m.CONFIG_PATH = Path(cls.tmp.name) / "config.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.app = self.m.HumanTyperApp()
        self.app.update_idletasks()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _walk(widget):
        yield widget
        for child in widget.winfo_children():
            for item in StylingTests._walk(child):
                yield item

    @staticmethod
    def _defaults():
        """The stock colours, straight from the toolkit's own theme table."""
        import customtkinter as ctk
        theme = ctk.ThemeManager.theme
        out = set()
        for widget_name in ("CTkButton", "CTkSegmentedButton", "CTkSwitch",
                            "CTkSlider", "CTkProgressBar", "CTkCheckBox",
                            "CTkOptionMenu", "CTkEntry"):
            block = theme.get(widget_name, {})
            for key in ("fg_color", "progress_color", "button_color",
                        "selected_color", "hover_color", "border_color"):
                value = block.get(key)
                if isinstance(value, list):
                    out.add(tuple(value))
                elif isinstance(value, str) and value != "transparent":
                    out.add(value)
        return out

    def _assert_styled(self, root, where):
        import customtkinter as ctk
        defaults = self._defaults()
        interesting = (ctk.CTkButton, ctk.CTkSegmentedButton, ctk.CTkSwitch,
                       ctk.CTkSlider, ctk.CTkProgressBar, ctk.CTkCheckBox,
                       ctk.CTkOptionMenu, ctk.CTkEntry)
        checked = 0
        for widget in self._walk(root):
            if not isinstance(widget, interesting):
                continue
            checked += 1
            props = ["fg_color", "progress_color"]
            # A default border colour only matters when a border is drawn.
            try:
                if int(widget.cget("border_width") or 0) > 0:
                    props.append("border_color")
            except (ValueError, AttributeError, TypeError):
                pass
            for prop in props:
                try:
                    value = widget.cget(prop)
                except (ValueError, AttributeError):
                    continue
                if value in (None, "transparent"):
                    continue
                key = tuple(value) if isinstance(value, list) else value
                self.assertNotIn(
                    key, defaults,
                    "%s: a %s still has the toolkit default %s=%r — it was "
                    "built without the theme recipes"
                    % (where, type(widget).__name__, prop, value))
        self.assertGreater(checked, 0, "%s: found no widgets to check" % where)
        return checked

    def _assert_borders_have_colours(self, root, where):
        """border_width without border_color is what made Replace all look dead."""
        import customtkinter as ctk
        for widget in self._walk(root):
            if not isinstance(widget, (ctk.CTkButton, ctk.CTkEntry,
                                       ctk.CTkFrame, ctk.CTkCheckBox)):
                continue
            try:
                width = widget.cget("border_width")
                colour = widget.cget("border_color")
            except (ValueError, AttributeError):
                continue
            if width and int(width) > 0:
                self.assertNotIn(
                    colour, (None, "transparent"),
                    "%s: a %s has border_width=%s but no border_colour"
                    % (where, type(widget).__name__, width))

    @staticmethod
    def _toplevels(app):
        import customtkinter as ctk
        return [w for w in app.winfo_children()
                if isinstance(w, ctk.CTkToplevel)]

    # -- the main window ------------------------------------------------
    def test_main_window_uses_no_default_colours(self):
        for key, _t, _s in self.app.NAV:
            self.app._show_page(key)
            self.app.update_idletasks()
        self._assert_styled(self.app, "main window")
        self._assert_borders_have_colours(self.app, "main window")

    def test_main_window_is_styled_in_every_accent(self):
        import theme
        for name in theme.ACCENTS:
            self.app._on_theme_change(name)
            self.app.update_idletasks()
            self._assert_styled(self.app, "main window / %s" % name)

    # -- dialogs --------------------------------------------------------
    def test_find_and_replace_is_styled(self):
        self.app.open_find_replace()
        self.app.update_idletasks()
        win = self.app._find_win
        self.assertTrue(win.winfo_exists())
        self._assert_styled(win, "Find & Replace")
        self._assert_borders_have_colours(win, "Find & Replace")
        win.destroy()

    def test_find_and_replace_actually_replaces(self):
        self.app._tb.delete("1.0", "end")
        self.app._tb.insert("1.0", "one two one two one")
        self.app.open_find_replace()
        self.app.update_idletasks()
        import customtkinter as ctk
        entries = [w for w in self._walk(self.app._find_win)
                   if isinstance(w, ctk.CTkEntry)]
        self.assertEqual(len(entries), 2)
        entries[0].insert(0, "one")
        entries[1].insert(0, "three")
        buttons = {w.cget("text"): w for w in self._walk(self.app._find_win)
                   if isinstance(w, ctk.CTkButton)}
        self.assertIn("Replace all", buttons)
        buttons["Replace all"].invoke()
        self.app.update_idletasks()
        self.assertEqual(self.app._tb.get("1.0", "end").strip(),
                         "three two three two three")
        self.app._find_win.destroy()

    def test_dry_run_window_is_styled(self):
        self.app._tb.delete("1.0", "end")
        self.app._tb.insert("1.0", "a b")
        self.app._dry_run()
        self.app.update_idletasks()
        windows = self._toplevels(self.app)
        self.assertTrue(windows, "dry run opened no window")
        for win in windows:
            self._assert_styled(win, "Dry run")
            self._assert_borders_have_colours(win, "Dry run")
            win.destroy()

    # -- nothing may be clipped out of its own window -------------------
    def _assert_nothing_clipped(self, win, where):
        """Every widget must fall inside the window that owns it.

        This is the bug the user actually hit: the Replace all button was
        styled correctly but sat below the bottom edge of a fixed-height
        dialog, so it looked absent. A hard-coded size cannot survive
        different font metrics; this catches it on any platform.
        """
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        self.assertGreaterEqual(
            h, win.winfo_reqheight(),
            "%s: window is %dpx tall but its content needs %dpx"
            % (where, h, win.winfo_reqheight()))
        self.assertGreaterEqual(
            w, win.winfo_reqwidth(),
            "%s: window is %dpx wide but its content needs %dpx"
            % (where, w, win.winfo_reqwidth()))

        import customtkinter as ctk
        for widget in self._walk(win):
            if not isinstance(widget, (ctk.CTkButton, ctk.CTkEntry,
                                       ctk.CTkCheckBox, ctk.CTkOptionMenu)):
                continue
            if not widget.winfo_ismapped():
                continue
            top = widget.winfo_rooty() - win.winfo_rooty()
            left = widget.winfo_rootx() - win.winfo_rootx()
            bottom = top + widget.winfo_height()
            right = left + widget.winfo_width()
            try:
                label = widget.cget("text")
            except (ValueError, AttributeError):
                label = type(widget).__name__
            self.assertLessEqual(
                bottom, h + 1,
                "%s: %r (%s) ends at y=%d but the window is only %dpx tall — "
                "it is cut off and looks missing"
                % (where, label, type(widget).__name__, bottom, h))
            self.assertLessEqual(
                right, w + 1,
                "%s: %r (%s) ends at x=%d but the window is only %dpx wide"
                % (where, label, type(widget).__name__, right, w))
            self.assertGreaterEqual(top, -1, "%s: %r is above the top edge"
                                    % (where, label))

    def test_find_and_replace_shows_all_its_buttons(self):
        self.app.open_find_replace()
        self.app.update_idletasks()
        win = self.app._find_win
        self._assert_nothing_clipped(win, "Find & Replace")
        import customtkinter as ctk
        labels = {w.cget("text") for w in self._walk(win)
                  if isinstance(w, ctk.CTkButton) and w.winfo_ismapped()}
        for expected in ("Find all", "Replace all", "Close"):
            self.assertIn(expected, labels,
                          "%s is missing from the dialog" % expected)
        win.destroy()

    def test_main_window_clips_nothing(self):
        for key, _t, _s in self.app.NAV:
            self.app._show_page(key)
            self.app.update_idletasks()
        self._assert_nothing_clipped(self.app, "main window")

    def test_overlay_is_styled(self):
        self.app._build_overlay()
        self.app.update_idletasks()
        self._assert_styled(self.app._overlay_win, "progress overlay")
        self.app._destroy_overlay()


@unittest.skipUnless(HAVE_DISPLAY, "no display available")
class TypingRunTests(unittest.TestCase):
    """End-to-end runs, with keystroke injection stubbed out.

    These drive a real mainloop, because the typing thread hands its updates
    back with self.after() and Tkinter only permits that while the loop is
    running.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _load_app_module()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.m.CONFIG_PATH = Path(cls.tmp.name) / "config.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        # A fresh config per test: start_typing persists settings, so a run
        # that sets Repeat to 3 would otherwise leak into the next test's
        # freshly constructed app.
        self._case_config = Path(self.tmp.name) / ("%s.json" % self.id().split(".")[-1])
        self.m.CONFIG_PATH = self._case_config
        self.app = self.m.HumanTyperApp()
        self.app.update_idletasks()
        self.typed = []
        # Nothing may reach the real keyboard from a test.
        self.app._emit = self.typed.append
        self.app._press_key = self._fake_key
        self.app._sleep = lambda _s: None
        self.app._vars["start_delay"].set("0")

    def tearDown(self):
        try:
            self.app.stop_typing()
        except Exception:
            pass
        try:
            self.app.destroy()
        except Exception:
            pass

    def _fake_key(self, name):
        if name == "backspace":
            if self.typed:
                self.typed.pop()
        elif name in ("enter", "shift_enter"):
            self.typed.append("\n")

    def _run_to_completion(self, text, timeout=30):
        import time
        self.typed.clear()
        self.app._tb.delete("1.0", "end")
        self.app._tb.insert("1.0", text)
        deadline = time.time() + timeout

        def poll():
            if not self.app._typing_active or time.time() > deadline:
                self.app.quit()
                return
            self.app.after(10, poll)

        self.app.start_typing()
        self.app.after(10, poll)
        self.app.mainloop()
        self.assertFalse(self.app._typing_active, "the run never finished")
        return "".join(self.typed)

    def test_every_profile_types_the_text_exactly(self):
        source = "Hello there. This is definitely a test!\n\nSecond paragraph."
        self.app._apply_preset("Blazing")
        self.app._newline_var.set("Press Enter")
        for profile in self.m.REALISM_PROFILES:
            self.app._apply_realism_profile(profile)
            self.assertEqual(self._run_to_completion(source), source,
                             "%s did not reproduce the text" % profile)

    def test_run_reports_done_and_records_a_session(self):
        self.app._apply_preset("Blazing")
        self.app._apply_realism_profile("Robotic")
        before = len(self.app.config.get("session_history", []))
        self._run_to_completion("A short run.")
        self.app.update()
        self.assertIn("Done", self.app._status_var.get())
        self.assertEqual(len(self.app.config.get("session_history", [])),
                         before + 1)

    def test_skip_mode_sends_no_newline(self):
        self.app._apply_preset("Blazing")
        self.app._apply_realism_profile("Robotic")
        self.app._newline_var.set("Skip (join)")
        out = self._run_to_completion("line one\nline two")
        self.assertNotIn("\n", out)
        self.assertEqual(out, "line oneline two")

    def test_closing_mid_run_stops_the_worker(self):
        """Closing the window during a run must not leave the thread going.

        The worker posts updates with after(); destroying the root underneath
        it left those firing into a dead interpreter and Tk printed a stream
        of "invalid command name" errors.
        """
        self.app._apply_preset("Slow")
        self.app._apply_realism_profile("Robotic")
        self.app._sleep = lambda s: __import__("time").sleep(min(s, 0.01))
        self.app._tb.delete("1.0", "end")
        self.app._tb.insert("1.0", "x" * 2000)
        self.app.start_typing()
        self.assertFalse(self.app._run_finished.is_set())
        self.app.after(200, lambda: (self.app._on_close(), self.app.quit()))
        self.app.mainloop()
        self.assertTrue(self.app._run_finished.is_set(),
                        "the typing thread outlived the window")
        self.assertTrue(self.app._closing)

    def test_cross_thread_updates_go_through_the_guard(self):
        """Every worker-to-UI hop must use _post, which honours shutdown."""
        import ast
        tree = ast.parse((ROOT / "human-type.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        offenders = []
        for node in cls.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name in ("_post", "_show_page", "_build_cadence"):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "after"
                        and sub.args
                        and isinstance(sub.args[0], ast.Constant)
                        and sub.args[0].value == 0):
                    offenders.append(node.name)
        self.assertEqual(
            offenders, [],
            "these post to the UI with a raw after(0, ...) instead of _post: %s"
            % sorted(set(offenders)))

    def test_repeat_joins_with_the_separator(self):
        self.app._apply_preset("Blazing")
        self.app._apply_realism_profile("Robotic")
        self.app._repeat_count_var.set("3")
        self.app._repeat_sep_var.set("\\n")
        self.assertEqual(self._run_to_completion("ab"), "ab\nab\nab")


class ThreadSafetyTests(unittest.TestCase):
    """The typing thread must not touch Tkinter directly.

    Tkinter is not thread-safe. Reading a variable from the worker is
    undefined behaviour even when it appears to work, and _run did exactly
    that for the newline mode, while _record_session reached the editor
    contents through _persist_state. Both are static mistakes, so a static
    check catches them without needing a display.
    """

    @classmethod
    def setUpClass(cls):
        import ast
        cls.tree = ast.parse((ROOT / "human-type.py").read_text(encoding="utf-8"))
        cls.cls_node = next(n for n in cls.tree.body
                            if isinstance(n, ast.ClassDef))

    def _method(self, name):
        import ast
        for node in self.cls_node.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail("no method named %s" % name)

    def _calls_in(self, node):
        import ast
        names = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                names.append(sub.func.attr)
        return names

    def test_run_reads_no_tk_variables(self):
        """Anything the worker needs must be passed in from the main thread."""
        node = self._method("_run")
        for banned in ("_newline_mode_value", "_current_style", "_persist_state"):
            self.assertNotIn(
                banned, self._calls_in(node),
                "_run calls %s, which reads Tk state from the typing thread"
                % banned)

    def test_record_session_does_not_persist_inline(self):
        """It runs on the typing thread; _persist_state reads the editor."""
        import ast
        node = self._method("_record_session")
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "_persist_state"):
                parent_is_after = False
                for outer in ast.walk(node):
                    if (isinstance(outer, ast.Call)
                            and isinstance(outer.func, ast.Attribute)
                            and outer.func.attr == "after"
                            and any(getattr(a, "attr", None) == "_persist_state"
                                    for a in outer.args)):
                        parent_is_after = True
                self.assertTrue(
                    parent_is_after,
                    "_record_session calls _persist_state directly from the "
                    "typing thread; schedule it with self.after instead")

    def test_start_typing_hands_the_worker_plain_values(self):
        """The thread should receive data, not widgets to interrogate."""
        import ast
        node = self._method("start_typing")
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and getattr(sub.func, "attr", None) == "Thread"):
                kwargs = {k.arg: k.value for k in sub.keywords}
                self.assertIn("args", kwargs)
                return
        self.fail("start_typing no longer starts a thread")


class HostileConfigTests(unittest.TestCase):
    """A corrupted config file must not lock the user out of the app.

    ~/.humantyper.json is the one input that persists between runs, so it is
    the one a partial write, a crash, a sync conflict or hand-editing can
    mangle. Nine different wrong types used to crash on startup with an
    AttributeError and no way back in. These need no display.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _load_app_module()

    def _load(self, payload):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.json"
            if isinstance(payload, (bytes, bytearray)):
                path.write_bytes(payload)
            else:
                path.write_text(json.dumps(payload))
            original = self.m.CONFIG_PATH
            self.m.CONFIG_PATH = path
            try:
                return self.m.load_config()
            finally:
                self.m.CONFIG_PATH = original

    def test_wrong_types_fall_back_to_defaults(self):
        cases = {
            "stats": "not a dict",
            "session_history": {"a": 1},
            "custom_snippets": ["a", "b"],
            "custom_presets": "nope",
            "recent_files": 7,
            "toggles": [1, 2, 3],
            "last_settings": [1, 2],
            "repeat": "x",
            "appearance": {"a": 1},
            "draft": 12345,
        }
        for key, bad in cases.items():
            cfg = self._load({key: bad})
            expected = type(self.m.DEFAULT_CONFIG[key])
            self.assertIsInstance(
                cfg[key], expected,
                "%s survived as %r" % (key, type(cfg[key]).__name__))

    def test_nulls_are_replaced(self):
        cfg = self._load({"stats": None, "toggles": None, "draft": None})
        self.assertIsInstance(cfg["stats"], dict)
        self.assertIsInstance(cfg["toggles"], dict)
        self.assertIsInstance(cfg["draft"], str)

    def test_corrupt_files_load_defaults(self):
        for blob in (b"{{{{", b"", b"[1,2,3]", b'"hello"', b"null",
                     b"\x00\x01binary"):
            cfg = self._load(blob)
            self.assertIsInstance(cfg, dict)
            self.assertIn("stats", cfg)

    def test_free_form_containers_are_filtered(self):
        cfg = self._load({
            # JSON turns a non-string key into a string, so 7 legitimately
            # survives as "7"; the dict value is the one to drop.
            "custom_snippets": {"good": "body", "bad": {"nested": 1}, 7: "x"},
            "recent_files": ["/a.txt", 5, None, "/b.txt"],
            "session_history": [{"chars": 1}, "junk", 42],
        })
        self.assertEqual(cfg["custom_snippets"], {"good": "body", "7": "x"})
        self.assertEqual(cfg["recent_files"], ["/a.txt", "/b.txt"])
        self.assertEqual(cfg["session_history"], [{"chars": 1}])

    def test_unknown_keys_are_kept(self):
        """Forward compatibility: a newer build's keys must survive."""
        cfg = self._load({"something_new": {"a": 1}})
        self.assertEqual(cfg["something_new"], {"a": 1})

    def test_real_settings_still_round_trip(self):
        cfg = self._load({"theme": "Emerald", "appearance": "Auto",
                          "rhythm_drift": 0.2, "notice_max": 5,
                          "last_settings": {"base_delay": "0.05"}})
        self.assertEqual(cfg["theme"], "Emerald")
        self.assertEqual(cfg["appearance"], "Auto")
        self.assertEqual(cfg["rhythm_drift"], 0.2)
        self.assertEqual(cfg["last_settings"]["base_delay"], "0.05")


@unittest.skipUnless(HAVE_DISPLAY, "no display available")
class InputSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load_app_module()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.m.CONFIG_PATH = Path(cls.tmp.name) / "c.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.app = self.m.HumanTyperApp()
        self.app.update_idletasks()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_schedule_delays_stay_inside_tcl_limits(self):
        """Tcl's after() takes a 32-bit millisecond count."""
        for raw in ("25h", "999999h", "99999999999s"):
            self.assertIsNone(self.app._parse_schedule(raw),
                              "%s was accepted" % raw)
        for raw, expect in (("30s", 30000), ("5m", 300000), ("24h", 86400000)):
            self.assertEqual(self.app._parse_schedule(raw), expect)
        for raw in ("30s", "24h", "23:59"):
            delay = self.app._parse_schedule(raw)
            self.assertLessEqual(delay, 2 ** 31 - 1)

    def test_opening_a_file_with_variables_warns(self):
        """A file someone else wrote must not silently decide what is typed."""
        seen = {}
        # Save the real one first — re-importing the module afterwards would
        # just hand back the stub, leaking it into every later test.
        original = self.m.messagebox.showwarning
        self.m.messagebox.showwarning = lambda t, msg: seen.update(t=t, msg=msg)
        try:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "invoice.txt"
                path.write_text("Please review. {clipboard}")
                self.app._vars_expand.set(True)
                self.app._load_path(str(path))
                self.assertTrue(seen, "no warning for {clipboard} in a file")
                self.assertIn("{clipboard}", seen["msg"])

                seen.clear()
                clean = Path(d) / "clean.txt"
                clean.write_text("Nothing special here.")
                self.app._load_path(str(clean))
                self.assertFalse(seen, "warned about a file with no variables")
        finally:
            self.m.messagebox.showwarning = original

    def test_recent_files_list_is_bounded(self):
        for i in range(200):
            self.app._push_recent("/tmp/f%d.txt" % i)
        self.assertLessEqual(len(self.app.config.get("recent_files", [])), 20)


class SourceStyleTests(unittest.TestCase):
    """Static checks — these need no display, so CI runs them everywhere."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "human-type.py").read_text(encoding="utf-8")

    def test_input_dialogs_all_go_through_the_helper(self):
        """A raw CTkInputDialog would come up in the toolkit's default blue."""
        self.assertEqual(
            self.source.count("ctk.CTkInputDialog("), 1,
            "build input dialogs with self._ask_text() so they are themed")

    def test_popup_menus_all_go_through_the_helper(self):
        self.assertEqual(
            self.source.count("tk.Menu("), 1,
            "build popup menus with self._menu() so they are themed")

    def test_no_hardcoded_grey_text_colours(self):
        for bad in ('text_color="gray', "text_color='gray"):
            self.assertNotIn(
                bad, self.source,
                "use the INK/INK_2/INK_3 tokens instead of a literal grey")

    def test_no_leftover_default_toplevels(self):
        """Every secondary window should be built by self._dialog()."""
        self.assertEqual(
            self.source.count("ctk.CTkToplevel("), 2,
            "secondary windows go through self._dialog(); the overlay is the "
            "one deliberate exception")


if __name__ == "__main__":
    if not HAVE_DISPLAY:
        print("No display — interface tests skipped.")
    unittest.main(verbosity=2)
