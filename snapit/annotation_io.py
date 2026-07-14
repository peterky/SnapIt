"""Serialize and load editable annotation sidecars."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from snapit.editor_render import Annotation, annotation_from_dict, annotations_to_dicts

SIDECAR_SUFFIX = ".snapit.json"


def sidecar_path_for(image_path: Path) -> Path:
    return image_path.with_suffix(image_path.suffix + SIDECAR_SUFFIX)


def save_sidecar(
    image_path: Path,
    annotations: list[Annotation],
    base_source: Path | None = None,
) -> Path:
    path = sidecar_path_for(image_path)
    payload: dict[str, Any] = {
        "version": 1,
        "annotations": annotations_to_dicts(annotations),
    }
    if base_source is not None:
        try:
            payload["base_source"] = str(base_source.relative_to(image_path.parent))
        except ValueError:
            payload["base_source"] = str(base_source)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_sidecar(image_path: Path) -> tuple[list[Annotation], Path | None] | None:
    path = sidecar_path_for(image_path)
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    annotations = [annotation_from_dict(item) for item in data.get("annotations", [])]

    base_source: Path | None = None
    raw_base = data.get("base_source")
    if raw_base:
        candidate = Path(raw_base)
        base_source = candidate if candidate.is_absolute() else image_path.parent / candidate

    return annotations, base_source


def resolve_base_image_path(image_path: Path) -> Path:
    loaded = load_sidecar(image_path)
    if loaded is None:
        return image_path

    _annotations, base_source = loaded
    if base_source and base_source.exists():
        return base_source
    return image_path