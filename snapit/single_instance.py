"""Prevent multiple SnapIt instances from running."""

from __future__ import annotations

import ctypes
import sys

_MUTEX_NAME = "Global\\SnapIt_SingleInstance_Mutex"
_ERROR_ALREADY_EXISTS = 183


def acquire_single_instance() -> bool:
    if sys.platform != "win32":
        return True

    handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    return True