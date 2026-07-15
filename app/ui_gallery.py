"""
Memory Explorer — Gallery View

A fast, lazy-loading thumbnail grid using QListView and QAbstractListModel.
"""

from __future__ import annotations

from typing import Any
import logging

from PySide6.QtCore import (
    Qt,
    QAbstractListModel,
    QModelIndex,
    QSize,
    Signal,
)
from PySide6.QtGui import QIcon, QColor, QPalette
from PySide6.QtWidgets import QListView

from app.core_thumbnails import ThumbnailManager, THUMB_SIZE

logger = logging.getLogger(__name__)


class MediaListModel(QAbstractListModel):
    """
    Model wrapping the flat `_items` list for QListView.
    Lazy-loads thumbnails using ThumbnailManager.
    """

    def __init__(self, items: list[dict], thumb_manager: ThumbnailManager, parent=None) -> None:
        super().__init__(parent)
        self.items = items
        self.thumb_manager = thumb_manager
        # Track items we've already requested so we don't spam the manager
        self._requested: set[int] = set()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        item = self.items[row]

        if role == Qt.ItemDataRole.DisplayRole:
            return item["filename"]

        if role == Qt.ItemDataRole.DecorationRole:
            # We must return a QIcon. If not cached, we ask for it and return None temporarily.
            path = item["path"]
            
            # Fast-path if it's already in memory cache
            from app.core_thumbnails import _MEM_CACHE
            if path in _MEM_CACHE:
                return _MEM_CACHE[path]
                
            if row not in self._requested:
                self._requested.add(row)
                
                # Callback triggers a dataChanged on this specific row
                def _on_thumb_ready(icon: QIcon) -> None:
                    # Make sure the row hasn't completely shifted/changed
                    # This is naive but works well enough if we clear _requested on layout changes
                    self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

                self.thumb_manager.get_thumbnail_async(path, item["type"], _on_thumb_ready)
            
            # Return a blank transparent icon placeholder while loading
            return QIcon()

        return None


class GalleryView(QListView):
    """
    Thumbnail grid view.
    Emits item_double_clicked(index_int) to jump to the single-item viewer.
    """

    item_double_clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(THUMB_SIZE + 20, THUMB_SIZE + 40))
        self.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self.setSpacing(10)
        self.setWordWrap(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)

        # Style
        self.setStyleSheet(
            "QListView { background: #1c1c1e; border: none; outline: none; }"
            "QListView::item { color: #e5e5ea; border-radius: 8px; padding: 5px; font-size: 11px; }"
            "QListView::item:selected { background: rgba(10, 132, 255, 0.25); color: #fff; border: 1px solid #0a84ff; }"
            "QListView::item:hover { background: rgba(255, 255, 255, 0.06); }"
        )

        # Performance: batch layout to avoid freezing when model has 23k+ items
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(200)

        self.doubleClicked.connect(self._on_double_click)

    def _on_double_click(self, index: QModelIndex) -> None:
        if index.isValid():
            self.item_double_clicked.emit(index.row())

    def update_model(self, items: list[dict], thumb_manager: ThumbnailManager) -> None:
        """Replace the model data entirely."""
        model = MediaListModel(items, thumb_manager, parent=self)
        self.setModel(model)
