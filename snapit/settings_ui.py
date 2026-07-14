"""Settings window for hotkeys and save location."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from snapit.config import SCREENSHOT_TYPES, AppConfig, find_hotkey_conflicts, normalize_combo
from snapit.hotkeys import HotkeyCaptureSession, HotkeyManager

logger = logging.getLogger(__name__)


class SettingsWindow:
    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        hotkey_manager: HotkeyManager,
        on_save: Callable[[AppConfig], None],
    ) -> None:
        self._root = root
        self._config = config
        self._hotkey_manager = hotkey_manager
        self._on_save = on_save
        self._window: tk.Toplevel | None = None
        self._capture_session: HotkeyCaptureSession | None = None
        self._hotkey_vars: dict[str, tk.StringVar] = {}
        self._assign_type = tk.StringVar(value=SCREENSHOT_TYPES["region"])
        self._assign_status = tk.StringVar(value="Select a capture type, then press Assign.")
        self._save_dir_var = tk.StringVar(value=str(config.save_directory))
        self._clipboard_var = tk.BooleanVar(value=config.copy_to_clipboard)
        self._notify_var = tk.BooleanVar(value=config.show_notification)
        self._startup_var = tk.BooleanVar(value=config.start_with_windows)
        self._editor_var = tk.BooleanVar(value=config.open_editor_after_capture)
        self._delay_var = tk.DoubleVar(value=config.capture_delay_seconds)
        self._suppress_var = tk.BooleanVar(value=config.hotkey_suppress)
        self._video_seconds_var = tk.DoubleVar(value=config.video_record_seconds)

    def show(self) -> None:
        logger.info("Opening settings window")
        if self._window and self._window.winfo_exists():
            self._present_window(self._window)
            return

        self._window = tk.Toplevel(self._root)
        self._window.title("SnapIt Settings")
        self._window.geometry("620x520+120+80")
        self._window.minsize(560, 480)

        notebook = ttk.Notebook(self._window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        hotkeys_tab = ttk.Frame(notebook, padding=12)
        general_tab = ttk.Frame(notebook, padding=12)
        notebook.add(hotkeys_tab, text="Hotkeys")
        notebook.add(general_tab, text="General")

        self._build_hotkeys_tab(hotkeys_tab)
        self._build_general_tab(general_tab)

        button_row = ttk.Frame(self._window, padding=(12, 0, 12, 12))
        button_row.pack(fill=tk.X)
        ttk.Button(button_row, text="Save", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(button_row, text="Cancel", command=self._window.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        self._window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._present_window(self._window)
        logger.info("Settings window created")

    def _present_window(self, window: tk.Toplevel) -> None:
        window.deiconify()
        window.wm_state("normal")
        window.attributes("-topmost", True)
        window.update_idletasks()
        window.lift()
        window.focus_force()
        window.after(200, lambda: window.attributes("-topmost", False))

    def _build_hotkeys_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Assign hotkeys by choosing a capture type, clicking Assign, then pressing your desired key combo.\n"
            "SnapIt registers both Windows hotkeys and a low-level hook for reliability. Enable strong override in General.",
            wraplength=540,
        ).pack(anchor=tk.W, pady=(0, 12))

        table = ttk.Frame(parent)
        table.pack(fill=tk.BOTH, expand=True)

        ttk.Label(table, text="Capture type", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Label(table, text="Hotkey", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky=tk.W, padx=(16, 0), pady=4)

        for row_index, (shot_type, label) in enumerate(SCREENSHOT_TYPES.items(), start=1):
            ttk.Label(table, text=label).grid(row=row_index, column=0, sticky=tk.W, pady=4)
            var = tk.StringVar(value=self._config.hotkeys.get(shot_type) or "(not set)")
            self._hotkey_vars[shot_type] = var
            ttk.Label(table, textvariable=var).grid(row=row_index, column=1, sticky=tk.W, padx=(16, 0), pady=4)
            ttk.Button(
                table,
                text="Clear",
                command=lambda st=shot_type: self._clear_hotkey(st),
            ).grid(row=row_index, column=2, padx=(12, 0), pady=4)

        assign_frame = ttk.LabelFrame(parent, text="Assign hotkey", padding=12)
        assign_frame.pack(fill=tk.X, pady=(16, 0))

        ttk.Label(assign_frame, text="Capture type:").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(
            assign_frame,
            textvariable=self._assign_type,
            values=list(SCREENSHOT_TYPES.values()),
            state="readonly",
            width=28,
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Button(assign_frame, text="Assign…", command=self._begin_assign).grid(row=0, column=2, padx=(12, 0))
        ttk.Label(assign_frame, textvariable=self._assign_status, foreground="#555555").grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(10, 0)
        )

    def _build_general_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Save directory:").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=self._save_dir_var, width=48).grid(row=0, column=1, sticky=tk.W, padx=(8, 0), pady=4)
        ttk.Button(parent, text="Browse…", command=self._browse_save_dir).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Checkbutton(parent, text="Copy screenshots to clipboard", variable=self._clipboard_var).grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(12, 4)
        )
        ttk.Checkbutton(parent, text="Show notification after capture", variable=self._notify_var).grid(
            row=2, column=0, columnspan=3, sticky=tk.W, pady=4
        )
        ttk.Checkbutton(parent, text="Start with Windows", variable=self._startup_var).grid(
            row=3, column=0, columnspan=3, sticky=tk.W, pady=4
        )
        ttk.Checkbutton(
            parent,
            text="Open image editor after each capture (still auto-saves PNG)",
            variable=self._editor_var,
        ).grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=4)

        delay_frame = ttk.Frame(parent)
        delay_frame.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(12, 4))
        ttk.Label(delay_frame, text="Capture delay (seconds):").pack(side=tk.LEFT)
        delay_spin = ttk.Spinbox(
            delay_frame,
            from_=0.0,
            to=10.0,
            increment=0.5,
            width=6,
            textvariable=self._delay_var,
        )
        delay_spin.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            delay_frame,
            text="Wait before capture so you can hover tooltips.",
            foreground="#555555",
        ).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Checkbutton(
            parent,
            text="Strong hotkey override (suppress keys from other apps while SnapIt is running)",
            variable=self._suppress_var,
        ).grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=4)

        video_frame = ttk.Frame(parent)
        video_frame.grid(row=7, column=0, columnspan=3, sticky=tk.W, pady=(8, 4))
        ttk.Label(video_frame, text="Video record length (seconds):").pack(side=tk.LEFT)
        ttk.Spinbox(
            video_frame,
            from_=1.0,
            to=120.0,
            increment=1.0,
            width=6,
            textvariable=self._video_seconds_var,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(video_frame, text="Default format: MP4", foreground="#555555").pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(
            parent,
            text="Config is stored per machine in %APPDATA%\\SnapIt\\config.json.\n"
            "Each PC can use its own save folder and hotkeys.\n"
            "Use build.ps1 to create dist\\SnapIt.exe for a standalone app.",
            foreground="#555555",
            justify=tk.LEFT,
        ).grid(row=8, column=0, columnspan=3, sticky=tk.W, pady=(20, 0))

    def _browse_save_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self._save_dir_var.get())
        if chosen:
            self._save_dir_var.set(chosen)

    def _clear_hotkey(self, shot_type: str) -> None:
        self._config.hotkeys[shot_type] = None
        self._hotkey_vars[shot_type].set("(not set)")

    def _shot_type_from_label(self, label: str) -> str | None:
        for key, value in SCREENSHOT_TYPES.items():
            if value == label:
                return key
        return None

    def _begin_assign(self) -> None:
        shot_type = self._shot_type_from_label(self._assign_type.get())
        if not shot_type:
            self._assign_status.set("Select a valid capture type first.")
            return
        self._assign_status.set("Press your key combination now… (Esc to cancel)")
        if self._capture_session:
            self._capture_session.stop()

        def on_captured(combo: str | None) -> None:
            self._root.after(0, lambda st=shot_type, c=combo: self._finish_assign(st, c))

        self._capture_session = HotkeyCaptureSession(on_captured)
        self._capture_session.start()

    def _finish_assign(self, shot_type: str, combo: str | None) -> None:
        if not combo:
            self._assign_status.set("Assignment cancelled.")
            return

        normalized = normalize_combo(combo)
        conflicts = find_hotkey_conflicts(self._config.hotkeys, normalized, exclude_type=shot_type)
        if conflicts:
            labels = ", ".join(SCREENSHOT_TYPES[c] for c in conflicts)
            messagebox.showwarning(
                "Hotkey conflict",
                f"{normalized} is already assigned to:\n{labels}",
                parent=self._window,
            )
            self._assign_status.set("Conflict detected — hotkey not changed.")
            return

        warning = self._hotkey_manager.probe_combo(normalized, self._config.hotkeys, shot_type)
        if warning:
            proceed = messagebox.askyesno(
                "Hotkey warning",
                f"{warning}\n\nAssign anyway?",
                parent=self._window,
            )
            if not proceed:
                self._assign_status.set("Assignment cancelled.")
                return

        self._config.hotkeys[shot_type] = normalized
        self._hotkey_vars[shot_type].set(normalized)
        self._assign_status.set(f"Assigned {normalized} to {SCREENSHOT_TYPES[shot_type]}.")

    def _save(self) -> None:
        save_dir = self._save_dir_var.get().strip()
        if not save_dir:
            messagebox.showerror("Invalid directory", "Please choose a save directory.", parent=self._window)
            return

        self._config.save_directory = Path(save_dir)
        self._config.copy_to_clipboard = self._clipboard_var.get()
        self._config.show_notification = self._notify_var.get()
        self._config.start_with_windows = self._startup_var.get()
        self._config.open_editor_after_capture = self._editor_var.get()
        self._config.capture_delay_seconds = max(0.0, float(self._delay_var.get()))
        self._config.hotkey_suppress = self._suppress_var.get()
        self._config.video_record_seconds = max(1.0, float(self._video_seconds_var.get()))
        self._on_save(self._config)
        if self._window:
            self._window.destroy()

    def _on_close(self) -> None:
        if self._capture_session:
            self._capture_session.stop()
        if self._window:
            self._window.destroy()