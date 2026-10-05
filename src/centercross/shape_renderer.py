from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF

from .geometry import symmetry_transforms
from .image_utils import load_processed_pixmap
from .models import ShapeLayer


SHAPE_LABELS = {
    "line": "선",
    "ellipse": "원 · 타원",
    "ring": "링",
    "rect": "사각형",
    "dot": "점",
    "arrow": "화살표",
    "arc": "호",
    "triangle_equilateral": "정삼각형",
    "triangle_isosceles": "이등변삼각형",
    "image": "PNG 이미지",
    "nose": "가상 코",
    "arm_left": "왼팔",
    "arm_right": "오른팔",
}


FILLED_SHAPES = {
    "ellipse", "rect", "dot", "triangle_equilateral", "triangle_isosceles",
    "nose", "arm_left", "arm_right",
}


def layer_extent(layers: list[ShapeLayer]) -> int:
    extent = 24.0
    for layer in layers:
        if not layer.visible:
            continue
        radius = layer.arc_radius if layer.shape == "arc" else math.hypot(max(1, layer.width), max(1, layer.height)) / 2
        if layer.shape == "line" and layer.cap_style == "triangle":
            radius += max(1.0, (layer.thickness / 2) / math.tan(math.radians(layer.cap_angle)))
        for x, y, _rotation in symmetry_transforms(
            layer.x, layer.y, layer.rotation, layer.mirror_horizontal,
            layer.mirror_vertical, layer.rotation_symmetry, layer.circular_pattern,
            layer.pattern_angle, layer.pattern_copies,
        ):
            padding=layer.thickness+layer.outline_thickness*2+5
            extent = max(extent, abs(x) + radius + padding, abs(y) + radius + padding)
    return min(2048, max(24, math.ceil(extent)))


def draw_layers(
    painter: QPainter,
    layers: list[ShapeLayer],
    center: QPointF,
    scale: float = 1.0,
    selected_id: str | None = None,
) -> None:
    painter.save()
    for layer in layers:
        if not layer.visible:
            continue
        for copy_index, (x, y, rotation) in enumerate(symmetry_transforms(
            layer.x, layer.y, layer.rotation, layer.mirror_horizontal,
            layer.mirror_vertical, layer.rotation_symmetry, layer.circular_pattern,
            layer.pattern_angle, layer.pattern_copies,
        )):
            painter.save()
            painter.translate(center.x() + x * scale, center.y() + y * scale)
            painter.rotate(rotation)
            _draw_primitive(painter, layer, scale)
            if selected_id == layer.layer_id and copy_index == 0:
                _draw_selection(painter, layer, scale)
            painter.restore()
    painter.restore()


