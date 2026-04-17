# track-tag-manager

A lightweight DJ tagging GUI that writes metadata **directly into your audio files** — so your tags survive re-imports, library moves, and new DJ setups.

Built for the [Little Data Lotta Love](https://www.reddit.com/r/DJs/comments/1brgng/little_data_lotta_love_a_beginners_guide_to/) tagging philosophy: tag every track richly so you can search and build sets on the fly.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Why

DJ software like Rekordbox stores custom tags (My Tags, cue points, etc.) in its own database — not in the audio file. Switch computers, re-import a track, or share files with another DJ and those tags are gone.

This tool writes standard metadata tags directly into MP3, WAV, AIFF, FLAC, and M4A files:

| Field | ID3 formats (MP3/WAV/AIFF) | FLAC (VorbisComment) | M4A (MP4 atoms) | Rekordbox field |
|---|---|---|---|---|
| Energy level | `TCON` (Genre) | `GENRE` | `©gen` | Genre |
| Rating | `POPM` (Popularimeter) | `RATING` | ★ in Comment | Rating |
| Style / Mood / Vibe / etc. | `COMM` (Comment) | `COMMENT` | `©cmt` | Comment |

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
| M4A | ❌ (pygame limitation) | ✅ | ✅ |
| WAV | ✅ | ✅ | ❌ (Genre & Rating only) |

For best Rekordbox compatibility, **FLAC is the recommended lossless format** — it supports full metadata including comments, and produces smaller files than both WAV and AIFF.

---

## Recommended workflow

A typical DJ prep workflow looks like this:

```
Download / buy tracks  →  Tag & convert  →  Import into Rekordbox
       (mixed formats)       (in any order)       (all tags visible)
```

**Step 1 — Collect tracks.** Download or purchase tracks into a prep folder (e.g. `To Prep`). These will be a mix of WAV, MP3, AIFF, and FLAC files — that's fine.

**Step 2 — Tag and convert (in either order).**

- **Option A: Tag first, convert after.** Open the folder in DJ Tag Manager, tag every track with energy, rating, style, mood, etc. Then click `🔄 Convert WAVs` to convert any WAV files to FLAC (recommended), AIFF, or MP3. Tags are preserved during conversion.

- **Option B: Convert first, tag after.** Convert your WAVs up front so all files are in a Rekordbox-compatible format. Then tag them — the app reads and writes tags to all supported formats.

Either order works. Tags are always preserved during conversion.

**Step 3 — Import into Rekordbox.** Drag the folder into Rekordbox. All tags (Genre, Rating, Comments) will be visible. For tracks already in your library, select them → right-click → **Reload Tags**.

**Step 4 — Archive or discard originals.** If you converted WAV files and kept the originals, you can safely archive or delete them — your tags live in the converted files.

> 💡 **Tip:** Tag while previewing — WAV files play directly in the app, so tagging before converting lets you listen and tag in one pass.

---

## License

MIT
