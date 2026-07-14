"""System tray icon and menu."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem


def _create_icon_image() -> Image.Image:
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 10, 58, 48), radius=8, fill=(0, 120, 212, 255))
    draw.rectangle((18, 18, 46, 36), outline=(255, 255, 255, 255), width=3)
    draw.ellipse((40, 8, 54, 22), fill=(255, 255, 255, 255))
    return image


class TrayController:
    def __init__(
        self,
        on_capture_region: Callable[[], None],
        on_capture_active_window: Callable[[], None],
        on_capture_fullscreen: Callable[[], None],
        on_capture_all_monitors: Callable[[], None],
        on_settings: Callable[[], None],
        on_edit_last: Callable[[], None],
        on_open_folder: Callable[[], None],
        on_exit: Callable[[], None],
        save_directory: Path,
        on_video_region: Callable[[], None] | None = None,
        on_video_active_window: Callable[[], None] | None = None,
        on_video_fullscreen: Callable[[], None] | None = None,
    ) -> None:
        self._on_capture_region = on_capture_region
        self._on_capture_active_window = on_capture_active_window
        self._on_capture_fullscreen = on_capture_fullscreen
        self._on_capture_all_monitors = on_capture_all_monitors
        self._on_video_region = on_video_region
        self._on_video_active_window = on_video_active_window
        self._on_video_fullscreen = on_video_fullscreen
        self._on_settings = on_settings
        self._on_edit_last = on_edit_last
        self._on_open_folder = on_open_folder
        self._on_exit = on_exit
        self._save_directory = save_directory
        self._icon: Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        capture_menu = Menu(
            MenuItem("Region…", lambda _i, _m: self._on_capture_region()),
            MenuItem("Active window", lambda _i, _m: self._on_capture_active_window()),
            MenuItem("Full screen", lambda _i, _m: self._on_capture_fullscreen()),
            MenuItem("All monitors", lambda _i, _m: self._on_capture_all_monitors()),
        )
        video_items = []
        if self._on_video_region:
            video_items.append(MenuItem("Record region (video)…", lambda _i, _m: self._on_video_region()))
        if self._on_video_active_window:
            video_items.append(MenuItem("Record active window (video)", lambda _i, _m: self._on_video_active_window()))
        if self._on_video_fullscreen:
            video_items.append(MenuItem("Record full screen (video)", lambda _i, _m: self._on_video_fullscreen()))
        menu_entries = [
            MenuItem("Capture", capture_menu),
            MenuItem("Settings…", lambda _i, _m: self._on_settings(), default=True),
            MenuItem("Edit last capture", lambda _i, _m: self._on_edit_last()),
            MenuItem("Open save folder", lambda _i, _m: self._on_open_folder()),
            Menu.SEPARATOR,
            MenuItem("Exit", lambda _i, _m: self._on_exit()),
        ]
        if video_items:
            menu_entries.insert(1, MenuItem("Video", Menu(*video_items)))
        menu = Menu(*menu_entries)
        self._icon = Icon("SnapIt", _create_icon_image(), "SnapIt", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def notify(self, title: str, message: str) -> None:
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
            self._icon = None