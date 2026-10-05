from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from .models import CrosshairSettings, FindEffectSettings, MotionAssistSettings, PointerSettings
from .shape_renderer import draw_layers, layer_extent
from .winapi import apply_click_through


class OverlayWidget(QWidget):
    def __init__(self) -> None:
        # Topmost state is managed explicitly through SetWindowPos so the user
        # setting can also remove it without recreating the transparent window.
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        apply_click_through(int(self.winId()))


def _color(value: str, alpha: int) -> QColor:
    result = QColor(value)
    result.setAlpha(max(0, min(alpha, 255)))
    return result


class CrosshairOverlay(OverlayWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = CrosshairSettings()
        self._cache = QPixmap()
        self._extent = 24

    def set_settings(self, settings: CrosshairSettings) -> None:
        self.settings = settings
        self._extent = layer_extent(settings.layers)
        self.resize(self._extent * 2, self._extent * 2)
        self._rebuild_cache()
        self.update()

    def _rebuild_cache(self) -> None:
        dpr = max(1.0, self.devicePixelRatioF())
        physical_size = QSize(math.ceil(self.width() * dpr), math.ceil(self.height() * dpr))
        self._cache = QPixmap(physical_size)
        self._cache.setDevicePixelRatio(dpr)
        self._cache.fill(Qt.transparent)
        cache_painter = QPainter(self._cache)
        cache_painter.setRenderHint(QPainter.Antialiasing, self.settings.antialiasing)
        cache_painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        draw_layers(cache_painter, self.settings.layers, QPointF(self._extent, self._extent))
        cache_painter.end()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._cache.isNull() or abs(self._cache.devicePixelRatioF() - self.devicePixelRatioF()) > .01:
            self._rebuild_cache()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)


