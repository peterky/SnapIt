"""Global hotkey registration and capture-assist utilities."""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable

import keyboard

from snapit.config import find_hotkey_conflicts, normalize_combo

if sys.platform == "win32":
    from snapit.win32_hotkeys import Win32HotkeyManager
    from snapit.win32_ll_hook import LowLevelHotkeyHook

logger = logging.getLogger(__name__)

_HOTKEY_DEBOUNCE_SECONDS = 0.35

_NUMPAD_ALIASES = {str(digit): f"num {digit}" for digit in range(10)}


def _hotkey_variants(combo: str) -> list[str]:
    variants = [combo]
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    key_parts = [part for part in parts if part not in {"ctrl", "alt", "shift", "win"}]
    if len(key_parts) == 1 and key_parts[0] in _NUMPAD_ALIASES:
        modifiers = [part for part in parts if part in {"ctrl", "alt", "shift", "win"}]
        alias = "+".join(modifiers + [_NUMPAD_ALIASES[key_parts[0]]])
        if alias not in variants:
            variants.append(alias)
    return variants


def _debounced(handler: Callable[[], None]) -> Callable[[], None]:
    last_fire = 0.0
    lock = threading.Lock()

    def wrapped() -> None:
        nonlocal last_fire
        now = time.monotonic()
        with lock:
            if now - last_fire < _HOTKEY_DEBOUNCE_SECONDS:
                return
            last_fire = now
        handler()

    return wrapped


class HotkeyManager:
    def __init__(self) -> None:
        self._handles: list[keyboard.Hotkey] = []
        self._win32: Win32HotkeyManager | None = Win32HotkeyManager() if sys.platform == "win32" else None
        self._ll_hook: LowLevelHotkeyHook | None = LowLevelHotkeyHook() if sys.platform == "win32" else None
        self._lock = threading.Lock()
        self._suppress = True

    def clear(self) -> None:
        with self._lock:
            for handle in self._handles:
                try:
                    keyboard.remove_hotkey(handle)
                except KeyError:
                    pass
            self._handles.clear()
            if self._win32:
                self._win32.clear()
            if self._ll_hook:
                self._ll_hook.clear()

    def register_all(
        self,
        hotkeys: dict[str, str | None],
        handlers: dict[str, Callable[[], None]],
        root=None,
        suppress: bool = True,
    ) -> list[str]:
        self.clear()
        self._suppress = suppress
        errors: list[str] = []

        for shot_type, combo in hotkeys.items():
            if not combo:
                continue
            conflicts = find_hotkey_conflicts(hotkeys, combo, exclude_type=shot_type)
            if conflicts:
                errors.append(f"{combo} is assigned to multiple capture types in SnapIt.")

        wrapped_handlers = {
            shot_type: _debounced(handler) for shot_type, handler in handlers.items()
        }

        # Primary: low-level hook (works when other apps hold focus).
        if self._ll_hook is not None:
            ll_errors = self._ll_hook.register_all(hotkeys, wrapped_handlers, suppress=suppress)
            errors.extend(ll_errors)
            logger.info("Low-level hotkey hook active (suppress=%s)", suppress)

        win32_ok: set[str] = set()
        if self._win32 and root is not None:
            win32_errors = self._win32.register_all(root, hotkeys, wrapped_handlers)
            failed_combos = set()
            for message in win32_errors:
                for shot_type, combo in hotkeys.items():
                    if combo and combo in message:
                        failed_combos.add(shot_type)
            win32_ok = {st for st, combo in hotkeys.items() if combo and st not in failed_combos}
            errors.extend(win32_errors)

        with self._lock:
            for shot_type, combo in hotkeys.items():
                if not combo:
                    continue
                handler = wrapped_handlers.get(shot_type)
                if not handler:
                    continue
                if find_hotkey_conflicts(hotkeys, combo, exclude_type=shot_type):
                    continue
                registered_variant = False
                for variant in _hotkey_variants(combo):
                    try:
                        handle = keyboard.add_hotkey(variant, handler, suppress=suppress)
                        self._handles.append(handle)
                        registered_variant = True
                    except Exception:
                        continue
                if not registered_variant and shot_type not in win32_ok and self._ll_hook is None:
                    errors.append(f"Could not register {combo}")
        return errors

    def probe_combo(self, combo: str, hotkeys: dict[str, str | None], exclude_type: str) -> str | None:
        normalized = normalize_combo(combo)
        if not normalized or "+" not in normalized:
            return "Press a key combination that includes at least one modifier (Ctrl, Alt, Shift, or Win)."

        conflicts = find_hotkey_conflicts(hotkeys, combo, exclude_type=exclude_type)
        if conflicts:
            labels = ", ".join(conflicts)
            return f"Already assigned to: {labels}"

        handle = None
        try:
            handle = keyboard.add_hotkey(combo, lambda: None, suppress=False)
        except Exception as exc:
            return f"Could not use this hotkey: {exc}"
        finally:
            if handle is not None:
                try:
                    keyboard.remove_hotkey(handle)
                except KeyError:
                    pass

        return None


class HotkeyCaptureSession:
    """Listen for the next key combination pressed by the user."""

    def __init__(self, on_captured: Callable[[str | None], None]) -> None:
        self._on_captured = on_captured
        self._active = False
        self._pressed_modifiers: set[str] = set()
        self._hook = None

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        self._pressed_modifiers.clear()
        self._hook = keyboard.hook(self._on_event, suppress=False)

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None
        self._pressed_modifiers.clear()

    def _on_event(self, event: keyboard.KeyboardEvent) -> None:
        if not self._active or event.event_type != keyboard.KEY_DOWN:
            return

        name = event.name
        if not name:
            return

        if name in {"ctrl", "alt", "shift", "windows", "win", "left windows", "right windows"}:
            modifier = "win" if "windows" in name or name == "win" else name
            self._pressed_modifiers.add(modifier)
            return

        if name in {"esc", "escape"}:
            self.stop()
            self._on_captured(None)
            return

        if not self._pressed_modifiers:
            return

        parts = sorted(self._pressed_modifiers) + [name]
        combo = "+".join(parts)
        self.stop()
        self._on_captured(combo)