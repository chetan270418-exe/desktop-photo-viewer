"""
Memory Explorer — People View

Displays a grid of identified people.
"""

import logging
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QBrush, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QListView, QLabel, QHBoxLayout, QPushButton
)
import cv2
import numpy as np

logger = logging.getLogger(__name__)

def _crop_and_circle_face(image_path: str, box: list[int], size: int = 120) -> QPixmap:
    try:
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return QPixmap()
            
        x, y, w, h = box
        # add a small margin
        margin = int(w * 0.2)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img.shape[1], x + w + margin)
        y2 = min(img.shape[0], y + h + margin)
        
        crop = img[y1:y2, x1:x2]
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        
        h_img, w_img, ch = crop_rgb.shape
        bytes_per_line = ch * w_img
        
        from PySide6.QtGui import QImage
        qimg = QImage(crop_rgb.data, w_img, h_img, bytes_per_line, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        
        # Circle crop
        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        
        # Center the pixmap
        dx = (size - pix.width()) // 2
        dy = (size - pix.height()) // 2
        painter.drawPixmap(dx, dy, pix)
        painter.end()
        return out
        
    except Exception as e:
        logger.warning(f"Failed to crop face from {image_path}: {e}")
        return QPixmap()

class PeopleView(QWidget):
    person_selected = Signal(int) # -1 for clear selection

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: #1c1c1e;")
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(20)
        
        # Header
        header_lay = QHBoxLayout()
        title = QLabel("People")
        title.setStyleSheet("color: white; font-size: 24px; font-weight: bold; font-family: -apple-system, sans-serif;")
        header_lay.addWidget(title)
        
        self.clear_btn = QPushButton("Clear Filter")
        self.clear_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.1); color: white; padding: 5px 15px; border-radius: 5px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.2); }"
        )
        self.clear_btn.clicked.connect(self._clear_selection)
        self.clear_btn.hide()
        header_lay.addStretch()
        header_lay.addWidget(self.clear_btn)
        
        lay.addLayout(header_lay)
        
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListView.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_widget.setSpacing(20)
        self.list_widget.setIconSize(QSize(120, 120))
        self.list_widget.setStyleSheet(
            "QListWidget { border: none; background: transparent; }"
            "QListWidget::item { color: white; font-family: -apple-system, sans-serif; font-size: 14px; border-radius: 10px; }"
            "QListWidget::item:selected { background: rgba(10, 132, 255, 0.3); }"
            "QListWidget::item:hover { background: rgba(255, 255, 255, 0.1); }"
        )
        
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self.list_widget)

    def load_people(self, faces_data: dict) -> None:
        self.list_widget.clear()
        
        # Group by person_id
        clusters = {}
        for path, face_list in faces_data.items():
            for face in face_list:
                pid = face.get("person_id", -1)
                if pid == -1:
                    continue
                if pid not in clusters:
                    clusters[pid] = []
                clusters[pid].append((path, face["box"]))
                
        # Sort clusters by size (most frequent first)
        sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
        
        for pid, instances in sorted_clusters:
            # Take the first instance as the representative face
            rep_path, rep_box = instances[0]
            pixmap = _crop_and_circle_face(rep_path, rep_box)
            if pixmap.isNull():
                continue
                
            item = QListWidgetItem()
            from PySide6.QtGui import QIcon
            item.setIcon(QIcon(pixmap))
            item.setText(f"Person {pid}\n({len(instances)} photos)")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self.list_widget.addItem(item)
            
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        self.clear_btn.show()
        self.person_selected.emit(pid)
        
    def _clear_selection(self) -> None:
        self.list_widget.clearSelection()
        self.clear_btn.hide()
        self.person_selected.emit(-1)
