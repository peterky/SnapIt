"""Render markup annotations onto a PIL image."""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont

ShapeKind = Literal["line", "arrow", "rect", "ellipse"]
AnnotationKind = Literal["line", "arrow", "rect", "ellipse", "freehand", "text"]


@dataclass
class ShapeAnnotation:
    kind: ShapeKind
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class FreehandAnnotation:
    kind: Literal["freehand"]
    points: list[tuple[float, float]]
    color: str
    width: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TextAnnotation:
    kind: Literal["text"]
    x: float
    y: float
    text: str
    color: str
    font_size: int
    bg_color: str | None
    padding: int = 6
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


Annotation = ShapeAnnotation | FreehandAnnotation | TextAnnotation

SAVE_FORMATS = {
    "PNG": ("PNG files", "*.png"),
    "JPEG": ("JPEG files", "*.jpg"),
    "BMP": ("Bitmap files", "*.bmp"),
    "GIF": ("GIF files", "*.gif"),
    "WEBP": ("WebP files", "*.webp"),
}


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _arrow_head(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str,
    width: int,
) -> None:
    angle = math.atan2(y2 - y1, x2 - x1)
    head_len = max(12, width * 4)
    spread = math.pi / 7
    points = [
        (x2, y2),
        (
            x2 - head_len * math.cos(angle - spread),
            y2 - head_len * math.sin(angle - spread),
        ),
        (
            x2 - head_len * math.cos(angle + spread),
            y2 - head_len * math.sin(angle + spread),
        ),
    ]
    draw.polygon(points, fill=color)


