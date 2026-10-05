from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from ctypes import wintypes

from .geometry import Rect


IS_WINDOWS = os.name == "nt"


@dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    executable: str
    executable_path: str = ""

    @property
    def label(self) -> str:
        return Path(self.executable).stem or "Application"


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    handle: int
    device_name: str
    rect: Rect


if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        dwmapi = None

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_APPWINDOW = 0x00040000
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_NOOWNERZORDER = 0x0200
    GW_OWNER = 4
    DWMWA_CLOAKED = 14
    GA_ROOT = 2
    MONITOR_DEFAULTTONEAREST = 2

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    user32.SetProcessDPIAware.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    if dwmapi is not None:
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        # Per-monitor v2, dynamically resolved for older Windows compatibility.
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = wintypes.BOOL
        set_context(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _process_path(pid: int) -> str:
    """Read only the executable path metadata with the least process permission."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_top_level_windows() -> list[WindowInfo]:
    if not IS_WINDOWS:
        return []
    found: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
            return True
        if user32.GetWindow(hwnd, GW_OWNER) and not (ex_style & WS_EX_APPWINDOW):
            return True
        if dwmapi is not None:
            cloaked = wintypes.DWORD()
            if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
                return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return True
        path = _process_path(int(pid.value))
        found.append(WindowInfo(int(hwnd), int(pid.value), title, Path(path).name if path else "", path))
        return True

    user32.EnumWindows(visit, 0)
    return sorted(found, key=lambda item: item.label.casefold())


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0) if IS_WINDOWS else 0


def is_window_usable(hwnd: int) -> bool:
    return bool(IS_WINDOWS and hwnd and user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd))


def is_own_window(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) == os.getpid()


def client_rect_on_screen(hwnd: int) -> Rect | None:
    if not is_window_usable(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return Rect(origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)


def get_cursor_pos() -> tuple[int, int] | None:
    if not IS_WINDOWS:
        return None
    point = wintypes.POINT()
    return (point.x, point.y) if user32.GetCursorPos(ctypes.byref(point)) else None


def _monitor_info(handle: int) -> MonitorInfo | None:
    if not IS_WINDOWS or not handle:
        return None
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
        return None
    rect = info.rcMonitor
    return MonitorInfo(
        int(handle),
        info.szDevice,
        Rect(rect.left, rect.top, rect.right, rect.bottom),
    )


def monitor_for_window(hwnd: int) -> MonitorInfo | None:
    if not IS_WINDOWS or not hwnd:
        return None
    return _monitor_info(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))


def monitor_for_point(point: tuple[int, int]) -> MonitorInfo | None:
    if not IS_WINDOWS:
        return None
    native_point = wintypes.POINT(point[0], point[1])
    return _monitor_info(user32.MonitorFromPoint(native_point, MONITOR_DEFAULTTONEAREST))


def find_matching_window(executable: str, title: str) -> WindowInfo | None:
    return match_window(list_top_level_windows(), executable, title)


def match_window(windows: list[WindowInfo], executable: str, title: str = "", preferred_hwnd: int = 0) -> WindowInfo | None:
    exe_key = executable.casefold().strip()
    title_key = title.casefold().strip()
    executable_matches = [item for item in windows if exe_key and item.executable.casefold() == exe_key]
    if executable_matches:
        return next((item for item in executable_matches if item.hwnd == preferred_hwnd), executable_matches[0])
    if title_key:
        return next((item for item in windows if title_key in item.title.casefold()), None)
    return None


def apply_click_through(hwnd: int) -> None:
    if not IS_WINDOWS or not hwnd:
        return
    get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    style = get_style(hwnd, GWL_EXSTYLE)
    set_style(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def ensure_topmost(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    return bool(user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
    ))


def remove_topmost(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    return bool(user32.SetWindowPos(
        hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
    ))


def set_start_with_windows(enabled: bool, command: str) -> None:
    if not IS_WINDOWS:
        return
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            winreg.SetValueEx(key, APP_DIR_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_DIR_NAME)
            except FileNotFoundError:
                pass


APP_DIR_NAME = "CenterCross"
