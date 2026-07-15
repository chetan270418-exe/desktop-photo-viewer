"""
Memory Explorer — Entry Point

Usage
-----
Launch the desktop GUI (default):
    python main.py

Phase 1 CLI scanner:
    python main.py --scan "C:/path/to/photos" "D:/another/folder"

Options (--scan mode only):
    --images-only    Print only image entries
    --videos-only    Print only video entries
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the project root is always on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# CLI scanner mode  (--scan flag)
# ---------------------------------------------------------------------------

def _run_scan_cli(argv: list[str]) -> None:
    """
    Parse --scan arguments and print discovered media paths to stdout.

    Example output
    --------------
    [IMAGE] D:\\photos\\2023\\beach.jpg
    [VIDEO] D:\\photos\\2023\\clip.mp4
    ...
    Found 12,482 media files (11,900 images, 582 videos)
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="main.py --scan",
        description="Memory Explorer — Phase 1 recursive scanner",
        add_help=True,
    )
    parser.add_argument(
        "folders",
        nargs="+",
        metavar="FOLDER",
        help="Root folder(s) to scan recursively",
    )
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Print only image files",
    )
    parser.add_argument(
        "--videos-only",
        action="store_true",
        help="Print only video files",
    )

    # Strip the '--scan' token before parsing the remainder
    remaining = [a for a in argv if a != "--scan"]
    args = parser.parse_args(remaining)

    logging.basicConfig(
        level=logging.WARNING,          # suppress INFO noise in CLI output
        format="%(levelname)s: %(message)s",
    )

    from app.core_scanner import scan_folders

    items = scan_folders(args.folders)

    # Optional filter
    if args.images_only:
        items = [d for d in items if d["type"] == "image"]
    elif args.videos_only:
        items = [d for d in items if d["type"] == "video"]

    # Print each path with a type tag
    for d in items:
        tag = "IMAGE" if d["type"] == "image" else "VIDEO"
        print(f"[{tag}] {d['path']}")

    # Summary line
    total = len(items)
    images = sum(1 for d in items if d["type"] == "image")
    videos = total - images
    print(f"\nFound {total:,} media files ({images:,} images, {videos:,} videos)")


# ---------------------------------------------------------------------------
# GUI mode  (default)
# ---------------------------------------------------------------------------

def _run_gui() -> None:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from PySide6.QtCore import Qt
    from app.ui_main import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Memory Explorer")
    app.setApplicationVersion("0.1.0")
    app.setFont(QFont("Segoe UI", 10))
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if "--scan" in sys.argv:
        _run_scan_cli(sys.argv[1:])
    else:
        _run_gui()


if __name__ == "__main__":
    main()
