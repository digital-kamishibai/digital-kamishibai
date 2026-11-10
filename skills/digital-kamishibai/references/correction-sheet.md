# Writing a correction sheet back into the script

While practising a draft (built with `--draft`), the narrator corrects the narration and the words on the screen in the
room player, moves or resizes the words on the picture, and changes their colour and the band behind them. The player never changes the work; it gives a
**correction sheet** — Markdown the maker pastes into the chat or saves as a file. Your job is to write each correction
back into `script.md`, build again, and check.

The format is defined in `docs/work-format.md` §6 of the Digital Kamishibai repository; this page is how to write it back.
Keywords of the sheet (`Correction sheet`, `[Slide N]`, `notes`, `overlay`, `layout`, `comment`, `Before`, `After`,
`Comment`, `left`, `top`, `width`, `height`, `size`, `color`, `fill`, `none`, `picture`, `video`, `ending seat`, `At`, `Label`, `Pin`, `From`,
`To`, `source`, `Use`) are never translated.

## Before writing anything back: gather, sort, stop

**Gather.** The player's sheet **keeps growing**: each time it is saved, everything not yet done is in it again.
For each work, the sheet with the **newest date in its name** is the one to use; older ones are old copies — do not add
them together. A "conflicted copy" made by a sync service is an old copy too; if it differs from the newest sheet, show
the maker. A sheet saved in the wrong folder still counts: look for `*-corrections-*` files near the work as well, and
ask the maker which work a stray sheet belongs to before using it. If the maker also changed the plan or the script by
hand since the last write-back, find those changes too (compare with the last saved version) — without deciding who
made them.

**Sort** what is in the sheets into three, and show the maker before changing anything:

| | What goes in | How to show it |
|---|---|---|
| **1. Things you can do** | `notes`, `overlay`, `layout`; a `picture` with `Use` (the maker chose that candidate: `--use`); a `picture` (the changed prompt — making pictures waits for the maker, who hears the count and the cost first); a `comment` whose wish is clear | per work and per slide, Before → After in one line. Never reword After. If After brings a new fact, say it needs checking |
| **2. Things to ask the maker** | Before not found in the script; a `comment` that could mean two things; `video` and `ending seat` (the maker cuts and chooses — you prepare the new start and end, or the storyboard with `--mark`); choosing among generated candidates | one short question each, that can be asked aloud ("Where should the music on slide 8 start?") |
| **3. Something wrong with a tool** | the player, the builder or `check_sheet.py` behaving oddly (a sheet that is malformed, a status that is wrong) | a short report for the Digital Kamishibai repository's issues, in general terms: no title, no contents, no names from the work |

What the maker changed by hand: list it briefly (which slide, what changed), **with no judgement and no suggestions** —
it is there so the adult can say "I saw it".

**Stop** here until the maker (or the adult working with a child maker) says to go on. Then write back as below.

When everything is written back and checked, tell the maker what changed, slide by slide, in a few short lines, and the
questions from group 2, one at a time. If an adult adds words of their own to that message, **pass them on as written**:
do not polish them.

## The rule above all

**The maker decides.** Write After as it is — do not reword it, even to follow the pitfalls. If you see a problem
(a fact you have not checked, a negative at the end of a slide), say so once, after writing it back, and let the maker
choose. If After brings in a **new fact** (a number, a year, a name), check it as in step 3.5 of the skill.

## One correction at a time

A sheet looks like this (fences are made of three or more backticks):

````markdown
# Correction sheet: The Lighthouse Keeper's Lamp (2026-10-25 21:04)

## [Slide 1] notes 2
### Before
```
Who do you think lit it, every night, for forty years?
```
### After
```
Who lit it, do you think, every night, for forty years?
```
Comment: sounds more like me
````

