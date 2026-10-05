from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import locale
from typing import Any, TypeVar
from uuid import uuid4


T = TypeVar("T")


def default_language() -> str:
    language = (locale.getlocale()[0] or "").casefold()
    return "ko" if language.startswith("ko") else "en"


def _from_dict(cls: type[T], value: object) -> T:
    """Load known dataclass fields only, preserving forward compatibility."""
    raw = value if isinstance(value, dict) else {}
    known = {item.name for item in fields(cls)}
    return cls(**{key: val for key, val in raw.items() if key in known})


@dataclass(slots=True)
class TargetSpec:
    mode: str = "monitor"
    executable: str = ""
    active_only: bool = True

    @classmethod
    def from_dict(cls, raw: object) -> "TargetSpec":
        data = raw if isinstance(raw, dict) else {}
        executable = str(data.get("executable", "")).strip()
        mode = str(data.get("mode", "")).strip()
        if mode not in {"monitor", "active", "application"}:
            mode = "application" if executable else "monitor"
        return cls(mode=mode, executable=executable, active_only=bool(data.get("active_only", True)))


@dataclass(slots=True)
class ShapeLayer:
    """One user-authored primitive positioned relative to the fixed center."""

    layer_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = "새 도형"
    shape: str = "line"
    visible: bool = True
    x: int = 0
    y: int = 0
    width: int = 30
    height: int = 30
    rotation: int = 0
    thickness: int = 2
    stroke_color: str = "#ff3b30"
    outline_color: str = "#000000"
    outline_thickness: int = 0
    fill_color: str = "#ff3b30"
    opacity: int = 230
    cap_style: str = "round"
    cap_angle: int = 45
    mirror_horizontal: bool = False
    mirror_vertical: bool = False
    rotation_symmetry: bool = False
    circular_pattern: bool = False
    pattern_angle: int = 30
    pattern_copies: int = 1
    arc_radius: int = 15
    arc_start_angle: int = 0
    arc_span_angle: int = 90
    image_path: str = ""
    color_key_enabled: bool = False
    color_key: str = "#ffffff"
    color_key_tolerance: int = 0
    color_key_softness: int = 8

    @classmethod
    def from_dict(cls, raw: object) -> "ShapeLayer":
        data = raw if isinstance(raw, dict) else {}
        known = {item.name for item in fields(cls)}
        layer = cls(**{key: val for key, val in data.items() if key in known})
        if bool(data.get("rotation_symmetry", False)) and "circular_pattern" not in data:
            layer.circular_pattern = True
            layer.pattern_angle = 90
            layer.pattern_copies = 3
            layer.rotation_symmetry = False
        if layer.shape == "arc" and "arc_radius" not in data:
            layer.arc_radius = max(1, round(max(layer.width, layer.height) / 2))
        layer.pattern_copies = max(0, min(3, int(layer.pattern_copies)))
        layer.cap_angle = max(15, min(75, int(layer.cap_angle)))
        layer.arc_radius = max(1, min(1000, int(layer.arc_radius)))
        layer.arc_span_angle = max(-360, min(360, int(layer.arc_span_angle)))
        return layer


def default_shape_layers() -> list[ShapeLayer]:
    return [
        ShapeLayer(name="가로선", x=16, width=22, height=0, mirror_horizontal=True),
        ShapeLayer(name="세로선", y=16, width=22, height=0, rotation=90, mirror_vertical=True),
        ShapeLayer(name="기준점 링", shape="ring", width=7, height=7, thickness=2),
    ]


def body_reference_preset(name: str) -> list[ShapeLayer]:
    """Bundled body-image presets anchored to screen bottom-center."""
    if name == "arms":
        return [
            ShapeLayer(name="왼손", shape="image", image_path="builtin://body/left_hand",
                       x=-340, y=-150, width=620, height=300, opacity=130),
            ShapeLayer(name="오른손", shape="image", image_path="builtin://body/right_hand",
                       x=340, y=-150, width=620, height=300, opacity=130),
        ]
    if name == "body":
        return [
            ShapeLayer(name="가상 코", shape="image", image_path="builtin://body/nose",
                       x=0, y=-105, width=210, height=210, opacity=120),
            ShapeLayer(name="왼손", shape="image", image_path="builtin://body/left_hand",
                       x=-340, y=-150, width=620, height=300, opacity=130),
            ShapeLayer(name="오른손", shape="image", image_path="builtin://body/right_hand",
                       x=340, y=-150, width=620, height=300, opacity=130),
        ]
    return [ShapeLayer(
        name="가상 코", shape="image", image_path="builtin://body/nose",
        x=0, y=-105, width=210, height=210, opacity=120,
    )]


