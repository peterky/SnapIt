"""Pre-capture countdown so the user can position the mouse."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable


class CaptureDelayOverlay:
    def __init__(self, parent: tk.Tk, seconds: float, on_complete: Callable[[], None]) -> None:
        self._parent = parent
        self._seconds = max(0.0, seconds)
        self._on_complete = on_complete
        self._remaining = self._seconds
        self._window: tk.Toplevel | None = None

    def start(self) -> None:
        if self._seconds <= 0:
            self._on_complete()
            return

        self._window = tk.Toplevel(self._parent)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.configure(bg="#111111")
        self._label = tk.Label(
            self._window,
            text="",
            fg="#ffffff",
            bg="#111111",
            font=("Segoe UI", 16, "bold"),
            padx=24,
            pady=16,
        )
        self._label.pack()
        self._position()
        self._tick()

    def _position(self) -> None:
        if not self._window:
            return
        self._window.update_idletasks()
        screen_w = self._window.winfo_screenwidth()
        width = self._window.winfo_reqwidth()
        self._window.geometry(f"+{max(0, (screen_w - width) // 2)}+40")

    def _tick(self) -> None:
        if not self._window:
            return

        if self._remaining <= 0:
            self._window.destroy()
            self._window = None
            self._on_complete()
            return

        if self._remaining >= 1.0:
            self._label.config(text=f"Capture in {int(math.ceil(self._remaining))}…\nMove the mouse over your tooltip")
        else:
            self._label.config(text="Capturing…")
        self._remaining -= 0.1
        self._window.after(100, self._tick)