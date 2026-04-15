# track-tag-manager

A lightweight DJ tagging GUI that writes metadata **directly into your audio files** — so your tags survive re-imports, library moves, and new DJ setups.

Built for the [Little Data Lotta Love](https://www.reddit.com/r/DJs/comments/1brgng/little_data_lotta_love_a_beginners_guide_to/) tagging philosophy: tag every track richly so you can search and build sets on the fly.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Why

DJ software like Rekordbox stores custom tags (My Tags, cue points, etc.) in its own database — not in the audio file. Switch computers, re-import a track, or share files with another DJ and those tags are gone.

This tool writes standard ID3 tags directly into MP3, WAV, and AIFF files:

| Field | Stored as | Rekordbox field |
|---|---|---|
| Energy level | `TCON` (Genre) | Genre |
| Rating | `POPM` (Popularimeter) | Rating |
| Style / Mood / Vibe / etc. | `COMM` (Comment) | Comment |

After tagging, right-click any track in Rekordbox → **Reload Tags** and everything comes through.

---

## Features

- Folder picker on launch — point it at any music folder
- Auto-plays each track as you select it
- Click-to-seek scrubber with time display
- Toggle buttons for energy, rating, and all comment tags
- Keyboard-first workflow: `Space` play/pause · `S` save · `Enter` save + next · `↑↓` navigate
- Tags written to file instantly on save, no library lock-in

---

## Installation

Requires Python 3.8+.

```bash
pip install -r requirements.txt
python tag_manager.py
```

---

## Tagging system

The included `DJ Tagging Reference.md` documents the default tag vocabulary — feel free to customise it to your own style. The vocabulary is defined in `tag_manager.py` under `COMMENT_TAGS` and is easy to edit.

**Default categories:**

| Category | Purpose |
|---|---|
| Energy | Set position — Start / Build / Peak / Sustain / Release |
| Rating | 1★ situational · 3★ reliable · 5★ essential |
| Style | Genre the track lives in |
| Mood | Emotional feel |
| Vibe | Energy texture |
| Crowd | How it lands |
| Vocals | Vocals / No-Vocals / Rap |
| Instruments | Distinctive instruments worth searching by |

---

## Format support

| Format | Playback | Tagging |
|---|---|---|
| MP3 | ✅ | ✅ |
| WAV | ✅ | ✅ |
| AIFF | ❌ (pygame limitation) | ✅ |

---

## License

MIT
