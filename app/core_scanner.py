"""
Memory Explorer — Recursive Media Scanner (Phase 1)

Public API
----------
scan_folders(root_folders: list[str]) -> list[dict]

Each dict has the keys:
    path      str   – absolute path to the file
    filename  str   – basename only
    type      str   – "image" or "video"
    mtime     float – os.path.getmtime value (seconds since epoch)

Rules (non-negotiable)
----------------------
* Read-only — never modifies, moves, or renames any file.
* Skips .json sidecar files and every other non-media extension silently.
* Handles permission errors and broken symlinks gracefully (log & continue).
* Results are sorted by full path (case-insensitive) for deterministic order.
* Never raises on a single bad file.
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Generator, Callable
import concurrent.futures
import json

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1024)
def _list_json_names(parent: str) -> tuple[str, ...]:
    """Cached listing of *.json filenames in a directory (thread-safe: read-only)."""
    try:
        return tuple(e.name for e in os.scandir(parent) if e.name.lower().endswith(".json"))
    except OSError:
        return ()


def _find_sidecar_json(path: Path) -> Path | None:
    """
    Locate a Google Takeout JSON sidecar for a media file.

    Google has used several inconsistent sidecar naming schemes over the
    years, and truncates long filenames, e.g. for "IMG_1234.jpg":
        IMG_1234.jpg.json                                  (older exports)
        IMG_1234.jpg.supplemental-metadata.json            (2024+ exports)
        IMG_20230815_142536.jpg.supplemental-metad.json    (truncated)
        IMG_1234.json                                      (no extension)
    """
    name = path.name
    direct_candidates = (
        path.with_name(name + ".json"),
        path.with_name(name + ".supplemental-metadata.json"),
        path.with_suffix(".json"),
    )
    for candidate in direct_candidates:
        if candidate.exists():
            return candidate

    best_name, best_len = None, 0
    for json_name in _list_json_names(str(path.parent)):
        common = os.path.commonprefix([name, json_name])
        if len(common) > best_len:
            best_len, best_name = len(common), json_name

    if best_name and best_len >= max(8, int(len(name) * 0.7)):
        return path.parent / best_name
    return None

# ---------------------------------------------------------------------------
# Extension sets (case-insensitive matching done via .lower())
# ---------------------------------------------------------------------------

_IMAGE_EXT: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
)
_VIDEO_EXT: frozenset[str] = frozenset(
    {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
)


def _classify(filename: str) -> str | None:
    """Return 'image', 'video', or None for unrecognised / sidecar files."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _VIDEO_EXT:
        return "video"
    return None


# ---------------------------------------------------------------------------
# Core walker
# ---------------------------------------------------------------------------

def _fast_walk(root: str) -> Generator[str, None, None]:
    """
    Recursively yield absolute paths of regular files using os.scandir.
    Significantly faster than Path.rglob("*") on Windows.
    """
    try:
        with os.scandir(root) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        yield from _fast_walk(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry.path
                except OSError:
                    pass  # skip unreadable files/dirs
    except OSError as exc:
        logger.warning("Cannot scan %s — %s", root, exc)


# ---------------------------------------------------------------------------
# Worker for metadata parsing
# ---------------------------------------------------------------------------

def _process_file(path_str: str, media_type: str) -> dict | None:
    """Parse stat mtime and JSON sidecars. Runs in a thread pool."""
    path = Path(path_str)
    try:
        mtime = path.stat().st_mtime
        lat = 0.0
        lon = 0.0
        
        # Check for Google Takeout JSON sidecar metadata
        json_path = _find_sidecar_json(path)

        if json_path is not None:
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    if "photoTakenTime" in meta and "timestamp" in meta["photoTakenTime"]:
                        mtime = float(meta["photoTakenTime"]["timestamp"])
                    elif "creationTime" in meta and "timestamp" in meta["creationTime"]:
                        mtime = float(meta["creationTime"]["timestamp"])

                    if "geoData" in meta:
                        geo = meta["geoData"]
                        lat = float(geo.get("latitude", 0.0))
                        lon = float(geo.get("longitude", 0.0))
            except Exception:
                pass  # Silently fallback to file stat mtime
                
    except OSError:
        mtime = 0.0
        lat = 0.0
        lon = 0.0

    return {
        "path": path_str,
        "filename": path.name,
        "type": media_type,
        "mtime": mtime,
        "lat": lat,
        "lon": lon,
    }


# ---------------------------------------------------------------------------
# Public function (Phase 1 spec)
# ---------------------------------------------------------------------------

def scan_folders(
    root_folders: list[str],
    progress_cb: Callable[[int], None] | None = None
) -> list[dict]:
    """
    Scan one or more root directories recursively for media files.
    """
    results: list[dict] = []
    
    # Phase 1: Fast traversal to find all candidate files
    candidates = []
    for folder_str in root_folders:
        root = Path(folder_str).resolve()
        logger.info("Scanning: %s", root)

        if not root.is_dir():
            logger.warning("Not a directory, skipping: %s", root)
            continue

        for path_str in _fast_walk(str(root)):
            media_type = _classify(path_str)
            if media_type is not None:
                candidates.append((path_str, media_type))
    
    if not candidates:
        return []

    # Phase 2: Parallel metadata extraction (stat + JSON parsing)
    count = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for path_str, m_type in candidates:
            futures.append(executor.submit(_process_file, path_str, m_type))
            
        for future in concurrent.futures.as_completed(futures):
            item = future.result()
            if item:
                results.append(item)
            count += 1
            if progress_cb and count % 200 == 0:
                progress_cb(count)

    if progress_cb:
        progress_cb(count)

    results.sort(key=lambda d: d["path"].lower())
    logger.info("Scan complete — %d media files found.", len(results))
    return results