@dataclass(slots=True)
class CrosshairSettings:
    enabled: bool = True
    horizontal_length: int = 18
    vertical_length: int = 18
    thickness: int = 2
    color: str = "#ffffff"
    opacity: int = 220
    outline_color: str = "#000000"
    outline_thickness: int = 1
    gap: int = 5
    center_shape: str = "ring"
    center_size: int = 6
    center_color: str = "#ffffff"
    center_opacity: int = 230
    offset_x: int = 0
    offset_y: int = 0
    antialiasing: bool = True
    layers: list[ShapeLayer] = field(default_factory=default_shape_layers)

    @classmethod
    def from_dict(cls, raw: object) -> "CrosshairSettings":
        data = raw if isinstance(raw, dict) else {}
        known = {item.name for item in fields(cls)} - {"layers"}
        settings = cls(**{key: val for key, val in data.items() if key in known})
        layers_raw = data.get("layers")
        if isinstance(layers_raw, list):
            settings.layers = [ShapeLayer.from_dict(item) for item in layers_raw if isinstance(item, dict)]
        else:
            settings.layers = settings._legacy_layers()
        return settings

    def _legacy_layers(self) -> list[ShapeLayer]:
        layers = [
            ShapeLayer(
                name="가로선", x=self.gap + self.horizontal_length // 2,
                width=self.horizontal_length, height=0, thickness=self.thickness,
                stroke_color=self.color, outline_color=self.outline_color,
                outline_thickness=self.outline_thickness,
                opacity=self.opacity, cap_style="round",
                mirror_horizontal=True,
            ),
            ShapeLayer(
                name="세로선", y=self.gap + self.vertical_length // 2,
                width=self.vertical_length, height=0, rotation=90,
                thickness=self.thickness, stroke_color=self.color,
                outline_color=self.outline_color, outline_thickness=self.outline_thickness,
                opacity=self.opacity, cap_style="round", mirror_vertical=True,
            ),
        ]
        if self.center_shape != "none":
            shape = "dot" if self.center_shape == "dot" else ("rect" if self.center_shape == "square" else "ring")
            layers.append(ShapeLayer(
                name="화면 기준점", shape=shape, width=self.center_size,
                height=self.center_size, thickness=max(1, self.thickness),
                stroke_color=self.center_color, fill_color=self.center_color,
                outline_color=self.outline_color, outline_thickness=self.outline_thickness,
                opacity=self.center_opacity,
            ))
        return layers


@dataclass(slots=True)
class PointerSettings:
    enabled: bool = False
    active_only: bool = True
    update_rate: int = 0
    offset_x: int = 0
    offset_y: int = 0
    antialiasing: bool = True
    layers: list[ShapeLayer] = field(default_factory=lambda: [ShapeLayer(
        name="커서 링", shape="ring", width=34, height=34, thickness=3,
        stroke_color="#ffff00", outline_color="#000000", outline_thickness=2,
        fill_color="#ffff00", opacity=220,
    )])

    @classmethod
    def from_dict(cls, raw: object) -> "PointerSettings":
        data = raw if isinstance(raw, dict) else {}
        common = {
            "enabled": bool(data.get("enabled", False)),
            "active_only": bool(data.get("active_only", True)),
            "update_rate": int(data.get("update_rate", 0)),
            "offset_x": int(data.get("offset_x", 0)),
            "offset_y": int(data.get("offset_y", 0)),
            "antialiasing": bool(data.get("antialiasing", True)),
        }
        common["update_rate"] = common["update_rate"] if common["update_rate"] in {0, 60, 120, 144, 165, 240} else 0
        layers_raw = data.get("layers")
        if isinstance(layers_raw, list):
            return cls(**common, layers=[ShapeLayer.from_dict(item) for item in layers_raw if isinstance(item, dict)])
        size = max(8, min(600, int(data.get("size", 34))))
        width = max(8, min(600, int(data.get("width", size))))
        height = max(8, min(600, int(data.get("height", size))))
        shape = str(data.get("shape", "ring"))
        shared = dict(
            width=width, height=height, thickness=max(2, int(data.get("outline_thickness", 2))),
            stroke_color=str(data.get("color", "#ffff00")), fill_color=str(data.get("color", "#ffff00")),
            outline_color=str(data.get("outline_color", "#000000")),
            outline_thickness=max(0, int(data.get("outline_thickness", 2))), opacity=int(data.get("opacity", 220)),
        )
        image_path = str(data.get("image_path", ""))
        if image_path:
            layers = [ShapeLayer(
                name="커서 이미지", shape="image", image_path=image_path,
                color_key_enabled=bool(data.get("color_key_enabled", False)),
                color_key=str(data.get("color_key", "#ffffff")),
                color_key_tolerance=int(data.get("color_key_tolerance", 0)),
                color_key_softness=int(data.get("color_key_softness", 8)), **shared,
            )]
        elif shape == "cross":
            layers = [
                ShapeLayer(name="커서 가로선", **{**shared, "height": 1}),
                ShapeLayer(name="커서 세로선", rotation=90, **{**shared, "height": 1}),
            ]
        else:
            mapped_shape = {"circle": "ellipse", "ring": "ring", "arrow": "arrow"}.get(shape, "ring")
            layers = [ShapeLayer(name="커서 도형", shape=mapped_shape, **shared)]
        return cls(**common, layers=layers)


