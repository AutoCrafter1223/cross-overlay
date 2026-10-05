from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


def overlay_rect(center: tuple[int, int], extent: int, offset_x: int = 0, offset_y: int = 0) -> Rect:
    size = max(2, extent * 2)
    x = center[0] + offset_x - extent
    y = center[1] + offset_y - extent
    return Rect(x, y, x + size, y + size)


def physical_to_logical_point(
    point: tuple[int, int], physical_screen: Rect, logical_screen: Rect
) -> tuple[int, int]:
    """Map a Win32 physical-pixel point into Qt's per-screen logical space."""
    if physical_screen.width <= 0 or physical_screen.height <= 0:
        return point
    scale_x = logical_screen.width / physical_screen.width
    scale_y = logical_screen.height / physical_screen.height
    return (
        logical_screen.left + round((point[0] - physical_screen.left) * scale_x),
        logical_screen.top + round((point[1] - physical_screen.top) * scale_y),
    )


def symmetry_transforms(
    x: float,
    y: float,
    rotation: float,
    mirror_horizontal: bool = False,
    mirror_vertical: bool = False,
    rotation_symmetry: bool = False,
    circular_pattern: bool = False,
    pattern_angle: float = 30,
    pattern_copies: int = 1,
) -> list[tuple[float, float, float]]:
    """Return linked copies around CENTER without duplicate transforms."""
    base = [(x, y, rotation)]
    if mirror_horizontal:
        base.append((-x, y, 180 - rotation))
    if mirror_vertical:
        base.append((x, -y, -rotation))
    if mirror_horizontal and mirror_vertical:
        base.append((-x, -y, rotation + 180))
    if rotation_symmetry and not circular_pattern:
        circular_pattern, pattern_angle, pattern_copies = True, 90, 3
    copies = max(0, min(3, int(pattern_copies))) if circular_pattern else 0
    values: list[tuple[float, float, float]] = []
    for copy_index in range(copies + 1):
        angle = math.radians(pattern_angle * copy_index)
        cosine, sine = math.cos(angle), math.sin(angle)
        for base_x, base_y, base_rotation in base:
            values.append((
                base_x * cosine - base_y * sine,
                base_x * sine + base_y * cosine,
                base_rotation + pattern_angle * copy_index,
            ))
    unique: list[tuple[float, float, float]] = []
    seen: set[tuple[float, float, float]] = set()
    for px, py, angle in values:
        normalized = (round(px, 4), round(py, 4), round(angle % 360, 4))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique
