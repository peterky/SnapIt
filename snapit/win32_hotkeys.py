"""Windows RegisterHotKey backend — works better than hooks in some fullscreen apps."""

from __future__ import annotations

import ctypes
import logging
import string
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

logger = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

FUNCTION_KEYS = {f"f{i}": 0x6F + i for i in range(1, 13)}


def _parse_combo(combo: str) -> tuple[int, int] | None:
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    modifiers = 0
    key_name: str | None = None

    for part in parts:
        if part in {"ctrl", "control"}:
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        elif part in {"win", "windows"}:
            modifiers |= MOD_WIN
        else:
            key_name = part

    if not key_name:
        return None

    if key_name in FUNCTION_KEYS:
        return modifiers, FUNCTION_KEYS[key_name]
    if len(key_name) == 1 and key_name in string.digits:
        return modifiers, ord(key_name)
    if key_name in {f"num {d}" for d in string.digits} or key_name.startswith("num"):
        digit = key_name.replace("num", "").strip()
        if digit in string.digits:
            return modifiers, 0x60 + int(digit)
    if len(key_name) == 1 and key_name in string.ascii_lowercase:
        return modifiers, ord(key_name.upper())
    return None


class Win32HotkeyManager:
    def __init__(self) -> None:
        self._handlers: dict[int, Callable[[], None]] = {}
        self._registered: list[int] = []
        self._next_id = 1
        self._hwnd: int | None = None
        self._poll_scheduled = False

    def clear(self) -> None:
        if user32 and self._hwnd:
            for hotkey_id in self._registered:
                user32.UnregisterHotKey(self._hwnd, hotkey_id)
        self._registered.clear()
        self._handlers.clear()
        self._poll_scheduled = False

    def register_all(
        self,
        root: tk.Tk,
        hotkeys: dict[str, str | None],
        handlers: dict[str, Callable[[], None]],
    ) -> list[str]:
        self.clear()
        if user32 is None:
            return ["Win32 hotkeys are only available on Windows."]

        self._hwnd = root.winfo_id()
        errors: list[str] = []

        for shot_type, combo in hotkeys.items():
            if not combo:
                continue
            handler = handlers.get(shot_type)
            if not handler:
                continue

            parsed = _parse_combo(combo)
            if not parsed:
                errors.append(f"Could not parse hotkey {combo}")
                continue

            modifiers, vk = parsed
            hotkey_id = self._next_id
            self._next_id += 1

            if not user32.RegisterHotKey(self._hwnd, hotkey_id, modifiers, vk):
                errors.append(f"Could not register {combo} (may be in use by another app)")
                continue

            self._registered.append(hotkey_id)
            self._handlers[hotkey_id] = handler

        if self._registered and not self._poll_scheduled:
            self._poll_scheduled = True
            self._poll(root)

        return errors

    def _poll(self, root: tk.Tk) -> None:
        if not self._hwnd or not self._handlers:
            self._poll_scheduled = False
            return

        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), self._hwnd, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
            handler = self._handlers.get(int(msg.wParam))
            if handler:
                try:
                    handler()
                except Exception:
                    logger.exception("Win32 hotkey handler failed")

        root.after(10, lambda: self._poll(root))