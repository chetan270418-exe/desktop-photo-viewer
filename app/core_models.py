"""
Memory Explorer — Data Models

Defines the core data structures and settings persistence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"
CACHE_PATH = Path(__file__).parent.parent / "data" / "scan_cache.json"


@dataclass
class Settings:
    """Application settings, persisted to data/settings.json."""
    root_folders: list[str] = field(default_factory=list)
    rotations: dict[str, int] = field(default_factory=dict)
    # Placeholder fields for future phases
    sort_order: str = "path"
    last_index: int = 0


def load_settings() -> Settings:
    """Load settings from disk. Returns a default Settings if missing or corrupt."""
    if not SETTINGS_PATH.exists():
        return Settings()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        roots = data.get("root_folders", [])
        if not isinstance(roots, list):
            roots = []
        roots = [str(r) for r in roots]
        
        rotations = data.get("rotations", {})
        if not isinstance(rotations, dict):
            rotations = {}
            
        return Settings(root_folders=roots, rotations=rotations)
    except Exception as exc:
        logger.warning("Could not read settings.json (%s), using defaults.", exc)
        return Settings()


def save_settings(settings: Settings) -> None:
    """Persist settings to disk."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "root_folders": settings.root_folders,
            "rotations": settings.rotations,
            "sort_order": settings.sort_order,
            "last_index": settings.last_index,
        }
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Saved settings successfully.")
    except Exception as exc:
        logger.error("Failed to save settings.json: %s", exc)


def load_scan_cache() -> list[dict] | None:
    """Load the scanned items from disk cache, returning None if missing or corrupt."""
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            logger.info("Loaded %d items from scan cache.", len(data))
            return data
    except Exception as exc:
        logger.warning("Could not read scan cache (%s)", exc)
    return None


def save_scan_cache(items: list[dict]) -> None:
    """Save the scanned items to disk cache for instant startup."""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(items), encoding="utf-8")
        logger.info("Saved %d items to scan cache.", len(items))
    except Exception as exc:
        logger.error("Failed to save scan cache: %s", exc)
