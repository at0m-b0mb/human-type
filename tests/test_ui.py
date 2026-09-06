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
