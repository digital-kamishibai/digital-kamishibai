# Work format (v1, first draft)

This is the **only** definition of what a kamishibai *work* looks like on disk.
Three tools follow it and nothing else:

| Tool | Role |
|---|---|
| Builder (`skills/digital-kamishibai/scripts/build_work.py`) | writes `work.json` from `script.md` |
| Room player (`player/`) | reads `work.json` and the media files |
| Exporters of older works (outside this repository) | write `work.json` and media |

To change the format, change this file first, then the tools.
All three are tested against the same example, [`examples/sample-story/`](../examples/sample-story/).

Status: **v1, first edition (2026-10-22)**; `[BGM once]` added 2026-10-24 (player stage 4). Several `[Video]` on one slide allowed 2026-10-24 (the narrator picks which one to play). `overlays`, `draft` and the correction sheet (§6) added 2026-10-25 (practising and correcting in the player). `slide_size`, `overlay_base`, `overlay_layout` and the `layout` correction added 2026-10-25 (moving the words on the picture). `[Text]` (words on the screen, written in `script.md`, §2.6) added 2026-10-25, and drawn into the picture by the builder the same day. `role`, `seats` and `source_segments` of a video (§3.3) and the `picture`, `video K` and `ending seat N` corrections (§6) added 2026-10-26 (pointing at pictures and videos while practising). `[BGM after video]` added 2026-10-29 (music that the old works start by a click once the video is over). `Use` of a `picture` correction (choosing a candidate in the player) added 2026-10-29. `color` and `fill` of a `layout` correction, the colour of a box and the light-against-dark guide (§3.2) added 2026-10-30 (correcting the colours of the words on the picture). `picture_source` of a slide (§3.2) added 2026-11-01 (a picture correction was taken as changed after a rebuild). `[Video]` with a YouTube link — a **linked video** (§2.4, §3.3) — added 2026-11-09, and its `captions` the same day (listeners cannot choose captions themselves), (a work handed out to other families shows published videos without packing them, and listeners on their own devices see them too). Music that is too loud is played quieter (§4) from 2026-11-09 (a song from a CD put in place of a sample's music drowned out the narration). `volume` of a linked video added 2026-11-10 (a talk on YouTube played about 6 dB louder than the video files beside it, and the player cannot measure it). Covers what stage 1 of the player needs (pictures, slide order, narrator notes)
and fixes the shape of sound and video cues. Size limits for video are provisional until stage 2 measures them.

**Not in v1** (decided, not forgotten): sound effects the narrator triggers by tapping, and music volume per slide.
Sounds play when a slide opens; music plays at one volume (a song that is too loud is played quieter, §4) and fades out when a video starts. It does not come back after the video: the next music starts at the next `[BGM]`. (`[BGM after video]` is the one music that waits for a video and starts when it ends.)

---

## 1. Two parts: text and media

A work has two parts that travel separately.

| Part | What | Made by | Goes where |
|---|---|---|---|
| **Text** | `work.json` (and its source, `script.md`) | the builder, or a chat AI | anywhere — it holds no pictures |
| **Media** | pictures, videos, music, sound effects | the family | **stays on the family's own devices** |

The player puts them together: the narrator opens `work.json` and picks the folder that holds the media.
Files are matched by the relative paths written in `work.json`.

Why split: family photos and videos should never have to be uploaded anywhere — not to a chat AI to be packed,
not to a server to be shown. A chat AI only ever needs to produce text.

A **linked video** (§2.4) is the one exception to "media are files": it is a link to a video already published on
YouTube, written in the text. It is not a file at all, so nothing is sent between devices for it.

### Folder layout (recommended, not required)

```
my-story/
├── work.json
├── script.md          (source; the player does not read it)
├── pictures/          01.jpg, 02.jpg, ...
├── videos/
└── sounds/            music and sound effects
```

Text and media may also sit in two different folders; only the relative paths inside `work.json` matter.

### Zip

The player also accepts a `.zip`:

- `work.json` at the root of the zip, or inside exactly one top-level folder.
- Media may be in the same zip **only when the zip was made on the family's own device.**
  A zip from a chat AI holds `work.json` (and `script.md`) only.
- Paths in `work.json` are resolved inside the zip first, then in the media folder the narrator picks.

---

## 2. `script.md` — the source the family writes

Plain Markdown. Everything before the first slide heading is the **header**.

### 2.1 Header

```markdown
# The Lighthouse Keeper's Lamp

> Language: en
```

- `# Title` — the first level-1 heading is the work's title. Required.
- `> Language: xx` — optional BCP 47 tag (`en`, `ja`, ...). If missing, the builder guesses from the text.
- Any other header lines are free notes for the family. Nothing in the header reaches the narrator's screen.

### 2.2 Slide heading

```markdown
## [Slide 3] The storm
```

- `[Slide N]` is a **fixed marker. Do not translate it.** The title after it may be in any language.
- Numbers start at 1 and go up by 1, with no gaps and no repeats.
- A script with **no** slide headings is an error. The builder stops; it never writes an empty work.

### 2.3 Inside a slide

| Kind | How to write | On the narrator's screen | Sent to listeners |
|---|---|---|---|
| Narration | plain text | yes | **never** |
| A hole's narration | `~ ` at the start of each line (below) | yes, as narration, **highlighted** | **never** |
| Free cue (for the narrator's eyes) | a `>` line not listed below | yes, marked as a cue | never |
| **Machine cue** | `> [Keyword] ...` (§2.4) | yes, marked as a cue | the player acts on it |
| Production note | `<!-- ... -->` | **no** | never |
| End of slide body | a line that is exactly `---` | — | — |

- **Line breaks are kept exactly as written.** Blank lines and short lines are where the narrator breathes
  and pauses. No tool may re-wrap or join lines.
- A `>` line is either a machine cue or a free cue. Consecutive `>` lines are one block; the **first line**
  decides which it is.
  - A block that starts with a machine cue may hold more machine cues, one per line (`[Text]` is the exception:
    its block holds its words, §2.6). Any other line in it is an error.
  - A block that starts with a free cue may not hold a machine cue on a later line — it would silently do nothing.
    That is an error too. Put a blank line between them.
- **A hole's narration** is narration a maker or a narrator may replace with their own (a sample's hole: their own
  ingredient, their own stumble). It is **read aloud** like any narration, so it is not a cue: it starts with `~ `
  (a half-width tilde and a space), on **every line** of the paragraph. The mark is not said and not shown as text;
  the narrator's screen shows the words as usual, on a light highlighter-yellow background.

  ```markdown
  ~ My favourite was the banana,
  ~ because it tastes like the morning.
  ```

  - When the hole is filled with the maker's own words and nobody should change it any more, the mark comes off.
  - A line that starts with `～ `, `〜 ` (full-width) or with `~` and no space is plain narration; the builder warns.

### 2.4 Machine cues

Keywords are fixed English words in square brackets. **Do not translate them.**
Paths are relative to the media folder and use `/`.

| Cue | Meaning |
|---|---|
| `> [Picture] pictures/03.jpg` | the picture for this slide (see §2.5) |
| `> [BGM] sounds/sea.mp3` | start this music when the slide opens; it loops and **keeps playing across slides** until the next `[BGM]` or `[BGM stop]`. Switching crossfades |
| `> [BGM once] sounds/theme.mp3` | like `[BGM]`, but it plays **once** and then stays silent (no loop). For music already cut to the length of its slides, such as the exporter of older works writes |
| `> [BGM after video] sounds/theme.mp3` | like `[BGM once]`, but it starts **when this slide's video has played to its end**. Until then the slide is silent (the music before it fades out when the slide opens). If the narrator moves on without playing the video, it starts on the next slide. The slide must have a `[Video]`. For music that the old works start by a click after the video |
| `> [BGM stop]` | fade the music out when the slide opens |
| `> [Sound] sounds/bell.mp3` | play once when the slide opens |
| `> [Video] videos/ending.mp4` | this slide has a video. It starts when the **narrator presses play** — never by itself. Music fades out when it starts and does not come back after it (the next `[BGM]` starts music again). A slide may have **several** (see below) |
| `> [Video] https://www.youtube.com/watch?v=ID start 5:51 end 6:09 captions ja volume -6dB` | a **linked video**: a video published on YouTube, played from YouTube on every device (below). `start`, `end`, `captions` and `volume` are optional |
| `> [Text] place top size 54pt bold` | words drawn on the picture. The `>` lines that follow are the words. See §2.6 |

- At most one `[Picture]` and one `[BGM]`/`[BGM once]`/`[BGM after video]`/`[BGM stop]` per slide. Any number of `[Sound]`, `[Video]` and `[Text]`.
- Several `[Video]` on one slide: the narrator's screen lists them **in the order written** and the narrator picks which one to play. Nothing plays the next one by itself — to show two videos one after the other, the narrator presses play on each.
- A slide with `[Video]` may have no picture; before the video is played, the player shows the first frame of the slide's first video (on a device that has not received the video yet, the screen stays black).

**Linked videos.** `[Video]` followed by a YouTube link (a line whose argument starts with `http://` or `https://`)
is a linked video. Use it for a video someone else published, which the work may point at but not pack (a talk, a
broadcast). It plays and stops like a video file: the narrator presses play, pause and seeks, every listener's
device follows, music fades out when it starts, and `[BGM after video]` starts when it reaches its end.

```markdown
> [Video] https://www.youtube.com/watch?v=8KkKuTCFvzI start 5:51 end 6:09
```

- The link: `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/embed/`, `youtube.com/shorts/` or
  `youtube-nocookie.com/embed/`. Only YouTube. Copy it from the video's **Share** button.
- After the link, optionally `start <time>` and `end <time>`, in that order of words or the other; each at most once.
  A time is seconds (`351`, `351.5`) or minutes and seconds (`5:51`, `1:05:51`). The video plays from `start`
  (missing: from the beginning) and **stops at `end`** (missing: at the end of the video).
- Optionally `captions <language>` (a language code: `ja`, `en`, `pt-BR`): every device shows that language's
  captions from the start. Listeners' devices have no buttons on the video, so this is the only way they get captions;
  the narrator can still change them on the narrator's screen. Nothing shows when the video has no captions in that
  language, and YouTube does not always obey (check it once before the show).
- Optionally `volume <dB>` (`volume -6dB`): play this video that much **quieter** on every device, from `0dB` down to
  `-40dB` (a linked video cannot be made louder). Video files are made the same loudness when they are exported (about
  −22 LUFS), but a linked video plays with YouTube's own sound, and YouTube only turns down videos louder than about
  −14 LUFS — so linked videos differ by up to about 10 dB, and the player cannot measure them. When one sounds too loud
  next to the others, write how much quieter by ear; if you know its loudness (LUFS) over the stretch played, write the
  difference (−16 LUFS against −22 LUFS: `volume -6dB`). The day's video volume knob still works on top of it.
  The player hands YouTube's player `setVolume(n)` with `n = knob × 10^(dB/20) × 100`, rounded; `setVolume(n)` sets the
  embedded `<video>`'s `volume` to `n/100`, which scales the sound wave (measured with the real YouTube player for every
  `n` from 0 to 100, 2026-11-10). So `-6dB` is `50`, `-10dB` is `32`, `-20dB` is `10`, `-40dB` is `1`.
