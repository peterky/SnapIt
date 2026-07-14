"""Fullscreen region selection with SnagIt-style corner toggle and magnifier."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import mss
from PIL import Image, ImageDraw, ImageTk

from snapit.screen_coords import normalize_rect, screen_to_local, virtual_screen_bounds

MAGNIFIER_SIZE = 280
SAMPLE_PIXELS = 48
ZOOM_FACTOR = 3


class _Magnifier:
    def __init__(self) -> None:
        self._window = tk.Toplevel()
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.configure(bg="#111111", highlightthickness=1, highlightbackground="#00b4ff")
        self._label = tk.Label(self._window, bg="#111111", bd=0)
        self._label.pack(padx=4, pady=4)
        self._photo: ImageTk.PhotoImage | None = None

    def show(self) -> None:
        self._window.deiconify()

    def update(self, screen_x: int, screen_y: int) -> None:
        half = SAMPLE_PIXELS // 2
        with mss.mss() as sct:
            shot = sct.grab(
                {
                    "left": screen_x - half,
                    "top": screen_y - half,
                    "width": SAMPLE_PIXELS,
                    "height": SAMPLE_PIXELS,
                }
            )
            sample = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        zoomed = sample.resize(
            (SAMPLE_PIXELS * ZOOM_FACTOR, SAMPLE_PIXELS * ZOOM_FACTOR),
            Image.Resampling.NEAREST,
        )
        draw = ImageDraw.Draw(zoomed)
        center = zoomed.width // 2
        draw.line((center, 0, center, zoomed.height), fill="#00b4ff", width=1)
        draw.line((0, center, zoomed.width, center), fill="#00b4ff", width=1)

        self._photo = ImageTk.PhotoImage(zoomed)
        self._label.configure(image=self._photo)
        display = SAMPLE_PIXELS * ZOOM_FACTOR + 8
        offset = max(display, MAGNIFIER_SIZE // 2)
        self._window.geometry(f"{MAGNIFIER_SIZE}x{MAGNIFIER_SIZE}+{screen_x + 24}+{screen_y + 24}")
        self._window.deiconify()

    def destroy(self) -> None:
        self._window.destroy()


class RegionSelector:
    def __init__(self, on_complete: Callable[[tuple[int, int, int, int] | None], None]) -> None:
        self._on_complete = on_complete
        self._root: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._magnifier = _Magnifier()
        self._origin_left = 0
        self._origin_top = 0
        self._screen_w = 0
        self._screen_h = 0
        self._pinned: tuple[int, int] | None = None
        self._free: tuple[int, int] | None = None
        self._free_follows_mouse = True
        self._mouse_x = 0
        self._mouse_y = 0
        self._shape_ids: list[int] = []
        self._info_var = tk.StringVar(
            value="Click a corner • Space swaps pinned corner • Arrows nudge 1px • Enter / click to capture"
        )
        self._magnifier_job: str | None = None

    def show(self, parent: tk.Tk) -> None:
        self._origin_left, self._origin_top, self._screen_w, self._screen_h = virtual_screen_bounds()

        self._root = tk.Toplevel(parent)
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.22)
        self._root.configure(bg="black")
        self._root.geometry(
            f"{self._screen_w}x{self._screen_h}+{self._origin_left}+{self._origin_top}"
        )

        self._canvas = tk.Canvas(
            self._root,
            cursor="crosshair",
            highlightthickness=0,
            bg="black",
            width=self._screen_w,
            height=self._screen_h,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        info = tk.Toplevel(self._root)
        info.overrideredirect(True)
        info.attributes("-topmost", True)
        info.configure(bg="#1a1a1a")
        tk.Label(
            info,
            textvariable=self._info_var,
            fg="white",
            bg="#1a1a1a",
            font=("Segoe UI", 10),
            padx=10,
            pady=6,
        ).pack()
        info.geometry(f"+{self._origin_left + 12}+{self._origin_top + 12}")
        self._info_window = info

        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self._root.bind("<KeyPress-space>", self._on_swap_corner)
        self._root.bind("<Return>", self._on_confirm)
        self._root.bind("<Escape>", self._on_cancel)
        for key, dx, dy in (
            ("Left", -1, 0),
            ("Right", 1, 0),
            ("Up", 0, -1),
            ("Down", 0, 1),
        ):
            self._root.bind(f"<KeyPress-{key}>", lambda e, dx=dx, dy=dy: self._nudge_free(dx, dy))
        self._root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._root.deiconify()
        self._root.grab_set()
        self._root.focus_force()
        self._magnifier.show()

    def _to_local(self, x: int, y: int) -> tuple[int, int]:
        return screen_to_local(x, y, self._origin_left, self._origin_top)

    def _active_free(self) -> tuple[int, int] | None:
        if self._pinned is None:
            return None
        if self._free_follows_mouse:
            return self._mouse_x, self._mouse_y
        return self._free

    def _current_rect(self) -> tuple[int, int, int, int] | None:
        free = self._active_free()
        if self._pinned is None or free is None:
            return None
        return normalize_rect((self._pinned[0], self._pinned[1], free[0], free[1]))

    def _clear_shapes(self) -> None:
        if not self._canvas:
            return
        for item_id in self._shape_ids:
            self._canvas.delete(item_id)
        self._shape_ids.clear()

    def _redraw(self) -> None:
        if not self._canvas:
            return
        self._clear_shapes()

        focus_x, focus_y = self._mouse_x, self._mouse_y
        free = self._active_free()
        if free and not self._free_follows_mouse:
            focus_x, focus_y = free

        lx, ly = self._to_local(focus_x, focus_y)
        self._shape_ids.append(
            self._canvas.create_line(lx, 0, lx, self._screen_h, fill="#ffffff", width=1, dash=(3, 5))
        )
        self._shape_ids.append(
            self._canvas.create_line(0, ly, self._screen_w, ly, fill="#ffffff", width=1, dash=(3, 5))
        )

        if self._pinned and free:
            px, py = self._to_local(self._pinned[0], self._pinned[1])
            self._shape_ids.append(
                self._canvas.create_oval(px - 4, py - 4, px + 4, py + 4, outline="#ffcc00", width=2)
            )

        rect = self._current_rect()
        if rect:
            left, top, right, bottom = rect
            x1, y1 = self._to_local(left, top)
            x2, y2 = self._to_local(right, bottom)

            self._shape_ids.append(
                self._canvas.create_rectangle(x1, y1, x2, y2, outline="#00b4ff", width=2)
            )
            self._shape_ids.append(
                self._canvas.create_rectangle(
                    x1 + 1, y1 + 1, x2 - 1, y2 - 1, outline="#ffffff", width=1, dash=(4, 3)
                )
            )

            width = right - left
            height = bottom - top
            self._info_var.set(
                f"{width} × {height} px  •  Space swap corner  •  Arrows ±1px  •  Enter / click capture"
            )
        else:
            self._info_var.set(
                "Click a corner • Space swaps pinned corner • Arrows nudge 1px • Enter / click to capture"
            )

    def _schedule_magnifier(self, screen_x: int, screen_y: int) -> None:
        if not self._root:
            return
        if self._magnifier_job is not None:
            self._root.after_cancel(self._magnifier_job)

        def update() -> None:
            self._magnifier.update(screen_x, screen_y)
            self._magnifier_job = None

        self._magnifier_job = self._root.after(30, update)

    def _update_focus_point(self) -> None:
        free = self._active_free()
        if free and not self._free_follows_mouse:
            self._schedule_magnifier(free[0], free[1])
        else:
            self._schedule_magnifier(self._mouse_x, self._mouse_y)

    def _on_motion(self, event: tk.Event) -> None:
        self._mouse_x = event.x_root
        self._mouse_y = event.y_root
        if self._pinned is not None:
            self._free_follows_mouse = True
        self._redraw()
        self._update_focus_point()

    def _on_click(self, event: tk.Event) -> None:
        if self._pinned is None:
            self._pinned = (event.x_root, event.y_root)
            self._free = (event.x_root, event.y_root)
            self._free_follows_mouse = True
            self._mouse_x = event.x_root
            self._mouse_y = event.y_root
            self._redraw()
            self._update_focus_point()
            return
        self._confirm()

    def _on_swap_corner(self, _event: tk.Event) -> str:
        if self._pinned is None:
            self._pinned = (self._mouse_x, self._mouse_y)
            self._free = (self._mouse_x, self._mouse_y)
            self._free_follows_mouse = True
            self._redraw()
            return "break"

        current_free = self._active_free()
        if current_free is None:
            return "break"

        old_pinned = self._pinned
        self._pinned = current_free
        self._free = old_pinned
        self._free_follows_mouse = False
        self._redraw()
        self._update_focus_point()
        return "break"

    def _nudge_free(self, dx: int, dy: int) -> str:
        if self._pinned is None:
            return "break"

        if self._free_follows_mouse:
            self._free = (self._mouse_x, self._mouse_y)
            self._free_follows_mouse = False

        if self._free is None:
            self._free = (self._mouse_x, self._mouse_y)

        self._free = (self._free[0] + dx, self._free[1] + dy)
        self._redraw()
        self._schedule_magnifier(self._free[0], self._free[1])
        return "break"

    def _on_confirm(self, _event: tk.Event | None = None) -> None:
        self._confirm()

    def _confirm(self) -> None:
        rect = self._current_rect()
        if rect is None:
            return
        left, top, right, bottom = rect
        if right - left < 2 or bottom - top < 2:
            return
        self._finish(rect)

    def _on_cancel(self, _event: tk.Event | None = None) -> None:
        self._finish(None)

    def _finish(self, rect: tuple[int, int, int, int] | None) -> None:
        self._magnifier.destroy()
        if hasattr(self, "_info_window"):
            self._info_window.destroy()
        if self._root:
            self._root.grab_release()
            self._root.destroy()
            self._root = None
        self._on_complete(rect)