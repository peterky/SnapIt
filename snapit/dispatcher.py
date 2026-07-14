"""Thread-safe dispatch of work onto the tkinter main thread."""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable

import tkinter as tk

logger = logging.getLogger(__name__)


class MainThreadDispatcher:
    def __init__(self, root: tk.Tk, interval_ms: int = 20) -> None:
        self._root = root
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._interval_ms = interval_ms
        self._poll()

    def submit(self, callback: Callable[[], None]) -> None:
        self._queue.put(callback)

    def _poll(self) -> None:
        while True:
            try:
                callback = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                logger.exception("UI callback failed")
        self._root.after(self._interval_ms, self._poll)