class PointerOverlay(OverlayWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = PointerSettings()
        self._cache = QPixmap()
        self._extent = 24

    def set_settings(self, settings: PointerSettings) -> bool:
        self.settings = settings
        self._extent = layer_extent(settings.layers)
        self.resize(self._extent * 2, self._extent * 2)
        self._rebuild_cache()
        self.update()
        return True

    def _rebuild_cache(self) -> None:
        dpr = max(1.0, self.devicePixelRatioF())
        physical_size = QSize(math.ceil(self.width() * dpr), math.ceil(self.height() * dpr))
        self._cache = QPixmap(physical_size);self._cache.setDevicePixelRatio(dpr);self._cache.fill(Qt.transparent)
        painter = QPainter(self._cache);painter.setRenderHint(QPainter.Antialiasing,self.settings.antialiasing);painter.setRenderHint(QPainter.SmoothPixmapTransform,True)
        draw_layers(painter,self.settings.layers,QPointF(self._extent,self._extent));painter.end()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._cache.isNull() or abs(self._cache.devicePixelRatioF()-self.devicePixelRatioF())>.01:self._rebuild_cache()
        painter=QPainter(self);painter.drawPixmap(0,0,self._cache)


class MotionAssistOverlay(OverlayWidget):
    """One full-target static layer for vignette, body reference, guides and grid."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = MotionAssistSettings()
        self._vignette_cache = QPixmap()
        self._resize_debounce=QTimer(self);self._resize_debounce.setSingleShot(True);self._resize_debounce.setInterval(120);self._resize_debounce.timeout.connect(self._finish_resize)

    def set_settings(self, settings: MotionAssistSettings) -> None:
        self.settings = settings
        self._rebuild_vignette()
        self.update()

    def any_enabled(self) -> bool:
        s = self.settings
        return s.vignette.enabled or s.body.enabled or s.guides.enabled or s.grid.enabled

    @staticmethod
    def _pattern_pen(color: QColor, width: int, dashed: bool, length: int, gap: int, offset: int = 0) -> QPen:
        pen = QPen(color, width, Qt.SolidLine, Qt.FlatCap)
        if dashed:
            # Qt measures dash lengths in multiples of the pen width.
            unit = max(1, width)
            pen.setDashPattern([max(0.1, length / unit), max(0.1, gap / unit)])
            pen.setDashOffset(offset / unit)
        return pen

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._resize_debounce.start()

    def _finish_resize(self) -> None:
        self._rebuild_vignette();self.update()

    def _rebuild_vignette(self) -> None:
        if not self.settings.vignette.enabled or self.width() < 2 or self.height() < 2:
            self._vignette_cache = QPixmap()
            return
        self._vignette_cache = self.render_vignette(self.settings.vignette, self.width(), self.height())

    @staticmethod
    def render_vignette(v, target_width: int, target_height: int) -> QPixmap:
        # A capped-resolution gradient keeps 4K memory use small. It is rebuilt
        # only when settings or target geometry changes, never on a frame timer.
        scale = min(1.0, 960 / max(1,target_width), 540 / max(1,target_height))
        width, height = max(2, round(target_width * scale)), max(2, round(target_height * scale))
        pixmap = QPixmap(width, height);pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        maximum = QColor(v.color);maximum.setAlpha(v.opacity);painter.fillRect(pixmap.rect(), maximum)
        cx = width / 2 + v.offset_x * scale;cy = height / 2 + v.offset_y * scale
        inner_w = width * v.center_width / 100;inner_h = height * v.center_height / 100
        outer_w = inner_w + (width - inner_w) * v.softness / 100
        outer_h = inner_h + (height - inner_h) * v.softness / 100
        steps = 48
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setPen(Qt.NoPen)
        for index in range(steps):
            t = index / (steps - 1)
            w = outer_w + (inner_w - outer_w) * t;h = outer_h + (inner_h - outer_h) * t
            alpha = round(v.opacity * (1 - t) ** 1.7)
            color = QColor(v.color);color.setAlpha(alpha);painter.setBrush(color)
            rect = QRectF(cx - w / 2, cy - h / 2, w, h)
            if v.shape == "rounded_rect":painter.drawRoundedRect(rect, min(w,h)*.18, min(w,h)*.18)
            else:painter.drawEllipse(rect)
        painter.end();return pixmap

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self);s = self.settings
        painter.setRenderHint(QPainter.Antialiasing, True)
        if s.vignette.enabled and not self._vignette_cache.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(self.rect(), self._vignette_cache)
        if s.grid.enabled:self._draw_grid(painter)
        if s.guides.enabled:self._draw_guides(painter)
        if s.body.enabled:
            painter.setRenderHint(QPainter.Antialiasing, s.body.antialiasing)
            draw_layers(painter, s.body.layers, QPointF(self.width()/2, self.height()))

    def _draw_grid(self, painter: QPainter) -> None:
        self.draw_grid(painter,self.settings.grid,self.width(),self.height())

    @classmethod
    def draw_grid(cls, painter: QPainter, g, width: int, height: int) -> None:
        color=QColor(g.color);color.setAlpha(g.opacity)
        painter.setBrush(Qt.NoBrush)
        left,top=g.margin,g.margin;right,bottom=width-g.margin,height-g.margin
        if right<=left or bottom<=top:return
        for column in range(1,g.columns):
            x=left+(right-left)*column/g.columns
            weight=g.thickness*2 if g.emphasize_center and g.columns%2==0 and column==g.columns//2 else g.thickness
            painter.setPen(cls._pattern_pen(color,weight,g.vertical_dashed,g.vertical_dash_length,g.vertical_dash_gap,g.vertical_dash_offset));painter.drawLine(QPointF(x,top),QPointF(x,bottom))
        for row in range(1,g.rows):
            y=top+(bottom-top)*row/g.rows
            weight=g.thickness*2 if g.emphasize_center and g.rows%2==0 and row==g.rows//2 else g.thickness
            painter.setPen(cls._pattern_pen(color,weight,g.horizontal_dashed,g.horizontal_dash_length,g.horizontal_dash_gap,g.horizontal_dash_offset));painter.drawLine(QPointF(left,y),QPointF(right,y))

    def _draw_guides(self, painter: QPainter) -> None:
        self.draw_guides(painter,self.settings.guides,self.width(),self.height())

    @classmethod
    def draw_guides(cls, painter: QPainter, g, width: int, height: int) -> None:
        color = QColor(g.color)
        color.setAlpha(g.opacity)
        cx = width / 2 + g.offset_x
        cy = height / 2 + g.offset_y

        # Each length is measured inward from its own screen edge, not from
        # the center. This keeps the guides stable when a target window moves.
        if g.horizontal:
            length = min(
                width / 2,
                g.horizontal_length if g.horizontal_length is not None else width * g.length_percent / 200,
            )
            inset = min(length / 2, g.thickness / 2) if g.center_cap == "round" else 0
            cls._draw_guide_segment(
                painter, QPointF(g.offset_x + inset, cy),
                QPointF(g.offset_x + length - inset, cy), "left", g, color,
            )
            cls._draw_guide_segment(
                painter, QPointF(width + g.offset_x - inset, cy),
                QPointF(width + g.offset_x - length + inset, cy), "right", g, color,
            )
        if g.vertical:
            length = min(
                height / 2,
                g.vertical_length if g.vertical_length is not None else height * g.length_percent / 200,
            )
            inset = min(length / 2, g.thickness / 2) if g.center_cap == "round" else 0
            cls._draw_guide_segment(
                painter, QPointF(cx, g.offset_y + inset),
                QPointF(cx, g.offset_y + length - inset), "up", g, color,
            )
            cls._draw_guide_segment(
                painter, QPointF(cx, height + g.offset_y - inset),
                QPointF(cx, height + g.offset_y - length + inset), "down", g, color,
            )

    @classmethod
    def _draw_guide_segment(
        cls, painter: QPainter, outer: QPointF, inner: QPointF,
        outward: str, settings, color: QColor,
    ) -> None:
        pen = cls._pattern_pen(
            color, settings.thickness, settings.dashed,
            settings.dash_length, settings.dash_gap,
        )
        if settings.center_cap == "round":
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(outer, inner)
            return
        if settings.center_cap == "flat":
            painter.setPen(pen)
            painter.drawLine(outer, inner)
            return

        radius = settings.thickness / 2
        angle = max(15, min(75, settings.center_cap_angle))
        depth = max(1.0, radius / math.tan(math.radians(angle)))
        depth = min(depth, math.hypot(outer.x() - inner.x(), outer.y() - inner.y()))
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[outward]
        base = QPointF(inner.x() + dx * depth, inner.y() + dy * depth)
        normal = QPointF(-dy * radius, dx * radius)

        triangle = QPainterPath()
        triangle.addPolygon(QPolygonF([
            inner,
            QPointF(base.x() + normal.x(), base.y() + normal.y()),
            QPointF(base.x() - normal.x(), base.y() - normal.y()),
        ]))
        triangle.closeSubpath()

        # A separate drawLine/drawPolygon pair leaves an antialiased hairline
        # at the shared edge. Fill one combined path so even translucent tips
        # are composited just once, without a darker overlap.
        shape = QPainterPath()
        available = math.hypot(outer.x() - base.x(), outer.y() - base.y())
        if available > 0:
            stub = min(available, max(settings.thickness, settings.dash_gap if settings.dashed else 0))
            end = QPointF(base.x() + dx * stub, base.y() + dy * stub)
            line = QPainterPath(outer)
            line.lineTo(end)
            stroke = QPainterPathStroker()
            stroke.setWidth(settings.thickness)
            stroke.setCapStyle(Qt.FlatCap)
            if settings.dashed:
                stroke.setDashPattern(pen.dashPattern())
            shape = stroke.createStroke(line)

            # Cross the triangle's base by one logical pixel. Merely touching
            # it leaves a subpixel seam at some widths and preview zoom levels.
            overlap = min(1.0, depth)
            stub_line = QPainterPath(end)
            stub_line.lineTo(QPointF(base.x() - dx * overlap, base.y() - dy * overlap))
            solid_stroke = QPainterPathStroker()
            solid_stroke.setWidth(settings.thickness)
            solid_stroke.setCapStyle(Qt.FlatCap)
            shape = shape.united(solid_stroke.createStroke(stub_line))

        # Geometric unions avoid holes where Qt's stroke contours wind in the
        # opposite direction to the filled triangle.
        shape = shape.united(triangle)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(shape)
        painter.restore()

class FindEffectOverlay(OverlayWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = FindEffectSettings()
        self._progress = 0.0
        self._repetition = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def play(self, position: tuple[int, int], settings: FindEffectSettings) -> None:
        self.settings = settings
        self._progress = 0.0
        self._repetition = 0
        extent = settings.max_size + settings.thickness + 4
        self.setGeometry(position[0] - extent, position[1] - extent, extent * 2, extent * 2)
        self.show()
        self._timer.start()

    def _tick(self) -> None:
        step = self._timer.interval() / max(100, self.settings.duration_ms) * max(.1, self.settings.speed / 100)
        self._progress += step
        if self._progress >= 1:
            self._repetition += 1
            if self._repetition >= max(1, self.settings.repeats):
                self.stop()
                return
            self._progress = 0.0
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802
        s, p = self.settings, self._progress
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        center = self.rect().center()
        alpha = int(s.opacity * (1 - .6 * p))
        painter.setPen(QPen(_color(s.color, alpha), s.thickness))
        radius = s.max_size * (1 - p if s.effect == "contract" else p)
        if s.effect == "flash":
            radius = s.max_size * .6
            painter.setOpacity(.35 + .65 * abs(math.sin(p * math.pi * 4)))
        if s.effect in {"expand", "contract", "flash"}:
            painter.drawEllipse(center, int(radius), int(radius))
        elif s.effect == "grow":
            # Visual-only enlarged pointer surrogate; the real system cursor is untouched.
            size = s.max_size * (.25 + .35 * math.sin(p * math.pi))
            x, y = center.x(), center.y()
            arrow = QPolygonF([
                QPointF(x - size * .28, y - size * .42),
                QPointF(x - size * .05, y + size * .35),
                QPointF(x + size * .08, y + size * .10),
                QPointF(x + size * .35, y + size * .35),
            ])
            painter.drawPolyline(arrow)
        elif s.effect in {"lines", "focus_lines"}:
            gap = int(s.max_size * (.15 + .45 * (p if s.effect == "lines" else 1-p)))
            edge = s.max_size
            painter.drawLine(center.x() - edge, center.y(), center.x() - gap, center.y())
            painter.drawLine(center.x() + gap, center.y(), center.x() + edge, center.y())
            painter.drawLine(center.x(), center.y() - edge, center.x(), center.y() - gap)
            painter.drawLine(center.x(), center.y() + gap, center.x(), center.y() + edge)
