"""
Memory Explorer — Filter Bar (Phase 7)

A secondary toolbar providing Search, MediaType Filter, Sort Dropdown,
and the Gallery vs Viewer toggle.
"""

from __future__ import annotations

import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QLabel,
)

logger = logging.getLogger(__name__)


class FilterBar(QWidget):
    """
    Secondary toolbar.
    Emits signals when filters change or view mode is toggled.
    """

    filters_changed = Signal()         # Emitted whenever search/type/sort changes
    view_mode_toggled = Signal(int)   # 0=viewer, 1=gallery, 2=people

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(
            "background: #151515; border-bottom: 1px solid rgba(255, 255, 255, 0.1);"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(12)

        # ── View Toggle ────────────────────────────────────────────────
        self._gallery_btn = QPushButton("▦ Gallery")
        self._gallery_btn.setCheckable(True)
        self._gallery_btn.setChecked(False)

        self._viewer_btn = QPushButton("🖽 Viewer")
        self._viewer_btn.setCheckable(True)
        self._viewer_btn.setChecked(True)

        self._people_btn = QPushButton("🧑 People")
        self._people_btn.setCheckable(True)
        self._people_btn.setChecked(False)

        self._fav_btn = QPushButton("⭐ Favorites")
        self._fav_btn.setCheckable(True)
        self._fav_btn.setChecked(False)

        for btn in (self._gallery_btn, self._viewer_btn, self._people_btn, self._fav_btn):
            btn.setStyleSheet(
                "QPushButton { background: rgba(255, 255, 255, 0.08); color: #8e8e93; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; padding: 4px 10px; font-size: 12px; font-family: -apple-system, 'Segoe UI', sans-serif; }"
                "QPushButton:hover { background: rgba(255, 255, 255, 0.15); color: #e5e5ea; }"
                "QPushButton:checked { background: #0a84ff; color: #fff; font-weight: bold; border-color: #0a84ff; }"
            )
            
        self._gallery_btn.clicked.connect(lambda: self._on_view_changed(1))
        self._viewer_btn.clicked.connect(lambda: self._on_view_changed(0))
        self._people_btn.clicked.connect(lambda: self._on_view_changed(2))
        self._fav_btn.clicked.connect(self._emit_filters_changed)

        # ── Search ─────────────────────────────────────────────────────
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("🔍 Search filename or folder...")
        self._search_box.setFixedWidth(200)
        self._search_box.setStyleSheet(
            "QLineEdit { background: rgba(255, 255, 255, 0.08); color: #fff; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; padding: 4px 8px; font-size: 13px; font-family: -apple-system, 'Segoe UI', sans-serif; }"
            "QLineEdit:focus { border: 1px solid #0a84ff; background: rgba(255, 255, 255, 0.12); }"
        )
        self._search_box.textChanged.connect(self._emit_filters_changed)
        self._search_box.returnPressed.connect(self._search_box.clearFocus)

        # ── Type Filter ────────────────────────────────────────────────
        self._type_combo = QComboBox()
        self._type_combo.addItems(["All Media", "Photos Only", "Videos Only"])
        self._type_combo.setStyleSheet(self._combo_style())
        self._type_combo.currentIndexChanged.connect(self._emit_filters_changed)

        # ── Sort ───────────────────────────────────────────────────────
        sort_lbl = QLabel("Sort:")
        sort_lbl.setStyleSheet("color: #666; font-size: 12px;")

        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Folder/Path", "Filename", "Date (Newest)", "Date (Oldest)"])
        self._sort_combo.setStyleSheet(self._combo_style())
        self._sort_combo.currentIndexChanged.connect(self._emit_filters_changed)

        # ── Layout ─────────────────────────────────────────────────────
        lay.addWidget(self._gallery_btn)
        lay.addWidget(self._viewer_btn)
        lay.addWidget(self._people_btn)
        lay.addSpacing(10)
        lay.addWidget(self._fav_btn)
        
        lay.addSpacing(20)
        lay.addWidget(self._search_box)
        lay.addWidget(self._type_combo)
        
        lay.addStretch()
        lay.addWidget(sort_lbl)
        lay.addWidget(self._sort_combo)

    def _combo_style(self) -> str:
        return (
            "QComboBox { background: rgba(255, 255, 255, 0.08); color: #e5e5ea; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; padding: 3px 8px; font-size: 12px; font-family: -apple-system, 'Segoe UI', sans-serif; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox:focus { border: 1px solid #0a84ff; }"
            "QComboBox QAbstractItemView { background: #1c1c1e; color: #e5e5ea; border: 1px solid rgba(255, 255, 255, 0.1); selection-background-color: #0a84ff; selection-color: #fff; }"
        )

    def _emit_filters_changed(self, *args) -> None:
        self.filters_changed.emit()

    def _on_view_changed(self, mode: int) -> None:
        self._viewer_btn.setChecked(mode == 0)
        self._gallery_btn.setChecked(mode == 1)
        self._people_btn.setChecked(mode == 2)
        self.view_mode_toggled.emit(mode)

    def get_search_text(self) -> str:
        return self._search_box.text().strip().lower()

    def get_type_filter(self) -> str:
        # Returns "all", "image", or "video"
        idx = self._type_combo.currentIndex()
        if idx == 1:
            return "image"
        if idx == 2:
            return "video"
        return "all"

    def get_sort_mode(self) -> str:
        # Returns "path", "name", "newest", "oldest"
        idx = self._sort_combo.currentIndex()
        if idx == 1:
            return "name"
        if idx == 2:
            return "newest"
        if idx == 3:
            return "oldest"
        return "path"

    def get_favorites_only(self) -> bool:
        return self._fav_btn.isChecked()
