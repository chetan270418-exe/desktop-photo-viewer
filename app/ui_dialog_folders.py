"""
Memory Explorer — Folder Management Dialog

A small modal dialog to view, add, and remove root folders.
"""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QLabel,
    QFileDialog,
)


class ManageFoldersDialog(QDialog):
    """
    Dialog for adding and removing multiple root folders.
    After it closes, the caller can inspect self.roots for the updated list.
    """

    def __init__(self, current_roots: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Folders")
        self.resize(500, 350)
        self.setStyleSheet("background: #1c1c1e; color: #e5e5ea; font-family: -apple-system, 'Segoe UI', sans-serif;")

        self.roots: list[str] = list(current_roots)

        lay = QVBoxLayout(self)

        lbl = QLabel("Active Root Folders")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #0a84ff;")
        lay.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.addItems(self.roots)
        self.list_widget.setStyleSheet(
            "QListWidget { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 4px; font-size: 13px; }"
            "QListWidget::item { padding: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }"
            "QListWidget::item:selected { background: #0a84ff; color: #fff; border-radius: 4px; }"
        )
        lay.addWidget(self.list_widget)

        btn_lay = QHBoxLayout()

        add_btn = QPushButton("+ Add Folder")
        add_btn.clicked.connect(self._add_folder)

        self.remove_btn = QPushButton("− Remove Selected")
        self.remove_btn.clicked.connect(self._remove_folder)
        self.remove_btn.setEnabled(False)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        for b in (add_btn, self.remove_btn, close_btn):
            b.setStyleSheet(
                "QPushButton { background: rgba(255, 255, 255, 0.08); color: #e5e5ea; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px 14px; font-size: 13px; }"
                "QPushButton:hover { background: rgba(255, 255, 255, 0.15); }"
                "QPushButton:pressed { background: #0a84ff; color: #fff; border-color: #0a84ff; }"
            )

        btn_lay.addWidget(add_btn)
        btn_lay.addWidget(self.remove_btn)
        btn_lay.addStretch()
        btn_lay.addWidget(close_btn)

        lay.addLayout(btn_lay)

    def _on_selection_changed(self) -> None:
        self.remove_btn.setEnabled(bool(self.list_widget.selectedItems()))

    def _add_folder(self) -> None:
        start_dir = self.roots[-1] if self.roots else str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Select a root folder to scan", start_dir
        )
        if folder:
            path_str = str(Path(folder).resolve())
            if path_str not in self.roots:
                self.roots.append(path_str)
                self.list_widget.addItem(path_str)

    def _remove_folder(self) -> None:
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)
            self.roots.pop(row)
