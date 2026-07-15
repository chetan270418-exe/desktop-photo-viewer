"""
Memory Explorer — Thumbnail Worker

Generates 200x200 center-cropped thumbnails in the background using Pillow.
Caches them in memory and on disk.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtGui import QIcon, QPixmap
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data" / "thumb_cache"
THUMB_SIZE = 200

# Simple global memory cache for active session
_MEM_CACHE: dict[str, QIcon] = {}


class ThumbnailSignals(QObject):
    """Signals for a background thumbnail request."""
    # (original_path, cache_path, is_video)
    ready = Signal(str, str, bool)


class ThumbnailTask(QRunnable):
    """A single background task to generate/load a thumbnail."""

    def __init__(self, path: str, media_type: str, rotations: dict[str, int]) -> None:
        super().__init__()
        self.path = path
        self.media_type = media_type
        self.rotations = rotations
        self.signals = ThumbnailSignals()

    def run(self) -> None:
        if self.media_type == "video":
            self._safe_emit(self.path, "", True)
            return

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # Use mtime + rot as cache key
            mtime = Path(self.path).stat().st_mtime
            rot = self.rotations.get(self.path, 0)
            
            # Simple hash for filename to avoid illegal characters
            import hashlib
            name_hash = hashlib.md5(self.path.encode("utf-8")).hexdigest()
            cache_key = f"{name_hash}_{int(mtime)}_{rot}.jpg"
            cache_file = CACHE_DIR / cache_key

            if cache_file.exists():
                self._safe_emit(self.path, str(cache_file), False)
                return

            # Generate new thumbnail
            with Image.open(self.path) as img:
                img = ImageOps.exif_transpose(img)
                if rot:
                    # Pillow rotates counter-clockwise, so negate for CW
                    img = img.rotate(-rot, expand=True)
                
                if img.mode != "RGB":
                    img = img.convert("RGB")
                    
                thumb = ImageOps.fit(
                    img, (THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS
                )
                thumb.save(cache_file, "JPEG", quality=85)

            self._safe_emit(self.path, str(cache_file), False)
            
        except Exception as exc:
            logger.debug("Could not generate thumbnail for %s: %s", self.path, exc)
            self._safe_emit(self.path, "", False)

    def _safe_emit(self, path: str, cache_path: str, is_video: bool) -> None:
        """Emit the ready signal, silently ignoring if the receiver was deleted."""
        try:
            self.signals.ready.emit(path, cache_path, is_video)
        except RuntimeError:
            pass  # Signal source deleted — model was replaced, safe to ignore


class ThumbnailManager(QObject):
    """
    Manages background generation of thumbnails.
    Must be instantiated on the main UI thread.
    """
    
    def __init__(self, rotations: dict[str, int], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self.rotations = rotations
        
        # Keep references to callbacks so they aren't garbage collected
        self._callbacks: dict[str, list[Callable[[QIcon], None]]] = {}

    def get_thumbnail_async(self, path: str, media_type: str, callback: Callable[[QIcon], None]) -> None:
        """
        Request a thumbnail. If it's in memory, callback is invoked immediately.
        Otherwise, it's generated on a background thread and callback is invoked later.
        """
        if path in _MEM_CACHE:
            callback(_MEM_CACHE[path])
            return

        if path in self._callbacks:
            self._callbacks[path].append(callback)
            return

        self._callbacks[path] = [callback]

        task = ThumbnailTask(path, media_type, self.rotations)
        task.signals.ready.connect(self._on_ready)
        self._pool.start(task)

    def _on_ready(self, orig_path: str, cache_path: str, is_video: bool) -> None:
        if orig_path not in self._callbacks:
            return

        if is_video:
            pix = QPixmap(THUMB_SIZE, THUMB_SIZE)
            pix.fill(Qt.GlobalColor.darkBlue)
            icon = QIcon(pix)
        elif not cache_path:
            pix = QPixmap(THUMB_SIZE, THUMB_SIZE)
            pix.fill(Qt.GlobalColor.darkRed)
            icon = QIcon(pix)
        else:
            icon = QIcon(cache_path)
            
        _MEM_CACHE[orig_path] = icon
        
        cbs = self._callbacks.pop(orig_path)
        for cb in cbs:
            cb(icon)

    @staticmethod
    def clear_memory_cache() -> None:
        _MEM_CACHE.clear()