- A link may carry its own start and end (`?t=351`, `&start=351&end=369`, as YouTube's share and embed links do).
  They are read too, but a time may not be both in the link and after it.
- It stops at `end` and stays on that frame; it never runs on into YouTube's suggestions. Only one stretch per line:
  to skip a part in the middle, write two `[Video]` lines with the same link and two stretches.
- **Every device needs the internet** to play it, and plays it from YouTube itself. It does not work when the owner
  of the video does not allow it to be played on other sites, when the video is taken down (links often stop
  working within a few years), or on a device that cannot reach YouTube. The narrator's screen says so, for this
  device and for each listener, and the narrator goes on with words: **write in the slide what to say when the video
  cannot be played.**
- YouTube may show an advertisement before the video, and its own title and buttons when the video is paused.
- A chat AI can write a linked video (it is text), but it should take the link from the person, not guess one.

### 2.5 Pictures without `[Picture]`

If a slide has no `[Picture]` cue, the picture is `pictures/NN.jpg`, where `NN` is the slide number
with two digits (`01`, `02`, ... `99`, then `100`).

- A builder that can see the media folder writes the real file name (for example `pictures/03.png`).
- A chat AI cannot see the photos, so it writes `pictures/03.jpg`. If that file is missing,
  the player tries the same name with the other picture extensions (§4) before reporting it missing.

### 2.6 Words on the screen: `[Text]`

Words that listeners see **on the picture** (a title, a label, a year) are written in the slide, next to the narration,
so the script stays the one source of the work. One `[Text]` block is one text box.

```markdown
## [Slide 2] The storm

> [Picture] pictures/02.png

> [Text] place top size 54pt bold
> The storm
>
> that night

> [Text] left 0.50in top 6.30in width 4.00in height 0.80in size 28pt align left
> Winter, long ago

One winter night, the wind was so strong
that the windows sang.
```

**The words.** The `>` lines after the `[Text]` line, up to the first line that does not start with `>`.
The leading `>` and one space after it are removed; the rest of each line is kept exactly.

- They are written the same way as an overlay in the correction sheet (§6): the lines of a paragraph are lines;
  paragraphs are separated by **one line that is only `>`**; an empty paragraph is a `>` line between two such lines.
- Leave a line that does not start with `>` (usually a blank line) between a `[Text]` block and the next cue or block.
  A word line that looks like a machine cue (`> [Picture] ...`) is an error: it means the blank line was forgotten.
- `**` and other Markdown are not read: the words are drawn as written.
- Boxes are numbered in the order they are written. This is the `B` of `overlay B` and `layout B` in the correction sheet.

**Where and how big** — words after `[Text]` on the same line, in any order:

| Words | Meaning | If missing |
|---|---|---|
| `place top`, `place middle`, `place bottom` | a band across the slide (below) | — |
| `left 0.50in` `top 0.30in` `width 12.33in` `height 1.10in` | the box, in inches, up to two decimals. Write **all four, or none** (then `place`) | — |
| `size 54pt` | size of the words, whole points. All paragraphs of the box | `40pt` |
| `bold` | bold | not bold |
| `align left`, `align center`, `align right` | | `center` |
| `anchor top`, `anchor middle`, `anchor bottom` | where the words sit when they are shorter than the box | `middle` |
| `color #RRGGBB` | colour of the words | `#000000` |
| `fill #RRGGBB` | a band of colour behind the words | no fill |

- Write either `place` or the four lengths. Neither, both, or only some of the four is an error.
- The slide is **16:9, 13.333 × 7.5 inches**. Bands of `place` are `left 0.50in`, `width 12.33in`, `height 1.20in`, at
  `top 0.30in` (top), `top 3.15in` (middle) or `top 6.00in` (bottom).
- The units are the ones the correction sheet uses (`left 0.50in`, `size 32pt`, §6), so a `layout B` correction is written
  back by replacing the same words on the `[Text]` line, or **adding** the word when the line does not have it yet
  (a box with no `size` or `color` uses the default above). A box written with `place` that is moved or resized gets
  all four lengths instead of `place`. `fill none` in a correction means "no band": the `fill` word is **removed** from
  the line (`fill none` is not a value the `[Text]` line takes).
- Not written here, decided by the tool that draws the words: the font (by the work's language), the space between
  the edge of the box and the words, and wrapping (long lines always wrap at the width of the box).

**What the builder makes of it.** The builder draws the words into the picture (§3.2 *Drawing*, with the same code the
player uses for its draft) and writes the result to `pictures/_built/NN.jpg` (1920 × 1080). The slide's `picture` points
there; the original picture is never changed. Only slides with `[Text]` get a built picture.

- The picture is fitted into the 16:9 slide: if its shape differs from 16:9 by 2% or less, it is stretched to fill;
  otherwise it is shown whole on black (nothing is cut off).
- With `--draft` (a version for practising, §6) the builder also writes `draft: true`, `slide_size`
  (`12192000` × `6858000`), and for each slide with `[Text]`: `overlays` (the words, read as in §6: lines are lines,
  paragraphs are separated by one blank line), `overlay_layout`, `overlay_base` = `pictures/_built/NN.base.jpg`,
  the same fitted picture **without** the words, and `picture_source` = the original picture (when there is one).
- `overlay_layout` from a `[Text]` line: lengths × 914400 (EMU); `inset` 0.10 / 0.05 inch (`[91440, 45720, 91440, 45720]`);
  `wrap` true; one paragraph entry per paragraph with `space_before` 0 and the box's `size`, `bold`, `align`, `color`;
  `font` by the work's language (`ja` Meiryo, `ko` Malgun Gothic, `zh` Microsoft YaHei, others Arial); `fill` when written.

---

## 3. `work.json` — what the player reads

UTF-8 JSON. The builder writes it from `script.md`; a person never needs to edit it.

```json
{
  "format": "digital-kamishibai/work",
  "version": 1,
  "title": "The Lighthouse Keeper's Lamp",
  "language": "en",
  "slides": [
    {
      "number": 1,
      "title": "Cover",
      "picture": "pictures/01.jpg",
      "notes": "Tonight's story is about a lamp.\n\nWho do you think lit it?",
      "cues": [
        { "type": "bgm", "file": "sounds/sea.mp3" }
      ]
    }
  ]
}
```

### 3.1 Top level

| Field | Required | Meaning |
|---|---|---|
| `format` | yes | always `"digital-kamishibai/work"` |
| `version` | yes | `1`. A player refuses a version it does not know, with a message |
| `title` | yes | from `# Title` |
| `language` | yes | BCP 47 tag |
| `slides` | yes | at least one slide, in order |
| `draft` | no | `true` means **a version before it is handed out** (for practising and correcting). Write it only when it is `true`; never write `false`. A player shows a banner on a draft and turns on correcting (§6). Players must not read anything inside `origin` for this |
| `slide_size` | with `overlay_layout` | `{"width": W, "height": H}`: the size of a slide in **EMU** (1 inch = 914400 EMU; a 16:9 slide of 13.333 × 7.5 inches is `12192000` × `6858000`). Required when any slide has `overlay_layout` |
| `origin` | no | free object for the tool that made the work (for example the original title and export date of an older work). Players ignore it. **Must not contain anything that identifies a family** |

### 3.2 A slide

| Field | Required | Meaning |
|---|---|---|
| `number` | yes | 1, 2, 3, ... matching the position in `slides` |
| `title` | yes | the text after `[Slide N]` (may be empty) |
| `picture` | yes, or `null` | path of what listeners see. `null` only on a slide with a video cue |
| `background` | no | path of the same picture **without text drawn on it**, for remaking the work. Players ignore it |
| `notes` | yes | narration and free cues as plain text (below). May be empty |
| `cues` | yes | machine cues in the order written. May be empty |
| `overlays` | no | the words drawn on top of the picture, **as text**, for the narrator's screen only (below). Missing when the words are only inside the picture |
| `overlay_layout` | no | where and how each box of `overlays` is drawn, for the narrator's screen only (below). Only with `overlays` |
| `picture_source` | no | path of the picture that `picture` was **built from** (the `[Picture]` file the builder drew the words on, §2.6), written with `--draft`. The narrator's screen tells by this file whether the picture itself changed (§6 `picture`); the built picture changes at every build. Players never send it to listeners |
| `overlay_base` | with `overlay_layout` | path of the picture **as the slide software draws it with the overlay boxes taken away** (everything else — shapes, lines, small pictures — stays); for a work built from `[Text]`, the builder's fitted picture without the words (§2.6). The narrator's screen draws the boxes on top of it to move them. Players never send it to listeners |

**`notes`** is the slide body turned into plain text, in this order:

1. Remove production notes. A line that holds **only** a production note is removed **with its line break**;
   a note inside a line is removed and the rest of the line stays.
2. Remove machine cue lines (§2.4), each with its line break. For `[Text]`, the whole block (its words too).
3. Remove `**` around bold text. **Keep the leading `> ` of free cues**, so the player can show them as cues
   rather than as words to read aloud. (A tool that writes speaker notes for slides, such as the `--pptx` export,
   may remove it there.) **Keep the leading `~ ` of a hole's narration too** (§2.3), so the player can highlight it
   and a correction sheet's paragraphs match `script.md`. It is a mark, not words: a player shows the line without it,
   and a tool that writes the notes out as text to read (speaker notes, a printed script) **must remove it**.
4. **Only if something was removed in steps 1–2**: where blank lines now run two or more in a row,
   make them one blank line. (A note between two paragraphs would otherwise leave a wider gap than
   the writer made. If nothing was removed, the writer's blank lines stay exactly as they are.)
5. Trim blank lines at the start and the end.

Nothing else changes: line breaks are kept exactly (§2.3).
**Notes are for the narrator's device only. A player must never send them to a listener's device** —
not even hidden. This is checked on the data, not on the screen.

**`overlays`** is three lists nested inside each other: **text boxes → paragraphs of a box → lines of a paragraph**.
A new line inside a paragraph is a line break that does not start a new paragraph (Shift+Enter in slide software).

```json
"overlays": [[["line 1", "line 2"], ["paragraph 2"]], [["the words of box 2"]]]
```

Box 1 has two paragraphs (the first one has two lines); box 2 has one paragraph.

- Boxes are in the order they sit on the slide. A box with no words is **not** listed, so box numbers count only boxes with words.
- **Empty paragraphs stay** (`[""]`): some works use them for spacing.
- Each box has at least one paragraph, and each paragraph at least one line.
- The words are already on the listeners' picture. `overlays` exist so the narrator can read and correct them (§6).
  **Like `notes`, a player must never send `overlays` to a listener's device.** This is checked on the data.

**`overlay_layout`** has one entry per box of `overlays`, in the same order (so it has the same length).
Lengths are integers in EMU, measured on a slide of `slide_size`; sizes of letters are in points.

```json
"overlay_layout": [{
  "x": 457200, "y": 502920, "width": 11247120, "height": 1005840,
  "inset": [91440, 45720, 91440, 45720],
  "anchor": "top", "wrap": true,
  "paragraphs": [{ "align": "center", "space_before": 0, "size": 54, "bold": true, "color": "#7A4518", "font": "Meiryo" }]
}]
```

| Field | Required | Meaning |
|---|---|---|
| `x`, `y`, `width`, `height` | yes | the box: top-left corner and size, before rotation |
| `rotation` | no | degrees, clockwise, around the centre of the box. Missing means 0 |
| `inset` | yes | `[left, top, right, bottom]`: the space between the edge of the box and the words |
| `anchor` | yes | `"top"`, `"middle"` or `"bottom"`: where the words sit when they are shorter than the box |
| `wrap` | yes | `true`: long lines wrap at the width of the box. `false`: they do not |
| `shape` | no | `"rect"` (missing means this) or `"roundRect"`. A round rectangle also has `corner`: the radius as a part of the shorter side (0 to 0.5), and the words sit inside the rounded edge (inset by `corner × shorter side × 0.29289` on each side, added to `inset`) |
| `fill` | no | `"#RRGGBB"`: the box is filled with this colour (a band behind the words). Missing means no fill |
| `outline` | no | `{"color": "#RRGGBB", "width": W}`: a line around the box. Missing means none |
| `paragraphs` | yes | one entry per paragraph of the box in `overlays`: `align` (`"left"`, `"center"` or `"right"`), `space_before` (points, added above every paragraph except the first), `size` (points), `bold`, `color` (`"#RRGGBB"`), `font` (the font the slide software actually used — when the slide names none, the theme's) |

Every value is **the one the slide software actually draws** — a value the box inherits (from the paragraph, the
theme, ...) is written out, never left for the player to look up.

**Drawing.** A player draws the words so that they land where the slide software put them:
one line is **1.2 × `size`** high; **an empty paragraph is one line high**; `space_before` is added above each paragraph
but the first; the words are laid out inside the box minus `inset` (and minus the rounded edge), then placed by `anchor`.
Drawn this way with the same font, the words land within a few pixels of the slide software's own picture
(1920 px wide; measured on 157 boxes of 7 works, 2026-10-25). The drawing on the narrator's screen is a **draft for
moving the words**: what listeners see is always the picture drawn by the slide software — or, for a work built from
`[Text]` (§2.6), by the builder with this same drawing, so the draft and the listeners' picture match.
**Like `overlays`, a player must never send `overlay_layout` or `overlay_base` to a listener's device.**

**The colour of a box** (for the `color` of a `layout` correction, §6) is the `color` of its paragraphs **that have
words** (a paragraph whose lines in `overlays` are all empty or spaces does not count: an empty paragraph may inherit
another colour, and it draws nothing). When those paragraphs have different colours, the box has no single colour and
its colour cannot be corrected in the player (ask for it in a comment).

**Light against dark** (a guide shown while correcting colours, §6). Brightness is `0.299 R + 0.587 G + 0.114 B`
(0–255). The background of a box is its `fill` when it has one; otherwise the mean brightness of `overlay_base` inside
the box (the rectangle `x`, `y`, `width`, `height`, rotation ignored). The difference is the background's brightness
minus the brightness of the box's colour, taken without its sign. **Below 70, the words may be hard to read.** It is a
guide, not a rule: a mean cannot see a background that is half dark and half light. A player marks a box below 70 and
never stops the narrator from choosing a colour. A tool that checks a work with the same numbers reads the same
`overlay_base`, so that it shows the same value.

### 3.3 Cues

| `type` | Fields |
|---|---|
| `"bgm"` | `file`, and `loop: false` for `[BGM once]` (missing means it loops). `[BGM after video]` is `loop: false` with `start: "after-video"` (missing `start` means it starts when the slide opens) |
| `"bgm-stop"` | — |
| `"sound"` | `file` |
| `"video"` | `file`, and optionally `role`, `seats`, `source_segments` (below). A linked video has `url` instead of `file`, and optionally `start` and `end` (below) |

`[Picture]` is not a cue in `work.json`; it becomes the slide's `picture`.

**A video cue may say more about the video**, so the narrator can point at a part of it while practising (§6).
`script.md` has no words for this: the tool that writes `work.json` fills it in from what it knows. The builder
writes `role` and `seats` only for a draft (`--draft`), for a `[Video]` that is the output of the work's ending video
definition (`ending_video*.json`). A cross-fade between two seats is split at its middle, so a seat is where its
own picture is the one mostly seen.

| Field | Meaning |
|---|---|
| `role` | `"ending"`: the video was put together from pictures on a song (the ladder's ending video). Missing means a video shown during the story |
| `seats` | only with `role: "ending"`, and may be missing even then (an ending made in an editing app has none). The places on the video's timeline, one per seat of the ending video's definition, in order: `{"n": 1, "from": 4.2, "to": 10.2}`. `n` counts from 1 by one; `from` and `to` are **seconds from the start of this video file** (an opening before the song is already added in), `from < to`, and a seat never starts before the previous one ends. Optional: `label` (what the maker put in the seat, as the maker named it — a file name), `pin` (why the seat must not move, for a seat the maker pinned) |
| `source_segments` | only without `role`: the video file is these stretches of a longer original, joined in order: `[{"start": 82, "dur": 74}, {"start": 278, "dur": 105}]` (seconds in the original). The narrator's corrections then also give the time in the original |

```json
{ "type": "video", "file": "videos/ending.mp4", "role": "ending",
  "seats": [{ "n": 1, "from": 0, "to": 6, "label": "pictures/02.png" },
            { "n": 2, "from": 6, "to": 12, "label": "pictures/03.png" },
            { "n": 3, "from": 12, "to": 18, "label": "pictures/01.jpg", "pin": "the title at the end of the song" }] }
```

**A linked video** (§2.4) has no `file`. The builder writes the link in one form, whatever form was written
(`https://www.youtube.com/watch?v=ID`), and whole seconds as integers:

```json
{ "type": "video", "url": "https://www.youtube.com/watch?v=8KkKuTCFvzI", "start": 351, "end": 369 }
```

| Field | Meaning |
|---|---|
| `url` | a YouTube link (the forms of §2.4). Not with `file` |
| `start` | seconds into the YouTube video where it starts, `>= 0`. Missing means `0` |
| `end` | seconds into the YouTube video where it stops, after `start`. Missing means the end of the video |
| `captions` | a language code (`ja`, `en`, `pt-BR`): show captions in that language from the start on every device. Missing means YouTube's own default |
| `volume` | how much quieter to play it, in dB, from `-40` to `0` (§2.4). Missing means `0` (as YouTube plays it). The builder writes it only when it is not `0` |

A linked video has no `role`, `seats` or `source_segments`. It counts in the order of the slide's videos like any
other (`video K`, §6), but the narrator cannot point at a stretch of it while practising (change `start` and `end`
in `script.md` instead). A player sends listeners **only the video's YouTube id, `start`, `end`, `captions` and `volume`** — not the link
as written (it can carry more, such as a playlist). Times in the playback messages are seconds into the YouTube video.

A seat holds the times `from <= t < to` (so a time on the line between two seats belongs to the later one). A time
between two seats or outside every seat (an opening or a closing) belongs to no seat.
**Like `notes`, a player must never send `seats`, `label`, `pin` or `source_segments` to a listener's device** —
a label can carry a family's names and dates. Listeners get the video itself and nothing about it but its size.

### 3.4 Joining in the middle

A listener who joins (or rejoins) at slide N must hear the right music.
The player finds it by walking the cues of slides 1..N: the last `bgm` or `bgm-stop` wins.
At slide N itself, a `bgm` with `start: "after-video"` stays silent until the narrator's video has ended (the narrator sends the music when it starts).
Sounds and videos of earlier slides are not replayed.

---

## 4. Media files

| Kind | Formats | Limits |
|---|---|---|
| Pictures | JPEG, PNG, WebP (`.jpg` `.jpeg` `.png` `.webp`) | long side ≤ 1920 px recommended. Any shape; 16:9 fills the screen best |
| Music, sound effects | MP3, AAC (`.mp3` `.m4a`) | — |
| Video | MP4 with H.264 video and AAC audio (`.mp4`) | **≤ 1080p. ≤ 300 MB per file and ≤ 1 GB per work (provisional — set in player stage 2)** |

- **iPhone photos (HEIC) are not accepted.** Export them as JPEG first.
- A linked video (§2.4) is not a file: it has no format or size limit here, and nothing is sent for it.
- **Music that is too loud is played quieter.** Before the show, the narrator's player measures each song of a `[BGM]`,
  `[BGM once]` or `[BGM after video]` (integrated loudness, ITU-R BS.1770). A song louder than **−29 LUFS** is played at **−30 LUFS**
  on every device, so a song from a CD or a streaming service (about −10 to −14 LUFS) sits under the narration like the samples' music
  (−30 to −34 LUFS). A quieter song is not made louder. The file is not changed, and no tool is needed (no ffmpeg).
  Sound effects and the sound of video files are played as they are. A linked video can be made quieter by hand (`volume`, §2.4).
- **A video over the limit is not sent to listeners.** The player tells the narrator to make a lighter copy.
  The player never re-encodes. Who makes the lighter copy:
  - a family making its own video: export again from the editing app at 720p or 1080p;
  - an exporter of an older work: it makes the lighter copy itself.

---

## 5. Checks

| Check | Builder | Player |
|---|---|---|
| No slide headings | error, stop | — |
| Slide numbers not 1..N | error, stop | error |
| Unknown machine cue keyword (`> [Something]`) | error, stop (a typo would silently do nothing) | — |
| A machine cue block with a line that is not a machine cue, or a free cue block with a machine cue on a later line (§2.3) | error, stop | — |
| Two `[Picture]` or `[BGM]`/`[BGM once]`/`[BGM after video]` on one slide | error, stop | — |
| `[BGM after video]` (`start: "after-video"`) on a slide with no `[Video]` | error, stop | error |
| A line that looks like the mark of a hole's narration but is not (`～ `, `〜 `, `~` with no space), or `~ ` with no words (§2.3) | warning (it is read as plain narration) | — |
| `<!--` without `-->` | error, stop (the rest of the script would vanish from the notes) | — |
| `[Text]` with no words, an unknown word on its line, neither or both of `place` and the four lengths, or only some of the four (§2.6) | error, stop | — |
| A word line of `[Text]` that looks like a machine cue | error, stop (a blank line was forgotten) | — |
| Unknown `format` or `version` | — | error, with a message |
| Media file missing | warning, if it can see the media folder | lists missing files **by name** before the show |
| Video over the limit, or not MP4 | warning | not sent; shown to the narrator |
| `[Video]` with a link that is not a YouTube link, a time that is not seconds or `m:ss`, an unknown word after the link, `captions` not a language code, `volume` not dB from `0dB` to `-40dB`, `end` not after `start`, or a time both in the link and after it (§2.4) | error, stop | — |
| `url` not a YouTube link, both `url` and `file`, `start < 0`, `end` not after `start`, `captions` not a language code, `volume` not a number from `-40` to `0`, or `role`/`seats`/`source_segments` on a linked video (§3.3) | — | error |
| Linked video that cannot be played (the owner does not allow other sites, gone, no internet) | — (it cannot see YouTube) | shown to the narrator, for this device and for each listener; never an error window |
| Picture is HEIC | error | error |
| `overlays` not boxes → paragraphs → lines of text (§3.2) | — | error |
| `draft` other than `true` | — | error |
| `overlay_layout` without `overlays`, of another length, or a box or paragraph not as in §3.2 | — | error |
| `overlay_layout` without `slide_size` or `overlay_base` | — | error |
| `role` other than `"ending"`; `seats` without `role: "ending"`; `source_segments` with `role` | — | error |
| `seats` not numbered 1, 2, 3, ..., a seat with `from >= to`, or a seat that starts before the previous one ends | — | error |
| `source_segments` empty, or a stretch with `start < 0` or `dur <= 0` | — | error |

---

## 6. Correction sheet

While **practising a draft** (`draft: true`, audience not yet invited), the narrator may correct the notes and the
overlay words of a slide, and — when the work has `overlay_layout` — move an overlay box, change its size, change the size of its words, or change the colour of its words and of the band behind them. The player **never changes `work.json`** — `work.json` is made from the source
(`script.md`, or the slides of an older work), and a second copy to edit would drift from it.
The player writes a **correction sheet** instead: plain Markdown that a person reads and that can be pasted into
a chat AI, which then edits the source. The work is built again and opened again in the player.

The player keeps the sheet in the browser, keyed by the work's `title`, and reads or writes it **only for a draft**
(so a family member practising the handed-out version of the same work never sees unfinished corrections).
It never leaves the narrator's device except when the narrator copies it or saves it to a file.
Where the browser lets the player open the work folder itself (`showDirectoryPicker`), the save dialog starts in the
work folder (the one with `work.json`), so the sheet lands next to the source, where the person writing it back looks for it.

```````markdown
# Correction sheet: The Lighthouse Keeper's Lamp (2026-10-25 21:04)

## [Slide 1] notes 2
### Before
```
Who do you think lit it?
```
### After
```
Who lit it, do you think?
```
Comment: sounds more like me

## [Slide 2] overlay 1
### Before
```
The storm
```
### After
```
The storm

that night
```

## [Slide 2] layout 1
### Before
```
top 0.18in
size 30pt
```
### After
```
top 0.30in
size 32pt
```

## [Slide 3] layout 1
### Before
```
color #3A3A3A
fill none
```
### After
```
color #FFFFFF
fill #2B4A74
```
Comment: the band in the picture is gone, and the words sank into the sky
```````

- One `##` heading is one correction: `[Slide N]`, then `notes P` or `overlay B` (both counted from 1).
  - `notes P`: the P-th paragraph of the slide's `notes`. **Paragraphs are separated by one or more blank lines**
    (a line with only spaces is blank). One correction per changed paragraph.
    When paragraphs were added or removed, the paragraphs that did not change are lined up first, and each changed
    run becomes one correction, `notes P-Q` when Before holds several paragraphs. A run that only **adds** paragraphs
    also carries the unchanged paragraph just before it (or just after it, at the top), so that Before is never empty
    while the slide has notes. An empty **After** means: remove these paragraphs.
  - `overlay B`: the B-th box of `overlays` (boxes with words only, as in §3.2). An empty **After** means: remove this box.
    Adding a box is asked for in the comment.
  - `layout B`: the place, size and colours of the B-th box (counted as for `overlay B`). Before and After hold one line per
    value that changed, in this order: `left`, `top`, `width`, `height` (the box, in inches with two decimals: `left 0.50in`),
    `size` (the words, in whole points: `size 32pt`; it applies to every paragraph of the box),
    `color` (the words, `color #FFFFFF`; it applies to every paragraph of the box) and `fill` (the band behind the words:
    `fill #1E2C4A`, or `fill none` for no band). Colours are written in capitals. Values that did not
    change are not written. `left` and `top` are the box's `x` and `y` in §3.2; `color` is the colour of the box (§3.2),
    and `fill none` stands for a box with no `fill`. A box with no single colour (§3.2) never has a `color` line.
- **Before** and **After** are fenced so the text keeps its line breaks. In an overlay, the lines of a paragraph are
  lines, and paragraphs are separated by **one blank line**. An empty paragraph is an empty line between two blank lines.
- The fence is made of backticks, **one more than the longest run of backticks in the text** (at least three),
  so a text containing ``` cannot break it.
- `Comment:` is optional and is one line. A comment with no change of text (for example, asking for a new box)
  is a heading `## [Slide N] comment` followed by the `Comment:` line only.
- **Before** is what lets the person or the chat AI find the place in the source: notes are not the source word for word
  (production notes, bold and cues are removed — §3.2).
- The keywords (`Correction sheet`, `[Slide N]`, `notes`, `overlay`, `layout`, `left`, `top`, `width`, `height`, `size`, `color`, `fill`, `none`, `Before`, `After`, `Comment`, `picture`, `video`, `ending seat`, `At`, `Label`, `Pin`, `From`, `To`, `source`, `Use`) are fixed. Do not translate them.

**Pictures and videos** cannot be corrected in the player — a picture is made again, a video is cut again or put
together again, and **the maker chooses** the new one. The sheet only says **what to change, and where**:

````markdown
## [Slide 3] picture
Comment: the lamp should be dark — the storm has put it out

## [Slide 4] picture
Use pictures/_candidates/04-2.png

## [Slide 5] video 2
From 0:12.5 (source 1:34.5)
To 1:10.0 (source 4:58.0)
Comment: start after the interview

## [Slide 7] ending seat 2
At 0:08.3
Label pictures/03.png
Comment: too dark — another photo from that morning
````

- `picture`: a request to make the picture again (or, for a photo, to change it). `Comment:` is **required**.
  A slide has at most one: writing it again replaces it.
  - `Use <path>`: the maker **chose a candidate** in the player. Candidates are `pictures/_candidates/NN-K` with a
    picture extension (§4) — `NN` the slide number in two digits, `K` from 1 — in the work folder or the media folder;
    a tool that makes pictures again puts them there (the ladder's `gen_images.py` does). While practising, the player
    shows the slide's candidates next to the picture now (with the slide's overlay words drawn on them, fitted as the
    builder fits a picture), newest first, and choosing one writes `Use`. `Comment:` is then optional. Choosing
    replaces a request on the same slide, and asking again replaces a choice. The candidate is put in the slide's
    place on the maker's computer (`gen_images.py --use N-K`), never by the player.
- `video K`: the K-th `[Video]` of the slide (counted from 1 in the order written, as in `cues`), and the part the
  narrator wants: `From` and `To` are times in this video file (`m:ss.s`), set from where it was paused. Either
  may be missing (only the start, or only the end). `(source m:ss.s)` follows when the cue has `source_segments`:
  the same moment in the original. A `To` exactly where two stretches meet is the end of the earlier stretch (a `From`
  there is the start of the later one). If the narrator sets a start at or after the end (or an end at or before the
  start), the other one is dropped. `Comment:` is optional.
- `ending seat N`: seat N of the slide's ending video (`role: "ending"` with `seats`), pointed at while paused:
  `At` is where it was paused; `Label` and `Pin` copy the seat's `label` and `pin` when it has them. It asks for
  **another picture in that seat**; `Comment:` (optional) says why. The seat keeps its place on the song.
- One slide may have several of these, and any of them next to text corrections. A slide's `comment` stays as above.

These three are **never judged as done by Before and After** (there is no text to compare). The player remembers,
next to the sheet but not in the Markdown, which picture or video file was pointed at (its size and date, and the
picture's path — for a slide with `picture_source`, that file, not the built picture, which every build writes again), the seat's `label`, and the video's `source_segments`. When the work is opened again and that file, label or cut has
changed (or the video is gone), the player shows the correction as
**changed — look, and remove it**. It never removes one by itself: something changed, but not necessarily as wished.
A new candidate for a picture that the maker has not chosen yet changes nothing: the slide still shows the old picture.
A `picture` with `Use` is **done** (removed by itself) when the picture has changed **and** the chosen candidate is no
longer among the candidates (it was moved into the slide's place); when the picture changed but the candidate is still
there, it is **changed — look, and remove it**.

When the corrected work is opened again, the player compares each correction with **the same slide** of the new work,
whole paragraph or whole box at a time (trailing spaces of each line ignored; a Before or After of several
paragraphs must appear as the same paragraphs one after another):

| Correction | Done (removed by itself) | Done, but reworded (shown; the narrator removes it) | Not done (kept) |
|---|---|---|---|
| After is not empty | a paragraph/box equal to After | neither After nor Before is there | a paragraph/box equal to Before |
| After is empty (removed) | no paragraph/box equal to Before | — | a paragraph/box equal to Before |

"Reworded" happens when the source was edited while writing the correction back (for example to follow its own rules).
It also happens when Before changed for another reason, so the player never removes it by itself.
A comment with no change of text is never judged; the narrator removes it.

A `layout` correction is judged on the values it names, read from `overlay_layout` of the same box and rounded as the
sheet writes them (inches to two decimals, points to whole numbers, colours in capitals, a box with no `fill` as
`fill none`): **Done** when every value equals After;
**Not done** when every value equals Before; otherwise **Done, but reworded**.
A `color` correction on a box that now has no single colour (§3.2) is **Done, but reworded**.
