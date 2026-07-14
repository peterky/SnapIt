"""Programmatic mini-icons for editor tools."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from PIL import Image, ImageDraw, ImageTk

ICON_SIZE = 28
FG = (230, 230, 230, 255)
ACCENT = (0, 180, 255, 255)
MUTED = (120, 120, 120, 255)
BG = (45, 45, 45, 255)
BG_ACTIVE = (0, 100, 160, 255)


def _blank() -> Image.Image:
    return Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))


def _icon_select(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((6, 6, 20, 20), outline=FG, width=2)
    draw.line((6, 6, 10, 6, 10, 10), fill=ACCENT, width=2)
    draw.line((20, 20, 16, 20, 16, 16), fill=ACCENT, width=2)


def _icon_line(draw: ImageDraw.ImageDraw) -> None:
    draw.line((6, 22, 22, 6), fill=FG, width=3)


def _icon_arrow(draw: ImageDraw.ImageDraw) -> None:
    draw.line((6, 22, 18, 10), fill=FG, width=3)
    draw.polygon([(22, 6), (14, 8), (16, 14)], fill=FG)


def _icon_rect(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((7, 8, 21, 20), outline=FG, width=3)


def _icon_ellipse(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((7, 8, 21, 20), outline=FG, width=3)


def _icon_freehand(draw: ImageDraw.ImageDraw) -> None:
    draw.line([(6, 18), (10, 10), (14, 16), (18, 8), (22, 14)], fill=FG, width=3)


def _icon_text(draw: ImageDraw.ImageDraw) -> None:
    draw.text((8, 6), "T", fill=FG)


def _icon_crop(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((8, 8, 20, 20), outline=MUTED, width=2)
    draw.line((5, 5, 5, 12, 12, 12), fill=FG, width=2)
    draw.line((23, 23, 23, 16, 16, 16), fill=FG, width=2)


def _icon_pick_color(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((8, 8, 20, 20), fill=(255, 59, 48, 255), outline=FG, width=1)
    draw.line((18, 18, 24, 24), fill=FG, width=2)


def _icon_pick_bg(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((6, 10, 22, 20), fill=(60, 60, 60, 255), outline=FG, width=1)
    draw.text((10, 9), "BG", fill=FG)


ICON_DRAWERS: dict[str, Callable[[ImageDraw.ImageDraw], None]] = {
    "select": _icon_select,
    "line": _icon_line,
    "arrow": _icon_arrow,
    "rect": _icon_rect,
    "ellipse": _icon_ellipse,
    "freehand": _icon_freehand,
    "text": _icon_text,
    "crop": _icon_crop,
    "pick_color": _icon_pick_color,
    "pick_transparent": _icon_pick_bg,
}


def _render_icon(tool_id: str, active: bool = False) -> Image.Image:
    image = _blank()
    if active:
        bg = ImageDraw.Draw(image)
        bg.rounded_rectangle((1, 1, ICON_SIZE - 2, ICON_SIZE - 2), radius=5, fill=BG_ACTIVE)
    draw = ImageDraw.Draw(image)
    drawer = ICON_DRAWERS.get(tool_id)
    if drawer:
        drawer(draw)
    return image


class ToolIconToolbar:
    """Icon button toolbar that replaces radiobuttons."""

    def __init__(
        self,
        parent: tk.Widget,
        tools: list[tuple[str, str, str]],
        variable: tk.StringVar,
        on_change: Callable[[], None],
    ) -> None:
        self._frame = tk.Frame(parent, bg="#2f2f2f")
        self._variable = variable
        self._on_change = on_change
        self._photos: dict[str, ImageTk.PhotoImage] = {}
        self._buttons: dict[str, tk.Button] = {}

        for _label, tool_id, tooltip in tools:
            normal = ImageTk.PhotoImage(_render_icon(tool_id, active=False))
            active = ImageTk.PhotoImage(_render_icon(tool_id, active=True))
            self._photos[f"{tool_id}_normal"] = normal
            self._photos[f"{tool_id}_active"] = active

            button = tk.Button(
                self._frame,
                image=normal,
                relief=tk.FLAT,
                bd=0,
                bg="#2f2f2f",
                activebackground="#3a3a3a",
                cursor="hand2",
                command=lambda tid=tool_id: self._select(tid),
            )
            button.pack(side=tk.LEFT, padx=1)
            self._buttons[tool_id] = button
            self._attach_tooltip(button, tooltip)

        self._variable.trace_add("write", lambda *_: self._sync_active())
        self._sync_active()

    @property
    def widget(self) -> tk.Frame:
        return self._frame

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        tip: tk.Toplevel | None = None

        def show(_event: tk.Event) -> None:
            nonlocal tip
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.attributes("-topmost", True)
            x = widget.winfo_rootx() + 4
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip.geometry(f"+{x}+{y}")
            tk.Label(
                tip,
                text=text,
                bg="#222222",
                fg="#eeeeee",
                padx=6,
                pady=3,
                font=("Segoe UI", 9),
            ).pack()

        def hide(_event: tk.Event) -> None:
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _select(self, tool_id: str) -> None:
        self._variable.set(tool_id)
        self._on_change()

    def _sync_active(self) -> None:
        current = self._variable.get()
        for tool_id, button in self._buttons.items():
            photo = self._photos[f"{tool_id}_active" if tool_id == current else f"{tool_id}_normal"]
            button.configure(image=photo)