def _normalize_rect(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def render_image(base: Image.Image, annotations: list[Annotation]) -> Image.Image:
    image = base.convert("RGBA")
    draw = ImageDraw.Draw(image)

    for ann in annotations:
        if isinstance(ann, ShapeAnnotation):
            if ann.kind in {"line", "arrow"}:
                draw.line((ann.x1, ann.y1, ann.x2, ann.y2), fill=ann.color, width=ann.width)
                if ann.kind == "arrow":
                    _arrow_head(draw, ann.x1, ann.y1, ann.x2, ann.y2, ann.color, ann.width)
            elif ann.kind == "rect":
                left, top, right, bottom = _normalize_rect(ann.x1, ann.y1, ann.x2, ann.y2)
                draw.rectangle((left, top, right, bottom), outline=ann.color, width=ann.width)
            elif ann.kind == "ellipse":
                left, top, right, bottom = _normalize_rect(ann.x1, ann.y1, ann.x2, ann.y2)
                draw.ellipse((left, top, right, bottom), outline=ann.color, width=ann.width)
        elif isinstance(ann, FreehandAnnotation) and len(ann.points) >= 2:
            draw.line(ann.points, fill=ann.color, width=ann.width, joint="curve")
        elif ann.kind == "text":
            font = _load_font(ann.font_size)
            bbox = draw.textbbox((ann.x, ann.y), ann.text, font=font)
            if ann.bg_color:
                pad = ann.padding
                draw.rectangle(
                    (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
                    fill=ann.bg_color,
                )
            draw.text((ann.x, ann.y), ann.text, fill=ann.color, font=font)

    return image


def sample_pixel_color(image: Image.Image, x: int, y: int) -> str:
    clamped_x = max(0, min(int(x), image.width - 1))
    clamped_y = max(0, min(int(y), image.height - 1))
    pixel = image.convert("RGB").getpixel((clamped_x, clamped_y))
    return f"#{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}"


def annotation_bounds(ann: Annotation, draw: ImageDraw.ImageDraw | None = None) -> tuple[float, float, float, float]:
    if isinstance(ann, FreehandAnnotation):
        xs = [p[0] for p in ann.points]
        ys = [p[1] for p in ann.points]
        pad = ann.width + 4
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    if isinstance(ann, ShapeAnnotation):
        return _normalize_rect(ann.x1, ann.y1, ann.x2, ann.y2)
    font = _load_font(ann.font_size)
    probe = draw or ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = probe.textbbox((ann.x, ann.y), ann.text, font=font)
    pad = ann.padding if ann.bg_color else 0
    return bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad


def _point_line_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _point_in_ellipse(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    left, top, right, bottom = _normalize_rect(x1, y1, x2, y2)
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    rx = max((right - left) / 2, 1.0)
    ry = max((bottom - top) / 2, 1.0)
    return ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1.0


def hit_test_annotation(ann: Annotation, x: float, y: float, tolerance: float = 8.0) -> bool:
    if isinstance(ann, FreehandAnnotation):
        for index in range(1, len(ann.points)):
            x1, y1 = ann.points[index - 1]
            x2, y2 = ann.points[index]
            if _point_line_distance(x, y, x1, y1, x2, y2) <= tolerance + ann.width:
                return True
        return False
    if isinstance(ann, ShapeAnnotation):
        if ann.kind in {"line", "arrow"}:
            return _point_line_distance(x, y, ann.x1, ann.y1, ann.x2, ann.y2) <= tolerance + ann.width
        if ann.kind == "rect":
            left, top, right, bottom = _normalize_rect(ann.x1, ann.y1, ann.x2, ann.y2)
            return left - tolerance <= x <= right + tolerance and top - tolerance <= y <= bottom + tolerance
        if ann.kind == "ellipse":
            left, top, right, bottom = _normalize_rect(ann.x1, ann.y1, ann.x2, ann.y2)
            if not (left - tolerance <= x <= right + tolerance and top - tolerance <= y <= bottom + tolerance):
                return False
            return _point_in_ellipse(x, y, ann.x1, ann.y1, ann.x2, ann.y2)
    left, top, right, bottom = annotation_bounds(ann)
    return left <= x <= right and top <= y <= bottom


def find_annotation_at(annotations: list[Annotation], x: float, y: float) -> int | None:
    for index in range(len(annotations) - 1, -1, -1):
        if hit_test_annotation(annotations[index], x, y):
            return index
    return None


def move_annotation(ann: Annotation, dx: float, dy: float) -> None:
    if isinstance(ann, FreehandAnnotation):
        ann.points = [(px + dx, py + dy) for px, py in ann.points]
    elif isinstance(ann, ShapeAnnotation):
        ann.x1 += dx
        ann.y1 += dy
        ann.x2 += dx
        ann.y2 += dy
    else:
        ann.x += dx
        ann.y += dy


def resize_shape_annotation(ann: ShapeAnnotation, handle: str, x: float, y: float) -> None:
    if handle == "nw":
        ann.x1, ann.y1 = x, y
    elif handle == "ne":
        ann.x2, ann.y1 = x, y
    elif handle == "sw":
        ann.x1, ann.y2 = x, y
    elif handle == "se":
        ann.x2, ann.y2 = x, y
    elif handle == "start":
        ann.x1, ann.y1 = x, y
    elif handle == "end":
        ann.x2, ann.y2 = x, y


def shape_handles(ann: ShapeAnnotation) -> list[tuple[str, float, float]]:
    left, top, right, bottom = _normalize_rect(ann.x1, ann.y1, ann.x2, ann.y2)
    if ann.kind in {"line", "arrow"}:
        return [("start", ann.x1, ann.y1), ("end", ann.x2, ann.y2)]
    return [
        ("nw", left, top),
        ("ne", right, top),
        ("sw", left, bottom),
        ("se", right, bottom),
    ]


def annotations_to_dicts(annotations: list[Annotation]) -> list[dict[str, Any]]:
    return [asdict(ann) for ann in annotations]


def annotation_from_dict(data: dict[str, Any]) -> Annotation:
    kind = data.get("kind")
    if kind == "freehand":
        return FreehandAnnotation(
            kind="freehand",
            points=[(float(px), float(py)) for px, py in data.get("points", [])],
            color=str(data["color"]),
            width=int(data["width"]),
            id=str(data.get("id", uuid.uuid4())),
        )
    if kind == "text":
        return TextAnnotation(
            kind="text",
            x=float(data["x"]),
            y=float(data["y"]),
            text=str(data["text"]),
            color=str(data["color"]),
            font_size=int(data["font_size"]),
            bg_color=data.get("bg_color"),
            padding=int(data.get("padding", 6)),
            id=str(data.get("id", uuid.uuid4())),
        )
    return ShapeAnnotation(
        kind=kind,
        x1=float(data["x1"]),
        y1=float(data["y1"]),
        x2=float(data["x2"]),
        y2=float(data["y2"]),
        color=str(data["color"]),
        width=int(data["width"]),
        id=str(data.get("id", uuid.uuid4())),
    )


# Backward compatibility alias used by older editor imports.
LineAnnotation = ShapeAnnotation