def _draw_primitive(painter: QPainter, layer: ShapeLayer, scale: float) -> None:
    if layer.shape == "arc":
        width = height = max(1.0, layer.arc_radius * 2 * scale)
    else:
        width = max(1.0, layer.width * scale)
        height = max(1.0, layer.height * scale)
    rect = QRectF(-width / 2, -height / 2, width, height)
    if layer.shape == "image" and layer.image_path:
        pixmap = load_processed_pixmap(
            layer.image_path, layer.color_key_enabled, layer.color_key,
            layer.color_key_tolerance, layer.color_key_softness,
        )
        if not pixmap.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setOpacity(layer.opacity / 255)
            painter.drawPixmap(rect.toRect(), pixmap)
        return

    if layer.shape == "arc" and layer.arc_span_angle == 0:
        return
    thickness = max(1.0, layer.thickness * scale)
    outline = max(0.0, layer.outline_thickness * scale)
    filled = layer.shape in FILLED_SHAPES
    geometry = _geometry_path(layer, width, height, rect, scale)
    if geometry.isEmpty():
        return
    if layer.shape == "line" and layer.cap_style == "triangle":
        stroke = geometry
    else:
        stroker = QPainterPathStroker()
        stroker.setWidth(thickness)
        stroker.setCapStyle(Qt.RoundCap if layer.cap_style == "round" else Qt.FlatCap)
        stroker.setJoinStyle(Qt.MiterJoin)
        stroke = stroker.createStroke(geometry)
    core = geometry.united(stroke) if filled else stroke

    border = QPainterPath()
    if outline:
        border_stroker = QPainterPathStroker()
        border_stroker.setWidth(outline * 2)
        border_stroker.setJoinStyle(Qt.MiterJoin)
        border = border_stroker.createStroke(core).subtracted(core)

    # Compose opaque colors first, then apply layer opacity once. This prevents
    # overlapping contour paths (notably noses and arms) from becoming darker.
    bounds = core.boundingRect()
    if outline:
        bounds = bounds.united(border.boundingRect())
    bounds = bounds.adjusted(-2, -2, 2, 2)
    dpr = max(1.0, painter.device().devicePixelRatioF())
    image = QImage(max(1, math.ceil(bounds.width() * dpr)),
                   max(1, math.ceil(bounds.height() * dpr)), QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(dpr)
    image.fill(Qt.transparent)
    composite = QPainter(image)
    composite.setRenderHint(QPainter.Antialiasing, painter.testRenderHint(QPainter.Antialiasing))
    composite.translate(-bounds.left(), -bounds.top())
    composite.setPen(Qt.NoPen)
    if outline:
        composite.setBrush(QColor(layer.outline_color))
        composite.drawPath(border)
    if filled:
        composite.setBrush(QColor(layer.fill_color))
        composite.drawPath(geometry.subtracted(stroke))
    composite.setBrush(QColor(layer.stroke_color))
    composite.drawPath(stroke)
    composite.end()
    painter.save()
    painter.setOpacity(painter.opacity() * max(0, min(255, layer.opacity)) / 255)
    painter.drawImage(bounds.topLeft(), image)
    painter.restore()


def _geometry_path(layer: ShapeLayer, width: float, height: float, rect: QRectF, scale: float) -> QPainterPath:
    path = QPainterPath()
    if layer.shape == "line":
        if layer.cap_style == "triangle":
            half_height = max(1.0, layer.thickness * scale) / 2
            slope = math.tan(math.radians(max(15, min(75, layer.cap_angle))))
            tip = max(1.0, half_height / slope)
            path.addPolygon(QPolygonF([
                QPointF(-width/2-tip, 0), QPointF(-width/2, -half_height),
                QPointF(width/2, -half_height), QPointF(width/2+tip, 0),
                QPointF(width/2, half_height), QPointF(-width/2, half_height),
            ]))
            path.closeSubpath()
        else:
            path.moveTo(-width/2, 0)
            path.lineTo(width/2, 0)
    elif layer.shape in {"ellipse", "ring", "dot"}:
        path.addEllipse(rect)
    elif layer.shape == "rect":
        path.addRect(rect)
    elif layer.shape == "arc":
        path.arcMoveTo(rect, layer.arc_start_angle)
        path.arcTo(rect, layer.arc_start_angle, layer.arc_span_angle)
    elif layer.shape in {"triangle_equilateral", "triangle_isosceles"}:
        triangle_height = width * math.sqrt(3) / 2 if layer.shape == "triangle_equilateral" else height
        path.addPolygon(QPolygonF([
            QPointF(0, -triangle_height / 2), QPointF(width / 2, triangle_height / 2),
            QPointF(-width / 2, triangle_height / 2),
        ]))
        path.closeSubpath()
    elif layer.shape == "arrow":
        path.moveTo(-width/2, 0)
        path.lineTo(width/2, 0)
        head = min(width * .35, max(6.0 * scale, height / 2))
        for direction in (-1, 1):
            path.moveTo(width/2, 0)
            path.lineTo(width/2-head, direction*head*.65)
    elif layer.shape == "nose":
        path.moveTo(0, -height * .46)
        path.cubicTo(-width * .16, -height * .20, -width * .12, height * .12, -width * .34, height * .32)
        path.cubicTo(-width * .22, height * .46, -width * .08, height * .40, 0, height * .34)
        path.cubicTo(width * .08, height * .40, width * .22, height * .46, width * .34, height * .32)
        path.cubicTo(width * .12, height * .12, width * .16, -height * .20, 0, -height * .46)
        path.closeSubpath()
    elif layer.shape in {"arm_left", "arm_right"}:
        direction = -1 if layer.shape == "arm_left" else 1
        path.moveTo(direction * width * .50, height * .42)
        path.cubicTo(direction * width * .28, height * .24, direction * width * .16, -height * .18, 0, -height * .42)
        path.cubicTo(-direction * width * .12, -height * .25, direction * width * .04, height * .12, direction * width * .28, height * .50)
        path.closeSubpath()
    return path


def _draw_selection(painter: QPainter, layer: ShapeLayer, scale: float) -> None:
    if layer.shape == "arc":
        width = height = max(8.0, layer.arc_radius * 2 * scale)
    else:
        width = max(8.0, layer.width * scale)
        height = max(8.0, layer.height * scale)
    if layer.shape == "line":
        height = max(10.0, (layer.thickness+layer.outline_thickness*2) * scale + 8)
        if layer.cap_style=="triangle":
            width += max(2.0, layer.thickness*scale/math.tan(math.radians(max(15,min(75,layer.cap_angle)))))
    rect = QRectF(-width / 2 - 4, -height / 2 - 4, width + 8, height + 8)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor("#1677ff"), 1, Qt.DashLine))
    painter.drawRect(rect)
    painter.setBrush(QColor("white"))
    painter.setPen(QPen(QColor("#1677ff"), 1))
    for point in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
        painter.drawEllipse(point, 3, 3)
