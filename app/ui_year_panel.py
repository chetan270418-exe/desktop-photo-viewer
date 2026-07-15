"""
Year Panel Widget
─────────────────
A vertical sidebar panel that displays year groups extracted from media items.
Designed for the right side of a photo viewer with a macOS-dark aesthetic.
"""

from __future__ import annotations

import datetime
from collections import Counter
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class _YearButton(QWidget):
    """A single clickable year entry showing the year and item count."""

    clicked = Signal()

    def __init__(self, year: int, count: int, label: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._year = year
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)

        # ── layout ──────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(1)

        self._title_label = QLabel(label or str(year))
        self._title_label.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 500; background: transparent;"
        )

        self._count_label = QLabel(self._format_count(count))
        self._count_label.setStyleSheet(
            "color: #636366; font-size: 11px; font-weight: 400; background: transparent;"
        )

        layout.addWidget(self._title_label)
        layout.addWidget(self._count_label)

        self._apply_style()

    # ── public api ──────────────────────────────────────────────

    @property
    def year(self) -> int:
        return self._year

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        if self._selected != value:
            self._selected = value
            self._apply_style()

    # ── events ──────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        if not self._selected:
            self.setStyleSheet(self._base_style(hover=True))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._apply_style()
        super().leaveEvent(event)

    # ── internals ───────────────────────────────────────────────

    @staticmethod
    def _format_count(count: int) -> str:
        if count == 1:
            return "1 photo"
        return f"{count:,} photos"

    def _base_style(self, *, hover: bool = False) -> str:
        if self._selected:
            return (
                "background-color: #0a84ff;"
                "border-radius: 6px;"
            )
        if hover:
            return (
                "background-color: rgba(255, 255, 255, 0.08);"
                "border-radius: 6px;"
            )
        return "background: transparent; border-radius: 6px;"

    def _apply_style(self) -> None:
        self.setStyleSheet(self._base_style())
        # Update label colours for selected state
        title_color = "#ffffff"
        count_color = "#ffffff" if self._selected else "#636366"
        self._title_label.setStyleSheet(
            f"color: {title_color}; font-size: 13px; font-weight: 500; background: transparent;"
        )
        self._count_label.setStyleSheet(
            f"color: {count_color}; font-size: 11px; font-weight: 400; background: transparent;"
        )


class YearPanel(QWidget):
    """
    Vertical sidebar panel that groups media items by year.

    Signals
    -------
    year_selected(int)
        Emitted when the user clicks a year button.
        ``0`` means *All Years*; otherwise the value is the four-digit year.
    """

    year_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_year: int = 0
        self._buttons: list[_YearButton] = []

        self.setFixedWidth(160)
        self.setStyleSheet(
            "QWidget#YearPanel {"
            "  background-color: #161616;"
            "  border-left: 1px solid rgba(255, 255, 255, 0.08);"
            "}"
        )
        self.setObjectName("YearPanel")

        self._build_ui()

    # ── public api ──────────────────────────────────────────────

    def update_years(self, items: list[dict]) -> None:
        """
        Extract unique years from *items* and rebuild the button list.

        Each item is expected to carry an ``mtime`` key whose value is a
        Unix timestamp (``int`` or ``float``).
        """
        year_counts = self._extract_year_counts(items)
        total = sum(year_counts.values())
        self._rebuild_buttons(year_counts, total)

    def select_year(self, year: int) -> None:
        """Programmatically select a year (0 = All Years)."""
        self._selected_year = year
        for btn in self._buttons:
            btn.selected = (btn.year == year)

    @property
    def selected_year(self) -> int:
        return self._selected_year

    # ── ui construction ─────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── header ──────────────────────────────────────────────
        header = QLabel("TIMELINE")
        header.setStyleSheet(
            "color: #636366;"
            "font-size: 10px;"
            "font-weight: 600;"
            "font-variant: small-caps;"
            "letter-spacing: 1.2px;"
            "padding: 14px 12px 6px 12px;"
            "background: transparent;"
        )
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(header)

        # ── scroll area ─────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  background: transparent;"
            "  width: 4px;"
            "  margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255, 255, 255, 0.15);"
            "  min-height: 24px;"
            "  border-radius: 2px;"
            "}"
            "QScrollBar::add-line:vertical,"
            "QScrollBar::sub-line:vertical {"
            "  height: 0; background: none;"
            "}"
            "QScrollBar::add-page:vertical,"
            "QScrollBar::sub-page:vertical {"
            "  background: none;"
            "}"
        )

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(4, 0, 4, 8)
        self._scroll_layout.setSpacing(2)
        self._scroll_layout.addStretch()

        scroll.setWidget(self._scroll_content)
        outer.addWidget(scroll)

        # Global font family
        self.setStyleSheet(
            self.styleSheet()
            + "\n* { font-family: -apple-system, 'Segoe UI', sans-serif; }"
        )

    # ── internals ───────────────────────────────────────────────

    @staticmethod
    def _extract_year_counts(items: list[dict]) -> dict[int, int]:
        """Return ``{year: count}`` from a list of media dicts."""
        counter: Counter[int] = Counter()
        for item in items:
            mtime = item.get("mtime")
            if mtime is None:
                continue
            try:
                year = datetime.datetime.fromtimestamp(float(mtime)).year
                counter[year] += 1
            except (OSError, ValueError, OverflowError):
                continue
        return dict(counter)

    def _rebuild_buttons(self, year_counts: dict[int, int], total: int) -> None:
        """Clear existing buttons and create new ones."""
        # Remove old buttons
        for btn in self._buttons:
            btn.setParent(None)
            btn.deleteLater()
        self._buttons.clear()

        # Remove the trailing stretch
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            # Stretch items have no widget
            if item.widget():
                item.widget().setParent(None)

        # ── 'All Years' button ──────────────────────────────────
        all_btn = _YearButton(year=0, count=total, label="All Years")
        all_btn.clicked.connect(lambda: self._on_year_clicked(0))
        self._scroll_layout.addWidget(all_btn)
        self._buttons.append(all_btn)

        # ── Per-year buttons (newest first) ─────────────────────
        for year in sorted(year_counts, reverse=True):
            btn = _YearButton(year=year, count=year_counts[year])
            btn.clicked.connect(lambda y=year: self._on_year_clicked(y))
            self._scroll_layout.addWidget(btn)
            self._buttons.append(btn)

        self._scroll_layout.addStretch()

        # Restore selection highlight
        self.select_year(self._selected_year)

    def _on_year_clicked(self, year: int) -> None:
        self.select_year(year)
        self.year_selected.emit(year)
