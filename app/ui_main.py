"""
Memory Explorer — Main Window (v1.0)

Phase coverage
--------------
Phase 1 : Scanner + CLI              (app/scanner.py)
Phase 2 : Image viewer + navigation  (app/image_viewer.py)
Phase 3 : Video playback             (app/video_player.py)
Phase 4 : Folder picker dialog       (app/manage_folders_dialog.py)
Phase 5 : settings.json persistence  (app/models.py)
Phase 6 : Gallery View               (app/gallery_view.py, app/thumbnail_worker.py)
Phase 7 : Search & Filters           (app/filter_bar.py)
Phase 8 : Performance (Background scanning progress, lazy loading)
Phase 9 : Safety & Deletion          (send2trash integration)

Navigation rules
----------------
* Right / Left Arrow          → ±1 item  (clamped at both ends)
* Shift + Right / Left Arrow  → ±10 items (clamped)
* Space                        → play / pause current video
* F / F11                      → toggle fullscreen
* Esc                          → exit fullscreen
* Delete                       → send current item to trash
* R / Shift+R                  → rotate image right/left
"""

from __future__ import annotations

import logging
import shutil
import webbrowser
from pathlib import Path
from datetime import datetime
import send2trash

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QKeyEvent, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QFileDialog,
)

from app.ui_viewer_image import ImageViewer
from app.core_scanner import scan_folders
from app.ui_viewer_video import VideoPlayer
from app.core_models import load_settings, save_settings, Settings, load_scan_cache, save_scan_cache, APP_DIR, load_faces, save_faces
from app.ui_dialog_folders import ManageFoldersDialog
from app.ui_filter_bar import FilterBar
from app.ui_gallery import GalleryView
from app.core_thumbnails import ThumbnailManager, _MEM_CACHE
from app.ui_year_panel import YearPanel
from app.ui_people_view import PeopleView
from app.core_ml_faces import FaceAnalyzer, cluster_embeddings

logger = logging.getLogger(__name__)

_PAGE_VIEWER = 0
_PAGE_GALLERY = 1
_PAGE_PEOPLE = 2


# ---------------------------------------------------------------------------
# Shared stylesheet tokens (Premium Dark Theme)
# ---------------------------------------------------------------------------

_BTN_STYLE = """
    QPushButton {
        background: rgba(255, 255, 255, 0.08);
        color: #e5e5ea;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        font-size: 13px;
        padding: 5px 14px;
        font-family: -apple-system, 'Segoe UI', sans-serif;
    }
    QPushButton:hover   { background: rgba(255, 255, 255, 0.15); border-color: rgba(255, 255, 255, 0.2); }
    QPushButton:pressed { background: #0a84ff; color: #fff; border-color: #0a84ff; }
"""

_COUNTER_STYLE = """
    QLabel {
        color: #ffffff;
        font-size: 13px;
        font-family: -apple-system, 'Segoe UI', sans-serif;
        background: rgba(10, 132, 255, 0.2);
        border: 1px solid rgba(10, 132, 255, 0.3);
        border-radius: 6px;
        padding: 4px 12px;
        font-weight: 500;
    }
"""

_TYPE_BADGE_IMAGE = (
    "color:#0a84ff; font-size:11px; font-weight:700; "
    "background:rgba(10,132,255,0.12); border-radius:4px; "
    "padding:2px 7px; font-family:-apple-system, 'Segoe UI', sans-serif;"
)
_TYPE_BADGE_VIDEO = (
    "color:#ff9f0a; font-size:11px; font-weight:700; "
    "background:rgba(255,159,10,0.12); border-radius:4px; "
    "padding:2px 7px; font-family:-apple-system, 'Segoe UI', sans-serif;"
)


# ---------------------------------------------------------------------------
# Background scanner worker
# ---------------------------------------------------------------------------

class _ScanWorker(QObject):
    finished = Signal(list)
    error    = Signal(str)
    progress = Signal(int)

    def __init__(self, roots: list[str]) -> None:
        super().__init__()
        self._roots_str = roots

    def run(self) -> None:
        try:
            # Emit progress periodically from scanner.py
            items = scan_folders(self._roots_str, progress_cb=self.progress.emit)
            self.finished.emit(items)
        except Exception as exc:
            logger.exception("Background scan failed")
            self.error.emit(str(exc))


