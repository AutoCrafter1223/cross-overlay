import unittest

from centercross.geometry import Rect, overlay_rect, physical_to_logical_point, symmetry_transforms


class GeometryTests(unittest.TestCase):
    def test_client_center_handles_negative_monitor_coordinates(self):
        rect = Rect(-1920, 100, 0, 1180)
        self.assertEqual(rect.center, (-960, 640))

    def test_overlay_rect_applies_offset(self):
        self.assertEqual(overlay_rect((500, 300), 50, -10, 20), Rect(440, 270, 540, 370))

    def test_invalid_dimensions_do_not_become_negative(self):
        rect = Rect(10, 10, 2, 4)
        self.assertEqual((rect.width, rect.height), (0, 0))

    def test_physical_to_logical_at_125_percent(self):
        physical = Rect(0, 0, 1920, 1200)
        logical = Rect(0, 0, 1536, 960)
        self.assertEqual(physical_to_logical_point((960, 600), physical, logical), (768, 480))

    def test_physical_to_logical_preserves_monitor_origins(self):
        physical = Rect(-2560, 0, -640, 1080)
        logical = Rect(-2048, 0, -512, 864)
        self.assertEqual(physical_to_logical_point((-1600, 540), physical, logical), (-1280, 432))

    def test_horizontal_and_vertical_symmetry(self):
        values = symmetry_transforms(40, 10, 30, True, True, False)
        self.assertEqual(values, [(40, 10, 30), (-40, 10, 150), (40, -10, 330), (-40, -10, 210)])

    def test_rotation_symmetry_makes_four_linked_copies(self):
        values = symmetry_transforms(0, -40, 0, rotation_symmetry=True)
        self.assertEqual(values, [(0, -40, 0), (40, 0, 90), (0, 40, 180), (-40, 0, 270)])

    def test_circular_pattern_rotates_the_mirrored_group(self):
        values = symmetry_transforms(
            20, 0, 0, mirror_horizontal=True,
            circular_pattern=True, pattern_angle=30, pattern_copies=2,
        )
        self.assertEqual(len(values), 6)
        self.assertIn((round(20 * 3 ** .5 / 2, 4), 10.0, 30), values)

    def test_circular_pattern_copy_count_is_capped_at_three(self):
        values = symmetry_transforms(
            0, -40, 0, circular_pattern=True, pattern_angle=20, pattern_copies=99,
        )
        self.assertEqual(len(values), 4)


if __name__ == "__main__":
    unittest.main()
