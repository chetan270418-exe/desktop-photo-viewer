"""
Memory Explorer — Image Viewer Widget

Displays a single image, scaled to fill the available space while
preserving aspect ratio. Handles every failure mode without crashing:
  - File not found
  - Corrupted / unreadable image
  - Zero-size widget during startup

Only one image is held in memory at a time (the currently-displayed one).
Supports dynamic rotation applied visually via QTransform.
Includes floating year badge, translucent navigation arrows,
and scroll-wheel zoom with drag-to-pan.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPixmap, QTransform, QPainter, QWheelEvent, QMouseEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel

logger = logging.getLogger(__name__)

# Zoom limits
_MIN_ZOOM = 0.1
_MAX_ZOOM = 20.0


class ImageViewer(QWidget):
    """
    Central image display widget with overlay navigation arrows,
    a floating year badge, and mouse-wheel zoom + drag-to-pan.
    """
    navigate_requested = Signal(int)  # +1 = forward, -1 = backward
    map_requested = Signal()          # Emitted when map button clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: #1c1c1e;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: QPixmap | None = None
        self._rotated_pixmap: QPixmap | None = None  # cached after rotation
        self._rotation: int = 0
        self._year_str: str = ""

        # Zoom & Pan state
        self._zoom: float = 1.0
        self._pan_offset: QPointF = QPointF(0, 0)
        self._is_panning: bool = False
        self._last_mouse_pos: QPointF = QPointF(0, 0)
        self._fit_zoom: float = 1.0  # the zoom level that "fits" the image

        # Error / placeholder text
        self._placeholder_text: str = ""

        # Floating year badge (top-right corner)
        self._year_badge = QLabel(self)
        self._year_badge.setStyleSheet(
            "background: rgba(0, 0, 0, 0.55); color: #ffffff; font-size: 22px; font-weight: 700; "
            "border-radius: 10px; padding: 6px 16px; "
            "font-family: -apple-system, 'Segoe UI', sans-serif; "
            "border: 1px solid rgba(255,255,255,0.1);"
        )
        self._year_badge.hide()

        # Zoom indicator badge
        self._zoom_badge = QLabel(self)
        self._zoom_badge.setStyleSheet(
            "background: rgba(0, 0, 0, 0.6); color: #e5e5ea; font-size: 13px; font-weight: 600; "
            "border-radius: 8px; padding: 4px 12px; "
            "font-family: -apple-system, 'Segoe UI', sans-serif; "
            "border: 1px solid rgba(255,255,255,0.08);"
        )
        self._zoom_badge.hide()

        # Map button (floating top right, next to year badge)
        self._map_btn = QPushButton("🗺️", self)
        self._map_btn.setFixedSize(38, 38)
        self._map_btn.setStyleSheet(
            "QPushButton { background: rgba(0, 0, 0, 0.55); color: #ffffff; font-size: 18px; "
            "border-radius: 19px; border: 1px solid rgba(255,255,255,0.1); }"
            "QPushButton:hover { background: rgba(10,132,255,0.6); color: #fff; }"
        )
        self._map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._map_btn.setToolTip("Open in Maps")
        self._map_btn.clicked.connect(self.map_requested.emit)
        self._map_btn.hide()

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: Path, rotation: int = 0, year_str: str = "") -> bool:
        """
        Load and display the image at *path* with the given *rotation*.
        Resets zoom to fit-to-window.
        """
        self._pixmap = None
        self._rotated_pixmap = None
        self._rotation = rotation
        self._year_str = year_str
        self._placeholder_text = ""
        self._has_map = False

        # Reset zoom & pan
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)

        self._year_badge.hide()
        self._map_btn.hide()
        self._zoom_badge.hide()
        self._prev_btn.hide()
        self._next_btn.hide()

        if not path.exists():
            self._placeholder_text = f"⚠  File not found\n\n{path.name}"
            logger.warning("File not found: %s", path)
            self.update()
            return False

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._placeholder_text = f"⚠  Cannot open image\n\n{path.name}\n\n(corrupted or unsupported format)"
            logger.warning("QPixmap returned null for: %s", path)
            self.update()
            return False

        self._pixmap = pixmap
        self._apply_rotation()

        # Show year badge
        if self._year_str:
            self._year_badge.setText(self._year_str)
            self._year_badge.adjustSize()
            self._year_badge.show()

        # Show nav arrows
        self._prev_btn.show()
        self._next_btn.show()

        # Compute fit zoom and set it
        self._compute_fit_zoom()
        self._zoom = self._fit_zoom

        self._position_overlays()
        self.update()
        return True

    def set_has_map(self, has_map: bool) -> None:
        """Show or hide the map button overlay."""
        self._has_map = has_map
        if has_map:
            self._map_btn.show()
        else:
            self._map_btn.hide()
        self._position_overlays()

    def set_rotation(self, rotation: int) -> None:
        """Update rotation (0, 90, 180, 270) and re-render."""
        self._rotation = rotation % 360
        self._apply_rotation()
        self._compute_fit_zoom()
        self._zoom = self._fit_zoom
        self._pan_offset = QPointF(0, 0)
        self.update()

    def clear(self) -> None:
        """Blank the display; releases the held pixmap."""
        self._pixmap = None
        self._rotated_pixmap = None
        self._placeholder_text = ""
        self._year_badge.hide()
        self._map_btn.hide()
        self._zoom_badge.hide()
        self._prev_btn.hide()
        self._next_btn.hide()
        self.update()

    def show_placeholder(self, message: str) -> None:
        """Display an arbitrary text placeholder (used for video entries)."""
        self._pixmap = None
        self._rotated_pixmap = None
        self._placeholder_text = message
        self._year_badge.hide()
        self._map_btn.hide()
        self._zoom_badge.hide()
        self._prev_btn.hide()
        self._next_btn.hide()
        self.update()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_rotation(self) -> None:
        """Pre-compute the rotated pixmap."""
        if self._pixmap is None:
            self._rotated_pixmap = None
            return
        if self._rotation == 0:
            self._rotated_pixmap = self._pixmap
        else:
            transform = QTransform().rotate(self._rotation)
            self._rotated_pixmap = self._pixmap.transformed(
                transform, Qt.TransformationMode.SmoothTransformation
            )

    def _compute_fit_zoom(self) -> None:
        """Calculate the zoom level that fits the image inside the widget."""
        if self._rotated_pixmap is None:
            self._fit_zoom = 1.0
            return
        pw, ph = self._rotated_pixmap.width(), self._rotated_pixmap.height()
        ww, wh = self.width(), self.height()
        if pw < 1 or ph < 1 or ww < 1 or wh < 1:
            self._fit_zoom = 1.0
            return
        self._fit_zoom = min(ww / pw, wh / ph)

    def _position_overlays(self) -> None:
        """Position the year badge, zoom badge, and navigation arrows."""
        w, h = self.width(), self.height()
        pad = 20
        mid_y = h // 2 - 22

        # Year badge — top right
        current_x = w - pad
        if self._year_badge.isVisible():
            current_x -= self._year_badge.width()
            self._year_badge.move(current_x, pad)
            self._year_badge.raise_()
            current_x -= 12 # spacing

        # Map button — left of year badge
        if self._map_btn.isVisible():
            current_x -= self._map_btn.width()
            self._map_btn.move(current_x, pad)
            self._map_btn.raise_()

        # Zoom badge — bottom center
        if self._zoom_badge.isVisible():
            self._zoom_badge.move(
                (w - self._zoom_badge.width()) // 2,
                h - self._zoom_badge.height() - pad
            )
            self._zoom_badge.raise_()

        # Navigation arrows — vertically centered on left/right edges
        if self._prev_btn.isVisible():
            self._prev_btn.move(pad, mid_y)
            self._prev_btn.raise_()
        if self._next_btn.isVisible():
            self._next_btn.move(w - 44 - pad, mid_y)
            self._next_btn.raise_()

    def _update_zoom_badge(self) -> None:
        """Show or hide the zoom percentage badge."""
        pct = round(self._zoom / self._fit_zoom * 100)
        if pct == 100:
            self._zoom_badge.hide()
        else:
            self._zoom_badge.setText(f"{pct}%")
            self._zoom_badge.adjustSize()
            self._zoom_badge.show()
        self._position_overlays()

    # ------------------------------------------------------------------
    # Qt overrides — painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Fill background
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        if self._rotated_pixmap is not None:
            pw = self._rotated_pixmap.width() * self._zoom
            ph = self._rotated_pixmap.height() * self._zoom

            # Center the image + pan offset
            x = (self.width() - pw) / 2 + self._pan_offset.x()
            y = (self.height() - ph) / 2 + self._pan_offset.y()

            target_rect = QRectF(x, y, pw, ph)
            source_rect = QRectF(self._rotated_pixmap.rect())
            painter.drawPixmap(target_rect, self._rotated_pixmap, source_rect)
        elif self._placeholder_text:
            painter.setPen(Qt.GlobalColor.gray)
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder_text)

        painter.end()

    # ------------------------------------------------------------------
    # Qt overrides — events
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._rotated_pixmap is not None:
            old_fit = self._fit_zoom
            self._compute_fit_zoom()
            # If user hadn't zoomed, keep fitting
            if old_fit > 0 and abs(self._zoom - old_fit) < 0.001:
                self._zoom = self._fit_zoom
                self._pan_offset = QPointF(0, 0)
        self._position_overlays()
        self.update()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._compute_fit_zoom()
        self._position_overlays()
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        """Zoom in/out with mouse wheel, centered on the cursor position."""
        if self._rotated_pixmap is None:
            return

        # Get cursor position relative to widget
        cursor_pos = event.position()

        old_zoom = self._zoom
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))

        if new_zoom == old_zoom:
            return

        # Adjust pan so the point under the cursor stays fixed
        # image_point = (cursor - center - pan) / old_zoom
        center = QPointF(self.width() / 2, self.height() / 2)
        image_point = (cursor_pos - center - self._pan_offset) / old_zoom

        self._zoom = new_zoom
        # new_pan = cursor - center - image_point * new_zoom
        self._pan_offset = cursor_pos - center - image_point * new_zoom

        self._update_zoom_badge()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._rotated_pixmap is not None:
            self._is_panning = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._is_panning:
            delta = event.position() - self._last_mouse_pos
            self._pan_offset += delta
            self._last_mouse_pos = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Double-click to reset zoom to fit."""
        if self._rotated_pixmap is not None:
            self._compute_fit_zoom()
            self._zoom = self._fit_zoom
            self._pan_offset = QPointF(0, 0)
            self._update_zoom_badge()
            self.update()
        super().mouseDoubleClickEvent(event)