@dataclass(slots=True)
class VignetteSettings:
    enabled: bool = False
    opacity: int = 145
    center_width: int = 62
    center_height: int = 58
    softness: int = 30
    shape: str = "ellipse"
    color: str = "#000000"
    offset_x: int = 0
    offset_y: int = 0

    @classmethod
    def from_dict(cls, raw: object) -> "VignetteSettings":
        item = _from_dict(cls, raw)
        item.opacity = max(0, min(255, int(item.opacity)))
        item.center_width = max(10, min(95, int(item.center_width)))
        item.center_height = max(10, min(95, int(item.center_height)))
        item.softness = max(1, min(100, int(item.softness)))
        item.shape = item.shape if item.shape in {"ellipse", "rounded_rect"} else "ellipse"
        return item


@dataclass(slots=True)
class BodyReferenceSettings:
    enabled: bool = False
    preset: str = "body"
    antialiasing: bool = True
    layers: list[ShapeLayer] = field(default_factory=lambda: body_reference_preset("body"))

    @classmethod
    def from_dict(cls, raw: object) -> "BodyReferenceSettings":
        data = raw if isinstance(raw, dict) else {}
        preset = str(data.get("preset", "body"))
        layers_raw = data.get("layers")
        layers = (
            [ShapeLayer.from_dict(item) for item in layers_raw if isinstance(item, dict)]
            if isinstance(layers_raw, list) else body_reference_preset(preset)
        )
        previous_sizes = {
            "builtin://body/nose": ((0, -52, 105, 105), (0, -105, 210, 210)),
            "builtin://body/left_hand": ((-340, -75, 310, 150), (-340, -150, 620, 300)),
            "builtin://body/right_hand": ((340, -75, 310, 150), (340, -150, 620, 300)),
        }
        for layer in layers:
            sizes = previous_sizes.get(layer.image_path)
            if sizes and (layer.x, layer.y, layer.width, layer.height) == sizes[0]:
                layer.x, layer.y, layer.width, layer.height = sizes[1]
        return cls(
            enabled=bool(data.get("enabled", False)), preset=preset,
            antialiasing=bool(data.get("antialiasing", True)), layers=layers,
        )


