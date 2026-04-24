#!/usr/bin/env python3
"""
DJ Tag Manager — Little Data Lotta Love system
Writes Genre (energy), Rating, and Comment tags directly into audio files.
Supports MP3, WAV, AIFF, FLAC, M4A.

Keys:  Space = play/pause   S = save   Enter = save+next   Up/Down = navigate
"""

import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, colorchooser
from pathlib import Path
import json
import re
import sys
import time
import audioop
import shutil
import threading
import pygame
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.aiff import AIFF
from mutagen.flac import FLAC as FLACFile
from mutagen.mp4 import MP4
from mutagen.id3 import TCON, COMM, POPM
from pydub import AudioSegment

# ─── Config ────────────────────────────────────────────────────────────────────

DEFAULT_DIR = Path(__file__).parent
SUPPORTED   = {'.mp3', '.wav', '.aif', '.aiff', '.flac', '.m4a'}

RATINGS       = [1, 3, 5]
RATING_LABELS = {1: "1★  Situational", 3: "3★  Reliable", 5: "5★  Essential"}
RATING_COMMENT = {1: "1★", 3: "3★", 5: "5★"}
_RATING_COMMENTS = set(RATING_COMMENT.values())

# Default vocabulary — used as the fallback when tags.json is missing or invalid.
# Live values are loaded into ENERGY_LEVELS / COMMENT_TAGS / ENERGY_COLORS below
# and can be edited via the in-app Tags editor.
DEFAULT_ENERGY_LEVELS = ["Start", "Build", "Peak", "Sustain", "Release"]

DEFAULT_COMMENT_TAGS = {
    "Style":       ["House", "Disco", "Funk", "Pop", "Hip-Hop", "R&B",
                    "Latin", "Afro", "Electronic", "Soul",
                    "Arabic", "Desi", "East-Asian",
                    "Hardstyle", "Techno", "DnB", "Dubstep"],
    "Mood":        ["Happy", "Chill", "Sexy", "Dark", "Aggressive", "Fun",
                    "Uplifting", "Nostalgic", "Emotional", "Hypnotic"],
    "Vibe":        ["Groovy", "Bouncy", "Driving", "Anthemic", "Melodic", "Classic",
                    "Punchy", "Deep", "Smooth", "Soulful", "Tropical", "Late-Night",
                    "Banging"],
    "Crowd":       ["Singalong", "Dancefloor", "Crowd-Pleaser", "Beach-Vibes", "Cafe-Set", "Warehouse"],
    "Vocals":      ["Vocals", "No-Vocals", "Rap"],
    "Instruments": ["Piano", "Guitar", "Horns", "Bass-Heavy", "Strings",
                    "Synth", "Percussion", "Organ"],
}

DEFAULT_ENERGY_COLORS = {
    "Start":   "#2d8659",
    "Build":   "#2471a3",
    "Peak":    "#c0392b",
    "Sustain": "#7d3c98",
    "Release": "#d68910",
}

# Live (mutable) vocabulary — read by the rest of the app. Populated by load_tag_config().
ENERGY_LEVELS = list(DEFAULT_ENERGY_LEVELS)
COMMENT_TAGS  = {k: list(v) for k, v in DEFAULT_COMMENT_TAGS.items()}
ENERGY_COLORS = dict(DEFAULT_ENERGY_COLORS)
TAG_META      = {}  # optional: name / author / description / version for the active pack

TAG_CONFIG_PATH = DEFAULT_DIR / "tags.json"

# Reasonable limits — protect the GUI from hostile or accidentally huge packs.
# Each comment tag becomes a button; thousands would freeze the renderer.
MAX_PACK_FILE_BYTES   = 256 * 1024
MAX_ENERGY_LEVELS     = 20
MAX_CATEGORIES        = 30
MAX_TAGS_PER_CATEGORY = 100
MAX_TOTAL_TAGS        = 600
MAX_NAME_LEN          = 60
MAX_DESC_LEN          = 500
_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

# Reserved top-level keys (underscore-prefixed) for forward-compat metadata.
_META_KEY = "_meta"


def _resource_path(name):
    """Locate a bundled resource (preset, etc.) on disk.

    Works in source checkouts and is defensively forward-compatible with
    PyInstaller-style packaging via sys._MEIPASS. Returns the path even if
    the resource doesn't exist — callers should check .exists().
    """
    candidates = [DEFAULT_DIR / name]
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.insert(0, Path(meipass) / name)
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _is_valid_hex_color(s):
    return isinstance(s, str) and bool(_HEX_COLOR_RE.match(s))


