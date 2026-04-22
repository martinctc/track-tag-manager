# Contributing

Thanks for your interest in improving **track-tag-manager**! This is a small,
single-file Tk app maintained in spare time, so keeping contributions focused
and low-friction is the priority.

## Ground rules

- **Be kind.** Assume good intent.
- **One change per PR.** Smaller PRs get reviewed faster.
- **Don't commit `tags.json`.** It's user-local and intentionally `.gitignore`d.
  The defaults baked into `tag_manager.py` are the source of truth.
- **Don't commit audio files**, even small samples. Use file paths in tests
  pointing at files contributors generate locally.

## Running locally

Requires **Python 3.10+** and **ffmpeg** (for the WAV converter and the
waveform display).

```bash
# Install ffmpeg (one of):
#   macOS:    brew install ffmpeg
#   Windows:  winget install --id=Gyan.FFmpeg
#   Linux:    sudo apt install ffmpeg

python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows:     .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tag_manager.py
```

## Testing

There is no automated test suite yet. Changes are verified manually against a
folder of mixed MP3 / WAV / AIFF / FLAC / M4A files. If you're touching the
tag read/write paths, please:

1. Test on **all five formats**, not just MP3.
2. Round-trip a tag (write → close app → reopen → confirm it reads back).
3. Confirm Rekordbox (or your DJ software) still picks the tags up after
   **Reload Tags**.

Smoke tests around the `mutagen`-based read/write helpers would be very
welcome — open an issue first to discuss layout.

## Coding style

- Match the existing style in `tag_manager.py` (4-space indent, light comments,
  `# ─── Section ───` dividers).
- No new heavyweight dependencies without discussion — the install footprint is
  a feature.
- Keep the GUI keyboard-driven. New actions should have a sensible shortcut.

## Commit messages

Conventional-commit prefixes, lowercase description:

```
feat: add bulk re-tag from CSV
fix: preserve POPM rating when rewriting comments on MP3
perf: cache waveform peaks per file
docs: clarify WAV limitation in README
```

## Reporting bugs

Open an issue with:

- OS + Python version
- Audio file format and (if safe to share) a tiny sample that reproduces it
- Steps to reproduce, expected vs actual behaviour
- Anything from the terminal output

**If you find a bug that corrupts or destroys audio files, please email the
maintainer (see GitHub profile) before opening a public issue** so we can ship
a fix before others trip over it.
