from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WH_MOUSE_LL = 14
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN = 0x0201, 0x0204, 0x0207, 0x020B
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12


class HotkeyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedHotkey:
    modifiers: int
    key: int
    mouse_button: int = 0


def parse_hotkey(sequence: str, language: str = "ko") -> ParsedHotkey:
    parts = [part.strip().casefold() for part in sequence.split("+") if part.strip()]
    if not parts:
        message = "Choose a key or mouse button." if language == "en" else "키 또는 마우스 버튼을 선택하세요."
        raise HotkeyError(message)
    modifiers = MOD_NOREPEAT
    key_name = parts[-1]
    for part in parts[:-1]:
        if part in {"ctrl", "control"}:
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        elif part in {"win", "meta"}:
            modifiers |= MOD_WIN
        else:
            message = f"Unsupported modifier: {part}" if language == "en" else f"지원하지 않는 보조 키: {part}"
            raise HotkeyError(message)
    if key_name.startswith("mouse") and key_name[5:].isdigit() and 1 <= int(key_name[5:]) <= 5:
        return ParsedHotkey(modifiers, 0, int(key_name[5:]))
    if len(key_name) == 1 and (key_name.isalpha() or key_name.isdigit()):
        key = ord(key_name.upper())
    elif key_name.startswith("f") and key_name[1:].isdigit() and 1 <= int(key_name[1:]) <= 24:
        key = 0x6F + int(key_name[1:])
    else:
        message = "Use a letter, number, or F1–F24." if language == "en" else "단축키는 문자, 숫자 또는 F1~F24를 사용하세요."
        raise HotkeyError(message)
    return ParsedHotkey(modifiers, key)


class _HotkeyReceiver(QWidget):
    activated = Signal(int)

    def nativeEvent(self, _event_type, message: int) -> tuple[bool, int]:  # noqa: N802
        if os.name == "nt":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.activated.emit(int(msg.wParam))
                return True, 0
        return False, 0


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HotkeyManager(QObject):
    activated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._names: dict[int, str] = {}
        self._mouse_bindings: dict[tuple[int, int], str] = {}
        self._mouse_hook = None
        self._mouse_proc = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
        if self._user32 is not None:
            self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self._user32.RegisterHotKey.restype = wintypes.BOOL
            self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self._user32.UnregisterHotKey.restype = wintypes.BOOL
            self._user32.GetAsyncKeyState.argtypes=[ctypes.c_int];self._user32.GetAsyncKeyState.restype=ctypes.c_short
            self._user32.SetWindowsHookExW.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD];self._user32.SetWindowsHookExW.restype=ctypes.c_void_p
            self._user32.CallNextHookEx.argtypes=[ctypes.c_void_p,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM];self._user32.CallNextHookEx.restype=ctypes.c_ssize_t
            self._user32.UnhookWindowsHookEx.argtypes=[ctypes.c_void_p];self._user32.UnhookWindowsHookEx.restype=wintypes.BOOL
        self._receiver = _HotkeyReceiver()
        self._receiver.activated.connect(self._dispatch)
        self._receiver_hwnd = int(self._receiver.winId()) if self._user32 is not None else 0

    def register_all(self, bindings: dict[str, str], language: str = "ko") -> list[str]:
        self.unregister_all()
        errors: list[str] = []
        for hotkey_id, (name, sequence) in enumerate(bindings.items(), start=101):
            try:
                parsed = parse_hotkey(sequence, language)
            except HotkeyError as exc:
                errors.append(f"{sequence}: {exc}")
                continue
            if parsed.mouse_button:
                modifiers=parsed.modifiers & ~MOD_NOREPEAT;binding=(parsed.mouse_button,modifiers)
                if binding in self._mouse_bindings:
                    reason="Duplicate mouse shortcut." if language=="en" else "같은 마우스 단축키가 중복되었습니다."
                    errors.append(f"{sequence}: {reason}")
                else:self._mouse_bindings[binding]=name
                continue
            if self._user32 is None or not self._user32.RegisterHotKey(
                self._receiver_hwnd, hotkey_id, parsed.modifiers, parsed.key
            ):
                reason = "Already used by another application or cannot be registered." if language == "en" else "다른 프로그램에서 사용 중이거나 등록할 수 없습니다."
                errors.append(f"{sequence}: {reason}")
                continue
            self._names[hotkey_id] = name
        if self._mouse_bindings and not self._install_mouse_hook():
            message="Mouse shortcuts could not be registered." if language=="en" else "마우스 단축키를 등록할 수 없습니다."
            errors.append(message);self._mouse_bindings.clear()
        return errors

    def _install_mouse_hook(self) -> bool:
        if self._user32 is None:return False
        callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        self._mouse_proc=callback_type(self._mouse_event)
        kernel32=ctypes.WinDLL("kernel32",use_last_error=True);kernel32.GetModuleHandleW.restype=ctypes.c_void_p
        self._mouse_hook=self._user32.SetWindowsHookExW(WH_MOUSE_LL,ctypes.cast(self._mouse_proc,ctypes.c_void_p),kernel32.GetModuleHandleW(None),0)
        return bool(self._mouse_hook)

    def _mouse_event(self,code,wparam,lparam):
        if code>=0:
            button={WM_LBUTTONDOWN:1,WM_RBUTTONDOWN:2,WM_MBUTTONDOWN:3}.get(int(wparam),0)
            if int(wparam)==WM_XBUTTONDOWN:
                data=ctypes.cast(lparam,ctypes.POINTER(_MSLLHOOKSTRUCT)).contents.mouseData;button=3+((data>>16)&0xffff)
            if button:
                modifiers=0
                if self._user32.GetAsyncKeyState(VK_CONTROL)&0x8000:modifiers|=MOD_CONTROL
                if self._user32.GetAsyncKeyState(VK_MENU)&0x8000:modifiers|=MOD_ALT
                if self._user32.GetAsyncKeyState(VK_SHIFT)&0x8000:modifiers|=MOD_SHIFT
                name=self._mouse_bindings.get((button,modifiers))
                if name:self.activated.emit(name)
        return self._user32.CallNextHookEx(self._mouse_hook,code,wparam,lparam)

    def unregister_all(self) -> None:
        if self._user32 is not None:
            for hotkey_id in tuple(self._names):
                self._user32.UnregisterHotKey(self._receiver_hwnd, hotkey_id)
            if self._mouse_hook:self._user32.UnhookWindowsHookEx(self._mouse_hook)
        self._names.clear()
        self._mouse_bindings.clear();self._mouse_hook=None;self._mouse_proc=None

    def _dispatch(self, hotkey_id: int) -> None:
        name = self._names.get(hotkey_id)
        if name:
            self.activated.emit(name)

    def close(self) -> None:
        self.unregister_all()
        self._receiver.close()
