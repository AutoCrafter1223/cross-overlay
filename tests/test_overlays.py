import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from centercross.models import GuideLineSettings, MotionAssistSettings, PointerSettings, ShapeLayer
from centercross.overlays import MotionAssistOverlay, PointerOverlay


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_horizontal_and_vertical_lengths_are_fixed_pixels(self):
        settings = MotionAssistSettings()
        guides = settings.guides
        guides.horizontal = guides.vertical = True
        guides.horizontal_length = 120
        guides.vertical_length = 70
        guides.center_gap = 40
        guides.center_cap = "flat"
        guides.thickness = 8
        guides.opacity = 255

        def render(width, height):
            image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            MotionAssistOverlay.draw_guides(painter, guides, width, height)
            painter.end()
            return image

        for width, height in ((640, 480), (1000, 700)):
            image = render(width, height)
            cx, cy = width // 2, height // 2
            self.assertEqual(image.pixelColor(60, cy).alpha(), 255)
            self.assertEqual(image.pixelColor(width - 60, cy).alpha(), 255)
            self.assertEqual(image.pixelColor(140, cy).alpha(), 0)
            self.assertEqual(image.pixelColor(cx, 35).alpha(), 255)
            self.assertEqual(image.pixelColor(cx, height - 35).alpha(), 255)
            self.assertEqual(image.pixelColor(cx, 90).alpha(), 0)

        legacy = GuideLineSettings.from_dict({
            "center_gap": 120, "horizontal_margin": 230, "vertical_margin": 130,
        })
        self.assertEqual(legacy.center_gap, 0)
        self.assertEqual(legacy.horizontal_length, 730)
        self.assertEqual(legacy.vertical_length, 410)

    def test_pointer_overlay_uses_cached_shape_layers(self):
        settings = PointerSettings(layers=[
            ShapeLayer(shape="arc", x=40, arc_radius=25, arc_span_angle=210),
            ShapeLayer(shape="triangle_equilateral", x=-20, width=18, height=18),
        ])
        overlay = PointerOverlay()
        try:
            self.assertTrue(overlay.set_settings(settings))
            self.assertGreater(overlay.width(), 100)
            image = overlay.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
            self.assertTrue(any(image.pixelColor(x, y).alpha() for y in range(image.height()) for x in range(image.width())))
        finally:
            overlay.close()

    def test_static_motion_overlay_renders_without_animation(self):
        settings = MotionAssistSettings()
        settings.vignette.enabled = True
        settings.body.enabled = True
        settings.guides.enabled = True
        settings.grid.enabled = True
        overlay = MotionAssistOverlay()
        try:
            overlay.resize(640, 360)
            overlay.set_settings(settings)
            self.assertTrue(overlay.any_enabled())
            image = overlay.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
            self.assertTrue(any(image.pixelColor(x, y).alpha() for y in range(0, image.height(), 20) for x in range(0, image.width(), 20)))
            settings.enabled = False
            overlay.set_settings(settings)
            self.assertTrue(overlay.any_enabled())
        finally:
            overlay.close()

    def test_triangle_guide_tip_has_no_double_opacity(self):
        settings = MotionAssistSettings()
        guides = settings.guides
        guides.enabled = True
        guides.horizontal = True
        guides.vertical = False
        guides.horizontal_margin = 0
        guides.horizontal_length = 200
        guides.center_gap = 100
        guides.thickness = 17
        guides.opacity = 100
        guides.center_cap = "triangle"
        guides.dashed = True
        overlay = MotionAssistOverlay()
        try:
            overlay.resize(400, 200)
            overlay.set_settings(settings)
            image = QImage(400, 200, QImage.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            try: overlay._draw_guides(painter)
            finally: painter.end()
            self.assertGreater(max(image.pixelColor(x, 100).alpha() for x in range(130, 150)), 0)
            self.assertLessEqual(max(image.pixelColor(x, 100).alpha() for x in range(130, 150)), 100)
        finally:
            overlay.close()

    def test_triangle_guide_tip_has_no_join_gap(self):
        settings = MotionAssistSettings()
        guides = settings.guides
        guides.horizontal = True
        guides.vertical = True
        guides.horizontal_length = 501
        guides.vertical_length = 151
        guides.thickness = 49
        guides.opacity = 120
        guides.center_cap = "triangle"

        for dashed in (False, True):
            with self.subTest(dashed=dashed):
                guides.dashed = dashed
                image = QImage(1200, 400, QImage.Format_ARGB32_Premultiplied)
                image.fill(0)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                try:
                    MotionAssistOverlay.draw_guides(painter, guides, 1200, 400)
                finally:
                    painter.end()

                # Odd thickness puts each line-to-triangle join between pixels.
                # Every centerline pixel across the join must keep full alpha.
                for x in (475, 476, 477, 722, 723, 724):
                    self.assertEqual(image.pixelColor(x, 200).alpha(), 120)
                for y in (124, 125, 126, 273, 274, 275):
                    self.assertEqual(image.pixelColor(600, y).alpha(), 120)


if __name__ == "__main__":
    unittest.main()
