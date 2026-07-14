"""Configuration load/save for SnapIt."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "SnapIt"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"

SCREENSHOT_TYPES = {
    "region": "Drawable region",
    "active_window": "Active window",
    "fullscreen": "Full screen (primary monitor)",
    "all_monitors": "All monitors",
    "video_region": "Record region (video)",
    "video_active_window": "Record active window (video)",
    "video_fullscreen": "Record full screen (video)",
}

DEFAULT_HOTKEYS: dict[str, str | None] = {
    "region": "ctrl+shift+1",
    "active_window": "ctrl+shift+2",
    "fullscreen": "ctrl+shift+3",
    "all_monitors": None,
    "video_region": None,
    "video_active_window": None,
    "video_fullscreen": None,
}


@dataclass
class AppConfig:
    save_directory: Path = field(
        default_factory=lambda: Path.home() / "Pictures" / "SnapIt"
    )
    hotkeys: dict[str, str | None] = field(
        default_factory=lambda: deepcopy(DEFAULT_HOTKEYS)
    )
    copy_to_clipboard: bool = True
    show_notification: bool = True
    filename_prefix: str = "screenshot"
    start_with_windows: bool = True
    open_editor_after_capture: bool = False
    editor_default_format: str = "PNG"
    capture_delay_seconds: float = 0.0
    hotkey_suppress: bool = True
    video_default_format: str = "mp4"
    video_record_seconds: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "save_directory": str(self.save_directory),
            "hotkeys": self.hotkeys,
            "copy_to_clipboard": self.copy_to_clipboard,
            "show_notification": self.show_notification,
            "filename_prefix": self.filename_prefix,
            "start_with_windows": self.start_with_windows,
            "open_editor_after_capture": self.open_editor_after_capture,
            "editor_default_format": self.editor_default_format,
            "capture_delay_seconds": self.capture_delay_seconds,
            "hotkey_suppress": self.hotkey_suppress,
            "video_default_format": self.video_default_format,
            "video_record_seconds": self.video_record_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        hotkeys = deepcopy(DEFAULT_HOTKEYS)
        hotkeys.update(data.get("hotkeys", {}))
        return cls(
            save_directory=Path(data.get("save_directory", str(cls().save_directory))),
            hotkeys=hotkeys,
            copy_to_clipboard=data.get("copy_to_clipboard", True),
            show_notification=data.get("show_notification", True),
            filename_prefix=data.get("filename_prefix", "screenshot"),
            start_with_windows=data.get("start_with_windows", True),
            open_editor_after_capture=data.get("open_editor_after_capture", False),
            editor_default_format=data.get("editor_default_format", "PNG"),
            capture_delay_seconds=float(data.get("capture_delay_seconds", 0.0)),
            hotkey_suppress=data.get("hotkey_suppress", True),
            video_default_format=data.get("video_default_format", "mp4"),
            video_record_seconds=float(data.get("video_record_seconds", 5.0)),
        )


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        config = AppConfig()
        save_config(config)
        return config

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return AppConfig.from_dict(data)


def save_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.save_directory.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(config.to_dict(), handle, indent=2)


def find_hotkey_conflicts(
    hotkeys: dict[str, str | None], combo: str, exclude_type: str | None = None
) -> list[str]:
    normalized = normalize_combo(combo)
    conflicts: list[str] = []
    for shot_type, assigned in hotkeys.items():
        if shot_type == exclude_type or not assigned:
            continue
        if normalize_combo(assigned) == normalized:
            conflicts.append(shot_type)
    return conflicts


def normalize_combo(combo: str) -> str:
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    modifiers = sorted(part for part in parts if part in {"ctrl", "alt", "shift", "win"})
    keys = [part for part in parts if part not in {"ctrl", "alt", "shift", "win"}]
    if not keys:
        return "+".join(modifiers)
    return "+".join(modifiers + keys[:1])