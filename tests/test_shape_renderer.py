import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter

from centercross.models import ShapeLayer
from centercross.shape_renderer import draw_layers


class ShapeRendererTests(unittest.TestCase):
    @staticmethod
    def _render(layer):
        image=QImage(220,220,QImage.Format_ARGB32_Premultiplied);image.fill(0)
        painter=QPainter(image)
        try:draw_layers(painter,[layer],QPointF(110,110))
        finally:painter.end()
        return image

    def test_outline_never_stacks_opacity_for_any_vector_shape(self):
        shapes=("line","ellipse","ring","rect","dot","arrow","arc",
                "triangle_equilateral","triangle_isosceles","nose","arm_left","arm_right")
        for shape in shapes:
            with self.subTest(shape=shape):
                layer=ShapeLayer(shape=shape,width=80,height=80,arc_radius=40,
                                 thickness=4,outline_thickness=4,opacity=180,
                                 stroke_color="#ff3b30",fill_color="#ff3b30",
                                 outline_color="#000000")
                image=self._render(layer)
                alphas=[image.pixelColor(x,y).alpha() for y in range(220) for x in range(220)]
                self.assertGreater(max(alphas),0)
                self.assertLessEqual(max(alphas),180)

    def test_semitransparent_triangle_has_only_external_black_border(self):
        for shape in ("triangle_equilateral","triangle_isosceles"):
            with self.subTest(shape=shape):
                layer=ShapeLayer(shape=shape,width=40,height=80,rotation=45,
                                 thickness=4,outline_thickness=4,opacity=230,
                                 stroke_color="#ff3b30",fill_color="#ff3b30",
                                 outline_color="#000000")
                image=self._render(layer)
                red_pixels=[];black_pixels=[]
                for y in range(70,150):
                    for x in range(70,150):
                        color=image.pixelColor(x,y)
                        if color.alpha()<220:continue
                        if color.red()>240:red_pixels.append((x,y))
                        elif color.red()<20:black_pixels.append((x,y))
                        else:self.fail(f"Black outline leaked through red interior at {(x,y)}: {color.getRgb()}")
                self.assertTrue(red_pixels)
                self.assertTrue(black_pixels)

    def test_fill_stroke_and_outline_remain_separate(self):
        layer=ShapeLayer(shape="rect",width=80,height=80,thickness=8,
                         outline_thickness=4,opacity=230,fill_color="#ff0000",
                         stroke_color="#00ff00",outline_color="#000000")
        image=self._render(layer)
        self.assertEqual(image.pixelColor(110,110).name(),"#ff0000")
        self.assertEqual(image.pixelColor(70,110).name(),"#00ff00")
        self.assertEqual(image.pixelColor(63,110).name(),"#000000")
        for x in (63,70,110):
            self.assertLessEqual(image.pixelColor(x,110).alpha(),230)

    def test_flat_and_triangle_line_caps_keep_their_outer_edges(self):
        for cap in ("flat", "triangle"):
            layer = ShapeLayer(shape="line", width=50, thickness=10, outline_thickness=5, cap_style=cap)
            image = QImage(200, 200, QImage.Format_ARGB32_Premultiplied);image.fill(0)
            painter = QPainter(image)
            try:draw_layers(painter, [layer], QPointF(100, 100))
            finally:painter.end()
            self.assertGreater(image.pixelColor(70, 100).alpha(), 0, cap)

    def test_arc_shape_renders_pixels(self):
        layer = ShapeLayer(shape="arc", arc_radius=25, thickness=3, arc_span_angle=180)
        image = QImage(100, 100, QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        try:
            draw_layers(painter, [layer], QPointF(50, 50))
        finally:
            painter.end()
        self.assertTrue(any(image.pixelColor(x, y).alpha() for y in range(100) for x in range(100)))

    def test_flat_arc_outline_covers_end_face(self):
        layer = ShapeLayer(shape="arc", arc_radius=30, arc_start_angle=0,
                           arc_span_angle=90, thickness=10, outline_thickness=4,
                           cap_style="flat", stroke_color="#ff0000",
                           outline_color="#000000", opacity=255)
        image = QImage(200, 200, QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        try: draw_layers(painter, [layer], QPointF(100, 100))
        finally: painter.end()
        self.assertEqual(image.pixelColor(130, 102).name(), "#000000")
        self.assertEqual(image.pixelColor(130, 98).name(), "#ff0000")

    def test_selection_handles_are_drawn_only_on_original(self):
        layer = ShapeLayer(
            shape="line",
            x=30,
            mirror_horizontal=True,
            mirror_vertical=True,
            circular_pattern=True,
            pattern_angle=45,
            pattern_copies=3,
        )
        image = QImage(200, 200, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        try:
            with patch("centercross.shape_renderer._draw_selection") as selection:
                draw_layers(painter, [layer], QPointF(100, 100), selected_id=layer.layer_id)
            selection.assert_called_once()
        finally:
            painter.end()


if __name__ == "__main__":
    unittest.main()
