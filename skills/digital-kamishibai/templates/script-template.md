# Script template

How to use this file: copy the block under **Template** into the work's `script.md` and fill it in the maker's language.
**Do not translate** `[Slide N]`, the bracketed cue keywords or the words on a `[Text]` line — tools read them exactly.

The full definition of the format is `docs/work-format.md` in the Digital Kamishibai repository
(§2 for `script.md`). This page is a summary for writing; if the two ever disagree, `work-format.md` is right.

## Notation

| Kind | How to write | Who sees it |
|---|---|---|
| Header | everything before the first slide: `# Title`, then `> Language: xx` (for example `en`, `ja`) | the family only |
| Slide heading | `## [Slide N] Title` — N starts at 1 and goes up by 1, no gaps | — |
| Narration | plain text | the narrator, who says it aloud |
| A hole's narration | `~ ` at the start of each line (`~ My favourite was ...`) | the narrator, who says it aloud — highlighted, as words they may replace with their own |
| Free cue | a `>` line without a bracketed keyword (`> Wait until everyone is looking.`) | the narrator's eyes |
| Machine cue | `> [Keyword] ...` (below) | tools act on it |
| Words on the screen | a `> [Text]` block (below) | listeners, on the picture |
| Production note | `<!-- ... -->` | **nobody at the show** — for the people making the work |
| End of slide | a line that is exactly `---` | — |

- **Line breaks are kept exactly.** Blank lines and short lines are where the narrator breathes and pauses.
- Consecutive `>` lines are one block; the first line decides what kind of block it is.
  Put a blank line between cues, so each cue is its own block.
- A production note must be closed (`-->`), or everything after it disappears from the narrator's screen.

### Machine cues

| Cue | Meaning |
|---|---|
| `> [Picture] pictures/03.jpg` | the picture of this slide. Without it: `pictures/NN.jpg` (NN = slide number, two digits) |
| `> [BGM] sounds/sea.mp3` | music from this slide on, looping, until the next `[BGM]` or `[BGM stop]` |
| `> [BGM once] sounds/theme.mp3` | music that plays once, then silence |
| `> [BGM after video] sounds/theme.mp3` | music that plays once, starting when this slide's video has ended (the slide needs a `[Video]`) |
| `> [BGM stop]` | fade the music out |
| `> [Sound] sounds/bell.mp3` | a sound, once, when the slide opens |
| `> [Video] videos/ending.mp4` | a video the narrator starts by pressing play |
| `> [Video] https://youtu.be/⟨id⟩ start 5:51 end 6:09 captions ja` | a video published on YouTube, played from YouTube on every device from `start` to `end`, with captions in that language shown from the start (all three optional; listeners cannot turn captions on themselves). Nothing is packed. Each device needs the internet, and it does not play when its owner does not allow other sites — write what to say when it cannot be played |

At most one `[Picture]` and one `[BGM]` / `[BGM once]` / `[BGM after video]` / `[BGM stop]` per slide. Paths use `/`.

### Words on the screen: `[Text]`

One `[Text]` block is one text box on the picture. The `>` lines after the `[Text]` line are its words;
a line that is only `>` separates paragraphs. Leave a blank line after the block.

```markdown
> [Text] place top size 54pt bold
> The storm
>
> that night

> [Text] left 0.50in top 6.30in width 4.00in height 0.80in size 28pt align left
> Winter, long ago
```

On the `[Text]` line, in any order:

| Words | Meaning | If missing |
|---|---|---|
| `place top` / `place middle` / `place bottom` | a band across the slide | — |
| `left` `top` `width` `height` (inches: `0.50in`) | the box. All four, or `place` instead | — |
| `size 54pt` | size of the words | `40pt` |
| `bold` | bold | not bold |
| `align left` / `center` / `right` | | `center` |
| `anchor top` / `middle` / `bottom` | where short words sit in the box | `middle` |
| `color #RRGGBB` | colour of the words | `#000000` |
| `fill #RRGGBB` | a band of colour behind the words | none |

The slide is 16:9, 13.333 × 7.5 inches. Keep words on the screen short: a title, a label, a year, a number.
They are for the eye; **they are not the narration written out**.

### Length

Estimate the length from the narration only (cues and notes do not count):
about **140 words a minute** in English (a general figure for reading aloud), about **290 characters a minute**
in Japanese (measured at family performances, pauses and slide changes included). Add the length of every video.
Music that must play to its end on a slide takes as long as the music, however fast the narrator reads.
The figures are estimates for the plan, not a target for the narrator.

## Template

Holes are marked with a production note, so they never reach the narrator's screen.
A hole may stay empty: write the slide so that it stands without it, and delete the note if it is never filled.
When a hole has stand-in narration that someone else may tell their own way (a sample, a script another person
narrates), start each of its lines with `~ `: the narrator's screen highlights it, so the narrator sees what they may
replace. It is still read aloud. Take the mark off once the maker's own words are in and are not to be changed.

```markdown
# ⟨Title⟩

> Language: ⟨xx⟩

<!-- Plan: ⟨where the plan is⟩. Target: about ⟨N⟩ minutes including videos, ⟨N⟩ words / characters. -->

## [Slide 1] ⟨Cover⟩

> [Picture] pictures/01.jpg

> [BGM] sounds/⟨opening⟩.mp3

> [Text] place middle size 60pt bold
> ⟨Title as shown on the screen⟩

<!-- Hole: the listener is there — something the listener loves (for a group, something the room shares), in the picture or the music, not by name. -->

⟨Narration. A question the story will answer near the end.⟩

---

## [Slide 2] ⟨Title⟩

⟨Narration.⟩

<!-- Hole: the maker's own stumble — first person, unfinished, unflattering. Empty is fine. -->

---

## [Slide 3] ⟨Title⟩

> [Sound] sounds/⟨sound⟩.mp3

⟨Narration.⟩

> ⟨Free cue for the narrator, for example: wait for the sound to end.⟩

---

## [Slide ⟨N⟩] ⟨Last slide⟩

> [Video] videos/⟨ending⟩.mp4

<!-- Hole: the family's record on one song — photos and videos, from the beginning until now. -->

⟨A few words, then stop. No explanation, no punch line.⟩
```