@dataclass(slots=True)
class GuideLineSettings:
    enabled: bool = False
    horizontal: bool = True
    vertical: bool = False
    offset_x: int = 0
    offset_y: int = 0
    length_percent: int = 76
    horizontal_margin: int | None = 230
    vertical_margin: int | None = 130
    horizontal_length: int | None = 730
    vertical_length: int | None = 410
    thickness: int = 2
    center_gap: int = 0
    horizontal_gap: int | None = None
    vertical_gap: int | None = None
    opacity: int = 80
    color: str = "#ffffff"
    center_cap: str = "round"
    center_cap_angle: int = 45
    dashed: bool = False
    dash_length: int = 12
    dash_gap: int = 8

    @classmethod
    def from_dict(cls, raw: object) -> "GuideLineSettings":
        data = raw if isinstance(raw, dict) else {}
        item = _from_dict(cls, data)
        if "length_percent" in data and "horizontal_margin" not in data:
            item.horizontal_margin = None
        if "length_percent" in data and "vertical_margin" not in data:
            item.vertical_margin = None
        item.length_percent = max(5, min(100, int(item.length_percent)))
        if item.horizontal_margin is not None:
            item.horizontal_margin = max(0, min(4000, int(item.horizontal_margin)))
        if item.vertical_margin is not None:
            item.vertical_margin = max(0, min(4000, int(item.vertical_margin)))
        # Older profiles described the outer screen margin. Convert it to the
        # length of one edge-anchored segment at the former 1920x1080 size.
        if "horizontal_length" not in data or item.horizontal_length is None:
            if item.horizontal_margin is not None:
                item.horizontal_length = (1920 - item.horizontal_margin * 2) / 2
            else:
                item.horizontal_length = 1920 * item.length_percent / 200
        if "vertical_length" not in data or item.vertical_length is None:
            if item.vertical_margin is not None:
                item.vertical_length = (1080 - item.vertical_margin * 2) / 2
            else:
                item.vertical_length = 1080 * item.length_percent / 200
        item.horizontal_length = max(1, min(4000, round(item.horizontal_length)))
        item.vertical_length = max(1, min(4000, round(item.vertical_length)))
        item.thickness = max(1, min(100, int(item.thickness)))
        item.center_gap = 0
        item.horizontal_gap = item.vertical_gap = None
        item.opacity = max(0, min(255, int(item.opacity)))
        item.center_cap = item.center_cap if item.center_cap in {"round", "flat", "triangle"} else "round"
        item.center_cap_angle = max(15, min(75, int(item.center_cap_angle)))
        item.dash_length = max(1, min(200, int(item.dash_length)))
        item.dash_gap = max(1, min(200, int(item.dash_gap)))
        return item


@dataclass(slots=True)
class GridSettings:
    enabled: bool = False
    columns: int = 3
    rows: int = 3
    thickness: int = 1
    opacity: int = 45
    color: str = "#ffffff"
    margin: int = 0
    dashed: bool = False
    dash_length: int = 10
    dash_gap: int = 8
    horizontal_dashed: bool = False
    horizontal_dash_length: int = 10
    horizontal_dash_gap: int = 8
    horizontal_dash_offset: int = 0
    vertical_dashed: bool = False
    vertical_dash_length: int = 10
    vertical_dash_gap: int = 8
    vertical_dash_offset: int = 0
    emphasize_center: bool = False

    @classmethod
    def from_dict(cls, raw: object) -> "GridSettings":
        data = raw if isinstance(raw, dict) else {}
        item = _from_dict(cls, data)
        if "horizontal_dashed" not in data:
            item.horizontal_dashed = bool(data.get("dashed", item.dashed))
            item.horizontal_dash_length = int(data.get("dash_length", item.dash_length))
            item.horizontal_dash_gap = int(data.get("dash_gap", item.dash_gap))
        if "vertical_dashed" not in data:
            item.vertical_dashed = bool(data.get("dashed", item.dashed))
            item.vertical_dash_length = int(data.get("dash_length", item.dash_length))
            item.vertical_dash_gap = int(data.get("dash_gap", item.dash_gap))
        item.columns = max(2, min(16, int(item.columns)))
        item.rows = max(2, min(16, int(item.rows)))
        item.thickness = max(1, min(10, int(item.thickness)))
        item.opacity = max(0, min(255, int(item.opacity)))
        item.margin = max(0, min(500, int(item.margin)))
        item.dash_length = max(1, min(200, int(item.dash_length)))
        item.dash_gap = max(1, min(200, int(item.dash_gap)))
        item.horizontal_dash_length = max(1, min(200, int(item.horizontal_dash_length)))
        item.horizontal_dash_gap = max(1, min(200, int(item.horizontal_dash_gap)))
        item.horizontal_dash_offset = max(-400, min(400, int(item.horizontal_dash_offset)))
        item.vertical_dash_length = max(1, min(200, int(item.vertical_dash_length)))
        item.vertical_dash_gap = max(1, min(200, int(item.vertical_dash_gap)))
        item.vertical_dash_offset = max(-400, min(400, int(item.vertical_dash_offset)))
        return item


@dataclass(slots=True)
class MotionAssistSettings:
    enabled: bool = True
    vignette: VignetteSettings = field(default_factory=VignetteSettings)
    body: BodyReferenceSettings = field(default_factory=BodyReferenceSettings)
    guides: GuideLineSettings = field(default_factory=GuideLineSettings)
    grid: GridSettings = field(default_factory=GridSettings)

    @classmethod
    def from_dict(cls, raw: object) -> "MotionAssistSettings":
        data = raw if isinstance(raw, dict) else {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            vignette=VignetteSettings.from_dict(data.get("vignette")),
            body=BodyReferenceSettings.from_dict(data.get("body")),
            guides=GuideLineSettings.from_dict(data.get("guides")),
            grid=GridSettings.from_dict(data.get("grid")),
        )


