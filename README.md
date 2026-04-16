# track-tag-manager

A lightweight DJ tagging GUI that writes metadata **directly into your audio files** — so your tags survive re-imports, library moves, and new DJ setups.

Built for the [Little Data Lotta Love](https://www.reddit.com/r/DJs/comments/1brgng/little_data_lotta_love_a_beginners_guide_to/) tagging philosophy: tag every track richly so you can search and build sets on the fly.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Why

DJ software like Rekordbox stores custom tags (My Tags, cue points, etc.) in its own database — not in the audio file. Switch computers, re-import a track, or share files with another DJ and those tags are gone.

This tool writes standard metadata tags directly into MP3, WAV, AIFF, and FLAC files:

| Field | ID3 formats (MP3/WAV/AIFF) | FLAC (VorbisComment) | Rekordbox field |
|---|---|---|---|
| Energy level | `TCON` (Genre) | `GENRE` | Genre |
| Rating | `POPM` (Popularimeter) | `RATING` | Rating |
| Style / Mood / Vibe / etc. | `COMM` (Comment) | `COMMENT` | Comment |

After tagging, right-click any track in Rekordbox → **Reload Tags** and everything comes through.

> ⚠️ **WAV limitation:** Rekordbox does not read comment tags from WAV files — only Genre and Rating will show up. This is a Rekordbox limitation, not a bug in this tool. **MP3, AIFF, and FLAC files work fully.** Use the built-in converter (`🔄 Convert WAVs`) to convert to FLAC (recommended) or AIFF.
>
> **Windows File Explorer** also does not display ID3 comment tags reliably. Use a tool like [Mp3tag](https://www.mp3tag.de/en/) to verify tags outside of DJ software.

---

## Features

- Folder picker on launch — point it at any music folder
- Auto-plays each track as you select it
- Waveform scrubber with click-to-seek and time display
- Volume control
- Toggle buttons for energy, rating, and all comment tags
- Keyboard-first workflow: `Space` play/pause · `S` save · `Enter` save + next · `↑↓` navigate
- Tags written to file instantly on save, no library lock-in
- Untagged tracks marked with `●` in the file list for easy identification
- **Stats dashboard** (`📊 Stats`) — see how many tracks are tagged, energy/rating distribution, and top tags by frequency
- **WAV converter** (`🔄 Convert WAVs`) — batch convert WAV files to FLAC (recommended), AIFF, or MP3 with full tag preservation

---

## Installation

Requires Python 3.8+. [ffmpeg](https://ffmpeg.org/) is required for the WAV converter and waveform display.

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

| Format | Playback | Tagging | Rekordbox Comment tags |
|---|---|---|---|
| MP3 | ✅ | ✅ | ✅ |
| FLAC | ❌ (pygame limitation) | ✅ | ✅ |
| AIFF | ❌ (pygame limitation) | ✅ | ✅ |
| WAV | ✅ | ✅ | ❌ (Genre & Rating only) |

For best Rekordbox compatibility, **FLAC is the recommended lossless format** — it supports full metadata including comments, and produces smaller files than both WAV and AIFF.

### Recommended workflow

1. **Tag your tracks** in DJ Tag Manager (WAV playback works for previewing)
2. **Convert WAVs** → click `🔄 Convert WAVs` and choose FLAC
3. **Import/reload in Rekordbox** — all tags (Genre, Rating, Comments) will be visible

---

## License

MIT