| Heading | What to change in `script.md` |
|---|---|
| `## [Slide N] notes P` (or `notes P-Q`) | In slide N, find the paragraph(s) that read as **Before** once production notes (`<!-- -->`), machine cues and `**` are taken away, and replace them with **After**. Keep production notes and cues that sit around unchanged words. A paragraph of a free cue starts with `> ` — keep that mark. An empty After removes the paragraphs |
| `## [Slide N] overlay B` | The **B-th `[Text]` block** of slide N (counted in the order written). Replace its word lines with After: each line becomes `> line`; a blank line between paragraphs becomes a line that is only `>`. An empty After removes the whole `[Text]` block |
| `## [Slide N] layout B` | The `[Text]` line of the B-th block. Each line of After (`top 0.67in`, `size 62pt`, `color #FFFFFF`, `fill #1E2C4A`) replaces the same word's value, or is **added** when the line does not have that word yet. `fill none` means no band: **remove** the `fill` word (never write `fill none` on the line — the builder stops). If After has a length and the line uses `place`, write all four lengths instead of `place`, taking the ones not in After from the band (`left 0.50in`, `width 12.33in`, `height 1.20in`; `top 0.30in` / `3.15in` / `6.00in` for top / middle / bottom); a change of `size`, `color` or `fill` alone keeps `place`. After writing back a colour, look at the slide once (or at the player's light-against-dark number when the work is opened again): the maker chose the colour, but a number under 70 is worth one sentence |
| `## [Slide N] comment` | No change of text; the `Comment:` line asks for something (often a new box). Do it if it is clear; otherwise ask the maker |
| `## [Slide N] video K` with `Volume -6dB (was 0dB)` | The narrator made the K-th `[Video]` of slide N (a YouTube link) quieter or louder by ear while practising. On that `[Video]` line, set `volume -6dB` (replace the `volume` word's value, or add `volume -6dB` at the end of the line). `Volume 0dB` means: **remove** the `volume` word. If the line does not say `was` now (its `volume` changed since), ask the maker |

- `Comment:` under a correction is the maker's reason or wish. Read it; it may ask for more than the change itself.
- A `comment` about the **ending video** (a photo in it, not the words of the slide) is not written back either:
  take it to the storyboard as below, with the seat the maker means.

## Pictures and videos: not written back — the maker chooses

`picture`, `video K` (with `From`/`To`) and `ending seat N` say what to change and where. They have no After: a new picture, a new cut
or another photo in a seat is **chosen by the maker**. Never pick it yourself, and never write these into `script.md`.

| Heading | What to do |
|---|---|
| `## [Slide N] ending seat S` | The maker wants another picture in seat S of the ending video (`At` is where they paused, `Label` the picture there now, `Pin` the reason the seat is pinned). Make the storyboard with those seats already pointed at, show it to the maker, and let them choose: `python <repository>/ladder/ending-video/build_ending_video.py <work folder> --storyboard --mark S,T` (all the ending seats of the sheet). Then follow the ladder's steps (`references/ending-video.md`): `--replace S=FILE` for what they chose, the storyboard again, build, the stutter check. A pinned seat holds a lyric or a moment on the song: tell the maker before changing it. **Do not use `--replace` before the maker has chosen** |
| `## [Slide N] picture` with `Use` | The maker **chose a candidate** in the player (`Use pictures/_candidates/NN-K.png`). Put it in place: `python <repository>/ladder/images/gen_images.py <work folder> --use N-K` (the old picture moves to `pictures/_replaced/`), then build the draft again. If the ending video showed the old picture, `--use` (and the builder) name the seat and the `--replace` command: tell the maker, and replace it, then make the storyboard and the video again, only when they want the new picture there too. A `Comment:` next to it is a wish on top of the choice: read it, and ask if it means the picture should be made again |
| `## [Slide N] picture` | The maker wants the picture of slide N made again; `Comment:` (always there) says what should change. **A generated picture** (the plan has its `[Prompt N]`; `references/pictures.md`): change that prompt in the plan so it asks for what the comment says, and show the maker the change. Then, only when they want it and after saying how many pictures and what they cost, make a candidate: `python <repository>/ladder/images/gen_images.py <work folder> N`. It goes to `pictures/_candidates/` and the slide keeps its old picture. **The maker chooses in the player**: when the work is opened again, the slide shows its candidates next to the picture now, and choosing one puts `Use` on the next sheet. Tell the maker, in your message, that slide N has new candidates to choose from in the player — a candidate nobody hears about is never chosen. If they tell you their choice another way, `--use N-K` for the one they chose (the old picture moves to `pictures/_replaced/`). **Do not use `--use` before the maker has chosen.** `--use` saves the picture as `pictures/NN.png`: if the slide's `[Picture]` line names another file, change the line to it. **A photo or a child's drawing**: tell the maker what the comment asks; they take or draw another one and put it in place (under the same name, or change the `[Picture]` line to the new one, as they say). Never draw over or edit a family picture yourself |
| `## [Slide N] video K` | The narrator wants another part of the K-th `[Video]` of slide N (counted in the order written). `From` and `To` are times **in that video file as it is now**; a missing one means "keep this end". `(source m:ss.s)` is the same moment in the longer original it was cut from, when the work knows the cut (`source_segments`). **Do not cut the video yourself.** Tell the maker the new start and end; they cut it again in the app they made it with — from the original when the new part reaches outside the present file (what was cut away cannot come back from it). The new file goes where the old one was, or the `[Video]` line changes to its name, as they say. If the work keeps its cuts in a definition file, show the maker the changed cut and change it only when they agree; then cut again with the tool that reads that file |

After the maker has chosen the new picture, or the new ending video or the new cut is made, build the draft again (below).
When the work is opened again, the player shows a picture, a seat or a cut whose file has changed as
**changed — look, and remove it**; it never removes one by itself. A candidate the maker has not chosen yet changes
nothing: the picture correction stays **not done yet**.
- **If Before is not in the script** (the script changed after the sheet was made), do not guess. Show the maker the
  slide and ask where the change belongs.
- Several corrections on one slide: apply them from the top. A correction that adds paragraphs carries the unchanged
  paragraph next to it in Before, so it can be found.

## Build and check

1. Build the draft again: `python <skill>/scripts/build_work.py <work folder> --draft`.
2. Check the sheet against the new script — the same rules the player uses when the work is opened again:

   ```
   python <skill>/scripts/check_sheet.py <work folder> <sheet.md>
   ```

   Each correction is `done`, `reworded` (neither Before nor After is there — fine if you changed it on purpose; say so)
   or `PENDING` (Before is still there: not written back). Fix every `PENDING` before handing back. Comments are listed
   for you to answer. Pictures and videos are listed as `look` (the maker has not chosen yet; a new picture or a new cut
   of a video is in the file, not in `script.md`, so the check cannot see it) or, for an ending seat that now holds another
   picture, `changed`; neither is `PENDING`. The player sees a new picture or video file when the work is opened again.
   A picture with `Use` is `PENDING` while the chosen candidate is still in `pictures/_candidates/` (run `--use`), and
   `done` once it has been put in place. A `Volume` is `PENDING` while the `[Video]` line still has the old volume
   (`was`), `done` once it has the new one, and `changed` when it has another.
3. Tell the maker what you changed, slide by slide, and ask them to open the work again in the player.
   The player removes the corrections that are done by itself and shows the rest.
   **If you made candidates, say which slides have them** and that the maker chooses in the player
   (the slide shows its candidates, to compare and choose, while practising). Until one is chosen, the slide keeps its old picture.

If the sheet was pasted into the chat, save it as a file first (for example next to `script.md`) so the check can read it.
On a platform where you cannot run Python, write the corrections back and list them for the maker; the player's own
check when the work is opened again is then the only check.
