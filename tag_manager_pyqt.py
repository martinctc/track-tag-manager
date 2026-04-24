#!/usr/bin/env python3
"""
DJ Tag Manager — PyQt6 Edition
Modernised UI reusing all tag I/O logic from tag_manager.py.

Launch:  python tag_manager_pyqt.py

Keys:  Space = play/pause   S = save   Ctrl+O = open folder
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QScrollArea,
    QFrame, QFileDialog, QMessageBox, QSlider,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

# Re-use all tag I/O from the original app — no changes needed there.
sys.path.insert(0, str(Path(__file__).parent))
from tag_manager import (
    read_tags, write_tags,
    COMMENT_TAGS, ENERGY_LEVELS, ENERGY_COLORS,
    DEFAULT_DIR, SUPPORTED, RATINGS, RATING_LABELS,
)

# Optional audio: uses python-vlc when present, silent fallback otherwise.
try:
    import vlc as _vlc
    _vlc.Instance()          # raises if libvlc.dll / libvlc.so is missing
    HAS_VLC = True
except Exception:
    HAS_VLC = False


# ─── Colour palette ─────────────────────────────────────────────────────────

class _C:
    BG_DARK    = "#1a1a1a"
    BG_MEDIUM  = "#2a2a2a"
    BG_LIGHT   = "#3a3a3a"
    FG         = "#e0e0e0"
    FG2        = "#999999"
    ACCENT     = "#0d7377"
    ACCENT_HI  = "#14919b"
    ACCENT_LO  = "#0a5a5f"


def _stylesheet() -> str:
    return f"""
        * {{ background-color: {_C.BG_DARK}; color: {_C.FG}; border: none; }}
        QPushButton {{
            background-color: {_C.BG_LIGHT};
            border-radius: 4px; padding: 7px 12px; font-weight: bold;
        }}
        QPushButton:hover  {{ background-color: {_C.BG_MEDIUM}; }}
        QPushButton:pressed {{ background-color: {_C.ACCENT}; color: #fff; }}
        QPushButton:disabled {{ color: {_C.FG2}; }}
        QListWidget {{
            background-color: {_C.BG_MEDIUM}; border-radius: 4px;
        }}
        QListWidget::item {{ padding: 8px; border-radius: 2px; }}
        QListWidget::item:hover    {{ background-color: {_C.BG_LIGHT}; }}
        QListWidget::item:selected {{ background-color: {_C.ACCENT}; }}
        QScrollBar:vertical {{
            background: {_C.BG_MEDIUM}; width: 10px;
        }}
        QScrollBar::handle:vertical {{
            background: {_C.BG_LIGHT}; border-radius: 5px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {_C.ACCENT}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QSlider::groove:horizontal {{
            background: {_C.BG_LIGHT}; height: 4px; border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {_C.ACCENT}; width: 12px; height: 12px;
            margin: -4px 0; border-radius: 6px;
        }}
        QMenuBar {{ background-color: {_C.BG_MEDIUM}; }}
        QMenuBar::item:selected {{ background-color: {_C.ACCENT}; }}
        QMenu {{ background-color: {_C.BG_MEDIUM}; }}
        QMenu::item:selected {{ background-color: {_C.ACCENT}; }}
    """


# ─── Tag status helpers ──────────────────────────────────────────────────────

def _tag_status(path: Path) -> str:
    """Return 'full', 'partial', or 'empty' for a track."""
    t = read_tags(path)
    energy   = t.get('energy')
    rating   = t.get('rating')
    comments = t.get('comments', set())

    if not energy and not rating and not comments:
        return 'empty'

    has_all = bool(energy) and bool(rating) and all(
        bool(comments & set(COMMENT_TAGS[cat])) for cat in COMMENT_TAGS
    )
    return 'full' if has_all else 'partial'


_STATUS_ICON = {'full': '🟢', 'partial': '🟡', 'empty': '🔴'}
_STATUS_HINT = {'full': 'Fully tagged', 'partial': 'Partially tagged', 'empty': 'Untagged'}


# ─── Widgets ─────────────────────────────────────────────────────────────────

class _TrackRow(QWidget):
    """A single row in the track list showing status, name, and hint."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        lay = QHBoxLayout()
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(8)

        self._icon = QLabel()
        self._icon.setFont(QFont("Segoe UI Emoji", 13))
        self._icon.setFixedWidth(28)
        lay.addWidget(self._icon)

        self._name = QLabel(path.name)
        self._name.setFont(QFont("Arial", 10))
        lay.addWidget(self._name, 1)

        self._hint = QLabel()
        self._hint.setFont(QFont("Arial", 9))
        self._hint.setStyleSheet(f"color: {_C.FG2};")
        lay.addWidget(self._hint)

        self.setLayout(lay)
        self.refresh()

    def refresh(self):
        status = _tag_status(self.path)
        self._icon.setText(_STATUS_ICON[status])
        self._hint.setText(_STATUS_HINT[status])


class TrackListPanel(QWidget):
    track_selected = pyqtSignal(Path)

    def __init__(self):
        super().__init__()
        self._rows: dict[Path, _TrackRow] = {}

        lay = QVBoxLayout()
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        lbl = QLabel("TRACKS")
        lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_C.FG2};")
        hdr.addWidget(lbl)
        self._count = QLabel()
        self._count.setFont(QFont("Arial", 9))
        self._count.setStyleSheet(f"color: {_C.FG2};")
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight)
        hdr.addWidget(self._count)
        lay.addLayout(hdr)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_click)
        lay.addWidget(self._list)

        self.setLayout(lay)

    def load(self, directory: Path):
        self._list.clear()
        self._rows.clear()
        if not directory.exists():
            return
        files = sorted(
            [f for f in directory.iterdir() if f.suffix.lower() in SUPPORTED],
            key=lambda f: f.name.lower(),
        )
        for path in files:
            row = _TrackRow(path)
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 46))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            self._rows[path] = row
        self._count.setText(f"{len(files)} tracks")

    def refresh_track(self, path: Path):
        if path in self._rows:
            self._rows[path].refresh()

    def _on_click(self, item: QListWidgetItem):
        row = self._list.itemWidget(item)
        if isinstance(row, _TrackRow):
            self.track_selected.emit(row.path)


class AudioBar(QWidget):
    """Compact playback controls (shown only when VLC is available)."""

    def __init__(self):
        super().__init__()
        self._player = None
        self._media_player = None
        self._playing = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)

        if HAS_VLC:
            self._instance = _vlc.Instance('--quiet')
            self._player = self._instance.media_list_player_new()

        lay = QHBoxLayout()
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.clicked.connect(self.toggle_play)
        self._play_btn.setEnabled(False)
        lay.addWidget(self._play_btn)

        stop_btn = QPushButton("■")
        stop_btn.setFixedSize(36, 36)
        stop_btn.clicked.connect(self.stop)
        lay.addWidget(stop_btn)

        self._time = QLabel("0:00 / 0:00")
        self._time.setFont(QFont("Courier", 9))
        self._time.setStyleSheet(f"color: {_C.FG2};")
        self._time.setMinimumWidth(84)
        lay.addWidget(self._time)

        self._scrub = QSlider(Qt.Orientation.Horizontal)
        self._scrub.setRange(0, 1000)
        self._scrub.sliderMoved.connect(self._seek)
        lay.addWidget(self._scrub, 1)

        lay.addWidget(QLabel("🔊"))
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(80)
        self._vol.setMaximumWidth(90)
        self._vol.valueChanged.connect(self._set_vol)
        lay.addWidget(self._vol)

        self.setLayout(lay)
        self.setFixedHeight(58)
        self.setStyleSheet(f"background-color: {_C.BG_MEDIUM};")

    def load(self, path: Path):
        if not HAS_VLC:
            return
        ml = self._instance.media_list_new([str(path)])
        self._player.set_media_list(ml)
        self._media_player = self._player.get_media_player()
        self._play_btn.setEnabled(True)
        # Auto-play on track selection
        self._player.play()
        self._playing = True
        self._play_btn.setText("⏸")
        self._timer.start(150)

    def toggle_play(self):
        if not HAS_VLC or not self._player:
            return
        if self._playing:
            self._player.pause()
            self._play_btn.setText("▶")
            self._timer.stop()
        else:
            self._player.play()
            self._play_btn.setText("⏸")
            self._timer.start(150)
        self._playing = not self._playing

    def stop(self):
        if not HAS_VLC or not self._player:
            return
        self._player.stop()
        self._playing = False
        self._play_btn.setText("▶")
        self._timer.stop()
        self._scrub.setValue(0)
        self._time.setText("0:00 / 0:00")

    def _seek(self, val: int):
        if self._media_player:
            self._media_player.set_position(val / 1000)

    def _set_vol(self, val: int):
        if self._media_player:
            self._media_player.audio_set_volume(val)

    def _tick(self):
        if not self._media_player:
            return
        pos = self._media_player.get_position()
        dur = self._media_player.get_length()
        cur = int(pos * dur)
        self._scrub.blockSignals(True)
        self._scrub.setValue(int(pos * 1000))
        self._scrub.blockSignals(False)
        self._time.setText(f"{_fmt(cur)} / {_fmt(dur)}")


def _fmt(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class TagEditorPanel(QWidget):
    """Full tag editor: energy, rating, and all comment categories."""

    saved = pyqtSignal(Path)

    def __init__(self):
        super().__init__()
        self._path: Path | None = None
        self._tags: dict = {}
        self._energy_btns: dict = {}
        self._rating_btns: dict = {}
        self._tag_btns: dict = {}
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout()
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(10)

        self._track_lbl = QLabel("No track selected")
        self._track_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        outer.addWidget(self._track_lbl)

        # Scrollable section
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        inner_w = QWidget()
        inner = QVBoxLayout()
        inner.setSpacing(10)

        # Energy
        inner.addWidget(self._section_label("ENERGY"))
        row = QHBoxLayout()
        for lvl in ENERGY_LEVELS:
            b = QPushButton(lvl)
            b.setMinimumHeight(32)
            b.clicked.connect(lambda _, l=lvl: self._pick_energy(l))
            row.addWidget(b)
            self._energy_btns[lvl] = b
        row.addStretch()
        inner.addLayout(row)

        # Rating
        inner.addWidget(self._section_label("RATING"))
        row = QHBoxLayout()
        for r in RATINGS:
            b = QPushButton(RATING_LABELS[r])
            b.setMinimumHeight(32)
            b.clicked.connect(lambda _, rv=r: self._pick_rating(rv))
            row.addWidget(b)
            self._rating_btns[r] = b
        row.addStretch()
        inner.addLayout(row)

        # Comment tags
        inner.addWidget(self._section_label("TAGS"))
        for cat, tags in COMMENT_TAGS.items():
            lbl = QLabel(cat.upper())
            lbl.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {_C.FG2};")
            inner.addWidget(lbl)
            flow = QHBoxLayout()
            flow.setSpacing(4)
            for tag in tags:
                b = QPushButton(tag)
                b.setMaximumWidth(100)
                b.setMinimumHeight(26)
                b.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {_C.BG_LIGHT};
                        font-size: 9px; border-radius: 3px; padding: 4px 8px;
                    }}
                    QPushButton:hover {{ background-color: {_C.BG_MEDIUM}; }}
                    QPushButton:pressed {{ background-color: {_C.ACCENT}; color: #fff; }}
                """)
                b.clicked.connect(lambda _, t=tag: self._toggle_tag(t))
                flow.addWidget(b)
                self._tag_btns[tag] = b
            flow.addStretch()
            inner.addLayout(flow)

        inner.addStretch()
        inner_w.setLayout(inner)
        scroll.setWidget(inner_w)
        outer.addWidget(scroll, 1)

        save_btn = QPushButton("💾  Save Tags")
        save_btn.setMinimumHeight(40)
        save_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C.ACCENT}; color: #fff;
                border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover  {{ background-color: {_C.ACCENT_HI}; }}
            QPushButton:pressed {{ background-color: {_C.ACCENT_LO}; }}
        """)
        save_btn.clicked.connect(self._save)
        outer.addWidget(save_btn)

        self.setLayout(outer)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_C.FG2}; margin-top: 6px;")
        return lbl

    def load(self, path: Path):
        self._path = path
        self._tags = read_tags(path)
        self._track_lbl.setText(path.name)
        self._refresh_buttons()

    def _refresh_buttons(self):
        energy   = self._tags.get('energy')
        rating   = self._tags.get('rating')
        comments = self._tags.get('comments', set())

        for lvl, b in self._energy_btns.items():
            col = ENERGY_COLORS.get(lvl, _C.ACCENT) if lvl == energy else _C.BG_LIGHT
            fg  = '#fff' if lvl == energy else _C.FG
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col}; color: {fg};
                    border-radius: 4px; padding: 7px 12px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {_C.BG_MEDIUM}; }}
            """)

        for r, b in self._rating_btns.items():
            col = _C.ACCENT if r == rating else _C.BG_LIGHT
            fg  = '#fff' if r == rating else _C.FG
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col}; color: {fg};
                    border-radius: 4px; padding: 7px 12px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {_C.BG_MEDIUM}; }}
            """)

        for tag, b in self._tag_btns.items():
            on = tag in comments
            col = _C.ACCENT if on else _C.BG_LIGHT
            fg  = '#fff' if on else _C.FG
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col}; color: {fg};
                    font-size: 9px; border-radius: 3px; padding: 4px 8px;
                }}
                QPushButton:hover {{ background-color: {_C.BG_MEDIUM}; }}
            """)

    def _pick_energy(self, lvl: str):
        self._tags['energy'] = lvl
        self._refresh_buttons()

    def _pick_rating(self, r: int):
        self._tags['rating'] = r
        self._refresh_buttons()

    def _toggle_tag(self, tag: str):
        comments = self._tags.setdefault('comments', set())
        comments.discard(tag) if tag in comments else comments.add(tag)
        self._refresh_buttons()

    def _save(self):
        if not self._path:
            return
        err = write_tags(
            self._path,
            self._tags.get('energy'),
            self._tags.get('rating'),
            self._tags.get('comments', set()),
        )
        if err:
            QMessageBox.critical(self, "Save error", err)
        else:
            self.saved.emit(self._path)


# ─── Main Window ─────────────────────────────────────────────────────────────

class App(QMainWindow):

    def __init__(self):
        super().__init__()
        self._dir = DEFAULT_DIR
        self._build()
        self.setWindowTitle("DJ Tag Manager")
        self.resize(1300, 820)
        self.setStyleSheet(_stylesheet())
        self._load_dir(self._dir)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # Left sidebar
        sidebar = QFrame()
        sidebar.setStyleSheet(f"background-color: {_C.BG_MEDIUM};")
        sidebar.setMaximumWidth(380)
        sb_lay = QVBoxLayout()
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)

        pick = QPushButton("📁  Open Folder")
        pick.setMinimumHeight(42)
        pick.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        pick.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C.ACCENT}; color: #fff;
                border-radius: 0; margin: 0; padding: 10px;
            }}
            QPushButton:hover {{ background-color: {_C.ACCENT_HI}; }}
        """)
        pick.clicked.connect(self._pick_folder)
        sb_lay.addWidget(pick)

        self._tracks = TrackListPanel()
        self._tracks.track_selected.connect(self._on_select)
        sb_lay.addWidget(self._tracks)
        sidebar.setLayout(sb_lay)
        h.addWidget(sidebar)

        # Right side
        right = QFrame()
        right.setStyleSheet(f"background-color: {_C.BG_DARK};")
        r_lay = QVBoxLayout()
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(0)

        self._audio = AudioBar()
        if HAS_VLC:
            r_lay.addWidget(self._audio)

        self._editor = TagEditorPanel()
        self._editor.saved.connect(self._on_saved)
        r_lay.addWidget(self._editor, 1)

        right.setLayout(r_lay)
        h.addWidget(right, 1)
        root.setLayout(h)

        self._build_menu()

    def _build_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        a = fm.addAction("Open Folder…")
        a.setShortcut("Ctrl+O")
        a.triggered.connect(self._pick_folder)
        fm.addSeparator()
        a = fm.addAction("Exit")
        a.setShortcut("Ctrl+Q")
        a.triggered.connect(self.close)

        em = mb.addMenu("Edit")
        a = em.addAction("Save")
        a.setShortcut("S")
        a.triggered.connect(self._editor._save)

        if HAS_VLC:
            pm = mb.addMenu("Playback")
            a = pm.addAction("Play / Pause")
            a.setShortcut("Space")
            a.triggered.connect(self._audio.toggle_play)
            a = pm.addAction("Stop")
            a.setShortcut("Shift+Space")
            a.triggered.connect(self._audio.stop)

        hm = mb.addMenu("Help")
        a = hm.addAction("About")
        a.triggered.connect(self._about)

    def _load_dir(self, directory: Path):
        self._dir = directory
        self._tracks.load(directory)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Music Folder", str(self._dir))
        if d:
            self._load_dir(Path(d))

    def _on_select(self, path: Path):
        self._editor.load(path)
        if HAS_VLC:
            self._audio.load(path)

    def _on_saved(self, path: Path):
        self._tracks.refresh_track(path)

    def _about(self):
        QMessageBox.about(
            self,
            "DJ Tag Manager",
            "DJ Tag Manager — PyQt6 Edition\n\n"
            "Writes Genre, Rating, and Comment tags directly into\n"
            "MP3, WAV, AIFF, FLAC, and M4A files.\n\n"
            "Licensed under MIT",
        )


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
