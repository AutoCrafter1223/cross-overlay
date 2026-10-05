from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPixmap


_BUILTIN_IMAGES = {
    "builtin://body/nose": "nose.png",
    "builtin://body/left_hand": "left_hand.png",
    "builtin://body/right_hand": "right_hand.png",
}


def resolve_image_path(path: str | Path) -> Path:
    filename = _BUILTIN_IMAGES.get(str(path))
    return Path(__file__).resolve().parent / "assets" / filename if filename else Path(path)


def apply_color_key(
    source: QImage,
    key_color: str,
    tolerance: int = 0,
    softness: int = 0,
) -> QImage:
    """Return a copy with pixels near key_color made transparent."""
    image = source.convertToFormat(QImage.Format_RGBA8888)
    if image.isNull():
        return image
    key = QColor(key_color)
    if not key.isValid():
        return image
    tolerance = max(0, min(255, int(tolerance)))
    softness = max(0, min(255, int(softness)))
    pixels = image.bits().cast("B")
    stride = image.bytesPerLine()
    red, green, blue = key.red(), key.green(), key.blue()
    for y in range(image.height()):
        row = y * stride
        for x in range(image.width()):
            offset = row + x * 4
            distance = max(
                abs(pixels[offset] - red),
                abs(pixels[offset + 1] - green),
                abs(pixels[offset + 2] - blue),
            )
            if distance <= tolerance:
                pixels[offset + 3] = 0
            elif softness and distance < tolerance + softness:
                ratio = (distance - tolerance) / softness
                pixels[offset + 3] = round(pixels[offset + 3] * ratio)
    return image


@lru_cache(maxsize=64)
def _cached_pixmap(
    path: str,
    modified_ns: int,
    color_key_enabled: bool,
    color_key: str,
    tolerance: int,
    softness: int,
) -> QPixmap:
    del modified_ns
    image = QImage(path)
    if image.isNull():
        return QPixmap()
    if color_key_enabled:
        image = apply_color_key(image, color_key, tolerance, softness)
    return QPixmap.fromImage(image)


def load_processed_pixmap(
    path: str,
    color_key_enabled: bool = False,
    color_key: str = "#ffffff",
    tolerance: int = 0,
    softness: int = 0,
) -> QPixmap:
    source = resolve_image_path(path)
    try:
        modified_ns = source.stat().st_mtime_ns
    except OSError:
        modified_ns = 0
    return _cached_pixmap(str(source), modified_ns, color_key_enabled, color_key, tolerance, softness)
