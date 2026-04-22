# Tag Packs

A **tag pack** is a JSON file describing an energy/rating/comment-tag
vocabulary. Packs let DJs share tagging systems with each other and let
new users start from a sensible baseline instead of a blank palette.

## Bundled packs

| File | For |
|---|---|
| `minimal.json` | New users — energy + rating + Style + Mood. Grow it from there. |
| `open-format-wedding.json` | Open-format / weddings — broad styles, mood-heavy, crowd-led. |
| `house-techno.json` | House and techno DJs — focused subgenres and dance-floor vibes. |
| `hip-hop-rnb.json` | Hip-hop / R&B sets — era and feel-led. |
| `multilingual-global.json` | Global / multilingual sets — language and regional style tags. |

## Loading a pack

In the app: **🏷️ Tags → 📥 Load pack…**, then pick a bundled preset
(or **Browse for file…** to load a pack a friend has sent you). You'll
be asked whether to:

- **Replace** — your current vocabulary is replaced by the pack.
- **Merge** — the pack is added on top of your current vocabulary.

Nothing persists until you click **Save & Apply** in the editor, so
you can always experiment and cancel.

### Merge rules

- Existing energy levels and their order are preserved; new ones append.
- Existing energy colours are **never** overwritten — only new levels
  receive colours from the pack.
- For each comment-tag category, existing values and their order are
  preserved; new ones append.
- A tag value already present in **another** category is skipped (the
  app stores comment tags in a flat namespace, so the same string in
  two categories cannot be distinguished).
- Pack metadata (`_meta`) is **not** merged into your local pack info.

## File format

```json
{
  "_meta": {
    "name": "My Pack",
    "author": "Your name / @handle",
    "description": "One or two sentences explaining who this is for.",
    "version": "1.0"
  },
  "energy_levels": ["Start", "Build", "Peak", "Sustain", "Release"],
  "energy_colors": {
    "Start":   "#2d8659",
    "Build":   "#2471a3",
    "Peak":    "#c0392b",
    "Sustain": "#7d3c98",
    "Release": "#d68910"
  },
  "comment_tags": {
    "Style": ["House", "Disco"],
    "Mood":  ["Happy", "Chill"]
  }
}
```

All top-level keys are optional. Top-level keys starting with `_` are
reserved for future metadata; don't invent your own.

### Conventions

- **Filenames:** `kebab-case.json` (e.g. `house-techno.json`).
- **Display names** (in `_meta.name`): Title Case, short.
- **Tag values:** hyphenate multi-word tags (`Late-Night`, not `Late Night`).
- **Colours:** `#RRGGBB` only; invalid colours are ignored on import.

### Limits

To keep the GUI responsive, the loader caps imports at:

- File size: 256 KB
- Energy levels: 20
- Categories: 30
- Tags per category: 100
- Total tags: 600

## Contributing a pack

Two paths:

1. **Easy — open an issue.** Use the
   [Submit a tag pack](../../.github/ISSUE_TEMPLATE/submit-tag-pack.yml)
   issue template, attach your exported JSON, and a maintainer will
   commit it on your behalf.
2. **Direct — open a PR.** Add your file to `presets/`, update the
   table in this README, and ensure `_meta.name`, `_meta.author`, and
   `_meta.description` are filled in. Please test the pack via
   **Load pack… → your file** before submitting.

Submissions are accepted under the project's MIT licence.