class _FaceWorker(QObject):
    progress = Signal(int, int) # current, total
    finished = Signal(dict)
    
    def __init__(self, items: list[dict], current_faces: dict) -> None:
        super().__init__()
        self.items = items
        self.faces = current_faces
        
    def run(self) -> None:
        try:
            analyzer = FaceAnalyzer()
            analyzer._initialize()
            
            image_items = [d for d in self.items if d["type"] == "image"]
            total = len(image_items)
            
            for i, d in enumerate(image_items):
                path = d["path"]
                if path not in self.faces:
                    try:
                        extracted = analyzer.extract_faces(path)
                        if extracted:
                            self.faces[path] = extracted
                    except Exception as exc:
                        logger.warning(f"Skipping {path} — face extraction failed: {exc}")
                self.progress.emit(i, total)
                
            # Cluster embeddings
            all_emb = []
            face_refs = []
            for path, flist in self.faces.items():
                for f in flist:
                    if "embedding" in f:
                        all_emb.append(f["embedding"])
                        face_refs.append(f)
                    
            if all_emb:
                clusters = cluster_embeddings(all_emb)
                # DBSCAN labels faces that don't match anyone closely enough
                # as noise (-1). Rather than discarding those people entirely,
                # give each one its own person_id so solo/rare faces still
                # show up in the People view as a "singleton" of one photo.
                next_singleton_id = max([c for c in clusters if c != -1], default=-1) + 1
                for f, cid in zip(face_refs, clusters):
                    if cid == -1:
                        f["person_id"] = next_singleton_id
                        next_singleton_id += 1
                    else:
                        f["person_id"] = cid
                    
            self.finished.emit(self.faces)
        except Exception as e:
            logger.exception(f"Face worker failed: {e}")
            self.finished.emit(self.faces)


# ---------------------------------------------------------------------------
# Welcome page
# ---------------------------------------------------------------------------

