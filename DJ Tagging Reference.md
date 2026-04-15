# DJ Tagging Reference

## Field Structure

| Field   | Content          | Format                          |
|---------|------------------|---------------------------------|
| Genre   | Energy level     | One value only                  |
| Rating  | Track confidence | 1 / 3 / 5 stars only            |
| Comment | Everything else  | Space-separated, hyphenated     |

---

## Energy (Genre field — pick ONE per track)

| Tag       | When to use                                      |
|-----------|--------------------------------------------------|
| Start     | First hour, warming the room                     |
| Build     | Crowd is engaged, building toward peak           |
| Peak      | Full energy, floor is packed                     |
| Sustain   | Keeping energy high without pushing further      |
| Release   | Bringing it down, closing out                    |

---

## Rating

| Stars | Meaning                                          |
|-------|--------------------------------------------------|
| 1★    | Situational — works in the right moment, not a go-to |
| 3★    | Reliable — plays well in most sets               |
| 5★    | Essential — guaranteed for your crowd            |

---

## Comment Field Vocabulary

All tags go into the Comment field together, space-separated.
Multi-word tags are hyphenated (e.g. Beach-Vibes, not Beach Vibes).

### Style — what genre the track lives in
```
House  Disco  Funk  Pop  Hip-Hop  R&B  Latin  Afro  Electronic  Soul
Arabic  Desi  East-Asian
```

### Mood — the emotional feel
```
Happy  Chill  Sexy  Dark  Fun  Uplifting  Nostalgic  Emotional
```

### Vibe — the energy texture
```
Groovy  Bouncy  Driving  Anthemic  Melodic  Classic  Punchy
Deep  Smooth  Soulful  Tropical  Late-Night  Banging
```

### Crowd — how the track lands
```
Singalong  Dancefloor  Crowd-Pleaser  Beach-Vibes
```

### Vocals
```
Vocals  No-Vocals  Rap
```

### Instruments — only tag if distinctive enough to search by
```
Piano  Guitar  Horns  Bass-Heavy  Strings  Synth  Percussion  Organ
```

---

## Rules

1. Use this list only — no ad-hoc new tags mid-session or the search breaks
2. 3–7 tags per track is the sweet spot
3. Add new tags to this file first, agree on the word, then apply consistently

---

## Examples

**Sabrina Carpenter - Espresso (Sgt Slick's Discotizer ReCut)**
- Genre: `Build`
- Rating: 5★
- Comment: `Pop Disco Fun Bouncy Dancefloor Singalong Vocals`

**ANOTR & 54 ULTRA - Talk To You (D.X.D & UMANE Remix)**
- Genre: `Build`
- Rating: 3★
- Comment: `House Driving Melodic Deep Vocals Synth`

**Ultra Nate - Free (Sammy Porter Remix)**
- Genre: `Peak`
- Rating: 5★
- Comment: `House Happy Anthemic Classic Uplifting Dancefloor Vocals`

**Harry Styles - Watermelon Sugar (Mentol Cover Remix)**
- Genre: `Build`
- Rating: 3★
- Comment: `Pop Chill Happy Tropical Beach-Vibes Vocals Melodic`
