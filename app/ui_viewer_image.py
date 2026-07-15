"""
Memory Explorer — Image Viewer Widget

Displays a single image, scaled to fill the available space while
preserving aspect ratio. Handles every failure mode without crashing:
  - File not found
  - Corrupted / unreadable image
  - Zero-size widget during startup

Only one image is held in memory at a time (the currently-displayed one).
Supports dynamic rotation applied visually via QTransform.
Includes floating year badge and translucent navigation arrows.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget, QVBoxLayout, QPushButton

logger = logging.getLogger(__name__)


class ImageViewer(QWidget):
    """
    Central image display widget with overlay navigation arrows
    and a floating year badge.
    """
    navigate_requested = Signal(int)  # +1 = forward, -1 = backward

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: #1c1c1e;")

        self._pixmap: QPixmap | None = None
        self._rotation: int = 0
        self._year_str: str = ""

        self._label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._label.setWordWrap(True)
        self._label.setStyleSheet("color: #636366; font-size: 14px; background: transparent;")

        # Floating year badge (top-right corner)
        self._year_badge = QLabel(self)
        self._year_badge.setStyleSheet(
            "background: rgba(0, 0, 0, 0.55); color: #ffffff; font-size: 22px; font-weight: 700; "
            "border-radius: 10px; padding: 6px 16px; "
            "font-family: -apple-system, 'Segoe UI', sans-serif; "
            "border: 1px solid rgba(255,255,255,0.1);"
        )
        self._year_badge.hide()

        # Navigation arrow overlays
        arrow_style = (
            "QPushButton { background: rgba(0,0,0,0.35); color: rgba(255,255,255,0.7); "
            "border: none; border-radius: 22px; font-size: 22px; font-weight: bold; "
            "font-family: -apple-system, 'Segoe UI', sans-serif; }"
            "QPushButton:hover { background: rgba(10,132,255,0.6); color: #fff; }"
            "QPushButton:pressed { background: rgba(10,132,255,0.85); }"
        )

        self._prev_btn = QPushButton("‹", self)
        self._prev_btn.setFixedSize(44, 44)
        self._prev_btn.setStyleSheet(arrow_style)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setToolTip("Previous (←)")
        self._prev_btn.clicked.connect(lambda: self.navigate_requested.emit(-1))
        self._prev_btn.hide()

        self._next_btn = QPushButton("›", self)
        self._next_btn.setFixedSize(44, 44)
        self._next_btn.setStyleSheet(arrow_style)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setToolTip("Next (→)")
        self._next_btn.clicked.connect(lambda: self.navigate_requested.emit(+1))
        self._next_btn.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: Path, rotation: int = 0, year_str: str = "") -> bool:
        """
        Load and display the image at *path* with the given *rotation*.
        """
        self._pixmap = None
        self._rotation = rotation
        self._year_str = year_str
        self._label.setStyleSheet(
            "color: #636366; font-size: 14px; background: transparent;"
        )
        self._year_badge.hide()
        self._prev_btn.hide()
        self._next_btn.hide()

        if not path.exists():
            msg = f"⚠  File not found\n\n{path.name}"
            logger.warning("File not found: %s", path)
            self._label.setText(msg)
            return False

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            msg = f"⚠  Cannot open image\n\n{path.name}\n\n(corrupted or unsupported format)"
            logger.warning("QPixmap returned null for: %s", path)
            self._label.setText(msg)
            return False

        self._pixmap = pixmap
        self._label.setText("")

        # Show year badge
        if self._year_str:
            self._year_badge.setText(self._year_str)
            self._year_badge.adjustSize()
            self._year_badge.show()

        # Show nav arrows
        self._prev_btn.show()
        self._next_btn.show()

        self._render()
        self._position_overlays()
        return True

    def set_rotation(self, rotation: int) -> None:
        """Update rotation (0, 90, 180, 270) and re-render."""
        self._rotation = rotation % 360
        self._render()

    def clear(self) -> None:
        """Blank the display; releases the held pixmap."""
        self._pixmap = None
        self._label.clear()
        self._year_badge.hide()
        self._prev_btn.hide()
        self._next_btn.hide()

    def show_placeholder(self, message: str) -> None:
        """Display an arbitrary text placeholder (used for video entries)."""
        self._pixmap = None
        self._year_badge.hide()
        self._prev_btn.hide()
        self._next_btn.hide()
        self._label.setText(message)
        self._label.setStyleSheet(
            "color: #636366; font-size: 16px; background: transparent;"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render(self) -> None:
        """Apply rotation and re-scale the stored pixmap to the current label size."""
        if self._pixmap is None:
            return

        target = self._label.size()
        if target.width() < 1 or target.height() < 1:
            return

        # 1. Rotate the original pixmap
        transform = QTransform().rotate(self._rotation)
        rotated = self._pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)

        # 2. Scale the rotated pixmap to fit the label bounds
        scaled = rotated.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def _position_overlays(self) -> None:
        """Position the year badge and navigation arrows."""
        w, h = self.width(), self.height()
        pad = 20
        mid_y = h // 2 - 22

        # Year badge — top right
        if self._year_badge.isVisible():
            self._year_badge.move(w - self._year_badge.width() - pad, pad)

        # Navigation arrows — vertically centered on left/right edges
        if self._prev_btn.isVisible():
            self._prev_btn.move(pad, mid_y)
            self._prev_btn.raise_()
        if self._next_btn.isVisible():
            self._next_btn.move(w - 44 - pad, mid_y)
            self._next_btn.raise_()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._render()
        self._position_overlays()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._render()
        self._position_overlays()
