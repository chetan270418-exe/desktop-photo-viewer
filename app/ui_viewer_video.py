"""
Memory Explorer — Video Player Widget (Phase 3)

Wraps Qt Multimedia (QMediaPlayer + QAudioOutput + QVideoWidget) to deliver
inline video playback with a polished control bar.

Public API
----------
load(path)            Load and auto-play a video file.
release()             Stop, clear source, reset UI — call before navigating away.
toggle_play_pause()   Space-key handler; toggling play ↔ pause.
is_playing() -> bool  True if currently in PlayingState.

Error handling
--------------
If the media player signals an error (unsupported codec, missing file, etc.)
an on-screen error overlay is shown *inside* the widget instead of crashing.

Design notes
------------
* The scrubber only seeks when the user drags it (`sliderMoved`), not during
  programmatic position updates, to avoid a feedback loop.
* Volume/mute state is preserved across load() calls.
* The control bar is always visible (hides only in fullscreen — handled by
  MainWindow, not here).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_ms(ms: int) -> str:
    """Format a millisecond duration as M:SS or H:MM:SS."""
    s = max(ms, 0) // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Control bar
# ---------------------------------------------------------------------------

_CTRL_BTN = (
    "QPushButton { color:#fff; background:#1e1e2e; border:none; "
    "font-size:18px; border-radius:5px; padding:4px 10px; }"
    "QPushButton:hover { background:#2e2e4e; }"
    "QPushButton:pressed { background:#7c6af7; }"
)
_SLIDER_SS = (
    "QSlider::groove:horizontal { height:4px; background:#2e2e3e; border-radius:2px; }"
    "QSlider::sub-page:horizontal { background:#7c6af7; border-radius:2px; }"
    "QSlider::handle:horizontal { width:14px; height:14px; margin:-5px 0; "
    "background:#fff; border-radius:7px; }"
)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class VideoPlayer(QWidget):
    """
    Self-contained video player: video area + control bar.

    Layout
    ------
    ┌─────────────────────────────────────────────┐
    │                                             │
    │            QVideoWidget  (or error)         │  ← expands
    │                                             │
    ├─────────────────────────────────────────────┤
    │ ▶  [━━━━━━━━━━━━━━━━━━━━━━━━━━━━]  0:00/0:00  🔊 │  ← fixed height
    └─────────────────────────────────────────────┘
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background:#0d0d0d;")

        # ── Qt Multimedia stack ────────────────────────────────────────
        self._audio = QAudioOutput(self)
        self._audio.setVolume(1.0)

        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)

        # ── Video display area (stacked: video | error overlay) ────────
        self._video_widget = QVideoWidget()
        self._video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_widget.setStyleSheet("background:#000;")
        self._player.setVideoOutput(self._video_widget)

        self._error_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            "color:#c0392b; font-size:15px; background:#0d0d0d; padding:20px;"
        )

        self._display_stack = QStackedWidget()
        self._display_stack.addWidget(self._video_widget)   # index 0 — normal
        self._display_stack.addWidget(self._error_lbl)      # index 1 — error

        # ── Control bar ────────────────────────────────────────────────
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(38, 32)
        self._play_btn.setStyleSheet(_CTRL_BTN)
        self._play_btn.setToolTip("Play / Pause  (Space)")
        self._play_btn.clicked.connect(self.toggle_play_pause)

        self._mute_btn = QPushButton("🔊")
        self._mute_btn.setFixedSize(36, 32)
        self._mute_btn.setStyleSheet(_CTRL_BTN)
        self._mute_btn.setToolTip("Mute / Unmute")
        self._mute_btn.clicked.connect(self._toggle_mute)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, 0)
        self._scrubber.setStyleSheet(_SLIDER_SS)
        self._scrubber.setToolTip("Seek")
        # sliderMoved  → user is dragging  → seek immediately
        self._scrubber.sliderMoved.connect(self._player.setPosition)
        # sliderPressed → lock out programmatic updates while user holds
        self._scrubber.sliderPressed.connect(self._on_slider_pressed)
        self._scrubber.sliderReleased.connect(self._on_slider_released)

        self._time_lbl = QLabel("0:00 / 0:00")
        self._time_lbl.setStyleSheet(
            "color:#aaa; font-size:12px; font-family:'Segoe UI'; "
            "background:transparent; min-width:96px;"
        )
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ctrl_lay = QHBoxLayout()
        ctrl_lay.setContentsMargins(10, 5, 10, 8)
        ctrl_lay.setSpacing(8)
        ctrl_lay.addWidget(self._play_btn)
        ctrl_lay.addWidget(self._scrubber, stretch=1)
        ctrl_lay.addWidget(self._time_lbl)
        ctrl_lay.addWidget(self._mute_btn)

        ctrl_bar = QWidget()
        ctrl_bar.setFixedHeight(48)
        ctrl_bar.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #151520, stop:1 #0d0d0d);"
            "border-top: 1px solid #1e1e30;"
        )
        ctrl_bar.setLayout(ctrl_lay)

        # ── Main layout ────────────────────────────────────────────────
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        main_lay.addWidget(self._display_stack, stretch=1)
        main_lay.addWidget(ctrl_bar)

        # ── Player signals ─────────────────────────────────────────────
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # Internal flag — prevents scrubber→position feedback loop
        self._user_seeking: bool = False

    # ==================================================================
    # Public API
    # ==================================================================

    def load(self, path: Path) -> None:
        """
        Load *path* and begin playing immediately.
        Any previous playback is stopped and released first.
        """
        self._clear_error()
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        logger.info("VideoPlayer: loading %s", path.name)

    def release(self) -> None:
        """
        Stop playback and fully release the media source.
        Call this before navigating to a different item so the previous
        video does not keep decoding in the background.
        """
        self._player.stop()
        self._player.setSource(QUrl())        # clears the source
        self._scrubber.setValue(0)
        self._time_lbl.setText("0:00 / 0:00")
        self._play_btn.setText("▶")
        self._clear_error()
        logger.debug("VideoPlayer: released")

    def toggle_play_pause(self) -> None:
        """Toggle between Playing and Paused. Safe to call at any time."""
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # ==================================================================
    # Private slots
    # ==================================================================

    def _on_slider_pressed(self) -> None:
        self._user_seeking = True

    def _on_slider_released(self) -> None:
        self._player.setPosition(self._scrubber.value())
        self._user_seeking = False

    def _toggle_mute(self) -> None:
        muted = self._audio.isMuted()
        self._audio.setMuted(not muted)
        self._mute_btn.setText("🔇" if not muted else "🔊")

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setText("⏸" if playing else "▶")

    def _on_position_changed(self, pos_ms: int) -> None:
        if not self._user_seeking:
            # Suppress the valueChanged signal so it doesn't fire sliderMoved
            self._scrubber.blockSignals(True)
            self._scrubber.setValue(pos_ms)
            self._scrubber.blockSignals(False)
        dur = self._player.duration()
        self._time_lbl.setText(f"{_fmt_ms(pos_ms)} / {_fmt_ms(dur)}")

    def _on_duration_changed(self, dur_ms: int) -> None:
        self._scrubber.setRange(0, max(dur_ms, 0))

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        """Catch InvalidMedia to show a user-friendly error overlay."""
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._show_error(
                "⚠  Cannot play this video\n\n"
                "The file may be corrupted or use an unsupported codec.\n\n"
                f"Format hint: {Path(self._player.source().toLocalFile()).suffix.upper() or 'unknown'}"
            )

    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        logger.warning("VideoPlayer error [%s]: %s", error, error_string)
        if error != QMediaPlayer.Error.NoError:
            self._show_error(
                f"⚠  Unable to play this video\n\n{error_string}\n\n"
                "Unsupported format or missing codec."
            )

    # ==================================================================
    # Error overlay helpers
    # ==================================================================

    def _show_error(self, message: str) -> None:
        self._error_lbl.setText(message)
        self._display_stack.setCurrentIndex(1)   # flip to error overlay

    def _clear_error(self) -> None:
        self._display_stack.setCurrentIndex(0)   # flip back to video widget
        self._error_lbl.setText("")
