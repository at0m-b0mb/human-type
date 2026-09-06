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


if __name__ == "__main__":
    if not HAVE_DISPLAY:
        print("No display — interface tests skipped.")
    unittest.main(verbosity=2)