class _WelcomePage(QWidget):
    manage_folders_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: #1c1c1e;")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(20)

        lbl_icon = QLabel("📷")
        lbl_icon.setStyleSheet("font-size: 72px; background: transparent;")

        lbl_title = QLabel("Memory Explorer")
        lbl_title.setStyleSheet("color: #ffffff; font-size: 32px; font-weight: 600; background: transparent; font-family: -apple-system, 'Segoe UI', sans-serif;")

        lbl_sub = QLabel("No folders added yet — click Folders to get started.")
        lbl_sub.setStyleSheet("color: #636366; font-size: 14px; background: transparent; font-family: -apple-system, 'Segoe UI', sans-serif;")

        btn = QPushButton("Manage Folders")
        btn.setStyleSheet(_BTN_STYLE)
        btn.setFixedWidth(180)
        btn.setFixedHeight(40)
        btn.clicked.connect(self.manage_folders_requested)

        for w in (lbl_icon, lbl_title, lbl_sub, btn):
            if isinstance(w, QLabel):
                w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Memory Explorer")
        self.resize(1280, 820)
        self.setMinimumSize(800, 600)
        self.setStyleSheet("background-color: #1c1c1e;")

        self._settings: Settings = load_settings()
        self._master_items: list[dict] = []
        self._items: list[dict] = []
        self._index: int = 0
        self._scan_thread: QThread | None = None
        self._current_type: str = ""   # "" | "image" | "video"
        self._selected_year: int = 0    # 0 = all years
        self._selected_person: int = -1
        self._faces: dict = load_faces()

        self._thumb_manager = ThumbnailManager(self._settings.rotations, parent=self)

        icon_path = APP_DIR / "image.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.setInterval(4000)
        self._slideshow_timer.timeout.connect(lambda: self._navigate(+1))

        self._build_ui()

        if self._settings.root_folders:
            self._start_scan()
        else:
            self._page_stack.setCurrentIndex(0)

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # 1. Top Bar
        self._top_bar = self._make_top_bar()
        root_lay.addWidget(self._top_bar)

        # 2. Filter Bar (Phase 7)
        self._filter_bar = FilterBar()
        self._filter_bar.filters_changed.connect(self._apply_filters)
        self._filter_bar.view_mode_toggled.connect(self._on_view_mode_toggled)
        # Install event filter on search box so arrow keys still navigate
        self._filter_bar._search_box.installEventFilter(self)
        root_lay.addWidget(self._filter_bar)

        # 3. Main Stack (Welcome | Content)
        self._page_stack = QStackedWidget()
        root_lay.addWidget(self._page_stack)

        # 3a. Welcome Page
        self._welcome_page = _WelcomePage()
        self._welcome_page.manage_folders_requested.connect(self._on_manage_folders)
        self._page_stack.addWidget(self._welcome_page)

        # 3b. Content Area
        content_container = QWidget()
        content_container.setStyleSheet("background:#1c1c1e;")
        cc_lay = QVBoxLayout(content_container)
        cc_lay.setContentsMargins(0, 0, 0, 0)
        cc_lay.setSpacing(0)

        # Inner stack: Single Viewer | Gallery Grid
        self._view_stack = QStackedWidget()
        
        # Viewer container
        viewer_widget = QWidget()
        vw_lay = QVBoxLayout(viewer_widget)
        vw_lay.setContentsMargins(0,0,0,0)
        vw_lay.setSpacing(0)
        self._media_stack = QStackedWidget()
        self._image_viewer = ImageViewer()
        self._image_viewer.navigate_requested.connect(self._navigate)
        self._image_viewer.map_requested.connect(self._open_map)
        self._video_player = VideoPlayer()
        self._media_stack.addWidget(self._image_viewer)
        self._media_stack.addWidget(self._video_player)
        vw_lay.addWidget(self._media_stack)
        
        self._view_stack.addWidget(viewer_widget)    # index 0

        # Gallery container
        self._gallery_view = GalleryView()
        self._gallery_view.item_double_clicked.connect(self._on_gallery_double_clicked)
        self._view_stack.addWidget(self._gallery_view) # index 1

        # People container
        self._people_view = PeopleView()
        self._people_view.person_selected.connect(self._on_person_selected)
        self._view_stack.addWidget(self._people_view) # index 2
        self._people_view.load_people(self._faces)
        
        # Horizontal layout: view_stack + year panel
        content_h = QHBoxLayout()
        content_h.setContentsMargins(0, 0, 0, 0)
        content_h.setSpacing(0)
        content_h.addWidget(self._view_stack, stretch=1)

        # Year panel (right side)
        self._year_panel = YearPanel()
        self._year_panel.year_selected.connect(self._on_year_selected)
        content_h.addWidget(self._year_panel)

        cc_lay.addLayout(content_h, stretch=1)

        # Info bar (only visible when in Single Viewer mode, or we can leave it at the very bottom)
        self._info_bar = self._make_info_bar()
        cc_lay.addWidget(self._info_bar)

        self._page_stack.addWidget(content_container)

        # 4. Progress bar (Phase 8)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # Indeterminate initially
        self._progress.setMaximumHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0a84ff, stop:1 #30d158); }"
        )
        self._progress.hide()
        root_lay.addWidget(self._progress)

        # 5. Status bar
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        sb.setStyleSheet("QStatusBar { background: #111; border-top: 1px solid rgba(255,255,255,0.07); }")
        self.setStatusBar(sb)
        self._status_label = QLabel("No folders added yet.")
        self._status_label.setStyleSheet("color: #636366; font-size: 12px; font-family: -apple-system, 'Segoe UI', sans-serif;")
        sb.addPermanentWidget(self._status_label, 1)

    def _make_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            "background: #111111;"
            "border-bottom: 1px solid rgba(255, 255, 255, 0.08);"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(16)

        title = QLabel("📷  Memory Explorer")
        title.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 600; background: transparent; font-family: -apple-system, 'Segoe UI', sans-serif; letter-spacing: 0.3px;"
        )

        hint = QLabel(
            "← → navigate  ·  Space play  ·  F fullscreen  ·  Del delete  ·  R rotate"
        )
        hint.setStyleSheet("color: #48484a; font-size: 11px; background: transparent; font-family: -apple-system, 'Segoe UI', sans-serif;")

        self._counter_lbl = QLabel("")
        self._counter_lbl.setStyleSheet(_COUNTER_STYLE)
        self._counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._play_slideshow_btn = QPushButton("▶  Slideshow")
        self._play_slideshow_btn.setStyleSheet(_BTN_STYLE)
        self._play_slideshow_btn.setToolTip("Auto-play photos (4s interval)")
        self._play_slideshow_btn.clicked.connect(self._toggle_slideshow)
        self._play_slideshow_btn.setCheckable(True)

        self._scan_faces_btn = QPushButton("🤖 Scan Faces")
        self._scan_faces_btn.setStyleSheet(_BTN_STYLE)
        self._scan_faces_btn.setToolTip("Analyze photos to group by people")
        self._scan_faces_btn.clicked.connect(self._start_face_scan)

        rescan_btn = QPushButton("↻  Rescan")
        rescan_btn.setStyleSheet(_BTN_STYLE)
        rescan_btn.setToolTip("Re-scan all folders for new files")
        rescan_btn.clicked.connect(lambda checked=False: self._start_scan(force=True))

        manage_btn = QPushButton("⊞  Folders")
        manage_btn.setStyleSheet(_BTN_STYLE)
        manage_btn.setToolTip("Add or remove root folders")
        manage_btn.clicked.connect(self._on_manage_folders)

        lay.addWidget(title)
        lay.addSpacing(20)
        lay.addWidget(hint)
        lay.addStretch()
        lay.addWidget(self._counter_lbl)
        lay.addWidget(self._play_slideshow_btn)
        lay.addWidget(self._scan_faces_btn)
        lay.addWidget(rescan_btn)
        lay.addWidget(manage_btn)
        return bar

    def _make_info_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet("background: #151515; border-top: 1px solid rgba(255, 255, 255, 0.1);")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)

        self._type_badge = QLabel("")
        self._type_badge.setStyleSheet(_TYPE_BADGE_IMAGE)
        self._type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._date_lbl = QLabel("")
        self._date_lbl.setStyleSheet("color: #0a84ff; font-size: 12px; font-family: -apple-system, 'Segoe UI', sans-serif; font-weight: 500; background: transparent;")

        self._filename_lbl = QLabel("")
        self._filename_lbl.setStyleSheet("color: #e5e5ea; font-size: 13px; font-family: -apple-system, 'Segoe UI', sans-serif; background: transparent;")

        # Actions inside info bar for visibility
        self._rot_l_btn = QPushButton("↺")
        self._rot_r_btn = QPushButton("↻")
        self._export_btn = QPushButton("📤")
        self._fav_btn = QPushButton("⭐")
        self._del_btn = QPushButton("🗑")
        
        for b in (self._rot_l_btn, self._rot_r_btn, self._export_btn, self._fav_btn, self._del_btn):
            b.setFixedSize(28, 28)
            b.setStyleSheet("QPushButton { background: transparent; color: #8e8e93; border: none; font-size: 16px; border-radius: 4px; } QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }")
            
        self._rot_l_btn.setToolTip("Rotate Left (Shift+R)")
        self._rot_r_btn.setToolTip("Rotate Right (R)")
        self._export_btn.setToolTip("Export a copy")
        self._fav_btn.setToolTip("Toggle Favorite")
        self._del_btn.setToolTip("Delete (Del)")
            
        self._rot_l_btn.clicked.connect(lambda: self._rotate_current(False))
        self._rot_r_btn.clicked.connect(lambda: self._rotate_current(True))
        self._export_btn.clicked.connect(self._export_current)
        self._fav_btn.clicked.connect(self._toggle_favorite)
        self._del_btn.clicked.connect(self._delete_current)
        self._del_btn.setStyleSheet(self._del_btn.styleSheet() + "QPushButton:hover { background: rgba(255, 69, 58, 0.2); color: #ff453a; }")

        self._folder_lbl = QLabel("")
        self._folder_lbl.setStyleSheet("color: #636366; font-size: 11px; font-family: -apple-system, 'Segoe UI', sans-serif; background: transparent;")
        self._folder_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        lay.addWidget(self._type_badge)
        lay.addWidget(self._date_lbl)
        lay.addWidget(self._filename_lbl)
        lay.addWidget(self._rot_l_btn)
        lay.addWidget(self._rot_r_btn)
        lay.addWidget(self._export_btn)
        lay.addWidget(self._fav_btn)
        lay.addWidget(self._del_btn)
        lay.addStretch()
        lay.addWidget(self._folder_lbl)
        return bar

    # ==================================================================
    # Scanning & Filtering
    # ==================================================================

    def _start_scan(self, force: bool = False) -> None:
        if not self._settings.root_folders:
            self._release_current()
            self._master_items = []
            self._apply_filters()
            self._page_stack.setCurrentIndex(0)
            self._status_label.setText("No folders added yet.")
            self._counter_lbl.setText("")
            return
            
        if not force:
            cached = load_scan_cache()
            if cached is not None:
                self._on_scan_finished(cached, save_cache=False)
                return

        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait()

        self._progress.setRange(0, 0) # Indeterminate initially
        self._progress.show()
        self._status_label.setText(f"Scanning {len(self._settings.root_folders)} folder(s)…")

        self._scan_thread = QThread(self)
        self._worker = _ScanWorker(self._settings.root_folders)
        self._worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        
        self._worker.finished.connect(self._scan_thread.quit)
        self._worker.error.connect(self._scan_thread.quit)
        self._scan_thread.start()

    def _on_scan_progress(self, count: int) -> None:
        self._status_label.setText(f"Scanning... found {count:,} media files so far.")

    def _on_scan_finished(self, items: list, save_cache: bool = True) -> None:
        if save_cache:
            save_scan_cache(items)
        self._progress.hide()
        self._master_items = items
        self._year_panel.update_years(items)
        self._apply_filters()
        self._page_stack.setCurrentIndex(1 if self._items else 0)

    def _on_scan_error(self, msg: str) -> None:
        self._progress.hide()
        self._status_label.setText(f"Scan error: {msg}")
        logger.error("Scan error: %s", msg)

    def _apply_filters(self) -> None:
        """Filter and sort _master_items into _items based on FilterBar state."""
        search = self._filter_bar.get_search_text()
        m_type = self._filter_bar.get_type_filter()
        sort_m = self._filter_bar.get_sort_mode()

        filtered = []
        for d in self._master_items:
            if m_type != "all" and d["type"] != m_type:
                continue
            if search:
                if search not in d["filename"].lower() and search not in d["path"].lower():
                    continue

            # Favorites filter
            if self._filter_bar.get_favorites_only():
                if d["path"].lower() not in (f.lower() for f in self._settings.favorites):
                    continue

            # Year filter
            if self._selected_year != 0:
                from datetime import datetime as _dt
                item_year = _dt.fromtimestamp(d["mtime"]).year
                if item_year != self._selected_year:
                    continue

            # Person filter
            if self._selected_person != -1:
                path = d["path"]
                if path not in self._faces:
                    continue
                found = False
                for face in self._faces[path]:
                    if face.get("person_id") == self._selected_person:
                        found = True
                        break
                if not found:
                    continue

            filtered.append(d)

        if sort_m == "name":
            filtered.sort(key=lambda d: d["filename"].lower())
        elif sort_m == "newest":
            filtered.sort(key=lambda d: d["mtime"], reverse=True)
        elif sort_m == "oldest":
            filtered.sort(key=lambda d: d["mtime"])
        else: # path
            filtered.sort(key=lambda d: d["path"].lower())

        current_path = self._items[self._index]["path"] if self._items and self._index < len(self._items) else None
        
        self._items = filtered
        
        total = len(self._master_items)
        images = sum(1 for d in self._items if d["type"] == "image")
        videos = len(self._items) - images
        self._status_label.setText(f"Showing {len(self._items):,} of {total:,} files — {images:,} photos, {videos:,} videos")

        self._gallery_view.update_model(self._items, self._thumb_manager)

        # Restore index if possible
        new_index = min(self._index, max(0, len(self._items) - 1))
        if current_path:
            for i, d in enumerate(self._items):
                if d["path"] == current_path:
                    new_index = i
                    break
                    
        self._index = new_index
        if self._items:
            self._show_current()
        else:
            self._release_current()
            self._counter_lbl.setText("0 / 0")
            self._filename_lbl.setText("No results")
            self._date_lbl.setText("")
            self.setWindowTitle("Memory Explorer")

    # ==================================================================
    # Actions (Delete, Rotate, Mode Toggle, Year Selection)
    # ==================================================================

    def _on_year_selected(self, year: int) -> None:
        """Filter media to show only items from the selected year."""
        self._selected_year = year
        self._apply_filters()

    def _on_view_mode_toggled(self, mode: int) -> None:
        self._release_current()
        if mode == 1:
            self._view_stack.setCurrentIndex(_PAGE_GALLERY)
            if self._items:
                idx = self._gallery_view.model().index(self._index, 0)
                self._gallery_view.setCurrentIndex(idx)
                self._gallery_view.scrollTo(idx)
            self._info_bar.hide()
        elif mode == 2:
            self._view_stack.setCurrentIndex(_PAGE_PEOPLE)
            self._info_bar.hide()
        else:
            self._view_stack.setCurrentIndex(_PAGE_VIEWER)
            self._info_bar.show()
            self._show_current()

    def _on_person_selected(self, pid: int) -> None:
        self._selected_person = pid
        self._apply_filters()
        # Switch to gallery view when filtering by person
        if pid != -1:
            self._filter_bar._gallery_btn.click()

    def _on_gallery_double_clicked(self, row: int) -> None:
        self._index = row
        # Switch back to viewer
        self._filter_bar._viewer_btn.click() # This fires _on_view_mode_toggled

    def _delete_current(self) -> None:
        if not self._items:
            return
        
        # If in gallery, delete selected
        if self._view_stack.currentIndex() == _PAGE_GALLERY:
            sel = self._gallery_view.selectedIndexes()
            if not sel: return
            self._index = sel[0].row()

        d = self._items[self._index]
        path_str = d["path"]
        
        reply = QMessageBox.question(
            self, "Send to Trash",
            f"Are you sure you want to delete this file?\n\n{d['filename']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._release_current()
        
        try:
            send2trash.send2trash(path_str)
            logger.info("Sent to trash: %s", path_str)
        except Exception as e:
            logger.error("Failed to delete %s: %s", path_str, e)
            QMessageBox.critical(self, "Error", f"Failed to delete file:\n{e}")
            self._show_current() # restore
            return

        # Purge from cache
        if path_str in _MEM_CACHE:
            del _MEM_CACHE[path_str]

        # Remove from master list and reapply filters
        self._master_items = [item for item in self._master_items if item["path"] != path_str]
        
        # If we were at the end, shift index back
        if self._index >= len(self._items) - 1:
            self._index = max(0, self._index - 1)
            
        self._apply_filters()
        
        if self._view_stack.currentIndex() == _PAGE_GALLERY and self._items:
            idx = self._gallery_view.model().index(self._index, 0)
            self._gallery_view.setCurrentIndex(idx)

    def _toggle_slideshow(self) -> None:
        if self._play_slideshow_btn.isChecked():
            self._slideshow_timer.start()
            self._play_slideshow_btn.setText("⏸  Pause")
            # If at the end, wrap to beginning
            if self._index >= len(self._items) - 1:
                self._index = -1
        else:
            self._slideshow_timer.stop()
            self._play_slideshow_btn.setText("▶  Slideshow")

    def _export_current(self) -> None:
        if not self._items:
            return
        d = self._items[self._index]
        path_str = d["path"]
        
        dest_dir = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not dest_dir:
            return
            
        try:
            shutil.copy2(path_str, dest_dir)
            logger.info("Exported %s to %s", path_str, dest_dir)
            QMessageBox.information(self, "Export Successful", f"File exported to:\n{dest_dir}")
        except Exception as e:
            logger.error("Export failed: %s", e)
            QMessageBox.critical(self, "Export Failed", f"Failed to export file:\n{e}")

    def _toggle_favorite(self) -> None:
        if not self._items:
            return
        d = self._items[self._index]
        path_str = d["path"]
        
        # Check case-insensitively
        is_fav = any(f.lower() == path_str.lower() for f in self._settings.favorites)
        
        if is_fav:
            # Remove all matches (in case of weird casing dupes)
            to_remove = [f for f in self._settings.favorites if f.lower() == path_str.lower()]
            for f in to_remove:
                self._settings.favorites.remove(f)
            self._fav_btn.setText("☆")
            self._fav_btn.setStyleSheet(self._fav_btn.styleSheet().replace("color: #ffcc00;", "color: #8e8e93;"))
        else:
            self._settings.favorites.add(path_str)
            self._fav_btn.setText("⭐")
            self._fav_btn.setStyleSheet(self._fav_btn.styleSheet().replace("color: #8e8e93;", "color: #ffcc00;"))
            
        save_settings(self._settings)

    def _open_map(self) -> None:
        if not self._items:
            return
        d = self._items[self._index]
        lat = d.get("lat", 0.0)
        lon = d.get("lon", 0.0)
        if lat != 0.0 or lon != 0.0:
            url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            webbrowser.open(url)

    def _start_face_scan(self) -> None:
        if not self._master_items:
            return
            
        self._scan_faces_btn.setEnabled(False)
        self._scan_faces_btn.setText("Scanning...")
        
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.show()
        
        self._face_thread = QThread(self)
        self._face_worker = _FaceWorker(self._master_items, self._faces)
        self._face_worker.moveToThread(self._face_thread)
        self._face_thread.started.connect(self._face_worker.run)
        self._face_worker.progress.connect(self._on_face_scan_progress)
        self._face_worker.finished.connect(self._on_face_scan_finished)
        self._face_worker.finished.connect(self._face_thread.quit)
        self._face_worker.finished.connect(self._face_worker.deleteLater)
        self._face_thread.finished.connect(self._face_thread.deleteLater)
        self._face_thread.start()
        
    def _on_face_scan_progress(self, current: int, total: int) -> None:
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        self._status_label.setText(f"Scanning faces: {current}/{total}")
        
    def _on_face_scan_finished(self, faces: dict) -> None:
        self._scan_faces_btn.setEnabled(True)
        self._scan_faces_btn.setText("🤖 Scan Faces")
        self._progress.hide()
        
        self._faces = faces
        save_faces(self._faces)
        self._people_view.load_people(self._faces)
        self._view_stack.setCurrentIndex(_PAGE_PEOPLE)
        self._apply_filters()
        self._status_label.setText(f"Face scan complete. Found {len(faces)} images with faces.")

    def _rotate_current(self, clockwise: bool = True) -> None:
        if not self._items or self._current_type != "image":
            return
            
        # Get selected item based on active view
        idx = self._index
        if self._view_stack.currentIndex() == _PAGE_GALLERY:
            sel = self._gallery_view.selectedIndexes()
            if not sel: return
            idx = sel[0].row()

        path_str = self._items[idx]["path"]
        
        # Find existing rotation case-insensitively
        cur_rot = 0
        rot_key = path_str
        for k, v in self._settings.rotations.items():
            if k.lower() == path_str.lower():
                cur_rot = v
                rot_key = k
                break
                
        delta = 90 if clockwise else -90
        new_rot = (cur_rot + delta) % 360
        
        if new_rot == 0:
            self._settings.rotations.pop(rot_key, None)
        else:
            self._settings.rotations[path_str] = new_rot
        save_settings(self._settings)

        # Drop from cache so thumbnail regenerates next time it's seen
        if path_str in _MEM_CACHE:
            del _MEM_CACHE[path_str]

        # Visual update if in viewer
        if self._view_stack.currentIndex() == _PAGE_VIEWER and idx == self._index:
            self._image_viewer.set_rotation(new_rot)
            
        # If in gallery, trigger dataChanged for the row to reload thumbnail
        if self._view_stack.currentIndex() == _PAGE_GALLERY:
            model = self._gallery_view.model()
            qidx = model.index(idx, 0)
            if hasattr(model, "_requested") and idx in model._requested:
                model._requested.remove(idx)
            model.dataChanged.emit(qidx, qidx, [Qt.ItemDataRole.DecorationRole])

    # ==================================================================
    # Display & Navigation
    # ==================================================================

    def _release_current(self) -> None:
        if self._current_type == "image":
            self._image_viewer.clear()
        elif self._current_type == "video":
            self._video_player.release()
        self._current_type = ""

    def _show_current(self) -> None:
        if not self._items:
            return

        d = self._items[self._index]
        total = len(self._items)

        self._release_current()
        self._current_type = d["type"]

        self._counter_lbl.setText(f"{self._index + 1:,} / {total:,}")
        self._filename_lbl.setText(d["filename"])
        
        dt = datetime.fromtimestamp(d["mtime"])
        self._date_lbl.setText(dt.strftime("%Y-%m-%d"))

        parent_str = str(Path(d["path"]).parent)
        if len(parent_str) > 70:
            parent_str = "…" + parent_str[-67:]
        self._folder_lbl.setText(parent_str)
        
        self.setWindowTitle(f"Memory Explorer — {d['filename']}")

        # Enable/Disable rotation for videos
        can_rotate = d["type"] == "image"
        self._rot_l_btn.setEnabled(can_rotate)
        self._rot_r_btn.setEnabled(can_rotate)

        # Favorite state
        is_fav = any(f.lower() == d["path"].lower() for f in self._settings.favorites)
        if is_fav:
            self._fav_btn.setText("⭐")
            self._fav_btn.setStyleSheet(self._fav_btn.styleSheet().replace("color: #8e8e93;", "color: #ffcc00;"))
        else:
            self._fav_btn.setText("☆")
            self._fav_btn.setStyleSheet(self._fav_btn.styleSheet().replace("color: #ffcc00;", "color: #8e8e93;"))

        # Map state
        has_gps = d.get("lat", 0.0) != 0.0 or d.get("lon", 0.0) != 0.0
        self._image_viewer.set_has_map(has_gps)

        if d["type"] == "image":
            self._type_badge.setText("IMG")
            self._type_badge.setStyleSheet(_TYPE_BADGE_IMAGE)
            self._media_stack.setCurrentIndex(0)
            dt = datetime.fromtimestamp(d["mtime"])
            year_str = dt.strftime("%Y")
            
            # Find rotation case-insensitively
            rot = 0
            for k, v in self._settings.rotations.items():
                if k.lower() == d["path"].lower():
                    rot = v
                    break
                    
            self._image_viewer.load(
                Path(d["path"]),
                rot,
                year_str=year_str,
            )
        else:
            self._type_badge.setText("VID")
            self._type_badge.setStyleSheet(_TYPE_BADGE_VIDEO)
            self._media_stack.setCurrentIndex(1)
            self._video_player.load(Path(d["path"]))

    def _navigate(self, delta: int) -> None:
        if not self._items:
            return
            
        if self._view_stack.currentIndex() == _PAGE_GALLERY:
            # Gallery navigation uses Qt's built in arrow navigation mostly,
            # but we can intercept PgUp/PgDn via shift if needed.
            # Usually QListView handles its own keyboard navigation.
            return

        new_index = max(0, min(self._index + delta, len(self._items) - 1))
        if new_index == self._index:
            return
        self._index = new_index
        self._show_current()

    # ==================================================================
    # Keyboard handling
    # ==================================================================

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        """Intercept arrow keys from the search box so they navigate photos."""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                       Qt.Key.Key_Up, Qt.Key.Key_Down):
                # Steal the event — clear focus from search and navigate
                self._filter_bar._search_box.clearFocus()
                self.keyPressEvent(event)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key   = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        step  = 10 if shift else 1

        # Prevent overriding native QListView navigation when in gallery mode
        in_gallery = (self._view_stack.currentIndex() == _PAGE_GALLERY)

        if key == Qt.Key.Key_Right and not in_gallery:
            self._navigate(+step)
        elif key == Qt.Key.Key_Left and not in_gallery:
            self._navigate(-step)
        elif key == Qt.Key.Key_Space:
            if self._current_type == "video" and not in_gallery:
                self._video_player.toggle_play_pause()
        elif key in (Qt.Key.Key_F, Qt.Key.Key_F11):
            self._toggle_fullscreen()
        elif key == Qt.Key.Key_Escape and self.isFullScreen():
            self._exit_fullscreen()
        elif key == Qt.Key.Key_Delete:
            self._delete_current()
        elif key == Qt.Key.Key_R:
            self._rotate_current(not shift) # Shift+R = Counter-Clockwise
        else:
            super().keyPressEvent(event)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self.showFullScreen()
            self._top_bar.hide()
            self._filter_bar.hide()
            self._info_bar.hide()
            self.statusBar().hide()

    def _exit_fullscreen(self) -> None:
        self.showNormal()
        self._top_bar.show()
        self._filter_bar.show()
        if self._view_stack.currentIndex() == _PAGE_VIEWER:
            self._info_bar.show()
        self.statusBar().show()

    # ==================================================================
    # Folder picker
    # ==================================================================

    def _on_manage_folders(self) -> None:
        dlg = ManageFoldersDialog(self._settings.root_folders, parent=self)
        if dlg.exec():
            if dlg.roots != self._settings.root_folders:
                self._settings.root_folders = dlg.roots
                save_settings(self._settings)
                
                self._release_current()
                self._current_type = ""
                self._start_scan(force=True)
