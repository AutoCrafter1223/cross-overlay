import unittest

from PySide6.QtGui import QColor, QImage

from centercross.image_utils import apply_color_key


class ImageUtilsTests(unittest.TestCase):
    def test_exact_key_color_becomes_transparent(self):
        image = QImage(2, 1, QImage.Format_RGBA8888)
        image.setPixelColor(0, 0, QColor(255, 255, 255, 200))
        image.setPixelColor(1, 0, QColor(0, 0, 0, 123))

        result = apply_color_key(image, "#ffffff")

        self.assertEqual(result.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(result.pixelColor(1, 0).alpha(), 123)

    def test_softness_feathers_nearby_colors(self):
        image = QImage(1, 1, QImage.Format_RGBA8888)
        image.setPixelColor(0, 0, QColor(245, 245, 245, 200))

        result = apply_color_key(image, "#ffffff", tolerance=5, softness=10)

        self.assertEqual(result.pixelColor(0, 0).alpha(), 100)


if __name__ == "__main__":
    unittest.main()
