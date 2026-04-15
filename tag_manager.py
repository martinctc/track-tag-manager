#!/usr/bin/env python3
"""
DJ Tag Manager — Little Data Lotta Love system
Writes Genre (energy), Rating, and Comment tags directly into audio files.
Supports MP3, WAV, AIFF.

Keys:  Space = play/pause   S = save   Enter = save+next   Up/Down = navigate
"""

import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import time
import pygame
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.aiff import AIFF
from mutagen.id3 import TCON, COMM, POPM

# ─── Config ────────────────────────────────────────────────────────────────────

DEFAULT_DIR = Path(__file__).parent
SUPPORTED   = {'.mp3', '.wav', '.aif', '.aiff'}

ENERGY_LEVELS = ["Start", "Build", "Peak", "Sustain", "Release"]
RATINGS       = [1, 3, 5]
RATING_LABELS = {1: "1★  Situational", 3: "3★  Reliable", 5: "5★  Essential"}

COMMENT_TAGS = {
    "Style":       ["House", "Disco", "Funk", "Pop", "Hip-Hop", "R&B",
                    "Latin", "Afro", "Electronic", "Soul",
                    "Arabic", "Desi", "East-Asian"],
    "Mood":        ["Happy", "Chill", "Sexy", "Dark", "Fun",
                    "Uplifting", "Nostalgic", "Emotional"],
    "Vibe":        ["Groovy", "Bouncy", "Driving", "Anthemic", "Melodic", "Classic",
                    "Punchy", "Deep", "Smooth", "Soulful", "Tropical", "Late-Night",
                    "Banging"],
    "Crowd":       ["Singalong", "Dancefloor", "Crowd-Pleaser", "Beach-Vibes"],
    "Vocals":      ["Vocals", "No-Vocals", "Rap"],
    "Instruments": ["Piano", "Guitar", "Horns", "Bass-Heavy", "Strings",
                    "Synth", "Percussion", "Organ"],
}

ENERGY_COLORS = {
    "Start":   "#2d8659",
    "Build":   "#2471a3",
    "Peak":    "#c0392b",
    "Sustain": "#7d3c98",
    "Release": "#d68910",
}

RATING_POPM = {1: 51, 3: 153, 5: 255}

def _popm_to_stars(val):
    if val == 0:
        return None
    closest = min(RATING_POPM.items(), key=lambda x: abs(x[1] - val))
    return closest[0] if abs(closest[1] - val) < 40 else None

# ─── Colours ───────────────────────────────────────────────────────────────────

BG     = "#1a1a1a"
BG2    = "#232323"
BG3    = "#2e2e2e"
FG     = "#e0e0e0"
FG2    = "#666666"
ACCENT = "#3fa89a"
SEL    = "#2a3a4a"

# ─── Tag I/O ───────────────────────────────────────────────────────────────────

def _open(path):
    ext = path.suffix.lower()
    if ext == '.mp3':              return MP3(path)
    if ext == '.wav':              return WAVE(path)
    if ext in ('.aif', '.aiff'):   return AIFF(path)
    return None

def read_tags(path):
    try:
        audio = _open(path)
        if audio is None:
            return {}
        t = audio.tags
        if t is None:
            return {'energy': None, 'rating': None, 'comments': set()}

        energy = None
        if 'TCON' in t and t['TCON'].text:
            v = str(t['TCON'].text[0])
            if v in ENERGY_LEVELS:
                energy = v

        comments = set()
        for k in t.keys():
            if k.startswith('COMM'):
                text = t[k].text[0] if t[k].text else ''
                comments = set(text.split())
                break

        rating = None
        for k in t.keys():
            if k.startswith('POPM'):
                rating = _popm_to_stars(t[k].rating)
                break

        return {'energy': energy, 'rating': rating, 'comments': comments}
    except Exception as e:
        return {'energy': None, 'rating': None, 'comments': set(), '_err': str(e)}