def _clean_meta(raw):
    """Return a sanitised _meta dict containing only known string fields."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ("name", "author", "description", "version"):
        v = raw.get(key)
        if isinstance(v, str):
            v = v.strip()
            if v:
                limit = MAX_DESC_LEN if key == "description" else MAX_NAME_LEN
                out[key] = v[:limit]
    return out


def validate_tag_data(data):
    """Validate and normalise a tag-pack dict.

    Returns (clean, errors, warnings). `clean` is always a dict with keys
    energy_levels (list), energy_colors (dict), comment_tags (dict),
    _meta (dict) — any of which may be empty if absent in input. Errors
    indicate the data is unusable; warnings indicate values were dropped.
    """
    errors = []
    warnings = []
    clean = {"energy_levels": [], "energy_colors": {}, "comment_tags": {}, _META_KEY: {}}

    if not isinstance(data, dict):
        errors.append("Top-level value must be a JSON object.")
        return clean, errors, warnings

    clean[_META_KEY] = _clean_meta(data.get(_META_KEY))

    # Energy levels
    levels = data.get("energy_levels")
    if levels is not None:
        if not isinstance(levels, list):
            errors.append("'energy_levels' must be a list.")
        else:
            seen = set()
            for x in levels:
                if not isinstance(x, str):
                    continue
                name = x.strip()[:MAX_NAME_LEN]
                if not name or name in seen:
                    continue
                seen.add(name)
                clean["energy_levels"].append(name)
                if len(clean["energy_levels"]) >= MAX_ENERGY_LEVELS:
                    warnings.append(
                        f"Energy levels capped at {MAX_ENERGY_LEVELS}; extras dropped.")
                    break

    # Energy colors — only accept #RRGGBB
    colors = data.get("energy_colors")
    if colors is not None:
        if not isinstance(colors, dict):
            errors.append("'energy_colors' must be an object.")
        else:
            for k, v in colors.items():
                if not isinstance(k, str):
                    continue
                if _is_valid_hex_color(v):
                    clean["energy_colors"][k.strip()[:MAX_NAME_LEN]] = v
                else:
                    warnings.append(f"Ignored invalid color for '{k}'.")

    # Comment tags
    tags = data.get("comment_tags")
    if tags is not None:
        if not isinstance(tags, dict):
            errors.append("'comment_tags' must be an object.")
        else:
            total = 0
            cats_used = 0
            for cat, vals in tags.items():
                if cats_used >= MAX_CATEGORIES:
                    warnings.append(
                        f"Categories capped at {MAX_CATEGORIES}; extras dropped.")
                    break
                if not isinstance(cat, str) or not isinstance(vals, list):
                    continue
                cat_clean = cat.strip()[:MAX_NAME_LEN]
                if not cat_clean:
                    continue
                seen = set()
                kept = []
                for v in vals:
                    if not isinstance(v, str):
                        continue
                    nv = v.strip()[:MAX_NAME_LEN]
                    if not nv or nv in seen:
                        continue
                    seen.add(nv)
                    kept.append(nv)
                    total += 1
                    if len(kept) >= MAX_TAGS_PER_CATEGORY:
                        warnings.append(
                            f"'{cat_clean}' capped at {MAX_TAGS_PER_CATEGORY} tags.")
                        break
                    if total >= MAX_TOTAL_TAGS:
                        warnings.append(
                            f"Total tags capped at {MAX_TOTAL_TAGS}; remainder dropped.")
                        break
                clean["comment_tags"][cat_clean] = kept
                cats_used += 1
                if total >= MAX_TOTAL_TAGS:
                    break

    return clean, errors, warnings


def read_pack_file(path):
    """Read and validate a pack JSON file.

    Returns (clean, errors, warnings). Always returns a usable structure
    even on failure; callers check `errors` to decide whether to apply.
    """
    p = Path(path)
    try:
        if p.stat().st_size > MAX_PACK_FILE_BYTES:
            return ({"energy_levels": [], "energy_colors": {}, "comment_tags": {}, _META_KEY: {}},
                    [f"File is larger than {MAX_PACK_FILE_BYTES // 1024} KB — refusing to load."],
                    [])
        data = json.loads(p.read_text(encoding='utf-8'))
    except OSError as e:
        return ({"energy_levels": [], "energy_colors": {}, "comment_tags": {}, _META_KEY: {}},
                [f"Could not read file: {e}"], [])
    except json.JSONDecodeError as e:
        return ({"energy_levels": [], "energy_colors": {}, "comment_tags": {}, _META_KEY: {}},
                [f"Invalid JSON: {e.msg} (line {e.lineno})"], [])
    return validate_tag_data(data)


def apply_pack(state, pack, mode):
    """Return a NEW state dict with `pack` applied to `state` in given mode.

    `state` and `pack` use the same shape: dict with energy_levels,
    energy_colors, comment_tags, _meta. `mode` is "replace" or "merge".
    Never mutates inputs. Also returns a `summary` dict and a list of
    warnings (e.g. cross-category duplicate tags skipped during merge).
    """
    new_state = {
        "energy_levels":  list(state.get("energy_levels", [])),
        "energy_colors":  dict(state.get("energy_colors", {})),
        "comment_tags":   {k: list(v) for k, v in state.get("comment_tags", {}).items()},
        _META_KEY:        dict(state.get(_META_KEY, {})),
    }
    warnings = []
    summary = {"levels_added": 0, "tags_added": 0, "categories_added": 0,
               "cross_category_skipped": []}

    if mode == "replace":
        new_state["energy_levels"] = list(pack.get("energy_levels", []))
        # Replace colors but only keep ones that map to a known level (post-replace).
        valid_levels = set(new_state["energy_levels"])
        new_state["energy_colors"] = {
            k: v for k, v in pack.get("energy_colors", {}).items()
            if k in valid_levels and _is_valid_hex_color(v)
        }
        new_state["comment_tags"] = {
            k: list(v) for k, v in pack.get("comment_tags", {}).items()
        }
        new_state[_META_KEY] = dict(pack.get(_META_KEY, {}))
        summary["levels_added"] = len(new_state["energy_levels"])
        summary["categories_added"] = len(new_state["comment_tags"])
        summary["tags_added"] = sum(len(v) for v in new_state["comment_tags"].values())
        return new_state, summary, warnings

    # MERGE
    existing_levels = set(new_state["energy_levels"])
    for lv in pack.get("energy_levels", []):
        if lv not in existing_levels:
            new_state["energy_levels"].append(lv)
            existing_levels.add(lv)
            summary["levels_added"] += 1
    # Only set colors for levels that don't yet have one (don't clobber user choices).
    for lv, c in pack.get("energy_colors", {}).items():
        if lv in existing_levels and lv not in new_state["energy_colors"] and _is_valid_hex_color(c):
            new_state["energy_colors"][lv] = c

    # Build flat index of existing tag → category for cross-category check.
    tag_to_cat = {}
    for cat, vals in new_state["comment_tags"].items():
        for v in vals:
            tag_to_cat[v] = cat

    for cat, vals in pack.get("comment_tags", {}).items():
        target = new_state["comment_tags"].get(cat)
        if target is None:
            new_state["comment_tags"][cat] = []
            target = new_state["comment_tags"][cat]
            summary["categories_added"] += 1
        existing_in_cat = set(target)
        for v in vals:
            if v in existing_in_cat:
                continue
            other = tag_to_cat.get(v)
            if other is not None and other != cat:
                # Same string already lives in another category — skip to keep
                # the flat namespace unambiguous.
                summary["cross_category_skipped"].append((v, other, cat))
                continue
            target.append(v)
            existing_in_cat.add(v)
            tag_to_cat[v] = cat
            summary["tags_added"] += 1

    if summary["cross_category_skipped"]:
        examples = ", ".join(
            f"'{t}' (already in '{o}')"
            for t, o, _ in summary["cross_category_skipped"][:3])
        more = len(summary["cross_category_skipped"]) - 3
        warnings.append(
            f"Skipped {len(summary['cross_category_skipped'])} tag(s) already "
            f"present in another category: {examples}"
            + (f" and {more} more." if more > 0 else "."))

    # _meta is intentionally NOT merged — pack metadata describes the pack,
    # not the user's customised vocabulary. Leave existing _meta alone.

    return new_state, summary, warnings


def list_bundled_presets():
    """Return a list of (path, meta_dict) for valid presets in presets/.

    Skips files that are missing, malformed, or empty. Never raises.
    """
    out = []
    presets_dir = _resource_path("presets")
    if not presets_dir.exists() or not presets_dir.is_dir():
        return out
    try:
        files = sorted(presets_dir.glob("*.json"))
    except OSError:
        return out
    for f in files:
        try:
            clean, errors, _ = read_pack_file(f)
        except Exception:
            continue
        if errors:
            continue
        if not (clean["energy_levels"] or clean["comment_tags"]):
            continue
        out.append((f, clean.get(_META_KEY, {})))
    return out


def save_tag_config():
    """Write the current live vocabulary to tags.json (with optional _meta)."""
    data = {}
    if TAG_META:
        data[_META_KEY] = dict(TAG_META)
    data["energy_levels"] = list(ENERGY_LEVELS)
    data["energy_colors"] = {k: ENERGY_COLORS.get(k, "#888888") for k in ENERGY_LEVELS}
    data["comment_tags"]  = {k: list(v) for k, v in COMMENT_TAGS.items()}
    try:
        TAG_CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"[tags] failed to write {TAG_CONFIG_PATH}: {e}")


def load_tag_config():
    """Load vocabulary from tags.json into the live globals.
    On first run (file missing) write defaults so the file is self-documenting.
    Malformed files are ignored and defaults are kept in memory."""
    if not TAG_CONFIG_PATH.exists():
        save_tag_config()
        return
    clean, errors, warnings = read_pack_file(TAG_CONFIG_PATH)
    if errors:
        print(f"[tags] {TAG_CONFIG_PATH}: {'; '.join(errors)} — using defaults")
        return
    for w in warnings:
        print(f"[tags] {TAG_CONFIG_PATH}: {w}")

    if clean["energy_levels"]:
        ENERGY_LEVELS[:] = clean["energy_levels"]
    if clean["energy_colors"]:
        ENERGY_COLORS.clear()
        for k, v in clean["energy_colors"].items():
            ENERGY_COLORS[k] = v
        for lv in ENERGY_LEVELS:
            ENERGY_COLORS.setdefault(lv, DEFAULT_ENERGY_COLORS.get(lv, "#888888"))
    if clean["comment_tags"]:
        COMMENT_TAGS.clear()
        COMMENT_TAGS.update(clean["comment_tags"])
    if clean[_META_KEY]:
        TAG_META.clear()
        TAG_META.update(clean[_META_KEY])


load_tag_config()


def normalize_tag_name(name):
    """Trim and hyphenate internal whitespace (matches DJ Tagging Reference convention)."""
    return '-'.join(name.strip().split())

RATING_POPM = {1: 1, 3: 128, 5: 255}
POPM_EMAIL  = 'rekordbox@rekordbox.com'

def _popm_to_stars(val):
    if val == 0:
        return None
    closest = min(RATING_POPM.items(), key=lambda x: abs(x[1] - val))
    return closest[0]

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
    if ext == '.flac':             return FLACFile(path)
    if ext == '.m4a':              return MP4(path)
    return None

def _extract_rating_from_comments(comments):
    """Extract and remove rating comment tags (e.g. '3★') from a comment set."""
    found = comments & _RATING_COMMENTS
    comments -= _RATING_COMMENTS
    if found:
        for r, label in RATING_COMMENT.items():
            if label in found:
                return r
    return None

def _extract_energy_from_comments(comments):
    """Promote the first energy-level word found in a comment set (legacy support).

    Older versions and some DJ tools stored the energy level as the first word
    of the comment field rather than in the Genre (TCON/GENRE/©gen) field.
    Checks in ENERGY_LEVELS order for determinism; removes the word in-place.
    """
    for level in ENERGY_LEVELS:
        if level in comments:
            comments.discard(level)
            return level
    return None

def read_tags(path):
    try:
        audio = _open(path)
        if audio is None:
            return {}

        ext = path.suffix.lower()
        is_flac = ext == '.flac'
        is_m4a = ext == '.m4a'

        if is_m4a:
            t = audio.tags
            if t is None:
                return {'energy': None, 'rating': None, 'comments': set()}

            energy = None
            genres = t.get('\xa9gen', [])
            if genres and genres[0] in ENERGY_LEVELS:
                energy = genres[0]

            comments = set()
            comm = t.get('\xa9cmt', [])
            if comm and comm[0]:
                comments = set(comm[0].split())

            # M4A has no standard rating field — extract from comments
            rating = None
            comment_rating = _extract_rating_from_comments(comments)
            if comment_rating is not None:
                rating = comment_rating

            if energy is None:
                energy = _extract_energy_from_comments(comments)

            return {'energy': energy, 'rating': rating, 'comments': comments}

        t = audio.tags if not is_flac else audio
        if t is None:
            return {'energy': None, 'rating': None, 'comments': set()}

        if is_flac:
            energy = None
            genres = t.get('GENRE', [])
            if genres and genres[0] in ENERGY_LEVELS:
                energy = genres[0]

            comments = set()
            comm = t.get('COMMENT', [])
            if comm and comm[0]:
                comments = set(comm[0].split())

            rating = None
            rat = t.get('RATING', [])
            if rat:
                try:
                    rating = _popm_to_stars(int(rat[0]))
                except (ValueError, TypeError):
                    pass

            # Also check for rating in comments (fallback)
            comment_rating = _extract_rating_from_comments(comments)
            if rating is None:
                rating = comment_rating

            if energy is None:
                energy = _extract_energy_from_comments(comments)

            return {'energy': energy, 'rating': rating, 'comments': comments}

        # ID3-based formats (MP3, WAV, AIFF)
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

        # Also check for rating in comments (fallback)
        comment_rating = _extract_rating_from_comments(comments)
        if rating is None:
            rating = comment_rating

        if energy is None:
            energy = _extract_energy_from_comments(comments)

        return {'energy': energy, 'rating': rating, 'comments': comments}
    except Exception as e:
        return {'energy': None, 'rating': None, 'comments': set(), '_err': str(e)}

def write_tags(path, energy, rating, comments):
    try:
        audio = _open(path)
        if audio is None:
            return f"Unsupported format: {path.suffix}"

        ext = path.suffix.lower()
        is_flac = ext == '.flac'
        is_m4a = ext == '.m4a'

        # Build the full comment string: user tags + rating comment
        all_comments = set(comments) if comments else set()
        all_comments -= _RATING_COMMENTS  # strip any old rating comments
        if rating and rating in RATING_COMMENT:
            all_comments.add(RATING_COMMENT[rating])
        comment_str = ' '.join(sorted(all_comments)) if all_comments else ''

        if is_m4a:
            t = audio.tags
            if t is None:
                audio.add_tags()
                t = audio.tags

            if energy:
                t['\xa9gen'] = [energy]
            elif '\xa9gen' in t:
                del t['\xa9gen']

            if '\xa9cmt' in t:
                del t['\xa9cmt']
            if comment_str:
                t['\xa9cmt'] = [comment_str]

            # No standard rating field in M4A — rating is in the comment string
            audio.save()
            return None

        if is_flac:
            if energy:
                audio['GENRE'] = [energy]
            elif 'GENRE' in audio:
                del audio['GENRE']

            if 'COMMENT' in audio:
                del audio['COMMENT']
            if comment_str:
                audio['COMMENT'] = [comment_str]

            if 'RATING' in audio:
                del audio['RATING']
            if rating and rating in RATING_POPM:
                audio['RATING'] = [str(RATING_POPM[rating])]

            audio.save()
            return None

        # ID3-based formats (MP3, WAV, AIFF)
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
        if comment_str:
            t['COMM::eng'] = COMM(encoding=3, lang='eng', desc='',
                                   text=[comment_str])

        for k in list(t.keys()):
            if k.startswith('POPM'):
                del t[k]
        if rating and rating in RATING_POPM:
            t['POPM:' + POPM_EMAIL] = POPM(email=POPM_EMAIL,
                                       rating=RATING_POPM[rating], count=0)
        audio.save()
        return None
    except Exception as e:
        return str(e)

def compute_waveform(path, num_bars=200):
    """Return a list of normalised RMS amplitudes (0.0–1.0) for drawing."""
    try:
        seg = AudioSegment.from_file(str(path))
        seg = seg.set_channels(1).set_sample_width(2)
        raw = seg.raw_data
        n_samples = len(raw) // 2
        if n_samples == 0:
            return [0.0] * num_bars
        chunk_samples = max(1, n_samples // num_bars)
        chunk_bytes = chunk_samples * 2
        rms_vals = []
        for i in range(num_bars):
            start = i * chunk_bytes
            end = min(start + chunk_bytes, len(raw))
            if start >= len(raw):
                rms_vals.append(0.0)
            else:
                rms_vals.append(audioop.rms(raw[start:end], 2))
        mx = max(rms_vals) or 1
        return [v / mx for v in rms_vals]
    except Exception:
        return [0.0] * num_bars


def _has_ffmpeg():
    """Check whether ffmpeg is available on PATH."""
    return shutil.which('ffmpeg') is not None


def _copy_id3_tags(src_path, dst_path):
    """Copy all ID3 tags from one audio file to another."""
    src = _open(src_path)
    dst = _open(dst_path)
    if src is None or dst is None:
        return
    src_tags = src.tags
    if src_tags is None:
        return
    if dst.tags is None:
        dst.add_tags()
    for key in src_tags.keys():
        dst.tags[key] = src_tags[key]
    dst.save()


def _copy_tags_to_flac(src_path, dst_path):
    """Copy ID3 tags from a source audio file to a FLAC file (VorbisComment)."""
    src = _open(src_path)
    if src is None or src.tags is None:
        return
    flac = FLACFile(dst_path)
    t = src.tags

    if 'TCON' in t and t['TCON'].text:
        flac['GENRE'] = t['TCON'].text

    # Build comment string including rating
    comment_parts = set()
    for k in t.keys():
        if k.startswith('COMM'):
            text = t[k].text[0] if t[k].text else ''
            if text:
                comment_parts = set(text.split())
            break

    rating_val = None
    for k in t.keys():
        if k.startswith('POPM'):
            rating_val = t[k].rating
            flac['RATING'] = [str(rating_val)]
            break

    # Add rating comment tag for Rekordbox visibility
    comment_parts -= _RATING_COMMENTS
    if rating_val:
        stars = _popm_to_stars(rating_val)
        if stars and stars in RATING_COMMENT:
            comment_parts.add(RATING_COMMENT[stars])

    if comment_parts:
        flac['COMMENT'] = [' '.join(sorted(comment_parts))]

    flac.save()

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
        self.legacy_btns = {}
        self.tag_palette_frame = None
        self.legacy_frame = None
        self.tag_editor_win = None
        self.stats_win   = None
        self.convert_win = None

        # Render diff tracking — _SENTINEL forces full render on first call
        self._SENTINEL     = object()
        self._prev_energy  = self._SENTINEL
        self._prev_rating  = self._SENTINEL
        self._prev_comments = set()
        self._prev_legacy_sig = None

        # Player state
        self.p_state    = 'stopped'   # 'stopped' | 'playing' | 'paused'
        self.p_duration = 0.0
        self.p_seek_off = 0.0         # position (secs) at last play/seek
        self.p_t0       = 0.0         # time.time() when current segment started
        self._prog_job  = None
        self.waveform   = []
        self._wave_ids  = []          # canvas item IDs for waveform bars
        self._head_id   = None        # canvas item ID for playhead line
        self._last_fill = -1          # last filled bar index for incremental updates
        self._canvas_w  = 0           # cached canvas dimensions
        self._canvas_h  = 0
        self._resize_job = None       # debounce handle for canvas resize

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
        tk.Button(
            hdr, text="📊 Stats",
            bg=BG3, fg=FG, activebackground=BG3, activeforeground=FG,
            relief='flat', padx=10, pady=4, bd=0, highlightthickness=0,
            font=('Helvetica', 9), cursor='hand2',
            command=self._show_stats,
        ).pack(side='right', padx=(8, 0))
        tk.Button(
            hdr, text="🏷️ Tags",
            bg=BG3, fg=FG, activebackground=BG3, activeforeground=FG,
            relief='flat', padx=10, pady=4, bd=0, highlightthickness=0,
            font=('Helvetica', 9), cursor='hand2',
            command=self._show_tag_editor,
        ).pack(side='right', padx=(8, 0))
        tk.Button(
            hdr, text="🔄 Convert WAVs",
            bg=BG3, fg=FG, activebackground=BG3, activeforeground=FG,
            relief='flat', padx=10, pady=4, bd=0, highlightthickness=0,
            font=('Helvetica', 9), cursor='hand2',
            command=self._show_convert,
        ).pack(side='right', padx=(8, 0))
        self.status_lbl = tk.Label(hdr, text="", bg=BG, fg=FG2,
                                    font=('Helvetica', 10))
        self.status_lbl.pack(side='right')

        body = tk.PanedWindow(
            self, orient=tk.HORIZONTAL, bg=BG,
            sashwidth=6, sashcursor='sb_h_double_arrow',
            handlesize=0, sashrelief='flat',
        )
        body.pack(fill='both', expand=True, padx=14, pady=10)
        self._build_list(body)
        self._build_editor(body)
        self._build_footer()

    def _build_list(self, parent):
        frame = tk.Frame(parent, bg=BG2)
        parent.add(frame, minsize=180, width=290, stretch='never')

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
        parent.add(outer, minsize=400, stretch='always')

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
        self.tag_palette_frame = tk.Frame(sf, bg=BG)
        self.tag_palette_frame.pack(fill='x', anchor='w')
        self._build_tag_groups(self.tag_palette_frame)

        # Legacy section sits below the editable palette and is populated per-track
        # in _render_legacy() with any tags/energy on the current track that are
        # no longer in the live vocabulary.
        self.legacy_frame = tk.Frame(sf, bg=BG)
        self.legacy_frame.pack(fill='x', anchor='w')

    def _build_tag_groups(self, parent):
        """(Re)build the comment-tag category rows inside `parent`."""
        for cat, tags in COMMENT_TAGS.items():
            self._build_tag_group(parent, cat, tags)

    def _rebuild_tag_palette(self):
        """Tear down and rebuild the comment-tag category rows after a config edit."""
        if not self.tag_palette_frame:
            return
        for w in self.tag_palette_frame.winfo_children():
            w.destroy()
        self.tag_btns.clear()
        self._build_tag_groups(self.tag_palette_frame)
        # Energy buttons may also need rebuilding if levels/colors changed.
        # Easiest: rebuild the whole energy row in place too.
        self._rebuild_energy_row()
        # Force full re-render of state on the new buttons.
        self._prev_energy = self._SENTINEL
        self._prev_comments = set()
        self._prev_legacy_sig = None
        self._render()

    def _rebuild_energy_row(self):
        """Rebuild just the energy button row in place after vocabulary edits."""
        if not self.energy_btns:
            return
        # Find the parent frame of any existing energy button (the row built in _build_energy).
        any_btn = next(iter(self.energy_btns.values()))
        row = any_btn.master
        section_label = row.master  # the scrollable frame `sf`
        # Remember position by destroying old row and rebuilding inside same parent.
        for w in row.winfo_children():
            w.destroy()
        self.energy_btns.clear()
        for level in ENERGY_LEVELS:
            btn = tk.Button(
                row, text=level, bg=BG3, fg=FG2,
                relief='flat', padx=18, pady=9,
                font=('Helvetica', 10, 'bold'), cursor='hand2',
                activebackground=ENERGY_COLORS.get(level, ACCENT), activeforeground='white',
                bd=0, highlightthickness=0,
                command=lambda lv=level: self._click_energy(lv),
            )
            btn.pack(side='left', padx=(0, 6))
            self.energy_btns[level] = btn

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

        # Waveform / Scrubber
        self.prog_canvas = tk.Canvas(bar, bg=BG2, height=60,
                                      highlightthickness=0, cursor='hand2')
        self.prog_canvas.pack(side='left', fill='x', expand=True)
        self.prog_canvas.bind('<Button-1>', self._seek_click)
        self.prog_canvas.bind('<B1-Motion>', self._seek_click)
        self.prog_canvas.bind('<Configure>', lambda e: self._on_canvas_resize())

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

    def _build_waveform(self):
        """Create canvas items for waveform bars and playhead (called once per track)."""
        c = self.prog_canvas
        c.delete('all')
        self._wave_ids = []
        self._head_id = None
        self._last_fill = -1
        w = c.winfo_width()
        h = c.winfo_height()
        self._canvas_w = w
        self._canvas_h = h
        if w < 4 or h < 4:
            return
        mid = h // 2
        if self.waveform:
            num_bars = len(self.waveform)
            bar_w = w / num_bars
            for i, peak in enumerate(self.waveform):
                x0 = int(i * bar_w)
                x1 = max(x0 + 1, int((i + 1) * bar_w) - 1)
                bar_h = max(1, int(peak * (mid - 2)))
                rid = c.create_rectangle(x0, mid - bar_h, x1, mid + bar_h,
                                         fill=BG3, outline='')
                self._wave_ids.append(rid)
        else:
            self._wave_ids.append(c.create_line(0, mid, w, mid, fill=BG3, width=4))
        self._head_id = c.create_line(1, 0, 1, h, fill=FG, width=1)

    def _draw_progress(self, frac):
        c = self.prog_canvas
        w = self._canvas_w
        h = self._canvas_h
        if w < 4 or h < 4:
            return
        frac = max(0.0, min(1.0, frac))

        if self._wave_ids and self.waveform:
            num_bars = len(self.waveform)
            bar_w = w / num_bars
            filled_bar = int(frac * num_bars)
            filled_bar = min(filled_bar, num_bars - 1)
            if filled_bar != self._last_fill:
                lo = min(filled_bar, self._last_fill if self._last_fill >= 0 else 0)
                hi = max(filled_bar, self._last_fill if self._last_fill >= 0 else 0)
                for i in range(lo, hi + 1):
                    color = ACCENT if i <= filled_bar else BG3
                    c.itemconfig(self._wave_ids[i], fill=color)
                self._last_fill = filled_bar

        if self._head_id:
            filled_px = int(w * frac)
            px = max(1, min(w - 1, filled_px))
            c.coords(self._head_id, px, 0, px, h)

    def _load_waveform_async(self, path):
        """Compute waveform in a background thread to avoid blocking the UI."""
        def _worker(p=path):
            data = compute_waveform(p)
            self.after(0, lambda: self._on_waveform_ready(p, data))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_canvas_resize(self):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._do_canvas_resize)

    def _do_canvas_resize(self):
        self._resize_job = None
        self._build_waveform()
        self._draw_progress(self._pos_fraction())

    def _on_waveform_ready(self, path, data):
        if self.files and self.files[self.idx] == path:
            self.waveform = data
            self._build_waveform()
            self._draw_progress(self._pos_fraction())

    def _play_track(self, path):
        """Load and start playing a track from the beginning."""
        self._cancel_progress()
        pygame.mixer.music.stop()
        self.waveform = []
        self._build_waveform()
        self._load_waveform_async(path)
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
            if path.suffix.lower() in ('.aif', '.aiff', '.flac'):
                self._msg("AIFF/FLAC playback not supported — tags still work fine", FG2)
            elif path.suffix.lower() == '.m4a':
                self._msg("M4A playback not supported — tags still work fine", FG2)
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

    def _set_volume(self, val):
        pygame.mixer.music.set_volume(float(val) / 100.0)

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
        if self.files:
            self.listbox.insert('end', *[self._list_label(f) for f in self.files])
        self.status_lbl.config(text=f"{len(self.files)} tracks")
        if self.files:
            self._select(0)

    def _is_tagged(self, path):
        """Check whether a track has any tags (energy, rating, or comments)."""
        t = read_tags(path)
        return bool(t.get('energy') or t.get('rating') or t.get('comments'))

    def _get_tag_status(self, path):
        """Analyze a track's tagging completeness and return status: 'full', 'partial', or 'empty'.
        
        - 'empty': No tags at all
        - 'partial': Has some tags but missing energy, rating, or comments from some categories
        - 'full': Has energy + rating + at least one tag from EVERY comment category
        """
        t = read_tags(path)
        energy = t.get('energy')
        rating = t.get('rating')
        comments = t.get('comments', set())
        
        # Check if completely untagged
        if not energy and not rating and not comments:
            return 'empty'
        
        # Check if fully tagged: has energy, rating, AND at least one tag from every category
        has_energy = bool(energy)
        has_rating = bool(rating)
        
        # Check if has at least one comment from each category
        has_all_categories = True
        for category in COMMENT_TAGS:
            # Get all tags in this category
            category_tags = set(COMMENT_TAGS[category])
            # Check if track has at least one tag from this category
            has_category = bool(comments & category_tags)
            if not has_category:
                has_all_categories = False
                break
        
        if has_energy and has_rating and has_all_categories:
            return 'full'
        else:
            return 'partial'

    def _get_status_indicator(self, status):
        """Return the emoji indicator based on tag status."""
        if status == 'full':
            return '🟢'
        elif status == 'partial':
            return '🟡'
        else:  # empty
            return '🔴'

    def _list_label(self, path):
        """Return the listbox display text with colour indicator based on tag status."""
        status = self._get_tag_status(path)
        indicator = self._get_status_indicator(status)
        return f"{indicator}  {path.name}"

    def _update_list_label(self, idx):
        """Refresh a single listbox entry after tagging."""
        label = self._list_label(self.files[idx])
        self.listbox.delete(idx)
        self.listbox.insert(idx, label)

    def _select(self, idx):
        if not self.files or not (0 <= idx < len(self.files)):
            return
        if self.unsaved:
            if not self._save(resume_playback=False):
                return
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

        if energy != self._prev_energy:
            for lv, btn in self.energy_btns.items():
                btn.config(bg=ENERGY_COLORS[lv] if lv == energy else BG3,
                           fg='white' if lv == energy else FG2)
            self._prev_energy = energy

        if rating != self._prev_rating:
            for r, btn in self.rating_btns.items():
                btn.config(bg=ACCENT if r == rating else BG3,
                           fg='white' if r == rating else FG2)
            self._prev_rating = rating

        for tag, btn in self.tag_btns.items():
            on = tag in comments
            was_on = tag in self._prev_comments
            if on != was_on:
                btn.config(bg=ACCENT if on else BG3,
                           fg='white' if on else FG)
        self._prev_comments = set(comments)

        self._render_legacy()

    def _render_legacy(self):
        """Show per-track tags / energy that aren't in the current vocabulary."""
        if not self.legacy_frame:
            return
        energy   = self.tags.get('energy')
        comments = self.tags.get('comments', set())

        legacy_energy = energy if (energy and energy not in ENERGY_LEVELS) else None

        cur_vocab = set()
        for vals in COMMENT_TAGS.values():
            cur_vocab.update(vals)
        cur_vocab.update(_RATING_COMMENTS)  # rating markers aren't legacy
        legacy_tags = sorted(c for c in comments if c not in cur_vocab)

        sig = (legacy_energy, tuple(legacy_tags))
        if sig == self._prev_legacy_sig:
            return
        self._prev_legacy_sig = sig

        for w in self.legacy_frame.winfo_children():
            w.destroy()
        self.legacy_btns.clear()

        if not legacy_energy and not legacy_tags:
            return

        tk.Label(self.legacy_frame,
                 text="LEGACY  (not in current vocabulary — click to clear)",
                 bg=BG, fg='#e67e22',
                 font=('Helvetica', 9, 'bold')).pack(anchor='w', pady=(16, 5))

        row = tk.Frame(self.legacy_frame, bg=BG)
        row.pack(anchor='w')

        if legacy_energy:
            tk.Button(
                row, text=f"Energy: {legacy_energy}  ✕",
                bg='#5a3a1a', fg='white',
                activebackground='#7a4a20', activeforeground='white',
                relief='flat', padx=12, pady=7,
                font=('Helvetica', 10), cursor='hand2',
                bd=0, highlightthickness=0,
                command=self._clear_legacy_energy,
            ).pack(side='left', padx=(0, 5), pady=(0, 4))

        for i, tag in enumerate(legacy_tags):
            btn = tk.Button(
                row, text=f"{tag}  ✕",
                bg='#5a3a1a', fg='white',
                activebackground='#7a4a20', activeforeground='white',
                relief='flat', padx=12, pady=7,
                font=('Helvetica', 10), cursor='hand2',
                bd=0, highlightthickness=0,
                command=lambda t=tag: self._clear_legacy_tag(t),
            )
            btn.pack(side='left', padx=(0, 5), pady=(0, 4))
            self.legacy_btns[tag] = btn
            if (i + 1) % 6 == 0 and (i + 1) < len(legacy_tags):
                row = tk.Frame(self.legacy_frame, bg=BG)
                row.pack(anchor='w')

    def _clear_legacy_tag(self, tag):
        comments = set(self.tags.get('comments', set()))
        comments.discard(tag)
        self.tags['comments'] = comments
        self.unsaved = True
        self._prev_legacy_sig = None
        self._render()
        self._msg(f"Cleared legacy tag: {tag}")

    def _clear_legacy_energy(self):
        self.tags['energy'] = None
        self.unsaved = True
        self._prev_energy = self._SENTINEL
        self._prev_legacy_sig = None
        self._render()
        self._msg("Cleared legacy energy")

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

    def _save(self, resume_playback=True):
        if not self.files:
            return True
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
            # Reload so user can retry; don't proceed with navigation
            if was_playing or was_paused:
                try:
                    pygame.mixer.music.load(str(path))
                except Exception:
                    pass
            return False
        self.unsaved = False
        self._msg("✓ saved", ACCENT)
        self._update_list_label(self.idx)
        self.listbox.selection_set(self.idx)
        self.after(2500, lambda: self._msg("") if not self.unsaved else None)
        # Resume playback from where we left off (skip when switching tracks)
        if resume_playback:
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
        return True

    def _prev(self):
        if self.idx > 0:
            self._select(self.idx - 1)

    def _next(self):
        if self.idx < len(self.files) - 1:
            self._select(self.idx + 1)

    def _save_next(self):
        if self._save():
            self._next()

    def _on_close(self):
        self._cancel_progress()
        pygame.mixer.quit()
        self.destroy()

    # ── Stats dashboard ────────────────────────────────────────────────────────

    def _show_stats(self):
        """Open (or refresh) a stats dashboard window."""
        if self.stats_win and self.stats_win.winfo_exists():
            self.stats_win.lift()
            self.stats_win.focus_force()
            self._refresh_stats()
            return

        win = tk.Toplevel(self)
        win.title("Tag Stats")
        win.configure(bg=BG)
        win.geometry("520x620")
        win.minsize(400, 400)
        self.stats_win = win

        self._stats_body = tk.Frame(win, bg=BG)
        self._stats_body.pack(fill='both', expand=True, padx=16, pady=(10, 0))

        btn_bar = tk.Frame(win, bg=BG)
        btn_bar.pack(fill='x', padx=16, pady=10)
        tk.Button(
            btn_bar, text="🔄 Refresh", bg=BG3, fg=FG,
            activebackground=BG3, activeforeground=FG,
            relief='flat', padx=14, pady=6, bd=0, highlightthickness=0,
            font=('Helvetica', 9), cursor='hand2',
            command=self._refresh_stats,
        ).pack(side='left')

        # Show "Scanning…" then populate via after() to keep UI responsive
        self._stats_loading = tk.Label(
            self._stats_body, text="Scanning…", bg=BG, fg=FG2,
            font=('Helvetica', 11))
        self._stats_loading.pack(pady=30)
        win.after(50, self._refresh_stats)

    def _refresh_stats(self):
        """Scan all tracks and redraw the stats dashboard content."""
        if not self.stats_win or not self.stats_win.winfo_exists():
            return

        # Clear previous content
        for w in self._stats_body.winfo_children():
            w.destroy()

        if not self.files:
            tk.Label(self._stats_body, text="No tracks in folder.",
                     bg=BG, fg=FG2, font=('Helvetica', 11)).pack(pady=30)
            return

        # ── Scan ──────────────────────────────────────────────────────────
        total      = len(self.files)
        tagged     = 0
        errors     = 0
        energy_cnt = {lv: 0 for lv in ENERGY_LEVELS}
        rating_cnt = {r: 0 for r in RATINGS}
        tag_cnt    = {}

        for i, f in enumerate(self.files):
            # Use in-memory state for the current track if unsaved
            if i == self.idx and self.unsaved:
                t = dict(self.tags)
            else:
                t = read_tags(f)

            if '_err' in t:
                errors += 1
                continue

            has_tag = False
            if t.get('energy'):
                energy_cnt[t['energy']] = energy_cnt.get(t['energy'], 0) + 1
                has_tag = True
            if t.get('rating'):
                rating_cnt[t['rating']] = rating_cnt.get(t['rating'], 0) + 1
                has_tag = True
            for c in t.get('comments', set()):
                tag_cnt[c] = tag_cnt.get(c, 0) + 1
                has_tag = True
            if has_tag:
                tagged += 1

        untagged = total - tagged - errors

        # ── Render ────────────────────────────────────────────────────────
        container = self._stats_body

        # Scrollable canvas for the stats content
        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(container, orient='vertical', command=canvas.yview)
        sf = tk.Frame(canvas, bg=BG)
        sf.bind('<Configure>',
                lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=sf, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        canvas.bind('<MouseWheel>',
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

        def section(text):
            tk.Label(sf, text=text, bg=BG, fg=FG2,
                     font=('Helvetica', 9, 'bold')).pack(anchor='w', pady=(14, 4))

        def stat_row(parent, label, value, color=FG):
            row = tk.Frame(parent, bg=BG)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=label, bg=BG, fg=FG,
                     font=('Helvetica', 10), anchor='w').pack(side='left')
            tk.Label(row, text=str(value), bg=BG, fg=color,
                     font=('Helvetica', 10, 'bold'), anchor='e').pack(side='right')

        def bar_row(parent, label, count, max_count, color=ACCENT):
            row = tk.Frame(parent, bg=BG)
            row.pack(fill='x', pady=2)
            tk.Label(row, text=label, bg=BG, fg=FG,
                     font=('Helvetica', 10), width=14, anchor='w').pack(side='left')
            tk.Label(row, text=str(count), bg=BG, fg=ACCENT,
                     font=('Helvetica', 10, 'bold'), width=4, anchor='e').pack(side='right')
            bar_frame = tk.Frame(row, bg=BG3, height=14)
            bar_frame.pack(side='left', fill='x', expand=True, padx=(6, 6))
            bar_frame.pack_propagate(False)
            if max_count > 0 and count > 0:
                frac = count / max_count
                fill = tk.Frame(bar_frame, bg=color, width=1)
                fill.place(relwidth=frac, relheight=1.0)

        # Summary
        section("SUMMARY")
        pct = f"{tagged * 100 // total}%" if total > 0 else "0%"
        stat_row(sf, "Total tracks", total)
        stat_row(sf, "Tagged", f"{tagged}  ({pct})", ACCENT)
        stat_row(sf, "Untagged", untagged)
        if errors:
            stat_row(sf, "Unreadable", errors, "#e74c3c")

        # Energy distribution
        section("ENERGY")
        max_e = max(energy_cnt.values()) if energy_cnt else 0
        for lv in ENERGY_LEVELS:
            bar_row(sf, lv, energy_cnt[lv], max_e,
                    ENERGY_COLORS.get(lv, ACCENT))

        # Rating distribution
        section("RATING")
        max_r = max(rating_cnt.values()) if rating_cnt else 0
        for r in RATINGS:
            bar_row(sf, RATING_LABELS[r], rating_cnt[r], max_r)

        # Comment tags — sorted by frequency
        section("TOP TAGS")
        sorted_tags = sorted(tag_cnt.items(), key=lambda x: x[1], reverse=True)
        max_t = sorted_tags[0][1] if sorted_tags else 0
        for tag, cnt in sorted_tags[:30]:
            bar_row(sf, tag, cnt, max_t)

        if not sorted_tags:
            tk.Label(sf, text="No comment tags found.", bg=BG, fg=FG2,
                     font=('Helvetica', 10, 'italic')).pack(anchor='w', pady=4)

    # ── Tag vocabulary editor ──────────────────────────────────────────────────

    def _show_tag_editor(self):
        """Open the in-app tag vocabulary editor."""
        if self.tag_editor_win and self.tag_editor_win.winfo_exists():
            self.tag_editor_win.lift()
            self.tag_editor_win.focus_force()
            return

        win = tk.Toplevel(self)
        self.tag_editor_win = win
        win.title("Tag Vocabulary Editor")
        win.configure(bg=BG)
        win.geometry("780x720")
        win.minsize(620, 480)

        # Working state — deep copies so Cancel really cancels.
        self._te_levels = list(ENERGY_LEVELS)
        self._te_colors = {k: ENERGY_COLORS.get(k, DEFAULT_ENERGY_COLORS.get(k, "#888888"))
                           for k in self._te_levels}
        self._te_cats = list(COMMENT_TAGS.keys())
        self._te_tags_by_cat = {k: list(v) for k, v in COMMENT_TAGS.items()}
        self._te_meta = dict(TAG_META)

        # Header
        hdr = tk.Frame(win, bg=BG)
        hdr.pack(fill='x', padx=14, pady=(12, 6))
        tk.Label(hdr, text="TAG VOCABULARY", bg=BG, fg=ACCENT,
                 font=('Helvetica', 13, 'bold')).pack(side='left')
        tk.Label(hdr,
                 text="Edits apply to the live palette and are saved to tags.json",
                 bg=BG, fg=FG2, font=('Helvetica', 9, 'italic')).pack(side='left', padx=(12, 0))

        # Pack toolbar — load / export / edit pack info
        tb = tk.Frame(win, bg=BG)
        tb.pack(fill='x', padx=14, pady=(0, 6))
        for label, cmd in [
            ("📥  Load pack…",  self._te_load_pack),
            ("💾  Export pack…", self._te_export_pack),
            ("✏️  Pack info…",  self._te_edit_meta),
        ]:
            tk.Button(tb, text=label, bg=BG3, fg=FG,
                      activebackground=BG3, activeforeground=FG,
                      relief='flat', padx=10, pady=5, bd=0, highlightthickness=0,
                      font=('Helvetica', 9), cursor='hand2',
                      command=cmd).pack(side='left', padx=(0, 6))

        # Scrollable body
        body = tk.Frame(win, bg=BG)
        body.pack(fill='both', expand=True, padx=14, pady=4)
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(body, orient='vertical', command=canvas.yview)
        sf = tk.Frame(canvas, bg=BG)
        sf.bind('<Configure>',
                lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=sf, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        canvas.bind('<MouseWheel>',
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), 'units'))
        self._te_body = sf

        # Footer
        footer = tk.Frame(win, bg=BG)
        footer.pack(fill='x', padx=14, pady=(6, 12))
        tk.Button(footer, text="Save & Apply",
                  bg=ACCENT, fg='white',
                  activebackground='#4bbfae', activeforeground='white',
                  relief='flat', padx=18, pady=8, bd=0, highlightthickness=0,
                  font=('Helvetica', 10, 'bold'), cursor='hand2',
                  command=self._te_save).pack(side='right', padx=(8, 0))
        tk.Button(footer, text="Cancel",
                  bg=BG3, fg=FG,
                  activebackground=BG3, activeforeground=FG,
                  relief='flat', padx=18, pady=8, bd=0, highlightthickness=0,
                  font=('Helvetica', 10), cursor='hand2',
                  command=win.destroy).pack(side='right')

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._te_render()

    # ── Editor render & helpers ────────────────────────────────────────────────

    def _te_render(self):
        """Rebuild the editor body from the working state."""
        if not self._te_body or not self._te_body.winfo_exists():
            return
        for w in self._te_body.winfo_children():
            w.destroy()

        # ENERGY LEVELS
        tk.Label(self._te_body, text="ENERGY LEVELS", bg=BG, fg=FG2,
                 font=('Helvetica', 9, 'bold')).pack(anchor='w', pady=(8, 4))
        tk.Label(self._te_body,
                 text="Order matters — levels appear left-to-right in the track editor.",
                 bg=BG, fg=FG2, font=('Helvetica', 9, 'italic')).pack(anchor='w', pady=(0, 6))

        for i, lv in enumerate(self._te_levels):
            self._te_level_row(self._te_body, i, lv)

        tk.Button(self._te_body, text="+ Add energy level",
                  bg=BG3, fg=FG, activebackground=BG3, activeforeground=FG,
                  relief='flat', padx=12, pady=6, bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=self._te_add_level).pack(anchor='w', pady=(4, 12))

        # COMMENT CATEGORIES
        tk.Label(self._te_body, text="COMMENT TAG CATEGORIES", bg=BG, fg=FG2,
                 font=('Helvetica', 9, 'bold')).pack(anchor='w', pady=(8, 4))

        for ci, cat in enumerate(self._te_cats):
            self._te_category_block(self._te_body, ci, cat)

        tk.Button(self._te_body, text="+ Add category",
                  bg=BG3, fg=FG, activebackground=BG3, activeforeground=FG,
                  relief='flat', padx=12, pady=6, bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=self._te_add_category).pack(anchor='w', pady=(4, 16))

    def _te_level_row(self, parent, i, lv):
        row = tk.Frame(parent, bg=BG2, padx=8, pady=4)
        row.pack(fill='x', pady=2)
        # Reorder
        tk.Button(row, text="▲", width=2, bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_move_level(i, -1)
                  ).pack(side='left', padx=(0, 2))
        tk.Button(row, text="▼", width=2, bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_move_level(i, +1)
                  ).pack(side='left', padx=(0, 8))

        # Color swatch
        color = self._te_colors.get(lv, "#888888")
        sw = tk.Button(row, text="    ", bg=color,
                       activebackground=color,
                       relief='flat', bd=1, highlightthickness=1,
                       highlightbackground=FG2, cursor='hand2',
                       command=lambda: self._te_pick_color(lv))
        sw.pack(side='left', padx=(0, 8))

        tk.Label(row, text=lv, bg=BG2, fg=FG,
                 font=('Helvetica', 11), width=14, anchor='w').pack(side='left')

        tk.Button(row, text="✕", width=2, bg=BG3, fg='#e74c3c',
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 10), cursor='hand2',
                  command=lambda: self._te_delete_level(i)
                  ).pack(side='right', padx=(4, 0))
        tk.Button(row, text="Rename", bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  padx=8, pady=2,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_rename_level(i)
                  ).pack(side='right', padx=(4, 0))

    def _te_category_block(self, parent, ci, cat):
        block = tk.Frame(parent, bg=BG, padx=0, pady=4)
        block.pack(fill='x', pady=(8, 0))

        head = tk.Frame(block, bg=BG)
        head.pack(fill='x')
        tk.Button(head, text="▲", width=2, bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_move_category(ci, -1)
                  ).pack(side='left', padx=(0, 2))
        tk.Button(head, text="▼", width=2, bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_move_category(ci, +1)
                  ).pack(side='left', padx=(0, 8))
        tk.Label(head, text=cat, bg=BG, fg=ACCENT,
                 font=('Helvetica', 11, 'bold')).pack(side='left')
        tk.Button(head, text="✕ Delete category", bg=BG3, fg='#e74c3c',
                  relief='flat', bd=0, highlightthickness=0,
                  padx=8, pady=2, font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_delete_category(ci)
                  ).pack(side='right', padx=(4, 0))
        tk.Button(head, text="Rename", bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  padx=8, pady=2, font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_rename_category(ci)
                  ).pack(side='right', padx=(4, 0))

        tags = self._te_tags_by_cat.get(cat, [])
        body = tk.Frame(block, bg=BG2, padx=10, pady=6)
        body.pack(fill='x', pady=(4, 0))
        if not tags:
            tk.Label(body, text="(no tags yet)", bg=BG2, fg=FG2,
                     font=('Helvetica', 9, 'italic')).pack(anchor='w')
        for ti, tag in enumerate(tags):
            self._te_tag_row(body, cat, ti, tag)

        tk.Button(body, text="+ Add tag", bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  padx=10, pady=4, font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_add_tag(cat)
                  ).pack(anchor='w', pady=(6, 0))

    def _te_tag_row(self, parent, cat, ti, tag):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill='x', pady=1)
        tk.Button(row, text="▲", width=2, bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_move_tag(cat, ti, -1)
                  ).pack(side='left', padx=(0, 2))
        tk.Button(row, text="▼", width=2, bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_move_tag(cat, ti, +1)
                  ).pack(side='left', padx=(0, 8))
        tk.Label(row, text=tag, bg=BG2, fg=FG,
                 font=('Helvetica', 10), anchor='w').pack(side='left')
        tk.Button(row, text="✕", width=2, bg=BG2, fg='#e74c3c',
                  activebackground=BG3,
                  relief='flat', bd=0, highlightthickness=0,
                  font=('Helvetica', 10), cursor='hand2',
                  command=lambda: self._te_delete_tag(cat, ti)
                  ).pack(side='right', padx=(4, 0))
        tk.Button(row, text="Rename", bg=BG2, fg=FG2,
                  activebackground=BG3,
                  relief='flat', bd=0, highlightthickness=0,
                  padx=6, pady=1, font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_rename_tag(cat, ti)
                  ).pack(side='right', padx=(4, 0))

    # ── Energy level mutations ─────────────────────────────────────────────────

    def _te_move_level(self, i, delta):
        j = i + delta
        if not (0 <= j < len(self._te_levels)):
            return
        self._te_levels[i], self._te_levels[j] = self._te_levels[j], self._te_levels[i]
        self._te_render()

    def _te_pick_color(self, lv):
        cur = self._te_colors.get(lv, "#888888")
        result = colorchooser.askcolor(color=cur, parent=self.tag_editor_win,
                                        title=f"Color for {lv}")
        if result and result[1]:
            self._te_colors[lv] = result[1]
            self._te_render()

    def _te_rename_level(self, i):
        old = self._te_levels[i]
        new = simpledialog.askstring("Rename energy level",
                                      f"Rename '{old}' to:",
                                      initialvalue=old,
                                      parent=self.tag_editor_win)
        if not new:
            return
        new = normalize_tag_name(new)
        if not new or new == old:
            return
        if new in self._te_levels:
            messagebox.showerror("Duplicate", f"Energy level '{new}' already exists.",
                                  parent=self.tag_editor_win)
            return
        self._te_levels[i] = new
        if old in self._te_colors:
            self._te_colors[new] = self._te_colors.pop(old)
        self._te_render()

    def _te_delete_level(self, i):
        lv = self._te_levels[i]
        if not messagebox.askyesno("Delete energy level",
                                    f"Delete '{lv}'?\n\nExisting tracks tagged with this energy will show it as a legacy entry until cleared.",
                                    parent=self.tag_editor_win):
            return
        del self._te_levels[i]
        self._te_colors.pop(lv, None)
        self._te_render()

    def _te_add_level(self):
        new = simpledialog.askstring("Add energy level", "Name:",
                                      parent=self.tag_editor_win)
        if not new:
            return
        new = normalize_tag_name(new)
        if not new:
            return
        if new in self._te_levels:
            messagebox.showerror("Duplicate", f"Energy level '{new}' already exists.",
                                  parent=self.tag_editor_win)
            return
        self._te_levels.append(new)
        self._te_colors[new] = DEFAULT_ENERGY_COLORS.get(new, ACCENT)
        self._te_render()

    # ── Category mutations ─────────────────────────────────────────────────────

    def _te_move_category(self, ci, delta):
        j = ci + delta
        if not (0 <= j < len(self._te_cats)):
            return
        self._te_cats[ci], self._te_cats[j] = self._te_cats[j], self._te_cats[ci]
        self._te_render()

    def _te_rename_category(self, ci):
        old = self._te_cats[ci]
        new = simpledialog.askstring("Rename category",
                                      f"Rename category '{old}' to:",
                                      initialvalue=old,
                                      parent=self.tag_editor_win)
        if not new:
            return
        new = new.strip()
        if not new or new == old:
            return
        if new in self._te_cats:
            messagebox.showerror("Duplicate", f"Category '{new}' already exists.",
                                  parent=self.tag_editor_win)
            return
        self._te_cats[ci] = new
        self._te_tags_by_cat[new] = self._te_tags_by_cat.pop(old, [])
        self._te_render()

    def _te_delete_category(self, ci):
        cat = self._te_cats[ci]
        n = len(self._te_tags_by_cat.get(cat, []))
        warn = (f"Delete category '{cat}' and its {n} tag(s)?\n\n"
                "Existing tracks tagged with these will show them as legacy entries until cleared.")
        if not messagebox.askyesno("Delete category", warn, parent=self.tag_editor_win):
            return
        del self._te_cats[ci]
        self._te_tags_by_cat.pop(cat, None)
        self._te_render()

    def _te_add_category(self):
        new = simpledialog.askstring("Add category", "Category name:",
                                      parent=self.tag_editor_win)
        if not new:
            return
        new = new.strip()
        if not new:
            return
        if new in self._te_cats:
            messagebox.showerror("Duplicate", f"Category '{new}' already exists.",
                                  parent=self.tag_editor_win)
            return
        self._te_cats.append(new)
        self._te_tags_by_cat[new] = []
        self._te_render()

    # ── Tag mutations ──────────────────────────────────────────────────────────

    def _te_move_tag(self, cat, ti, delta):
        tags = self._te_tags_by_cat.get(cat, [])
        j = ti + delta
        if not (0 <= j < len(tags)):
            return
        tags[ti], tags[j] = tags[j], tags[ti]
        self._te_render()

    def _te_rename_tag(self, cat, ti):
        tags = self._te_tags_by_cat.get(cat, [])
        old = tags[ti]
        new = simpledialog.askstring("Rename tag",
                                      f"Rename '{old}' to:",
                                      initialvalue=old,
                                      parent=self.tag_editor_win)
        if not new:
            return
        new = normalize_tag_name(new)
        if not new or new == old:
            return
        if new in tags:
            messagebox.showerror("Duplicate", f"Tag '{new}' already exists in '{cat}'.",
                                  parent=self.tag_editor_win)
            return
        tags[ti] = new
        self._te_render()

    def _te_delete_tag(self, cat, ti):
        tags = self._te_tags_by_cat.get(cat, [])
        tag = tags[ti]
        if not messagebox.askyesno("Delete tag",
                                    f"Delete '{tag}' from '{cat}'?\n\nExisting tracks tagged with this will show it as a legacy entry until cleared.",
                                    parent=self.tag_editor_win):
            return
        del tags[ti]
        self._te_render()

    def _te_add_tag(self, cat):
        new = simpledialog.askstring("Add tag", f"New tag in '{cat}':",
                                      parent=self.tag_editor_win)
        if not new:
            return
        new = normalize_tag_name(new)
        if not new:
            return
        tags = self._te_tags_by_cat.setdefault(cat, [])
        if new in tags:
            messagebox.showerror("Duplicate", f"Tag '{new}' already exists in '{cat}'.",
                                  parent=self.tag_editor_win)
            return
        # Also warn if the tag exists in another category — same string would collide.
        for other_cat, other_tags in self._te_tags_by_cat.items():
            if other_cat != cat and new in other_tags:
                if not messagebox.askyesno(
                        "Duplicate across categories",
                        f"'{new}' already exists in category '{other_cat}'. "
                        "Comment tags share a flat namespace in the file — adding it here "
                        "as well will not let you distinguish them. Add anyway?",
                        parent=self.tag_editor_win):
                    return
                break
        tags.append(new)
        self._te_render()

    # ── Save ───────────────────────────────────────────────────────────────────

    def _te_save(self):
        if not self._te_levels:
            messagebox.showerror("Validation", "At least one energy level is required.",
                                  parent=self.tag_editor_win)
            return
        # Commit working state to live globals
        ENERGY_LEVELS[:] = list(self._te_levels)
        ENERGY_COLORS.clear()
        for lv in ENERGY_LEVELS:
            ENERGY_COLORS[lv] = self._te_colors.get(lv, DEFAULT_ENERGY_COLORS.get(lv, ACCENT))
        COMMENT_TAGS.clear()
        for cat in self._te_cats:
            COMMENT_TAGS[cat] = list(self._te_tags_by_cat.get(cat, []))
        TAG_META.clear()
        TAG_META.update(self._te_meta)
        save_tag_config()
        self._rebuild_tag_palette()
        self._msg("Tag vocabulary updated", ACCENT)
        if self.tag_editor_win and self.tag_editor_win.winfo_exists():
            self.tag_editor_win.destroy()

    # ── Pack import / export ───────────────────────────────────────────────────

    def _te_current_state(self):
        return {
            "energy_levels":  list(self._te_levels),
            "energy_colors":  dict(self._te_colors),
            "comment_tags":   {k: list(v) for k, v in self._te_tags_by_cat.items()},
            "_meta":          dict(self._te_meta),
        }

    def _te_apply_state(self, new_state):
        """Swap working state to a freshly-built state dict (transactional)."""
        self._te_levels = list(new_state["energy_levels"])
        self._te_colors = dict(new_state["energy_colors"])
        # Preserve insertion order from the new state's comment_tags dict.
        self._te_cats = list(new_state["comment_tags"].keys())
        self._te_tags_by_cat = {k: list(v) for k, v in new_state["comment_tags"].items()}
        self._te_meta = dict(new_state.get("_meta", {}))
        self._te_render()

    def _te_load_pack(self):
        """Show a chooser of bundled presets + Browse… option."""
        parent = self.tag_editor_win
        presets = list_bundled_presets()

        win = tk.Toplevel(parent)
        win.title("Load tag pack")
        win.configure(bg=BG)
        win.geometry("520x420")
        win.transient(parent)

        tk.Label(win, text="LOAD A TAG PACK", bg=BG, fg=ACCENT,
                 font=('Helvetica', 12, 'bold')).pack(anchor='w', padx=14, pady=(12, 2))
        tk.Label(win,
                 text="Pick a bundled preset or browse to a JSON file you've been sent.",
                 bg=BG, fg=FG2, font=('Helvetica', 9, 'italic'),
                 wraplength=480, justify='left').pack(anchor='w', padx=14, pady=(0, 8))

        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(fill='both', expand=True, padx=14, pady=4)

        if not presets:
            tk.Label(list_frame,
                     text="(No bundled presets found in presets/.)",
                     bg=BG, fg=FG2, font=('Helvetica', 9, 'italic')
                     ).pack(anchor='w', pady=8)
        else:
            canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
            sb = tk.Scrollbar(list_frame, orient='vertical', command=canvas.yview)
            inner = tk.Frame(canvas, bg=BG)
            inner.bind('<Configure>',
                       lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.create_window((0, 0), window=inner, anchor='nw')
            canvas.configure(yscrollcommand=sb.set)
            canvas.pack(side='left', fill='both', expand=True)
            sb.pack(side='right', fill='y')

            for path, meta in presets:
                name = meta.get("name") or path.stem
                desc = meta.get("description") or ""
                if len(desc) > 140:
                    desc = desc[:137] + "…"
                row = tk.Frame(inner, bg=BG2, padx=10, pady=8)
                row.pack(fill='x', pady=2)
                tk.Label(row, text=name, bg=BG2, fg=FG,
                         font=('Helvetica', 10, 'bold')).pack(anchor='w')
                if desc:
                    tk.Label(row, text=desc, bg=BG2, fg=FG2,
                             font=('Helvetica', 9), wraplength=380,
                             justify='left').pack(anchor='w', pady=(2, 4))
                btns = tk.Frame(row, bg=BG2)
                btns.pack(anchor='w')
                tk.Button(btns, text="Replace…", bg=BG3, fg=FG,
                          relief='flat', bd=0, highlightthickness=0,
                          padx=10, pady=4, font=('Helvetica', 9), cursor='hand2',
                          command=lambda p=path: self._te_load_pack_from_file(p, win, "replace")
                          ).pack(side='left', padx=(0, 6))
                tk.Button(btns, text="Merge", bg=BG3, fg=FG,
                          relief='flat', bd=0, highlightthickness=0,
                          padx=10, pady=4, font=('Helvetica', 9), cursor='hand2',
                          command=lambda p=path: self._te_load_pack_from_file(p, win, "merge")
                          ).pack(side='left')

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill='x', padx=14, pady=(6, 12))
        tk.Button(bottom, text="📂  Browse for file…", bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  padx=12, pady=6, font=('Helvetica', 9), cursor='hand2',
                  command=lambda: self._te_browse_pack(win)).pack(side='left')
        tk.Button(bottom, text="Cancel", bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0,
                  padx=12, pady=6, font=('Helvetica', 9), cursor='hand2',
                  command=win.destroy).pack(side='right')

    def _te_browse_pack(self, picker_win):
        path = filedialog.askopenfilename(
            parent=picker_win,
            title="Select a tag pack JSON file",
            filetypes=[("Tag pack JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        # Ask mode
        choice = messagebox.askyesnocancel(
            "Apply pack",
            "How should this pack be applied?\n\n"
            "Yes  =  Replace your current vocabulary\n"
            "No   =  Merge into your current vocabulary\n"
            "Cancel = abort",
            parent=picker_win)
        if choice is None:
            return
        mode = "replace" if choice else "merge"
        self._te_load_pack_from_file(Path(path), picker_win, mode)

    def _te_load_pack_from_file(self, path, picker_win, mode):
        clean, errors, warnings = read_pack_file(path)
        if errors:
            messagebox.showerror("Could not load pack",
                                  "\n".join(errors), parent=picker_win)
            return
        if not (clean["energy_levels"] or clean["comment_tags"]):
            messagebox.showerror("Could not load pack",
                                  "The file contained no energy levels or tags.",
                                  parent=picker_win)
            return
        new_state, summary, apply_warnings = apply_pack(
            self._te_current_state(), clean, mode)

        # Confirmation summary.
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
            bits.append("⚠ " + w)
        bits.append("\nApply now? (Save & Apply in the editor still required to persist.)")

        if not messagebox.askokcancel("Confirm pack", "\n".join(bits), parent=picker_win):
            return

        self._te_apply_state(new_state)
        if picker_win and picker_win.winfo_exists():
            picker_win.destroy()
        self._msg(f"Pack loaded into editor: {meta_name}", ACCENT)

    def _te_export_pack(self):
        parent = self.tag_editor_win
        if not self._te_levels and not self._te_tags_by_cat:
            messagebox.showinfo("Nothing to export",
                                 "Add some energy levels or tags first.",
                                 parent=parent)
            return
        suggested = (self._te_meta.get("name") or "my-tag-pack")
        suggested = re.sub(r'[^a-zA-Z0-9]+', '-', suggested).strip('-').lower() or "tag-pack"
        path = filedialog.asksaveasfilename(
            parent=parent,
            title="Export tag pack",
            defaultextension=".json",
            initialfile=f"{suggested}.json",
            filetypes=[("Tag pack JSON", "*.json")])
        if not path:
            return
        data = {}
        if self._te_meta:
            data["_meta"] = dict(self._te_meta)
        data["energy_levels"] = list(self._te_levels)
        data["energy_colors"] = {k: self._te_colors.get(k, "#888888")
                                  for k in self._te_levels}
        data["comment_tags"] = {k: list(self._te_tags_by_cat.get(k, []))
                                  for k in self._te_cats}
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')
        except OSError as e:
            messagebox.showerror("Export failed", str(e), parent=parent)
            return
        self._msg(f"Exported pack: {Path(path).name}", ACCENT)

    def _te_edit_meta(self):
        parent = self.tag_editor_win
        win = tk.Toplevel(parent)
        win.title("Pack info")
        win.configure(bg=BG)
        win.geometry("480x340")
        win.transient(parent)

        tk.Label(win, text="PACK INFO", bg=BG, fg=ACCENT,
                 font=('Helvetica', 12, 'bold')).pack(anchor='w', padx=14, pady=(12, 2))
        tk.Label(win,
                 text="Optional — describes the pack when you export or share it.",
                 bg=BG, fg=FG2, font=('Helvetica', 9, 'italic'),
                 wraplength=440, justify='left').pack(anchor='w', padx=14, pady=(0, 10))

        entries = {}
        for key, label, multiline in [
            ("name",        "Pack name",   False),
            ("author",      "Author / handle", False),
            ("version",     "Version",     False),
            ("description", "Description", True),
        ]:
            row = tk.Frame(win, bg=BG)
            row.pack(fill='x', padx=14, pady=4)
            tk.Label(row, text=label, bg=BG, fg=FG2, width=16,
                     anchor='w', font=('Helvetica', 9)).pack(side='left')
            if multiline:
                txt = tk.Text(row, bg=BG2, fg=FG, height=4, width=30,
                              relief='flat', insertbackground=FG,
                              highlightthickness=0, font=('Helvetica', 10))
                txt.insert('1.0', self._te_meta.get(key, ""))
                txt.pack(side='left', fill='x', expand=True)
                entries[key] = ('text', txt)
            else:
                ent = tk.Entry(row, bg=BG2, fg=FG, relief='flat',
                                insertbackground=FG, highlightthickness=0,
                                font=('Helvetica', 10))
                ent.insert(0, self._te_meta.get(key, ""))
                ent.pack(side='left', fill='x', expand=True, ipady=4)
                entries[key] = ('entry', ent)

        def commit():
            new_meta = {}
            for key, (kind, w) in entries.items():
                v = w.get('1.0', 'end').strip() if kind == 'text' else w.get().strip()
                if v:
                    limit = MAX_DESC_LEN if key == 'description' else MAX_NAME_LEN
                    new_meta[key] = v[:limit]
            self._te_meta = new_meta
            win.destroy()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill='x', padx=14, pady=(10, 12))
        tk.Button(bottom, text="OK", bg=ACCENT, fg='white',
                  activebackground='#4bbfae', activeforeground='white',
                  relief='flat', bd=0, highlightthickness=0, padx=16, pady=6,
                  font=('Helvetica', 10, 'bold'), cursor='hand2',
                  command=commit).pack(side='right', padx=(8, 0))
        tk.Button(bottom, text="Cancel", bg=BG3, fg=FG,
                  relief='flat', bd=0, highlightthickness=0, padx=16, pady=6,
                  font=('Helvetica', 10), cursor='hand2',
                  command=win.destroy).pack(side='right')

    # ── WAV converter ──────────────────────────────────────────────────────────

    def _show_convert(self):
        """Open the WAV conversion dialog."""
        if self.convert_win and self.convert_win.winfo_exists():
            self.convert_win.lift()
            self.convert_win.focus_force()
            return

        wav_files = [f for f in self.files if f.suffix.lower() == '.wav']

        if not wav_files:
            self._msg("No WAV files to convert", FG2)
            return

        if not _has_ffmpeg():
            self._msg("ffmpeg not found — required for conversion", "#e74c3c")
            return

        win = tk.Toplevel(self)
        win.title("Convert WAV Files")
        win.configure(bg=BG)
        win.geometry("480x340")
        win.resizable(False, False)
        self.convert_win = win

        body = tk.Frame(win, bg=BG)
        body.pack(fill='both', expand=True, padx=20, pady=16)

        tk.Label(body, text="CONVERT WAV FILES", bg=BG, fg=ACCENT,
                 font=('Helvetica', 12, 'bold')).pack(anchor='w')
        tk.Label(body, text=f"{len(wav_files)} WAV file(s) found in current folder.",
                 bg=BG, fg=FG, font=('Helvetica', 10)).pack(anchor='w', pady=(6, 12))

        # Format selection
        tk.Label(body, text="TARGET FORMAT", bg=BG, fg=FG2,
                 font=('Helvetica', 9, 'bold')).pack(anchor='w', pady=(0, 4))
        fmt_var = tk.StringVar(value='flac')
        tk.Radiobutton(body, text="FLAC — lossless, compact, full tag support (Recommended)",
                       variable=fmt_var, value='flac',
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=FG, highlightthickness=0,
                       font=('Helvetica', 10)).pack(anchor='w')
        tk.Radiobutton(body, text="AIFF — lossless, full tag support, large files",
                       variable=fmt_var, value='aiff',
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=FG, highlightthickness=0,
                       font=('Helvetica', 10)).pack(anchor='w')
        tk.Radiobutton(body, text="MP3 — 320 kbps, smallest files, lossy",
                       variable=fmt_var, value='mp3',
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=FG, highlightthickness=0,
                       font=('Helvetica', 10)).pack(anchor='w')

        # Playback warning (shown for FLAC and AIFF)
        warn_lbl = tk.Label(body,
                            text="⚠ Note: FLAC/AIFF playback is not supported in this app "
                                 "(pygame limitation).\nYour tags will still be written "
                                 "and readable in Rekordbox.",
                            bg=BG, fg="#e67e22", font=('Helvetica', 9),
                            justify='left', wraplength=430)
        warn_lbl.pack(anchor='w', pady=(6, 0))

        def _update_warning(*_):
            if fmt_var.get() in ('aiff', 'flac'):
                warn_lbl.pack(anchor='w', pady=(6, 0))
            else:
                warn_lbl.pack_forget()
        fmt_var.trace_add('write', _update_warning)

        # Delete originals option
        del_var = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="Delete original WAV files after conversion",
                       variable=del_var,
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=FG, highlightthickness=0,
                       font=('Helvetica', 10)).pack(anchor='w', pady=(12, 0))

        # Progress
        progress_lbl = tk.Label(body, text="", bg=BG, fg=FG2,
                                font=('Helvetica', 10))
        progress_lbl.pack(anchor='w', pady=(10, 0))

        # Buttons
        btn_bar = tk.Frame(body, bg=BG)
        btn_bar.pack(fill='x', pady=(12, 0))

        convert_btn = tk.Button(
            btn_bar, text="Convert", bg=ACCENT, fg='white',
            activebackground="#4bbfae", activeforeground='white',
            relief='flat', padx=20, pady=8, bd=0, highlightthickness=0,
            font=('Helvetica', 10, 'bold'), cursor='hand2',
        )
        convert_btn.pack(side='left')

        def _do_convert():
            convert_btn.config(state='disabled', text="Converting…")
            fmt = fmt_var.get()
            delete = del_var.get()

            # Save any unsaved changes first
            if self.unsaved:
                self._save()

            # Stop player and unload to release file handles
            self._cancel_progress()
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

            def _worker():
                converted = 0
                skipped = 0
                failed = 0
                total = len(wav_files)

                for i, wav_path in enumerate(wav_files):
                    self.after(0, lambda i=i, t=total:
                               progress_lbl.config(
                                   text=f"Converting {i + 1} / {t}…"))
                    ext_map = {'flac': '.flac', 'aiff': '.aiff', 'mp3': '.mp3'}
                    out_path = wav_path.with_suffix(ext_map[fmt])

                    if out_path.exists():
                        skipped += 1
                        continue

                    try:
                        seg = AudioSegment.from_wav(str(wav_path))
                        if fmt == 'mp3':
                            seg.export(str(out_path), format='mp3',
                                       bitrate='320k')
                        elif fmt == 'flac':
                            seg.export(str(out_path), format='flac')
                        else:
                            seg.export(str(out_path), format='aiff')

                        # Copy tags from original to converted file
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
                        # Clean up partial output
                        if out_path.exists():
                            try:
                                out_path.unlink()
                            except Exception:
                                pass

                # Update UI on main thread
                parts = []
                if converted:
                    parts.append(f"{converted} converted")
                if skipped:
                    parts.append(f"{skipped} skipped (already exist)")
                if failed:
                    parts.append(f"{failed} failed")
                summary = ", ".join(parts) or "Nothing to convert"

                def _done():
                    progress_lbl.config(text=f"✓ {summary}")
                    convert_btn.config(state='normal', text="Convert")
                    self._reload_files()

                self.after(0, _done)

            threading.Thread(target=_worker, daemon=True).start()

        convert_btn.config(command=_do_convert)


if __name__ == '__main__':
    App().mainloop()
