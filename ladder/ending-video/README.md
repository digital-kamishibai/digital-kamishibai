# Ladder: the ending video

Optional. **Free, but needs software**: Python 3.10 or later, Pillow (`python -m pip install pillow`) and
[ffmpeg](https://ffmpeg.org/) with ffprobe on the PATH. You do not need it: a phone's photo app or a free video editor
makes an ending video too (see the skill's `references/ending-video.md`). This tool is for a family that wants to point
at seats on a storyboard and have the video re-made exactly, as often as they like.

The ending video is the family's photos and videos, from the beginning until now, on one song, after the story.

## The idea: seats first, pictures later

The song is cut into **seats**: each has a start (`at`, seconds into the song) and a length (`dur`). The seats never
move. Pictures and videos are only *put into* seats — replacing, reordering and sorting change what sits in a seat,
never when it starts. So you can build the whole video before anything is chosen, and no change ever slips a picture
against the song.

## Use

```
python build_ending_video.py <work> --init --audio sounds/song.mp3 --photos "D:/Photos/family"   # a first timeline
python build_ending_video.py <work> --storyboard        # ending/storyboard.html: point at the seats to change
python build_ending_video.py <work> --storyboard --mark 17,20   # the same, with the seats of a correction sheet already pointed at
python build_ending_video.py <work> --replace 17=2016/bike.jpg --replace 3=2019/run.mp4@1.2   # @ = start second
python build_ending_video.py <work> --move 14=2         # the content of seat 14 goes after seat 2
python build_ending_video.py <work> --sort 1-30         # by date taken; pinned seats stay
python build_ending_video.py <work> --pin-set 42="the first line of the chorus"
python build_ending_video.py <work> --confirm 1-22      # mark what the maker has decided
python build_ending_video.py <work>                     # build videos/<output>
python build_ending_video.py <work> --check             # files, song, video, storyboard up to date
python check_smoothness.py <work>                       # judder check of the finished video
```

- `--init` cuts the song into equal seats (`--seat 5` seconds) and fills them with photos from `--photos`, by date
  taken. Everything starts as a placeholder: **the maker chooses**. It never overwrites a definition.
- After any change, run `--storyboard` again before pointing at more seats (`--check` says when it is old).
- On another computer, where the photos are in another folder: `--photo-root <folder>`.
- One work, two ending videos: `--config NAME` (its own definition, storyboard and cache).

The finished video goes to `videos/<output>`, ready for the room player's `[Video]` cue: 1920x1080, -22 LUFS,
and re-encoded to about 270 MB if it would be over the player's 300 MB.

## The definition (`ending_video.json`)

```json
{
 "audio": "sounds/song.mp3", "audio_sha256": "...", "audio_duration_sec": 20.0, "duration_sec": 20.0,
 "photo_root": "D:/Photos/family", "output": "ending.mp4",
 "final_still": {"title": "The title", "color": "#FFFFFF", "title_pt": 40, "top_in": 0.8},
 "page": {"lang": "en", "title": "The title", "lead": "...", "beat_notes": {"Chorus": "..."}},
 "prologue": {"src": "2019/first-steps.mp4", "dur": 8, "start_sec": 2, "fade_out": 1.5, "gain_db": 6},
 "frames": [
  {"i": 1, "at": 0.0, "dur": 6.0, "xfade": 0.8, "beat": "Intro", "src": "2013/a.jpg", "status": "picked"},
  {"i": 2, "at": 6.0, "dur": 5.0, "xfade": 0.6, "beat": "Verse", "kind": "clip", "src": "2014/b.mp4",
   "clip_start_sec": 3.5, "pin": "the first line of the verse"},
  {"i": 3, "at": 11.0, "dur": 9.0, "kind": "final", "root": "work", "src": "pictures/01.png", "zoom": 1.0}
 ]
}
```

| In a seat | |
|---|---|
| `at`, `dur`, `xfade`, `beat`, `zoom`, `zoom_from`, `zoom_center`, `ease`, `pin` | belong to the seat: they stay when the content changes |
| `src`, `kind` (`photo` / `clip` / `final`), `status` (`placeholder` / `picked` / `confirmed`), `clip_start_sec`, `clip_hold_sec`, `clip_parts`, `rotate`, `root` | the content |

- Photos zoom in slowly (`zoom`, default 1.06; `1.0` holds still). `zoom_from` zooms out instead, keeping
  `zoom_center` ([x, y], 0 to 1) in place: a subject moving away. The moves are drawn at sub-pixel positions;
  `check_smoothness.py` measures the result.
- Videos are silent: the song is the only sound. `rotate` (`cw`, `ccw`, `180`) is for a video whose rotation
  information is wrong (people lying on their side). `clip_hold_sec` holds the last frame; `clip_parts` joins several
  stretches of one video.
- The prologue and epilogue play one family video **with its own sound**, before and after the song (never on top).
- `audio_sha256` ties the seats to that exact song file: another download of the same song is usually a little
  longer or shorter, and every seat would be off.

## Keep out of a repository

`ending/` (the storyboard and the cache) and `videos/` contain the family's photos. The definition is text: keep it with
the work. Keep the song file safe too — the seats are timed to it.

## Try it on the example

```
mkdir examples/sample-story/sounds
ffmpeg -f lavfi -i "sine=frequency=330:duration=18" -af volume=0.3 examples/sample-story/sounds/ending.mp3
python ladder/ending-video/build_ending_video.py examples/sample-story --storyboard
python ladder/ending-video/build_ending_video.py examples/sample-story
python ladder/ending-video/build_ending_video.py examples/sample-story --replace 1=pictures/03.png
python ladder/ending-video/build_ending_video.py examples/sample-story --storyboard
python ladder/ending-video/build_ending_video.py examples/sample-story
```

(`--replace` changes `examples/sample-story/ending_video.json`; put it back with `git checkout` afterwards.)