@dataclass(slots=True)
class FindEffectSettings:
    enabled: bool = True
    effect: str = "expand"
    color: str = "#00e5ff"
    opacity: int = 230
    max_size: int = 150
    thickness: int = 4
    duration_ms: int = 700
    repeats: int = 1
    speed: int = 100

    @classmethod
    def from_dict(cls, raw: object) -> "FindEffectSettings":
        item = _from_dict(cls, raw)
        if item.effect == "spotlight":
            item.effect = "focus_lines"
        if item.effect not in {"expand", "contract", "flash", "lines", "focus_lines", "grow"}:
            item.effect = "expand"
        return item


@dataclass(slots=True)
class HotkeySettings:
    crosshair: str = "Ctrl+Alt+F9"
    pointer: str = "Ctrl+Alt+F10"
    motion_assist: str = "Ctrl+Alt+F8"
    find: str = "Ctrl+Alt+F11"
    all_overlays: str = "Ctrl+Alt+F12"


@dataclass(slots=True)
class Profile:
    name: str = "기본 프로필"
    enabled: bool = True
    target: TargetSpec = field(default_factory=TargetSpec)
    crosshair: CrosshairSettings = field(default_factory=CrosshairSettings)
    pointer: PointerSettings = field(default_factory=PointerSettings)
    motion_assist: MotionAssistSettings = field(default_factory=MotionAssistSettings)
    find_effect: FindEffectSettings = field(default_factory=FindEffectSettings)
    hotkeys: HotkeySettings = field(default_factory=HotkeySettings)

    @classmethod
    def from_dict(cls, raw: object) -> "Profile":
        data = raw if isinstance(raw, dict) else {}
        return cls(
            name=str(data.get("name", "기본 프로필")),
            enabled=bool(data.get("enabled", True)),
            target=TargetSpec.from_dict(data.get("target")),
            crosshair=CrosshairSettings.from_dict(data.get("crosshair")),
            pointer=PointerSettings.from_dict(data.get("pointer")),
            motion_assist=MotionAssistSettings.from_dict(data.get("motion_assist")),
            find_effect=FindEffectSettings.from_dict(data.get("find_effect")),
            hotkeys=_from_dict(HotkeySettings, data.get("hotkeys")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AppSettings:
    profiles: list[Profile] = field(default_factory=lambda: [Profile()])
    selected_profile: int = 0
    overlays_enabled: bool = True
    start_with_windows: bool = False
    minimize_to_tray: bool = True
    keep_overlay_on_top: bool = True
    language: str = field(default_factory=default_language)
    schema_version: int = 14

    @classmethod
    def from_dict(cls, raw: object) -> "AppSettings":
        data = raw if isinstance(raw, dict) else {}
        profiles_raw = data.get("profiles", [])
        profiles = [Profile.from_dict(item) for item in profiles_raw] if isinstance(profiles_raw, list) else []
        if not profiles:
            profiles = [Profile()]
        schema_version = int(data.get("schema_version", 1))
        if schema_version == 12 and isinstance(profiles_raw, list):
            for profile, source in zip(profiles, profiles_raw):
                guides_raw = source.get("motion_assist", {}).get("guides", {}) if isinstance(source, dict) else {}
                if not isinstance(guides_raw, dict):
                    continue
                guides = profile.motion_assist.guides
                for axis in ("horizontal", "vertical"):
                    if guides_raw.get(f"{axis}_length") is not None:
                        setattr(guides, f"{axis}_length", max(1, min(4000, round(int(guides_raw[f"{axis}_length"]) / 2))))
        if schema_version < 2:
            for profile in profiles:
                if (profile.pointer.offset_x, profile.pointer.offset_y) == (16, 16):
                    profile.pointer.offset_x = 0
                    profile.pointer.offset_y = 0
        selected = int(data.get("selected_profile", 0))
        selected = max(0, min(selected, len(profiles) - 1))
        return cls(
            profiles=profiles,
            selected_profile=selected,
            overlays_enabled=bool(data.get("overlays_enabled", True)),
            start_with_windows=bool(data.get("start_with_windows", False)),
            minimize_to_tray=bool(data.get("minimize_to_tray", True)),
            keep_overlay_on_top=bool(data.get("keep_overlay_on_top", True)),
            language=str(data.get("language", default_language())) if str(data.get("language", default_language())) in {"ko", "en"} else "en",
            schema_version=14,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
