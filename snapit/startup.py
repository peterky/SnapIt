"""Windows startup shortcut management."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "SnapIt"
SHORTCUT_NAME = f"{APP_NAME}.lnk"


def startup_folder() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def shortcut_path() -> Path:
    return startup_folder() / SHORTCUT_NAME


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def launch_target() -> tuple[Path, str, Path]:
    """Return shortcut target path, arguments, and working directory."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return exe, "", exe.parent

    built_exe = project_root() / "dist" / f"{APP_NAME}.exe"
    if built_exe.exists():
        return built_exe, "", built_exe.parent

    pythonw = project_root() / ".venv" / "Scripts" / "pythonw.exe"
    if pythonw.exists():
        return pythonw, "-m snapit", project_root()

    return Path(sys.executable), "-m snapit", project_root()


def is_startup_enabled() -> bool:
    return shortcut_path().exists()


def set_startup_enabled(enabled: bool) -> None:
    if enabled:
        enable_startup()
    else:
        disable_startup()


def enable_startup() -> None:
    target, arguments, working_dir = launch_target()
    startup_folder().mkdir(parents=True, exist_ok=True)
    shortcut = shortcut_path()

    ps_command = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$link = $shell.CreateShortcut('{shortcut}'); "
        f"$link.TargetPath = '{target}'; "
        f"$link.Arguments = '{arguments}'; "
        f"$link.WorkingDirectory = '{working_dir}'; "
        f"$link.Description = '{APP_NAME} screenshot utility'; "
        "$link.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_command],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def disable_startup() -> None:
    if shortcut_path().exists():
        shortcut_path().unlink()


def sync_startup(enabled: bool) -> None:
    if enabled and not is_startup_enabled():
        enable_startup()
    elif not enabled and is_startup_enabled():
        disable_startup()