# ⟨Maker⟩'s kamishibai

The works of one maker, one folder per work. The tools are not in here: they come from the Digital Kamishibai
repository (installed as a Claude Code or Codex plugin, or a copy of it next to this folder). Do not copy the tools in.

```
works/
  ⟨work⟩/
    plan.md              the plan (and the picture prompts, if pictures are generated)
    script.md            the script: narration, cues, words on the screen  <- the source of truth
    pictures/01.jpg ...  the pictures, by slide number
    sounds/              music and sound effects (not committed)
    videos/              videos, the ending video too (not committed)
    ending_video.json    the ending video's seats (if there is one)
    work.json            made by the builder from script.md (never edit it; not committed)
```

## Working with an AI

`AGENTS.md` tells the AI how to work here (Codex reads it; `CLAUDE.md` only points Claude Code to it — change
`AGENTS.md`, not both). At the start of planning, writing, practising or a correction sheet, call the skill by name:
`/digital-kamishibai:digital-kamishibai` in Claude Code, `$digital-kamishibai` in Codex. In the middle of a
conversation it is not always picked by itself.

## Commands

`<tools>` is the folder of the Digital Kamishibai repository.

```
python <tools>/skills/digital-kamishibai/scripts/doctor.py --for basic --for ending-video   # what this computer lacks
python <tools>/skills/digital-kamishibai/scripts/build_work.py works/<work> --draft         # for practising
python <tools>/skills/digital-kamishibai/scripts/build_work.py works/<work>                 # for the show
python <tools>/ladder/ending-video/build_ending_video.py works/<work> --storyboard           # the ending video
```

Then open the room player and choose `works/<work>`.

## What is kept here

- Kept: the plan, the script, the pictures (fully opaque pictures without an alpha channel, at most 1920 px on the long
  side), `ending_video.json`.
- Not kept (`.gitignore`): `work.json` and the pictures drawn by the builder (`pictures/_built/`), picture candidates, music, videos, the
  storyboard (it holds the family's photos). Keep those safe somewhere else: a song the ending video is timed to cannot
  be swapped for another download of the same song.

Change `script.md`, never `work.json`: the builder writes `work.json` again every time.
