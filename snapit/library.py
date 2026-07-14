"""Snapshot library helpers for browsing saved captures."""

from __future__ import annotations

from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def list_snapshots(
    directory: Path,
    filename_prefix: str | None = None,
    *,
    limit: int = 80,
) -> list[Path]:
    if not directory.exists():
        return []

    matches: list[Path] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if filename_prefix and not path.stem.startswith(filename_prefix):
            continue
        matches.append(path)

    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[:limit]