from __future__ import annotations

import time
import copy

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from .hotkeys import HotkeyManager
from .geometry import Rect, physical_to_logical_point
from .models import AppSettings, Profile
from .overlays import CrosshairOverlay, FindEffectOverlay, MotionAssistOverlay, PointerOverlay
from .storage import SettingsStore
from .winapi import (
    client_rect_on_screen, ensure_topmost, foreground_window, get_cursor_pos, list_top_level_windows,
    is_own_window, match_window, monitor_for_point, monitor_for_window, remove_topmost,
)


class OverlayController(QObject):
    hotkey_errors = Signal(list)
    profile_activated = Signal(int)
    settings_changed = Signal()

    def __init__(self, settings: AppSettings, store: SettingsStore, app) -> None:
        super().__init__()
        self.settings = settings
        self.store = store
        self.crosshair = CrosshairOverlay()
        self.pointer = PointerOverlay()
        self.motion = MotionAssistOverlay()
        self.effect = FindEffectOverlay()
        self.hotkeys = HotkeyManager()
        self.hotkeys.activated.connect(self.handle_hotkey)
        self.last_hotkey_errors: list[str] = []
        self._visual_settings = {}
        self._target_hwnd = 0
        self._last_target_check = 0.0
        self._last_discovery = 0.0
        self._last_topmost_check = 0.0
        self._cursor_coordinate_mapping: tuple[Rect, Rect] | None = None
        self._last_cursor_mapping_check = 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self._pointer_interval())
        self.timer.timeout.connect(self._update)
        self.apply_profile()
        self.timer.start()

    @property
    def profile(self) -> Profile:
        return self.settings.profiles[self.settings.selected_profile]

    def apply_profile(self) -> list[str]:
        self._target_hwnd = 0
        self._last_discovery = 0.0
        self._cursor_coordinate_mapping = None
        self.refresh_visuals()
        return self.register_hotkeys()

    def refresh_visuals(self) -> None:
        if not self.profile.enabled or not self.profile.find_effect.enabled:
            self.effect.stop()
        for name,overlay,settings in (("crosshair",self.crosshair,self.profile.crosshair),("pointer",self.pointer,self.profile.pointer),("motion",self.motion,self.profile.motion_assist)):
            if self._visual_settings.get(name)!=settings:
                overlay.set_settings(settings)
                self._visual_settings[name]=copy.deepcopy(settings)
            else:
                overlay.settings=settings
        self._last_target_check = 0.0
        self._update()

    def refresh_topmost(self) -> None:
        """Apply or remove the native topmost state immediately."""
        operation = ensure_topmost if self.settings.keep_overlay_on_top else remove_topmost
        for overlay in (self.motion, self.crosshair, self.pointer, self.effect):
            operation(int(overlay.winId()))
        self._last_topmost_check = 0.0

    def register_hotkeys(self) -> list[str]:
        bindings = self.profile.hotkeys
        errors = self.hotkeys.register_all({
            "find": bindings.find,
            "all": bindings.all_overlays,
        }, self.settings.language)
        self.last_hotkey_errors = list(errors)
        self.hotkey_errors.emit(errors)
        return errors

    def _auto_select_profile(self, foreground: int, windows) -> bool:
        # Keep the user's selected variant when it already matches this app.
        current = self.profile.target
        if self.profile.enabled and current.mode == "application" and current.executable:
            match = match_window(windows, current.executable, preferred_hwnd=foreground)
            if match and match.hwnd == foreground:
                return False
        for index, profile in enumerate(self.settings.profiles):
            if (
                index == self.settings.selected_profile
                or not profile.enabled
                or profile.target.mode != "application"
                or not profile.target.executable
            ):
                continue
            match = match_window(windows, profile.target.executable, preferred_hwnd=foreground)
            if match and match.hwnd == foreground:
                self.settings.selected_profile = index
                self.apply_profile()
                self.profile_activated.emit(index)
                return True
        return False

    @staticmethod
    def _logical_position(position: tuple[int, int], hwnd: int = 0) -> tuple[int, int]:
        """Convert native physical coordinates to the matching Qt screen space."""
        monitor = monitor_for_window(hwnd) if hwnd else monitor_for_point(position)
        if monitor is None:
            return position
        screen = next(
            (item for item in QGuiApplication.screens() if item.name().casefold() == monitor.device_name.casefold()),
            None,
        )
        if screen is None:
            return position
        geometry = screen.geometry()
        logical_rect = Rect(
            geometry.left(), geometry.top(), geometry.right() + 1, geometry.bottom() + 1
        )
        return physical_to_logical_point(position, monitor.rect, logical_rect)

    def _logical_cursor_position(self, position: tuple[int, int]) -> tuple[int, int]:
        """Map cursor coordinates while avoiding a monitor lookup every timer tick."""
        now = time.monotonic();mapping=self._cursor_coordinate_mapping
        inside = bool(mapping and mapping[0].left <= position[0] < mapping[0].right and mapping[0].top <= position[1] < mapping[0].bottom)
        if mapping is None or not inside or now-self._last_cursor_mapping_check>=2.0:
            monitor=monitor_for_point(position);self._last_cursor_mapping_check=now
            if monitor is None:return position
            screen=next((item for item in QGuiApplication.screens() if item.name().casefold()==monitor.device_name.casefold()),None)
            if screen is None:return position
            geometry=screen.geometry();mapping=(monitor.rect,Rect(geometry.left(),geometry.top(),geometry.right()+1,geometry.bottom()+1));self._cursor_coordinate_mapping=mapping
        return physical_to_logical_point(position,mapping[0],mapping[1])

    @staticmethod
    def _logical_rect(rect: Rect, hwnd: int = 0) -> Rect:
        monitor = monitor_for_window(hwnd) if hwnd else monitor_for_point(rect.center)
        if monitor is None:return rect
        screen=next((item for item in QGuiApplication.screens() if item.name().casefold()==monitor.device_name.casefold()),None)
        if screen is None:return rect
        geometry=screen.geometry();logical=Rect(geometry.left(),geometry.top(),geometry.right()+1,geometry.bottom()+1)
        left,top=physical_to_logical_point((rect.left,rect.top),monitor.rect,logical)
        right,bottom=physical_to_logical_point((rect.right,rect.bottom),monitor.rect,logical)
        return Rect(left,top,max(left+1,right),max(top+1,bottom))

    def _pointer_interval(self, logical_position: tuple[int, int] | None = None) -> int:
        rate = self.profile.pointer.update_rate
        if rate <= 0:
            screen = QGuiApplication.screenAt(QPoint(*logical_position)) if logical_position else QGuiApplication.primaryScreen()
            rate = round(screen.refreshRate()) if screen and screen.refreshRate() > 1 else 60
        return max(4, min(33, round(1000 / max(30, rate))))

    def _update(self, force_target: bool = False) -> None:
        now = time.monotonic()
        if force_target or now - self._last_target_check >= .12:
            self._last_target_check = now
            foreground = foreground_window()
            mode = self.profile.target.mode
            if force_target or now - self._last_discovery >= 1.0:
                self._last_discovery = now
                windows = list_top_level_windows()
                if self._auto_select_profile(foreground, windows):
                    return
                mode = self.profile.target.mode
                if mode == "application":
                    target = match_window(windows, self.profile.target.executable, preferred_hwnd=foreground)
                    self._target_hwnd = target.hwnd if target else 0
            if mode == "active":
                self._target_hwnd = foreground if not is_own_window(foreground) else 0
            elif mode == "monitor":
                self._target_hwnd = 0
            mode = self.profile.target.mode
            if mode == "monitor":
                monitor = monitor_for_window(foreground)
                if monitor is None:
                    cursor = get_cursor_pos()
                    monitor = monitor_for_point(cursor) if cursor else None
                rect = monitor.rect if monitor else None
                target_active = True
            else:
                rect = client_rect_on_screen(self._target_hwnd)
                target_active = mode == "active" or bool(self._target_hwnd and foreground == self._target_hwnd)
            show_crosshair = bool(
                self.settings.overlays_enabled
                and self.profile.enabled
                and self.profile.crosshair.enabled
                and rect
                and target_active
            )
            if show_crosshair and rect:
                x, y = self._logical_position(rect.center, self._target_hwnd)
                self.crosshair.move(x + self.profile.crosshair.offset_x - self.crosshair.width() // 2,
                                    y + self.profile.crosshair.offset_y - self.crosshair.height() // 2)
                self.crosshair.show()
            else:
                self.crosshair.hide()
            show_motion = bool(
                self.settings.overlays_enabled
                and self.profile.enabled
                and self.motion.any_enabled()
                and rect
                and target_active
            )
            if show_motion and rect:
                logical_rect=self._logical_rect(rect,self._target_hwnd)
                geometry=(logical_rect.left,logical_rect.top,logical_rect.width,logical_rect.height)
                if self.motion.geometry().getRect()!=geometry:self.motion.setGeometry(*geometry)
                self.motion.show()
                if self.crosshair.isVisible():self.crosshair.raise_()
            else:self.motion.hide()
            show_pointer = bool(
                self.settings.overlays_enabled
                and self.profile.enabled
                and self.profile.pointer.enabled
                and rect
                and target_active
            )
            self.pointer.setVisible(show_pointer)
            desired_interval = self._pointer_interval() if show_pointer else 120
            if self.timer.interval() != desired_interval:
                self.timer.setInterval(desired_interval)
        if self.pointer.isVisible():
            position = get_cursor_pos()
            if position:
                logical = self._logical_cursor_position(position)
                desired_interval = self._pointer_interval(logical)
                if self.timer.interval() != desired_interval:
                    self.timer.setInterval(desired_interval)
                target_x = logical[0] + self.profile.pointer.offset_x - self.pointer.width() // 2
                target_y = logical[1] + self.profile.pointer.offset_y - self.pointer.height() // 2
                if self.pointer.x() != target_x or self.pointer.y() != target_y:
                    self.pointer.move(target_x, target_y)
        if self.settings.keep_overlay_on_top and now - self._last_topmost_check >= 1.0:
            self._last_topmost_check = now
            for overlay in (self.motion, self.crosshair, self.pointer, self.effect):
                if overlay.isVisible():
                    ensure_topmost(int(overlay.winId()))

    def handle_hotkey(self, action: str) -> None:
        if action == "all":
            self.settings.overlays_enabled = not self.settings.overlays_enabled
        elif action == "find":
            position = get_cursor_pos()
            if (
                position
                and self.settings.overlays_enabled
                and self.profile.enabled
                and self.profile.find_effect.enabled
            ):
                self.effect.play(self._logical_position(position), self.profile.find_effect)
        self.store.save(self.settings)
        self._update(force_target=True)
        self.settings_changed.emit()

    def preview_effect(self) -> None:
        position = get_cursor_pos()
        if position:
            self.effect.play(self._logical_position(position), self.profile.find_effect)

    def close(self) -> None:
        self.timer.stop()
        self.hotkeys.close()
        self.effect.stop()
        self.crosshair.close()
        self.pointer.close()
        self.motion.close()
        self.effect.close()
