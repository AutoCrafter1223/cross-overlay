import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from centercross.models import MotionAssistSettings, CrosshairSettings, ShapeLayer
from centercross.overlays import MotionAssistOverlay
from centercross.ui import MotionAssistPreview, ReticlePreview


def paint_image(draw):
    image = QImage(640, 360, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    try:
        draw(painter)
    finally:
        painter.end()
    return image


class PreviewAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_vignette_matches_overlay_and_responds_to_softness(self):
        settings = MotionAssistSettings()
        settings.vignette.enabled = True
        settings.vignette.offset_x = 120
        preview = MotionAssistPreview()
        preview.resize(640, 360)
        preview.set_model(settings)
        overlay = MotionAssistOverlay()
        overlay.resize(1920, 1080)
        try:
            images = []
            for softness in (0, 100):
                settings.vignette.softness = softness
                overlay.set_settings(settings)
                actual = paint_image(preview._draw_vignette)
                def draw_expected(painter):
                    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                    painter.drawPixmap(preview.rect(), overlay._vignette_cache)
                self.assertEqual(actual, paint_image(draw_expected))
                images.append(actual)
            self.assertNotEqual(images[0], images[1])
        finally:
            preview.close()
            overlay.close()

    def test_grid_and_guides_match_scaled_overlay(self):
        settings = MotionAssistSettings()
        settings.grid.horizontal_dashed = True
        settings.grid.vertical_dashed = True
        settings.grid.horizontal_dash_offset = 7
        settings.grid.vertical_dash_offset = 13
        settings.grid.thickness = 2
        settings.guides.dashed = True
        settings.guides.center_cap = "triangle"
        settings.guides.thickness = 7
        settings.guides.vertical = True
        settings.guides.offset_x = 31
        preview = MotionAssistPreview()
        preview.resize(640, 360)
        preview.set_model(settings)
        overlay = MotionAssistOverlay()
        overlay.resize(1920, 1080)
        overlay.set_settings(settings)
        try:
            for method in ("_draw_grid", "_draw_guides"):
                with self.subTest(method=method):
                    def draw_expected(painter):
                        painter.scale(1/3, 1/3)
                        getattr(overlay, method)(painter)
                    self.assertEqual(paint_image(getattr(preview, method)), paint_image(draw_expected))
        finally:
            preview.close()
            overlay.close()

    def test_reticle_preview_honors_antialiasing(self):
        settings = CrosshairSettings(layers=[ShapeLayer(shape="line", rotation=27, width=80, thickness=3)])
        preview = ReticlePreview()
        preview.set_model(settings, None)
        try:
            settings.antialiasing = False
            first = preview.grab().toImage()
            settings.antialiasing = True
            preview.update()
            self.assertNotEqual(first, preview.grab().toImage())
        finally:
            preview.close()
