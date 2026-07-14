"""Global low-level keyboard hook — most reliable hotkey path on Windows."""

from __future__ import annotations

import ctypes
import logging
import string
import sys
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

if sys.platform != "win32":
    user32 = None
else:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
HC_ACTION = 0

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

NUMPAD_VK = {str(i): 0x60 + i for i in range(10)}
FUNCTION_VK = {f"f{i}": 0x6F + i for i in range(1, 13)}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_uint32),
        ("scanCode", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


def _vk_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _combo_to_matchers(combo: str) -> list[tuple[frozenset[str], frozenset[int]]]:
    """Return modifier sets and acceptable VK codes (main + numpad for digits)."""
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    modifiers: set[str] = set()
    key_name: str | None = None
    for part in parts:
        if part in {"ctrl", "control"}:
            modifiers.add("ctrl")
        elif part == "alt":
            modifiers.add("alt")
        elif part == "shift":
            modifiers.add("shift")
        elif part in {"win", "windows"}:
            modifiers.add("win")
        else:
            key_name = part

    if not key_name:
        return []

    vk_codes: set[int] = set()
    if key_name in FUNCTION_VK:
        vk_codes.add(FUNCTION_VK[key_name])
    elif len(key_name) == 1 and key_name in string.ascii_lowercase:
        vk_codes.add(ord(key_name.upper()))
    elif len(key_name) == 1 and key_name in string.digits:
        vk_codes.add(ord(key_name))
        vk_codes.add(NUMPAD_VK[key_name])
    elif key_name.startswith("num ") and key_name[4:] in NUMPAD_VK:
        vk_codes.add(NUMPAD_VK[key_name[4:]])
    elif key_name in NUMPAD_VK:
        vk_codes.add(NUMPAD_VK[key_name])
        vk_codes.add(ord(key_name))

    return [(frozenset(modifiers), frozenset(vk_codes))]


def _modifiers_active(required: frozenset[str]) -> bool:
    ctrl = _vk_down(VK_CONTROL)
    shift = _vk_down(VK_SHIFT)
    alt = _vk_down(VK_MENU)
    win = _vk_down(VK_LWIN) or _vk_down(VK_RWIN)

    if "ctrl" in required and not ctrl:
        return False
    if "shift" in required and not shift:
        return False
    if "alt" in required and not alt:
        return False
    if "win" in required and not win:
        return False

    # Require exact modifier match for combos that specify modifiers.
    if "ctrl" not in required and ctrl:
        return False
    if "shift" not in required and shift:
        return False
    if "alt" not in required and alt:
        return False
    if "win" not in required and win:
        return False
    return True


class LowLevelHotkeyHook:
    """Install WH_KEYBOARD_LL and pump messages on a dedicated thread."""

    def __init__(self) -> None:
        self._bindings: list[tuple[frozenset[str], frozenset[int], Callable[[], None]]] = []
        self._suppress = True
        self._hook = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._proc_ref = None

    def clear(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            if user32:
                user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=2.0)
        self._thread = None
        self._hook = None
        self._bindings.clear()

    def register_all(
        self,
        hotkeys: dict[str, str | None],
        handlers: dict[str, Callable[[], None]],
        suppress: bool = True,
    ) -> list[str]:
        self.clear()
        if user32 is None:
            return ["Low-level hook is only available on Windows."]

        self._suppress = suppress
        errors: list[str] = []

        for shot_type, combo in hotkeys.items():
            if not combo:
                continue
            handler = handlers.get(shot_type)
            if not handler:
                continue
            matchers = _combo_to_matchers(combo)
            if not matchers:
                errors.append(f"Could not parse hotkey {combo}")
                continue
            for mods, vks in matchers:
                self._bindings.append((mods, vks, handler))

        if not self._bindings:
            return errors

        self._running = True
        self._thread = threading.Thread(target=self._thread_main, name="SnapItHotkeyHook", daemon=True)
        self._thread.start()
        return errors

    def _thread_main(self) -> None:
        if not user32:
            return

        LowLevelProc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

        def hook_proc(code: int, wparam: ctypes.c_size_t, lparam: ctypes.c_ssize_t) -> int:
            if code == HC_ACTION and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(kb.vkCode)
                for mods, vks, handler in self._bindings:
                    if vk in vks and _modifiers_active(mods):
                        try:
                            handler()
                        except Exception:
                            logger.exception("Low-level hotkey handler failed")
                        if self._suppress:
                            return 1
                        break
            return user32.CallNextHookEx(self._hook, code, wparam, lparam)

        self._proc_ref = LowLevelProc(hook_proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc_ref, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            logger.error("SetWindowsHookExW failed")
            return

        msg = ctypes.wintypes.MSG()
        while self._running:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0 or result == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None