"""Copy images to the Windows clipboard."""

from __future__ import annotations

import io

import win32clipboard
from PIL import Image


def copy_image_to_clipboard(image: Image.Image) -> None:
    with io.BytesIO() as output:
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()