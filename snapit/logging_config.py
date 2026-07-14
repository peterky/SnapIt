"""File logging for troubleshooting tray/UI issues."""

from __future__ import annotations

import logging
from pathlib import Path

from snapit.config import CONFIG_DIR


def setup_logging() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = CONFIG_DIR / "snapit.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )