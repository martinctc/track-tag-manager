#!/usr/bin/env python3
"""
DJ Tag Manager — PyQt6 Edition
Modernised UI reusing all tag I/O logic from tag_manager.py.

Launch:  python tag_manager_pyqt.py

Keys:  Space = play/pause   S = save   Ctrl+O = open folder
"""

import sys
import json
import re
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QScrollArea,
    QFrame, QFileDialog, QMessageBox, QSlider, QDialog, QDialogButtonBox,
    QLineEdit, QTextEdit, QColorDialog, QButtonGroup, QRadioButton,
    QCheckBox, QProgressBar, QSizePolicy, QSplitter, QInputDialog,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QColor

# Re-use all tag I/O from the original app — no changes needed there.
sys.path.insert(0, str(Path(__file__).parent))
from tag_manager import (
    read_tags, write_tags,
    COMMENT_TAGS, ENERGY_LEVELS, ENERGY_COLORS, DEFAULT_ENERGY_COLORS,
    DEFAULT_DIR, SUPPORTED, RATINGS, RATING_LABELS, TAG_META,
    save_tag_config, list_bundled_presets, read_pack_file, apply_pack,
    normalize_tag_name, _has_ffmpeg, _copy_id3_tags, _copy_tags_to_flac,
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

        # Scrollable section — stored so it can be rebuilt when vocab changes
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._build_scroll_content()
        outer.addWidget(self._scroll, 1)

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

    def _build_scroll_content(self):
        """Build or rebuild the scrollable tag-picker widget."""
        self._energy_btns = {}
        self._rating_btns = {}
        self._tag_btns = {}

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
        self._scroll.setWidget(inner_w)

    def rebuild_vocab(self):
        """Rebuild tag palette after the vocabulary has been updated."""
        self._build_scroll_content()
        if self._path:
            self._refresh_buttons()

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


# ─── Statistics Dialog ───────────────────────────────────────────────────────

class StatsDialog(QDialog):
    """Read-only statistics about all tracks in the current folder."""

    _progress = pyqtSignal(str)   # emitted from worker thread
    _results  = pyqtSignal(int, int, int, int, dict, dict, dict)

    def __init__(self, files: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistics")
        self.resize(620, 560)
        self.setStyleSheet(_stylesheet())
        self._files = files
        self._init_ui()
        # Connect before starting the thread
        self._progress.connect(self._status_lbl.setText)
        self._results.connect(self._show_results)
        threading.Thread(target=self._scan, daemon=True).start()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        title = QLabel("📊  Statistics")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        self._status_lbl = QLabel(f"Scanning {len(self._files)} tracks…")
        self._status_lbl.setStyleSheet(f"color: {_C.FG2};")
        lay.addWidget(self._status_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setSpacing(12)
        scroll.setWidget(self._body)
        lay.addWidget(scroll, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _scan(self):
        tagged = untagged = errors = 0
        energy_counts: dict = {}
        rating_counts: dict = {}
        tag_counts: dict = {}
        total = len(self._files)

        for i, path in enumerate(self._files):
            self._progress.emit(f"Scanning {i + 1} / {total}…")
            try:
                t = read_tags(path)
                energy   = t.get('energy')
                rating   = t.get('rating')
                comments = t.get('comments', set())
                if energy or rating or comments:
                    tagged += 1
                else:
                    untagged += 1
                if energy:
                    energy_counts[energy] = energy_counts.get(energy, 0) + 1
                if rating:
                    rating_counts[rating] = rating_counts.get(rating, 0) + 1
                for tag in comments:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            except Exception:
                errors += 1

        self._results.emit(total, tagged, untagged, errors,
                           energy_counts, rating_counts, tag_counts)

    def _show_results(self, total: int, tagged: int, untagged: int, errors: int,
                      energy_counts: dict, rating_counts: dict, tag_counts: dict):
        self._status_lbl.setText(f"Scanned {total} tracks")
        lay = self._body_lay

        # Summary cards
        self._section("SUMMARY", lay)
        grid = QHBoxLayout()
        for label, value, color in [
            ("Total",    total,    _C.FG),
            ("Tagged",   tagged,   "#2ecc71"),
            ("Untagged", untagged, "#e74c3c"),
            ("Errors",   errors,   "#f39c12"),
        ]:
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {_C.BG_MEDIUM}; border-radius: 6px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            v = QLabel(str(value))
            v.setFont(QFont("Arial", 20, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {color};")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(v)
            l = QLabel(label)
            l.setFont(QFont("Arial", 9))
            l.setStyleSheet(f"color: {_C.FG2};")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(l)
            grid.addWidget(card)
        lay.addLayout(grid)

        # Energy distribution
        if energy_counts:
            self._section("ENERGY DISTRIBUTION", lay)
            max_e = max(energy_counts.values(), default=1)
            for lvl in ENERGY_LEVELS:
                count = energy_counts.get(lvl, 0)
                color = ENERGY_COLORS.get(lvl, _C.ACCENT)
                self._bar_row(lay, lvl, count, total, max_e, color)
            for lvl, count in sorted(energy_counts.items()):
                if lvl not in ENERGY_LEVELS:
                    self._bar_row(lay, f"{lvl} (legacy)", count, total, max_e, _C.FG2)

        # Rating distribution
        if rating_counts:
            self._section("RATING DISTRIBUTION", lay)
            max_r = max(rating_counts.values(), default=1)
            for r in sorted(RATINGS, reverse=True):
                count = rating_counts.get(r, 0)
                self._bar_row(lay, RATING_LABELS[r], count, total, max_r, _C.ACCENT)

        # Top comment tags
        if tag_counts:
            self._section("TOP COMMENT TAGS", lay)
            top = sorted(tag_counts.items(), key=lambda x: -x[1])[:20]
            max_t = top[0][1] if top else 1
            for tag, count in top:
                self._bar_row(lay, tag, count, total, max_t, "#3498db")

        lay.addStretch()

    @staticmethod
    def _section(title: str, lay: QVBoxLayout):
        lbl = QLabel(title)
        lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_C.FG2}; margin-top: 6px;")
        lay.addWidget(lbl)

    @staticmethod
    def _bar_row(lay: QVBoxLayout, label: str, count: int, total: int,
                 max_val: int, color: str):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(140)
        lbl.setFont(QFont("Arial", 9))
        row.addWidget(lbl)
        bar = QProgressBar()
        bar.setRange(0, max(max_val, 1))
        bar.setValue(count)
        pct = f"{count / total * 100:.0f}%" if total else "0%"
        bar.setFormat(f" {count}  ({pct})")
        bar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        bar.setMinimumHeight(22)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {_C.BG_MEDIUM}; border-radius: 3px;
                color: {_C.FG}; font-size: 9px;
            }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}
        """)
        row.addWidget(bar, 1)
        lay.addLayout(row)


# ─── Vocabulary Editor Dialog ─────────────────────────────────────────────────

class VocabEditorDialog(QDialog):
    """Edit energy levels and comment tag categories. Cancel-safe."""

    vocab_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag Vocabulary Editor")
        self.resize(720, 680)
        self.setStyleSheet(_stylesheet())

        # Deep-copy working state so Cancel truly discards
        self._levels = list(ENERGY_LEVELS)
        self._colors = dict(ENERGY_COLORS)
        self._cats   = list(COMMENT_TAGS.keys())
        self._tags   = {k: list(v) for k, v in COMMENT_TAGS.items()}
        self._meta   = dict(TAG_META)

        self._init_ui()
        self._render()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        title = QLabel("🏷️  Tag Vocabulary Editor")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        note = QLabel("Changes are not applied until you click Save & Apply.")
        note.setFont(QFont("Arial", 9))
        note.setStyleSheet(f"color: {_C.FG2};")
        lay.addWidget(note)

        tb = QHBoxLayout()
        for text, slot in [
            ("📂 Load Pack…",    self._load_pack),
            ("💾 Export Pack…",  self._export_pack),
            ("ℹ️ Pack Info…",     self._edit_meta),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            tb.addWidget(b)
        tb.addStretch()
        lay.addLayout(tb)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setSpacing(10)
        scroll.setWidget(self._body)
        lay.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        save_btn = QPushButton("✅  Save & Apply")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C.ACCENT}; color: #fff;
                border-radius: 4px; padding: 8px 20px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {_C.ACCENT_HI}; }}
        """)
        save_btn.clicked.connect(self._save)
        bottom.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        lay.addLayout(bottom)

    def _render(self):
        """Rebuild the scrollable body from working state."""
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Energy levels
        hdr = QHBoxLayout()
        sec = QLabel("ENERGY LEVELS")
        sec.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        sec.setStyleSheet(f"color: {_C.ACCENT};")
        hdr.addWidget(sec)
        hdr.addStretch()
        add_b = QPushButton("+ Add Level")
        add_b.clicked.connect(self._add_level)
        hdr.addWidget(add_b)
        hdr_w = QWidget()
        hdr_w.setLayout(hdr)
        self._body_lay.addWidget(hdr_w)

        for i, lvl in enumerate(self._levels):
            self._body_lay.addWidget(self._level_row(i, lvl))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_C.BG_LIGHT};")
        self._body_lay.addWidget(sep)

        # Comment categories
        hdr2 = QHBoxLayout()
        sec2 = QLabel("COMMENT CATEGORIES & TAGS")
        sec2.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        sec2.setStyleSheet(f"color: {_C.ACCENT};")
        hdr2.addWidget(sec2)
        hdr2.addStretch()
        add_cat = QPushButton("+ Add Category")
        add_cat.clicked.connect(self._add_category)
        hdr2.addWidget(add_cat)
        hdr2_w = QWidget()
        hdr2_w.setLayout(hdr2)
        self._body_lay.addWidget(hdr2_w)

        for ci, cat in enumerate(self._cats):
            self._body_lay.addWidget(self._category_block(ci, cat))

        self._body_lay.addStretch()

    # ── Row builders ──────────────────────────────────────────────────────────

    def _level_row(self, i: int, lvl: str) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"background-color: {_C.BG_MEDIUM}; border-radius: 4px;")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 6, 8, 6)

        swatch = QPushButton()
        swatch.setFixedSize(24, 24)
        col = self._colors.get(lvl, "#888888")
        swatch.setStyleSheet(
            f"background-color: {col}; border-radius: 3px; padding: 0;")
        swatch.setToolTip("Change colour")
        swatch.clicked.connect(lambda _, l=lvl: self._pick_color(l))
        h.addWidget(swatch)

        h.addWidget(QLabel(lvl), 1)

        for text, slot in [
            ("▲", lambda _, idx=i: self._move_level(idx, -1)),
            ("▼", lambda _, idx=i: self._move_level(idx, +1)),
        ]:
            b = QPushButton(text)
            b.setFixedSize(28, 28)
            b.clicked.connect(slot)
            h.addWidget(b)

        ren = QPushButton("Rename")
        ren.clicked.connect(lambda _, idx=i: self._rename_level(idx))
        h.addWidget(ren)

        del_b = QPushButton("✕")
        del_b.setFixedSize(28, 28)
        del_b.setStyleSheet("QPushButton { color: #e74c3c; }")
        del_b.clicked.connect(lambda _, idx=i: self._delete_level(idx))
        h.addWidget(del_b)
        return row

    def _category_block(self, ci: int, cat: str) -> QWidget:
        block = QFrame()
        block.setStyleSheet(
            f"background-color: {_C.BG_DARK}; border-radius: 4px;")
        v = QVBoxLayout(block)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)

        hdr = QHBoxLayout()
        for text, slot in [
            ("▲", lambda _, idx=ci: self._move_category(idx, -1)),
            ("▼", lambda _, idx=ci: self._move_category(idx, +1)),
        ]:
            b = QPushButton(text)
            b.setFixedSize(26, 26)
            b.clicked.connect(slot)
            hdr.addWidget(b)
        clbl = QLabel(cat)
        clbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        clbl.setStyleSheet(f"color: {_C.ACCENT};")
        hdr.addWidget(clbl)
        hdr.addStretch()
        ren = QPushButton("Rename")
        ren.clicked.connect(lambda _, idx=ci: self._rename_category(idx))
        hdr.addWidget(ren)
        del_b = QPushButton("✕ Delete")
        del_b.setStyleSheet("QPushButton { color: #e74c3c; }")
        del_b.clicked.connect(lambda _, idx=ci: self._delete_category(idx))
        hdr.addWidget(del_b)
        v.addLayout(hdr)

        inner = QFrame()
        inner.setStyleSheet(
            f"background-color: {_C.BG_MEDIUM}; border-radius: 3px;")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(8, 6, 8, 6)
        iv.setSpacing(2)

        tags = self._tags.get(cat, [])
        if not tags:
            no_t = QLabel("(no tags yet)")
            no_t.setStyleSheet(f"color: {_C.FG2}; font-style: italic;")
            iv.addWidget(no_t)
        for ti, tag in enumerate(tags):
            iv.addWidget(self._tag_row(cat, ti, tag))

        add_tag = QPushButton("+ Add tag")
        add_tag.clicked.connect(lambda _, c=cat: self._add_tag(c))
        iv.addWidget(add_tag)
        v.addWidget(inner)
        return block

    def _tag_row(self, cat: str, ti: int, tag: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        for text, slot in [
            ("▲", lambda _, c=cat, idx=ti: self._move_tag(c, idx, -1)),
            ("▼", lambda _, c=cat, idx=ti: self._move_tag(c, idx, +1)),
        ]:
            b = QPushButton(text)
            b.setFixedSize(24, 24)
            b.clicked.connect(slot)
            h.addWidget(b)
        h.addWidget(QLabel(tag), 1)
        ren = QPushButton("Rename")
        ren.setFixedHeight(24)
        ren.clicked.connect(lambda _, c=cat, idx=ti: self._rename_tag(c, idx))
        h.addWidget(ren)
        del_b = QPushButton("✕")
        del_b.setFixedSize(24, 24)
        del_b.setStyleSheet("QPushButton { color: #e74c3c; }")
        del_b.clicked.connect(lambda _, c=cat, idx=ti: self._delete_tag(c, idx))
        h.addWidget(del_b)
        return row

    # ── Energy level mutations ────────────────────────────────────────────────

    def _move_level(self, i: int, delta: int):
        j = i + delta
        if 0 <= j < len(self._levels):
            self._levels[i], self._levels[j] = self._levels[j], self._levels[i]
            self._render()

    def _pick_color(self, lvl: str):
        cur = self._colors.get(lvl, "#888888")
        col = QColorDialog.getColor(QColor(cur), self, f"Colour for {lvl}")
        if col.isValid():
            self._colors[lvl] = col.name()
            self._render()

    def _rename_level(self, i: int):
        old = self._levels[i]
        new, ok = QInputDialog.getText(self, "Rename energy level",
                                        f"Rename '{old}' to:", text=old)
        if not ok:
            return
        new = normalize_tag_name(new)
        if not new or new == old:
            return
        if new in self._levels:
            QMessageBox.warning(self, "Duplicate",
                                 f"Energy level '{new}' already exists.")
            return
        self._levels[i] = new
        if old in self._colors:
            self._colors[new] = self._colors.pop(old)
        self._render()

    def _delete_level(self, i: int):
        lvl = self._levels[i]
        if QMessageBox.question(
                self, "Delete energy level",
                f"Delete '{lvl}'?\n\nExisting tracks tagged with this level will "
                "show it as a legacy entry until cleared.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        del self._levels[i]
        self._colors.pop(lvl, None)
        self._render()

    def _add_level(self):
        new, ok = QInputDialog.getText(self, "Add energy level", "Level name:")
        if not ok:
            return
        new = normalize_tag_name(new)
        if not new:
            return
        if new in self._levels:
            QMessageBox.warning(self, "Duplicate",
                                 f"Energy level '{new}' already exists.")
            return
        self._levels.append(new)
        self._colors[new] = DEFAULT_ENERGY_COLORS.get(new, _C.ACCENT)
        self._render()

    # ── Category mutations ────────────────────────────────────────────────────

    def _move_category(self, ci: int, delta: int):
        j = ci + delta
        if 0 <= j < len(self._cats):
            self._cats[ci], self._cats[j] = self._cats[j], self._cats[ci]
            self._render()

    def _rename_category(self, ci: int):
        old = self._cats[ci]
        new, ok = QInputDialog.getText(self, "Rename category",
                                        f"Rename '{old}' to:", text=old)
        if not ok:
            return
        new = new.strip()
        if not new or new == old:
            return
        if new in self._cats:
            QMessageBox.warning(self, "Duplicate",
                                 f"Category '{new}' already exists.")
            return
        self._cats[ci] = new
        self._tags[new] = self._tags.pop(old, [])
        self._render()

    def _delete_category(self, ci: int):
        cat = self._cats[ci]
        n = len(self._tags.get(cat, []))
        if QMessageBox.question(
                self, "Delete category",
                f"Delete category '{cat}' and its {n} tag(s)?\n\n"
                "Existing tracks tagged with these will show them as legacy entries.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        del self._cats[ci]
        self._tags.pop(cat, None)
        self._render()

    def _add_category(self):
        new, ok = QInputDialog.getText(self, "Add category", "Category name:")
        if not ok:
            return
        new = new.strip()
        if not new:
            return
        if new in self._cats:
            QMessageBox.warning(self, "Duplicate",
                                 f"Category '{new}' already exists.")
            return
        self._cats.append(new)
        self._tags[new] = []
        self._render()

    # ── Tag mutations ─────────────────────────────────────────────────────────

    def _move_tag(self, cat: str, ti: int, delta: int):
        tags = self._tags.get(cat, [])
        j = ti + delta
        if 0 <= j < len(tags):
            tags[ti], tags[j] = tags[j], tags[ti]
            self._render()

    def _rename_tag(self, cat: str, ti: int):
        tags = self._tags.get(cat, [])
        old = tags[ti]
        new, ok = QInputDialog.getText(self, "Rename tag",
                                        f"Rename '{old}' to:", text=old)
        if not ok:
            return
        new = normalize_tag_name(new)
        if not new or new == old:
            return
        if new in tags:
            QMessageBox.warning(self, "Duplicate",
                                 f"Tag '{new}' already exists in '{cat}'.")
            return
        tags[ti] = new
        self._render()

    def _delete_tag(self, cat: str, ti: int):
        tags = self._tags.get(cat, [])
        tag = tags[ti]
        if QMessageBox.question(
                self, "Delete tag",
                f"Delete '{tag}' from '{cat}'?\n\n"
                "Existing tracks with this tag will show it as a legacy entry.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        del tags[ti]
        self._render()

    def _add_tag(self, cat: str):
        new, ok = QInputDialog.getText(self, "Add tag",
                                        f"New tag in '{cat}':")
        if not ok:
            return
        new = normalize_tag_name(new)
        if not new:
            return
        tags = self._tags.setdefault(cat, [])
        if new in tags:
            QMessageBox.warning(self, "Duplicate",
                                 f"Tag '{new}' already exists in '{cat}'.")
            return
        for other_cat, other_tags in self._tags.items():
            if other_cat != cat and new in other_tags:
                if QMessageBox.question(
                        self, "Duplicate across categories",
                        f"'{new}' already exists in '{other_cat}'. Tags share a "
                        "flat namespace in the file — adding it here as well may "
                        "cause confusion. Add anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) != QMessageBox.StandardButton.Yes:
                    return
                break
        tags.append(new)
        self._render()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._levels:
            QMessageBox.warning(self, "Validation",
                                 "At least one energy level is required.")
            return
        ENERGY_LEVELS[:] = list(self._levels)
        ENERGY_COLORS.clear()
        for lv in ENERGY_LEVELS:
            ENERGY_COLORS[lv] = self._colors.get(
                lv, DEFAULT_ENERGY_COLORS.get(lv, _C.ACCENT))
        COMMENT_TAGS.clear()
        for cat in self._cats:
            COMMENT_TAGS[cat] = list(self._tags.get(cat, []))
        TAG_META.clear()
        TAG_META.update(self._meta)
        save_tag_config()
        self.vocab_saved.emit()
        self.accept()

    # ── Pack load / export ────────────────────────────────────────────────────

    def _current_state(self) -> dict:
        return {
            "energy_levels": list(self._levels),
            "energy_colors": dict(self._colors),
            "comment_tags":  {k: list(v) for k, v in self._tags.items()},
            "_meta":         dict(self._meta),
        }

    def _apply_state(self, state: dict):
        self._levels = list(state["energy_levels"])
        self._colors = dict(state["energy_colors"])
        self._cats   = list(state["comment_tags"].keys())
        self._tags   = {k: list(v) for k, v in state["comment_tags"].items()}
        self._meta   = dict(state.get("_meta", {}))
        self._render()

    def _load_pack(self):
        presets = list_bundled_presets()
        dlg = QDialog(self)
        dlg.setWindowTitle("Load tag pack")
        dlg.resize(500, 420)
        dlg.setStyleSheet(_stylesheet())
        lay = QVBoxLayout(dlg)

        ttl = QLabel("LOAD A TAG PACK")
        ttl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        lay.addWidget(ttl)
        note = QLabel("Pick a bundled preset or browse to a JSON file.")
        note.setStyleSheet(f"color: {_C.FG2}; font-style: italic;")
        lay.addWidget(note)

        if presets:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; }")
            body = QWidget()
            bl = QVBoxLayout(body)
            bl.setSpacing(6)
            for path, meta in presets:
                name = meta.get("name") or path.stem
                desc = meta.get("description") or ""
                if len(desc) > 140:
                    desc = desc[:137] + "…"
                card = QFrame()
                card.setStyleSheet(
                    f"background-color: {_C.BG_MEDIUM}; border-radius: 4px;")
                cl = QVBoxLayout(card)
                cl.setContentsMargins(10, 8, 10, 8)
                n_lbl = QLabel(name)
                n_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
                cl.addWidget(n_lbl)
                if desc:
                    d = QLabel(desc)
                    d.setStyleSheet(f"color: {_C.FG2}; font-size: 9px;")
                    d.setWordWrap(True)
                    cl.addWidget(d)
                btns = QHBoxLayout()
                for mode_text, mode in [("Replace…", "replace"), ("Merge", "merge")]:
                    b = QPushButton(mode_text)
                    b.clicked.connect(
                        lambda _, p=path, m=mode, picker=dlg:
                        self._load_pack_from_file(p, m, picker))
                    btns.addWidget(b)
                btns.addStretch()
                cl.addLayout(btns)
                bl.addWidget(card)
            bl.addStretch()
            scroll.setWidget(body)
            lay.addWidget(scroll, 1)
        else:
            no_p = QLabel("(No bundled presets found in presets/.)")
            no_p.setStyleSheet(f"color: {_C.FG2}; font-style: italic;")
            lay.addWidget(no_p)
            lay.addStretch()

        bottom = QHBoxLayout()
        browse = QPushButton("📂 Browse for file…")
        browse.clicked.connect(lambda: self._browse_pack(dlg))
        bottom.addWidget(browse)
        bottom.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        bottom.addWidget(cancel)
        lay.addLayout(bottom)
        dlg.exec()

    def _browse_pack(self, picker: QDialog):
        path, _ = QFileDialog.getOpenFileName(
            picker, "Select a tag pack JSON file",
            filter="Tag pack JSON (*.json);;All files (*.*)")
        if not path:
            return
        ans = QMessageBox.question(
            picker, "Apply pack",
            "Yes = Replace your current vocabulary\n"
            "No  = Merge into your current vocabulary",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Cancel:
            return
        mode = "replace" if ans == QMessageBox.StandardButton.Yes else "merge"
        self._load_pack_from_file(Path(path), mode, picker)

    def _load_pack_from_file(self, path: Path, mode: str, picker: QDialog):
        clean, errors, warnings = read_pack_file(path)
        if errors:
            QMessageBox.critical(picker, "Could not load pack", "\n".join(errors))
            return
        if not (clean["energy_levels"] or clean["comment_tags"]):
            QMessageBox.critical(picker, "Could not load pack",
                                  "The file contained no energy levels or tags.")
            return
        new_state, summary, apply_warnings = apply_pack(
            self._current_state(), clean, mode)
        meta_name = clean.get("_meta", {}).get("name") or path.stem
        bits = []
        if mode == "replace":
            bits.append(
                f"Replace with '{meta_name}': "
                f"{len(new_state['energy_levels'])} levels, "
                f"{sum(len(v) for v in new_state['comment_tags'].values())} tags "
                f"across {len(new_state['comment_tags'])} categories.")
        else:
            bits.append(
                f"Merge '{meta_name}': adding {summary['levels_added']} energy "
                f"level(s), {summary['categories_added']} new categor(y/ies), "
                f"{summary['tags_added']} new tag(s).")
        for w in warnings + apply_warnings:
            bits.append(f"⚠ {w}")
        bits.append("\nApply now? (Save & Apply still required to persist.)")
        if QMessageBox.question(
                picker, "Confirm pack", "\n".join(bits),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        ) != QMessageBox.StandardButton.Ok:
            return
        self._apply_state(new_state)
        picker.accept()

    def _export_pack(self):
        if not self._levels and not self._tags:
            QMessageBox.information(self, "Nothing to export",
                                     "Add some energy levels or tags first.")
            return
        suggested = (self._meta.get("name") or "my-tag-pack")
        suggested = (re.sub(r'[^a-zA-Z0-9]+', '-', suggested)
                     .strip('-').lower() or "tag-pack")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export tag pack", f"{suggested}.json",
            "Tag pack JSON (*.json)")
        if not path:
            return
        data: dict = {}
        if self._meta:
            data["_meta"] = dict(self._meta)
        data["energy_levels"] = list(self._levels)
        data["energy_colors"]  = {k: self._colors.get(k, "#888888")
                                   for k in self._levels}
        data["comment_tags"]   = {k: list(self._tags.get(k, []))
                                   for k in self._cats}
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')
        except OSError as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _edit_meta(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Pack Info")
        dlg.resize(460, 320)
        dlg.setStyleSheet(_stylesheet())
        lay = QVBoxLayout(dlg)

        ttl = QLabel("PACK INFO")
        ttl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        lay.addWidget(ttl)
        note = QLabel("Optional — describes the pack when you export or share it.")
        note.setStyleSheet(f"color: {_C.FG2}; font-style: italic;")
        lay.addWidget(note)

        entries: dict = {}
        for key, label, multiline in [
            ("name",        "Pack name",       False),
            ("author",      "Author / handle", False),
            ("version",     "Version",         False),
            ("description", "Description",     True),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(120)
            lbl.setStyleSheet(f"color: {_C.FG2};")
            row.addWidget(lbl)
            if multiline:
                w = QTextEdit()
                w.setFixedHeight(72)
                w.setPlainText(self._meta.get(key, ""))
                w.setStyleSheet(
                    f"background-color: {_C.BG_MEDIUM}; color: {_C.FG};")
            else:
                w = QLineEdit(self._meta.get(key, ""))
                w.setStyleSheet(
                    f"background-color: {_C.BG_MEDIUM}; color: {_C.FG};")
            row.addWidget(w)
            entries[key] = (multiline, w)
            lay.addLayout(row)

        def commit():
            new_meta: dict = {}
            for k, (ml, w) in entries.items():
                v = w.toPlainText().strip() if ml else w.text().strip()
                if v:
                    new_meta[k] = v
            self._meta = new_meta
            dlg.accept()

        bottom = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_C.ACCENT}; color: #fff; }}")
        ok_btn.clicked.connect(commit)
        bottom.addStretch()
        bottom.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        bottom.addWidget(cancel_btn)
        lay.addLayout(bottom)
        dlg.exec()


# ─── WAV Converter Dialog ─────────────────────────────────────────────────────

class WavConverterDialog(QDialog):
    """Convert WAV files in the current folder to FLAC, AIFF, or MP3."""

    files_changed = pyqtSignal()
    _progress_sig = pyqtSignal(str)   # thread-safe progress update
    _done_sig     = pyqtSignal(str)   # thread-safe completion

    def __init__(self, files: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Convert WAV Files")
        self.resize(480, 360)
        self.setStyleSheet(_stylesheet())
        self._wav_files = [f for f in files if f.suffix.lower() == '.wav']
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        title = QLabel("🔄  Convert WAV Files")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        count_lbl = QLabel(
            f"{len(self._wav_files)} WAV file(s) found in current folder.")
        count_lbl.setStyleSheet(f"color: {_C.FG2};")
        lay.addWidget(count_lbl)

        fmt_hdr = QLabel("TARGET FORMAT")
        fmt_hdr.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        fmt_hdr.setStyleSheet(f"color: {_C.FG2};")
        lay.addWidget(fmt_hdr)

        self._fmt_group = QButtonGroup(self)
        for fmt, label in [
            ('flac', "FLAC — lossless, compact, full tag support (Recommended)"),
            ('aiff', "AIFF — lossless, full tag support, large files"),
            ('mp3',  "MP3 — 320 kbps, smallest files, lossy"),
        ]:
            rb = QRadioButton(label)
            if fmt == 'flac':
                rb.setChecked(True)
            rb.setProperty("fmt", fmt)
            self._fmt_group.addButton(rb)
            lay.addWidget(rb)

        self._del_check = QCheckBox(
            "Delete original WAV files after conversion")
        lay.addWidget(self._del_check)

        self._progress_lbl = QLabel("")
        self._progress_lbl.setStyleSheet(f"color: {_C.FG2};")
        lay.addWidget(self._progress_lbl)

        # Connect thread-safe signals to UI slots
        self._progress_sig.connect(self._progress_lbl.setText)
        self._done_sig.connect(self._on_done)

        lay.addStretch()

        buttons = QHBoxLayout()
        self._convert_btn = QPushButton("Convert")
        self._convert_btn.setMinimumHeight(38)
        self._convert_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_C.ACCENT}; color: #fff;
                border-radius: 4px; padding: 8px 20px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {_C.ACCENT_HI}; }}
            QPushButton:disabled {{
                background-color: {_C.BG_LIGHT}; color: {_C.FG2};
            }}
        """)
        self._convert_btn.clicked.connect(self._do_convert)
        if not self._wav_files:
            self._convert_btn.setEnabled(False)
        buttons.addWidget(self._convert_btn)
        buttons.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        lay.addLayout(buttons)

    def _get_fmt(self) -> str:
        for btn in self._fmt_group.buttons():
            if btn.isChecked():
                return btn.property("fmt")
        return 'flac'

    def _do_convert(self):
        try:
            from pydub import AudioSegment  # noqa: PLC0415
        except ImportError:
            QMessageBox.critical(
                self, "Missing dependency",
                "pydub is required for WAV conversion.\n"
                "Install it with:  pip install pydub")
            return

        fmt = self._get_fmt()
        delete = self._del_check.isChecked()
        wav_files = list(self._wav_files)
        self._convert_btn.setEnabled(False)
        self._convert_btn.setText("Converting…")

        def _worker():
            from pydub import AudioSegment  # noqa: PLC0415 (thread needs own import)
            ext_map = {'flac': '.flac', 'aiff': '.aiff', 'mp3': '.mp3'}
            converted = skipped = failed = 0
            total = len(wav_files)
            for i, wav_path in enumerate(wav_files):
                self._progress_sig.emit(f"Converting {i + 1} / {total}…")
                out_path = wav_path.with_suffix(ext_map[fmt])
                if out_path.exists():
                    skipped += 1
                    continue
                try:
                    seg = AudioSegment.from_wav(str(wav_path))
                    if fmt == 'mp3':
                        seg.export(str(out_path), format='mp3', bitrate='320k')
                    elif fmt == 'flac':
                        seg.export(str(out_path), format='flac')
                    else:
                        seg.export(str(out_path), format='aiff')
                    if fmt == 'flac':
                        _copy_tags_to_flac(wav_path, out_path)
                    else:
                        _copy_id3_tags(wav_path, out_path)
                    converted += 1
                    if delete:
                        try:
                            wav_path.unlink()
                        except Exception:
                            pass
                except Exception:
                    failed += 1
                    if out_path.exists():
                        try:
                            out_path.unlink()
                        except Exception:
                            pass
            parts = []
            if converted:
                parts.append(f"{converted} converted")
            if skipped:
                parts.append(f"{skipped} skipped")
            if failed:
                parts.append(f"{failed} failed")
            self._done_sig.emit(", ".join(parts) or "Nothing to convert")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_done(self, summary: str):
        self._progress_lbl.setText(f"✓ {summary}")
        self._convert_btn.setEnabled(True)
        self._convert_btn.setText("Convert")
        self.files_changed.emit()


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

        # Tool buttons row
        tool_row = QHBoxLayout()
        tool_row.setContentsMargins(4, 4, 4, 4)
        tool_row.setSpacing(4)
        for label, slot in [
            ("📊 Stats",   self._show_stats),
            ("🏷️ Tags",    self._show_vocab_editor),
            ("🔄 Convert", self._show_converter),
        ]:
            b = QPushButton(label)
            b.setMinimumHeight(32)
            b.setFont(QFont("Arial", 9))
            b.clicked.connect(slot)
            tool_row.addWidget(b)
        tool_w = QWidget()
        tool_w.setStyleSheet(f"background-color: {_C.BG_MEDIUM};")
        tool_w.setLayout(tool_row)
        sb_lay.addWidget(tool_w)

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
        a.setShortcut("Ctrl+S")
        a.triggered.connect(self._editor._save)

        tm = mb.addMenu("Tools")
        a = tm.addAction("📊 Statistics…")
        a.triggered.connect(self._show_stats)
        a = tm.addAction("🏷️ Tag Vocabulary…")
        a.triggered.connect(self._show_vocab_editor)
        a = tm.addAction("🔄 Convert WAV Files…")
        a.triggered.connect(self._show_converter)

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

    def _show_stats(self):
        files = list(self._tracks._rows.keys())
        if not files:
            QMessageBox.information(self, "Stats", "No tracks loaded.")
            return
        dlg = StatsDialog(files, self)
        dlg.exec()

    def _show_vocab_editor(self):
        dlg = VocabEditorDialog(self)
        dlg.vocab_saved.connect(self._on_vocab_saved)
        dlg.exec()

    def _show_converter(self):
        files = list(self._tracks._rows.keys())
        wav_files = [f for f in files if f.suffix.lower() == '.wav']
        if not wav_files:
            QMessageBox.information(self, "Convert WAVs",
                                     "No WAV files found in the current folder.")
            return
        if not _has_ffmpeg():
            QMessageBox.warning(self, "Convert WAVs",
                                 "ffmpeg not found — it is required for conversion.\n"
                                 "Install ffmpeg and ensure it is on your PATH.")
            return
        dlg = WavConverterDialog(files, self)
        dlg.files_changed.connect(lambda: self._load_dir(self._dir))
        dlg.exec()

    def _on_vocab_saved(self):
        self._editor.rebuild_vocab()
        self._load_dir(self._dir)

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
