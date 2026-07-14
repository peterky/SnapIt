"""Video capture hooks — extension points for screen recording."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

VideoFormat = Literal["mp4", "webm"]
VIDEO_FORMATS: dict[VideoFormat, str] = {
    "mp4": ".mp4",
    "webm": ".webm",
}

VIDEO_CAPTURE_TYPES = {
    "video_region": "Record region (video)",
    "video_active_window": "Record active window (video)",
    "video_fullscreen": "Record full screen (video)",
}


@dataclass
class VideoCaptureConfig:
    save_directory: Path
    filename_prefix: str = "recording"
    default_format: VideoFormat = "mp4"
    fps: int = 15


class VideoCaptureHooks:
    """Hook surface for video capture. Image recording uses capture.py; video plugs in here."""

    def __init__(self, config: VideoCaptureConfig) -> None:
        self._config = config
        self._recording = False
        self._on_status: Callable[[str], None] | None = None

    def set_status_handler(self, handler: Callable[[str], None]) -> None:
        self._on_status = handler

    def _status(self, message: str) -> None:
        logger.info("Video: %s", message)
        if self._on_status:
            self._on_status(message)

    @property
    def is_recording(self) -> bool:
        return self._recording

    def is_backend_available(self) -> bool:
        try:
            import imageio.v3  # noqa: F401
            return True
        except ImportError:
            return False

    def availability_message(self) -> str:
        if self.is_backend_available():
            return "Video backend ready (imageio + ffmpeg)."
        return "Install imageio[ffmpeg] to enable MP4 recording."

    def begin_region_capture(
        self,
        rect: tuple[int, int, int, int],
        duration_seconds: float = 5.0,
        on_complete: Callable[[Path | None], None] | None = None,
    ) -> None:
        """Hook: record a screen region to the default video format."""
        self._recording = True
        self._status(f"Recording region {rect} for {duration_seconds:.1f}s…")

        try:
            path = self._record_region_to_file(rect, duration_seconds)
            self._status(f"Saved video to {path.name}")
            if on_complete:
                on_complete(path)
        except Exception as exc:
            logger.exception("Video capture failed")
            self._status(f"Video capture failed: {exc}")
            if on_complete:
                on_complete(None)
        finally:
            self._recording = False

    def begin_active_window_capture(
        self,
        duration_seconds: float = 5.0,
        on_complete: Callable[[Path | None], None] | None = None,
    ) -> None:
        self._status("Active-window video capture hook invoked.")
        logger.info("video_active_window hook (duration=%s)", duration_seconds)
        if on_complete:
            on_complete(None)

    def begin_fullscreen_capture(
        self,
        duration_seconds: float = 5.0,
        on_complete: Callable[[Path | None], None] | None = None,
    ) -> None:
        self._status("Fullscreen video capture hook invoked.")
        logger.info("video_fullscreen hook (duration=%s)", duration_seconds)
        if on_complete:
            on_complete(None)

    def _record_region_to_file(
        self,
        rect: tuple[int, int, int, int],
        duration_seconds: float,
    ) -> Path:
        import time

        import imageio.v3 as iio
        import mss
        import numpy as np

        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)
        monitor = {"left": left, "top": top, "width": width, "height": height}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = VIDEO_FORMATS[self._config.default_format]
        path = self._config.save_directory / f"{self._config.filename_prefix}_{timestamp}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)

        frame_interval = 1.0 / max(1, self._config.fps)
        end_time = time.monotonic() + max(0.5, duration_seconds)
        frames: list[np.ndarray] = []

        with mss.mss() as sct:
            while time.monotonic() < end_time:
                shot = sct.grab(monitor)
                frame = np.array(shot)[:, :, :3]  # BGRA -> drop alpha, keep BGR
                frames.append(frame[:, :, ::-1])  # RGB for imageio
                time.sleep(frame_interval)

        if not frames:
            raise RuntimeError("No frames captured.")

        iio.imwrite(path, frames, fps=self._config.fps, codec="libx264")
        return path