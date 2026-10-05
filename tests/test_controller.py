import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from centercross.controller import OverlayController
from centercross.geometry import Rect
from centercross.models import AppSettings, Profile


class ProfileHarness:
    profile = OverlayController.profile
    _auto_select_profile = OverlayController._auto_select_profile

    def __init__(self):
        self.settings = AppSettings(profiles=[Profile(), Profile(), Profile()])
        for profile in self.settings.profiles[1:]:
            profile.target.mode = "application"
            profile.target.executable = "game.exe"
        self.windows = [SimpleNamespace(hwnd=123, executable="game.exe")]
        self.profile_activated = Mock()
        self.applications = 0

    def apply_profile(self):
        self.applications += 1
        if self.applications > 3:
            raise AssertionError("Recursive profile switching")
        # Applying a profile refreshes visuals and re-enters target discovery.
        self._auto_select_profile(123, self.windows)


class ControllerTests(unittest.TestCase):
    def test_disabled_find_effect_ignores_hotkey_but_allows_manual_preview(self):
        profile=Profile()
        profile.find_effect.enabled=False
        controller=SimpleNamespace(profile=profile,settings=AppSettings(),effect=Mock(),
                                   store=Mock(),_update=Mock(),settings_changed=Mock(),
                                   _logical_position=Mock(return_value=(10,20)))
        with patch("centercross.controller.get_cursor_pos",return_value=(10,20)):
            OverlayController.handle_hotkey(controller,"find")
            controller.effect.play.assert_not_called()
            OverlayController.preview_effect(controller)
            controller.effect.play.assert_called_once_with((10,20),profile.find_effect)

    def test_only_changed_overlay_is_rebuilt(self):
        profile=Profile()
        controller=SimpleNamespace(profile=profile,crosshair=Mock(),pointer=Mock(),motion=Mock(),_visual_settings={},_update=Mock())
        OverlayController.refresh_visuals(controller)
        OverlayController.refresh_visuals(controller)
        profile.crosshair.layers[0].x+=1
        OverlayController.refresh_visuals(controller)
        self.assertEqual(controller.crosshair.set_settings.call_count,2)
        self.assertEqual(controller.pointer.set_settings.call_count,1)
        self.assertEqual(controller.motion.set_settings.call_count,1)

    def test_duplicate_app_profiles_select_once_without_recursion(self):
        controller = ProfileHarness()
        self.assertTrue(controller._auto_select_profile(123, controller.windows))
        self.assertEqual(controller.settings.selected_profile, 1)
        self.assertEqual(controller.applications, 1)
        controller.profile_activated.emit.assert_called_once_with(1)
        self.assertFalse(controller._auto_select_profile(123, controller.windows))

    def test_manually_selected_app_variant_is_retained(self):
        controller = ProfileHarness()
        controller.settings.selected_profile = 2
        for _ in range(4):
            self.assertFalse(controller._auto_select_profile(123, controller.windows))
        self.assertEqual(controller.settings.selected_profile, 2)
        self.assertEqual(controller.applications, 0)

    def test_disabled_profile_is_skipped_by_auto_selection(self):
        controller = ProfileHarness()
        controller.settings.profiles[1].enabled = False
        self.assertTrue(controller._auto_select_profile(123, controller.windows))
        self.assertEqual(controller.settings.selected_profile, 2)

    def test_application_target_requires_foreground_even_for_old_unrestricted_profile(self):
        profile = Profile()
        profile.target.mode = "application"
        profile.target.executable = "game.exe"
        profile.target.active_only = False
        profile.crosshair.enabled = True
        profile.pointer.enabled = True
        profile.pointer.active_only = False

        controller = SimpleNamespace(
            settings=AppSettings(profiles=[profile], keep_overlay_on_top=False),
            profile=profile,
            _last_target_check=0.0,
            _last_discovery=0.0,
            _target_hwnd=0,
            _auto_select_profile=Mock(return_value=False),
            crosshair=Mock(),
            motion=Mock(),
            pointer=Mock(),
            timer=Mock(),
        )
        controller.motion.any_enabled.return_value = True
        controller.pointer.isVisible.return_value = False
        controller._pointer_interval = Mock(return_value=120)

        with (
            patch("centercross.controller.foreground_window", return_value=321),
            patch("centercross.controller.list_top_level_windows", return_value=[]),
            patch("centercross.controller.match_window", return_value=SimpleNamespace(hwnd=123)),
            patch("centercross.controller.client_rect_on_screen", return_value=Rect(0, 0, 800, 600)),
        ):
            OverlayController._update(controller, force_target=True)

        controller.crosshair.show.assert_not_called()
        controller.motion.show.assert_not_called()
        controller.pointer.setVisible.assert_called_once_with(False)

    def test_hotkey_registration_retains_failure_and_clears_on_success(self):
        controller = ProfileHarness()
        controller.hotkeys = Mock()
        controller.hotkey_errors = Mock()
        controller.hotkeys.register_all.side_effect = [["Alt+R conflict"], []]
        OverlayController.register_hotkeys(controller)
        self.assertEqual(controller.last_hotkey_errors, ["Alt+R conflict"])
        bindings=controller.hotkeys.register_all.call_args_list[0].args[0]
        self.assertEqual(set(bindings), {"find", "all"})
        OverlayController.register_hotkeys(controller)
        self.assertEqual(controller.last_hotkey_errors, [])
        controller.hotkey_errors.emit.assert_called_with([])
