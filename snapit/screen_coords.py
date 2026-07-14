"""Virtual screen bounds and DPI helpers for accurate captures."""

from __future__ import annotations

import ctypes
import sys

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def ensure_dpi_aware() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Return left, top, width, height of the full virtual desktop."""
    user32 = ctypes.windll.user32
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return left, top, width, height


def screen_to_local(x: int, y: int, origin_left: int, origin_top: int) -> tuple[int, int]:
    return x - origin_left, y - origin_top


def normalize_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = rect
    if left > right:
        left, right = right, left
    if top > bottom:
        top, bottom = bottom, top
    return left, top, right, bottom