"""Image editor with markup, crop, save-as, and snap library."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from snapit.annotation_io import load_sidecar, resolve_base_image_path, save_sidecar
from snapit.clipboard_util import copy_image_to_clipboard
from snapit.editor_render import (
    SAVE_FORMATS,
    Annotation,
    FreehandAnnotation,
    ShapeAnnotation,
    TextAnnotation,
    annotation_bounds,
    find_annotation_at,
    move_annotation,
    render_image,
    resize_shape_annotation,
    sample_pixel_color,
    shape_handles,
)
from snapit.library import list_snapshots
from snapit.tool_icons import ToolIconToolbar

logger = logging.getLogger(__name__)

TOOL_SELECT = "select"
TOOL_LINE = "line"
TOOL_ARROW = "arrow"
TOOL_RECT = "rect"
TOOL_ELLIPSE = "ellipse"
TOOL_TEXT = "text"
TOOL_CROP = "crop"
TOOL_PICK_COLOR = "pick_color"
TOOL_PICK_TRANSPARENT = "pick_transparent"
TOOL_FREEHAND = "freehand"

SHAPE_TOOLS = {TOOL_LINE, TOOL_ARROW, TOOL_RECT, TOOL_ELLIPSE, TOOL_FREEHAND}

LIBRARY_HEIGHT = 132
THUMB_SIZE = 96
MIN_CANVAS_HEIGHT = 240
WINDOW_CHROME_WIDTH = 28
WINDOW_CHROME_HEIGHT = 56


@dataclass
class _EditorState:
    base: Image.Image
    annotations: list[Annotation]
    base_source_path: Path | None


class ImageEditorWindow:
    def __init__(
        self,
        parent: tk.Tk,
        image: Image.Image,
        save_directory: Path,
        filename_prefix: str,
        copy_to_clipboard: bool,
        default_format: str = "PNG",
        base_source_path: Path | None = None,
        on_close: Callable[[], None] | None = None,
        on_capture_region: Callable[[], None] | None = None,
        on_capture_active_window: Callable[[], None] | None = None,
        on_capture_fullscreen: Callable[[], None] | None = None,
        on_video_region: Callable[[], None] | None = None,
        on_video_active_window: Callable[[], None] | None = None,
        on_video_fullscreen: Callable[[], None] | None = None,
    ) -> None:
        self._parent = parent
        self._base_image = image.convert("RGB")
        self._annotations: list[Annotation] = []
        self._undo_stack: list[_EditorState] = []
        self._save_directory = save_directory
        self._filename_prefix = filename_prefix
        self._copy_to_clipboard = copy_to_clipboard
        self._default_format = default_format.upper()
        self._base_source_path = base_source_path
        self._current_image_path: Path | None = None
        self._on_close = on_close
        self._on_capture_region = on_capture_region
        self._on_capture_active_window = on_capture_active_window
        self._on_capture_fullscreen = on_capture_fullscreen
        self._on_video_region = on_video_region
        self._on_video_active_window = on_video_active_window
        self._on_video_fullscreen = on_video_fullscreen

        self._tool = tk.StringVar(value=TOOL_ARROW)
        self._freehand_points: list[tuple[float, float]] = []
        self._freehand_undo_pushed = False
        self._stroke_color = "#ff3b30"
        self._text_bg_color: str | None = None
        self._stroke_width = 3
        self._font_size = 16

        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._photo: ImageTk.PhotoImage | None = None
        self._thumb_photos: list[ImageTk.PhotoImage] = []
        self._drag_start: tuple[float, float] | None = None
        self._temp_item: int | None = None
        self._crop_rect_item: int | None = None
        self._resize_job: str | None = None
        self._library_visible = tk.BooleanVar(value=True)

        self._selected_index: int | None = None
        self._active_handle: str | None = None
        self._selection_items: list[int] = []
        self._select_undo_pushed = False

        self._window = tk.Toplevel(parent)
        self._window.title("SnapIt Editor")
        self._window.geometry("+80+40")
        self._window.protocol("WM_DELETE_WINDOW", self._close)
        self._window.bind("<Delete>", self._delete_selected)
        self._window.bind("<BackSpace>", self._delete_selected)
        self._build_ui()
        self._apply_initial_geometry()
        self._window.after(50, self._refresh_canvas)
        self._refresh_library()
        self._present()

    def _build_ui(self) -> None:
        self._toolbar = ttk.Frame(self._window, padding=8)
        self._toolbar.pack(fill=tk.X)
        toolbar = self._toolbar

        tool_defs = [
            ("Select", TOOL_SELECT, "Select / move annotations"),
            ("Line", TOOL_LINE, "Draw line"),
            ("Arrow", TOOL_ARROW, "Draw arrow"),
            ("Square", TOOL_RECT, "Draw rectangle"),
            ("Circle", TOOL_ELLIPSE, "Draw circle / ellipse"),
            ("Free draw", TOOL_FREEHAND, "Freehand pen"),
            ("Text", TOOL_TEXT, "Place text"),
            ("Crop", TOOL_CROP, "Crop image"),
            ("Pick color", TOOL_PICK_COLOR, "Sample draw color from pixel"),
            ("Sample text BG", TOOL_PICK_TRANSPARENT, "Sample text background color"),
        ]
        icon_toolbar = ToolIconToolbar(toolbar, tool_defs, self._tool, self._on_tool_changed)
        icon_toolbar.widget.pack(side=tk.LEFT)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text="Color…", command=self._choose_color).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Clear text BG", command=self._clear_text_bg).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Undo", command=self._undo).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Apply crop", command=self._apply_crop).pack(side=tk.LEFT, padx=(0, 5))

        if self._on_capture_region:
            capture_menu = ttk.Menubutton(toolbar, text="Capture ▾")
            capture_menu.pack(side=tk.LEFT, padx=(8, 0))
            menu = tk.Menu(capture_menu, tearoff=0)
            menu.add_command(label="Region", command=self._on_capture_region)
            if self._on_capture_active_window:
                menu.add_command(label="Active window", command=self._on_capture_active_window)
            if self._on_capture_fullscreen:
                menu.add_command(label="Full screen", command=self._on_capture_fullscreen)
            if self._on_video_region or self._on_video_active_window or self._on_video_fullscreen:
                menu.add_separator()
                if self._on_video_region:
                    menu.add_command(label="Record region (video)", command=self._on_video_region)
                if self._on_video_active_window:
                    menu.add_command(label="Record active window (video)", command=self._on_video_active_window)
                if self._on_video_fullscreen:
                    menu.add_command(label="Record full screen (video)", command=self._on_video_fullscreen)
            capture_menu["menu"] = menu

        ttk.Button(toolbar, text="Copy image", command=self._copy_to_clipboard).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(toolbar, text="Save as…", command=self._save_as).pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="Close", command=self._close).pack(side=tk.RIGHT, padx=(0, 8))

        self._color_preview = tk.Canvas(toolbar, width=28, height=28, highlightthickness=1, highlightbackground="#888")
        self._color_preview.pack(side=tk.LEFT, padx=(8, 0))
        self._update_color_preview()

        self._status = tk.StringVar(value="Ready")
        ttk.Label(toolbar, textvariable=self._status).pack(side=tk.LEFT, padx=(12, 0))

        self._options = ttk.Frame(self._window, padding=(8, 0, 8, 8))
        self._options.pack(fill=tk.X)
        options = self._options
        ttk.Label(options, text="Stroke width:").pack(side=tk.LEFT)
        self._width_spin = ttk.Spinbox(options, from_=1, to=20, width=4, command=self._read_width)
        self._width_spin.set(self._stroke_width)
        self._width_spin.pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(options, text="Font size:").pack(side=tk.LEFT)
        self._font_spin = ttk.Spinbox(options, from_=8, to=72, width=4, command=self._read_font_size)
        self._font_spin.set(self._font_size)
        self._font_spin.pack(side=tk.LEFT, padx=(6, 16))
        self._bg_label = ttk.Label(options, text="Text BG: transparent")
        self._bg_label.pack(side=tk.LEFT)

        self._canvas = tk.Canvas(self._window, bg="#2b2b2b", highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self._library_header = ttk.Frame(self._window, padding=(8, 4))
        self._library_header.pack(fill=tk.X)
        library_header = self._library_header
        self._library_toggle = ttk.Checkbutton(
            library_header,
            text="Show snap library",
            variable=self._library_visible,
            command=self._toggle_library,
        )
        self._library_toggle.pack(side=tk.LEFT)
        ttk.Button(library_header, text="Refresh", command=self._refresh_library).pack(side=tk.RIGHT)

        self._library_shell = ttk.Frame(self._window, padding=(8, 0, 8, 8))
        self._library_shell.pack(fill=tk.X)

        self._library_canvas = tk.Canvas(
            self._library_shell,
            height=LIBRARY_HEIGHT,
            bg="#1e1e1e",
            highlightthickness=1,
            highlightbackground="#444444",
            xscrollcommand=lambda *_: None,
        )
        self._library_scroll = ttk.Scrollbar(self._library_shell, orient=tk.HORIZONTAL, command=self._library_canvas.xview)
        self._library_canvas.configure(xscrollcommand=self._library_scroll.set)
        self._library_scroll.pack(fill=tk.X, side=tk.BOTTOM)
        self._library_canvas.pack(fill=tk.X, side=tk.TOP)
        self._library_inner = ttk.Frame(self._library_canvas)
        self._library_window_id = self._library_canvas.create_window((0, 0), window=self._library_inner, anchor=tk.NW)
        self._library_inner.bind("<Configure>", self._on_library_configure)

    def _apply_initial_geometry(self) -> None:
        """Size the window so the full toolbar fits without clipping."""
        self._window.update_idletasks()

        min_width = (
            max(
                self._toolbar.winfo_reqwidth(),
                self._options.winfo_reqwidth(),
                self._library_header.winfo_reqwidth(),
            )
            + WINDOW_CHROME_WIDTH
        )

        if self._library_visible.get():
            library_block = self._library_header.winfo_reqheight() + self._library_shell.winfo_reqheight() + 16
        else:
            library_block = self._library_header.winfo_reqheight() + 8

        min_height = (
            self._toolbar.winfo_reqheight()
            + self._options.winfo_reqheight()
            + library_block
            + MIN_CANVAS_HEIGHT
            + WINDOW_CHROME_HEIGHT
        )

        self._window.minsize(min_width, min_height)

        screen_w = self._window.winfo_screenwidth()
        screen_h = self._window.winfo_screenheight()
        width = min(max(min_width, int(screen_w * 0.85)), screen_w - 40)
        height = min(max(min_height, int(screen_h * 0.8)), screen_h - 40)

        self._window.geometry(f"{width}x{height}")

    def _present(self) -> None:
        self._window.deiconify()
        self._window.wm_state("normal")
        self._window.attributes("-topmost", True)
        self._window.lift()
        self._window.focus_force()
        self._window.after(200, lambda: self._window.attributes("-topmost", False))

    def _toggle_library(self) -> None:
        if self._library_visible.get():
            self._library_shell.pack(fill=tk.X, padx=8, pady=(0, 8))
            self._refresh_library()
        else:
            self._library_shell.pack_forget()

    def _on_library_configure(self, _event: tk.Event) -> None:
        self._library_canvas.configure(scrollregion=self._library_canvas.bbox("all"))

    def _on_canvas_resize(self, event: tk.Event) -> None:
        if event.widget is not self._canvas:
            return
        if self._resize_job is not None:
            self._window.after_cancel(self._resize_job)
        self._resize_job = self._window.after(60, self._refresh_canvas)

    def _on_tool_changed(self) -> None:
        tool = self._tool.get()
        if tool == TOOL_SELECT:
            self._status.set("Click an annotation to select it. Drag to move; drag handles to resize.")
        elif tool == TOOL_CROP:
            self._status.set("Drag a crop rectangle, then click Apply crop.")
        elif tool == TOOL_PICK_COLOR:
            self._status.set("Click a pixel to set the draw color.")
        elif tool == TOOL_PICK_TRANSPARENT:
            self._status.set("Click a pixel to sample a text background color.")
        elif tool == TOOL_FREEHAND:
            self._status.set("Click and drag to draw freehand.")
        else:
            self._status.set(f"Tool: {tool}")

    def _read_width(self) -> None:
        try:
            self._stroke_width = max(1, int(self._width_spin.get()))
            self._apply_style_to_selection()
        except ValueError:
            pass

    def _read_font_size(self) -> None:
        try:
            self._font_size = max(8, int(self._font_spin.get()))
            self._apply_style_to_selection()
        except ValueError:
            pass

    def _apply_style_to_selection(self) -> None:
        if self._selected_index is None:
            return
        ann = self._annotations[self._selected_index]
        if isinstance(ann, (ShapeAnnotation, FreehandAnnotation)):
            ann.width = self._stroke_width
            ann.color = self._stroke_color
        elif isinstance(ann, TextAnnotation):
            ann.font_size = self._font_size
            ann.color = self._stroke_color
            ann.bg_color = self._text_bg_color
        self._refresh_canvas()

    def _choose_color(self) -> None:
        color = colorchooser.askcolor(color=self._stroke_color, parent=self._window)
        if color and color[1]:
            self._stroke_color = color[1]
            self._update_color_preview()
            self._apply_style_to_selection()
            self._status.set(f"Draw color set to {self._stroke_color}")

    def _clear_text_bg(self) -> None:
        self._text_bg_color = None
        self._bg_label.config(text="Text BG: transparent")
        self._apply_style_to_selection()

    def _update_color_preview(self) -> None:
        self._color_preview.delete("all")
        self._color_preview.create_rectangle(2, 2, 26, 26, fill=self._stroke_color, outline="")

    def _compute_layout(self) -> None:
        canvas_w = max(self._canvas.winfo_width(), 1)
        canvas_h = max(self._canvas.winfo_height(), 1)
        img_w = self._base_image.width
        img_h = self._base_image.height
        self._scale = min(canvas_w / img_w, canvas_h / img_h)
        display_w = img_w * self._scale
        display_h = img_h * self._scale
        self._offset_x = (canvas_w - display_w) / 2
        self._offset_y = (canvas_h - display_h) / 2

    def _image_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return x * self._scale + self._offset_x, y * self._scale + self._offset_y

    def _canvas_to_image(self, x: float, y: float) -> tuple[float, float]:
        return (x - self._offset_x) / self._scale, (y - self._offset_y) / self._scale

    def _canvas_coords(self, event: tk.Event) -> tuple[float, float]:
        return self._canvas_to_image(float(event.x), float(event.y))

    def _current_render(self) -> Image.Image:
        return render_image(self._base_image, self._annotations)

    def _refresh_canvas(self) -> None:
        self._resize_job = None
        self._compute_layout()
        rendered = self._current_render()
        display_w = max(1, int(rendered.width * self._scale))
        display_h = max(1, int(rendered.height * self._scale))
        display = rendered.resize((display_w, display_h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(display)
        self._canvas.delete("all")
        self._canvas.create_image(self._offset_x, self._offset_y, image=self._photo, anchor=tk.NW)
        self._crop_rect_item = None
        self._temp_item = None
        self._draw_selection_overlay()

    def _draw_selection_overlay(self) -> None:
        for item in self._selection_items:
            self._canvas.delete(item)
        self._selection_items.clear()

        if self._selected_index is None or self._selected_index >= len(self._annotations):
            return

        ann = self._annotations[self._selected_index]
        left, top, right, bottom = annotation_bounds(ann)
        cx1, cy1 = self._image_to_canvas(left, top)
        cx2, cy2 = self._image_to_canvas(right, bottom)
        self._selection_items.append(
            self._canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="#00d4ff", width=1, dash=(3, 3))
        )

        if isinstance(ann, ShapeAnnotation):
            for _handle, hx, hy in shape_handles(ann):
                chx, chy = self._image_to_canvas(hx, hy)
                self._selection_items.append(
                    self._canvas.create_rectangle(
                        chx - 5, chy - 5, chx + 5, chy + 5, fill="#00d4ff", outline="#ffffff"
                    )
                )

    def _has_unsaved_changes(self) -> bool:
        return bool(self._annotations) or bool(self._undo_stack)

    def _load_image_from_path(self, path: Path) -> None:
        if self._has_unsaved_changes():
            proceed = messagebox.askyesno(
                "Load snapshot",
                "Replace the current image? Unsaved markup will be lost.",
                parent=self._window,
            )
            if not proceed:
                return

        try:
            base_path = resolve_base_image_path(path)
            loaded = Image.open(base_path).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc), parent=self._window)
            return

        sidecar = load_sidecar(path)
        annotations: list[Annotation] = []
        base_source = base_path
        if sidecar is not None:
            annotations, declared_base = sidecar
            if declared_base and declared_base.exists():
                base_source = declared_base

        self._base_image = loaded
        self._annotations = annotations
        self._undo_stack = []
        self._selected_index = None
        self._current_image_path = path
        self._base_source_path = base_source
        self._crop_rect_item = None
        self._temp_item = None
        self._refresh_canvas()
        if sidecar is not None:
            self._status.set(f"Loaded {path.name} with editable annotations")
        else:
            self._status.set(f"Loaded {path.name}")

    def _refresh_library(self) -> None:
        for child in self._library_inner.winfo_children():
            child.destroy()
        self._thumb_photos.clear()

        snapshots = list_snapshots(self._save_directory, filename_prefix=None)
        if not snapshots:
            ttk.Label(
                self._library_inner,
                text="No saved snaps yet. Save from the editor or capture without auto-edit enabled.",
                foreground="#aaaaaa",
            ).pack(padx=12, pady=24)
            self._library_canvas.configure(scrollregion=self._library_canvas.bbox("all"))
            return

        for index, path in enumerate(snapshots):
            frame = ttk.Frame(self._library_inner, padding=4)
            frame.grid(row=0, column=index, padx=(0, 6))

            try:
                thumb = Image.open(path)
                thumb.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(thumb)
                self._thumb_photos.append(photo)
            except Exception:
                ttk.Label(frame, text="?", width=8).pack()
                ttk.Label(frame, text=path.name, wraplength=THUMB_SIZE).pack()
                continue

            button = tk.Button(
                frame,
                image=photo,
                relief=tk.FLAT,
                bd=1,
                highlightthickness=1,
                highlightbackground="#555555",
                command=lambda p=path: self._load_image_from_path(p),
            )
            button.pack()
            label = path.name
            if load_sidecar(path) is not None:
                label += " ✎"
            ttk.Label(frame, text=label, wraplength=THUMB_SIZE, anchor=tk.CENTER).pack()

        self._library_inner.update_idletasks()
        self._library_canvas.configure(scrollregion=self._library_canvas.bbox("all"))

    def _push_undo(self) -> None:
        self._undo_stack.append(
            _EditorState(
                base=self._base_image.copy(),
                annotations=list(self._annotations),
                base_source_path=self._base_source_path,
            )
        )

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        state = self._undo_stack.pop()
        self._base_image = state.base
        self._annotations = state.annotations
        self._base_source_path = state.base_source_path
        self._selected_index = None
        self._refresh_canvas()
        self._status.set("Undid last change.")

    def _select_annotation(self, index: int | None) -> None:
        self._selected_index = index
        if index is not None:
            ann = self._annotations[index]
            if isinstance(ann, (ShapeAnnotation, FreehandAnnotation)):
                self._stroke_color = ann.color
                self._stroke_width = ann.width
                self._width_spin.set(ann.width)
            elif isinstance(ann, TextAnnotation):
                self._stroke_color = ann.color
                self._font_size = ann.font_size
                self._font_spin.set(ann.font_size)
                self._text_bg_color = ann.bg_color
                self._bg_label.config(
                    text="Text BG: transparent" if ann.bg_color is None else f"Text BG: {ann.bg_color}"
                )
            self._update_color_preview()
        self._draw_selection_overlay()

    def _hit_test_handle(self, x: float, y: float) -> tuple[int, str] | None:
        tolerance = 10 / max(self._scale, 0.01)
        for index in range(len(self._annotations) - 1, -1, -1):
            ann = self._annotations[index]
            if not isinstance(ann, ShapeAnnotation):
                continue
            for handle, hx, hy in shape_handles(ann):
                if abs(hx - x) <= tolerance and abs(hy - y) <= tolerance:
                    return index, handle
        return None

    def _on_press(self, event: tk.Event) -> None:
        self._read_width()
        self._read_font_size()
        ix, iy = self._canvas_coords(event)
        if ix < 0 or iy < 0 or ix > self._base_image.width or iy > self._base_image.height:
            return

        tool = self._tool.get()

        if tool == TOOL_SELECT:
            handle_hit = self._hit_test_handle(ix, iy)
            if handle_hit is not None:
                self._selected_index, self._active_handle = handle_hit
                self._drag_start = (ix, iy)
                self._select_undo_pushed = False
                self._sync_selection_style()
                return

            index = find_annotation_at(self._annotations, ix, iy)
            self._select_annotation(index)
            if index is not None:
                self._drag_start = (ix, iy)
                self._select_undo_pushed = False
            return

        if tool == TOOL_PICK_COLOR:
            color = sample_pixel_color(self._current_render(), ix, iy)
            self._stroke_color = color
            self._update_color_preview()
            self._status.set(f"Draw color sampled: {color}")
            return

        if tool == TOOL_PICK_TRANSPARENT:
            color = sample_pixel_color(self._current_render(), ix, iy)
            self._text_bg_color = color
            self._bg_label.config(text=f"Text BG: {color}")
            self._status.set(f"Text background sampled: {color}")
            return

        if tool == TOOL_TEXT:
            text = simpledialog.askstring("Add text", "Enter text:", parent=self._window)
            if text:
                self._push_undo()
                self._annotations.append(
                    TextAnnotation(
                        kind="text",
                        x=ix,
                        y=iy,
                        text=text,
                        color=self._stroke_color,
                        font_size=self._font_size,
                        bg_color=self._text_bg_color,
                    )
                )
                self._select_annotation(len(self._annotations) - 1)
                self._refresh_canvas()
            return

        if tool == TOOL_FREEHAND:
            self._freehand_points = [(ix, iy)]
            self._freehand_undo_pushed = False
            self._drag_start = (ix, iy)
            return

        self._drag_start = (ix, iy)
        if tool == TOOL_CROP and self._crop_rect_item is not None:
            self._canvas.delete(self._crop_rect_item)

    def _sync_selection_style(self) -> None:
        if self._selected_index is None:
            return
        ann = self._annotations[self._selected_index]
        if isinstance(ann, ShapeAnnotation):
            self._stroke_color = ann.color
            self._stroke_width = ann.width
            self._width_spin.set(ann.width)
            self._update_color_preview()

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag_start:
            return

        tool = self._tool.get()
        x1, y1 = self._drag_start
        x2, y2 = self._canvas_coords(event)

        if tool == TOOL_SELECT and self._selected_index is not None:
            if not self._select_undo_pushed:
                self._push_undo()
                self._select_undo_pushed = True
            ann = self._annotations[self._selected_index]
            if self._active_handle and isinstance(ann, ShapeAnnotation):
                resize_shape_annotation(ann, self._active_handle, x2, y2)
            else:
                move_annotation(ann, x2 - x1, y2 - y1)
                self._drag_start = (x2, y2)
            self._refresh_canvas()
            return

        if tool == TOOL_FREEHAND:
            self._freehand_points.append((x2, y2))
            if not self._freehand_undo_pushed:
                self._push_undo()
                self._freehand_undo_pushed = True
            if self._temp_item is not None:
                self._canvas.delete(self._temp_item)
            canvas_points: list[float] = []
            for px, py in self._freehand_points:
                cx, cy = self._image_to_canvas(px, py)
                canvas_points.extend((cx, cy))
            if len(canvas_points) >= 4:
                self._temp_item = self._canvas.create_line(
                    *canvas_points,
                    fill=self._stroke_color,
                    width=self._stroke_width,
                    smooth=True,
                    splinesteps=12,
                )
            return

        if tool not in SHAPE_TOOLS and tool != TOOL_CROP:
            return

        cx1, cy1 = self._image_to_canvas(x1, y1)
        cx2, cy2 = self._image_to_canvas(x2, y2)

        if self._temp_item is not None:
            self._canvas.delete(self._temp_item)

        if tool == TOOL_CROP:
            self._temp_item = self._canvas.create_rectangle(
                cx1, cy1, cx2, cy2, outline="#00b4ff", width=2, dash=(4, 4)
            )
            self._crop_rect_item = self._temp_item
        elif tool == TOOL_RECT:
            self._temp_item = self._canvas.create_rectangle(
                cx1, cy1, cx2, cy2, outline=self._stroke_color, width=self._stroke_width
            )
        elif tool == TOOL_ELLIPSE:
            self._temp_item = self._canvas.create_oval(
                cx1, cy1, cx2, cy2, outline=self._stroke_color, width=self._stroke_width
            )
        elif tool == TOOL_LINE:
            self._temp_item = self._canvas.create_line(
                cx1, cy1, cx2, cy2, fill=self._stroke_color, width=self._stroke_width
            )
        else:
            self._temp_item = self._canvas.create_line(
                cx1, cy1, cx2, cy2, fill=self._stroke_color, width=self._stroke_width, arrow=tk.LAST
            )

    def _on_release(self, event: tk.Event) -> None:
        if not self._drag_start:
            return

        tool = self._tool.get()
        if tool == TOOL_SELECT:
            self._active_handle = None
            self._drag_start = None
            self._select_undo_pushed = False
            self._draw_selection_overlay()
            return

        if tool == TOOL_FREEHAND:
            self._drag_start = None
            self._freehand_undo_pushed = False
            if len(self._freehand_points) >= 2:
                self._annotations.append(
                    FreehandAnnotation(
                        kind="freehand",
                        points=list(self._freehand_points),
                        color=self._stroke_color,
                        width=self._stroke_width,
                    )
                )
                self._select_annotation(len(self._annotations) - 1)
            self._freehand_points = []
            self._temp_item = None
            self._refresh_canvas()
            return

        if tool not in SHAPE_TOOLS:
            self._drag_start = None
            return

        x1, y1 = self._drag_start
        x2, y2 = self._canvas_coords(event)
        self._drag_start = None
        if abs(x2 - x1) < 2 and abs(y2 - y1) < 2:
            if self._temp_item is not None:
                self._canvas.delete(self._temp_item)
                self._temp_item = None
            return

        self._push_undo()
        kind = {
            TOOL_ARROW: "arrow",
            TOOL_LINE: "line",
            TOOL_RECT: "rect",
            TOOL_ELLIPSE: "ellipse",
        }[tool]
        self._annotations.append(
            ShapeAnnotation(
                kind=kind,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                color=self._stroke_color,
                width=self._stroke_width,
            )
        )
        self._temp_item = None
        self._select_annotation(len(self._annotations) - 1)
        self._refresh_canvas()

    def _delete_selected(self, _event: tk.Event | None = None) -> None:
        if self._selected_index is None:
            return
        self._push_undo()
        del self._annotations[self._selected_index]
        self._selected_index = None
        self._refresh_canvas()
        self._status.set("Deleted selected annotation.")

    def _apply_crop(self) -> None:
        if self._crop_rect_item is None:
            messagebox.showinfo("Crop", "Drag a crop rectangle first.", parent=self._window)
            return

        coords = self._canvas.coords(self._crop_rect_item)
        if len(coords) != 4:
            return

        x1, y1 = self._canvas_to_image(coords[0], coords[1])
        x2, y2 = self._canvas_to_image(coords[2], coords[3])
        left = int(min(x1, x2))
        top = int(min(y1, y2))
        right = int(max(x1, x2))
        bottom = int(max(y1, y2))

        if right - left < 2 or bottom - top < 2:
            messagebox.showinfo("Crop", "Crop area is too small.", parent=self._window)
            return

        rendered = self._current_render()
        self._push_undo()
        self._base_image = rendered.crop((left, top, right, bottom)).convert("RGB")
        self._annotations = []
        self._selected_index = None
        self._base_source_path = None
        self._crop_rect_item = None
        self._refresh_canvas()
        self._status.set("Crop applied.")

    def _copy_to_clipboard(self) -> None:
        try:
            image = self._current_render().convert("RGB")
            copy_image_to_clipboard(image)
            self._status.set("Copied edited image to clipboard.")
        except Exception as exc:
            messagebox.showerror("Clipboard", str(exc), parent=self._window)

    def _save_as(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fmt = self._default_format if self._default_format in SAVE_FORMATS else "PNG"
        ext = SAVE_FORMATS[fmt][1].replace("*", "")
        default_name = f"{self._filename_prefix}_{timestamp}{ext}"
        filetypes = [(label, pattern) for label, pattern in SAVE_FORMATS.values()]
        path_str = filedialog.asksaveasfilename(
            parent=self._window,
            title="Save image as",
            initialdir=str(self._save_directory),
            initialfile=default_name,
            defaultextension=ext,
            filetypes=filetypes,
        )
        if not path_str:
            return

        path = Path(path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = self._current_render()
        ext = path.suffix.lower().lstrip(".")

        save_kwargs: dict = {}
        if ext in {"jpg", "jpeg"}:
            image = image.convert("RGB")
            save_kwargs["quality"] = 95
        elif ext == "gif":
            image = image.convert("P", palette=Image.Palette.ADAPTIVE)
        elif ext == "bmp":
            image = image.convert("RGB")

        image.save(path, **save_kwargs)
        base_source = self._base_source_path or self._current_image_path
        save_sidecar(path, self._annotations, base_source=base_source)

        if self._copy_to_clipboard:
            copy_image_to_clipboard(image.convert("RGB") if image.mode == "RGBA" else image)

        self._current_image_path = path
        self._status.set(f"Saved to {path.name} (annotations remain editable)")
        logger.info("Editor saved %s", path)
        self._refresh_library()

    def _close(self) -> None:
        if self._on_close:
            self._on_close()
        self._window.destroy()


def open_image_editor(
    parent: tk.Tk,
    image: Image.Image,
    save_directory: Path,
    filename_prefix: str,
    copy_to_clipboard: bool,
    default_format: str = "PNG",
    base_source_path: Path | None = None,
    on_capture_region: Callable[[], None] | None = None,
    on_capture_active_window: Callable[[], None] | None = None,
    on_capture_fullscreen: Callable[[], None] | None = None,
    on_video_region: Callable[[], None] | None = None,
    on_video_active_window: Callable[[], None] | None = None,
    on_video_fullscreen: Callable[[], None] | None = None,
) -> ImageEditorWindow:
    return ImageEditorWindow(
        parent=parent,
        image=image,
        save_directory=save_directory,
        filename_prefix=filename_prefix,
        copy_to_clipboard=copy_to_clipboard,
        default_format=default_format,
        base_source_path=base_source_path,
        on_capture_region=on_capture_region,
        on_capture_active_window=on_capture_active_window,
        on_capture_fullscreen=on_capture_fullscreen,
        on_video_region=on_video_region,
        on_video_active_window=on_video_active_window,
        on_video_fullscreen=on_video_fullscreen,
    )