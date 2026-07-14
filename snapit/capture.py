"""Screenshot capture routines."""

from __future__ import annotations

import ctypes
from datetime import datetime
from pathlib import Path

import mss
import win32con
import win32gui
import win32ui
from PIL import Image

from snapit.clipboard_util import copy_image_to_clipboard


def _capture_rect(rect: tuple[int, int, int, int]) -> Image.Image:
    from snapit.screen_coords import normalize_rect

    left, top, right, bottom = normalize_rect(rect)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError("Capture area has no size.")

    with mss.mss() as sct:
        monitor = {"left": left, "top": top, "width": width, "height": height}
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def capture_region(rect: tuple[int, int, int, int]) -> Image.Image:
    return _capture_rect(rect)


def capture_fullscreen() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def capture_all_monitors() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def capture_active_window() -> Image.Image:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("No active window found.")

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError("Active window has no visible area.")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)

    result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
    if result != 1:
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        return _capture_rect((left, top, right, bottom))

    bmpinfo = bitmap.GetInfo()
    bmpstr = bitmap.GetBitmapBits(True)
    image = Image.frombuffer(
        "RGB",
        (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
        bmpstr,
        "raw",
        "BGRX",
        0,
        1,
    )

    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    return image


def save_screenshot(
    image: Image.Image,
    directory: Path,
    prefix: str,
    copy_clipboard: bool,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = directory / f"{prefix}_{timestamp}.png"
    image.save(path, format="PNG")

    if copy_clipboard:
        copy_image_to_clipboard(image)

    return path