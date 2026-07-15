# Memory Explorer — Task Tracker

## Phase 1-3: Core MVP (Scanner + Image Viewer + Video Playback)

- [x] Project scaffold created (`main.py`, `app/`, `data/`, `requirements.txt`, `README.md`)
- [x] `app/models.py` — `MediaItem`, `MediaType`, `classify()`, extension sets
- [x] `app/scanner.py` — `scan_folder()`, `scan_folders()`, CLI (`python -m app.scanner`)
- [x] `app/image_viewer.py` — `ImageViewer` widget (aspect-ratio scaling, error handling)
- [x] `app/video_player.py` — `VideoPlayer` widget (QMediaPlayer, scrubber, mute)
- [x] `app/main_window.py` — `MainWindow` (navigation, keyboard shortcuts, fullscreen, folder picker, settings persistence)
- [x] `main.py` — entry point
- [x] `data/settings.json` — initial empty settings

## Phase 4: Folder picker + persistence
- [x] Folder picker via QFileDialog (embedded in main_window.py)
- [x] settings.json read/write (embedded in main_window.py)

## Pending Phases
- [ ] Phase 5: Gallery view with thumbnails
- [ ] Phase 6: Search and filters
- [ ] Phase 7: Performance pass (background threads, progress bar)
- [ ] Phase 8: Safety/testing pass