def write_tags(path, energy, rating, comments):
    try:
        audio = _open(path)
        if audio is None:
            return f"Unsupported format: {path.suffix}"
        if audio.tags is None:
            audio.add_tags()
        t = audio.tags

        if energy:
            t['TCON'] = TCON(encoding=3, text=[energy])
        elif 'TCON' in t:
            del t['TCON']

        for k in list(t.keys()):
            if k.startswith('COMM'):
                del t[k]
        if comments:
            t['COMM::eng'] = COMM(encoding=3, lang='eng', desc='',
                                   text=[' '.join(sorted(comments))])

        for k in list(t.keys()):
            if k.startswith('POPM'):
                del t[k]
        if rating and rating in RATING_POPM:
            t['POPM:no@email'] = POPM(email='no@email',
                                       rating=RATING_POPM[rating], count=0)
        audio.save()
        return None
    except Exception as e:
        return str(e)

# ─── App ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DJ Tag Manager")
        self.configure(bg=BG)
        self.geometry("1160x820")
        self.minsize(900, 640)

        self.music_dir   = DEFAULT_DIR
        self.files       = []
        self.idx         = 0
        self.tags        = {}
        self.unsaved     = False
        self.energy_btns = {}
        self.rating_btns = {}
        self.tag_btns    = {}

        # Player state
        self.p_state    = 'stopped'   # 'stopped' | 'playing' | 'paused'
        self.p_duration = 0.0
        self.p_seek_off = 0.0         # position (secs) at last play/seek
        self.p_t0       = 0.0         # time.time() when current segment started
        self._prog_job  = None

        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

        self._build()
        self._pick_folder(startup=True)
        self._reload_files()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=14, pady=(10, 0))
        tk.Label(hdr, text="DJ TAG MANAGER", bg=BG, fg=ACCENT,
                 font=('Helvetica', 14, 'bold')).pack(side='left')
        tk.Button(
            hdr, text="📁 Change Folder",
            bg=BG3, fg=FG, activebackground=BG3, activeforeground=FG,
            relief='flat', padx=10, pady=4, bd=0, highlightthickness=0,
            font=('Helvetica', 9), cursor='hand2',
            command=self._pick_folder,
        ).pack(side='right', padx=(8, 0))
        self.status_lbl = tk.Label(hdr, text="", bg=BG, fg=FG2,
                                    font=('Helvetica', 10))
        self.status_lbl.pack(side='right')

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True, padx=14, pady=10)
        self._build_list(body)
        self._build_editor(body)
        self._build_footer()

    def _build_list(self, parent):
        frame = tk.Frame(parent, bg=BG2, width=290)
        frame.pack(side='left', fill='y', padx=(0, 10))
        frame.pack_propagate(False)

        tk.Label(frame, text="TRACKS", bg=BG2, fg=FG2,
                 font=('Helvetica', 9, 'bold')).pack(anchor='w', padx=10, pady=(8, 4))

        inner = tk.Frame(frame, bg=BG2)
        inner.pack(fill='both', expand=True, padx=6, pady=(0, 6))

        sb = tk.Scrollbar(inner, bg=BG3, troughcolor=BG2, relief='flat')
        sb.pack(side='right', fill='y')

        self.listbox = tk.Listbox(
            inner, bg=BG2, fg=FG,
            selectbackground=SEL, selectforeground='white',
            relief='flat', borderwidth=0, highlightthickness=0,
            font=('Helvetica', 9), activestyle='none',
            yscrollcommand=sb.set, exportselection=False,
        )
        self.listbox.pack(side='left', fill='both', expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind('<<ListboxSelect>>', self._on_list_sel)

    def _build_editor(self, parent):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(side='left', fill='both', expand=True)

        self.track_lbl = tk.Label(outer, text="", bg=BG, fg=FG,
                                   font=('Helvetica', 11, 'bold'),
                                   wraplength=820, justify='left', anchor='w')
        self.track_lbl.pack(fill='x', pady=(0, 6))

        # ── Mini player ──────────────────────────────────────────────────────
        self._build_player(outer)

        # ── Scrollable tag editor ────────────────────────────────────────────
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        sf = tk.Frame(canvas, bg=BG)
        sf.bind('<Configure>',
                lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=sf, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        canvas.bind('<MouseWheel>',
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

        self._build_energy(sf)
        self._build_rating(sf)
        for cat, tags in COMMENT_TAGS.items():
            self._build_tag_group(sf, cat, tags)

    def _build_player(self, parent):
        bar = tk.Frame(parent, bg=BG2, padx=12, pady=8)
        bar.pack(fill='x', pady=(0, 8))

        # Play/Pause
        self.play_btn = tk.Button(
            bar, text="▶", width=2,
            bg=BG2, fg=FG, activebackground=BG3, activeforeground=FG,
            relief='flat', font=('Helvetica', 15), cursor='hand2',
            bd=0, highlightthickness=0,
            command=self._toggle_play,
        )
        self.play_btn.pack(side='left')

        # Stop
        tk.Button(
            bar, text="■", width=2,
            bg=BG2, fg=FG2, activebackground=BG3, activeforeground=FG,
            relief='flat', font=('Helvetica', 11), cursor='hand2',
            bd=0, highlightthickness=0,
            command=self._stop_player,
        ).pack(side='left', padx=(2, 10))

        # Current time
        self.time_lbl = tk.Label(bar, text="0:00", bg=BG2, fg=FG2,
                                  font=('Courier', 10), width=4, anchor='e')
        self.time_lbl.pack(side='left', padx=(0, 6))

        # Duration
        self.dur_lbl = tk.Label(bar, text="0:00", bg=BG2, fg=FG2,
                                 font=('Courier', 10), width=4, anchor='w')
        self.dur_lbl.pack(side='right', padx=(6, 0))

        # Volume
        self.vol_var = tk.DoubleVar(value=0.8)
        tk.Label(bar, text="🔊", bg=BG2, fg=FG2,
                 font=('Helvetica', 10)).pack(side='right', padx=(8, 0))
        vol_slider = tk.Scale(
            bar, from_=0, to=100, orient='horizontal',
            variable=self.vol_var, showvalue=False, length=80,
            bg=BG2, fg=FG, troughcolor=BG3, activebackground=ACCENT,
            highlightthickness=0, bd=0, sliderlength=12,
            command=self._set_volume,
        )
        vol_slider.set(80)
        vol_slider.pack(side='right')
        pygame.mixer.music.set_volume(0.8)

        # Scrubber
        self.prog_canvas = tk.Canvas(bar, bg=BG2, height=20,
                                      highlightthickness=0, cursor='hand2')
        self.prog_canvas.pack(side='left', fill='x', expand=True)
        self.prog_canvas.bind('<Button-1>', self._seek_click)
        self.prog_canvas.bind('<B1-Motion>', self._seek_click)
        self.prog_canvas.bind('<Configure>', lambda e: self._draw_progress(self._pos_fraction()))

    def _sec(self, parent, label):
        tk.Label(parent, text=label, bg=BG, fg=FG2,
                 font=('Helvetica', 9, 'bold')).pack(anchor='w', pady=(16, 5))

    def _build_energy(self, parent):
        self._sec(parent, "ENERGY")
        row = tk.Frame(parent, bg=BG)
        row.pack(anchor='w')
        for level in ENERGY_LEVELS:
            btn = tk.Button(
                row, text=level, bg=BG3, fg=FG2,
                relief='flat', padx=18, pady=9,
                font=('Helvetica', 10, 'bold'), cursor='hand2',
                activebackground=ENERGY_COLORS[level], activeforeground='white',
                bd=0, highlightthickness=0,
                command=lambda lv=level: self._click_energy(lv),
            )
            btn.pack(side='left', padx=(0, 6))
            self.energy_btns[level] = btn

    def _build_rating(self, parent):
        self._sec(parent, "RATING")
        row = tk.Frame(parent, bg=BG)
        row.pack(anchor='w')
        for r in RATINGS:
            btn = tk.Button(
                row, text=RATING_LABELS[r], bg=BG3, fg=FG2,
                relief='flat', padx=16, pady=9,
                font=('Helvetica', 10), cursor='hand2',
                activebackground=ACCENT, activeforeground='white',
                bd=0, highlightthickness=0,
                command=lambda rv=r: self._click_rating(rv),
            )
            btn.pack(side='left', padx=(0, 6))
            self.rating_btns[r] = btn

    def _build_tag_group(self, parent, category, tags):
        self._sec(parent, category.upper())
        row = tk.Frame(parent, bg=BG)
        row.pack(anchor='w')
        for i, tag in enumerate(tags):
            btn = tk.Button(
                row, text=tag, bg=BG3, fg=FG,
                relief='flat', padx=12, pady=7,
                font=('Helvetica', 10), cursor='hand2',
                activebackground=ACCENT, activeforeground='white',
                bd=0, highlightthickness=0,
                command=lambda tg=tag: self._click_tag(tg),
            )
            btn.pack(side='left', padx=(0, 5), pady=(0, 4))
            self.tag_btns[tag] = btn
            if (i + 1) % 6 == 0 and (i + 1) < len(tags):
                row = tk.Frame(parent, bg=BG)
                row.pack(anchor='w')

    def _build_footer(self):
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill='x', padx=14, pady=(0, 12))

        self.save_btn = tk.Button(
            footer, text="SAVE  [S]",
            bg=ACCENT, fg='white',
            activebackground="#4bbfae", activeforeground='white',
            relief='flat', padx=22, pady=10, bd=0, highlightthickness=0,
            font=('Helvetica', 11, 'bold'), cursor='hand2',
            command=self._save,
        )
        self.save_btn.pack(side='left')

        for label, cmd in [("↑ PREV", self._prev),
                           ("NEXT ↓", self._next),
                           ("SAVE + NEXT  [↵]", self._save_next)]:
            tk.Button(footer, text=label, bg=BG3, fg=FG,
                      relief='flat', padx=16, pady=10, bd=0, highlightthickness=0,
                      font=('Helvetica', 10), cursor='hand2',
                      command=cmd).pack(side='left', padx=(6, 0))

        self.msg_lbl = tk.Label(footer, text="", bg=BG, fg=FG2,
                                 font=('Helvetica', 10, 'italic'))
        self.msg_lbl.pack(side='left', padx=14)

    # ── Player ─────────────────────────────────────────────────────────────────

    def _get_duration(self, path):
        try:
            audio = _open(path)
            return float(audio.info.length) if audio else 0.0
        except Exception:
            return 0.0

    def _fmt(self, secs):
        secs = max(0, int(secs))
        return f"{secs // 60}:{secs % 60:02d}"

    def _pos_fraction(self):
        if self.p_duration <= 0:
            return 0.0
        pos = self._current_pos()
        return max(0.0, min(1.0, pos / self.p_duration))

    def _current_pos(self):
        if self.p_state == 'playing':
            return self.p_seek_off + (time.time() - self.p_t0)
        return self.p_seek_off

    def _draw_progress(self, frac):
        c = self.prog_canvas
        c.delete('all')
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return
        mid = h // 2
        # Track line
        c.create_line(0, mid, w, mid, fill=BG3, width=4)
        # Filled portion
        filled = int(w * max(0.0, min(1.0, frac)))
        if filled > 0:
            c.create_line(0, mid, filled, mid, fill=ACCENT, width=4)
        # Playhead dot
        r = 6
        cx = max(r, min(w - r, filled))
        c.create_oval(cx - r, mid - r, cx + r, mid + r,
                      fill=ACCENT, outline=BG2, width=2)

    def _play_track(self, path):
        """Load and start playing a track from the beginning."""
        self._cancel_progress()
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            self.p_state    = 'playing'
            self.p_seek_off = 0.0
            self.p_t0       = time.time()
            self.p_duration = self._get_duration(path)
            self.play_btn.config(text="⏸")
            self.dur_lbl.config(text=self._fmt(self.p_duration))
            self.time_lbl.config(text="0:00")
            self._draw_progress(0)
            self._schedule_progress()
        except Exception as e:
            self.p_state = 'stopped'
            self.play_btn.config(text="▶")
            if path.suffix.lower() in ('.aif', '.aiff'):
                self._msg("AIFF playback not supported — tags still work fine", FG2)
            else:
                self._msg(f"Playback error: {e}", "#e74c3c")

    def _play_from(self, secs):
        """Seek to a position and play."""
        if not self.files:
            return
        path = self.files[self.idx]
        self._cancel_progress()
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play(start=float(secs))
        except Exception:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            secs = 0.0
        self.p_state    = 'playing'
        self.p_seek_off = float(secs)
        self.p_t0       = time.time()
        self.play_btn.config(text="⏸")
        self._schedule_progress()

    def _toggle_play(self):
        if self.p_state == 'playing':
            pygame.mixer.music.pause()
            self.p_seek_off = self._current_pos()
            self.p_state = 'paused'
            self.play_btn.config(text="▶")
            self._cancel_progress()
        elif self.p_state == 'paused':
            pygame.mixer.music.unpause()
            self.p_t0    = time.time()
            self.p_state = 'playing'
            self.play_btn.config(text="⏸")
            self._schedule_progress()
        else:
            # stopped — play from beginning
            if self.files:
                self._play_track(self.files[self.idx])

    def _stop_player(self):
        self._cancel_progress()
        pygame.mixer.music.stop()
        self.p_state    = 'stopped'
        self.p_seek_off = 0.0
        self.play_btn.config(text="▶")
        self.time_lbl.config(text="0:00")
        self._draw_progress(0)

    def _seek_click(self, event):
        if self.p_duration <= 0:
            return
        w = self.prog_canvas.winfo_width()
        if w < 2:
            return
        secs = max(0.0, min(1.0, event.x / w)) * self.p_duration
        self._play_from(secs)

    def _set_volume(self, val):
        pygame.mixer.music.set_volume(float(val) / 100.0)

    def _schedule_progress(self):
        self._cancel_progress()
        self._prog_job = self.after(200, self._update_progress)

    def _cancel_progress(self):
        if self._prog_job:
            self.after_cancel(self._prog_job)
            self._prog_job = None

    def _update_progress(self):
        if self.p_state != 'playing':
            return
        if not pygame.mixer.music.get_busy():
            # Track finished
            self.p_state    = 'stopped'
            self.p_seek_off = 0.0
            self.play_btn.config(text="▶")
            self._draw_progress(1.0)
            self.time_lbl.config(text=self._fmt(self.p_duration))
            return
        pos = self._current_pos()
        if self.p_duration > 0:
            pos = min(pos, self.p_duration)
        self.time_lbl.config(text=self._fmt(pos))
        self._draw_progress(self._pos_fraction())
        self._schedule_progress()

    # ── Data ───────────────────────────────────────────────────────────────────

    def _pick_folder(self, startup=False):
        chosen = filedialog.askdirectory(
            title="Select music folder",
            initialdir=str(self.music_dir),
        )
        if chosen:
            self.music_dir = Path(chosen)
            self.title(f"DJ Tag Manager — {self.music_dir.name}")
            self._stop_player()
            self._reload_files()
        elif startup:
            self.title(f"DJ Tag Manager — {self.music_dir.name}")

    def _reload_files(self):
        self.files = sorted(
            [f for f in self.music_dir.iterdir() if f.suffix.lower() in SUPPORTED],
            key=lambda f: f.name.lower(),
        )
        self.listbox.delete(0, 'end')
        for f in self.files:
            self.listbox.insert('end', f.name)
        self.status_lbl.config(text=f"{len(self.files)} tracks")
        if self.files:
            self._select(0)

    def _select(self, idx):
        if not self.files or not (0 <= idx < len(self.files)):
            return
        if self.unsaved:
            self._save()
        self.idx = idx
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.track_lbl.config(text=self.files[idx].name)
        self.tags = read_tags(self.files[idx])
        self.unsaved = False
        self._msg("")
        self._render()
        self._play_track(self.files[idx])

    def _render(self):
        energy   = self.tags.get('energy')
        rating   = self.tags.get('rating')
        comments = self.tags.get('comments', set())

        for lv, btn in self.energy_btns.items():
            btn.config(bg=ENERGY_COLORS[lv] if lv == energy else BG3,
                       fg='white' if lv == energy else FG2)

        for r, btn in self.rating_btns.items():
            btn.config(bg=ACCENT if r == rating else BG3,
                       fg='white' if r == rating else FG2)

        for tag, btn in self.tag_btns.items():
            on = tag in comments
            btn.config(bg=ACCENT if on else BG3,
                       fg='white' if on else FG)

    # ── Interactions ───────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.bind('<space>',  lambda e: self._toggle_play())
        self.bind('<s>',      lambda e: self._save())
        self.bind('<S>',      lambda e: self._save())
        self.bind('<Up>',     lambda e: self._prev())
        self.bind('<Down>',   lambda e: self._next())
        self.bind('<Return>', lambda e: self._save_next())

    def _on_list_sel(self, _):
        sel = self.listbox.curselection()
        if sel:
            self._select(sel[0])

    def _click_energy(self, level):
        self.tags['energy'] = None if self.tags.get('energy') == level else level
        self._dirty()
        self._render()

    def _click_rating(self, r):
        self.tags['rating'] = None if self.tags.get('rating') == r else r
        self._dirty()
        self._render()

    def _click_tag(self, tag):
        c = self.tags.setdefault('comments', set())
        c.discard(tag) if tag in c else c.add(tag)
        self._dirty()
        self._render()

    def _dirty(self):
        if not self.unsaved:
            self.unsaved = True
            self._msg("● unsaved", "#e67e22")

    def _msg(self, text, color=FG2):
        self.msg_lbl.config(text=text, fg=color)

    def _save(self):
        if not self.files:
            return
        path = self.files[self.idx]
        # Remember playback state so we can resume after saving
        was_playing = self.p_state == 'playing'
        was_paused  = self.p_state == 'paused'
        resume_pos  = self._current_pos() if was_playing else self.p_seek_off
        # Unload the file so pygame releases the file handle
        self._cancel_progress()
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        err = write_tags(
            path,
            self.tags.get('energy'),
            self.tags.get('rating'),
            self.tags.get('comments', set()),
        )
        if err:
            self._msg(f"Error: {err}", "#e74c3c")
        else:
            self.unsaved = False
            self._msg("✓ saved", ACCENT)
            self.after(2500, lambda: self._msg("") if not self.unsaved else None)
        # Resume playback from where we left off
        if was_playing:
            self._play_from(resume_pos)
        elif was_paused:
            try:
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play(start=float(resume_pos))
                pygame.mixer.music.pause()
            except Exception:
                pygame.mixer.music.load(str(path))
            self.p_state    = 'paused'
            self.p_seek_off = resume_pos
            self.play_btn.config(text="▶")

    def _prev(self):
        if self.idx > 0:
            self._select(self.idx - 1)

    def _next(self):
        if self.idx < len(self.files) - 1:
            self._select(self.idx + 1)

    def _save_next(self):
        self._save()
        self._next()

    def _on_close(self):
        self._cancel_progress()
        pygame.mixer.quit()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
