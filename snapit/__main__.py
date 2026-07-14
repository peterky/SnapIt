"""Run SnapIt with: python -m snapit"""

import sys

from snapit.app import SnapItApp
from snapit.screen_coords import ensure_dpi_aware
from snapit.single_instance import acquire_single_instance


def main() -> None:
    ensure_dpi_aware()
    if not acquire_single_instance():
        sys.exit(0)
    SnapItApp().run()


if __name__ == "__main__":
    main()