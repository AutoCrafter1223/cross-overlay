import unittest

from centercross.models import AppSettings, BodyReferenceSettings, CrosshairSettings, Profile, body_reference_preset


class ModelTests(unittest.TestCase):
    def test_profile_round_trip(self):
        profile = Profile(name="메모장")
        profile.target.executable = "notepad.exe"
        profile.crosshair.offset_x = -27
        restored = Profile.from_dict(profile.to_dict())
        self.assertEqual(restored, profile)

    def test_unknown_fields_are_ignored(self):
        profile = Profile.from_dict({"name": "호환", "crosshair": {"thickness": 7, "future": 99}})
        self.assertEqual(profile.crosshair.thickness, 7)

    def test_selected_profile_is_clamped(self):
        settings = AppSettings.from_dict({"profiles": [{"name": "하나"}], "selected_profile": 99})
        self.assertEqual(settings.selected_profile, 0)

    def test_legacy_crosshair_is_migrated_to_layers(self):
        settings = CrosshairSettings.from_dict({"horizontal_length": 40, "gap": 8, "center_shape": "dot"})
        self.assertEqual(len(settings.layers), 3)
        self.assertTrue(settings.layers[0].mirror_horizontal)
        self.assertEqual(settings.layers[0].width, 40)

    def test_empty_layer_list_round_trips(self):
        settings = CrosshairSettings.from_dict({"layers": []})
        self.assertEqual(settings.layers, [])

    def test_old_default_pointer_offset_is_migrated_to_center(self):
        settings = AppSettings.from_dict({
            "profiles": [{"pointer": {"offset_x": 16, "offset_y": 16}}],
            "schema_version": 1,
        })
        self.assertEqual((settings.profiles[0].pointer.offset_x, settings.profiles[0].pointer.offset_y), (0, 0))
        self.assertEqual(settings.schema_version, 14)

    def test_older_profiles_default_to_enabled(self):
        settings = AppSettings.from_dict({"schema_version": 13, "profiles": [{"name": "Old"}]})
        self.assertTrue(settings.profiles[0].enabled)
        self.assertFalse(Profile.from_dict({"name": "Off", "enabled": False}).enabled)

    def test_legacy_find_effect_remains_enabled(self):
        profile=Profile.from_dict({"find_effect":{"effect":"flash","duration_ms":200}})
        self.assertTrue(profile.find_effect.enabled)

    def test_v11_guide_arms_ignore_hidden_gap(self):
        settings=AppSettings.from_dict({"schema_version":11,"profiles":[{
            "motion_assist":{"guides":{"horizontal_length":500,"vertical_length":200,
                                        "horizontal_gap":120,"vertical_gap":80,"center_gap":900}}
        }]})
        guides=settings.profiles[0].motion_assist.guides
        self.assertEqual((guides.horizontal_length,guides.vertical_length),(500,200))
        self.assertEqual((guides.center_gap,guides.horizontal_gap,guides.vertical_gap),(0,None,None))

    def test_v12_total_guide_length_becomes_per_edge_length(self):
        settings=AppSettings.from_dict({"schema_version":12,"profiles":[{
            "motion_assist":{"guides":{"horizontal_length":1100,"vertical_length":500,"center_gap":900}}
        }]})
        guides=settings.profiles[0].motion_assist.guides
        self.assertEqual((guides.horizontal_length,guides.vertical_length),(550,250))
        self.assertEqual(guides.center_gap,0)

    def test_legacy_guide_length_remains_resolution_relative(self):
        profile = Profile.from_dict({"motion_assist": {"guides": {"length_percent": 82}}})
        self.assertIsNone(profile.motion_assist.guides.horizontal_margin)
        self.assertIsNone(profile.motion_assist.guides.vertical_margin)
        restored = Profile.from_dict(profile.to_dict())
        self.assertEqual(restored.motion_assist.guides.length_percent, 82)
        self.assertIsNone(restored.motion_assist.guides.horizontal_margin)

    def test_motion_assist_round_trip_and_defaults(self):
        profile = Profile()
        profile.motion_assist.vignette.enabled = True
        profile.motion_assist.vignette.center_width = 70
        profile.motion_assist.body.enabled = True
        profile.motion_assist.guides.dashed = True
        profile.motion_assist.guides.dash_length = 17
        profile.motion_assist.guides.dash_gap = 9
        restored = Profile.from_dict(profile.to_dict())
        self.assertTrue(restored.motion_assist.vignette.enabled)
        self.assertEqual(restored.motion_assist.vignette.center_width, 70)
        self.assertTrue(restored.motion_assist.body.enabled)
        self.assertEqual(restored.motion_assist.body.layers[0].shape, "image")
        self.assertEqual([layer.image_path for layer in restored.motion_assist.body.layers],
                         ["builtin://body/nose", "builtin://body/left_hand", "builtin://body/right_hand"])
        self.assertEqual((restored.motion_assist.guides.dash_length, restored.motion_assist.guides.dash_gap), (17, 9))
        self.assertTrue(restored.motion_assist.enabled)
        self.assertEqual(restored.hotkeys.motion_assist, "Ctrl+Alt+F8")
        self.assertEqual([layer.image_path for layer in body_reference_preset("arms")],
                         ["builtin://body/left_hand", "builtin://body/right_hand"])
        self.assertEqual([layer.image_path for layer in body_reference_preset("body")],
                         ["builtin://body/nose", "builtin://body/left_hand", "builtin://body/right_hand"])
        self.assertEqual([(layer.x, layer.y, layer.width, layer.height)
                          for layer in body_reference_preset("body")],
                         [(0, -105, 210, 210), (-340, -150, 620, 300),
                          (340, -150, 620, 300)])
        self.assertEqual([(layer.width, layer.height) for layer in body_reference_preset("nose")],
                         [(210, 210)])
        self.assertEqual([(layer.width, layer.height) for layer in body_reference_preset("arms")],
                         [(620, 300), (620, 300)])

    def test_old_bundled_body_images_resize_without_changing_custom_layout(self):
        layers = [
            {"shape": "image", "image_path": "builtin://body/nose",
             "x": 0, "y": -52, "width": 105, "height": 105},
            {"shape": "image", "image_path": "builtin://body/left_hand",
             "x": -340, "y": -75, "width": 310, "height": 150},
            {"shape": "image", "image_path": "builtin://body/right_hand",
             "x": 400, "y": -75, "width": 310, "height": 150},
        ]
        restored = BodyReferenceSettings.from_dict({"preset": "body", "layers": layers})
        self.assertEqual([(item.x, item.y, item.width, item.height) for item in restored.layers],
                         [(0, -105, 210, 210), (-340, -150, 620, 300),
                          (400, -75, 310, 150)])

    def test_legacy_pointer_size_is_migrated_to_a_shape_layer(self):
        settings = AppSettings.from_dict({"profiles": [{"pointer": {"size": 73}}]})
        pointer = settings.profiles[0].pointer
        self.assertEqual((pointer.layers[0].width, pointer.layers[0].height), (73, 73))
        self.assertNotIn("size", settings.to_dict()["profiles"][0]["pointer"])

    def test_legacy_pointer_png_settings_are_migrated_to_image_layer(self):
        settings = AppSettings.from_dict({"profiles": [{"pointer": {
            "image_path": "pointer.png", "color_key_enabled": True, "color_key": "#00ff00",
        }}]})
        layer = settings.profiles[0].pointer.layers[0]
        self.assertEqual((layer.shape, layer.image_path), ("image", "pointer.png"))
        self.assertTrue(layer.color_key_enabled)
        self.assertEqual(layer.color_key, "#00ff00")

    def test_legacy_rotation_symmetry_becomes_circular_pattern(self):
        settings = CrosshairSettings.from_dict({"layers": [{"rotation_symmetry": True}]})
        layer = settings.layers[0]
        self.assertTrue(layer.circular_pattern)
        self.assertEqual((layer.pattern_angle, layer.pattern_copies), (90, 3))
        self.assertFalse(layer.rotation_symmetry)

    def test_legacy_arc_dimensions_are_migrated_to_radius(self):
        settings = CrosshairSettings.from_dict({
            "layers": [{"shape": "arc", "width": 80, "height": 40}],
        })
        self.assertEqual(settings.layers[0].arc_radius, 40)

    def test_current_pointer_offset_is_preserved(self):
        settings = AppSettings.from_dict({
            "profiles": [{"pointer": {"offset_x": 16, "offset_y": 16}}],
            "schema_version": 2,
        })
        self.assertEqual((settings.profiles[0].pointer.offset_x, settings.profiles[0].pointer.offset_y), (16, 16))

    def test_pointer_update_rate_is_limited_to_supported_values(self):
        fast = AppSettings.from_dict({"profiles": [{"pointer": {"update_rate": 240}}]})
        slow = AppSettings.from_dict({"profiles": [{"pointer": {"update_rate": 30}}]})
        automatic = AppSettings.from_dict({"profiles": [{"pointer": {"update_rate": 0}}]})
        self.assertEqual(fast.profiles[0].pointer.update_rate, 240)
        self.assertEqual(slow.profiles[0].pointer.update_rate, 0)
        self.assertEqual(automatic.profiles[0].pointer.update_rate, 0)

    def test_triangle_cap_angles_are_clamped(self):
        profile = Profile.from_dict({
            "crosshair": {"layers": [{"cap_angle": 5}]},
            "motion_assist": {"guides": {"center_cap_angle": 90}},
        })
        self.assertEqual(profile.crosshair.layers[0].cap_angle, 15)
        self.assertEqual(profile.motion_assist.guides.center_cap_angle, 75)

    def test_legacy_grid_dashes_are_copied_to_both_directions(self):
        profile = Profile.from_dict({"motion_assist": {"grid": {
            "dashed": True, "dash_length": 21, "dash_gap": 13,
        }}})
        grid = profile.motion_assist.grid
        self.assertTrue(grid.horizontal_dashed)
        self.assertTrue(grid.vertical_dashed)
        self.assertEqual((grid.horizontal_dash_length, grid.horizontal_dash_gap), (21, 13))
        self.assertEqual((grid.vertical_dash_length, grid.vertical_dash_gap), (21, 13))

    def test_legacy_spotlight_becomes_focus_lines(self):
        profile = Profile.from_dict({"find_effect": {"effect": "spotlight"}})
        self.assertEqual(profile.find_effect.effect, "focus_lines")

    def test_old_blank_target_becomes_monitor_center(self):
        profile = Profile.from_dict({"target": {"executable": "", "title": "private document"}})
        self.assertEqual(profile.target.mode, "monitor")
        self.assertNotIn("title", profile.to_dict()["target"])

    def test_old_application_target_keeps_only_executable(self):
        profile = Profile.from_dict({"target": {"executable": "notepad.exe", "title": "private note"}})
        self.assertEqual(profile.target.mode, "application")
        self.assertEqual(profile.target.executable, "notepad.exe")
        self.assertNotIn("title", profile.to_dict()["target"])

    def test_language_is_validated(self):
        self.assertEqual(AppSettings.from_dict({"language": "en"}).language, "en")
        self.assertEqual(AppSettings.from_dict({"language": "xx"}).language, "en")


if __name__ == "__main__":
    unittest.main()
