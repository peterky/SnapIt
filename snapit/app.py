"""SnapIt application orchestrator."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox

from PIL import Image

from snapit.capture import (
    capture_active_window,
    capture_all_monitors,
    capture_fullscreen,
    capture_region,
    save_screenshot,
)
from snapit.capture_delay import CaptureDelayOverlay
from snapit.config import AppConfig, load_config, save_config
from snapit.dispatcher import MainThreadDispatcher
from snapit.editor import open_image_editor
from snapit.hotkeys import HotkeyManager
from snapit.logging_config import setup_logging
from snapit.region_selector import RegionSelector
from snapit.settings_ui import SettingsWindow
from snapit.startup import sync_startup
from snapit.tray import TrayController
from snapit.video_capture import VideoCaptureConfig, VideoCaptureHooks

logger = logging.getLogger(__name__)


class SnapItApp:
    def __init__(self) -> None:
        setup_logging()
        logger.info("SnapIt starting")
        self._config = load_config()
        self._hotkey_manager = HotkeyManager()
        self._video = VideoCaptureHooks(
            VideoCaptureConfig(
                save_directory=self._config.save_directory,
                filename_prefix="recording",
                default_format=self._config.video_default_format,  # type: ignore[arg-type]
            )
        )
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("SnapIt")
        self._dispatcher = MainThreadDispatcher(self._root)
        self._last_capture: Image.Image | None = None
        self._last_capture_path: Path | None = None
        self._settings = SettingsWindow(
            self._root,
            self._config,
            self._hotkey_manager,
            on_save=self._apply_config,
        )
        self._tray = TrayController(
            on_capture_region=lambda: self._dispatcher.submit(self._capture_region),
            on_capture_active_window=lambda: self._dispatcher.submit(self._capture_active_window),
            on_capture_fullscreen=lambda: self._dispatcher.submit(self._capture_fullscreen),
            on_capture_all_monitors=lambda: self._dispatcher.submit(self._capture_all_monitors),
            on_settings=self._open_settings,
            on_edit_last=self._open_last_in_editor,
            on_open_folder=self._open_save_folder,
            on_exit=self._exit,
            save_directory=self._config.save_directory,
            on_video_region=lambda: self._dispatcher.submit(self._video_region),
            on_video_active_window=lambda: self._dispatcher.submit(self._video_active_window),
            on_video_fullscreen=lambda: self._dispatcher.submit(self._video_fullscreen),
        )
        self._register_hotkeys()
        self._sync_startup_quiet(self._config.start_with_windows)

    def run(self) -> None:
        self._tray.start()
        self._root.mainloop()

    def _register_hotkeys(self) -> None:
        handlers = {
            "region": lambda: self._dispatcher.submit(self._capture_region),
            "active_window": lambda: self._dispatcher.submit(self._capture_active_window),
            "fullscreen": lambda: self._dispatcher.submit(self._capture_fullscreen),
            "all_monitors": lambda: self._dispatcher.submit(self._capture_all_monitors),
            "video_region": lambda: self._dispatcher.submit(self._video_region),
            "video_active_window": lambda: self._dispatcher.submit(self._video_active_window),
            "video_fullscreen": lambda: self._dispatcher.submit(self._video_fullscreen),
        }
        errors = self._hotkey_manager.register_all(
            self._config.hotkeys,
            handlers,
            root=self._root,
            suppress=self._config.hotkey_suppress,
        )
        if errors:
            self._root.after(
                0,
                lambda: messagebox.showwarning(
                    "Hotkey registration",
                    "Some hotkeys could not be registered:\n\n" + "\n".join(errors),
                ),
            )

    def _apply_config(self, config: AppConfig) -> None:
        self._config = config
        save_config(config)
        self._video = VideoCaptureHooks(
            VideoCaptureConfig(
                save_directory=config.save_directory,
                filename_prefix="recording",
                default_format=config.video_default_format,  # type: ignore[arg-type]
            )
        )
        try:
            sync_startup(config.start_with_windows)
        except Exception as exc:
            messagebox.showerror("Startup setting", f"Could not update Windows startup:\n{exc}")
        self._register_hotkeys()

    def _sync_startup_quiet(self, enabled: bool) -> None:
        try:
            sync_startup(enabled)
        except Exception:
            pass

    def _open_settings(self) -> None:
        logger.info("Settings requested from tray")
        self._dispatcher.submit(self._settings.show)

    def _open_last_in_editor(self) -> None:
        self._dispatcher.submit(self._show_last_in_editor)

    def _show_last_in_editor(self) -> None:
        if self._last_capture is None:
            messagebox.showinfo("SnapIt", "No capture yet. Take a screenshot first.")
            return
        self._open_editor(self._last_capture.copy(), base_source_path=self._last_capture_path)

    def _open_editor(self, image: Image.Image, base_source_path: Path | None = None) -> None:
        open_image_editor(
            parent=self._root,
            image=image,
            save_directory=self._config.save_directory,
            filename_prefix=self._config.filename_prefix,
            copy_to_clipboard=self._config.copy_to_clipboard,
            default_format=self._config.editor_default_format,
            base_source_path=base_source_path,
            on_capture_region=lambda: self._dispatcher.submit(self._capture_region),
            on_capture_active_window=lambda: self._dispatcher.submit(self._capture_active_window),
            on_capture_fullscreen=lambda: self._dispatcher.submit(self._capture_fullscreen),
            on_video_region=lambda: self._dispatcher.submit(self._video_region),
            on_video_active_window=lambda: self._dispatcher.submit(self._video_active_window),
            on_video_fullscreen=lambda: self._dispatcher.submit(self._video_fullscreen),
        )

    def _open_save_folder(self) -> None:
        path = str(self._config.save_directory)
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])

    def _with_capture_delay(self, action: Callable[[], None]) -> None:
        CaptureDelayOverlay(
            self._root,
            self._config.capture_delay_seconds,
            action,
        ).start()

    def _capture_region(self) -> None:
        def start_selector() -> None:
            def on_complete(rect: tuple[int, int, int, int] | None) -> None:
                if rect is None:
                    return
                try:
                    image = capture_region(rect)
                    self._finalize_capture(image)
                except Exception as exc:
                    messagebox.showerror("Capture failed", str(exc))

            RegionSelector(on_complete).show(self._root)

        self._with_capture_delay(start_selector)

    def _capture_active_window(self) -> None:
        def capture() -> None:
            try:
                image = capture_active_window()
                self._finalize_capture(image)
            except Exception as exc:
                messagebox.showerror("Capture failed", str(exc))

        self._with_capture_delay(capture)

    def _capture_fullscreen(self) -> None:
        def capture() -> None:
            try:
                image = capture_fullscreen()
                self._finalize_capture(image)
            except Exception as exc:
                messagebox.showerror("Capture failed", str(exc))

        self._with_capture_delay(capture)

    def _capture_all_monitors(self) -> None:
        def capture() -> None:
            try:
                image = capture_all_monitors()
                self._finalize_capture(image)
            except Exception as exc:
                messagebox.showerror("Capture failed", str(exc))

        self._with_capture_delay(capture)

    def _video_region(self) -> None:
        if not self._video.is_backend_available():
            messagebox.showinfo("Video capture", self._video.availability_message())
            return

        def start_selector() -> None:
            def on_complete(rect: tuple[int, int, int, int] | None) -> None:
                if rect is None:
                    return

                def on_video_done(path: Path | None) -> None:
                    if path and self._config.show_notification:
                        self._tray.notify("SnapIt", f"Video saved to {path.name}")

                self._video.begin_region_capture(
                    rect,
                    duration_seconds=self._config.video_record_seconds,
                    on_complete=on_video_done,
                )

            RegionSelector(on_complete).show(self._root)

        self._with_capture_delay(start_selector)

    def _video_active_window(self) -> None:
        def on_complete(_path: Path | None) -> None:
            if self._config.show_notification:
                self._tray.notify("SnapIt", "Active-window video hook called")

        self._video.begin_active_window_capture(
            duration_seconds=self._config.video_record_seconds,
            on_complete=on_complete,
        )
        messagebox.showinfo("Video capture", "Active-window video hook is wired; implementation pending.")

    def _video_fullscreen(self) -> None:
        def on_complete(_path: Path | None) -> None:
            if self._config.show_notification:
                self._tray.notify("SnapIt", "Fullscreen video hook called")

        self._video.begin_fullscreen_capture(
            duration_seconds=self._config.video_record_seconds,
            on_complete=on_complete,
        )
        messagebox.showinfo("Video capture", "Fullscreen video hook is wired; implementation pending.")

    def _finalize_capture(self, image: Image.Image) -> None:
        try:
            self._last_capture = image.copy()
            path = save_screenshot(
                image,
                self._config.save_directory,
                self._config.filename_prefix,
                self._config.copy_to_clipboard,
            )
            self._last_capture_path = path

            if self._config.open_editor_after_capture:
                self._open_editor(image, base_source_path=path)
                if self._config.show_notification:
                    self._tray.notify("SnapIt", f"Saved to {path.name} — opened in editor")
            elif self._config.show_notification:
                self._tray.notify("SnapIt", f"Saved to {path.name}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _exit(self) -> None:
        self._dispatcher.submit(self._shutdown)

    def _shutdown(self) -> None:
        logger.info("SnapIt shutting down")
        self._hotkey_manager.clear()
        self._tray.stop()
        self._root.destroy()